# Plan Batch Orchestration — Implementation Plan

**Version:** 1.2 (R1 applied; R2 + R3 triaged → R3-distilled MVP is the canonical build surface)
**Date:** 2026-05-29 (v1.2 triage 2026-05-31)
**Pairs with:** `PLAN_BATCH_ORCHESTRATION_REQUIREMENTS.md` (v0.4)

> **Build surface (v1.2):** implement the **Part-4 essential task set** (below), not the §7 v1.1 table.
> The §1–§9 body and §7 table are retained as rationale/traceability. Canonical order:
> `t-baseline-characterization` → `t-orchestrator-loop` → `t-batch-record-writer` (≈ already built:
> `BatchLedger` in `contractors/batch_postmortem.py`) → `t-batch-transition-gate` →
> `t-batch-partitioner` → `t-context-inherit`. **Do NOT extend checkpoint-v4** (verified phantom —
> see requirements R4). First increment in progress: **Increment 0 — script the orchestrator loop.**

This plan is grounded in a deep read of the existing wave/lane/dependency machinery and
the parallel-generation postmortems. It deliberately scopes to **sequential inter-run
batching** and treats parallelism as studied-but-deferred.

---

## 1. What actually exists (grounded, with `file:line`)

| Primitive | Location | What it does | Reuse for sequential batching |
|-----------|----------|--------------|-------------------------------|
| Topological order | `contractors/context_seed/shared.py:243-293` `_topological_sort()` | DFS + white/gray/black cycle detection; orders tasks so deps precede dependents; **falls back to input order on cycle** | **Order batches + tasks within a batch** |
| Lane grouping | `contractors/artisan_contractor.py:970-1026` `compute_lanes()` | **Union-Find** on shared `target_files` **+** `depends_on` → connected components that must run serially | **Group file-coupled tasks into the *same* batch** |
| Cycle validation | `contractors/queue.py:413-482` `_detect_and_break_cycles()` | breaks circular deps; escalates to clearing deps on deadlock; **feature-serial mode only** | **Validate acyclicity before each batch** |
| Shared-file manifest | `contractors/context_seed/design_support.py:449-522` | `build_shared_file_manifest` / `compute_lane_to_file_mapping` / `compute_critical_path_tasks` — **computed but UNUSED** | **Decide batch boundaries; pick context to inject** |
| Subset execution | `run-prime-contractor.sh` (`--task`/`--task-filter`/`--max-features`) → `FeatureQueue` | runs a task subset; **does NOT recompute wave/lane** | **Execute one batch's task IDs** |
| Resume state | `contractors/artisan_contractor.py:532-540` checkpoint **v4** (`wave_assignments`, `completed_waves`, `current_wave`) | persists wave/lane execution state | **Cross-batch resume ledger** |
| Partition producer | `workflows/builtin/plan_ingestion_emitter.py:976` | **`wave_metadata=None` (stubbed)** | **The hook to emit batch/partition metadata** |

**Key correction vs the brief:** there is **no `compute_waves()`**. `wave_index`
(`shared.py:64-65`) is parsed from the seed (upstream-annotated), **never computed by the
SDK**. Partitioning must be built from `_topological_sort()` + `compute_lanes()` (+ the
shared-file manifest), not from a non-existent wave computer.

---

## 2. Why parallel failed — the constraint the new design MUST respect

Per `CONTEXT_CORRECTNESS_BY_DESIGN.md:43-211` and `ARTISAN_RUN2_POSTMORTEM.md:92-130`:

- **It was NOT scheduling/locking.** Topo order, cycle-breaking, and shared-file serial
  lanes all work.
- **It was design-time *context isolation*.** Lane-peer tasks that touch the same files
  design **incompatible** changes (e.g. A adds `class HealthChecker`, B adds
  `HealthMonitor` to the same `utils.py`) because the DESIGN phase iterates a flat task list
  with only **300-char summaries** (`shared.py:71-93`) — no lane-aware shared context. The
  "Lane Coherence Invariant" (`SharedContext(t_i) ≈ ∅`) is violated.
- **Context compression** also drops requirement-specific parameters across
  requirements→seed→design (Category-2 defects: SDK context-propagation, not plan gaps).

---

## 3. Dependency semantics — "how dependencies can and cannot work"

**CAN:** `depends_on` ordering (topo); shared-`target_files` serial execution (lanes); design
context carrying plan/requirements + 300-char prior-task summaries.

**CANNOT (reliably):** a task depend on another task's **generated output** at *design*
time (context isolation); parallel design of file-sharing tasks; wave-ordered *design*
(design ignores `wave_index`); subset execution does **not** revalidate dependencies
(inherited from seed).

---

## 4. The make-or-break implication for *sequential* batching

Sequential batching removes the **concurrency** of incompatible design — batch *N* is fully
generated **and on disk** before *N+1* runs. **But it does not automatically fix context
isolation at the batch seam:** batch *N+1*'s DESIGN phase still receives only 300-char
summaries, not batch *N*'s generated code/design docs. A naive "loop + gate" batcher would
reproduce the same incompatible-design failure **across** batch boundaries.

Two mitigations, both in scope:
1. **Inter-batch context inheritance (the core fix):** inject batch *N*'s generated
   artifacts / design docs into batch *N+1*'s design context — at least for the files batch
   *N+1* touches (use the shared-file manifest to scope it and avoid token bloat).
2. **File-cohesive, dependency-closed partitioning:** keep file-coupled / tightly-dependent
   tasks in the **same** batch (via `compute_lanes()` + manifest), so cross-batch context
   need is minimized in the first place.

---

## 5. Components

- **`BatchPartitioner` (NEW, SDK).** In: ingested seed tasks (`depends_on`, `target_files`).
  Out: an ordered list of **dependency-closed, file-cohesive** batches. Reuses
  `_topological_sort` (order) + `compute_lanes` (file cohesion) + shared-file manifest
  (boundary decisions) + `_detect_and_break_cycles` (validate). Deterministic.
- **Partition emitter (NEW, fills `plan_ingestion_emitter.py:976`).** Emits batch/partition
  metadata into the seed **for ordering only** — must **not** flip on cross-lane parallel
  execution (see Risk R1).
- **`BatchOrchestrator` (NEW, cap-dev-pipe).** Loop: for each batch → `run-prime-contractor
  --task-filter <batch ids>` → **validation gate** → record state → resume → next batch.
- **Inter-batch context injection (NEW).** Make batch *N+1* design context include batch
  *N*'s outputs (scoped via manifest). The riskiest, highest-value piece — build last, iteratively.
- **REUSE as-is:** `--task-filter`, checkpoint-v4 resume state, topo/lanes/cycle-detect.
- **Cohesion-vs-closure merge rule (NEW — R1-S2):** a `compute_lanes()` component merges into
  the **smallest dependency-closed batch containing the whole lane**, up to a **max batch
  size** (else a named error); deterministic tie-break (NFR-2).
- **Cross-batch rollback (NEW — R1-S5):** on gate failure, batch *k*'s partial artifacts are
  **quarantined**; inter-batch context injection reads only **completed** batches.
- **Partition pinning (NEW — R1-S6):** persist partition + **seed hash** in the resume
  ledger; reuse on resume; **fail loudly** on hash mismatch (no silent re-partition).
- **Observability sink (NEW — R1-S7):** extend the checkpoint-v4 ledger (or per-batch OTel
  spans) with batch ID / task IDs / status / cost / gate result — the concrete FR-7 store.
- **Operator-override interface (NEW — R1-S8):** define the operator-supplied batch format +
  `--task-filter` hand-off; **validate overrides still satisfy FR-2 closure** (or an explicit
  "operator assumes responsibility" bypass).

---

## 6. Iterative delivery (revised by planning)

- **Increment 0 — Orchestrator loop over operator-defined batches.** Loop + validation gate
  + cross-batch resume ledger. No partitioner. Codifies this session's manual cadence.
  **Seam caveat (R1-S4 — do not understate):** batch *N+1*'s **DESIGN** phase still runs on
  300-char summaries *before* IMPLEMENT touches the on-disk code, so Increment 0 can emit an
  incompatible *design* even though batch *N*'s code exists. **Guardrail:** require the
  operator to keep file-coupled tasks in **one** batch (or restrict cross-seam tasks to
  edit/IMPLEMENT-only), and label the residual incompatible-design risk explicitly until
  Increment 2 closes it.
