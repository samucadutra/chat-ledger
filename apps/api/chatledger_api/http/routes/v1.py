"""Versioned API router. Later features include their routers here."""

from fastapi import APIRouter

from chatledger_api.http.routes import matters

router = APIRouter(prefix="/api/v1")
router.include_router(matters.router)
