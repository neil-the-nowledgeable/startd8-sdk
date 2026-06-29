"""Red Carpet Treatment N2-inc2 — the two-step data-model ratification (R1-F4) + bootstrap-if-absent.

The `brief` proposal writes the requirements doc (no schema); a separate `schema` proposal then derives
+ promotes the contract FROM the confirmed on-disk brief. Two deliberate human gates.
"""

from __future__ import annotations

from pathlib import Path

from startd8.kickoff_experience.proposals import (
    _RC_BRIEF_PATH,
    PROPOSAL_KINDS,
    ProposalBuffer,
    ProposedAction,
    apply_proposal,
    make_propose_handler,
)
from startd8.kickoff_experience.red_carpet import build_red_carpet_state

_BRIEF = """## Entities

### Customer
A person.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| name | text | yes | |
"""


def test_brief_kind_in_allowlist() -> None:
    assert "brief" in PROPOSAL_KINDS


def test_two_step_brief_then_schema(tmp_path: Path) -> None:
    # Step 1: confirm the brief → writes the requirements doc, NO schema yet.
    b = apply_proposal(tmp_path, ProposedAction("brief", {"source": _BRIEF}, id="b1"))
    assert b.ok, b
    assert (tmp_path / _RC_BRIEF_PATH).is_file()
    assert not (tmp_path / "prisma" / "schema.prisma").exists()      # brief-confirm wrote no .prisma

    # Step 2: confirm `schema` with NO params brief → it reads the on-disk brief, derives + promotes.
    s = apply_proposal(tmp_path, ProposedAction("schema", {}, id="s1"))
    assert s.ok, s
    assert "model Customer" in (tmp_path / "prisma" / "schema.prisma").read_text()


def test_schema_without_a_brief_is_rejected(tmp_path: Path) -> None:
    # No params brief and no on-disk brief → cannot derive; points at the brief step.
    out = apply_proposal(tmp_path, ProposedAction("schema", {}, id="s1"))
    assert out.code == "missing_brief" and not out.ok
    assert _RC_BRIEF_PATH in out.detail


def test_brief_no_clobber_then_replace(tmp_path: Path) -> None:
    assert apply_proposal(tmp_path, ProposedAction("brief", {"source": _BRIEF}, id="b1")).ok
    (tmp_path / _RC_BRIEF_PATH).write_text("# hand-edited\n")
    blocked = apply_proposal(tmp_path, ProposedAction("brief", {"source": _BRIEF}, id="b2"))
    assert blocked.code == "would_clobber" and not blocked.ok
    assert (tmp_path / _RC_BRIEF_PATH).read_text() == "# hand-edited\n"
    ok = apply_proposal(tmp_path, ProposedAction("brief", {"source": _BRIEF, "replace": True}, id="b3"))
    assert ok.ok and "Entities" in (tmp_path / _RC_BRIEF_PATH).read_text()


def test_propose_handler_records_brief_and_optional_schema(tmp_path: Path) -> None:
    buf = ProposalBuffer()
    handler = make_propose_handler(tmp_path, buf)
    assert "recorded" in handler({"kind": "brief", "source": _BRIEF}).lower()
    # schema needs no brief param now (reads on-disk at apply) → recorded
    assert "recorded" in handler({"kind": "schema"}).lower()
    assert {a.kind for a in buf.pending()} == {"brief", "schema"}


def test_bootstrap_detail_when_package_absent(tmp_path: Path) -> None:
    vi = next(s for s in build_red_carpet_state(tmp_path).stages if s.key == "value_inputs")
    assert "instantiate" in vi.detail                                # scaffold-first guidance
    (tmp_path / "docs" / "kickoff" / "inputs").mkdir(parents=True)
    vi2 = next(s for s in build_red_carpet_state(tmp_path).stages if s.key == "value_inputs")
    assert "instantiate" not in vi2.detail                           # package present → normal detail
