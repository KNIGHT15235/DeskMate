"""UI-independent assembly and ownership of one Agent runtime.

R2 adds one leased SessionService and optional RuntimeExtensions. A borrowed
HookEngine remains owned by the entry; an extension-created engine is owned here.
"""
from __future__ import annotations

import asyncio
import logging
from copy import deepcopy
from pathlib import Path
from typing import Callable

from likecc import client as clients
from likecc.agent import Agent
from likecc.agents import task_manager as tasks
from likecc.agents.loader import AgentLoader
from likecc.agents.trace import TraceManager
from likecc.cache import FileCache
from likecc.config import AppConfig, ProviderConfig, WorktreeConfig
from likecc.hooks import HookEngine
from likecc.memory.instructions import load_instructions
from likecc.permissions import (
    DangerousCommandDetector, PathSandbox, PermissionChecker, PermissionMode, RuleEngine,
)
from likecc.teams.manager import TeamManager
from likecc.teams.registry import AgentNameRegistry
from likecc.tools import create_default_registry
from likecc.tools.agent_tool import AgentTool
from likecc.tools.enter_worktree import EnterWorktreeTool
from likecc.tools.exit_worktree import ExitWorktreeTool
from likecc.tools.impl.tool_search import ToolSearchTool
from likecc.tools.team_create import TeamCreateTool
from likecc.tools.team_delete import TeamDeleteTool
from likecc.worktree.manager import WorktreeManager

log = logging.getLogger(__name__)


async def finish_cleanup(task: asyncio.Task) -> None:
    """Reap a shared cleanup even if its waiter is cancelled (including twice)."""
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
        except Exception:
            break  # Retrieve below, preserving an already requested cancellation.
    # Always retrieve errors, but preserve the caller's cancellation.
    if cancelled:
        if not task.cancelled():
            task.exception()
        raise asyncio.CancelledError
    task.result()


