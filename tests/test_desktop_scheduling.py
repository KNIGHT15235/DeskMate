"""R5 acceptance through the real controller/service/Agent, clock and SQLite."""
import asyncio
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from likecc.client import LLMClient
from likecc.config import AppConfig, ProviderConfig
from likecc.desktop.controller import DesktopController, DesktopOptions
from likecc.runtime import Runtime
from likecc.tools.base import TextDelta, ToolCallComplete, StreamEnd
from test_desktop_controller import wait, command, close, reply
from test_scheduling import Clock, reminder


@pytest.fixture
def desktop(tmp_path, monkeypatch):
    provider = ProviderConfig("offline-r5", "anthropic", "http://unused.invalid", "fake", api_key="offline", context_window=32000)
    monkeypatch.setattr("likecc.desktop.controller.load_config", lambda **kw: AppConfig([provider]))
    (tmp_path / "project_notes.md").write_text("# Project\nRead then verify.\n", encoding="utf-8")
    clients = []
    behavior = {"mode": "normal"}

    class Client(LLMClient):
        def __init__(self):
            self.calls = 0
            self.tools = []
            clients.append(self)

        async def stream(self, conversation, **kwargs):
            prompt = next(m.content for m in conversation.history if m.role == "user" and not m.transient)
            self.calls += 1
            if prompt == "hold foreground":
                await asyncio.Event().wait()
            if "本次已确认范围" not in prompt or behavior["mode"] == "text_only":
                yield TextDelta("offline answer")
                yield StreamEnd("end_turn")
                return
            calls = [("ReadFile", {"file_path": "project_notes.md"}),
                ("AskUserQuestion", {"questions": [{"type": "text", "name": "note", "message": "确认本次补充说明"}]}),
                ("WriteFile", {"file_path": "outputs/weekly-summary.md", "content": "# Weekly\nRead then verify [S1]."}),
                ("ReadFile", {"file_path": "outputs/weekly-summary.md"})]
            if behavior["mode"] == "expand":
                calls = [("WriteFile", {"file_path": "extra.md", "content": "no"}),
                    ("ReadFile", {"file_path": "unconfirmed.md"}),
                    ("FetchWebPage", {"url": "https://injected.example/"})]
            if self.calls <= len(calls):
                name, args = calls[self.calls-1]
                if behavior["mode"] == "readback_fail" and name == "ReadFile" and self.calls == 4:
                    (tmp_path / "outputs/weekly-summary.md").write_text("changed externally", encoding="utf-8")
                self.tools.append(name)
                yield ToolCallComplete(f"r5-{self.calls}", name, args)
                yield StreamEnd("tool_use")
            else:
                yield TextDelta("only tool evidence proves the result")
                yield StreamEnd("end_turn")

    class OfflineRuntime(Runtime):
        def __init__(self, **kwargs):
            kwargs.update(client_factory=lambda _: Client(), user_home=tmp_path / "user")
            super().__init__(**kwargs)

    clock = Clock()
    controllers = []

    def make():
        c = DesktopController(DesktopOptions(work_dir=str(tmp_path)), runtime_factory=OfflineRuntime, clock=clock)
        controllers.append(c)
        wait(c, lambda s: s["state"] in {"idle", "error"})
        return c

    yield make, clock, clients, behavior
    for c in controllers:
        if c.is_alive:
            close(c)


def arrange(c, spec, **kwargs):
    assert command(c, "schedule_preview", spec=asdict(spec), **kwargs)["accepted"]
    draft = c.snapshot()["schedule_draft"]
    assert command(c, "schedule_confirm", token=draft["token"])["accepted"]
    assert not command(c, "schedule_confirm", token=draft["token"])["accepted"]
    return c.snapshot()["tasks"][0]["id"]


def execute_spec(clock, **kwargs):
    return replace(reminder(clock, repeat="weekly"), kind="execute", files=["project_notes.md"],
        outputs=["outputs/weekly-summary.md"], **kwargs)


