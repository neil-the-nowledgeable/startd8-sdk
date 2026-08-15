# N-Level Tree Renderer — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.3.1   **Date:** 2026-08-14
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — this is the spec-only deliverable; plan follows)*
**Inherits standards:** det-req-kit · NODE-SCHEMA v0.3.9 · REQ-01-sdk-node-home (parent)
**Audience:** operator (benchmark / dev-os / legal-navigator adopters)
**Trust boundary:** local filesystem + pre-projected NODE-SCHEMA-JSON; no LLM
**Data classification:** internal

> **Readable handle:** `feature/navigator-n-level-tree-renderer`
> **Semantic name:** *Navigator renders Node trees to arbitrary depth via a dedicated tree renderer, reusing the existing wireframe path for 2-level projections and serving the three adopting consumers.*

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (draft assumptions) and v0.2 (after planning against the real code).
> Planning against `navigator/project.py`, `wireframe_view/`, `wireframe/plan.py`, and
> ContextCore `navigator/render.py` revealed 6 corrections:

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| The tree renderer would extend `WireframeItem` with nested children (option a) or add a depth attribute (option c) | CC implemented **option (b)**: an independent tree renderer (`render_navigator_tree_html`) with its own CSS/JS template that recurses `node.children` — it does NOT touch `WireframePlan` or `WireframeItem` at all | Design recommendation = option (b); the wireframe plan stays depth-2; no WireframeItem extension needed |
| The audience × fluency lenses (the "crown jewel") would be reused by the tree renderer | The lenses are coupled to `WireframePlan` + the compose/view pipeline; the tree renderer from CC uses its own dark-mode `_TREE_CSS`/`_TREE_JS` — it is a **separate surface** from the wireframe | FR-3 is simplified: lenses are reused only in the `--renderer wireframe` path (unchanged); the tree renderer carries its own presentation; NR-2 clarified |
| The CC `render.py` had one live copy of `_tree_node_html` | CC `render.py` (1023 lines) has **duplicate top-level defs** — `_tree_node_html` at lines 378 and 824, `render_navigator_tree_html` at 502 and 953. The 824/953 pair is live (later def wins in Python); the 378/502 pair is dead code | FR-1 must explicitly port only the live (824/953) pair; do NOT carry over the shadowed dead pair |
| `--source nodes-json` was a minor optional seam | `--source nodes-json` is the **primary adopter seam** — benchmark/dev-os projectors emit a pre-projected JSON graph and want to pipe it into the tree renderer; this is the highest-value FR for unblocking REQ-10 | FR-2 (nodes-json source) elevated to critical; it pairs with FR-1 to form the minimum viable unblocking slice |
| `nodes_to_json` dropped `children` silently | Confirmed: `project.py:218-238` iterates nodes as a flat list, omitting `children`/`child_keys` from JSON output | FR-4 (JSON carries children) is the prerequisite for the `nodes-json` round-trip |
| The tree renderer would add `--renderer` as a separate concern from `--source` | The natural pairing is `--source nodes-json --renderer tree` (default); `--source capability-index|requirements --renderer wireframe` (default for backward compat); both flags are needed on the `build` command | FR-5 (CLI flags) refactored to reflect the default-by-source pairing |

**Resolved open questions:**

- **OQ-1 (design tension — which option?) → option (b), independent tree renderer.** A new `render_tree.py` module alongside `project.py`, porting the live CC pair (lines 824–1023). WireframeItem is byte-identical. The app-scaffold path is completely unaffected — the tree renderer lives in a separate module that the wireframe path never imports.
- **OQ-2 (do the lenses compose with the tree?) → No, they are different surfaces.** The wireframe lenses (audience × fluency) ride the `WireframePlan` → compose → template pipeline. The tree renderer has its own dark-UI HTML shell with search + expand/collapse. Adopters choose a renderer via `--renderer` flag; no mixing.
- **OQ-3 (byte-identity for app-scaffold path?) → Guaranteed by option (b).** Because the tree renderer is a separate module that the wireframe pipeline never imports, no existing WireframePlan/WireframeItem/compose paths change. The determinism tests pass without golden edits.
- **OQ-4 (dead code in CC render.py?) → Port only lines 824–1023.** The 378–502 pair is unreachable (shadowed); carry over only the live pair.
- **OQ-5 (debug layer + expand/collapse in tree?) → carried by the tree's own JS.** `toggleAll(open)` in `_TREE_JS`, `open_depth` parameter for default expansion depth, and keyword search are the CC tree's debug/navigation affordances. Scaffold-mode and the profiled debug panel (FR-11 through FR-15 of REQ-01) are wireframe-path features only; they do not apply to the tree renderer.

