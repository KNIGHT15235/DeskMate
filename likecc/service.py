"""Single-session orchestration, independent of Textual and transport adapters.

One service leases one Runtime. Closing a run leaves delegated background work
alive; closing the Runtime closes the service before its tools and clients.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import aclosing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from copy import deepcopy
from typing import AsyncIterator
from weakref import WeakValueDictionary

from likecc.agent import AgentEvent, CompactNotification, ErrorEvent, LoopComplete, ToolResultEvent
from likecc.conversation import ConversationManager, Message, ToolResultBlock
from likecc.interaction import Interaction
from likecc.memory import MemoryManager, SessionManager, find_relevant_memories, render_reminder, generate_session_summary
from likecc.memory.session import RecordType, SessionRecord, make_compact_boundary
from likecc.runtime import finish_cleanup

_session_owners: WeakValueDictionary = WeakValueDictionary()
log = logging.getLogger(__name__)


@dataclass
class RunEvent:
    run_id: str
    session_id: str
    event: AgentEvent

    def to_dict(self) -> dict:
        return {"run_id": self.run_id, "session_id": self.session_id,
                "type": type(self.event).__name__, "data": asdict(self.event)}


class RunHandle:
    """One live subscription. Use `async with handle` even when breaking early."""

    def __init__(self, service: SessionService, interactive: bool, timeout: float):
        self.service = service
        self.interaction = Interaction(timeout=timeout)
        self.run_id = self.interaction.run_id
        self.session_id = service.session.session_id if service.session else ""
        self.interactive = interactive
        self.status = "running"
        self.answer = ""
        self.error: BaseException | None = None
        self._queue: asyncio.Queue[RunEvent | None] = asyncio.Queue()
        self._subscribed = False
        self._task: asyncio.Task | None = None
        self._started = False
        self._cancel_requested = False

    def reply(self, run_id: str, request_id: str, value) -> bool:
        return self.interaction.reply(run_id, request_id, value)

    def _emit(self, event: AgentEvent) -> None:
        self._queue.put_nowait(RunEvent(self.run_id, self.session_id, event))

    async def events(self) -> AsyncIterator[RunEvent]:
        if self._subscribed:
            raise RuntimeError("A run supports one event consumer")
        self._subscribed = True
        try:
            while (event := await self._queue.get()) is not None:
                yield event
            await self.result()
        finally:
            await self.cancel()

    async def result(self) -> str:
        await asyncio.shield(self._task)
        if self.error is not None:
            raise self.error
        if self.status == "cancelled":
            raise asyncio.CancelledError
        if self.status != "completed":
            raise RuntimeError(f"Agent run ended with status: {self.status}")
        return self.answer

    async def cancel(self) -> None:
        if self._task is None:
            return
        # Let the worker enter its try/finally even if cancelled before scheduled.
        if not self._task.done() and self.status == "running":
            self._cancel_requested = True
            if self._started:
                self._task.cancel()
        await finish_cleanup(self._task)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.cancel()


class SessionService:
    def __init__(self, runtime, *, persistent: bool = False, memory: bool = False,
                 summaries: bool = False, cleanup_sessions: bool = False, affairs=None):
        if runtime.agent is None or runtime.closed:
            raise RuntimeError("Initialize Runtime before creating a service")
        if getattr(runtime, "service", None) is not None:
            raise RuntimeError("Runtime already has a session service")
        self.runtime = runtime
        self.agent = runtime.agent
        self.affairs = affairs
        self._tool_session_root = self.agent.session_dir
        self.conversation = ConversationManager()
        self.session_manager = SessionManager(runtime.work_dir) if persistent else None
        self.memory_manager = MemoryManager(runtime.work_dir) if memory else None
        self.summaries = summaries
        self.session = None
        self.active_run: RunHandle | None = None
        self.last_run: RunHandle | None = None
        self._close_task: asyncio.Task | None = None
        self._background: set[asyncio.Task] = set()
        self._saved: dict[int, Message] = {}  # retain identities; avoid id reuse
        self._mcp_injected = False
        self._recall_message = None
        if cleanup_sessions and self.session_manager:
            self.session_manager.cleanup()
        try:
            self.new_session()
        except BaseException:
            if self.session:
                self.session.close()
                _session_owners.pop((self.runtime.work_dir, self.session.session_id), None)
            raise
        self.agent.memory_manager = self.memory_manager
        runtime.service = self

    def _ensure_idle(self):
        if self._close_task is not None:
            raise RuntimeError("Session service is closing")
        if self.active_run is not None:
            raise RuntimeError("Session already has an active run")

    def _bind_session(self):
        from likecc.filehistory import FileHistory
        self._token_baseline = self.session.meta.total_tokens if self.session else 0
        self.agent.reset_session_context()
        self.agent.session_dir = self._tool_session_root / uuid.uuid4().hex
        self.agent.session_dir.mkdir(parents=True, exist_ok=True)
        self.agent.session_id = self.session.session_id if self.session else ""
        self.file_history = FileHistory(self.runtime.work_dir, self.session.session_id) if self.session and self.affairs is None else None
        if self.affairs is not None:
            self.affairs.begin("")
        self.agent.file_history = self.file_history
        for tool in self.runtime.registry.list_tools():
            if hasattr(tool, "file_history"):
                tool.file_history = self.file_history

    def new_session(self):
        self._ensure_idle()
        new = self.session_manager.create() if self.session_manager else None
        if self.session:
            self.session.close()
            _session_owners.pop((self.runtime.work_dir, self.session.session_id), None)
        self.session = new
        if new:
            _session_owners[(self.runtime.work_dir, new.session_id)] = self
        self.conversation = ConversationManager()
        self._saved.clear()
        self._mcp_injected = False
        self._bind_session()
        return new

    def resume(self, session_id: str):
        self._ensure_idle()
        if self.session_manager is None:
            raise RuntimeError("Persistence is disabled")
        owner = _session_owners.get((self.runtime.work_dir, session_id))
        if owner is not None and owner is not self:
            raise RuntimeError("Session is already open in another service")
        result = self.session_manager.resume(session_id)
        if result is None:
            return None
        if self.session:
            self.session.close()
            _session_owners.pop((self.runtime.work_dir, self.session.session_id), None)
        self.session = result.session
        _session_owners[(self.runtime.work_dir, session_id)] = self
        # R1 sometimes saved generated static context. Recognize only its exact
        # envelope; reload current context instead of duplicating stale copies.
        original_count = len(result.messages)
        result.messages = [m for m in result.messages if not (
            m.role == "user" and (
                (m.content.startswith("Current working directory: ") and "\nOperating system: " in m.content and "\nCurrent time: " in m.content)
                or m.content.startswith("<system-reminder>\nAs you answer the user's questions, you can use the following context:\n")
            )
        )]
        self.conversation = ConversationManager(history=result.messages)
        self._saved = {id(m): m for m in result.messages}
        self._mcp_injected = False
        self._bind_session()
        # A new boundary makes a previously truncated crash tail non-authoritative
        # without deleting audit history or replaying orphan tool calls.
        if result.recovered_tail or len(result.messages) != original_count:
            self.session.append_record(make_compact_boundary("", result.messages))
        return result

    def start(self, prompt: str, *, interactive: bool = False, permission_timeout: float = 300) -> RunHandle:
        self._ensure_idle()
        if self.affairs is not None:
            self.affairs.begin(prompt)
        handle = RunHandle(self, interactive, permission_timeout)
        self.active_run = self.last_run = handle
        handle._task = asyncio.create_task(self._execute(handle, prompt), name=f"session-run-{handle.run_id}")
        return handle

    async def run_to_completion(self, prompt: str) -> str:
        async with self.start(prompt) as run:
            # Drain events so long runs do not retain every text delta.
            async for _ in run.events():
                pass
            return await run.result()

    async def cancel(self):
        if self.active_run:
            await self.active_run.cancel()

    def _state(self, run: RunHandle):
        if self.session:
            self.session.append_record(SessionRecord(
                RecordType.RUN_STATE, {"run_id": run.run_id, "status": run.status}, datetime.now(timezone.utc)))

    def _flush(self):
        if self.session:
            for message in self.conversation.history:
                if id(message) not in self._saved and not message.transient:
                    self.session.append(message)
                    self._saved[id(message)] = message

    def record_compact(self, notification: CompactNotification):
        if self.session and notification.boundary:
            keep = [m for m in notification.boundary.keep if not m.transient]
            self.session.append_record(make_compact_boundary(notification.boundary.summary, keep))
            self._saved = {id(m): m for m in self.conversation.history}

    def _repair_interrupted_tools(self, results: dict[str, ToolResultEvent]):
        pending = {}
        for m in self.conversation.history:
            for call in m.tool_uses:
                pending[call.tool_use_id] = call
            for result in m.tool_results:
                pending.pop(result.tool_use_id, None)
        if pending:
            self.conversation.add_tool_results_message([
                ToolResultBlock(tool_id, results[tool_id].output, results[tool_id].is_error)
                if tool_id in results else ToolResultBlock(tool_id,
                    "Execution interrupted; outcome unknown. Check external state before retrying; side effects may already exist.", True)
                for tool_id in pending
            ])

    async def _execute(self, run: RunHandle, prompt: str):
        run._started = True
        results = {}
        fatal_reported = False
        terminal = LoopComplete(0, status="failed")
        try:
            self._state(run)
            if run._cancel_requested:
                raise asyncio.CancelledError
            extensions = getattr(self.runtime, "extensions", None)
            if extensions:
                await extensions.wait_ready()
                for diagnostic in extensions.diagnostics:
                    run._emit(ErrorEvent(diagnostic))
            if self._recall_message is not None:
                self.conversation.history = [m for m in self.conversation.history if m is not self._recall_message]
                self.conversation.baseline_tokens = 0
                self._recall_message = None
            # Prepare static context first and exclude it from user history.
            self.agent.prepare_context(self.conversation)
            if prompt:
                self.conversation.add_user_message(prompt)
            self._flush()
            if extensions and extensions.mcp_instructions and not self._mcp_injected:
                self._add_transient(extensions.mcp_instructions)
                self._mcp_injected = True
            if prompt and self.memory_manager:
                reminder = await self.recall(prompt)
                if reminder:
                    self._add_transient(reminder)
                    self._recall_message = self.conversation.history[-1]
            async with aclosing(self.agent.run(self.conversation, interaction=run.interaction if run.interactive else None)) as events:
                async for event in events:
                    if isinstance(event, LoopComplete):
                        terminal = event
                        continue  # publish only after persistence and final state
                    if isinstance(event, CompactNotification):
                        self.record_compact(event)
                    if isinstance(event, ToolResultEvent):
                        results[event.tool_id] = event
                    if self.affairs is not None:
                        self.affairs.observe(event)
                    if isinstance(event, ErrorEvent) and event.fatal:
                        fatal_reported = True
                    self._flush()
                    run._emit(event)
            run.status, run.answer = terminal.status, terminal.result
        except asyncio.CancelledError:
            run.status = "cancelled"
        except Exception as exc:
            run.status, run.error = "failed", exc
            if not fatal_reported:
                run._emit(ErrorEvent(str(exc), fatal=True))
        finally:
            run.interaction.close()
            try:
                if self.affairs is not None:
                    self.affairs.finish()
                if run.status != "completed":
                    self._repair_interrupted_tools(results)
                self._flush()
                if self.session:
                    self.session.meta.total_tokens = self._token_baseline + self.agent.total_input_tokens + self.agent.total_output_tokens
                self._state(run)
                if run.status == "completed":
                    self._schedule_followup()
            except Exception as exc:
                run.status, run.error = "failed", exc
                run._emit(ErrorEvent(f"Session persistence failed: {exc}", fatal=True))
            self.active_run = None
            run._emit(LoopComplete(terminal.total_turns, status=run.status, result=run.answer))
            run._queue.put_nowait(None)

    def _add_transient(self, content: str):
        self.conversation.add_system_reminder(content)
        message = self.conversation.history[-1]
        message.transient = True

    async def recall(self, query: str) -> str:
        from likecc import client as clients
        from likecc.tools.base import TextDelta
        async def selector(system_prompt, user_message):
            client = clients.create_client(self.runtime.provider)
            try:
                conv = ConversationManager(history=[Message(role="user", content=user_message)])
                async with aclosing(client.stream(conv, system=system_prompt)) as events:
                    return "".join([e.text async for e in events if isinstance(e, TextDelta)])
            finally:
                await finish_cleanup(asyncio.create_task(client.aclose()))
        try:
            results = await asyncio.wait_for(find_relevant_memories(
                query=query, user_mem_dir=self.memory_manager.user_mem_dir,
                project_mem_dir=self.memory_manager.project_mem_dir,
                recent_tools=None, already_surfaced=None, selector=selector), timeout=3.0)
            return render_reminder(results)
        except Exception:
            return ""

    def _schedule_followup(self):
        session = self.session
        extract = self.memory_manager and self.agent._loop_count % 5 == 0
        if not extract and not (self.summaries and session):
            return
        conversation = deepcopy(self.conversation)
        async def followup():
            if extract:
                await self.agent._extract_memories(conversation)
            if self.summaries and session:
                summary = await generate_session_summary(self.runtime.client, conversation, self.agent.protocol)
                if summary and session is self.session and not session._file.closed:
                    session.meta.summary = summary
                    session.meta.save(session._sessions_dir / f"{session.session_id}.meta")
        task = asyncio.create_task(followup(), name="session-followup")
        self._background.add(task)
        def finished(task):
            self._background.discard(task)
            if not task.cancelled() and task.exception() is not None:
                log.error("Session follow-up failed", exc_info=task.exception())
        task.add_done_callback(finished)

    async def aclose(self, *, extract_memories: bool = False):
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._close(extract_memories))
        await finish_cleanup(self._close_task)

    async def _close(self, extract: bool):
        try:
            await self.cancel()
            tasks = list(self._background)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if extract and self.memory_manager:
                try:
                    await asyncio.wait_for(self.agent._extract_memories(self.conversation), 3)
                except Exception:
                    pass
        finally:
            if self.session:
                self.session.close()
                _session_owners.pop((self.runtime.work_dir, self.session.session_id), None)
