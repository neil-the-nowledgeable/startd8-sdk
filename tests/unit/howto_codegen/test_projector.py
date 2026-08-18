"""Unit tests for the det-howto projector (STANDARD Part 1/Part 6, SCHEMA §2/§5/§7).

Built strictly from the STANDARD + SCHEMA — the golden-diff fixture is the real
``REQ-08-nl-programming-pipeline-provenance.md`` (it carries a `## Contract projection` table).
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from startd8.contractors.deterministic_providers import ProviderContext
from startd8.howto_codegen import (
    DetHowtoProjectorProvider,
    NotHowtoOwedError,
    Howto,
    findings_to_sarif,
    project_howto,
    render_howto,
    validate_howto,
)
from startd8.howto_codegen.render import GENERATED_MARKER

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
REQ_08 = (
    REPO_ROOT
    / "docs/design/requirements-visualization/REQ-08-nl-programming-pipeline-provenance.md"
)


# A minimal REQ WITH a command surface (a `## Contract projection` command row).
_REQ_WITH_COMMANDS = """# Widget Exporter — Requirements

**Version:** 0.2.0
**Format:** det-req/0.1

> **Semantic name:** *Widget exporter emits a CSV of widgets for an operator to download.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-99`

## Functional requirements

- **FR-1 — Export command.** Add `startd8 widget export --out <p>` writing a CSV. Touches: src/startd8/widget/export.py. Verify: `startd8 widget export` exits 0. Serves: O-1

## Contract projection

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| widget-export | command | structure | new: `startd8 widget export --out <p>` |
| out-flag | option | structure | `--out <p>` target path |
"""

# A solo-by-design REQ — NO command surface (no Contract-projection command rows, no CLI-declaring FR).
_REQ_SOLO = """# Internal Refactor — Requirements

**Version:** 0.1.0
**Format:** det-req/0.1

> **Semantic name:** *Internal refactor consolidates a helper with no operator surface.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-98`

## Functional requirements

- **FR-1 — Consolidate helper.** Merge two helpers into one. Touches: src/startd8/x/helper.py. Verify: the module imports. Serves: O-1

