"""Render R8-A Qt pages offscreen with real offline fixtures, never a Provider.

Run from the repository: python scripts/capture_desktop_ux.py --scale 1.25
These PNGs are layout evidence, not Windows visible/manual acceptance.
"""
import argparse
import os
from pathlib import Path
import sys
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=".r1-verification/r8-captures")
    parser.add_argument("--scale", default="1")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    args = parser.parse_args()
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QT_SCALE_FACTOR"] = args.scale
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo))
    from PySide6.QtWidgets import QApplication
    from examples.deskmate_notifications import prepare, seed, controller
    from likecc.desktop.controller import DesktopOptions
    from likecc.desktop.window import ChatWindow

    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    root = prepare(tempfile.mkdtemp(prefix="fixture-", dir=output))
    seed(root)
    app = QApplication([])
    options = DesktopOptions(work_dir=str(root / "A"))
    c = controller(options, root)
    w = ChatWindow(c, options)

    def spin(predicate, timeout=20):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            app.processEvents()
            w.refresh()
            if predicate():
                return
            time.sleep(.01)
        raise RuntimeError("offline screenshot fixture timed out")

    def capture(name):
        w.resize(args.width, args.height)
        app.processEvents()
        path = output / f"{name}-{args.width}x{args.height}-scale{args.scale}.png"
        if not w.grab().save(str(path)):
            raise RuntimeError("PNG save failed")
        print(path, flush=True)

    try:
        w.show()
        spin(lambda: c.snapshot()["state"] == "idle")
        w.input.setPlainText("明天晚上七点提醒我复习项目笔记")
        capture("01-chat")
        w.send_button.click()
        spin(lambda: w.schedule_window is not None and w.schedule_window.confirm.isEnabled())
        w.schedule_window.confirm.click()
        spin(lambda: not c.snapshot()["schedule_draft"])
        w.schedule_window.editor.set_expanded(False)
        capture("02-tasks")
        w.show_page("chat")
        w.input.setPlainText("请记住，我的周报按结论、依据、行动项排列")
        w.send_button.click()
        spin(lambda: w.memory_window is not None and w.memory_window.confirm.isEnabled())
        spin(lambda: c.snapshot().get("memory_details") is not None)
        w.memory_window.refresh()
        capture("03-memory-confirmation")
        w.memory_window.confirm.click()
        spin(lambda: c.snapshot()["memories"][0]["status"] == "confirmed")
        w.show_notifications()
        capture("04-notifications")
        w.show_page("settings")
        # The setting editor isn't submitted: remove the machine-specific fixture
        # path from the PNG without changing the controller's workspace.
        w.workspace.setText("D:/DeskMate-Demo/A")
        capture("05-settings")
        w.show_schedules()
        w.schedule_window.clear_form()
        w.schedule_window.kind.setCurrentIndex(w.schedule_window.kind.findData("execute"))
        w.schedule_window.content.setPlainText("每周整理项目笔记")
        w.schedule_window.files.setPlainText("project_notes.md")
        w.schedule_window.outputs.setPlainText("outputs/weekly-summary.md")
        w.schedule_window.scroll.verticalScrollBar().setValue(0)
        capture("06-task-editor")
    finally:
        c.request_close()
        spin(lambda: not c.is_alive)
        w.hide()
        w.deleteLater()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
