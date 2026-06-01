# M4 Batch — Field-Content + Module-Path Invention Survives Mode-A Inheritance

**Date:** 2026-06-01 (post-authoring update applied 2026-06-01 17:00 —
TS2345 signature shipped between authoring and postmortem re-run; see §6
addendum)
**Trigger incident:** prime-contractor run `run-011-20260601T1542` (the M4
batch — enrichment passes + value map) reported **PARTIAL / 0.50** with
**5 of 10 features succeeded, 5 failed**. The failures attributed to
specific cross-file contract violations (`prisma_unknown_field:*`,
`unresolvable_import:*`). 5 features required direct-fix; the 6th never
reached disk and is awaiting regeneration via `--task-filter`.
**Cost:** $2.07 total ($0.20 average; PI-010 the cost outlier at $0.42).
**Headline finding (good):** the verdict is now **honest** for the first
time in this session. Approach B's `cross_file_imports.py` /
`prisma_usage.py` / `prisma_zod_symmetry.py` classifier signatures fire
with attributed causes; the false-PASS-on-broken-output pattern from
RUN_007 / RUN_008 / RUN_009-attempt-2 is closed. The pipeline now tells
the truth.
**Headline finding (bad):** Mode A intra-batch inheritance has shipped
and propagates module paths between same-batch sibling files (M4's
`/api/ai/enrich-*` routes correctly imported `@/lib/value-model` and
`@/lib/ai/service` from M3). But the LLM continues to **invent Prisma
field names** that don't exist on the schema (`aiRefId`, `label`,
`outcomeId`, `title`, `supportingEvidence`, …) and continues to **invent
canonical-looking module paths** for files outside the same-batch
producer set (`@/lib/prisma`, `@/lib/ai/client`, `@/lib/db/capabilities`).
These are the **content-level cross-file contracts** that
`CROSS_FILE_CONTRACT_RESOLUTION.md` §3 §4 predicted: addressed by
neither Mode A nor Mode B as currently implemented; classifier-detected
but not classifier-prevented; require Approach A (pre-flight
project-knowledge artifact) or Approach D (single-pass synthesis) to
close.

---

## 1. What happened

The M4 plan declared 12 features across 4 functional groups (Capabilities
+ Outcomes, Metrics, Differentiators, ValueProps + Value Map), each a
`lib → API route → UI` triple. Prime-contractor processed 10 before
halting at PI-010; PI-011 and PI-012 (the ValueProps API route + Value Map
UI) never ran due to stop-on-failure on PI-010.

| ID | Feature | Reported | Real verdict (classifier) | Cause |
|----|---------|---------:|---------------------------|-------|
| PI-001 | Capabilities + Outcomes enrichment lib | ✅ | ❌ | `prisma_unknown_field: aiRefId, label` |
| PI-002 | Capabilities + Outcomes API route | ✅ | ❌ | `unresolvable_import: @/lib/db/capabilities, @/lib/db/outcomes` |
| PI-003 | Capabilities + Outcomes UI | ✅ | ✅ | clean |
| PI-004 | Metrics quantification lib | ✅ | ❌ | `prisma_unknown_field: outcomeId, label` |
| PI-005 | Metrics quantification API route | ✅ | ✅ | clean |
| PI-006 | Metrics quantification UI | ✅ | ✅ | clean |
| PI-007 | Differentiators synthesis lib | ✅ | ❌ | `unresolvable_import: @/lib/prisma, @/lib/ai/client`; `prisma_unknown_field: title, supportingEvidence (+1 more)` |
| PI-008 | Differentiators synthesis API route | ✅ | ✅ | clean |
| PI-009 | Differentiators UI | ✅ | ✅ | clean |
| PI-010 | ValuePropositions synthesis lib | — | ❌ | **(updated at 16:55):** `typecheck / type_class_mismatch` (TS2345) — Approach B's new TS2345 signature now fires; classifier also surfaces `unresolvable_import: @/lib/prisma` + `prisma_unknown_field: capabilityId, outcomeId, text`. Never reached disk due to halt on type error. |
| PI-011 | ValuePropositions API route | ⏭ | ⏭ | halt-cascade from PI-010 |
| PI-012 | Value Map UI | ⏭ | ⏭ | halt-cascade from PI-010 |

