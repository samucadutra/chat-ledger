"""Audit event entity and append-only log port (consumed by F02 onwards)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class AuditEvent:
    id: int
    occurred_at: datetime
    action: str
    entity_type: str
    entity_id: str
    details: dict[str, Any] = field(default_factory=dict)


class AuditLog(Protocol):
    def record(
        self,
        action: str,
        entity_type: str,
        entity_id: str,
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Append one event and return it (with its ID and UTC timestamp)."""
        ...

    def list_for_entity(self, entity_type: str, entity_id: str) -> list[AuditEvent]:
        """Return every event for the entity, in ID order."""
        ...
