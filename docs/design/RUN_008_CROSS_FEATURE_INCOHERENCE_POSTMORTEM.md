# Cross-Feature Semantic Incoherence in a Single Batch — Postmortem & Remediation

**Date:** 2026-05-31
**Trigger incident:** prime-contractor run `run-008-20260531T2050` reported `16/16
succeeded` with verdict **PASS** (score 0.99), with **15 of 16 features routed
to a real LLM call** (resolving the RUN_007 micro-prime SIMPLE-tier
stub-fallback regression). Every generated file is internally well-engineered.
**Net working delivery is 0 features against M1+M2 as a system**: the app does
not compile (3 invented module import paths + 1 invalid Prisma usage), and even
if patched to compile, the API layer would throw at runtime because every
child entity's `profileId` foreign key in the Zod schema does not exist in the
Prisma schema. **The codebase contains three independent definitions of the
Profile model — one in Prisma, one in Zod, one in the Profile UI — pairwise
disagreeing.**
**Headline finding:** the RUN_003 + RUN_007 remediation paths assume that
giving each feature the contract for **its own target files** is sufficient.
Run-008 shows the assumption is wrong: dependent features generated in the
same batch do not see each other's output at design time, so each one
**invents its own definition of the cross-file contract** (module names, FK
shape, field naming, type choices, even the data model). This is the
**inter-batch context isolation failure mode** (`CONTEXT_CORRECTNESS_BY_DESIGN.md`
/ `PLAN_BATCH_ORCHESTRATION_REQUIREMENTS.md` FR-10) reproduced at the
**intra-batch / inter-feature scope** the Forward Manifest design didn't
address.

---

## 1. What happened

Run-008 executed against the same M1-M2 seed as RUN_007 (16 features,
identical task IDs). The cost profile flipped relative to RUN_007: 15 of 16
features went through the lead/drafter LLM path (cost $0.05–$0.29 each), only
1 SIMPLE-tier ($0.0000). The RUN_007 micro-prime stub-fallback failure mode
did not fire. **Every generated file has substantive content.** Per-file form
quality is high:

| ID | Target file | Lines | Form quality |
|----|-------------|-------|--------------|
| PI-001 | `package.json` | 34 | ✅ Next 14 / React 18 / Prisma 5.14 / Zod 3 / Jest config |
| PI-002 | `tsconfig.json` | 64 | ✅ Production-grade strict TS (`noUncheckedIndexedAccess`, `moduleDetection: force`) |
| PI-003 | `next.config.mjs` | 5 | ✅ Registry-templated, parses |
| PI-004 | `.env.example` | 20 | ✅ Real content |
| PI-005 | `lib/env.ts` | 49 | ⚠ 2 getters only (ANTHROPIC_API_KEY, COST_BUDGET_USD); coverage gap vs `.env.example` |
| PI-006/010 | `prisma/schema.prisma` | 268 | ✅ Full Value Model graph with provenance + 3 join tables |
| PI-007 | `lib/db.ts` | 12 | ✅ Idiomatic Prisma singleton with dev global cache |
| PI-008 | `app/layout.tsx` | 50 | ✅ Idiomatic Next 14 App Router layout (metadata + nav) |
| PI-009 | `app/page.tsx` | 103 | ✅ Clean landing page |
| PI-011 | `lib/value-model.ts` | 475 | ⚠ Internally clean Zod; **diverges from Prisma on every entity** |
| PI-012 | `app/api/profile/route.ts` | 58 | ⚠ Clean GET/PUT shape; **broken import + invalid Prisma usage** |
| PI-013 | `app/profile/page.tsx` | 216 | ⚠ Clean React shape; **invents a third Profile model** |
| PI-014 | `app/api/proof-points/route.ts` | 121 | ⚠ Clean shape; **broken import + Zod/Prisma FK mismatch** |
| PI-015 | `app/api/proof-points/[id]/route.ts` | 170 | ⚠ Clean shape; **broken import + FK mismatch** |
| PI-016 | `app/proof-points/page.tsx` | 895 | ⚠ Substantial React UI; **dependent on broken Zod/API contract** |

Pipeline self-assessment surfaces (`prime-result.json`,
`prime-postmortem-summary.md`):

- **Verdict:** PASS (score 0.99)
- **Total features:** 16, **Successful:** 16, **Failed:** 0
- **Total cost:** $1.7671 (average $0.1104, max PI-016 $0.2907)
- **Micro-prime:** 1 element, 1 successful, 0 escalated, tier distribution `simple: 1`
- **Lessons / Kaizen suggestions:** none of substance

