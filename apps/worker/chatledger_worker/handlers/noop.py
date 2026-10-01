"""Built-in ``noop`` handler used for smoke tests and queue verification.

Payload: ``{"fail_times": int = 0, "sleep_seconds": float = 0}``. The handler
raises :class:`NoopFailure` while ``attempts <= fail_times``, otherwise sleeps
``sleep_seconds`` (aborting early if the lease is lost) and succeeds.
"""

from __future__ import annotations

from chatledger_core.domain.jobs.job import Job
from chatledger_worker.registry import JobContext

KIND = "noop"


class NoopFailure(RuntimeError):  # noqa: N818 — name is part of the contract (last_error)
    pass


class LeaseLostError(RuntimeError):
    pass


def handle_noop(job: Job, ctx: JobContext) -> None:
    fail_times = int(job.payload.get("fail_times", 0) or 0)
    sleep_seconds = float(job.payload.get("sleep_seconds", 0) or 0)
    if job.attempts <= fail_times:
        raise NoopFailure(f"noop failing on purpose (attempt {job.attempts} of {fail_times})")
    if sleep_seconds > 0 and ctx.lease_lost.wait(sleep_seconds):
        raise LeaseLostError("lease lost while sleeping")
