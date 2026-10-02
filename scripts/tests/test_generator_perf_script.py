from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "e2e" / "generator_perf.sh"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, check=False)


def test_help_exits_zero_and_documents_usage() -> None:
    result = run("--help")
    assert result.returncode == 0
    assert "--profile" in result.stdout


@pytest.mark.parametrize(
    "args", [["--bogus"], ["--profile", "stress"], ["--seed", "abc"], ["--seed", "-1"]]
)
def test_invalid_arguments_exit_two(args: list[str]) -> None:
    assert run(*args).returncode == 2


def test_script_is_executable() -> None:
    assert SCRIPT.stat().st_mode & 0o111
