# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Unit tests for coverage_reconcile — the pure expected-vs-actual join (REQ-TCP-100/101).

Fixtures are inline ``LiveComparisonReport.to_dict()``-shaped dicts (no docker, no re-query),
mirroring test_compare_live.py's builder style. Every presence_status is exercised, plus the
criticality-resolution precedence and the summarize() rollup.
"""

from __future__ import annotations

from startd8.observability import coverage_reconcile as cr


def _ps(coverage, signals=None, total=1, passed=0):
    """A tier_b.per_service[svc] entry."""
    return {"total": total, "passed": passed, "coverage": coverage, "signals": signals or {}}


def _report(*, tier_b=None, tier_a=None, pending=None, **top):
    base = {
        "report_version": 2,
        "status": "pass",
        "reason": "ok",
        "tier_a": tier_a or {"gaps": {}},
        "tier_b": tier_b,
        "pending_verdicts": pending or [],
    }
    base.update(top)
    return base


def _by_service(records):
    return {r.service: r for r in records}


# ─────────────────────────── liveness / stale (EC-13) ──────────────────────


def test_liveness_downgrades_bound_to_stale():
    tb = {"per_service": {"web": _ps(1.0), "cart": _ps(1.0)}}
    recs = _by_service(cr.reconcile(_report(tier_b=tb), liveness={"web": True, "cart": False}))
    assert recs["web"].presence_status == cr.BOUND     # live → bound
    assert recs["cart"].presence_status == cr.STALE    # no recent traffic → stale
    assert "went dark" in recs["cart"].next_step


def test_liveness_absent_is_backward_compatible():
    tb = {"per_service": {"web": _ps(1.0)}}
    r = cr.reconcile(_report(tier_b=tb))  # no liveness arg
    assert r[0].presence_status == cr.BOUND


def test_summarize_counts_stale_as_not_observable():
    tb = {"per_service": {"web": _ps(1.0), "cart": _ps(1.0)}}
    recs = cr.reconcile(_report(tier_b=tb), criticality_map={"web": "critical", "cart": "critical"},
                        liveness={"web": True, "cart": False})
    s = cr.summarize(recs)
    assert s["by_criticality"]["critical"]["coverage"] == 0.5   # stale drags the tier down
    assert "cart" in s["by_criticality"]["critical"]["not_bound"]


# ─────────────────────────── presence taxonomy ─────────────────────────────


def test_bound_service():
    tb = {"per_service": {"web": _ps(1.0, {"latency": {"total": 1, "passed": 1}})}}
    recs = _by_service(cr.reconcile(_report(tier_b=tb)))
    assert recs["web"].presence_status == cr.BOUND
    assert recs["web"].binding_coverage == 1.0
    assert recs["web"].actual_axes == ["latency"]
    assert recs["web"].missing_signals == []


def test_partial_service():
    tb = {"per_service": {"web": _ps(0.5, {
        "latency": {"total": 1, "passed": 1},
        "errors": {"total": 1, "passed": 0},
    })}}
    r = _by_service(cr.reconcile(_report(tier_b=tb)))["web"]
    assert r.presence_status == cr.PARTIAL
    assert r.binding_coverage == 0.5
    assert r.actual_axes == ["latency"]
    assert r.missing_signals == ["errors"]
    assert "errors" in r.next_step


def test_no_telemetry_service():
    tb = {"per_service": {"cart": _ps(0.0, {"latency": {"total": 1, "passed": 0}})}}
    r = _by_service(cr.reconcile(_report(tier_b=tb)))["cart"]
    assert r.presence_status == cr.NO_TELEMETRY
    assert r.binding_coverage == 0.0


def test_declared_absent_from_target_drift():
    tb = {
        "per_service": {},
        "target_drift": {"declared_absent": ["payments"], "checked": True},
    }
    r = _by_service(cr.reconcile(_report(tier_b=tb)))["payments"]
    assert r.presence_status == cr.DECLARED_ABSENT
    assert r.binding_coverage is None
    assert "deploy" in r.next_step


def test_live_coverage_beats_declared_absent():
    """EC-RECONCILE-ABSENT-SHADOWS-LIVE: identity-label drift must not hide live binds."""
    tb = {
        "per_service": {
            "receive": _ps(0.5, {"throughput": {"total": 2, "passed": 1}}),
        },
        "target_drift": {"declared_absent": ["receive"], "checked": True},
    }
    r = _by_service(cr.reconcile(_report(tier_b=tb)))["receive"]
    assert r.presence_status == cr.PARTIAL
    assert r.binding_coverage == 0.5
    assert r.provenance.get("identity_label_drift") is True


def test_declared_absent_when_per_service_coverage_zero():
    """Zero live coverage + identity absent → keep deploy hint (declared_absent)."""
    tb = {
        "per_service": {
            "payments": _ps(0.0, {"latency": {"total": 1, "passed": 0}}),
        },
        "target_drift": {"declared_absent": ["payments"], "checked": True},
    }
    r = _by_service(cr.reconcile(_report(tier_b=tb)))["payments"]
    assert r.presence_status == cr.DECLARED_ABSENT
    assert r.binding_coverage == 0.0


def test_pending_probe_is_positive_not_a_gap():
    pending = [{"verdict": "pending_probe", "service": "feed", "probe": "fanout"}]
    r = _by_service(cr.reconcile(_report(tier_b={"per_service": {}}, pending=pending)))["feed"]
    assert r.presence_status == cr.PENDING_PROBE
    assert r.binding_coverage is None


def test_tier_b_missing_is_degraded_not_fabricated():
    # Standup/scrape failed → tier_b None. Service known only via hints must be degraded,
    # never silently reported as bound (NR-3 fail-loud).
    hints = {"web": {"criticality": "high"}}
    r = _by_service(cr.reconcile(_report(tier_b=None), service_hints=hints))["web"]
    assert r.presence_status == cr.DEGRADED
    assert r.binding_coverage is None


def test_suppressed_base_metrics_is_not_degraded():
    """#363: generation-side omission ≠ standup unavailable."""
    tier_a = {
        "gaps": {
            "suppressed_base_metrics": [
                {
                    "service": "receive",
                    "metrics_surface": "prometheus_exporter",
                    "suppressed_sli_kinds": ["availability", "latency", "throughput"],
                    "reason": (
                        "base RED SLIs suppressed — metrics_surface='prometheus_exporter' "
                        "does not emit the OTel-convention meter"
                    ),
                }
            ]
        }
    }
    # tier_b present but empty for this service — the Thanos pilot shape.
    r = _by_service(
        cr.reconcile(_report(tier_b={"per_service": {}}, tier_a=tier_a))
    )["receive"]
    assert r.presence_status == cr.SUPPRESSED
    assert r.binding_coverage is None
    assert "re-run compare-live" not in r.next_step
    assert "generation" in r.next_step.lower() or "suppressed" in r.next_step.lower()
    assert r.provenance.get("metrics_surface") == "prometheus_exporter"
    assert r.expected_axes == ["availability", "latency", "throughput"]


