# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Spec resolution, taxonomy classification, and onboarding/manifest loaders.

Extracted verbatim from ``artifact_generator.py`` (Tier-2 refactor, step 2).
"""

import json  # noqa: F401
import logging
import re  # noqa: F401
from datetime import datetime, timezone  # noqa: F401
from pathlib import Path  # noqa: F401
from typing import Any, Dict, List, Optional, Set, Tuple  # noqa: F401

import yaml  # noqa: F401

from .taxonomy_enums import Category, Orientation, RouteState  # noqa: F401
from .artifact_generator_models import *  # noqa: F401,F403

try:
    from startd8.logging_config import get_logger

    logger = get_logger(__name__)
except ImportError:  # pragma: no cover
    logger = logging.getLogger(__name__)


_ARTIFACT_TYPE_REGISTRY: Dict[str, ArtifactTypeSpec] = {
    spec.declared_type: spec
    for spec in [
        # Triplet — always produced (no declaration gate). runtime != declared
        # for the first two (the contract names differ from the generator labels).
        ArtifactTypeSpec("prometheus_rule", "alert_rule", Category.SERVICE.value, Orientation.BRIDGE.value, False, 10),
        ArtifactTypeSpec("dashboard", "dashboard_spec", Category.SERVICE.value, Orientation.HUMAN.value, False, 20),
        ArtifactTypeSpec("slo_definition", "slo_definition", Category.SERVICE.value, Orientation.SYSTEM.value, False, 30),
        # Extended per-service generators — produced only when declared.
        ArtifactTypeSpec("service_monitor", "service_monitor", Category.SERVICE.value, Orientation.SYSTEM.value, True, 40),
        ArtifactTypeSpec("notification_policy", "notification_policy", Category.SERVICE.value, Orientation.BRIDGE.value, True, 50),
        ArtifactTypeSpec("loki_rule", "loki_rule", Category.SERVICE.value, Orientation.BRIDGE.value, True, 60),
        ArtifactTypeSpec("runbook", "runbook", Category.SERVICE.value, Orientation.HUMAN.value, True, 70),
        # Project-level artifacts (consumers — emitted after per-service rows).
        ArtifactTypeSpec("capability_index", "capability_index", Category.PROJECT.value, Orientation.HUMAN.value, False, 80),
        ArtifactTypeSpec("onboarding_portal", "portal", Category.PROJECT.value, Orientation.HUMAN.value, True, 90),
    ]
}


_RUNTIME_TO_DECLARED: Dict[str, str] = {
    **{spec.runtime_type: spec.declared_type for spec in _ARTIFACT_TYPE_REGISTRY.values()},
    "dashboard": "dashboard",  # rendered Grafana JSON shares the dashboard contract
}


def resolve_artifact_spec(label: str) -> Optional[ArtifactTypeSpec]:
    """Resolve a declared OR runtime artifact label to its registry row (REQ-OAT-070a)."""
    if label in _ARTIFACT_TYPE_REGISTRY:
        return _ARTIFACT_TYPE_REGISTRY[label]
    declared = _RUNTIME_TO_DECLARED.get(label)
    if declared is not None:
        return _ARTIFACT_TYPE_REGISTRY.get(declared)
    return None


def _stamp_taxonomy(result: ArtifactResult) -> ArtifactResult:
    """Centrally assign category/orientation/declared_type/runtime_type from the
    registry (REQ-OAT-023 — assigned once here, not per call site). Unknown labels
    leave the axes unset (logged once by the caller) rather than guessing."""
    spec = resolve_artifact_spec(result.artifact_type)
    if spec is not None:
        result.category = spec.category
        result.orientation = spec.orientation
        result.declared_type = spec.declared_type
        result.runtime_type = result.artifact_type
    return result


def _infer_metric_category(metric_name: str) -> str:
    """Name-pattern fallback for a metric's taxonomy category (REQ-OAT-040).

    FALLBACK ONLY — used when onboarding metadata does not declare ``category``
    (REQ-OAT-024). Callers MUST record the result as ``inferred`` so the upstream
    declaration gap stays visible rather than silently authoritative. Returns ""
    when no pattern matches.
    """
    n = metric_name.lower()
    if n.startswith("contextcore"):
        return Category.PROJECT.value
    if n.startswith("startd8"):
        return Category.AI_AGENT.value
    if n.startswith(("http", "rpc")) or ".server." in n or ".client." in n:
        return Category.SERVICE.value
    return ""


def classify_route_state(
    metric_name: str,
    *,
    sdk_emitted: bool = False,
    is_convention: bool = False,
    declared: str = "",
) -> RouteState:
    """Classify a metric's emit-vs-cede provenance (REQ-OBS-SHARED-004).

    Routing is by explicit provenance, NOT inferred from category. The
    ``contextcore`` prefix wins over ``sdk_emitted`` so STALE ``contextcore_task_*``
    entries still listed in onboarding metadata classify as ``contextcore_owned``
    on read (REQ-OBS-SHARED-004 stale-metadata clause), never mis-attributed to
    the SDK. A declared route_state (when upstream provides one) is honored first.
    """
    if declared:
        try:
            return RouteState(declared)
        except ValueError:
            pass
    if metric_name.lower().startswith("contextcore"):
        return RouteState.CONTEXTCORE_OWNED
    if sdk_emitted:
        return RouteState.SDK_EMITTED
    if is_convention:
        return RouteState.EXTERNAL_CONVENTION
    # An otherwise-unclassifiable, externally-observed metric (no SDK meter site).
    return RouteState.EXTERNAL_CONVENTION


_ROUTE_STATE_STATUS_TEXT: Dict[RouteState, str] = {
    RouteState.SDK_EMITTED: "SDK-emitted (in-process) — produced",
    RouteState.CONTEXTCORE_OWNED: "ContextCore-owned — skipped (owned elsewhere)",
    RouteState.DECLARED_UNIMPLEMENTED: "declared, no generator yet — skipped",
    RouteState.EXTERNAL_CONVENTION: "externally-observed convention metric — produced",
}


def classify_route_states(services: List[ServiceHints]) -> List[Dict[str, Any]]:
    """Build per-metric route_state report rows (REQ-OBS-SHARED-004).

    Walks every metric in the onboarding hints (declared + convention),
    classifies provenance + taxonomy category, and records whether the category
    was declared upstream or ``inferred`` (REQ-OAT-024). Each row carries a
    user-visible status string (R3-F6). Deduplicated by metric name.
    """
    rows: List[Dict[str, Any]] = []
    seen: Set[str] = set()

    def _row(m: ConventionMetric, *, sdk_emitted: bool, is_convention: bool) -> Dict[str, Any]:
        rs = classify_route_state(
            m.name, sdk_emitted=sdk_emitted, is_convention=is_convention,
            declared=m.route_state,
        )
        declared_cat = bool(m.category)
        cat = m.category or _infer_metric_category(m.name)
        if not cat and is_convention:
            cat = Category.SERVICE.value
        row: Dict[str, Any] = {
            "name": m.name,
            "category": cat,
            "route_state": rs.value,
            "status": _ROUTE_STATE_STATUS_TEXT[rs],
            "classification_source": "declared" if declared_cat else "inferred",
        }
        if rs is RouteState.CONTEXTCORE_OWNED:
            row["owner"] = "contextcore"
        return row

    for svc in services:
        for m in svc.declared_metrics:
            if m.name in seen:
                continue
            seen.add(m.name)
            rows.append(_row(m, sdk_emitted=True, is_convention=False))
        for m in svc.convention_metrics:
            if m.name in seen:
                continue
            seen.add(m.name)
            rows.append(_row(m, sdk_emitted=False, is_convention=True))

    rows.sort(key=lambda r: r["name"])
    return rows


def load_onboarding_metadata(path: Path) -> Dict[str, Any]:
    """Load onboarding-metadata.json and return raw dict.

    Raises FileNotFoundError if path does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"Onboarding metadata not found: {path}")
    with open(path, "r") as f:
        data = json.load(f)
    logger.info("Loaded onboarding metadata from %s (%d top-level keys)", path, len(data))
    return data


