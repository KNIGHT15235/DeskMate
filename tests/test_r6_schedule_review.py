"""R6-0: review belongs to one execution, including real Qt retry clicks."""
import pytest
pytest.importorskip("PySide6")

from likecc.desktop.controller import DesktopOptions
from likecc.desktop.window import ChatWindow
from likecc.scheduling import ScheduleStore
from test_desktop_window import qtapp, spin
from test_desktop_scheduling import desktop, execute_spec, arrange
from test_desktop_controller import command, wait, close


def test_review_switch_refresh_retry_and_outstanding(qtapp, desktop, tmp_path):
    make, clock, clients, behavior = desktop
    behavior["mode"] = "text_only"
    initial = make()
    arrange(initial, execute_spec(clock))
    close(initial)
    store = ScheduleStore(tmp_path, clock=clock)
    clock.advance(hours=2)
    store.scan()
    a = store.executions()[0]["id"]
    store.update(a, status="completed")
    clock.advance(days=7)
    store.scan()
    b = store.executions()[0]["id"]
    store.update(b, status="interrupted", evidence={"write_intents": {
        "outputs/weekly-summary.md": {"status": "write_unverified"}}})
    store.close()
    c = make()
    w = ChatWindow(c, DesktopOptions())
    w.show_schedules()
    manager = w.schedule_window
    try:
        manager.executions.setCurrentIndex(manager.executions.findData(a))
        manager.reviewed.click()
        assert manager.retry.isEnabled()
        manager.executions.setCurrentIndex(manager.executions.findData(b))
        assert not manager.reviewed.isChecked()
        assert not manager.retry.isEnabled()
        manager.retry.click()
        assert not any(e["retry_of"] for e in c.snapshot()["executions"])
        # A stale receipt for A must not authorize retrying B either.
        assert not command(c, "schedule_retry", execution_id=b, reviewed=True,
                           reviewed_execution_id=a)["accepted"]
        clock.advance(days=7)
        command(c, "schedule_scan")
        assert any(e["status"] == "blocked_review" for e in c.snapshot()["executions"])
        manager.refresh()
        assert manager.executions.currentData() == b
        assert not manager.reviewed.isChecked()
        manager.reviewed.click()
        manager.show_executions()  # rebuilding the same selection preserves its review
        assert manager.reviewed.isChecked() and manager.retry.isEnabled()
        manager.retry.click()
        spin(lambda: any(e["retry_of"] == b for e in c.snapshot()["executions"]))
        retried = next(e for e in c.snapshot()["executions"] if e["retry_of"] == b)
        command(c, "schedule_allow_model", execution_id=retried["id"])
        command(c, "schedule_scan")
        wait(c, lambda s: s["state"] == "idle" and any(
            e["id"] == retried["id"] and e["status"] == "completed" for e in s["executions"]))
        old = next(e for e in c.snapshot()["executions"] if e["id"] == b)
        assert old["status"] == "interrupted" and old["reviewed_at"]
        assert old["label"] == "已中断，已核对"
        w.refresh()
        assert "0 项待处理/确认" in w.task_button.text()
        # The next real occurrence still needs its model decision.
        clock.advance(days=7)
        command(c, "schedule_scan")
        w.refresh()
        assert "1 项待处理/确认" in w.task_button.text()
    finally:
        w.timer.stop()
        manager.timer.stop()
        manager.hide()
        w.hide()
        w.deleteLater()
