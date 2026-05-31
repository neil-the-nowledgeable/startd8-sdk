# Partial Delivery via Micro-Prime Stub Fallback — Postmortem & Remediation

**Date:** 2026-05-31
**Trigger incident:** prime-contractor run `run-007-20260531T1041` reported `16/16
succeeded` with verdict **PASS** (score 0.94), but **9 of 16 generated files are
3-line empty-class stubs** of the form `export class <file-basename> { }`. Net
functional delivery is **~6/16 features**; the pipeline's own bookkeeping
reports 100%.
**Headline finding:** the Forward Manifest repair (commits `b6212419`,
`1c9c15a8`, `0d31cc51`) closed the **registry-matched** instance of the
RUN_003 PI-003 failure (`next.config.mjs` now generates correctly), but the
**same root cause** — drafter emits the file basename as a class identifier
when no real specification is available — has regressed at a **different layer**:
the **micro-prime SIMPLE-tier template path** falls through to an empty-class
stub for every file outside `FRAMEWORK_CONFIG_DEFAULTS`. The postmortem
classifier doesn't see it, and the pipeline's three success counts
(`prime-result.json`, `prime-postmortem-summary.md`, on-disk reality) disagree
with each other.

---

## 1. What happened

The prime-contractor run executed against an M1-M2 ingested seed (16 features).
It processed **all 16 features and self-reported success on all of them**, but
9 of the produced files are syntactically-valid empty-class stubs and 1 file
the postmortem flagged as failed (`tsconfig.json`) is actually production-quality.

| Order | Feature | Target file | Result reported | Cost | Reality |
|-------|---------|-------------|-----------------|------|---------|
| PI-001 | package.json scaffold | `package.json` | ✅ | $0.0914 | ✅ GOOD (Next 14 / React 18 / Prisma 5 / Zod 3) |
| PI-002 | tsconfig.json scaffold | `tsconfig.json` | ✅ in `prime-result`, ❌ in `prime-postmortem` | $0.1088 | ✅ GOOD (production-quality strict TS config) |
| PI-003 | next.config.mjs scaffold | `next.config.mjs` | ✅ | **$0.0000** | ✅ GOOD (registry-templated) **— RUN_003 fix confirmed working** |
| PI-004 | Environment config | `.env.example` | ✅ | $0.1237 | ✅ GOOD |
| PI-005 | typed env getters | `lib/env.ts` | ✅ | **$0.0000** | ❌ **STUB** — `\nexport class env {\n\n}` |
| PI-006 | prisma datasource | `prisma/schema.prisma` | ✅ | $0.0691 | ✅ GOOD (superseded by PI-010) |
| PI-007 | Prisma client singleton | `lib/db.ts` | ✅ | **$0.0000** | ❌ **STUB** — `\nexport class db {\n\n}` |
| PI-008 | base layout | `app/layout.tsx` | ✅ | **$0.0000** | ❌ **STUB** — `\nexport class layout {\n\n}` |
| PI-009 | landing page | `app/page.tsx` | ✅ | **$0.0000** | ❌ **STUB** — `\nexport class page {\n\n}` |
| PI-010 | full Value Model schema | `prisma/schema.prisma` | ✅ | $0.1299 | ✅ GOOD (179 lines, full graph) |
| PI-011 | Zod ValueModel | `lib/value-model.ts` | ✅ | **$0.0000** | ❌ **STUB** — `\nexport class value-model {\n\n}` **(invalid JS identifier — hyphen)** |
| PI-012 | Profile API route | `app/api/profile/route.ts` | ✅ | **$0.0000** | ❌ **STUB** — `\nexport class route {\n\n}` |
| PI-013 | Profile capture form | `app/profile/page.tsx` | ✅ | **$0.0000** | ❌ **STUB** — `\nexport class page {\n\n}` |
| PI-014 | ProofPoint collection API | `app/api/proof-points/route.ts` | ✅ | **$0.0000** | ❌ **STUB** — `\nexport class route {\n\n}` |
| PI-015 | ProofPoint item API | `app/api/proof-points/[id]/route.ts` | ✅ | **$0.0000** | ❌ **STUB** — `\nexport class route {\n\n}` |
| PI-016 | ProofPoint library UI | `app/proof-points/page.tsx` | ✅ | $0.3070 | ✅ GOOD (1063-line React component, `"use client"`) |

