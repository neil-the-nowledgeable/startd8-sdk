"""Declared-series latency threshold unit-scaling (audit F1 / REQ-declared-latency-unit-scaling).

Before the fix, the declared-emitted-series latency SLO shipped the raw string ``target: 500ms`` against
a numeric ``histogram_quantile`` SLI — a type/unit mismatch, verified live on real Harbor output
(core/jobservice/registry). Now the target is a NUMBER in the SLI's native unit, mirroring the
convention path.
"""

import json

from startd8.observability.artifact_generator import generate_observability_artifacts
from startd8.observability.artifact_generator_generators import _metric_unit
from startd8.observability.metric_descriptor import scale_seconds_to_unit


# --- FR-1: _metric_unit distinguishes seconds from milliseconds by name ---

def test_metric_unit_recognizes_milliseconds():
    assert _metric_unit("istio_request_duration_milliseconds") == "ms"
    assert _metric_unit("something_millis") == "ms"


def test_metric_unit_seconds_and_unknown():
    assert _metric_unit("http_request_duration_seconds") == "s"
    assert _metric_unit("harbor_task_queue_latency") == ""  # no unit suffix → unknown (FR-3 fallback)


def test_scale_seconds_to_unit_single_authority():
    assert scale_seconds_to_unit(0.5, "s") == 0.5
    assert scale_seconds_to_unit(0.5, "ms") == 500.0
    assert scale_seconds_to_unit(0.5, "") == 0.5  # unknown → seconds


# --- FR-2/FR-3: the declared-latency SLO target is a NUMBER in the SLI's native unit ---

def _latency_target(tmp_path, series_name):
    doc = {"project_id": "p", "instrumentation_hints": {"svc": {
        "service_id": "svc", "service_name": "svc", "kind": "http_server", "transport": "http",
        "metrics_surface": "prometheus_exporter",
        "metrics": {"declared_emitted_series": [
            {"name": series_name, "type": "histogram", "labels": {"x": "1"}, "covers": ["latency"]}]}}}}
    p = tmp_path / "onboarding-metadata.json"
    p.write_text(json.dumps(doc))
    report = generate_observability_artifacts(onboarding_metadata_path=p, output_dir=tmp_path / "out", dry_run=False)
    for a in report.artifacts:
        if "declared-base" in a.output_path and a.status == "generated":
            for line in a.content.splitlines():
                s = line.strip()
                if s.startswith("target:"):
                    return s[len("target:"):].strip()
    return None


def test_seconds_series_scales_to_seconds(tmp_path):
    t = _latency_target(tmp_path, "http_request_duration_seconds")
    assert t == "0.5"                    # numeric seconds, NOT the raw string "500ms"
    assert "ms" not in t


def test_milliseconds_series_scales_to_ms(tmp_path):
    t = _latency_target(tmp_path, "istio_request_duration_milliseconds")
    assert t == "500"                    # numeric ms — coincidentally the old raw number, but as an int
    assert "ms" not in t


def test_no_unit_suffix_defaults_to_seconds(tmp_path):
    # FR-3: a real Harbor case (harbor_task_queue_latency has no suffix) → seconds fallback, numeric.
    t = _latency_target(tmp_path, "harbor_task_queue_latency")
    assert t == "0.5"
    assert "ms" not in t


def test_declared_latency_target_is_never_a_unit_suffixed_string(tmp_path):
    # the defect guard: no declared latency SLO may ship a `<num>ms`/`<num>s` STRING target again.
    for name in ["http_request_duration_seconds", "istio_request_duration_milliseconds", "svc_latency"]:
        t = _latency_target(tmp_path, name)
        assert t is not None and not t.endswith("ms") and not t.endswith("s"), (name, t)
        float(t)  # must parse as a number