The `prime-result.json` recorded 9 succeeded / 1 failed; the
`prime-postmortem-summary.md` recorded 5 succeeded / 5 failed. The
postmortem is authoritative — it ran the cross-file integrity classifier
signatures after prime-contractor's own bookkeeping closed, reclassifying
4 features as failed.

**Critical observation: the verdict is honest.** Score 0.50, PARTIAL.
This is the first run in this session where the postmortem report
accurately reflects the on-disk state. Score-vs-reality inversion (RUN_009
Gap D) is genuinely closed — at least for the failure modes Approach B's
signature set covers.

---

## 2. The gaps this incident exposes

Three structural gaps. Two are content-level extensions of the same root
cause that survived prior remediation passes; the third is a new SDK
classifier-coverage gap.

### Gap A — LLM invents Prisma field names despite the schema being on disk and inheritable

Three of five failed libs (PI-001, PI-004, PI-007) invented fields on
Prisma models that don't exist:

| File | Invented fields | Model | Real fields |
|------|----------------|-------|-------------|
| `lib/ai/enrich-capabilities.ts` | `aiRefId`, `label` | Capability, Outcome | `name`, `category`, `description`, `proficiency` / `metric`, `timeframe`, `notes` (+ provenance) |
| `lib/ai/enrich-metrics.ts` | `outcomeId`, `label` | Metric | `name`, `value`, `unit`, `direction`, `timeframe`, `description`, `notes` (+ provenance) — note no FK to Outcome |
| `lib/ai/enrich-differentiators.ts` | `title`, `supportingEvidence` (+1 more — likely `order`) | Differentiator | `name`, `category`, `description`, `evidence`, `notes` (+ provenance) |

