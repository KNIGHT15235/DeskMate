"""R8-A presentation regressions with real Qt, isolated SQLite and fake clients."""
from copy import deepcopy
from pathlib import Path

import pytest
pytest.importorskip("PySide6")
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QPushButton

from likecc.desktop.controller import DesktopOptions
from likecc.desktop.window import ChatWindow
from likecc.desktop.artifacts import read_artifact, MAX_PREVIEW_BYTES
from likecc.desktop.presentation import artifacts_text
from test_desktop_window import qtapp, spin, offline_socket_guard
from test_desktop_controller import command, wait
from test_desktop_scheduling import desktop
from test_r7_acceptance import journey, arrange, advance, note, navigate, answer, wait_request


def dispose(w):
    w.timer.stop()
    for page in (w.schedule_window, w.memory_window, w.notification_window):
        if page:
            page.timer.stop()
    w.hide()
    w.deleteLater()


def test_navigation_preserves_live_run_and_all_editor_drafts(journey):
    root, clock, inputs, open_app = journey
    owner, c = open_app()
    w = owner.window
    arrange(owner, clock, "R8 导航", ["outputs/navigation.md"])
    advance(c, clock, minutes=2)
    navigate(owner, note(c, "model"))
    w.schedule_window.allow_model.click()
    wait_request(c)
    w.refresh()
    pending = c.snapshot()["pending"][0]
    consumer = c._consumer
    count = len(inputs)
    w.input.setPlainText("还没发送的对话")
    w.schedule_window.content.setPlainText("还没保存的任务")
    w.show_memories()
    w.memory_window.content.setPlainText("还没保存的偏好")
    for name in ("settings", "notifications", "schedules", "memories", "chat") * 2:
        w.show_page(name)
        w.refresh()
    assert c._consumer is consumer
    assert c.snapshot()["pending"][0] == pending and len(inputs) == count
    assert w.input.toPlainText() == "还没发送的对话"
    assert w.schedule_window.content.toPlainText() == "还没保存的任务"
    assert w.memory_window.content.toPlainText() == "还没保存的偏好"
    assert all(not p.isWindow() for p in (w.schedule_window, w.memory_window, w.notification_window))
    assert not (root / "A/outputs/navigation.md").exists()
    navigate(owner, note(c, "request"))
    assert w.pages.currentWidget() is w.chat_page
    assert w.request_area.findChild(QPushButton, "allow").isVisible()
    answer(owner, "deny")
    spin(lambda: c.snapshot()["state"] == "idle")
    assert not (root / "A/outputs/navigation.md").exists()


def test_transcript_streaming_preserves_selection_scroll_and_noop_revision(qtapp, desktop):
    make, _, _, _ = desktop
    c = make()
    w = ChatWindow(c, DesktopOptions())
    w.timer.stop()
    w.show()
    try:
        state = c.snapshot()
        state["rows"] = [{"kind": "user", "text": "<b>literal</b>"},
                         {"kind": "assistant", "text": "line\n" * 180}]
        w.render_transcript(state)
        QApplication.processEvents()
        cursor = w.transcript.textCursor()
        cursor.setPosition(2)
        cursor.setPosition(15, QTextCursor.MoveMode.KeepAnchor)
        w.transcript.setTextCursor(cursor)
        bar = w.transcript.verticalScrollBar()
        bar.setValue(20)
        selected, position = cursor.selectedText(), bar.value()
        revision = w.transcript.document().revision()
        w.render_transcript(state)
        assert w.transcript.document().revision() == revision
        state["rows"][-1]["text"] += "new streamed text"
        w.render_transcript(state)
        assert w.transcript.textCursor().selectedText() == selected
        assert bar.value() == position
        assert "<b>literal</b>" in w.transcript.toPlainText()
        assert w.transcript.toPlainText().endswith("new streamed text")
    finally:
        dispose(w)


