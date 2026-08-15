# Enhancement Backlog — Navigator Requirements-Visualization (HTH harvest)

**Source:** HTH Phase 4, seeded by the Phase-2.5 dormant inventory in
`RETROSPECTIVE_navigator-viz-delivery.md`. **CEP note:** focused single-pass backlog (NR-5 fork) —
2 grounded dormants + 1 standard amendment; full CEP divergence (VARY/CROSS/fusion) not warranted for
this count. **Auto-execute:** none — all rows are S/M with a judgment call (byte-identity or a design
choice); left as triaged rows for the human / the next Spec Delivery Loop pass.

| ID | Size | Enhancement | Grounded in | Value | Risk / gate |
|----|------|-------------|-------------|-------|-------------|
| **EB-1** | **S** | Wire `graph_projection.validate_graph_model` into `render_graph` — validate the projected graph before drawing; annotate/warn on dangling or duplicate edges instead of rendering them silently | D-2 (0 call sites; ported + tested, never runs) | the ported validator actually protects the render path; a malformed graph is surfaced, not drawn blind | low — additive; a warning path + one test. Keep byte-identity for valid graphs (warn only on invalid) |
| **EB-2** | **M** | Wire the **tree** (REQ-02) and **a11y** (REQ-03) renderers through `node_lenses.project_nodes`; route `compose` through `apply_node_lenses` so the aggregate is the single chokepoint | D-1 (3 of 4 renderers unlensed; `apply_node_lenses` 0 external consumers) | realizes REQ-04's "every renderer inherits the lenses" claim (soft-labeled in HTH P1); ends the `apply_node_lenses` thin-ice | **medium** — tree/a11y output *changes* (they'd apply audience×fluency lenses) → new goldens + a fresh byte-identity baseline; a real design decision, not mechanical |
| **EB-3** | **S** | Add a **reachability probe** to the Spec Delivery Loop's GATE-2 (stage 3): grep each new/ported public symbol for a call site in the real render/CLI path; warn if 0 | Retro Phase-4 clause 5 ("wired, not just built"); the process surprise that green tests masked D-1/D-2 | the loop catches dormants like D-1/D-2 automatically next time; converges with REQ-06 governance | low — advisory warn in the gate driver; feeds REQ-06 |

## Sequencing
1. **EB-3 first** (cheap, and it's the meta-fix — the probe that would have caught EB-1/EB-2 at delivery).
2. **EB-1** (cheap, low-risk, closes the clearest dormant).
3. **EB-2** (needs a byte-identity decision + new goldens — run it through the Spec Delivery Loop as its
   own spec increment, since it changes renderer output).

Each row, when picked up, re-grounds at build time (a backlog item is a belief — re-verify the claim +
the code before building).
