# Pilot report — the `$0` det-plan projector (REQ-29 FR-7)

**Date:** 2026-08-17 · **For:** `REQ-29-det-plan-projector.md` · **Format piloted:** `SCHEMA_det-plan-0.1.md`
**Method:** `/reflective-adoption` — the two hand-authored PLANs are the ground truth that reveals what the
`$0` projection is missing; the delta is the deliverable. **Projector:** `src/startd8/plan_codegen/`.

> **One line:** the projector cleanly realizes the *mechanical* half of a plan (FRs→iterations,
> targetFiles, gates, the phantom audit, the Verify rollup) at `$0`; the two golden PLANs show the
> *strategic* half (role-based batching, the build-order DAG, planning discoveries, the CRP log) is
> **human-gated residue** — exactly what the charter predicts. The one structural gap the pilot forces
> back into the grammar: **det-req has no parsed FR-dependency field, so `dependsOn` is always empty.**

## What was run

`startd8 generate plan --requirements <req>` over the five-cell iteration-1 matrix. Projected artifacts
land beside their reqs as `*.projected.md`; conformance/liveness findings emit as SARIF via the ONE
`coverage_map/findings_sarif` (imported, not vendored).

| # | Pilot REQ | Cell | Result |
|---|-----------|------|--------|
| 1 | **REQ-08** (9 FRs) | golden-parity ⭐ | projected → `REQ-08-….projected.md` (9 iters, all `llm-integration`), 0 conformance errors; diffed vs `PLAN-nl-programming-pipeline-provenance.md` |
| 2 | **REQ-01** (19 FRs) | golden-parity / stress ⭐ | projected → `REQ-01-….projected.md` (19 iters), 0 conformance errors; diffed vs `PLAN-01-sdk-node-home.md` |
| 3 | **REQ-03** | negative-gate | **projected NOTHING** — `is_plan_owed` False (pairs with a *brief*, no `plan deferred`, no `PLAN-…`); reported skipped, exit 0 ✅ |
| 4 | **REQ-16** (4 FRs) | demand-clearing | conformant `det-plan/0.1`, **zero findings** (pairsWith LIVE) → `REQ-16-….projected.md` ✅ |
| 5 | **REQ-17** (4 FRs) | demand-clearing | conformant `det-plan/0.1`, **zero findings** (pairsWith LIVE) → `REQ-17-….projected.md` ✅ |

*(Cross-repo REQ-seat pilots deferred — correct-absence; iter-1 stays SDK-internal.)*

## The golden-diff — every delta and its disposition

