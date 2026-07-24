"""#229 / #226 FR-7 — per-signal_kind grounded threshold defaults.

Spec: docs/design/observability-requirement-shaped/SIGNAL_KIND_THRESHOLDS_REQUIREMENTS.md v0.4.
The honest deliverable: the signal_kind axis + `saturation` as the ONE grounded cell (monotone ceiling
ladder); everything else grounding-pending (defer, never invent).
"""

import yaml

from startd8.observability.artifact_generator import (
    BusinessContext, FunctionalRequirement, ServiceHints, generate_functional_slos,
)
from startd8.observability.obs_config import load_importance_thresholds


def _worker():
    return ServiceHints(service_id="sidekiq", transport="", kinds=["async_worker"])


def _slo(business):
    r = generate_functional_slos(_worker(), business)
    return yaml.safe_load(r.content) if r.content else None, r


def _biz(kind, *, criticality="high", deployment_mode=None, target=None):
    return BusinessContext(
        criticality=criticality, deployment_mode=deployment_mode,
        functional_requirements=[FunctionalRequirement(id=f"FR-{kind}", signal_kind=kind, target=target)],
    )


class TestSaturationGroundedCell:
    def test_fr2_no_target_binds_config_default_with_tier_label(self):
        # FR-4/FR-4a: a saturation FR with NO author target now BINDS at the grounded config ceiling.
        d, _ = _slo(_biz("saturation", criticality="high", deployment_mode="deployed"))
        assert d["spec"]["target"] == "0.80"
        assert d["metadata"]["labels"]["threshold_tier"] == "default:importance"  # FR-6 on-disk provenance
        assert d["spec"]["indicator"]["spec"]["thresholdMetric"]["metricSource"]["spec"]["query"] \
            == 'max(resource_utilization_ratio{service="sidekiq"})'

    def test_fr5_installed_mode_gets_forgiving_ceiling(self):
        d, _ = _slo(_biz("saturation", criticality="high", deployment_mode="installed"))
        assert d["spec"]["target"] == "0.90"  # forgiving vs deployed 0.80

    def test_fr2a_criticality_ladder(self):
        vals = {c: _slo(_biz("saturation", criticality=c, deployment_mode="deployed"))[0]["spec"]["target"]
                for c in ("critical", "high", "medium", "low")}
        assert vals == {"critical": "0.75", "high": "0.80", "medium": "0.85", "low": "0.90"}

    def test_nr3_author_target_wins_byte_identical(self):
        # authored path: target = author's, NO threshold_tier label (byte-identical to pre-#229).
        d, _ = _slo(_biz("saturation", criticality="high", target="0.6"))
        assert d["spec"]["target"] == "0.6"
        assert "threshold_tier" not in d["metadata"]["labels"]


class TestGroundingPending:
    def test_nr1_freshness_still_defers_no_invented_value(self):
        _, r = _slo(_biz("freshness"))
        assert r.status == "skipped"
        assert any(u["signal_kind"] == "freshness" for u in r.quality["unfulfilled"])

    def test_nr1_run_success_grounding_pending(self):
        # R1-F7: run_success's ratio query is a bare rate → deliberately NOT filled → defers.
        _, r = _slo(_biz("run_success"))
        assert any(u["signal_kind"] == "run_success" for u in r.quality["unfulfilled"])

    def test_nr1_queue_depth_defers(self):
        _, r = _slo(_biz("queue_depth"))
        assert any(u["signal_kind"] == "queue_depth" for u in r.quality["unfulfilled"])


class TestTableInvariants:
    def test_fr2a_monotonic_ceiling_and_omit_key(self):
        # FR-2a: saturation is a ceiling — non-decreasing as criticality DROPS; installed >= deployed
        # (forgiving); no cell > 0.95. And the grounding-pending kinds are OMITTED (R1-F5).
        t = load_importance_thresholds(None)
        order = ["critical", "high", "medium", "low"]
        deployed = [float(t[c]["deployed"]["saturation"]) for c in order]
        assert deployed == sorted(deployed)          # non-decreasing as criticality drops
        for c in order:
            dep = float(t[c]["deployed"]["saturation"])
            ins = float(t[c]["installed"]["saturation"])
            assert ins >= dep and ins <= 0.95        # installed forgiving, capped
            # grounding-pending kinds must be absent (omit-key → None → defer)
            for pending in ("freshness", "queue_depth", "lag", "retry_rate", "run_success"):
                assert pending not in t[c]["deployed"] and pending not in t[c]["installed"]

    def test_nr4_red_fields_untouched(self):
        # NR-4: the new saturation key must not perturb the existing availability/latency resolution.
        t = load_importance_thresholds(None)
        assert t["high"]["deployed"]["availability"] == "99.5"
        assert t["high"]["deployed"]["latency_p99"] == "400ms"
        assert "throughput" not in t["high"]["deployed"]  # NR-2: throughput stays flat