_REQ_ID_PATTERN = re.compile(r"^req[a-z]{2,}\d+")


_RUN_ID_PATTERN = re.compile(r"/run-\d+|^run-\d+")


_NON_SERVICE_NAMES = frozenset({
    "protos", "proto", "shared", "common", "lib", "libs",
    "docs", "scripts", "tools", "config", "configs",
})


def _is_non_service_entry(
    svc_id: str,
    hint: Dict[str, Any],
    metadata: Dict[str, Any],
) -> bool:
    """Check if an instrumentation_hints entry is not a real runtime service.

    Filters requirement IDs, run IDs, project-level names, and known
    non-service directories (REQ-KZ-OBS-103).
    """
    # Requirement ID pattern (reqcdpobs001..., reqpms002...)
    if _REQ_ID_PATTERN.match(svc_id):
        return True

    # Run ID pattern (online-boutique/run-093-...)
    if _RUN_ID_PATTERN.search(svc_id):
        return True

    # Project-level name match
    project_id = metadata.get("project_id", "")
    if project_id and svc_id == project_id:
        return True
    # Also match the project name portion of composite IDs
    project_name = project_id.split("/")[0] if "/" in str(project_id) else ""
    if project_name and svc_id == project_name:
        return True

    # Known non-service directory names — check both exact match and as
    # path segments so compound IDs like "online-boutique/protos" are caught.
    svc_parts = {p.lower() for p in svc_id.replace("\\", "/").split("/")}
    if svc_parts & _NON_SERVICE_NAMES:
        return True

    # Entries ending in common non-service suffixes
    svc_lower = svc_id.lower()
    if svc_lower.endswith(("-demo", "-docs", "-guidance", "-overview")):
        return True

    # Multi-word names that look like document titles, not service IDs
    # (services are typically single words or hyphenated: cartservice, email-service)
    if "guidance" in svc_lower or "objectives" in svc_lower:
        return True

    return False


