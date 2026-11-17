"""Exercise the actual terminal interaction adapter over SessionService."""
import asyncio
from pathlib import Path

import pytest

from likecc.config import ProviderConfig
from likecc.interaction import PermissionResponse
from likecc.tools.base import TextDelta, ToolCallComplete, StreamEnd
from test_execution_contract import ScriptClient


@pytest.mark.asyncio
@pytest.mark.parametrize("choice", ["allow", "deny", "cancel", "ask"])
async def test_tui_responds_through_service_and_session_commands(tmp_path, monkeypatch, choice):
    import likecc.app as ui
    from likecc.permission_dialog import InlinePermissionWidget
    from likecc.askuser_dialog import InlineAskUserWidget
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    call = ToolCallComplete("tool", "WriteFile", {"file_path": "file.txt", "content": "written"})
    if choice == "ask":
        call = ToolCallComplete("tool", "AskUserQuestion", {"questions": [{"type": "text", "name": "answer", "message": "Answer?"}]})
    client = ScriptClient([[call, StreamEnd("tool_use")], [TextDelta("done"), StreamEnd("end_turn")]])
    monkeypatch.setattr("likecc.client.create_client", lambda _: client)
    async def metadata(provider):
        pass
    monkeypatch.setattr(ui, "resolve_context_window", metadata)
    provider = ProviderConfig("offline", "anthropic", "http://unused.invalid", "fake", api_key="fake")
    app = ui.LikeCCApp([provider], work_dir=tmp_path)
    received = asyncio.Event()
    original = app._handle_askuser if choice == "ask" else app._handle_permission_request
    async def display(request):
        await original(request)
        received.set()
    monkeypatch.setattr(app, "_handle_askuser" if choice == "ask" else "_handle_permission_request", display)
    async with app.run_test(size=(100, 35)) as pilot:
        app.service.summaries = False
        app.send_user_message("test input")
        await asyncio.wait_for(received.wait(), 3)
        task = app._agent_task
        if choice == "ask":
            assert app.query_one("#askuser-inline")
            await pilot.pause()
            await pilot.press("y", "e", "s", "enter")
        elif choice == "cancel":
            app.action_cancel()
        else:
            assert app.query_one("#perm-inline")
            app.on_inline_permission_widget_responded(InlinePermissionWidget.Responded(PermissionResponse(choice)))
        await asyncio.wait_for(task, 3)
        await pilot.pause()
        assert app.service.last_run.status == ("cancelled" if choice == "cancel" else "completed")
        assert not app.query_one("#chat-input").disabled
        assert (tmp_path / "file.txt").exists() == (choice == "allow")
        if choice == "ask":
            assert any("answer: yes" in r.content for m in app.conversation.history for r in m.tool_results)
        sid = app.session.session_id
        await app._dispatch_command("/session new")
        assert app.session is app.service.session
        assert app.conversation is app.service.conversation
        await app._dispatch_command(f"/session resume {sid}")
        assert sum(m.content == "test input" for m in app.conversation.history) == 1
        assert app.conversation is app.service.conversation
        await app._dispatch_command("/clear")
        assert app.conversation is app.service.conversation
        assert not app.conversation.history
