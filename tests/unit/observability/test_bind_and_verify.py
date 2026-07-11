# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Tests for the bind-and-verify orchestrator.

Every external effect (metric-name read, export subprocess, generate, validate) is
injected, so these exercise the orchestration + reconciliation logic with no
network, no subprocess, and no real Prometheus.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import yaml

from startd8.observability.bind_and_verify import (
    EXIT_FAIL,
    EXIT_PASS,
    EXIT_UNKNOWN,
    bind_and_verify,
    read_manifest_profiles,
    write_project_profile,
)


# ───────────────────────────── fixtures / fakes ────────────────────────────


def _manifest(tmp_path: Path, *, project_profile=None, target_profile=None) -> Path:
    observability = {}
    if project_profile:
        observability["metricsProfile"] = project_profile
    target = {"kind": "Deployment", "name": "checkout"}
    if target_profile:
        target["metricsProfile"] = target_profile
    data = {
        "project": {"id": "shop"},
        "spec": {"observability": observability, "targets": [target]},
    }
    path = tmp_path / ".contextcore.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


class _FakeFidelity:
    def __init__(self, status="pass", suggested=""):
        self.status = status
        self.reason = f"coverage vs min ({status})"
        self._suggested = suggested

    def to_dict(self):
        return {
            "status": self.status,
            "reason": self.reason,
            "suggested_metrics_profile": self._suggested,
        }


def _ok_export(calls):
    def _export(manifest_path, output_dir, export_cmd):
        calls.append(("export", Path(manifest_path), Path(output_dir)))
        # Simulate export writing the onboarding file the next steps need.
        (Path(output_dir)).mkdir(parents=True, exist_ok=True)
        (Path(output_dir) / "onboarding-metadata.json").write_text("{}")
        return {"ok": True, "returncode": 0, "stderr_tail": "", "cmd": list(export_cmd)}
    return _export


def _ok_generate(calls):
    def _generate(onboarding, artifacts_dir, manifest_path):
        calls.append(("generate", Path(onboarding), Path(artifacts_dir)))
        return {"ok": True, "services_processed": 1, "artifacts_by_status": {"generated": 3}, "errors": []}
    return _generate


def _validate(fidelity, calls):
    def _v(**kwargs):
        calls.append(("validate", kwargs["artifacts_dir"], kwargs["prometheus_url"]))
        return fidelity
    return _v


def _run(manifest, tmp_path, *, live, fidelity=None, freeze=False, generate=None):
    calls: list = []
    fidelity = fidelity or _FakeFidelity()
    report = bind_and_verify(
        manifest_path=manifest,
        prometheus_url="http://localhost:9090",
        output_dir=tmp_path / "out",
        freeze=freeze,
        list_names_fn=lambda url, auth=None: list(live),
        export_fn=_ok_export(calls),
        generate_fn=generate or _ok_generate(calls),
        validate_fn=_validate(fidelity, calls),
    )
    return report, calls


# span-metrics live surface (matches span-metrics-connector signature)
_SPAN_METRICS = ["calls_total", "duration_milliseconds_bucket", "up"]
_SEMCONV_HTTP = ["http_server_duration_count", "http_server_duration_bucket"]


# ─────────────────────────── manifest profile I/O ──────────────────────────


def test_read_manifest_profiles(tmp_path):
    m = _manifest(tmp_path, project_profile="semconv-http", target_profile="semconv-grpc")
    got = read_manifest_profiles(m)
    assert got["project"] == "semconv-http"
    assert got["targets"] == {"checkout": "semconv-grpc"}


def test_write_project_profile_preserves_other_fields(tmp_path):
    m = _manifest(tmp_path)
    dst = tmp_path / "copy.yaml"
    write_project_profile(m, dst, "span-metrics-connector")
    data = yaml.safe_load(dst.read_text())
    assert data["spec"]["observability"]["metricsProfile"] == "span-metrics-connector"
    assert data["project"]["id"] == "shop"  # untouched
    # Source is unchanged.
    assert read_manifest_profiles(m)["project"] is None


# ─────────────────────────── reconciliation paths ──────────────────────────


def test_detected_applied_non_mutating(tmp_path):
    m = _manifest(tmp_path)  # no profile authored
    report, calls = _run(m, tmp_path, live=_SPAN_METRICS)
    assert report.status == "pass"
    assert report.exit_code() == EXIT_PASS
    assert report.detection["detected_profile"] == "span-metrics-connector"
    assert report.reconciliation["action"] == "detected-applied"
    # The real manifest was NOT mutated.
    assert read_manifest_profiles(m)["project"] is None
    # Export ran against a throwaway sibling temp, now cleaned up.
    export_manifest = calls[0][1]
    assert export_manifest != m
    assert not export_manifest.exists()


