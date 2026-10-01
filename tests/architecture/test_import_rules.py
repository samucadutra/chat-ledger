"""The clean-architecture layering contracts (import-linter) hold for the tree."""

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_import_linter_contracts_kept() -> None:
    exe = shutil.which("lint-imports")
    assert exe is not None, "import-linter is not installed in the environment"
    result = subprocess.run([exe], cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 broken" in result.stdout
