import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import threading
import time
from pathlib import Path

import pytest
pytest.importorskip("PySide6", reason="install the optional desktop extra for GUI tests")
from PySide6.QtWidgets import QApplication, QPushButton, QComboBox, QLineEdit
from PySide6.QtTest import QTest

from likecc.desktop.controller import DesktopController, DesktopOptions
from likecc.desktop.window import ChatWindow


@pytest.fixture(scope="module")
def qtapp():
    return QApplication.instance() or QApplication([])


def spin(predicate, timeout=6):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        QTest.qWait(10)
    raise AssertionError("Qt condition timed out")


@pytest.mark.parametrize("allow", [True, False])
def test_gui_permission_question_hidden_resume_and_no_duplicate_execution(qtapp, allow, monkeypatch):
    import socket
    def no_network(*args, **kwargs):
        raise AssertionError("offline demo attempted network")
    monkeypatch.setattr(socket.socket, "connect", no_network)
    c = DesktopController(DesktopOptions(demo=True))
    refresh_threads = set()
    class CheckedWindow(ChatWindow):
        def refresh(self):
            refresh_threads.add(threading.get_ident())
            super().refresh()
    w = CheckedWindow(c, DesktopOptions(demo=True))
    w.show()
    try:
        spin(lambda: w.send_button.isEnabled())
        workspace = Path(c.snapshot()["workspace"])
        w.input.setPlainText("<img src='https://invalid.example/image'> & literal")
        w.send_button.click()
        spin(lambda: bool(w.findChildren(QPushButton, "allow")))
        assert w.cancel_button.isEnabled()
        w.hide()
        w.show()
        w.findChild(QPushButton, "allow" if allow else "deny").click()
        spin(lambda: bool(w.findChildren(QPushButton, "answer")))
        assert (workspace / "demo.txt").exists() == allow
        w.findChild(QComboBox, "next").setCurrentText("完成")
        w.findChild(QLineEdit, "note").setText("<b>literal</b>")
        w.findChild(QPushButton, "answer").click()
        spin(lambda: c.snapshot()["state"] == "idle")
        w.refresh()
        assert "<img src=" in w.transcript.toPlainText()
        assert "<b>literal</b>" in w.transcript.toPlainText()
        assert sum("离线演示完成" in r["text"] for r in c.snapshot()["rows"]) == 1
        session = c.snapshot()["session_id"]
        w.new_button.click()
        spin(lambda: c.snapshot()["session_id"] != session)
        w.refresh()
        w.sessions.setCurrentIndex(w.sessions.findData(session))
        w.resume_button.click()
        spin(lambda: c.snapshot()["session_id"] == session)
        assert (workspace / "demo.txt").exists() == allow
        assert refresh_threads == {threading.get_ident()}
        assert c.snapshot()["worker_thread"] != threading.get_ident()
    finally:
        c.submit("close")
        spin(lambda: not c.is_alive)
        w.hide()
        w.deleteLater()


def test_gui_wait_cancel_remains_responsive_and_can_send_again(qtapp):
    c = DesktopController(DesktopOptions(demo=True))
    w = ChatWindow(c, DesktopOptions(demo=True))
    w.show()
    try:
        spin(lambda: w.send_button.isEnabled())
        w.input.setPlainText("wait")
        w.send_button.click()
        spin(lambda: bool(w.findChildren(QPushButton, "deny")))
        w.findChild(QPushButton, "deny").click()
        spin(lambda: bool(w.findChildren(QPushButton, "answer")))
        w.findChild(QComboBox, "next").setCurrentText("等待取消")
        w.findChild(QPushButton, "answer").click()
        spin(lambda: any(r["kind"] == "tool" and "DemoWait" in r["text"] for r in c.snapshot()["rows"]))
        w.cancel_button.click()
        spin(lambda: c.snapshot()["state"] == "idle")
        w.refresh()
        assert c.snapshot()["last_status"] == "cancelled"
        assert w.send_button.isEnabled()
        assert not w.request_area.isVisible()
    finally:
        c.submit("close")
        spin(lambda: not c.is_alive)
        w.hide()
        w.deleteLater()


def test_all_ask_schema_types_and_name_mapping(qtapp):
    from PySide6.QtWidgets import QCheckBox, QWidget
    from likecc.client import LLMClient
    from likecc.runtime import Runtime
    from likecc.tools.base import TextDelta, ToolCallComplete, StreamEnd
    class QuestionClient(LLMClient):
        def __init__(self):
            self.calls = 0
        async def stream(self, conversation, **kwargs):
            self.calls += 1
            if self.calls == 1:
                yield ToolCallComplete("questions", "AskUserQuestion", {"questions": [
                    {"name": kind, "type": kind, "message": "<b>plain</b>", "options": ["a", "b"]}
                    for kind in ("text", "radio", "select", "checkbox")
                ]})
                yield StreamEnd("tool_use")
            else:
                yield TextDelta("done")
                yield StreamEnd("end_turn")
    class QuestionRuntime(Runtime):
        def __init__(self, **kwargs):
            kwargs["client_factory"] = lambda _: QuestionClient()
            super().__init__(**kwargs)
    c = DesktopController(DesktopOptions(demo=True), runtime_factory=QuestionRuntime)
    w = ChatWindow(c, DesktopOptions(demo=True))
    w.show()
    try:
        spin(lambda: w.send_button.isEnabled())
        w.input.setPlainText("questions")
        w.send_button.click()
        spin(lambda: bool(w.findChildren(QPushButton, "answer")))
        w.findChild(QLineEdit, "text").setText("typed")
        w.findChild(QComboBox, "radio").setCurrentText("b")
        w.findChild(QComboBox, "select").setCurrentText("custom")
        for check in w.findChild(QWidget, "checkbox").findChildren(QCheckBox):
            check.setChecked(True)
        w.findChild(QPushButton, "answer").click()
        spin(lambda: c.snapshot()["state"] == "idle")
        text = "\n".join(r["text"] for r in c.snapshot()["rows"] if r["kind"] == "result")
        assert all(expected in text for expected in ("text: typed", "radio: b", "select: custom", "checkbox: a, b"))
    finally:
        c.submit("close")
        spin(lambda: not c.is_alive)
        w.hide()
        w.deleteLater()
