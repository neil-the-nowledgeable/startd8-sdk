"""
Generate observability artifacts (alert rules, dashboard specs, SLO definitions)
from ContextCore onboarding metadata and manifest business context.

Reads onboarding-metadata.json (from cap-dev-pipe Stage 4 EXPORT) and
.contextcore.yaml, then produces per-service artifact files.

See docs/design/UNIFIED_OBSERVABILITY_MANIFEST_REQUIREMENTS.md for design.
"""

import json
import logging
import os
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

# Target Metric Binding (REQ_TARGET_METRIC_BINDING Step 3): resolve one
# MetricDescriptor per service and thread it into the descriptor-aware generators.
from .metric_descriptor import (
    BASE_RED_KINDS,
    NON_EMITTING_CONVENTION_SURFACES,
    NON_SCRAPEABLE_SURFACES,
    UNGROUNDED_KINDS,
    MetricDescriptor,
    resolve_descriptor,
    resolve_sli_kinds,
    suggested_signals_for,
)

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
    _target_for,
    generate_alert_rules,
    generate_business_criticality_dashboard,
    generate_capability_index,
    generate_collector_enrichment,
    generate_dashboard_spec,
    generate_loki_rule,
    generate_notification_policy,
    generate_runbook,
    generate_service_monitor,
    generate_slo_definitions,
    generate_functional_slos,
    generate_declared_base_slos,
    generate_declared_functional_slos,
    generate_declared_span_slos,
    generate_declared_probe_slos,
    generate_declared_probe_specs,
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
_IMPLEMENTED_ARTIFACT_TYPES = frozenset(
    {
        "dashboard",
        "prometheus_rule",
        "slo_definition",
        "service_monitor",
        "notification_policy",
        "loki_rule",
        "runbook",
        "capability_index",
    }
)


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
_ALWAYS_PRODUCED_DECLARED_TYPES = frozenset(
    {"prometheus_rule", "dashboard", "slo_definition"}
)


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
# Helpers
# ---------------------------------------------------------------------------


def _emit_time_sdk_sha() -> Dict[str, str]:
    """Resolve the startd8 checkout sha used at quality-emit time (OBS-200a tip honesty).

    Prefer ``git rev-parse HEAD`` from the import path of ``startd8`` so Thanos can
    fail-closed when quality ``sdk_sha`` ≠ remasure READY tip. Installed wheels
    without a ``.git`` directory yield ``source=absent`` (never invent a sha).
    """
    import subprocess

    try:
        import startd8

        module_path = Path(startd8.__file__).resolve()
    except Exception:  # pragma: no cover — import always present in-repo
        return {"sdk_sha": "", "sdk_sha_source": "absent"}

    # src/startd8/__init__.py → repo root; also try parents (editable / flat installs).
    candidates = [module_path.parents[2], module_path.parents[1], module_path.parent]
    for root in candidates:
        if not (root / ".git").exists():
            continue
        try:
            proc = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):  # pragma: no cover
            continue
        sha = (proc.stdout or "").strip()
        if proc.returncode == 0 and len(sha) >= 7:
            return {
                "sdk_sha": sha,
                "sdk_sha_source": "git_rev_parse",
                "sdk_module_path": str(module_path),
            }
    return {
        "sdk_sha": "",
        "sdk_sha_source": "absent",
        "sdk_module_path": str(module_path),
    }


def _utc_now_iso() -> str:
    """UTC timestamp for `generated_at` fields, honoring deterministic runs.

    Under cap-dev-pipe's ``--deterministic-output``, the observability stage pins
    ``CDP_DETERMINISTIC_RUN_TIMESTAMP`` (canonical format ``%Y%m%dT%H%M``) so the
    generated meta files (manifest yaml, quality json, portal json) are
    byte-identical across otherwise-identical runs (issue #224). When set, parse
    and re-emit in the canonical ISO shape; if the value is unrecognized, return
    it verbatim (still deterministic since it is pinned) — never fall back to
    wall clock while the var is set. When unset, use wall clock as before.
    """
    pinned = os.environ.get("CDP_DETERMINISTIC_RUN_TIMESTAMP", "").strip()
    if pinned:
        for fmt in ("%Y%m%dT%H%M", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.strptime(pinned, fmt).replace(tzinfo=timezone.utc)
                return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                continue
        return pinned
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Native extended generators for declared artifact types beyond the RED triplet — produced only
# when the onboarding metadata declares the type (contract-driven).


# Declared-type-name → (per-service generator, output_prefix). Contract-driven:
# only generated when the onboarding metadata declares the type (Closure 3B).
_EXTENDED_PER_SERVICE_GENERATORS = {
    "service_monitor": (generate_service_monitor, "service-monitors"),
    "notification_policy": (generate_notification_policy, "notifications"),
    "loki_rule": (generate_loki_rule, "loki-rules"),
    "runbook": (generate_runbook, "runbooks"),
}

#: spec.targets[].kind values that are NOT Kubernetes workloads — a Prometheus-Operator ServiceMonitor
#: CRD is meaningless for these (no k8s API / operator to reconcile it). Used to suppress a dead k8s
#: ServiceMonitor on a non-k8s runtime (ADR-003 FP-3). An empty/unknown/k8s kind is NOT listed, so it
#: keeps emitting (conservative — today's k8s default is preserved).
_NON_K8S_TARGET_KINDS = frozenset(
    {"compose_service", "docker_service", "docker_container", "systemd", "process", "binary", "host"}
)


# ---------------------------------------------------------------------------
# Phase 4.5: Validate-with-autofix (REQ-KZ-OBS-700 + 710)
# ---------------------------------------------------------------------------


def _repair_and_validate(
    result: ArtifactResult,
    business: BusinessContext,
    transport: Optional[str] = None,
    descriptor: Optional[MetricDescriptor] = None,
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
            validate_collector_enrichment_artifact,
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
            result.content,
            result.output_path,
            autofix=True,
            service_id=result.service_id,
            transport=transport,
            descriptor=descriptor,
        )
        # If gridPos was injected, update content with repaired YAML
        if vr.repairs_applied:
            try:
                repaired = yaml.safe_load(result.content)
                from startd8.validators.observability_artifact_checks import (
                    repair_gridpos,
                )

                repaired, _ = repair_gridpos(repaired)
                result.content = yaml.dump(
                    repaired, default_flow_style=False, sort_keys=False
                )
            except Exception:
                pass

    elif result.artifact_type == "alert_rule":
        vr = validate_alerts(
            result.content,
            result.output_path,
            manifest_availability=avail,
            service_id=result.service_id,
            transport=transport,
        )

    elif result.artifact_type == "slo_definition":
        vr = validate_slo(
            result.content,
            result.output_path,
            manifest_availability=avail,
            autofix=True,
            service_id=result.service_id,
            transport=transport,
        )
        # If SLO target was repaired, update content
        if vr.repairs_applied:
            try:
                from startd8.validators.observability_artifact_checks import (
                    repair_slo_target,
                )

                repaired = yaml.safe_load(result.content)
                repaired, _ = repair_slo_target(repaired, avail)
                result.content = yaml.dump(
                    repaired, default_flow_style=False, sort_keys=False
                )
            except Exception:
                pass

    elif result.artifact_type == "collector_enrichment":
        # LH-3: score the enrichment artifact like its siblings (structural content re-check).
        vr = validate_collector_enrichment_artifact(result.content, result.output_path)

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
                result.artifact_type,
                result.service_id,
                vr.score * 100,
                issue_summary,
            )

    return result


# Generators that accept a resolved MetricDescriptor as their 3rd positional arg
# (REQ_TARGET_METRIC_BINDING Step 3, FR-4/FR-1a). notification_policy joined this set
# per REQ_NOTIFICATION_POLICY FR-8: its route matcher label is metric-shape-DEPENDENT
# (`service` vs `service_name` for span-metrics), so it must read
# `descriptor.service_label_key` rather than hardcoding `service`. The remaining
# per-service generators (service_monitor, runbook) stay (service, business).
_DESCRIPTOR_AWARE_GENERATORS = frozenset(
    {
        generate_alert_rules,
        generate_slo_definitions,
        generate_dashboard_spec,
        generate_loki_rule,
        generate_notification_policy,
    }
)


def _generate_one(
    gen_fn: Any,
    service: ServiceHints,
    business: BusinessContext,
    artifact_type: str,
    output_prefix: str,
    descriptor: Optional[MetricDescriptor] = None,
) -> ArtifactResult:
    """Generate, validate, and score a single artifact. Catches exceptions.

    Central taxonomy assignment site (REQ-OAT-023): every result is stamped with
    category/orientation/declared_type/runtime_type from the registry here, so the
    ~7 generator functions never hand-set those axes.

    ``descriptor`` (the per-service resolved MetricDescriptor) is forwarded only
    to the descriptor-aware generators; the others keep their 2-arg signature.
    """
    try:
        if descriptor is not None and gen_fn in _DESCRIPTOR_AWARE_GENERATORS:
            result = gen_fn(service, business, descriptor)
        else:
            result = gen_fn(service, business)
        result = _repair_and_validate(
            result, business, transport=service.transport, descriptor=descriptor
        )
        return _stamp_taxonomy(result)
    except Exception:
        logger.exception(
            "%s generation failed for %s", artifact_type, service.service_id
        )
        return _stamp_taxonomy(
            ArtifactResult(
                artifact_type=artifact_type,
                service_id=service.service_id,
                output_path=f"{output_prefix}/{service.service_id}-{output_prefix}.yaml",
                status="error",
                error_message="Generation raised exception",
            )
        )


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
    coverage: Optional[Dict[str, Any]] = None,
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
            business,
            services,
            report,
            metadata,
            persona=persona,
            coverage=coverage,
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
            error_msg = (
                result.output.get("error", "Unknown workflow error")
                if isinstance(result.output, dict)
                else str(result.output)
            )
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


