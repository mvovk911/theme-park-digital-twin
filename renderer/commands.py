"""Bounded, cancellable commands between HTTP workers and the native GPU owner."""

from __future__ import annotations

from dataclasses import dataclass, field
import itertools
import queue
import threading
import time
from typing import Any, Callable


class MailboxClosed(RuntimeError):
    pass


@dataclass
class RenderCommand:
    id: int
    kind: str
    payload: dict[str, Any]
    deadline: float
    done: threading.Event = field(default_factory=threading.Event)
    result: dict[str, Any] | None = None
    cancelled: bool = False


class CommandMailbox:
    """Native objects never cross this boundary; results contain plain values."""

    def __init__(
        self, capacity: int = 128, clock: Callable[[], float] = time.monotonic
    ):
        self._queue: queue.Queue[RenderCommand] = queue.Queue(maxsize=capacity)
        self._clock = clock
        self._lock = threading.RLock()
        self._ids = itertools.count(1)
        self._outstanding: dict[int, RenderCommand] = {}
        self._closed = False

    def submit(self, kind: str, payload: dict, ttl: float = 15.0) -> RenderCommand:
        with self._lock:
            if self._closed:
                raise MailboxClosed("Renderer command service is unavailable")
            command = RenderCommand(
                next(self._ids), kind, dict(payload), self._clock() + ttl
            )
            self._queue.put_nowait(command)  # queue.Full is deliberately exposed.
            self._outstanding[command.id] = command
            return command

    def active(self, command: RenderCommand) -> bool:
        with self._lock:
            return (
                not self._closed
                and not command.cancelled
                and not command.done.is_set()
                and self._clock() < command.deadline
            )

    def take(self) -> RenderCommand | None:
        while True:
            try:
                command = self._queue.get_nowait()
            except queue.Empty:
                return None
            if self.active(command):
                return command
            self.cancel(command, "Renderer request expired")

    def finish(self, command: RenderCommand, result: dict | None = None) -> bool:
        with self._lock:
            if not self.active(command):
                self.cancel(command, "Renderer request expired")
                return False
            command.result = result or {"accepted": True}
            self._outstanding.pop(command.id, None)
            command.done.set()
            return True

    def cancel(
        self, command: RenderCommand, reason: str = "Renderer request cancelled"
    ) -> None:
        with self._lock:
            if command.done.is_set():
                return
            command.cancelled = True
            command.result = {"error": reason, "cancelled": True}
            self._outstanding.pop(command.id, None)
            command.done.set()

    def close(self, reason: str = "Renderer stopped") -> None:
        with self._lock:
            self._closed = True
            for command in list(self._outstanding.values()):
                self.cancel(command, reason)
            while True:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break

    @property
    def outstanding(self) -> int:
        with self._lock:
            return len(self._outstanding)
