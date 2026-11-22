# DeskMate 桌面入口（R3–R5）

R5 增加“任务与执行记录”窗口。聊天中的明确安排先解析为预览，也可用表单创建/修改一次性或每周任务。确认本地时间、时区及材料/输出范围后保存；模型调用授权独立选择，网页与写入继续使用 R4 卡片。后台到期调度不依赖窗口可见性；真正退出停止领取，重开保留提醒、历史和中断线索。[操作、存储位置、恢复策略与三条验收流程](deskmate-schedules.md)。

定时资料任务使用独立持久会话，前台忙时排队；运行期间暂时展示该次执行，结束后恢复原聊天和草稿。历史详情区分运行结束、实际写入和回读核对。退出期间错过的提醒标为逾期，周期只合并最近一次，中断写入不自动重放。首版时区为 Asia/Shanghai 和 UTC，同工作区只允许一个活动调度器。2026-11-22 已完成 Windows 提醒、周期定义/到期待确认/取消、重启逾期与第二实例阻止的可见检查；真实 DeepSeek 的前台问题卡片、周期排队/接续、权限等待取消、批准写入/回读、历史、原聊天/草稿恢复及成果重启保留已有证据。用户误取消后选择跳过拒绝案例补做，该真实案例保持未完成；不沿用 R4 人工结果冒充 R5 证据。

R4 起，正常桌面入口使用[资料整理模式](deskmate-affairs.md)。输入框接受用户明确提供的公开 URL、工作区 UTF-8 文本/Markdown 和期望的 Markdown 路径。来源与成果面板显示本次实际工具结果。只有 ReadFile 回读与写入摘要一致时才显示「已回读核对」，生成回答或运行完成会单独展示。取消、托盘、恢复历史和旧 `--demo` 沿用原入口。

资料模式提供 ReadFile、WriteFile、FetchWebPage 与交互工具。公网读取默认按 URL 确认，覆盖前需要读取现有目标文件。隐藏窗口仍由后台继续消费事件。恢复历史只展示既有工具记录，下一任务从空的来源/成果摘要开始，不重新抓取或写入。独立离线示例可用 `python -m examples.deskmate_materials`。