- **Increment 1 — `BatchPartitioner`.** Auto-derive dependency-closed, file-cohesive batches
  (topo + lanes + manifest). Operator override allowed. Emit partition metadata (ordering only).
- **Increment 2 — Inter-batch context inheritance.** Inject prior-batch outputs into the next
  batch's design context (the parallel-failure fix, applied to seams). Add a
  context-coherence regression test (incompatible-design detection).
- **Increment 3 (guarded — maybe never).** Intra-batch parallelism, only if Increment 2
  proves context coherence is solvable. **Default off.**

---

## 7. Task decomposition

| Task | Description | Complexity | Increment | FRs |
|------|-------------|------------|-----------|-----|
| t-orchestrator | cap-dev-pipe `run-batch-contractor.sh`: loop `run-prime-contractor --task-filter` over batches + validation gate + resume ledger | MODERATE | 0 | FR-3,4,5,6,7 |
| t-resume-ledger | Cross-batch state (reuse checkpoint-v4 fields): resume from next incomplete batch; **partition pinning (seed hash, fail-loud on change)**; **per-batch provenance/cost sink** | MODERATE | 0 | FR-5,7,12 |
| t-reuse-verify | **Characterization tests pinning each §1 primitive at its anchor** (topo fallback; `compute_lanes` unions on `target_files`+`depends_on`; `_detect_and_break_cycles` reachable from the batch path; checkpoint-v4 writable cross-process; **identify the cross-lane concurrency flag**) | SIMPLE | 0 | FR-8; R1 |
| t-rollback | Cross-batch gate-failure disposition: **quarantine** partial artifacts; resume re-enters cleanly; FR-10 reads only completed batches | MODERATE | 1 | FR-11 |
| t-partitioner | `BatchPartitioner`: dependency-closed + file-cohesive batches via `_topological_sort`+`compute_lanes`+manifest; deterministic; invariant tests | COMPLEX | 1 | FR-1,2,8 |
| t-emit-partition | Fill `plan_ingestion_emitter.py:976` to emit partition metadata (ordering only; assert no parallel-exec flip) | MODERATE | 1 | FR-1; R1 |
| t-context-inherit | Inject prior-batch artifacts (manifest-scoped) into next batch's design context | COMPLEX | 2 | NFR-4 (+ new FR) |
| t-tests | Partition invariants (closure/cohesion/determinism), ordering, resume, **single-run no-regression**, context-coherence regression | MODERATE | 0-2 | NFR-1,2 |

Suggested build order = increment order (0 → 1 → 2), each shippable and verifiable alone.

---

## 8. Risks

- **R1 — Accidentally re-enabling parallel.** Emitting `wave_metadata`/partition data could
  feed the dormant cross-lane parallel path. **Mitigation (concrete + located — R1-S3):**
  (a) the partition emitter writes the **ordering-only** field and **must not** populate the
  cross-lane concurrency flag — identify that exact seed field in `t-reuse-verify` and assert
  it stays unset/None at `:976`; (b) the orchestrator loop holds a **single-in-flight**
  invariant (never two `run-prime-contractor` processes alive at once). Unit test on the
  emitter + integration test on the loop.
- **R2 — Context bloat.** Injecting full prior-batch outputs can blow the design token budget
  (`TOTAL_SPEC_BUDGET_TOKENS`). **Mitigation:** inject only manifest-contested / depended-on
  files; iterate.
- **R3 — Wrong partition.** A dependent task placed too early breaks closure. **Mitigation:**
  dependency-closed invariant + `_detect_and_break_cycles` + tests before each batch.
- **R4 — Scope creep into parallel.** **Mitigation:** NFR-1 no-regression + parallel
  explicitly deferred (Increment 3 default-off).

---

## 9. Discoveries (feed REQUIREMENTS §0)

| v0.1 assumption | Planning discovery | Impact |
|-----------------|--------------------|--------|
| Reuse `compute_waves()` (Kahn) as partitioner | **No `compute_waves()` exists**; `wave_index` is seed-static; real primitives are `_topological_sort()` + `compute_lanes()` (union-find) | FR-8/OQ-2 corrected to those primitives |
| Parallel failed on scheduling/ordering | It failed on **design-time context isolation** (incompatible designs on shared files; 300-char summaries) | OQ-3 resolved; reframes the whole risk |
| Sequential loop + gate is sufficient | Sequential does **not** auto-fix context isolation at batch seams | **New FR + Increment 2**: inter-batch context inheritance |
| Batches keyed on "wave/phase/milestone" | Best key = **dependency-closed + file-cohesive** (lanes + shared-file manifest) | FR-1/FR-2 refined; new file-cohesion requirement |
| `--task-filter` revalidates deps | It does **not** recompute wave/lane; inherits from seed | Partitioner must validate closure itself |
| Resume needs new machinery | Checkpoint **v4** already carries wave/lane state | FR-5 reuses it |
| `wave_metadata` is the only orphaned piece | Shared-file **manifest + critical-path** are also computed-but-unused | Reuse them for partitioning + context scoping |
| Populating `wave_metadata` is safe | It could feed the dormant parallel path | OQ-7 → hard Risk R1 (ordering-only; assert serial) |

---

*Plan 1.0 — paired with REQUIREMENTS v0.2. Implementation begins only after requirements
are confirmed and optional Convergent Review is done.*

*Plan 1.1 — Convergent Review R1 applied (8 S-suggestions, all accepted): reuse-verification
spike (`t-reuse-verify`), cohesion-vs-closure merge rule, concrete Risk-R1 guard, sharpened
Increment-0 seam caveat, cross-batch rollback (`t-rollback`), partition pinning,
observability sink, operator-override interface. Dispositions in Appendix A. Paired with
REQUIREMENTS v0.3.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-S1 | Reuse-verification spike (pin §1 primitives at anchors) | R1 | New → `t-reuse-verify` | 2026-05-29 |
| R1-S2 | Cohesion-vs-closure merge rule + max size + deterministic tie-break | R1 | §5 + `t-partitioner` | 2026-05-29 |
| R1-S3 | Concrete + located Risk-R1 guard (emitter flag + single-in-flight) | R1 | §8 R1 + `t-emit-partition` | 2026-05-29 |
| R1-S4 | Strengthen Increment-0 seam caveat + guardrail | R1 | §6 Increment 0 | 2026-05-29 |
| R1-S5 | Cross-batch rollback (quarantine; completed-only inheritance) | R1 | §5 + `t-rollback` (FR-11) | 2026-05-29 |
| R1-S6 | Partition pinning (seed hash, fail-loud) | R1 | §5 + `t-resume-ledger` (FR-12) | 2026-05-29 |
| R1-S7 | Concrete observability sink (checkpoint-v4 / OTel) | R1 | §5 + `t-resume-ledger` | 2026-05-29 |
| R1-S8 | Operator-override interface + closure validation | R1 | §5 | 2026-05-29 |
| R2-S2 | Atomic lockfile for single-in-flight | R2 | Applied (modified) → `t-orchestrator-loop`: use `flock(LOCK_EX\|LOCK_NB)` (kernel crash-recovery; NFSv4-safe) not `O_EXCL`. Lock at `<pipeline-output>/<plan-id>/.batch-orchestrator.lock`; second invocation fails fast `LockHeldError`. | 2026-05-31 |
| R2-S4 | Provenance enrichment writer | R2 | Applied (modified) → `t-batch-record-writer`: writer targets `BatchLedger`/`batch-ledger.json` (NOT checkpoint-v4); reduced fields per R2-F2. | 2026-05-31 |
| R3-S1 | Rewrite §1 row 6 — checkpoint-v4 reuse claim is phantom | R3 | Applied → §1/§5 corrected; v4 is functionally v2 (feature-serial fields only). Cross-batch state uses `BatchLedger`. | 2026-05-31 |
| R3-S2 | Fresh `batch_record_v1.json` artifact | R3 | Applied → satisfied by existing `BatchLedger` (`batch_postmortem.py`) + cap-dev-pipe wiring. One writer, atomic save, round-trip-testable. | 2026-05-31 |
| R3-S3 | Rename emitter seam `wave_metadata` → `batch_metadata` | R3 | Applied → `t-batch-partitioner` (Increment 1): keep `wave_metadata=None` at `plan_ingestion_emitter.py:983`, add `batch_metadata`. | 2026-05-31 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R2-S1 | `t-checkpoint-wire-audit` markdown matrix | R2 | Shape rejected (matrix decays on field add). Concern kept structurally: folded into `t-baseline-characterization` as a `WorkflowCheckpoint` round-trip test that fails in CI on schema drift. | 2026-05-31 |
| R2-S3 | `t-design-failure-gate` (FR-13 impl) | R2 | Consequence of R2-F1 rejection — within-run resume-cache lesson is shape-incompatible with the cross-batch seam; subsumed by the gate's zero-files-written post-check. | 2026-05-31 |
| R2-S5 | Typed artifact-consumption manifest task | R2 | Consequence of R2-F3 rejection — premature for a 2-type universe; deferred to Increment 3. | 2026-05-31 |
| R2-S6 | Batch-index-tiered gate | R2 | Consequence of R2-F4 rejection — project-state detection at the gate is the correct discriminator, not partition position. | 2026-05-31 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-7-1m — 2026-05-29

