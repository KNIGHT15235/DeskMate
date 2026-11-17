from __future__ import annotations

import asyncio
from contextlib import aclosing
from dataclasses import asdict
from copy import deepcopy
import json

import pytest
from pydantic import BaseModel

from likecc.agent import Agent, LoopComplete, PermissionRequest, StreamText, ToolResultEvent
from likecc.client import LLMClient
from likecc.conversation import ConversationManager
from likecc.interaction import Interaction, PermissionResponse, UserInputRequest
from likecc.permissions import DangerousCommandDetector, PathSandbox, PermissionChecker, RuleEngine
from likecc.tools import ToolRegistry
from likecc.tools.ask_user import AskUserTool
from likecc.tools.base import Tool, ToolResult, TextDelta, ToolCallComplete, StreamEnd


class Params(BaseModel):
    pass


class WriteCounter(Tool):
    name = "WriteCounter"
    description = "Write a counter"
    category = "write"
    params_model = Params

    def __init__(self):
        self.calls = 0

    async def execute(self, params):
        self.calls += 1
        return ToolResult("counter updated")


class ScriptClient(LLMClient):
    def __init__(self, turns):
        self.turns = iter(turns)
        self.requests = []
        self.finalized = 0

    async def stream(self, conversation, **kwargs):
        self.requests.append(deepcopy(conversation.get_messages()))
        try:
            for event in next(self.turns):
                yield event
        finally:
            self.finalized += 1


def make_agent(tmp_path, turns, *, checker=True):
    tool = WriteCounter()
    registry = ToolRegistry()
    registry.register(tool)
    registry.register(AskUserTool())
    permission = PermissionChecker(DangerousCommandDetector(), PathSandbox(str(tmp_path)), RuleEngine()) if checker else None
    return Agent(ScriptClient(turns), registry, "anthropic", str(tmp_path), permission_checker=permission), tool


def turns():
    return [[TextDelta("intermediate"), ToolCallComplete("write", "WriteCounter", {}), StreamEnd("tool_use")],
            [TextDelta("final"), StreamEnd("end_turn")]]


@pytest.mark.asyncio
@pytest.mark.parametrize("approve", [True, False])
async def test_permission_reply_is_correlated_single_use_and_serializable(tmp_path, approve):
    agent, tool = make_agent(tmp_path, turns())
    interaction = Interaction()
    request = None
    async with aclosing(agent.run(ConversationManager(), interaction=interaction)) as events:
        async for event in events:
            if isinstance(event, PermissionRequest):
                request = event
                json.dumps(asdict(event))
                assert not interaction.reply("another-run", event.request_id, PermissionResponse.ALLOW)
                assert not interaction.reply(event.run_id, "unknown", PermissionResponse.ALLOW)
                assert interaction.reply(event.run_id, event.request_id, PermissionResponse.ALLOW if approve else PermissionResponse.DENY)
                assert not interaction.reply(event.run_id, event.request_id, PermissionResponse.ALLOW)
    assert tool.calls == int(approve)
    assert interaction.pending_count == 0
    assert not interaction.reply(request.run_id, request.request_id, PermissionResponse.ALLOW)


@pytest.mark.asyncio
async def test_absent_handler_denies_without_waiting(tmp_path):
    agent, tool = make_agent(tmp_path, turns())
    assert await asyncio.wait_for(agent.run_to_completion("write"), 2) == "final"
    assert tool.calls == 0
    assert any("cannot prompt" in r.content for m in agent.client.requests[-1] for r in m.tool_results)


@pytest.mark.asyncio
async def test_stream_and_completion_share_tool_behavior_and_final_answer(tmp_path):
    first, a = make_agent(tmp_path, turns(), checker=False)
    second, b = make_agent(tmp_path, turns(), checker=False)
    events = [e async for e in first.run(ConversationManager())]
    callback = []
    result = await second.run_to_completion("", event_callback=callback.append)
    assert a.calls == b.calls == 1
    assert result == events[-1].result == "final"
    assert [e.output for e in events if isinstance(e, ToolResultEvent)] == ["counter updated"]
    assert [e['type'] for e in callback].count('tool_use') == 1
    assert first.client.finalized == second.client.finalized == 2


@pytest.mark.asyncio
async def test_empty_final_answer_does_not_return_intermediate_text(tmp_path):
    script = turns()
    script[-1] = [StreamEnd("end_turn")]
    agent, _ = make_agent(tmp_path, script, checker=False)
    assert await agent.run_to_completion("") == ""


