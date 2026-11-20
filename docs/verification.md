# 验证说明

本页按阶段保留 LikeCC 0.2.0 和 DeskMate 各轮实际结果。各阶段的“待确认”代表当时状态，最新结果见文末 R4 验证。

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
