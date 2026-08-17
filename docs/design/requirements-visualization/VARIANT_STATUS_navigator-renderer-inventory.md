# Variant Status — Navigator Renderer Inventory (canonical record)

**Date:** 2026-08-17 · **Status:** OFFICIAL · **Scope:** the requirements-visualization renderers in
`src/startd8/navigator/` + `src/startd8/wireframe_view/`. **Grounded** in the source (file:line);
every CLI flag below was verified against `src/startd8/navigator/cli_navigator.py`.

> **Purpose.** A single canonical status record so nobody (a) rebuilds a renderer that already exists,
> or (b) deprecates a renderer that owns a live cell. Read this before proposing to "consolidate,"
> "retire," or "replace" any navigator renderer. The bottom line (§5) is the operative sentence:
> **among the renderers, essentially nothing should be deprecated.**

---

## 1. Framing — the four-axis product space (why the renderers are complementary, not redundant)

Per `VISUALIZATION_VARIANTS_ANALYSIS.md` §2, every visualizer is a **point** in a four-axis product
space — it is not ad-hoc, it *factors*:

```
visualization  =  SOURCE  ×  TOPOLOGY  ×  PRESENTATION  ×  AUDIENCE-LENS
```

- **SOURCE** (`Fᵢ : Domainᵢ → Node`) — what information is projected in (requirements · capability-index
  · node-schema · nodes-json).
- **TOPOLOGY** — the shape of the node relation (flat · 2-level · N-level tree · corpus-index · graph).
- **PRESENTATION** (`Gⱼ : Node → View`) — the renderer / shell.
- **AUDIENCE-LENS** — a natural transformation on the view-model (audience × fluency × debug × a11y).

**The invariant is the Node** — the waist of the hourglass (`VISUALIZATION_VARIANTS_ANALYSIS.md` §2).
SOURCES are functors *into* it, RENDERERS are functors *out* of it, and a visualization is
`Gⱼ ∘ (lens) ∘ Fᵢ`. Add a source = one new `Fᵢ`; add a renderer = one new `Gⱼ`.

**The navig8r card view occupies exactly ONE cell.** The wireframe/navig8r renderer
(`src/startd8/wireframe_view/view.py` → `_template.py`) is:

> **requirements × flat/2-level × editorial-card × audience-lens.**

It is the editorial, benefit-first "is my thing right?" surface for the `end_user`/`architect`
audiences (`view.py:36`, `DEFAULT_HTML_ROLE = "end_user"`; the four embedded audience variants at
`view.py:42`). It is a **2-level** shell (section → item cards) — it structurally cannot draw an
N-level drill, a cross-referencing graph, a two-state delta, a multi-doc corpus, or a dense speakable
text view. **The other renderers fill cells the card view cannot** — so they are complementary,
NOT redundant. Deprecating one because "we already have the card view" is a category error: they do
not overlap in the product space.

---

## 2. Active renderer variants

Six renderers are ACTIVE. Each owns a distinct `(topology, audience)` cell.

