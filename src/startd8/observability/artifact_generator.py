"""
Generate observability artifacts (alert rules, dashboard specs, SLO definitions)
from ContextCore onboarding metadata and manifest business context.

Reads onboarding-metadata.json (from cap-dev-pipe Stage 4 EXPORT) and
.contextcore.yaml, then produces per-service artifact files.

See docs/design/UNIFIED_OBSERVABILITY_MANIFEST_REQUIREMENTS.md for design.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

from .taxonomy_enums import Category, Orientation, RouteState

# Data models live in artifact_generator_models.py (Tier-2 step 1); re-exported
# here so existing `from ...artifact_generator import ArtifactResult` keeps working.
from .artifact_generator_models import *  # noqa: F401,F403

# Context + generator clusters extracted to sibling modules (Tier-2 step 2);
# re-exported so the orchestrator and external consumers keep their import paths.
from .artifact_generator_context import (  # noqa: F401
    _ARTIFACT_TYPE_REGISTRY,
    _NON_SERVICE_NAMES,
    _REQ_ID_PATTERN,
    _ROUTE_STATE_STATUS_TEXT,
    _RUNTIME_TO_DECLARED,
    _RUN_ID_PATTERN,
    _infer_metric_category,
    _is_non_service_entry,
    _parse_metric_set,
    _stamp_taxonomy,
    classify_route_state,
    classify_route_states,
    extract_service_hints,
    load_business_context,
    load_onboarding_metadata,
    resolve_artifact_spec,
)
from .artifact_generator_generators import (  # noqa: F401
    _ARTIFACT_TYPE_TO_CATEGORY,
    _CAPABILITY_INDEX_EXCLUDE,
    _CRITICALITY_TO_SEVERITY,
    _DEFAULT_THRESHOLDS,
    _INSTRUMENT_TO_PANEL,
    _INSTRUMENT_TO_QUERY,
    _METRIC_UNITS,
    _add_database_panels,
    _add_domain_panels,
    _alert_name,
    _assign_gridpos,
    _derivation_comment,
    _domain_alert_todo_block,
    _domain_metric_type,
    _domain_panel_group,
    _domain_query,
    _domain_unit,
    _ensure_red_coverage,
    _error_filter_for_protocol,
    _metric_unit,
    _panel_group,
    _panel_title,
    _parse_availability_to_fraction,
    _parse_duration_to_seconds,
    _pascal,
    _prom_name,
    _resolve_threshold,
    _severity_for,
    generate_alert_rules,
    generate_capability_index,
    generate_dashboard_spec,
    generate_loki_rule,
    generate_notification_policy,
    generate_runbook,
    generate_service_monitor,
    generate_slo_definitions,
)

try:
    from startd8.logging_config import get_logger

    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


# Declared onboarding artifact_types this generator actually produces, keyed by
# the declared type name. prometheus_rule ← alert_rule output; dashboard ←
# Grafana JSON (Gap 4); slo_definition ← slo output; the remaining five are
# native extended generators (Closure 3B), produced when declared. Any declared
# type NOT in this set is still recorded as an honest, explicit skip (Gap 2).
_IMPLEMENTED_ARTIFACT_TYPES = frozenset({
    "dashboard",
    "prometheus_rule",
    "slo_definition",
    "service_monitor",
    "notification_policy",
    "loki_rule",
    "runbook",
    "capability_index",
})


# ---------------------------------------------------------------------------
# Single type-keyed artifact registry (REQ-OAT-070a / REQ-OAT-023 keystone)
# ---------------------------------------------------------------------------
#
# ONE place to add an artifact type: a declarative row, never a new dispatch or
# validation branch (REQ-OAT-070). Keyed by the *declared* (contract/onboarding)
# type; each row projects category (five-category taxonomy) + orientation
# (human|system|bridge) + the internal runtime label + requires_declaration +
# order (producers before consumers, REQ-OAT-070a R3-F2). The taxonomy `category`
# here is INDEPENDENT of the legacy 4-value `_ARTIFACT_TYPE_TO_CATEGORY`
# (observe/integration/action/reference) below, which feeds the capability-index
# schema only — do not conflate (REQ-OAT-023 correction, CRP R2-F1).


# Runtime label -> declared type, so records stamped from a generator's runtime
# label resolve to their declared identity. The rendered Grafana JSON (runtime
# "dashboard", _convert_dashboards_to_grafana_json) shares declared "dashboard".

# The triplet is produced UNCONDITIONALLY (no declaration / cede gate). Marking one
# of these owned_elsewhere is contradictory — production wins (see
# _record_unimplemented_artifact_types), so coverage never excludes a produced type.
_ALWAYS_PRODUCED_DECLARED_TYPES = frozenset({"prometheus_rule", "dashboard", "slo_definition"})


# ---------------------------------------------------------------------------
# route_state classification (REQ-OBS-SHARED-004 / REQ-OAT-040 / REQ-OAT-024)
# ---------------------------------------------------------------------------


# Quality-report composite blend (Run-007 Findings 1 & 3): structural = mean of
# all scored artifacts; coverage = mean(dashboarded, alerted).
_COMPOSITE_STRUCTURAL_WEIGHT = 0.7
_COMPOSITE_COVERAGE_WEIGHT = 0.3

# OTel instrument type → Grafana panel type

# OTel instrument type → PromQL query template

# Metric unit hints by name pattern


# ---------------------------------------------------------------------------
# Phase 1: Input loading
# ---------------------------------------------------------------------------


# Known non-service directory names that may appear in instrumentation_hints


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Phase 2: Alert rule generation
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Phase 3: Dashboard spec generation
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Domain (manifest_declared) metric helpers — Closure 1 / Gap 1
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Phase 4: SLO definition generation
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Phase 4c: Extended artifact generators (Closure 3B / Gap 2)
#
# Native generators for the declared artifact types beyond the RED triplet.
# Contract-driven: only produced when the onboarding metadata declares the type
# in artifact_types. Each is derived from ServiceHints + BusinessContext, so
# they carry the same per-service provenance as the triplet.
# ---------------------------------------------------------------------------


# Maps a generated artifact type to a capability-index category (Run-007 Finding 2).

# Artifact types that are intermediates/self and not surfaced as capabilities.


# Declared-type-name → (per-service generator, output_prefix). Contract-driven:
# only generated when the onboarding metadata declares the type (Closure 3B).
_EXTENDED_PER_SERVICE_GENERATORS = {
    "service_monitor": (generate_service_monitor, "service-monitors"),
    "notification_policy": (generate_notification_policy, "notifications"),
    "loki_rule": (generate_loki_rule, "loki-rules"),
    "runbook": (generate_runbook, "runbooks"),
}


# ---------------------------------------------------------------------------
# Phase 4.5: Validate-with-autofix (REQ-KZ-OBS-700 + 710)
# ---------------------------------------------------------------------------


def _repair_and_validate(
    result: ArtifactResult,
    business: BusinessContext,
    transport: Optional[str] = None,
) -> ArtifactResult:
    """Apply autofix repairs, validate, compute score. Modifies result in-place.

    Runs after each generate_*() call, before disk write. Attaches
    quality dict to ArtifactResult for postmortem consumption.
    """
    if result.status != "generated" or not result.content:
        return result

    try:
        from startd8.validators.observability_artifact_checks import (
            validate_dashboard,
            validate_alerts,
            validate_slo,
        )
    except ImportError:
        return result  # validators not available — degrade gracefully

    avail = None
    if business.availability:
        try:
            avail = float(business.availability)
        except (ValueError, TypeError):
            pass

    vr = None

    if result.artifact_type == "dashboard_spec":
        vr = validate_dashboard(
            result.content, result.output_path, autofix=True,
            service_id=result.service_id, transport=transport,
        )
        # If gridPos was injected, update content with repaired YAML
        if vr.repairs_applied:
            try:
                repaired = yaml.safe_load(result.content)
                from startd8.validators.observability_artifact_checks import repair_gridpos
                repaired, _ = repair_gridpos(repaired)
                result.content = yaml.dump(repaired, default_flow_style=False, sort_keys=False)
            except Exception:
                pass

    elif result.artifact_type == "alert_rule":
        vr = validate_alerts(
            result.content, result.output_path,
            manifest_availability=avail,
            service_id=result.service_id, transport=transport,
        )

    elif result.artifact_type == "slo_definition":
        vr = validate_slo(
            result.content, result.output_path,
            manifest_availability=avail,
            autofix=True,
            service_id=result.service_id, transport=transport,
        )
        # If SLO target was repaired, update content
        if vr.repairs_applied:
            try:
                from startd8.validators.observability_artifact_checks import repair_slo_target
                repaired = yaml.safe_load(result.content)
                repaired, _ = repair_slo_target(repaired, avail)
                result.content = yaml.dump(repaired, default_flow_style=False, sort_keys=False)
            except Exception:
                pass

    if vr is not None:
        result.quality = {
            "score": round(vr.score, 4),
            "checks_passed": vr.checks_passed,
            "checks_total": vr.checks_total,
            "issues": [
                {"check": i.check, "severity": i.severity, "message": i.message}
                for i in vr.issues
            ],
            "repairs_applied": vr.repairs_applied,
        }
        # Log quality summary
        if vr.issues:
            issue_summary = ", ".join(
                f"{i.check}({i.severity[0]})" for i in vr.issues[:3]
            )
            logger.info(
                "Artifact quality: %s %s score=%.0f%% issues=[%s]",
                result.artifact_type, result.service_id,
                vr.score * 100, issue_summary,
            )

    return result


def _generate_one(
    gen_fn: Any,
    service: ServiceHints,
    business: BusinessContext,
    artifact_type: str,
    output_prefix: str,
) -> ArtifactResult:
    """Generate, validate, and score a single artifact. Catches exceptions.

    Central taxonomy assignment site (REQ-OAT-023): every result is stamped with
    category/orientation/declared_type/runtime_type from the registry here, so the
    ~7 generator functions never hand-set those axes.
    """
    try:
        result = gen_fn(service, business)
        result = _repair_and_validate(result, business, transport=service.transport)
        return _stamp_taxonomy(result)
    except Exception:
        logger.exception("%s generation failed for %s", artifact_type, service.service_id)
        return _stamp_taxonomy(ArtifactResult(
            artifact_type=artifact_type,
            service_id=service.service_id,
            output_path=f"{output_prefix}/{service.service_id}-{output_prefix}.yaml",
            status="error",
            error_message="Generation raised exception",
        ))


# ---------------------------------------------------------------------------
# Phase 4b: Portal artifact generation (REQ-OBP-103)
# ---------------------------------------------------------------------------


def _generate_portal_artifact(
    business: BusinessContext,
    services: List[ServiceHints],
    report: GenerationReport,
    metadata: Dict[str, Any],
    output_dir: Path,
    *,
    persona: str = "operator",
    provision_url: Optional[str] = None,
    dry_run: bool = False,
) -> Optional[ArtifactResult]:
    """Generate an onboarding portal via DashboardCreatorWorkflow.

    Builds a DashboardSpec dict from pipeline context, then routes through
    the Jsonnet → Grafana JSON pipeline for compilation and optional provisioning.

    Returns ArtifactResult or None on failure.
    """
    try:
        from startd8.observability.portal_spec_builder import build_portal_spec
    except ImportError:
        logger.warning("portal_spec_builder not available; skipping portal generation")
        return None

    project_id = business.project_id or "unknown"

    try:
        spec_dict = build_portal_spec(
            business, services, report, metadata, persona=persona,
        )
    except Exception:
        logger.exception("Portal spec build failed for %s", project_id)
        return ArtifactResult(
            artifact_type="portal",
            service_id=project_id,
            output_path=f"portal/{project_id}-portal.json",
            status="error",
            error_message="Portal spec build raised exception",
        )

    # Route through DashboardCreatorWorkflow
    portal_output_dir = output_dir / "portal"
    portal_output_dir.mkdir(parents=True, exist_ok=True)

    try:
        from startd8.dashboard_creator.workflow import DashboardCreatorWorkflow

        workflow = DashboardCreatorWorkflow()
        config: Dict[str, Any] = {
            "spec": spec_dict,
            "output_dir": str(portal_output_dir),
            "dry_run": dry_run,
        }
        if provision_url:
            config["provision"] = True
            config["grafana_url"] = provision_url

        result = workflow.run(config)

        if result.success:
            uid = spec_dict.get("uid", f"portal-{project_id}")
            json_path = portal_output_dir / f"{uid}.json"
            content = ""
            if json_path.is_file():
                content = json_path.read_text()

            logger.info("Portal generated: %s", json_path)
            return ArtifactResult(
                artifact_type="portal",
                service_id=project_id,
                output_path=f"portal/{uid}.json",
                status="generated",
                content=content,
            )
        else:
            error_msg = result.output.get("error", "Unknown workflow error") if isinstance(result.output, dict) else str(result.output)
            logger.error("Portal workflow failed: %s", error_msg)
            return ArtifactResult(
                artifact_type="portal",
                service_id=project_id,
                output_path=f"portal/{project_id}-portal.json",
                status="error",
                error_message=str(error_msg),
            )
    except Exception:
        logger.exception("Portal generation failed for %s", project_id)
        return ArtifactResult(
            artifact_type="portal",
            service_id=project_id,
            output_path=f"portal/{project_id}-portal.json",
            status="error",
            error_message="DashboardCreatorWorkflow raised exception",
        )


# ---------------------------------------------------------------------------
# Phase 5: Orchestration + index file
# ---------------------------------------------------------------------------


def generate_observability_artifacts(
    onboarding_metadata_path: Path,
    output_dir: Path,
    manifest_path: Optional[Path] = None,
    dry_run: bool = False,
    portal: bool = False,
    portal_persona: str = "operator",
    portal_provision_url: Optional[str] = None,
    dashboard_provision_url: Optional[str] = None,
    observability_yaml_path: Optional[Path] = None,
) -> GenerationReport:
    """Top-level orchestrator.

    1. Load inputs (onboarding metadata + business context)
    2. Extract per-service hints
    3. For each service: generate alerts, dashboard spec, SLO definitions
    4. Write files and index
    5. Return generation report
    """
    metadata = load_onboarding_metadata(onboarding_metadata_path)
    services = extract_service_hints(metadata)
    business = load_business_context(manifest_path, metadata)

    report = GenerationReport(
        project_id=business.project_id,
        generated_at=_utc_now_iso(),
    )

    if not services:
        logger.warning("No services found; producing zero artifacts")
        return report

    # Per-service artifact generators — adding a new type is a tuple, not a code block
    _GENERATORS = [
        (generate_alert_rules, "alert_rule", "alerts"),
        (generate_dashboard_spec, "dashboard_spec", "dashboards"),
        (generate_slo_definitions, "slo_definition", "slos"),
    ]

    for service in services:
        for gen_fn, artifact_type, output_prefix in _GENERATORS:
            report.artifacts.append(
                _generate_one(gen_fn, service, business, artifact_type, output_prefix)
            )

    report.services_processed = len(services)
    report.services_skipped = len(
        [s for s in services if not s.convention_metrics]
    )

    report.declared_artifact_types = _declared_artifact_types(metadata)

    # REQ-OBS-SHARED-004: classify every metric's emit-vs-cede provenance up front,
    # by explicit route_state (not category). Surfaced in the index summary so the
    # report shows who emits / why skipped, with declared-vs-inferred visibility.
    report.route_states = classify_route_states(services)

    # REQ-OAT-052: declared types ceded to another component (e.g. capability_index
    # owned by onboarding/ContextCore). Read from explicit metadata, not guessed.
    owned_elsewhere = _owned_elsewhere_types(metadata)

    # Closure 3B: native extended generators, produced only for declared types that
    # this SDK actually owns (ceded types are recorded as owned_elsewhere skips below).
    declared = set(report.declared_artifact_types)
    for atype, (gen_fn, output_prefix) in _EXTENDED_PER_SERVICE_GENERATORS.items():
        if atype not in declared or atype in owned_elsewhere:
            continue
        for service in services:
            report.artifacts.append(
                _generate_one(gen_fn, service, business, atype, output_prefix)
            )

    # Closure 3A / Gap 2 + REQ-OAT-052: record declared-but-unproduced types as
    # explicit skips carrying skip_reason (owned_elsewhere | unimplemented) + owner,
    # so coverage reporting is honest, not silently partial.
    _record_unimplemented_artifact_types(report, owned_elsewhere)

    # Gap 4 / Closure 4A: render dashboard specs to deployable Grafana JSON at the
    # contracted grafana/dashboards/{service}-dashboard.json path. Runs in dry_run
    # too (side-effect-free; renders via a temp dir) so drift detection stays
    # consistent — only the disk write below is gated on dry_run. Provisioning,
    # when requested, only happens on a real (non-dry-run) render.
    _convert_dashboards_to_grafana_json(
        report, provision_url=None if dry_run else dashboard_provision_url
    )

    # Portal generation — after per-service artifacts (REQ-OBP-103a)
    if portal:
        portal_result = _generate_portal_artifact(
            business, services, report, metadata, output_dir,
            persona=portal_persona,
            provision_url=portal_provision_url,
            dry_run=dry_run,
        )
        if portal_result is not None:
            report.artifacts.append(portal_result)

    # M1 / FR-OAA-12: domain alert rules from observability.yaml. Declared thresholds become ACTIVE
    # rules — closing the gap the convention path leaves as `_domain_alert_todo_block` stubs. Strictly
    # additive + opt-in: an absent observability_yaml_path ⇒ no new artifact and RED output stays
    # byte-identical. The renderer is taxonomy-free; the _stamp_taxonomy pass below stamps the result.
    if observability_yaml_path is not None and Path(observability_yaml_path).exists():
        from .alert_renderer import render_domain_alert_rules
        from .spec import from_observability_yaml
        _obs = yaml.safe_load(Path(observability_yaml_path).read_text(encoding="utf-8")) or {}
        report.artifacts.append(
            render_domain_alert_rules(
                from_observability_yaml(_obs),
                project_id=business.project_id or "domain",
            )
        )

    # Closure 3B: project-level capability index runs last so its inventory
    # reflects every artifact produced this run (triplet + extended + dashboard
    # JSON + portal).
    if "capability_index" in declared and "capability_index" not in owned_elsewhere:
        try:
            report.artifacts.append(
                generate_capability_index(services, business, report)
            )
        except Exception:
            logger.exception("capability_index generation failed")

    # REQ-OAT-023 (keystone): stamp taxonomy axes on every artifact built OUTSIDE
    # _generate_one (rendered Grafana JSON, portal, capability_index) in one place,
    # so category/orientation/declared_type/runtime_type are universal. Idempotent;
    # records already stamped (status="generated"/"error" via _generate_one) are
    # left as-is. Skip records get route_state in _record_unimplemented (below).
    for _a in report.artifacts:
        if not _a.category:
            _stamp_taxonomy(_a)

    # Run-007 Finding 1: score the extended types + Grafana JSON against their
    # declared contracts so every generated artifact is scored, not just the triplet.
    _score_extended_artifacts(report, metadata.get("expected_output_contracts", {}))

    # REQ-OAT-050/061/062: orientation-aware annotation + bridge two-half breakdown.
    # After scoring (quality exists) and stamping (axes exist), before the report write.
    _apply_orientation_scoring(report)

    if not dry_run:
        # Gap 3 / Closure 2: expected metric set per service (declared + convention)
        # drives the semantic metric-coverage score in the quality report.
        service_metrics: Dict[str, Set[str]] = {
            s.service_id: {m.name for m in s.convention_metrics}
            | {m.name for m in s.declared_metrics}
            for s in services
        }
        _write_artifacts(report.artifacts, output_dir)
        _write_index(report, business, onboarding_metadata_path, output_dir)
        _write_quality_report(
            report.artifacts, output_dir, service_metrics=service_metrics
        )

    return report


def _declared_artifact_types(metadata: Dict[str, Any]) -> List[str]:
    """Extract the declared artifact_types from onboarding metadata (Closure 3A).

    Accepts either a dict (keyed by type name) or a list of type names.
    """
    decl = metadata.get("artifact_types")
    if isinstance(decl, dict):
        return sorted(decl.keys())
    if isinstance(decl, list):
        return sorted(str(t) for t in decl if t)
    return []


def _owned_elsewhere_types(metadata: Dict[str, Any]) -> Dict[str, str]:
    """Declared artifact types ceded to another component (REQ-OAT-011/052).

    Read from explicit onboarding metadata, NOT guessed (REQ-OAT-024): when
    ``artifact_types`` is a dict whose entry carries an ``owner`` (or a
    ``route_state`` of ``contextcore_owned``), that type is owned elsewhere and is
    excluded from the ``artifact_type_coverage`` denominator so a correct cede does
    not read as <1.0 coverage (REQ-OAT-052 R4-F2). Returns ``{declared_type: owner}``.
    """
    decl = metadata.get("artifact_types")
    owners: Dict[str, str] = {}
    if isinstance(decl, dict):
        for t, v in decl.items():
            if not isinstance(v, dict):
                continue
            owner = v.get("owner")
            if owner:
                owners[str(t)] = str(owner)
            elif v.get("route_state") == RouteState.CONTEXTCORE_OWNED.value:
                owners[str(t)] = "contextcore"
    return owners


def _coverage_by_category(counted: Set[str]) -> Dict[str, float]:
    """Per-category artifact-type coverage (REQ-OAT-052), over the post-cede
    denominator. Each declared type is bucketed by its registry taxonomy category;
    coverage is the produced fraction within the category."""
    by_cat: Dict[str, List[bool]] = {}
    for atype in counted:
        spec = _ARTIFACT_TYPE_REGISTRY.get(atype)
        cat = spec.category if spec else "uncategorized"
        by_cat.setdefault(cat, []).append(atype in _IMPLEMENTED_ARTIFACT_TYPES)
    return {
        cat: round(sum(flags) / len(flags), 4)
        for cat, flags in sorted(by_cat.items())
    }


def _score_extended_artifacts(
    report: GenerationReport,
    contracts: Dict[str, Any],
) -> None:
    """Score every generated artifact that has a contract but no validator score
    yet (Run-007 Finding 1) — the 5 extended types plus the Grafana JSON.

    Attaches a ``quality`` dict (via ``validate_extended_artifact``) so these
    artifacts enter ``artifacts_scored`` and the composite, instead of only
    counting toward artifact_type_coverage. The triplet keeps its richer
    structural validators (already scored); this fills the gap for the rest.
    """
    if not contracts:
        return
    try:
        from startd8.validators.observability_artifact_checks import (
            validate_extended_artifact,
        )
    except ImportError:
        return
    for a in report.artifacts:
        if a.status != "generated" or a.quality is not None or not a.content:
            continue
        contract = contracts.get(a.artifact_type)
        if not contract:
            continue
        a.quality = validate_extended_artifact(a.content, contract).to_quality()


# ---------------------------------------------------------------------------
# Orientation-aware scoring (REQ-OAT-050 / 061 / 062)
# ---------------------------------------------------------------------------


def _iter_rule_dicts(content: str) -> List[Dict[str, Any]]:
    """Yield rule dicts from alert/recording YAML (``groups[].rules[]`` —
    PrometheusRule CRD or flat — tolerating malformed content)."""
    try:
        data = yaml.safe_load(content)
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    groups = data.get("spec", {}).get("groups", []) or data.get("groups", [])
    rules: List[Dict[str, Any]] = []
    if groups:
        for g in groups:
            rules.extend(r for r in (g.get("rules", []) or []) if isinstance(r, dict))
    else:
        rules = [r for r in (data.get("rules", []) or []) if isinstance(r, dict)]
    return rules


def _produced_service_targets(report: GenerationReport) -> Tuple[Set[str], Set[str]]:
    """Service IDs that got a produced dashboard / runbook this run — the
    resolvable handoff targets for bridge actionability (REQ-OAT-061). Resolved
    at service granularity (not exact UID), so the obs-/cc-obs- UID skew between
    an alert's dashboard_url and the rendered dashboard does not false-flag."""
    dash: Set[str] = set()
    run: Set[str] = set()
    for a in report.artifacts:
        if a.status != "generated":
            continue
        if a.artifact_type in ("dashboard_spec", "dashboard"):
            dash.add(a.service_id)
        elif a.artifact_type == "runbook":
            run.add(a.service_id)
    return dash, run


