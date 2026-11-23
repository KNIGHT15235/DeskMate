"""Qt widgets are confined to the application thread; snapshots contain data only."""
from dataclasses import asdict
from html import escape

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QTextBrowser, QLineEdit, QComboBox, QGroupBox, QFormLayout,
    QCheckBox, QScrollArea,
)

from .controller import DesktopOptions
from likecc.scheduling import needs_attention


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
        self._shown_memory_proposal = None
        self._shown_schedule_token = None
        self.setWindowTitle("DeskMate 桌伴")
        self.resize(920, 780)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        self.banner = label("正在启动…")
        self.banner.setStyleSheet("font-weight: bold; color: #245aa4")
        layout.addWidget(self.banner)
        settings = QHBoxLayout()
        self.workspace = QLineEdit(options.work_dir)
        self.workspace.setPlaceholderText("工作区绝对路径")
        self.provider = QLineEdit(options.provider or "")
        self.provider.setPlaceholderText("Provider 名称（空白取首个）")
        self.open_button = QPushButton("打开工作区")
        self.demo_button = QPushButton("离线演示")
        for widget in (self.workspace, self.provider, self.open_button, self.demo_button):
            settings.addWidget(widget)
        layout.addLayout(settings)
        self.info = label()
        layout.addWidget(self.info)
        self.task_button = QPushButton("任务与执行记录")
        self.task_button.clicked.connect(self.show_schedules)
        layout.addWidget(self.task_button)
        self.memory_button = QPushButton("工作区记忆与来源")
        self.memory_button.clicked.connect(self.show_memories)
        layout.addWidget(self.memory_button)
        self.memory_summary = label()
        layout.addWidget(self.memory_summary)
        sessions = QHBoxLayout()
        self.sessions = QComboBox()
        self.sessions.setMinimumContentsLength(28)
        self.new_button = QPushButton("新建会话")
        self.resume_button = QPushButton("恢复所选会话")
        for widget in (self.sessions, self.new_button, self.resume_button):
            sessions.addWidget(widget)
        layout.addLayout(sessions)
        self.transcript = QTextBrowser()
        self.transcript.setOpenExternalLinks(False)
        self.transcript.setOpenLinks(False)
        layout.addWidget(self.transcript, 1)
        self.materials_summary = label("")
        self.materials_summary.hide()
        layout.addWidget(self.materials_summary)
        self.request_area = QScrollArea()
        self.request_area.setWidgetResizable(True)
        self.request_area.setMaximumHeight(250)
        self.request_area.setMinimumHeight(180)
        self.request_area.hide()
        layout.addWidget(self.request_area)
        self.input = QPlainTextEdit()
        self.input.setPlaceholderText("输入任务；离线演示会依次请求写文件、问答，可选择等待取消")
        self.input.setMaximumHeight(95)
        layout.addWidget(self.input)
        buttons = QHBoxLayout()
        self.send_button, self.cancel_button = QPushButton("发送"), QPushButton("取消当前请求")
        self.exit_button = QPushButton("退出应用")
        for button in (self.send_button, self.cancel_button, self.exit_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.feedback = label()
        layout.addWidget(self.feedback)
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
        self.refresh()

    def send(self):
        text = self.input.toPlainText().strip()
        if text and self._draft is None:
            version = self.input.document().revision()
            command_id = self._submit("send", text=text)
            if command_id is not None:
                self._draft = (command_id, version)
                self.send_button.setEnabled(False)

    def show_schedules(self):
        if self.schedule_window is None:
            from .schedules import ScheduleWindow
            self.schedule_window = ScheduleWindow(self.controller, self._submit, self)
        self.schedule_window.refresh()
        self.schedule_window.show()
        self.schedule_window.raise_()

    def show_memories(self):
        if self.memory_window is None:
            from .memories import MemoryWindow
            self.memory_window = MemoryWindow(self.controller, self._submit, self)
        self.memory_window.refresh()
        self.memory_window.show()
        self.memory_window.raise_()

    def _submit(self, command, **data):
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
        idle = state["state"] == "idle"
        configurable = state["state"] in {"idle", "error"}
        for widget in (self.workspace, self.provider, self.open_button, self.demo_button):
            widget.setEnabled(configurable)
        for widget in (self.input, self.new_button, self.resume_button, self.sessions):
            widget.setEnabled(idle)
        self.cancel_button.setEnabled(state["state"] in {"running", "waiting"})
        names = {"starting": "启动中", "idle": "就绪", "running": "执行中", "waiting": "等待回复",
                 "cancelling": "取消中", "closing": "正在关闭资源", "closed": "已关闭", "error": "配置/启动错误"}
        self.banner.setText(("离线演示 · 无模型网络请求 | " if state["demo"] else "真实模式 · 资料整理 | ") + names[state["state"]])
        self.input.setPlaceholderText("输入任务；离线演示会依次请求写文件、问答，可选择等待取消" if state["demo"] else
            "提供公开网页 URL、工作区内的文本或 Markdown，以及要生成的 Markdown 路径")
        self.show_materials(state.get("materials"))
        self.memory_button.setText(f"工作区记忆与来源 · {len(state.get('memories', []))} 条")
        used = state.get("recalled_memories", [])
        lines = [f"{m['content'][:80]} · 命中：{', '.join(m['matched'])} · 来源会话 {m['source']['session_id']}"
                 for m in used]
        self.memory_summary.setText("定时任务不召回前台记忆" if state.get("scheduled_execution") else
            "本次使用记忆：\n" + "\n".join(lines) if used else "本次未使用工作区记忆")
        proposal = state.get("memory_proposal")
        if proposal and proposal != self._shown_memory_proposal and self.isVisible():
            self._shown_memory_proposal = proposal
            self.show_memories()
        outstanding = sum(needs_attention(e) for e in state.get("executions", []))
        self.task_button.setText(f"任务与执行记录 · {len(state.get('tasks', []))} 项安排 · {outstanding} 项待处理/确认")
        draft = state.get("schedule_draft")
        if draft and draft["token"] != self._shown_schedule_token and self.isVisible():
            self._shown_schedule_token = draft["token"]
            self.show_schedules()
        self.info.setText(f"工作区：{state['workspace']}\n模型：{state['provider']}\n会话：{state['session_id']}")
        selected = self.sessions.currentData()
        items = [(m["id"], f"{m['title'][:50]} ({m['count']}) · {m['id']}") for m in state["sessions"]]
        if items != getattr(self, "_session_items", None):
            self._session_items = items
            self.sessions.clear()
            for sid, title in items:
                self.sessions.addItem(title, sid)
            index = self.sessions.findData(selected or state["session_id"])
            self.sessions.setCurrentIndex(max(0, index))
        colors = {"error": "#a32626", "tool_error": "#9b5b00", "tool": "#245aa4", "user": "#216447"}
        blocks = []
        if state["notice"]:
            blocks.append(f"<p>{escape(state['notice'])}</p>")
        for row in state["rows"]:
            blocks.append(f"<p style='color:{colors.get(row['kind'], '#222')}'><b>{escape(row['kind'])}</b><br>"
                          + escape(row["text"]).replace("\n", "<br>") + "</p>")
        bar = self.transcript.verticalScrollBar()
        at_end, position = bar.value() >= bar.maximum() - 30, bar.value()
        self.transcript.setHtml("".join(blocks))  # all external text is escaped
        bar.setValue(bar.maximum() if at_end else position)
        pending_key = tuple(p["request_id"] for p in state["pending"])
        if pending_key != self._pending_key:
            self._pending_key = pending_key
            self.show_requests(state["pending"])
        for ack in receipts:
            if self._draft and ack["id"] == self._draft[0]:
                if ack["accepted"] and self.input.document().revision() == self._draft[1]:
                    self.input.clear()
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

    def show_materials(self, summary):
        self.materials_summary.setVisible(summary is not None)
        if summary is None:
            return
        sources = {"read": "已读", "truncated": "截断", "failed": "失败", "interrupted": "中断", "empty": "无可用正文"}
        artifacts = {"written": "已写入，待回读", "verified": "已回读核对",
                     "readback_failed": "回读未通过", "write_unverified": "写入未核实"}
        lines = [f"{s['id']} {sources[s['status']]} · {s['target'][:130]}"
                 for s in summary["sources"] if s["status"] in sources]
        outputs = [f"{a['path'][:160]}（{artifacts[a['status']]}）" for a in summary["artifacts"]]
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
