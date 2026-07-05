"""M0 — kernel surface rename to `startd8 kickoff` (three verbs + brownfield on-ramp).

Covers the plan's M0a/M0b + FR-10 alias window:
  (a) `startd8 kickoff {survey,assess,instantiate,derive}` resolve on the kernel surface.
  (b) the old `startd8 concierge …` names still work (hidden alias) and emit a deprecation warning.
  (c) the old MCP `ConciergeInput.action` enum values still dispatch (aliased + DeprecationWarning).
  (d) `startd8 kickoff-legacy` still exposes the demoted metaphor commands.

Nothing is deleted — this is a rename/alias milestone (NR-5, FR-9).
"""

from __future__ import annotations

import warnings
from pathlib import Path

from typer.testing import CliRunner

from startd8.cli import app
from startd8.cli_concierge import concierge_app, kickoff_kernel_app
from startd8.cli_kickoff import kickoff_app as kickoff_legacy_app
from startd8.concierge import handle_concierge_tool
from startd8.concierge.core import _ACTION_ALIASES

runner = CliRunner()


def _make_project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "docs" / "kickoff" / "inputs").mkdir(parents=True)
    (root / "REQUIREMENTS_app.md").write_text(
        "# Reqs\n## Entities\nAI assists\nOwned fields\nCoverage\n", encoding="utf-8"
    )
    return root


# --- (a) kernel verbs resolve on `startd8 kickoff` ----------------------------------------------


def test_kickoff_kernel_exposes_three_verbs_plus_onramp():
    res = runner.invoke(kickoff_kernel_app, ["--help"])
    assert res.exit_code == 0, res.output
    for verb in ("survey", "assess", "instantiate", "derive"):
        assert verb in res.output, f"{verb!r} missing from kernel: {res.output}"


def test_kickoff_kernel_verbs_resolve_via_full_app(tmp_path):
    root = _make_project(tmp_path)
    # survey is a $0 read — exercise it end-to-end on the real surface.
    res = runner.invoke(app, ["kickoff", "survey", str(root)])
    assert res.exit_code == 0, res.output
    assert "survey" in res.output.lower()
    # instantiate/derive at least resolve (help does not error → the verb exists).
    for verb in ("instantiate", "derive", "assess"):
        r = runner.invoke(app, ["kickoff", verb, "--help"])
        assert r.exit_code == 0, (verb, r.output)


def test_kickoff_name_hosts_kernel_not_metaphor():
    # The `kickoff` name no longer routes to the metaphor group's `check`/`red-carpet` verbs.
    res = runner.invoke(app, ["kickoff", "red-carpet", "--help"])
    assert res.exit_code != 0


# --- (b) old `startd8 concierge …` names still work, with a deprecation warning ------------------


def test_concierge_alias_group_still_resolves(tmp_path):
    root = _make_project(tmp_path)
    res = runner.invoke(app, ["concierge", "survey", str(root)])
    assert res.exit_code == 0, res.output


def test_concierge_alias_emits_deprecation_on_stderr(tmp_path):
    root = _make_project(tmp_path)
    res = runner.invoke(concierge_app, ["survey", str(root)])
    assert res.exit_code == 0, res.output
    assert "deprecation" in res.stderr.lower()
    assert "kickoff" in res.stderr.lower()
    # SOTTO: the deprecation stays on stderr — stdout is untouched by the alias.
    assert "deprecation" not in res.stdout.lower()


def test_concierge_alias_old_write_subcommands_still_registered():
    # instantiate-kickoff / derive-contract keep their OLD names on the concierge alias surface.
    for old in ("instantiate-kickoff", "derive-contract", "log-friction"):
        res = runner.invoke(concierge_app, [old, "--help"])
        assert res.exit_code == 0, (old, res.output)


def test_concierge_group_hidden_from_top_level_help():
    res = runner.invoke(app, ["--help"])
    assert res.exit_code == 0
    # The onboarding kernel `kickoff` is the single prominent kickoff-domain group.
    assert "kickoff" in res.output
    # FR-GE-7 / R1-F1: the demoted metaphor group `kickoff-legacy` is now hidden from the
    # top-level listing (still resolvable), so `kickoff` is the ONE visible kickoff group.
    assert "kickoff-legacy" not in res.output
    # The deprecated `concierge` alias is likewise hidden from the main command listing.
    assert "concierge" not in res.output


# --- (c) old MCP `action` enum values still dispatch (aliased + DeprecationWarning) --------------


def test_old_mcp_action_values_still_dispatch(tmp_path):
    root = _make_project(tmp_path)
    for old_action in ("instantiate-kickoff",):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = handle_concierge_tool(old_action, str(root), posture="prototype")
        assert isinstance(result, dict), result
        assert any(
            issubclass(w.category, DeprecationWarning) for w in caught
        ), f"no DeprecationWarning for {old_action}"


def test_canonical_action_dispatches_without_warning(tmp_path):
    root = _make_project(tmp_path)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = handle_concierge_tool("instantiate", str(root), posture="prototype")
    assert isinstance(result, dict)
    assert not any(issubclass(w.category, DeprecationWarning) for w in caught)


def test_action_alias_map_covers_renamed_verbs():
    assert _ACTION_ALIASES == {
        "instantiate-kickoff": "instantiate",
        "derive-contract": "derive",
    }


def test_mcp_enum_carries_canonical_and_deprecated_values():
    # The MCP module is heavy to import; a source check is sufficient to prove the alias-window
    # contract on the MCP surface (canonical `instantiate` + deprecated `instantiate-kickoff`).
    mcp_path = (
        Path(__file__).resolve().parents[3]
        / "mcp"
        / "startd8-mcp-builder"
        / "startd8_mcp.py"
    )
    src = mcp_path.read_text(encoding="utf-8")
    assert 'INSTANTIATE = "instantiate"' in src
    assert 'INSTANTIATE_KICKOFF = "instantiate-kickoff"' in src


# --- (d) `kickoff-legacy` still exposes the demoted metaphor commands ----------------------------


def test_kickoff_legacy_exposes_metaphor_commands():
    res = runner.invoke(kickoff_legacy_app, ["--help"])
    assert res.exit_code == 0, res.output
    for cmd in ("check", "red-carpet", "start", "plan"):
        assert cmd in res.output, f"{cmd!r} missing from kickoff-legacy: {res.output}"


def test_kickoff_legacy_resolves_via_full_app():
    res = runner.invoke(app, ["kickoff-legacy", "lint-config"])
    assert res.exit_code == 0, res.output


def test_kickoff_legacy_emits_deprecation_notice():
    res = runner.invoke(kickoff_legacy_app, ["lint-config"])
    assert res.exit_code == 0, res.output
    assert "deprecation" in res.stderr.lower()
    assert "kickoff-legacy" in res.stderr.lower()
