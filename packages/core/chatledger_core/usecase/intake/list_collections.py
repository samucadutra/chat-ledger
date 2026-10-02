"""List and fetch collections of a matter."""

from __future__ import annotations

from uuid import UUID

from chatledger_core.domain.intake.collection import Collection
from chatledger_core.domain.intake.errors import CollectionNotFoundError, MatterNotFoundError
from chatledger_core.domain.intake.ports import UnitOfWorkFactory


class ListCollections:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, matter_id: UUID) -> list[Collection]:
        with self._uow_factory() as uow:
            if uow.matters.get(matter_id) is None:
                raise MatterNotFoundError
            return uow.collections.list_for_matter(matter_id)


class GetCollection:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, matter_id: UUID, collection_id: UUID) -> Collection:
        with self._uow_factory() as uow:
            if uow.matters.get(matter_id) is None:
                raise MatterNotFoundError
            collection = uow.collections.get(matter_id, collection_id)
        if collection is None:
            raise CollectionNotFoundError
        return collection
