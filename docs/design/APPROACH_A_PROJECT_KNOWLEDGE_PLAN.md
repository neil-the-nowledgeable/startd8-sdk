# Approach A — Project-Knowledge Artifact — Implementation Plan

> ## ⚠️ SUPERSEDED BY CKG §8.1 (2026-06-01)
> This implementation plan is **superseded** and must **not** be executed. Approach A is
> owned by the live **Code Knowledge Graph (CKG)** track as its **L5 Knowledge Provider**
> (`CODE_KNOWLEDGE_GRAPH_DESIGN.md` §8.1), built on CKG's resolved model + helpers
> (`tsconfig_paths.py`, `cross_file_imports.py`, Prisma DMMF [deferred/optional]) — **not** the
> bespoke regex `ProjectKnowledge` producer (S1/S2) this plan describes, which would duplicate CKG.
>
> The S3 renderer + S5 injection-seam ideas remain relevant but belong on CKG's model;
> the salvageable, substrate-independent deltas are in `APPROACH_A_TO_CKG_HANDOFF.md`.
> Implementation belongs to the CKG session (worktree `feat/ckg-phase1`).

**Version:** 1.1 (Post-CRP — convergent review R1 applied; pairs with `APPROACH_A_PROJECT_KNOWLEDGE_REQUIREMENTS.md` v0.3) — **SUPERSEDED, see banner**
**Date:** 2026-06-01
**Status:** Reviewed — CRP R1 applied (7 S-suggestions accepted); ready to implement S1→S8.

This plan decomposes Approach A into discrete, testable changes against the **existing**
seams (the requirements' §0 established that this is a *generalization* of shipped code,
not a greenfield build). It resolves the open questions, fixes the data model, and
sequences the work so each step ships green.

---

## 1. Architecture decisions (resolves the open questions)

