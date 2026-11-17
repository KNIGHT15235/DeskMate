# 验证说明

本页保留 LikeCC 0.2.0 的历史发布结果；本次 DeskMate R1 的独立实测记录在文末，不将两者混为同一次验证。

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
