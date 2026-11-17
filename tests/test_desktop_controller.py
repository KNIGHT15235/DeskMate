import asyncio
from pathlib import Path
import threading
import time

import pytest

from likecc.desktop.controller import DesktopController, DesktopOptions, MAX_ROWS, MAX_DISPLAY_CHARS
from likecc.runtime import Runtime


def wait(controller, predicate, timeout=6):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        snapshot = controller.snapshot()
        if predicate(snapshot):
            return snapshot
        time.sleep(0.005)
    raise AssertionError(controller.snapshot())


def close(controller):
    controller.submit("close")
    end = time.monotonic() + 6
    while controller.is_alive and time.monotonic() < end:
        time.sleep(0.005)
    assert not controller.is_alive
    assert controller.snapshot()["state"] == "closed"


def command(controller, name, **kwargs):
    cid = controller.submit(name, **kwargs)
    return wait(controller, lambda s: s["command"] and s["command"]["id"] == cid)["command"]


def reply(controller, value):
    pending = wait(controller, lambda s: bool(s["pending"]))["pending"][0]
    return command(controller, "reply", session_id=pending["session_id"], run_id=pending["run_id"],
                   request_id=pending["request_id"], value=value)


@pytest.mark.parametrize("allow", [True, False])
def test_worker_owns_resources_and_demo_uses_real_service(allow, monkeypatch):
    observations = []
    class ObservedRuntime(Runtime):
        def __init__(self, **kwargs):
            observations.append(("create", threading.get_ident(), id(asyncio.get_running_loop())))
            super().__init__(**kwargs)
        async def initialize(self, *args, **kwargs):
            await super().initialize(*args, **kwargs)
            original_run = self.agent.run
            async def run(*args, **kwargs):
                observations.append(("run", threading.get_ident(), id(asyncio.get_running_loop())))
                interaction = kwargs["interaction"]
                original_reply = interaction.reply
                def observed_reply(*a, **kw):
                    observations.append(("reply", threading.get_ident(), id(asyncio.get_running_loop())))
                    return original_reply(*a, **kw)
                interaction.reply = observed_reply
                async for event in original_run(*args, **kwargs):
                    yield event
            self.agent.run = run
        async def _close(self):
            observations.append(("close", threading.get_ident(), id(asyncio.get_running_loop())))
            await super()._close()
    def no_home(cls):
        raise AssertionError("demo must not read the real home")
    monkeypatch.setattr(Path, "home", classmethod(no_home))
    c = DesktopController(DesktopOptions(demo=True), runtime_factory=ObservedRuntime)
    try:
        start = wait(c, lambda s: s["state"] == "idle")
        assert start["demo"]
        workspace = Path(start["workspace"])
        assert command(c, "send", text="demo")["accepted"]
        wait(c, lambda s: s["state"] == "waiting")
        assert not command(c, "new")["accepted"]
        assert reply(c, "allow" if allow else "deny")["accepted"]
        wait(c, lambda s: s["pending"] and s["pending"][0]["kind"] == "UserInputRequest")
        assert (workspace / "demo.txt").exists() == allow
        assert reply(c, {"next": "完成", "note": "safe <img>"})["accepted"]
        final = wait(c, lambda s: s["state"] == "idle")
        assert final["last_status"] == "completed"
        saved = list(final["rows"])
        sid = final["session_id"]
        assert command(c, "new")["accepted"]
        assert command(c, "resume", session_id=sid)["accepted"]
        restored = c.snapshot()
        assert sum(r["kind"] == "user" and r["text"] == "demo" for r in restored["rows"]) == 1
        assert any("safe <img>" in r["text"] for r in restored["rows"])
        assert len([x for x in observations if x[0] == "run"]) == 1
        restored["rows"].clear()
        assert c.snapshot()["rows"]  # detached snapshot
    finally:
        close(c)
    assert {o[1] for o in observations} == {start["worker_thread"]}
    assert start["worker_thread"] != threading.get_ident()
    assert len({o[2] for o in observations}) == 1
    assert not workspace.exists()


def test_permission_cancel_late_reply_rejected_and_next_run_works():
    c = DesktopController(DesktopOptions(demo=True))
    try:
        wait(c, lambda s: s["state"] == "idle")
        command(c, "send", text="first")
        pending = wait(c, lambda s: s["pending"])["pending"][0]
        assert command(c, "cancel")["accepted"]
        assert wait(c, lambda s: s["state"] == "idle")["last_status"] == "cancelled"
        command(c, "send", text="second")
        wait(c, lambda s: s["state"] == "waiting")
        assert not command(c, "reply", session_id=pending["session_id"], run_id=pending["run_id"], request_id=pending["request_id"], value="allow")["accepted"]
        assert reply(c, "deny")["accepted"]
        wait(c, lambda s: s["pending"] and s["pending"][0]["kind"] == "UserInputRequest")
    finally:
        close(c)


