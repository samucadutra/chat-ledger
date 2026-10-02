"""Fetch one matter."""

from __future__ import annotations

from uuid import UUID

from chatledger_core.domain.intake.errors import MatterNotFoundError
from chatledger_core.domain.intake.matter import MatterSummary
from chatledger_core.domain.intake.ports import UnitOfWorkFactory


class GetMatter:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, matter_id: UUID) -> MatterSummary:
        with self._uow_factory() as uow:
            matter = uow.matters.get(matter_id)
        if matter is None:
            raise MatterNotFoundError
        return matter
