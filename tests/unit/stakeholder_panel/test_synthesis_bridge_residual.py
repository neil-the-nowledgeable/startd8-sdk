# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""E — residual/unstructured capture + input_kind typing + the FR-5 coverage invariant.

Guards the CRP-hardened refinements (H-1..H-8, H-12): unknown-heading capture, normalization-aware +
bidirectional coverage (no drop AND no double-count), bold-lead titles, word-boundary kind heuristic,
the 10-kind taxonomy, and scrutiny additive-compat.
"""
from __future__ import annotations

from startd8.stakeholder_panel.synthesis_bridge import (
    Candidate,
    InputKind,
    Lane,
    TriageReport,
    classify,
    extract_candidates,
)
from startd8.stakeholder_panel.synthesis_bridge.extract import (
    _clean,
    _is_boilerplate,
    extract_residual,
    extract_structured,
)

# A realistic prototype synthesis (trimmed from the real household run) — the shape that used to yield
# "7 Open Questions only".
PROTOTYPE = """## Synthesis: household-o11y Early-Prototype UX Review

*All input below is synthetic, unratified panel material for human judgment.*

## Prioritized UX Improvements

**1. Verify the recurrence loop end-to-end.** The near-unanimous keystone.
**2. Per-item lead times.** A yearly gutter task warns weeks out.

## Quick Wins

- Prove the alert once on entry with a plain-language confirmation.
- Single-item cold start so a new user gets value fast.

## Bigger Bets

- One-tap chore completion that auto-advances the rotation.

## Tensions

**T1 — Frictionless logging vs medication accuracy — OPEN**
Member wants one-tap; care-recipient needs accuracy.

## Open Questions for the Human

1. Does the recurrence engine actually generate DueInstance rows today?
2. How is alerting delivered without external cloud push?

## Parking Lot

We should also consider a weekly digest email. Data must never leave the network.
"""

SCRUTINY = """## Synthesis

## Risk Register

| Risk | Roles | Corroboration |
| ---- | ---- | ---- |
| Demand may not exist | PO | cross-family |
| Payments integration slips | Eng | single |

## Recommendations

1. Build the checkout service first.

## Open Questions

