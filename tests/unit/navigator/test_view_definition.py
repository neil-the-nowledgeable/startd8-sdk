"""View Definition + cascade resolver (REQ-10) — the presentation twin of NODE-SCHEMA.

Covers the seven FRs. The keystone acceptance is FR-5 + FR-6 together: a base design change propagates
atomically to two domains that share it, while each keeps its overrides.
"""
from __future__ import annotations

import copy
import json
from dataclasses import replace

import pytest

from startd8.navigator.sources_capability import CAPABILITY_PROFILE
from startd8.navigator.sources_requirements import REQUIREMENTS_PROFILE
from startd8.navigator.view_definition import (
    BASE_NAVIG8R_DEFINITION,
    CAPABILITY_DEFINITION,
    DEFINITION_REGISTRY,
    REQUIREMENTS_DEFINITION,
    ResolvedDefinition,
    ViewDefinition,
    resolve,
    to_render_profile,
)
from startd8.wireframe.profile import RenderProfile, StatusStyle


# ── FR-1 — ViewDefinition model: serializable, keyed collections, JSON round-trip ────────────────

def test_view_definition_round_trips_through_json():
    d = ViewDefinition(
        name="demo",
        extends="base",
        theme={"accent": "#123456"},
        vocabulary={"gap_noun": "thing", "statuses": {"ok": {"label": "OK", "color": "#0a0"}}},
        chrome={"title": "Demo"},
    )
    # dict round-trip
    assert ViewDefinition.from_dict(d.to_dict()) == d
    # JSON round-trip (the cross-repo VIEW-SCHEMA seam — NR-4)
    assert ViewDefinition.from_dict(json.loads(json.dumps(d.to_dict()))) == d


def test_overridable_collections_are_keyed_maps_not_positional_lists():
    # statuses is a dict keyed by status id, never a positional list.
    assert isinstance(REQUIREMENTS_DEFINITION.vocabulary["statuses"], dict)
    assert "grounded" in REQUIREMENTS_DEFINITION.vocabulary["statuses"]
    assert isinstance(CAPABILITY_DEFINITION.vocabulary["statuses"], dict)


# ── FR-2 — Cascade resolver: deep-merge, per-leaf, keyed-by-id ───────────────────────────────────

def test_resolve_merges_per_leaf_key():
    # capability overrides theme.accent; it must still inherit the base theme.ink (per-leaf, atomic).
    resolved = resolve(CAPABILITY_DEFINITION, DEFINITION_REGISTRY)
    assert resolved.theme["accent"] == "#3a6a94"                         # domain override wins
    assert resolved.theme["ink"] == BASE_NAVIG8R_DEFINITION.theme["ink"]  # base sibling inherited


def test_resolve_merges_keyed_collections_by_id_not_positional():
    base = ViewDefinition(
        name="kbase",
        vocabulary={"statuses": {
            "a": {"label": "A", "color": "#111", "meaning": "aa"},
            "b": {"label": "B", "color": "#222", "meaning": "bb"},
        }},
    )
    child = ViewDefinition(
        name="kchild",
        extends="kbase",
        vocabulary={"statuses": {"a": {"color": "#999"}}},  # override ONE leaf of ONE entry
    )
    reg = {"kbase": base, "kchild": child}
    resolved = resolve(child, reg)
    statuses = resolved.vocabulary["statuses"]
    assert statuses["a"]["color"] == "#999"      # overridden leaf wins
    assert statuses["a"]["label"] == "A"         # sibling leaf of the same entry preserved
    assert statuses["b"] == {"label": "B", "color": "#222", "meaning": "bb"}  # other entry untouched


def test_resolve_raises_clear_error_on_unknown_extends_target():
    orphan = ViewDefinition(name="orphan", extends="nope")
    with pytest.raises(ValueError, match=r"extends unknown definition 'nope'"):
        resolve(orphan, {"orphan": orphan})


def test_resolve_raises_clear_error_on_cyclic_extends():
    a = ViewDefinition(name="a", extends="b")
    b = ViewDefinition(name="b", extends="a")
    with pytest.raises(ValueError, match=r"cyclic 'extends' chain"):
        resolve(a, {"a": a, "b": b})


def test_resolve_of_root_is_idempotent():
    once = resolve(BASE_NAVIG8R_DEFINITION, DEFINITION_REGISTRY)
    twice = resolve(BASE_NAVIG8R_DEFINITION, DEFINITION_REGISTRY)
    assert once == twice
    assert once.theme == BASE_NAVIG8R_DEFINITION.theme


def test_resolve_does_not_mutate_the_authored_definitions():
    before = copy.deepcopy(BASE_NAVIG8R_DEFINITION.theme)
    resolved = resolve(CAPABILITY_DEFINITION, DEFINITION_REGISTRY)
    resolved.theme["ink"] = "#deadbeef"  # mutate the RESULT
    assert BASE_NAVIG8R_DEFINITION.theme == before  # authored base is untouched (resolve is pure)


