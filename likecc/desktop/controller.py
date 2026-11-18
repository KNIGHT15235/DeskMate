"""Application-owned worker. This module has no Qt dependency.

The UI sends commands, then polls detached bounded display snapshots. It never
receives Runtime, RunHandle, asyncio tasks, queues or futures.
"""
from __future__ import annotations

import asyncio
from contextlib import aclosing
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import threading
from tempfile import TemporaryDirectory
import uuid

from likecc.config import AppConfig, ConfigError, ProviderConfig, load_config
from likecc.extensions import ExtensionOptions, RuntimeExtensions
from likecc.permissions import PermissionMode
from likecc.runtime import Runtime
from likecc.service import SessionService

MAX_ROWS = 200
MAX_TEXT = 12000
MAX_DISPLAY_CHARS = 180000
SUPPORTED_QUESTIONS = {"text", "radio", "select", "checkbox"}


@dataclass(frozen=True)
class DesktopOptions:
    work_dir: str = "."
    demo: bool = False
    provider: str | None = None
    skills: bool = False
    mcp: bool = False
    hooks: bool = False
    memory: bool = False
    summaries: bool = False
    permission_timeout: float = 300


class DesktopController:
    def __init__(self, options: DesktopOptions, *, runtime_factory=Runtime):
        self._options = options
        self._runtime_factory = runtime_factory
        self._lock = threading.Lock()
        self._view = {"revision": 0, "state": "starting", "session_id": "", "run_id": "",
                      "rows": [], "pending": [], "sessions": [], "notice": "",
                      "command": None, "demo": options.demo, "workspace": "", "provider": "",
                      "worker_thread": None}
        self._loop = None
        self._close_requested = threading.Event()
        self._thread = threading.Thread(target=self._thread_main, name="deskmate-asyncio", daemon=False)
        self._thread.start()

    @property
    def is_alive(self):
        return self._thread.is_alive()

    def request_close(self) -> None:
        """Nonblocking application close, including before the worker loop is ready."""
        self._close_requested.set()
        if self.is_alive:
            self.submit("close")

    def wait_closed(self, timeout: float = 5.0) -> bool:
        """Bounded fallback before/after Qt exec; never use in a live GUI slot.

        Running GUIs should request_close and poll is_alive instead. All resource
        cleanup stays in the worker; joining only waits for that thread to exit.
        """
        if threading.current_thread() is self._thread:
            raise RuntimeError("Worker cannot wait for its own exit")
        self._thread.join(timeout=timeout)
        return not self.is_alive

    def snapshot(self) -> dict:
        with self._lock:
            return deepcopy(self._view)

    def submit(self, command: str, **data) -> str:
        """Nonblocking thread-safe submission; acceptance arrives in snapshot.command."""
        command_id = uuid.uuid4().hex
        if command == "close":
            self._close_requested.set()
        loop = self._loop
        if loop is None or not self.is_alive:
            self._set(command={"id": command_id, "accepted": False, "message": "后台尚未就绪或已关闭"})
            return command_id
        payload = deepcopy(data)
        try:
            loop.call_soon_threadsafe(self._schedule, command_id, command, payload)
        except RuntimeError:
            self._set(command={"id": command_id, "accepted": False, "message": "后台已关闭"})
        return command_id

    def _set(self, **values):
        with self._lock:
            self._view.update(values)
            self._view["revision"] += 1

    def _row(self, kind, text, **extra):
        text = str(text)
        if len(text) > MAX_TEXT:
            text = text[:MAX_TEXT] + "\n[展示截断；完整结果仍按会话规则保存]"
        with self._lock:
            self._view["rows"].append({"kind": kind, "text": text, **extra})
            self._trim()
            self._view["revision"] += 1

    def _trim(self):
        rows = self._view["rows"]
        while len(rows) > MAX_ROWS or sum(len(r["text"]) for r in rows) > MAX_DISPLAY_CHARS:
            rows.pop(0)
            self._view["notice"] = "展示缓存已截断较早内容；会话原始记录不受影响。待处理请求单独保留。"

    def _text(self, text):
        with self._lock:
            rows = self._view["rows"]
            if not rows or rows[-1]["kind"] != "assistant" or rows[-1].get("run_id") != self._run.run_id:
                rows.append({"kind": "assistant", "text": "", "run_id": self._run.run_id})
            current = rows[-1]["text"]
            if len(current) < MAX_TEXT:
                rows[-1]["text"] = (current + text)[:MAX_TEXT]
                if len(current) + len(text) > MAX_TEXT:
                    rows[-1]["text"] += "\n[展示截断；完整文本保留在会话中]"
            elif len(current) == MAX_TEXT:
                rows[-1]["text"] += "\n[展示截断；完整文本保留在会话中]"
            self._trim()
            self._view["revision"] += 1

    def _thread_main(self):
        try:
            asyncio.run(self._lifetime())
        except BaseException as exc:
            self._row("error", f"后台退出异常：{type(exc).__name__}: {exc}")
        finally:
            self._set(state="closed", pending=[])

    async def _lifetime(self):
        self._loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        self._commands = set()
        self._runtime = self._service = self._run = self._consumer = None
        self._demo_dir = None
        self._closing = False
        self._set(worker_thread=threading.get_ident())
        try:
            opening = asyncio.create_task(self._open(self._options))
            self._commands.add(opening)
            opening.add_done_callback(self._commands.discard)
            if self._close_requested.is_set():
                self._closing = True
                self._set(state="closing")
                self._stop.set()
            await self._stop.wait()
        finally:
            self._closing = True
            for task in list(self._commands):
                task.cancel()
            await asyncio.gather(*self._commands, return_exceptions=True)
            await self._release()
            self._loop = None

    async def _release(self):
        try:
            if self._runtime:
                await self._runtime.aclose()
            if self._consumer:
                await asyncio.gather(self._consumer, return_exceptions=True)
        finally:
            self._runtime = self._service = self._run = self._consumer = None
            if self._demo_dir:
                self._demo_dir.cleanup()
                self._demo_dir = None

    async def _open(self, options):
        self._set(state="starting", pending=[])
        await self._release()
        try:
            if options.demo:
                from .demo import DemoClient, DemoWait
                self._demo_dir = TemporaryDirectory(prefix="deskmate-desktop-")
                root = Path(self._demo_dir.name)
                workspace, user_home = root / "workspace", root / "user"
                workspace.mkdir()
                user_home.mkdir()
                provider = ProviderConfig("offline-demo", "anthropic", "http://unused.invalid", "fake", api_key="offline-placeholder")
                config = AppConfig([provider])
                client_factory = lambda _: DemoClient()
            else:
                workspace, user_home = Path(options.work_dir).expanduser().resolve(), None
                if not workspace.is_dir():
                    raise ValueError(f"工作区不存在：{workspace}")
                config = load_config(work_dir=workspace)
                provider = next((p for p in config.providers if p.name == options.provider), None) if options.provider else config.providers[0]
                if provider is None:
                    raise ValueError(f"Provider 未找到：{options.provider}")
                client_factory = None
            self._set(workspace=str(workspace), provider=f"{provider.name} / {provider.model}", demo=options.demo)
            self._runtime = self._runtime_factory(config=config, work_dir=workspace,
                permission_mode=PermissionMode.DEFAULT, user_home=user_home, client_factory=client_factory)
            extensions = RuntimeExtensions(self._runtime, ExtensionOptions(
                interactive_tools=True, skills=options.skills and not options.demo,
                hooks=options.hooks and not options.demo, mcp=options.mcp and not options.demo))
            await self._runtime.initialize(provider)
            await extensions.initialize()
            if options.demo:
                self._runtime.registry.register(DemoWait())
            # Delegation/worktree/plan completion are deliberately unavailable in
            # this first desktop adapter. TUI registries are separate instances.
            for name in ("ExitPlanMode", "EnterPlanMode", "SyntheticOutput"):
                self._runtime.registry.disable(name)
            self._service = SessionService(self._runtime, persistent=True,
                memory=options.memory and not options.demo, summaries=options.summaries and not options.demo)
            self._options = options
            self._set(state="idle", rows=[], pending=[], run_id="", notice="",
                      session_id=self._service.session.session_id)
            self._sessions()
        except Exception as exc:
            await self._release()
            self._set(state="error", pending=[])
            detail = "配置结构或 YAML 格式无效（不展示可能含凭据的原始配置片段）" if isinstance(exc, ConfigError) else str(exc)
            self._row("error", f"启动失败：{type(exc).__name__}: {detail}；可重试或进入离线演示。")

    def _schedule(self, command_id, command, data):
        if self._closing:
            self._set(command={"id": command_id, "accepted": False, "message": "正在关闭"})
            return
        task = asyncio.create_task(self._dispatch(command_id, command, data))
        self._commands.add(task)
        task.add_done_callback(self._commands.discard)

    async def _dispatch(self, command_id, command, data):
        accepted, message = True, "已接受"
        try:
            state = self.snapshot()["state"]
            if command == "close":
                self._closing = True
                self._set(state="closing", pending=[])
                self._stop.set()
            elif command == "cancel":
                if not self._run or state not in {"running", "waiting", "cancelling"}:
                    raise RuntimeError("没有正在执行的请求")
                self._set(state="cancelling", pending=[])
                await self._run.cancel()
            elif command == "reply":
                if state != "waiting" or not self._run or self._run.run_id != data["run_id"]:
                    raise RuntimeError("请求已过期或属于其他运行")
                if data.get("session_id") != self._run.session_id:
                    raise RuntimeError("请求属于其他会话")
                value = data["value"]
                request = next((p for p in self.snapshot()["pending"] if p["request_id"] == data["request_id"]), None)
                if request is None:
                    raise RuntimeError("请求不存在或已回复")
                if request["kind"] == "PermissionRequest" and value not in {"allow", "deny"}:
                    raise ValueError("桌面只允许本次批准或拒绝")
                if not self._run.reply(data["run_id"], data["request_id"], value):
                    raise RuntimeError("后端未接受回复：请求已过期或已处理")
                self._set(pending=[], state="running")
            elif command in {"send", "new", "resume", "open", "demo"}:
                if state not in {"idle", "error"}:
                    raise RuntimeError("运行或启动期间不能提交、切换会话/工作区/Provider")
                if command in {"open", "demo"}:
                    options = DesktopOptions(**data) if command == "open" else DesktopOptions(demo=True)
                    await self._open(options)
                    if self.snapshot()["state"] == "error":
                        raise RuntimeError("启动失败，见诊断")
                else:
                    if self._service is None:
                        raise RuntimeError("请先选择有效配置或进入离线演示")
                    if command == "send":
                        prompt = data["text"].strip()
                        if not prompt:
                            raise ValueError("输入不能为空")
                        self._run = self._service.start(prompt, interactive=True, permission_timeout=self._options.permission_timeout)
                        self._set(state="running", run_id=self._run.run_id, pending=[])
                        self._row("user", prompt)
                        self._consumer = asyncio.create_task(self._consume(self._run))
                    else:
                        if command == "new":
                            self._service.new_session()
                        else:
                            if self._service.resume(data["session_id"]) is None:
                                raise ValueError("会话未找到")
                        self._set(rows=[], run_id="", pending=[], session_id=self._service.session.session_id)
                        for m in self._service.conversation.history:
                            if not m.transient:
                                if m.content:
                                    self._row(m.role, m.content)
                                for call in m.tool_uses:
                                    self._row("tool", f"{call.tool_name}: {call.arguments}", tool_id=call.tool_use_id)
                                for result in m.tool_results:
                                    self._row("tool_error" if result.is_error else "result", result.content, tool_id=result.tool_use_id)
                        self._sessions()
            else:
                raise ValueError(f"未知命令：{command}")
        except Exception as exc:
            accepted, message = False, str(exc)
        self._set(command={"id": command_id, "accepted": accepted, "message": message})

    def _sessions(self):
        self._set(sessions=[{"id": m.id, "title": m.title or "未命名", "count": m.message_count}
                            for m in self._service.session_manager.list()[:100]])

    async def _consume(self, run):
        try:
            async with run, aclosing(run.events()) as events:
                async for envelope in events:
                    self._event(envelope.to_dict())
        except asyncio.CancelledError:
            pass  # terminal status was already persisted and published
        except Exception as exc:
            self._row("error", f"运行失败：{type(exc).__name__}: {exc}")
        finally:
            if self._run is run:
                self._set(pending=[], state="closing" if self._closing else "idle")
                self._run = None
                self._sessions()

    def _event(self, event):
        if event["run_id"] != self.snapshot()["run_id"] or event["session_id"] != self.snapshot()["session_id"]:
            return
        kind, data = event["type"], event["data"]
        if kind == "StreamText":
            self._text(data["text"])
        elif kind in {"PermissionRequest", "UserInputRequest"}:
            if kind == "UserInputRequest" and any(q.get("type") not in SUPPORTED_QUESTIONS for q in data["questions"]):
                self._row("error", "不支持的问题类型；已取消运行，避免无限等待。")
                self._schedule(uuid.uuid4().hex, "cancel", {})
                return
            self._set(state="waiting", pending=[{**data, "kind": kind, "session_id": event["session_id"]}])
        elif kind == "ToolUseEvent":
            self._row("tool", f"{data['tool_name']}: {data['arguments']}", tool_id=data["tool_id"])
        elif kind == "ToolResultEvent":
            self._row("tool_error" if data["is_error"] else "result", data["output"], tool_id=data["tool_id"])
            with self._lock:
                pending = self._view["pending"]
                remaining = [p for p in pending if not (
                    p["session_id"] == event["session_id"] and p["run_id"] == event["run_id"]
                    and p["tool_id"] == data["tool_id"])]
                if len(remaining) != len(pending):
                    self._view["pending"] = remaining
                    if (not remaining and self._view["state"] == "waiting" and not self._closing
                            and self._run is not None and self._run.status == "running"):
                        self._view["state"] = "running"
                    self._view["revision"] += 1
        elif kind == "ErrorEvent":
            self._row("error" if data["fatal"] else "diagnostic", data["message"])
        elif kind == "LoopComplete":
            self._row("status", f"运行结束：{data['status']}")  # result already streamed; do not repeat
            self._set(pending=[], last_status=data["status"])
        elif kind in {"HookEvent", "CompactNotification", "RetryEvent"}:
            self._row("diagnostic", str(data))
