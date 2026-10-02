"""``chatledger-gen``: write a deterministic synthetic Slack export and its ground truth.

Exit codes: 0 success, 2 invalid arguments, 3 insufficient disk space, 4 I/O error.
Progress lines go to stderr every 10,000 messages; stdout ends with the ZIP and ground-truth
paths and SHA-256 digests.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TextIO

from chatledger_core.config import Settings, get_settings
from chatledger_core.domain.generator.errors import (
    GenerationParamsInvalidError,
    InsufficientDiskSpaceError,
)
from chatledger_core.domain.generator.overlap import (
    DAYS_PCT_MAX,
    DAYS_PCT_MIN,
    DEFAULT_DAYS_PCT,
)
from chatledger_core.domain.generator.params import (
    GenerationParams,
    Preset,
    Profile,
    validate_params,
)
from chatledger_core.infra.generator.disk import DiskProbe
from chatledger_core.infra.generator.ground_truth_writer import GroundTruthWriter
from chatledger_core.infra.generator.zip_export_writer import ZipExportWriter
from chatledger_core.usecase.generator.generate_export import GenerateExport, OverlapSpec

PROGRESS_EVERY = 10_000
EXIT_OK = 0
EXIT_INVALID = 2
EXIT_DISK = 3
EXIT_IO = 4


def _days_pct(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid integer: {raw!r}") from None
    if not DAYS_PCT_MIN <= value <= DAYS_PCT_MAX:
        raise argparse.ArgumentTypeError(
            f"must be an integer between {DAYS_PCT_MIN} and {DAYS_PCT_MAX}, got {value}"
        )
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chatledger-gen", description=__doc__)
    parser.add_argument("--seed", type=int, required=True, help="PRNG seed (0 to 2147483647)")
    parser.add_argument("--preset", choices=[p.value for p in Preset], required=True)
    parser.add_argument("--messages", type=int, help="message records (custom preset only)")
    parser.add_argument("--conversations", type=int, help="conversations (custom preset only)")
    parser.add_argument("--profile", choices=[p.value for p in Profile], default="default")
    parser.add_argument("--overlap-of", type=int, metavar="SEED", help="seed of the base export")
    parser.add_argument(
        "--overlap-days-pct",
        type=_days_pct,
        default=None,
        help=f"share of the base period to overlap (default {DEFAULT_DAYS_PCT})",
    )
    parser.add_argument("--out", type=Path, required=True, help="output directory")
    return parser


def _resolve_params(parser: argparse.ArgumentParser, args: argparse.Namespace) -> GenerationParams:
    if args.preset == Preset.CUSTOM.value:
        if args.messages is None:
            parser.error("--messages is required with --preset custom")
        if args.conversations is None:
            parser.error("--conversations is required with --preset custom")
    else:
        if args.messages is not None:
            parser.error("--messages is only valid with --preset custom")
        if args.conversations is not None:
            parser.error("--conversations is only valid with --preset custom")
    if args.overlap_days_pct is not None and args.overlap_of is None:
        parser.error("--overlap-days-pct requires --overlap-of")
    try:
        params = validate_params(
            seed=args.seed,
            preset=args.preset,
            profile=args.profile,
            messages=args.messages,
            conversations=args.conversations,
        )
        if args.overlap_of is not None:
            validate_params(
                seed=args.overlap_of,
                preset=args.preset,
                profile=args.profile,
                messages=args.messages,
                conversations=args.conversations,
            )
    except GenerationParamsInvalidError as exc:
        parser.error(exc.message)
    return params


def main(
    argv: Sequence[str] | None = None,
    *,
    settings_factory: Callable[[], Settings] = get_settings,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    out = stdout or sys.stdout
    err = stderr or sys.stderr
    parser = build_parser()
    args = parser.parse_args(argv)  # exits 2 on invalid arguments
    params = _resolve_params(parser, args)
    settings = settings_factory()

    out_dir: Path = args.out.resolve()
    zip_final = out_dir / params.filename
    truth_final = out_dir / params.ground_truth_filename
    zip_part = out_dir / f".{params.filename}.part"
    truth_part = out_dir / f".{params.ground_truth_filename}.part"
    overlap = (
        None
        if args.overlap_of is None
        else OverlapSpec(args.overlap_of, args.overlap_days_pct or DEFAULT_DAYS_PCT)
    )
    usecase = GenerateExport(
        DiskProbe(settings.generator_free_space_override_bytes),
        bytes_per_message=settings.generator_bytes_per_message,
        headroom=settings.generator_disk_headroom,
    )

    next_mark = PROGRESS_EVERY

    def on_progress(done: int) -> None:
        nonlocal next_mark
        while done >= next_mark and next_mark < params.messages:
            print(f"generated {next_mark} / {params.messages} messages", file=err, flush=True)
            next_mark += PROGRESS_EVERY

    zip_sink = ZipExportWriter(zip_part)
    try:
        usecase.check_disk(params.messages, str(out_dir))
        out_dir.mkdir(parents=True, exist_ok=True)
        result = usecase.execute(
            params,
            zip_sink=zip_sink,
            ground_truth_sink=GroundTruthWriter(truth_part),
            disk_path=str(out_dir),
            overlap=overlap,
            on_progress=on_progress,
        )
        os.replace(zip_part, zip_final)
        os.replace(truth_part, truth_final)
    except InsufficientDiskSpaceError as exc:
        _cleanup(zip_part, truth_part)
        print(exc.message, file=err)
        return EXIT_DISK
    except OSError as exc:
        _cleanup(zip_part, truth_part)
        print(f"I/O error: {exc}", file=err)
        return EXIT_IO
    except BaseException:
        _cleanup(zip_part, truth_part)
        raise
    print(f"ZIP {zip_final} sha256:{result.zip_sha256}", file=out)
    print(f"GROUND_TRUTH {truth_final} sha256:{result.ground_truth_sha256}", file=out)
    return EXIT_OK


def _cleanup(*paths: Path) -> None:
    for path in paths:
        with contextlib.suppress(OSError):
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