#: AffordanceMap export dispositions for the expected-set union (FR-2 / FR-4).
_EXPORT_NO = "no_export"
_EXPORT_FRESH_ZERO = "fresh_export_zero_metric_loci"
_EXPORT_STALE = "stale_or_mismatched_export"
_EXPORT_MALFORMED = "malformed_export"
_EXPORT_OK = "fresh_export"


#: Coverage / expected-set admit statuses — same honesty window as RED bind
#: (``plan_affordance_actions``): ``source_backed`` and ``partial``. Restricting
#: to ``source_backed`` alone silently drops query-frontend when its
#: ``metric_coverage_empty`` row is absent and only ``partial`` RED/dead rows
#: carry metric loci (tip ``a6968b9c`` metric depth regression).
_ADMIT_LOCUS_STATUSES = frozenset({"source_backed", "partial"})


def _admit_affordance_metric_families(
    services: List[Any],
    affordance_map: Any,
) -> Tuple[Dict[str, Set[str]], str, Dict[str, Any]]:
    """Admit AffordanceMap metric loci into per-service family sets (FR-2/FR-3).

    Exact ``element_id == service_id`` join only (no prefix/stack-default). Entry-level
    ``locus_status`` in ``source_backed``|``partial`` then ``metric_loci``; fail-closed
    on load error or history truncation. Returns
    ``(per_service_families, disposition, diagnostics)``.
    """
    empty: Dict[str, Set[str]] = {s.service_id: set() for s in services}
    diag: Dict[str, Any] = {
        "orphan_element_ids": [],
        "hint_only_services": [],
        "artifact_only_services": sorted(s.service_id for s in services),
    }
    if affordance_map is None:
        return empty, _EXPORT_NO, diag

    from .affordance_map_consume import (
        AffordanceMapEntry,
        LoadResult,
        load_affordance_map,
        metric_loci,
    )

    loaded: LoadResult
    if isinstance(affordance_map, LoadResult):
        loaded = affordance_map
    elif isinstance(affordance_map, (tuple, list)) and affordance_map and all(
        isinstance(x, AffordanceMapEntry) for x in affordance_map
    ):
        # Entry objects first — a bare list also matches load_affordance_map's JSON shape.
        loaded = LoadResult(entries=list(affordance_map))
    elif isinstance(affordance_map, (str, Path, dict, list)):
        loaded = load_affordance_map(affordance_map)
    else:
        return empty, _EXPORT_MALFORMED, {**diag, "error": f"unsupported type {type(affordance_map)!r}"}

    if loaded.error:
        return empty, _EXPORT_MALFORMED, {**diag, "error": loaded.error}
    if loaded.source_truncated:
        return empty, _EXPORT_STALE, {**diag, "error": "source_truncated"}

    known = {s.service_id for s in services}
    per: Dict[str, Set[str]] = {sid: set() for sid in known}
    orphans: List[str] = []
    admitted = 0
    for entry in loaded.entries:
        eid = entry.element_id or ""
        if eid not in known:
            if eid:
                orphans.append(eid)
            continue
        if (entry.locus_status or "") not in _ADMIT_LOCUS_STATUSES:
            continue
        for row in metric_loci(entry):
            fam = str(row.get("family_or_signal") or "").strip()
            if fam:
                per[eid].add(fam)
                admitted += 1

    diag["orphan_element_ids"] = sorted(set(orphans))
    map_touched = {sid for sid, fams in per.items() if fams}
    # hint-only: ServiceHints present, no admitted map loci for that id.
    # artifact-only: reserved for quality-report universe (unknown here) — empty.
    diag["hint_only_services"] = sorted(known - map_touched)
    diag["artifact_only_services"] = []
    if admitted == 0:
        return per, _EXPORT_FRESH_ZERO, diag
    return per, _EXPORT_OK, diag


def build_service_metrics_expected(
    services: List[Any],
    *,
    affordance_map: Any = None,
) -> Dict[str, Any]:
    """Build per-service expected metric sets + ``expected_sources`` (FR-1..FR-4).

    Union = convention ∪ declared ∪ ``declared_emitted_series`` ∪ admitted AffordanceMap
    metric families. Never unions ``declared_span_signals``. Span/convention/declared counts
    are pre-union source sizes (FR-4).
    """
    map_families, disposition, map_diag = _admit_affordance_metric_families(
        services, affordance_map
    )
    service_metrics: Dict[str, Set[str]] = {}
    expected_sources: Dict[str, Dict[str, Any]] = {}
    for svc in services:
        convention = {m.name for m in (svc.convention_metrics or ()) if getattr(m, "name", None)}
        declared = {m.name for m in (svc.declared_metrics or ()) if getattr(m, "name", None)}
        emitted = {
            s.name
            for s in (getattr(svc, "declared_emitted_series", None) or ())
            if getattr(s, "name", None)
        }
        afford = set(map_families.get(svc.service_id) or ())
        union = set(convention) | set(declared) | set(emitted) | set(afford)
        service_metrics[svc.service_id] = union
        expected_sources[svc.service_id] = {
            "convention": len(convention),
            "declared": len(declared),
            "emitted_series": len(emitted),
            "affordance_loci": len(afford),
            "expected_raw_union": len(union),
        }
    return {
        "service_metrics": service_metrics,
        "expected_sources": expected_sources,
        "export_disposition": disposition,
        "diagnostics": map_diag,
    }


#: FR-2 coverage-bind panel group — distinct from every other panel group so a
#: reader can see which panels exist ONLY to close AffordanceMap-sourced coverage.
_COVERAGE_BIND_GROUP = "Coverage (AffordanceMap)"


def _coverage_bind_panel_expr(fam: str, *, is_summary: bool = False) -> str:
    """PromQL for one AffordanceMap coverage-bind panel.

    Gauges stay ``max(name{})`` (extractor-visible). Native histogram basenames
    (duration/delay/retries/…_seconds) use ``histogram_quantile`` on ``*_bucket``
    — same shape as declared-base latency + AffordanceMap Duration panels — so
    live bind does not fail Class B on missing basename gauges (PATHFIX_QF:
    ``cortex_query_frontend_retries`` @ tip 21398c57).

    ``is_summary`` (EC-SUMMARY-TYPE): a Prometheus **Summary** shares the
    ``…_duration_seconds`` basename shape of a histogram but exposes **no**
    ``_bucket`` series — so ``histogram_quantile(rate(…_bucket))`` binds DEAD in
    the regenerated dashboard/alert (the finding this fixes). A summary's
    ``_sum``/``_count`` children always exist, so an average-latency SLI binds
    live; p99 would need configured quantile objectives a summary may omit, so
    the guaranteed-bindable average is preferred over a possibly-dead quantile.
    The caller passes ``is_summary`` from the service's ``declared_emitted_series``
    type; unknown/histogram families keep the existing behaviour (no regression).
    """
    from .affordance_map_consume import (
        _duration_panel_expr,
        _is_native_hist_basename,
        _summary_avg_expr,
    )

    if is_summary:
        return _summary_avg_expr(fam)
    if _is_native_hist_basename(fam):
        return _duration_panel_expr(fam)
    return f"max({fam}{{}})"