**The smoking gun is the cost column.** Every broken stub has cost **$0.0000**
— no LLM call was made. All 9 broken features hit the same code path: the
**micro-prime SIMPLE-tier template** at `src/startd8/micro_prime/engine.py`.
PI-003 (`next.config.mjs`) ALSO hit this path with $0.0000 cost but produced
correct output, because `FRAMEWORK_CONFIG_DEFAULTS` (added by commit
`1c9c15a8`) contains a real skeleton for `next.config.{js,mjs,ts}`. The
postmortem confirms the population: *"Micro Prime Analysis: Total elements: 10,
Successful: 10, Escalated: 0, Tier distribution: simple: 10."* — exactly the
1 registry-templated + 9 fall-through-to-empty-stub split.

The drafter's emitted code for `app/profile/page.tsx` (3 lines, 23 bytes):

```typescript

export class page {

}
```

Mechanism: the micro-prime SIMPLE-tier path consults the framework conventions
registry for a template; on no match, it falls back to a generic
`export class <basename> { }` skeleton derived from the file basename. The
basename is the same identifier-extraction rule that produced
`export class next.config { }` in RUN_003 PI-003 (now closed by the registry
entry, but the rule itself was never removed — only deflected for the
registry-matched cases).

The postmortem layer reported:

- **Verdict:** PASS (score 0.94)
- **Total features:** 16, **Successful:** 15, **Failed:** 1
- **Sole failed feature:** PI-002 (`tsconfig.json scaffold`) with
  *"Root cause: unknown / Pipeline stage: unknown / Error: (none) / Cost:
  $0.1088"* — but `tsconfig.json` on disk is 60+ lines of production-quality
  strict TS config. **The postmortem mis-flagged a healthy feature as failed
  and silently passed nine broken ones.**

So the postmortem produced an actively misleading summary: it claims one
healthy file is broken, claims nine broken files are healthy, and reports a
0.94 quality score on a run that delivered ~38% of attempted features.

---

## 2. The gaps this incident exposes

Three structural gaps. Each is independently true; together they explain the
silent partial delivery.

### Gap A — Micro-prime SIMPLE-tier falls back to an empty-class stub when no registry template matches

The RUN_003 Forward Manifest repair added a `FRAMEWORK_CONFIG_DEFAULTS`
registry (Fix 2 in `RUN_003_FORWARD_MANIFEST_GAP_POSTMORTEM.md`). When a
target path matches a registered pattern — `next.config.{js,mjs,ts}`,
`tsconfig.json`, `package.json`, `prisma/schema.prisma`, etc. — the
micro-prime path produces a real skeleton. For paths **outside** the registry,
the same SIMPLE-tier code path falls through to a generic
`export class <basename> { }` template (derived from the file basename) and
the feature is marked successful.

Evidence from RUN_007:

- `FRAMEWORK_CONFIG_DEFAULTS` matched: `next.config.mjs` (PI-003) →
  registry skeleton with `defineConfig` import → ✅
- `FRAMEWORK_CONFIG_DEFAULTS` did NOT match: `lib/env.ts`, `lib/db.ts`,
  `lib/value-model.ts`, `app/layout.tsx`, `app/page.tsx`,
  `app/profile/page.tsx`, `app/api/profile/route.ts`,
  `app/api/proof-points/route.ts`, `app/api/proof-points/[id]/route.ts`
  (9 features) → `export class <basename> { }` stubs → ❌
- All 9 fall-through-cases were classified **SIMPLE** tier by the complexity
  router (escalated: 0). All cost **$0.0000** (no LLM call).

This is the **same root cause** as RUN_003 PI-003 — the drafter / template
path derives a class identifier from the file basename when no real
specification is available. Fix 2 (registry) deflected the
registry-matched cases. The general case is unfixed.

