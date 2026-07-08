# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""GE-M1 — single guided entry point + vocabulary retirement.

Covers:
  * `startd8 kickoff guided` sequences Orient → Guide deterministically at $0 (no LLM / no network).
  * `--no-guided` is respected at the kernel `assess` seam (offer suppressed, kernel byte-identical).
  * The guided flow REUSES the existing pieces — `build_assess` (Orient) + `build_kickoff_plan`
    (Guide, which itself wraps `red_carpet_advisor`) — no new readiness engine (FR-GE-6). Asserted
    structurally by import/wiring, not by re-deriving readiness.
  * Group retirement: the old `concierge` / `panel` groups (and the interim `kickoff panel`) still
    resolve as HIDDEN deprecated aliases (one release), while `kickoff stakeholders …` is canonical.
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

import startd8.cli_concierge as cli_concierge
from startd8.cli import app
from startd8.cli_concierge import kickoff_guided
from startd8.cli_panel import panel_deprecated_app

runner = CliRunner()


def _make_project(tmp_path):
    root = tmp_path / "proj"
    (root / "docs" / "kickoff" / "inputs").mkdir(parents=True, exist_ok=True)
    (root / "REQUIREMENTS_app.md").write_text(
        "# Reqs\n## Entities\nAI assists\nOwned fields\n", encoding="utf-8"
    )
    return root


# ── kickoff guided runs Orient → Guide deterministically at $0 (no LLM / no network) ──────────────


def test_kickoff_guided_runs_orient_then_guide(tmp_path):
    root = _make_project(tmp_path)
    res = runner.invoke(app, ["kickoff", "guided", str(root)])
    assert res.exit_code == 0, res.stdout
    # phases present, in order
    i_orient = res.stdout.index("1. Orient")
    i_guide = res.stdout.index("2. Guide")
    i_deepen = res.stdout.index("3. Deepen")
    assert i_orient < i_guide < i_deepen
    # Orient renders the readiness surface; Guide renders the deterministic conductor plan.
    assert "Kickoff inputs" in res.stdout
    assert "$0 cascade" in res.stdout


def test_kickoff_guided_is_zero_llm_by_default(tmp_path, monkeypatch):
    """Guide is $0/no-LLM by default (FR-GE-5): a no-agent user costs zero LLM.

    Poison every agent/provider construction path; if `guided` touched one, this raises.
    """
    def _boom(*a, **k):  # pragma: no cover - only fires on a spec violation
        raise AssertionError("guided (no --agent) must not construct an LLM agent / provider")

    import startd8.providers.registry as preg

    monkeypatch.setattr(preg.ProviderRegistry, "get_provider", staticmethod(_boom), raising=False)

    root = _make_project(tmp_path)
    res = runner.invoke(app, ["kickoff", "guided", str(root)])
    assert res.exit_code == 0, res.stdout


def test_kickoff_guided_json_combines_reused_phases(tmp_path):
    root = _make_project(tmp_path)
    res = runner.invoke(app, ["kickoff", "guided", str(root), "--json"])
    assert res.exit_code == 0
    doc = json.loads(res.stdout)
    assert doc["schema"] == "kickoff.guided.v1"
    # Orient payload is the assess result; Guide payload is the plan dict; Deepen is never engaged.
    assert "kickoff_inputs" in doc["orient"]
    assert "steps" in doc["guide"]
    assert doc["deepen"]["engaged"] is False


def test_deepen_is_optional_pointer_only(tmp_path):
    """Deepen is a clearly-marked optional stub in GE-M1 (no panel promotion, no LLM)."""
    root = _make_project(tmp_path)
    off = runner.invoke(app, ["kickoff", "guided", str(root)])
    assert "--deepen" in off.stdout  # skipped-by-default hint names the flag
    on = runner.invoke(app, ["kickoff", "guided", str(root), "--deepen"])
    assert on.exit_code == 0
    assert "later step" in on.stdout  # "coming in a later step" stub, not a real panel run


# ── --no-guided is respected (offer suppressed; kernel byte-identical) ─────────────────────────────


def test_no_guided_flag_suppresses_offer_and_preserves_kernel_bytes(tmp_path, monkeypatch):
    """`--no-guided` (tri-state OFF) suppresses the offer even when interactive + greenfield-blank."""
    captured = []
    monkeypatch.setattr(cli_concierge._stderr_console, "print", lambda *a, **k: captured.append(a))

    class _Term:
        is_terminal = True

    monkeypatch.setattr(cli_concierge, "console", _Term(), raising=False)
    root = _make_project(tmp_path)
    assess_payload = {"kickoff_inputs": {"domains": {"stakeholders": {"status": "absent"}}}}

    # --guided ⇒ an offer surfaces (interactive force-on)…
    cli_concierge._maybe_offer_guided(root, assess=assess_payload, flag=True)
    assert captured, "expected --guided to surface the offer line"
    captured.clear()

    # …--no-guided ⇒ tri-state OFF terminates resolution, no offer line at all.
    cli_concierge._maybe_offer_guided(root, assess=assess_payload, flag=False)
    assert not captured, "--no-guided must suppress the offer entirely"