| Variant | Cell (topology / audience it owns) | Distinct use case + audience | Signature feature the card view lacks | CLI invocation | Status |
|---------|-----------------------------------|------------------------------|---------------------------------------|----------------|--------|
| **tree** (`render_tree.py`) | N-level tree / integrator, drill-reader | Drill an arbitrarily deep node tree (`node.children` recursion). Adopter seam for cross-repo node graphs (legal · benchmark · dev-os). | **Free-text search across all nodes** (`id="q"` + `data-search` real-time filter, `render_tree.py:45-52`, `326-345`) + N-level nesting | `navigator build --renderer tree` (default for `--source nodes-json`) | ACTIVE |
| **graph** (`render_graph.py`) | graph / network topology / architect | Show cross-ref + cycle edges (`child_keys`, `serves`, `built_by`, `delivers`, `derived-from`, `revises`) that a tree structurally cannot draw (`render_graph.py:1-8`). | Network view with back-edges & cycles; kind-distinguished edges (`render_graph.py:49-60`) | `navigator build --renderer graph` (`--semantic-only`/`--full-graph`) | ACTIVE |
| **a11y** (`render_a11y.py`) | flat semantic / screen-reader user | Screen-reader-native semantic HTML + a dense speakable TEXT view; landmarks, ordered headings, status-by-text+glyph never colour-alone (`render_a11y.py:1-14`). | **Traceability spine / matrix** (objectives↔capabilities via `Serves`; `render_a11y.py:221,229-249,516-524`) + speakable text | `navigator build --format a11y` | ACTIVE |
| **index** (`render_index.py`) | corpus-index / auditor, corpus reader | Multi-doc overview: one health-encoded row per REQ + facet-count coverage strip, drilling to one a11y leaf per doc (`render_index.py:1-9`). | Multi-document corpus view (card view is single-doc) | `navigator index --dir <dir> --out <f>` | ACTIVE |
| **diff** (`render_diff.py`) | two-state delta / reviewer, auditor | "What changed between two node graphs" — added/removed/changed + status transitions + new dangling refs, with an altitude roll-up (`render_diff.py:1-20`). | Two-state delta affordance (card view is single-state) | `navigator diff --before <a> --after <b> --out <f>` (`--json` for CI) | ACTIVE |
| **wireframe / navig8r** (`wireframe_view/view.py` + `_template.py`) | flat / 2-level editorial-card / end_user · architect | The editorial benefit-first "is my thing right?" preview; 4 embedded audience×fluency variants; status-filter chips + paging (`_template.py:502-506,722-736`). | (this IS the card view) | `navigator build --renderer wireframe` (default for the flat sources) | ACTIVE |

**Two support pieces (KEEP — infrastructure, not renderers):**

- **`graph_projection.py`** — the pure `Node → GraphModel` bridge (`graph_projection.py:1-12`). It is
  the shared projection the graph, tree (flatten reuse, `render_tree.py:218-224`) and diff renderers
  build on. Not a renderer; do not deprecate.
- **`scripts/navigator_*_loop.py`** — the five governance loops (`navigator_pilot_loop.py`,
  `navigator_content_loop.py`, `navigator_origin_audit.py`, `navigator_cruft_loop.py`,
  `navigator_inspect_loop.py`). These are **operators that judge/propose** (prove-or-purge, salvage,
  cruft/inspect) — they are NOT renderers and are out of scope for any renderer-deprecation decision.

---

## 3. Gap list — distinct/useful capabilities NOT in the navig8r card view

Capabilities the card view (`_template.py`) structurally lacks. For each: KEEP-SEPARATE or PULL-IN.

| Gap | Where it lives today | Verdict |
|-----|----------------------|---------|
| **Free-text search across nodes** | tree renderer: `id="q"` search box + `data-search` real-time filter (`render_tree.py:45-52`, `326-345`, `404`). The navig8r card view has **0 search input** (grep for `type="search"`/`id="q"`/`data-search` in `_template.py` = 0 hits) — only status-filter chips (`status-chip`, `data-status`, `_template.py:502-506,722-736`) + paging. | **PULL-IN candidate (strongest).** A free-text filter over `key/does/citation/tag` is the single highest-value affordance the card view is missing. |
| **Graph topology (cross-ref / cycle edges)** | graph renderer (`render_graph.py`) — the only surface that can draw back-edges + cycles. | **KEEP-SEPARATE** (a tree/card shell cannot draw a graph). Add a **"view as graph" cross-link** from the card view. |
| **Traceability spine / matrix** (objectives↔capabilities via `Serves`) | a11y renderer's TRACEABILITY spine (`render_a11y.py:221,229-249,516-524`). navig8r has none. | **PULL-IN candidate** — a traceability-spine panel on the **full-page** card view. |
| **Two-state diff** ("what changed since last render") | diff renderer (`render_diff.py`). | **KEEP-SEPARATE** (the diff renderer owns the two-state cell). Consider a **"diff against previous"** cross-link from the card view. |
| **Corpus / multi-doc index** | index renderer (`render_index.py`). | **KEEP-SEPARATE** — navig8r is single-doc by design; the index owns the corpus cell. |
| **Dense speakable TEXT view** (a11y) | a11y renderer (`render_a11y.py:1-14`). | **KEEP-SEPARATE** — belongs to the a11y cell (screen-reader-first). |

