# Control-Panel + Scaffold-Region Unification — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-15
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — spec-only; delivered via the Spec Delivery Loop)* · architecture `ARCHITECTURE_navig8r-presentation-definition-inheritance.md` (§7 **step 4 — control-layer schema** + **step 5 — region/layer bindings**; the two roadmap steps that were skipped while REQ-11/12/13 landed)
**Inherits standards:** det-req-kit · NODE-SCHEMA v0.3.9 · NAMING_CONVENTION · REQ-10-view-definition-cascade (parent keystone) · REQ-11-theme-token-activation · REQ-12-chrome-binding-grammar (sibling projections)
**Audience:** operator / SDK contributors / cross-repo adopters (legal · benchmark · dev-os)
**Trust boundary:** local render only; no network; no LLM
**Data classification:** internal

> **Readable handle:** `feature/sdk-navigator-unifies-the-debug-control-panel-93a3c2a4`
> **Semantic name:** *SDK navigator unifies the debug control panel and the scaffold region-and-layer taxonomy into the View Definition control and regions sections so the template reads them instead of hardcoding them and a domain can relabel or regroup them via its delta while the default render stays byte-identical.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-14`

> **BUILT (2026-08-16, `a84bf12c`) — the canonical REQ-14.** Delivered in 3 byte-verified layers (model → project → override). FR-3/FR-5 were realized as an **additive runtime override** (not build-from-scratch): building the panel from the payload would have moved the debug-panel's literal strings into the builder and broken FR-6's byte-identity + unedited-test gate, so — the REQ-11 theme pattern — the hardcoded panel + static region attrs stay and `applyDefinitionOverride()` re-labels from `profile.control`/`regions` (base ⇒ no-op ⇒ byte-identical; a domain delta overrides; scaffold reveals the definition). Supersedes the narrower `REQ-14-control-schema-formalization.md` (removed).

## 0. Why this exists — close the mirror

REQ-10 made presentation a serializable `ViewDefinition`; REQ-11 projected its `theme`, REQ-12 its
`chrome`, REQ-13 imported one cross-repo. But the definition's `control` and `regions` sections are still
**inert placeholders** — `view_definition.py` says outright they are "NOT yet extracted into the profile
(architecture §7 steps 4/5 — later REQs)". Meanwhile the debug control panel (the top-right VIEW /
OVERLAYS / TEMPLATE ANATOMY toggles) and the scaffold region/layer taxonomy (the `data-layer` +
`data-scaffold` anatomy labels) are **still hardcoded** in `_template.py` (~28 `data-scaffold` / `#debug`
/ `body.scaffold` refs). This is the exact "mirror" the whole architecture was built to close: the
scaffold mode's job is to *reveal the template's anatomy*, yet that anatomy lives in the template's HTML,
not in the definition the profile is built from — so a second domain cannot relabel or regroup it, and the
scaffold reveals hand-authored strings rather than the resolved definition. REQ-14 lifts both layers into
the definition and has the template **read** them, closing steps 4 and 5. It is a **pure lift** — the
default render is byte-identical; the *interaction JS* (toggle handlers) deliberately stays
renderer-specific (the should-we discipline against a control DSL).

## Overview

Enrich the `control` section to an ordered schema (panel position → groups → toggles) and the `regions`
section to ordered region bindings (id → layer → scaffold anatomy label → revealing mode), and **populate
`BASE_NAVIG8R_DEFINITION` with the exact groups / toggles / region labels the template hardcodes today**.
Project both onto `RenderProfile` (new `control` + `regions` fields, defaulting to the base so an absent
delta renders identically). Have `_template.py` **build the debug panel and emit each region's
`data-layer` / `data-scaffold` from the profile** instead of hardcoding them — while the toggle *handler
JS* stays keyed in the template. Prove atomic override: a domain delta that renames a control group or a
region's anatomy label renders the change; the shipped default render is byte-identical.

## Objectives

