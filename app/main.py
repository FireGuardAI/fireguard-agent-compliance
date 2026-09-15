"""FastAPI application entry point.

Grows as each build step wires in a new service — retrieval client
(Step 2), Gemini compliance engine (Step 3), the fused /audit endpoint
(Step 4). See README.md's build-status checklist for what's done.
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.exceptions import ComplianceEngineError, LLMResponseParsingError, RetrievalClientError
from app.logger import get_logger
from app.schemas import AuditRequest, ComplianceResponse
from app.services.compliance_engine import ComplianceEngine
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
compliance_engine: ComplianceEngine | None = None


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


@app.get("/health/gemini")
async def health_gemini() -> dict:
    """Makes one real (minimal) Gemini API call to prove the API key and
    model actually work. Not polled automatically — call it manually,
    it costs a tiny sliver of free-tier quota each time."""
    if compliance_engine is None:
        raise HTTPException(
            status_code=503, detail="Compliance engine not initialized"
        )
    try:
        await compliance_engine.self_check()
    except ComplianceEngineError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "ok", "model": settings.gemini_model_name}


@app.post("/api/v1/audit", response_model=ComplianceResponse)
async def run_compliance_audit(request: AuditRequest) -> ComplianceResponse:
    """Fetches relevant regulations and asks Gemini for a compliance
    verdict. Each failure mode gets its own status code and a clean
    message — the reference doc caught every possible failure with one
    blanket `except Exception: raise HTTPException(500, str(e))`, which
    leaked raw internal exception text and couldn't distinguish "our
    retrieval agent is down" from "Gemini returned garbage" from
    "nothing relevant was found"."""
    if retrieval_client is None or compliance_engine is None:
        raise HTTPException(status_code=503, detail="Services not initialized")

    query = (
        f"Fire regulations for {request.building_details.building_type} "
        f"with {request.building_details.number_of_floors} floors"
    )

    try:
        retrieved_chunks = await retrieval_client.get_relevant_chunks(query)
    except RetrievalClientError as exc:
        raise HTTPException(
            status_code=502, detail=f"Could not fetch regulations: {exc}"
        ) from exc

    if not retrieved_chunks:
        raise HTTPException(
            status_code=422,
            detail="No relevant fire regulations found for this building type",
        )

    try:
        return await compliance_engine.analyze(
            building_info=request.building_details.model_dump(),
            retrieved_chunks=retrieved_chunks,
        )
    except LLMResponseParsingError as exc:
        raise HTTPException(
            status_code=502, detail=f"Gemini returned an unusable response: {exc}"
        ) from exc
    except ComplianceEngineError as exc:
        raise HTTPException(
            status_code=503, detail=f"Compliance engine failed: {exc}"
        ) from exc


@app.on_event("startup")
async def on_startup() -> None:
    global retrieval_client, compliance_engine
    logger.info(f"{settings.api_title} v{settings.api_version} starting up")
    retrieval_client = RetrievalClient()
    compliance_engine = ComplianceEngine()
