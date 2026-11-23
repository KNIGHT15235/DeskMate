"""Pre-commit R5 findings, exercised without network or real time waits."""
from dataclasses import replace
from pathlib import Path

import pytest

from likecc.scheduling import ScheduleStore
from likecc.runtime import Runtime
from likecc.tools.base import TextDelta, ToolCallComplete, StreamEnd
from test_desktop_controller import command, wait, reply, close
from test_desktop_scheduling import desktop, arrange, execute_spec


def test_scheduled_context_excludes_implicit_instruction_files(desktop, tmp_path, monkeypatch):
    make, clock, clients, _ = desktop
    markers = ["PROJECT_INCLUDE_PRIVATE_9271", "HIDDEN_INSTRUCTION_9271", "HOME_INSTRUCTION_9271"]
    (tmp_path / "private_notes.md").write_text(markers[0], encoding="utf-8")
    (tmp_path / "LIKECC.md").write_text("@include private_notes.md\n", encoding="utf-8")
    for folder, marker in ((tmp_path / ".likecc", markers[1]), (tmp_path / "user/.likecc", markers[2])):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "LIKECC.md").write_text(marker, encoding="utf-8")
    c = make()
    seen = []

    async def capture(self, conversation, **kwargs):
        self.calls += 1
        seen.append("\n".join(str(m.content) for m in conversation.history))
        yield TextDelta("offline only")
        yield StreamEnd("end_turn")

    monkeypatch.setattr(type(clients[0]), "stream", capture)
    # Ordinary foreground sessions retain the existing instruction behavior.
    assert command(c, "send", text="foreground context check")["accepted"]
    wait(c, lambda s: s["state"] == "idle")
    assert all(marker in seen[0] for marker in markers)
    seen.clear()

    def forbid_implicit_load(*args, **kwargs):
        pytest.fail("scheduled initialization must not open instruction files")

    monkeypatch.setattr("likecc.runtime.load_instructions", forbid_implicit_load)
    arrange(c, execute_spec(clock, model_policy="allow"))
    clock.advance(hours=2)
    assert command(c, "schedule_scan")["accepted"]
    final = wait(c, lambda s: s["state"] == "idle" and s["executions"][0]["status"] == "completed")
    assert final["executions"][0]["snapshot"]["files"] == ["project_notes.md"]
    assert seen and not any(marker in text for marker in markers for text in seen)


def test_confirmed_instruction_filename_is_read_as_material_without_includes(desktop, tmp_path, monkeypatch):
    make, clock, clients, _ = desktop
    (tmp_path / "LIKECC.md").write_text("@include private.md\n", encoding="utf-8")
    (tmp_path / "private.md").write_text("PRIVATE_INCLUDE_9271", encoding="utf-8")
    c = make()
    seen = []

    async def read_material(self, conversation, **kwargs):
        self.calls += 1
        seen.append("\n".join(str(m.content) + str(m.tool_results) for m in conversation.history))
        if self.calls <= 2:
            path = "LIKECC.md" if self.calls == 1 else "private.md"
            yield ToolCallComplete(f"read-{self.calls}", "ReadFile", {"file_path": path})
            yield StreamEnd("tool_use")
        else:
            yield TextDelta("done")
            yield StreamEnd("end_turn")

    monkeypatch.setattr(type(clients[0]), "stream", read_material)
    arrange(c, replace(execute_spec(clock, model_policy="allow"), files=["LIKECC.md"]))
    clock.advance(hours=2)
    assert command(c, "schedule_scan")["accepted"]
    final = wait(c, lambda s: s["state"] == "idle" and s["executions"][0]["status"] == "completed")
    evidence = final["executions"][0]["evidence"]
    assert any(s["target"] == "LIKECC.md" and s["status"] == "read" for s in evidence["sources"])
    assert any("范围" in e["output"] for e in evidence["tool_errors"])
    assert any("@include private.md" in text for text in seen)
    assert not any("PRIVATE_INCLUDE_9271" in text for text in seen)


def test_start_link_failure_releases_run_and_dispatches_other_task(desktop, monkeypatch):
    make, clock, clients, behavior = desktop
    behavior["mode"] = "text_only"
    c = make()
    first_id = arrange(c, execute_spec(clock, model_policy="allow"))
    original = ScheduleStore.update
    failures = []

    def fail_once(self, execution_id, **values):
        if "run_id" in values and not failures:
            failures.append(execution_id)
            raise OSError("transient run-link persistence failure")
        return original(self, execution_id, **values)

    monkeypatch.setattr(ScheduleStore, "update", fail_once)
    clock.advance(hours=2)
    command(c, "schedule_scan")
    final = wait(c, lambda s: s["state"] == "idle" and s["executions"][0]["status"] == "interrupted")
    old, = final["executions"]
    assert failures and old["task_id"] == first_id
    assert c._run is None and c._scheduled_runtime is None
    assert all(client.calls == 0 for client in clients)
    assert old["session_id"] and old["run_id"]
    second_id = arrange(c, replace(execute_spec(clock, model_policy="allow"), content="independent second task"))
    clock.advance(hours=2)
    assert command(c, "schedule_scan")["accepted"]
    final = wait(c, lambda s: s["state"] == "idle" and any(
        row["task_id"] == second_id and row["status"] == "completed" for row in s["executions"]))
    assert len(final["executions"]) == 2
    assert sum(client.calls for client in clients) == 1
    assert command(c, "schedule_scan")["accepted"]
    assert len(c.snapshot()["executions"]) == 2


