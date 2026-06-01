# RUN-008 Cross-Feature Incoherence Remediation — Requirements

**Version:** 0.2 (Comprehensive TS-robustness direction — toolchain-backed)
**Date:** 2026-05-31
**Status:** Draft (ready for convergent review)
**Source incident:** `docs/design/RUN_008_CROSS_FEATURE_INCOHERENCE_POSTMORTEM.md` — prime-contractor run `run-008-20260531T2050` reported **16/16 PASS (score 0.99)** but delivered **0 functional features as a system**: 3 unresolvable import paths + Prisma↔Zod schema disagreement on every entity + an invented `profileId` FK + a third Profile model in the UI. Every individual file is internally well-formed.
**Root-cause basis:** A 4-thread code investigation (2026-05-31) against the exact files the postmortem cites. Findings are recorded as **§0 Root-Cause Discovery** below with file:line anchors.

> **Direction (decided with user, 2026-05-31).** Address this **as comprehensively as possible, adding as robust TypeScript support as possible.** This reverses v0.1's conservative scoping in two ways: (1) **G3 framework support is promoted from a minimal `.prisma` floor to a first-class TS-stack robustness track** built on the *real toolchain* (`tsc --noEmit` project-level + `prisma generate`/`validate`), because running the stack's own tools over the generated set is both more thorough and *less* bespoke code than hand-rolled signatures; (2) **the v0.1 Non-Requirement against project-wide `tsc` is reversed** — it is now the verification backbone. The requirements are organised into three tracks: **A — language-agnostic cross-file propagation** (G1), **B — TS-stack robustness via the real toolchain** (G2+G3 merged), **C — verification wiring + regression**.

> **v0.2 key decisions vs v0.1.** (a) **OQ-1 resolved — disk-authoritative.** FR-1 sources a producer's interface from its emitted **`.d.ts`** (TypeScript's native module-interface artifact), with the `InterfaceContract` as validator + fallback. (b) **Bespoke signatures subsumed.** v0.1's FR-4 (`@/` resolution) and FR-6 (Prisma usage validity) are largely *subsumed by the real `tsc` + `prisma generate`* and demoted to a reduced-confidence fallback when the toolchain is absent. (c) **One residual bespoke check** — Prisma↔Zod field-name symmetry — survives, because `tsc` structurally cannot see drift between two hand-maintained parallel schemas that are never type-linked. (d) **Loud degradation** is a hard requirement: a missing/unrunnable toolchain emits `verification-unavailable`, never a silent PASS.

---

## 0. Root-Cause Discovery (RESOLVED 2026-05-31)

Four parallel code investigations + a read of the run-008 evidence artifacts. All three user hypotheses confirmed with anchors.

### G1 — No inter-feature cross-file contract propagation *(language-agnostic; postmortem Gap A/B/C, Fix 1)*

The Forward Manifest is wired to a **single-file (intra-file) contract scope** and was never extended to the cross-file (inter-feature) scope. A consumer feature never sees its producer's actual emitted interface.

| Finding | Anchor |
|---------|--------|
| `file_specs_for_task()` filters `{path: spec ... if path in target_files}` — returns the feature's **own** target files only, never files it imports from. | `src/startd8/forward_manifest.py:492-508` |
| Spec builder injects forward-element specs filtered by `target_files` only (`_format_forward_element_specs(fm, id, target_files)`). | `src/startd8/contractors/context_resolution.py:824-828`, `:579-590` |
| Drafter receives a pre-formatted `forward_contracts` **string**, cannot look up an imported file's contract. | `src/startd8/implementation_engine/drafter.py:950-952` |
| `_build_generation_context` uses static `seed_data` + current-feature-only `feature_data`; never reads a sibling feature's generated output. | `src/startd8/contractors/prime_contractor.py:3804-3987`, `:3828-3842` |
| `_populate_existing_files` reads only **same-directory `*.py` siblings of edit targets** — not upstream features' outputs. | `src/startd8/contractors/prime_contractor.py:886-970`, glob at `:943` |
| `_collect_dependency_imports` threads dependency module **names only**, inferred by regex over the dep's *description* and base-class prefixes — not the producer's real exports. | `src/startd8/contractors/prime_contractor.py:4168-4256` |
| Features **are** topologically ordered with cycle-breaking; `process_feature` integrates F1 to disk **before** F2 develops. So upstream output is physically on disk at design time — nothing reads it. | `src/startd8/contractors/queue.py:505-550`, `:413-482`; `prime_contractor.py:5001`, `:2204-2230` |
| Run-008 evidence: PI-012's enriched context lists `depends_on: ["PI-011","PI-007"]` and a spec import line `lib/schemas → ProfileSchema` — a **guessed** path; the real producer file is `lib/value-model.ts` exporting `ProfileSchema`. 90 manifest contracts, **zero** binding PI-011's export to PI-012's import. | run-008 `prime-context-seed-enriched.json`, generated `app/api/profile/route.ts:2` |

