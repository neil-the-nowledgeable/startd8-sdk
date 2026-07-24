# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Tier-B live derived-vs-emitted comparison (+ CI regression gate).

Stands up a subject + Prometheus (``live_standup``), replays the generated PromQL
through the built engine (``validate_promql.run_validation``), and **merges** the
live fidelity verdicts with Tier-A's static ``fr_coverage`` gaps (``compare``)
into one report. The ``fail`` verdict is exactly the #274 (dead metric) / #275
(wrong label) bug class; :func:`ci_gate` fails a build on any *new* ``fail``.

Tier A (``compare.py``) and the engine (``validate_promql.py``) are **read-only
dependencies** — imported, never modified (NR-3). Every external effect is
injectable so the merge/gate logic is unit-tested with zero docker (FR-10),
mirroring ``bind_and_verify``.

See ``docs/design/observability-compare/REQUIREMENTS.md``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from . import live_standup
from .compare import ComparisonReport, build_comparison_report, read_fr_coverage
from .prometheus_query import Auth
from .validate_promql import FidelityReport, run_validation

# Reuse the engine's exit-code + verdict taxonomy — single-source (do not restate).
EXIT_PASS, EXIT_FAIL, EXIT_UNKNOWN = 0, 2, 3
#: rollup severity: higher wins. unknown (couldn't observe) > fail (dead SLI) > pass.
#: #308 P2 (FR-P2-1/F3): `pending_probe` is severity 0 EXPLICITLY (a declared invariant, not a
#: `.get(default=0)` accident) — a probe metric expected-absent until its runner runs is NEVER a fail.
_SEVERITY = {"pass": 0, "pending_probe": 0, "fail": 1, "unknown": 2}
_STATUS_BY_SEVERITY = {0: "pass", 1: "fail", 2: "unknown"}


def pending_probe_verdicts(fr_coverage: Dict[str, Any]) -> List[Dict[str, Any]]:
    """#308 P2 (FR-P2-1): SYNTHESIZE a `pending_probe` verdict per `pending_probes` fr_coverage entry.

    P0/P1 write no SLO YAML, so `extract_exprs` yields no verdict for the probe metric — compare-live
    synthesizes one here, identified by the entry's recorded ``published_metric`` (a fr_coverage JOIN, NOT
    a ``probe_`` name-prefix heuristic — ``published_metric`` is author-overridable). These verdicts are
    ``pending_probe`` (severity 0) and MUST NOT be fed to ``compute_coverage`` (they are excluded from the
    binding-coverage denominator, like ``excluded``), so a pending probe can never drop coverage below the
    floor and trip ``EXIT_FAIL``. They are also not ``"fail"``, so they never enter the CI ``fail_verdicts``
    / baseline-diff set."""
    out: List[Dict[str, Any]] = []
    for e in (fr_coverage.get("pending_probes") or []):
        if not isinstance(e, dict) or not e.get("query"):
            continue  # unsupported metric_kind/signal_kind entries carry no query → nothing to bind
        out.append({
            "verdict": "pending_probe",
            "expr": e["query"],
            "metric": e.get("published_metric", ""),
            "service": e.get("service", ""),
            "probe": e.get("name", ""),
            "detail": "expected-absent until the probe runner runs (#308 P2)",
        })
    return out


def promote_probe_slo(entry: Dict[str, Any], slo_window: str = "30d") -> Dict[str, Any]:
    """#308 P2 (FR-P2-2): build a real OpenSLO doc from a live-confirmed `pending_probes` entry — using the
    ALREADY-RECORDED ``query``/``target`` (Mottainai: no re-derivation; the promoted PromQL == the P0
    string, so ``validate_promql`` self-heals off it). Caller gates promotion on live confirmation +
    ≥2 warm-up scrapes (NR-5); this is the pure builder."""
    svc, name = entry.get("service", "svc"), entry.get("name", "probe")
    slug = f"{svc}-{name}".lower().replace("_", "-")
    spec: Dict[str, Any] = {
        "description": f"freshness SLO for {svc} promoted from confirmed probe {name!r} (#308 P2).",
        "timeWindow": {"duration": slo_window, "isRolling": True},
        "indicator": {"metadata": {"name": f"{slug}-probe-sli"},
                      "spec": {"thresholdMetric": {"metricSource": {
                          "type": "prometheus", "spec": {"query": entry["query"]}}}}},
    }
    if entry.get("target") is not None:
        spec["target"] = entry["target"]
    return {"apiVersion": "openslo/v1", "kind": "SLO",
            "metadata": {"name": f"{slug}-probe", "labels": {"service": svc, "signal_kind": "freshness",
                                                             "generated_by": "startd8"}},
            "spec": spec}