- **O-1:** The debug control panel is defined in the View Definition, not the template — target: `control` populated with the current groups/toggles, projected to `RenderProfile.control`, and the template builds the panel from it.
- **O-2:** The scaffold region/layer taxonomy is defined in the View Definition — target: `regions` populated with the current region→layer→anatomy-label bindings, projected, and the template emits `data-layer`/`data-scaffold` from it.
- **O-3:** Close the mirror, byte-identically — target: a domain delta that relabels/regroups control or a region's anatomy label renders the change atomically; the shipped default render + the reqs/capability profiles are byte-identical.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| scope | Over-abstracting the toggle interaction into a control DSL (declaring *how* the browser toggles, not just *what* exists) | NR-1: the definition declares structure only (groups/toggles/regions); the handler JS stays keyed in the template — the should-we boundary | high |
| quality | The lift drifts from the hardcoded labels → default render changes | FR-6: populate `control`/`regions` from the EXACT current strings; `test_no_profile_is_byte_identical` + a golden-HTML diff guard the default render | high |
| quality | `control`/`regions` are inert placeholders today — projecting them naively yields empty panels | FR-1/FR-4 populate the base with the real current structure BEFORE FR-2/FR-3/FR-5 project + consume | high |
| scope | Adding new debug modes / new anatomy while lifting | NR-2: pure lift of the EXISTING scaffold+debug — no new capability, no new mode | medium |

## Functional requirements

