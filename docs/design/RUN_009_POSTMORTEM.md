# False-PASS on a Self-Wiped Foundation — Postmortem & Remediation (RUN_009)

**Date:** 2026-06-01 (corrected 2026-06-01 post-review — see §1 attribution note)
**Trigger incident:** prime-contractor run `run-009-20260601T0045` (attempt-2 via
`./run-prime-contractor.sh --fresh`) reported **PASS verdict / score 1.00 /
13 of 13 features succeeded / $2.22 cost**, but the project root was missing
the entire 9-file M1 ship set the plan declared **out of scope and immutable**,
and the run shipped **7 files that import from modules that do not exist on
disk** (5 invented `@/lib/prisma` imports; 1 invented `@/lib/logger`; 1
reference to the absent `@/lib/db`). Net functional delivery against M2-redo
+ M3 is **0 of 13 features as a working system** — the app cannot be
installed (no `package.json`), cannot be built (no `tsconfig.json`), and
every M3 feature imports a path that doesn't resolve.
**Headline finding:** the Fix 1 + Fix 2 remediation pass landed only the
**intra-batch sibling-output portion of cross-feature inheritance** ("Mode A"),
which works (4 distinct producer/consumer chains correctly inherited in this
run — real progress over RUN_008). It did **not** cover the
**pre-existing-upstream portion** ("Mode B"). Independently of Fix 1, the
`ForwardFileSpec` schema has **no field distinguishing a regeneration target
from a pre-existing upstream anchor** (both have identical keys), and tasks
carry **no `target_files`** — so `clean-prior-run.sh --fresh` cannot tell
anchors from targets and wipes every entry in `forward_manifest.file_specs`
during whichever run lists them. **And the Fix 2 classifier signatures are
still not wired** — a run with seven unresolvable imports and a missing
`package.json` reported a perfect verdict.
**Cross-run trajectory:** verdict score went **0.94 → 0.99 → 0.00 → 1.00**
across RUN_007 / RUN_008 / RUN_009-attempt-1 / RUN_009-attempt-2 while actual
working-as-a-system delivery went **6 → 0 → 0 → 0**. The score is now
**inversely correlated** with delivery. RUN_009 attempt-2 is the cleanest
demonstration: the highest reported score on the worst-delivery run.

---

## 1. What happened

Run-009 was the first pipeline invocation after the user implemented the
**Fix 1 (intra-batch inter-feature context inheritance)** and **Fix 2
(cross-file integrity classifier signatures)** specced in
`RUN_008_CROSS_FEATURE_INCOHERENCE_POSTMORTEM.md`. The active plan was the
new `typescript-plan.md` (scope: M2 consumer regeneration + M3 AI engine; 6
plan features expected, which the pipeline expanded into 13 `PI-*` tasks).

**Attempt-1** halted at PI-001 on a pre-merge `tsc --noEmit` check failing
with `Cannot find module 'zod'` — a tooling artifact (the temp-file copy at
`/var/folders/.../tmp4r0z9dfv.ts` had no `node_modules`; the project's
`node_modules/zod` was present and the on-disk Zod file would have compiled
fine in the project context). Pipeline reported FAIL 0.00, stage
`unknown / unknown(1)`. See `RUN_009_IN_FLIGHT_FINDINGS.md` for the
attempt-1 details and the snapshot location.

**Attempt-2** (analysed here) is the re-invocation of `run-prime-contractor.sh`
against the same seed via `--fresh`. The tooling issue from attempt-1 was
either repaired or sidestepped; the pipeline progressed through all 13 tasks
and emitted a PASS verdict.

### Attribution correction (post-review, 2026-06-01)

A first reading of this run attributed the missing M1 ship-set to
run-009 attempt-2's `--fresh` invocation. Verification overturned that claim:

- `git ls-files prisma/ package.json tsconfig.json next.config.mjs lib/db.ts
  lib/env.ts app/layout.tsx app/page.tsx .env.example` → **empty.** None of
  the M1 anchors were ever git-tracked; `git status` shows `prisma/` as `??`.
