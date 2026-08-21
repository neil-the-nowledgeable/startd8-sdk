# navig8r — the a11y-renderer track (migration ask from dev-os)

**From:** dev-os (visualization-capability catalog + REQ-10 benchmark-node-tree work), 2026-08-14.
**To:** the startd8-sdk agent team (owns the navigator forward home).
**Kind:** consumer note / migration ask (companion to `NAVIG8_FEEDBACK_FROM_CONSUMER_2026-07-10.md`).
**One line:** the deep-drill / a11y renderer capability is **built and wired in ContextCore**, but the
startd8-sdk navigator port received **only the flattening (wireframe) projection** — so the forward home
can't yet render an N-level `children` tree. This is the gap blocking dev-os REQ-10 and (per the
2026-08-14 decision that the navigator consolidates into startd8-sdk) it needs to land here.

---

## Context — why this lands on startd8-sdk

dev-os decided (2026-08-14) that **the navigator ("navig8r") consolidates into `startd8-sdk` going
forward**; ContextCore's `navigator/` is the prior home. dev-os REQ-10 (render the Summer-2026 code-review
benchmark as one `run → cell → role-review → file` drill-tree) assumed the forward-home navigator could
render a deep `children` tree "for free." A grounded review (CRP R1) **falsified that** — see below. The
capability exists; it just hasn't been ported yet. This note is the grounded scope of that port.

## Grounded state — what's here vs. what's in the prior home

**startd8-sdk navigator** (`src/startd8/navigator/`) — the forward home:

| Surface | State (grounded) |
|---|---|
| `Node` data model (`models.py`) | ✅ carries `children` / `child_keys` fields — the model is ready |
| `project.py` → `nodes_to_wireframe_plan` | ⚠ flattens to **2-level sections→items**; never recurses `node.children` (project.py:123-195) |
| `project.py` → `nodes_to_json` (`--format json`) | ⚠ emits a **flat list; omits `children`/`child_keys` entirely** (project.py:198-218) |
| `cli_navigator.py` | `--source {requirements\|capability-index}`, `--format {json\|html}` only. No `--renderer`, no `--source nodes-json`, no `--format a11y\|graph` |
| a11y / corpus-index renderers | ✘ not present |

`project.py:1` self-describes as a *"port of ContextCore navigator/render projection"* — but only the
wireframe projection was ported.

**ContextCore navigator** (`src/contextcore/navigator/`) — the prior home, **built + wired**:

| Capability | Evidence (grounded) |
|---|---|
| N-level drill tree | `render.py` `_tree_node_html(node, depth, open_depth)` recurses `node.children` into nested `<details>` (collapse-by-default via `open_depth`); `render_navigator_tree_html` wraps it |
| Wired to the CLI | `cli/navigator.py` `--renderer {wireframe,tree}` — *"tree: nested N-level drill-down"*, **default `tree` for `--source nodes-json`**; `render_navigator_tree_html` called at cli/navigator.py:635 |
| a11y view | `render_a11y.py` `render_html` / `render_a11y_to_file`; `--format a11y` |
| corpus index | `render_index.py` |
| pre-projected-graph source | `--source nodes-json` — *"loads a pre-projected Node graph (e.g. from a downstream exporter)"*; `sources_seam.py` renders it *"through the existing renderer (`render_navigator_tree_html`) rather than a bespoke one"* |

**Net:** the exact thing REQ-10 needs — *accept a pre-projected node tree and render it N-level* — is a
one-command path in ContextCore (`navigator build --source nodes-json --renderer tree`) and **absent** in
startd8-sdk.

## The port (proposed scope of the a11y-renderer track)

Migrate from ContextCore `navigator/` into startd8-sdk `navigator/`, in dependency order:

1. **`render.py` tree renderer** — `_tree_node_html` + `render_navigator_tree_html` (the N-level
   `<details>` drill). *Smallest slice that unblocks REQ-10.*
2. **`children` in `nodes_to_json`** — so `--format json` carries the tree (currently dropped).
3. **`--source nodes-json`** — accept a pre-projected Node graph from a downstream exporter (this is the
   seam benchmarks / dev-os projectors emit into).
4. **`--renderer {wireframe,tree}`** CLI flag (default `tree` for `nodes-json`, else `wireframe` for
   back-compat).
5. **`render_a11y.py`** (`--format a11y`) and **`render_index.py`** (corpus drill-to-leaf) — the rest of
   the a11y/cockpit family (REQ-06/07/08 lineage).

**⚠ Defect to resolve on port (do not carry it over):** ContextCore `render.py` (1023 lines) has
**duplicate top-level defs** — `_tree_node_html` at lines **378 and 824**, `render_navigator_tree_html` at
**502 and 953**. In Python the later def wins, so the first pair (~378–500) is **dead code**. Confirm which
copy is live (the 824/953 pair) and port only that; don't replicate the shadowed pair. (This is itself a
single-source hazard — a reader could port the dead one.)

## Interim for consumers (until the port lands)

Consumers that need a deep tree **today** can render on the prior home: emit the pre-projected Node graph
JSON, then `contextcore navigator build --source nodes-json --renderer tree`. This is the honest interim —
but it renders on the home being retired, so it's a bridge, not the destination.

## Why now / what it unblocks

- **dev-os REQ-10** (`benchmark-as-node-tree`) FR-3 depends on step 1–4; currently specified against a
  capability the forward home lacks. dev-os will rebase REQ-10 onto this track (make the dependency
  explicit) rather than claim pure reuse.
- **The consolidation decision** (navigator forward home = startd8-sdk) is not fully realized until the
  drill/a11y renderers live here — today the forward home is strictly less capable than the prior one for
  node-tree work.

## References (grounded homes — cite, don't copy)

- Forward home: `startd8-sdk/src/startd8/navigator/` (project.py, cli_navigator.py, models.py).
- Prior home: `ContextCore/src/contextcore/navigator/` (render.py, render_a11y.py, render_index.py,
  sources_seam.py, cli/navigator.py).
- dev-os: `VISUALIZATION-CAPABILITY-CATALOG.md` (§2 modalities, §3 reuse map), `REQ-10-Navigate-Benchmark-As-Node-Tree.md` (FR-3 + Appendix C R1-F①), `CLOSURE-LEDGER.md` CL-54.

*Grounded 2026-08-14 by direct read of both navigators (file:line above). No code changed by this note.*
