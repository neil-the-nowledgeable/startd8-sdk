"""The (D) wire, SLO side — `generate_business_criticality_slos` consumes the `business_criticality`
span-metrics dimension the `collector_enrichment` OTTL processor stamps.

The dashboard counterpart (`generate_business_criticality_dashboard`) already *visualizes* traffic/error
by tier; this gates an **error budget per tier** (one availability SLO per criticality tier, a stricter
tier getting a tighter target). Presence-gated on the same signal — absent criticality ⇒ skipped
(byte-identical to pre-feature), because the label wouldn't exist and the SLIs would be dead.
"""

from __future__ import annotations

import yaml

from startd8.observability.artifact_generator_generators import (
    _BUSINESS_CRITICALITY_SLO_PATH,
    _CRITICALITY_TO_AVAILABILITY_TARGET,
    generate_business_criticality_slos,
)
from startd8.observability.artifact_generator_models import (
    BusinessContext,
    GenerationReport,
    ServiceHints,
)


def _report() -> GenerationReport:
    return GenerationReport(project_id="ob", generated_at="2026-08-18T00:00:00Z")


def _svc(sid, crit=""):
    return ServiceHints(service_id=sid, service_name=sid, criticality=crit)


def _docs(result):
    return [d for d in yaml.safe_load_all(result.content) if d]


# ── presence gate — byte-identical when the dimension wouldn't exist ────────────────────────────────

def test_skipped_when_no_service_carries_criticality():
    r = generate_business_criticality_slos([_svc("a"), _svc("b")], BusinessContext(), _report())
    assert r.status == "skipped" and r.skip_reason
    assert r.content in ("", None)                                   # nothing emitted


def test_generated_when_at_least_one_service_has_criticality():
    r = generate_business_criticality_slos([_svc("a", "critical"), _svc("b")], BusinessContext(), _report())
    assert r.status == "generated" and r.artifact_type == "slo_definition"
    assert r.output_path == _BUSINESS_CRITICALITY_SLO_PATH


# ── one SLO per tier, deduped ───────────────────────────────────────────────────────────────────────

def test_one_slo_per_distinct_tier_deduped():
    svcs = [_svc("a", "critical"), _svc("b", "high"), _svc("c", "critical")]  # critical appears twice
    docs = _docs(generate_business_criticality_slos(svcs, BusinessContext(), _report()))
    names = [d["metadata"]["name"] for d in docs]
    assert names == ["business-criticality-critical-availability", "business-criticality-high-availability"]


# ── the SLIs CONSUME the stamped label (the whole point of the wire) ────────────────────────────────

def test_slis_query_calls_total_by_business_criticality():
    docs = _docs(generate_business_criticality_slos([_svc("a", "critical")], BusinessContext(), _report()))
    rm = docs[0]["spec"]["indicator"]["spec"]["ratioMetric"]
    total = rm["total"]["metricSource"]["spec"]["query"]
    good = rm["good"]["metricSource"]["spec"]["query"]
    assert total == 'sum(rate(calls_total{business_criticality="critical"}[5m]))'
    assert good == 'sum(rate(calls_total{business_criticality="critical",status_code!="STATUS_CODE_ERROR"}[5m]))'


# ── stricter tier → tighter target; severity mirrors the criticality map ────────────────────────────

def test_target_per_tier_stricter_is_tighter():
    svcs = [_svc("a", "critical"), _svc("b", "high"), _svc("c", "medium"), _svc("d", "low")]
    by_name = {d["metadata"]["name"]: d for d in _docs(generate_business_criticality_slos(svcs, BusinessContext(), _report()))}

    def tgt(tier):
        return by_name[f"business-criticality-{tier}-availability"]["spec"]["target"]

    assert tgt("critical") == _CRITICALITY_TO_AVAILABILITY_TARGET["critical"] == 99.9
    assert tgt("critical") > tgt("high") > tgt("medium") > tgt("low")  # monotone: stricter → tighter


def test_unknown_tier_falls_back_to_default_target():
    docs = _docs(generate_business_criticality_slos([_svc("a", "bespoke-tier")], BusinessContext(), _report()))
    assert docs[0]["spec"]["target"] == 99.0                          # _DEFAULT_THRESHOLDS availability


def test_severity_label_mirrors_the_criticality_map():
    docs = _docs(generate_business_criticality_slos([_svc("a", "critical"), _svc("b", "low")], BusinessContext(), _report()))
    sev = {d["metadata"]["name"]: d["spec"]["alerting"]["labels"]["severity"] for d in docs}
    assert sev["business-criticality-critical-availability"] == "critical"
    assert sev["business-criticality-low-availability"] == "info"


# ── valid OpenSLO v1 (flows through the same validation as every SLO) ───────────────────────────────

def test_each_doc_is_valid_openslo_v1():
    docs = _docs(generate_business_criticality_slos([_svc("a", "critical"), _svc("b", "high")], BusinessContext(), _report()))
    for d in docs:
        assert d["apiVersion"] == "openslo/v1" and d["kind"] == "SLO"
        rm = d["spec"]["indicator"]["spec"]["ratioMetric"]
        assert "good" in rm and "total" in rm
        assert d["spec"]["timeWindow"]["duration"]                    # window present


def test_window_comes_from_business_context():
    r = generate_business_criticality_slos([_svc("a", "critical")], BusinessContext(slo_window="7d"), _report())
    assert _docs(r)[0]["spec"]["timeWindow"]["duration"] == "7d"