def _apply_affordance_coverage_bind_panels(
    artifacts: List[Any],
    services: List[Any],
    affordance_map: Any = None,
) -> Dict[str, Any]:
    """Step 2/2a — land AffordanceMap ``source_backed`` metric families as real
    dashboard panels on the IN-MEMORY ``dashboard_spec`` content, before
    ``_write_artifacts`` / ``_write_quality_report`` run (FR-2, FR-2b).

    This is generator input, not a post-hoc file append: because it mutates
    ``ArtifactResult.content`` before ``_write_artifacts`` writes it, a normal
    regen reproduces the panel AND ``_write_quality_report`` scores it in the
    same in-memory pass whose ``expected`` set Step 1's evaluator union already
    widens — so ``expected ∩ referenced`` (``compute_metric_coverage``) can
    actually be non-empty for these families, instead of the panel being
    destroyed by the next ``_write_artifacts`` (the R1-S1/R1-S2 write-collision
    this step exists to avoid).

    Reuses Step 1's identity join (``_admit_affordance_metric_families`` — exact
    ``element_id == service_id``, fail-closed on unmatched/stale/malformed) — no
    second matcher is implemented here (Mottainai). FR-5 locus-kind discipline is
    inherited transitively: that admission already calls ``metric_loci(entry)``,
    which excludes ``transport``-kind rows and unresolved synthetic components.

    Uses ``_coverage_bind_panel_expr``: ``max(<name>{})`` for gauges (extractor-
    visible vs bare ``max(name)``), and histogram_quantile on ``*_bucket`` for
    duration/delay families so native-histogram basenames bind live.

    Returns FR-7 evidence: ``{"export_disposition": ..., "services": {svc_id:
    {"families_admitted": n, "panels_added": n}}}``.
    """
    try:
        from startd8.validators.observability_artifact_checks import (
            _normalize_metric_name,
            extract_referenced_metrics,
        )
    except ImportError:  # pragma: no cover
        extract_referenced_metrics = None  # type: ignore[assignment]
        _normalize_metric_name = None  # type: ignore[assignment]

    map_families, disposition, _diag = _admit_affordance_metric_families(
        services, affordance_map
    )
    evidence: Dict[str, Any] = {"export_disposition": disposition, "services": {}}
    if disposition != _EXPORT_OK:
        # no_export / fresh_export_zero_metric_loci / stale / malformed → nothing
        # admitted; fail closed rather than bind against a phantom/absent export.
        return evidence

    by_service = {
        a.service_id: a
        for a in artifacts
        if a.artifact_type == "dashboard_spec" and a.status == "generated"
    }
    # EC-SUMMARY-TYPE: which admitted families are Prometheus SUMMARIES (per the
    # service's declared_emitted_series type) — a summary must NOT be panelled with
    # histogram_quantile(rate(_bucket)) (no _bucket series ⇒ dead SLI).
    svc_by_id = {getattr(s, "service_id", None): s for s in services}
    for svc_id, families in map_families.items():
        if not families:
            continue
        art = by_service.get(svc_id)
        if art is None or not art.content:
            continue
        _svc = svc_by_id.get(svc_id)
        summary_families = {
            s.name
            for s in (getattr(_svc, "declared_emitted_series", None) or ())
            if getattr(s, "name", None) and getattr(s, "type", "") == "summary"
        }
        try:
            data = yaml.safe_load(art.content) or {}
        except Exception:
            logger.warning(
                "coverage-bind: could not parse dashboard_spec YAML for %s — skipping bind",
                svc_id,
            )
            continue
        panels = data.get("panels")
        if not isinstance(panels, list):
            continue
        existing = {str(p.get("expr", "")) for p in panels if isinstance(p, dict)}
        # PICR-fixed: dedup by REFERENCED metric name, not raw expr text — a family
        # already panelled via _add_declared_gauge_observe_panels (a real selector,
        # e.g. max(name{job="x"})) must not also get our bare max(name{}) rebind;
        # both exprs reference the same name but would fail a raw-string dedup.
        already_named = (
            extract_referenced_metrics(existing) if extract_referenced_metrics else set()
        )
        added = 0
        for fam in sorted(families):
            if _normalize_metric_name and _normalize_metric_name(fam) in already_named:
                continue
            # Native Prometheus histograms expose *_bucket/_sum/_count — not a
            # gauge at the basename. max(basename{}) is empty live and surfaces
            # as Class B latency dead (compact/query/store/receive remasure).
            # Reuse AffordanceMap Duration panel shape (histogram_quantile on
            # _bucket) for duration/delay families; keep max({}) for gauges.
            expr = _coverage_bind_panel_expr(fam, is_summary=fam in summary_families)
            if expr in existing:
                continue
            panels.append(
                {
                    "type": "timeseries",
                    "title": _panel_title(fam),
                    "expr": expr,
                    "unit": "short",
                    "group": _COVERAGE_BIND_GROUP,
                }
            )
            existing.add(expr)
            added += 1
        if added == 0:
            continue
        data["panels"] = panels
        # Preserve the byte-identical leading comment header (every line of it
        # starts with "#" — see _derivation_comment — followed by one blank
        # line); re-dump only the YAML body so unrelated fields are untouched.
        header_lines: List[str] = []
        for line in art.content.splitlines(keepends=True):
            if line.startswith("#") or not line.strip():
                header_lines.append(line)
                continue
            break
        art.content = "".join(header_lines) + yaml.dump(
            data, default_flow_style=False, sort_keys=False
        )
        art.derivations.append(
            DerivationTrace(
                field="affordance_coverage_bind_panels",
                source=f"affordance_map.source_backed.metric_locus.{svc_id}",
                transformation=f"{added} AffordanceMap-derived coverage bind panel(s) added",
                tier="affordance_map",
            )
        )
        evidence["services"][svc_id] = {
            "families_admitted": len(families),
            "panels_added": added,
        }
    return evidence


_ORIENTATION_BIND_QUALITY = {
    "score": 1.0,
    "checks_passed": 0,
    "checks_total": 0,
    "issues": [],
    "repairs_applied": [],
}


def _coverage_bind_preserve_header(content: str, body_yaml: str) -> str:
    """Keep leading ``#`` comment header + blank line; replace YAML body only."""
    header_lines: List[str] = []
    for line in content.splitlines(keepends=True):
        if line.startswith("#") or not line.strip():
            header_lines.append(line)
            continue
        break
    return "".join(header_lines) + body_yaml


def _orientation_slo_doc(svc_id: str, fam: str) -> Dict[str, Any]:
    """One OpenSLO doc whose active ``query`` references ``fam`` (system axis).

    Name shape mirrors declared-base (``{svc}-{kind}-{slug}-declared``): never
    ``{svc}-coverage-bind-…``, which filename/last-resort attribution turns into a
    phantom service ``{svc}-coverage-bind`` (PATHFIX_QF residual @ 1d951b03).
    """
    safe = fam.replace("_", "-")[:48]
    expr = _coverage_bind_panel_expr(fam)
    return {
        "apiVersion": "openslo/v1",
        "kind": "SLO",
        "metadata": {
            "name": f"{svc_id}-orientation-{safe}",
            "labels": {
                "service": svc_id,
                "bound_series": fam,
                "generated_by": "startd8",
                "coverage_bind": "affordance_map_orientation",
            },
        },
        "spec": {
            "description": (
                f"AffordanceMap coverage-bind system orientation for '{fam}' "
                "(metric_coverage_system residual)."
            ),
            "target": "99%",
            "timeWindow": {"duration": "30d", "isRolling": True},
            "indicator": {
                "metadata": {"name": f"{svc_id}-orientation-{safe}-sli"},
                "spec": {
                    "thresholdMetric": {
                        "metricSource": {
                            "type": "prometheus",
                            "spec": {"query": expr},
                        }
                    }
                },
            },
        },
    }


def _orientation_alert_rule(svc_id: str, fam: str) -> Dict[str, Any]:
    """One Prometheus alert rule whose ``expr`` references ``fam`` (bridge axis)."""
    safe = "".join(p[:1].upper() + p[1:] for p in fam.replace("-", "_").split("_") if p)
    expr = _coverage_bind_panel_expr(fam)
    return {
        "alert": f"{svc_id.replace('-', '').title()}Orientation{safe}"[:200],
        "expr": f"{expr} >= 0",
        "for": "5m",
        # ``service`` required — without it filename ``{svc}-coverage-bind-alerts``
        # attributes to phantom ``{svc}-coverage-bind`` (PATHFIX_QF dead #1).
        "labels": {
            "severity": "info",
            "service": svc_id,
            "coverage_bind": "affordance_map_orientation",
        },
        "annotations": {
            "summary": f"AffordanceMap coverage-bind bridge orientation for {fam}",
        },
    }


