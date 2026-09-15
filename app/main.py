"""FastAPI application entry point.

Grows as each build step wires in a new service — retrieval client
(Step 2), Gemini compliance engine (Step 3), the fused /audit endpoint
(Step 4). See README.md's build-status checklist for what's done.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)

app = FastAPI(title=settings.api_title, version=settings.api_version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    """Basic liveness check — confirms the API process itself is up.
    Does NOT check the retrieval agent or Gemini; those get their own
    /health/retrieval and /health/gemini checks in Steps 2 and 3."""
    return {"status": "ok", "service": settings.api_title}


@app.on_event("startup")
async def on_startup() -> None:
    logger.info(f"{settings.api_title} v{settings.api_version} starting up")
