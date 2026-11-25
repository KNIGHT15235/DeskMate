"""Local Qt styling; no fonts, images or resources are fetched from the network."""

STYLE = """
QWidget { color: #24344b; font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif; font-size: 13px; }
QMainWindow, QDialog, QScrollArea, QWidget#pageBody { background: #f5f7fb; }
QLabel#heading { font-size: 22px; font-weight: 600; color: #162640; }
QLabel#muted { color: #64748b; }
QLabel#status { color: #245aa4; font-weight: 600; }
QWidget#sidebar { background: #eaf0f8; border-radius: 12px; }
QPushButton { background: white; border: 1px solid #cbd5e1; border-radius: 7px; padding: 7px 12px; min-height: 20px; }
QPushButton:hover { background: #edf3fd; border-color: #7f9fc9; }
QPushButton:pressed { background: #dce8fa; }
QPushButton:disabled { color: #8c98aa; background: #f1f4f8; border-color: #e0e5ed; }
QPushButton[primary="true"] { background: #245aa4; border-color: #245aa4; color: white; }
QPushButton[primary="true"]:disabled { background: #93accf; border-color: #93accf; }
QPushButton[danger="true"] { color: #a32b35; }
QPushButton[nav="true"] { text-align: left; border: none; background: transparent; padding: 10px; }
QPushButton[nav="true"]:checked { color: #164a91; background: #d5e3f8; font-weight: 600; }
QLineEdit, QPlainTextEdit, QTextBrowser, QComboBox, QSpinBox, QTreeWidget, QListWidget {
    background: white; border: 1px solid #d4dce8; border-radius: 7px; padding: 6px;
    selection-background-color: #d7e7ff; selection-color: #162640;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextBrowser:focus, QComboBox:focus { border-color: #4677ba; }
QComboBox { min-height: 24px; }
QTreeWidget::item, QListWidget::item { padding: 9px 5px; }
QTreeWidget::item:selected, QListWidget::item:selected { background: #e0ebfb; color: #163d72; }
QHeaderView::section { background: #eef2f8; color: #52637b; border: none; padding: 7px; }
QGroupBox { border: 1px solid #cbd8ea; border-radius: 8px; margin-top: 12px; padding-top: 12px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
QToolButton { border: none; color: #456791; padding: 7px 0; text-align: left; }
QScrollArea { border: none; }
QCheckBox { spacing: 7px; padding: 5px 0; }
"""


def apply_theme(widget):
    # Qt's Windows offscreen plugin can expose an empty font database. Load a
    # local OS font for test/render parity; native Windows already supplies it.
    import os
    from pathlib import Path
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QApplication
    if os.name == "nt" and QApplication.platformName() == "offscreen" and not QFontDatabase.families():
        font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc"
        if font.is_file():
            QFontDatabase.addApplicationFont(str(font))
    widget.setStyleSheet(STYLE)