def test_workspace_handover_isolates_chat_and_manager_drafts(journey):
    root, _, _, open_app = journey
    owner, c = open_app()
    w = owner.window
    w.input.setPlainText("A 的对话草稿")
    w.show_schedules()
    w.schedule_window.content.setPlainText("A 的任务草稿")
    w.show_memories()
    w.memory_window.content.setPlainText("A 的记忆草稿")
    for workspace, expected in (("B", ""), ("A", "A 的对话草稿")):
        w.workspace.setText(str(root / workspace))
        w.open_workspace()
        spin(lambda: c.snapshot()["state"] == "idle" and c.snapshot()["workspace"] == str(root / workspace))
        w.refresh()
        assert w.input.toPlainText() == expected
        assert w.schedule_window.content.toPlainText() == ""
        assert w.memory_window.content.toPlainText() == ""
        assert not c.snapshot()["pending"]
        if workspace == "B":
            w.input.setPlainText("B 的对话草稿")
            assert not c.snapshot()["memories"] and not c.snapshot()["notifications"]


def test_handover_hides_old_audit_but_startup_error_remains_visible(qtapp, desktop):
    make, _, _, _ = desktop
    c = make()
    w = ChatWindow(c, DesktopOptions())
    w.timer.stop()
    original = c.snapshot()
    try:
        c._set(workspace="", state="starting", rows=[{"kind": "user", "text": "旧工作区内容"}])
        w.refresh()
        assert "旧工作区内容" not in w.transcript.toPlainText()
        assert "旧工作区内容" not in w.technical.toPlainText()
        c._set(state="error", rows=[{"kind": "user", "text": "旧工作区内容"},
            {"kind": "error", "text": "启动失败：请选择有效工作区"}])
        w.refresh()
        assert "请选择有效工作区" in w.transcript.toPlainText()
        assert "旧工作区内容" not in w.technical.toPlainText()
    finally:
        c._set(**{k: v for k, v in original.items() if k != "revision"})
        dispose(w)


@pytest.mark.parametrize("action", ["preview", "cancel"])
def test_schedule_commands_cannot_mutate_a_releasing_workspace(desktop, tmp_path, action):
    import asyncio
    from dataclasses import asdict
    from test_desktop_scheduling import arrange as save_schedule
    from test_scheduling import reminder
    make, clock, clients, _ = desktop
    c = make()
    task_id = save_schedule(c, reminder(clock))
    other = tmp_path / "B"
    other.mkdir()

    async def probe():
        original_release = c._release
        entered, proceed = asyncio.Event(), asyncio.Event()

        async def held_release():
            entered.set()
            await proceed.wait()
            await original_release()

        before = c._store.task(task_id)
        c._release = held_release
        opening = asyncio.create_task(c._open(DesktopOptions(work_dir=str(other))))
        try:
            await entered.wait()
            assert c.snapshot()["state"] == "starting" and c.snapshot()["workspace"] == ""
            await c._dispatch("handover-review", "schedule_" + action,
                              {"spec": asdict(reminder(clock)), "task_id": task_id, "revision": 1})
            result = c.snapshot()["command"], before, c._store.task(task_id)
        finally:
            c._release = original_release
            proceed.set()
            await opening
        return result

    receipt, before, after = asyncio.run_coroutine_threadsafe(probe(), c._loop).result(timeout=20)
    assert not receipt["accepted"]
    assert after == before
    assert c.snapshot()["workspace"] == str(other.resolve())
    assert not c.snapshot()["schedule_draft"] and not c.snapshot()["tasks"]
    assert all(client.calls == 0 for client in clients)


@pytest.mark.parametrize("page_name", ["chat", "schedules", "memories"])
def test_stale_page_submission_cannot_land_in_the_new_workspace(qtapp, desktop, tmp_path, page_name):
    make, _, clients, _ = desktop
    c = make()
    w = ChatWindow(c, DesktopOptions())
    w.timer.stop()
    w.show_page(page_name)
    if page_name == "schedules":
        page = w.schedule_window
        page.timer.stop()
        page.content.setPlainText("A 的任务草稿")
        submit = page.preview_button.click
    elif page_name == "memories":
        page = w.memory_window
        page.timer.stop()
        page.content.setPlainText("A 的偏好草稿")
        submit = page.propose.click
    else:
        w.input.setPlainText("A 的对话草稿")
        submit = w.send_button.click
    other = tmp_path / "B"
    other.mkdir()
    try:
        assert command(c, "open", work_dir=str(other))["accepted"]
        # The worker has switched, but Qt has not yet polled the new workspace.
        old_receipt = c.snapshot()["command"]["id"]
        submit()
        state = wait(c, lambda s: s["command"]["id"] != old_receipt)
        assert not state["command"]["accepted"]
        assert not state["tasks"] and not state["memories"] and not state["schedule_draft"]
        assert all(client.calls == 0 for client in clients)
    finally:
        dispose(w)


