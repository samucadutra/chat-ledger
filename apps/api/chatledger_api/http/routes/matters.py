"""Matter and collection routes (``/api/v1/matters``)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from chatledger_api.http.upload import (
    check_content_length,
    check_media_type,
    parse_filename,
    stage_request_body,
)
from chatledger_core.domain.intake.collection import Collection
from chatledger_core.domain.intake.errors import (
    CollectionNotFoundError,
    MatterNotFoundError,
)
from chatledger_core.domain.intake.matter import MatterSummary
from chatledger_core.infra.blobstore.fs_blob_store import FsBlobStore
from chatledger_core.usecase.intake.create_matter import CreateMatter
from chatledger_core.usecase.intake.get_matter import GetMatter
from chatledger_core.usecase.intake.list_collections import GetCollection, ListCollections
from chatledger_core.usecase.intake.list_matters import ListMatters
from chatledger_core.usecase.intake.register_collection import RegisterCollection


@dataclass(frozen=True)
class IntakeServices:
    """Use cases and settings the intake routes depend on (built in the composition root)."""

    create_matter: CreateMatter
    list_matters: ListMatters
    get_matter: GetMatter
    list_collections: ListCollections
    get_collection: GetCollection
    register_collection: RegisterCollection
    blob_store: FsBlobStore
    max_upload_bytes: int
    upload_chunk_bytes: int


class CreateMatterRequest(BaseModel):
    name: str
    description: str | None = None


class MatterOut(BaseModel):
    id: UUID
    name: str
    description: str | None
    created_at: datetime
    collection_count: int
    total_size_bytes: int


class MatterListOut(BaseModel):
    items: list[MatterOut]


class CollectionOut(BaseModel):
    id: UUID
    matter_id: UUID
    sha256: str = Field(min_length=64, max_length=64)
    original_filename: str
    size_bytes: int
    source: str
    entry_count: int
    conversation_count: int
    export_date_from: date | None
    export_date_to: date | None
    root_prefix: str
    added_at: datetime


class CollectionListOut(BaseModel):
    items: list[CollectionOut]


def _matter_out(m: MatterSummary) -> MatterOut:
    return MatterOut(
        id=m.id,
        name=m.name,
        description=m.description,
        created_at=m.created_at,
        collection_count=m.collection_count,
        total_size_bytes=m.total_size_bytes,
    )


def _collection_out(c: Collection) -> CollectionOut:
    return CollectionOut(
        id=c.id,
        matter_id=c.matter_id,
        sha256=c.sha256,
        original_filename=c.original_filename,
        size_bytes=c.size_bytes,
        source=c.source.value,
        entry_count=c.entry_count,
        conversation_count=c.conversation_count,
        export_date_from=c.export_date_from,
        export_date_to=c.export_date_to,
        root_prefix=c.root_prefix,
        added_at=c.added_at,
    )


def _services(request: Request) -> IntakeServices:
    services: IntakeServices = request.app.state.intake
    return services


def _parse_id(raw: str, error: type[MatterNotFoundError] | type[CollectionNotFoundError]) -> UUID:
    try:
        return UUID(raw)
    except ValueError:
        raise error from None


router = APIRouter(prefix="/matters", tags=["matters"])


@router.post("", status_code=201, response_model=MatterOut, summary="Create matter")
def create_matter(body: CreateMatterRequest, request: Request) -> MatterOut:
    return _matter_out(_services(request).create_matter.execute(body.name, body.description))


@router.get("", response_model=MatterListOut, summary="List matters")
def list_matters(request: Request) -> MatterListOut:
    return MatterListOut(items=[_matter_out(m) for m in _services(request).list_matters.execute()])


@router.get("/{matter_id}", response_model=MatterOut, summary="Get matter")
def get_matter(matter_id: str, request: Request) -> MatterOut:
    return _matter_out(
        _services(request).get_matter.execute(_parse_id(matter_id, MatterNotFoundError))
    )


@router.get(
    "/{matter_id}/collections", response_model=CollectionListOut, summary="List collections"
)
def list_collections(matter_id: str, request: Request) -> CollectionListOut:
    items = _services(request).list_collections.execute(_parse_id(matter_id, MatterNotFoundError))
    return CollectionListOut(items=[_collection_out(c) for c in items])


@router.get(
    "/{matter_id}/collections/{collection_id}",
    response_model=CollectionOut,
    summary="Get collection",
)
def get_collection(matter_id: str, collection_id: str, request: Request) -> CollectionOut:
    services = _services(request)
    return _collection_out(
        services.get_collection.execute(
            _parse_id(matter_id, MatterNotFoundError),
            _parse_id(collection_id, CollectionNotFoundError),
        )
    )


@router.post(
    "/{matter_id}/collections",
    status_code=201,
    response_model=CollectionOut,
    summary="Upload collection",
    description=(
        "Raw streaming upload: the body is the ZIP file, `Content-Type: application/zip`, "
        "and the original file name is sent percent-encoded in `X-Filename`."
    ),
)
async def upload_collection(matter_id: str, request: Request) -> CollectionOut:
    services = _services(request)
    check_media_type(request.headers.get("content-type"))
    filename = parse_filename(request.headers.get("x-filename"))
    check_content_length(request.headers.get("content-length"), services.max_upload_bytes)
    matter_uuid = _parse_id(matter_id, MatterNotFoundError)
    await run_in_threadpool(services.get_matter.execute, matter_uuid)

    staged = await stage_request_body(
        request,
        services.blob_store.tmp_dir,
        services.max_upload_bytes,
        services.upload_chunk_bytes,
    )
    collection = await run_in_threadpool(
        services.register_collection.execute,
        matter_uuid,
        staged.path,
        filename,
        "upload",
        staged.sha256,
    )
    return _collection_out(collection)
