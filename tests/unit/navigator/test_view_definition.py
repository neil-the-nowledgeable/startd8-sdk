"""View Definition + cascade resolver (REQ-10) — the presentation twin of NODE-SCHEMA.

Covers the seven FRs. The keystone acceptance is FR-5 + FR-6 together: a base design change propagates
atomically to two domains that share it, while each keeps its overrides.
"""
from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest

from startd8.navigator.sources_capability import CAPABILITY_PROFILE
from startd8.navigator.sources_node_schema import NODE_SCHEMA_PROFILE
from startd8.navigator.sources_requirements import REQUIREMENTS_PROFILE
from startd8.navigator.view_definition import (
    BASE_NAVIG8R_DEFINITION,
    CAPABILITY_DEFINITION,
    DEFINITION_REGISTRY,
    NODE_SCHEMA_DEFINITION,
    REQUIREMENTS_DEFINITION,
    ResolvedDefinition,
    ViewDefinition,
    definition_diff,
    load_definition,
    resolve,
    resolve_bindings,
    resolve_external,
    to_render_profile,
    validate_definitions,
)
from startd8.wireframe.profile import RenderProfile, StatusStyle

_BASE_RESOLVED_FOR_EXPECTED = resolve(BASE_NAVIG8R_DEFINITION, DEFINITION_REGISTRY)
_BASE_CONTROL = _BASE_RESOLVED_FOR_EXPECTED.control
_BASE_REGIONS = _BASE_RESOLVED_FOR_EXPECTED.regions
_LEGAL_FIXTURE = Path(__file__).parent / "fixtures" / "legal-view-definition.json"


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
    # REQ-11: requirements overrides no theme → inherits the base tokens (the real _template.py :root).
    theme_tokens={"ink": "#241f17", "paper": "#f4efe4", "accent": "#1b545f"},
    control=_BASE_CONTROL, regions=_BASE_REGIONS,
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
    # REQ-11: capability overrides theme.accent → inherits base ink/paper, keeps its own accent.
    theme_tokens={"ink": "#241f17", "paper": "#f4efe4", "accent": "#3a6a94"},
    control=_BASE_CONTROL, regions=_BASE_REGIONS,
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
    "node-schema": NODE_SCHEMA_PROFILE,
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


# ── REQ-11 — theme-token activation ──────────────────────────────────────────────────────────────

def test_base_theme_equals_the_renderers_actual_root_values():
    # FR-1: the base theme tokens ARE the template's real `:root` values, so projecting them is a
    # no-op for a non-overriding domain (the byte-identity anchor — not REQ-10's placeholder values).
    assert BASE_NAVIG8R_DEFINITION.theme == {
        "ink": "#241f17", "paper": "#f4efe4", "accent": "#1b545f",
    }


def test_to_render_profile_projects_theme_into_theme_tokens():
    # FR-3: the resolved theme section (previously unprojected) now rides on the profile.
    req = to_render_profile(resolve(REQUIREMENTS_DEFINITION, DEFINITION_REGISTRY))
    cap = to_render_profile(resolve(CAPABILITY_DEFINITION, DEFINITION_REGISTRY))
    assert req.theme_tokens == BASE_NAVIG8R_DEFINITION.theme          # requirements: no override
    assert cap.theme_tokens["accent"] == "#3a6a94"                    # capability: its own accent
    assert cap.theme_tokens["ink"] == BASE_NAVIG8R_DEFINITION.theme["ink"]  # …but inherits base ink


def test_base_theme_change_propagates_to_projected_tokens():
    # FR-5: a base theme change reaches both domains' projected tokens; an overrider keeps its own.
    mutated_base = replace(
        BASE_NAVIG8R_DEFINITION, theme={**BASE_NAVIG8R_DEFINITION.theme, "ink": "#010101"},
    )
    reg = {**DEFINITION_REGISTRY, "base": mutated_base}
    req = to_render_profile(resolve(REQUIREMENTS_DEFINITION, reg))
    cap = to_render_profile(resolve(CAPABILITY_DEFINITION, reg))
    assert req.theme_tokens["ink"] == "#010101"      # non-overriding domain follows the base
    assert cap.theme_tokens["ink"] == "#010101"      # capability didn't override ink → follows too
    assert cap.theme_tokens["accent"] == "#3a6a94"   # …but keeps its own accent override


