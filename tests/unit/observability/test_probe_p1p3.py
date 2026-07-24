"""#308 P1–P3 — runner-spec emission, the pending_probe verdict + promotion, and the link-aware core.

Spec: docs/design/observability-compare/SYNTHETIC_PROBE_P1P3_REQUIREMENTS.md v0.4 (unit-tier FRs only;
P2-live and P3-validation are external and NOT exercised here).
"""

import yaml

from startd8.observability.artifact_generator import (
    BusinessContext, DeclaredProbe, ServiceHints, generate_declared_probe_specs,
)
from startd8.observability import compare_live as _cl
from startd8.observability.compare import build_comparison_report
from startd8.observability.validate_promql import FidelityReport, _EXCLUDED_ARTIFACT_DIRS
from startd8.observability.probe_trace import SpanLite, SpanLink, compute_fanout_freshness


def _svc(probes):
    return ServiceHints(service_id="web", transport="http", kinds=["http_server"],
                        declared_probes=probes)


# --- P1: runner-spec emission ------------------------------------------------

class TestP1RunnerSpec:
    def test_fr_p1_1_emits_runnable_spec_with_runner_block(self):
        p = DeclaredProbe(name="fanout", action="POST /statuses", poll="GET /home",
                          assert_="id present")
        r = generate_declared_probe_specs(_svc([p]), BusinessContext())
        assert r.status == "generated" and r.output_path == "probe-specs/web-probe-specs.yaml"
        doc = yaml.safe_load(r.content)
        spec = doc["probes"][0]
        assert spec["runnable"] is True
        assert spec["runner"]["action"] == "POST /statuses"
        assert spec["published_metric"] == "probe_fanout_seconds"

    def test_fr_p1_2_incomplete_spec_is_structurally_non_runnable(self):
        # NR-6: missing poll/assert → runnable:false so a runner can't run a partial spec.
        p = DeclaredProbe(name="fanout", action="POST /statuses")  # no poll/assert
        spec = yaml.safe_load(generate_declared_probe_specs(_svc([p]), BusinessContext()).content)["probes"][0]
        assert spec["runnable"] is False
        assert "UNRESOLVED" in spec["unresolved"]

    def test_fr_p1_2_secret_refs_extracted_not_inlined(self):
        p = DeclaredProbe(name="fanout", action="POST ${SECRET:TOKEN}", poll="GET ${ENV:BASE_URL}",
                          assert_="ok")
        spec = yaml.safe_load(generate_declared_probe_specs(_svc([p]), BusinessContext()).content)["probes"][0]
        assert spec["required_secrets"] == ["ENV:BASE_URL", "SECRET:TOKEN"]

    def test_fr_p1_1_no_probes_skipped_no_file(self):
        r = generate_declared_probe_specs(_svc([]), BusinessContext())
        assert r.status == "skipped" and r.output_path == ""

    def test_fr_p1_3_probe_specs_excluded_from_promql_replay(self):
        assert _EXCLUDED_ARTIFACT_DIRS.get("probe-specs") == "probe_spec"


# --- P2: pending_probe verdict + promotion (SDK harness; live proof external) ---

