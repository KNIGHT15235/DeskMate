"""Local storage, confirmation and immutable run-qualified source records."""
import shutil

import pytest

from likecc.memory.workspace import WorkspaceMemory, MAX_RECALL, MAX_RECALL_CHARS, render_recall


@pytest.fixture
def store(tmp_path):
    result = WorkspaceMemory(tmp_path / "a")
    yield result
    result.close()


def source(store, run="run-a", evidence=None):
    return store.record_source(session_id="session-a", run_id=run,
        kind="task_run" if evidence else "user_statement", quote="用户明确提供的内容", evidence=evidence)


@pytest.mark.parametrize("kind", ["preference", "project", "affair"])
def test_confirm_update_delete_stable_identity_restart_and_revision(store, kind):
    row = store.propose(kind, "周报按结论、依据、行动项排列", source(store))
    assert row["status"] == "pending"
    store.change(row["id"], 1, action="confirm", session_id="confirmation-session")
    store.change(row["id"], 2, action="update", session_id="edit-session", content="周报按行动项、依据、结论排列")
    with pytest.raises(ValueError, match="已变化"):
        store.change(row["id"], 2, action="delete", session_id="stale")
    workspace = store.workspace
    store.close()
    reopened = WorkspaceMemory(workspace)
    try:
        saved = reopened.get(row["id"])
        assert saved["content"] == "周报按行动项、依据、结论排列"
        assert saved["status"] == "confirmed" and saved["revision"] == 3
        details = reopened.details(row["id"])
        assert details["source"]["quote"] == "用户明确提供的内容"
        assert details["changes"][-1]["session_id"] == "edit-session"
        assert details["changes"][-1]["detail"]["content"] == saved["content"]
        reopened.change(row["id"], 3, action="delete", session_id="delete-session")
        assert reopened.list() == []
        assert reopened.source(row["source_id"])["session_id"] == "session-a"
    finally:
        reopened.close()


def test_run_scoped_s1_and_tool_evidence_unchanged(store):
    ids = []
    for run, path, status in (("run-a", "a.md", "verified"), ("run-b", "b.md", "written")):
        evidence = {"sources": [{"id": "S1", "target": path, "status": "read"}],
            "artifacts": [{"path": f"outputs/{path}", "status": status}]}
        ids.append(source(store, run, evidence))
        assert "key" not in evidence["sources"][0]  # preserve caller-owned evidence
    a, b = map(store.source, ids)
    assert a["evidence"]["sources"][0]["key"] != b["evidence"]["sources"][0]["key"]
    assert a["evidence"]["artifacts"][0]["status"] == "verified"
    assert b["evidence"]["artifacts"][0]["status"] == "written"


def test_workspace_isolation_and_copied_database_rejected(store, tmp_path):
    row = store.propose("project", "项目使用 SQLite", source(store))
    other = WorkspaceMemory(tmp_path / "b")
    try:
        assert other.list() == []
        with pytest.raises(ValueError):
            other.get(row["id"])
        with pytest.raises(ValueError):
            other.source(row["source_id"])
    finally:
        other.close()
    shutil.copy2(store.workspace + "/.likecc/memories.sqlite3", tmp_path / "b/.likecc/memories.sqlite3")
    with pytest.raises(ValueError, match="另一工作区"):
        WorkspaceMemory(tmp_path / "b")


@pytest.mark.parametrize("kind,content", [("guess", "fact"), ("project", ""), ("preference", "x" * 1001)])
def test_content_validation(store, kind, content):
    with pytest.raises(ValueError):
        store.propose(kind, content, source(store))


def test_local_chinese_recall_is_confirmed_bounded_and_fresh(store):
    for index in range(9):
        row = store.propose("preference", f"周报格式 {index}：结论、依据、行动项", source(store, str(index)))
        if index < 8:
            store.change(row["id"], 1, action="confirm", session_id="user")
    found = store.recall("整理周报")
    assert 1 <= len(found) <= MAX_RECALL
    assert len(render_recall(found)) <= MAX_RECALL_CHARS
    assert all("周报" in r["matched"] for r in found)
    assert row["id"] not in [r["id"] for r in found]  # pending
    assert store.recall("我的旅行天气") == []
    assert store.recall("周") == []  # single-character overlap is too weak
    first = found[0]
    store.change(first["id"], 2, action="update", session_id="user", content="发票使用 PDF")
    assert first["id"] not in [r["id"] for r in store.recall("周报")]
    assert any(r["id"] == first["id"] for r in store.recall("pdf"))
    store.change(first["id"], 3, action="delete", session_id="user")
    assert store.recall("发票 pdf") == []


def test_long_memories_fit_total_budget_without_partial_content(store):
    content = "周报 " + "具体依据" * 220
    for index in range(7):
        row = store.propose("preference", content, source(store, str(index)))
        store.change(row["id"], 1, action="confirm", session_id="user")
    selected = store.recall("周报")
    assert 0 < len(selected) < MAX_RECALL
    assert len(render_recall(selected)) <= MAX_RECALL_CHARS
    assert all(row["content"] == content for row in selected)
