"""Unit tests for the nearest-match decision core (Inc 3, FR-3, NFR-3).

These tests pin OQ-4: they encode the empirical reality that the run-011 field
inventions split into a typo/substring class (repairable) and a synonym class
(must abstain). See name_resolution.DEFAULT_CUTOFF for the finding.
"""

from __future__ import annotations

import pytest

from startd8.repair.name_resolution import (
    AMBIGUOUS_TIE,
    NO_CANDIDATES,
    best_match,
)

_CAP = ["id", "name", "category", "description", "proficiency", "notes"]
_DIFF = ["id", "name", "category", "description", "evidence", "notes"]
_METRIC = ["id", "name", "value", "unit", "direction", "timeframe", "description", "notes"]


# ── Rewrite cases: genuine typo / substring near-matches ────────────────────

@pytest.mark.parametrize(
    "invented,candidates,expected",
    [
        ("supportingEvidence", _DIFF, "evidence"),  # run-011, substring @0.538
        ("descriptio", _CAP, "description"),         # dropped char typo
        ("proficiencyy", _CAP, "proficiency"),       # doubled char typo
        ("Name", _CAP, "name"),                      # casing
    ],
)
def test_typo_class_rewrites(invented, candidates, expected):
    d = best_match(invented, candidates)
    assert d.is_rewrite, f"{invented} should rewrite, got {d}"
    assert d.target == expected


# ── Abstain cases: run-011 synonyms have no near-match ──────────────────────

@pytest.mark.parametrize(
    "invented,candidates",
    [
        ("title", _DIFF),       # synonym of name — top match scores ~0.40
        ("aiRefId", _CAP),      # invented dedup key — top ~0.44
        ("label", _CAP),        # synonym — top ~0.44
        ("outcomeId", _METRIC), # presumed FK, no relation — top ~0.43 (R4-S3)
    ],
)
def test_synonym_class_abstains_no_candidates(invented, candidates):
    d = best_match(invented, candidates)
    assert not d.is_rewrite
    assert d.reason == NO_CANDIDATES


def test_empty_candidates_abstains():
    d = best_match("anything", [])
    assert not d.is_rewrite
    assert d.reason == NO_CANDIDATES


def test_fk_case_abstains_without_structural_flag():
    """R4-S3: outcomeId is handled by no_candidates, no structural parameter."""
    d = best_match("outcomeId", _METRIC)
    assert d.reason == NO_CANDIDATES
    assert d.target is None


# ── Ambiguity / tie handling ────────────────────────────────────────────────

def test_ambiguous_tie_abstains():
    # Two equally-close candidates -> abstain, do not guess.
    d = best_match("naem", ["name", "nmae"])
    assert not d.is_rewrite
    assert d.reason == AMBIGUOUS_TIE


def test_clear_winner_over_runner_up_rewrites():
    # "descriptionn" is much closer to description than to anything else.
    d = best_match("descriptionn", _CAP)
    assert d.is_rewrite
    assert d.target == "description"


def test_single_candidate_above_cutoff_rewrites():
    d = best_match("descriptio", ["description"])
    assert d.is_rewrite
    assert d.target == "description"
    assert d.similarity > 0.9
