from dataclasses import replace
from datetime import datetime, timedelta, timezone
import shutil
import sqlite3

import pytest

from likecc.scheduling import ScheduleStore, SchedulerOwned, TaskSpec, parse_schedule, local_instant


class Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


def reminder(clock, **kwargs):
    return TaskSpec("复习这份计划", "reminder", (clock.now + timedelta(hours=1)).replace(tzinfo=None).isoformat(),
        timezone="UTC", **kwargs)


def test_definition_history_unique_claim_and_reopen(tmp_path):
    clock = Clock()
    store = ScheduleStore(tmp_path, clock=clock)
    task = store.save(reminder(clock))
    original = store.task(task)
    store.save(replace(reminder(clock), content="复习新版计划"), task_id=task, revision=1)
    with pytest.raises(ValueError, match="已变化"):
        store.save(reminder(clock), task_id=task, revision=1)
    store.close()
    store = ScheduleStore(tmp_path, clock=clock)
    try:
        store.scan()
        assert not store.executions()
        clock.advance(hours=2)
        store.scan()
        store.scan()
        row, = store.executions()
        assert row["status"] == "pending" and "逾期" in row["reason"]
        assert row["snapshot"]["content"] == "复习新版计划"
        store.save(reminder(clock), task_id=task, revision=2)
        assert store.execution(row["id"])["snapshot"]["content"] != original["spec"]["content"]
        store.complete_reminder(row["id"])
        store.complete_reminder(row["id"])
        assert store.execution(row["id"])["status"] == "done"
        with pytest.raises(sqlite3.IntegrityError):
            store.db.execute("INSERT INTO executions (id,task_id,due_at,snapshot,status) VALUES ('dup',?,?, '{}','pending')",
                (task, row["due_at"]))
    finally:
        store.close()


def test_live_owner_cannot_be_stolen_or_recover_active_work(tmp_path):
    clock = Clock()
    store = ScheduleStore(tmp_path, clock=clock)
    task = store.save(replace(reminder(clock), kind="execute", outputs=["out.md"], model_policy="allow"))
    clock.advance(hours=2)
    store.scan()
    row, = store.executions(task)
    assert store.start(row["id"])
    assert not store.start(row["id"])
    try:
        for _ in range(2):
            with pytest.raises(SchedulerOwned):
                ScheduleStore(tmp_path, clock=clock)
            assert store.execution(row["id"])["status"] == "running"
    finally:
        store.close()
    new = ScheduleStore(tmp_path, clock=clock)
    try:
        assert new.execution(row["id"])["status"] == "interrupted"
        new.scan()
        assert len(new.executions()) == 1
        new.retry(row["id"])
        new.retry(row["id"])
        assert len(new.executions()) == 2
        assert new.execution(row["id"])["status"] == "interrupted"
    finally:
        new.close()


def test_weekly_coalescing_edit_cancel_and_workspace_isolation(tmp_path):
    clock = Clock()
    a, b = ScheduleStore(tmp_path / "a", clock=clock), ScheduleStore(tmp_path / "b", clock=clock)
    try:
        task = a.save(reminder(clock, repeat="weekly"))
        clock.advance(days=29)
        a.scan()
        a.scan()
        row, = a.executions()
        assert "合并错过的 4" in row["reason"]
        assert datetime.fromisoformat(a.task(task)["next_due"]) > clock.now
        assert not b.tasks() and not b.executions()
        a.save(reminder(clock, repeat="weekly"), task_id=task, revision=1)
        assert a.execution(row["id"])["snapshot"]["revision"] == 1
        a.cancel(task)
        clock.advance(days=35)
        a.scan()
        assert len(a.executions()) == 1 and not a.task(task)["enabled"]
    finally:
        a.close()
        b.close()
    shutil.copyfile(tmp_path / "a/.likecc/schedules.sqlite3", tmp_path / "b/.likecc/schedules.sqlite3")
    with pytest.raises(ValueError, match="另一工作区"):
        ScheduleStore(tmp_path / "b", clock=clock)


