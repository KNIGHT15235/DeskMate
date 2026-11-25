"""Notification center, including the complete no-tray workflow."""
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget,
    QListWidgetItem, QPlainTextEdit, QPushButton, QSpinBox, QCheckBox, QLineEdit, QComboBox,
    QWidget, QFormLayout)

from .widgets import Page, Disclosure, text_label, update_text, confirm_action
from .presentation import display_time


class QuietSettings(QWidget):
    def __init__(self, controller, submit, parent=None):
        super().__init__(parent)
        self.controller, self.submit_command = controller, submit
        self._workspace, self._settings = None, None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(text_label("通知与免打扰", "status"))
        self.quiet = QCheckBox("启用免打扰")
        layout.addWidget(self.quiet)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.start, self.end = QLineEdit(), QLineEdit()
        self.timezone = QComboBox()
        self.timezone.addItems(["Asia/Shanghai", "UTC"])
        for title, widget in (("开始（HH:MM）", self.start), ("结束（HH:MM）", self.end), ("时区", self.timezone)):
            form.addRow(title, widget)
        layout.addLayout(form)
        self.save_quiet = QPushButton("保存免打扰")
        self.save_quiet.clicked.connect(self.configure)
        layout.addWidget(self.save_quiet)
        layout.addWidget(text_label("支持跨午夜；起止相同表示全天静音。任务照常执行，通知仍保留。", "muted"))

    def configure(self):
        self.submit_command("notification_configure", workspace=self._workspace,
            settings={"enabled": self.quiet.isChecked(), "start": self.start.text(),
                      "end": self.end.text(), "timezone": self.timezone.currentText()})

    def refresh(self):
        state = self.controller.snapshot()
        settings = state.get("notification_settings", {})
        if state["workspace"] != self._workspace or settings != self._settings:
            self._workspace, self._settings = state["workspace"], settings
            self.quiet.setChecked(settings.get("enabled", False))
            self.start.setText(settings.get("start", "22:00"))
            self.end.setText(settings.get("end", "08:00"))
            self.timezone.setCurrentText(settings.get("timezone", "Asia/Shanghai"))
        self.save_quiet.setEnabled(state["state"] not in {"starting", "error", "closing", "closed"})


