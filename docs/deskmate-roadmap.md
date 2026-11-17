# DeskMate 开发路线与 R1 / R2 记录

## 路线状态

| 轮次 | 目标 | 状态 |
| --- | --- | --- |
| R1 | 共享装配与生命周期 | 已完成，保留下方历史记录 |
| R2 | 统一执行与会话服务 | 已完成，见文末 R2 记录 |
| R3 | 桌面入口 | 计划，未实现 |
| R4 | 个人事务流程 | 计划，未实现 |
| R5 | 持久任务与调度 | 计划，未实现 |
| R6 | 个人记忆 | 计划，未实现 |
| R7 | 主动通知与交互 | 计划，未实现 |
| R8 | 演示、打包、验证和文档整合 | 计划，未实现 |

DeskMate（桌伴）是目标产品名称。本轮保持 Python 包 `likecc`、CLI `likecc`、配置目录 `.likecc`、项目规则 `LIKECC.md` 以及历史会话路径；没有引入桌面 GUI、调度器、事务工具或新的个人记忆模型。

## R1 基线（2026-11-16）

以下 R1 章节描述当时的代码与验证状态；当前实现的变化以文末 R2 章节为准。

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