Reality: **0 of the 16 features deliver against M1+M2 as a working system.**
Each individual file is internally well-formed; the system as a whole is
broken because the dependent features each invented their own version of the
cross-file contract. The pipeline measured "did each generator return
without raising?" and "does the file parse?" — neither catches the actual
failure mode.

---

## 2. The gaps this incident exposes

Four structural gaps. Together they explain why a 0.99-score run delivered
nothing functional.

### Gap A — No inter-feature contract for cross-file **names**

Three independently generated API features each invented their own module
name for the same target Zod module:

| Importer | Imports | Resolves? |
|----------|---------|-----------|
| `app/api/profile/route.ts:2` | `from '@/lib/schemas'` (plural) | ❌ |
| `app/api/proof-points/route.ts:3` | `from '@/lib/schema'` (singular) | ❌ |
| `app/api/proof-points/[id]/route.ts:2` | `from '@/lib/schemas'` (plural) | ❌ |
| **Actual file** | `lib/value-model.ts` | — |

The Zod schemas feature (PI-011) named the module `lib/value-model.ts`. Each
of the three consumer features (PI-012, PI-014, PI-015) invented its own name
for what it was about to import. PI-012 and PI-015 picked `schemas` plural;
PI-014 picked `schema` singular. The names were never reconciled because no
feature saw the others' generation context — PI-011's choice of
`value-model.ts` was never propagated to its downstream consumers, and PI-012's
choice of `schemas` was never propagated to PI-015 (which independently picked
the same wrong name).

This is exactly the failure shape the original Forward Manifest design
attempted to close at the file-internals level (FR-3 single-source contract
between spec_builder and reviewer for the same target file). It did **not**
extend to the cross-file scope. The spec_builder gives each feature the
forward_manifest entry for **its own** `target_files`; it does not give the
feature the forward_manifest entries for the **files it imports from**.

### Gap B — No inter-feature contract for cross-file **types**

The Prisma schema (PI-010) and the Zod schemas (PI-011) were generated
independently and **disagree on every entity**. The headline divergences are
not field-naming style — they are structural:

| Entity | Concrete divergence |
|--------|---------------------|
| **Profile** | Prisma `summary` vs Zod `bio`; Prisma `yearsExp` vs Zod `yearsOfExperience`; Zod-only `websiteUrl`, `metadata`; Prisma-only `company`, `phone`, `notes` |
| **ProofPoint** | Zod requires `category` and `profileId` — Prisma has **neither**. Prisma uses join tables (`ProofPointCapability`, `ProofPointOutcome`) for many-to-many; Zod invents a direct `profileId` FK. |
| **Capability / Outcome / Differentiator / ValueProp / Artifact / AiCall** | Same pattern — Zod invents a `profileId` foreign key for **every** child entity. Prisma defines **none** of them. |
| **Metric** | Prisma: `value: String`. Zod: `value: z.number()`. **Fundamental type mismatch.** |

This is the canonical "drafter sees no contract for what callers expect"
failure: PI-011 received `target_files = ["lib/value-model.ts"]` and produced
a coherent Zod model graph rooted at a synthetic `Profile`-as-aggregate-owner
shape. PI-010 received `target_files = ["prisma/schema.prisma"]` and produced
a coherent join-table-rooted graph. **Neither feature saw the other.** Each
plausibly invented a graph; the two graphs are not the same graph.

Consequence: when the API routes (PI-012, PI-014, PI-015) validate a request
body with Zod (which requires `profileId`) and pass it to Prisma (which has
no `profileId` column on any child entity), Prisma errors on the unknown
field. Even patching the broken import paths from Gap A would not make the
API functional.

### Gap C — No inter-feature contract for cross-file **behavior**

The Profile UI (PI-013) defines `ProfileFormState { name, targetRoles,
industry, seniority }` and uses `fetch('/api/profile')` to read it. Neither
`targetRoles` nor `seniority` exists in the Prisma Profile, the Zod Profile,
or anywhere else in the codebase. **The Profile UI invented a third Profile
model**, disagreeing with both the data layer and the validation layer.

Per the seed task PI-013 description: `Profile capture form`. PI-013's
generation context had the task title and any forward_manifest spec for
`app/profile/page.tsx` itself, but no read on what fields PI-010's prisma
model declared, no read on what fields PI-011's Zod model required, and no
read on what fields PI-012's API actually returns. The lead/drafter
plausibly chose realistic-looking job-seeker form fields (`targetRoles`,
`seniority`) that match the M1-M2 product story but do not match the
already-generated data layer's actual columns.

