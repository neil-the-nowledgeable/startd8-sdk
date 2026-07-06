# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Kickoff value-input confirmation — the kernel `kickoff confirm` verb + honest assess count.

Covers the VALUE_INPUT_CONFIRMATION feature (replaces the legacy `"REVIEW"` sentinel confirm-leg):
ledger IO, confirmable inventory, honest per-field count, set/as-is confirm, stale detection,
scanner-invisibility (R1-S1), partial-failure contract (R1-S2), and value_path round-trip (R1-S7).
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from startd8.cli import app
from startd8.concierge.confirmation import (
    LEDGER_REL,
    ConfirmError,
    apply_confirm,
    build_confirm_plan,
    confirmable_fields,
    confirmed_value_paths,
    domain_confirmation,
    load_ledger,
)

runner = CliRunner()

_BUILD_PREFS = "provenance_default: estimate\nbudgets:\n  per_pipeline_run: \"10\"\n"
_BIZ = "provenance_default: estimate\nmonetization:\n  mode_now: pre-revenue\n"


def _mk_project(tmp_path):
    """Minimal instantiated project: the two input files whose confirmable fields we exercise."""
    inputs = tmp_path / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True)
    (inputs / "build-preferences.yaml").write_text(_BUILD_PREFS, encoding="utf-8")
    (inputs / "business-targets.yaml").write_text(_BIZ, encoding="utf-8")
    return tmp_path


_BUDGET = "build-preferences.yaml#/budgets.per_pipeline_run"
_MODE = "business-targets.yaml#/monetization.mode_now"


# ── inventory + ledger IO ─────────────────────────────────────────────────────────────────────────


def test_confirmable_fields_are_the_defaulted_set():
    vps = {f["value_path"] for f in confirmable_fields()}
    assert _BUDGET in vps and _MODE in vps
    # a fully-authored field (conventions language) is NOT confirmable.
    assert "conventions.yaml#/language" not in vps


def test_load_ledger_absent_is_empty(tmp_path):
    assert load_ledger(tmp_path) == {}
    assert confirmed_value_paths(tmp_path) == set()


def test_load_ledger_malformed_degrades(tmp_path):
    (tmp_path / "docs" / "kickoff").mkdir(parents=True)
    (tmp_path / LEDGER_REL).write_text("{ not: valid: yaml", encoding="utf-8")
    assert load_ledger(tmp_path) == {}   # never raises


# ── honest count (FR-3) ─────────────────────────────────────────────────────────────────────────


def test_domain_confirmation_absent_ledger_all_awaiting(tmp_path):
    _mk_project(tmp_path)
    conf = domain_confirmation(tmp_path)
    assert conf["build-preferences"] == {"confirmable": 1, "confirmed": 0, "awaiting": 1, "stale": 0}


def test_confirm_set_decrements_awaiting(tmp_path):
    _mk_project(tmp_path)
    plan = build_confirm_plan(tmp_path, _BUDGET, "5.00", mode="set", timestamp="2026-07-06")
    apply_confirm(tmp_path, plan)
    conf = domain_confirmation(tmp_path)["build-preferences"]
    assert conf == {"confirmable": 1, "confirmed": 1, "awaiting": 0, "stale": 0}
    # the value landed in the YAML AND the ledger records it with mode.
    assert "5.00" in (tmp_path / "docs/kickoff/inputs/build-preferences.yaml").read_text()
    assert load_ledger(tmp_path)[_BUDGET] == {"value": "5.00", "at": "2026-07-06", "mode": "set"}


def test_confirm_as_is_records_on_disk_value_distinguishably(tmp_path):
    _mk_project(tmp_path)
    plan = build_confirm_plan(tmp_path, _MODE, mode="as-is", timestamp="2026-07-06")
    apply_confirm(tmp_path, plan)
    entry = load_ledger(tmp_path)[_MODE]
    assert entry == {"value": "pre-revenue", "at": "2026-07-06", "mode": "as-is"}
    # as-is changed no YAML value.
    assert "pre-revenue" in (tmp_path / "docs/kickoff/inputs/business-targets.yaml").read_text()


def test_stale_when_confirmed_field_hand_edited(tmp_path):
    _mk_project(tmp_path)
    apply_confirm(tmp_path, build_confirm_plan(tmp_path, _BUDGET, "5.00", timestamp="d"))
    # hand-edit the confirmed field on disk → diverges from the ledger's recorded value.
    (tmp_path / "docs/kickoff/inputs/build-preferences.yaml").write_text(
        "provenance_default: estimate\nbudgets:\n  per_pipeline_run: \"999\"\n", encoding="utf-8"
    )
    conf = domain_confirmation(tmp_path)["build-preferences"]
    assert conf["confirmed"] == 1 and conf["stale"] == 1   # still confirmed (decision act), but stale


# ── errors + round-trip ─────────────────────────────────────────────────────────────────────────


def test_unknown_field_raises(tmp_path):
    with pytest.raises(ConfirmError) as e:
        build_confirm_plan(tmp_path, "nope.yaml#/x", "y")
    assert e.value.code == "unknown_field"


