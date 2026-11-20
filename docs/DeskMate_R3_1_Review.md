# DeskMate R3.1 源码审查与 R4 推进结论

> 审查日期：2026-11-18\
> 审查版本：`19e5d6d74c8413b71088e4dea3be538da3b05151`\
> 对比版本：R3 `b1d44a1ae6e09f009ac01260712a5dc508e0fd7b`\
> 目标依据：`DeskMate_Target_Spec.md`（建议在项目中保存为 `docs/deskmate-target-spec.md`）。

## 1. 结论

**可以进入 R4。建议先在同一轮完成一个小范围 R4-0 收尾，再实现指定网页与本地资料整理。**

R3.1 的交互超时展示、launch 异常收尾和慢关闭提示优先级修复已经落到代码，现有 Runtime、SessionService、统一 Agent Loop 和桌面后台控制器可以继续复用。

本次独立复测得到 **821 passed，0 failed，0 skipped**；独立 SubAgent 脚本 **90/90**。另通过实际 Qt 和后台服务的定向故障检查确认了三个局部问题：发送被拒绝后丢失草稿、单槽命令回执可能覆盖前一条结果，以及旧演示工作区清理异常后卡在 `starting`。这些属于下一轮开头可局部修复的可靠性问题，不需要推翻桌面架构。

R4 的产品目标固定为：

> 用户给出少量明确的公开网页 URL 和工作区内的文本 / Markdown 材料，DeskMate 调用工具读取、整理，在既有权限机制下生成带来源的 Markdown 文件，并依据实际文件回读反馈结果。

## 2. 版本与改动范围核对

| 项目 | 本次核验结果 |
| --- | --- |
| ZIP 名称 | `likecc-19e5d6d74c8413b71088e4dea3be538da3b05151.zip` |
| ZIP 注释中的 SHA | 与上述 R3.1 SHA 一致 |
| ZIP 内容与远程固定提交 | 对 202 个文件逐一进行字节比较，全部一致；无缺失、额外或内容不一致的文件 |
| ZIP SHA-256 | `2266ab057aa99ccc0fdf1a254d8b38cdcdeee381dfcda0473a03a1df51cc0202` |
| 相对 R3 的 Git 差异 | 13 个文件，新增 1661 行、删除 52 行（以 `git diff --stat` 为准） |
| 生产代码范围 | `likecc/desktop/application.py`、`controller.py`、`window.py` |
| 其余改动 | 6 个测试文件、4 份文档 |
| 依赖 | `pyproject.toml` 和 `uv.lock` 没有相对 R3 改动 |

本次只读取远程固定提交，并在隔离审查副本中测试，没有向 GitHub 提交或推送，也没有访问或修改用户的本地 `D:\ldj\03\DeskMate` 或原 `likecc` 目录。

