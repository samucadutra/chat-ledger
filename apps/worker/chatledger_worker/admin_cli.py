"""``chatledger-admin``: operator commands (``enqueue-noop``, ``job-status``)."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from typing import TextIO
from uuid import UUID

from chatledger_core.config import get_settings
from chatledger_core.domain._shared.errors import NotFoundError
from chatledger_core.domain.jobs.queue import JobQueue


def _bounded_int(lo: int, hi: int) -> Callable[[str], int]:
    def parse(raw: str) -> int:
        try:
            value = int(raw)
        except ValueError:
            raise argparse.ArgumentTypeError(f"invalid integer: {raw!r}") from None
        if not lo <= value <= hi:
            raise argparse.ArgumentTypeError(f"must be between {lo} and {hi}, got {value}")
        return value

    return parse


def _bounded_float(lo: float, hi: float) -> Callable[[str], float]:
    def parse(raw: str) -> float:
        try:
            value = float(raw)
        except ValueError:
            raise argparse.ArgumentTypeError(f"invalid number: {raw!r}") from None
        if not lo <= value <= hi:
            raise argparse.ArgumentTypeError(f"must be between {lo:g} and {hi:g}, got {value:g}")
        return value

    return parse


def _uuid(raw: str) -> UUID:
    try:
        return UUID(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid job id: {raw!r}") from None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chatledger-admin", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    enqueue = sub.add_parser("enqueue-noop", help="enqueue a noop job and print its UUID")
    enqueue.add_argument("--fail-times", type=_bounded_int(0, 1_000_000), default=0)
    enqueue.add_argument("--sleep-seconds", type=_bounded_float(0, 300), default=0.0)
    enqueue.add_argument("--priority", type=_bounded_int(0, 1000), default=100)

    status = sub.add_parser("job-status", help="print a job as JSON")
    status.add_argument("job_id", type=_uuid)
    return parser


def _default_queue() -> JobQueue:
    from chatledger_worker.main import build_queue

    return build_queue(get_settings())


def main(
    argv: Sequence[str] | None = None,
    *,
    queue_factory: Callable[[], JobQueue] = _default_queue,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    out = stdout or sys.stdout
    err = stderr or sys.stderr
    args = build_parser().parse_args(argv)  # exits 2 on invalid arguments
    queue = queue_factory()

    if args.command == "enqueue-noop":
        payload: dict[str, object] = {}
        if args.fail_times:
            payload["fail_times"] = args.fail_times
        if args.sleep_seconds:
            payload["sleep_seconds"] = args.sleep_seconds
        job = queue.enqueue("noop", payload, priority=args.priority)
        print(job.id, file=out)
        return 0

    try:
        job = queue.get(args.job_id)
    except NotFoundError:
        print(f"Job {args.job_id} not found", file=err)
        return 1
    print(json.dumps(job.to_public_dict()), file=out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
