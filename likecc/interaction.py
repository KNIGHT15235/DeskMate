"""Run-scoped, in-process request/reply protocol; no UI objects cross this API."""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any


class PermissionResponse(Enum):
    ALLOW = "allow"
    DENY = "deny"
    ALLOW_ALWAYS = "allow_always"


@dataclass
class PermissionRequest:
    tool_name: str
    description: str
    run_id: str
    request_id: str
    tool_id: str


@dataclass
class UserInputRequest:
    questions: list[dict[str, Any]]
    run_id: str
    request_id: str
    tool_id: str


class Interaction:
    """Only the matching live run can answer a request, at most once.

    An absent Interaction means non-interactive denial. An explicitly attached
    but abandoned handler is bounded by timeout. Replies contain no Futures.
    """
    def __init__(self, run_id: str | None = None, *, timeout: float = 300.0):
        self.run_id = run_id or uuid.uuid4().hex
        self.timeout = timeout
        self._pending: dict[str, tuple[str, asyncio.Future]] = {}
        self._closed = False

    def request(self, kind: str) -> str:
        if self._closed:
            raise RuntimeError("Interaction is closed")
        request_id = uuid.uuid4().hex
        self._pending[request_id] = (kind, asyncio.get_running_loop().create_future())
        return request_id

    def reply(self, run_id: str, request_id: str, value: Any) -> bool:
        pending = self._pending.get(request_id)
        if run_id != self.run_id or pending is None or self._closed:
            return False
        kind, future = pending
        if future.done():
            return False
        if kind == "permission":
            try:
                value = PermissionResponse(value)
            except (ValueError, TypeError):
                return False
        elif not isinstance(value, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in value.items()
        ):
            return False
        future.set_result(value)
        return True

    def is_pending(self, request_id: str) -> bool:
        """Read-only liveness check; navigation must never answer the future."""
        pending = self._pending.get(request_id)
        return bool(not self._closed and pending and not pending[1].done())

    async def wait(self, request_id: str) -> Any:
        _, future = self._pending[request_id]
        try:
            return await asyncio.wait_for(future, self.timeout)
        finally:
            self._pending.pop(request_id, None)

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def close(self) -> None:
        self._closed = True
        for _, future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()
