"""Bounded, explicit local artifact preview; never changes execution evidence."""
from pathlib import Path

MAX_PREVIEW_BYTES = 512 * 1024


def read_artifact(workspace, path):
    root = Path(workspace).resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root) or target.suffix.lower() not in {".md", ".txt"}:
        raise ValueError("仅可查看当前工作区内已记录的 Markdown 或文本成果")
    if not target.is_file():
        raise ValueError("成果文件已移动或不存在；历史执行证据仍保留")
    with target.open("rb") as stream:
        data = stream.read(MAX_PREVIEW_BYTES + 1)
    if len(data) > MAX_PREVIEW_BYTES:
        raise ValueError("成果超过 512 KiB，请使用本地编辑器查看")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("成果不是 UTF-8 文本，无法安全预览") from exc
    if "\x00" in text:
        raise ValueError("成果包含二进制内容，无法预览")
    return "当前磁盘内容 · 只读预览（不重新核验或改变历史回读状态）\n\n" + text
