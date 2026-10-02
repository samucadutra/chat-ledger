from __future__ import annotations

import hashlib
import io
import re
from pathlib import Path

import pytest

from chatledger_core.config import Settings
from chatledger_worker.gen_cli import main


def settings(**overrides: object) -> Settings:
    return Settings(**overrides)  # type: ignore[arg-type]


def run(tmp_path: Path, *args: str, cfg: Settings | None = None) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(
        [*args],
        settings_factory=lambda: cfg or settings(),
        stdout=out,
        stderr=err,
    )
    return code, out.getvalue(), err.getvalue()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_small_run_writes_both_files_and_reports(tmp_path: Path) -> None:
    out = tmp_path / "out" / "nested"
    code, stdout, _ = run(
        tmp_path, "--seed", "42", "--preset", "small", "--profile", "default", "--out", str(out)
    )
    assert code == 0
    assert sorted(p.name for p in out.iterdir()) == [
        "ground-truth-42.json",
        "slack-export-42-small-default.zip",
    ]
    lines = stdout.strip().splitlines()
    zip_line = re.fullmatch(r"ZIP (\S+) sha256:([0-9a-f]{64})", lines[-2])
    truth_line = re.fullmatch(r"GROUND_TRUTH (\S+) sha256:([0-9a-f]{64})", lines[-1])
    assert zip_line is not None
    assert truth_line is not None
    assert zip_line.group(2) == sha(out / "slack-export-42-small-default.zip")
    assert truth_line.group(2) == sha(out / "ground-truth-42.json")


def test_same_seed_twice_and_other_seed(tmp_path: Path) -> None:
    for name, seed in (("a", "42"), ("b", "42"), ("c", "43")):
        code, _, _ = run(
            tmp_path,
            "--seed",
            seed,
            "--preset",
            "small",
            "--profile",
            "default",
            "--out",
            str(tmp_path / name),
        )
        assert code == 0
    zip_a = sha(tmp_path / "a" / "slack-export-42-small-default.zip")
    assert zip_a == sha(tmp_path / "b" / "slack-export-42-small-default.zip")
    assert zip_a != sha(tmp_path / "c" / "slack-export-43-small-default.zip")


def test_progress_lines_every_10000_messages(tmp_path: Path) -> None:
    code, _, stderr = run(
        tmp_path,
        "--seed",
        "5",
        "--preset",
        "custom",
        "--messages",
        "25000",
        "--conversations",
        "40",
        "--profile",
        "clean",
        "--out",
        str(tmp_path / "o"),
    )
    assert code == 0
    progress = [line for line in stderr.splitlines() if line.startswith("generated ")]
    assert progress == ["generated 10000 / 25000 messages", "generated 20000 / 25000 messages"]


@pytest.mark.parametrize(
    ("args", "needle"),
    [
        (["--preset", "custom"], "--messages is required"),
        (["--preset", "custom", "--messages", "2000"], "--conversations is required"),
        (
            ["--preset", "small", "--messages", "5000"],
            "--messages is only valid with --preset custom",
        ),
        (["--preset", "small", "--conversations", "5"], "--conversations is only valid"),
        (
            ["--preset", "custom", "--messages", "2000000", "--conversations", "50"],
            "Messages must be between 1,000 and 1,000,000",
        ),
        (
            ["--preset", "custom", "--messages", "2000", "--conversations", "1001"],
            "Conversations must not exceed messages / 2",
        ),
        (["--preset", "huge"], "invalid choice"),
        (["--preset", "small", "--overlap-days-pct", "30"], "requires --overlap-of"),
        (
            ["--preset", "small", "--overlap-of", "42", "--overlap-days-pct", "0"],
            "between 1 and 100",
        ),
        (["--preset", "small", "--overlap-of", "-5"], "Seed must be an integer"),
    ],
)
def test_invalid_arguments_exit_2_and_write_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], args: list[str], needle: str
) -> None:
    out = tmp_path / "out"
    with pytest.raises(SystemExit) as exc:
        main(["--seed", "7", *args, "--profile", "clean", "--out", str(out)])
    assert exc.value.code == 2
    assert needle in capsys.readouterr().err
    assert not out.exists()


def test_negative_seed_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--seed", "-1", "--preset", "small", "--out", str(tmp_path / "o")])
    assert exc.value.code == 2
    assert "Seed must be an integer between 0 and 2,147,483,647" in capsys.readouterr().err


def test_insufficient_disk_space_exit_3(tmp_path: Path) -> None:
    out = tmp_path / "o"
    code, stdout, stderr = run(
        tmp_path,
        "--seed",
        "42",
        "--preset",
        "small",
        "--out",
        str(out),
        cfg=settings(generator_free_space_override_bytes=1_000_000),
    )
    assert code == 3
    assert stdout == ""
    assert re.fullmatch(r"Not enough disk space: need ~\d+\.\d GB, \d+\.\d GB free\.\n", stderr)
    assert not out.exists() or not list(out.iterdir())


def test_io_error_exit_4(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x")
    code, _, stderr = run(
        tmp_path, "--seed", "42", "--preset", "small", "--out", str(blocker / "out")
    )
    assert code == 4
    assert stderr.startswith("I/O error")


def test_overlap_run_records_relation(tmp_path: Path) -> None:
    code, _, _ = run(
        tmp_path,
        "--seed",
        "43",
        "--preset",
        "small",
        "--profile",
        "default",
        "--overlap-of",
        "42",
        "--overlap-days-pct",
        "50",
        "--out",
        str(tmp_path / "o"),
    )
    assert code == 0
    import json

    truth = json.loads((tmp_path / "o" / "ground-truth-43.json").read_text())
    assert truth["overlap"] == {"base_seed": 42, "days_pct": 50}
