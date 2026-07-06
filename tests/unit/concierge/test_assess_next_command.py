"""FR-5 — `assess` emits the exact next command (M1).

Covers the ported next-command map (`_blocker_command` + constants, from the retiring Red Carpet
advisor), the per-blocker `next_command`, and the headline `next_command` on `build_assess`.

The load-bearing guard (CRP R3-S1 trap): after M0 the metaphor group moved to `kickoff-legacy`, so
every emitted command MUST resolve against the CURRENT (post-M0) CLI registry — in particular NO
emitted command may reference a bare `startd8 kickoff <metaphor>` path (e.g. `kickoff red-carpet`).
"""

from __future__ import annotations

import pytest

from startd8.concierge import build_assess, handle_concierge_tool
from startd8.concierge.core import (
    CMD_GENERATE_BACKEND,
    CMD_GENERATE_CONTRACT_PROMOTE,
    CMD_KICKOFF_ASSESS,
    CMD_KICKOFF_INSTANTIATE,
    CMD_SCREENS_SUGGEST,
    CMD_SCREENS_SUGGEST_ROLES,
    _blocker_command,
    _headline_next_command,
)

# The commands this milestone is allowed to emit. Each is verified resolvable below.
_EMITTABLE_COMMANDS = {
    CMD_GENERATE_BACKEND,
    CMD_GENERATE_CONTRACT_PROMOTE,
    CMD_SCREENS_SUGGEST,
    CMD_SCREENS_SUGGEST_ROLES,
    CMD_KICKOFF_INSTANTIATE,
    CMD_KICKOFF_ASSESS,
}

# Post-M0 metaphor subcommands that live under `kickoff-legacy`, NOT `kickoff` — a `next_command`
# of the form `startd8 kickoff <one of these>` would fail to resolve (the R3-S1 trap).
_LEGACY_METAPHOR_VERBS = ("red-carpet", "wizard", "start", "chat", "concierge-chat")


# ── the section → command map ──────────────────────────────────────────────────────────────────


def test_blocker_command_schema_family():
    for section in ("Schema / data model", "Contract", "Data Model missing"):
        assert _blocker_command(section) == CMD_GENERATE_CONTRACT_PROMOTE


def test_blocker_command_screen_family():
    # PAGES → the paid `--roles` pass (the $0 baseline only authors views); VIEWS/screens → baseline.
    assert _blocker_command("Pages & Nav") == CMD_SCREENS_SUGGEST_ROLES
    for section in ("Composite Views", "View: dashboard", "Screen X"):
        assert _blocker_command(section) == CMD_SCREENS_SUGGEST


def test_blocker_command_app_family_retargeted_not_red_carpet():
    # The R3-S1 trap: the old advisor pointed these at `startd8 kickoff red-carpet --agent`.
    for section in ("App manifest", "Forms", "Flows"):
        cmd = _blocker_command(section)
        assert cmd == CMD_KICKOFF_INSTANTIATE
        assert "red-carpet" not in cmd


def test_blocker_command_unmapped_returns_none():
    assert _blocker_command("Services") is None
    assert _blocker_command("Deployment posture") is None


# ── no emitted constant references a legacy metaphor path (R3-S1) ───────────────────────────────


def test_no_emitted_constant_references_legacy_metaphor_path():
    for cmd in _EMITTABLE_COMMANDS:
        assert not any(
            cmd == f"startd8 kickoff {verb}" or cmd.startswith(f"startd8 kickoff {verb} ")
            for verb in _LEGACY_METAPHOR_VERBS
        ), f"{cmd!r} references a metaphor verb that moved to kickoff-legacy after M0"


# ── every emitted command resolves in the post-M0 CLI registry ──────────────────────────────────