def test_schedule_preview_must_be_renewed_after_form_edit(qtapp, desktop):
    make, clock, _, _ = desktop
    c = make()
    w = ChatWindow(c, DesktopOptions())
    w.show()
    try:
        w.input.setPlainText("明天晚上七点提醒我复习")
        w.send_button.click()
        spin(lambda: w.schedule_window is not None and w.schedule_window.confirm.isEnabled())
        page = w.schedule_window
        assert page.editor.toggle.isChecked()
        assert not page.scope_panel.isVisible()
        page.content.setPlainText("复习修改后的计划")
        page.refresh()
        assert not page.confirm.isEnabled() and c.snapshot()["tasks"] == []
        page.preview_button.click()
        spin(lambda: page.confirm.isEnabled())
        page.confirm.click()
        spin(lambda: len(c.snapshot()["tasks"]) == 1)
        assert c.snapshot()["tasks"][0]["spec"]["content"] == "复习修改后的计划"
    finally:
        dispose(w)


def test_delayed_schedule_preview_preserves_newer_typing(qtapp, desktop, monkeypatch):
    import threading
    make, _, _, _ = desktop
    c = make()
    w = ChatWindow(c, DesktopOptions())
    entered, release = threading.Event(), threading.Event()
    original = c._prepare_schedule

    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(4)
        return original(*args, **kwargs)

    monkeypatch.setattr(c, "_prepare_schedule", delayed)
    try:
        w.show_schedules()
        page = w.schedule_window
        page.content.setPlainText("原来的安排")
        page.preview_button.click()
        spin(entered.is_set)
        page.content.setPlainText("刚输入的新草稿")
        release.set()
        spin(lambda: bool(c.snapshot()["schedule_draft"]))
        page.refresh()
        assert page.content.toPlainText() == "刚输入的新草稿"
        assert not page.confirm.isEnabled() and not c.snapshot()["tasks"]
    finally:
        release.set()
        dispose(w)


def test_queued_schedule_previews_cannot_restore_an_older_form(qtapp, desktop, monkeypatch):
    import threading
    make, _, _, _ = desktop
    c = make()
    w = ChatWindow(c, DesktopOptions())
    w.timer.stop()
    entered = [threading.Event(), threading.Event()]
    release = [threading.Event(), threading.Event()]
    original = c._prepare_schedule
    calls = []

    def delayed(*args, **kwargs):
        index = len(calls)
        calls.append(index)
        entered[index].set()
        assert release[index].wait(4)
        return original(*args, **kwargs)

    monkeypatch.setattr(c, "_prepare_schedule", delayed)
    try:
        w.show_schedules()
        page = w.schedule_window
        page.timer.stop()
        page.content.setPlainText("第一份安排")
        page.preview_button.click()
        spin(entered[0].is_set)
        page.content.setPlainText("第二份安排")
        page.preview_button.click()
        release[0].set()
        spin(entered[1].is_set)
        page.refresh()
        assert page.content.toPlainText() == "第二份安排"
        assert not page.confirm.isEnabled()
        release[1].set()
        spin(lambda: c.snapshot()["schedule_draft"]["spec"]["content"] == "第二份安排")
        page.refresh()
        assert page.content.toPlainText() == "第二份安排" and page.confirm.isEnabled()
        page.confirm.click()
        spin(lambda: len(c.snapshot()["tasks"]) == 1)
        assert c.snapshot()["tasks"][0]["spec"]["content"] == "第二份安排"
    finally:
        for gate in release:
            gate.set()
        dispose(w)


