"""Synthetic export generation routes and the ground-truth download."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from chatledger_core.domain.generator.errors import (
    GenerationNotFoundError,
    GroundTruthNotFoundError,
)
from chatledger_core.domain.generator.ports import GenerationRecord
from chatledger_core.domain.intake.errors import MatterNotFoundError
from chatledger_core.usecase.generator.get_generation import GetGeneration
from chatledger_core.usecase.generator.get_ground_truth import GetGroundTruth
from chatledger_core.usecase.generator.list_generations import ListGenerations
from chatledger_core.usecase.generator.request_generation import RequestGeneration
from chatledger_core.usecase.generator.retry_generation import RetryGeneration


@dataclass(frozen=True)
class GenerationServices:
    """Use cases the generation routes depend on (built in the composition root)."""

    request_generation: RequestGeneration
    list_generations: ListGenerations
    get_generation: GetGeneration
    retry_generation: RetryGeneration
    get_ground_truth: GetGroundTruth


class CreateGenerationRequest(BaseModel):
    """Raw input; every rule (and its message) lives in the domain validation."""

    seed: int | None = None
    preset: str | None = None
    messages: int | None = None
    conversations: int | None = None
    profile: str | None = None
    overlap_of_collection_id: UUID | None = None


class GenerationErrorOut(BaseModel):
    code: str
    message: str


class GenerationOut(BaseModel):
    id: UUID
    matter_id: UUID
    job_id: UUID | None
    state: str
    seed: int
    preset: str
    profile: str
    messages: int
    conversations: int
    overlap_of_collection_id: UUID | None
    progress_messages: int
    total_messages: int
    collection_id: UUID | None
    error: GenerationErrorOut | None
    created_at: datetime
    updated_at: datetime


class GenerationListOut(BaseModel):
    items: list[GenerationOut]


def _generation_out(g: GenerationRecord) -> GenerationOut:
    error = None
    if g.state == "failed":
        error = GenerationErrorOut(
            code=g.error_code or "GENERATION_FAILED",
            message=g.error_message or "Generation failed.",
        )
    return GenerationOut(
        id=g.id,
        matter_id=g.matter_id,
        job_id=g.job_id,
        state=g.state,
        seed=g.seed,
        preset=g.preset,
        profile=g.profile,
        messages=g.messages,
        conversations=g.conversations,
        overlap_of_collection_id=g.overlap_of_collection_id,
        progress_messages=g.progress_messages,
        total_messages=g.messages,
        collection_id=g.collection_id,
        error=error,
        created_at=g.created_at,
        updated_at=g.updated_at,
    )


def _services(request: Request) -> GenerationServices:
    services: GenerationServices = request.app.state.generations
    return services


def _matter_id(raw: str) -> UUID:
    try:
        return UUID(raw)
    except ValueError:
        raise MatterNotFoundError from None


def _generation_id(raw: str) -> UUID:
    try:
        return UUID(raw)
    except ValueError:
        raise GenerationNotFoundError from None


def _collection_id(raw: str) -> UUID:
    try:
        return UUID(raw)
    except ValueError:
        raise GroundTruthNotFoundError from None


router = APIRouter(prefix="/matters", tags=["generations"])


@router.post(
    "/{matter_id}/generations",
    status_code=202,
    response_model=GenerationOut,
    summary="Request a synthetic export",
)
def create_generation(
    matter_id: str, body: CreateGenerationRequest, request: Request
) -> GenerationOut:
    record = _services(request).request_generation.execute(
        _matter_id(matter_id),
        seed=body.seed,
        preset=body.preset,
        profile=body.profile,
        messages=body.messages,
        conversations=body.conversations,
        overlap_of_collection_id=body.overlap_of_collection_id,
    )
    return _generation_out(record)


@router.get(
    "/{matter_id}/generations", response_model=GenerationListOut, summary="List generations"
)
def list_generations(matter_id: str, request: Request) -> GenerationListOut:
    items = _services(request).list_generations.execute(_matter_id(matter_id))
    return GenerationListOut(items=[_generation_out(g) for g in items])


@router.get(
    "/{matter_id}/generations/{generation_id}",
    response_model=GenerationOut,
    summary="Get generation",
)
def get_generation(matter_id: str, generation_id: str, request: Request) -> GenerationOut:
    record = _services(request).get_generation.execute(
        _matter_id(matter_id), _generation_id(generation_id)
    )
    return _generation_out(record)


@router.post(
    "/{matter_id}/generations/{generation_id}/retry",
    status_code=202,
    response_model=GenerationOut,
    summary="Retry a failed generation",
)
def retry_generation(matter_id: str, generation_id: str, request: Request) -> GenerationOut:
    record = _services(request).retry_generation.execute(
        _matter_id(matter_id), _generation_id(generation_id)
    )
    return _generation_out(record)


@router.get(
    "/{matter_id}/collections/{collection_id}/ground-truth",
    summary="Download ground truth",
    response_class=FileResponse,
    responses={200: {"content": {"application/json": {}}, "description": "The ground-truth file"}},
)
def download_ground_truth(matter_id: str, collection_id: str, request: Request) -> FileResponse:
    found = _services(request).get_ground_truth.execute(
        _matter_id(matter_id), _collection_id(collection_id)
    )
    return FileResponse(
        found.path,
        media_type="application/json",
        filename=found.filename,
        content_disposition_type="attachment",
    )