def _parse_metric_set(raw: Any) -> List[ConventionMetric]:
    """Parse a list of raw metric dicts into ConventionMetric objects.

    Shared by both ``convention_based`` and ``manifest_declared`` metric sets,
    which carry the same ``{name, type, source}`` schema. Entries without a
    name are dropped. Non-list input yields an empty list.
    """
    if not isinstance(raw, list):
        return []
    return [
        ConventionMetric(
            name=m.get("name", ""),
            type=m.get("type", ""),
            source=m.get("source", ""),
            category=m.get("category", ""),
            route_state=m.get("route_state", ""),
        )
        for m in raw
        if isinstance(m, dict) and m.get("name")
    ]


def extract_service_hints(metadata: Dict[str, Any]) -> List[ServiceHints]:
    """Extract per-service instrumentation hints from onboarding metadata.

    Returns empty list if instrumentation_hints key is absent (REQ-UOM-070).
    Skips services with no transport field (REQ-UOM-071).
    Skips non-service entries (REQ-KZ-OBS-103).
    """
    raw_hints = metadata.get("instrumentation_hints")
    if not raw_hints:
        logger.warning(
            "No instrumentation_hints in onboarding metadata; "
            "producing zero artifacts"
        )
        return []

    services: List[ServiceHints] = []
    skipped_non_service = 0
    for svc_id, hint in raw_hints.items():
        # REQ-KZ-OBS-103: Filter non-service entries
        if _is_non_service_entry(svc_id, hint, metadata):
            logger.info("Skipping non-service entry: %s", svc_id)
            skipped_non_service += 1
            continue

        transport = hint.get("transport")
        if not transport:
            logger.warning("Service %s has no transport field; skipping", svc_id)
            continue

        metrics = hint.get("metrics", {})
        convention_metrics = _parse_metric_set(metrics.get("convention_based", []))
        # Closure 1 / Gap 1: also consume manifest_declared domain metrics so
        # artifacts describe what *this* service does, not just generic HTTP.
        declared_metrics = _parse_metric_set(metrics.get("manifest_declared", []))

        services.append(
            ServiceHints(
                service_id=svc_id,
                transport=transport,
                language=hint.get("language"),
                detected_databases=hint.get("detected_databases", []),
                convention_metrics=convention_metrics,
                declared_metrics=declared_metrics,
            )
        )

    logger.info(
        "Extracted hints for %d services (%d skipped)",
        len(services),
        len(raw_hints) - len(services),
    )
    return services


def load_business_context(
    manifest_path: Optional[Path],
    metadata: Dict[str, Any],
) -> BusinessContext:
    """Extract business context from .contextcore.yaml or onboarding metadata.

    Prefers manifest for direct reads; falls back to metadata fields.
    All fields are optional — defaults applied with log warnings (REQ-UOM-072).
    """
    ctx = BusinessContext()

    # Try manifest first
    manifest: Dict[str, Any] = {}
    if manifest_path and manifest_path.exists():
        with open(manifest_path, "r") as f:
            manifest = yaml.safe_load(f) or {}
        logger.info("Loaded business context from manifest: %s", manifest_path)

    spec = manifest.get("spec", {})
    meta = manifest.get("metadata", {})
    business = spec.get("business", {})
    requirements = spec.get("requirements", {})
    observability = spec.get("observability", {})
    project = spec.get("project", {})

    ctx.project_id = project.get("id") or metadata.get("project_id")
    ctx.project_name = project.get("name")
    ctx.criticality = business.get("criticality", "medium")
    ctx.owner = business.get("owner")
    ctx.dashboard_placement = observability.get("dashboardPlacement", "standard")

    # Delivery fields (FR-CONS-1) consumed by notification_policy / service_monitor /
    # loki_rule / runbook in place of hardcoded placeholders.
    ctx.alert_channels = list(observability.get("alertChannels") or [])
    ctx.owners = list(meta.get("owners") or [])
    ctx.metrics_interval = observability.get("metricsInterval")
    ctx.targets = list(spec.get("targets") or [])
    ctx.prometheus_datasource = observability.get("prometheusDatasource")
    ctx.runbook_base = observability.get("runbookBase")

    # SLO thresholds from requirements
    ctx.availability = requirements.get("availability")
    ctx.latency_p99 = requirements.get("latencyP99")
    ctx.throughput = requirements.get("throughput")
    ctx.error_budget = requirements.get("errorBudget")

    # SLO window from strategy objectives if available
    strategy = manifest.get("strategy", {})
    for obj in strategy.get("objectives", []):
        for kr in obj.get("keyResults", []):
            if kr.get("window"):
                ctx.slo_window = kr["window"]
                break

    # Log defaults
    if not ctx.availability:
        logger.info("No availability threshold in manifest; will use default (99%%)")
    if not ctx.latency_p99:
        logger.info("No latencyP99 in manifest; will use default (500ms)")

    return ctx
