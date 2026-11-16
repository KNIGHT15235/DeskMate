"""R1 contracts: entry parity, isolated state and explicit resource ownership."""
from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest

from likecc import __main__ as cli
from likecc.client import LLMClient, create_client, resolve_context_window
from likecc.config import AppConfig, MCPServerConfig, ProviderConfig
from likecc.context.manager import persist_tool_result
from likecc.hooks import Action, Hook, HookEngine
from likecc.permissions import PermissionMode
from likecc.runtime import Runtime
from likecc.teams.spawn_inprocess import InProcessTeammateHandle
from likecc.tools.agent_tool import AgentToolParams
from likecc.tools.base import StreamEnd, TextDelta


class FakeClient(LLMClient):
    def __init__(self):
        self.closed = 0
        self.schemas = []

    async def stream(self, conversation, system="", tools=None):
        self.schemas.append(tools or [])
        yield TextDelta("offline-runtime-result")
        yield StreamEnd("end_turn")

    async def aclose(self):
        self.closed += 1


@pytest.fixture
def config(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return AppConfig(providers=[ProviderConfig(
        "offline", "openai-compat", "http://unused.invalid", "offline",
        api_key="fake", context_window=32000,
    )])


@pytest.fixture
def clients(monkeypatch):
    instances = []

    def factory(provider):
        instance = FakeClient()
        instances.append(instance)
        return instance

    monkeypatch.setattr("likecc.client.create_client", factory)
    return instances


def make_runtime(config, tmp_path, **kwargs):
    return Runtime(config=config, work_dir=tmp_path,
                   permission_mode=PermissionMode.DEFAULT, **kwargs)


def test_runtime_assembles_with_textual_imports_blocked(tmp_path):
    # A fresh interpreter rules out accidentally relying on an already imported UI.
    script = '''
import asyncio, sys
from pathlib import Path
class NoTextual:
    def find_spec(self, fullname, *args):
        if fullname == "textual" or fullname.startswith("textual."):
            raise AssertionError("runtime imported Textual")
sys.meta_path.insert(0, NoTextual())
from likecc import client
from likecc.config import AppConfig, ProviderConfig
from likecc.permissions import PermissionMode
from likecc.runtime import Runtime
class Fake(client.LLMClient):
    async def stream(self, *args, **kwargs):
        if False:
            yield
client.create_client = lambda _: Fake()
async def check():
    config = AppConfig([ProviderConfig("fake", "openai-compat", "", "fake")])
    runtime = Runtime(config=config, work_dir=sys.argv[1], permission_mode=PermissionMode.PLAN)
    try:
        await runtime.initialize(config.providers[0])
        runtime.assemble_delegation(interactive=False)
        assert runtime.agent.work_dir == str(Path(sys.argv[1]).resolve())
        assert runtime.agent.permission_mode == PermissionMode.PLAN
        assert runtime.registry.get("Agent") is not None
    finally:
        await runtime.aclose()
asyncio.run(check())
'''
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio
async def test_runtime_instances_isolate_config_tools_permissions_and_disk_results(config, clients, tmp_path):
    first = make_runtime(config, tmp_path, cache_files=True)
    second = make_runtime(config, tmp_path, cache_files=True)
    try:
        await first.initialize(config.providers[0])
        await second.initialize(config.providers[0])
        first.assemble_delegation(interactive=False)
        second.assemble_delegation(interactive=False)
        first.registry.mark_discovered("Agent")
        first.registry.disable("WriteFile")
        first.file_cache.put("same", "first")
        first.agent.set_permission_mode(PermissionMode.PLAN)
        first.agent.active_skills["first"] = "loaded"
        first.provider.set_fetched_context_window(123456)
        first.config.worktree.symlink_directories.append("first-only")
        first.team_manager.name_registry.register("reviewer", "first-agent")
        second.team_manager.name_registry.register("reviewer", "second-agent")
        assert not second.registry.is_discovered("Agent")
        assert second.registry.is_enabled("WriteFile")
        assert second.file_cache.get("same") is None
        assert second.agent.permission_mode == PermissionMode.DEFAULT
        assert second.agent.active_skills == {}
        assert second.provider._fetched_context_window == 0
        assert config.providers[0]._fetched_context_window == 0
        assert "first-only" not in second.config.worktree.symlink_directories
        assert "first-only" not in config.worktree.symlink_directories
        assert first.team_manager.name_registry.resolve("reviewer") == "first-agent"
        assert second.team_manager.name_registry.resolve("reviewer") == "second-agent"
        a = persist_tool_result("same-call", "first", first.agent.session_dir)
        b = persist_tool_result("same-call", "second", second.agent.session_dir)
        assert a != b
        assert a.read_text() == "first"
        assert b.read_text() == "second"
    finally:
        await asyncio.gather(first.aclose(), second.aclose())
    assert [client.closed for client in clients] == [1, 1]


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_partial_initialization_releases_client(config, clients, tmp_path, monkeypatch, cancel):
    started = asyncio.Event()

    async def fail_or_wait(provider):
        started.set()
        if cancel:
            await asyncio.Event().wait()
        raise ValueError("metadata failure")

    monkeypatch.setattr("likecc.client.resolve_context_window", fail_or_wait)
    runtime = make_runtime(config, tmp_path)
    task = asyncio.create_task(runtime.initialize(config.providers[0], resolve_context=True))
    await started.wait()
    if cancel:
        task.cancel()
    with pytest.raises(asyncio.CancelledError if cancel else ValueError):
        await task
    await runtime.aclose()
    assert clients[0].closed == 1


@pytest.mark.asyncio
async def test_cancelled_and_concurrent_close_waits_for_resource_finalizer(config, tmp_path, monkeypatch):
    started, release = asyncio.Event(), asyncio.Event()

    class SlowClient(FakeClient):
        async def aclose(self):
            started.set()
            await release.wait()
            await super().aclose()

    client = SlowClient()
    monkeypatch.setattr("likecc.client.create_client", lambda _: client)
    runtime = make_runtime(config, tmp_path)
    await runtime.initialize(config.providers[0])
    close = asyncio.create_task(runtime.aclose())
    await started.wait()
    second = asyncio.create_task(runtime.aclose())
    close.cancel()
    await asyncio.sleep(0)
    close.cancel()
    await asyncio.sleep(0)
    assert not close.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await close
    await second
    await runtime.aclose()
    assert client.closed == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("scheduled", [False, True])
async def test_close_reaps_background_agents_before_transport(config, tmp_path, monkeypatch, scheduled):
    started, finalized = asyncio.Event(), asyncio.Event()
    client = FakeClient()
    monkeypatch.setattr("likecc.client.create_client", lambda _: client)
    runtime = make_runtime(config, tmp_path)
    await runtime.initialize(config.providers[0])

    async def blocked(*args):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            assert client.closed == 0
            finalized.set()

    runtime.agent.run_to_completion = blocked
    task_id = runtime.task_manager.launch(runtime.agent, "blocked")
    if scheduled:
        await started.wait()
    await runtime.aclose()
    assert runtime.task_manager.get(task_id).status == "cancelled"
    if started.is_set():
        assert finalized.is_set()
    assert client.closed == 1


@pytest.mark.asyncio
async def test_close_reaps_team_handle_and_model_override(config, clients, tmp_path):
    runtime = make_runtime(config, tmp_path)
    await runtime.initialize(config.providers[0])
    runtime.assemble_delegation(interactive=False)
    result = await runtime.registry.get("Agent").execute(AgentToolParams(
        prompt="offline", description="test", subagent_type="general-purpose", model="test-model",
    ))
    assert not result.is_error
    assert len(clients) == 2
    assert clients[1].closed == 0  # retained until all children are quiescent
    started, finalized = asyncio.Event(), asyncio.Event()

    async def teammate():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            assert all(client.closed == 0 for client in clients)
            finalized.set()

    task = asyncio.create_task(teammate())
    runtime.team_manager.register_inprocess_handle("child", InProcessTeammateHandle(
        agent=runtime.agent, task=task, name="child",
    ))
    await started.wait()
    await runtime.aclose()
    assert task.done() and finalized.is_set()
    assert [client.closed for client in clients] == [1, 1]


@pytest.mark.asyncio
async def test_cleanup_failure_attempts_other_resources(config, clients, tmp_path, monkeypatch, caplog):
    runtime = make_runtime(config, tmp_path)
    await runtime.initialize(config.providers[0])

    async def fail():
        raise RuntimeError("worker cleanup failed")

    monkeypatch.setattr(runtime.task_manager, "shutdown", fail)
    await runtime.aclose()
    await runtime.aclose()
    assert clients[0].closed == 1
    assert "worker cleanup failed" in caplog.text


@pytest.mark.asyncio
async def test_entries_use_shared_core_and_preserve_capabilities(config, clients, tmp_path, monkeypatch, capsys):
    from likecc.app import LikeCCApp

    assembled = []
    original = Runtime.initialize

    async def record(self, *args, **kwargs):
        await original(self, *args, **kwargs)
        assembled.append(self)

    monkeypatch.setattr(Runtime, "initialize", record)
    project = tmp_path / "project"
    project.mkdir()
    # Deliberately keep process cwd elsewhere: the supplied project must win.
    app = LikeCCApp(config.providers, work_dir=project, permission_mode=PermissionMode.PLAN)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.agent is app.runtime.agent
        assert app.registry is app.runtime.registry
        assert app.agent.work_dir == str(project)
        assert app.agent.permission_mode == PermissionMode.PLAN
        assert app.agent.memory_manager is app.memory_manager
        assert app.session and app.skill_loader
        assert app.registry.get("AskUserQuestion") is not None
        assert app.registry.get("LoadSkill") is not None
        assert app.registry.get("ExitPlanMode") is not None
        assert app.command_registry.find("help") is not None
        session = app.session
    assert session._file.closed
    await app._close_resources()
    await cli._run_prompt(config, PermissionMode.PLAN, None, "offline", work_dir=str(project))
    assert capsys.readouterr().out.strip() == "offline-runtime-result"
    assert len(assembled) == 2
    headless = assembled[1]
    assert headless.agent.work_dir == str(project)
    assert headless.agent.permission_mode == PermissionMode.PLAN
    assert headless.agent.memory_manager is None
    assert headless.agent.session_id == ""
    assert headless.registry.get("LoadSkill") is None
    assert headless.registry.get("AskUserQuestion") is None
    assert headless.registry.get("ExitPlanMode") is None
    assert all(client.closed == 1 for client in clients)


@pytest.mark.asyncio
async def test_headless_extension_failure_closes_core_and_hooks(config, clients, tmp_path, monkeypatch):
    def fail(self):
        raise RuntimeError("agent definitions failed")

    monkeypatch.setattr("likecc.agents.loader.AgentLoader.load_all", fail)
    hooks = HookEngine([Hook(id="stop", event="shutdown", action=Action(type="prompt", message="stopped"))])
    with pytest.raises(RuntimeError, match="agent definitions failed"):
        await cli._run_prompt_with_hook_cleanup(config, PermissionMode.DEFAULT, hooks, "offline", work_dir=str(tmp_path))
    assert clients[0].closed == 1
    assert [note.event for note in hooks.drain_notifications()] == ["shutdown"]


@pytest.mark.asyncio
async def test_tui_extension_failure_closes_session_and_core(config, clients, tmp_path, monkeypatch):
    from likecc.app import LikeCCApp

    def fail(self):
        raise RuntimeError("skills failed")

    monkeypatch.setattr("likecc.skills.loader.SkillLoader.load_all", fail)
    app = LikeCCApp(config.providers, work_dir=tmp_path)
    with pytest.raises(RuntimeError, match="skills failed"):
        await app._select_provider(config.providers[0])
    assert app.session._file.closed
    assert clients[0].closed == 1
    await app.on_unmount()
    assert clients[0].closed == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("initializing", [False, True])
async def test_tui_mcp_lifetime_has_one_owner_on_exit(config, clients, tmp_path, monkeypatch, initializing):
    import likecc.app as ui

    started = asyncio.Event()
    acquired, closed = [], []

    class FakeMCP:
        _clients = {}

        def load_configs(self, configs):
            pass

        async def register_all_tools(self, registry):
            acquired.append(asyncio.current_task())
            started.set()
            if initializing:
                await asyncio.Event().wait()
            return []

        async def shutdown(self):
            closed.append(asyncio.current_task())

    monkeypatch.setattr(ui, "MCPManager", FakeMCP)
    app = ui.LikeCCApp(config.providers, work_dir=tmp_path,
                      mcp_servers=[MCPServerConfig("fake", command="unused")])
    async with app.run_test() as pilot:
        await asyncio.wait_for(started.wait(), timeout=2)
        await pilot.pause()
    await app._close_resources()
    assert len(closed) == 1
    assert closed == acquired
    assert clients[0].closed == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("protocol", ["anthropic", "openai", "openai-compat"])
async def test_real_sdk_transport_is_closed_without_network(protocol):
    client = create_client(ProviderConfig("test", protocol, "http://unused.invalid", "test", api_key="fake"))
    await client.aclose()
    await client.aclose()
    assert client._client.is_closed()


@pytest.mark.asyncio
async def test_model_metadata_cancellation_closes_temporary_client(monkeypatch):
    started = asyncio.Event()

    class MetadataClient(FakeClient):
        async def fetch_model_context_window(self):
            started.set()
            await asyncio.Event().wait()

    client = MetadataClient()
    monkeypatch.setattr("likecc.client.create_client", lambda _: client)
    task = asyncio.create_task(resolve_context_window(ProviderConfig("fake", "anthropic", "", "test")))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert client.closed == 1


@pytest.mark.asyncio
async def test_tui_real_local_mcp_connection_closes_on_unmount(config, clients, tmp_path):
    from likecc.app import LikeCCApp

    server = tmp_path / "server.py"
    server.write_text(
        'from mcp.server.fastmcp import FastMCP\n'
        'server = FastMCP("runtime-test")\n'
        '@server.tool()\n'
        'def hello() -> str:\n'
        '    return "local-mcp-result"\n'
        'server.run(transport="stdio")\n', encoding="utf-8",
    )
    app = LikeCCApp(config.providers, work_dir=tmp_path, mcp_servers=[
        MCPServerConfig("local", command=sys.executable, args=[str(server)]),
    ])
    async with app.run_test() as pilot:
        await asyncio.wait_for(app._mcp_ready.wait(), timeout=10)
        assert app.mcp_manager is not None
        connection = await app.mcp_manager.get_client("local")
        assert connection.is_alive
        response = await connection.call_tool("hello", {})
        assert response.content[0].text == "local-mcp-result"
        await pilot.pause()
    assert not connection.is_alive
    assert app.mcp_manager is None
    assert clients[0].closed == 1


@pytest.mark.asyncio
async def test_tui_sessions_and_hook_lifetimes_are_separate(config, clients, tmp_path):
    from likecc.app import LikeCCApp

    def hooks():
        return HookEngine([
            Hook(id=event, event=event, action=Action(type="prompt", message=event))
            for event in ("startup", "shutdown")
        ])

    first_hooks, second_hooks = hooks(), hooks()
    first = LikeCCApp(config.providers, work_dir=tmp_path, hook_engine=first_hooks)
    second = LikeCCApp(config.providers, work_dir=tmp_path, hook_engine=second_hooks)
    async with first.run_test() as pilot:
        await pilot.pause()
        first_session = first.session
        first.registry.mark_discovered("LoadSkill")
    async with second.run_test() as pilot:
        await pilot.pause()
        assert first_session.session_id != second.session.session_id
        assert not second.registry.is_discovered("LoadSkill")
        assert second.conversation.history == []
    await first._close_resources()
    await second._close_resources()
    assert [note.event for note in first_hooks.drain_notifications()] == ["startup", "shutdown"]
    assert [note.event for note in second_hooks.drain_notifications()] == ["startup", "shutdown"]
    assert all(client.closed == 1 for client in clients)