@pytest.mark.asyncio
async def test_limit_is_not_a_successful_partial_answer(tmp_path):
    agent, _ = make_agent(tmp_path, turns(), checker=False)
    agent.max_iterations = 1
    with pytest.raises(RuntimeError, match="limit"):
        await agent.run_to_completion("")


@pytest.mark.asyncio
async def test_permission_wait_cancellation_invalidates_request(tmp_path):
    agent, tool = make_agent(tmp_path, turns())
    interaction = Interaction()
    received = asyncio.Event()
    requests = []

    async def consume():
        async with aclosing(agent.run(ConversationManager(), interaction=interaction)) as events:
            async for event in events:
                if isinstance(event, PermissionRequest):
                    requests.append(event)
                    received.set()

    task = asyncio.create_task(consume())
    await asyncio.wait_for(received.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 2)
    assert interaction.pending_count == 0
    assert not interaction.reply(interaction.run_id, requests[0].request_id, "allow")
    assert tool.calls == 0


@pytest.mark.asyncio
async def test_closing_consumer_closes_model_generator(tmp_path):
    agent, _ = make_agent(tmp_path, [[TextDelta("part"), StreamEnd("end_turn")]])
    async with aclosing(agent.run(ConversationManager())) as events:
        assert isinstance(await anext(events), StreamText)
    assert agent.client.finalized == 1


@pytest.mark.asyncio
async def test_ask_user_is_delivered_before_tool_waits(tmp_path):
    script = [[ToolCallComplete("ask", "AskUserQuestion", {"questions": [
        {"type": "text", "name": "answer", "message": "Choose?"},
    ]}), StreamEnd("tool_use")], [TextDelta("done"), StreamEnd("end_turn")]]
    agent, _ = make_agent(tmp_path, script)
    interaction = Interaction()
    async with aclosing(agent.run(ConversationManager(), interaction=interaction)) as events:
        async for event in events:
            if isinstance(event, UserInputRequest):
                assert interaction.reply(event.run_id, event.request_id, {"answer": "yes"})
    assert any("answer: yes" in r.content for m in agent.client.requests[-1] for r in m.tool_results)
    headless, _ = make_agent(tmp_path, script)
    assert await asyncio.wait_for(headless.run_to_completion("ask"), 2) == "done"
    assert any(r.is_error for m in headless.client.requests[-1] for r in m.tool_results)
    from likecc.tools.ask_user import AskUserParams
    direct = await asyncio.wait_for(AskUserTool().execute(AskUserParams.model_validate(script[0][0].arguments)), 2)
    assert direct.is_error and "interactive run" in direct.output


@pytest.mark.asyncio
async def test_abandoned_permission_handler_times_out_to_denial(tmp_path):
    agent, tool = make_agent(tmp_path, turns())
    interaction = Interaction(timeout=0.01)
    async def consume():
        return [e async for e in agent.run(ConversationManager(), interaction=interaction)]
    events = await asyncio.wait_for(consume(), 2)
    assert tool.calls == 0
    assert events[-1].status == "completed"
    assert interaction.pending_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["model", "tool"])
async def test_cancel_reaps_current_model_or_tool(tmp_path, phase):
    entered, closed = asyncio.Event(), asyncio.Event()
    agent, tool = make_agent(tmp_path, turns(), checker=False)

    async def blocked_tool(params):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            closed.set()

    async def blocked_model(*args, **kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
            yield TextDelta("unreachable")
        finally:
            closed.set()

    if phase == "model":
        agent.client.stream = blocked_model
    else:
        tool.execute = blocked_tool
    task = asyncio.create_task(agent.run_to_completion("start"))
    await asyncio.wait_for(entered.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 2)
    assert closed.is_set()


@pytest.mark.asyncio
async def test_bash_cancellation_reaps_process_and_closes_child_pipes(monkeypatch):
    import os
    from likecc.tools.bash import Bash, Params
    if os.name != "posix":
        pytest.skip("WSL/POSIX process group contract")
    started = asyncio.Event()
    processes = []
    original = asyncio.create_subprocess_shell
    async def create(*args, **kwargs):
        proc = await original(*args, **kwargs)
        processes.append(proc)
        started.set()
        return proc
    monkeypatch.setattr(asyncio, "create_subprocess_shell", create)
    task = asyncio.create_task(Bash().execute(Params(command="sleep 60")))
    await asyncio.wait_for(started.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 2)
    assert processes[0].returncode is not None
    await asyncio.wait_for(processes[0].communicate(), 2)