class NotificationWindow(Page):
    def __init__(self, controller, submit, parent=None, *, embedded=False, quiet_settings=None):
        super().__init__(parent, embedded=embedded)
        self.controller, self.submit_command = controller, submit
        self._rows, self._tasks, self._workspace = [], [], ""
        self.setWindowTitle("DeskMate · 通知中心")
        self.resize(820, 660)
        layout = self.body_layout
        layout.addWidget(text_label("通知", "heading"))
        self.notice = text_label("查看不会批准请求或重试。稍后提醒只推迟提示，不延长权限请求的有效时间。")
        layout.addWidget(self.notice)
        self.quiet_status = text_label("", "status")
        layout.addWidget(self.quiet_status)
        self.filter = QComboBox()
        for title, key in (("全部通知", "all"), ("待处理", "pending"), ("未读", "unread"), ("已处理 / 历史", "history")):
            self.filter.addItem(title, key)
        layout.addWidget(self.filter)
        self._list_key = None
        self.listing = QListWidget()
        self.listing.setWordWrap(True)
        self.listing.setMinimumHeight(160)
        self.listing.setMaximumHeight(230)
        layout.addWidget(self.listing)
        self.summary = text_label()
        layout.addWidget(self.summary)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        actions = QHBoxLayout()
        self.open_button = QPushButton("继续处理 / 查看记录")
        self.snooze_button = QPushButton("稍后提醒")
        self.minutes = QSpinBox()
        self.minutes.setRange(1, 10080)
        self.minutes.setValue(10)
        self.minutes.setSuffix(" 分钟")
        self.dismiss_button = QPushButton("关闭本条提醒")
        self.open_button.setProperty("primary", True)
        for widget in (self.open_button, self.dismiss_button):
            actions.addWidget(widget)
        layout.addLayout(actions)
        snooze = QHBoxLayout()
        snooze.addWidget(self.minutes)
        snooze.addWidget(self.snooze_button)
        snooze.addStretch()
        layout.addLayout(snooze)
        cancellations = QHBoxLayout()
        self.cancel_button = QPushButton("取消本次执行")
        self.stop_button = QPushButton("停止整个安排…")
        self.stop_button.setProperty("danger", True)
        cancellations.addWidget(self.cancel_button)
        cancellations.addWidget(self.stop_button)
        layout.addLayout(cancellations)
        layout.addWidget(text_label("关闭本条提醒仅停止这条提示；取消本次执行结束选定的一次；停止整个安排会停用未来周期并取消当前活动执行。"))
        self.technical_panel = Disclosure("查看技术详情", self.details)
        layout.addWidget(self.technical_panel)
        self.quiet_settings = quiet_settings or QuietSettings(controller, submit)
        if quiet_settings is None:
            layout.addWidget(Disclosure("免打扰设置", self.quiet_settings))
        for name in ("quiet", "start", "end", "timezone", "save_quiet"):
            setattr(self, name, getattr(self.quiet_settings, name))
        layout.addStretch()
        self.listing.currentRowChanged.connect(self.show_details)
        self.listing.itemClicked.connect(lambda _: self.action("open"))
        self.open_button.clicked.connect(lambda: self.action("open"))
        self.snooze_button.clicked.connect(lambda: self.action("snooze", minutes=self.minutes.value()))
        self.dismiss_button.clicked.connect(lambda: self.action("dismiss"))
        self.cancel_button.clicked.connect(lambda: self.action("cancel_execution"))
        self.stop_button.clicked.connect(lambda: self.action("stop_task"))
        self.filter.currentIndexChanged.connect(self.refresh)
        self.timer = QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    def selected(self):
        item = self.listing.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def action(self, action, **values):
        row = self.selected()
        if not row:
            return
        task = next((t for t in self._tasks if t["id"] == row["task_id"]), None)
        payload = dict(workspace=row["workspace"], notification_id=row["id"],
            revision=row["revision"], task_revision=task["revision"] if task else None, **values)
        if action == "stop_task":
            confirm_action(self, "停止整个安排", "这会取消当前执行，并停止未来所有周期。已生成文件和历史保留。",
                lambda: self.submit_command("notification_stop_task", **payload))
        else:
            self.submit_command("notification_" + action, **payload)

    def configure(self):
        self.quiet_settings.configure()

    def refresh(self):
        state = self.controller.snapshot()
        workspace = state["workspace"]
        if workspace != self._workspace:
            self._workspace = workspace
            self.filter.setCurrentIndex(0)
            if getattr(self, "confirmation", None):
                self.confirmation.reject()
        self.quiet_settings.refresh()
        self.quiet_status.setText("静音中 · 可随时在此处理通知" if state.get("notification_quiet") else "通知正常 · 免打扰可在设置中调整")
        rows = state.get("notifications", [])
        self._tasks = state.get("tasks", [])
        key = (rows, self.filter.currentData(), self._tasks)
        if key != self._list_key:
            self._list_key = key
            selected = self.selected()
            selected_id = selected["id"] if selected else None
            mode = self.filter.currentData()
            rows = [r for r in rows if mode == "all" or
                (mode == "pending" and r["valid"] and r["kind"] in {"request", "model", "reminder", "interrupted", "failed", "blocked_review"}) or
                (mode == "unread" and r["valid"] and r["state"] == "unread") or
                (mode == "history" and (not r["valid"] or r["state"] == "handled" or r["kind"] in {"completed", "cancelled"}))]
            self._rows = rows
            self.listing.blockSignals(True)
            self.listing.clear()
            index = 0
            names = {"unread": "未读", "viewed": "已查看", "snoozed": "已延后", "handled": "已关闭提醒"}
            for i, row in enumerate(rows):
                title = (names[row["state"]] if row["valid"] else "历史") + " · " + row["title"]
                task = next((t for t in self._tasks if t["id"] == row["task_id"]), None)
                context = task["spec"]["content"] if task else "当前对话"
                item = QListWidgetItem(title + "\n" + context[:70] + " · " + display_time(row.get("created_at")))
                item.setData(Qt.ItemDataRole.UserRole, row)
                self.listing.addItem(item)
                if row["id"] == selected_id:
                    index = i
            self.listing.setCurrentRow(index if rows else -1)
            self.listing.blockSignals(False)
        self.show_details()

    def show_details(self):
        row = self.selected()
        active = bool(row and row["valid"])
        task = next((t for t in self._tasks if row and t["id"] == row["task_id"]), None)
        execution = next((e for e in self.controller.snapshot().get("executions", [])
                          if row and e["id"] == row["execution_id"]), None)
        self.open_button.setEnabled(bool(row))
        self.open_button.setText("继续处理" if active and row["kind"] in {"request", "model", "reminder"} else "查看成果 / 记录")
        self.snooze_button.setEnabled(bool(active and row["state"] != "handled"))
        self.dismiss_button.setEnabled(bool(row and row["state"] != "handled"))
        self.cancel_button.setEnabled(bool(active and execution and execution["status"] in {
            "pending", "queued", "awaiting_model", "running", "waiting", "blocked_review"}))
        self.stop_button.setEnabled(bool(active and task and task["enabled"]))
        self.summary.setText((row["title"] + "\n" + row["body"] +
            ("\n稍后提醒：" + display_time(row["snoozed_until"]) if row["snoozed_until"] else "")) if row else "这里暂时没有通知。任务到期或需要你决定时会出现在这里。")
        content = (f"{row['title']}\n{row['body']}\n\n工作区：{row['workspace']}\n"
            f"任务：{row['task_id'] or '前台交互'}\n本次执行：{row['execution_id'] or '前台交互'}\n"
            f"会话：{row['session_id'] or '尚未开始'}\n运行：{row['run_id'] or '尚未开始'}\n"
            f"请求：{row['request_id'] or '无'}\n稍后提醒时间（UTC）：{row['snoozed_until'] or '无'}\n"
            + ("该事项已结束，仅可查看历史。" if not row["valid"] else "")) if row else "当前工作区暂无通知。"
        if self.details.toPlainText() != content:
            self.details.setPlainText(content)