def test_config_error_recovery_and_repeat_exit(tmp_path):
    c = DesktopController(DesktopOptions(work_dir=str(tmp_path / "missing")))
    try:
        wait(c, lambda s: s["state"] == "error")
        assert command(c, "demo")["accepted"]
        command(c, "send", text="wait permission")
        wait(c, lambda s: s["state"] == "waiting")
    finally:
        c.submit("close")
        close(c)


def test_close_immediately_during_startup():
    c = DesktopController(DesktopOptions(demo=True))
    close(c)


def test_explicit_workspace_config_keeps_priority_without_chdir(tmp_path, monkeypatch):
    from likecc.config import load_config
    home, project, other = (tmp_path / name for name in ("home", "project", "other"))
    for root, model in ((home, "user"), (project, "project")):
        (root / ".likecc").mkdir(parents=True)
        (root / ".likecc/config.yaml").write_text(f"providers:\n  - name: test\n    protocol: openai\n    base_url: http://unused.invalid\n    model: {model}\n")
    (project / ".likecc/config.local.yaml").write_text("providers:\n  - name: test\n    protocol: openai\n    base_url: http://unused.invalid\n    model: local\n")
    other.mkdir()
    monkeypatch.chdir(other)
    assert load_config(work_dir=project, user_home=home).providers[0].model == "local"
    assert Path.cwd() == other