# ── FR-3 — Base navig8r definition ───────────────────────────────────────────────────────────────

def test_base_definition_is_a_root_with_shared_defaults():
    assert BASE_NAVIG8R_DEFINITION.extends is None
    assert BASE_NAVIG8R_DEFINITION.theme  # shared theme tokens
    assert BASE_NAVIG8R_DEFINITION.lenses and BASE_NAVIG8R_DEFINITION.control
    assert BASE_NAVIG8R_DEFINITION.glance and BASE_NAVIG8R_DEFINITION.regions
    # the base owns no domain vocabulary/chrome — those are each domain's delta
    assert BASE_NAVIG8R_DEFINITION.vocabulary == {}
    assert BASE_NAVIG8R_DEFINITION.chrome == {}


# ── FR-4 — Requirements domain is base + a thin delta, projecting to today's profile ─────────────

_EXPECTED_REQUIREMENTS_PROFILE = RenderProfile(
    statuses=(
        StatusStyle("grounded", "Grounded", "#3d7a57", "reuses existing code", 0),
        StatusStyle("spec", "Spec", "#6b6252", "written, not built", 2),
        StatusStyle("awaiting", "Awaiting", "#a9781a", "needs a decision", 3, True),
        StatusStyle("excluded", "Excluded", "#948b78", "out of scope", 2),
        StatusStyle("unknown", "Unknown", "#ab473a", "done-claim without Lives", 4, True),
    ),
    title="This spec — a first look",
    eyebrow="This spec",
    section_lead="What this spec defines",
    headline="A first look at this spec",
    gap_noun="requirement",
    summary_meta=(
        "A glance-approvable view of every requirement in this spec — each grounded in code, "
        "or flagged as still-spec.",
    ),
    why=(
        "Each requirement is a Node: what it does, where it Lives (code/test refs), and "
        "whether evidence grounds it."
    ),
    do=(
        "Read top-down — grounded (green) reuses existing code; spec/awaiting needs a "
        "decision. Approve or flag each requirement below."
    ),
)


def test_requirements_is_thin_delta_over_base():
    assert REQUIREMENTS_DEFINITION.extends == "base"
    # its own keys are only the domain delta — no theme/lenses/control copied from the base
    assert REQUIREMENTS_DEFINITION.theme == {}
    assert set(REQUIREMENTS_DEFINITION.vocabulary) == {"gap_noun", "statuses"}
    assert REQUIREMENTS_DEFINITION.chrome  # owns its masthead/apex chrome


def test_requirements_projection_reproduces_todays_profile_byte_for_byte():
    projected = to_render_profile(resolve(REQUIREMENTS_DEFINITION, DEFINITION_REGISTRY))
    assert projected == _EXPECTED_REQUIREMENTS_PROFILE
    # and the module-level constant the CLI consumes IS the projection
    assert REQUIREMENTS_PROFILE == _EXPECTED_REQUIREMENTS_PROFILE


# ── FR-5 — Second domain proves cross-domain reuse of the same base ──────────────────────────────

_EXPECTED_CAPABILITY_PROFILE = RenderProfile(
    statuses=(
        StatusStyle("built", "Built", "#3d7a57", "code leaf present", 0),
        StatusStyle("thin", "Thin", "#a9781a", "early / incomplete evidence", 2, True),
        StatusStyle("spec", "Spec", "#6b6252", "declared, not built", 3, True),
        StatusStyle("deprecated", "Deprecated", "#ab473a", "do not use", 4),
    ),
    title="Capabilities — a first look",
    eyebrow="Capability index",
    section_lead="What the SDK ships",
    headline="A first look at SDK capabilities",
    gap_noun="capability",
    summary_meta=(
        "A glance-approvable view of what the SDK ships — each capability grounded in a code "
        "leaf, or flagged as thin/spec.",
    ),
    why=(
        "Each capability is a Node: what it does, where it Lives (code refs), and whether a "
        "code leaf grounds it."
    ),
    do=(
        "Read top-down — built (green) has a code leaf; thin/spec needs evidence or is "
        "declared-only. Approve or flag each capability below."
    ),
)


def test_two_domains_share_one_base_with_only_their_own_deltas():
    assert REQUIREMENTS_DEFINITION.extends == CAPABILITY_DEFINITION.extends == "base"
    req = resolve(REQUIREMENTS_DEFINITION, DEFINITION_REGISTRY)
    cap = resolve(CAPABILITY_DEFINITION, DEFINITION_REGISTRY)
    # both inherit the base lenses/control/glance/regions (not re-specified in either delta)
    assert req.lenses == cap.lenses == BASE_NAVIG8R_DEFINITION.lenses
    assert req.control == cap.control == BASE_NAVIG8R_DEFINITION.control
    # each keeps its own vocabulary
    assert req.vocabulary["gap_noun"] == "requirement"
    assert cap.vocabulary["gap_noun"] == "capability"


