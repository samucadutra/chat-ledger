"""Free-space probe with an optional override (test knob)."""

from __future__ import annotations

import os
import shutil


class DiskProbe:
    def __init__(self, override_bytes: int | None = None) -> None:
        self._override = override_bytes

    def free_bytes(self, path: str) -> int:
        if self._override is not None:
            return self._override
        probe = path
        while not os.path.exists(probe):
            parent = os.path.dirname(probe)
            if parent == probe:
                break
            probe = parent
        return shutil.disk_usage(probe).free