## Contract projection

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| WidgetModel | entity | structure | a data model, not a command |
"""


def test_solo_req_owes_no_howto_raises():
    """STANDARD 6a / SCHEMA §5 — a REQ with no command surface raises NotHowtoOwedError."""
    with pytest.raises(NotHowtoOwedError):
        project_howto(_REQ_SOLO)


def test_req_with_commands_is_owed():
    """A REQ declaring a command surface projects a Howto (the gate fires narrowly)."""
    h = project_howto(_REQ_WITH_COMMANDS)
    assert isinstance(h, Howto)
    assert len(h.commands) >= 1


def test_command_derivation_from_contract_projection():
    """SCHEMA §2 — commands derive from `## Contract projection` command/option rows."""
    h = project_howto(_REQ_WITH_COMMANDS)
    names = {(c.name, c.kind) for c in h.commands}
    assert ("widget-export", "command") in names
    assert ("out-flag", "option") in names
    # Every command traces to an authored source (never invented) — STANDARD I-1.
    assert all(c.source for c in h.commands)


def test_cli_declaring_fr_placeholder_span_is_filtered():
    """SCHEMA §0.1 (pinned by the det-howto independent-replication finding) — a `startd8 …` span
    containing a placeholder (`<p>`, `…`, …) is PROSE, not a runnable command, so it is NOT emitted.
    The fixture's only FR span is `startd8 widget export --out <p>` (has `<p>`) → filtered; the clean
    `widget-export` command still comes from the Contract-projection table row."""
    h = project_howto(_REQ_WITH_COMMANDS)
    assert not any("<p>" in c.name or "…" in c.name for c in h.commands)
    assert any(
        c.name == "widget-export" for c in h.commands
    )  # the clean contract-projection row


def test_clean_cli_declaring_fr_contributes_a_command():
    """A placeholder-free `startd8 …` span in an FR DOES contribute a command (the positive case)."""
    req = _REQ_WITH_COMMANDS.replace(
        "Add `startd8 widget export --out <p>` writing a CSV.",
        "Add `startd8 widget doctor` running a self-check.",
    )
    h = project_howto(req)
    assert any(c.name == "startd8 widget doctor" for c in h.commands)


def test_zero_cost_no_network(monkeypatch):
    """STANDARD Part 1 — the projector is pure: no network. Monkeypatch socket to prove it."""

    def _boom(*args, **kwargs):
        raise AssertionError("projector must not open a socket ($0, no network)")

    monkeypatch.setattr(socket, "socket", _boom)
    h = project_howto(_REQ_WITH_COMMANDS)
    render_howto(h)  # render is pure too
    validate_howto(h)


def test_maturity_is_initial_0_1():
    """STANDARD 6b / SCHEMA §4 — a projected howto starts at 0.1 (anti-inflation)."""
    h = project_howto(_REQ_WITH_COMMANDS)
    assert h.maturity == "0.1"


def test_didl_naming_present():
    """STANDARD 6c — DIDL name/handle/ref via name_forms(kind='howto')."""
    h = project_howto(_REQ_WITH_COMMANDS)
    assert h.name
    assert h.handle.startswith("howto/")
    assert h.ref == "cc:intent:requirements-visualization:howto:req-99"


def test_phantom_prerequisite_flagged(tmp_path):
    """SCHEMA §2/§3 — a Touches ref absent on disk resolves PHANTOM and is a conformance finding."""
    req = tmp_path / "REQ-phantom.md"
    req.write_text(
        "# Phantom — Requirements\n\n**Version:** 0.1.0\n\n"
        "> **Canonical ref:** `cc:intent:x:feature:req-1`\n\n"
        "## Functional requirements\n\n"
        "- **FR-1 — Cmd.** Add `startd8 x go`. Touches: src/does/not/exist.py. Verify: ok. Serves: O-1\n",
        encoding="utf-8",
    )
    # No src/startd8 above tmp_path → repo_root is None → LEGACY, not a false LIVE. Put a fake tree.
    (tmp_path / "src" / "startd8").mkdir(parents=True)
    h = project_howto(req.read_text(), req_path=req)
    phantoms = [p for p in h.prerequisites if p.liveness == "PHANTOM"]
    assert phantoms, "an absent Touches ref must resolve PHANTOM"
    findings = validate_howto(h)
    assert any(f.check == "phantom-prerequisite" for f in findings)


def test_live_prerequisite_resolves(tmp_path):
    """SCHEMA §2 — a Touches ref present on disk resolves LIVE."""
    (tmp_path / "src" / "startd8").mkdir(parents=True)
    real = tmp_path / "src" / "startd8" / "real.py"
    real.write_text("x = 1\n", encoding="utf-8")
    req = tmp_path / "REQ-live.md"
    req.write_text(
        "# Live — Requirements\n\n**Version:** 0.1.0\n\n"
        "> **Canonical ref:** `cc:intent:x:feature:req-2`\n\n"
        "## Functional requirements\n\n"
        "- **FR-1 — Cmd.** Add `startd8 y go`. Touches: src/startd8/real.py. Verify: ok. Serves: O-1\n",
        encoding="utf-8",
    )
    h = project_howto(req.read_text(), req_path=req)
    assert any(
        p.liveness == "LIVE" and p.ref.endswith("real.py") for p in h.prerequisites
    )


def test_sarif_imports_not_vendors():
    """STANDARD Part 3 — findings_to_sarif uses the ONE coverage_map renderer (imported)."""
    import startd8.howto_codegen.conformance as conf

    # The symbol is imported from coverage_map, not re-defined locally.
    from startd8.coverage_map.findings_sarif import render_sarif_from_findings

    assert conf.render_sarif_from_findings is render_sarif_from_findings

    h = project_howto(_REQ_WITH_COMMANDS)
    findings = validate_howto(h)
    sarif = findings_to_sarif(findings)
    assert sarif["version"] == "2.1.0"
    assert sarif["runs"][0]["tool"]["driver"]["name"] == "det-howto-projector"


def test_render_has_no_timestamp():
    """STANDARD Part 2 — the render carries no timestamp (byte-identity depends on it)."""
    import re

    h = project_howto(_REQ_WITH_COMMANDS)
    text = render_howto(h)
    assert GENERATED_MARKER in text
    # No ISO date / time patterns.
    assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", text)
    assert not re.search(r"\b\d{4}-\d{2}-\d{2}\b", text.replace("det-howto/0.1", ""))


def test_render_is_idempotent():
    """STANDARD Part 2 — same model → same bytes."""
    h = project_howto(_REQ_WITH_COMMANDS)
    assert render_howto(h) == render_howto(h)
    # Re-projecting the same source is also stable.
    h2 = project_howto(_REQ_WITH_COMMANDS)
    assert render_howto(h) == render_howto(h2)


def test_provider_owns_and_in_sync_roundtrip(tmp_path):
    """STANDARD Part 4 — owns() = marker; is_in_sync() = re-project from pairsWith + compare bytes."""
    (tmp_path / "src" / "startd8").mkdir(parents=True)
    req = tmp_path / "REQ-rt.md"
    req.write_text(_REQ_WITH_COMMANDS, encoding="utf-8")

    h = project_howto(req.read_text(), req_path=req)
    rendered = render_howto(h)

    provider = DetHowtoProjectorProvider()
    doc_path = tmp_path / "HOWTO_widget.md"
    doc_path.write_text(rendered, encoding="utf-8")

    ctx = ProviderContext(project_root=tmp_path)
    assert provider.owns(doc_path, rendered) is True
    assert provider.is_in_sync(doc_path, rendered, ctx) is True

    # A doc without the marker is not owned.
    assert provider.owns(doc_path, "no marker here") is False

    # Drift: mutate the on-disk doc → not in-sync.
    drifted = rendered.replace("Command reference", "Tampered heading")
    assert provider.is_in_sync(doc_path, drifted, ctx) is False


def test_provider_not_in_sync_when_source_absent(tmp_path):
    """STANDARD Part 4 / §3 — a phantom pairsWith source → not in-sync (silent-False logged)."""
    provider = DetHowtoProjectorProvider()
    rendered = (
        f"{GENERATED_MARKER}\n\n# HOWTO — x\n\n"
        "**pairsWith:** `nonexistent/REQ.md` (LIVE)\n"
    )
    ctx = ProviderContext(project_root=tmp_path)
    assert provider.is_in_sync(tmp_path / "HOWTO_x.md", rendered, ctx) is False


def test_golden_diff_req08():
    """Golden-diff eyeball against the real REQ-08 (has a `## Contract projection` table)."""
    h = project_howto(REQ_08.read_text(), req_path=REQ_08)
    # Contract-projection rows: navigator-build/verify (commands) + source-pipeline/run-oracle (options)
    kinds = {(c.name, c.kind) for c in h.commands}
    assert ("navigator-build", "command") in kinds
    assert ("source-pipeline", "option") in kinds
    assert ("run-oracle", "option") in kinds
    # Prerequisites resolved against the live repo tree — navigator sources exist (LIVE).
    live = [p for p in h.prerequisites if p.liveness == "LIVE"]
    assert any("sources_pipeline.py" in p.ref for p in live)
    # Conformance: no error findings on the real REQ (a PHANTOM warning is honest, not fatal).
    findings = validate_howto(h)
    assert not [f for f in findings if f.severity == "error"]
    # Narrative is human-residue — the render carries the placeholder, not invented prose.
    text = render_howto(h)
    assert "HUMAN-RESIDUE" in text
    assert "not projected" in text
