"""$0 post-hoc re-scoring of a completed benchmark run (NEXT_STEPS #2).

Builds a minimal fake run directory (cells.json + run-spec.json + sandboxes/ with a real
generated file + a seed pointing at it) and verifies rescore_run re-runs the current
scoring layer over the on-disk artifact, leaving non-ok cells alone.
"""
from __future__ import annotations

import json

import pytest

from startd8.benchmark_matrix import CellResult, rescore_run
from startd8.benchmark_matrix.runner import (
    STATUS_INFRA_FAIL,
    STATUS_OK,
    sandbox_dir_name,
)
from startd8.benchmark_matrix.scoring import COMPILE_FLOOR


SPEC_HASH = "abcdef012345abcdef012345"  # >=12 chars; cell_id uses [:12]


def _write_seed(seeds_dir, service, target_rel):
    """A minimal seed whose first task targets ``target_rel`` (matches runner schema)."""
    seed = {"tasks": [{"config": {"context": {"target_files": [target_rel]}}}]}
    (seeds_dir / f"seed-{service}.json").write_text(json.dumps(seed), encoding="utf-8")


def _cell(service, model, *, status=STATUS_OK, quality=1.0, structural=1.0,
          compile_ok=None, degraded=True, rep=0):
    return CellResult(
        cell_id=f"{SPEC_HASH[:12]}:{service}:{model}:r{rep}",
        service=service, model=model, language="nodejs", repetition=rep,
        status=status, quality=quality, structural_quality=structural,
        compile_ok=compile_ok, degraded=degraded, cost_usd=0.01,
    )


@pytest.fixture()
def fake_run(tmp_path):
    """A run dir mirroring run_ob_benchmark output: cells.json, run-spec.json, sandboxes/."""
    run_dir = tmp_path / "run"
    seeds_dir = tmp_path / "seeds"
    (run_dir / "sandboxes").mkdir(parents=True)
    seeds_dir.mkdir()

    target_rel = "src/currencyservice/server.js"
    _write_seed(seeds_dir, "currencyservice", target_rel)

    def _place_file(model, rep, contents):
        sb = run_dir / "sandboxes" / sandbox_dir_name("currencyservice", model, rep)
        f = sb / target_rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(contents, encoding="utf-8")

    return run_dir, seeds_dir, _place_file


def _write_cells(run_dir, cells):
    (run_dir / "cells.json").write_text(
        json.dumps([c.to_dict() for c in cells], indent=2), encoding="utf-8")
    (run_dir / "run-spec.json").write_text(
        json.dumps({"name": "test-round", "spec_hash": SPEC_HASH}), encoding="utf-8")


def test_rescore_lifts_degraded_js_to_compiled(fake_run):
    """A nodejs cell scored degraded (gate didn't run) flips to compile_ok=True once the
    fallback gate runs against the real .js on disk."""
    run_dir, seeds_dir, place = fake_run
    model = "anthropic:claude-opus-4-8"
    place(model, 0, "function charge(req) { return { id: 1 }; }\n")
    _write_cells(run_dir, [_cell("currencyservice", model, compile_ok=None, degraded=True)])

    rep = rescore_run(run_dir, seeds_dir, run_lint=False)

    assert rep.cells_rescored == 1
    cell = rep.cells[0]
    assert cell.compile_ok is True          # node --check fallback fired
    assert cell.degraded is False
    assert cell.quality == pytest.approx(1.0)
    assert rep.changes and rep.changes[0].changed


def test_rescore_floors_broken_js(fake_run):
    """Structurally-perfect but syntactically broken JS is floored by the compile gate."""
    run_dir, seeds_dir, place = fake_run
    model = "gemini:gemini-2.5-flash"
    place(model, 0, "const x = ;\nfunction (\n")  # SyntaxError
    _write_cells(run_dir, [_cell("currencyservice", model, quality=1.0, compile_ok=None, degraded=True)])

    rep = rescore_run(run_dir, seeds_dir, run_lint=False)

    cell = rep.cells[0]
    assert cell.compile_ok is False
    assert cell.quality == COMPILE_FLOOR


def test_rescore_leaves_infra_fail_untouched(fake_run):
    """Cells that produced no artifact (infra fail) are not re-scored."""
    run_dir, seeds_dir, _place = fake_run
    model = "openai:gpt-5.5"
    _write_cells(run_dir, [
        _cell("currencyservice", model, status=STATUS_INFRA_FAIL,
              quality=None, structural=None, compile_ok=None, degraded=False),
    ])

    rep = rescore_run(run_dir, seeds_dir, run_lint=False)

    assert rep.cells_rescored == 0
    assert rep.cells_not_ok == 1
    assert rep.cells[0].status == STATUS_INFRA_FAIL
    assert rep.cells[0].quality is None


def test_rescore_write_persists_and_backs_up(fake_run):
    """--write persists the three artifacts and keeps a single .bak of the originals."""
    run_dir, seeds_dir, place = fake_run
    model = "anthropic:claude-haiku-4-5-20251001"
    place(model, 0, "module.exports = { ok: true };\n")
    _write_cells(run_dir, [_cell("currencyservice", model, compile_ok=None, degraded=True)])
    original_cells = (run_dir / "cells.json").read_text(encoding="utf-8")

    rep = rescore_run(run_dir, seeds_dir, run_lint=False, write=True)

    assert rep.written
    # backup preserves the pre-rescore copy
    assert (run_dir / "cells.json.bak").read_text(encoding="utf-8") == original_cells
    # new files exist and reflect the re-score
    reloaded = json.loads((run_dir / "cells.json").read_text(encoding="utf-8"))
    assert reloaded[0]["compile_ok"] is True
    assert (run_dir / "aggregate.json").exists()
    assert "test-round" in (run_dir / "leaderboard.md").read_text(encoding="utf-8")

    # a second --write must NOT clobber the original .bak
    rescore_run(run_dir, seeds_dir, run_lint=False, write=True)
    assert (run_dir / "cells.json.bak").read_text(encoding="utf-8") == original_cells


def test_missing_artifact_counts_but_does_not_change(fake_run):
    """An ok cell whose generated file is absent is reported, not silently dropped."""
    run_dir, seeds_dir, _place = fake_run  # note: no file placed
    model = "anthropic:claude-sonnet-4-6"
    _write_cells(run_dir, [_cell("currencyservice", model, quality=1.0, compile_ok=None, degraded=True)])

    rep = rescore_run(run_dir, seeds_dir, run_lint=False)

    assert rep.cells_rescored == 0
    assert rep.cells_no_artifact == 1
    assert rep.cells[0].quality == pytest.approx(1.0)  # unchanged


def test_cellresult_from_dict_roundtrips():
    c = _cell("currencyservice", "anthropic:claude-opus-4-8")
    again = CellResult.from_dict(c.to_dict())   # drops computed tokens_per_sec
    assert again == c
