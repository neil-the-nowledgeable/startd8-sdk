"""Red Carpet Treatment — stage funnel (FR-RCT-14) + per-increment reflection (FR-RCT-12)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from startd8.kickoff_experience.proposals import ProposedAction, apply_proposal
from startd8.kickoff_experience.red_carpet import (
    build_red_carpet_state,
    record_red_carpet_progress,
    reflection_text,
)
from startd8.kickoff_experience.telemetry import (
    EV_RED_CARPET_CASCADE_OFFERED,
    EV_RED_CARPET_STAGE,
    FUNNEL_EVENTS,
    WM2_EVENT_ATTR_ALLOWLIST,
    record_events,
)

_BRIEF = """## Entities

### Customer
A person.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| name | text | yes | |
"""


def test_rct_events_registered() -> None:
    assert {"red_carpet_started", "red_carpet_stage", "red_carpet_cascade_offered"} <= set(FUNNEL_EVENTS)
    assert {"stage", "status"} <= WM2_EVENT_ATTR_ALLOWLIST   # bounded attrs allow-listed


def test_progress_emits_stage_transition_with_bounded_attrs(tmp_path: Path) -> None:
    empty = build_red_carpet_state(tmp_path)
    with record_events() as events:
        record_red_carpet_progress(None, empty)              # initial → emit the current gap
    stage_ev = [e for e in events if e.name == EV_RED_CARPET_STAGE]
    assert len(stage_ev) == 1
    attrs = stage_ev[0].attributes
    assert attrs["stage"] == "data_model" and attrs["status"] == "next"
    assert set(attrs) <= WM2_EVENT_ATTR_ALLOWLIST            # privacy: only allow-listed attrs

    # No transition (same next_stage) → no stage event.
    with record_events() as events2:
        record_red_carpet_progress(empty, empty)
    assert not [e for e in events2 if e.name == EV_RED_CARPET_STAGE]


def test_cascade_offered_emits_once_on_the_flip() -> None:
    # Build two synthetic states: not-offerable → offerable. The event fires only on the True flip.
    base = build_red_carpet_state("/tmp/does-not-matter")
    not_off = replace(base, cascade_offerable=False, next_stage="manifests")
    offerable = replace(base, cascade_offerable=True, next_stage=None, unmet_gates=())
    with record_events() as events:
        record_red_carpet_progress(not_off, offerable)
    assert len([e for e in events if e.name == EV_RED_CARPET_CASCADE_OFFERED]) == 1
    # already-offerable → no repeat
    with record_events() as events2:
        record_red_carpet_progress(offerable, offerable)
    assert not [e for e in events2 if e.name == EV_RED_CARPET_CASCADE_OFFERED]


def test_reflection_names_the_next_gap_and_friction_escape(tmp_path: Path) -> None:
    text = reflection_text(build_red_carpet_state(tmp_path))
    assert "next gap: data_model" in text
    assert "still blocking the build:" in text and "schema" in text
    assert "log friction" in text                            # the RETROSPECTIVE escape hatch


def test_reflection_after_schema_advances(tmp_path: Path) -> None:
    assert apply_proposal(tmp_path, ProposedAction("schema", {"brief": _BRIEF}, id="s1")).ok
    text = reflection_text(build_red_carpet_state(tmp_path))
    assert "decided so far: data_model" in text and "next gap: data_model" not in text
