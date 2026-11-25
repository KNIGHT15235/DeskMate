"""Pure display formatting. Business state and verification remain authoritative."""
from datetime import datetime
from likecc.scheduling import zone

ARTIFACT_STATUS = {"written": "已写入，待回读", "verified": "已回读核对",
    "readback_failed": "回读未通过", "write_unverified": "可能写入，需人工核对"}


def display_time(value, timezone="Asia/Shanghai"):
    if not value:
        return "—"
    try:
        date = datetime.fromisoformat(value)
        if date.tzinfo:
            date = date.astimezone(zone(timezone))
        return date.strftime("%m-%d %H:%M")
    except (ValueError, TypeError):
        return str(value)


def artifacts_text(artifacts):
    return "\n".join(f"{a['path']} · {ARTIFACT_STATUS.get(a['status'], '状态待核对')}"
                     for a in artifacts) or "没有已写入成果"


def activity(state):
    if state["pending"]:
        return "需要你的决定 · 请查看授权或补充信息卡片"
    if state["state"] != "running":
        return {"idle": "可以开始新的对话", "starting": "正在准备工作区…",
                "cancelling": "正在取消本次执行…", "error": "启动失败，请在设置中检查工作区与模型"}.get(state["state"], "")
    last = next((r for r in reversed(state["rows"]) if r["kind"] == "tool"), None)
    name = last["text"].split(":", 1)[0] if last else ""
    return {"ReadFile": "正在读取资料", "WebFetch": "正在读取网页", "FetchWebPage": "正在读取网页",
            "WriteFile": "正在生成文件", "AskUserQuestion": "等待补充信息"}.get(name, "正在整理资料…")
