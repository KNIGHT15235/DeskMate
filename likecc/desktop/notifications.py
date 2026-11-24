"""Notification center, including the complete no-tray workflow."""
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget,
    QListWidgetItem, QPlainTextEdit, QPushButton, QSpinBox, QCheckBox, QLineEdit, QComboBox)

from .schedules import text_label


class NotificationWindow(QDialog):
    def __init__(self, controller, submit, parent=None):
        super().__init__(parent)
        self.controller, self.submit_command = controller, submit
        self._rows, self._tasks, self._workspace = [], [], ""
        self.setWindowTitle("DeskMate · 通知中心")
        self.resize(820, 660)
        layout = QVBoxLayout(self)
        self.notice = text_label("查看不会批准请求或重试。稍后提醒只推迟提示，不延长权限请求的有效时间。")
        layout.addWidget(self.notice)
        self.listing = QListWidget()
        layout.addWidget(self.listing, 1)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        layout.addWidget(self.details, 1)
        actions = QHBoxLayout()
        self.open_button = QPushButton("继续处理 / 查看记录")
        self.snooze_button = QPushButton("稍后提醒")
        self.minutes = QSpinBox()
        self.minutes.setRange(1, 10080)
        self.minutes.setValue(10)
        self.minutes.setSuffix(" 分钟")
        self.dismiss_button = QPushButton("关闭本条提醒")
        for widget in (self.open_button, self.minutes, self.snooze_button, self.dismiss_button):
            actions.addWidget(widget)
        layout.addLayout(actions)
        cancellations = QHBoxLayout()
        self.cancel_button = QPushButton("取消本次执行（保留未来周期）")
        self.stop_button = QPushButton("停止整个安排 / 周期")
        cancellations.addWidget(self.cancel_button)
        cancellations.addWidget(self.stop_button)
        layout.addLayout(cancellations)
        layout.addWidget(text_label("关闭本条提醒仅停止这条提示；取消本次执行结束选定的一次；停止整个安排会停用未来周期并取消当前活动执行。"))
        quiet = QHBoxLayout()
        self.quiet = QCheckBox("免打扰")
        self.start, self.end = QLineEdit(), QLineEdit()
        self.start.setMaximumWidth(70)
        self.end.setMaximumWidth(70)
        self.timezone = QComboBox()
        self.timezone.addItems(["Asia/Shanghai", "UTC"])
        self.save_quiet = QPushButton("保存免打扰")
        for widget in (self.quiet, self.start, text_label("至"), self.end, self.timezone, self.save_quiet):
            quiet.addWidget(widget)
        layout.addLayout(quiet)
        layout.addWidget(text_label("支持跨午夜；开始与结束相同表示全天。静音期间仍可在这里处理，解除后合并提示。"))
        self.listing.currentRowChanged.connect(self.show_details)
        self.listing.itemClicked.connect(lambda _: self.action("open"))
        self.open_button.clicked.connect(lambda: self.action("open"))
        self.snooze_button.clicked.connect(lambda: self.action("snooze", minutes=self.minutes.value()))
        self.dismiss_button.clicked.connect(lambda: self.action("dismiss"))
        self.cancel_button.clicked.connect(lambda: self.action("cancel_execution"))
        self.stop_button.clicked.connect(lambda: self.action("stop_task"))
        self.save_quiet.clicked.connect(self.configure)
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
        self.submit_command("notification_" + action, workspace=row["workspace"], notification_id=row["id"],
            revision=row["revision"], task_revision=task["revision"] if task else None, **values)

    def configure(self):
        self.submit_command("notification_configure", workspace=self._workspace,
            settings={"enabled": self.quiet.isChecked(), "start": self.start.text(),
                      "end": self.end.text(), "timezone": self.timezone.currentText()})

    def refresh(self):
        state = self.controller.snapshot()
        workspace = state["workspace"]
        settings = state.get("notification_settings", {})
        if workspace != self._workspace or getattr(self, "_settings", None) != settings:
            self._workspace, self._settings = workspace, settings
            self.quiet.setChecked(settings.get("enabled", False))
            self.start.setText(settings.get("start", "22:00"))
            self.end.setText(settings.get("end", "08:00"))
            self.timezone.setCurrentText(settings.get("timezone", "Asia/Shanghai"))
        rows = state.get("notifications", [])
        self._tasks = state.get("tasks", [])
        if rows != self._rows:
            selected = self.selected()
            selected_id = selected["id"] if selected else None
            self._rows = rows
            self.listing.blockSignals(True)
            self.listing.clear()
            index = 0
            names = {"unread": "未读", "viewed": "已查看", "snoozed": "已延后", "handled": "已关闭提醒"}
            for i, row in enumerate(rows):
                title = (names[row["state"]] if row["valid"] else "历史") + " · " + row["title"]
                item = QListWidgetItem(title + " · " + row["body"].splitlines()[0][:80])
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
        self.snooze_button.setEnabled(bool(active and row["state"] != "handled"))
        self.dismiss_button.setEnabled(bool(row and row["state"] != "handled"))
        self.cancel_button.setEnabled(bool(active and execution and execution["status"] in {
            "pending", "queued", "awaiting_model", "running", "waiting", "blocked_review"}))
        self.stop_button.setEnabled(bool(active and task and task["enabled"]))
        content = (f"{row['title']}\n{row['body']}\n\n工作区：{row['workspace']}\n"
            f"任务：{row['task_id'] or '前台交互'}\n本次执行：{row['execution_id'] or '前台交互'}\n"
            f"会话：{row['session_id'] or '尚未开始'}\n运行：{row['run_id'] or '尚未开始'}\n"
            f"请求：{row['request_id'] or '无'}\n稍后提醒时间（UTC）：{row['snoozed_until'] or '无'}\n"
            + ("该事项已结束，仅可查看历史。" if not row["valid"] else "")) if row else "当前工作区暂无通知。"
        if self.details.toPlainText() != content:
            self.details.setPlainText(content)
