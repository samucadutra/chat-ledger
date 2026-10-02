from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from factories import make_generation_services, make_matter, make_synthetic_collection


@pytest.fixture
def api(client: TestClient, clean_intake: Engine, clean_jobs: Engine) -> TestClient:
    return client


def post(api: TestClient, matter: object, **body: object):  # type: ignore[no-untyped-def]
    return api.post(f"/api/v1/matters/{matter}/generations", json=body)


def run_job(app: FastAPI, engine: Engine, blob_root: Path, generation_id: str) -> None:
    from uuid import UUID

    run, _, _, _ = make_generation_services(engine, blob_root)
    run.execute(UUID(generation_id), lambda: False)


def test_create_list_get(api: TestClient, clean_intake: Engine) -> None:
    matter = make_matter(clean_intake)
    res = post(api, matter, seed=42, preset="small", profile="default")
    assert res.status_code == 202
    body = res.json()
    assert body["state"] in ("queued", "running")
    assert (body["messages"], body["conversations"], body["total_messages"]) == (10_000, 50, 10_000)
    assert body["job_id"] and body["error"] is None and body["collection_id"] is None
    listed = api.get(f"/api/v1/matters/{matter}/generations").json()["items"]
    assert [g["id"] for g in listed] == [body["id"]]
    one = api.get(f"/api/v1/matters/{matter}/generations/{body['id']}")
    assert one.status_code == 200
    assert one.json()["id"] == body["id"]


@pytest.mark.parametrize(
    ("payload", "message", "field"),
    [
        (
            {
                "seed": 1,
                "preset": "custom",
                "messages": 2_000_000,
                "conversations": 50,
                "profile": "default",
            },
            "Messages must be between 1,000 and 1,000,000",
            "messages",
        ),
        (
            {
                "seed": 1,
                "preset": "custom",
                "messages": 2000,
                "conversations": 1001,
                "profile": "default",
            },
            "Conversations must not exceed messages / 2",
            "conversations",
        ),
        ({"seed": -1, "preset": "huge", "profile": "default"}, None, "seed"),
        ({"seed": 1, "preset": "small", "messages": 5000, "profile": "default"}, None, "messages"),
        ({}, None, "seed"),
    ],
)
def test_invalid_parameters(
    api: TestClient,
    clean_intake: Engine,
    payload: dict,
    message: str | None,
    field: str,  # type: ignore[type-arg]
) -> None:
    matter = make_matter(clean_intake)
    res = post(api, matter, **payload)
    assert res.status_code == 422
    error = res.json()["error"]
    assert error["code"] == "GENERATION_PARAMS_INVALID"
    assert error["details"]["field"] == field
    if message:
        assert error["message"] == message
    assert api.get(f"/api/v1/matters/{matter}/generations").json() == {"items": []}


def test_unknown_matter_and_ids(api: TestClient, clean_intake: Engine) -> None:
    res = post(api, uuid4(), seed=1, preset="small", profile="clean")
    assert (res.status_code, res.json()["error"]["code"]) == (404, "MATTER_NOT_FOUND")
    assert post(api, "not-a-uuid", seed=1, preset="small", profile="clean").status_code == 404
    matter = make_matter(clean_intake)
    res = api.get(f"/api/v1/matters/{matter}/generations/{uuid4()}")
    assert res.json()["error"]["code"] == "GENERATION_NOT_FOUND"
    assert api.get(f"/api/v1/matters/{matter}/generations/zzz").status_code == 404
    assert api.get(f"/api/v1/matters/{matter}/collections/zzz/ground-truth").status_code == 404


