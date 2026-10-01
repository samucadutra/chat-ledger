"""Handler registry keyed by job kind. Later features register their kinds here."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from chatledger_core.domain.jobs.job import Job


@dataclass
class JobContext:
    """Passed to handlers. ``lease_lost`` is set when the lease can no longer be renewed;
    long-running handlers should check it and abort."""

    worker_id: str
    lease_lost: threading.Event = field(default_factory=threading.Event)


Handler = Callable[[Job, JobContext], None]

UNKNOWN_JOB_KIND = "UNKNOWN_JOB_KIND"


class UnknownJobKindError(LookupError):
    def __init__(self, kind: str) -> None:
        super().__init__(f"{UNKNOWN_JOB_KIND}: no handler registered for kind '{kind}'")
        self.kind = kind


class HandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, kind: str, handler: Handler) -> None:
        if kind in self._handlers:
            raise ValueError(f"handler for job kind '{kind}' already registered")
        self._handlers[kind] = handler

    def get(self, kind: str) -> Handler:
        try:
            return self._handlers[kind]
        except KeyError:
            raise UnknownJobKindError(kind) from None

    def kinds(self) -> list[str]:
        return sorted(self._handlers)