源码入口：[R3.1 固定提交](https://github.com/KNIGHT15235/likecc/tree/19e5d6d74c8413b71088e4dea3be538da3b05151)。

## 3. 本次独立执行的验证

### 3.1 环境与结果

审查环境是 Linux、Python 3.12.14。使用上传版本的 `uv.lock` 在独立虚拟环境安装 desktop extra 和测试依赖，PySide6 为 6.8.3。Qt 使用 offscreen；没有真实模型调用、真实桌面托盘操作或 Windows 人工操作。

| 检查 | 实际结果 | 说明 |
| --- | --- | --- |
| 完整 pytest | 821 passed，0 failed，0 skipped，36.35 秒 | 全量测试，未删减断言或跳过失败项；耗时不是性能提升指标 |
| `tests/verify_subagent.py` | 90/90 | 离线组件脚本 |
| `python -m likecc --help` | 退出 0 | 原 CLI 入口 |
| `python -m likecc.desktop --help` | 退出 0 | 桌面入口 |
| 实际 Interaction / Bash 定向检查 | 9 项通过 | 含关联回复、超时、取消、关闭、并发工作目录和 POSIX 管道回收 |
| 实际 Qt / DesktopController / Runtime / SessionService 定向检查 | 三项局部问题均复现 | 使用离线 DemoClient 和可控故障条件；测试自行关闭所有后台线程 |

“全部 pytest 通过”与“发现未覆盖问题”可以同时成立：新增定向检查覆盖了原测试尚未覆盖的边界。

### 3.2 首轮失败及处理方式

第一次完整执行为 **817 passed、4 failed、1 warning**，没有直接忽略失败。

- 一项权限测试把源码文件作为工作区外目标。本审查环境的 `TMPDIR` 恰好是整个会话工作区，而现有 `PathSandbox` 默认允许系统临时目录，导致源码也落在允许范围内。复测为测试子进程设置了不包含源码的独立临时目录。
- 三项真实 SDK 关闭测试只创建、关闭客户端，不发起模型请求。审查环境预设 SOCKS 代理，锁定依赖不含可选 `socksio`，因此在客户端初始化时失败。复测仅在离线测试子进程中移除代理环境变量，没有修改全局代理、锁定依赖或业务代码。

上述环境隔离完成后重新执行完整套件，得到 821 passed。真实服务网络连接与用户平台验收不由这次离线测试替代。

复测使用的关键设置：

```text
Python 3.12.14，上传版本 uv.lock，PySide6 6.8.3
PYTHONUTF8=1
PYTHONNOUSERSITE=1
PYTHONDONTWRITEBYTECODE=1
QT_QPA_PLATFORM=offscreen
TMPDIR=独立审查临时目录（不包含源码）
pytest 使用独立 --basetemp 和 cache_dir
离线测试子进程不继承模型密钥和代理环境变量

python -m pytest -q -rs --tb=short --basetemp <独立目录> -o cache_dir=<独立缓存>
python tests/verify_subagent.py
python -m likecc --help
python -m likecc.desktop --help
```

## 4. R3.1 已落实的修复

### 4.1 超时后不再留下空的等待状态

`DesktopController._event()` 按 session / run / tool 关联清除待处理交互。只有当前仍有活动运行、没有剩余请求、展示状态为 waiting 且应用未关闭时，才恢复 running；不会覆盖 cancelling / closing。

依据：[controller.py](https://github.com/KNIGHT15235/likecc/blob/19e5d6d74c8413b71088e4dea3be538da3b05151/likecc/desktop/controller.py)，重点为 335–347 行；[超时回归测试](https://github.com/KNIGHT15235/likecc/blob/19e5d6d74c8413b71088e4dea3be538da3b05151/tests/test_desktop_wait_state.py)。

### 4.2 异常启动或 Qt 退出也有后台回收兜底

`launch()` 的 finally 覆盖生命周期对象构造、信号处理器注册和 Qt 事件循环，使用公开关闭接口回收后台线程，并保留原异常。有限等待只用于 Qt 循环尚未开始或已经结束后的兜底；正常 GUI 退出仍异步等待。

依据：[application.py](https://github.com/KNIGHT15235/likecc/blob/19e5d6d74c8413b71088e4dea3be538da3b05151/likecc/desktop/application.py)，重点为 195–255 行；[launch 回归测试](https://github.com/KNIGHT15235/likecc/blob/19e5d6d74c8413b71088e4dea3be538da3b05151/tests/test_desktop_launch.py)。

### 4.3 慢关闭提示不会被迟到确认覆盖

关闭阶段由应用级状态拥有提示优先级；命令回执和托盘消失仍被处理，但不覆盖资源尚在清理的警告。对应测试通过受控时序验证，而非依赖偶然刷新时机。

依据：[window.py](https://github.com/KNIGHT15235/likecc/blob/19e5d6d74c8413b71088e4dea3be538da3b05151/likecc/desktop/window.py)，重点为 144–149 行；[生命周期测试](https://github.com/KNIGHT15235/likecc/blob/19e5d6d74c8413b71088e4dea3be538da3b05151/tests/test_desktop_lifecycle.py)。

## 5. 建议放入 R4-0 的三个局部问题

### 5.1 被后台拒绝的发送仍清空输入草稿（P2）

`ChatWindow.send()` 在提交命令后立即清空输入框，尚未确认后台是否接受。GUI 使用定时快照，快照与真实后台状态之间存在时间差；后台拒绝后，文本既不在输入框，也没有成为本次用户消息。

实际 Qt 定向复现：保持旧 idle 快照、后台进入活动状态，再通过真实按钮信号发送。后台拒绝，但 `QPlainTextEdit` 已为空。为确定性复现暂停了 GUI 轮询，不代表用户每次点击都会触发。

建议：按 command_id 关联草稿与接受结果，防止重复发送；接受后只清除对应提交版本，拒绝时保留原稿，不覆盖用户后来输入的新文本。

依据：`window.py` 93–97 行，`controller.py` 261–263、272–300 行。

### 5.2 单槽回执可能覆盖较早命令结果（P2）

`snapshot.command` 只保存最后一条回执。两条命令在一次 GUI 刷新前结束时，前一条结果无法从公开快照消费。

实际控制器复现：运行中连续提交 new / resume，两条都被拒绝，快照只留下第二条 ACK。没有证据说明它导致重复执行；确认的问题是回执丢失。

建议与草稿问题一起修复：提供按 command_id 可消费、容量有界的回执机制，或完整且明确的在途命令协议。不要只在现有单槽之上增加“等待 ACK 再清空”，否则会引入等待不到确认的状态。取消、权限回复和关闭不能被普通提交阻塞。

依据：`controller.py` 47–50、226–230、298–300 行，`window.py` 144–152 行。

### 5.3 旧工作区清理失败可能留下 starting 状态（P2，故障注入）

`_open()` 在进入 try 前调用 `_release()`。对旧演示临时目录的 cleanup 注入 `PermissionError` 后，旧 Runtime 与会话资源已经关闭，但切换命令被拒绝，状态保持 starting；再次进入演示仍被状态检查拒绝。

这是一条实际类故障注入验证的错误路径，不能写成用户当前已经发生的人工验收失败。默认 Runtime 对常规关闭异常另有日志和后续回收逻辑，也不能泛化为所有关闭错误都会触发。

建议：把旧资源释放纳入切换错误处理，进入明确的可恢复状态，保留未完成清理对象以便重试；仍有未关闭资源时，不得伪装为新工作区已就绪。

依据：`controller.py` 165–180、220–224 行。

## 6. 用户平台验收记录应如何理解

以下依据上传源码中的 [verification.md](https://github.com/KNIGHT15235/likecc/blob/19e5d6d74c8413b71088e4dea3be538da3b05151/docs/verification.md) 和 [桌面说明](https://github.com/KNIGHT15235/likecc/blob/19e5d6d74c8413b71088e4dea3be538da3b05151/docs/deskmate-desktop.md)，不是本次审查者亲自执行的 Windows / 真实模型结果。

- WSLg 无托盘离线人工流程：用户逐项确认通过。
- DeepSeek 指定真实任务：读取公开样例、审批写入、实际文件核查、继续对话、退出重开与恢复展示已记录通过；恢复后再发起新的模型任务不在该次证据范围。
- Windows Conda 离线真实托盘：启动、隐藏、恢复、运行中隐藏、托盘取消、继续交互和退出已记录通过。
- Windows 最后完整回归：815 passed、0 failed、6 skipped。五项跳过依赖 POSIX 进程组，一项依赖本机缺少的符号链接测试目标。
- 文档中的 WSL 821 passed 是关闭提示修复阶段的完整回归；后续 Shell 测试适配阶段记录的是 92 项相关回归。本次审查则已针对上传的最终源码重新跑出 Linux 821 passed。

### Windows Shell 的准确边界

R3.1 调整的是测试输入：Windows 用 `cd` 代替 POSIX 的 `pwd`，按目标 Shell 构造 Python 参数。生产 `Bash` 仍调用 `asyncio.create_subprocess_shell()`；POSIX 回收自有进程组，Windows 分支仅 kill 当前 shell。

因此，选定原生文件流程通过，不等于通用 Windows 子进程树清理、所有 POSIX 命令兼容或安装分发已完成。R4 采用专用文件与网页工具即可推进，不需要先扩大到这些平台工程。

## 7. R4 必须补充的能力

### 7.1 专用网页读取工具

当前默认注册表只有文件、目录搜索和 Bash 等基础工具，没有原生网页抓取或互联网搜索。`ToolSearch` 是工具发现，不是搜索引擎。

R4 增加一个异步、可取消的指定 URL 读取工具，优先复用已有 `httpx`。支持静态 HTML、纯文本和 Markdown；保留实际来源及失败 / 截断信息。对网络协议、目标地址、重定向、响应大小和超时给出明确策略。

依据：[工具注册](https://github.com/KNIGHT15235/likecc/blob/19e5d6d74c8413b71088e4dea3be538da3b05151/likecc/tools/__init__.py)、[工具基类](https://github.com/KNIGHT15235/likecc/blob/19e5d6d74c8413b71088e4dea3be538da3b05151/likecc/tools/base.py)。

### 7.2 桌面个人事务身份与工具范围

当前桌面仍复用编程助手提示。应在现有提示构造与显式装配中加入个人事务配置，保留原 CLI / TUI 的编程用途以及共同的权限、上下文与事件契约。

本轮资料流程使用文件和网页工具；默认不依赖 Bash、浏览器自动点击或外部 MCP。网页及本地文档中的内容作为资料处理，不提升其中嵌入指令的权限。

依据：[prompts.py](https://github.com/KNIGHT15235/likecc/blob/19e5d6d74c8413b71088e4dea3be538da3b05151/likecc/prompts.py)。

### 7.3 来源与成果验证

先支持工作区内 UTF-8 文本 / Markdown 和明确 URL，输出 Markdown。记录实际读取的来源，区分成功、失败和截断；最终文件附来源说明。

“生成成功”应依据实际写入和回读，不仅依赖模型说完成。利用现有工具和服务实现，不另建执行循环或庞大的通用验证框架。

### 7.4 权限与支持范围应与实现一致

现有 `PathSandbox` 默认允许工作区和整个系统临时目录；Bash 不走这层文件路径检查。新增 URL 工具也不会自动获得网络地址权限策略。R4 必须明确桌面资料模式的文件根与网络访问策略，避免仅靠提示词约束。

这是新增资料能力需要落实的边界，不是声称当前尚不存在的网页工具已经发生漏洞。网络检查的实际保证需要如实描述，尤其不能把一次 DNS 检查写成完整的 DNS 重绑定防护。

依据：[sandbox.py](https://github.com/KNIGHT15235/likecc/blob/19e5d6d74c8413b71088e4dea3be538da3b05151/likecc/permissions/sandbox.py)、[checker.py](https://github.com/KNIGHT15235/likecc/blob/19e5d6d74c8413b71088e4dea3be538da3b05151/likecc/permissions/checker.py)、[rules.py](https://github.com/KNIGHT15235/likecc/blob/19e5d6d74c8413b71088e4dea3be538da3b05151/likecc/permissions/rules.py)。

## 8. 建议的下一轮检查点

| 检查点 | 目标 |
| --- | --- |
| R4-0 | 修复草稿 / 命令回执及切换清理错误，更新 README 过时状态，确认个人事务装配方案 |
| R4-A | 指定网页读取、网络与文件边界、来源数据和离线测试 |
| R4-B | 桌面个人事务配置、真实文件生成与回读、最小成果展示 |
| R4-C | 真实 Provider / 桌面人工验收、回归、学习与验证文档 |

README 第 113 行仍称统一内核和桌面未实现，与开头矛盾；第 24 行的 Bash 依赖描述也应按实际 Shell 行为校正。仅更新当前说明，历史验证记录保留其原时点含义。

R4 不开发持久调度（R5）、记忆模型升级（R6）或主动提醒系统（R7），也不扩展到飞书、通用 GUI 自动操作、DAG 多 Agent 或经验治理。下一轮提示词见配套 `DeskMate_R4_Codex_Prompt.md`。
