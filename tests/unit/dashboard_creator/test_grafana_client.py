"""Tests for dashboard_creator.grafana_client — GrafanaClient (DC-202)."""

import json

import httpx
import pytest
import respx

from startd8.dashboard_creator.grafana_client import (
    GrafanaClient,
    GrafanaResponse,
    _TOKEN_ENV_VAR,
)
from startd8.exceptions import APIError, ConfigurationError


GRAFANA_URL = "https://grafana.example.com"


@pytest.fixture(autouse=True)
def _set_token(monkeypatch):
    """Ensure GRAFANA_API_TOKEN is set for every test."""
    monkeypatch.setenv(_TOKEN_ENV_VAR, "test-token-123")


# ---------------------------------------------------------------------------
# Construction / config validation
# ---------------------------------------------------------------------------


class TestGrafanaClientInit:
    def test_rejects_http_url_without_allow_insecure(self):
        with pytest.raises(ConfigurationError, match="HTTPS"):
            GrafanaClient("http://grafana.local")

    def test_allows_http_with_flag(self):
        client = GrafanaClient("http://grafana.local", allow_insecure=True)
        assert client._url == "http://grafana.local"

    def test_https_url_accepted(self):
        client = GrafanaClient(GRAFANA_URL)
        assert client._url == GRAFANA_URL

    def test_trailing_slash_stripped(self):
        client = GrafanaClient(f"{GRAFANA_URL}/")
        assert client._url == GRAFANA_URL

    def test_missing_token_raises(self, monkeypatch):
        monkeypatch.delenv(_TOKEN_ENV_VAR, raising=False)
        with pytest.raises(ConfigurationError, match=_TOKEN_ENV_VAR):
            GrafanaClient(GRAFANA_URL)


# ---------------------------------------------------------------------------
# check_version
# ---------------------------------------------------------------------------


class TestCheckVersion:
    @respx.mock
    def test_healthy_v10(self):
        respx.get(f"{GRAFANA_URL}/api/health").mock(
            return_value=httpx.Response(200, json={"version": "10.2.3", "database": "ok"})
        )
        client = GrafanaClient(GRAFANA_URL)
        resp = client.check_version()
        assert resp.success is True
        assert resp.data["version"] == "10.2.3"

    @respx.mock
    def test_rejects_old_version(self):
        respx.get(f"{GRAFANA_URL}/api/health").mock(
            return_value=httpx.Response(200, json={"version": "8.5.0"})
        )
        client = GrafanaClient(GRAFANA_URL)
        resp = client.check_version()
        assert resp.success is False
        assert "below" in resp.error

    @respx.mock
    def test_unparseable_version(self):
        respx.get(f"{GRAFANA_URL}/api/health").mock(
            return_value=httpx.Response(200, json={"version": "unknown"})
        )
        client = GrafanaClient(GRAFANA_URL)
        resp = client.check_version()
        assert resp.success is False
        assert "parse" in resp.error.lower()

    @respx.mock
    def test_server_error(self):
        respx.get(f"{GRAFANA_URL}/api/health").mock(
            return_value=httpx.Response(500, json={"message": "internal error"})
        )
        client = GrafanaClient(GRAFANA_URL)
        resp = client.check_version()
        assert resp.success is False
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# upsert_dashboard
# ---------------------------------------------------------------------------