def test_reminder_create_edit_close_reopen_complete_no_model(desktop):
    make, clock, clients, _ = desktop
    c = make()
    task = arrange(c, reminder(clock))
    arrange(c, replace(reminder(clock), content="修改后提醒"), task_id=task, revision=1)
    close(c)
    clock.advance(hours=3)
    reopened = make()
    row, = wait(reopened, lambda s: len(s["executions"]) == 1)["executions"]
    assert row["status"] == "pending" and "逾期" in row["reason"]
    assert row["snapshot"]["content"] == "修改后提醒"
    command(reopened, "schedule_scan")
    assert len(reopened.snapshot()["executions"]) == 1
    assert command(reopened, "schedule_complete", execution_id=row["id"])["accepted"]
    assert reopened.snapshot()["executions"][0]["status"] == "done"
    assert all(client.calls == 0 for client in clients)


@pytest.mark.parametrize("deny", [False, True])
def test_weekly_queues_then_permissions_evidence_and_preserved_chat(desktop, tmp_path, deny):
    make, clock, clients, _ = desktop
    c = make()
    arrange(c, execute_spec(clock, model_policy="allow"))
    assert command(c, "send", text="hold foreground")["accepted"]
    foreground_id = c.snapshot()["session_id"]
    clock.advance(hours=2)
    command(c, "schedule_scan")
    queued, = c.snapshot()["executions"]
    assert queued["status"] == "queued" and "等待当前" in queued["reason"]
    assert len(clients) == 1
    command(c, "cancel")
    wait(c, lambda s: s["pending"] and s["pending"][0]["kind"] == "UserInputRequest")
    assert c.snapshot()["session_id"] != foreground_id
    assert reply(c, {"note": "continue"})["accepted"]
    request = wait(c, lambda s: s["pending"] and s["pending"][0]["kind"] == "PermissionRequest")["pending"][0]
    assert request["tool_name"] == "WriteFile"
    assert not (tmp_path / "outputs/weekly-summary.md").exists()
    assert reply(c, "deny" if deny else "allow")["accepted"]
    final = wait(c, lambda s: s["state"] == "idle" and s["executions"][0]["status"] == "completed")
    row, = final["executions"]
    assert final["session_id"] == foreground_id and any(r["text"] == "hold foreground" for r in final["rows"])
    assert row["session_id"] != foreground_id and row["run_id"]
    if deny:
        assert not row["evidence"]["artifacts"]
        assert "用户拒绝" in str(row["evidence"]["tool_errors"])
        assert not (tmp_path / "outputs/weekly-summary.md").exists()
    else:
        assert row["evidence"]["artifacts"] == [{"path": "outputs/weekly-summary.md", "status": "verified"}]
        assert row["evidence"]["digests"]["outputs/weekly-summary.md"]
        assert "[S1]" in (tmp_path / "outputs/weekly-summary.md").read_text(encoding="utf-8")
    calls = sum(client.calls for client in clients)
    close(c)
    restored = make()
    assert restored.snapshot()["executions"][0]["evidence"] == row["evidence"]
    assert sum(client.calls for client in clients) == calls


@pytest.mark.parametrize("mode", ["text_only", "readback_fail", "expand"])
def test_model_confirmation_and_truthful_outcomes(desktop, mode, tmp_path):
    make, clock, clients, behavior = desktop
    behavior["mode"] = mode
    c = make()
    arrange(c, execute_spec(clock))
    clock.advance(hours=2)
    command(c, "schedule_scan")
    row, = c.snapshot()["executions"]
    assert row["status"] == "awaiting_model" and len(clients) == 1 and clients[0].calls == 0
    command(c, "schedule_allow_model", execution_id=row["id"])
    command(c, "schedule_scan")
    if mode == "readback_fail":
        reply(c, {"note": "continue"})
        wait(c, lambda s: s["pending"] and s["pending"][0]["kind"] == "PermissionRequest")
        reply(c, "allow")
    final = wait(c, lambda s: s["state"] == "idle" and s["executions"][0]["status"] == "completed")
    evidence = final["executions"][0]["evidence"]
    if mode == "readback_fail":
        assert evidence["artifacts"][0]["status"] == "readback_failed"
    else:
        assert not evidence["artifacts"]
        assert not (tmp_path / "extra.md").exists()
    if mode == "expand":
        assert len(evidence["tool_errors"]) == 3
        assert all("范围" in e["output"] for e in evidence["tool_errors"])


