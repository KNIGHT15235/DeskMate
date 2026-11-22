import pytest
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QPushButton

from likecc.desktop.controller import DesktopOptions
from likecc.desktop.window import ChatWindow
from test_desktop_window import qtapp, spin
from test_desktop_scheduling import desktop, arrange, execute_spec
from test_desktop_controller import command, close


def test_desktop_reminder_edit_hidden_due_reopen_complete(qtapp, desktop):
    make, clock, _, _ = desktop
    c = make()
    window = ChatWindow(c, DesktopOptions())
    window.show()
    try:
        window.input.setPlainText("明天晚上七点提醒我复习这份计划")
        window.send_button.click()
        spin(lambda: window.schedule_window is not None)
        manager = window.schedule_window
        spin(lambda: manager.confirm.isEnabled())
        assert "Asia/Shanghai" in manager.preview_text.toPlainText()
        assert "19:00:00" in manager.preview_text.toPlainText()
        manager.confirm.click()
        spin(lambda: len(c.snapshot()["tasks"]) == 1 and not c.snapshot()["schedule_draft"])
        manager.refresh()
        manager.load_selected()
        manager.content.setPlainText("复习修改后的计划")
        manager.local_at.setText("2026-11-21T20:00:00")
        manager.preview_button.click()
        spin(lambda: bool(c.snapshot()["schedule_draft"]))
        manager.refresh()
        manager.confirm.click()
        spin(lambda: c.snapshot()["tasks"][0]["revision"] == 2)
        window.input.setPlainText("尚未发送的草稿")
        manager.hide()
        window.hide()
        clock.advance(days=2)
        command(c, "schedule_scan")
        spin(lambda: len(c.snapshot()["executions"]) == 1)
        assert c.snapshot()["executions"][0]["status"] == "pending"
        assert window.input.toPlainText() == "尚未发送的草稿"
        close(c)
    finally:
        window.timer.stop()
        if window.schedule_window:
            window.schedule_window.timer.stop()
        window.hide()
        window.deleteLater()
    reopened = make()
    second = ChatWindow(reopened, DesktopOptions())
    try:
        second.show_schedules()
        manager = second.schedule_window
        assert manager.complete.isEnabled()
        assert "复习修改后的计划" in manager.details.toPlainText()
        manager.complete.click()
        spin(lambda: reopened.snapshot()["executions"][0]["status"] == "done")
        command(reopened, "schedule_scan")
        assert len(reopened.snapshot()["executions"]) == 1
    finally:
        second.timer.stop()
        manager.timer.stop()
        second.hide()
        manager.hide()
        second.deleteLater()


def test_scheduled_r4_question_permission_cards_preserve_draft(qtapp, desktop):
    make, clock, _, _ = desktop
    c = make()
    arrange(c, execute_spec(clock, model_policy="allow"))
    window = ChatWindow(c, DesktopOptions())
    window.show()
    try:
        window.input.setPlainText("前台未发送草稿")
        clock.advance(hours=2)
        command(c, "schedule_scan")
        spin(lambda: window.request_area.findChild(QPushButton, "answer") is not None)
        window.request_area.findChild(QPushButton, "answer").click()
        spin(lambda: window.request_area.findChild(QPushButton, "allow") is not None)
        window.request_area.findChild(QPushButton, "allow").click()
        spin(lambda: c.snapshot()["state"] == "idle" and c.snapshot()["executions"][0]["status"] == "completed")
        assert window.input.toPlainText() == "前台未发送草稿"
        window.show_schedules()
        assert "已回读核对" in window.schedule_window.details.toPlainText()
    finally:
        window.timer.stop()
        if window.schedule_window:
            window.schedule_window.timer.stop()
            window.schedule_window.hide()
        window.hide()
        window.deleteLater()
