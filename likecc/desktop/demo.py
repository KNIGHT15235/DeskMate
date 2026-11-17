"""Offline client and cancellable tool, using the normal service execution path."""
import asyncio

from pydantic import BaseModel

from likecc.client import LLMClient
from likecc.tools.base import Tool, ToolResult, TextDelta, ToolCallComplete, StreamEnd


class WaitParams(BaseModel):
    pass


class DemoWait(Tool):
    name = "DemoWait"
    description = "Offline demo: wait until the current run is cancelled"
    params_model = WaitParams

    async def execute(self, params):
        await asyncio.Event().wait()
        return ToolResult("unreachable")


class DemoClient(LLMClient):
    async def stream(self, conversation, **kwargs):
        # Each submitted input runs the same write -> ask -> optional wait flow.
        last_input = max((i for i, m in enumerate(conversation.history)
                          if m.role == "user" and m.content and not m.content.startswith("<system-reminder>")
                          and not m.transient), default=0)
        tail = conversation.history[last_input:]
        calls = {c.tool_name for m in tail for c in m.tool_uses}
        if not calls:
            for text in ("离线演示：", "准备在临时工作区写入 demo.txt。\n"):
                yield TextDelta(text)
                await asyncio.sleep(0.03)
            yield ToolCallComplete("demo-write", "WriteFile", {"file_path": "demo.txt", "content": "DeskMate R3 demo"})
        elif "AskUserQuestion" not in calls:
            yield ToolCallComplete("demo-ask", "AskUserQuestion", {"questions": [
                {"type": "radio", "name": "next", "message": "下一步？", "options": ["完成", "等待取消"]},
                {"type": "text", "name": "note", "message": "备注（可留空）"},
            ]})
        elif any("等待取消" in r.content for m in tail for r in m.tool_results):
            yield TextDelta("正在等待；可以隐藏窗口，或点击取消。")
            yield ToolCallComplete("demo-wait", "DemoWait", {})
        else:
            yield TextDelta("离线演示完成。允许才会写入文件；会话已保存。")
            yield StreamEnd("end_turn")
            return
        yield StreamEnd("tool_use")
