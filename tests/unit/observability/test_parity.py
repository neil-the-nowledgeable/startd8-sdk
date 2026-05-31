"""Tests for descriptor↔emission parity (REQ-OBS-SHARED-002): kind-aware sub-checks
+ bootstrap exclusion registry."""

from startd8.observability.manifest import MetricDescriptor, ObservabilityManifest
from startd8.observability.parity import (
    check_metric_bijection,
    check_metric_identity,
    exported_name,
    run_parity,
)


def _m(name, prom=None):
    return MetricDescriptor(name=name, instrument="counter", unit="1", description="d",
                            prometheus_name=prom)


class TestExportedName:
    def test_dot_to_underscore(self):
        assert exported_name("startd8.session.cost.total") == "startd8_session_cost_total"

    def test_explicit_prometheus_name_wins(self):
        assert exported_name("startd8.cost.total", "custom_name") == "custom_name"


class TestMetricIdentity:
    def test_exported_name_collision_detected(self):
        # Distinct canonical names colliding on the exported surface (R3-F2).
        man = ObservabilityManifest(metrics=[_m("startd8.cost.total"), _m("startd8_cost_total")])
        collisions = check_metric_identity(man)
        assert len(collisions) == 1
        assert "startd8_cost_total" in collisions[0]

    def test_explicit_prometheus_name_avoids_collision(self):
        man = ObservabilityManifest(metrics=[
            _m("startd8.cost.total", prom="startd8_cost_total_v2"),
            _m("startd8_cost_total"),
        ])
        assert check_metric_identity(man) == []


class TestMetricBijection:
    def test_declared_not_emitted_flagged(self):
        man = ObservabilityManifest(metrics=[_m("startd8.phantom.metric")])
        r = check_metric_bijection(man, emitted={})  # nothing emitted
        assert r.declared_not_emitted == ["startd8.phantom.metric"]
        assert not r.ok

    def test_emitted_not_declared_unowned_is_hard(self):
        man = ObservabilityManifest(metrics=[])
        r = check_metric_bijection(man, emitted={"some.random.metric": ["f.py"]})
        assert r.emitted_not_declared == ["some.random.metric"]
        assert not r.ok

    def test_excluded_emitter_is_tolerated(self, monkeypatch):
        # The live EMITTER_EXCLUSIONS registry is now EMPTY (B complete — every
        # emitter is declared). This test exercises the bootstrap MECHANISM with a
        # synthetic owned exclusion, so it stays valid regardless of registry
        # contents: an excluded emitter is reported as bootstrap, not hard-failed.
        from startd8.observability import parity as _parity

        synthetic = _parity.EmitterExclusion("synthetic.", "test", "mechanism check", prefix=True)
        monkeypatch.setattr(_parity, "EMITTER_EXCLUSIONS", [synthetic])

        man = ObservabilityManifest(metrics=[])
        r = check_metric_bijection(man, emitted={"synthetic.template_hits": ["f.py"]})
        assert r.emitted_not_declared == []
        assert r.bootstrap_undeclared == ["synthetic.template_hits"]
        assert r.ok

    def test_declared_and_emitted_matches(self):
        man = ObservabilityManifest(metrics=[_m("startd8.cost.total")])
        r = check_metric_bijection(man, emitted={"startd8.cost.total": ["f.py"]})
        assert r.ok


class TestExportNamePreservation:
    """Phase 2 dotted rename preserves the exported Prometheus names byte-for-byte
    for the 6 round-tripping session metrics; the cost metric changes intentionally
    (R1-S4 golden baseline; the documented dot->underscore model — the live OTel
    Prometheus exporter's unit/_total suffixes are an integration-level concern)."""

    # dotted OTel name -> expected exported Prometheus name
    GOLDEN = {
        "startd8.active.sessions": "startd8_active_sessions",
        "startd8.requests.total": "startd8_requests_total",
        "startd8.tokens.total": "startd8_tokens_total",
        "startd8.response.time_ms": "startd8_response_time_ms",
        "startd8.context.usage_ratio": "startd8_context_usage_ratio",
        "startd8.truncations.total": "startd8_truncations_total",
        # Intentionally NOT startd8_cost_total — disambiguated from the global metric.
        "startd8.session.cost.total": "startd8_session_cost_total",
    }

    def test_dotted_names_reproduce_golden_export_names(self):
        for dotted, expected in self.GOLDEN.items():
            assert exported_name(dotted) == expected, f"{dotted} -> {exported_name(dotted)} != {expected}"

    def test_session_cost_no_longer_collides_with_global(self):
        # The global cost metric keeps startd8_cost_total; the per-session one moved.
        assert exported_name("startd8.session.cost.total") != exported_name("startd8.cost.total")


class TestRealManifestParity:
    def test_real_manifest_full_parity(self):
        # B complete: every live emitter is declared and registered, so the
        # bijection holds with ZERO bootstrap tolerance. EMITTER_EXCLUSIONS is
        # empty and this asserts the post-B end-state invariant (not bootstrap mode).
        r = run_parity()
        assert r.ok
        assert r.declared_not_emitted == []
        assert r.emitted_not_declared == []
        assert r.bootstrap_undeclared == [], (
            "EMITTER_EXCLUSIONS should be empty now that B is complete; "
            f"unexpected bootstrap gaps: {r.bootstrap_undeclared}"
        )
        assert r.exported_name_collisions == []