def test_flow_with_ground_truth_payload_and_redelivery(
    api: TestClient, app: FastAPI, clean_intake: Engine, blob_root: Path
) -> None:
    acme = make_matter(clean_intake)
    beta = make_matter(clean_intake, "Beta Internal")
    created = post(api, acme, seed=42, preset="small", profile="default").json()
    run_job(app, clean_intake, blob_root, created["id"])
    done = api.get(f"/api/v1/matters/{acme}/generations/{created['id']}").json()
    assert done["state"] == "done"
    assert done["progress_messages"] == done["total_messages"] == 10_000
    collection_id = done["collection_id"]

    # not retryable, foreign matter
    retry = api.post(f"/api/v1/matters/{acme}/generations/{created['id']}/retry")
    assert (retry.status_code, retry.json()["error"]["code"]) == (409, "GENERATION_NOT_RETRYABLE")
    foreign = api.get(f"/api/v1/matters/{beta}/generations/{created['id']}")
    assert foreign.json()["error"]["code"] == "GENERATION_NOT_FOUND"

    # collection payload
    make_synthetic_collection(clean_intake, acme, 99)
    items = api.get(f"/api/v1/matters/{acme}/collections").json()["items"]
    synthetic = next(i for i in items if i["id"] == collection_id)
    assert synthetic["source"] == "generator"
    assert synthetic["generation"] == {
        "id": created["id"],
        "seed": 42,
        "preset": "small",
        "profile": "default",
        "has_ground_truth": True,
    }
    uploaded = next(i for i in items if i["id"] != collection_id)
    assert uploaded["generation"] is None
    one = api.get(f"/api/v1/matters/{acme}/collections/{collection_id}").json()
    assert one["generation"]["seed"] == 42

    # download
    res = api.get(f"/api/v1/matters/{acme}/collections/{collection_id}/ground-truth")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/json")
    assert res.headers["content-disposition"] == 'attachment; filename="ground-truth-42.json"'
    assert hashlib.sha256(res.content).hexdigest() == (
        "b76aa55410c3f349a0ec6fbfbc7cf1699e6294b6c9a6d495b1be8b3559141e1d"
    )
    for target in (uploaded["id"], str(uuid4())):
        miss = api.get(f"/api/v1/matters/{acme}/collections/{target}/ground-truth")
        assert (miss.status_code, miss.json()["error"]["code"]) == (404, "GROUND_TRUTH_NOT_FOUND")

    # re-delivery base rules
    bad = post(
        api, beta, seed=3, preset="small", profile="default", overlap_of_collection_id=collection_id
    )
    assert bad.json()["error"]["code"] == "GENERATION_OVERLAP_BASE_INVALID"
    bad = post(
        api,
        acme,
        seed=3,
        preset="small",
        profile="default",
        overlap_of_collection_id=uploaded["id"],
    )
    assert bad.status_code == 422
    ok = post(
        api,
        acme,
        seed=43,
        preset="medium",
        profile="stress",
        overlap_of_collection_id=collection_id,
    )
    assert ok.status_code == 202
    assert (ok.json()["preset"], ok.json()["profile"], ok.json()["messages"]) == (
        "small",
        "default",
        10_000,
    )
    assert ok.json()["seed"] == 43


def test_failed_generation_can_be_retried(api: TestClient, clean_intake: Engine) -> None:
    from chatledger_core.infra.generator.pg_generation_repository import PgGenerationRepository

    matter = make_matter(clean_intake)
    created = post(api, matter, seed=7, preset="small", profile="clean").json()
    repo = PgGenerationRepository(clean_intake)
    from uuid import UUID

    repo.mark_failed(UUID(created["id"]), "INSUFFICIENT_DISK_SPACE", "Not enough disk space: x")
    failed = api.get(f"/api/v1/matters/{matter}/generations/{created['id']}").json()
    assert failed["state"] == "failed"
    assert failed["error"] == {
        "code": "INSUFFICIENT_DISK_SPACE",
        "message": "Not enough disk space: x",
    }
    res = api.post(f"/api/v1/matters/{matter}/generations/{created['id']}/retry")
    assert res.status_code == 202
    body = res.json()
    assert (body["state"], body["progress_messages"], body["error"]) == ("queued", 0, None)
    assert body["job_id"] != created["job_id"]