---

### 0.1 Lessons-Learned Hardening (v0.3)

> Design-docs lessons base consulted (`Design_Docs_LESSONS_LEARNED.md`). ContextCore
> `lesson recall` MCP unavailable in this environment — recorded as checked-empty.
> Applied three lessons:

- **[Phantom-reference audit / Leg 6 #6/#13]** — Grepped CC `render.py` before citing line numbers. Confirmed: the live copy is at 824/953, NOT 378/502. FR-1 Verify now specifies "port only the live (non-shadowed) pair" explicitly. The dead-code defect note from the a11y-renderer brief is carried into FR-1 so the implementer sees it at the exact FR they'll act on.
- **[Vocabulary single-source / Leg 5]** — `open_depth`, `_TREE_CSS`, `_TREE_JS`, `_search_blob`, `_facets_html`, `_tree_body_html` are CC-originated names cited here by reference; this REQ does not redefine their semantics — it cites CC `render.py:824-1023` as the port source. Contract Projection cites the source file.
- **[Mottainai / reuse]** — The tree renderer reuses CC's implementation; the wireframe renderer reuses the existing `project.py`/`wireframe_view` path. No third renderer is built. NR-2 made explicit: do not fork the wireframe_view pipeline for the tree use-case.

---

### 0.2 Design-Principle Hardening (v0.3.1)

> Checked the PRINCIPLE-INDEX.md (dev-os) and startd8-sdk `docs/design-princples/`. Applied four principles:

- **[Mottainai]** — Port the CC live tree renderer; do not build a new one. `nodes_to_json` extended in-place (add children), not replaced. NR-2 (no forking the wireframe pipeline for the tree case). This saves all the CC CSS/JS/search/expand authoring. Applied to FR-1/FR-4/NR-2.
- **[Genchi Genbutsu]** — Bound to the real CC `render.py` source (read lines 824–1023 directly before specifying); confirmed the `open_depth`/`_count_nodes`/`_TREE_CSS`/`_TREE_JS` contract. Confirmed `nodes_to_json` drops children (project.py:218-238, direct read). No guessing. Bound to real ContextCore CLI path (`cli/navigator.py` `--renderer {wireframe,tree}` — read directly). FR-1 Touches cites `src/startd8/navigator/render_tree.py` (to-be-created) as the explicit target.
- **[Kagami — edit the source, not the mirror]** — `nodes_to_json` currently omits `children`. The fix lives in `project.py` (the source), not in a post-processing wrapper that re-adds children after the fact. Similarly, the dead-code pair in CC must not be ported (carrying dead code is a Kagami defect — a shadow of the original that will confuse a future reader). FR-4 touches `project.py` directly.
- **[Accidental-Complexity anti-principle]** — Rejected option (a) (extend WireframeItem with nested children) and option (c) (flatten with depth attribute) because both would introduce machinery (recursive dataclasses / depth-indented flattening) to compensate for a non-problem. Option (b) — a separate renderer — is the principled path: the wireframe plan is a 2-level app-layout shape; the tree renderer is a recursive node-navigation shape. They serve different use-cases. Adding depth to WireframeItem would be accidental complexity accumulated for the wrong reason.

---

## Overview

Phase 2 of the requirements-visualization ladder
([`TOP_DOWN_IMPROVEMENT_PLAN.md`](./TOP_DOWN_IMPROVEMENT_PLAN.md)): close the gap between the
forward-home navigator (`src/startd8/navigator/`) and the prior-home ContextCore navigator. The SDK
`Node` model already carries `children`/`child_keys` (a tree), but nothing renders them recursively.
The prior home (ContextCore `navigator/render.py`) has a working N-level tree renderer; this work ports
it (live copy only), extends the JSON output to carry the tree, adds the `--source nodes-json` adopter
seam, and wires the `--renderer` CLI flag — making the forward home fully capable for the three
adopting consumers.

**Three adopters unblocked by this spec:**

| Adopter | What they need | Key FR |
|---|---|---|
| dev-os REQ-10 (benchmark node tree) | Emit a pre-projected Node graph JSON; pipe to `startd8 navigator build --source nodes-json --renderer tree` | FR-1, FR-2, FR-4, FR-5 |
| startd8-work legal navigator | Same pipe (legal navigator already emits NODE-SCHEMA-JSON via `navigator_export.py`) | FR-1, FR-2, FR-5 |
| dev-os projectors | `startd8 navigator build --source nodes-json --format json` round-trip with children preserved | FR-4 |

**The design recommendation (from §0 OQ-1):**

> **Option (b): a new recursive tree renderer alongside the wireframe plan, not extending WireframeItem.**
>
> The wireframe plan (sections → items, depth 2) is an *app-layout shape* optimized for the audience
> × fluency lenses. The tree renderer is a *node-navigation shape* optimized for recursive drill-down.
> They serve different use-cases and carry different presentations. Mixing them would be accidental
> complexity. Option (b) keeps each surface clean and byte-identical from the other's perspective.

---

## Objectives

- O-1: An adopter can pipe a pre-projected NODE-SCHEMA-JSON graph into `startd8 navigator build --source nodes-json --renderer tree` and receive a self-contained, offline, searchable N-level HTML drill-down tree.
- O-2: The JSON output of `startd8 navigator build --format json` preserves `children` and `child_keys` so downstream consumers can round-trip the full tree without information loss.
- O-3: The existing 2-level wireframe path (audience × fluency lenses, app-scaffold byte identity, profiled debug layer) is completely unaffected by this work — the determinism golden tests pass without edits.
- O-4: The three adopting consumers (dev-os REQ-10, legal navigator, dev-os projectors) can render through the SDK navigator without a 4th renderer, without rendering through ContextCore, and without carrying their own tree-rendering code.

---

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | Porting the dead-code pair from CC render.py instead of the live pair | FR-1 Verify: grep the ported module for duplicate top-level defs (must = 1 occurrence each); unit test calls the function and confirms N-level recursion | high |
| quality | `nodes_to_json` children extension changes existing JSON golden (breaks adopter parsers already consuming the flat shape) | FR-4 Verify: existing consumers only iterated the flat `nodes` array; `children` is additive (was absent, now present). Check the two known consumers (legal navigator fallback parser, dev-os REQ-10 projector) — both stated they need children, so additive is the correct direction. No regression risk. | medium |
| quality | App-scaffold wireframe path picks up tree renderer import and breaks byte-identity | option (b) keeps `render_tree.py` in a separate module; the wireframe path never imports it. FR-6 Verify: `test_no_profile_is_byte_identical` passes without golden edits | high |
| availability | `--source nodes-json` admits untrusted Node JSON (XSS via key/does/attributes) | FR-2 Verify: the tree renderer uses `html.escape` on every user-visible field (inherited from CC render.py:825-829 which was hardened in issues #398/#400) — must confirm each interpolation in the ported code is escaped | high |
| scope-creep | Porting the full CC navigator (a11y, corpus-index, sources_seats, sources_conversations) | FR-1 through FR-5 port only the tree renderer + nodes-json source + CLI flags. Full a11y/corpus-index = NR-3 | medium |
| quality | Dead CC live-pair (`_search_blob`, `_facets_html`, `_tree_body_html`) XSS mitigations (issues #398/#400) missed if port is naïve | FR-1 explicitly cites these helper functions by name as part of the port scope; Verify requires a fixture with `<script>` in key/does to confirm HTML output is escaped | medium |

---

## Profile

Declared profile: **internal** (adopter consumers are dev-os, startd8-work, benchmark — not end-users directly)

---

## Functional requirements

- **FR-1 — Tree renderer ported from CC live pair.** The SDK gains `src/startd8/navigator/render_tree.py` containing `_tree_node_html(node, depth, open_depth)` + `render_navigator_tree_html(nodes, out_path, *, title, subtitle, open_depth, status_legend, readiness)`, ported from ContextCore `navigator/render.py` lines 824–1023 (the live pair — the 378–502 pair is dead code and must not be included). The port carries all XSS mitigations (`html.escape` on every interpolation; `_safe_href`/`_safe_color` guards from lines 700–729; `_facets_html`, `_tree_body_html`, `_search_blob`, `_live_row_html`, `_attr_row_html` helper set). No import of ContextCore. Name: Navigator ports the CC live tree renderer so it can render Node trees to arbitrary depth without ContextCore. Touches: `src/startd8/navigator/render_tree.py` (to-be-created). Lives: code src/startd8/navigator/render_tree.py. Verify: (a) `grep -c "def _tree_node_html" src/startd8/navigator/render_tree.py` outputs `1` (no duplicate); (b) a fixture with `children` 3 levels deep produces HTML with ≥3 nested `<details>` elements; (c) a fixture with `<script>alert(1)</script>` in `node.key` produces HTML where no `<script>` tag appears unescaped. Serves: O-1, O-4.

- **FR-2 — `--source nodes-json` adopter seam.** `startd8 navigator build` gains `--source nodes-json` accepting a file path to a pre-projected NODE-SCHEMA-JSON payload (the shape `nodes_to_json` emits: `{"source": ..., "nodes": [...]}`) and loading it into a `List[Node]`. Validation: the top-level `nodes` array must be present; each item must have `key` and `does`; unknown fields are ignored (forward-compatible). An invalid/missing file exits non-zero with a human-readable error. Name: Navigator accepts a pre-projected nodes-json file as a source so benchmark and legal-navigator adopters can pipe their projections into the renderer. Touches: `src/startd8/navigator/cli_navigator.py`, `src/startd8/navigator/sources_node_schema.py` or a new `sources_nodes_json.py`. Lives: code src/startd8/navigator/cli_navigator.py. Verify: `startd8 navigator build --source nodes-json --file <fixture.json> --renderer tree --out /tmp/tree.html` exits 0 and the HTML contains the fixture's root node key. Serves: O-1, O-4.

- **FR-3 — `--renderer` CLI flag with source-paired defaults.** `startd8 navigator build` gains `--renderer {wireframe,tree}`. Default is **`tree`** when `--source nodes-json`; default is **`wireframe`** for all other sources (backward-compatible). `--renderer wireframe` always uses `render_nodes_html` + `nodes_to_wireframe_plan`; `--renderer tree` always uses `render_navigator_tree_html`. The two renderers are mutually exclusive per invocation (no mixing). Name: Navigator wires a renderer flag with source-paired defaults so adopters get the right renderer without extra flags. Touches: `src/startd8/navigator/cli_navigator.py`. Lives: code src/startd8/navigator/cli_navigator.py. Verify: (a) `startd8 navigator build --source capability-index --format html --out /tmp/cap.html` (no `--renderer`) still produces the wireframe HTML (audience/fluency lenses present); (b) `startd8 navigator build --source nodes-json --file f.json --out /tmp/tree.html` (no `--renderer`) produces tree HTML (`<details class="node"`). Serves: O-1, O-3.

- **FR-4 — `nodes_to_json` carries children.** `project.py:nodes_to_json` is extended to include `children` (recursive, same shape as a node entry) and `child_keys` in each node dict. Nodes with no children emit `"children": []`. The existing flat fields (`key`, `does`, `status`, `wont`, `lives`, `ships_when`, `confidence`, `triggers`, `category`, `orientation`, `route_state`, `attributes`) are unchanged. Name: nodes_to_json carries children so the JSON format round-trips the full tree without information loss. Touches: `src/startd8/navigator/project.py`, `tests/unit/navigator/test_models.py`. Lives: code src/startd8/navigator/project.py. Verify: a `Node` with two `children` (each with one child) produces JSON where `nodes[0].children` has length 2 and `nodes[0].children[0].children` has length 1; `nodes[0].children` is `[]` for a leaf node. Serves: O-2.

- **FR-5 — `open_depth` parameter exposed in CLI.** `startd8 navigator build --renderer tree` accepts `--open-depth <int>` (default 2) forwarded to `render_navigator_tree_html`. This controls how many levels of `<details>` are expanded on load; deeper trees benefit from a shallower default. Name: Navigator exposes open-depth for tree renders so adopters tune the default expansion level for their tree depth. Touches: `src/startd8/navigator/cli_navigator.py`. Lives: code src/startd8/navigator/cli_navigator.py. Verify: `--open-depth 1` produces HTML where only depth-0 nodes have `open` attribute; depth-1 nodes do not. Serves: O-1.

- **FR-6 — App-scaffold byte identity preserved.** The deterministic app-scaffold wireframe path (no profile, no Node grounding) remains byte-identical: no new keys in compose JSON, no new imports in `wireframe/plan.py` or `wireframe_view/`, no changes to `_template.py`. Name: App-scaffold wireframe remains byte-identical after the tree renderer lands so the deterministic $0 path is unaffected. Touches: `tests/unit/wireframe/test_render_profile.py`, `tests/unit/wireframe/test_determinism_and_json.py`. Lives: test tests/unit/wireframe/test_render_profile.py. Verify: `test_no_profile_is_byte_identical` passes without golden edits; `test_visual_html` passes without golden edits; `compose(plan)` keyset for a classic app plan is unchanged. Serves: O-3.

---

## Non-goals

- NR-1: Extending `WireframeItem` with nested children or a `depth` attribute (option a/c — rejected in §0 OQ-1).
- NR-2: Reusing the audience × fluency lenses (wireframe_view/compose/template pipeline) in the tree renderer. The tree renderer carries its own HTML shell. The lenses are the crown jewel of the wireframe path; they are not ported to the tree surface (different use-case, different presentation contract).
- NR-3: Porting the full CC navigator family — `render_a11y.py`, `render_index.py`, `sources_seats.py`, `sources_conversation.py`, graph-projection, role-inventory, etc. This spec ports only the drill-tree surface (items 1–4 of the a11y-renderer track brief).
- NR-4: Building a new CSS design system or theme for the tree renderer. Port CC's dark-mode `_TREE_CSS`/`_TREE_JS` as-is (it is offline, no CDN dependency); Tier-2 theming is deferred.
- NR-5: Wiring the tree renderer into the profiled debug panel (FR-11 through FR-15 of REQ-01 are wireframe-path features).
- NR-6: Emitting the status-filter, scaffold-mode toggle, or hide-app-scaffold-chrome controls in the tree renderer (those are wireframe_view template features).
- NR-7: Automatic tree construction from flat sources (capability-index → tree). The tree renderer accepts pre-projected trees via `--source nodes-json`; building the tree from flat sources is the adopter's projection responsibility.
- NR-8: Real-time `--watch` / live-reload for the tree renderer (EC-3 from the wireframe path is out of scope here).

---

## Owned fields

Only humans/adopters control: the pre-projected `nodes-json` payload (key/does/children/status set by the adopter's projector); `open_depth` CLI parameter; `title`/`subtitle` arguments to `render_navigator_tree_html` (for named tree views).

---

## Contract projection

- **Backend:** python-cli-surface
- **Vocabulary home (cite):** `~/Documents/dev/dev-os/det-req-kit/SCHEMA.md` §8 `python-cli-surface` · living homes `~/Documents/dev/startd8-sdk/pyproject.toml`, `~/Documents/dev/startd8-sdk/src/startd8/navigator/cli_navigator.py` · grammar cite `~/Documents/dev/dev-os/NODE-SCHEMA.md` · port source `ContextCore/src/contextcore/navigator/render.py:824-1023`

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| startd8 | console-script | structure | existing `startd8 = "startd8.cli:app"` |
| navigator-build | command | structure | `startd8 navigator build` (existing; extended) |
| source-nodes-json | option | structure | `--source nodes-json --file <path>` (new) |
| renderer-wireframe | option | structure | `--renderer wireframe` (new; default for cap-index/requirements/node-schema) |
| renderer-tree | option | structure | `--renderer tree` (new; default for nodes-json) |
| open-depth | option | structure | `--open-depth <int>` (new; default 2; tree renderer only) |
| exit-navigator | exit-class | structure | 0 = wrote artifacts; non-zero = parse/IO/validation failure |

Library seams (not CLI kinds — cite as Touches file paths):
- `src/startd8/navigator/render_tree.py` (to-be-created; the N-level tree renderer)
- `src/startd8/navigator/project.py` (`nodes_to_json` children extension)
- `src/startd8/navigator/cli_navigator.py` (new flags + sources-nodes-json dispatch)
- `src/startd8/navigator/sources_nodes_json.py` (to-be-created, or inline in cli; loads pre-projected JSON)
- `tests/unit/navigator/test_tree_renderer.py` (to-be-created)

---

## Planning Insights — what the plan pass changed about the draft

> This section summarizes the **4 most significant changes** the planning pass made to the v0.1
> draft (before §0 was written). Future reviewers: these were wrong in the first draft.

1. **Design recommendation flipped from option (a) to option (b).** The draft assumed WireframeItem would gain a `children` tuple for nesting. Reading CC `render.py` showed the tree renderer is a **completely separate pipeline** from the wireframe plan — it never imports `WireframePlan`, `WireframeItem`, or `compose.py`. Option (b) is the right path because the two surfaces have different purposes and different HTML presentations. Option (a) would have contaminated the app-scaffold shape with tree-specific fields.

2. **Dead code hazard surfaced and encoded into FR-1.** The a11y-renderer brief mentioned a duplicate-defs defect but only as a note. After reading `render.py` and confirming lines 378-502 are shadowed (Python last-def-wins), the FR makes the dead-code check explicit in Verify: `grep -c "def _tree_node_html"` must output `1`. Without this guard, an implementer scanning CC top-to-bottom would port the dead pair and produce a subtly wrong renderer.

3. **`--source nodes-json` elevated from minor to primary adopter seam.** The draft treated this as a convenience option. Planning revealed it is the **only path** for dev-os REQ-10 and the legal navigator (they emit NODE-SCHEMA-JSON; they do not rebuild Nodes inside the SDK). Without FR-2, none of the three adopters are unblocked. FR-2 is now listed alongside FR-1 as the minimum viable unblocking slice.

4. **The lenses (audience × fluency) are NOT reused by the tree renderer.** The draft assumed the "crown jewel" would be shared. Reading `wireframe_view/view.py` and the CC tree renderer clarified that the two surfaces have entirely different HTML shells. The lenses require `WireframePlan`; the tree renderer recurses raw `Node` objects. NR-2 added explicitly to prevent future scope-creep.

---

## Appendix A — Accepted (with where merged)

*(empty at v0.3.1 — no CRP review run yet)*

## Appendix B — Rejected (with rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| — | option (a): extend WireframeItem with nested children | v0.1 draft | Mixes two different shapes (app-layout vs. recursive tree) into one dataclass; breaks Accidental-Complexity principle; planning revealed CC didn't do this either | 2026-08-14 |
| — | option (c): flatten tree into indented items with depth attribute | v0.1 draft | Loses structural information (you can't reconstruct the tree from a flat list with depth counters without sorting assumptions); harder to expand/collapse in JS; CC implemented option (b) with better UX | 2026-08-14 |

## Appendix C — Incoming review rounds

*(ready for CRP — see focus file `crp-focus-n-level-tree-renderer.md` when created)*

---

*v0.3.1 — Post planning + lessons-learned + design-principle hardening. Design recommendation locked: option (b) independent tree renderer. App-scaffold path byte-identical. 4 planning insights captured. Ready for CRP review.*
