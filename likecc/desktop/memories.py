"""Read stored provenance as text. Viewing it never opens a resource or runs tools."""
import json

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QComboBox,
    QPushButton, QPlainTextEdit, QWidget)

from likecc.memory.workspace import KINDS
from .widgets import Page, ChoiceList, Disclosure, text_label


def update_text(widget, text):
    # Polling must not reset selection/scroll while the user inspects provenance.
    if widget.toPlainText() != text:
        widget.setPlainText(text)


class MemoryWindow(Page):
    def __init__(self, controller, submit, parent=None, *, embedded=False):
        super().__init__(parent, embedded=embedded)
        self.controller, self.submit_command = controller, submit
        self.setWindowTitle("DeskMate · 工作区记忆与来源")
        self.resize(900, 720)
        self._rows = []
        self._selection = None
        self._proposal = None
        self._source_session = None
        self._workspace = None
        layout = self.body_layout
        layout.addWidget(text_label("记忆", "heading"))
        self.notice = text_label("仅已确认内容参与召回。删除不抹去会话和运行审计；记忆不授予读写权限。")
        layout.addWidget(self.notice)
        self.used = QPlainTextEdit()
        self.used.setReadOnly(True)
        self.used.setMaximumHeight(115)
        self.listing = ChoiceList(["桌伴记住了什么", "类型", "状态"])
        layout.addWidget(self.listing)
        self.listing.currentIndexChanged.connect(self.load_selected)
        self.kind = QComboBox()
        for key, name in KINDS.items():
            self.kind.addItem(name, key)
        layout.addWidget(self.kind)
        self.content = QPlainTextEdit()
        self.content.setPlaceholderText("填写需要保存的具体偏好或项目事实（最多 1000 字符）")
        self.content.setMaximumHeight(130)
        layout.addWidget(self.content)
        self.source_summary = text_label("尚无记忆。填写偏好后列为待确认，再核对保存。", "muted")
        layout.addWidget(self.source_summary)
        row = QHBoxLayout()
        self.new = QPushButton("新内容")
        self.propose = QPushButton("列为待确认")
        self.link_run = QPushButton("关联本次资料运行")
        self.confirm = QPushButton("确认保存")
        self.update = QPushButton("保存修改")
        self.delete = QPushButton("删除所选记忆")
        for button in (self.new, self.propose, self.link_run):
            row.addWidget(button)
        layout.addLayout(row)
        changes = QHBoxLayout()
        for button in (self.confirm, self.update, self.delete):
            changes.addWidget(button)
        self.confirm.setProperty("primary", True)
        self.delete.setProperty("danger", True)
        layout.addLayout(changes)
        self.new.clicked.connect(self.clear_form)
        self.propose.clicked.connect(lambda: self.propose_content(False))
        self.link_run.clicked.connect(lambda: self.propose_content(True))
        self.confirm.clicked.connect(lambda: self.change("memory_confirm"))
        self.update.clicked.connect(lambda: self.change("memory_update"))
        self.delete.clicked.connect(lambda: self.change("memory_delete"))
        self.source = QPlainTextEdit()
        self.source.setReadOnly(True)
        self.source.setMinimumHeight(190)
        provenance = QWidget()
        provenance_layout = QVBoxLayout(provenance)
        provenance_layout.setContentsMargins(0, 0, 0, 0)
        provenance_layout.addWidget(text_label("来源记录与修改审计（历史快照）"))
        provenance_layout.addWidget(self.source)
        provenance_layout.addWidget(text_label("本次实际召回"))
        provenance_layout.addWidget(self.used)
        self.technical_panel = Disclosure("查看来源会话、相关资料与审计", provenance)
        layout.addWidget(self.technical_panel)
        self.resume = QPushButton("查看来源会话（仅恢复历史）")
        self.resume.clicked.connect(lambda: self.submit_command("resume", session_id=self._source_session))
        layout.addWidget(self.resume)
        layout.addStretch()
        self.timer = QTimer(self)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    def clear_form(self):
        self.listing.setCurrentIndex(-1)
        self.content.clear()
        self.source.clear()
        self.kind.setCurrentIndex(0)
        self._source_session = None
        self._selection = None
        self.source_summary.setText("新内容需要你确认保存后，才会在后续对话使用。")

    def propose_content(self, from_run):
        self.submit_command("memory_propose", content=self.content.toPlainText(),
            kind="affair" if from_run else self.kind.currentData(), from_run=from_run)

    def change(self, command):
        row = next((r for r in self._rows if r["id"] == self.listing.currentData()), None)
        if row:
            values = {} if command == "memory_delete" else {
                "kind": self.kind.currentData(), "content": self.content.toPlainText()}
            self.submit_command(command, memory_id=row["id"], revision=row["revision"], **values)

    def load_selected(self):
        row = next((r for r in self._rows if r["id"] == self.listing.currentData()), None)
        self._selection = (row["id"], row["revision"]) if row else None
        self._source_session = None
        self.source.clear()
        if row:
            self.kind.setCurrentIndex(self.kind.findData(row["kind"]))
            self.content.setPlainText(row["content"])
            self.submit_command("memory_view", memory_id=row["id"])
            self.source_summary.setText("正在读取来源摘要…")
        else:
            self.content.clear()
            self.source_summary.setText("尚无所选记忆。可以新增偏好或项目事实。")

    def refresh(self):
        state = self.controller.snapshot()
        if self._workspace != state.get("workspace"):
            self.clear_form()
            self._workspace = state.get("workspace")
        rows = state.get("memories", [])
        update_text(self.used, json.dumps(state.get("recalled_memories", []), ensure_ascii=False, indent=2))
        proposal = state.get("memory_proposal")
        if rows != self._rows:
            selected = self.listing.currentData()
            if proposal and proposal != self._proposal:
                selected = proposal
            self._rows = rows
            self.listing.blockSignals(True)
            self.listing.clear()
            for row in rows:
                status = "待确认" if row["status"] == "pending" else "已确认"
                self.listing.addItem([row['content'], KINDS[row['kind']], status], row["id"])
            self.listing.setCurrentIndex(max(0, self.listing.findData(selected)))
            self.listing.blockSignals(False)
            current = next((r for r in rows if r["id"] == self.listing.currentData()), None)
            selection = (current["id"], current["revision"]) if current else None
            if self._selection != selection:
                self.load_selected()
        self._proposal = proposal
        details = state.get("memory_details")
        if details and self._selection == (details["memory"]["id"], details["memory"]["revision"]):
            update_text(self.source, json.dumps(details, ensure_ascii=False, indent=2))
            self._source_session = details["source"]["session_id"]
            source = details["source"]
            self.source_summary.setText("来源：" + (source.get("quote") or "本次资料运行")[:220] +
                "\n" + ("待确认 · 尚未用于召回" if details["memory"]["status"] == "pending" else "已确认 · 可修改或删除"))
        idle = state["state"] == "idle"
        row = next((r for r in rows if r["id"] == self.listing.currentData()), None)
        self.confirm.setEnabled(bool(idle and row and row["status"] == "pending"))
        self.update.setEnabled(bool(idle and row and row["status"] == "confirmed"))
        self.delete.setEnabled(bool(idle and row))
        self.resume.setEnabled(bool(idle and self._source_session))
        self.link_run.setEnabled(idle and state.get("memory_source_available", False))
        self.propose.setEnabled(idle)
        if state["state"] == "closed":
            self.timer.stop()
