# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Live-validation harness — replay generated PromQL against a real Prometheus.

Implements Group C of ContextCore ``REQ_TARGET_METRIC_BINDING.md`` (FR-8, FR-8a,
FR-8b, FR-8c, FR-9, FR-10). This is the *authoritative* fidelity signal: it goes
and sees the actual thing (Genchi Genbutsu R1) by replaying every generated
PromQL expression against a live ``/api/v1/query`` and reporting whether each
returns a non-empty result.

Two design-principle-hardened behaviors are load-bearing here:

* **Mottainai — forward the descriptor, don't re-parse PromQL (FR-8).** Expected
  metric identity is reconstructed from the onboarding metadata the generator
  consumed (``extract_service_hints`` → ``resolve_descriptor``), *not* by parsing
  the emitted PromQL. This is the same resolution the generator ran, so expected
  identity is guaranteed consistent. The emitted PromQL is read only to *replay*
  it.
* **Context-Correctness — no silent green (FR-10).** A run that replayed **zero**
  queries or hit an **unreachable** backend exits a distinct non-pass status
  (``unknown`` / exit 3), never ``pass``/0.

Exit codes:

* ``0`` — ``pass``: coverage ≥ ``--min-coverage`` and at least one query replayed.
* ``2`` — ``fail``: coverage below ``--min-coverage``.
* ``3`` — ``unknown``: zero queries replayed (empty artifact tree) OR the backend
  was unreachable. Fail-loud; NEVER conflated with pass.

The static coverage gate (``observability_artifact_checks.py``) is *offline
structural smoke — NOT a fidelity signal*; this harness is the fidelity signal
(FR-10). The report carries a one-line note restating that so a static ``1.0``
can never masquerade as fidelity.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml

from .artifact_generator_context import extract_service_hints
from .metric_descriptor import MetricDescriptor, resolve_descriptor
from . import prometheus_query
from .prometheus_query import Auth

logger = logging.getLogger(__name__)

# Exit-code semantics (FR-10). Distinct statuses so an empty/backend-less run is
# never indistinguishable from a real pass.
EXIT_PASS = 0
EXIT_FAIL = 2
EXIT_UNKNOWN = 3

#: Max differential probes per failed expression (FR-9 cardinality cap). One
#: probe per descriptor axis (name, label key, error selector, unit) plus a
#: small margin for the two-sided live checks. Documented constant.
MAX_PROBES_PER_EXPR = 6

#: Default per-run query budget (FR-8c). Bounds total live queries.
DEFAULT_QUERY_BUDGET = 5000

#: Signals we map alert/rule names onto (per-service, per-signal rollup, FR-10).
_SIGNAL_PATTERNS: Tuple[Tuple[str, str], ...] = (
    ("latency", r"latency|duration|p99|p95|p50"),
    ("error", r"error"),
    ("availability", r"avail"),
    ("throughput", r"throughput|calls|request|count|rate"),
)


# ─────────────────────────── expr extraction ───────────────────────────────


@dataclass
class ExtractedExpr:
    """One PromQL expression pulled from a generated artifact."""

    service: str
    signal: str
    expr: str
    source_file: str
    source_kind: str  # "alert" | "slo" | "dashboard"


def _service_from_filename(path: Path) -> str:
    """``checkoutservice-alerts.yaml`` → ``checkoutservice`` (FR-8 mapping)."""
    stem = path.stem
    for suffix in (
        "-alerts",
        "-slo",
        "-slos",
        "-dashboard-spec",
        "-dashboard",
        "-loki-rules",
    ):
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    return stem


def _signal_for(name: str) -> str:
    """Map an alert/rule/panel name to a RED signal (FR-9 per-signal rollup)."""
    lowered = (name or "").lower()
    for signal, pattern in _SIGNAL_PATTERNS:
        if re.search(pattern, lowered):
            return signal
    return "other"