def _bridge_human_actionable(
    result: ArtifactResult, dash_services: Set[str], run_services: Set[str],
) -> bool:
    """REQ-OAT-061 human (actionability) half of a bridge artifact.

    notification_policy → a route + receiver exists. alert/loki rules → every
    active rule has a severity + summary AND a context link (runbook_url/
    dashboard_url) that resolves to an artifact actually produced for the service
    this run (a non-produced handoff target = broken handoff → human half fails).
    """
    if result.artifact_type == "notification_policy":
        try:
            data = yaml.safe_load(result.content) or {}
        except Exception:
            return False
        return bool(data.get("route") and data.get("receivers"))

    rules = [r for r in _iter_rule_dicts(result.content) if "alert" in r]
    if not rules:
        return False
    handoff_exists = result.service_id in dash_services or result.service_id in run_services
    for r in rules:
        labels = r.get("labels", {}) or {}
        ann = r.get("annotations", {}) or {}
        if not labels.get("severity") or not ann.get("summary"):
            return False
        has_link = bool(ann.get("runbook_url") or ann.get("dashboard_url"))
        if not (has_link and handoff_exists):
            return False
    return True


def _recording_subscore(content: str) -> Optional[Dict[str, Any]]:
    """REQ-OAT-062: when a bridge file mixes alerting + recording rules, score the
    off-orientation (recording = system) subset as a recorded sub-score. Returns
    None when the file is not mixed (so it stays a single-orientation artifact)."""
    rules = _iter_rule_dicts(content)
    recording = [r for r in rules if "record" in r]
    alerting = [r for r in rules if "alert" in r]
    if not (recording and alerting):
        return None
    valid = sum(1 for r in recording if r.get("expr"))
    return {
        "orientation": Orientation.SYSTEM.value,
        "rules": len(recording),
        "valid": valid,
        "score": round(valid / len(recording), 4) if recording else 0.0,
    }