The MVP-typical Next.js project has ~70% of its files outside the framework-
config set (layouts, pages, API routes, libs, types). Registry-only coverage
is structurally insufficient for any realistic delivery.

### Gap B — Complexity classifier routes non-trivial files to the no-LLM SIMPLE tier

For the micro-prime fallback to fire, the complexity router has to classify a
feature as SIMPLE. RUN_007 classified **10 of 16 features as SIMPLE**,
including:

- `lib/value-model.ts` — Zod schema mirror of the full Value Model graph (the
  canonical type system; not simple by any sane reading)
- `app/profile/page.tsx` — full Profile capture form with API integration
- `app/api/proof-points/[id]/route.ts` — full CRUD route with three verbs

These were classified SIMPLE because the seed's complexity signals
(`estimated_loc`, `blast_radius`, `target_file_count`) are derived heuristically
from the plan-ingestion text and don't capture the actual implementation
surface. SIMPLE-tier features skip the LLM and consult the registry. When the
registry doesn't have an entry (Gap A), the empty-stub fallback fires.

Evidence: postmortem reports *"Tier distribution: simple: 10. Escalated: 0."*
Zero escalations means the SIMPLE path never had a "I don't know what to
generate" signal that would have promoted these to a real LLM call.

### Gap C — Postmortem classifier is blind to the empty-stub signature AND reports false failures

Two distinct postmortem-layer defects:

**C-1 — False negatives on the empty-stub signature.** The output
`export class <basename> { }` is syntactically valid JavaScript (in 8 of 9
cases — `value-model` has a hyphen and would fail to parse). It passes the
Node syntax check that caught RUN_003 PI-003. The postmortem classifier (the
target of RUN_003 Fix 3) was specced against captured `SyntaxError` /
`ParseError` output, but the new failure mode is **shape-level wrongness with
clean syntax**: empty classes, file-basename-as-identifier, content length
well below feature scope. The classifier has no signature for this and marks
9 features successful that are not.

**C-2 — False positive on PI-002.** The classifier marks
`tsconfig.json scaffold` as the **only** failure with *"Root cause: unknown
/ Pipeline stage: unknown / Error: (none) / Cost: $0.1088"* — but the
on-disk `tsconfig.json` is 60+ lines of production-quality config. The
"Error: (none)" with "unknown" root cause is the same `unknown / unknown`
signature RUN_003 Fix 3 was supposed to close. Fix 3 has not shipped; the
classifier has gotten worse rather than better, since it now fabricates a
failure where there isn't one while missing nine real ones.

Net: the postmortem is **actively misleading**, not just incomplete. A
reader trusting the report would conclude that PI-002 needs fixing and
everything else is fine.

### Gap D — Three success counts disagree

For the same 16 features:

| Source | Path | Reports |
|--------|------|---------|
| Prime contractor | `prime-result.json` | `succeeded: 16, failed: 0, success: true` |
| Postmortem | `prime-postmortem-summary.md` | `Successful: 15, Failed: 1 (PI-002)` |
| Reality | on-disk files | ~6 functional, ~9 stubs, 1 file (PI-002) the postmortem says failed but is actually fine |

There is no single source of truth for "did this feature deliver." Downstream
consumers (Kaizen aggregator, batch ledger, future Plan Batch Orchestration
gates) pick one of the three and inherit its blind spots. The Kaizen
suggestions for RUN_007 are an empty array (`"suggestions": []`) — the
learning loop did not fire on a run that delivered roughly a third of what
it claimed.

---

## 3. How to close the gaps

Three fixes, ordered by leverage and increasing scope.

### Fix 1 — Replace the micro-prime empty-stub fallback with an escalation path (highest leverage, smallest blast radius)

**What:** in the micro-prime SIMPLE-tier code path, when no
`FRAMEWORK_CONFIG_DEFAULTS` entry matches the target path **and** no
plan-declared `ForwardFileSpec.elements[]` is non-empty, the path MUST
**either** (a) escalate to the next tier (real LLM call) or (b) refuse to
ship the feature with a structured `MissingTemplateError`. It MUST NOT emit a
generic `export class <basename> { }` skeleton.

