# Plan Batch Orchestration — Requirements

**Version:** 0.4 (R1 applied; R2 + R3 triaged → R3-distilled MVP adopted)
**Date:** 2026-05-29 (v0.4 triage 2026-05-31)
**Status:** Reviewed against the wave/lane/dependency code + parallel-failure postmortems
**Component:** startd8 SDK + cap-dev-pipe (prime-contractor / plan-ingestion path)
**Related:** `context-bridge/` (Eagle structure analyzer — feeds partitioning, not the batcher), `cap-dev-pipe/CLAUDE.md`

---

## 0. Planning Insights (Self-Reflective Update)

> Changes between v0.1 (pre-planning) and v0.2, after a deep read of the wave/lane/
> dependency code and the parallel-failure postmortems (see
> `PLAN_BATCH_ORCHESTRATION_PLAN.md`). 8 corrections; the headline one reshaped the MVP.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| Reuse `compute_waves()` (Kahn) as the partitioner | **No `compute_waves()` exists.** `wave_index` is seed-static (`shared.py:64-65`); real primitives are `_topological_sort()` (`shared.py:243`) + `compute_lanes()` (union-find, `artisan_contractor.py:970`) | **FR-8** corrected to those primitives |
| Parallel failed on scheduling/ordering | It failed on **design-time context isolation** — lane-peers design incompatible changes to shared files with only 300-char summaries (`CONTEXT_CORRECTNESS_BY_DESIGN.md:43-211`); ordering/locking work | Reframes the risk model (**NFR-4**) |
| A sequential loop + gate is sufficient | **Sequential does NOT auto-fix context isolation at batch seams** — batch N+1's design phase still won't see batch N's outputs | **New FR-10** (inter-batch context inheritance); an in-scope increment, not optional |
| Batches keyed on wave/phase/milestone | Best key = **dependency-closed AND file-cohesive** (`compute_lanes()` + shared-file manifest) | **FR-1/FR-2** refined; file-cohesion added |
| `--task-filter` revalidates dependencies | It does **not**; the partitioner must validate closure itself (`_detect_and_break_cycles`, `queue.py:413`) | **FR-2** owns closure validation |
| Cross-batch resume needs new machinery | Checkpoint **v4** already carries `wave_assignments`/`completed_waves`/`current_wave` (`artisan_contractor.py:532`) | **FR-5** reuses it |
| `wave_metadata` is the only dormant piece | The shared-file **manifest + critical-path** (`design_support.py:449`) are also computed-but-unused | Reuse them (FR-8/FR-10) |
| Populating `wave_metadata` is safe | It could feed the dormant cross-lane **parallel** path | **OQ-7 → hard risk**: emit partition metadata for **ordering only**; assert serial |

**Resolved open questions:**
- **OQ-1 → Both layers.** A `BatchPartitioner` in the SDK (emits partition metadata at the
  `:976` stub) + a `BatchOrchestrator` loop in cap-dev-pipe (`run-prime-contractor
  --task-filter` per batch).
- **OQ-2 → No `compute_waves()`;** use `_topological_sort()` + `compute_lanes()` + the
  shared-file manifest.
- **OQ-3 → Parallel failed on *context isolation*,** not ordering; a task can't reliably
  depend on another's *generated output* at design time.
- **OQ-4 → Batches keyed on dependency-closure + file-cohesion** (lanes), not raw
  phase/milestone.
- **OQ-5 → Gate = the plan's per-batch acceptance / build / tests, with operator override**
  (mechanism kept configurable).
- **OQ-6 → Reuse checkpoint-v4 state** for cross-batch resume.
- **OQ-7 → Real risk;** emit partition metadata for ordering only, with a test asserting no
  concurrent generation.

### CRP Review Update (v0.2 → v0.3)

An independent Convergent Review (R1) accepted all 15 suggestions (7 F + 8 S). Requirements
hardened: **FR-10** got a testable trigger/acceptance + **blocking** missing-artifact
behavior (no silent fallback to summaries); **FR-2** gained cohesion-vs-closure conflict
resolution (max batch size or named error) + unknown-`target_files` handling; **FR-4** a
default gate + audited overrides; **FR-6/FR-7** measurable units/sink; and new **FR-11**
(cross-batch quarantine/rollback) + **FR-12** (partition pinning by seed hash). Plan-side
fixes (a reuse-verification spike, a concrete Risk-R1 guard, a sharper Increment-0 seam
caveat) are in `PLAN_BATCH_ORCHESTRATION_PLAN.md` v1.1.

---

## 1. Problem Statement

A large plan (e.g. an MVP spanning milestones M1–M6) is too big to generate in a single
Prime Contractor run — for cost, reviewability, and risk reasons. This session we split
one plan **by hand** into milestone batches (M1–M2 → M3 → M4 → M5–M6), running
plan-ingestion + prime-contractor once per batch and reviewing between. **Plan Batch
Orchestration** automates that: take one plan, derive *dependency-closed* batches, and run
the Prime Contractor **sequentially** over them with a review/validation gate between
batches.

| Component | Current State | Gap |
|-----------|--------------|-----|
| Batch boundaries | Operator decides milestones manually | No automated, dependency-aware partition |
| Per-batch run | `run-prime-contractor.sh --task-filter <ids>` works for a subset | No loop/orchestrator over batches |
| Batch ordering | Implicit in operator's head | No enforced "batch N depends only on batches < N" guarantee |
| Review between batches | Manual (`--list`, `npm test`) | No gate that blocks the next batch on the prior's validation |
| `wave_metadata` (partition signal) | Schema field plumbed end-to-end | **Producer stubbed**: `plan_ingestion_emitter.py:976` = `None` |
| Resume after partial failure | `--retry-incomplete` (within a run) | No cross-batch resume |

### Critical distinction (preserve throughout)

- **INTER-run batching (this capability / MVP):** split one plan into **N separate,
  sequential** prime-contractor runs. One batch completes and passes its gate before the
  next starts. Low concurrency risk.
- **INTRA-run parallel waves/lanes (NOT this capability):** concurrent generation of
  multiple tasks *inside one run*. This is the historically hard, partially-failed effort.
  It is **explicitly out of scope** here (see Non-Requirements).

---

## 2. Requirements

### MVP — Sequential batch orchestration

- **FR-1 Partition a plan into ordered batches.** Given an ingested plan/seed, produce an
  ordered list of batches (each a set of task IDs) that are **dependency-closed and
  file-cohesive** (see FR-2).
- **FR-2 Dependency-closed + file-cohesive batches (hard invariant).** Every task in batch
  *k* depends only on tasks in batches *≤ k*; **no task depends on a later batch**. Tasks
  that share `target_files` (per `compute_lanes()` / the shared-file manifest) stay in the
  **same** batch. The partitioner validates acyclicity itself (`_detect_and_break_cycles`),
  since `--task-filter` does **not** revalidate dependencies. *(Confirmed: tasks form a DAG
  via `depends_on`, orderable by `_topological_sort()`.)*
  - **Cohesion-vs-closure conflict (R1-F3/R1-S2):** when a `compute_lanes()` component spans
    tasks at different dependency depths, merge them into the **smallest dependency-closed
    batch that contains the whole lane**, up to a **max batch size**; if that bound is
    exceeded, **fail with a named error** rather than silently collapsing the plan into one
    batch (protects NFR-3). Merge/tie-break order is deterministic (NFR-2).
  - **Unknown `target_files` (R1-F2):** for edit/discovery tasks whose `target_files` aren't
    known until generation, the partitioner behavior is configurable — either **require
    declared `target_files`** in the seed, or place such a task in a **trailing singleton
    batch** — with the FR-4 gate as the backstop for post-hoc file collisions.
- **FR-3 Sequential execution loop.** Run the Prime Contractor once per batch, in order,
  passing that batch's task IDs (assumption: via the existing `--task-filter`). Batch *k+1*
  does not start until batch *k* has completed.