**Verdict: NO** — cross-file contract is not propagated at design time. Dependency ordering controls **merge order, not generation input**.

### G2 — No cross-file integrity verification for TypeScript *(acute for the display framework; postmortem Gap D, Fix 2)*

| Finding | Anchor |
|---------|--------|
| Node `validate_syntax` is **per-file**; `tsc --noEmit --isolatedModules --skipLibCheck` — `--isolatedModules` **disables cross-file type checking by design**. | `src/startd8/languages/nodejs.py:311-433`, flag at `:394` |
| **No `@/` import-alias resolution anywhere** in `src/startd8/` (zero grep hits). The broken `@/lib/schemas` import is unresolvable by any current check. | repo-wide grep `@/` |
| `validate_disk_compliance` short-circuits `if abs_path.suffix != ".py"` → the cross-file disk validator is **Python-only**; it never ran on the `.ts` files → the 0.99 PASS. | `src/startd8/forward_manifest_validator.py:392`, `:406` |
| Node semantic checks (6) are **regex / single-file**; Python's (4) are AST + one **cross-file** phantom-dependency check. | `src/startd8/validators/nodejs_semantic_checks.py:220-246` vs `semantic_checks.py:225-264` |
| Node repair routes ≈ 2 semantic (ESLint-dependent); Python = 4 AST-based. Node merge = `"simple"` text; Python = `"ast"`. | `src/startd8/repair/routing.py:157-165` vs `:116-124`; `nodejs.py:201` vs `python.py:96` |

**Verdict: NONE** — no cross-file integrity capability for TypeScript today, and the one cross-file disk validator that exists is Python-only.

### G3 — Zero encoded framework knowledge (Prisma / Zod / Next.js) *(structural; postmortem Fix 3 territory)*

| Finding | Anchor |
|---------|--------|
| `.prisma` maps to **no language profile** in the extension map and falls back to Python. Prisma is invisible to the toolchain. | `src/startd8/languages/resolution.py:167-254`, map at `:217-225`, fallback `:241-242` |
| No Prisma / Zod / Next.js awareness anywhere (grep `prisma`/`zod`/`next.config`/`@/lib`). The stack is treated as generic text, so a Prisma `model` and a Zod `z.object` for the same entity cannot be compared. | repo-wide grep |
| Run-008 concrete divergences confirmed: `summary`/`bio`, `yearsExp`/`yearsOfExperience`, Zod-invented `websiteUrl`/`metadata`, Zod-invented `profileId` FK on every child entity, `Metric.value` String-vs-number. | run-008 `prisma/schema.prisma` vs `lib/value-model.ts` |

**Verdict: CONFIRMED** — "not much practice with the framework" is structurally "no encoded framework knowledge." `.prisma` isn't even a recognised file type.

**Net root cause:** *Generate blind, verify blind.* G1 lets each feature invent its own cross-file contract; G2+G3 mean the invention is never caught for the TS/Next/Prisma stack, so the run reports a clean PASS. RUN-003/007 closed *intra-file* deflections; G1 is the first *inter-file* layer, and TS is where it bites hardest because TS has neither propagation (G1) nor verification (G2/G3).

### G4 — Config↔layout incoherence (new, found during spike)
A fourth instance of G1, in the config layer: the generated `tsconfig.json` maps `"@/*": ["./src/*"]` but every generated file lives at **root** (`lib/`, `app/`), not `src/`. So **every `@/` import is unresolvable — including the *correct* ones** (`@/lib/db`). The config feature invented a `src/` layout the code features didn't use. (Anchor: run-008 workspace `tsconfig.json` vs file tree.)