# ── EC-2 (REQ-10 backlog) — node-schema is the 3rd real domain ───────────────────────────────────

def test_node_schema_is_a_thin_delta_over_the_same_base():
    assert NODE_SCHEMA_DEFINITION.extends == "base"
    assert NODE_SCHEMA_DEFINITION.theme == {}                       # no theme override → inherits base
    ns = resolve(NODE_SCHEMA_DEFINITION, DEFINITION_REGISTRY)
    assert ns.lenses == BASE_NAVIG8R_DEFINITION.lenses             # shares the base lenses/control/…
    assert ns.control == BASE_NAVIG8R_DEFINITION.control


def test_node_schema_projection_reproduces_the_former_literal_and_inherits_theme():
    # The derived NODE_SCHEMA_PROFILE reproduces the former standalone literal's vocabulary + chrome…
    assert NODE_SCHEMA_PROFILE.eyebrow == "NODE-SCHEMA"
    assert NODE_SCHEMA_PROFILE.gap_noun == "field"
    assert tuple(s.key for s in NODE_SCHEMA_PROFILE.statuses) == ("authored", "derived", "computed", "meta")
    assert NODE_SCHEMA_PROFILE.statuses[1].color == "#2b7382"      # 'derived' teal, unchanged
    # …and now inherits the activated base theme (REQ-11), overriding nothing.
    assert NODE_SCHEMA_PROFILE.theme_tokens == BASE_NAVIG8R_DEFINITION.theme


# ── EC-4 (REQ-10 backlog) — definition_diff surfaces a domain's delta vs the base ────────────────

def test_definition_diff_shows_only_what_a_domain_overrides_or_adds():
    delta = definition_diff(CAPABILITY_DEFINITION, BASE_NAVIG8R_DEFINITION, DEFINITION_REGISTRY)
    # capability overrides theme.accent and adds its own vocabulary + chrome…
    assert delta["theme"] == {"accent": "#3a6a94"}          # only the overridden leaf, not ink/paper
    assert delta["vocabulary"]["gap_noun"] == "capability"
    assert "chrome" in delta
    # …and inherited-unchanged sections do NOT appear in the delta.
    assert "lenses" not in delta and "control" not in delta and "regions" not in delta


def test_definition_diff_of_the_base_against_itself_is_empty():
    assert definition_diff(BASE_NAVIG8R_DEFINITION, BASE_NAVIG8R_DEFINITION, DEFINITION_REGISTRY) == {}


# ── REQ-12 — chrome-binding grammar ──────────────────────────────────────────────────────────────

def test_resolve_bindings_substitutes_single_fields_only():
    # FR-1: single-field substitution; unknown/empty → ""; no-placeholder unchanged.
    assert resolve_bindings("What {key} defines", {"key": "REQ-01"}) == "What REQ-01 defines"
    assert resolve_bindings("{missing}", {}) == ""
    assert resolve_bindings("static text", {"key": "x"}) == "static text"


def test_requirements_chrome_carries_the_fr17_bindings():
    # FR-4: the masthead derivations are declarative bindings on the definition, not hardcoded Python.
    bindings = REQUIREMENTS_DEFINITION.chrome["bindings"]
    assert bindings["eyebrow"] == "{key}"
    assert bindings["headline"] == "{title}"
    assert bindings["section_lead"] == "What {key} defines"
    assert bindings["summary_meta"] == ["{semantic_name}"]


def test_chrome_bindings_are_context_gated_and_fall_back_when_empty():
    # FR-3: no context → static; context with a field → derived; empty field → static fallback.
    static = to_render_profile(resolve(REQUIREMENTS_DEFINITION, DEFINITION_REGISTRY))
    assert static.eyebrow == "This spec"                       # context=None → static (byte-identical)
    bound = to_render_profile(
        resolve(REQUIREMENTS_DEFINITION, DEFINITION_REGISTRY),
        context={"key": "REQ-9", "title": "Demo", "semantic_name": "does a thing"},
    )
    assert bound.eyebrow == "REQ-9"                             # {key} resolved
    assert bound.section_lead == "What REQ-9 defines"          # template with embedded literal
    assert bound.summary_meta == ("does a thing",)             # list template → tuple
    empty = to_render_profile(
        resolve(REQUIREMENTS_DEFINITION, DEFINITION_REGISTRY), context={"key": ""},
    )
    assert empty.eyebrow == "This spec"                        # empty field → static fallback


