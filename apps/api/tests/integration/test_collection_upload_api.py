from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from chatledger_api.main import create_app
from chatledger_core.config import Settings
from factories import FIXTURES_DIR, make_matter, make_synthetic_collection


@pytest.fixture
def api(client: TestClient, clean_intake: Engine) -> TestClient:
    return client


@pytest.fixture
def acme(api: TestClient, clean_intake: Engine) -> str:
    return str(make_matter(clean_intake, "Acme v. Beta"))


def upload(
    api: TestClient,
    matter_id: str,
    fixture: str,
    *,
    filename: str | None = None,
    headers: dict[str, str] | None = None,
    content: bytes | Iterator[bytes] | None = None,
):  # type: ignore[no-untyped-def]
    data = (FIXTURES_DIR / fixture).read_bytes() if content is None else content
    all_headers = {"Content-Type": "application/zip", "X-Filename": quote(filename or fixture)}
    all_headers.update(headers or {})
    all_headers = {k: v for k, v in all_headers.items() if v != ""}
    return api.post(f"/api/v1/matters/{matter_id}/collections", content=data, headers=all_headers)


def tmp_files(blob_root: Path) -> list[Path]:
    tmp = blob_root / "tmp"
    return sorted(tmp.iterdir()) if tmp.exists() else []


def listing(api: TestClient, matter_id: str) -> list[dict]:  # type: ignore[type-arg]
    return api.get(f"/api/v1/matters/{matter_id}/collections").json()["items"]  # type: ignore[no-any-return]


def test_upload_minimal_export_201(api: TestClient, acme: str, blob_root: Path) -> None:
    res = upload(api, acme, "minimal-export.zip")
    assert res.status_code == 201, res.text
    body = res.json()
    raw = (FIXTURES_DIR / "minimal-export.zip").read_bytes()
    assert body["sha256"] == hashlib.sha256(raw).hexdigest()
    assert body["size_bytes"] == len(raw)
    assert body["source"] == "upload"
    assert body["original_filename"] == "minimal-export.zip"
    assert body["matter_id"] == acme
    assert (body["entry_count"], body["conversation_count"], body["root_prefix"]) == (8, 2, "")
    assert (body["export_date_from"], body["export_date_to"]) == ("2024-01-03", "2024-01-05")
    assert tmp_files(blob_root) == []
    stored = blob_root / "sha256" / body["sha256"][:2] / f"{body['sha256']}.zip"
    assert stored.read_bytes() == raw
    assert oct(stored.stat().st_mode & 0o777) == "0o444"
    assert api.get(f"/api/v1/matters/{acme}/collections/{body['id']}").json() == body
    assert api.get(f"/api/v1/matters/{acme}").json()["collection_count"] == 1
    assert api.get(f"/api/v1/matters/{acme}").json()["total_size_bytes"] == len(raw)


def test_upload_octet_stream_accepted(api: TestClient, acme: str) -> None:
    res = upload(
        api, acme, "minimal-export.zip", headers={"Content-Type": "application/octet-stream"}
    )
    assert res.status_code == 201


def test_upload_filename_percent_decoded(api: TestClient, acme: str) -> None:
    res = upload(api, acme, "minimal-export.zip", filename="ünï cödé 2024.ZIP")
    assert res.status_code == 201
    assert res.json()["original_filename"] == "ünï cödé 2024.ZIP"


def test_upload_metadata_50conv(api: TestClient, acme: str) -> None:
    body = upload(api, acme, "export-50conv-90d.zip").json()
    assert body["conversation_count"] == 50
    assert (body["export_date_from"], body["export_date_to"]) == ("2024-01-03", "2024-04-01")


def test_upload_nested_export(api: TestClient, acme: str) -> None:
    body = upload(api, acme, "nested-export.zip").json()
    assert body["root_prefix"] == "Acme Slack export Jan 2024/"
    assert body["conversation_count"] == 2


def test_upload_duplicate_409(api: TestClient, acme: str, blob_root: Path) -> None:
    first = upload(api, acme, "minimal-export.zip").json()
    res = upload(api, acme, "minimal-export.zip")
    assert res.status_code == 409
    error = res.json()["error"]
    assert error["code"] == "COLLECTION_DUPLICATE"
    assert error["details"]["existing_collection_id"] == first["id"]
    assert "minimal-export.zip" in error["message"]
    assert first["sha256"] in error["message"]
    assert len(listing(api, acme)) == 1
    assert tmp_files(blob_root) == []


def test_upload_same_zip_other_matter(api: TestClient, acme: str, clean_intake: Engine) -> None:
    beta = str(make_matter(clean_intake, "Beta Internal"))
    first = upload(api, acme, "minimal-export.zip").json()
    res = upload(api, beta, "minimal-export.zip")
    assert res.status_code == 201
    assert res.json()["sha256"] == first["sha256"]


