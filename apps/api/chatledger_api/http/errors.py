"""Uniform error envelope ``{"error": {"code", "message", "details"}}`` and request IDs."""

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import ClientDisconnect
from starlette.responses import Response

from chatledger_core.domain._shared.errors import DomainError
from chatledger_core.infra.logging import bind_context, get_logger, unbind_context

REQUEST_ID_HEADER = "X-Request-ID"
_log = get_logger("chatledger_api.http")

_STATUS_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "VALIDATION_ERROR",
    429: "TOO_MANY_REQUESTS",
    503: "SERVICE_UNAVAILABLE",
}


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def _request_id(request: Request) -> str:
    rid = getattr(request.state, "request_id", None)
    return rid if isinstance(rid, str) else str(uuid.uuid4())


def _envelope(
    request: Request,
    status: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    all_headers = {REQUEST_ID_HEADER: _request_id(request), **(headers or {})}
    return JSONResponse(error_body(code, message, details), status_code=status, headers=all_headers)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Echo or generate ``X-Request-ID``, bind it into logs, log one line per request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, "").strip()
        rid = incoming[:128] if incoming else str(uuid.uuid4())
        request.state.request_id = rid
        bind_context(request_id=rid)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            unbind_context("request_id")
        response.headers[REQUEST_ID_HEADER] = rid
        _log.info(
            "http.request",
            request_id=rid,
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
        )
        return response


async def _domain_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    return _envelope(request, exc.http_status, exc.code, exc.message, exc.details)


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    fields = [
        {"loc": list(err.get("loc", ())), "msg": str(err.get("msg", ""))} for err in exc.errors()
    ]
    return _envelope(
        request, 422, "VALIDATION_ERROR", "Request validation failed.", {"fields": fields}
    )


async def _http_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    status = exc.status_code
    code = _STATUS_CODES.get(status, f"HTTP_{status}")
    if status == 404:
        message = f"Route {request.method} {request.url.path} not found."
    elif status == 405:
        message = f"Method {request.method} not allowed for {request.url.path}."
    else:
        message = str(exc.detail) if exc.detail else "Request failed."
    headers = dict(exc.headers) if exc.headers else None
    return _envelope(request, status, code, message, headers=headers)


async def _client_disconnect(request: Request, exc: Exception) -> JSONResponse:
    # The client went away mid-request (e.g. an aborted upload); nobody reads this response.
    _log.info(
        "http.client_disconnect",
        request_id=_request_id(request),
        method=request.method,
        path=request.url.path,
    )
    return _envelope(request, 499, "CLIENT_DISCONNECTED", "Client closed the connection.")


async def _unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    rid = _request_id(request)
    _log.error(
        "http.unhandled_exception",
        request_id=rid,
        method=request.method,
        path=request.url.path,
        exc_info=exc,
    )
    return _envelope(
        request,
        500,
        "INTERNAL_ERROR",
        f"Unexpected server error. See API logs (request_id={rid}).",
    )


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(ClientDisconnect, _client_disconnect)
    app.add_exception_handler(Exception, _unhandled_error)