def test_set_without_value_raises(tmp_path):
    _mk_project(tmp_path)
    with pytest.raises(ConfirmError) as e:
        build_confirm_plan(tmp_path, _BUDGET, None, mode="set")
    assert e.value.code == "missing_value"


def test_ledger_key_round_trips_to_assess_lookup(tmp_path):
    """R1-S7: the key emitted at confirm == the value_path the count looks up (else silent miss)."""
    _mk_project(tmp_path)
    apply_confirm(tmp_path, build_confirm_plan(tmp_path, _BUDGET, "5.00", timestamp="d"))
    assert _BUDGET in confirmed_value_paths(tmp_path)
    assert domain_confirmation(tmp_path)["build-preferences"]["confirmed"] == 1


def test_partial_failure_is_loud(tmp_path, monkeypatch):
    """R1-S2: value write succeeds but ledger write fails ⇒ apply_confirm must FAIL loud, not silently
    under-count (`safe_write.apply_write_plan` never raises — it returns errors/blocked)."""
    import startd8.concierge.safe_write as sw

    _mk_project(tmp_path)
    plan = build_confirm_plan(tmp_path, _BUDGET, "5.00", timestamp="d")

    class _Bad:
        ok = False
        written: list = []
        blocked = [{"path": LEDGER_REL, "reason": "injected"}]
        errors: list = []
        skipped: list = []

    real = sw.apply_write_plan

    def fake(root, writes, **k):   # fail ONLY the ledger write; value write goes through
        if any(getattr(w, "path", None) == LEDGER_REL for w in writes):
            return _Bad()
        return real(root, writes, **k)

    monkeypatch.setattr(sw, "apply_write_plan", fake)
    with pytest.raises(ConfirmError) as e:
        apply_confirm(tmp_path, plan)
    assert e.value.code == "ledger_not_recorded"
    # the value DID land (value-first), only the confirmation record failed — hence "loud".
    assert "5.00" in (tmp_path / "docs/kickoff/inputs/build-preferences.yaml").read_text()


# ── scanner-invisibility (R1-S1) + FR-6 byte-identity ────────────────────────────────────────────


def test_ledger_is_scanner_invisible(tmp_path):
    from startd8.concierge.core import build_survey

    _mk_project(tmp_path)
    apply_confirm(tmp_path, build_confirm_plan(tmp_path, _BUDGET, "5.00", timestamp="d"))
    # ledger lives OUTSIDE inputs/, and no survey list mentions it.
    assert not (tmp_path / "docs/kickoff/inputs/confirmed.yaml").exists()
    assert (tmp_path / LEDGER_REL).exists()
    blob = json.dumps(build_survey(tmp_path))
    assert "confirmed.yaml" not in blob


def test_no_ledger_when_nothing_confirmed(tmp_path):
    """FR-6 / R1-S5: assess with zero confirms leaves no ledger file on disk."""
    from startd8.concierge import build_assess

    _mk_project(tmp_path)
    build_assess(tmp_path)
    assert not (tmp_path / LEDGER_REL).exists()


# ── FR-7: the legacy prefill (the "REVIEW" sentinel source) is GONE entirely ─────────────────────


def test_legacy_prefill_machinery_removed():
    # The red-carpet wizard's value-input prefill (`_prefill_actions`, which once wrote the "REVIEW"
    # sentinel) was retired with the wizard — a stronger guarantee than "no sentinel". Value-input
    # confirmation now lives only in the kernel `kickoff confirm` (+ the guided walk).
    import startd8.kickoff_experience.orchestrator as orch

    assert not hasattr(orch, "_prefill_actions")
    assert not hasattr(orch, "run_red_carpet_driver")


# ── CLI ──────────────────────────────────────────────────────────────────────────────────────────


def test_cli_confirm_and_assess_count(tmp_path):
    _mk_project(tmp_path)
    r = runner.invoke(app, ["kickoff", "confirm", _BUDGET, "--value", "5.00", "--project", str(tmp_path)])
    assert r.exit_code == 0, r.stdout
    a = runner.invoke(app, ["kickoff", "assess", str(tmp_path), "--json"])
    dom = json.loads(a.stdout)["kickoff_inputs"]["domains"]["build-preferences"]["confirmation"]
    assert dom["confirmed"] == 1 and dom["awaiting"] == 0


def test_cli_confirm_json_and_bad_flags(tmp_path):
    _mk_project(tmp_path)
    j = runner.invoke(app, ["kickoff", "confirm", _MODE, "--as-is", "--project", str(tmp_path), "--json"])
    assert json.loads(j.stdout)["mode"] == "as-is"
    # neither flag → error exit 2
    bad = runner.invoke(app, ["kickoff", "confirm", _BUDGET, "--project", str(tmp_path)])
    assert bad.exit_code == 2
    # unknown field → exit 2
    unk = runner.invoke(app, ["kickoff", "confirm", "x.yaml#/y", "--value", "1", "--project", str(tmp_path)])
    assert unk.exit_code == 2
