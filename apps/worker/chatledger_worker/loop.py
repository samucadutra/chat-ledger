"""Worker job loop: claim -> dispatch -> complete/fail, with lease renewal and sweeps."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from uuid import UUID

from chatledger_core.domain.jobs.job import Job
from chatledger_core.domain.jobs.queue import JobQueue
from chatledger_core.infra.logging import bind_context, get_logger, unbind_context
from chatledger_worker.registry import HandlerRegistry, JobContext, UnknownJobKindError

_log = get_logger("chatledger_worker.loop")


@dataclass(frozen=True)
class LoopConfig:
    lease_renew_seconds: float = 20
    sweep_interval_seconds: float = 15
    poll_interval_seconds: float = 1.0


def format_error(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


class _LeaseRenewer(threading.Thread):
    def __init__(
        self, queue: JobQueue, job_id: UUID, ctx: JobContext, every_seconds: float
    ) -> None:
        super().__init__(name=f"lease-{job_id}", daemon=True)
        self._queue = queue
        self._job_id = job_id
        self._ctx = ctx
        self._every = every_seconds
        self._done = threading.Event()

    def run(self) -> None:
        while not self._done.wait(self._every):
            try:
                if not self._queue.renew_lease(self._job_id, self._ctx.worker_id):
                    _log.warning("job.lease_lost", job_id=str(self._job_id))
                    self._ctx.lease_lost.set()
                    return
            except Exception as exc:
                _log.warning("job.lease_renew_failed", job_id=str(self._job_id), error=str(exc))

    def finish(self) -> None:
        self._done.set()
        self.join(timeout=self._every + 5)


class JobLoop:
    def __init__(
        self,
        queue: JobQueue,
        registry: HandlerRegistry,
        *,
        worker_id: str,
        config: LoopConfig | None = None,
        stop_event: threading.Event | None = None,
    ) -> None:
        self.queue = queue
        self.registry = registry
        self.worker_id = worker_id
        self.config = config or LoopConfig()
        self.stop_event = stop_event or threading.Event()
        self.current_job_id: UUID | None = None
        self._last_sweep = 0.0

    def stop(self) -> None:
        self.stop_event.set()

    def sweep_if_due(self, *, force: bool = False) -> int:
        now = time.monotonic()
        if not force and now - self._last_sweep < self.config.sweep_interval_seconds:
            return 0
        self._last_sweep = now
        count = self.queue.requeue_expired()
        if count:
            _log.info("job.leases_requeued", count=count)
        return count

    def run_once(self) -> bool:
        """Sweep if due, then claim and process at most one job. Returns True if one ran."""
        self.sweep_if_due()
        job = self.queue.claim(self.worker_id)
        if job is None:
            return False
        self.process(job)
        return True

    def process(self, job: Job) -> None:
        ctx = JobContext(worker_id=self.worker_id)
        self.current_job_id = job.id
        bind_context(job_id=str(job.id), job_kind=job.kind)
        renewer = _LeaseRenewer(self.queue, job.id, ctx, self.config.lease_renew_seconds)
        renewer.start()
        started = time.monotonic()
        try:
            handler = self.registry.get(job.kind)
            handler(job, ctx)
        except UnknownJobKindError as exc:
            renewer.finish()
            _log.error("job.unknown_kind", error=str(exc))
            self.queue.fail(job.id, self.worker_id, str(exc), retry=False)
        except Exception as exc:
            renewer.finish()
            _log.warning("job.failed", attempt=job.attempts, error=format_error(exc))
            self.queue.fail(job.id, self.worker_id, format_error(exc))
        else:
            renewer.finish()
            if self.queue.complete(job.id, self.worker_id):
                _log.info(
                    "job.done",
                    attempt=job.attempts,
                    duration_ms=round((time.monotonic() - started) * 1000, 1),
                )
            else:
                _log.warning("job.complete_lost_lease")
        finally:
            self.current_job_id = None
            unbind_context("job_id", "job_kind")

    def run(self) -> None:
        _log.info("worker.loop.start", worker_id=self.worker_id, kinds=self.registry.kinds())
        while not self.stop_event.is_set():
            try:
                processed = self.run_once()
            except Exception as exc:  # DB outage etc.: keep the process alive
                _log.error("worker.loop.error", error=format_error(exc))
                processed = False
            if not processed:
                self.stop_event.wait(self.config.poll_interval_seconds)
        _log.info("worker.loop.stopped", worker_id=self.worker_id)
