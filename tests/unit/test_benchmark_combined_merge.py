"""M1 — cross-run cell merge engine + supersedence resolver (CS-1/2/3/4/5/6/16).

Includes the **A3 adversarial supersedence cases** (plan §X, in lieu of full CRP): one per precedence
tier plus the hard ties — the one place a wrong answer is silent and publication-damaging.
"""
from __future__ import annotations

import json
from pathlib import Path

from startd8.benchmark_matrix import merge_runs


def _write(run_dir: Path, *, spec: dict | None = None, cells: list, cells_bak: list | None = None) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    if spec is not None:
        (run_dir / "run-spec.json").write_text(json.dumps(spec), encoding="utf-8")
    (run_dir / "cells.json").write_text(json.dumps(cells), encoding="utf-8")
    if cells_bak is not None:
        (run_dir / "cells.json.bak").write_text(json.dumps(cells_bak), encoding="utf-8")
    return run_dir


def _cell(service, model, rep, status="ok", *, defect_total=1, quality=0.97, cid=None):
    return {
        "cell_id": cid or f"hash:{service}:{model}:r{rep}", "service": service, "model": model,
        "language": "go", "repetition": rep, "status": status, "quality": quality,
        "defect_total": defect_total,
    }


# expose-stamped spec so the run is a current-method anchor
_EXPOSE = {"repair_mode": "shadow", "expose_defects": True, "sdk_version": "0.4.0", "scoring_formula": "f"}
_NAIVE = {"repair_mode": "apply", "expose_defects": False, "sdk_version": "0.4.0", "scoring_formula": "f"}


# --------------------------------------------------------------------------- A3 tier 1: status quality
def test_rerun_ok_beats_asrun_infra_fail(tmp_path):
    """The real case: a re-run's `ok` OpenAI cell supersedes the original run's `infra_fail`."""
    base = _write(tmp_path / "round3", spec=_EXPOSE,
                  cells=[_cell("checkout", "openai:gpt-5.5", 0, "infra_fail", defect_total=None)])
    rerun = _write(tmp_path / "rerun", spec=_EXPOSE,
                   cells=[_cell("checkout", "openai:gpt-5.5", 0, "ok")])
    # base is anchor (listed first); rerun supplies the fix
    res = merge_runs([base, rerun])
    key = ("checkout", "openai:gpt-5.5", 0)
    assert res.provenance[key].winner_run == "rerun"
    assert res.provenance[key].winner_status == "ok"
    assert "status ok > infra_fail" in res.provenance[key].reason
    assert [c.status for c in res.cells] == ["ok"]


# --------------------------------------------------------------------------- A3 tier 2: caller priority
def test_caller_priority_breaks_scored_tie(tmp_path):
    a = _write(tmp_path / "a", spec=_EXPOSE, cells=[_cell("svc", "m", 0, "ok", quality=0.9)])
    b = _write(tmp_path / "b", spec=_EXPOSE, cells=[_cell("svc", "m", 0, "ok", quality=0.5)])
    res = merge_runs([a, b])  # a listed first → a wins
    key = ("svc", "m", 0)
    assert res.provenance[key].winner_run == "a"
    assert "caller priority" in res.provenance[key].reason


def test_reclassified_depsmissing_wins_via_caller_order(tmp_path):
    """as-run `failed` vs fairness-reclassified `deps_missing` — both scoreless; the reclassified run,
    listed first, wins (CS-7 fairness expressed through priority order)."""
    rescored = _write(tmp_path / "rescored", spec=_EXPOSE,
                      cells=[_cell("svc", "m", 0, "deps_missing", defect_total=None)])
    asrun = _write(tmp_path / "asrun", spec=_EXPOSE,
                   cells=[_cell("svc", "m", 0, "failed", defect_total=None)])
    res = merge_runs([rescored, asrun])
    key = ("svc", "m", 0)
    assert res.provenance[key].winner_status == "deps_missing"
    assert res.provenance[key].winner_run == "rescored"


# --------------------------------------------------------------------------- A3 tier: absent in one input
def test_cell_absent_in_one_input_no_spurious_winner(tmp_path):
    a = _write(tmp_path / "a", spec=_EXPOSE, cells=[_cell("svc", "m", 0, "ok")])
    b = _write(tmp_path / "b", spec=_EXPOSE, cells=[_cell("other", "m", 0, "ok")])
    res = merge_runs([a, b])
    assert set(res.provenance) == {("svc", "m", 0), ("other", "m", 0)}
    assert res.provenance[("svc", "m", 0)].reason == "sole source"
    assert res.provenance[("other", "m", 0)].reason == "sole source"
    assert len(res.cells) == 2


# --------------------------------------------------------------------------- CS-5/6 method-parity gate
def test_naive_run_excluded_from_expose_merge(tmp_path):
    """A naive calibration board must NOT contribute cells to a shadow+expose ranking (CS-5/6)."""
    anchor = _write(tmp_path / "round3", spec=_EXPOSE, cells=[_cell("svc", "m", 0, "ok")])
    naive = _write(tmp_path / "round1", spec=_NAIVE,
                   cells=[_cell("svc", "m", 0, "ok", defect_total=None, quality=1.0)])
    res = merge_runs([anchor, naive])
    excluded = {r.run: r for r in res.excluded_runs}
    assert "round1" in excluded
    assert "method naive != anchor" in excluded["round1"].reason
    # the naive cell never entered the merge — the anchor's cell is the only source
    assert res.provenance[("svc", "m", 0)].winner_run == "round3"
    assert len(res.cells) == 1


def test_warns_when_anchor_is_naive(tmp_path):
    naive = _write(tmp_path / "round1", spec=_NAIVE,
                   cells=[_cell("svc", "m", 0, "ok", defect_total=None)])
    res = merge_runs([naive])
    assert any("scoring_method='naive'" in w for w in res.warnings)


# --------------------------------------------------------------------------- CS-16 tolerance
def test_tolerates_partial_dirs(tmp_path):
    good = _write(tmp_path / "good", spec=_EXPOSE, cells=[_cell("svc", "m", 0, "ok")])
    missing = tmp_path / "missing"        # no cells.json, no run-spec
    missing.mkdir()
    res = merge_runs([good, missing])     # must not raise
    assert len(res.cells) == 1
    # the empty dir resolves to 'unknown' signature ⇒ excluded, not a crash
    assert any(r.run == "missing" and not r.included for r in res.runs)


# --------------------------------------------------------------------------- no cell_id parsing (CS-4)
def test_merges_across_differing_spec_hash_prefixes(tmp_path):
    """Cross-run keys must ignore the per-run spec-hash prefix in cell_id (CS-4)."""
    a = _write(tmp_path / "a", spec=_EXPOSE,
               cells=[_cell("svc", "m", 0, "infra_fail", defect_total=None, cid="AAAA:svc:m:r0")])
    b = _write(tmp_path / "b", spec=_EXPOSE,
               cells=[_cell("svc", "m", 0, "ok", cid="BBBB:svc:m:r0")])
    res = merge_runs([a, b])
    # same logical key despite different cid prefixes ⇒ one merged cell, the `ok` one
    assert len(res.cells) == 1
    assert res.cells[0].status == "ok"