@pytest.mark.parametrize("status", ["queued", "awaiting_model", "running", "waiting"])
def test_recovery_never_replays_claimed_execution(tmp_path, status):
    clock = Clock()
    store = ScheduleStore(tmp_path, clock=clock)
    store.save(replace(reminder(clock), kind="execute", outputs=["out.md"]))
    clock.advance(hours=2)
    store.scan()
    row, = store.executions()
    evidence = {"artifacts": [{"path": "out.md", "status": "written"}], "sources": []}
    store.update(row["id"], status=status, session_id="session-test", run_id="run-test", evidence=evidence)
    (tmp_path / "out.md").write_text("side effect", encoding="utf-8")
    before = (tmp_path / "out.md").stat().st_mtime_ns
    store.close()
    new = ScheduleStore(tmp_path, clock=clock)
    try:
        new.scan()
        saved, = new.executions()
        assert saved["status"] == "interrupted" and saved["evidence"] == evidence
        assert saved["session_id"] == "session-test" and saved["run_id"] == "run-test"
        assert not new.start(saved["id"])
        assert (tmp_path / "out.md").read_text(encoding="utf-8") == "side effect"
        assert (tmp_path / "out.md").stat().st_mtime_ns == before
    finally:
        new.close()


def test_natural_time_parser_and_scope_validation(tmp_path):
    clock = Clock()
    one = parse_schedule("明天晚上七点提醒我复习这份计划", now=clock())
    assert (one.local_at, one.timezone, one.repeat) == ("2026-11-21T19:00:00", "Asia/Shanghai", "once")
    weekly = parse_schedule("每周五下午六点，根据工作区的 `project_notes.md` 更新 `outputs/weekly-summary.md`", now=clock())
    assert weekly.kind == "execute" and weekly.local_at == "2026-11-20T18:00:00"
    assert weekly.validated(tmp_path).files == ["project_notes.md"]
    assert weekly.outputs == ["outputs/weekly-summary.md"]
    for text in ("明天七点提醒我", "以后提醒", "每周下午三点整理"):
        with pytest.raises(ValueError):
            parse_schedule(text, now=clock())
    with pytest.raises(ValueError):
        replace(weekly, outputs=["../escape.md"]).validated(tmp_path)
    with pytest.raises(ValueError):
        local_instant("2026-11-21T19:00:00", "unknown/timezone")


def test_unknown_side_effect_blocks_later_cycles_until_explicit_review(tmp_path):
    clock = Clock()
    spec = replace(reminder(clock, repeat="weekly"), kind="execute", outputs=["out.md"], model_policy="allow")
    store = ScheduleStore(tmp_path, clock=clock)
    store.save(spec)
    clock.advance(hours=2)
    store.scan()
    old, = store.executions()
    store.start(old["id"])
    store.close()
    store = ScheduleStore(tmp_path, clock=clock)
    try:
        clock.advance(days=21)
        store.scan()
        rows = store.executions()
        assert {r["status"] for r in rows} == {"interrupted", "blocked_review"}
        assert not any(store.start(r["id"]) for r in rows)
        store.retry(old["id"])
        store.retry(old["id"])
        assert len(store.executions()) == 3
        assert store.execution(old["id"])["reviewed_at"]
        assert {r["status"] for r in store.executions()} == {"interrupted", "cancelled", "awaiting_model"}
    finally:
        store.close()


@pytest.mark.parametrize("text,expected", [
    ("明天晚上七点十五分提醒我", "19:15:00"),
    ("明天早上七点半提醒我", "07:30:00"),
    ("明天07:05提醒我", "07:05:00"),
])
def test_natural_parser_does_not_drop_minutes(text, expected):
    assert parse_schedule(text, now=Clock()()).local_at.endswith(expected)


@pytest.mark.parametrize("text", ["明天晚上七点一刻提醒我", "明天晚上七点左右提醒我", "明天晚上七点或八点提醒我"])
def test_ambiguous_minutes_need_clarification(text):
    with pytest.raises(ValueError):
        parse_schedule(text, now=Clock()())
