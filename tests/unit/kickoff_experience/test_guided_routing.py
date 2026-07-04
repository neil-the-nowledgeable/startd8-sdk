"""GE-M0 — the guided-experience routing seam (FR-GE-1/2/3/4).

Covers, as a **semantic contract** that does NOT import ``concierge_agent.py`` (R2-F3/R3-S5):

* tri-state resolution — ``on`` / ``off`` / ``unset`` are distinct (FR-GE-3);
* the critical **force-off is never lost to a falsy fall-through** (R3-F2 / FR-GE-4):
  project ``guided: false`` + global ``guided: true`` ⇒ NO offer; ``--no-guided`` beats config;
* precedence — flag > project > global > default (FR-GE-4);
* the offer is **computed but never forced**, defaults quiet, and is one ignorable line (FR-GE-3);
* byte-identity — a non-offered / non-interactive path emits nothing (FR-GE-1).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.kickoff_experience.guided_routing import (
    GuidedRoutingDecision,
    OfferStrength,
    Tri,
    coerce_tri,
    decide_guided_routing,
    offer_line,
    resolve_guided_preference,
)


def _write_guided(project: Path, value) -> None:
    """Write a project build-preferences.yaml with (or without) a `guided:` key."""
    inputs = project / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    body = "domain: build-preferences\n"
    if value is not None:
        body += f"guided: {value}\n"
    (inputs / "build-preferences.yaml").write_text(body, encoding="utf-8")


# --------------------------------------------------------------------------- tri-state coercion


@pytest.mark.parametrize(
    "value, expected",
    [
        (None, Tri.UNSET),
        (True, Tri.ON),
        (False, Tri.OFF),
        ("on", Tri.ON),
        ("off", Tri.OFF),
        ("true", Tri.ON),
        ("false", Tri.OFF),
        ("", Tri.UNSET),          # empty ⇒ unset, NOT a silent off
        ("garbage", Tri.UNSET),   # unrecognized ⇒ unset, never crashes
    ],
)
def test_coerce_tri_preserves_on_off_unset(value, expected):
    """on/off/unset are three distinct states; unknown/empty degrade to unset, never off."""
    assert coerce_tri(value) is expected


def test_tri_off_is_distinct_from_unset():
    """The load-bearing invariant: OFF ≠ UNSET (the property the string ladder cannot express)."""
    assert coerce_tri(False) is Tri.OFF
    assert coerce_tri(None) is Tri.UNSET
    assert Tri.OFF is not Tri.UNSET


# --------------------------------------------------------------------------- precedence ladder


def test_default_layer_when_nothing_set(tmp_path):
    """No flag, no project, no global ⇒ default/UNSET."""
    res = resolve_guided_preference(tmp_path, None)
    assert (res.value, res.source) == (Tri.UNSET, "default")


def test_flag_on_wins_over_everything(tmp_path, monkeypatch):
    """--guided beats project + global (top of precedence, FR-GE-4)."""
    _write_guided(tmp_path, "false")
    import startd8.kickoff_experience.guided_routing as mod

    monkeypatch.setattr(mod, "_global_guided", lambda: Tri.OFF)
    res = resolve_guided_preference(tmp_path, True)
    assert (res.value, res.source) == (Tri.ON, "flag")


def test_project_layer_used_when_no_flag(tmp_path):
    """Project build-preferences.yaml `guided:` is read live when no flag (FR-GE-3)."""
    _write_guided(tmp_path, "true")
    res = resolve_guided_preference(tmp_path, None)
    assert (res.value, res.source) == (Tri.ON, "project")


def test_global_layer_used_when_no_flag_no_project(tmp_path, monkeypatch):
    """Global ~/.startd8 preference applies when no flag and no project value."""
    import startd8.kickoff_experience.guided_routing as mod

    monkeypatch.setattr(mod, "_global_guided", lambda: Tri.ON)
    res = resolve_guided_preference(tmp_path, None)
    assert (res.value, res.source) == (Tri.ON, "global")


def test_malformed_project_prefs_skip_not_crash(tmp_path):
    """A malformed build-preferences.yaml degrades to the next layer, never raises."""
    inputs = tmp_path / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    (inputs / "build-preferences.yaml").write_text(
        "domain: build-preferences\nbogus_top_key: 1\n", encoding="utf-8"
    )
    res = resolve_guided_preference(tmp_path, None)
    assert res.value is Tri.UNSET  # skipped the bad layer, fell through to default


def test_guided_must_be_bool_in_prefs(tmp_path):
    """A non-bool `guided:` in build-preferences.yaml is a loud parse error (skipped by resolver)."""
    from startd8.kickoff_inputs import parse_build_preferences

    with pytest.raises(ValueError):
        parse_build_preferences("domain: build-preferences\nguided: maybe\n")
    # ...and the resolver swallows it, degrading to UNSET (never crashes the CLI).
    _write_guided(tmp_path, "maybe")
    assert resolve_guided_preference(tmp_path, None).value is Tri.UNSET


# ------------------------------------------------- CRITICAL: force-off never lost to fall-through


def test_force_off_project_beats_global_on(tmp_path, monkeypatch):
    """R3-F2/FR-GE-4: project `guided: false` + global `guided: true` ⇒ resolution TERMINATES at OFF.

    The exact failure a naive string-ladder reuse would cause: a falsy project layer being skipped,
    falling through to the global `true`. Here OFF must win.
    """
    _write_guided(tmp_path, "false")
    import startd8.kickoff_experience.guided_routing as mod

    monkeypatch.setattr(mod, "_global_guided", lambda: Tri.ON)
    res = resolve_guided_preference(tmp_path, None)
    assert (res.value, res.source) == (Tri.OFF, "project")


def test_no_guided_flag_beats_config_true(tmp_path, monkeypatch):
    """--no-guided (flag=False) beats any config `true` at project or global (FR-GE-4)."""
    _write_guided(tmp_path, "true")
    import startd8.kickoff_experience.guided_routing as mod

    monkeypatch.setattr(mod, "_global_guided", lambda: Tri.ON)
    res = resolve_guided_preference(tmp_path, False)
    assert (res.value, res.source) == (Tri.OFF, "flag")


def test_force_off_project_yields_no_offer_over_global_on(tmp_path, monkeypatch):
    """End-to-end: force-off must produce NO offer even with a global `on` beneath it."""
    _write_guided(tmp_path, "false")
    import startd8.kickoff_experience.guided_routing as mod

    monkeypatch.setattr(mod, "_global_guided", lambda: Tri.ON)
    decision = decide_guided_routing(tmp_path, served_surface=True, interactive=True)
    assert decision.offer is OfferStrength.NONE
    assert offer_line(decision) is None


# --------------------------------------------------------------------------- routing signals / offer


def _assess_payload(*present_domains: str, blank: bool = False):
    """Minimal build_assess-shaped payload for the project-shape signal."""
    domains = {"stakeholders": {"status": "absent"}, "value": {"status": "absent"}}
    for d in present_domains:
        domains[d] = {"status": "present"}
    return {"kickoff_inputs": {"domains": domains}}


def test_explicit_on_offers_strong_and_engages(tmp_path):
    """Explicit force-on ⇒ STRONG offer + engaged (signal 1 authoritative)."""
    decision = decide_guided_routing(tmp_path, flag=True, interactive=True)
    assert decision.offer is OfferStrength.STRONG
    assert decision.engaged is True


def test_served_surface_offers_quietly_when_not_blank(tmp_path):
    """Signal 2 (served surface) ⇒ a QUIET offer for a non-blank project; never engaged by a signal."""
    decision = decide_guided_routing(
        tmp_path, served_surface=True, assess=_assess_payload("stakeholders"), interactive=True
    )
    assert decision.offer is OfferStrength.QUIET
    assert decision.engaged is False  # an offer is NOT engagement (never forced)


def test_greenfield_blank_offers_quietly(tmp_path):
    """Signal 3 (project-shape): a greenfield-blank project ⇒ a QUIET offer even without a surface."""
    decision = decide_guided_routing(tmp_path, assess=_assess_payload(), interactive=True)
    assert decision.offer is OfferStrength.QUIET


def test_served_surface_plus_blank_strengthens_offer(tmp_path):
    """Served surface + greenfield-blank ⇒ STRONG (signals compose), still not engaged."""
    decision = decide_guided_routing(
        tmp_path, served_surface=True, assess=_assess_payload(), interactive=True
    )
    assert decision.offer is OfferStrength.STRONG
    assert decision.engaged is False


def test_no_signal_no_offer(tmp_path):
    """No preference, no surface, brownfield project ⇒ NO offer (default bias quiet, FR-GE-1)."""
    decision = decide_guided_routing(
        tmp_path, assess=_assess_payload("stakeholders", "value"), interactive=True
    )
    assert decision.offer is OfferStrength.NONE
    assert offer_line(decision) is None


def test_offer_is_never_a_gate(tmp_path):
    """The decision surfaces only an *offer strength* + a courtesy line — never a forced path.

    `engaged` is True ONLY on explicit force-on; no soft signal ever engages the flow (FR-GE-2/3).
    """
    for kwargs in (
        {"served_surface": True, "assess": _assess_payload()},
        {"assess": _assess_payload()},
        {"served_surface": True, "assess": _assess_payload("stakeholders")},
    ):
        decision = decide_guided_routing(tmp_path, interactive=True, **kwargs)
        assert decision.engaged is False


# --------------------------------------------------------------------------- byte-identity (FR-GE-1)


def test_non_interactive_suppresses_offer_line(tmp_path):
    """Piped/CI (interactive=False) ⇒ the offer line is suppressed, never blocking (FR-GE-1)."""
    decision = decide_guided_routing(
        tmp_path, served_surface=True, assess=_assess_payload(), interactive=False
    )
    assert decision.offer is OfferStrength.NONE
    assert offer_line(decision) is None


def test_non_interactive_forced_on_still_engages_but_no_line(tmp_path):
    """Non-interactive + --guided ⇒ still engages the flow, but emits no offer prose (kernel bytes)."""
    decision = decide_guided_routing(tmp_path, flag=True, interactive=False)
    assert decision.offer is OfferStrength.NONE   # no line
    assert decision.engaged is True               # but force-on honored
    assert offer_line(decision) is None


def test_offer_line_is_one_line(tmp_path):
    """When an offer surfaces, it is exactly ONE ignorable line (FR-GE-3)."""
    decision = decide_guided_routing(tmp_path, flag=True, interactive=True)
    line = offer_line(decision)
    assert line is not None
    assert "\n" not in line