class Runtime:
    def __init__(
        self, *, config: AppConfig, work_dir: str | Path,
        permission_mode: PermissionMode, hook_engine: HookEngine | None = None,
        cache_files: bool = False,
        client_factory: Callable | None = None,
    ) -> None:
        self.config = deepcopy(config)
        self.work_dir = str(Path(work_dir).resolve())
        self.permission_mode = permission_mode
        self.hook_engine = hook_engine  # borrowed; never started/closed here
        self.file_cache = FileCache() if cache_files else None
        self._client_factory = client_factory
        self.registry = create_default_registry(file_cache=self.file_cache)
        self.task_manager = tasks.TaskManager()
        self.trace_manager = TraceManager()
        self.provider: ProviderConfig | None = None
        self.client: clients.LLMClient | None = None
        self.checker: PermissionChecker | None = None
        self.agent: Agent | None = None
        self.worktree_manager: WorktreeManager | None = None
        self.agent_loader: AgentLoader | None = None
        self.team_manager: TeamManager | None = None
        self._agent_tool: AgentTool | None = None
        self._interactive = False
        self._initializing = False
        self._close_task: asyncio.Task | None = None
        self._stop_task: asyncio.Task | None = None
        self.service = None
        self.extensions = None

    @property
    def closed(self) -> bool:
        return self._close_task is not None

    async def initialize(self, provider: ProviderConfig, *, resolve_context: bool = False) -> None:
        """Acquire the common core; roll back every acquired resource on failure."""
        if self._initializing or self.client is not None or self._close_task is not None:
            raise RuntimeError("Runtime can only be initialized once")
        self._initializing = True
        self.provider = deepcopy(provider)
        try:
            self.client = (self._client_factory or clients.create_client)(self.provider)
            if resolve_context:
                await clients.resolve_context_window(self.provider)
            home = Path.home()
            root = Path(self.work_dir)
            self.checker = PermissionChecker(
                detector=DangerousCommandDetector(), sandbox=PathSandbox(self.work_dir),
                rule_engine=RuleEngine(
                    user_rules_path=home / ".likecc" / "permissions.yaml",
                    project_rules_path=root / ".likecc" / "permissions.yaml",
                    local_rules_path=root / ".likecc" / "permissions.local.yaml",
                ),
                mode=self.permission_mode,
            )
            self.registry.register(ToolSearchTool(self.registry, protocol=self.provider.protocol))
            self.agent = Agent(
                client=self.client, registry=self.registry, protocol=self.provider.protocol,
                work_dir=self.work_dir, permission_checker=self.checker,
                context_window=self.provider.get_context_window(),
                instructions_content=load_instructions(self.work_dir),
                hook_engine=self.hook_engine,
            )
            # Preserve the historical root, but never reuse another runtime's
            # tool-use IDs or replacement records within it.
            self.agent.session_dir = self.agent.session_dir / self.agent.agent_id
            self.agent.session_dir.mkdir(parents=True, exist_ok=True)
        except BaseException:
            await self.aclose()
            raise
        finally:
            self._initializing = False

    def assemble_delegation(
        self, *, interactive: bool,
        on_work_dir_change: Callable[[str], None] | None = None,
    ) -> None:
        """Wire shared extensions after the adapter has added its own tools."""
        if self.agent is None or self.provider is None or self._close_task is not None:
            raise RuntimeError("Runtime is not initialized or is closing")
        if self.worktree_manager is not None:
            raise RuntimeError("Delegation is already assembled")
        self._interactive = interactive

        def sync_worktree_context(path: str) -> None:
            self.registry.clear_file_caches()
            self.agent.work_dir = path
            self.checker.sandbox.set_project_root(path)
            if on_work_dir_change is not None:
                on_work_dir_change(path)

        wt_cfg = self.config.worktree or WorktreeConfig()
        self.worktree_manager = WorktreeManager(
            repo_root=self.work_dir, symlink_directories=wt_cfg.symlink_directories,
            on_work_dir_change=sync_worktree_context,
        )
        self.worktree_manager.restore_session()
        self.registry.register(EnterWorktreeTool(worktree_manager=self.worktree_manager))
        self.registry.register(ExitWorktreeTool(worktree_manager=self.worktree_manager))
        self.agent_loader = AgentLoader(
            self.work_dir, enable_verification=self.config.enable_verification_agent,
        )
        self.agent_loader.load_all()
        self.team_manager = TeamManager(
            worktree_manager=self.worktree_manager, trace_manager=self.trace_manager,
            name_registry=AgentNameRegistry(),
        )
        self._agent_tool = AgentTool(
            agent_loader=self.agent_loader, task_manager=self.task_manager,
            trace_manager=self.trace_manager, parent_agent=self.agent,
            enable_fork=self.config.enable_fork, provider_config=self.provider,
            worktree_manager=self.worktree_manager, team_manager=self.team_manager,
        )
        self.registry.register(self._agent_tool)
        self.registry.register(TeamCreateTool(
            team_manager=self.team_manager, parent_agent=self.agent,
            teammate_mode=self.config.teammate_mode if interactive else "in-process",
            is_interactive=interactive,
            enable_coordinator_mode=self.config.enable_coordinator_mode,
        ))
        self.registry.register(TeamDeleteTool(
            team_manager=self.team_manager, parent_agent=self.agent,
        ))

    async def aclose(self) -> None:
        """Stop children before clients; concurrent/repeated callers share one close."""
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._close(), name="runtime-close")
        await finish_cleanup(self._close_task)

    async def stop_background(self) -> None:
        """Quiesce children before entry-owned hooks/MCP/session are closed."""
        if self._stop_task is None:
            self._stop_task = asyncio.create_task(self._stop_background())
        await finish_cleanup(self._stop_task)

    async def _stop_background(self) -> None:
        try:
            await self.task_manager.shutdown()
        finally:
            if self.team_manager is not None:
                await self.team_manager.shutdown(delete_teams=self._interactive)

    async def _close(self) -> None:
        # Each stage is attempted even when a preceding resource cannot close.
        closers = []
        if self.service is not None:
            closers.append(self.service.aclose)
        closers.append(self.stop_background)
        if self.extensions is not None:
            closers.append(self.extensions.aclose)
        if self._agent_tool is not None:
            closers.append(self._agent_tool.aclose)
        if self.client is not None:
            closers.append(self.client.aclose)
        for close in closers:
            try:
                await close()
            except Exception:
                log.exception("Runtime resource cleanup failed")
