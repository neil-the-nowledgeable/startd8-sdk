"""Tier-A multi-phase judging — compile-gate trajectory over persisted DRAFT artifacts ($0).

Builds synthetic ``.artifacts`` dirs (a 1-draft and a 3-draft feature, with compiling and
non-compiling drafts) and asserts the derived metrics, the not-computed path, and idempotency.
Uses a Python service so ``score_file``'s ``py_compile`` gate actually runs (no toolchain mocking).
"""
from __future__ import annotations

import json

import pytest

from startd8.benchmark_matrix.phase_trajectory import (
    TRAJECTORY_FILE,
    build_phase_trajectory,
)
from startd8.benchmark_matrix.runner import CellResult, STATUS_OK, sandbox_dir_name

SPEC_HASH = "abcdef012345abcdef012345"  # >=12 chars; cell_id uses [:12]

GOOD_PY = "def handler(x):\n    return x + 1\n"
BAD_PY = "def handler(x):\n    return x +\n"  # syntax error → py_compile fails

# Artifact feature key: <Feature>__<lang>__…  (the 2nd __-token is the language)
PY_FEATURE = "EmailService__python____Online_Boutique_gRPC_service"

ARTIFACTS_SUBPATH = (".startd8", "benchmark-output", "generated", ".artifacts")


def _write_seed(seeds_dir, service, target_rel, language):
    seed = {
        "service_metadata": {"service": service, "language": language},
        "tasks": [{"config": {"context": {
            "language": language, "target_files": [target_rel]}}}],
    }
    (seeds_dir / f"seed-{service}.json").write_text(json.dumps(seed), encoding="utf-8")


def _cell(service, model, *, compile_ok=True, degraded=False, rep=0):
    return CellResult(
        cell_id=f"{SPEC_HASH[:12]}:{service}:{model}:r{rep}",
        service=service, model=model, language="python", repetition=rep,
        status=STATUS_OK, quality=1.0, structural_quality=1.0,
        compile_ok=compile_ok, degraded=degraded, cost_usd=0.01,
    )


def _artifacts_dir(run_dir, service, model, rep):
    sb = run_dir / "sandboxes" / sandbox_dir_name(service, model, rep)
    art = sb.joinpath(*ARTIFACTS_SUBPATH)
    art.mkdir(parents=True, exist_ok=True)
    return art


def _place_drafts(art_dir, feature_key, draft_contents):
    """draft_contents: list of (n, source) → writes ``<feature>-draft-<n>.md``."""
    for n, src in draft_contents:
        (art_dir / f"{feature_key}-draft-{n}.md").write_text(src, encoding="utf-8")


def _write_cells(run_dir, cells):
    (run_dir / "cells.json").write_text(
        json.dumps([c.to_dict() for c in cells], indent=2), encoding="utf-8")
    (run_dir / "run-spec.json").write_text(
        json.dumps({"name": "test-round", "spec_hash": SPEC_HASH}), encoding="utf-8")


@pytest.fixture()
def run_env(tmp_path):
    run_dir = tmp_path / "run"
    seeds_dir = tmp_path / "seeds"
    (run_dir / "sandboxes").mkdir(parents=True)
    seeds_dir.mkdir()
    _write_seed(seeds_dir, "emailservice", "src/emailservice/email_server.py", "python")
    return run_dir, seeds_dir


@pytest.mark.unit
def test_single_draft_first_draft_compiles(run_env):
    """A 1-draft compiling feature: first_draft_compiles=True, iters_to_first_compile=1,
    no convergence/monotonicity fields claimed (single draft)."""
    run_dir, seeds_dir = run_env
    art = _artifacts_dir(run_dir, "emailservice", "modelA", 0)
    _place_drafts(art, PY_FEATURE, [(1, GOOD_PY)])
    _write_cells(run_dir, [_cell("emailservice", "modelA")])

    out = build_phase_trajectory(run_dir, seeds_dir)
    cell = out["cells"][f"{SPEC_HASH[:12]}:emailservice:modelA:r0"]
    assert cell["status"] == "computed"
    feat = cell["features"][0]
    assert feat["feature"] == PY_FEATURE
    assert feat["first_draft_compiles"] is True
    assert feat["iterations_to_first_compile"] == 1
    assert feat["final_compiles"] is True
    # single draft → subsample-only metrics not asserted as a curve
    assert "compile_convergence" not in feat
    assert out["coverage"] == {"computed": 1, "total": 1, "not_computed": 0}


