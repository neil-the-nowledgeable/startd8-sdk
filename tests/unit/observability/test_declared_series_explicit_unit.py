"""Consumer half of contextcore#404 — a producer-stamped `unit` on declared_emitted_series OVERRIDES
the SDK's name-suffix inference for latency threshold scaling (F1). Absent/unrecognized ⇒ name-inference
(byte-identical). Pairs with `METRIC_ACTIVATION_TAXONOMY.md` / `REQ-declared-latency-unit-scaling.md`.
"""

import json

from startd8.observability.artifact_generator import generate_observability_artifacts
from startd8.observability.artifact_generator_generators import _normalize_unit


def test_normalize_unit():
    assert _normalize_unit("seconds") == "s"
    assert _normalize_unit("milliseconds") == "ms"
    assert _normalize_unit("MS") == "ms"
    assert _normalize_unit("s") == "s"
    assert _normalize_unit("") == ""          # absent → fall through
    assert _normalize_unit("furlongs") == ""  # unrecognized → fall through, never worsens the guess


def _latency_target(tmp_path, series_name, unit=None):
    series = {"name": series_name, "type": "histogram", "labels": {"x": "1"}, "covers": ["latency"]}
    if unit is not None:
        series["unit"] = unit
    doc = {"project_id": "p", "instrumentation_hints": {"svc": {
        "service_id": "svc", "service_name": "svc", "kind": "http_server", "transport": "http",
        "metrics_surface": "prometheus_exporter", "metrics": {"declared_emitted_series": [series]}}}}
    p = tmp_path / "onboarding-metadata.json"
    p.write_text(json.dumps(doc))
    report = generate_observability_artifacts(onboarding_metadata_path=p, output_dir=tmp_path / "out", dry_run=False)
    for a in report.artifacts:
        if "declared-base" in a.output_path and a.status == "generated":
            for line in a.content.splitlines():
                if line.strip().startswith("target:"):
                    return line.strip()[len("target:"):].strip()
    return None


def test_explicit_unit_overrides_misleading_seconds_name(tmp_path):
    # name says seconds, producer says milliseconds → explicit WINS → ms scaling → 500.
    assert _latency_target(tmp_path, "http_request_duration_seconds", unit="milliseconds") == "500"


def test_explicit_unit_overrides_misleading_ms_name(tmp_path):
    # name says milliseconds, producer says seconds → explicit WINS → seconds → 0.5.
    assert _latency_target(tmp_path, "istio_request_duration_milliseconds", unit="seconds") == "0.5"


def test_explicit_unit_retires_the_guess_on_suffixless_name(tmp_path):
    # harbor_task_queue_latency has NO unit suffix (would guess seconds→0.5); producer stamps ms → 500.
    assert _latency_target(tmp_path, "harbor_task_queue_latency", unit="milliseconds") == "500"


def test_absent_unit_is_byte_identical_name_inference(tmp_path):
    # no unit field → name-inference, exactly as before (#424).
    assert _latency_target(tmp_path, "http_request_duration_seconds", unit=None) == "0.5"
    assert _latency_target(tmp_path, "istio_request_duration_milliseconds", unit=None) == "500"


def test_unrecognized_unit_falls_through_to_name(tmp_path):
    # a garbage unit must NOT worsen the guess — falls through to the name suffix.
    assert _latency_target(tmp_path, "http_request_duration_seconds", unit="furlongs") == "0.5"