@dataclass
class LiveComparisonReport:
    """Tier-A gaps + Tier-B live fidelity, merged. Tier B is authoritative."""

    status: str  # pass | fail | unknown
    reason: str
    tier_a: Dict[str, Any]  # ComparisonReport.to_dict()
    standup: Dict[str, Any]  # StandupHandle.to_dict() (or {"skipped": ...} on --prometheus)
    tier_b: Optional[Dict[str, Any]] = None  # FidelityReport.to_dict(), None if standup/scrape failed
    total_gaps: int = 0  # convenience rollup from tier_a
    fail_verdicts: List[Dict[str, Any]] = field(default_factory=list)  # tier_b fails (the CI signal)

    #: Bumped when the emitted ``to_dict()`` shape changes — the ``--json`` output
    #: is the machine surface CI parses, so the key set is a versioned contract (R1-F7).
    REPORT_VERSION = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_version": self.REPORT_VERSION,
            "status": self.status,
            "reason": self.reason,
            "total_gaps": self.total_gaps,
            "fail_verdicts": self.fail_verdicts,
            "tier_a": self.tier_a,
            "tier_b": self.tier_b,
            "standup": self.standup,
        }

    def exit_code(self) -> int:
        return {"pass": EXIT_PASS, "fail": EXIT_FAIL}.get(self.status, EXIT_UNKNOWN)


def build_live_comparison(
    comparison: ComparisonReport,
    fidelity: Optional[FidelityReport],
    standup_status: Dict[str, Any],
    *,
    strict_tier_a: bool = False,
) -> LiveComparisonReport:
    """Pure merge — the unit-test core (no I/O, no docker, no Prometheus).

    * ``fidelity is None`` (standup/scrape failed) → ``unknown`` (fail-loud);
      Tier-A gaps are still reported.
    * else status = the more severe of Tier-A's contribution and Tier-B's status.
      Tier A contributes ``fail`` only under ``strict_tier_a`` with gaps present;
      otherwise it is advisory (``pass``). Tier B (authoritative) contributes its
      own status directly.
    """
    tier_a = comparison.to_dict()
    total_gaps = comparison.total_gaps

    if fidelity is None:
        return LiveComparisonReport(
            status="unknown",
            reason=str(standup_status.get("reason") or "live standup unavailable"),
            tier_a=tier_a,
            standup=standup_status,
            tier_b=None,
            total_gaps=total_gaps,
        )

    tier_b = fidelity.to_dict()
    fail_verdicts = [v for v in tier_b.get("verdicts", []) if v.get("verdict") == "fail"]

    tier_a_status = "fail" if (strict_tier_a and total_gaps > 0) else "pass"
    severity = max(_SEVERITY.get(tier_a_status, 0), _SEVERITY.get(fidelity.status, 0))
    status = _STATUS_BY_SEVERITY[severity]

    reason = _rollup_reason(status, fidelity, total_gaps, strict_tier_a)
    return LiveComparisonReport(
        status=status,
        reason=reason,
        tier_a=tier_a,
        standup=standup_status,
        tier_b=tier_b,
        total_gaps=total_gaps,
        fail_verdicts=fail_verdicts,
    )


def _rollup_reason(status: str, fidelity: FidelityReport, total_gaps: int, strict_tier_a: bool) -> str:
    if status == "unknown":
        return fidelity.reason or "live replay inconclusive"
    if status == "fail":
        parts = []
        n_fail = sum(1 for v in fidelity.verdicts if v.verdict == "fail")
        if n_fail:
            parts.append(f"{n_fail} dead SLI(s) (Tier B fail)")
        if strict_tier_a and total_gaps > 0:
            parts.append(f"{total_gaps} static gap(s) (Tier A, strict)")
        return "; ".join(parts) or "fidelity below threshold"
    note = f"{total_gaps} advisory static gap(s)" if total_gaps else "no static gaps"
    return f"all replayed SLIs bind to live telemetry; {note}"


