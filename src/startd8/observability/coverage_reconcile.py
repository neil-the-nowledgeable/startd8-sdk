# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Telemetry-coverage reconciliation — join expected coverage with live actuals.

The Telemetry Coverage Portal (ContextCore REQ_TELEMETRY_COVERAGE_PORTAL, REQ-TCP-100/101)
needs one per-service record answering *"is this service actually observable, and if not,
what's missing?"*. Both inputs already exist and are **consumed here, never recomputed**
(Mottainai / determinism):

* **Actual** — a ``LiveComparisonReport.to_dict()`` from ``compare-live`` (Tier-B live
  fidelity: ``tier_b.per_service`` coverage, ``tier_b.verdicts``, ``tier_b.target_drift``;
  Tier-A gaps; ``pending_verdicts``).
* **Expected** — per-service ``ServiceHints`` (``criticality``, ``owner``, declared/convention
  surface) and the ``per_service.signals`` the engine replayed.
* **Business** — a ``{service: criticality}`` map supplied by the caller (ContextCore resolves
  it from the manifest; REQ-TCP-103). Authoritative over ``ServiceHints.criticality``.

This module is **pure** (no I/O, no re-query — NR-2): given the report dict it returns records.
It imports ``compare-live``/``ServiceHints`` shapes as read-only data; it never re-derives
binding. The presence taxonomy (REQ-TCP-101) is a fixed enum mapped from existing verdicts, not
a new detection ladder.

See ``ContextCore/docs/design/requirements/REQ_TELEMETRY_COVERAGE_PORTAL.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ─────────────────────────── presence taxonomy (REQ-TCP-101) ────────────────
# Fixed enum, each value mapped 1:1 from an existing compare-live signal. No new logic.
BOUND = "bound"                    # per_service coverage >= 1.0 — emitting + fully bound
PARTIAL = "partial"                # 0 < coverage < 1.0 — some axes bound, some missing
NO_TELEMETRY = "no_telemetry"      # coverage <= 0 — queries ran, nothing bound
DECLARED_ABSENT = "declared_absent"  # tier_b.target_drift.declared_absent — never emitted
PENDING_PROBE = "pending_probe"    # pending_verdicts only — positive, NOT a gap (#308)
DEGRADED = "degraded"              # tier_b is None / not observed — fail-loud unknown (NR-3)
SUPPRESSED = "suppressed"          # Tier-A suppressed_base_metrics — SLIs omitted at generation (#363)
STALE = "stale"                    # EC-13: series PRESENT (binds) but no recent traffic — a
                                   # frozen span-metric of a service that went dark. Presence != liveness.

#: Statuses that count as "observable" for a coverage rollup. ``pending_probe`` is positive-
#: but-pending and is EXCLUDED from both numerator and denominator (mirrors #308 in compare-live).
#: ``stale`` is NOT observable — the series binds but the service isn't actually live.
_OBSERVABLE = {BOUND}
_ROLLUP_DENOMINATOR_EXCLUDES = {PENDING_PROBE}

UNKNOWN_CRITICALITY = "unknown"


@dataclass
class CoverageRecord:
    """One reconciled per-service coverage record (REQ-TCP-100)."""

    service: str
    presence_status: str                      # one of the taxonomy constants above
    criticality: str = UNKNOWN_CRITICALITY
    owner: Optional[str] = None
    binding_coverage: Optional[float] = None   # None when not measurable (absent/pending/degraded)
    expected_axes: List[str] = field(default_factory=list)
    actual_axes: List[str] = field(default_factory=list)
    missing_signals: List[str] = field(default_factory=list)
    next_step: str = ""
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "service": self.service,
            "presence_status": self.presence_status,
            "criticality": self.criticality,
            "owner": self.owner,
            "binding_coverage": self.binding_coverage,
            "expected_axes": self.expected_axes,
            "actual_axes": self.actual_axes,
            "missing_signals": self.missing_signals,
            "next_step": self.next_step,
            "provenance": self.provenance,
        }


# ─────────────────────────── hint accessor (dict OR ServiceHints) ───────────

def _hint_attr(hint: Any, name: str, default: Any = None) -> Any:
    """Read ``name`` from a ServiceHints dataclass OR a plain dict — tests use either."""
    if hint is None:
        return default
    if isinstance(hint, dict):
        return hint.get(name, default)
    return getattr(hint, name, default)


def _resolve_criticality(svc: str, criticality_map: Dict[str, str], hint: Any) -> str:
    """REQ-TCP-103 precedence: caller map (authoritative) → ServiceHints → explicit ``unknown``.

    Never silently defaults (Context-Correctness): an unresolved service is ``unknown``, a
    distinct bucket, not mistaken for low criticality.
    """
    return (
        (criticality_map or {}).get(svc)
        or (_hint_attr(hint, "criticality") or "")
        or UNKNOWN_CRITICALITY
    )