1. Who owns the payment provider decision?
"""


def _covered_line_indices(text):
    """The non-boilerplate content line indices a reader would expect covered."""
    return {i for i, ln in enumerate(text.splitlines()) if not _is_boilerplate(ln)}


def _claimed_and_residual(text):
    structured, claimed = extract_structured(text)
    residual = extract_residual(text, claimed)
    return structured, claimed, residual


# ── FR-3 / H-1: unknown-heading capture ──────────────────────────────────────
def test_unknown_heading_lines_become_unstructured():
    cands = extract_candidates(PROTOTYPE)
    parking = [c for c in cands if c.source_section == "Parking Lot"]
    assert parking, "content under the unknown 'Parking Lot' heading must be captured"
    assert all(c.lane is Lane.UNSTRUCTURED for c in parking)


# ── the headline regression: prototype no longer collapses to 'Open Questions only' ──
def test_prototype_surfaces_all_sections_not_just_open_questions():
    cands = extract_candidates(PROTOTYPE)
    sections = {c.source_section for c in cands}
    for expected in ("UX Improvements", "Quick Wins", "Bigger Bets", "Tensions", "Open Questions"):
        assert expected in sections, f"{expected} was dropped (the old bug)"
    # and the bold-lead tension is captured (FR-2), not lost to the numbered/bullet-only filter
    assert any(c.source_section == "Tensions" and c.title.startswith("T1") for c in cands)


# ── H-6: bold-lead title not truncated at the em-dash ────────────────────────
def test_bold_lead_title_not_split_on_em_dash():
    cands = extract_candidates(PROTOTYPE)
    t1 = next(c for c in cands if c.title.startswith("T1"))
    assert "vs medication accuracy" in t1.title  # full bold span, not truncated at "—"


# ── FR-5 / H-2 / H-3: coverage invariant — bidirectional, normalization-aware ─
def test_coverage_no_drop_and_disjoint_prototype():
    structured, claimed, residual = _claimed_and_residual(PROTOTYPE)
    # normalization-aware coverage: every non-boilerplate line is claimed by structured OR emitted residual
    expected = _covered_line_indices(PROTOTYPE)
    residual_texts = {_clean(r.raw_text) for r in residual}
    lines = PROTOTYPE.splitlines()
    for i in expected:
        norm = _clean(lines[i])
        covered = (i in claimed) or (norm in residual_texts)
        assert covered, f"line {i} dropped: {lines[i]!r}"
    # disjointness: residual never re-emits a structurally-claimed line
    residual_idx = {i for i, ln in enumerate(lines)
                    if not _is_boilerplate(ln) and i not in claimed and _clean(ln) in residual_texts}
    assert claimed.isdisjoint(residual_idx)


def test_table_data_under_unknown_heading_is_preserved():
    # H-2/M-2 regression: a data-bearing table under an UNRECOGNIZED heading is not silently dropped —
    # the structured pass only tables under "Risk Register", so residual must preserve these rows.
    text = (
        "## Some Weird Heading\n\n"
        "| Feature | Notes |\n|---------|-------|\n"
        "| Real content that matters | important detail |\n"
    )
    cands = extract_candidates(text)
    joined = " ".join(c.raw_text for c in cands)
    assert "Real content that matters" in joined
    assert all(c.lane is Lane.UNSTRUCTURED for c in cands)


def test_coverage_scrutiny_risk_table_not_double_counted():
    structured, claimed, residual = _claimed_and_residual(SCRUTINY)
    # the two risk DATA rows are claimed once (structured); residual emits no table scaffolding
    risks = [c for c in structured if c.source_section == "Risk Register"]
    assert len(risks) == 2
    assert not any("|" in r.raw_text and r.lane is Lane.UNSTRUCTURED for r in residual)


# ── FR-4 / H-7: input_kind taxonomy + word-boundary heuristic ────────────────
def test_input_kind_from_section():
    cands = classify(extract_candidates(PROTOTYPE))
    by_section = {c.source_section: c.input_kind for c in cands}
    assert by_section["UX Improvements"] is InputKind.suggestion
    assert by_section["Tensions"] is InputKind.tension
    assert by_section["Open Questions"] is InputKind.question


def test_infer_kind_word_boundary_no_false_positive():
    from startd8.stakeholder_panel.synthesis_bridge.classify import _infer_kind
    # 'only' must NOT fire inside 'commonly'; 'limit' not inside 'unlimited'
    assert _infer_kind("this is commonly seen behavior in the field") is InputKind.content
    assert _infer_kind("we have unlimited scope for the prototype phase") is InputKind.content
    # real signals do fire
    assert _infer_kind("data must never leave the network") is InputKind.constraint
    assert _infer_kind("we decided to ship the MVP first") is InputKind.decision
    assert _infer_kind("you should consider a digest email") is InputKind.suggestion
    assert _infer_kind("is the recurrence engine wired up?") is InputKind.question


# ── H-12: counts() stays all-int; kind_counts() sibling ──────────────────────
def test_counts_all_int_and_kind_counts_sibling():
    report = TriageReport(session_id="s", candidates=classify(extract_candidates(PROTOTYPE)))
    counts = report.counts()
    assert all(isinstance(v, int) for v in counts.values())
    assert "UNSTRUCTURED" in counts
    assert sum(report.kind_counts().values()) == counts["total"]


# ── scrutiny stays additive-compatible (structured items unchanged) ──────────
def test_scrutiny_structured_items_unchanged():
    structured, _ = extract_structured(SCRUTINY)
    # 2 risks + 1 recommendation + 1 open question = 4 structured items (residual is additive on top)
    assert len(structured) == 4
    assert {c.source_section for c in structured} == {"Risk Register", "Recommendations", "Open Questions"}
