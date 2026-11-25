"""R7-C through the normal DesktopApplication, real Qt controls and local tools."""
from datetime import timedelta
import json
from pathlib import Path
import time

import pytest
pytest.importorskip("PySide6")
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from examples.deskmate_notifications import prepare, controller, injected_write_failure
from likecc.desktop.application import DesktopApplication
from likecc.desktop.controller import DesktopOptions
from test_desktop_window import qtapp, spin as qt_spin, offline_socket_guard
from test_desktop_lifecycle import FakeTray
from test_desktop_controller import command
from test_scheduling import Clock


def spin(predicate, timeout=20):
    # QTest.qWait pumps Qt but can monopolize Python on Windows. Yield the GIL
    # explicitly so the real worker can finish SQLite/filesystem transactions.
    def probe():
        time.sleep(0.001)
        return predicate()
    qt_spin(probe, timeout=timeout)


@pytest.fixture
def journey(qtapp, tmp_path, offline_socket_guard):
    root, clock, inputs, owners = prepare(tmp_path), Clock(), [], []

    def open_app(tray=True):
        options = DesktopOptions(work_dir=str(root / "A"))
        c = controller(options, root, inputs=inputs, clock=clock)
        owner = DesktopApplication(qtapp, c, options, tray_probe=lambda: tray,
            tray_factory=FakeTray, quit_callback=lambda: None)
        owners.append(owner)
        spin(lambda: c.snapshot()["state"] == "idle")
        owner.window.refresh()
        return owner, c

    with injected_write_failure(root):
        yield root, clock, inputs, open_app
        for owner in owners:
            if owner.controller.is_alive:
                shutdown(owner)


def shutdown(owner):
    owner.request_exit()
    spin(lambda: not owner.controller.is_alive)
    owner.poll()
    owner.dispose()


def arrange(owner, clock, content, outputs=(), repeat="weekly"):
    w, c = owner.window, owner.controller
    before = {t["id"] for t in c.snapshot()["tasks"]}
    w.show_schedules()
    manager = w.schedule_window
    manager.clear_form()
    manager.content.setPlainText(content)
    manager.kind.setCurrentIndex(manager.kind.findData("execute" if outputs else "reminder"))
    manager.repeat.setCurrentIndex(manager.repeat.findData(repeat))
    manager.timezone.setCurrentText("UTC")
    manager.local_at.setText((clock() + timedelta(minutes=1)).replace(tzinfo=None).isoformat())
    manager.files.setPlainText("project_notes.md" if outputs else "")
    manager.outputs.setPlainText("\n".join(outputs))
    manager.preview_button.click()
    spin(lambda: manager.confirm.isEnabled())
    manager.confirm.click()
    spin(lambda: len(c.snapshot()["tasks"]) > len(before))
    manager.hide()
    return next(t for t in c.snapshot()["tasks"] if t["id"] not in before)


def note(c, kind, *, valid=True):
    matches = [n for n in c.snapshot()["notifications"] if n["kind"] == kind and bool(n["valid"]) == valid]
    return matches[0] if matches else None


def wait_request(c):
    try:
        spin(lambda: bool(note(c, "request")))
    except AssertionError as exc:
        state = c.snapshot()
        raise AssertionError({k: state[k] for k in ("state", "pending", "notifications", "executions", "command", "rows")}) from exc


def select(owner, row):
    owner.show_notifications()
    center = owner.window.notification_window
    center.refresh()
    index = next(i for i, n in enumerate(center._rows) if n["id"] == row["id"])
    center.listing.setCurrentRow(index)
    center.show_details()
    return center


def navigate(owner, row):
    c = owner.controller
    previous = c.snapshot().get("notification_target")
    center = select(owner, row)
    center.open_button.click()
    spin(lambda: c.snapshot().get("notification_target") != previous)
    owner.window.refresh()
    return c.snapshot()["notification_target"]


def advance(c, clock, **kwargs):
    clock.advance(**kwargs)
    assert command(c, "schedule_scan")["accepted"]


def allow_model(owner):
    c = owner.controller
    spin(lambda: note(c, "model"))
    row = note(c, "model")
    target = navigate(owner, row)
    assert target["execution_id"] == row["execution_id"]
    manager = owner.window.schedule_window
    assert manager.executions.currentData() == row["execution_id"]
    assert manager.allow_model.isEnabled()
    manager.allow_model.click()
    manager.hide()
    if owner.window.notification_window:
        owner.window.notification_window.hide()
    return row


