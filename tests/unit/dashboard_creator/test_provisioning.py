"""Tests for dashboard_creator.provisioning — DC-203, DC-208."""

from unittest.mock import MagicMock

import yaml

from startd8.dashboard_creator.grafana_client import GrafanaResponse
from startd8.dashboard_creator.provisioning import (
    ProvisioningResult,
    delete_local_artifacts,
    deprovision_dashboard,
    provision_dashboard,
)


def _mock_client(url: str = "https://grafana.example.com") -> MagicMock:
    client = MagicMock()
    client.base_url = url
    return client


# ---------------------------------------------------------------------------
# provision_dashboard
# ---------------------------------------------------------------------------


class TestProvisionDashboard:
    def test_success_returns_url(self):
        client = _mock_client()
        client.upsert_dashboard.return_value = GrafanaResponse(
            success=True,
            status_code=200,
            data={"uid": "my-uid", "url": "/d/my-uid/my-dash", "version": 1},
        )
        result = provision_dashboard({"uid": "my-uid", "title": "My Dash"}, client)
        assert result.success is True
        assert result.dashboard_url == "https://grafana.example.com/d/my-uid/my-dash"
        assert result.uid == "my-uid"

    def test_failure_returns_error(self):
        client = _mock_client()
        client.upsert_dashboard.return_value = GrafanaResponse(
            success=False, status_code=500, error="Internal Server Error"
        )
        result = provision_dashboard({"uid": "fail-uid", "title": "Fail"}, client)
        assert result.success is False
        assert "Internal Server Error" in result.error
        assert result.details["status_code"] == 500

    def test_url_defaults_when_response_missing_url_field(self):
        client = _mock_client()
        client.upsert_dashboard.return_value = GrafanaResponse(
            success=True, status_code=200, data={"uid": "x"}
        )
        result = provision_dashboard({"uid": "x", "title": "T"}, client)
        assert result.dashboard_url == "https://grafana.example.com/d/x"


# ---------------------------------------------------------------------------
# deprovision_dashboard
# ---------------------------------------------------------------------------


class TestDeprovisionDashboard:
    def test_delete_success(self):
        client = _mock_client()
        client.delete_dashboard.return_value = GrafanaResponse(
            success=True, status_code=200, data={"title": "Gone"}
        )
        result = deprovision_dashboard("del-uid", client)
        assert result.success is True
        assert result.uid == "del-uid"

    def test_404_treated_as_success(self):
        client = _mock_client()
        client.delete_dashboard.return_value = GrafanaResponse(
            success=False, status_code=404, error="Not found"
        )
        result = deprovision_dashboard("gone-uid", client)
        assert result.success is True

    def test_server_error_returns_failure(self):
        client = _mock_client()
        client.delete_dashboard.return_value = GrafanaResponse(
            success=False, status_code=500, error="Internal Error"
        )
        result = deprovision_dashboard("err-uid", client)
        assert result.success is False
        assert result.error == "Internal Error"


# ---------------------------------------------------------------------------
# delete_local_artifacts
# ---------------------------------------------------------------------------


class TestDeleteLocalArtifacts:
    def test_deletes_json_file(self, tmp_path):
        json_file = tmp_path / "my-uid.json"
        json_file.write_text("{}")
        result = delete_local_artifacts("my-uid", output_dir=tmp_path)
        assert result["json"] is True
        assert not json_file.exists()

    def test_json_not_found(self, tmp_path):
        result = delete_local_artifacts("nope", output_dir=tmp_path)
        assert result["json"] is False

    def test_removes_libsonnet_when_requested(self, tmp_path):
        libsonnet = tmp_path / "my_uid.libsonnet"
        libsonnet.write_text("local x = {};")
        result = delete_local_artifacts(
            "cc-startd8-my-uid",
            output_dir=tmp_path,
            remove_source=True,
            libsonnet_dir=tmp_path,
        )
        assert result["libsonnet"] is True
        assert not libsonnet.exists()

    def test_removes_manifest_ref(self, tmp_path):
        manifest = tmp_path / "manifest.yaml"
        manifest.write_text(yaml.dump({
            "dashboards": [
                {"uid": "keep-me", "title": "Keep"},
                {"uid": "remove-me", "title": "Remove"},
            ]
        }))
        result = delete_local_artifacts(
            "remove-me",
            output_dir=tmp_path,
            manifest_path=manifest,
        )
        assert result["manifest_ref"] is True
        data = yaml.safe_load(manifest.read_text())
        uids = [d["uid"] for d in data["dashboards"]]
        assert "remove-me" not in uids
        assert "keep-me" in uids

    def test_manifest_ref_not_found(self, tmp_path):
        manifest = tmp_path / "manifest.yaml"
        manifest.write_text(yaml.dump({"dashboards": [{"uid": "other"}]}))
        result = delete_local_artifacts(
            "missing-uid",
            output_dir=tmp_path,
            manifest_path=manifest,
        )
        assert result["manifest_ref"] is False


# ---------------------------------------------------------------------------
# ProvisioningResult dataclass
# ---------------------------------------------------------------------------


class TestProvisioningResult:
    def test_defaults(self):
        r = ProvisioningResult(success=True, uid="test")
        assert r.dashboard_url is None
        assert r.error is None
        assert r.details == {}
