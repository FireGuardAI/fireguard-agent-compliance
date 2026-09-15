"""FastAPI application entry point.

Grows as each build step wires in a new service — retrieval client
(Step 2), Gemini compliance engine (Step 3), the fused /audit endpoint
(Step 4). See README.md's build-status checklist for what's done.
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.exceptions import RetrievalClientError
from app.logger import get_logger
from app.services.retrieval_client import RetrievalClient

logger = get_logger(__name__)

app = FastAPI(title=settings.api_title, version=settings.api_version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Loaded once at startup (see on_startup below), never per-request.
retrieval_client: RetrievalClient | None = None


@app.get("/health")
async def health() -> dict:
    """Basic liveness check — confirms the API process itself is up.
    Does NOT check the retrieval agent or Gemini; those get their own
    /health/retrieval and /health/gemini checks in Steps 2 and 3."""
    return {"status": "ok", "service": settings.api_title}


@app.get("/health/retrieval")
async def health_retrieval() -> dict:
    """Proves fireguard-agent-retrieval is actually reachable — not just
    that the client object was constructed."""
    if retrieval_client is None:
        raise HTTPException(
            status_code=503, detail="Retrieval client not initialized"
        )
    try:
        upstream_health = await retrieval_client.health_check()
    except RetrievalClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "ok", "retrieval_agent": upstream_health}


@app.on_event("startup")
async def on_startup() -> None:
    global retrieval_client
    logger.info(f"{settings.api_title} v{settings.api_version} starting up")
    retrieval_client = RetrievalClient()
