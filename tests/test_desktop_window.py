import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import socket
import sys
import threading
import time
from contextvars import ContextVar
from pathlib import Path

import pytest
pytest.importorskip("PySide6", reason="install the optional desktop extra for GUI tests")
from PySide6.QtWidgets import QApplication, QPushButton, QComboBox, QLineEdit
from PySide6.QtCore import QTimer
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
        # Pumping Qt alone can monopolize the GIL in PySide on Windows. Let
        # the real asyncio worker advance as it would under QApplication.exec.
        time.sleep(0.001)
    raise AssertionError("Qt condition timed out")


def test_spin_advances_qt_events_and_background_python(qtapp):
    ready, gate, finished = threading.Event(), threading.Event(), threading.Event()

    def worker():
        ready.set()
        gate.wait()
        finished.set()

    thread = threading.Thread(target=worker)
    thread.start()
    interval = sys.getswitchinterval()
    try:
        assert ready.wait(1)
        # Make incidental interpreter switching unavailable within the deadline:
        # the Qt wait must explicitly give the Python worker a chance to run.
        sys.setswitchinterval(2)
        QTimer.singleShot(0, gate.set)
        spin(lambda: gate.is_set() and finished.is_set(), timeout=0.5)
    finally:
        sys.setswitchinterval(interval)
        gate.set()
        thread.join(timeout=1)
    assert not thread.is_alive()


@pytest.fixture
def offline_socket_guard(monkeypatch):
    blocked = []
    in_socketpair = ContextVar("in_socketpair", default=False)
    socketpair = socket.socketpair

    def local_socketpair(*args, **kwargs):
        token = in_socketpair.set(True)
        try:
            return socketpair(*args, **kwargs)
        finally:
            in_socketpair.reset(token)

    def guard(connect):
        def checked(sock, address):
            # Windows asyncio uses a TCP loopback pair to wake its own event loop.
            if (in_socketpair.get() and isinstance(address, tuple) and address
                    and address[0] in ("127.0.0.1", "::1")):
                return connect(sock, address)
            blocked.append(address)
            raise AssertionError(f"offline demo attempted network: {address!r}")
        return checked

    monkeypatch.setattr(socket, "socketpair", local_socketpair)
    monkeypatch.setattr(socket.socket, "connect", guard(socket.socket.connect))
    monkeypatch.setattr(socket.socket, "connect_ex", guard(socket.socket.connect_ex))
    return blocked


def test_offline_socket_guard_only_allows_internal_pair(offline_socket_guard):
    sender, receiver = socket.socketpair()
    with sender, receiver:
        sender.sendall(b"x")
        assert receiver.recv(1) == b"x"

    with socket.socket() as sock:
        for connect in (sock.connect, sock.connect_ex):
            for address in (("127.0.0.1", 1), ("192.0.2.1", 1)):
                with pytest.raises(AssertionError, match="offline demo attempted network"):
                    connect(address)
    assert len(offline_socket_guard) == 4


@pytest.mark.parametrize("allow", [True, False])
def test_gui_permission_question_hidden_resume_and_no_duplicate_execution(qtapp, allow, offline_socket_guard):
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
        # Tool results now live in the expandable audit view, still literal.
        assert "<b>literal</b>" in w.technical.toPlainText()
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
    assert not offline_socket_guard


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


def test_stale_idle_send_preserves_rejected_draft(qtapp):
    from test_desktop_controller import command, wait

    c = DesktopController(DesktopOptions(demo=True))
    w = ChatWindow(c, DesktopOptions(demo=True))
    w.timer.stop()
    try:
        wait(c, lambda s: s["state"] == "idle")
        w.refresh()
        command(c, "send", text="already running")
        wait(c, lambda s: s["state"] == "waiting")
        w.input.setPlainText("keep this draft")
        w.send()
        wait(c, lambda s: not s["command"]["accepted"])
        w.refresh()
        assert w.input.toPlainText() == "keep this draft"
    finally:
        c.request_close()
        assert c.wait_closed()
        w.deleteLater()


