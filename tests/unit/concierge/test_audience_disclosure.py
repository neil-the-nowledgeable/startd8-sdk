# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Kickoff-audience M4 — disclosure tiers (FR-9/FR-10).

The NR-1 drift-risk gate: the single-source tier loader (compose with ``section=``, degrade-to-light,
and — the concrete R3-F30(b) bug — the Beginner PLAIN prose must NEVER leak into a light/full render),
plus the audience→tier map and the Advanced per-field suppression (FR-10).
"""

from __future__ import annotations

import pytest

from startd8.concierge import audience as aud
from startd8.concierge.audience import AudienceResolution, KickoffAudience, disclosure_tier
from startd8.concierge import writes as w
from startd8.concierge.writes import DISCLOSURE_TIERS, load_experience_doc
from startd8.concierge.confirm_walk import field_prompt_lines, run_confirm_walk

# Anchors unique to each region of KICKOFF_EXPERIENCE_INTRO.md:
_BODY_ONLY = 'What "kickoff" is'                 # a light-body heading
_TLDR_ONLY = "Start here"                        # in the TL;DR slice
_PLAIN_ONLY = "You can't break anything here"    # in the PLAIN (expanded) region only
_BANNER_ONLY = "Machines draft; you decide"      # in the BANNER slice


# --- the tier loader (A-FR9b) --------------------------------------------------------------------

def test_light_is_full_body_without_plain_or_markers():
    out = load_experience_doc("intro", tier="light")
    assert _BODY_ONLY in out
    assert _PLAIN_ONLY not in out          # R3-F30(b): beginner prose must not leak into light
    assert "<!--" not in out               # no marker survives


def test_compact_is_tldr():
    out = load_experience_doc("intro", tier="compact")
    assert _TLDR_ONLY in out
    assert _PLAIN_ONLY not in out


def test_expanded_is_plain():
    out = load_experience_doc("intro", tier="expanded")
    assert _PLAIN_ONLY in out
    assert "<!--" not in out


def test_no_leak_plain_absent_from_every_non_expanded_render():
    """R3-F30(b) — THE gate: the PLAIN region appears ONLY at tier=expanded."""
    for tier in ("compact", "light"):
        assert _PLAIN_ONLY not in load_experience_doc("intro", tier=tier)
    # and the markers themselves never survive any render (no HTML-comment marker leaks)
    for tier in DISCLOSURE_TIERS:
        assert "<!--" not in load_experience_doc("intro", tier=tier)


def test_section_banner_composes_with_tier():
    """R3-F30(a): a banner is a SECTION, not a tier — returned regardless of tier, no leak."""
    for tier in DISCLOSURE_TIERS:
        out = load_experience_doc("intro", tier=tier, section="banner")
        assert _BANNER_ONLY in out
        assert _PLAIN_ONLY not in out


def test_compact_back_compat_alias():
    assert load_experience_doc("intro", compact=True) == load_experience_doc("intro", tier="compact")
    assert load_experience_doc("intro", compact=False) == load_experience_doc("intro", tier="light")


def test_unknown_tier_raises():
    with pytest.raises(Exception):
        load_experience_doc("intro", tier="verbose")


def test_expanded_degrades_to_light_when_plain_absent(monkeypatch):
    """A-FR9b(c) fail-closed: a doc with no PLAIN region degrades expanded → light (never raw)."""
    monkeypatch.setattr(w, "_load_template", lambda _rel: "# Just the body\nno markers here\n")
    out = load_experience_doc("intro", tier="expanded")
    assert out == "# Just the body\nno markers here"


# --- audience → tier map -------------------------------------------------------------------------

@pytest.mark.parametrize("audience,tier", [
    (KickoffAudience.BEGINNER, "expanded"),
    (KickoffAudience.INTERMEDIATE, "light"),
    (KickoffAudience.ADVANCED, "compact"),
    ("beginner", "expanded"),
    (None, "light"),   # unset → default (Intermediate) → light (byte-identical)
])
def test_disclosure_tier_map(audience, tier):
    assert disclosure_tier(audience) == tier


# --- FR-10 Advanced suppression ------------------------------------------------------------------

_FIELD = {
    "value_path": "business-targets.yaml#/monetization.mode_now",
    "label": "Monetization mode (now)",
    "domain": "business-targets",
    "widget": "select",
    "choices": ["free-during-demo", "live"],
}


def test_field_prompt_lines_default_shows_why_and_grammar(tmp_path):
    lines = field_prompt_lines(tmp_path, _FIELD, None, {})
    assert any(ln.strip().startswith("why:") for ln in lines)
    assert any("choices:" in ln for ln in lines)


def test_field_prompt_lines_terse_suppresses_why_and_grammar(tmp_path):
    lines = field_prompt_lines(tmp_path, _FIELD, None, {}, terse=True)
    assert not any(ln.strip().startswith("why:") for ln in lines)
    assert any("choices:" in ln for ln in lines)   # choices kept — the valid-value contract
    assert lines[0].startswith("Monetization mode")


def _mk_instantiated(tmp_path):
    inputs = tmp_path / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True)
    (inputs / "build-preferences.yaml").write_text(
        "provenance_default: estimate\nbudgets:\n  per_pipeline_run: \"10\"\n", encoding="utf-8")
    (inputs / "business-targets.yaml").write_text(
        "provenance_default: estimate\nmonetization:\n  mode_now: live\n", encoding="utf-8")
    (inputs / "observability.yaml").write_text("provenance_default: authored\n", encoding="utf-8")


def _force_audience(monkeypatch, a):
    monkeypatch.setattr(aud, "resolve_audience_preference", lambda *_a, **_k: AudienceResolution(a, "test"))


def test_walk_advanced_is_terse(tmp_path, monkeypatch):
    _mk_instantiated(tmp_path)
    _force_audience(monkeypatch, KickoffAudience.ADVANCED)
    lines = []
    run_confirm_walk(tmp_path, read_input=lambda _p: None, emit_line=lines.append, timestamp="2026-07-07")
    assert not any(ln.strip().startswith("why:") for ln in lines)   # Advanced: no scaffolding


def test_walk_intermediate_shows_why(tmp_path, monkeypatch):
    _mk_instantiated(tmp_path)
    _force_audience(monkeypatch, KickoffAudience.INTERMEDIATE)
    lines = []
    run_confirm_walk(tmp_path, read_input=lambda _p: None, emit_line=lines.append, timestamp="2026-07-07")
    assert any(ln.strip().startswith("why:") for ln in lines)       # Intermediate: full scaffolding


# --- the workbook intro doc (WORKBOOK_AUDIENCE_PERSONALIZATION Slice A) --------------------------

_WORKBOOK_NARRATIVE = (
    "The **Digital Project Workbook** — the shared, whole-project view of the foundational kickoff "
    "decisions. A dynamic, query-based evolution of Brooks' workbook (_The Mythical Man-Month_), "
    "which was static (paper/microfiche); this one is generated from live project state. State is "
    "the canonical `KickoffState` (the same `$0` extraction the web UI and TUI use) — projected into "
    "these panels. Re-run `startd8 kickoff portal` to refresh."
)


def test_workbook_light_is_byte_identical_to_legacy_narrative():
    # FR-2: the Intermediate/light render MUST equal today's inline narrative byte-for-byte.
    assert load_experience_doc("workbook", tier="light") == _WORKBOOK_NARRATIVE


def test_workbook_expanded_slices_the_plain_beginner_rewrite():
    # FR-2 marker-slice guard (R1-S5): expanded really differs from light (not a silent degrade-to-light).
    expanded = load_experience_doc("workbook", tier="expanded")
    light = load_experience_doc("workbook", tier="light")
    assert expanded != light
    assert "Your Project Workbook" in expanded
    assert "🛡️" in expanded              # the Beginner rewrite explains the safe-default badge
    assert "<!--" not in expanded         # no marker leakage


def test_workbook_compact_degrades_to_light_by_design():
    # No TL;DR region (byte-identity constraint) → compact degrades to light (Advanced == Intermediate).
    assert load_experience_doc("workbook", tier="compact") == load_experience_doc("workbook", tier="light")
