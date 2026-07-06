"""Tests for the Kickoff UX / IA presentation layer (KICKOFF_UX FR-UX + CRP R1)."""

from __future__ import annotations

import tempfile

from startd8.kickoff_experience import presentation as P
from startd8.kickoff_experience.red_carpet import RedCarpetStage, RedCarpetState, build_red_carpet_state


def _state(*, schema=False, app=False, pages=False, views=False, completion=None,
           advisories=(), next_steps=()):
    gates = {"schema": schema, "app": app, "pages": pages, "views": views}
    unmet = tuple(k for k in ("schema", "app", "pages", "views") if not gates[k])
    stages = (
        RedCarpetStage("data_model", "done" if schema else "pending", ""),
        RedCarpetStage("manifests", "done" if (app and pages and views) else "pending", ""),
        RedCarpetStage("value_inputs", "pending", ""),
        RedCarpetStage("content", "pending", ""),
        RedCarpetStage("run", "done" if not unmet else "pending", ""),
    )
    return RedCarpetState(
        stages=stages, next_stage=next((s.key for s in stages if s.status != "done"), None),
        cascade_offerable=not unmet, unmet_gates=unmet, readiness_score=0.4,
        completion=completion, advisories=tuple(advisories), next_steps=tuple(next_steps))


class _Adv:
    def __init__(self, severity): self.severity = severity


# ── FR-UX-1 / CRP R1-F1: Build never "done"; content de-emphasized ────────────────────────────────

def test_build_renders_ready_not_done_when_offerable():
    spine = {n.key: n for n in P.build_spine(_state(schema=True, app=True, pages=True, views=True))}
    assert spine["run"].status == "ready"       # offerable ≠ built — never ✓done
    assert spine["content"].status == "later" and spine["content"].optional


def test_spine_marks_the_next_gap():
    spine = {n.key: n for n in P.build_spine(_state(schema=False))}
    assert spine["data_model"].status == "next"


# ── FR-UX-7 / CRP R1-F3: headline is "% filled", honestly annotated ───────────────────────────────

def test_headline_is_percent_filled():
    st = _state(schema=True, completion={"overall_pct": 40, "n_defaulted": 0, "stages": []})
    assert "40% filled" in P.headline(st)["pct_label"]


def test_headline_not_yet_buildable_at_100():
    # all fillable present but not offerable → 100% filled · not yet buildable (never a bare "done")
    st = _state(schema=True, app=True, pages=True, views=False,
                completion={"overall_pct": 100, "n_defaulted": 0, "stages": []})
    assert "not yet buildable" in P.headline(st)["pct_label"]


def test_headline_flags_all_defaulted():
    st = _state(schema=True, completion={"overall_pct": 50, "n_defaulted": 4, "stages": []})
    assert "to review" in P.headline(st)["pct_label"]


# ── FR-UX-4/8: single next action + calm greenfield ───────────────────────────────────────────────

def test_greenfield_is_calm_and_points_to_confirm():
    # The interactive wizard was retired; greenfield now points at the kernel `kickoff confirm`.
    st = _state(schema=False, completion={"overall_pct": 0, "n_defaulted": 0, "stages": []})
    hl = P.headline(st)
    assert hl["greenfield"] is True
    assert "begin with Your data" in hl["next_action"]["title"]
    assert hl["next_action"]["command"] == "startd8 kickoff confirm"
    assert "--wizard" not in hl["next_action"]["command"]


# ── FR-UX-4/F4: error advisories are counted (never hidden) ───────────────────────────────────────

def test_headline_counts_error_advisories():
    st = _state(schema=False, advisories=[_Adv("error"), _Adv("warn"), _Adv("error")])
    assert P.headline(st)["n_errors"] == 2


# ── FR-UX-2 / CRP R1-F2: the no-jargon guard over the RENDERED default view ───────────────────────

def _render_default(state) -> str:
    from rich.console import Console
    import startd8.cli_kickoff as cli
    buf = Console(record=True, width=100)
    orig = cli.console
    cli.console = buf
    try:
        cli._render_red_carpet_state(state, verbose=False)
    finally:
        cli.console = orig
    return buf.export_text()


def test_default_view_has_no_jargon():
    # a full state with advisories/next_steps present — none of it should leak jargon in the DEFAULT view.
    st = build_red_carpet_state(tempfile.mkdtemp())
    text = _render_default(st)
    bad = P.has_jargon(text)
    assert bad is None, f"default view leaked jargon: {bad!r}\n{text}"


def test_default_view_is_focused():
    st = build_red_carpet_state(tempfile.mkdtemp())
    lines = [ln for ln in _render_default(st).splitlines() if ln.strip()]
    assert len(lines) <= 12                                  # focused, not a wall
    assert sum(1 for ln in lines if "Do next" in ln) == 1    # exactly one next action


def test_verbose_restores_detail():
    from rich.console import Console
    import startd8.cli_kickoff as cli
    st = build_red_carpet_state(tempfile.mkdtemp())
    buf = Console(record=True, width=100)
    orig = cli.console
    cli.console = buf
    try:
        cli._render_red_carpet_state(st, verbose=True)
    finally:
        cli.console = orig
    text = buf.export_text()
    assert "Insights" in text and "Playbook" in text          # detail is back under --verbose


# (The wizard-step render + wizard-prose tests were removed with the retired red-carpet wizard —
#  ADR_RETIRE_RED_CARPET_WIZARD; value-input prompts now live in the kernel confirm walk.)


# ── Command-resolution guard (regression for the stale `kickoff red-carpet` next-action) ──────────
# The headline's next-action command MUST resolve in the post-M0 CLI registry. Post-M0 the red-carpet
# metaphor moved to `kickoff-legacy`, so `startd8 kickoff red-carpet …` errors "No such command
# 'red-carpet'". This headline was the third emitter of that stale form (after core.py + the advisor).
import pytest


def _resolve_in_registry(command: str) -> bool:
    """True if `command` (a `startd8 …` string) resolves to a registered Typer command."""
    from startd8.cli import app

    tokens = command.split()
    assert tokens[0] == "startd8"
    path = []
    for t in tokens[1:]:
        if t.startswith("-"):
            break
        path.append(t)

    def _walk(typer_app, remaining):
        if not remaining:
            return True
        head, *tail = remaining
        for grp in typer_app.registered_groups:
            if grp.name == head:
                return _walk(grp.typer_instance, tail)
        for cmd in typer_app.registered_commands:
            if cmd.name == head and not tail:
                return True
        return False

    return _walk(app, path)


@pytest.mark.parametrize("command", [P.CMD_WIZARD, P.CMD_REVIEW, P.CMD_BUILD])
def test_headline_command_resolves(command):
    assert _resolve_in_registry(command), f"{command!r} does not resolve in the CLI registry"


def test_no_headline_command_uses_the_demoted_bare_red_carpet():
    # Regression: the bug the user hit — a bare `kickoff red-carpet` (must be `kickoff-legacy`).
    for command in (P.CMD_WIZARD, P.CMD_REVIEW, P.CMD_BUILD):
        assert "kickoff red-carpet" not in command
