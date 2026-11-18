"""Launch fault injection uses real Qt and a real worker, with no model network."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import asyncio
import signal
import threading

import pytest
pytest.importorskip("PySide6", reason="optional desktop extra")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from shiboken6 import isValid

from likecc.desktop import application as desktop
from likecc.desktop.controller import DesktopController, DesktopOptions
from likecc.runtime import Runtime
from test_desktop_controller import close, wait

ActualDesktopApplication = desktop.DesktopApplication


@pytest.fixture
def launch_resources(monkeypatch):
    app = QApplication.instance() or QApplication([])
    controllers, runtimes, owners, closed = [], [], [], []
    signals = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}

    class ObservedRuntime(Runtime):
        async def initialize(self, *args, **kwargs):
            await super().initialize(*args, **kwargs)
            runtimes.append(self)
            original = self.client.aclose
            async def tracked_close():
                await original()
                closed.append((threading.get_ident(), id(asyncio.get_running_loop())))
            self.client.aclose = tracked_close

    def controller_factory(options):
        c = DesktopController(options, runtime_factory=ObservedRuntime)
        controllers.append(c)
        wait(c, lambda s: s["state"] == "idle")
        return c

    original_owner = desktop.DesktopApplication
    def owner_factory(*args, **kwargs):
        owner = original_owner(*args, **kwargs)
        owners.append(owner)
        return owner

    monkeypatch.setattr(desktop, "DesktopController", controller_factory)
    monkeypatch.setattr(desktop, "DesktopApplication", owner_factory)
    yield app, controllers, runtimes, owners, closed, signals
    # The unfixed baseline must not leak workers when an assertion fails.
    for c in controllers:
        close(c)
    for owner in owners:
        if isValid(owner):
            owner.dispose()
    for sig, handler in signals.items():
        signal.signal(sig, handler)


@pytest.mark.parametrize("phase", ["owner_constructor", "owner_midway", "exec_error", "exec_return"])
def test_launch_closes_real_worker_when_qt_cannot_keep_running(launch_resources, monkeypatch, phase):
    app, controllers, runtimes, owners, closed, signals = launch_resources
    failure = ValueError(f"injected {phase}")
    if phase == "owner_constructor":
        def fail_owner(*args, **kwargs):
            raise failure
        monkeypatch.setattr(desktop, "DesktopApplication", fail_owner)
    elif phase == "owner_midway":
        def fail_poll(owner):
            owners.append(owner)
            raise failure
        monkeypatch.setattr(ActualDesktopApplication, "poll", fail_poll)
    elif phase == "exec_error":
        def fail_exec():
            raise failure
        monkeypatch.setattr(app, "exec", fail_exec)
    else:
        monkeypatch.setattr(app, "exec", lambda: 7)
    if phase == "exec_return":
        assert desktop.launch(DesktopOptions(demo=True)) == 7
    else:
        with pytest.raises(ValueError) as raised:
            desktop.launch(DesktopOptions(demo=True))
        assert raised.value is failure
    assert len(controllers) == len(runtimes) == 1
    assert not controllers[0].is_alive
    assert runtimes[0].closed
    assert runtimes[0].service.session._file.closed
    assert len(closed) == 1 and closed[0][0] == controllers[0].snapshot()["worker_thread"]
    assert all(signal.getsignal(sig) == handler for sig, handler in signals.items())
    if phase == "owner_midway":
        assert not owners[0].timer.isActive()
        assert not owners[0].window.isVisible()


def test_partial_signal_registration_restores_only_successful_changes(launch_resources, monkeypatch):
    _, controllers, runtimes, _, closed, signals = launch_resources
    original = signal.signal
    changed = []
    failure = RuntimeError("injected SIGTERM registration failure")
    def register(sig, handler):
        changed.append((sig, handler))
        if sig == signal.SIGTERM and handler != signals[sig]:
            raise failure
        return original(sig, handler)
    monkeypatch.setattr(signal, "signal", register)
    with pytest.raises(RuntimeError) as raised:
        desktop.launch(DesktopOptions(demo=True))
    assert raised.value is failure
    assert not controllers[0].is_alive
    assert runtimes[0].service.session._file.closed and len(closed) == 1
    assert [sig for sig, handler in changed if handler == signals[sig]] == [signal.SIGINT]
    assert all(signal.getsignal(sig) == handler for sig, handler in signals.items())


def test_normal_qt_exit_waits_asynchronously_and_fallback_is_repeatable(launch_resources, monkeypatch):
    app, controllers, runtimes, owners, closed, signals = launch_resources
    factory = desktop.DesktopApplication
    inside_exec = False
    original_exec = app.exec
    def actual_exec():
        nonlocal inside_exec
        inside_exec = True
        try:
            return original_exec()
        finally:
            inside_exec = False
    def owner(*args, **kwargs):
        result = factory(*args, **kwargs)
        QTimer.singleShot(0, result.request_exit)
        c = controllers[0]
        original_wait = c.wait_closed
        def checked_wait(timeout=5):
            assert not inside_exec, "Do not block a running Qt event loop"
            return original_wait(timeout)
        c.wait_closed = checked_wait
        return result
    monkeypatch.setattr(app, "exec", actual_exec)
    monkeypatch.setattr(desktop, "DesktopApplication", owner)
    assert desktop.launch(DesktopOptions(demo=True)) == 0
    c = controllers[0]
    c.request_close()
    c.request_close()
    assert c.wait_closed(0) and not c.is_alive
    assert len(closed) == 1 and runtimes[0].service.session._file.closed
    assert all(signal.getsignal(sig) == handler for sig, handler in signals.items())


@pytest.mark.parametrize("original_failure", [False, True])
def test_fallback_timeout_reports_unclean_exit_without_masking_original(launch_resources, monkeypatch, caplog, original_failure):
    app, controllers, runtimes, _, closed, signals = launch_resources
    release, entered = threading.Event(), threading.Event()
    factory = desktop.DesktopController
    def slow_controller(options):
        c = factory(options)
        original_close = runtimes[0]._close
        async def slow_close():
            entered.set()
            while not release.is_set():
                await asyncio.sleep(0.005)
            await original_close()
        runtimes[0]._close = slow_close
        return c
    failure = ValueError("original exec error")
    def exec_shell():
        if original_failure:
            raise failure
        return 0
    monkeypatch.setattr(desktop, "DesktopController", slow_controller)
    monkeypatch.setattr(app, "exec", exec_shell)
    monkeypatch.setattr(desktop, "FALLBACK_SHUTDOWN_TIMEOUT", 0.05)
    try:
        if original_failure:
            with pytest.raises(ValueError) as raised:
                desktop.launch(DesktopOptions(demo=True))
            assert raised.value is failure
            assert any("清理未完成" in note for note in failure.__notes__)
        else:
            with pytest.raises(RuntimeError, match="清理未完成"):
                desktop.launch(DesktopOptions(demo=True))
        assert entered.wait(3)
        assert controllers[0].is_alive and not closed
        assert "未强制终止" in caplog.text
        assert all(signal.getsignal(sig) == handler for sig, handler in signals.items())
    finally:
        release.set()
        if controllers:
            controllers[0].request_close()
            assert controllers[0].wait_closed(3)
    assert len(closed) == 1


def test_launch_closes_during_backend_initialization(monkeypatch):
    app = QApplication.instance() or QApplication([])
    started, finalized = threading.Event(), threading.Event()
    controllers = []
    class InitializingRuntime(Runtime):
        async def initialize(self, *args, **kwargs):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                finalized.set()
    def factory(options):
        c = DesktopController(options, runtime_factory=InitializingRuntime)
        controllers.append(c)
        assert started.wait(3)
        return c
    monkeypatch.setattr(desktop, "DesktopController", factory)
    monkeypatch.setattr(app, "exec", lambda: 0)
    try:
        assert desktop.launch(DesktopOptions(demo=True)) == 0
        assert not controllers[0].is_alive and finalized.is_set()
    finally:
        for c in controllers:
            close(c)


@pytest.mark.parametrize("cleanup_error_type", [RuntimeError, KeyboardInterrupt])
def test_cleanup_error_never_masks_original_or_skips_signal_restore(launch_resources, monkeypatch, cleanup_error_type):
    app, controllers, runtimes, _, closed, signals = launch_resources
    factory = desktop.DesktopController
    def controller(options):
        c = factory(options)
        original_wait = c.wait_closed
        def failed_wait(timeout):
            assert original_wait(timeout)
            raise cleanup_error_type("injected fallback diagnostic")
        c.wait_closed = failed_wait
        return c
    failure = ValueError("keep original exception")
    def fail_exec():
        raise failure
    monkeypatch.setattr(desktop, "DesktopController", controller)
    monkeypatch.setattr(app, "exec", fail_exec)
    with pytest.raises(ValueError) as raised:
        desktop.launch(DesktopOptions(demo=True))
    assert raised.value is failure
    assert any("injected fallback diagnostic" in note for note in failure.__notes__)
    assert not controllers[0].is_alive and len(closed) == 1
    assert runtimes[0].service.session._file.closed
    assert all(signal.getsignal(sig) == handler for sig, handler in signals.items())
