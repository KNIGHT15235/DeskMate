"""Offline R4 workflow using real file tools and isolated HTTP fixtures."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory, mkdtemp

import httpx

from likecc.affairs import install_materials_profile
from likecc.client import LLMClient
from likecc.config import AppConfig, ProviderConfig
from likecc.extensions import ExtensionOptions, RuntimeExtensions
from likecc.permissions import PermissionMode
from likecc.runtime import Runtime
from likecc.service import SessionService
from likecc.tools.base import StreamEnd, TextDelta, ToolCallComplete

PAGES = ("https://study.example/recall", "https://study.example/review")
OUTPUT = "outputs/study-plan.md"


class BytesStream(httpx.AsyncByteStream):
    def __init__(self, data):
        self.data = data

    async def __aiter__(self):
        yield self.data


async def fixture_resolver(host, port):
    if host != "study.example":
        raise OSError("unexpected fixture host")
    return ["93.184.216.34"]


def fixture_transport():
    def handle(request):
        pages = {
            "/recall": ("text/html", b"<title>Active recall</title><p>Answer from memory before reviewing notes.</p>"),
            "/review": ("text/markdown", b"# Spaced review\nReview on days 1, 3 and 7."),
        }
        media, data = pages[request.url.path]
        return httpx.Response(200, headers={"Content-Type": media}, stream=BytesStream(data))
    return httpx.MockTransport(handle)


class StudyClient(LLMClient):
    def __init__(self, *, deny_write=False):
        self.step = 0
        self.deny_write = deny_write

    async def stream(self, conversation, **kwargs):
        self.step += 1
        contents = "# 学习计划\n\n- 每次安排 20 分钟 [S1]。\n- 先闭卷回想再看笔记 [S2]。"
        if self.step == 4:
            review = next(result for message in conversation.history for result in message.tool_results
                          if result.tool_use_id == "study-3")
            contents += ("\n\n## 限制\n复习网页读取失败，暂不引用。" if review.is_error
                         else "\n- 第 1、3、7 天复习 [S3]。")
        calls = {
            1: ("ReadFile", {"file_path": "project_notes.md"}),
            2: ("FetchWebPage", {"url": PAGES[0]}),
            3: ("FetchWebPage", {"url": PAGES[1]}),
            4: ("WriteFile", {"file_path": OUTPUT, "content": contents}),
            5: ("ReadFile", {"file_path": OUTPUT}),
        }
        if self.step > 5 or (self.step == 5 and self.deny_write):
            yield TextDelta("离线示例已结束，实际成果状态以工具回读记录为准。")
            yield StreamEnd("end_turn")
        else:
            name, args = calls[self.step]
            yield ToolCallComplete(f"study-{self.step}", name, args)
            yield StreamEnd("tool_use")


async def run_example(workspace: Path, *, deny_write=False):
    if any(workspace.iterdir()):
        raise ValueError("请使用空的独立示例目录")
    (workspace / "project_notes.md").write_text("# 学习笔记\n每次可投入 20 分钟。\n", encoding="utf-8")
    provider = ProviderConfig("offline-r4", "anthropic", "http://unused.invalid", "fake", api_key="offline-placeholder")
    with TemporaryDirectory(prefix="deskmate-r4-user-") as user_home:
        runtime = Runtime(config=AppConfig([provider]), work_dir=workspace, user_home=user_home,
                          permission_mode=PermissionMode.DEFAULT,
                          client_factory=lambda _: StudyClient(deny_write=deny_write))
        try:
            await runtime.initialize(provider)
            workflow = install_materials_profile(runtime, resolver=fixture_resolver, transport_factory=fixture_transport)
            await RuntimeExtensions(runtime, ExtensionOptions(interactive_tools=True)).initialize()
            service = SessionService(runtime, persistent=True, affairs=workflow)
            prompt = f"阅读 project_notes.md、{PAGES[0]} 和 {PAGES[1]}，生成 {OUTPUT} 并回读。"
            async with service.start(prompt, interactive=True) as run:
                async for envelope in run.events():
                    event = envelope.to_dict()
                    if event["type"] == "PermissionRequest":
                        data = event["data"]
                        value = "deny" if deny_write and data["tool_name"] == "WriteFile" else "allow"
                        assert run.reply(run.run_id, data["request_id"], value)
                await run.result()
            return workflow.summary()
        finally:
            await runtime.aclose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, help="An existing empty directory. Default: a new temporary directory.")
    parser.add_argument("--deny-write", action="store_true", help="Reject the Markdown write in this offline run.")
    args = parser.parse_args()
    workspace = (args.work_dir or Path(mkdtemp(prefix="deskmate-r4-example-"))).resolve()
    result = asyncio.run(run_example(workspace, deny_write=args.deny_write))
    print(json.dumps({"workspace": str(workspace), **result}, ensure_ascii=False, indent=2))
    artifact = workspace / OUTPUT
    if args.deny_write:
        return int(artifact.exists() or bool(result["artifacts"]))
    return int(not artifact.is_file() or result["artifacts"] != [{"path": OUTPUT, "status": "verified"}])


if __name__ == "__main__":
    raise SystemExit(main())
