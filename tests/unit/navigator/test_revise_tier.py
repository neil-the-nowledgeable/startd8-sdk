"""REQ-21 — guarded `revises` auto-tier (byte-identity-gated, fail-safe, audited).

The load-bearing guarantees: auto requires ALL three properties affirmatively proven (FR-1); the byte-
identity is ENFORCED through the guard, not declared (FR-2, fail-closed); any uncertainty fails safe to
human (FR-5); and the default (no auto-eligible revise) equals REQ-20 — the consequential loop is untouched.
"""

from __future__ import annotations

from pathlib import Path

from startd8.navigator.models import Node
from startd8.navigator.revise_tier import (
    CONFIDENCE_FLOOR,
    TIER_AUTO,
    TIER_HUMAN,
    ReviseEligibility,
    auto_apply_revise,
    classify_revise_tier,
    eligibility_of,
    is_reversible,
    lesson_confidence,
)
from startd8.navigator.sources_retrospective import build_lesson_from_regression


def _lesson(confidence=0.95):
    from startd8.navigator.govern import Finding
    lesson = build_lesson_from_regression(Finding("FR-6", "fail", "d", "node 'FR-1' ... regression.", fr="FR-1"))
    import dataclasses
    return dataclasses.replace(lesson, confidence=confidence)


# ── FR-1 — the conjunction (auto iff ALL three) ────────────────────────────────────────────────────

def test_auto_requires_all_three_properties():
    ok = ReviseEligibility(byte_identical=True, reversible=True, lesson_confidence=0.95)
    assert classify_revise_tier(ok) == TIER_AUTO
    # failing ANY single property → human
    for bad in (
        ReviseEligibility(byte_identical=False, reversible=True, lesson_confidence=0.95),
        ReviseEligibility(byte_identical=True, reversible=False, lesson_confidence=0.95),
        ReviseEligibility(byte_identical=True, reversible=True, lesson_confidence=0.4),
    ):
        assert classify_revise_tier(bad) == TIER_HUMAN


# ── FR-5 — fail-safe: any UNRESOLVED (None) property → human ────────────────────────────────────────

def test_unresolved_property_defaults_to_human():
    for elig in (
        ReviseEligibility(byte_identical=None, reversible=True, lesson_confidence=0.95),
        ReviseEligibility(byte_identical=True, reversible=None, lesson_confidence=0.95),
        ReviseEligibility(byte_identical=True, reversible=True, lesson_confidence=None),
        ReviseEligibility(),                                    # everything unknown
    ):
        assert classify_revise_tier(elig) == TIER_HUMAN


# ── FR-3 — reversibility (no irreversible side effect) ─────────────────────────────────────────────

def test_reversibility_excludes_irreversible_effects():
    assert is_reversible([]) is True                            # pure git-tracked IR change
    assert is_reversible(["spend"]) is False
    assert is_reversible(["outward_publish"]) is False
    assert is_reversible(["external_ship"]) is False
    assert is_reversible(["regenerate_with_spend"]) is False
    assert is_reversible(["not_git_tracked"]) is False


# ── FR-4 — confidence floor ─────────────────────────────────────────────────────────────────────────

def test_below_floor_lesson_forces_human_even_if_byte_identical_and_reversible():
    elig = eligibility_of(_lesson(confidence=CONFIDENCE_FLOOR - 0.01), byte_identical=True, effects=[])
    assert classify_revise_tier(elig) == TIER_HUMAN            # below floor → human despite the rest
    at_floor = eligibility_of(_lesson(confidence=CONFIDENCE_FLOOR), byte_identical=True, effects=[])
    assert classify_revise_tier(at_floor) == TIER_AUTO         # at/above floor → auto


def test_lesson_confidence_absent_is_none():
    assert lesson_confidence(Node(key="lesson:x", does="", category="lesson")) is None


# ── FR-2 — enforce through the guard (fail-closed) ─────────────────────────────────────────────────

def test_auto_apply_requires_guard_to_prove_unchanged():
    lesson = _lesson(0.95)
    elig = eligibility_of(lesson, byte_identical=True, effects=[])
    # guard proves the product unchanged → auto-applies + audits
    audit = auto_apply_revise(lesson, elig, guard=lambda: True, timestamp="2026-08-16T00:00Z", revert_ref="abc123")
    assert audit is not None and audit.lesson == lesson.key and audit.target == "FR-1"
    assert audit.guard_result is True and audit.revert_ref == "abc123"

    # FR-2 fail-closed: a revise CLASSIFIED auto whose application changes the product (guard False) is
    # NOT applied — downgraded to human, never shipped.
    assert auto_apply_revise(lesson, elig, guard=lambda: False, timestamp="t", revert_ref="r") is None


def test_auto_apply_refuses_a_human_tier_revise():
    lesson = _lesson(0.4)                                       # below floor → human
    elig = eligibility_of(lesson, byte_identical=True, effects=[])
    # even with a passing guard, a human-tier revise never auto-applies
    assert auto_apply_revise(lesson, elig, guard=lambda: True, timestamp="t", revert_ref="r") is None


# ── FR-6 — audit trail completeness (govern) ───────────────────────────────────────────────────────

def test_fr6_audit_completeness_govern_flags_missing_revert_ref():
    from startd8.navigator.govern import check_auto_revise_audit
    from startd8.navigator.revise_tier import ReviseAudit

    good = ReviseAudit("lesson:FR-1", "FR-1", True, "2026-08-16T00:00Z", "abc123")
    assert check_auto_revise_audit([good]) == []
    incomplete = ReviseAudit("lesson:FR-1", "FR-1", True, "2026-08-16T00:00Z", "")  # no revert ref
    f = check_auto_revise_audit([incomplete])
    assert len(f) == 1 and f[0].check == "FR-6" and "revert_ref" in f[0].message


# ── FR-7 — amends REQ-20 NR-1 additively; default human; product-changing revises gated ────────────

def test_fr7_default_is_human_and_amendment_recorded():
    # with no proven eligibility, behaviour == REQ-20 (all revises propose → human)
    assert classify_revise_tier(ReviseEligibility()) == TIER_HUMAN
    # a product-CHANGING revise (guard would prove NOT byte-identical) is never auto-applied
    lesson = _lesson(0.95)
    elig = eligibility_of(lesson, byte_identical=True, effects=[])
    assert auto_apply_revise(lesson, elig, guard=lambda: False, timestamp="t", revert_ref="r") is None
    # REQ-20 NR-1 carries the recorded amendment pointer (the additive amendment, FR-7)
    req20 = (Path(__file__).parents[3] / "docs" / "design" / "requirements-visualization"
             / "REQ-20-lesson-node-and-revises-feedback-edge.md").read_text()
    assert "Amended by REQ-21" in req20
