"""
Tests for Phase 4 Enterprise — HTTP Server:
- FR-520: HTTP endpoints (list, run, poll)
- FR-521: API key authentication middleware
- FR-522: CLI serve command

Tests are split into:
- Always-run tests (module structure, ImportError handling, run store logic)
- Starlette-dependent tests (skipped when starlette not installed)
"""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Dict, Any, Optional


# =========================================================================
# Module structure tests (always run)
# =========================================================================

class TestServerModuleStructure:
    """Verify the server package exists and exports correctly."""

    def test_server_package_importable(self):
        """The server package can be imported regardless of starlette."""
        import startd8.server
        assert hasattr(startd8.server, 'create_app')

    def test_create_app_without_starlette_raises(self):
        """create_app() raises ImportError when starlette not installed."""
        from startd8.server.app import Starlette as _starlette_cls
        if _starlette_cls is not None:
            pytest.skip("starlette is installed — this tests the missing-dep path")

        from startd8.server import create_app
        with pytest.raises(ImportError, match="Server extras"):
            create_app()

    def test_auth_module_importable(self):
        from startd8.server.auth import APIKeyMiddleware
        assert APIKeyMiddleware is not None


# =========================================================================
# FR-521: API key middleware (unit-tested without starlette)
# =========================================================================

class TestAPIKeyMiddleware:
    """FR-521: API key authentication logic."""

    def test_middleware_stores_key(self):
        from startd8.server.auth import APIKeyMiddleware
        mock_app = MagicMock()
        mw = APIKeyMiddleware(mock_app, api_key="secret-123")
        assert mw.api_key == "secret-123"
        assert mw.app is mock_app

    def test_middleware_passes_get_requests(self):
        """GET requests should pass through without auth."""
        from startd8.server.auth import APIKeyMiddleware
        mock_app = AsyncMock()
        mw = APIKeyMiddleware(mock_app, api_key="secret")

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/workflows",
            "headers": [],
        }
        receive = AsyncMock()
        send = AsyncMock()

        asyncio.run(mw(scope, receive, send))
        mock_app.assert_called_once_with(scope, receive, send)

    def test_middleware_rejects_post_without_key(self):
        """POST requests without API key should be rejected."""
        from startd8.server.auth import APIKeyMiddleware

        try:
            from starlette.responses import JSONResponse
        except ImportError:
            pytest.skip("starlette required for rejection test")

        mock_app = AsyncMock()
        mw = APIKeyMiddleware(mock_app, api_key="secret")

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/workflows/test/run",
            "headers": [],
        }
        receive = AsyncMock()
        send = AsyncMock()

        asyncio.run(mw(scope, receive, send))
        # mock_app should NOT have been called (request rejected)
        mock_app.assert_not_called()

    def test_middleware_accepts_post_with_valid_key(self):
        """POST requests with valid API key should pass through."""
        from startd8.server.auth import APIKeyMiddleware
        mock_app = AsyncMock()
        mw = APIKeyMiddleware(mock_app, api_key="secret")

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/workflows/test/run",
            "headers": [(b"x-api-key", b"secret")],
        }
        receive = AsyncMock()
        send = AsyncMock()

        asyncio.run(mw(scope, receive, send))
        mock_app.assert_called_once_with(scope, receive, send)

    def test_middleware_rejects_invalid_key(self):
        """POST with wrong key should be rejected."""
        from startd8.server.auth import APIKeyMiddleware

        try:
            from starlette.responses import JSONResponse
        except ImportError:
            pytest.skip("starlette required for rejection test")

        mock_app = AsyncMock()
        mw = APIKeyMiddleware(mock_app, api_key="correct-key")

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/workflows/test/run",
            "headers": [(b"x-api-key", b"wrong-key")],
        }
        receive = AsyncMock()
        send = AsyncMock()

        asyncio.run(mw(scope, receive, send))
        mock_app.assert_not_called()

    def test_middleware_passes_non_http(self):
        """Non-HTTP scopes (e.g., websocket) pass through."""
        from startd8.server.auth import APIKeyMiddleware
        mock_app = AsyncMock()
        mw = APIKeyMiddleware(mock_app, api_key="secret")

        scope = {"type": "websocket", "path": "/ws"}
        receive = AsyncMock()
        send = AsyncMock()

        asyncio.run(mw(scope, receive, send))
        mock_app.assert_called_once()


# =========================================================================
# FR-520: Run store and background execution logic
# =========================================================================

