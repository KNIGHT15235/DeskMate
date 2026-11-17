# DeskMate 桌面入口（R3）

## 安装与启动

在可显示 Qt 窗口的 Python 3.11+ 环境、仓库根目录执行：

```bash
uv sync --locked --extra desktop
uv run --locked --extra desktop python -m likecc.desktop --demo
```

本机指定的 Conda 环境已经安装依赖，可直接运行：

```bash
source /home/ldj/anaconda3/etc/profile.d/conda.sh
conda activate cc
cd /mnt/d/ldj/03/DeskMate
python -m likecc.desktop --demo
python -m likecc.desktop --work-dir /mnt/d/ldj/03/DeskMate --provider your-provider-name
```

第二条是真实模式，必须先准备现有 LikeCC 配置。`--provider` 可省略，取合并后配置中的首个 Provider。显式工作区按用户配置→该项目 `.likecc/config.yaml`→该项目 `.likecc/config.local.yaml` 加载，保持原字段合并规则，不改变进程 cwd。界面在发送前显示工作区与模型，不展示 Key；无效配置可改路径重试，或进入离线演示。

可选开关：`--skills --mcp --hooks --memory --summaries`，默认全部关闭；演示无论传哪些开关都保持关闭。权限固定为现有 `default`，没有默认 bypass 或永久授权按钮。本轮不提供权限模式编辑器。真实模式的用户数据路径仍为 `~/.likecc`，项目会话仍在工作区 `.likecc/sessions`。

desktop extra 锁定 PySide6 6.8.3 及三个 Qt 配套包，未升级原依赖版本。没有安装 extra 时原 CLI/core 可用，桌面启动提供安装说明，`--help` 无需 Qt。

## 界面与操作

- 输入后点击发送，查看文本、工具参数、结果以及成功/失败/取消状态。工具失败可恢复，运行失败单独标记。文本按纯文本转义，不打开链接、执行输出或加载远程图片。
- 权限卡片可“本次允许”“拒绝”或“取消运行”。问答支持 text、radio、select、checkbox，按 schema 的 name 返回；不支持的类型明确诊断并取消，避免悬挂。
- 回复以后台确认结果为准。过期、重复、旧会话/旧运行的回复被拒绝。工具完成、超时或运行终止后卡片清理。
- 空闲时新建或恢复会话；运行/启动/取消/关闭中拒绝重复发送及切换会话、工作区或 Provider。恢复只加载历史，不重做工具。
- 工作区/Provider 变更先关闭旧 Runtime，再创建新实例。API Key 不在界面编辑，继续使用现有配置。
- 委派、团队、Worktree 与计划模式工具没有在桌面注册或被显式禁用，避免无人消费的子任务或外部终端后端；原 TUI/CLI 的独立工具表不受影响。

## 隐藏、取消与退出

应用检测实际 `QSystemTrayIcon.isSystemTrayAvailable()`：有托盘时关闭窗口隐藏，首次给出提示；菜单含显示、取消、退出。控制器继续消费同一事件流，重新显示不重订阅。隐藏时新权限/问答有待处理标记和一次基础提示，不自动批准。

没有托盘时关闭会询问“最小化 / 退出应用 / 取消关闭”，不会隐藏成无法找回的进程。托盘在运行中消失会恢复窗口。最小化仍可从桌面任务栏找回。

“取消当前请求”只取消本次运行，可以继续下一次输入；“退出应用”进入 closing，拒绝新命令，在后台调用 Runtime.aclose()，等运行、扩展和 client 关闭，工作线程和 asyncio loop 结束后才退出 Qt。重复退出安全。清理超过 15 秒时显示仍在等待，不强退线程、不丢弃资源。

本版本只承诺进程存活期间继续执行。关机、休眠、程序退出后恢复执行、持久权限队列及副作用回滚均未实现。POSIX 只清理 Bash 自己的新进程组；主动脱离该组的程序和 Windows 完整进程树回收不在本轮验证保证内。

## 演示与人工验收

`--demo` 走相同控制器、SessionService 和 Agent 内核，用注入的 fake client 替换模型。工作区与用户根在独立临时目录，不修改 Path.home、不读取真实规则/记忆/配置、不启动扩展或模型元数据查询；退出后清理。界面显著标为离线演示。

1. 发送任务：先拒绝写入，确认无文件；新建会话重试并批准，确认临时工作区出现 demo.txt。问答选择“完成”，检查最终回答只显示一次。
2. 问答选择“等待取消”，在有托盘环境关闭窗口，再从托盘恢复；应保留同一运行。点击取消，检查可再次发送。恢复旧会话不重写文件。
3. 隐藏后等待权限提示，确认无自动授权。退出时应完成资源关闭，不留本应用线程/进程。无托盘环境分别尝试取消关闭、最小化、退出。

本轮已实测 WSLg Wayland 窗口显示、权限卡片与正常资源退出；实际托盘检测为 False。offscreen 自动化覆盖控件操作与模拟的托盘存在/消失策略，不能代替真实托盘人工验收。原生 Windows Python、Windows 托盘、真实模型、外部 MCP/Hook 和安装包尚未验证。截图/测试证据见 verification 的 R3 节。

本实现依据 [Qt 托盘 API](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QSystemTrayIcon.html) 的运行时能力检测；Qt 可选依赖安装参考 [Qt for Python 入门文档](https://doc.qt.io/qtforpython-6/gettingstarted.html)。未使用额外的 Qt/asyncio 整合框架。
