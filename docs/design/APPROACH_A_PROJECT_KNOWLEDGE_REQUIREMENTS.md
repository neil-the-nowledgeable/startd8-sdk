# Approach A — Pre-flight Project-Knowledge Artifact (the CodeGraph slice)

> ## ⚠️ SUPERSEDED BY CKG §8.1 (2026-06-01)
> This standalone spec is **superseded**. The live **Code Knowledge Graph (CKG)** track
> already owns this work as its **L5 Knowledge Provider** — see
> `CODE_KNOWLEDGE_GRAPH_DESIGN.md` §8.1 *"Knowledge Provider (pre-generation) = Approach A,
> done right."* CKG Phase 1 (the cross-file verifier / Approach B) is shipping on `main`;
> the generation-time Knowledge Provider (this doc's subject) is **CKG Phase 2**, owned by
> the CKG session (worktree `feat/ckg-phase1`).
>
> **Do not implement from this doc.** It was drafted before the author realized CKG Phase 1
> had shipped past the tree-sitter pin-conflict blocker; it would have built a *parallel
> regex `ProjectKnowledge` producer*, duplicating CKG's resolved model, `tsconfig_paths.py`,
> `cross_file_imports.py`, and Prisma DMMF (deferred/optional in CKG).
>
> **Retained for its CRP'd deltas only** — the few points that strengthen CKG's Knowledge
> Provider regardless of substrate are extracted in
> `APPROACH_A_TO_CKG_HANDOFF.md`. Implementation belongs to the CKG track.

**Version:** 0.3 (Post-CRP — convergent review R1 applied) — **SUPERSEDED, see banner**
**Date:** 2026-06-01
**Status:** Reviewed — CRP R1 applied (8 F-suggestions accepted); pairs with `APPROACH_A_PROJECT_KNOWLEDGE_PLAN.md` v1.1
**Source incidents:** `RUN_011_M4_FIELD_AND_PATH_INVENTION_POSTMORTEM.md` (Gaps A+B),
`CROSS_FILE_CONTRACT_RESOLUTION.md` §5 (Approach A) + §11 (the CodeGraph convergence).

> **What this is.** A deterministic, read-only **project-knowledge artifact** built
> before generation and injected as a P0 spec-context section, carrying the
> authoritative answers the LLM keeps inventing: the exact Prisma field sets, the
> canonical module-import paths (and the *non-existent* ones), `package.json`
> dependencies, and `tsconfig` path aliases. It generalizes the shipped Mode-A /
> Mode-B inheritance + the FR-3 Prisma field-set injection into **one** structured
> contract surface — and it is the generation-time **slice of the Mieruka
> `CodeGraph`**, so code-gen coherence and code-observability share one resolver
> rather than building it twice.

---

## 0. Planning Insights (Self-Reflective Update)

> Changes between v0.1 (the postmortem's "build a deterministic scanner" framing) and
> v0.2 (after reading the live seams). The grounding pass revealed that Approach A is
> a **generalization of code that already ships**, not a greenfield primitive — which
> reshapes scope, de-risks effort, and points at the likely Gap-A root cause.

| v0.1 assumption (from the postmortem) | Grounding discovery | Impact |
|---------------------------------------|---------------------|--------|
| Approach A is a new from-scratch scanner | The **first slice already ships**: `upstream_interface.render_prisma_field_sets` + `extract_ts_exports` + `prisma_parser` + `_package_name`, wired through `_collect_upstream_interfaces` → `gen_context["upstream_interfaces"]` → spec_builder | **FR-6** reframed: *generalize and unify the existing extractors into one artifact*, don't rebuild. Effort drops from medium to **small-medium** |
| The schema is "readable but the LLM guessed anyway" | The Prisma field-set injection (Gap-B FR-3) is **heuristic-gated** by `_feature_mirrors_data_model(feature)` and only renders for features that match — PI-001/004/007 plausibly **didn't trigger the heuristic**, so the field set was never injected for them | **FR-3/FR-5**: injection must be **reliably scoped to the entities a feature touches**, not gated by a name/description heuristic that silently skips |
| Gap B needs "more inheritance" | Mode B injects real *exports* but no **canonical module-path table** and no **negative signal** ("there is no `@/lib/prisma`; the client is `@/lib/db`") strong enough to beat the LLM's canonical-name prior; it also can't catch invented **sub-paths** (`@/lib/db/capabilities`) | **FR-4** is a distinct first-class requirement: an authoritative module-path table **with explicit negatives** for the recurring inventions |
| Build it "as the CodeGraph" before implementing | The Mieruka `CodeGraph` Phase 1 is **blocked** (tree-sitter/codebleu pin conflict) and is its own project; blocking Approach A on it stalls a shipping-now fix | **OQ-1 resolved:** converge on the **artifact schema/contract**, not a shared implementation on day one. Ship a minimal producer now (reusing the regex/stdlib extractors, which already exist) that conforms to the schema; Mieruka's `CodeGraph` becomes the production backend later. "Don't pay the integration tax twice" = **one schema**, swappable backend |
| tree-sitter adoption is a prerequisite | tree-sitter is **already a dependency** (`languages/csharp_parser.py` uses it); the pin conflict only blocks the *CodeBLEU* pairing | **FR-7/NFR**: v1 may use the existing regex/stdlib extractors (the "partial-code" tier); tree-sitter/SCIP are documented upgrade paths, not v1 gates |

**Resolved open questions (from this grounding pass):**
- **OQ-1 → Converge on schema, not implementation.** Define `forward_project_knowledge.json` as the shared contract; minimal producer now; Mieruka `CodeGraph` as the later backend. Approach A does **not** block on Mieruka Phase 1.
- **OQ-3 → Extend the existing seam.** Build on `_collect_upstream_interfaces` → `gen_context` → spec_builder (the proven path), not a parallel injection mechanism.

Open questions that remain (OQ-2, OQ-4, OQ-5, OQ-6) are in §6.

### CRP Review Update (v0.2 → v0.3)

An independent Convergent Review (R1) accepted all 8 F-suggestions. Key changes: FR-2
gains a **language-neutral symbol/URI core + a non-Prisma convergence test** (the load-
bearing claim is now tested, not just asserted); FR-8 splits into **FR-8a injection**
(deterministic) and **FR-8b adherence** (N≥5 seeds, threshold `PK_ADHERENCE_THRESHOLD`),
dropping the mis-scoped PI-010 (a type-class failure, not a field/path one); FR-5 relation
negatives are **derived from the parsed relation table**, not asserted in prose; FR-4 v1
negatives are the **seeded list** (derive-from-priors deferred to FR-4.1); FR-3 defines a
**depth-1 transitive-entity policy**; FR-9's budget is now a **normative formula**; NFR-3
gains a **testable omission-statement criterion**. Plan-side fixes (typed `RelationInfo`,
an `omissions` field, a pre-S5 characterization-snapshot step, a coverage audit in R3, and
producer-identity in the persisted artifact) are in `PLAN.md` v1.1.

---

## 1. Problem Statement & Gap Table

Run-011 (the M4 batch) produced the first **honest** verdict of this session (0.50 /
PARTIAL) because Approach B's classifier signatures now fire. But honesty exposed the
next layer: **5 of 10 features failed on content the LLM invented despite the truth
being on disk.** Mode-A/B inheritance propagates *module paths between same-batch
files* (which worked); it does **not** propagate *which fields an entity has* or
*which import paths are canonical vs hallucinated*.

| Category | What the LLM invented (run-011) | Truth on disk | Covered today? |
|----------|----------------------------------|---------------|----------------|
| **Prisma field names** (Gap A) | `aiRefId`, `label`, `outcomeId`, `title`, `supportingEvidence` | `name`, `category`, `evidence`, `value`, `unit`, … (in `prisma/schema.prisma`) | Partially — FR-3 injection is **heuristic-gated**, skipped these features |
| **Module-import paths** (Gap B) | `@/lib/prisma` (3rd recurrence), `@/lib/db/capabilities`, `@/lib/ai/client` | `@/lib/db` (exports `db`), `@/lib/ai/service` | Mode B injects exports, but no **authoritative path table + negatives** |
| **Dependency availability** | (covered) | `package.json` | Detected by Approach B; **not prevented** at the source |
| **Project config** (tsconfig aliases) | — (latent) | `tsconfig.json` `paths` | Not injected |

Root cause (per `CROSS_FILE_CONTRACT_RESOLUTION.md` §4): **per-file probabilistic
generation (locality).** Each feature is drafted in isolation; absent an authoritative,
structured, *injected* statement of the project's contract surface, the LLM fills gaps
with plausible-canonical guesses from its training distribution. Detection (Approach B)
makes failures honest; **only injection of the truth (Approach A) prevents them.**

---

## 2. Goal

Before a batch generates, build one deterministic, read-only project-knowledge artifact
and inject the **relevance-scoped** subset into every feature's spec prompt as a P0
section, framed authoritatively, so the drafter imports real paths and uses real fields
instead of inventing them — measurably reducing the run-011 failure classes to zero on
re-run, at bounded token cost, and on a schema the Mieruka `CodeGraph` can later produce.

---

## 3. Functional Requirements

### FR-1 — Deterministic project-knowledge artifact
A scanner (no LLM) reads the project at batch start and emits
`forward_project_knowledge.json` into the run's plan-ingestion output, carrying:
1. **Prisma model summary** — per model: `field → {type, nullable, default, id, unique}` and relations.
2. **Module-path table** — per exported symbol/module: its canonical import specifier (e.g. `db → @/lib/db`), derived from on-disk files + `tsconfig` `paths`.
3. **`package.json` snapshot** — declared dependencies + devDependencies (names; versions optional).
4. **`tsconfig` snapshot** — `paths` aliases + the compiler options that change validity (`target`, `lib`, `strict`, `module`, `moduleResolution`).
5. **Per-file export table** — for project source files: exported symbols (reuse `extract_ts_exports`).

*Acceptance:* against the strtd8 project root, the artifact lists `Capability` with exactly its schema fields (no `aiRefId`/`label`), and `modulePaths["db"] == "@/lib/db"`. Built with zero LLM calls. A project missing a `prisma/schema.prisma` or `tsconfig.json` produces a partial artifact (omits that section), never an error.

### FR-2 — Shared schema / resolver contract (CodeGraph convergence)
`forward_project_knowledge.json` MUST conform to a documented schema designed so the
Mieruka `CodeGraph` can produce it as a query result later (the artifact is a *view* of
the CodeGraph, per `CROSS_FILE_CONTRACT_RESOLUTION.md` §11). The producer backend is
swappable behind the schema; v1 ships a regex/stdlib producer (OQ-1).

**Language-neutral core (R1-F1/NFR-5):** the schema's first-class entity is a **symbol**
identified by a qualified name + a resolved file URI; the TS *import specifier*
(`db → @/lib/db`) and the Prisma-named `models` map are **derived TS/Prisma views** over
that core, not the core itself. A CodeGraph backend serving Go/Java/C# must be able to
populate the symbol/URI core without a Prisma model or a `tsconfig`-style path resolver.
*Acceptance:*
1. The schema is documented (a `pydantic` model + a JSON-schema/example).
2. The producer is injected behind an interface (`ProjectKnowledgeProducer` protocol) so
   a future `CodeGraph`-backed producer drops in without changing the injection seam.
3. **Convergence test (R1-F1):** a `ProjectKnowledge` can be constructed from
   **symbol-name + file-URI inputs alone — no Prisma model, no `tsconfig`** — and
   round-trips, proving `models`/import-specifiers are not the only first-class entities.

### FR-3 — Reliable, relevance-scoped injection (replaces the heuristic gate)
The artifact's relevant subset is injected into every feature's spec context as a P0
section via the existing `_collect_upstream_interfaces` → `gen_context` → spec_builder
path. Relevance scope = the feature's `target_files` import-graph closure **plus the
Prisma entities the feature references** — determined structurally, **not** by the
current `_feature_mirrors_data_model` name/description heuristic (which silently skipped
PI-001/004/007).
**Transitive references (R1-F6):** the scope policy MUST state whether an entity reached
only through a *relation* (feature touches `Outcome`; `Outcome` relates to `Metric`) is
included. v1 policy: include relation-reachable entities to depth 1; the whole-schema
fallback (≤ `PK_FULL_SCHEMA_MAX_MODELS`, see plan §1) subsumes this below the threshold.
*Acceptance:*
1. A reproduction of PI-001 (enrich-capabilities) receives the `Capability` + `Outcome`
   field sets **without** matching any name heuristic; injected-section token cost is
   bounded (FR-9).
2. **Transitive (R1-F6):** on a >`PK_FULL_SCHEMA_MAX_MODELS`-model fixture, a feature
   referencing entity A (where A relates to B) includes B per the stated depth-1 policy;
   an entity two relation-hops away is excluded.

### FR-4 — Module-path authority with explicit negatives (closes Gap B)
The injected section states, authoritatively, the canonical import path for each module
a feature is likely to use, **and explicit negatives for the recurring inventions**:
"The Prisma client is imported as `import { db } from '@/lib/db'`. There is no
`@/lib/prisma`, no `@/lib/db/<model>` sub-module, and the AI service is `@/lib/ai/service`
(not `@/lib/ai/client`)."

**v1 scope (R1-F4):** negatives are a **seeded constant list** of the recurring inventions
(`@/lib/prisma`, `@/lib/db/<model>`, `@/lib/ai/client`), per OQ-7. "Derive negatives from
the gap between the LLM's canonical-name priors and the real module-path table" is
**deferred to a future requirement** (FR-4.1) — it is not testable in v1 because "the
LLM's known priors" has no deterministic source.
*Acceptance:* (1) v1 negatives `==` the seeded constant list (no runtime prior-derivation);
(2) a reproduction of PI-002 / PI-007 imports emits only paths present in the module-path
table; the `@/lib/prisma` invention does not recur.

### FR-5 — Prisma field-set authority (closes Gap A)
For each entity a feature touches, the injected section lists the **exact** field set
with types and an explicit instruction: "Use only these fields; do not invent fields
(e.g. no `title`/`aiRefId`/`supportingEvidence`)."

**Relation negatives are derived, not asserted (R1-F3).** A statement like "`Metric` has
no FK to `Outcome`" MUST be **rendered from the artifact's parsed relation table** (the
absence of a `Metric→Outcome` relation), not written as a literal fact in the spec/prompt
text — a hard-coded project datum would rot and violates NFR-1 (the producer emits it).
*Acceptance:* (1) the artifact's `relations` for `Metric` lacks `Outcome` and the rendered
negative is generated from that absence, not a literal; (2) a reproduction of
PI-001/004/007 generates `db.<model>.create/update` calls using only fields in the
artifact; the run-011 invented-field set does not recur.

### FR-6 — Subsume the existing extractors (don't build twice)
The artifact producer reuses and unifies the shipped extractors —
`upstream_interface.extract_ts_exports` / `render_prisma_field_sets` /
`render_upstream_interfaces`, `prisma_parser.parse_prisma_schema`,
`cross_file_imports._package_name`. Mode-A sibling-producer inheritance and Mode-B
anchor inheritance become **queries over the same artifact**, not separate code paths.
*Acceptance:* `_collect_upstream_interfaces` is refactored to source Mode-A/B interface
rendering from the artifact; existing Mode-A/B tests
(`test_upstream_interface.py`, `test_mode_b_prisma_inheritance.py`) stay green.

### FR-7 — Two-tier substrate, partial-code tier for v1
The producer operates on **partial / non-building** code (the generation-time reality),
so v1 uses the regex/stdlib (`ast`/`symtable`) extractors that already exist. The
SCIP/buildable tier (post-build, precise) is a documented upgrade path that complements
the `tsc` gate — **out of v1 scope** (see Non-Requirements).
*Acceptance:* the artifact builds correctly when the project does not compile (mid-batch),
without requiring a provisioned toolchain.

### FR-8 — Validation against run-011 (injection ≠ adherence)
Two distinct gates (R1-F5/R1-S6 — injection is unit-testable; adherence is only
measurable from generated output):

**FR-8a — Injection (deterministic, unit/repro).** The reproduction harness targets the
four field/path-invention features **PI-001, PI-002, PI-004, PI-007** (PI-010 was a
TS2345 *type-class* failure — Gap C, handled by the postmortem signature, **not** Approach
A — so it is **out of scope** here, R1-F2). With the artifact injected, assert the spec
context contains the real `Capability`/`Outcome`/`Metric`/`Differentiator` field sets and
the `@/lib/db` / `@/lib/ai/service` paths + the seeded negatives. A no-artifact baseline
asserts the prior (gappy) context — proving the artifact is what changes the input.

**FR-8b — Adherence (empirical, E2E, probabilistic).** Re-generate the four features at
**N ≥ 5 seeds each** (or a temperature sweep) and compute an **adherence rate** =
(generations with zero invented fields/paths) / (total). The gate is **adherence rate ≥
`PK_ADHERENCE_THRESHOLD` (default 0.9)**; below it, OQ-4 escalation fires (draft self-check
/ Approach C). A single passing re-run does NOT satisfy FR-8b (can't distinguish a fix
from sampling luck).

### FR-9 — Bounded token cost
The injected section is relevance-scoped (FR-3) and size-bounded; the producer logs the
artifact size and the per-feature injected-token delta. A whole-project artifact must not
be injected wholesale into every feature.
*Acceptance (R1-F8 — normative):* the per-feature injected section stays within
`PK_SECTION_TOKEN_BUDGET`, defined as **`min(1024, 64 × entity_count + 256)` tokens**
(hard default, not illustrative); the warn fires at exactly that boundary and the budget +
actual are logged. The whole-project artifact is never injected wholesale.

### FR-10 — Read-only at generation time
The artifact is read-only during generation. New files a feature introduces are declared
via the existing Mode-A `depends_on` producer set (already handled) and surface to later
features through the artifact's per-file export table — no feature mutates the artifact
mid-batch.
*Acceptance:* concurrent feature generation reads a stable artifact; a producer file
generated by an earlier feature appears in the artifact view consumed by its dependents
(parity with today's Mode-A behavior).

---

## 4. Non-Functional Requirements

- **NFR-1 Deterministic.** No LLM in the producer; same project state → same artifact.
- **NFR-2 Fast & bounded.** One per-batch build; bounded read per feature.
- **NFR-3 Degrade loudly, never falsely.** Missing schema/config/file → omit that
  section + log; never silently inject a wrong/empty truth that the LLM would trust.
  *Acceptance (R1-F7):* when a section is omitted, the rendered P0 block **states the
  omission** ("Prisma schema not available — do not assume a field set") and **omits the
  field-authority claim entirely** — it must NOT render "use only these fields: (none)",
  which would falsely authorize the empty set. The artifact records the omission in an
  `omissions` field (plan §2) so the renderer can surface it.
- **NFR-4 Language-aware, TS/Prisma-first.** v1 targets the TS + Prisma surface that
  run-008/009/011 failed on; the schema is extensible to Go/Java/C# (pairs with the
  compile-gate roadmap) without rework.
- **NFR-5 Convergence-preserving.** The schema is the Mieruka `CodeGraph` contract;
  do not encode SDK-only assumptions that would block the CodeGraph backend.

---

## 5. Non-Requirements (v1)

- **Not** the full Mieruka `CodeGraph` build (tree-sitter Phase 1 is pin-blocked); v1 is
  the regex/stdlib producer conforming to the shared schema.
- **Not** retiring Approach B's regex signatures — they remain the cheap-now detection
  layer; querying the `CodeGraph` instead is a later convergence.
- **Not** the SCIP / buildable-precise tier (post-build; complements the `tsc` gate).
- **Not** Approach D (single-pass batch synthesis) — a separate, orthogonal lever.
- **Not** changing `clean-prior-run.sh` / the `upstream_anchors` signal — consumed, not built.
- **Not** guaranteeing the LLM *consults* the artifact (a content-level risk, OQ-4) —
  v1 maximizes the odds (P0, structured, authoritative, negatives) and **measures** it
  via FR-8b; it does not claim 100% adherence.

---

## 6. Open Questions

- **OQ-2 — Relevance-scoping algorithm.** Import-graph closure of `target_files` + a
  Prisma-entity reference scan? Or a simpler "all entities + the canonical module table"
  (small at strtd8 scale)? Trade token cost vs completeness. *(Plan to resolve.)*
- **OQ-4 — Adherence measurement.** *(Resolved by R1-F5.)* Measured empirically via
  **FR-8b**: adherence rate over N≥5 seeds/feature, gated at `PK_ADHERENCE_THRESHOLD`
  (default 0.9); below it, escalate to a draft-time self-check or Approach C. The
  *residual* uncertainty (will the threshold be met?) is carried into validation, not
  resolvable at spec time.
- **OQ-5 — tree-sitter vs regex for the v1 producer.** tree-sitter is already a dep;
  is its TS-export fidelity worth adopting now, or is `extract_ts_exports` (regex)
  sufficient for v1 given the pin-conflict isolation cost? *(Lean regex for v1.)*
- **OQ-6 — Artifact persistence & staleness.** Rebuild per batch (simple, always fresh)
  vs cache with mtime invalidation (faster, risk of staleness). *(Lean rebuild-per-batch.)*
- **OQ-7 — Negative-signal source (FR-4).** *(Resolved by R1-F4.)* v1 = the seeded
  constant list; derive-from-priors is deferred to future requirement **FR-4.1**.

---

## 7. Relationship to the roadmap

- **Closes:** RUN-011 Gap A (FR-5) + Gap B (FR-4) at the source; generalizes RUN-008
  Fix 1 (Mode A) and RUN-009 Fix 2 (Mode B) into one artifact (FR-6).
- **Complements:** Approach B (detection) — Approach A injects the truth, B verifies it;
  both will query the same `CodeGraph` after convergence (§11 of the resolution doc).
- **Pairs with:** the verification-ledger consolidation (RUN-011 Gap D, Fix 3) — both
  write into / read from the canonical project surface; can ship independently.
- **Does not gate:** strtd8 M4-M6 delivery (direct-fix + the honest gate proceed in
  parallel); this reduces the direct-fix burden on future batches.

---

*v0.3 — Convergent Review R1 applied: all 8 F-suggestions accepted. FR-2 convergence
test + language-neutral core; FR-8 split into injection (8a) / adherence (8b) with N-seed
threshold; FR-5 relation negatives derived not asserted; FR-4 v1 = seeded list; FR-3
depth-1 transitive policy; FR-9 normative budget; NFR-3 omission-statement criterion.
Pairs with `APPROACH_A_PROJECT_KNOWLEDGE_PLAN.md` v1.1. (v0.2 — post-planning reframe:
"generalize the shipped extractors" not a new scanner; OQ-1/OQ-3 resolved.)*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

> Append-only convergent-review state. New reviewers add a round to **Appendix C**, then
> dispositions are recorded in **Appendix A** (applied) or **Appendix B** (rejected).
> Reviewers: scan A/B/C first and do **not** re-propose settled or rejected items.

### Appendix A: Applied Suggestions

| ID | Area | Suggestion (summary) | Merged into |
|----|------|----------------------|-------------|
| R1-F1 | Interfaces | Test the convergence claim with a non-Prisma symbol; language-neutral symbol/URI core | FR-2 (acceptance #3 + language-neutral core) |
| R1-F2 | Validation | PI-010 undefined — it's a type-class failure (Gap C), drop from the harness | FR-8a (scoped to PI-001/002/004/007) |
| R1-F3 | Data | Derive relation negatives ("Metric no FK to Outcome") from the parsed table, not prose | FR-5 (relation-negatives-derived) |
| R1-F4 | Interfaces | Scope v1 negatives to the seeded list; defer derive-from-priors | FR-4 (v1 scope + FR-4.1 deferral) |
| R1-F5 | Validation | Add sample size + adherence threshold + escalation trigger | FR-8b (N≥5, `PK_ADHERENCE_THRESHOLD`); OQ-4 resolved |
| R1-F6 | Risks | Define transitive/relation-reachable entity scoping | FR-3 (depth-1 policy + acceptance #2) |
| R1-F7 | Validation | NFR-3 testable: omitted sections stated, not silently empty | NFR-3 (omission-statement acceptance) |
| R1-F8 | Ops | Make the token budget normative, not "~800" | FR-9 (`min(1024, 64×entity_count+256)`) |

### Appendix B: Rejected Suggestions (with Rationale)
_None — all 8 R1 F-suggestions accepted (anchored, testable, sharpened the FR-2
convergence + FR-8 adherence risks)._

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-01

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-01 21:40:00 UTC
- **Scope**: Requirements quality for Approach A, weighted to the sponsor focus (FR-2 schema convergence, OQ-4 adherence, OQ-2 scoping, FR-4 negatives). Testable acceptance criteria and FR↔plan traceability.

**Focus-file asks (sponsor) — answered before standard suggestions:**

- **Ask 1 — Is the `ProjectKnowledge` shape the right CodeGraph contract, or does it bake in SDK-only assumptions?**
  - **Summary answer:** Partial — the shape is close but leaks two TS/Prisma-specific assumptions that NFR-5 forbids.
  - **Rationale:** FR-1's `module_paths` keys on a TS *import specifier* (`db → @/lib/db`) and `models` is named for Prisma. A language-agnostic CodeGraph produces *symbols with qualified names + resolved file URIs*, not import specifiers. NFR-5 says "do not encode SDK-only assumptions that would block the CodeGraph backend," yet FR-1.2/FR-1.4 hard-code `tsconfig` `paths` resolution as the path-authority source.
  - **Assumptions / conditions:** Holds if Mieruka's CodeGraph is intended to serve non-TS projects (NFR-4 says the schema must extend to Go/Java/C#).
  - **Suggested improvements:** see R1-F1, R1-F4.

- **Ask 2 — Will P0 + negatives + "use only these fields" actually move the LLM off its canonical-name prior (OQ-4)?**
  - **Summary answer:** Necessary-but-insufficient; the requirements correctly decline to *claim* adherence but under-specify the *escalation trigger*.
  - **Rationale:** FR-8 asserts "zero invented fields/paths" as a binary gate but OQ-4 says adherence is empirical. There is no stated numeric adherence threshold or sample size that decides "weak → escalate." A single re-run of 5 features is too small to distinguish "fixed" from "got lucky."
  - **Assumptions / conditions:** none.
  - **Suggested improvements:** see R1-F5, R1-F7.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Interfaces | high | FR-2's acceptance criterion ("schema is documented ... producer injected behind an interface") does not test the *convergence* claim. Add an acceptance criterion that the schema is expressible as a CodeGraph query result for at least one non-Prisma symbol kind (e.g. a plain TS export with no Prisma model), proving `models` is not the only first-class entity. | NFR-5 forbids SDK-only assumptions but FR-2 only verifies the SDK-side producer, not that a CodeGraph backend could populate the same fields. The load-bearing convergence decision is currently untested. | FR-2 acceptance | Add a fixture asserting a `ProjectKnowledge` can be constructed from symbol+URI inputs (no Prisma) and round-trips. |
| R1-F2 | Validation | high | FR-8 lists "PI-010-field-portion" as a reproduction target but PI-010 is not defined anywhere in the doc (unlike PI-001/002/004/007 which appear in §0 and the Gap table). Define what "field-portion" means or drop it. | An implementer cannot build the FR-8 harness without knowing which fields of PI-010 are in scope; "field-portion" is untestable as written. | FR-8 acceptance, verbatim: "PI-010-field-portion" | Verify the harness fixture set enumerates exactly the features named, each with a concrete expected field/path assertion. |
| R1-F3 | Data | medium | FR-5 states "`Metric` has no FK to `Outcome`" as a hard-coded fact in the requirement text. This is a project-specific datum that will rot. Reframe FR-5 to require *relation negatives be derived from the parsed schema's relation table*, not asserted in prose. | A requirement that embeds a specific project's schema fact (verbatim: "`Metric` has no FK to `Outcome`") is not a requirement, it is test data, and it contradicts NFR-1 determinism (the producer should emit this, not the spec). | FR-5 body | Verify the artifact's `relations` for `Metric` is empty/lacks `Outcome` and the negative is rendered from that, not a literal. |
| R1-F4 | Interfaces | medium | FR-4 defines negatives as "generated from the gap between the LLM's known canonical-name priors and the real module-path table" but provides no testable definition of "the LLM's known canonical-name priors." As written this is unverifiable. Either scope FR-4 v1 to the *seeded* list only (matching OQ-7's "seed now") and move "derive from priors" to a future requirement, or specify the prior-source. | The acceptance criterion only checks the seeded inventions recur to zero; the "generated from the gap" clause is aspirational and untestable, creating a spec/acceptance mismatch. | FR-4 body, verbatim: "generated from the gap between the LLM's known canonical-name priors" | Verify v1 negatives == the seeded constant list; assert no runtime prior-derivation in v1. |
| R1-F5 | Validation | high | FR-8's headline gate is binary ("zero invented Prisma fields, zero invented module paths") on a single re-run, but OQ-4 frames adherence as probabilistic. Add an acceptance criterion specifying sample size (e.g. N≥3 seeds per feature or temperature sweep) and an adherence rate threshold that defines "weak → escalate per OQ-4." | Without a stated N and threshold, a one-shot pass cannot distinguish a real fix from sampling luck, and the OQ-4 escalation path has no objective trigger. | FR-8 acceptance + OQ-4 | Re-run harness at N seeds; assert adherence rate ≥ threshold; assert escalation fires below it. |
| R1-F6 | Risks | medium | FR-3's relevance scope ("`target_files` import-graph closure **plus the Prisma entities the feature references**") has no acceptance criterion for *transitive* entity references — an entity reached only through a relation (e.g. feature touches `Outcome`, which relates to `Metric`). The focus file (OQ-2) explicitly worries about "entities a feature touches transitively." | FR-3 acceptance only tests PI-001 receiving `Capability`+`Outcome` directly; it does not test that a transitively-referenced entity is included or deliberately excluded. The plan's whole-schema fallback masks this at strtd8 scale but not for >12-model projects. | FR-3 acceptance | Add a >12-model fixture where a feature references entity A, A relates to B; assert B's inclusion policy is defined and tested. |
| R1-F7 | Validation | medium | NFR-3 ("Degrade loudly, never falsely") has no acceptance criterion, unlike FR-1's "produces a partial artifact ... never an error." Add a testable NFR-3 criterion: when a section is omitted, the rendered P0 block must *state the omission* so the LLM is not silently told a truth is absent (vs. believing the empty set is authoritative). | "Never silently inject a wrong/empty truth that the LLM would trust" is the stated intent but is not verifiable; an empty `models` map rendered as "use only these fields: (none)" is exactly the false-authority failure NFR-3 warns against. | NFR-3, verbatim: "never silently inject a wrong/empty truth" | Assert that with no `prisma/schema.prisma`, the rendered section omits the field-authority claim entirely rather than rendering an empty list. |
| R1-F8 | Ops | low | FR-9's token budget is stated as "e.g. ≤ ~800 tokens" with "e.g." and "~", making it non-normative. Pick a hard number (or a formula keyed to model count) so the FR-9 log-and-warn assertion has a definite threshold. | An acceptance criterion gated on an illustrative budget cannot pass/fail deterministically. | FR-9 acceptance, verbatim: "≤ ~800 tokens" | Assert the warn fires at the exact configured budget boundary. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
_None — first review round; no prior untriaged items._

> **Triage note (2026-06-01):** R1 triaged by the orchestrator — all 8 F-suggestions
> **accepted** and merged into the v0.3 body (dispositions in Appendix A). No rejections.

## Areas Substantially Addressed

| Area | Accepted (R1) | Addressed (≥3)? |
|------|---------------|-----------------|
| Validation | 4 (F2, F5, F7 + F-coverage) | ✓ |
| Interfaces | 2 (F1, F4) | — |
| Data | 1 (F3) | — |
| Risks | 1 (F6) | — |
| Ops | 1 (F8) | — |
