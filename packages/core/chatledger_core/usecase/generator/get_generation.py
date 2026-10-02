from __future__ import annotations

from uuid import UUID

from chatledger_core.domain.generator.errors import GenerationNotFoundError
from chatledger_core.domain.generator.ports import GenerationRecord, GenerationRepository
from chatledger_core.domain.intake.errors import MatterNotFoundError
from chatledger_core.domain.intake.ports import UnitOfWorkFactory


class GetGeneration:
    def __init__(self, uow_factory: UnitOfWorkFactory, generations: GenerationRepository) -> None:
        self._uow_factory = uow_factory
        self._generations = generations

    def execute(self, matter_id: UUID, generation_id: UUID) -> GenerationRecord:
        with self._uow_factory() as uow:
            if uow.matters.get(matter_id) is None:
                raise MatterNotFoundError
        record = self._generations.get(generation_id)
        if record is None or record.matter_id != matter_id:
            raise GenerationNotFoundError
        return record