def answer(owner, value="allow"):
    c = owner.controller
    spin(lambda: bool(c.snapshot()["pending"]))
    owner.window.refresh()
    button = owner.window.request_area.findChild(QPushButton, value)
    assert button and button.isEnabled()
    button.click()


@pytest.mark.parametrize("tray", [True, False])
def test_reminder_snooze_complete_exit_restart_once(journey, tray):
    root, clock, inputs, open_app = journey
    owner, c = open_app(tray)
    task = arrange(owner, clock, "R7 reminder", repeat="once")
    owner.window.showMinimized()
    advance(c, clock, minutes=2)
    spin(lambda: note(c, "reminder"))
    if tray:
        spin(lambda: len(owner.tray.messages) == 1)
    row = note(c, "reminder")
    center = select(owner, row)
    center.minutes.setValue(1)
    center.snooze_button.click()
    spin(lambda: note(c, "reminder")["state"] == "snoozed")
    due_at = c.snapshot()["executions"][0]["due_at"]
    shutdown(owner)
    owner, c = open_app(tray)
    owner.window.showMinimized()
    QTest.qWait(250)
    if tray:
        assert not owner.tray.messages
    advance(c, clock, seconds=59)
    assert note(c, "reminder")["state"] == "snoozed"
    advance(c, clock, seconds=1)
    if tray:
        spin(lambda: len(owner.tray.messages) == 1)
        QTest.qWait(250)
        assert len(owner.tray.messages) == 1
        owner.tray.messageClicked.emit()
        assert owner.window.notification_window.isVisible()
    navigate(owner, note(c, "reminder"))
    manager = owner.window.schedule_window
    manager.complete.click()
    spin(lambda: c.snapshot()["executions"][0]["status"] == "done")
    assert c.snapshot()["executions"][0]["due_at"] == due_at
    assert c.snapshot()["tasks"][0]["spec"] == task["spec"]
    assert not note(c, "reminder") and not inputs
    shutdown(owner)
    owner, c = open_app(tray)
    advance(c, clock, days=1)
    assert len(c.snapshot()["notifications"]) == 1
    assert not c.snapshot()["notification_due"] and not inputs


@pytest.mark.parametrize("window_state", ["visible", "minimized", "hidden", "no_tray"])
@pytest.mark.parametrize("entry", ["row", "button"])
def test_permission_navigation_reveals_card_with_managers_left_open(journey, window_state, entry):
    root, clock, inputs, open_app = journey
    owner, c = open_app(tray=window_state != "no_tray")
    w = owner.window
    arrange(owner, clock, "R7 通知定位", ["outputs/navigation.md"])
    advance(c, clock, minutes=2)
    spin(lambda: note(c, "model"))
    navigate(owner, note(c, "model"))
    manager = w.schedule_window
    manager.allow_model.click()
    # Real users leave this owned dialog open after confirming the model.
    # Hiding it in a test helper masks the Windows owner/owned-window stacking.
    wait_request(c)
    manager.content.setPlainText("保留尚未保存的安排草稿")
    w.show_memories()
    if window_state == "minimized":
        w.showMinimized()
    elif window_state == "hidden":
        w.hide()
    row = note(c, "request")
    calls = len(inputs)
    for _ in range(2):
        center = select(owner, row)
        previous = c.snapshot().get("notification_target")
        if entry == "row":
            item = center.listing.currentItem()
            QTest.mouseClick(center.listing.viewport(), Qt.MouseButton.LeftButton,
                             pos=center.listing.visualItemRect(item).center())
        else:
            center.open_button.click()
        spin(lambda: c.snapshot().get("notification_target") != previous)
        w.refresh()
        assert c.snapshot()["notification_target"]["mode"] == "request"
        assert not manager.isVisible(), "任务窗口仍遮挡原权限卡片"
        assert not w.memory_window.isVisible()
        assert not center.isVisible()
        assert w.isVisible() and not w.isMinimized()
        assert w.request_area.isVisible()
        for name in ("allow", "deny"):
            button = w.request_area.findChild(QPushButton, name)
            assert button.isVisible() and button.isEnabled()
        spin(w.request_area.hasFocus)  # Qt delivers window activation asynchronously.
        assert c.snapshot()["pending"][0]["request_id"] == row["request_id"]
        assert len(inputs) == calls and not (root / "A/outputs/navigation.md").exists()
        assert not (root / "writes.jsonl").exists()
        w.show_schedules()
        assert manager.content.toPlainText() == "保留尚未保存的安排草稿"
        w.show_memories()
        row = next(n for n in c.snapshot()["notifications"] if n["id"] == row["id"])