def test_freeze_persists_into_manifest(tmp_path):
    m = _manifest(tmp_path)
    report, calls = _run(m, tmp_path, live=_SPAN_METRICS, freeze=True)
    assert report.reconciliation["action"] == "frozen"
    # The real manifest now carries the detected profile.
    assert read_manifest_profiles(m)["project"] == "span-metrics-connector"
    # Export ran against the real manifest.
    assert calls[0][1] == m


def test_authored_profile_wins_and_flags_mismatch(tmp_path):
    m = _manifest(tmp_path, project_profile="semconv-http")  # authored
    report, calls = _run(m, tmp_path, live=_SPAN_METRICS)  # live says span-metrics
    assert report.reconciliation["action"] == "authored"
    assert report.reconciliation["mismatch"] is True
    assert "note" in report.reconciliation
    # No temp copy — export ran against the real (authored) manifest.
    assert calls[0][1] == m
    assert read_manifest_profiles(m)["project"] == "semconv-http"


def test_authored_profile_no_mismatch_when_agreement(tmp_path):
    m = _manifest(tmp_path, project_profile="span-metrics-connector")
    report, _ = _run(m, tmp_path, live=_SPAN_METRICS)
    assert report.reconciliation["action"] == "authored"
    assert report.reconciliation["mismatch"] is False


def test_no_detection_uses_generator_default(tmp_path):
    m = _manifest(tmp_path)
    # metrics exist but no profile's full signature is present
    report, _ = _run(m, tmp_path, live=["calls_total", "up"])
    assert report.detection["detected_profile"] == ""
    assert report.reconciliation["action"] == "none"
    assert report.status == "pass"  # default may still resolve; fake says pass


# ─────────────────────── fidelity outcomes surfaced ────────────────────────


def test_fidelity_fail_surfaces_suggested_profile(tmp_path):
    m = _manifest(tmp_path)
    fidelity = _FakeFidelity(status="fail", suggested="span-metrics-connector")
    report, _ = _run(m, tmp_path, live=_SPAN_METRICS, fidelity=fidelity)
    assert report.status == "fail"
    assert report.exit_code() == EXIT_FAIL
    assert report.suggested_metrics_profile == "span-metrics-connector"
    assert report.fidelity["status"] == "fail"


# ───────────────────────────── fail-loud paths ─────────────────────────────


def test_unreachable_backend_is_unknown(tmp_path):
    m = _manifest(tmp_path)

    def _boom(url, auth=None):
        raise RuntimeError("connection refused")

    report = bind_and_verify(
        manifest_path=m,
        prometheus_url="http://localhost:9090",
        output_dir=tmp_path / "out",
        list_names_fn=_boom,
        export_fn=_ok_export([]),
        generate_fn=_ok_generate([]),
        validate_fn=_validate(_FakeFidelity(), []),
    )
    assert report.status == "unknown"
    assert report.exit_code() == EXIT_UNKNOWN
    assert report.detection["reachable"] is False


def test_zero_metrics_is_unknown(tmp_path):
    m = _manifest(tmp_path)
    report, _ = _run(m, tmp_path, live=[])
    assert report.status == "unknown"
    assert report.exit_code() == EXIT_UNKNOWN


def test_export_failure_is_unknown_and_cleans_temp(tmp_path):
    m = _manifest(tmp_path)

    def _bad_export(manifest_path, output_dir, export_cmd):
        return {"ok": False, "returncode": 1, "stderr_tail": "boom", "cmd": []}

    report = bind_and_verify(
        manifest_path=m,
        prometheus_url="http://localhost:9090",
        output_dir=tmp_path / "out",
        list_names_fn=lambda url, auth=None: list(_SPAN_METRICS),
        export_fn=_bad_export,
        generate_fn=_ok_generate([]),
        validate_fn=_validate(_FakeFidelity(), []),
    )
    assert report.status == "unknown"
    assert report.export["stderr_tail"] == "boom"
    # Temp sibling copy cleaned up even on the export-failure path.
    tmp = m.with_suffix(m.suffix + ".bindverify.tmp")
    assert not tmp.exists()


def test_generation_errors_is_unknown(tmp_path):
    m = _manifest(tmp_path)

    def _bad_generate(onboarding, artifacts_dir, manifest_path):
        return {"ok": False, "errors": ["checkout/alert_rule: kaboom"]}

    report, _ = _run(m, tmp_path, live=_SPAN_METRICS, generate=_bad_generate)
    assert report.status == "unknown"
    assert report.generation["errors"] == ["checkout/alert_rule: kaboom"]


def test_report_is_json_serializable(tmp_path):
    import json

    m = _manifest(tmp_path)
    report, _ = _run(m, tmp_path, live=_SPAN_METRICS)
    # to_dict round-trips through json cleanly.
    assert json.loads(json.dumps(report.to_dict()))["status"] == "pass"
