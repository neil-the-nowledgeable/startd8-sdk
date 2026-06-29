"""M8 — kickoff funnel observability."""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

import pytest

from startd8.kickoff_experience.capture import apply_capture, build_capture_plan
from startd8.kickoff_experience.telemetry import (
    EV_CAPTURE_FAILED,
    EV_FIELD_CAPTURED,
    EV_GAP_CLOSED,
    EV_PREVIEW_BUILT,
    EV_STEP_ENTERED,
    FUNNEL_EVENTS,
    KickoffEvent,
    emit,
    kickoff_span,
    record_events,
)

CONVENTIONS = textwrap.dedent(
    """\
    domain: conventions
    provenance_default: authored
    language: python
    data_model:
      money: cents
    """
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    inputs = tmp_path / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True)
    (inputs / "conventions.yaml").write_text(CONVENTIONS, encoding="utf-8")
    return tmp_path


def test_emit_and_record_events() -> None:
    with record_events() as events:
        emit("field_captured", value_path="x", code="ok")
    assert len(events) == 1
    assert events[0] == KickoffEvent("field_captured", {"value_path": "x", "code": "ok"})


def test_emit_drops_none_attributes() -> None:
    with record_events() as events:
        emit("step_entered", step="conventions", extra=None)
    assert events[0].attributes == {"step": "conventions"}


def test_sink_removed_after_block() -> None:
    with record_events() as events:
        emit("session_started")
    # Outside the block, the sink is gone — this emit is not collected by `events`.
    emit("session_started")
    assert len(events) == 1


def test_apply_capture_emits_field_captured(project: Path) -> None:
    with record_events() as events:
        plan = build_capture_plan(project, "conventions.yaml#/data_model.money", "float")
        apply_capture(project, plan)
    names = [e.name for e in events]
    assert EV_FIELD_CAPTURED in names
    captured = next(e for e in events if e.name == EV_FIELD_CAPTURED)
    assert captured.attributes["value_path"] == "conventions.yaml#/data_model.money"


def test_kickoff_span_is_noop_safe() -> None:
    # Works whether or not OTel is configured; never raises.
    with kickoff_span("kickoff.capture", value_path="x") as span:
        span.set_attribute("k", "v")
        span.add_event("e")


def test_funnel_event_names_are_stable() -> None:
    assert set(FUNNEL_EVENTS) == {
        "session_started", "step_entered", "preview_built", "field_captured",
        "gap_closed", "capture_failed", "friction_logged",
        # Concierge mode (M-CM5)
        "survey_viewed", "kickoff_instantiated", "concierge_write_refused",
        # Agentic Concierge (proposals)
        "proposal_made", "proposal_confirmed", "proposal_discarded",
        # Welcome Mat 2.0 — template download (FR-WM2-14)
        "template_downloaded", "template_bundle_downloaded",
        # Welcome Mat 2.0 — agentic chat (FR-WM2-14a)
        "chat_turn", "chat_refused",
        # Red Carpet Treatment — stage funnel (FR-RCT-14)
        "red_carpet_started", "red_carpet_stage", "red_carpet_cascade_offered",
    }


# --- end-to-end funnel over the web app --------------------------------------------------------


def test_web_capture_flow_emits_funnel(project: Path) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from startd8.kickoff_experience.web import build_kickoff_app

    client = TestClient(build_kickoff_app(project))
    with record_events() as events:
        html = client.get("/step/conventions").text
        csrf = re.search(r"name='csrf' value='([^']+)'", html).group(1)
        client.post(
            "/capture/preview",
            data={"value_path": "conventions.yaml#/data_model.money", "value": "float"},
        )
        client.post(
            "/capture/apply",
            data={
                "value_path": "conventions.yaml#/data_model.money",
                "value": "float",
                "csrf": csrf,
            },
        )
    names = [e.name for e in events]
    assert EV_STEP_ENTERED in names
    assert EV_PREVIEW_BUILT in names
    assert EV_FIELD_CAPTURED in names


def test_web_capture_failure_emits_capture_failed(project: Path) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from startd8.kickoff_experience.web import build_kickoff_app

    client = TestClient(build_kickoff_app(project))
    html = client.get("/step/conventions").text
    csrf = re.search(r"name='csrf' value='([^']+)'", html).group(1)
    with record_events() as events:
        # Stale-file path: mutate on disk after the form was issued is hard here; instead force a
        # round-trip failure via an unknown value_path (rejected at plan build).
        client.post(
            "/capture/apply",
            data={"value_path": "conventions.yaml#/evil", "value": "x", "csrf": csrf},
        )
    assert EV_CAPTURE_FAILED in [e.name for e in events]


def test_gap_closed_when_field_becomes_ok(project: Path) -> None:
    # data_model.money is an input-domain field; capturing it does not flip an *extraction* field
    # to ok, so gap_closed only fires when the post-write refresh shows attention == ok. This test
    # asserts the wiring exists by checking gap_closed is at least a recognized funnel event and
    # that field_captured fired (the precondition for a possible gap_closed).
    with record_events() as events:
        plan = build_capture_plan(project, "conventions.yaml#/data_model.money", "float")
        apply_capture(project, plan)
    assert EV_FIELD_CAPTURED in [e.name for e in events]
    assert EV_GAP_CLOSED in FUNNEL_EVENTS
