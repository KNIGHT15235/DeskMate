# 验证说明

本页按阶段保留 LikeCC 0.2.0 和 DeskMate 各轮实际结果。各阶段的“待确认”代表当时状态；最新提交前复审见首节，R8-A.1 及更早数字均为历史证据，不计作本次重跑。剩余人工项继续按用户要求暂缓。

## R8-A 提交前代码复审与版本固定（2026-11-25）

### Git、环境与审查范围

仅操作 `D:\ldj\03\DeskMate-Standalone`，`main`，提交前 HEAD 为 R7 `22f4ddeb30bb74617cd6080f912155a43f385b82`。origin fetch/push 均指向 `https://github.com/KNIGHT15235/DeskMate.git`；R7 为当前祖先，初始暂存区为空，没有 merge/rebase/cherry-pick 等未完成操作。所有既有 R8-A 修改保留。以命令级 `safe.directory` 适配 Windows 归属检查，没有更改全局 Git 配置。

Windows 实测 10.0.19045、Conda deskmate-win Python 3.12.7、PySide6 6.8.3、SQLite 3.54.1；WSL Ubuntu-24.04 / cc Python 3.11.16、PySide6 6.8.3、SQLite 3.53.4。读取实际源码、全部变更测试和目标/路线/UX/验证/学习文档，核对 R8-A.1 日志与历史源码 manifest。开始时 214 个 Python 文件与历史最终回归一致；本轮复审后有 5 个文件变化：controller、window、schedules、widgets 和 test_desktop_ux，因此完整回归重新执行。

五页导航只管理 QWidget 可见性；Qt 主线程不执行模型或文件读取，后台 asyncio、唯一事件消费者和 Runtime 资源所有权保留。原权限回复继续核对 session/run/request，通知继续核对 workspace/revision/真实请求；查看不批准、稍后不重跑，停止周期仍需明确确认。核对绑定 execution_id，记忆修改删除继续经服务，定时上下文和权限范围未扩大。成果仅显式读取已有记录的工作区内 UTF-8 Markdown/文本，最大 512 KiB，纯文本展示，不提升历史回读状态。没有改动 Agent、Runtime、SessionService、权限策略、SQLite 核心或 DesktopApplication 生命周期。

### 先复现、后最小修复

| 问题 | 复现证据 | 最小修复 |
| --- | --- | --- |
| P0：连续预览覆盖较新任务草稿 | `r8-review-repro.log` 的任务用例失败，第一份响应把第二份表单恢复为第一份 | 临时 preview_id 与表单快照绑定，旧响应不能消费新请求；原保存 token 与 revision 仍有效 |
| P1：换成果文件保留旧内容或接收迟到结果 | 同一日志的文件选择用例失败，新路径下仍显示 FIRST FILE | 选择变化清空内容、折叠预览并废弃旧读取令牌，不自动发起读取 |
| P1：不同执行复用路径时预览串来源 | `r8-review-context-repro.log`：执行切换 1 failed，目录链接边界 1 passed | 预览身份包含 execution，聊天包含 session/run；变更来源后要求显式重新读取 |
| P0：旧工作区释放期仍可预览/取消任务 | `r8-review-handover-repro.log`：2 failed；通过可控异步释放复现旧调度库接受命令 | 调度入口同时核对就绪状态、展示 workspace 和存储 workspace |
| P0：后台已切换但旧页面尚未刷新时，草稿进入新工作区 | `r8-review-stale-page-repro.log`：对话/任务/记忆 3 failed | 主窗口提交携带实际展示工作区，后台在任何修改前重新匹配，旧页面得到拒绝回执 |

后两组先在忽略目录的独立探针复现，以保持当时完整测试运行中的源码不变；确认后原样纳入 `tests/test_desktop_ux.py`。本轮共新增 9 项用例，该模块由 18 增至 27。Windows 的目录链接测试实际使用 NTFS junction，WSL 使用符号链接，没有增加跳过、降低原断言或提高已有等待上限。

### 本次实际验证

所有测试使用隔离目录和 fake client。Qt offscreen 仅作为自动化环境，不代表新的 Windows 人工验收。两平台完整回归串行执行；日志、XML、源码 manifest 和辅助脚本仅保存在已忽略的 `.r1-verification/`。

| 阶段 / 命令内容 | 实际结果 |
| --- | --- |
| 最初两个复现用例 | 2 failed；修复后相关预览用例 4 passed / 16 deselected，7.10s |
| 来源切换与链接越界复现 | 1 failed / 1 passed / 20 deselected，11.18s |
| 前三项修复后 GUI 9 模块 | 97 passed，6 warnings，83.25s |
| 首轮 Windows 完整回归（工作区隔离修复前） | 1012 passed / 6 skipped / 6 warnings，238.54s；SubAgent 90/90 |
| 首轮 WSL 完整回归（工作区隔离修复前） | 1018 passed / 6 warnings，150.69s；SubAgent 90/90 |
| 交接与旧页面命令复现 | 分别 2 failed / 13.06s、3 failed / 2 deselected / 12.39s；未作为通过证据 |
| 全部五项修复后 Windows GUI 9 模块 | **102 passed，6 warnings，90.13s** |
| 隔离防护的首次完整复测 | Windows 2 failed / 1015 passed / 6 skipped，214.87s；旧故障恢复回归发现 error 状态的诊断扫描被过度拦截，执行证据未刷新。保留失败记录 `r8-win-review-verified-full.log`；收窄为允许同工作区的只读诊断扫描，原 `_tick_schedules` 继续阻止派发，交接/关闭及跨工作区仍拒绝 |
| 诊断兼容修正后定向回归 | **34 passed，1 warning，27.96s**；原两项失败恢复断言、9 项新增边界及原 UX 回归均通过 |
| 最终 Windows 启动专项 | **6 passed / 13 deselected，1.64s**；最大 wait 0.094s、最大 `_open` 0.125s，未复现超时 |
| 最终 Windows 完整离线回归 | **1017 passed / 6 skipped / 6 warnings，203.20s**；原 6 项平台跳过不变 |
| 最终 WSL 启动专项 | **6 passed / 13 deselected，6.07s**；最大 wait 0.499s、最大 `_open` 0.550s，未复现超时 |
| 最终 WSL 完整离线回归 | **1023 passed / 0 skipped / 6 warnings，145.22s** |
| 双平台独立 SubAgent、编译、入口与 fake 演示 | **各 90/90**；各 214 个 Python 文件 AST/内存编译通过，3 个帮助入口、离线样例准备及推进时钟均 exit 0 |
| Windows / WSL `python -m pip check` | 两平台均 `No broken requirements found` |
| `uv lock --check --offline --python <deskmate-win-python>` | 58 packages，exit 0，锁文件未改 |
| `git diff --check`、提交候选路径/敏感信息检查 | 通过；4 处匹配为 R7 既有环境变量示例或离线假值，复核后无待处理匹配；本机数据不进入提交 |

最终完整回归入口命令：

```powershell
& C:\Users\28436\.conda\envs\deskmate-win\python.exe -s -B -X utf8 .r1-verification/r8_run.py D:/ldj/03/DeskMate-Standalone win-review-release
wsl.exe -d Ubuntu-24.04 --cd /mnt/d/ldj/03/DeskMate-Standalone -- /home/ldj/anaconda3/envs/cc/bin/python -s -B -X utf8 .r1-verification/r8_run.py /mnt/d/ldj/03/DeskMate-Standalone wsl-review-release
```

该本地辅助脚本在新的临时 cwd 依次执行 `python -s -B -X utf8 -m pytest -q -ra -p no:cacheprovider -c REPO/pyproject.toml --rootdir=REPO REPO/tests --basetemp=TEMP/pytest --junitxml=REPORT`、`python REPO/tests/verify_subagent.py`、`python -m likecc --help`、`python -m likecc.desktop --help`、`python -m examples.deskmate_notifications --help`、同样例的 `--check --root TEMP/demo` 与 `--advance-minutes 10 --root TEMP/demo`；解释器前缀、`PYTHONPATH=REPO;REPO/tests`（Linux 为冒号）与 `QT_QPA_PLATFORM=offscreen` 固定。214 个 Python 文件逐个 AST 解析和内存编译并记录 SHA-256。没有真实 Provider、网页或外部 MCP 调用；网络操作仅为用户明确授权的 Git fetch/push/远程 SHA 核验。

GUI 定向命令为上述 pytest 参数加 9 个模块：`test_desktop_ux.py`、`test_desktop_window.py`、`test_desktop_lifecycle.py`、`test_desktop_scheduling.py`、`test_desktop_memory.py`、`test_desktop_notifications.py`、`test_r6_schedule_review.py`、`test_r7_acceptance.py`、`test_r7_request_review.py`，结果保存为 `r8-review-gui-final.log/xml`。诊断兼容修正后另外运行 `test_schedule_review_regressions.py tests/test_desktop_ux.py`（相同 pytest 参数，日志 `r8-review-diagnostics.log/xml`），再跑完整回归。最终启动专项沿用 `.r1-verification/r8_a1_probe.py REPO <win/wsl>-review-release-startup startup`，内部运行 `test_r7_request_review.py -k old_notification_commands -o faulthandler_timeout=5`，仅记录时长，原 6 秒等待不变；结果前缀 `r8-a1-<win/wsl>-review-release-startup`。

历史 R8-A Windows 1008 passed / 6 skipped、WSL 1014 passed，以及 R8-A.1 GUI 93 passed / 启动各 6 passed，仅用于来源核对。首轮本次全量通过后又发现交接问题，因此也仅作中间结果；最终结论必须使用包含全部 9 个新用例的最后一轮，不混用数字。Qt 官方候选替代在 R8-A.1 出现 2 项焦点失败，本轮没有再次替换或删断言，保留现接口与 6 条弃用警告；偶发启动超时继续观察，未虚构根因。

最终 `r8-win-review-release-*` 与 `r8-wsl-review-release-*` 的 manifest 完全相同，并与当前 214 个 Python 文件逐个哈希一致。Windows 仍只跳过原 5 项 POSIX 进程组契约与 1 项依赖系统文件的旧符号链接用例；新增目录联接越界用例实际通过。所有复审 P0/P1 已修复，当前未发现未解决的提交阻塞；具备固定 R8-A 代码版本的条件，完整人工产品验收仍未完成。

### 文件边界、版本固定与发布前清单

本轮预定提交 25 个文件：9 个 desktop 源码（controller/window/schedules/memories/notifications/artifacts/widgets/theme/presentation）、4 个 GUI 测试、`scripts/capture_desktop_ux.py`、README 和 10 份文档。逐路径暂存，复核 cached name-status/stat/check；不纳入 `.likecc/`、`.r1-verification/`、数据库/WAL/SHM、截图、测试日志、虚拟环境、缓存或构建产物。源码 ZIP 使用成功推送后的完整 SHA 从 Git 对象导出，放在仓库外；实际提交 SHA、远端一致性及 ZIP 路径以版本固定交付报告为准。

用户允许剩余人工项目未完成时提交 R8-A，但这不等于产品全部验收。发布前仍需补齐：八项 Windows 真实操作的未覆盖部分；剩余截图及主观视觉评价；100%/125%/150% 原生缩放；真实系统托盘和通知交互；真实 Provider 记忆质量；R5 真实拒绝写入；R4 实网读取期间取消和重定向。已有“整洁美观”、导航/草稿/提醒/周期修改及权限卡片的部分反馈与一张原生截图仍只按下面 R8-A.1 的实际覆盖范围保留。本轮不再要求人工操作，不启动 R8-B、不制作安装包、不创建 Release。

## DeskMate R8-A.1（2026-11-24～25，阶段收尾／人工暂缓）

### 本轮实际预检

- `git status --short` / `rev-parse`：`main`，HEAD `22f4ddeb30bb74617cd6080f912155a43f385b82`；保留全部 R8-A 未提交修改，不暂存、不提交、不推送。
- Windows `deskmate-win` 实测 Python 3.12.7、PySide6 6.8.3、pytest 9.0.3、SQLite 3.54.1。当前 214 个 Python 文件按文本 SHA-256 核对，与 `r8-win-final-serial-manifest.json` 全部一致。
- 已读取 R8-A 两平台 summary / 日志：Windows 1008 passed / 6 skipped、WSL 1014 passed、SubAgent 各 90/90。以上是核对历史报告，不计作本轮重跑。后续 R8-A.1 专项已实际使用 WSL cc：Python 3.11.16、PySide6 6.8.3、SQLite 3.53.4，详见下方专项结果。
- 已确认 `examples/deskmate_notifications.py` 使用 fake client、隔离用户配置、A/B 工作区、真实控制器及 SQLite。没有真实 Provider 请求。
- 第一次从受限执行环境启动的测试进程未出现在 Windows 可见窗口列表，已仅终止该实例；这是启动工具环境记录，不计入第 8 项正常退出验收。随后使用新的隔离目录启动，窗口枚举实际返回唯一“DeskMate 桌伴”。尚未据此判定内容渲染或操作通过。

当前验收根目录：`.r1-verification/r8-a1-visible-20261124-220538/`。实际进程入口：

```powershell
# 设置仅作用于启动子进程的环境；未改变系统缩放。
$env:QT_QPA_PLATFORM = 'windows'
Remove-Item Env:QT_SCALE_FACTOR -ErrorAction SilentlyContinue
Remove-Item Env:QT_SCREEN_SCALE_FACTORS -ErrorAction SilentlyContinue
& C:\Users\28436\.conda\envs\deskmate-win\pythonw.exe -u -s -B -X utf8 -m examples.deskmate_notifications --root D:\ldj\03\DeskMate-Standalone\.r1-verification\r8-a1-visible-20261124-220538
```

通过 `Start-Process -WindowStyle Normal` 启动并将 stdout / stderr 分别保存到该目录 `launch.log` / `error.log`；已核对打印的 `offline-r7 / fake`，启动错误日志为空。测试窗口保留给用户操作。`screenshots/` 已创建且由仓库现有规则忽略，尚未保存本轮原生截图；不复用 R8-A 的 18 张 offscreen 图作为本轮可见证据。

### 人工验收进度

| 项目 | Windows 实际窗口 | 用户视觉 / 操作反馈 |
| --- | --- | --- |
| 1 主界面与导航 | 用户确认五页切换正常；手动缩小后恢复窗口，未发现严重遮挡，按钮可见或可滚动到达；未记录具体尺寸和系统缩放 | 2026-11-25：初始界面“正常显示，整洁美观”；任务“顺畅，正常显示”；记忆“顺畅无遮挡”；其余导航与窗口布局合并反馈“这组正常” |
| 2 对话与草稿保持 | 用户确认未发送草稿切任务页再返回后完整且可继续编辑；工具详情默认折叠并可展开。运行期间切页是否重跑的人工核对暂缓，不包含跨退出持久化 | 2026-11-25 合并反馈：“这组正常” |
| 3 一次性提醒 | 用户确认对话输入“明天晚上七点提醒我复习项目笔记”后自动进入预览，明天 19:00 / Asia/Shanghai / 一次性正确，确认保存后易于定位；按发送→确认保存两次主要按钮路径，未反馈多余或不清楚的操作。到期处理尚未在本项验收 | 2026-11-25 用户原话：“全部正确” |
| 4 周期任务管理 | 用户确认“R7 两次写入”的状态、时间、执行历史和技术详情可查看，修改为 2026-11-26 20:00 / Asia/Shanghai / 每周并预览确认后成功，历史保留；只读数据库复核一致。停止安排及取消单次动作人工验收暂缓 | 2026-11-25 用户原话：“全部正确” |
| 5 权限交互与通知跳转 | 用户确认原卡片跳转、路径及三个操作正确；原生手动截图已核对。两项请求随后均 ended，未写入。批准/拒绝/取消实际点击结果与旧通知历史跳转人工验收暂缓 | 2026-11-25 用户原话：“正确”“已保存”；截图 `screenshots/06-permission.png` |
| 6 成果预览 | 未完成人工验收 | 用户要求暂缓 |
| 7 记忆管理 | 未完成人工验收 | 用户要求暂缓 |
| 8 系统托盘与退出 | 未完成人工验收；不得以第一次测试进程的强制清理代替 | 用户要求暂缓 |

2026-11-25 用户明确要求先跳过剩余人工步骤，已确认结果保留；其余人工项、100% / 125% / 150% 原生缩放及剩余六类截图均记为暂缓／未验收。转入无需人工操作的专项检查与文档收尾，不据此宣布 R8-A 已全部验收，R8-B 尚未开始。

只读记录 `manual-deferred-state.json`：该次运行 completed，但 reason 明确“没有已写入的成果，存在工具拒绝或失败”，artifact 与 write_intents 均为空，两项请求 active=0 / ended；fake 模型输入日志 6 条、写入日志 0 条，两输出均不存在。没有把运行结束当成文件生成成功。桌面进程仍在，没有执行或声称通过本轮正常退出清理。

### 周期修改复核与权限场景准备（2026-11-25）

以 `sqlite3.connect(..., uri=True)` 的 `mode=ro` 连接只读查询当前隔离 A 工作区。周期任务修改结果为 revision 2、`2026-11-26T20:00:00 / Asia/Shanghai / weekly`；旧次执行为 cancelled，历史保留，model_policy=ask，输出仍为 `outputs/first.md`、`outputs/second.md`。查询辅助命令最初漏传 `uri=True` 两次打开失败，修正该只读查询后成功；这不是产品数据库故障，没有修改产品代码。

从实际 next_due 与演示时钟计算所需分钟数后，运行：

```powershell
& C:\Users\28436\.conda\envs\deskmate-win\python.exe -s -B -X utf8 -m examples.deskmate_notifications --root D:\ldj\03\DeskMate-Standalone\.r1-verification\r8-a1-visible-20261124-220538 --advance-minutes 1672
```

命令 exit 0，演示时钟推进至 `2026-11-26T12:02:07.719719+00:00`，系统时间未改变。后续只读断言确认新执行为 awaiting_model、对应“等待本次模型调用确认”通知存在、历史 cancelled 记录仍在；推进前后 `model-inputs.jsonl` 和 `writes.jsonl` 均为 0 条。只读快照保存在验收根目录 `before-permission-clock.json` / `after-permission-clock.json`。这属于场景准备与数据核对，不计为用户已经批准模型、写入权限或完成成果验收；推进也使较早的隔离提醒到期，不涉及真实用户安排。

### 权限卡片观察与截图尝试（2026-11-25）

用户确认通知跳转、卡片可见性、路径及按钮含义正确后，只读核对当前执行 waiting、WriteFile 请求 description=`outputs/first.md` 且 active=1；fake 模型输入日志 2 条、写入日志 0 条，`outputs/first.md` 和 `outputs/second.md` 均不存在。证据为验收根目录 `permission-card-observed.json`，未自动批准任何写入。

以 computer-use 的 `sky.list_windows()` 重新选择唯一“DeskMate 桌伴”，请求原生窗口截图：第一次返回 `FrameArrived timed out: timed out waiting on channel`；重新枚举、选择窗口后重试一次，返回 `window capture timed out: timed out waiting on channel`。两次均未取得截图，随后停止自动采集；不使用 offscreen 代替，也不修改产品代码。开始指导用户用 Windows 截图工具手动保存 `screenshots/06-permission.png`；当前仍待用户确认文件已保存。

用户随后反馈“已保存”，文件已实际读取并视觉核对：原生窗口中 first.md 的 WriteFile 卡片、本次允许/拒绝/取消运行三按钮清楚可见，素材为隔离 fake 工作区，未见真实密钥或私人文档。该截图不证明后来仍是同一活动请求。

保存后的只读快照 `after-permission-screenshot.json` 显示：first.md 请求 active=0 / resolution=ended，工具证据为权限拒绝及后续文件不存在；同一运行已产生 second.md 请求 active=1。源文件读取时间 08:13:14 UTC、首次失败读取 08:18:14 UTC，与默认 300 秒等待相符；持久记录未单独保存超时原因，故不假定用户主动点了拒绝。此时 fake 模型输入日志 4 条、写入日志 0 条、两输出均不存在。接下来按当前 second.md 卡片进行明确允许验收，不重新批准旧请求或修改权限策略。

### 人工暂缓后的自动专项（2026-11-25）

用户暂缓人工项目后，本轮继续已有授权范围内的只读检查和隔离离线测试。没有修改产品 Python 源码、测试断言或超时。被 Git 忽略的 `.r1-verification/r8_a1_probe.py` 为本轮独立探针：新建临时 cwd，使用指定解释器和仓库源码，offscreen 仅用于自动化；不操作正在展示的真实窗口，不将自动化冒充人工通过。

实际入口命令（输出日志、XML、summary 均在 `.r1-verification/`）：

```powershell
wsl.exe -d Ubuntu-24.04 --cd /mnt/d/ldj/03/DeskMate-Standalone -- /home/ldj/anaconda3/envs/cc/bin/python -s -B -X utf8 .r1-verification/r8_a1_probe.py /mnt/d/ldj/03/DeskMate-Standalone wsl-startup startup
& C:\Users\28436\.conda\envs\deskmate-win\python.exe -s -B -X utf8 .r1-verification/r8_a1_probe.py D:/ldj/03/DeskMate-Standalone win-startup startup
& C:\Users\28436\.conda\envs\deskmate-win\python.exe -s -B -X utf8 .r1-verification/r8_a1_probe.py D:/ldj/03/DeskMate-Standalone win-focus-candidate focus-candidate
& C:\Users\28436\.conda\envs\deskmate-win\python.exe -s -B -X utf8 .r1-verification/r8_a1_probe.py D:/ldj/03/DeskMate-Standalone win-gui-current gui
```

探针调用 pytest 的共同参数为 `-q -ra -p no:cacheprovider -c REPO/pyproject.toml --rootdir=REPO --junitxml=REPORT`。startup 指定 `tests/test_r7_request_review.py -k old_notification_commands -o faulthandler_timeout=5`，保留原 `wait(..., timeout=6)`，记录实际 wait / `_open` 时间，失败时打印线程栈。focus-candidate 指定 `tests/test_r7_acceptance.py -k permission_navigation_reveals_card`，仅在该进程临时替换激活调用；不更改保存的源码。

| 本轮实际检查 | 结果 | 结论 |
| --- | --- | --- |
| WSL 启动相关原 6 个参数用例 | 6 passed / 13 deselected，5.74s | 未复现；最大 wait 0.998s，最大 `_open` 0.996s |
| Windows 同组启动用例 | 6 passed / 13 deselected，1.58s | 未复现；最大 wait / `_open` 均约 0.125s |
| Windows 激活接口候选替代 | 6 passed / 2 failed / 11 deselected，53.55s | row-hidden / button-hidden 在原 `request_area.hasFocus` 等待处失败；候选未采纳 |
| Windows 当前实现 GUI 回归 | **93 passed / 0 failed / 0 skipped，6 warnings，73.19s** | 独立新进程，不装载候选替代；包含原隐藏恢复焦点断言 |

