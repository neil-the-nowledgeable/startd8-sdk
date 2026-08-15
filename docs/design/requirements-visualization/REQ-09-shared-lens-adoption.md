# Shared-Lens Adoption in Tree + A11y Renderers — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-15
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — spec-only deliverable; delivered via the Spec Delivery Loop)* · `ENHANCEMENT_BACKLOG_navigator-viz.md` EB-2 · `RETROSPECTIVE_navigator-viz-delivery.md` D-1
**Inherits standards:** det-req-kit · NODE-SCHEMA v0.3.9 · NAMING_CONVENTION · REQ-01-sdk-node-home (parent) · REQ-02-n-level-tree-renderer · REQ-03-a11y-renderer-and-corpus-index · REQ-04-lift-lenses-to-shared-transform (the transform) · REQ-05-graph-topology-renderer (the FR-5 opt-in precedent)
**Audience:** operator / SDK contributors
**Trust boundary:** local filesystem + authored manifests only; no LLM, no network
**Data classification:** internal

> **Readable handle:** `feature/navigator-shared-lens-adoption`
> **Semantic name:** *Navigator wires the tree and a11y renderers through the shared node-lens transform and gives apply_node_lenses a direct consumer, so every renderer can inherit audience×fluency lenses without forking and no lens path stays dormant — while default (no-role) rendering stays byte-identical.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-09`

---

## 0. Why this exists — closing dormant D-1

The HTH retrospective (`RETROSPECTIVE_navigator-viz-delivery.md`) found dormant **D-1**: REQ-04 lifted the
audience×fluency lenses into a shared transform (`node_lenses`), but only the **graph** renderer (REQ-05)
consumes it. The **tree** (REQ-02) and **a11y** (REQ-03) renderers render raw `Node` labels and never
inherit the lenses; and `apply_node_lenses` has **0** direct external consumers (reached only internally
via `project_nodes`), so it is "thin ice" — a rename away from dead. REQ-04's claim "every renderer
inherits the lenses without forking" is therefore only partially realized. This REQ realizes it, using
the **opt-in pattern REQ-05 FR-5 already proved**: an optional `role`/`fluency`, soft-guarded
`project_nodes` consumption, and `role=None` → raw labels → byte-identical default.

## Overview

Give the tree and a11y renderers the same `role`/`fluency` seam the graph renderer has, routing labels
through `node_lenses.project_nodes` when a role is requested and falling back to raw `Node` labels
otherwise (byte-identical default). Give `apply_node_lenses` at least one **direct** consumer so it is no
longer dormant. Do not re-fork the lens helpers. Do not disturb the deterministic app-scaffold wireframe
path.

## Objectives

- **O-1:** The tree and a11y renderers can inherit the shared audience×fluency lenses (opt-in via `role`),
  realizing REQ-04's "every renderer inherits without forking" claim — target: a lensed render differs
  from the raw render for a jargon-bearing node; neither re-implements `_display_label`/`has_jargon`.
- **O-2:** No dormant lens path — target: `apply_node_lenses` has ≥1 direct consumer and the Spec Delivery
  Loop's `--reachability` probe reports it `wired` (was `DORMANT`/soft-only).
- **O-3:** Default (no-role) rendering is byte-identical — target: existing tree/a11y/wireframe tests pass
  unedited; no golden churn for the default path.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | Routing `compose` through `apply_node_lenses` double-applies `_display_label` (compose already lenses at `_item_view` time) → byte drift | PREP must confirm byte-safety; if not byte-safe, scope FR-3 to "give apply_node_lenses a direct consumer" a different way (or defer) rather than break the wireframe golden | high |
| quality | `project_nodes` returns a positional flat list; tree/a11y must key labels by `Node.key` over the same flattened set (the REQ-05 D3 impedance point) | flatten once, key by `Node.key`, mirror `render_graph`'s `_labels_via_lenses` | high |
| quality | Adding a `role` param changes tree/a11y output when a role IS passed → lensed goldens needed | default `role=None` → byte-identical; lensed mode gets its own new tests, not edited old goldens | medium |
| scope | Over-reaching into a `compose` refactor that risks the app path | app-scaffold byte-identity (REQ-01 FR-8) is the hard gate; FR-5 pins it | high |

## Functional requirements

- **FR-1 — Tree renderer inherits lenses (opt-in).** `render_navigator_tree_html` gains optional `role`/`fluency` params; when `role` is set it routes node labels through `node_lenses.project_nodes` (soft-import guarded, keyed by `Node.key` over the flattened nodes), else raw `Node` labels; `role=None` default is byte-identical. Name: the tree renderer routes labels through the shared node-lens transform when a role is requested and renders raw labels otherwise. Touches: `src/startd8/navigator/render_tree.py`, `src/startd8/navigator/cli_navigator.py`. Lives: code src/startd8/navigator/render_tree.py. Approve?: does role=None render byte-identically to today while a role applies the lens?. Verify: a jargon-bearing node renders humanised under `role=end_user` and raw under `role=None`; `render_tree.py` has no `_display_label`/`has_jargon` def. Serves: O-1
- **FR-2 — A11y renderer inherits lenses (opt-in).** `render_a11y_to_file` / `render_html` gain the same optional `role`/`fluency` seam with the same soft-guarded `project_nodes` routing and `role=None` byte-identical default. Name: the a11y renderer inherits the shared node-lens transform through the same opt-in role seam as the tree and graph renderers. Touches: `src/startd8/navigator/render_a11y.py`, `src/startd8/navigator/cli_navigator.py`. Lives: code src/startd8/navigator/render_a11y.py. Approve?: is the a11y default path byte-identical with lenses applied only under a role?. Verify: a11y render under `role=end_user` humanises a jargon node; `role=None` output is unchanged; no lens helper re-forked. Serves: O-1
- **FR-3 — apply_node_lenses gets a direct consumer (NR-4 path, PREP-decided).** Give `node_lenses.apply_node_lenses` a **direct** external call site so it is no longer dormant/thin-ice: the **tree** renderer calls `apply_node_lenses` directly on a flat item-view list (label = `node.does`) rather than only via `project_nodes`. The `compose` chokepoint route was **considered and rejected** — PREP proved it double-applies (`apply_node_lenses` adds an item-level `need_items` key → JSON keyset change → breaks the wireframe byte-identity golden), so `compose.py` is NOT touched (NR-4). Name: apply_node_lenses gains a direct external consumer in the tree renderer so the shared aggregate is no longer a dormant single-internal-caller path. Touches: `src/startd8/navigator/render_tree.py`. Lives: code src/startd8/wireframe_view/node_lenses.py. Approve?: does apply_node_lenses have ≥1 direct consumer without any byte drift to the app path?. Verify: the Spec Delivery Loop `--reachability` probe reports `apply_node_lenses` as `wired` (real ≥ 1), not `export-only`/`DORMANT`. Serves: O-2
- **FR-4 — Reachability green.** After this change the loop's reachability probe over the touched files reports **no dormant symbols** for the lens transform. Name: the reachability probe reports every public node-lens symbol wired after tree and a11y adoption. Touches: `scripts/navigator_spec_delivery_loop.py` (probe, unchanged), `src/startd8/wireframe_view/node_lenses.py`. Lives: code src/startd8/wireframe_view/node_lenses.py. Approve?: is the lens transform free of dormant public symbols?. Verify: `navigator_spec_delivery_loop.py --reachability src/startd8/wireframe_view/node_lenses.py` prints `no dormant symbols`. Serves: O-2
- **FR-5 — Byte-identity of the default + app path.** The deterministic app-scaffold wireframe path and the default (no-role) tree/a11y output stay byte-identical — no golden edits. Name: the app-scaffold wireframe path and default no-role tree and a11y output stay byte-identical with no golden edits. Touches: `tests/unit/wireframe/test_render_profile.py`, `tests/unit/navigator/`. Lives: test tests/unit/wireframe/test_render_profile.py. Approve?: do all existing byte-identity and determinism tests pass unedited?. Verify: `test_no_profile_is_byte_identical` + the wireframe determinism suite + existing tree/a11y tests pass without golden edits. Serves: O-3
- **FR-6 — No re-fork.** Neither the tree nor the a11y renderer re-implements the lens logic (`_display_label` / `has_jargon` / `_END_USER_ORDER`); they consume the shared transform only. Name: the tree and a11y renderers consume the shared lens transform without re-forking any lens helper. Touches: `src/startd8/navigator/render_tree.py`, `src/startd8/navigator/render_a11y.py`. Lives: code src/startd8/navigator/render_tree.py. Approve?: is there zero re-forked lens logic in the two renderers?. Verify: grep for `_display_label`/`has_jargon`/`_END_USER_ORDER` in both renderer modules returns 0. Serves: O-1

## Non-requirements

- **NR-1:** No new lens *behaviour* — this is adoption of the REQ-04 transform, not new humanisation rules.
- **NR-2:** No change to the graph renderer (already adopts the lenses).
- **NR-3:** Lensed-mode goldens are new tests, never edits to the existing default-path goldens.
- **NR-4:** If PREP finds routing `compose` through `apply_node_lenses` is not byte-safe, FR-3 satisfies "direct consumer" via the tree/a11y bridge instead — the wireframe golden is never sacrificed for the chokepoint.