def _apply_orientation_scoring(report: GenerationReport) -> None:
    """Annotate each scored artifact with its taxonomy axes and, for bridge
    artifacts, a two-half (system/human) breakdown that is *partial* when only one
    half passes (REQ-OAT-050/061), plus a recorded recording-rule sub-score for
    mixed files (REQ-OAT-062). Runs after stamping + scoring, before the report
    is written. Honest skips (status != generated) are untouched."""
    # REQ-OAT-050 (artifacts_scored == artifacts_generated): the rendered Grafana
    # JSON (runtime "dashboard") is the compiled form of a "dashboard_spec" and has
    # no validator of its own — inherit the spec's already-validated quality so the
    # derived artifact is scored, not silently dropped from the scored denominator.
    spec_quality = {
        a.service_id: a.quality
        for a in report.artifacts
        if a.artifact_type == "dashboard_spec" and a.quality is not None
    }
    for a in report.artifacts:
        if (
            a.artifact_type == "dashboard"
            and a.status == "generated"
            and a.quality is None
            and a.service_id in spec_quality
        ):
            a.quality = dict(spec_quality[a.service_id])
            a.quality["inherited_from"] = "dashboard_spec"

    dash_services, run_services = _produced_service_targets(report)
    for a in report.artifacts:
        if a.status != "generated" or a.quality is None:
            continue
        if a.category:
            a.quality["category"] = a.category
        if a.orientation:
            a.quality["orientation"] = a.orientation
        if a.orientation != Orientation.BRIDGE.value:
            continue
        # system half = structurally valid (all structural checks pass).
        total = a.quality.get("checks_total", 0)
        passed = a.quality.get("checks_passed", 0)
        system_ok = total > 0 and passed == total
        human_ok = _bridge_human_actionable(a, dash_services, run_services)
        a.quality["orientation_breakdown"] = {"system": system_ok, "human": human_ok}
        a.quality["orientation_partial"] = system_ok != human_ok
        sub = _recording_subscore(a.content)
        if sub is not None:
            a.quality["offorientation_subscore"] = sub