### Spike validation (RESOLVED 2026-05-31) — the load-bearing bet, tested
A contained reproduction of the run-008 `profile` route (real `prisma/schema.prisma` + `lib/value-model.ts`, `prisma generate` + project `tsc --noEmit`, imports fixed to isolate typing) established the **exact subsumption boundary** between the toolchain and the bespoke check:

| run-008 failure class | `tsc`+`prisma generate` | Evidence |
|---|---|---|
| Unresolvable `@/` import | ✅ **caught** | `TS2307: Cannot find module '@/lib/schemas'` |
| Invalid `where` on non-`@unique` column (`findUnique/upsert({where:{ownerId}})`) | ✅ **caught** | `TS2322: '{ownerId}' not assignable to 'ProfileWhereUniqueInput' … 'id' is missing` (fires even with imports fixed) |
| **Prisma↔Zod field/type divergence** (`bio`/`summary`, `yearsExp`/`yearsOfExperience`, invented `websiteUrl`/`metadata`/`profileId`) | ❌ **ESCAPES** | `{ ...parsed.data }` spread into `create`/`update` produced **zero** errors — TS **suppresses excess-property checking for spreads of a variable** |
| UI invents fields via untyped `fetch()` | ❌ escapes | (not in spike; untyped boundary, see FR-1) |

**Consequences for the requirements:** (a) FR-4 and FR-5's toolchain subsumption is **confirmed** for the import-class and the where-clause usage-class. (b) **FR-7 (Prisma↔Zod symmetry) is proven load-bearing, not a hedge** — `tsc` structurally cannot see field/type divergence that flows through a `{ ...variable }` spread, which is the dominant data-flow shape in these routes. (c) The run-008 workspace had **no `node_modules`/`tsc`/`prisma`** installed at all — verification capability never existed (informs OQ-3 / FR-9). The spike artifacts are preserved as the FR-11 regression fixture seed.

---

## 1. Problem Statement

A single prime-contractor batch generates N dependent features. Each feature's design context contains the contract for **its own** target files but **not** for the files it imports from — even when the producer has already been generated and written to disk earlier in the same run. Each dependent feature therefore **invents its own version of the cross-file contract** (module name, field set, type, FK shape, even the data model). For the TypeScript/Next.js/Prisma/Zod stack the divergence is then **invisible to every verification surface**, so the run reports PASS. Three compounding gaps:

| ID | Gap | Layer | Postmortem map | Track |
|----|-----|-------|----------------|-------|
| **G1** | No inter-feature cross-file contract propagation | Generation (language-agnostic) | Gap A/B/C → Fix 1 | A |
| **G2** | No cross-file integrity verification for TypeScript | Verification (TS-acute) | Gap D → Fix 2 | B |
| **G3** | Zero encoded framework knowledge | Structural | Fix 3 territory | B |

---

## 2. Requirements

### Track A — Close G1 (inter-feature contract propagation) — *language-agnostic*

#### FR-1 — A feature's design context MUST carry its upstream producers' real interface (disk-authoritative)
When feature F2 depends on F1 (via `depends_on`/`dependencies`) **or** F2's `target_files` import from a path F1 produces, F2's spec-builder and drafter context MUST include F1's **actual emitted interface** for the imported file — the real module path, exported symbol names, and field/type/FK shape — sourced from F1's generated artifact on disk (it is integrated before F2 develops, G1 anchor `prime_contractor.py:5001`), **not** from name inference over descriptions/base-class prefixes (the current `_collect_dependency_imports` behaviour that produced the `lib/schemas` guess).
- **Extraction mechanism (resolves OQ-1):** for TS/JS producers, extract the interface from the producer's emitted **`.d.ts`** declaration (`tsc --declaration --emitDeclarationOnly`, produced by the Track-B toolchain) — TypeScript's own native, compact representation of a module's public interface. For non-TS producers, extract from the language's existing structure extractor.
- **Contract role:** the `InterfaceContract` (already in the manifest) is used to (a) **validate** that F1 honored its promise (emitted what it declared) and (b) serve as **fallback** when the on-disk artifact is unavailable (e.g. cross-batch). Disk is authoritative when present.

*Acceptance:* synthetic seed PI-011→PI-012, PI-011 writes `lib/value-model.ts` exporting `ProfileSchema`; assert PI-012's emitted import is `@/lib/value-model` + `ProfileSchema` (matches the emitted `.d.ts`), not an invented name; if PI-011's emitted interface diverges from its `InterfaceContract`, the divergence is recorded.

