"""M3 — combined (cross-run) scorecard renderer + the M2↔M3 alignment composition.

Renders one v2.0-format scorecard over a merged cell set, with a Provenance section and a calibration
annex; verifies determinism (CS-12), provenance-aware contamination (CS-10), and that align=True
composes the M2 step (a no-op on same-method inputs).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from startd8.benchmark_matrix import (
    build_combined_scorecard,
    build_combined_scorecard_html,
)

_NOW = datetime(2026, 6, 16, 18, 0, tzinfo=timezone.utc)
_EXPOSE = {"repair_mode": "shadow", "expose_defects": True, "sdk_version": "0.4.0", "scoring_formula": "f"}
_NAIVE = {"repair_mode": "apply", "expose_defects": False, "sdk_version": "0.4.0", "scoring_formula": "f"}


def _cell(service, model, rep, status="ok", *, defect_total=1, quality=0.97, cid=None):
    return {
        "cell_id": cid or f"hash:{service}:{model}:r{rep}", "service": service, "model": model,
        "language": "go", "repetition": rep, "status": status, "quality": quality,
        "defect_total": defect_total, "cost_usd": 0.1,
    }


def _run(run_dir: Path, *, spec, cells, contam=None) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run-spec.json").write_text(json.dumps(spec), encoding="utf-8")
    (run_dir / "cells.json").write_text(json.dumps(cells), encoding="utf-8")
    if contam is not None:
        (run_dir / "contamination-probe.json").write_text(json.dumps(contam), encoding="utf-8")
    return run_dir


def test_renders_all_sections(tmp_path):
    anchor = _run(tmp_path / "round3", spec=_EXPOSE,
                  cells=[_cell("svc", "gemini:gemini-2.5-pro", 0)])
    md = build_combined_scorecard([anchor], now=_NOW)
    assert "# Combined Scoreboard — Summer 2026 (consolidated)" in md
    assert "## Scoreboard — composite quality" in md
    assert "## Consistency" in md
    assert "## Provenance — canonical cell sources" in md
    assert "## Annex — methodology evolution" in md
    assert "method **shadow+expose**" in md   # stamped shadow+expose (inferred runs coarsen to 'expose')
    # reliability-lens headline (CS-9)
    assert "leads" in md and "reliability" in md


def test_deterministic_same_now(tmp_path):
    r = _run(tmp_path / "r", spec=_EXPOSE, cells=[_cell("svc", "m", 0)])
    assert build_combined_scorecard([r], now=_NOW) == build_combined_scorecard([r], now=_NOW)


def test_html_renders(tmp_path):
    r = _run(tmp_path / "r", spec=_EXPOSE, cells=[_cell("svc", "gemini:gemini-2.5-pro", 0)])
    html = build_combined_scorecard_html([r], now=_NOW)
    assert html.startswith("<!doctype html>")
    assert "Combined" in html and "Scoreboard" in html
    assert "Provenance" in html and "annex" in html.lower()


def test_naive_run_in_annex_not_ranking(tmp_path):
    anchor = _run(tmp_path / "round3", spec=_EXPOSE, cells=[_cell("svc", "m", 0, "ok")])
    naive = _run(tmp_path / "round1", spec=_NAIVE,
                 cells=[_cell("svc", "m", 0, "ok", defect_total=None, quality=1.0)])
    md = build_combined_scorecard([anchor, naive], now=_NOW)
    assert "`round1` — naive" in md          # listed in the annex
    # the naive 1.0 did not enter the ranking — only the anchor's 0.97 cell did
    assert "round1`: 1" not in md            # provenance shows no cells sourced from round1


def test_provenance_reflects_supersedence(tmp_path):
    base = _run(tmp_path / "round3", spec=_EXPOSE,
                cells=[_cell("checkout", "openai:gpt-5.5", 0, "infra_fail", defect_total=None)])
    rerun = _run(tmp_path / "rerun", spec=_EXPOSE,
                 cells=[_cell("checkout", "openai:gpt-5.5", 0, "ok")])
    md = build_combined_scorecard([base, rerun], now=_NOW)
    # the canonical openai cell came from the rerun, not the infra-failed base
    assert "`rerun`: 1" in md


def test_contamination_is_provenance_aware(tmp_path):
    # base wins svc/m1 (has contamination for it); rerun supersedes svc/m2 (no contamination probed)
    base = _run(tmp_path / "base", spec=_EXPOSE,
                cells=[_cell("svc", "m1", 0, "ok"), _cell("svc", "m2", 0, "infra_fail", defect_total=None)],
                contam={"reference_root": "/ref", "n_cells": 2, "n_scored": 2, "cells": [
                    {"service": "svc", "model": "m1", "language": "go", "codebleu": 0.3, "available": True},
                    {"service": "svc", "model": "m2", "language": "go", "codebleu": 0.4, "available": True},
                ]})
    rerun = _run(tmp_path / "rerun", spec=_EXPOSE, cells=[_cell("svc", "m2", 0, "ok")])
    md = build_combined_scorecard([base, rerun], now=_NOW)
    # m1 contamination shown (base won it); m2's base-probe is dropped (rerun, unprobed, supplied quality)
    cred = md.split("## Credibility")[1].split("##")[0]
    assert "`m1`" in cred
    assert "`m2`" not in cred


# --------------------------------------------------------------------------- M2↔M3 composition
def test_align_true_requires_seeds_dir(tmp_path):
    r = _run(tmp_path / "r", spec=_EXPOSE, cells=[_cell("svc", "m", 0)])
    with pytest.raises(ValueError, match="seeds_dir"):
        build_combined_scorecard([r], now=_NOW, align=True)


def test_align_noop_on_current_inputs_matches_direct(tmp_path):
    # all inputs already at target method ⇒ alignment is a no-op ⇒ identical output to align=False.
    anchor = _run(tmp_path / "round3", spec=_EXPOSE, cells=[_cell("svc", "m", 0, "ok")])
    other = _run(tmp_path / "round3b", spec=_EXPOSE, cells=[_cell("svc2", "m", 0, "ok")])
    seeds = tmp_path / "seeds"
    seeds.mkdir()
    direct = build_combined_scorecard([anchor, other], now=_NOW)
    aligned = build_combined_scorecard([anchor, other], now=_NOW, align=True, seeds_dir=seeds)
    assert direct == aligned
