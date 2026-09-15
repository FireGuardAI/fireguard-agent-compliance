import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.logger import get_logger

logger = get_logger("app.access")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = (time.monotonic() - start) * 1000
        logger.info(
            f"{request.method} {request.url.path} -> "
            f"{response.status_code} ({duration_ms:.0f}ms)"
        )
        return response
