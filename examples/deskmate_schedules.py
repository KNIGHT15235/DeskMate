"""Reproducible R5 experiments: no network, no real clock waits, real SQLite.

python -m examples.deskmate_schedules missed-reminder
python -m examples.deskmate_schedules interrupted --stage written
python -m examples.deskmate_schedules interrupted --stage claimed
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import mkdtemp

from likecc.affairs import install_materials_profile
from likecc.client import LLMClient
from likecc.config import AppConfig, ProviderConfig
from likecc.permissions import PermissionMode
from likecc.runtime import Runtime
from likecc.scheduling import ScheduleStore, TaskSpec
from likecc.service import SessionService
from likecc.tools.base import ToolCallComplete, StreamEnd, TextDelta

START = datetime(2026, 11, 20, 9, tzinfo=timezone.utc)


class WeeklyClient(LLMClient):
    def __init__(self):
        self.calls = 0

    async def stream(self, *args, **kwargs):
        self.calls += 1
        calls = [("ReadFile", {"file_path": "project_notes.md"}),
            ("WriteFile", {"file_path": "outputs/weekly-summary.md", "content": "# Summary\nProject evidence [S1]."}),
            ("ReadFile", {"file_path": "outputs/weekly-summary.md"})]
        if self.calls <= len(calls):
            name, arguments = calls[self.calls-1]
            yield ToolCallComplete(f"experiment-{self.calls}", name, arguments)
            yield StreamEnd("tool_use")
        else:
            yield TextDelta("done")
            yield StreamEnd("end_turn")


def specification():
    return TaskSpec("复习计划", "reminder", "2026-11-20T10:00:00", timezone="UTC")


def missed_reminder(workspace):
    store = ScheduleStore(workspace, clock=lambda: START)
    task = store.save(specification())
    store.close()  # app fully exited before the due time
    reopened = ScheduleStore(workspace, clock=lambda: START + timedelta(days=1))
    try:
        reopened.scan()
        reopened.scan()
        row, = reopened.executions(task)
        assert row["status"] == "pending" and "逾期" in row["reason"]
        reopened.complete_reminder(row["id"])
        assert reopened.execution(row["id"])["status"] == "done"
        return {"experiment": "missed-reminder", "workspace": str(workspace), "records": reopened.executions(),
            "model_calls": 0, "result": "退出期间错过的提醒重开后逾期待处理；完成和重复扫描不产生第二条"}
    finally:
        reopened.close()


async def crash_child(workspace, stage):
    store = ScheduleStore(workspace, clock=lambda: START + timedelta(hours=2))
    store.scan()
    row, = store.executions()
    assert store.start(row["id"])
    if stage == "claimed":
        os._exit(71)  # simulate process death, no finally/close hooks
    provider = ProviderConfig("offline-experiment", "anthropic", "http://unused.invalid", "fake", api_key="offline", context_window=32000)
    model = WeeklyClient()
    runtime = Runtime(config=AppConfig([provider]), work_dir=workspace, user_home=workspace / "user",
        permission_mode=PermissionMode.DEFAULT, client_factory=lambda _: model)
    await runtime.initialize(provider)
    workflow = install_materials_profile(runtime)
    service = SessionService(runtime, persistent=True, affairs=workflow)
    write = runtime.registry.get("WriteFile")
    original = write.execute

    async def counted(params):
        with (workspace / "write-calls.jsonl").open("a", encoding="utf-8") as file:
            file.write(json.dumps({"path": params.file_path}) + "\n")
            file.flush()
            os.fsync(file.fileno())
        return await original(params)

    write.execute = counted

    def checkpoint():
        store.update(row["id"], evidence=workflow.summary() | {"write_intents": workflow.write_intents})
        if any(a["status"] == "written" for a in workflow.artifacts.values()):
            os._exit(71)  # real file exists, terminal execution state not saved

    workflow.on_change = checkpoint
    run = service.start("读取 project_notes.md，生成 outputs/weekly-summary.md 并回读。", interactive=True)
    store.update(row["id"], session_id=run.session_id, run_id=run.run_id)
    async with run:
        async for envelope in run.events():
            event = envelope.to_dict()
            if event["type"] == "PermissionRequest":
                assert run.reply(run.run_id, event["data"]["request_id"], "allow")
    raise AssertionError("crash checkpoint not reached")


def interrupted(workspace, stage="written"):
    (workspace / "project_notes.md").write_text("# Notes\nProject evidence.\n", encoding="utf-8")
    store = ScheduleStore(workspace, clock=lambda: START)
    store.save(replace(specification(), kind="execute", files=["project_notes.md"],
        outputs=["outputs/weekly-summary.md"], model_policy="allow"))
    store.close()
    child = subprocess.run([sys.executable, "-m", "examples.deskmate_schedules", "crash-child",
        "--stage", stage, "--work-dir", str(workspace)], capture_output=True, text=True, timeout=25)
    assert child.returncode == 71, (child.stdout, child.stderr)
    output = workspace / "outputs/weekly-summary.md"
    before = (output.read_bytes(), output.stat().st_mtime_ns) if output.exists() else None
    calls_file = workspace / "write-calls.jsonl"
    calls = calls_file.read_text(encoding="utf-8").splitlines() if calls_file.exists() else []
    assert len(calls) == (1 if stage == "written" else 0)
    reopened = ScheduleStore(workspace, clock=lambda: START + timedelta(days=1))
    try:
        reopened.scan()
        reopened.scan()
        row, = reopened.executions()
        assert row["status"] == "interrupted" and not reopened.start(row["id"])
        after = (output.read_bytes(), output.stat().st_mtime_ns) if output.exists() else None
        assert before == after
        assert (calls_file.read_text(encoding="utf-8").splitlines() if calls_file.exists() else []) == calls

        async def resume_only():
            model = WeeklyClient()
            provider = ProviderConfig("offline", "anthropic", "http://unused.invalid", "fake", api_key="offline", context_window=32000)
            runtime = Runtime(config=AppConfig([provider]), work_dir=workspace, user_home=workspace / "user",
                permission_mode=PermissionMode.DEFAULT, client_factory=lambda _: model)
            try:
                await runtime.initialize(provider)
                service = SessionService(runtime, persistent=True)
                assert service.resume(row["session_id"])
                assert model.calls == 0
            finally:
                await runtime.aclose()

        if row["session_id"]:
            asyncio.run(resume_only())
            assert (output.read_bytes(), output.stat().st_mtime_ns) == before
            assert calls_file.read_text(encoding="utf-8").splitlines() == calls
        return {"experiment": "interrupted", "stage": stage, "workspace": str(workspace), "write_calls": len(calls),
            "records": reopened.executions(), "result": "已中断，待核对；扫描/恢复会话不重复写入。查看旧成果后可明确发起新尝试。"}
    finally:
        reopened.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiment", choices=["missed-reminder", "interrupted", "crash-child"])
    parser.add_argument("--stage", choices=["claimed", "written"], default="written")
    parser.add_argument("--work-dir", type=Path)
    args = parser.parse_args()
    root = (args.work_dir or Path(mkdtemp(prefix="deskmate-r5-"))).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if args.experiment == "crash-child":
        asyncio.run(crash_child(root, args.stage))
        return
    if any(root.iterdir()):
        raise ValueError("请使用新的空目录；不会覆盖既有实验数据")
    result = missed_reminder(root) if args.experiment == "missed-reminder" else interrupted(root, args.stage)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