- **FR-4 Review/validation gate between batches.** After each batch, run a defined
  validation step (e.g. the plan's per-batch acceptance / `npm test` / build) and require
  it to pass (or an explicit operator override) before the next batch runs. **A default gate
  applies when the plan specifies none** (build + the batch's acceptance criteria).
  **Operator overrides are audited** — recorded in the FR-7 provenance store (who/when/why);
  an overridden failure still surfaces the FR-10 seam caveat. *(R1-F7)*
- **FR-5 Cross-batch resume.** If the orchestration stops (failure, budget, manual halt),
  it can resume from the next incomplete batch without redoing completed ones.
- **FR-6 Per-batch cost budget.** Each batch gets its own budget in **declared units (USD)**;
  the orchestrator tracks **per-batch and cumulative** spend and stops at a global cap. On
  hitting the cap **mid-batch**, the in-flight batch **finishes to a checkpoint** (no hard
  kill), then the loop halts before the next batch. *(R1-F6)*
- **FR-7 Progress + provenance.** The orchestrator records, per batch, to a **named sink**
  (the resume ledger / checkpoint-v4 state — see PLAN §5 / R1-S7): **batch ID, task IDs,
  status, cost, gate result, and any override**. Inspectable between batches (the `--list`
  analogue). *(R1-F6)*
- **FR-8 Leverage existing partition logic.** Reuse `_topological_sort()` (`shared.py:243`,
  ordering), `compute_lanes()` (`artisan_contractor.py:970`, union-find on shared
  `target_files`+`depends_on` for file cohesion), and the shared-file manifest
  (`design_support.py:449`) as the *partitioning* substrate. Do **not** invent a new
  dependency model. (Note: there is **no** `compute_waves()`; `wave_index` is seed-static.)
- **FR-9 Iterative delivery.** Ship in small, independently-verifiable increments (see §5),
  each usable on its own.
- **FR-10 Inter-batch context inheritance (the parallel-failure fix, applied to seams).**
  Batch *k+1*'s design context MUST include prior batches' **generated artifacts / design
  docs** for the files it touches — not just the 300-char summaries that allowed
  incompatible designs to sink the parallel effort. Scope the injected context via the
  shared-file manifest to bound token cost. **Trigger:** batch *k+1* contains a task whose
  `target_files` ∩ files produced by prior batches ≠ ∅. **Acceptance:** for every such file
  F, batch *k+1*'s design context contains F's current on-disk content (or design doc), not
  its 300-char summary — asserted by a context-coherence test. **Missing-artifact behavior is
  BLOCKING, not silent:** an absent expected artifact halts the batch with a diagnostic
  rather than falling back to the summary (the silent fallback **is** the parallel-failure
  mode). Inherits only **completed** batches' outputs (see FR-11). Required for general
  correctness; **delivered in Increment 2** (earlier increments carry a documented seam
  caveat, mitigated by file-cohesive batches + prior-batch code already being on disk for
  edit-mode tasks). *(R1-F1)*
- **FR-11 Cross-batch failure / rollback semantics.** When batch *k*'s FR-4 gate fails after
  partial generation, its artifacts are left in a **defined, quarantined** state (not
  reverted, not silently kept): resume re-enters batch *k* cleanly, and **FR-10 inheritance
  reads only *completed* batches' outputs**, never a failed batch's half-written files.
  *(R1-F4 / R1-S5)*
- **FR-12 Partition pinning.** The computed partition is **persisted with the seed hash** in
  the resume ledger and **pinned** across resume; if the plan/seed changes mid-run (hash
  mismatch) the orchestrator **fails loudly** rather than silently re-partitioning completed
  batches. *(R1-F5 / R1-S6)*

---

## 3. Non-Functional Requirements

- **NFR-1 Extreme caution / no regression.** The existing single-run path
  (`run-prime-contractor.sh` with no batching) must keep working unchanged; batching is
  additive and opt-in.
- **NFR-2 Determinism.** Given the same plan, partitioning produces the same batches in the
  same order (reviewable, reproducible).
- **NFR-3 Reviewability over speed.** Optimize for small, reviewable batches and clear gates
  — not throughput. (Speed/parallelism is explicitly not a goal here.)
- **NFR-4 Respect the context-isolation constraint.** Parallel generation failed because
  design-time context was isolated (lane-peers couldn't see each other's designs; only
  300-char summaries). The sequential design must not reproduce this at batch seams — hence
  **FR-10**. The ordering/locking primitives (`_topological_sort`, `compute_lanes`) are
  sound and are reused as-is.

---

## 4. Non-Requirements

- **No parallel / concurrent generation.** Intra-run waves/lanes (multiple tasks generated
  at once) are **deferred and guarded**, not built. The historical parallel effort is
  studied for its dependency lessons only.
- Does **not** modify the Prime Contractor's internal per-task scheduling or the Artisan
  phase machinery.
- Does **not** author plan content or change the polish/ingestion contract beyond
  populating the partition signal.
- Does **not** require the Eagle/Context-Bridge structure analyzer (it may *inform*
  service-boundary partitioning later, but is not a dependency for the MVP).

---

## 5. Iterative delivery increments (assumption — refine in planning)

- **Increment 0 — Orchestrator loop over operator-defined batches.** Loop
  `run-prime-contractor --task-filter` over operator-supplied batches + validation gate +
  cross-batch resume. Codifies this session's manual cadence; lowest risk. *Carries a
  documented context-isolation caveat at batch seams until Increment 2 — mitigated meanwhile
  by file-cohesive batches and batch N's code being on disk for N+1's edit-mode tasks.*
- **Increment 1 — Automatic partitioning.** `BatchPartitioner` derives dependency-closed,
  file-cohesive batches (`_topological_sort` + `compute_lanes` + shared-file manifest); emit
  partition metadata (**ordering only**) at the `:976` stub. Optional cost/complexity
  sub-splitting under a per-batch budget.
- **Increment 2 — Inter-batch context inheritance (FR-10; the essential fix).** Inject
  prior-batch outputs into the next batch's design context; add a context-coherence
  regression test. **Not optional** for general correctness.
- **Increment 3 (guarded — maybe never) — intra-batch parallelism.** Only if Increment 2
  proves context coherence is solvable. Default off.

---

## 6. Open Questions

*All v0.1 open questions (OQ-1 … OQ-7) were resolved during planning — see §0.* None remain
open for the MVP. The one that hardened into a constraint is **OQ-7**: partition metadata is
emitted for **ordering only**, with a test asserting no concurrent generation (Risk R1 in
the plan).

---

*v0.2 — Post-planning self-reflective update. Headline: planning revealed the prior parallel
effort failed on **design-time context isolation**, not scheduling, and that a sequential
loop alone does **not** fix it at batch seams → added **FR-10** (inter-batch context
inheritance), delivered in Increment 2. Corrected **FR-8** (no `compute_waves()`; use
`_topological_sort` + `compute_lanes` + shared-file manifest), refined **FR-1/FR-2**
(dependency-closed **+ file-cohesive**), reframed **NFR-4**, and resolved all 7 open
questions. Paired with `PLAN_BATCH_ORCHESTRATION_PLAN.md` v1.0.*

*v0.3 — Convergent Review R1 applied (7 F-suggestions, all accepted): FR-10 made testable
+ blocking on missing artifacts; FR-2 cohesion-vs-closure + unknown-`target_files`; FR-4
default gate + audited override; FR-6/FR-7 measurable; new FR-11 (rollback) + FR-12
(pinning). Dispositions in Appendix A. Paired with `PLAN_BATCH_ORCHESTRATION_PLAN.md` v1.1.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-F{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-F1 | FR-10 testable: trigger + acceptance + **blocking** on missing artifact | R1 | Applied → FR-10 | 2026-05-29 |
| R1-F2 | FR-2 unknown-`target_files` handling | R1 | Applied → FR-2 | 2026-05-29 |
| R1-F3 | FR-2 cohesion-vs-closure conflict (max size / named error) | R1 | Applied → FR-2 | 2026-05-29 |
| R1-F4 | Cross-batch failure / rollback semantics | R1 | New → FR-11 | 2026-05-29 |
| R1-F5 | Partition recompute/pinning on plan change | R1 | New → FR-12 | 2026-05-29 |
| R1-F6 | FR-6/FR-7 measurable (units, global-cap-mid-batch, sink, fields) | R1 | Applied → FR-6, FR-7 | 2026-05-29 |
| R1-F7 | FR-4 default gate + audited override | R1 | Applied → FR-4 | 2026-05-29 |
| R2-F2 | Provenance enrichment (config/seed/output fingerprints, quality summary) | R2 | Applied (modified) → Essential-5: keep `config_hash`+`seed_fingerprint`, scope output fingerprints to declared `target_files`, drop `quality_summary`. Target = `BatchLedger` (`batch_postmortem.py`), NOT checkpoint-v4. | 2026-05-31 |
| R3-F1 | `batch_record_v1.json` instead of extending checkpoint-v4 | R3 | Applied → Essential-4/5. Checkpoint-v4 `wave_*` phantom verified; the existing `BatchLedger` already implements the fresh artifact. | 2026-05-31 |
| R3-F2 | Rename emitter seam `wave_metadata` → `batch_metadata` (additive) | R3 | Applied → Essential-1 / `t-batch-partitioner`. Structural R1 mitigation: parallel path keeps reading `wave_metadata=None`. | 2026-05-31 |
| R3-F3 | Load-bearing-doc verification protocol (cited `file:line` ⇒ companion test) | R3 | Applied → folds into `t-baseline-characterization` (doc-cite lint). Applied to R3 itself in the R4 note. | 2026-05-31 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R2-F1 | FR-13 design-failure cascade gate | R2 | SDK Leg 13 #46-47 is a *within-run* resume-cache defect; the cross-batch seam is process-level (each batch starts from disk), so the lesson is shape-incompatible. Residual signal subsumed by the gate's post-check: "FAIL if a task with declared `target_files` wrote zero files." | 2026-05-31 |
| R2-F3 | Typed artifact-consumption manifest | R2 | Premature flexibility — the MVP cross-batch artifact universe is exactly two kinds (code files, design docs). FR-10's on-disk trigger + blocking-on-missing already gives the MissingConsumed property structurally. Deferred to Increment 3 (only if intra-batch parallelism is pursued). | 2026-05-31 |
| R2-F4 | Tiered preflight by batch index | R2 | Batch-index is the wrong discriminator (BATCH-1 may be a brownfield add; BATCH-2 may have no test infra yet). Replaced by project-state detection at the gate (`package.json`→`npm test`; `pyproject.toml`→`pytest`; neither→WARN). | 2026-05-31 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-7-1m — 2026-05-29

- **Reviewer**: claude-opus-4-7-1m
- **Date**: 2026-05-29 20:10:00 UTC
- **Scope**: Requirements quality for sequential plan-batch orchestration — testability of FR-10 (inter-batch context inheritance), airtightness of the FR-2 dependency-closed + file-cohesive invariant, and missing MVP acceptance criteria (failure/rollback, partition recompute, observability, cost accounting).

**Executive summary** (top requirements gaps):

- FR-10 names *what* to inject but has no **trigger**, no **completeness/acceptance** test, and no failure behavior when a prior artifact is missing — the headline fix is currently unverifiable.
- FR-2's file-cohesion invariant is under-specified for the case where a task's `target_files` are **unknown until generation** (edit-mode / discovery tasks) — the partition can become wrong *after* it is computed.
- FR-2 has no defined behavior when `compute_lanes()` cohesion and dependency-closure **conflict** (a lane spanning tasks in two dependency layers can force an arbitrarily large batch).
- No requirement covers **partition recomputation** if the plan/seed changes mid-run, yet FR-5 resume assumes a stable partition.
- FR-4 ("validation gate") and FR-5 (resume) lack acceptance criteria for **cross-batch rollback / failure semantics** — what state batch *k*'s partial output is left in when its gate fails.
- FR-6 cost budget and FR-7 provenance are stated but have no measurable acceptance criterion (units, where recorded, what "stop at global cap" does to an in-flight batch).

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Validation | high | Make FR-10 testable: specify the **trigger** ("batch *k+1* contains a task whose `target_files` ∩ prior-batch produced files ≠ ∅"), the **scope** (manifest-bounded set, named), the **completeness/acceptance criterion** (e.g. "for every file F that batch *k+1* edits and a prior batch produced, the design context for *k+1* contains F's current on-disk content or design doc"), and **what happens when an expected artifact is absent** (BLOCKING vs WARNING). | As written, FR-10 says context "MUST include prior batches' generated artifacts … for the files it touches" but gives no way to verify inclusion happened or to detect the silent-degradation path (missing artifact → falls back to 300-char summary = the exact parallel-failure mode). | FR-10, after "Scope the injected context via the shared-file manifest" | Context-coherence regression test: construct batch *N* that writes `utils.py` and batch *N+1* that edits it; assert *N+1*'s design context contains the real `utils.py`, not its summary; assert a missing-artifact case is flagged, not silently defaulted. |
| R1-F2 | Data | high | FR-2 must define behavior for tasks whose `target_files` are **not known until generation** (edit/discovery tasks). State explicitly whether the partitioner (a) requires `target_files` to be declared in the seed, (b) treats unknown-`target_files` tasks as a singleton/last batch, or (c) is best-effort and the **gate** catches post-hoc file collisions. | FR-2 grounds cohesion on `compute_lanes()` over `target_files`, but `target_files` may be empty/unknown at partition time, so a task that *later* writes a shared file silently breaks the file-cohesion invariant after partitioning. The review brief flags this exact edge case. | FR-2, after the union-find sentence | Test: seed with a task that declares no `target_files` but generates an edit to a file owned by an earlier batch; assert the documented behavior (rejected, deferred, or gate-caught) actually occurs. |
| R1-F3 | Risks | high | Add an explicit acceptance criterion for the **cohesion-vs-closure conflict**: when a single `compute_lanes()` component spans tasks at different dependency depths, define the resolution (merge into one batch up to a max size, else fail with a named error). Cap batch size or declare it unbounded-by-design. | FR-2 asserts both "dependency-closed" and "file-cohesive" as a hard invariant but does not say which wins when a shared-file lane forces a batch to absorb a long dependency chain — this can collapse the whole plan into one batch, defeating the MVP's reviewability goal (NFR-3). | FR-2, new sub-bullet | Test: craft a lane that transitively links batch-1 and batch-4 tasks; assert partitioner either merges them per the documented rule or fails with the specified error, and that NFR-3 small-batch expectation is reconciled. |
| R1-F4 | Risks | high | Add a requirement (or extend FR-5) for **cross-batch failure / rollback semantics**: define the state of batch *k*'s partial artifacts when its FR-4 gate fails (left on disk? reverted? quarantined?), and whether resume re-runs the failed batch from scratch or from its internal checkpoint. | FR-4 requires the gate to pass before the next batch, and FR-5 resumes "from the next incomplete batch," but neither defines what happens to a batch that *started and failed its gate* — half-generated files on disk become poisoned context for FR-10 inheritance. | New FR-11 or FR-5 extension | Test: fail batch *k*'s gate after partial generation; assert resume re-enters batch *k* in the documented state and that FR-10 does not inherit half-written artifacts. |
| R1-F5 | Data | medium | Add a requirement for **partition recomputation on plan change**: state whether the partition is frozen at first run (resume reuses the stored partition) or recomputed each invocation, and what happens if the plan/seed hash changes mid-run. | FR-5 resume + NFR-2 determinism implicitly assume a stable partition, but nothing forbids the operator editing the plan between batches; a recomputed partition could reorder or re-split already-completed batches, corrupting the resume ledger. | New FR or NFR-2 extension | Test: change the seed between batch *k* and *k+1*; assert the orchestrator either pins the original partition (with a warning) or fails loudly rather than silently re-partitioning. |
| R1-F6 | Ops | medium | Give FR-6 and FR-7 measurable acceptance criteria: FR-6 — define budget **units** (USD/tokens), per-batch vs cumulative tracking, and the behavior of "stop at a global cap" for an **in-flight** batch (hard kill vs finish-current). FR-7 — specify **where** provenance is recorded (the resume ledger? a per-batch artifact?) and the minimum fields, so "inspectable between batches" is verifiable. | Both are currently aspirational ("tracks", "records") with no unit, location, or stop-semantics, so neither can be acceptance-tested and the global-cap edge (cap hit mid-batch) is undefined. | FR-6 and FR-7 | Test: set a global cap below batch-2's projected cost; assert the documented stop behavior. Inspect the named provenance store after a run; assert all minimum fields present per batch. |
| R1-F7 | Validation | medium | Strengthen FR-4: define the **default** validation step when the plan specifies none, make the operator-override **audited** (recorded in provenance per FR-7), and state whether a gate failure with override still triggers FR-10 caveats. | FR-4 lists examples ("npm test / build") and allows "explicit operator override" but no default and no record of overrides, so a run can silently skip validation and the provenance trail (FR-7) would not show it. | FR-4 | Test: run a batch with no plan-defined gate (assert default applies); override a failing gate (assert override is recorded in the FR-7 provenance store). |

(No prior rounds exist; no endorsements/disagreements applicable for R1.)

_Triaged 2026-05-29: all 7 R1-F items **accepted** → Appendix A. No rejections._

#### Review Round R2 — claude-opus-4-7-1m (lessons-learned synthesis) — 2026-05-30

- **Reviewer**: claude-opus-4-7-1m (lessons-learned synthesis pass, not an independent architectural review — sourced from `/Users/neilyashinsky/Documents/craft/Lessons_Learned/sdk/lessons/{10-workflow-system,11-multi-agent-workflows,13-cross-system-pipeline}.md`).
- **Date**: 2026-05-30
- **Scope**: Requirements-level improvements derived from validated SDK lessons that the v0.3 requirements do not yet absorb. Focus areas: design-failure cascade prevention, provenance richness, typed inter-batch artifact contracts, and lifecycle-aware preflight gates. Plan-level companions are in the plan's R2 (S-suggestions).

**Executive summary**

- **Design-failure cascade is uncovered.** FR-11 handles gate failure *after* partial IMPLEMENT, but does not catch a batch whose DESIGN phase silently failed before IMPLEMENT ran — the exact shape of SDK Leg 13 #46-47 (`--force-design` did not invalidate downstream cache; design-failed tasks proceeded through IMPLEMENT with no design doc). Batch N+1 can inherit a poisoned upstream and never know.
- **FR-7 provenance fields are too thin** vs the canonical `run-provenance.json` shape (SDK Leg 13 #11). Missing config snapshot, per-artifact output fingerprints, and quality summary. Without per-artifact fingerprints, FR-12's seed-hash protection has no symmetric output-side guard — an out-of-band edit to batch N's artifacts silently corrupts FR-10 inheritance.
- **FR-10 inheritance is untyped.** It says "include prior batches' generated artifacts / design docs" without declaring *which* artifact types batch N produces that batch N+1 consumes. SDK Leg 11 #59-60 (design docs generated but not consumed) and SDK Leg 13 #19-20 (artifact registry coverage gaps) document this as a recurring silent-gap failure mode.
- **FR-4 default gate is project-lifecycle-blind.** Treating BATCH-1 (greenfield — project may not exist yet) and BATCH-N>1 (incremental — protecting structure) identically forces operators to choose between blocking on absent infrastructure (BATCH-1 false positive) or skipping the gate everywhere (BATCH-N regression risk). SDK Leg 13 #18 (advisory-by-default preflight) provides the canonical tiering.

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Robustness | high | Add **FR-13 — Design-failure cascade gate.** Before batch N+1 starts, the orchestrator MUST verify that batch N's DESIGN-phase produced its expected artifacts and that none are marked failed. If any expected design artifact is missing or failed, batch N+1 **halts loudly** with a diagnostic citing the missing/failed artifact and the batch boundary — the orchestrator MUST NOT proceed to IMPLEMENT against an absent or failed design. Trigger: batch N+1 pre-start. Acceptance: a synthetic test marking batch N's design-phase as failed produces a halt at batch N+1 start without spawning `run-prime-contractor`. Behavior: BLOCKING (not advisory), parallel in shape to FR-12's loud failure on seed-hash mismatch. | SDK Leg 13 #46-47 documents the exact failure: `--force-design` did not invalidate downstream resume cache → TEST/REVIEW silently reused stale results; design-failed tasks proceeded through IMPLEMENT with no design doc. FR-11 covers gate failure *after partial IMPLEMENT*, which is a different timing (post-IMPLEMENT). FR-12 covers seed mutation. Neither catches pre-IMPLEMENT design failure at the seam. This is the canonical SDK silent-cascade failure mode and the cheapest place to close it. | New FR-13 in §2 MVP (after FR-12); also strengthens FR-10 (inheritance preconditions) and FR-11 (which currently covers only the post-IMPLEMENT case). | Construct batch N with a forced empty design output (or simulated DESIGN crash). Invoke orchestrator for batch N+1. Assert: (a) batch N+1 halts before any `run-prime-contractor` spawn; (b) diagnostic names the missing artifact + batch boundary; (c) resume re-enters batch N (not N+1) to allow re-running its design phase. |
| R2-F2 | Ops | medium | Extend **FR-7 provenance fields** beyond `{batch ID, task IDs, status, cost, gate result, override}` to include: (a) **config snapshot** (the orchestrator's effective config at batch start, content-hashed); (b) **input seed fingerprint** (already implied by FR-12 — record it explicitly per batch); (c) **per-artifact output fingerprints** (SHA-256 of every file batch N wrote, keyed by path); (d) **quality summary** (per-task confidence scores if available, override count, count of gate failures suppressed by override). Schema is the contract; subsequent classifiers (parallel to Forward Manifest Fix 3) consume against it. | SDK Leg 13 #11 (`run-provenance.json` artifact for CLI lineage) specifies these as the canonical shape: execution context + config snapshot + input/output fingerprints + quality summary. The v0.3 FR-7 field set covers only the first half. Without per-artifact output fingerprints, FR-12's "fail loudly on seed-hash mismatch" has no symmetric output-side protection — an out-of-band edit to batch N's artifacts between batches silently corrupts FR-10 inheritance. Quality summary is the postmortem classifier's hook. | FR-7 in §2 (expand the field list); §5 partition/ledger components carry the schema. Plan companion: R2-S4 wires the writer into `t-resume-ledger`. | Multi-batch run; inspect ledger; assert all enumerated fields present + well-formed per batch. Mutate one file written by batch N between batches; assert batch N+1's provenance read detects fingerprint drift loudly. |
| R2-F3 | Architecture | high | Extend **FR-10** to require a **typed artifact-consumption manifest**. Per batch boundary, declare which **artifact types** batch N produces (e.g. `code_files`, `design_docs`, `interface_contracts`, `tests`) and which batch N+1 consumes. The orchestrator MUST validate at the seam that every consumed type has a producer in a prior **completed** batch (FR-11 quarantine). Consumer-without-producer fails loudly (mirrors FR-10's blocking missing-artifact behavior). Producer-without-consumer surfaces as advisory in FR-7 provenance (orphaned output, not blocking). The manifest schema is extensible (no static enum — see plan R2-S5). | SDK Leg 13 #19-20 (Static Artifact Type Registry & Disconnected Detection Fragments — "static enum + parallel dicts create invisible coverage gaps; detection without action = wasted infrastructure") + SDK Leg 11 #59-60 (Pipeline Phase Artifact Disconnect — "design docs generated but not consumed by implementation") together show this is a recurring SDK silent-gap failure mode. FR-10 v0.3 says "include prior batches' generated artifacts / design docs" — without a typed manifest, batch N can produce artifact type X that batch N+1 never reads (silent orphan), or batch N+1 can expect type Y that no prior batch produces (FR-10 silently falls back to the 300-char summary = the parallel-failure mode FR-10 exists to close). A typed manifest closes both holes by construction. | FR-10 in §2: new sub-bullet "consumption manifest" alongside the trigger/acceptance/missing-artifact bullets. Schema sketch in §0. Plan companion: R2-S5 implements it inside `t-context-inherit`. | (a) Configure batch N+1 to declare consumption of `design_docs`; configure batch N to produce only `code_files`. Assert seam validation fails loudly with the unmet consumption type. (b) Configure batch N to produce `interface_contracts` that no later batch declares as a consumer; assert provenance records this as advisory orphan (not blocking). (c) Round-trip: assert the manifest is recorded in FR-7 provenance per batch. |
| R2-F4 | Validation | medium | Extend **FR-4 default gate** to be **tiered by batch position**: BATCH-1 = **advisory-by-default** (WARN on most preflight checks; FAIL only on conditions that prevent code generation entirely — e.g. unparseable seed); BATCH-N where N>1 = **blocking on regressions** against structure established by prior batches (project must exist, tests must pass if a test suite was created, build must succeed). Tier is auto-selected from the orchestrator's batch index, not a per-batch config flag. Operator override (FR-4 existing) still applies on top of the tier. | SDK Leg 13 #18 (Advisory-by-Default Preflight for Greenfield Code Generation): "preflight rules default to WARN unless condition prevents code generation. FAIL rules designed for established codebases produce false positives in greenfield." A strict `npm test` gate on BATCH-1 in an empty project directory fails for the wrong reason (no test infrastructure yet) — the operator's only escape is FR-4 override, which then logs as "audited override" even though the failure was a false positive. Tiered gates match the actual project lifecycle: BATCH-1 establishes structure; BATCH-N>1 protects it. | FR-4 in §2 (extend the default-gate paragraph); plan companion: R2-S6 implements the tier selection in `t-orchestrator`. | (a) Run BATCH-1 in an empty project directory with default `npm test` gate; assert WARN logged + batch 2 proceeds. (b) Run BATCH-2 with an introduced regression (failing test added by BATCH-1); assert blocking — batch 3 does not start; assert the override path still works and is audited per existing FR-4. |

(Lessons-learned synthesis round; no endorsements/disagreements section — R2's suggestions derive from external knowledge base, not from re-reading R1's suggestions.)

_Status: **TRIAGED 2026-05-31 → see Appendix A/B and the R4 disposition note below.** R2-F2 applied (modified); R2-F1, R2-F3, R2-F4 rejected (rationale in Appendix B). Pairs dispositioned with their plan-side S-companions._

#### Review Round R3 — claude-opus-4-7-1m — 2026-05-30 — Independent pressure-test + complexity audit

- **Reviewer**: claude-opus-4-7-1m
- **Date**: 2026-05-30
- **Scope**: Independent pressure-test of R2 lessons-derived suggestions PLUS cumulative complexity audit (Brooks essential-vs-accidental). Behavioral verification of the plan's §1 reuse table against the actual SDK code (informed by the Forward Manifest phantom-API precedent).

### Part 1 — Pressure-test of the 6 R2 items

**R2-F1 + R2-S3 — Design-failure cascade gate (FR-13)**
**Summary answer:** REJECT — the lesson is misapplied; subsume the residual signal into a revised FR-11 / FR-4.
**Rationale:** SDK Leg 13 #46-47 documents `--force-design` failing to invalidate downstream **resume cache** *within one prime-contractor run* — TEST/REVIEW re-using stale results. That is shape-incompatible with a cross-batch seam: each batch is a separate `run-prime-contractor` process and starts from disk, not from another run's resume cache. The R2 synthesis says "before batch N+1 starts, verify batch N's DESIGN-phase produced its expected artifacts" but offers no description of where that "expected design-artifact list" lives at the cross-batch boundary, no canonical artifact path, and assumes the resume ledger carries it — which R2-S4 has to land first. The alternative: FR-4 already requires the post-batch gate to assert build/tests/acceptance; if batch N's DESIGN crashed, IMPLEMENT cannot produce passing artifacts, and FR-4 already blocks batch N+1. The residual case — DESIGN crashes silently producing empty IMPLEMENT — is a *single-run* defect that the SDK must fix in its own DESIGN→IMPLEMENT boundary, not at the batch seam.
**Assumptions:** The cross-batch boundary is process-level (separate `run-prime-contractor` invocations writing finished artifacts to disk before the next starts). If a future revision shares state across batches via something other than disk + the resume ledger, this rejection weakens.
**Suggested improvements:** Replace R2-F1 with a one-line addition to FR-4: "The default gate FAILS if batch N's IMPLEMENT phase wrote zero files for any task whose seed declared `target_files`." That covers the silent-cascade shape without inventing a new mechanism. The fully-typed-manifest variant (R2-F3) is a different and more general answer to the same concern; if R2-F3 is accepted, R2-F1 is redundant by construction.

**R2-F2 + R2-S4 — Provenance schema enrichment**
**Summary answer:** ACCEPT-WITH-MODIFICATIONS — keep `config_hash` + `seed_fingerprint`; defer `output_artifact_fingerprints` to declared `target_files` only; drop `quality_summary` until the upstream confidence pipeline exists.
**Rationale:** `config_hash` and `seed_fingerprint` are cheap, finite-size scalars that directly enable FR-12's pinning check (symmetric input-side guard) and cost ~one `sha256` per batch. `output_artifact_fingerprints: {path: sha256}` at "every file batch N wrote" scales poorly — a batch producing 200 files writes 200 hashes per batch boundary, all of which must be re-read and re-verified on every resume to detect out-of-band edits. Scoping to declared `target_files` (typically <10 per batch) caps the work without losing the out-of-band-edit detection that R2-F2 wants. `quality_summary.confidence_avg` rests on SDK Leg 13 #22 (numbered gate advisory) that isn't wired into this capability and would land as `None` for every record — dead schema field.
**Assumptions:** Batches declare `target_files` (FR-2 already requires either declared `target_files` or trailing-singleton placement). If a batch's `target_files` is empty *and* writes hundreds of files (a discovery-mode batch), the scoped variant misses out-of-band edits to those files — accept that gap because FR-12's seed-hash check is the primary protection and the discovery-mode batch is the configurable case in FR-2.
**Suggested improvements:** Specify `seed_fingerprint` as exactly the same hash function and input domain as FR-12's "seed hash" — one named primitive, not two. The R2-F2 schema lists `gate_failures_suppressed` separately from `override_count`; collapse — every suppressed gate failure IS an override, so this is one counter not two. Per-record provenance lives in the ledger writer; specify that the writer is a single function with a documented schema (R2-S1's wire-audit then collapses to "this function is the only writer; readers consume against the dataclass").

**R2-F3 + R2-S5 — Typed artifact-consumption manifest**
**Summary answer:** REJECT for MVP — folds into FR-10's "shared-file manifest" with a small extension; revisit in Increment 3 if intra-batch parallelism is ever pursued.
**Rationale:** FR-10 already mandates the trigger (`target_files` ∩ prior-produced ≠ ∅) and the acceptance criterion (file F's on-disk content is injected, not its summary). A typed manifest adds: (a) producer-vs-consumer declaration ceremony at the partition, (b) seam validation logic, (c) registry extensibility framework, (d) `MissingConsumedArtifact` / orphan-output exception classes. None of these enable any behavior the FR-10 trigger condition + the existing on-disk check don't already give us for the MVP scope (code files, design docs at known paths). The cited SDK Leg 13 #19-20 lesson is about *intra-pipeline* artifact registry coverage gaps (within one run, across many handler kinds) — not inter-batch flow, where the universe of artifact types is small and known (code, design docs). The "extensible registry" is premature flexibility — name the 2-3 types you need for the MVP and hardcode them; if a fourth type ever appears, that's the moment to register, not before.
**Assumptions:** The MVP's universe of cross-batch artifact types is small (code files + design docs); the orchestrator runs sequentially with single-in-flight (R1-S3); no batch reads another batch's *internal-only* artifacts.
**Suggested improvements:** Replace R2-F3 with a one-bullet extension to FR-10: "Inheritance reads from a small fixed set of artifact kinds: `code_files` (`target_files` on disk) and `design_docs` (`<output>/design/{task_id}.md`). Other kinds are deferred." That captures the same MissingConsumed property structurally — if the file isn't at the canonical path, FR-10's blocking-on-missing-artifact behavior already fails loud.

**R2-F4 + R2-S6 — Tiered preflight by batch index**
**Summary answer:** REJECT — batch-index is the wrong discriminator; replace with a project-state check.
**Rationale:** SDK Leg 13 #18 is explicit: "preflight rules designed for **established codebases** produce false positives in **greenfield**." That's a project-state distinction, not a batch-index distinction. BATCH-1 may land in an existing project (e.g. adding M7 to an M1–M6 codebase shipped last quarter) — the synthesis would mark this advisory, suppressing real regressions. BATCH-2 may produce nothing test-runnable if BATCH-1 was design-only — the synthesis would block on a test suite that doesn't yet exist. The proxy is wrong in both directions. The right discriminator is observable state at the gate: "does `package.json` / `pyproject.toml` exist?", "does a test runner exist?", "does the build pass with no changes applied?". If yes → blocking; if no → advisory with a named diagnostic that says *what* infrastructure is missing.
**Assumptions:** The orchestrator can cheaply inspect project state at each gate (it can — the cap-dev-pipe script already inspects `package.json` for project type detection).
**Suggested improvements:** Replace R2-F4 with: "FR-4 default gate auto-detects each tool by presence: `package.json` → `npm test` blocking; `pyproject.toml` → `pytest` blocking; neither → preflight WARN with a 'no test infrastructure detected' diagnostic. Operator override is unchanged." This is one rule, not two tiers, and reads structurally rather than ordinally.

**R2-S1 — Two-site checkpoint-v4 wire-audit (markdown matrix)**
**Summary answer:** REJECT the markdown-matrix shape; ACCEPT the underlying concern as a runtime assertion.
**Rationale:** A tick-box matrix in `docs/design/notes/` decays the moment a developer adds a field without updating the matrix. SDK Leg 10 #35 (the 12+ wiring points anti-pattern) is real — but the cure isn't documentation, it's structural: a single `assert_checkpoint_roundtrip(payload)` helper that every writer calls before saving and every reader calls after loading, parameterized by the new field set. This becomes a unit test that runs in CI; it fails the moment a field is added without being threaded. The matrix never decays because it does not exist as a separate artifact.
**Assumptions:** All checkpoint readers/writers can be located via grep (`grep -rn "WorkflowCheckpoint(" src/`) and refactored to share one helper. The Phantom-API finding in Part 2 makes this MORE urgent, not less — there's already a silent drop today.
**Suggested improvements:** Replace `t-checkpoint-wire-audit` with `t-checkpoint-roundtrip-test`: a property-based test that constructs a `WorkflowCheckpoint` with every dataclass field non-default, saves it, loads it, and asserts byte-equal round-trip. Failing the test means a field was added that the load path strips (the exact bug Part 2 identifies). This is one test file, runs in CI, fails loudly, and replaces the markdown.

**R2-S2 — Atomic O_EXCL lockfile**
**Summary answer:** ACCEPT-WITH-MODIFICATIONS — use `flock(LOCK_EX | LOCK_NB)`, not `O_EXCL`; the cited lesson is wrong but the mechanism is right.
**Rationale:** SDK Leg 11 #68 (the cited TOCTOU lesson) is about `exists()` + `stat()` in *single-process* file-reuse checks; its remedy is `try: stat() except OSError`. It does NOT support a cross-process lockfile. R2-S2's mechanism is appropriate for the actual problem (cross-process single-in-flight enforcement) but the citation is borrowed legitimacy from an unrelated lesson — the synthesis would be more honest reframed as "POSIX file locking is the canonical cross-process mutex." `O_EXCL` has known unreliability on NFS (the failure mode the synthesis flags); `flock(2)` is advisory but supported on NFSv4 client-side and provides automatic crash-recovery (the kernel releases the lock when the holding process dies — no PID-alive check, no audit-log dance, no fencing-token complexity). The "stale-lock detection via PID-alive check" the synthesis proposes is itself a TOCTOU race (process can die between check and reclaim) — `flock` eliminates that branch entirely.
**Assumptions:** The orchestrator and any concurrent operator invocation are on the same host (cap-dev-pipe is local). If the orchestrator is ever distributed across hosts, neither `O_EXCL` nor `flock` is sufficient and the design needs a real distributed lock (etcd, ZooKeeper, etc.) — that's out of scope and should be stated.
**Suggested improvements:** Specify `flock(LOCK_EX | LOCK_NB)` against a file at `<pipeline-output>/<plan-id>/.batch-orchestrator.lock`; the file contents are `{pid, batch_id, started_at}` for diagnostic logging only — not used for enforcement. On second-invocation: `flock` raises `BlockingIOError` immediately; the orchestrator reads the file contents (for the error message) and exits with `LockHeldError`. On orchestrator crash: kernel releases the lock; next invocation succeeds without ceremony. Drop the PID-alive check, drop the atexit dance (kernel handles it), drop the audit-log entry on reclaim.

### Part 2 — Phantom-API verification of plan §1 reuse table

The Forward Manifest precedent says: do not accept "file:line X exists" as proof the code does what the doc claims. Behavioral verification, row by row:

- **`_topological_sort()` at `shared.py:243-293`** — **VERIFIED.** DFS + white/gray/black at lines 252-274; cycle fallback to `list(tasks)` at line 291. Behavior matches the plan claim.
- **`wave_index` at `shared.py:64-65`** — **VERIFIED as seed-static.** Declared `wave_index: Optional[int] = None` at line 65; no SDK code path computes it. The CCD-400 check at `design.py:1167-1173` only *warns* when `wave_index is None` — it never assigns. Genuinely dormant.
- **`compute_lanes()` at `artisan_contractor.py:970-1026`** — **VERIFIED.** Union-find on `target_files` (lines 1000-1010) AND `depends_on` (lines 1013-1016) → connected components in input order. Behavior matches.
- **Absence of `compute_waves()`** — **VERIFIED PHANTOM.** `grep -rn 'compute_waves' /Users/neilyashinsky/Documents/dev/startd8-sdk/src/` returns zero matches. The function does not exist anywhere. The plan's correction of the brief is sound. **However:** `docs/design-princples/CONTEXT_CORRECTNESS_BY_DESIGN.md:47` SAYS `compute_waves()` partitions tasks using Kahn's topological sort, with a `~861` line anchor — **this load-bearing postmortem doc itself contains the same phantom-API claim the plan corrected.** Any future reader citing the postmortem will reintroduce the bug.
- **Checkpoint-v4 schema at `artisan_contractor.py:532-540` — fields `wave_assignments`, `completed_waves`, `current_wave`, `wave_resume_count`** — **PHANTOM / DORMANT (Forward-Manifest-class severity).** The docstring at lines 526-534 claims v4 adds these fields. The actual `WorkflowCheckpoint` dataclass at lines 521-550 declares **none of them**. The migration code at lines 783-786 calls `data.setdefault(...)` to populate these keys in the load-time dict; the validation code at lines 792-829 mutates them; then line 833-842 filters the dict against `{f.name for f in fields(WorkflowCheckpoint)}`, **stripping the wave_* fields it just populated**, and only the remaining dataclass fields reach `WorkflowCheckpoint(**data)` at line 849. The save path at lines 2424-2454 constructs the dataclass from the 13 declared fields only and `json.dumps(asdict(checkpoint))` at line 715 cannot serialize fields that aren't on the dataclass. **The wave_* fields never reach disk.** This is a load-side phantom worse than the Forward Manifest `getattr(..., None)` precedent — the dead-code migration appears to populate fields that the very loader silently filters out. **This blocks FR-5 (resume reuses checkpoint-v4 state), `t-resume-ledger` (which writes new batch-orchestration fields), R1-S6 (partition pinning in the ledger), R1-S7 (observability sink "extend checkpoint-v4 ledger"), R2-S1 (wire-audit assumes the fields exist), and R2-S4 (extends the ledger schema).** Repair before any of those increments are scoped: either add the wave_* fields to the dataclass (the documented intent) OR rewrite the v4 migration to use `metadata` / `context_snapshot` as the carrier and update the docstring. Either way, the §1 table row 6 must be rewritten and the plan's "REUSE as-is" claim for checkpoint-v4 is wrong.
- **`_detect_and_break_cycles()` at `queue.py:413-482` — "feature-serial mode only"** — **DRIFTED.** The function is called unconditionally at `queue.py:359` from `add_features_from_seed()` — no feature-serial gate, no mode check. The "feature-serial mode only" parenthetical in the plan and in R1-S1's task description is incorrect. The function runs every time tasks are loaded into the queue, regardless of mode. Implication: FR-2's "partitioner validates closure itself" is *already done* by the queue load — the partitioner is doing redundant work. Also implication: R1-S1's `t-reuse-verify` is verifying a property that doesn't hold (the function is not gated to feature-serial).
- **`build_shared_file_manifest` / `compute_lane_to_file_mapping` / `compute_critical_path_tasks` at `design_support.py:449-522` — "computed but UNUSED"** — **DRIFTED.** All three are called inside `phases/design.py` at lines 1145, 1162, 1178; results flow into `context["shared_file_manifest"]`, `context["lane_to_file_mapping"]`, and `_compute_ccd_task_metadata` calls at lines 1389/1765/2090/2215. They are *used* in production DESIGN. The plan's reuse claim ("invent nothing; reuse these as the partitioning substrate") is double-booking: if the BatchPartitioner calls them at plan-ingestion time AND the DESIGN phase calls them again per batch, the manifests are computed twice on different task sets (the partitioner sees the whole plan; DESIGN sees the batch's tasks). FR-8 must specify which call site is authoritative and which is derived.
- **`plan_ingestion_emitter.py:976` — `wave_metadata=None`** — **DRIFTED (line number).** The actual `wave_metadata=None` argument is at line 983, inside a 20-line `ContextSeed(...)` constructor call that begins at line 969. Minor; the seam exists. The plan's `:976` anchor will rot the first time someone edits the constructor.
- **`run-prime-contractor.sh --task-filter`** — **VERIFIED.** Exists at line 392; passes through to `scripts/run_prime_workflow.py` line 487; applied via skip-set at lines 740-760 with **no dependency revalidation**. The plan's claim is accurate at this level. (Important note: `add_features_from_seed` still calls `_detect_and_break_cycles` over the WHOLE seed at queue-load time — see the row above — so cycle-breaking still runs per `--task-filter` invocation, just not scoped to the filtered set.)
- **`CONTEXT_CORRECTNESS_BY_DESIGN.md:43-211`** — **EXISTS at a different path** (`docs/design-princples/` with the dir typo) and supports the "design-time context isolation, not scheduling" claim at lines 43-105 — but the doc itself contains the same `compute_waves()` phantom claim at line 47. Load-bearing for NFR-4 but tainted by its own internal drift.
- **`ARTISAN_RUN2_POSTMORTEM.md:92-130`** — **EXISTS at a different path** (`.cap-dev-pipe/design/`). Not at `docs/design/`.

**Blocker call-out (most important finding):** The checkpoint-v4 fields are phantom — **stop scoping FR-5 / `t-resume-ledger` / R1-S6 / R1-S7 / R2-S1 / R2-S4 until either (a) the wave_* fields are added to the `WorkflowCheckpoint` dataclass, or (b) the cross-batch ledger uses a new, separately-defined dataclass / file that doesn't pretend to extend a non-existent schema.** The Forward Manifest precedent (an entire FR was load-bearing on a non-existent method) is repeating here at a different load-bearing point.

### Part 3 — Cumulative complexity audit

**3a. In the docs (highest-leverage first).**

*Finding D1 — FR-4, FR-11, FR-12, R2-F1 (FR-13) are four faces of one mechanism.* All four are pre/post-conditions on entering or leaving a batch: FR-4 = post-batch validation; FR-11 = post-batch rollback on FR-4 failure; FR-12 = pre-batch seed-hash check; R2-F1 = pre-batch design-artifact check. Each carries its own diagnostic, override semantics, and audit trail. Collapse to one `BatchTransition` primitive with N preconditions and N postconditions, one diagnostic format, one audit record. Essential property preserved: every batch boundary is gated. Incidental property dropped: four named mechanisms × four override paths × four diagnostic templates × four sets of validation tests.

*Finding D2 — Persistence-layer sprawl across FR-5, FR-7, FR-12, R2-F2, R2-S1.* The capability proposes: checkpoint-v4 state (reused) + resume ledger (FR-5/FR-7) + provenance enrichment (R2-F2) + seed-hash pinning record (FR-12) + per-batch audit (R2-S1 matrix). These can be one artifact: a `batch_record_v1.json` written once per batch with all fields, read by all consumers. Essential property: each batch's outcome is durable and inspectable. Incidental: separate writers/readers, separate schemas, separate wire-audits. Especially given the Part-2 phantom finding — DON'T try to extend checkpoint-v4 at all; write a fresh artifact.

*Finding D3 — Vocabulary debt from a deferred parallel capability.* `wave_metadata`, `wave_index`, `lane_assignments`, `compute_lanes`, `wave_assignments`, `completed_waves`, `current_wave` — every one of these names comes from the dormant intra-run parallel effort. The MVP is sequential inter-run batching. Reusing the vocabulary forces every reader to mentally translate "wave" → "batch" and creates the R1 risk (re-enabling parallel by accident) at the language level. Rename the seam: emit `batch_metadata`, not into `wave_metadata`. The cost is one new field; the benefit is **R1 is solved by construction** — the dormant parallel path reads `wave_metadata` and gets `None`. See section 3c below.

*Finding D4 — Pre-Increment-0 task sprawl.* `t-reuse-verify` (R1-S1) + `t-checkpoint-wire-audit` (R2-S1) + the implicit `t-design-failure-gate` (R2-S3 if accepted) = three pre-Increment-0 tasks all doing the same thing in different shapes: "audit the existing SDK code before we touch it." The Forward Manifest pair accumulated three pre-0 tasks, one of which was obsoleted by the phantom-API discovery. Pattern smell. Consolidate to one task: `t-baseline-characterization` — a single test file that (a) pins primitive behaviors at their anchors, (b) round-trips a `WorkflowCheckpoint` with every dataclass field set, (c) asserts the cycle-breaker call site is unconditional. One artifact, one CI gate, one place to update.

*Finding D5 — R1-S5 quarantine is overstructured.* "Quarantine" implies a new state with its own lifecycle (entered, audited, eventually purged or restored). The essential property is: FR-10 inheritance must not read a failed batch's half-written files. The simpler form: maintain a `completed_batches` list in the batch record; FR-10 reads only from files associated with completed batches. Half-written files stay on disk (operator can inspect / delete); no quarantine state machine.

*Finding D6 — FR-10 trigger is over-specified.* "Batch k+1 contains a task whose `target_files` ∩ files-produced-by-prior-batches ≠ ∅" — but the orchestrator runs batches sequentially against a real filesystem; every prior batch's files are on disk. There is no scenario where batch k+1 should NOT see batch k's outputs. Simplify: batch k+1's design context always includes prior batches' code-on-disk and design-docs-on-disk, scoped to the manifest. The trigger is implicit in "Increment 2 is reached." This eliminates the trigger evaluation logic, the "what counts as ∩" edge cases, and one diagnostic path.

**3b. In the SDK code.**

*Finding C1 — `WorkflowCheckpoint` wave_* migration is dead code (`artisan_contractor.py:783-829`).* The `data.setdefault` calls populate fields the loader then filters out at line 842. The validation logic at 792-828 mutates those same fields, also filtered. ~40 lines of code that does nothing observable. Either add the fields to the dataclass (fixing the documented intent) or delete the migration. Ships inside Increment 0 (paired with `t-baseline-characterization` above; this is exactly the kind of finding that test would have caught earlier had it existed).

*Finding C2 — `lane_assignments=None` companion drift at `plan_ingestion_emitter.py:984`.* Right next to `wave_metadata=None` is `lane_assignments=None`. Same family of dormant fields, same risk of accidental cross-lane activation. If the rename in 3c is applied, this also goes away.

*Finding C3 — `wave_resume_count` is mentioned in the docstring but in no other file across the SDK.* `grep -rn "wave_resume_count" src/` returns only the docstring line. Even if the wave_* fields are added to the dataclass for one of the dormant parallel paths, this field has no writers anywhere. Delete from the docstring or implement.

*Finding C4 — `_detect_and_break_cycles` always-on call (`queue.py:359`).* Not necessarily a problem to fix, but it means FR-2's "partitioner validates closure itself" creates a *third* cycle-check (queue load + partitioner + per-batch). The simpler form: trust the queue-load check, drop the partitioner-level cycle check, document the dependency on `add_features_from_seed`'s post-load step.

*Finding C5 — `compute_lanes` is union-find with destructive parent flattening (`artisan_contractor.py:988-997`).* Idempotent on its inputs but mutates `parent` dict — running it twice on the same input from different call sites (partitioner + DESIGN phase, per Finding 3a) creates redundant computation that allocates a fresh `parent` dict each time. Cache the result by `tuple(sorted(t.task_id for t in tasks))` if performance matters; or accept the cost. Per-batch this is small.

*Finding C6 — `docs/design-princples/` (sic) directory typo.* Every reference to `CONTEXT_CORRECTNESS_BY_DESIGN.md` in any new doc inherits the typo. Rename the directory to `docs/design-principles/` and update references — one-time pain, perpetual readability win. Ships outside this capability.

*Finding C7 — `getattr(..., None)` pattern audit.* The Forward Manifest phantom-API used `getattr(forward_manifest, "validate_implementation", None)`. The SDK has 25+ similar patterns (see grep results), most defensive. The one at `prime_contractor.py:3792` (`getattr(self, "_forward_manifest", None)`) is the closest analog to the prior bug — verify it's wired to a present attribute. The pattern itself isn't fixable wholesale; the lesson is that any **plan-asserted** capability that hinges on a `getattr(..., None)` is a phantom-API candidate. Audit each load-bearing claim in this plan for one.

**3c. Vocabulary debt — concrete renames.**

| Inherited name | Source | Proposed batch-native name | Why |
|---|---|---|---|
| `wave_metadata` | dormant parallel | `batch_metadata` (new seed field) | Eliminates R1 by construction — the parallel path reads `wave_metadata`, gets `None`, cannot activate |
| `wave_assignments` | dormant ckpt field | `batch_assignments` in `batch_record_v1.json` | New artifact; no overlap with parallel state |
| `completed_waves` | dormant ckpt field | `completed_batches` | Same |
| `current_wave` | dormant ckpt field | `current_batch` | Same |
| `compute_lanes()` | used as cohesion primitive | keep — it's correctly named for what it does | No rename; it really does compute lanes |
| `_topological_sort` | used as ordering primitive | keep — correctly named | No rename |

**3d. Multiple-mechanism collapse opportunities.**

| Collapse target | Subsumes | Collapsed shape |
|---|---|---|
| `BatchTransition` | FR-4 + FR-11 + FR-12 + R2-F1(FR-13) | One pre/post-condition gate with N checks; one diagnostic format; one audit trail entry; one override path. The check list grows as needs grow; the mechanism does not. |
| `batch_record_v1.json` | FR-5 ledger + FR-7 provenance + FR-12 hash + R2-F2 enrichment + R2-S1 wire-audit | One artifact per batch with all fields; one writer; one reader; round-trip test instead of matrix. |
| `t-baseline-characterization` | t-reuse-verify + t-checkpoint-wire-audit + t-design-failure-gate's preamble | One test file; pins anchors + round-trips the checkpoint + asserts cycle-break call site. CI gate. |
| FR-10 inheritance | R2-F3 typed manifest, R1-S5 quarantine state | Fixed small artifact-kind list (code, design docs); read-only-from-completed; no extensible registry, no quarantine state. |

### Part 4 — Essential MVP distillation

The user's headline ask. After Brooks's essential-vs-accidental cut, the minimum viable MVP is:

- **Essential-1: Partition** (subsumes FR-1, FR-2, FR-8) — Given a seed, produce an ordered list of dependency-closed batches. Lane cohesion preserved. Deterministic.
- **Essential-2: Sequential execution** (subsumes FR-3, NFR-1) — For each batch, run prime-contractor with `--task-filter`. Never two in flight.
- **Essential-3: Gated transition** (subsumes FR-4, FR-11, FR-12, R2-F1) — `BatchTransition` gate runs N pre-checks and M post-checks at each boundary. Default checks: seed-hash unchanged (pre), declared `target_files` non-empty + plan-specified acceptance (post). Override path: audited via Essential-5.
- **Essential-4: Resume from disk** (subsumes FR-5) — On restart, identify the highest-numbered batch whose post-checks passed; resume from the next. State on disk in `batch_record_v1.json`, not in checkpoint-v4.
- **Essential-5: Per-batch record** (subsumes FR-6, FR-7, R2-F2 reduced, R1-S7) — `batch_record_v1.json` writes per batch: `{batch_id, task_ids, seed_hash, config_hash, cost_usd, status, gate_result, override_record}`. One writer, one schema, round-trip-tested.
- **Essential-6: Inter-batch context inheritance** (subsumes FR-10, NFR-4, R2-F3 reduced) — At each batch's DESIGN phase, inject prior-batches' code-on-disk + design-docs-on-disk, scoped via `compute_lanes`+`build_shared_file_manifest`. Missing-artifact is blocking. Read-only from completed batches (Essential-4's `batch_record_v1`).

**That's 6 essential requirements.** Current count: 12 FRs (FR-1..FR-12) + 4 NFRs + 4 R2-Fs (R2-F1..R2-F4) + 4 increments + 8 R1-S/8 R1-F applied. Compression ratio for the headline FR count: 6 essential vs ~16 current (12 FR + 4 R2-F) ≈ **~63% deletable**.

**Disposition of current FRs / R2 items / tasks under this distillation:**

| Item | Disposition |
|---|---|
| FR-1 | FOLD-INTO-Essential-1 |
| FR-2 | FOLD-INTO-Essential-1 (closure + cohesion as one) |
| FR-3 | FOLD-INTO-Essential-2 |
| FR-4 | FOLD-INTO-Essential-3 (one face of the gate) |
| FR-5 | FOLD-INTO-Essential-4 (resume off disk record, NOT checkpoint-v4) |
| FR-6 | FOLD-INTO-Essential-5 (cost is a record field, not a separate mechanism) |
| FR-7 | FOLD-INTO-Essential-5 |
| FR-8 | FOLD-INTO-Essential-1 (reuse as substrate is implicit) |
| FR-9 | DELETE (iterative delivery is a process, not a requirement) |
| FR-10 | FOLD-INTO-Essential-6 |
| FR-11 | FOLD-INTO-Essential-3 (post-gate disposition is one of the gate's outcomes) |
| FR-12 | FOLD-INTO-Essential-3 (seed-hash check is one pre-check) |
| NFR-1 | FOLD-INTO-Essential-2 (single-in-flight implies no regression) |
| NFR-2 | KEEP as cross-cutting (determinism applies to Essential-1 and Essential-5) |
| NFR-3 | DELETE (reviewability is a value, not a testable requirement) |
| NFR-4 | FOLD-INTO-Essential-6 |
| R2-F1 (FR-13) | DELETE — subsumed by Essential-3's post-check on declared `target_files` |
| R2-F2 | FOLD-INTO-Essential-5 (reduced field set: drop `quality_summary`, scope fingerprints to `target_files`) |
| R2-F3 | DEFER to Increment 3 (typed manifest is for intra-batch parallelism, if ever) |
| R2-F4 | DELETE — replace with project-state detection inside Essential-3 |
| R2-S1 | DELETE the matrix; FOLD-INTO `t-baseline-characterization` |
| R2-S2 | KEEP, MODIFIED to `flock(LOCK_EX | LOCK_NB)`; FOLD-INTO Essential-2 |
| R2-S3 | DELETE (consequence of R2-F1 delete) |
| R2-S4 | FOLD-INTO Essential-5 implementation |
| R2-S5 | DEFER (consequence of R2-F3 defer) |
| R2-S6 | DELETE — replace with project-state detection |

### Part 5 — New suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | Architecture | critical | Replace the "extend checkpoint-v4 ledger" approach (FR-5, FR-7, R1-S6, R1-S7, R2-F2, R2-S1, R2-S4) with a new artifact `batch_record_v1.json` written per batch under `<output>/batches/<batch_id>/`. Define its schema as the contract. Do NOT extend `WorkflowCheckpoint` — the existing v4 wave_* migration is dead code (Part 2 finding); piggybacking on it inherits a phantom that the plan already corrected once. | The Part-2 audit shows the wave_* fields are dropped silently by the loader's known_fields filter. Writing batch-orchestration state into the same dataclass continues the dormancy. A fresh artifact has no carrying capacity for inherited bugs, can be schema-tested in isolation, and uses batch-native vocabulary (Finding 3c). | New §5 component "Batch record"; rewrite FR-5, FR-7; collapse R2-F2/R2-S1/R2-S4 into the schema. | Property-based round-trip test on the schema; CI gate on schema drift. |
| R3-F2 | Architecture | high | Rename the partition emitter field at `plan_ingestion_emitter.py:983` from `wave_metadata` to `batch_metadata`. Leave `wave_metadata=None` in place (parallel path keeps reading `None`); add `batch_metadata=<partition>` as the new sequential carrier. | Risk R1 ("accidentally re-enabling parallel") is currently mitigated behaviorally (single-in-flight + assert flag stays None). Renaming makes the mitigation structural — the parallel path literally reads from a different field. The cost is one field rename + one plumbing pass through `seeds/models.py`, `seeds/builder.py`, `phases/design.py`. | §5 components; new task in Increment 1; deprecate `wave_metadata` in v0.5 cycle. | Test: populate `batch_metadata`; assert `wave_metadata` remains `None`; assert no DESIGN-phase code path reads `batch_metadata` as if it were `wave_metadata`. |
| R3-F3 | Risks | high | Add a load-bearing-doc verification protocol: any new design doc that cites a function or file:line as evidence MUST be paired with a behavioral test (one assert per cite) that runs in CI. The protocol is: "if you put `file.py:NNN` in a requirements doc, a test must import that symbol and assert one observable behavior." | The Forward Manifest precedent + the checkpoint-v4 phantom + the `compute_waves` claim in CONTEXT_CORRECTNESS_BY_DESIGN.md demonstrate that file:line citations decay or are wrong from day one. Treating cited code like cited statutes (verified against the actual code) is the cheapest preventative. | New NFR-5 (or a doc-quality appendix). | Lint: parse each docs/design/*.md for `\.py:\d+` patterns; for each, check that `tests/design_verification/test_<doc-stem>.py` imports and asserts the cited symbol. |

_Status: **TRIAGED 2026-05-31 → ADOPTED as the canonical MVP.** Part-2 phantom-API findings behaviorally re-verified against live SDK code (see R4 note below). R3-F1 (batch_record_v1, not checkpoint-v4), R3-F2 (batch_metadata rename), R3-F3 (doc-cite verification) all APPLIED. Part-4 essential distillation adopted: the 6 Essential requirements replace the FR-1..FR-12 / R2-F surface for build purposes (the FRs remain as the rationale/traceability layer). The Part-2 checkpoint-v4 blocker is resolved by R3-F1 (the existing `BatchLedger` in `batch_postmortem.py` already implements the fresh artifact)._

---

## R4 — Behavioral Verification & Triage Disposition (2026-05-31)

**Reviewer:** claude-opus-4-8 (1m). **Scope:** behaviorally verify R3's load-bearing `file:line` claims against the live SDK before adopting (R3-F3's own protocol applied to R3 itself), then disposition R2 + R3 and lock the build spec.

**Verification results (all R3 claims CONFIRMED against current `src/`):**

| Claim | Verdict |
|---|---|
| Checkpoint-v4 `wave_*` fields phantom — `WorkflowCheckpoint` dataclass declares 13 fields, none `wave_*`; migration `setdefault`s them (`artisan_contractor.py:783-786`), then line 842 filters against `known_fields` and strips them before `WorkflowCheckpoint(**data)`. Never reach disk. | ✅ CONFIRMED — hard blocker for FR-5 "reuse checkpoint-v4 as-is"; resolved by R3-F1. |
| `_detect_and_break_cycles()` called unconditionally at `queue.py:359` (not "feature-serial only") | ✅ CONFIRMED (drift) — FR-2 closure validation is partly redundant with queue-load. |
| `build_shared_file_manifest`/`compute_lane_to_file_mapping`/`compute_critical_path_tasks` are USED in `phases/design.py:1145/1162/1178` (not dormant) | ✅ CONFIRMED (drift) — FR-8 must name the authoritative call site (double-booking risk). |
| Emitter seam at `plan_ingestion_emitter.py:983-984` (`wave_metadata=None`, `lane_assignments=None`), not `:976` | ✅ CONFIRMED — v1.1 anchor stale; R3 anchor correct. |

**Key discovery (strengthens R3-F1/R3-S2):** the fresh artifact R3 proposes **already exists and is wired**. `contractors/batch_postmortem.py` defines `BatchLedger` / `TaskLedgerRecord` / `RunSnapshot` with `compute_seed_checksum()` (FR-12 pinning), per-task status + cost history (FR-6/FR-7), atomic `save_ledger()`, and `load_or_create_ledger()` that starts a new batch on seed-hash change. cap-dev-pipe wires it via `prime-post-run.py --batch-ledger-dir` + `run-prime-contractor.sh`. The pilot's `batch-ledger.json` is its output. So `t-batch-record-writer` is ~built; Increment 0 reuses it rather than building or extending checkpoint-v4.

**Disposition summary** (full rows in Appendix A/B):
- **APPLIED:** R2-F2 (modified — keep `config_hash`+`seed_fingerprint`, scope output fingerprints to declared `target_files`, drop `quality_summary`); R3-F1; R3-F2; R3-F3 (folds into `t-baseline-characterization`).
- **REJECTED:** R2-F1/FR-13 (within-run resume-cache lesson is shape-incompatible with the cross-batch seam; subsumed by the gate's post-check on declared `target_files`); R2-F3 (typed manifest — premature for a 2-type universe; deferred to Increment 3); R2-F4 (batch-index is the wrong discriminator; replaced by project-state gate detection).
- **ADOPTED:** Part-4 essential distillation as the canonical build surface (6 Essentials / 6 tasks).

## Areas Substantially Addressed

| Area | Accepted (R1) | Addressed (≥3)? |
|------|---------------|-----------------|
| Validation | 2 | — |
| Data | 2 | — |
| Risks | 2 | — |
| Ops | 1 | — |
