# Enhancement Backlog — Navigator Requirements-Visualization (HTH harvest)

**Source:** HTH Phase 4, seeded by the Phase-2.5 dormant inventory in
`RETROSPECTIVE_navigator-viz-delivery.md`. **CEP note:** focused single-pass backlog (NR-5 fork) —
2 grounded dormants + 1 standard amendment; full CEP divergence (VARY/CROSS/fusion) not warranted for
this count. **Auto-execute:** none — all rows are S/M with a judgment call (byte-identity or a design
choice); left as triaged rows for the human / the next Spec Delivery Loop pass.

| ID | Size | Enhancement | Grounded in | Value | Risk / gate |
|----|------|-------------|-------------|-------|-------------|
| ~~**EB-1**~~ ✅ | **S** | **DONE** (`1bd4bf95`) — `render_graph` now calls `validate_graph_model` on the projected model and surfaces dangling/duplicate-edge issues as a visible escaped banner; valid graphs stay byte-identical (empty banner). Reachability probe now reports the symbol `wired`. | D-2 (was 0 call sites) | the ported validator protects the render path; a malformed graph is surfaced, not drawn blind | shipped — additive; +2 tests; 294 pass |
| ~~**EB-2**~~ ✅ | **M** | **DONE** (`90efe69f`, via REQ-09 through the Spec Delivery Loop) — tree + a11y gained the opt-in `role`/`fluency` seam; `role=None` → byte-identical, a role → lensed. FR-3 took NR-4 (tree calls `apply_node_lenses` directly; compose proven byte-unsafe, untouched). `apply_node_lenses` export-only 0/1 → **wired 2/1**. | D-1 (was 3 of 4 unlensed; `apply_node_lenses` thin-ice) | realizes REQ-04's "every renderer inherits" claim; ends the thin-ice | shipped — byte-identical default (goldens unedited); +8 tests; 302 pass |
| ~~**EB-3**~~ ✅ | **S** | **DONE** (`a7618250`) — reachability probe in GATE-2: `--reachability <files.py>` classifies each public symbol wired \| export-only \| DORMANT; `--strict` exits 1. Independently re-catches D-2 (`validate_graph_model` 0/0). | Retro Phase-4 clause 5 ("wired, not just built") | the loop now catches dormants like D-1/D-2 at delivery; converges with REQ-06 | shipped — advisory by default; +4 tests |

## Sequencing
1. ~~**EB-3 first**~~ ✅ **DONE** (`a7618250`) — the meta-fix; the probe now catches EB-1/EB-2-class dormants at delivery.
2. ~~**EB-1**~~ ✅ **DONE** (`1bd4bf95`) — the D-2 dormant the probe flagged is now wired.
3. ~~**EB-2**~~ ✅ **DONE** (`90efe69f`, via REQ-09) — D-1 closed; byte-identity held (NR-4, no golden churn).

**Backlog CLEARED** — all three HTH-harvested rows shipped; both dormants (D-1, D-2) closed and the
reachability probe reports no dormant lens symbols.

Each row, when picked up, re-grounds at build time (a backlog item is a belief — re-verify the claim +
the code before building).