def test_capability_projection_reproduces_todays_profile_byte_for_byte():
    projected = to_render_profile(resolve(CAPABILITY_DEFINITION, DEFINITION_REGISTRY))
    assert projected == _EXPECTED_CAPABILITY_PROFILE
    assert CAPABILITY_PROFILE == _EXPECTED_CAPABILITY_PROFILE


# ── FR-6 — Base-change propagation (the keystone, with FR-5) ─────────────────────────────────────

def test_base_change_propagates_to_both_non_overriding_domains():
    # A change to a shared base token that NEITHER domain overrides (theme.ink) reaches BOTH.
    mutated_base = replace(
        BASE_NAVIG8R_DEFINITION,
        theme={**BASE_NAVIG8R_DEFINITION.theme, "ink": "#000000"},
    )
    reg = {**DEFINITION_REGISTRY, "base": mutated_base}

    req = resolve(REQUIREMENTS_DEFINITION, reg)
    cap = resolve(CAPABILITY_DEFINITION, reg)
    assert req.theme["ink"] == "#000000"   # requirements did not override ink → inherits the change
    assert cap.theme["ink"] == "#000000"   # capability did not override ink → inherits the change too
    # no edit to either domain delta was needed
    assert REQUIREMENTS_DEFINITION.theme == {}
    assert CAPABILITY_DEFINITION.theme == {"accent": "#3a6a94"}


def test_a_domain_that_overrides_keeps_its_own_value_when_the_base_changes():
    # capability overrides theme.accent; changing the BASE accent must NOT reach it, but MUST reach
    # requirements (which does not override accent). This is the "atomic, per-leaf" guarantee.
    mutated_base = replace(
        BASE_NAVIG8R_DEFINITION,
        theme={**BASE_NAVIG8R_DEFINITION.theme, "accent": "#ffffff"},
    )
    reg = {**DEFINITION_REGISTRY, "base": mutated_base}

    req = resolve(REQUIREMENTS_DEFINITION, reg)
    cap = resolve(CAPABILITY_DEFINITION, reg)
    assert req.theme["accent"] == "#ffffff"   # non-overriding domain follows the base
    assert cap.theme["accent"] == "#3a6a94"   # overriding domain keeps its own


# ── FR-7 — RenderProfile projection (byte-identity) ──────────────────────────────────────────────

def test_projection_returns_a_render_profile_the_renderers_consume():
    resolved = resolve(REQUIREMENTS_DEFINITION, DEFINITION_REGISTRY)
    profile = to_render_profile(resolved)
    assert isinstance(profile, RenderProfile)
    # statuses project in authored order from the keyed map
    assert tuple(s.key for s in profile.statuses) == (
        "grounded", "spec", "awaiting", "excluded", "unknown",
    )


def test_resolved_definition_is_a_distinct_flattened_type():
    resolved = resolve(REQUIREMENTS_DEFINITION, DEFINITION_REGISTRY)
    assert isinstance(resolved, ResolvedDefinition)
    # a resolved definition carries no extends pointer (it is flattened)
    assert not hasattr(resolved, "extends")


# ── Definition-integrity guard (CEP EC-3) ────────────────────────────────────────────────────────
# A registry-parametrized gate so a FUTURE domain added to DEFINITION_REGISTRY is automatically
# covered — no silent drift between a definition, its JSON serialization, and its projected profile.

# Every registry domain that has a module-level RenderProfile the CLI consumes, keyed by its
# definition name → the projection must equal the constant (drift guard). Extend this map when a
# new domain is folded into a definition (EC-2).
_PROFILE_BY_DOMAIN = {
    "requirements": REQUIREMENTS_PROFILE,
    "capability": CAPABILITY_PROFILE,
}


@pytest.mark.parametrize("name", sorted(DEFINITION_REGISTRY))
def test_every_registry_definition_resolves_and_round_trips(name):
    d = DEFINITION_REGISTRY[name]
    # (a) resolves without a cycle / dangling-extends error
    assert isinstance(resolve(d, DEFINITION_REGISTRY), ResolvedDefinition)
    # (b) the REAL authored definition (not a synthetic one) survives a JSON round-trip unchanged
    assert ViewDefinition.from_dict(json.loads(json.dumps(d.to_dict()))) == d


@pytest.mark.parametrize("name", sorted(_PROFILE_BY_DOMAIN))
def test_domain_profile_equals_its_projected_definition(name):
    projected = to_render_profile(resolve(DEFINITION_REGISTRY[name], DEFINITION_REGISTRY))
    assert projected == _PROFILE_BY_DOMAIN[name], (
        f"{name!r} RenderProfile drifted from its ViewDefinition projection"
    )
