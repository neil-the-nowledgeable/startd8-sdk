# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Kickoff-audience M2 (FR-6/FR-13) — ledger provenance + the ``audience_defaulted`` count bucket.

Covers the post-CRP hardening: conditional ``v1→v2`` bump (A-FR6d), explicit-promotion strips
provenance (A-FR6b), the bucket partition + stale overlay (A-FR13b), the no-display-regression
guarantee (A-FR13 / ``test_assess_no_audience_regression``), and v1 backward-compat load (A-FR6).
"""

from __future__ import annotations

import yaml

from startd8.concierge.confirmation import (
    AUDIENCE_DEFAULT_PREFIX,
    LEDGER_REL,
    LEDGER_SCHEMA,
    LEDGER_SCHEMA_V2,
    _dump_ledger,
    apply_confirm,
    audience_default_provenance,
    build_confirm_plan,
    domain_confirmation,
    load_ledger,
)

_BUILD_PREFS = "provenance_default: estimate\nbudgets:\n  per_pipeline_run: \"10\"\n"
_BIZ = "provenance_default: estimate\nmonetization:\n  mode_now: pre-revenue\n"
_BUDGET = "build-preferences.yaml#/budgets.per_pipeline_run"
_MODE = "business-targets.yaml#/monetization.mode_now"
_BEGINNER = audience_default_provenance("beginner")


def _mk_project(tmp_path):
    inputs = tmp_path / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True)
    (inputs / "build-preferences.yaml").write_text(_BUILD_PREFS, encoding="utf-8")
    (inputs / "business-targets.yaml").write_text(_BIZ, encoding="utf-8")
    return tmp_path


def _confirm(tmp_path, vp, *, value=None, mode="set", provenance=None, at="2026-07-06"):
    plan = build_confirm_plan(tmp_path, vp, value, mode=mode, timestamp=at, provenance=provenance)
    apply_confirm(tmp_path, plan)
    return plan


# --- A-FR6d: conditional schema bump -------------------------------------------------------------

def test_all_explicit_ledger_stays_v1_byte_identical(tmp_path):
    _mk_project(tmp_path)
    _confirm(tmp_path, _BUDGET, value="5.00")
    _confirm(tmp_path, _MODE, mode="as-is")
    ledger = load_ledger(tmp_path)
    dumped = _dump_ledger(ledger)
    # byte-for-byte the pre-audience v1 dump (no schema-line churn for a non-audience user)
    expected = yaml.safe_dump(
        {"schema": LEDGER_SCHEMA, "confirmed": ledger}, sort_keys=True, allow_unicode=True
    )
    assert dumped == expected
    assert "kickoff.confirmed.v1" in dumped
    assert LEDGER_SCHEMA_V2 not in dumped


def test_audience_default_entry_bumps_to_v2(tmp_path):
    _mk_project(tmp_path)
    _confirm(tmp_path, _BUDGET, value="5.00", provenance=_BEGINNER)
    text = (tmp_path / LEDGER_REL).read_text(encoding="utf-8")
    assert LEDGER_SCHEMA_V2 in text
    assert "kickoff.confirmed.v1" not in text


# --- FR-6 + A-FR6b: provenance stamping / stripping ----------------------------------------------

def test_explicit_confirm_writes_no_provenance(tmp_path):
    _mk_project(tmp_path)
    _confirm(tmp_path, _BUDGET, value="5.00")
    entry = load_ledger(tmp_path)[_BUDGET]
    assert "provenance" not in entry


def test_machine_confirm_stamps_provenance(tmp_path):
    _mk_project(tmp_path)
    plan = _confirm(tmp_path, _BUDGET, value="5.00", provenance=_BEGINNER)
    assert plan.provenance == _BEGINNER
    entry = load_ledger(tmp_path)[_BUDGET]
    assert entry["provenance"] == _BEGINNER
    assert entry["provenance"].startswith(AUDIENCE_DEFAULT_PREFIX)


def test_explicit_promotion_strips_provenance(tmp_path):
    """A-FR6b: promoting an audience-default via `kickoff confirm` (explicit) drops the provenance,
    so the entry becomes indistinguishable from a direct human confirmation — and the schema reverts."""
    _mk_project(tmp_path)
    _confirm(tmp_path, _BUDGET, value="5.00", provenance=_BEGINNER)   # machine default
    assert "provenance" in load_ledger(tmp_path)[_BUDGET]
    _confirm(tmp_path, _BUDGET, mode="as-is")                        # human promotes it
    entry = load_ledger(tmp_path)[_BUDGET]
    assert "provenance" not in entry
    # with no audience-default left, the ledger reverts to v1
    assert "kickoff.confirmed.v1" in (tmp_path / LEDGER_REL).read_text(encoding="utf-8")


# --- A-FR13 / A-FR13b: the audience_defaulted bucket ---------------------------------------------

def test_audience_default_counts_in_its_own_bucket_not_confirmed(tmp_path):
    _mk_project(tmp_path)
    _confirm(tmp_path, _BUDGET, value="5.00", provenance=_BEGINNER)
    bp = domain_confirmation(tmp_path)["build-preferences"]
    assert bp.get("audience_defaulted") == 1
    assert bp["confirmed"] == 0                      # NOT counted as a human confirmation


def test_buckets_partition_the_confirmable_set(tmp_path):
    """A-FR13b: confirmed + awaiting + audience_defaulted == confirmable, per domain (no double-count)."""
    _mk_project(tmp_path)
    _confirm(tmp_path, _BUDGET, value="5.00", provenance=_BEGINNER)   # audience-default
    _confirm(tmp_path, _MODE, mode="as-is")                          # explicit
    conf = domain_confirmation(tmp_path)
    for counts in conf.values():
        partition = counts["confirmed"] + counts["awaiting"] + counts.get("audience_defaulted", 0)
        assert partition == counts["confirmable"]


def test_assess_no_audience_regression(tmp_path):
    """A-FR13 / R2-F26: with NO audience-default entries, the `audience_defaulted` key is omitted
    entirely — the returned shape is byte-identical to the pre-audience behavior."""
    _mk_project(tmp_path)
    _confirm(tmp_path, _BUDGET, value="5.00")   # explicit only
    conf = domain_confirmation(tmp_path)
    for counts in conf.values():
        assert "audience_defaulted" not in counts
        assert set(counts) == {"confirmable", "confirmed", "awaiting", "stale"}


def test_audience_default_stale_is_overlay_not_double_counted(tmp_path):
    """A-FR13b: an audience-default whose on-disk value diverged is audience_defaulted AND stale,
    but the partition (which excludes stale) is unaffected."""
    _mk_project(tmp_path)
    _confirm(tmp_path, _BUDGET, value="5.00", provenance=_BEGINNER)
    # hand-edit the input so on-disk diverges from the recorded value
    p = tmp_path / "docs/kickoff/inputs/build-preferences.yaml"
    p.write_text("provenance_default: estimate\nbudgets:\n  per_pipeline_run: \"9.99\"\n", encoding="utf-8")
    bp = domain_confirmation(tmp_path)["build-preferences"]
    assert bp.get("audience_defaulted") == 1
    assert bp["stale"] == 1
    assert bp["confirmed"] == 0
    assert bp["confirmed"] + bp["awaiting"] + bp["audience_defaulted"] == bp["confirmable"]


# --- A-FR6: backward compat — a v1 ledger loads as explicit --------------------------------------

def test_v1_ledger_loads_as_explicit_confirmed(tmp_path):
    """A v1 ledger on disk (entries with no `provenance`) is treated as explicit — counted as
    confirmed, never audience_defaulted — and no bucket key appears."""
    _mk_project(tmp_path)
    (tmp_path / "docs" / "kickoff").mkdir(parents=True, exist_ok=True)
    (tmp_path / LEDGER_REL).write_text(
        "schema: kickoff.confirmed.v1\n"
        "confirmed:\n"
        f"  {_BUDGET}:\n"
        "    value: '5.00'\n"
        "    at: '2026-07-01'\n"
        "    mode: set\n",
        encoding="utf-8",
    )
    bp = domain_confirmation(tmp_path)["build-preferences"]
    assert bp["confirmed"] == 1
    assert "audience_defaulted" not in bp