def test_artifact_selection_discards_displayed_and_inflight_old_contents(qtapp):
    from likecc.desktop.widgets import ArtifactPreview
    submitted = []

    def submit(command, **data):
        submitted.append((command, data))
        return str(len(submitted))

    preview = ArtifactPreview(submit)
    state = {"workspace": "isolated-workspace", "artifact_preview": None}
    artifacts = [{"path": "first.md"}, {"path": "second.md"}]
    try:
        preview.refresh(state, artifacts)
        preview.open_button.click()
        state["artifact_preview"] = {"token": "1", "workspace": state["workspace"], "text": "FIRST FILE"}
        preview.refresh(state, artifacts)
        assert preview.text.toPlainText() == "FIRST FILE"
        preview.paths.setCurrentIndex(1)
        preview.refresh(state, artifacts)
        assert "FIRST FILE" not in preview.text.toPlainText()
        preview.open_button.click()
        preview.paths.setCurrentIndex(0)
        state["artifact_preview"] = {"token": "2", "workspace": state["workspace"], "text": "SECOND FILE"}
        preview.refresh(state, artifacts)
        assert "SECOND FILE" not in preview.text.toPlainText()
        assert len(submitted) == 2  # Selection alone never reads a file.
    finally:
        preview.deleteLater()


def test_artifact_preview_uses_real_output_without_replay_or_evidence_change(journey):
    root, clock, inputs, open_app = journey
    owner, c = open_app()
    task = arrange(owner, clock, "R8 成果", ["outputs/preview.md"])
    advance(c, clock, minutes=2)
    navigate(owner, note(c, "model"))
    owner.window.schedule_window.allow_model.click()
    wait_request(c)
    answer(owner)
    spin(lambda: c.snapshot()["state"] == "idle" and c.snapshot()["executions"][0]["status"] == "completed")
    w = owner.window
    w.show_schedules()
    page = w.schedule_window
    evidence = deepcopy(c.snapshot()["executions"][0]["evidence"])
    calls = len(inputs)
    file = root / "A/outputs/preview.md"
    mtime = file.stat().st_mtime_ns
    page.artifact_preview.open_button.click()
    spin(lambda: "当前磁盘内容" in page.artifact_preview.text.toPlainText())
    assert file.read_text(encoding="utf-8") in page.artifact_preview.text.toPlainText()
    assert len(inputs) == calls and file.stat().st_mtime_ns == mtime
    assert c.snapshot()["executions"][0]["evidence"] == evidence
    assert not command(c, "artifact_preview", workspace=str(root / "B"), path="outputs/preview.md")["accepted"]
    assert not command(c, "artifact_preview", workspace=str(root / "A"), path="project_notes.md")["accepted"]
    assert len(inputs) == calls
    w.show_notifications()
    center = w.notification_window
    center.filter.setCurrentIndex(center.filter.findData("history"))
    center.refresh()
    assert any(r["kind"] == "completed" and r["valid"] for r in center._rows)


def test_execution_change_clears_preview_even_when_output_path_is_reused(qtapp, desktop, tmp_path):
    from likecc.scheduling import ScheduleStore
    from test_desktop_controller import close
    from test_desktop_scheduling import arrange as save_schedule, execute_spec
    make, clock, clients, _ = desktop
    initial = make()
    save_schedule(initial, execute_spec(clock))
    close(initial)
    path = "outputs/weekly-summary.md"
    store = ScheduleStore(tmp_path, clock=clock)
    executions = []
    try:
        for days in (0, 7):
            clock.advance(days=days, hours=2)
            store.scan()
            execution_id = store.executions()[0]["id"]
            executions.append(execution_id)
            store.update(execution_id, status="completed", evidence={
                "artifacts": [{"path": path, "status": "written"}]})
    finally:
        store.close()
    output = tmp_path / path
    output.parent.mkdir(exist_ok=True)
    output.write_text("FIRST CONTENT", encoding="utf-8")
    c = make()
    w = ChatWindow(c, DesktopOptions())
    w.show_schedules()
    page = w.schedule_window
    try:
        page.executions.setCurrentIndex(page.executions.findData(executions[0]))
        page.artifact_preview.open_button.click()
        spin(lambda: "FIRST CONTENT" in page.artifact_preview.text.toPlainText())
        output.write_text("SECOND CONTENT", encoding="utf-8")
        page.executions.setCurrentIndex(page.executions.findData(executions[1]))
        assert "FIRST CONTENT" not in page.artifact_preview.text.toPlainText()
        page.artifact_preview.open_button.click()
        spin(lambda: "SECOND CONTENT" in page.artifact_preview.text.toPlainText())
        assert all(client.calls == 0 for client in clients)
        assert all(e["evidence"]["artifacts"][0]["status"] == "written"
                   for e in c.snapshot()["executions"])
    finally:
        dispose(w)


