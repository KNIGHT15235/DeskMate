# DeskMate R1 / R2 学习记录

本文记录本轮代码结构和可复现行为，不代写个人学习体会。路线与验证入口：[roadmap](deskmate-roadmap.md)、[verification](verification.md)。

前半部分保留 R1 时点的学习材料；当前执行和会话接口见文末 R2，不能把 R1 的“两套循环仍独立”等描述当作当前实现。

## 为什么从 TUI 中提取装配

重构前，`LikeCCApp._select_provider()` 和 `__main__._run_prompt()` 分别创建 client、权限检查器、基础工具、Agent 和委派管理器。新增桌面入口如果继续复制，会出现三份装配代码，权限规则路径、工作目录或关闭顺序容易发生偏差。

`Runtime` 现在只描述一个运行实例如何组装及释放公共对象。它不导入 Textual 或 LikeCCApp，不负责展示消息，也不替入口决定是否启用会话、记忆、Skills 或 MCP。测试在全新解释器里阻止所有 Textual 导入，仍能完成装配。

“装配共享”不等于“能力一致”。TUI 和非交互入口的输出、权限交互、扩展加载与执行循环仍按原方式工作。R1 为 R2 的服务迁移建立边界，没有提前实现 R2。

## 实际涉及的代码

| 文件 | 类 / 函数 | 本轮作用 |
| --- | --- | --- |
| `likecc/runtime.py` | `Runtime.__init__ / initialize / assemble_delegation / stop_background / aclose`、`finish_cleanup` | 公共装配、配置快照和生命周期契约 |
| `likecc/app.py` | `LikeCCApp._select_provider / _configure_interactive_runtime / _spawn_task / _close_resources / _serve_mcp` | TUI 适配及入口资源管理 |
| `likecc/__main__.py` | `main / _run_prompt / _run_prompt_with_hook_cleanup` | 显式传工作目录；接入共享层；保留非交互执行 |
| `likecc/client.py` | `LLMClient.aclose / resolve_context_window` | 释放主 client 与元数据查询临时 client |
| `likecc/agents/task_manager.py` | `TaskManager.shutdown` | 取消、等待及补全尚未开始执行的任务状态 |
| `likecc/teams/manager.py` | `TeamManager.__init__ / shutdown` | 注入实例名字注册表；等待队友退出 |
| `likecc/tools/agent_tool.py` | `AgentTool.aclose / _create_client_for_model / _bind_child_tools` | 子 client 归属、嵌套工具资源树和子 Agent 工具结果隔离 |
| `likecc/tools/send_message.py` | `SendMessageTool.execute` | 使用所属 TeamManager 的名字注册表 |
| `likecc/mcp/client.py`、`manager.py` | `connect / register_all_tools` | 初始化中取消也可清理；及时持有已创建 client |
| `tests/test_runtime_assembly.py` | 20 项参数展开后的测试 | 装配、隔离、入口能力、失败、取消、重复关闭和真实本地 MCP 生命周期 |

`likecc/agent.py` 的 `Agent.run()` 与 `run_to_completion()` 本轮没有修改。

## 调用关系：重构前后

重构前：

```text
main
 ├─ LikeCCApp._select_provider
 │   ├─ client + checker + registry + Agent
 │   ├─ Memory / Session / Skills / Worktree / 子 Agent / Team
 │   └─ Hook startup + MCP + UI
 └─ _run_prompt
     ├─ client + checker + registry + Agent（另一份创建代码）
     └─ Worktree / 子 Agent / Team
```

重构后：

```text
main（读取配置并捕获工作目录）
 ├─ LikeCCApp
 │   ├─ Runtime.initialize
 │   ├─ TUI 特有对象、命令和交互工具
 │   ├─ Runtime.assemble_delegation(interactive=True)
 │   ├─ Hook / MCP / 界面
 │   └─ Agent.run(conversation)
 └─ _run_prompt_with_hook_cleanup
     ├─ Hook startup
     ├─ Runtime.initialize(resolve_context=True)
     ├─ Runtime.assemble_delegation(interactive=False)
     ├─ Agent.run_to_completion(prompt, conversation)
     ├─ Runtime.aclose
     └─ Hook shutdown
```

