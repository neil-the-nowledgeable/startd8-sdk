# Graph / Network-Topology Renderer — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-15
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — spec-only deliverable; plan follows)*
**Inherits standards:** det-req-kit · NODE-SCHEMA v0.3.9 · NAMING_CONVENTION · REQ-01-sdk-node-home (parent) · REQ-02-n-level-tree-renderer · REQ-03-a11y-renderer-and-corpus-index · REQ-04-lift-lenses-to-shared-transform (lens dependency)
**Audience:** operator (benchmark / dev-os / legal-navigator adopters; SDK contributors)
**Trust boundary:** local filesystem + pre-projected NODE-SCHEMA-JSON; no LLM, no network
**Data classification:** internal

> **Readable handle:** `feature/navigator-graph-topology-renderer`
> **Semantic name:** *Navigator renders Node relationships as a graph/network topology (dependency and cross-reference edges, not just the child tree) via a standalone force-directed graph renderer that never imports wireframe and inherits the shared lenses.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-05`

---

## 0. Why this exists — the empty TOPOLOGY cell

> `VISUALIZATION_VARIANTS_ANALYSIS.md` factored every visualization into
> `SOURCE × TOPOLOGY × PRESENTATION × AUDIENCE-LENS`, with the **Node as the fixed point** (§2). The
> **TOPOLOGY** axis lists its members as `flat · 2-level · N-level tree (REQ-02) · corpus-index
> (REQ-03) · **graph/network — empty**` (§2 table). §7 names the emergent requirement directly:
>
> > **REQ-05 — graph/network topology renderer** · *new topology* · "the empty TOPOLOGY cell:
> > `child_keys` are edges; a network view (vs tree) is unbuilt."
>
> Every topology built so far is a **tree** — a node has exactly one parent (`children` recursion).
> But the Node model carries relationships that form a **general graph**, not a tree: `child_keys`
> (dependency edges that can point across the tree, forming cycles), `Serves`/`built_by`/`delivers`
> cross-references (in `attributes`), and `triggers` (activation edges). A tree renderer cannot show
> these: a `child_keys` edge from `FR-7` back to `FR-2` is a back-edge the tree drops. REQ-05 renders
> the Nodes as a **node-link graph** where these relationships are first-class edges.

**Where REQ-05 sits on the ladder:**

| Phase | REQ | Topology added |
|------|-----|----------------|
| 1 | REQ-01 / REQ-02 | flat → 2-level → **N-level tree** |
| 2 | REQ-03 | tree + **corpus-index** (doc → drill-to-leaf) |
| 3 | REQ-04 | *(no new topology — factor the lenses out so later renderers inherit them)* |
| **4** | **REQ-05** | **general graph / network** (dependency + cross-ref edges, cycles allowed) |

---

## 0.1 Planning Insights (Self-Reflective Update)

> What changed between the v0.1 draft assumptions and this spec, after grounding against the real
> code: CC `navigator/graph_projection.py`, the SDK `navigator/models.py` Node, `navigator/project.py`
> (`nodes_to_json`), REQ-02's `render_tree.py` port pattern, and REQ-04's shared-lens plan.

| v0.1 Draft Assumption | Grounding Discovery | Impact |
|-----------------------|---------------------|--------|
| REQ-05 must author the graph *projection* (Node → graph model) from scratch | CC already ships a **pure, tested `nodes_to_graph(nodes) -> {schema, nodes, edges}`** in `navigator/graph_projection.py` (promoted from `dev-os/visual-editor/spikes/nodeschema_to_graph.py`), plus `validate_graph_model()`. It emits schema `visual-editor.graph-model/21`, derives identity from `Node.key` only, and already distinguishes semantic edges (`contains-child`, `depends-on` from `child_keys`, `serves`, `built-by`, `delivers`) from `view:section:` containment markers | The **projection is a Mottainai port**, not new work. FR-1 ports `graph_projection.py` (live symbols only). REQ-05's new authoring is confined to the **renderer** (the HTML shell) — the projection already exists |
| CC also has a graph *renderer* to port (like the tree renderer in REQ-02) | **No.** CC has `render.py` (tree), `render_a11y.py`, `render_index.py`, and `graph_projection.py` (the model only) — but **no HTML renderer that draws the graph model**. The `visual-editor.graph-model/21` payload is consumed by an external visual-editor spike, not by a CC HTML shell | FR-2 (the standalone graph HTML renderer) is **genuinely new code** — there is no CC renderer to port. This is the one substantial build in REQ-05 |
| The graph edges are just `child_keys` | The Node model + CC projection surface **five edge kinds**: `contains-child` (from `children` recursion), `depends-on` (from `child_keys`), `serves`/`built-by`/`delivers` (from `attributes`, comma-split), plus the presentation-only `has-section`/`contains` view markers | FR-2 must render the semantic edge kinds distinctly (colour/label) and must let the view *exclude* the `view_marker=true` section nodes (which exist only for the tree-ish visual-editor layout) — see FR-4 |
| The renderer needs a heavy graph library (d3/cytoscape) | The whole navigator family is **offline, self-contained, no-CDN** (REQ-02 NR-4, REQ-03 NR-5). A graph renderer needs layout, but it must ship inlined | FR-2 ships an **inlined, dependency-free** force-directed / deterministic-layout JS (no CDN, no external `<script src>`). NR-6 forbids a CDN dependency |
| The lenses (audience × fluency) can't apply to a graph, like the tree/a11y | REQ-04 lifts the lenses to a shared `node_lenses.project_nodes(nodes, *, role, fluency)` transform any renderer can call. Once REQ-04 lands, the graph renderer can filter/label nodes through the same lens layer — the FF-1 factorization the analysis demanded | FR-5 makes the graph renderer a **REQ-04 consumer** (opt-in `project_nodes` for labels/filtering); it is a soft dependency (graph renders raw Nodes if REQ-04 hasn't landed), noted as a dependency risk |

**Resolved open questions:**

- **OQ-1 (port a graph renderer, or build one?) → build the renderer; port only the projection.** CC ships the projection (`graph_projection.py`) but no graph HTML shell. FR-1 ports the projection (Mottainai); FR-2 authors the standalone HTML renderer (new).
- **OQ-2 (extend `render_tree.py` or a new module?) → new standalone module `render_graph.py`.** Same structural choice REQ-02/REQ-03 made: a graph is a *different topology* from a tree (cycles, multiple parents, cross-edges). It carries its own HTML shell and never imports `wireframe_view`. Mixing it into the tree renderer would be accidental complexity.
- **OQ-3 (byte-identity for the app-scaffold path?) → guaranteed by the standalone-module choice.** `render_graph.py` and `graph_projection.py` are modules the wireframe pipeline never imports; no `WireframePlan`/`WireframeItem`/`compose.py`/`_template.py` path changes. Existing byte-identity tests pass unedited.
- **OQ-4 (do the section view-markers belong in the graph view?) → excludable, off by default for the requirements graph.** CC's projection injects `view:section:*` nodes with `view_marker=true` purely for the visual-editor's tree-ish layout. For a *relationship* graph the operator wants the semantic edges (`depends-on`/`serves`), not the layout scaffolding. FR-4 provides `--semantic-only` (default on) to render only source nodes + semantic edges; the full projection (with markers) is opt-in via `--full-graph`.
- **OQ-5 (cycles — does the layout hang?) → the projection allows cycles; the layout must be cycle-safe.** `child_keys` can form cycles (the MEMORY note: "LLM dependency graphs are unreliable — validate acyclicity"). The graph renderer is a *general* graph view (cycles are legitimate data to *show*, not a bug), so the layout must be a force-directed / fixed-iteration algorithm that terminates regardless of cycles — never a recursion that assumes a DAG. FR-2 Verify includes a cyclic fixture.

---

## 0.2 Lessons-Learned & Design-Principle Hardening

> Consulted `docs/NAMING_CONVENTION.md`, the SDK `docs/design-princples/`, and the REQ-02/03 port-hazard pattern. Applied:

- **[Mottainai — reuse the projection]** — Port CC `graph_projection.py` (`nodes_to_graph`, `validate_graph_model`, and the `_flatten`/`_node_payload`/`_slug`/`_kind`/`_section`/`_split_ids` helper set) rather than re-deriving the Node→graph mapping. This saves the entire edge-derivation contract (five edge kinds, view-marker discipline, deterministic ordering). Applied to FR-1.
- **[Genchi Genbutsu]** — Bound to the real CC source (`graph_projection.py:88-192` `nodes_to_graph`, `:195-217` `validate_graph_model`), read directly before specifying; confirmed the emitted schema string (`visual-editor.graph-model/21`), the edge labels, and that identity is `Node.key`-only. Confirmed CC has **no** graph HTML renderer (dir listing + grep). No guessing.
- **[Kagami — port live symbols only]** — REQ-02 found CC `render.py` carried shadowed duplicate defs; the same port-hazard gate applies. FR-1 Verify requires each ported top-level symbol to appear exactly once (`grep -c "def nodes_to_graph" == 1`). `graph_projection.py` is a smaller, cleaner file than `render.py` but the gate is cheap insurance.
- **[Accidental-Complexity anti-principle]** — Rejected extending `render_tree.py` with a graph mode (OQ-2). A tree renderer assumes single-parent recursion; a graph renderer needs a layout engine and cycle-safety. Fusing them would bury graph machinery in the tree path. Separate `render_graph.py` is the principled path.
- **[SOTTO / byte-identity]** — The graph renderer and projection are new standalone modules; the deterministic $0 app-scaffold path is byte-identical (FR-6).
- **[Naming]** — `render_graph.py`, `graph_projection.py`, `--source nodes-json` (reused), `--renderer graph`, `--semantic-only` are descriptive slugs; every FR carries a `Name:` (actor·action·object·outcome). No bare `type+integer` identity.

---

## Overview

Phase 4 of the requirements-visualization ladder ([`VISUALIZATION_VARIANTS_ANALYSIS.md`](./VISUALIZATION_VARIANTS_ANALYSIS.md) §7): fill the **empty TOPOLOGY cell** with a **graph / network** renderer. The SDK `Node` model carries relationships that form a general graph — `child_keys` (dependency edges, which can point across the tree and form cycles), `attributes` cross-references (`serves`/`built_by`/`delivers`), and `triggers` — but every renderer built so far (wireframe, tree, a11y, corpus-index) renders a **tree**, which structurally cannot show back-edges, multiple parents, or cycles.

ContextCore already ships a **pure Node→graph projection** (`navigator/graph_projection.py`: `nodes_to_graph()` → a validated `{schema, nodes, edges}` GraphModel with five distinguished edge kinds) but **no HTML renderer** for it. REQ-05 therefore: (1) ports the projection (Mottainai — live symbols only); (2) authors a **standalone** offline node-link HTML renderer (the one genuinely new build) that never imports `wireframe_view`; (3) reuses the `--source nodes-json` adopter seam and adds a `--renderer graph` flag; and (4) consumes REQ-04's shared lens transform once it lands, so the graph inherits the audience × fluency lenses instead of re-forking them (the FF-1 fix the analysis demands).

**Three adopters this unblocks:**

| Adopter | What they need | Key FR |
|---|---|---|
| dev-os / benchmark node graphs | Emit a pre-projected Node graph; pipe to `startd8 navigator build --source nodes-json --renderer graph` to *see the dependency network* (not just the tree) | FR-1, FR-2, FR-3 |
| startd8-work legal navigator | Same pipe — render the cross-reference graph between statutes/authorities (already emits NODE-SCHEMA-JSON) | FR-2, FR-3 |
| requirements-viz self-use | Render this very corpus's `Serves:`/`child_keys` edges as a network (which FR serves which O; which FR depends on which) | FR-1, FR-4 |

**The design recommendation (from §0.1 OQ-2):**

> **A new standalone `render_graph.py` (its own HTML shell) + a ported `graph_projection.py`, never extending the tree renderer.**
>
> A tree is a single-parent recursion; a graph is a general relation with cycles and cross-edges. They
> are different topologies with different layout needs. The graph renderer carries its own offline,
> dependency-free layout JS and is byte-identical from every other surface's perspective — the same
> standalone-renderer discipline REQ-02 and REQ-03 established.

---

## Objectives

- O-1: An adopter can pipe a pre-projected NODE-SCHEMA-JSON graph into `startd8 navigator build --source nodes-json --renderer graph` and receive a self-contained, offline, interactive node-link **graph** HTML that shows dependency (`child_keys`) and cross-reference (`serves`/`built_by`/`delivers`) edges, including back-edges and cycles a tree cannot show.
- O-2: The Node→graph projection is reused from ContextCore (`graph_projection.py`) rather than re-derived — one canonical mapping of Node relationships to graph edges, with the five edge kinds and view-marker discipline intact.
- O-3: The existing 2-level wireframe path, the tree renderer (REQ-02), and the a11y/index renderers (REQ-03) are completely unaffected — the app-scaffold determinism golden tests pass without edits; the graph renderer never imports `wireframe_view`.
- O-4: The operator can render only the *semantic* relationship graph (source nodes + `depends-on`/`serves`/`built-by`/`delivers` edges) without the visual-editor layout scaffolding (`view:section:*` markers), or opt into the full projection.
- O-5: Once REQ-04 lands, the graph renderer inherits the audience × fluency lenses via the shared `node_lenses.project_nodes` transform — no lens re-fork (the FF-1 fix). Until then, it renders raw Node labels (soft dependency).

---

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| security | `--source nodes-json` admits untrusted Node JSON; XSS via node `key`/`does`/`label`/`attributes` interpolated into graph labels, tooltips, and `<svg>`/`<text>` | FR-2 Verify: every user-visible field (`label`, `does`, `key`, edge `label`, tooltip text) is `html.escape`d; hrefs sanitized via a `_safe_href` guard and colours via a `_safe_color` guard (port the REQ-02/REQ-03 pattern, CC #398/#400); a `<script>alert(1)</script>` fixture in `node.key` must not appear unescaped | high |
| quality | Cyclic `child_keys` (LLM graphs are unreliable — MEMORY: "always validate acyclicity") cause a naïve layout to recurse infinitely or hang | FR-2: the layout is force-directed / fixed-iteration and cycle-safe (never assumes a DAG); FR-2 Verify includes a 3-node cycle fixture that must render (a cycle is legitimate data to *show*, not an error). `validate_graph_model` (ported in FR-1) reports dangling edges but does NOT reject cycles | high |
| architecture | The graph renderer picks up a heavy graph library or CDN dependency, breaking offline self-containment | NR-6 forbids any CDN / external `<script src>`; FR-2 ships inlined, dependency-free layout JS; Verify greps the output HTML for `src=` / `cdn` / `http` in script tags (must be absent) | high |
| quality | App-scaffold wireframe path imports the graph renderer and breaks byte-identity | Standalone-module choice (OQ-3): `render_graph.py`/`graph_projection.py` live in `navigator/`; the wireframe path never imports them. FR-6 Verify: `test_no_profile_is_byte_identical` passes without golden edits | high |
| quality | Porting a dead/shadowed symbol from CC (the REQ-02 hazard) | FR-1 Verify: `grep -c "def nodes_to_graph"` (and each ported symbol) `== 1` in the ported module | medium |
| coupling | The graph renderer re-forks the lenses instead of using REQ-04's shared transform (repeats FF-1) | FR-5: consume `node_lenses.project_nodes` for labels/filtering when REQ-04 has landed; do NOT copy `_display_label`/jargon logic into `render_graph.py`. Soft dependency: raw Node labels until REQ-04 lands | medium |
| scope-creep | Building a graph *editor* (drag-to-connect, live edit) rather than a read-only view | NR-2: REQ-05 is a read-only renderer; editing is the external visual-editor's job (the projection's original consumer). Pan/zoom/hover are the only interactions | medium |
| quality | Extending `nodes_to_json` again (REQ-02 already added `children`) to carry edges duplicates the projection | NR-7: the graph *edges* are derived at render time by the ported `nodes_to_graph`, not persisted into `nodes_to_json`; `nodes_to_json` (REQ-02 shape) is the input, `nodes_to_graph` is the transform | low |

---

## Profile

Declared profile: **internal** (adopter consumers are dev-os, startd8-work/legal, benchmark, and requirements-viz self-use — not end-users directly)

---

## Functional requirements

- **FR-1 — Node→graph projection ported from CC (live symbols only).** The SDK gains `src/startd8/navigator/graph_projection.py` containing `nodes_to_graph(nodes) -> {"schema", "nodes", "edges"}` and `validate_graph_model(graph) -> tuple[str, ...]`, plus the helper set `_flatten`, `_node_payload`, `_slug`, `_kind`, `_section`, `_split_ids`, ported from ContextCore `navigator/graph_projection.py:1-217` — identity from `Node.key` only, the five edge kinds preserved (`contains-child` from `children`, `depends-on` from `child_keys`, `serves`/`built-by`/`delivers` from `attributes`, plus presentation `has-section`/`contains` markers), `view:section:*` nodes carry `view_marker=true`, deterministic ordering, no import of ContextCore. Name: Navigator ports the CC Node-to-graph projection so Node relationships become a validated graph model without ContextCore. Touches: `src/startd8/navigator/graph_projection.py` (to-be-created), `tests/unit/navigator/test_graph_projection.py` (to-be-created). Lives: link ContextCore/src/contextcore/navigator/graph_projection.py:88-217. Approve?: does the port carry all five edge kinds + view-marker discipline with identity from key only?. Verify: (a) `grep -c "def nodes_to_graph" src/startd8/navigator/graph_projection.py` outputs `1` (and once for each ported top-level symbol); (b) a fixture where `FR-7.child_keys=("FR-2",)` produces an edge `{from:"FR-7", to:"FR-2", label:"depends-on", data:{semantic:true}}`; (c) `validate_graph_model(nodes_to_graph(fixture))` returns `()` for a valid fixture and a non-empty tuple for a dangling edge. Serves: O-2.

- **FR-2 — Standalone offline graph renderer (new build).** The SDK gains `src/startd8/navigator/render_graph.py` with `render_navigator_graph_html(nodes, out_path, *, title, subtitle, semantic_only=True) -> Path` that projects via `nodes_to_graph` (FR-1) and renders a self-contained, offline node-link **graph** HTML: nodes drawn with status glyph/colour, edges drawn and labelled by kind (`depends-on`/`serves`/`built-by`/`delivers` visually distinct), a cycle-safe force-directed / fixed-iteration layout, pan/zoom/hover-to-highlight-neighbours, and inlined CSS+JS (no CDN, no `<script src>`). It must NOT import `wireframe_view`. Every user-visible field is `html.escape`d; hrefs/colours guarded by `_safe_href`/`_safe_color` (ported pattern, CC #398/#400). Name: Navigator renders the Node graph as a standalone offline node-link view without importing wireframe. Touches: `src/startd8/navigator/render_graph.py` (to-be-created), `tests/unit/navigator/test_graph_renderer.py` (to-be-created). Lives: code src/startd8/navigator/render_graph.py. Approve?: is the graph renderer standalone (no wireframe import), offline (no CDN), cycle-safe, and XSS-escaped?. Verify: (a) the module has no `import wireframe_view`; (b) a fixture with a 3-node `child_keys` cycle renders (exits 0, all 3 nodes + 3 edges present in the HTML) without hanging; (c) a `<script>alert(1)</script>` in `node.key` produces HTML with no unescaped `<script>`; (d) the output HTML contains no `src=`/`cdn`/`http` in any `<script>` tag. Serves: O-1, O-3.

- **FR-3 — `--renderer graph` CLI flag on the nodes-json seam.** `startd8 navigator build` gains `--renderer graph` (alongside REQ-02's `wireframe`/`tree`), dispatching to `render_navigator_graph_html`. It reuses REQ-02's `--source nodes-json --file <path>` adopter seam as its primary input (a pre-projected NODE-SCHEMA-JSON graph). The three renderers are mutually exclusive per invocation. Back-compat preserved: `--renderer {wireframe,tree}` behaviour is unchanged. Name: Navigator wires a graph renderer flag on the nodes-json seam so adopters pipe a projection into a network view. Touches: `src/startd8/navigator/cli_navigator.py`. Lives: code src/startd8/navigator/cli_navigator.py. Approve?: is `--renderer graph` additive and mutually exclusive with wireframe/tree?. Verify: (a) `startd8 navigator build --source nodes-json --file <fixture.json> --renderer graph --out /tmp/graph.html` exits 0 and the HTML contains the fixture's root node key; (b) `startd8 navigator build --source nodes-json --file f.json --renderer tree` (REQ-02) still produces tree HTML unchanged; (c) `startd8 navigator --help` lists `graph` among `--renderer` choices. Serves: O-1.

- **FR-4 — `--semantic-only` view (default) vs `--full-graph`.** `--renderer graph` accepts `--semantic-only` (default: render only source nodes + semantic edges `depends-on`/`serves`/`built-by`/`delivers`/`contains-child`, excluding `view:section:*` view-marker nodes and their `has-section`/`contains` edges) and `--full-graph` (render the entire `nodes_to_graph` payload including the layout markers). The exclusion filter reads the `view_marker`/`data.semantic` fields the projection already stamps — it never guesses from the id prefix. Name: Navigator graph offers a semantic-only relationship view so operators see dependency edges without visual-editor layout scaffolding. Touches: `src/startd8/navigator/render_graph.py`, `src/startd8/navigator/cli_navigator.py`. Lives: code src/startd8/navigator/render_graph.py. Approve?: does semantic-only exclude view-markers via the stamped fields, not prefix-guessing?. Verify: (a) with `--semantic-only` (default), the output HTML contains no node id beginning `view:section:` and no `has-section`/`contains` edge; (b) `--full-graph` includes the `view:section:*` nodes; (c) the filter selects on `data.semantic == true` / `data.view_marker != true`, not on a substring match of the id. Serves: O-4.

- **FR-5 — Graph renderer consumes the shared lens transform (REQ-04) for labels/filtering.** When REQ-04's `node_lenses.project_nodes(nodes, *, role, fluency)` is available, `render_navigator_graph_html` accepts `role`/`fluency` params and uses `project_nodes` to produce the node labels and the `end_user` jargon filter — it does NOT copy `_display_label`/`has_jargon`/jargon logic into `render_graph.py`. This is a **soft dependency**: absent REQ-04, the renderer falls back to raw `Node.does`/`Node.key` labels (no lens). No lens logic is re-forked (the FF-1 fix). Name: Navigator graph inherits the audience and fluency lenses via the shared node-lenses transform instead of re-forking them. Touches: `src/startd8/navigator/render_graph.py`. Lives: code src/startd8/navigator/render_graph.py. Approve?: does the graph renderer call node_lenses.project_nodes rather than duplicate the lens logic?. Verify: (a) `grep -c "_display_label\|has_jargon\|_END_USER_ORDER" src/startd8/navigator/render_graph.py` outputs `0` for each (no re-fork); (b) when REQ-04 is present, `render_navigator_graph_html(nodes, out, role="end_user")` labels match `node_lenses.project_nodes(nodes, role="end_user")` labels; (c) when `node_lenses.project_nodes` is unavailable (import guarded), the renderer still exits 0 with raw labels. Serves: O-5.

- **FR-6 — App-scaffold byte identity preserved.** The deterministic app-scaffold wireframe path (no profile, no Node grounding) remains byte-identical: no new imports in `wireframe/plan.py` or `wireframe_view/`, no changes to `_template.py`, no new keys in compose JSON. `graph_projection.py` and `render_graph.py` are standalone modules the wireframe pipeline never imports. Name: App-scaffold wireframe remains byte-identical after the graph renderer lands so the deterministic dollar-zero path is unaffected. Touches: `tests/unit/wireframe/test_render_profile.py`, `tests/unit/wireframe/test_determinism_and_json.py`. Lives: test tests/unit/wireframe/test_render_profile.py. Approve?: is the wireframe path untouched by the graph renderer?. Verify: `pytest tests/unit/wireframe/test_render_profile.py::test_no_profile_is_byte_identical tests/unit/wireframe/test_determinism_and_json.py` exits 0 without any test-file or golden edit; `wireframe_view` does not import `render_graph`/`graph_projection`. Serves: O-3.

- **FR-7 — Port-hazard gate (dead code + XSS) matches REQ-02/03.** The port of `graph_projection.py` drops any CC dead/shadowed code (each ported top-level symbol appears exactly once) and the graph renderer carries the XSS mitigations, using the single-live-def gate REQ-02 established. Name: The graph port drops CC dead code and carries its XSS escaping mitigations with a single-live-def gate. Touches: `src/startd8/navigator/graph_projection.py`, `src/startd8/navigator/render_graph.py`. Lives: code src/startd8/navigator/graph_projection.py. Approve?: does the port keep only live defs and escape all user-visible graph text?. Verify: every ported top-level symbol appears once (`grep -c` per symbol `== 1`); a fixture with `<script>` / `javascript:` href / a non-hex colour in node fields produces HTML where the script is escaped, the href is dropped/sanitized, and the colour is rejected by `_safe_color`. Serves: O-2, O-3.

---

## Non-goals

- NR-1: Reusing the audience × fluency **JS presentation-layer** controls (the wireframe `_template.py` toggle/debug panel). The graph renderer carries its own HTML shell; it consumes only the REQ-04 **Python data-layer** lens transform (FR-5), not the JS controls.
- NR-2: A graph **editor** (drag-to-connect, live edit, node creation). REQ-05 is a read-only view; editing belongs to the external visual-editor that consumes `visual-editor.graph-model/21`. Only pan/zoom/hover interactions ship.
- NR-3: Porting the rest of the CC navigator family (`render.py` tree — that is REQ-02; `render_a11y.py`/`render_index.py` — REQ-03; `role_inventory.py`, `initiative_dossier.py`, `seat_pages.py`, `sources_seats.py`, etc.). REQ-05 ports only `graph_projection.py` and authors the graph renderer.
- NR-4: A new CSS design system or theme. The graph renderer ships a minimal offline dark-UI shell consistent with the tree renderer's `_TREE_CSS` aesthetic; Tier-2 theming is deferred.
- NR-5: Extending `WireframeItem`/`WireframePlan` or the wireframe compose path with graph fields (the REQ-02 NR-1 stance holds for graphs too).
- NR-6: Any CDN / external `<script src>` / npm graph library at runtime. The layout JS is inlined and dependency-free (offline self-containment, per REQ-02 NR-4 / REQ-03 NR-5).
- NR-7: Persisting the graph edges into `nodes_to_json`. Edges are derived at render time by `nodes_to_graph` (FR-1); `nodes_to_json` (the REQ-02 tree/children shape) is the *input* to the projection, unchanged by this spec.
- NR-8: Automatic graph construction from flat sources (capability-index → graph) inside the SDK. The renderer accepts pre-projected Nodes via `--source nodes-json`; building the Node graph from a flat source is the adopter's projector responsibility (same stance as REQ-02 NR-7).
- NR-9: Acyclicity *enforcement*. `validate_graph_model` reports dangling edges but does NOT reject cycles — a general graph legitimately contains cycles, and REQ-05's job is to *show* them (the tree renderer is the one that drops back-edges). Cycle *detection for the prime-contractor queue* is a separate, existing concern (`contractors/queue.py`).

---

## Owned fields

Only humans/adopters control: the pre-projected `nodes-json` payload (`key`/`does`/`child_keys`/`attributes` set by the adopter's projector — these become the graph's nodes and edges); `--semantic-only` / `--full-graph`; `role`/`fluency` (when REQ-04 has landed); `title`/`subtitle` arguments to `render_navigator_graph_html`.

---

## Contract projection

- **Backend:** python-cli-surface
- **Vocabulary home (cite):** `~/Documents/dev/dev-os/det-req-kit/SCHEMA.md` §8 `python-cli-surface` · living homes `~/Documents/dev/startd8-sdk/pyproject.toml`, `~/Documents/dev/startd8-sdk/src/startd8/navigator/cli_navigator.py` · grammar cite `~/Documents/dev/dev-os/NODE-SCHEMA.md` · port source `ContextCore/src/contextcore/navigator/graph_projection.py:1-217` (projection only — CC has NO graph HTML renderer to port)

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| navigator-build | command | structure | existing (REQ-02); gains `--renderer graph` |
| renderer-graph | option | structure | `--renderer graph` (new; dispatches to `render_navigator_graph_html`) |
| semantic-only | option | structure | `--semantic-only` (new; default on; excludes view-markers) |
| full-graph | option | structure | `--full-graph` (new; includes the visual-editor layout markers) |
| source-nodes-json | option | structure | `--source nodes-json --file <path>` (reused from REQ-02 FR-2) |
| exit-navigator | exit-class | structure | 0 = wrote artifact; non-zero = parse/IO/validation failure |

Library seams (not CLI kinds — cite as Touches file paths):
- `src/startd8/navigator/graph_projection.py` (to-be-created; ported Node→graph projection)
- `src/startd8/navigator/render_graph.py` (to-be-created; the standalone graph HTML renderer — the one new build)
- `src/startd8/navigator/cli_navigator.py` (`--renderer graph` + `--semantic-only`/`--full-graph` dispatch)
- `src/startd8/wireframe_view/node_lenses.py` (REQ-04 — soft dependency consumed by FR-5)
- `tests/unit/navigator/test_graph_projection.py`, `tests/unit/navigator/test_graph_renderer.py` (to-be-created)

---

## Dependencies

- **REQ-01** (parent — the SDK Node home) — the `Node` model REQ-05 projects. **Built.**
- **REQ-02** (N-level tree renderer) — supplies the `--source nodes-json` adopter seam and the `--renderer` CLI vocabulary REQ-05 extends; the standalone-renderer + port-hazard pattern REQ-05 follows. **Spec (REQ-only).**
- **REQ-03** (a11y + corpus index) — the sibling standalone-renderer precedent; not a hard dependency. **Spec.**
- **REQ-04** (lift lenses to shared transform) — **soft dependency** for FR-5: once landed, the graph renderer inherits the lenses via `node_lenses.project_nodes` instead of re-forking them (the FF-1 fix). Absent REQ-04, the graph renders raw Node labels. The analysis's guidance ("do REQ-04 before adding a fourth renderer, or every new shell re-forks the crown jewel") applies: **REQ-05 is that fourth renderer** — landing REQ-04 first is strongly preferred so FR-5 is a first-class consumption rather than a deferred retrofit. **Spec.**
- **ContextCore `graph_projection.py`** — the Mottainai port source for FR-1. **Built (in CC).**

---

## Appendix A — Accepted (with where merged)

*(empty at v0.1 — no CRP review run yet)*

## Appendix B — Rejected (with rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| — | Extend `render_tree.py` with a graph mode | v0.1 draft | A tree is single-parent recursion; a graph needs a cycle-safe layout engine and cross-edge/back-edge rendering. Fusing them buries graph machinery in the tree path (Accidental-Complexity). Separate `render_graph.py` (OQ-2). | 2026-08-15 |
| — | Author the Node→graph projection from scratch | v0.1 draft | CC already ships a pure, tested `nodes_to_graph` with the five edge kinds and view-marker discipline. Re-deriving it is a Mottainai violation and risks edge-mapping drift. Port it (FR-1). | 2026-08-15 |
| — | Persist graph edges into `nodes_to_json` | v0.1 draft | Edges are a *derived view* of the Node relationships, not durable state; deriving them at render time (via `nodes_to_graph`) keeps `nodes_to_json` (the REQ-02 shape) unchanged and avoids two homes for the edge mapping. NR-7. | 2026-08-15 |
| — | Enforce acyclicity / reject cyclic input | v0.1 draft | A general graph legitimately contains cycles; REQ-05's purpose is to *show* the network the tree drops. Rejecting cycles would defeat the point. `validate_graph_model` reports dangling edges only. NR-9. | 2026-08-15 |

## Appendix C — Incoming review rounds

*(ready for CRP — see focus file `crp-focus-graph-topology-renderer.md` when created)*

---

*v0.1 — Fills the empty TOPOLOGY cell (VISUALIZATION_VARIANTS_ANALYSIS §7 REQ-05). Projection is a Mottainai port of CC `graph_projection.py` (live symbols only); the standalone offline graph renderer is the one genuinely new build (CC has no graph HTML renderer). Standalone (no wireframe import), byte-identical app-scaffold path, cycle-safe, XSS-escaped. Soft-depends on REQ-04 for the shared lens transform (the FF-1 fix — this is the fourth renderer the analysis warned about). Ready for CRP review.*