Even if Gaps A and B were patched (imports resolved, Prisma↔Zod
reconciled), the Profile page would render an empty form because every state
field would silently fall through `data.targetRoles ?? ""` to the empty
string.

### Gap D — Postmortem classifier is still blind to cross-file mismatches

The postmortem reports verdict PASS (0.99) and 0 Kaizen suggestions, on a run
that delivers nothing functional. This is the **same gap-class** as RUN_007
Gap C (postmortem blind to the empty-stub signature) and RUN_003 Gap C
(postmortem reports `unknown / unknown` for captured failures) — the
classifier sees only "the generator returned" and "the file parses." Neither
signal catches:

- **Unresolvable imports** in a TypeScript file (a `tsc --noEmit` pass over
  the generated set would).
- **Prisma↔Zod symmetry violations** for the same logical entity (a
  cross-file comparison of `prisma/schema.prisma` model definitions against
  `lib/value-model.ts` Zod schema definitions would).
- **Prisma usage validity** at the call sites (whether `findUnique({ where:
  { ownerId } })` resolves to an actually-`@unique` column — it does not for
  `Profile.ownerId String @default("local")`, an invalid usage TypeScript
  itself would flag).
- **Cross-feature import / consumer / producer mismatches** more broadly
  (PI-012 says it imports from `@/lib/schemas`; PI-011 says it produces
  `@/lib/value-model`; these names should be reconciled at the seam).

Net: the postmortem is *still* actively misleading, not just incomplete.
RUN_007 Fix 2 (empty-stub classifier signatures) would not have caught
RUN_008. The classifier must add a cross-file integrity pass to the
signature set, otherwise no run of any scope can be trusted to mean what it
says.

---

## 3. How to close the gaps

Three fixes, ordered by leverage and increasing scope.

### Fix 1 — Intra-batch inter-feature context inheritance (the headline fix)

**What:** when feature F2's `target_files` depend on (or import from)
feature F1's `target_files`, F2's spec-builder context MUST include F1's
**already-generated content** for the imported file — not the seed's
forward_manifest stub, not the 300-character summary. Dependency is detected
either (a) declaratively from `depends_on` in the seed (where F1 is upstream
of F2 in the dependency DAG), or (b) heuristically from the seed's
`target_files` / language-aware import-path inference.

