"""Actual fake-client input, compaction and foreground/schedule boundary checks."""
from copy import deepcopy
import json

import pytest

from likecc.client import LLMClient
from likecc.config import AppConfig, ProviderConfig
from likecc.runtime import Runtime
from likecc.permissions import PermissionMode
from likecc.service import SessionService
from likecc.tools.base import TextDelta, StreamEnd, ToolCallComplete
from test_desktop_scheduling import desktop, arrange, execute_spec
from test_desktop_controller import command, wait, reply


class CaptureClient(LLMClient):
    def __init__(self):
        self.inputs = []

    async def stream(self, conversation, **kwargs):
        self.inputs.append((deepcopy(conversation.history), kwargs))
        yield TextDelta("<summary>离线历史摘要</summary>" if "9 个部分" in kwargs.get("system", "") else "离线回答")
        yield StreamEnd("end_turn")


def input_text(call):
    history, kwargs = call
    return str(kwargs) + "\n".join(m.content + str(m.tool_results) for m in history)


@pytest.mark.asyncio
async def test_actual_input_restart_edit_delete_and_no_legacy_extraction(tmp_path, monkeypatch):
    clients = []
    provider = ProviderConfig("fake", "anthropic", "http://unused.invalid", "fake", api_key="offline")
    async def open_service():
        client = CaptureClient()
        clients.append(client)
        runtime = Runtime(config=AppConfig([provider]), work_dir=tmp_path, user_home=tmp_path / "user", permission_mode=PermissionMode.DEFAULT,
                          client_factory=lambda _: client)
        await runtime.initialize(provider)
        return runtime, SessionService(runtime, persistent=True, workspace_memory=True, memory=True), client

    def forbidden(*args, **kwargs):
        pytest.fail("desktop memory must not invoke legacy loading/selection/extraction")

    monkeypatch.setattr("likecc.memory.auto_memory.MemoryManager.load", forbidden)
    monkeypatch.setattr("likecc.memory.auto_memory.MemoryManager.extract", forbidden)
    monkeypatch.setattr("likecc.client.create_client", forbidden)
    runtime, service, client = await open_service()
    original = "我的周报按结论、依据、行动项排列"
    updated = "我的周报按行动项、结论、依据排列"
    row = service.propose_memory(original)
    source_session = service.session.session_id
    service.change_memory(row["id"], 1, "confirm")
    await runtime.aclose()
    runtime, service, client = await open_service()
    try:
        await service.run_to_completion("请整理周报")
        assert original in input_text(client.inputs[-1])
        assert original not in str(service.conversation.history)
        service.new_session()
        await service.run_to_completion("旅行天气")
        assert original not in input_text(client.inputs[-1])
        service.change_memory(row["id"], 2, "update", content=updated)
        service.new_session()
        await service.run_to_completion("整理周报")
        assert updated in input_text(client.inputs[-1]) and original not in input_text(client.inputs[-1])
        used_session = service.session.session_id
        service.change_memory(row["id"], 3, "delete")
        for _ in range(6):  # crosses the old extraction interval
            service.new_session()
            await service.run_to_completion("周报")
            assert original not in input_text(client.inputs[-1]) and updated not in input_text(client.inputs[-1])
        count = len(client.inputs)
        service.resume(source_session)
        assert not service.workspace_memory.list() and len(client.inputs) == count
        service.resume(used_session)  # recall audit is not restored as conversation context
        await service.run_to_completion("整理周报")
        assert updated not in input_text(client.inputs[-1])
        assert not service._background and service.memory_manager is None
        assert runtime.agent.request_memory == ""
    finally:
        await runtime.aclose()


