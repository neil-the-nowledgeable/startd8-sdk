# RUN-013 (M6) Postmortem — Sub-Namespace Invention + Type-Narrowing TS2322

**Date:** 2026-06-01
**Run:** `pipeline-output/startd8/run-013-20260601T2025/`
**Score:** 0.60 (3/5 features passed)
**Verdict:** FAIL
**Total cost:** $0.86 ($0.1724 / feature avg; PI-002 outlier at $0.3233 — Opus tier)
**Predecessors:** [RUN_011_M4_FIELD_AND_PATH_INVENTION_POSTMORTEM.md](./RUN_011_M4_FIELD_AND_PATH_INVENTION_POSTMORTEM.md), [RUN_012_M5_REACT_ORG_INVENTION_POSTMORTEM.md](./RUN_012_M5_REACT_ORG_INVENTION_POSTMORTEM.md)
**Companion architectural doc:** [CROSS_FILE_CONTRACT_RESOLUTION.md](./CROSS_FILE_CONTRACT_RESOLUTION.md) §12 — RUN-013 is the third confirmed instance of the "canonical-name discipline domain-by-domain" pattern.

---

## 1. What happened

Run-013 was the first attempt to deliver M6 (Markdown + JSON export — `lib/export/{corpus,markdown,json}.ts`, `app/api/export/route.ts`, `app/export/page.tsx`) via the prime-contractor pipeline. The M6 plan was extended (after RUN-012) with **two** explicit Canonical-name discipline blocks: the data-domain block (validated in RUN-012) and a new frontend-organization-domain block (CSS Modules / barrel imports / top-level `types/` dir — each explicitly prohibited).

**Both discipline blocks held perfectly.** Verification:
- Zero `@/lib/prisma` imports across 5 generated files.
- Zero `*.module.css` imports.
- Zero barrel-import inventions (no `from "@/lib/export"` or `from "@/lib/export/index"`).
- Zero top-level `types/` inventions.
- Zero Prisma field-name inventions.

**But RUN-013 produced 2 new failures in 2 new flavors** — both in domains the plan did NOT explicitly enumerate:

| Flavor | Failed feature | Cost |
|---|---|---|
| **Sub-namespace invention** (`/renderers/` segment that doesn't exist) | PI-004 Export download endpoint | $0.10 |
| **TS2322 ReactNode/unknown type-narrowing** | PI-005 Export trigger UI page | $0.17 |

This is the **third** consecutive run where the plan's discipline blocks countered the previous run's invention category and a new category surfaced.

## 2. Failure attribution

| Feature | Status | Cost | Invented | Plan said |
|---|---|---|---|---|
| PI-001 Export corpus reader | PASS | $0.16 | — | — |
| PI-002 Markdown renderer | PASS (Opus tier) | $0.32 | — | — |
| PI-003 JSON serializer | PASS | $0.10 | — | — |
| PI-004 Export download endpoint | FAIL (cross_file_contract) | $0.10 | `from "@/lib/export/renderers/markdown"` and `from "@/lib/export/renderers/json"` | `lib/export/markdown.ts` and `lib/export/json.ts` (named verbatim in plan §F-401, §F-402) |
| PI-005 Export trigger UI page | FAIL (type_class_mismatch, status:failed) | $0.17 | TS2322: `Type 'unknown' is not assignable to type 'ReactNode'` at line 293 — `signals` map iteration without type narrowing | Plan named the data shape from the F-301 `CompletenessResult` (via `useCompleteness()` of M5) but didn't enumerate that map iteration must narrow the value type before rendering. |

**`pipeline_attribution` rollup populated correctly** for the first time consistently — RUN-012 Gap I (rollup regression) **fully closed**:
```json
[{"stage": "typecheck", "failure_count": 1, "root_causes": {"type_class_mismatch": 1}}]
```

`cross_feature_patterns` reported no cross-feature patterns this run — only 2 failures, no rebucketing possible. The RUN-012 Gap H (cross-feature pattern detection blindness) is still open in principle but didn't surface in this batch.

## 3. Gaps observed

### Gap J — Sub-namespace invention is a new (fourth) flavor of the canonical-name discipline pattern's domain-by-domain limit

PI-004's invented `@/lib/export/renderers/{markdown,json}` is a **plausible-but-wrong sub-namespace organization**. LLM training priors include "renderers live in a `renderers/` subdir" (Rails ActionPack, Django templates, Spring MVC, etc.). The plan named the files explicitly at `lib/export/markdown.ts` and `lib/export/json.ts` — and PI-002 and PI-003 generated them correctly at those paths — but the explicit enumeration was at the **filename** level, not at the **directory structure** level. PI-004 inferred a layer that the plan didn't anticipate.

This adds a **fourth domain** to the canonical-name discipline pattern's whack-a-mole catalog (alongside Prisma fields, CSS Modules, barrel imports, top-level types-dir):

| Discipline domain | Pre-empted in plan | Held in RUN-013 |
|---|---|---|
| Data layer (`@/lib/db`, Prisma fields, Zod schemas) | ✅ | ✅ |
| React component styling (no CSS Modules) | ✅ | ✅ |
| Component registry / barrel imports | ✅ | ✅ |
| Top-level types directory | ✅ | ✅ |
| **Sub-namespace organization** (no `/renderers/`, no `/handlers/`, etc.) | ❌ NOT enumerated | ❌ INVENTED |

**Mode A inheritance evidence:** PI-002 and PI-003 generated their files at the correct paths (`lib/export/markdown.ts`, `lib/export/json.ts`). PI-004 ran AFTER both — the sibling outputs were on disk at the time of PI-004's design context build. **The actual file locations did not propagate.** Third consecutive postmortem with this evidence (RUN-011 PI-010, RUN-012 PI-008 + PI-012, RUN-013 PI-004).

### Gap K — Type narrowing in map iteration is a new TS-content failure mode

PI-005's TS2322 (`Type 'unknown' is not assignable to type 'ReactNode'`) happens when iterating an object like `signals` from `CompletenessResult` and rendering values without narrowing them to `string | number | boolean`. Plain `Object.entries(signals)` returns `[string, unknown][]` and rendering the value into JSX trips TS2322 in strict mode.

This is a **content-level failure** caught by the typecheck stage — not a contract/import failure. The TS2345 classifier signature already shipped catches it. The remediation is small (~3-5 line type narrowing in the page component) but the generation step itself produced unsafe code that the type system rejected.

This is **not new in kind** — TS strict-mode failures are anticipated and caught by the existing classifier — but it's a content failure flavor (map iteration without value narrowing) that may recur in any feature that iterates an `unknown` shape.

### Gap L (carried — RUN-012 Gap H still open)

Cross-feature pattern detection by invention category: with only 2 failures in this run, the heuristic could not fire (insufficient data). Still on the SDK roadmap.

### Gap M — Failed features sometimes never land on disk (PI-005 specifically)

PI-005 status is `failed` (not `complete`) — the file `app/export/page.tsx` was not written to the project tree even though the generation produced a draft (visible at `kaizen-prompts/standalone/PI-005/draft_1_response.md`). RUN-012's failures all had `status:complete` with `verdict:FAIL` — the files were written but flagged. RUN-013 introduced a state where the file is gone but the generation cost ($0.17) was incurred.

For direct-fix triage: the generated draft is still recoverable from `kaizen-prompts/`. **Recommend: SDK pipeline should always persist the generated draft to the project tree even on typecheck failure**, so the direct-fix surface is the draft + 1-line type-narrowing patch, not "write the whole file from spec."

## 4. What's NEW vs RUN-012 (the most recent predecessor)

| Pattern | RUN-012 | RUN-013 |
|---|---|---|
| `@/lib/prisma` family invention | ✅ eliminated | ✅ eliminated |
| Prisma field invention | ✅ eliminated | ✅ eliminated |
| CSS Modules invention | ❌ 3 failures | ✅ **eliminated** (frontend-org discipline block held) |
| Barrel-import invention | ❌ 1 failure | ✅ **eliminated** (same) |
| Top-level types-dir invention | ❌ 1 failure | ✅ **eliminated** (same) |
| Sub-namespace invention (`/renderers/`) | not surfaced | ❌ **1 failure** (NEW Gap J) |
| TS-content type narrowing failure | not surfaced | ❌ **1 failure** (Gap K — minor; classifier catches it) |
| `pipeline_attribution` rollup | ❌ regressed to empty | ✅ **populated reliably** (Gap I closed) |
| Failed features land on disk | ✅ (all `status:complete`) | ❌ PI-005 status:failed, no file (Gap M — new) |
| Opus tier prevents invention | ❌ NO | ❌ NO (no Opus failure this run, but PI-002 at $0.32 Opus tier succeeded — small sample) |
| Mode A inheritance reliable across siblings | ❌ NO | ❌ NO (PI-004 didn't pick up PI-002+PI-003 paths) |

**Net structural progress:** the RUN-012 frontend-organization discipline block is **fully validated** — every category enumerated in it was eliminated in RUN-013. This is **two consecutive postmortems** where an explicit per-domain discipline block held perfectly. The pattern works.

**Net structural regression:** new Gap J (sub-namespace) and new Gap M (failed-feature-not-on-disk). Both fixable with small SDK changes.

## 5. Recommended fixes

### Tier 1 — direct-fix (~15 min)

| Feature | Fix |
|---|---|
| PI-004 | `app/api/export/route.ts`: change `from "@/lib/export/renderers/markdown"` → `from "@/lib/export/markdown"` and `from "@/lib/export/renderers/json"` → `from "@/lib/export/json"`. Two lines. |
| PI-005 | Salvage `kaizen-prompts/standalone/PI-005/draft_1_response.md` to `app/export/page.tsx`. Fix the TS2322: narrow `signals[key]` values via `String(value)` or `typeof value === "number" ? value : 0` before rendering. |

### Tier 2 — plan-level (apply to typescript-plan-m7.md or P2 if any)

Extend the frontend-organization Canonical-name discipline block with a **sub-namespace** clause:

> **No invented sub-namespaces.** When the plan names files at a flat path like `lib/{kind}/markdown.ts`, the import path is `from "@/lib/{kind}/markdown"` — NOT `from "@/lib/{kind}/renderers/markdown"` or any other invented sub-segment. If the plan names a directory structure with subdirectories, it does so explicitly; absent that, assume flat.

Plus a **map iteration narrowing** clause for FR-style features that iterate unknown-shaped data:

> **Map iteration must narrow value types.** `Object.entries(unknownObj)` yields `[string, unknown]` tuples; rendering the value into JSX or any `ReactNode`-typed slot requires explicit narrowing (`String(v)`, `typeof v === "number" ? v : 0`, etc.). Strict-mode TS rejects `unknown` in `ReactNode` positions.

### Tier 3 — SDK-level

- **Fix 8 — new classifier signature `unresolvable_invented_subnamespace`** — fires when an import resolves to a path of the form `@/lib/{X}/{invented}/{file}` where `@/lib/{X}/{file}` exists but the invented sub-segment does not. Would have caught PI-004.
- **Fix 9 — Persist generated drafts on typecheck failure** (closes Gap M). When a feature's draft fails typecheck, write the draft file to the project tree anyway, marked with a status comment. Direct-fix becomes "open file, fix 3 lines" instead of "find the kaizen artifact and copy it over." Low-effort SDK change with high leverage on the operator's direct-fix loop.
- **Fix 5 (carried from RUN-012)** — cross-feature pattern detection by invention category. Still wanted; would have fired in RUN-012 (3 CSS modules) but not in RUN-013 (only 2 failures).

### Tier 4 — already-shipped (validated this run)

- **Fix 2 — TS2345 classifier signature** ✅ caught PI-005's TS2322 (same family).
- **Fix 7 — Pipeline attribution rollup** ✅ populated reliably this run (Gap I closed).
- **Per-domain canonical-name discipline blocks (plan-level pattern)** ✅ second consecutive run where every enumerated category held.

## 6. Why this matters beyond M6

Three consecutive runs (RUN-011, RUN-012, RUN-013) on the same project, each with progressively stronger discipline blocks, each producing a new invention flavor in a domain the plan didn't anticipate. The **whack-a-mole pattern is empirically confirmed** at three independent domain boundaries:

1. RUN-011: Prisma field names (data layer)
2. RUN-012: CSS Modules + barrel imports + top-level types (frontend organization)
3. RUN-013: Sub-namespaces (`/renderers/`) + map-iteration type narrowing

Each new domain costs roughly the same to enumerate (a paragraph in the plan) and pre-empts the same category of failures. But the cost of **finding** which domain to enumerate is paid only AFTER the failure surfaces. This is the strongest case yet that **Approach A (programmatic project-knowledge artifact) is the load-bearing structural fix.** A scanner that enumerates the project's actual import paths, file organization, and naming patterns produces the discipline block automatically — no need for the human to anticipate which domain will surface next.

**The classifier signature approach (Approach B) continues to recouple score with reality.** Each new signature adds a domain to the attributed-failure set. RUN-013 shows the rollup table is reliable; the score (0.60) accurately reflects 3 of 5 deliverable.

## 6.1 Addendum — PI-001/002/003 were marked PASS but were ALSO broken (2026-06-02)

Added during the M6 direct-fix pass (commit `bc147aa`). Documents a new gap surfaced when the human-driven fix workflow ran `npx tsc --noEmit` against the project as a whole and found that the three features the postmortem marked as PASS contained type errors the verdict layer didn't surface.

### What was found

The original verdict table (§2) listed:

| Feature | Postmortem said | Cost |
|---|---|---|
| PI-001 Export corpus reader | PASS | $0.16 |
| PI-002 Markdown renderer | PASS | $0.32 (Opus tier) |
| PI-003 JSON serializer | PASS | $0.10 |
| PI-004 Export download endpoint | FAIL — `cross_file_contract` | $0.10 |
| PI-005 Export trigger UI page | FAIL — `type_class_mismatch`, status:failed | $0.17 |

Running `npx tsc --noEmit` against the project after RUN-013 produced **8 errors** in PI-001's `lib/export/corpus.ts` alone (not counting PI-004's known `/renderers/` issue or PI-005 being missing):

```
lib/export/corpus.ts(148): TS2322 — ProofPointData requires 'text' (Prisma row has no 'text')
lib/export/corpus.ts(153): TS2353 — 'text' does not exist in ProofPointSelect
lib/export/corpus.ts(168): TS2322 — CapabilityData has 'name: string' (Prisma is string | null)
lib/export/corpus.ts(188): TS2322 — OutcomeData requires 'impact' (Prisma has no 'impact')
lib/export/corpus.ts(194): TS2353 — 'impact' does not exist in OutcomeSelect
lib/export/corpus.ts(208): TS2322 — MetricData requires 'label' (Prisma has no 'label')
```

Inspection of `lib/export/markdown.ts` (PI-002, PASS, $0.32 Opus tier) revealed **a different invented field set again** — none of which match either Prisma OR corpus.ts:

| Field referenced in markdown.ts | Real source |
|---|---|
| `profile.tagline` | doesn't exist (Prisma + corpus.ts) |
| `profile.contactEmail` | doesn't exist (Prisma has `email`) |
| `profile.valueSummary` | doesn't exist (lives in `Artifact.dataJson`) |
| `profile.pitches` | doesn't exist (same) |
| `point.situation`, `point.action`, `point.metric` | doesn't exist (real: `title`, `description`, `context`, `result`, `impact`) |
| `capability.level` | doesn't exist (real: `proficiency`) |
| `outcome.title` | doesn't exist (real: `name`) |
| `metric.context` | doesn't exist (real: `description`) |
| `diff.title`, `diff.description` | invented (real Differentiator has `name`, `description`, `evidence`) |
| `prop.title`, `prop.targetRole`, `prop.body` | invented (real ValueProp has `headline`, `subheadline`, `body`, `audience`) |

Inspection of `lib/export/json.ts` (PI-003, PASS, $0.10) found it had locally re-declared every type as `Record<string, unknown>`, so type-checking against the real corpus shape was effectively bypassed — the file compiled cleanly because it had abandoned types entirely.

**All five M6 features were broken.** The postmortem PASS verdicts for PI-001/002/003 were wrong.

### Why the verdict layer missed this

The classifier signatures that fired in RUN-013 caught:

- **PI-004**: TS2307 (`unresolvable_import`) at the cross-file contract layer — fired because `route.ts` imports `@/lib/export/renderers/markdown` and that path doesn't exist on disk
- **PI-005**: TS2322 (`type_class_mismatch`) at the typecheck stage — fired because the page's `Object.entries(signals)` map iteration rendered an `unknown` into a `ReactNode` slot

What the classifier did NOT catch:

- **PI-001's TS2322/TS2353 errors** between the file's declared `ProofPointData` type and the actual `Prisma.ProofPointSelect` shape — these are **intra-file type mismatches**, not cross-file contract violations
- **PI-002's mismatch between markdown.ts's field references and the type signatures declared in corpus.ts** — this WOULD fire as a TS2339 / TS2551 error in a proper compilation, but apparently didn't reach the verdict layer
- **PI-003's local type erasure** — `Record<string, unknown>` everywhere means tsc has nothing to check; no errors are emitted, so the classifier sees clean output

The shared property of the missed failures: **the type mismatch is contained within a single feature's file boundary** OR **the file's types are too loose to fail compilation**. The classifier appears to run per-file or per-import-graph-fragment, not against the whole project as a single compilation unit. Cross-file contract violations (where file A references a symbol or path that file B was supposed to provide but didn't) reliably surface. Intra-file content errors do not.

### New Gap N — Per-feature typecheck is not project-wide typecheck

The TS2345 / TS2322 classifier signature (Fix 2, shipped 2026-06-01) catches what happens when the LLM emits TypeScript that fails compilation **in isolation**. But run-013 evidence shows the verdict layer's typecheck stage is running **per feature**, not against the assembled project. Consequence: a feature whose declared types are internally consistent BUT semantically wrong against the rest of the project's true types passes the per-feature gate.

The simplest signature that would catch RUN-013's PI-001 failure: **run `npx tsc --noEmit` against the project root after each feature's outputs are merged**, treating the resulting errors as additional attributable failures even if the per-feature gate passed. This requires:

1. The project's `tsconfig.json` already exists (it does for any non-trivial Next.js / TS project)
2. Adding a post-merge typecheck step after each feature's outputs land
3. Bucketing the emergent errors back to the feature whose outputs introduced them (which is straightforward: the file paths in the error messages map to the features that wrote them)

This is **Fix 10** on the SDK roadmap and would have changed RUN-013's verdict table from `3 PASS / 2 FAIL` to `0 PASS / 5 FAIL` — accurate.

### Implications

1. **The "score-vs-reality recoupled" claim from CROSS_FILE_CONTRACT_RESOLUTION §12.4 is partial.** Score is recoupled with reality at the cross-file contract layer (where Fix 2 fires); it is NOT recoupled at the intra-file type-correctness layer. RUN-013 has 3 examples of this gap.

2. **The "3 of 5 deliverable" framing in §6 of this postmortem is wrong** — the correct framing is "0 of 5 deliverable until the direct-fix pass at commit `bc147aa` rewrote three of them and fixed the other two."

3. **The "$2.20 total cost spent on broken outputs" framing also requires update.** In RUN-013 specifically: the entire $0.86 was spent on outputs that did not function end-to-end. The 3 PASS-marked features still had to be rewritten by hand.

4. **Approach A's argument strengthens further.** A pre-flight project-knowledge artifact that enumerates the real Prisma field set would have eliminated every one of PI-001/002/003's intra-file invention failures (they're all Prisma-field invention at the file-internal level). The case for Approach A as the load-bearing structural fix is now supported by 4 independent failure modes across 3 runs.

5. **Fix 10 (project-wide typecheck post-merge) is now on the SDK roadmap.** Its absence is exactly why RUN-013's verdict layer missed PI-001/002/003. Implementation cost is low; leverage is high.

### Reconciled RUN-013 verdict table

| Feature | What classifier said | Reality | $ |
|---|---|---|---|
| PI-001 Export corpus reader | PASS | BROKEN (8 internal TS errors: invented `text`/`impact`/`label` fields + `name: string` vs `string \| null` mismatch) | $0.16 |
| PI-002 Markdown renderer | PASS (Opus tier) | BROKEN (references ~12 invented fields that exist in NEITHER Prisma NOR corpus.ts) | $0.32 |
| PI-003 JSON serializer | PASS | BROKEN-BY-OMISSION (locally redefined every type as `Record<string, unknown>` to bypass type-checking) | $0.10 |
| PI-004 Export download endpoint | FAIL — `cross_file_contract` | Same — invented `/renderers/` sub-namespace | $0.10 |
| PI-005 Export trigger UI page | FAIL — `type_class_mismatch`, status:failed | Same — never landed on disk; draft salvaged from kaizen-prompts/ | $0.17 |

**Real verdict: 0 of 5 deliverable. Real direct-fix surface: full rewrite of 3 lib files + 1 import fix + 1 new page from scratch.**

## 7. Recommended next steps

1. ✅ **Tier 1 direct-fixes** — PI-004 (2 lines) + PI-005 (salvage draft + type-narrow). ~15 min.
2. **Extend M6 smoke test** — `tests/e2e/m6-smoke.spec.ts`: GET /api/export?format=md and ?format=json return correct content-type, /export renders, round-trip-fidelity assertion (JSON→Markdown byte-identity from the parsed corpus).
3. **Layout integration** — add `<Link href="/export">Export</Link>` to `app/layout.tsx` nav (matches the M5 post-batch pattern; layout is anchored, batch did not regenerate it).
4. **Tier 2 plan-level discipline extension** — only applicable if there's another batch after M6. P2 (JD ingest, asset generation) would surface a new set of domains; the discipline block grows again.
5. **Tier 3 SDK fixes (Fix 8 + Fix 9)** — independent of strtd8 delivery. Fix 9 (persist failed drafts to disk) has the highest leverage per LOC on the operator's direct-fix workflow.
6. **Update [CROSS_FILE_CONTRACT_RESOLUTION.md §12](./CROSS_FILE_CONTRACT_RESOLUTION.md)** with the RUN-013 sub-namespace evidence — third confirmed instance further strengthens the §12.1 case that per-domain discipline blocks are whack-a-mole and Approach A is the structural fix.