class TestRunStore:
    """FR-520: In-memory run store for async execution."""

    def test_run_store_is_dict(self):
        from startd8.server.app import _run_store
        assert isinstance(_run_store, dict)

    def test_execute_run_stores_result(self):
        """_execute_run populates the run store on success."""
        from startd8.server.app import _execute_run, _run_store

        mock_workflow = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.to_dict.return_value = {"output": "done"}
        mock_workflow.run.return_value = mock_result

        # Remove arun so it falls back to sync run
        if hasattr(mock_workflow, 'arun'):
            del mock_workflow.arun

        run_id = "test-run-001"
        with patch("startd8.server.app.WorkflowRegistry", create=True) as mock_reg_mod:
            # We need to patch the import inside _execute_run
            with patch.dict("sys.modules", {}):
                from startd8.workflows import registry as reg_mod
                with patch.object(reg_mod, 'WorkflowRegistry') as mock_reg:
                    mock_reg.discover.return_value = None
                    mock_reg.get_workflow.return_value = mock_workflow

                    asyncio.run(_execute_run(run_id, "test-wf", {}))

        assert run_id in _run_store
        assert _run_store[run_id]["status"] in ("completed", "failed", "running")
        # Clean up
        _run_store.pop(run_id, None)

    def test_execute_run_unknown_workflow(self):
        """_execute_run marks run as failed for unknown workflow."""
        from startd8.server.app import _execute_run, _run_store

        run_id = "test-run-unknown"
        from startd8.workflows import registry as reg_mod
        with patch.object(reg_mod, 'WorkflowRegistry') as mock_reg:
            mock_reg.discover.return_value = None
            mock_reg.get_workflow.return_value = None

            asyncio.run(_execute_run(run_id, "nonexistent-wf", {}))

        assert _run_store[run_id]["status"] == "failed"
        assert "Unknown workflow" in _run_store[run_id]["error"]
        # Clean up
        _run_store.pop(run_id, None)

    def test_execute_run_exception_handling(self):
        """_execute_run stores error on exception."""
        from startd8.server.app import _execute_run, _run_store

        run_id = "test-run-error"
        from startd8.workflows import registry as reg_mod
        with patch.object(reg_mod, 'WorkflowRegistry') as mock_reg:
            mock_reg.discover.side_effect = RuntimeError("discover boom")

            asyncio.run(_execute_run(run_id, "any-wf", {}))

        assert _run_store[run_id]["status"] == "failed"
        assert "discover boom" in _run_store[run_id]["error"]
        # Clean up
        _run_store.pop(run_id, None)


# =========================================================================
# FR-522: CLI serve command structure
# =========================================================================

class TestServeCommand:
    """FR-522: CLI serve command exists."""

    def test_serve_command_registered(self):
        """The serve command is registered in the main app."""
        from startd8.cli import app
        command_names = [cmd.name for cmd in app.registered_commands]
        assert "serve" in command_names


# =========================================================================
# Starlette integration tests (skipped if starlette not installed)
# =========================================================================

class TestStarletteIntegration:
    """Full endpoint tests requiring starlette + httpx."""

    @pytest.fixture(autouse=True)
    def _require_starlette(self):
        pytest.importorskip("starlette")
        pytest.importorskip("httpx")

    def _get_client(self, api_key=None):
        from starlette.testclient import TestClient
        from startd8.server import create_app
        app = create_app(api_key=api_key)
        return TestClient(app)

    def test_create_app_returns_starlette(self):
        from starlette.applications import Starlette
        from startd8.server import create_app
        app = create_app()
        assert isinstance(app, Starlette)

    def test_create_app_with_api_key(self):
        from starlette.applications import Starlette
        from startd8.server import create_app
        app = create_app(api_key="test-key")
        assert isinstance(app, Starlette)

    def test_list_workflows_endpoint(self):
        client = self._get_client()
        response = client.get("/workflows")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_workflows_without_auth(self):
        """GET /workflows works without API key even when auth enabled."""
        client = self._get_client(api_key="secret")
        response = client.get("/workflows")
        assert response.status_code == 200

    def test_run_workflow_returns_run_id(self):
        """POST /workflows/{id}/run returns run_id and 202 status."""
        client = self._get_client()
        response = client.post("/workflows/test-wf/run", json={})
        assert response.status_code == 202
        data = response.json()
        assert "run_id" in data
        assert data["status"] == "queued"

    def test_api_key_required_for_mutation(self):
        """POST without key returns 401 when auth enabled."""
        client = self._get_client(api_key="secret-key")
        response = client.post("/workflows/test/run", json={})
        assert response.status_code == 401

    def test_api_key_accepted_for_mutation(self):
        """POST with correct key returns 202."""
        client = self._get_client(api_key="secret-key")
        response = client.post(
            "/workflows/test/run",
            json={},
            headers={"x-api-key": "secret-key"},
        )
        assert response.status_code == 202

    def test_poll_nonexistent_run(self):
        """GET /workflows/{id}/runs/{run_id} returns 404 for unknown run."""
        client = self._get_client()
        response = client.get("/workflows/test/runs/nonexistent-id")
        assert response.status_code == 404
