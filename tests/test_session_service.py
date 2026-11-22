from __future__ import annotations

import asyncio
from contextlib import aclosing
import json
from pathlib import Path

import pytest

from likecc.agent import LoopComplete, PermissionRequest, StreamText, ToolResultEvent, ErrorEvent
from likecc.config import AppConfig, ProviderConfig, MCPServerConfig
from likecc.extensions import ExtensionOptions, RuntimeExtensions
from likecc.permissions import PermissionMode
from likecc.runtime import Runtime
from likecc.service import SessionService
from likecc.tools.base import TextDelta, ToolCallComplete, StreamEnd
from test_execution_contract import ScriptClient, WriteCounter, turns


@pytest.fixture
def factory(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    async def make(script=None, *, root=None, persistent=True, memory=False, mode=PermissionMode.DEFAULT):
        client = ScriptClient(script if script is not None else [[TextDelta("done"), StreamEnd("end_turn")]])
        client.closed = 0
        async def close():
            client.closed += 1
        client.aclose = close
        monkeypatch.setattr("likecc.client.create_client", lambda _: client)
        config = AppConfig(providers=[ProviderConfig("fake", "anthropic", "http://unused.invalid", "fake", api_key="fake")])
        runtime = Runtime(config=config, work_dir=root or tmp_path / "project", permission_mode=mode)
        await runtime.initialize(config.providers[0])
        tool = WriteCounter()
        runtime.registry.register(tool)
        service = SessionService(runtime, persistent=persistent, memory=memory)
        return runtime, service, tool
    return make


def read_records(service):
    path = Path(service.runtime.work_dir) / ".likecc/sessions" / f"{service.session.session_id}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.mark.asyncio
async def test_close_retries_failed_session_and_shares_concurrent_cleanup(factory, monkeypatch):
    from likecc.service import _session_owners
    runtime, service, _ = await factory()
    session = service.session
    original = session.close
    attempts = []

    def transient_close():
        attempts.append(True)
        if len(attempts) == 1:
            raise OSError("temporary flush failure")
        original()

    monkeypatch.setattr(session, "close", transient_close)
    try:
        results = await asyncio.gather(service.aclose(), service.aclose(), return_exceptions=True)
        assert all(isinstance(r, OSError) for r in results)
        assert len(attempts) == 1 and not session._file.closed
        assert _session_owners[(runtime.work_dir, session.session_id)] is service
        await asyncio.gather(service.aclose(), service.aclose())
        assert len(attempts) == 2 and session._file.closed
        assert (runtime.work_dir, session.session_id) not in _session_owners
    finally:
        monkeypatch.setattr(session, "close", original)
        original()
        await runtime.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["allow", "deny"])
async def test_no_ui_execution_permission_persistence_and_repeated_resume(factory, decision):
    runtime, service, tool = await factory(turns())
    envelopes = []
    try:
        async with service.start("write once", interactive=True) as run:
            async for envelope in run.events():
                json.dumps(envelope.to_dict())
                envelopes.append(envelope)
                event = envelope.event
                if isinstance(event, PermissionRequest):
                    assert run.reply(run.run_id, event.request_id, decision)
            assert await run.result() == "final"
        assert tool.calls == int(decision == "allow")
        assert len({e.run_id for e in envelopes}) == 1
        assert {e.session_id for e in envelopes} == {service.session.session_id}
        assert envelopes[-1].event.status == run.status == "completed"
        records = read_records(service)
        assert [r["content"] for r in records if r["type"] == "user"].count("write once") == 1
        assert [r["content"]["status"] for r in records if r["type"] == "run_state"] == ["running", "completed"]
        original = [(m.role, m.content, m.tool_uses, m.tool_results) for m in service.conversation.history if not m.transient]
        sid = service.session.session_id
        runtime.registry.mark_discovered("WriteCounter")
        runtime.agent.active_skills["previous-session"] = "old instructions"
        previous_results = runtime.agent.session_dir
        service.resume(sid)
        assert not runtime.registry.is_discovered("WriteCounter")
        assert not runtime.agent.active_skills
        assert runtime.agent.session_dir != previous_results
        assert [(m.role, m.content, m.tool_uses, m.tool_results) for m in service.conversation.history] == original
        assert read_records(service) == records
        service.resume(sid)
        assert [(m.role, m.content, m.tool_uses, m.tool_results) for m in service.conversation.history] == original
    finally:
        await runtime.aclose()
    assert service.session._file.closed
    assert runtime.client.closed == 1