def _iter_exprs_in_obj(obj: Any) -> List[Tuple[str, str]]:
    """Recursively collect ``(name_hint, expr)`` pairs from a parsed YAML tree.

    Handles all three artifact shapes generically rather than binding to one
    schema: alert-rule ``.expr`` (with sibling ``.alert``/``.record`` name),
    SLO ``metricSource.spec.query`` / ``.query`` (with nearest ``metadata.name``),
    and dashboard-panel ``.expr`` / ``targets[].expr`` (with sibling ``.title``).
    """
    found: List[Tuple[str, str]] = []

    def _name_hint(d: Dict[str, Any]) -> str:
        for key in ("alert", "record", "title", "name"):
            v = d.get(key)
            if isinstance(v, str) and v:
                return v
        meta = d.get("metadata")
        if isinstance(meta, dict) and isinstance(meta.get("name"), str):
            return meta["name"]
        return ""

    def _walk(node: Any, name_hint: str) -> None:
        if isinstance(node, dict):
            local_hint = _name_hint(node) or name_hint
            # alert / dashboard-panel expr, and SLO "query" fields
            for expr_key in ("expr", "query"):
                v = node.get(expr_key)
                if isinstance(v, str) and v.strip():
                    found.append((local_hint, v.strip()))
            for value in node.values():
                _walk(value, local_hint)
        elif isinstance(node, list):
            for item in node:
                _walk(item, name_hint)

    _walk(obj, "")
    return found


def extract_exprs(artifacts_dir: Path) -> List[ExtractedExpr]:
    """Walk ``alerts/`` ``slos/`` ``dashboards/`` and pull every PromQL expr.

    Maps each expr to ``(service, signal)`` via the per-service filename and the
    nearest alert/rule/panel name (FR-8). Reads the *actual emitted* PromQL —
    it does NOT re-derive metric identity from it (Mottainai; identity comes from
    the descriptor).
    """
    exprs: List[ExtractedExpr] = []
    kinds = {
        "alerts": "alert",
        "slos": "slo",
        "dashboards": "dashboard",
    }
    for subdir, kind in kinds.items():
        base = artifacts_dir / subdir
        if not base.is_dir():
            continue
        for path in sorted(base.glob("*.yaml")) + sorted(base.glob("*.yml")):
            try:
                docs = list(yaml.safe_load_all(path.read_text()))
            except (yaml.YAMLError, OSError) as e:
                logger.warning("skipping unparseable artifact %s: %s", path, e)
                continue
            service = _service_from_filename(path)
            for doc in docs:
                if doc is None:
                    continue
                for name_hint, expr in _iter_exprs_in_obj(doc):
                    exprs.append(
                        ExtractedExpr(
                            service=service,
                            signal=_signal_for(name_hint),
                            expr=expr,
                            source_file=str(path),
                            source_kind=kind,
                        )
                    )
    return exprs


# ─────────────────── expected identity (from the descriptor) ────────────────


def reconstruct_descriptors(onboarding_metadata: Path) -> Dict[str, MetricDescriptor]:
    """Rebuild the per-service expected ``MetricDescriptor`` (FR-8, Mottainai).

    Uses the SAME resolution the generator ran (``artifact_generator.py`` lines
    ~484-487): ``extract_service_hints(metadata)`` then, per service,
    ``resolve_descriptor(profile=h.metric_profile, transport=h.transport,
    overrides=h.descriptor_overrides)``. No PromQL re-parse; expected identity is
    guaranteed consistent with what the generator emitted.
    """
    metadata = json.loads(Path(onboarding_metadata).read_text())
    hints = extract_service_hints(metadata)
    return {
        h.service_id: resolve_descriptor(
            profile=h.metric_profile or None,
            transport=h.transport,
            overrides=h.descriptor_overrides,
        )
        for h in hints
    }


# ───────────────────────────── FR-9 diagnosis ──────────────────────────────


@dataclass
class AxisFinding:
    """One descriptor axis and whether it is (a) cause of an empty result."""

    axis: str
    expected: str
    mismatched: bool
    detail: str