两阶段装配让 TUI 在公共核心与委派能力之间注册自己的工具，保留原 schema 顺序和绑定关系。不要在第二阶段失败后忘记 `finally: await runtime.aclose()`。

## 初始化、执行、关闭分别由谁负责

初始化由 Runtime 创建公共依赖；入口创建其特有对象。`work_dir` 先解析为绝对路径，不通过修改进程 cwd 来切换工作区。WorktreeManager 的回调更新 Agent 工作目录和权限 sandbox，并清空对应工具缓存。

执行仍由入口驱动：TUI 消费 Agent 事件并响应用户确认；headless 收集结果、打印文本并跟进后台通知。会话对象及恢复流程仍由入口负责。

TUI 关闭时，先停止界面计时器并取消、等待入口协程，再停止共享运行时的子任务；随后清理 Hook/MCP，正常 Ctrl+C 退出时尝试记忆提取；最终关闭会话文件及 Runtime client。强制退出、初始化失败或 Textual 测试卸载，也进入同一个幂等关闭入口。

非交互入口在 `finally` 中关闭 Runtime，外层在同一事件循环中关闭 Hook。Runtime 借用 HookEngine，不重复执行 startup/shutdown。临时元数据 client 和记忆召回 client 由创建它们的局部查询负责关闭。

`cancel()` 只是发出取消请求；`await` 或 `gather()` 才能确保任务的 `finally` 已执行。共享清理任务配合 `asyncio.shield()`，让取消等待者不会把资源释放一起中断；同一个关闭任务被多次等待，不重复关闭资源。

## 一个测试构造的失败案例

`test_tui_extension_failure_closes_session_and_core` 将 `SkillLoader.load_all()` 替换成抛出 `RuntimeError("skills failed")` 的函数。

当异常出现时，主 client、Agent、MemoryManager、Session 文件和窗口查询任务已创建。`_select_provider()` 捕获该装配异常，调用 `_close_resources(run_shutdown_hook=False)`；窗口查询被取消并等待，会话文件关闭，Runtime 关闭 client，然后原异常继续向上传播。

测试断言会话文件已关闭、fake client 关闭次数为 1；随后再调用 `on_unmount()`，关闭次数仍为 1。这同时验证部分初始化回滚和幂等关闭，而不是检查源码中是否出现某个 `finally` 字符串。

另一个案例 `test_cancelled_and_concurrent_close_waits_for_resource_finalizer` 用事件阻塞 fake client 的关闭。连续两次取消等待者，资源释放仍会等到测试解除阻塞；其他关闭调用也能等待同一次清理完成。最后取消才传播回调用者。

## 对应代码的面试问答

**1. 为什么共享层既不接收 LikeCCApp，也不创建 Textual 组件？**

它依赖的是配置、路径和核心对象。UI 反向依赖 Runtime，后续桌面入口才能复用同一装配。`test_runtime_assembles_with_textual_imports_blocked` 用导入阻断验证这条边界。

**2. 工厂函数只返回 Agent 够不够？**

这里不够。Agent 背后还连接主/子 client、后台 TaskManager 和 TeamManager。只返回 Agent 会隐藏需要关闭的对象。Runtime 同时作为这些对象的持有者，公开 `stop_background()` 与 `aclose()`；入口仍对自己的会话和 MCP 负责。

**3. 为什么取消任务后还要 gather？**

因为任务尚需运行清理逻辑，直接关闭模型连接可能打断子 Agent 的 finalizer。`TaskManager.shutdown()` 等待所有任务，且处理尚未得到第一次调度的任务：这类任务不会进入协程内的 `try/finally`，需补记 cancelled 状态。

**4. 实例隔离是把所有数据复制一份吗？**