def run_live_comparison(
    *,
    manifest: Path,
    onboarding_metadata: Optional[Path] = None,
    artifacts_dir: Optional[Path] = None,
    subject_image: Optional[str] = None,
    subject_port: int = 8080,
    metrics_path: str = "/metrics",
    prometheus: Optional[str] = None,
    min_coverage: float = 1.0,
    allow_prod: bool = False,
    keep_up: bool = False,
    strict_tier_a: bool = False,
    job_name: str = "subject",
    auth: Optional[Auth] = None,
    # injectable seams (FR-10) — mirror bind_and_verify / run_validation.
    standup_fn: Optional[Callable[..., live_standup.StandupHandle]] = None,
    teardown_fn: Optional[Callable[..., None]] = None,
    validate_fn: Optional[Callable[..., FidelityReport]] = None,
    read_fr_coverage_fn: Optional[Callable[[Path], Dict[str, Any]]] = None,
) -> LiveComparisonReport:
    """Orchestrate: Tier A (static) + Tier B (live) → one merged report.

    Two Tier-B backends:
    * ``prometheus=<url>`` — replay against an already-running backend (skip
      standup). This is the multi-container / Mastodon path (NR-1) and is $0-docker.
    * ``subject_image=<image>`` — stand up the subject + Prometheus, wait for a
      scrape, then replay. Teardown always runs in ``finally`` unless ``--keep-up``.
    """
    _read = read_fr_coverage_fn or read_fr_coverage
    _validate = validate_fn or run_validation
    _standup = standup_fn or live_standup.stand_up_subject_and_prometheus
    _teardown = teardown_fn or live_standup.tear_down
    auth = auth if auth is not None else Auth.from_env()

    comparison = build_comparison_report(_read(manifest))

    # ── Path 1: existing backend (no standup) ──────────────────────────────
    if prometheus:
        fidelity = _validate(
            artifacts_dir=artifacts_dir,
            onboarding_metadata=onboarding_metadata,
            prometheus_url=prometheus,
            min_coverage=min_coverage,
            allow_prod=allow_prod,
            auth=auth,
        )
        return build_live_comparison(
            comparison, fidelity,
            {"skipped": "used existing --prometheus backend", "prometheus_url": prometheus},
            strict_tier_a=strict_tier_a,
        )

    # ── Path 2: stand up subject + Prometheus ──────────────────────────────
    if not subject_image:
        return build_live_comparison(
            comparison, None,
            {"reason": "no --subject-image and no --prometheus given"},
            strict_tier_a=strict_tier_a,
        )

    handle: Optional[live_standup.StandupHandle] = None
    try:
        handle = _standup(
            subject_image=subject_image,
            subject_port=subject_port,
            metrics_path=metrics_path,
            job_name=job_name,
            scrape_ready_check=live_standup.prometheus_query.scrape_ready,
            auth=auth,
        )
        if not handle.scrape_ready:
            return build_live_comparison(comparison, None, handle.to_dict(), strict_tier_a=strict_tier_a)

        fidelity = _validate(
            artifacts_dir=artifacts_dir,
            onboarding_metadata=onboarding_metadata,
            prometheus_url=handle.prometheus_url,
            min_coverage=min_coverage,
            allow_prod=allow_prod,
            auth=auth,
        )
        return build_live_comparison(comparison, fidelity, handle.to_dict(), strict_tier_a=strict_tier_a)
    finally:
        if handle is not None and not keep_up:
            _teardown(handle)


# ────────────────────────────── CI gate (FR-8) ─────────────────────────────


def _source_key(source_file: str) -> str:
    """Directory-qualified source key (last two path components).

    NOT bare ``basename``: ``alerts/foo.yaml`` and ``dashboards/foo.yaml`` share a
    basename, so a bare-basename identity would let a genuinely-new dead SLI in one
    file normalize onto a baselined id from the other and slip the gate (R1-F8/S2).
    Keeping ``<parent>/<name>`` disambiguates the two artifact kinds while staying
    stable across an absolute-vs-relative path prefix.
    """
    parts = Path(str(source_file)).parts
    return "/".join(parts[-2:]) if len(parts) >= 2 else (parts[-1] if parts else "")


