# Retrospective — Navigator Requirements-Visualization Delivery (Hansei)

**Pilot (raw material):** this session's navigator requirements-visualization delivery —
REQ-02 tree · REQ-03 a11y + corpus index · REQ-04 lift-lenses · REQ-05 graph renderer — plus the
**Spec Delivery Loop** (LOOP_CATALOG #6) that delivered REQ-05 and this HTH pass over the result.
**Window:** 2026-08-15. **Method:** `/reflective-retrospective` as HTH Phase 3 (grounded in code, not docs).

## Phase 2.5 — Dormant inventory (grounded, `rg`, not asserted)

| Touch | Grep / evidence | Status |
|-------|-----------------|--------|
| `render_tree` / `render_a11y` / `render_index` consume `node_lenses` | 0 hits each (`render_graph` = 8) | **dormant** (3 of 4 renderers unlensed) |
| `node_lenses.apply_node_lenses` external consumers | 0 (reached only internally via `project_nodes`) | **soft-only** (thin ice — dies if graph is removed) |
| `node_lenses.project_nodes` | `render_graph.py` (graph renderer) | wired |
| `node_lenses.{has_jargon, GAP_STATUSES, HONEST_SKIP_ROUTES}` | `compose.py` | wired |
| `node_lenses.apply_section_lenses` | `compose.py:311` | wired |
| `graph_projection.validate_graph_model` | **0 call sites** (never called by `render_graph` or CLI) | **dormant** (ported + tested, never runs) |
| renderer entrypoints (`render_*_to_file`, `render_navigator_{tree,graph}_html`) | all have `cli_navigator.py` call sites | wired |
| Spec Delivery Loop stage-0 gate (`navigator_spec_delivery_loop.py`) | `--status` flagged REQ-01/seat-req; delivered REQ-05 | wired + exercised |

Scanned ~12 symbols; **2 genuinely dormant**, 1 soft-only, rest wired.

## Phase 3 — Reflection (belief → actual)

| Kind | What I believed | What the actuals revealed | So the standard is… |
|------|-----------------|---------------------------|---------------------|
| **process** | GATE-2 (green tests) proves the build is *wired* | 290 tests passed while `validate_graph_model` sat unwired **and** 3 renderers stayed unlensed — green ≠ reachable | **GATE-2 must include a value-path/reachability check** (the HTH §1.5 audit), not only test-pass. Fold a reachability probe into the Spec Delivery Loop. |
| **artifact** | REQ-05 FR-1 "ported `validate_graph_model`" = done | 0 call sites — the render path never validates the projected graph | Wire it into `render_graph` (validate → warn/annotate on dangling/dupe edges) or soft-label FR-1. → CEP |
| **artifact** | REQ-04 "every renderer inherits the lenses" | only `graph` consumes the aggregate; tree/a11y/index don't | Wire tree + a11y through `project_nodes`; route `compose` through `apply_node_lenses` as the single chokepoint (soft-labeled P1). → CEP |
| **process** | "port + test" is enough for a ported symbol | a ported validator that is tested but uncalled is dormant | **"ported + tested" ≠ "wired"** — a port's acceptance must include a call site in the real path. |

## Phase 4 — The standard this delivery PROVED

**The Standalone Navigator Renderer pattern** (proven 3× — a11y, index, graph; ready for Yokoten):
1. **Own HTML shell; never `import wireframe_view`** — asserted by an import-line test (not prose).
2. **Reuse shared XSS helpers** (`_safe_href`/`_safe_color`), never copy them (Kagami — one live def).
3. **Port-hazard gate:** every ported symbol has a single-live-def test (`count("def X(") == 1`).
4. **App-scaffold byte-identity preserved UNEDITED** — the wireframe golden tests never change.
5. **NEW clause the dormants add:** a ported/lifted capability's acceptance includes a **reachability
   check** — a call site in the real render/CLI path, not just existence + a unit test. ("Wired, not
   just built.") This is the HTH §1.5 audit promoted into the renderer standard.

The **Spec Delivery Loop** (LOOP_CATALOG #6) is the delivery process this pilot proved; clause 5 above
is the one amendment the retro earned — **its GATE-2 should run a reachability probe**, because a green
suite here masked two dormants.

## Phase 5 — Lessons

- **Green tests mask dormants.** A passing suite proves the code *works when called*; it does not prove
  it *is* called. Detection: grep public/ported symbols for call sites in the real path. Recovery:
  wire or soft-label. (Recurs across the corpus — EC-AP-01 read_history, and now `validate_graph_model`.)
- **A lifted "shared" transform is only shared once ≥2 consumers call it.** One consumer = a rename with
  extra indirection. `apply_node_lenses` (1 internal consumer) is the tell.

## Phase 6 — Yokoten + feed-forward

- **Yokoten:** apply clause 5 (reachability in acceptance) to the remaining specced renderers
  (REQ-06/07/08) via the Spec Delivery Loop's GATE-2, and to the standalone-renderer standard.
- **Feed-forward:** the two dormants (D-1 lens adoption, D-2 `validate_graph_model` unwired) are CEP
  prior-art (HTH Phase 4). The amended GATE-2 becomes an input to the next `/reflective-requirements`.
