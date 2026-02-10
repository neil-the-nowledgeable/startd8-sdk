"""
HTTP server module for webhook-triggered workflow execution.

Provides a Starlette ASGI application with endpoints for listing,
running, and polling workflow executions.

Install extras: pip install startd8[server]

Usage:
    from startd8.server import create_app
    app = create_app(api_key="secret")
"""

from .app import create_app

__all__ = ["create_app"]
