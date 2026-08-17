# A11y as a Cross-Topology Lens (the fourth RenderProfile moment) — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-17
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — spec-only; delivered via the Spec Delivery Loop)* · **`ANALYSIS_corpus-self-study-five-threads.md` Thread 4 (the empty cell this fills)** · `REQ-03` (the a11y renderer + `check_no_bleed`) · `REQ-04` (the lens-lift pattern this repeats) · `REQ-09` (shared-lens adoption) · `VISUALIZATION_VARIANTS_ANALYSIS.md` (FF-1)
**Inherits standards:** det-req-kit · NODE-SCHEMA v0.4.0 (inv. 8 — modality-independence) · NAMING_CONVENTION · REQ-04 (`node_lenses.py` — the lifted lens home)
**Audience:** operator / accessibility users (low-vision + no-vision) / SDK contributors
**Trust boundary:** local render only; no network; no LLM
**Data classification:** internal

> **Readable handle:** `feature/sdk-navigator-lifts-accessibility-from-a-41228c6e`
> **Semantic name:** *SDK navigator lifts accessibility from a standalone flat renderer into a cross-topology lens so the tree graph and diff topologies each render an accessible semantic view reusing the no-bleed check, closing the FF-1 pattern for a11y so adding a renderer never re-forks the accessible view while the flat a11y case stays byte-identical.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-26`

## 0. Why this exists — a11y is welded to one topology (FF-1, again)

The axis-coverage refresh (self-study Thread 4) found the corpus's empty cells have migrated *up the stack*:
the highest-leverage gap is that **accessibility is welded to the flat topology** — `render_a11y.py` renders
only the 2-level requirements view. A screen-reader user can approve a *requirements doc* but **cannot
navigate a dependency graph, a corpus diff, or an N-level tree.** This is the *exact* shape of **FF-1** (the
audience/fluency lenses were once welded to the wireframe renderer) — a11y is a **lens value on the
view-model** (NODE-SCHEMA inv. 8: every visual cue must have a spoken/textual equivalent) that is currently
trapped in one renderer. This REQ is the **fourth RenderProfile moment**: after domain-vocab (M2) and
audience/fluency (REQ-04), lift **a11y** into `node_lenses.py` so every topology inherits it — so that
*adding a new renderer never re-forks the accessible view* (the crown-jewel-doesn't-refork rule).

## Design decisions

- **a11y is a lens, not a renderer.** Model accessibility as a lens value (a semantic projection mode on the
  view-model) that tree/graph/diff render *through*, reusing the REQ-04 `node_lenses.py` seam — not a
  standalone flat-only renderer.
- **Reuse `check_no_bleed` (REQ-03) across topologies.** The no-visual-vocabulary-bleed invariant applies to
  the a11y lens on *every* topology, not just flat.
- **Modality-independence (inv. 8) is the target.** The graph's node-link structure gets a navigable
  textual/landmark equivalent — the accessible form carries the same information as the visual one.

## Overview

Lift a11y into `node_lenses.py` as a cross-topology lens; render the N-level tree, the dependency graph, and
the corpus diff each in an accessible semantic mode (landmarks/roles/headings + a navigable textual
equivalent), reusing `render_a11y`'s primitives + `check_no_bleed`; wire `--format a11y` to compose with
`--renderer tree|graph|diff`; keep the shipped flat a11y case byte-identical; and guard that adding a future
renderer inherits the a11y lens rather than re-forking it. Additive, byte-identical for the flat case.

## Objectives

- **O-1:** a11y is a cross-topology lens — target: `--format a11y` composes with `--renderer tree|graph|diff`, each producing an accessible semantic view with a navigable textual equivalent.
- **O-2:** No bleed, no fork — target: `check_no_bleed` passes on the a11y lens across all topologies; a synthetic "new renderer" inherits the a11y lens without a per-renderer a11y fork (FF-1 closed for a11y).
- **O-3:** Additive, byte-identical — target: the shipped flat a11y render is byte-identical; the lift is additive.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | A graph rendered as a11y loses its structure (an inaccessible node-link blob) | FR-3: the graph a11y form is a navigable textual equivalent of the node-link structure (inv. 8), not a flattened list — edges are spoken as relations | high |
| scope | Rebuilding a11y from scratch instead of lifting | NR-2: reuse `render_a11y` primitives + `node_lenses.py`; the lift is a re-home, not a rewrite | high |
| quality | Visual vocabulary bleeds into the a11y view on the new topologies | FR-5: `check_no_bleed` (REQ-03) runs on the a11y lens across every topology | medium |
| regression | The flat a11y case changes | O-3/FR-7: the shipped flat a11y render is byte-identical | high |

## Functional requirements

- **FR-1 — a11y as a lens value in the shared transform.** Lift accessibility into `node_lenses.py` (REQ-04's lifted-lens home) as a lens value — a semantic projection mode on the view-model — that any renderer consumes, rather than a flat-only standalone renderer. Name: Accessibility becomes a lens value in the shared node-lenses transform consumed by any renderer. Touches: `src/startd8/wireframe_view/node_lenses.py`, `src/startd8/navigator/render_a11y.py`, tests. Lives: code src/startd8/wireframe_view/node_lenses.py. Approve?: is a11y a lens value in the shared transform rather than a flat-only renderer?. Verify: the a11y lens is applied via `node_lenses` and consumed by more than one renderer; the flat renderer's a11y output is unchanged. Serves: O-1
- **FR-2 — a11y-of-tree (accessible N-level drill).** The N-level tree renders in an accessible semantic mode (landmarks / roles / heading levels mapping the drill hierarchy) so a screen-reader user can navigate the tree topology. Name: The N-level tree renders an accessible semantic view of its drill hierarchy. Touches: `src/startd8/navigator/render_tree.py`, `src/startd8/navigator/render_a11y.py`, tests. Lives: code src/startd8/navigator/render_tree.py. Approve?: does the tree topology render an accessible semantic drill view?. Verify: `--source requirements --renderer tree --format a11y` emits a semantic view with heading levels/roles mapping the node hierarchy and a screen-reader-navigable structure. Serves: O-1
- **FR-3 — a11y-of-graph (navigable textual equivalent of the node-link structure).** The dependency graph renders in an accessible mode whose textual/landmark form carries the same information as the visual node-link (edges spoken as relations, per inv. 8) — not a flattened list. Name: The dependency graph renders a navigable textual equivalent of its node-link structure with edges as spoken relations. Touches: `src/startd8/navigator/render_graph.py`, `src/startd8/navigator/render_a11y.py`, tests. Lives: code src/startd8/navigator/render_graph.py. Approve?: does the graph render a navigable textual equivalent carrying the edge structure?. Verify: `--renderer graph --format a11y` emits a semantic view where each node's relations (edges) are enumerated as navigable text; the information matches the visual graph's edges. Serves: O-1
- **FR-4 — a11y-of-diff (accessible delta).** The corpus diff renders in an accessible mode where added / removed / changed and status transitions are semantic regions a screen-reader user can navigate. Name: The corpus diff renders added removed and changed as accessible semantic regions. Touches: `src/startd8/navigator/render_diff.py`, `src/startd8/navigator/render_a11y.py`, tests. Lives: code src/startd8/navigator/render_diff.py. Approve?: does the diff topology render accessible added/removed/changed regions?. Verify: a diff rendered `--format a11y` exposes added/removed/changed and status transitions as distinct semantic regions navigable by role/landmark. Serves: O-1
- **FR-5 — `check_no_bleed` across every topology.** REQ-03's `check_no_bleed` (no visual/wireframe vocabulary leaks into the semantic view) runs on the a11y lens for tree, graph, and diff — not only the flat view. Name: The no-bleed check runs on the a11y lens across tree graph and diff not only the flat view. Touches: `src/startd8/navigator/render_a11y.py`, tests. Lives: code src/startd8/navigator/render_a11y.py. Approve?: does check_no_bleed run on the a11y lens for every topology?. Verify: `check_no_bleed` passes for the a11y lens on tree/graph/diff; an injected visual-vocabulary leak fails it on each topology. Serves: O-2
- **FR-6 — No re-fork (FF-1 closed for a11y).** Because a11y is a lens on the view-model, a new renderer inherits it without a per-renderer a11y fork — verified by a synthetic new renderer that gains the a11y lens with no a11y-specific code. Name: A new renderer inherits the a11y lens without a per-renderer accessibility fork. Touches: `tests/unit/navigator/test_a11y_lens.py`. Lives: test tests/unit/navigator/test_a11y_lens.py. Approve?: does a new renderer inherit a11y with no a11y fork?. Verify: a synthetic renderer applying `node_lenses` gains an accessible view with zero a11y-specific code; no renderer carries a forked a11y implementation. Serves: O-2
- **FR-7 — Additive, byte-identical flat case.** The lift is additive: the shipped flat a11y render (REQ-03) is byte-identical, and the app-scaffold path is untouched. Name: The a11y lens lift leaves the shipped flat a11y render and the app-scaffold path byte-identical. Touches: `tests/unit/navigator/test_render_a11y.py`, `tests/unit/wireframe/test_render_profile.py`. Lives: test tests/unit/navigator/test_render_a11y.py. Approve?: is the flat a11y render byte-identical after the lift?. Verify: the existing flat a11y render test passes unedited; `test_no_profile_is_byte_identical` passes unedited. Serves: O-3

## Non-requirements

- **NR-1:** Does NOT change the visual renderers' default (visual) output — a11y is an additive `--format a11y` lens; the visual paths are byte-identical.
- **NR-2:** Does NOT rebuild a11y — it re-homes `render_a11y`'s primitives into the `node_lenses` seam (REQ-04 pattern); a re-home, not a rewrite.
- **NR-3:** Does NOT add a new renderer — it makes the *existing* topologies (tree/graph/diff) accessible via the lifted lens.
- **NR-4:** Build-blocked (not spec-blocked) on nothing new — REQ-03 (a11y + no-bleed), REQ-04 (`node_lenses`), REQ-05 (graph), REQ-07 (diff) are all built.