The pattern is consistent: **the LLM picks "canonical-looking" field
names from its training distribution** (`title` instead of `name`,
`supportingEvidence` instead of `evidence`, `aiRefId` as an
LLM-side-convenience for upsert deduplication, `outcomeId` as a presumed
FK that the schema doesn't define). Mode A inheritance currently
propagates **module-path-level** signals (which file to import from); it
does not propagate **field-content-level** signals (which fields the
imported entity actually has).

`prisma/schema.prisma` is on disk and was readable by the SDK during
generation. The pre-flight project-knowledge artifact (`Approach A`
from `CROSS_FILE_CONTRACT_RESOLUTION.md` §5) would have injected the
exact field set per model into each feature's spec context. Without it,
the LLM falls back to plausible-canonical guesses.

### Gap B — LLM invents `@/lib/*` module paths despite the canonical paths being on disk

Two of five failed files invented `@/lib/*` paths that don't exist:

- PI-002: `@/lib/db/capabilities` and `@/lib/db/outcomes` — invented
  sub-paths under `@/lib/db` (the real, existing file at `lib/db.ts`
  exports a single `db` binding; there are no sub-modules).
- PI-007: `@/lib/prisma` (the classic invention — third recurrence this
  session, after RUN_008 and RUN_009-attempt-2) and `@/lib/ai/client`
  (a path that follows a plausible-canonical naming pattern but doesn't
  match the actual `lib/ai/service.ts` filename).

Three observations matter:

1. **The same `@/lib/prisma` invention appears across three different
   batches** (RUN_008 ProofPoint API + AI service files; RUN_009-attempt-2
   five separate files; RUN_011 differentiators lib). Mode A propagates
   the correct path WHEN the producer is in the same batch (the M4
   batch's three sibling routes for Capabilities/Metrics/Differentiators
   API all correctly inherit `@/lib/ai/service` from the M3 `lib/ai/`
   surface). It does NOT propagate when the canonical-looking guess is
   strong enough that the LLM doesn't notice the producer artifact in
   context.

2. **Mode B is partial.** It clearly works for `@/lib/ai/service` and
   `@/lib/value-model` (those propagated across the batch correctly).
   But it does not appear to feed the LLM an **explicit "the project
   uses @/lib/db, NOT @/lib/prisma"** signal strong enough to override
   the LLM's canonical-name prior.

3. **The classifier caught both inventions.** This is a real win — the
   `unresolvable_import` signature fires and attributes correctly. The
   failure is visible. The remediation is direct-fix or regen.

### Gap C — TS2345 (type-class mismatch) is classifier-blind

PI-010 generated `synthesize-value-props.ts` with a type error:

```
synthesize-value-props.ts:273:55
error TS2345: Argument of type 'Set<unknown>' is not assignable to
parameter of type 'Set<string>'. Type 'unknown' is not assignable to
type 'string'.
```

The postmortem attributed this as `Stage: unknown / Root cause: unknown` —
the only `unknown/unknown` attribution in this run. Approach B's current
signature set covers:

- Unresolvable imports
- Missing dependencies
- Prisma field name validity
- Prisma usage constraint validity (compound keys, etc.)
- Zod ↔ Prisma symmetry

It does **not** cover **type-class assignment incompatibilities** — the
TS234x family (assignment to incompatible types), TS231x family
(operator overload resolution failures), TS233x family (binding pattern
mismatches), etc. These are real TypeScript errors that survive the
per-file isolation check (correctly — they're not module-resolution
false positives) and represent genuine type-level contract violations.

PI-010's specific error was a Zod inference issue: a `Set<unknown>`
likely arose from iterating a generic `unknown`-typed collection from
the LLM's tool-use response into a `Set` used downstream as
`Set<string>`. A fix would be a `Set<string>` annotation or an explicit
type cast at the iteration site. Without a signature for this category,
the verdict shows `unknown` and the developer must look at the raw error
message to diagnose.

### Gap D — Two-source-of-truth (prime-result vs postmortem) still disagrees

For run-011:

| Source | Reports |
|--------|---------|
| `prime-result.json` | 9 succeeded / 1 failed (success counted at prime-contractor's bookkeeping layer) |
| `prime-postmortem-summary.md` | 5 succeeded / 5 failed (after classifier signatures ran) |

This is the RUN_008 §3 Fix 3 (`verification-ledger`) consolidation that
hasn't shipped. Downstream consumers picking one or the other inherit
inconsistent realities. The right surface is **postmortem** (it ran the
classifier signatures); the wrong-but-still-emitted surface is
**prime-result** (which optimistically counts as "succeeded" anything
that didn't raise during generation).

This is a cosmetic problem today (developers know to read the postmortem)
but a load-bearing problem tomorrow: Plan Batch Orchestration's FR-4
gate, the R2-F2 / R3 essential-MVP provenance work, and any
human-supervised triage workflow all need a single canonical answer to
"did this feature succeed?"

---

## 3. How to close the gaps

### Fix 1 — Approach A (pre-flight project-knowledge artifact) for Prisma field-content propagation (highest leverage, closes Gap A)

**What:** at batch start, a deterministic scanner reads
`prisma/schema.prisma` and produces a structured per-model summary
(field name → type → nullable → relation kind), then injects it as a
P0-priority context section into every feature's spec prompt.

**Smallest concrete shape:** the scanner emits
`forward_project_knowledge.json` keyed by entity, e.g.:

```json
{
  "models": {
    "Capability": {
      "fields": {
        "id": {"type": "String", "id": true, "default": "cuid()"},
        "ownerId": {"type": "String", "default": "local"},
        "source": {"type": "String", "default": "user"},
        "confirmed": {"type": "Boolean", "default": true},
        "name": {"type": "String", "nullable": true},
        "category": {"type": "String", "nullable": true},
        "description": {"type": "String", "nullable": true},
        "proficiency": {"type": "String", "nullable": true},
        "notes": {"type": "String", "nullable": true}
      },
      "relations": [
        {"name": "proofPoints", "model": "ProofPointCapability", "many": true},
        {"name": "outcomes", "model": "CapabilityOutcome", "many": true}
      ]
    }
  },
  "modulePaths": {
    "db": "@/lib/db",
    "ai_service": "@/lib/ai/service",
    "value_model": "@/lib/value-model",
    "logger": "@/lib/logger"
  }
}
```

The `modulePaths` section also closes Gap B by providing the
authoritative path for each commonly-imported module (preventing the
recurring `@/lib/prisma` / `@/lib/ai/client` inventions).

**Why this and not "more inheritance":** Mode A and Mode B both
propagate **what other files in the project look like**. Approach A
propagates a **structured, deterministic summary of the project's
contract surface** — exactly the level of abstraction the LLM needs to
not invent. A textual file paste is fundamentally less reliable than a
typed field-by-field summary in the spec prompt's most-protected section.

**Acceptance / validation:**

- A reproduction of PI-001 / PI-004 / PI-007 with the artifact injected:
  assert the generated files use only Prisma field names that appear in
  the artifact's `models.<Entity>.fields` set.
- A reproduction of PI-002 / PI-007 imports: assert the generated files
  import from paths that match `modulePaths` (never from canonical-
  looking guesses like `@/lib/prisma`).
- A baseline run without the artifact: existing behavior preserved.

**Closes:** Gap A directly. Closes most of Gap B (canonical-name
overrides for the common modules).

### Fix 2 — Type-class signature for the classifier (closes Gap C)

**What:** extend Approach B's signature set with a TS2345-family
signature that runs `tsc --noEmit` against the merged tree (already done
at the project-level gate per `cap-dev-pipe/ts-verify-gate.py`), parses
any `error TS234[0-9]` / `TS232[0-9]` / `TS231[0-9]` lines, and emits a
postmortem finding with stage `tsc / type_class_mismatch` and a
suggestion citing the file:line.

Per-file `tsc` already runs (in `src/startd8/languages/nodejs.py:362-440`);
the existing `_PER_FILE_FALSE_POSITIVE_CODES` list correctly drops codes
that are isolation-artifacts. **TS2345 is NOT a false positive** — it's a
real type error that survives isolation. The postmortem currently sees
the error message but doesn't attribute it to a specific cause; a new
signature would close that gap.

**Acceptance / validation:**

- A reproduction of PI-010: postmortem report's
  `pipeline_attribution.stage` becomes `tsc / type_class_mismatch` (or
  similar specific cause), not `unknown / unknown`.
- A clean baseline: no false positives on already-passing files.

**Closes:** Gap C directly. Provides a hook for postmortem-classifier
extension to other type-class families as they surface.

### Fix 3 — Verification ledger consolidation (closes Gap D)

**What:** the four-postmortems-deferred Fix 3 from
`CROSS_FILE_CONTRACT_RESOLUTION.md` and RUN_008 postmortem §3. A single
write-once `verification-ledger.json` per run records per-feature
verdict. `prime-result.json` and `prime-postmortem-summary.md` both read
from it instead of computing their own counts.

**Smallest concrete shape:**

```json
{
  "run_id": "run-011-20260601T1542",
  "features": [
    {"feature_id": "PI-001", "verdict": "FAIL",
     "stage": "cross_feature_contract",
     "cause": "prisma_unknown_field",
     "details": ["aiRefId", "label"],
     "cost_usd": 0.1979}
  ]
}
```

Both `prime-result.json`'s `succeeded`/`failed` counts and
`prime-postmortem-summary.md`'s table derive from this single source.

**Why now:** Plan Batch Orchestration's FR-4 gate, the M5 acceptance
checklist's "honest postmortem verdict" item, and any downstream
human-supervised triage all need a canonical truth. With Approach B
firing, the data is right — it just gets reported twice with different
shapes. Consolidating closes Gap D and prevents future divergence.

**Closes:** Gap D directly. Provides the durable canonical surface
Approach A and Fix 2 will write into.

---

## 4. Why this matters beyond run-011

- **Score-vs-reality inversion is closed for the cross-file contract
  family.** This is the canonical achievement of RUN_011 — four
  postmortems named Approach B (RUN_003 Fix 3, RUN_007 Fix 2,
  RUN_008 Fix 2, RUN_009 Fix 3); it shipped and works. The verdict now
  reflects on-disk reality for cross-file contract violations. Future
  iteration cycles can trust the postmortem's verdict as a signal
  worth optimizing against.
- **Mode A inheritance is a real win, demonstrably.** Three M4 routes
  correctly inherited `@/lib/ai/service` from M3; four M4 features
  imported `@/lib/value-model` cleanly. The intra-batch sibling
  propagation works. **Do not regress this.**
- **The content-level contract problem is the next layer.** Mode A and
  Mode B propagate paths; the LLM still invents fields and the
  not-explicitly-propagated module names. Approach A's structured
  project-knowledge artifact is the structural fix; further inheritance
  layering at the path level will not address it.
- **The TS2345 gap is a small but compounding signature backlog.**
  Each new type-class family the classifier misses becomes a quiet false
  PASS for that failure mode. The signature-extension approach (Fix 2)
  is cheap and additive; running it down a list of canonical
  TypeScript error codes is a few hours of work that closes a long tail.
- **Score is at 0.50, not 1.00.** Treat 0.50 as a *good* result this
  session — it's honest. The next iteration should aim for 1.00 because
  the underlying failures are closed (not because the classifier was
  bypassed).

---

## 5. Recommended next step

**Tier 1 (this session, after the valueprops regen):** Approach B's
classifier-signature set has shipped and works. The remaining strtd8
delivery work (PI-010-12 valueprops regen, smoke-test extension for M4
surfaces, M5+M6 batch authoring) does not depend on further SDK fixes
and can proceed in parallel with the SDK roadmap.

**Tier 2 (SDK roadmap, in priority order — revised per the 17:00 addendum):**

1. **Fix 1 — Approach A pre-flight project-knowledge artifact**. The
   highest-leverage remaining lever. Closes Gap A directly and most of
   Gap B. Five M4 features (PI-001, PI-002, PI-004, PI-007, PI-010) and
   the recurring `@/lib/prisma` invention pattern (now FOUR recurrences
   across run-008, run-009, run-011 PI-007, run-011 PI-010) would no
   longer occur. Effort estimate: medium (deterministic Prisma scanner +
   spec_builder seam + tool definition extension). Spec via
   reflective-requirements + plan.
2. **Fix 3 — Verification ledger consolidation**. Closes Gap D. Small
   structural change. Effort estimate: low (centralize the count
   computation; both writers point at the same file). Could ship before
   Fix 1 if the bandwidth split favors it.
3. **~~Fix 2 — TS2345 signature extension~~ — ✅ SHIPPED.** Closed Gap C
   between authoring and the 16:55 postmortem re-run. See §6 addendum.
4. **Fix 4 (new) — Wire `CAUSE_TO_SUGGESTION` for the active classifier
   signatures**. Closes the new Gap E. Effort estimate: very low (a few
   entries in the mapping per cause). The classifier now attributes
   correctly; Kaizen needs to consume the attribution and emit guidance.

**Approach D (single-pass batch synthesis)** remains the larger
unrealized lever for batches under ~15 files. Worth piloting after
Approach A lands — together they would cover ~6 of the 7 cross-file
contract categories in `CROSS_FILE_CONTRACT_RESOLUTION.md`. Not
recommended before Approach A; Approach A is the more bounded change.

---

## 6. Post-authoring addendum (2026-06-01 17:00)

The postmortem layer re-ran between the initial authoring of this
document and the user's review. Two structural changes surfaced:

### Gap C closed: TS2345 signature now fires

`prime-postmortem-report.json:pipeline_attribution` is populated:

```json
[{"stage": "typecheck", "failure_count": 1,
  "root_causes": {"type_class_mismatch": 1}}]
```

PI-010 is now attributed as `typecheck / type_class_mismatch` (was
`unknown / unknown` at original authoring time). Fix 2 from §3 is
shipped. §5 Tier-2 priority list revised accordingly.

### PI-010 expanded error list — strongest evidence yet for Approach A

The 16:55 re-run surfaced four additional findings on `PI-010` beyond
the TS2345:

```
unresolvable_import: @/lib/prisma
prisma_unknown_field: capabilityId
prisma_unknown_field: outcomeId
prisma_unknown_field: text  (on ProofPoint)
```

This is the structurally significant finding of the entire run. **PI-010
was the most expensive feature in the batch** ($0.4194 — 2× average,
consistent with complexity-router tier-3 escalation to Opus). **Even
the highest-capability model invented the same canonical-looking
field/module names** that Sonnet-tier features invented in this run and
in run-008, run-009, run-011. The invention pattern is INVARIANT to
model capability — it's a per-file-locality property of probabilistic
generation, not a capability ceiling.

This validates `CROSS_FILE_CONTRACT_RESOLUTION.md` §4 argument: the root
cause is **the locality of generation, not the absence of inheritance or
the limit of the model**. Approach A's structured project-knowledge
artifact (which provides the LLM with the actual model field set and
the actual module paths, instead of relying on training-distribution
priors) is the structural fix. More inheritance layering and more model
capability won't address it.

### Gap E (new): Kaizen suggestions empty despite classifier firing

`kaizen-suggestions.json` is `{"suggestions": []}` — the classifier
correctly attributes failures with `prisma_unknown_field`,
`unresolvable_import`, `type_class_mismatch` causes, but no Kaizen
suggestions are emitted. The `CAUSE_TO_SUGGESTION` mapping referenced
in `RUN_009_NEXT_STEPS.md` §3 either has no entries for these causes,
or isn't being consulted during postmortem generation. The learning
loop's last mile (cause → actionable suggestion → developer-facing
guidance) isn't closed yet.

Effort to close: very low — a few lookup entries from cause name to a
canonical suggestion ("Look up the actual Prisma model fields in
`prisma/schema.prisma`. Field `<NAME>` doesn't exist on `<MODEL>`.").
Added to §5 Tier 2 as Fix 4.

### Two-source-of-truth still observable

`prime-result.json` (mtime 16:16, the original prime-contractor write)
still records `succeeded: 9 / failed: 1`. The 16:55 postmortem re-run
regenerated the postmortem-side artifacts but did not update
`prime-result.json`. Gap D still open; verification-ledger
consolidation is the structural fix.

---

*Authored 2026-06-01 from the prime-contractor run-011 attempt-1 verdict.
Evidence:
`pipeline-output/startd8/run-011-20260601T1542/plan-ingestion/{prime-result.json,
prime-postmortem-report.json, prime-postmortem-summary.md,
kaizen-suggestions.json}`; direct-fix commit `653b046` on the strtd8 repo
captures the per-file rewrites that closed Gap A and Gap B for the four
broken M4 files. Companions:
`RUN_003_FORWARD_MANIFEST_GAP_POSTMORTEM.md`,
`RUN_007_PARTIAL_DELIVERY_POSTMORTEM.md`,
`RUN_008_CROSS_FEATURE_INCOHERENCE_POSTMORTEM.md`,
`RUN_009_POSTMORTEM.md`,
`CROSS_FILE_CONTRACT_RESOLUTION.md` (the load-bearing architectural
reframe these five postmortems all reinforce).*