class TestP2Verdict:
    def test_fr_p2_1_synthesizes_verdict_joined_on_published_metric(self):
        # R1-F4: identity is the recorded published_metric (author-overridable, no probe_ prefix heuristic).
        fc = {"pending_probes": [{"service": "web", "name": "fanout",
                                  "published_metric": "mastodon_fanout_seconds",  # no probe_ prefix
                                  "query": "max(mastodon_fanout_seconds{service=\"web\"})"}]}
        vs = _cl.pending_probe_verdicts(fc)
        assert len(vs) == 1 and vs[0]["verdict"] == "pending_probe"
        assert vs[0]["metric"] == "mastodon_fanout_seconds"

    def test_fr_p2_1_unbindable_entry_yields_no_verdict(self):
        # an unsupported metric_kind/signal_kind entry carries no query → nothing to synthesize.
        fc = {"pending_probes": [{"service": "web", "name": "x", "reason_code": "probe_unsupported_metric_kind"}]}
        assert _cl.pending_probe_verdicts(fc) == []

    def test_fr_p2_1_pending_probe_is_severity_zero_never_fail(self):
        # R1-F2/F3: declared severity 0 (not a .get default) — a pending probe never rolls up to fail/exit-2.
        assert _cl._SEVERITY["pending_probe"] == 0
        assert _cl._SEVERITY["pending_probe"] < _cl._SEVERITY["fail"]

    def test_fr_p2_1_pending_probe_never_in_fail_set(self):
        # it is not "fail", so it is excluded from the CI fail_verdicts / baseline diff by construction.
        v = _cl.pending_probe_verdicts({"pending_probes": [{"service": "web", "name": "f",
                                        "published_metric": "m", "query": "max(m)"}]})[0]
        assert v["verdict"] != "fail"

    def test_fr_p2_2_promotion_reuses_recorded_query(self):
        # R1-F8 (Mottainai): the promoted SLO's PromQL == the recorded query; target carried; naming disambiguates.
        entry = {"service": "web", "name": "fanout", "query": 'max(probe_fanout_seconds{service="web"})',
                 "target": "5"}
        slo = _cl.promote_probe_slo(entry, slo_window="30d")
        q = slo["spec"]["indicator"]["spec"]["thresholdMetric"]["metricSource"]["spec"]["query"]
        assert q == 'max(probe_fanout_seconds{service="web"})'
        assert slo["spec"]["target"] == "5"
        assert slo["metadata"]["name"] == "web-fanout-probe"

    def test_fr_p2_2_promotion_of_queryless_entry_raises(self):
        # code-review M1: a query-less pending entry (unbindable kind) must fail loudly, not KeyError.
        import pytest
        with pytest.raises(ValueError, match="no grounded query"):
            _cl.promote_probe_slo({"service": "web", "name": "x",
                                   "reason_code": "probe_unsupported_metric_kind"})

    # --- EC-1: the pending_probe verdict is now WIRED into build_live_comparison ---

    def _fidelity(self):
        return FidelityReport(status="pass", queries_replayed=1, reason="", coverage=1.0,
                              min_coverage=1.0)

    def _live_report(self, fidelity):
        fc = {"pending_probes": [{"service": "web", "name": "fanout", "published_metric": "m",
                                  "query": "max(m)", "reason_code": "probe_runner_emitted"}]}
        comparison = build_comparison_report(fc)
        return _cl.build_live_comparison(comparison, fidelity, {"skipped": True})

    def test_ec1_pending_verdict_merged_into_tier_b_not_fail(self):
        # EC-1 (built-but-unwired fix): a live run's Tier-B verdict list now carries the pending probe,
        # it is NOT a fail, and it does not flip status to fail.
        rep = self._live_report(self._fidelity())
        assert len(rep.pending_verdicts) == 1 and rep.pending_verdicts[0]["verdict"] == "pending_probe"
        assert any(v.get("verdict") == "pending_probe" for v in rep.tier_b["verdicts"])
        assert rep.fail_verdicts == []
        assert rep.status != "fail"
        # versioned JSON contract bumped + carries the new key.
        d = rep.to_dict()
        assert d["report_version"] == 2 and len(d["pending_verdicts"]) == 1

    def test_ec1_pending_rendered_distinctly_from_dead(self):
        text = _cl.render_live_report(self._live_report(self._fidelity()))
        assert "Pending probes — freshness SLIs awaiting a runner" in text
        assert "web/fanout: pending runner" in text

    def test_ec1_pending_carried_even_when_standup_failed(self):
        # fidelity None (standup/scrape failed) → unknown, but the Tier-A-derived pending still surfaces.
        rep = self._live_report(None)
        assert rep.status == "unknown" and len(rep.pending_verdicts) == 1


# --- P3: link-aware pure delta core (validation trace-gated / external) ---

class TestP3LinkAwareCore:
    def _enqueue(self):
        return SpanLite(trace_id="t1", span_id="enq", start_ns=1_000_000_000, end_ns=1_100_000_000)

    def _worker(self, links, end_ns=3_000_000_000):
        return SpanLite(trace_id="t2", span_id="wrk", start_ns=2_000_000_000, end_ns=end_ns,
                        name="FeedInsertWorker", links=links)

    def test_ok_delta_seconds(self):
        r = compute_fanout_freshness(self._enqueue(), self._worker([SpanLink("t1", "enq")]))
        assert r.status == "ok" and abs(r.delta_seconds - 2.0) < 1e-9  # (3.0 - 1.0)s

    def test_unlinkable_when_no_link(self):
        r = compute_fanout_freshness(self._enqueue(), self._worker([]))
        assert r.status == "unlinkable" and r.delta_seconds is None

    def test_error_on_reversed_span(self):
        bad = SpanLite(trace_id="t2", span_id="wrk", start_ns=5, end_ns=1, links=[SpanLink("t1", "enq")])
        assert compute_fanout_freshness(self._enqueue(), bad).status == "error"

    def test_error_when_feed_visible_precedes_creation(self):
        # worker ends before the enqueue starts → error, never a negative delta.
        early = self._worker([SpanLink("t1", "enq")], end_ns=500_000_000)  # < enqueue.start 1e9
        assert compute_fanout_freshness(self._enqueue(), early).status == "error"
