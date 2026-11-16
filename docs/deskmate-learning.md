# DeskMate R1 学习记录

本文记录本轮代码结构和可复现行为，不代写个人学习体会。路线与验证入口：[roadmap](deskmate-roadmap.md)、[verification](verification.md)。

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
