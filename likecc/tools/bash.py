
from __future__ import annotations

import asyncio
import os
import signal

from pydantic import BaseModel, Field

from likecc.tools.base import Tool, ToolResult
from likecc.tools.work_dir import get_tool_work_dir

MAX_TIMEOUT = 600


async def _terminate_owned_process(proc) -> None:
    """Only for shells started with start_new_session on POSIX.

    returncode describes the shell, not the group or inherited output pipes.
    """
    if proc is None:
        return
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        elif proc.returncode is None:
            proc.kill()
    except ProcessLookupError:
        pass
    await proc.wait()
    await proc.communicate()  # reap transports even after communicate was cancelled


class Params(BaseModel):
    command: str = Field(description="Shell command to execute")
    timeout: int = Field(default=120, description="Timeout in seconds (max 600)")


class Bash(Tool):
    name = "Bash"
    description = "Execute a shell command and return stdout and stderr."
    params_model = Params
    category = "command"


    async def execute(self, params: Params) -> ToolResult:
        timeout = min(params.timeout, MAX_TIMEOUT)
        proc = None

        async def terminate() -> None:
            from likecc.runtime import finish_cleanup
            await finish_cleanup(asyncio.create_task(_terminate_owned_process(proc)))

        try:
            proc = await asyncio.create_subprocess_shell(
                params.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(get_tool_work_dir()),
                start_new_session=os.name == "posix",
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            await terminate()
            return ToolResult(output=f"Error: command timed out after {timeout}s", is_error=True)
        except asyncio.CancelledError:
            await terminate()
            raise
        except Exception as e:
            return ToolResult(output=f"Error executing command: {e}", is_error=True)

        parts: list[str] = []
        if stdout:
            parts.append(f"STDOUT:\n{stdout.decode(errors='replace')}")
        if stderr:
            parts.append(f"STDERR:\n{stderr.decode(errors='replace')}")
        if not parts:
            parts.append("(no output)")

        output = "\n".join(parts)
        return ToolResult(output=output, is_error=proc.returncode != 0)
