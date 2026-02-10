"""
Starlette ASGI application for the StartD8 HTTP workflow server (FR-520).

Endpoints:
    GET  /workflows                      — list all registered workflows
    POST /workflows/{id}/run             — trigger async workflow execution
    GET  /workflows/{id}/runs/{run_id}   — poll execution status
"""

import asyncio
import uuid
from typing import Any, Dict, Optional

try:
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.responses import JSONResponse
    from starlette.routing import Route
except ImportError:
    Starlette = None  # type: ignore[assignment, misc]

from .auth import APIKeyMiddleware


# In-memory run store (keyed by run_id)
_run_store: Dict[str, Any] = {}


async def _execute_run(run_id: str, workflow_id: str, body: Dict[str, Any]) -> None:
    """Background task: execute workflow and store result."""
    from ..workflows.registry import WorkflowRegistry

    _run_store[run_id] = {"status": "running", "workflow_id": workflow_id}
    try:
        WorkflowRegistry.discover()
        workflow = WorkflowRegistry.get_workflow(workflow_id)
        if workflow is None:
            _run_store[run_id] = {
                "status": "failed",
                "error": f"Unknown workflow: {workflow_id}",
            }
            return

        # Prefer async execution
        if hasattr(workflow, "arun"):
            result = await workflow.arun(body)
        else:
            result = workflow.run(body)

        _run_store[run_id] = {
            "status": "completed" if result.success else "failed",
            "result": result.to_dict(),
        }
    except Exception as e:
        _run_store[run_id] = {
            "status": "failed",
            "error": str(e),
        }


async def list_workflows(request):
    """GET /workflows — list all registered workflows."""
    from ..workflows.registry import WorkflowRegistry

    WorkflowRegistry.discover()
    workflows = WorkflowRegistry.list_workflow_metadata()
    return JSONResponse([w.to_dict() for w in workflows])


async def run_workflow(request):
    """POST /workflows/{id}/run — trigger async execution, return run_id."""
    workflow_id = request.path_params["id"]

    try:
        body = await request.json()
    except Exception:
        body = {}

    run_id = str(uuid.uuid4())
    asyncio.create_task(_execute_run(run_id, workflow_id, body))
    return JSONResponse({"run_id": run_id, "status": "queued"}, status_code=202)


async def get_run_status(request):
    """GET /workflows/{id}/runs/{run_id} — poll execution status."""
    run_id = request.path_params["run_id"]
    entry = _run_store.get(run_id)

    if entry is None:
        return JSONResponse({"error": "Run not found"}, status_code=404)

    return JSONResponse(entry)


def create_app(api_key: Optional[str] = None) -> "Starlette":
    """Create the StartD8 ASGI application.

    Args:
        api_key: Optional API key. When set, POST endpoints require
                 an X-API-Key header matching this value.

    Returns:
        A Starlette application instance.

    Raises:
        ImportError: If starlette is not installed.
    """
    if Starlette is None:
        raise ImportError(
            "Server extras required: pip install startd8[server]"
        )

    routes = [
        Route("/workflows", list_workflows),
        Route("/workflows/{id}/run", run_workflow, methods=["POST"]),
        Route("/workflows/{id}/runs/{run_id}", get_run_status),
    ]

    middleware = []
    if api_key:
        middleware.append(Middleware(APIKeyMiddleware, api_key=api_key))

    return Starlette(routes=routes, middleware=middleware)