For REQ-08 and REQ-01 we diffed the `$0` projection against the hand-authored PLAN. Sections the human
PLAN carries but the projection lacks (or vice-versa), each dispositioned **fold-into-grammar** (the
projector should derive it) or **human-residue** (genuine judgment, the charter's human-gated tail).

| Δ | The human PLAN has… | Projection today | Disposition | Rationale |
|---|---------------------|------------------|-------------|-----------|
| **D-1** | **Role-based FR batching** (REQ-01: 6 iters F-1…F-5+F-CC-1 grouping FRs by role; REQ-08 build-order groups FR-1+FR-4 as roots) | one iteration per FR (19, 9) | **human-residue** | The two goldens batch the *same* FRs differently by strategic role, from no authored signal — the charter's "ordering strategy is the human-gated residue". The projector emits the honest per-FR scaffold; the human re-batches. |
| **D-2** | **The build-order DAG** (REQ-08 `FR-1 → FR-2`, `FR-4 → FR-5 → FR-7 → FR-8`; REQ-01 `F-1→F-2→F-3→F-4`) | `dependsOn` **empty** everywhere | **fold-into-grammar (cross-kit)** | `dependsOn` is empty **not by choice** but because **det-req's single-line FR grammar has no parsed dependency field** — `Verify:` swallows to EOL, `Touches:` swallows up to `Verify:`, leaving no slot. See **Grammar revision G-1**. The strategic *ordering* stays residue; the *ability to author an edge at all* must be folded in. |
| **D-3** | **"Discoveries / Planning Insights"** table (what planning found that revised the req) | absent | **human-residue** | A reflection bookend (charter §4 BACK) — not a `$0` projection of the req; it is *authored during* planning. Correct-absence. |
| **D-4** | **Appendix A/B/C CRP review log** | absent | **human-residue (other kit)** | Belongs to **det-crp-kit** (the CONVERGENT REVIEW), not det-plan. Reconcile-don't-fork (charter inv. 6). |
| **D-5** | **"Reference audit (phantoms)"** / **Design table (`★` to-be-created)** | **§4 reuse/phantom audit** (each Touches/code-Lives ref resolved on disk) | **folded ✓ (partial)** | The projector already derives exists/absent. The *extend-vs-create intent* (`★`) and the *symbol*-level design remain human judgment. |
| **D-6** | **"Verify (whole change)"** rollup | **§5 Verify rollup** (every FR verify carried forward) | **folded ✓** | Fully derived. |
| **D-7** | **"Requirements Coverage Matrix"** (FR→section grid) | the per-iteration `frs[]` **is** the coverage (every FR maps to exactly one iteration) | **folded ✓ (implicit)** | The one-per-FR scaffold makes coverage total by construction; an explicit rollup line is an optional future nicety. |
| **D-8** | *(no `costClass` — a det-plan/0.1 addition)* | `costClass` present but **coarse** (all `llm-integration`) | **fold-into-grammar (note)** | Every navigator FR is hand-written `src/startd8/navigator/*.py` → the honest single band. A *finer* band needs a per-FR realization declaration in det-req (there is none). See **Grammar revision G-2**. |

### Bugs the pilot surfaced and fixed in the projector (before conclusions)

- **costClass mis-band:** REQ-08 FR-1 cites a `doc` vocabulary-home in `Lives:` while Touching code;
  the first cut banded the whole batch `human`. Fixed: the regime is driven by what the FR **builds**
  (`Touches`), and `human` is checked *last* (only for a no-code, doc-only FR).
- **`Depends:` pollutes `Touches`:** an authored `Depends: FR-x` between `Touches:` and `Verify:` leaked
  into the Touches capture (det-req has no `Depends` slot). Fixed defensively: the projector reads
  `Depends:` from the raw line and **strips** the span before `parse_fr_lines`. This is the symptom of
  **G-1** below.

## Fold-back into `det-plan/0.1` (the grammar revisions this pilot produced)

Applied to `SCHEMA_det-plan-0.1.md` (see its §2/§3 revision notes):

- **G-1 (cross-kit, det-req) — an authored FR-dependency field is required for a non-trivial `dependsOn`.**
  det-plan/0.1 §3 assumes the req carries an *authored acyclic dependency topology*, but the det-req
  single-line FR grammar has **no parsed slot** for it. Until det-req adds a first-class `Depends:` FR
  field (position-defined, parsed like `Serves:`), every projected `dependsOn` is empty and the
  build-order DAG is 100% human-residue. **The projector already parses a `Depends: FR-x, FR-y` field
  when present** (and cycle-rejects it via `queue.py`) — the gap is upstream, in det-req. Recorded as a
  det-req-kit grammar request.
- **G-2 (det-plan §2) — `costClass` is coarse absent a per-FR regime.** Documented that the default
  band is derived from `Touches` path + `Lives` type (a `$0`-codegen target → `deterministic-$0`, a
  doc-only FR → `human`, else `llm-integration`); a finer band needs a per-FR realization declaration in
  the req. The single-band rollup is honest, not a defect.
- **G-3 (det-plan §2) — the default grouping is one-iteration-per-FR.** The pilot proved transitive
  shared-`Touches` batching *over-merges* on a hub file (REQ-08's 9 FRs → 1 iteration via
  `cli_navigator.py`). §2's "batch FRs that share Touches" is retained as an opt-in (`--strategy
  shared-touches`); the honest default is the transparent per-FR scaffold, with strategic batching left
  as the human overlay.

## Hard exit criteria — status

- **`$0` / no LLM:** ✅ asserted (`test_projector_makes_no_network_or_llm_call` forbids `socket.socket`;
  `test_projector_source_imports_no_llm_provider_modules` bans agent/provider/httpx imports).
- **Never-inferred:** ✅ every `dependsOn` edge traces to an authored `Depends:`; a cyclic req is
  rejected by `queue.py` via `PlanDependencyCycleError` (`test_cyclic_depends_rejected_with_named_error`).
- **Golden pilots run:** ✅ REQ-08 + REQ-01 project, diff recorded above, deltas dispositioned.
- **Negative gate:** ✅ REQ-03 projects nothing (`test_negative_gate_solo_req_projects_nothing`).
- **Demand:** ✅ REQ-16 + REQ-17 each produce a §10-conformant `det-plan/0.1` (zero findings).
- **Reuse-not-vendor:** ✅ the SARIF path imports `coverage_map/findings_sarif`
  (`test_sarif_path_imports_not_vendors_findings_sarif`); no vendored copy.
- **Additive / byte-identical:** ✅ `test_no_profile_is_byte_identical` passes unedited; the existing
  `generate {frontend,backend,scaffold,views}` are untouched; every projected plan validates against §10.

## What to build next (out of scope here)

- **det-req `Depends:` FR field (G-1)** — the upstream grammar slot that makes `dependsOn` real. The
  projector is ready for it today.
- **det-plan-kit dir in dev-os** — adopt the format kit cross-repo (charter §8); this REQ built the
  SDK-side projector only (NR-5).