def diagnose_axes(
    descriptor: MetricDescriptor,
    service_id: str,
    *,
    live_metric_names: List[str],
    label_values_fn: Callable[[str], List[str]],
    probe_budget: List[int],
) -> List[AxisFinding]:
    """Two-sided, per-axis diagnosis of an empty result (FR-9).

    Ground truth is BOTH the reconstructed descriptor (what it SHOULD match) and
    the live system's actual series (``list_metric_names`` + ``label_values``).
    Iterates over EACH descriptor axis in turn — metric name, service label key,
    error selector value, unit — a general per-axis loop, not a fixed step-list.
    Reports ALL mismatched axes (the BPI case is a simultaneous 4-axis miss; we
    never short-circuit at the first). Bounded by ``MAX_PROBES_PER_EXPR``.
    """
    findings: List[AxisFinding] = []
    live_set = set(live_metric_names)

    def _budget_ok() -> bool:
        return probe_budget[0] < MAX_PROBES_PER_EXPR

    def _spend() -> None:
        probe_budget[0] += 1

    # ── axis: metric name ────────────────────────────────────────────────
    # A metric name is a cause when the emitted name is absent from the live
    # __name__ set. (Live names come from a single list_metric_names probe.)
    for axis, expected_name in (
        ("metric_name.throughput", descriptor.throughput_metric),
        ("metric_name.latency_bucket", descriptor.latency_bucket_metric),
    ):
        if not expected_name:
            continue
        present = expected_name in live_set
        findings.append(
            AxisFinding(
                axis=axis,
                expected=expected_name,
                mismatched=not present,
                detail=(
                    f"{expected_name!r} present in live series"
                    if present
                    else f"{expected_name!r} absent from live __name__ set"
                ),
            )
        )

    # ── axis: service label key ──────────────────────────────────────────
    # The key is a cause when the backend has no values for it. One probe.
    label_key = descriptor.service_label_key
    if _budget_ok():
        _spend()
        try:
            values = label_values_fn(label_key)
        except Exception as e:  # a failed probe is inconclusive, not a pass
            values = []
            logger.debug("label_values(%s) probe failed: %s", label_key, e)
        key_present = bool(values)
        expected_val = descriptor.service_label_value_tpl.format(service_id=service_id)
        value_present = expected_val in values
        findings.append(
            AxisFinding(
                axis="service_label_key",
                expected=f'{label_key}="{expected_val}"',
                mismatched=(not key_present) or (not value_present),
                detail=(
                    f"label key {label_key!r} absent from backend"
                    if not key_present
                    else (
                        f"key {label_key!r} present but value {expected_val!r} "
                        "not among its values"
                        if not value_present
                        else f"{label_key}={expected_val!r} present"
                    )
                ),
            )
        )

    # ── axis: error selector value ───────────────────────────────────────
    # Reported when an error selector is present but the throughput metric it
    # rides on is absent (so the selector can never match). Uses already-fetched
    # live names — no extra probe.
    if descriptor.error_selector:
        base_absent = descriptor.throughput_metric not in live_set
        findings.append(
            AxisFinding(
                axis="error_selector",
                expected=descriptor.error_selector,
                mismatched=base_absent,
                detail=(
                    f"error selector {descriptor.error_selector!r} rides on "
                    f"absent metric {descriptor.throughput_metric!r}"
                    if base_absent
                    else f"error selector {descriptor.error_selector!r} "
                    "base metric present"
                ),
            )
        )

    # ── axis: unit ───────────────────────────────────────────────────────
    # A unit mismatch is inferred from the live name shape: when the emitted
    # latency metric is absent BUT a *_milliseconds_bucket exists (or vice
    # versa), the unit axis is a cause alongside the name.
    exp_bucket = descriptor.latency_bucket_metric
    if exp_bucket and exp_bucket not in live_set:
        ms_present = any("milliseconds" in n and n.endswith("_bucket") for n in live_set)
        s_shape_present = any(
            n.endswith("_duration_bucket") and "milliseconds" not in n for n in live_set
        )
        unit_mismatch = (descriptor.latency_unit == "s" and ms_present) or (
            descriptor.latency_unit == "ms" and s_shape_present and not ms_present
        )
        if unit_mismatch:
            findings.append(
                AxisFinding(
                    axis="unit",
                    expected=descriptor.latency_unit,
                    mismatched=True,
                    detail=(
                        f"emitted unit {descriptor.latency_unit!r} but live latency "
                        "histogram uses the other unit"
                    ),
                )
            )

    return findings


