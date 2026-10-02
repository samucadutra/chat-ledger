"""Collection entity: one Slack export ZIP registered into a matter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID


class CollectionSource(StrEnum):
    UPLOAD = "upload"
    GENERATOR = "generator"


@dataclass(frozen=True)
class NewCollection:
    """A collection about to be inserted (ID and ``added_at`` are assigned by the store)."""

    matter_id: UUID
    sha256: str
    original_filename: str
    size_bytes: int
    source: CollectionSource
    entry_count: int
    conversation_count: int
    export_date_from: date | None
    export_date_to: date | None
    root_prefix: str


@dataclass(frozen=True)
class Collection:
    id: UUID
    matter_id: UUID
    sha256: str
    original_filename: str
    size_bytes: int
    source: CollectionSource
    entry_count: int
    conversation_count: int
    export_date_from: date | None
    export_date_to: date | None
    root_prefix: str
    added_at: datetime


@dataclass(frozen=True)
class BlobRef:
    sha256: str
    size_bytes: int
    storage_path: str
