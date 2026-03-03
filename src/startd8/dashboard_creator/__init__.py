"""
Dashboard Creator (dbrd-cr8r) — Generate Grafana dashboards from declarative specs.

Public API for the dashboard_creator package.
"""

from startd8.dashboard_creator.batch import BatchReport, DashboardReport, run_batch
from startd8.dashboard_creator.grafana_client import GrafanaClient, GrafanaResponse
from startd8.dashboard_creator.layout import apply_layout, auto_group_rows, auto_layout
from startd8.dashboard_creator.manifest_sync import extract_metrics_used, sync_manifest
from startd8.dashboard_creator.mixin_update import derive_mixin_entry, update_mixin_imports
from startd8.dashboard_creator.models import (
    DashboardSpec,
    GridPos,
    PanelSpec,
    PanelType,
    TargetSpec,
    ThresholdStep,
    VariableSpec,
    VariableType,
)
from startd8.dashboard_creator.provisioning import (
    ProvisioningResult,
    delete_local_artifacts,
    deprovision_dashboard,
    provision_dashboard,
)
from startd8.dashboard_creator.requirements_parser import (
    parse_requirements,
    requirements_to_yaml,
)
from startd8.dashboard_creator.workflow import DashboardCreatorWorkflow

__all__ = [
    # Models
    "DashboardSpec",
    "PanelSpec",
    "VariableSpec",
    "TargetSpec",
    "PanelType",
    "VariableType",
    "GridPos",
    "ThresholdStep",
    # Workflow
    "DashboardCreatorWorkflow",
    # Layout (DC-108, DC-109)
    "apply_layout",
    "auto_group_rows",
    "auto_layout",
    # Batch (DC-111)
    "run_batch",
    "BatchReport",
    "DashboardReport",
    # Manifest sync (DC-201)
    "sync_manifest",
    "extract_metrics_used",
    # Mixin update (DC-204)
    "update_mixin_imports",
    "derive_mixin_entry",
    # Grafana client
    "GrafanaClient",
    "GrafanaResponse",
    # Provisioning
    "ProvisioningResult",
    "provision_dashboard",
    "deprovision_dashboard",
    "delete_local_artifacts",
    # Requirements parser (DC-301)
    "parse_requirements",
    "requirements_to_yaml",
]