def _next_step(status: str, missing: List[str], remediation: str) -> str:
    if remediation:
        return remediation
    if status == DECLARED_ABSENT:
        return "deploy the service, or --exclude-services it if intentionally out of scope"
    if status == NO_TELEMETRY:
        return "service emitted no bindable telemetry — check instrumentation / metrics_surface"
    if status == PARTIAL:
        return f"bind missing signal(s): {', '.join(missing)}" if missing else "close remaining axis gaps"
    if status == PENDING_PROBE:
        return "awaiting the probe runner (freshness SLI) — positive, not a gap"
    if status == SUPPRESSED:
        return (
            "SLIs suppressed at generation (metrics_surface / profile) — "
            "adjust the generation profile or declare emitted series; "
            "re-running compare-live will not help"
        )
    if status == STALE:
        return "series present but NO recent traffic — the service likely went dark (check it's up)"
    if status == DEGRADED:
        return "live standup/scrape unavailable — re-run compare-live to measure this service"
    return ""


def _expected_from_hint(hint: Any) -> List[str]:
    """Fallback expected axes when the report replayed no queries for a service.

    Derived from the service's declared/convention surface names (best-effort labels), so an
    empty-services gap still shows *what was expected*.
    """
    names: List[str] = []
    for key in ("declared_metrics", "convention_metrics"):
        for m in _hint_attr(hint, key, []) or []:
            n = _hint_attr(m, "name")
            if n:
                names.append(n)
    return sorted(set(names))


def reconcile(
    live_report: Dict[str, Any],
    *,
    criticality_map: Optional[Dict[str, str]] = None,
    service_hints: Optional[Dict[str, Any]] = None,
    liveness: Optional[Dict[str, bool]] = None,
) -> List[CoverageRecord]:
    """Reconcile a ``LiveComparisonReport.to_dict()`` into per-service coverage records.

    Pure and deterministic: records are returned sorted by service id. ``service_hints`` and
    ``criticality_map`` only *enrich* — the presence verdict comes entirely from the report.
    """
    criticality_map = criticality_map or {}
    service_hints = service_hints or {}

    tier_b = live_report.get("tier_b")
    tier_a = live_report.get("tier_a") or {}
    pending_verdicts = live_report.get("pending_verdicts") or []

    per_service: Dict[str, Any] = (tier_b or {}).get("per_service") or {}
    target_drift: Dict[str, Any] = (tier_b or {}).get("target_drift") or {}
    declared_absent = set(target_drift.get("declared_absent") or [])
    verdicts: List[Dict[str, Any]] = (tier_b or {}).get("verdicts") or []
    pending_services = {v.get("service") for v in pending_verdicts if v.get("service")}
    suppressed_by_svc = _suppressed_gap_by_service(tier_a)

    # Per-service remediation hint: first fail verdict's remediation (already authored upstream).
    remediation_by_svc: Dict[str, str] = {}
    mismatched_by_svc: Dict[str, List[str]] = {}
    for v in verdicts:
        svc = v.get("service")
        if not svc:
            continue
        if v.get("verdict") == "fail":
            remediation_by_svc.setdefault(svc, v.get("remediation") or "")
            for ax in v.get("mismatched_axes") or []:
                mismatched_by_svc.setdefault(svc, [])
                if ax not in mismatched_by_svc[svc]:
                    mismatched_by_svc[svc].append(ax)

    # Universe of services: everything any signal mentions, plus declared hints.
    universe = (
        set(per_service)
        | declared_absent
        | pending_services
        | {v.get("service") for v in verdicts if v.get("service")}
        | set(service_hints)
        | _services_in_gaps(tier_a)
    )
    universe.discard(None)

    tier_b_missing = tier_b is None
    provenance_base = {
        "report_version": live_report.get("report_version"),
        "status": live_report.get("status"),
        "reason": live_report.get("reason"),
        "tier_b_present": not tier_b_missing,
    }

    records: List[CoverageRecord] = []
    for svc in sorted(universe):
        hint = service_hints.get(svc)
        crit = _resolve_criticality(svc, criticality_map, hint)
        owner = _hint_attr(hint, "owner")
        expected = _expected_from_hint(hint)
        actual: List[str] = []
        missing: List[str] = []
        coverage: Optional[float] = None
        gap = suppressed_by_svc.get(svc) or {}

        if tier_b_missing:
            status = DEGRADED
        elif svc in declared_absent:
            status = DECLARED_ABSENT
        elif svc in per_service:
            ps = per_service[svc] or {}
            coverage = float(ps.get("coverage", 0.0) or 0.0)
            signals = ps.get("signals") or {}
            if signals:
                expected = sorted(signals.keys())
                actual = sorted(s for s, d in signals.items() if (d or {}).get("passed", 0) > 0)
                missing = sorted(s for s, d in signals.items() if (d or {}).get("passed", 0) <= 0)
            # Fold in any per-axis mismatches surfaced by fail verdicts.
            for ax in mismatched_by_svc.get(svc, []):
                if ax not in missing:
                    missing.append(ax)
            if coverage >= 1.0 and not missing:
                status = BOUND
            elif coverage <= 0.0:
                status = NO_TELEMETRY
            else:
                status = PARTIAL
        elif svc in pending_services:
            status = PENDING_PROBE
        elif svc in suppressed_by_svc:
            # #363: generation omitted SLIs — distinct from "standup unavailable".
            status = SUPPRESSED
            kinds = gap.get("suppressed_sli_kinds") or []
            if isinstance(kinds, list) and kinds:
                expected = sorted({str(k) for k in kinds})
        else:
            # Declared (has a hint / gap) but not observed and not in drift → not measured.
            status = DEGRADED

        # EC-13: presence != liveness. A fully-bound service with NO recent traffic is STALE
        # (its span-metric series is present — so it binds — but frozen at its last value; the
        # service went dark). ``liveness`` is a caller-supplied rate>0 probe; absent → unchanged.
        if status == BOUND and liveness is not None and liveness.get(svc) is False:
            status = STALE

        # Prefer upstream fail remediation; for suppressed, surface the generation gap reason.
        remediation = remediation_by_svc.get(svc, "") or (
            str(gap.get("reason") or "") if status == SUPPRESSED else ""
        )
        provenance = dict(provenance_base)
        if status == SUPPRESSED and gap.get("metrics_surface"):
            provenance["metrics_surface"] = gap["metrics_surface"]
            provenance["gap_class"] = "suppressed_base_metrics"

        records.append(
            CoverageRecord(
                service=svc,
                presence_status=status,
                criticality=crit,
                owner=owner,
                binding_coverage=round(coverage, 4) if coverage is not None else None,
                expected_axes=expected,
                actual_axes=actual,
                missing_signals=missing,
                next_step=_next_step(status, missing, remediation),
                provenance=provenance,
            )
        )
    return records


