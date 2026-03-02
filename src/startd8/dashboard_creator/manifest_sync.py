"""
Manifest sync — create/update DashboardRef entries in ObservabilityManifest (DC-201).
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from startd8.dashboard_creator.models import DashboardSpec
from startd8.logging_config import get_logger
from startd8.observability.manifest import DashboardRef

logger = get_logger(__name__)

# Reuse the same regex from generator.py for consistency
_METRIC_REF = re.compile(r"\$\{metrics\.(\w+)\}")


def extract_metrics_used(spec: DashboardSpec) -> List[str]:
    """Scan all panel/target/variable expressions for ``${metrics.*}`` references.

    Returns a sorted, deduplicated list of metric names.
    """
    metrics: set[str] = set()

    for panel in spec.panels:
        if panel.expr:
            metrics.update(_METRIC_REF.findall(panel.expr))
        if panel.query:
            metrics.update(_METRIC_REF.findall(panel.query))
        if panel.targets:
            for target in panel.targets:
                if target.expr:
                    metrics.update(_METRIC_REF.findall(target.expr))
                if target.query:
                    metrics.update(_METRIC_REF.findall(target.query))

    for var in spec.variables:
        if var.metric:
            metrics.update(_METRIC_REF.findall(var.metric))
        if var.query:
            metrics.update(_METRIC_REF.findall(var.query))

    return sorted(metrics)


def build_dashboard_ref(
    spec: DashboardSpec,
    json_path: Path,
) -> DashboardRef:
    """Build a ``DashboardRef`` from a spec and its output path.

    Args:
        spec: The dashboard spec (after UID enforcement).
        json_path: Path to the compiled JSON file.

    Returns:
        A populated DashboardRef.
    """
    datasources = sorted(spec.datasources.keys()) if spec.datasources else []
    metrics_used = extract_metrics_used(spec)

    return DashboardRef(
        uid=spec.uid or "",
        title=spec.title,
        file_path=str(json_path),
        datasources=datasources,
        metrics_used=metrics_used,
        tags=list(spec.tags),
    )


def sync_manifest(
    spec: DashboardSpec,
    json_path: Path,
    manifest_path: Optional[Path] = None,
) -> bool:
    """DC-201: Upsert a ``DashboardRef`` into the observability manifest.

    - Upserts by UID (no duplicates).
    - Skipped when ``manifest_path`` is None or the file doesn't exist.
    - Tags from the spec are propagated to the DashboardRef.

    Args:
        spec: The dashboard spec (after UID enforcement and config merge).
        json_path: Path to the compiled JSON file.
        manifest_path: Path to ``observability-manifest.yaml``.
            Defaults to None (skip).

    Returns:
        True if the manifest was modified, False otherwise.
    """
    if manifest_path is None:
        return False

    if not manifest_path.is_file():
        logger.debug("Manifest not found at %s — skipping sync", manifest_path)
        return False

    try:
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("Failed to read manifest %s: %s", manifest_path, exc)
        return False

    if not isinstance(data, dict):
        logger.warning("Manifest %s is not a dict — skipping sync", manifest_path)
        return False

    dashboards: List[Dict[str, Any]] = data.get("dashboards", [])
    if not isinstance(dashboards, list):
        dashboards = []

    ref = build_dashboard_ref(spec, json_path)
    ref_dict = ref.to_dict()
    uid = ref.uid

    # Upsert: replace existing entry with same UID, or append
    found = False
    for i, existing in enumerate(dashboards):
        if existing.get("uid") == uid:
            dashboards[i] = ref_dict
            found = True
            break

    if not found:
        dashboards.append(ref_dict)

    data["dashboards"] = dashboards

    try:
        manifest_path.write_text(
            yaml.dump(data, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Failed to write manifest %s: %s", manifest_path, exc)
        return False

    logger.info(
        "%s dashboard %s in manifest",
        "Updated" if found else "Added",
        uid,
    )
    return True