不是。配置、Provider 窗口缓存、工具发现状态、文件缓存、权限状态、任务队列和名字解析表需要独立；已有用户记忆和持久团队文件仍按原路径共享。`test_runtime_instances_isolate_config_tools_permissions_and_disk_results` 还用相同 tool-use ID 验证两个实例的结果文件不会覆盖或读到彼此内容。

**5. 为什么 MCP 需要专门的生命周期协程？**

其底层包含 AnyIO 异步上下文和取消作用域。连接和退出上下文应在同一任务中配对。`_serve_mcp()` 持有连接直到收到停止信号，在 `finally` 里关闭；入口只等待就绪或请求停止。测试既记录 fake MCP 连接/关闭时的任务身份，也启动本地真实 stdio 服务验证退出后的连接状态。

## 可以亲手验证的小实验

目标：观察“取消等待者”与“资源释放完成”是两个事件，不需要模型 Key。

在 WSL2 终端执行：

```bash
source /home/ldj/anaconda3/etc/profile.d/conda.sh
conda activate cc
cd /mnt/d/ldj/03/DeskMate
python -m pytest -q -o cache_dir=/tmp/deskmate-r1-pytest-cache \
  tests/test_runtime_assembly.py::test_cancelled_and_concurrent_close_waits_for_resource_finalizer
```

打开该测试，找出 `started`、`release` 两个事件以及两次 `close.cancel()`：前者表示已经开始释放资源，后者控制释放完成。在 `release.set()` 前后临时打印 `close.done()` 和 `client.closed`，加 `-s` 再运行；检查解除阻塞前关闭等待尚未完成，结束后 client 只关闭一次。打印结果受协程调度时点影响，应以测试中的同步点和断言为准。实验结束删除临时打印，再运行该用例。

进一步可运行整个 `tests/test_runtime_assembly.py`，其中所有模型回复都是 fake；本地 MCP 用例只启动临时 Python stdio 服务。测试通过不能推导真实模型效果、桌面交互质量或性能指标。

## R2 学习记录：从共享装配到共享执行

### 1. 初始化共享并不等于执行共享

R1 的 Runtime 让两个入口获得同样的 client、权限检查器和 Agent，但 Agent 里仍有两套完整循环。修复一条循环的 thinking、压缩或取消，并不会自动修复另一条。R2 在 `agent.py` 的 `_run_loop()` 保留一个执行内核：`run()` 产生事件，`run_to_completion()` 消费相同事件。完整结果只使用 `LoopComplete.result`，不会把“准备调用工具”混进最终答案。

### 2. 谁负责哪一段

| 阶段 | 代码 | 责任 |
| --- | --- | --- |
| 装配 | `runtime.py: Runtime.initialize / assemble_delegation` | 显式配置/目录、模型与工具、委派资源 |
| 可选扩展 | `extensions.py: RuntimeExtensions.initialize` | 显式启用 Skills、MCP、Hook、交互工具；关闭已获取资源 |
| 准备会话 | `service.py: SessionService.new_session / resume / _execute` | 历史、记忆召回、加入一次输入、持久化 |
| 执行 | `agent.py: Agent._run_loop` | 模型→工具→结果回填→下一轮；不管理用户会话文件 |
| 展示和回复 | `app.py: LikeCCApp._send_message / on_inline_permission_widget_responded` | 展示事件，通过 run_id/request_id 提交决定 |
| 收尾 | `RunHandle.cancel / SessionService.aclose / Runtime.aclose` | 当前运行→服务任务/会话→子任务/团队→扩展→client |

`SessionService` 借用 Runtime 的 Agent/client；Runtime 持有服务并负责总关闭。单独关闭服务不关闭模型或委派资源；单独取消运行也不会停止用户明确允许的后台工作。

### 3. 一次输入的调用关系

R1（历史）：

```text
TUI._send_message → 在 UI 中追加/召回/保存 → Agent.run → 第一套模型/工具循环
CLI._run_prompt → Agent.run_to_completion → 第二套模型/工具循环
```

R2（当前）：

