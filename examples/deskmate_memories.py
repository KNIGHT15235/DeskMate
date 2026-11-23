"""Visible R6 offline acceptance harness using the normal desktop application.

python -m examples.deskmate_memories
python -m examples.deskmate_memories --root <printed directory>
Only the model/configuration are replaced; SQLite, sessions, tools and permissions
are real. Samples and model-inputs.jsonl persist for restart/review, with no key.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
from datetime import timedelta
import hashlib
import json
from pathlib import Path
from tempfile import mkdtemp
import uuid

from likecc.client import LLMClient
from likecc.config import AppConfig, ProviderConfig
from likecc.desktop.controller import DesktopController, DesktopOptions
from likecc.runtime import Runtime
from likecc.scheduling import utc_now, ScheduleStore, TaskSpec
from likecc.tools.base import TextDelta, ToolCallComplete, StreamEnd


class MemoryDemoClient(LLMClient):
    def __init__(self, workspace, log_path, inputs):
        self.workspace, self.log_path, self.inputs = Path(workspace), Path(log_path), inputs
        self._message = None
        self._plan = []
        self._step = 0

    async def stream(self, conversation, **kwargs):
        record = {"workspace": str(self.workspace), "system": kwargs.get("system", ""),
            "messages": [asdict(m) for m in conversation.history]}
        self.inputs.append(deepcopy(record))
        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
        message = next(m for m in reversed(conversation.history) if m.role == "user"
                       and m.content and not m.transient and not m.tool_results
                       and not m.content.startswith("<system-reminder>"))
        if message is not self._message:
            self._message, self._step = message, 0
            prompt = message.content
            pair = (("source-a.md", "outputs/a.md") if "整理资料一" in prompt else
                    ("source-b.md", "outputs/b.md") if "整理资料二" in prompt else None)
            if "本次已确认范围" in prompt:
                scope = json.loads(next(line for line in prompt.splitlines() if line.startswith('{"workspace":')))
                pair = (scope["files"][0], scope["outputs"][0]) if scope["files"] and scope["outputs"] else None
            self._plan = []
            if pair:
                source, output = pair
                self._plan.append(("ReadFile", {"file_path": source}))
                if (self.workspace / output).is_file():
                    self._plan.append(("ReadFile", {"file_path": output}))
                self._plan.extend([
                    ("WriteFile", {"file_path": output, "content": f"# 离线整理成果\n资料：{source} [S1]\n"}),
                    ("ReadFile", {"file_path": output})])
        if self._step < len(self._plan):
            name, arguments = self._plan[self._step]
            self._step += 1
            yield ToolCallComplete(uuid.uuid4().hex, name, arguments)
            yield StreamEnd("tool_use")
        else:
            yield TextDelta("离线脚本运行结束。请查看本次记忆、资料来源与成果回读状态。")
            yield StreamEnd("end_turn")


def prepare(root):
    root = Path(root).resolve()
    for name in ("A", "B"):
        workspace = root / name
        workspace.mkdir(parents=True, exist_ok=True)
        for path, content in {"project_notes.md": "# 每周已确认材料\n本周完成离线验证。\n",
                              "source-a.md": "# 资料一\n事务一的独立资料。\n",
                              "source-b.md": "# 资料二\n事务二的独立资料。\n"}.items():
            target = workspace / path
            if not target.exists():
                target.write_text(content, encoding="utf-8")
    return root


def demo_provider():
    return ProviderConfig("offline-r6", "anthropic", "http://unused.invalid", "fake", api_key="offline", context_window=32000)


def seed_review(root):
    """Clearly labelled synthetic history for visible R6-0 review, only on request."""
    workspace = Path(root) / "A"
    current = utc_now() - timedelta(days=15)
    store = ScheduleStore(workspace, clock=lambda: current)
    try:
        if any(t["spec"]["content"] == "R6-0 离线核对样例" for t in store.tasks()):
            return
        p = demo_provider()
        fingerprint = hashlib.sha256(f"{p.protocol}\n{p.base_url}\n{p.model}".encode()).hexdigest()[:12]
        task = store.save(TaskSpec("R6-0 离线核对样例", "execute",
            (current + timedelta(hours=1)).replace(tzinfo=None).isoformat(), timezone="UTC", repeat="weekly",
            files=["project_notes.md"], outputs=["outputs/review-summary.md"], provider=f"{p.name} / {p.model} · {fingerprint}"))
        current += timedelta(hours=2)
        store.scan()
        store.update(store.executions(task)[0]["id"], status="completed", reason="合成样例 A：已结束记录")
        current += timedelta(days=7)
        store.scan()
        store.update(store.executions(task)[0]["id"], status="interrupted", reason="合成样例 B：未知写入，需逐条核对",
            evidence={"write_intents": {"outputs/review-summary.md": {"status": "write_unverified"}}})
        current += timedelta(days=7)
        store.scan()  # a later occurrence visibly remains blocked_review
    finally:
        store.close()


def controller(options, root, *, inputs=None, clock=utc_now):
    root = Path(root).resolve()
    inputs = [] if inputs is None else inputs
    provider = demo_provider()

    def config_loader(*, work_dir):
        if Path(work_dir).resolve() not in {root / "A", root / "B"}:
            raise ValueError("R6 离线验收只使用打印的 A、B 工作区")
        return AppConfig([provider])

    def runtime_factory(**kwargs):
        workspace = Path(kwargs["work_dir"]).resolve()
        kwargs.update(config=config_loader(work_dir=workspace), user_home=root / "isolated-user",
            client_factory=lambda _: MemoryDemoClient(workspace, root / "model-inputs.jsonl", inputs))
        return Runtime(**kwargs)

    return DesktopController(options, runtime_factory=runtime_factory, clock=clock, config_loader=config_loader)


def main():
    parser = argparse.ArgumentParser(description="R6 持久离线桌面验收；不调用 Provider，不读取用户配置")
    parser.add_argument("--root", help="首次打印的验收根目录；不传则新建临时根目录并保留")
    parser.add_argument("--check", action="store_true", help="仅准备样例并打印路径，不打开窗口")
    parser.add_argument("--review-fixture", action="store_true", help="在 A 加入明确标注的 R6-0 合成历史 A/B 和受阻周期")
    args = parser.parse_args()
    root = prepare(args.root or mkdtemp(prefix="deskmate-r6-"))
    if args.review_fixture:
        seed_review(root)
    print(f"离线验收根目录：{root}\n工作区 A：{root / 'A'}\n工作区 B：{root / 'B'}\n实际模型输入：{root / 'model-inputs.jsonl'}", flush=True)
    if not args.check:
        from likecc.desktop.application import launch
        return launch(DesktopOptions(work_dir=str(root / "A")), controller_factory=lambda options: controller(options, root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