@pytest.mark.parametrize("cleanup_failure", ["database", "runtime"])
def test_start_failure_with_failed_recovery_stops_dispatch(desktop, monkeypatch, cleanup_failure):
    make, clock, clients, behavior = desktop
    behavior["mode"] = "text_only"
    c = make()
    arrange(c, execute_spec(clock, model_policy="allow"))
    original_update, original_close = ScheduleStore.update, Runtime.aclose
    failed_link = []
    failed_close = []

    def update(self, execution_id, **values):
        if "run_id" in values and not failed_link:
            failed_link.append(True)
            raise OSError("run linkage failed")
        if cleanup_failure == "database" and values.get("status") == "interrupted":
            raise OSError("recovery persistence failed")
        return original_update(self, execution_id, **values)

    async def close_runtime(self):
        if cleanup_failure == "runtime" and self is c._scheduled_runtime and not failed_close:
            failed_close.append(True)
            raise OSError("temporary runtime close failure")
        await original_close(self)

    monkeypatch.setattr(ScheduleStore, "update", update)
    monkeypatch.setattr(Runtime, "aclose", close_runtime)
    clock.advance(hours=2)
    command(c, "schedule_scan")
    wait(c, lambda s: s["state"] == "error")
    clock.advance(days=7)
    command(c, "schedule_scan")
    assert len(c.snapshot()["executions"]) == 1
    assert all(client.calls == 0 for client in clients)
    close(c)
    reopened = make()
    command(reopened, "schedule_scan")
    assert {row["status"] for row in reopened.snapshot()["executions"]} == {"interrupted", "blocked_review"}
    assert all(client.calls == 0 for client in clients)


@pytest.mark.parametrize("failure_stage", ["partial", "after_full_write"])
def test_write_io_failure_is_reviewed_before_next_cycle(desktop, monkeypatch, tmp_path, failure_stage):
    make, clock, clients, _ = desktop
    c = make()
    arrange(c, execute_spec(clock, model_policy="allow"))
    output = tmp_path / "outputs/weekly-summary.md"
    original = Path.write_text
    writes = []

    def failed_write(path, text, *args, **kwargs):
        if path == output:
            with path.open("w", encoding="utf-8") as target:
                target.write("PARTIAL SIDE EFFECT\n" if failure_stage == "partial" else text)
            writes.append(str(path))
            raise OSError("injected I/O failure after writing")
        return original(path, text, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", failed_write)
    clock.advance(hours=2)
    command(c, "schedule_scan")
    assert reply(c, {"note": "continue"})["accepted"]
    wait(c, lambda s: s["pending"] and s["pending"][0]["kind"] == "PermissionRequest")
    assert reply(c, "allow")["accepted"]
    final = wait(c, lambda s: s["state"] == "idle" and s["executions"][0]["ended_at"])
    row, = final["executions"]
    before = output.read_bytes(), output.stat().st_mtime_ns
    assert len(writes) == 1
    if failure_stage == "after_full_write":
        # A later successful readback can resolve an initially uncertain write.
        assert row["status"] == "completed"
        assert row["evidence"]["artifacts"] == [{"path": "outputs/weekly-summary.md", "status": "verified"}]
        assert row["evidence"]["write_intents"]["outputs/weekly-summary.md"]["status"] == "written"
        return
    assert before[0].strip() == b"PARTIAL SIDE EFFECT"
    assert row["status"] == "interrupted" and "核对" in row["reason"]
    assert row["evidence"]["write_intents"]["outputs/weekly-summary.md"]["status"] == "write_unverified"
    assert row["evidence"]["artifacts"][0]["status"] == "readback_failed"
    calls = sum(client.calls for client in clients)
    clock.advance(days=7)
    assert command(c, "schedule_scan")["accepted"]
    assert {r["status"] for r in c.snapshot()["executions"]} == {"interrupted", "blocked_review"}
    close(c)
    reopened = make()
    assert command(reopened, "schedule_scan")["accepted"]
    assert sum(client.calls for client in clients) == calls
    assert len(writes) == 1 and (output.read_bytes(), output.stat().st_mtime_ns) == before
    assert command(reopened, "schedule_retry", execution_id=row["id"], reviewed_execution_id=row["id"])["accepted"]
    assert command(reopened, "schedule_retry", execution_id=row["id"], reviewed_execution_id=row["id"])["accepted"]
    attempts = [r for r in reopened.snapshot()["executions"] if r["retry_of"] == row["id"]]
    assert len(attempts) == 1 and attempts[0]["status"] == "awaiting_model"
    assert sum(client.calls for client in clients) == calls