def _record_unimplemented_artifact_types(
    report: GenerationReport,
    owned_elsewhere: Optional[Dict[str, str]] = None,
) -> None:
    """Emit explicit skip records for declared-but-unproduced types (Closure 3A / Gap 2 + REQ-OAT-052).

    The onboarding contract may declare more artifact types than this SDK
    produces. Rather than silently covering a subset (a "looks-like-success"
    failure where artifacts_skipped reads 0), record each unproduced declared type
    as a skip carrying a typed ``skip_reason`` + ``owner`` + ``route_state``:
    - ``owned_elsewhere`` (REQ-OAT-011/052): ceded to another component — excluded
      from the coverage denominator;
    - ``unimplemented`` (Gap 2): declared but no generator yet.
    Skip records carry NO ``source_checksum`` (no input slice; REQ-OAT-052), and
    are stamped with taxonomy axes from the registry where known (REQ-OAT-023).
    """
    owned_elsewhere = owned_elsewhere or {}
    project_id = report.project_id or "project"
    for atype in report.declared_artifact_types:
        ceded = atype in owned_elsewhere
        if ceded and atype in _ALWAYS_PRODUCED_DECLARED_TYPES:
            # The triplet is produced unconditionally; honoring a cede here would
            # record a skip for a type that IS produced and wrongly drop it from the
            # coverage denominator (which derives `owned` from these skip records).
            logger.warning(
                "artifact_type %r marked owned_elsewhere but is always produced by the "
                "triplet generator; ignoring the cede (counted as produced)", atype,
            )
            ceded = False
        if ceded:
            owner = owned_elsewhere[atype]
            report.artifacts.append(_stamp_taxonomy(ArtifactResult(
                artifact_type=atype,
                service_id=project_id,
                output_path=f"(owned by {owner}: {atype})",
                status="skipped",
                error_message=f"declared but owned by {owner}; produced elsewhere",
                skip_reason="owned_elsewhere",
                owner=owner,
                route_state=RouteState.CONTEXTCORE_OWNED.value,
            )))
            continue
        if atype in _IMPLEMENTED_ARTIFACT_TYPES:
            continue
        report.artifacts.append(_stamp_taxonomy(ArtifactResult(
            artifact_type=atype,
            service_id=project_id,
            output_path=f"(not generated: {atype})",
            status="skipped",
            error_message=(
                "declared in onboarding artifact_types but not implemented "
                "by the observability triplet generator"
            ),
            skip_reason="unimplemented",
            route_state=RouteState.DECLARED_UNIMPLEMENTED.value,
        )))