def test_close_during_scheduled_permission_recovers_without_model_replay(desktop):
    make, clock, clients, _ = desktop
    c = make()
    arrange(c, execute_spec(clock, model_policy="allow"))
    clock.advance(hours=2)
    command(c, "schedule_scan")
    wait(c, lambda s: bool(s["pending"]))
    close(c)
    calls = sum(client.calls for client in clients)
    reopened = make()
    row, = reopened.snapshot()["executions"]
    assert row["status"] == "interrupted" and "核对" in row["reason"]
    command(reopened, "schedule_scan")
    assert sum(client.calls for client in clients) == calls
    assert not command(reopened, "schedule_retry", execution_id=row["id"])["accepted"]
    assert command(reopened, "schedule_retry", execution_id=row["id"], reviewed_execution_id=row["id"])["accepted"]
    assert len(reopened.snapshot()["executions"]) == 2


def test_cancel_during_scheduled_initialization_never_calls_model(desktop, monkeypatch):
    import threading
    make, clock, clients, _ = desktop
    c = make()
    task_id = arrange(c, execute_spec(clock, model_policy="allow"))
    entered, release = threading.Event(), threading.Event()
    original = Runtime.initialize

    async def blocked(self, *args, **kwargs):
        entered.set()
        while not release.is_set():
            await asyncio.sleep(0.005)
        await original(self, *args, **kwargs)

    monkeypatch.setattr(Runtime, "initialize", blocked)
    clock.advance(hours=2)
    c.submit("schedule_scan")
    try:
        assert entered.wait(3)
        assert command(c, "schedule_cancel", task_id=task_id)["accepted"]
    finally:
        release.set()
    final = wait(c, lambda s: s["state"] == "idle" and s["executions"][0]["status"] == "cancelled")
    assert not final["tasks"][0]["enabled"]
    assert all(client.calls == 0 for client in clients)


def test_terminal_database_failure_preserves_evidence_and_stops_dispatch(desktop, monkeypatch, tmp_path):
    from likecc.scheduling import ScheduleStore
    make, clock, clients, _ = desktop
    c = make()
    arrange(c, execute_spec(clock, model_policy="allow"))
    original = ScheduleStore.update

    def fail_terminal(self, execution_id, **values):
        if values.get("status") == "completed":
            raise OSError("injected terminal write failure")
        return original(self, execution_id, **values)

    monkeypatch.setattr(ScheduleStore, "update", fail_terminal)
    clock.advance(hours=2)
    command(c, "schedule_scan")
    reply(c, {"note": "continue"})
    wait(c, lambda s: s["pending"] and s["pending"][0]["kind"] == "PermissionRequest")
    reply(c, "allow")
    state = wait(c, lambda s: s["state"] == "error")
    assert "停止" in state["scheduler_error"]
    before = (tmp_path / "outputs/weekly-summary.md").read_bytes()
    close(c)
    calls = sum(client.calls for client in clients)
    reopened = make()
    row, = reopened.snapshot()["executions"]
    assert row["status"] == "interrupted"
    assert row["evidence"]["artifacts"][0]["status"] == "verified"
    assert (tmp_path / "outputs/weekly-summary.md").read_bytes() == before
    assert sum(client.calls for client in clients) == calls
