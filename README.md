# DeskMate（桌伴）

R8-A 已把桌面入口整理为**对话、任务、记忆、通知、设置**五个页面，支持简明任务列表、来源摘要、通知筛选及 Markdown 成果只读预览。权限确认与原业务核心保持，Windows 安装包属于尚未开始的 R8-B。[当前桌面指南与离线验收](docs/deskmate-ux-guide.md) · [本轮验证记录](docs/verification.md)。

DeskMate（桌伴）是一个 Python 桌面助手实验项目，支持资料整理、个人提醒、持久任务、执行历史、可管理的工作区记忆及事件驱动通知，并保留终端编程助手入口。通知中心支持继续处理、稍后提醒和免打扰。

项目从 [LikeCC](https://github.com/KNIGHT15235/likecc) 0.2.0 演进而来，保留原 MIT 许可证和完整开发历史：[初始基线](https://github.com/KNIGHT15235/likecc/commit/4a9b77d281646385bf48fd85b8a03c4d28bbee23)、[R4 基线](https://github.com/KNIGHT15235/likecc/commit/0d76f22d729c781bf4a6f584b0f16f8ab0d73f4a)。当前独立仓库为 [KNIGHT15235/DeskMate](https://github.com/KNIGHT15235/DeskMate)，默认开发分支为 `main`；历史文档中的原仓库固定提交链接继续保留。

R1/R2 已建立共享运行时、统一执行内核与会话服务。R3/R3.1 增加 Qt 桌面、后台生命周期和异常收尾。R4 的桌面资料模式可读取明确给出的公网网页与工作区文本，生成带工具来源记录的 Markdown 并回读校验。离线验证与真实验收状态见[资料模式](docs/deskmate-affairs.md)。Python 包、原 CLI 和 `.likecc` 数据路径沿用原名，后续进度见[路线图](docs/deskmate-roadmap.md)与[学习记录](docs/deskmate-learning.md)。

R5 增加一次性提醒、每周资料任务、SQLite 执行历史及中断恢复。桌面先预览时间/时区和操作范围，确认后保存；到期执行沿用原权限链。Windows 提醒、真实 DeepSeek 排队/批准写入/回读及重启主流程已验收；真实拒绝写入因操作取消后用户跳过补做而未完成。支持范围与覆盖边界见[任务与调度](docs/deskmate-schedules.md)及[验证记录](docs/verification.md)。

本项目为独立学习实践，与 Anthropic 无官方关联，也不声称复现 Claude Code 的完整内部实现。

R6 增加需用户确认的偏好、项目事实与事务关联，按当前请求本地召回并展示来源，支持修改和删除。不同工作区及定时任务保持隔离；历史不会因恢复而重做工具或重新保存记忆。[使用说明与一遍走完的离线桌面清单](docs/deskmate-memory.md)。

R7 将到期、权限/问答、完成、失败和中断事件保存为关联具体执行的通知，支持持久延后、跨午夜免打扰及重复事件去重。查看通知不批准权限；关闭提醒、取消本次执行和停止周期分别处理。七条 Windows 可见主流程与双平台离线回归已有记录，真实 Provider 的 R7 验收仍未开展。[通知使用说明、离线演示与可见桌面清单](docs/deskmate-notifications.md)。

## 能力

| 模块 | 已有能力 |
| --- | --- |
| Agent 运行 | 异步工具调用循环、流式响应、Textual 终端界面，以及 `-p` 非交互入口 |
| 模型接入 | Anthropic、OpenAI、OpenAI 兼容协议；通过配置选择模型与服务端点 |
| 代码工具 | 文件读取与编辑、目录搜索、命令执行；编辑前检查文件是否读过、是否被修改 |
| 上下文 | 会话保存与恢复、上下文压缩、用户和项目记忆 |
| 扩展 | Markdown Agent 定义、Skill、Hook 与 MCP 工具接入 |
| 子 Agent | 定义式独立上下文、Fork 历史继承、后台任务通知、独立权限与文件读取状态 |
| 协作与隔离 | 团队任务和消息、Git Worktree 工作目录隔离 |
| 权限 | 权限模式、显式规则、文件路径检查；子 Agent 权限不超过父 Agent |

## 安装

需要 Python 3.11 或更高版本、uv；使用 Worktree 时还需要 Git。Bash 工具使用系统 Shell，WSL/Linux 通常为 `/bin/sh`，Windows 原生为 `cmd.exe`。命令须采用所在系统的语法。克隆仓库并安装锁定依赖：

```bash
git clone https://github.com/KNIGHT15235/DeskMate.git
cd DeskMate
uv sync --locked
```

## 配置与运行

桌面入口单独安装可选依赖，原终端入口不需要 PySide6：

```bash
uv sync --locked --extra desktop
uv run --locked --extra desktop python -m likecc.desktop --demo
uv run --locked --extra desktop python -m likecc.desktop --work-dir /absolute/project --provider provider-name
```

已在 Conda `cc` 安装锁定依赖时，可直接运行 `python -m likecc.desktop --demo` 或 `python -m likecc.desktop --work-dir /absolute/workspace`。安装本项目后也可使用 `deskmate` 命令。

已安装桌面依赖时，在源码根目录运行 `python -m examples.deskmate_notifications` 可启动 R7 离线通知演示，使用临时 A/B 工作区、fake client 和可推进的时钟。打印的根目录可用于退出重开；操作步骤见[通知说明](docs/deskmate-notifications.md)。

演示使用临时工作区与独立用户数据根，不读取真实凭据。真实模式使用选定工作区配置，权限默认 `default`；Skills、MCP、Hooks 和摘要须分别显式启用。R6 桌面默认使用需确认的工作区记忆，`--memory` 不再启用旧 Markdown 自动提取。桌面当前禁用委派/团队/Worktree/计划模式工具。已有 WSLg 启动和原生 Windows 桌面人工验收记录；R5 的提醒、任务历史、窗口恢复与真实模型主流程覆盖见下表，不代表所有平台和显示器配置均已验收。安装、生命周期与验收步骤见 [桌面说明](docs/deskmate-desktop.md)。

在需要处理的项目目录中创建 `.likecc/config.yaml`，参考 [配置示例](examples/config.example.yaml)。将 `YOUR_MODEL` 和服务地址替换为实际可用的配置。

API Key 建议通过环境变量提供：`openai` 和 `openai-compat` 使用 `OPENAI_API_KEY`，`anthropic` 使用 `ANTHROPIC_API_KEY`。示例中的 `api_key: ""` 会读取对应环境变量。

```bash
# Bash / Zsh：替换为自己的凭据
export OPENAI_API_KEY="YOUR_API_KEY"
uv run --locked likecc
```

```powershell
# PowerShell：替换为自己的凭据
$env:OPENAI_API_KEY = "YOUR_API_KEY"
uv run --locked likecc
```

上述 `uv run` 命令在本仓库根目录执行。处理其他目录时，可先从本地源码安装命令，再到目标目录运行：

```bash
uv tool install .
# 切换到目标项目，并为该项目准备 .likecc/config.yaml
likecc
```

配置也可以放在用户目录的 `~/.likecc/config.yaml`。加载顺序为用户配置、项目 `.likecc/config.yaml`、项目 `.likecc/config.local.yaml`；各层按字段合并。真实凭据和个人配置不应提交到仓库。

常见入口：

```bash
uv run --locked likecc --help
uv run --locked likecc -p "阅读当前项目，概括主要模块及其职责"
uv run --locked likecc --mode plan
```

终端界面中可使用 `/help` 查看命令，例如 `/plan`、`/permission`、`/session`、`/compact`、`/memory` 和 `/skill`。项目规则可写入 `LIKECC.md`。

默认权限模式是 `default`。Fork 需要开启 `enable_fork`；定义式子 Agent 默认同步运行，可由定义或调用参数选择后台运行。后台任务不弹出人工确认，未获允许的操作会返回拒绝。

## 目录

```text
likecc/
  agent.py          Agent 运行循环
  client.py         模型协议适配
  runtime.py        共享装配、实例隔离与资源生命周期
  tools/            文件、命令与协作工具
  agents/           子 Agent 定义、Fork 与后台任务
  permissions/      权限模式、规则与路径检查
  context/          上下文预算与压缩
  memory/           记忆、项目规则与会话
  skills/           Skill 加载与执行
  hooks/            生命周期扩展
  mcp/              MCP 工具接入
  teams/            团队任务与消息
  worktree/         Git Worktree 管理
tests/              自动化测试与验证脚本
examples/           可公开的配置示例
docs/               验证说明
```

## 验证与边界

LikeCC 0.2.0 在 2026-09-22 的发布验证为 Python 3.11 和 3.12 各 **720 项 pytest 测试**、**90 项独立 SubAgent 检查**。DeskMate 各阶段的环境、命令与结果分别记录在 [验证说明](docs/verification.md)，不复用历史通过数量。

R5 当前验收状态（2026-11-22）：

| 类别 | 最新记录与边界 |
| --- | --- |
| 离线回归 | WSL 891 passed；Windows 885 passed、6 skipped；独立 SubAgent 双平台均 90/90。崩溃恢复、周期错过与工作区隔离含隔离自动化证据，不等同于可见桌面验收。 |
| 可见桌面 | Windows 提醒创建/修改/到期/完成/取消、退出与重启恢复、周期定义/待确认/取消、第二实例阻止及 UI1 窗口位置修正已验收。其他显示器配置与跨 Windows/WSL 同库并发不在通过范围。 |
| 真实 Provider | DeepSeek 前台问答、排队接续、权限等待取消、批准写入与回读、原聊天/草稿恢复和成果重启保留已核验，共三次 Agent 运行；真实拒绝写入因用户选择跳过补做而未完成。两项验收周期均已停用。 |

本次独立仓库迁移沿用以上验收证据；迁移后的额外离线检查另记于验证说明，不新增真实模型调用。

- 已验证用例以本地 fake 模型、临时文件和临时 Git 仓库为主，不代表真实模型服务、所有操作系统或外部 MCP 服务都已验证。
- TUI 与 `-p` 共用核心 Agent 能力；`-p` 尚未装配 TUI 的 Memory、Session、Skill 与 MCP 全套管理器。
- Hook 的 `agent` 执行器、插件来源的 Agent 加载尚未实现。
- R5 持久调度、R6 工作区记忆及 R7 事件通知已实现，支持范围分别见[任务说明](docs/deskmate-schedules.md)、[记忆说明](docs/deskmate-memory.md)及[通知说明](docs/deskmate-notifications.md)。进程完全退出期间不后台唤醒；系统气泡可能被操作系统屏蔽，持久通知中心仍可查看。R4 首版资料模式的格式、来源、网络和平台边界见[验收说明](docs/deskmate-affairs.md)。
- Fork 保留可复用的请求前缀；实际缓存命中取决于服务端、模型和请求内容，不承诺固定命中率。
- 子 Agent 的报告格式由提示词约束；Worktree 提供工作目录隔离，权限检查不等同于操作系统级安全沙箱。
- 本仓库版本仅包含源码、测试与示例，不包含开发阶段的审计备份、运行日志或个人配置。

## 许可证

采用 [MIT License](LICENSE)。

## 后续开发

本机迁移后的开发目录为 `D:\ldj\03\DeskMate-Standalone`，`main` 跟踪新仓库的 `origin/main`。原 `DeskMate`、`likecc` 目录与原 GitHub 仓库保留为来源。拉取和推送在新目录执行：

```powershell
Set-Location 'D:\ldj\03\DeskMate-Standalone'
git pull --ff-only
# 修改后按实际文件路径暂存并提交
git add -- path/to/file
git commit -m "说明本次修改"
git push
```

新用户可按安装步骤克隆到自己的目录。Python 包名 `likecc`、原 CLI、配置路径 `.likecc` 及锁定依赖继续兼容；桌面命令为 `deskmate`。在独立工作区中按公开配置模板准备自己的 Provider，运行数据、凭据、日志与旧验收工作区不随源码迁移。
