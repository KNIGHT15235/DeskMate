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
        self._last_command = None
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
        self.new_button.clicked.connect(lambda: controller.submit("new"))
        self.resume_button.clicked.connect(lambda: controller.submit("resume", session_id=self.sessions.currentData()))
        self.open_button.clicked.connect(self.open_workspace)
        self.demo_button.clicked.connect(lambda: controller.submit("demo"))
        self.exit_button.clicked.connect(lambda: self.lifecycle.request_exit() if self.lifecycle else controller.submit("close"))
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    def send(self):
        text = self.input.toPlainText().strip()
        if text:
            self.controller.submit("send", text=text)
            self.input.clear()

    def open_workspace(self):
        values = asdict(self.options)
        values.update(work_dir=self.workspace.text(), provider=self.provider.text().strip() or None, demo=False)
        self.controller.submit("open", **values)

    def refresh(self):
        state = self.controller.snapshot()
        if state["revision"] == self._revision:
            return
        self._revision = state["revision"]
        idle = state["state"] == "idle"
        configurable = state["state"] in {"idle", "error"}
        for widget in (self.workspace, self.provider, self.open_button, self.demo_button):
            widget.setEnabled(configurable)
        for widget in (self.send_button, self.input, self.new_button, self.resume_button, self.sessions):
            widget.setEnabled(idle)
        self.cancel_button.setEnabled(state["state"] in {"running", "waiting"})
        names = {"starting": "启动中", "idle": "就绪", "running": "执行中", "waiting": "等待回复",
                 "cancelling": "取消中", "closing": "正在关闭资源", "closed": "已关闭", "error": "配置/启动错误"}
        self.banner.setText(("离线演示 · 无模型网络请求 | " if state["demo"] else "真实模式 | ") + names[state["state"]])
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
        ack = state["command"]
        if ack and ack["id"] != self._last_command:
            self._last_command = ack["id"]
            self.feedback.setText(("后端已接受：" if ack["accepted"] else "未接受：") + ack["message"])
            if not ack["accepted"]:
                for button in self.request_area.findChildren(QPushButton):
                    button.setEnabled(True)

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
        for button in self.request_area.findChildren(QPushButton):
            button.setEnabled(False)
        self.feedback.setText("回复已发送，等待后端确认…")
        self.controller.submit("reply", session_id=request["session_id"], run_id=request["run_id"],
                               request_id=request["request_id"], value=value)

    def closeEvent(self, event):
        event.ignore()
        if self.lifecycle:
            self.lifecycle.close_window()
        else:
            self.controller.submit("close")
