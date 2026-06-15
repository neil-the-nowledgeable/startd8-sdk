"""Unit tests for benchmark_matrix.observability (P1) + benchmark.contextcore.yaml (P0)."""

import json
import re
from pathlib import Path

from startd8.benchmark_matrix.observability import (
    build_run_dashboard_spec,
    generate_run_dashboard,
)

_MANIFEST = (
    Path(__file__).resolve().parents[2]
    / "docs/design/deterministic-sre-onboarding/benchmark.contextcore.yaml"
)


def _write_run(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "run-spec.json").write_text(json.dumps(
        {"name": "summer-2026-round-1", "spec_hash": "49252392edaa02539f80d22b4d7e59c1"}))
    (run / "cells.json").write_text(json.dumps([
        {"cell_id": "h:cart:opus:r0", "service": "cart", "model": "opus", "status": "ok", "cost_usd": 0.1},
    ]))
    return run


# --- P1: spec shape (the spike gotchas) ---

def test_spec_uid_and_datasource_variable(tmp_path):
    spec = build_run_dashboard_spec(_write_run(tmp_path))
    # spike: UID must match cc-{pack}-{kebab-name}
    assert re.fullmatch(r"cc-benchmark-run-[a-f0-9]{12}", spec["uid"])
    assert spec["uid"] == "cc-benchmark-run-49252392edaa"
    # spike: a datasource variable is required (else templating validation fails)
    assert any(v["name"] == "datasource" for v in spec["variables"])


def test_spec_panels_carry_run_project(tmp_path):
    spec = build_run_dashboard_spec(_write_run(tmp_path))
    assert len(spec["panels"]) == 5
    exprs = " ".join(p["expr"] for p in spec["panels"])
    # execution pass/fail keyed by the run project_id (FR-18a)
    assert 'task_count_by_status{project_id="startd8-benchmark-run-49252392edaa"' in exprs
    # cost from the live startd8.cost.* metric (FR-3)
    assert "startd8_cost_total" in exprs
    groups = {p["group"] for p in spec["panels"]}
    assert groups == {"Execution", "Cost"}


def test_generate_compiles_or_degrades(tmp_path):
    """FR-16: with the jsonnet toolchain + mixin vendor present → compiled JSON; else spec YAML."""
    out = generate_run_dashboard(_write_run(tmp_path), tmp_path / "out")
    assert out["mode"] in {"compiled", "spec_only"}
    assert out["uid"] == "cc-benchmark-run-49252392edaa"
    if out["mode"] == "compiled":
        d = json.loads(Path(out["json_path"]).read_text())
        assert d["uid"] == "cc-benchmark-run-49252392edaa"
        assert d["schemaVersion"] >= 36
        assert d["templating"]["list"]  # datasource var present
    else:
        assert Path(out["spec_path"]).exists()


# --- P0: the manifest loads into a BusinessContext ---

def test_benchmark_manifest_loads():
    from startd8.observability.artifact_generator_context import load_business_context

    ctx = load_business_context(_MANIFEST, {})
    assert ctx.project_id == "startd8-benchmark"
    assert ctx.criticality == "high"
    assert ctx.prometheus_datasource == "prometheus"
    assert ctx.owners  # metadata.owners parsed


# --- P2: harness runbook from declared risks ---

def test_harness_runbook_from_manifest_risks(tmp_path):
    from startd8.benchmark_matrix.observability import build_harness_runbook, write_harness_runbook

    md = build_harness_runbook(_MANIFEST)
    assert "# Runbook:" in md
    # the manifest's real incident classes (= declared risks) appear
    assert "sandbox" in md.lower()        # FR-44
    assert "redact" in md.lower() or "leakage" in md.lower()  # FR-45
    assert "budget" in md.lower()         # cost overrun
    assert "## Escalation" in md and "platform-engineering" in md
    out = write_harness_runbook(_MANIFEST, tmp_path)
    assert Path(out["path"]).exists()
    assert out["incident_classes"] >= 5   # 5 declared risks


# --- P3: per-persona onboarding portal ---

def test_onboarding_portal_personas(tmp_path):
    from startd8.benchmark_matrix.onboarding import generate_onboarding_portal

    results = generate_onboarding_portal(_MANIFEST, tmp_path / "portal")
    assert len(results) == 4  # operator/engineer/manager/executive
    for r in results:
        assert r["mode"] in {"compiled", "spec_only"}
        assert r["uid"].startswith("cc-portal-startd8-benchmark")
        if r["mode"] == "compiled":
            d = json.loads(Path(r["json_path"]).read_text())
            assert d["templating"]["list"]  # datasource var → valid Grafana JSON
