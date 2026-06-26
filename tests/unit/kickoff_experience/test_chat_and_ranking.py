"""M5 — read-only tool floor enforcement + next-action ranking."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from startd8.kickoff_experience.chat import (
    KICKOFF_READ_ACTIONS,
    KickoffChatError,
    build_kickoff_registry,
    handle_kickoff_read,
)
from startd8.kickoff_experience.manifest import default_config
from startd8.kickoff_experience.ranking import (
    KIND_BLOCKER,
    KIND_DONE,
    KIND_FILL,
    KIND_REVIEW,
    next_action,
)
from startd8.kickoff_experience.readiness import ReadinessView
from startd8.kickoff_experience.state import (
    Ambiguity,
    Attention,
    FieldState,
    KickoffState,
    SourceInventory,
)
from startd8.manifest_extraction.models import Status


# --- enforcement: read-only floor (R1-S5) ------------------------------------------------------

WRITE_ACTIONS = ("instantiate-kickoff", "log-friction", "derive-contract")


def test_registry_exposes_exactly_three_read_tools() -> None:
    reg = build_kickoff_registry("/tmp/whatever")
    assert reg.names() == {"survey", "assess", "field_states"}
    assert reg.allow_effect_classes == {"read"}


@pytest.mark.parametrize("action", WRITE_ACTIONS)
def test_write_actions_refused_at_kickoff_floor(action: str) -> None:
    with pytest.raises(KickoffChatError):
        handle_kickoff_read(action, "/tmp/whatever")


def test_field_states_is_in_the_allow_list_not_a_bypass() -> None:
    assert "field_states" in KICKOFF_READ_ACTIONS
    # And it is registered as a read tool (so it routes through the same floor).
    reg = build_kickoff_registry("/tmp/whatever")
    assert reg._tools["field_states"].effect_class == "read"


def test_no_write_action_is_registered() -> None:
    reg = build_kickoff_registry("/tmp/whatever")
    for w in WRITE_ACTIONS:
        assert w not in reg.names()


# --- field_states tool payload over a real project ---------------------------------------------

REQ_DOC = textwrap.dedent(
    """\
    ## Entities

    ### Profile
    | Field | Type | Notes |
    |---|---|---|
    | name | text | |
    """
)


def test_field_states_payload_over_real_project(tmp_path: Path) -> None:
    kdir = tmp_path / "docs" / "kickoff"
    kdir.mkdir(parents=True)
    (kdir / "REQUIREMENTS.md").write_text(REQ_DOC, encoding="utf-8")
    payload = handle_kickoff_read("field_states", tmp_path)
    assert payload["action"] == "field_states"
    assert "state" in payload and "fields" in payload["state"]
    assert "next_action" in payload
    # Profile entity should have been extracted.
    paths = {f["value_path"] for f in payload["state"]["fields"]}
    assert any("Profile" in p for p in paths)


# --- next-action ranking (R2-S3) ---------------------------------------------------------------


def _state(*fields: FieldState) -> KickoffState:
    inv = SourceInventory((), (), (), {})
    return KickoffState(fields=tuple(fields), inventory=inv, grammar_version="x")


def _blocked(vp: str) -> FieldState:
    return FieldState("m", vp, Status.NOT_EXTRACTED, Attention.BLOCKED,
                      Ambiguity.UNRESOLVED_REFERENCE, reason="entity 'X' not declared")


def _defaulted(vp: str, value: str) -> FieldState:
    return FieldState("m", vp, Status.DEFAULTED, Attention.REVIEW, Ambiguity.NONE, value=value)


def _ok(vp: str) -> FieldState:
    return FieldState("m", vp, Status.EXTRACTED, Attention.OK, Ambiguity.NONE, value="v")


def test_ranking_prefers_readiness_blockers() -> None:
    rv = ReadinessView.from_assess(
        {"cascade": {"status": "ok", "blockers": [{"section": "Data model", "consequence": "no build"}]},
         "kickoff_inputs": {}}
    )
    action = next_action(_state(_blocked("/a")), rv)
    assert action.kind == KIND_BLOCKER
    assert "Data model" in action.title


def test_ranking_then_blocked_fields() -> None:
    action = next_action(_state(_ok("/a"), _blocked("/b")))
    assert action.kind == KIND_FILL
    assert action.value_path == "/b"


def test_ranking_then_defaulted_review() -> None:
    action = next_action(_state(_ok("/a"), _defaulted("/b", "guess")))
    assert action.kind == KIND_REVIEW
    assert action.value_path == "/b"


def test_ranking_done_when_clean() -> None:
    action = next_action(_state(_ok("/a"), _ok("/b")))
    assert action.kind == KIND_DONE


def test_ranking_is_deterministic_for_parity() -> None:
    # Same state -> same recommendation (the cross-surface parity property).
    s = _state(_blocked("/z"), _blocked("/a"), _ok("/m"))
    assert next_action(s).to_dict() == next_action(s).to_dict()
    # blocked_fields is identity-sorted, so /a wins over /z deterministically.
    assert next_action(s).value_path == "/a"


def test_default_config_unused_import_guard() -> None:
    # Sanity: the seeded config still imports/lints in this test module's environment.
    assert default_config().steps
