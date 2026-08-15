# Diff-Audience View (Node-Corpus Delta Renderer) — Requirements

**Project:** startd8-sdk   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-15
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — spec-only deliverable; plan follows)* · analysis `VISUALIZATION_VARIANTS_ANALYSIS.md` §5/§7 (REQ-07 candidate)
**Inherits standards:** det-req-kit · NODE-SCHEMA v0.3.9 · NAMING_CONVENTION · REQ-01-sdk-node-home (parent) · REQ-02-n-level-tree-renderer · REQ-03-a11y-renderer-and-corpus-index · REQ-04-lift-lenses-to-shared-transform · REQ-05 (graph topology) · REQ-06 (corpus governance)
**Audience:** operator / reviewer (an approver comparing two states of a requirements corpus)
**Trust boundary:** local filesystem + two pre-projected/authored Node states; no LLM; no network fetch of evidence
**Data classification:** internal

> **Readable handle:** `feature/navigator-diff-audience-view`
> **Semantic name:** *SDK navigator diffs two states of the Node corpus and renders the delta — added/removed/changed FRs, status transitions, new dangling refs — as reviewer-audience Nodes/rows via a standalone diff renderer that never imports wireframe.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-07`

---

## 0. Why this exists — the audience whose need is a delta

The variants analysis (`VISUALIZATION_VARIANTS_ANALYSIS.md`) factors every visualization as
`SOURCE × TOPOLOGY × PRESENTATION × AUDIENCE-LENS` with **the Node as the invariant** (§2). Section 5
predicts the next audiences are **meta** — a *diff auditor* and an *exec summarizer* — and the next
information↔presentation relation drifts from transparent → self-referential → **evaluative/generative**.
REQ-07 is the **diff auditor**: an audience whose need is not "show me the corpus" but "show me what
**changed** between two states of the corpus."

The two states are two projections of the Node corpus — two versions of a requirements doc, or two
runs (yesterday's `nodes-json` vs today's). The reviewer wants the **delta rendered as Nodes/rows**:
which FRs were **added**, which **removed**, which **changed** (field-by-field), which underwent a
**status transition** (`spec → built`, `built → deprecated`), and which introduced **new dangling
refs** (a `lives` reference to a path that no longer resolves). This is the "generative/meta end" of
§5: the presentation *judges* the information across time.

**No CC renderer to port (Mottainai check).** ContextCore's `navigator/` has **no** diff/delta
renderer — the "diff" strings in `render.py`/`graph_projection.py`/`sources_requirements.py` are
incidental (`"a different block"`, `"Duplicate … with different content"`). REQ-07 is **greenfield**,
but it reuses established seams: `nodes_from_json` (REQ-02 FR-4) as the state loader, the `Node.key`
identity for pairing, and REQ-02's already-tested `_safe_href` for XSS.

**Track position map** (the ladder the analysis §7 names):

| Candidate | Kind | This REQ |
|-----------|------|----------|
| REQ-04 | factor-out (lift lenses) | inherited (FR-6) |
| REQ-05 | new topology (graph) | out of scope (NR-6) |
| REQ-06 | corpus governance | complementary (the diff is a governance signal; NR-7) |
| **REQ-07** | **new audience (diff)** | **this REQ** |

## Overview

A **standalone** two-part capability: (1) a pure **diff engine** `diff_nodes(before, after) -> NodeDiff`
that keys on `Node.key`, classifies each key as **added / removed / changed / unchanged**, extracts
per-field **status transitions** and **new dangling refs**, and is renderer-independent; (2) a
**standalone diff renderer** with its **own HTML shell** (never imports `wireframe_view`, the same
structural choice REQ-02/REQ-03 made) that renders the `NodeDiff` as a reviewer-facing delta view —
added rows, removed rows, changed rows (before→after per field), and a status-transition summary —
with a11y-safe classification (green/red/amber conveyed by **text + glyph**, not colour alone). A
`startd8 navigator diff --before X --after Y --out Z.html` CLI drives it. Once REQ-04 lands, the diff
renderer inherits the shared audience × fluency lenses (a reviewer sees the `architect` lens; an
`end_user` sees a benefit-first delta) via the shared transform rather than re-forking them.

## Objectives

- **O-1:** Compute a deterministic, renderer-independent **delta** between two Node states keyed by
  `Node.key` — target: `diff_nodes(before, after)` returns a `NodeDiff` with `added` / `removed` /
  `changed` / `unchanged` buckets and per-changed-key field-level deltas, stable under re-ordering.
- **O-2:** Render the delta as a **reviewer-audience** view via a **standalone** renderer (own HTML
  shell; never imports `wireframe_view`) — target: `startd8 navigator diff --before X --after Y --out
  z.html` exits 0 and writes self-contained HTML with added/removed/changed sections.
- **O-3:** Surface the two review-critical derived signals — **status transitions** and **new
  dangling refs** — as first-class, at-a-glance rows so an approver can accept/reject the delta at a
  glance (the glance-approve acceptance test, extended across time).
- **O-4:** The diff engine + renderer are **standalone**; the app-scaffold wireframe path stays
  **byte-identical** — target: existing byte-identity/determinism tests pass unedited.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | A **huge diff** (hundreds of changed keys — a whole doc rewrite) overwhelms the reviewer | FR-7: altitude/summarization — a header roll-up (`+N / −M / ~K`), collapse-by-default changed rows, and a `--max-detail` cap that degrades to counts-only past a threshold | high |
| quality | **False "changed"** from cosmetic reordering (children/lives/wont/triggers reordered, whitespace) | FR-1: **stable keying + order-insensitive** field comparison for tuple/collection fields (compare as sets/sorted where order is not semantic); byte compare only where order is semantic | high |
| security | XSS on authored before/after text (does/lives/attributes) in the diff HTML | FR-4: route every authored/evidence string through `html.escape`; every href through REQ-02's `_safe_href`; no colour sink from source | high |
| quality | Diff renderer secretly coupling to wireframe (re-welding the crown jewel) | FR-2: own HTML shell; forbid `import wireframe_view`; a `grep`-gate as REQ-02/03 use | high |
| quality | **Ambiguous identity** — a renamed key reads as one removed + one added, hiding a real "changed" | FR-1: document key-identity semantics explicitly (rename = remove+add by design in v0.1); NR-4 defers fuzzy rename detection; the renderer labels added/removed honestly | medium |
| a11y | Delta conveyed by **colour alone** (green/red/amber) fails colour-blind reviewers | FR-3: every delta class carries a **text label + glyph** (`+ added` / `− removed` / `~ changed`) independent of colour; contrast bar met | high |
| scope-creep | Dragging in graph topology (REQ-05) or corpus governance (REQ-06) | NR-6/NR-7: flat keyed diff of two states only; not a graph-delta, not a governance loop | medium |

## Functional requirements

- **FR-1 — Diff engine `diff_nodes(before, after) -> NodeDiff`.** A pure, renderer-independent function in `src/startd8/navigator/diff.py` that pairs two `list[Node]` by `Node.key` and returns a `NodeDiff` dataclass with `added` / `removed` / `changed` / `unchanged` buckets, where each changed entry carries per-field `FieldDelta(field, before, after)` over `key/does/status/status_facets/children/attributes/lives/wont/ships_when` — comparing order-insensitive collection fields as sets/sorted so cosmetic reordering is NOT reported as changed. Name: Navigator diff engine pairs two Node states by key and returns an order-stable added/removed/changed/unchanged delta. Touches: `src/startd8/navigator/diff.py`, `tests/unit/navigator/test_diff.py`. Lives: code src/startd8/navigator/diff.py. Approve?: does diff_nodes key on Node.key and treat reordered collections as unchanged (no false "changed")?. Verify: `diff_nodes(a, a) == empty delta`; reordering a node's children/lives yields `unchanged`; an added key lands in `.added`, a dropped key in `.removed`, a `does`/`status` edit in `.changed` with the right `FieldDelta`s. Serves: O-1
- **FR-2 — Standalone diff renderer with own HTML shell.** A renderer in `src/startd8/navigator/render_diff.py` that takes a `NodeDiff` and writes a self-contained offline HTML page (inlined CSS+JS, no CDN) with its OWN shell — it must NOT import `wireframe_view` — laying the delta out as three sections (Added / Removed / Changed) plus a header roll-up, where changed rows show before→after per field. Name: Navigator renders a NodeDiff as a standalone self-contained delta view that never imports wireframe. Touches: `src/startd8/navigator/render_diff.py`, `tests/unit/navigator/test_render_diff.py`. Lives: code src/startd8/navigator/render_diff.py. Approve?: is the diff renderer standalone (no wireframe import) with added/removed/changed sections + a roll-up header?. Verify: rendered HTML is self-contained (no external URLs), has Added/Removed/Changed sections and a `+N / −M / ~K` roll-up; `grep -c "import wireframe_view" render_diff.py == 0`. Serves: O-2
- **FR-3 — A11y-safe delta classification (not colour-only).** Each delta class renders with a **text label + glyph** independent of colour — added = green + `+ added`, removed = red + `− removed`, changed = amber + `~ changed` — so the classification survives greyscale/colour-blindness; contrast meets the stated bar. Name: The diff view conveys added/removed/changed by text plus glyph, never by colour alone. Touches: `src/startd8/navigator/render_diff.py`. Lives: code src/startd8/navigator/render_diff.py. Approve?: does every delta class carry a text label + glyph, decodable in greyscale?. Verify: each row has a textual class label + glyph; removing all CSS colour still disambiguates added/removed/changed; contrast bar met on the palette. Serves: O-3
- **FR-4 — Status transitions + new dangling refs as first-class rows.** The renderer surfaces two derived review signals at the top of the Changed section: a **status-transition** summary (`key: spec → built`, `built → deprecated`) derived from `FieldDelta("status", …)`, and a **new dangling refs** list — `lives` references present in `after` but absent in `before` whose ref does not resolve on the local filesystem — flagged honestly. Name: The diff view surfaces status transitions and newly-introduced dangling refs as first-class at-a-glance rows. Touches: `src/startd8/navigator/render_diff.py`, `src/startd8/navigator/diff.py`. Lives: code src/startd8/navigator/diff.py. Approve?: are status transitions and new dangling refs surfaced as distinct, at-a-glance rows?. Verify: a `spec→built` node appears in the transition summary; a new `lives` ref to a nonexistent path appears in the dangling-refs list; an existing (already-present) dangling ref is NOT re-flagged as new. Serves: O-3
- **FR-5 — `startd8 navigator diff` CLI.** A new `navigator diff` subcommand — `startd8 navigator diff --before X --after Y --out Z.html` — where `--before`/`--after` each accept a requirements doc OR a `nodes-json` file (loaded via `nodes_from_json`, REQ-02 FR-4), consistent with REQ-02/03 CLI vocabulary; additive (no break to `build`/`ground`/`index`); `--json` emits the machine-readable `NodeDiff` for CI. Name: Navigator CLI exposes a diff subcommand taking a before and an after Node state and writing a delta view. Touches: `src/startd8/navigator/cli_navigator.py`, `tests/unit/navigator/test_cli_diff.py`. Lives: code src/startd8/navigator/cli_navigator.py. Approve?: is `navigator diff --before --after --out` additive and does it accept requirements OR nodes-json for each side?. Verify: `startd8 navigator --help` lists `diff`; `navigator diff --before a.md --after b.md --out d.html` exits 0 + writes d.html; `--json` prints the NodeDiff; existing `build`/`ground`/`index` unchanged. Serves: O-2
- **FR-6 — Inherit REQ-04 shared lenses (no re-fork).** Once REQ-04 lands the shared Node-view-model transform, the diff renderer consumes lens-annotated item-views (`node_lenses.project_nodes(nodes, role=…, fluency=…)`) for the before/after states rather than re-implementing audience × fluency — a reviewer defaults to the `architect` lens; `--role`/`--fluency` select others; the diff renderer adds NO forked lens code. Name: The diff renderer inherits the shared audience and fluency lenses via the REQ-04 transform instead of re-forking them. Touches: `src/startd8/navigator/render_diff.py`, `src/startd8/wireframe_view/node_lenses.py`. Lives: doc docs/design/requirements-visualization/REQ-04-lift-lenses-to-shared-transform.md. Approve?: does the diff renderer call the shared lens transform rather than re-implementing lens logic?. Verify: `render_diff` contains no duplicated `_display_label`/`_item_view` logic; `--role architect|end_user` changes the delta labelling via `node_lenses.project_nodes`; absent REQ-04, this FR is spec-blocked and cited as a dependency, not silently forked. Serves: O-2
- **FR-7 — Altitude / summarization for huge diffs.** The renderer degrades gracefully on large deltas: a header roll-up (`+N added / −M removed / ~K changed`), changed rows collapsed by default (expand-on-demand JS in the renderer's own shell), and a `--max-detail N` cap past which the Changed section renders counts-only with a "diff too large — showing summary" banner, so a whole-doc rewrite does not produce an unreadable wall. Name: The diff view summarizes to an altitude roll-up and caps per-row detail so huge diffs stay reviewable. Touches: `src/startd8/navigator/render_diff.py`, `src/startd8/navigator/cli_navigator.py`. Lives: code src/startd8/navigator/render_diff.py. Approve?: does a huge diff degrade to a roll-up + capped detail rather than an unreadable wall?. Verify: a diff of >`--max-detail` changed keys renders the counts-only banner + roll-up; a small diff renders full detail; the roll-up counts match the NodeDiff bucket sizes. Serves: O-1
- **FR-8 — XSS mitigations (reuse REQ-02).** All authored/evidence text (does/lives/attributes/wont/ships_when, both before and after) is `html.escape`-d; every href is passed through REQ-02's already-tested `_safe_href`; the diff renderer has no user-controlled colour sink (classification colours come from the fixed palette). Name: The diff renderer escapes all authored before-and-after text and sanitizes every href via the shared safe-href helper. Touches: `src/startd8/navigator/render_diff.py`, `tests/unit/navigator/test_render_diff.py`. Lives: code src/startd8/navigator/render_tree.py. Approve?: is every authored string escaped and every href sanitized (no raw source into HTML)?. Verify: a node whose `does` contains `<script>` renders escaped; a `javascript:` href in a `lives` ref is neutralized by `_safe_href`; no source string reaches the HTML unescaped. Serves: O-2
- **FR-9 — App-scaffold byte identity + standalone.** `diff.py` and `render_diff.py` are standalone modules the wireframe pipeline never imports; no `WireframePlan` / `WireframeItem` / `compose.py` / `_template.py` path changes; the app-scaffold path stays byte-identical. Name: The diff engine and renderer leave the app-scaffold wireframe path byte-identical. Touches: `tests/unit/wireframe/test_render_profile.py`, `tests/unit/navigator/test_diff.py`. Lives: test tests/unit/wireframe/test_render_profile.py. Approve?: is the wireframe path untouched by the diff engine and renderer?. Verify: `test_no_profile_is_byte_identical` + determinism tests pass unedited; `wireframe_view` does not import `diff`/`render_diff`. Serves: O-4
- **FR-10 — Deterministic delta (order-stable, reproducible).** `diff_nodes` and `render_diff` are deterministic: the same (before, after) pair yields byte-identical HTML and an identically-ordered `NodeDiff` across runs (buckets sorted by key; field deltas in a fixed field order), so a CI diff-of-diffs is meaningful. Name: The diff engine and renderer are deterministic and order-stable across runs. Touches: `src/startd8/navigator/diff.py`, `src/startd8/navigator/render_diff.py`, `tests/unit/navigator/test_diff.py`. Lives: code src/startd8/navigator/diff.py. Approve?: is the delta deterministic (same inputs → byte-identical output, stable ordering)?. Verify: running `diff_nodes`/`render_diff` twice on the same inputs yields identical output; buckets are key-sorted; shuffling input node order does not change the rendered result. Serves: O-1

## Non-goals

- NR-1: A three-way / N-way merge or conflict view — v0.1 is a **two-state** delta only.
- NR-2: History/time-series across >2 states (a changelog timeline) — that is a follow-on; this REQ diffs exactly one `before` against one `after`.
- NR-3: Reusing the wireframe renderer's HTML shell — the diff renderer carries its own (the REQ-02/03 standalone discipline).
- NR-4: Fuzzy **rename detection** (heuristic key-matching) — in v0.1 a renamed key is honestly `removed + added`; similarity-based rename pairing is deferred.
- NR-5: Semantic/NLP diffing of prose `does` text (word-level intra-string diff) — v0.1 reports a field as changed with before→after values; sub-string highlighting is a follow-on.
- NR-6: Graph/network delta (edge added/removed between nodes) — that rides REQ-05 (graph topology); this REQ diffs the flat keyed node set.
- NR-7: A governance loop over the diff (prove-or-purge on the delta) — REQ-06 corpus governance owns loops; the diff is a **signal** it can consume, not a loop itself.
- NR-8: Forking the audience × fluency lenses into the diff renderer — the lenses arrive via REQ-04's shared transform (FR-6); absent REQ-04, FR-6 is spec-blocked, not forked.
- NR-9: Network resolution of `lives` refs — dangling-ref detection (FR-4) is **local-filesystem only**; no HTTP HEAD/fetch.

## Contract projection

- **Backend:** python-cli-surface
- **Vocabulary home (cite):** `dev-os/NODE-SCHEMA.md` · `VISUALIZATION_VARIANTS_ANALYSIS.md` §5/§7 (the diff-audience candidate) · REQ-02 (`nodes_from_json`, `_safe_href`) · REQ-04 (`node_lenses`)

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| navigator-diff | command | structure | new: `startd8 navigator diff --before … --after … --out …` |
| before | option | structure | `--before` (a requirements doc OR a nodes-json file) |
| after | option | structure | `--after` (a requirements doc OR a nodes-json file) |
| out | option | structure | `--out` (the delta HTML target) |
| json | option | structure | `--json` (machine-readable NodeDiff for CI) |
| max-detail | option | structure | `--max-detail N` (altitude cap for huge diffs) |
| role / fluency | option | structure | inherited from REQ-04 shared lenses (FR-6) |

Library seams (Touches file paths): `src/startd8/navigator/diff.py`,
`src/startd8/navigator/render_diff.py`, `src/startd8/navigator/cli_navigator.py`,
`src/startd8/wireframe_view/node_lenses.py` (REQ-04, consumed).

## Dependencies

- **REQ-02** (`nodes_from_json` state loader; `_safe_href` XSS helper) — **built**, hard dependency.
- **REQ-04** (shared lens transform `node_lenses.project_nodes`) — FR-6 is **spec-blocked** on it; the diff renderer must NOT re-fork lenses. If REQ-04 has not landed, ship FR-1..FR-5 + FR-7..FR-10 and cite FR-6 as pending.
- **REQ-06** (corpus governance) — complementary consumer of the diff signal (NR-7); not a build dependency.

## Appendix A — Accepted (with where merged)
## Appendix B — Rejected (with rationale)
## Appendix C — Incoming review rounds

*v0.1 — REQ-07, the diff-audience view (the §5 "diff auditor"): a keyed two-state Node delta engine + a standalone reviewer-facing delta renderer. Greenfield (no CC diff renderer to port). Ready for CRP.*