- **Reviewer**: claude-opus-4-7-1m
- **Date**: 2026-05-29 20:10:00 UTC
- **Scope**: Architectural review of sequential plan-batch orchestration — reuse-claim soundness, the R1 parallel-reactivation guard, FR-2 invariant edge cases, Increment-0 shippability under the seam caveat, and MVP gaps (cross-batch rollback, partition determinism/recompute, observability, cost accounting).

**Executive summary** (top risks / opportunities / blocking gaps):

- The §1 reuse table is the design's foundation but the plan **assumes** primitive behavior at specific `file:line` anchors without an explicit verification task — if any anchor drifted or behaves differently than stated, multiple FRs collapse.
- §5 reuses `compute_lanes()` (which already folds `depends_on` into its union-find) for **file cohesion** while §1 reuses `_topological_sort()` for **ordering** — the interaction (a lane that spans dependency layers) is not reconciled and can force a single mega-batch (defeats NFR-3).
- Risk R1's guard ("assert no two tasks generate concurrently") is the right idea but **not concretely located** — it needs a named assertion at the partition-emit and orchestrator-loop boundaries, not just a behavioral test.
- Increment 0 ships *without* FR-10 by relying on "batch *N*'s code on disk for *N+1*'s IMPLEMENT-time edits" — but DESIGN still runs first with 300-char summaries, so Increment 0 can emit an *incompatible design* before IMPLEMENT ever sees the on-disk code. The seam caveat may be understated.
- No plan step covers **cross-batch rollback** when a gate fails after partial generation; FR-10 could then inherit half-written artifacts.
- No plan step covers **partition recompute / pinning** if the seed changes between batches, though FR-5 resume depends on partition stability.
- Observability/provenance (FR-7) has no concrete sink named (OTel? checkpoint-v4 ledger?) — a low-effort, high-value extension given checkpoint-v4 already persists state.

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Validation | high | Add an explicit **reuse-verification task** (or a pre-Increment-0 spike) that asserts each §1 primitive behaves as claimed at its anchor: `_topological_sort` falls back to input order on cycle; `compute_lanes` unions on `target_files` **and** `depends_on`; `_detect_and_break_cycles` is reachable from the partitioner path (it is noted "feature-serial mode only"); checkpoint-v4 fields are writable cross-process. | The entire plan rests on the §1 `file:line` table; the plan even self-corrects one brief assumption (`compute_waves` doesn't exist), proving anchors can be wrong. `_detect_and_break_cycles` being "feature-serial mode only" is an unverified assumption that FR-2 closure validation depends on. | §7 Task decomposition, new `t-reuse-verify` task (Increment 0) | Characterization tests pinning each primitive's documented behavior at its anchor; CI fails if a primitive moves or changes semantics. |
| R1-S2 | Architecture | high | Reconcile the **cohesion-vs-ordering interaction** in §5/§7: specify that `compute_lanes()` components are merged into the smallest dependency-closed batch that contains the whole lane, with a documented **max batch size** (or explicit "unbounded by design" with NFR-3 trade-off noted). State the tie-break order so partitioning is deterministic (NFR-2). | §1 reuses `_topological_sort` for ordering and §5 reuses `compute_lanes` for cohesion, but a lane that links a layer-1 and a layer-4 task forces the batch to absorb the intervening chain — potentially collapsing the plan into one batch and defeating reviewability (NFR-3). No rule is given. | §5 `BatchPartitioner` bullet; mirror in §7 `t-partitioner` | Test: lane spanning distant dependency layers → assert documented merge/cap behavior and deterministic batch IDs across two runs. |
| R1-S3 | Security | high | Make Risk R1's guard **concrete and located**: name the assertion site(s) — (a) the partition emitter must write an ordering-only field and **must not** populate the cross-lane concurrency flag (assert the dormant flag stays false/None), and (b) the orchestrator loop must hold a single in-flight invariant. Specify the exact field/flag name from the seed schema that gates parallelism. | R1 currently says "assert execution remains serial … explicit test that no two tasks generate concurrently" but gives no locus or field name; an emitter could correctly emit ordering metadata yet still flip the concurrency-enabling field at `:976`. The guard must target the specific dormant flag. | §8 Risk R1 mitigation; §7 `t-emit-partition` | Unit test on the emitter asserting the concurrency flag is unset; integration test asserting the orchestrator never has two `run-prime-contractor` processes alive at once. |
| R1-S4 | Risks | high | Strengthen the **Increment 0 seam caveat**: state that Increment 0's DESIGN phase for batch *N+1* still runs on 300-char summaries *before* IMPLEMENT touches on-disk code, so Increment 0 can emit an incompatible *design* even though prior code is on disk. Add a guardrail (restrict Increment-0 cross-seam tasks to edit/IMPLEMENT-only, or require the operator to keep file-coupled tasks in one batch) and label residual risk. | §6 Increment 0 claims safety because batch *N*'s code is "on disk for *N+1*'s IMPLEMENT-time edits," but the DESIGN phase precedes IMPLEMENT and is exactly where the parallel effort failed; the "shippable/safe" claim may be overstated without a design-phase guardrail. | §6 Increment 0; §4 mitigations | Test: two batches sharing a file run under Increment 0; assert either the operator-cohesion guardrail prevents the split or the residual incompatible-design risk is surfaced (not silent). |
| R1-S5 | Risks | high | Add a **cross-batch failure/rollback** component and task: define on-gate-failure disposition of batch *k*'s partial artifacts (quarantine vs revert vs leave) and ensure FR-10 inheritance reads only **completed** batch outputs, never a failed batch's partial files. | §6/§7 have a validation gate and resume ledger but no statement of what happens to half-generated files when a gate fails; those poisoned artifacts would later be inherited by §5's inter-batch context injection, re-introducing incompatible context. | §5 (new component) + §7 (`t-orchestrator` or new `t-rollback`) | Test: fail batch *k*'s gate mid-generation; assert resume re-enters *k* cleanly and FR-10 injects only completed-batch artifacts. |
| R1-S6 | Data | medium | Add **partition pinning / recompute policy**: persist the computed partition (with a seed hash) in the resume ledger; on resume, reuse the pinned partition and **fail loudly** if the seed hash changed, rather than silently re-partitioning. | §6/§7 reuse checkpoint-v4 for resume and NFR-2 requires determinism, but nothing pins the partition — an operator editing the plan between batches could re-split completed batches and corrupt the resume ledger. | §5 `BatchPartitioner` / §7 `t-resume-ledger` | Test: change the seed between batches; assert resume reuses the pinned partition or aborts with a hash-mismatch error. |
| R1-S7 | Ops | medium | Name a concrete **observability sink** for FR-7 progress/provenance and FR-6 cost: since checkpoint-v4 already persists wave/lane state cross-process, extend its ledger (or emit OTel spans per batch) with per-batch task IDs, status, cost, and gate result. Low-effort given the ledger already exists. | §7 `t-resume-ledger` already writes cross-batch state; capturing provenance/cost there is ~marginal work (Lens 1: capability 80% built) and makes FR-6/FR-7 acceptance-testable instead of aspirational. | §5 components / §7 `t-resume-ledger` | Inspect the ledger/OTel after a multi-batch run; assert per-batch cost, status, task IDs, and gate result are present and queryable. |
| R1-S8 | Interfaces | medium | Specify the **operator-override partition interface** (Increment 1 "operator override allowed") and the **task-ID hand-off contract** to `--task-filter`: format of operator-supplied batches, validation that override batches still satisfy FR-2 closure (or an explicit "operator assumes responsibility" bypass), and how batch task IDs are serialized into `--task-filter`. | §5/§6 mention operator override and §7 t-orchestrator passes IDs to `--task-filter`, but the override's relationship to the closure invariant is undefined — an operator override could violate FR-2 with no check, silently re-creating wrong-partition Risk R3. | §5 partition emitter / §6 Increment 1 | Test: operator override that violates dependency closure → assert it is either rejected or explicitly flagged as unchecked. |

(No prior rounds exist; no endorsements/disagreements applicable for R1.)

_Triaged 2026-05-29: all 8 R1-S items **accepted** → Appendix A. No rejections._

#### Review Round R2 — claude-opus-4-7-1m (lessons-learned synthesis) — 2026-05-30

- **Reviewer**: claude-opus-4-7-1m (lessons-learned synthesis pass, not an independent architectural review — sourced from `/Users/neilyashinsky/Documents/craft/Lessons_Learned/sdk/lessons/{10-workflow-system,11-multi-agent-workflows,13-cross-system-pipeline}.md`).
- **Date**: 2026-05-30
- **Scope**: Plan-level improvements (tasks, risks, components) derived from validated SDK lessons that the v1.1 plan does not yet absorb. Requirements-level companions are in the requirements R2 (F-suggestions). Two pure plan-level items (R2-S1 propagation-wiring audit, R2-S2 atomic lockfile) have no requirements companion; the other four (R2-S3..R2-S6) are implementation tasks for the corresponding R2-F suggestions.

**Executive summary**

- **Checkpoint-v4 wiring is the SDK's most-bitten anti-pattern.** `t-resume-ledger` (R1-S6/R1-S7) adds batch-orchestration fields to checkpoint-v4 state, but the plan does not enumerate the reader/writer sites or assert round-trip coverage. SDK Leg 10 #35 documents that propagation fields require wiring at 12+ points; missing one silently drops data.
- **R1's single-in-flight invariant is TOCTOU-shaped.** R1-S3 specifies "the orchestrator loop holds a single-in-flight invariant" verified by an integration test — a behavioral assertion. SDK Leg 11 #67-69 (TOCTOU race in sequential filesystem checks) is the direct anti-pattern: any check-then-spawn pattern races against a simultaneous invocation. An atomic lockfile (`O_EXCL`) makes the invariant structural.
- **Four requirements companions need plan tasks.** R2-F1 (design-failure cascade gate), R2-F2 (provenance enrichment), R2-F3 (artifact-consumption manifest), R2-F4 (tiered preflight) each need a plan-side implementation task. Without them the FR additions land as documentation only.
- **§5 components implicitly conflate ledger state and inter-batch context handoff** (SDK Leg 11 #34: orchestrator checkpoints don't persist shared context; use separate handoff file). The resume ledger carries lifecycle state; the FR-10 inheritance reads code/design artifacts directly from disk. The plan should state this separation explicitly so a future contributor doesn't try to stuff FR-10 payload into the ledger.

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Ops | high | Add new task **`t-checkpoint-wire-audit`** (SIMPLE, Increment 0): enumerate every reader/writer of checkpoint-v4 state across the SDK + cap-dev-pipe surface (`artisan_contractor.py:532-540` writers, plus any downstream readers in `run-prime-contractor.sh`, plan-ingestion, prime-contractor); produce `docs/design/notes/CHECKPOINT_V4_WIRE_AUDIT.md` with a tick-box matrix of {site → field}. Block Increment-0 merge until the audit matrix shows zero missing sites for the new batch-orchestration fields (`batch_id`, `batch_sequence`, `upstream_batch_status`, plus the R2-F2 provenance fields if accepted). | SDK Leg 10 #35 (Two-Site Registration for Pipeline Context Keys — Checkpoint Persistence Gap, v7.55.0 changelog): "propagation field to the pipeline requires wiring 12+ points; missing one silently drops data." This is the SDK's most-bitten anti-pattern. `t-resume-ledger` (R1-S6/R1-S7) adds new fields but does not enumerate the wire sites. The cheapest place to prevent the silent-drop failure mode is a one-shot audit artifact committed alongside Increment 0. | §7 Task decomposition, new row in Increment 0 (adjacent to `t-reuse-verify` which similarly is a one-shot characterization-test gate). Reference in §5 `BatchOrchestrator` / `t-resume-ledger` component descriptions. | Audit artifact is the test: CI lints presence + completeness (every new field has every site ticked). Companion property-based test: write checkpoint-v4 state with all new fields populated; read it from each consumer site; assert round-trip fidelity per field. |
| R2-S2 | Risks | high | Harden Risk R1's single-in-flight invariant with an **atomic lockfile**. The orchestrator acquires a lock at a deterministic path (e.g. `<pipeline-output>/<plan-id>/.batch-orchestrator.lock`) using `open(O_CREAT \| O_EXCL)` semantics (or `flock(LOCK_EX \| LOCK_NB)` — pick one, document the choice); lock content is `{pid, batch_id, started_at}`; release on batch completion or orchestrator exit (`atexit` hook + signal handlers for SIGINT/SIGTERM). Stale-lock detection: if the lock exists but the recorded PID is not alive (e.g. crash), the second orchestrator may reclaim the lock with an audit log entry. A second simultaneous invocation against the same plan directory MUST fail fast with `LockHeldError` reporting the holder's PID + batch ID. Replaces the v1.1 R1 mitigation (b) ("orchestrator loop holds a single-in-flight invariant"), which is behavioral and TOCTOU-shaped. | SDK Leg 11 #67-69 (TOCTOU race in sequential filesystem checks) is the canonical anti-pattern: any "check no other process alive, then spawn ours" sequence races against a simultaneous "check, spawn" by another invocation — both pass the check, both spawn. The current R1-S3 mitigation describes the *desired property* but not the *mechanism*; an integration test can demonstrate the property holds under normal conditions but cannot prove it under adversarial timing. An atomic lockfile makes the invariant structural (cannot be violated by two simultaneous invocations) rather than behavioral. | §8 Risk R1, replace mitigation (b) with the lockfile mechanism (keep (a) as-is). §7 `t-orchestrator` description: add "acquire/release atomic lockfile" responsibility. Optional new task `t-orchestrator-lock` (SIMPLE) if separation aids review. | (a) **Race test.** Spawn two orchestrators simultaneously against the same plan directory (via `&` background + `wait`); assert the second exits with `LockHeldError` containing the first's PID + batch ID. (b) **Crash test.** Kill the first orchestrator mid-batch (SIGKILL — bypasses atexit); start a second orchestrator; assert it detects the stale lock (PID-not-alive) and either recovers (audited) or refuses (documented mode). (c) **Normal-exit test.** Orchestrator completes; assert lock file is removed. |
| R2-S3 | Validation | high | Add new task **`t-design-failure-gate`** (MODERATE, Increment 0) implementing R2-F1's FR-13: at batch N+1 pre-start, the orchestrator reads batch N's design-phase artifact list from the resume ledger / FR-7 provenance, checks each expected artifact exists and is marked successful, and halts loudly via `DesignFailureCascade` exception if any are missing or marked failed. The gate runs **before** any `run-prime-contractor` invocation for batch N+1 — it is a pre-spawn check, not an in-batch hook. Wires into the BatchOrchestrator loop alongside the existing FR-4 post-batch gate; the two gates bracket the batch (R2-S3 pre, FR-4 post). | Implementation of R2-F1. SDK Leg 13 #46-47 shows that without this gate, design failure silently cascades into stale IMPLEMENT. Pre-spawn placement matters: a per-batch post-IMPLEMENT gate (FR-4) is too late — batch N+1 has already executed IMPLEMENT against the missing design and produced poisoned artifacts that FR-10 would later inherit. R2-F1 + R2-S3 must land together; the FR without the task is documentation. | §7 Task decomposition, new row in Increment 0 (positioned **before** `t-orchestrator` per dependency — orchestrator wires the gate). §5 BatchOrchestrator component description: add pre-spawn gate responsibility. | Synthetic ledger entry marking batch N's design phase as failed; invoke orchestrator with batch N+1 as the starting batch. Assert: (a) no `run-prime-contractor` spawn; (b) `DesignFailureCascade` exception with batch N + missing-artifact name in the message; (c) resume re-enters batch N (not N+1); (d) when batch N is re-run successfully, batch N+1 proceeds normally. |
| R2-S4 | Ops | medium | Extend **`t-resume-ledger`** (Increment 0) to write the R2-F2 enriched FR-7 fields: `config_hash`, `seed_fingerprint`, `output_artifact_fingerprints: {path: sha256}`, `quality_summary: {confidence_avg, override_count, gate_failures_suppressed}`. Specify the JSON schema **up-front** in the task description so the ledger shape is the contract; downstream postmortem classifiers (parallel to Forward Manifest Fix 3) consume against the stable shape and do not require ledger churn to land. | Implementation of R2-F2. SDK Leg 13 #11 (`run-provenance.json` artifact for CLI lineage) specifies these as the canonical shape. The ledger writer already exists per R1-S7; this is incremental extension, not new infrastructure. Schema-now (per R1-S6 pattern from the Forward Manifest plan) prevents dead-code drift if the postmortem classifier ships after this. | §7 `t-resume-ledger` row description (extend with the field list + schema reference). §5 components: add "provenance schema" sub-bullet to the observability sink description. R2-S1 wire-audit picks these fields up automatically. | Multi-batch run (3 batches); inspect ledger JSON; assert every new field present per batch + well-formed. Mutate one file in batch-N's output between batches; assert batch N+1's pre-start read detects the fingerprint drift loudly (paired with R2-F2 / FR-12 symmetry). |
| R2-S5 | Architecture | high | Extend **`t-context-inherit`** (Increment 2, COMPLEX) with the R2-F3 typed artifact-consumption manifest. Define `ArtifactType` as an **extensible** registry (per SDK Leg 13 #19-20: NOT a static enum with parallel dicts), keyed by string with a sibling metadata dict per type (e.g. `{type, content_carrier, format, fingerprint_strategy}`). Per-batch produces/consumes lists are declared in the partition output (Increment 1's `BatchPartitioner` emits them); validated at the seam in Increment 2 before context injection. Consumer-without-producer fails loudly via `MissingConsumedArtifact`; producer-without-consumer is surfaced as advisory in R2-F2 provenance (`orphan_outputs: [paths]`). | Implementation of R2-F3. SDK Leg 13 #19-20 directs explicitly against a static enum (parallel dicts create silent gaps); the extensible-registry pattern matches the FR-7 framework-conventions registry pattern in the Forward Manifest work. SDK Leg 11 #59-60 (Pipeline Phase Artifact Disconnect — design docs generated but not consumed by implementation) is the failure mode this task prevents at the batch seam. | §7 `t-context-inherit` row description (extend); §5 components: add "ArtifactType registry" sub-bullet. The Increment-1 `BatchPartitioner` task picks up the produces/consumes annotation responsibility (small ripple). | (a) Producer/consumer mismatch (consumer expects `design_docs`; producer emits only `code_files`) → seam validation fails with `MissingConsumedArtifact`. (b) Orphaned producer (batch N emits `interface_contracts`; no later batch declares consumption) → advisory in provenance, not blocking. (c) Round-trip: the manifest is written to FR-7 provenance per batch and is queryable post-run. (d) Schema extensibility: add a new `ArtifactType` at test time; assert validation works without code changes to the seam validator. |
| R2-S6 | Validation | medium | Extend **`t-orchestrator`** (Increment 0) with batch-index-aware gate selection per R2-F4. The orchestrator inspects its current batch index in the partition and selects the gate tier: **index == 0 → advisory** (WARN on most checks; FAIL only on conditions preventing code generation entirely); **index > 0 → blocking** (regression-protective). Tier is derived from partition state, not a per-batch config flag. The FR-4 operator override path applies on top of either tier and is recorded per existing FR-4 + R2-F2 audit. | Implementation of R2-F4. SDK Leg 13 #18 (Advisory-by-Default Preflight for Greenfield Code Generation): preflight rules designed for established codebases produce false positives in greenfield. Wiring the tier into `t-orchestrator` (already extended for FR-4 default-gate) is the natural seam. | §7 `t-orchestrator` row description (extend with batch-index-aware tier selection). §5 BatchOrchestrator component: add "tier selection" bullet. | (a) BATCH-1 in an empty project directory with default `npm test` gate → WARN logged, batch 2 proceeds. (b) BATCH-2 with an introduced regression (failing test added in BATCH-1) → blocking, batch 3 does not start. (c) Operator override on a BATCH-2 blocking failure → recorded per FR-4 + R2-F2 quality summary. (d) BATCH-1 with truly fatal condition (unparseable seed) → blocking even in advisory tier (the tier governs default severity, not absolute fatalness). |

(Lessons-learned synthesis round; no endorsements/disagreements section — R2's suggestions derive from external knowledge base, not from re-reading R1's suggestions.)

_Status: **TRIAGED 2026-05-31 → see Appendix A/B.** R2-S2 applied (modified to `flock`); R2-S4 applied (modified, targets `BatchLedger`); R2-S1 folded into `t-baseline-characterization` (roundtrip test, not a markdown matrix); R2-S3, R2-S5, R2-S6 rejected (paired with their F-companions)._

#### Review Round R3 — claude-opus-4-7-1m — 2026-05-30 — Independent pressure-test + complexity audit

- **Reviewer**: claude-opus-4-7-1m
- **Date**: 2026-05-30
- **Scope**: Independent pressure-test of R2 lessons-derived suggestions PLUS cumulative complexity audit (Brooks essential-vs-accidental). Behavioral verification of the plan's §1 reuse table against the actual SDK code (informed by the Forward Manifest phantom-API precedent). The long-form audit lives in the **requirements R3** appendix; this plan R3 focuses on §1, §5, §7, §8 deltas and task-level impact. Cross-reference: see `PLAN_BATCH_ORCHESTRATION_REQUIREMENTS.md` Appendix C R3 for full Part 1 (R2 pressure-test) and Part 4 (essential MVP distillation).

### Part 1 — R2 plan-side verdicts (matches requirements R3 Part 1)

- **R2-S1 (markdown wire-audit matrix):** REJECT shape, ACCEPT concern. Replace with `t-baseline-characterization` (one test file, CI-enforced round-trip on `WorkflowCheckpoint` + anchor pins). The matrix decays the moment a field is added without an update. A roundtrip test fails loudly the same moment — and would have caught the Part 2 phantom finding before anyone wrote this plan.
- **R2-S2 (O_EXCL lockfile):** ACCEPT-WITH-MODIFICATIONS. Use `flock(LOCK_EX | LOCK_NB)`, not `O_EXCL`. The cited lesson (SDK Leg 11 #68) is about single-process `exists()+stat()` TOCTOU — its prescription is `try: stat() except OSError`, not a cross-process lockfile. The mechanism R2-S2 proposes is right for the actual problem, but the citation is borrowed legitimacy. `flock` provides automatic crash-recovery via kernel cleanup — drops the PID-alive check, atexit dance, and audit-on-reclaim branch entirely. NFS unreliability of `O_EXCL` is real; `flock` is NFSv4-safe on the client side.
- **R2-S3 (`t-design-failure-gate`):** REJECT. SDK Leg 13 #46-47 is about resume-cache invalidation *within one prime-contractor run* — shape-incompatible with the cross-batch seam where each batch is a separate process and starts from disk. Replace with one line in FR-4: "default gate FAILS if batch N's IMPLEMENT wrote zero files for any task whose seed declared `target_files`." Or, if R2-S5/F3 typed manifest is accepted, R2-S3 is redundant by construction. The most economical move is to DELETE R2-F1/R2-S3 entirely and rely on FR-4's existing post-batch gate (a crashed DESIGN cannot produce passing IMPLEMENT, so FR-4 already blocks the seam).
- **R2-S4 (provenance enrichment writer):** ACCEPT-WITH-MODIFICATIONS. Keep `config_hash` + `seed_fingerprint` (cheap, finite, symmetric to FR-12). Scope `output_artifact_fingerprints` to declared `target_files` only (cap N at ~10/batch rather than O(files-written) = potentially hundreds). Drop `quality_summary.confidence_avg` — depends on a SDK Leg 13 #22 pipeline that is not wired into this capability and would land as `None`. Collapse `gate_failures_suppressed` into `override_count` (every suppressed gate failure IS an override). And — most important — the WRITER must target the new `batch_record_v1.json` artifact (R3-S2 below), NOT checkpoint-v4 (which is phantom — see Part 2).
- **R2-S5 (typed artifact-consumption manifest in `t-context-inherit`):** REJECT for MVP. FR-10 already gives the trigger (`target_files` ∩ prior ≠ ∅) and acceptance (on-disk content, blocking on miss). The typed manifest adds producer/consumer ceremony + registry extensibility for a universe of artifact types that for the MVP is exactly two (code files, design docs). Premature flexibility. The cited SDK Leg 13 #19-20 is about *intra-pipeline* artifact registries (within one run, many handler kinds) — different problem space. Replace with one bullet in FR-10: inheritance reads `code_files` (`target_files` on disk) + `design_docs` (`<output>/design/{task_id}.md`); other kinds deferred. Defer the typed manifest to Increment 3 if intra-batch parallelism is ever pursued.
- **R2-S6 (batch-index-tiered gate in `t-orchestrator`):** REJECT. Batch-index is a proxy for "does test infrastructure exist?" The proxy is wrong in both directions: BATCH-1 may land in an existing project (advisory mode suppresses real regressions); BATCH-2 may not yet have built test infra (blocking mode false-positives on absent tooling). Replace with project-state detection at the gate: `package.json` → `npm test` blocking; `pyproject.toml` → `pytest` blocking; neither → preflight WARN with a "no test infrastructure detected" diagnostic. One rule, no tier vocabulary, reads observable state instead of partition position.

### Part 2 — Phantom-API verification of §1 reuse table

Behavioral check, row by row. Single-line verdicts; full evidence in requirements R3 Part 2.

- **`_topological_sort()` `shared.py:243-293`** — VERIFIED. DFS + tri-color colors at 252-274; cycle fallback to `list(tasks)` at 291.
- **`wave_index` `shared.py:64-65`** — VERIFIED seed-static. Dataclass `Optional[int] = None`; CCD-400 at `design.py:1167-1173` only warns when None, never assigns.
- **`compute_lanes()` `artisan_contractor.py:970-1026`** — VERIFIED. Union-find on `target_files` (1000-1010) + `depends_on` (1013-1016).
- **Absence of `compute_waves()`** — VERIFIED PHANTOM. `grep -rn` over `src/` returns zero matches; plan's correction of the brief is sound. **HOWEVER:** `docs/design-princples/CONTEXT_CORRECTNESS_BY_DESIGN.md:47` itself contains the same phantom claim with anchor `~861` — the postmortem doc that NFR-4 / Increment-2 rest on is internally inconsistent with the plan's correction. Future readers citing the postmortem will reintroduce the bug.
- **Checkpoint-v4 fields `wave_assignments`, `completed_waves`, `current_wave`, `wave_resume_count` at `artisan_contractor.py:532-540`** — **PHANTOM / DORMANT (Forward-Manifest-class severity, HARD BLOCKER).** Docstring at 526-534 claims v4 adds these fields. `WorkflowCheckpoint` dataclass at 521-550 declares none of them. Migration code at 783-786 calls `data.setdefault(...)` to populate them in the load-time dict; validation at 792-829 mutates them; **line 833-842 filters the dict against `{f.name for f in fields(WorkflowCheckpoint)}`**, stripping the wave_* fields it just added, before `WorkflowCheckpoint(**data)` at 849. The save path at 2424-2454 passes only the 13 declared dataclass fields; `asdict()` at 715 serializes only those. **The wave_* fields never reach disk.** This is a load-side phantom worse than the Forward Manifest `getattr(..., None)` precedent — the dead-code migration appears to populate fields that the very loader silently filters out. **Blocks: FR-5, `t-resume-ledger`, R1-S6 (partition pinning), R1-S7 (observability sink), R2-S1 (wire-audit), R2-S4 (provenance enrichment).** The plan's "REUSE as-is" claim for checkpoint-v4 is wrong as currently shipped. Repair before scoping any ledger-touching increment.
- **`_detect_and_break_cycles()` `queue.py:413-482` — "feature-serial mode only"** — DRIFTED. The function is called unconditionally at `queue.py:359` from `add_features_from_seed()` — no mode gate. The parenthetical in §1 row 3 and in R1-S1's task description is wrong; cycle detection runs every time tasks are loaded into the queue. Implication: FR-2's closure-validation requirement is partially redundant with the existing queue-load step.
- **`build_shared_file_manifest`/`compute_lane_to_file_mapping`/`compute_critical_path_tasks` at `design_support.py:449-522` — "computed but UNUSED"** — DRIFTED. All three are called inside `phases/design.py` at 1145, 1162, 1178; results flow into `context["shared_file_manifest"]`, `context["lane_to_file_mapping"]`, and feed `_compute_ccd_task_metadata` at 1389, 1765, 2090, 2215. They are used. The plan's reuse claim ("invent nothing; reuse as the partitioning substrate") is **double-booking**: if `BatchPartitioner` calls them at plan-ingestion time and DESIGN calls them again per batch, the manifest is computed twice over different task sets. §1 row 4 must be rewritten and FR-8 must name an authoritative call site.
- **`plan_ingestion_emitter.py:976` — `wave_metadata=None` stub** — DRIFTED (line number). Actual stub is at line 983 inside a `ContextSeed(...)` constructor that begins at 969. The seam exists; the anchor is stale.
- **`run-prime-contractor.sh --task-filter`** — VERIFIED. Exists at line 392; threads to `scripts/run_prime_workflow.py:487`; applied via skip-set at 740-760 with no per-batch dependency revalidation. The plan's claim is accurate at this level. Caveat: `add_features_from_seed` still calls `_detect_and_break_cycles` over the WHOLE seed at queue-load time per the row above — cycle-breaking runs per `--task-filter` invocation, just not scoped to the filtered set.
- **`CONTEXT_CORRECTNESS_BY_DESIGN.md:43-211` (cited by §2)** — EXISTS at `docs/design-princples/` (note dir typo), supports the "design-time context isolation, not scheduling" claim — **but contains the `compute_waves()` phantom itself at line 47**. Tainted by internal drift.
- **`ARTISAN_RUN2_POSTMORTEM.md:92-130` (cited by §2)** — EXISTS at `.cap-dev-pipe/design/` not at `docs/design/`.

**Blocker call-out:** Halt scoping of FR-5 / `t-resume-ledger` / R1-S6 / R1-S7 / R2-S1 / R2-S4 until either (a) the wave_* fields are added to `WorkflowCheckpoint` (the documented intent) or (b) the cross-batch ledger uses a NEW artifact (R3-S2) that doesn't pretend to extend the broken v4 schema. The Forward Manifest precedent is repeating at a different load-bearing point.

### Part 3 — Plan-level accidental complexity (highest-leverage first)

*3a-P1 — Multiple-mechanism collapse: `BatchTransition`.* FR-4 (post-batch validation), FR-11 (post-batch rollback), FR-12 (pre-batch seed-hash), and R2-F1 (pre-batch design-artifact check) are four faces of one mechanism. Each carries its own diagnostic format, override semantics, and audit trail. Collapse §5 component and §7 task to one primitive: a `BatchTransition` gate runs N pre-checks and M post-checks at each boundary, with one diagnostic format, one override path, one audit record. Essential property: every boundary is gated. Incidental: four named mechanisms × four override paths × four diagnostic templates × four test sets.

*3a-P2 — Persistence-layer sprawl.* The plan's "extend checkpoint-v4" approach (FR-5, R1-S6, R1-S7) + provenance enrichment (R2-S4) + wire-audit (R2-S1) + per-batch audit (R2-F2 fields) compound to: multiple writers, multiple schemas, separate readers, separate round-trip stories. Collapse to one artifact: `batch_record_v1.json` per batch under `<output>/batches/<batch_id>/`. Single writer, single schema, single round-trip test. The Part-2 phantom finding makes this more urgent — DON'T extend the broken v4 schema; write a fresh artifact.

*3a-P3 — Pre-Increment-0 task sprawl.* `t-reuse-verify` (R1-S1) + `t-checkpoint-wire-audit` (R2-S1) + the implicit pre-step inside `t-design-failure-gate` (R2-S3) = three pre-0 tasks doing the same shape of work ("audit the SDK before we touch it"). Forward Manifest accumulated three pre-0 tasks and obsoleted one when the phantom-API was found. Pattern smell. Consolidate to one: `t-baseline-characterization` — one test file that (a) pins primitive behaviors at their anchors with one assert each, (b) round-trips `WorkflowCheckpoint` with every dataclass field set, (c) asserts the cycle-breaker call site is unconditional, (d) lints docs/design/*.md for `.py:NNN` citations that have no companion test. One artifact, one CI gate.

*3a-P4 — R1-S5 "quarantine" overstructure.* "Quarantine" implies a new state with its own lifecycle (entered, audited, eventually purged or restored). Essential property: FR-10 inheritance must not read a failed batch's half-written files. Simpler form: `batch_record_v1.json` has a `status: completed|failed|in_progress` field; FR-10 reads only from files associated with `completed` batch records. Half-written files stay on disk (operator can inspect / delete); no state machine.

*3a-P5 — Risk R1 mitigation is behavioral when it could be structural.* R1-S3 says "ordering-only field" + "single-in-flight invariant" — both are behavioral assertions verified by tests. Rename the emitter seam from `wave_metadata` to `batch_metadata` (see 3c below) — the parallel path literally reads from a different field. R1 is mitigated structurally; the test then asserts a property that holds by construction, not by discipline.

*3a-P6 — FR-10 trigger is over-specified for sequential execution.* The trigger "batch k+1's `target_files` ∩ prior-batches-produced ≠ ∅" exists to bound the inheritance scope. But every prior batch's files are ON DISK by sequential construction; there is no scenario where batch k+1 should NOT see them. Simplify: batch k+1's DESIGN context always includes prior batches' code-on-disk + design-docs-on-disk, scoped to the shared-file manifest. Eliminates the trigger evaluation logic and the edge-case branches for what counts as ∩.

### Part 3b — SDK code findings (ship inside this capability where noted)

| Finding | Location | Overcomplicated form | Simpler form | Ship inside |
|---|---|---|---|---|
| C1 — `WorkflowCheckpoint` wave_* migration is dead code | `artisan_contractor.py:783-829` | `setdefault` populates fields the loader strips at line 842; validation logic mutates fields that never reach the dataclass | Either ADD the fields to the dataclass (documented intent) or DELETE the migration + docstring lines 532-534 | Increment 0 (paired with `t-baseline-characterization`) |
| C2 — `lane_assignments=None` companion drift | `plan_ingestion_emitter.py:984` | Right next to `wave_metadata=None`; same dormant-field family; same R1 risk surface | Rename + null-fill per R3-S3 below | Increment 1 |
| C3 — `wave_resume_count` has no writers anywhere | `artisan_contractor.py:533` (docstring) | Docstring lists a field that grep finds nowhere else in `src/` | Delete from docstring | Increment 0 |
| C4 — Triple cycle-check redundancy | `queue.py:359` (load) + partitioner cycle-check (per R1-S1) + per-batch via `_detect_and_break_cycles` | FR-2's "partitioner validates closure itself" is third call site | Trust queue-load check; drop partitioner-level cycle check; document dependency | Increment 1 (cheap simplification of `t-partitioner`) |
| C5 — `compute_lanes` redundant computation | `artisan_contractor.py:988-1026` | If BatchPartitioner uses it AND DESIGN uses it again per batch, allocates parent dict twice on overlapping inputs | Cache by `tuple(sorted(task_ids))` if perf matters; else accept | Defer — perf cost is small |
| C6 — `docs/design-princples/` directory typo | dir name | Every reference inherits typo | Rename to `docs/design-principles/`; update references | Separate cleanup commit |
| C7 — `getattr(..., None)` audit | sdk-wide, esp `prime_contractor.py:3792` (`getattr(self, "_forward_manifest", None)`) | 25+ patterns sdk-wide; mostly defensive; the prior Forward Manifest bug was this shape | Audit each load-bearing plan claim that hinges on a `getattr(..., None)` lookup; verify the attribute is actually wired | Defer — needs separate effort |

### Part 3c — Vocabulary debt: concrete renames

| Inherited name | Source | Proposed batch-native name | Why |
|---|---|---|---|
| `wave_metadata` (seed field) | dormant parallel | `batch_metadata` (new seed field, alongside `wave_metadata=None`) | Eliminates R1 by construction — parallel path keeps reading `wave_metadata=None`, cannot activate |
| `wave_assignments` (ckpt) | dormant ckpt field | `batch_assignments` in `batch_record_v1.json` | Fresh artifact; no overlap with parallel state |
| `completed_waves` (ckpt) | dormant ckpt field | `completed_batches` | Same |
| `current_wave` (ckpt) | dormant ckpt field | `current_batch` | Same |
| `compute_lanes()` | used as cohesion primitive | KEEP — correctly named for what it does | No rename |
| `_topological_sort` | used as ordering primitive | KEEP — correctly named | No rename |
| `lane_assignments=None` (`plan_ingestion_emitter.py:984`) | dormant | Leave at None; do not populate from BatchPartitioner | Same R1 structural mitigation |

### Part 4 — Essential MVP distillation (mirrors requirements R3 Part 4)

After Brooks's cut, the minimum viable plan is **6 essential requirements** + **5 essential tasks**, replacing 12 FRs + 8 R1-Ss + 6 R2 items + 8 §7 tasks. Compression ratio: **6 essential vs 16 current FR-shaped items ≈ ~63% deletable.**

**Essential plan tasks (replaces §7):**

| Task | Subsumes | Complexity | Increment |
|---|---|---|---|
| `t-baseline-characterization` | `t-reuse-verify` (R1-S1) + `t-checkpoint-wire-audit` (R2-S1) + pre-step of `t-design-failure-gate` (R2-S3) + doc citation lint | SIMPLE | 0 (pre-everything) |
| `t-orchestrator-loop` | `t-orchestrator` (loop+gate+resume) + `t-orchestrator-lock` (R2-S2 flock) | MODERATE | 0 |
| `t-batch-record-writer` | `t-resume-ledger` + FR-7 sink + FR-12 hash + R2-S4 enrichment | MODERATE | 0 |
| `t-batch-transition-gate` | FR-4 post-check + FR-11 rollback + FR-12 pre-check + (R2-F1 deleted) | MODERATE | 1 |
| `t-batch-partitioner` | `t-partitioner` + `t-emit-partition` (with `batch_metadata` rename) | COMPLEX | 1 |
| `t-context-inherit` | FR-10 inheritance (without R2-F3 typed manifest) | COMPLEX | 2 |

**Dispositions for current items:**

- `t-orchestrator` → FOLD into t-orchestrator-loop (subsumes R2-S2 flock)
- `t-resume-ledger` → FOLD into t-batch-record-writer (new artifact, NOT extension of v4)
- `t-reuse-verify` → FOLD into t-baseline-characterization
- `t-rollback` → FOLD into t-batch-transition-gate (post-check failure is one path of the gate)
- `t-partitioner` + `t-emit-partition` → FOLD into t-batch-partitioner
- `t-tests` → DELETE (each essential task carries its own tests; no separate test task)
- R2-S1 → DELETE the matrix; FOLD into t-baseline-characterization
- R2-S2 → FOLD into t-orchestrator-loop (using flock not O_EXCL)
- R2-S3 → DELETE (consequence of R2-F1 delete)
- R2-S4 → FOLD into t-batch-record-writer (reduced field set)
- R2-S5 → DEFER to Increment 3 (typed manifest is for intra-batch parallelism)
- R2-S6 → DELETE; replace with project-state detection inside t-batch-transition-gate

**Risk-section dispositions:** R1 (parallel reactivation) → MITIGATED STRUCTURALLY by `batch_metadata` rename (3c); behavioral assertion becomes confirmation, not enforcement. R2 (context bloat) → KEEP. R3 (wrong partition) → KEEP. R4 (scope creep) → KEEP.

### Part 5 — New plan suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | Architecture | critical | Rewrite §1 row 6 (Resume state). The claim "checkpoint v4 (wave_assignments, completed_waves, current_wave) persists wave/lane execution state" is false: those fields are not on the `WorkflowCheckpoint` dataclass, are populated by `data.setdefault` in the migration, then immediately stripped by the `known_fields` filter at `artisan_contractor.py:842` before reaching the dataclass constructor, and never reach disk. Document that v4 is functionally identical to v2 (feature-serial fields only), and that any cross-batch state must use a NEW artifact (R3-S2 below), not an extension of v4. | Part-2 audit shows the dead-code migration is a Forward-Manifest-class phantom. FR-5, R1-S6, R1-S7, R2-S1, R2-S4 all rest on the false claim. Repair §1 before scoping any ledger-touching task. | §1 reuse table row 6; cross-reference fix in §5 components ("Reuse as-is"); add to §8 as Risk R5 "phantom reuse-claim". | A `test_checkpoint_field_set.py` test that asserts `{f.name for f in fields(WorkflowCheckpoint)}` equals the set documented in `§1`; fails on docstring drift. |
| R3-S2 | Data | critical | Introduce a new artifact `batch_record_v1.json` written per batch under `<output>/batches/<batch_id>/`. Schema: `{batch_id, batch_sequence, task_ids, seed_hash, config_hash, status: pending\|completed\|failed, started_at, ended_at, cost_usd, gate_result: pass\|fail\|overridden, override_record: {who, when, why} \| null, output_artifact_fingerprints: {path: sha256} scoped to declared target_files only}`. ONE writer (helper function in `t-batch-record-writer`); readers consume against the dataclass; round-trip CI test. Replaces FR-5 ledger extension, FR-7 sink, FR-12 pinning record, R1-S6/S7, R2-F2 schema, R2-S1 wire-audit, R2-S4 provenance enrichment. | The Part-2 phantom forces this — extending the broken v4 schema inherits the silent-drop bug. A fresh artifact has no carrying capacity for inherited bugs and uses batch-native vocabulary by construction. Compression: 5 §5 components / 4 FRs / 4 R2 items collapse into one artifact + one writer. | §5 components (replace "Observability sink (NEW — R1-S7)" + "Partition pinning (NEW — R1-S6)" + the implicit ledger extension); §7 new task `t-batch-record-writer`; §8 add Risk R5 "phantom reuse-claim" referencing R3-S1. | Property-based round-trip test on the schema dataclass; CI lint that no other code path writes to `<output>/batches/`. |
| R3-S3 | Security | high | Rename the partition emitter seam: at `plan_ingestion_emitter.py:983` keep `wave_metadata=None` and ADD `batch_metadata=<partition>` as a separate field. Plumb through `seeds/models.py`, `seeds/builder.py`, the `ContextSeed` dataclass, and `phases/design.py`. The dormant parallel path (which reads `wave_metadata`) keeps reading `None` and cannot activate. Risk R1 becomes structural rather than behavioral. | R1's current mitigation is "assert the cross-lane concurrency flag stays None" — behavioral. A separate field is structural: the parallel path literally can't read batch metadata because it doesn't know the field name. The cost is one new field + one plumbing pass. The R1-S3 integration test then asserts a property that holds by construction. | §5 components (rename "Partition emitter"); §7 new task `t-rename-batch-metadata-seam` in Increment 1; §8 Risk R1 mitigation collapses to "field-naming structural; R1-S3 single-in-flight assertion remains" | (a) Populate `batch_metadata`; assert `wave_metadata` remains `None`. (b) Grep all DESIGN-phase code paths to confirm none read `batch_metadata` as if it were `wave_metadata`. (c) Mutation test: rename `wave_metadata` → `wave_data` somewhere DESIGN reads it; assert tests fail (catches name-aliasing regressions). |

**Endorsements** (untriaged prior items I agree with):
- R1-S1 underlying intent (anchor pinning) — endorse, but the matrix decay concern means this should fold into `t-baseline-characterization` (R3 Part 4) rather than ship as a standalone reuse-verify task.
- R1-S2 (cohesion-vs-closure merge rule) — endorse as-is; max-batch-size + named error is the right shape.
- R1-S4 (Increment-0 seam caveat strengthening) — endorse; the seam IS understated.

**Disagreements** (untriaged prior items I would reject or substantially modify):
- R2-S3 (`t-design-failure-gate`) — REJECT as scoped. The lesson is misapplied (within-run resume cache ≠ cross-batch seam); the gate is redundant with FR-4's post-batch check on declared `target_files`.
- R2-S5 (typed artifact-consumption manifest in `t-context-inherit`) — REJECT for MVP. Premature flexibility for a 2-type universe (code + design docs). Defer to Increment 3.
- R2-S6 (batch-index-tiered gate) — REJECT. Batch-index is the wrong discriminator; project-state detection at the gate is the right one.

_Status: **TRIAGED 2026-05-31 → ADOPTED.** Part-2 phantom-API findings behaviorally re-verified against live SDK (requirements R4). R3-S1 (rewrite §1 row 6 — checkpoint-v4 is functionally v2, wave_* never persist), R3-S2 (`batch_record_v1.json` — satisfied by the existing `BatchLedger`), R3-S3 (`batch_metadata` rename) all APPLIED. Part-4 essential task set adopted as the canonical build surface (see the header note). R2-S2 → `flock(LOCK_EX|LOCK_NB)` not `O_EXCL`._

## Areas Substantially Addressed

| Area | Accepted (R1) | Addressed (≥3)? |
|------|---------------|-----------------|
| Risks | 2 | — |
| Architecture | 1 | — |
| Validation | 1 | — |
| Security | 1 | — |
| Data | 1 | — |
| Ops | 1 | — |
| Interfaces | 1 | — |

---

## Requirements Coverage Matrix — R1

Analysis only (no triage). Maps each requirement in `PLAN_BATCH_ORCHESTRATION_REQUIREMENTS.md` v0.2 to plan coverage.

| Requirement | Plan Section / Task | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 Partition into ordered batches | §5 `BatchPartitioner`; §7 `t-partitioner`, `t-emit-partition`; §6 Increment 1 | Full | — |
| FR-2 Dependency-closed + file-cohesive (hard invariant) | §5 `BatchPartitioner`; §7 `t-partitioner` (closure/cohesion tests); §3 dependency semantics | Partial | No rule for cohesion-vs-closure conflict (R1-S2/R1-F3); no behavior for unknown-`target_files` tasks (R1-F2); no max batch size. |
| FR-3 Sequential execution loop | §5 `BatchOrchestrator`; §7 `t-orchestrator`; §6 Increment 0 | Full | — |
| FR-4 Review/validation gate between batches | §5 `BatchOrchestrator` (validation gate); §7 `t-orchestrator`; OQ-5 | Partial | No default gate, no audited override record, no on-failure disposition (R1-S5/R1-F7). |
| FR-5 Cross-batch resume | §5 REUSE checkpoint-v4; §7 `t-resume-ledger`; §6 Increment 0 | Partial | No partition pinning/recompute policy (R1-S6/R1-F5); resume-into-failed-batch state undefined (R1-S5/R1-F4). |
| FR-6 Per-batch cost budget | §7 `t-partitioner` ("optional cost sub-splitting"); R2 (token budget) | Partial | No budget units, no global-cap-mid-batch behavior, no sink (R1-S7/R1-F6). |
| FR-7 Progress + provenance | §5 `BatchOrchestrator` (record state); §7 `t-orchestrator` | Partial | No concrete provenance sink or minimum fields (R1-S7/R1-F6). |
| FR-8 Leverage existing partition logic | §1 reuse table; §5 `BatchPartitioner`; §9 discoveries | Full | (Soundness of anchors unverified — see R1-S1, validation gap not a coverage gap.) |
| FR-9 Iterative delivery | §6 Increments 0–3; §7 build order | Full | — |
| FR-10 Inter-batch context inheritance | §4 mitigation 1; §5 inter-batch context injection; §7 `t-context-inherit`; §6 Increment 2 | Partial | No trigger/completeness/acceptance criteria; missing-artifact (silent-degradation) behavior undefined (R1-F1); poisoned-partial-artifact inheritance unguarded (R1-S5). |
| NFR-1 No regression (single-run path) | §5 REUSE as-is; §7 `t-tests` (no-regression); §8 R4 | Full | — |
| NFR-2 Determinism | §5 ("Deterministic"); §7 `t-partitioner` (determinism tests) | Partial | Tie-break order for cohesion merges unspecified (R1-S2); partition not pinned across resume (R1-S6). |
| NFR-3 Reviewability over speed | §6 (small increments); whole sequential framing | Partial | Mega-batch risk from cohesion-vs-closure undermines small-batch goal (R1-S2/R1-F3). |
| NFR-4 Respect context-isolation constraint | §2 (why parallel failed); §4; FR-10 linkage; §8 R1/R2 | Partial | Increment-0 DESIGN-phase seam risk understated vs IMPLEMENT-on-disk claim (R1-S4). |