def _log_provision_outcome(result: Any, service_id: str) -> None:
    """Surface the workflow's provision step outcome for a service dashboard.

    The workflow provisions warn-don't-fail (a push failure keeps result.success
    True and records a 'provision' step note), so we read that step and log it.
    """
    for step in getattr(result, "steps", None) or []:
        if getattr(step, "step_name", "") == "provision":
            output = getattr(step, "output", "")
            if "failed" in output.lower() or "error" in output.lower():
                logger.warning("Provisioning %s: %s", service_id, output)
            else:
                logger.info("Provisioning %s: %s", service_id, output)
            return


def _convert_dashboards_to_grafana_json(
    report: GenerationReport,
    provision_url: Optional[str] = None,
) -> None:
    """Render each dashboard spec to deployable Grafana JSON (Gap 4 / Closure 4A).

    Routes every generated dashboard_spec through DashboardCreatorWorkflow
    (jsonnet → Grafana JSON) and records a ``dashboard`` artifact at the
    contracted path ``grafana/dashboards/{service}-dashboard.json`` — the format
    and location ``onboarding-metadata.json`` artifact_types.dashboard declares.
    The obs-{service} uid is preserved (enforce_uid=False) so alert/SLO
    dashboard_url links stay valid. Degrades gracefully: if the jsonnet
    toolchain/mixin is unavailable, the conversion is recorded as ``skipped``
    rather than failing the run.

    When ``provision_url`` is set, each dashboard is also pushed to that Grafana
    instance (idempotent upsert by uid; auth via the GRAFANA_API_TOKEN env var).
    Provisioning is warn-don't-fail: a push failure logs a warning but the
    dashboard artifact is still recorded as generated.
    """
    specs = [
        a
        for a in report.artifacts
        if a.artifact_type == "dashboard_spec" and a.status == "generated" and a.content
    ]
    if not specs:
        return

    try:
        from startd8.dashboard_creator.workflow import DashboardCreatorWorkflow
    except ImportError:
        logger.warning(
            "DashboardCreatorWorkflow unavailable; skipping Grafana JSON conversion"
        )
        return

    import tempfile

    workflow = DashboardCreatorWorkflow()
    for art in specs:
        service_id = art.service_id
        rel_path = f"grafana/dashboards/{service_id}-dashboard.json"
        try:
            spec_dict = yaml.safe_load(art.content)
        except yaml.YAMLError:
            logger.warning("Could not parse dashboard spec for %s", service_id)
            continue

        content = ""
        status = "skipped"
        error_message: Optional[str] = None
        try:
            with tempfile.TemporaryDirectory() as staging:
                config: Dict[str, Any] = {
                    "spec": spec_dict,
                    "output_dir": staging,
                    "enforce_uid": False,
                }
                if provision_url:
                    config["provision"] = True
                    config["grafana_url"] = provision_url
                result = workflow.run(config)
                if result.success:
                    uid = spec_dict.get("uid", f"obs-{service_id}")
                    produced = Path(staging) / f"{uid}.json"
                    if produced.is_file():
                        content = produced.read_text()
                        status = "generated"
                        if provision_url:
                            _log_provision_outcome(result, service_id)
                    else:
                        error_message = "workflow reported success but no JSON file found"
                else:
                    error_message = getattr(result, "error", None) or "conversion failed"
        except Exception as exc:  # toolchain missing, compile error, etc.
            logger.exception("Grafana JSON conversion failed for %s", service_id)
            error_message = f"conversion raised: {exc}"

        if status != "generated":
            logger.warning(
                "Grafana JSON conversion skipped for %s: %s", service_id, error_message
            )

        report.artifacts.append(
            ArtifactResult(
                artifact_type="dashboard",
                service_id=service_id,
                output_path=rel_path,
                status=status,
                content=content,
                error_message=error_message,
            )
        )


