"""Small presentation widgets shared by embedded pages and compatibility dialogs."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QLabel, QScrollArea,
    QToolButton, QTreeWidget, QTreeWidgetItem, QHeaderView, QMessageBox,
    QPlainTextEdit, QComboBox, QPushButton, QSizePolicy)

from .theme import apply_theme


def text_label(text="", role=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    if role:
        widget.setObjectName(role)
    return widget


def update_text(widget, text):
    if widget.toPlainText() != text:
        widget.setPlainText(text)


class Disclosure(QWidget):
    def __init__(self, title, content, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.toggle = QToolButton()
        self.toggle.setText(title)
        self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.content = content
        layout.addWidget(self.toggle)
        layout.addWidget(content)
        self.toggle.toggled.connect(self.set_expanded)
        self.set_expanded(False)

    def set_expanded(self, expanded):
        self.toggle.setChecked(expanded)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.content.setVisible(expanded)


class Page(QWidget):
    """Modeless show/hide API; embedded pages must be real QWidget instances.

    QDialog restores its last focus on visibility changes even with Widget flags,
    which can reveal an inactive page or steal focus during notification routing.
    Standalone managers retain a native dialog window through their window flags.
    """
    def __init__(self, parent=None, *, embedded=False):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Widget if embedded else Qt.WindowType.Dialog)
        apply_theme(self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.body = QWidget()
        self.body.setObjectName("pageBody")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(18, 14, 18, 18)
        self.body_layout.setSpacing(12)
        self.scroll.setWidget(self.body)
        outer.addWidget(self.scroll)


class ChoiceList(QTreeWidget):
    """A visible multi-column list with the existing selection adapter API."""
    currentIndexChanged = Signal(int)

    def __init__(self, headers):
        super().__init__()
        self.setHeaderLabels(headers)
        self.setRootIsDecorated(False)
        self.setMinimumHeight(130)
        self.setMaximumHeight(235)
        self.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.currentItemChanged.connect(lambda *_: self.currentIndexChanged.emit(self.currentIndex()))

    def addItem(self, text, data):
        item = QTreeWidgetItem([text] if isinstance(text, str) else text)
        item.setData(0, Qt.ItemDataRole.UserRole, data)
        item.setToolTip(0, item.text(0))
        self.addTopLevelItem(item)

    def currentData(self):
        return self.currentItem().data(0, Qt.ItemDataRole.UserRole) if self.currentItem() else None

    def currentIndex(self):
        return self.indexOfTopLevelItem(self.currentItem())

    def setCurrentIndex(self, index):
        self.setCurrentItem(self.topLevelItem(index) if index >= 0 else None)

    def findData(self, data):
        return next((i for i in range(self.topLevelItemCount())
                     if self.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole) == data), -1)


def confirm_action(parent, title, message, callback):
    """Nonblocking confirmation. Capture the selected identity before opening it."""
    old = getattr(parent, "confirmation", None)
    if old is not None:
        old.raise_()
        return
    dialog = QMessageBox(parent)
    dialog.setWindowTitle(title)
    dialog.setText(message)
    dialog.setTextFormat(Qt.TextFormat.PlainText)
    accept = dialog.addButton(title, QMessageBox.ButtonRole.DestructiveRole)
    cancel = dialog.addButton("返回", QMessageBox.ButtonRole.RejectRole)
    dialog.setDefaultButton(cancel)
    parent.confirmation = dialog

    def finished(_):
        parent.confirmation = None
        if dialog.clickedButton() == accept:
            callback()
        dialog.deleteLater()
    dialog.finished.connect(finished)
    dialog.open()


class ArtifactPreview(QWidget):
    """Explicit, bounded text preview via the worker; no external HTML resources."""
    def __init__(self, submit):
        super().__init__()
        self.submit = submit
        self.workspace = ""
        self._identity = None
        self._token = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.paths = QComboBox()
        self.open_button = QPushButton("查看成果内容")
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setMinimumHeight(180)
        self.panel = Disclosure("成果内容（只读）", self.text)
        layout.addWidget(self.paths)
        layout.addWidget(self.open_button)
        layout.addWidget(self.panel)
        self.open_button.clicked.connect(self.open_selected)
        self.paths.currentIndexChanged.connect(self.reset_preview)

    def reset_preview(self):
        self._token = None
        self.text.clear()
        self.panel.set_expanded(False)

    def open_selected(self):
        if self.paths.currentData():
            self._token = self.submit("artifact_preview", workspace=self.workspace,
                                      path=self.paths.currentData())
            if self._token:
                self.panel.set_expanded(True)
                update_text(self.text, "正在读取成果…")

    def refresh(self, state, artifacts, *, source=None):
        identity = (state["workspace"], source, tuple(a["path"] for a in artifacts))
        if identity != self._identity:
            self._identity = identity
            self.workspace = state["workspace"]
            self.reset_preview()
            self.paths.clear()
            for artifact in artifacts:
                self.paths.addItem(artifact["path"], artifact["path"])
        self.setVisible(bool(artifacts))
        result = state.get("artifact_preview")
        if result and result["token"] == self._token and result["workspace"] == self.workspace:
            update_text(self.text, result["text"])
