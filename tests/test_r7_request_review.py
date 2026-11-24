"""R7 review: authoritative request liveness and workspace handover races."""
import asyncio
import sqlite3

import pytest

from likecc.desktop.controller import DesktopOptions
from test_desktop_controller import command, reply, wait
from test_desktop_scheduling import arrange, desktop, execute_spec
from likecc.tools.write_file import WriteFile


def waiting_review_request(desktop, permission):
    make, clock, clients, _ = desktop
    c = make()
    arrange(c, execute_spec(clock, model_policy="allow"))
    clock.advance(hours=2)
    command(c, "schedule_scan")
    wait(c, lambda s: bool(s["pending"]))
    if permission:
        assert reply(c, {"note": "continue to permission"})["accepted"]
        wait(c, lambda s: s["pending"] and s["pending"][0]["kind"] == "PermissionRequest")
    return c, clients


def record_writes(monkeypatch):
    writes = []
    original = WriteFile._write_text

    def recorded(tool, path, content):
        writes.append(str(path))
        return original(tool, path, content)

    monkeypatch.setattr(WriteFile, "_write_text", recorded)
    return writes


@pytest.mark.parametrize("decision", ["allow", "deny", "answer"])
def test_reply_persistence_failure_keeps_future_live_until_explicit_retry(desktop, tmp_path, monkeypatch, decision):
    writes = record_writes(monkeypatch)
    c, clients = waiting_review_request(desktop, permission=decision != "answer")

    async def probe():
        pending = c.snapshot()["pending"][0]
        value = {"note": "confirmed"} if decision == "answer" else decision
        payload = {key: pending[key] for key in ("session_id", "run_id", "request_id")}
        payload["value"] = value
        ledger = c._store.notifications
        original = ledger.resolve
        failed = False
        calls = sum(client.calls for client in clients)

        def fail_once(*args, **kwargs):
            nonlocal failed
            if not failed:
                failed = True
                raise sqlite3.OperationalError("review injected resolve failure")
            return original(*args, **kwargs)

        ledger.resolve = fail_once
        try:
            await c._dispatch("failed-persist", "reply", payload)
            assert not c.snapshot()["command"]["accepted"]
            assert c._run.interaction.is_pending(pending["request_id"])
            assert sum(client.calls for client in clients) == calls and not writes
            assert not (tmp_path / "outputs/weekly-summary.md").exists()
            assert tuple(c._store.db.execute(
                "SELECT active,resolution FROM notification_requests WHERE run_id=? AND request_id=?",
                (pending["run_id"], pending["request_id"])).fetchone()) == (1, "")
            # A separate explicit retry can now commit the decision and release
            # exactly the same Future; a failed save did not grant permission.
            await c._dispatch("retry-persist", "reply", payload)
            assert c.snapshot()["command"]["accepted"]
            assert not c._run.interaction.is_pending(pending["request_id"])
            return tuple(c._store.db.execute(
                "SELECT active,resolution FROM notification_requests WHERE run_id=? AND request_id=?",
                (pending["run_id"], pending["request_id"])).fetchone())
        finally:
            ledger.resolve = original

    resolved = asyncio.run_coroutine_threadsafe(probe(), c._loop).result(timeout=20)
    assert resolved == (0, "answered" if decision == "answer" else decision)
    if decision == "answer":
        wait(c, lambda s: s["pending"] and s["pending"][0]["kind"] == "PermissionRequest")
        assert reply(c, "allow")["accepted"]
    wait(c, lambda s: s["state"] == "idle")
    assert sum(client.tools.count("WriteFile") for client in clients) == 1
    assert len(writes) == (0 if decision == "deny" else 1)
    assert (tmp_path / "outputs/weekly-summary.md").exists() == (decision != "deny")


