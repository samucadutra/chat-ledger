from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from starlette.requests import ClientDisconnect

from chatledger_api.main import create_app
from chatledger_core.config import Settings
from chatledger_core.domain._shared.errors import ConflictError, NotFoundError
from chatledger_core.infra.db.engine import make_engine


class NameTakenError(ConflictError):
    default_code = "NAME_TAKEN"


class Body(BaseModel):
    name: str = Field(min_length=3)


@pytest.fixture
def app(make_settings: Callable[..., Settings]) -> FastAPI:  # no DB needed
    engine = make_engine("postgresql+psycopg://x:y@127.0.0.1:1/none", connect_timeout=1)
    app = create_app(make_settings(), engine=engine)

    @app.post("/api/v1/_test/validate")
    def validate(body: Body) -> dict[str, str]:
        return {"name": body.name}

    @app.get("/api/v1/_test/conflict")
    def conflict() -> None:
        raise NameTakenError("Name already used.", details={"name": "x"})

    @app.get("/api/v1/_test/missing")
    def missing() -> None:
        raise NotFoundError("Matter not found.")

    @app.get("/api/v1/_test/disconnect")
    def disconnect() -> None:
        raise ClientDisconnect

    @app.get("/api/v1/_test/boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail")

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_unknown_route_404_envelope(client: TestClient) -> None:
    res = client.get("/api/v1/nope")
    assert res.status_code == 404
    assert res.json() == {
        "error": {
            "code": "NOT_FOUND",
            "message": "Route GET /api/v1/nope not found.",
            "details": {},
        }
    }
    assert res.headers["X-Request-ID"]


def test_method_not_allowed_envelope(client: TestClient) -> None:
    res = client.post("/health")
    assert res.status_code == 405
    assert res.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_validation_error_envelope(client: TestClient) -> None:
    res = client.post("/api/v1/_test/validate", json={"name": "ab"})
    assert res.status_code == 422
    err = res.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["message"] == "Request validation failed."
    assert err["details"]["fields"]
    assert err["details"]["fields"][0]["loc"] == ["body", "name"]


def test_domain_error_mapping(client: TestClient) -> None:
    res = client.get("/api/v1/_test/conflict")
    assert res.status_code == 409
    assert res.json() == {
        "error": {"code": "NAME_TAKEN", "message": "Name already used.", "details": {"name": "x"}}
    }
    assert client.get("/api/v1/_test/missing").json()["error"]["code"] == "NOT_FOUND"


def test_unhandled_exception_hides_trace(client: TestClient) -> None:
    res = client.get("/api/v1/_test/boom")
    assert res.status_code == 500
    body = res.json()
    rid = res.headers["X-Request-ID"]
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["message"] == f"Unexpected server error. See API logs (request_id={rid})."
    assert "Traceback" not in res.text
    assert "secret internal detail" not in res.text


def test_request_id_echoed(client: TestClient) -> None:
    res = client.get("/api/v1/nope", headers={"X-Request-ID": "contract-req-1"})
    assert res.headers["X-Request-ID"] == "contract-req-1"


def test_cors_preflight_for_web_origin(client: TestClient) -> None:
    res = client.options(
        "/api/v1/does-not-exist",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"},
    )
    assert res.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "POST" in res.headers["access-control-allow-methods"]


def test_cors_exposes_request_id(client: TestClient) -> None:
    res = client.get("/api/v1/nope", headers={"Origin": "http://localhost:3000"})
    assert "X-Request-ID" in res.headers["access-control-expose-headers"]


def test_lazy_module_app(monkeypatch: pytest.MonkeyPatch) -> None:
    import chatledger_api.main as main_module

    with pytest.raises(AttributeError):
        main_module.__getattr__("nope")


def test_client_disconnect_is_not_an_unhandled_error(client: TestClient) -> None:
    res = client.get("/api/v1/_test/disconnect")
    assert res.status_code == 499
    assert res.json()["error"]["code"] == "CLIENT_DISCONNECTED"
