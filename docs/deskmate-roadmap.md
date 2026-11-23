# DeskMate 开发路线与 R1 / R2 / R3 记录

## 路线状态

| 轮次 | 目标 | 状态 |
| --- | --- | --- |
| R1 | 共享装配与生命周期 | 已完成，保留下方历史记录 |
| R2 | 统一执行与会话服务 | 已完成并推送，见 R2 与 R3 基线记录 |
| R3 | 桌面入口 | 已实现，后续边界修复和补充验收见 R3.1 |
| R3.1 | 桌面边界修复与验收收尾 | WSLg 人工、DeepSeek 指定冒烟、Windows 离线真实托盘通过。两项收尾修复和 Shell 测试修正已完成，Windows 完整回归 815 通过、6 跳过 |
| R4 | 个人资料整理流程 | 已实现，指定真实网页/Provider 主流程和恢复验收通过；两项实网覆盖限制保留 |
| R5 | 持久任务与调度 | 已实现；Windows 提醒/单实例、真实资料排队/批准写入/回读/成果重启已有人工证据，UI1 已修正。独立副本已修复三项提交前审查问题，最新离线 WSL 903 通过、Windows 897 通过/6 跳过；真实拒绝写入由用户跳过，限制见验证记录 |
| R6 | 个人记忆 | 已实现工作区确认记忆、来源管理和有界前台召回；R6-0 核对串记录修复及 R6-C 离线完整流程通过，最终双平台数字见验证记录；可见人工清单待用户复核 |
| R7 | 主动通知与交互 | 计划，未实现 |
| R8 | 演示、打包、验证和文档整合 | 计划，未实现 |

