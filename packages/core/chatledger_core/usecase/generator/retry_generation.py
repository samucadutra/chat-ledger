"""Retry a failed generation with a fresh job (not for duplicates, which would fail again)."""

from __future__ import annotations

from uuid import UUID

from chatledger_core.domain.generator.errors import GenerationNotRetryableError
from chatledger_core.domain.generator.ports import GenerationRecord, GenerationRepository
from chatledger_core.domain.intake.ports import UnitOfWorkFactory
from chatledger_core.domain.jobs.queue import JobQueue
from chatledger_core.usecase.generator.get_generation import GetGeneration
from chatledger_core.usecase.generator.request_generation import GENERATE_KIND

DUPLICATE_CODE = "COLLECTION_DUPLICATE"


class RetryGeneration:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        generations: GenerationRepository,
        queue: JobQueue,
    ) -> None:
        self._generations = generations
        self._queue = queue
        self._get = GetGeneration(uow_factory, generations)

    def execute(self, matter_id: UUID, generation_id: UUID) -> GenerationRecord:
        record = self._get.execute(matter_id, generation_id)
        if record.state != "failed" or record.error_code == DUPLICATE_CODE:
            raise GenerationNotRetryableError
        job = self._queue.enqueue(GENERATE_KIND, {"generation_id": str(record.id)})
        return self._generations.reset_for_retry(record.id, job.id)
