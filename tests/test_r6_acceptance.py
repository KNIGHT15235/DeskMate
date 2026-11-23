"""One complete offline acceptance through normal Qt controls and real storage."""
import json
from datetime import timedelta

import pytest
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QPushButton

from examples.deskmate_memories import prepare, controller, seed_review
from likecc.scheduling import ScheduleStore
from likecc.desktop.controller import DesktopOptions
from likecc.desktop.window import ChatWindow
from test_desktop_window import qtapp, spin, offline_socket_guard
from test_desktop_memory import dispose
from test_desktop_controller import wait, close
from test_scheduling import Clock


def test_visible_review_fixture_is_repeatable_and_blocked(tmp_path):
    root = prepare(tmp_path)
    seed_review(root)
    seed_review(root)
    store = ScheduleStore(root / "A")
    try:
        assert len(store.tasks()) == 1
        assert {e["status"] for e in store.executions()} == {"completed", "interrupted", "blocked_review"}
        assert len(store.executions()) == 3
        assert not (root / "model-inputs.jsonl").exists()
    finally:
        store.close()


def test_complete_r6_desktop_journey(qtapp, tmp_path, offline_socket_guard):
    root = prepare(tmp_path)
    clock, inputs, controllers, windows = Clock(), [], [], []

    def open_window():
        c = controller(DesktopOptions(work_dir=str(root / "A")), root, inputs=inputs, clock=clock)
        controllers.append(c)
        wait(c, lambda s: s["state"] == "idle")
        w = ChatWindow(c, DesktopOptions(work_dir=str(root / "A")))
        windows.append(w)
        w.show()
        return c, w

    def new_session(c, w):
        sid = c.snapshot()["session_id"]
        w.new_button.click()
        spin(lambda: c.snapshot()["session_id"] != sid)
        w.refresh()

    def run_task(c, w, prompt):
        start = len(inputs)
        w.refresh()
        spin(lambda: w.send_button.isEnabled())
        w.input.setPlainText(prompt)
        w.send_button.click()
        spin(lambda: len(inputs) > start)
        def finished():
            button = w.request_area.findChild(QPushButton, "allow")
            if button and button.isEnabled():
                button.click()
            return c.snapshot()["state"] == "idle" and w._draft is None
        spin(finished, timeout=20)
        w.refresh()
        return inputs[start:]

    def text(records):
        return json.dumps(records, ensure_ascii=False)

    def confirm(c, manager):
        spin(lambda: manager.confirm.isEnabled())
        mid = manager.listing.currentData()
        manager.confirm.click()
        spin(lambda: any(m["id"] == mid and m["status"] == "confirmed" for m in c.snapshot()["memories"]))
        spin(lambda: manager.update.isEnabled())
        return mid

    try:
        c, w = open_window()
        original = "我的周报按结论、依据、行动项排列"
        updated = "我的周报按行动项、依据、结论排列"
        w.input.setPlainText("请记住，" + original)
        w.send_button.click()
        spin(lambda: w.memory_window is not None)
        manager = w.memory_window
        mid = confirm(c, manager)
        spin(lambda: original in manager.source.toPlainText())
        original_source = c.snapshot()["memory_details"]["source"]
        assert original_source["session_id"] == c.snapshot()["session_id"]
        assert inputs == []  # remember + confirmation are entirely local

        # Save an original, confirmed scheduled task using the actual task form.
        w.show_schedules()
        schedule = w.schedule_window
        schedule.kind.setCurrentIndex(schedule.kind.findData("execute"))
        schedule.repeat.setCurrentIndex(schedule.repeat.findData("weekly"))
        schedule.timezone.setCurrentText("UTC")
        schedule.local_at.setText((clock() + timedelta(hours=1)).replace(tzinfo=None).isoformat())
        schedule.content.setPlainText("整理周报")
        schedule.files.setPlainText("project_notes.md")
        schedule.outputs.setPlainText("outputs/weekly-summary.md")
        schedule.preview_button.click()
        spin(lambda: schedule.confirm.isEnabled())
        schedule.confirm.click()
        spin(lambda: len(c.snapshot()["tasks"]) == 1)
        saved_spec = c.snapshot()["tasks"][0]["spec"]
        close(c)
        dispose(w)
        windows.remove(w)

        c, w = open_window()
        new_session(c, w)
        assert original in text(run_task(c, w, "请整理周报"))
        w.refresh()
        assert original in w.memory_summary.text()
        assert c.snapshot()["recalled_memories"][0]["source"]["id"] == original_source["id"]
        new_session(c, w)
        assert original not in text(run_task(c, w, "旅行天气"))
        assert c.snapshot()["recalled_memories"] == []

        w.show_memories()
        manager = w.memory_window
        spin(lambda: manager.update.isEnabled())
        manager.content.setPlainText(updated)
        manager.update.click()
        spin(lambda: c.snapshot()["memories"][0]["revision"] == 3)
        new_session(c, w)
        captured = text(run_task(c, w, "整理周报"))
        assert updated in captured and original not in captured

        # Check B while A still has a confirmed memory: isolation is non-vacuous.
        w.workspace.setText(str(root / "B"))
        w.open_button.click()
        spin(lambda: c.snapshot()["workspace"] == str(root / "B") and c.snapshot()["state"] == "idle")
        assert c.snapshot()["memories"] == []
        assert updated not in text(run_task(c, w, "整理周报"))
        w.workspace.setText(str(root / "A"))
        w.open_button.click()
        spin(lambda: c.snapshot()["workspace"] == str(root / "A") and c.snapshot()["state"] == "idle")
        assert c.snapshot()["tasks"][0]["spec"] == saved_spec
        assert c.snapshot()["memories"][0]["content"] == updated

        # Run the original task while A's confirmed preference still exists.
        clock.advance(hours=2)
        spin(lambda: len(c.snapshot()["executions"]) == 1)
        w.show_schedules()
        schedule = w.schedule_window
        spin(lambda: schedule.allow_model.isEnabled())
        first = len(inputs)
        schedule.allow_model.click()
        def scheduled_done():
            button = w.request_area.findChild(QPushButton, "allow")
            if button and button.isEnabled():
                button.click()
            return c.snapshot()["executions"][0]["status"] == "completed" and c.snapshot()["state"] == "idle"
        spin(scheduled_done, timeout=20)
        w.refresh()
        assert len(inputs) > first and updated not in text(inputs[first:])
        execution = c.snapshot()["executions"][0]
        assert execution["snapshot"]["files"] == saved_spec["files"]
        assert execution["snapshot"]["outputs"] == saved_spec["outputs"]
        assert execution["evidence"]["artifacts"] == [{"path": "outputs/weekly-summary.md", "status": "verified"}]

        manager.refresh()
        spin(lambda: manager._selection == (mid, 3))
        manager.delete.click()
        spin(lambda: not c.snapshot()["memories"])
        new_session(c, w)
        captured = text(run_task(c, w, "整理周报"))
        assert updated not in captured and original not in captured

        # Two runs in the SAME conversation both start their material ledger at S1.
        sources = []
        for name, path in (("一", "a"), ("二", "b")):
            run_task(c, w, "整理资料" + name)
            manager.refresh()
            manager.new.click()
            manager.content.setPlainText("事务" + name + "的资料与成果关联")
            spin(lambda: manager.link_run.isEnabled())
            manager.link_run.click()
            spin(lambda: any(m["status"] == "pending" for m in c.snapshot()["memories"]))
            association = confirm(c, manager)
            spin(lambda: c.snapshot()["memory_details"] is not None and
                 c.snapshot()["memory_details"]["memory"]["id"] == association)
            src = c.snapshot()["memory_details"]["source"]
            sources.append(src)
            assert src["evidence"]["sources"][0]["id"] == "S1"
            assert src["evidence"]["sources"][0]["target"] == f"source-{path}.md"
            assert src["evidence"]["artifacts"] == [{"path": f"outputs/{path}.md", "status": "verified"}]
            assert src["evidence"]["digests"][f"outputs/{path}.md"]
        assert sources[0]["session_id"] == sources[1]["session_id"]
        assert sources[0]["run_id"] != sources[1]["run_id"]
        assert sources[0]["evidence"]["sources"][0]["key"] != sources[1]["evidence"]["sources"][0]["key"]
        calls, memories = len(inputs), c.snapshot()["memories"]
        artifacts = {p.name: p.read_bytes() for p in (root / "A/outputs").glob("*.md")}
        manager.resume.click()
        spin(lambda: c.snapshot()["session_id"] == sources[1]["session_id"])
        assert c.snapshot()["memories"] == memories and len(inputs) == calls
        assert {p.name: p.read_bytes() for p in (root / "A/outputs").glob("*.md")} == artifacts
        close(c)
        reopened, _ = open_window()
        assert reopened.snapshot()["memories"] == memories
        assert len(inputs) == calls and offline_socket_guard == []
        assert len((root / "model-inputs.jsonl").read_text(encoding="utf-8").splitlines()) == calls
    finally:
        for c in controllers:
            if c.is_alive:
                close(c)
        for w in windows:
            dispose(w)
