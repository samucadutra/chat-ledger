from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from starlette.requests import ClientDisconnect

from chatledger_api.http.upload import (
    check_content_length,
    check_media_type,
    parse_filename,
    stage_request_body,
)
from chatledger_core.domain._shared.errors import DomainError
from chatledger_core.domain.intake.errors import FileTooLargeError, InvalidFilenameError


def test_parse_filename_decodes_percent_encoding() -> None:
    assert parse_filename("caf%C3%A9%20export.zip") == "café export.zip"
    assert parse_filename("Plain.ZIP") == "Plain.ZIP"


def test_parse_filename_missing() -> None:
    for value in (None, "", "   "):
        with pytest.raises(DomainError) as info:
            parse_filename(value)
        assert info.value.code == "MISSING_FILENAME"
        assert info.value.http_status == 400
        assert info.value.message == "X-Filename header is required."


@pytest.mark.parametrize(
    "value", ["notes.txt", "a%2Fb.zip", "a%5Cb.zip", "a%00b.zip", "x" * 252 + ".zip", "%ff%fe.zip"]
)
def test_parse_filename_invalid(value: str) -> None:
    with pytest.raises(InvalidFilenameError):
        parse_filename(value)


def test_parse_filename_length_boundary() -> None:
    assert len(parse_filename("x" * 251 + ".zip")) == 255


def test_media_types() -> None:
    check_media_type("application/zip")
    check_media_type("Application/Octet-Stream; charset=binary")
    for bad in (None, "", "text/plain", "multipart/form-data; boundary=x"):
        with pytest.raises(DomainError) as info:
            check_media_type(bad)
        assert info.value.code == "UNSUPPORTED_MEDIA_TYPE"
        assert info.value.http_status == 415


def test_content_length_precheck() -> None:
    check_content_length(None, 100)
    check_content_length("100", 100)
    check_content_length("not-a-number", 100)
    with pytest.raises(FileTooLargeError) as info:
        check_content_length("101", 100)
    assert info.value.details == {"limit_bytes": 100, "size_bytes": 101}
    assert info.value.message.startswith("File exceeds the 2 GB limit")


class FakeRequest:
    def __init__(self, parts: list[bytes], error: BaseException | None = None) -> None:
        self._parts = parts
        self._error = error

    async def stream(self) -> AsyncIterator[bytes]:
        for part in self._parts:
            yield part
        if self._error is not None:
            raise self._error


def stage(request: FakeRequest, tmp: Path, max_bytes: int = 1000) -> Any:
    return asyncio.run(stage_request_body(request, tmp, max_bytes, 4))  # type: ignore[arg-type]


def test_stage_request_body_hashes(tmp_path: Path) -> None:
    import hashlib

    staged = stage(FakeRequest([b"abc", b"defg", b"h"]), tmp_path)
    assert staged.size == 8
    assert staged.sha256 == hashlib.sha256(b"abcdefgh").hexdigest()
    assert staged.path.read_bytes() == b"abcdefgh"


def test_client_disconnect_discards_temp(tmp_path: Path) -> None:
    with pytest.raises(ClientDisconnect):
        stage(FakeRequest([b"abcdefgh", b"ij"], ClientDisconnect()), tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_oversize_stream_discards_and_reports_413(tmp_path: Path) -> None:
    with pytest.raises(FileTooLargeError):
        stage(FakeRequest([b"x" * 600, b"x" * 600]), tmp_path)
    assert list(tmp_path.iterdir()) == []
