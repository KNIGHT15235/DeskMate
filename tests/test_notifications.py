"""Durable notification boundaries, upgrade, quiet hours and source recovery."""
from dataclasses import replace
from datetime import datetime, timezone
import sqlite3

import pytest

from likecc.notifications import DEFAULT_SETTINGS, is_quiet
from likecc.scheduling import ScheduleStore
from test_scheduling import Clock, reminder


@pytest.fixture
def store(tmp_path):
    value = ScheduleStore(tmp_path, clock=Clock())
    yield value
    value.close()


def due(store, *, kind="reminder"):
    task = store.save(replace(reminder(store.clock), kind=kind,
        outputs=["outputs/result.md"] if kind == "execute" else []))
    store.clock.advance(hours=2)
    store.scan()
    return store.execution(store.executions(task)[0]["id"])


def test_snooze_restart_single_delivery_and_independent_completion(store, tmp_path):
    execution = due(store)
    ledger = store.notifications
    task_before = store.task(execution["task_id"])
    row, = ledger.rows()
    assert ledger.claim_alert()
    row = ledger.get(row["id"])
    ledger.change(row["id"], row["revision"], "snooze", minutes=10)
    assert store.task(execution["task_id"]) == task_before
    assert store.execution(execution["id"])["status"] == "pending"
    store.close()
    reopened = ScheduleStore(tmp_path, clock=store.clock)
    try:
        ledger = reopened.notifications
        assert not ledger.claim_alert()
        store.clock.advance(minutes=9)
        assert not ledger.claim_alert()
        store.clock.advance(minutes=1)
        assert ledger.claim_alert()
        assert not ledger.claim_alert()
        for _ in range(4):
            reopened.scan()
        assert len(ledger.rows()) == 1
        row = ledger.get(row["id"])
        ledger.change(row["id"], row["revision"], "view")
        assert reopened.execution(execution["id"])["status"] == "pending"
        reopened.complete_reminder(execution["id"])
        assert not ledger.get(row["id"])["valid"]
        store.clock.advance(days=1)
        assert not ledger.claim_alert()
    finally:
        reopened.close()


def test_three_decisions_in_same_execution_and_duplicate_request(store):
    execution = due(store, kind="execute")
    ledger = store.notifications
    model, = ledger.rows()
    store.approve_model(execution["id"])
    store.start(execution["id"])
    store.update(execution["id"], run_id="run", session_id="session")
    for number in (1, 2):
        event = {"type": "PermissionRequest", "session_id": "session", "run_id": "run", "data": {
            "request_id": f"request-{number}", "tool_id": f"tool-{number}", "tool_name": "WriteFile", "description": "write"}}
        ledger.request(event, execution["id"])
        ledger.request(event, execution["id"])
        assert len(ledger.rows()) == number + 1
        assert not ledger.get(model["id"])["valid"]
        ledger.resolve("run", request_id=f"request-{number}", resolution="allow")
        assert not ledger.request(event, execution["id"])
    assert len({r["event_key"] for r in ledger.rows()}) == 3
    assert all(not r["valid"] for r in ledger.rows())


def test_source_and_notification_rollback_together(store, monkeypatch):
    execution = due(store)
    original = store.notifications.reconcile

    def fail_after_projection():
        original()
        raise OSError("injected before commit")

    monkeypatch.setattr(store.notifications, "reconcile", fail_after_projection)
    with pytest.raises(OSError):
        store.complete_reminder(execution["id"])
    assert store.execution(execution["id"])["status"] == "pending"
    assert store.notifications.rows()[0]["valid"]
    monkeypatch.setattr(store.notifications, "reconcile", original)
    store.complete_reminder(execution["id"])
    assert not store.notifications.rows()[0]["valid"]


