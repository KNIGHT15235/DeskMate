"""Offline R2 demo: python -m examples.deskmate_session --decision allow|deny|cancel."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from likecc.agent import PermissionRequest
from likecc.client import LLMClient
from likecc.config import AppConfig, ProviderConfig
from likecc.permissions import PermissionMode
from likecc.runtime import Runtime
from likecc.service import SessionService
from likecc.tools.base import TextDelta, ToolCallComplete, StreamEnd


class DemoClient(LLMClient):
    def __init__(self):
        self.calls = 0

    async def stream(self, conversation, **kwargs):
        self.calls += 1
        if self.calls == 1:
            yield TextDelta("I will write a file in this temporary workspace.")
            yield ToolCallComplete("demo-write", "WriteFile", {"file_path": "demo.txt", "content": "DeskMate R2"})
            yield StreamEnd("tool_use")
        else:
            yield TextDelta("The tool result has been processed.")
            yield StreamEnd("end_turn")


async def demo(root: Path, decision: str):
    provider = ProviderConfig("offline", "anthropic", "http://unused.invalid", "fake", api_key="offline-placeholder")
    runtime = Runtime(config=AppConfig(providers=[provider]), work_dir=root,
                      permission_mode=PermissionMode.DEFAULT, client_factory=lambda _: DemoClient())
    try:
        await runtime.initialize(provider)
        service = SessionService(runtime, persistent=True)
        prompt = "Create demo.txt once"
        run = service.start(prompt, interactive=True)
        try:
            async with run:
                async for envelope in run.events():
                    print(json.dumps(envelope.to_dict(), ensure_ascii=False))
                    event = envelope.event
                    if isinstance(event, PermissionRequest):
                        if decision == "cancel":
                            await run.cancel()
                        else:
                            assert run.reply(run.run_id, event.request_id, decision)
        except asyncio.CancelledError:
            assert decision == "cancel" and run.status == "cancelled"
            print("Cancellation propagated after cleanup.")
        sid = service.session.session_id
        service.resume(sid)
        before = list(service.conversation.history)
        service.resume(sid)
        assert service.conversation.history == before
        assert sum(m.content == prompt for m in before) == 1
        assert (root / "demo.txt").exists() == (decision == "allow")
        print(f"status={run.status}; file_created={(root / 'demo.txt').exists()}; user_input_count=1; repeated_resume_unchanged=True")
        print(f"session={sid}; temporary workspace is removed on exit")
    finally:
        await runtime.aclose()
        await runtime.aclose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision", choices=["allow", "deny", "cancel"], default="allow")
    args = parser.parse_args()
    with TemporaryDirectory(prefix="deskmate-r2-") as directory:
        root = Path(directory)
        home = root / "isolated-home"
        home.mkdir()
        # Never read personal permissions, memory, configuration or credentials.
        with patch.object(Path, "home", return_value=home):
            asyncio.run(demo(root, args.decision))


if __name__ == "__main__":
    main()