def _suggested_profile(live_metric_names: List[str], emitted_profile: str = "") -> str:
    """Which profile the live backend actually matches (≠ the emitted one), or ""."""
    from .metric_descriptor import match_profiles

    for p in match_profiles(live_metric_names):
        if p != emitted_profile:
            return p
    return ""


def _remediation_hint(
    mismatched: List[AxisFinding],
    live_metric_names: List[str],
    emitted_profile: str = "",
) -> str:
    """Actionable hint naming the EXACT profile the live backend uses (quick-win #1).

    Uses the canonical ``match_profiles`` matcher rather than an ad-hoc span-metrics
    guess, so the suggestion is concrete for any convention and one grep from a fix.
    """
    if not mismatched:
        return ""
    axes = ", ".join(sorted(f.axis for f in mismatched))
    suggestion = _suggested_profile(live_metric_names, emitted_profile)
    if suggestion:
        return (
            f"mismatched axes [{axes}]; the live backend emits the {suggestion!r} "
            f"convention — set `spec.observability.metricsProfile: {suggestion}` in the "
            "manifest (or a per-target override) and regenerate."
        )
    return (
        f"mismatched axes [{axes}]; the emitted identity is absent from the live "
        "backend and no built-in profile matches its series — declare a per-axis "
        "`metrics` override on the target."
    )


# ───────────────────────────── report model ────────────────────────────────


@dataclass
class ExprVerdict:
    service: str
    signal: str
    expr: str
    source_file: str
    live_result_count: int
    verdict: str  # "pass" | "fail"
    mismatched_axes: List[str] = field(default_factory=list)
    expected_metric: str = ""
    remediation: str = ""
    suggested_profile: str = ""  # the metricsProfile the live backend matches (quick-win #1)
    axis_detail: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class FidelityReport:
    status: str  # "pass" | "fail" | "unknown"
    reason: str
    queries_replayed: int
    coverage: float
    min_coverage: float
    verdicts: List[ExprVerdict] = field(default_factory=list)
    per_service: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    per_axis: Dict[str, int] = field(default_factory=dict)
    # Quick-win #1: the single metricsProfile the live backend most consistently
    # matches across failing queries — the one-line fix for the whole run. "" when
    # nothing failed or no built-in profile matches (a per-axis override is needed).
    suggested_metrics_profile: str = ""
    static_gate_note: str = (
        "The static coverage gate (observability_artifact_checks.py) is "
        "offline structural smoke — NOT a fidelity signal. This live-replay "
        "report is the authoritative fidelity signal (FR-10)."
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "queries_replayed": self.queries_replayed,
            "coverage": round(self.coverage, 4),
            "min_coverage": self.min_coverage,
            "static_gate_note": self.static_gate_note,
            "suggested_metrics_profile": self.suggested_metrics_profile,
            "per_service": self.per_service,
            "per_axis_mismatch_counts": self.per_axis,
            "verdicts": [
                {
                    "service": v.service,
                    "signal": v.signal,
                    "expr": v.expr,
                    "source_file": v.source_file,
                    "live_result_count": v.live_result_count,
                    "verdict": v.verdict,
                    "mismatched_axes": v.mismatched_axes,
                    "expected_metric": v.expected_metric,
                    "remediation": v.remediation,
                    "suggested_profile": v.suggested_profile,
                    "axis_detail": v.axis_detail,
                }
                for v in self.verdicts
            ],
        }

    def exit_code(self) -> int:
        if self.status == "pass":
            return EXIT_PASS
        if self.status == "fail":
            return EXIT_FAIL
        return EXIT_UNKNOWN


