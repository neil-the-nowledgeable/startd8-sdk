# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Kickoff-audience M5 — confirm-all (FR-12/FR-18/A-FR12b) + the FR-4 byte-identity goldens.

The acceptance gate that proves audience stayed a *lens*: given the SAME explicit decisions, output is
byte-identical across audiences (A-FR4). Plus the Advanced batch confirm-all: two-phase, placeholder-
skipping, and byte-identical to N single confirms (test_confirm_all_equals_single).
"""

from __future__ import annotations

from startd8.concierge.audience import apply_audience_defaults
from startd8.concierge.confirmation import (
    apply_confirm,
    apply_confirm_all,
    build_confirm_all_plan,
    build_confirm_plan,
    load_ledger,
)

_BUDGET = "build-preferences.yaml#/budgets.per_pipeline_run"
_MODE = "business-targets.yaml#/monetization.mode_now"
_OBS = "observability.yaml#/provenance_default"


def _mk(tmp_path, *, budget="10", mode="live", obs="authored"):
    inputs = tmp_path / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True)
    (inputs / "build-preferences.yaml").write_text(
        f"provenance_default: estimate\nbudgets:\n  per_pipeline_run: \"{budget}\"\n", encoding="utf-8")
    (inputs / "business-targets.yaml").write_text(
        f"provenance_default: estimate\nmonetization:\n  mode_now: {mode}\n", encoding="utf-8")
    (inputs / "observability.yaml").write_text(f"provenance_default: {obs}\n", encoding="utf-8")


def _ledger_values(tmp_path):
    return {vp: e["value"] for vp, e in load_ledger(tmp_path).items()}


# --- FR-12 / FR-18 / A-FR12b: confirm-all --------------------------------------------------------

def test_confirm_all_skips_placeholders(tmp_path):
    _mk(tmp_path, budget="$<5.00>", mode="<free-during-demo | live>", obs="config-default")
    plan = build_confirm_all_plan(tmp_path)
    skipped = {vp for vp, _ in plan.skipped_placeholder}
    assert _BUDGET in skipped and _MODE in skipped          # placeholders NOT confirmed (R4-F33)
    assert _OBS in {vp for vp, _ in plan.to_confirm}         # a real value IS confirmable


def test_confirm_all_builds_and_applies_real_values(tmp_path):
    _mk(tmp_path, budget="5.00", mode="live", obs="config-default")
    plan = build_confirm_all_plan(tmp_path)
    assert {vp for vp, _ in plan.to_confirm} == {_BUDGET, _MODE, _OBS}
    applied = apply_confirm_all(tmp_path, plan, timestamp="2026-07-07")
    assert set(applied) == {_BUDGET, _MODE, _OBS}
    assert set(load_ledger(tmp_path)) == {_BUDGET, _MODE, _OBS}   # two-phase: none clobbered


def test_confirm_all_equals_single(tmp_path):
    """A-FR12/R2-F28: the batch path produces byte-identical ledger entries to N single as-is confirms."""
    _mk(tmp_path, budget="5.00", mode="live", obs="config-default")
    apply_confirm_all(tmp_path, build_confirm_all_plan(tmp_path), timestamp="2026-07-07")
    batch = load_ledger(tmp_path)

    _mk(other := tmp_path.parent / "single", budget="5.00", mode="live", obs="config-default")
    for vp in (_BUDGET, _MODE, _OBS):
        apply_confirm(other, build_confirm_plan(other, vp, mode="as-is", timestamp="2026-07-07"))
    single = load_ledger(other)
    assert batch == single


# --- FR-4 (A-FR4): byte-identity across audiences given the same explicit decisions --------------

def _decide_all_explicitly(tmp_path, audience):
    """Under a given audience, run the pre-pass (a no-op unless Beginner) then EXPLICITLY confirm all
    three fields to the SAME fixed values. Returns (inputs_bytes, ledger_values)."""
    apply_audience_defaults(tmp_path, audience, timestamp="2026-07-01")   # pre-pass (Beginner writes defaults)
    for vp, val in ((_BUDGET, "7.50"), (_MODE, "live"), (_OBS, "authored")):
        apply_confirm(tmp_path, build_confirm_plan(tmp_path, vp, val, mode="set", timestamp="2026-07-07"))
    inputs = tmp_path / "docs" / "kickoff" / "inputs"
    blob = b"".join(sorted((p.name.encode() + p.read_bytes()) for p in inputs.glob("*.yaml")))
    return blob, _ledger_values(tmp_path)


def test_same_explicit_decisions_are_byte_identical_across_audiences(tmp_path):
    """A-FR4: audience is a lens — the SAME explicit decisions yield byte-identical inputs and
    value-identical ledgers, whether or not a Beginner pre-pass ran first (A-FR6b promotion strips)."""
    results = {}
    for audience in ("beginner", "intermediate", "advanced"):
        d = tmp_path / audience
        _mk(d)
        results[audience] = _decide_all_explicitly(d, audience)

    blobs = {a: b for a, (b, _v) in results.items()}
    vals = {a: v for a, (_b, v) in results.items()}
    assert blobs["beginner"] == blobs["intermediate"] == blobs["advanced"]   # inputs byte-identical
    assert vals["beginner"] == vals["intermediate"] == vals["advanced"]      # ledger values identical
    # A-FR6b: the Beginner's promoted entries are indistinguishable from direct-explicit (no provenance)
    for entry in load_ledger(tmp_path / "beginner").values():
        assert "provenance" not in entry