def test_high_frequency_display_is_bounded_and_preserves_tool_request():
    from likecc.client import LLMClient
    from likecc.tools.base import TextDelta, StreamEnd, ToolCallComplete
    class BurstClient(LLMClient):
        def __init__(self):
            self.calls = 0
        async def stream(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                for i in range(20000):
                    yield TextDelta("0123456789")
                    if i % 64 == 0:
                        await asyncio.sleep(0)
                yield ToolCallComplete("burst", "WriteFile", {"file_path": "burst.txt", "content": "once"})
                yield StreamEnd("tool_use")
            else:
                yield TextDelta("final answer")
                yield StreamEnd("end_turn")
    class BurstRuntime(Runtime):
        def __init__(self, **kwargs):
            kwargs["client_factory"] = lambda _: BurstClient()
            super().__init__(**kwargs)
    c = DesktopController(DesktopOptions(demo=True), runtime_factory=BurstRuntime)
    try:
        wait(c, lambda s: s["state"] == "idle")
        command(c, "send", text="burst")
        pending = wait(c, lambda s: bool(s["pending"]), timeout=15)
        assert "展示截断" in pending["rows"][1]["text"]
        assert len(pending["rows"]) <= MAX_ROWS
        assert sum(len(r["text"]) for r in pending["rows"]) <= MAX_DISPLAY_CHARS
        assert any(r.get("tool_id") == "burst" for r in pending["rows"])
        assert reply(c, "deny")["accepted"]
        final = wait(c, lambda s: s["state"] == "idle")
        assert [r["kind"] for r in final["rows"]][-3:] == ["tool_error", "assistant", "status"]
    finally:
        close(c)


@pytest.mark.parametrize("phase", ["initialize", "model"])
def test_exit_cancels_owned_coroutines_in_worker_thread(phase):
    started, finalized = threading.Event(), threading.Event()
    owner = []
    class BlockedRuntime(Runtime):
        async def initialize(self, *args, **kwargs):
            if phase == "initialize":
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    owner.append(threading.get_ident())
                    finalized.set()
            else:
                await super().initialize(*args, **kwargs)
                async def model(*args, **kwargs):
                    started.set()
                    try:
                        await asyncio.Event().wait()
                        yield
                    finally:
                        owner.append(threading.get_ident())
                        finalized.set()
                self.client.stream = model
    c = DesktopController(DesktopOptions(demo=True), runtime_factory=BlockedRuntime)
    try:
        if phase == "model":
            wait(c, lambda s: s["state"] == "idle")
            command(c, "send", text="block")
        assert started.wait(3)
    finally:
        close(c)
    assert finalized.is_set()
    assert owner == [c.snapshot()["worker_thread"]]


def test_core_and_cli_without_qt_and_missing_desktop_has_install_hint():
    import subprocess, sys
    prelude = '''
import sys,runpy
class NoQt:
    def find_spec(self, fullname, *args):
        if fullname == 'PySide6' or fullname.startswith('PySide6.'):
            raise ModuleNotFoundError('desktop extra absent', name='PySide6')
sys.meta_path.insert(0,NoQt())
'''
    for module, args, expected in (("likecc", ["--help"], 0), ("likecc.desktop", ["--help"], 0), ("likecc.desktop", ["--demo"], 2)):
        script = prelude + f"\nsys.argv = [{module!r}] + {args!r}\nrunpy.run_module({module!r}, run_name='__main__')"
        result = subprocess.run([sys.executable, "-c", script], text=True, capture_output=True, timeout=20)
        assert result.returncode == expected, result.stderr
        if expected == 2:
            assert "--extra desktop" in result.stderr


def test_model_failure_then_next_request_and_permission_timeout():
    from likecc.client import LLMClient
    from likecc.tools.base import TextDelta, StreamEnd, ToolCallComplete
    class FailingOnce(LLMClient):
        def __init__(self):
            self.calls = 0
        async def stream(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise ValueError("constructed model failure")
            if self.calls == 2:
                yield ToolCallComplete("timeout", "WriteFile", {"file_path": "timeout.txt", "content": "never"})
                yield StreamEnd("tool_use")
            else:
                yield TextDelta("recovered")
                yield StreamEnd("end_turn")
    class TestRuntime(Runtime):
        def __init__(self, **kwargs):
            kwargs["client_factory"] = lambda _: FailingOnce()
            super().__init__(**kwargs)
    c = DesktopController(DesktopOptions(demo=True, permission_timeout=0.15), runtime_factory=TestRuntime)
    try:
        initial = wait(c, lambda s: s["state"] == "idle")
        command(c, "send", text="fail")
        failed = wait(c, lambda s: s.get("last_status") == "failed" and s["state"] == "idle")
        assert any("constructed model failure" in r["text"] for r in failed["rows"])
        command(c, "send", text="timeout permission")
        request = wait(c, lambda s: bool(s["pending"]))["pending"][0]
        result = wait(c, lambda s: s.get("last_status") == "completed" and s["state"] == "idle")
        assert not (Path(initial["workspace"]) / "timeout.txt").exists()
        assert not command(c, "reply", session_id=request["session_id"], run_id=request["run_id"], request_id=request["request_id"], value="allow")["accepted"]
        assert any(r["kind"] == "tool_error" for r in result["rows"])
    finally:
        close(c)


def test_unsupported_question_cancels_instead_of_hanging():
    from likecc.client import LLMClient
    from likecc.tools.base import ToolCallComplete, StreamEnd
    class UnsupportedClient(LLMClient):
        async def stream(self, *args, **kwargs):
            yield ToolCallComplete("unsupported", "AskUserQuestion", {"questions": [
                {"type": "unknown", "name": "q", "message": "unsupported"}]})
            yield StreamEnd("tool_use")
    class TestRuntime(Runtime):
        def __init__(self, **kwargs):
            kwargs["client_factory"] = lambda _: UnsupportedClient()
            super().__init__(**kwargs)
    c = DesktopController(DesktopOptions(demo=True), runtime_factory=TestRuntime)
    try:
        wait(c, lambda s: s["state"] == "idle")
        command(c, "send", text="unknown")
        result = wait(c, lambda s: s.get("last_status") == "cancelled" and s["state"] == "idle")
        assert any("不支持的问题类型" in r["text"] for r in result["rows"])
        assert not result["pending"]
    finally:
        close(c)


def test_exit_during_tool_wait_reaps_tool_in_its_owner_loop(monkeypatch):
    started, finished = threading.Event(), threading.Event()
    threads = []
    async def wait_tool(self, params):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            threads.append(threading.get_ident())
            finished.set()
    monkeypatch.setattr("likecc.desktop.demo.DemoWait.execute", wait_tool)
    c = DesktopController(DesktopOptions(demo=True))
    try:
        wait(c, lambda s: s["state"] == "idle")
        command(c, "send", text="wait")
        reply(c, "deny")
        wait(c, lambda s: s["pending"] and s["pending"][0]["kind"] == "UserInputRequest")
        reply(c, {"next": "等待取消", "note": ""})
        assert started.wait(3)
    finally:
        close(c)
    assert finished.is_set()
    assert threads == [c.snapshot()["worker_thread"]]