def test_bindings_ride_the_cascade_and_appear_in_the_resolved_dump():
    # FR-6: bindings are part of the resolved chrome (inspectable via view-definition, cascade-merged).
    resolved = resolve(REQUIREMENTS_DEFINITION, DEFINITION_REGISTRY)
    assert resolved.chrome["bindings"]["eyebrow"] == "{key}"


def test_non_requirements_domains_have_no_bindings_and_ignore_context():
    # capability has no bindings → a context can't change its chrome (byte-safe).
    a = to_render_profile(resolve(CAPABILITY_DEFINITION, DEFINITION_REGISTRY))
    b = to_render_profile(resolve(CAPABILITY_DEFINITION, DEFINITION_REGISTRY), context={"key": "X"})
    assert a == b


# ── EC-6 (REQ-10 backlog) — validate_definitions governs the registry ────────────────────────────

def test_shipped_registry_is_valid():
    assert validate_definitions(DEFINITION_REGISTRY) == []


def test_validate_flags_unknown_extends_and_unknown_binding_field():
    orphan = ViewDefinition(name="orphan", extends="ghost")
    bad_bind = ViewDefinition(
        name="bad", extends="base",
        chrome={"bindings": {"eyebrow": "{nope}"}},
    )
    reg = {**DEFINITION_REGISTRY, "orphan": orphan, "bad": bad_bind}
    issues = validate_definitions(reg)
    assert any("unknown definition 'ghost'" in i for i in issues)
    assert any("unknown context field 'nope'" in i for i in issues)


# ── REQ-13 — cross-repo VIEW-SCHEMA import ───────────────────────────────────────────────────────

def test_load_definition_from_dict_and_requires_name():
    d = load_definition({"name": "x", "extends": "base", "vocabulary": {"gap_noun": "thing"}})
    assert isinstance(d, ViewDefinition) and d.name == "x"
    with pytest.raises(ValueError, match="missing the required 'name'"):
        load_definition({"extends": "base"})
    with pytest.raises(ValueError, match="must be a JSON object"):
        load_definition([1, 2, 3])


def test_external_definition_inherits_the_shipped_base_and_projects():
    # FR-2/FR-4: the synthetic 'legal' adopter loads, resolves against the base, and projects.
    legal = load_definition(_LEGAL_FIXTURE)
    resolved = resolve_external(legal)
    assert resolved.theme == BASE_NAVIG8R_DEFINITION.theme          # inherits the shared theme
    assert resolved.lenses == BASE_NAVIG8R_DEFINITION.lenses        # …and lenses/control/…
    profile = to_render_profile(resolved)
    assert profile.eyebrow == "This statute"                         # its own chrome
    assert profile.gap_noun == "provision"
    assert profile.theme_tokens == BASE_NAVIG8R_DEFINITION.theme     # inherited theme reaches the render
    assert tuple(s.key for s in profile.statuses) == ("enacted", "proposed", "contested")


def test_resolve_external_does_not_mutate_the_shipped_registry():
    before = set(DEFINITION_REGISTRY)
    resolve_external(load_definition(_LEGAL_FIXTURE))
    assert set(DEFINITION_REGISTRY) == before                        # NR-2: registry untouched


# ── REQ-14 — control + region model in the definition (data layer; consumption deferred) ─────────

def test_base_models_the_debug_control_panel_as_groups_of_toggles():
    # REQ-view-definition-mode FR-2: collapsed to one pick-one VIEW picker + one additive OVERLAYS stack.
    control = resolve(BASE_NAVIG8R_DEFINITION, DEFINITION_REGISTRY).control
    assert control["panel"] == "top-right"
    assert set(control["groups"]) == {"view", "overlays"}
    assert control["groups"]["view"]["label"] == "View"
    assert control["groups"]["view"]["first"] is True
    # VIEW is the Requirement/View-Definition pick; the density modes + scaffoldOnly are retired.
    assert set(control["groups"]["view"]["toggles"]) == {"viewRequirement", "viewDefinition"}
    toggle_ids = {tid for g in control["groups"].values() for tid in g["toggles"]}
    assert toggle_ids == {"viewRequirement", "viewDefinition", "nodeMeta", "outlineRegions", "hideScaffold"}
    assert "structOnly" not in toggle_ids and "combined" not in toggle_ids and "scaffoldOnly" not in toggle_ids
    assert "nodeMeta" in control["groups"]["overlays"]["toggles"]  # the item.meta reveal survives as an overlay


