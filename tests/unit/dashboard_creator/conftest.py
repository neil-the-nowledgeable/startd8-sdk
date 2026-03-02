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


@pytest.fixture
def michigan_budget_spec_dict():
    """Realistic multi-panel spec exercising raw PromQL dashboard features.

    Uses instant queries, fieldConfig, transformations, dataLinks,
    dashboard links, and variable options.
    """
    return {
        "title": "Michigan State Budget Overview",
        "uid": "cc-govbudget-michigan-overview",
        "description": "Where does Michigan's money go?",
        "tags": ["government", "budget", "michigan"],
        "links": [
            {
                "title": "USAspending.gov",
                "url": "https://www.usaspending.gov",
                "icon": "external link",
                "tooltip": "Federal spending data",
                "targetBlank": True,
            },
            {
                "title": "Related Dashboards",
                "type": "dashboards",
                "tags": ["budget"],
                "asDropdown": True,
                "includeVars": True,
                "keepTime": True,
            },
        ],
        "variables": [
            {
                "type": "prometheusDatasource",
                "name": "datasource",
                "label": "Data Source",
                "hide": 2,
            },
            {
                "type": "customVariable",
                "name": "fiscal_year",
                "label": "Fiscal Year",
                "query": "2024,2025,2026",
                "multi": False,
                "includeAll": True,
                "allValue": ".*",
                "default": "2026",
                "skipUrlSync": False,
            },
            {
                "type": "customVariable",
                "name": "department",
                "label": "Department",
                "query": "Education,Health,Transportation,Corrections",
                "multi": True,
                "includeAll": True,
                "default": "Education",
            },
        ],
        "panels": [
            {
                "type": "stat",
                "title": "Total Budget",
                "expr": "gov_budget_total_dollars",
                "unit": "currencyUSD",
                "description": "Total state budget for selected fiscal year",
                "gridPos": {"h": 4, "w": 6, "x": 0, "y": 0},
            },
            {
                "type": "table",
                "title": "Budget by Department",
                "targets": [
                    {
                        "expr": "gov_budget_by_department_dollars",
                        "legendFormat": "{{department}}",
                        "instant": True,
                        "format": "table",
                        "refId": "A",
                    },
                ],
                "gridPos": {"h": 10, "w": 12, "x": 0, "y": 4},
                "fieldConfig": {
                    "defaults": {"unit": "currencyUSD"},
                    "overrides": [
                        {
                            "matcher": {"id": "byName", "options": "department"},
                            "properties": [{"id": "custom.width", "value": 200}],
                        }
                    ],
                },
                "transformations": [
                    {
                        "id": "organize",
                        "options": {
                            "excludeByName": {"Time": True, "__name__": True},
                        },
                    },
                ],
                "dataLinks": [
                    {
                        "title": "View Department Detail",
                        "url": "/d/cc-govbudget-dept-detail?var-department=${__value.text}",
                    },
                ],
            },
            {
                "type": "timeseries",
                "title": "Budget Trend",
                "targets": [
                    {
                        "expr": "gov_budget_by_department_dollars",
                        "legendFormat": "{{department}}",
                    },
                ],
                "unit": "currencyUSD",
                "gridPos": {"h": 8, "w": 12, "x": 12, "y": 4},
                "description": "Year-over-year budget trend by department",
            },
            {"type": "row", "title": "Detailed Breakdown"},
            {
                "type": "piechart",
                "title": "Budget Distribution",
                "targets": [
                    {
                        "expr": "gov_budget_by_department_dollars",
                        "legendFormat": "{{department}}",
                        "instant": True,
                    },
                ],
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 13},
            },
        ],
    }
