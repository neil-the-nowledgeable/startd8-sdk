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

---

## REQ-08 (NL-Programming pipeline) — HTH harvest 2026-08-16 (`86f5d9f3`)

From the Stage-7 harvest of the 9th delivery. Two XS rows were auto-applied in the harvest; three
remain as triaged rows (re-ground before building — a backlog item is a belief).

| ID | Effort | Row | Evidence | Status |
|----|--------|-----|----------|--------|
| ~~**R8-EB-1**~~ ✅ | XS | Add a test for `verify --format html` (verdicts-as-Nodes arm) | `cli_navigator.py:303` html arm had no test | **DONE** (harvest) |
| ~~**R8-EB-2**~~ ✅ | XS | Remove dead `'verify'` from `_READONLY_NAV_SUBCOMMANDS` (self-exec catches it first) | `verify_oracle.py:58` | **DONE** (harvest) |
| **R8-EB-3** | S | Wire `topo_order()` as a fail-loud build-time acyclicity assert in `nodes_from_pipeline` (or demote to a private test helper) — it is production-dormant (test-only caller) | `sources_pipeline.py` `topo_order`; only caller `test_pipeline_source.py:95` | open |
| ~~**R8-EB-4**~~ ✅ | S | Implement the D-B "FR id" query in `pipeline_provenance` (resolve an FR-id → its `Lives`/`Touches` file, then walk) | `provenance.py` `_fr_file_path` + `requirement_nodes` param; FR named on the intent-origin row | **DONE** (`5b5cee9e`+) — resolves an FR-id → its first `code` `Lives:`/`Touches:` file; unknown/unresolvable FR → honest not-found. +6 tests |
| ~~**R8-EB-5**~~ ✅ | M | Expose `pipeline_provenance` via an operator CLI surface | delivered alongside EB-4 (a wired consumer is what keeps the FR-id path non-dormant) | **DONE** — `navigator provenance --query <fr-id\|path> [--requirements <doc>]`; JSON chain, exit 1 on not-found so CI can distinguish traced from unowned |

**Value-path lesson carried forward:** the GATE-2 reachability probe scored `topo_order` "wired" on a
**test-only** reference — Phase-2.5 must grep for a *non-test* caller to catch production-dormancy the
probe can't see.

### R8-EB-4/5 own HTH harvest 2026-08-16 (`fc647853`)

The FR-id query + `provenance` CLI got their own full harden-then-harvest (they shipped after the parent
REQ-08 harvest). Phase-1 fixed one Low/UX defect (the no-corpus not-found reason leaked the internal
`requirement_nodes` param name — now interface-agnostic + a friendly CLI pre-check names `--requirements`).
Phase-2.5 inventory: **5 new symbols scanned, all wired** (no dormants — the capability shipped with its
CLI consumer by design). One new row:

| ID | Effort | Row | Evidence | Status |
|----|--------|-----|----------|--------|
| ~~**R8-EB-6**~~ ✅ | S | Give `navigator provenance` a `--format html` (project the chain rows to Nodes → existing tree renderer, mirroring `verify --format html`) | `cli_navigator.py` `provenance` | **DONE** (`499694f0`) — `--format json\|html`; html renders `pipeline-provenance` Nodes; REQ-08 reconciled to v0.4 (FR-6 signature + FR-9 provenance CLI). +4 tests |

**Retro surprise (belief→actual):** an FR-id traces only when its file falls under a *modeled compiler
stage* — so a spec's own FRs implemented outside those stages (e.g. REQ-08's, in `navigator/`) honestly
report not-found. A query capability's reach is bounded by the domain model it queries; the command help
says so rather than implying every FR traces.