def test_reply_refresh_failure_does_not_report_committed_allow_as_rejected(desktop, tmp_path, monkeypatch):
    writes = record_writes(monkeypatch)
    c, clients = waiting_review_request(desktop, permission=True)

    async def probe():
        pending = c.snapshot()["pending"][0]
        payload = {key: pending[key] for key in ("session_id", "run_id", "request_id")}
        payload["value"] = "allow"
        original = c._notification_view

        def failed_refresh():
            raise sqlite3.OperationalError("review injected refresh failure")

        c._notification_view = failed_refresh
        try:
            await c._dispatch("failed-refresh", "reply", payload)
            return c.snapshot()["command"], tuple(c._store.db.execute(
                "SELECT active,resolution FROM notification_requests WHERE run_id=? AND request_id=?",
                (pending["run_id"], pending["request_id"])).fetchone())
        finally:
            c._notification_view = original

    receipt, resolved = asyncio.run_coroutine_threadsafe(probe(), c._loop).result(timeout=20)
    assert receipt["accepted"]
    assert resolved == (0, "allow")
    wait(c, lambda s: s["state"] == "idle")
    assert len(writes) == 1 and (tmp_path / "outputs/weekly-summary.md").exists()
    assert sum(client.tools.count("WriteFile") for client in clients) == 1


def test_invalid_answer_does_not_persist_resolution_or_end_future(desktop):
    c, clients = waiting_review_request(desktop, permission=False)

    async def probe():
        pending = c.snapshot()["pending"][0]
        payload = {key: pending[key] for key in ("session_id", "run_id", "request_id")}
        payload["value"] = {"note": 42}
        before = c._store.notifications.rows()
        calls = sum(client.calls for client in clients)
        await c._dispatch("invalid-answer", "reply", payload)
        return {"receipt": c.snapshot()["command"], "live": c._run.interaction.is_pending(pending["request_id"]),
            "before": before, "after": c._store.notifications.rows(), "calls": calls,
            "calls_after": sum(client.calls for client in clients), "fact": tuple(c._store.db.execute(
                "SELECT active,resolution FROM notification_requests WHERE run_id=? AND request_id=?",
                (pending["run_id"], pending["request_id"])).fetchone())}

    result = asyncio.run_coroutine_threadsafe(probe(), c._loop).result(timeout=20)
    assert not result["receipt"]["accepted"] and result["live"]
    assert result["fact"] == (1, "") and result["after"] == result["before"]
    assert result["calls_after"] == result["calls"]


def test_terminal_request_cleanup_failure_allows_explicit_reopen_without_replay(desktop, tmp_path, monkeypatch):
    writes = record_writes(monkeypatch)
    c, clients = waiting_review_request(desktop, permission=True)
    before = c.snapshot()
    execution_id = before["executions"][0]["id"]
    session_id = before["pending"][0]["session_id"]
    calls = sum(client.calls for client in clients)

    async def probe():
        ledger = c._store.notifications
        original_resolve, original_event = ledger.resolve, c._event
        consumed_terminal = False
        failures = []
        consumer = c._consumer

        def observed_event(event):
            nonlocal consumed_terminal
            original_event(event)
            if event["type"] == "LoopComplete":
                consumed_terminal = True

        def fail_final_cleanup(*args, **kwargs):
            # The LoopComplete event itself succeeds. Inject only the final
            # whole-run notification cleanup, outside event processing.
            if consumed_terminal and not kwargs and not failures:
                failures.append(True)
                raise sqlite3.OperationalError("review injected terminal resolve failure")
            return original_resolve(*args, **kwargs)

        ledger.resolve, c._event = fail_final_cleanup, observed_event
        try:
            await c._dispatch("cancel-terminal-review", "cancel", {})
            result, = await asyncio.gather(consumer, return_exceptions=True)
            return c.snapshot(), result, failures, c._run
        finally:
            ledger.resolve, c._event = original_resolve, original_event

    state, result, failures, current_run = asyncio.run_coroutine_threadsafe(probe(), c._loop).result(timeout=20)
    assert failures == [True]
    assert state["state"] == "error" and not state["pending"]
    assert "terminal resolve failure" in state["scheduler_error"]
    assert current_run is None and not isinstance(result, BaseException)
    assert sum(client.calls for client in clients) == calls and not writes
    assert not (tmp_path / "outputs/weekly-summary.md").exists()

    assert command(c, "open", work_dir=str(tmp_path))["accepted"]
    reopened = wait(c, lambda s: s["state"] == "idle")
    execution, = reopened["executions"]
    assert execution["id"] == execution_id and execution["status"] == "interrupted"
    assert command(c, "resume", session_id=session_id)["accepted"]
    assert not c.snapshot()["pending"]
    assert command(c, "schedule_scan")["accepted"]
    assert sum(client.calls for client in clients) == calls and not writes
    assert not (tmp_path / "outputs/weekly-summary.md").exists()