- **FR-1 — Model the control panel in the definition.** Enrich the `control` section to an ordered schema (`panel` position + ordered `groups`, each with `id`/`label` + ordered `toggles` of `id`/`label`/`mode`) and populate `BASE_NAVIG8R_DEFINITION.control` with the groups + toggles the template hardcodes today (VIEW: `structOnly`,`combined`; OVERLAYS: `hideScaffold`; TEMPLATE ANATOMY: `scaffold`,`scaffoldOnly`). Name: The View Definition control section models the debug panel as ordered groups of toggles. Touches: `src/startd8/navigator/view_definition.py`, `tests/unit/navigator/test_view_definition.py`. Lives: code src/startd8/navigator/view_definition.py. Approve?: does resolving the base yield the 3 debug groups with their current toggles?. Verify: `resolve(BASE_NAVIG8R_DEFINITION, DEFINITION_REGISTRY).control` has groups `view`/`overlays`/`template-anatomy` with toggle ids `structOnly,combined,hideScaffold,scaffold,scaffoldOnly`. Serves: O-1
- **FR-2 — Project control onto RenderProfile.** `to_render_profile` projects the resolved `control` into a new `RenderProfile.control` field, defaulting to the base panel so a profile built without a `control` delta carries the base groups (absent-delta renders identically). Name: to_render_profile projects the resolved control section onto a RenderProfile.control field defaulting to the base panel. Touches: `src/startd8/navigator/view_definition.py`, `src/startd8/wireframe/profile.py`, `tests/unit/wireframe/test_render_profile.py`. Lives: code src/startd8/navigator/view_definition.py. Approve?: does a projected profile carry the control groups, and default to base when no delta is given?. Verify: `to_render_profile(resolve(REQUIREMENTS_DEFINITION,...)).control` has the 3 groups; a profile from a definition with no `control` delta still carries the base groups. Serves: O-1
- **FR-3 — Template builds the debug panel FROM the profile.** `_template.py` builds the top-right debug panel by iterating `profile.control.groups`/toggles instead of hardcoding the group headers + toggle rows; the toggle *interaction JS* (handlers keyed by toggle id) stays in the template (NR-1). Name: The template renders the debug control panel by iterating profile.control instead of hardcoded group and toggle HTML. Touches: `src/startd8/wireframe_view/_template.py`, `tests/unit/navigator/test_sources_and_cli.py`. Lives: code src/startd8/wireframe_view/_template.py. Approve?: is the debug panel built from the profile, with a domain able to relabel a group?. Verify: the default render's debug panel is byte-identical; a definition whose delta renames the `template-anatomy` group label to "Structure" renders "Structure" as the group header. Serves: O-1, O-3
- **FR-4 — Model the region/layer taxonomy in the definition.** Enrich the `regions` section to ordered region entries (`id` + `layer` + `scaffold` anatomy label + revealing `mode`) and populate `BASE_NAVIG8R_DEFINITION.regions` with the current region→layer→anatomy-label bindings (masthead/glance/control/legend/section-lead/outline/shape/…) drawn from the template's existing `data-layer`/`data-scaffold` strings. Name: The View Definition regions section models each region as a layer plus its scaffold anatomy label. Touches: `src/startd8/navigator/view_definition.py`, `tests/unit/navigator/test_view_definition.py`. Lives: code src/startd8/navigator/view_definition.py. Approve?: does resolving the base yield the current regions with their layers and anatomy labels?. Verify: `resolve(BASE_NAVIG8R_DEFINITION,...).regions` includes a `masthead` region on layer `descriptive` and an `outline` region on layer `node`, each carrying its current `data-scaffold` anatomy string. Serves: O-2
- **FR-5 — Template emits data-layer/data-scaffold FROM the profile.** `to_render_profile` projects `regions` onto `RenderProfile.regions`, and `_template.py` emits each region's `data-layer` + `data-scaffold` anatomy label from `profile.regions` instead of hardcoding them. Name: The template emits each region's data-layer and data-scaffold anatomy label from profile.regions instead of hardcoded attributes. Touches: `src/startd8/navigator/view_definition.py`, `src/startd8/wireframe_view/_template.py`, `tests/unit/navigator/test_sources_and_cli.py`. Lives: code src/startd8/wireframe_view/_template.py. Approve?: are the scaffold anatomy labels emitted from the definition, with a domain able to override one atomically?. Verify: the default render's `data-scaffold` labels are byte-identical; a definition delta overriding the `outline` region's anatomy label renders that one label changed while every other region label is unchanged (atomic override). Serves: O-2, O-3
- **FR-6 — Pure lift, byte-identical default.** The unification is behaviour-preserving — the shipped default render (HTML) and the three domain profiles (requirements/capability/base) are byte-identical; `test_no_profile_is_byte_identical` passes unedited and a golden-HTML comparison of the pre/post default render is empty. Name: The control and region lift preserves the shipped default render byte-for-byte. Touches: `tests/unit/wireframe/test_render_profile.py`, `tests/unit/navigator/test_view_definition.py`. Lives: test tests/unit/wireframe/test_render_profile.py. Approve?: is the shipped default render unchanged by the lift?. Verify: `test_no_profile_is_byte_identical` passes unedited; a golden diff of the default navigator HTML before vs after the lift is empty. Serves: O-3
- **FR-7 — Close the mirror.** The scaffold mode's revealed anatomy is drawn from the same definition the profile was built from, so a change to a region's anatomy label (or a control group) in the definition appears in scaffold mode — the scaffold reveals the resolved definition, not hand-authored template strings. Name: Scaffold mode reveals anatomy sourced from the same View Definition the profile is built from. Touches: `tests/unit/navigator/test_view_definition.py`, `src/startd8/wireframe_view/_template.py`. Lives: test tests/unit/navigator/test_view_definition.py. Approve?: does the scaffold anatomy reflect the definition rather than hardcoded strings?. Verify: rendering a definition whose `regions` delta changes the `glance` anatomy label, in scaffold mode, shows the changed label — proving the scaffold mirrors the definition. Serves: O-2, O-3

## Non-requirements

- **NR-1:** The toggle **interaction JS** (the handlers, the mode-switching / show-hide logic keyed by toggle id) stays renderer-specific in `_template.py` — it is NOT lifted into the definition. The definition declares *what* groups/toggles/regions exist; *how* the browser toggles them is renderer mechanics. This is the should-we boundary that keeps this a lift, not a control DSL.
- **NR-2:** No new debug modes, no new toggles, no new anatomy layers — this is a pure lift of the EXISTING scaffold + debug surface into the definition. New control capabilities are a separate concern.
- **NR-3:** The scaffold **CSS positioning** (the top-gap legibility fix — `body.scaffold` padding, per-region `margin-top`, label offsets) stays in the template stylesheet; it is presentation mechanics, not definition data.
- **NR-4:** No per-region or per-toggle JavaScript is stored in the definition (a corollary of NR-1) — the definition holds only declarative structure (ids, labels, layers, modes).
- **NR-5:** No change to `control`/`regions` cross-repo import semantics beyond what REQ-13 already ships — an external definition that carries `control`/`regions` deltas resolves through the same base+delta cascade (this REQ just makes those sections load-bearing).