def test_closed_reminder_is_still_business_pending(journey):
    _, clock, _, open_app = journey
    owner, c = open_app()
    arrange(owner, clock, "R8 通知筛选", repeat="once")
    advance(c, clock, minutes=2)
    owner.window.show_notifications()
    center = owner.window.notification_window
    center.dismiss_button.click()
    spin(lambda: note(c, "reminder")["state"] == "handled")
    center.filter.setCurrentIndex(center.filter.findData("pending"))
    center.refresh()
    assert len(center._rows) == 1
    assert center.cancel_button.isEnabled() and not center.snooze_button.isEnabled()
    navigate(owner, note(c, "reminder"))
    owner.window.schedule_window.complete.click()
    spin(lambda: c.snapshot()["executions"][0]["status"] == "done")
    center.refresh()
    assert center._rows == []
    center.filter.setCurrentIndex(center.filter.findData("history"))
    assert len(center._rows) == 1 and not center._rows[0]["valid"]


@pytest.mark.parametrize("status,verified", [("verified", True), ("written", False),
    ("write_unverified", False), ("readback_failed", False)])
def test_result_status_never_promotes_unverified_writes(status, verified):
    assert ("已回读核对" in artifacts_text([{"path": "a.md", "status": status}])) is verified


def test_preview_rejects_outside_scope_large_binary_and_missing_files(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (tmp_path / "outside.md").write_text("private", encoding="utf-8")
    for path, data in (("large.md", b"x" * (MAX_PREVIEW_BYTES + 1)), ("binary.md", b"\x00"), ("bad.md", b"\xff")):
        (workspace / path).write_bytes(data)
    for path in ("../outside.md", "large.md", "binary.md", "missing.md", "bad.md"):
        with pytest.raises(ValueError):
            read_artifact(workspace, path)


def test_preview_rejects_directory_link_escape(tmp_path):
    import os
    import subprocess
    workspace, outside = tmp_path / "workspace", tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (outside / "private.md").write_text("OUTSIDE PRIVATE CONTENT", encoding="utf-8")
    link = workspace / "linked"
    if os.name == "nt":
        # NTFS junctions need no elevated symlink privilege and exercise the
        # native Windows reparse-point boundary instead of skipping this check.
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)],
                       check=True, capture_output=True)
    else:
        link.symlink_to(outside, target_is_directory=True)
    try:
        assert (link / "private.md").read_text(encoding="utf-8") == "OUTSIDE PRIVATE CONTENT"
        with pytest.raises(ValueError, match="当前工作区"):
            read_artifact(workspace, "linked/private.md")
    finally:
        if os.name == "nt":
            link.rmdir()  # Remove only the junction, never recurse into its target.
        else:
            link.unlink()
    assert (outside / "private.md").exists()


@pytest.mark.parametrize("size", [(1280, 720), (1366, 768), (1920, 1080), (1024, 576), (853, 480)])
def test_pages_fit_logical_window_and_forms_scroll(qtapp, desktop, size):
    make, _, _, _ = desktop
    c = make()
    w = ChatWindow(c, DesktopOptions())
    w.show()
    try:
        for name in ("chat", "schedules", "memories", "notifications", "settings"):
            w.show_page(name)
            w.resize(*size)
            QApplication.processEvents()
            assert w.width() <= size[0] and w.height() <= size[1]
            assert w.exit_button.isVisible()
        page = w.schedule_window
        w.show_schedules()
        page.clear_form()
        page.kind.setCurrentIndex(page.kind.findData("execute"))
        QApplication.processEvents()
        page.scroll.ensureWidgetVisible(page.confirm)
        QApplication.processEvents()
        point = page.confirm.mapTo(page.scroll.viewport(), page.confirm.rect().center())
        assert page.scroll.viewport().rect().contains(point)
    finally:
        dispose(w)