startup 结果只说明本次定向复测未复现，不足以把历史超时归因于线程启动、事件循环、系统负载或同步逻辑；没有据此调整时限。Qt 6.8 [官方弃用说明](https://doc.qt.io/qt-6.8/qapplication-obsolete.html) 推荐 `QWidget.activateWindow()`；[该 API 的 Windows 前台激活限制](https://doc.qt.io/qt-6.8/qwidget.html#activateWindow) 也说明不能仅按接口名称推导平台等价。候选保持原延迟回调、可见性和 request_id 校验，只替换两行激活调用；由于真实焦点断言失败，保留当前实现及弃用警告，后续结合原生验证处理。

gui 模式覆盖 `test_desktop_window.py`、`test_desktop_lifecycle.py`、`test_desktop_ux.py`、`test_desktop_scheduling.py`、`test_desktop_memory.py`、`test_desktop_notifications.py`、`test_r6_schedule_review.py`、`test_r7_acceptance.py`、`test_r7_request_review.py`。本轮没有更改公共组件或生命周期实现，不重跑整套 1014 项和 SubAgent 90 项；R8-A 的双平台全量结果继续仅作为历史证据。

最终核对当前 `likecc/`、`tests/`、`examples/`、`scripts/` 共 214 个 Python 文件与 R8-A 最终源码 manifest 一致，产品及既有测试源码未变；`git diff --check` 通过。当前 GUI 回归 6 条警告均来自保留的 Qt 激活接口。人工截图 `06-permission.png` 实际为 1386×937 PNG、125717 字节，SHA-256 为 `1642a7648ca0eb41e3cdd383436a221c2af88ee60565e5b8129c4a4277b38d61`。

### DeskMate R8-A.1 UI/UX 阶段验收报告

本报告对应用户主动暂缓剩余人工步骤后的阶段性收尾，不是全部人工验收完成报告。

| 项目 | 结论 |
| --- | --- |
| 1 Git 与环境 | main / 22f4ddeb30bb74617cd6080f912155a43f385b82；Windows deskmate-win Python 3.12.7、WSL cc Python 3.11.16，PySide6 均 6.8.3；R8-A 改动继续未提交 |
| 2 八项可见结果 | 基础主界面、导航、草稿、一次性提醒、周期查看修改及权限卡片跳转已有用户确认；运行中切页、授权结果、取消/停止、成果、记忆、托盘退出未完成的部分暂缓，详见上表 |
| 3 实际截图 | `.r1-verification/r8-a1-visible-20261124-220538/screenshots/06-permission.png`，用户 Windows 手动采集并已读取核对；其余六类暂缓 |
| 4 视觉反馈 | 用户评价“正常显示，整洁美观”；导航顺畅、无遮挡，手动缩小恢复后布局正常；指定系统缩放尚未确认 |
| 5 核心流程改善 | 提醒创建和周期修改获得正向确认，通知定位原卡片正确；记忆与成果预览的真实体验尚不能据此评价 |
| 6 P0/P1/P2 | 本轮用户未报告已确认的 P0/P1/P2 产品缺陷；Qt 激活兼容与历史启动超时列为 OBS-01/02 观察项，不把未验收等同无问题 |
| 7 必要修复 | 未改产品代码；Qt 候选仅在独立测试进程验证，因两项焦点回归未采纳；截图失败采用手动采集，没有改业务代码 |
| 8 本次测试 | Windows GUI 93 通过；Windows/WSL 启动各 6 通过；Qt 候选 6 通过/2 失败；源码 manifest 一致、diff 空白检查通过。命令、日志和失败均见上方 |
| 9 未解决事项 | Qt 弃用警告保留，历史启动超时根因未明；其余人工及原生缩放暂缓，原生自动截图接口不可用；现存演示窗口保留且本次执行已结束、无成果 |
| 10 最终标准 | 尚未达到完整人工验收标准；具备可供代码复审的阶段性基线 |
| 11 R8-B 建议 | 下一步先复审当前改动并明确 R8-B 范围；可把暂缓的人工项并入 R8-B 发布前验收，但不能据此宣称已验证全部真实窗口行为。本轮不启动打包 |
| 12 用户后续确认 | 确认阶段性基线及未验收清单是否接受、是否将剩余人工项纳入 R8-B，以及下一轮打包范围；当前无需继续逐项人工操作 |

本轮没有暂存、提交、推送、创建 Release 或制作安装包，没有调用付费 Provider。阶段收尾完成，等待用户复审和下一轮指令。

## DeskMate R8-A（2026-11-24）

### 基线、范围与环境

只在 `D:\ldj\03\DeskMate-Standalone` / `/mnt/d/ldj/03/DeskMate-Standalone` 开发。开始时 `main` / `22f4ddeb30bb74617cd6080f912155a43f385b82`，工作区干净；完成后仍在该分支及 HEAD，未提交、推送、发布或打包。旧项目目录没有修改。

| 平台 | 解释器 | Python / PySide6 / pytest / SQLite |
| --- | --- | --- |
| Windows Conda deskmate-win | `C:\Users\28436\.conda\envs\deskmate-win\python.exe` | 3.12.7 / 6.8.3 / 9.0.3 / 3.54.1 |
| WSL Ubuntu 24.04 Conda cc | `/home/ldj/anaconda3/envs/cc/bin/python` | 3.11.16 / 6.8.3 / 9.0.3 / 3.53.4 |

没有新增依赖或更改 `pyproject.toml` / `uv.lock`，没有安装环境包。变更限于桌面展示与适配、测试、离屏截图脚本和文档；Agent、Runtime、SessionService、权限、调度/记忆/通知业务核心及 `DesktopApplication` 保持原实现。

### 实际命令与隔离方式

最终检查由被 Git 忽略的 `.r1-verification/r8_run.py` 顺序执行，输出同目录的 `r8-<平台>-<检查>.log`、JUnit XML、summary JSON 和源码 manifest。该脚本为本地验收辅助，不是产品运行依赖。实际入口命令：

```powershell
Set-Location D:\ldj\03\DeskMate-Standalone
wsl.exe -d Ubuntu-24.04 --cd /mnt/d/ldj/03/DeskMate-Standalone -- /home/ldj/anaconda3/envs/cc/bin/python -s -B -X utf8 .r1-verification/r8_run.py /mnt/d/ldj/03/DeskMate-Standalone wsl-final-serial
& C:\Users\28436\.conda\envs\deskmate-win\python.exe -s -B -X utf8 .r1-verification/r8_run.py D:/ldj/03/DeskMate-Standalone win-final-serial
```

每个平台使用独立临时 cwd，把仓库及 `tests` 加入 `PYTHONPATH`，设置 `QT_QPA_PLATFORM=offscreen`、`PYTHONDONTWRITEBYTECODE=1`、`PYTHONUTF8=1`，复制测试所需 README / pyproject 到临时目录。源码导入路径核对指向本独立仓库。子进程均使用对应解释器和 `-s -B -X utf8`，实际执行下列检查（`REPO`、`CWD`、`REPORT` 为该平台绝对路径）：

```text
python -m pytest -q -ra -p no:cacheprovider -c REPO/pyproject.toml --rootdir=REPO REPO/tests --basetemp=CWD/pytest --junitxml=REPORT
python REPO/tests/verify_subagent.py
python -m likecc --help
python -m likecc.desktop --help
python -m examples.deskmate_notifications --help
python -m examples.deskmate_notifications --check --root CWD/demo
python -m examples.deskmate_notifications --advance-minutes 10 --root CWD/demo
```

另外以 `ast.parse` 和内存 `compile(source, path, 'exec')` 检查 `likecc/`、`tests/`、`examples/`、`scripts/` 下所有 Python 文件，生成按文本规范化换行后的 SHA-256 manifest，不写 pyc、不构建分发包。测试用 fake client、临时 SQLite 和工作区；没有调用计费 Provider、读取个人模型配置或使用外部网络完成测试。

锁一致性与空白检查的实际命令：

```powershell
$env:UV_PYTHON_DOWNLOADS = 'never'
$env:UV_CACHE_DIR = 'D:\ldj\03\DeskMate-Standalone\.r1-verification\uv-r8-cache'
& C:\Users\28436\.local\bin\uv.exe lock --check --offline --python C:\Users\28436\.conda\envs\deskmate-win\python.exe
git -c safe.directory=D:/ldj/03/DeskMate-Standalone diff --check
```

`uv lock --check` 通过，解析 58 个包，没有重写锁文件。Git 的单次 `safe.directory` 参数仅用于当前命令，不修改全局配置。

### 自动化结果

最终两平台串行运行，同一份 214 个 Python 源文件的 manifest 一致，结果如下；不是 R7 历史数字：

| 检查 | Windows（r8-win-final-serial） | WSL（r8-wsl-final-serial） |
| --- | --- | --- |
| 完整 pytest | **1008 passed / 6 skipped / 0 failed，165.93s** | **1014 passed / 0 skipped / 0 failed，171.56s** |
| 独立 SubAgent 脚本 | **90/90** | **90/90** |
| Python 语法 / 编译 | 214 文件通过 | 214 文件通过 |
| CLI / 桌面 / 通知演示帮助 | 均 exit 0 | 均 exit 0 |
| 离线演示准备 / 时钟推进 | 均 exit 0 | 均 exit 0 |

Windows 6 个跳过沿用原平台条件：5 个 POSIX/WSL 进程组契约，1 个缺少适合的系统文件用于 symlink 检查；本轮没有新增 skip。每个平台完整测试各有 6 条 Qt 激活 API 弃用警告，详见下方。`git diff --check` 通过，源码与测试保持最终回归时版本。

新增 `tests/test_desktop_ux.py` 共 18 项：导航期间消费者/权限不变、各编辑器草稿、流式文本选择与滚动、A/B 工作区隔离、交接隐藏旧审计但显示启动错误、预览失效及迟到响应不覆盖新输入、真实成果预览不重跑且不改证据、关闭提醒仍待业务处理、四种成果状态、受限文件预览、五档窗口大小和滚动到确认按钮。最终新增用例专项 Windows 结果为 **18 passed，1 warning，17.51s**（`r8-win-audit-green.log`）。既有 R6/R7 的实际权限、写入、取消/停用、核对、记忆失效与重启契约仍参加完整回归。

### 中间失败与修复记录

所有下列记录均来自本轮，不删除失败日志，不把文件名中的 `final` 当成通过证据。

| 记录前缀 / 检查 | 实际结果 | 处理 |
| --- | --- | --- |
| r8-win-ui-first | 14 failed / 31 passed | 原工具文字断言迁移到完整工具过程；嵌入页可见性及停止周期确认适配继续修复 |
| r8-win-ui-second | 9 failed / 32 passed / 3 errors | 改用真正 QWidget 页面；长标签允许换行收缩；补齐新测试依赖的离线网络 guard fixture 导入 |
| r8-win-ui-third | 2 failed / 32 passed | 隐藏窗口恢复后原权限按钮焦点仍不正确，保留失败继续处理 |
| r8-win-ui-final | 2 failed / 56 passed | 同一焦点问题；加入恢复后延迟聚焦，并重新校验当前页及请求身份 |
| r8-win-focus | 8 passed / 11 deselected | 对应隐藏/最小化恢复与权限导航专项通过 |
| r8-win-full | 1 failed / 1004 passed / 6 skipped，240.88s | 旧 R6 导航文案断言仍要求完整长标签；迁移到无障碍描述/提示与可见待处理数，保留 0/1 状态和业务断言 |
| r8-win-ui-fonts | 1 failed / 58 passed | 同一 R6 用例的第二个旧标签断言继续迁移 |
| r8-win-ui-green | 60 passed，65.41s | 受影响 GUI、生命周期、记忆、调度、通知模块通过；随后补充交接错误展示和通知筛选两项边界 |
| r8-wsl-final | 1012 passed / 0 skipped，141.49s | 当时版本的完整结果；之后新增两项用例，不能作为最终源码计数 |
| r8-wsl-verified | 1 failed / 1013 passed / 0 skipped，149.43s | `test_old_notification_commands_are_rejected_during_workspace_release[open]` 在初始控制器启动的 6 秒等待超时，尚未进入旧通知操作；保留原时限及失败 |
| r8-wsl-startup-probe | 6 passed / 13 deselected，6.22s | 原 6 个旧通知参数用例附等待耗时及超时线程栈诊断，未复现；没有据此认定根因，随后串行重跑全量 |

最后一次中间启动超时发生时，另有 Windows 新增用例专项运行；这只是并发负载背景，尚不足以证明因果或宣称已经修复。诊断没有修改业务源码、放宽超时、增加 skip 或删除断言。若复审再遇启动慢，需要保留线程栈进一步定位。诊断脚本提前导入 fixture 带来的 1 条 `PytestAssertRewriteWarning` 仅属于该次探针。

通知导航仍使用 Qt 6.8 的 `QApplication.setActiveWindow` 兼容调用，完整 GUI 回归会报告 6 条弃用警告；这与实际可见/可操作断言分别记录。升级 Qt 前应验证替代激活 API，不能直接去掉激活而恢复隐藏卡片问题。

### Windows 可见验收与截图边界

实际启动了隔离 R7 fake 演示的当前 R8-A 窗口，Windows 窗口枚举识别到“DeskMate 桌伴”。原生屏幕采集第一次超时，重新枚举并选择窗口后重试仍为 `window capture timed out`，故停止原生 UI 操作，不能记作八步可见验收通过。仅关闭了本轮创建的隔离演示进程；没有操作用户的已有窗口。日志为 `.r1-verification/r8-visible-launch*.log` / `r8-visible-error*.log`。

完成了真实 Qt 控件的离屏截图及模型/SQLite 驱动的自动化布局验证。Windows offscreen 初始字体库为空，截图为方框；主题层在该场景加载本机已有微软雅黑字体后中文正常，没有下载字体或依赖在线素材。

截图保存在 Git 忽略的 `.r1-verification/r8-captures/`，共 **18 张 PNG**：对话、任务、待确认记忆、通知、设置、任务编辑，各有 1280×720 / scale 1、1024×576 / scale 1.25、853×480 / scale 1.5 三版；后两者是逻辑尺寸，实际 PNG 按缩放扩大。五种逻辑窗口的自动化几何验证还覆盖 1366×768 和 1920×1080。截图使用假资料，设置路径替换为演示路径，日志与数据库不提交。

复现截图命令和八步原生验收见 [R8-A 使用与验收指南](deskmate-ux-guide.md)。`QT_SCALE_FACTOR` 离屏模拟不等于 Windows 系统缩放人工验收。当前证据分层为：**自动化结果按上表记录；Windows 八步可见交互待用户复审；原生 125%/150%、多屏、托盘气泡、字体大小和视觉舒适度待人工评价。** 不提前进入 R8-B 打包分发。

以下为 LikeCC 0.2.0 在 2026-09-22 完成的发布验证。测试使用本地 fake 模型、临时文件和临时 Git 仓库；不需要模型 API Key。

## 已有结果

| 验证对象 | 结果 | 范围 |
| --- | --- | --- |
| pytest / Python 3.11.16 | 720 passed，0 skipped | 完整单元与集成回归 |
| pytest / Python 3.12.3 | 720 passed，0 skipped | 全新锁定依赖环境中的完整回归 |
| 独立 SubAgent 脚本 / Python 3.11 | 90/90 | Agent 定义、工具过滤、Fork、任务通知及相关契约 |
| 安装 | `uv sync --locked --dev` 通过 | 从公开 PyPI 安装；依赖版本和文件哈希保持不变 |
| 分发包 | wheel 与 sdist 构建通过 | 独立 Python 3.11 环境安装锁定依赖和 wheel 后，脱离源码检查 CLI、样式、4 个 Agent、4 个 Skill 及动态工具资源通过 |
| 命名与发布文件 | 检查通过 | 模块、CLI、配置目录、指令文件、环境变量、动态资源与测试引用一致；旧标识无残留 |

验证环境为 Ubuntu 24.04 / WSL。Provider 用例通过真实 SDK 加本地 MockTransport 验证，MCP 用例使用本地 stdio 服务；没有调用真实模型服务或外部 MCP 服务。公开版本不包含开发机器上的审计备份、私有配置和运行日志。

## 本地复现

在仓库根目录执行：

```bash
uv sync --locked
uv run --locked pytest -q
uv run --locked python tests/verify_subagent.py
uv run --locked python -m compileall -q likecc
uv run --locked likecc --help
```

测试需要 Python 3.11 或更高版本。Git / Worktree 集成用例需要本地 Git 可用；应以测试输出中的实际通过、跳过和失败数量为准。依赖安装可能需要访问包源，测试中的模型回复由本地 fake 提供。

## 重点回归

- 定义式子 Agent 默认同步；Fork 始终后台运行，结果通过任务通知回传。
- Fork 保留父请求的 system、历史和工具 schema；独立来源标记阻止递归委派，引用文档中的标签不会误触发限制。
- 子 Agent 的权限模式受父 Agent 上界约束；配置策略和本地拒绝规则保留，父会话的临时允许审批不自动继承。显式拒绝优先于安全命令的自动放行。
- 子 Agent 的文件缓存与读取记录独立。其他 Agent 修改文件后重新读取应看到新内容，未读过的新内容不能被静默覆盖；相同 mtime 也需要核对内容。
- ToolSearch 和 LoadSkill 使用子 Agent 自己的状态；Hook、客户端等按职责共享。
- 显式 Worktree 隔离、后台生命周期、任务取消和资源回收有相应回归用例。

## 验证边界

这些测试证明的是已覆盖输入下的程序行为，不用于推导模型任务成功率、生产环境稳定性或固定的 prompt cache 命中率。真实模型鉴权、端点兼容性、外部工具副作用和具体终端显示仍需在目标环境中验证。

统一入口为 Python 包 `likecc`、命令 `likecc`、配置目录 `.likecc`、项目规则 `LIKECC.md`，以及 `LIKECC_*` 团队协作环境变量。CI 会重新执行全量测试、独立 SubAgent 检查、构建和安装包验证。

本初版尚未实现 Hook 的 `agent` 执行器和插件来源的 Agent 加载；headless 尚未装配 TUI 的 Memory、Session、Skill、MCP 全套管理器。权限检查和 Worktree 不提供操作系统级安全沙箱，EviForge 后续版本的证据验收、持久化恢复与经验治理也不在本版的验证范围内。

## DeskMate R1（2026-11-16）

基线 HEAD：`4a9b77d281646385bf48fd85b8a03c4d28bbee23`，分支 `main`。开发目录为 `D:\ldj\03\DeskMate` / `/mnt/d/ldj/03/DeskMate`，源目录 `D:\ldj\03\likecc` 未修改。实现与生命周期边界见 [R1 路线记录](deskmate-roadmap.md)，代码导读与实验见 [学习记录](deskmate-learning.md)。

### 环境与依赖安装

用户指定的验收环境为本机 WSL2 Ubuntu 24.04、内核 `6.6.87.2-microsoft-standard-WSL2`、Conda 环境 `cc`，Python `3.11.16`。解释器是 `/home/ldj/anaconda3/envs/cc/bin/python`。所有下述重构后的测试和 CLI 检查都在该环境运行，不使用 Windows 的 `.venv`。

`cc` 最初未安装 pytest、Textual、模型 SDK 或 MCP。实际安装过程：

```bash
source /home/ldj/anaconda3/etc/profile.d/conda.sh
conda activate cc
cd /mnt/d/ldj/03/DeskMate

# 首次尝试，失败：uv 0.12.17 报告锁文件需要更新。
uv export --locked --group dev --no-emit-project \
  --output-file .r1-verification/requirements.txt

# 使用已有锁文件直接导出；未重写 uv.lock。
uv export --frozen --group dev --no-emit-project \
  --output-file .r1-verification/requirements.txt
uv pip install --python /home/ldj/anaconda3/envs/cc/bin/python \
  --require-hashes -r .r1-verification/requirements.txt
```

后两条成功，安装了 51 个锁定依赖；原环境中的 packaging `26.3` 调整到锁文件要求的 `26.2`。仓库 `pyproject.toml`、`uv.lock` 均无修改。此方式不把项目装成 editable；在仓库根目录执行 `python -m likecc` 即使用当前源码。

开始工作、用户补充 WSL 要求之前，还执行过 Windows `uv sync --locked --dev`（uv 自动选 CPython 3.13.13）及 `uv run --no-sync python -m pytest -q`：**716 passed、3 failed、1 skipped**。三个失败分别为 `test_six_real_tools_complete_a_file_workflow`、`test_relative_file_and_bash_tools_follow_worktree_cwd`、`test_concurrent_agents_with_shared_tools_keep_work_dirs_isolated`，涉及原生 Windows 命令执行与 POSIX 命令差异。这是重构前的平台基线，不是本轮新增失败，也不作为最终验收结果。

### 实际测试命令与结果

下列命令均先激活 `cc` 并进入开发目录。执行时设置 `PYTHONUTF8=1`。本地完整输出保存在被 Git 忽略的 `.r1-verification/`；这里列出实际结果便于提交后的复现。

1. 修改前完整基线：

   ```bash
   PYTHONUTF8=1 python -m pytest -q
   ```

   **720 passed，0 failed，0 skipped，16.89 秒**。有 1 个 `PytestCacheWarning`：WSL 无法写入此前由 Windows 生成的 `.pytest_cache/v/cache`。后续用例将缓存位置指定到 `/tmp`，不改业务代码来规避环境权限。

2. 受影响模块回归（中途版本）：

   ```bash
   PYTHONUTF8=1 python -m pytest -q -o cache_dir=/tmp/deskmate-r1-pytest-cache \
     tests/test_runtime_assembly.py tests/test_document_headless.py \
     tests/test_document_runtime.py tests/test_hook_lifecycle.py \
     tests/test_context_window.py tests/test_teams.py tests/test_subagent.py \
     tests/test_mcp.py tests/test_worktree.py tests/test_document_isolation.py \
     tests/test_document_subagent.py tests/test_tool_search.py
   ```

   **341 passed，12.11 秒**。此前较小的受影响集合另有一次 **193 passed**。

3. 补充最终两个生命周期用例后的新增测试：

   ```bash
   PYTHONUTF8=1 python -m pytest -q -o cache_dir=/tmp/deskmate-r1-pytest-cache \
     tests/test_runtime_assembly.py
   ```

   **20 passed，6.29 秒**。覆盖禁止 Textual 导入时装配、两个真实入口接入、配置/工具/权限/缓存/会话隔离、同 tool-use ID 落盘隔离、初始化异常和取消、并发及重复关闭、子任务与队友回收、子模型 client、关闭失败的后续清理、Hook 单次启动关闭、MCP 同协程连接关闭。真实 SDK 只验证关闭，没有发送模型请求；TUI 的本地 stdio MCP 测试实际启动临时 Python 服务并调用工具。

4. 最终完整回归：

   ```bash
   PYTHONUTF8=1 python -m pytest -q -o cache_dir=/tmp/deskmate-r1-pytest-cache
   ```

   **740 passed，0 failed，0 skipped，18.86 秒**。新增 20 项参数展开后的契约测试。补充最终用例前的一次全量结果为 738 passed；以 740 项这一轮为最终结果。耗时仅是本机本次运行记录，不是性能基准或性能提升结论。

5. 独立 SubAgent、编译与 CLI：

   ```bash
   PYTHONUTF8=1 python tests/verify_subagent.py
   python -m compileall -q likecc
   python -m likecc --help
   git diff --check
   ```

   分别为 **90/90**、退出码 0、正常显示原 LikeCC 帮助并退出 0、补丁检查通过。本轮触及 AgentTool、任务清理和团队名字注册表，因此执行独立 SubAgent 检查。

### 本轮验证边界

- fake 模型测试与 Textual `run_test()` 验证行为和生命周期，不代表真实模型、人工终端体验或桌面 GUI 验证。
- MCP 验证包含本地 stdio 服务；未连接外部 MCP 服务，没有验证所有重连、断网或第三方服务退出行为。
- 未运行真实模型鉴权/服务端测试、tmux/iTerm2 外部队友进程验收，以及 wheel/sdist 构建与分发安装。本轮未更改打包元数据和资源清单，不沿用历史分发验证作为新验证。
- 两种入口的能力差异保留：headless 不新增 Memory、Session、Skill、MCP 全套装配；两套执行循环仍独立。关闭时回收原本可能遗漏的后台任务属于 R1 生命周期修正。
- 不迁移已有用户配置/历史数据。新运行实例的工具结果在原根目录下增加独立子目录；这些结果保留供历史引用，新的长期保留策略尚未实现。
- 测试结束核对源仓库仍为基线 HEAD、工作区干净；DeskMate 中没有提交或推送。

## DeskMate R2（2026-11-16）

本节对应 `834ad1de41eae48559e984428a73e9c116fbcee8` 之上的未提交 R2 工作区；前述 R1 与更早版本结果保留历史含义。开发分支 `feat/deskmate`，目录 `D:\ldj\03\DeskMate` / `/mnt/d/ldj/03/DeskMate`。本轮不提交、不推送、不修改凭据或全局 Git 配置。

### 环境及实际命令

继续使用 R1 已准备好的 WSL2 Ubuntu 24.04 / conda `cc` / Python 3.11.16。无安装、依赖升级或锁文件修改。下列命令均在该目录执行，公共前缀为：

```bash
source /home/ldj/anaconda3/etc/profile.d/conda.sh
conda activate cc
cd /mnt/d/ldj/03/DeskMate
```

1. 修改前完整基线：

   ```bash
   PYTHONUTF8=1 python -m pytest -q -o cache_dir=/tmp/deskmate-r2-pytest-cache
   ```

   **740 passed，0 failed，0 skipped，28.56 秒**。不是直接引用 R1 报告数字。

2. R2-A 检查点（统一循环、权限协议、模型/工具取消；尚未接入会话服务）：

   ```bash
   PYTHONUTF8=1 python -m pytest -q -o cache_dir=/tmp/deskmate-r2-pytest-cache \
     tests/test_execution_contract.py tests/test_agent.py tests/test_runtime_assembly.py \
     tests/test_document_headless.py tests/test_document_subagent.py tests/test_document_skill.py \
     tests/test_recovery.py tests/test_tool_search.py tests/test_worktree.py \
     tests/test_hook_lifecycle.py tests/test_document_runtime.py
   ```

   **189 passed，17.57 秒**。之前构造阶段发现异常被通用失败覆盖，已修复并保持原 headless 异常断言；两项新测试错误地假设 tool_result 一定是最后一条请求消息，已改为查找对应工具结果（后面可能还有 deferred-tool 提示）。Worktree 旧测试迁移到标识回复接口，目录捕获及文件内容断言保留。

3. R2-B 受影响回归：

   ```bash
   PYTHONUTF8=1 python -m pytest -q -o cache_dir=/tmp/deskmate-r2-pytest-cache \
     tests/test_runtime_assembly.py tests/test_document_runtime.py \
     tests/test_document_headless.py tests/test_hook_lifecycle.py
   ```

   **45 passed，9.96 秒**。后续补充 TUI 命令/权限/问答与恢复测试后执行：

   ```bash
   PYTHONUTF8=1 python -m pytest -q --tb=short -o cache_dir=/tmp/deskmate-r2-pytest-cache \
     tests/test_entry_service.py tests/test_session_service.py \
     tests/test_execution_contract.py tests/test_runtime_assembly.py
   ```

   **54 passed，9.23 秒**（此后增加禁止 Textual 导入的完整服务演示测试）。

4. 最终完整回归：

   ```bash
   PYTHONUTF8=1 python -m pytest -q --tb=short \
     -o cache_dir=/tmp/deskmate-r2-pytest-cache \
     > .r1-verification/r2-final-pytest.log 2>&1
   ```

   **775 passed，0 failed，0 skipped，23.19 秒**。比本轮基线增加 **35** 项参数展开测试。日志目录沿用已忽略的 `.r1-verification/`，不作为发布文件。最终版本包含会话切换时清理工具发现/压缩恢复状态，以及恢复后的累计 token 基线断言；之前一次 775 项通过为 23.38 秒，以最终这次为准。

   中途完整回归曾为 **762 passed / 2 failed**：旧权限测试仍直接读 Future，按新公共协议迁移后保留原批准/拒绝断言；另一次为 **772 passed / 1 failed**：实际 AskUser UI 渲染触发 MarkupError，修复 Rich 渲染、动态文本转义和答案 name 映射后全量通过。未删除测试、跳过失败用例或降低原断言；不是 R1 基线失败。

5. 独立 SubAgent、编译、CLI 及 Git 差异：

   ```bash
   PYTHONUTF8=1 python tests/verify_subagent.py
   python -m compileall -q likecc examples/deskmate_session.py
   python -m likecc --help
   git diff --check
   ```

   **90/90**、退出码 0、原 LikeCC 帮助正常且退出 0、差异格式检查通过。独立脚本的 `Background task ... failed: boom` 是预期的构造失败路径，最终 90/90；本轮触及子 Agent 的执行内核，因此执行此项验证。

6. 无 UI 演示（每次临时工作区，fake client，不读取真实凭据）：

   ```bash
   python -m examples.deskmate_session --decision allow
   python -m examples.deskmate_session --decision deny
   python -m examples.deskmate_session --decision cancel
   ```

   三项均退出 0。批准：`status=completed; file_created=True`；拒绝：`status=completed; file_created=False`；取消：`status=cancelled; file_created=False`，并报告取消已传播。每项均检查 `user_input_count=1; repeated_resume_unchanged=True`。最终全量还在全新解释器阻止所有 Textual 导入，运行批准演示成功。

### 新增契约覆盖与边界

- `test_execution_contract.py`：两个 Agent 接口共享工具过程和终止回答；权限、无 handler、相关 ID、重复/过期回复、等待超时、模型/工具/权限取消、流关闭、AskUser 请求先于等待、上限失败；WSL 真实本地 shell 进程取消回收。
- `test_session_service.py`：不启动 UI 的执行/保存/恢复，原始模型异常、可恢复工具错误、输入唯一、召回临时性、崩溃尾部修复、同会话重叠拒绝、进程内会话租约、独立会话与后台任务、单次收尾、MCP 构造/连接失败可观察降级、Skills 初始化失败清理、Hook 不重复、记忆任务先于 client 回收。
- `test_entry_service.py`：实际 Textual run_test 中权限批准/拒绝/取消、AskUser 键盘输入及答案传递、`/session new`、恢复和 `/clear` 均操作服务拥有的历史。
- 保留所有 R1 20 项契约测试；其中 MCP 包含临时本地 stdio 服务。没有把 fake 模型测试称作真实模型测试，也没有把 Textual 测试称作桌面 GUI 验收。
- 本轮未运行原生 Windows 完整回归、真实模型请求、外部 MCP、tmux/iTerm2 队友、打包/安装。R1 记录的三个 Windows POSIX 命令兼容失败仍属未解决的平台边界。
- SessionService 只保证同进程租约与单次运行，不提供跨进程事务；低层 SessionManager 仍可被直接调用。取消不回滚外部副作用。当前权限等待、事件队列均在进程内，单消费者，无跨线程/网络或重启恢复承诺。
- 不改变 `-p` 默认能力：无交互确认时拒绝，不新增持久会话/记忆/Skills/MCP；完整结果执行现在与 TUI 共享内核，并有意将迭代耗尽报告为失败。
- 原目录最终检查仍为 `4a9b77d281646385bf48fd85b8a03c4d28bbee23`、干净工作区；DeskMate HEAD 未变，R2 改动保留未提交。

## DeskMate R3（2026-11-17）

### 基线与环境

R2 已提交并推送：`7f09816729ca63717b050f0cd9690c79049d456e`，分支 `feat/deskmate`。上方 R2 的“未提交工作区”等描述保留历史含义。本轮从该 HEAD 的干净工作区开始，目录 `/mnt/d/ldj/03/DeskMate`，不提交、不推送、不修改全局 Git 配置，原 likecc 目录不动。

Windows 10 / WSL2 Ubuntu 24.04.4 LTS，内核 `6.6.87.2-microsoft-standard-WSL2`；Conda `cc`、Python 3.11.16，解释器 `/home/ldj/anaconda3/envs/cc/bin/python`。下列命令先执行：

```bash
source /home/ldj/anaconda3/etc/profile.d/conda.sh
conda activate cc
cd /mnt/d/ldj/03/DeskMate
```

### 实际执行及结果

1. **修改前完整基线**：

   ```bash
   PYTHONUTF8=1 python -m pytest -q --tb=short -o cache_dir=/tmp/deskmate-r3-pytest-cache
   ```

   **775 passed，0 failed，0 skipped，28.41 秒**。没有直接沿用 R2 反馈数字。

2. **R3-0 先复现再修复**：

   ```bash
   PYTHONUTF8=1 python -m pytest -q --tb=short -o cache_dir=/tmp/deskmate-r3-pytest-cache tests/test_bash_process_group.py
   ```

   修复前 **2 failed / 1 passed，9.34 秒**：超时和取消后子 sleep 仍在运行，测试 finally 清理了自己的进程组。后增加重复清理测试并最小修复，再执行：

   ```bash
   PYTHONUTF8=1 python -m pytest -q --tb=short -o cache_dir=/tmp/deskmate-r3-pytest-cache \
     tests/test_bash_process_group.py tests/test_execution_contract.py tests/test_worktree.py
   ```

   **77 passed，6.16 秒**。曾错误指定不存在的 tests/test_tools.py，pytest 报未找到文件、未运行测试；改为实际文件后得到上述结果。没有删除失败测试或降低子进程断言。

3. **可选依赖**：

   ```bash
   uv lock --python /home/ldj/anaconda3/envs/cc/bin/python
   uv export --frozen --extra desktop --group dev --no-emit-project \
     --output-file /tmp/deskmate-r3-requirements.txt
   uv pip install --python /home/ldj/anaconda3/envs/cc/bin/python \
     --require-hashes -r /tmp/deskmate-r3-requirements.txt
   # 环境默认镜像使锁文件源地址发生批量迁移，随后使用仓库原索引重新锁定：
   uv lock --python /home/ldj/anaconda3/envs/cc/bin/python --default-index https://pypi.org/simple
   ```

   安装 **PySide6 / PySide6-Addons / PySide6-Essentials / shiboken6 6.8.3**。解析前后逐包比较，既有依赖版本没有变化；最终锁文件保留官方 PyPI 源，只增加 desktop extra、Qt 四包并由 uv 调整项目条目排序。未改系统图形配置或安装完整 Linux 桌面。

4. **R3-A 检查点**：

   ```bash
   PYTHONUTF8=1 python -m pytest -q --tb=short -o cache_dir=/tmp/deskmate-r3-pytest-cache \
     tests/test_desktop_controller.py tests/test_runtime_assembly.py tests/test_session_service.py
   ```

   **44 passed，13.86 秒**。此前配置测试样例缺少既有规则要求的 base_url，产生 1 failed / 43 passed；补齐 fake 样例，未放宽配置校验。

5. **R3-B/C 桌面检查点**：

   ```bash
   PYTHONUTF8=1 QT_QPA_PLATFORM=offscreen python -m pytest -q --tb=short \
     -o cache_dir=/tmp/deskmate-r3-pytest-cache \
     tests/test_desktop_window.py tests/test_desktop_controller.py
   # 随后加入托盘生命周期及补充边界：
   PYTHONUTF8=1 QT_QPA_PLATFORM=offscreen python -m pytest -q --tb=short \
     -o cache_dir=/tmp/deskmate-r3-pytest-cache \
     tests/test_desktop_lifecycle.py tests/test_desktop_window.py tests/test_desktop_controller.py
   ```

   前者 **9 passed，15.15 秒**。后者最终补充阶段 **19 passed，27.17 秒**，之后加入工具退出/不支持问答的两项测试，纳入下列最终全量。

   中途 **2 failed / 14 passed**：一项 GUI 测试在控件刷新前点击禁用发送按钮，改用明确的 UI 就绪条件；另一项揭示文本刚好到达展示上限时缺少截断标记，已修复实际展示边界并保留原断言。没有用长 sleep 或跳过失败掩盖时序问题。

6. **最终完整回归**：

   ```bash
   PYTHONUTF8=1 QT_QPA_PLATFORM=offscreen python -m pytest -q --tb=short \
     -o cache_dir=/tmp/deskmate-r3-pytest-cache \
     > .r1-verification/r3-full-pytest.log 2>&1
   PYTHONUTF8=1 python tests/verify_subagent.py > .r1-verification/r3-subagent.log 2>&1
   python -m compileall -q likecc examples
   python -m likecc --help
   python -m likecc.desktop --help
   git diff --check
   ```

   **800 passed，0 failed，0 skipped，67.77 秒**；比修改前基线新增 **25** 项（4 项 POSIX 回收、21 项桌面相关参数展开测试）。独立 SubAgent **90/90**，编译与两个帮助入口退出 0，差异格式检查通过。之前一次全量为 796 passed / 51.84 秒，最终计数以上述完整版本为准；这些耗时不是性能指标。

   GUI 专项仅在明确缺少 optional extra 时允许 importorskip。本轮已安装 extra，最终没有跳过任何 GUI 测试；既有核心测试全部继续执行。fresh-interpreter 测试阻止 PySide6 导入，原 CLI/core 和桌面 help 正常；启动桌面则给安装提示并退出 2。

### 显示与托盘证据分开记录

收尾另执行 `uv lock --check --offline --default-index https://pypi.org/simple`，锁文件一致性通过；将配置错误测试改为明确不存在的工作区以避免读取真实用户配置后，单独重跑 `tests/test_desktop_controller.py::test_config_error_recovery_and_repeat_exit`，**1 passed，2.96 秒**。这项仅调整测试隔离输入，业务代码与上述 800 项回归版本一致。最终 WSLg 冒烟再次正常退出，暂存区为空，HEAD 未变；进程检查未发现本轮演示或 sleep 30 测试进程残留。

| 证据 | 本轮实际结果 |
| --- | --- |
| offscreen Qt 自动化 | 实际创建 Widgets，操作权限、问答、取消、会话和关闭对话；全部通过 |
| WSLg 实际显示窗口 | DISPLAY=:0、WAYLAND_DISPLAY=wayland-0，实际 Qt 平台 wayland；窗口可见，权限卡片显示，正常关闭且线程结束 |
| 实际系统托盘 | QSystemTrayIcon.isSystemTrayAvailable() 返回 False，没有声称真实托盘验收 |
| 模拟托盘 | FakeTray 验证存在、隐藏、待处理标记、恢复、消失后恢复窗口；这属于策略自动化 |
| 用户完整人工验收 | 待按 deskmate-desktop.md 步骤完成 |
| 原生 Windows Python/托盘 | 未运行 |

实际 WSLg 冒烟使用本地忽略目录 `.r1-verification/r3_display.py`，默认显示平台，未设置 offscreen：

```bash
PYTHONPATH=. python .r1-verification/r3_display.py
```

它创建同一个 DesktopApplication/Controller、发送演示请求、观察权限等待并保存 `.r1-verification/r3-desktop.png` 和 `r3-display.json`，再请求正常退出；实际结果是 `platform=wayland; tray_available=false; window_visible=true; state=waiting; demo=true`。截图经过查看，中文、工具过程和权限卡片可见。正常启动逻辑没有设置 QT_QPA_PLATFORM。

### 覆盖与限制

- 行为测试覆盖：线程/loop 所有权；批准、拒绝、过期与旧运行回复；配置/模型错误恢复；请求超时；四类问答 name 映射及不支持类型取消；高频合并/限额和关键工具事件顺序；隐藏不取消、恢复不重复执行；模型/工具/权限等待和初始化期间退出；重复退出、慢关闭提示和无线程遗留。
- 演示测试阻止真实 HOME 读取及 Python socket 连接，走同一 SessionService 路径；临时目录在完整关闭后删除，不全局修改 Path.home。MCP/Hooks/Skills/记忆/摘要/元数据查询在 demo 均关闭。
- 实际 WSLg 可见窗口不等于 Windows 原生托盘；offscreen 与 FakeTray 不能代替人工桌面验收。没有运行真实模型、外部 MCP/Hook、外部终端队友、打包与安装验证。
- 继承 R2 的进程内单会话、单消费者和无跨进程事务边界。展示缓存有界，R2 内部服务队列仍没有硬容量限制。关闭不回滚副作用，不支持关机/退出后的任务恢复。
- POSIX 修复仅覆盖工具拥有的新进程组；Windows 完整进程树回收、主动脱离该组的程序仍未保证。
- R3 代码、测试和文档留在工作区，HEAD 仍为 R2 SHA，未提交/推送；原 likecc 目录保持原 HEAD 和干净工作区。R4 未开始。

## DeskMate R3.1（2026-11-17）

### 实际基线、范围与环境

R3 已提交并推送至 `b1d44a1ae6e09f009ac01260712a5dc508e0fd7b`。本轮实际从该 HEAD、`feat/deskmate` 干净工作区开始；R2 为其祖先。没有适用 AGENTS.md。开发目录 `/mnt/d/ldj/03/DeskMate`，原 likecc 目录保持 `4a9b77d281646385bf48fd85b8a03c4d28bbee23` 和干净工作区。

WSL2 Ubuntu 24.04.4 / Linux `6.6.87.2-microsoft-standard-WSL2`；Conda cc，Python 3.11.16、PySide6 6.8.3，使用完整已安装 SDK，不使用导入占位。没有依赖升级、锁文件重生成、真实 Provider 调用或凭据修改。

下列命令在 WSL 中先激活环境：

```bash
source /home/ldj/anaconda3/etc/profile.d/conda.sh
conda activate cc
cd /mnt/d/ldj/03/DeskMate
```

### 基线与先失败后通过

1. 修改前完整基线：

   ```bash
   PYTHONUTF8=1 QT_QPA_PLATFORM=offscreen python -m pytest -q --tb=short \
     -o cache_dir=/tmp/deskmate-r31-pytest-cache
   ```

   **800 passed，0 failed，0 skipped，48.52 秒**。是本轮实际重新执行，不是复制上轮数字。

2. 只增加测试，尚未修改业务代码时：

   ```bash
   PYTHONUTF8=1 QT_QPA_PLATFORM=offscreen python -m pytest -q --tb=short \
     -o cache_dir=/tmp/deskmate-r31-pytest-cache \
     tests/test_desktop_wait_state.py tests/test_desktop_launch.py
   ```

   **5 failed，0 passed，5.07 秒**。权限/问答两例在下一模型调用已经阻塞时仍为 waiting/pending=[]；launch 构造失败、exec 抛错和提前返回三例均留下实际后台线程。测试 finally 随后关闭自己创建的控制器，没有遗留故障注入线程。

3. 最小修复后重跑上述五例：**5 passed，3.99 秒**。没有删除测试、跳过失败或放宽原断言。

4. 补齐交错、部分初始化和清理异常后：

   ```bash
   PYTHONUTF8=1 QT_QPA_PLATFORM=offscreen python -m pytest -q --tb=short \
     -o cache_dir=/tmp/deskmate-r31-pytest-cache \
     tests/test_desktop_wait_state.py tests/test_desktop_launch.py \
     tests/test_desktop_controller.py tests/test_desktop_window.py tests/test_desktop_lifecycle.py
   ```

   **41 passed，0 failed，0 skipped，24.08 秒**。更早的扩展集合曾为 38 passed 和 39 passed；以最终完整集合为准。

### 最终实际回归及其他检查

```bash
PYTHONUTF8=1 QT_QPA_PLATFORM=offscreen python -m pytest -q --tb=short \
  -o cache_dir=/tmp/deskmate-r31-pytest-cache > /tmp/deskmate-r31-final.log 2>&1
PYTHONUTF8=1 python tests/verify_subagent.py > /tmp/deskmate-r31-subagent.log 2>&1
python -m compileall -q likecc
python -m likecc --help
python -m likecc.desktop --help
uv lock --check --offline --default-index https://pypi.org/simple
git diff --check
```

- **820 passed，0 failed，0 skipped，51.21 秒**；比本轮 800 项基线新增 20 项参数展开用例（状态 9、launch 11）。耗时只记录本次运行，不是性能基准。
- 独立 SubAgent **90/90**；编译、两个帮助入口、离线锁一致性和差异检查均退出 0。没有更新锁文件或绕过 GUI 专项。
- 正常 GUI 异步退出、原有慢关闭不强退、无托盘降级和 POSIX 自有进程组回收的原测试均保留通过。
- 收尾提取桌面/学习文档中的 17 段 Bash 命令分别执行 `bash -n`，语法检查通过；只解析、不执行，未因此读取真实配置或发起模型调用。

### 新增用例的证据类型

| 类型 | 使用条件 | 证明范围 |
| --- | --- | --- |
| 实际控制器/服务＋fake client | 完整项目 SDK，权限和问答超时，下一模型调用停在同步屏障 | 无写入、pending 清理、running 状态、迟到回复拒绝、取消后继续输入 |
| 线事件注入 | 同一实际后台 loop 内投影旧 session/run、无关 tool、延迟结果及保护状态 | 关联清理和不覆盖 cancelling/closing/终态；不表示已支持并发审批 |
| Qt 控制流故障注入 | 实际 launch、Qt 对象和工作线程，替换构造器/exec 或信号注册 | 失败/提前返回后 worker、client、会话文件关闭，原异常和信号恢复 |
| 实际 Qt offscreen exec | 真正运行 Qt 主循环、通过异步 request_exit 正常结束 | 兜底等待不在活跃 Qt 循环内执行，重复关闭安全 |
| 有限等待超时/异常注入 | 人工屏障保持 Runtime 关闭不完成，或在收尾注入异常/KeyboardInterrupt | 报告未完成清理、不强杀、不掩盖原始启动异常；测试释放屏障后确认线程退出 |

### 本轮有限可见窗口观察

使用忽略目录 `.r1-verification/r31_visible.py` 做本机启动/显示/退出检查：

```bash
PYTHONPATH=. python .r1-verification/r31_visible.py
```

脚本使用同一个 launch、DesktopApplication 和 Controller，只用本进程的构造器观察包装安排截图和正常关闭；不自动点击、不发送任务、不调用真实 Provider。若继承 offscreen/minimal，只在该脚本进程移除变量，正常平台自动选择。

实际输出：**platform=wayland，visible=True，state=idle，demo=True，tray_available=False，exit_code=0，worker_alive_after_return=False**。截图 `.r1-verification/r31-visible.png` 已查看，中文离线标识和临时工作区可见；脱敏元数据在同目录 `r31-visible.json`。这些原始本机文件被 Git 忽略，不纳入源码提交。

这只证明本机可见窗口启动与退出，不是完整人工验收。本轮没有替用户点击验收清单，也没有用 fake client 声称真实模型可用。

### 人工验收与真实服务状态

[桌面说明的 R3.1 清单](deskmate-desktop.md) 已提供：可见启动命令（与 offscreen 自动化分开）、本次 PID/线程检查、拒绝/批准文件验证、问答、取消、恢复、无托盘找回、短超时观察，以及独立公开样例工作区的真实 Provider 最多四次提交方案。

| 项目 | 本轮状态 |
| --- | --- |
| 代码修复与自动化 | 完成，上述实际回归通过 |
| WSLg 窗口启动/显示/退出观察 | 本轮已执行，Wayland；只有限观察 |
| 用户完整 demo 点击清单、最小化找回与超时人工观察 | 通过，2026-11-17 用户逐项执行确认；详见下方人工补记 |
| 首个真实 Provider / 文件结果 | DeepSeek 指定冒烟通过：真实响应、读取、获批写入、继续对话、退出重开恢复及最终清理 |
| 真实托盘、原生 Windows、外部 MCP/Hook、分发安装 | 未验收 |

真实配置只提供按已知层级的脱敏检查步骤，不遍历个人目录寻找凭据，不打印/复制 Key。用户应记录 Provider 来自用户级还是验收工作区项目/本地覆盖；没有可解析配置时停止，不盲目复制含凭据文件。

当时建议以 A（WSL2/WSLg 可见窗口＋无托盘降级）作为主验收范围，将 B（真实托盘/Windows/安装）作为后续兼容性验证。A 的离线人工与 DeepSeek 指定冒烟随后通过，Windows 原生离线托盘也在后续阶段通过。下方保留各阶段的检查与待确认状态，当前结果以文末最新汇总为准。

本轮不暂存、不提交、不推送，HEAD 仍为 R3 SHA；原 likecc 目录未修改。输入清空和全量重绘等体验事项仅记入路线，不扩大修复范围。

### 用户执行的离线人工验收补记（2026-11-17）

执行者为用户，在本聊天逐步操作实际 WSLg 窗口并反馈；Codex 提供命令和检查点，没有自动点击。以下结果以用户反馈为依据，超时两项另有用户提供的截图，不将其写成 Codex 亲自操作或真实模型调用。

| 检查 | 用户确认的实际结果 |
| --- | --- |
| 离线启动 | 可见窗口显示“离线演示 · 无模型网络请求”、就绪及 `/tmp` 临时工作区；后续截图显示 `offline-demo / fake` |
| 拒绝首次写入 | 点击拒绝后出现问答；目录存在，`demo.txt` 未创建 |
| 新建后批准 | 新会话正常，批准后文件存在，实际内容为 `DeskMate R3 demo` |
| 问答输出 | 字段正确，最终回答只出现一次，回到就绪 |
| 取消与重用 | 进入 DemoWait 后取消，卡片清空且输入可用；同会话新任务正常完成，仅新增一次最终回答 |
| 新建/恢复 | 恢复到原会话，历史正确，无新卡片；恢复前后文件哈希、修改时间和大小均未变化 |
| 无托盘取消关闭 | 出现无托盘对话框，取消关闭后窗口、会话正常 |
| 无托盘最小化 | 最小化后所记录 PID 有线程记录，从任务栏/窗口切换找回后会话正常 |
| 正常演示退出 | 用户执行仅针对本次 PID 的检查，反馈退出码 0、进程及线程退出、临时工作区清理 |
| 5 秒自然超时 | 新临时工作区启动；不操作卡片后，截图出现写入拒绝、问答超时和 completed；用户确认卡片消失、输入可用、文件未创建 |
| 超时后再次运行 | 同会话新消息正常运行，截图显示第二轮 completed、顶部就绪，无遗留卡片 |
| 短超时演示退出 | 用户再次执行本次 PID 检查，确认退出码 0、进程及线程退出、临时工作区清理 |

用户使用桌面说明中的可见窗口命令及 `DesktopOptions(demo=True, permission_timeout=5)`，文件检查先验证目录存在，再判断文件；恢复检查使用 `sha256sum` 和 `stat -c '%y %s'`。退出检查先以 `kill -0` 最多观察约 10 秒（只探测、不发终止信号），随后 `wait` 读取退出码并检查临时目录。没有强杀线程或批量结束进程。

截图只含离线测试文本、临时路径及测试会话编号，保存在 Git 忽略目录：`.r1-verification/r31-manual-timeout-completed.png`、`.r1-verification/r31-manual-timeout-reuse.png`；不纳入源码提交。截图确认最终收尾，不代表逐帧观察了权限超时至下一模型调用之间的 running；该中间状态仍由前述屏障回归验证。也不把历史工具展示及文件时间比较单独当成所有工具调用次数的证明，调用契约由自动化补充。

本次离线补记只更新文档与忽略的本地截图，没有修改业务代码，也没有重跑 pytest。前述 820 passed、SubAgent 90/90 是 R3.1 修复阶段已实际执行的回归记录。截至该离线检查时点，尚未进行真实 Provider 验收；后续用户授权的真实验收单独记录在下文，不以 fake/offscreen 结果替代。

### 真实 Provider / 托盘交互验收：预检查（2026-11-17）

本次仍在 `feat/deskmate`、R3 HEAD `b1d44a1ae6e09f009ac01260712a5dc508e0fd7b` 上保留 R3.1 未提交修改，未暂存或推送。以下是新的实际预检查，不是重新运行完整回归，也不是模型连接验收。

| 检查 | 实际结果与边界 |
| --- | --- |
| 指定运行环境 | `/home/ldj/anaconda3/envs/cc/bin/python`，3.11.16；PySide6 6.8.3；WSL2 内核 6.6.87.2 |
| 桌面入口 | `python -m likecc.desktop --help` 退出 0，真实启动参数为 `--work-dir` / `--provider`；扩展开关默认关闭 |
| 标准配置层 | WSL 用户级、DeskMate 项目级/本地覆盖及新验收目录配置均未找到；`load_config` 返回 ConfigError，未输出原始错误或 YAML |
| 凭据存在性 | 只输出两个受支持环境变量是否存在，本次工具进程中均为 False；没有输出值，没有推断其他终端状态 |
| 隔离样例 | 已创建 `/tmp/deskmate-r31-provider-cdax32uf/project_notes.md`，内容为用户指定公开项目说明，258 字节 |
| 当前权限预判 | 复用桌面 DEFAULT 及实际规则，ReadFile(project_notes.md)=allow，WriteFile(summary.md)=ask；尚未执行工具或修改规则 |
| 已知用户指令/权限文件 | `~/.likecc/LIKECC.md` 与 `~/.likecc/permissions.yaml` 均不存在；只检测这两个确定路径，没有遍历用户目录 |
| 真实托盘探测 | 使用正常 WSLg QApplication，Wayland，DISPLAY/WAYLAND_DISPLAY 存在，`QSystemTrayIcon.isSystemTrayAvailable()` 为 False；未用 offscreen 或模拟值替代 |
| Windows 只读元数据 | PATH 中 Python 为 D:\anaconda3\python.exe，3.12.7，PySide6 未安装；未安装软件、未运行原生 GUI，其他环境未枚举 |
| 真实 Provider | 未选定 Provider/模型，无服务请求；静态配置未就绪，不能判为认证失败或通过 |

实际执行包括激活 cc 后的环境元数据检查、桌面 `--help`、无窗口 QApplication 托盘探测，以及 `PYTHONPATH=. python .r1-verification/r31_provider_preflight.py`。本地脚本只创建公开样例，读取规定配置位置，输出白名单元数据/布尔值，不创建 client 或调用服务；脱敏结果保存到忽略目录 `.r1-verification/r31-provider-preflight.json`。另在 Windows 当前 Python 中用 importlib 元数据检测 PySide6，不导入模型 client。业务代码未改变。

下一步等待用户确认服务商/模型或已有配置路径（不接收 Key），然后逐项完成配置静态复核、费用与请求次数确认、真实窗口启动、集成文件任务、输出核验、继续发送及重开恢复。每个用户操作确认后再记录结果。当前预检查不把未来步骤标为通过。

随后用户确认尚无配置文件、拟使用 DeepSeek 官方 API。已只读查阅 [官方接入说明](https://api-docs.deepseek.com/)、[Anthropic 兼容说明](https://api-docs.deepseek.com/guides/anthropic_api/) 和 [当前价格页](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)，没有运行示例或请求模型。密钥管理页需要用户自行登录，未尝试接管账号；当前等待用户准备 Key，仅接收完成状态，不接收密钥。DeepSeek 已选定，模型与本地配置尚未完成，认证/工具调用/恢复会话仍待实际验收。

注意：现有文件沙箱还允许系统临时目录，Bash 为独立命令权限。真实启动前应在验收工作区设置进程级 TMPDIR 子目录和仅拒绝 Bash 的项目规则，保留 ReadFile/WriteFile 的既有审批判定；不宣称仅靠提示词完成强隔离。不自动批准额外工具请求。原生托盘及 Windows/安装清单已补入桌面说明，全部待实际验收。

### DeepSeek 无密钥配置与费用确认准备

用户确认“Key 已准备好”；没有发送密钥到聊天。执行 `PYTHONPATH=. python .r1-verification/r31_provider_setup.py`（cc 环境，退出 0），只在上述独立目录创建 `.likecc/config.yaml`、`.likecc/permissions.yaml` 与 `.tmp`。脚本先检查文件不存在，使用独占创建、不覆盖已有配置；目录权限 0700、两个配置文件 0600。api_key 为空，后续仅在用户终端为 GUI 子进程设置 ANTHROPIC_API_KEY，不将真实 Key 写入文件。

实际配置来源为**验收项目级**，Provider=deepseek-r31，模型=deepseek-flash，协议=anthropic，地址为 DeepSeek 官方兼容入口，thinking=True，context_window=1000000，每请求 max_output_tokens=4096。静态协议选择依据为现有 Anthropic 流解析/序列化保留思考块，对应官方多轮工具要求；不能据此声明服务可用。

配置后不执行工具，仅调用实际权限检查器：ReadFile(project_notes.md)=allow、WriteFile(summary.md)=ask、工作区外文件=deny、Bash(pwd)=deny。该进程将 TMPDIR 指向工作区 `.tmp`，真实 GUI 尚未启动，启动时必须复用此设置。没有更改 DEFAULT 或增加放行规则。Anthropic SDK 构造参数的默认 max_retries 静态检查为 2；未构造 client，没有服务请求。

下一步只等待用户的单任务费用确认。预计读取样例→生成摘要→最终输出约 3–6 次模型请求，实际轮次和重试可能增加；[官方 Flash 价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/) 的高峰缓存未命中输入/输出为 2/8 元每百万 tokens。以累计 5 万输入和 1 万输出为例约 0.18 元，仅为计费示例，不是上限或实际扣费。费用尚未获确认，真实 Provider 仍为待验收。

脱敏配置/权限结果位于忽略目录 `.r1-verification/r31-provider-setup.json`；不含 Key。本次未修改业务代码、未重跑 pytest，未暂存、提交或推送。

用户随后明确回复“同意本次单任务验收，不限制费用”，记录为本次摘要任务的费用授权；不扩展为新任务或无限重试。准备 `.r1-verification/r31_deepseek_launch.sh` 供用户在 WSL Bash 中 source，安全隐藏输入 Key、仅传给真实 GUI 子进程，保留父 shell 的 PID/wait 关系。脚本不替用户发送任务、不记录 Key，启动前复核官方地址、空密钥配置与实际权限。Bash 语法检查与两段嵌入 Python 的 AST 解析均通过，没有执行启动脚本来代替用户输入。

用户随后执行脚本并确认真实窗口正常，模式、Provider/模型和工作区均一致。读取忽略目录的启动元数据后，仅用 kill(pid, 0) 确认记录的进程 2021545 存在，没有读取进程环境或 Key。公开样例存在、summary.md 尚不存在，源文件 SHA256 为 `be8167dd45cd5110cd494b558b51cfb7d4234b3c9b97899f1113e4333023bbe9`。这些证明真实入口已装配，不证明认证或模型调用成功。

下一步指导用户提交一次已授权的集成任务，并先停在 WriteFile(summary.md) 审批处，核对 ReadFile 结果与写入路径。模型请求、审批、文件结果、继续发送和重开恢复仍待后续逐项确认；不提前标记通过。

### 首次真实任务：读取成功，写入尚未触发

用户提交集成任务后反馈没有卡片、模型给出拟写摘要并询问“是否批准写入 summary.md？”，当前回合 completed。截图为真实模式、deepseek-r31 / deepseek-flash。随后运行只读脚本 `.r1-verification/r31_provider_audit.py`，仅分析公开验收目录，实际结果：

- 会话 `session_20261117_231313_nnq5.jsonl` 有两条 assistant 记录；这不是含 SDK 重试的 API 请求总数。
- ReadFile 调用 1 次，目标 project_notes.md；结果 is_error=False，包含项目名、R1–R3 和下一阶段事实。
- 没有 WriteFile 调用，summary.md 不存在；project_notes.md SHA256 与发送前一致。
- 最后一条普通 assistant 文本包含 summary.md 与批准询问；没有证据表明绕过了权限或执行了写入。

因此真实模型响应和读取工具链已获得实际证据，但写入审批/落盘尚未验收。权限卡片由实际工具请求触发，普通文字询问不会生成卡片；没有为该现象修改业务代码。下一用户步骤为继续同一任务，确认草稿内容并要求实际调用 WriteFile，然后先核对审批卡片。不是重新发送整个任务，也不另行发起其他任务。

用户公开测试截图保存在忽略目录 `.r1-verification/r31-provider-text-approval.png`。实际工具记录比单看“completed”或草稿内容更能区分“当前回合结束”与“用户要求的文件已生成”。Provider 总体验收仍待写入、文件核查及重开恢复完成。

### 真实写入审批与文件核查通过

用户在同一会话发送草稿确认后，提供截图：真实模式等待回复，工具 WriteFile、操作 summary.md。随后点击“本次允许”，截图显示 Successfully wrote to summary.md、一次最终回复“已写入 summary.md”、completed，顶部回到就绪。未修改审批策略或业务代码。

再次执行只读 `r31_provider_audit.py` 并读取实际 summary.md：

- project_notes.md SHA256 仍为 `be8167dd45cd5110cd494b558b51cfb7d4234b3c9b97899f1113e4333023bbe9`，源文件未改变。
- summary.md 已存在，为 257 字节，SHA256 为 `fa4e5446cca188c0fdc6ead4b2f576f76df6c92dc837a6915e926a12351ee156`；内容与 WriteFile 参数完全一致。
- 实际 Markdown 包含 DeskMate 测试项目、R1 运行时重构完成、R2 执行与会话服务完成、R3 桌面界面和后台生命周期完成、下一阶段增加个人事务处理功能，人工读取核对与源文件事实一致。
- 同一会话记录中 ReadFile / WriteFile 各一次，各有成功结果，没有重复工具调用记录。共四条 assistant 记录，不等于包含 SDK 重试的实际 API 请求总数，也没有据此虚构扣费金额。

审批与完成截图分别保存于忽略目录 `.r1-verification/r31-provider-write-permission.png`、`r31-provider-write-completed.png`，只含公开验收内容。下一用户步骤为一次无工具的继续对话检查（会有新的模型响应计费），然后真正退出、重启并恢复会话；这些结果仍待确认。真实模式工作区不归 demo TemporaryDirectory 所有，退出后应保留文件和会话供恢复；检查进程退出时不能要求删除该目录。

### 继续对话通过，已保存重开恢复基线

用户确认继续消息的实际结果与预期一致：DESKMATE_R31_CONTINUE_OK 单次回复、无工具/卡片、就绪且输入可用。再次只读审计确认标记记录恰好一次，assistant 记录增加至五条，ReadFile/WriteFile 仍各一次，源文件和摘要哈希不变，没有新增文件工具执行。没有据此声称实际计费请求数或扣费金额。

为重开恢复保存 `.r1-verification/r31-provider-resume-baseline.json`（忽略目录，不含 Key）：会话 session_20261117_231313_nnq5、两文件的哈希/大小/mtime_ns、工具计数、assistant 数及标记次数。基线独占检查后创建，未覆盖已有文件。当前下一步为用户真正退出并在原终端 wait 读取退出码；进程退出、文件保留、重启及恢复均尚待确认，不提前打勾。

用户随后确认窗口正常关闭，原终端退出码 0。只读检查实际结果：旧记录 PID 2021545 的 /proc 项不存在；原会话 JSONL 文件存在；project_notes.md 与 summary.md 的哈希、mtime_ns、大小均与恢复基线完全相同。因此真实模式退出及文件/会话保留通过。下一步重新 source 本地启动脚本，在用户终端再次隐藏输入 Key，启动后再选择原会话恢复；目前不标记重启/恢复通过，也不发送新模型任务。

用户随后确认真实窗口重新启动并就绪，模型/工作区一致、当前为新空白会话。只读复核记录的新进程存在、原会话文件仍在、两文件全部基线字段一致。新空白会话是当前入口启动语义，不是历史丢失。下一用户步骤为下拉框选择 session_20261117_231313_nnq5 并点击恢复；历史显示、无新卡片及恢复后基线仍待确认，不提前标记恢复通过。

### 原会话恢复通过

用户点击恢复后确认原会话编号、历史正确，就绪且无新卡片。随后运行真实目录的只读审计并比较恢复基线：原会话 assistant 仍五条、DESKMATE_R31_CONTINUE_OK 仍一次，ReadFile/WriteFile 仍各一次且成功；两文件哈希、mtime_ns、大小全部一致。重启新建的 session_20261117_234747_6ftr 没有 assistant 或工具调用记录。没有重复写入或模型回复追加记录，源文件和摘要未被恢复过程改写。

因此本次 DeepSeek 指定功能链（真实模型→读取→权限批准→写入→继续对话→退出重开→恢复展示）通过。恢复后未再发新的模型任务，这不等于验证恢复后的所有思考模式续聊或所有 Provider。重启 GUI 的 PID 2064399 仍由用户持有，最后一步为用户退出并在原终端 wait；新进程消失和最终退出码仍待确认，不提前标为已清理。

### 最终清理与 A–D 结论（2026-11-18 收尾）

用户最后确认重启后的窗口 wait 返回 0；只读核查 PID 2064399 已消失，原会话存在，源文件及摘要的哈希、mtime_ns、大小仍与恢复前基线完全一致。第一次真实窗口 PID 2021545 此前也已消失，两次真实退出均为 0。本次只用了文件工具，没有 Shell/MCP 等外部子程序调用记录。实际项目配置 api_key 为空、权限 0600、官方服务器未变；不读取进程凭据。验收目录及公开会话保留，未删除数据。

最终再次用正常 WSLg QApplication 探测：platform=wayland，QSystemTrayIcon.isSystemTrayAvailable()=False。没有使用 offscreen 或模拟托盘值作为本次实际结果。

| 判断 | 最终结论 |
| --- | --- |
| A. 真实 Provider | 通过本次 DeepSeek 指定冒烟：deepseek-r31 / deepseek-flash / anthropic；读、批准写、真实文件、继续对话、退出重开恢复及最终清理均有实际证据 |
| B. 真实系统托盘 | 当前 WSLg 不具备条件，实际 False；跳过真实托盘验收，模拟测试不替代。后续原生桌面步骤见桌面说明 |
| C. 进入 R4 前置 | 当前 WSLg 无托盘支持范围内满足：两项修复、代码回归、离线人工和首个真实 Provider 冒烟已通过，没有本次范围内未解决的阻塞问题。可以建议进入 R4，本轮不启动 |
| D. 延后至 R8 | 真实托盘、原生 Windows 的 shell/路径/进程树/权限/Qt 兼容验证、干净环境安装、依赖与资源打包、分发和平台文档整合。依赖这些平台能力的后续工作仍须先验证 |

边界：未在恢复后另发模型请求，未验证所有 Provider/思考模式续聊、长期负载或生产数据；真实模式未额外执行备选的拒绝写入任务，拒绝行为的人工证据来自离线清单。实际账单未查询，0.18 元仅是调用前的计费示例，五条 assistant 记录不等于包含 SDK 重试的 API 请求数。没有把这些未测范围记为通过。

本次验收阶段只更新四份文档和忽略的本机辅助脚本/脱敏证据，没有新增业务代码修改或依赖升级，未重跑 pytest/SubAgent；820 passed / 90/90 保持其 R3.1 修复阶段实际执行的版本含义。辅助启动脚本通过 bash -n、两段嵌入 Python 通过 AST 解析；桌面 --help、实际 Qt 托盘探测、文件/会话审计及 git diff --check 均实际执行。用户每一步确认均有单独记录，没有自动点击或由工具额外发起模型任务。

最终仍在 feat/deskmate、R3 HEAD b1d44a1ae6e09f009ac01260712a5dc508e0fd7b 上保留 R3.1 修改，不暂存、不提交、不推送、不开始 R4，不修改原 likecc。

## R3.1 Windows 原生独立环境准备（2026-11-18，人工托盘待确认）

本节是前述 WSLg/真实 Provider 验收结束后的新增阶段。用户授权准备原生环境、继续离线真实托盘人工验收，保持 WSL cc、不调用真实模型、不提交或推送。

环境为 Windows 10 10.0.19045、原生 CPython 3.12.7（基础解释器 D:\anaconda3\python.exe），新建 `.venv-win-r31`，不共享 system site-packages。uv 0.11.8 使用现有锁文件安装 58 个包，包含 PySide6/Qt 6.8.3 和 Windows 条件依赖 pywin32 311。没有改动原有环境或源码/测试。以下环境变量仅用于本次命令进程：

```powershell
uv venv 'D:\ldj\03\DeskMate\.venv-win-r31' --python 'D:\anaconda3\python.exe' --no-python-downloads --no-managed-python --no-config --cache-dir 'D:\ldj\03\DeskMate\.r1-verification\uv-cache-win' --offline
$env:UV_PROJECT_ENVIRONMENT = 'D:\ldj\03\DeskMate\.venv-win-r31'
$env:UV_CACHE_DIR = 'D:\ldj\03\DeskMate\.r1-verification\uv-cache-win'
uv sync --locked --extra desktop --python 'D:\anaconda3\python.exe' --no-python-downloads --no-managed-python --default-index https://pypi.org/simple --no-config --no-progress
```

首次受限执行的下载重试被中止；独立 HTTPS 检查发现该执行环境 TLS 凭据不可用。本机获准执行的官方 PyPI HEAD 返回 200，随后相同锁定安装成功（本机重试设置 UV_HTTP_TIMEOUT=30、UV_HTTP_RETRIES=1）。保留 TLS 证书验证，没有切换不安全源或修改认证配置。

实际检查：

```powershell
& .\.venv-win-r31\Scripts\python.exe -X utf8 -m likecc.desktop --help
uv sync --check --locked --extra desktop --offline --no-config --default-index https://pypi.org/simple
uv pip check --python .venv-win-r31/Scripts/python.exe --offline --no-config
$env:PYTHONUTF8 = '1'
$env:QT_QPA_PLATFORM = 'offscreen'
& .\.venv-win-r31\Scripts\python.exe -m pytest -q --tb=short -o cache_dir=.r1-verification/pytest-cache-win tests/test_desktop_controller.py tests/test_desktop_window.py tests/test_desktop_lifecycle.py tests/test_desktop_wait_state.py tests/test_desktop_launch.py
```

- 前三项返回 0；sync 检查 58 个包并报告不会修改环境，pip check 报告依赖兼容。
- 原生桌面测试为 **39 passed、2 failed、4 warnings，71.62 秒**，退出码 1。日志 `.r1-verification/r31-windows-desktop-tests.log`。没有将失败计入通过，没有运行本机完整 pytest/SubAgent，也没有重跑 WSL 完整回归。
- 两项失败是 `test_gui_permission_question_hidden_resume_and_no_duplicate_execution[True/False]`，等待发送按钮启用超时。该测试在控制器构造前把所有 `socket.socket.connect` 替换为抛错函数；Windows ProactorEventLoop 初始化内部管道需要回环 socket，导致后台在开始业务前退出，并产生 coroutine 未 await / `_ssock` 不存在的清理警告。
- 用原生 `asyncio.new_event_loop()` 记录 connect 的实际调用栈，确认唯一连接为回环地址，路径为 `proactor_events._make_self_pipe → socket._fallback_socketpair → connect`。这是测试防联网钩子的跨平台兼容问题，尚未修复；没有为过测放开全部网络、改断言或更换产品事件循环。
- 独立运行未套该钩子的 `DesktopController(DesktopOptions(demo=True))`：idle、offline-demo / fake、临时工作区存在；request_close/wait_closed 后 worker 结束，工作区清理，全部断言通过。没有提交任务或创建真实模型 client。这支持继续人工离线检查，不代表全部 Windows 功能已通过。
- 在本机 Windows 桌面会话用独立 QApplication 探测（该进程显式 QT_QPA_PLATFORM=windows）：`platform=windows, tray_available=True, supports_messages=True`，返回 0。未使用模拟托盘，也未显示/点击验收图标；实际图标、菜单、任务中隐藏与退出仍待用户逐步确认。

安装前后 pyproject.toml SHA256 均为 `e6584c2385f159a503860b8b658bed703cb20c53f3ed264a9bc0d33698e9091c`，uv.lock 均为 `33073366b52085995b9b2ffe929eae1011b3e3a6001031324a55c7b24469f33b`。Git 检查使用单次 `-c safe.directory=D:/ldj/03/DeskMate` 处理沙箱账户所有权差异，不修改全局 Git 配置。仍为 feat/deskmate / R3 基线，已有 R3.1 修改保留，索引为空。独立环境和缓存被现有规则忽略。

本阶段仅新增环境、忽略的日志并更新文档，原 likecc、WSL cc、业务源码和测试文件均未修改。首个人工步骤及预期见桌面说明的 Windows 原生节；在用户反馈前不标记真实托盘人工通过。Windows Shell、路径/链接、子进程树以及安装包仍属于后续独立兼容验证。

## R3.1 改用 Windows Conda deskmate-win（2026-11-18）

用户指定使用 Windows Conda，并保留前节的 `.venv-win-r31` 和 WSL cc。开始时标准 Conda 环境目录中没有 deskmate-win；先 dry-run 核对计划，再创建 `C:\Users\28436\.conda\envs\deskmate-win`。本节为当前原生验收环境，前节历史结果不覆盖。

### 创建与锁定安装

Windows Conda 24.9.2，Python 3.12.7；PySide6/Qt 6.8.3。实际创建命令：

```powershell
& D:\anaconda3\Scripts\conda.exe create --name deskmate-win python=3.12.7 pip --no-default-packages --dry-run --yes --json
& D:\anaconda3\Scripts\conda.exe create --prefix 'C:\Users\28436\.conda\envs\deskmate-win' python=3.12.7 pip --no-default-packages --yes --json
```

两项返回 success=True；实际环境路径与计划一致。使用既有 Conda 源配置，没有修改全局源、凭据、Shell 初始化或执行策略。随后从现有 uv.lock 导出 requirements，再显式安装到该 Conda 解释器；没有使用 uv sync / uv pip sync / --exact 去重建或清理 Conda：

```powershell
$env:UV_CACHE_DIR = 'D:\ldj\03\DeskMate\.r1-verification\uv-cache-win'
uv export --locked --extra desktop --group dev --format requirements.txt --no-emit-project --output-file .r1-verification/r31-conda-win-requirements.txt --python D:\anaconda3\python.exe --offline --no-config --default-index https://pypi.org/simple
uv pip install --python 'C:\Users\28436\.conda\envs\deskmate-win\python.exe' --require-hashes --no-deps --requirement .r1-verification/r31-conda-win-requirements.txt --link-mode copy --no-python-downloads --no-config --default-index https://pypi.org/simple --no-progress
uv pip install --python 'C:\Users\28436\.conda\envs\deskmate-win\python.exe' --no-deps --editable . --link-mode copy --offline --no-config --no-progress
uv pip check --python 'C:\Users\28436\.conda\envs\deskmate-win\python.exe' --offline --no-config
```

依赖安装先尝试 --offline，因缓存缺少 annotated-types 的索引条目退出 1，未完成安装；随后使用官方 PyPI 补齐索引成功，仍保留锁定版本、--require-hashes 和 TLS 校验。没有因缓存不足改变依赖版本。安装了 57 个锁定第三方包，再 editable 安装 likecc；Conda 初始的 packaging 26.3 被项目锁定的 26.2 替换，只发生在新环境。最终依赖检查覆盖 61 个 Python 包并报告全部兼容。Conda 的解释器/运行库、pip/setuptools/wheel 以及 editable 构建工具不属于 uv.lock 的锁定范围。

### 新环境实际检查

```powershell
& D:\anaconda3\Scripts\conda.exe run --no-capture-output -n deskmate-win python -s -X utf8 .r1-verification/r31_conda_verify.py
& D:\anaconda3\Scripts\conda.exe run --no-capture-output -n deskmate-win python -s -X utf8 -m likecc.desktop --help
```

均返回 0。本机忽略目录的 verify 脚本核对 sys.prefix/conda-meta/history、源码路径，按当前平台 marker 逐项核对导出 requirements 的 57 个版本；site.ENABLE_USER_SITE=False，源码来自当前 DeskMate。实际离线控制器到达 idle，模型标识 offline-demo / fake；request_close/wait_closed 后线程结束、临时工作区已删除。结果记录于 `.r1-verification/r31-conda-preflight.json`。脚本不是项目发布入口，不读取真实 Provider 配置或发起模型请求。

另在本机桌面会话中，用该 Conda 环境的 QApplication 和 QSystemTrayIcon 实测：`platform=windows, tray_available=True, supports_messages=True`，退出 0。该探测进程显式 QT_QPA_PLATFORM=windows；没有伪造托盘值、显示人工验收图标或点击菜单。真实图标及各操作仍待用户确认。

### 桌面回归与未解决事项

首次实际命令：

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHONNOUSERSITE = '1'
$env:QT_QPA_PLATFORM = 'offscreen'
& D:\anaconda3\Scripts\conda.exe run --no-capture-output -n deskmate-win python -s -X utf8 -m pytest -q --tb=short -o cache_dir=.r1-verification/pytest-cache-conda-win tests/test_desktop_controller.py tests/test_desktop_window.py tests/test_desktop_lifecycle.py tests/test_desktop_wait_state.py tests/test_desktop_launch.py
```

结果为 **36 passed、3 failed、2 errors、4 warnings，101.04 秒**，退出 1。日志为 `.r1-verification/r31-conda-windows-desktop-tests.log`。

- 两项 errors：pytest 访问共享 `C:\Users\28436\AppData\Local\Temp\pytest-of-28436` 被拒绝，发生在 fixture 初始化；未删除旧目录或修改 ACL。
- 两项失败仍是 test_desktop_window 中 allow=True/False 的全局 socket.connect 防联网拦截与 Windows asyncio 自唤醒连接冲突，和前节相同。
- 另一次失败为 `test_slow_cleanup_keeps_gui_responsive_and_reports_timeout`，预期“尚未完成关闭”，实际显示“后端已接受：已接受”。源码复核发现提示覆盖竞态：application.poll 首次显示超时警告并设置 _shutdown_warned，之后 window.refresh 的新 command ACK 会重写同一 feedback；后续 poll 不再重写警告。该失败影响关闭耗时提示的可见性，不能归为 Conda 安装或 TEMP 权限问题；没有证据表明该次失败提前终止后台线程。

为排除临时目录权限问题，校验一个项目忽略目录下的新路径在预期根内、尚不存在，再给同一命令增加：

```text
--basetemp D:\ldj\03\DeskMate\.r1-verification\pytest-conda-win-986d6e0f81ac4c90a4e74a119befceb9
```

未跳过测试或更改断言。第二次结果为 **39 passed、2 failed、4 warnings，55.45 秒**，退出 1；剩余失败是上述两项 socket 钩子问题。日志 `.r1-verification/r31-conda-windows-desktop-isolated.log` 保留完整命令和实际临时目录。后续重跑应另选全新目录，不把已有验收数据作为 pytest basetemp。

关闭提示测试第二次通过不消除首轮已暴露的时序缺陷，仍列为待修复。未修改业务源码、测试钩子或产品事件循环；本阶段不扩展成 Windows 兼容改造。新环境已经可以进行分步离线窗口/托盘观察，但**不宣称原生回归全绿或完整 Windows 验收通过**。没有运行本机完整 pytest/SubAgent 或重跑 WSL 回归。

### 保留状态与下一人工步骤

pyproject.toml/uv.lock SHA256 与前节一致；旧 `.venv-win-r31` 的 58 个包名称/版本清单前后相同。没有操作 WSL cc、原 likecc 或修改 Windows 基础环境包。Git 仍为 feat/deskmate / R3 基线，原 R3.1 修改保留，索引为空；无提交、推送或 R4 开发。

本阶段只新增 Conda 环境、忽略的本机 requirements/脚本/结果及更新文档。人工下一步仅用 Conda 命令启动离线窗口并确认就绪及蓝底 D 托盘图标，命令见桌面说明最新 Conda 节。用户反馈前不标记该步完成，也不自动提交任务、关闭窗口或调用真实模型。

### Conda 原生人工第 1 步：窗口与真实托盘图标通过（2026-11-18）

用户随后明确反馈“窗口已正常就绪，D 托盘图标也出现了”。记录为用户实际执行并确认的离线可见窗口/真实托盘图标证据，不是 offscreen 或 tray_probe 模拟结果。没有据此认定菜单、隐藏恢复、任务不中断或退出清理已通过。

下一人工步骤只点击主窗口标题栏右上角 X。预期主窗口隐藏、D 图标继续存在、启动 PowerShell 命令仍未结束且未打印退出码；首次隐藏可能提示“DeskMate 继续运行”，通知未弹出本身不作为失败。暂不执行托盘恢复或退出，等待用户反馈。未自动点击、发消息或调用模型，原有测试兼容失败与提示竞态仍保持待处理。

### Conda 原生人工第 2 步：关闭窗口后隐藏到托盘通过（2026-11-18）

用户点击标题栏 X 后确认主窗口隐藏、D 图标保留、启动终端仍在运行。随后只读进程检查发现 deskmate-win 解释器仍有一个进程（PID `54464`）。据此记录关闭隐藏通过。

下一步从 D 图标右键菜单选择“显示 DeskMate”，观察原离线窗口是否恢复，是否仍为就绪，以及工作区和会话是否与隐藏前一致。恢复、任务中隐藏和真正退出仍待分别确认。

### Conda 原生人工第 3 步：从托盘恢复原窗口通过（2026-11-18）

用户确认从托盘恢复原窗口，仍为离线演示、状态就绪，工作区与会话均与隐藏前一致。只读进程检查确认同一个 deskmate-win 解释器进程 PID `54464` 仍在运行。

接下来逐步准备 `DemoWait`。当前操作只发送“R3.1 验收：运行中隐藏到托盘”，预期出现 `WriteFile` 权限卡片，目标为临时工作区内的 `demo.txt`。待用户确认卡片后继续。运行中隐藏和退出仍待验收。

### Conda 原生人工第 4 步：演示权限卡片出现（2026-11-18）

用户确认出现 WriteFile 权限卡片，并要求将剩余操作一次列出，自行连续执行后反馈。后续清单已写入桌面说明，依次为批准临时文件写入、问答进入 DemoWait、任务运行中隐藏和恢复、从托盘取消并恢复查看结果、同会话再次完成任务、从托盘真正退出。各项当前均待反馈。

只读复核当前进程 PID `54464`、解释器为 Windows Conda deskmate-win。未自动点击卡片或托盘，也未发起额外任务。本轮记录与检查没有改变代码或既有测试结果。

## R3.1 人工验收收尾汇总（2026-11-18，回归修复前）

### Windows 原生真实托盘人工清单通过

用户在 Windows 10 10.0.19045、Conda deskmate-win、Python 3.12.7、PySide6/Qt 6.8.3 中执行前述离线命令与清单，最后反馈各项操作均符合预期、退出码 0，并提供进程检查结果“验收通过：原 DeskMate 进程已退出”。

| 操作 | 实际反馈 |
| --- | --- |
| 启动与真实图标 | 窗口就绪，离线模式，D 托盘图标出现 |
| 空闲关闭隐藏 | 主窗口隐藏，D 图标保留，终端仍运行 |
| 托盘恢复 | 原窗口恢复，模式/就绪/工作区/会话保持一致 |
| 批准写入与问答 | WriteFile 卡片出现并允许，显示写入成功，问答选择等待取消 |
| 执行中隐藏与恢复 | DemoWait 隐藏约 10 秒再恢复，原任务仍在执行，已有历史保留 |
| 隐藏时托盘取消 | 从托盘取消后恢复，cancelled、就绪、卡片清空、输入可用 |
| 同会话继续 | 再次发送、允许写入、问答完成，正常 completed，最终回答仅新增一次 |
| 托盘真正退出 | D 图标消失，启动终端返回，退出码 0，原进程检查通过 |

以上 UI 结果来自用户执行确认。Codex 随后只读复核 PID 54464 已消失，并且未检测到 deskmate-win 解释器路径下的遗留 Python 进程。此次离线流程没有 Shell/MCP 子程序调用步骤，通用 Windows 子进程树清理仍需另行验证。没有额外发起真实模型调用。

本次人工窗口的工作区具体路径尚未提供，因此该目录删除情况列为待独立确认。`.r1-verification/r31-conda-preflight.json` 已有另一次独立控制器预检的线程关闭和临时目录删除通过记录，两项证据分别保留。

### R3.1 已通过范围与实际回归结果

| 范围 | 已有结果与执行阶段 |
| --- | --- |
| 原始两项边界修复 | 权限/问答超时清卡后恢复状态，launch 构造失败/exec 异常/提前返回的资源关闭兜底，已由故障注入和行为测试验证 |
| WSL cc 修复阶段自动化 | 最终完整 pytest 820 passed、0 failed、0 skipped，51.21 秒，SubAgent 90/90。桌面专项 41 passed，24.08 秒。保留 2026-11-17 实际运行含义 |
| WSLg 离线人工 | 拒绝/批准写入、问答、单次最终回答、取消/重用、恢复不重放、无托盘关闭/最小化找回、权限/问答超时收尾与正常退出均通过 |
| WSLg DeepSeek 指定冒烟 | 真实读取、写入审批、摘要落盘、继续对话、退出重开恢复展示，两次退出码 0。恢复后没有另发新模型任务 |
| Windows Conda 环境 | 57 个生效锁定第三方版本核对一致，61 个包依赖检查通过，入口帮助、独立控制器启动与关闭/临时清理通过 |
| Windows 真实托盘人工 | 上表离线清单全部通过，退出码 0，原进程已结束 |
| Windows 自动化首轮 | 36 passed、3 failed、2 errors、4 warnings，101.04 秒。包含共享 TEMP 权限问题和关闭提示覆盖失败 |
| Windows 自动化隔离目录复跑 | 39 passed、2 failed、4 warnings，55.45 秒。两项防联网钩子兼容失败仍未修复 |

### 仍需处理的问题与后续验证

1. **Windows 两项测试兼容失败。** `test_gui_permission_question_hidden_resume_and_no_duplicate_execution[True/False]` 全局拦截 socket.connect，阻断 asyncio 内部回环 socketpair 初始化。后续需保留外部联网拦截契约并允许所需内部通信，再重跑相关桌面测试。
2. **关闭耗时提示覆盖竞态。** application.poll 首次写警告并设置 _shutdown_warned，window.refresh 的新 command ACK 随后可能覆盖 feedback。首轮实际失败，复跑通过，仍需最小修复、确定性时序验证及相关回归。
3. **本次人工临时目录清理待确认。** 缺少实际工作区路径，当前仅确认退出码、进程退出和独立预检清理。共享 pytest TEMP 权限错误已通过全新隔离 basetemp 排除，原临时目录及 ACL 保留。
4. **后续平台与交付范围。** Windows Shell/POSIX 命令、路径/链接/权限、通用子进程树、Windows 真实 Provider、外部扩展集成、真实恢复后新模型调用、长期负载、DeskMate 干净安装和打包资源继续待验证。WSLg 会话托盘仍为 False，Windows 已有实际托盘通过证据。

### 本次文档收尾检查

本次更新 verification、desktop、roadmap、learning 四份文档，保留分阶段结果，并更新当前状态和未解决问题。实际执行 Git 状态/分支/HEAD/索引检查、进程退出检查、原 likecc 的只读状态检查、pyproject/uv.lock 哈希检查及 git diff --check。未重跑 pytest/SubAgent，各项计数沿用上述实际执行阶段。

当前仍为 feat/deskmate，HEAD `b1d44a1ae6e09f009ac01260712a5dc508e0fd7b`，索引为空，R3.1 修改继续留在工作区。原 likecc HEAD 为 `4a9b77d281646385bf48fd85b8a03c4d28bbee23` 且工作区干净。pyproject/uv.lock 哈希与环境准备前一致。保留 WSL cc、Windows deskmate-win 和 .venv-win-r31，本轮仅更新记录，未暂存、提交或推送，R4 保持规划状态。

## R3.1 Windows 收尾修复与双环境复测（2026-11-18）

### 复现与修复

先在原实现上加固 `test_slow_cleanup_keeps_gui_responsive_and_reports_timeout`。测试控制应用时钟，先阻止后台分派关闭命令，显示超过 15 秒的警告，再放行关闭确认，保持实际清理挂起。Windows 和 WSL 都观察到警告被“后端已接受：已接受”覆盖。Windows 修复前完整回归还复现了两项防联网测试失败，以及三个此前已记录的 POSIX 命令兼容失败。

- `tests/test_desktop_window.py` 将防联网例外限定到 `socketpair()` 调用期间的数字回环地址。普通 `connect` 和 `connect_ex` 仍被拦截。新增契约用例在真实 socketpair 中收发字节，并验证普通回环和外部地址都被拒绝。原有离线流程用例继续覆盖批准、拒绝、会话恢复以及无被拦截的连接尝试。
- `DesktopApplication` 自发出退出请求起拥有关闭提示的优先级。`ChatWindow.refresh()` 仍处理命令确认，关闭期间保留应用的提示。托盘消失依然会恢复窗口，也保留关闭提示。测试按固定顺序检查迟到确认和托盘消失，确认后台仍在清理，随后释放屏障并验证退出回调只调用一次。

### 实际命令

两边都使用 offscreen Qt，设定 `PYTHONUTF8=1`、`PYTHONNOUSERSITE=1` 和 `PYTHONDONTWRITEBYTECODE=1`，每次使用新建测试根目录并为 pytest 指定独立 `--basetemp` 与缓存。测试进程不继承常见的模型凭据变量。

Windows 在仓库根目录用 PowerShell 执行下列命令。`$runRoot` 为每次新建的本机忽略目录，专项调用传入五个桌面模块，完整回归省去文件参数。

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
$env:PYTHONUTF8 = '1'
$env:PYTHONNOUSERSITE = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
Remove-Item Env:OPENAI_API_KEY,Env:ANTHROPIC_API_KEY,Env:ANTHROPIC_AUTH_TOKEN,Env:DEEPSEEK_API_KEY -ErrorAction SilentlyContinue
$runRoot = (New-Item -ItemType Directory -Path (Join-Path (Resolve-Path .r1-verification) ('r31-win-' + [guid]::NewGuid().ToString('N')))).FullName
$desktopTests = @('tests/test_desktop_controller.py', 'tests/test_desktop_window.py',
    'tests/test_desktop_lifecycle.py', 'tests/test_desktop_wait_state.py', 'tests/test_desktop_launch.py')
& D:\anaconda3\Scripts\conda.exe run --no-capture-output -n deskmate-win python -s -m pytest -q --tb=short `
    --basetemp (Join-Path $runRoot 'tmp') -o "cache_dir=$runRoot/cache" @desktopTests
```

WSL 用以下命令执行专项。完整回归省去最后五个文件参数。修复前单项复现只传入 `tests/test_desktop_lifecycle.py::test_slow_cleanup_keeps_gui_responsive_and_reports_timeout`。

```bash
cd /mnt/d/ldj/03/DeskMate
source /home/ldj/anaconda3/etc/profile.d/conda.sh
conda activate cc
unset OPENAI_API_KEY ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN DEEPSEEK_API_KEY
run_dir=$(mktemp -d /tmp/deskmate-r31-wsl.XXXXXX)
PYTHONUTF8=1 PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen \
  python -m pytest -q --tb=short --basetemp "$run_dir/tmp" -o "cache_dir=$run_dir/cache" \
  tests/test_desktop_controller.py tests/test_desktop_window.py tests/test_desktop_lifecycle.py \
  tests/test_desktop_wait_state.py tests/test_desktop_launch.py
```

### 实际结果

| 环境与阶段 | 结果 | 日志目录 |
| --- | --- | --- |
| Windows deskmate-win 3.12.7，修复前完整 | 808 passed、6 failed、6 skipped、4 warnings，149.78 秒，退出 1 | `.r1-verification/r31-win-before-4c5ae70a78ed41d39f446876a841a9f4` |
| WSL cc 3.11.16，修复前关闭竞态单项 | 1 failed，8.33 秒，退出 1 | `/tmp/deskmate-r31-wsl-before.IXPoAC` |
| Windows deskmate-win，修复后桌面专项 | 42 passed，51.49 秒，退出 0 | `.r1-verification/r31-win-related-a109eb17eb154e7ab2abb642eb3d7702` |
| WSL cc，修复后桌面专项 | 42 passed，25.97 秒，退出 0 | `/tmp/deskmate-r31-wsl-related.irWinn` |
| Windows deskmate-win，修复后完整 | 812 passed、3 failed、6 skipped，141.91 秒，退出 1 | `.r1-verification/r31-win-full-5c57396dbeea4ca5aea7785755d00a84` |
| WSL cc，修复后完整 | 821 passed，48.09 秒，退出 0 | `/tmp/deskmate-r31-wsl-full.iTbByU` |

该阶段 Windows 完整回归的剩余失败与修复前基线中的三项非桌面失败一致。六项原有跳过数量不变。下列三项随后在本文最后一节继续处理。

- `tests/test_document_runtime.py::test_six_real_tools_complete_a_file_workflow` 的 Bash 步骤在 Windows 默认 shell 返回文件名、目录名或卷标语法错误。
- `tests/test_worktree.py::TestWorktreeManager::test_relative_file_and_bash_tools_follow_worktree_cwd` 与 `tests/test_worktree.py::TestWorktreeManager::test_concurrent_agents_with_shared_tools_keep_work_dirs_isolated` 的 `pwd` 不能由 Windows 默认 shell 执行。

本次补丁通过上述离线自动化验证。真实托盘及 DeepSeek 的人工结果沿用前述实际验收，未重跑人工流程、SubAgent 脚本或真实模型调用。此前人工临时目录删除仍缺少路径；Windows 路径/权限、通用子进程树、真实 Provider、长期稳定性及安装打包仍是后续范围。保留原环境、原 likecc 工作区与 feat/deskmate 上的未暂存修改，R4 保持计划状态。

## R3.1 Windows Shell 集成回归（2026-11-18）

在 Windows Conda deskmate-win（Python 3.12.7）中先重跑下面三个测试，全部复现。用同一解释器在带空格的临时工作目录直接调用 `asyncio.create_subprocess_shell`，确认 `%COMSPEC%` 指向 `cmd.exe`。`pwd` 退出 1，原先用 `shlex.quote()` 构造的 Python 命令也退出 1，报告文件名、目录名或卷标语法错误。裸 `cd` 输出实际工作目录，按 Windows 参数规则构造的 Python 校验打印 `checked`，两者均退出 0。

三项失败来自集成测试传给原生 Shell 的输入。Worktree 测试在 Windows 传 `cd`，在 POSIX 保留 `pwd`，并比较完整目录路径。文件流程测试在 Windows 用 `subprocess.list2cmdline()` 拼接固定的 Python 校验参数，POSIX 用 `shlex.join()`。Python 子进程通过相对路径读取被编辑的 `sample.py`，因此还验证了工具子进程的工作目录。两个测试文件继续走真实 `Bash` 工具，验证文件内容与并发工作目录隔离。生产 Shell 选择、工作目录传递和 POSIX 进程组清理保持原实现。

Windows 测试继续使用隔离的 `--basetemp` 和缓存、offscreen Qt，并按上节方式清除测试进程中的常见模型凭据变量。修复前运行这三个选择器。

```text
tests/test_document_runtime.py::test_six_real_tools_complete_a_file_workflow
tests/test_worktree.py::TestWorktreeManager::test_relative_file_and_bash_tools_follow_worktree_cwd
tests/test_worktree.py::TestWorktreeManager::test_concurrent_agents_with_shared_tools_keep_work_dirs_isolated
```

修复后 Windows 在仓库根目录执行以下相关测试。完整回归省去文件参数，每次新建独立 `$runRoot`。

```powershell
& D:\anaconda3\Scripts\conda.exe run --no-capture-output -n deskmate-win python -s -m pytest -q -rs --tb=short `
  --basetemp (Join-Path $runRoot 'tmp') -o "cache_dir=$runRoot/cache" `
  tests/test_document_runtime.py tests/test_worktree.py tests/test_bash_process_group.py tests/test_execution_contract.py
```

WSL 在 `/mnt/d/ldj/03/DeskMate` 激活已有 `cc`（Python 3.11.16），用同样的四个测试文件和 `python -m pytest -q -rs --tb=short` 运行相关测试。测试和缓存目录放在新建的 `/tmp` 子目录下。

| 环境与阶段 | 实际结果 | 日志目录 |
| --- | --- | --- |
| Windows，修复前三项 | 3 failed，7.71 秒，退出 1 | `.r1-verification/r31-win-shell-before-55e17f92337d46039ca1aeff5e011a9a` |
| Windows deskmate-win，修复后相关测试 | 87 passed、5 skipped，70.14 秒，退出 0 | `.r1-verification/r31-win-shell-related-157b1e88f7234129a432ede9ffd6b2b7` |
| Windows deskmate-win，修复后完整回归 | 815 passed、0 failed、6 skipped，350.14 秒，退出 0 | `.r1-verification/r31-win-shell-full-907bf2554e0d468db7964e8d48771d40` |
| WSL cc，修复后相关测试 | 92 passed，10.22 秒，退出 0 | `/tmp/deskmate-r31-wsl-shell-related.0IIzAa` |

Windows 完整回归的三个既有失败全部通过。六项跳过沿用既有测试条件，其中五项依赖 POSIX 进程组，一项需要 Windows 本机缺少的符号链接测试目标文件。WSL 相关测试包含实际 `pwd`、文件流程和 POSIX 进程组清理，92 项全部执行。上节的 WSL 821 passed 仍是上一阶段的完整回归记录。

本轮的 Windows 验证覆盖选定的原生 Shell 工作区和文件流程。其他 POSIX 命令在 Windows 的可用性、通用子进程树清理及安装打包继续作为后续范围。使用已有 Windows Conda 和 WSL cc，测试跑离线脚本及临时文件。原 LikeCC 工作区复核干净，改动保留在 feat/deskmate 工作区，R4 仍处于规划阶段。

## R4 资料整理验证（2026-11-18）

工作区 `D:\ldj\03\DeskMate`，分支 `feat/deskmate`，起点 `19e5d6d74c8413b71088e4dea3be538da3b05151`。环境为 WSL2 Ubuntu 的 `cc` / Python 3.11.16，以及原生 Windows 10 的 `deskmate-win` / Python 3.12.7。两侧使用已有 PySide6 6.8.3、HTTPX 0.28.1 和锁定依赖。开始时有三份用户提供的未跟踪文档，保留其中两份原内容，目标规格仅更新完成状态。

| 阶段 | 实际结果 |
| --- | --- |
| R4-0 修复前定向复现 | `test_stale_idle_send_preserves_rejected_draft` 与 `test_demo_cleanup_failure_can_retry_without_losing_directory` 均失败，11.10 秒。前者输入为空，后者状态为 `starting` |
| R4-0 桌面回归 | WSL 46 passed，31.98 秒。后续补运行资源重试、独立回复额度与历史恢复断言，均纳入最终回归 |
| R4 相关回归 | WSL 190 passed，42.96 秒。Windows 188 passed、2 skipped，81.64 秒。退出码均为 0 |
| R4 最终 WSL 完整回归 | 853 passed、0 failed、0 skipped，58.56 秒，退出 0 |
| R4 最终 Windows 完整回归 | 847 passed、0 failed、6 skipped，129.14 秒，退出 0 |
| 独立检查 | WSL SubAgent 90/90，compileall、两个入口 `--help`、uv 锁检查、`git diff --check` 通过 |

Windows 全量的六项既有跳过包括五项 POSIX/WSL 进程组契约和一项缺少符号链接测试目标文件。相关测试子集包含其中两项。两侧都用 offscreen Qt 和隔离的 pytest 临时目录，移除测试进程中的常见模型凭据变量，没有真实模型调用。最终 WSL pytest 输出目录为 `/tmp/deskmate-r4-wsl-full.wTCa6k`，Windows 日志在 `.r1-verification/r4-win-full-f0d53aa9e5314f64b193f7bd12b0c612/pytest.log`。WSL `/tmp` 为临时位置。

### 实际运行方式

WSL 在 `/mnt/d/ldj/03/DeskMate` 激活 `cc`。独立的测试根用 `mktemp -d` 创建，执行：

```bash
export QT_QPA_PLATFORM=offscreen PYTHONUTF8=1 PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
unset OPENAI_API_KEY ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN DEEPSEEK_API_KEY
r=$(mktemp -d /tmp/deskmate-r4-wsl.XXXXXX)
python -m pytest -q -rs --tb=short --basetemp "$r/tmp" -o "cache_dir=$r/cache"
python tests/verify_subagent.py
PYTHONPYCACHEPREFIX="$r/pyc" python -m compileall -q likecc examples
python -m likecc --help
python -m likecc.desktop --help
uv lock --check --offline --default-index https://pypi.org/simple
git diff --check
```

Windows 从仓库根目录执行同一 pytest 参数。每次新建 `$d`，实际用 `.r1-verification` 下的独立目录，并移除与 WSL 相同的凭据变量。

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
$env:PYTHONUTF8 = '1'
$env:PYTHONNOUSERSITE = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
Remove-Item Env:OPENAI_API_KEY,Env:ANTHROPIC_API_KEY,Env:ANTHROPIC_AUTH_TOKEN,Env:DEEPSEEK_API_KEY -ErrorAction SilentlyContinue
$d = (New-Item -ItemType Directory -Path (Join-Path (Resolve-Path .r1-verification) ('r4-win-' + [guid]::NewGuid().ToString('N')))).FullName
& D:\anaconda3\Scripts\conda.exe run --no-capture-output -n deskmate-win python -s -m pytest -q -rs --tb=short --basetemp (Join-Path $d 'tmp') -o "cache_dir=$d/cache"
```

相关回归在相同 pytest 参数末尾加入以下文件：

```text
tests/test_materials_workflow.py tests/test_desktop_controller.py tests/test_desktop_window.py
tests/test_desktop_lifecycle.py tests/test_desktop_wait_state.py tests/test_desktop_launch.py
tests/test_permissions.py tests/test_session_service.py tests/test_execution_contract.py tests/test_document_runtime.py
```

### 可观察证据和待验收范围

- 离线 `python -m examples.deskmate_materials --work-dir <独立空目录>` 生成 `.r1-verification/r4-offline-Y0wZmt/outputs/study-plan.md`。三项来源为笔记、HTML、Markdown。结果为 `verified`，文件 SHA256 `caac8fa6479b1476afef5d2f5c578b30b327cc0a07f3f736d09d6d4869565009`。带 `--deny-write` 的运行没有产物。offscreen 测试使用真实控制器和假网页传输，核对隐藏时完成、恢复不重放，以及取消后流与传输退出。
- 公开浏览确认两份 IANA 样例为静态 HTML。再试生产 FetchWebPage 时，WSL 在 DNS 检查阶段返回非公网目标错误。系统解析结果核对确认 Windows 与 WSL 都对候选域名返回 `198.18.0.0/15` 保留地址，未向这些地址发起 GET。没有更改 DNS、代理或工具的拒绝策略。
- 独立公开验收工作区、未填密钥的 Provider 模板、源文件基线、非付费第一步及后续启动命令见 [R4 资料模式](deskmate-affairs.md)。真实 Provider 工具调用、可见 Qt 页面、真实结果总结质量和人工取消/恢复等待用户操作及本轮计费授权。锁文件、原 LikeCC 和暂存区保持原状态。

### R4 真实网页验收前的 DNS 诊断

2026-11-18 在 Codex 发起的非交互进程中，分别使用 WSL2 `cc`（Python 3.11.16）和 Windows `deskmate-win`（Python 3.12.7），从项目目录调用生产模块的 `resolve_host(host, 443)` 和 `public_ip(ip)`。两套解释器返回相同结果。用户随后在平时启动 GUI 的交互式 WSL 终端运行同一预检，确认使用 `/home/ldj/anaconda3/envs/cc/bin/python`，`www.iana.org` 返回 `198.18.1.67`，被同一生产地址校验拒绝。[预检命令](deskmate-affairs.md#真实人工验收的起点)

| 域名 | WSL `cc` 和 Windows `deskmate-win` 的解析结果 | `public_ip` |
| --- | --- | --- |
| `www.iana.org`（两份验收材料） | `198.18.1.67` | 拒绝非公网网络目标 |
| `www.rfc-editor.org`（对照） | `198.18.1.68` | 拒绝非公网网络目标 |
| `example.org`（对照） | `198.18.1.71` | 拒绝非公网网络目标 |

- WSL 使用自动生成的 `resolv.conf`，解析器端点为私有 IPv4，`/etc/hosts` 无 IANA 条目。两套探测进程均未继承常用 HTTP 代理变量，Windows 当前用户的 WinINET 系统代理及 PAC 未启用。
- Windows 运行中的 Clash Verge Rev 版本为 2.4.1。`clash-verge.yaml` 的运行配置启用了 TUN、DNS 接管及 `enhanced-mode: fake-ip`，配置的 Fake-IP 范围包含 IANA 探测地址；`blacklist` 模式的过滤列表没有 `www.iana.org` 的匹配项。应用的全局 DNS 覆写开关未启用。配置和解析结果相互印证，指向本机 Clash Verge 的 Fake-IP 解析。日志只登记开关、模式及目标匹配情况。
- 生产代码的 HTTPX client 设置 `trust_env=False`，允许的初始 URL 来自本轮用户输入并经过权限检查。每个连接和重定向都重新解析并校验地址，传输使用已校验 IP，HTTP Host 和 TLS SNI 保留域名，证书按默认策略校验。流和 client 由每跳的异步上下文关闭。
- 在 Codex 发起的 WSL `cc` 中，文档版预检输出 `www.iana.org: 198.18.1.67` 并按预期退出 1。用 Node.js 对文档中的订阅脚本做了 4 项本地检查，覆盖精确追加、同域不重复、其他过滤模式及缺少 DNS 配置。实际客户端应用仍待操作。
- 当前订阅脚本经核对为默认模板，按原字节备份并核验。用户在该订阅的脚本编辑器保存单域名过滤，确认界面未报错。随后读取生效配置确认 `www.iana.org` 恰有一条，另外 24 条过滤项仍在。TUN、DNS、`fake-ip` 和 `blacklist` 仍启用。复测使用文档中的同一 WSL `cc` 解释器和预检，返回 `104.18.24.232`、`104.18.25.232`、`2606:4700::6812:18e8`、`2606:4700::6812:19e8`，全部通过，退出 0。

### R4 无模型实网检查

2026-11-18 使用 WSL `cc`，通过 `Runtime` → `SessionService` → `PermissionChecker` → `FetchWebPage` 检查真实 HTTPS。探针的脚本化 client 只产生两条工具调用，不使用 Provider 账户或 API Key。会话明确提供两条 HTTPS URL，分别收到 `PermissionRequest` 并按该精确 URL 批准。生产工具沿用系统解析及默认 HTTPX 传输，探针仅记录实际响应、TLS 参数和关闭状态。实际命令退出 0：

```bash
cd /mnt/d/ldj/03/DeskMate
conda activate cc
PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 python - < .r1-verification/r4_web_acceptance.py
```

| 来源 | 输入及最终 URL | 标题 | HTTP 与正文 |
| --- | --- | --- | --- |
| `S1` | `https://www.iana.org/help/example-domains` | Example Domains | 200，`read`，1,244 字符，未截断 |
| `S2` | `https://www.iana.org/domains/reserved` | IANA-managed Reserved Domains | 200，`read`，2,768 字符，未截断 |

两页均直达，各一个 GET。传给 HTTPX 的连接目标均为 `104.18.24.232`，两次 HTTP Host、SNI 参数和实际 TLS 连接的主机名均为 `www.iana.org`。两次协商 TLS 1.3，证书及主机名验证开启。HTTPX 的 `trust_env=False` 和自动重定向关闭均得到确认。两个响应流和客户端正常关闭。实网重定向和实网中途取消本次未触发，离线对应测试见上文。

本次新增可复现的本机验收脚本和文档，生产代码无变动。未重新执行完整 pytest 或 SubAgent，上文保留 R4 开发阶段实际执行结果。

### R4 真实 Provider 桌面验收

用户已明确授权单次 R4 真实 Provider 资料任务并接受实际用量计费。已核对样例工作区的 `deepseek-r4` 配置与 `deepseek-flash` 标识，`project_notes.md` 的 SHA256 与基线一致，目标 `outputs/project-summary.md` 尚不存在。

用户确认在 WSL `cc` 启动的可见窗口已就绪，横幅为「真实模式 · 资料整理」，模型及独立样例工作区一致，聊天框为空。下一项检查从用户发送单次资料任务开始，目标为两份指定 IANA 页面、`project_notes.md` 和唯一产物 `outputs/project-summary.md`。真实工具调用与权限卡片待用户观察。

用户提交任务后，截图显示资料面板登记 `S1 已读 · project_notes.md`，成果区尚无记录。第一张权限卡片显示 `FetchWebPage`，操作为 `https://www.iana.org/help/example-domains`，与授权任务一致。此时等待用户批准，网页读取结果尚未确认。

批准第一张卡片后，用户截图确认 `S2 已读 · https://www.iana.org/help/example-domains`，工具输出区显示网页正文。第二张权限卡片显示 `FetchWebPage`，操作为 `https://www.iana.org/domains/reserved`。此时成果区仍无记录。

批准第二张卡片后，用户截图确认 `S3 已读 · https://www.iana.org/domains/reserved`，`S1` 至 `S3` 均可见。`WriteFile` 权限卡片只申请 `outputs/project-summary.md`。同时在磁盘核对目标尚不存在，`project_notes.md` 的 SHA256 与基线一致。此时等待写入批准。

批准写入后，用户截图显示运行 `completed`，窗口回到「就绪」，成果标记为「已回读核对」。只读检查会话 `session_20261118_211555_tpax` 确认工具记录恰好对应本地笔记读一次、两个 URL 各读一次、目标写入一次及目标回读一次，五条工具结果均成功。回读事件明确记录全文摘要一致。实际文件正文涵盖项目进度、两个行动项和 IANA 示例域名用途，三项正文引用与工具附加的来源一致。笔记未填写正式项目名，产物将名称标为暂称。

退出重开前基线如下。在恢复原会话后，对照文件和原会话记录，检查是否有重复写入或新工具记录。

| 路径或记录 | 字节数 | UTC 修改时间 | SHA256 |
| --- | --- | --- | --- |
| `project_notes.md` | 255 | `2026-11-18T08:50:32.877040+00:00` | `23f6d302affcc181428f7ccac9f7a3dc37fc78b838b01ba88dcbebeccd753988` |
| `outputs/project-summary.md` | 1,486 | `2026-11-18T13:21:33.078257+00:00` | `3c2ed274eb8518c6077392eef65fef4026fbbb288fcf7a5282683e0106a4725a` |
| `session_20261118_211555_tpax.jsonl` | 13,236 | `2026-11-18T13:21:35.766689+00:00` | `3d202c9cc1fafc4d08283009450148691aeff0e9ef24deb19ad9068d7a77f7c4` |

用户确认点击「退出应用」后正常退出。关闭后只读复核三个路径的 SHA256、字节数及修改时间，均与上述基线一致。待用相同工作区重开并恢复原会话。

用户确认使用相同命令重开后，窗口已就绪，Provider、模型与工作区一致，当前是新的空白会话。待从会话列表恢复 `session_20261118_211555_tpax`。

用户选择原会话并点击「恢复所选会话」，确认 ID、原任务历史、原工具结果及就绪状态符合预期，没有新权限卡片。恢复后从磁盘复核，上表三个路径的 SHA256、字节数及修改时间均一致，原会话仍只有五次既有工具调用。这次恢复没有观察到网页读取或文件写入重放。

### R4 收尾结论与覆盖边界

2026-11-20 用户按连续验收清单操作后确认全部符合预期。新会话 `session_20261120_200239_zoyx` 的磁盘记录已复核，取消后重用、成果回读及退出恢复通过。实际阶段与证据见下表。[连续验收清单](deskmate-affairs.md#连续验收清单2026-11-20)

| 检查 | 复核结果 |
| --- | --- |
| 权限等待时取消 | 用户确认卡片清空、回到就绪。首轮持久状态为 `cancelled`，网页工具记录中断 |
| 批准访问后尝试取消 | 第二轮已成功读取网页并以 `completed` 结束，未捕捉到实际取消窗口 |
| 同会话重新完成资料任务 | 第三轮 `completed`，本地笔记和单个网页各读一次，新摘要只写一次，再回读成功 |
| 成果文件与来源 | `outputs/cancel-retry-summary.md` 共 895 字节，SHA256 为 `22a3789f4b31d2dfc28e2b65ac33618bf66faff9b4284dd314e9b554b82464e8`，两条来源与正文相符 |
| 原文件保护 | `project_notes.md` 和 `outputs/project-summary.md` 的 SHA256 与 11 月 18 日基线一致 |
| 退出与恢复 | 用户确认两次正常退出、退出码为 0、恢复历史与就绪状态正常。独立比对恢复前快照，7 个文件的 SHA256、大小和纳秒修改时间全部一致，包括新会话日志和新成果 |

新会话保存了三个运行终态 `cancelled → completed → completed`，六条工具调用对应一条中断结果和五条成功结果。原中断调用已具有终结结果，后续工具调用和会话恢复没有重复执行记录。成功的文件调用参数使用 Windows 盘符绝对路径，本次桌面的具体启动解释器未独立采集。下面的只读审计在 WSL `cc` 中实际执行，退出 0，未发送模型或网页请求：

```bash
cd /mnt/d/ldj/03/DeskMate
conda activate cc
PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 python - < .r1-verification/r4_cancel_acceptance_audit.py
```

- 单次真实 DeepSeek `deepseek-r4` / `deepseek-flash` 资料任务与 WSLg 人工恢复通过。五次是会话日志中的工具调用数，未检查 Provider 账单或推断实际网络请求数。
- 用户已手动完成真实 Provider 权限等待时取消和同会话重用。第二次任务在捕捉到取消前已完成，真实 HTTP 响应流读取期间的取消仍未覆盖。两页实际 HTTPS 已验证直达读取及正常关闭，实网重定向未触发。这两项保留为覆盖边界。
- 11 月 18 日在 WSL `cc` 补跑下面三个离线测试，实际结果为 **3 passed，2.31 秒**，退出 0。使用 fake client、受控解析/传输和离线桌面控制器，覆盖取消后的资源释放与重用、拒绝迟到回复、每跳固定连接地址。完整 pytest 与 SubAgent 的历史结果仍为 WSL 853 通过、Windows 847 通过及 6 跳过、SubAgent 90/90。11 月 20 日只更新文档和只读审计脚本，未重新运行这些回归。
- 本轮收尾改动为单域名本机过滤、忽略目录内的验收材料与探针、验收文档。生产网络、权限及 TLS 策略无修改。`git diff --check` 通过，分支仍为 `feat/deskmate`，HEAD 为 `19e5d6d74c8413b71088e4dea3be538da3b05151`，暂存区为空。

```bash
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 \
  python -m pytest -q -p no:cacheprovider \
  tests/test_materials_workflow.py::test_permission_fetch_cancels_and_reuses_without_expanding_or_replaying \
  tests/test_materials_workflow.py::test_redirect_pins_each_hop_and_extracts_safe_text \
  tests/test_desktop_controller.py::test_permission_cancel_late_reply_rejected_and_next_run_works
```

### R4 提交前核对（2026-11-20）

本次提交范围按 R3.1 基线 `19e5d6d74c8413b71088e4dea3be538da3b05151` 的完整差异确定，共 28 个源码、测试、示例和文档文件，包含 R4-0 的回执与草稿修复。三份原有未跟踪设计文档纳入版本记录，R3.1 审查报告保留其原始版本含义。个人配置、会话、验收产物和 `.r1-verification/` 中的辅助脚本留在本机。

已获取远程 `feat/deskmate`，提交前本地与远程均为上述基线，分歧计数为 `0 0`，暂存区起初为空。WSL Git 的有效提交身份与上一提交一致，使用现有身份。依据完整工作区差异、开发记录和文件修改时间，最终完整回归之后只有文档与本机审计辅助文件变化。此轮补正 README 的 PowerShell 代码块和目标规格中的 R4 验收状态，生产代码与测试内容未修改。

实际执行了 28 个候选文件的敏感信息及文件类型检查、19 个 Python 文件的 AST 解析、`git diff --check` 和忽略规则检查。WSL `cc` 再次运行本机只读验收审计，确认运行终态、单次写入、回读以及恢复快照中 7 个文件的哈希、大小、修改时间一致，退出 0。本次未重新执行 pytest 或 SubAgent，完整回归沿用上文明确标注的开发阶段结果。真实 HTTP 流内取消与实网重定向仍保留为覆盖限制。

首次暂存检查发现两份新增文档头部的 Markdown 行末双空格被报告为尾随空白，已改用等效的反斜杠换行，原文字内容保留。提交前重新核对暂存路径、统计与差异格式。

## R5 开发与离线验收（2026-11-20）

工作区 `D:\ldj\03\DeskMate`（WSL `/mnt/d/ldj/03/DeskMate`），分支 `feat/deskmate`，起始 HEAD `0d76f22d729c781bf4a6f584b0f16f8ab0d73f4a`，初始状态干净，无适用 AGENTS.md。Windows 沙箱用户与仓库 owner 不同，Git 检查使用单命令 `-c safe.directory=D:/ldj/03/DeskMate`，没有更改全局 Git 设置。沙箱内 WSL 首次返回 E_ACCESSDENIED，随后通过允许的提升调用使用既有 cc；不更换解释器、依赖或权限策略。

### 分检查点与实际调试过程

| 阶段 | 实际结果 |
| --- | --- |
| R5-0 新用例修复前 | WSL 6 failed / 4.18s，涵盖关闭重试、URL allow/deny、来源复制、两种空网页 |
| R5-0 修复后相关回归 | WSL 119 passed / 8.42s；Windows 118 passed、1 skipped / 15.72s |
| R5-A 存储首轮 | WSL 8 passed / 2.62s：定义/历史、唯一领取、活实例、隔离、周期合并、重启 |
| R5-B 初次兼容检查 | WSL 57 passed、1 failed / 22.51s：写入前意图误登记为实际成果，导致旧文件读取被当成回读失败；已分离 write_intents 与 artifacts |
| R5-B 修正后的控制器与资料用例 | WSL 32 passed / 6.59s：队列、模型确认、R4 卡片、拒绝、真实文件回读、文本-only、越界拒绝、原聊天保留 |
| R5-C 首次 Qt/实验检查 | 4 passed、1 failed / 14.70s：实验恢复 Runtime 缺少 permission_mode 参数；已修复实验装配，未放宽断言 |
| 首轮扩大专项 | WSL 188 passed / 50.05s；Windows 183 passed、4 failed、1 skipped / 92.97s |
| Windows 时序修复 | 四项失败暴露 idle 先于恢复历史发布，以及空任务窗口未初始化详情。改为原子发布就绪/历史，初始化详情；相关 9 passed / 16.98s |
| Windows 存储/硬退出/来源补测 | 17 passed / 15.80s |
| 收尾边界 | WSL 23 passed / 13.40s：含启动期间取消、终态落盘失败后停止领取、未知副作用阻塞后续周期 |
| 时间解析补充 | WSL 15 passed / 3.74s；中文分钟/半点不丢失，近似或多个时刻请求补充 |

此前完整回归曾为 WSL 882 passed / 71.15s；在此后补充分钟解析用例，最终完整结果以下节为准。所有 R5 自动化均使用离线 LLMClient、可控时钟、临时工作区和真实 SQLite；未发送真实模型/网页请求。Qt 用例使用 offscreen，不能称为可见桌面或真实托盘人工通过。

三条完整流程分别位于 `test_schedule_window.py`、`test_desktop_scheduling.py` 和 `test_schedule_experiments.py`。中断实验确实启动独立 Python 子进程并 os._exit(71)，不是仅改状态字段：已领取情形工具写入数 0，写入后情形为 1；同一数据库重开、重复扫描和恢复会话后计数及文件 bytes/mtime 均不变。另有故障注入验证“文件已回读但终态落盘失败”的证据保留。

本轮未执行可见桌面人工清单或真实计费模型验收。真实调用建议范围、三条人工步骤、存储与恢复限制见 [R5 说明](deskmate-schedules.md)。R4 已有真实网页验收继续有效；真实 HTTP 流中途取消与实网重定向两项覆盖限制保持原记录。

### 最终完整离线结果与命令

| 环境/检查 | 实际结果 |
| --- | --- |
| WSL Ubuntu-24.04 / cc | Python 3.11.16，SQLite 3.53.4，PySide6 6.8.3；最终 **888 passed，0 failed，0 skipped，59.68s** |
| Windows / deskmate-win | Python 3.12.7，SQLite 3.54.1，PySide6 6.8.3；最终 **882 passed，0 failed，6 skipped，138.66s** |
| `tests/verify_subagent.py` | 两环境分别 **90/90**；脚本的 `Background task … failed: boom` 是故障注入预期输出，退出码均 0 |
| 两个入口 `--help` | 两环境的 `python -m likecc --help`、`python -m likecc.desktop --help` 均退出 0 |
| 学习实验 CLI | WSL 实际运行 missed-reminder、interrupted --stage written，均退出 0；分别为 0 次模型调用与 1 次工具写入，重开无重放 |
| 静态/版本检查 | 16 个改动 Python 文件 AST 解析通过，24 个改动/新增文件；`git diff --check` 通过；暂存区为空，分支/HEAD 与开工一致 |

Windows 6 项跳过均为原有平台边界：`test_bash_process_group.py` 四项 POSIX 进程组契约，`test_execution_contract.py:229` 一项 WSL/POSIX 进程组契约，`test_permissions.py:136` 一项找不到适合的系统文件链接测试。本轮没有新增平台跳过或弱化这些断言。时间解析补充前 Windows 完整结果另为 876 passed、6 skipped / 148.56s，不与最终结果混用。

WSL 实际使用解释器 `/home/ldj/anaconda3/envs/cc/bin/python`，可在现有 cc 终端复现：

```bash
cd /mnt/d/ldj/03/DeskMate
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 \
  /home/ldj/anaconda3/envs/cc/bin/python -m pytest -q -ra -p no:cacheprovider \
  --junitxml=.r1-verification/r5-final-wsl.xml
PYTHONDONTWRITEBYTECODE=1 /home/ldj/anaconda3/envs/cc/bin/python tests/verify_subagent.py
/home/ldj/anaconda3/envs/cc/bin/python -m likecc --help
/home/ldj/anaconda3/envs/cc/bin/python -m likecc.desktop --help
/home/ldj/anaconda3/envs/cc/bin/python -m examples.deskmate_schedules missed-reminder
/home/ldj/anaconda3/envs/cc/bin/python -m examples.deskmate_schedules interrupted --stage written
```

两个 CLI 实验本次分别保留在 `/tmp/deskmate-r5-4r63s736`、`/tmp/deskmate-r5-cmdc7gd2`。这些是 WSL 临时实验目录，不是用户正式工作区。claimed 阶段在两环境完整 pytest 中均实际启动子进程覆盖。

Windows 实际命令如下。重跑应换一个全新的 basetemp 名称，避免共享临时目录权限或已有内容被 pytest 清理；本轮未清理历史验证目录。

```powershell
Set-Location 'D:\ldj\03\DeskMate'
$env:QT_QPA_PLATFORM='offscreen'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONUTF8='1'
& D:/anaconda3/Scripts/conda.exe run --no-capture-output -n deskmate-win python -s -X utf8 -m pytest -q -ra -p no:cacheprovider --basetemp=.r1-verification/r5-final-win-05 --junitxml=.r1-verification/r5-final-win.xml
& D:/anaconda3/Scripts/conda.exe run --no-capture-output -n deskmate-win python -s -X utf8 tests/verify_subagent.py
& D:/anaconda3/Scripts/conda.exe run --no-capture-output -n deskmate-win python -s -X utf8 -m likecc --help
& D:/anaconda3/Scripts/conda.exe run --no-capture-output -n deskmate-win python -s -X utf8 -m likecc.desktop --help
```

阶段性专项使用同一 `pytest -q -p no:cacheprovider`，文件集合为 `test_scheduling`、`test_desktop_scheduling`、`test_schedule_window`、`test_schedule_experiments`、`test_r5_material_regressions`、`test_session_service`、`test_materials_workflow`、原有五个桌面测试及 `test_permissions`。阶段性 XML 与最终 XML 保留在忽略的 `.r1-verification/` 下。没有新增生产依赖、修改 uv.lock、暂存、提交或推送。

### R5 集中人工验收前的本次核查

本轮按用户要求一次性提供全部操作与预期，等待集中反馈。分支仍为 feat/deskmate，HEAD 仍为 R4 基线，已有 24 个 R5 改动/新增文件保留，暂存区为空。没有修改生产代码或测试代码，没有新功能开发。

历史证据只读核对：r5-final-wsl.xml 为 888 tests、0 failures、0 errors、0 skipped；r5-final-win.xml 为 888 tests、0 failures、0 errors、6 skipped，等于 882 passed。时间戳分别为 2026-11-20T20:55:07+08:00、20:56:26+08:00。本轮未重跑完整套件或 SubAgent，SubAgent 90/90 与入口帮助结果沿用先前记录。

实际环境复核：Windows deskmate-win 的 python.exe 为 `C:\Users\28436\.conda\envs\deskmate-win\python.exe`，Python 3.12.7、SQLite 3.54.1、PySide6 6.8.3，源码来自 DeskMate。一次多行 python -c 被 Conda 包装器拒绝，改用单行/外部脚本完成检查；不是产品失败。沙箱 CIM 进程清单无权限，未据此声称用户当前桌面进程不存在。

新建独立根目录 `C:\Users\28436\AppData\Local\Temp\deskmate-r5-acceptance-0f5098c3`，workspace 内为指定样例与无真实凭据占位配置。预检实际取得 windows Qt 平台、托盘可用 True、后端 idle、0 tasks / 0 executions，关闭后 worker_closed=True，退出码 0；没有显示窗口或提交任务，不算人工验收。

本次重新执行的只是现有四个专项文件 `test_scheduling.py test_desktop_scheduling.py test_schedule_window.py test_schedule_experiments.py`：**29 passed，24.18s，退出 0**。命令使用 deskmate-win、python -s -X utf8、QT_QPA_PLATFORM=offscreen、PYTHONDONTWRITEBYTECODE=1、-p no:cacheprovider，basetemp 在上述根目录的 regression-01，XML 为 current-offline.xml。覆盖真实存储、可控时钟、离线 LLMClient、Qt 控件和独立崩溃子进程；不等同于真实桌面操作或真实 Provider 验收。

本轮用户可见操作仍全部待反馈；真实 Provider 未授权、未执行。预期与编号详见 [集中清单](deskmate-schedules.md#r5-人工验收准备集中操作统一反馈2026-11-20)。没有暂存、提交、推送或启动 R6，原 likecc 目录未改动。

### R5 直接桌面操作尝试与阻塞（2026-11-20）

用户授权直接操作电脑后，使用电脑操作工具读取实际 Windows DeskMate 控件。工作区为上述隔离 workspace，模型显示 r5-reminder-only / offline-no-model，就绪，0 项安排。填入提醒测试草稿成功，但未能发送；没有创建任务或执行记录。

截图失败信息为 `FrameArrived timed out: timed out waiting on channel` / `window capture timed out: timed out waiting on channel`，点击失败为 `coordinate input geometry is unavailable`。文本控件树可读取；激活窗口、Raise 和 Tab 导航未观察到焦点变化。用户确认桌面已解锁、DeskMate 已在前台后，重新选择窗口仍截图超时，Tab 仍未改变焦点，因此停止进一步输入，保留未发送的测试草稿。仅凭这些信息无法定位底层原因，记录为电脑控制通道阻塞，不归类为 DeskMate 产品失败。

只读审计实际结果：tasks=[]、executions=[]、duplicate_due_groups=[]；project_notes.md 为 220 bytes，SHA256 为 `5c708cbd1324f2504ec5b0952d7b0f16e4bf066213c8cb5e92df91b2cd5f435a`，修改时间未变；outputs/weekly-summary.md 不存在。本次重新核对三个 XML 的计数和时间戳，未重跑测试：完整 WSL 888 passed、Windows 882 passed / 6 skipped；验收准备专项 29 passed / 24.183s。

分支仍为 feat/deskmate，HEAD 为 0d76f22d729c781bf4a6f584b0f16f8ab0d73f4a，24 项已有改动/新增文件保留。此次无产品修复、无真实模型调用、无强制退出或手工崩溃。A/B/C 可见验收仍待完成，不能新增“人工通过”或“已具备提交条件”的结论。限制仍为一次性/每周、Asia/Shanghai/UTC、本地单调度器；不支持 Windows/WSL 同写任务库，未知写入不承诺无损恢复或自动重放。

### R5 逐项人工验收进展（2026-11-22）

用户改为每轮一项、反馈后继续。沿用仓库外隔离 workspace 与 r5-reminder-only 占位 Provider，不使用真实模型。下列编号对应本次逐项清单，与 11 月 20 日集中清单的编号分别记录。

| 项目 | 实际结果与证据 |
| --- | --- |
| P1 启动独立工作区 | 用户回复“正确”：主窗口就绪，工作区、占位模型及 0 项安排/待处理符合预期 |
| P2 打开任务管理 | 用户回复“正确”：任务窗口、空列表、表单和后台调度说明符合预期 |
| A1 自然语言提醒预览 | 用户提供截图：2026-11-23T19:00:00、Asia/Shanghai、仅一次、正确隔离工作区，材料/网页/输出均无，模型不调用；安排及执行列表仍为空，未确认保存 |
| A2 歧义时间 | 用户回复“正确”：发送“明天七点提醒我复习这份计划”后提示补充上午/下午，不新增安排，输入保留 |
| A3 保存临近提醒 | 用户回复“正确”：表单预览并确认 R5-A3 隐藏到期提醒，未到期时一项安排、无执行记录 |
| A4 隐藏后到期 | 用户回复“正确”：关闭任务窗口及主窗口后保留托盘，真实到期后恢复，只有一条待处理，完成按钮可用，无模型或写入卡片 |
| A5 重复扫描 | 用户回复“正确”：保持运行等待 20 秒并三次关闭/打开任务窗口，仍只有原定时刻的一条待处理 |
| A6 完成提醒 | 用户回复“正确”：点击完成后显示“已完成提醒”，按钮禁用，主窗口一项安排、零项待处理，历史仍一条 |
| A7 正常退出重开 | 用户回复“正确”：原提醒和唯一已完成历史保留；附图主窗口为一项安排、零项待处理。重开后只读审计确认任务/执行 ID、due_at、done 状态与重启前一致，无重复记录 |
| A8 修改提醒 | 修改保存用户回复“正确”，持久定义 revision=2；用户在 18:07 提供截图，新时间 18:04:18 的记录为待处理。旧时间点的空列表未现场查看；事后只读历史确认旧时间 18:02:18 无记录，新时间仅一条 |
| A9 取消提醒 | 创建后立即取消，用户回复“正确”；到期前审计定义 enabled=0、next_due 为空，本任务无执行记录。超过原定时间后用户再次确认，18:18:09 附近只读复核仍无本任务执行记录 |
| B1 周期资料预览 | 用户回复“正确”：解析为 2026-11-27 18:00:00、Asia/Shanghai、每周五、执行资料任务，预览阶段未保存 |
| B2 范围核对及保存 | 用户回复“正确”：材料 project_notes.md，URL 无，输出 outputs/weekly-summary.md，模型每次确认；保存后四项安排、零项待处理，新任务无到期记录 |
| B3 修改周期任务 | 用户回复“正确”；只读审计确认原 task_id 保持、revision=2，首次改为 2026-11-22 18:26:52、每周日，材料/输出和 ask 策略未扩大 |
| B4 到期待确认 | 用户回复“正确”：唯一记录为待确认模型调用，四项安排/一项待处理，会话和运行为空，无成果；未点击允许模型 |
| B5 取消周期任务 | 用户回复“正确”：定义和当次记录显示已取消，允许模型按钮禁用，四项安排/零项待处理；只读核实历史保留且未执行 |
| C1 未到期重启 | 创建及正常退出重开两轮均获用户“正确”反馈；重启前后同一 task_id、18:50:05 到期时间及空执行历史保持，五项安排/零项待处理 |
| C2 退出期间错过提醒 | 用户确认到期前退出、过期后重开出现逾期待处理，并明确确认随后手动完成；等待与三次重复查看后仍唯一。只读核实原定 18:47:00 的同一记录为 done，无重复 |
| C7 第二可见实例 | 用户回复“正确”：同一 Windows 工作区第二实例提示已有活动调度器，原实例仍就绪且六项安排/零项待处理；只读核实任务与执行记录未变化。随后用户确认只退出报错第二窗口，原实例继续运行 |
| D1 最终持久数据核查 | 只读审计为六项安排、四条执行（三条 done、一条 cancelled），没有重复到期组；输入哈希/大小/mtime 未变，输出不存在。此项为数据核查，不新增人工操作结论 |

A1 的内容保留完整原句“明天晚上七点提醒我复习这份计划”，与 parse_schedule() 将原文保存到 TaskSpec.content 的实现一致。此前指导将内容简写为“复习这份计划”不够准确，已说明；不是此次发现的产品缺陷。右侧任务内容编辑框为空、下方聊天解析预览完整，符合现有表单行为。截图仅证明预览，未证明持久保存、到期、隐藏或重启流程通过。

上述 P1 至 A7 人工步骤未重跑 pytest 或 SubAgent，未修改生产代码或调用真实 Provider。随后 UI1 的修正与新回归结果单独记录如下，其余逐项验收继续等待操作和反馈。

A4 反馈后的只读数据库审计：task_id=d6287841294348deb88928a3fd8e4210，revision=1，内容为 R5-A3 隐藏到期提醒，本地时间 2026-11-22T17:35:02、Asia/Shanghai、once。唯一执行 id=526e7a807e114fc091e99c2a853f3cdf，due_at=2026-11-22T09:35:02+00:00，status=pending，原因为“逾期待处理。”，session_id/run_id 为空，evidence={}，duplicate_due_groups=[]。输入文件哈希/大小/修改时间保持原样，输出不存在。该审计支持持久记录与用户反馈一致；窗口隐藏过程的证据来自用户确认，重复查看、完成和重启仍待后续逐项验收。

A6 反馈后、重启前再次只读审计：上述 task_id、execution_id、due_at 和定义均未变化，唯一执行 status=done，duplicate_due_groups=[]。输入文件哈希/大小/修改时间仍不变，输出不存在，session_id/run_id 仍为空。该结果作为 A7 正常退出重开的对照；此时尚未确认重启验收通过。

A7 重开后审计的输入文件哈希、大小、修改时间也与重启前一致，输出仍不存在。持久化案例通过，但用户同时报告主窗口只显示一部分且无法鼠标拖动；截图中左侧及标题栏在屏幕可见范围外，右侧和底部仍可见。记为 UI1 窗口可达性问题，待定位，不因 A7 数据正确而忽略。源码初查 ChatWindow.__init__() 只设置 resize(920, 780)，DesktopApplication.show_window() 调用 showNormal()/raise_()/activateWindow()，未发现按屏幕可用区域校正位置的逻辑；尚不能据此确定该次偏移的根因。先指导用户通过 Windows 系统菜单最大化恢复可见性，再观察结果；未修改生产代码，未宣称修复，也未重新运行测试。

### UI1 窗口可达性最小修正与可见复验（2026-11-22）

用户反馈 Alt+空格没有弹出菜单，窗口仍显示不全。A8 暂停，保留原始偏移原因尚未确定的结论。隔离 Qt 回归将主窗口设为 (-300, -180) 且超过屏幕大小，在启动与托盘恢复两条路径均复现窗口继续越界，验证了缺少恢复措施的问题；该故障注入不等于复现用户桌面最初产生偏移的原因。

最小生产改动仅在 DesktopApplication：首次显示及 show_window() 后，通过带 QObject 上下文的零延时 Qt 回调执行 _fit_window()，在原生边框形成后核对各屏幕 availableGeometry。已完整位于任一屏幕内的位置保持；越界窗口选主要重叠的屏幕，必要时缩小并移动回可用区域。全部计算沿用 Qt 逻辑像素，合法负坐标副屏不会被当成越界；最大化/全屏状态跳过。若布局最小尺寸超过可用区域，仅保证标题栏回到可见范围，不承诺所有小屏幕布局都能完整容纳。没有修改调度器、数据库、会话或权限行为。

测试在 tests/test_desktop_lifecycle.py 增加启动/恢复越界两项，以及模拟负坐标副屏一项；同时检查草稿、会话、空任务记录保持。首次 Windows 运行 3 failed / 17.67s：两项为旧代码未纠正窗口，第三项是测试对 Qt offscreen 显示时两像素边框位移的断言过严。副屏断言改为仍完整位于原副屏、尺寸不变、只容许极小边框位移；未放宽越界窗口必须完整进入可用区域的断言。生产修正后定向 3 passed / 14.81s。

| 本次实际回归 | 结果 |
| --- | --- |
| Windows deskmate-win，五个相关文件 | 38 passed，66.07s，退出 0 |
| WSL Ubuntu-24.04 / cc，同五个文件 | 38 passed，35.64s，退出 0 |
| 隔离工作区只读审计 | 原 task/execution ID、due_at 和 done 状态不变；duplicate_due_groups=[]，输入哈希/大小/mtime 不变，输出仍不存在 |
| Git 检查 | diff --check 通过，暂存区为空，无提交或推送 |

五个文件为 test_desktop_lifecycle.py、test_desktop_launch.py、test_desktop_window.py、test_schedule_window.py、test_desktop_scheduling.py。共同参数为 `-m pytest -q -p no:cacheprovider`、QT_QPA_PLATFORM=offscreen、PYTHONDONTWRITEBYTECODE=1；Windows 使用 `conda run --no-capture-output -n deskmate-win python -s -X utf8`，WSL 使用既有 `/home/ldj/anaconda3/envs/cc/bin/python`。Windows basetemp 在 `C:\Users\28436\AppData\Local\Temp\deskmate-r5-ui1-related-20261122-a`，XML 为同路径加 `.xml`；WSL basetemp 在 `/tmp/deskmate-r5-ui1-related-20261122-a`，XML 同样加 `.xml`。两平台测试库互相独立，不写正在运行的验收任务库。修复前、定向修复后 XML 分别为 Windows Temp 下 deskmate-r5-ui1-before-20261122-a.xml、deskmate-r5-ui1-after-20261122-a.xml。

上述是离线自动化证据，用户当前旧进程尚未加载修正，需要正常退出重开进行 UI1 可见复验；未将其记为人工修复通过。本轮未重跑完整套件、SubAgent 或帮助入口，先前 888/882 等仍是 UI1 修正之前的历史记录。未调用真实 Provider，未改动原 likecc 目录。

随后用户执行正常退出重开，并回复“正确”：新主窗口完整显示、标题栏可见且能拖动，仍一项安排、零项待处理，原已完成记录保留。因此 UI1 的本次 Windows 重启显示/拖动复验通过，恢复 A8 逐项验收。再次只读审计确认 task_id=d6287841294348deb88928a3fd8e4210、execution_id=526e7a807e114fc091e99c2a853f3cdf、due_at 和 done 状态不变，无重复到期组，输入文件未变、输出不存在。该人工结论不扩大到其他显示器组合、分辨率或原始偏移诱因；修正后的托盘恢复定位目前仍以自动化回归为证据。

### A8 修改时间后的实际记录（2026-11-22）

按逐项操作生成相差两分钟的旧/新时间，用户保存 R5-A8 修改前后，再选中原安排修改为 R5-A8 修改后并确认。用户回复“正确”后，17:59:45 附近只读核实 task_id=37385d958f104b94a8ddfe9a5888c1a9，revision=2，local_at=2026-11-22T18:04:18、Asia/Shanghai，next_due=10:04:18+00:00；本任务尚无执行记录，总共两项定义，未新增第三项。

原计划在旧时间 18:02:18 后、新时间之前查看空列表，用户实际于 18:07 检查并提供截图：新内容和新时间正确，状态待处理、会话/运行为空、没有已写入成果。此时已过新时间，出现待处理符合预期。随后的真实工作区只读审计确认本任务唯一执行 id=659e8df6e8a2446599a8a8b286c3bf10，due_at=2026-11-22T10:04:18+00:00，status=pending，旧时间无执行记录，duplicate_due_groups=[]。输入文件未变，输出不存在；原 A3 执行仍为 done。

因此新时间到期有用户可见截图证据，旧时间未生成记录由实际持久历史核实；不能声称用户在旧时间点亲眼观察过空列表，也不将截图查看时间当成后台准确领取时间。本轮未修改代码或重跑测试，接下来先完成 A8 待处理提醒再进入 A9。

A8 收尾用户回复“正确”，随后只读审计确认原执行 659e8df6e8a2446599a8a8b286c3bf10 已为 done，未新增执行记录。

### A9 到期前取消（2026-11-22）

用户按表单创建 R5-A9 取消提醒并立即取消，回复“正确”。18:12:14 附近只读核实 task_id=401826b2f1c54d839d2b002ee0fcf467、revision=2、enabled=0、next_due=null，原定本地时间为 2026-11-22T18:16:14、Asia/Shanghai；本任务无执行记录。全库三项安排、两条 done 执行，duplicate_due_groups=[]，输入文件未变、输出不存在。此时尚未到原定时间，取消后不触发的到期后检查留待下一轮用户反馈与审计。

到期后用户回复“正确”；18:18:09 附近再审计，原定 18:16:14 已过去，本任务仍 enabled=0、无执行记录，全库仍是三项安排和原来的两条 done，无重复到期组，输入/输出状态未变。A9 的真实时间到期后不触发检查通过。接下来进入 B1 周期资料任务预览，真实 Provider 仍未授权、未调用。

### B1/B2 周期定义与确认范围（2026-11-22）

用户发送“每周五下午六点，根据工作区的 `project_notes.md` 更新 `outputs/weekly-summary.md`”，确认预览时间/时区后，逐项核对文件、URL、输出及模型策略并保存，两轮分别回复“正确”。18:22:34 附近只读审计确认新 task_id=32634e55e8604010b8cf73f5fea4377d、revision=1、kind=execute、repeat=weekly、local_at=2026-11-27T18:00:00、timezone=Asia/Shanghai、next_due=2026-11-27T10:00:00+00:00。files=[project_notes.md]、urls=[]、outputs=[outputs/weekly-summary.md]、model_policy=ask，Provider 为既有 r5-reminder-only / offline-no-model 占位配置。

全库四项安排，仍仅有前两项提醒的 done 记录，新任务没有执行记录；duplicate_due_groups=[]，输入文件未变，输出不存在。此阶段只确认真实桌面的周期定义、预览、保存与查询，不是模型资料执行通过。下一项为修改首次时间，以今天到期验证待模型确认；若改为周日首次日期，重复星期相应变为周日，不能继续称其为每周五。

B3 用户修改原周期任务并回复“正确”。18:27:41 附近只读核实仍为 task_id=32634e55e8604010b8cf73f5fea4377d、revision=2，内容更新为 R5-B3 周期资料任务，local_at=2026-11-22T18:26:52、Asia/Shanghai、weekly，星期为周日；输入/URL/输出列表与 model_policy=ask 保持。此时新时间已过，存在唯一执行 id=5220d89f33004a9cbfce7b271733bb1f，due_at=2026-11-22T10:26:52+00:00，status=awaiting_model，session_id/run_id 为空、evidence={}，下一时刻为 2026-11-29T10:26:52+00:00。没有重复组，输入未变、输出不存在。这里只记录真实库已到期待模型确认；B4 可见状态仍待用户查看，不自动批准模型调用。

B4/B5 随后分别获用户“正确”反馈。取消后只读审计确认原周期 task_id 不变、revision=3、enabled=0、next_due=null；原执行 5220d89f33004a9cbfce7b271733bb1f 保留，状态 cancelled、原因“用户取消安排”，session_id/run_id 仍为空、evidence={}。全库四项安排、两条 done 与一条 cancelled，无重复到期组，输入文件未变，输出不存在。周期定义、修改、到期待确认和取消的可见流程已通过；没有批准占位 Provider 或真实 Provider 执行。

### B6–B9 离线证据复核

本轮只读核对 UI1 回归的 Windows XML（38 tests、0 failures/errors/skipped）与相关源码断言，没有再次运行测试。以下项目已包含在上文 Windows/WSL 各 38 passed 中；属于离线模型、临时工作区、真实 SQLite/文件和 offscreen Qt 的自动化证据，不标为用户可见执行或真实 Provider 通过。

| 清单项目 | 已有测试及核对内容 |
| --- | --- |
| B6 前台忙时排队 | test_weekly_queues_then_permissions_evidence_and_preserved_chat：前台运行时为 queued 且说明等待当前运行，之后独立定时会话执行并恢复前台内容 |
| B7 拒绝写入 | 上述 deny=True 参数：WriteFile 卡片被拒绝，磁盘无输出，artifacts 空、tool_errors 保留用户拒绝；Agent completed 不被当作写入成功 |
| B8 批准写入/回读/历史 | deny=False：输出含来源标识，artifacts=verified、digest 和 session/run 保存，重开保留证据且不增加模型调用 |
| B9 R4 卡片与草稿 | test_scheduled_r4_question_permission_cards_preserve_draft：实际 Qt 问答/权限控件可提交，原草稿保持，记录显示已回读核对 |

XML 同时包含 test_model_confirmation_and_truthful_outcomes 的 text_only、readback_fail、expand 三个参数，分别核对无写入、回读失败和超范围拒绝的真实结果。当前普通桌面入口的占位 Provider 不能执行这些资料任务；真实可见执行仍须单独授权。接下来继续 C1 未到期重启检查。

### C1 未到期重启的前置对照（2026-11-22）

用户创建 R5-C1 未到期重启提醒并回复“正确”。18:35:50 附近只读审计确认 task_id=db19fe56663145e4ac1f30e8c23cd343、revision=1、enabled=1，local_at=2026-11-22T18:50:05、Asia/Shanghai、once，next_due=2026-11-22T10:50:05+00:00，本任务无执行记录。全库五项安排，仍为既有两条 done 与一条 cancelled，duplicate_due_groups=[]，输入未变、输出不存在。保存为重启前对照，下一轮要求在到期前正常退出并重开同一工作区；此时不宣称重启检查通过。

用户按原工作区命令正常退出重开后回复“正确”。18:37:46 附近只读复核上述任务 ID、revision=1、enabled=1、next_due、内容和范围均与重启前相同，仍未到 18:50:05，未生成该任务执行记录。原两条 done 与一条 cancelled 也保持，无重复，样例文件未变。C1 未到期任务重开后继续等待的可见流程与持久数据核验通过。下一轮先由用户取消这条测试提醒，避免它干扰 C2 的退出期间错过提醒案例；取消尚未执行，不提前记为通过。

C1 收尾用户确认取消正确；后续审计确认原任务 revision=2、enabled=0、next_due=null，仍无执行记录，取消后的定义保留。

### C2 退出期间错过提醒的前置对照（2026-11-22）

用户创建 R5-C2 退出期间错过提醒，保存后立即正常退出，并确认托盘 D 消失、启动终端返回提示符。18:43:18 附近只读审计确认 task_id=0a29a0c6a7a4451cbd762c2f06cdaf70、revision=1、enabled=1、local_at=2026-11-22T18:47:00、Asia/Shanghai、once，next_due=2026-11-22T10:47:00+00:00，本任务无执行记录。全库六项安排，执行仍为原两条 done 和一条 cancelled，无重复，输入未变、输出不存在。应用完全退出由用户反馈确认，审计只读数据库、不启动调度器。下一轮要求保持退出直到 18:47:20 或之后再重开；此时尚未标记逾期恢复通过。

C2 过期后重开一轮用户回复“正确”。18:55:42 附近审计已发现唯一执行 id=6a27aba7299f40a4974f4d548c9f05f6，task_id 保持，due_at=2026-11-22T10:47:00+00:00，reason=“逾期待处理。”，status=done，session_id/run_id 为空、evidence={}。因上轮要求先保留待处理，专门向用户核对；用户明确回答“是，我手动点击了完成”。因此记录为先出现逾期待处理、用户随后手动完成，不误判为调度器自动完成。

当前全库六项安排、三条 done 与一条 cancelled，duplicate_due_groups=[]，输入文件未变，输出不存在；C1/A9 取消安排仍无执行记录。只读审计脚本使用 mode=ro 且仅 SELECT，不触发扫描或状态修改。C2 的逾期恢复与完成已有用户和持久记录证据，下一轮检查重复查看后同一条已完成历史仍保留。

C2 收尾用户确认等待 20 秒、三次关闭/打开任务窗口后仍只有原已完成历史，六项安排、零项待处理。再次读库确认 execution_id=6a27aba7299f40a4974f4d548c9f05f6、due_at、done 状态及全库计数均不变，无重复到期组。C2 逾期恢复、手动完成及重复扫描不新增记录通过。

### C3–C6 既有隔离实验与离线证据复核

本轮只读复核验收准备阶段的 current-offline.xml（29 tests、0 failures/errors/skipped，24.183s）和 tests/test_scheduling.py、tests/test_schedule_experiments.py、examples/deskmate_schedules.py，未重新运行实验。以下结论沿用那次实际执行结果，不计为当前桌面人工制造或复现崩溃。

| 清单项目 | 证据与边界 |
| --- | --- |
| C3 多个周期错过 | test_weekly_coalescing_edit_cancel_and_workspace_isolation 用可控时钟推进 29 天，重复扫描仍一条，原因含合并错过的 4 次，next_due 在未来；属于存储层周期合并验证，没有通过改系统时间或真实等待多周来验收 |
| C4 已领取尚未执行中断 | test_real_process_crash_and_reopen_experiment[claimed] 调用真实隔离子进程 os._exit(71)，同库重开为 interrupted，实际写入次数 0，重复扫描不重放 |
| C5 写入后终态未保存 | 同用例 [written] 在真实 WriteFile 成功、checkpoint 保存证据后硬退出；实际写入次数 1，重开后文件 bytes/mtime 与调用计数不变，恢复会话模型调用为 0 |
| C6 工作区隔离 | 独立 a/b 库不共享定义或记录；复制数据文件到另一工作区后因 metadata 所属路径不符而拒绝加载，不默默迁移授权 |

另复核 queued/awaiting_model/running/waiting 四种状态恢复为 interrupted、保留 session/run/evidence 的用例，以及未知写入阻止后续周期、明确重试只创建一条关联记录的用例。活实例所有权用例证明第二次打开不能把 running 改为 interrupted；接下来 C7 单独做同一 Windows 环境中的第二可见实例检查。未强制结束当前桌面应用，未跨 Windows/WSL 同写验收库，真实 Provider 仍未授权。

### C7 同一 Windows 工作区的第二实例（2026-11-22）

用户保持原 DeskMate 运行，在另一个 Windows PowerShell 使用相同工作区和占位 Provider 启动第二实例，回复“正确”：新窗口显示“配置/启动错误”，正文包含“该工作区已有活动调度器；请先退出另一实例”；原窗口仍就绪、六项安排、零项待处理。随后只读审计确认六项定义的 ID/revision/enabled/next_due 未变化，原四条执行仍为三条 done 与一条 cancelled，ID/due_at/status 均保持，没有新增 interrupted 或重复到期组；输入文件未变、输出不存在。

本次可见检查时原实例没有进行中的模型运行；running 状态不被第二实例回收的证据来自前述离线 live_owner 用例。未启动 WSL 实例打开此库，不据此宣称跨内核并发受支持。阻止第二实例接管的检查通过，下一轮仅正常退出报错的第二个窗口，保留原实例供收尾检查。

### D1 收尾与 UI1 修正后的完整离线回归（2026-11-22）

C7 收尾用户回复“正确”：只退出第二个报错窗口，原实例仍运行。随后执行只读 audit.py，仍为六项安排、四条执行（三条 done、一条 cancelled），duplicate_due_groups=[]。所有原 ID、due_at、状态和取消定义保留；project_notes.md 为 220 bytes，SHA256 为 `5c708cbd1324f2504ec5b0952d7b0f16e4bf066213c8cb5e92df91b2cd5f435a`、mtime_ns=1795181309474078500，outputs/weekly-summary.md 不存在。完整审计保存在验收根目录的 final-audit-20261122.json；没有启动第二个调度器来做审计。

鉴于本次人工验收中加入了 UI1 最小修正，重新执行完整离线回归、SubAgent、两个入口帮助及内存编译。下面均为本次新结果；先前 888 / 882+6 是修正前的历史证据，未改写为本次成绩。

| 环境/检查 | 本次实际结果 | 证据 |
| --- | --- | --- |
| WSL Ubuntu-24.04 / cc，完整 pytest | 891 passed，0 skipped，XML time=67.817s | `/tmp/deskmate-r5-final-ui1-20261122-a.xml`，timestamp=2026-11-22T19:10:34.268472+08:00 |
| Windows deskmate-win，完整 pytest | 885 passed、6 skipped，控制台 136.52s，退出 0 | Windows Temp 下 `deskmate-r5-final-ui1-win-20261122-b.xml`；891 cases、0 failures/errors，XML time=136.475s |
| tests/verify_subagent.py | 双平台均 90/90，退出 0 | Windows Temp 下 `deskmate-r5-final-ui1-win-subagent-20261122.log`；WSL `/tmp/deskmate-r5-final-ui1-subagent-20261122.log` |
| `python -m likecc --help` 与 `python -m likecc.desktop --help` | 双平台四次均退出 0 | 同一 Temp 或 `/tmp` 的 `deskmate-r5-final-ui1-*-help-20261122.log` |
| 本轮 18 个修改/新增 Python 文件 | 双平台 AST 解析及内存 compile 全部通过，退出 0，不生成 pyc | Windows Temp 的 `deskmate-r5-final-ui1-win-compile-20261122.json`；WSL `/tmp/deskmate-r5-final-ui1-compile-20261122.json` |

运行环境本次读取：Windows Python 3.12.7、SQLite 3.54.1、PySide6 6.8.3，解释器 `C:\Users\28436\.conda\envs\deskmate-win\python.exe`；WSL Python 3.11.16、SQLite 3.53.4、PySide6 6.8.3，解释器 `/home/ldj/anaconda3/envs/cc/bin/python`。SubAgent 日志中的 `failed: boom` 是异常任务测试的预期注入，汇总为 90/90。

Windows 六项跳过原因保持原状：test_bash_process_group.py 四项、test_execution_contract.py 一项要求 POSIX 进程组；test_permissions.py 的 test_symlink_escape 未找到合适系统文件。不能以跳过视为 Windows 已覆盖这些契约。新增三项测试均来自 UI1 的启动/恢复越界及负坐标副屏；其他屏幕配置的人工覆盖没有因此扩大。

完整 pytest 使用 QT_QPA_PLATFORM=offscreen、PYTHONDONTWRITEBYTECODE=1、PYTHONUTF8=1、`-q -ra -p no:cacheprovider`，basetemp 为对应 XML 去掉 `.xml` 的新目录。Windows 首次启动未留下可核验报告，之后改为明确的字面路径参数并使用全新 `...win-20261122-b` 完成；未把缺少证据的尝试计作通过。命令为：

```powershell
& D:/anaconda3/Scripts/conda.exe run --no-capture-output -n deskmate-win python -s -X utf8 -m pytest -q -ra -p no:cacheprovider --basetemp=C:/Users/28436/AppData/Local/Temp/deskmate-r5-final-ui1-win-20261122-b --junitxml=C:/Users/28436/AppData/Local/Temp/deskmate-r5-final-ui1-win-20261122-b.xml
```

```bash
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 /home/ldj/anaconda3/envs/cc/bin/python -m pytest -q -ra -p no:cacheprovider --basetemp=/tmp/deskmate-r5-final-ui1-20261122-a --junitxml=/tmp/deskmate-r5-final-ui1-20261122-a.xml
```

复现应换新 basetemp，不重用以上证据目录。所有测试数据在仓库外临时目录，两平台不共享 SQLite；Windows 正在运行的人工验收库仅 mode=ro 审计。完整套件此次也重新覆盖 B6–B9、C3–C6 的离线断言及 claimed/written 隔离子进程实验，仍不能等同于真实可见模型运行或强制结束实际桌面进程。

当前人工证据：Windows P1/P2、A1–A9、B1–B5、C1/C2/C7 与 UI1 重启显示/拖动。A8 旧时间点由事后数据库核实，未现场观察。B6–B9 的模型执行流程、C3–C6 的周期/崩溃/隔离保留离线证据类别。真实 Provider 未授权、未执行。

文档同步后 Git diff --check 通过，暂存区为空；分支仍为 feat/deskmate，HEAD 仍为 0d76f22d729c781bf4a6f584b0f16f8ab0d73f4a，26 项已有修改/新增保留。未暂存、提交、推送或操作原 likecc 目录。

### R1 真实 Provider 验收准备与单独授权

已新建仓库外 `C:\Users\28436\AppData\Local\Temp\deskmate-r5-provider-20261122-a\workspace`，仅复制核验过的 project_notes.md 样例、建立空 outputs 目录，并写入无密钥项目配置。Provider 为 `deepseek-r5`，服务 DeepSeek、模型 `deepseek-flash`、Anthropic 兼容协议，thinking=true、context_window=1000000、max_output_tokens=4096。只解析配置并检查默认写入规则，无 client、任务库、模型请求或输出文件；未读取/复制真实 Key。未来使用 Windows deskmate-win，不与 WSL 共写库。

具体 proposal.txt 位于该临时根目录，拟授权共三次 Agent 运行：一次只读前台任务等待用户输入以观察排队，再取消；一次定时资料任务拒绝写入；一次定时资料任务批准写入并回读。两项定时任务每次单独确认模型，验收后取消未来周期，不授予长期周期调用。只读样例 project_notes.md 和既有目标输出，只写 outputs/weekly-summary.md，URL 列表为空；相关工具为 ReadFile、AskUserQuestion、WriteFile 及必要的本地工具发现，不启用网页、Shell、子 Agent、Skills/MCP/Hook/记忆/摘要扩展。

预计合计 8–15 次模型请求，不含 SDK 重试，这是估计而非硬上限；额外任务或新一轮重试需另行确认。模型拿到样例内容、任务、系统/工具说明和本次对话上下文，费用按实际 tokens 计算。期望只在批准案例生成 outputs/weekly-summary.md，另有 .likecc 下的任务、所有权和会话记录。权限流程为模型单次确认，再经现有工具权限卡片拒绝/批准写入；范围确认不替代写入决定。

2026-11-22 仅浏览核对 [DeepSeek 官方 Anthropic 文档](https://api-docs.deepseek.com/guides/anthropic_api/) 与 [官方价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)，没有调用模型。Flash 每百万 tokens：空闲时段缓存未命中输入 1 元、命中 0.02 元、输出 4 元；高峰分别 2/0.04/8 元。举例 10 万未缓存输入加 1 万输出是 0.14 元或 0.28 元，并非本次账单或费用上限。服务端兼容处理和 SDK 重试可能影响用量，4096 配置值也不作为费用上限。没有查询余额或账单。

准备完成时尚未对本次范围取得同意，标记为“真实 Provider 验收待完成”。普通验收反馈“正确”不自动视为计费授权。代码具备进入评审的离线证据，但不能宣布完整真实 Provider/桌面执行验收通过。所有改动保留工作区，暂存、提交、推送仍另行进行；不启动 R6。限制保持：一次性/每周、Asia/Shanghai/UTC、本地单调度器；不支持 Windows/WSL 同库并发，未知写入需核对且不承诺无损恢复或自动重放。R4 两项实网覆盖限制也保持。

随后用户明确回复“同意上述三次真实 Provider 验收”。本次授权已取得，范围就是上述一次只读前台运行、一次定时拒绝写入、一次定时批准并回读；包括已告知的请求估计、SDK 重试可能性和按实际 tokens 计费，不自动扩大到额外任务或长期周期调用。2026-11-22 19:28 附近复核分支/HEAD 与准备目录，未读取凭据、未发模型请求。继续每轮一个人工步骤，先正常退出旧 r5-reminder-only 验收窗口，下一轮再准备新工作区的本地隐藏凭据输入与启动；此时退出和新启动均尚待用户反馈。

用户随后回复“正确”，确认旧占位 Provider 窗口已正常退出、托盘消失、原启动终端返回提示符。2026-11-22 20:21 后在仓库外准备 launch.py，使用既有 Windows deskmate-win 解释器及原 `python -m likecc.desktop` 入口，工作区固定为新 provider workspace，不修改生产代码。启动器通过本机交互终端 getpass 隐藏读取 Key，非交互 stdin 直接拒绝；凭据仅用于 GUI 子进程环境，不放命令行参数或配置文件。它不改变父进程环境，不开启额外扩展，也不自动发送任何任务。

本次实际只运行 check_preparation.py 与 `launch.py --check`，均退出 0：空 Key 配置、样例哈希、无任务库/输出、默认写入无 allow/deny 覆盖均符合准备状态；没有提示读取 Key、创建模型 client 或发请求。下一步由用户在可见 PowerShell 启动并反馈工作区、deepseek-r5 / deepseek-flash、就绪和零项安排；此时仍未取得新窗口的可见反馈，启动就绪也不等于 API 凭据或计费连通性已验证。没有重跑 pytest/SubAgent，不把预检算入三次模型运行。

### R1 新工作区可见启动反馈

用户回复“正确”：原生 Windows 窗口就绪，显示 deepseek-r5 / deepseek-flash、独立 provider workspace、零项安排和零项待处理/确认。20:24 后对新库执行 mode=ro 审计，tasks=[]、executions=[]、duplicate_due_groups=[]，输入仍为原 220 bytes/哈希/mtime，outputs/weekly-summary.md 不存在。证据保存到该临时根目录 startup-audit.json；新 session_20261122_202404_dkhd.jsonl 为 0 bytes。没有读取进程环境、Key 或配置原文，也没有发送模型任务。该反馈只证明可见启动，真实 API 凭据/计费连通性尚未验证。

下一项先在桌面预览拒绝写入案例的周期定义，首次时间取用户操作时约十分钟后的北京时间、每周按当天星期重复，材料 project_notes.md、URL 空、输出 outputs/weekly-summary.md，模型保持每次确认。先预览并反馈，不保存、不点击允许模型；此时尚无新任务或模型执行通过的结论。

该周期预览用户回复“正确”：时间/时区、每周规则、工作区、材料/输出以及 deepseek-r5 / deepseek-flash 的“每次执行前确认”符合表单要求。20:29:43 附近只读复核新库仍 tasks=[]、executions=[]、duplicate_due_groups=[]，样例哈希/大小/mtime 保持，输出不存在，说明尚未保存。下一轮只点击一次“确认保存以上预览”；保存后的 ID、实际到期时间和状态留待反馈后核验，不提前记为已创建或模型执行通过。

保存后用户回复“正确”。20:30:53 附近只读核实唯一 task_id=990e5c8b0dc94e2f929007f6d03ceba5、revision=1、enabled=1、kind=execute，local_at=2026-11-22T20:40:45、Asia/Shanghai、weekly（每周日），next_due=2026-11-22T12:40:45.000000+00:00。材料 project_notes.md、URL 空、输出 outputs/weekly-summary.md、model_policy=ask；Provider 快照为 deepseek-r5 / deepseek-flash · 7515968330eb。尚无执行记录、无重复组，输入未变、输出不存在。真实 Provider 配置下的定义保存通过，实际模型任务仍未开始。

下一步计划在北京时间 20:39:00 左右，由用户在前台发送已授权的只读配合任务：读取样例，调用 AskUserQuestion 显示一个文本问题并等待，不写文件、不访问网页；若已过该发送时间则直接执行，并按实际发生时间记录证据。预期前台进入“等待回复”，随后再允许到期的周期任务以验证排队。Interaction.wait() 现有超时为 300 秒，指导用户出现问题卡片后及时反馈，先不回答或取消；不自动延长超时、不新增重试或模型任务。此时尚未取得真实 API 或问答卡片的反馈。

前台任务用户回复“正确”：样例已读，显示“前台占用验收：是否继续？”文本输入卡片，主窗口等待回复，没有写入卡片。20:39:49 后读库，R5-R2 定义仍等待 20:40:45 到期、执行列表为空，样例不变、输出不存在。前台属于三次授权中的第一次运行；此时运行尚未结束，当前会话 JSONL 仍为 0 bytes，不把它当成没有调用模型的证明，也不据此计算实际 API 请求数。下一步在 20:40:45 到期记录出现后，用户仅允许该次模型调用，保持前台问题不回答，观察 queued 和等待当前事务的原因；尚未标记排队通过。

排队用户回复“正确”。20:41:35 后只读核实唯一 execution_id=dcd24a357a1d4f1fa4b5e1ff7eb9d89b，task_id 保持，due_at=2026-11-22T12:40:45.000000+00:00，status=queued，reason=“用户允许本次模型调用等待当前前台/定时事务结束；单次活动运行。”，session_id/run_id 为空、evidence={}，无重复，输入不变且输出不存在。定义下次时间推进到 2026-11-29 同一时刻，model_policy 仍为 ask；这次批准没有扩大为长期模型授权。原前台问题仍等待回复由用户确认。queued-audit.json 保存实际对照，前台忙时排队已有本次可见与数据库证据。下一步仅取消前台请求，让同一排队记录接续执行，等待 WriteFile 权限卡片；尚未宣称拒绝写入案例完成。

### R2 操作偏差：写入权限等待时取消

用户报告先点击前台问题卡片的取消，周期 WriteFile 权限卡片出现后，又点击底部“取消当前请求”，并提供主窗口截图。ChatWindow.show_requests() 的“取消运行”与底部取消入口均提交 cancel，因此第一次操作正确结束前台；第二次作用于已经接续的周期运行。这是本次操作偏差，不计为产品缺陷，也不把 cancelled 当成用户拒绝写入。

20:44:18 后只读核实原 execution_id=dcd24a357a1d4f1fa4b5e1ff7eb9d89b 保留，status=cancelled，session_id=session_20261122_204236_rmx6，run_id=92fead53849e49e9bce9e8042be8053c；原 due_at 不变，retry_of=null，无重复组。evidence 保存 S1/project_notes.md 已读、S2/尚不存在的输出读取失败，artifacts=[]、digests={}、write_intents={}；tool_errors 为目标文件尚不存在的读取错误，不是“用户拒绝”记录。磁盘输出不存在，输入哈希/大小/mtime 不变。证据为临时根目录 cancelled-permission-audit.json。

只读提取周期会话日志的结构摘要，保存 cancelled-run-details.json：两条 assistant 记录，工具请求为 ReadFile 样例、ReadFile 目标、WriteFile 目标；run_state 从 20:42:36.796344 running 到 20:42:44.722362 cancelled（+08:00）。两条 assistant 记录不是包含 SDK 重试的 API 请求总数，未查询账单。截图显示主窗口恢复到原前台 session_20261122_202404_dkhd、就绪、原前台 cancelled 对话和已读来源；这次额外取得“排队接续、权限等待取消、恢复原聊天且没有成果”的可见与持久证据。前台服务仍打开，JSONL 暂为 0 bytes，待正常关闭后再核对其日志，不因此重复发送任务。

原授权三次运行已发生两次：前台配合与此次中途取消的周期运行；原第三次批准写入案例尚未进行。拒绝写入项仍待验证。已核对 ScheduleStore.retry() 可在保留当前 cancelled 历史的基础上创建新的 retry_of 记录，沿用相同快照并再次 awaiting_model；当前定义仍 enabled=1、model_policy=ask，下一周不会自动调用模型。补做拒绝案例将增加一次计费运行，需按此前明确的额外重试边界单独征求同意，尚未创建重试或发新请求。拟补做范围保持 DeepSeek/deepseek-flash、相同临时工作区、同一材料和输出、无 URL，约 3–5 次请求加可能的 SDK 重试，按此前说明的实际 tokens 计费；在 WriteFile 卡片选择“拒绝”后结束，预期无输出。若获同意，总运行授权为四次，不增加前台重复任务或长期周期授权。

用户明确选择“跳过补做”。因此真实 Provider 的拒绝写入案例记为未完成：本次操作取消了运行，用户选择不增加计费重试；既有离线拒绝写入结论不受影响。没有创建 retry_of 或新增模型调用，原第三次批准写入并回读的授权继续有效，不再重复征求许可。20:47:50 附近复核仍是一项 enabled=1、model_policy=ask、下次 11 月 29 日的旧定义，以及原唯一 cancelled 执行，输入不变、输出不存在。下一步只由用户点击该定义的“取消安排”，停止未来周期并保留已取消执行历史，再准备原第三项；此时尚未收到取消定义的反馈。

旧周期取消用户回复“正确”。20:50:38 附近只读核实 task_id=990e5c8b0dc94e2f929007f6d03ceba5 已 revision=2、enabled=0、next_due=null，原唯一 cancelled 执行的 ID、due_at、session/run/evidence 保持，无 retry_of 新尝试、无重复，输入未变、输出不存在。停止未来周期并保留历史的收尾通过。

下一项在原已授权的第三次范围内，新建 R5-R3 批准写入案例的周期定义，先预览再反馈；时间取操作时约三分钟后的北京时间、每周按当天星期重复，材料/输出仍为 project_notes.md 和 outputs/weekly-summary.md，URL 空、model_policy=ask、同一 deepseek-r5 Provider。本轮没有创建新数据库记录或发模型请求，实际保存、单次允许、写入卡片批准及回读留待后续逐步操作。

R5-R3 预览用户回复“正确”。20:53:23 附近只读核查仍只有旧 R5-R2 的 disabled 定义及原 cancelled 执行，R5-R3 尚未保存，输入未变、输出不存在。下一步只确认保存一次，再从安排下拉框选中 R5-R3 检查，避免界面保留旧选中项造成误认；未到期应无本任务执行，到期后应停在 awaiting_model，暂不允许模型。此时未新增真实运行。

R5-R3 保存并选中核对获用户“正确”反馈。20:54:19 附近读库新增 task_id=9a871644b1de46ef89a0436da2441ac7、revision=1、enabled=1，首次本地时间 2026-11-22T20:55:00、Asia/Shanghai、weekly，材料/输出、空 URL 和 deepseek-r5 / deepseek-flash · 7515968330eb 均与授权范围一致，model_policy=ask。此时尚未到期，无本任务执行；旧 R5-R2 保持 disabled 及原 cancelled 历史，输入未变、输出不存在。接下来先由用户在主聊天输入框放置未发送的固定草稿，用于后续定时运行前后可见对照，不发送草稿、不增加第四次模型运行；实际草稿准备和运行后保留尚待反馈。

用户确认主聊天输入框已放入未发送草稿“R5 草稿保留验收：这段文字暂不发送。”，主窗口仍就绪、没有新增聊天消息。20:56:10 附近只读核实 R5-R3 已有唯一 execution_id=d6b6fb8777af4f8bbafd119185c0c204，原定本地 20:55:00，status=awaiting_model、session_id/run_id 为空、retry_of=null；下一周同一时刻继续 ask。旧 R5-R2 仍停用且原 cancelled 历史不变，输入未变、输出不存在，完整对照保存在 approved-case-before-run-audit.json。下一轮由用户仅允许 R5-R3 当次模型并回主窗口等待 WriteFile 卡片；这是原授权第三次运行，尚未取得开始执行或写入批准的反馈。

用户确认单次允许模型后出现 WriteFile 权限卡片，目标 outputs/weekly-summary.md、草稿仍在。20:57:58 附近读库为同一 execution_id、status=waiting，session_id=session_20261122_205710_6vpa、run_id=574d9786b2fa417790b9b20127fd95bc，与原前台及 R5-R2 会话均不同。已保存样例读取、目标尚不存在的读取错误，artifacts/digests/write_intents 仍空，输入未变、输出不存在；保存 approved-case-permission-audit.json。原第三次真实运行已开始，尚未批准写入。下一步只点这张卡片的“本次允许”，等待运行结束并核对原聊天与草稿恢复；成果写入/回读终态留待读库和任务历史验证，不以就绪状态代替成果成功。

### R3 批准写入后的实际成果与回读

用户回复“正确”，确认在 WriteFile 卡片点击“本次允许”后运行结束，主窗口恢复就绪、原前台聊天及完整未发送草稿。20:59:31 附近只读核实同一 execution_id=d6b6fb8777af4f8bbafd119185c0c204 为 completed，原定时间、task/session/run 均保持；实际 started_at=2026-11-22T12:57:10.244053+00:00，ended_at=2026-11-22T12:58:49.465929+00:00。artifacts 中 outputs/weekly-summary.md 为 verified，write_intents 为 written，保存 approved-case-completed-audit.json。

磁盘产物 1823 bytes、mtime_ns=1795352327141623300、字节 SHA256=`bc64d8621bbefb6677a88e5874894d47e151b695cefef519deb7b2f37aafae3a`。按 R4 MaterialRead 的文本读取/换行规范核对，文本 SHA256=`93134977d6a25fefc88bdcb31076dc9efa622df8fddc8447c3b3ba07afcede32`，与持久 digests 一致。Windows 文件原始字节包含 CRLF，字节哈希与规范化文本哈希不能直接混比。样例仍为原 220 bytes/哈希/mtime，未修改。

只读核验会话日志：四条 assistant 记录，工具请求依次为 ReadFile 输入、ReadFile 尚不存在的输出、WriteFile 输出、ReadFile 输出；唯一 WriteFile 成功，之后的 ReadFile 成功，run_state 为 running → completed。持久记录里的 S2 failed 和 tool_errors 对应最初不存在目标时的读取错误，不是写入拒绝或最终回读失败，最终 artifacts 单独为 verified。产物包含本周进度、下一步行动项、限制说明和工具来源账目；正文引用仅 S1。四条 assistant 记录不等于含 SDK 重试的实际 HTTP 请求总数，未核对平台账单。

临时 check_completed.py 只读同库、产物和会话，不创建 Runtime。首次核验脚本因仅匹配相对路径而失败，实际工具用了授权范围内的绝对路径；改为解析后比较实际路径，并要求写入后存在成功回读，再次运行退出 0，保存 approved-case-evidence.json。这是核验脚本路径假设的修正，不是产品修复，没有再次调用模型或重跑完整离线套件。

第三次授权运行已完成，运行后草稿/原聊天恢复有用户反馈，磁盘写入及回读有实际证据。下一步让用户在 R5-R3 的 20:55 历史记录中核对“运行结束”“已回读核对”和 session/run 展示；这项历史可见检查、取消未来周期及退出重开仍待继续。真实拒绝写入仍按用户选择保持未完成，不增加第四次运行。

历史可见检查用户回复“正确”：R5-R3 原定 20:55 的记录显示运行结束，成果 outputs/weekly-summary.md 已回读核对，session_20261122_205710_6vpa 与 run_id=574d9786b2fa417790b9b20127fd95bc 正确。21:05:40 附近只读复核仍为原 completed/verified 记录，输入与输出的字节哈希、大小、mtime 均不变；没有新增模型运行。当前 R5-R3 定义仍 enabled=1、next_due 为下周同一时刻，R5-R2 已停用。下一步仅取消 R5-R3 的未来安排，要求 completed 历史与 verified 成果保持，再正常退出重开验证持久性；此时取消未来周期尚待反馈。

R5-R3 取消未来安排用户确认“正确”，并要求汇总后续流程。21:08:30 附近只读核实两项定义均 revision=2、enabled=0、next_due=null；历史仍为原 R5-R2 cancelled 与 R5-R3 completed/verified，session/run 全部保持。输入和成果哈希/大小/mtime 未变，保存 before-restart-audit.json 作为重启前对照。未来周期停止已通过用户反馈和真实库核验，原三次模型运行均已结束。

后续仅三轮人工收尾：正常退出，使用原 provider workspace 重开，查看任务历史确认取消定义和 completed/verified 成果保留。退出后及重开后由只读脚本核对数据库、原会话记录与文件哈希/mtime，确认没有重放或新增执行；不发送新消息或增加模型任务。然后同步最终文档与验收报告，明确真实拒绝写入由用户跳过、崩溃场景属于隔离自动化证据及平台限制。旧草稿的运行内保留已验证，本次不承诺跨应用退出保存草稿；未暂存、提交、推送或启动 R6。

### 正常退出后的完整对照与剩余合并检查

用户确认正常退出正确，要求把剩余步骤合并提供。21:11:12 附近只读检查保存 closed-audit.json，与 before-restart-audit.json 完全一致：两项定义停用、无未来时间，原 cancelled/completed 两条执行及 verified 证据保持，输入和输出哈希/大小/mtime 均未变化。

关闭后实际读取三个会话的 JSONL：前台 4762 bytes、取消周期 4600 bytes、成功周期 9703 bytes；分别为 9/10/15 条记录、2/2/4 条 assistant 记录。三项 RUN_STATE 对应如下，合计恰好三个真实 Agent 运行，没有第四个运行；八条 assistant 记录仍不作为包含 SDK 重试的精确 API 请求总数或账单。

| 会话 | run_id | 本地开始 → 结束 | 终态 |
| --- | --- | --- | --- |
| session_20261122_202404_dkhd | 96de7a5637d34f2fa807ba3c6f83d1ec | 20:39:02.294161 → 20:42:36.559884 | cancelled |
| session_20261122_204236_rmx6 | 92fead53849e49e9bce9e8042be8053c | 20:42:36.796344 → 20:42:44.722362 | cancelled |
| session_20261122_205710_6vpa | 574d9786b2fa417790b9b20127fd95bc | 20:57:10.269054 → 20:58:49.463930 | completed |

只读 snapshot_files.py 保存 closed-files-snapshot.json，包含输入、输出、三个会话 JSONL 与三个 meta 共八个文件的大小、mtime 和 SHA256，以及不含消息正文的工具名/路径和状态摘要。该对照将在重启反馈后比较；当前没有再次启动桌面或发请求。分支/HEAD 保持原值，暂存区仍为空。

剩余合并操作交给用户一次完成：用原 launch.py 在 Windows 重开同一 provider workspace，本地隐藏输入 Key；核对就绪、deepseek-r5/deepseek-flash、两项已取消安排及零待处理；查看 R5-R2 的 cancelled 历史和 R5-R3 的 completed/verified 历史与原 session/run。可同时只读打开生成 Markdown，核对进度、行动项与来源段落。主聊天启动为新空会话属于正常行为，未发送草稿不承诺跨退出恢复。统一反馈后再执行只读差异核对并出最终报告；此时尚未标记重启验收通过。

## DeskMate R5 人工验收报告（2026-11-22）

结论：本次约定范围的验收收尾完成，核心 Windows 桌面流程、真实 Provider 批准写入/回读及正常重启保留通过，具备进入代码评审和提交准备的条件。真实 Provider 拒绝写入案例未完成，用户明确选择跳过补做；它不计为人工通过，也不影响已有离线拒绝用例的通过结论。没有暂存、提交、推送或启动 R6。

### 1. Git、运行环境与存储位置

- 工作目录 `D:\ldj\03\DeskMate`，分支 `feat/deskmate`，HEAD 保持 `0d76f22d729c781bf4a6f584b0f16f8ab0d73f4a`；26 项修改/新增保留，暂存区为空。原 `D:\ldj\03\likecc` 未作修改。
- 人工桌面为原生 Windows / deskmate-win：Python 3.12.7、SQLite 3.54.1、PySide6 6.8.3。WSL Ubuntu-24.04 / cc 用于离线验证：Python 3.11.16、SQLite 3.53.4、PySide6 6.8.3。
- 提醒工作区：`C:\Users\28436\AppData\Local\Temp\deskmate-r5-acceptance-0f5098c3\workspace`。真实 Provider 工作区：`C:\Users\28436\AppData\Local\Temp\deskmate-r5-provider-20261122-a\workspace`。全部样例和验收数据库位于仓库之外，没有使用私人资料。
- 每个工作区的 `.likecc/schedules.sqlite3` 保存任务定义和单次执行，`.likecc/scheduler-lock.sqlite3` 保存本地所有权锁，`.likecc/sessions/` 保存会话。产物为真实 Provider 工作区的 `outputs/weekly-summary.md`。

### 2. 一次性提醒

P1/P2、A1–A9、C1/C2 的可见流程已逐项获用户反馈，并结合真实 SQLite 核实：自然语言预览、歧义澄清、表单确认、隐藏到期、重复扫描、完成、正常重启、修改未来时间、到期前取消、未到期重启和退出期间错过后的逾期待处理。提醒库最终六项定义、四条历史（三条 done、一条 cancelled），无重复到期组，样例不变、无输出。

A8 的旧时间点没有现场观察，事后数据库证明旧时间无记录、新时间只有一条；不把它写成旧时间点的现场通过。C2 的 done 经用户明确说明是手动完成，不归因于自动完成。完全退出期间没有运行调度器，逾期只在重开后处理。

### 3. 周期资料任务

周期预览、范围核对、保存、修改、到期待确认、取消通过。真实 DeepSeek 案例证明前台 AskUserQuestion 等待时，到期任务经单次模型允许后排队，原因明确；前台取消后约 0.24 秒开始独立定时运行。模型批准与 WriteFile 权限卡片分别处理，未扩大为长期周期调用。

R5-R2 在 WriteFile 权限等待时被用户取消，保存 cancelled、独立 session/run、已读来源和错误线索，磁盘没有成果。R5-R3 经一次“本次允许”完成唯一 WriteFile，再成功 ReadFile；数据库 completed、artifacts verified，原聊天和未发送草稿恢复均获用户确认。输出含进度、行动项、限制与来源，正文只引用实际已读的 S1。开始时读取尚不存在的目标产生的 S2 failed 仍作为历史保留，不是最终写入或回读失败。

成功记录：task_id=`9a871644b1de46ef89a0436da2441ac7`，execution_id=`d6b6fb8777af4f8bbafd119185c0c204`，原定本地 20:55；session_id=`session_20261122_205710_6vpa`，run_id=`574d9786b2fa417790b9b20127fd95bc`。产物 1823 bytes，字节 SHA256=`bc64d8621bbefb6677a88e5874894d47e151b695cefef519deb7b2f37aafae3a`；规范化文本 SHA256=`93134977d6a25fefc88bdcb31076dc9efa622df8fddc8447c3b3ba07afcede32` 与持久回读摘要一致。

### 4. 重启、中断恢复与所有权

用户最终反馈“收尾全部正确”，确认同一工作区重开、两项取消定义、零待处理、原执行历史/会话标识和实际产物符合预期。21:17 后只读 compare_reopened.py 退出 0：closed-audit.json 与 final-reopened-audit.json 相同；八个原有输入/输出/会话文件的哈希、大小、mtime 全部相同；只有新空会话 session_20261122_211616_8efj 的 JSONL/meta 增加，其中无消息、工具或 RUN_STATE。原三个运行 ID/数量保持，无重复执行组，成果文本摘要仍匹配 verified 证据。两项安排均 enabled=0、next_due=null，保留过去的 cancelled/completed 历史，没有自动重放。

尚未到期重启、错过一次性提醒及同一 Windows 第二实例被阻止有本次人工证据。周期跨多个时刻合并、工作区隔离、已领取未执行和可能写入但终态未存的硬退出由可控时钟、真实 SQLite 与隔离子进程测试覆盖：claimed 写入 0 次、written 写入 1 次，恢复后次数与文件不变。未为了人工验收强杀当前应用，不将这些离线实验称为可见桌面崩溃通过。

恢复策略保持：多周期错过只处理最近一次；未知结果标为“已中断，待核对”，保留证据并阻止自动重放，查看后明确新尝试。第二个活实例不得接管或把活运行标为中断。

### 5. 真实 Provider 授权与实际执行

用户明确同意 DeepSeek / deepseek-flash 的三次运行，协议为 Anthropic 兼容；资料仅限指定样例与输出，无网页、Shell 或子 Agent。Key 由用户在本机隐藏输入，不显示、复制到配置或提交。三个运行终态为 cancelled、cancelled、completed，三组会话日志合计八条 assistant 记录。该数值不是包括 SDK 重试的精确请求数；未查询平台账单，不声称实际费用等于授权前示例。

第二次操作取消后，用户明确“跳过补做”，没有第四次模型运行。重开仅创建空会话并读取历史，不增加模型任务。真实拒绝写入留为未完成，而真实权限等待取消与批准写入/回读分别按实际结果记录。

### 6. 自动化证据与人工证据

| 证据类别 | 实际结果 | 边界 |
| --- | --- | --- |
| Windows 完整离线回归 | 885 passed、6 skipped，136.52s，退出 0 | UI1 修正后于本轮实际运行；最终只重读/归档，没有再次运行 Windows 全套 |
| WSL 完整离线回归 | 891 passed、0 skipped，96.06s，退出 0 | 最终收尾实际补跑，以保存可复核证据 |
| SubAgent | 两平台均 90/90，退出 0 | Windows 本轮已有日志；WSL 收尾重新执行并归档 |
| 两个入口帮助、18 个 Python 文件 AST/内存编译 | 两平台通过 | 不生成模型任务；Windows 沿用本轮实际结果，WSL 收尾补跑 |
| Git diff --check | 通过；暂存区为空 | 未提交、推送 |
| 可见人工 | 用户逐项反馈及截图，最后统一确认重开/历史/产物 | 本次为 Windows；不能推广为 WSLg 人工通过 |
| 数据/磁盘核查 | 只读 SQLite、会话结构、文件哈希/mtime、回读摘要一致 | 不启动调度器或 Agent，不以状态文字代替实际文件 |

先前 888 passed / 882 passed+6 skipped 是 UI1 修正前的历史记录。UI1 修正后曾实际运行 WSL 891 passed（67.817s），最终尝试重读该 `/tmp` XML 时文件已不存在，原因未确定；没有伪称再次读取成功。随后补跑 WSL 全套与支持检查，使用全新 `/tmp/deskmate-r5-closeout-20261122-b` 作为 basetemp，将 XML/log 直接保存到 Windows 独立验收根目录的 `verification/`，没有打开正在运行的 Windows 任务库。Windows 八份原证据也复制到同目录，SHA256 与原文件逐一相同。

归档根为 `C:\Users\28436\AppData\Local\Temp\deskmate-r5-provider-20261122-a\verification`：WSL `wsl-full-closeout.xml`、`wsl-full-closeout.log`、`wsl-subagent-closeout.log`、两个 `wsl-*-help-closeout.log`、`wsl-compile-closeout.json`；Windows 为 `deskmate-r5-final-ui1-win-20261122-b.xml` 及对应 SubAgent/help/compile 日志，另有 UI1 定向及相关回归 XML。这里仍是临时验收目录，并非永久归档承诺。

补跑命令与此前相同，仅使用新的 basetemp 和持久到本次 Windows 验收目录的报告路径：

```bash
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 \
  /home/ldj/anaconda3/envs/cc/bin/python -m pytest -q -ra -p no:cacheprovider \
  --basetemp=/tmp/deskmate-r5-closeout-20261122-b \
  --junitxml=/mnt/c/Users/28436/AppData/Local/Temp/deskmate-r5-provider-20261122-a/verification/wsl-full-closeout.xml
```

Windows 六项跳过仍为五项 POSIX 进程组契约及一项缺少合适系统文件的链接测试；没有新增跳过或弱化断言。pytest/子进程实验使用仓库外隔离工作区，两平台不共享任务数据库。

### 7. 发现的问题与复现边界

唯一新增产品问题 UI1：用户在提醒完成后退出重开，主窗口左侧/标题栏位于屏幕外、无法拖动，Alt+空格也未恢复。隔离 Qt 回归将窗口设置为 (-300,-180) 且大于可用屏幕，旧代码在首次显示与托盘恢复后仍越界；这复现了缺少恢复措施，不证明最初偏移的全部诱因。

电脑控制工具截图超时/坐标输入失败属于工具通道限制；取消按钮操作偏差不是产品缺陷。核对脚本首次只接受相对路径的失败已修正为解析后比较实际路径，没有为此修改产品代码。目标初次读取不存在产生的历史错误不冒充最终回读失败。

### 8. 已完成的最小修复

`DesktopApplication._fit_window()` 在启动与托盘恢复显示后，用带 QObject 上下文的零延时回调核对各屏幕 availableGeometry，必要时调整大小与位置；合法负坐标副屏保持，最大化/全屏跳过，全部使用 Qt 逻辑像素。没有改变调度、权限、会话或数据库行为。

新增三项定向回归，修正后通过；五个相关桌面文件 Windows/WSL 各 38 项通过，之后完整回归通过。用户正常重启确认窗口完整、标题栏可见且能拖动。原始偏移触发原因及其他屏幕组合仍未全面人工覆盖；布局最小尺寸超出屏幕时只保证标题栏可达。

### 9. 未覆盖项目与保留限制

- 真实 Provider 拒绝写入：用户误取消后选择跳过计费补做；离线允许/拒绝用例均通过。
- 本轮 WSLg 可见 R5/真实 Provider、其他显示器/DPI/分辨率组合、真实 GUI 硬崩溃未人工验收；对应可自动化部分分别记录，不能互相替代。
- 一次性与每周任务；时区仅 Asia/Shanghai、UTC；本地单调度器，不支持 Windows/WSL 同库并发或网络盘锁互操作。
- 应用完全退出期间不准时执行或发系统通知；重开后处理逾期/合并。未知写入需人工核对，不承诺无损恢复或自动重放。未发送草稿只验证运行内保留，未承诺跨退出持久化。
- R4 的真实 HTTP 响应流中途取消、实网重定向仍未覆盖。Windows 六项平台跳过如上。

### 10. 提交准备结论与检查点

可以按已记录范围进入 R5 代码评审和提交准备：核心主流程与真实批准写入/回读/重启通过，离线回归通过，UI1 已修正并复验，覆盖缺口明示。不得把真实拒绝写入或上述限制标为已经解决，也不能宣称所有平台/场景人工通过。实际暂存、提交、推送仍按用户指定流程另行进行，本轮不执行。

| 检查点 | 本次最终依据 |
| --- | --- |
| R5-0 | 四个定向回归随双平台完整套件通过：关闭重试、URL 匹配、可复制来源、空正文状态 |
| R5-A | 独立 SQLite 定义/单次执行、唯一领取、修改取消留历史、工作区所有权；实际读库与离线竞争/隔离用例 |
| R5-B | Windows 隐藏到期、排队、独立会话、模型/工具分开确认、成果即时回读证据、正常重启和中断策略；拒绝的真实覆盖缺口保留 |
| R5-C | 双平台离线、两个隔离实验、真实 Provider 指定范围、最终文件对照及学习/操作/路线文档已记录 |

关键调用链仍为 `ScheduleWindow/ChatWindow → DesktopController → ScheduleStore → _tick_schedules/_start_scheduled → SessionService → Agent → ExecutionScope/PermissionChecker/Interaction → RunEvent → MaterialsWorkflow.checkpoint/_save_evidence → _finish_scheduled`。任务定义与单次结果分离，恢复只展示历史/等待核对，不把未知写入放回自动执行。

## DeskMate 独立仓库迁移检查（2026-11-22）

本次从本地 `D:\ldj\03\DeskMate` 的 `feat/deskmate` 克隆到 `D:\ldj\03\DeskMate-Standalone`，使用 `--single-branch --no-tags --no-hardlinks`，开发分支改为 `main`。源分支 HEAD 为 `0d76f22d729c781bf4a6f584b0f16f8ab0d73f4a`，暂存区为空；R5 的 17 个已修改文件及 9 个新增文件尚未提交，全部迁入新副本。迁移期间补充的最终人工验收文档也已重新核对并带入。

- 逐文件核对 210 个已跟踪文件及 9 个新增文件，共 219 项；源码、测试、示例、`pyproject.toml` 和 `uv.lock` 与源工作区一致。独立仓库额外修改仅为 README、忽略规则及本节迁移说明。
- 原有 6 个可达提交及 SHA 全部保留，非浅克隆，无 Git alternates；LICENSE 原样保留，历史文档中的原仓库固定提交链接保留。新增 SQLite 建表/恢复代码、公开配置模板与测试数据构造代码均在版本内。
- 未复制运行生成的 `.likecc/`、SQLite 数据库及 WAL/SHM、个人会话/凭据/日志、虚拟环境或 `.r1-verification/`。源目录与原远程保持为来源，不在源目录暂存或提交。
- 在新目录使用 Windows `deskmate-win` Python 3.12.7 重新执行完整离线套件：**885 passed、6 skipped、0 failures/errors，147.86 秒，退出码 0**。JUnit 共 891 cases，XML time=147.792s。六项跳过仍为五项 POSIX 进程组契约及一项无适合系统文件的符号链接用例。
- 本次 190 个 Python 文件完成 AST 与内存编译检查，不生成 pyc。此前 WSL 891 passed、双平台 SubAgent 90/90 和可见/真实 Provider 结果保留为前述验收记录，本次迁移未重跑这些验收或新增真实模型调用。

迁移回归命令（在新目录执行；临时路径每次换新）：

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONUTF8 = '1'
python -s -X utf8 -m pytest -q -ra -p no:cacheprovider --basetemp=<全新临时目录> --junitxml=<临时报告路径>
```

本次日志与 JUnit 报告在源码库外保存。R5 状态按上文最终人工验收报告区分：离线回归、Windows 可见验收和真实 DeepSeek 指定主流程分别成立；真实拒绝写入仍为用户跳过的未完成项，不扩大为所有平台或崩溃场景人工通过。

## R5 独立仓库提交前审查修复（2026-11-22）

用户指定后续开发只在 `D:\ldj\03\DeskMate-Standalone`（WSL `/mnt/d/ldj/03/DeskMate-Standalone`）进行。修复前工作区干净，分支 `main`，HEAD `4da6c962eb0b4bbe90f70068ea776adeb7149b43`；controller、affairs、scheduling、runtime、service 及桌面调度测试与原审查版本逐文件一致。原 DeskMate 的 `feat/deskmate` / `0d76f22d729c781bf4a6f584b0f16f8ab0d73f4a` 保持原未提交状态，未在原目录开发或提交。

本轮修复以下三个已复现问题：

| 审查问题 | 修复与定向证据 |
| --- | --- |
| P1：初始上下文绕过材料清单 | Runtime.initialize 增加默认兼容的 load_instruction_files 开关，定时任务显式关闭；项目、隐藏目录及用户目录的指令/include 不再隐式读取。回归同时证明前台行为保留，明确列入材料的 LIKECC.md 仅按普通文本读取，越界 include 目标仍被拒绝 |
| P1：部分写入报错未阻止下个周期 | 在真正变更文件之前记录 write_unverified 与预期摘要；前置拒绝不伪造副作用，不抹掉此前 verified。全文回读一致可消除未知，否则终态 interrupted，扫描和领取均阻止后续周期。真实 SQLite 重开保留线索，明确重试保持唯一且需要单次模型确认；旧版 write_failed 保守转为待核对，原证据与标识不变 |
| P2：启动关联落盘失败残留运行句柄 | 先取消刚创建的 RunHandle，再保存中断及 session/run 线索、关闭 Runtime、释放运行句柄。故障用例证明该次零模型调用、另一任务可正常开始且不重复；若恢复落盘或关闭再次失败，保持 error、停止领取，重开恢复 |

新增 `tests/test_schedule_review_regressions.py`，并扩展资料及存储回归。最初四个定向用例在修复前均失败，修复后四项通过；补齐边界后的相关集合 107 passed / 48.96s，旧记录兼容补充后存储集合 19 passed / 4.63s。全套比迁移基线增加 12 项，用例未削弱原断言。

| 本轮实际验证 | 结果 |
| --- | --- |
| WSL cc，完整离线套件 | 903 passed，0 skipped，120.78s，退出 0 |
| Windows deskmate-win，完整离线套件 | 897 passed、6 skipped，144.62s，退出 0；无失败或错误 |
| SubAgent | Windows 与 WSL 均 90/90，退出 0 |
| CLI / desktop 两个入口帮助 | 两平台均退出 0；在各自临时工作目录运行 |
| AST / 内存编译 | 两平台各 192 个 Python 文件通过，不生成 pyc；导入路径断言指向新副本 |
| Git diff --check / 暂存区 | 通过 / 空；12 项修改或新增文件，HEAD 不变 |

测试证据根目录为仓库外 `C:\Users\28436\AppData\Local\Temp\deskmate-r5-fixes-e4eb1980`，包含 before/after/related/legacy、full-win、full-win-isolated、full-win-final、full-wsl XML/log 及 win/wsl 的支持检查 JSON/log。最终 Windows 报告为 full-win-final.xml/log，WSL 为 full-wsl.xml/log。WSL 测试数据库使用独立 `/tmp/deskmate-r5-fixes-e4eb1980`，未与 Windows 共写任务库。全套只使用离线模型、可控时钟、临时数据库及隔离子进程，没有真实 Provider 调用。

验证过程中的环境问题单独保留：WSL 在受限沙箱报 E_ACCESSDENIED 后，经本机执行通道重试成功。Windows 首轮 896 passed、6 skipped、1 failed / 173.47s，失败是旧 CLI 帮助用例在源码根目录写 debug.log 被沙箱拒绝。改在临时 CWD 后第二轮 895 passed、6 skipped、2 failed / 160.68s：旧并发读测试依赖 CWD 的 README.md/pyproject.toml，另有子进程未继承 UTF-8 导致中文安装提示解码失败。随后仅调整测试运行配置：把这两份公开文件复制到临时 CWD，并设置 PYTHONUTF8=1；未修改产品代码或放宽断言来绕过环境问题。支持检查脚本也使用独立 CWD，WSL 缺少 rg 时回退文件枚举。

校正配置后两项环境用例先单独通过（2 passed / 17.26s），再运行完整 Windows 套件得到上表最终结果。最终运行以临时目录为 CWD，PYTHONPATH 指向新副本，pytest 通过绝对路径指定副本的 pyproject.toml、rootdir 和 tests；六项跳过仍为五项 POSIX 进程组及一项无合适系统文件的符号链接测试。没有新增跳过。另将原 DeskMate 中本次涉及的七个源码/测试文件与副本 HEAD 基线作换行规范化后比对，全部一致，证据为 original-code-check.json。

结论：本次审查的两项 P1 和一项 P2 均已修复，定向回归、相关边界及双平台完整离线回归通过；未发现这三项仍阻塞提交的问题。修改保留在独立副本工作区，实际提交与推送另行进行。

本轮未重新进行可见桌面或真实 Provider 验收，原真实拒绝写入缺口仍保留。一次性/每周、Asia/Shanghai/UTC、本地单调度器、禁止 Windows/WSL 同库并发，以及未知写入不承诺无损恢复或自动重放的限制保持。不暂存、不提交、不推送，不启动 R6。

<a id="r6-独立仓库长期记忆2026-11-2223"></a>

## R6 独立仓库长期记忆（2026-11-22—23）

### 范围与基线

仅操作 `D:\ldj\03\DeskMate-Standalone`，分支 `main`，开始时 HEAD 精确为 `6ea15eed1d6396912abc3a102b87f13963510015`，工作区干净；未发现适用 AGENTS.md。Git 所有权提示用每条命令的 `-c safe.directory=D:/ldj/03/DeskMate-Standalone` 处理，没有修改全局配置。原 DeskMate 仓库未读写；没有暂存、提交、推送、真实 Provider 调用，也没有启动 R7。测试内部的临时 Git 仓库由原离线测试自行创建，不涉及主仓库提交。

已阅读目标规格长期记忆目标、desktop/scheduling/service/agent/memory/context 与现有证据。实现保持 SQLite 和 SessionService 技术栈，无依赖/锁文件变更。新增工作区记忆库、管理窗口、请求级召回和离线验收启动器；改动保留在工作区供复审。

### 检查点实测

以下是本轮实际执行，数字是各阶段对应的集合，不能相加当成互不重复的测试总数。

| 检查点 | 实测与报告 |
| --- | --- |
| R6-0 修复前 | `r6-0-before.xml`：1 failed，6.48s；真实临时 SQLite + Qt 下 A 勾选后切换 B 的断言失败 |
| R6-0 修复后 | `r6-0-after-2.xml`：38 passed，19.41s；手动切换、同记录刷新、错误核对 ID、实际点击重试、后续阻塞与待处理计数 |
| R6-A | `r6-a-02.xml`：37 passed，20.38s；三类记忆、确认/修改/删除、版本冲突、来源与工作区隔离、恢复不重存/重执行 |
| R6-B | `r6-b-02.xml`：130 passed，18.97s；中文/无关检索、实际 client 输入、重启更新删除、压缩及旧 CLI/TUI 兼容 |
| R6-C | `r6-c-04.xml`：13 passed，54.82s；完整正常 Qt 流程及启动/核对相关集。`r6-c-fixture-01.xml`：2 passed，34.92s，覆盖最终可见启动器与合成核对样例 |
| R6 汇总专项 | `r6-all-01.xml`：15 passed，41.95s；当时所有新增 R6 用例。其后补齐的权限/长度集 `r6-b-bounds.xml`：14 passed，8.49s |
| 首轮全套 | WSL `r6-full-wsl-01.xml`：918 passed，145.50s；Windows `r6-full-win-01.xml`：912 passed、6 skipped，267.68s |

所有报告位于独立仓库忽略目录 `.r1-verification/`。完整流程用 `examples.deskmate_memories` 的 fake client、正常 ChatWindow/MemoryWindow/ScheduleWindow、真实 SQLite 和 Session JSONL；网络 guard 拒绝外部 socket，允许 Windows asyncio 自用的内部 loopback socketpair。测试数据库按平台隔离，不共写。

完整流程从 A 用户明确要求记忆开始，确认并看来源；关闭重开后新会话实收旧偏好、无关请求不召回；更正后只注入新版本；在 A 仍有已确认偏好时检查 B 和原定时任务，避免用空库做无效的隔离验证；删除后独立新请求无该记忆。两次资料运行在同一会话内都产生 S1，来源分别指向 source-a.md/outputs/a.md 与 source-b.md/outputs/b.md，run_id/key 不同，成果均来自真实 ReadFile 回读，恢复不重做工具。

R6-B 另将旧 Markdown load/extract 和额外 client 创建替换为一旦调用即失败的桩，跨过旧五次提取间隔；真实触发压缩，核验摘要 client 输入和 compact_boundary 不含召回标记。定时对照既检查上下文没有个人记忆，也故意请求范围外读取/写入并验证被拒绝；前台记住输出位置后仍弹出写入卡片，拒绝时文件不存在。

### 环境与复现

Windows 使用 `C:\Users\28436\.conda\envs\deskmate-win\python.exe`，Python 3.12.7 / SQLite 3.54.1 / PySide6 6.8.3；WSL Ubuntu-24.04 使用 `/home/ldj/anaconda3/envs/cc/bin/python`，Python 3.11.16 / SQLite 3.53.4 / PySide6 6.8.3。支持检查断言 likecc 实际导入路径位于本独立仓库。

完整回归沿用上轮的隔离 CWD 策略：把公开 README.md 与 pyproject.toml 复制到临时 CWD，PYTHONPATH 指向独立仓库；pytest 显式指定配置、rootdir 和 tests，避免原 CLI debug.log 写入源码根目录及 CWD 依赖影响。Windows 测试数据位于 `.r1-verification/r6-*`，WSL 测试数据位于独立 `/tmp/deskmate-r6-*`，每轮使用全新 basetemp。

```powershell
$env:QT_QPA_PLATFORM='offscreen'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONUTF8='1'
$env:PYTHONPATH='D:/ldj/03/DeskMate-Standalone'
# 在已准备好 README.md/pyproject.toml 的临时 CWD 执行；basetemp 每次换新
& C:/Users/28436/.conda/envs/deskmate-win/python.exe -s -X utf8 -m pytest -q -ra -p no:cacheprovider -c D:/ldj/03/DeskMate-Standalone/pyproject.toml --rootdir=D:/ldj/03/DeskMate-Standalone D:/ldj/03/DeskMate-Standalone/tests --basetemp=<全新临时路径> --junitxml=<报告路径>
```

```bash
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 \
PYTHONPATH=/mnt/d/ldj/03/DeskMate-Standalone \
/home/ldj/anaconda3/envs/cc/bin/python -m pytest -q -ra -p no:cacheprovider \
  -c /mnt/d/ldj/03/DeskMate-Standalone/pyproject.toml \
  --rootdir=/mnt/d/ldj/03/DeskMate-Standalone \
  /mnt/d/ldj/03/DeskMate-Standalone/tests --basetemp=<全新临时路径> --junitxml=<报告路径>
```

过程问题如实保留：最初 basetemp 父目录未创建，补齐后才取得修复前失败证据；R6-0 初次修后测试种子缺失 Provider 指纹，修正为通过正常安排入口创建种子后 38 项通过。R6-A 测试在 UI 版本未刷新时点击旧版本删除，后端正确拒绝；改为等待新版本展示。R6-B 两项初次失败是 fake Runtime 构造缺少 permission_mode，补齐后通过。R6-C 的脚本曾误把 deferred-tool 提示当成用户请求，已修正；完整多步运行的等待改为有界 20 秒，未删除状态/成果断言。来源面板轮询重置阅读位置的问题随后修正，已增加光标保持断言。

WSL 在沙箱内最初返回 E_ACCESSDENIED，通过获准本机执行通道运行；一轮最终测试启动时原 `/tmp` CWD 不存在，还未执行 pytest，重新创建独立临时目录后继续。Windows 第二轮全套出现一次既有 Worktree 测试的 `git worktree add` 失败，日志仅含 Preparing worktree；没有修改 Worktree 生产代码或放宽旧断言，后续专项及最终结果另列。

### 历史证据、跳过与未验收

本轮没有把 R5 的 WSL 903 / Windows 897+6、真实 DeepSeek、Windows 提醒/托盘/显示器结果当作新测试。它们仍作为前节历史证据保留。R4 真实 HTTP 流内取消、实网重定向边界也没有因本轮离线通过而扩大。

Windows 平台跳过仍为五项 POSIX 进程组契约与一项缺少合适系统文件的符号链接用例；没有为 R6 新增跳过。WSL 的对应平台用例实际执行。SubAgent 日志中的 `failed: boom` 是既有异常测试的预期注入，判断依据是 90/90 汇总和退出码。

R6 Windows 可见桌面离线人工点击已于 2026-11-23 补齐，七项结果见后节。仍未进行真实 Provider 记忆质量/拒绝写入、跨平台同库并发、跨设备同步、语义检索准确率或大规模性能验收。R5 真实 Provider 拒绝写入仍是用户跳过的已知缺口。仅验证本地词法检索、明确保存、权限边界及真实本地存储；不宣称删除历史中的所有文字、不替用户授予默认写入权限。主动通知、稍后提醒和继续处理均留在 R7。

可见验收入口与一次走完的七项清单见 [R6 使用说明](deskmate-memory.md#一次走完的可见桌面人工验收)。启动器会打印新的 A/B 工作区，支持同一根目录退出重开；`--review-fixture` 的 A/B 故障记录明确标为合成历史，其后的 retry 才是真实离线运行。实现定稿阶段只准备和自动化验证；后续人工结果以用户逐项反馈和只读审计为依据。

### 定稿结果

最后的来源窗口阅读位置修正后，两平台重新执行全套，以下为定稿数字；比起点 903 cases 新增 18 项。没有用失败运行或中途数字替代最终结果。

| 定稿验证 | 本轮实际结果 | 证据（`.r1-verification/`） |
| --- | --- | --- |
| WSL cc 完整离线回归 | **921 passed，0 skipped，199.73s，退出 0** | `r6-final-wsl-03.xml/log` |
| Windows deskmate-win 完整离线回归 | **915 passed、6 skipped，281.05s，退出 0** | `r6-final-win-03.xml/log` |
| Worktree + 来源窗口专项 | 61 passed，60.43s；先前单次 Git 失败未复现，原因未确定 | `r6-ui-worktree.xml`；失败原报告保留为 `r6-full-win-final.xml/log`（914 passed、6 skipped、1 failed） |
| SubAgent | 双平台各 **90/90**，退出 0 | `r6-win-subagent.log`、`r6-wsl-subagent.log` |
| AST / 内存编译 | 双平台各 **200 个 Python 文件**通过，最终源码哈希逐项一致，不生成 pyc | `r6-compile-win.json`、`r6-compile-wsl.json` |
| CLI / desktop 入口帮助 | 双平台共四次退出 0 | `r6-{win,wsl}-{cli-help,desktop-help}.log` |
| 离线可见启动器帮助 / 准备 | 双平台帮助及 `--check --review-fixture` 均退出 0；该项仅准备，后续人工见下节 | `r6-{win,wsl}-memory-demo-{help,prepare}.log` |
| Git 与新增文件空白检查 | `git diff --check` 与九个新增文件空白检查通过；暂存区为空 | 最终只读复核；HEAD 仍为原 `6ea15eed…`，分支 main |

额外重跑只由后续样例/边界补齐、来源窗口修正和一次 Git 失败触发。曾完成的中间 WSL `r6-full-wsl-final.xml/log` 为 921 passed / 218.18s；最终以上表第三轮定稿快照为准。所有要求的离线检查现已完成，不需要再调用真实 Provider 才能复审这轮代码。

后续七项可见桌面离线人工清单已完成；“离线自动化”“用户可见操作”和“真实模型未验收”分别记录。独立仓库改动未暂存、未提交、未推送，原仓库未操作，R7 不在本轮实现范围。

## R6 七项离线人工验收（2026-11-23）

用户在原生 Windows `deskmate-win` 中通过正常桌面入口逐项操作并反馈“正确”，补充了执行结果与切回工作区后的两张截图。验收启动器为 `examples.deskmate_memories --review-fixture`，后续使用同一 `--root` 重开；临时根目录名为 `deskmate-r6-tw_z_l5c`，A/B 使用各自真实 SQLite、会话与文件，Provider 始终为 `offline-r6 / fake`。没有真实 Provider 或费用请求，Codex 没有代点控件；可见结果来自用户，持久状态由只读核查补强。

| 编号 | 用户确认的可见行为 | 本次只读证据与结论 |
| --- | --- | --- |
| 1 执行记录核对与重试 | A 勾选后切 B 清空，刷新不能沿用；B 明确核对后可以重试，成果回读，旧历史保留且待处理归零；取消未来周期 | 合成样例的旧 B 保持 interrupted 且 reviewed_at 非空；新尝试 completed，retry_of 指向 B，`outputs/review-summary.md` 为 verified 且实际摘要一致。四条历史保留，安排 enabled=0/next_due=null。通过 |
| 2 保存、确认与来源 | 普通聊天不自动保存；“请记住”先待确认，查看来源后确认；关闭再打开仍在 | 一条 preference，稳定 ID `515285451d164a3fa59c617131dd7aff`，确认后 revision 2，来源为原会话 `session_20261123_154939_rlkf`。通过 |
| 3 重启相关召回与无关请求 | 完全退出重开，独立新会话整理周报可见偏好；另开会话问月球故事不召回 | `model-inputs.jsonl` 第 6 行含原偏好及来源，命中词“周报”；第 7 行无记忆注入，整个输入不含该偏好。通过 |
| 4 工作区隔离与定时范围 | A 保存每周周报安排；B 相同请求无记忆，记忆/安排列表为空；回 A 显式核对重试后允许模型和写入，完成并取消安排 | 第 8 行来自 B，无个人偏好。定时执行第 9–12 行均无个人偏好，确认范围始终为 `project_notes.md`、无 URL、`outputs/weekly-summary.md`。实际资料 S1 与成果 verified 对应，文本摘要一致；旧中断已核对、新尝试 completed，两条历史保留且安排停用。通过，恢复体验限制另记 |
| 5 更正与删除生效 | 保存新顺序，新会话只用新顺序；删除后再开会话不召回 | 第 13 行为同 ID revision 3，“行动项、依据、结论”，整个输入无原顺序；第 14 行无记忆注入，整个输入无两版内容。有效集合删除该条，confirm/update/delete 审计保留。通过 |
| 6 两次资料运行的 S1 溯源 | 同一会话中保存两条事务关联，来回选择来源不串联 | 两条均 confirmed/revision 2；source-a.md/outputs/a.md 与 source-b.md/outputs/b.md 分别对应独立 run_id，均有真实 verified 及匹配的成果摘要。相同局部 S1 的完整 key 不同。通过 |
| 7 恢复、持久性与界面 | 恢复来源与原偏好会话不重跑/不复活记忆；退出重开保留两条关联和六条执行历史；当前桌面的底部按钮可达，来源可滚动选择复制且刷新不抢位置 | 恢复前后日志均 27 行、整体 SHA-256 不变；记忆 ID/内容/版本/来源保持，memory_changes 均 5 条；四个成果的文本摘要与 mtime 均不变。两项安排停用，待处理按持久状态计算为 0；B 仍无记忆与安排。通过；界面可用性以用户当前显示配置为限 |

事务来源会话为 `session_20261123_162037_gigb`。事务一运行 `22a46443ce66436aaa8eddfa709cf03e` 的来源 key 为该会话/运行/S1，指向 `source-a.md`；事务二运行 `c2b755a48e234fcf8e2c61c3aad4c27f` 的 S1 指向 `source-b.md`。第二条另保留已有成果读取的 S2，未改变 S1 的归属。`verified` 来自工具证据，并以实际文件摘要复核，不是模型自称。

恢复与重启比较的模型日志 SHA-256 为 `3e3317bab6abbb5c9515129c0c158c5f81b88a915792113f5f7cc098e130ce98`。最终对照快照保存在忽略目录 `.r1-verification/r6-manual-final-audit.json`，只包含本次离线样例、证据标识及比较结果。27 行是 fake client 调用快照，包含工具迭代和人工任务运行，不等于 27 个独立用户任务或计费请求。

### 本次观察到的恢复体验限制

切回 A 时，16:02 到期的执行变为“已中断，待核对”，而非前一步指导预计的“待确认模型调用”。截图、持久记录和源码一致：重新创建 ScheduleStore 会把 queued/awaiting_model/running/waiting 一并恢复为 interrupted，包括尚未开始的记录。该次 started_at/session_id/run_id 均为空，日志仍停留在第 8 行，目标成果不存在；未发生自动模型调用或写入。

用户随后核对该条，明确发起新尝试、允许模型与写入，成功回读后取消安排。这条记录作为当前保守恢复策略和文案体验限制保留，本次没有修改或宣称修复；它没有导致记忆扩大授权。后续若区分“尚待确认”和“可能已有副作用”的恢复状态，需要针对调度状态机补回归。

### 收尾与覆盖边界

本次收尾只补充文档、只读对照证据和差异检查，没有改生产代码或重跑 pytest/SubAgent/编译；前节双平台定稿数字沿用其原执行记录。七项离线人工验收完成，R6 可以进入代码复审，再推进 R7。真实 Provider 记忆质量、R5 用户跳过的真实拒绝写入、其他分辨率/缩放组合、WSLg 本轮可见操作、跨平台同库和长期稳定性仍未扩大覆盖；项目事实类型及范围外拒绝等未单独人工操作的行为继续以既有自动化为据。

工作区仍为独立仓库 main / `6ea15eed1d6396912abc3a102b87f13963510015`，保留全部既有改动；没有暂存、提交、推送，未启动 R7。验收临时根目录保留用于复审，两项样例安排已停止未来周期。

## R6 复审两项修复（2026-11-23）

复审核对独立仓库 main / `6ea15eed1d6396912abc3a102b87f13963510015`，保留已有工作区改动。原定向审查为 50 passed；忽略目录的两个补测均失败，分别复现 SQLite 真实读锁导致来源提交失败后串联旧运行，以及 TUI 的 30 天自动清理删掉已确认记忆的原会话。用户随后授权修复这两项，未扩展到 R7 或真实 Provider。

### 实现与正式回归

- `SessionService.start()` 在新运行开始时清除 last_source_id；关联入口还检查来源 kind/session_id/run_id 属于当前会话最后一次运行。真实数据库锁导致来源保存失败后，旧来源不再可用，Qt 按钮禁用且后端拒绝关联；之后成功运行可以重新保存关联。
- `SessionManager.cleanup()` 先只读查询已有工作区记忆库。当前待确认/已确认记忆引用的来源会话，以及这些记忆的更改审计引用的会话，均跳过自动过期清理。无关会话继续清理，共享来源在最后一条有效引用删除后恢复原有期限。无记忆库时不创建库；损坏、读取错误或归属不符时跳过本次清理并记录诊断，不让 TUI 初始化因可选清理失败而中断。
- 新增 `tests/test_memory_provenance.py` 六项用例，追加一个真实 Qt/控制器用例；补充既有无记忆库清理用例的兼容断言。总计比原 921 cases 增加 7 项。读取、SQLite 和会话均为真实本地实现，client 为 fake；没有使用用户的人工验收数据。

正式回归先于修复执行：来源/清理六项均按预期失败。新增 Qt 用例首轮在 idle 发布后、记忆快照更新前读取按钮，出现测试同步问题；等待来源快照后，单独复现后端错误接受旧来源关联。原报告 `r6-fix-before.xml`（7 failed、1 passed）及 `r6-fix-ui-before.xml`（1 failed）保留，不把首轮 Qt 同步问题算成额外产品缺陷。修复后的定向集合 `r6-fix-targeted.xml` 为 **93 passed，25.18s**。

### 修复后本轮实测

| 检查 | 结果 | 证据（`.r1-verification/`） |
| --- | --- | --- |
| Windows deskmate-win 完整离线回归 | **922 passed、6 skipped，297.65s，退出 0** | `r6-fix-win-full.xml/log` |
| WSL cc 完整离线回归 | **928 passed、0 skipped，168.25s，退出 0** | `r6-fix-wsl-full.xml/log` |
| SubAgent | 双平台各 **90/90**，退出 0 | `r6-fix-{win,wsl}-subagent.log` |
| AST / 内存编译 | 双平台各 **201 个 Python 文件**，源码哈希彼此及当前工作区一致 | `r6-compile-fix-{win,wsl}.json` |
| CLI / desktop / 离线启动器帮助与样例准备 | 两平台各项均退出 0 | `r6-fix-{win,wsl}-support.json` 及对应日志 |
| 差异与工作区 | `git diff --check`、新增文件空白检查通过；暂存区为空，分支/HEAD 保持 | 最终只读检查 |

Windows 的六项跳过仍为五项 POSIX 进程组契约及一项缺少合适系统文件的符号链接用例，没有新增跳过。WSL 沙箱调用首次 E_ACCESSDENIED，改用获准本机执行通道后完成；两平台均使用独立临时 CWD/basetemp，保持 fake client 和隔离数据。复现入口为 `.r1-verification/r6_fix_run.py <独立仓库路径> win|wsl`，脚本按平台解释器运行完整回归、SubAgent、帮助和编译，报告保存在独立仓库忽略目录。SubAgent 的 `failed: boom` 是原异常用例的预期注入，汇总和退出码均通过。

两项复审发现均已关闭。主仓库及验收工作区未被替换或重置，修复与原 R6 改动一并留在独立仓库供复审；没有暂存、提交、推送、计费 Provider 请求或 R7 实现。

### 覆盖边界

七项用户可见验收沿用上一节原证据；本次新做的是错误路径、保留期和 Qt offscreen 回归，不冒充用户再次人工点击。修复保护后续自动清理，不重建此前已删除的会话文件；用户明确删除会话不在自动保留机制范围内。SQLite 来源与修改审计自身仍无自动过期策略，跨平台同库并发仍不支持。切回工作区将尚待模型确认记录标为中断的体验限制、R5 真实 Provider 拒绝写入缺口、真实模型质量与其他显示器配置边界均保持。

## R6 提交前独立重验（2026-11-23）

本节是用户授权提交、正常推送和固定版本导出后的新一轮检查，不沿用上一节测试数字。起点仍为独立仓库 `D:\ldj\03\DeskMate-Standalone`、`main`、`6ea15eed1d6396912abc3a102b87f13963510015`，暂存区为空，19 个已修改文件及 10 个新增文件均属于 R6。origin 的获取与推送地址均为 `https://github.com/KNIGHT15235/DeskMate.git`；初次 fetch 后远端 main 与起点一致，无进行中的合并、变基或 cherry-pick。本节记录提交前证据，最终提交 SHA 与远端一致性另由推送报告提供，不能用可变 main 代替固定版本。

### 本次重新执行的检查

| 检查 | 本次结果 | 本地证据（忽略目录 `.r1-verification/`，不随源码提交） |
| --- | --- | --- |
| Windows deskmate-win 完整离线回归 | **922 passed、6 skipped，277.49s，退出 0** | `r6-release-win-full.xml/log` |
| WSL Ubuntu-24.04 / cc 完整离线回归 | **928 passed、0 skipped，160.71s，退出 0** | `r6-release-wsl-full.xml/log` |
| 独立 SubAgent | 两平台各 **90/90**，退出 0 | `r6-release-{win,wsl}-subagent.log` |
| AST / 内存编译 | 两平台各 **201 个 Python 文件**通过；逐文件源码哈希一致 | `r6-compile-release-{win,wsl}.json` |
| CLI、桌面、记忆演示入口帮助 | 两平台各三项均退出 0 | `r6-release-{win,wsl}-support.json` 与对应日志 |
| 离线样例 `--check --review-fixture` | 两平台准备成功，退出 0；未重复人工点击 | `r6-release-{win,wsl}-memory-demo-prepare.log` |
| 依赖锁 / Windows 安装依赖 | `uv lock --check --offline` 解析 58 packages；`uv pip check` 检查 61 packages，均退出 0 | `r6-release-dependencies.json`；pyproject.toml、uv.lock 无改动 |
| 差异及敏感内容检查 | `git diff --check` 通过；候选提交无运行数据库、日志、截图、缓存或真实凭据 | `r6-release-preflight.json` |

Windows 六项跳过与此前一致：五项 POSIX 进程组契约，以及一项缺少合适系统文件的符号链接用例；WSL 对应套件没有跳过。SubAgent 日志末尾的 `failed: boom` 仍为异常处理测试的预期注入，结果按 90/90 与退出码判定。没有修改产品代码或测试断言来取得本次结果；仅同步目标说明中过时的人工验收状态并补本节记录。

### 实际命令与隔离方式

实际从独立仓库执行的编排命令如下。编排脚本只在本地忽略目录，负责创建新临时 CWD、复制 README.md / pyproject.toml、设置环境并顺序运行下面列出的检查，不属于发布源码。

```powershell
& C:/Users/28436/.conda/envs/deskmate-win/python.exe -s -B -X utf8 .r1-verification/r6_release_run.py D:/ldj/03/DeskMate-Standalone win
wsl.exe -d Ubuntu-24.04 --cd /mnt/d/ldj/03/DeskMate-Standalone -- /home/ldj/anaconda3/envs/cc/bin/python -s -B -X utf8 .r1-verification/r6_release_run.py /mnt/d/ldj/03/DeskMate-Standalone wsl
```

Windows 实际 Python 为 3.12.7、SQLite 3.54.1；WSL 为 Python 3.11.16、SQLite 3.53.4；PySide6 均为 6.8.3。两平台设置 `QT_QPA_PLATFORM=offscreen`、`PYTHONDONTWRITEBYTECODE=1`、`PYTHONUTF8=1`，`PYTHONPATH` 为各自仓库及 tests 路径。Windows 临时 CWD 为 `.r1-verification/r6-release-win-cwd-1foy0vmu`，WSL 为 `/tmp/r6-release-wsl-cwd-1vnv4q9j`，没有使用此前用户的人工验收目录。

编排执行的完整回归及辅助命令如下（`<python>` / `<repo>` 对应上面的各平台绝对路径，`<cwd>` 为上述实际临时 CWD，`<platform>` 为 win 或 wsl；重新验收时为 cwd/basetemp 另选全新路径）：

```text
<python> -s -B -X utf8 -m pytest -q -ra -p no:cacheprovider -c <repo>/pyproject.toml --rootdir=<repo> <repo>/tests --basetemp=<cwd>/pytest --junitxml=<repo>/.r1-verification/r6-release-<platform>-full.xml
<python> -s -X utf8 <repo>/tests/verify_subagent.py
<python> -s -X utf8 -m likecc --help
<python> -s -X utf8 -m likecc.desktop --help
<python> -s -X utf8 -m examples.deskmate_memories --help
<python> -s -X utf8 -m examples.deskmate_memories --check --review-fixture --root <cwd>/visible-demo
<python> -s -B -X utf8 <repo>/.r1-verification/r6_compile.py <repo> release-<platform>
```

编译脚本遍历 likecc/tests/examples/scripts 的 201 个 Python 文件，执行 `ast.parse(source)` 和 `compile(source, filename, 'exec')`，不写 pyc，并对规范化换行后的源码计算 SHA-256。提交前再对照两平台编译清单与暂存 blob，保证提交的是已测试内容。

依赖与 Git 只读检查实际命令如下；uv 缓存限于独立仓库忽略目录，没有升级依赖或修改全局 Git 设置：

```powershell
$env:UV_CACHE_DIR='D:/ldj/03/DeskMate-Standalone/.r1-verification/uv-release-cache'
& C:/Users/28436/.local/bin/uv.exe lock --check --offline --default-index https://pypi.org/simple --python C:/Users/28436/.conda/envs/deskmate-win/python.exe
& C:/Users/28436/.local/bin/uv.exe pip check --python C:/Users/28436/.conda/envs/deskmate-win/python.exe --offline --no-config
git -c safe.directory=D:/ldj/03/DeskMate-Standalone diff --check
git -c safe.directory=D:/ldj/03/DeskMate-Standalone diff --exit-code HEAD -- pyproject.toml uv.lock
```

### 提交范围和证据边界

候选源码树共 230 个文件，路径扫描没有发现运行数据库、WAL/SHM、`.likecc/`、本地验收产物、环境或缓存。凭据启发式扫描的八处候选逐一核对为模板占位符、离线 demo/test 字符串或 URL 拒绝测试夹具，没有发现真实凭据；源码、数据库初始化、虚构夹具与使用文档全部保留。29 个 R6 文件按明确清单暂存，随后核对暂存名称、统计、空白检查及 Git 规范化后的 blob 与工作区一致性。

七项 Windows 可见桌面人工验收沿用本文件的原始人工记录，本次新证据是双平台离线套件、SubAgent、编译、帮助和样例准备。没有真实 Provider 调用；真实模型记忆质量和 R5 用户跳过的真实拒绝写入仍未验收。工作区切回的保守中断恢复、词法检索误召回/漏召回、来源审计尚无自动过期、跨平台同库并发不支持等限制不变。不开展 R7，也不操作原 DeskMate/LikeCC 仓库。
## R7 事件驱动的主动跟进与打扰控制（2026-11-23）

本节为 R7 新证据；上方保留历轮原始记录。独立目录 `D:\ldj\03\DeskMate-Standalone` / `/mnt/d/ldj/03/DeskMate-Standalone`，远端 `KNIGHT15235/DeskMate`，分支 `main`，开始 HEAD `9d1e7d426b625fd978fc2fe4ad20883fc60197a4`，工作区干净，无适用 AGENTS.md。Git 沙箱所有者检查以单次 `-c safe.directory=...` 解决，未改全局 Git 配置。原 DeskMate 目录未开发；本轮不提交、不推送、不调用计费 Provider、不做 R8 分发。

| 检查点 | 结果与证据 |
| --- | --- |
| R7-0 事件梳理 | [业务事件—触发位置—展示—操作表](deskmate-notifications.md#r7-0事件和通知入口) 已整理；原唯一 `_consume` 保持 |
| R7-0 缺陷复现 | 新测试在旧代码 **1 failed、1 passed**：最小化超时未收到气泡，隐藏通过；修复后两种情况均通过 |
| R7-A 持久化 | 共用 schedules.sqlite3；事务投影、升级静默旧完成、request 级去重、幂等修复、回滚、延后跨重启、证据文案，`test_notifications.py` **19 passed** |
| R7-B 操作与打扰 | 通知中心/原卡片/具体执行、真实 Future 核验、旧工作区与旧请求拒绝、三个取消语义、跨午夜和批量提示；存储/控制器/生命周期合并专项 **31 passed / 53.31s**，`r7-boundaries-win.xml` |
| R7-C 正常桌面入口 | `DesktopApplication` + 实际 Qt 控件 + 可控时钟 + fake client + FakeTray；**8 passed / 23.99s**，`r7-journey-win.xml`；含无托盘、允许两次写入/拒绝、失败/部分写入未知、历史恢复和重启不重放 |

首次定稿完整回归（人工复验前的同一源码快照，R6 基线 928 项，当时新增 32 项，总计 960 项；后续导航修复的增量证据见下方人工验收记录）：

| 检查 | 实际结果 | 证据（仓库忽略目录 `.r1-verification`） |
| --- | --- | --- |
| WSL Ubuntu-24.04 / cc 完整离线回归 | **960 passed、0 skipped，252.65s，退出 0** | `r7-wsl-full.xml/log` |
| Windows / deskmate-win 完整离线回归 | **954 passed、6 skipped，347.62s，退出 0** | `r7-win-full.xml/log` |
| 独立 SubAgent | 两平台各 **90/90，退出 0** | `r7-{win,wsl}-subagent.log` |
| 入口帮助 | 两平台 CLI、桌面、R7 演示 `--help` 均退出 0 | `r7-{win,wsl}-{cli-help,desktop-help,notification-help}.log` |
| 离线演示准备与推进 | 两平台 `--check`、`--advance-minutes 10` 均退出 0 | `r7-{win,wsl}-{notification-prepare,notification-clock}.log` |
| AST / 内存编译 | 两平台各 **207 个 Python 文件**；摘要彼此一致且匹配当前源码 | `r7-{win,wsl}-manifest.json` |
| 差异检查 | `git diff --check` 通过；main / HEAD 保持基线，无暂存、提交或推送 | 工作区与最终检查输出 |

Windows 六项跳过仍为五项 POSIX 进程组契约和一项无合适系统文件的符号链接用例，没有新增跳过；对应 WSL 用例全部运行。SubAgent 的 `failed: boom` 日志是既有异常注入，按 90/90 汇总和退出码判断。Windows 使用 Python 3.12.7 / SQLite 3.54.1；WSL 为 Python 3.11.16 / SQLite 3.53.4；PySide6 均 6.8.3。

两平台均设 `QT_QPA_PLATFORM=offscreen`、`PYTHONDONTWRITEBYTECODE=1`、`PYTHONUTF8=1`，PYTHONPATH 明确指向本独立仓库及 tests。隔离 CWD 分别为 `.r1-verification/r7-win-cwd-4pvuf4y9` 和 `/tmp/r7-wsl-cwd-mnytd0n2`，复制公开 README/pyproject 供旧 CWD 相关测试使用，pytest basetemp 各自独立，不共写任务库。WSL 沙箱初次 E_ACCESSDENIED 后经获准本机通道执行，未修改产品代码规避权限。

完整检查启动命令（脚本保留在本地验证目录，输出 JSON 汇总及上述日志）：

```powershell
Set-Location D:\ldj\03\DeskMate-Standalone
& C:\Users\28436\.conda\envs\deskmate-win\python.exe -s -B -X utf8 .r1-verification/r7_run.py D:/ldj/03/DeskMate-Standalone win
wsl.exe -d Ubuntu-24.04 --cd /mnt/d/ldj/03/DeskMate-Standalone -- /home/ldj/anaconda3/envs/cc/bin/python -s -B -X utf8 .r1-verification/r7_run.py /mnt/d/ldj/03/DeskMate-Standalone wsl
```

脱离该本地脚本也可复现：在独立临时 CWD 设置上述环境、复制 README/pyproject 后，用各平台解释器执行 `-m pytest -q -ra -p no:cacheprovider -c <repo>/pyproject.toml --rootdir=<repo> <repo>/tests --basetemp=<新临时目录>/pytest --junitxml=<报告路径>`，再执行 `<repo>/tests/verify_subagent.py` 和各入口帮助。

端到端第一轮暴露展示快照分步发布的竞态，已把相关执行、通知版本、领取结果和导航字段合并发布。Windows Qt 的 QTest 等待可能占用 Python GIL，R7 验收探针显式让出 1ms 并使用与既有 R6 完整流程一致的 20s 上限，保留全部业务断言；连续权限及未知写入完成后，8 条完整流程通过。旧生命周期测试也改为等待后台领取回执后检查模拟托盘，因为气泡去重现在由后台持久存储负责。

本轮离线演示为 `python -m examples.deskmate_notifications`；只替换模型/配置、演示时钟和明确标注的故障注入，实际文件、权限、会话和任务库保持。样例定义预先安排在未来，不伪造已完成历史。`model-inputs.jsonl` 与 `writes.jsonl` 可核对点击、恢复和重开前后的调用次数。完整 [Windows 一次走完清单及复制命令](deskmate-notifications.md#windows-一次走完的可见验收清单) 已提供。

人工观察边界：本轮 Qt 为 offscreen，FakeTray 证明的是 showMessage 调用和主线程路径，不证明 Windows 屏幕上确实出现系统气泡。气泡可见性/系统勿扰/点击/缩放、多显示器和真实无托盘环境仍待人工观察。没有真实 Provider 质量结论。程序完全退出不准点唤醒；气泡先持久领取再显示，崩溃窗口可能少一次系统提示，通知中心仍保留；权限延后不延长请求超时，未知写入不自动重放。首版仍为 Asia/Shanghai/UTC、本地单调度器，不支持 Windows/WSL 同库并发，通知历史尚无自动清理。
## R7 Windows 可见人工验收进展（2026-11-23）

用户已反馈第 1 条“启动与入口”通过。本次验收根目录为 `C:\Users\28436\AppData\Local\Temp\deskmate-r7-nuguu4kp`，工作区为其下 `A`。只读核查确认五项样例安排已保存，资料任务 Provider 为 `offline-r7 / fake`；核验时一次性提醒为 pending，“两次写入”为 awaiting_model，所有 run_id 均为空，模型输入日志及写入日志均为 0 次。沙箱不能读取新建临时目录，获准使用本机只读通道核查，未修改该工作区数据。

第 2 条将使用这条已有提醒验证延后、完全退出重开、到期再次提示及完成后停止提醒；尚未收到用户反馈，不能记为通过。其余资料任务在重开时如转为 interrupted，属于既有 R5 保守恢复规则，后续按原核对入口明确发起新尝试。

第 2 条重开检查中，用户提供截图并指出预期与界面不对应。2026-11-23 18:32（UTC+8）只读核验：一次性提醒仍是唯一通知 `55032ed8b7824302b8f50d53493a86f1`，对应原执行 `9ed3277d11444362b297626b3941d9c0`，state=snoozed、valid=1，延后截止 `2026-11-23T10:40:13.211169+00:00`（北京时间 18:40:13），generation=1、alerted_generation=0；原 due_at 未修改，重复 event_key 查询为空。列表九行实际为一条延后提醒、四条有效中断通知和四条已失效的模型确认历史，后者不会再提示。截图当前选中“R7 拒绝写入”，所以详情显示“稍后提醒时间：无”；不是所选提醒的详情。验收说明此前未充分说明历史行同时保留，已向用户澄清并要求仅选择一次性提醒查看其延后时间。演示时钟偏移仍为 0，模型输入及写入调用仍各 0 次；延后持久性有只读证据，界面时间确认、再次提示及完成后的停止提醒仍待后续人工反馈。

用户随后确认上述检查正确，并明确反馈延后到期后“看到了单条提醒气泡”。再次只读核验：演示时钟偏移为 10 分钟，同一提醒执行已为 done，原通知 state=viewed、valid=0、generation=1、alerted_generation=1，延后代次已经领取且事项已结束；模型输入及写入调用仍各 0 次。第 2 条提醒延后、退出重开、再次提示和完成收尾记为通过，Windows 单条系统气泡有本次人工反馈支持。

第 3 条开始前只读确认“R7 两次写入”安排仍启用，唯一旧执行 `0c501c1d92134b28a21703239ea3537f` 为 interrupted、尚未核对，无 session/run、evidence 为空；冻结范围为读取 project_notes.md、写入 outputs/first.md 与 outputs/second.md，两个输出均不存在。接下来由用户在原核对入口明确发起新尝试，再确认模型及两个独立写入权限；该条尚未验收通过。

用户反馈第 3 条通过。只读核验新执行 `e5de2fddf28d4916b7cb958d1769a5c1` 为 completed，retry_of 指向旧中断执行；原执行已核对。新运行 `8fdf4e0defa04075a79b570b174395a7` 下两个不同 request_id 分别对应 outputs/first.md 与 outputs/second.md，均为 allow，结束后 active=0。两个 artifact 均 verified，磁盘文本 SHA-256 均与持久摘要 `f02a6fa4686bfdfb14f71621cbcf2cc34e67b6a384b94142ba42db6a8b84df63` 一致；完成通知关联新执行、含两个正确成果且已查看。fake client 输入共 6 次、真实本地写入边界共 2 次，只有这两个输出，denied.md 尚不存在。对照保存在 `.r1-verification/r7-manual-step3.json`。

权限入口覆盖单列：两条权限通知 state 仍为 unread，第二条 alerted_generation=-1；用户补充确认“两次均直接在主窗口卡片允许”。因此第 3 条的两次独立授权、实际写入、回读及完成通知定位记为人工通过，不能把它扩展为两次都通过权限通知导航或两次系统气泡通过。第 4 条将明确从权限通知“继续处理”进入原卡片后拒绝写入，同时补验这条通知入口；尚未操作或判为通过。

用户反馈第 4 条通过。只读核验新执行 `edf320128dd141d9bc6825e605f4a390` 为 completed，关联旧中断记录 `caa481541a7f4894a60850c270fd9d3e`；WriteFile 请求 `6c3cca1d3aed4d26b887a23ad6ddb14a` 已记录 deny、active=0。成果、写入意图和摘要均为空，磁盘 outputs/denied.md 不存在。完成通知明确写“本次有写入被拒绝”“没有已写入的成果记录”，没有 verified 成功文案；证据还保留脚本随后读取不存在目标的工具错误。累计 fake client 输入为 10 次，写入边界仍仅第 3 条的 2 次；first.md/second.md 的内容摘要、大小和修改时间与第 3 条对照完全一致。拒绝决定、文案与磁盘结果已有人工反馈和只读证据。

第 4 条的权限通知仍为 unread、alerted_generation=-1，故单独向用户核对实际进入方式，暂不将通知导航判为人工通过。第 5 条起始状态已只读确认：R7 失败与 R7 未知写入的旧执行均为未核对的 interrupted，无 session/run 和执行证据，failed.md/unknown.md 均不存在；后续仍由用户明确发起样例新尝试。

用户对第 4 条权限入口的补记回答为“不确定”。因此保留拒绝决定、通知文案和磁盘结果通过，权限通知导航仍为未确认，不根据该回答推断界面缺陷或已通过。已给出第 5A 模型失败与重复查看步骤，尚待执行反馈；第 5B 将在权限等待处停下，逐步核对通知导航，再由用户明确允许离线故障样例写入，无需为补记重做第 4 条。

用户确认 5A“已看到失败通知”。只读核验新执行 `f556b81f18a84b389b6758fa2000a637` 为 failed，retry_of 为旧中断执行 `d7fcfd4619434f5491d29c400a73b08b`，会话 `session_20261123_185743_kadc`、运行 `a36069fcd21d443db5b61b4c7cd7049e`，原因为预设离线模型失败；成果、来源、写入意图均为空，failed.md 不存在。失败通知 `9f95f0df0f614f01adb99709d406e06d` 已查看并关联该次执行。重复查看前对照为 8 条执行、3 个权限请求、11 次 fake client 输入、2 次写入边界；first.md/second.md 的摘要与修改时间仍匹配第 3 条。对照保存为 `.r1-verification/r7-manual-step5a-before-review.json`，接下来只重复打开同一失败通知，核对不会自动重试；重复查看结论尚待反馈与后续对照。

用户反馈“重复查看正确”。5A 后续只读对照通过：执行数仍为 8、权限请求仍为 3、fake client 输入仍为 11、写入边界仍为 2；同一失败执行状态及 session/run 保持，reviewed_at 仍为空，failed.md 未生成，first.md/second.md 的字节摘要和修改时间均未改变。5A 的失败通知、具体执行定位、重复查看不自动重试记为人工与只读对照通过，证据为 `.r1-verification/r7-manual-step5a-after-review.json`。

5B 开始前再次只读确认未知写入安排仍只有原中断执行 `794836e9830f426eaa36caccb647326d`，无 session/run、无证据、未核对，unknown.md 不存在。下一步仅由用户核对旧记录、发起新尝试并允许离线模型，在 unknown.md 的权限通知出现时停下；通知导航及实际部分写入结果尚未验证。

用户确认已看到 unknown.md 权限通知，并明确点击了通知中心中的该行。20:30（北京时间）只读核验：新执行 `78fcddd61301473b965df59f0e14dc5a` 为 waiting，运行 `a7340e383400420c8c7a9a1c3ab2c7c0`，请求 `ece4c53528784fbbb8b3e56c2cfc2eee` 仍 active=1、resolution 为空；对应权限通知 `c6e590b13e3144519a3d29025ad0338e` 已为 viewed、valid=1。unknown.md 仍不存在，累计 fake client 输入为 13、写入边界仍为 2；用户点击通知没有批准或写入。该对照保存为 `.r1-verification/r7-manual-step5b-before-allow.json`。下一步由用户在原权限卡片明确允许一次，才触发预设的部分写入故障；该故障结果仍待反馈。

5B 用户随后报告没有回到权限卡片，并补充点击后看到的是“任务与执行记录”。该导航不能记为通过。只读核查确认通知已被接收、当时请求仍有效；新增真实 Qt 复现中，后台导航目标为 request，但原任务 QDialog 留在主窗口上方，仅隐藏通知中心、raise 主窗口不足以露出卡片。旧测试在允许模型后主动隐藏任务窗口，漏掉了这条路径。补充回归保留任务和记忆窗口，旧实现得到 **1 failed**（`r7-nav-red.xml`，明确断在任务窗口仍可见），随后在 `ChatWindow.navigate_notification` 修复：仅在匹配的有效请求分支隐藏附属窗口，保留草稿，恢复主窗口、滚回卡片顶部并聚焦。历史和超时仍沿原执行记录处理。

排查期间该请求于真实时间 20:33:15 达到五分钟等待上限，resolution=ended，而非用户 allow/deny；本次执行成为 completed，理由为无成果且有工具拒绝/失败。模拟时钟偏移为十分钟，因此执行记录 started_at/ended_at 对应 20:38:15/20:43:15，不能将它们误认为权限等待的实际墙钟。unknown.md 仍不存在、写入边界仍为 2；fake client 输入从 13 到 15，是超时后原离线脚本继续读取失败并结束，没有创建新一次执行。未触发未知写入故障，不能据此通过 5B。20:46 再次只读对照及完整记录保存为 `.r1-verification/r7-manual-step5b-navigation-timeout.json`。排查没有操作用户的权限按钮、重试或更改演示数据库；computer-use 只读访问窗口树，截图捕获超时后改用可访问性树。

修复后的 Windows `test_r7_acceptance.py` 为 **16 passed / 45.07s**（`r7-nav-journey.xml`）：原 8 项及新增 8 项，新增为行点击/按钮 × 可见/最小化/隐藏/无托盘，并检查重复导航不增加调用/写入、卡片与按钮可见、聚焦、未保存草稿保留。第一次修复后试跑有 5 项焦点断言过早，补为等待 Qt 异步激活后完整 16 项通过，没有移除焦点断言。相关窗口、生命周期、通知与等待态回归另 **30 passed / 81.11s**（`r7-nav-win.xml`），使用独立临时 CWD。上方 960 项全量结果属于人工复验前快照，本次补丁的证据单列。修复尚需用户完全退出并以原验收根目录重开，再明确发起新尝试观察 Windows 可见导航；旧权限不会复活。

WSL cc 在独立临时 CWD 合并运行同一组 46 项，首次 **45 passed、1 failed / 134.15s**（`r7-nav-wsl.xml`）；包括新增 8 项在内的全部 16 项 R7 流程通过。唯一失败为旧窗口测试 `test_gui_permission_question_hidden_resume_and_no_duplicate_execution[False]`，断在初始发送按钮就绪前的 6 秒启动等待，尚未进入任何通知导航。随后在新的隔离目录单独复跑整个 `test_desktop_window.py`，**9 passed / 51.28s**（`r7-nav-wsl-startup-recheck.xml`），未修改该旧测试或其超时。保留首次失败和复跑两份证据，不将首次结果改写为全绿。双平台新增导航组合均已验证，`git diff --check` 通过；真实 Windows 修复后可见效果仍待用户反馈。

用户确认已以原根目录重开。21:26（北京时间）只读核验：未知写入仍只有原中断执行和上次超时结束的执行 `78fcddd61301473b965df59f0e14dc5a`，没有自动生成新尝试；旧请求 active=0，其权限通知为历史。unknown.md 不存在，fake client 输入仍为 15、写入边界仍为 2。重开没有恢复旧授权或增加调用。下一步由用户核对这条已结束记录并明确创建新一次执行，先停在等待模型确认，避免在等待对话反馈时再次消耗权限的五分钟有效期；修复后的实际导航仍待该新请求复验。

用户确认已看到新一次模型确认。只读核验新执行 `f5ab7bdb5f214cfc807f23c22ca90f1f` 为 awaiting_model，retry_of 指向上次超时结束记录，session/run 尚为空；原记录已核对。unknown.md 仍不存在，fake client 输入仍为 15、写入边界仍为 2。下一轮人工操作保留任务窗口打开，从托盘通知中心点击该新执行的权限通知，先观察是否露出原卡片，再由用户明确允许一次并观察离线部分写入故障；尚未将导航修复或未知写入验收记为通过。

用户反馈“已回到卡片并允许，已看到中断待核对”，本次修复后的权限通知导航有可见人工反馈支持。只读核验执行 `f5ab7bdb5f214cfc807f23c22ca90f1f` 为 interrupted，会话 `session_20261123_213152_w9mh`、运行 `bff08a9c2bbc4264b7531b9f1c06bc00`；独立请求 `5338ad6269e84de192e4f01eafb0bdcf` resolution=allow、active=0，权限通知已查看。中断通知 `23afd6033af94143906fa854451c9b46` 已查看并关联同一次执行，明确写入结果未知、回读未通过，没有 verified 成功文案。磁盘 unknown.md 为 32 字节，内容为“R7 故障注入：部分写入\n”，artifact=readback_failed、write_intent=write_unverified，与注入结果相符；reviewed_at 仍为空。first.md/second.md 的摘要和修改时间不变，denied.md/failed.md 仍不存在。重复查看前对照为 10 条执行、5 个权限请求、19 次 fake client 输入、3 次写入边界，完整摘要和日志哈希保存在 `.r1-verification/r7-manual-step5b-before-review.json`。通知导航和故障结果已核实，接下来只重复查看这次中断记录，尚未提前通过未知写入的重复查看检查。

用户反馈“未知写入重复查看正确”。后续只读对照中，execution 全字段、五个输出文件的存在性/内容摘要/修改时间、两份调用日志的行数和整体哈希、执行数和请求数均与重复查看前一致：仍为 10 条执行、5 个权限请求、19 次 fake client 输入、3 次写入边界；未知写入仍为 interrupted，reviewed_at 为空。完整对照保存为 `.r1-verification/r7-manual-step5b-after-review.json`。第 5 条的失败与未知写入通知、具体执行定位和重复查看不重试记为通过，修复后的权限通知导航也有本次人工反馈。历史会话恢复与最终重开对照留在最后一条验收。第 6 条尚未开始；只读确认工作区仍未保存免打扰配置，演示时钟偏移保持 10 分钟，接下来先由用户保存 Asia/Shanghai 的 22:00–08:00 跨午夜时段，再逐步检查静音入库、积压提示和取消语义。

用户反馈“免打扰已保存”。只读确认 notification_meta.quiet 为 enabled=true、22:00–08:00、Asia/Shanghai；演示时钟偏移保持 10 分钟，核验时演示本地时间为 2026-11-24 00:07:58，处于跨午夜静音区间。模型输入仍 19 次、写入仍 3 次，现有四条有效结果通知均已领取过本代提示，没有新事项可用于静音验证，因此尚不把“没有气泡”记为通过。接下来由用户通过原任务窗口创建两条一次性提醒 R7 静音提醒 A/B，在最小化后推进演示时钟并观察静音期间入库；原五项安排和未知写入核对状态保持。

用户反馈两条静音提醒均出现、期间没有看到系统气泡。只读核验 A/B 分别只有一条 pending 执行 `4abba6ce0bfe49c19d053b708cf7ef4f` / `e7441e3b8f7f4701add27a0c0ebec1f7`；对应通知 `92d85047fe864a07acc0cf7c48592e04` / `8346f0ce9320441781b20fa5cd886152` 均 unread、valid=1、generation=0、alerted_generation=-1，尚未领取气泡。两条首次本地时间都是 2026-11-24 01:00（Asia/Shanghai），到期后仍入中心且不改变待处理状态。此次实际持久演示时钟偏移为 60 分钟，核验时演示时间为 01:11:21，跨午夜免打扰仍启用；模型输入仍 19、写入仍 3。第 6 条中的静音入库小步通过，对照为 `.r1-verification/r7-manual-step6a-quiet.json`。下一步按当前读数再推进 410 分钟越过 08:00，保持免打扰配置，观察两条积压是否只生成一条汇总提示；此项尚未提前判定。

用户反馈“一条汇总气泡”。只读核验演示偏移为 470 分钟，本地演示时间 2026-11-24 08:05:13；免打扰配置仍启用且保持 22:00–08:00，已自然越过结束边界。A/B 两条通知仍各一条、unread、valid=1、generation=0，alerted_generation 均由 -1 变为 0；last_alert 为演示本地时间 08:04:03。两条任务及执行全部字段与静音时对照相同，仍 pending；模型输入仍 19、写入仍 3。结合人工只见一条气泡，静音结束后的积压合并提示记为通过，证据为 `.r1-verification/r7-manual-step6b-summary-alert.json`。第 6 条的三个取消语义尚待操作，接下来先对 A 使用“关闭本条提醒”，检查通知关闭而任务仍待处理，B 保持原状。

用户反馈“关闭提醒后，A 仍待处理”。只读核验 A 通知 state=handled、valid=1，其任务仍 enabled=1、原执行仍 pending；B 通知仍 unread，任务与执行状态保持。两份调用日志的行数和哈希不变，仍为 19 次 fake client 输入、3 次写入，三个已有文件摘要及修改时间不变。“关闭本条提醒”仅关闭该通知、不完成或取消任务的小步通过，证据为 `.r1-verification/r7-manual-step6c-dismiss.json`。同时建立取消单次执行前对照：R7 两次写入仍 enabled=1、revision=1、next_due=2026-11-30T10:27:03.323653+00:00；旧已完成执行 `e5de2fddf28d4916b7cb958d1769a5c1` 尚未核对。接下来由用户明确创建新尝试，停在模型确认前，再从该次通知选择“取消本次执行（保留未来周期）”；不会要求允许模型或重写已有成果，该项尚未通过。

用户反馈“本次已取消，安排仍保留”。只读核验新执行 `29a6003455684006993d423ac11f6e0a` 为 cancelled，原因为“用户取消本次执行；未来周期保持”，session/run 为空；retry_of 指向原已完成执行，原执行仅按明确重试流程补记 reviewed_at。R7 两次写入任务全部字段与操作前对照一致，仍 enabled=1、revision=1，下次周期仍为 2026-11-30T10:27:03.323653+00:00。两份日志哈希及三个文件摘要/修改时间也相同，仍为 19 次 fake client 输入、3 次写入，取消前没有调用模型。“取消本次执行”保留未来周期的小步通过，对照为 `.r1-verification/r7-manual-step6d-cancel-once.json`。接下来对另一个仍启用的 R7 拒绝写入安排创建待确认的新执行，再从其通知选择“停止整个安排 / 周期”，检查该安排停用、当前执行取消且历史保留；停止整个周期尚未操作或判为通过。

用户反馈“整个安排已停止，本次也已取消”。只读核验 R7 拒绝写入安排 enabled=0、revision=2、next_due=NULL；新执行 `3db25aaf57654a5d84e35d36739275ad` 为 cancelled，原因“用户取消安排”，session/run 为空；原 completed 拒绝执行和更早的 interrupted 历史保留。R7 两次写入任务与前一对照完全一致，仍保持启用及原未来周期；日志哈希、三个文件摘要和修改时间均未变化，仍为 19 次 fake client 输入、3 次写入。第 6 条的跨午夜静音、结束后合并提示以及三个不同取消语义均有本次人工反馈和只读证据，记为通过。完整对照为 `.r1-verification/r7-manual-step6e-stop-period.json`；A 当前有 7 项安排、14 条执行、30 条通知、5 个已结束权限请求，没有活动执行；B 尚未建立任务库，作为下一步隔离检查的起点。第 7 条将合并工作区切换、历史恢复和最终重开验收，尚未判为通过。

用户反馈“B 为空，切回 A 记录正确”。只读核验 B 已建立独立任务库，任务、执行、通知和请求均为 0，尚无免打扰配置，使用默认关闭；A 仍保持启用的 22:00–08:00 Asia/Shanghai 设置。A 的任务、执行全部字段与切换前一致，计数仍为 7/14/30/5；日志行数和哈希、三个文件摘要及修改时间不变，仍为 19 次 fake client 输入、3 次写入。工作区显示隔离与设置保留小步通过，对照为 `.r1-verification/r7-manual-step7a-workspaces.json`。旧 A 命令在 B 的拒绝边界由已有自动化覆盖，本步没有声称人工强制触发过时点击。接下来恢复两次写入、拒绝、失败和未知写入的四个原会话，只查看历史，不发送新任务；历史恢复与最终退出重开仍待反馈。

用户反馈“四个历史会话均可查看，没有新权限卡片”。只读核验 A 的 tasks、executions、notifications、notification_requests 全部与工作区切换后对照一致，日志行数及整体哈希、三个文件摘要及修改时间也未变；仍为 19 次 fake client 输入、3 次写入，denied.md/failed.md 仍不存在。历史恢复不重放的小步通过，证据为 `.r1-verification/r7-manual-step7b-history.json`。当前没有活动执行，剩余启用周期为 R7 两次写入、R7 失败、R7 未知写入，均到下周才再到期；两条静音提醒仍 pending。最后由用户停止这三个剩余周期，保留提醒和历史，再完全退出并用原根目录重开，核对旧权限不复活和调用/文件不变；最终重开尚待反馈。

用户反馈“重开后历史正确，没有新权限卡片”。最终只读对照确认 executions、notifications、notification_requests 全部与重开前一致；唯一任务变更为用户明确停止的 R7 两次写入、R7 失败、R7 未知写入，均变为 enabled=0、revision=2、next_due=NULL。连同此前停止的拒绝写入，四个周期都已停用。A 仍为 7 项安排、14 条执行、30 条通知、5 个已结束请求；B 对应各项均为 0。静音提醒 A 仍为通知 handled/业务 pending，B 仍为通知 unread/业务 pending；免打扰设置保留。日志仍为 19 次 fake client 输入、3 次写入，整体哈希、三个已有文件摘要和修改时间完全一致，denied.md/failed.md 仍不存在。第 7 条通过，最终对照为 `.r1-verification/r7-manual-step7c-final-reopen.json`。

## R7 人工验收收尾与最终回归（2026-11-24）

七条 Windows 可见人工主流程已完成，验收根目录保留为 `C:\Users\28436\AppData\Local\Temp\deskmate-r7-nuguu4kp`。本节汇总最终结论；上方逐步记录和初次失败/修复过程作为原始证据保留。

| 人工检查点 | 结果 | 实际覆盖与边界 |
| --- | --- | --- |
| 1 启动与入口 | 通过 | 独立 A/B 工作区、offline-r7 / fake、五个原始安排与通知中心 |
| 2 一次性提醒 | 通过 | 延后持久化、完全退出重开、同一代仅一条系统提醒、完成后停止提示；单条系统气泡有人工反馈 |
| 3 周期任务两次写入 | 通过 | 同一执行两次独立允许，两份文件 verified，完成通知定位到正确成果；两次允许均从主窗口卡片进入 |
| 4 拒绝写入 | 通过 | deny 已落库，denied.md 不存在，无成果/拒绝文案一致；当时进入权限卡片的路径不确定，通知导航由第 5 条补验 |
| 5 失败、未知写入与重复查看 | 通过 | 修复附属任务窗口遮挡权限卡片后人工复验；真实部分写入对应 interrupted/readback_failed/write_unverified；重复查看不重试 |
| 6 免打扰与三个取消含义 | 通过 | 跨午夜时段通知入库无气泡，08:00 后一条汇总气泡；关闭通知保留待处理、取消一次保留周期、停止整个安排取消当前并停用未来 |
| 7 工作区、历史与最终重开 | 通过 | B 无 A 事项，切回 A 配置/历史保持；四个历史会话恢复及最后重开无新增模型调用、写入或权限卡片 |

最终仍为 **19 次离线 fake client 输入、3 次写入边界调用**。19 次包含成功、拒绝、模型失败、一次权限超时后的脚本收尾及明确重试的未知写入，不是 19 次计费 Provider 调用；3 次写入是 first.md、second.md 和明确允许后故障注入的 unknown.md。unknown.md 保留部分内容及待核对历史，没有将其标为已验证成功。两个测试提醒刻意保留待处理，用于核对“关闭通知不完成任务”；四个周期已停止。

自动化与人工边界：无托盘完整路径、过时工作区命令拒绝、最小化/隐藏与两种点击入口的组合由自动化覆盖；本机真实无托盘、每次权限均出现系统气泡、原生气泡点击回调、多屏与不同缩放组合没有逐项人工验证。操作系统可能屏蔽气泡，领取后崩溃也可能丢失显示，但通知中心持久保留；完全退出期间不唤醒，权限延后不延长授权，未知写入不会自动重试。真实 Provider 质量、本地历史长期规模和 R8 分发不在本轮结论内。

关键实现文件：`likecc/notifications.py` 和 `likecc/scheduling.py` 负责同库事务投影与通知状态；`likecc/desktop/controller.py` 和 `likecc/interaction.py` 负责工作区/执行/请求与真实 Future 核验；`likecc/desktop/notifications.py`、`window.py`、`application.py`、`schedules.py` 负责通知中心、导航、托盘及明确操作入口。`examples/deskmate_notifications.py` 提供隔离的可控时钟/fake client/故障演示；三个通知测试文件及生命周期测试覆盖存储、边界和正常桌面流程。使用与复验清单见 [通知说明](deskmate-notifications.md)，三项设计问题和人工缺陷经验见 [学习记录](deskmate-learning.md)。

最终同一源码回归已完成，包含人工验收发现的导航修复及新增 8 个组合：R6 基线 928 项，R7 共新增 40 项，总计 968 项。本次两个最终整套均一次执行完成、无失败；此前专项中旧窗口启动等待超时的原始失败与单独复跑证据仍保留，该用例在本次整套中通过。

| 最终检查 | 实际结果 | 本地证据（`.r1-verification`，未提交） |
| --- | --- | --- |
| WSL Ubuntu-24.04 / cc 完整离线回归 | **968 passed、0 skipped，270.85s，退出 0** | `r7-wsl-final-full.xml/log` |
| Windows / deskmate-win 完整离线回归 | **962 passed、6 skipped，439.69s，退出 0** | `r7-win-final-full.xml/log` |
| R7 正常桌面入口流程（包含在完整回归内） | 两平台各 **16/16**，包括新增 8 种通知导航组合 | 两份 final-full.xml 中 `test_r7_acceptance` |
| 独立 SubAgent | 两平台各 **90/90，退出 0** | `r7-{win,wsl}-final-subagent.log` |
| CLI、桌面、R7 演示入口帮助 | 两平台三种 `--help` 均退出 0 | `r7-{win,wsl}-final-{cli-help,desktop-help,notification-help}.log` |
| 离线演示准备与时钟推进 | 两平台 `--check`、`--advance-minutes 10` 均退出 0 | `r7-{win,wsl}-final-{notification-prepare,notification-clock}.log` |
| AST / 内存编译与源码一致性 | 两平台各 **207 个 Python 文件**；两份 manifest 相同且与当前源码相符 | `r7-{win,wsl}-final-manifest.json` |
| Git 范围与空白检查 | `git diff --check` 通过；main / HEAD 仍为 R6 基线，无暂存、提交或推送 | 最终命令输出 |

耗时采用 pytest 终端汇总。Windows 的六项跳过仍为五项既有 POSIX 进程组用例和一项无合适系统文件的符号链接用例，对应 WSL 用例全部运行，没有新增跳过。两平台环境版本与前述首次定稿相同。最终隔离 CWD 为 Windows `.r1-verification/r7-win-final-cwd-8ektrtuw`、WSL `/tmp/r7-wsl-final-cwd-nklentyd`；不共写数据库，也不使用人工验收根目录。两个 final-summary.json 中全部七个命令退出码为 0。

最终检查的可复制命令：

```powershell
Set-Location D:\ldj\03\DeskMate-Standalone
& C:\Users\28436\.conda\envs\deskmate-win\python.exe -s -B -X utf8 .r1-verification/r7_run.py D:/ldj/03/DeskMate-Standalone win-final
wsl.exe -d Ubuntu-24.04 --cd /mnt/d/ldj/03/DeskMate-Standalone -- /home/ldj/anaconda3/envs/cc/bin/python -s -B -X utf8 .r1-verification/r7_run.py /mnt/d/ldj/03/DeskMate-Standalone wsl-final
```

本地检查脚本位于忽略目录；不依赖该脚本的原生命令方式见上方 R7 首次定稿部分。离线可见演示启动与重开命令、可一次走完的七条清单见 [通知使用说明](deskmate-notifications.md)。所有改动保留在独立仓库工作区供复审；没有计费 Provider 调用，未开发原 DeskMate 仓库，也未开展 R8 分发。

## R7 提交前复审（2026-11-24）

按用户要求，仅在独立仓库复审已有 R7 工作区改动并直接修复。开始及收尾检查均保留 `main` / R6 基线 `9d1e7d426b625fd978fc2fe4ad20883fc60197a4`；未暂存、提交、推送、调用计费 Provider 或开展 R8。三名审查代理分别复核去重、请求/工作区、取消语义，主代理整合并检查异常路径。本轮不访问或变更上述人工验收根目录，所有探针、数据库及完整回归使用独立临时目录。

上节七条人工验收及 968 项自动化是复审前版本的原始证据，仍保留；本节修复由新增离线自动化验证，不冒充再次进行了 Windows 可见人工验收。

| 缺陷及影响 | 修复与回归 |
| --- | --- |
| P1：权限先放行后保存；数据库失败可导致界面报拒绝但真实写入继续，决定证据缺失 | 先检查格式/身份/Future，再同步保存决定并放行；数据库失败保持原 Future 待处理，用户明确重试后仅执行一次。允许、拒绝、补充回答三组覆盖真实工具/磁盘。纯展示刷新失败保留成功回执 |
| P2：Future 已结束而结果事件尚未消费，仍领取过期气泡；迟到首次事件可覆盖当前卡片 | 扫描/领取前检查真实 Future，首次事件已结束则丢弃；覆盖回答/取消 × 权限/问答、迟到两种事件，也验证不误删另一条仍有效的请求 |
| P2：切换工作区已开始而旧库尚未释放时接受旧通知命令 | 同时检查展示工作区、存储工作区和就绪状态；打开、延后、关闭、取消本次、停止周期、保存免打扰六种命令均拒绝，旧/新工作区事实不变 |
| P2：待处理提醒漏取消按钮；关闭通知错误地禁用仍有效事项的业务取消 | UI/后端以业务有效性决定取消；handled 只禁止再次延后。提醒/模型任务 × 是否先关闭四组正常 Qt 流程，旧周期原参数与刷新后的历史参数都不能取消下一期 |
| P2：一次气泡领取失败或初始状态拒绝后，Qt 等待令牌不释放，后续可能一直无提示 | 统一失败回执覆盖事务和初始拒绝，Qt 清除令牌并至少退避一秒；未就绪时不申请领取。真实 SQLite COMMIT 失败回滚代次/冷却，重试及重开不重复 |
| P2：运行收尾的请求结束落库异常逃逸，界面卡在“取消中” | 纳入原收尾错误边界，清空过期卡片及运行引用并停止后续领取；明确重开后原执行为中断待核对，恢复历史不增加调用/写入 |

去重存储原有 UNIQUE 事件键和事务投影未发现重复缺陷。额外测试真实 SQLite 读锁引起 COMMIT 失败、恢复后重放相同 PermissionRequest 五次；均无新增通知、无授权复活。没有增加调度器、事件消费者或后台自动工具重放。

针对性红/绿证据（均在忽略目录 `.r1-verification`）：

| 检查 | 实际结果与证据 |
| --- | --- |
| 去重、回滚与恢复事件重放 | **21 passed，13.46s**；`r7-review-dedupe-regressions.xml`；另有独立事务探针 `r7-review-dedupe-probe.json` |
| 请求有效性与切换过渡期 | 修复前 **10 failed / 1 passed**，补迟到事件后 **13 passed，15.53s**；`r7-request-review-{red,green}.xml` |
| 权限保存与刷新故障 | 修复前 **4 failed / 1 passed**；加入上述请求用例后的模块 **18 passed，21.93s**；`r7-reply-review-red.xml`、`r7-request-review-final.xml` |
| 运行收尾故障 | 新回归修复前 **1 failed**；修复后连同原终态保存故障用例 **2 passed，14.95s**；`r7-terminal-review-{red,green}.xml` |
| 正常桌面取消与旧周期重放 | 四组取消用例修复前 **3 failed / 1 passed**；完整入口验收模块最终 **19 passed，39.24s**；`r7-review-cancel-all-red.xml`、`r7-review-cancel-stale-final.xml` |
| 气泡事务失败与守卫拒绝 | 临时领取故障修复前 **1 failed**；初始拒绝修复前 **2 failed**（本轮命令输出，无单独 JUnit）；最终通知模块及领取重试共 **6 passed，13.99s**；`r7-review-alert-red.xml`、`r7-alert-guard-green.xml` |
| 桌面交互/生命周期交叉检查 | **22 passed，44.82s**；`r7-review-desktop.xml`，后续完整回归再覆盖最终源码 |

已有原始失败报告保留。取消用例追加下一期重放时，曾误用扫描前的 next_due 作为比较基准；修正为下一期生成后的快照后通过，未因此改动生产代码。没有跳过或删除失败用例来取得通过。

修复后同一源码的双平台完整检查均一次完成。本轮相对上节新增 **27 项**回归，总计 **995 项**；`test_r7_request_review.py` 为 19 项，正常 Qt 入口 `test_r7_acceptance.py` 为 19 项。

| 最终检查 | 实际结果 | 本地证据（`.r1-verification`，未提交） |
| --- | --- | --- |
| WSL Ubuntu-24.04 / cc 完整离线回归 | **995 passed、0 skipped，235.07s，退出 0** | `r7-wsl-review-full.xml/log` |
| Windows / deskmate-win 完整离线回归 | **989 passed、6 skipped，383.96s，退出 0** | `r7-win-review-full.xml/log` |
| 独立 SubAgent | 两平台各 **90/90，退出 0** | `r7-{win,wsl}-review-subagent.log` |
| CLI、桌面、R7 演示入口帮助 | 两平台三种 `--help` 均退出 0 | `r7-{win,wsl}-review-{cli-help,desktop-help,notification-help}.log` |
| 离线演示准备与时钟推进 | 两平台 `--check`、`--advance-minutes 10` 均退出 0 | `r7-{win,wsl}-review-{notification-prepare,notification-clock}.log` |
| AST / 内存编译及源码一致性 | 两平台各 **208 个 Python 文件**；manifest 完全一致且匹配当前源码 | `r7-{win,wsl}-review-manifest.json` |
| 工作区检查 | `git diff --check` 通过；main / R6 HEAD 不变，暂存区为空 | 最终检查输出与 `r7-review-audit.json` |

耗时采用 pytest 终端汇总。Windows 六项跳过仍为五项既有 POSIX 进程组用例和一项无合适系统文件的符号链接用例，WSL 全部运行，没有新增跳过。Windows 为 Python 3.12.7 / SQLite 3.54.1，WSL 为 Python 3.11.16 / SQLite 3.53.4；两边 PySide6 均为 6.8.3。

隔离 CWD：Windows `.r1-verification/r7-win-review-cwd-uohmwky4`；WSL `/tmp/r7-wsl-review-cwd-d5n5gf04`。两个 review-summary.json 内的七个命令退出码均为 0。规范化 manifest 的 SHA-256 为 `5b449f5e59ab55a4ff59919e7b22daa577df63ad765bb1d57e55e12b9ea777d6`。

复跑本轮检查可使用上节同一脚本，将末尾后缀分别改为 `win-review` 和 `wsl-review`。不依赖忽略目录脚本的完整命令、可见离线演示与七条人工清单仍见前文及[通知说明](deskmate-notifications.md)。本次没有新增 Windows 原生气泡可见性结论，原生托盘/多屏限制保持；每代最多领取一次不等于操作系统保证显示一次。工作区已包含修复、回归及通知说明/路线/学习记录更新，未提交推送或开展 R8。

## R7 授权发布前检查（2026-11-24，因回归失败暂停）

用户随后明确授权正常提交、推送至 `KNIGHT15235/DeskMate` 的 `main` 及导出固定 SHA ZIP；同时要求“如果必要回归失败，停止提交并报告”。本节为该次新执行的结果，不沿用上一节通过数字。本次 Windows 完整回归有一项失败，因此没有暂存、创建 Commit、推送或导出 R7 ZIP，尚无 R7 SHA；没有用复跑覆盖失败、修改断言或扩大跳过范围。

Git 初始检查：实际目录 `D:\ldj\03\DeskMate-Standalone`；分支 `main`，HEAD 为 `9d1e7d426b625fd978fc2fe4ad20883fc60197a4`；R6 基线在历史中，origin 为 `https://github.com/KNIGHT15235/DeskMate.git`。暂存区为空，无 merge/rebase/cherry-pick/revert/sequencer 或 index.lock。首次 `git fetch origin` 成功，`origin/main...HEAD` 左右计数 **0/0**；无异常历史。未修改其他仓库或使用强制推送/历史重写。

停止提交后再次执行 `git ls-remote origin refs/heads/main`，远程 SHA 仍为上述 R6 基线，与本地 HEAD 一致；工作区保留 23 个 R7 候选文件，暂存区为空。该一致性表示尚未发布新版本，不代表 R7 已推送。

只读审查确认 8 个生产文件、5 个测试文件和 1 个离线演示属于 R7，R1–R6 契约未发现新的破坏。候选文件与已跟踪路径没有真实配置、数据库、日志、截图或 `.r1-verification` 产物；候选正文未发现真实凭据，api_key 字面量为离线占位值；18 项代表性配置/缓存/SQLite 附属文件路径均被忽略。文档中的 fake 人工验收元数据按说明保留，不访问该人工根目录。

本次只补充文档：README 增加已实现 R7 的简介、通知入口与离线演示命令；同步目标规格、路线和通知说明的过时状态。源码和测试未变，候选总计 **23 个文件（15 修改、8 新增）**；清单保存在忽略目录 `r7-publish-files.json`。Python 源码清单与上一节复审版本一致。

本次实际执行的主命令：

```powershell
Set-Location D:\ldj\03\DeskMate-Standalone
& C:\Users\28436\.conda\envs\deskmate-win\python.exe -s -B -X utf8 .r1-verification/r7_run.py D:/ldj/03/DeskMate-Standalone win-publish
wsl.exe -d Ubuntu-24.04 --cd /mnt/d/ldj/03/DeskMate-Standalone -- /home/ldj/anaconda3/envs/cc/bin/python -s -B -X utf8 .r1-verification/r7_run.py /mnt/d/ldj/03/DeskMate-Standalone wsl-publish
$env:UV_PYTHON_DOWNLOADS = 'never'
$env:UV_CACHE_DIR = 'D:\ldj\03\DeskMate-Standalone\.r1-verification\uv-publish-cache'
& C:\Users\28436\.local\bin\uv.exe lock --check --offline --python C:\Users\28436\.conda\envs\deskmate-win\python.exe
```

脚本在两个独立临时 CWD 中分别执行 `python -s -B -X utf8 -m pytest -q -ra -p no:cacheprovider`，指定仓库的 `pyproject.toml`、`--rootdir`、绝对 tests 路径、独立 `--basetemp` 和 JUnit；设置 `QT_QPA_PLATFORM=offscreen`、`PYTHONDONTWRITEBYTECODE=1` 和仓库/tests 的 `PYTHONPATH`。同一脚本还分别执行 `tests/verify_subagent.py`，`-m likecc --help`、`-m likecc.desktop --help`、`-m examples.deskmate_notifications --help`，以及独立根目录下的演示 `--check` 和 `--advance-minutes 10`。本机脚本与原始报告均不提交。

| 本次检查 | 实际结果 | 忽略目录 `.r1-verification` 中的证据 |
| --- | --- | --- |
| WSL Ubuntu-24.04 / cc 完整离线回归 | **995 passed，288.79s，退出 0** | `r7-wsl-publish-full.xml/log` |
| Windows / deskmate-win 完整离线回归 | **1 failed、988 passed、6 skipped，338.00s，退出 1** | `r7-win-publish-full.xml/log` |
| 独立 SubAgent | 两平台各 **90/90，退出 0** | `r7-{win,wsl}-publish-subagent.log` |
| CLI、桌面与 R7 演示帮助 | 两平台三个入口均退出 0 | `r7-{win,wsl}-publish-*-help.log` |
| 离线演示准备与推进时钟 | 两平台 `--check`、`--advance-minutes 10` 均退出 0 | `r7-{win,wsl}-publish-notification-{prepare,clock}.log` |
| Python AST / 内存编译 | 两平台各 **208 文件**；两份 manifest 与当前源码相同 | `r7-{win,wsl}-publish-manifest.json` |
| 依赖锁一致性 | uv 0.11.8 离线 `lock --check` 通过，解析 **58 packages**；pyproject.toml、uv.lock 与 HEAD 一致 | 本轮命令输出 |
| Git 空白与工作区 | `git diff --check` 通过，暂存区为空，HEAD 不变 | `r7-publish-blocked-audit.json` 与本轮输出 |

唯一失败是 `tests/test_schedule_window.py::test_scheduled_r4_question_permission_cards_preserve_draft`：问答和允许按钮已点击，但在第 84 行等待控制器变为 idle 且执行变为 completed 时超过现有 **6 秒**限制，抛出 `Qt condition timed out`。目前证据只证明完成条件未在时限内被观察到，不能直接判定为无害的时序抖动，也不能声称草稿丢失；根因仍待定位。本次遵循发布失败即停的要求，没有修改业务代码/测试或重跑掩盖失败。

Windows 的六项跳过仍是五项既有 POSIX 进程组用例和一项无适合系统文件的符号链接用例；WSL 全部运行。两平台 Python/SQLite/PySide6 版本与上一节相同。隔离 CWD 为 Windows `.r1-verification/r7-win-publish-cwd-07fuukyi` 和 WSL `/tmp/r7-wsl-publish-cwd-yqftpyo8`。

验证边界：本次 Qt 自动化使用 offscreen 和模拟托盘，不是新的 Windows 可见人工或真实系统托盘验收；此前七条可见主流程、单条及汇总气泡观察保留为历史证据。真实无托盘、所有窗口/缩放/多屏组合、原生气泡点击回调未补验；本次没有真实 Provider 调用或 R7 质量验收。修复/解释该回归并重新满足发布检查之前，不生成 R7 提交链接、R6→R7 对比链接或固定 ZIP；未创建 Release，未进入 R8。

## R7 等待器修复与重新发布验证（2026-11-24）

用户明确要求继续修复上述问题，并在修复后完成 Git 推送；固定 SHA 源码 ZIP 仍按此前授权流程执行。本节承接上节真实失败，不删除或改写首次发布检查结果。

失败的隔离工作区只读核对：问答和写入决定均已保存，分别为 answered/allow，两请求均结束；目标文件存在，artifact 为 verified，按 R4 换行规范化后的摘要与文件相同，没有工具错误，执行最终为 completed。会话中真实回读成功时间为 UTC 06:16:57.585854，运行完成为 06:16:57.883585；execution 的 started_at/ended_at 是模拟时钟，不能用于推断真实耗时。完整报告只有 call 阶段的 Qt 超时，没有 teardown 关闭失败。由于收尾先保存 completed，再关闭资源并发布 idle，这些证据不能还原超时当刻的界面状态。

另用隔离 Qt 探针排除了旧控件假设：`takeWidget()` 已解除旧卡片父子关系，尚未执行 deleteLater 时，findChild 已不能命中旧按钮。原用例单项动态审计 **1 passed，6.45s**；answer/allow 点击时均 enabled/visible，两条回复都有命令 ID 和成功回执，allow 到 idle/completed 约 2.47 秒。该单项通过只用于诊断，不替代上节失败的完整回归；证据为 `.r1-verification/r7-click-audit.log/.xml`。

可重复验证的缺陷在共享测试等待器：`QTest.qWait(10)` 可推进 Qt 事件，但在 Windows PySide6 下不保证让出 GIL 给后台 Python 线程。微型探针将自动切换间隔设为一秒，由 Qt singleShot 打开后台线程 gate，保持同样 0.25 秒时限：旧循环连续三次超时，Qt gate 已打开但 worker 未完成；增加 `time.sleep(0.001)` 后连续三次通过，约 15–31 毫秒。脚本为忽略目录 `r7_qwait_gil_probe.py`，数字来自本轮探针输出。此实验隔离了模型和数据库耗时，证明等待器本身缺少调度保证；因原失败没有即时线程栈，不将它夸大为还原当时每一步的唯一原因证明。

修复仅落在 `tests/test_desktop_window.py`：共享 spin 每轮处理 Qt 后显式让出线程；原默认 **6 秒**时限、失败逻辑、原业务断言及跳过条件完全不变。新增 `test_spin_advances_qt_events_and_background_python` 验证同一等待中 Qt 事件和后台线程都推进；finally 恢复解释器切换间隔并释放/回收线程。生产代码未作额外修改。

| 针对性检查 | 实际结果 | 忽略目录证据 |
| --- | --- | --- |
| 新行为回归 + 旧共享等待器 | **1 failed，16.43s**，后台线程完成条件超时 | `r7-qt-wait-red.xml/log` |
| 修复后两个完整窗口测试模块 | **12 passed，18.90s**，包括新回归及原失败用例 | `r7-qt-wait-green.xml/log` |
| 测试改动独立复审 | 原时限、断言、skip/xfail 未改变，线程及全局间隔有 finally 清理 | 本轮只读审查输出 |

专项命令：在既有 deskmate-win 解释器中设置 `QT_QPA_PLATFORM=offscreen`、仓库和 tests 的 `PYTHONPATH`，执行 `python -s -B -X utf8 -m pytest -q -p no:cacheprovider tests/test_desktop_window.py tests/test_schedule_window.py --junitxml=.r1-verification/r7-qt-wait-green.xml`。首次红回归只选新行为用例，在修改共享 spin 前执行；两份原始报告均保留。

修复后首次双平台并行全量（独立目录、不共写数据库）：WSL **996 passed，171.56s**；Windows **1 failed、989 passed、6 skipped，245.38s**。原 Qt 用例和新增调度回归在两平台均通过：原 Qt 用例 Windows 1.512s / WSL 0.826s，新回归 Windows 0.028s / WSL 0.013s。报告为 `r7-{win,wsl}-release-full.xml/log`。

Windows 此次唯一失败变为既有 `test_session_service.py::test_offline_demo_runs_when_all_textual_imports_are_blocked`：整个子进程（含首次依赖导入）的原 **20 秒**门限超时。只执行一次同入口仪器化诊断，保留 NoTextual 与 20 秒门限，加 importtime、每五秒 faulthandler 及阶段时间戳：总 **6.874s** 正常退出，RuntimeExtensions 首次导入 **6.345s**，实际演示 **0.232s**，确认 `repeated_resume_unchanged=True`。五秒线程栈位于 importlib.get_data / openai.types 模块加载，尚未进入演示。证据为 `r7-textual-probe-summary.json` 和对应 stdout/stderr 日志。

诊断证明本次导入成本占主导，但未复现 20 秒超时，不能确定先前失败的唯一原因。没有修改该测试或放宽时限；后续保持相同源码，在 WSL 全部结束后单独执行 Windows 完整检查，作为隔离并行资源影响的对照。中间失败报告原样保留，不用专项通过冒充完整通过。

最终同一源码完整验证通过。Windows 串行全量中，原 Qt 用例 **1.392s**、新增调度回归 **0.020s**、NoTextual 子进程用例 **8.183s**，均满足未修改的时限。串行通过不证明前一次子进程超时的唯一原因；这项未稳定复现的并行运行波动作为已知限制保留。

| 最终发布前检查 | 本次实际结果 | 本地证据（`.r1-verification`，不提交） |
| --- | --- | --- |
| WSL Ubuntu-24.04 / cc 完整离线回归 | **996 passed、0 skipped，171.56s，退出 0** | `r7-wsl-release-full.xml/log` |
| Windows / deskmate-win 串行完整离线回归 | **990 passed、6 skipped，190.75s，退出 0** | `r7-win-serial-full.xml/log` |
| 独立 SubAgent | 两平台各 **90/90，退出 0** | `r7-{wsl-release,win-serial}-subagent.log` |
| CLI、桌面、R7 演示帮助 | 两平台三个入口均退出 0 | 两份 summary.json 及对应 help 日志 |
| 离线演示准备、推进时钟 | 两平台 `--check`、`--advance-minutes 10` 均退出 0 | 两份 summary.json 及对应 notification 日志 |
| Python AST / 内存编译 | 两平台各 **208 个文件**；manifest 完全相同并匹配当前源码 | `r7-{wsl-release,win-serial}-manifest.json` |
| 依赖锁一致性 | `uv lock --check --offline` 解析 **58 packages**，退出 0；依赖文件未变 | 本轮命令输出 |
| 发布候选审查 | **24 个明确列出的源码/测试/演示/文档文件**；无真实凭据、数据库、个人配置或本机验证产物 | `r7-release-files.json`、`r7-release-audit.json` |
| Git 空白检查 | 工作区与暂存后的 `git diff --check` 均须通过，R6 历史保留，正常快进推送 | 本轮 Git 输出及发布审计 |

本次最终完整检查命令如下；脚本使用上节说明的隔离 CWD、offscreen、fake client 及模拟托盘，内部命令/版本不变。WSL 通过后源码未再改变，Windows 单独完成最终对照；不是将先前 Windows 失败数量改写为通过。

```powershell
Set-Location D:\ldj\03\DeskMate-Standalone
wsl.exe -d Ubuntu-24.04 --cd /mnt/d/ldj/03/DeskMate-Standalone -- /home/ldj/anaconda3/envs/cc/bin/python -s -B -X utf8 .r1-verification/r7_run.py /mnt/d/ldj/03/DeskMate-Standalone wsl-release
& C:\Users\28436\.conda\envs\deskmate-win\python.exe -s -B -X utf8 .r1-verification/r7_run.py D:/ldj/03/DeskMate-Standalone win-serial
```

源码 manifest 的规范化 SHA-256 为 `7a81cc4256655d2c199b4b25782ee135dc74450e2621910dec823f65af847fa2`。最终隔离目录为 WSL `/tmp/r7-wsl-release-cwd-qywaraxp`、Windows `.r1-verification/r7-win-serial-cwd-baz6sr9v`。Python、SQLite、PySide6 版本与上一节相同；Windows 六项跳过仍是既有平台/系统文件条件，没有新增 skip 或 xfail。

发布边界保持：此前七条 Windows 可见主流程是历史人工证据，本次是 Qt offscreen/模拟托盘自动化；真实无托盘、原生气泡点击回调、多屏/缩放组合及 R7 真实 Provider 质量未补验。系统气泡仍可能被屏蔽或在领取后崩溃时丢失，通知中心持久保留；完全退出不后台唤醒，通知不恢复旧授权或自动重试未知写入。本节记录提交前验证；实际 Commit、远程 SHA、固定 ZIP 与工作区状态由提交推送后的 Git/归档审计报告给出，不提前虚构 SHA。未开发 R8，也不创建 GitHub Release。
