"""``generate`` job handler: payload ``{"generation_id": "<uuid>"}``.

All work happens in :class:`RunGeneration`; permanent failures (disk space, duplicate, limits)
are recorded on the generation row and the job completes. Crashes and unexpected exceptions
propagate so the queue's lease and retry rules apply (3 attempts).
"""

from __future__ import annotations

from uuid import UUID

from chatledger_core.domain.jobs.job import Job
from chatledger_core.usecase.generator.run_generation import RunGeneration
from chatledger_worker.registry import Handler, JobContext

KIND = "generate"


def make_generate_handler(run_generation: RunGeneration) -> Handler:
    def handle_generate(job: Job, ctx: JobContext) -> None:
        run_generation.execute(UUID(str(job.payload["generation_id"])), ctx.lease_lost.is_set)

    return handle_generate
