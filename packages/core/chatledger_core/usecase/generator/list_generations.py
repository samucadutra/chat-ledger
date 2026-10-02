"""Read-side generation use cases: list and get."""

from __future__ import annotations

from uuid import UUID

from chatledger_core.domain.generator.ports import GenerationRecord, GenerationRepository
from chatledger_core.domain.intake.errors import MatterNotFoundError
from chatledger_core.domain.intake.ports import UnitOfWorkFactory


class ListGenerations:
    def __init__(self, uow_factory: UnitOfWorkFactory, generations: GenerationRepository) -> None:
        self._uow_factory = uow_factory
        self._generations = generations

    def execute(self, matter_id: UUID) -> list[GenerationRecord]:
        with self._uow_factory() as uow:
            if uow.matters.get(matter_id) is None:
                raise MatterNotFoundError
        return self._generations.list_for_matter(matter_id)
