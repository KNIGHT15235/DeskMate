import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
pytest.importorskip("PySide6", reason="optional desktop extra")
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from likecc.desktop.application import DesktopApplication
from likecc.desktop.controller import DesktopController, DesktopOptions
from test_desktop_window import spin


class FakeTray(QObject):
    activated = Signal(object)
    def __init__(self, icon, parent):
        super().__init__(parent)
        self.messages = []
        self.visible = False
    def setContextMenu(self, menu):
        self.menu = menu
    def setToolTip(self, text):
        self.tooltip = text
    def show(self):
        self.visible = True
    def hide(self):
        self.visible = False
    def showMessage(self, title, message):
        self.messages.append((title, message))


@pytest.fixture
def lifecycle():
    app = QApplication.instance() or QApplication([])
    available = [True]
    quit_calls = []
    c = DesktopController(DesktopOptions(demo=True))
    owner = DesktopApplication(app, c, DesktopOptions(demo=True), tray_probe=lambda: available[0],
                               tray_factory=FakeTray, quit_callback=lambda: quit_calls.append(True))
    spin(lambda: c.snapshot()["state"] == "idle")
    spin(lambda: owner.window.send_button.isEnabled())
    yield owner, c, available, quit_calls
    owner.request_exit()
    spin(lambda: not c.is_alive)
    owner.poll()
    app.removeEventFilter(owner)
    owner.window.deleteLater()
    owner.deleteLater()


def test_hide_keeps_single_consumer_and_pending_mark_and_tray_loss_restores(lifecycle):
    owner, c, available, _ = lifecycle
    owner.window.input.setPlainText("hide while waiting")
    owner.window.send_button.click()
    owner.window.close()
    assert not owner.window.isVisible()
    spin(lambda: c.snapshot()["state"] == "waiting")
    owner.poll()
    run_id = c.snapshot()["run_id"]
    assert "待处理" in owner.show_action.text()
    count = len(owner.tray.messages)
    owner.poll()
    assert len(owner.tray.messages) == count
    owner.show_window()
    assert c.snapshot()["run_id"] == run_id
    assert c.snapshot()["state"] == "waiting"
    assert not owner.tray.messages[-1][0].startswith("允许")
    owner.window.close()
    available[0] = False
    owner.poll()
    assert owner.window.isVisible()
    assert not owner.tray.visible
    assert c.snapshot()["run_id"] == run_id


def test_no_tray_close_dialog_minimize_cancel_and_exit(lifecycle):
    owner, c, available, quit_calls = lifecycle
    available[0] = False
    owner.poll()
    owner.window.close()
    assert owner.window.isVisible() and owner._dialog is not None
    buttons = owner._dialog.buttons()
    next(b for b in buttons if b.text() == "取消关闭").click()
    spin(lambda: owner._dialog is None)
    assert owner.window.isVisible()
    owner.window.close()
    next(b for b in owner._dialog.buttons() if b.text() == "最小化").click()
    spin(lambda: owner._dialog is None)
    assert owner.window.isMinimized()
    owner.show_window()
    owner.window.close()
    next(b for b in owner._dialog.buttons() if b.text() == "退出应用").click()
    spin(lambda: not c.is_alive)
    owner.poll()
    owner.request_exit()
    owner.poll()
    assert quit_calls == [True]


def test_exit_while_permission_pending_and_late_commands_rejected(lifecycle):
    owner, c, _, quit_calls = lifecycle
    c.submit("send", text="exit pending")
    spin(lambda: bool(c.snapshot()["pending"]))
    owner.request_exit()
    owner.request_exit()
    c.submit("send", text="must not run")
    spin(lambda: not c.is_alive)
    owner.poll()
    assert c.snapshot()["state"] == "closed"
    assert c.snapshot()["last_status"] == "cancelled"
    assert not c.snapshot()["pending"]
    assert quit_calls == [True]


def test_slow_cleanup_keeps_gui_responsive_and_reports_timeout():
    import asyncio
    import threading
    from likecc.runtime import Runtime
    app = QApplication.instance() or QApplication([])
    release, entered = threading.Event(), threading.Event()
    class SlowRuntime(Runtime):
        async def _close(self):
            entered.set()
            while not release.is_set():
                await asyncio.sleep(0.01)
            await super()._close()
    c = DesktopController(DesktopOptions(demo=True), runtime_factory=SlowRuntime)
    quit_calls = []
    owner = DesktopApplication(app, c, DesktopOptions(demo=True), tray_probe=lambda: False,
        quit_callback=lambda: quit_calls.append(True), shutdown_warning_seconds=0)
    try:
        spin(lambda: c.snapshot()["state"] == "idle")
        owner.request_exit()
        spin(lambda: entered.is_set())
        owner.poll()
        assert c.is_alive and not quit_calls
        assert "尚未完成关闭" in owner.window.feedback.text()
        assert owner.window.isVisible()
        assert not owner.window.send_button.isEnabled() or c.snapshot()["state"] == "closing"
    finally:
        release.set()
        spin(lambda: not c.is_alive)
        owner.poll()
        app.removeEventFilter(owner)
        owner.window.deleteLater()
        owner.deleteLater()
    assert quit_calls == [True]
