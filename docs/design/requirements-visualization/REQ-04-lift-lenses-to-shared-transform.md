# Lift Lenses to a Shared Node-View-Model Transform — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-14
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — spec-only deliverable; plan follows)*
**Inherits standards:** det-req-kit · NODE-SCHEMA v0.3.9 · REQ-01-sdk-node-home (parent) · REQ-02-n-level-tree-renderer · REQ-03-a11y-renderer-and-corpus-index
**Audience:** operator (SDK contributors; tree/a11y renderer adopters)
**Trust boundary:** local filesystem + authored manifests only; no LLM
**Data classification:** internal

> **Readable handle:** `feature/navigator-lifts-the-audience-fluency-debug-a0a42985`
> **Semantic name:** *Navigator lifts the audience × fluency × debug lenses out of the wireframe renderer into a shared Node-view-model transform so every renderer inherits them without forking.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-04`

---

## 0. Planning Insights (Reflective Update)

> Draft assumptions tested against the real code (`wireframe_view/compose.py`, `_template.py`,
> `view.py`, `navigator/render_tree.py`, `wireframe/profile.py`, `tests/unit/wireframe/`).
> Six corrections follow.

| v0.1 Draft Assumption | Planning Discovery | Impact |
|-----------------------|--------------------|--------|
| The lenses live only in `_template.py` (JS) | The lenses operate at **two layers**: a Python data-layer in `compose.py` (`role`/`fluency`/`voice` params driving `_display_label`, `_item_view`, `_is_gap_item`, section ordering, `need_items`, `todos`) and a JS presentation-layer in `_template.py` (the toggle controls, debug panel, PF-1 status-filter chips). REQ-04 can lift only the **data layer** to a shared transform; the JS layer is renderer-specific and cannot be shared without a major template overhaul | FR scope narrows to the Python data-layer lift; the JS layer (toggle, debug panel) is NR-5 |
| A "shared lens module" would be a new dataclass | The natural container is a pure function `apply_node_lenses(items, *, role, fluency) -> list[dict]` that produces a lens-annotated item-view list from a flat `list[Node]` — the existing `_item_view` / `_display_label` / `_is_gap_item` logic extracted verbatim. `compose()` becomes a thin wrapper calling this function. Byte-identity preserved because the logic is unchanged — only the call site moves. | FR-1 targets a module `wireframe_view/node_lenses.py`; compose.py calls through to it |
| The debug layer (structure/combined/scaffold/hide-scaffold) is a lens | The debug modes are **purely JS body-class toggles** (`body.structure-only`, `body.combined`, etc.) gated to `payload.profile` — they operate on the rendered DOM, not the view-model data. They are not data-layer lenses. Lifting them would require redesigning the JS machinery and is out of scope. | The debug panel stays in `_template.py`; NR-5 encodes this |
| The audience toggle (QW-1) embeds multiple pre-composed variants | `view.py` calls `compose()` four times (one per `_EMBED_COMBOS` entry) to produce the `variants` dict. The shared lens transform does NOT change this: `compose()` still calls `apply_node_lenses` once per variant, and the four-call fan-out stays. The transform is a factoring of a single compose call, not a change to the embed strategy. | FR-1 Verify: `len(payload["variants"]) == 4` unchanged after the refactor |
| The tree renderer could call the shared transform directly on `Node` objects | `apply_node_lenses` operates on the **item-view dict** (the `dict` that `_item_view` today produces), not the raw `Node` model. The tree renderer renders raw `Node` objects through its own `_tree_node_html`. To give the tree renderer the lenses, it must receive lens-annotated item-views — which means a `nodes → item_views` projection step must precede the lens call when the renderer is `tree`. FR-2 specs this bridge: `node_lenses.project_nodes(nodes, *, role, fluency)` that produces a `List[dict]` consumable by a renderer. | FR-2 (tree renderer integration) is a separate FR from FR-1 (the shared transform itself) |
| Byte-identity is proven by a new golden file | The existing `test_no_profile_is_byte_identical` (in `test_render_profile.py`) is the byte-identity gate — it asserts `render_html(plan) == render_html(plan, profile=None)`. After the refactor, this test must pass **without editing the golden or the assertion**. No new golden is needed; the existing test IS the gate. | FR-6 Verify cites `test_no_profile_is_byte_identical` + `test_visual_html` by name |

**Resolved open questions:**

- **OQ-1 (where does the shared transform live?) → `src/startd8/wireframe_view/node_lenses.py`.** Placing it in `wireframe_view/` means both `compose.py` (same package) and the tree/a11y renderers (which import from `wireframe_view`) can call it without circular imports. It imports only `wireframe.profile.RenderProfile` (for the `role` default) and stdlib — no dependency on `WireframePlan` or `_template.py`.
- **OQ-2 (does the tree renderer call the shared transform?) → Yes, via FR-2, but only for the item-view projection path.** The tree renderer's existing `_tree_node_html` is untouched. A new `project_nodes` function in `node_lenses.py` produces a lens-filtered item-view list for renderers that want the shared lenses without the full `WireframePlan`.
- **OQ-3 (byte-identity proof mechanism?) → existing test, no golden edit.** `test_no_profile_is_byte_identical` passes unchanged. Any gold-edit is a failing gate.
- **OQ-4 (do the JS controls move?) → No, NR-5.** The audience/depth toggle and the debug panel are renderer-specific JS and stay in their respective templates. The shared transform is a Python data-layer concern only.
- **OQ-5 (does this change the compose() signature?) → No.** `compose(plan, *, role, fluency, profile)` is unchanged from outside. The internal factoring routes the lens-sensitive logic through `apply_node_lenses`; callers see no difference.

---

### 0.1 Design-Principle Hardening

- **[Mottainai]** — `apply_node_lenses` is an **in-place extraction** of existing logic from `compose.py`, not a rewrite. Every line of lens logic (`_display_label`, `_is_gap_item`, `has_jargon`, `_plain_item_label`, `_END_USER_ORDER`, `GAP_STATUSES`, `HONEST_SKIP_ROUTES`) moves verbatim to `node_lenses.py`; `compose.py` imports and calls them. Zero logic is invented; the existing corpus of lens behaviour is the deliverable.
- **[Kagami]** — `compose.py` delegates to `node_lenses.py` (the canonical lens source). No copy of lens logic remains in `compose.py` (a shadow would defeat the entire purpose). NR-3 makes this explicit.
- **[Hitsuzen]** — The byte-identity of the app-scaffold path is not a test to pass by cleverness; it is the **only acceptance criterion that matters** for this refactor. The SOTTO principle governs: existing behaviour rides the refactored skeleton byte-for-byte.
- **[Accidental-Complexity anti-principle]** — REQ-04 does NOT add new lens behaviour. The scope is strictly factor-out (move + delegate); any new lens capability (a new debug mode, a new audience tier) is a follow-on tracked as NR-6. Adding new behaviour here would bury a behaviour change inside a refactor, defeating the byte-identity gate.

---

## Overview

Phase 3 of the requirements-visualization ladder (following REQ-01 / REQ-02 / REQ-03): address the
**factorization failure FF-1** identified in `VISUALIZATION_VARIANTS_ANALYSIS.md` §3. The audience ×
fluency × debug **lenses** — the crown jewel of the wireframe renderer — are welded into
`wireframe_view/compose.py` and `_template.py`. The N-level tree renderer (REQ-02) and the a11y
renderer (REQ-03) each carry their own HTML shells and cannot inherit the lenses; every new renderer
re-forks them.

The fix is the **second RenderProfile moment**: just as REQ-01 lifted domain vocabulary out of the
template into `wireframe/profile.py` (making the renderer domain-agnostic), REQ-04 lifts the
audience/fluency lens logic out of `compose.py` into a shared `node_lenses.py` module — a middleware
layer between the SOURCE (`Fᵢ: Domain → Node`) and the RENDERER (`Gⱼ: Node → View`). After the lift,
a visualization is `Gⱼ ∘ apply_node_lenses ∘ Fᵢ`: the lenses are a natural transform on the
view-model, not a private method of one `Gⱼ`.

**The scope is a pure factoring: no new lens behaviour, no new audiences, no changes to `_template.py`
JS. The hardest constraint is that the app-scaffold wireframe path remains byte-identical — existing
golden tests pass without edits.**

---

## Objectives

- O-1: The audience × fluency data-layer lenses (jargon filtering, label humanisation, `need_items` computation, section ordering, `todos` roll-up) live in one module (`wireframe_view/node_lenses.py`) callable by any renderer.
- O-2: `compose.py` delegates to `node_lenses.py` — no lens logic remains duplicated in `compose.py` itself.
- O-3: The tree renderer (REQ-02, `render_tree.py`) and the a11y renderer (REQ-03, when built) can call `node_lenses.project_nodes(nodes, *, role, fluency)` to get a lens-filtered item-view list without importing `WireframePlan`.
- O-4: The app-scaffold wireframe path is byte-identical after the refactor — `test_no_profile_is_byte_identical` and `test_visual_html` pass without golden edits and without modifying the test assertions.
- O-5: No new lens behaviour is introduced; this spec is a factoring, not a feature addition.

---

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | Byte-identity breaks because the extraction subtly changes argument evaluation order or default-value handling | FR-6 Verify: run `test_no_profile_is_byte_identical` + `test_visual_html` against the refactored code before merging; any failure is a blocking gate | high |
| quality | `apply_node_lenses` duplicates instead of replaces the lens logic in `compose.py` (Kagami violation) | FR-1 Verify: grep `compose.py` after the refactor for each of `_display_label` / `_is_gap_item` / `_END_USER_ORDER` / `GAP_STATUSES` — each must output 0 (all moved to `node_lenses.py`); FR-6 Verify catches any behavioural divergence | high |
| scope-creep | Adding new lens behaviour (a new debug mode, a new audience tier) during the refactor buries a behaviour change inside a factoring | NR-6: new lens capabilities are explicitly out of scope; any new behaviour must be a follow-on FR | medium |
| architecture | Circular import: `node_lenses.py` imports from `wireframe/plan.py` to type-check items, which imports back | `node_lenses.py` accepts plain `dict` item-views (already produced by `_item_view`); it does NOT import `WireframePlan` or `WireframeItem`; `from __future__ import annotations` for forward refs if needed | high |
| quality | `project_nodes` bridge (FR-2) invents a new projection path that diverges from `compose.py`'s projection | FR-2 Verify: `project_nodes(nodes_from_plan, role=r, fluency=f)` must produce the same `items` list as `compose(plan, role=r, fluency=f)["sections"][i]["items"]` for each section `i`; a parity test guards this | high |
| availability | The tree renderer's `render_navigator_tree_html` is not modified — it still renders raw `Node` objects; callers who want lens-filtered output must call `project_nodes` first | NR-4: the tree renderer's internal `_tree_node_html` is not changed; the bridge is opt-in, not injected | low |

---

## Profile

Declared profile: **internal** (SDK contributors and multi-renderer adopters; not end-user facing)

---

## Functional requirements

- **FR-1 — Shared lens transform extracted to node_lenses module.** A new module `src/startd8/wireframe_view/node_lenses.py` is created containing: `apply_node_lenses(item_views, *, role, fluency, voice) -> list[dict]` (filters jargon items for `end_user`, applies `_display_label`, computes `need_items`, sorts by `_END_USER_ORDER` when `voice == "end_user"`); the constants `GAP_STATUSES`, `HONEST_SKIP_ROUTES`; the helper functions `has_jargon`, `_display_label`, `_plain_item_label`, `_is_gap_item`, `_humanize`, `_END_USER_ITEM_LABELS`, `_END_USER_ORDER`; and `apply_section_lenses(sections, *, voice) -> list[dict]` (the section-level ordering and `need_items` aggregation). All logic is moved verbatim from `compose.py` — no semantic changes. `compose.py` imports and calls these functions; the extracted names are removed from `compose.py` (not left as aliases). Name: NodeLenses extracts lens logic to a shared module so any renderer can call it without importing compose. Touches: `src/startd8/wireframe_view/node_lenses.py` (to-be-created), `src/startd8/wireframe_view/compose.py`. Lives: code src/startd8/wireframe_view/node_lenses.py. Verify: (a) `grep -c "def _display_label\|def _is_gap_item\|GAP_STATUSES\|_END_USER_ORDER" src/startd8/wireframe_view/compose.py` outputs `0` for each name (definitions moved); (b) `from startd8.wireframe_view.node_lenses import apply_node_lenses, has_jargon, GAP_STATUSES` imports cleanly from a cold Python process; (c) `compose(plan, role="end_user", fluency="intermediate")` output is byte-identical to the pre-refactor output. Serves: O-1, O-2.

- **FR-2 — project_nodes bridge for tree and a11y renderers.** `node_lenses.py` gains `project_nodes(nodes, *, role="architect", fluency="intermediate") -> list[dict]`, where `nodes` is a `List[Node]` (from `navigator.models`). The function produces a lens-filtered item-view list equivalent to what `compose()` would produce for the same nodes, without requiring a `WireframePlan`. Each returned dict has at minimum: `label`, `status`, `detail`, `technical`, `need_items` (empty list for non-gap nodes). Tree/a11y renderers call this to get lens-filtered output; calling it is opt-in (callers that want raw `Node` rendering skip it). Name: NodeLenses provides a project_nodes bridge so the tree and a11y renderers can consume lenses without a WireframePlan. Touches: `src/startd8/wireframe_view/node_lenses.py`, `tests/unit/wireframe_view/test_node_lenses.py` (to-be-created). Lives: code src/startd8/wireframe_view/node_lenses.py. Verify: (a) for a `Node` with `does="FR-1 sign in"` and `status="spec"`, `project_nodes([node], role="architect")` returns a list with `len == 1` and `result[0]["label"] == "FR-1 sign in"`; (b) for a `Node` whose label matches `_JARGON_RE`, `project_nodes([node], role="end_user")["technical"] == True`; (c) `project_nodes(nodes_from_plan_items, role=r, fluency=f)` item labels match `compose(plan, role=r, fluency=f)` item labels for the same set of nodes (parity test). Serves: O-3.

- **FR-3 — node_lenses module is importable standalone without wireframe plan dependencies.** `node_lenses.py` has zero imports from `wireframe.plan`, `wireframe_view.compose`, or `wireframe_view.view`. Its only internal SDK imports are `wireframe.delivery_roles` (for `effective_voice`) and `navigator.models.Node` (for `project_nodes` type annotation); both are already standalone. This ensures tree/a11y renderers can import `node_lenses` without pulling in the full wireframe plan machinery. Name: NodeLenses is importable standalone so renderers outside the wireframe pipeline incur no plan-machinery dependency. Touches: `src/startd8/wireframe_view/node_lenses.py`. Lives: code src/startd8/wireframe_view/node_lenses.py. Verify: in a test that imports ONLY `from startd8.wireframe_view.node_lenses import apply_node_lenses, project_nodes`, no `WireframePlan`, `WireframeItem`, or `WireframeSection` name appears in `sys.modules` after the import. Serves: O-3.

- **FR-4 — node_lenses public surface exported from wireframe_view __init__.** `wireframe_view/__init__.py` exports `apply_node_lenses`, `project_nodes`, `has_jargon`, `GAP_STATUSES`, and `HONEST_SKIP_ROUTES` so adopters can import them from the package root without knowing the submodule path. Existing exports from `wireframe_view/__init__.py` are unchanged. Name: NodeLenses public surface is exported from wireframe_view so adopters get a stable import path. Touches: `src/startd8/wireframe_view/__init__.py`. Lives: code src/startd8/wireframe_view/__init__.py. Verify: `from startd8.wireframe_view import apply_node_lenses, project_nodes, has_jargon` resolves cleanly; existing `from startd8.wireframe_view import ...` imports in `tests/` continue to resolve (no symbols removed from the prior public surface). Serves: O-1, O-3.

- **FR-5 — compose.py delegates to node_lenses and is internally lean.** After the refactor, `compose.py` contains: (a) the `compose()` function (unchanged signature and return value); (b) `parse_form_detail` and the form/list view helpers (`_form_entity`, `_multiline_fields`, `_item_view`, `_entity_columns`) which are plan-specific and stay in compose; (c) the plain-language summary helpers (`_plain_shape`, `_plain_status`, `_plain_ready`, `_plain_content`, `_app_name`, `_plural`) which are plan-specific and stay; (d) `_csv`. The lens logic (`_display_label`, `_plain_item_label`, `_humanize`, `_END_USER_ITEM_LABELS`, `_END_USER_ORDER`, `GAP_STATUSES`, `HONEST_SKIP_ROUTES`, `has_jargon`, `_is_gap_item`) is removed from compose and imported from `node_lenses`. Name: compose delegates lens logic to node_lenses so compose contains only plan-specific view construction. Touches: `src/startd8/wireframe_view/compose.py`. Lives: code src/startd8/wireframe_view/compose.py. Verify: (a) `wc -l src/startd8/wireframe_view/compose.py` decreases by at least the number of lines moved (≥ 60 lines removed); (b) the module still imports cleanly; (c) all existing `tests/unit/wireframe/test_composition_matrix.py` tests pass unchanged. Serves: O-2.

- **FR-6 — App-scaffold wireframe path byte-identical after refactor.** The existing byte-identity acceptance gate (`test_no_profile_is_byte_identical`) passes without modifying the test file or its assertions. `test_visual_html` passes without golden edits. `compose(plan)` for a classic app plan (no profile, no Node grounding, `role="architect"`, `fluency="intermediate"`) produces JSON byte-for-byte identical to the pre-refactor output — same keyset, same values, same ordering (`sort_keys=True`). This is the top acceptance gate: if it fails, the refactor is rejected regardless of other test results. Name: AppScaffold wireframe remains byte-identical after the lens lift so the deterministic dollar-zero path is unaffected. Touches: `tests/unit/wireframe/test_render_profile.py`, `tests/unit/wireframe/test_visual_html.py`, `tests/unit/wireframe/test_determinism_and_json.py`. Lives: test tests/unit/wireframe/test_render_profile.py. Verify: `pytest tests/unit/wireframe/test_render_profile.py::test_no_profile_is_byte_identical tests/unit/wireframe/test_visual_html.py tests/unit/wireframe/test_determinism_and_json.py` exits 0 without any test file modification. Serves: O-4.

- **FR-7 — Parity test guards compose vs project_nodes equivalence.** A new test `tests/unit/wireframe_view/test_node_lenses.py` contains a parity assertion: for a fixture plan with ≥2 sections and ≥3 items per section, `project_nodes(nodes, role=r, fluency=f)` item `label` values must equal the corresponding `compose(plan, role=r, fluency=f)` section item `label` values for `role in ("end_user", "architect")` and `fluency in ("beginner", "intermediate", "advanced")`. This guards against the `project_nodes` bridge drifting from `compose`'s lens application. Name: NodeLenses parity test guards project_nodes against compose drift so the bridge stays equivalent. Touches: `tests/unit/wireframe_view/test_node_lenses.py` (to-be-created). Lives: test tests/unit/wireframe_view/test_node_lenses.py. Verify: the parity test is present, covers all 6 role×fluency combos listed above, and passes on first run. Serves: O-3, O-4.

---

## Non-goals

- NR-1: Adding new lens behaviour (new audiences, new fluency levels, new debug modes) — this spec is a pure factoring; new capabilities are follow-on FRs.
- NR-2: Changing the `compose()` function signature, its return shape, or its caller contract — the refactor is internal only.
- NR-3: Leaving any copy of the lens logic in `compose.py` as an alias or backward-compat shim — the whole point is one canonical home. A shim is a Kagami violation; callers that need the functions import from `node_lenses`.
- NR-4: Modifying `render_tree.py`'s internal `_tree_node_html` or `_tree_body_html` to consume the shared lenses — the bridge is opt-in (`project_nodes`); callers who prefer raw Node rendering skip it. REQ-03 may opt in when it is built.
- NR-5: Lifting the JS presentation-layer lenses (audience/depth toggle, debug panel, structure-only/combined modes, PF-1 status-filter chips) out of `_template.py` — those are renderer-specific DOM operations; lifting them would require redesigning the JS machinery and is a separate, larger undertaking.
- NR-6: Building a new renderer (4th renderer) as part of this work — REQ-04 is the prerequisite for making new renderers cheap; the renderers themselves are follow-on.
- NR-7: Changing the `_EMBED_COMBOS` fan-out or the `variants` embed strategy in `view.py` — the compose call site is unchanged; only the internal routing within each `compose()` call changes.
- NR-8: Providing a JS-side shared lens payload (serialised lens config that JS renderers read) — out of scope; the shared transform is a Python data-layer concern only.

---

## Owned fields

Only the factored implementation controls: the internal call routing inside `compose()` (delegates to `node_lenses`). No authored content, no runtime config, no user-facing flags change. The `role` and `fluency` parameters remain the caller's concern, unchanged.

---

## Contract projection

- **Backend:** python-cli-surface
- **Vocabulary home (cite):** `~/Documents/dev/dev-os/det-req-kit/SCHEMA.md` §8 `python-cli-surface` · living homes `~/Documents/dev/startd8-sdk/pyproject.toml`, `~/Documents/dev/startd8-sdk/src/startd8/wireframe_view/` · grammar cite `~/Documents/dev/dev-os/NODE-SCHEMA.md`

This REQ is a library/module refactor: its seams are Python modules, functions, and constants — not
CLI surfaces. Those seams are carried as **file-path `Touches:` / `Lives:` evidence on the FRs above**,
not as `python-cli-surface` projection entries (declaring library symbols as CLI kinds would invent a
CLI structure this REQ does not add). For reference, the library seams the FRs deliver are:

- `node_lenses.py` (new module) — the shared lens transform (FR-1, FR-2, FR-3)
- `apply_node_lenses` (function) — item-view list → lens-filtered list (FR-1)
- `project_nodes` (function) — `List[Node]` → lens-filtered item-view list (FR-2)
- `has_jargon` (function) — moved from `compose.py`; re-exported from `wireframe_view/__init__.py` (FR-4)
- `GAP_STATUSES`, `HONEST_SKIP_ROUTES` (constants) — moved from `compose.py`; re-exported (FR-4)
- `compose.py` (modified module) — delegates lens logic; signature unchanged (FR-5)
- `wireframe_view/__init__.py` (modified) — new exports for the moved symbols (FR-4)

---

## Planning Insights — what the planning pass changed about the draft

> The four most significant draft corrections. Future reviewers: these were wrong in the first draft.

1. **The lens lift is a two-layer problem, and REQ-04 addresses only the Python data layer.** The draft assumed lifting the lenses meant one module encompassing both the Python logic and the JS toggle/debug machinery. Reading `_template.py` (the JS) and `compose.py` (the Python) clarified they are fundamentally different: the Python layer produces the view-model data; the JS layer renders controls over it. The JS controls are DOM operations that cannot be extracted without redesigning the template architecture. NR-5 encodes this.

2. **Byte-identity is not a new golden file — it is the existing `test_no_profile_is_byte_identical` test.** The draft assumed a new golden capture would be needed. Reading `test_render_profile.py:34` showed the test already asserts `render_html(plan) == render_html(plan, profile=None)` — a live byte-for-byte equality check, not a stored golden. After the refactor, this test must pass without any modification. FR-6 Verify names this test explicitly as the top gate.

3. **`project_nodes` is a bridge, not a replacement for the compose path.** The draft framed FR-2 as "the tree renderer calls the lens module directly". Reading `render_tree.py` revealed the tree renderer works on raw `Node` objects via `_tree_node_html`, which has no concept of `role`/`fluency`. The bridge (`project_nodes`) is an opt-in function that a renderer calls before its own rendering pipeline if it wants lens-filtered item-views; it does not replace `_tree_node_html`. This is why FR-7 adds a parity test to guard the bridge against divergence from `compose()`.

4. **`node_lenses.py` must not import `WireframePlan` — the independence constraint is the whole point.** The draft described the module vaguely as "shared". Reading `project.py` (which bridges `Node → WireframePlan`) and the import chains revealed that if `node_lenses.py` imported `WireframePlan` it would drag the entire wireframe plan machinery into the tree renderer's dependency closure, defeating the purpose. FR-3 makes this a hard constraint with an explicit `sys.modules` Verify.

---

## Appendix A — Accepted (with where merged)

*(empty at v0.1 — no CRP review run yet)*

## Appendix B — Rejected (with rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| — | Lift the JS debug panel (structure/combined/scaffold) into a shared JS snippet | v0.1 draft | The JS controls are DOM operations on `body.classList`; they are renderer-specific and require each renderer to have compatible HTML structure (`.item[data-status]`, `.node-meta`, etc.). A shared JS snippet would couple renderer HTML to a common schema — a larger architectural change. NR-5. | 2026-08-14 |
| — | Add a new `debug_mode` parameter to `apply_node_lenses` for the structure-only/combined modes | v0.1 draft | Those modes are toggled purely in JS by body-class; they do not change the Python view-model data. Adding a Python `debug_mode` would be a no-op data-layer field that only the JS reads — accidental complexity. NR-1. | 2026-08-14 |

## Appendix C — Incoming review rounds

*(ready for CRP — see focus file `crp-focus-lift-lenses-to-shared-transform.md` when created)*

---

*v0.1 — Post planning-pass hardening. Byte-identity strategy: existing `test_no_profile_is_byte_identical` is the top acceptance gate; refactor extracts logic verbatim, compose delegates. Lens lift scope: Python data layer only (JS presentation layer NR-5). Ready for CRP review.*
