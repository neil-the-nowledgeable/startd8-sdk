"""
Grafana HTTP API client for dashboard provisioning (DC-202).

Wraps httpx.Client with token auth, version checking, and typed responses.
Token is read from GRAFANA_API_TOKEN env var — never logged or stored in results.
"""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import httpx

from startd8.exceptions import APIError, ConfigurationError
from startd8.logging_config import get_logger

logger = get_logger(__name__)

_MIN_GRAFANA_MAJOR = 9
_CONNECT_TIMEOUT = 10.0
_REQUEST_TIMEOUT = 30.0
_TOKEN_ENV_VAR = "GRAFANA_API_TOKEN"


@dataclass
class GrafanaResponse:
    """Typed wrapper around Grafana API responses."""

    success: bool
    status_code: int
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class GrafanaClient:
    """Sync Grafana HTTP API client for dashboard CRUD operations.

    Args:
        grafana_url: Base URL of the Grafana instance (e.g. ``https://grafana.example.com``).
        allow_insecure: Allow plain HTTP connections.  Logs a warning when True.
    """

    def __init__(self, grafana_url: str, allow_insecure: bool = False) -> None:
        self._url = grafana_url.rstrip("/")

        if not allow_insecure and not self._url.startswith("https://"):
            raise ConfigurationError(
                "Grafana URL must use HTTPS. Pass allow_insecure=True to override."
            )

        if allow_insecure and self._url.startswith("http://"):
            logger.warning(
                "Connecting to Grafana over plain HTTP — traffic is unencrypted"
            )

        token = os.environ.get(_TOKEN_ENV_VAR)
        if not token:
            raise ConfigurationError(
                f"Environment variable {_TOKEN_ENV_VAR} is not set"
            )

        self._token = token
        self._client = httpx.Client(
            base_url=self._url,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=httpx.Timeout(connect=_CONNECT_TIMEOUT, read=_REQUEST_TIMEOUT,
                                  write=_REQUEST_TIMEOUT, pool=_REQUEST_TIMEOUT),
        )

    @property
    def base_url(self) -> str:
        """Base URL of the Grafana instance (no trailing slash)."""
        return self._url

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_version(self) -> GrafanaResponse:
        """GET /api/health — verify connectivity and reject Grafana < v9."""
        resp = self._request("GET", "/api/health")
        if not resp.success:
            return resp

        version_str = resp.data.get("version", "")
        try:
            major = int(version_str.split(".")[0])
        except (ValueError, IndexError):
            return GrafanaResponse(
                success=False,
                status_code=resp.status_code,
                data=resp.data,
                error=f"Cannot parse Grafana version: '{version_str}'",
            )

        if major < _MIN_GRAFANA_MAJOR:
            return GrafanaResponse(
                success=False,
                status_code=resp.status_code,
                data=resp.data,
                error=(
                    f"Grafana v{version_str} is below the minimum supported "
                    f"version (v{_MIN_GRAFANA_MAJOR})"
                ),
            )

        logger.info("Grafana v%s — OK", version_str)
        return resp

    def upsert_dashboard(self, dashboard_json: Dict[str, Any]) -> GrafanaResponse:
        """POST /api/dashboards/db — create or update a dashboard."""
        payload = {
            "dashboard": dashboard_json,
            "overwrite": True,
        }
        return self._request("POST", "/api/dashboards/db", json=payload)

    def get_dashboard(self, uid: str) -> GrafanaResponse:
        """GET /api/dashboards/uid/{uid} — fetch a dashboard by UID."""
        return self._request("GET", f"/api/dashboards/uid/{uid}")

    def search_dashboards(self, query: str = "") -> GrafanaResponse:
        """GET /api/search — search dashboards."""
        return self._request("GET", "/api/search", params={"type": "dash-db", "query": query})

    def delete_dashboard(self, uid: str) -> GrafanaResponse:
        """DELETE /api/dashboards/uid/{uid} — delete a dashboard."""
        return self._request("DELETE", f"/api/dashboards/uid/{uid}")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> GrafanaResponse:
        """Execute an HTTP request and return a GrafanaResponse."""
        try:
            resp = self._client.request(method, path, json=json, params=params)
        except httpx.TimeoutException as exc:
            return GrafanaResponse(
                success=False,
                status_code=0,
                error=f"Request timed out: {exc}",
            )
        except httpx.HTTPError as exc:
            return GrafanaResponse(
                success=False,
                status_code=0,
                error=f"HTTP error: {exc}",
            )

        if resp.status_code in (401, 403):
            self._handle_auth_error(resp.status_code)

        try:
            data = resp.json() if resp.content else {}
        except ValueError:
            data = {}

        if resp.is_success:
            # search endpoint returns a list
            if isinstance(data, list):
                data = {"results": data}
            return GrafanaResponse(
                success=True,
                status_code=resp.status_code,
                data=data,
            )

        error_msg = data.get("message", resp.reason_phrase) if isinstance(data, dict) else str(data)
        return GrafanaResponse(
            success=False,
            status_code=resp.status_code,
            data=data if isinstance(data, dict) else {},
            error=error_msg,
        )

    @staticmethod
    def _handle_auth_error(status_code: int) -> None:
        """Raise APIError on 401/403 with a generic message (no token leak)."""
        raise APIError(
            "Grafana authentication failed — check that GRAFANA_API_TOKEN is valid "
            "and has the required permissions",
            provider="grafana",
            status_code=status_code,
        )
