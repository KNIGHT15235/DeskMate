"""Qt widgets are confined to the application thread; snapshots contain data only."""
from dataclasses import asdict
from pathlib import Path
import json

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QTextBrowser, QLineEdit, QComboBox, QGroupBox, QFormLayout,
    QCheckBox, QScrollArea, QStackedWidget, QButtonGroup,
)

from .controller import DesktopOptions
from likecc.scheduling import needs_attention
from .widgets import Disclosure, ArtifactPreview, text_label, update_text
from .theme import apply_theme
from .presentation import activity


def label(text=""):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    return widget


class ChatWindow(QMainWindow):
    def __init__(self, controller, options: DesktopOptions):
        super().__init__()
        self.controller, self.options = controller, options
        self.lifecycle = None
        self._revision = -1
        self._pending_key = None
        self._draft = None
        self._reply = None
        self.schedule_window = None
        self.memory_window = None
        self.notification_window = None
        self._notification_target = None
        self._shown_memory_proposal = None
        self._shown_schedule_token = None
        self._workspace_key = None
        self._workspace_drafts = {}
        self._transcript_text = ""
        self.setWindowTitle("DeskMate 桌伴")
        self.resize(1100, 720)
        apply_theme(self)
        root = QWidget()
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(12, 12, 12, 12)
        shell.setSpacing(14)
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(158)
        navigation = QVBoxLayout(sidebar)
        navigation.setSpacing(8)
        navigation.addWidget(text_label("DeskMate", "heading"))
        navigation.addWidget(text_label("桌伴 · 个人事务助手", "muted"))
        self.navigation = QButtonGroup(self)
        self.nav_buttons = {}
        for key, title in (("chat", "对话"), ("schedules", "任务"), ("memories", "记忆"),
                           ("notifications", "通知"), ("settings", "设置")):
            button = QPushButton(title)
            button.setObjectName("nav_" + key)
            button.setProperty("nav", True)
            button.setCheckable(True)
            self.navigation.addButton(button)
            self.nav_buttons[key] = button
            button.clicked.connect(lambda checked=False, page=key: self.show_page(page))
            navigation.addWidget(button)
        navigation.addStretch()
        navigation.addWidget(text_label("关闭窗口后，任务可继续运行。", "muted"))
        self.exit_button = QPushButton("退出应用")
        navigation.addWidget(self.exit_button)
        shell.addWidget(sidebar)
        main = QWidget()
        layout = QVBoxLayout(main)
        layout.setContentsMargins(0, 0, 0, 0)
        shell.addWidget(main, 1)
        self.workspace_title = text_label("正在打开工作区", "heading")
        layout.addWidget(self.workspace_title)
        self.banner = label("正在启动…")
        self.banner.setObjectName("status")
        layout.addWidget(self.banner)
        self.pages = QStackedWidget()
        self.pages.setMinimumSize(0, 0)
        layout.addWidget(self.pages, 1)
        self.chat_page = QScrollArea()
        self.chat_page.setWidgetResizable(True)
        chat_body = QWidget()
        chat_body.setObjectName("pageBody")
        self.chat_page.setWidget(chat_body)
        chat = QVBoxLayout(chat_body)
        chat.setContentsMargins(0, 0, 0, 0)
        self.pages.addWidget(self.chat_page)
        from .widgets import Page
        self.settings_page = Page(self, embedded=True)
        settings = self.settings_page.body_layout
        settings.addWidget(text_label("设置", "heading"))
        settings.addWidget(text_label("工作区与模型", "status"))
        config = QFormLayout()
        config.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        config.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.workspace = QLineEdit(options.work_dir)
        self.workspace.setPlaceholderText("工作区绝对路径")
        self.provider = QLineEdit(options.provider or "")
        self.provider.setPlaceholderText("Provider 名称（空白取首个）")
        self.open_button = QPushButton("打开工作区")
        self.demo_button = QPushButton("离线演示")
        config.addRow("工作区路径", self.workspace)
        config.addRow("Provider", self.provider)
        settings.addLayout(config)
        config_buttons = QHBoxLayout()
        config_buttons.addWidget(self.open_button)
        config_buttons.addWidget(self.demo_button)
        settings.addLayout(config_buttons)
        self.info = label()
        settings.addWidget(Disclosure("当前工作区与会话详情", self.info))
        self.task_button = self.nav_buttons["schedules"]
        self.memory_button = self.nav_buttons["memories"]
        self.notification_button = self.nav_buttons["notifications"]
        from .notifications import QuietSettings
        self.quiet_settings = QuietSettings(controller, self._submit)
        settings.addWidget(self.quiet_settings)
        settings.addStretch()
        self.pages.addWidget(self.settings_page)
        self.memory_summary = label()
        self.memory_summary.setObjectName("muted")
        session_panel = QWidget()
        sessions = QVBoxLayout(session_panel)
        sessions.setContentsMargins(0, 0, 0, 0)
        self.sessions = QComboBox()
        self.sessions.setMinimumContentsLength(12)
        self.sessions.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.new_button = QPushButton("新建会话")
        self.resume_button = QPushButton("恢复所选会话")
        sessions.addWidget(self.sessions)
        session_buttons = QHBoxLayout()
        for widget in (self.new_button, self.resume_button):
            session_buttons.addWidget(widget)
        sessions.addLayout(session_buttons)
        self.session_panel = Disclosure("切换或恢复会话", session_panel)
        chat.addWidget(self.session_panel)
        self.activity = text_label("", "status")
        chat.addWidget(self.activity)
        self.transcript = QTextBrowser()
        self.transcript.setOpenExternalLinks(False)
        self.transcript.setOpenLinks(False)
        self.transcript.setMinimumHeight(160)
        chat.addWidget(self.transcript, 1)
        self.technical = QPlainTextEdit()
        self.technical.setReadOnly(True)
        self.technical.setMaximumHeight(170)
        self.technical_panel = Disclosure("查看完整工具过程与运行详情", self.technical)
        chat.addWidget(self.technical_panel)
        chat.addWidget(self.memory_summary)
        self.materials_summary = label("")
        self.materials_summary.hide()
        self.result_panel = QWidget()
        results = QVBoxLayout(self.result_panel)
        results.setContentsMargins(0, 0, 0, 0)
        results.addWidget(self.materials_summary)
        self.artifact_preview = ArtifactPreview(self._submit)
        results.addWidget(self.artifact_preview)
        self.result_disclosure = Disclosure("最新成果与来源", self.result_panel)
        chat.addWidget(self.result_disclosure)
        self.request_area = QScrollArea()
        self.request_area.setWidgetResizable(True)
        self.request_area.setMaximumHeight(220)
        self.request_area.setMinimumHeight(150)
        self.request_area.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.request_area.hide()
        chat.addWidget(self.request_area)
        self.input = QPlainTextEdit()
        self.input.setPlaceholderText("输入任务；离线演示会依次请求写文件、问答，可选择等待取消")
        self.input.setMaximumHeight(95)
        self.input.setMinimumHeight(66)
        chat.addWidget(self.input)
        buttons = QHBoxLayout()
        self.send_button, self.cancel_button = QPushButton("发送"), QPushButton("取消本次执行")
        self.send_button.setProperty("primary", True)
        for button in (self.send_button, self.cancel_button):
            buttons.addWidget(button)
        chat.addLayout(buttons)
        self.feedback = label()
        layout.addWidget(self.feedback)
        self.pending_button = QPushButton("处理待确认请求")
        self.pending_button.setProperty("primary", True)
        self.pending_button.hide()
        layout.insertWidget(2, self.pending_button)
        self.pending_button.clicked.connect(self.focus_request)
        self.send_button.clicked.connect(self.send)
        self.cancel_button.clicked.connect(lambda: controller.submit("cancel"))
        self.new_button.clicked.connect(lambda: self._submit("new"))
        self.resume_button.clicked.connect(lambda: self._submit("resume", session_id=self.sessions.currentData()))
        self.open_button.clicked.connect(self.open_workspace)
        self.demo_button.clicked.connect(lambda: self._submit("demo"))
        self.exit_button.clicked.connect(lambda: self.lifecycle.request_exit() if self.lifecycle else controller.submit("close"))
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.show_page("chat")
        self.refresh()

    def send(self):
        text = self.input.toPlainText().strip()
        if text and self._draft is None:
            version = self.input.document().revision()
            command_id = self._submit("send", text=text)
            if command_id is not None:
                self._draft = (command_id, version, self._workspace_key, self.input.toPlainText())
                self.send_button.setEnabled(False)

    def show_schedules(self):
        if self.schedule_window is None:
            from .schedules import ScheduleWindow
            self.schedule_window = ScheduleWindow(self.controller, self._submit, self, embedded=True)
            self.pages.addWidget(self.schedule_window)
        self.schedule_window.refresh()
        self._select_page("schedules", self.schedule_window)

    def show_memories(self):
        if self.memory_window is None:
            from .memories import MemoryWindow
            self.memory_window = MemoryWindow(self.controller, self._submit, self, embedded=True)
            self.pages.addWidget(self.memory_window)
        self.memory_window.refresh()
        self._select_page("memories", self.memory_window)

    def show_notifications(self):
        if self.notification_window is None:
            from .notifications import NotificationWindow
            self.notification_window = NotificationWindow(self.controller, self._submit, self, embedded=True,
                quiet_settings=self.quiet_settings)
            self.pages.addWidget(self.notification_window)
        self.notification_window.refresh()
        self._select_page("notifications", self.notification_window)

    def _select_page(self, name, widget):
        self.pages.setCurrentWidget(widget)
        # Compatibility QDialogs can restore a previous focus widget while
        # hiding. Enforce a single visible page after that Qt transition.
        for index in range(self.pages.count()):
            page = self.pages.widget(index)
            if page is not widget:
                page.hide()
        widget.show()
        self.nav_buttons[name].setChecked(True)
        if hasattr(self, "pending_button"):
            self.pending_button.setVisible(bool(self.controller.snapshot()["pending"]) and name != "chat")

    def show_page(self, name):
        if name == "chat":
            self._select_page(name, self.chat_page)
        elif name == "settings":
            self.quiet_settings.refresh()
            self._select_page(name, self.settings_page)
        else:
            getattr(self, "show_" + name)()

    def focus_request(self):
        self.show_page("chat")
        self.chat_page.ensureWidgetVisible(self.request_area)
        self.request_area.setFocus()

    def navigate_notification(self, target, state):
        if not target or target["token"] == self._notification_target:
            return
        self._notification_target = target["token"]
        if target["workspace"] != state["workspace"]:
            return
        if target["mode"] == "request" and any(p["request_id"] == target["request_id"]
                and p["run_id"] == target["run_id"] for p in state["pending"]):
            # Keep page drafts while revealing the one authoritative card.
            self.show_page("chat")
            if self.lifecycle:
                self.lifecycle.show_window()
            else:
                self.showNormal()
                self.raise_()
                self.activateWindow()
            self.request_area.verticalScrollBar().setValue(0)
            self.chat_page.ensureWidgetVisible(self.request_area)
            self.request_area.setFocus()
            request_id = target["request_id"]
            QTimer.singleShot(0, self, lambda: self._focus_pending_card(request_id))
        elif target["execution_id"]:
            self.show_schedules()
            self.schedule_window.focus_execution(target["task_id"], target["execution_id"])
        else:
            # Ended foreground interactions have no schedule occurrence. Selecting
            # their session is navigation only; explicit Restore remains available.
            index = self.sessions.findData(target["session_id"])
            if index >= 0:
                self.sessions.setCurrentIndex(index)
            self.show_page("chat")
            self.session_panel.set_expanded(True)
            self.feedback.setText("请求已结束。可恢复所选会话查看历史，不会重新执行。")

    def _focus_pending_card(self, request_id):
        # Restore/activation events can arrive after the synchronous page change.
        # A later page choice or an expired request must not steal focus back.
        if (self.pages.currentWidget() is self.chat_page and self.isVisible()
                and any(p["request_id"] == request_id for p in self.controller.snapshot()["pending"])):
            from PySide6.QtWidgets import QApplication
            QApplication.setActiveWindow(self)
            self.chat_page.ensureWidgetVisible(self.request_area)
            self.request_area.setFocus(Qt.FocusReason.OtherFocusReason)

    def _submit(self, command, **data):
        if command in {"send", "new", "resume"} or command.startswith(("schedule_", "memory_")):
            # Bind mutations to the workspace actually displayed, including the
            # interval before Qt observes a completed worker-side handover.
            data.setdefault("workspace", self._workspace_key)
        command_id = self.controller.submit_ui(command, **data)
        if command_id is None and (self.lifecycle is None or not self.lifecycle.is_closing):
            self.feedback.setText("待确认命令已满，请稍后重试。")
        return command_id

    def open_workspace(self):
        values = asdict(self.options)
        values.update(work_dir=self.workspace.text(), provider=self.provider.text().strip() or None, demo=False)
        self._submit("open", **values)

    def refresh(self):
        state = self.controller.snapshot()
        receipts = self.controller.take_receipts()
        if state["revision"] == self._revision and not receipts:
            return
        self._revision = state["revision"]
        workspace = state["workspace"]
        if workspace != self._workspace_key:
            if self._workspace_key:
                self._workspace_drafts[self._workspace_key] = self.input.toPlainText()
            self._workspace_key = workspace
            self.input.setPlainText(self._workspace_drafts.get(workspace, ""))
            self._shown_schedule_token = self._shown_memory_proposal = None
            self._pending_key = None
            for panel in (self.schedule_window, self.memory_window, self.notification_window):
                if panel:
                    panel.refresh()
        idle = state["state"] == "idle"
        configurable = state["state"] in {"idle", "error"}
        for widget in (self.workspace, self.provider, self.open_button, self.demo_button):
            widget.setEnabled(configurable)
        for widget in (self.input, self.new_button, self.resume_button, self.sessions):
            widget.setEnabled(idle)
        self.cancel_button.setEnabled(state["state"] in {"running", "waiting"})
        names = {"starting": "启动中", "idle": "就绪", "running": "执行中", "waiting": "等待回复",
                 "cancelling": "取消中", "closing": "正在关闭资源", "closed": "已关闭", "error": "配置/启动错误"}
        self.banner.setText(("离线演示 · 无模型网络请求 | " if state["demo"] else "资料整理 | ") + names[state["state"]])
        workspace_name = Path(workspace).name if workspace else "选择工作区"
        self.workspace_title.setText(workspace_name[:32] + "  ·  " + (state["provider"] or "尚未连接"))
        self.workspace_title.setToolTip(workspace_name)
        self.activity.setText(activity(state))
        self.input.setPlaceholderText("输入任务；离线演示会依次请求写文件、问答，可选择等待取消" if state["demo"] else
            "提供公开网页 URL、工作区内的文本或 Markdown，以及要生成的 Markdown 路径")
        self.show_materials(state.get("materials"))
        self.memory_button.setText(f"记忆 · {len(state.get('memories', []))}")
        unread = sum(n["valid"] and n["state"] == "unread" for n in state.get("notifications", []))
        self.notification_button.setText(f"通知 · {unread} 未读")
        used = state.get("recalled_memories", [])
        self.memory_summary.setVisible(bool(used or state.get("scheduled_execution")))
        lines = [f"{m['content'][:80]}"
                 for m in used]
        self.memory_summary.setText("定时任务不召回前台记忆" if state.get("scheduled_execution") else
            "本次使用记忆：\n" + "\n".join(lines) if used else "本次未使用工作区记忆")
        proposal = state.get("memory_proposal")
        if proposal and proposal != self._shown_memory_proposal and self.isVisible():
            self._shown_memory_proposal = proposal
            self.show_memories()
        outstanding = sum(needs_attention(e) for e in state.get("executions", []))
        self.task_button.setText(f"任务 · {outstanding} 待处理" if outstanding else "任务")
        self.task_button.setAccessibleDescription(f"{outstanding} 项待处理/确认")
        self.task_button.setToolTip(f"{outstanding} 项待处理/确认")
        draft = state.get("schedule_draft")
        if draft and draft["token"] != self._shown_schedule_token and self.isVisible():
            self._shown_schedule_token = draft["token"]
            self.show_schedules()
        self.info.setText(f"工作区：{state['workspace']}\n模型：{state['provider']}\n会话：{state['session_id']}")
        selected = self.sessions.currentData()
        items = [(m["id"], f"{m['title'][:50]} · {m['count']} 条消息") for m in state["sessions"]]
        if items != getattr(self, "_session_items", None):
            self._session_items = items
            self.sessions.clear()
            for sid, title in items:
                self.sessions.addItem(title, sid)
            index = self.sessions.findData(selected or state["session_id"])
            self.sessions.setCurrentIndex(max(0, index))
        self.render_transcript(state)
        update_text(self.technical, json.dumps({"session_id": state["session_id"], "run_id": state["run_id"],
            "rows": self.visible_rows(state), "recalled_memories": used}, ensure_ascii=False, indent=2))
        self.artifact_preview.refresh(state, (state.get("materials") or {}).get("artifacts", []),
                                      source=(state["session_id"], state["run_id"]))
        self.quiet_settings.refresh()
        pending_key = tuple(p["request_id"] for p in state["pending"])
        self.pending_button.setVisible(bool(pending_key) and self.pages.currentWidget() is not self.chat_page)
        if pending_key != self._pending_key:
            self._pending_key = pending_key
            self.show_requests(state["pending"])
        for ack in receipts:
            if self._draft and ack["id"] == self._draft[0]:
                if ack["accepted"]:
                    if self._workspace_key == self._draft[2] and self.input.document().revision() == self._draft[1]:
                        self.input.clear()
                    elif self._workspace_drafts.get(self._draft[2]) == self._draft[3]:
                        self._workspace_drafts[self._draft[2]] = ""
                self._draft = None
            # Application-level shutdown feedback takes priority over delayed replies.
            if self.lifecycle is None or not self.lifecycle.is_closing:
                self.feedback.setText(("后端已接受：" if ack["accepted"] else "未接受：") + ack["message"])
            if self._reply and ack["id"] == self._reply[0]:
                if not ack["accepted"] and self._reply[1] in pending_key:
                    for button in self.request_area.findChildren(QPushButton):
                        button.setEnabled(True)
                self._reply = None
        self.send_button.setEnabled(idle and self._draft is None)
        self.navigate_notification(state.get("notification_target"), state)

    def render_transcript(self, state):
        names = {"user": "你", "assistant": "桌伴", "error": "需要处理"}
        rows = self.visible_rows(state)
        parts = [f"{names[r['kind']]}\n{r['text']}" for r in rows if r["kind"] in names]
        # Tool outputs stay in the expandable audit view, including literal text.
        text = "\n\n".join(parts) or "今天想完成什么？\n\n可以整理资料、安排提醒，或告诉桌伴需要记住的偏好。"
        if state["notice"]:
            text += "\n\n" + state["notice"]
        if text == self._transcript_text:
            return
        bar = self.transcript.verticalScrollBar()
        cursor = self.transcript.textCursor()
        anchor, position = cursor.anchor(), cursor.position()
        at_end, scroll = bar.value() >= bar.maximum() - 30, bar.value()
        if text.startswith(self._transcript_text) and self._transcript_text:
            end = QTextCursor(self.transcript.document())
            end.movePosition(QTextCursor.MoveOperation.End)
            end.insertText(text[len(self._transcript_text):])
        else:
            self.transcript.setPlainText(text)
        self._transcript_text = text
        cursor.setPosition(min(anchor, len(text)))
        cursor.setPosition(min(position, len(text)), QTextCursor.MoveMode.KeepAnchor)
        self.transcript.setTextCursor(cursor)
        bar.setValue(bar.maximum() if at_end and anchor == position else scroll)

    @staticmethod
    def visible_rows(state):
        if state["workspace"]:
            return state["rows"]
        # During handover the worker can still be releasing the old runtime.
        # Show startup failures, but never the previous workspace's transcript.
        return [r for r in state["rows"] if r["kind"] == "error"][-1:] if state["state"] == "error" else []

    def show_materials(self, summary):
        self.materials_summary.setVisible(summary is not None)
        self.result_disclosure.setVisible(bool(summary and (summary["sources"] or summary["artifacts"])))
        if summary is None:
            return
        sources = {"read": "已读", "truncated": "截断", "failed": "失败", "interrupted": "中断", "empty": "无可用正文"}
        artifacts = {"written": "已写入，待回读", "verified": "已回读核对",
                     "readback_failed": "回读未通过", "write_unverified": "写入未核实"}
        lines = [f"{s['id']} {sources[s['status']]} · {s['target'][:130]}"
                 for s in summary["sources"] if s["status"] in sources]
        outputs = [f"{a['path'][:160]}（{artifacts[a['status']]}）" for a in summary["artifacts"]]
        self.result_disclosure.toggle.setText("最新成果 · " + outputs[-1] if outputs else "本次来源记录")
        shown = lines[:4]
        if len(lines) > len(shown):
            shown.append(f"另有 {len(lines) - len(shown)} 项来源，详见工具记录。")
        self.materials_summary.setText("来源\n" + ("\n".join(shown) or "本次尚无读取记录")
                                       + "\n成果  " + ("；".join(outputs) or "本次尚无成果记录"))

    def show_requests(self, pending):
        old = self.request_area.takeWidget()
        if old:
            old.deleteLater()
        self.request_area.setVisible(bool(pending))
        if not pending:
            return
        request = pending[0]
        box = QGroupBox("需要你的决定（仅本次有效）")
        form = QFormLayout(box)
        if request["kind"] == "PermissionRequest":
            form.addRow(label(f"工具：{request['tool_name']}\n操作：{request['description']}"))
            for title, value in (("本次允许", "allow"), ("拒绝", "deny")):
                button = QPushButton(title)
                button.setObjectName(value)
                button.clicked.connect(lambda checked=False, v=value: self.reply(request, v))
                form.addRow(button)
        else:
            self.answer_fields = {}
            for q in request["questions"]:
                kind = q["type"]
                if kind == "text":
                    widget = QLineEdit()
                    getter = widget.text
                elif kind in {"radio", "select"}:
                    widget = QComboBox()
                    widget.addItems(q.get("options", []))
                    widget.setEditable(True)  # custom text remains possible
                    getter = widget.currentText
                elif kind == "checkbox":
                    widget = QWidget()
                    choices = QVBoxLayout(widget)
                    checks = [QCheckBox(option) for option in q.get("options", [])]
                    for check in checks:
                        choices.addWidget(check)
                    getter = lambda items=checks: ", ".join(c.text() for c in items if c.isChecked())
                else:
                    form.addRow(label(f"不支持的问题类型：{kind}；请取消运行。"))
                    continue
                widget.setObjectName(q["name"])
                self.answer_fields[q["name"]] = getter
                form.addRow(label(q["message"]), widget)
            button = QPushButton("提交回答")
            button.setObjectName("answer")
            button.clicked.connect(lambda: self.reply(request, {name: get() for name, get in self.answer_fields.items()}))
            form.addRow(button)
        cancel = QPushButton("取消运行")
        cancel.clicked.connect(lambda: self.controller.submit("cancel"))
        form.addRow(cancel)
        self.request_area.setWidget(box)

    def reply(self, request, value):
        command_id = self._submit("reply", session_id=request["session_id"], run_id=request["run_id"],
                                  request_id=request["request_id"], value=value)
        if command_id is None:
            return
        self._reply = (command_id, request["request_id"])
        for button in self.request_area.findChildren(QPushButton):
            button.setEnabled(False)
        self.feedback.setText("回复已发送，等待后端确认…")

    def closeEvent(self, event):
        event.ignore()
        if self.lifecycle:
            self.lifecycle.close_window()
        else:
            self.controller.submit("close")