| OQ | Decision | Rationale |
|----|----------|-----------|
| **OQ-1** (schema vs impl) | Define `ProjectKnowledge` (pydantic) + a `ProjectKnowledgeProducer` Protocol; ship a `RegexProjectKnowledgeProducer` now behind it | Converge on the **contract**; the Mieruka `CodeGraph` becomes a drop-in producer later without touching the injection seam. Doesn't block on pin-conflicted tree-sitter Phase 1. |
| **OQ-2** (relevance scope) | **Module-path table: always injected in full** (it's tiny — a handful of modules). **Prisma field sets: entities the feature references** (names found in `target_files` paths + the feature description/plan slice), with a **whole-schema fallback when the model count ≤ `PK_FULL_SCHEMA_MAX_MODELS` (default 12)** | strtd8 has 9 models — full-schema injection is cheap and eliminates "the heuristic skipped my entity" (the Gap-A cause). Larger projects scope down. |
| **OQ-4** (adherence) | v1 maximizes odds (P0 section, authoritative framing, explicit negatives, a one-line draft instruction) and **measures** via the FR-8 re-run. If adherence is weak, escalate (draft self-check / Approach C) — tracked, not built now | The postmortem's own caveat: Approach A can't *force* consultation. Measure before adding machinery. |
| **OQ-5** (tree-sitter vs regex) | **Regex/stdlib for v1** — reuse `extract_ts_exports` + `prisma_parser` | tree-sitter export-fidelity gain doesn't justify the pin-conflict isolation cost in v1; the producer is swappable (OQ-1) so tree-sitter can back it later. |
| **OQ-6** (persistence) | **Rebuild once per batch**, persist `forward_project_knowledge.json` to the run output dir for audit; no mtime cache | Always-fresh, deterministic (NFR-1), trivial. Caching is premature at batch cadence. |
| **OQ-7** (negatives) | **Seed** the recurring inventions (`@/lib/prisma`, `@/lib/db/<model>`, `@/lib/ai/client`); derive from canonical-name priors later | Cheap, covers the observed recurrences now; extensible as new inventions surface. |

---

## 2. Data model — the shared schema (FR-1, FR-2)

New module `src/startd8/contractors/project_knowledge.py`:

```python
class FieldInfo(BaseModel):
    type: str
    nullable: bool = False
    default: str | None = None
    is_id: bool = False
    unique: bool = False

class RelationInfo(BaseModel):    # R1-S4: typed, not list[dict]
    name: str
    model: str                     # target entity
    many: bool = False

class ModelInfo(BaseModel):
    fields: dict[str, FieldInfo]
    relations: list[RelationInfo] = []   # FK-absence negatives derive from this (R1-F3)

class Symbol(BaseModel):           # R1-F1: language-neutral first-class entity
    qualified_name: str            # e.g. "db", "Capability"
    file_uri: str                  # resolved path
    kind: str                      # "binding" | "prisma_model" | "function" | ...

class ModulePath(BaseModel):
    specifier: str                 # TS *view*: "@/lib/db"  (derived from Symbol+tsconfig)
    exports: list[str]             # ["db"]

class ProjectKnowledge(BaseModel):
    symbols: list[Symbol] = []                 # R1-F1 language-neutral core
    models: dict[str, ModelInfo] = {}          # Prisma view
    module_paths: dict[str, ModulePath] = {}   # TS view: symbol/module -> path+exports
    invalid_module_paths: list[str] = []       # FR-4 seeded negatives (R1-F4)
    packages: list[str] = []                   # package.json deps+devDeps
    tsconfig: dict = {}                         # paths + target/lib/strict/module
    file_exports: dict[str, list[str]] = {}    # path -> exported symbols
    omissions: list[str] = []                  # R1-S5/R1-F7: sections not scanned + why
    producer: str = "regex"                    # R1-S7: which backend built this
    schema_version: int = 1

class ProjectKnowledgeProducer(Protocol):
    def build(self, project_root: str, anchors: list[str]) -> ProjectKnowledge: ...
```

`RegexProjectKnowledgeProducer.build()` composes the **already-shipped** extractors
(FR-6): `prisma_parser.parse_prisma_schema` → `models`; `extract_ts_exports` over
project TS files → `file_exports` + `module_paths`; `cross_file_imports._package_name`
+ a `package.json` read → `packages`; a `tsconfig.json` read → `tsconfig` (+ `paths`
feed `module_paths`). `invalid_module_paths` seeded from a constant list (OQ-7).

The pydantic model **is** the CodeGraph view contract (FR-2): a future
`CodeGraphProjectKnowledgeProducer` returns the same type.

---

## 3. Renderer — artifact → P0 spec section (FR-4, FR-5)

`render_project_knowledge(pk: ProjectKnowledge, *, entities: list[str]) -> str` emits a
compact authoritative block:

```
## Project contract (authoritative — use ONLY what is listed)
Imports: the Prisma client is `import { db } from "@/lib/db"`. AI service:
`import { ... } from "@/lib/ai/service"`. Do NOT import `@/lib/prisma`,
`@/lib/db/<model>`, or `@/lib/ai/client` — they do not exist.
Prisma models (use only these fields; do not invent fields):
- Capability: id, ownerId, source, confirmed, name?, category?, description?, proficiency?, notes?
- Outcome: id, ownerId, ... ; Metric has NO foreign key to Outcome.
Dependencies available (package.json): @anthropic-ai/sdk, zod, next, ...
```

Negatives (FR-4) and the "use only these fields" instruction (FR-5) are explicit. The
renderer is the single place that frames the truth authoritatively.

---

## 4. Injection seam refactor (FR-3, FR-6, FR-9, FR-10)

`prime_contractor.py`:

1. **Build once per batch.** In `load_seed_context` (where `project_root` +
   `seed_upstream_anchors` are known), construct `self._project_knowledge =
   self._pk_producer.build(self.project_root, self.seed_upstream_anchors)` and persist
   it to `<run>/plan-ingestion/forward_project_knowledge.json`. `self._pk_producer`
   defaults to `RegexProjectKnowledgeProducer()` (swappable — OQ-1). **The persisted JSON
   embeds `schema_version` + `producer` (R1-S7)** so artifacts from different backends
   (regex vs CodeGraph) are distinguishable on disk for audit.
2. **Refactor `_collect_upstream_interfaces`** to source its renders from the artifact:
   - Mode A/B TS interface rendering → `file_exports` / `module_paths` lookups (FR-6;
     preserve existing output so `test_upstream_interface` / `test_mode_b_prisma_inheritance`
     stay green).
   - **Replace** the heuristic-gated FR-3 Prisma block: always append
     `render_project_knowledge(pk, entities=relevant_entities(feature, pk))` (FR-3) —
     no `_feature_mirrors_data_model` gate.
3. **Relevance scope** `relevant_entities(feature, pk)` (OQ-2 + R1-S3/R1-F6):
   - If `len(pk.models) <= PK_FULL_SCHEMA_MAX_MODELS` (default 12) → **return all models**
     (strtd8's 9 models hit this — eliminates the heuristic-skip that caused Gap A).
   - Else (>12-model projects): seed = entity names matched in `feature.target_files` +
     `feature.description`; then **expand by relation to depth 1** (for each seed entity,
     add entities reachable via `ModelInfo.relations`). Entities two relation-hops away
     are excluded. This is the documented transitive policy R1-F6/R1-S3 asked for; the
     `>12-model` fixture test (FR-3 acceptance #2) gates it.
4. **Token bound + logging** (FR-9): log artifact size + the rendered section's token
   estimate per feature; warn if over `PK_SECTION_TOKEN_BUDGET` (default ~800).
5. **Read-only** (FR-10): the artifact is built before per-feature generation and not
   mutated; Mode-A producer outputs already surface via the existing on-disk reads
   (keep that path; the artifact augments, doesn't replace, sibling inheritance).

---

## 5. Implementation sequence (each step ships green)

| Step | Change | FRs | Files | Test |
|------|--------|-----|-------|------|
| **S1** | `ProjectKnowledge` schema + `ProjectKnowledgeProducer` protocol | FR-1, FR-2 | `contractors/project_knowledge.py` | schema round-trip + protocol |
| **S2** | `RegexProjectKnowledgeProducer.build()` reusing shipped extractors | FR-1, FR-6, FR-7 | same + reuse `upstream_interface`, `prisma_parser`, `cross_file_imports` | build against strtd8 root → asserts `Capability` fields, `db→@/lib/db` |
| **S3** | `render_project_knowledge()` with negatives + field-set authority | FR-4, FR-5 | same | golden render asserts negatives + exact fields |
| **S4** | Build-once-per-batch + persist json (incl. `schema_version`+`producer`) | FR-1, FR-9, NFR-1/3 | `prime_contractor.load_seed_context` | artifact written; partial + `omissions` recorded on missing schema/tsconfig |
| **S4.5** | **Characterization snapshot (R1-S1):** capture *current* `_collect_upstream_interfaces` output as golden fixtures for the at-risk inputs — **absent-anchor** and **Mode-A not-yet-generated producer** cases — before any refactor | (de-risks S5) | new `tests/.../test_collect_upstream_interfaces_characterization.py` | golden snapshot of today's output on the edge inputs |
| **S5** | Refactor `_collect_upstream_interfaces` to source from artifact; drop heuristic gate | FR-3, FR-6, FR-10 | `prime_contractor._collect_upstream_interfaces` | existing Mode-A/B tests green **+ S4.5 snapshots reproduce byte-for-byte** + new always-injected test |
| **S6** | Relevance scope (incl. depth-1 transitive) + token bound/logging | FR-3, FR-9 | same | scoping unit (≤12 + >12 transitive) + budget log assertion |
| **S7** | Run-011 reproduction harness (injection, FR-8a) | FR-8a | `tests/.../test_approach_a_repro.py` | PI-001/002/004/007 fixtures: real fields/paths injected, gappy baseline |
| **S8** | Adherence E2E (FR-8b) — optional, post-merge | FR-8b | E2E `--fresh` re-run | adherence rate ≥ `PK_ADHERENCE_THRESHOLD` over N≥5 seeds |

S1–S3 are pure additions (no behavior change). **S4.5 is the de-risking gate for S5** —
the snapshot proves output parity on the exact edge inputs the legacy suite may not cover.
S5 is the only behavior-changing step.

---

## 6. Testing strategy (FR-8 is the headline gate)

- **Unit:** schema round-trip; producer against a fixture project (the strtd8 schema +
  a `lib/db.ts` + `package.json` + `tsconfig.json` fixture); renderer golden output.
- **Regression:** `test_upstream_interface.py`, `test_mode_b_prisma_inheritance.py`,
  `test_cross_file_integrity_postmortem.py` stay green (FR-6 preserves behavior).
- **Reproduction = injection only (FR-8a, R1-S6).** Fixtures derived from the run-011
  features (PI-001/002/004/007). With the artifact injected, assert the **spec context**
  contains the real field sets + `@/lib/db` / `@/lib/ai/service` paths + the seeded
  negatives; a no-artifact baseline asserts the prior gappy context. **This proves the
  truth was *injected* — it cannot prove the LLM *used* it** (the prompt is the unit under
  test, not the generation).
- **Adherence = E2E (FR-8b, R1-S6/R1-F5).** Generation output is the only place adherence
  is measurable: a real `--fresh` M4 re-run at **N≥5 seeds/feature**; assert adherence
  rate ≥ `PK_ADHERENCE_THRESHOLD` (default 0.9). Below threshold → OQ-4 escalation. This is
  S8, distinct from S7 — do not conflate "injected" with "adhered."

---

## 7. Risks

- **R1 — Adherence (OQ-4).** The LLM may still ignore the P0 truth. *Mitigation:* explicit
  negatives + "use only these fields" instruction; measure via FR-8/E2E; escalate to a
  draft self-check only if measured weak. **This is the load-bearing uncertainty.**
- **R2 — Token cost.** Whole-schema injection on a large project. *Mitigation:* FR-9
  bound + `PK_FULL_SCHEMA_MAX_MODELS` scope-down + logging.
- **R3 — Refactor regression (S5).** Subsuming Mode-A/B could change their output.
  *Mitigation (strengthened, R1-S2):* "existing tests green" is **necessary but not
  sufficient** — it only proves parity on tested inputs. Before S5, run a **coverage audit
  of `_collect_upstream_interfaces` branches** for the three at-risk behaviors
  (absent-anchor warning, Mode-A not-yet-generated producer, no-TS/JS-upstream early
  return). For any branch found **uncovered**, **write the missing characterization test
  first (S4.5) or explicitly scope it out of S5** — do not refactor an unasserted branch.
  S5 lands only when the legacy suite **and** the S4.5 snapshots pass.
- **R4 — Schema drift from CodeGraph (FR-2).** The v1 schema might not match Mieruka's
  eventual `CodeGraph` query shape. *Mitigation:* the language-neutral `Symbol`
  (qualified_name + file_uri) core + the FR-2 non-Prisma round-trip test (added in R1)
  keep the contract backend-agnostic; `models`/`module_paths` are explicit TS/Prisma
  *views* over the core. CRP R1 pressure-tested this — it was the load-bearing finding.
- **R5 — Regex extractor fidelity (OQ-5).** `extract_ts_exports` may miss exotic export
  forms. *Mitigation:* v1 targets the Next.js/Prisma surface that actually failed;
  tree-sitter backend is the upgrade path.

---

## 8. What this plan deliberately leaves out

Per the requirements' Non-Requirements: no full CodeGraph build, no SCIP tier, no
Approach B retirement, no Approach D, no `clean-prior-run` changes. The verification-
ledger consolidation (RUN-011 Gap D / Fix 3) is independent and can ship in any order.

---

*Plan 1.1 — Convergent Review R1 applied (7 S-suggestions accepted): typed `RelationInfo`
+ language-neutral `Symbol` core, an `omissions` field, a pre-S5 characterization-snapshot
step (S4.5), a strengthened R3 coverage audit, explicit >12-model + depth-1 transitive
scoping, S7/S8 injection-vs-adherence split, and producer-identity in the persisted
artifact. Pairs with REQUIREMENTS v0.3. Ready to implement S1→S8.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

> Append-only convergent-review state. New reviewers add a round to **Appendix C**;
> dispositions recorded in **Appendix A** (applied) / **Appendix B** (rejected).
> Scan A/B/C first; do not re-propose settled or rejected items.

### Appendix A: Applied Suggestions

| ID | Area | Suggestion (summary) | Merged into |
|----|------|----------------------|-------------|
| R1-S1 | Validation | Characterization snapshot of `_collect_upstream_interfaces` edge cases before S5 | §5 step S4.5 |
| R1-S2 | Risks | R3: pre-refactor coverage audit + write-missing-test-or-scope-out if uncovered | §7 R3 |
| R1-S3 | Architecture | Specify >12-model scoping incl. depth-1 transitive relations | §4 item 3 |
| R1-S4 | Data | Typed `RelationInfo` (not `list[dict]`); language-neutral `Symbol` core | §2 schema |
| R1-S5 | Interfaces | `omissions` field so the renderer can state omissions (NFR-3) | §2 schema (`omissions`) |
| R1-S6 | Validation | Note S7 tests injection only; adherence needs E2E at N seeds | §5 (S7/S8 split), §6 |
| R1-S7 | Ops | Persist `schema_version` + `producer` identity in the artifact | §2 schema, §4 item 1 |

### Appendix B: Rejected Suggestions (with Rationale)
_None — all 7 R1 S-suggestions accepted (each anchored to a step/section and closed a
real traceability or coverage gap, esp. the S5 refactor-safety and FR-2 convergence)._

> **Triage note (2026-06-01):** R1 triaged by the orchestrator — all 7 S-suggestions
> **accepted** and merged into the v1.1 body (dispositions in Appendix A). The
> Coverage Matrix below is the R1 snapshot; the Partials it flagged are now resolved by
> the merges (FR-2/F1→§2 Symbol core + FR-2 test; FR-3/S3→§4.3 transitive; FR-5/S4→typed
> relations; FR-8/S6→S7/S8 split; FR-9/F8→normative budget; NFR-3/S5→`omissions`).

## Areas Substantially Addressed

| Area | Accepted (R1) | Addressed (≥3)? |
|------|---------------|-----------------|
| Validation | 3 (S1, S6 + matrix) | ✓ |
| Architecture | 1 (S3) | — |
| Data | 1 (S4) | — |
| Interfaces | 1 (S5) | — |
| Risks | 1 (S2) | — |
| Ops | 1 (S7) | — |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-01

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-01 21:40:00 UTC
- **Scope**: Plan quality for Approach A, weighted to the sponsor focus (FR-2 CodeGraph schema convergence, the S5 refactor risk, OQ-2 scoping, FR-4 negatives). FR↔step traceability and validation strategy.

**Focus-file asks (sponsor) — answered before standard suggestions:**

- **Ask (S5) — Is "keep the existing Mode-A/B tests green" a sufficient gate for the S5 refactor?**
  - **Summary answer:** No — it is necessary but not sufficient; it cannot catch behaviors the existing tests do not exercise.
  - **Rationale:** §5 calls S5 "the only behavior-changing step — gated by keeping the existing Mode-A/B tests green." But the focus file names three behaviors (`_collect_upstream_interfaces` edge cases, absent-anchor warnings, Mode-A not-yet-generated producers) whose coverage by `test_upstream_interface`/`test_mode_b_prisma_inheritance` is unknown. A green legacy suite proves *output parity on tested inputs only*; the refactor changes the *source* of that output (artifact lookups vs. direct reads), so untested edge inputs can silently diverge.
  - **Assumptions / conditions:** Holds unless a coverage audit shows the three named behaviors are already asserted.
  - **Suggested improvements:** see R1-S1, R1-S2, R1-S6.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Validation | high | Before S5, add a characterization step that captures the *current* `_collect_upstream_interfaces` output for the absent-anchor and not-yet-generated-producer cases as golden fixtures, then assert S5 reproduces them. "Keep existing tests green" is insufficient because those tests may not cover these inputs. | §5 declares S5 the only behavior-changing step but gates it on a suite of unknown coverage. The refactor moves output sourcing from direct reads to artifact lookups; un-asserted edge cases can diverge silently. | §5 table, between S4 and S5 (new S4.5 or expand S5 Test cell) | Snapshot legacy output on edge inputs pre-refactor; diff post-refactor. |
| R1-S2 | Risks | high | R3's mitigation ("the existing Mode-A/B tests are the gate") inherits the same coverage blind spot. Strengthen R3 to require a pre-refactor coverage audit of the three focus-named behaviors, and state what happens if a behavior is found *uncovered* (write the missing test first, or scope it out of S5). | R3 as written treats the legacy suite as authoritative without verifying it exercises the at-risk paths the sponsor flagged. | §7 R3 mitigation | Coverage report on `_collect_upstream_interfaces` branches before S5 lands. |
| R1-S3 | Architecture | high | The OQ-2 decision injects the **module-path table in full always** plus **whole-schema field sets when ≤12 models**, but the plan never states the policy for the >12-model case beyond "scope down." Specify the scoping algorithm (FR-3 says import-graph closure + entity-reference scan) concretely in §4.3, including whether transitively-related entities (via `relations`) are pulled in. | The focus file (OQ-2) explicitly worries entity-name match "will miss entities a feature touches transitively." `relevant_entities` in §4.3 only matches names in `target_files` + `description` — a relation-reachable entity is silently dropped above the fallback threshold. | §4 item 3, `relevant_entities(feature, pk)` | Unit test on a >12-model fixture: feature references A, A relates to B; assert B inclusion per stated policy. |
| R1-S4 | Data | medium | §2's `ProjectKnowledge` schema names the relation field as `relations: list[dict]  # {name, model, many}` — an untyped `dict`. Promote it to a `RelationInfo` BaseModel so FR-4/FR-5 relation negatives (e.g. "`Metric` has no FK to `Outcome`") can be derived and tested against a typed structure, and so the CodeGraph contract (FR-2) is fully typed. | An untyped `list[dict]` defeats the FR-2 "documented pydantic schema" goal for the relation portion and makes relation-derived negatives stringly-typed. | §2 schema, `relations: list[dict]` | Schema round-trip test includes a typed relation; renderer derives the FK-absence negative from it. |
| R1-S5 | Interfaces | medium | The `ProjectKnowledgeProducer.build(self, project_root, anchors)` signature in §2 omits a way to signal *partial* production (which sections were omitted and why), which FR-1/NFR-3 require ("produces a partial artifact ... never an error" / "degrade loudly"). Add an explicit `omissions`/`warnings` field to `ProjectKnowledge` or the build return so the renderer can state omissions (see requirements R1-F7). | The schema has no field to record that, e.g., `prisma/schema.prisma` was absent; the renderer cannot distinguish "no models" from "models not scanned," which is the NFR-3 false-authority risk. | §2 `ProjectKnowledge` model | Build against a project missing schema; assert an omission is recorded and surfaced in the render. |
| R1-S6 | Validation | medium | S7 (run-011 reproduction) and §6 assert "the spec context contains the real field sets/paths," i.e. they test *injection*, not *adherence*. Add an explicit note in §6 that S7 validates injection only, and that adherence (OQ-4/R1) requires the E2E re-run with a stated sample size and threshold (cross-ref requirements R1-F5). | §6 conflates "the truth was injected" with "the LLM used it." FR-8's "zero invented fields" can only be measured by generation output, not by inspecting the prompt — the unit/repro layer cannot prove the gate. | §6 "Reproduction (FR-8)" bullet | Repro asserts prompt content; a separate E2E asserts generated-code adherence at N seeds. |
| R1-S7 | Ops | low | §4 item 1 persists `forward_project_knowledge.json` to `<run>/plan-ingestion/` but the plan does not state whether the artifact embeds its `schema_version` and producer identity (regex vs CodeGraph) in the persisted file. Record both so audit/debugging can tell which backend produced a given run's artifact (supports the FR-2 swap). | When the CodeGraph producer later drops in (OQ-1), persisted artifacts from different backends will be indistinguishable on disk without a producer tag. | §4 item 1, persistence | Assert the written JSON includes `schema_version` and a `producer` field. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
_None — first review round; no prior untriaged items._

---

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each requirement (FR/NFR) → plan step(s)/section → Covered / Partial / Gap.

| Requirement | Plan Step(s) / Section | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 (deterministic artifact) | S1, S2, S4; §2 schema | Covered | — |
| FR-2 (shared CodeGraph schema/resolver) | §1 OQ-1, §2 (pydantic model); S1 | Partial | Schema convergence asserted SDK-side only; no test that a non-Prisma symbol round-trips (see R1-F1, R1-S4). Relation field untyped (R1-S4). |
| FR-3 (reliable relevance-scoped injection) | S5, S6; §4 items 2–3 | Partial | Transitive/relation-reachable entity scoping undefined for >12-model case (R1-S3, R1-F6). |
| FR-4 (module-path negatives) | S3; §3 renderer; OQ-7 seed | Partial | "Derive from canonical-name priors" untestable in v1; acceptance only covers seeded list (R1-F4). |
| FR-5 (Prisma field-set authority) | S3; §3 renderer | Partial | Relation negative ("Metric no FK to Outcome") embedded as prose/test-data rather than derived from typed relations (R1-F3, R1-S4). |
| FR-6 (subsume existing extractors) | S2, S5; §2, §4 item 2 | Covered | Behavior-parity gate depends on legacy-test coverage of edge cases (tracked under R1-S1/S2). |
| FR-7 (partial-code tier, regex v1) | S2; §1 OQ-5 | Covered | — |
| FR-8 (validation vs run-011) | S7; §6 | Partial | Validates injection, not adherence; binary gate lacks sample size/threshold (R1-S6, R1-F5); PI-010 undefined (R1-F2). |
| FR-9 (bounded token cost) | S6; §4 item 4 | Partial | Budget illustrative ("~800"), non-normative threshold (R1-F8). |
| FR-10 (read-only at gen time) | S5; §4 item 5 | Covered | — |
| NFR-1 (deterministic) | OQ-6 rebuild-per-batch; §1 | Covered | — |
| NFR-2 (fast & bounded) | OQ-6; S6 | Covered | — |
| NFR-3 (degrade loudly, never falsely) | §4 item 5; S4 partial-artifact | Partial | No criterion that omitted sections are *stated* in the render vs. silently empty (R1-F7, R1-S5). |
| NFR-4 (language-aware, TS/Prisma-first, extensible) | §2; OQ-5 | Partial | Extensibility to Go/Java/C# asserted but schema keys on TS import specifiers (R1-F1). |
| NFR-5 (convergence-preserving) | §1 OQ-1; §2 | Partial | SDK-only assumptions (`tsconfig` path resolution, Prisma-named `models`) risk blocking CodeGraph backend (R1-F1). |
