"""Matter entity and input validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from chatledger_core.domain.intake.errors import (
    MatterDescriptionInvalidError,
    MatterNameInvalidError,
)

NAME_MIN_LENGTH = 3
NAME_MAX_LENGTH = 80
DESCRIPTION_MAX_LENGTH = 500


@dataclass(frozen=True)
class Matter:
    id: UUID
    name: str
    description: str | None
    created_at: datetime


@dataclass(frozen=True)
class MatterSummary(Matter):
    collection_count: int = 0
    total_size_bytes: int = 0


def validate_matter_input(name: str, description: str | None) -> tuple[str, str | None]:
    """Trim and validate; an empty description becomes ``None`` (spec A1)."""
    clean_name = name.strip()
    if not NAME_MIN_LENGTH <= len(clean_name) <= NAME_MAX_LENGTH:
        raise MatterNameInvalidError
    clean_description: str | None = None
    if description is not None:
        trimmed = description.strip()
        if len(trimmed) > DESCRIPTION_MAX_LENGTH:
            raise MatterDescriptionInvalidError
        clean_description = trimmed or None
    return clean_name, clean_description