@pytest.mark.parametrize("kind", ["UserInputRequest", "PermissionRequest"])
@pytest.mark.parametrize("ending", ["answered", "cancelled"])
def test_alert_does_not_claim_request_after_its_future_ends(desktop, kind, ending):
    make, clock, clients, _ = desktop
    c = make()
    arrange(c, execute_spec(clock, model_policy="allow"))
    clock.advance(hours=2)
    assert command(c, "schedule_scan")["accepted"]
    wait(c, lambda s: bool(s["pending"]))
    if kind == "PermissionRequest":
        assert reply(c, {"note": "continue to write permission"})["accepted"]
        wait(c, lambda s: s["pending"] and s["pending"][0]["kind"] == kind)

    async def probe():
        pending = c.snapshot()["pending"][0]
        assert pending["kind"] == kind
        row = next(n for n in c.snapshot()["notifications"]
                   if n["request_id"] == pending["request_id"])
        interaction = c._run.interaction
        calls = sum(client.calls for client in clients)
        if ending == "answered":
            value = "deny" if kind == "PermissionRequest" else {"note": "finished"}
            assert c._run.reply(pending["run_id"], pending["request_id"], value)
        else:
            # wait_for cancels this same Future at its timeout boundary. Keep
            # the consumer from handling ToolResult until after the alert call.
            interaction._pending[pending["request_id"]][1].cancel()
        assert not interaction.is_pending(pending["request_id"])
        assert c.snapshot()["pending"]  # stale UI/ledger, but ended actual Future
        await c._notification_command("notification_alert", {
            "workspace": row["workspace"], "request_token": "expired-review"})
        return (c.snapshot()["notification_alert"]["delivery"],
                c._store.notifications.get(row["id"]),
                calls, sum(client.calls for client in clients))

    delivery, stored, calls_before, calls_after = asyncio.run_coroutine_threadsafe(
        probe(), c._loop).result(timeout=20)
    assert delivery is None
    assert not stored["valid"] and stored["alerted_generation"] == -1
    assert calls_after == calls_before


def test_alert_keeps_live_requests_not_in_the_latest_pending_snapshot(desktop):
    make, clock, _, _ = desktop
    c = make()
    arrange(c, execute_spec(clock, model_policy="allow"))
    clock.advance(hours=2)
    command(c, "schedule_scan")
    wait(c, lambda s: bool(s["pending"]))

    async def probe():
        run = c._run
        first = c.snapshot()["pending"][0]["request_id"]
        second = run.interaction.request("permission")
        # A second live interaction replaces the single visible pending card;
        # absence from that presentation cache must not expire the first one.
        c._event({"type": "PermissionRequest", "session_id": run.session_id,
            "run_id": run.run_id, "data": {"request_id": second,
                "run_id": run.run_id, "tool_id": "parallel-review",
                "tool_name": "WriteFile", "description": "outputs/weekly-summary.md"}})
        assert c.snapshot()["pending"][0]["request_id"] == second
        assert run.interaction.is_pending(first) and run.interaction.is_pending(second)
        await c._notification_command("notification_alert", {
            "workspace": c.snapshot()["workspace"], "request_token": "live-review"})
        delivery = c.snapshot()["notification_alert"]["delivery"]
        rows = {n["id"]: n for n in c.snapshot()["notifications"]}
        return {rows[item["id"]]["request_id"] for item in delivery["items"]}, {first, second}

    delivered, expected = asyncio.run_coroutine_threadsafe(probe(), c._loop).result(timeout=20)
    assert delivered == expected


