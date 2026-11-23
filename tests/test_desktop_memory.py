"""Desktop memory commands and widgets use the real service, SQLite and sessions."""
import json
import sqlite3

import pytest
pytest.importorskip("PySide6")

from likecc.desktop.controller import DesktopOptions
from likecc.desktop.window import ChatWindow
from likecc.memory.workspace import WorkspaceMemory
from test_desktop_window import qtapp, spin
from test_desktop_scheduling import desktop
from test_desktop_controller import command, wait, close


def dispose(window):
    window.timer.stop()
    for child in (window.memory_window, window.schedule_window):
        if child:
            child.timer.stop()
            child.hide()
    window.hide()
    window.deleteLater()


def test_explicit_desktop_confirmation_management_and_history(qtapp, desktop, tmp_path):
    make, _, clients, _ = desktop
    c = make()
    w = ChatWindow(c, DesktopOptions())
    w.show()
    try:
        assert command(c, "send", text="普通聊天提到偏好，不等于请保存")["accepted"]
        wait(c, lambda s: s["state"] == "idle")
        assert c.snapshot()["memories"] == []
        count = sum(x.calls for x in clients)
        request = "请记住，我的周报按结论、依据、行动项排列"
        w.input.setPlainText(request)
        w.send_button.click()
        spin(lambda: w.memory_window is not None and len(c.snapshot()["memories"]) == 1)
        manager = w.memory_window
        spin(lambda: manager.confirm.isEnabled() and "session_id" in manager.source.toPlainText())
        pending = c.snapshot()["memories"][0]
        assert pending["status"] == "pending"
        assert request in manager.source.toPlainText()
        cursor = manager.source.textCursor()
        cursor.setPosition(30)
        manager.source.setTextCursor(cursor)
        manager.refresh()
        assert manager.source.textCursor().position() == 30
        assert sum(x.calls for x in clients) == count
        manager.confirm.click()
        spin(lambda: c.snapshot()["memories"][0]["status"] == "confirmed")
        sid = c.snapshot()["session_id"]
        spin(lambda: manager.update.isEnabled())
        manager.content.setPlainText("我的周报按行动项、依据、结论排列")
        manager.update.click()
        spin(lambda: c.snapshot()["memories"][0]["revision"] == 3)
        assert c.snapshot()["memories"][0]["id"] == pending["id"]
        spin(lambda: manager._selection == (pending["id"], 3) and manager.resume.isEnabled())
        manager.resume.click()
        spin(lambda: any(request in r["text"] for r in c.snapshot()["rows"]))
        assert len(c.snapshot()["memories"]) == 1 and sum(x.calls for x in clients) == count
        manager.delete.click()
        spin(lambda: not c.snapshot()["memories"])
        records = [json.loads(s) for s in (tmp_path / ".likecc/sessions" / f"{sid}.jsonl").read_text(encoding="utf-8").splitlines()]
        assert any(r["type"] == "memory_action" and r["content"]["action"] == "delete" for r in records)
        assert any(r["type"] == "user" and r["content"] == request for r in records)
        close(c)
        reopened = make()
        assert reopened.snapshot()["memories"] == []
        assert command(reopened, "resume", session_id=sid)["accepted"]
        assert reopened.snapshot()["memories"] == []
        assert sum(x.calls for x in clients) == count
    finally:
        dispose(w)


def test_source_failure_disables_link_until_a_new_run_is_captured(qtapp, desktop, monkeypatch):
    make, _, _, _ = desktop
    c = make()
    w = ChatWindow(c, DesktopOptions())
    w.show_memories()
    manager = w.memory_window
    original = WorkspaceMemory.record_source

    def fail_second(store, **kwargs):
        if kwargs["quote"] == "source B":
            raise sqlite3.OperationalError("injected source capture failure")
        return original(store, **kwargs)

    monkeypatch.setattr(WorkspaceMemory, "record_source", fail_second)
    try:
        command(c, "send", text="source A")
        wait(c, lambda s: s["state"] == "idle" and s["memory_source_available"])
        manager.refresh()
        assert manager.link_run.isEnabled()
        command(c, "send", text="source B")
        wait(c, lambda s: s["state"] == "idle" and s.get("last_status") == "failed")
        assert not command(c, "memory_propose", content="事务 B", kind="affair", from_run=True)["accepted"]
        manager.refresh()
        assert not manager.link_run.isEnabled()
        assert c.snapshot()["memories"] == []
        command(c, "send", text="source C")
        wait(c, lambda s: s["state"] == "idle" and s.get("last_status") == "completed" and s["memory_source_available"])
        manager.refresh()
        assert manager.link_run.isEnabled()
        manager.content.setPlainText("事务 C")
        manager.link_run.click()
        spin(lambda: bool(c.snapshot()["memories"]))
        row = c.snapshot()["memories"][0]
        command(c, "memory_view", memory_id=row["id"])
        assert c.snapshot()["memory_details"]["source"]["run_id"] == c.snapshot()["run_id"]
        assert c.snapshot()["memory_details"]["source"]["quote"] == "source C"
    finally:
        dispose(w)
