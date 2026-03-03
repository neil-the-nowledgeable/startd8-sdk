"""
Dashboard provisioning and deprovisioning (DC-203, DC-208).

Handles push/delete of dashboards to Grafana and local artifact cleanup.
Provisioning failures return results (not exceptions) — callers decide severity.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from startd8.dashboard_creator.grafana_client import GrafanaClient, GrafanaResponse
from startd8.logging_config import get_logger

logger = get_logger(__name__)

_DEFAULT_OUTPUT_DIR = ".startd8/dashboards"


@dataclass
class ProvisioningResult:
    """Outcome of a provisioning or deprovisioning operation."""

    success: bool
    uid: str
    dashboard_url: Optional[str] = None
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


def provision_dashboard(
    dashboard_json: Dict[str, Any],
    client: GrafanaClient,
) -> ProvisioningResult:
    """Upsert a dashboard to Grafana and return a clickable URL.

    Verifies Grafana version compatibility (DC-202 AC4) before attempting
    the upsert.  All failures — including version mismatch — are returned
    as ``ProvisioningResult(success=False)``; callers decide severity.

    Args:
        dashboard_json: Compiled dashboard JSON (dict).
        client: Authenticated GrafanaClient instance.

    Returns:
        ProvisioningResult with dashboard_url on success, or
        ProvisioningResult(success=False) on any failure.
    """
    uid = dashboard_json.get("uid", "unknown")

    # DC-202 AC4: Verify Grafana version before provisioning
    version_resp = client.check_version()
    if not version_resp.success:
        logger.warning("Grafana version check failed for %s: %s", uid, version_resp.error)
        return ProvisioningResult(
            success=False,
            uid=uid,
            error=f"Grafana version check failed: {version_resp.error}",
            details={"status_code": version_resp.status_code},
        )

    resp: GrafanaResponse = client.upsert_dashboard(dashboard_json)
    if not resp.success:
        logger.warning("Provisioning failed for %s: %s", uid, resp.error)
        return ProvisioningResult(
            success=False,
            uid=uid,
            error=resp.error,
            details={"status_code": resp.status_code},
        )

    # Build clickable URL from the response 'url' field
    grafana_url = client.base_url
    dashboard_path = resp.data.get("url", f"/d/{uid}")
    full_url = f"{grafana_url}{dashboard_path}"

    logger.info("Provisioned dashboard %s → %s", uid, full_url)
    return ProvisioningResult(
        success=True,
        uid=uid,
        dashboard_url=full_url,
        details={
            "version": resp.data.get("version"),
            "status_code": resp.status_code,
        },
    )


def deprovision_dashboard(
    uid: str,
    client: GrafanaClient,
) -> ProvisioningResult:
    """Delete a dashboard from Grafana.  404 is treated as success.

    Args:
        uid: Dashboard UID to delete.
        client: Authenticated GrafanaClient instance.

    Returns:
        ProvisioningResult (success=True if deleted or already absent).
    """
    resp: GrafanaResponse = client.delete_dashboard(uid)

    if resp.success:
        logger.info("Deleted dashboard %s from Grafana", uid)
        return ProvisioningResult(success=True, uid=uid)

    # 404 = already gone — treat as success
    if resp.status_code == 404:
        logger.info("Dashboard %s not found in Grafana (already deleted)", uid)
        return ProvisioningResult(success=True, uid=uid)

    logger.warning("Failed to delete dashboard %s: %s", uid, resp.error)
    return ProvisioningResult(
        success=False,
        uid=uid,
        error=resp.error,
        details={"status_code": resp.status_code},
    )


def delete_local_artifacts(
    uid: str,
    output_dir: Optional[Path] = None,
    remove_source: bool = False,
    libsonnet_dir: Optional[Path] = None,
    manifest_path: Optional[Path] = None,
) -> Dict[str, bool]:
    """Delete local dashboard files.

    Args:
        uid: Dashboard UID (used to derive filenames).
        output_dir: Directory containing {uid}.json.
        remove_source: Also delete the .libsonnet source file.
        libsonnet_dir: Directory containing the .libsonnet file.
        manifest_path: Path to manifest YAML to remove the dashboard ref from.

    Returns:
        Dict mapping artifact names to whether they were deleted.
    """
    results: Dict[str, bool] = {}

    # JSON artifact
    resolved_dir = output_dir or Path(_DEFAULT_OUTPUT_DIR)
    json_path = resolved_dir / f"{uid}.json"
    results["json"] = _safe_unlink(json_path)

    # Libsonnet source
    if remove_source and libsonnet_dir is not None:
        name = uid.replace("cc-startd8-", "").replace("cc-", "").replace("-", "_")
        libsonnet_path = libsonnet_dir / f"{name}.libsonnet"
        results["libsonnet"] = _safe_unlink(libsonnet_path)

    # Manifest reference
    if manifest_path is not None:
        results["manifest_ref"] = _remove_dashboard_ref_from_manifest(uid, manifest_path)

    return results


def _safe_unlink(path: Path) -> bool:
    """Delete a file if it exists; return True if deleted."""
    try:
        if path.is_file():
            path.unlink()
            logger.info("Deleted %s", path)
            return True
        logger.debug("File not found (skip): %s", path)
        return False
    except OSError as exc:
        logger.warning("Failed to delete %s: %s", path, exc)
        return False


def _remove_dashboard_ref_from_manifest(uid: str, manifest_path: Path) -> bool:
    """Remove a dashboard entry from a YAML manifest file.

    Minimal implementation — Phase 3 will supersede with full manifest management.
    Expects the manifest to have a top-level ``dashboards`` list of dicts with ``uid`` keys.
    """
    try:
        if not manifest_path.is_file():
            return False

        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return False

        dashboards = data.get("dashboards")
        if not isinstance(dashboards, list):
            return False

        original_len = len(dashboards)
        data["dashboards"] = [d for d in dashboards if d.get("uid") != uid]

        if len(data["dashboards"]) == original_len:
            return False  # uid not found

        manifest_path.write_text(
            yaml.dump(data, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        logger.info("Removed dashboard %s from manifest %s", uid, manifest_path)
        return True
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("Failed to update manifest %s: %s", manifest_path, exc)
        return False