def test_upload_collection_cap_409(api: TestClient, clean_intake: Engine) -> None:
    full = make_matter(clean_intake, "Full Matter")
    for i in range(1, 21):
        make_synthetic_collection(clean_intake, full, i)
    res = upload(api, str(full), "minimal-export.zip")
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "COLLECTION_LIMIT_REACHED"
    assert res.json()["error"]["message"] == "This matter already has 20 collections (limit 20)."
    assert len(listing(api, str(full))) == 20


def test_upload_content_length_over_limit_413(api: TestClient, acme: str, blob_root: Path) -> None:
    res = upload(
        api,
        acme,
        "minimal-export.zip",
        headers={"Content-Length": "2147483649"},
        content=b"tiny",
    )
    assert res.status_code == 413
    error = res.json()["error"]
    assert error["code"] == "FILE_TOO_LARGE"
    assert error["message"].startswith("File exceeds the 2 GB limit")
    assert error["details"]["limit_bytes"] == 2147483648
    assert listing(api, acme) == []
    assert tmp_files(blob_root) == []


def test_upload_stream_over_limit_413(
    engine: Engine,
    clean_intake: Engine,
    make_settings: Callable[..., Settings],
    blob_root: Path,
) -> None:
    app: FastAPI = create_app(
        make_settings(max_upload_bytes=1000, upload_chunk_bytes=64), engine=engine
    )
    client = TestClient(app, raise_server_exceptions=False)
    matter = str(make_matter(engine, "Acme v. Beta"))

    def chunks() -> Iterator[bytes]:
        for _ in range(20):
            yield b"x" * 100

    res = upload(client, matter, "minimal-export.zip", content=chunks())
    assert res.status_code == 413
    assert res.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert tmp_files(blob_root) == []
    assert listing(client, matter) == []


def test_upload_missing_filename_400(api: TestClient, acme: str) -> None:
    res = upload(api, acme, "minimal-export.zip", headers={"X-Filename": ""})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "MISSING_FILENAME"
    assert listing(api, acme) == []


@pytest.mark.parametrize(
    "name", ["notes.txt", "a/b.zip", "a\\b.zip", "x" * 256 + ".zip", "%ff.zip"]
)
def test_upload_non_zip_extension_422(api: TestClient, acme: str, name: str) -> None:
    res = upload(api, acme, "minimal-export.zip", headers={"X-Filename": name})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "INVALID_FILENAME"
    assert res.json()["error"]["message"] == "File must be a .zip archive."


def test_upload_wrong_media_type_415(api: TestClient, acme: str) -> None:
    res = upload(api, acme, "minimal-export.zip", headers={"Content-Type": "text/plain"})
    assert res.status_code == 415
    assert res.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_upload_not_slack_export_422(api: TestClient, acme: str, blob_root: Path) -> None:
    res = upload(api, acme, "missing-users.zip")
    assert res.status_code == 422
    error = res.json()["error"]
    assert error["code"] == "NOT_A_SLACK_EXPORT"
    assert (
        error["message"] == "Not a Slack workspace export: users.json and channels.json not found."
    )
    assert listing(api, acme) == []
    assert tmp_files(blob_root) == []


def test_upload_path_traversal_422(api: TestClient, acme: str) -> None:
    res = upload(api, acme, "path-traversal.zip")
    assert res.status_code == 422
    error = res.json()["error"]
    assert error["code"] == "ARCHIVE_REJECTED"
    assert error["details"]["rule"] == "path_escape"
    assert error["message"] == "Archive rejected: entry path escapes archive"


def test_upload_zip_bomb_422(api: TestClient, acme: str) -> None:
    res = upload(api, acme, "zip-bomb.zip")
    assert res.status_code == 422
    assert res.json()["error"]["details"]["rule"] == "compression_ratio"


def test_upload_not_a_zip_422(api: TestClient, acme: str) -> None:
    res = upload(api, acme, "not-a-zip.zip")
    assert res.status_code == 422
    assert res.json()["error"]["details"]["rule"] == "not_a_zip"


def test_upload_empty_body_422(api: TestClient, acme: str) -> None:
    res = upload(api, acme, "minimal-export.zip", content=b"")
    assert res.status_code == 422
    assert res.json()["error"]["details"]["rule"] == "not_a_zip"


@pytest.mark.parametrize("matter_id", ["00000000-0000-4000-8000-000000000000", "nope"])
def test_upload_unknown_matter_404(api: TestClient, blob_root: Path, matter_id: str) -> None:
    res = upload(api, matter_id, "minimal-export.zip")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "MATTER_NOT_FOUND"
    assert tmp_files(blob_root) == []


def test_upload_unknown_matter_uses_random_uuid(api: TestClient) -> None:
    assert upload(api, str(uuid4()), "minimal-export.zip").status_code == 404