- The run-009 seed's `forward_manifest.file_specs` has exactly **13
  entries** — the M2/M3 task targets only. **None of `prisma/schema.prisma`,
  `package.json`, `tsconfig.json`, `next.config.mjs`, `.env.example`,
  `lib/db.ts`, `lib/env.ts`, `app/layout.tsx`, or `app/page.tsx` is in the
  run-009 seed.** Run-009's `--fresh` cannot have removed them via the
  file_specs loop — they weren't in the loop.
- Earlier runs (run-003 / run-004 era, when those files WERE plan targets
  for M1 generation) had ~15 entries in `forward_manifest.file_specs` that
  included these files. A `--fresh` invocation in one of those earlier runs
  removed them. Because they were never committed to git, the removal was
  permanent.

So the correct attribution chain is: **the M1 ship set was wiped by some
earlier `--fresh` (when those files were legitimate regeneration targets) and
never restored, because they were never git-committed.** By the time run-009
attempt-2 started, the project root was already missing those 9 files. The
run-009 verdict's PASS is wrong for a different reason — the 7 invented
imports and the missing prerequisite files — not because this run's
`--fresh` did the wiping.

The deeper structural gap behind this is the load-bearing finding and is
analysed as Gap A below.

| Order | Feature | Target file(s) | Reported | Cost | Reality |
|-------|---------|-----------------|----------|------|---------|
| PI-001 | Value Model Zod schemas | `lib/value-model.ts` | ✅ | $0.1356 | 108-line thin Zod, **same shape as run-008** (invented `bio`, missing ~11 Prisma fields/model, no provenance, no join-table schemas) |
| PI-002 | Profile API route | `app/api/profile/route.ts` | ✅ | $0.1070 | Imports `@/lib/db` (wiped from disk) + `pino` (not in deps) |
| PI-003 | Profile capture UI | `app/profile/page.tsx` | ✅ | $0.1893 | 417 lines; likely invents form fields again (not audited) |
| PI-004 | ProofPoint list/create API | `app/api/proof-points/route.ts` | ✅ | $0.2217 | Imports `@/lib/prisma` (**invented**; file doesn't exist) |
| PI-005 | ProofPoint item API | `app/api/proof-points/[id]/route.ts` | ✅ | $0.1290 | 200 lines; same Prisma-client import pattern |
| PI-006 | ProofPoint library UI | `app/proof-points/page.tsx` | ✅ | $0.1545 | 637 lines |
| PI-007 | AI service wrapper | `lib/ai/service.ts` | ✅ | $0.2186 | 427 lines, real Anthropic wrapper; imports `@/lib/prisma` (**invented**) + `pino` (not in deps) |
| PI-008 | Extract pass impl | `lib/ai/extract.ts` | ✅ | $0.1629 | 290 lines; imports `@/lib/prisma` (**invented**) |
| PI-009 | Extract API route | `app/api/ai/extract/route.ts` | ✅ | $0.0950 | Clean — only imports `@/lib/ai/extract` (real) |
| PI-010 | Extract UI | `app/extract/page.tsx` | ✅ | $0.2646 | 633 lines |
| PI-011 | Artifact generation impl | `lib/ai/artifacts.ts` | ✅ | $0.1600 | 191 lines; imports `@/lib/prisma` (**invented**) |
| PI-012 | Artifacts API route | `app/api/ai/artifacts/route.ts` | ✅ | $0.1344 | Imports `@/lib/prisma` (**invented**) + `@/lib/logger` (**invented**) |
| PI-013 | Artifacts UI | `app/artifacts/page.tsx` | ✅ | $0.2489 | 637 lines |

**The pipeline's own bookkeeping says 13/13 success / score 1.00.** Postmortem
`pipeline_attribution: []`, `cross_feature_patterns: []`,
`observability_repairs: {}`, `kaizen-suggestions.json: { "suggestions": [] }`
— every diagnostic channel is empty.

Reality at the same instant:

| Layer | State |
|-------|-------|
| M1 ship set (`package.json`, `tsconfig.json`, `next.config.mjs`, `prisma/schema.prisma`, `.env.example`, `lib/env.ts`, `lib/db.ts`, `app/layout.tsx`, `app/page.tsx`) | **9 of 9 MISSING** — wiped by an earlier run's `--fresh` when those files were seed targets; never restored because never committed to git (see attribution note above) |
| `lib/db.ts` (Prisma client singleton) | MISSING |
| `lib/prisma.ts` (invented import target) | Never existed |
| `lib/logger.ts` (invented import target) | Never existed |
| `pino` (dependency) | Not declared in (now-missing) `package.json` |
| `lib/value-model.ts` field set | Same thin shape as RUN_008 — Profile has `{id, name, title, bio, createdAt, updatedAt}` against a Prisma model with 17 fields (none of which is `bio`) |
| `npm install` | Cannot run — no `package.json` |
| `npx tsc --noEmit` | Cannot run — no `tsconfig.json` |
| `npx prisma generate` | Cannot run — no `prisma/schema.prisma` |

**0 of the 13 generated features deliver as a working system.**

---

## 2. The gaps this incident exposes

Four structural gaps. Each is independently true; together they explain how a
0-functional-features run earned a 1.00 score.

### Gap A — `ForwardFileSpec` schema cannot distinguish regeneration targets from pre-existing upstream anchors

The structural defect underneath this run's wipe is at the **schema level,
not the cleanup-script logic level**: a `ForwardFileSpec` entry has the same
shape regardless of whether the file is a regeneration target for this
batch or a pre-existing upstream anchor the batch reads from. The keys are
identical:

```
file, language, elements, imports, dependencies, convention_provenance
```

Tasks in the seed carry **no `target_files`** declaration that would name
exactly which file_specs entries are this task's regeneration targets.
`clean-prior-run.sh` was written against this schema: it iterates every
key in `forward_manifest.file_specs` and `rm`s the corresponding path.
**This is the only signal the script has.** It cannot tell anchors from
targets because the schema doesn't encode the distinction. Whichever run
puts an M1 anchor into `file_specs` (as a real target in that run, e.g.
during M1 generation), the next `--fresh` invocation legitimately removes
it. The plan's "Non-Goals" / "out-of-scope" prose is a documentation
artifact; nothing downstream consults it.

In run-009 specifically, the M1 anchors were already missing before this
run started (see attribution note in §1). But the underlying gap is what
made them removable in the first place during some earlier run, and what
makes them removable in every future run that lists them as targets.

The plan's docs/PLAN.md milestone sequence (M1 → M2 → M3 → M4 → M5 → M6)
presupposes incremental delivery — each batch builds on the prior batch's
on-disk output. Today the pipeline schema cannot represent "this file is
an anchor for this batch, not a target." Result: any incremental milestone
batch can wipe its predecessor's delivery merely by appearing in the same
file_specs, and the only durable user-side defense is committing every
intermediate output to git (which is fragile — see §5 strategic insight).

### Gap B — Fix 1 covers Mode A (intra-batch sibling) but not Mode B (pre-existing upstream)

Categorizing every `@/lib/*` import across the 13 generated files:

| Import | Source | Result |
|--------|--------|--------|
| `@/lib/value-model` | producer was F-101 (PI-001) in this batch | ✅ All 2 consumers used the correct path |
| `@/lib/ai/service` | producer was F-104 (PI-007) in this batch | ✅ Both consumers used the correct path |
| `@/lib/ai/extract` | producer was F-105 (PI-008) in this batch | ✅ Consumer used the correct path |
| `@/lib/ai/artifacts` | producer was F-106 (PI-011) in this batch | ✅ Consumer used the correct path |
| `@/lib/db` | pre-existing M1 ship set (now wiped by Gap A) | 🔶 1 file used the correct path; rest invented |
| `@/lib/prisma` | invented — file never existed | ❌ 5 files independently picked this path |
| `@/lib/logger` | invented — file never existed | ❌ 1 file |

**Mode A (intra-batch sibling-output inheritance) works** — 4 distinct
producer/consumer chains, every consumer correctly inherited the producer's
emitted module path. This is genuine progress over RUN_008's three-invented-names
failure pattern.

**Mode B (pre-existing-upstream inheritance) does not** — 5 features that
needed the Prisma client all invented the path `@/lib/prisma` instead of
inheriting the (pre-existing-before-the-batch) `@/lib/db` path. The choice was
stable across all 5 — same wrong name, not random LLM noise — which suggests
**the drafter has no signal at all about the project's existing module
inventory and falls back to a canonical guess** (`@/lib/prisma` is the
"obvious" name for a Prisma client; the project just doesn't use it).

Compounded with Gap A: even if Mode B were perfectly implemented, the
upstream files were wiped at run start, so there'd be nothing on disk for
Mode B to inherit from anyway. The two gaps reinforce each other.

### Gap C — Fix 2 classifier signatures are not wired (third time named)

The cross-file integrity classifier signatures specced as RUN_008 Fix 2 (and
the empty-stub signatures specced as RUN_007 Fix 2 before that, and the
postmortem classifier specced as RUN_003 Fix 3 before that) **have not
shipped**.

This run produced, conservatively:
- **5 unresolvable-import violations** on `@/lib/prisma`
- **1 unresolvable-import violation** on `@/lib/logger`
- **1 unresolvable-import violation** on `@/lib/db` (the file was wiped)
- **2 missing-dependency violations** for `pino` (not in any deps manifest)
- **9 missing-file violations** for the wiped M1 ship set (every file
  referenced by the generated code but not on disk)
- **1 Prisma↔Zod symmetry violation** (the thin Zod still diverging from the
  canonical Prisma model — Prisma was wiped, so the symmetry check would
  have flagged "Prisma absent, cannot verify symmetry" as its own signature)

Every one of these is the canonical RUN_008 Fix-2 signature shape. **None
fired.** The postmortem's `pipeline_attribution` is `[]`. `kaizen-suggestions`
is `[]`. `cross_feature_patterns` is `[]`. Three remediation passes named
this fix; it remains the most-deferred, highest-leverage SDK debt in this
session.

### Gap D — Verdict scoring is now inversely correlated with delivery

Tracking across the four runs in this session:

| Run | Reported verdict | Score | Working features (as a system) |
|-----|------------------|-------|--------------------------------|
| RUN_007 | PASS | 0.94 | ~6 of 16 |
| RUN_008 | PASS | 0.99 | 0 of 16 |
| RUN_009 attempt-1 | FAIL | 0.00 | 0 of 1 (halted) |
| RUN_009 attempt-2 | **PASS** | **1.00** | **0 of 13** |

**The pipeline reports its highest-ever score on the worst-delivery run in
this session.** Each RUN_007 / RUN_008 fix that closed a visible failure mode
without wiring Fix 2 made the verdict more confident on the next run's
different failure mode. The trajectory is monotone: visible failure modes
get closed; the classifier remains blind; the verdict score moves up while
working-feature count moves down (or stays at zero).

A reader of the run-009 postmortem-summary.md (PASS 1.00 / 13 of 13
successful / observability scores 100% across the board / no Kaizen
suggestions / no cross-feature patterns) would conclude this was the best
run yet. The only working code from the run is the four Mode-A inheritance
paths between same-batch features — which doesn't help when the system
depends on pre-existing files that the pipeline wiped.

---

## 3. How to close the gaps

Three fixes, ordered by leverage and increasing scope. **None are new** —
they are the cumulative debt from RUN_003 / RUN_007 / RUN_008 reaching the
point where every subsequent run will reproduce the same failure shape
until they ship.

### Fix 1 — Schema-level target/anchor distinction on `ForwardFileSpec` (highest leverage, smallest blast radius)

**What:** add a structural field that distinguishes "this batch will
regenerate this file" from "this batch reads from this file as a
pre-existing upstream." Two equivalent shapes either work; either is
fine, but the choice should be picked deliberately:

- **Schema-level field:** add `kind: "target" | "anchor"` (or
  `regenerates: bool`) to `ForwardFileSpec`. Every entry declares which
  role it plays in this batch.
- **Task-level declaration:** add `target_files: list[str]` to each task,
  naming exactly which `forward_manifest.file_specs` paths this task
  regenerates. Any file in `file_specs` not named as a target by any task
  is implicitly an anchor.

The producer side (plan-ingestion / seed-emitter) populates the
distinction from the plan: every file the plan body declares as a
deliverable for a task is a target; every other file referenced (typically
in "Prerequisites" / "Non-Goals" sections or as an inheritance dependency
in the Implementation contract) is an anchor.

The consumer side (`clean-prior-run.sh`) iterates only over targets, never
over anchors. Spec_builder.py + the Mode B inheritance work (Fix 2 below)
can read anchor entries to inject pre-existing upstream content into the
generating feature's context.

The smallest concrete diff that proves the shape: add `kind` to the
dataclass with default `"target"` for backwards compat; have
`clean-prior-run.sh` skip entries where `kind == "anchor"`; have the
seed-emitter set `kind = "anchor"` for files mentioned in the plan but
not declared as a deliverable for any task.

**Why:** the schema-level distinction is the smallest structural change
that gives every downstream tool (`clean-prior-run.sh`,
`spec_builder.py`, postmortem classifier, future Plan Batch Orchestration
FR-10) a single shared signal for "this is an anchor, not a target." A
plan-marker + heuristic-cleanup approach (the first cut of this fix in an
earlier draft of this postmortem) is fragile: any prose reference to a
filename anywhere in the plan can be re-derived as a target by
enrichment, defeating the marker. A schema-level field is the durable
fix.

**Acceptance / validation:**

- Schema migration: every existing `ForwardFileSpec` consumer continues to
  work (default `kind="target"` preserves current behavior).
- A reproduction: a seed with 13 target entries + 9 anchor entries (the
  M1 ship set) — `clean-prior-run.sh --fresh` leaves the 9 anchors on
  disk and removes only the 13 targets.
- Negative test: a seed with all targets (no anchors) behaves as today.
- Spec_builder.py (when Fix 2 lands) can iterate anchors and inject their
  content into the generating feature's context — that's the Mode B win
  that closes Gap B.

**Closes:** Gap A directly. Provides the structural pre-condition for
Fix 2 (Mode B inheritance has anchors to read from).

### Fix 2 — Inter-feature inheritance extends to pre-existing project files (Mode B)

**What:** the same context-injection mechanism that propagates F-101's
emitted `lib/value-model.ts` path to F-102/F-103's spec_builder context MUST
also propagate **the contents of pre-existing project files** that the
generating feature is likely to import from. Detection heuristic: any file
in the project root that exports a symbol whose name appears in the
generating feature's task description, target file's expected imports, or
plan-document text. Plus a small registry of "canonical project files"
(by path pattern: `lib/db.ts`, `lib/env.ts`, `prisma/schema.prisma`,
`package.json`) that always get propagated when the batch touches the
relevant scope.

Bound the token cost the same way Fix 1 (Forward Manifest) bounds it:
inject only the file content, not summaries; cap by import-relevance to the
generating feature; let `enforce_prompt_budget` evict lower-priority
sections if the inheritance set is large.

**Why:** Gap B's 5-files-invented-`@/lib/prisma` pattern is the same root
cause as the RUN_008 Gap-A pattern, applied to the pre-existing-upstream
seam instead of the intra-batch-sibling seam. Fix 1 (in the Forward
Manifest postmortem) closed the single-target-file case; Fix 1 (RUN_008
postmortem) closed the intra-batch sibling case (now confirmed working in
this run); this fix closes the third case.

**Acceptance / validation:**

- A regression test reproducing this run: a synthetic seed where M1 ship-set
  files are on disk + an M2/M3 feature that imports a Prisma client; assert
  the emitted import is `@/lib/db` (the existing path), not `@/lib/prisma`.
- A symmetric test for `lib/env.ts`, `prisma/schema.prisma` field set,
  `package.json` dependencies (next/react/zod present).
- Negative test: feature whose generation does not involve any pre-existing
  upstream file — context budget for this feature is unchanged.

**Closes:** Gap B directly. Reduces Gap D (cross-file failure rate drops,
so verdict accuracy improves).

### Fix 3 — Wire the cross-file integrity classifier signatures (THIRD time named)

**What:** ship the postmortem-classifier signatures specced as RUN_007 Fix 2
and refined as RUN_008 Fix 2. At minimum:

1. **Unresolvable-import signature.** For every `*.ts` / `*.tsx` in the
   generated set, parse import declarations; assert every `@/`-prefixed
   path resolves to a file in the generated set or a pre-existing project
   file. **Would have caught 7 of this run's broken imports.**
2. **Missing-dependency signature.** For every external import (e.g.
   `import pino from "pino"`), assert the package is declared in
   `package.json`. **Would have caught the pino case.**
3. **Missing-prerequisite signature.** For every project-level file
   referenced by generated code that is expected to exist before generation
   (e.g. `prisma/schema.prisma`, `package.json`), assert it exists on disk.
   **Would have caught the wiped-ship-set case end-to-end.**
4. **Prisma↔Zod symmetry signature** (from RUN_008 Fix 2). For every Prisma
   `model` and matching Zod schema, assert field name sets and type classes
   agree. **Would have caught the thin Zod / `bio` invention.**

Each signature match marks the feature failed regardless of syntax-check
outcome, classifies the pipeline stage as **`drafter / cross-feature
contract`**, attributes root cause to the specific signature, and emits at
least one Kaizen suggestion citing the violation.

**Why:** without Fix 3, every run's verdict is decorative. The current
classifier surface returns "PASS" on a run that wiped its own foundation
and shipped 7 broken imports. **Until Fix 3 is wired, no run's verdict
should be trusted**, including the verdict on a run that would test Fix 1
or Fix 2. This is the load-bearing item for the entire postmortem feedback
loop.

**Acceptance / validation:**

- A reproduction of run-009 attempt-2's exact output: the postmortem
  classifier MUST emit at least 7 unresolvable-import findings, a missing-
  prerequisite finding for the wiped M1 ship set, and a Kaizen suggestion
  per signature.
- Reproduction of run-008's output: same signatures fire on the run-008
  defects (the symmetric Prisma↔Zod failure shape).
- A baseline reproduction of a hypothetical clean run (no defects): zero
  findings, no false positives.

**Closes:** Gap C directly. Resolves Gap D as a side-effect — once
classifier signatures fire, the verdict score actually reflects delivery
quality.

---

## 4. Why this matters beyond run-009

- **Same root cause, fifth layer.** The "drafter / micro-prime path invents
  structure when no contract is available" rule has now surfaced at:
  RUN_003 (single-file structure, framework-config registry case), RUN_007
  (single-file structure, SIMPLE-tier template fallback case), RUN_008
  (cross-file structure, intra-batch inter-feature case), RUN_009 (cross-file
  structure, pre-existing-upstream case), and the parallel-effort
  inter-batch case (PLAN_BATCH_ORCHESTRATION FR-10). Each fix closes a
  deflection path; the underlying rule survives in the next layer.
  **The fix shape generalizes** to "propagate the available contract from
  wherever it exists into the generating feature's design context" — Fix 1
  in this postmortem is the same mechanism Plan Batch Orchestration FR-10
  defines, applied to a different seam.
- **`--fresh` is structurally incompatible with multi-batch delivery.**
  The docs/PLAN.md milestone sequence (M1 → M2 → M3 → M4 → M5 → M6)
  presupposes that each batch builds on the prior batch's delivered work.
  `--fresh` wipes the prior delivery. Without Fix 1 from this postmortem,
  the entire batch-orchestration roadmap (single-batch-per-milestone) is
  unworkable — every batch's first action would be to delete its
  predecessor.
- **The score-vs-reality inversion is the most diagnostic signal in this
  session.** A pipeline whose verdict tracks delivery quality is one
  whose failure modes are exposed to the learning loop. A pipeline whose
  verdict is inversely correlated with delivery is one whose classifier
  surface is structurally blind. Fix 3 (this postmortem) is the cheapest
  intervention that flips the correlation.
- **The Fix 2 / Fix 3 / Fix-name debt is now a chain.** RUN_003 Fix 3 was
  the postmortem classifier. RUN_007 Fix 2 was the empty-stub signatures.
  RUN_008 Fix 2 was the cross-file integrity signatures. RUN_009 Fix 3 (this
  one) is the same item with another layer of motivating evidence. Four
  postmortems have named this fix; none of them shipped it. The fifth
  postmortem will likely name it again unless the third is the one that
  lands.

---

## 5. Recommended next step

Spec **Fix 1 + Fix 2** as a single reflective-requirements + plan pair —
they share infrastructure (plan-level scope semantics propagating into the
seed-emitter + spec_builder), and isolating them as a unit lets the
implementation pass touch one cohesive surface. **Fix 3 is the loudest piece
of accumulated debt and should ship as a parallel work stream** — it is the
postmortem-classifier extension that's been deferred across four
remediation passes; deferring it again on this postmortem would extend the
score-vs-reality inversion to a fifth run.

In parallel, the **direct-fix path on run-009's outputs** (restore M1 ship
set from git; sed the 5 invented `@/lib/prisma` imports to `@/lib/db`;
resolve `@/lib/logger`; resolve pino; expand `lib/value-model.ts` against
the restored Prisma schema; audit UI form state against the corrected Zod
shapes) gets startd8 to a working M2-redo + M3 end state without depending
on any of the three SDK fixes here. This is the recommended approach to
unblock app delivery while the SDK fixes follow their own cadence.

**Do not run-010 (a fresh full pipeline invocation) until Fix 1 from this
postmortem has shipped.** Running `--fresh` again on any plan that lists
the M1 ship set in its seed `file_specs` will reproduce the wipe; even
a plan that doesn't list those files is at risk if any prior run leaves
them on disk and a future run picks them up. Until the schema-level
target/anchor distinction is in place, there is no pipeline-level signal
that keeps an anchor on disk.

### Strategic insight: git discipline is the only durable user-side defense

The run-009 attribution chain (§1 attribution note) makes this load-bearing:
**any file in the project root that is not committed to git is one
`--fresh` away from disappearing.** The M1 ship set was never committed,
so when an earlier run wiped it, the loss was permanent and cascaded
through every subsequent run. Until Fix 1 from this postmortem lands,
adopt these as session-level habits:

1. **Commit aggressively.** Any file the pipeline produces that you intend
   to keep — every milestone deliverable, every hand-fixed file, every
   restored anchor — gets `git add` + `git commit` **before** the next
   pipeline-touching action. Treat any uncommitted artifact as ephemeral.
2. **Commit before `--fresh`.** Every `--fresh` invocation is a destructive
   operation against the project root's `file_specs` targets. If anything
   on disk matters, commit it first.
3. **Treat the seed's `file_specs` as the at-risk set.** Inspect the seed
   before every run; verify the listed paths are intentional regeneration
   targets. Today there is no other signal you can read.

These habits do not replace Fix 1; they bridge the gap until Fix 1 ships.
The schema-level fix is the durable answer — git discipline is the
duct-tape that prevents data loss in the meantime.

---

## 6. Verified reconciliation + implemented fix (2026-06-01 review)

A code-grounded review against the merged SDK confirmed the three gaps but **corrected two attributions** and **shipped the highest-leverage fix**:

**Gap A (timing/mechanism corrected).** "run-009's seed still listed the 9 files → wiped" is **not supported**: run-009's enriched seed `file_specs` has **13 entries — M2/M3 targets only**; the M1 anchors are absent. They were wiped by an **earlier** `--fresh` (`run-003`/`run-004` seeds listed them) and, being **never git-tracked**, never restored. Confirmed root cause: **`ForwardFileSpec` has no target-vs-anchor field** → cleanup can't distinguish them. Fix direction unchanged; the concrete enabler is that flag + **git-committing the anchors**.

**Gap C corrected (Fix 2 *is* wired).** RUN-008 Fix 2 (Prisma↔Zod symmetry) is shipped/wired (`_evaluate_cross_file_integrity`, `:1378`); it **no-oped on run-009 because Prisma was wiped**, not because it's unwired. The missing classifier was the unresolvable-import signal — covered by the `tsc` gate (FR-4) **only when provisioned**, which the wipe destroyed. So Fix 3 re-scopes to a **toolchain-free** check.

**✅ IMPLEMENTED — Fix 3 (re-scoped): toolchain-free unresolvable-import signature.** `validators/cross_file_imports.py:scan_unresolvable_imports` (reuses the FR-1 `upstream_interface` resolver), wired into `_evaluate_cross_file_integrity` so it fires **even with no `.prisma`/`node_modules`/`tsconfig`**. Flags `@/`-aliased and relative imports resolving to neither the generated batch nor an on-disk file → feature FAIL (`root_cause=CROSS_FILE_CONTRACT`) + `unresolvable_import` Kaizen suggestion. **Validated against the real run-009 output: 8 violations caught** (5× `@/lib/prisma`, `@/lib/db`, `@/lib/logger`, +1) on the 1.00-PASS run — flips Gap D for this class. 24 tests; 273-test cross-file/postmortem suite green.

**Still open (next implementation):**
- **Gap A** — `ForwardFileSpec` target-vs-anchor flag + seed-emitter omits anchors + `clean-prior-run.sh` do-not-wipe list + git-commit anchors. *Highest-leverage; blocks multi-batch delivery.*
- **Gap B** — Mode-B inheritance: extend `_collect_upstream_interfaces` (in-batch `depends_on` only today) to propagate **pre-existing on-disk anchors** (same files Gap A's flag identifies). Needs Gap A first to be testable.
- **Gap C residual** — missing-dependency signature (`import pino` vs `package.json`); deferred until a `package.json` survives (Gap A). The unresolvable-`@/`-import half is shipped.

---

*Authored 2026-06-01 from the prime-contractor run-009 attempt-2 verdict.
Evidence:
`pipeline-output/startd8/run-009-20260601T0045/plan-ingestion/{prime-result.json,
prime-postmortem-report.json, prime-postmortem-summary.md,
kaizen-suggestions.json}`; on-disk file state at
`/Users/neilyashinsky/Documents/dev/strtd8/strtd8/{lib/,app/,prisma/}` after
the run; attempt-1 snapshot at `/tmp/run-009-attempt-1-20260601T1005/`;
in-flight observations at `RUN_009_IN_FLIGHT_FINDINGS.md`; companions
`RUN_003_FORWARD_MANIFEST_GAP_POSTMORTEM.md`,
`RUN_007_PARTIAL_DELIVERY_POSTMORTEM.md`,
`RUN_008_CROSS_FEATURE_INCOHERENCE_POSTMORTEM.md`,
`PLAN_BATCH_ORCHESTRATION_REQUIREMENTS.md` FR-10. Project plan:
`/Users/neilyashinsky/Documents/dev/strtd8/strtd8/.cap-dev-pipe/typescript/typescript-plan.md`.*
