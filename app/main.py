from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings
from app.exceptions import ComplianceEngineError, LLMResponseParsingError, RetrievalClientError
from app.logger import get_logger
from app.middleware import RequestLoggingMiddleware
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
app.add_middleware(RequestLoggingMiddleware)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(f"Unhandled exception on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


retrieval_client: RetrievalClient | None = None
compliance_engine: ComplianceEngine | None = None


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": settings.api_title}


@app.get("/health/retrieval")
async def health_retrieval() -> dict:
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
    if compliance_engine is None:
        raise HTTPException(
            status_code=503, detail="Compliance engine not initialized"
        )
    try:
        await compliance_engine.self_check()
    except ComplianceEngineError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "ok", "model": settings.gemini_model_name}


@app.get("/health/all")
async def health_all() -> dict:
    dependencies: dict = {}
    overall_ok = True

    if retrieval_client is None:
        dependencies["retrieval"] = {"status": "error", "detail": "not initialized"}
        overall_ok = False
    else:
        try:
            dependencies["retrieval"] = {
                "status": "ok",
                "detail": await retrieval_client.health_check(),
            }
        except RetrievalClientError as exc:
            dependencies["retrieval"] = {"status": "error", "detail": str(exc)}
            overall_ok = False

    if compliance_engine is None:
        dependencies["gemini"] = {"status": "error", "detail": "not initialized"}
        overall_ok = False
    else:
        try:
            await compliance_engine.self_check()
            dependencies["gemini"] = {"status": "ok"}
        except ComplianceEngineError as exc:
            dependencies["gemini"] = {"status": "error", "detail": str(exc)}
            overall_ok = False

    return {"status": "ok" if overall_ok else "degraded", "dependencies": dependencies}


@app.post("/api/v1/audit", response_model=ComplianceResponse)
@limiter.limit(settings.audit_rate_limit)
async def run_compliance_audit(
    request: Request, audit_request: AuditRequest
) -> ComplianceResponse:
    if retrieval_client is None or compliance_engine is None:
        raise HTTPException(status_code=503, detail="Services not initialized")

    query = (
        f"Fire regulations for {audit_request.building_details.building_type} "
        f"with {audit_request.building_details.number_of_floors} floors"
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
            building_info=audit_request.building_details.model_dump(),
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
