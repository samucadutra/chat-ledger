"""List matters, newest first."""

from __future__ import annotations

from chatledger_core.domain.intake.matter import MatterSummary
from chatledger_core.domain.intake.ports import UnitOfWorkFactory


class ListMatters:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self) -> list[MatterSummary]:
        with self._uow_factory() as uow:
            return uow.matters.list_summaries()