class TestUpsertDashboard:
    @respx.mock
    def test_upsert_success(self):
        respx.post(f"{GRAFANA_URL}/api/dashboards/db").mock(
            return_value=httpx.Response(200, json={
                "id": 1, "uid": "test-uid", "url": "/d/test-uid/test",
                "status": "success", "version": 1,
            })
        )
        client = GrafanaClient(GRAFANA_URL)
        resp = client.upsert_dashboard({"uid": "test-uid", "title": "Test"})
        assert resp.success is True
        assert resp.data["uid"] == "test-uid"

    @respx.mock
    def test_upsert_sends_overwrite(self):
        route = respx.post(f"{GRAFANA_URL}/api/dashboards/db").mock(
            return_value=httpx.Response(200, json={"status": "success"})
        )
        client = GrafanaClient(GRAFANA_URL)
        client.upsert_dashboard({"uid": "x", "title": "T"})
        body = json.loads(route.calls[0].request.content)
        assert body["overwrite"] is True

    @respx.mock
    def test_auth_error_raises(self):
        respx.post(f"{GRAFANA_URL}/api/dashboards/db").mock(
            return_value=httpx.Response(401, json={"message": "Unauthorized"})
        )
        client = GrafanaClient(GRAFANA_URL)
        with pytest.raises(APIError, match="authentication failed"):
            client.upsert_dashboard({"uid": "x", "title": "T"})


# ---------------------------------------------------------------------------
# get_dashboard
# ---------------------------------------------------------------------------


class TestGetDashboard:
    @respx.mock
    def test_get_success(self):
        respx.get(f"{GRAFANA_URL}/api/dashboards/uid/my-uid").mock(
            return_value=httpx.Response(200, json={
                "dashboard": {"uid": "my-uid", "title": "My Dashboard"},
                "meta": {"slug": "my-dashboard"},
            })
        )
        client = GrafanaClient(GRAFANA_URL)
        resp = client.get_dashboard("my-uid")
        assert resp.success is True
        assert resp.data["dashboard"]["uid"] == "my-uid"

    @respx.mock
    def test_get_not_found(self):
        respx.get(f"{GRAFANA_URL}/api/dashboards/uid/missing").mock(
            return_value=httpx.Response(404, json={"message": "Dashboard not found"})
        )
        client = GrafanaClient(GRAFANA_URL)
        resp = client.get_dashboard("missing")
        assert resp.success is False
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# search_dashboards
# ---------------------------------------------------------------------------


class TestSearchDashboards:
    @respx.mock
    def test_search_returns_results(self):
        respx.get(f"{GRAFANA_URL}/api/search").mock(
            return_value=httpx.Response(200, json=[
                {"uid": "a", "title": "Alpha"},
                {"uid": "b", "title": "Beta"},
            ])
        )
        client = GrafanaClient(GRAFANA_URL)
        resp = client.search_dashboards("test")
        assert resp.success is True
        assert len(resp.data["results"]) == 2


# ---------------------------------------------------------------------------
# delete_dashboard
# ---------------------------------------------------------------------------


class TestDeleteDashboard:
    @respx.mock
    def test_delete_success(self):
        respx.delete(f"{GRAFANA_URL}/api/dashboards/uid/del-uid").mock(
            return_value=httpx.Response(200, json={"title": "Deleted"})
        )
        client = GrafanaClient(GRAFANA_URL)
        resp = client.delete_dashboard("del-uid")
        assert resp.success is True

    @respx.mock
    def test_delete_403_raises(self):
        respx.delete(f"{GRAFANA_URL}/api/dashboards/uid/del-uid").mock(
            return_value=httpx.Response(403, json={"message": "Forbidden"})
        )
        client = GrafanaClient(GRAFANA_URL)
        with pytest.raises(APIError, match="authentication failed"):
            client.delete_dashboard("del-uid")


# ---------------------------------------------------------------------------
# Timeout / transport errors
# ---------------------------------------------------------------------------


class TestTransportErrors:
    @respx.mock
    def test_timeout_returns_error(self):
        respx.get(f"{GRAFANA_URL}/api/health").mock(
            side_effect=httpx.ReadTimeout("read timed out")
        )
        client = GrafanaClient(GRAFANA_URL)
        resp = client.check_version()
        assert resp.success is False
        assert "timed out" in resp.error.lower()


# ---------------------------------------------------------------------------
# GrafanaResponse dataclass
# ---------------------------------------------------------------------------


class TestGrafanaResponse:
    def test_default_data_is_empty_dict(self):
        r = GrafanaResponse(success=True, status_code=200)
        assert r.data == {}
        assert r.error is None
