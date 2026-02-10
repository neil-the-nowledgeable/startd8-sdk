"""
API key authentication middleware for the StartD8 HTTP server (FR-521).

Requires X-API-Key header for mutation endpoints (POST).
GET /workflows is allowed without authentication for read-only discovery.
"""

from typing import Optional


class APIKeyMiddleware:
    """ASGI middleware that enforces API key authentication on mutation endpoints."""

    def __init__(self, app, api_key: str):
        self.app = app
        self.api_key = api_key

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            method = scope.get("method", "GET")
            path = scope.get("path", "")

            # Require auth for POST (mutation) endpoints
            if method == "POST":
                headers = dict(scope.get("headers", []))
                key = headers.get(b"x-api-key", b"").decode()
                if key != self.api_key:
                    from starlette.responses import JSONResponse
                    response = JSONResponse(
                        {"error": "Unauthorized"}, status_code=401
                    )
                    await response(scope, receive, send)
                    return

        await self.app(scope, receive, send)
