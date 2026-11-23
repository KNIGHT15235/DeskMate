"""Desktop CLI parses help before importing the optional Qt dependency."""
import argparse
import sys

from .controller import DesktopOptions


def main():
    parser = argparse.ArgumentParser(prog="deskmate", description="DeskMate 桌面入口（可选 PySide6）")
    parser.add_argument("--demo", action="store_true", help="隔离临时工作区中的离线演示，无模型网络请求")
    parser.add_argument("--work-dir", default=".", help="显式工作区目录，默认当前目录")
    parser.add_argument("--provider", help="配置中的 Provider 名称，默认首个")
    parser.add_argument("--memory", action="store_true", help="兼容旧参数；桌面始终使用需确认的工作区记忆，不启用旧 Markdown 自动提取")
    for name in ("skills", "mcp", "hooks", "summaries"):
        parser.add_argument(f"--{name}", action="store_true", help=f"显式启用已有 {name} 能力（demo 始终关闭）")
    args = parser.parse_args()
    try:
        from .application import launch
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("PySide6"):
            parser.exit(2, "桌面依赖未安装。仓库中运行 uv sync --locked --extra desktop，或 python -m pip install '.[desktop]'。\n")
        raise
    return launch(DesktopOptions(**vars(args)))


if __name__ == "__main__":
    sys.exit(main())
