"""Build metadata: resolve the git SHA baked into the image (or overridden)."""

from __future__ import annotations

import re
from pathlib import Path

UNKNOWN = "unknown"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def normalise_sha(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = value.strip().lower()
    return candidate if _SHA_RE.match(candidate) else None


def resolve_git_sha(override: str | None, sha_file: str | Path = "/app/GIT_SHA") -> str:
    """Return the 40-hex SHA from ``override`` (``GIT_SHA``), else the build file, else unknown."""
    sha = normalise_sha(override)
    if sha:
        return sha
    try:
        sha = normalise_sha(Path(sha_file).read_text(encoding="utf-8"))
    except OSError:
        sha = None
    return sha or UNKNOWN