def _apply_affordance_coverage_bind_orientation(
    artifacts: List[Any],
    services: List[Any],
    affordance_map: Any = None,
) -> Dict[str, Any]:
    """Land AffordanceMap-admitted families into system (SLO) + bridge (alert) buckets.

    Parent coverage-bind panels only feed ``metric_coverage_human``. Tip honesty after
    #372 still shows ``system``/``bridge`` ≈ 0 because many services lack scored
    ``slo_definition`` / ``alert_rule`` content referencing the widened expected set.
    This mutates/creates those artifacts in-memory before ``_write_artifacts`` so
    ``_write_quality_report`` scores them in the same pass (same write-collision
    discipline as panel bind). Reuses ``_admit_affordance_metric_families`` (Mottainai).
    """
    try:
        from startd8.validators.observability_artifact_checks import (
            _normalize_metric_name,
            extract_referenced_metrics,
        )
    except ImportError:  # pragma: no cover
        extract_referenced_metrics = None  # type: ignore[assignment]
        _normalize_metric_name = None  # type: ignore[assignment]

    map_families, disposition, _diag = _admit_affordance_metric_families(
        services, affordance_map
    )
    evidence: Dict[str, Any] = {"export_disposition": disposition, "services": {}}
    if disposition != _EXPORT_OK:
        return evidence

    def _named(content: str) -> set:
        if not content or not extract_referenced_metrics:
            return set()
        return extract_referenced_metrics([content])

    for svc_id, families in map_families.items():
        if not families:
            continue
        # Prefer Thanos twins over Cortex mixin aliases (#371 / SDK brief P2).
        try:
            from .artifact_generator_context import _apply_declared_series_upstream_rename
        except ImportError:  # pragma: no cover
            _apply_declared_series_upstream_rename = None  # type: ignore[assignment]
        renamed: List[str] = []
        seen: set = set()
        for fam in families:
            live = fam
            if _apply_declared_series_upstream_rename is not None:
                live, _ = _apply_declared_series_upstream_rename(fam, {})
            if live not in seen:
                seen.add(live)
                renamed.append(live)
        fam_sorted = sorted(renamed)
        norm = _normalize_metric_name or (lambda x: x)

        # --- system: slo_definition ---
        slo_arts = [
            a
            for a in artifacts
            if a.artifact_type == "slo_definition"
            and a.service_id == svc_id
            and a.status == "generated"
            and a.content
        ]
        already_slo = set()
        for a in slo_arts:
            already_slo |= {norm(n) for n in _named(a.content)}
        to_add_slo = [f for f in fam_sorted if norm(f) not in already_slo]
        system_added = 0
        if to_add_slo:
            docs = [_orientation_slo_doc(svc_id, f) for f in to_add_slo]
            body = "\n---\n".join(
                yaml.dump(d, default_flow_style=False, sort_keys=False) for d in docs
            )
            if slo_arts:
                art = slo_arts[0]
                sep = "\n---\n" if art.content.rstrip() else ""
                art.content = art.content.rstrip() + sep + body
                if not art.quality or "score" not in art.quality:
                    art.quality = dict(_ORIENTATION_BIND_QUALITY)
                art.derivations.append(
                    DerivationTrace(
                        field="affordance_coverage_bind_orientation_slo",
                        source=f"affordance_map.source_backed.metric_locus.{svc_id}",
                        transformation=f"{len(to_add_slo)} system-orientation SLO bind(s)",
                        tier="affordance_map",
                    )
                )
            else:
                header = (
                    f"# AffordanceMap coverage-bind system orientation for {svc_id}\n"
                    f"# Generated by startd8 observability artifact generator\n\n"
                )
                artifacts.append(
                    ArtifactResult(
                        artifact_type="slo_definition",
                        service_id=svc_id,
                        output_path=f"slos/{svc_id}-coverage-bind-slo.yaml",
                        status="generated",
                        content=header + body,
                        quality=dict(_ORIENTATION_BIND_QUALITY),
                        derivations=[
                            DerivationTrace(
                                field="affordance_coverage_bind_orientation_slo",
                                source=f"affordance_map.source_backed.metric_locus.{svc_id}",
                                transformation=(
                                    f"{len(to_add_slo)} system-orientation SLO bind(s) (new file)"
                                ),
                                tier="affordance_map",
                            )
                        ],
                    )
                )
            system_added = len(to_add_slo)

        # --- bridge: alert_rule ---
        alert_arts = [
            a
            for a in artifacts
            if a.artifact_type == "alert_rule"
            and a.service_id == svc_id
            and a.status == "generated"
            and a.content
        ]
        already_alert = set()
        for a in alert_arts:
            already_alert |= {norm(n) for n in _named(a.content)}
        # Bridge bucket also scores loki_rule / notification_policy — don't
        # duplicate families already referenced there.
        for a in artifacts:
            if (
                a.service_id == svc_id
                and a.status == "generated"
                and a.content
                and a.artifact_type in ("loki_rule", "notification_policy")
            ):
                already_alert |= {norm(n) for n in _named(a.content)}
        to_add_alert = [f for f in fam_sorted if norm(f) not in already_alert]
        bridge_added = 0
        if to_add_alert:
            new_rules = [_orientation_alert_rule(svc_id, f) for f in to_add_alert]
            if alert_arts:
                art = alert_arts[0]
                try:
                    data = yaml.safe_load(art.content) or {}
                except Exception:
                    logger.warning(
                        "orientation-bind: could not parse alert_rule YAML for %s — "
                        "creating companion file",
                        svc_id,
                    )
                    data = {}
                if not isinstance(data, dict):
                    data = {}
                groups = data.get("groups")
                if not isinstance(groups, list):
                    groups = []
                    data["groups"] = groups
                group = None
                for g in groups:
                    if isinstance(g, dict) and g.get("name") == f"{svc_id}.coverage_bind":
                        group = g
                        break
                if group is None:
                    group = {"name": f"{svc_id}.coverage_bind", "rules": []}
                    groups.append(group)
                rules = group.setdefault("rules", [])
                if not isinstance(rules, list):
                    rules = []
                    group["rules"] = rules
                existing_exprs = {
                    str(r.get("expr", "")) for r in rules if isinstance(r, dict)
                }
                added_here = 0
                for rule in new_rules:
                    if rule["expr"] in existing_exprs:
                        continue
                    rules.append(rule)
                    existing_exprs.add(rule["expr"])
                    added_here += 1
                if added_here:
                    art.content = _coverage_bind_preserve_header(
                        art.content,
                        yaml.dump(data, default_flow_style=False, sort_keys=False),
                    )
                    if not art.quality or "score" not in art.quality:
                        art.quality = dict(_ORIENTATION_BIND_QUALITY)
                    art.derivations.append(
                        DerivationTrace(
                            field="affordance_coverage_bind_orientation_alert",
                            source=f"affordance_map.source_backed.metric_locus.{svc_id}",
                            transformation=f"{added_here} bridge-orientation alert bind(s)",
                            tier="affordance_map",
                        )
                    )
                    bridge_added = added_here
            else:
                content_dict = {
                    "groups": [
                        {"name": f"{svc_id}.coverage_bind", "rules": new_rules}
                    ]
                }
                header = (
                    f"# AffordanceMap coverage-bind bridge orientation for {svc_id}\n"
                    f"# Generated by startd8 observability artifact generator\n\n"
                )
                body = yaml.dump(content_dict, default_flow_style=False, sort_keys=False)
                artifacts.append(
                    ArtifactResult(
                        artifact_type="alert_rule",
                        service_id=svc_id,
                        output_path=f"alerts/{svc_id}-coverage-bind-alerts.yaml",
                        status="generated",
                        content=header + body,
                        quality=dict(_ORIENTATION_BIND_QUALITY),
                        derivations=[
                            DerivationTrace(
                                field="affordance_coverage_bind_orientation_alert",
                                source=f"affordance_map.source_backed.metric_locus.{svc_id}",
                                transformation=(
                                    f"{len(new_rules)} bridge-orientation alert bind(s) "
                                    "(new file)"
                                ),
                                tier="affordance_map",
                            )
                        ],
                    )
                )
                bridge_added = len(new_rules)

        if system_added or bridge_added:
            evidence["services"][svc_id] = {
                "families_admitted": len(families),
                "system_added": system_added,
                "bridge_added": bridge_added,
            }
    return evidence


#: FR-1 landed RED panel group — distinct from every other panel group so a
#: reader can see which panels exist because of the locus-biased RED bind.
_RED_BIND_GROUP_PREFIX = "RED (locus-grounded)"