提交前审查补记（2026-11-22）：后续修复位于 `D:\ldj\03\DeskMate-Standalone`，分支 `main`、基线 `4da6c962eb0b4bbe90f70068ea776adeb7149b43`。已修复定时任务隐式读取指令/include 越过材料范围、部分写入报错遗漏待核对保护，以及启动关联落盘失败残留句柄阻塞队列三项问题；边界回归和本轮完整复测见 [验证记录](verification.md#r5-独立仓库提交前审查修复2026-11-22)。此前人工/真实模型结果作为历史证据保留，本轮没有新增计费调用，也未提交或推送。

DeskMate（桌伴）是目标产品名称。保持 Python 包 `likecc`、原 CLI `likecc`、配置目录 `.likecc`、项目规则 `LIKECC.md` 以及历史会话路径；R3 增加桌面入口 `deskmate`，R4 增加资料工作流，R5 增加个人持久调度，R6 增加有来源的工作区确认记忆。CLI/TUI 旧记忆行为保留。

## R1 基线（2026-11-16）

以下 R1/R2 章节描述各轮当时的代码与验证状态；当前实现的变化见文末 R3 章节。

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

## R2：统一执行、交互与会话服务（2026-11-16）

### 实际起点和复核结论

- 目录：`D:\ldj\03\DeskMate`，WSL 挂载 `/mnt/d/ldj/03/DeskMate`。
- 分支 `feat/deskmate`；起点及结束时 HEAD 均为 `834ad1de41eae48559e984428a73e9c116fbcee8`，与用户提供的 R1 SHA 一致，没有额外提交。开始时工作区干净；本轮改动留在工作区，未暂存、提交或推送，也未修改 Git 凭据或全局配置。
- Windows 10 / WSL2 Ubuntu 24.04，内核 `6.6.87.2-microsoft-standard-WSL2`；`conda activate cc`，Python `3.11.16`，`/home/ldj/anaconda3/envs/cc/bin/python`。沿用 R1 已安装的依赖，没有修改 pyproject、锁文件或升级依赖。
- 修改前完整 pytest：**740 passed，0 failed，0 skipped，28.56 秒**；实际源码确实仍有两套循环。TUI 负责会话、记忆召回、Skills/MCP 等业务，R1 Runtime 仅共享装配。
- 未发现适用的 AGENTS.md。Windows Git 的只读检查提示仓库归属不同；改用用户指定 WSL 中的 Git，没有添加全局 safe.directory。
- 最终复核原目录 `/mnt/d/ldj/03/likecc` 仍为 `4a9b77d281646385bf48fd85b8a03c4d28bbee23`、工作区干净。

### R2-A：一套循环与独立交互

`Agent._run_loop()` 是唯一的模型调用、工具执行、结果回填循环。`run()` 转发事件并关闭底层模型流；`run_to_completion()` 消费 `run()`，只返回终止轮的回答，不拼接中间文本、工具输出或重试片段。子 Agent 仍直接用后者，不创建用户会话。

以原 TUI 的完整循环为基础，统一上下文预算/压缩、thinking、max_tokens 恢复、工具并行规则、Hook 和文件快照机制。所有现有模型客户端都提供 `stream()`；本轮没有额外复制一套非流式传输循环。完整结果的回调保留 `usage`、`stream_text`、`tool_use` 字典接口；流文本现在按增量回调。

`interaction.py` 的 `Interaction` 管理运行内 Future；外部只看 `PermissionRequest` / `UserInputRequest` 普通数据，并用 `reply(run_id, request_id, value)` 回复。回复只接受当前、未完成的请求。没有交互处理器时立即拒绝；显式交互默认等候不超过 300 秒，超时拒绝。拒绝、未知、重复、过期、跨运行回复及取消均有测试。

`ErrorEvent.fatal=False` 是诊断，`ToolResultEvent.is_error=True` 是可恢复工具失败；`LoopComplete.status` 区分 `completed`、`failed`、`limit`、`cancelled`（最后一个由服务收尾发布）。达到迭代上限不再以部分回答伪装成功；模型异常原类型继续传播。

### R2-B：会话服务与显式扩展

| 文件 / 接口 | 职责 |
| --- | --- |
| `runtime.py` / `Runtime` | 配置和工作目录快照、client/权限/工具/Agent/委派装配；持有一个服务及可选扩展；按顺序关闭 |
| `service.py` / `SessionService` | 创建/恢复会话、上下文与记忆召回、输入只追加一次、持久化、状态和中断修复、记忆提取/摘要任务 |
| `service.py` / `RunHandle`, `RunEvent` | 单次运行、唯一事件消费者、回复、取消、最终结果；`to_dict()` 可 JSON 序列化 |
| `extensions.py` / `RuntimeExtensions`, `ExtensionOptions` | 显式启用 Skills、交互工具、MCP、Hook 与 Worktree 清理；不依赖 Textual |
| `app.py`, `__main__.py` | TUI 展示、命令、键盘/弹窗回复与 CLI stdout/后台通知策略；均调用服务 |
| `memory/session.py`, `conversation.py` | 兼容 JSONL 的 `run_state` 审计记录、恢复截断标识、临时上下文标识 |
| `examples/deskmate_session.py` | 通过公共服务 API 的 fake 模型临时工作区演示 |

服务选项 `persistent`、`memory`、`summaries` 默认关闭；TUI 显式开启，`-p` 保持关闭。扩展选项也默认全部关闭。非 UI 调用方可以构造 `RuntimeExtensions(runtime, ExtensionOptions(...))`，在 core 初始化后调用 `initialize()`。TUI 在 core 初始化前注册扩展，以保持 LoadSkill 在 ToolSearch 前的 schema 顺序。

### 资源、会话和取消契约

- 一个 Runtime 只允许一个 SessionService；一个服务同时只允许一次运行，重叠调用明确报错。同一进程中两个服务不能同时打开同一路径下同一会话；跨进程写入没有事务锁，仍不支持。
- 同一服务新建/恢复会话时也调用 `Agent.reset_session_context()`，清理工具发现、激活的 Skills、文件缓存、压缩恢复/替换状态与当前用量；工具结果使用新的独立子目录，已有结果不删除。恢复会话的历史 token 总量作为基线保留。这是为隔离而明确改变的会话切换行为，权限模式和工具启用策略仍属于 Runtime。
- 服务持有会话、FileHistory、MemoryManager、运行交互和摘要/提取任务。Runtime 关闭服务，再停止子任务/团队、关闭扩展、子模型 client 和主 client；关闭可以重复。运行取消只停止当前执行，不顺带关闭 Runtime 或取消独立后台子任务。
- 公开消费方式是 `async with service.start(...) as run`，再消费 `run.events()`。提前 break 时退出该上下文会取消并等待收尾；也可用 `aclosing(run.events())` 显式关闭事件生成器。`await run.cancel()` 是取消/等待清理接口，`run.result()` 或仍有效的事件订阅以 `CancelledError` 表达取消。TUI 捕获后显示取消提示。
- 环境、长期记忆注入和当次召回是临时上下文，不再作为普通用户消息重复落盘。下一次召回替换上一次召回；历史恢复只加载一次。识别 R1 保存的标准环境/长期记忆封装后重新加载当前上下文。
- 正常、失败、取消和上限状态写入 `run_state`；旧读取器忽略未知记录类型，新读取器不会把审计记录交给模型。异常中断工具链保留已收到的结果，对缺失结果补“结果未知，检查外部状态”的错误记录。
- 进程崩溃遗留的不完整尾部沿用原校验器过滤；仅发生恢复修复时追加已有格式的 compact boundary，避免后续追加又被旧孤立调用截断。不删除原始审计记录。普通重复恢复不追加任何消息或边界。
- 模型异步流被显式关闭；Bash 在 WSL/POSIX 取消时杀死进程组并等待子进程回收。取消不能撤销已经写入的文件或远程副作用，第三方工具仍须遵守异步取消契约。
- MCP 的连接和关闭保持同一任务。配置/Skills 等初始化异常关闭 Runtime 已有资源；MCP 不可用按原入口策略降级，诊断可从服务事件和 `diagnostics` 观察。未启用不启动。
- 借入的 HookEngine 仍由入口负责 startup/shutdown。扩展 `hooks=True` 则从配置创建、持有并关闭 engine；不允许对同一个借入 engine 再接管生命周期。session_start/session_end 沿用原 Agent 的“每次完整调用”语义，不等于每创建一个磁盘会话触发一次。显式异步 Hook 属于 engine 生命周期，可继续到 Runtime/入口关闭。

### 保留的差异与有意变化

- TUI：持久会话、记忆/召回/摘要、Skills、配置的 MCP、交互工具、终端命令、界面展示和交互回复保持启用。
- `-p`：非交互、仅 stdout 最终答案、原权限模式、后台子任务通知处理和 180 秒后续处理上限保留。不默认增加记忆、会话、Skills、MCP 或交互工具；默认权限不是自动批准。
- 子 Agent：轻量 `run_to_completion()`，保持工具限制、fork 与工作目录语义；没有用户会话或记忆写入。现在共享完整循环的 Hook、thinking、输出恢复和并行读取行为。
- 原来完整结果路径的缺口被补齐；迭代耗尽明确失败，终止轮为空时返回空串，不回退到早先的中间文本。权限事件不再暴露 Future，旧交互调用者必须显式提供 Interaction。已更新原权限/Worktree 测试使用新回复协议，保留原批准、拒绝、目录捕获断言。

### R1 遗留修正与实际发现

1. AskUser 原路径先等待 Future，TUI 却只在工具结果之后检查 pending，形成等待环。改为执行器先发布 UserInputRequest，再等待外部回复；移除旧 AskUserEvent/Future 通道，直接调用工具或无交互时立即报工具错误。
2. 真实问答界面测试进一步触发富文本 `MarkupError`，并发现原组件按问题文本返回答案，而工具按 `name` 读取。最小修复采用 Rich Text 渲染、转义动态内容、按 `name` 回复、适配 checkbox 标识及拒绝空问题列表；加入实际键盘输入验证。未重做 UI。
3. 原 Agent 每五轮 `ensure_future` 的记忆提取没有资源归属。迁入服务跟踪、使用历史快照，关闭时等待取消完成，再关闭 client。
4. 原 Bash 取消缺少进程回收。增加进程/进程组清理与真实本地 `sleep` 子进程取消测试。

### 验证结果与 R3 前置条件

实际命令和中途失败记录见 [verification 的 R2 章节](verification.md)。R2-A 检查点 **189 passed**；最终完整回归 **775 passed，0 failed，0 skipped，23.19 秒**，比基线新增 35 项；独立 SubAgent **90/90**。编译、CLI help、`git diff --check` 通过。批准/拒绝/取消三个无 UI 演示均成功；新解释器禁止 Textual 导入时也能运行完整演示。耗时不是性能指标。

具备进入 R3 的服务接口条件：桌面入口可以接收 `RunEvent.to_dict()`、按标识回复，并显式取消/关闭。R3 仍是计划，需确定桌面技术、主线程与 asyncio 的衔接、窗口关闭/消费者断连策略、错误展示和配置入口，再验证实际桌面环境。

仍未覆盖真实模型、远程 MCP、外部队友进程、原生 Windows 本轮回归及分发安装；R1 Windows 历史失败没有被宣称已修复。会话恢复不是持久任务恢复；权限等待仅在进程内；没有跨进程会话事务、任务调度或副作用回滚。直接使用 Agent/SessionManager 的低层调用方应自行避免并发；服务租约约束适用于 SessionService API。事件订阅当前单消费者，尚无跨线程传输或有界事件背压，桌面适配时需及时消费。

## R2 提交与 R3 开发记录（2026-11-17）

R2 已提交并推送到 `feat/deskmate`：`7f09816729ca63717b050f0cd9690c79049d456e`，父提交为 R1 `834ad1de41eae48559e984428a73e9c116fbcee8`。上方“未提交”等表述属于开发结束时的历史记录；R3 从此 R2 提交开始。

### 基线与目标

- 实际目录 `/mnt/d/ldj/03/DeskMate`，分支 `feat/deskmate`，HEAD 与 R2 SHA 完全一致，开始时工作区干净；没有适用 AGENTS.md。原 `/mnt/d/ldj/03/likecc` 保持 `4a9b77d281646385bf48fd85b8a03c4d28bbee23`、工作区干净。
- 环境：Windows 10 下 WSL2 Ubuntu 24.04.4 LTS，内核 `6.6.87.2-microsoft-standard-WSL2`，Conda `cc`、Python 3.11.16。修改前实测完整基线 **775 passed，28.41 秒**。
- 本轮实现可选 Qt 桌面入口，复用 R2 Runtime/SessionService/RunHandle/Interaction；不开发 R4，不提交或推送。

### 四个检查点

| 检查点 | 实际改动 | 验证状态 |
| --- | --- | --- |
| R3-0 | R2 遗留边界：Bash 超时/取消不再只判断 shell returncode；清理自己创建的 POSIX 进程组和输出管道 | 修复前新增测试 2 failed / 1 passed；最小修复后相关回归 77 passed |
| R3-A | 无 Qt 的 DesktopController，专用非 daemon 线程/asyncio loop；命令通道、独立事件消费、展示快照 | 检查点 44 passed，资源创建、回复、运行、取消、关闭线程归属及 R2 契约通过 |
| R3-B | Qt Widgets 对话/工具/权限/问答/会话；显式工作区配置；隔离演示 | 初始 GUI/控制器检查点 9 passed；后续增加完整 schema 和异常测试 |
| R3-C | 实际托盘检测、隐藏/恢复/消失策略、无托盘选择、异步退出与慢关闭提示 | 桌面检查点 19 passed；最终全量包含 21 项桌面测试，真实托盘仍待人工验收 |

最终完整回归 **800 passed，0 failed，0 skipped，67.77 秒**，比 R2 基线增加 25 项；独立 SubAgent **90/90**。此前一次全量为 796 passed，其后补足四种问答、慢关闭、工具退出和不支持问题类型等边界，以最终版本记录为准。完整命令、试验失败和环境证据见 verification 的 R3 节。耗时是单次记录，不代表性能提升。

### 关键设计与取舍

- Qt 主线程只持有窗口、控件、托盘与展示状态。`desktop/controller.py` 的 DesktopController 在一个长期工作线程内以 asyncio.run 管理 loop，在该 loop 创建、使用、关闭 Runtime、SessionService、交互 Future 和 client。
- GUI 只调用 `submit()`，通过 call_soon_threadsafe 提交独立命令任务；执行的事件消费任务独立存在，权限等待不会堵塞回复/取消通道。`snapshot()` 返回加锁后的普通数据副本，Qt QTimer 每 50ms 拉取；不用每 token 投递 Qt 消息，不共享可变会话或 Future。
- 后台是 RunHandle.events() 的唯一消费者。窗口隐藏、重新显示、重绘均不重新订阅。关联检查使用 session_id/run_id，回复再检查 request_id；展示记录保留 tool_id。
- 高频连续文本合并，单条最多约 12000 字符，最多 200 条、总计约 180000 字符的展示缓存；截断有明确提示，权限请求独立保留。这里只限制展示缓存，没有宣称 R2 内部服务队列具有硬容量上限，也没有给现有 put_nowait 加不安全的 maxsize。
- `config.load_config(work_dir=..., user_home=...)` 兼容扩展，保持既有优先级和 CLI 无参数语义，不使用 chdir。Runtime 与 load_instructions 增加显式 user_home 依赖注入，只为演示指定临时用户根，不全局修改 Path.home。
- 演示与真实模式使用同一控制器和服务。DemoClient、DemoWait 注入内核；演示临时目录与真实用户数据隔离，关闭外部扩展、记忆/摘要和元数据查询，界面显著标记离线。完整退出才删除临时目录。
- 桌面默认权限为 default，仅本次允许/拒绝/取消，无永久授权。Skills/MCP/Hooks/记忆/摘要各自显式启用。暂不装配委派/团队/Worktree，显式禁用计划/协调工具；原入口的工具表独立，不受影响。
- `desktop/application.py` 的 DesktopApplication 属于整个应用。有托盘时窗口关闭隐藏；没有托盘时保留最小化/退出/取消选择；运行中托盘消失恢复窗口。退出等待 Runtime 资源树、事件消费者、loop 和线程结束后才退出 Qt。15 秒未结束时报告仍在等待，不强退。

### 实现、证据与待验收

- **已实现并自动化验证**：对话、工具过程、四类问答、权限关联/拒绝/超时、取消后再次提交、新建/恢复、线程归属、配置隔离、无 Qt 时 CLI/help、展示限额、关闭与异常处理。
- **本机实际窗口证据**：存在 DISPLAY=:0、WAYLAND_DISPLAY=wayland-0 和 /mnt/wslg。默认 Qt 平台实际为 `wayland`，演示窗口可见、权限卡片已显示，并正常回收线程退出；截图保存在被忽略的 `.r1-verification/r3-desktop.png`。实际 `QSystemTrayIcon.isSystemTrayAvailable()` 为 False。
- **待人工验收**：用户在实际桌面完整操作、实际系统托盘的隐藏/找回/待回复提示、Windows 原生 Python/托盘及 Windows Bash 进程树。本轮没有声称 offscreen 或模拟托盘等于这些验收。
- **未验证/未实现范围**：真实模型、外部 MCP/Hook、打包安装、跨进程后端、退出/关机后的任务恢复、持久调度、新记忆与个人事务。POSIX 脱离工具拥有进程组的程序不在回收保证内。

进入 R4 前，应先按 [桌面说明](deskmate-desktop.md) 完成人工验收和真实托盘验证，确认首个真实 Provider/工作区在预期权限下工作。若需要 Windows 原生前端连接 WSL 内核，另行设计进程边界；本轮没有悄悄引入双架构。R4–R8 仍是计划。

## R3.1：桌面边界修复与验收收尾（2026-11-17）

### 基线与状态

R3 已独立提交并推送至 `b1d44a1ae6e09f009ac01260712a5dc508e0fd7b`。R3.1 实际从该 HEAD、`feat/deskmate` 干净工作区开始；环境仍为 WSL2 Ubuntu 24.04.4、Conda cc、Python 3.11.16、PySide6 6.8.3。此前各轮“未提交”的表述描述各轮开发结束时点，不表示当前分支未包含 R3。

本轮状态：**修复、自动化、WSLg 离线人工与 DeepSeek 指定冒烟通过，2026-11-18 退出清理完成**。修改只在 DeskMate；不暂存、不提交、不推送，不修改依赖锁或凭据，不开始 R4。

### 两项问题：本机复现与最小修复

1. **交互超时后仍显示 waiting。** 在完整 SDK 环境使用真实 DesktopController/Runtime/SessionService，加 fake client 构造权限和问答超时，再将下一次模型调用停在可取消屏障；均复现 pending 为空但 state 仍为 waiting。`controller.py: DesktopController._event()` 现在按 session_id、run_id、tool_id 清除对应交互，在没有其他 pending、当前运行仍活动且展示状态确为 waiting 时原子恢复 running。无关工具结果不清理请求，也不覆盖 cancelling、closing 或终态。
2. **launch 异常退出遗漏后台关闭。** 用实际 launch、真实 Qt 对象和实际工作线程，注入生命周期构造失败、exec 抛错和提前返回，均复现函数退出但线程存活。`application.py: launch()` 现在从控制器创建成功起覆盖构造、信号注册、Qt 执行与收尾；通过公开 request_close()/wait_closed() 兜底。正常 GUI 仍异步等待；只有 Qt 循环未开始或已结束时才有限等待，默认 5 秒。未完成清理明确报告：存在原异常则保留并添加诊断，没有原异常则抛出清理失败。只恢复成功修改过的信号处理器。

DesktopApplication.dispose() 清理 Qt 展示对象，构造中途失败也回收已取得的定时器/窗口；不操作后台服务。后台仍由原专用非 daemon 线程拥有，唯一事件消费者架构不变，未使用强杀、daemon 或新 UI 框架。

### 验证记录

- 修改前完整回归：**800 passed，0 failed，0 skipped，48.52 秒**。
- 新增失败复现：**5 failed，5.07 秒**，分别为权限/问答超时两例与 launch 三例；测试 finally 回收自己创建的线程。
- 最小修复后上述 5 项：**5 passed，3.99 秒**。
- 扩展的受影响桌面回归：**41 passed，24.08 秒**；覆盖关联错误事件、取消/关闭交错、正常 Qt exec、部分构造、部分信号注册、初始化中退出、清理超时和异常保持。
- 最终完整回归：**820 passed，0 failed，0 skipped，51.21 秒**，比基线新增 20 项；独立 SubAgent **90/90**。编译、两个入口帮助、锁一致性和 diff 检查通过。详见 verification 的 R3.1 节。
- 本轮实际 WSLg 冒烟：Wayland 窗口可见，离线演示 idle，托盘 False；正常 launch 返回 0 后 worker_alive=False。只观察启动/显示/退出，没有自动点击或提交任务，也没有将其写作完整人工验收。
- 2026-11-17 用户补充完成 WSLg 无托盘离线人工清单：拒绝/批准写入、问答结果与单次最终输出、DemoWait 取消后重用、新建/恢复且文件未变化、取消关闭、最小化找回、5 秒超时后回到就绪及再次运行。正常和短超时演示退出均反馈退出码 0、进程/线程退出、临时工作区已清理。证据来源为用户逐项反馈与两张超时截图，不是自动点击，也不包含真实 Provider。

### 建议的验收范围调整

明确建议区分支持证据，保留上方 R3 历史要求：

- **A：当前主验证环境**为 WSL2/WSLg 可见窗口及无托盘降级。自动化、可见窗口启动、用户离线点击清单与首个 DeepSeek 指定冒烟均已完成。
- **B：后续兼容性验证**为真实托盘、原生 Windows、分发安装。保持未验收，不为本轮强装 Linux 桌面或引入 Windows/WSL 双进程架构。

两项修复通过、完整自动化无回归，且 A 的人工清单与 DeepSeek 指定冒烟已确认，可以建议进入 R4。真实托盘缺失是 B 的环境/兼容性限制，不是当前 A 的阻塞缺陷；B 可纳入 R8 兼容性、打包和交付验证。若后续工作依赖其他平台，应先验证该平台；本轮不自行开始 R4。

准确的可复制命令、无托盘清单和真实 Provider 配置来源见 [桌面说明的 R3.1 节](deskmate-desktop.md)，逐项证据见 [verification.md](verification.md)。修复与离线阶段没有真实模型调用；真实验收经用户单任务费用授权，由用户本机隐藏输入 Key 并逐项发送/批准，Codex 不接收或改写 Key。

### 真实 Provider 验收结果

- 环境与配置：cc、Python 3.11.16、PySide6 6.8.3；DeepSeek / deepseek-r31 / deepseek-flash，anthropic 兼容协议。只在独立验收目录创建空密钥项目配置、Bash 拒绝规则和内部临时目录，不影响原 likecc 或全局凭据。读 allow、写 ask 的桌面语义不变。
- 实际任务：ReadFile 一次成功；模型先文字询问批准，确认当时无 WriteFile、无摘要文件，不是审批绕过。继续当前任务后出现实际 WriteFile 卡片，用户批准后一次写入成功；summary.md 与源事实/工具参数一致，源文件未变。无需为模型的文字询问修改业务代码。
- 继续与恢复：继续标记回复一次，无新工具；退出后重启并恢复原会话，用户确认历史/编号正确，无新卡片。文件哈希、mtime_ns、大小及工具次数未变，原 assistant 五条，新空白会话没有模型或工具记录。
- 清理：两次真实 GUI 退出均由用户确认 wait=0，自动核查两个记录 PID 均已消失，公开文件和会话保留。配置实际 api_key 仍为空、权限 0600，没有把 Key 写入记录。
- 范围：只确认该 DeepSeek 配置与指定任务、恢复展示和不重放；未在恢复后另发模型任务，未验证所有 Provider、长稳或平台兼容性。最终实际 Wayland 托盘仍 False；Windows 当前探测到的 Python 未装 PySide6，原生 GUI、真实托盘、安装包均未验收。实际扣费未查平台账单，不将五条 assistant 记录当作 API 请求/计费次数。

### 保留限制与后续事项

R2 服务事件队列仍无硬容量上限，展示缓存与单消费者限制不变。取消不撤销副作用，进程退出后不恢复任务。输入提交后立即清空、整段历史定时重绘等体验事项仅记录，不在本轮修复范围；本轮没有引入额外业务或依赖。

### Windows 原生托盘验收准备补充（2026-11-18）

用户随后选择提前进行原生离线托盘验收。已在 `.venv-win-r31` 创建隔离 Windows Python 3.12.7 环境，使用未变的 uv.lock 安装 desktop extra，PySide6/Qt 6.8.3；没有修改 WSL cc、原 likecc 或基础 Python 的包。入口、锁一致性、依赖检查通过，实际 Windows Qt 托盘探测为 True，首个人工窗口/图标步骤待确认。

本机五个桌面测试文件实际为 39 passed、2 failed（4 warnings）：两项 GUI 测试的全局 connect 拦截误伤 Windows asyncio 内部 socketpair，调用栈已复核；保留失败与待修复事项，不改弱断言。独立 demo 控制器初始化、关闭与临时目录清理通过，因此可以继续分步人工检查，但不宣称原生完整回归或平台兼容通过。本阶段没有业务代码或测试修改，没有真实模型调用、提交或推送。详情与实际命令见 verification 的新增原生环境节。

### Windows Conda 环境切换与复核（2026-11-18）

用户随后指定 deskmate-win。已在 Windows Conda 用户环境目录创建 Python 3.12.7 环境，按 uv.lock 导出并以哈希校验安装 57 个适用第三方依赖及 editable 项目；61 个已安装包依赖检查通过。使用 conda run + python -s 核对解释器、源码路径和用户 site 隔离；启动/关闭/临时目录清理通过，实际 Windows 托盘可用 True。旧 `.venv-win-r31` 的 58 个包版本未变，WSL cc 保持原样。

初次桌面回归为 36 passed、3 failed、2 errors；改用安全的全新 pytest 临时目录后为 39 passed、2 failed，已知 socket 钩子兼容失败仍保留。首轮另暴露关闭耗时警告会被 command ACK 覆盖的 UI 时序缺陷，重跑通过不能代替修复，列入待处理事项。本阶段没有修改业务代码或测试，不将 Conda 切换表述为修复测试问题。

当时原生环境已具备离线可见窗口与托盘人工观察条件。用户后续完成结果见下方，Shell、路径、进程树及安装包仍另行验证。命令和两次自动化结果见 verification 的 Conda 节。

人工进展（2026-11-18）：用户确认 deskmate-win 离线窗口就绪，真实 D 图标出现，点击标题栏 X 后窗口隐藏且程序继续运行。从托盘恢复后，窗口仍为离线演示、就绪，工作区与会话均未变化。启动、隐藏与恢复通过。

用户随后按连续清单完成 WriteFile 批准、问答进入 DemoWait、执行中隐藏/恢复、隐藏时托盘取消并恢复查看结果、同会话继续完成任务、托盘真正退出，明确反馈各项符合预期。退出码 0，用户进程检查通过。Codex 只读复核 PID 54464 消失，未检测到该 Conda 路径的遗留 Python 进程。因此 Windows 原生离线真实托盘清单通过。此次人工临时工作区具体路径待提供，目录删除尚待独立核查。

### R3.1 人工验收收尾时的状态（2026-11-18）

已通过范围包括原始超时展示与 launch 异常收尾修复、WSL 修复阶段完整 pytest 820 passed 和 SubAgent 90/90、WSLg 无托盘离线人工、DeepSeek 指定真实任务与退出恢复，以及 Windows Conda 离线真实托盘清单。当时 Windows 桌面自动化结果为 39 passed、2 failed，首轮还暴露关闭提示覆盖竞态。

人工验收后进入收尾修复，范围为 Windows 防联网测试对内部 socketpair 的兼容，以及关闭耗时警告的展示优先级。共享 pytest TEMP 的访问问题已通过隔离 basetemp 排除，原目录保留。

待验证范围包括本次人工临时目录删除、Windows Shell/路径/链接/权限与子进程树、Windows 真实 Provider、外部扩展集成、真实会话恢复后的新模型调用、长期稳定性及 DeskMate 干净安装和打包。交付兼容项继续纳入 R8 计划，依赖相关平台能力时先验证。R4 保持计划状态。

人工验收收尾阶段只更新四份文档并做只读检查，前述数量保留各自执行阶段含义。

### R3.1 收尾修复与双环境复测（2026-11-18）

先在 Windows 完整回归复现三项相关失败，再修复测试防联网钩子和关闭提示优先级。WSL 修复前的单项测试也稳定复现了提示覆盖。防联网钩子仅允许 `socketpair()` 建立内部回环连接，普通连接保持拦截。关闭过程中由应用提示优先，迟到的命令确认和托盘消失都保留警告。

Windows deskmate-win 和 WSL cc 的桌面专项各 42 passed。WSL 完整回归 821 passed。该阶段 Windows 完整回归由 808 passed、6 failed、6 skipped 改善为 812 passed、3 failed、6 skipped，三个 POSIX 命令兼容失败在下一阶段处理。

用户已通过的 WSLg、DeepSeek 与 Windows 真实托盘人工验收保留原有范围。当前待验证项为本次人工临时目录核对，以及 Windows 系统兼容与后续交付范围。R4 保持计划状态，R3.1 改动仍留在 feat/deskmate 工作区。

### R3.1 Windows Shell 集成回归补记（2026-11-18）

先复现三个失败并确认 Windows 默认 `cmd.exe` 的行为。两项 Worktree 测试改用原生的工作目录查询命令，文件流程按目标系统构造 Python 校验参数。保持生产 Shell、工作目录传递及 POSIX 进程组逻辑。Windows 相关测试 87 passed、5 skipped，完整回归 815 passed、6 skipped、0 failed。WSL 受影响测试 92 passed。完整命令和诊断见 [verification.md](verification.md) 文末。

## R4 个人资料整理（2026-11-18）

基线 `19e5d6d74c8413b71088e4dea3be538da3b05151`，分支 `feat/deskmate`。开工时已有三个用户提供的文档处于未跟踪状态，保留 R3.1 审查和 R4 提示词，目标规格仅更新进度。

| 检查点 | 实际交付 |
| --- | --- |
| R4-0 | 有界命令回执按 ID 消费，保护草稿版本和关闭提示。切换失败进入可恢复错误状态，分别保留失败的资源和待删除的临时目录 |
| R4-A | 正常桌面装配资料身份、限额文件工具和指定公网 URL 工具。锁定源地址后保留 Host 和 TLS 名称；每跳重新校验。来源记录随任务重置 |
| R4-B | SessionService 驱动原 Agent 循环，审批后写 Markdown，工具追加来源账目，回读摘要一致后更新成果面板。离线示例与拒绝写入实验可运行 |
| R4-C | 相关和完整回归已记录，两份 IANA 实网读取、真实 Provider 资料任务、产物回读和会话恢复通过。11 月 20 日补充通过权限等待取消后的同会话重用 |

调用链为 `ChatWindow → DesktopController → SessionService/RunHandle → Agent → PermissionChecker/Interaction → ReadFile/FetchWebPage/WriteFile → RunEvent → 界面摘要`。来源及成果状态属于本次运行。持久会话保留工具历史，文件保留工具追加的来源账目。

R4-C 收尾在 Codex 发起的 WSL `cc` 和 Windows `deskmate-win` 以及用户平时启动 GUI 的 WSL 终端复现 Fake-IP 地址拒绝。原脚本备份后，用户在 Clash Verge Rev 2.4.1 的当前订阅应用单域名过滤。WSL `cc` DNS 复测和两份验收页面的无模型真实 HTTPS 读取通过。用户在可见窗口批准两次网页读取及一次写入，单次真实 Provider 任务完成，产物和回读证据已核实。退出重开并恢复原会话后，用户确认状态正确，磁盘文件和会话日志与退出前一致。[R4 验证记录](verification.md#r4-真实网页验收前的-dns-诊断)

2026-11-20 用户确认连续验收结果正常。新会话日志复核为 `cancelled → completed → completed`，确认取消后可继续使用同一会话。新产物只写一次并完成回读，退出恢复前后 7 个文件的哈希、大小和修改时间一致。R4 核心功能与人工主流程验收完成。实际 HTTP 响应流期间取消、实网重定向保留为覆盖边界。R5 仍是后续计划，设计独立于桌面进程的持久任务与调度。R6–R8 范围沿用目标规格。

## R5 持久任务与调度（2026-11-20）

从 `feat/deskmate` 的 `0d76f22d729c781bf4a6f584b0f16f8ab0d73f4a` 开始，初始工作区干净，未发现 AGENTS.md。未改变分支、提交或推送，依赖锁和已有真实验收材料保留。

| 检查点 | 交付 |
| --- | --- |
| R5-0 | 会话关闭失败可重试且并发共享；网页规则仅 * 通配、主机规范化而路径/查询大小写保留；Markdown 来源原文可复制；空网页标 empty 并禁止正文引用 |
| R5-A | 标准库 sqlite3 独立个人任务模型；定义/单次记录分表、唯一时刻、事务领取、实例所有权；一次性和每周、本地时间/时区与冻结范围 |
| R5-B | 应用后台调度、前台忙时排队；独立会话但唯一活动运行和消费者；模型确认与 R4 工具权限；即时证据保存和重启核对 |
| R5-C | 可控时钟、真实 SQLite、离线模型/Qt 完整案例；领取后/写入后真实子进程硬退出实验；双平台回归和学习记录 |

调用链、存储表、恢复策略、人工步骤、真实计费验收建议范围与首版限制见 [任务说明](deskmate-schedules.md)。本轮可见桌面人工验收和真实计费模型调用尚未进行，待单独授权后执行；R4 的真实 HTTP 流中途取消与实网重定向限制不变。R6/R7/R8 仍按目标规格推进。

R5 人工验收准备补记：已核对历史 XML，并在仓库外隔离工作区完成原生 Windows 启动/关闭预检与 29 项现有离线专项。用户要求集中执行，完整操作编号及预期已补入任务说明。可见桌面结果等待用户反馈，真实 Provider 仍未授权、未执行；不把上述预检升级为人工通过。当前不据此新增“人工验收通过、可提交”的结论。

直接操作补记（2026-11-20）：用户授权 Codex 操作电脑后，实际读到原生 DeskMate 就绪控件并填入测试草稿；截图超时、点击失败、键盘导航无可见效果，用户恢复前台后仍未恢复控制。停止在未发送状态，隔离任务库仍为空。记录为电脑控制通道阻塞，不算产品缺陷或人工通过；可见 A/B/C 与真实 Provider 继续待完成，离线证据保持原结论，未启动 R6。

逐项人工进展（2026-11-22）：用户确认独立工作区启动、空任务窗口正确；提醒预览截图的时间、时区、范围和未保存状态符合预期。已完成 P1/P2/A1，持久保存、隐藏到期、重启和周期执行尚待继续，真实 Provider 未授权。没有新增产品修复或测试执行，不据此宣布 R5 全部人工通过。

后续用户确认 A2 歧义澄清、A3 提醒保存、A4 隐藏后到期通过；数据库只读审计对应一项安排和一条 pending 记录，输入未变，无输出。完成提醒、重启、周期资料与恢复案例继续逐项验收，真实 Provider 仍未授权。

A5/A6/A7 后续通过：重复扫描保持一条，完成后为 done，正常退出重开保留同一记录，数据库和文件审计一致。新增 UI1 窗口可达性问题：用户重开后主窗口部分位于屏幕外，无法拖动；根因待定位，先恢复可见性，尚无产品修复。其余验收继续待完成。

UI1 最小修正已加入 DesktopApplication._fit_window()，启动/托盘恢复后检查可用屏幕区域，越界时恢复主窗口可达性。定向回归 3 passed，Windows/WSL 相关回归各 38 passed；未重跑完整套件，真实 Provider 未调用。用户正常重开后确认主窗口完整、可拖动、历史保留，UI1 本次 Windows 显示复验通过，数据库/文件审计一致；原始偏移原因与其他显示器配置尚未确认，恢复 A8 逐项验收。

A8 修改未来时间已通过新时间的可见记录与持久历史验证，旧时间未生成记录由数据库核实，用户错过旧时间点的现场观察。修改后的提醒已完成，历史仍唯一。A9 到期前取消及到期后不触发均通过用户确认和真实数据库审计。接下来进入周期资料预览；周期执行与后续恢复案例仍待逐项验收，真实 Provider 仍未授权。

B1/B2 周期预览、明确范围及保存已获用户确认，并由真实数据库核实每周五时间、输入/输出范围和每次模型确认策略。新周期任务未执行、无成果文件；修改、到期待确认及取消继续逐项验收，真实 Provider 保持未授权。

B3–B5 周期修改、到期待确认和取消也已通过用户确认及真实库审计；唯一执行从 awaiting_model 变为 cancelled，未调用模型，原历史保留。B6–B9 复核既有双平台离线回归中的排队、权限、回读和草稿证据，未把它们提升为真实桌面模型执行通过。继续 C1 重启与后续恢复案例，真实 Provider 仍待授权。

C1 未到期重启通过：用户确认正常退出重开后提醒继续等待，只读审计确认同一 ID、原未来时间和空执行记录，已有历史未变。当前准备取消这条测试提醒，随后验证 C2 退出期间错过提醒；真实 Provider 仍未授权。

C1 测试提醒已取消，C2 新提醒已保存，用户确认应用在原定 18:47:00 前完全退出；退出后读库仍无该次执行。当前等待用户过期后重开验证，恢复结论尚未产生，真实 Provider 未授权。

C2 用户确认过期后重开出现逾期待处理，并明确确认手动完成；实际库保留同一原定时间的一条 done，未重复、未生成成果。当前六项安排、三条 done 与一条 cancelled，重复查看收尾待继续。真实 Provider 仍未授权。

C2 重复扫描/查看收尾已通过用户确认与数据库复核。C3–C6 复核既有可控时钟、隔离崩溃及工作区隔离的自动化证据，未重跑或人工制造崩溃；不扩大为可见桌面通过。下一项 C7 检查第二 Windows 实例，真实 Provider 仍未授权。

C7 同一 Windows 工作区第二可见实例已被正确阻止，用户确认原实例仍就绪；数据库定义、执行历史与文件状态保持不变。当前仅需退出报错第二窗口并进行收尾检查；没有运行中模型任务的可见并发验证，相关状态保护沿用离线用例，跨 Windows/WSL 同库仍不支持。

C7 收尾与 D1 已完成：用户确认只退出报错第二窗口，原实例保持。最终只读审计仍为六项定义、四条历史（三条 done、一条 cancelled），无重复，样例未变、输出不存在。UI1 修正后的完整离线回归本次重新执行，WSL 891 passed、Windows 885 passed/6 skipped；SubAgent 双平台 90/90，两个入口帮助和 18 个 Python 文件内存编译通过。Windows 跳过项仍是五项 POSIX 进程组及一项系统链接测试；本次结果与先前 888/882 历史分别记录。

已准备另一仓库外临时工作区及 DeepSeek / deepseek-flash 空密钥配置，列出一次前台排队配合、一次拒绝写入、一次批准并回读的验收范围和预计请求/计费说明。真实 Provider 尚未授权或执行；B6–B9 的可见模型流程继续待验收，C3–C6 仍以隔离自动化实验证据为准。当前可进入代码评审，不能宣布全部真实验收通过；不暂存、不提交、不推送，不启动 R6。一次性/每周、Asia/Shanghai/UTC、本地单调度器、禁止 Windows/WSL 同库并发和未知写入需核对的限制不变。

授权补记：用户随后明确同意上述三次真实 Provider 验收。状态更新为“已授权，尚待执行”，授权范围不扩大；继续逐项人工指导，先正常退出旧占位 Provider 窗口。没有因收到授权就把真实执行或产物核对记为通过。

启动准备补记：用户确认旧占位实例已退出。仓库外隐藏输入启动器和新工作区检查通过，未读 Key、未创建 client 或调用模型；下一步为用户可见启动反馈。没有新增产品代码修改或重跑离线套件，真实三次运行仍尚待执行。

新 Provider 窗口可见启动已获用户确认，新库只读审计为零项安排/执行、样例不变、无输出。下一项为周期定义预览；真实模型任务仍未发起，不提前记为 API 连通或执行验收通过。

真实执行进展：周期定义、前台读取/用户输入卡片、到期单次授权后排队、前台取消后周期接续均已有用户反馈和数据库/会话证据。用户在周期写入权限等待时再次取消，执行准确保存 cancelled、无成果且原聊天恢复；作为操作偏差和取消案例记录，不冒充拒绝写入通过。原三次范围已运行两次，批准案例仍未开始；补做拒绝将增加一次真实运行，等待额外明确同意。未新增产品修复或重跑离线套件。

用户明确跳过拒绝案例补做，不新增计费重试；该真实案例保持未完成，已有离线结论保留。原第三次批准写入与回读的授权继续有效，下一步先收尾旧周期定义，再继续原计划，未扩大调用范围。

原第三次真实任务完成：用户确认本次允许写入后原聊天/草稿恢复；数据库 completed、成果 verified，磁盘文本摘要与持久摘要一致，会话记录为一次成功写入及之后成功回读。真实运行共三次，拒绝案例仍因用户跳过保持未完成。下一步仅核对可见历史、停止未来周期与重启持久性，不启动新的模型任务。

已完成可见历史核对、两项周期停用和正常退出。退出后数据库/成果对照保持，三个会话日志显示恰好三个运行。用户要求合并剩余步骤，当前等待原工作区重开和历史反馈，再做只读差异检查及最终报告；未提前标记成果重启通过。

最终重启与产物检查用户统一确认正确。只读对照为两项定义/两条执行不变，八个原文件哈希、大小和 mtime 保持，仅增加无 RUN_STATE 的空会话；原三次模型运行没有重放。本次验收收尾完成，可带明确覆盖边界进入代码评审和提交准备，真实拒绝写入保留未完成项。未暂存、提交、推送或启动 R6。

## R6：确认记忆与来源（2026-11-22—23）

本轮仅在独立仓库 `D:\ldj\03\DeskMate-Standalone` 实施，起点 `main` / `6ea15eed1d6396912abc3a102b87f13963510015`、工作区干净。按 R6-0 → R6-A → R6-B → R6-C 顺序先验证再继续；没有暂存、提交、推送或计费 Provider 请求，改动留待复审。

| 检查点 | 实际交付 |
| --- | --- |
| R6-0 | 临时 SQLite + Qt 回归先复现 A 核对串到 B；绑定执行 ID、后端检查、刷新与实际点击重试；已核对旧中断保留但不计待处理 |
| R6-A | 三类用户确认记忆，SQLite 稳定 ID/工作区/版本/状态；本地明确保存入口、查看/修改/删除；来源及修改审计保留 |
| R6-B | 本地中文双字片段/英文词检索，最多 5 条、2400 字符，UI 显示命中及来源；只加入模型请求副本，旧加载/选取/提取不接入桌面，CLI/TUI 兼容 |
| R6-C | 正常桌面控件串起保存、重启、实际上下文、更新删除、A/B 隔离、原周期任务及同会话两次 S1；可复用的持久离线可见启动器和集中人工清单 |

操作、存储、检索边界和人工清单见 [记忆说明](deskmate-memory.md)，实际测试数字见 [验证记录](verification.md#r6-独立仓库长期记忆2026-11-2223)。R7 的主动通知、稍后提醒和继续处理未提前实现。R5 真实拒绝写入缺口继续保留；旧真实 Provider/托盘/显示器结论仍只是历史证据，不冒充本轮新验收。

2026-11-23 七项 Windows 离线人工验收完成：用户逐项确认核对重试、明确保存与来源、重启召回、工作区及定时范围隔离、更正删除、两次 S1 溯源、历史恢复与界面操作。实际 fake client 输入与 SQLite/成果文件只读对照一致；最后恢复重启前后日志仍为 27 条且哈希不变，记忆修改审计仍为 5 条，四个成果文件内容及 mtime 不变，两项安排停用、六条历史保留。详见 [人工记录](verification.md#r6-七项离线人工验收2026-11-23)。

本次额外观察到切回工作区会把尚未开始的待模型确认记录标为中断，需逐条核对后手动发起新尝试。现有恢复策略没有越过权限或自动重放，本次没有修复这一体验限制。R6 可进入代码复审，并作为后续 R7 的已验收基线；真实 Provider 记忆质量、R5 真实拒绝写入及其他平台/显示配置仍保持原覆盖边界。R7 尚未开始，工作区改动继续保留且未暂存、提交或推送。

复审修复补记（2026-11-23）：已修复两项来源边界。新运行开始即清除旧来源，来源保存失败后禁止关联旧运行，并核对 session/run 身份；自动会话清理只读保护当前记忆及其更改审计引用的会话，不创建旧 CLI/TUI 的记忆库，读取失败时跳过清理。无关过期会话及删除最后引用后的原清理规则保留。正式回归覆盖真实 SQLite 锁失败、Qt 按钮与后端拒绝、后续恢复、30 天保留期、共享引用和损坏/异工作区库，结果见 [复审修复验证](verification.md#r6-复审两项修复2026-11-23)。切换工作区的中断文案体验不属于这两项修复，R7 保持未开始。
