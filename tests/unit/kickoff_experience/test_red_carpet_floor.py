"""Red Carpet Treatment — the apply-side allow-list + no-loop-write floor (FR-RCT-9 / CRP R1-F1/S1).

These codify the security invariant every future RCT proposal kind (`schema`/`manifest`) must ride:
`apply_proposal` rejects any kind outside the closed `PROPOSAL_KINDS` set before any write path, and
the agentic registry exposes only read-effect tools — the loop can *propose*, never *write*. This is
the security floor sequenced first in the RCT plan (step 0), built before N1/N2/N3.
"""

from __future__ import annotations

from pathlib import Path

from startd8.kickoff_experience.chat import build_kickoff_registry
from startd8.kickoff_experience.proposals import (
    PROPOSAL_KINDS,
    ProposedAction,
    apply_proposal,
)


def test_proposal_kinds_is_the_closed_allowlist() -> None:
    # The single source of truth shared by the propose handler and apply. RCT extends this only
    # alongside an explicit apply branch — `schema` (N2) and `manifest` (N1) have landed.
    assert PROPOSAL_KINDS == ("instantiate", "friction", "capture", "schema", "manifest")


def test_apply_rejects_kind_outside_allowlist_without_writing(tmp_path: Path) -> None:
    # Any kind outside the closed set must be rejected at apply with NO write — the floor.
    before = sorted(p.name for p in tmp_path.rglob("*"))
    out = apply_proposal(tmp_path, ProposedAction(kind="bogus_kind", params={"x": 1}, id="p1"))
    assert out.code == "unknown_kind" and out.ok is False
    assert sorted(p.name for p in tmp_path.rglob("*")) == before   # nothing written to disk


def test_agentic_registry_is_read_only_floor(tmp_path: Path) -> None:
    # The loop-never-writes floor: every tool is read-effect and the registry allows only read
    # effects, even with the propose tool registered.
    reg = build_kickoff_registry(tmp_path, proposal_sink=lambda _payload: "recorded")
    assert reg.allow_effect_classes == {"read"}
    specs = list(reg._tools.values())
    assert specs and all(s.effect_class == "read" for s in specs)
    names = set(reg._tools)
    assert "propose_action" in names                                  # propose present (read-effect)
    assert not (names & {"apply_proposal", "apply", "write", "capture", "instantiate"})  # no write tool


def test_pure_chat_registry_has_no_propose_tool(tmp_path: Path) -> None:
    # Without a proposal sink (pure read-only chat) there is not even a propose tool.
    reg = build_kickoff_registry(tmp_path)
    names = set(reg._tools)
    assert names == {"survey", "assess", "field_states"}
    assert reg.allow_effect_classes == {"read"}
