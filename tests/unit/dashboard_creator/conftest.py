"""Shared fixtures for dashboard_creator unit tests."""

import pytest
from pathlib import Path


@pytest.fixture
def sample_spec_dict():
    """Minimal valid DashboardSpec as a dict."""
    return {
        "title": "Test Dashboard",
        "panels": [
            {"type": "stat", "title": "Test Metric", "expr": "up"}
        ],
    }


@pytest.fixture
def sample_spec_yaml(tmp_path, sample_spec_dict):
    """Write sample spec to a YAML file and return path."""
    import yaml
    spec_path = tmp_path / "test-spec.yaml"
    spec_path.write_text(yaml.dump(sample_spec_dict))
    return spec_path


@pytest.fixture
def mock_mixin_dir(tmp_path):
    """Create a minimal mixin directory structure for testing."""
    mixin = tmp_path / "startd8-mixin"
    (mixin / "lib").mkdir(parents=True)
    (mixin / "dashboards").mkdir()
    vendor = mixin / "vendor"
    vendor.mkdir()
    (vendor / "grafonnet").mkdir()
    # Write minimal .libsonnet files
    (mixin / "config.libsonnet").write_text("{ _config+:: {} }")
    (mixin / "lib" / "panels.libsonnet").write_text("{ stat(title, expr):: {} }")
    (mixin / "lib" / "variables.libsonnet").write_text("{ }")
    (mixin / "lib" / "dashboards.libsonnet").write_text(
        "{ dashboard(t, u, description='', tags=[]):: {}, "
        "withPanels(d, p):: d { panels: p } }"
    )
    (mixin / "mixin.libsonnet").write_text("{ grafanaDashboards+:: {} }")
    return mixin


@pytest.fixture
def full_spec_dict():
    """A more complete spec with variables, tags, and multiple panels."""
    return {
        "title": "Full Test Dashboard",
        "description": "Integration test dashboard",
        "tags": ["test", "integration"],
        "panels": [
            {"type": "stat", "title": "Uptime", "expr": "up"},
            {
                "type": "timeseries",
                "title": "Request Rate",
                "targets": [
                    {"expr": "rate(http_requests_total[5m])", "legendFormat": "{{method}}"},
                ],
            },
            {"type": "row", "title": "Details"},
            {
                "type": "table",
                "title": "Top Endpoints",
                "targets": [
                    {"expr": "topk(10, http_requests_total)", "refId": "A"},
                ],
            },
        ],
        "variables": [
            {"type": "prometheusDatasource", "name": "datasource", "label": "Data Source"},
        ],
    }


@pytest.fixture
def grouped_spec_dict():
    """Spec with grouped panels for layout testing (DC-108)."""
    return {
        "title": "Grouped Dashboard",
        "tags": ["grouped"],
        "panels": [
            {"type": "stat", "title": "Global Metric", "expr": "up"},
            {
                "type": "stat",
                "title": "Infra CPU",
                "expr": "${metrics.requestsTotal}",
                "group": "Infrastructure",
            },
            {
                "type": "stat",
                "title": "Infra Memory",
                "expr": "${metrics.tokensTotal}",
                "group": "Infrastructure",
            },
            {
                "type": "stat",
                "title": "Cost Total",
                "expr": "${metrics.costTotal}",
                "group": "+Costs",
            },
        ],
    }