R4 验收截至 2026-11-20 已完成真实 DeepSeek 资料整理、两次网页审批、写入及回读、权限等待时取消、同会话重用和退出恢复。样例文件与恢复前快照均已核对。批准访问后的那次取消尝试对应运行已完成，实网 HTTP 流内取消和实网重定向保留为未覆盖项。[验收记录](verification.md#r4-收尾结论与覆盖边界)

截至 2026-11-18，WSLg 离线人工流程、DeepSeek 指定真实任务、Windows Conda deskmate-win 离线真实托盘清单均已通过。Windows 防联网测试和关闭耗时提示竞态已修复，两个 Conda 环境的桌面专项均通过。各阶段过程保留在下文，完整回归结果见文末验收汇总。

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

“取消当前请求”只取消本次运行，可以继续下一次输入；“退出应用”进入 closing，拒绝新命令，在后台调用 Runtime.aclose()，等运行、扩展和 client 关闭，工作线程和 asyncio loop 结束后才退出 Qt。重复退出安全。清理超过 15 秒时恢复窗口并显示等待提示。关闭期间，迟到的命令确认和托盘变更不会覆盖关闭提示。

本版本只承诺进程存活期间继续执行。关机、休眠、程序退出后恢复执行、持久权限队列及副作用回滚均未实现。POSIX 只清理 Bash 自己的新进程组；主动脱离该组的程序和 Windows 完整进程树回收不在本轮验证保证内。

## 演示与人工验收

`--demo` 走相同控制器、SessionService 和 Agent 内核，用注入的 fake client 替换模型。工作区与用户根在独立临时目录，不修改 Path.home、不读取真实规则/记忆/配置、不启动扩展或模型元数据查询；退出后清理。界面显著标为离线演示。

1. 发送任务：先拒绝写入，确认无文件；新建会话重试并批准，确认临时工作区出现 demo.txt。问答选择“完成”，检查最终回答只显示一次。
2. 问答选择“等待取消”，在有托盘环境关闭窗口，再从托盘恢复；应保留同一运行。点击取消，检查可再次发送。恢复旧会话不重写文件。
3. 隐藏后等待权限提示，确认无自动授权。退出时应完成资源关闭，不留本应用线程/进程。无托盘环境分别尝试取消关闭、最小化、退出。

R3 阶段已实测 WSLg Wayland 窗口显示、权限卡片与正常资源退出，当时实际托盘检测为 False。该阶段使用 offscreen 和模拟托盘验证策略。R3.1 后续补充了真实 Provider 和 Windows 原生托盘人工验收，结果见本文后续章节。外部 MCP/Hook 集成与 DeskMate 安装包仍待验证。

本实现依据 [Qt 托盘 API](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QSystemTrayIcon.html) 的运行时能力检测；Qt 可选依赖安装参考 [Qt for Python 入门文档](https://doc.qt.io/qtforpython-6/gettingstarted.html)。未使用额外的 Qt/asyncio 整合框架。

## R3.1 可见窗口人工验收清单

R3.1 已修复交互超时展示与 launch 异常收尾。2026-11-17 用户在 WSLg 可见窗口中按下表逐项操作并反馈通过，超时结束及超时后再次运行另有用户截图。以下“通过”指用户执行确认，与此前程序化启动观察和 offscreen 自动化分别记录。该离线阶段没有真实模型调用，该 WSLg 会话实际托盘不可用。

### 1. 独立的可见窗口启动命令

在 **WSL 的 Bash 终端**执行。先激活指定环境，显示服务应已有 DISPLAY/WAYLAND_DISPLAY；不要安装完整桌面或改系统显示配置。

```bash
source /home/ldj/anaconda3/etc/profile.d/conda.sh
conda activate cc
cd /mnt/d/ldj/03/DeskMate
printf 'DISPLAY=%s WAYLAND_DISPLAY=%s\n' "${DISPLAY:-未设置}" "${WAYLAND_DISPLAY:-未设置}"

# 仅当继承了测试平台时，在本次子进程命令中移除，不改变当前/全局环境。
r31_python=(python)
case "${QT_QPA_PLATFORM:-}" in
  offscreen|offscreen:*|minimal|minimal:*) r31_python=(env -u QT_QPA_PLATFORM python) ;;
esac
"${r31_python[@]}" -m likecc.desktop --demo &
r31_app_pid=$!
printf '本次演示进程 PID=%s\n' "$r31_app_pid"
```

不强制指定 xcb/wayland，让当前 WSLg 正常选择平台。若两个显示变量都没有或启动失败，记录“可见窗口环境未就绪”，不要用 offscreen 代替。自动化命令单独使用 QT_QPA_PLATFORM=offscreen，不能拿它人工验收。

### 2. 按顺序操作与检查

| 项目 | 操作与预期 | 本轮人工状态 |
| --- | --- | --- |
| 启动 | 标题区为“离线演示 · 无模型网络请求”，工作区为 `/tmp/deskmate-desktop-.../workspace`，模型为 fake | 通过（用户确认，超时演示截图也显示 fake） |
| 拒绝首次写入 | 发送任意无隐私测试文字，WriteFile 卡片点击“拒绝”；工具错误可恢复，demo.txt 不存在 | 通过（用户确认工作区存在且文件未创建） |
| 批准写入 | 问答选择“完成”后新建会话，再发送一次并点击“本次允许”；demo.txt 内容为 `DeskMate R3 demo` | 通过（用户确认实际文件内容） |
| 问答与最终回答 | 输入一个无隐私备注，选择“完成”；显示正确 name 对应答案，最终回答只出现一次 | 通过（用户确认字段正确、最终回答一次、回到就绪） |
| 取消后继续 | 再发一次，拒绝写入，问答选择“等待取消”；出现 DemoWait 后取消，状态回到就绪，能再发送并完成一轮 | 通过（用户确认取消后无卡片，新任务正常完成） |
| 新建/恢复 | 空闲时新建，再恢复先前会话；只显示记录，不产生新授权/问答，也不再次写文件 | 通过（用户确认会话与历史正确，无新卡片，文件哈希、修改时间和大小均未变化） |
| 无托盘降级 | 关闭窗口分别选择“取消关闭”“最小化”“退出应用”；前两项仍可找回窗口，最后一项完成清理后结束进程 | 通过（用户分别确认三条路径） |
| 超时展示 | 按下一节短超时命令重启，不回复；卡片清理后不能停在没有请求的“等待回复” | 通过（用户确认未写入、无卡片且输入可用；截图显示 completed，后续再次运行后为就绪） |
| 退出残留 | 只检查下面记录的本次 PID/线程，确认它们已经退出 | 通过（正常演示与短超时演示均由用户确认退出码 0、进程/线程退出、临时工作区清理） |

短超时演示使用 `DesktopOptions(demo=True, permission_timeout=5)`。用户完成一次自然超时后再次发送，新运行同样正常结束；截图可见问答超时、completed、顶部就绪且无待回复卡片。这里确认的是最终展示、再次发送和未写入；没有声称人工逐帧观察到了下一模型调用期间的 running 状态，该中间状态仍由屏障回归测试验证。详细证据来源见 [验证记录](verification.md) 的人工补记。

从窗口复制实际临时工作区路径到同一个终端（不要照抄占位字符串）：

```bash
r31_demo_dir='/tmp/从窗口复制实际路径/workspace'
# 拒绝首次写入后：同时检查工作区确实存在，避免因路径抄错而误判。
test -d "$r31_demo_dir" && test ! -e "$r31_demo_dir/demo.txt" && printf '拒绝后未创建文件\n'
# 批准后：
test -d "$r31_demo_dir" && test -f "$r31_demo_dir/demo.txt" && cat -- "$r31_demo_dir/demo.txt"
# 新建/恢复前后分别执行，比较内容 hash 和高精度修改时间应相同。
sha256sum -- "$r31_demo_dir/demo.txt"
stat -c '%y %s' -- "$r31_demo_dir/demo.txt"
```

新建会话不会删除工作区已有文件；拒绝测试的“文件不存在”只针对最初尚未批准过写入的阶段。恢复历史中显示的工具块不是新的执行证据，需结合无新卡片、文件时间和自动化调用次数断言判断。

运行中可从另一个终端只查看该 PID 的线程：

```bash
ps -T -p "$r31_app_pid" -o pid,tid,comm
```

通过 GUI 真正退出后，在启动它的终端执行：

```bash
wait "$r31_app_pid"
printf '退出码=%s\n' "$?"
if kill -0 "$r31_app_pid" 2>/dev/null; then
  printf '本次进程仍存在，请记录未完成清理\n'
  ps -T -p "$r31_app_pid" -o pid,tid,comm
else
  printf '本次进程及其线程已退出\n'
fi
```

这里 kill -0 仅探测存在性，不发送终止信号。不要使用 pkill/killall、扫描后批量结束所有 Python 或其他应用。demo 不启动外部子程序；退出后临时工作区也应不存在。

### 3. 缩短超时的人工观察（仍为离线演示）

先退出上一演示，保留前面同一终端中的 r31_python 命令数组，再执行：

```bash
"${r31_python[@]}" -c 'from likecc.desktop.application import launch; from likecc.desktop.controller import DesktopOptions; raise SystemExit(launch(DesktopOptions(demo=True, permission_timeout=5)))' &
r31_app_pid=$!
printf '本次短超时进程 PID=%s\n' "$r31_app_pid"
```

发送一次，不点击批准/拒绝：约 5 秒后权限超时，写入不能发生；随后新问答卡片可能正常显示“等待回复”，因为此时确实有待处理问题。问答也不回复，让其超时：最终应清除卡片并回到就绪，不能留下空的等待状态。再次发送及退出后按上面的 PID 检查。

离线模型通常快速完成，人工不一定能看清中间 running 帧。下一模型调用被屏障阻塞时的 running 状态已由新增回归验证，不能仅凭这个快速演示就声称所有真实服务时序均已人工验证。

### 4. 证据如何保留

只保存 demo 的截图和无隐私摘要到被忽略的 `.r1-verification/`，不把真实 Key、个人聊天、目录内容或真实服务错误原文放入截图/Git。人工记录可写“通过/失败、对应步骤、脱敏现象”，未操作项目保持待确认。程序化窗口截图也不能把上表自动打勾。

## R3.1 真实 Provider 指定冒烟（已通过，2026-11-18 收尾）

验收由用户在真实 WSLg 窗口中逐项发送、批准并确认，Codex 自动核对公开文件、会话记录、进程和配置元数据；没有自动点击或由工具发起未经授权的模型请求。Key 只在用户本机隐藏输入，不发送到聊天，不写入文件或命令历史。

### 本次实际配置与范围（2026-11-17）

| 项目 | 本次配置 |
| --- | --- |
| 环境 | WSL2 Ubuntu 24.04.4、Conda cc、Python 3.11.16、PySide6 6.8.3、Wayland |
| Provider / 模型 | DeepSeek，配置名 deepseek-r31，模型 deepseek-flash |
| 协议 / 服务器 | anthropic，https://api.deepseek.com/anthropic；这是 DeepSeek 的兼容接口 |
| 模型参数 | thinking=True、context_window=1000000、max_output_tokens=4096 |
| 工作区 | /tmp/deskmate-r31-provider-cdax32uf，仅含公开验收样例与本次会话 |
| 配置来源 | 验收项目级 .likecc/config.yaml，api_key 为空，文件权限 0600 |
| 凭据来源 | 用户终端隐藏输入，只传 GUI 子进程的 ANTHROPIC_API_KEY；不改全局凭据 |
| 权限 | 桌面原有 DEFAULT：读 allow、写 ask；验收项目仅增加 Bash(*) deny，不增加放行规则 |
| 扩展与临时根 | Skills/MCP/Hooks/memory/summaries 均关闭；GUI 的 TMPDIR 指向工作区 .tmp |

开始时标准位置没有配置，后续只在该验收目录建立空密钥配置。工作区外文件及 Bash 的静态探测为 deny，真实任务也没有越界或 Shell 工具记录；这不是操作系统级沙箱。没有修改权限模式来制造批准卡片。

选择 Anthropic 格式，是因为现有 AnthropicClient / build_anthropic_messages 保留思考与工具消息，符合 [DeepSeek 官方兼容说明](https://api-docs.deepseek.com/guides/anthropic_api/) 的多轮工具要求。只证明本次配置与任务通过，未验证其他模型/协议。官方 [模型与价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/) 已在调用前核对。

用户明确回复“同意本次单任务验收，不限制费用”，并在获知继续对话也会产生模型响应计费后手动执行检查。未自动叠加备选任务；现有 SDK 的重试可能增加请求，五条 assistant 记录不等于实际 API 请求总数。没有查询平台账单或声称实际扣费等于此前的价格示例。

### 已执行步骤与证据

| 检查 | 实际结果 |
| --- | --- |
| 真实启动 | 用户确认真实模式、就绪、Provider/模型和工作区正确 |
| 读取样例 | ReadFile(project_notes.md) 一次且成功，返回项目名称、R1–R3 和下一阶段的真实内容 |
| 文字确认 | 模型先给摘要草稿并用文字询问批准；当时没有 WriteFile、文件不存在，不是审批绕过 |
| 工具批准 | 继续同一任务后出现 WriteFile(summary.md) 卡片，用户点击本次允许 |
| 实际文件 | summary.md 为 257 字节，内容与源事实及写入参数一致；源文件哈希未变，WriteFile 一次且成功 |
| 继续对话 | DESKMATE_R31_CONTINUE_OK 恰好一次，无新工具或文件变化，再次就绪 |
| 退出与重开 | 第一次 wait 返回 0，进程消失；重新启动的新空白会话符合既有语义，原会话保留 |
| 恢复原会话 | 用户确认 session_20261117_231313_nnq5 的历史/编号正确，就绪且无卡片；文件哈希/mtime_ns/大小、工具计数和回复数均未变 |
| 最终退出 | 重启后的窗口也退出码 0，新 PID 消失，两文件和原会话保留，无工具重放 |

本次恢复后没有另发新的模型任务，恢复后思考模式续聊、其他 Provider 和长期稳定性仍待验证。Windows 原生离线托盘后续补充验收的结果见文末，DeskMate 安装包仍待验证。详细哈希、记录及阶段过程见 [verification.md](verification.md)。

### 本机使用的启动方式

用户在 WSL Bash 中执行了两次以下命令，启动后由用户决定何时发送任务：

```bash
cd /mnt/d/ldj/03/DeskMate
source /mnt/d/ldj/03/DeskMate/.r1-verification/r31_deepseek_launch.sh
```

该脚本为本机 Git 忽略目录的临时验收辅助文件，不是发布入口或克隆仓库保证存在的脚本。它激活 cc、复核配置和权限，再用 read -s 读取 Key；关闭命令跟踪，只为 GUI 子进程传入凭据/TMPDIR，移除可能继承的其他 Anthropic auth token；若继承 offscreen/minimal，只为本次启动移除。启动后清除局部 Key，保留 r31_app_pid 供同一父终端 wait 取退出码。Bash 与两段嵌入 Python 的语法检查已通过，实际运行由用户完成。

真实工作区由验收流程持有，应用退出只关闭运行时/会话资源，不删除文件；本轮保留了 project_notes.md、summary.md 和会话供检查。该 /tmp 路径只是临时验收数据位置，不保证跨系统清理或重启持久保存。下方为可复用检查方式及未执行的备选用例，不是本轮额外通过记录。

### 配置来源与隔离工作区

优先复用已有用户级 `~/.likecc/config.yaml`，在独立临时验收目录运行，避免在代码仓库做写入试验：

```bash
r31_accept_dir=$(mktemp -d /tmp/deskmate-r31-acceptance.XXXXXX)
printf 'DeskMate R3.1 acceptance\nPublic test data only.\n' > "$r31_accept_dir/sample.txt"
printf '验收工作区=%s\n' "$r31_accept_dir"
```

脱敏检查只输出配置层是否存在、Provider 名称/协议/模型；不输出 Key、base_url、配置原文或环境变量值，不创建模型 client、不请求服务：

```bash
python - "$r31_accept_dir" <<'PY'
import sys
from pathlib import Path
from likecc.config import load_config
workspace = Path(sys.argv[1]).resolve()
for label, path in [
    ('用户级 ~/.likecc/config.yaml', Path.home()/'.likecc/config.yaml'),
    ('验收项目级 .likecc/config.yaml', workspace/'.likecc/config.yaml'),
    ('验收本地覆盖 .likecc/config.local.yaml', workspace/'.likecc/config.local.yaml'),
]:
    print(label, '存在' if path.is_file() else '不存在')
try:
    config = load_config(work_dir=workspace)
except Exception as exc:
    print('配置尚未就绪，错误类别：', type(exc).__name__)
    raise SystemExit(1)
for provider in config.providers:
    print('Provider:', provider.name, '协议:', provider.protocol, '模型:', provider.model)
PY
```

若只有原项目配置、验收目录无法解析 Provider，先标为“待用户准备配置”，不要盲目复制含 Key 的 config.local.yaml。用户可自行准备仅含非秘密模型元数据、`api_key: ""` 并复用已有凭据环境来源的项目配置；若凭据只存在原文件而不在环境中，不由本轮脚本迁移或改写它。报告本次实际使用“用户级”或“验收工作区项目级/本地覆盖”，有覆盖时以既有用户→项目→本地顺序合并。

确认来源和 Provider 名称后启动（替换占位名称；保留前面可见平台的 r31_python 数组）：

```bash
"${r31_python[@]}" -m likecc.desktop --work-dir "$r31_accept_dir" --provider '已有Provider名称' &
r31_app_pid=$!
printf '真实模式 PID=%s\n' "$r31_app_pid"
```

**不要传 `--skills --mcp --hooks --memory --summaries`**：这些开关默认 False，此命令明确保持关闭。发送前检查窗口显示的工作区就是验收目录、Provider 正确且没有 demo 标识；没有在 GUI 编辑 Key。

### 备选的分步冒烟（尚未执行）

1. 输入：`只回复 DESKMATE_R31_OK，不调用工具。` 检查单次文本回答和正常结束。
2. 输入：`只读取工作区 sample.txt 并复述其中两行，不执行命令或其他工具。` 检查 ReadFile 的目标和公开样例结果。
3. 输入：`只尝试新建 denied.md，内容为 denied test；如果用户拒绝就停止，不要重试或换工具。不要执行 shell。` 在 WriteFile 卡片拒绝，确认 `$r31_accept_dir/denied.md` 不存在。
4. 输入：`只新建 acceptance-result.md，写三行 Markdown：# R3.1 acceptance、- sample read、- write approved。不执行命令或外部工具。` 核对目标后本次批准，检查该文件内容正确。

上述提示是验收约束，不是对模型行为的保证。出现 Bash、越界路径或额外任务请求时拒绝并取消；不要为了完成清单批准非预期动作。认证或配置失败只记录脱敏错误类别，立即停止，不截图 Key、响应头或私人配置。退出后按本次 PID 检查；保留公开样例文件供用户自行核验，不自动删除任何原项目资料。

当前状态：**DeepSeek 指定冒烟与两次退出清理全部通过**。以上结果来自用户实际操作与文件/记录核查，fake client 和 offscreen 均不能代替。备选四步未额外执行，未在真实模式另做拒绝写入试验；拒绝行为的用户证据来自前面的离线人工验收。

## 真实托盘与原生平台后续复验

本次实际 WSLg 探测仍为无托盘，不安装完整桌面、不伪造可用状态。待具备原生 Windows 或带系统托盘的真实 Linux 桌面后，逐项操作并确认：

1. 在该系统的原生 Python 环境安装锁定兼容依赖和 desktop extra，先用 `python -m likecc.desktop --demo` 启动，确认真实托盘图标出现；Windows 验证不得改为调用 WSL Python。
2. 关闭窗口，确认应用隐藏且进程仍存活；从托盘“显示 DeskMate”恢复。
3. 离线演示进入 DemoWait 后隐藏，再恢复，确认同一任务仍运行且历史存在；取消后可继续操作。此步骤不需要付费模型。
4. 从托盘选择“退出应用”，核对本次进程/线程及测试所启动子进程退出。不能把窗口消失单独作为清理证明，也不批量结束其他 Python。

以上流程制订时尚待实际平台确认，后续 Windows Conda 执行结果见文末。此前只读预检查发现 PATH 的 Python 为 `D:\anaconda3\python.exe`（3.12.7），当时未安装 PySide6。其余兼容性/交付检查范围如下。

| 范围 | 当前代码依据与后续检查 |
| --- | --- |
| Shell/POSIX 工具 | Bash 工具实际调用 `asyncio.create_subprocess_shell`，Windows 默认 shell 语义不同；检查命令、引号和 POSIX 外部工具，不假定 `bash.exe` 的 WSL 启动器等于原生 Bash |
| 路径与链接 | 检查盘符、反斜杠、大小写、空格/中文路径、symlink/junction 与沙箱真实路径；WSL 的 `/mnt/d` 结果不能作为 Windows 证据 |
| 子进程清理 | POSIX 使用独立会话与 `killpg`；Windows 分支只 kill 当前 shell，子进程树清理需独立验证，不能宣称等价 |
| Qt | 原生环境安装 PySide6 后检查窗口、实际托盘、信号与退出；本轮不自动安装或适配 |
| 配置和文件权限 | Windows `Path.home()` 与 WSL home 分离；验证配置来源、ACL、会话目录权限，不复制真实密钥来完成演示 |
| 分发与资源 | `pyproject.toml` 已声明 desktop extra 和 deskmate 入口，但尚未构建安装包；验证 Qt 插件/依赖、入口、动态绘制图标及包内资源（包括 TUI styles.tcss）在干净环境可用 |

这些是后续验证项，不表示发现项均已修复或原生环境已通过。

## R3.1 验收范围建议

WSL2/WSLg 的可见窗口与无托盘流程、DeepSeek 指定冒烟，以及 Windows Conda 离线真实托盘清单均已通过。后续关闭提示修复与 Windows 回归的具体范围见文末。R4 保持规划状态。

## Windows 原生离线托盘验收准备（2026-11-18）

用户随后授权准备独立 Windows 环境并逐步人工验收。上文“原生 Python 未装 PySide6、只读预检查”是此前阶段的记录；本节记录新的进展，不改变 WSLg 托盘 False 的结论。

- 原生 Windows 10 10.0.19045，基础解释器 `D:\anaconda3\python.exe` / Python 3.12.7。
- 新环境为 `D:\ldj\03\DeskMate\.venv-win-r31`，`include-system-site-packages=false`；直接调用其 `Scripts\python.exe`，无需激活或更改 PowerShell 执行策略。
- 用已有 uv 0.11.8 与 `uv.lock` 安装 desktop extra 和开发测试依赖，共 58 个包，PySide6/Qt 为 6.8.3。锁文件与 pyproject 的 SHA256 未变，WSL cc 和 Windows 基础环境均未安装或升级包。
- 独立环境及 `.r1-verification/` 下载缓存、测试日志均被现有 Git 忽略规则覆盖，不进入提交。
- 原生 Qt 探测实际返回 `platform=windows`、`tray_available=True`、`supports_messages=True`。这只表示具备托盘服务，图标、菜单和隐藏恢复仍需用户确认。

入口帮助、锁定环境一致性和包依赖检查通过。五个桌面测试文件实际为 **39 passed、2 failed、4 warnings**：两项失败来自测试对所有 `socket.connect` 的禁止，误拦 Windows asyncio 用来建立内部自唤醒管道的回环连接。已通过实际调用栈定位到 `_make_self_pipe → socket._fallback_socketpair → connect`。没有改弱测试、跳过失败或修改事件循环；独立原生 DemoController 初始化 idle、正常关闭和临时目录清理另行通过。详细命令见 verification，本阶段不宣称 Windows 自动化全绿或完整平台兼容。

第一步仅启动并观察，在 **Windows PowerShell** 中执行：

```powershell
Set-Location 'D:\ldj\03\DeskMate'
& '.\.venv-win-r31\Scripts\python.exe' -X utf8 -m likecc.desktop --demo
Write-Host "退出码=$LASTEXITCODE"
```

预期：窗口显示“离线演示 · 无模型网络请求”和“就绪”，模型 `offline-demo / fake`，工作区为 Windows 临时目录中的 `deskmate-desktop-...\workspace`；右下角通知区或“^”隐藏图标区出现蓝底白色 D，悬停提示 DeskMate 桌伴。第一步先不发消息、不关闭窗口，等用户确认后再测试关闭隐藏、托盘恢复、任务中隐藏与真正退出。最后一行在真正退出后才执行。

当前人工结果：**待用户启动并确认**。演示创建自己的临时 workspace/user 并注入 DemoClient，不读真实 Provider 配置，关闭 Skills/Hook/MCP/memory/summaries；本阶段没有模型调用或付费请求。后续每个操作单独确认，不能用本次 offscreen 测试替代真实图标和菜单验收。

## 当前 Windows 验收环境：Conda deskmate-win（2026-11-18）

用户随后指定改用 Windows Conda。已新建 `C:\Users\28436\.conda\envs\deskmate-win`，Python 3.12.7、PySide6/Qt 6.8.3。前节 `.venv-win-r31` 保留，其 58 个包版本与改用 Conda 前一致；WSL cc 和原 likecc 未改动。前节命令和结果保留为历史，本轮后续人工步骤使用本节命令。

安装采用 Conda 提供解释器、uv 从未变的 uv.lock 导出 desktop/dev requirements 后安装的方式；57 个生效的锁定第三方包均已校验版本，下载保留哈希校验。本地 likecc 另行 editable 安装，不重新解析业务依赖。没有用 uv sync 接管 Conda 环境或精确删除 Conda 自有包；新环境初始 packaging 26.3 按项目锁定要求调整为 26.2。Conda 的解释器、运行库、pip/setuptools/wheel 和 editable 构建工具不属于 uv.lock 的锁定范围。

环境/源码来源检查、61 个已安装包的依赖兼容检查、桌面 --help、离线控制器 idle/关闭/临时目录清理均通过。新环境实际 Windows Qt 探测为 `platform=windows, tray_available=True, supports_messages=True`。自动测试重新执行，实际结果及限制见 verification 的 Conda 小节；这些不代替人工看到图标和使用菜单。

环境准备阶段首轮为 36 passed、3 failed、2 errors，使用全新独立 pytest 临时目录排除共享 TEMP 权限问题后为 39 passed、2 failed。首轮还暴露关闭耗时提示被命令确认覆盖的竞态。测试钩子和提示竞态已在后续收尾修复，见文末。

第一步只启动并观察，在 **Windows PowerShell** 执行：

```powershell
Set-Location 'D:\ldj\03\DeskMate'
& 'D:\anaconda3\Scripts\conda.exe' run --no-capture-output -n deskmate-win python -s -X utf8 -m likecc.desktop --demo
Write-Host "退出码=$LASTEXITCODE"
```

conda run 使用指定环境及其激活所需路径，无需修改 PowerShell profile、执行策略或 conda init。`-s` 仅为该 Python 进程排除用户级 site-packages，避免混入环境外的包；不修改用户全局设置。实际解释器已核对为新 Conda 路径，源码仍来自 DeskMate 工作目录。

预期是“离线演示 · 无模型网络请求”、就绪、`offline-demo / fake`、Windows 临时工作区，以及通知区（可能在“^”内）的蓝底白色 D 图标。用户已执行下方完整离线清单，末行退出码在真正退出后显示。

人工进展（2026-11-18）：用户确认离线窗口就绪，真实 D 托盘图标出现。点击标题栏右上角 X 后，主窗口隐藏、D 图标保留、启动终端仍在运行。用户从托盘菜单恢复原窗口，确认离线模式和就绪状态正常，工作区与会话均未变化。启动、关闭隐藏和托盘恢复三步通过。

用户随后确认发送演示消息后出现 `WriteFile` 权限卡片，并按连续操作清单完成余下验收，最终明确反馈各项符合预期。当前结果如下。

| 操作 | 预期结果 | 当前证据 |
| --- | --- | --- |
| 在 demo.txt 权限卡片点击“本次允许” | 显示写入成功，随后出现问答卡片 | 通过，用户确认 |
| “下一步”选择“等待取消”，提交回答 | 出现 DemoWait，状态“执行中”，取消按钮可用 | 通过，用户确认 |
| 点击标题栏 X，保持隐藏约 10 秒，再从 D 图标菜单选择“显示 DeskMate” | 窗口恢复，原任务仍在执行，工作区/会话和已有历史保持一致 | 通过，用户确认 |
| 再次隐藏，从 D 图标菜单选择“取消当前请求”，稍后恢复窗口 | 原任务 cancelled，回到就绪，卡片清空、输入可用 | 通过，用户确认 |
| 在同会话再发送一条演示消息，批准写入，问答选择“完成”后提交 | 正常 completed，仅新增一次最终回答，再次就绪 | 通过，用户确认 |
| 点击标题栏 X，从 D 菜单选择“退出应用” | 图标消失，启动终端返回，退出码 0，应用进程结束 | 通过，用户反馈退出码 0 和进程检查通过，Codex 复核 PID 已消失 |

启动演示的 PID 为 `54464`。用户退出后，Codex 只读复核该 PID 已消失，并且没有检测到 deskmate-win 路径下的遗留 Python 进程。验收使用内置离线模型。此次人工窗口的临时工作区具体路径尚未提供，删除情况待独立核对。此前新 Conda 环境的独立控制器预检已确认线程退出和其临时目录清理通过，两次检查的范围分别保留。

## R3.1 当前验收汇总（2026-11-18）

原始两项边界修复已通过 WSL 完整回归与故障注入，WSLg 离线人工、DeepSeek 指定任务、Windows Conda 离线真实托盘清单均已通过。Windows 真实托盘现在已有用户操作证据，WSLg 自身托盘检测仍为 False。

2026-11-18 收尾修复验证了以下行为。

1. 防联网测试只允许标准库 `socketpair()` 执行期间的数字回环地址连接，普通 `connect` 和 `connect_ex` 继续被拦截。Windows asyncio 可以完成内部唤醒管道初始化，离线 GUI 的批准和拒绝用例均通过。
2. 使用受控时钟和后台关闭屏障重现了先显示警告、后收到命令确认的顺序。修复后，迟到的确认和托盘消失都保留关闭警告，后台线程结束后退出回调只调用一次。

Windows Conda deskmate-win 和 WSL cc 的桌面专项均为 42 passed。该阶段 WSL 完整回归为 821 passed。随后修正了三项 Windows 测试的 Shell 输入，Windows 完整回归为 815 passed、6 skipped、0 failed，WSL 受影响测试为 92 passed。Windows 的 Bash 工具沿用 `cmd.exe`，使用其原生命令语法。真实托盘人工结果来自此前已完成的离线清单。

此前人工窗口临时工作区删除情况待具体路径核对。共享 pytest TEMP 的权限问题已用全新独立 basetemp 排除，后续原生回归继续采用独立测试目录。

后续兼容性与交付验证包括其他 Windows Shell 命令、盘符/链接/权限、通用子进程树清理、Windows 真实 Provider、外部扩展集成、干净环境安装和 DeskMate 打包资源。真实 Provider 恢复后新模型调用及长期稳定性也未覆盖。最新命令、结果与证据来源见 [verification.md](verification.md) 文末。

## R5 验收中的窗口位置恢复（2026-11-22）

用户在持久化重启验收时发现主窗口左侧及标题栏超出屏幕，Alt+空格未能恢复。现在首次显示和托盘“显示 DeskMate”后会检查窗口外框是否位于某个屏幕的可用区域内；越界时调整大小和位置。合法负坐标副屏上的完整窗口保持原位，计算使用 Qt 逻辑像素，不重复应用显示缩放。布局最小尺寸若大于屏幕，仅保证标题栏可达；其他分辨率、多显示器与原始偏移原因仍需实际环境验证。

修正需要正常退出旧进程并重新启动才能加载。复验检查完整标题栏、拖动能力及原任务历史，保留同一工作区；无需重建任务库或修改系统显示设置。Windows/WSL 各 38 项相关离线回归通过后，用户正常重开并确认窗口完整、可拖动、历史保留，本次 Windows 可见复验通过。其他显示器配置未人工覆盖，原始偏移诱因尚未确定，托盘恢复定位的修正目前以自动化回归为证据。