def _write_artifacts(artifacts: List[ArtifactResult], output_dir: Path) -> None:
    """Write generated YAML artifacts to disk."""
    for artifact in artifacts:
        if artifact.status != "generated" or not artifact.content:
            continue
        dest = output_dir / artifact.output_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(artifact.content)
        logger.info("Wrote %s", dest)


def _write_index(
    report: GenerationReport,
    business: BusinessContext,
    onboarding_path: Path,
    output_dir: Path,
) -> None:
    """Write observability-manifest.yaml index file (REQ-UOM-004)."""
    # Collect unique derivation rules, deduplicating by (field, source, transformation)
    seen_rules: Dict[str, Dict[str, Any]] = {}
    for artifact in report.artifacts:
        for d in artifact.derivations:
            key = f"{d.field}|{d.source}|{d.transformation}"
            if key not in seen_rules:
                seen_rules[key] = {
                    "field": d.field,
                    "source": d.source,
                    "transformation": d.transformation,
                    "tier": d.tier,
                    "applied_to": [],
                }
            if artifact.service_id not in seen_rules[key]["applied_to"]:
                seen_rules[key]["applied_to"].append(artifact.service_id)

    generated = sum(1 for a in report.artifacts if a.status == "generated")
    skipped = sum(1 for a in report.artifacts if a.status == "skipped")
    errored = sum(1 for a in report.artifacts if a.status == "error")

    summary: Dict[str, Any] = {
        "services_processed": report.services_processed,
        "services_skipped": report.services_skipped,
        "artifacts_generated": generated,
        "artifacts_skipped": skipped,
        "artifacts_errored": errored,
    }

    # REQ-OAT-052: honest, route-aware artifact-type coverage. Types ceded to
    # another component (skip_reason=owned_elsewhere) are EXCLUDED from the declared
    # denominator so a correct cede does not read as a false <1.0 FAIL (R4-F2).
    if report.declared_artifact_types:
        declared = set(report.declared_artifact_types)
        owned = {a.artifact_type for a in report.artifacts if a.skip_reason == "owned_elsewhere"}
        counted = declared - owned  # the REQ-OAT-052 denominator
        implemented = counted & _IMPLEMENTED_ARTIFACT_TYPES
        unimplemented = sorted(counted - _IMPLEMENTED_ARTIFACT_TYPES)
        summary["declared_artifact_types"] = sorted(declared)
        summary["owned_elsewhere_artifact_types"] = sorted(owned)
        summary["unimplemented_artifact_types"] = unimplemented
        summary["artifact_type_coverage"] = (
            round(len(implemented) / len(counted), 4) if counted else 1.0
        )
        # REQ-OAT-052: coverage reported per category.
        summary["artifact_type_coverage_by_category"] = _coverage_by_category(counted)

    # REQ-OBS-SHARED-004: surface emit-vs-cede provenance counts + the inferred-vs-declared
    # gap (REQ-OAT-024), so the report shows who emits / why skipped, not silent.
    if report.route_states:
        rs_counts: Dict[str, int] = {}
        inferred = 0
        for r in report.route_states:
            rs_counts[r["route_state"]] = rs_counts.get(r["route_state"], 0) + 1
            if r.get("classification_source") == "inferred":
                inferred += 1
        summary["metric_route_state_counts"] = rs_counts
        summary["metric_classifications_inferred"] = inferred
        # REQ-OAT-041: cat-4/5 (project / AI-agent) metrics have no generator yet;
        # surface the count so the "awaiting a cat-4/5 home" gap is visible, not
        # silently mixed into service observability.
        summary["metrics_awaiting_category_home"] = sum(
            1 for r in report.route_states
            if r.get("category") in (Category.PROJECT.value, Category.AI_AGENT.value)
        )

    index: Dict[str, Any] = {
        "manifest_id": "observability-artifacts",
        "version": "1.0.0",
        "project_id": report.project_id,
        "generated_at": report.generated_at,
        "source": {
            "onboarding_metadata": str(onboarding_path),
        },
        "summary": summary,
        "artifacts": [
            {
                "type": a.artifact_type,
                "service": a.service_id,
                "path": a.output_path,
                "status": a.status,
                # Taxonomy keystone (REQ-OAT-023) + provenance (REQ-OBS-SHARED-004).
                **({"category": a.category} if a.category else {}),
                **({"orientation": a.orientation} if a.orientation else {}),
                **({"declared_type": a.declared_type} if a.declared_type else {}),
                **({"route_state": a.route_state} if a.route_state else {}),
                **({"skip_reason": a.skip_reason} if a.skip_reason else {}),
                **({"owner": a.owner} if a.owner else {}),
                **({"quality_score": a.quality["score"]} if a.quality else {}),
            }
            for a in report.artifacts
        ],
        # Per-metric route_state classification (REQ-OBS-SHARED-004 validation surface).
        "metric_route_states": report.route_states,
        "derivation_rules": list(seen_rules.values()),
    }

    # Quality summary (REQ-KZ-OBS-730)
    scored = [a for a in report.artifacts if a.quality]
    if scored:
        by_type: Dict[str, List[float]] = {}
        for a in scored:
            by_type.setdefault(a.artifact_type, []).append(a.quality["score"])
        quality_summary: Dict[str, Any] = {}
        for atype, scores in by_type.items():
            quality_summary[f"avg_{atype}_score"] = round(sum(scores) / len(scores), 4)
        all_scores = [a.quality["score"] for a in scored]
        quality_summary["avg_composite_score"] = round(sum(all_scores) / len(all_scores), 4)
        quality_summary["artifacts_scored"] = len(scored)
        quality_summary["total_issues"] = sum(
            len(a.quality.get("issues", [])) for a in scored
        )
        quality_summary["total_repairs"] = sum(
            len(a.quality.get("repairs_applied", [])) for a in scored
        )
        index["quality_summary"] = quality_summary

    dest = output_dir / "observability-manifest.yaml"
    dest.parent.mkdir(parents=True, exist_ok=True)

    header = "# observability-manifest.yaml\n# Generated by startd8 observability artifact generator\n\n"
    body = yaml.dump(index, default_flow_style=False, sort_keys=False)
    dest.write_text(header + body)
    logger.info("Wrote index: %s", dest)