This is the **FR-10 inheritance contract from
`PLAN_BATCH_ORCHESTRATION_REQUIREMENTS.md`** applied at the **intra-batch
inter-feature seam** instead of the inter-batch seam. Same shape, smaller
scope. The blocking-on-missing-artifact behavior (FR-10's "no silent fallback
to summaries") applies identically here: if F1's output is expected but not
present (e.g. F1 has not generated yet, or was skipped), F2 halts loudly
rather than inventing a contract.

**Why:** the Forward Manifest fix gives each feature the contract for **its
own** target files via `file_specs_for_task(target_files=…)`. It does not
give the feature the contract for **files it imports from**. That gap is the
root cause of every Gap-A and Gap-B failure in this run. Inheritance fills
it by construction: PI-012 sees PI-011's emitted `lib/value-model.ts`; PI-013
sees PI-012's emitted `app/api/profile/route.ts`; the import names and the
field shapes are then sourced from the actually-generated artifact, not from
each feature's independent invention.

**Acceptance / validation:**

- A regression test reproducing run-008: a synthetic seed with PI-011 →
  PI-012 dependency where PI-011 writes a Zod module named `schemas.ts` and
  PI-012 imports from it; assert PI-012's emitted import path is
  `@/lib/schemas` (matches what was actually written), not an invented
  name.
- A cross-file Prisma↔Zod symmetry test: synthetic seed with PI-010 →
  PI-011 dependency where PI-010 writes a Prisma model with `summary` and
  `yearsExp`; assert PI-011's emitted Zod schema uses the same field names,
  not synonyms (`bio`, `yearsOfExperience`).
- A missing-artifact-blocks test: invoke PI-012 in a synthetic context where
  PI-011 has not generated; assert PI-012 halts with a
  `MissingUpstreamArtifact` diagnostic, not a silent invention of the
  import path.

**Closes:** Gap A directly. Closes most of Gap B. Reduces Gap C significantly
(the UI now sees the API's actual response shape).

### Fix 2 — Cross-file integrity signatures in the postmortem classifier

**What:** the postmortem classifier MUST add at least three cross-file
integrity checks that run after batch generation, before the success/fail
record is finalized:

1. **Unresolvable-import signature.** For every `*.ts` / `*.tsx` file in the
   generated set, parse import declarations and assert every `@/`-prefixed
   path resolves to a file in the generated set or a pre-existing project
   file. Match on file existence, not on hand-maintained tables.
2. **Prisma↔Zod symmetry signature.** For every Prisma `model` and every
   Zod `z.object(...)` that maps to the same logical entity (by name match
   or by an emitted producer/consumer manifest entry), assert field name
   sets, type-class compatibility, and FK shape agree.
3. **Prisma usage validity signature.** For every `db.<model>.{findUnique,
   upsert}({ where: { … } })` call site, assert the `where` keys map to
   `@unique` (or `@@unique`) columns in the corresponding Prisma model.

Each signature match marks the feature failed regardless of syntax-check
outcome, classifies the pipeline stage as **`drafter / cross-feature
contract`**, attributes root cause to the specific signature
(`unresolvable_import` / `prisma_zod_symmetry_violation` /
`prisma_usage_invalid_constraint`), and emits at least one Kaizen
suggestion.

These signatures generalize RUN_007 Fix 2's "drafter template fallback"
detector to the multi-file / cross-feature scope. They are the postmortem
side of Fix 1: if Fix 1 lands and Fix 2 doesn't, future regressions in the
inheritance path will silently slip past again; if Fix 2 lands without Fix
1, the failures are at least visible.

**Why:** the postmortem's PASS verdict on a 0-functional-feature run is
actively misleading. Every downstream consumer (Kaizen aggregator, batch
ledger, the future Plan Batch Orchestration FR-4 gate) is reading from a
surface that says "good run." Closing the gap requires the classifier to
see the cross-file failure mode that actually shipped.

**Acceptance / validation:**

- A reproduction of any RUN_008 broken file (broken import, FK invention,
  invalid `findUnique`) produces a non-`unknown` stage, a specific signature
  attribution, and at least one Kaizen suggestion citing the specific
  cross-file violation.
- A reproduction of PI-002 / PI-003 / PI-010 (production-quality files)
  produces a SUCCESSFUL classification — no false positives.
- Signatures are testable from a fixture set of file pairs without an LLM
  call.

**Closes:** Gap D directly. Provides the failure-visibility surface that
makes Fix 1 testable in production.

### Fix 3 — Single-source-of-truth Value Model contract artifact per batch

**What:** for batches whose features collectively implement a logical data
model (e.g. the Value Model in startd8 M1-M2), emit **one canonical contract
artifact** at batch start (or as part of plan ingestion) that subsequent
features consult as their cross-file shape source of truth. Shape: a small
JSON/YAML artifact (e.g. `forward_value_model.json`) keyed by logical entity
(`Profile`, `ProofPoint`, …) declaring field names, types, FK shape, and
which feature produces which file representation. Features generating any
file that touches the model consult the artifact; the artifact is
immutable for the duration of the batch.

This is a constrained, scoped version of the typed artifact-consumption
manifest discussed in
`PLAN_BATCH_ORCHESTRATION_PLAN.md` R2-S5 — same idea (declare contracts up
front, validate at the seam), reduced from "typed registry across all
artifact types" to "one logical data model per batch." A small starter case
that proves the pattern.

**Why:** Fix 1 (inter-feature context inheritance) prevents downstream
features from inventing contracts when their upstream has already
materialized. It does not prevent the **upstream itself** (PI-010 + PI-011 in
RUN_008) from materializing two divergent contracts in the first place,
when both are generated from the same logical entity definition in the plan
prose. A pre-batch contract artifact constrains both upstream features to
the same shape by construction.

**Acceptance / validation:**

- A reproduction where PI-010 and PI-011 both consult the same
  `forward_value_model.json` produces a Prisma model and a Zod schema with
  identical field name sets and type-class agreement for every entity.
- The contract artifact is inspectable and version-stampable per batch.
- Fix 3 is opt-in per batch (configurable via the seed) — batches that do
  not declare a logical data model do not pay the contract-artifact cost.

**Closes:** the remainder of Gap B (the upstream-divergence half). Reduces
the contract surface that Fix 1 inheritance has to reconcile.

---

## 4. Why this matters beyond run-008

- **Same root cause, fourth layer.** The "drafter / micro-prime path
  invents structure when no contract is available" rule has surfaced in
  RUN_003 (single-file structure inside the framework-config registry case),
  RUN_007 (single-file structure inside the SIMPLE-tier template fallback
  case), and now RUN_008 (cross-file structure across dependent features in
  one batch). Each prior fix closed a deflection path; the root rule
  survives because no fix has yet propagated **already-generated sibling
  output** into a feature's design context. Fix 1 here is the first
  remediation pass that addresses the inter-artifact contract at all.
- **Sequential generation does not auto-fix context isolation.** RUN_008's
  16 features generated **in dependency order** within a single
  prime-contractor run — PI-010 (Prisma) before PI-011 (Zod) before PI-012
  (API) before PI-013 (UI). Sequential ordering put PI-011's output **on
  disk** before PI-012 generated. But PI-012's spec-builder context did not
  read from disk; it read from the seed's forward_manifest entries for
  PI-012's own target files. The "code is on disk" mitigation from
  `PLAN_BATCH_ORCHESTRATION_PLAN.md` Increment 0 seam caveat (R1-S4)
  applies only when downstream features actually read from disk at design
  time. **They do not today.** This is the load-bearing observation that
  invalidates the Increment-0 "safe" claim at the intra-batch level — the
  same way it was already noted to invalidate it at the inter-batch level.
- **The PASS verdict is the most dangerous output.** RUN_003 reported a
  failure (the integration syntax check caught the parse error). RUN_007
  reported PASS but at least one feature was flagged (the false-positive on
  PI-002). RUN_008 reports a clean PASS with no flagged features at all.
  **Every successive remediation pass that fixes a visible failure mode
  without fixing the classifier surface for the next layer's failure mode
  reduces the rate at which real failures get caught.** The classifier
  upgrade (Fix 2 here, mirroring RUN_007 Fix 2 and RUN_003 Fix 3 — none of
  which have shipped) is at this point load-bearing across all three
  postmortems.
- **The fix shape generalizes.** Fix 1 is the FR-10
  ("inter-batch context inheritance, blocking on missing artifact") contract
  applied to a smaller scope — features inside a single batch instead of
  batches inside a multi-batch plan. The two are the same mechanism at
  different granularities. Specifying both together would let Plan Batch
  Orchestration MVP and the next prime-contractor patch share a single
  inheritance implementation.

---

## 5. Recommended next step

Spec **Fix 1 + Fix 2** as a single reflective-requirements + plan pair —
they are the minimum coherent unit (Fix 2 is the visibility surface that
makes Fix 1 testable in production; either alone is insufficient). Defer
**Fix 3** as a follow-on once Fix 1's inheritance contract is in place; Fix
3's contract-artifact shape is best designed after observing what Fix 1's
inheritance actually carries between features.

Align the Fix 1 scope with the parallel `PLAN_BATCH_ORCHESTRATION` FR-10
work: they are the same mechanism applied at two granularities, and
duplicating the inheritance implementation across batches and features would
itself be the next layer of accidental complexity. The R3 essential-MVP
distillation already in
`PLAN_BATCH_ORCHESTRATION_PLAN.md` Appendix C is the right place to
land this consolidation.

---

*Authored 2026-05-31 from the prime-contractor run-008 cross-feature
incoherence. Evidence:
`pipeline-output/startd8/run-008-20260531T2050/plan-ingestion/{prime-result.json,
prime-postmortem-summary.md, prime-context-seed-enriched.json}`; generated
files at the project root (the 6 broken consumer-layer files plus their
empty parent directories were triaged out as part of this postmortem's
shipping decision); code:
`src/startd8/implementation_engine/{spec_builder.py, drafter.py,
contractor_workflow.py}`,
`src/startd8/forward_manifest.py` (`file_specs_for_task`),
`src/startd8/contractors/queue.py` (feature ordering). Companions:
`RUN_003_FORWARD_MANIFEST_GAP_POSTMORTEM.md` (whose Fix 1 wired the spec
prompt for the single-file contract case),
`RUN_007_PARTIAL_DELIVERY_POSTMORTEM.md` (whose Fix 1 attacks the
SIMPLE-tier template fallback, complementary to this postmortem), and
`PLAN_BATCH_ORCHESTRATION_REQUIREMENTS.md` FR-10 (whose contract is the
same mechanism applied at the inter-batch instead of inter-feature
granularity).*