**Why:** the empty-stub fallback is the **identifier-extraction rule from
RUN_003 PI-003 surviving inside a different code path**. Removing the
fallback closes the failure mode by construction (the bad output cannot be
emitted) instead of trying to enumerate every possible target path in a
registry. Escalation preserves the cost-routing intent of micro-prime for
genuinely simple files; refusal would surface as a real failure the
postmortem can act on. Either is acceptable; escalation is preferred because
it ships output rather than blocking.

**Acceptance / validation:**

- A regression test reproducing RUN_007: construct a minimal seed with a
  task targeting `lib/value-model.ts` (no registry match, no
  plan-declared elements); run prime-contractor; assert the produced file is
  either (a) a real Zod schema module (escalation) or (b) the feature is
  marked failed (refusal) — assert **never** an `export class <basename> { }`
  stub.
- A unit test on the micro-prime path: feed a target path that does not
  match `FRAMEWORK_CONFIG_DEFAULTS` with empty `ForwardFileSpec.elements`;
  assert the path raises `MissingTemplateError` or returns an
  `EscalationRequest` rather than the basename-class template.
- Cost regression: the genuine SIMPLE-tier cases (PI-003 next.config.mjs,
  package.json, tsconfig.json) MUST still hit the registry path at
  $0.0000.

**Closes:** Gap A directly. Reduces pressure on Gap B (a wrong SIMPLE
classification now escalates instead of silently shipping a stub).

### Fix 2 — Empty-stub classifier signatures in the postmortem

**What:** the prime-postmortem / Kaizen classifier (the surface from
RUN_003 Fix 3) MUST add at least two pattern detectors that run after
generation, before the success/fail decision is recorded:

1. **Empty-class-with-basename-identifier.** Pattern: file content is
   `\nexport class <basename> {\n\n}\n` (or its 3-line variant); flag as
   `drafter_template_fallback`. Apply to every generated file; not gated on
   SyntaxError capture (the failure mode is shape-level, not syntactic).
2. **Below-spec content length.** Pattern: generated file content length is
   under a per-task-shape minimum (e.g., 100 bytes for any
   `app/**/page.tsx` or `app/api/**/route.ts`); flag as
   `output_below_specified_scope`.