```text
TUI._send_message ─→ SessionService.start(interactive=True) ─┐
CLI._run_prompt ──→ SessionService.run_to_completion() ─────┤
                                                        ↓
             准备上下文 → 保存输入一次 → Agent.run → _run_loop
                                                        ↓
             工具结果/状态落盘 ← RunEvent ← AgentEvent
                                       ↓
                       TUI 展示 / CLI 返回最终结果

内部子 Agent → Agent.run_to_completion → Agent.run → 同一个 _run_loop
```

会话服务给事件加 `run_id`、`session_id`，没有另造一套工具/文本事件。`RunEvent.to_dict()` 展开 dataclass，输出可以 `json.dumps()`。服务等到持久化和交互清理完成才发布唯一终止事件，状态与 `RunHandle.status` 一致。

### 4. 权限请求怎样避免等待环

`interaction.py: Interaction.request()` 在执行任务内登记私有 Future。执行器先 yield `PermissionRequest`，服务将其放到事件队列，UI 或其他消费者因此能继续运行。消费者调用 `run.reply(run_id, request_id, "allow")`，Interaction 检查标识和是否已经回复后才完成等待。

批准才执行工具；拒绝返回可恢复工具错误；没有 handler 立即拒绝；handler 没回复默认 300 秒后拒绝。等待时取消会注销请求；之后的旧回复返回 False。AskUser 走相同请求/回复结构，但回复内容是 `{问题name: 答案}`。

低层 `Agent.run()` 需要显式 `interaction=Interaction()` 才允许交互。TUI/CLI 推荐调用服务，避免直接管理权限对象。`PermissionResponse` 仍可从 agent 模块导入，`PermissionRequest.future` 已被移除。

### 5. 取消不等于撤销

`RunHandle.cancel()` 请求停止并等待 worker 收尾。仍有效的订阅先获得 `LoopComplete(status="cancelled")`，随后 `events()` / `result()` 抛出 `CancelledError`。提前关闭消费者应配合 `async with run` 或 `aclosing(run.events())`，让 Python 明确执行 finally，不能仅丢弃一个未关闭的生成器。

WSL/POSIX 的 Bash 会结束进程组，模型流关闭；已经写入的文件仍可能存在。若一个批次部分工具完成、部分被取消，服务保留已观察的结果，为其余调用补“结果未知”的错误记录。恢复时应检查真实外部状态，不能假定失败意味着无副作用。

### 6. 会话恢复和持久任务恢复

`SessionManager.resume()` 读取 JSONL、找最近 compact boundary、过滤不完整工具尾部；`SessionService.resume()` 加载一次历史、重新绑定 FileHistory，必要时追加修复边界。`run_state` 记录成功/失败/取消用于审计，不是等待队列。

它不会重新启动进程、重建权限 Future 或自动重做工具。R5 的持久任务/调度仍未实现。服务只提供同进程会话独占和同会话一次运行；跨进程写入、外部副作用事务和重启恢复待授权操作均不支持。

环境、长期记忆封装、MCP 提示与召回用 `Message.transient` 标识，服务保存时排除；下一次召回替换上一条。用户输入、模型消息和工具结果按对象身份只保存一次。普通重复 resume 不向文件重复追加历史。

会话隔离还包括切换后的内存状态。`SessionService._bind_session()` 调用 `Agent.reset_session_context()` 清理工具发现、激活 Skills、文件缓存及压缩恢复状态，并更换工具结果子目录。保留 Runtime 的权限模式、工具启用配置和独立后台任务；恢复时保留磁盘会话的累计 token 基线。

### 7. 一个实际测试构造的失败案例

`tests/test_session_service.py::test_permission_cancel_emits_terminal_and_repairs_tool_chain` 用 fake 模型提出写入，在 PermissionRequest 到达后取消。断言工具执行次数为零、旧回复无效、请求数归零、终止状态为 cancelled；恢复后的工具调用与错误结果对应，JSONL 不是 completed。

