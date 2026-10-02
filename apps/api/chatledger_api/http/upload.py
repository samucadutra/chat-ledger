"""Upload helpers: header parsing and the streaming staging loop."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import unquote

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request

from chatledger_core.domain._shared.errors import DomainError
from chatledger_core.domain.intake.errors import FileTooLargeError, InvalidFilenameError
from chatledger_core.infra.blobstore.staging import StagedFile, StagingWriter

ACCEPTED_MEDIA_TYPES = ("application/zip", "application/octet-stream")
MAX_FILENAME_LENGTH = 255


class MissingFilenameError(DomainError):
    default_code = "MISSING_FILENAME"
    http_status = 400

    def __init__(self) -> None:
        super().__init__("X-Filename header is required.")


class UnsupportedMediaTypeError(DomainError):
    default_code = "UNSUPPORTED_MEDIA_TYPE"
    http_status = 415

    def __init__(self) -> None:
        super().__init__("Upload must be sent as application/zip.")


def check_media_type(content_type: str | None) -> None:
    media = (content_type or "").split(";", 1)[0].strip().lower()
    if media not in ACCEPTED_MEDIA_TYPES:
        raise UnsupportedMediaTypeError


def parse_filename(header: str | None) -> str:
    """Decode the RFC 5987 percent-encoded ``X-Filename`` and validate it (spec A2)."""
    if header is None or not header.strip():
        raise MissingFilenameError
    try:
        name = unquote(header.strip(), encoding="utf-8", errors="strict")
    except UnicodeDecodeError:
        raise InvalidFilenameError from None
    if (
        len(name) > MAX_FILENAME_LENGTH
        or not name.lower().endswith(".zip")
        or any(ch in name for ch in ("/", "\\", "\x00"))
    ):
        raise InvalidFilenameError
    return name


def check_content_length(header: str | None, max_bytes: int) -> None:
    """Reject an oversized declared length before any body byte is read."""
    if header is None:
        return
    try:
        declared = int(header)
    except ValueError:
        return
    if declared > max_bytes:
        raise FileTooLargeError(max_bytes, declared)


async def _coalesce(stream: AsyncIterator[bytes], chunk_bytes: int) -> AsyncIterator[bytes]:
    buffer = bytearray()
    async for part in stream:
        buffer += part
        if len(buffer) >= chunk_bytes:
            yield bytes(buffer)
            buffer.clear()
    if buffer:
        yield bytes(buffer)


async def stage_request_body(
    request: Request, tmp_dir: Path, max_bytes: int, chunk_bytes: int
) -> StagedFile:
    """Stream the request body to a staged ``.part`` file, hashing as it goes.

    Any failure (client disconnect, oversize stream, cancellation) deletes the file.
    """
    writer = StagingWriter(tmp_dir, max_bytes, chunk_bytes)
    try:
        async for chunk in _coalesce(request.stream(), chunk_bytes):
            await run_in_threadpool(writer.write, chunk)
        return await run_in_threadpool(writer.finish)
    except FileTooLargeError as exc:
        writer.discard()
        raise FileTooLargeError(max_bytes, max_bytes + 1) from exc
    except BaseException:  # includes ClientDisconnect and task cancellation
        writer.discard()
        raise