A match on either pattern MUST mark the feature as failed regardless of
syntax-check outcome, classify the pipeline stage as
**`drafter / micro-prime template fallback`**, attribute root cause as
**`drafter emitted basename-class stub; no registry match and no
plan-declared elements`**, and emit at least one Kaizen suggestion (e.g.,
*"add path-shape entry to FRAMEWORK_CONFIG_DEFAULTS for this pattern, or
investigate why complexity classifier routed this to SIMPLE tier"*).

**Why:** the postmortem must be able to detect the failure mode that
*actually shipped* in production, not just the one that broke parsing in
RUN_003. The reader's experience of the postmortem must align with
reality before the learning loop can usefully fire.

**Acceptance / validation:**

- A reproduction of any RUN_007 broken file produces a non-`unknown` stage,
  a non-`unknown` root cause, and at least one Kaizen suggestion.
- A reproduction of PI-002 (production-quality `tsconfig.json`) produces a
  SUCCESSFUL classification — the current `unknown / unknown / Error: (none)`
  false positive is eliminated.
- The classifier table is testable from a small fixture of raw file
  contents; no LLM call required.

**Closes:** Gap C (both C-1 and C-2).

### Fix 3 — One success count, sourced from on-disk verification

**What:** `prime-result.json` and `prime-postmortem-summary.md` MUST consult
the same per-feature success record, derived from **a single
post-generation verification pass** that runs after each feature's files are
written. The verification pass executes both Fix-2 signature checks plus the
existing syntax check, and writes its verdict to a **shared verification
ledger** (a new artifact, e.g.,
`plan-ingestion/generated/verification-ledger.json`) keyed by `feature_id`.
Both summary writers read from this ledger; neither computes its own count.

**Why:** today, `prime-result` records success at the orchestration layer
(did the generator return without raising?), `prime-postmortem` recomputes
from its own classifier, and on-disk reality reflects what was actually
written — three independent definitions of "success." A single ledger
sourced from on-disk content guarantees the three counts agree by
construction and that future downstream consumers (Kaizen aggregator, batch
ledger, Plan Batch Orchestration's FR-4 gate) inherit one source of truth.

**Acceptance / validation:**

- After any prime-contractor run, `prime-result.json` and
  `prime-postmortem-summary.md` report **identical** per-feature
  success/fail counts. A multi-batch run with one synthetic stub failure
  produces matching `1 failed` in both surfaces.
- The verification ledger is the only writer of per-feature success and is
  inspectable independently of the two summary surfaces.
- Backwards compatibility: existing downstream consumers reading either
  surface continue to work; the difference is the surfaces now agree.

**Closes:** Gap D. Makes Fix-2's classifier outputs visible to every
downstream consumer.

---

## 4. Why this matters beyond run-007

- **Same root cause, third layer.** The "drafter emits the file basename as
  a class identifier when no specification is available" rule survived two
  prior remediation passes (the Fix 1 + Fix 2 from
  `RUN_003_FORWARD_MANIFEST_GAP_POSTMORTEM.md`). Fix 1 wired the spec to the
  draft prompt; Fix 2 added a registry. Neither removed the **template
  fallback itself** — they only ensured it would be deflected for some files.
  RUN_007 shows the fallback is still firing for the broader file
  population that any real MVP touches. The rule must be removed
  (Fix 1 of this postmortem), not further deflected.
- **The Forward Manifest design treated framework configs as the canonical
  "empty file_spec" case.** Real plans don't enumerate internals for ~70%
  of files (every UI component, every API route, every library module).
  The registry-expansion path scales poorly; the escalate-or-refuse path
  closes the failure by construction. This is the registry-sprawl risk
  the original FR-7 warned about, now observed.
- **The pipeline's success bookkeeping is the load-bearing input to every
  downstream consumer.** Plan Batch Orchestration's FR-4 gate, FR-7
  provenance, R2-F2 quality summary, and the future R3 essential-MVP
  rewrite all rest on per-feature success/fail being correct. While today's
  bookkeeping reports PASS on a 38%-functional run, every downstream
  capability builds on sand.
- **Fixes 1 + 2 together would have surfaced this run-007 partial delivery**
  as a real failure rather than a PASS verdict. Without those, no run of any
  scope can be trusted to mean what it says.

---

## 5. Recommended next step

Spec the **Fix 1 + Fix 2** package as a small reflective-requirements + plan
pair (the scope is small enough that the planning pass can verify the
micro-prime path's fallback site and the postmortem classifier's
extension surface in one read). Defer **Fix 3** (verification ledger
unification) as a separate, slightly larger change — it is a refactor of how
three artifacts agree on a single record, and is best done after Fix 1 + 2
have produced a postmortem-detectable signal worth recording. Fix 3 also
overlaps with the Plan Batch Orchestration R2-F2 / R3 essential-MVP work
(both want a single verification record); align scopes before specifying.

---

*Authored 2026-05-31 from the prime-contractor run-007 partial delivery.
Evidence:
`pipeline-output/startd8/run-007-20260531T1041/plan-ingestion/{prime-result.json,
prime-postmortem-summary.md, prime-context-seed-enriched.json}`;
generated files at the project root; code:
`src/startd8/micro_prime/engine.py`,
`src/startd8/forward_manifest_extractor.py` (`FRAMEWORK_CONFIG_DEFAULTS`),
`src/startd8/complexity/classifier.py`,
`src/startd8/implementation_engine/{spec_builder.py, drafter.py}`.
Companion: `RUN_003_FORWARD_MANIFEST_GAP_POSTMORTEM.md` (whose Fix 1+2
closed the registry-matched case; whose Fix 3 has not shipped and whose
absence is part of this incident).*
