"""Unit tests for the $0 REQ+ledger → det-handoff/0.1 projector (the second det-doc-kit projector).

Exercises the projector-standard's parts on a NEW doc-type: $0/no-LLM, solo-vs-gap gate (ledger
state, not a marker), maturity 0.1, dual-source (REQ + ledger), conformance + SARIF (imported),
provider round-trip, idempotency.
"""

from __future__ import annotations

import pytest

from startd8.handoff_codegen import (
    DetHandoffProjectorProvider,
    NotHandoffOwedError,
    findings_to_sarif,
    is_handoff_owed,
    project_handoff,
    render_handoff,
    validate_handoff,
)

pytestmark = pytest.mark.unit

REQ = """# Widget — Requirements

**Format:** det-req/0.1
**Pairs with:** *(plan deferred)*

> **Semantic name:** *SDK builds a widget and verifies it.*
> **Canonical ref:** `cc:intent:demo:requirement:req-42`

## Objectives

- **O-1:** the widget builds — target: `startd8 widget build` exits 0.
- **O-2:** the widget self-checks — target: the self-check passes.

## Functional requirements

- **FR-1 — Build the widget.** Name: The SDK builds a widget. Touches: `src/startd8/widget.py`. Verify: `startd8 widget build` exits 0. Serves: O-1
- **FR-2 — Verify the widget.** Name: The SDK verifies a widget. Touches: `src/startd8/nonexistent_xyz.py`. Verify: the widget passes its self-check. Serves: O-2
"""

LEDGER_DELIVERED = """# Session Ledger
| Artifact | What | State |
| **REQ-42 Widget** | FR-1..FR-2 | built, tests green (abc1234) |
"""
LEDGER_DELIVERED_OPEN = """# Session Ledger
| **REQ-42 Widget** | FR-1..FR-2 | built; follow-on: cross-repo mirror open |
"""


# ── solo-vs-gap gate (ledger state) ──────────────────────────────────────────────────────────────


def test_owed_when_no_ledger_and_has_frs():
    assert is_handoff_owed(REQ) is True


def test_not_owed_when_ledger_marks_delivered_no_followon():
    assert is_handoff_owed(REQ, ledger_text=LEDGER_DELIVERED) is False
    with pytest.raises(NotHandoffOwedError):
        project_handoff(REQ, ledger_text=LEDGER_DELIVERED)


def test_owed_when_delivered_but_open_followon():
    assert is_handoff_owed(REQ, ledger_text=LEDGER_DELIVERED_OPEN) is True


def test_not_owed_when_no_frs():
    assert is_handoff_owed("# Empty\n\n**Pairs with:** x\n") is False


# ── spine derivation (§2) ────────────────────────────────────────────────────────────────────────


def test_build_order_and_exit_criteria_from_frs():
    h = project_handoff(REQ, base_sha="abc1234")
    assert [s.fr for s in h.build_order] == ["FR-1", "FR-2"]
    assert h.build_order[0].verify == "`startd8 widget build` exits 0"


def test_hand_back_from_objectives():
    h = project_handoff(REQ, base_sha="abc1234")
    assert any("O-1" in hb for hb in h.hand_back)
    assert len(h.hand_back) == 2


def test_base_from_sha_param():
    h = project_handoff(REQ, base_sha="abc1234")
    assert h.base == "main @ abc1234"


def test_base_unresolved_without_sha():
    h = project_handoff(REQ)
    assert "unresolved" in h.base


# ── $0 / never-inferred ──────────────────────────────────────────────────────────────────────────


def test_projector_makes_no_network_call(monkeypatch):
    import socket

    monkeypatch.setattr(
        socket, "socket", lambda *a, **k: (_ for _ in ()).throw(AssertionError("net"))
    )
    assert project_handoff(REQ, base_sha="x").build_order


def test_gotchas_and_framing_are_human_residue_placeholders():
    h = project_handoff(REQ, base_sha="x")
    rendered = render_handoff(h)
    assert "human-residue" in h.gotchas_placeholder
    # The projector must NOT invent Gotcha content — only a placeholder.
    assert "human-residue" in rendered


# ── maturity (§4) ────────────────────────────────────────────────────────────────────────────────


def test_projected_handoff_is_maturity_0_1():
    h = project_handoff(REQ, base_sha="x")
    assert h.maturity == "0.1"
    assert "**maturity:** 0.1" in render_handoff(h)


# ── conformance + SARIF (§7) ─────────────────────────────────────────────────────────────────────


def test_phantom_prerequisite_is_surfaced():
    # FR-2 touches a nonexistent file → a phantom-prerequisite warning (not build-ready).
    h = project_handoff(REQ, req_path=None, base_sha="x")
    findings = validate_handoff(h, base_dir=None)
    checks = {f.check for f in findings}
    assert "phantom-prerequisite" in checks or all(
        not p.resolved for p in h.prerequisites
    )


def test_phantom_fr_is_a_conformance_error():
    h = project_handoff(REQ, base_sha="x")
    findings = validate_handoff(
        h, req_fr_ids={"FR-1"}, base_dir=None
    )  # FR-2 now phantom
    assert any(f.check == "phantom-fr" and f.severity == "error" for f in findings)


def test_sarif_imports_not_vendors():
    import startd8.handoff_codegen.conformance as conf

    assert (
        conf.render_sarif_from_findings.__module__
        == "startd8.coverage_map.findings_sarif"
    )
    h = project_handoff(REQ, base_sha="x")
    sarif = findings_to_sarif(validate_handoff(h, base_dir=None))
    assert sarif["version"] == "2.1.0"
    assert sarif["runs"][0]["tool"]["driver"]["name"] == "startd8-handoff-projector"


# ── provider round-trip (§6) + idempotency ───────────────────────────────────────────────────────


def test_provider_owns_and_in_sync(tmp_path):
    from startd8.contractors.deterministic_providers import ProviderContext

    req = tmp_path / "REQ-42.md"
    req.write_text(REQ, encoding="utf-8")
    h = project_handoff(req.read_text(), req_path=req, base_sha="abc1234")
    content = render_handoff(h)
    prov = DetHandoffProjectorProvider()
    ctx = ProviderContext(project_root=tmp_path, source_anchors=())
    from pathlib import Path

    assert prov.owns(Path("HANDOFF.md"), content) is True
    assert prov.owns(Path("HANDOFF.md"), "# hand-authored\n") is False
    # in_sync re-projects and reproduces the same base sha (extracted from the doc).
    assert prov.is_in_sync(tmp_path / "HANDOFF-42.md", content, ctx) is True
    assert prov.is_in_sync(tmp_path / "HANDOFF-42.md", content + "\nEDIT", ctx) is False


def test_idempotent_and_no_timestamp():
    import re

    a = render_handoff(project_handoff(REQ, base_sha="x"))
    b = render_handoff(project_handoff(REQ, base_sha="x"))
    assert a == b
    assert not re.search(r"\d{4}-\d{2}-\d{2}", a)
