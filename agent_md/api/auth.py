"""API key middleware for TCP transport.

Only applied when the backend is started with --port. Unix socket
connections are implicitly trusted (file permissions are the gate).
"""

from __future__ import annotations

import json

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


_PUBLIC_PATHS = {"/health"}


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Require X-API-Key header on all routes except /health."""

    def __init__(self, app, api_key: str) -> None:
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        provided = request.headers.get("X-API-Key")
        if not provided or provided != self.api_key:
            return Response(
                content=json.dumps({"detail": "Invalid or missing API key"}),
                status_code=401,
                media_type="application/json",
            )

        return await call_next(request)