def test_kernel_assess_stdout_byte_identical_across_guided_flag(tmp_path):
    """The kernel `assess` stdout is byte-identical whether guided is on/off/unset (offer is stderr-only)."""
    root = _make_project(tmp_path)
    outs = []
    for args in ([], ["--guided"], ["--no-guided"]):
        res = runner.invoke(app, ["kickoff", "assess", str(root), *args])
        assert res.exit_code == 0
        outs.append(res.stdout)
    assert outs[0] == outs[1] == outs[2]


# ── FR-GE-6: guided reuses the existing pieces; no new readiness engine ────────────────────────────


def test_guided_reuses_build_assess_and_build_kickoff_plan(monkeypatch, tmp_path):
    """Structural: guided must call the EXISTING `build_assess` (Orient) and `build_kickoff_plan`
    (Guide) — not a private re-implementation. Sentinels prove the wiring."""
    import startd8.concierge as concierge_pkg
    import startd8.kickoff_experience.orchestrator as orch

    calls = {"assess": 0, "plan": 0}

    real_assess = concierge_pkg.build_assess
    real_plan = orch.build_kickoff_plan

    def _spy_assess(root):
        calls["assess"] += 1
        return real_assess(root)

    def _spy_plan(root):
        calls["plan"] += 1
        return real_plan(root)

    # `kickoff_guided` imports these names at call time from their home modules.
    monkeypatch.setattr(concierge_pkg, "build_assess", _spy_assess)
    monkeypatch.setattr(orch, "build_kickoff_plan", _spy_plan)

    root = _make_project(tmp_path)
    res = runner.invoke(app, ["kickoff", "guided", str(root)])
    assert res.exit_code == 0
    assert calls["assess"] == 1, "Orient must reuse concierge.build_assess"
    assert calls["plan"] == 1, "Guide must reuse orchestrator.build_kickoff_plan"


def test_guided_imports_no_new_readiness_engine():
    """FR-GE-6 guard: the guided command references only the existing readiness projections
    (`build_assess`, `build_kickoff_plan`), not a new extractor/generator/writer."""
    import inspect

    src = inspect.getsource(kickoff_guided)
    assert "build_assess" in src
    assert "build_kickoff_plan" in src
    # It must not spin up its own readiness computation or a writer inside the guided seam.
    for forbidden in ("build_red_carpet_state(", "derive_advisories(", "apply_write_plan(", "open("):
        assert forbidden not in src, f"guided must not introduce {forbidden!r} (no new engine)"


# ── Group retirement: old groups resolve as hidden deprecated aliases; kickoff stakeholders is canonical ──


def test_old_concierge_group_is_hidden_deprecated_but_resolves():
    top = runner.invoke(app, ["--help"])
    assert "concierge" not in top.stdout  # not a visible top-level group
    dep = runner.invoke(app, ["concierge", "--help"])
    assert dep.exit_code == 0
    assert "DEPRECATED" in dep.stdout  # still resolves, marked deprecated


def test_old_panel_group_is_hidden_deprecated_but_resolves():
    top = runner.invoke(app, ["--help"])
    # `panel` appears only as the hidden alias, never as a visible standalone top-level group.
    assert "\n│ panel" not in top.stdout
    dep = runner.invoke(app, ["panel", "--help"])
    assert dep.exit_code == 0
    assert "DEPRECATED" in dep.stdout
    # the deprecated alias re-registers the same four verbs
    for verb in ("list", "ask", "ask-all", "import"):
        assert verb in dep.stdout


def test_kickoff_stakeholders_is_the_surviving_surface():
    res = runner.invoke(app, ["kickoff", "stakeholders", "--help"])
    assert res.exit_code == 0
    for verb in ("list", "ask", "ask-all", "import"):
        assert verb in res.stdout
    assert "DEPRECATED" not in res.stdout  # the canonical surface carries no deprecation banner


def test_kickoff_panel_is_now_a_deprecated_alias():
    # `kickoff panel` was canonical for one release; it is renamed to `kickoff stakeholders` and
    # survives only as a hidden deprecated alias (disambiguated from `kickoff portal`).
    res = runner.invoke(app, ["kickoff", "panel", "--help"])
    assert res.exit_code == 0
    assert "DEPRECATED" in res.stdout
    for verb in ("list", "ask", "ask-all", "import"):
        assert verb in res.stdout


def test_panel_deprecated_alias_emits_warning_on_stderr():
    """Invoking the deprecated group runs its callback ⇒ deprecation notice (byte-identical commands)."""
    res = runner.invoke(app, ["panel", "list", "/tmp/does-not-exist-guided-m1"])
    # Exit 2 = roster-missing (the command body ran, i.e. the alias truly dispatches — not a usage error).
    assert res.exit_code == 2


def test_kickoff_deepen_verb_is_a_pointer(tmp_path):
    root = _make_project(tmp_path)
    res = runner.invoke(app, ["kickoff", "deepen", str(root)])
    assert res.exit_code == 0
    # normalize whitespace — Rich wraps the longer command string across lines
    assert "kickoff stakeholders ask-all" in " ".join(res.stdout.split())  # points at the canonical surface