def test_upgrade_keeps_decisions_and_failure_but_silences_old_completions(store, tmp_path):
    first = due(store, kind="execute")
    store.update(first["id"], status="completed")
    second = due(store, kind="execute")
    store.update(second["id"], status="failed")
    third = due(store, kind="execute")
    fourth = due(store)
    # Real R5/R6 schema: drop only newly introduced tables, preserving source rows.
    for table in ("notifications", "notification_requests", "notification_meta"):
        store.db.execute("DROP TABLE " + table)
    store.close()
    reopened = ScheduleStore(tmp_path, clock=store.clock)
    try:
        by_execution = {r["execution_id"]: r for r in reopened.notifications.rows()}
        assert by_execution[first["id"]]["state"] == "handled"
        assert by_execution[second["id"]]["kind"] == "failed"
        assert by_execution[third["id"]]["kind"] == "interrupted"
        assert by_execution[fourth["id"]]["kind"] == "reminder"
        assert len(reopened.notifications.due()) == 3
        assert reopened.notifications.claim_alert()
        assert not reopened.notifications.claim_alert()
    finally:
        reopened.close()


@pytest.mark.parametrize("hour,minute,expected", [(21,59,False), (22,0,True), (23,59,True),
    (0,0,True), (7,59,True), (8,0,False)])
def test_quiet_crosses_midnight_with_exact_boundaries(hour, minute, expected):
    settings = {**DEFAULT_SETTINGS, "enabled": True, "timezone": "UTC"}
    assert is_quiet(datetime(2026, 11, 23, hour, minute, tzinfo=timezone.utc), settings) is expected


def test_quiet_backlog_aggregates_only_valid_items_and_survives_restart(store, tmp_path):
    settings = {**DEFAULT_SETTINGS, "enabled": True, "start": "00:00", "end": "00:00", "timezone": "UTC"}
    store.notifications.configure(settings)
    first, second = due(store), due(store)
    third = due(store)
    assert not store.notifications.claim_alert()
    store.complete_reminder(first["id"])
    store.close()
    reopened = ScheduleStore(tmp_path, clock=store.clock)
    try:
        assert reopened.notifications.settings() == settings
        reopened.notifications.configure({**settings, "enabled": False})
        delivery = reopened.notifications.claim_alert()
        assert "2 条" in delivery["title"]
        assert not reopened.notifications.claim_alert()
        assert all(e["status"] == "pending" for e in reopened.executions() if e["id"] in {second["id"], third["id"]})
    finally:
        reopened.close()


def test_dismiss_only_notification_cancel_only_occurrence_and_stop_whole_schedule(store):
    task = store.save(reminder(store.clock, repeat="weekly"))
    store.clock.advance(hours=2)
    store.scan()
    row, = store.notifications.rows()
    task_before = store.task(task)
    store.notifications.change(row["id"], row["revision"], "dismiss")
    assert store.task(task) == task_before
    assert store.execution(row["execution_id"])["status"] == "pending"
    assert not store.notifications.claim_alert()
    store.cancel_execution(row["execution_id"])
    assert store.task(task) == task_before
    store.clock.advance(days=7)
    store.scan()
    assert len(store.executions()) == 2
    store.cancel(task)
    assert not store.task(task)["enabled"] and store.task(task)["next_due"] is None


@pytest.mark.parametrize("artifact,needle", [(None,"没有已写入"), ("written","未回读核对"),
    ("verified","文件已回读核对"), ("readback_failed","回读未通过"), ("write_unverified","写入结果未知")])
def test_completed_copy_is_grounded_in_artifact_evidence(store, artifact, needle):
    row = due(store, kind="execute")
    store.update(row["id"], status="completed", evidence={"artifacts":
        [{"path":"outputs/result.md", "status":artifact}] if artifact else []})
    note = next(n for n in store.notifications.rows() if n["kind"] == "completed")
    assert note["title"] == "运行结束" and needle in note["body"]
    assert ("文件已回读核对" in note["body"]) is (artifact == "verified")