def _suppressed_gap_by_service(tier_a: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Map service id → Tier-A ``suppressed_base_metrics`` gap entry (#363)."""
    out: Dict[str, Dict[str, Any]] = {}
    for e in (tier_a.get("gaps") or {}).get("suppressed_base_metrics") or []:
        if isinstance(e, dict) and e.get("service"):
            out.setdefault(str(e["service"]), e)
        elif isinstance(e, str) and e:
            out.setdefault(e, {"service": e})
    return out


def _services_in_gaps(tier_a: Dict[str, Any]) -> set:
    """Service ids named anywhere in Tier-A gap entries (best-effort — entries vary by class)."""
    out: set = set()
    for entries in (tier_a.get("gaps") or {}).values():
        for e in entries or []:
            if isinstance(e, dict) and e.get("service"):
                out.add(e["service"])
            elif isinstance(e, str):
                out.add(e)
    return out


# ─────────────────────────── rollups (REQ-TCP-102/110) ──────────────────────

def summarize(records: List[CoverageRecord]) -> Dict[str, Any]:
    """System-posture rollup: counts by status, overall bound %, and per-criticality breakdown.

    ``pending_probe`` is excluded from rollup denominators (positive-but-pending). The
    ``critical`` tier is reported explicitly so *"are our critical services observable?"* is
    answerable (REQ-TCP-102).
    """
    by_status: Dict[str, int] = {}
    by_tier: Dict[str, Dict[str, Any]] = {}
    for r in records:
        by_status[r.presence_status] = by_status.get(r.presence_status, 0) + 1
        tier = by_tier.setdefault(
            r.criticality, {"total": 0, "bound": 0, "not_bound": [], "denominator": 0}
        )
        tier["total"] += 1
        if r.presence_status in _ROLLUP_DENOMINATOR_EXCLUDES:
            continue
        tier["denominator"] += 1
        if r.presence_status in _OBSERVABLE:
            tier["bound"] += 1
        else:
            tier["not_bound"].append(r.service)

    for tier in by_tier.values():
        d = tier["denominator"]
        tier["coverage"] = round(tier["bound"] / d, 4) if d else None

    denom = sum(t["denominator"] for t in by_tier.values())
    bound = sum(t["bound"] for t in by_tier.values())
    critical = by_tier.get("critical", {})
    return {
        "total_services": len(records),
        "by_status": by_status,
        "overall_coverage": round(bound / denom, 4) if denom else None,
        "by_criticality": by_tier,
        "critical_not_bound": list(critical.get("not_bound", [])),
    }