def _apply_affordance_red_bind_panels(
    artifacts: List[Any],
    services: List[Any],
    affordance_map: Any = None,
) -> Dict[str, Any]:
    """pilot-gap_red_dashboards Step 2 — land the already-built locus-biased
    ``gen.emit_red_panels`` output onto the IN-MEMORY ``dashboard_spec``
    content, BEFORE ``_write_artifacts`` runs (FR-1, FR-2, FR-3, FR-7).

    Generator input, not a post-hoc file append or full-file replace: mirrors
    gap #2's Step 2/2a (``_apply_affordance_coverage_bind_panels``) write-
    ordering exactly — one write-collision resolution for the shared
    ``dashboards/{svc}-dashboard-spec.yaml`` file, not two (FR-7). Reuses the
    already-dogfooded ``_locus_red_dashboard_yaml``/``_pick_red_families``
    (FR-1, FR-1b) verbatim for family selection and panel-expr construction —
    no second RED-panel-shape implementation.

    Does **not** reuse gap #2's ``_admit_affordance_metric_families`` for RED
    family pick (RED needs ``plan_affordance_actions``'s emit_red filter +
    transport-only skip + audited ``_LOCUS_BLOCKING`` reasons). Gap #2 admit
    now shares the same ``source_backed``|``partial`` honesty window for
    coverage expected-set / orientation, but RED still goes through the
    planner so skip reasons stay verbatim (R3-F2 / Accidental-Complexity).

    APPENDS the (at most 3) RED panels into the existing top-level ``panels``
    list rather than replacing the whole document, so this bind composes with
    the primary generator's own panels and with gap #2's coverage bind instead
    of clobbering either. Dedup is by REFERENCED METRIC NAME (the same
    extractor gap #2's PICR fix uses), so a family already panelled by any
    other bind is not re-panelled.

    Returns ``{"export_disposition": ..., "services": {svc_id: {"families_admitted":
    n, "panels_added": n, "locus_families": [...]}}, "skipped": {svc_id: reason}}``.
    """
    from .affordance_map_consume import (
        AffordanceMapEntry,
        GEN_EMIT_RED,
        LoadResult,
        _LOCUS_BLOCKING,
        _locus_red_dashboard_yaml,
        load_affordance_map,
        plan_affordance_actions,
    )

    try:
        from startd8.validators.observability_artifact_checks import (
            _normalize_metric_name,
            extract_referenced_metrics,
        )
    except ImportError:  # pragma: no cover
        extract_referenced_metrics = None  # type: ignore[assignment]
        _normalize_metric_name = None  # type: ignore[assignment]

    evidence: Dict[str, Any] = {
        "export_disposition": _EXPORT_NO,
        "services": {},
        "skipped": {},
    }
    if affordance_map is None:
        return evidence

    if isinstance(affordance_map, LoadResult):
        loaded = affordance_map
    elif isinstance(affordance_map, (tuple, list)) and affordance_map and all(
        isinstance(x, AffordanceMapEntry) for x in affordance_map
    ):
        loaded = LoadResult(entries=list(affordance_map))
    elif isinstance(affordance_map, (str, Path, dict, list)):
        loaded = load_affordance_map(affordance_map)
    else:
        return {**evidence, "export_disposition": _EXPORT_MALFORMED}

    if loaded.error:
        return {**evidence, "export_disposition": _EXPORT_MALFORMED}
    if loaded.source_truncated:
        return {**evidence, "export_disposition": _EXPORT_STALE}

    known_ids = [s.service_id for s in services]
    plan = plan_affordance_actions(loaded.entries, known_ids)
    evidence["export_disposition"] = _EXPORT_OK

    for sk in plan.skips:
        if sk.affordance_id == GEN_EMIT_RED:
            evidence["skipped"][sk.service_id] = sk.reason

    by_service_artifact = {
        a.service_id: a
        for a in artifacts
        if a.artifact_type == "dashboard_spec" and a.status == "generated"
    }
    for action in plan.actions:
        if action.affordance_id != GEN_EMIT_RED:
            continue
        loci = list(action.loci_used or [])
        red_yaml = _locus_red_dashboard_yaml(action.service_id, loci)
        if not red_yaml:
            evidence["skipped"][action.service_id] = "locus_families_unusable"
            continue
        red_doc = yaml.safe_load(red_yaml) or {}
        red_spec = red_doc.get("spec") or {}
        red_panels = red_spec.get("panels") or []
        red_families = red_spec.get("locus_families") or []

        art = by_service_artifact.get(action.service_id)
        if art is None or not art.content:
            evidence["skipped"][action.service_id] = "no_dashboard_artifact"
            continue
        try:
            data = yaml.safe_load(art.content) or {}
        except Exception:
            logger.warning(
                "red-bind: could not parse dashboard_spec YAML for %s — skipping bind",
                action.service_id,
            )
            evidence["skipped"][action.service_id] = "unparseable_dashboard_spec"
            continue
        panels = data.get("panels")
        if not isinstance(panels, list):
            evidence["skipped"][action.service_id] = "no_panels_container"
            continue

        existing = {str(p.get("expr", "")) for p in panels if isinstance(p, dict)}
        already_named = (
            extract_referenced_metrics(existing) if extract_referenced_metrics else set()
        )
        added_panels: List[Dict[str, Any]] = []
        used_families: List[str] = []
        # red_panels[i] and red_families[i] are appended in lockstep by
        # _locus_red_dashboard_yaml (rate, then error, then duration — only for
        # populated slots), so a positional zip pairs each panel with its family
        # without re-deriving the association from the expr text.
        for panel, fam in zip(red_panels, red_families):
            expr = str(panel.get("expr", ""))
            if expr in existing:
                continue
            if _normalize_metric_name and _normalize_metric_name(fam) in already_named:
                continue
            added_panels.append({**panel, "group": _RED_BIND_GROUP_PREFIX})
            existing.add(expr)
            used_families.append(fam)

        if not added_panels:
            evidence["skipped"][action.service_id] = "red_already_complete_locus"
            continue

        panels[:0] = added_panels  # prepend — RED panels lead the dashboard
        data["panels"] = panels
        header_lines: List[str] = []
        for line in art.content.splitlines(keepends=True):
            if line.startswith("#") or not line.strip():
                header_lines.append(line)
                continue
            break
        art.content = "".join(header_lines) + yaml.dump(
            data, default_flow_style=False, sort_keys=False
        )
        art.derivations.append(
            DerivationTrace(
                field="affordance_red_bind_panels",
                source=f"affordance_map.{action.locus_status}.metric_locus.{action.service_id}",
                transformation=(
                    f"{len(added_panels)} locus-biased RED panel(s) added "
                    "(rate/error/duration, distinct families)"
                ),
                tier="affordance_map",
            )
        )
        evidence["services"][action.service_id] = {
            "families_admitted": len(red_families),
            "panels_added": len(added_panels),
            "locus_families": sorted(set(used_families)) or sorted(set(red_families)),
        }

    # FR-5/R3-F2 audit completeness: an element outside `services` (e.g.
    # `business-criticality`, a synthetic artifact this generator's own
    # per-service loop never processes) fails `match_service_id` before
    # `plan_affordance_actions` ever inspects its `affordance_ids`, so its skip
    # is recorded with `affordance_id="(unresolved)"` — not `GEN_EMIT_RED` —
    # and the `plan.skips` loop above misses it. Record every raw entry that
    # DECLARES `gen.emit_red_panels` and never produced a bind (checked last,
    # after every real plan action has already claimed its service_id), so
    # "business-criticality produces no artifact" (FR-5) is explicit in
    # evidence, not merely implicit in what's absent.
    for entry in loaded.entries:
        eid = entry.element_id or ""
        if not eid or eid in evidence["services"] or eid in evidence["skipped"]:
            continue
        if GEN_EMIT_RED not in (entry.affordance_ids or []):
            continue
        reason = (
            f"locus_blocked:{entry.locus_status}"
            if entry.locus_status in _LOCUS_BLOCKING
            else ("not_a_generator_service" if eid not in known_ids else "no_plan_action")
        )
        evidence["skipped"][eid] = reason

    return evidence


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
    portal_coverage: Optional[Dict[str, Any]] = None,
    affordance_map: Any = None,
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

    # REQ_NOTIFICATION_POLICY FR-1: thread the authored `alerting.receivers` into the
    # business context BEFORE per-service generation, so notification_policy binds to the
    # DECLARED channel type+secret (Receiver.target) instead of guessing from string shape.
    # Parsed once here via the single canonical entry point (from_observability_yaml) and
    # reused by the domain-alert path below (no double parse). Absent path ⇒ no receivers ⇒
    # routed channels with no matching receiver become UNRESOLVED-REQUIRED (FR-3/FR-3a).
    _obs_spec = None
    if observability_yaml_path is not None and Path(observability_yaml_path).exists():
        from .spec import from_observability_yaml

        _obs = (
            yaml.safe_load(Path(observability_yaml_path).read_text(encoding="utf-8"))
            or {}
        )
        _obs_spec = from_observability_yaml(_obs)
        business.receivers = list(_obs_spec.receivers)

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

    # Build the effective MetricDescriptor once per service (Step 3, FR-7
    # terminus). ServiceHints carries the profile + per-axis overrides that
    # ContextCore resolved from the manifest via onboarding metadata; an empty
    # profile falls back to semconv-{transport} (byte-identical to prior output).
    descriptors: Dict[str, MetricDescriptor] = {
        service.service_id: resolve_descriptor(
            profile=service.metric_profile or None,
            kinds=service.kinds,  # #226 FR-6: kind wins over transport
            transport=service.transport,
            overrides=service.descriptor_overrides,
            # REQ-01 FR-3: manifest-declared metric profiles (built-in wins on collision).
            declared_profiles=business.metric_profiles,
        )
        for service in services
    }

    # FR-9 coverage/gap accumulation — one typed home (complexity-distiller D1). Each field
    # carries the same lineage the 11 inline lists did (#226/#230/#274/#286/#300/#307/#308);
    # see CoverageReport for the per-field notes and the byte-identity serialization contract.
    coverage = CoverageReport()
    for service in services:
        descriptor = descriptors[service.service_id]
        for gen_fn, artifact_type, output_prefix in _GENERATORS:
            report.artifacts.append(
                _generate_one(
                    gen_fn,
                    service,
                    business,
                    artifact_type,
                    output_prefix,
                    descriptor,
                )
            )
        # FR-5: functional-requirement SLOs for declared non-triplet signal_kinds.
        func_slo = generate_functional_slos(service, business, descriptor)
        if func_slo.status == "generated":
            report.artifacts.append(func_slo)
        _q = func_slo.quality or {}
        coverage.emitted.extend(_q.get("emitted_fr_ids", []))
        coverage.unfulfilled.extend(_q.get("unfulfilled", []))
        # #286: base RED SLIs bound to declared-emitted series (precedence declared > suppress >
        # convention; the convention RED for a bound kind is dropped in _service_sli_kinds).
        decl_slo = generate_declared_base_slos(service, business, descriptor)
        if decl_slo.status == "generated":
            report.artifacts.append(decl_slo)
        _dq = decl_slo.quality or {}
        coverage.bound_declared_series.extend(_dq.get("bound_declared_series", []))
        coverage.deferred_declared_kinds.extend(_dq.get("deferred_declared_kinds", []))
        # #300 D2: declared-series FUNCTIONAL SLOs (saturation/queue_depth/…) — a separate lane/doc
        # (FR-6); threshold-deferred/type-mismatch/precedence-skip candidates feed the same gap channel.
        declf_slo = generate_declared_functional_slos(service, business, descriptor)
        if declf_slo.status == "generated":
            report.artifacts.append(declf_slo)
        _dfq = declf_slo.quality or {}
        coverage.bound_declared_functional.extend(_dfq.get("bound_declared_functional", []))
        coverage.deferred_declared_kinds.extend(_dfq.get("deferred_declared_kinds", []))
        # #307: per-span RED SLOs bound to declared span signals via span-metrics (a third declared lane).
        decls_slo = generate_declared_span_slos(service, business, descriptor)
        if decls_slo.status == "generated":
            report.artifacts.append(decls_slo)
        _dsq = decls_slo.quality or {}
        coverage.bound_declared_span.extend(_dsq.get("bound_declared_span", []))
        coverage.deferred_declared_kinds.extend(_dsq.get("deferred_declared_kinds", []))
        # #308 P0: synthetic-probe freshness SLIs — recorded pending a runner (writes NO slos/ file).
        probe_slo = generate_declared_probe_slos(service, business, descriptor)
        _ppq = probe_slo.quality or {}
        coverage.pending_probes.extend(_ppq.get("pending_probes", []))
        # #308 P1: the runnable probe-spec artifact (probe-specs/, excluded from PromQL replay).
        probe_spec = generate_declared_probe_specs(service, business, descriptor)
        if probe_spec.status == "generated":
            report.artifacts.append(probe_spec)
        # FR-9: a service that resolves to ∅ SLI kinds (non-request, nothing declared)
        # is observed by nothing — surface it rather than silently emitting nothing.
        _svc_signals = [
            f.signal_kind
            for f in (business.functional_requirements or [])
            if f.service in (None, "", service.service_id)
        ]
        # Resolve the SLI kinds once (pure fn) — reused by the ∅-coverage check here and the
        # base-RED gate below (was re-derived at both sites: complexity-distiller S8).
        _sli_kinds = resolve_sli_kinds(service.kinds, _svc_signals, service.transport)
        _observed_by_nothing = not _sli_kinds
        if _observed_by_nothing:
            coverage.empty_services.append(service.service_id)
        # #230/#231/#233: recognized-but-ungrounded kind — name it, cross-reference the
        # ∅ symptom (LH-1: one story, not two gaps), and give a KIND-SPECIFIC next step
        # (P1a: cron→freshness, ml_inference→saturation/lag — shape, never a value).
        for _k in service.kinds:
            if _k in UNGROUNDED_KINDS:
                _sugg = suggested_signals_for(_k)
                coverage.ungrounded_kinds.append(
                    {
                        "service": service.service_id,
                        "kind": _k,
                        # LH-1: an ungrounded service with no declared FRs is ALSO in
                        # empty_services; tag it so a reader sees the cause, not two gaps.
                        "observed_by_nothing": _observed_by_nothing,
                        # P1a: the kind-specific signal SHAPE (not a value) — structured so a
                        # surface can render it terse without parsing the prose reason.
                        "suggested_signals": list(_sugg),
                        "reason": (
                            f"kind {_k!r} is recognized but has no grounded metric profile yet "
                            f"(OQ-5); its default SLIs are deferred rather than invented. Declare "
                            f"a functional[] FR with signal_kind {'/'.join(_sugg)} + target to "
                            f"emit an SLO, or await a grounded profile."
                        ),
                    }
                )
        # #274 / REQ-CCL-106 — the two-tier ADR-003 handling, keyed on the emission-surface signal.
        # BASE_RED_KINDS is single-sourced (metric_descriptor) so this gate can't drift from the
        # declared-series covers-filter or the convention-triplet suppression.
        _ms = getattr(service, "metrics_surface", "")
        _red_before = BASE_RED_KINDS & _sli_kinds
        if _ms in NON_EMITTING_CONVENTION_SURFACES and _red_before:
            # STRICT: the surface is DECLARED non-emitting → the base RED SLIs were suppressed
            # (dropped from _service_sli_kinds) so no dead SLI ships. Record the real gap.
            coverage.suppressed_base_metrics.append(
                {
                    "service": service.service_id,
                    "metrics_surface": _ms,
                    "suppressed_sli_kinds": sorted(_red_before),
                    "reason": (
                        f"base RED SLIs suppressed — metrics_surface={_ms!r} does not emit the OTel-"
                        f"convention meter metric they query (REQ-CCL-106 / #274). Declare the emitted "
                        f"series (manifest_declared) or a functional[] FR with a real target to get SLIs."
                    ),
                }
            )
        elif (
            # ADVISORY (graceful fallback, #277): the surface is UNKNOWN (not declared) but this is
            # the traces-only RISK profile — flag it, don't suppress (would false-gap a real HTTP svc).
            not _ms
            and service.has_traces
            and service.convention_metrics
            and not service.declared_metrics
            and _red_before
        ):
            coverage.unverified_base_metrics.append(
                {
                    "service": service.service_id,
                    "convention_metrics": [m.name for m in service.convention_metrics],
                    "reason": (
                        "base RED SLIs use convention metrics derived from the service kind, NOT "
                        "verified as emitted (trace-instrumented, no manifest_declared, no declared "
                        "metrics_surface). If the subject is traces-only or a different metric surface, "
                        "the SLI won't evaluate — declare `Metrics surface:` in the plan (REQ-CCL-106) "
                        "for the strict fix, or declare the emitted metric. Advisory (ADR-003 / #274)."
                    ),
                }
            )

    # Serialize the typed accumulator to report.fr_coverage. to_fr_coverage() preserves the exact
    # prior contract: 8 keys always, {bound_declared_functional, bound_declared_span, pending_probes}
    # present only when non-empty (byte-identity vs pre-#300/#307/#308 goldens).
    report.fr_coverage = coverage.to_fr_coverage()

    report.services_processed = len(services)
    report.services_skipped = len([s for s in services if not s.convention_metrics])

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
    # #285: a ServiceMonitor is a Prometheus /metrics scrape config; suppress it for a service
    # whose declared metrics_surface serves NO scrape endpoint (traces_only/none) — else it ships a
    # dead scrape target (the ADR-003 FP-3 the Mastodon pilot found). Mirrors the base-RED gate above.
    _suppressed_scrape: List[Dict[str, Any]] = []
    for atype, (gen_fn, output_prefix) in _EXTENDED_PER_SERVICE_GENERATORS.items():
        if atype not in declared or atype in owned_elsewhere:
            continue
        for service in services:
            if (
                atype == "service_monitor"
                and getattr(service, "metrics_surface", "") in NON_SCRAPEABLE_SURFACES
            ):
                _suppressed_scrape.append(
                    {
                        "service": service.service_id,
                        "metrics_surface": service.metrics_surface,
                        "reason": (
                            f"ServiceMonitor suppressed — metrics_surface="
                            f"{service.metrics_surface!r} exposes no Prometheus /metrics scrape "
                            f"endpoint, so the scrape config would target nothing (#285 / ADR-003). "
                            f"Declare a scrapeable surface (prometheus_exporter/node_metrics) to emit one."
                        ),
                    }
                )
                continue
            # Runtime-correct artifact set: a ServiceMonitor is a Prometheus-Operator (k8s) CRD. On a
            # NON-k8s target (docker-compose, systemd, bare process) it targets a resource that does not
            # exist — a dead k8s artifact (ADR-003 FP-3, the Harbor pilot). Suppress + record when the
            # service's target kind is KNOWN non-k8s; empty/unknown/k8s kinds keep emitting (conservative,
            # no regression to today's k8s default). The scrapeable surface is still real — a compose
            # subject wants a static prometheus scrape_config, not a ServiceMonitor (follow-up).
            if atype == "service_monitor":
                _tk = str((_target_for(service.service_id, business.targets) or {}).get("kind", "")).strip().lower()
                # Fail-closed on an EXPLICIT unknown runtime: a ServiceMonitor is a k8s-operator CRD, so
                # it needs POSITIVE evidence of k8s. When the probe authored spec.deployment.runtime as
                # 'unknown' (it could not confirm the deployment shape — e.g. Thanos, deployed many ways),
                # a defaulted `Deployment` target is NOT that evidence → suppress (else the dead-k8s FP-3).
                # An absent runtime stays today's k8s default (back-compat); a KNOWN non-k8s target kind is
                # still suppressed by the kind check below.
                _rt = str(getattr(business, "deployment_runtime", "") or "").strip().lower()
                if _rt == "unknown" or _tk in _NON_K8S_TARGET_KINDS:
                    _suppressed_scrape.append(
                        {
                            "service": service.service_id,
                            "target_kind": _tk,
                            "deployment_runtime": _rt or None,
                            "reason": (
                                f"ServiceMonitor suppressed — "
                                + (
                                    f"deployment runtime is {_rt!r} (k8s not confirmed), so a "
                                    if _rt == "unknown"
                                    else f"target kind {_tk!r} is not a Kubernetes workload, so a "
                                )
                                + "Prometheus-Operator ServiceMonitor CRD has nothing to select (a dead "
                                "k8s artifact). A static prometheus scrape_config is the runtime-correct "
                                "scrape for this target."
                            ),
                        }
                    )
                    continue
            report.artifacts.append(
                _generate_one(
                    gen_fn,
                    service,
                    business,
                    atype,
                    output_prefix,
                    descriptors[service.service_id],
                )
            )
    # #285: fold the scrape-config suppressions into fr_coverage (assembled above), same shape as
    # suppressed_base_metrics — an honest gap, so `observability compare` can surface it.
    report.fr_coverage["suppressed_scrape_configs"] = _suppressed_scrape

    # Closure 3A / Gap 2 + REQ-OAT-052: record declared-but-unproduced types as
    # explicit skips carrying skip_reason (owned_elsewhere | unimplemented) + owner,
    # so coverage reporting is honest, not silently partial.
    _record_unimplemented_artifact_types(report, owned_elsewhere)

    # Value round-2 #1: the project-level business-criticality dashboard CONSUMES the
    # collector_enrichment span-metrics dimension. Generated HERE (before the Grafana-JSON render)
    # so it renders like every other dashboard_spec; presence-gated on criticality (self-skips
    # otherwise). Its sibling — the enrichment processor itself — is generated further below.
    _bcd = _repair_and_validate(
        generate_business_criticality_dashboard(services, business, report), business
    )
    if _bcd.status != "skipped":
        report.artifacts.append(_bcd)

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
            business,
            services,
            report,
            metadata,
            output_dir,
            persona=portal_persona,
            provision_url=portal_provision_url,
            dry_run=dry_run,
            coverage=portal_coverage,
        )
        if portal_result is not None:
            report.artifacts.append(portal_result)

    # M1 / FR-OAA-12: domain alert rules from observability.yaml. Declared thresholds become ACTIVE
    # rules — closing the gap the convention path leaves as `_domain_alert_todo_block` stubs. Strictly
    # additive + opt-in: an absent observability_yaml_path ⇒ no new artifact and RED output stays
    # byte-identical. The renderer is taxonomy-free; the _stamp_taxonomy pass below stamps the result.
    if _obs_spec is not None:
        from .alert_renderer import render_domain_alert_rules
        from .dashboard_renderer import render_domain_dashboard

        _spec = _obs_spec  # parsed once above (single from_observability_yaml call)
        _pid = business.project_id or "domain"
        # E1: the SAME observability.yaml drives both — domain alert rules AND a domain dashboard.
        # Both additive/opt-in; the renderers are taxonomy-free (the _stamp_taxonomy pass stamps them).
        report.artifacts.append(render_domain_alert_rules(_spec, project_id=_pid))
        report.artifacts.append(render_domain_dashboard(_spec, project_id=_pid))

    # collector_enrichment (REQ_COLLECTOR_ENRICHMENT FR-3): the OTTL transform/business processor,
    # sourced from per-service hint["business"] (FR-1b). PRESENCE-gated (not declaration-gated): the
    # generator self-skips when no service carries business context, so a manifest without business
    # context is byte-identical to a pre-feature run (SOTTO). Runs before capability_index so the
    # inventory can include it.
    try:
        _ce = generate_collector_enrichment(services, business, report)
        if _ce.status != "skipped":
            # LH-3: score it like the triplet (attaches a quality dict via the CE-1xx checks).
            _ce = _repair_and_validate(_ce, business)
            report.artifacts.append(_ce)
            # LH-2: make the $0 pass legible — surface the counts (already in fr_coverage) on the console.
            _cec = report.fr_coverage.get("collector_enrichment") or {}
            logger.info(
                "collector_enrichment: %d services enriched, %d statements, criticality_dimension=%s",
                _cec.get("services_enriched", 0),
                _cec.get("statements", 0),
                _cec.get("criticality_dimension", False),
            )
            # Value round-2 #2: name the services still missing business context, so the operator
            # can complete their manifest instead of discovering the gap during an incident.
            _missing = _cec.get("services_missing") or []
            if _missing:
                logger.warning(
                    "collector_enrichment: %d service(s) have NO business context (add "
                    "criticality/owner in the manifest): %s",
                    len(_missing),
                    ", ".join(_missing),
                )
    except Exception:
        logger.exception("collector_enrichment generation failed")

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

    # Gap 3 / Closure 2 + product-gap evaluator union (Step 1): expected metric set
    # per service drives semantic metric-coverage. Computed for dry_run too so
    # report.metric_expected matches non-dry for the same inputs (FR-4).
    expected_build = build_service_metrics_expected(
        services, affordance_map=affordance_map
    )
    service_metrics: Dict[str, Set[str]] = expected_build["service_metrics"]
    report.metric_expected = {
        "expected_sources": expected_build["expected_sources"],
        "export_disposition": expected_build["export_disposition"],
        "diagnostics": expected_build["diagnostics"],
        "service_metrics": {
            sid: sorted(names) for sid, names in service_metrics.items()
        },
    }

    # Step 2/2a (FR-2/FR-2b): land the AffordanceMap-derived coverage bind onto the
    # IN-MEMORY dashboard_spec content — BEFORE _write_artifacts — so the bind is
    # generator input (survives regen) and is scored by _write_quality_report below
    # in the same pass, not destroyed by the next _write_artifacts (R1-S1/R1-S2).
    # Computed unconditionally (dry_run included) so report.coverage_bind mirrors
    # metric_expected's dry-run/non-dry parity contract (FR-4); only the disk write
    # below is gated on dry_run.
    # pilot-gap_red_dashboards Step 2 (FR-1/FR-2/FR-3/FR-7): land the locus-biased
    # RED bind onto the in-memory dashboard_spec content BEFORE the coverage bind
    # (and BEFORE _write_artifacts) — generator input, computed unconditionally
    # (dry_run included) for the same dry-run/non-dry parity contract FR-2b
    # established. MUST run first: the coverage bind below panels EVERY admitted
    # family it sees not-yet-referenced, so if it ran first it would already claim
    # the RED slots' families (source_backed services) and the RED bind's own
    # dedup would then skip all three as "already covered" — silently landing zero
    # RED-labeled panels. Running RED first lets it claim its (at most 3) families
    # with Request/Error/Duration titles; the coverage bind's referenced-name dedup
    # then fills in only the REMAINING admitted families, so the two binds compose
    # on the shared file (FR-7) instead of one erasing the other.
    report.red_bind = _apply_affordance_red_bind_panels(
        report.artifacts, services, affordance_map=affordance_map
    )

    report.coverage_bind = _apply_affordance_coverage_bind_panels(
        report.artifacts, services, affordance_map=affordance_map
    )
    # Orientation residual (system/bridge): same admit set → SLO + alert_rule binds
    # so avg_metric_coverage_system/bridge can leave 0 on tip honesty (FR-1/FR-2 of
    # product-gap_0_metric_coverage_orientation_bind). Runs after panel bind so
    # human coverage is unchanged; before _write_artifacts for write-collision safety.
    report.orientation_bind = _apply_affordance_coverage_bind_orientation(
        report.artifacts, services, affordance_map=affordance_map
    )

    # OBS-200a tip honesty (bus 576bf153 / tip 21398c57): AffordanceMap RED /
    # coverage binds mutate dashboard_spec *content* after per-artifact
    # ``_repair_and_validate`` cached ``a.quality``. Re-score so
    # observability-quality.json matches the panels that land on disk (tip
    # re-score already PASSed OBS-200a on the written specs while quality
    # still listed RED 0%).
    _rescore_dashboard_specs_after_binds(report.artifacts, services)

    if not dry_run:
        _write_artifacts(report.artifacts, output_dir)
        _write_index(report, business, onboarding_metadata_path, output_dir)
        _write_quality_report(
            report.artifacts,
            output_dir,
            service_metrics=service_metrics,
            expected_sources=expected_build["expected_sources"],
            export_disposition=expected_build["export_disposition"],
        )

    return report


