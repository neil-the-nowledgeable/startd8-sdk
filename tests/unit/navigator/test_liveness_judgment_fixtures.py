"""REQ-25 FR-4 — the labeled fixture set that grounds the judgment-rung precision gate.

A judgment-rung's ``precision`` is not a hand-passed float — it is MEASURED by running a candidate judge
over this labeled fixture set. This proves (1) the fixture set is well-formed eval data, and (2) the
fixture → measured-precision → un-park path fires end-to-end: an accurate judge un-parks, a wolf-crier
(low precision) or a non-verify-live judge stays parked. No LLM — the judge is a controlled test double.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from startd8.navigator.govern import (
    PRECISION_THRESHOLD,
    is_unparked,
    load_judgment_fixtures,
    measure_precision,
    measured_judgment_rung,
    run_judgment_rung,
)
from startd8.navigator.models import Node

_FIXTURES = Path(__file__).parent / "fixtures" / "liveness_judgment_fixtures.json"
_CELLS = ("mitigation-inert", "non-goal-violated", "touches-dead")
_LIVE_GATE = "`startd8 navigator build --source pipeline --format json`"

FX = load_judgment_fixtures(_FIXTURES)


def _tagged_all():
    """Tag each fixture's input with its id so a controlled mock judge can key on it (test-only — the
    judge sees the case, not the label; production inputs stay untagged)."""
    return [dataclasses.replace(f, input={**f.input, "_id": f.id}) for f in FX]


def _judge(positive_ids):
    """A mock judge predicting the positive class for exactly ``positive_ids`` — lets a test dial in a
    known precision without a live LLM."""
    return lambda inp: inp.get("_id") in positive_ids


def _live_judge_node():
    return Node(key="judge", does="", verify_gate=_LIVE_GATE)


# ── the fixture set is well-formed eval data ────────────────────────────────────────────────────────

def test_fixture_set_covers_every_cell_with_both_labels():
    by_cell = {c: [f for f in FX if f.cell == c] for c in _CELLS}
    for cell, rows in by_cell.items():
        assert len(rows) >= 4, cell
        assert sum(f.label for f in rows) >= 2, f"{cell} needs ≥2 positives"
        assert sum(not f.label for f in rows) >= 2, f"{cell} needs ≥2 negatives"
    assert {f.cell for f in FX} == set(_CELLS)                       # no stray cells
    assert len({f.id for f in FX}) == len(FX)                        # ids unique


def test_every_fixture_carries_an_input_and_rationale():
    for f in FX:
        assert f.input and f.rationale, f.id                        # a case + why it's labeled that way


# ── measure_precision math (precision, not recall — NR-4) ───────────────────────────────────────────

def test_precision_is_one_for_a_perfect_judge():
    mi = [f for f in _tagged_all() if f.cell == "mitigation-inert"]
    pos = {f.id for f in mi if f.label}
    assert measure_precision(mi, _judge(pos)) == 1.0


def test_a_wolf_crier_scores_low_precision():
    mi = [f for f in _tagged_all() if f.cell == "mitigation-inert"]
    all_ids = {f.id for f in mi}
    # predicts positive for everything → FP on every negative → precision = positives / total
    p = measure_precision(mi, _judge(all_ids))
    assert p is not None and p < PRECISION_THRESHOLD


def test_no_positive_prediction_is_undefined_precision():
    mi = [f for f in _tagged_all() if f.cell == "mitigation-inert"]
    assert measure_precision(mi, _judge(set())) is None             # undefined → parked


def test_one_false_positive_drops_below_threshold():
    mi = [f for f in _tagged_all() if f.cell == "mitigation-inert"]
    pos = {f.id for f in mi if f.label}
    one_neg = next(f.id for f in mi if not f.label)
    p = measure_precision(mi, _judge(pos | {one_neg}))              # 4 TP / (4 TP + 1 FP) = 0.8
    assert p is not None and p < PRECISION_THRESHOLD                # the threshold bites


# ── the grounded un-park decision (measured precision AND verify-live judge) ────────────────────────

def test_accurate_verify_live_judge_unparks_every_cell():
    tagged = _tagged_all()
    for cell in _CELLS:
        pos = {f.id for f in tagged if f.cell == cell and f.label}
        rung = measured_judgment_rung(cell, tagged, _judge(pos), judge_node=_live_judge_node())
        assert rung.precision == 1.0
        assert is_unparked(rung) is True, cell


def test_accurate_judge_but_not_verify_live_stays_parked():
    """FR-6 — even a perfect-precision judge stays parked if the judge itself is not verify-live."""
    tagged = _tagged_all()
    pos = {f.id for f in tagged if f.cell == "mitigation-inert" and f.label}
    rung = measured_judgment_rung("mitigation-inert", tagged, _judge(pos), judge_node=None)
    assert rung.precision == 1.0 and rung.judge_verify_live is False
    assert is_unparked(rung) is False


def test_wolf_crier_stays_parked_even_when_verify_live():
    tagged = _tagged_all()
    all_ids = {f.id for f in tagged if f.cell == "non-goal-violated"}
    rung = measured_judgment_rung("non-goal-violated", tagged, _judge(all_ids), judge_node=_live_judge_node())
    assert is_unparked(rung) is False                               # NR-4: crying wolf never un-parks


# ── end-to-end — an un-parked rung emits candidates (never GAPs) ────────────────────────────────────

def test_unparked_rung_emits_candidates_not_gaps():
    tagged = _tagged_all()
    pos = {f.id for f in tagged if f.cell == "touches-dead" and f.label}
    rung = measured_judgment_rung("touches-dead", tagged, _judge(pos), judge_node=_live_judge_node())
    out = run_judgment_rung(rung, candidates=[{"key": "FR-3", "evidence": "the sort was dropped"}], doc="d")
    assert len(out) == 1 and out[0].severity == "advisory"          # candidate, never a fail/GAP
    assert out[0].ref == "candidate:touches-dead"
