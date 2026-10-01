from pathlib import Path

from chatledger_core.infra.git_sha import UNKNOWN, normalise_sha, resolve_git_sha

SHA = "0123456789abcdef0123456789abcdef01234567"


def test_override_wins(tmp_path: Path) -> None:
    f = tmp_path / "GIT_SHA"
    f.write_text("f" * 40)
    assert resolve_git_sha(SHA.upper(), f) == SHA


def test_reads_build_file(tmp_path: Path) -> None:
    f = tmp_path / "GIT_SHA"
    f.write_text(SHA + "\n")
    assert resolve_git_sha(None, f) == SHA


def test_invalid_override_falls_back_to_file(tmp_path: Path) -> None:
    f = tmp_path / "GIT_SHA"
    f.write_text(SHA)
    assert resolve_git_sha("not-a-sha", f) == SHA


def test_missing_file_is_unknown(tmp_path: Path) -> None:
    assert resolve_git_sha(None, tmp_path / "missing") == UNKNOWN


def test_file_with_unknown_is_unknown(tmp_path: Path) -> None:
    f = tmp_path / "GIT_SHA"
    f.write_text("unknown\n")
    assert resolve_git_sha("", f) == UNKNOWN


def test_normalise_sha() -> None:
    assert normalise_sha(None) is None
    assert normalise_sha(" " + SHA + " ") == SHA
    assert normalise_sha("123") is None