@pytest.mark.parametrize("deny", [False, True])
def test_periodic_model_two_permissions_verified_or_denied(journey, deny):
    root, clock, inputs, open_app = journey
    owner, c = open_app()
    outputs = ["outputs/denied.md"] if deny else ["outputs/first.md", "outputs/second.md"]
    arrange(owner, clock, "R7 两次写入", outputs)
    advance(c, clock, minutes=2)
    model = allow_model(owner)
    decisions = []
    for index, output in enumerate(outputs):
        wait_request(c)
        row = note(c, "request")
        decisions.append(row)
        before = len(inputs)
        target = navigate(owner, row)
        assert target["mode"] == "request"
        assert len(inputs) == before and not (root / "A" / output).exists()
        assert c.snapshot()["pending"][0]["request_id"] == row["request_id"]
        answer(owner, "deny" if deny else "allow")
        spin(lambda: not any(n["id"] == row["id"] and n["valid"] for n in c.snapshot()["notifications"]))
    spin(lambda: c.snapshot()["state"] == "idle" and note(c, "completed"))
    completed = note(c, "completed")
    assert all(n["execution_id"] == model["execution_id"] for n in decisions + [completed])
    assert len({n["request_id"] for n in decisions}) == len(outputs)
    if deny:
        assert "写入被拒绝" in completed["body"] and "文件已回读核对" not in completed["body"]
        assert not (root / "A" / outputs[0]).exists()
    else:
        assert completed["body"].count("文件已回读核对") == 2
        assert all((root / "A" / path).is_file() for path in outputs)
    calls_before = len(inputs)
    snapshot = [(p, (root / "A" / p).stat().st_mtime_ns) for p in outputs if (root / "A" / p).exists()]
    for _ in range(3):
        navigate(owner, next(n for n in c.snapshot()["notifications"] if n["id"] == completed["id"]))
        assert owner.window.schedule_window.executions.currentData() == model["execution_id"]
    assert all(path in owner.window.schedule_window.details.toPlainText() for path in outputs) if not deny else True
    # Ended permission clicks select historical execution, never another request.
    target = navigate(owner, next(n for n in c.snapshot()["notifications"] if n["id"] == decisions[0]["id"]))
    assert target["mode"] == "execution" and not c.snapshot()["pending"]
    session = completed["session_id"]
    assert command(c, "resume", session_id=session)["accepted"]
    shutdown(owner)
    owner, c = open_app()
    assert len(inputs) == calls_before
    assert snapshot == [(p, (root / "A" / p).stat().st_mtime_ns) for p, _ in snapshot]
    assert len(c.snapshot()["notifications"]) == len(outputs) + 2


@pytest.mark.parametrize("fault", ["failed", "interrupted"])
def test_failure_unknown_review_navigation_and_restart_never_replays(journey, fault):
    root, clock, inputs, open_app = journey
    owner, c = open_app()
    output = "outputs/unknown.md" if fault == "interrupted" else "outputs/failed.md"
    arrange(owner, clock, "R7 未知写入" if fault == "interrupted" else "R7 失败", [output])
    advance(c, clock, minutes=2)
    allow_model(owner)
    if fault == "interrupted":
        answer(owner)
    spin(lambda: c.snapshot()["state"] == "idle" and note(c, fault))
    row = note(c, fault)
    disk = root / "A" / output
    if fault == "interrupted":
        assert "写入结果未知" in row["body"] and disk.read_text(encoding="utf-8").startswith("R7 故障注入")
        assert "文件已回读核对" not in row["body"]
    else:
        assert not disk.exists()
    calls = len(inputs)
    writes = (root / "writes.jsonl").read_bytes() if (root / "writes.jsonl").exists() else b""
    for _ in range(3):
        navigate(owner, next(n for n in c.snapshot()["notifications"] if n["id"] == row["id"]))
        manager = owner.window.schedule_window
        assert not manager.reviewed.isChecked() and not manager.retry.isEnabled()
        assert manager.executions.currentData() == row["execution_id"]
    assert command(c, "resume", session_id=row["session_id"])["accepted"]
    shutdown(owner)
    owner, c = open_app()
    advance(c, clock, days=7)
    if fault == "interrupted":
        assert any(e["status"] == "blocked_review" for e in c.snapshot()["executions"])
    assert len(inputs) == calls
    assert ((root / "writes.jsonl").read_bytes() if (root / "writes.jsonl").exists() else b"") == writes


