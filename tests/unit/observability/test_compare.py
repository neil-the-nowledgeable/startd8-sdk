"""Tier-A derived-vs-declared comparison (docs/design/OBSERVABILITY_DERIVED_VS_EMITTED_COMPARISON.md)."""
from __future__ import annotations

import yaml

from startd8.observability.compare import (
    build_comparison_report,
    read_fr_coverage,
    render_report,
)


def test_no_divergence_reads_clean():
    r = build_comparison_report({"emitted": ["FR-1"], "unfulfilled": [], "suppressed_base_metrics": []})
    assert r.total_gaps == 0 and r.emitted == ["FR-1"]
    assert "No divergence" in render_report(r)


def test_divergence_classes_reported_with_counts_and_reasons():
    fc = {
        "emitted": [],
        "suppressed_base_metrics": [
            {"service": "web", "metrics_surface": "traces_only", "reason": "base RED SLIs suppressed"}],
        "unfulfilled": [{"id": "FR-7", "signal_kind": "freshness", "reason": "no emitting series"}],
        "empty_services": ["mailer"],
    }
    r = build_comparison_report(fc)
    assert r.total_gaps == 3 and set(r.gaps) == {"suppressed_base_metrics", "unfulfilled", "empty_services"}
    text = render_report(r)
    assert "SUPPRESSED base SLIs" in text and "web: base RED SLIs suppressed" in text
    assert "mailer" in text and "FR-7" in text
    assert "validate-promql" in text  # points at Tier B


def test_bound_declared_series_shown_as_positive():
    # #286: a base SLI bound to a real declared series is grounding (positive), not a gap.
    r = build_comparison_report({
        "emitted": [],
        "bound_declared_series": [
            {"service": "web", "kind": "latency", "series": "http_request_duration_seconds"}],
    })
    assert r.total_gaps == 0 and len(r.bound) == 1
    text = render_report(r)
    assert "Bound to declared emitted series" in text
    assert "web: latency → http_request_duration_seconds" in text
    assert r.to_dict()["bound_count"] == 1


def test_deferred_declared_kinds_reported_as_a_gap_class():
    # #286: a covered-but-not-yet-bindable kind (availability w/o error-selector) is a gap.
    r = build_comparison_report({
        "emitted": [],
        "deferred_declared_kinds": [
            {"service": "web", "kind": "availability", "series": "http_requests_total"}],
    })
    assert "deferred_declared_kinds" in r.gaps
    text = render_report(r)
    assert "DEFERRED declared kinds" in text
    assert "web: availability → http_requests_total" in text


def test_read_fr_coverage_from_a_manifest(tmp_path):
    m = tmp_path / "observability-manifest.yaml"
    m.write_text(yaml.safe_dump({"fr_coverage": {"emitted": ["FR-1"], "empty_services": ["x"]}}))
    assert read_fr_coverage(m) == {"emitted": ["FR-1"], "empty_services": ["x"]}
    # a manifest with no fr_coverage (fully grounded) → {}
    m2 = tmp_path / "clean.yaml"; m2.write_text(yaml.safe_dump({"version": "1.0"}))
    assert read_fr_coverage(m2) == {}
