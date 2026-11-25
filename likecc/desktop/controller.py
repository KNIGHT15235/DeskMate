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
import hashlib
import json
import re
from dataclasses import asdict

from likecc.config import AppConfig, ConfigError, ProviderConfig, load_config
from likecc.affairs import install_materials_profile
from likecc.extensions import ExtensionOptions, RuntimeExtensions
from likecc.permissions import PermissionMode
from likecc.runtime import Runtime
from likecc.service import SessionService
from likecc.scheduling import ScheduleStore, TaskSpec, ExecutionScope, parse_schedule, utc_now, stamp

MAX_ROWS = 200
MAX_TEXT = 12000
MAX_DISPLAY_CHARS = 180000
MAX_RECEIPTS = 32
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
    def __init__(self, options: DesktopOptions, *, runtime_factory=Runtime, clock=utc_now, config_loader=None):
        self._options = options
        self._runtime_factory = runtime_factory
        self._config_loader = config_loader or load_config
        self._clock = clock
        self._lock = threading.Lock()
        self._receipts = {}
        self._view = {"revision": 0, "state": "starting", "session_id": "", "run_id": "",
                      "rows": [], "pending": [], "sessions": [], "notice": "",
                      "command": None, "demo": options.demo, "workspace": "", "provider": "",
                      "worker_thread": None, "materials": None, "tasks": [], "executions": [],
                      "schedule_draft": None, "scheduled_execution": None, "scheduler_error": "",
                      "memories": [], "memory_details": None, "memory_proposal": None,
                      "recalled_memories": [], "memory_source_available": False}
        self._view.update(notifications=[], notification_settings={}, notification_due=False,
                          notification_target=None, notification_alert=None, artifact_preview=None)
        self._loop = None
        self._close_requested = threading.Event()
        self._shutdown_error = None
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
        if not self.is_alive and self._shutdown_error is not None:
            raise RuntimeError("后台资源关闭失败") from self._shutdown_error
        return not self.is_alive

    def snapshot(self) -> dict:
        with self._lock:
            return deepcopy(self._view)

    def submit_ui(self, command: str, **data) -> str | None:
        """Reserve a receipt before submitting; unconsumed receipts are never evicted."""
        command_id = uuid.uuid4().hex
        reply = command == "reply"
        with self._lock:
            # A full ordinary queue must not delay a permission or question reply.
            used = sum((name == "reply") == reply for name, _ in self._receipts.values())
            if used >= (1 if reply else MAX_RECEIPTS):
                return None
            self._receipts[command_id] = (command, None)
        self._submit(command_id, command, data)
        return command_id

    def take_receipts(self):
        with self._lock:
            ready = [key for key, (_, receipt) in self._receipts.items() if receipt is not None]
            return [self._receipts.pop(key)[1] for key in ready]

    def _ack(self, command_id, accepted, message):
        receipt = {"id": command_id, "accepted": accepted, "message": message}
        with self._lock:
            if command_id in self._receipts:
                self._receipts[command_id] = (self._receipts[command_id][0], receipt)
            self._view["command"] = receipt
            self._view["revision"] += 1

    def submit(self, command: str, **data) -> str:
        """Submit control/diagnostic commands without reserving UI receipt capacity."""
        command_id = uuid.uuid4().hex
        self._submit(command_id, command, data)
        return command_id

    def _submit(self, command_id, command, data):
        if command == "close":
            self._close_requested.set()
        loop = self._loop
        if loop is None or not self.is_alive:
            self._ack(command_id, False, "后台尚未就绪或已关闭")
            return
        payload = deepcopy(data)
        try:
            loop.call_soon_threadsafe(self._schedule, command_id, command, payload)
        except RuntimeError:
            self._ack(command_id, False, "后台已关闭")

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
            self._shutdown_error = exc
            self._row("error", f"后台退出异常：{type(exc).__name__}: {exc}")
        finally:
            with self._lock:
                for key, (command, receipt) in self._receipts.items():
                    if receipt is None:
                        self._receipts[key] = (command, {"id": key, "accepted": False, "message": "后台已关闭"})
                self._view.update(state="closed", pending=[])
                self._view["revision"] += 1

    async def _lifetime(self):
        self._loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        self._commands = set()
        self._runtime = self._service = self._run = self._consumer = None
        self._affairs = None
        self._demo_dir = None
        self._closing = False
        self._store = self._scheduled_runtime = self._scheduled_service = self._scheduled_affairs = None
        self._execution_id = self._foreground_view = self._schedule_draft = None
        self._evidence_errors = []
        self._scheduled_cancel_requested = False
        self._tick_lock = asyncio.Lock()
        self._poller = asyncio.create_task(self._scheduler_loop())
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
            self._poller.cancel()
            await asyncio.gather(self._poller, return_exceptions=True)
            for task in list(self._commands):
                task.cancel()
            await asyncio.gather(*self._commands, return_exceptions=True)
            try:
                await self._release()
            finally:
                self._loop = None

    async def _release(self):
        if self._scheduled_runtime:
            await self._scheduled_runtime.aclose()
            if self._consumer:
                await asyncio.gather(self._consumer, return_exceptions=True)
        if self._runtime:
            try:
                await self._runtime.aclose()
            except Exception as exc:
                raise RuntimeError(f"运行资源尚未关闭: {exc}") from exc
        if self._consumer:
            await asyncio.gather(self._consumer, return_exceptions=True)
        self._runtime = self._service = self._run = self._consumer = None
        self._affairs = None
        self._scheduled_runtime = self._scheduled_service = self._scheduled_affairs = None
        self._execution_id = self._foreground_view = None
        if self._store:
            self._store.close()
            self._store = None
        if self._demo_dir:
            try:
                self._demo_dir.cleanup()
            except OSError as exc:
                raise OSError(f"运行资源已关闭，临时目录尚未删除: {exc}") from exc
            self._demo_dir = None

    async def _open(self, options):
        self._set(state="starting", pending=[], workspace="", provider="", session_id="", sessions=[], run_id="", materials=None,
                  tasks=[], executions=[], schedule_draft=None, scheduler_error="", memories=[],
                  memory_details=None, memory_proposal=None, recalled_memories=[], memory_source_available=False,
                  notifications=[], notification_settings={}, notification_due=False,
                  notification_target=None, notification_alert=None, artifact_preview=None)
        self._schedule_draft = None
        released = False
        try:
            await self._release()
            released = True
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
                config = self._config_loader(work_dir=workspace)
                provider = next((p for p in config.providers if p.name == options.provider), None) if options.provider else config.providers[0]
                if provider is None:
                    raise ValueError(f"Provider 未找到：{options.provider}")
                client_factory = None
            self._set(workspace=str(workspace), provider=f"{provider.name} / {provider.model}", demo=options.demo)
            self._runtime = self._runtime_factory(config=config, work_dir=workspace,
                permission_mode=PermissionMode.DEFAULT, user_home=user_home, client_factory=client_factory)
            self._runtime.retry_close_errors = True
            extensions = RuntimeExtensions(self._runtime, ExtensionOptions(
                interactive_tools=True, skills=options.skills and not options.demo,
                hooks=options.hooks and not options.demo, mcp=options.mcp and not options.demo))
            await self._runtime.initialize(provider)
            if not options.demo:
                self._affairs = install_materials_profile(self._runtime)
            await extensions.initialize()
            if options.demo:
                self._runtime.registry.register(DemoWait())
            # Delegation/worktree/plan completion are deliberately unavailable in
            # this first desktop adapter. TUI registries are separate instances.
            for name in ("ExitPlanMode", "EnterPlanMode", "SyntheticOutput"):
                self._runtime.registry.disable(name)
            self._service = SessionService(self._runtime, persistent=True,
                workspace_memory=True, summaries=options.summaries and not options.demo, affairs=self._affairs)
            self._store = ScheduleStore(workspace, clock=self._clock)
            self._options = options
            self._sessions()
            self._memory_view()
            # Publish readiness together with restored history. File I/O can
            # release the GIL, so publishing idle first exposes a partial view.
            self._set(state="idle", rows=[], pending=[], run_id="", notice="",
                      session_id=self._service.session.session_id, materials=self._materials(),
                      **self._schedule_values())
        except Exception as exc:
            detail = "配置结构或 YAML 格式无效（不展示可能含凭据的原始配置片段）" if isinstance(exc, ConfigError) else str(exc)
            if released:
                try:
                    await self._release()
                except Exception as cleanup_error:
                    detail += f"。清理失败：{cleanup_error}"
            self._set(state="error", pending=[], workspace="", provider="", session_id="", sessions=[])
            self._row("error", f"启动失败：{type(exc).__name__}: {detail}；可重试或进入离线演示。")

    def _schedule(self, command_id, command, data):
        if self._closing:
            self._ack(command_id, False, "正在关闭")
            return
        task = asyncio.create_task(self._dispatch(command_id, command, data))
        self._commands.add(task)
        task.add_done_callback(self._commands.discard)

    async def _dispatch(self, command_id, command, data):
        accepted, message = True, "已接受"
        try:
            view = self.snapshot()
            state = view["state"]
            if (command in {"send", "new", "resume"} or command.startswith(("schedule_", "memory_"))):
                if "workspace" in data and data["workspace"] != view["workspace"]:
                    raise ValueError("工作区已变化，请刷新后重新操作")
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
                if request["kind"] == "PermissionRequest":
                    if not isinstance(value, str) or value not in {"allow", "deny"}:
                        raise ValueError("桌面只允许本次批准或拒绝")
                elif not isinstance(value, dict) or not all(
                        isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
                    raise ValueError("补充回答必须是问题名到文本的映射")
                if not self._request_is_live(request):
                    raise RuntimeError("后端未接受回复：请求已过期或已处理")
                # Commit the decision before releasing the tool. No await may
                # separate this liveness check, commit and in-loop reply.
                self._store.notifications.resolve(data["run_id"], request_id=data["request_id"],
                    resolution=value if request["kind"] == "PermissionRequest" else "answered")
                if not self._run.reply(data["run_id"], data["request_id"], value):
                    raise RuntimeError("后端未接受回复：请求已过期或已处理")
                self._set(pending=[], state="running")
                try:
                    self._notification_view()
                except Exception as exc:
                    # A display refresh cannot turn an accepted grant into a
                    # rejected command; the scheduler will refresh again.
                    self._set(scheduler_error=f"回复已保存，通知刷新失败：{type(exc).__name__}: {exc}")
            elif command.startswith("notification_"):
                await self._notification_command(command, data)
            elif command == "artifact_preview":
                snapshot = self.snapshot()
                workspace = data.get("workspace")
                if not workspace or snapshot["workspace"] != workspace or state in {"starting", "error", "closing", "closed"}:
                    raise ValueError("工作区已变化，请重新选择成果")
                artifacts = (snapshot.get("materials") or {}).get("artifacts", [])
                artifacts += [a for e in snapshot["executions"] for a in e["evidence"].get("artifacts", [])]
                result = {"token": command_id, "workspace": workspace}
                try:
                    if data.get("path") not in {a["path"] for a in artifacts}:
                        raise ValueError("该路径不是当前工作区记录的成果")
                    from .artifacts import read_artifact
                    result["text"] = await asyncio.to_thread(read_artifact, workspace, data["path"])
                except (OSError, ValueError) as exc:
                    result["text"] = "无法预览：" + str(exc)
                    accepted, message = False, str(exc)
                if self.snapshot()["workspace"] == workspace:
                    self._set(artifact_preview=result)
            elif command.startswith("schedule_"):
                await self._schedule_command(command, data)
            elif command.startswith("memory_"):
                if state != "idle" or self._service is None:
                    raise RuntimeError("请等待当前运行结束后管理记忆")
                self._memory_command(command, data)
            elif command in {"send", "new", "resume", "open", "demo"}:
                if state not in {"idle", "error"}:
                    raise RuntimeError("运行或启动期间不能提交、切换会话/工作区/Provider")
                if command in {"open", "demo"}:
                    options = DesktopOptions(**data) if command == "open" else DesktopOptions(demo=True)
                    await self._open(options)
                    if self.snapshot()["state"] == "error":
                        raise RuntimeError("启动失败，见诊断")
                else:
                    if state != "idle" or self._service is None:
                        raise RuntimeError("请先选择有效配置或进入离线演示")
                    if command == "send":
                        prompt = data["text"].strip()
                        if not prompt:
                            raise ValueError("输入不能为空")
                        remember = re.match(r"^(?:请记住|记住)[，,:：\s]*(.+)$", prompt, re.S)
                        if remember:
                            row = self._service.propose_memory(remember[1], quote=prompt)
                            self._set(memory_proposal=row["id"])
                            self._memory_view()
                            self._sessions()
                            self._row("user", prompt)
                            self._row("status", "请在工作区记忆窗口核对类型、内容和来源，然后确认保存。")
                            self._ack(command_id, True, "已生成待确认记忆，尚未参与召回")
                            return
                        if re.search(r"每周|明天.*提醒|明晚.*提醒|\d{4}-\d{2}-\d{2}.*提醒", prompt):
                            self._prepare_schedule(parse_schedule(prompt, now=self._clock()))
                            self._ack(command_id, True, "已解析安排，请核对时间、时区、范围后确认保存")
                            return
                        self._run = self._service.start(prompt, interactive=True, permission_timeout=self._options.permission_timeout)
                        self._set(state="running", run_id=self._run.run_id, pending=[], materials=self._materials())
                        self._row("user", prompt)
                        self._consumer = asyncio.create_task(self._consume(self._run))
                    else:
                        if command == "new":
                            self._service.new_session()
                        else:
                            if self._service.resume(data["session_id"]) is None:
                                raise ValueError("会话未找到")
                        self._set(rows=[], run_id="", pending=[], session_id=self._service.session.session_id,
                                  materials=self._materials())
                        for m in self._service.conversation.history:
                            if not m.transient:
                                if m.content:
                                    self._row(m.role, m.content)
                                for call in m.tool_uses:
                                    self._row("tool", f"{call.tool_name}: {call.arguments}", tool_id=call.tool_use_id)
                                for result in m.tool_results:
                                    self._row("tool_error" if result.is_error else "result", result.content, tool_id=result.tool_use_id)
                        self._sessions()
                        self._memory_view()
            else:
                raise ValueError(f"未知命令：{command}")
        except Exception as exc:
            accepted, message = False, str(exc)
            if command == "notification_alert":
                # Every rejection, including a workspace handover, must release
                # Qt's in-flight token even if another command overwrites ack.
                self._set(notification_alert={"request_token": data.get("request_token"),
                    "workspace": data.get("workspace"), "delivery": None, "failed": True})
        self._ack(command_id, accepted, message)

    def _sessions(self):
        self._set(sessions=[{"id": m.id, "title": m.title or "未命名", "count": m.message_count}
                            for m in self._service.session_manager.list()[:100]])

    def _memory_view(self):
        store = self._service.workspace_memory
        if store is not None and store.db is None:
            return  # a closing consumer must not query an already closed SQLite handle
        self._set(memories=store.list() if store else [],
            memory_source_available=bool(self._service.last_source_id),
            recalled_memories=deepcopy(self._service.recalled_memories))

    def _memory_command(self, command, data):
        service = self._service
        if command == "memory_propose":
            row = service.propose_memory(data["content"], data["kind"], from_run=data.get("from_run", False))
            self._set(memory_proposal=row["id"])
            self._sessions()
        elif command == "memory_view":
            self._set(memory_details=service.workspace_memory.details(data["memory_id"]))
        elif command in {"memory_confirm", "memory_update", "memory_delete"}:
            values = {k: data[k] for k in ("kind", "content") if k in data}
            service.change_memory(data["memory_id"], data["revision"], command.removeprefix("memory_"), **values)
            self._set(memory_details=None, memory_proposal=None)
        else:
            raise ValueError("未知记忆命令")
        self._memory_view()

    def _provider_identity(self):
        p = self._runtime.provider
        fingerprint = hashlib.sha256(f"{p.protocol}\n{p.base_url}\n{p.model}".encode()).hexdigest()[:12]
        return f"{p.name} / {p.model} · {fingerprint}"

    def _schedule_view(self):
        if self._store:
            self._set(**self._schedule_values())

    def _schedule_values(self):
        return dict(tasks=self._store.tasks(), executions=self._store.executions(), **self._notification_values())

    def _notification_view(self):
        if self._store:
            self._set(**self._notification_values())

    def _notification_values(self):
        from likecc.notifications import is_quiet
        ledger = self._store.notifications
        return dict(notifications=ledger.rows(), notification_settings=ledger.settings(),
                    notification_due=bool(ledger.due()), notification_quiet=is_quiet(self._clock(), ledger.settings()))

    def _request_is_live(self, row):
        run = self._run
        return bool(run and run.status == "running" and run.run_id == row["run_id"]
            and run.session_id == row["session_id"]
            and run.interaction.is_pending(row["request_id"])
            and (not row.get("execution_id") or self._execution_id == row["execution_id"]))

    def _expire_notification_requests(self):
        # Timeout/answer may finish a Future before its ToolResult is consumed.
        # The single visible card is not authoritative for other live requests.
        ledger = self._store.notifications
        for row in ledger.active_requests():
            if not self._request_is_live(row):
                ledger.resolve(row["run_id"], request_id=row["request_id"])

    async def _notification_command(self, command, data):
        state = self.snapshot()
        if (not self._store or data.get("workspace") != self._store.workspace
                or state["workspace"] != self._store.workspace
                or state["state"] in {"starting", "error", "closing", "closed"}
                or self._closing or self._close_requested.is_set()):
            raise ValueError("工作区已变化，请在当前通知中心重新选择")
        ledger = self._store.notifications
        if command == "notification_configure":
            ledger.configure(data["settings"])
        elif command == "notification_alert":
            alert = {"request_token": data["request_token"],
                     "workspace": self._store.workspace, "delivery": None}
            self._expire_notification_requests()
            alert["delivery"] = ledger.claim_alert()
            values = self._notification_values()
            self._set(notification_alert=alert, **values)
        else:
            # Re-read source facts before interpreting a click from a detached UI.
            with self._store.transaction():
                pass
            row = ledger.get(data["notification_id"])
            if row["revision"] != data["revision"]:
                raise ValueError("通知已变化，请刷新后重新选择")
            execution = self._store.execution(row["execution_id"]) if row["execution_id"] else None
            request = next((p for p in self.snapshot()["pending"] if p["request_id"] == row["request_id"]
                and p["run_id"] == row["run_id"] and p["session_id"] == row["session_id"]), None)
            live_request = bool(request and self.snapshot()["state"] == "waiting"
                                and self._request_is_live(row))
            if command == "notification_open":
                ledger.change(row["id"], row["revision"], "view")
                mode = "request" if row["kind"] == "request" and row["valid"] and live_request else (
                    "execution" if execution else "history")
                self._set(notification_target={"token": uuid.uuid4().hex, "workspace": self._store.workspace,
                    "notification_id": row["id"], "mode": mode, "task_id": row["task_id"],
                    "execution_id": row["execution_id"], "run_id": row["run_id"],
                    "request_id": row["request_id"], "session_id": row["session_id"]}, **self._schedule_values())
            elif command in {"notification_snooze", "notification_dismiss"}:
                if command == "notification_snooze" and row["kind"] == "request" and not live_request:
                    raise ValueError("请求已经结束，只能查看历史")
                ledger.change(row["id"], row["revision"], command.removeprefix("notification_"),
                              minutes=data.get("minutes", 10))
            elif command in {"notification_cancel_execution", "notification_stop_task"}:
                if not execution or not row["valid"]:
                    raise ValueError("该事项已结束，请从任务历史查看")
                if row["kind"] == "request" and not live_request:
                    raise ValueError("请求已经结束，不能取消其他运行")
                if command == "notification_stop_task":
                    task = self._store.task(execution["task_id"])
                    if task["revision"] != data.get("task_revision") or not task["enabled"]:
                        raise ValueError("安排已变化，请重新查看")
                    await self._schedule_command("schedule_cancel", {"task_id": task["id"]})
                elif execution["status"] in {"running", "waiting"}:
                    if self._execution_id != execution["id"]:
                        raise ValueError("本次执行已不在运行，请刷新核对")
                    self._scheduled_cancel_requested = True
                    if self._run:
                        self._set(state="cancelling", pending=[])
                        await self._run.cancel()
                elif not self._store.cancel_execution(execution["id"]):
                    raise ValueError("本次执行已经结束，只能查看历史")
            else:
                raise ValueError("未知通知命令")
        self._schedule_view()

    def _prepare_schedule(self, spec, *, task_id=None, revision=None, preview_id=None):
        if not self._store or not self._runtime:
            raise RuntimeError("请先打开工作区")
        if spec.kind == "execute" and self._options.demo:
            raise ValueError("临时演示工作区只演示提醒；资料定时执行请使用持久工作区")
        spec.provider = self._provider_identity() if spec.kind == "execute" else ""
        spec = spec.validated(self._store.workspace)
        self._schedule_draft = {"token": uuid.uuid4().hex, "spec": asdict(spec),
            "workspace": self._store.workspace, "task_id": task_id, "revision": revision,
            "preview_id": preview_id}
        self._set(schedule_draft=deepcopy(self._schedule_draft))

    async def _schedule_command(self, command, data):
        view = self.snapshot()
        if (not self._store or view["workspace"] != self._store.workspace
                or view["state"] in {"starting", "closing", "closed"}
                or (view["state"] == "error" and command != "schedule_scan")):
            raise RuntimeError("工作区切换中或调度器未就绪，请稍后重新操作")
        # In an error state, scan still publishes existing diagnostic evidence;
        # _tick_schedules itself refuses to dispatch work until recovery.
        if command == "schedule_preview":
            spec = TaskSpec(**data["spec"]) if "spec" in data else parse_schedule(
                data["text"], now=self._clock(), timezone_name=data.get("timezone", "Asia/Shanghai"))
            self._prepare_schedule(spec, task_id=data.get("task_id"), revision=data.get("revision"),
                                   preview_id=data.get("preview_id"))
        elif command == "schedule_confirm":
            draft = self._schedule_draft
            if not draft or draft["token"] != data["token"]:
                raise ValueError("预览已变化，请重新核对")
            self._store.save(TaskSpec(**draft["spec"]), task_id=draft["task_id"], revision=draft["revision"])
            self._schedule_draft = None
            self._set(schedule_draft=None)
        elif command == "schedule_discard":
            self._schedule_draft = None
            self._set(schedule_draft=None)
        elif command == "schedule_cancel":
            self._store.cancel(data["task_id"])
            if self._execution_id and self._store.execution(self._execution_id)["task_id"] == data["task_id"]:
                self._scheduled_cancel_requested = True
                if self._run:
                    await self._run.cancel()
        elif command == "schedule_complete":
            self._store.complete_reminder(data["execution_id"])
        elif command == "schedule_allow_model":
            self._store.approve_model(data["execution_id"])
        elif command == "schedule_retry":
            if not data.get("execution_id") or data.get("reviewed_execution_id") != data["execution_id"]:
                raise ValueError("请先核对旧次会话、成果和磁盘状态")
            self._store.retry(data["execution_id"])
        elif command == "schedule_scan":
            await self._tick_schedules()
        else:
            raise ValueError("未知调度命令")
        self._schedule_view()

    async def _scheduler_loop(self):
        while True:
            await asyncio.sleep(0.25)
            try:
                await self._tick_schedules()
            except Exception as exc:
                # Keep the UI available; do not silently lose the polling task.
                self._set(scheduler_error=f"调度暂停：{type(exc).__name__}: {exc}")

    async def _tick_schedules(self):
        async with self._tick_lock:
            if self._closing or self._close_requested.is_set() or not self._store:
                return
            if self.snapshot()["state"] in {"starting", "error", "closing", "closed"}:
                return
            self._expire_notification_requests()
            self._store.scan()
            rows = [e for e in reversed(self._store.executions()) if e["status"] == "queued"]
            if rows and (self._run is not None or self.snapshot()["state"] != "idle"):
                for row in rows:
                    if "等待当前" not in row["reason"]:
                        self._store.update(row["id"], reason=row["reason"] + "等待当前前台/定时事务结束；单次活动运行。")
            elif rows:
                await self._start_scheduled(rows[0])
            if self.snapshot()["scheduler_error"]:
                self._set(scheduler_error="")
            self._schedule_view()

    def _save_evidence(self):
        if self._execution_id and self._scheduled_affairs:
            evidence = self._scheduled_affairs.summary()
            evidence["digests"] = {p: e.get("digest") for p, e in self._scheduled_affairs.artifacts.items()}
            evidence["write_intents"] = deepcopy(self._scheduled_affairs.write_intents)
            evidence["tool_errors"] = list(self._evidence_errors)
            self._store.update(self._execution_id, evidence=evidence)

    async def _start_scheduled(self, row):
        spec = row["snapshot"]
        if spec["provider"] != self._provider_identity():
            self._store.update(row["id"], status="awaiting_model", reason="模型配置已变化；请编辑安排并重新预览确认新模型范围")
            return
        if not self._store.start(row["id"]):
            return
        self._execution_id = row["id"]
        self._scheduled_cancel_requested = False
        current = self.snapshot()
        self._foreground_view = {k: current.get(k) for k in ("rows", "session_id", "run_id", "materials", "notice", "last_status", "recalled_memories")}
        self._set(state="running", rows=[], pending=[], recalled_memories=[], scheduled_execution=row["id"],
            notice="正在处理定时资料任务；结束后恢复原聊天，草稿保留。")
        try:
            # A fresh Runtime keeps foreground conversation/context fully intact.
            # Only one RunHandle is active; the same _consume is the sole reader.
            runtime = self._runtime_factory(config=self._runtime.config, work_dir=self._store.workspace,
                permission_mode=PermissionMode.DEFAULT, user_home=self._runtime.user_home,
                client_factory=self._runtime._client_factory)
            self._scheduled_runtime = runtime
            runtime.retry_close_errors = True
            # The snapshot's material list also bounds the initial model input.
            # LIKECC.md / @include must not read unconfirmed files implicitly.
            await runtime.initialize(self._runtime.provider, load_instruction_files=False)
            self._scheduled_affairs = install_materials_profile(runtime)
            extensions = RuntimeExtensions(runtime, ExtensionOptions(interactive_tools=True))
            await extensions.initialize()
            runtime.checker.scheduled_scope = ExecutionScope(spec)
            if self._scheduled_cancel_requested or self._close_requested.is_set():
                self._store.update(row["id"], status="cancelled" if self._scheduled_cancel_requested else "interrupted",
                    ended_at=stamp(self._clock()), reason="启动期间取消/退出；没有启动模型执行")
                await runtime.aclose()
                self._restore_foreground()
                return
            self._scheduled_service = SessionService(runtime, persistent=True, affairs=self._scheduled_affairs,
                workspace_memory=False, memory=False)
            self._evidence_errors = []
            self._scheduled_affairs.on_change = self._save_evidence
            prompt = (spec["content"] + "\n本次已确认范围（不能从网页或模型回答扩大）：\n" +
                json.dumps({k: spec[k] for k in ("workspace", "files", "urls", "outputs")}, ensure_ascii=False) +
                "\n读取需要更新的现有输出后再写入，写入后用 ReadFile 回读核对。")
            self._run = self._scheduled_service.start(prompt, interactive=True, permission_timeout=self._options.permission_timeout)
            self._scheduled_affairs.urls = set(spec["urls"])
            self._store.update(row["id"], session_id=self._run.session_id, run_id=self._run.run_id)
            self._set(session_id=self._run.session_id, run_id=self._run.run_id, materials=self._materials())
            self._row("user", prompt)
            self._consumer = asyncio.create_task(self._consume(self._run))
        except BaseException:
            try:
                try:
                    # Cancel the handle before yielding to Runtime cleanup. A
                    # newly created task must not start the model after its link
                    # failed to persist, nor remain as a stale dispatcher lock.
                    links = {}
                    if self._run is not None:
                        links = {"session_id": self._run.session_id, "run_id": self._run.run_id}
                        await self._run.cancel()
                    self._store.update(row["id"], status="interrupted", ended_at=stamp(self._clock()),
                        reason="定时运行启动中断，请查看会话及成果后明确重试", **links)
                finally:
                    if self._scheduled_runtime:
                        await self._scheduled_runtime.aclose()
            except BaseException as cleanup_error:
                # Retain ownership/resources for _release() to retry. Publishing
                # idle here would allow dispatch with an unknown database state.
                self._set(state="closing" if self._closing else "error", pending=[],
                    scheduler_error=f"启动恢复或资源关闭失败：{cleanup_error}；停止后续执行，请重新打开工作区")
                raise
            self._run = self._consumer = None
            self._restore_foreground()
            raise

    def _restore_foreground(self):
        self._scheduled_runtime = self._scheduled_service = self._scheduled_affairs = None
        self._execution_id = None
        self._set(**(self._foreground_view or {}), scheduled_execution=None,
            state="closing" if self._closing else "idle", pending=[],
            **self._schedule_values())
        self._foreground_view = None

    async def _finish_scheduled(self, run):
        self._save_evidence()
        summary = self._scheduled_affairs.summary()
        uncertain_write = any(intent["status"] == "write_unverified"
            for intent in self._scheduled_affairs.write_intents.values())
        status = "interrupted" if self._closing or uncertain_write else run.status
        outputs = summary["artifacts"]
        reason = ("应用退出中断，请核对已有成果再明确重试。" if self._closing else
            "运行结束；" + ("成果状态见回读证据。" if outputs else "没有已写入的成果。"))
        if status == "failed":
            reason = f"运行失败：{run.error or '请查看本次会话诊断'}。"
        if uncertain_write:
            reason = "写入可能已部分或全部发生，结果尚未核实；请核对会话、成果和磁盘后明确重试。"
        if self._evidence_errors:
            reason += "存在工具拒绝或失败，详见本次证据。"
        self._store.update(self._execution_id, status=status, ended_at=stamp(self._clock()), reason=reason)
        await self._scheduled_runtime.aclose()
        self._restore_foreground()
        self._schedule_view()

    def _materials(self):
        affairs = self._scheduled_affairs if self._execution_id else self._affairs
        return affairs.summary() if affairs is not None else None

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
                try:
                    if self._store:
                        self._store.notifications.resolve(run.run_id)
                    if self._execution_id:
                        await self._finish_scheduled(run)
                except Exception as exc:
                    self._run = None
                    self._set(state="error", pending=[], scheduler_error=f"运行通知、执行证据或资源收尾失败：{exc}；停止后续执行，请核对后重新打开工作区")
                    self._row("error", "运行收尾失败，已停止后续领取；已有成果可能存在。")
                    return
                self._set(pending=[], state="closing" if self._closing else "idle")
                self._run = None
                self._sessions()
                self._memory_view()
                self._notification_view()

    def _event(self, event):
        if event["run_id"] != self.snapshot()["run_id"] or event["session_id"] != self.snapshot()["session_id"]:
            return
        kind, data = event["type"], event["data"]
        if self._store:
            if kind in {"PermissionRequest", "UserInputRequest"}:
                if not self._request_is_live({"run_id": event["run_id"],
                        "session_id": event["session_id"], "request_id": data["request_id"],
                        "execution_id": self._execution_id}):
                    return  # a queued event cannot revive an already ended Future
                if not self._store.notifications.request(event, self._execution_id):
                    return  # a delayed duplicate cannot resurrect a resolved request
            elif kind == "ToolResultEvent":
                self._store.notifications.resolve(event["run_id"], tool_id=data["tool_id"])
            elif kind == "LoopComplete":
                self._store.notifications.resolve(event["run_id"])
        if self._execution_id:
            if kind == "ToolResultEvent":
                if data["is_error"]:
                    self._evidence_errors.append({"tool_id": data["tool_id"], "output": data["output"][:3000]})
                self._store.update(self._execution_id, status="running")
            if kind in {"PermissionRequest", "UserInputRequest", "ToolResultEvent", "LoopComplete", "ErrorEvent"}:
                self._save_evidence()
                if kind not in {"PermissionRequest", "UserInputRequest"}:
                    self._schedule_view()
        if kind == "MemoryRecall":
            self._set(recalled_memories=data["memories"])
        elif kind == "StreamText":
            self._text(data["text"])
        elif kind in {"PermissionRequest", "UserInputRequest"}:
            if kind == "UserInputRequest" and any(q.get("type") not in SUPPORTED_QUESTIONS for q in data["questions"]):
                self._row("error", "不支持的问题类型；已取消运行，避免无限等待。")
                self._schedule(uuid.uuid4().hex, "cancel", {})
                return
            self._set(state="waiting", pending=[{**data, "kind": kind, "session_id": event["session_id"]}],
                      **self._schedule_values())
        elif kind == "ToolUseEvent":
            self._row("tool", f"{data['tool_name']}: {data['arguments']}", tool_id=data["tool_id"])
        elif kind == "ToolResultEvent":
            self._row("tool_error" if data["is_error"] else "result", data["output"], tool_id=data["tool_id"])
            with self._lock:
                if self._affairs is not None or self._scheduled_affairs is not None:
                    self._view["materials"] = self._materials()
                    self._view["revision"] += 1
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
            self._set(pending=[], last_status=data["status"], materials=self._materials())
        elif kind in {"HookEvent", "CompactNotification", "RetryEvent"}:
            self._row("diagnostic", str(data))
        if kind in {"PermissionRequest", "UserInputRequest", "ToolResultEvent", "LoopComplete"}:
            self._notification_view()