---

## 4. Officially retired / superseded (the real deprecation list)

These — and ONLY these — are true deprecations. Marked DEPRECATED so they are not rebuilt.

| Item | Status | Reason / authority |
|------|--------|--------------------|
| **Hand-maintained FSN-markdown navigators ("ur-form")** | **RETIRED by design** | The hand `docs/**/README.md` FSN-markdown navigators are the ur-form the renderers replace (`VISUALIZATION_VARIANTS_ANALYSIS.md` §1, row 1: *"retired"*). Their retirement is the reason the Node model + the deterministic renderers exist (mutation M1, §4). Do **not** re-hand-maintain markdown navigators. |
| **`REQ-14-control-schema-formalization.md`** (the narrow control-schema spec) | **REMOVED / SUPERSEDED** | Removed in commit `5b5cee9e` ("reconcile REQ-14 — unification is canonical (built); remove superseded narrow spec"). Superseded by control-region **unification** — the canonical spec now on disk is `REQ-14-control-region-unification.md`. Do not resurrect the schema-formalization variant. |
| **Entangled audience/fluency lenses welded into the wireframe** (`_template.py`) | **SUPERSEDED (not deleted)** | The FF-1 factorization failure (`VISUALIZATION_VARIANTS_ANALYSIS.md` §3): the audience×fluency lenses were welded to the one wireframe renderer, so tree + a11y could not inherit them. Superseded by REQ-04's shared transform `src/startd8/wireframe_view/node_lenses.py` (the "second RenderProfile moment", `node_lenses.py:1-11`). The old **welded** form must not return; new renderers consume the shared transform via the soft-import seam (`render_tree.py:27-30`, `render_graph.py:38-41`, `render_diff.py:36-39`). |

> **Note on REQ-04 adoption status (not a deprecation — a tracked enhancement):** the shared lens
> transform exists and the **graph** renderer consumes the `apply_node_lenses`/`project_nodes`
> aggregate; wiring **tree** + **a11y** + routing `compose` through it as the single chokepoint is a
> cumulative-enhancement backlog item, **not a defect** (`node_lenses.py`, "Adoption status" note).
> Do not "fix" this by re-welding lenses into a renderer.

---

## 5. Bottom line

- **Among the renderers, essentially NOTHING should be deprecated.** Each of the six active renderers
  (tree · graph · a11y · index · diff · wireframe/navig8r) owns a **distinct cell** in
  SOURCE × TOPOLOGY × PRESENTATION × AUDIENCE. They are complementary by construction, not redundant.
- **The only true deprecations** are (a) the **ur-form hand FSN-markdown navigators** (retired by
  design) and (b) the **removed `REQ-14-control-schema-formalization.md`** spec (superseded by
  control-region unification). The welded-lens *form* is superseded-not-deleted by REQ-04's shared
  `node_lenses.py`; the welded form must not return.
- **Recommended next moves (in priority order):**
  1. **Pull free-text search into navig8r** (strongest) — port the tree renderer's `id="q"` +
     `data-search` filter into the card view, which today has none.
  2. **Add a traceability-spine panel** on the navig8r full-page view (the a11y renderer already
     proves the `Serves` objectives↔capabilities spine).
  3. **Add cross-links** from the card view to the **graph** ("view as graph") and **diff**
     ("diff against previous") renderers, rather than duplicating their cells.

---

*Grounded 2026-08-17 against `feat/navigator-doc-context-band`. DIDL-consistent (single canonical
record; every claim cites a file:line or commit). Regenerate the framing from
`VISUALIZATION_VARIANTS_ANALYSIS.md`; the CLI invocations from `navigator/cli_navigator.py`.*
