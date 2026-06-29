"""Red Carpet Treatment N2 — the `schema` proposal kind: derive + promote the data-model contract.

The `schema` kind is the second ratification gate (FR-RCT-4): it runs the existing $0
`generate contract` pipeline at human-confirm privilege and promotes `schema.prisma` ONLY when the
gate passes — never a lossy schema (R1-F12) and never a silent revision over a live contract
(FR-RCT-16, blocked unless `acknowledge_drift`).
"""

from __future__ import annotations

from pathlib import Path

from startd8.kickoff_experience.proposals import (
    ProposalBuffer,
    ProposedAction,
    apply_proposal,
    make_propose_handler,
)

_BRIEF_V1 = """## Entities

### Customer
A person who places orders.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| name | text | yes | |
| email | text | yes | |

### Order
A purchase made by a customer.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| total | number | yes | |

Relationships: an Order **belongs to** Customer.
"""

# v2 drops the Order entity → a semantic change vs a promoted v1 contract.
_BRIEF_V2 = """## Entities

### Customer
A person.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| name | text | yes | |
| email | text | yes | |
"""


def _schema_action(brief: str, **params) -> ProposedAction:
    return ProposedAction(kind="schema", params={"brief": brief, **params}, id="s1")


def test_schema_promotes_from_brief(tmp_path: Path) -> None:
    out = apply_proposal(tmp_path, _schema_action(_BRIEF_V1))
    assert out.ok, out
    contract = tmp_path / "prisma" / "schema.prisma"
    assert contract.is_file()
    text = contract.read_text()
    assert "model Customer" in text and "model Order" in text


def test_schema_missing_brief_rejected_without_write(tmp_path: Path) -> None:
    out = apply_proposal(tmp_path, _schema_action("   "))
    assert out.code == "missing_brief" and not out.ok
    assert not (tmp_path / "prisma" / "schema.prisma").exists()


def test_schema_revision_drift_blocked_then_acknowledged(tmp_path: Path) -> None:
    # Promote v1, then a v2 that drops Order must be BLOCKED as drift (FR-RCT-16) ...
    assert apply_proposal(tmp_path, _schema_action(_BRIEF_V1)).ok
    v1_text = (tmp_path / "prisma" / "schema.prisma").read_text()

    blocked = apply_proposal(tmp_path, _schema_action(_BRIEF_V2))
    assert blocked.code == "schema_drift" and not blocked.ok
    assert (tmp_path / "prisma" / "schema.prisma").read_text() == v1_text   # unchanged

    # ... and proceed only on an explicit acknowledge_drift re-confirm.
    ack = apply_proposal(tmp_path, _schema_action(_BRIEF_V2, acknowledge_drift=True))
    assert ack.ok, ack
    after = (tmp_path / "prisma" / "schema.prisma").read_text()
    assert "model Order" not in after            # v2 took effect
    assert (tmp_path / "prisma" / "_superseded-handauthored").exists() or after != v1_text


def test_schema_lossy_field_not_promoted(tmp_path: Path) -> None:
    # R1-F12: a brief declaring a field the contract can't express must NOT promote a degraded schema.
    lossy = _BRIEF_V1.replace("| total | number | yes | |", "| total | unsupported-type | yes | |")
    out = apply_proposal(tmp_path, _schema_action(lossy))
    assert out.code in ("schema_lossy", "schema_gate_failed") and not out.ok
    assert not (tmp_path / "prisma" / "schema.prisma").exists()


def test_propose_handler_records_schema(tmp_path: Path) -> None:
    buf = ProposalBuffer()
    handler = make_propose_handler(tmp_path, buf)
    ack = handler({"kind": "schema", "brief": _BRIEF_V1})
    assert "recorded" in ack.lower()
    assert len(buf.pending()) == 1 and buf.pending()[0].kind == "schema"
    # empty brief is rejected at propose time (no proposal recorded)
    err = handler({"kind": "schema", "brief": ""})
    assert err.startswith("error:") and len(buf.pending()) == 1
