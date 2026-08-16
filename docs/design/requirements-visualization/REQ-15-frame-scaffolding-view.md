# Frame / Scaffolding View — Requirements

**Project:** startd8-sdk   **Criticality:** medium
**Version:** 0.2 (post-planning — self-reflective update)   **Date:** 2026-08-16
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — spec-only; delivered via the Spec Delivery Loop)* · architecture `ARCHITECTURE_navig8r-presentation-definition-inheritance.md` (§3 regions/layers · §7 steps 4/5)
**Inherits standards:** det-req-kit · NODE-SCHEMA v0.3.9 · NAMING_CONVENTION · REQ-10-view-definition-cascade (keystone) · REQ-14-control-region-unification (parent — this extends its regions/control) · SOTTO_DESIGN_PRINCIPLE
**Audience:** operator / SDK contributors / cross-repo adopters (legal · benchmark · dev-os)
**Trust boundary:** local render only; no network; no LLM
**Data classification:** internal

> **Readable handle:** `feature/sdk-navigator-renders-the-view-definition-frame-cdae08e5`
> **Semantic name:** *SDK navigator renders the View Definition frame alone as a domain-neutral scaffolding view showing only each region's definition-owned meta-description of what will display plus the control surface, with progressive per-layer disclosure (no layers, one layer at a time, or all), and the layer taxonomy + labelling reconciled into the definition rather than hardcoded.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-15`

## 0. Why this exists — see navig8r free of any requirement

REQ-14 lifted the control panel + region anatomy into the View Definition; scaffold mode already reveals
each region's meta-description. But there is no way to view the **frame alone** — the bare scaffolding,
free of any requirement — and progressively **layer content back in one layer at a time**. This REQ adds
that: a domain-neutral **frame** render that shows only each region's *definition-owned meta-description*
of what content will display, plus the control surface; and **per-layer disclosure** so the operator can
build the picture up a layer at a time (or view none). It also closes a real labelling gap REQ-14 left:
the layer taxonomy (names/colours/legend) is still **hardcoded and inconsistent** with the definition —
this REQ reconciles it so *even the labelling is defined in the View Definition*.

## 0. Planning Insights (self-reflective update)

> Grounding the one-off "empty frame" against the real renderer revealed two corrections:

| v0.1 assumption | Planning discovery | Impact |
|-----------------|--------------------|--------|
| An "empty frame" is just a render with zero nodes | A zero-node render still shows the **actual chrome content** (headline/why/do) — that's the "more text than wanted". The *frame* view is **scaffold mode with content hidden**, where each region shows its `data-scaffold` meta-description via CSS `::before` (already in `_template.py`). | **FR-1**: the frame source renders **scaffold mode ON + content hidden by default** (reuse the existing mechanism), not just empty nodes |
| The layer names come from the definition | The layer taxonomy is **hardcoded and 3-way inconsistent**: the rendered legend says `control · descriptive · computed · node-driven`; the definition's `regions.layers` says `node · derived · computed · scaffold` (unused `derived`/`scaffold`, missing `control`/`descriptive`); the layers actually *used* by bindings are `computed · control · descriptive · node`. | **FR-2/FR-3**: reconcile `regions.layers` into an ordered keyed layer schema (id → label + colour + order) owned by the definition, and render the legend + scaffold colouring FROM it (Genchi Genbutsu — bind to the real values, the REQ-11/REQ-14 reconcile pattern) |

**Resolved open questions:** OQ-1 (frame = empty nodes?) → no, scaffold-mode-on + content-hidden (FR-1).
OQ-2 (per-layer disclosure — CLI or interactive?) → interactive panel toggles driven by the definition's
layers, with the frame defaulting to none; the toggle *interaction* JS stays renderer-specific (NR-1).
OQ-3 (is the layer legend definition-owned?) → not today; FR-2/FR-3 make it so.

## Overview

