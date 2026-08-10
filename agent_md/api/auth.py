"""API key middleware for the TCP transport.

Applied by wrapping the ASGI app handed to the TCP uvicorn server — never
via ``app.add_middleware``. The socket and TCP servers share a single
FastAPI instance (one runtime, one bootstrap), so a middleware installed on
the app itself would also guard the Unix socket, and the local CLI's
``BackendClient`` sends no key: every local command would answer 401.

Unix socket connections stay implicitly trusted — file permissions
(``chmod 600``) are the gate there.
"""

from __future__ import annotations

import hmac
import json

from starlette.types import ASGIApp, Receive, Scope, Send

_PUBLIC_PATHS = {"/health"}

_UNAUTHORIZED_BODY = json.dumps({"detail": "Invalid or missing API key"}).encode()


class ApiKeyMiddleware:
    """Require an ``X-API-Key`` header on every route except ``/health``."""

    def __init__(self, app: ASGIApp, api_key: str) -> None:
        self.app = app
        self.api_key = api_key

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Lifespan flows straight through: the wrapped app owns the runtime.
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return

        if scope["type"] == "http" and scope.get("path") in _PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return

        if self._authorized(scope):
            await self.app(scope, receive, send)
            return

        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return

        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(_UNAUTHORIZED_BODY)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": _UNAUTHORIZED_BODY})

    def _authorized(self, scope: Scope) -> bool:
        expected = self.api_key.encode()
        for name, value in scope.get("headers", []):
            if name == b"x-api-key":
                return hmac.compare_digest(value, expected)
        return False