def _write_quality_report(
    artifacts: List[ArtifactResult],
    output_dir: Path,
    service_metrics: Optional[Dict[str, Set[str]]] = None,
) -> None:
    """Write standalone observability-quality.json (REQ-KZ-OBS-730b).

    Produces a per-service breakdown of quality scores, issues, and repairs
    alongside the aggregate summary.  Uses ``compute_service_composite`` from
    ``startd8.validators.observability_artifact_checks`` when available;
    otherwise falls back to a simple average.

    When ``service_metrics`` (service_id → expected metric names) is provided,
    a semantic ``metric_coverage_score`` is computed per service and blended
    into the composite (Gap 3 / Closure 2), so a structurally-clean triplet
    that ignores the service's domain metrics no longer scores near-perfect.
    """
    try:
        from startd8.validators.observability_artifact_checks import (
            compute_metric_coverage,
        )
    except ImportError:  # pragma: no cover
        compute_metric_coverage = None  # type: ignore[assignment]

    scored = [a for a in artifacts if a.quality and a.status == "generated"]
    if not scored:
        return

    # ---- per-service breakdown ----
    # Track per-role contents so coverage can be split into dashboarded vs
    # alerted (Run-007 Finding 3), and all per-service scores so the composite
    # reflects every artifact, not just the triplet (Run-007 Finding 1).
    services: Dict[str, Dict[str, Any]] = {}
    # REQ-OAT-051: track per-ORIENTATION contents so coverage folds across
    # human (dashboards) / system (SLO SLIs, recording rules) / bridge (active
    # alerts, notifications). The prior dashboarded/alerted split is retained as
    # aliases (human≡dashboarded, bridge≡alerted) for continuity.
    svc_human_contents: Dict[str, List[str]] = {}
    svc_system_contents: Dict[str, List[str]] = {}
    svc_bridge_contents: Dict[str, List[str]] = {}
    svc_all_scores: Dict[str, List[float]] = {}
    for a in scored:
        svc = services.setdefault(a.service_id, {})
        svc[a.artifact_type] = {
            "score": a.quality["score"],
            "checks_passed": a.quality.get("checks_passed", 0),
            "checks_total": a.quality.get("checks_total", 0),
            "issues": a.quality.get("issues", []),
            "repairs_applied": a.quality.get("repairs_applied", []),
        }
        svc_all_scores.setdefault(a.service_id, []).append(a.quality["score"])
        if a.content:
            if a.artifact_type in ("dashboard_spec", "dashboard"):
                svc_human_contents.setdefault(a.service_id, []).append(a.content)
            elif a.artifact_type in ("alert_rule", "loki_rule", "notification_policy"):
                svc_bridge_contents.setdefault(a.service_id, []).append(a.content)
            elif a.artifact_type == "slo_definition":
                svc_system_contents.setdefault(a.service_id, []).append(a.content)

    # compute per-service composite over ALL scored artifacts, blended with the
    # orientation-split metric coverage (human + system + bridge, equal thirds).
    for svc_id, svc_data in services.items():
        cov_human: Optional[float] = None
        cov_system: Optional[float] = None
        cov_bridge: Optional[float] = None
        if (
            service_metrics
            and compute_metric_coverage is not None
            and svc_id in service_metrics
        ):
            expected = service_metrics[svc_id]
            # human: referenced by a live dashboard panel.
            cov_human = compute_metric_coverage(
                expected, svc_human_contents.get(svc_id, [])
            ).score
            # system: defined as a system artifact (SLO SLI / recording rule).
            cov_system = compute_metric_coverage(
                expected, svc_system_contents.get(svc_id, [])
            ).score
            # bridge: referenced by an active (non-commented) alert / notification.
            # extract_referenced_metrics strips comment lines, so the domain-alert
            # TODO stubs do NOT count here — only metrics with a live alert do.
            cov_bridge = compute_metric_coverage(
                expected, svc_bridge_contents.get(svc_id, [])
            ).score
            svc_data["metric_coverage_human"] = cov_human
            svc_data["metric_coverage_system"] = cov_system
            svc_data["metric_coverage_bridge"] = cov_bridge
            # Continuity aliases (REQ-OAT-051): names retained for downstream readers.
            svc_data["metric_coverage_dashboarded"] = cov_human
            svc_data["metric_coverage_alerted"] = cov_bridge

        all_scores = svc_all_scores.get(svc_id, [])
        structural = sum(all_scores) / len(all_scores) if all_scores else 0.0

        # Fold the available orientation coverages at equal weights (REQ-OAT-051).
        _covs = [c for c in (cov_human, cov_system, cov_bridge) if c is not None]
        coverage_for_blend: Optional[float] = (
            sum(_covs) / len(_covs) if _covs else None
        )

        if coverage_for_blend is None:
            composite = structural
        else:
            composite = (
                structural * _COMPOSITE_STRUCTURAL_WEIGHT
                + coverage_for_blend * _COMPOSITE_COVERAGE_WEIGHT
            )
        svc_data["composite_score"] = round(composite, 4)

    # ---- aggregate ----
    by_type: Dict[str, List[float]] = {}
    total_issues = 0
    total_repairs = 0
    for a in scored:
        by_type.setdefault(a.artifact_type, []).append(a.quality["score"])
        total_issues += len(a.quality.get("issues", []))
        total_repairs += len(a.quality.get("repairs_applied", []))

    aggregate: Dict[str, Any] = {}
    for atype, scores in by_type.items():
        aggregate[f"avg_{atype}_score"] = round(sum(scores) / len(scores), 4)

    composites = [s["composite_score"] for s in services.values()]
    aggregate["avg_composite_score"] = (
        round(sum(composites) / len(composites), 4) if composites else 0.0
    )

    # REQ-OAT-051: orientation coverage averages (human / system / bridge), with a
    # combined avg_metric_coverage_score (equal-weight mean across the orientations
    # present) so the CLI coverage gate keeps working. dashboarded/alerted retained
    # as aliases for human/bridge.
    def _avg(key: str) -> Optional[float]:
        vals = [s[key] for s in services.values() if key in s]
        return round(sum(vals) / len(vals), 4) if vals else None

    avg_human = _avg("metric_coverage_human")
    avg_system = _avg("metric_coverage_system")
    avg_bridge = _avg("metric_coverage_bridge")
    if avg_human is not None:
        aggregate["avg_metric_coverage_human"] = avg_human
        aggregate["avg_metric_coverage_dashboarded"] = avg_human  # alias
    if avg_system is not None:
        aggregate["avg_metric_coverage_system"] = avg_system
    if avg_bridge is not None:
        aggregate["avg_metric_coverage_bridge"] = avg_bridge
        aggregate["avg_metric_coverage_alerted"] = avg_bridge  # alias
    _present = [v for v in (avg_human, avg_system, avg_bridge) if v is not None]
    if _present:
        aggregate["avg_metric_coverage_score"] = round(sum(_present) / len(_present), 4)

    # Finding 1: make scored-vs-generated explicit so the gap is visible.
    aggregate["artifacts_scored"] = len(scored)
    aggregate["artifacts_generated"] = sum(
        1 for a in artifacts if a.status == "generated"
    )
    aggregate["total_issues"] = total_issues
    aggregate["total_repairs"] = total_repairs

    report: Dict[str, Any] = {
        "schema_version": "1.0",
        "generated_at": _utc_now_iso(),
        "services": services,
        "aggregate": aggregate,
    }

    dest = output_dir / "observability-quality.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=2) + "\n")
    logger.info("Wrote quality report: %s", dest)


