
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from likecc.config import ConfigError, load_config
from likecc.hooks import HookConfigError, HookContext, HookEngine, load_hooks
from likecc.permissions import PermissionMode


HEADLESS_BACKGROUND_TIMEOUT = 180.0
HEADLESS_NOTIFICATION_INTERVAL = 0.1


def main() -> None:
    # 先确保 .likecc/ 目录存在，否则下面写 debug.log 会因目录不存在而崩溃
    Path(".likecc").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(message)s",
        filename=".likecc/debug.log",
        filemode="w",
    )

    parser = argparse.ArgumentParser(prog="likecc", description="LikeCC AI coding assistant")
    parser.add_argument(
        "--mode",
        choices=[m.value for m in PermissionMode],
        default=None,
        help="Permission mode (overrides config.yaml)",
    )
    parser.add_argument(
        "-p",
        metavar="PROMPT",
        default=None,
        help="Run non-interactively: execute the prompt and print the result to stdout",
    )
    args = parser.parse_args()

    try:
        config = load_config()
    except ConfigError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    mode_str = args.mode if args.mode else config.permission_mode
    permission_mode = PermissionMode(mode_str)

    try:
        hooks = load_hooks(config.raw_hooks)
    except HookConfigError as e:
        print(f"Hook config error: {e}", file=sys.stderr)
        sys.exit(1)

    hook_engine = HookEngine(hooks) if hooks else None

    work_dir = str(Path.cwd().resolve())

    if args.p is not None:
        asyncio.run(
            _run_prompt_with_hook_cleanup(
                config, permission_mode, hook_engine, args.p, work_dir=work_dir
            )
        )
        return

    from likecc.app import LikeCCApp
    from likecc.driver import NoAltScreenDriver

    app = LikeCCApp(
        work_dir=work_dir,
        providers=config.providers,
        permission_mode=permission_mode,
        mcp_servers=config.mcp_servers,
        hook_engine=hook_engine,
        enable_fork=config.enable_fork,
        enable_verification_agent=config.enable_verification_agent,
        worktree_config=config.worktree,
        teammate_mode=config.teammate_mode,
        enable_coordinator_mode=config.enable_coordinator_mode,
        driver_class=NoAltScreenDriver,
    )
    app.run()


async def _shutdown_hook_engine(hook_engine: HookEngine | None, work_dir: str) -> None:
    if hook_engine is None:
        return

    async def _run_shutdown_hooks() -> None:
        await hook_engine.run_hooks(
            "shutdown", HookContext(event_name="shutdown", work_dir=work_dir)
        )
        await hook_engine.wait_for_background_hooks()

    try:
        await asyncio.wait_for(_run_shutdown_hooks(), timeout=3.0)
    except asyncio.TimeoutError:
        logging.warning("Timed out while shutting down hooks")
    except Exception:
        logging.exception("Hook shutdown failed")
    finally:
        await hook_engine.cancel_background_hooks()


async def _run_prompt_with_hook_cleanup(
    config, permission_mode, hook_engine: HookEngine | None, prompt: str,
    *, work_dir: str | None = None,
) -> None:
    work_dir = str(Path(work_dir or Path.cwd()).resolve())
    try:
        if hook_engine is not None:
            await hook_engine.run_hooks(
                "startup", HookContext(event_name="startup", work_dir=work_dir)
            )
        await _run_prompt(config, permission_mode, hook_engine, prompt, work_dir=work_dir)
    finally:
        from likecc.runtime import finish_cleanup
        await finish_cleanup(asyncio.create_task(_shutdown_hook_engine(hook_engine, work_dir)))


async def _run_prompt(config, permission_mode, hook_engine, prompt: str,
                      *, work_dir: str | None = None) -> None:
    from likecc.conversation import ConversationManager
    from likecc.runtime import Runtime

    runtime = Runtime(
        config=config, work_dir=work_dir or Path.cwd(),
        permission_mode=permission_mode, hook_engine=hook_engine,
    )
    try:
        await runtime.initialize(config.providers[0], resolve_context=True)
        runtime.assemble_delegation(interactive=False)
        agent = runtime.agent
        task_manager = runtime.task_manager
        team_manager = runtime.team_manager

        def drain_notifications() -> list[str]:
            notes: list[str] = []
            for t in task_manager.poll_completed():
                notes.append(
                    f"<task-notification>\n<task_id>{t.id}</task_id>\n"
                    f"<status>{t.status}</status>\n<result>{t.result}</result>\n"
                    f"</task-notification>"
                )
            notes.extend(team_manager.drain_lead_mailbox())
            return notes

        agent.notification_fn = drain_notifications

        conv = ConversationManager()
        last_result = await agent.run_to_completion(prompt, conv)
        print(last_result, flush=True)

        # Ordinary background sub-agents need the same delivery loop as team
        # members. Bound the whole follow-up phase, including new model turns.
        async with asyncio.timeout(HEADLESS_BACKGROUND_TIMEOUT):
            while True:
                notes = drain_notifications()
                if notes:
                    for note in notes:
                        conv.add_system_reminder(note)
                    last_result = await agent.run_to_completion(
                        "Background agent notifications received. Process them and continue.",
                        conv,
                    )
                    print(last_result, flush=True)
                    await asyncio.sleep(0)
                    continue

                pending = [
                    task for task in task_manager._async_tasks.values()
                    if not task.done()
                ]
                if not pending:
                    break
                await asyncio.wait(
                    pending,
                    timeout=HEADLESS_NOTIFICATION_INTERVAL,
                    return_when=asyncio.FIRST_COMPLETED,
                )

    finally:
        await runtime.aclose()


if __name__ == "__main__":
    main()
