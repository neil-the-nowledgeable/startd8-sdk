# Cross-File Contract Resolution — What the RUN_009 Build-Fix Pass Revealed, and What Mode A / Mode B Aren't Enough To Solve

**Date:** 2026-06-01
**Status:** Architectural design — not a postmortem
**Companions:** `RUN_003_FORWARD_MANIFEST_GAP_POSTMORTEM.md`, `RUN_007_PARTIAL_DELIVERY_POSTMORTEM.md`, `RUN_008_CROSS_FEATURE_INCOHERENCE_POSTMORTEM.md`, `RUN_009_POSTMORTEM.md`
**What this doc is:** A consolidation of the contract-drift evidence accumulated across four postmortems plus the live-fire RUN_009 attempt-2 direct-fix pass. The previous postmortems frame failure modes incident-by-incident. This doc steps back: it enumerates what the build-fix pass actually surfaced, what those findings mean for the Mode A / Mode B inheritance distinction proposed in `RUN_009_POSTMORTEM.md`, and what structurally superior approaches address the root rather than the next layer.

**Headline claim:** Mode A (intra-batch sibling-output inheritance) and Mode B (pre-existing-upstream inheritance) are necessary but not sufficient. They address **module-path propagation**, which is one narrow slice of the contracts a multi-file system needs. The RUN_009 attempt-2 build-fix pass surfaced **~16 distinct cross-file contract failures** that span seven categories of contract; only one of those categories is covered by Mode A as implemented today. Closing the gap requires a different shape of fix than another inheritance mode.

---

## 1. What the build-fix pass actually surfaced

After RUN_009 attempt-2 reported PASS / 13-of-13 / score 1.00 (and the M1 ship set was restored, the 5 invented `@/lib/prisma` imports were corrected, Zod was expanded against Prisma, and the run-009 generated files were committed), `npm run build` was attempted end-to-end. The build required **~11 additional contract fixes** beyond the punchlist's anticipated 9 steps to reach a green exit. Combined with the punchlist's pre-build fixes, that totals **~16 distinct cross-file failures** across the 13-file batch:

| # | Site | Failure | Category |
|---|------|---------|----------|
| 1 | 5 files | Invented `@/lib/prisma` import path (real path is `@/lib/db`) | **module-path** |
| 2 | 1 file | Invented `@/lib/logger` import path | **module-path** |
| 3 | 2 files | Imported `pino` not in `package.json` | **dependency-availability** |
| 4 | `next.config.mjs` | `import { defineConfig } from 'next'` — not a real export | **external-library-API** |
| 5 | `tsconfig.json` | `"@/*": ["./src/*"]` — project has no `src/` dir | **project-config** |
| 6 | `prisma/schema.prisma` | `Artifact.dataJson` field absent; M3 code expects it | **canonical-schema** |
| 7 | `app/api/profile/route.ts` | Type cast to loose `Record` shape stripped Zod inference's `name`-is-required signal | **type-signature** |
| 8 | `app/api/proof-points/[id]/route.ts` | 4 compound-key queries `id_ownerId: { ... }` — constraint doesn't exist in Prisma | **canonical-schema** |
| 9 | `app/api/proof-points/route.ts` | Destructured `capabilityIds`/`outcomeIds` from `ProofPointSchema` — fields not in canonical Zod | **api-request-shape** |
| 10 | `app/api/ai/artifacts/route.ts` | 2 unused `request` params on GET/POST | **type-signature** |
| 11 | `lib/ai/service.ts` | `Anthropic.ContentBlockParam` — doesn't exist; correct name `TextBlockParam` | **external-library-API** |
| 12 | `lib/ai/service.ts` | AiCall fields `inputTokens`/`outputTokens` — Prisma has `promptTokens`/`responseTokens` | **canonical-schema** |
| 13 | `lib/ai/extract.ts` | `sanitizeProofPoint` destructured `claim`/`category` — neither in ProofPoint model | **canonical-schema** |
| 14 | `lib/ai/artifacts.ts` | `dataJson: { ... }` object literal — SQLite has no native JSON; needs JSON.stringify | **canonical-schema** |
| 15 | `app/proof-points/page.tsx` | `ProofPointListItem` uses `body` field — not in Prisma ProofPoint (runtime only; build passes) | **api-response-shape** |
| 16 | Pages with `useEffect+fetch` | Static pre-render attempted DB calls; pages need `export const dynamic = 'force-dynamic'` | **framework-rendering-mode** |

Counts by category:

| Category | Failures | Cross-file scope |
|----------|---------:|------------------|
| **canonical-schema** (Prisma model fields, types, constraints) | 5 | Prisma → multiple consumers |
| **module-path** (where imported symbols live) | 6 | Producer file → consumer files |
| **external-library-API** (SDK exports, function names) | 2 | LLM hallucinated vs the installed package |
| **type-signature** (function params, type casts) | 2 | Local file errors but reveal LLM unaware of type system |
| **dependency-availability** (what's in `package.json`) | 1 (×2 files) | Generated code → project manifest |
| **api-request-shape** / **api-response-shape** | 2 | API producer ↔ API consumer (UI ↔ route) |
| **project-config** (tsconfig, next.config) | 2 | LLM unaware of project layout / framework conventions |

**The single Mode-A-relevant category — module-path — accounts for 6 of 16 failures.** The other 10 are categories Mode A doesn't even attempt to address.

---

## 2. What this means for Mode A

Mode A (intra-batch sibling-output inheritance) **demonstrably works** for the category it addresses:

- Producer F-101 emitted `lib/value-model.ts`; consumers F-102, F-103, F-105, F-106 all imported from the correct `@/lib/value-model` path. **Real progress over RUN_008.**
- Producer F-104 emitted `lib/ai/service.ts`; consumers F-105, F-106 imported from the correct `@/lib/ai/service` path.
- Producer F-105 emitted `lib/ai/extract.ts`; consumer (the extract API route) imported from the correct path.
- Producer F-106 emitted `lib/ai/artifacts.ts`; consumer (the artifacts API route) imported from the correct path.

Four producer/consumer chains, all module-path coherent. Mode A is a real fix for module-path inheritance.

But Mode A's scope ends there. It does not address:

- **Symbol shape**: F-101 emits `ProofPointSchema` — Mode A propagates the import path but not the field set. F-105's `sanitizeProofPoint` invents `claim`/`category` fields the Zod schema doesn't have. Mode A had nothing to say about this — it's a content-level disagreement, not a name-level one.
- **External library APIs**: Mode A only propagates names from same-batch siblings. The Anthropic SDK isn't a sibling — it's an external dependency. F-104 hallucinated `Anthropic.ContentBlockParam` (a plausible-looking but nonexistent type). Mode A doesn't read installed packages.
- **Dependency manifest**: Two files imported `pino`, which isn't in `package.json`. Mode A doesn't consult `package.json`.
- **Project configuration**: `tsconfig.json` had a path alias pointing at a nonexistent `src/` directory. The drafter never read the tsconfig to verify the path-alias mapping matched the file layout.

**Mode A is a tiny — but real — slice of the cross-file contract problem.** It solves the "where does this module live" question for the simplest case (same batch, same producer/consumer pair). It does not solve the seven other categories. RUN_009 attempt-2's 4 Mode-A successes are real wins; the 12+ other failures are categories Mode A wasn't designed to address.

---

## 3. What this means for Mode B

Mode B (pre-existing-upstream inheritance) **was hypothesized in RUN_009_POSTMORTEM.md §6 but cannot be cleanly observed in RUN_009 attempt-2** because the M1 ship-set anchors were missing from disk when the run started (already-wiped from earlier `--fresh` invocations; never git-committed). The 6 invented `@/lib/prisma` references are consistent with two equally-plausible explanations:

- **Mode B is unimplemented**, so the drafter never consults pre-existing files and falls back to canonical-looking guesses.
- **Mode B is implemented but had no upstream to read** (M1 anchors were already gone).

Either way, the build-fix pass added a third observation that disambiguates against Mode B as a complete solution:

> **Even with `prisma/schema.prisma` on disk and inherited (the Zod expansion successfully read it field-by-field), 5 of the 16 contract failures were `canonical-schema` mismatches — fields the schema does not contain, type-class mismatches, missing-field references.** The drafter had access to the schema (the Zod expansion proved that). It still produced code that uses `inputTokens`/`outputTokens` against an `AiCall` model that has `promptTokens`/`responseTokens`. It still invented `claim`/`category` on ProofPoint. It still wrote `id_ownerId` compound queries against a model with no such constraint.

So even if Mode B were perfectly wired — even if every feature could read every relevant pre-existing file at generation time — **content-level field-name and type-class drift would still occur**. Mode B addresses "what's the import path" with a wider scope than Mode A; it does not address "what fields/types does this referenced thing have."

**Mode B is Mode A's same-shape extension to a different scope.** Both modes solve the module-path category. Neither solves the canonical-schema, external-library-API, type-signature, dependency-availability, api-shape, or project-config categories.

This is the load-bearing finding. The architecture that solves RUN_008 → RUN_009 by extending inheritance to more scopes will not solve the seven categories where the failure is content-level disagreement, not path-level disagreement.

---

## 4. The deeper pattern

The drafter operates as a **per-file probabilistic generator**. For each file in isolation, it independently decides:

1. **Module paths** — where to import from (the `@/lib/prisma` invention case)
2. **Module export shapes** — what symbols a target module exports (the `Anthropic.ContentBlockParam` hallucination)
3. **Field names** — what columns a Prisma model has (`inputTokens` vs `promptTokens`)
4. **Field types** — what TypeScript type a column maps to (Metric.value as `number` vs `string`)
5. **API shapes** — what fields a request/response body carries (UI's `body` field on ProofPoint)
6. **External SDK surface** — what methods/types a third-party library exposes
7. **Dependencies** — what's available in node_modules (the pino case)
8. **Project conventions** — tsconfig path aliases, framework config patterns
9. **Naming conventions** — singular vs plural, default vs named exports

**Each decision is local.** Nothing in the drafter's process forces it to consult an authoritative source for any of these. When it guesses correctly (because the canonical convention matches its training data, or because Mode A propagated a producer's choice), the file works. When it guesses incorrectly, the file silently disagrees with its siblings or its environment.

The current Fix 1 (Mode A) propagates **one** decision (module path) for **one** producer/consumer relationship (intra-batch siblings). The drafter still makes the other eight categories of decision locally and probabilistically. Each is a coin-flip for cross-file coherence.

For a multi-file system with N files and K decision categories per file, the cross-file coherence probability under per-file probabilistic generation is roughly `p^(N×K)` where `p` is the per-decision-correctness probability. Even at `p=0.95` and modest N×K, the system-coherence probability collapses fast. RUN_009 attempt-2 had N=13 files and K≈8 decision categories per file; observed coherence was approximately 0/13 as a system despite 95%+ per-file form quality.

**The root problem is the locality of generation, not the absence of inheritance.** Inheritance is one mechanism for breaking locality. There are others, and several of them address more categories at once than inheritance does.

---

## 5. Structurally superior approaches

Six candidate architectures, in increasing scope of structural change. Each addresses a different subset of the locality problem.

### Approach A — Pre-flight project-knowledge artifact

Before generation, do an exhaustive read of the project's existing state and produce a single **canonical project-knowledge artifact** that the drafter MUST consult during every feature's generation. The artifact carries authoritative answers for:

- File paths and what each file exports (TypeScript module declarations)
- Dependencies in `package.json`
- `tsconfig.json` path aliases and compiler options
- Prisma schema models, field names, types, constraints, relations
- Existing API route shapes (handler signatures, request/response patterns)
- Framework conventions (Next.js app-dir layout, Tailwind config, etc.)

The artifact is built by a deterministic scanner, not an LLM. It is **read-only at generation time** — features query it; they don't modify it. If a feature wants to introduce a new file, it MUST declare it in the artifact first (and that declaration is what later features consult).

**Addresses:** module-path (1), external-library-API (2 partial — SDK type signatures via .d.ts), dependency-availability (3), project-config (5), canonical-schema (6, field set / FK / constraints).

**Doesn't address:** content-level mistakes that the drafter makes despite seeing the artifact (the drafter must actually consult it).

**Cost:** scanner is a one-time per-batch artifact-emitter; bounded read cost per feature. Acts as a sibling-output-inheritance generalization — Mode B done right.

### Approach B — Verify-after-generate as a hard gate (Fix 2 done exhaustively)

For every generated file, run an exhaustive cross-file integrity check before the feature is marked successful. Signatures:

- **Unresolvable-import**: every `@/`-prefixed import resolves to a file
- **Missing-dependency**: every external import is in `package.json`
- **Prisma-field-symmetry**: every `db.model.xxx({ where: { … }, data: { … } })` uses fields that exist on the model and have matching types
- **Zod↔Prisma-symmetry**: every Zod schema mirroring a Prisma model has the same field set and type classes
- **API-shape-symmetry**: every UI consumer's expected response shape matches the producing route's actual shape
- **SDK-API-presence**: every external library type/method reference resolves against the installed package's `.d.ts`

Each signature is a runtime classifier check, not a doc artifact. A signature match marks the feature failed regardless of syntax-check outcome. Kaizen suggestions cite the specific signature.

**Addresses:** detects ALL 16 categories of failure observable in RUN_009 attempt-2. Doesn't prevent them — but makes them visible.

**Cost:** moderate per-feature classifier overhead; one-time signature-implementation cost.

**Critical pairing:** Approach B is the visibility surface for any of the other approaches. Without Approach B, future runs will continue to report false-PASS verdicts even when the underlying generator improves. **Approach B should ship before or alongside any other approach.**

### Approach C — Contract-first generation

Flip the generation model: instead of generating files independently, generate a **contract specification** first that declares the shared names, types, and shapes; then generate each file with the contract in scope and the requirement that the file must conform to the contract.

Concretely:

- For data layers: generate the Prisma schema first, then the Zod schemas mirror-derived from it (deterministically, no LLM call), then the API routes that consume the Prisma+Zod pair (LLM call with both in context).
- For UI components: generate the API route shape first (TypeScript request/response types), then the UI component with those types in scope.
- For services that wrap external SDKs: generate the contract from the SDK's `.d.ts` first (deterministically extract the relevant type signatures), then the wrapper with those types in scope.

The contract is a structured artifact (not free text). Subsequent features cannot generate without consulting it.

**Addresses:** canonical-schema (6) and api-shape (15) by construction (the contract IS the schema/shape). external-library-API (4, 11) by giving the LLM the actual SDK types instead of letting it guess. type-signature (7, 10) by deriving the signatures from the contract instead of letting the LLM invent them.

**Doesn't address:** module-path (1) without additional mechanism (would need Approach A).

**Cost:** more sequencing constraint per batch; longer total wall time per batch but lower drift rate.

### Approach D — Single-pass batch synthesis

Treat the entire batch as one generation unit. The LLM sees all features, all targets, and all cross-file dependencies at once; produces all files coherently in one or a few prompts.

For RUN_009's 13-file batch (~1400 LOC), this is feasible — modern LLMs handle prompts of that size with cache breakpoints. Trade longer prompt cost for cross-file coherence by construction.

**Addresses:** all cross-file categories simultaneously. The LLM literally sees the other files it's referencing.

**Doesn't address:** scale beyond what fits in a single prompt; for very large batches this isn't tractable.

**Cost:** higher per-batch token spend (input tokens scale with cumulative target-file context); lower per-batch drift.

**Where this wins:** small-to-medium batches where coherence matters more than per-feature isolation. RUN_009's M2-redo + M3 batch (13 files) is squarely in this range.

### Approach E — Iterative refinement with cross-file feedback

Generate per-feature as today. After each feature lands, run Approach B's classifier signatures. If failures: regenerate the offending feature with the specific failure details as additional context. Loop until the classifier reports zero findings.

This is the postmortem-feedback-loop pattern applied per-feature instead of per-run.

**Addresses:** all categories that Approach B can detect, by closing the loop with regeneration.

**Cost:** higher per-batch token spend (each failed feature gets regenerated); convergence not guaranteed (a drafter that can't see the contract may regenerate the same wrong shape).

**Where this wins:** batches where Approach D doesn't fit but Approach B is available.

### Approach F — Domain-specific contract-driven code generation

For domains where contracts are highly structured (data layers, API routes, CRUD UIs), use a **deterministic generator** that takes the Prisma schema as input and emits all derivative artifacts (Zod schemas, OpenAPI specs, basic CRUD routes, basic CRUD UIs). The LLM's job narrows to the parts that genuinely require creative generation (business logic, AI integration, distinctive UI design).

This is the Rails/Django/Phoenix-style "scaffold from schema" pattern applied to LLM-augmented generation.

**Addresses:** the entire data-layer scope (categories 6, 9, 15) by construction. The LLM never touches Prisma↔Zod symmetry because both are derived deterministically from a single source.

**Doesn't address:** non-data-layer scope (M3 AI engine, M4 enrichment passes). Those still need LLM generation.

**Cost:** generator implementation cost (one-time); ongoing maintenance of the generator templates.

**Where this wins:** in any project with a structured data layer that benefits from boilerplate elimination — which includes most CRUD-heavy MVPs.

---

## 6. Recommended composition

No single approach is sufficient; the composition that addresses all seven categories with minimum redundant work:

**Tier 1 (load-bearing, ship first):**
- **Approach B — Verify-after-generate**. Until the classifier signatures fire, every other improvement is invisible to the learning loop. The current pipeline reports PASS on broken outputs across four consecutive postmortems; nothing else compounds without first making failures visible.

**Tier 2 (ships next, mutually compatible):**
- **Approach A — Pre-flight project-knowledge artifact**. Generalizes Mode A and Mode B into a single project-state read. Closes module-path (1, 2), dependency-availability (3), external-library-API (partial, via SDK .d.ts), project-config (5), and the field-set portion of canonical-schema (6).
- **Approach C — Contract-first for data layer**. Specifically the Prisma → Zod → API → UI sequence. Closes the remaining canonical-schema (6 fully), type-signature (7), and api-shape (9, 15) failures by construction.

**Tier 3 (situational):**
- **Approach D — Single-pass batch synthesis** for small batches where cost is acceptable. Use as the **default for batches under ~15 files / ~2000 LOC**. Falls back to per-feature for larger batches.
- **Approach E — Iterative refinement** as a per-feature retry mechanism when single-pass doesn't fit. Bounded by Approach B's classifier signatures so the loop has a clear exit condition.
- **Approach F — Schema-driven scaffold generators** for projects with structured data layers. Eliminate LLM involvement in the highest-drift categories entirely.

**Tier 1 is the load-bearing critical path.** Until Approach B ships, every other approach's effectiveness is unmeasurable. The score-vs-reality inversion documented in `RUN_009_POSTMORTEM.md` §2 Gap D is the canonical demonstration of this: four consecutive PASS verdicts on increasingly-broken outputs means the failure-feedback loop is broken at its measurement layer.

---

## 7. Implications for the current SDK fix roadmap

The previous postmortems' fix specs map onto this architecture as follows:

| Previous fix spec | Maps to | Status |
|---|---|---|
| RUN_007 Fix 1 — micro-prime escalation | Out-of-scope for cross-file contract; addresses single-file template fallback | ✅ shipped per RUN_007 |
| RUN_007 Fix 2 — empty-stub classifier signatures | Approach B (subset) | ❌ not shipped |
| RUN_008 Fix 1 — intra-batch inter-feature inheritance | Approach A (Mode A subset) | ✅ shipped per RUN_009 evidence (4 paths confirmed) |
| RUN_008 Fix 2 — cross-file integrity classifier signatures | Approach B (full) | ❌ not shipped (still `pipeline_attribution: []`) |
| RUN_008 Fix 3 — value-model contract artifact | Approach C (subset, data-layer scope) | ❌ not shipped |
| RUN_009 Fix 1 — schema-level target/anchor distinction | Approach A precondition (without this, Mode B has no signal) | ❌ not shipped |
| RUN_009 Fix 2 — Mode B (pre-existing upstream) | Approach A (Mode B portion) | ❌ not shipped |
| RUN_009 Fix 3 — wired classifier signatures | Approach B (full) — third time named | ❌ not shipped |

**The Approach B / classifier-signatures item has been named in four consecutive postmortems and never shipped.** It is the chronic deferral. Every other approach's effectiveness depends on it.

**The Approach A / Mode A item has shipped and works at its narrow scope.** Generalizing to Mode B (per RUN_009 Fix 2) is incremental work on the same primitive.

**The Approach C / contract-first item has been touched lightly** (the Forward Manifest registry from RUN_003 Fix 2 is the smallest fragment of this idea — pre-canned skeletons for framework configs). The full data-layer contract-first pattern (Prisma → Zod → API → UI) has not been attempted.

**The Approach D / single-pass synthesis item has not been attempted at all.** Despite the canonical PLAN.md §6 saying "M1–M2 as one prime-contractor batch; M3 as a second; M4 as its own reviewed batch" — implying batches of size 4–7 features — the per-feature drafter still processes each in isolation. Single-pass synthesis for batches of this size is feasible and untried.

---

## 8. Specific actionable recommendations

In priority order:

1. **Ship Approach B — Wire the cross-file integrity classifier signatures.** Concrete signatures (each is a runtime check, not a heuristic):
   - Unresolvable `@/`-prefixed import (parse all `.ts`/`.tsx` imports; resolve against the generated set + pre-existing project files)
   - External-dependency missing (parse all non-relative imports; verify against `package.json` dependencies + devDependencies)
   - Prisma field-set mismatch (parse all `db.<model>.{create,update,findUnique,findFirst,upsert,delete,deleteMany}` calls; resolve field names + types against the active `prisma/schema.prisma`)
   - Zod↔Prisma symmetry (for every `z.object({...})` whose name matches a Prisma model name, assert field-set and type-class agreement)
   - Compound-key validity (`findUnique` and `update.where` accept only fields that have `@unique` or `@id` constraints in the Prisma schema)
   - SDK type-name presence (for every type reference like `Anthropic.X`, resolve against the installed package's `.d.ts`)

   Each signature match: mark feature failed, attribute pipeline stage as `drafter / cross-file contract / <signature_name>`, emit a Kaizen suggestion citing the violation. **Without this, no other improvement is observable.**

2. **Ship Approach A precondition — `ForwardFileSpec.kind = "target" | "anchor"`** (per `RUN_009_POSTMORTEM.md` Fix 1). Schema-level target/anchor distinction; `clean-prior-run.sh` consults; the project-knowledge artifact (Approach A) reads anchors as project-state-available signals.

3. **Ship Approach A — Pre-flight project-knowledge artifact.** A deterministic scanner that emits per-batch:
   - File-tree manifest (paths + last-modified mtimes)
   - Per-file exported-symbol table (via TypeScript AST)
   - `package.json` snapshot
   - `tsconfig.json` snapshot
   - Prisma schema model summary (field-name → type-class)
   - Installed external dependencies with their `.d.ts` type surface (or a digest thereof)

   Inject as a P0 context section to every feature's spec_builder. Bound by relevance (the feature's `target_files` + their import-graph closure) to keep token cost finite.

4. **Pilot Approach D for batches under 15 files.** Default the prime-contractor's batch-execution mode to single-pass synthesis for batches whose cumulative `estimated_loc` fits a threshold (say, ~2000 LOC). Fall back to per-feature for larger batches. This is a workflow-level change, not a primitive-level one — likely cheapest to prototype.

5. **Defer Approach F.** The schema-driven scaffold generator is a more ambitious change with higher one-time cost. Worth scoping after Approaches A, B, C have shipped — at that point its incremental value can be measured against the actual residual drift rate.

6. **Update the verdict-scoring model.** Until Approach B is wired, the current PASS-with-score verdict is decorative. Treat the postmortem-summary's score field as not-yet-meaningful — show it greyed out or marked "unwired" in any UI/report — to prevent the score-vs-reality inversion from misleading future readers.

---

## 9. Why this matters beyond run-009

- **The Fix 1 (Mode A) success is real and worth keeping.** It demonstrates that propagating one decision (module path) across one relationship (sibling) closes one category (module-path) of failure. The same primitive extended to project-state (Approach A) generalizes naturally. **Don't throw out Mode A while extending it.**
- **The four-run pattern (RUN_003 → RUN_007 → RUN_008 → RUN_009) is converging on the same root.** Each postmortem named a different layer of the same generator-locality problem and proposed a layer-specific fix. The proposed fixes have all been narrow (single-file template registry; single-feature inheritance; pre-existing-upstream inheritance; schema-level target/anchor field). The classifier signatures (Approach B) have been deferred each time because they don't generate working code — they only catch failures.
- **Approach B is the load-bearing item.** The score-vs-reality inversion is the canonical evidence. Until the pipeline can detect cross-file contract failures, every other improvement is unmeasurable and every PASS verdict is decorative.
- **The compositions above are not mutually exclusive.** Approach B is a precondition for measuring everything else. Approach A and Approach C address different categories. Approach D is a workflow choice that orthogonalizes per-batch coherence. Approach F is a one-time investment in a specific domain. The right roadmap ships them in tiers (per §6), not as competing alternatives.
- **The cost ratio favors structural fixes.** RUN_009 attempt-2 spent $2.22 on 13 features that delivered 0 working features as a system. The direct-fix pass that followed required ~16 mechanical corrections and an additional Zod expansion agent call. Each subsequent run will reproduce the same pattern (more or less) until the generator-locality problem is addressed at a layer that matches its scope. The structural approaches above all have one-time implementation costs that pay back within ~3–5 runs of avoided rework.

---

## 10. The Brooks frame revisited

Brooks's essential-vs-accidental distinction (referenced in `PLAN_BATCH_ORCHESTRATION_PLAN.md` R3 audit) cuts through the inheritance-mode framing. The cross-file contract problem is **essential complexity** of multi-file system synthesis — there's no way to generate a coherent multi-file system without resolving cross-file contracts somehow. The current architecture's approach to that essential complexity (per-file probabilistic generation with selective inheritance) is **accidental complexity** layered on top. The structural approaches above each replace some of the accidental complexity with a more direct treatment of the essential.

The four-postmortem trajectory is the accidental-complexity tax compounding: each fix patches one symptom of the per-file-locality choice without addressing the choice itself. The structural shift is to step out of that trajectory — pick one or more of the approaches that treats cross-file coherence as a first-class concern, rather than continuing to extend inheritance to handle the n+1th category.

---

## 11. The shared resolver substrate — converging with Code Observability (Mieruka)

*Added 2026-06-01 after reviewing `CODE_OBSERVABILITY_RESEARCH_SECOND_PASS.md`.*

Approaches A (project-knowledge artifact) and B (verify-after-generate signatures) are, underneath, the **same primitive**: a **name/scope/import/type resolver over a multi-file codebase**, materialized as a queryable structural model. That is *exactly* what the Mieruka code-observability project builds (`CodeGraph` + per-language resolvers). The two efforts should **converge on one resolver/`CodeGraph`, not build it twice.**

- **Approach A = a slice of the `CodeGraph`** (file→exports table, `package.json`/`tsconfig` snapshots, Prisma model summary, installed-dep `.d.ts` surface) injected as P0 generation context.
- **Approach B = queries against the same `CodeGraph`** (unresolvable import, missing dependency, unknown Prisma field, symbol/type presence).
- The shipped signatures (`cross_file_imports.py`, `prisma_usage.py`, `prisma_zod_symmetry.py`) are **hand-rolled, regex-grade, TS/Prisma-specific instances** of what the resolver generalizes across all 5 languages — and they subsume the Go/Java/C# **compile-gate** (`COMPILE_GATE_*`) too.

**The load-bearing constraint (from the research): SCIP needs *buildable* targets; tree-sitter handles *partial/non-compiling* code.** Our inputs frequently don't compile (that *is* the failure being caught), so the substrate is **two-tier**:

| Tier | When | Tool | Serves |
|------|------|------|--------|
| **Partial** | in-process / mid-generation / unprovisioned / non-building | tree-sitter resolver (+ Python stdlib `ast`/`symtable`/Jedi) | the in-process signatures + Approach A on broken code |
| **Precise** | post-build, provisioned, compiling | SCIP (`scip-typescript`/`-go`/`-java`/`-dotnet`, Apache-2.0, active) | post-build verification (complements the `tsc` gate); multi-language uniformity + find-references |

Honest scoping: for **TS specifically, SCIP's marginal value over the `tsc` gate is modest** (tsc already resolves TS) — SCIP's win is **multi-language breadth + queryability**, which is what the Go/Java/C# compile-gate and Approach A actually need. tree-sitter is the lever for **partial-code reach** (the unprovisioned/mid-generation case the regex signatures occupy today).

**Adoption guardrails (from the research):**
- **Avoid** `stack-graphs` (archived, unsupported) and Heros (LGPL-2.1, not permissive embeddable) — dead-ends.
- **tree-sitter/codebleu pin conflict** (`codebleu` wants `tree-sitter<0.23`; current grammars want `~0.24`) blocks naive adoption — isolate the resolver in a `[code-observability]` extra; keep CodeBLEU subprocess/separate. (Note: tree-sitter is **already a dependency** — `languages/csharp_parser.py` uses it.)
- **Python** resolver: stdlib `ast`/`symtable` (+ optional Jedi) is enough for a first pass — cheapest to prototype.

**Roadmap implication:** build **Approach A as the Mieruka `CodeGraph` slice, not a bespoke scanner**, so code-gen coherence and code-observability share one resolver. Decide this **before** implementing Approach A — it's a "don't pay the integration tax twice" call. The shipped regex signatures + the `tsc` gate remain the correct cheap-now; the `CodeGraph` is the converge-here-next substrate that retires the per-language signature sprawl.

---

*Authored 2026-06-01 from the cumulative evidence of RUN_003 / RUN_007 / RUN_008 / RUN_009 postmortems plus the RUN_009 attempt-2 direct-fix pass (commits d5016ee and 87b06f9 on the startd8 repo). Evidence specifics — the 16 contract-failure enumeration in §1 — was collected during the `npm install && npx prisma generate && npm run build` iteration that took the attempt-2 outputs from "13 broken imports + multiple schema mismatches" to a green build. The composition recommendations in §§6–8 are stated in priority order for an SDK-level fix roadmap; the postmortem-specific fix specs in §7 map cleanly onto the approaches and are not abandoned by this analysis — they are repositioned within a larger structural frame.*

---

## 12. Empirical update — RUN-011 and RUN-012 evidence (2026-06-01)

*Added after the M4 and M5 batches on the strtd8 repo produced two more postmortems that converge on the same architectural pattern.*

This document was authored after RUN-009 with 16 contract failures enumerated in §1. Two further runs — RUN-011 (M4 batch) and RUN-012 (M5 batch) — produced new evidence that **strengthens** every load-bearing claim in this doc while also revealing the **limit** of the simplest plan-level countermeasure.

### 12.1 The simplest countermeasure (per-plan canonical-name discipline block) WORKS — but only for the domains it covers

The M5 plan introduced an explicit "Canonical-name discipline" block enumerating Prisma model fields, the `@/lib/db` import path, and the `@/lib/value-model` Zod schema location. **Result in RUN-012:** zero `@/lib/prisma` imports across all 15 generated files. Zero invented Prisma field names. The Prisma-domain failure mode that had recurred across RUN-007 through RUN-011 was **eliminated** in RUN-012 by a paragraph of explicit guidance in the plan.

This is real evidence that **per-domain canonical-name enumeration is a load-bearing countermeasure**. The structural argument of this doc (§§4–6) is empirically confirmed at the single-domain level.

**But the same RUN-012 produced 5 new failures in 3 new flavors** — all in domains the plan did NOT explicitly enumerate:

| Flavor | Failed features (run-012) | Counter NOT in plan | LLM training prior |
|---|---|---|---|
| CSS Modules invention (`*.module.css`) | PI-005, PI-007, PI-011 | "Inline-styled (no Tailwind)" ruled out one option but didn't enumerate which others are acceptable | "React components have a CSS-sibling pattern" |
| Barrel-import invention | PI-008 (Opus tier, $0.3247) | Plan named `components/wizard/WizardSteps.tsx`; did not explicitly state "no barrel export at `components/wizard/steps/`" | "`components/{kind}/index.ts` is the barrel" |
| Top-level `types/` directory invention | PI-012 | Plan named `components/wizard/types.ts`; did not state "there is no top-level `types/` directory" | "shared types live at top-level `types/`" |

**The countermeasure is per-domain whack-a-mole.** Each domain the plan doesn't pre-empt becomes the next batch's failure mode. This is exactly the failure model §4 of this doc predicted: priors override plan directives at the per-file generation boundary; the only reliable defense is *enumeration* of every counter-pattern. M5's plan enumerated for the data domain (worked) and not for the frontend-organization domain (failed). M6's plan now enumerates both.

This **strengthens** the §5 case for Approach A (programmatic pre-flight project-knowledge artifact). The per-plan hand-written discipline block is a manual instance of what Approach A produces automatically. The human author has to know **in advance** which domains will surface; the LLM's priors span every domain it was trained on. Programmatic enumeration is the only way to scale this.

### 12.2 Mode A inheritance is non-deterministic at sibling boundaries — the sharpest A/B yet

RUN-012 produced two clean A/B experiments where the convention was **observably correct in the same batch's sibling files** at the time the failing features were generated:

**CSS Modules A/B (3 fail / 2 pass within wizard steps):**
- ProfileStep, ValuePropsStep, ArtifactsStep: inline `style={{...}}` objects — correct
- ProofPointStep: invented `import styles from "./ProofPointStep.module.css"` — wrong
- All 5 generated in the same batch with the same set of plan directives and the same available sibling outputs.

**Top-level `types/` A/B (4 pass / 1 fail within wizard steps):**
- ProfileStep imported `from "../types"` — correct (relative)
- ProofPointStep, ValuePropsStep, ArtifactsStep imported `from "@/components/wizard/types"` — correct (alias)
- EnrichStep invented `from "../../../types/wizard"` — wrong
- All 5 in the same batch; PI-006 (the types file) was generated correctly and on disk by the time PI-012 ran.

This is direct evidence that **Mode A intra-batch sibling-output inheritance is probabilistic, not guaranteed**. Per §2 of this doc, Mode A was already characterized as fragile — but the RUN-012 A/B is the **first time we have N-of-5 sibling outcomes** showing the convention was visible-and-correct yet didn't propagate. The §4 "per-file probabilistic generation locality" frame is the only one that fits this evidence.

**Implication for Approach D (single-pass batch synthesis):** if intra-batch inheritance is N-of-K probabilistic, batch synthesis would need a final-pass consistency check across all features in the batch — independent of any per-feature classifier signature — that bucket failures by invention category and surface the dominant pattern. RUN-012's `cross_feature_patterns` reported only `cost_outlier`; it did NOT detect that 3 features invented `.module.css` imports. The classifier is feature-local; the failure pattern is batch-level.

### 12.3 Opus tier does not fix structural priors — second confirmation

RUN-011 PI-010 (Value Propositions library): $0.4194, COMPLEX-tier Opus routing — still invented `@/lib/prisma`, `text`, `capabilityId`, `outcomeId`. Same patterns as the Sonnet-tier siblings in the same batch.

RUN-012 PI-008 (WizardShell): $0.3247, 2.2× the average — Opus-tier signature again. Still invented `@/components/wizard/steps` as a barrel-export path. The convention (`WizardSteps.tsx` as the registry file) was named explicitly in the plan AND was generated correctly by PI-015 in the same batch.

**Two postmortems, two domains, same finding:** model capability does NOT prevent invention at the per-file generation boundary. The relevant constraint is the LLM's prior for the per-file content shape, not the model's reasoning capability for the broader plan. This **strengthens the argument that the structural fix is upstream of the model** — Approach A injects evidence the LLM can't generate from its prior; Approach B catches priors that slipped through; no amount of model capability inside the generation step fixes either.

### 12.4 Score-vs-reality inversion is fixable — empirical evidence the classifier signature approach works

RUN-011 showed score-vs-reality inversion: high-verdict features were structurally undeliverable (Gap C from RUN_011 postmortem). The Fix 2 TS2345 type_class_mismatch signature shipped mid-RUN-011 authoring.

RUN-012 verdict score is 0.67 — accurately reflecting 10/15 delivered. The 5 failed features were correctly attributed to `cross_feature_contract / cross_file_contract`. **Score-vs-reality is recoupled** — first run in this sequence where the headline metric is a reliable signal.

This validates the Approach B direction (§5.B + §6) at the per-signature level: each load-bearing signature that ships **converts a previously-invisible failure mode into an attributed-and-scored one**. It does NOT prevent the failure (RUN-012 still produced 5 failures); but it makes the failures legible to the verdict layer.

**The composition principle holds (per §6):** Approach A reduces the rate of invention; Approach B makes any invention that slips through legible. Neither alone is sufficient; the combination is what makes the pipeline trustworthy.

### 12.5 Updated priority for the SDK fix roadmap

Concrete prioritization update based on RUN-011 and RUN-012:

1. **Approach A (project-knowledge artifact, §5.A)** — load-bearing. RUN-012 evidence is the strongest case yet: a paragraph of hand-written enumeration prevented a category of failures the prior 4 runs all hit. Programmatic generation of the same enumeration would scale to every domain. **Now the #1 SDK roadmap item.**

2. **Approach B continued — per-failure-mode classifier signatures (§5.B / §6)** — RUN-012 validates the approach at the per-signature level (TS2345 worked). The next signature additions, in priority order from the RUN-012 evidence:
   - **`unresolvable_css_module`** — fires when generated code imports a `.module.css` sibling that doesn't exist. Trivially detectable.
   - **`barrel_import_to_non_existent_index`** — fires when an `@/components/X` import targets a directory that has no `index.ts`/`index.tsx`/registry file at the expected location.
   - **`top_level_types_dir_invented`** — fires when any generated file imports from `../../../types/*` or `@/types/*` and that path doesn't exist.
   - These three would have caught 5 of 5 RUN-012 failures.

3. **Cross-feature pattern detection (new — RUN-012 Gap H)** — bucket failures by invention category and surface the dominant pattern in `cross_feature_patterns`. The CSS Modules pattern (3 features, 60% of failures) was not surfaced because the classifier is feature-local. Cheap fix: if ≥N features failed with the same error-message regex, emit a `dominant_invention_pattern` finding.

4. **Pipeline attribution rollup reliability (RUN-012 Gap I)** — `pipeline_attribution` was populated in RUN-011's mid-authoring regen but empty in RUN-012. Either the rollup step is non-deterministic across runs, or the late-regen path is the only one that populates it. Either way, the user-facing reports can't trust this table.

The §6 recommended composition (A + B together) is **strengthened** by RUN-011 / RUN-012 evidence, not refuted. The empirical pattern is: **plan-level discipline blocks reduce per-domain failure rates; classifier signatures reliably attribute the remainder; Approach A programmatically removes the human bottleneck of "anticipate every domain."**

---

*Section 12 added 2026-06-01 from the cumulative evidence of RUN_011 (`docs/design/RUN_011_M4_FIELD_AND_PATH_INVENTION_POSTMORTEM.md`) and RUN_012 (`docs/design/RUN_012_M5_REACT_ORG_INVENTION_POSTMORTEM.md`). The §12.2 sibling A/B is the load-bearing new empirical evidence — 3-of-5 and 4-of-5 outcomes within a single batch establish that intra-batch inheritance is probabilistic rather than guaranteed, which the earlier postmortems suggested but did not directly demonstrate.*