def _rescore_dashboard_specs_after_binds(
    artifacts: List[Any],
    services: List[Any],
) -> int:
    """Refresh ``dashboard_spec.quality`` after AffordanceMap panel binds.

    Returns the number of dashboard artifacts re-scored.
    """
    try:
        from startd8.validators.observability_artifact_checks import validate_dashboard
    except ImportError:  # pragma: no cover
        return 0

    transport_by_svc = {
        getattr(s, "service_id", ""): getattr(s, "transport", None) or None
        for s in services or ()
    }
    n = 0
    for art in artifacts:
        if art.artifact_type != "dashboard_spec" or art.status != "generated":
            continue
        if not art.content:
            continue
        # Only re-score when a quality dict was previously attached (Phase 4.5).
        if not art.quality or "score" not in art.quality:
            continue
        transport = transport_by_svc.get(art.service_id)
        try:
            vr = validate_dashboard(
                art.content,
                art.output_path,
                autofix=False,
                service_id=art.service_id,
                transport=transport,
            )
        except Exception:
            logger.exception(
                "post-bind dashboard re-score failed for %s", art.service_id
            )
            continue
        art.quality = {
            "score": round(vr.score, 4),
            "checks_passed": vr.checks_passed,
            "checks_total": vr.checks_total,
            "issues": [
                {"check": i.check, "severity": i.severity, "message": i.message}
                for i in vr.issues
            ],
            "repairs_applied": list(art.quality.get("repairs_applied") or [])
            + list(vr.repairs_applied or []),
            "rescored_after_affordance_bind": True,
        }
        n += 1
    return n


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
        cat: round(sum(flags) / len(flags), 4) for cat, flags in sorted(by_cat.items())
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
        if a.status != "generated" or not a.content:
            continue
        # Score any generated artifact that lacks a structural *score* — not just
        # those with no quality dict at all. The declared-base/functional/span/probe
        # SLO generators pre-attach a binding-metadata quality dict
        # (``bound_declared_series`` / ``deferred_declared_kinds``) that carries NO
        # ``"score"``; the old ``a.quality is not None`` guard let that metadata
        # shadow the scorer, so SLOs were generated-but-unscored. That both violated
        # the scored==generated invariant (REQ-OAT-050) and dropped SLO content from
        # the metric-coverage feed in ``_write_quality_report`` (which iterates only
        # scored artifacts), pinning ``metric_coverage_system`` to 0.0 (the Harbor
        # false-zero, bus 01968b33).
        if a.quality is not None and "score" in a.quality:
            continue
        contract = contracts.get(a.artifact_type)
        if not contract:
            continue
        scored_quality = validate_extended_artifact(a.content, contract).to_quality()
        if a.quality:
            # Layer the structural score on top; preserve the binding/orientation
            # metadata the generator attached (bound_declared_series, etc.).
            merged = dict(a.quality)
            merged.update(scored_quality)
            a.quality = merged
        else:
            a.quality = scored_quality


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
    result: ArtifactResult,
    dash_services: Set[str],
    run_services: Set[str],
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
    handoff_exists = (
        result.service_id in dash_services or result.service_id in run_services
    )
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
                "triplet generator; ignoring the cede (counted as produced)",
                atype,
            )
            ceded = False
        if ceded:
            owner = owned_elsewhere[atype]
            report.artifacts.append(
                _stamp_taxonomy(
                    ArtifactResult(
                        artifact_type=atype,
                        service_id=project_id,
                        output_path=f"(owned by {owner}: {atype})",
                        status="skipped",
                        error_message=f"declared but owned by {owner}; produced elsewhere",
                        skip_reason="owned_elsewhere",
                        owner=owner,
                        route_state=RouteState.CONTEXTCORE_OWNED.value,
                    )
                )
            )
            continue
        if atype in _IMPLEMENTED_ARTIFACT_TYPES:
            continue
        report.artifacts.append(
            _stamp_taxonomy(
                ArtifactResult(
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
                )
            )
        )


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
                        error_message = (
                            "workflow reported success but no JSON file found"
                        )
                else:
                    error_message = (
                        getattr(result, "error", None) or "conversion failed"
                    )
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
    # LH-2: roll the collector_enrichment counts into the index summary so the manifest is
    # self-describing (services enriched / statements / dimension) without opening the artifact.
    _ce_cov = report.fr_coverage.get("collector_enrichment")
    if _ce_cov:
        summary["collector_enrichment"] = _ce_cov

    # REQ-OAT-052: honest, route-aware artifact-type coverage. Types ceded to
    # another component (skip_reason=owned_elsewhere) are EXCLUDED from the declared
    # denominator so a correct cede does not read as a false <1.0 FAIL (R4-F2).
    if report.declared_artifact_types:
        declared = set(report.declared_artifact_types)
        owned = {
            a.artifact_type
            for a in report.artifacts
            if a.skip_reason == "owned_elsewhere"
        }
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
        # REQ-OAT-041: cat-4/5/6 (project / AI-agent / delivery) metrics have no
        # generator yet; surface the count so the "awaiting a category home" gap is
        # visible, not silently mixed into service observability.
        summary["metrics_awaiting_category_home"] = sum(
            1
            for r in report.route_states
            if r.get("category")
            in (Category.PROJECT.value, Category.AI_AGENT.value, Category.DELIVERY.value)
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
                # #226 FR-5: functional-SLO artifacts carry a non-score quality
                # dict (emitted_fr_ids/unfulfilled), so gate on the key, not truthiness.
                **(
                    {"quality_score": a.quality["score"]}
                    if a.quality and "score" in a.quality
                    else {}
                ),
            }
            for a in report.artifacts
        ],
        # Per-metric route_state classification (REQ-OBS-SHARED-004 validation surface).
        "metric_route_states": report.route_states,
        "derivation_rules": list(seen_rules.values()),
    }

    # Quality summary (REQ-KZ-OBS-730). Only artifacts with an actual `score`
    # count — functional-SLO artifacts carry a scoreless coverage dict (#226 FR-5).
    scored = [a for a in report.artifacts if a.quality and "score" in a.quality]
    if scored:
        by_type: Dict[str, List[float]] = {}
        for a in scored:
            by_type.setdefault(a.artifact_type, []).append(a.quality["score"])
        quality_summary: Dict[str, Any] = {}
        for atype, scores in by_type.items():
            quality_summary[f"avg_{atype}_score"] = round(sum(scores) / len(scores), 4)
        all_scores = [a.quality["score"] for a in scored]
        quality_summary["avg_composite_score"] = round(
            sum(all_scores) / len(all_scores), 4
        )
        quality_summary["artifacts_scored"] = len(scored)
        quality_summary["total_issues"] = sum(
            len(a.quality.get("issues", [])) for a in scored
        )
        quality_summary["total_repairs"] = sum(
            len(a.quality.get("repairs_applied", [])) for a in scored
        )
        index["quality_summary"] = quality_summary

    # FR-9 (#226): surface FR/SLI-kind coverage in the manifest, but only when there
    # is something to report — a run with no functional[] stays byte-identical.
    # NB: gate on ANY non-empty value, NOT a hardcoded key subset. The prior fixed list
    # ({empty_services, unfulfilled, emitted, ungrounded_kinds, unverified_base_metrics,
    # suppressed_base_metrics}) drifted from the dict and omitted the #286/#300 positive-
    # binding keys (bound_declared_series/-functional, deferred_declared_kinds) — so a run
    # whose ONLY coverage signal was a declared binding (no suppression) silently dropped
    # fr_coverage from the manifest and `observability compare` read {}. Values-based gating
    # can't drift as new keys are added.
    if any(report.fr_coverage.values()):
        index["fr_coverage"] = report.fr_coverage

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
    expected_sources: Optional[Dict[str, Dict[str, Any]]] = None,
    export_disposition: str = "",
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

    # A scoreless quality dict (functional-SLO coverage, #226 FR-5) is not a
    # scored artifact — gate on the `score` key so it doesn't trip the subscripts below.
    scored = [
        a
        for a in artifacts
        if a.quality and "score" in a.quality and a.status == "generated"
    ]
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
            cov_human_r = compute_metric_coverage(
                expected, svc_human_contents.get(svc_id, [])
            )
            cov_system_r = compute_metric_coverage(
                expected, svc_system_contents.get(svc_id, [])
            )
            cov_bridge_r = compute_metric_coverage(
                expected, svc_bridge_contents.get(svc_id, [])
            )
            cov_human = cov_human_r.score
            cov_system = cov_system_r.score
            cov_bridge = cov_bridge_r.score
            svc_data["metric_coverage_human"] = cov_human
            svc_data["metric_coverage_system"] = cov_system
            svc_data["metric_coverage_bridge"] = cov_bridge
            # Continuity aliases (REQ-OAT-051): names retained for downstream readers.
            svc_data["metric_coverage_dashboarded"] = cov_human
            svc_data["metric_coverage_alerted"] = cov_bridge
            # Shared denominator across orientations (CRP R1-S6).
            svc_data["expected_count"] = len(cov_human_r.expected)
            if expected_sources and svc_id in expected_sources:
                src = dict(expected_sources[svc_id])
                src["expected_normalized"] = len(cov_human_r.expected)
                # sum(source counts) >= raw_union >= normalized
                src["sources_sum"] = (
                    int(src.get("convention", 0))
                    + int(src.get("declared", 0))
                    + int(src.get("emitted_series", 0))
                    + int(src.get("affordance_loci", 0))
                )
                svc_data["expected_sources"] = src

        all_scores = svc_all_scores.get(svc_id, [])
        structural = sum(all_scores) / len(all_scores) if all_scores else 0.0

        # Fold the available orientation coverages at equal weights (REQ-OAT-051).
        _covs = [c for c in (cov_human, cov_system, cov_bridge) if c is not None]
        coverage_for_blend: Optional[float] = sum(_covs) / len(_covs) if _covs else None

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
    if export_disposition:
        aggregate["affordance_export_disposition"] = export_disposition

    # Tip honesty (CC OBS-200a / Sapper tip_sha_match): stamp emit-time sdk sha so
    # remasure can fail-closed when quality was scored by a shadowed install.
    emit_prov = _emit_time_sdk_sha()
    if emit_prov.get("sdk_sha"):
        aggregate["sdk_sha"] = emit_prov["sdk_sha"]
    aggregate["sdk_sha_source"] = emit_prov.get("sdk_sha_source", "absent")

    report: Dict[str, Any] = {
        "schema_version": "1.0",
        "generated_at": _utc_now_iso(),
        "services": services,
        "aggregate": aggregate,
        "provenance": {
            "sdk_sha": emit_prov.get("sdk_sha", ""),
            "sdk_sha_source": emit_prov.get("sdk_sha_source", "absent"),
            "sdk_module_path": emit_prov.get("sdk_module_path", ""),
        },
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
        logger.info(
            "No run-provenance.json at %s; skipping provenance append", provenance_path
        )
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
        logger.warning(
            "Failed to append to provenance at %s", provenance_path, exc_info=True
        )
