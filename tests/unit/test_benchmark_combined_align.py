"""M2 — method-alignment pre-step for the combined scoreboard (CS-15, CS-7, CS-16).

Alignment classifies each input run as already_current / aligned / excluded:* and, for an *aligned*
run (behind the target but holding re-scorable artifacts), re-scores it to the current scoring layer
**without mutating the source dir**. `rescore_run` is mocked for the aligned path (real re-scoring
needs real sandbox artifacts); the contract under test is the *decision* and its non-destructiveness.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from startd8.benchmark_matrix.combined_align import (
    ACTION_ALIGNED,
    ACTION_ALREADY_CURRENT,
    ACTION_EXCLUDED_CALIBRATION,
    ACTION_EXCLUDED_NO_SANDBOXES,
    AlignmentResult,
    align_runs,
)
from startd8.benchmark_matrix.runner import CellResult

# Stamped specs (post-CS-17): expose at sdk 0.4.0 = the canonical current method; a 0.3.0 expose run is
# the SAME method-class but BEHIND (version lag → alignable). A naive run is a different method-class.
_EXPOSE_CURRENT = {"repair_mode": "shadow", "expose_defects": True, "sdk_version": "0.4.0", "scoring_formula": "f"}
_EXPOSE_BEHIND = {"repair_mode": "shadow", "expose_defects": True, "sdk_version": "0.3.0", "scoring_formula": "f"}
_NAIVE = {"repair_mode": "apply", "expose_defects": False, "sdk_version": "0.4.0", "scoring_formula": "f"}

_SEEDS = "/tmp/seeds-unused"  # rescore is mocked; seeds_dir is never read in these tests


def _cell_dict(service, model, rep, status="ok", *, quality=0.95, defect_total=1):
    return {
        "cell_id": f"hash:{service}:{model}:r{rep}", "service": service, "model": model,
        "language": "go", "repetition": rep, "status": status, "quality": quality,
        "defect_total": defect_total,
    }


def _write(run_dir: Path, *, spec: dict | None, cells: list | None, sandboxes: bool = False) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    if spec is not None:
        (run_dir / "run-spec.json").write_text(json.dumps(spec), encoding="utf-8")
    if cells is not None:
        (run_dir / "cells.json").write_text(json.dumps(cells), encoding="utf-8")
    if sandboxes:
        sb = run_dir / "sandboxes" / "svc__model__r0"
        sb.mkdir(parents=True, exist_ok=True)
        (sb / "main.go").write_text("package main\n", encoding="utf-8")
    return run_dir


# --------------------------------------------------------------------------- 1. already at target
def test_already_current_used_as_is(tmp_path):
    anchor = _write(tmp_path / "round3", spec=_EXPOSE_CURRENT, cells=[_cell_dict("svc", "m", 0)])
    res = align_runs([anchor], _SEEDS)
    assert isinstance(res, AlignmentResult)
    [act] = res.actions
    assert act.action == ACTION_ALREADY_CURRENT
    [inp] = res.inputs
    assert inp.action == ACTION_ALREADY_CURRENT
    assert inp.cells is None            # used as-is → M3 reads from disk
    assert inp.is_rescored is False
    assert inp.run_dir == anchor


# --------------------------------------------------------------------------- 2. behind + sandboxes → aligned
def test_behind_with_sandboxes_is_aligned_and_rescored(tmp_path):
    anchor = _write(tmp_path / "round3", spec=_EXPOSE_CURRENT, cells=[_cell_dict("svc", "m", 0)])
    behind = _write(tmp_path / "round2", spec=_EXPOSE_BEHIND,
                    cells=[_cell_dict("svc", "m", 0, quality=0.50)], sandboxes=True)

    rescored_cells = [CellResult(cell_id="hash:svc:m:r0", service="svc", model="m",
                                 language="go", repetition=0, status="ok", quality=0.99)]

    class _FakeReport:
        cells = rescored_cells
        cells_rescored = 1

    with patch("startd8.benchmark_matrix.combined_align.rescore_run",
               return_value=_FakeReport()) as mock_rescore:
        res = align_runs([anchor, behind], _SEEDS)

    # rescore_run was invoked exactly once, on the behind run, with write disabled (non-destructive).
    assert mock_rescore.call_count == 1
    called_run_dir = mock_rescore.call_args.args[0]
    assert Path(called_run_dir) == behind
    assert mock_rescore.call_args.kwargs.get("write") is False

    behind_action = next(a for a in res.actions if a.run == "round2")
    assert behind_action.action == ACTION_ALIGNED
    assert behind_action.signature_after.parity_key == res.target.parity_key

    behind_input = next(i for i in res.inputs if i.run_dir == behind)
    assert behind_input.is_rescored is True
    assert behind_input.cells == rescored_cells       # the in-memory re-scored cells flow to M3
    assert behind_input.cells[0].quality == 0.99


# --------------------------------------------------------------------------- 3. behind + no sandboxes
def test_behind_without_sandboxes_excluded(tmp_path):
    anchor = _write(tmp_path / "round3", spec=_EXPOSE_CURRENT, cells=[_cell_dict("svc", "m", 0)])
    behind = _write(tmp_path / "round2", spec=_EXPOSE_BEHIND,
                    cells=[_cell_dict("svc", "m", 0)], sandboxes=False)

    with patch("startd8.benchmark_matrix.combined_align.rescore_run") as mock_rescore:
        res = align_runs([anchor, behind], _SEEDS)

    mock_rescore.assert_not_called()      # nothing on disk to re-score
    behind_action = next(a for a in res.actions if a.run == "round2")
    assert behind_action.action == ACTION_EXCLUDED_NO_SANDBOXES
    assert behind_action.included is False
    # excluded run contributes no input
    assert all(i.run_dir != behind for i in res.inputs)


# --------------------------------------------------------------------------- 4. naive → calibration, never aligned
def test_naive_run_excluded_as_calibration(tmp_path):
    anchor = _write(tmp_path / "round3", spec=_EXPOSE_CURRENT, cells=[_cell_dict("svc", "m", 0)])
    # naive run WITH sandboxes — to prove method-class, not artifact presence, drives the exclusion.
    naive = _write(tmp_path / "round1", spec=_NAIVE,
                   cells=[_cell_dict("svc", "m", 0, defect_total=None)], sandboxes=True)

    with patch("startd8.benchmark_matrix.combined_align.rescore_run") as mock_rescore:
        res = align_runs([anchor, naive], _SEEDS)

    mock_rescore.assert_not_called()      # never rescore a naive run into an expose run
    naive_action = next(a for a in res.actions if a.run == "round1")
    assert naive_action.action == ACTION_EXCLUDED_CALIBRATION
    assert "different method" in naive_action.reason
    assert all(i.run_dir != naive for i in res.inputs)


# --------------------------------------------------------------------------- 5. non-mutation of source dir
def test_alignment_does_not_mutate_source_dir(tmp_path):
    anchor = _write(tmp_path / "round3", spec=_EXPOSE_CURRENT, cells=[_cell_dict("svc", "m", 0)])
    behind = _write(tmp_path / "round2", spec=_EXPOSE_BEHIND,
                    cells=[_cell_dict("svc", "m", 0, quality=0.50)], sandboxes=True)
    cells_path = behind / "cells.json"
    before_bytes = cells_path.read_bytes()

    rescored = [CellResult(cell_id="hash:svc:m:r0", service="svc", model="m",
                           language="go", repetition=0, status="ok", quality=0.99)]

    class _FakeReport:
        cells = rescored
        cells_rescored = 1

    # The fake honors write=False by NOT touching disk — proving align_runs requests preview mode.
    with patch("startd8.benchmark_matrix.combined_align.rescore_run", return_value=_FakeReport()):
        align_runs([anchor, behind], _SEEDS)

    assert cells_path.read_bytes() == before_bytes          # source cells.json byte-identical
    assert not (behind / "cells.json.bak").exists()         # no backup written either


# --------------------------------------------------------------------------- 6. CS-16: malformed/empty dir
def test_tolerates_empty_dir_without_raising(tmp_path):
    anchor = _write(tmp_path / "round3", spec=_EXPOSE_CURRENT, cells=[_cell_dict("svc", "m", 0)])
    empty = tmp_path / "empty"            # no run-spec, no cells, no sandboxes
    empty.mkdir()
    res = align_runs([anchor, empty], _SEEDS)   # must not raise
    empty_action = next(a for a in res.actions if a.run == "empty")
    # an empty dir resolves to method 'unknown' (different class than expose) → excluded, not a crash.
    assert empty_action.action == ACTION_EXCLUDED_CALIBRATION
    assert empty_action.included is False


def test_empty_run_list_tolerated(tmp_path):
    res = align_runs([], _SEEDS)
    assert res.inputs == []
    assert res.actions == []
    assert any("no run dirs" in w for w in res.warnings)