def verdict_id(v: Dict[str, Any]) -> str:
    """Stable identity of one verdict for baseline diffing.

    ``(service, signal, dir-qualified source key, normalized expr)`` — deliberately
    NOT ``live_result_count`` (environment-noisy). The whitespace-normalized expr
    keeps the id stable across formatting churn; the dir-qualified source key keeps
    same-basename files in different artifact dirs distinct (R1-F8/S2).
    """
    service = str(v.get("service", ""))
    signal = str(v.get("signal", ""))
    src = _source_key(str(v.get("source_file", "")))
    expr = " ".join(str(v.get("expr", "")).split())
    return f"{service}|{signal}|{src}|{expr}"


def new_fail_verdicts(tier_b: Optional[Dict[str, Any]], baseline: Set[str]) -> List[Dict[str, Any]]:
    """``fail`` verdicts whose identity is not in the accepted baseline."""
    if not tier_b:
        return []
    return [
        v for v in tier_b.get("verdicts", [])
        if v.get("verdict") == "fail" and verdict_id(v) not in baseline
    ]


def ci_gate(report: LiveComparisonReport, baseline: Set[str]):
    """(exit_code, new_fails). 2 ⇒ a NEW dead SLI shipped; 0 ⇒ clean/baselined; 3 ⇒ unknown.

    The gate is "no *new* fail", not "zero fail": a reference subject legitimately
    carries known-dead SLIs (baselined) until the generator is fixed.
    """
    if report.status == "unknown":
        return EXIT_UNKNOWN, []
    new_fails = new_fail_verdicts(report.tier_b, baseline)
    return (EXIT_FAIL, new_fails) if new_fails else (EXIT_PASS, [])


def load_baseline(path: Path) -> Set[str]:
    """Read the accepted-fail identity set from a baseline JSON (``{}`` if absent)."""
    if not path or not Path(path).exists():
        return set()
    data = json.loads(Path(path).read_text(encoding="utf-8")) or {}
    return set(data.get("accepted_fail_ids") or [])


def render_baseline(report: LiveComparisonReport, *, subject: str = "", note: str = "") -> Dict[str, Any]:
    """Serialize the CURRENT fail identities as a new baseline (operator writes this
    explicitly — the gate never self-heals, NR-4)."""
    ids = sorted({verdict_id(v) for v in report.fail_verdicts})
    return {
        "header": {"subject": subject, "note": note, "accepted_fail_count": len(ids)},
        "accepted_fail_ids": ids,
    }


# ─────────────────────────────── renderer ──────────────────────────────────


def render_live_report(report: LiveComparisonReport) -> str:
    """Human-readable merged Tier-A + Tier-B report."""
    icon = {"pass": "✓", "fail": "✗", "unknown": "?"}.get(report.status, "?")
    lines = [
        "# Observability comparison — derived vs emitted (Tier A + Tier B live)",
        "",
        f"Status: {report.status.upper()} {icon} — {report.reason}",
        "",
    ]
    # Tier B (authoritative)
    if report.tier_b is None:
        lines += ["Tier B (live fidelity): UNAVAILABLE — " + report.reason, ""]
    else:
        tb = report.tier_b
        lines += [
            "Tier B (live fidelity — authoritative):",
            f"  replayed {tb.get('queries_replayed', 0)} · "
            f"binding coverage {tb.get('binding_coverage', 0.0)} · "
            f"bound-no-data {tb.get('bound_no_data', 0)} · dead (fail) {len(report.fail_verdicts)}",
        ]
        for v in report.fail_verdicts[:20]:
            lines.append(f"    ✗ {v.get('service','?')}/{v.get('signal','?')}: "
                         f"{v.get('remediation') or v.get('expected_metric') or 'no matching series'}")
        if tb.get("suggested_metrics_profile"):
            lines.append(f"  one-line fix: metricsProfile = {tb['suggested_metrics_profile']}")
        lines.append("")
    # Tier A (static, advisory)
    lines += [f"Tier A (static divergence): {report.total_gaps} gap(s) across "
              f"{len(report.tier_a.get('gaps', {}))} class(es)."]
    for key, entries in (report.tier_a.get("gaps") or {}).items():
        lines.append(f"  {key} [{len(entries)}]")
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "LiveComparisonReport",
    "build_live_comparison",
    "run_live_comparison",
    "verdict_id",
    "new_fail_verdicts",
    "ci_gate",
    "load_baseline",
    "render_baseline",
    "render_live_report",
]