def test_visible_hidden_quiet_backlog_and_stale_workspace_click(journey):
    root, clock, inputs, open_app = journey
    owner, c = open_app()
    first = arrange(owner, clock, "R7 first", repeat="once")
    arrange(owner, clock, "R7 second", repeat="once")
    advance(c, clock, minutes=2)
    QTest.qWait(250)
    assert not owner.tray.messages  # visible main window uses the center
    center = select(owner, note(c, "reminder"))
    center.quiet.setChecked(True)
    center.start.setText("22:00")
    center.end.setText("08:00")
    center.timezone.setCurrentText("UTC")
    center.save_quiet.click()
    spin(lambda: c.snapshot()["notification_settings"].get("enabled"))
    clock.now = clock.now.replace(hour=23, minute=0)
    command(c, "schedule_scan")
    center.hide()
    owner.window.hide()
    QTest.qWait(250)
    assert not owner.tray.messages
    advance(c, clock, hours=1)
    assert c.snapshot()["notification_quiet"]
    row = next(n for n in c.snapshot()["notifications"] if n["task_id"] == first["id"])
    assert command(c, "schedule_complete", execution_id=row["execution_id"])["accepted"]
    advance(c, clock, hours=8)
    spin(lambda: len(owner.tray.messages) == 1)
    assert len([n for n in c.snapshot()["notifications"] if n["valid"]]) == 1
    old = note(c, "reminder")
    owner.show_window()
    owner.window.workspace.setText(str(root / "B"))
    owner.window.open_button.click()
    spin(lambda: c.snapshot()["workspace"] == str(root / "B") and c.snapshot()["state"] == "idle")
    for action in ("open", "snooze", "dismiss", "cancel_execution", "stop_task"):
        result = command(c, "notification_" + action, workspace=old["workspace"], notification_id=old["id"],
            revision=old["revision"], task_revision=1)
        assert not result["accepted"] and "工作区" in result["message"]
    assert not c.snapshot()["tasks"] and not c.snapshot()["notifications"] and not inputs


@pytest.mark.parametrize("outputs,kind", [(["outputs/result.md"], "model"), ([], "reminder")])
@pytest.mark.parametrize("dismiss_first", [False, True])
def test_cancel_occurrence_and_stop_period_have_distinct_effects(journey, outputs, kind, dismiss_first):
    _, clock, inputs, open_app = journey
    owner, c = open_app()
    task = arrange(owner, clock, "R7 cancel", outputs)
    advance(c, clock, minutes=2)
    row = note(c, kind)
    task_before = c.snapshot()["tasks"][0]
    center = select(owner, row)
    if dismiss_first:
        center.dismiss_button.click()
        spin(lambda: next(n for n in c.snapshot()["notifications"] if n["id"] == row["id"])["state"] == "handled")
        center.refresh()
        assert not center.snooze_button.isEnabled()
        assert c.snapshot()["executions"][0]["status"] == ("pending" if kind == "reminder" else "awaiting_model")
    assert center.cancel_button.isEnabled()
    assert center.stop_button.isEnabled()
    center.cancel_button.click()
    spin(lambda: c.snapshot()["executions"][0]["status"] == "cancelled")
    assert c.snapshot()["tasks"][0] == task_before
    assert not command(c, "notification_cancel_execution", workspace=row["workspace"], notification_id=row["id"],
        revision=row["revision"])["accepted"]
    advance(c, clock, days=7)
    assert len(c.snapshot()["executions"]) == 2
    next_row = note(c, kind)
    assert next_row["execution_id"] != row["execution_id"]
    executions_before = c.snapshot()["executions"]
    task_after_scan = c.snapshot()["tasks"][0]
    history_row = next(n for n in c.snapshot()["notifications"] if n["id"] == row["id"])
    for old_row in (row, history_row):
        assert not command(c, "notification_cancel_execution", workspace=old_row["workspace"],
            notification_id=old_row["id"], revision=old_row["revision"])["accepted"]
        assert c.snapshot()["executions"] == executions_before
        assert c.snapshot()["tasks"][0] == task_after_scan
    center = select(owner, next_row)
    if dismiss_first:
        center.dismiss_button.click()
        spin(lambda: next(n for n in c.snapshot()["notifications"] if n["id"] == next_row["id"])["state"] == "handled")
        center.refresh()
        assert not center.snooze_button.isEnabled()
    assert center.stop_button.isEnabled()
    center.stop_button.click()
    assert c.snapshot()["tasks"][0]["enabled"]
    assert center.confirmation is not None
    next(b for b in center.confirmation.buttons() if b.text() == "停止整个安排").click()
    spin(lambda: not c.snapshot()["tasks"][0]["enabled"])
    assert c.snapshot()["tasks"][0]["id"] == task["id"]
    assert all(e["status"] == "cancelled" for e in c.snapshot()["executions"])
    assert not inputs