@pytest.mark.asyncio
async def test_permission_cancel_emits_terminal_and_repairs_tool_chain(factory):
    runtime, service, tool = await factory(turns())
    try:
        run = service.start("cancel write", interactive=True)
        seen = []
        with pytest.raises(asyncio.CancelledError):
            async with run:
                async for envelope in run.events():
                    seen.append(envelope.event)
                    if isinstance(envelope.event, PermissionRequest):
                        request = envelope.event
                        await run.cancel()
        assert seen[-1].status == run.status == "cancelled"
        assert not run.reply(run.run_id, request.request_id, "allow")
        assert not tool.calls
        assert run.interaction.pending_count == 0
        sid = service.session.session_id
        service.resume(sid)
        results = [r for m in service.conversation.history for r in m.tool_results]
        assert len(results) == 1 and results[0].is_error
        assert "outcome unknown" in results[0].content
        assert results[0].tool_use_id == "write"
        assert [r["content"]["status"] for r in read_records(service) if r["type"] == "run_state"] == ["running", "cancelled"]
    finally:
        await runtime.aclose()
        await runtime.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["model", "tool", "before_start"])
async def test_service_cancel_and_close_preserve_cancellation(factory, phase):
    runtime, service, tool = await factory(turns(), mode=PermissionMode.BYPASS)
    entered, finalized = asyncio.Event(), asyncio.Event()
    async def blocked(*args, **kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            finalized.set()
    async def model(*args, **kwargs):
        await blocked()
        yield TextDelta("never")
    if phase == "model":
        runtime.client.stream = model
    elif phase == "tool":
        tool.execute = blocked
    run = service.start("cancel")
    if phase != "before_start":
        await asyncio.wait_for(entered.wait(), 2)
    if phase == "before_start":
        await run.cancel()
    else:
        await asyncio.wait_for(run.cancel(), 2)
    with pytest.raises(asyncio.CancelledError):
        await run.result()
    if phase != "before_start":
        assert finalized.is_set()
    assert run.status == "cancelled"
    await runtime.aclose()
    await runtime.aclose()
    assert runtime.client.closed == 1


@pytest.mark.asyncio
async def test_early_consumer_close_and_overlapping_requests(factory):
    runtime, service, tool = await factory(turns())
    try:
        async with service.start("write", interactive=True) as run:
            with pytest.raises(RuntimeError, match="active run"):
                service.start("overlap")
            with pytest.raises(RuntimeError, match="active run"):
                service.new_session()
            async with aclosing(run.events()) as events:
                async for envelope in events:
                    if isinstance(envelope.event, PermissionRequest):
                        break
        assert run.status == "cancelled"
        assert service.active_run is None
        assert not tool.calls
        assert await service.run_to_completion("continue") == "final"
    finally:
        await runtime.aclose()


@pytest.mark.asyncio
async def test_separate_services_and_exclusive_session_lease(factory):
    a, sa, _ = await factory()
    b, sb, _ = await factory()
    try:
        with pytest.raises(RuntimeError, match="another service"):
            sb.resume(sa.session.session_id)
        with pytest.raises(RuntimeError, match="already has"):
            SessionService(a)
        await sa.run_to_completion("only-a")
        assert not sb.conversation.history
        a.registry.mark_discovered("ToolSearch")
        assert not b.registry.is_discovered("ToolSearch")
        assert sa.session.session_id != sb.session.session_id
        await sa.aclose()
        assert sb.resume(sa.session.session_id)
    finally:
        await a.aclose()
        await b.aclose()


@pytest.mark.asyncio
async def test_tool_failure_is_recoverable_but_model_error_and_limit_are_not(factory):
    runtime, service, tool = await factory(turns(), mode=PermissionMode.BYPASS)
    async def fail(params):
        raise ValueError("broken tool")
    tool.execute = fail
    try:
        assert await service.run_to_completion("recover") == "final"
        assert any(r.is_error and "broken tool" in r.content for m in service.conversation.history for r in m.tool_results)
        async def fail_model(*args, **kwargs):
            raise ValueError("original model failure")
            yield
        runtime.client.stream = fail_model
        with pytest.raises(ValueError, match="original model failure"):
            await service.run_to_completion("fail")
        assert service.last_run.status == "failed"
        runtime.agent.max_iterations = 0
        with pytest.raises(RuntimeError, match="limit"):
            await service.run_to_completion("limit")
        assert service.last_run.status == "limit"
    finally:
        await runtime.aclose()


@pytest.mark.asyncio
async def test_recall_is_ephemeral_and_input_saved_once(factory, monkeypatch):
    runtime, service, _ = await factory([[TextDelta("a"), StreamEnd("end_turn")], [TextDelta("b"), StreamEnd("end_turn")]], memory=True)
    async def recall(query):
        return "recalled-marker"
    monkeypatch.setattr(service, "recall", recall)
    try:
        await service.run_to_completion("one")
        await service.run_to_completion("two")
        assert sum("recalled-marker" in m.content for m in service.conversation.history) == 1
        assert "recalled-marker" not in json.dumps(read_records(service))
        service.resume(service.session.session_id)
        assert [m.content for m in service.conversation.history if m.role == "user"] == ["one", "two"]
    finally:
        await runtime.aclose()


@pytest.mark.asyncio
async def test_optional_extensions_off_and_mcp_failure_observable(factory):
    runtime, service, _ = await factory()
    class FailingMCP:
        def __init__(self):
            self.closed = 0
        def load_configs(self, configs):
            pass
        async def register_all_tools(self, registry):
            self.owner = asyncio.current_task()
            raise RuntimeError("fake connect failure")
        async def shutdown(self):
            assert asyncio.current_task() is self.owner
            self.closed += 1
    manager = FailingMCP()
    runtime.config.mcp_servers = [MCPServerConfig("test", command="unused")]
    extensions = RuntimeExtensions(runtime, ExtensionOptions(mcp=True), mcp_factory=lambda: manager)
    try:
        await extensions.initialize()
        async with service.start("hello") as run:
            events = [e.event async for e in run.events()]
        assert any(isinstance(e, ErrorEvent) and "fake connect failure" in e.message and not e.fatal for e in events)
        assert run.status == "completed"
        assert extensions.skill_loader is None
        assert runtime.registry.get("AskUserQuestion") is None
    finally:
        await runtime.aclose()
    assert manager.closed == 1


@pytest.mark.asyncio
async def test_explicit_hook_and_skill_extensions_no_duplicate_lifecycle(factory):
    runtime, service, _ = await factory()
    lifecycle = ["startup", "session_start", "turn_start", "pre_send", "post_receive", "turn_end", "session_end", "shutdown"]
    runtime.config.raw_hooks = [{"id": event, "event": event, "action": {"type": "prompt", "message": event}} for event in lifecycle]
    ext = RuntimeExtensions(runtime, ExtensionOptions(skills=True, hooks=True, interactive_tools=True))
    try:
        await ext.initialize()
        assert ext.skill_loader is not None
        assert runtime.registry.get("LoadSkill") is ext.load_skill
        assert runtime.registry.get("AskUserQuestion") is not None
        assert runtime.agent.hook_engine is ext.hook_engine
        async with service.start("hello") as run:
            events = [e.event async for e in run.events()]
        from likecc.agent import HookEvent
        observed = [e.event for e in events if isinstance(e, HookEvent)]
    finally:
        await runtime.aclose()
        await ext.aclose()
    observed.extend(note.event for note in ext.hook_engine.drain_notifications())
    assert observed == lifecycle


@pytest.mark.asyncio
async def test_extension_init_failure_closes_session_and_core(factory, monkeypatch):
    runtime, service, _ = await factory()
    def fail(self):
        raise ValueError("bad skill definitions")
    monkeypatch.setattr("likecc.skills.loader.SkillLoader.load_all", fail)
    ext = RuntimeExtensions(runtime, ExtensionOptions(skills=True))
    with pytest.raises(ValueError, match="bad skill definitions"):
        await ext.initialize()
    assert runtime.client.closed == 1
    assert service.session._file.closed
    await runtime.aclose()
    assert runtime.client.closed == 1


@pytest.mark.asyncio
async def test_memory_extraction_is_owned_and_reaped_before_client_close(factory, monkeypatch):
    runtime, service, _ = await factory([[TextDelta("ok"), StreamEnd("end_turn")] for _ in range(5)], memory=True)
    entered, finalized = asyncio.Event(), asyncio.Event()
    async def recall(query):
        return ""
    async def extract(*args):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            assert runtime.client.closed == 0
            finalized.set()
    monkeypatch.setattr(service, "recall", recall)
    monkeypatch.setattr(service.memory_manager, "extract", extract)
    for i in range(5):
        await service.run_to_completion(str(i))
    await asyncio.wait_for(entered.wait(), 2)
    await runtime.aclose()
    assert finalized.is_set() and runtime.client.closed == 1


@pytest.mark.asyncio
async def test_crash_tail_and_legacy_context_not_replayed_on_resume(factory):
    from likecc.conversation import Message, ToolUseBlock
    runtime, service, _ = await factory([[TextDelta("a"), StreamEnd("end_turn", input_tokens=2, output_tokens=3)], [TextDelta("b"), StreamEnd("end_turn", input_tokens=4, output_tokens=5)]])
    try:
        await service.run_to_completion("old input")
        sid = service.session.session_id
        service.session.append(Message("user", "Current working directory: /old\nOperating system: Linux\nCurrent time: old"))
        service.session.append(Message("assistant", "partial", tool_uses=[ToolUseBlock("orphan", "WriteCounter", {})]))
        service.new_session()
        service.resume(sid)
        assert not any(m.tool_uses or "Current working directory" in m.content for m in service.conversation.history)
        assert await service.run_to_completion("new input") == "b"
        assert service.session.meta.total_tokens == 14
        service.resume(sid)
        assert [m.content for m in service.conversation.history if m.role == "user"] == ["old input", "new input"]
    finally:
        await runtime.aclose()


@pytest.mark.asyncio
async def test_cancel_one_run_does_not_stop_independent_or_background_work(factory):
    a, sa, _ = await factory(turns())
    b, sb, _ = await factory()
    child_started, release = asyncio.Event(), asyncio.Event()
    class Child:
        team_name = ""
        total_input_tokens = total_output_tokens = 0
        async def run_to_completion(self, *args, **kwargs):
            child_started.set()
            await release.wait()
            return "child done"
    task_id = a.task_manager.launch(Child(), "independent background")
    try:
        await asyncio.wait_for(child_started.wait(), 2)
        async with sa.start("write", interactive=True) as run:
            async with aclosing(run.events()) as events:
                async for envelope in events:
                    if isinstance(envelope.event, PermissionRequest):
                        break
        assert run.status == "cancelled"
        assert a.task_manager.get(task_id).status == "running"
        assert await sb.run_to_completion("other session") == "done"
    finally:
        release.set()
        await a.aclose()
        await b.aclose()


@pytest.mark.asyncio
async def test_mcp_constructor_failure_does_not_hang_service(factory):
    runtime, service, _ = await factory()
    runtime.config.mcp_servers = [MCPServerConfig("test", command="unused")]
    def fail():
        raise RuntimeError("constructor failed")
    ext = RuntimeExtensions(runtime, ExtensionOptions(mcp=True), mcp_factory=fail)
    try:
        await ext.initialize()
        assert await asyncio.wait_for(service.run_to_completion("continue without MCP"), 2) == "done"
        assert any("constructor failed" in d for d in ext.diagnostics)
    finally:
        await runtime.aclose()


def test_offline_demo_runs_when_all_textual_imports_are_blocked():
    import subprocess
    import sys
    script = '''
import sys, runpy
class NoTextual:
    def find_spec(self, fullname, *args):
        if fullname == "textual" or fullname.startswith("textual."):
            raise AssertionError("Service imported Textual")
sys.meta_path.insert(0, NoTextual())
from likecc.extensions import RuntimeExtensions
sys.argv = ["deskmate_session", "--decision", "allow"]
runpy.run_module("examples.deskmate_session", run_name="__main__")
'''
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert "repeated_resume_unchanged=True" in result.stdout
