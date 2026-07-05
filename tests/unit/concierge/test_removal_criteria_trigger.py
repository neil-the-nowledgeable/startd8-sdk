"""M5 — removal-criteria detection trigger (FR-12 / R2-F1).

This is the *forcing function* the migration note (``MIGRATION_NOTE.md``) codifies:
a passive checklist would let eligible code sit in the tree indefinitely (the
accidental-complexity-accretes pattern). Instead this test **enumerates the current
deprecated-alias surfaces** and **asserts they still resolve** — so:

  * Today (alias window OPEN): every enumerated surface resolves ⇒ NR-5 holds,
    nothing has been deleted; the enumeration below IS the checklist a future
    deletion PR must clear across the three real registries (CLI subcommands, MCP
    ``action`` enum, documented consumers).

  * Later (alias window CLOSING): when the aliases are actually removed, these
    assertions FLIP TO FAILING — a loud, dated, CI-visible signal that the window is
    being closed and that the removal-criteria grep now has a concrete target list.
    That is the activation gate FR-12/R2-F1 requires.

CRP correction (R1-F1): the removal gate is checked against the CLI subcommand set,
the MCP ``ConciergeInput.action`` enum, and documented consumers — **NOT** the
``startd8.contractors.deterministic_providers`` entry-point group (which would pass
vacuously; the retiring surfaces are CLI/MCP commands, not deterministic-provider
plugins).

Nothing here deletes anything (NR-5). This test only *observes*.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from startd8.cli import app
from startd8.cli_concierge import concierge_app
from startd8.cli_kickoff import kickoff_app as kickoff_legacy_app
from startd8.concierge.core import _ACTION_ALIASES

runner = CliRunner()


# --- The deprecated-alias surface inventory (the future-deletion checklist) ----------------------
#
# Each entry is a surface a later deletion PR must confirm has ZERO live callers across the three
# registries before the underlying code may be removed. Keep this list in sync with the aliases in
# cli.py / cli_concierge.py / concierge/core.py / the MCP ConciergeAction enum.

# (1) CLI: hidden alias *groups* that survive one release (FR-10 / FR-GE-7).
DEPRECATED_CLI_GROUPS = ("concierge", "panel", "kickoff-legacy")

# (2) CLI: old write-verb subcommand names kept on the hidden `concierge` group.
DEPRECATED_CONCIERGE_SUBCOMMANDS = ("instantiate-kickoff", "derive-contract", "log-friction")

# (3) MCP: old `action` enum values still dispatched via the alias map (FR-10).
DEPRECATED_MCP_ACTION_VALUES = tuple(_ACTION_ALIASES.keys())

# (4) Documented consumers whose migration is a removal precondition (FR-11).
DOCUMENTED_CONSUMERS = ("navig8", "household-o11y", "benchmark portal")


def test_removal_checklist_is_non_empty_and_covers_all_three_registries():
    """The detection trigger must actually enumerate something across each registry."""
    assert DEPRECATED_CLI_GROUPS, "CLI alias groups must be enumerated"
    assert DEPRECATED_CONCIERGE_SUBCOMMANDS, "CLI alias subcommands must be enumerated"
    assert DEPRECATED_MCP_ACTION_VALUES, "MCP action-enum aliases must be enumerated"
    assert DOCUMENTED_CONSUMERS, "documented consumers must be enumerated"


# --- (1) CLI alias groups still resolve (NR-5: nothing deleted) ----------------------------------


def test_deprecated_cli_alias_groups_still_resolve():
    """While the window is open, each hidden alias group must still resolve (`--help` ok)."""
    for group in DEPRECATED_CLI_GROUPS:
        res = runner.invoke(app, [group, "--help"])
        assert res.exit_code == 0, (
            f"deprecated CLI group {group!r} no longer resolves — if the alias window was "
            f"intentionally closed, update MIGRATION_NOTE.md and the removal checklist. Output: {res.output}"
        )


# --- (2) old write-verb subcommands still registered on the alias group --------------------------


def test_deprecated_concierge_subcommands_still_registered():
    for old in DEPRECATED_CONCIERGE_SUBCOMMANDS:
        res = runner.invoke(concierge_app, [old, "--help"])
        assert res.exit_code == 0, (
            f"deprecated concierge subcommand {old!r} no longer resolves (NR-5 violated unless "
            f"the alias window was deliberately closed). Output: {res.output}"
        )


def test_kickoff_legacy_still_hosts_the_retiring_metaphor_commands():
    res = runner.invoke(kickoff_legacy_app, ["--help"])
    assert res.exit_code == 0, res.output
    # red-carpet is the retiring metaphor whose $0 command-map was ported into the kernel (FR-5);
    # its home surface must still exist until the removal PR (NR-5).
    assert "red-carpet" in res.output, res.output


# --- (3) MCP action-enum aliases still dispatch --------------------------------------------------


def test_deprecated_mcp_action_aliases_still_dispatch():
    """Each old MCP `action` value must still map to a canonical verb (scripted/MCP callers)."""
    assert "instantiate-kickoff" in DEPRECATED_MCP_ACTION_VALUES
    assert "derive-contract" in DEPRECATED_MCP_ACTION_VALUES
    for old, canonical in _ACTION_ALIASES.items():
        assert canonical in ("instantiate", "derive"), (old, canonical)


def test_mcp_enum_still_carries_the_deprecated_value():
    """Source check on the MCP enum — the deprecated value must still be a member (FR-10)."""
    mcp_path = (
        Path(__file__).resolve().parents[3]
        / "mcp"
        / "startd8-mcp-builder"
        / "startd8_mcp.py"
    )
    src = mcp_path.read_text(encoding="utf-8")
    assert 'INSTANTIATE_KICKOFF = "instantiate-kickoff"' in src, (
        "the deprecated MCP action-enum value was removed — closing the alias window. "
        "Confirm the removal checklist in MIGRATION_NOTE.md cleared the MCP registry first."
    )


# --- (4) the consumer-safe VIPP default-posting seam is still in place (M3 alias window) ----------


def test_project_init_still_posts_vipp_by_default():
    """household-o11y + benchmark portal rely on `project init` posting VIPP by default until the
    alias window closes (FR-1a consumer-safe window). The default must remain `with_vipp=True`."""
    import inspect

    from startd8.project import init as project_init

    sig = inspect.signature(project_init.establish_postings)
    assert sig.parameters["with_vipp"].default is True, (
        "project init no longer posts VIPP by default — this closes the M3 consumer-safe window "
        "and would double-break household-o11y / benchmark portal. Migrate them to `--with-vipp` "
        "and update MIGRATION_NOTE.md before flipping this default."
    )


# --- (5) FR-5a capability loss is recorded (the skipped schema-shape diagnostics) ----------------


def test_fr5a_schema_diagnostics_loss_is_recorded_and_code_retained():
    """FR-5a was skipped (schema-shape diagnostics not ported into the kernel). Two invariants:
      (a) the loss is named in the migration note (FR-5a's "accept the loss and name it" clause);
      (b) the source code is RETAINED, not deleted (NR-5), so it can be re-surfaced later.
    """
    note = (
        Path(__file__).resolve().parents[3]
        / "docs" / "design" / "project-start" / "MIGRATION_NOTE.md"
    ).read_text(encoding="utf-8")
    assert "FR-5a" in note and "_schema_advisories" in note, "FR-5a loss not named in migration note"

    advisor = (
        Path(__file__).resolve().parents[3]
        / "src" / "startd8" / "kickoff_experience" / "red_carpet_advisor.py"
    )
    assert advisor.exists(), "red_carpet_advisor.py was deleted — NR-5 violated"
    assert "_schema_advisories" in advisor.read_text(encoding="utf-8"), (
        "the schema-shape diagnostics were removed from the retained advisor — NR-5 violated"
    )


# --- The trigger itself: print the checklist a future deletion PR must clear ---------------------


def test_removal_trigger_emits_the_deletion_checklist(capsys):
    """Emit the concrete caller-inventory a future deletion PR must clear across all three
    registries. This is the activation mechanism (FR-12/R2-F1): run this test, read the checklist,
    grep each surface for live callers; delete only what resolves to zero."""
    lines = [
        "REMOVAL-CRITERIA CHECKLIST (FR-12) — a deletion PR must show ZERO live callers for each:",
        "  CLI alias groups:        " + ", ".join(DEPRECATED_CLI_GROUPS),
        "  CLI alias subcommands:   " + ", ".join(DEPRECATED_CONCIERGE_SUBCOMMANDS),
        "  MCP action-enum aliases: " + ", ".join(DEPRECATED_MCP_ACTION_VALUES),
        "  Documented consumers:    " + ", ".join(DOCUMENTED_CONSUMERS),
        "  (checked across CLI subcommands + MCP action enum + documented consumers,",
        "   NOT the startd8.contractors.deterministic_providers group — R1-F1.)",
    ]
    print("\n".join(lines))
    out = capsys.readouterr().out
    assert "REMOVAL-CRITERIA CHECKLIST" in out
    # every enumerated surface appears in the emitted checklist
    for surface in (*DEPRECATED_CLI_GROUPS, *DEPRECATED_CONCIERGE_SUBCOMMANDS, *DEPRECATED_MCP_ACTION_VALUES):
        assert surface in out
