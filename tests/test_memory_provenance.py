"""Source failure and retention boundaries using real local SQLite and sessions."""
from datetime import datetime, timedelta, timezone
import json
import shutil
import sqlite3
import uuid

import pytest

from likecc.affairs import install_materials_profile
from likecc.client import LLMClient
from likecc.config import AppConfig, ProviderConfig
from likecc.memory.session import SessionManager
from likecc.memory.workspace import WorkspaceMemory
from likecc.permissions import PermissionMode
from likecc.runtime import Runtime
from likecc.service import SessionService
from likecc.tools.base import TextDelta, StreamEnd, ToolCallComplete
from test_desktop_window import offline_socket_guard


class SourceClient(LLMClient):
    def __init__(self):
        self.counts = {}

    async def stream(self, conversation, **kwargs):
        prompt = next(m.content for m in reversed(conversation.history)
                      if m.role == "user" and m.content and not m.transient
                      and not m.content.startswith("<system-reminder>"))
        self.counts[prompt] = self.counts.get(prompt, 0) + 1
        if prompt in {"read a", "read b", "read c"} and self.counts[prompt] == 1:
            yield ToolCallComplete(uuid.uuid4().hex, "ReadFile", {"file_path": prompt[-1] + ".md"})
            yield StreamEnd("tool_use")
        else:
            yield TextDelta("offline done")
            yield StreamEnd("end_turn")


async def open_service(workspace, *, memories=True, cleanup=False, materials=False):
    provider = ProviderConfig("source-fake", "anthropic", "http://unused.invalid",
                              "fake", api_key="offline", context_window=32000)
    runtime = Runtime(config=AppConfig([provider]), work_dir=workspace,
                      user_home=workspace / "isolated-user", permission_mode=PermissionMode.DEFAULT,
                      client_factory=lambda _: SourceClient())
    await runtime.initialize(provider, load_instruction_files=False)
    affairs = install_materials_profile(runtime) if materials else None
    return runtime, SessionService(runtime, persistent=True, workspace_memory=memories,
                                   cleanup_sessions=cleanup, affairs=affairs)


def age_session(workspace, session_id):
    path = workspace / ".likecc/sessions" / f"{session_id}.meta"
    meta = json.loads(path.read_text(encoding="utf-8"))
    meta["last_active"] = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    path.write_text(json.dumps(meta), encoding="utf-8")


@pytest.mark.asyncio
@pytest.mark.parametrize("confirmed", [False, True])
async def test_memory_source_survives_tui_cleanup(tmp_path, confirmed, offline_socket_guard):
    runtime, service = await open_service(tmp_path)
    try:
        row = service.propose_memory("周报按结论、依据、行动项排列")
        if confirmed:
            service.change_memory(row["id"], 1, "confirm")
        original_sid = service.session.session_id
        unrelated_sid = service.new_session().session_id
    finally:
        await runtime.aclose()
    for sid in (original_sid, unrelated_sid):
        age_session(tmp_path, sid)
    source_log = tmp_path / ".likecc/sessions" / f"{original_sid}.jsonl"
    before = source_log.read_bytes()

    # The normal TUI enables this flag even though it does not use WorkspaceMemory.
    runtime, service = await open_service(tmp_path, memories=False, cleanup=True)
    try:
        assert not service.runtime.client.counts
        assert not (tmp_path / ".likecc/sessions" / f"{unrelated_sid}.jsonl").exists()
    finally:
        await runtime.aclose()
    runtime, service = await open_service(tmp_path)
    try:
        assert service.workspace_memory.get(row["id"])["status"] == ("confirmed" if confirmed else "pending")
        assert service.workspace_memory.details(row["id"])["source"]["session_id"] == original_sid
        assert service.resume(original_sid) is not None
        assert source_log.read_bytes() == before
        assert not service.runtime.client.counts and not offline_socket_guard
    finally:
        await runtime.aclose()


@pytest.mark.asyncio
async def test_sqlite_source_failure_clears_old_run_and_recovers(tmp_path, offline_socket_guard):
    for name in ("a", "b", "c"):
        (tmp_path / f"{name}.md").write_text(f"source {name}", encoding="utf-8")
    runtime, service = await open_service(tmp_path, materials=True)
    try:
        await service.run_to_completion("read a")
        previous = service.workspace_memory.source(service.last_source_id)
        service.workspace_memory.db.execute("PRAGMA busy_timeout=25")
        reader = sqlite3.connect((tmp_path / ".likecc/memories.sqlite3").as_uri() + "?mode=ro", uri=True)
        try:
            reader.execute("BEGIN")
            reader.execute("SELECT * FROM memory_sources").fetchall()
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                await service.run_to_completion("read b")
        finally:
            reader.rollback()
            reader.close()
        assert service.affairs.summary()["sources"][0]["target"] == "b.md"
        with pytest.raises(ValueError):
            service.propose_memory("事务 B 的资料关联", kind="affair", from_run=True)
        assert service.last_source_id is None and service.workspace_memory.list() == []

        await service.run_to_completion("read c")
        row = service.propose_memory("事务 C 的资料关联", kind="affair", from_run=True)
        source = service.workspace_memory.source(row["source_id"])
        assert source["run_id"] == service.last_run.run_id != previous["run_id"]
        assert source["evidence"]["sources"][0]["target"] == "c.md"
        assert not offline_socket_guard
    finally:
        await runtime.aclose()


def test_cleanup_protects_shared_sources_and_change_audit_until_last_reference_removed(tmp_path):
    manager = SessionManager(str(tmp_path))
    sessions = [manager.create() for _ in range(3)]
    origin, editor, unrelated = [s.session_id for s in sessions]
    for session in sessions:
        session.close()
        age_session(tmp_path, session.session_id)
    store = WorkspaceMemory(tmp_path)
    try:
        source = store.record_source(session_id=origin, run_id="source-run", kind="user_statement", quote="周报偏好")
        first = store.propose("preference", "周报格式", source)
        second = store.propose("project", "周报项目事实", source)
        store.change(first["id"], 1, action="confirm", session_id=editor)
        assert manager.cleanup() == 1
        assert {m.id for m in manager.list()} == {origin, editor}
        store.change(first["id"], 2, action="delete", session_id=editor)
        assert manager.cleanup() == 1  # editor is no longer referenced; origin still is
        assert {m.id for m in manager.list()} == {origin}
        store.change(second["id"], 1, action="delete", session_id=origin)
        assert manager.cleanup() == 1
        assert manager.list() == []
        assert store.source(source)["quote"] == "周报偏好"  # deleting references does not erase the audit
    finally:
        store.close()


@pytest.mark.parametrize("broken", ["corrupt", "other_workspace"])
def test_cleanup_skips_deletion_when_memory_references_cannot_be_trusted(tmp_path, broken, caplog):
    manager = SessionManager(str(tmp_path))
    session = manager.create()
    session.close()
    age_session(tmp_path, session.session_id)
    path = tmp_path / ".likecc/memories.sqlite3"
    if broken == "corrupt":
        path.write_bytes(b"not a sqlite database")
    else:
        other = WorkspaceMemory(tmp_path / "other")
        other.close()
        shutil.copy2(tmp_path / "other/.likecc/memories.sqlite3", path)
    before = path.read_bytes()
    assert manager.cleanup() == 0
    assert [m.id for m in manager.list()] == [session.session_id]
    assert path.read_bytes() == before
    assert "cleanup" in caplog.text.lower()