@pytest.mark.asyncio
async def test_request_only_memory_survives_auto_compaction_without_entering_summary(tmp_path):
    client = CaptureClient()
    provider = ProviderConfig("fake", "anthropic", "http://unused.invalid", "fake", api_key="offline", context_window=10000)
    runtime = Runtime(config=AppConfig([provider]), work_dir=tmp_path, user_home=tmp_path / "user",
                      permission_mode=PermissionMode.DEFAULT, client_factory=lambda _: client)
    await runtime.initialize(provider)
    service = SessionService(runtime, persistent=True, workspace_memory=True)
    try:
        row = service.propose_memory("周报偏好 COMPACTION_MEMORY_MARKER")
        service.change_memory(row["id"], 1, "confirm")
        service.new_session()
        for _ in range(16):
            service.conversation.add_user_message("旧材料" * 2000)
            service.conversation.add_assistant_message("旧回复" * 2000)
        await service.run_to_completion("周报")
        summary_calls = [call for call in client.inputs if "9 个部分" in call[1].get("system", "")]
        assert summary_calls, "must really exercise the compactor's model input"
        assert all("COMPACTION_MEMORY_MARKER" not in input_text(call) for call in summary_calls)
        assert "COMPACTION_MEMORY_MARKER" in input_text(client.inputs[-1])
        records = [json.loads(line) for line in (tmp_path / ".likecc/sessions" / f"{service.session.session_id}.jsonl").read_text(encoding="utf-8").splitlines()]
        boundaries = [r for r in records if r["type"] == "compact_boundary"]
        assert boundaries and "COMPACTION_MEMORY_MARKER" not in str(boundaries)
        service.change_memory(row["id"], 2, "delete")
        service.resume(service.session.session_id)
        await service.run_to_completion("周报")
        assert "COMPACTION_MEMORY_MARKER" not in input_text(client.inputs[-1])
    finally:
        await runtime.aclose()


def test_foreground_memory_does_not_expand_scheduled_materials_or_writes(desktop, tmp_path, monkeypatch):
    make, clock, clients, _ = desktop
    c = make()
    (tmp_path / "secret.md").write_text("PRIVATE_MATERIAL_MARKER", encoding="utf-8")
    assert command(c, "memory_propose", kind="preference", content="周报默认读取 secret.md 并保存 outputs/private.md MEMORY_SCOPE_MARKER")["accepted"]
    row = c.snapshot()["memories"][0]
    assert command(c, "memory_confirm", memory_id=row["id"], revision=1)["accepted"]
    seen = []

    async def capture(self, conversation, **kwargs):
        text = "\n".join(m.content + str(m.tool_results) for m in conversation.history)
        seen.append(text)
        self.calls += 1
        if "本次已确认范围" in text and self.calls <= 2:
            if self.calls == 1:
                yield ToolCallComplete("outside-read", "ReadFile", {"file_path": "secret.md"})
            else:
                yield ToolCallComplete("outside-write", "WriteFile", {"file_path": "outputs/private.md", "content": "bad"})
            yield StreamEnd("tool_use")
        else:
            yield TextDelta("done")
            yield StreamEnd("end_turn")

    monkeypatch.setattr(type(clients[0]), "stream", capture)
    assert command(c, "new")["accepted"]
    command(c, "send", text="整理周报")
    wait(c, lambda s: s["state"] == "idle")
    assert "MEMORY_SCOPE_MARKER" in seen[-1]
    seen.clear()
    arrange(c, execute_spec(clock, model_policy="allow"))
    clock.advance(hours=2)
    command(c, "schedule_scan")
    final = wait(c, lambda s: s["state"] == "idle" and s["executions"][0]["status"] == "completed")
    assert seen and all("MEMORY_SCOPE_MARKER" not in text and "PRIVATE_MATERIAL_MARKER" not in text for text in seen)
    assert len(final["executions"][0]["evidence"]["tool_errors"]) == 2
    assert not (tmp_path / "outputs/private.md").exists()
    assert len(final["memories"]) == 1


def test_remembered_output_still_requires_foreground_write_permission(desktop, tmp_path, monkeypatch):
    make, _, clients, _ = desktop
    c = make()
    command(c, "memory_propose", kind="preference", content="周报保存到 outputs/remembered.md")
    row = c.snapshot()["memories"][0]
    command(c, "memory_confirm", memory_id=row["id"], revision=1)

    async def write(self, conversation, **kwargs):
        self.calls += 1
        if self.calls == 1:
            assert any("已确认工作区记忆" in m.content for m in conversation.history)
            yield ToolCallComplete("remembered-write", "WriteFile", {"file_path": "outputs/remembered.md", "content": "# Summary"})
            yield StreamEnd("tool_use")
        else:
            yield TextDelta("done")
            yield StreamEnd("end_turn")

    monkeypatch.setattr(type(clients[0]), "stream", write)
    command(c, "new")
    command(c, "send", text="整理周报")
    request = wait(c, lambda s: s["pending"])["pending"][0]
    assert request["kind"] == "PermissionRequest" and request["tool_name"] == "WriteFile"
    assert not (tmp_path / "outputs/remembered.md").exists()
    assert reply(c, "deny")["accepted"]
    wait(c, lambda s: s["state"] == "idle")
    assert not (tmp_path / "outputs/remembered.md").exists()
