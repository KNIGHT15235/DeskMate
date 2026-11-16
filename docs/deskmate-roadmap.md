# DeskMate 开发路线与 R1 记录

## 路线状态

| 轮次 | 目标 | 状态 |
| --- | --- | --- |
| R1 | 共享装配与生命周期 | 本轮完成；验证见下文 |
| R2 | 统一执行与会话服务 | 计划，未实现 |
| R3 | 桌面入口 | 计划，未实现 |
| R4 | 个人事务流程 | 计划，未实现 |
| R5 | 持久任务与调度 | 计划，未实现 |
| R6 | 个人记忆 | 计划，未实现 |
| R7 | 主动通知与交互 | 计划，未实现 |
| R8 | 演示、打包、验证和文档整合 | 计划，未实现 |

DeskMate（桌伴）是目标产品名称。本轮保持 Python 包 `likecc`、CLI `likecc`、配置目录 `.likecc`、项目规则 `LIKECC.md` 以及历史会话路径；没有引入桌面 GUI、调度器、事务工具或新的个人记忆模型。

## R1 基线（2026-11-16）

- 源目录：`D:\ldj\03\likecc`，分支 `main`，HEAD `4a9b77d281646385bf48fd85b8a03c4d28bbee23`，开始时无未提交修改。
- 工作目录：`D:\ldj\03\DeskMate`，开始为空。通过 `git clone --no-hardlinks D:\ldj\03\likecc D:\ldj\03\DeskMate` 复制已跟踪代码及独立 Git 对象；未复制源目录的虚拟环境、私有配置、缓存或构建产物。源目录不作修改。副本远端为 `https://github.com/KNIGHT15235/likecc.git`，未提交、未推送。
- 没有发现适用的 `AGENTS.md`。实际阅读了 README、pyproject、verification、两个入口、Agent，以及权限、工具、Memory/Session、Skills、MCP、Hook、Worktree、Task/Team 和相关测试。
- 宿主：Windows 10 `10.0.19045`，PowerShell `7.6.9`；默认系统 Python 为 `D:\anaconda3\python.exe` / `3.12.7`。
- 按用户补充要求，正式运行与验证环境为 WSL2 `Ubuntu-24.04`，内核 `6.6.87.2-microsoft-standard-WSL2`，`conda activate cc`，Python `3.11.16`，解释器 `/home/ldj/anaconda3/envs/cc/bin/python`。
- Windows 两个目录分别映射到 `/mnt/d/ldj/03/DeskMate` 和 `/mnt/d/ldj/03/likecc`。源仓库最终复核仍为同一 HEAD、干净工作区。

## 目标和实际改动

`likecc/runtime.py` 的 `Runtime` 接受显式 `AppConfig`、工作目录、权限模式和借用的 HookEngine。它集中创建模型 client、权限检查器、基础工具表、ToolSearch、Agent，以及 Worktree、AgentLoader、TaskManager、TraceManager、TeamManager 和委派工具。

装配分两步：`initialize()` 获取公共核心；`assemble_delegation()` 在入口加入特有工具后连接委派能力。这样保持原工具 schema 顺序和 TUI 的扩展绑定时机，不将两种入口强行补成相同能力。配置和 Provider 作运行实例快照，Provider 的窗口缓存不再污染其他实例。

- TUI：`LikeCCApp._select_provider()` 调用共享核心；`_configure_interactive_runtime()` 保留 Memory、Session、FileHistory、Skill、交互工具、终端命令和展示逻辑。
- 非交互：`_run_prompt()` 调用同一核心与委派装配，保留 stdout 输出、后台结果通知循环和 180 秒后续处理上限。
- `Agent.run()` 和 `run_to_completion()` 的循环代码没有修改或合并。
- 新增 `LLMClient.aclose()`；模型元数据查询和 TUI 记忆侧查询使用 `finally` 关闭临时 client；AgentTool 持有并关闭模型覆盖创建的 client，继承的父 client 只借用。
- TaskManager 取消并等待子任务，包括还没开始执行的任务；TeamManager 等待进程内队友结束。共享运行时关闭一次、可重复等待，清理失败会记录日志并继续尝试后续资源。
- TUI 跟踪前台回复、通知轮询、记忆预取、会话摘要、窗口解析、Worktree 定时清理等任务。正常退出、强制退出、测试卸载和初始化中断统一经过 `_close_resources()`。
- MCP 由 TUI 的 `_serve_mcp()` 在同一协程中连接、保持和关闭；初始化未完成就退出也有回收路径。运行时不重复启动或关闭 Hook/MCP。
- Runtime 为团队名解析提供实例独立的 AgentNameRegistry；旧的直接 TeamManager 使用方式仍保留默认注册表行为。新增运行时及其子 Agent 的工具结果放在原 `.likecc/session/tool-results/` 下的独立子目录，避免相同 tool-use ID 串扰；既有文件不迁移、不删除。

## 资源归属

