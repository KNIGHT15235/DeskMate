import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
pytest.importorskip("PySide6", reason="optional desktop extra")
from PySide6.QtCore import QObject, Signal, QPoint, QRect
from PySide6.QtTest import QTest
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


@pytest.mark.parametrize("phase", ["startup", "restore"])
def test_offscreen_window_becomes_reachable_without_losing_draft(monkeypatch, phase):
    from likecc.desktop import application

    app = QApplication.instance() or QApplication([])
    available = app.primaryScreen().availableGeometry()
    original_window = application.ChatWindow

    def displace(window):
        window.resize(available.width() + 100, available.height() + 100)
        window.move(available.topLeft() - QPoint(300, 180))

    def make_window(*args):
        window = original_window(*args)
        window.input.setPlainText("保留未发送草稿")
        if phase == "startup":
            displace(window)
        return window

    monkeypatch.setattr(application, "ChatWindow", make_window)
    options = DesktopOptions(demo=True)
    c = DesktopController(options)
    owner = None
    try:
        owner = DesktopApplication(app, c, options, tray_probe=lambda: True,
                                   tray_factory=FakeTray, quit_callback=lambda: None)
        spin(lambda: c.snapshot()["state"] == "idle")
        session = c.snapshot()["session_id"]
        if phase == "restore":
            displace(owner.window)
            owner.close_window()
            assert not owner.window.isVisible()
            owner.show_window()
        QTest.qWait(30)
        assert available.contains(owner.window.frameGeometry())
        assert owner.window.input.toPlainText() == "保留未发送草稿"
        assert c.snapshot()["session_id"] == session
        assert c.snapshot()["state"] == "idle"
        assert not c.snapshot()["tasks"] and not c.snapshot()["executions"]
    finally:
        c.request_close()
        spin(lambda: not c.is_alive)
        if owner is not None:
            owner.dispose()


def test_restore_preserves_reachable_negative_monitor_position(lifecycle, monkeypatch):
    from types import SimpleNamespace

    owner, _, _, _ = lifecycle
    # A display to the left of the primary has legitimate negative coordinates.
    area = QRect(-1600, -200, 1600, 1200)
    left = SimpleNamespace(availableGeometry=lambda: area)
    monkeypatch.setattr(owner.app, "screens", lambda: [left, owner.app.primaryScreen()])
    owner.window.resize(900, 780)
    owner.window.move(-1500, -100)
    before = owner.window.frameGeometry()
    assert area.contains(before)
    owner.close_window()
    owner.show_window()
    QTest.qWait(30)
    after = owner.window.frameGeometry()
    assert area.contains(after)
    assert after.size() == before.size()
    # The offscreen Qt plugin shifts the native frame by its two-pixel border on show.
    assert (after.topLeft() - before.topLeft()).manhattanLength() <= 8


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


def test_slow_cleanup_keeps_gui_responsive_and_reports_timeout(monkeypatch):
    import asyncio
    import threading
    from types import SimpleNamespace
    from likecc.desktop import application
    from likecc.runtime import Runtime
    app = QApplication.instance() or QApplication([])
    now = [10.0]
    monkeypatch.setattr(application, "time", SimpleNamespace(monotonic=lambda: now[0]))
    dispatch_close = threading.Event()
    release, entered = threading.Event(), threading.Event()

    class DelayedCloseController(DesktopController):
        async def _dispatch(self, command_id, command, data):
            if command == "close":
                while not dispatch_close.is_set():
                    await asyncio.sleep(0.01)
            await super()._dispatch(command_id, command, data)

    class SlowRuntime(Runtime):
        async def _close(self):
            entered.set()
            while not release.is_set():
                await asyncio.sleep(0.01)
            await super()._close()
    c = DelayedCloseController(DesktopOptions(demo=True), runtime_factory=SlowRuntime)
    quit_calls = []
    available = [True]
    owner = DesktopApplication(app, c, DesktopOptions(demo=True), tray_probe=lambda: available[0],
        tray_factory=FakeTray, quit_callback=lambda: quit_calls.append(True))
    try:
        owner.timer.stop()
        owner.window.timer.stop()
        spin(lambda: c.snapshot()["state"] == "idle")
        owner.window.close()
        assert not owner.window.isVisible()
        owner.request_exit()
        now[0] += 16
        owner.poll()
        warning = owner.window.feedback.text()
        assert "尚未完成关闭" in warning
        assert c.snapshot()["command"] is None

        dispatch_close.set()
        spin(lambda: entered.is_set())
        assert c.snapshot()["command"]["accepted"]
        late = c.submit_ui("new")
        spin(lambda: c.snapshot()["command"]["id"] == late)
        owner.window.refresh()
        assert owner.window.feedback.text() == warning
        available[0] = False
        owner.poll()
        assert c.is_alive and not quit_calls
        assert owner.window.feedback.text() == warning
        assert owner.window.isVisible()
        assert not owner.window.send_button.isEnabled()
    finally:
        c.request_close()
        dispatch_close.set()
        release.set()
        spin(lambda: not c.is_alive)
        owner.poll()
        owner.dispose()
    assert quit_calls == [True]
