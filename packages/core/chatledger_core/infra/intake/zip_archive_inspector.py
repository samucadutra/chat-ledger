"""ZIP adapter: reads the central directory only, never decompresses an entry."""

from __future__ import annotations

import zipfile
from pathlib import Path

from chatledger_core.domain.intake.archive import ArchiveEntry, ArchiveRule, rejected


class ZipArchiveInspector:
    def read_entries(self, path: Path) -> list[ArchiveEntry]:
        try:
            with zipfile.ZipFile(path) as archive:
                return [
                    ArchiveEntry(
                        name=info.filename,
                        file_size=info.file_size,
                        compress_size=info.compress_size,
                        is_dir=info.is_dir(),
                    )
                    for info in archive.infolist()
                ]
        except (zipfile.BadZipFile, zipfile.LargeZipFile, EOFError, OSError, ValueError) as exc:
            raise rejected(ArchiveRule.NOT_A_ZIP) from exc
