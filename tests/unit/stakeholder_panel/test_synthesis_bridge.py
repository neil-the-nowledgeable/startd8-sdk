# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Increment 1 — the NON-DECIDABLE router (extract → classify → route). Deterministic, $0."""

from __future__ import annotations

from types import SimpleNamespace

from startd8.stakeholder_panel.synthesis_bridge import (
    Lane,
    build_triage,
    classify,
    extract_candidates,
    health_check,
)

# A realistic synthesis excerpt: a Risk Register table, Recommendations, Open Questions, Tensions.
SYNTHESIS = """\
# Kickoff Synthesis

## Risk Register

| Risk | Roles Flagging | Corroboration |
|---|---|---|
| **No immutable published-result entity** — results not reproducibly citable | se-manager, backend | cross-family |
| **Embargo is a mutable flag** — no audited transition on Run.embargoState | sre, security | cross-family |

## Tensions

- **T1 — Per-vendor pre-publication review vs. neutrality. OPEN.** Vendors demand veto over claims.
- **T2 — Who owns embargo enforcement. OPEN.** Service logic vs security authz vs SRE runtime.

## Recommendations

1. **Build the immutable PublishedResult snapshot** binding runId + specHash to cleared cells.
2. **Convert embargo into an audited state machine** with server-side transition-gating.
3. Set Run.name to the canonical round label for every published run.

## Open Questions for the Human

1. **Blinding decision:** is vendor-blind human review actually required, or process-based?
2. **Pre-registration:** does a locked, dated protocol already exist before scoring?
"""


def test_extract_pulls_items_from_known_sections():
    cands = extract_candidates(SYNTHESIS)
    sections = {c.source_section for c in cands}
    assert sections == {"Risk Register", "Tensions", "Recommendations", "Open Questions"}
    # 2 risks + 2 tensions + 3 recs + 2 open questions
    assert len(cands) == 9
    # table separator / header rows are not mistaken for risks
    assert all(c.title and "---" not in c.title for c in cands)


def test_extract_empty_is_empty():
    assert extract_candidates("") == []
    assert extract_candidates("# Heading only\n\nno known sections here") == []


def test_classify_all_non_decidable_without_allow_list():
    cands = classify(extract_candidates(SYNTHESIS))  # no allow-list → nothing is field-level
    assert all(c.lane is Lane.NON_DECIDABLE for c in cands)
    # open questions route to a human; build-recommendations route to requirements-build
    oq = [c for c in cands if c.source_section == "Open Questions"]
    assert oq and all(c.suggested_owner == "human" for c in oq)
    build = [c for c in cands if c.source_section == "Recommendations" and "Build" in c.raw_text]
    assert build and all(c.suggested_owner == "requirements-build" for c in build)
    # every item has a reason + owner (FR-5: nothing dropped without a disposition)
    assert all(c.reason and c.suggested_owner for c in cands)


def test_classify_field_level_when_value_path_allow_listed():
    cands = classify(extract_candidates(SYNTHESIS), allowed_value_paths={"Run.name"})
    field = [c for c in cands if c.lane is Lane.FIELD_LEVEL]
    assert len(field) == 1
    assert field[0].value_path == "Run.name"
    assert "VIPP" in field[0].suggested_owner
    # a non-allow-listed field mention (Run.embargoState) must NOT become field-level
    assert all(c.value_path != "Run.embargoState" for c in cands)


def test_health_check_flags_empty_and_default_context():
    assert any("empty" in w for w in health_check(
        synthesis_text="", context_summary="x", default_context="y"))
    assert any("default placeholder" in w for w in health_check(
        synthesis_text="stuff", context_summary="the placeholder", default_context="the placeholder"))
    assert health_check(synthesis_text="stuff", context_summary="real objective",
                        default_context="the placeholder") == []


def test_build_triage_end_to_end():
    transcript = SimpleNamespace(
        session_id="kp-test", objective="Publish the scored round credibly.",
        synthesis=SimpleNamespace(text=SYNTHESIS),
    )
    report = build_triage(transcript, allowed_value_paths={"Run.name"})
    c = report.counts()
    assert c["total"] == 9
    assert c["FIELD_LEVEL"] == 1 and c["NON_DECIDABLE"] == 8
    md = report.to_markdown()
    assert "Panel synthesis triage — kp-test" in md
    assert "FIELD-LEVEL candidates" in md and "NON-DECIDABLE" in md
    d = report.to_dict()
    assert d["kind"] == "panel-synthesis-triage" and len(d["candidates"]) == 9


def test_nothing_dropped_every_item_has_exactly_one_lane():
    report = build_triage(SimpleNamespace(
        session_id="s", objective="o", synthesis=SimpleNamespace(text=SYNTHESIS)))
    assert len(report.by_lane(Lane.FIELD_LEVEL)) + len(report.by_lane(Lane.NON_DECIDABLE)) == \
        len(report.candidates) == report.counts()["total"]
