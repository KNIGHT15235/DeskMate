"""R3.1: actual controller/service runs, no SDK stubs or real model calls."""
import asyncio
from pathlib import Path
import threading

import pytest

from likecc.client import LLMClient
from likecc.desktop.controller import DesktopController, DesktopOptions
from likecc.runtime import Runtime
from likecc.tools.base import StreamEnd, TextDelta, ToolCallComplete
from test_desktop_controller import close, command, wait


@pytest.mark.parametrize("kind", ["permission", "question"])
def test_timeout_returns_to_running_while_next_model_call_is_blocked(kind):
    next_call, finalized = threading.Event(), threading.Event()

    class Client(LLMClient):
        def __init__(self):
            self.calls = 0

        async def stream(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                if kind == "permission":
                    yield ToolCallComplete("waiting-tool", "WriteFile", {"file_path": "denied.txt", "content": "never"})
                else:
                    yield ToolCallComplete("waiting-tool", "AskUserQuestion", {"questions": [
                        {"type": "text", "name": "answer", "message": "Wait for timeout"}]})
                yield StreamEnd("tool_use")
            elif self.calls == 2:
                next_call.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    finalized.set()
            else:
                yield TextDelta("next request completed")
                yield StreamEnd("end_turn")

    class TestRuntime(Runtime):
        def __init__(self, **kwargs):
            kwargs["client_factory"] = lambda _: Client()
            super().__init__(**kwargs)

    c = DesktopController(DesktopOptions(demo=True, permission_timeout=0.15), runtime_factory=TestRuntime)
    try:
        initial = wait(c, lambda s: s["state"] == "idle")
        command(c, "send", text="let the request expire")
        request = wait(c, lambda s: bool(s["pending"]))["pending"][0]
        assert next_call.wait(3)
        result = wait(c, lambda s: any(r["kind"] == "tool_error" for r in s["rows"]))
        assert not result["pending"]
        assert result["state"] == "running"
        assert not (Path(initial["workspace"]) / "denied.txt").exists()
        assert not command(c, "reply", session_id=request["session_id"], run_id=request["run_id"],
                           request_id=request["request_id"], value="allow" if kind == "permission" else {"answer": "late"})["accepted"]
        assert command(c, "cancel")["accepted"]
        assert finalized.wait(3)
        wait(c, lambda s: s["state"] == "idle" and s.get("last_status") == "cancelled")
        assert command(c, "send", text="another input")["accepted"]
        wait(c, lambda s: s["state"] == "idle" and s.get("last_status") == "completed")
    finally:
        close(c)


@pytest.mark.parametrize("state", ["waiting", "cancelling", "closing", "idle", "closed"])
def test_result_projection_keeps_unrelated_requests_and_protects_shutdown_states(state):
    """Inject wire events in the owner loop to cover late/interleaved delivery."""
    c = DesktopController(DesktopOptions(demo=True))
    done = threading.Event()
    observed, failures = {}, []
    try:
        wait(c, lambda s: s["state"] == "idle")
        command(c, "send", text="projection boundary")
        before = wait(c, lambda s: bool(s["pending"]))
        request = before["pending"][0]
        def probe():
            try:
                event = {"type": "ToolResultEvent", "session_id": request["session_id"], "run_id": request["run_id"],
                         "data": {"tool_id": request["tool_id"], "output": "synthetic late result", "is_error": True}}
                c._event({**event, "run_id": "foreign-run"})
                c._event({**event, "session_id": "foreign-session"})
                c._event({**event, "data": {**event["data"], "tool_id": "unrelated-tool"}})
                observed["unrelated"] = c.snapshot()
                # Two requests are defensive projection coverage, not a claim
                # that the current Agent runs multiple interactive tools at once.
                second = {**request, "request_id": "second", "tool_id": "second-tool"}
                c._set(state=state, pending=[request, second])
                c._event(event)
                observed["one_left"] = c.snapshot()
                c._event({**event, "data": {**event["data"], "tool_id": "second-tool"}})
                observed["finished"] = c.snapshot()
            except Exception as exc:
                failures.append(exc)
            finally:
                done.set()
        c._loop.call_soon_threadsafe(probe)
        assert done.wait(3)
        assert not failures
        assert observed["unrelated"]["pending"] == before["pending"]
        assert observed["unrelated"]["state"] == "waiting"
        assert len(observed["one_left"]["pending"]) == 1
        assert observed["one_left"]["state"] == state
        assert not observed["finished"]["pending"]
        assert observed["finished"]["state"] == ("running" if state == "waiting" else state)
    finally:
        close(c)


@pytest.mark.parametrize("finish", ["cancel", "close"])
def test_timeout_result_during_shutdown_does_not_restore_running(finish):
    """Hold actual model cancellation cleanup, then deliver a delayed tool result."""
    model_entered, cleanup_entered, cleanup_released = (threading.Event() for _ in range(3))
    release = []
    class Client(LLMClient):
        def __init__(self):
            self.calls = 0
        async def stream(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                yield ToolCallComplete("expired", "WriteFile", {"file_path": "never.txt", "content": "never"})
                yield StreamEnd("tool_use")
            else:
                gate = asyncio.Event()
                release.append(gate)
                model_entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cleanup_entered.set()
                    await gate.wait()
                    cleanup_released.set()
    class TestRuntime(Runtime):
        def __init__(self, **kwargs):
            kwargs["client_factory"] = lambda _: Client()
            super().__init__(**kwargs)
    c = DesktopController(DesktopOptions(demo=True, permission_timeout=0.1), runtime_factory=TestRuntime)
    try:
        wait(c, lambda s: s["state"] == "idle")
        command(c, "send", text="expire then stop")
        initial = wait(c, lambda s: bool(s["pending"]))
        assert model_entered.wait(3)
        c.submit(finish)
        assert cleanup_entered.wait(3)
        projected = threading.Event()
        def delayed():
            c._event({"type": "ToolResultEvent", "session_id": initial["session_id"], "run_id": initial["run_id"],
                      "data": {"tool_id": "expired", "output": "late timeout result", "is_error": True}})
            projected.set()
        c._loop.call_soon_threadsafe(delayed)
        assert projected.wait(3)
        assert c.snapshot()["state"] == ("cancelling" if finish == "cancel" else "closing")
    finally:
        if release and c.is_alive:
            c._loop.call_soon_threadsafe(release[0].set)
        try:
            if release and cleanup_entered.is_set():
                assert cleanup_released.wait(3)
        finally:
            close(c)