def _resolve_in_registry(command: str) -> bool:
    """True if `command` (a `startd8 …` string) resolves to a registered Typer command post-M0."""
    from startd8.cli import app

    tokens = command.split()
    assert tokens[0] == "startd8"
    # The subcommand path is the tokens BEFORE the first option flag; everything from the first
    # `-`/`--` on is options + their values (e.g. `--schema prisma/schema.prisma`), not path.
    path = []
    for t in tokens[1:]:
        if t.startswith("-"):
            break
        path.append(t)

    def _walk(typer_app, remaining):
        if not remaining:
            return True
        head, *tail = remaining
        info = typer_app.registered_groups + typer_app.registered_commands
        # Groups first (nested typers), then leaf commands.
        for grp in typer_app.registered_groups:
            if grp.name == head:
                return _walk(grp.typer_instance, tail)
        for cmd in typer_app.registered_commands:
            name = cmd.name or (cmd.callback.__name__.replace("_", "-") if cmd.callback else None)
            if name == head:
                return not tail  # leaf command: no further path allowed
        return False

    return _walk(app, path)


@pytest.mark.parametrize("command", sorted(_EMITTABLE_COMMANDS))
def test_every_emittable_command_resolves_post_m0(command):
    assert _resolve_in_registry(command), f"{command!r} does not resolve in the post-M0 CLI"


def test_legacy_red_carpet_does_not_resolve_under_kickoff():
    # Sanity: proves the trap is real — `startd8 kickoff red-carpet` genuinely does NOT resolve.
    assert not _resolve_in_registry("startd8 kickoff red-carpet")
    # …but it DOES resolve under the demoted group.
    assert _resolve_in_registry("startd8 kickoff-legacy red-carpet")


# ── integration: assess attaches next_command to blockers + a headline ──────────────────────────


def test_assess_reframes_bare_project_as_not_buildable(tmp_path):
    # Blocker reframe: a bare project has NO hard blockers (nothing is *invalid*), but it is NOT
    # buildable — the schema is missing, so backend/views generators are blocked. Optional next
    # steps are suppressed while not buildable (they're downstream of the missing schema).
    cascade = handle_concierge_tool("assess", tmp_path)["cascade"]
    assert cascade["status"] == "ok"
    assert cascade["hard_blockers"] == []
    assert cascade["buildable"] is False
    assert cascade["blocked_generators"]  # backend/views blocked on the schema
    assert cascade["optional_next_steps"] == []


def test_assess_emits_headline_next_command(tmp_path):
    out = build_assess(tmp_path)
    assert "next_command" in out
    headline = out["next_command"]
    # A bare project is not build-ready → a headline command is present and resolvable.
    assert headline is not None
    assert headline in _EMITTABLE_COMMANDS
    assert _resolve_in_registry(headline)


def test_headline_hard_blocker_wins():
    # A hard blocker (invalid manifest) that names a command takes priority.
    cascade = {"status": "ok", "buildable": False,
               "hard_blockers": [{"section": "App", "next_command": CMD_KICKOFF_INSTANTIATE}]}
    assert _headline_next_command(cascade) == CMD_KICKOFF_INSTANTIATE


def test_headline_buildable_points_at_build():
    # Reframe: buildable (no hard blockers, all generators ready) → BUILD, not an optional gap.
    cascade = {"status": "ok", "hard_blockers": [], "buildable": True, "blocked_generators": {}}
    assert _headline_next_command(cascade) == CMD_GENERATE_BACKEND


def test_headline_not_buildable_points_at_schema_root():
    # Reframe: a blocked backend/views generator → the schema contract is the root (not pages).
    cascade = {"status": "ok", "hard_blockers": [], "buildable": False,
               "blocked_generators": {"backend": "blocked(missing schema.prisma)"}}
    assert _headline_next_command(cascade) == CMD_GENERATE_CONTRACT_PROMOTE


def test_headline_falls_back_to_assess_on_inputs_error():
    assert _headline_next_command({"status": "inputs_error"}) == CMD_KICKOFF_ASSESS


def test_headline_none_when_no_commanded_blocker():
    assert _headline_next_command({"status": "ok", "blockers": []}) is None
    assert _headline_next_command(
        {"status": "ok", "blockers": [{"section": "Services", "next_command": None}]}
    ) is None