@pytest.mark.unit
def test_three_draft_convergence_and_monotonicity(run_env):
    """A 3-draft feature broken → broken → compiling:
    first_draft_compiles=False, iters_to_first_compile=3, convergence=True, monotonicity=1.0."""
    run_dir, seeds_dir = run_env
    art = _artifacts_dir(run_dir, "emailservice", "modelB", 0)
    _place_drafts(art, PY_FEATURE, [(1, BAD_PY), (2, BAD_PY), (3, GOOD_PY)])
    _write_cells(run_dir, [_cell("emailservice", "modelB")])

    out = build_phase_trajectory(run_dir, seeds_dir)
    feat = out["cells"][f"{SPEC_HASH[:12]}:emailservice:modelB:r0"]["features"][0]
    flags = [d["compiles"] for d in feat["drafts"]]
    assert flags == [False, False, True]
    assert feat["first_draft_compiles"] is False
    assert feat["iterations_to_first_compile"] == 3
    assert feat["compile_convergence"] is True
    # no compiling→broken regression anywhere → monotonicity 1.0
    assert feat["monotonicity"] == 1.0
    assert (out["cells"][f"{SPEC_HASH[:12]}:emailservice:modelB:r0"]["rollup"]["n_drafts_max"]
            == 3)


@pytest.mark.unit
def test_regression_lowers_monotonicity(run_env):
    """compiling → broken → compiling: one regression out of two steps → monotonicity 0.5,
    and first_draft_compiles=True with iters_to_first_compile=1."""
    run_dir, seeds_dir = run_env
    art = _artifacts_dir(run_dir, "emailservice", "modelC", 0)
    _place_drafts(art, PY_FEATURE, [(1, GOOD_PY), (2, BAD_PY), (3, GOOD_PY)])
    _write_cells(run_dir, [_cell("emailservice", "modelC")])

    out = build_phase_trajectory(run_dir, seeds_dir)
    feat = out["cells"][f"{SPEC_HASH[:12]}:emailservice:modelC:r0"]["features"][0]
    assert [d["compiles"] for d in feat["drafts"]] == [True, False, True]
    assert feat["first_draft_compiles"] is True
    assert feat["iterations_to_first_compile"] == 1
    assert feat["monotonicity"] == 0.5
    # went compiling, broke, recovered → still a broken→compiling transition exists
    assert feat["compile_convergence"] is True


@pytest.mark.unit
def test_not_computed_when_no_drafts(run_env):
    """A cell whose sandbox has no .artifacts (e.g. infra_fail) → status 'not computed', no raise."""
    run_dir, seeds_dir = run_env
    # cell exists in cells.json but we place NO draft artifacts for it
    _write_cells(run_dir, [_cell("emailservice", "ghostmodel")])

    out = build_phase_trajectory(run_dir, seeds_dir)
    cell = out["cells"][f"{SPEC_HASH[:12]}:emailservice:ghostmodel:r0"]
    assert cell["status"] == "not computed"
    assert cell["features"] == []
    assert out["coverage"] == {"computed": 0, "total": 1, "not_computed": 1}


@pytest.mark.unit
def test_idempotent(run_env):
    """Re-running the pass on an unchanged run yields a byte-identical result (determinism)."""
    run_dir, seeds_dir = run_env
    art = _artifacts_dir(run_dir, "emailservice", "modelB", 0)
    _place_drafts(art, PY_FEATURE, [(1, BAD_PY), (2, GOOD_PY)])
    _write_cells(run_dir, [_cell("emailservice", "modelB")])

    first = build_phase_trajectory(run_dir, seeds_dir)
    second = build_phase_trajectory(run_dir, seeds_dir)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


@pytest.mark.unit
def test_final_compiles_uses_stored_value_not_recompute(run_env):
    """final_compiles is read from the cell's STORED compile_ok, independent of draft results."""
    run_dir, seeds_dir = run_env
    art = _artifacts_dir(run_dir, "emailservice", "modelD", 0)
    # drafts all compile, but the stored final is False — final must reflect the STORED value
    _place_drafts(art, PY_FEATURE, [(1, GOOD_PY)])
    _write_cells(run_dir, [_cell("emailservice", "modelD", compile_ok=False, degraded=False)])

    out = build_phase_trajectory(run_dir, seeds_dir)
    feat = out["cells"][f"{SPEC_HASH[:12]}:emailservice:modelD:r0"]["features"][0]
    assert feat["first_draft_compiles"] is True
    assert feat["final_compiles"] is False