@pytest.mark.parametrize("kind", ["UserInputRequest", "PermissionRequest"])
def test_late_first_request_event_does_not_resurrect_ended_future(desktop, kind):
    make, clock, clients, _ = desktop
    c = make()
    arrange(c, execute_spec(clock, model_policy="allow"))
    clock.advance(hours=2)
    command(c, "schedule_scan")
    wait(c, lambda s: bool(s["pending"]))

    async def probe():
        run = c._run
        original = c.snapshot()["pending"]
        calls = sum(client.calls for client in clients)
        request_id = run.interaction.request("permission" if kind == "PermissionRequest" else "input")
        run.interaction._pending[request_id][1].cancel()
        data = {"run_id": run.run_id, "request_id": request_id, "tool_id": "late-review"}
        if kind == "PermissionRequest":
            data.update(tool_name="WriteFile", description="outputs/weekly-summary.md")
        else:
            data["questions"] = [{"type": "text", "name": "late", "message": "expired question"}]
        c._event({"type": kind, "run_id": run.run_id, "session_id": run.session_id, "data": data})
        return {"original": original, "pending": c.snapshot()["pending"],
            "expired_notifications": [n for n in c.snapshot()["notifications"]
                                      if n["request_id"] == request_id and n["valid"]],
            "original_still_live": run.interaction.is_pending(original[0]["request_id"]),
            "calls_before": calls, "calls_after": sum(client.calls for client in clients)}

    result = asyncio.run_coroutine_threadsafe(probe(), c._loop).result(timeout=20)
    assert result["pending"] == result["original"]
    assert not result["expired_notifications"]
    assert result["original_still_live"]
    assert result["calls_after"] == result["calls_before"]


@pytest.mark.parametrize("action", ["open", "snooze", "dismiss", "cancel_execution", "stop_task", "configure"])
def test_old_notification_commands_are_rejected_during_workspace_release(desktop, tmp_path, action):
    make, clock, clients, _ = desktop
    c = make()
    arrange(c, execute_spec(clock))
    clock.advance(hours=2)
    command(c, "schedule_scan")
    row = next(n for n in c.snapshot()["notifications"] if n["kind"] == "model")
    task = c.snapshot()["tasks"][0]
    other = tmp_path / "B"
    other.mkdir()

    async def probe():
        original_release = c._release
        entered, proceed = asyncio.Event(), asyncio.Event()

        async def held_release():
            entered.set()
            await proceed.wait()
            await original_release()

        before = c._schedule_values()
        c._release = held_release
        opening = asyncio.create_task(c._open(DesktopOptions(work_dir=str(other))))
        try:
            await entered.wait()
            assert c.snapshot()["state"] == "starting" and c.snapshot()["workspace"] == ""
            assert c._store.workspace == row["workspace"]
            await c._dispatch("stale-review", "notification_" + action, {
                "workspace": row["workspace"], "notification_id": row["id"],
                "revision": row["revision"], "task_revision": task["revision"], "minutes": 1,
                "settings": {"enabled": True, "start": "01:00", "end": "02:00", "timezone": "UTC"}})
            result = (c.snapshot()["command"], before, c._schedule_values(), c.snapshot()["notifications"])
        finally:
            c._release = original_release
            proceed.set()
            await opening
        return result

    receipt, before, after, shown = asyncio.run_coroutine_threadsafe(probe(), c._loop).result(timeout=20)
    assert not receipt["accepted"]
    assert after == before
    assert shown == []
    assert c.snapshot()["workspace"] == str(other.resolve())
    assert not c.snapshot()["notifications"] and not c.snapshot()["tasks"]
    assert all(client.calls == 0 for client in clients)
