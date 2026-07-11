# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Kickoff-audience M3 — profiles + the walk-start surface pre-pass (FR-5/7/8/11).

Covers the shieldability gate (A-OQ9) + lint coverage, and the pre-pass invariants: always-tagged
(A-FR6c), unledgered-only (FR-5), idempotent (R2-S21), fail-closed vs the present-file gate (A-FR11b),
plus the Beginner reduced-surface / Intermediate byte-identical walk integration.
"""

from __future__ import annotations

from startd8.concierge import audience as aud
from startd8.concierge.audience import (
    AudienceResolution,
    KickoffAudience,
    apply_audience_defaults,
)
from startd8.concierge.confirmation import (
    _CONFIRMABLE_PROVENANCE as CONF_PROV,
    audience_default_provenance,
    build_confirm_plan,
    apply_confirm,
    domain_confirmation,
    load_ledger,
)
from startd8.concierge.confirm_walk import run_confirm_walk
from startd8.kickoff_experience import manifest as mf
from startd8.kickoff_experience.manifest import (
    AUDIENCE_PROFILES,
    SHIELDABLE_VALUE_PATHS,
    audience_defaults,
    default_config,
    lint_config,
)

_BUDGET = "build-preferences.yaml#/budgets.per_pipeline_run"
_MODE = "business-targets.yaml#/monetization.mode_now"
_OBS = "observability.yaml#/provenance_default"
_BEGINNER_PROV = audience_default_provenance("beginner")


def _mk_instantiated(tmp_path, *, audience_line: str = "") -> None:
    """A fully-instantiated project: the 3 input files holding the shieldable target keys."""
    inputs = tmp_path / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True)
    (inputs / "build-preferences.yaml").write_text(
        f"provenance_default: estimate\n{audience_line}budgets:\n  per_pipeline_run: \"10\"\n",
        encoding="utf-8",
    )
    (inputs / "business-targets.yaml").write_text(
        "provenance_default: estimate\nmonetization:\n  mode_now: live\n", encoding="utf-8"
    )
    (inputs / "observability.yaml").write_text("provenance_default: authored\n", encoding="utf-8")


# --- profiles + shieldability (FR-7/FR-8, A-OQ9) -------------------------------------------------

def test_default_profiles_lint_clean():
    assert lint_config(default_config()) == []


def test_confirmable_provenance_matches_confirmation_module():
    from startd8.concierge.confirmation import _CONFIRMABLE_PROVENANCE
    assert CONF_PROV == _CONFIRMABLE_PROVENANCE  # drift guard (dup literal in two modules)


def test_shieldable_are_all_confirmable():
    confirmable = {
        f.value_path for f in default_config().writable_fields()
        if f.provenance_default in CONF_PROV
    }
    assert SHIELDABLE_VALUE_PATHS <= confirmable


def test_audience_defaults_partial():
    assert set(audience_defaults("beginner")) == {_BUDGET, _MODE, _OBS}
    assert audience_defaults("intermediate") == {}
    assert audience_defaults("advanced") == {}
    assert audience_defaults("unknown") == {}


def test_lint_rejects_unshieldable_profile(monkeypatch):
    # 'conventions.yaml#/language' is an AUTHORED field — not confirmable, not shieldable.
    bad = dict(AUDIENCE_PROFILES)
    bad["beginner"] = {"conventions.yaml#/language": "python"}
    monkeypatch.setattr(mf, "AUDIENCE_PROFILES", bad)
    codes = {i.code for i in lint_config(default_config())}
    assert "profile_not_shieldable" in codes
    assert "profile_not_confirmable" in codes


def test_lint_rejects_bad_choice_value(monkeypatch):
    bad = dict(AUDIENCE_PROFILES)
    bad["beginner"] = {_MODE: "not-a-choice"}
    monkeypatch.setattr(mf, "AUDIENCE_PROFILES", bad)
    codes = {i.code for i in lint_config(default_config())}
    assert "profile_bad_value" in codes


def test_lint_rejects_unknown_value_path(monkeypatch):
    bad = dict(AUDIENCE_PROFILES)
    bad["beginner"] = {"business-targets.yaml#/nope.gone": "x"}
    monkeypatch.setattr(mf, "AUDIENCE_PROFILES", bad)
    codes = {i.code for i in lint_config(default_config())}
    assert "profile_unknown_field" in codes


# --- pre-pass invariants -------------------------------------------------------------------------

def test_prepass_intermediate_is_noop(tmp_path):
    _mk_instantiated(tmp_path)
    res = apply_audience_defaults(tmp_path, "intermediate")
    assert res.ran is False
    assert res.written == () and load_ledger(tmp_path) == {}


def test_prepass_beginner_shields_all_and_tags(tmp_path):
    """FR-11 + A-FR6c: shields every shieldable field, each stamped audience-default:<slug>."""
    _mk_instantiated(tmp_path)
    res = apply_audience_defaults(tmp_path, "beginner", timestamp="2026-07-06")
    assert res.ran is True and res.blocked is False
    assert set(res.written) == {_BUDGET, _MODE, _OBS}
    ledger = load_ledger(tmp_path)
    # A-FR6c: EVERY written entry is provenance-tagged (never an untagged/explicit write)
    for vp in res.written:
        assert ledger[vp]["provenance"] == _BEGINNER_PROV
    bp = domain_confirmation(tmp_path)["build-preferences"]
    assert bp.get("audience_defaulted") == 1 and bp["confirmed"] == 0


def test_prepass_writes_are_provenance_tagged(tmp_path):
    """A-FR6c (R3-F31) — the named write-path invariant gate: the pre-pass NEVER writes an untagged
    (would-be-explicit) ledger entry. Every entry it lands carries an ``audience-default:*``
    provenance; and at the source level, ``apply_audience_defaults`` always passes ``provenance=``."""
    import inspect
    _mk_instantiated(tmp_path)
    res = apply_audience_defaults(tmp_path, "beginner", timestamp="2026-07-06")
    ledger = load_ledger(tmp_path)
    # runtime: every field the pre-pass wrote is tagged (none untagged)
    assert res.written, "expected the pre-pass to write at least one field"
    for vp in res.written:
        prov = ledger[vp].get("provenance")
        assert isinstance(prov, str) and prov.startswith("audience-default:"), (vp, ledger[vp])
    # source-level invariant: the pre-pass never calls the writer without a provenance= argument
    src = inspect.getsource(apply_audience_defaults)
    assert "provenance=audience_default_provenance" in src
    assert "build_confirm_plan(" in src and "provenance=" in src


def test_prepass_unledgered_only_never_overrides_explicit(tmp_path):
    """FR-5: a field the user already confirmed explicitly is left untouched."""
    _mk_instantiated(tmp_path)
    apply_confirm(tmp_path, build_confirm_plan(tmp_path, _MODE, mode="as-is", timestamp="2026-07-01"))
    res = apply_audience_defaults(tmp_path, "beginner", timestamp="2026-07-06")
    assert _MODE in res.skipped_ledgered and _MODE not in res.written
    entry = load_ledger(tmp_path)[_MODE]
    assert "provenance" not in entry           # still an explicit confirmation
    assert entry["at"] == "2026-07-01"         # untouched


def test_prepass_idempotent_second_run_writes_nothing(tmp_path):
    """R2-S21: a second pre-pass writes nothing and never re-bumps an existing `at`."""
    _mk_instantiated(tmp_path)
    apply_audience_defaults(tmp_path, "beginner", timestamp="2026-07-06")
    ats = {vp: e["at"] for vp, e in load_ledger(tmp_path).items()}
    res2 = apply_audience_defaults(tmp_path, "beginner", timestamp="2026-07-09")   # later stamp
    assert res2.written == ()
    assert set(res2.skipped_ledgered) == {_BUDGET, _MODE, _OBS}
    assert {vp: e["at"] for vp, e in load_ledger(tmp_path).items()} == ats   # no re-bump


def test_prepass_fail_closed_on_uninstantiated(tmp_path):
    """A-FR11b: no input files ⇒ blocked, NOTHING written (never silently full-surface)."""
    (tmp_path / "docs" / "kickoff" / "inputs").mkdir(parents=True)  # empty — no input YAMLs
    res = apply_audience_defaults(tmp_path, "beginner")
    assert res.blocked is True
    assert set(res.blocked_missing_inputs) == {_BUDGET, _MODE, _OBS}
    assert load_ledger(tmp_path) == {}   # zero partial writes


def test_prepass_fail_closed_on_write_error(tmp_path, monkeypatch):
    """Reliability: a present-file that still fails to write (keyless/partial input → ConfirmError) is
    reported as blocked, NOT crashed into the walk — fail-closed even when the write itself throws."""
    import startd8.concierge.confirmation as conf
    _mk_instantiated(tmp_path)
    real = conf.build_confirm_plan

    def flaky(project_root, vp, *a, **k):
        if vp == _OBS:
            raise conf.ConfirmError("capture_failed", "boom")
        return real(project_root, vp, *a, **k)

    monkeypatch.setattr(conf, "build_confirm_plan", flaky)
    res = apply_audience_defaults(tmp_path, "beginner", timestamp="2026-07-06")   # must NOT raise
    assert res.ran is True
    assert _OBS in res.blocked_missing_inputs   # the failed field is surfaced, not silently dropped


def test_prepass_fail_closed_on_partial_project(tmp_path):
    """A-FR11b: even one missing input blocks the whole pre-pass (no partial shield)."""
    inputs = tmp_path / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True)
    (inputs / "build-preferences.yaml").write_text(
        "provenance_default: estimate\nbudgets:\n  per_pipeline_run: \"10\"\n", encoding="utf-8"
    )
    # business-targets.yaml + observability.yaml absent
    res = apply_audience_defaults(tmp_path, "beginner")
    assert res.blocked is True
    assert load_ledger(tmp_path) == {}


# --- walk integration ----------------------------------------------------------------------------

def _force_audience(monkeypatch, a: KickoffAudience):
    monkeypatch.setattr(aud, "resolve_audience_preference", lambda *_a, **_k: AudienceResolution(a, "test"))


def _walk(tmp_path, script):
    out_lines = []
    it = iter(script)
    return run_confirm_walk(
        tmp_path,
        read_input=lambda _p: next(it, None),
        emit_line=out_lines.append,
        timestamp="2026-07-06",
    ), out_lines


def test_walk_beginner_reduced_surface(tmp_path, monkeypatch):
    _mk_instantiated(tmp_path)
    _force_audience(monkeypatch, KickoffAudience.BEGINNER)
    summary, lines = _walk(tmp_path, [])   # reader never needed — nothing left to ask
    assert summary["confirmed"] == [] and summary["remaining"] == 0
    assert any("set up 3 things for you" in ln for ln in lines)   # FR-15 reassurance moment
    # the shielded fields are ledgered as audience-defaults (reduced-but-WRITTEN, never dropped)
    ledger = load_ledger(tmp_path)
    assert {_BUDGET, _MODE, _OBS} <= set(ledger)


def test_walk_intermediate_byte_identical(tmp_path, monkeypatch):
    _mk_instantiated(tmp_path)
    _force_audience(monkeypatch, KickoffAudience.INTERMEDIATE)
    summary, lines = _walk(tmp_path, [None])   # quit immediately
    assert not any("pre-filled" in ln for ln in lines)   # no pre-pass side effect
    assert load_ledger(tmp_path) == {}                    # nothing written
    assert "blocked" not in summary


def test_walk_blocked_on_uninstantiated_beginner(tmp_path, monkeypatch):
    (tmp_path / "docs" / "kickoff" / "inputs").mkdir(parents=True)
    _force_audience(monkeypatch, KickoffAudience.BEGINNER)
    summary, lines = _walk(tmp_path, [])
    assert summary.get("blocked") is True
    assert any("kickoff instantiate" in ln for ln in lines)
    assert load_ledger(tmp_path) == {}
