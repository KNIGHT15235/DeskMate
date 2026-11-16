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