def test_invalid_settings_and_stale_actions_do_not_change_source(store):
    row = due(store)
    note, = store.notifications.rows()
    before = store.execution(row["id"])
    with pytest.raises(ValueError):
        store.notifications.configure({**DEFAULT_SETTINGS,"start":"25:00"})
    with pytest.raises(ValueError):
        store.notifications.change(note["id"], note["revision"], "snooze", minutes=0)
    store.notifications.change(note["id"], note["revision"], "dismiss")
    with pytest.raises(ValueError, match="已变化"):
        store.notifications.change(note["id"], note["revision"], "snooze")
    assert store.execution(row["id"]) == before


def test_legacy_writer_projection_repairs_once_and_suppresses_stale_snooze(store):
    execution = due(store)
    note, = store.notifications.rows()
    store.notifications.change(note["id"], note["revision"], "snooze", minutes=1)
    # Simulate an older compatible writer that only knows the execution table.
    store.db.execute("UPDATE executions SET status='done' WHERE id=?", (execution["id"],))
    store.clock.advance(minutes=2)
    store.scan()
    assert not store.notifications.claim_alert()
    assert len(store.notifications.rows()) == 1


def test_alert_claim_commit_failure_rolls_back_then_restart_does_not_repeat(store, tmp_path):
    due(store)
    due(store)
    ledger = store.notifications
    before = ledger.rows()
    store.db.execute("PRAGMA busy_timeout=10")
    # A real SQLite reader allows BEGIN IMMEDIATE and projection writes, but
    # prevents COMMIT. Neither delivery generations nor throttle may survive it.
    reader = sqlite3.connect(store.path.as_uri() + "?mode=ro", uri=True, isolation_level=None)
    try:
        reader.execute("BEGIN")
        reader.execute("SELECT * FROM notifications").fetchall()
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            ledger.claim_alert()
        assert ledger.rows() == before
        assert store.db.execute("SELECT value FROM notification_meta WHERE key='last_alert'").fetchone() is None
    finally:
        reader.execute("ROLLBACK")
        reader.close()
        store.db.execute("PRAGMA busy_timeout=5000")
    delivery = ledger.claim_alert()
    assert {item["id"] for item in delivery["items"]} == {row["id"] for row in before}
    store.clock.advance(minutes=1)  # Outside throttle: persistence must suppress it.
    store.close()
    reopened = ScheduleStore(tmp_path, clock=store.clock)
    try:
        assert not reopened.notifications.claim_alert()
        rows = reopened.notifications.rows()
        assert len(rows) == 2
        assert all(row["alerted_generation"] == row["generation"] == 0 for row in rows)
    finally:
        reopened.close()


def test_replayed_permission_after_restart_does_not_resurrect_source_or_notification(store, tmp_path):
    execution = due(store, kind="execute")
    store.approve_model(execution["id"])
    assert store.start(execution["id"])
    store.update(execution["id"], run_id="run", session_id="session")
    event = {"type": "PermissionRequest", "session_id": "session", "run_id": "run", "data": {
        "request_id": "request", "tool_id": "tool", "tool_name": "WriteFile", "description": "outputs/result.md"}}
    assert store.notifications.request(event, execution["id"])
    active, = store.notifications.active_requests()
    assert active["run_id"] == "run" and active["request_id"] == "request"
    store.close()
    reopened = ScheduleStore(tmp_path, clock=store.clock)
    try:
        recovered = reopened.execution(execution["id"])
        rows = reopened.notifications.rows()
        assert recovered["status"] == "interrupted"
        assert not reopened.notifications.active_requests()
        for _ in range(5):
            assert not reopened.notifications.request(event, execution["id"])
            reopened.scan()
            assert reopened.execution(execution["id"]) == recovered
            assert reopened.notifications.rows() == rows
            assert not reopened.notifications.active_requests()
        request, = [row for row in rows if row["kind"] == "request"]
        assert not request["valid"]
    finally:
        reopened.close()
