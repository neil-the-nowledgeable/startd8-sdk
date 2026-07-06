# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Guided multi-field confirm walk — the interactive layer over value-input confirmation.

Covers GUIDED_CONFIRM_FLOW: awaiting ordering, per-field prompt context, the set/as-is/skip/quit
dispatch, validation re-prompt, resumability, TTY-refuse, and the bare-`kickoff confirm` CLI adapter.
The loop is pure-of-IO — driven by a scripted reader (no real stdin).
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from startd8.cli import app
from startd8.concierge.confirm_walk import awaiting_fields, field_prompt_lines, run_confirm_walk
from startd8.concierge.confirmation import confirmed_value_paths, load_ledger

runner = CliRunner()

_BUDGET = "build-preferences.yaml#/budgets.per_pipeline_run"
_MODE = "business-targets.yaml#/monetization.mode_now"
_OBS = "observability.yaml#/provenance_default"

_FILES = {
    "build-preferences.yaml": "provenance_default: estimate\nbudgets:\n  per_pipeline_run: \"10\"\n",
    "business-targets.yaml": "provenance_default: estimate\nmonetization:\n  mode_now: free-during-demo\n",
    "observability.yaml": "provenance_default: config-default\n",
}


def _mk_project(tmp_path):
    inputs = tmp_path / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True)
    for name, body in _FILES.items():
        (inputs / name).write_text(body, encoding="utf-8")
    return tmp_path


def _reader(inputs):
    seq = iter(inputs)
    return lambda _prompt: next(seq, None)   # exhausted → None = quit


# ── ordering + prompt context ────────────────────────────────────────────────────────────────────


def test_awaiting_ordered_by_domain_ordinal(tmp_path):
    _mk_project(tmp_path)
    order = [f["value_path"] for f in awaiting_fields(tmp_path)]
    # registry ordinals: business-targets(1) < observability(2) < build-preferences(4)
    assert order == [_MODE, _OBS, _BUDGET]


def test_awaiting_excludes_fields_whose_input_file_is_absent(tmp_path):
    # Only build-preferences present ⇒ only its field is walkable (consistent with `assess`, and
    # avoids offering a field whose confirm would always fail with the file missing).
    inputs = tmp_path / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True)
    (inputs / "build-preferences.yaml").write_text(_FILES["build-preferences.yaml"], encoding="utf-8")
    order = [f["value_path"] for f in awaiting_fields(tmp_path)]
    assert order == [_BUDGET]   # _MODE / _OBS excluded (their files are absent)


def test_field_prompt_lines_reuse_registry_and_grammar(tmp_path):
    _mk_project(tmp_path)
    field = next(f for f in awaiting_fields(tmp_path) if f["value_path"] == _BUDGET)
    lines = field_prompt_lines(tmp_path, field, None, {})
    blob = "\n".join(lines)
    assert "Per-pipeline-run budget" in blob and "currently '10'" in blob   # label + current default
    assert "why:" in blob                                                    # domain question (reused)
    assert "dollar ceiling" in blob                                          # FieldDef.grammar_help


# ── dispatch: set / as-is / skip / quit ──────────────────────────────────────────────────────────


def test_set_value_on_text_field(tmp_path):
    _mk_project(tmp_path)
    # order = [mode, obs, budget]; skip the two selects, set the budget.
    s = run_confirm_walk(tmp_path, read_input=_reader(["", "", "5.00"]),
                         emit_line=lambda _l: None, timestamp="d")
    assert s["confirmed"] == [_BUDGET] and s["quit"] is False
    assert load_ledger(tmp_path)[_BUDGET] == {"value": "5.00", "at": "d", "mode": "set"}


def test_as_is_confirm(tmp_path):
    _mk_project(tmp_path)
    s = run_confirm_walk(tmp_path, read_input=_reader(["a"]), emit_line=lambda _l: None, timestamp="d")
    assert s["confirmed"] == [_MODE]
    assert load_ledger(tmp_path)[_MODE]["mode"] == "as-is"


def test_enter_skips_and_stays_awaiting(tmp_path):
    _mk_project(tmp_path)
    s = run_confirm_walk(tmp_path, read_input=_reader(["", "", ""]), emit_line=lambda _l: None)
    assert s["confirmed"] == [] and set(s["skipped"]) == {_MODE, _OBS, _BUDGET}
    assert confirmed_value_paths(tmp_path) == set()   # nothing written


def test_quit_persists_prior_confirms(tmp_path):
    _mk_project(tmp_path)
    # confirm the first field (as-is), then quit.
    s = run_confirm_walk(tmp_path, read_input=_reader(["a", "q"]), emit_line=lambda _l: None, timestamp="d")
    assert s["quit"] is True and s["confirmed"] == [_MODE]
    assert _MODE in confirmed_value_paths(tmp_path)   # persisted despite quitting


# ── validation re-prompt (FR-6) ──────────────────────────────────────────────────────────────────


def test_bad_select_value_reprompts_then_confirms(tmp_path):
    _mk_project(tmp_path)
    emitted = []
    # first field is the `mode` select; "nope" is not a choice → re-prompt → "live" confirms.
    s = run_confirm_walk(tmp_path, read_input=_reader(["nope", "live", "q"]),
                         emit_line=emitted.append, timestamp="d")
    assert s["confirmed"] == [_MODE]
    assert load_ledger(tmp_path)[_MODE]["value"] == "live"
    assert any("✗" in ln for ln in emitted)   # the rejection was shown


# ── resumability (FR-5) ──────────────────────────────────────────────────────────────────────────


def test_rerun_only_offers_still_awaiting(tmp_path):
    _mk_project(tmp_path)
    run_confirm_walk(tmp_path, read_input=_reader(["a", "q"]), emit_line=lambda _l: None, timestamp="d")
    # re-run: the confirmed field is no longer offered.
    order = [f["value_path"] for f in awaiting_fields(tmp_path)]
    assert _MODE not in order and order == [_OBS, _BUDGET]


# ── CLI adapter ──────────────────────────────────────────────────────────────────────────────────


def test_cli_bare_confirm_json_lists_awaiting_and_writes_nothing(tmp_path):
    _mk_project(tmp_path)
    r = runner.invoke(app, ["kickoff", "confirm", "--project", str(tmp_path), "--json"])
    assert r.exit_code == 0
    payload = json.loads(r.stdout)
    assert payload["interactive"] is False and payload["awaiting"] == [_MODE, _OBS, _BUDGET]
    assert not (tmp_path / "docs/kickoff/confirmed.yaml").exists()   # refused, wrote nothing


def test_cli_flags_without_value_path_error(tmp_path):
    _mk_project(tmp_path)
    r = runner.invoke(app, ["kickoff", "confirm", "--value", "5", "--project", str(tmp_path)])
    assert r.exit_code == 2


def test_cli_single_shot_still_works(tmp_path):
    _mk_project(tmp_path)
    r = runner.invoke(app, ["kickoff", "confirm", _BUDGET, "--value", "5.00", "--project", str(tmp_path)])
    assert r.exit_code == 0
    assert _BUDGET in confirmed_value_paths(tmp_path)


# ── FR-8: no dependency on the deprecated red-carpet surface ─────────────────────────────────────


def test_walk_does_not_import_the_legacy_driver():
    import startd8.concierge.confirm_walk as cw

    src = (cw.__file__)
    with open(src, encoding="utf-8") as fh:
        text = fh.read()
    assert "run_red_carpet_driver" not in text and "orchestrator" not in text
