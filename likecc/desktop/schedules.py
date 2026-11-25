"""Modeless task manager. All mutations still go through controller commands."""
from datetime import datetime, timedelta
import json
import uuid

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QLineEdit, QPlainTextEdit, QComboBox, QPushButton, QCheckBox, QSplitter, QWidget)

from likecc.scheduling import TaskSpec, zone
from likecc.scheduling import needs_attention
from .widgets import Page, Disclosure, ChoiceList, ArtifactPreview, update_text, confirm_action
from .presentation import display_time, artifacts_text


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


class ScheduleWindow(Page):
    def __init__(self, controller, submit, parent=None, *, embedded=False):
        super().__init__(parent, embedded=embedded)
        self.controller, self.submit_command = controller, submit
        self.setWindowTitle("DeskMate · 任务与执行记录")
        self.resize(1050, 760)
        self.edit_id = self.edit_revision = None
        self._tasks = self._executions = []
        self._draft_token = None
        self._reviewed_execution_id = None
        self._workspace = None
        self._seen_draft = None
        self._invalidated_token = None
        self._loading = False
        self._saving_spec = None
        self._preview_form = None
        layout = self.body_layout
        heading = text_label("任务")
        heading.setObjectName("heading")
        layout.addWidget(heading)
        self.notice = text_label()
        layout.addWidget(self.notice)
        left, right = QWidget(), QWidget()
        layout.addWidget(left)
        listing, editing = QVBoxLayout(left), QVBoxLayout(right)
        listing.setContentsMargins(0, 0, 0, 0)
        editing.setContentsMargins(0, 0, 0, 0)
        self.tasks = ChoiceList(["任务", "重复", "下次执行", "状态"])
        listing.addWidget(self.tasks)
        controls = QHBoxLayout()
        for name, callback in (("新建任务", self.clear_form), ("修改所选", self.load_selected),
                ("停止整个安排…", self.stop_selected)):
            button = QPushButton(name)
            button.clicked.connect(callback)
            controls.addWidget(button)
        listing.addLayout(controls)
        self.executions = QComboBox()
        listing.addWidget(text_label("单次到期记录"))
        listing.addWidget(self.executions)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMinimumHeight(135)
        self.details.setMaximumHeight(210)
        listing.addWidget(self.details)
        self.artifact_preview = ArtifactPreview(submit)
        listing.addWidget(self.artifact_preview)
        self.complete = QPushButton("完成这条提醒")
        self.allow_model = QPushButton("允许本次模型调用")
        self.reviewed = QCheckBox("我已核对该次会话、成果和磁盘状态")
        self.retry = QPushButton("明确发起新一次尝试")
        for widget in (self.complete, self.allow_model, self.reviewed, self.retry):
            listing.addWidget(widget)
        self.complete.clicked.connect(lambda: self.action("schedule_complete"))
        self.allow_model.clicked.connect(lambda: self.action("schedule_allow_model"))
        self.retry.clicked.connect(lambda: self.action("schedule_retry",
            reviewed_execution_id=self._reviewed_execution_id))
        self.tasks.currentIndexChanged.connect(self.show_executions)
        self.executions.currentIndexChanged.connect(self.show_details)
        self.reviewed.toggled.connect(self.review_selection)
        self.technical = QPlainTextEdit()
        self.technical.setReadOnly(True)
        self.technical.setMinimumHeight(180)
        self.technical_panel = Disclosure("查看技术详情与完整证据", self.technical)
        listing.addWidget(self.technical_panel)

        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
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
                ("时区", self.timezone), ("重复规则", self.repeat)):
            form.addRow(name, widget)
        scope = QWidget()
        scope_form = QFormLayout(scope)
        scope_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        for name, widget in (("材料文件", self.files), ("明确 URL", self.urls),
                             ("Markdown 输出", self.outputs), ("模型范围", self.model)):
            scope_form.addRow(name, widget)
        self.scope_panel = Disclosure("资料与授权范围（执行任务必填）", scope)
        editing.addWidget(self.scope_panel)
        self.kind.currentIndexChanged.connect(self.show_scope)
        self.preview_button = QPushButton("预览安排与范围")
        editing.addWidget(self.preview_button)
        self.preview_button.clicked.connect(self.preview)
        self.preview_text = QPlainTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMinimumHeight(190)
        editing.addWidget(self.preview_text)
        self.confirm = QPushButton("确认保存以上预览")
        editing.addWidget(self.confirm)
        self.confirm.clicked.connect(self.save_preview)
        self.confirm.setProperty("primary", True)
        self.editor = Disclosure("新建 / 修改任务", right)
        self.editor.toggle.toggled.connect(lambda expanded: left.setVisible(not expanded))
        back = QPushButton("返回任务列表（保留表单）")
        back.clicked.connect(lambda: self.editor.set_expanded(False))
        editing.insertWidget(0, back)
        layout.addWidget(self.editor)
        layout.addStretch()
        for field in (self.content, self.local_at, self.files, self.urls, self.outputs):
            field.textChanged.connect(self.invalidate_preview)
        for field in (self.kind, self.repeat, self.timezone):
            field.currentTextChanged.connect(self.invalidate_preview)
        self.model.toggled.connect(self.invalidate_preview)
        self.clear_form()
        self.editor.set_expanded(False)
        self.timer = QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()
        self.show_executions()

    def show_scope(self):
        self.scope_panel.setVisible(self.kind.currentData() == "execute")
        if self.kind.currentData() == "execute":
            self.scope_panel.set_expanded(True)

    def save_preview(self):
        draft = self.controller.snapshot().get("schedule_draft")
        if draft and draft["token"] == self._draft_token:
            self._saving_spec = draft["spec"]
            self.submit_command("schedule_confirm", token=self._draft_token)

    def invalidate_preview(self, *_):
        if not self._loading:
            self._invalidated_token = self._draft_token
            self.confirm.setEnabled(False)

    def stop_selected(self):
        task_id = self.tasks.currentData()
        workspace = self._workspace
        if task_id:
            confirm_action(self, "停止整个安排", "当前执行将取消，未来周期将停止。已有成果和历史保留。",
                lambda: self.submit_command("schedule_cancel", task_id=task_id)
                if self.controller.snapshot()["workspace"] == workspace else None)

    def action(self, command, **kwargs):
        if command == "schedule_retry" and self._reviewed_execution_id != self.executions.currentData():
            return
        self.submit_command(command, execution_id=self.executions.currentData(), **kwargs)
        self.reviewed.setChecked(False)

    def review_selection(self, checked):
        self._reviewed_execution_id = self.executions.currentData() if checked else None
        self.show_details()

    def clear_form(self):
        self._loading = True
        self.edit_id = self.edit_revision = None
        self.content.clear()
        self.local_at.setText((datetime.now(zone("Asia/Shanghai")) + timedelta(days=1)).replace(
            tzinfo=None, hour=19, minute=0, second=0, microsecond=0).isoformat())
        for widget in (self.files, self.urls, self.outputs):
            widget.clear()
        self.model.setChecked(False)
        self.kind.setCurrentIndex(0)
        self.repeat.setCurrentIndex(0)
        self.timezone.setCurrentText("Asia/Shanghai")
        self._loading = False
        self.invalidate_preview()
        self.editor.set_expanded(True)
        self.show_scope()

    def load_selected(self):
        task = next((t for t in self._tasks if t["id"] == self.tasks.currentData()), None)
        if task is None:
            return
        self._loading = True
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
        self._loading = False
        self.invalidate_preview()
        self.editor.set_expanded(True)

    def preview(self):
        spec = TaskSpec(self.content.toPlainText(), self.kind.currentData(), self.local_at.text().strip(),
            self.timezone.currentText().strip(), self.repeat.currentData(),
            *[[line for line in getattr(self, name).toPlainText().splitlines() if line] for name in ("files", "urls", "outputs")],
            model_policy="allow" if self.model.isChecked() else "ask")
        preview_id = uuid.uuid4().hex
        if self.submit_command("schedule_preview", spec=spec.__dict__, task_id=self.edit_id,
                               revision=self.edit_revision, preview_id=preview_id):
            self._preview_form = (preview_id, self.form_values())
            self.invalidate_preview()

    def form_values(self):
        return (self.content.toPlainText(), self.kind.currentData(), self.local_at.text(),
                self.timezone.currentText(), self.repeat.currentData(), self.files.toPlainText(),
                self.urls.toPlainText(), self.outputs.toPlainText(), self.model.isChecked())

    def refresh(self):
        state = self.controller.snapshot()
        if state["workspace"] != self._workspace:
            self._workspace = state["workspace"]
            self.clear_form()
            self.editor.set_expanded(False)
            self.reviewed.setChecked(False)
            self._seen_draft = self._draft_token = self._invalidated_token = None
            self._saving_spec = None
            self._preview_form = None
            if getattr(self, "confirmation", None):
                self.confirmation.reject()
        tasks, executions = state.get("tasks", []), state.get("executions", [])
        self.notice.setText(state.get("scheduler_error", "") or (
            "离线演示的临时工作区在退出时删除。" if state["demo"] else "窗口隐藏后继续调度；完全退出期间不执行。"))
        if tasks != self._tasks or executions != self._executions:
            selected = self.tasks.currentData()
            self._tasks = tasks
            self.tasks.blockSignals(True)
            self.tasks.clear()
            for task in tasks:
                attention = sum(needs_attention(e) for e in executions if e["task_id"] == task["id"])
                self.tasks.addItem([task["spec"]["content"], "每周" if task["spec"]["repeat"] == "weekly" else "一次性",
                    display_time(task.get("next_due"), task["spec"]["timezone"]),
                    f"{attention} 项待处理" if attention else ("已停止" if not task["enabled"] else
                    "等待下次执行" if task.get("next_due") else "已结束")], task["id"])
            self.tasks.setCurrentIndex(max(0, self.tasks.findData(selected)))
            self.tasks.blockSignals(False)
            self._executions = executions
            self.show_executions()
        draft = state.get("schedule_draft")
        self._draft_token = draft["token"] if draft else None
        if not draft and self._seen_draft:
            self.editor.set_expanded(False)
            self._seen_draft = None
            saved = next((t for t in tasks if t["spec"] == self._saving_spec), None)
            if saved:
                self.tasks.setCurrentIndex(self.tasks.findData(saved["id"]))
            self._saving_spec = None
        if draft and draft["token"] != self._seen_draft:
            self._seen_draft = draft["token"]
            self.editor.set_expanded(True)
            preview_id = draft.get("preview_id")
            pending = self._preview_form
            changed = bool(preview_id and pending and (
                preview_id != pending[0] or pending[1] != self.form_values()))
            # An earlier response must not consume the latest form's identity.
            # Chat-created drafts have no form request and remain independent.
            if not preview_id or (pending and preview_id == pending[0]):
                self._preview_form = None
            if changed:
                # A delayed preview must neither overwrite typing nor authorize
                # an old form while showing the user's newer content.
                self._invalidated_token = draft["token"]
                update_text(self.preview_text, "表单已修改，请重新预览再确认。")
                self.confirm.setEnabled(False)
                return
            self._loading = True
            spec = draft["spec"]
            self.edit_id, self.edit_revision = draft["task_id"], draft["revision"]
            self.content.setPlainText(spec["content"])
            self.local_at.setText(spec["local_at"])
            self.timezone.setCurrentText(spec["timezone"])
            self.kind.setCurrentIndex(self.kind.findData(spec["kind"]))
            self.repeat.setCurrentIndex(self.repeat.findData(spec["repeat"]))
            for name in ("files", "urls", "outputs"):
                getattr(self, name).setPlainText("\n".join(spec[name]))
            self.model.setChecked(spec["model_policy"] == "allow")
            self._loading = False
            QTimer.singleShot(0, self, lambda: self.scroll.ensureWidgetVisible(self.preview_text))
        self.confirm.setEnabled(bool(draft) and draft["token"] != self._invalidated_token
            and state["state"] not in {"starting", "error", "closing", "closed"})
        preview = describe_spec(draft["spec"], draft["workspace"]) if draft else "预览后，核对并确认保存。"
        if draft and draft["token"] == self._invalidated_token:
            preview = "表单已修改，请重新预览再确认。以下是上次预览：\n\n" + preview
        update_text(self.preview_text, preview)
        selected = next((e for e in executions if e["id"] == self.executions.currentData()), {})
        self.artifact_preview.refresh(state, selected.get("evidence", {}).get("artifacts", []),
                                      source=selected.get("id"))

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

    def focus_execution(self, task_id, execution_id):
        self.refresh()
        self.tasks.setCurrentIndex(self.tasks.findData(task_id))
        self.executions.setCurrentIndex(self.executions.findData(execution_id))
        self.show_details()

    def show_details(self):
        if self._reviewed_execution_id != self.executions.currentData():
            self.reviewed.setChecked(False)
        row = next((e for e in self._executions if e["id"] == self.executions.currentData()), None)
        self.complete.setEnabled(bool(row and row["status"] == "pending"))
        self.allow_model.setEnabled(bool(row and row["status"] == "awaiting_model"))
        self.retry.setEnabled(bool(row and row["snapshot"]["kind"] == "execute" and
            row["status"] in {"interrupted", "failed", "cancelled", "completed"} and self.reviewed.isChecked()))
        self.complete.setVisible(bool(row and row["snapshot"]["kind"] == "reminder"))
        self.allow_model.setVisible(bool(row and row["status"] == "awaiting_model"))
        reviewable = bool(row and row["snapshot"]["kind"] == "execute" and
                         row["status"] in {"interrupted", "failed", "cancelled", "completed"})
        self.reviewed.setVisible(reviewable)
        self.retry.setVisible(reviewable)
        task = next((t for t in self._tasks if t["id"] == self.tasks.currentData()), None)
        if not row:
            spec = task["spec"] if task else None
            update_text(self.details, (f"{spec['content']}\n"
                f"{'每周' if spec['repeat'] == 'weekly' else '一次性'} · {spec['local_at']} · {spec['timezone']}\n"
                "尚未执行。到期后可在这里查看本次状态与成果。") if task else
                "还没有任务。在对话中输入“明天晚上七点提醒我复习”，或点击新建任务。")
            update_text(self.technical, describe_spec(spec, task["workspace"]) if task else "暂无执行证据。")
            self.artifact_preview.refresh(self.controller.snapshot(), [])
            return
        evidence = row["evidence"]
        output_names = {"written": "已写入，未回读", "verified": "已回读核对", "readback_failed": "回读失败", "write_unverified": "可能写入，待核对"}
        artifacts = "\n".join(f"{a['path']}：{output_names.get(a['status'], a['status'])}" for a in evidence.get("artifacts", []))
        update_text(self.details, f"{row['snapshot']['content']}\n{row['label']} · {row['reason']}\n"
            f"开始：{display_time(row['started_at'])}　结束：{display_time(row['ended_at'])}\n"
            + artifacts_text(evidence.get("artifacts", [])) + "\n来源：" +
            ("、".join(s.get("target", "") for s in evidence.get("sources", [])) or "尚无读取记录"))
        self.artifact_preview.refresh(self.controller.snapshot(), evidence.get("artifacts", []), source=row["id"])
        update_text(self.technical, f"{row['label']}\n{row['reason']}\n任务：{row['task_id']}\n本次执行：{row['id']}\n开始：{row['started_at'] or '尚未开始'}\n结束：{row['ended_at'] or '尚未结束'}\n"
            f"核对记录：{row['reviewed_at'] or '尚未核对'}\n"
            f"会话：{row['session_id'] or '无'}\n运行：{row['run_id'] or '无'}\n成果：\n{artifacts or '没有已写入成果'}\n\n"
            + describe_spec(row["snapshot"], row["snapshot"]["workspace"]) + "\n\n本次资料与工具证据：\n" + json.dumps(evidence, ensure_ascii=False, indent=2))
