"""R7 offline desktop. Real controller, sessions, SQLite, permissions and files.

Only the client/configuration and explicitly labelled failure injection are fake.
The clock offset is persisted; advancing it never changes the system clock.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
from datetime import timedelta
import hashlib
import json
from pathlib import Path
from tempfile import mkdtemp
import uuid
from unittest.mock import patch

from likecc.client import LLMClient
from likecc.config import AppConfig, ProviderConfig
from likecc.desktop.controller import DesktopController, DesktopOptions
from likecc.runtime import Runtime
from likecc.scheduling import ScheduleStore, TaskSpec, utc_now
from likecc.tools.base import TextDelta, ToolCallComplete, StreamEnd
from likecc.tools.write_file import WriteFile


def prepare(root):
    root = Path(root).resolve()
    for name in ("A", "B"):
        folder = root / name
        folder.mkdir(parents=True, exist_ok=True)
        source = folder / "project_notes.md"
        if not source.exists():
            source.write_text("# R7 本地材料\n通知只导航，操作仍需明确授权。\n", encoding="utf-8")
    if not (root / "clock.json").exists():
        (root / "clock.json").write_text('{"offset_minutes": 0}', encoding="utf-8")
    return root


def demo_clock(root):
    def now():
        offset = json.loads((Path(root) / "clock.json").read_text(encoding="utf-8"))["offset_minutes"]
        return utc_now() + timedelta(minutes=offset)
    return now


def demo_provider():
    return ProviderConfig("offline-r7", "anthropic", "http://unused.invalid", "fake", api_key="offline", context_window=32000)


class NotificationDemoClient(LLMClient):
    def __init__(self, workspace, root, inputs):
        self.workspace, self.root, self.inputs = Path(workspace), Path(root), inputs
        self.message, self.plan, self.step = None, [], 0

    async def stream(self, conversation, **kwargs):
        record = {"workspace": str(self.workspace), "messages": [asdict(m) for m in conversation.history]}
        self.inputs.append(deepcopy(record))
        with (self.root / "model-inputs.jsonl").open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
        message = next(m for m in reversed(conversation.history) if m.role == "user"
            and m.content and not m.transient and not m.tool_results and not m.content.startswith("<system-reminder>"))
        if message is not self.message:
            self.message, self.step, self.plan = message, 0, []
            if "R7 失败" in message.content:
                raise RuntimeError("R7 离线注入的模型失败；没有网络请求")
            if "本次已确认范围" in message.content:
                scope = json.loads(next(line for line in message.content.splitlines() if line.startswith('{"workspace":')))
                self.plan = [("ReadFile", {"file_path": p}) for p in scope["files"]]
                if "R7 问答" in message.content:
                    self.plan.append(("AskUserQuestion", {"questions": [{"type":"text", "name":"note", "message":"补充本次说明"}]}))
                for path in scope["outputs"]:
                    if (self.workspace / path).exists():
                        self.plan.append(("ReadFile", {"file_path": path}))
                    self.plan.extend([("WriteFile", {"file_path": path, "content": "# R7 离线成果\n根据本地材料整理 [S1]。\n"}),
                                      ("ReadFile", {"file_path": path})])
            else:
                self.plan = [("AskUserQuestion", {"questions": [{"type":"text", "name":"note", "message":"R7 前台补充回答"}]})]
        # Refused or failed tool operations stop this scripted client. It cannot
        # interpret a notification click as another model/tool request.
        last = conversation.history[-1]
        if any(r.is_error for r in last.tool_results):
            self.step = len(self.plan)
        if self.step < len(self.plan):
            name, args = self.plan[self.step]
            self.step += 1
            yield ToolCallComplete(uuid.uuid4().hex, name, args)
            yield StreamEnd("tool_use")
        else:
            yield TextDelta("离线运行结束，请以执行记录中的工具证据核对成果。")
            yield StreamEnd("end_turn")


@contextmanager
def injected_write_failure(root):
    """Only the designated demo output fails after a real partial local write."""
    original = WriteFile._write_text
    roots = {(Path(root) / name).resolve() for name in ("A", "B")}

    def write(tool, path, content):
        root_match = any(path.is_relative_to(folder) for folder in roots)
        if root_match:
            with (Path(root) / "writes.jsonl").open("a", encoding="utf-8") as log:
                log.write(json.dumps({"path": str(path), "fault": path.name == "unknown.md"}) + "\n")
        if root_match and path.name == "unknown.md":
            path.write_text("R7 故障注入：部分写入\n", encoding="utf-8")
            raise OSError("R7 离线注入的写入中断")
        return original(tool, path, content)

    with patch.object(WriteFile, "_write_text", write):
        yield


def controller(options, root, *, inputs=None, clock=None):
    root = Path(root).resolve()
    inputs = [] if inputs is None else inputs
    provider = demo_provider()

    def config_loader(*, work_dir):
        if Path(work_dir).resolve() not in {root / "A", root / "B"}:
            raise ValueError("R7 离线验收只使用打印的 A、B 工作区")
        return AppConfig([provider])

    def runtime_factory(**kwargs):
        workspace = Path(kwargs["work_dir"]).resolve()
        kwargs.update(config=config_loader(work_dir=workspace), user_home=root / "isolated-user",
            client_factory=lambda _: NotificationDemoClient(workspace, root, inputs))
        return Runtime(**kwargs)

    return DesktopController(options, runtime_factory=runtime_factory, config_loader=config_loader,
                             clock=clock or demo_clock(root))


def seed(root):
    """Future definitions only; no fabricated completed executions or permissions."""
    clock = demo_clock(root)
    store = ScheduleStore(Path(root) / "A", clock=clock)
    try:
        if store.tasks():
            return
        p = demo_provider()
        fingerprint = hashlib.sha256(f"{p.protocol}\n{p.base_url}\n{p.model}".encode()).hexdigest()[:12]
        identity = f"{p.name} / {p.model} · {fingerprint}"
        for index, (name, outputs) in enumerate([
            ("R7 一次性提醒", []), ("R7 两次写入", ["outputs/first.md", "outputs/second.md"]),
            ("R7 拒绝写入", ["outputs/denied.md"]), ("R7 失败", ["outputs/failed.md"]),
            ("R7 未知写入（离线故障注入）", ["outputs/unknown.md"]),
        ], 1):
            store.save(TaskSpec(name, "execute" if outputs else "reminder",
                (clock() + timedelta(minutes=index)).replace(tzinfo=None).isoformat(), timezone="UTC",
                repeat="weekly" if outputs else "once", files=["project_notes.md"] if outputs else [],
                outputs=outputs, provider=identity if outputs else ""))
    finally:
        store.close()


def main():
    parser = argparse.ArgumentParser(description="R7 持久离线桌面：通知、延后、免打扰；不读取真实配置、不调用 Provider")
    parser.add_argument("--root", help="已有验收根目录；不传则创建新的临时根目录并保留")
    parser.add_argument("--check", action="store_true", help="只准备样例与未来安排，不打开窗口")
    parser.add_argument("--advance-minutes", type=int, help="仅推进此演示的持久时钟偏移；须传 --root，可在另一终端执行")
    args = parser.parse_args()
    if args.advance_minutes is not None and (not args.root or args.advance_minutes < 0):
        parser.error("推进时钟需要 --root 和非负分钟数")
    root = prepare(args.root or mkdtemp(prefix="deskmate-r7-"))
    if args.advance_minutes is not None:
        path = root / "clock.json"
        offset = json.loads(path.read_text(encoding="utf-8"))["offset_minutes"] + args.advance_minutes
        temporary = root / (uuid.uuid4().hex + ".json")
        temporary.write_text(json.dumps({"offset_minutes": offset}), encoding="utf-8")
        temporary.replace(path)
        print(f"演示时钟：{demo_clock(root)().isoformat()}；系统时间未改变")
        return 0
    seed(root)
    print(f"R7 离线验收根目录：{root}\n工作区 A：{root / 'A'}\n工作区 B：{root / 'B'}\n"
          f"模拟时钟：{demo_clock(root)().isoformat()}\n"
          "Provider：offline-r7 / fake；unknown.md 启用明确的部分写入故障注入。\n"
          "重开使用同一 --root；运行中推进时钟只用 --advance-minutes，不启动第二个桌面实例。", flush=True)
    if not args.check:
        from likecc.desktop.application import launch
        with injected_write_failure(root):
            return launch(DesktopOptions(work_dir=str(root / "A")),
                          controller_factory=lambda options: controller(options, root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