def test_materials_profile_finishes_while_window_hidden_and_shows_verified_file(qtapp, tmp_path, monkeypatch):
    from test_desktop_controller import command, reply, wait
    from examples.deskmate_materials import fixture_resolver, fixture_transport, StudyClient, PAGES, OUTPUT
    from likecc.affairs import install_materials_profile
    from likecc.config import AppConfig, ProviderConfig
    from likecc.desktop import controller
    from likecc.runtime import Runtime

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "project_notes.md").write_text("study notes", encoding="utf-8")
    provider = ProviderConfig("fake-r4", "anthropic", "http://unused.invalid", "fake", api_key="offline-placeholder")
    connections = []

    def transport():
        connections.append(True)
        return fixture_transport()

    monkeypatch.setattr(controller, "load_config", lambda **_: AppConfig([provider]))
    monkeypatch.setattr(controller, "install_materials_profile", lambda runtime: install_materials_profile(
        runtime, resolver=fixture_resolver, transport_factory=transport))

    def runtime_factory(**kwargs):
        return Runtime(**{**kwargs, "client_factory": lambda _: StudyClient(), "user_home": tmp_path / "home"})

    options = DesktopOptions(work_dir=str(workspace))
    c = DesktopController(options, runtime_factory=runtime_factory)
    w = ChatWindow(c, options)
    w.show()
    try:
        spin(lambda: w.send_button.isEnabled())
        assert "资料整理" in w.banner.text() and "Markdown" in w.input.placeholderText()
        w.input.setPlainText(f"整理 project_notes.md、{PAGES[0]} 和 {PAGES[1]} 到 {OUTPUT}")
        w.send_button.click()
        for url in PAGES:
            wait(c, lambda s: s["pending"] and s["pending"][0]["description"] == url)
            w.refresh()
            button = w.findChild(QPushButton, "allow")
            assert button.isEnabled()
            button.click()
        permission = wait(c, lambda s: s["pending"] and s["pending"][0]["tool_name"] == "WriteFile")
        assert not permission["materials"]["artifacts"]
        w.hide()
        assert reply(c, "allow")["accepted"]
        wait(c, lambda s: s.get("last_status") == "completed")
        artifact = workspace / OUTPUT
        contents = artifact.read_bytes()
        mtime = artifact.stat().st_mtime_ns
        w.show()
        w.refresh()
        assert "已回读核对" in w.materials_summary.text()
        assert all(source in w.materials_summary.text() for source in PAGES)
        session = c.snapshot()["session_id"]
        assert command(c, "new")["accepted"]
        assert command(c, "resume", session_id=session)["accepted"]
        assert len(connections) == 2 and artifact.read_bytes() == contents and artifact.stat().st_mtime_ns == mtime
    finally:
        c.request_close()
        assert c.wait_closed()
        w.deleteLater()


@pytest.mark.parametrize("edit", [False, True])
def test_single_send_consumes_its_receipt_even_with_later_ack(qtapp, edit):
    from test_desktop_controller import wait

    c = DesktopController(DesktopOptions(demo=True))
    w = ChatWindow(c, DesktopOptions(demo=True))
    w.timer.stop()
    try:
        wait(c, lambda s: s["state"] == "idle")
        w.refresh()
        w.input.setPlainText("first draft")
        w.send()
        w.send()
        assert not w.send_button.isEnabled()
        if edit:
            w.input.setPlainText("new version")
        wait(c, lambda s: s["state"] == "waiting")
        later = c.submit_ui("new")
        wait(c, lambda s: s["command"]["id"] == later)
        w.refresh()
        assert w.input.toPlainText() == ("new version" if edit else "")
        assert sum(r["kind"] == "user" for r in c.snapshot()["rows"]) == 1
        assert "未接受" in w.feedback.text()
        assert c.take_receipts() == []
    finally:
        c.request_close()
        assert c.wait_closed()
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