Add a domain-neutral **`navigator build --source frame`** that renders the resolved View Definition with
**zero nodes**, scaffold mode ON and node content hidden, so the output shows only each region's
definition-owned meta-description (its `regions.bindings[id].scaffold`), the control surface, and the
layer legend — free of any requirement. Reconcile `BASE_NAVIG8R_DEFINITION.regions.layers` from a flat
list into an **ordered keyed layer schema** (`id → {label, color, order}`) populated with the renderer's
actual layer names/colours, project it onto the profile, and render the debug-panel layer legend + the
scaffold per-layer colouring FROM it. Add **per-layer disclosure** — the debug panel gains a show/hide
toggle per layer (driven by the definition's layers) so the operator reveals one layer at a time, none,
or all. Additive + byte-identity-preserving: existing navigator renders, the app path, and the
debug-panel literal-string test stay byte-identical.

## Objectives

- **O-1:** View navig8r free of any requirement — target: `--source frame` renders the bare scaffolding (region meta-descriptions + control surface + layer legend) with no chrome content and no nodes.
- **O-2:** Progressive per-layer disclosure — target: the operator can show no layers, one layer at a time, or all, driven by the definition's layer schema.
- **O-3:** All labelling in the definition — target: the layer names/colours/legend are reconciled into `regions.layers` and rendered from it; the 3-way inconsistency is gone; nothing frame-facing is hardcoded.
- **O-4:** No regression — target: existing renders + app path + the debug-panel literal-string test are byte-identical.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | The layer reconcile drifts from the rendered legend/colours → default render changes | FR-2/FR-3: populate the layer schema from the EXACT current names/colours; byte-identity self-comparison + debug-panel test guard | high |
| scope | Over-building — a control DSL, new anatomy, or storing toggle JS in the definition | NR-1: reuse the existing scaffold/layer mechanism; declare structure only; the interaction JS stays renderer-specific | high |
| quality | The frame source leaks chrome content (the one-off bug) | FR-1: frame = scaffold-mode-on + content-hidden by default, not just empty nodes | medium |
| scope | The frame trying to be a domain view | NR-2: the frame is domain-neutral by design — its purpose is to see the scaffolding free of any requirement | medium |

## Functional requirements

- **FR-1 — Domain-neutral frame source.** `navigator build --source frame` renders the resolved View Definition with **zero nodes**, scaffold mode ON and node-content hidden by default, so the output shows only each region's meta-description (`regions.bindings[id].scaffold`) + the control surface + the layer legend — no chrome content, free of any requirement. Name: The navigator renders a domain-neutral frame source showing only the region meta-descriptions and control surface with no node content. Touches: `src/startd8/navigator/cli_navigator.py`, `src/startd8/navigator/view_definition.py`, `tests/unit/navigator/test_sources_and_cli.py`. Lives: code src/startd8/navigator/cli_navigator.py. Approve?: does `--source frame` render the bare scaffolding with no requirement content?. Verify: `navigator build --source frame --out f.html` renders with the scaffold-mode body class active + node content hidden; `data-scaffold="masthead — profile chrome (eyebrow · headline · why/do)"` is present and no requirement/FR node content is. Serves: O-1
- **FR-2 — Reconcile the layer taxonomy into a keyed schema in the definition.** `BASE_NAVIG8R_DEFINITION.regions.layers` becomes an ordered keyed map `{<id>: {label, color, order}}` populated with the renderer's actual layers — `control` (label "control", color "accent2", order 0), `descriptive` ("descriptive", "accent", 1), `computed` ("computed", "ochre", 2), `node` ("node-driven", "planned", 3) — replacing the flat, inconsistent list. Name: The View Definition regions layers become an ordered keyed schema of id label colour and order matching the renderer. Touches: `src/startd8/navigator/view_definition.py`, `tests/unit/navigator/test_view_definition.py`. Lives: code src/startd8/navigator/view_definition.py. Approve?: is the layer taxonomy a keyed schema owned by the definition, matching the renderer's real layers?. Verify: `resolve(BASE_NAVIG8R_DEFINITION, DEFINITION_REGISTRY).regions["layers"]["control"] == {"label": "control", "color": "accent2", "order": 0}`; the keyed layer ids equal the layers actually used by the region bindings (`control`/`descriptive`/`computed`/`node`). Serves: O-3
- **FR-3 — Render the legend + scaffold colouring FROM the layer schema.** `to_render_profile` carries the layer schema on the profile, and `_template.py` renders the debug-panel layer legend + the scaffold per-layer outline colours from it (via the REQ-14 additive-override seam) instead of the hardcoded legend/CSS; when the schema reproduces the current values the render is byte-identical, and the 3-way inconsistency is gone. Name: The template renders the layer legend and scaffold colouring from the definition layer schema not hardcoded strings. Touches: `src/startd8/navigator/view_definition.py`, `src/startd8/wireframe_view/_template.py`, `tests/unit/wireframe/test_render_profile.py`. Lives: code src/startd8/wireframe_view/_template.py. Approve?: is the layer legend/colouring driven by the definition, byte-identical for the default?. Verify: the default render's `dbg-layers` legend text is byte-identical and now sourced from `profile.regions.layers`; a definition whose delta renames the `node` layer label to "requirements" renders "requirements" in the legend. Serves: O-3
- **FR-4 — Progressive per-layer disclosure.** The debug panel gains a show/hide toggle per layer, driven by the definition's layer schema, so the operator reveals one layer at a time, none, or all; the `frame` source defaults to none (bare scaffold). Name: The debug panel offers a show hide toggle per definition layer so the operator reveals one layer at a time none or all. Touches: `src/startd8/wireframe_view/_template.py`, `tests/unit/wireframe/test_render_profile.py`. Lives: code src/startd8/wireframe_view/_template.py. Approve?: can the operator disclose layers one at a time / none / all?. Verify: a profiled render's panel contains a per-layer toggle for each layer id in `profile.regions.layers` (a `data-layer-toggle="node"` control et al.), and the frame source render starts with all layers hidden. Serves: O-2
- **FR-5 — Additive + byte-identical.** The frame source + layer-schema reconcile + per-layer toggles are additive — existing navigator renders (requirements/capability/node-schema), the app-scaffold path, and the debug-panel literal-string test are byte-identical. Name: The frame and layer-schema additions leave existing renders the app path and the debug-panel test byte-identical. Touches: `tests/unit/wireframe/test_render_profile.py`, `tests/unit/navigator/test_view_definition.py`. Lives: test tests/unit/wireframe/test_render_profile.py. Approve?: are all existing surfaces unchanged?. Verify: `test_no_profile_is_byte_identical` + `test_debug_view_mode_panel_is_profiled_and_byte_safe` pass UNEDITED; a requirements-domain render is byte-identical to its pre-REQ-15 golden. Serves: O-4

## Non-requirements

- **NR-1:** No control DSL. The definition declares *what* layers/regions/toggles exist; the per-layer show/hide **interaction JS** (the class-toggling logic) stays renderer-specific in `_template.py` — the should-we boundary carried from REQ-14 NR-1. No per-layer/per-toggle JavaScript is stored in the definition.
- **NR-2:** The `frame` source is domain-neutral by design — it renders no requirement/domain content; its purpose is to view the scaffolding free of any requirement. It does not become a per-domain view.
- **NR-3:** No new layers, regions, anatomy, or debug modes — a pure reconcile + expose of the EXISTING scaffold/layer/region mechanism. New anatomy is a separate concern.
- **NR-4:** Scaffold CSS positioning/mechanics (the `body.scaffold` padding, per-region `margin-top`, label offsets) stay in the template stylesheet — presentation mechanics, not definition data (REQ-14 NR-3 carried forward).

## Appendix A — Accepted (with where merged)
*(none yet — CRP incoming)*

## Appendix B — Rejected (with rationale)
*(none yet — CRP incoming)*

## Appendix C — Incoming review rounds
*(none yet)*

*v0.2 — Post-planning self-reflective update. Frame = scaffold-mode-on + content-hidden (not empty nodes); layer taxonomy reconciled into a keyed definition schema (the 3-way-inconsistency fix); 3 open questions resolved.*
