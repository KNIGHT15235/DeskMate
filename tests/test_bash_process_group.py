"""R3-0: an exited shell may still own children holding its output pipes."""
import asyncio
import os
from pathlib import Path
import signal

import pytest

from likecc.tools.bash import Bash, Params
from likecc.tools.work_dir import tool_working_directory

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(os.name != "posix", reason="POSIX process-group contract")]


def running(pid):
    try:
        return Path(f"/proc/{pid}/stat").read_text().split()[2] != "Z"
    except FileNotFoundError:
        return False


async def until(predicate):
    async with asyncio.timeout(3):
        while not predicate():
            await asyncio.sleep(0.01)


@pytest.mark.parametrize("cancel", [False, True])
async def test_exited_shell_child_pipes_are_reclaimed(tmp_path, monkeypatch, cancel):
    processes = []
    original = asyncio.create_subprocess_shell
    async def create(*args, **kwargs):
        proc = await original(*args, **kwargs)
        processes.append(proc)
        return proc
    monkeypatch.setattr(asyncio, "create_subprocess_shell", create)
    pidfile = tmp_path / "child.pid"
    with tool_working_directory(tmp_path):
        task = asyncio.create_task(Bash().execute(Params(command="sleep 30 & echo $! > child.pid", timeout=1)))
    try:
        await until(lambda: pidfile.exists() and processes and processes[0].returncode == 0)
        child = int(pidfile.read_text())
        assert running(child)
        assert not task.done()  # shell exited, but communicate still awaits pipes
        if cancel:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 3)
        else:
            result = await asyncio.wait_for(task, 3)
            assert result.is_error and result.output == "Error: command timed out after 1s"
        await until(lambda: not running(child))
        await asyncio.wait_for(processes[0].communicate(), 3)
    finally:
        # Reap only the new session created by this test, even on assertion failure.
        for proc in processes:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await asyncio.wait_for(proc.communicate(), 3)
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_normal_foreground_command_format(tmp_path):
    with tool_working_directory(tmp_path):
        result = await Bash().execute(Params(command="printf 'foreground'; printf 'warning' >&2"))
    assert not result.is_error
    assert result.output == "STDOUT:\nforeground\nSTDERR:\nwarning"


async def test_exited_process_cleanup_is_repeatable_and_uses_owned_group(monkeypatch):
    from likecc.tools.bash import _terminate_owned_process
    proc = await asyncio.create_subprocess_shell("true", start_new_session=True,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    await asyncio.wait_for(proc.communicate(), 3)
    groups = []
    original = os.killpg
    def record(group, sig):
        groups.append(group)
        original(group, sig)
    monkeypatch.setattr(os, "killpg", record)
    await asyncio.wait_for(_terminate_owned_process(proc), 3)
    await asyncio.wait_for(_terminate_owned_process(proc), 3)
    await _terminate_owned_process(None)
    assert groups == [proc.pid, proc.pid]
    assert proc.pid != os.getpgrp()
