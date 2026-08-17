# Feature→Capability Composition Primitive + Ground-Up Rollup View — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-17
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — spec-only deliverable; plan follows via reflective-requirements)*
**Inherits standards:** det-req-kit · NODE-SCHEMA v0.3.9 · NAMING_CONVENTION · REQ-01-sdk-node-home (parent) · REQ-05-graph-topology-renderer (the graph renderer + `nodes_to_graph` projection this reuses) · REQ-02-n-level-tree-renderer (the tree renderer + `--source`/`--renderer` vocabulary)
**Audience:** operator (SDK contributors; cross-repo adopters — ContextCore EB-4 dogfood; requirements-viz self-use)
**Trust boundary:** local filesystem (det-req markdown + capability YAML); no LLM, no network
**Data classification:** internal

> **Readable handle:** `feature/navigator-feature-capability-composition-rollup`
> **Semantic name:** *Navigator lets a feature (FR) declare the capability it composes up to, joins FR nodes and capability nodes into one graph so the feature→capability edge connects, and renders capabilities ground-up (bottom-up) from their constituent features — the SDK dogfood of ContextCore's missing objective→objective rollup (EB-4), one composition primitive for any corpus.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:feature-capability-composition-rollup`

---

## 0. Why this exists — the composition edge exists in the graph, the parser is the only gate

> **The finding this spec is built on (grounded, file:line):** the feature→capability composition edge is
> **almost entirely already built**. The `serves` edge is drawn by the graph projection; the FR node attribute
> that feeds it is already set by the requirements source; the capability nodes already exist as a separate
> source. The **one gate** is the det-req parser, which today only lets an FR target an objective (`O-N`), not
> a capability. This is a Mottainai (reuse) spec: extend one regex + join two node sets + reuse the existing
> edge machinery + reuse an existing renderer with a rank direction. No new edge system, no new renderer.

**navig8r is the two-sided validation surface** — technical grounding (does the code exist / is the check
live) on one side, human/business value (what outcome does this serve) on the other. This spec adds a
**composition primitive** to the *value* side: a feature declares **the capability it builds up to**, so
capabilities can be rendered **ground-up from their constituent features** — you see a capability *assembled*
from the features that compose it, not merely asserted.

**The four grounded facts that make this mostly reuse:**

1. **The `serves` edge already exists in the graph.** `src/startd8/navigator/graph_projection.py:181-182`
   splits `node.attributes["serves"]` into semantic `serves` edges, generic on the target id — it draws an edge
   to *whatever id the attribute names*; it does **not** require the target be an `O-N`. `built_by`/`delivers`
   (`:183-186`) and `depends-on` from `child_keys` (`:179-180`) plus `contains-child` (`:175-176`) are the
   sibling edge kinds. So an FR→capability edge needs **no new edge kind** — it flows through the same `serves`
   machinery the moment the FR attribute names a capability id.

2. **The GATE is the det-req parser.** `src/startd8/navigator/det_req.py:31-32` — `_SERVES` only matches
   `O-\d+` (comma lists): `r"(?:\*\*)?\bServes:(?:\*\*)?\s*((?:O-\d+)(?:\s*,\s*O-\d+)*)\.?"`. So an FR can
   only `Serves: O-N`; it **cannot yet name a capability**. Extending this regex (or adding a sibling
   `Composes:` field) to also accept a capability ref is the entire parser change — and it must keep
   `Serves: O-N` parsing byte-for-byte (109× `O-1`/etc. across the corpus must still parse).

3. **The pipeline is end-to-end.** `src/startd8/navigator/sources_requirements.py:303` sets
   `attrs["serves"] = ", ".join(fr.get("serves"))` → the exact node attribute the graph reads at
   `graph_projection.py:181`. Once the parser accepts a capability target, the value flows to the edge with
   **no new machinery**.

4. **Capabilities are a separate source.** `src/startd8/navigator/sources_capability.py`
   (`nodes_from_capability_index`, default `docs/capability-index/startd8.sdk.capabilities.yaml`) builds
   capability nodes whose `key` is the `capability_id` (e.g. `startd8.provider.registry`,
   `sources_capability.py:123`), carrying `child_keys = dependencies + cross_references` (`:131`), `category`
   (`:132`), and `kind="capability"` (`:138`). Today the CLI renders **one source per invocation**
   (`cli_navigator.py:118-186`: `capability-index` **or** `requirements`, never joined). But the projection's
   `add_semantic` guard **requires both endpoints be present** in the graph (`graph_projection.py:172`:
   `if source in by_id and target in by_id`) — so the FR→capability edge is **silently dropped unless both FR
   nodes and capability nodes are in the SAME node set**. Joining the two sources is therefore the second
   load-bearing change.

