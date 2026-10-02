"""Resolve the stored ground-truth file of a generated collection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from chatledger_core.domain.generator.errors import GroundTruthNotFoundError
from chatledger_core.domain.generator.ports import GenerationRepository
from chatledger_core.domain.intake.errors import MatterNotFoundError
from chatledger_core.domain.intake.ports import BlobStore, UnitOfWorkFactory


@dataclass(frozen=True)
class GroundTruthFile:
    path: Path
    filename: str


class GetGroundTruth:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        generations: GenerationRepository,
        blob_store: BlobStore,
    ) -> None:
        self._uow_factory = uow_factory
        self._generations = generations
        self._blobs = blob_store

    def execute(self, matter_id: UUID, collection_id: UUID) -> GroundTruthFile:
        with self._uow_factory() as uow:
            if uow.matters.get(matter_id) is None:
                raise MatterNotFoundError
            collection = uow.collections.get(matter_id, collection_id)
        generation = self._generations.find_by_collection(collection_id)
        if (
            collection is None
            or generation is None
            or generation.matter_id != matter_id
            or generation.ground_truth_sha256 is None
        ):
            raise GroundTruthNotFoundError
        path = self._blobs.ground_truth_path_for(collection.sha256)
        if not path.is_file():
            raise GroundTruthNotFoundError
        return GroundTruthFile(path=path, filename=f"ground-truth-{generation.seed}.json")
