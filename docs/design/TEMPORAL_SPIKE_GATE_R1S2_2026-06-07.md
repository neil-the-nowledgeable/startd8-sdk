# R1-S2 Decision Gate — Temporal Spike (Axis A)

**Date opened:** 2026-06-07
**Parent evaluation:** `CROSSPLANE_TEMPORAL_SUITABILITY_EVALUATION_2026-06-07.md` (§8.1)
**Gate question:** Does the Temporal spike start — i.e., does adopting a durable-execution
engine beat (a) the sized unwritten durability code of the next Plan Batch Orchestration
increment and (b) the scored harden-in-place baseline?
**Decision:** ☑ **NO-GO + harden in place** — maintainer sign-off 2026-06-07 (R5-S7).
**This document is the ADR of record (R7-S5).**

---

## Gate Input 1 (R6-S1) — The "unwritten code" Temporal is bid against

Source: `PLAN_BATCH_ORCHESTRATION_REQUIREMENTS.md` v0.4 / `PLAN_BATCH_ORCHESTRATION_PLAN.md`
v1.2, surveyed against live code 2026-06-07.

**Headline finding: a large share of the durability code the evaluation assumed was unwritten
has been written since — cheaply, additively, outside the SDK.** As of 2026-05-31:

- Essential ② `t-orchestrator-loop` is **DONE**: `cap-dev-pipe/run-batch-contractor.{sh,py}` —
  pure-stdlib sequential loop with `fcntl.flock` single-in-flight, `batches.json` + seed-hash
  pinning (FR-12), **cross-batch resume off `batch-ledger.json`**, and a project-state gate.
  Two additive files, **zero changes to existing SDK code**.
- Essential ③ `t-batch-record-writer` is ≈done by reuse: the existing `BatchLedger`
  (`contractors/batch_postmortem.py`) already provides atomic persistence, seed-checksum
  pinning, per-run snapshots — "Increment 0 reuses it; no new persistence."
- The phantom checkpoint-v4 `wave_*` machinery is confirmed dead and **will not be extended**
  (R3-S2 of that doc's review): fresh `batch_record_v1.json` ≈ BatchLedger serialization.

**Remaining Increment-1 durability plumbing (SDK-side, not yet written):**

| Component | Est. LOC | Engine-replaceable? |
|---|---|---|
| Batch-transition gate (pre/post checks, quarantine, override audit) | ~250 | **Mostly no** — validation/quarantine semantics are domain decisions; only the retry/sequencing shell is engine territory |
| Pinning + cost-budget enforcement (FR-6/FR-12 wiring) | ~150–250 | No — domain policy |
| Dependency-closure validation (FR-2) | ~100 | No — domain validation |
| Ledger extension + run-end hooks | ~100–150 | Partially |
| Tests | ~150 | n/a |
| **Total remaining** | **~750–900** | **Engine-replaceable slice: ~150–250** |

**The decisive scope fact:** intra-batch parallelism — *waves*, the single strongest Temporal
fit (child workflows) and the evaluation's headline forward-value claim — is **Increment 3,
guarded, default-off, deferred indefinitely**, and blocked on context coherence (RUN_008 →
CKG Knowledge Provider), which is a *domain* problem no execution engine solves.

## Gate Input 2 (R3-S1) — Harden-in-place baseline, scored against live code

| Site | Defect (verified) | Fix | LOC | Risk |
|---|---|---|---|---|
| Repair circuit breaker | Module-global `_circuit_breaker_state` dict (`repair/orchestrator.py:100`), cross-run scope leakage, test-order coupling | `RepairSession` instance state threaded through `run_file_repair()` | ~50 | Medium (2 prime_contractor call sites, ~16 test touchpoints) |
| Event-history trim race | In-place slice rebind under RLock (`events/bus.py:139–145`); race is real but narrow | `collections.deque(maxlen=...)` | ~15 | Low |
| 3-layer resume validation | No cross-layer correlation; checksum mismatch is warn-only (callers ignore); parse-clean corruption passes | Version bounds enforcement + opt-in strict checksum + state-file content hash | ~115 | Medium-high (strict mode must be opt-in) |
| **Total** | | | **~180** | |

This confirms the evaluation §7 baseline column's ~200-LOC estimate against actual code.

## Gate Input 3 (R3-S5) — Inventory reproducibility

`scripts/survey_orchestration_loc.py` committed (`aae8a13c`); reproduces §2 within rounding
(117,349 lines / 236 files). The ~4–6k replaceable-plumbing estimate stands.

---

## Gate Math

The evaluation's adoption logic (§8.1): the spike is justified because it competes against
*unwritten* durability code. The gate inputs falsify that premise **as of today**:

1. The riskiest unwritten piece (cross-batch resume + sequential orchestration) **already
   shipped** as ~2 additive script files reusing the tested BatchLedger — at roughly the cost
   the Temporal spike's *Step 0 alone* would consume.
2. The remaining Increment-1 durability is ~750–900 LOC, of which only **~150–250 LOC is
   engine-replaceable**; the rest is gate/validation domain policy that stays under any engine.
3. The wave/child-workflow use case — the forward-value core of the CONDITIONAL YES — is
   deferred indefinitely and blocked on a domain problem (context coherence), not a durability
   problem.
4. Against that, the spike's cost side is unchanged: `RunDriver` extraction from a 5,877-line
   run loop, a new external binary + worker lifecycle, OTel unification, contracts, and
   net-new supervision code that the R7-S4 accounting rule counts *against* the lens.
5. The harden-in-place baseline (~180 LOC, known code, no new deps) addresses every *named*
   fragility for less than the spike's charter-writing overhead.

**Per the evaluation's own decision rule — "adoption must state why the engine beats both" —
no such statement can honestly be made today.**

## Recommendation: NO-GO

The gate **closes without starting the spike**. The evaluation's verdict effectively resolves
from CONDITIONAL YES to **NOT NOW** for Axis A — not because Temporal is a poor fit, but
because the unwritten code it was bid against got written (cheaply) and the remaining fit
surface is too small to justify the platform cost.

**Action item in lieu of the spike:** execute the harden-in-place baseline (~180 LOC, three
fixes, recommended order: circuit breaker → deque → resume hardening).
**✓ EXECUTED same day** (`9c930644`): `RepairSession` per-run breaker scope (wired into
`IntegrationEngine`), `deque(maxlen=)` event history, `FeatureQueue` state-hash integrity +
loud refusal on corrupt/invalid resume state; 22 new tests. Bonus: fixed the latent
`forward_manifest=` TypeError (swallowed since `439c615d`) that had silently disabled
post-integrate contract-violation repair.

## Re-open triggers (this gate, not the whole evaluation)

1. **Waves un-deferred:** Increment 3 intra-batch parallelism enters scope (context coherence
   solved via CKG Knowledge Provider) — child-workflow orchestration becomes a real, sizable
   target again.
2. **Durable human-in-the-loop becomes a requirement:** the R6-S7 upside (human bookends as
   signals — pause/resume across days) gets product pull.
3. **Measured resume failures:** batch runs start spanning hosts/days and the file-state
   resume demonstrably fails (capture the R4-S3 baseline if this is suspected).

Axis B/C triggers are unchanged (evaluation §1 footnote, §6 trigger table).

---

*Signed off 2026-06-07: NO-GO + harden-in-place execution. This is the ADR of record (R7-S5);
the parent evaluation's Appendix A row for R1-S2 links here.*
