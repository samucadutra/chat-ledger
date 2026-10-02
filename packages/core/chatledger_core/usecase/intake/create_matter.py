"""Create a matter."""

from __future__ import annotations

from chatledger_core.domain.intake.matter import MatterSummary, validate_matter_input
from chatledger_core.domain.intake.ports import UnitOfWorkFactory


class CreateMatter:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, name: str, description: str | None = None) -> MatterSummary:
        clean_name, clean_description = validate_matter_input(name, description)
        with self._uow_factory() as uow:
            matter = uow.matters.add(clean_name, clean_description)
            uow.audit.record(
                "matter.created",
                "matter",
                str(matter.id),
                {"name": matter.name, "description": matter.description},
            )
        return MatterSummary(
            id=matter.id,
            name=matter.name,
            description=matter.description,
            created_at=matter.created_at,
        )
