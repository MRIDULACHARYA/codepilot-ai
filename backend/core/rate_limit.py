"""Small in-memory sliding-window rate limiter (per client IP) for expensive endpoints."""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.core.config import get_settings

# Only POST analysis endpoints are limited; reads and health checks are free.
LIMITED_PREFIX = "/api/"


_HITS: dict[str, deque] = defaultdict(deque)


def reset_rate_limiter() -> None:
    """Clear all counters (used by tests)."""
    _HITS.clear()


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.hits = _HITS

    async def dispatch(self, request: Request, call_next):
        limit = get_settings().rate_limit_per_minute
        if request.method == "POST" and request.url.path.startswith(LIMITED_PREFIX) and limit > 0:
            ip = request.client.host if request.client else "unknown"
            now = time.monotonic()
            window = self.hits[ip]
            while window and now - window[0] > 60:
                window.popleft()
            if len(window) >= limit:
                retry = max(1, int(60 - (now - window[0])))
                return JSONResponse(
                    {"detail": "Rate limit exceeded. Please retry later."},
                    status_code=429,
                    headers={"Retry-After": str(retry)},
                )
            window.append(now)
        return await call_next(request)
