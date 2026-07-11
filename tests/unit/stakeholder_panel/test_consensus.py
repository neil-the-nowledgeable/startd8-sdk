# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""#6 — the deterministic lexical consensus signal over R1 answers."""
from __future__ import annotations

import pytest

from startd8.stakeholder_panel import consensus as C

pytestmark = pytest.mark.unit


def _round(entries, round_id="R1"):
    return {"round_id": round_id, "entries": entries}


def _e(role_id, text):
    return {"role_id": role_id, "text": text}


# ── bucketing thresholds (named constants) ───────────────────────────────────
def test_bucket_thresholds():
    assert C._bucket(0.40) == "high"
    assert C._bucket(C._LEXICAL_HIGH) == "high"
    assert C._bucket(0.20) == "mixed"
    assert C._bucket(C._LEXICAL_MIXED) == "mixed"
    assert C._bucket(0.05) == "low"


# ── core scoring ─────────────────────────────────────────────────────────────
def test_identical_answers_high():
    rounds = [_round([_e("po", "ship the payment service quickly"),
                      _e("eu", "ship the payment service quickly")])]
    r = C.compute_consensus(rounds)
    assert r.label == "high" and r.score == pytest.approx(1.0) and r.n == 2
    assert r.basis == "lexical-r1"


def test_disjoint_vocab_low():
    rounds = [_round([_e("po", "budget timeline revenue margins"),
                      _e("eu", "latency caching database indexes")])]
    r = C.compute_consensus(rounds)
    assert r.label == "low" and r.score == pytest.approx(0.0)


def test_order_independent():
    a = [_e("po", "alpha beta gamma"), _e("eu", "beta gamma delta")]
    s1 = C.compute_consensus([_round(a)]).score
    s2 = C.compute_consensus([_round(list(reversed(a)))]).score
    assert s1 == pytest.approx(s2)


# ── FR-4 challenger exclusion ────────────────────────────────────────────────
def test_challengers_excluded_from_headline():
    # 2 aligned personas + 1 adversary who diverges by design → headline over the 2 non-challengers.
    rounds = [_round([
        _e("po", "ship the payment service quickly"),
        _e("eu", "ship the payment service quickly"),
        _e("adversary-exploit", "totally unrelated abuse vectors everywhere"),
    ])]
    r = C.compute_consensus(rounds, exclude_role_ids=frozenset({"adversary-exploit"}))
    assert r.n == 2 and r.label == "high"  # the adversary did not drag it down


# ── FR-8 edge cases ──────────────────────────────────────────────────────────
def test_single_persona_is_na():
    r = C.compute_consensus([_round([_e("po", "only one voice")])])
    assert r.label == "n/a" and r.score is None and r.n == 1


def test_no_r1_round_is_na():
    r = C.compute_consensus([_round([_e("po", "x"), _e("eu", "y")], round_id="R3")])
    assert r.label == "n/a" and r.n == 0


def test_empty_and_whitespace_safe():
    assert C.compute_consensus([]).label == "n/a"
    assert C.compute_consensus(None).label == "n/a"
    rounds = [_round([_e("po", "   "), _e("eu", "real content here now")])]
    assert C.compute_consensus(rounds).n == 1  # blank answer isn't rateable → only 1 left → n/a
    assert C.compute_consensus(rounds).label == "n/a"


# ── FR-9 method seam ─────────────────────────────────────────────────────────
def test_unknown_method_degrades_to_na():
    rounds = [_round([_e("po", "a b c"), _e("eu", "a b c")])]
    r = C.compute_consensus(rounds, method="embedding")  # not implemented yet → n/a, never raises
    assert r.label == "n/a" and r.basis == "embedding-r1"


# ── accepts typed objects too (not just dicts) ───────────────────────────────
def test_accepts_object_rounds():
    class _E:
        def __init__(self, role_id, text):
            self.role_id, self.text = role_id, text

    class _R:
        def __init__(self, entries):
            self.round_id, self.entries = "R1", entries

    rounds = [_R([_E("po", "same words here"), _E("eu", "same words here")])]
    assert C.compute_consensus(rounds).label == "high"


def test_to_dict_shape():
    d = C.compute_consensus([_round([_e("po", "same words here"), _e("eu", "same words here")])]).to_dict()
    assert set(d) == {"label", "score", "n", "basis"}
    assert d["label"] == "high" and isinstance(d["score"], float)