这是构造测试，不是真实模型事故。开发过程中实际遇到的回归是：初版完整结果适配在看到 failed 终止事件时提前抛出通用 RuntimeError，覆盖了模型原异常。修复为先消费完共同事件流，再处理正常结束的失败状态，保留模型原异常；原 `test_document_headless` 失败清理断言没有被削弱。

实际 TUI 测试还发现旧 AskUser 的等待环、富文本解析和答案标识问题。`tests/test_entry_service.py` 现在通过 Textual 测试环境实际键入 `yes` 并确认，验证工具收到 `answer: yes`。这不等于真实桌面 GUI 验收。

### 8. 五个面试问题与参考回答

1. **为什么不让 run_to_completion 再实现一个 while 循环？** 两份模型/工具循环会发生行为漂移。当前它消费 `Agent.run()`，通过终止事件取答案；上下文、Hook、工具和失败处理只有 `_run_loop()` 一份。
2. **为什么不能把 Future 放进服务事件给界面？** Future 绑定事件循环，无法作为普通消息序列化，且界面可能越过关联校验直接授权。当前 Future 留在 Interaction 内，外部使用一次性的 run_id/request_id 回复。
3. **怎样保证同一个输入不会保存两次？** 入口只提交字符串；`SessionService._execute()` 追加，`_flush()` 记住已保存消息身份并排除 transient。TUI 不再自己 append；普通 resume 标记已有历史为已保存。
4. **CancelledError 和工具错误为何不能一视同仁？** 工具错误可以回填给模型继续推理；取消表示整个运行终止。服务先清理请求和修复记录，再对结果调用者传播 CancelledError；不使用正常答案掩盖取消。
5. **为什么 Runtime 与服务不能都关闭 MCP/Hook？** 重复关闭会破坏异步资源上下文。RuntimeExtensions 独占 MCP 任务，连接与退出在同一协程；借入 Hook 归入口，自建 Hook 归扩展，构造时拒绝同时接管。

### 9. 两个可亲手运行的实验

先在 WSL 进入开发目录并激活用户指定环境：

```bash
source /home/ldj/anaconda3/etc/profile.d/conda.sh
conda activate cc
cd /mnt/d/ldj/03/DeskMate
```

**实验一：同一个假模型，批准和拒绝会改变什么？**

```bash
python -m examples.deskmate_session --decision allow
python -m examples.deskmate_session --decision deny
```

观察 PermissionRequest 与 ToolResultEvent。批准打印 `file_created=True`，拒绝为 False；二者最终均可 completed，因为工具拒绝是可恢复错误。两次都打印 `user_input_count=1`、`repeated_resume_unchanged=True`。演示使用 fake client、临时 HOME/工作区，不读取真实 Key；退出会删除临时目录。

**实验二：在权限等待时取消，再恢复会话。**

```bash
python -m examples.deskmate_session --decision cancel
PYTHONUTF8=1 python -m pytest -q -o cache_dir=/tmp/deskmate-r2-pytest-cache \
  tests/test_session_service.py::test_permission_cancel_emits_terminal_and_repairs_tool_chain
```

观察 cancelled 终止事件、取消传播提示、文件不存在和重复恢复不变。打开对应测试查看 run_state、工具关联 ID 和旧回复 False 的断言。若要观察原语控制流，再看 `tests/test_execution_contract.py::test_permission_wait_cancellation_invalidates_request`；这些都是离线构造案例，不能推断真实模型效果或性能。

### 10. R3 调用者的最小约定

```python
# runtime 已 initialize；service 已按需要启用 persistent/memory。
try:
    async with service.start("用户输入", interactive=True) as run:
        async for envelope in run.events():
            data = envelope.to_dict()  # 交给展示适配器
            # 收到权限/问答事件后，由外部提交 run.reply(...)
    answer = await run.result()
finally:
    await runtime.aclose()
```

不要从两个窗口同时调用同一个服务；重叠请求会被拒绝。桌面入口需要选择自己的线程与事件消费策略，及时消费单订阅队列；当前没有网络协议、跨线程投递、持久权限队列或自动重试副作用。