def test_base_models_the_region_layer_taxonomy():
    # FR-4: the base regions section carries each region's layer + scaffold anatomy label.
    regions = resolve(BASE_NAVIG8R_DEFINITION, DEFINITION_REGISTRY).regions
    b = regions["bindings"]
    assert b["mast"]["layer"] == "descriptive"
    assert b["mast"]["scaffold"] == "masthead — profile chrome (eyebrow · headline · why/do)"
    assert b["outline"]["layer"] == "node"
    # REQ-15 FR-2: layers is now an ordered keyed schema (id → label/color/order), matching the layers
    # actually used by the bindings — not the old flat, inconsistent list.
    assert set(regions["layers"]) == {"control", "descriptive", "computed", "node"}
    assert regions["layers"]["control"] == {"label": "control", "color": "accent2", "order": 0}
    used = {v["layer"] for v in b.values()}
    assert used == set(regions["layers"]), "every used layer must be declared in the layer schema"


def test_control_and_regions_ride_the_cascade_by_id():
    # a domain can override one control group label / one region anatomy label atomically (keyed merge).
    child = ViewDefinition(
        name="ctlchild", extends="base",
        control={"groups": {"overlays": {"label": "Filters"}}},
        regions={"bindings": {"outline": {"scaffold": "the requirements list"}}},
    )
    reg = {**DEFINITION_REGISTRY, "ctlchild": child}
    resolved = resolve(child, reg)
    assert resolved.control["groups"]["overlays"]["label"] == "Filters"                 # overridden
    assert resolved.control["groups"]["view"]["label"] == "View"                        # sibling kept
    assert resolved.regions["bindings"]["outline"]["scaffold"] == "the requirements list"  # overridden
    assert resolved.regions["bindings"]["mast"]["layer"] == "descriptive"               # sibling kept


def test_req14_region_override_flows_to_the_projected_profile_for_the_scaffold_mirror():
    # FR-7: a domain that overrides a region's scaffold anatomy label projects that override onto its
    # RenderProfile.regions — so scaffold mode (which reads data-scaffold set from profile.regions)
    # reveals the DEFINITION, not a hardcoded template string.
    child = ViewDefinition(
        name="mirrorchild", extends="base",
        regions={"bindings": {"outline": {"scaffold": "the statute's provisions"}}},
    )
    reg = {**DEFINITION_REGISTRY, "mirrorchild": child}
    prof = to_render_profile(resolve(child, reg))
    assert prof.regions["bindings"]["outline"]["scaffold"] == "the statute's provisions"  # overridden
    assert prof.regions["bindings"]["mast"]["layer"] == "descriptive"                     # sibling kept
    # a non-overriding domain projects the base anatomy verbatim (byte-identity anchor).
    base_prof = to_render_profile(resolve(REQUIREMENTS_DEFINITION, DEFINITION_REGISTRY))
    assert base_prof.regions["bindings"]["outline"]["scaffold"] == "outline — node sections + cards (the node-driven layer)"


def test_req15_layer_schema_projects_and_a_domain_can_relabel_a_layer():
    # FR-3: the layer schema rides the profile; a domain overriding a layer label projects it (the legend
    # is rebuilt from profile.regions.layers at render, so the relabel shows).
    base = to_render_profile(resolve(REQUIREMENTS_DEFINITION, DEFINITION_REGISTRY))
    assert base.regions["layers"]["node"]["label"] == "node-driven"       # base value → byte-identical legend
    child = ViewDefinition(name="lyrchild", extends="base",
                           regions={"layers": {"node": {"label": "requirements"}}})
    reg = {**DEFINITION_REGISTRY, "lyrchild": child}
    prof = to_render_profile(resolve(child, reg))
    assert prof.regions["layers"]["node"]["label"] == "requirements"      # relabel projected
    assert prof.regions["layers"]["control"]["label"] == "control"        # sibling layer kept
