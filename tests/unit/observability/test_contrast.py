# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Tests for the before/after contrast artifact.

The pipeline effects (export, generate, validate) are injected so these exercise the
governance-strip + two-variant orchestration + markdown rendering with no network,
subprocess, or real Prometheus.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from startd8.observability.contrast import (
    build_contrast,
    render_markdown,
    strip_governance,
)


def _manifest(tmp_path: Path) -> Path:
    data = {
        "project": {"id": "shop"},
        "spec": {
            "observability": {
                "metricsProfile": "span-metrics-connector",
                "datasources": {"prometheus": "webstore-metrics"},
                "traceSampling": 1.0,
            },
            "targets": [
                {"kind": "Deployment", "name": "checkout",
                 "metricsProfile": "semconv-grpc", "datasources": {"prometheus": "x"}},
            ],
        },
    }
    p = tmp_path / ".contextcore.yaml"
    p.write_text(yaml.safe_dump(data))
    return p


# ─────────────────────────── strip_governance ──────────────────────────────


def test_strip_governance_removes_bindings(tmp_path):
    src = _manifest(tmp_path)
    dst = tmp_path / "stripped.yaml"
    strip_governance(src, dst)
    d = yaml.safe_load(dst.read_text())
    obs = d["spec"]["observability"]
    assert "metricsProfile" not in obs and "datasources" not in obs
    assert obs["traceSampling"] == 1.0  # unrelated fields preserved
    t = d["spec"]["targets"][0]
    assert "metricsProfile" not in t and "datasources" not in t
    # source untouched
    assert yaml.safe_load(src.read_text())["spec"]["observability"]["metricsProfile"]


# ───────────────────── two-variant orchestration ───────────────────────────


class _FakeFidelity:
    def __init__(self, binding, data, status, verdicts):
        self._d = {
            "status": status, "binding_coverage": binding, "data_coverage": data,
            "queries_replayed": len(verdicts), "verdicts": verdicts,
        }

    def to_dict(self):
        return self._d


def _verdicts(verdict):
    return [
        {"service": "checkout", "signal": "error", "expr": f"q_{verdict}", "verdict": verdict},
        {"service": "checkout", "signal": "latency", "expr": f"l_{verdict}", "verdict": verdict},
    ]


def _build(tmp_path, ungoverned_fid, governed_fid):
    calls = []

    def _export(m, o, c):
        Path(o).mkdir(parents=True, exist_ok=True)
        (Path(o) / "onboarding-metadata.json").write_text("{}")
        calls.append(Path(m).name)
        return {"ok": True}

    def _generate(onb, art, m):
        return {"ok": True}

    # governed run is the 2nd variant → return governed on 2nd validate call
    seq = [ungoverned_fid, governed_fid]

    def _validate(**kw):
        return seq.pop(0)

    report = build_contrast(
        manifest_path=_manifest(tmp_path),
        prometheus_url="http://localhost:9090",
        output_dir=tmp_path / "out",
        export_fn=_export, generate_fn=_generate, validate_fn=_validate,
    )
    return report, calls


def test_contrast_orchestration_and_ordering(tmp_path):
    ung = _FakeFidelity(0.0, 0.0, "fail", _verdicts("fail"))
    gov = _FakeFidelity(1.0, 0.5, "pass", _verdicts("pass"))
    report, calls = _build(tmp_path, ung, gov)

    assert report.ungoverned.binding_coverage == 0.0
    assert report.governed.binding_coverage == 1.0
    # governed reads the real manifest; ungoverned reads the stripped temp copy
    assert calls[0].endswith(".ungoverned.tmp")
    assert calls[1] == ".contextcore.yaml"
    # datasource reflects each variant's manifest
    assert report.ungoverned.datasource.startswith("${datasource}")
    assert report.governed.datasource == "webstore-metrics"
    # temp stripped manifest cleaned up
    assert not (tmp_path / "out" / ".contextcore.yaml.ungoverned.tmp").exists()


def test_contrast_export_failure_is_unknown(tmp_path):
    def _export_fail(m, o, c):
        return {"ok": False}

    report = build_contrast(
        manifest_path=_manifest(tmp_path),
        prometheus_url="http://localhost:9090",
        output_dir=tmp_path / "out",
        export_fn=_export_fail,
        generate_fn=lambda *a: {"ok": True},
        validate_fn=lambda **k: _FakeFidelity(1, 1, "pass", []),
    )
    assert report.ungoverned.status == "unknown"
    assert report.governed.status == "unknown"


# ─────────────────────────────── rendering ─────────────────────────────────


def test_render_markdown_shows_before_after(tmp_path):
    ung = _FakeFidelity(0.0, 0.0, "fail", _verdicts("fail"))
    gov = _FakeFidelity(1.0, 0.5, "pass", _verdicts("pass"))
    report, _ = _build(tmp_path, ung, gov)
    md = render_markdown(report)

    assert "# Observability: ungoverned vs governed" in md
    assert "0%" in md and "100%" in md          # headline percentages
    assert "webstore-metrics" in md              # governed datasource
    assert "checkout/error" in md                # a query slot
    assert "q_fail" in md and "q_pass" in md     # before → after exprs
    assert "+100%" in md                          # the delta callout
