"""Window/tray policy and nonblocking application shutdown."""
import signal
import logging
import sys
import time

from PySide6.QtCore import QObject, QTimer, QEvent, Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QAction
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QMessageBox

from .controller import DesktopController
from .window import ChatWindow

log = logging.getLogger(__name__)
FALLBACK_SHUTDOWN_TIMEOUT = 5.0


def application_icon():
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setBrush(QColor("#245aa4"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(2, 2, 44, 44, 10, 10)
    painter.setPen(QColor("white"))
    font = painter.font()
    font.setPixelSize(30)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "D")
    painter.end()
    return QIcon(pixmap)


class DesktopApplication(QObject):
    def __init__(self, app, controller, options, *, tray_probe=None, tray_factory=None,
                 quit_callback=None, shutdown_warning_seconds=15):
        super().__init__(app)
        self.app, self.controller = app, controller
        self.tray_probe = tray_probe or QSystemTrayIcon.isSystemTrayAvailable
        self.tray_factory = tray_factory or QSystemTrayIcon
        self.quit_callback = quit_callback or app.quit
        self.shutdown_warning_seconds = shutdown_warning_seconds
        self.window = None
        self.timer = None
        self.tray = None
        self.tray_available = False
        self._first_hide = True
        self._notified = None
        self._closing_since = None
        self._quit_sent = False
        self._shutdown_warned = False
        self._dialog = None
        self._disposed = False
        try:
            self.window = ChatWindow(controller, options)
            self.window.lifecycle = self
            self.window.setWindowIcon(application_icon())
            app.setQuitOnLastWindowClosed(False)
            app.installEventFilter(self)
            self.timer = QTimer(self)
            self.timer.setInterval(100)
            self.timer.timeout.connect(self.poll)
            self.timer.start()
            self.poll()
            self.window.show()
        except BaseException as exc:
            try:
                self.dispose()
            except BaseException as cleanup_error:
                exc.add_note(f"Qt 初始化回收失败：{cleanup_error}")
            raise

    def _make_tray(self):
        self.tray = self.tray_factory(application_icon(), self)
        menu = QMenu()
        self.show_action = QAction("显示 DeskMate", menu)
        self.show_action.triggered.connect(self.show_window)
        cancel = QAction("取消当前请求", menu)
        cancel.triggered.connect(lambda: self.controller.submit("cancel"))
        leave = QAction("退出应用", menu)
        leave.triggered.connect(self.request_exit)
        for action in (self.show_action, cancel, leave):
            menu.addAction(action)
        self.tray_menu = menu
        self.tray.setContextMenu(menu)
        self.tray.setToolTip("DeskMate 桌伴")
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_activated(self, reason):
        if reason in {QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick}:
            self.show_window()

    def show_window(self):
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()
        self.window.refresh()

    @property
    def is_closing(self) -> bool:
        return self._closing_since is not None

    def close_window(self):
        if self.is_closing:
            return
        self.poll()  # check actual tray availability at the moment of close
        if self.tray_available:
            if self._first_hide:
                self._first_hide = False
                message = "窗口将隐藏到托盘，当前请求继续执行。可从托盘显示窗口或退出应用。"
                self.window.feedback.setText(message)
                self.tray.showMessage("DeskMate 继续运行", message)
            self.window.hide()
        else:
            if self._dialog is not None:
                self._dialog.raise_()
                return
            dialog = QMessageBox(self.window)
            dialog.setWindowTitle("系统托盘不可用")
            dialog.setText("请选择最小化以继续执行，或退出并清理资源。取消将保留窗口。")
            minimize = dialog.addButton("最小化", QMessageBox.ButtonRole.ActionRole)
            leave = dialog.addButton("退出应用", QMessageBox.ButtonRole.DestructiveRole)
            dialog.addButton("取消关闭", QMessageBox.ButtonRole.RejectRole)
            self._dialog = dialog
            def decided():
                clicked = dialog.clickedButton()
                self._dialog = None
                if clicked == minimize:
                    self.apply_close_choice("minimize")
                elif clicked == leave:
                    self.apply_close_choice("exit")
                dialog.deleteLater()
            dialog.finished.connect(decided)
            dialog.open()  # asynchronous; no nested blocking exec()

    def apply_close_choice(self, choice):
        if choice == "minimize":
            self.window.showMinimized()
        elif choice == "exit":
            self.request_exit()
        elif choice != "cancel":
            raise ValueError(choice)

    def request_exit(self):
        if not self.is_closing:
            self._closing_since = time.monotonic()
            self.controller.request_close()
            self.window.feedback.setText("正在取消当前请求并等待资源关闭；界面仍可响应。")

    def poll(self):
        available = bool(self.tray_probe())
        if available and self.tray is None:
            self._make_tray()
        if not available and self.tray_available:
            if self.tray:
                self.tray.hide()
            self.show_window()
            if not self.is_closing:
                self.window.feedback.setText("系统托盘已不可用，已恢复窗口。关闭时将提供最小化或退出。")
        elif available and not self.tray_available and self.tray:
            self.tray.show()
        self.tray_available = available
        snapshot = self.controller.snapshot()
        pending = snapshot["pending"]
        request_id = pending[0]["request_id"] if pending else None
        if self.tray:
            self.show_action.setText("显示 DeskMate · 待处理回复" if pending else "显示 DeskMate")
            self.tray.setToolTip("DeskMate · 等待你的回复" if pending else "DeskMate 桌伴")
            if pending and request_id != self._notified and not self.window.isVisible():
                self.tray.showMessage("DeskMate 等待回复", "请显示窗口处理权限或问答；未自动批准。")
                self._notified = request_id
        if self._closing_since is not None:
            if not self.controller.is_alive:
                self.timer.stop()
                self.window.timer.stop()
                if self.tray:
                    self.tray.hide()
                self.window.hide()
                if not self._quit_sent:
                    self._quit_sent = True
                    self.quit_callback()
            elif not self._shutdown_warned and time.monotonic() - self._closing_since > self.shutdown_warning_seconds:
                self._shutdown_warned = True
                self.show_window()
                self.window.feedback.setText("资源尚未完成关闭，仍在等待；未强制终止线程或伪装干净退出。")

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Quit and self.controller.is_alive:
            self.request_exit()
            return True
        return super().eventFilter(watched, event)

    def dispose(self):
        """Release Qt presentation after exec has ended; worker ownership is separate."""
        if self._disposed:
            return
        self._disposed = True
        if self.timer is not None:
            self.timer.stop()
        if self.window is not None:
            self.window.timer.stop()
        self.app.removeEventFilter(self)
        if self.tray:
            self.tray.hide()
        if self._dialog:
            self._dialog.reject()
        if self.window is not None:
            self.window.hide()
            self.window.deleteLater()
        self.deleteLater()


def launch(options):
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("DeskMate")
    controller = DesktopController(options)
    lifecycle = None
    previous = {}
    try:
        lifecycle = DesktopApplication(app, controller, options)
        for sig in (signal.SIGINT, signal.SIGTERM):
            original = signal.getsignal(sig)
            signal.signal(sig, lambda *_: lifecycle.request_exit())
            previous[sig] = original  # only restore successfully changed handlers
        return app.exec()
    finally:
        original_error = sys.exception()
        issues = []
        try:
            controller.request_close()
            # Qt has not started, or exec has returned/raised: no live Qt loop is
            # blocked here. Normal GUI exit already awaited the worker in poll().
            if not controller.wait_closed(FALLBACK_SHUTDOWN_TIMEOUT):
                issues.append("后台资源清理未完成，非 daemon 线程仍存活；未强制终止")
        except BaseException as exc:
            issues.append(f"后台关闭兜底失败：{type(exc).__name__}: {exc}")
        if lifecycle is not None:
            try:
                lifecycle.dispose()
            except BaseException as exc:
                issues.append(f"Qt 展示资源清理失败：{type(exc).__name__}: {exc}")
        for sig, handler in reversed(list(previous.items())):
            try:
                signal.signal(sig, handler)
            except BaseException as exc:
                issues.append(f"信号 {sig} 恢复失败：{type(exc).__name__}: {exc}")
        if issues:
            message = "; ".join(issues)
            log.error(message)
            if original_error is not None:
                original_error.add_note(message)
            else:
                raise RuntimeError(message)