def test_suppressed_does_not_override_per_service_binding():
    """A service with Tier-B queries stays bound/partial even if also in suppressed gaps."""
    tier_a = {
        "gaps": {
            "suppressed_base_metrics": [
                {"service": "compact", "metrics_surface": "prometheus_exporter"}
            ]
        }
    }
    tb = {"per_service": {"compact": _ps(1.0, {"throughput": {"total": 1, "passed": 1}})}}
    r = _by_service(cr.reconcile(_report(tier_b=tb, tier_a=tier_a)))["compact"]
    assert r.presence_status == cr.BOUND


def test_fail_verdict_remediation_and_mismatch_folded_in():
    tb = {
        "per_service": {"web": _ps(0.5, {"latency": {"total": 1, "passed": 1}})},
        "verdicts": [{
            "service": "web", "signal": "errors", "verdict": "fail",
            "mismatched_axes": ["error_selector"], "remediation": "label the 5xx series",
        }],
    }
    r = _by_service(cr.reconcile(_report(tier_b=tb)))["web"]
    assert "error_selector" in r.missing_signals
    assert r.next_step == "label the 5xx series"


# ─────────────────────────── criticality resolution (REQ-TCP-103) ───────────


def test_criticality_map_wins_over_hint():
    tb = {"per_service": {"web": _ps(1.0)}}
    hints = {"web": {"criticality": "low", "owner": "team-a"}}
    r = _by_service(cr.reconcile(_report(tier_b=tb), criticality_map={"web": "critical"}, service_hints=hints))["web"]
    assert r.criticality == "critical"   # map authoritative
    assert r.owner == "team-a"           # owner still from hint


def test_criticality_falls_back_to_hint_then_unknown():
    tb = {"per_service": {"a": _ps(1.0), "b": _ps(1.0)}}
    hints = {"a": {"criticality": "medium"}}  # b has no hint
    recs = _by_service(cr.reconcile(_report(tier_b=tb), service_hints=hints))
    assert recs["a"].criticality == "medium"
    assert recs["b"].criticality == cr.UNKNOWN_CRITICALITY


# ─────────────────────────── determinism + rollup ───────────────────────────


def test_reconcile_is_deterministic_and_sorted():
    tb = {"per_service": {"z": _ps(1.0), "a": _ps(0.0)}}
    r1 = cr.reconcile(_report(tier_b=tb))
    r2 = cr.reconcile(_report(tier_b=tb))
    assert [x.service for x in r1] == ["a", "z"]       # sorted
    assert [x.to_dict() for x in r1] == [x.to_dict() for x in r2]  # deterministic


def test_summarize_answers_are_critical_services_observable():
    tb = {
        "per_service": {
            "checkout": _ps(1.0),   # critical, bound
            "cart": _ps(0.0),       # critical, no_telemetry
            "recs": _ps(1.0),       # low, bound
        },
        "target_drift": {"declared_absent": [], "checked": True},
    }
    crit = {"checkout": "critical", "cart": "critical", "recs": "low"}
    summary = cr.summarize(cr.reconcile(_report(tier_b=tb), criticality_map=crit))
    assert summary["by_criticality"]["critical"]["coverage"] == 0.5
    assert summary["critical_not_bound"] == ["cart"]
    assert summary["by_status"][cr.BOUND] == 2
    assert summary["by_status"][cr.NO_TELEMETRY] == 1


def test_summarize_excludes_pending_from_denominator():
    tb = {"per_service": {"web": _ps(1.0)}}
    pending = [{"verdict": "pending_probe", "service": "feed"}]
    crit = {"web": "critical", "feed": "critical"}
    summary = cr.summarize(cr.reconcile(_report(tier_b=tb, pending=pending), criticality_map=crit))
    # feed (pending) must not drag critical coverage below 1.0
    assert summary["by_criticality"]["critical"]["coverage"] == 1.0
    assert summary["by_criticality"]["critical"]["denominator"] == 1
