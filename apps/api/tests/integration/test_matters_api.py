from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from chatledger_core.infra.audit.pg_audit_log import PgAuditLog


@pytest.fixture
def api(client: TestClient, clean_intake: Engine) -> TestClient:
    return client


def create(api: TestClient, name: str, description: str | None = None) -> dict:  # type: ignore[type-arg]
    body: dict[str, object] = {"name": name}
    if description is not None:
        body["description"] = description
    res = api.post("/api/v1/matters", json=body)
    assert res.status_code == 201, res.text
    return res.json()  # type: ignore[no-any-return]


def test_create_matter_201(api: TestClient) -> None:
    res = api.post(
        "/api/v1/matters", json={"name": "Internal Review Q3", "description": "Quarterly review"}
    )
    assert res.status_code == 201
    body = res.json()
    assert body["name"] == "Internal Review Q3"
    assert body["description"] == "Quarterly review"
    assert str(UUID(body["id"])) == body["id"]
    assert body["collection_count"] == 0
    assert body["total_size_bytes"] == 0
    assert body["created_at"].endswith("Z")


def test_create_matter_trims_name(api: TestClient) -> None:
    body = create(api, "   Acme v. Beta   ", "   ")
    assert body["name"] == "Acme v. Beta"
    assert body["description"] is None


def test_name_too_short_422_message(api: TestClient) -> None:
    res = api.post("/api/v1/matters", json={"name": "Ab"})
    assert res.status_code == 422
    error = res.json()["error"]
    assert error["code"] == "MATTER_NAME_INVALID"
    assert error["message"] == "Name must be 3\u201380 characters"
    assert api.get("/api/v1/matters").json() == {"items": []}


def test_name_too_long_422(api: TestClient) -> None:
    res = api.post("/api/v1/matters", json={"name": "x" * 81})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "MATTER_NAME_INVALID"


def test_missing_name_is_validation_error(api: TestClient) -> None:
    res = api.post("/api/v1/matters", json={})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_duplicate_name_case_insensitive_409(api: TestClient) -> None:
    first = create(api, "Acme v. Beta")
    res = api.post("/api/v1/matters", json={"name": "ACME V. BETA"})
    assert res.status_code == 409
    error = res.json()["error"]
    assert error["code"] == "MATTER_NAME_TAKEN"
    assert error["message"] == "A matter with this name already exists"
    assert error["details"]["existing_matter_id"] == first["id"]


def test_description_too_long_422(api: TestClient) -> None:
    res = api.post("/api/v1/matters", json={"name": "Acme", "description": "d" * 501})
    assert res.status_code == 422
    error = res.json()["error"]
    assert error["code"] == "MATTER_DESCRIPTION_INVALID"
    assert error["message"] == "Description must be at most 500 characters"


def test_list_matters_newest_first_with_counts(api: TestClient) -> None:
    acme = create(api, "Acme v. Beta")
    create(api, "Beta Internal")
    items = api.get("/api/v1/matters").json()["items"]
    assert [m["name"] for m in items] == ["Beta Internal", "Acme v. Beta"]
    assert items[1]["id"] == acme["id"]
    assert items[1]["collection_count"] == 0


def test_get_matter(api: TestClient) -> None:
    acme = create(api, "Acme v. Beta")
    res = api.get(f"/api/v1/matters/{acme['id']}")
    assert res.status_code == 200
    assert res.json() == acme


@pytest.mark.parametrize("matter_id", ["00000000-0000-4000-8000-000000000000", "not-a-uuid"])
def test_get_matter_404(api: TestClient, matter_id: str) -> None:
    res = api.get(f"/api/v1/matters/{matter_id}")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "MATTER_NOT_FOUND"
    assert res.json()["error"]["message"] == "Matter not found."


def test_list_collections_unknown_matter_404(api: TestClient) -> None:
    res = api.get(f"/api/v1/matters/{uuid4()}/collections")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "MATTER_NOT_FOUND"


def test_get_collection_404s(api: TestClient) -> None:
    acme = create(api, "Acme v. Beta")
    res = api.get(f"/api/v1/matters/{acme['id']}/collections/{uuid4()}")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "COLLECTION_NOT_FOUND"
    res = api.get(f"/api/v1/matters/{acme['id']}/collections/not-a-uuid")
    assert res.json()["error"]["code"] == "COLLECTION_NOT_FOUND"
    res = api.get(f"/api/v1/matters/{uuid4()}/collections/{uuid4()}")
    assert res.json()["error"]["code"] == "MATTER_NOT_FOUND"


def test_matter_created_audit_event(api: TestClient, engine: Engine) -> None:
    acme = create(api, "Acme v. Beta")
    events = PgAuditLog(engine).list_for_entity("matter", acme["id"])
    assert [e.action for e in events] == ["matter.created"]


def test_openapi_exposes_matter_routes(api: TestClient) -> None:
    schema = api.get("/openapi.json").json()
    assert "/api/v1/matters" in schema["paths"]
    assert "/api/v1/matters/{matter_id}/collections" in schema["paths"]
    assert {"MatterOut", "CollectionOut"} <= set(schema["components"]["schemas"])