def redact(text: str, secrets: List[str]) -> str:
    """Scrub credential strings from output (FR-8b)."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***REDACTED***")
    return text


# ─────────────────────────────── harness ───────────────────────────────────

# Hostnames treated as demo/local; anything else needs --allow-prod (FR-8c).
_LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "0.0.0.0")


def _is_local_backend(prometheus_url: str) -> bool:
    from urllib.parse import urlparse

    host = (urlparse(prometheus_url).hostname or "").lower()
    if host in _LOCAL_HOSTS:
        return True
    # kube-service / demo hostnames commonly used in the astronomy demo
    return host.endswith(".svc") or host.endswith(".local") or "demo" in host


def run_validation(
    *,
    artifacts_dir: Path,
    onboarding_metadata: Path,
    prometheus_url: str,
    min_coverage: float,
    allow_prod: bool = False,
    dry_run: bool = False,
    query_budget: int = DEFAULT_QUERY_BUDGET,
    auth: Optional[Auth] = None,
    query_fn: Optional[Callable[..., int]] = None,
    list_names_fn: Optional[Callable[..., List[str]]] = None,
    label_values_fn: Optional[Callable[..., List[str]]] = None,
) -> FidelityReport:
    """Replay every generated PromQL and build the fidelity report (FR-8..10).

    The ``*_fn`` params default to the canonical :mod:`prometheus_query` client
    and exist so tests can monkeypatch them without a live backend.
    """
    auth = auth if auth is not None else Auth.from_env()
    q_count = query_fn or prometheus_query.instant_query_count
    list_names = list_names_fn or prometheus_query.list_metric_names
    label_vals = label_values_fn or prometheus_query.label_values

    # FR-8c: refuse a non-demo backend without explicit opt-in.
    if not allow_prod and not _is_local_backend(prometheus_url):
        return FidelityReport(
            status="unknown",
            reason=(
                f"refusing non-demo backend {prometheus_url!r} without --allow-prod "
                "(FR-8c prod-replay guardrail)"
            ),
            queries_replayed=0,
            coverage=0.0,
            min_coverage=min_coverage,
        )

    exprs = extract_exprs(Path(artifacts_dir))

    # FR-10: zero queries to replay (empty artifact tree) is a distinct non-pass.
    if not exprs:
        return FidelityReport(
            status="unknown",
            reason="zero PromQL expressions found in artifact tree (nothing to replay)",
            queries_replayed=0,
            coverage=0.0,
            min_coverage=min_coverage,
        )

    # FR-8c dry-run: report the query count / estimated series and exit.
    if dry_run:
        return FidelityReport(
            status="unknown",
            reason=(
                f"dry-run: would replay {len(exprs)} queries against "
                f"{prometheus_url} (budget {query_budget}); no queries executed"
            ),
            queries_replayed=0,
            coverage=0.0,
            min_coverage=min_coverage,
        )

    descriptors = reconstruct_descriptors(Path(onboarding_metadata))

    # Lazily discovered live series (one probe, reused across diagnoses).
    live_names_cache: Dict[str, List[str]] = {}

    def _live_names() -> List[str]:
        if "names" not in live_names_cache:
            live_names_cache["names"] = list_names(prometheus_url, auth=auth)
        return live_names_cache["names"]

    verdicts: List[ExprVerdict] = []
    replayed = 0
    backend_unreachable = False

    for e in exprs:
        if replayed >= query_budget:
            logger.warning("per-run query budget %d reached; stopping", query_budget)
            break
        try:
            count = q_count(prometheus_url, e.expr, auth=auth)
        except Exception as exc:  # FR-10: unreachable backend ⇒ distinct non-pass
            logger.warning("query failed (backend unreachable?): %s", exc)
            backend_unreachable = True
            break
        replayed += 1

        descriptor = descriptors.get(e.service)
        expected_metric = ""
        mismatched: List[str] = []
        remediation = ""
        suggested_profile = ""
        axis_detail: List[Dict[str, Any]] = []

        if count > 0:
            verdict = "pass"
            if descriptor is not None:
                expected_metric = descriptor.throughput_metric
        else:
            verdict = "fail"
            if descriptor is not None:
                expected_metric = descriptor.throughput_metric
                try:
                    live = _live_names()
                except Exception as exc:
                    logger.warning("list_metric_names failed: %s", exc)
                    backend_unreachable = True
                    break
                probe_budget = [0]
                findings = diagnose_axes(
                    descriptor,
                    e.service,
                    live_metric_names=live,
                    label_values_fn=lambda lbl: label_vals(
                        prometheus_url, lbl, auth=auth
                    ),
                    probe_budget=probe_budget,
                )
                mismatched_findings = [f for f in findings if f.mismatched]
                mismatched = [f.axis for f in mismatched_findings]
                remediation = _remediation_hint(
                    mismatched_findings, live, descriptor.profile
                )
                suggested_profile = _suggested_profile(live, descriptor.profile)
                axis_detail = [
                    {
                        "axis": f.axis,
                        "expected": f.expected,
                        "mismatched": f.mismatched,
                        "detail": f.detail,
                    }
                    for f in findings
                ]

        verdicts.append(
            ExprVerdict(
                service=e.service,
                signal=e.signal,
                expr=e.expr,
                source_file=e.source_file,
                live_result_count=count,
                verdict=verdict,
                mismatched_axes=mismatched,
                expected_metric=expected_metric,
                remediation=remediation,
                suggested_profile=suggested_profile,
                axis_detail=axis_detail,
            )
        )

    # FR-10: unreachable backend ⇒ distinct non-pass (never pass), even if some
    # queries had already succeeded.
    if backend_unreachable:
        return FidelityReport(
            status="unknown",
            reason="Prometheus backend unreachable during replay (fail-loud, not pass)",
            queries_replayed=replayed,
            coverage=0.0,
            min_coverage=min_coverage,
            verdicts=verdicts,
        )

    if replayed == 0:
        return FidelityReport(
            status="unknown",
            reason="no queries were replayed",
            queries_replayed=0,
            coverage=0.0,
            min_coverage=min_coverage,
        )

    passes = sum(1 for v in verdicts if v.verdict == "pass")
    coverage = passes / replayed

    # Rollups (FR-10): per-service coverage and per-axis mismatch counts.
    per_service: Dict[str, Dict[str, Any]] = {}
    per_axis: Dict[str, int] = {}
    for v in verdicts:
        svc = per_service.setdefault(
            v.service, {"total": 0, "passed": 0, "signals": {}}
        )
        svc["total"] += 1
        if v.verdict == "pass":
            svc["passed"] += 1
        sig = svc["signals"].setdefault(v.signal, {"total": 0, "passed": 0})
        sig["total"] += 1
        if v.verdict == "pass":
            sig["passed"] += 1
        for axis in v.mismatched_axes:
            per_axis[axis] = per_axis.get(axis, 0) + 1
    for svc in per_service.values():
        svc["coverage"] = round(svc["passed"] / svc["total"], 4) if svc["total"] else 0.0

    status = "pass" if coverage >= min_coverage else "fail"
    reason = (
        f"coverage {coverage:.4f} >= min {min_coverage}"
        if status == "pass"
        else f"coverage {coverage:.4f} < min {min_coverage}"
    )
    # Quick-win #1: roll the per-verdict profile suggestions up into the single
    # metricsProfile that best matches the live backend across all failing
    # queries — the one-line fix for the whole run. Ties break on frequency.
    _profile_votes = Counter(v.suggested_profile for v in verdicts if v.suggested_profile)
    suggested_metrics_profile = _profile_votes.most_common(1)[0][0] if _profile_votes else ""
    return FidelityReport(
        status=status,
        reason=reason,
        queries_replayed=replayed,
        coverage=coverage,
        min_coverage=min_coverage,
        verdicts=verdicts,
        per_service=per_service,
        per_axis=per_axis,
        suggested_metrics_profile=suggested_metrics_profile,
    )
