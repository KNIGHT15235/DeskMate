"""Controller request liveness and command isolation beyond displayed snapshots."""
import threading

import pytest

from test_desktop_controller import command, wait, reply, close
from test_desktop_scheduling import desktop, arrange, execute_spec
from test_scheduling import reminder


def notify(c, action, row, **kwargs):
    return command(c, "notification_" + action, workspace=row["workspace"],
        notification_id=row["id"], revision=row["revision"], **kwargs)


def current(c):
    return next(n for n in c.snapshot()["notifications"] if n["kind"] == "request" and n["valid"])


@pytest.mark.parametrize("state", ["starting", "error"])
def test_alert_guard_rejection_releases_same_workspace_delivery_token(desktop, state):
    make, clock, _, _ = desktop
    c = make()
    arrange(c, reminder(clock))
    clock.advance(hours=2)
    assert command(c, "schedule_scan")["accepted"]
    snapshot = c.snapshot()
    assert snapshot["notification_due"]
    workspace = snapshot["workspace"]
    notification_id, = [row["id"] for row in snapshot["notifications"]]

    # An already queued Qt claim can reach the worker while reopening the same
    # workspace or after a worker error. Qt may never observe a workspace change,
    # so it needs the matching failed response to release its in-flight token.
    c._set(state=state)
    try:
        rejected = command(c, "notification_alert", workspace=workspace,
                           request_token="guard-rejected")
        response = c.snapshot()["notification_alert"]
    finally:
        c._set(state="idle")
    assert not rejected["accepted"]
    assert response == {"request_token": "guard-rejected", "workspace": workspace,
                        "delivery": None, "failed": True}

    assert command(c, "notification_alert", workspace=workspace,
                   request_token="after-recovery")["accepted"]
    delivered = c.snapshot()["notification_alert"]
    assert delivered["request_token"] == "after-recovery"
    assert [row["id"] for row in delivered["delivery"]["items"]] == [notification_id]


def test_question_snooze_resolution_and_stale_permission_navigation(desktop, tmp_path):
    make, clock, clients, _ = desktop
    c = make()
    arrange(c, execute_spec(clock))
    clock.advance(hours=2)
    command(c, "schedule_scan")
    model = next(n for n in c.snapshot()["notifications"] if n["kind"] == "model")
    assert notify(c, "open", model)["accepted"]
    assert all(client.calls == 0 for client in clients)
    assert command(c, "schedule_allow_model", execution_id=model["execution_id"])["accepted"]
    wait(c, lambda s: s["pending"] and s["pending"][0]["kind"] == "UserInputRequest")
    question = current(c)
    assert notify(c, "snooze", question, minutes=1)["accepted"]
    question = current(c)
    before = sum(client.calls for client in clients)
    assert notify(c, "open", question)["accepted"]
    assert c.snapshot()["notification_target"]["mode"] == "request"
    assert sum(client.calls for client in clients) == before
    assert reply(c, {"note":"answer"})["accepted"]
    wait(c, lambda s: s["pending"] and s["pending"][0]["kind"] == "PermissionRequest")
    permission = current(c)
    assert permission["request_id"] != question["request_id"]
    stale = next(n for n in c.snapshot()["notifications"] if n["id"] == question["id"])
    assert notify(c, "open", stale)["accepted"]
    assert c.snapshot()["notification_target"]["mode"] == "execution"
    assert not notify(c, "cancel_execution", stale)["accepted"]
    assert c.snapshot()["pending"][0]["request_id"] == permission["request_id"]
    assert not (tmp_path / "outputs/weekly-summary.md").exists()
    assert reply(c, "deny")["accepted"]
    wait(c, lambda s: s["state"] == "idle")
    clock.advance(minutes=2)
    command(c, "schedule_scan")
    assert not any(n["valid"] for n in c.snapshot()["notifications"] if n["kind"] == "request")


def test_click_rechecks_real_future_even_with_stale_pending_snapshot(desktop):
    make, clock, _, _ = desktop
    c = make()
    arrange(c, execute_spec(clock, model_policy="allow"))
    clock.advance(hours=2)
    command(c, "schedule_scan")
    wait(c, lambda s: bool(s["pending"]))
    row = current(c)
    finished, results = threading.Event(), {}

    async def probe():
        try:
            # Resolve the actual question without yet consuming its result. The
            # old UI pending row deliberately remains, exactly the click race.
            request = c.snapshot()["pending"][0]
            assert c._run.reply(request["run_id"], request["request_id"], {"note":"resolved"})
            await c._notification_command("notification_open", {"workspace":row["workspace"],
                "notification_id":row["id"], "revision":row["revision"]})
            results["mode"] = c.snapshot()["notification_target"]["mode"]
            results["request"] = c.snapshot()["pending"][0]["request_id"]
        finally:
            finished.set()

    import asyncio
    future = asyncio.run_coroutine_threadsafe(probe(), c._loop)
    assert finished.wait(5)
    future.result(timeout=5)
    assert results == {"mode":"execution", "request": row["request_id"]}


def test_cancel_current_execution_does_not_disable_next_cycle(desktop):
    make, clock, _, _ = desktop
    c = make()
    task = arrange(c, execute_spec(clock, model_policy="allow"))
    clock.advance(hours=2)
    command(c, "schedule_scan")
    wait(c, lambda s: bool(s["pending"]))
    row = current(c)
    assert notify(c, "cancel_execution", row)["accepted"]
    final = wait(c, lambda s: s["state"] == "idle")
    assert final["tasks"][0]["id"] == task and final["tasks"][0]["enabled"]
    assert final["executions"][0]["status"] == "cancelled"
    assert not notify(c, "cancel_execution", row)["accepted"]