| 对象或任务 | 创建 / 持有者 | 关闭责任 |
| --- | --- | --- |
| 主模型 client、权限、工具表、Agent、Task/Trace/AgentLoader/Worktree/TeamManager | Runtime；入口保留引用 | `stop_background()` 先停止委派任务，`aclose()` 再关闭模型 client |
| 覆盖模型的子 client、嵌套 AgentTool | AgentTool，归 Runtime 资源树管理 | 子任务退出后 `AgentTool.aclose()`；共享父 client 不重复关闭 |
| MemoryManager、SessionManager、当前 Session、FileHistory、SkillLoader/Executor | TUI | `_close_resources()` 关闭当前会话文件；无句柄管理器随实例释放 |
| ConversationManager、会话恢复/切换、消息写入和召回流程 | 各入口 | 入口管理；不在 R1 下沉 |
| HookEngine | CLI 创建并交给入口拥有，Runtime / Agent 借用 | TUI `_shutdown_hooks()`；非交互 `_run_prompt_with_hook_cleanup()`，均在原事件循环中完成 |
| MCPManager、MCP 连接 | TUI `_serve_mcp()` | 同一协程的 `finally`，关闭后才释放 Runtime client |
| TUI 定时任务和前台协程 | TUI `_spawn_task()`，Hook/MCP 单独持有 | 取消并 gather；Textual 计时器停止 |
| 持久会话、记忆、用户 Worktree 和团队元数据 | 原有存储机制 | 不因通用 Runtime 关闭而全量删除；TUI 保留原有团队删除策略，headless 保留团队元数据 |

调用方负责先停止前台执行，再关闭 Runtime。`initialize()` 自身失败会回滚；第二阶段装配及入口扩展失败由入口的 `try/finally` 回收。`finish_cleanup()` 用共享清理任务和 shield 处理重复等待、取消等待者，先完成资源清理再传播取消。它不是强制终止无法响应取消的第三方代码的机制。

## 保留的入口差异

| 项目 | TUI | `-p` |
| --- | --- | --- |
| 模型选择 | 交互选择 Provider | 首个 Provider |
| 执行与输出 | `Agent.run()` 事件、流式界面 | `run_to_completion()`，打印最终文本及后台后续结果 |
| 权限交互 | 保留人工审批与模式 UI | 保留非交互权限决定，不补人工审批 |
| 记忆、会话、Skills | 装配并支持原有流程 | 不增加这些管理器和流程；仍读取项目 instructions |
| MCP | 按配置后台连接，发消息前等待就绪 | 不加载 |
| AskUser / ExitPlan / SyntheticOutput | 保留 | 不额外注册 |
| 模型窗口查询 | 后台更新 | 执行前等待查询 |
| Hook 启动 | TUI 装配后启动 | 核心装配前执行 startup |
| Worktree 陈旧清理 | 保留周期任务 | 不增加周期任务 |
| 团队后端 | 原配置和交互检测 | 固定 in-process |
| 正常退出记忆提取 | Ctrl+C 退出时按原语义尽力提取 | 不增加 |

## 验证记录

完整命令、安装限制与验证边界见 [verification.md](verification.md#deskmate-r12026-11-16)。以下是本次实测，不是复制历史数字：

| 阶段 | 结果 |
| --- | --- |
| 用户指定 WSL 前的 Windows 探测基线（uv 自动选 Python 3.13.13） | 716 passed，3 failed，1 skipped；失败为 Bash/pwd 等平台差异，不作为 R1 的验收环境 |
| WSL2 / conda cc 修改前完整基线 | 720 passed，1 个缓存权限 warning |
| 中途受影响模块回归 | 341 passed |
| 最终新增 R1 契约测试 | 20 passed |
| 最终完整 pytest | 740 passed，0 failed，0 skipped |
| 独立 SubAgent 脚本 | 90/90 |
| compileall、CLI `--help`、`git diff --check` | 通过 |

测试使用 fake 模型、临时文件/目录和 Git 仓库；包含真实 SDK 无网络关闭测试及本地 stdio MCP 连接。没有验证真实模型鉴权与服务、外部 MCP、桌面 GUI、真实终端人工操作、tmux/iTerm2 外部队友进程、打包/分发安装。本轮没有修改锁定依赖或宣称性能收益。

## 遗留问题与 R2 前置条件

1. 两套执行循环、权限事件传递和通知跟进仍分开；R2 需要先定义统一事件与取消契约，并保留本轮行为测试。
2. 会话切换、落盘、召回、Memory/Skill/MCP 的完整能力仍依赖 TUI；R2 需要明确 headless 的扩展加载、会话恢复和权限默认值后再补齐，不能静默改变。
3. 用户/项目记忆、持久团队目录仍是按原路径有意共享的持久数据，不提供跨进程并发事务隔离；这不是本轮运行实例的内存状态隔离。R2 需明确会话服务的数据访问边界。
4. 工具结果独立子目录保留供历史引用，尚无新的保留期治理；长期任务和调度不是本轮范围。
5. Hook `agent` 执行器和插件来源 Agent 加载仍未实现。MCP 自动重连及外部后端的全部错误场景未在桌面场景实测。
6. 进入 R2 前保持 `cc` 锁定依赖环境和本轮回归通过；先设计前台执行、后台结果交付、会话持有者及资源关闭顺序，再迁移服务。R3 桌面适配应依赖服务，而不是继承 LikeCCApp。

R1 到此停止；提交与推送由用户执行。
