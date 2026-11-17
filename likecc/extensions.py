"""Explicit, non-UI extension assembly owned by Runtime.

An entry may lend a HookEngine (and own startup/shutdown itself). With hooks=True
this component instead creates and owns the configured engine. Never both.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from likecc.hooks import HookContext, HookEngine, load_hooks
from likecc.mcp import MCPManager
from likecc.runtime import finish_cleanup
from likecc.skills.loader import SkillLoader
from likecc.skills.executor import SkillExecutor
from likecc.tools.load_skill import LoadSkill
from likecc.tools.ask_user import AskUserTool
from likecc.tools.exit_plan_mode import ExitPlanModeTool
from likecc.tools.synthetic_output import SyntheticOutputTool
from likecc.worktree.cleanup import start_stale_cleanup_task


@dataclass(frozen=True)
class ExtensionOptions:
    skills: bool = False
    interactive_tools: bool = False
    mcp: bool = False
    hooks: bool = False
    stale_cleanup: bool = False


class RuntimeExtensions:
    def __init__(self, runtime, options: ExtensionOptions, *, mcp_factory=None):
        if runtime.extensions is not None or runtime.closed:
            raise RuntimeError("Extensions already configured or Runtime closed")
        if options.hooks and runtime.hook_engine is not None:
            raise ValueError("Cannot own lifecycle of a borrowed HookEngine")
        self.runtime, self.options = runtime, options
        self.mcp_factory = mcp_factory or MCPManager
        self.skill_loader = self.skill_executor = self.load_skill = None
        self.exit_plan = None
        self.mcp_manager = None
        self.mcp_instructions = ""
        self.diagnostics: list[str] = []
        self.ready, self._stop = asyncio.Event(), asyncio.Event()
        self._mcp_task = self._stale_task = self._close_task = None
        self._initialized = False
        self.hook_engine = None
        if options.skills:
            self.load_skill = LoadSkill()
            runtime.registry.register(self.load_skill)
        runtime.extensions = self

    async def initialize(self):
        if self._initialized or self._close_task:
            raise RuntimeError("Extensions can only initialize once")
        self._initialized = True
        runtime, agent = self.runtime, self.runtime.agent
        if agent is None:
            raise RuntimeError("Initialize Runtime core first")
        try:
            if self.options.skills:
                self.skill_loader = SkillLoader(runtime.work_dir)
                self.skill_loader.load_all()
                self.load_skill.set_loader(self.skill_loader)
                self.load_skill.set_agent(agent)
                self.skill_executor = SkillExecutor(agent=agent, client=runtime.client, protocol=runtime.provider.protocol)
                catalog = self.skill_loader.get_catalog()
                if catalog:
                    agent.set_skill_catalog("You can use the following Skills:\n\n" +
                        "\n".join(f"- {name}: {desc}" for name, desc in catalog) +
                        "\n\nIf the user's request matches a Skill, call LoadSkill to activate it.")
            if self.options.interactive_tools:
                runtime.registry.register(AskUserTool())
                self.exit_plan = ExitPlanModeTool()
                self.exit_plan._is_plan_mode = lambda: agent.plan_mode
                self.exit_plan._plan_exists = lambda: agent._get_plan_path().exists()
                runtime.registry.register(self.exit_plan)
                runtime.registry.register(SyntheticOutputTool())
            if self.options.hooks:
                self.hook_engine = HookEngine(load_hooks(runtime.config.raw_hooks))
                runtime.hook_engine = agent.hook_engine = self.hook_engine
                await self.hook_engine.run_hooks("startup", HookContext(event_name="startup", work_dir=runtime.work_dir))
            if self.options.stale_cleanup and runtime.worktree_manager:
                cfg = runtime.config.worktree
                self._stale_task = asyncio.create_task(start_stale_cleanup_task(
                    runtime.worktree_manager, cfg.stale_cleanup_interval, cfg.stale_cutoff_hours))
            if self.options.mcp and runtime.config.mcp_servers:
                self._mcp_task = asyncio.create_task(self._serve_mcp(), name="mcp-lifetime")
            else:
                self.ready.set()
        except BaseException:
            await runtime.aclose()
            raise

    async def _serve_mcp(self):
        try:
            self.mcp_manager = self.mcp_factory()
            self.mcp_manager.load_configs(self.runtime.config.mcp_servers)
            self.diagnostics.extend(await self.mcp_manager.register_all_tools(self.runtime.registry))
            parts = []
            for cfg in self.runtime.config.mcp_servers:
                names = [t.name for t in self.runtime.registry.list_tools() if t.name.startswith(f"mcp__{cfg.name}__")]
                if names:
                    parts.append(f"## {cfg.name}\nAvailable tools: " + ", ".join(names))
            if parts:
                self.mcp_instructions = "# MCP Server Instructions\n\nThe following MCP servers are connected. Use their tools when the user asks.\n\n" + "\n\n".join(parts)
            self.ready.set()
            await self._stop.wait()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.diagnostics.append(f"MCP unavailable: {exc}")
        finally:
            try:
                if self.mcp_manager is not None:
                    await self.mcp_manager.shutdown()
            except Exception as exc:
                self.diagnostics.append(f"MCP shutdown failed: {exc}")
            finally:
                self.mcp_manager = None
                self.ready.set()

    async def wait_ready(self):
        if not self._initialized:
            raise RuntimeError("Initialize configured extensions before running")
        await self.ready.wait()

    async def aclose(self):
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._close())
        await finish_cleanup(self._close_task)

    async def _close(self):
        if self._stale_task:
            self._stale_task.cancel()
            await asyncio.gather(self._stale_task, return_exceptions=True)
        try:
            if self._mcp_task:
                if not self.ready.is_set():
                    self._mcp_task.cancel()
                else:
                    self._stop.set()
                await asyncio.gather(self._mcp_task, return_exceptions=True)
        finally:
            if self.hook_engine:
                try:
                    async with asyncio.timeout(3):
                        await self.hook_engine.run_hooks("shutdown", HookContext(event_name="shutdown", work_dir=self.runtime.work_dir))
                        await self.hook_engine.wait_for_background_hooks()
                finally:
                    await self.hook_engine.cancel_background_hooks()
