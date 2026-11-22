"""Modeless task manager. All mutations still go through controller commands."""
from datetime import datetime, timedelta
import json

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QLineEdit, QPlainTextEdit, QComboBox, QPushButton, QCheckBox, QSplitter, QWidget)

from likecc.scheduling import TaskSpec, zone


def text_label(text=""):
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    return label


def describe_spec(spec, workspace):
    weekday = "一二三四五六日"[datetime.fromisoformat(spec["local_at"]).weekday()]
    return (f"{'提醒' if spec['kind'] == 'reminder' else '执行资料任务'}：{spec['content']}\n"
        f"本地时间：{spec['local_at']}　时区：{spec['timezone']}\n"
        f"重复：{'每周' + weekday + '，相同本地时间' if spec['repeat'] == 'weekly' else '仅一次'}\n"
        f"工作区：{workspace}\n材料：{', '.join(spec['files']) or '无'}\n"
        f"网页：{', '.join(spec['urls']) or '无'}\n输出：{', '.join(spec['outputs']) or '无'}\n"
        f"模型：{spec['provider'] or '不调用模型'}；"
        f"{'本安排每次允许' if spec['model_policy'] == 'allow' else '每次执行前确认'}\n"
        "网页与写入仍按权限规则逐次决定。周期离线错过多次只处理最近一次；中断写入须核对后手动重试。")