#### FR-2 — Block loudly on a missing upstream artifact (no silent invention)
If F2's upstream producer output is **expected but absent** (F1 not yet generated, skipped, or refused), F2 MUST halt with a structured `MissingUpstreamArtifact` diagnostic (`success=False`, distinct `root_cause`/`pipeline_stage`), caught — never a silent summary fallback or invented contract. Mirrors `PLAN_BATCH_ORCHESTRATION_REQUIREMENTS.md` FR-10's "no silent fallback to summaries" at the intra-batch seam.
*Acceptance:* invoke PI-012 where PI-011 has not generated → `MissingUpstreamArtifact`; batch continues; feature `success=False`.

#### FR-3 — Dependency edges drive *generation input*, not only merge order
The producer→consumer edges already used for ordering (`queue.py`) MUST also select what FR-1 propagates. Where `depends_on` is absent, **language-aware import-path inference** (resolving the consumer's declared/likely imports to producer target files) MUST derive the edge. The propagation budget is bounded to **direct producers of imported paths**, not the transitive closure of the whole batch (see OQ-5).
*Acceptance:* explicit `depends_on` and inferred-import both select the producer; an import-nothing feature gets no extra context.

### Track B — Close G2 + G3 (TS-stack robustness via the real toolchain) — *the comprehensive investment*

#### FR-4 — Project-level TypeScript type-check is the verification backbone
The Node/TS verification path MUST run a **project-level `tsc --noEmit`** over the generated file set using the project's real `tsconfig.json` (**not** `--isolatedModules`; G2 anchor `nodejs.py:394`). This is the primary cross-file integrity surface: it natively resolves `@/` path aliases from `tsconfig` `paths`/`baseUrl`, catches unresolvable imports (TS2307), missing/excess properties, and type/argument mismatches across the whole generated set in one pass.
*Acceptance:* the run-008 set with `@/lib/schemas` unresolved → tsc error surfaced and mapped to a feature FAIL; a coherent set → clean; `@/` aliases resolve via a `tsconfig` fixture with no bespoke alias table.

#### FR-5 — Prisma is generated and validated in the loop
For Prisma projects the verification path MUST run **`prisma validate`** (schema well-formedness) and **`prisma generate`** (materialise `@prisma/client` types) **before** the FR-4 `tsc` pass, so that invalid Prisma usage becomes a *compile error* via Prisma's strict generated types. This is what turns the invented `profileId` and the non-unique `findUnique({where:{ownerId}})` into detectable failures — using Prisma's own tooling, not reimplemented constraint logic.
*Acceptance:* run-008 `proof-points` route with invented `profileId` → tsc error against the generated Prisma client; `findUnique({where:{ownerId}})` against non-`@unique` `ownerId` → tsc/Prisma error; a malformed schema → `prisma validate` failure.

#### FR-6 — `.prisma` is a recognised, first-class file type
`.prisma` MUST resolve to a dedicated handling path (its own minimal language profile or explicit schema-DSL classification) — never silently fall back to Python (G3 anchor `resolution.py:241-242`). It MUST be parseable into an entity→{fields, types, relations, `@unique`/`@@unique`} model consumed by FR-5 (validate) and FR-7 (symmetry).
*Acceptance:* `resolve_language(["prisma/schema.prisma"])` ≠ Python; the parser extracts run-008 `Profile`/`ProofPoint` incl. unique columns and join tables; malformed `.prisma` is flagged, not treated as Python.

#### FR-7 — Prisma↔Zod semantic symmetry (the one residual bespoke check — *spike-proven mandatory*)
For every Prisma `model` and every Zod `z.object(...)` mapping to the same logical entity, the validator MUST assert field-name sets, type-class compatibility, and FK shape agree. This is bespoke domain knowledge because `tsc` **cannot** see drift between two hand-maintained parallel schemas that are never linked in the type system. **Empirically confirmed (§0 spike):** the run-008 routes pass Zod-validated data into Prisma `create`/`update` via `{ ...parsed.data }` spread, and TypeScript suppresses excess-property checking on spreads-of-a-variable, so the field/type divergence produced **zero** `tsc` errors. FR-7 is therefore the *only* surface that catches this class — it is mandatory, not a fallback.
*Acceptance:* the run-008 Profile pair (`summary`/`bio`, `yearsExp`/`yearsOfExperience`), the invented `profileId` on ProofPoint, and `Metric.value` String-vs-number each produce a FAIL (`root_cause=prisma_zod_symmetry_violation`) with a Kaizen suggestion naming the field(s); an aligned pair passes.

#### FR-8 — `.d.ts` interface-extraction capability (shared seam)
The toolchain MUST be able to emit/parse **`.d.ts`** declarations for generated TS modules (`tsc --declaration --emitDeclarationOnly`) and reduce them to a structured interface (module path → exported symbols + types). This single capability serves **both** FR-1 (generation-input: what does the producer actually export?) **and** FR-4 verification — built once, used on both sides.
*Acceptance:* `lib/value-model.ts` → a `.d.ts`-derived interface listing `ProfileSchema` and its field types; consumed by FR-1 propagation and reconciled against the `InterfaceContract`.

#### FR-9 — Loud degradation when the toolchain is unavailable
When `node`/`tsc`/`prisma` are absent, dependencies are not installed (`npm install` not run), or `prisma generate` cannot complete, the verification path MUST emit a structured **`verification-unavailable`** signal that is treated as **non-PASS** (or an explicit reduced-confidence verdict) — it MUST NOT silently report PASS. A reduced-confidence **fallback floor** MAY run the lightweight bespoke checks (v0.1's `@/`-existence import resolution and a Prisma-usage regex) and MUST label results as such.
*Acceptance:* with `tsc` unavailable, a broken run-008 set does **not** report PASS — it reports `verification-unavailable` or a fallback-floor FAIL; the verdict surfaces which checks actually ran.

### Track C — Verification wiring + regression

#### FR-10 — The classifier MUST run TS cross-file verification for non-Python sets and hard-FAIL
`validate_disk_compliance` MUST NOT short-circuit non-`.py` files out of cross-file integrity (today `suffix != ".py"` skips them — G2 anchor `forward_manifest_validator.py:392`). On any FR-4/5/7 failure the feature is marked failed regardless of single-file syntax success, the pipeline stage is classified `drafter / cross-feature contract`, root cause attributed to the specific signature, and ≥1 Kaizen suggestion emitted. A clean batch produces **no** false positives.
*Acceptance:* reproductions of the run-008 broken files → non-`unknown` stage + specific signature + Kaizen suggestion; production-quality files (PI-002/003/010) classify SUCCESSFUL.

#### FR-11 — Regression reproduction + detector-regression lock
Tests MUST reproduce the run-008 shapes and assert each output is **coherent-with-its-producer OR a structured refusal** — never a silently-divergent PASS. Coverage: the import-name mismatch, the Prisma↔Zod field/FK divergence, the invalid `findUnique`, the missing-upstream halt, and the toolchain-unavailable degradation. Additionally a **detector-regression lock** (mirroring RUN_007 FR-8): feed each broken shape directly to the verifier and assert FAIL/`verification-unavailable`, independent of the generation-side assertions, so a later refactor cannot silently re-blind the verdict.

---

## 3. Non-Requirements
- Does **not** build the full single-source-of-truth Value Model contract artifact per batch (postmortem Fix 3) — deferred until FR-1 inheritance is observed in practice. FR-6/FR-7 provide the Prisma↔Zod coherence that Fix 3 would otherwise enforce up front.
- Does **not** generalise framework knowledge beyond the TypeScript/Next.js/Prisma/Zod stack (no Vue/Svelte/Drizzle/etc.). Other frameworks remain generic-text until a run reproduces a defect on them.
- Does **not** unify the run's multiple disagreeing success counts (the deferred single-ledger from RUN_007 Fix 3).
- ~~Does not add project-wide `tsc` (too heavy).~~ **REVERSED in v0.2** — project-level `tsc --noEmit` is now the FR-4 verification backbone.
- Does **not** add full ESLint/type-aware lint or formatting as a gate (code-quality, not coherence) — out of scope for this remediation.

---

## 4. Open Questions (for CRP / implementation)
- **OQ-1 — RESOLVED (v0.2).** FR-1 propagation source = **disk-authoritative via emitted `.d.ts`**; `InterfaceContract` is validator + fallback.
- **OQ-2** — FR-7 entity-mapping: name-match (`Profile` model ↔ `ProfileSchema`) is the obvious heuristic but fragile (suffix stripping, `ProofPointSchema` vs `ProofPoint`). Should mapping require an explicit producer/consumer manifest entry, or is suffix-normalised name-match sufficient for the MVP?
- **OQ-3 — RESOLVED (2026-06-01, decided with user).** Verification host & timing:
  - **Execution = pipeline-owned gate, after every batch (including the terminal/only one).** The project-level `tsc --noEmit` runs in `cap-dev-pipe` as a post-batch gate, **consolidated with the Plan-Batch-Orchestration session's "Essential ④" transition gate** (one gate, not two). Load-bearing nuance: run-008 was a *single* batch, so the gate MUST fire after the final batch too — an inter-batch-only gate would miss it. The SDK's in-process `_evaluate_ts_toolchain` (env `STARTD8_TS_TYPECHECK`) stays an opt-in **same-run mirror** for postmortem/Kaizen, enabled when the gate host has provisioned the toolchain.
  - **Provisioning = `npm ci` cached + `prisma generate`.** `cap-dev-pipe` runs `npm ci` once per project keyed by the `package-lock.json` hash (node_modules reused across batches), and `npx prisma generate` after the Prisma-schema feature completes. Fast after warm, reproducible.
  - **FR-7 (Prisma↔Zod symmetry) needs no toolchain** — it runs in-process always, as the toolchain-free complement to the gate.
  - Division of labor: **cap-dev-pipe** = provisioning + set `STARTD8_TS_TYPECHECK`; **Essential ④** = post-every-batch (incl. terminal) `tsc --noEmit` gate via `ts_toolchain` (prefer `tsc` over `next build`); **SDK** = `ts_toolchain` + env-gated mirror (done).
- **OQ-4** — FR-6 `.prisma` handling: net-new minimal `LanguageProfile` (entry-point registered, 15-method protocol) vs a lighter "recognised schema-DSL" classification that bypasses the full profile protocol. Lower blast-radius which way?
- **OQ-5** — FR-3 propagation budget: is "direct producers of imported paths only" sufficient, or do transitive contracts (F3 imports F2 which re-exports F1) need propagation? Bound explicitly to avoid prompt-budget blow-up.
- **OQ-6 — RESOLVED (v0.2, cross-session 2026-05-31).** Yes — a **single inheritance implementation serves both granularities**, per postmortem §5 and a Plan-Batch-Orchestration session's input. **Consolidation:** that session's inter-batch step ("Essential ⑥") is **not** built standalone — it is the **inter-batch caller of the same cross-file-interface accessor RUN-008 Step 9 builds** (Step 6 in v0.1; renumbered in v0.2). Building two inheritance implementations is the accidental complexity R3's distillation exists to prevent. The accessor is **one interface with a pluggable source**: intra-batch sources the producer's freshly-emitted `.d.ts` from the current run's disk (FR-1 disk-authoritative); inter-batch sources the prior batch's persisted `InterfaceContract` artifact (FR-1's contract-fallback role). Same accessor, two source adapters — no contract-vs-disk fork.
- **OQ-7** — Incremental `tsc` cost: a full project type-check per batch (or per feature) may be slow. Is one type-check at end-of-batch sufficient, or is per-feature incremental checking (`tsc --incremental`) warranted for earlier failure attribution?

---

## 5. Implementation Plan
The step-by-step plan lives in a companion document: **`docs/design/RUN_008_REMEDIATION_PLAN.md`**.

---

## Appendix A — Accepted Suggestions
*(empty — populated after CRP triage)*

## Appendix B — Rejected / Narrowed Suggestions (with rationale)
*(empty — populated after CRP triage)*

## Appendix C — Incoming Suggestions (Untriaged, append-only)
*(CRP review rounds append here)*

---

*v0.2 — Comprehensive TS-robustness direction. Promotes G3 to a first-class toolchain-backed track (FR-4 project `tsc`, FR-5 `prisma generate`/`validate`, FR-6 `.prisma` first-class, FR-8 `.d.ts` extraction), reverses the v0.1 Non-Requirement against project-wide `tsc`, demotes v0.1's hand-rolled `@/`/Prisma-usage signatures to a toolchain-absent fallback floor (FR-9), and keeps one residual bespoke check (FR-7 Prisma↔Zod symmetry). Resolves OQ-1 disk-authoritative via `.d.ts`. New OQ-3 (verification host/timing) is the load-bearing implementation unknown. Anchors unchanged from §0.*