**This is corpus-agnostic — and it is the SDK realization of ContextCore EB-4.** The primitive lives at the
**Node / det-req grammar** level (an FR node's `serves` attribute → a semantic edge to another node), so it
works for *any* corpus that emits NODE-SCHEMA. The **same edge** is ContextCore's missing **EB-4**
(objective→objective `serves` rollup) documented in
[`PM_FINDINGS_contextcore-o11y-value-lineage.md`](./PM_FINDINGS_contextcore-o11y-value-lineage.md): ContextCore's
Objectives are a flat list with *"no `parent`/`serves`/`rollup` edge"* (§2), and the fix is *"one edge — an
`Objective`→`Objective` **`serves`** relation — which is exactly the derivation edge the navig8r's `Node` model
already carries"* (§TL;DR). **feature→capability (SDK) and objective→objective (ContextCore) are the same
composition primitive.** Building it here dogfoods the exact edge the PM findings recommend ContextCore build —
one primitive, both corpora.

**Where this sits — the composition ladder:**

| Concern | Grounded state | This spec |
|---|---|---|
| The `serves` edge (target-generic) | **built** — `graph_projection.py:181` | reuse (no change) |
| FR `serves` attribute set from parse | **built** — `sources_requirements.py:303` | reuse (no change) |
| Capability nodes | **built** — `sources_capability.py` | reuse as the join's second half |
| FR can target a **capability** (not just `O-N`) | **absent** — `det_req.py:31` gates on `O-\d+` | **FR-1 (parser)** |
| FR nodes + capability nodes in ONE graph | **absent** — CLI is one-source-per-run | **FR-2 (join source)** |
| The feature→capability edge drawn | falls out of FR-1+FR-2 via reuse | **FR-3 (reuse `serves`)** |
| **Ground-up rollup view** (features at base, capabilities above) | **absent** | **FR-4 (rank-directed reuse)** |
| Corpus-agnostic / ContextCore EB-4 dogfood | the primitive is Node-level | **FR-5** |
| `Serves: O-N` + existing renders byte-identical | must hold | **FR-6** |

---

## 0.1 Planning Insights (Self-Reflective Update)

> What grounding against the real navigator code changed, versus the naïve "build a composition system"
> framing. Bound directly to `graph_projection.py`, `det_req.py`, `sources_requirements.py`,
> `sources_capability.py`, `cli_navigator.py`, `render_graph.py`, `render_tree.py`, and the PM findings note.

| Naïve v0.1 Assumption | Grounding Discovery (file:line) | Impact |
|-----------------------|---------------------------------|--------|
| A feature→capability edge needs a new edge kind / a new projection | `graph_projection.py:181-182` already splits `attributes["serves"]` into `serves` edges **generic on the target id** — it draws to any id, not just `O-N`. `built_by`/`delivers`/`depends-on` are sibling kinds already present | **No new edge system.** FR-3 reuses `serves`. The whole edge is unlocked by the parser (FR-1) + the join (FR-2); no `graph_projection.py` edit is required to draw it |
| The parser already accepts arbitrary refs after `Serves:` | `det_req.py:31-32` `_SERVES` regex hard-codes `(?:O-\d+)(?:\s*,\s*O-\d+)*` — an FR can **only** target `O-N`. A `CAP-*`/`startd8.*` ref is not matched, so it is never captured into `fr["serves"]` | **The parser is the one gate.** FR-1 extends the regex (or adds a `Composes:` sibling) to also accept a capability ref, backward-compatible with `O-N` |
| Once the parser accepts it, the edge appears automatically | `graph_projection.py:172` `add_semantic` only draws an edge if **both** endpoints are in `by_id`. The CLI renders one source per run (`cli_navigator.py:123-181`: `capability-index` xor `requirements`), so the capability node is absent from the requirements graph and the edge is **silently dropped** | **A join is mandatory.** FR-2 adds a combined source (FR nodes + capability nodes in one node set) so both endpoints are present |
| A ground-up view needs a brand-new renderer | `render_graph.py` is force-directed (no inherent up/down); `render_tree.py` is top-down over `child_keys`. A **ground-up** (features base → capabilities above) view is a **rank/direction** choice over an existing renderer, not a third renderer | **FR-4 reuses a renderer with a rank direction** (rank-by-kind in the graph layout, or an inverted/rank-directed tree), never a new topology engine |
| This is an SDK-only feature | The PM findings note (`PM_FINDINGS_contextcore-o11y-value-lineage.md` §TL;DR, §4.1) identifies the identical missing edge in ContextCore (EB-4, objective→objective `serves`) and says the fix is *the derivation edge the navig8r Node model already carries* | **FR-5**: this is one corpus-agnostic primitive at the Node grammar level; note explicitly it is the SDK realization of ContextCore EB-4 |

**Resolved open questions:**

- **OQ-1 (extend `Serves:` or add a new `Composes:` field?) → extend `Serves:` to also accept a capability ref, with `Composes:` reserved as an explicit-intent alias.** Reuse maximizes: the FR `serves` attribute → `graph_projection.py:181` `serves` edge is already end-to-end. Overloading `Serves:` (an FR serves an objective *or* composes a capability — both are "what this FR builds toward") means zero downstream change beyond the regex. A `Composes:` sibling is admitted as an optional, clearer-intent alias that maps to the **same** `serves` attribute (so the edge kind stays `serves` — see FR-1/FR-3), never a second edge system.
- **OQ-2 (how is a capability ref shaped so the parser can distinguish it from `O-N`?) → a distinct token class.** Capability ids are dotted (`startd8.provider.registry`, `sources_capability.py:123`) or a `CAP-*` handle; `O-N` is `O-\d+`. The extended regex accepts a capability token that is NOT `O-\d+`-shaped, so the two never collide and `O-N` matching is untouched. FR-1 Verify includes both a pure-`O-N` FR (unchanged) and a mixed `Serves: O-2, startd8.provider.registry` FR.
- **OQ-3 (a new combined `--source` value, or teach an existing source to read both?) → a new `--source requirements+capabilities` (a combined source), not a mutation of either existing source.** Each existing source stays single-purpose and byte-identical (FR-6); the join is an additive new source value that calls `nodes_from_requirements` + `nodes_from_capability_index` and concatenates. This mirrors the one-source-per-run structure at `cli_navigator.py:123-181` without disturbing it.
- **OQ-4 (does the ground-up view need the graph or the tree renderer?) → reuse the graph renderer with a kind-ranked layout (primary), tree with inverted rank as fallback.** The relationship is a general graph (a capability composed of many features; a feature may compose >1 capability — not single-parent), so the graph renderer (REQ-05) is the natural home; FR-4 adds a **rank direction** (capabilities ranked above their composing features) to the existing force layout rather than a new engine. A rank-directed tree is the documented fallback if graph ranking proves insufficient. **No third renderer.**
- **OQ-5 (does the capability node need to declare its features, or the feature its capability?) → the FEATURE declares upward (`Serves:`/`Composes:` on the FR).** This is the ground-up direction: the constituent (feature) names what it composes into (capability), so the rollup is assembled bottom-up from the base. It also keeps the capability YAML untouched (byte-identical) — the composition lives in the det-req corpus, authored where the feature is authored.
- **OQ-6 (dangling capability ref — an FR names a capability id that isn't in the index?) → report, don't crash.** `validate_graph_model` (REQ-05 FR-1) already reports dangling edges; a feature→capability edge to an absent capability is a dangling edge surfaced by the same validator, not a parse failure. FR-2 Verify includes an FR naming an unknown capability and asserts the validator reports it (graph still renders).

---

## 0.2 Lessons-Learned & Design-Principle Hardening

> Consulted `docs/NAMING_CONVENTION.md`, the SDK `docs/design-princples/`, the REQ-05 port/reuse pattern, and the PM findings note. Applied:

- **[Mottainai — reuse over new]** — This spec is dominated by reuse: the `serves` edge (`graph_projection.py:181`), the FR `serves` attribute (`sources_requirements.py:303`), the capability source (`sources_capability.py`), and an existing renderer (`render_graph.py`/`render_tree.py`) are all reused. The only genuinely-new code is a parser-regex extension (FR-1) and a join source (FR-2); the edge and the view are reuse compositions (FR-3/FR-4).
- **[Genchi Genbutsu]** — Bound to the real code before specifying: confirmed `_SERVES` gates on `O-\d+` (`det_req.py:31-32`), that `serves` edges are target-generic (`graph_projection.py:181-182`), that `add_semantic` requires both endpoints (`:172`), that the FR attribute is the pipeline hinge (`sources_requirements.py:303`), and that capability nodes key on `capability_id` (`sources_capability.py:123`). No guessing.
- **[Shadow-taxonomy avoidance / single authority]** — The capability-vs-objective distinction is made ONCE, in the extended parser (FR-1), by token shape — not re-guessed by substring predicates scattered across the renderer. Downstream code treats every `serves` target uniformly (an edge to a node id).
- **[SOTTO / byte-identity]** — `Serves: O-N` parses identically; the capability YAML is untouched; each existing single-source render path is unchanged. The composition edge and the combined source are strictly additive (FR-6).
- **[Accidental-Complexity anti-principle]** — Rejected a new edge kind, a new projection, and a third renderer. The ground-up view is a rank *direction* over an existing renderer, not a new topology engine (OQ-4).
- **[Two-sided coin / value lineage]** — The composition edge is the value-side lineage (feature → capability it builds up to), the mirror of the technical-grounding side. This is exactly the PM findings' *"the missing edge is what would join the two validation sides"* (`PM_FINDINGS…` §4.3), realized in the SDK corpus.
- **[Naming]** — `Composes:`, `--source requirements+capabilities`, `--rank-direction ground-up`, `serves` (reused) are descriptive; every FR carries a `Name:` (actor·action·object·outcome). No bare `type+integer` identity.

---

## Overview

A **composition primitive** for navig8r: let a feature (FR) declare the **capability it builds up to**, so
capabilities render **ground-up from their constituent features**. Grounding proved this is mostly *reuse*:
the `serves` edge is drawn by the graph projection generic on its target id (`graph_projection.py:181-182`),
the FR `serves` attribute is already set from the parse (`sources_requirements.py:303`), and capability nodes
already exist as a source (`sources_capability.py`). The **one gate** is the det-req parser, which today only
lets `Serves:` target an objective (`O-N`) (`det_req.py:31-32`). This spec therefore: (1) extends the parser
so an FR can name a **capability** target, backward-compatible with `Serves: O-N` (FR-1); (2) joins FR nodes +
capability nodes into **one** graph so the edge's endpoints are both present — required by the `add_semantic`
both-endpoints guard (`graph_projection.py:172`) (FR-2); (3) reuses the existing `serves`/semantic-edge
machinery to draw the feature→capability edge, **no new edge kind** (FR-3); (4) adds a **ground-up rollup view**
— capabilities ranked above their composing features — by reusing a renderer with a rank direction, not a third
renderer (FR-4); (5) notes and dogfoods that this is a corpus-agnostic Node-level primitive, identical to
ContextCore's missing EB-4 objective→objective `serves` edge (FR-5); and (6) preserves `Serves: O-N`
parsing and every existing render byte-for-byte (FR-6).

**Adopters this unblocks:**

| Adopter | What they get | Key FR |
|---|---|---|
| requirements-viz self-use | See this corpus's capabilities *assembled* from the FRs that compose them (ground-up), not just asserted | FR-1, FR-4 |
| ContextCore (EB-4 dogfood) | The identical objective→objective `serves` rollup, proven in the SDK first; the navig8r renders the flat-vs-composed gap | FR-3, FR-5 |
| cross-repo NODE-SCHEMA adopters (dev-os / benchmark / legal) | A corpus-agnostic composition edge at the Node grammar level — any FR-like node can compose upward | FR-1, FR-5 |

---

## Objectives

- O-1: A feature author can write `Serves:` (or `Composes:`) naming a **capability** on an FR bullet, and the parser captures it into `fr["serves"]` — backward-compatible with `Serves: O-N`, which parses byte-for-byte identically.
- O-2: FR nodes and capability nodes can be projected into **one** graph (a combined source) so a feature→capability edge has both endpoints present and is drawn (not silently dropped by the both-endpoints guard).
- O-3: The feature→capability edge is drawn by the **existing** `serves` semantic-edge machinery — no new edge kind, no `graph_projection.py` edge-derivation change.
- O-4: An operator can render a **ground-up rollup view** — capabilities as roots ranked above their composing features (the base) — by reusing an existing renderer with a rank direction, not a new renderer.
- O-5: The composition primitive is **corpus-agnostic** (Node/det-req grammar level) and is explicitly the SDK realization of ContextCore's missing EB-4 (objective→objective `serves`) — one primitive, both corpora.
- O-6: `Serves: O-N` and every existing single-source render (`capability-index`, `requirements`, tree, graph, wireframe) are **byte-identical**; the composition edge and combined source are strictly additive.

---

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | Extending `_SERVES` breaks the 109× `Serves: O-N` bullets already in the corpus (a regex change that drops fields on the common case) | FR-1 Verify: a pure `Serves: O-1, O-2` FR parses to exactly `["O-1","O-2"]` (byte-identical to today); the corpus-wide `navigator build --source requirements --format json` still projects `named == FR-count` for every existing REQ | high |
| architecture | The feature→capability edge is silently dropped because the capability node isn't in the requirements graph (the `add_semantic` both-endpoints guard, `graph_projection.py:172`) | FR-2: a combined source puts FR nodes + capability nodes in one node set; FR-2 Verify asserts the edge is present in the projected graph (not dropped) | high |
| quality | A dangling capability ref (FR names a `capability_id` not in the index) crashes the parse or the projection | FR-2 Verify: an FR naming an unknown capability parses fine and produces a **dangling edge** that `validate_graph_model` reports (graph still renders) — report, don't crash (OQ-6) | medium |
| architecture | The distinction "is this target an objective or a capability?" gets re-guessed by substring predicates scattered across renderers (a shadow taxonomy) | FR-1: the distinction is made ONCE in the extended parser by token shape; downstream treats every `serves` target uniformly as an edge to a node id (no per-renderer re-classification) | medium |
| quality | A capability id containing a digit or a hyphen is mis-parsed as an `O-N` list or truncated | FR-1: the capability token class is defined as NOT `O-\d+`-shaped and anchored so `startd8.provider.registry` / `CAP-7` parse whole; Verify includes a dotted and a hyphenated id | medium |
| scope-creep | Building a third renderer for the ground-up view instead of adding a rank direction to an existing one | NR-2 / FR-4: reuse `render_graph.py` (kind-ranked layout) or a rank-directed tree; no new topology engine | medium |
| quality | The capability YAML is mutated to declare its features (wrong direction), breaking its byte-identity | NR-4 / OQ-5: composition is authored on the FEATURE (upward), not on the capability; `startd8.sdk.capabilities.yaml` is untouched | low |
| coupling | The combined source mutates `nodes_from_requirements` / `nodes_from_capability_index` instead of composing them | FR-2 / OQ-3: the combined source *calls* both existing functions and concatenates; neither existing source function changes (byte-identical) | low |

---

## Profile

Declared profile: **internal** (consumers are SDK contributors, the ContextCore EB-4 dogfood, and cross-repo NODE-SCHEMA adopters — not end-users directly).

---

## Functional requirements

- **FR-1 — Parser accepts a capability target on `Serves:`/`Composes:` (backward-compatible with `O-N`).** The det-req parser is extended so an FR bullet can name a capability id (dotted like `startd8.provider.registry` or a `CAP-*` handle) as a composition target, captured into `fr["serves"]` alongside any `O-N` targets, with an optional `Composes:` sibling label mapping to the same attribute. Name: The det-req parser lets a feature declare the capability it composes up to while parsing existing objective references byte-for-byte unchanged. Touches: `src/startd8/navigator/det_req.py`, `tests/unit/navigator/test_det_req_composes.py`. Verify: (a) a pure `Serves: O-1, O-2` FR still parses to exactly `["O-1","O-2"]`; (b) `Serves: O-2, startd8.provider.registry` parses to `["O-2","startd8.provider.registry"]`; (c) `Composes: startd8.provider.registry` (dotted) and `Composes: CAP-7` (hyphenated) each parse whole into `fr["serves"]` and are not truncated or split as an `O-N` list. Serves: O-1

- **FR-2 — Combined `requirements+capabilities` source joins both node sets into one graph.** A new `--source requirements+capabilities` value builds one node set by calling `nodes_from_requirements` and `nodes_from_capability_index` and concatenating them (neither existing source function is modified), so a feature→capability edge has both endpoints present and is not dropped by the `add_semantic` both-endpoints guard. Name: The navigator joins feature nodes and capability nodes into one combined source so the composition edge has both endpoints present and is drawn. Touches: `src/startd8/navigator/cli_navigator.py`, `src/startd8/navigator/sources_requirements.py`, `tests/unit/navigator/test_combined_source.py`. Verify: (a) `startd8 navigator build --source requirements+capabilities --requirements <fixture.md> --format json` emits a node set containing both an `FR-*` node and the referenced capability node; (b) the projected graph contains a `serves` edge from the FR to the capability id; (c) an FR naming an unknown capability parses fine and `validate_graph_model` reports exactly that edge as dangling while the graph still renders. Serves: O-2

- **FR-3 — Feature→capability edge drawn by the existing `serves` machinery (no new edge kind).** The feature→capability composition edge is rendered by the already-shipped `serves` semantic edge (`graph_projection.py:181-182`) with no new edge kind and no change to the projection's edge-derivation, once FR-1 supplies the target and FR-2 supplies both endpoints. Name: The navigator draws the feature-to-capability edge through the existing serves semantic-edge machinery without inventing a new edge system. Touches: `src/startd8/navigator/graph_projection.py`, `tests/unit/navigator/test_composition_edge.py`. Verify: (a) with a fixture where an FR node's `serves` attribute names a capability id, `nodes_to_graph` produces an edge `{from:"FR-N", to:"<capability_id>", label:"serves", data:{semantic:true}}`; (b) `grep -c "label.*serves\|new edge kind\|composes-edge" src/startd8/navigator/graph_projection.py` shows no new edge-label branch was added for composition (the edge reuses `serves`); (c) the five existing edge kinds are unchanged in the projection. Serves: O-3

- **FR-4 — Ground-up rollup view ranks capabilities above their composing features.** A `--rank-direction ground-up` option renders capabilities as roots ranked above their composing features (the base) by reusing an existing renderer (graph with a kind-ranked layout, or a rank-directed tree) — not a new renderer — so a capability is shown assembled bottom-up from the features that compose it. Name: The navigator renders capabilities ground-up from their constituent features by adding a rank direction to an existing renderer rather than building a third one. Touches: `src/startd8/navigator/render_graph.py`, `src/startd8/navigator/cli_navigator.py`, `tests/unit/navigator/test_rollup_view.py`. Verify: (a) `startd8 navigator build --source requirements+capabilities --requirements <fixture.md> --renderer graph --rank-direction ground-up --out /tmp/rollup.html` exits 0 and the capability node is laid out at a higher rank (smaller y / root band) than the FR nodes that compose it; (b) no new `render_*.py` module file is created (the view reuses `render_graph.py`/`render_tree.py`); (c) `--rank-direction` defaults to the current layout so existing renders are unchanged. Serves: O-4

- **FR-5 — Corpus-agnostic primitive, documented as the SDK realization of ContextCore EB-4.** The composition primitive lives at the Node/det-req grammar level (an FR node's `serves` attribute → a `serves` edge) so it applies to any NODE-SCHEMA corpus, and the spec/appendix explicitly names it the SDK dogfood of ContextCore's missing EB-4 (objective→objective `serves` rollup). Name: The navigator establishes composition as a corpus-agnostic Node-level primitive that is the SDK realization of ContextCore's missing objective-to-objective rollup. Touches: `docs/design/requirements-visualization/REQ-feature-capability-composition-rollup.md`, `docs/design/requirements-visualization/PM_FINDINGS_contextcore-o11y-value-lineage.md`. Verify: (a) the composition edge is produced by the same generic `serves`-attribute path (`graph_projection.py:181`) with no FR-node-type special-casing, demonstrated by a non-`FR-*`-keyed node (e.g. an objective-keyed node) whose `serves` attribute also yields a `serves` edge; (b) this doc's Appendix C cross-references `PM_FINDINGS_contextcore-o11y-value-lineage.md` §4.1/§TL;DR (EB-4 = the same edge). Serves: O-5

- **FR-6 — `Serves: O-N` and existing single-source renders byte-identical.** Existing `Serves: O-N` parsing, the `capability-index` and `requirements` single-source renders, and the tree/graph/wireframe renderers are byte-identical; the composition edge, the combined source, and the rank direction are strictly additive, and the capability YAML is untouched. Name: The navigator keeps objective references and every existing single-source render byte-identical so the composition primitive is strictly additive. Touches: `tests/unit/navigator/test_det_req.py`, `tests/unit/navigator/test_sources_capability.py`, `tests/unit/wireframe/test_render_profile.py`. Verify: (a) the existing `det_req` and capability-source unit suites pass without edits; (b) `startd8 navigator build --source requirements --format json` output for an all-`O-N` REQ is unchanged; (c) `docs/capability-index/startd8.sdk.capabilities.yaml` has no diff and the app-scaffold wireframe byte-identity test passes unedited. Serves: O-6

---

## Non-goals

- NR-1: A new edge KIND for composition. The feature→capability edge reuses the existing `serves` semantic edge (`graph_projection.py:181-182`); no `composes`/`rolls-up` edge label is added (FR-3).
- NR-2: A third HTML renderer. The ground-up view is a **rank direction** over the existing `render_graph.py` (kind-ranked layout) or a rank-directed `render_tree.py` — not a new topology engine (FR-4, OQ-4).
- NR-3: A new projection or a change to `nodes_to_graph`'s edge-derivation contract. The projection is reused unchanged; FR-1 (parser) + FR-2 (join) supply the target and both endpoints (FR-3).
- NR-4: Mutating `startd8.sdk.capabilities.yaml` to declare its constituent features. Composition is authored on the FEATURE (upward, `Serves:`/`Composes:` on the FR), keeping the capability YAML byte-identical (OQ-5, FR-6).
- NR-5: Modifying `nodes_from_requirements` or `nodes_from_capability_index`. The combined source *composes* both existing functions and concatenates; neither is changed (FR-2, OQ-3).
- NR-6: Acyclicity enforcement on composition edges. A capability composed of many features (and a feature composing >1 capability) is a general graph; `validate_graph_model` reports dangling edges but does not reject the shape (OQ-6).
- NR-7: Building the ContextCore side (EB-4). This spec dogfoods the *primitive* in the SDK corpus and names the parallel; the actual objective→objective edge in ContextCore is that repo's owner's change (PM findings §6 recommendation).
- NR-8: An LLM step. The parser extension, the join, the edge, and the view are all deterministic, offline, `$0` — consistent with the whole navigator family.

---

## Owned fields

Only humans/authors control: the `Serves:`/`Composes:` capability target on an FR bullet (the composition
edge's source→target); the capability index contents (`capability_id`s the FR targets); `--rank-direction`
(`ground-up` vs the default layout); `--source requirements+capabilities` selection; `--renderer`
(`graph`/`tree`); `--requirements` / `--capability-index` paths.

---

## Contract projection

- **Backend:** python-cli-surface
- **Vocabulary home (cite):** `~/Documents/dev/dev-os/det-req-kit/SCHEMA.md` §8 `python-cli-surface` · living homes `~/Documents/dev/startd8-sdk/pyproject.toml`, `~/Documents/dev/startd8-sdk/src/startd8/navigator/cli_navigator.py` · grammar cite `~/Documents/dev/dev-os/NODE-SCHEMA.md` · reuse sources `src/startd8/navigator/graph_projection.py:181-182` (`serves` edge — target-generic), `src/startd8/navigator/det_req.py:31-32` (`_SERVES` — the gate), `src/startd8/navigator/sources_requirements.py:303` (the FR `serves` attribute), `src/startd8/navigator/sources_capability.py:123` (capability node key = `capability_id`)

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| navigator-build | command | structure | existing (REQ-02/05); gains combined source + rank direction |
| source-requirements+capabilities | option | structure | `--source requirements+capabilities` (new; joins FR + capability nodes — FR-2) |
| composes-field | field | words | `Composes:` det-req FR field (new; alias mapping to the `serves` attribute — FR-1) |
| serves-capability | field | words | `Serves:` extended to accept a capability ref (FR-1) |
| rank-direction-ground-up | option | structure | `--rank-direction ground-up` (new; capabilities above composing features — FR-4) |
| exit-navigator | exit-class | structure | 0 = wrote artifact / clean parse; non-zero = parse/IO/validation failure |

Library seams (not CLI kinds — cite as Touches file paths):
- `src/startd8/navigator/det_req.py` (`_SERVES` extended to accept a capability ref + optional `Composes:` — FR-1)
- `src/startd8/navigator/cli_navigator.py` (`--source requirements+capabilities`, `--rank-direction` — FR-2/FR-4)
- `src/startd8/navigator/sources_requirements.py` (the combined source composes `nodes_from_requirements` + `nodes_from_capability_index` — FR-2)
- `src/startd8/navigator/graph_projection.py` (reused unchanged; the `serves` edge draws composition — FR-3)
- `src/startd8/navigator/render_graph.py` / `render_tree.py` (rank direction reuse — FR-4)
- `tests/unit/navigator/test_det_req_composes.py`, `test_combined_source.py`, `test_composition_edge.py`, `test_rollup_view.py` (to-be-created)

---

## Iterations

> Acyclic delivery order — each stage depends only on the prior. Matches the reuse cascade
> (parser → join → edge → view → corpus-agnostic dogfood).

| # | Iteration | FRs | Depends on | Rationale |
|---|-----------|-----|-----------|-----------|
| 1 | **Parser** — extend `_SERVES` / add `Composes:` | FR-1 | — | The one gate; unlocks the FR→capability target. Byte-identical `O-N`. |
| 2 | **Join** — combined `requirements+capabilities` source | FR-2 | FR-1 | Both endpoints in one graph (the `add_semantic` guard). |
| 3 | **Edge** — reuse `serves` to draw composition | FR-3 | FR-1, FR-2 | Falls out of parser + join via the existing edge machinery; no new edge kind. |
| 4 | **View** — ground-up rollup (rank direction) | FR-4 | FR-3 | Capabilities ranked above composing features, reusing a renderer. |
| 5 | **Corpus-agnostic dogfood** — Node-level primitive = ContextCore EB-4 | FR-5 | FR-3 | Prove the edge is generic (non-FR node yields it); name the EB-4 parallel. |
| — | **Byte-identity guard** (cross-cutting) | FR-6 | all | `Serves: O-N` + every existing render unchanged; strictly additive. |

---

## Dependencies

- **REQ-01** (parent — the SDK Node home) — the `Node` model this projects. **Built.**
- **REQ-05** (graph topology renderer) — supplies `graph_projection.py` (the `serves` edge, `nodes_to_graph`, `validate_graph_model`) and `render_graph.py` this reuses for the edge (FR-3) and the ground-up view (FR-4). **Spec/partially built (`graph_projection.py`/`render_graph.py` present in-tree).**
- **REQ-02** (N-level tree renderer) — supplies the `--source`/`--renderer` CLI vocabulary FR-2/FR-4 extend and `render_tree.py` (the rank-directed-tree fallback for FR-4). **Spec.**
- **ContextCore EB-4** — the parallel objective→objective `serves` rollup this dogfoods; documented in `PM_FINDINGS_contextcore-o11y-value-lineage.md`. **Unbuilt (in ContextCore) — a cross-repo belief; validate with the ContextCore owner before recommending they build it (PM findings §6).**

---

## Appendix A — Accepted (with where merged)

*(empty at v0.1 — no CRP review run yet)*

## Appendix B — Rejected (with rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| — | Add a new `composes`/`rolls-up` edge kind to the projection | v0.1 draft | The `serves` edge is already target-generic (`graph_projection.py:181-182`) — a composition edge reuses it. A new edge kind is a Mottainai violation and a shadow taxonomy. NR-1, FR-3. | 2026-08-17 |
| — | Build a third renderer for the ground-up view | v0.1 draft | The ground-up view is a rank *direction* over the existing graph/tree renderer, not a new topology. A third renderer is accidental complexity. NR-2, FR-4, OQ-4. | 2026-08-17 |
| — | Declare features on the capability (in `startd8.sdk.capabilities.yaml`) | v0.1 draft | Ground-up means the constituent (feature) declares upward; authoring on the capability breaks its byte-identity and inverts the direction. NR-4, OQ-5, FR-6. | 2026-08-17 |
| — | A separate `Composes:` edge system distinct from `Serves:` | v0.1 draft | `Composes:` is admitted only as an intent alias mapping to the *same* `serves` attribute/edge — a second edge system would fork the machinery the reuse eliminates. FR-1/FR-3. | 2026-08-17 |

## Appendix C — Incoming review rounds

*(ready for CRP)*

**Cross-repo parallel (EB-4):** this spec is the SDK realization of the composition edge
[`PM_FINDINGS_contextcore-o11y-value-lineage.md`](./PM_FINDINGS_contextcore-o11y-value-lineage.md) identifies as
missing in ContextCore — §TL;DR (*"one edge — an `Objective`→`Objective` **`serves`** relation … exactly the
derivation edge the navig8r's `Node` model already carries"*), §2 (the flat model), §4.1 (*"EB-4 ≈ give
objectives the edge the Node model already defines"*), §4.3 (*"the missing edge is what would join the two
validation sides"*). feature→capability (here) and objective→objective (EB-4) are one primitive. Validate the
EB-4 recommendation with the ContextCore owner before acting (PM findings §6, cross-repo belief).

---

*v0.1 — A composition primitive (feature declares the capability it composes up to) + a ground-up rollup view.
Grounded as **mostly reuse (Mottainai)**: the `serves` edge is drawn generic on its target
(`graph_projection.py:181`), the FR `serves` attribute is set from the parse (`sources_requirements.py:303`),
and capability nodes exist (`sources_capability.py`); the ONE gate is the det-req parser
(`det_req.py:31-32`, `O-\d+`-only). FR-1 extends the parser (backward-compatible with `Serves: O-N`); FR-2
joins FR + capability nodes into one graph (the `add_semantic` both-endpoints guard, `:172`); FR-3 reuses the
`serves` edge (no new kind); FR-4 renders ground-up via a rank direction over an existing renderer (no third
renderer); FR-5 makes it a corpus-agnostic Node-level primitive = the SDK dogfood of ContextCore EB-4; FR-6
keeps `Serves: O-N` and every existing render byte-identical. Ready for CRP review.*