class ScheduleWindow(QDialog):
    def __init__(self, controller, submit, parent=None):
        super().__init__(parent)
        self.controller, self.submit_command = controller, submit
        self.setWindowTitle("DeskMate · 任务与执行记录")
        self.resize(1050, 760)
        self.edit_id = self.edit_revision = None
        self._tasks = self._executions = []
        self._draft_token = None
        layout = QVBoxLayout(self)
        self.notice = text_label()
        layout.addWidget(self.notice)
        split = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(split)
        left, right = QWidget(), QWidget()
        split.addWidget(left)
        split.addWidget(right)
        listing, editing = QVBoxLayout(left), QVBoxLayout(right)
        self.tasks = QComboBox()
        listing.addWidget(text_label("安排（取消后仍保留历史）"))
        listing.addWidget(self.tasks)
        controls = QHBoxLayout()
        for name, callback in (("新安排", self.clear_form), ("修改所选", self.load_selected),
                ("取消安排", lambda: self.submit_command("schedule_cancel", task_id=self.tasks.currentData()))):
            button = QPushButton(name)
            button.clicked.connect(callback)
            controls.addWidget(button)
        listing.addLayout(controls)
        self.executions = QComboBox()
        listing.addWidget(text_label("单次到期记录"))
        listing.addWidget(self.executions)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        listing.addWidget(self.details, 1)
        self.complete = QPushButton("完成这条提醒")
        self.allow_model = QPushButton("允许本次模型调用")
        self.reviewed = QCheckBox("我已核对该次会话、成果和磁盘状态")
        self.retry = QPushButton("明确发起新一次尝试")
        for widget in (self.complete, self.allow_model, self.reviewed, self.retry):
            listing.addWidget(widget)
        self.complete.clicked.connect(lambda: self.action("schedule_complete"))
        self.allow_model.clicked.connect(lambda: self.action("schedule_allow_model"))
        self.retry.clicked.connect(lambda: self.action("schedule_retry", reviewed=self.reviewed.isChecked()))
        self.tasks.currentIndexChanged.connect(self.show_executions)
        self.executions.currentIndexChanged.connect(self.show_details)
        self.reviewed.toggled.connect(self.show_details)

        form = QFormLayout()
        editing.addLayout(form)
        self.content = QPlainTextEdit()
        self.content.setMaximumHeight(90)
        self.kind = QComboBox()
        self.kind.addItem("提醒（到期等待处理）", "reminder")
        self.kind.addItem("执行资料任务", "execute")
        self.local_at = QLineEdit()
        self.local_at.setPlaceholderText("2026-11-21T19:00:00")
        self.timezone = QComboBox()
        self.timezone.addItems(["Asia/Shanghai", "UTC"])
        self.timezone.setEditable(True)
        self.repeat = QComboBox()
        self.repeat.addItem("一次性", "once")
        self.repeat.addItem("每周（按上方日期的星期）", "weekly")
        self.files, self.urls, self.outputs = QPlainTextEdit(), QPlainTextEdit(), QPlainTextEdit()
        for field in (self.files, self.urls, self.outputs):
            field.setMaximumHeight(60)
            field.setPlaceholderText("每行一项；文件为工作区内的相对路径")
        self.model = QCheckBox("允许本安排按此模型周期调用；不勾选则每次确认")
        for name, widget in (("任务内容", self.content), ("类型", self.kind), ("首次本地时间", self.local_at),
                ("时区", self.timezone), ("重复规则", self.repeat), ("材料文件", self.files),
                ("明确 URL", self.urls), ("Markdown 输出", self.outputs), ("模型范围", self.model)):
            form.addRow(name, widget)
        self.preview_button = QPushButton("预览安排与范围")
        editing.addWidget(self.preview_button)
        self.preview_button.clicked.connect(self.preview)
        self.preview_text = QPlainTextEdit()
        self.preview_text.setReadOnly(True)
        editing.addWidget(self.preview_text, 1)
        self.confirm = QPushButton("确认保存以上预览")
        editing.addWidget(self.confirm)
        self.confirm.clicked.connect(lambda: self.submit_command("schedule_confirm", token=self._draft_token))
        self.clear_form()
        self.timer = QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()
        self.show_executions()

    def action(self, command, **kwargs):
        self.submit_command(command, execution_id=self.executions.currentData(), **kwargs)
        self.reviewed.setChecked(False)

    def clear_form(self):
        self.edit_id = self.edit_revision = None
        self.content.clear()
        self.local_at.setText((datetime.now(zone("Asia/Shanghai")) + timedelta(days=1)).replace(
            tzinfo=None, hour=19, minute=0, second=0, microsecond=0).isoformat())
        for widget in (self.files, self.urls, self.outputs):
            widget.clear()
        self.model.setChecked(False)
        self.kind.setCurrentIndex(0)
        self.repeat.setCurrentIndex(0)

    def load_selected(self):
        task = next((t for t in self._tasks if t["id"] == self.tasks.currentData()), None)
        if task is None:
            return
        self.edit_id, self.edit_revision = task["id"], task["revision"]
        spec = task["spec"]
        self.content.setPlainText(spec["content"])
        self.local_at.setText(spec["local_at"])
        self.timezone.setCurrentText(spec["timezone"])
        self.kind.setCurrentIndex(self.kind.findData(spec["kind"]))
        self.repeat.setCurrentIndex(self.repeat.findData(spec["repeat"]))
        for name in ("files", "urls", "outputs"):
            getattr(self, name).setPlainText("\n".join(spec[name]))
        self.model.setChecked(spec["model_policy"] == "allow")

    def preview(self):
        spec = TaskSpec(self.content.toPlainText(), self.kind.currentData(), self.local_at.text().strip(),
            self.timezone.currentText().strip(), self.repeat.currentData(),
            *[[line for line in getattr(self, name).toPlainText().splitlines() if line] for name in ("files", "urls", "outputs")],
            model_policy="allow" if self.model.isChecked() else "ask")
        self.submit_command("schedule_preview", spec=spec.__dict__, task_id=self.edit_id, revision=self.edit_revision)

    def refresh(self):
        state = self.controller.snapshot()
        tasks, executions = state.get("tasks", []), state.get("executions", [])
        self.notice.setText(state.get("scheduler_error", "") or (
            "离线演示的临时工作区在退出时删除。" if state["demo"] else "窗口隐藏后继续调度；完全退出期间不执行。"))
        if tasks != self._tasks:
            selected = self.tasks.currentData()
            self._tasks = tasks
            self.tasks.blockSignals(True)
            self.tasks.clear()
            for task in tasks:
                self.tasks.addItem(("已取消 · " if not task["enabled"] else "") + task["spec"]["content"][:65], task["id"])
            self.tasks.setCurrentIndex(max(0, self.tasks.findData(selected)))
            self.tasks.blockSignals(False)
            self._executions = executions
            self.show_executions()
        elif executions != self._executions:
            self._executions = executions
            self.show_executions()
        draft = state.get("schedule_draft")
        self._draft_token = draft["token"] if draft else None
        self.confirm.setEnabled(bool(draft) and state["state"] not in {"closing", "closed"})
        self.preview_text.setPlainText(describe_spec(draft["spec"], draft["workspace"]) if draft else "预览后，核对并确认保存。")

    def show_executions(self):
        selected = self.executions.currentData()
        self.executions.blockSignals(True)
        self.executions.clear()
        for row in self._executions:
            if row["task_id"] == self.tasks.currentData():
                due = datetime.fromisoformat(row["due_at"]).astimezone(zone(row["snapshot"]["timezone"]))
                self.executions.addItem(f"{due.isoformat(timespec='minutes')} · {row['label']}", row["id"])
        self.executions.setCurrentIndex(max(0, self.executions.findData(selected)))
        self.executions.blockSignals(False)
        if selected != self.executions.currentData():
            self.reviewed.setChecked(False)
        self.show_details()

    def show_details(self):
        row = next((e for e in self._executions if e["id"] == self.executions.currentData()), None)
        self.complete.setEnabled(bool(row and row["status"] == "pending"))
        self.allow_model.setEnabled(bool(row and row["status"] == "awaiting_model"))
        self.retry.setEnabled(bool(row and row["snapshot"]["kind"] == "execute" and
            row["status"] in {"interrupted", "failed", "cancelled", "completed"} and self.reviewed.isChecked()))
        task = next((t for t in self._tasks if t["id"] == self.tasks.currentData()), None)
        if not row:
            self.details.setPlainText(describe_spec(task["spec"], task["workspace"]) if task else "尚无安排。可直接在聊天输入明确时间，或填写右侧表单。")
            return
        evidence = row["evidence"]
        output_names = {"written": "已写入，未回读", "verified": "已回读核对", "readback_failed": "回读失败", "write_unverified": "可能写入，待核对"}
        artifacts = "\n".join(f"{a['path']}：{output_names.get(a['status'], a['status'])}" for a in evidence.get("artifacts", []))
        self.details.setPlainText(f"{row['label']}\n{row['reason']}\n开始：{row['started_at'] or '尚未开始'}\n结束：{row['ended_at'] or '尚未结束'}\n"
            f"会话：{row['session_id'] or '无'}\n运行：{row['run_id'] or '无'}\n成果：\n{artifacts or '没有已写入成果'}\n\n"
            + describe_spec(row["snapshot"], row["snapshot"]["workspace"]) + "\n\n本次资料与工具证据：\n" + json.dumps(evidence, ensure_ascii=False, indent=2))