# ---------------------------------------------------------------------------
# Phase 6: Drift detection
# ---------------------------------------------------------------------------


def check_drift(
    onboarding_metadata_path: Path,
    output_dir: Path,
    manifest_path: Optional[Path] = None,
) -> int:
    """Compare freshly generated artifacts against existing ones in output_dir.

    Returns 0 if no drift, 1 if drift detected.
    """
    index_path = output_dir / "observability-manifest.yaml"
    if not index_path.exists():
        print(f"No existing index at {index_path}; cannot check drift")
        return 1

    with open(index_path, "r") as f:
        existing_index = yaml.safe_load(f) or {}

    # Generate fresh (in memory)
    report = generate_observability_artifacts(
        onboarding_metadata_path=onboarding_metadata_path,
        output_dir=output_dir,
        manifest_path=manifest_path,
        dry_run=True,
    )

    # Build keyed sets for comparison. The derived "dashboard" (Grafana JSON) is
    # excluded: it is a 1:1 render of "dashboard_spec" (already compared) and its
    # presence depends on the jsonnet toolchain being available, which would
    # otherwise make drift flip on environment rather than on real change.
    _DERIVED_TYPES = {"dashboard"}
    existing_keys = {
        (a["type"], a["service"])
        for a in existing_index.get("artifacts", [])
        if a.get("status") == "generated" and a.get("type") not in _DERIVED_TYPES
    }
    fresh_keys = {
        (a.artifact_type, a.service_id)
        for a in report.artifacts
        if a.status == "generated" and a.artifact_type not in _DERIVED_TYPES
    }

    new_artifacts = fresh_keys - existing_keys
    removed_artifacts = existing_keys - fresh_keys
    drift_found = False

    if new_artifacts:
        drift_found = True
        print(f"NEW artifacts ({len(new_artifacts)}):")
        for art_type, svc in sorted(new_artifacts):
            print(f"  + {art_type} for {svc}")

    if removed_artifacts:
        drift_found = True
        print(f"REMOVED artifacts ({len(removed_artifacts)}):")
        for art_type, svc in sorted(removed_artifacts):
            print(f"  - {art_type} for {svc}")

    # Check threshold changes in derivation rules
    existing_rules = {
        (r.get("field"), r.get("source")): r.get("transformation")
        for r in existing_index.get("derivation_rules", [])
    }
    fresh_rules: Dict[tuple, str] = {}
    for a in report.artifacts:
        for d in a.derivations:
            key = (d.field, d.source)
            fresh_rules[key] = d.transformation

    for key, fresh_val in fresh_rules.items():
        existing_val = existing_rules.get(key)
        if existing_val and existing_val != fresh_val:
            drift_found = True
            print(f"CHANGED: {key[0]} ({key[1]}): {existing_val} → {fresh_val}")

    if not drift_found:
        print("No drift detected")
        return 0

    return 1


# ---------------------------------------------------------------------------
# Provenance extension (REQ-UOM-052)
# ---------------------------------------------------------------------------


def _append_to_provenance(
    provenance_path: Path,
    output_dir: Path,
) -> None:
    """Best-effort append observability artifacts to run-provenance.json."""
    if not provenance_path.exists():
        logger.info("No run-provenance.json at %s; skipping provenance append", provenance_path)
        return

    try:
        with open(provenance_path, "r") as f:
            provenance = json.load(f)

        inventory = provenance.get("artifact_inventory", [])
        inventory.append(
            {
                "stage": "4.5",
                "id": "observability-manifest",
                "path": str(output_dir / "observability-manifest.yaml"),
                "role": "observability-artifacts-index",
            }
        )
        provenance["artifact_inventory"] = inventory

        with open(provenance_path, "w") as f:
            json.dump(provenance, f, indent=2)
        logger.info("Appended observability entry to %s", provenance_path)
    except (OSError, json.JSONDecodeError):
        logger.warning("Failed to append to provenance at %s", provenance_path, exc_info=True)
