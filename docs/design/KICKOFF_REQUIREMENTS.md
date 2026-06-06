# Kickoff Requirements — User Inputs into the Build Process

**Version:** 0.3 (operator decision walkthrough — all 5 cross-class OQs resolved; see §9)
**Date:** 2026-06-05 (v0.1: extracted from `OBSERVABILITY_INPUT_PROVISIONING_REQUIREMENTS.md` v0.2)
**Status:** Draft

> **v0.2 CRP triage summary.** Convergent Review ran 2 rounds (R1 opus, R2 sonnet w/ adversarial
> pass) over the 5-doc set: 35 anchored suggestions, **ACCEPT 35 / REJECT 0** — all code-verified
> and non-overlapping (R2 endorsed 13 R1 items, re-proposed none). Headline fixes: the
> seven-manifest count reconciled (pages.yaml dual role); delegation markers on FR-X1/X3/I1; the
> FR-X4 "run quality report" named (`kaizen-metrics.json` `input_provisioning`); the
> `micro_prime` `convention_guidance` finding (hardcoded Python house style ≠ FR-H1 declared
> manifest — FR-H2 reframed); credential-presence + prompt-file catalog rows added. Per-file
> dispositions in each doc's Appendix A.
**Role:** **Master doc** for everything the user provides at the *start* of a build — the kickoff.
Catalogs ALL input classes at a high level; domain detail lives in companion slices (§6).
**Lineage:** The 2026-06-05 broadening of `OBSERVABILITY_INPUT_PROVISIONING_REQUIREMENTS.md`
(v0.2) was extracted here so that doc could return to its observability focus. The §0 planning
insights from that reflective pass (codebase-grounded, 8 assumptions tested) carry over and are
summarized below. Coverage reference: `strtd8/docs/v2/ASSEMBLY_INPUTS.md` (the first per-project
input inventory — every entry there is covered in §3 and detailed in a slice).

---

## 0. Planning Insights (carried from the reflective pass)

> Drafted assumption-first, then planned against the real seams of cap-dev-pipe (`pipeline/`
> package), `backend_codegen/`, plan ingestion, `project_knowledge/`, and the build-preference
> knobs. Key corrections that shape every requirement below:

| Assumption tested | Discovery | Consequence |
|-------------------|-----------|-------------|
| New input classes need new input surfaces | Mostly they **exist**: the deterministic cascade already consumes user manifests (`schema.prisma`, `app.yaml`, `pages.yaml`, `ai_passes.yaml`, `human_inputs.yaml`, `completeness.yaml`, `views.yaml`), hash-stamped into drift headers; cost budget / tier routing / profile env all exist | Requirements are about **visibility, provenance, status, and reach** — not new files |
| The staged pipeline can gate deterministic generation | `generate backend/scaffold/views` is a **standalone pre-pipeline $0 CLI** — zero cap-dev-pipe references (bucket separation by design) | The pipeline **records and flags** cascade inputs; it never orchestrates the cascade |
| RESOLVE might need new collection code | RESOLVE is **payload-agnostic** (`contextcore manifest fix` over arbitrary `guidance.questions[]` id↔answer pairs; `cap-dev-pipe/pipeline/stages/export.py:121–142`) | New classes ride the machinery by adding **questions/manifest fields** — ContextCore-owned (delegation per `OBSERVABILITY_POLISH_INPUT_REQUIREMENTS.md` v0.3 §2.2) |
| Conventions flow into generation prompts via onboarding-metadata | They **don't** — onboarding-metadata drives preflight/provenance only; convention authority (`project_knowledge`) reaches the lead/drafter path **only**; `micro_prime/` has zero refs (RUN-028); spec-authoring + test-gen also unreached (RUN-038) | Conventions need **collection AND injection-reach** requirements (Group H) |
| Cost budget / language / profile need surfaces | Budget + ~10 routing knobs exist; language is **inferred-only**; profile env exists but the REQ-GPC consumer is **unimplemented** | Group I = provenance + two real gaps (language declaration, default-vs-authored visibility) |

---

## 1. Problem & Input Classes

Wherever a build-driving input is un-derivable and uncollected, the pipeline either ships a
placeholder (`REPLACE_WITH_WEBHOOK_URL`, `Owner: contact`) or — worse — **invents** a value
(RUN-028: Flask-vs-FastAPI, `app.models`-vs-`app.tables`, SQLAlchemy-vs-SQLModel). The kickoff is
the moment to collect what only the user knows, mark what's placeholder, and record where every
value came from — so artifacts are *correct on first emit* and "looks done" never conceals "needs
the company's real input."

The kickoff input surface decomposes into **five classes**, each with a domain slice:

| Class | What the user provides | Group | Domain slice |
|-------|------------------------|-------|--------------|
| **Data-model & assembly** | the `.prisma` contract + the other cascade manifests (`app.yaml`, `human_inputs.yaml`, `ai_passes.yaml`, `completeness.yaml`, `views.yaml`; `pages.yaml` is the **seventh** cascade manifest — counted in F's inventory, owned by Group G for content semantics) | F | [`kickoff/KICKOFF_ASSEMBLY_INPUTS.md`](kickoff/KICKOFF_ASSEMBLY_INPUTS.md) |
| **User/company content** | `pages.yaml` + `app/pages/*.md` prose, placeholder copy, seed fixtures (buckets 2/4) | G | [`kickoff/KICKOFF_CONTENT_INPUTS.md`](kickoff/KICKOFF_CONTENT_INPUTS.md) |
| **Domain vocabulary & conventions** | framework/ORM/module-path conventions, domain terms, `onboarding-metadata.json` | H | [`kickoff/KICKOFF_CONVENTION_INPUTS.md`](kickoff/KICKOFF_CONVENTION_INPUTS.md) |
| **Build preferences** | cost budget, model/tier routing, language/stack, generation profile, orchestration config | I | [`kickoff/KICKOFF_BUILD_PREFERENCE_INPUTS.md`](kickoff/KICKOFF_BUILD_PREFERENCE_INPUTS.md) |
| **Observability & business targets** | SLO targets, thresholds, receivers, owners, runbook content, KPI targets | A–E | [`OBSERVABILITY_INPUT_PROVISIONING_REQUIREMENTS.md`](OBSERVABILITY_INPUT_PROVISIONING_REQUIREMENTS.md) |

Group letters are stable across the doc set: **A–E** live in the observability slice (the original
canonical doc), **F–I** in the four kickoff slices, **X** (cross-class machinery) here.

---

## 2. Where Inputs Enter

```
(pre-pipeline, $0 deterministic — buckets 1–2)
  schema.prisma + app.yaml + pages.yaml + ai_passes.yaml + human_inputs.yaml
      + completeness.yaml + views.yaml + app/pages/*.md + seeds/*.seed.json
      → startd8 generate scaffold / backend / views  →  application skeleton
                 │  (standalone CLI — NOT a pipeline stage; recorded per FR-F1)
                 ▼
Stage 0 CREATE → Stage 1 POLISH → Stage 1.5 ANALYZE → Stage 2 INIT → Stage 2.5 RESOLVE
   → Stage 3 VALIDATE → Stage 4 EXPORT → (onboarding-metadata.json) → INGESTION → generation
                                                                        (bucket 3 — integration)
```

- **Stage 1 POLISH** — plan quality gate today (`contextcore polish --strict`). **The flag point**:
  where a missing catalogued input becomes a visible pre-flight gap (FR-X1).
- **Stage 2 INIT** — bootstraps `.contextcore.yaml` from `plan.md` + `requirements.md`; where most
  manifest-borne inputs originate.
- **Stage 2.5 RESOLVE** — **the collect/ask point** (`pipeline/stages/export.py:121–142` →
  `contextcore manifest fix`). Pre-provided answers (`design/question-answers.yaml`) → defaults →
  interactive prompt (TTY-gated). Payload-agnostic: new input classes add *questions*, not code.
- **Stage 3 VALIDATE** — the hard gate for inputs the criticality matrix marks required (FR-X3).
- **Stage 4 EXPORT** — projects the manifest into `onboarding-metadata.json` (the generator's only
  read surface).

**POLISH (flag) → RESOLVE (collect) → VALIDATE (gate)** is the collection pipeline. The
**pre-pipeline lane** (the deterministic cascade) runs outside it by design; Group F requires the
staged pipeline to *know about* the cascade's inputs (record/flag/provenance) without ever
orchestrating the cascade.

---

## 3. Master Input Catalog

Every kickoff input, mapped to its class and slice. Entries marked **(AI)** appear in the
reference inventory `strtd8/docs/v2/ASSEMBLY_INPUTS.md` — all of its entries are covered here.

| Input | Class | Mechanism | Detail in |
|-------|-------|-----------|-----------|
| `prisma/schema.prisma` **(AI)** | F | `generate backend/views --schema` (required) — the contract, single source of truth | Assembly slice §2.1 |
| `app.yaml` (repo root) **(AI)** | F | `generate scaffold` — project name, db path, WAL, migrations, logging, container, env | Assembly slice §2.2 |
| `prisma/human_inputs.yaml` **(AI)** | F | `generate backend --human-inputs` — owned-field policy (fields AI must not write) | Assembly slice §2.3 |
| `prisma/ai_passes.yaml` **(AI)** | F | `generate backend --ai-passes` — AI pass manifest (extract + enrichment passes) | Assembly slice §2.4 |
| `prisma/completeness.yaml` **(AI)** | F | `generate backend --completeness` — completeness signal set + score formula | Assembly slice §2.5 |
| `prisma/views.yaml` **(AI)** | F | `generate views` — composite-view manifest (value-map, dashboards, workspaces, export) | Assembly slice §2.6 |
| `prisma/pages.yaml` **(AI)** | G | `generate backend --pages` — content pages + nav | Content slice §2.1 |
| `app/pages/*.md` prose | G | discovered via `pages.yaml` `content:` paths; untracked (temporal model) | Content slice §2.2 |
| `seeds/*.seed.json` (e.g. `extract.seed.json`) **(AI)** | G | seed/fixture data for AI passes & view-test seeding | Content slice §2.3 |
| AI-pass prompt files (e.g. `prompts/*.md`) | G | referenced by path from `ai_passes.yaml` (owned harness embeds the path only) | Content slice §2.4 |
| Convention manifest (proposed `semantic_conventions.yaml`) | H | per-run declaration: framework, ORM, module paths, naming | Conventions slice §3.1 |
| `onboarding-metadata.json` | H | `context_files` / `contextcore_export_dir` (user-provided) | Conventions slice §2.2 |
| `.contextcore.yaml` `guidance` (constraints `C-*` / preferences `PREF-*`) | H | operator-level convention surface | Conventions slice §2.3 |
| Controlled corpus (`.startd8/controlled-corpus.json`) | H | durable vocabulary store (pre-implementation) | Conventions slice §2.4 |
| `--cost-budget` | I | CLI both repos; enforced ceiling (default `"5.00"`) | Build-prefs slice §2.1 |
| Model/tier routing knobs (~10 flags) | I | `--lead-agent`/`--drafter-agent`/`--tier3-agent`/`--provider`/`--complexity-*` | Build-prefs slice §2.2 |
| `GENERATION_PROFILE` / `--profile` | I | env + planned flag (REQ-GPC-800/801) | Build-prefs slice §2.3 |
| Language/stack declaration (proposed) | I | today inferred-only (`languages/resolution.py:167`) | Build-prefs slice §2.4 |
| `.cap-dev-pipe/pipeline.env` **(AI)** | I | pipeline env (provider, SDK root, project root, profile, instrumentation) | Build-prefs slice §2.5 |
| `.cap-dev-pipe/design/question-answers.yaml` **(AI)** | I/X | pre-seeded answers for RESOLVE (unattended channel) | Build-prefs slice §2.6 |
| `.cap-dev-pipe/explain-content.yaml` **(AI)** | I | explain-mode display copy (**presentation-only** — never influences generated artifacts; REQ-CDP-EDU-009) | Build-prefs slice §2.7 |
| Provider credential **presence** (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / …) | I | env vars — presence-only check for the providers the routing knobs select (**never the value**) | Build-prefs slice §2 |
| `plan.md` + `requirements.md` | (root) | the upstream source of Stage 2 INIT — the kickoff documents themselves | §2 above |
| `.contextcore.yaml` `spec`/`strategy`/`insights` | A–E | SLOs, owners, risks, receivers, thresholds, business targets | Observability slice §3–§6b |
| `roles.yaml` business KPIs + targets | E | role portals + business SLOs | Observability slice Group E / §6b |

**Path convention (AI):** contract-derived manifests live under `prisma/` (siblings of
`pages.yaml`); the project scaffold manifest `app.yaml` lives at the repo root. Codified in the
template (FR-F5) so every project's inventory is navigable the same way.

---

## 4. Cross-Class Requirements (Group X)

The machinery every class shares. Domain slices state per-class requirements against these.

- **FR-X1 — One pre-flight report, five classes.** Stage 1 POLISH MUST report, per input class,
  each catalogued build-driving input as **`authored | placeholder | absent`** with the expected
  downstream impact (e.g. "conventions absent → micro-prime-routed views at invention risk").
  Sentinel placeholders (`REPLACE_WITH_*`, `contact`, `*@example.com`, scaffolded stubs) are never
  reported `authored`. Presentation-only inputs (e.g. `explain-content.yaml`) are recorded but
  carry **no build-impact warning**. **Delegation marker (mirrors FR-X2):** the report *mechanics*
  (emission at Stage 1 POLISH = `contextcore polish`) are ContextCore/cap-dev-pipe-owned; startd8
  owns the input catalog, the per-class state-assignment semantics, and the impact text. **The
  report is advisory** — binding actions live in the named FRs (FR-X3 matrix gating; FR-H2 routing
  precondition); the invention-risk example text is backed by FR-H2's routing guard, not by this
  report.
- **FR-X2 — RESOLVE carries all classes (delegated).** New-class collection rides the existing
  payload-agnostic question machinery (`guidance.questions[]` + `question-answers.yaml` +
  `contextcore manifest fix`). The question catalog and manifest schema are **ContextCore-owned**;
  this is a delegated requirement per the established ownership split (gather flow + schema:
  ContextCore/cap-dev-pipe; consumption + injection reach: startd8). **Startd8-side testable
  proxy** (so the delegation is never vacuously "passing"): for each Group F–I input with a
  RESOLVE question, a pre-seeded `question-answers.yaml` entry MUST surface in the FR-X4
  provenance record as `supplemental:pre-seeded` — verifiable entirely within cap-dev-pipe +
  startd8 scope, regardless of ContextCore internals.
- **FR-X3 — Criticality matrix spans classes.** The required-vs-flagged matrix (observability
  slice FR-E1) gains rows per class — e.g. `critical/high` ⇒ data-model contract `authored` +
  conventions declared-or-derived; `medium` ⇒ flagged only. Bucket-2 content is **never**
  matrix-mandatory (placeholders are the intended default); bucket-4 readiness is reported, not
  gated. Missing non-required inputs degrade gracefully (generation proceeds with honest low
  scores) — inputs improve output, they are not hard gates unless the matrix says so.
  **Dependency note:** the FR-E1 matrix (observability doc) is the **base table this FR extends**
  — FR-X3 is co-deployed with FR-E1, not independently testable; the new-class rows are defined
  against that table (master OQ-4 holds the exact row set). **Delegation marker:** gating
  *mechanics* (Stage 3 VALIDATE) are cap-dev-pipe/ContextCore-owned; startd8 owns the per-class
  row semantics. Routing consequences (re-route vs gate) remain FR-H2's — this matrix never
  silently substitutes for the routing guard.
- **FR-X4 — Provenance + per-class provisioning score.** Every consumed input value records its
  provenance: `authored` (manifest/file) | `supplemental:pre-seeded` (`question-answers.yaml`) |
  `supplemental:interactive` (RESOLVE prompt) | `config-default` | `templated`/inferred. **Enum
  mapping (provenance ↔ FR-X1 status):** `authored`/`supplemental:*` → status `authored`;
  `config-default`/`templated`/inferred → status `placeholder`; no value at any tier → `absent`
  — the FR-X1 report renders the status enum with the provenance tier in parentheses (e.g.
  `cost_budget: placeholder (config-default)`). **Named artifact:** the per-class
  **`input_provisioning_score`** lands in an `input_provisioning` section of
  **`kaizen-metrics.json`** (SDK-owned, written by `prime_postmortem.py` — the component that
  already owns run quality reporting), keyed by class (F/G/H/I + A–E), values in [0,1], fed by
  the FR-X1 report + provenance records. **Denominator:** the *applicable* FR-X5 inventory
  entries for the class — MUST/SHOULD inputs only; MAY-inputs (e.g. FR-G4 fixtures) are
  excluded from the denominator and counted in the numerator only when present (they can raise,
  never lower, the score). Kaizen trends provisioning independently of generation quality.
- **FR-X5 — Per-project input inventory (the template).** Each project MUST carry a kickoff input
  inventory instantiated from
  [`kickoff/ASSEMBLY_INPUTS_TEMPLATE.md`](kickoff/ASSEMBLY_INPUTS_TEMPLATE.md) — the
  project-agnostic template derived from `strtd8/docs/v2/ASSEMBLY_INPUTS.md` (the reference
  instance). The inventory enumerates the project's actual input files, what each drives, its
  phase, and its provisioning status; the FR-X1 pre-flight report and FR-F1 provenance record are
  generated against it.

---

## 5. Group Requirements (high level — detail in slices)

### Group F — Data-model intent & deterministic-assembly inputs
*(detail: [`kickoff/KICKOFF_ASSEMBLY_INPUTS.md`](kickoff/KICKOFF_ASSEMBLY_INPUTS.md))*

- **FR-F1 — Cascade-input provenance record.** Path + content hash (reuse drift-header hashes) +
  provisioning status for every assembly manifest, recorded where the staged pipeline reads it.
- **FR-F2 — POLISH flags data-model status.** A missing or scaffold-stub `schema.prisma` is
  `placeholder`/`absent`, never `authored`. Report by default; gate per FR-X3.
- **FR-F3 — Bookend bracketing.** Collection directs the user to the DATA MODEL / RETROSPECTIVE
  human bookends (`docs/design-princples/DATA_MODEL_AND_RETROSPECTIVE.md`); the pipeline records
  the contract, it never authors it.
- **FR-F4 — `human_inputs.yaml` reaches integration.** The owned-field policy binds the bucket-3
  LLM glue, not just the deterministic edge schemas.
- **FR-F5 — Inventory completeness.** All **seven** assembly manifests — `schema.prisma`,
  `app.yaml`, `human_inputs.yaml`, `ai_passes.yaml`, `pages.yaml` (dual role: cascade-consumed,
  Group-G-owned), `completeness.yaml`, `views.yaml` — plus the path convention are enumerated in
  the per-project inventory (FR-X5).

### Group G — User/company content & fixtures (buckets 2/4)
*(detail: [`kickoff/KICKOFF_CONTENT_INPUTS.md`](kickoff/KICKOFF_CONTENT_INPUTS.md))*

- **FR-G1 — Placeholder/authored marking.** Content prose MAY carry lightweight front-matter
  status, with defaults-by-origin and `placeholder` as the unknown-origin fallback; front-matter
  is stripped at render; drift surface untouched (temporal model preserved).
- **FR-G2 — Content provisioning score.** Authored ÷ total pages feeds FR-X4; all-placeholder runs
  score honestly low.
- **FR-G3 — Collection ≠ authorship.** The pipeline collects bucket-4 content *references* and
  flags placeholders; it never generates or improves real company content.
- **FR-G4 — Declared fixtures.** Seed/fixture files (e.g. `seeds/extract.seed.json`) are declared
  + provenance-recorded when present; their absence is never flagged (bucket 2).

### Group H — Domain vocabulary & conventions
*(detail: [`kickoff/KICKOFF_CONVENTION_INPUTS.md`](kickoff/KICKOFF_CONVENTION_INPUTS.md))*

- **FR-H1 — First-class convention declaration.** Per-run manifest (framework, ORM, module paths,
  naming) — the RUN-028 invention class, declared instead of invented.
- **FR-H2 — Injection reach.** Collected authority MUST reach lead/drafter spec authoring,
  **micro_prime**, and **test-gen**; a tier that can't receive it MUST NOT be routed
  convention-strict work. **Note (CRP R2 code finding):** micro_prime's existing
  `convention_guidance` injection (`micro_prime/context.py` via
  `repair/convention.py:render_convention_guidance()`) is a **hardcoded Python-only house-style
  block** — it partially closes the bypass for Python idioms only; FR-H2's remaining requirement
  is wiring the FR-H1 *user-declared* manifest into that same path. The existing injection never
  satisfies FR-H2 on its own.
- **FR-H3 — Onboarding-metadata as declared input.** Provenance records which consumed fields
  drove what.
- **FR-H4 — Corpus alignment (advisory).** Declarations seed the controlled corpus when it ships;
  no duplicate accumulation machinery here.
- **FR-H5 — Evidence vs declaration precedence.** Evidence wins for field-sets; declaration wins
  for non-derivable choices; conflicts flagged, never silently resolved.

### Group I — Build preferences & orchestration config
*(detail: [`kickoff/KICKOFF_BUILD_PREFERENCE_INPUTS.md`](kickoff/KICKOFF_BUILD_PREFERENCE_INPUTS.md))*

- **FR-I1 — Preference catalog + provenance.** Every preference records which precedence tier
  supplied it (`defaults < pipeline.yaml < pipeline.env < CLI < env vars`).
- **FR-I2 — Language/stack declaration.** Explicit declaration input; inference becomes fallback;
  declared≠inferred mismatch flagged.
- **FR-I3 — Generation profile: collect now, consume per REQ-GPC.** Don't re-spec the consumer.
- **FR-I4 — Budget default visibility.** Defaulted `"5.00"` distinguishable from authored;
  surfaced in the pre-flight report.
- **FR-I5 — Orchestration config provenance.** `pipeline.env`, `question-answers.yaml`,
  `explain-content.yaml` are catalogued kickoff inputs with provenance like any other
  (`explain-content.yaml` recorded as presentation-only; secret-class answers in
  `question-answers.yaml` use env-var indirection).
- **FR-I6 — Credential presence (never values).** Provider credential **presence** for the
  providers the routing knobs select is a catalogued Group I input: FR-X1 reports `authored`
  (set) / `absent` (unset) **before any LLM call** — the key string itself is never read into
  any report (see scoped §7 non-goal).

### Groups A–E — Observability & business targets
*(detail: [`OBSERVABILITY_INPUT_PROVISIONING_REQUIREMENTS.md`](OBSERVABILITY_INPUT_PROVISIONING_REQUIREMENTS.md))*

The original canonical requirements, unchanged: setup/config field population + sentinel
validation (A), schema extensions for thresholds/runbook/receivers/SLO-overrides/handoff targets
(B), polish-stage supplemental inputs (C), provenance & scoring (D — generalized by FR-X4),
business KPI targets (E — matrix generalized by FR-X3).

---

## 6. Companion Doc Set

| Doc | Covers | Group |
|-----|--------|-------|
| [`kickoff/KICKOFF_ASSEMBLY_INPUTS.md`](kickoff/KICKOFF_ASSEMBLY_INPUTS.md) | the 7 cascade manifests (contract + 6 siblings, incl. dual-role `pages.yaml`), path convention | F |
| [`kickoff/KICKOFF_CONTENT_INPUTS.md`](kickoff/KICKOFF_CONTENT_INPUTS.md) | pages, prose, fixtures/seeds | G |
| [`kickoff/KICKOFF_CONVENTION_INPUTS.md`](kickoff/KICKOFF_CONVENTION_INPUTS.md) | conventions, vocabulary, onboarding-metadata, corpus | H |
| [`kickoff/KICKOFF_BUILD_PREFERENCE_INPUTS.md`](kickoff/KICKOFF_BUILD_PREFERENCE_INPUTS.md) | budget, routing, profile, language, orchestration config | I |
| [`OBSERVABILITY_INPUT_PROVISIONING_REQUIREMENTS.md`](OBSERVABILITY_INPUT_PROVISIONING_REQUIREMENTS.md) | observability + business-target inputs | A–E |
| [`kickoff/ASSEMBLY_INPUTS_TEMPLATE.md`](kickoff/ASSEMBLY_INPUTS_TEMPLATE.md) | the per-project inventory template (FR-X5) | — |
| [`HITM_ROLE_MODEL_REQUIREMENTS.md`](HITM_ROLE_MODEL_REQUIREMENTS.md) | the human dimension: 11 delivery roles (Customer/PO→QA incl. Security), authorship tiers (U/E/D/G/R + class M), hash-bound validation gates, reuse-approval | J |
| [`kickoff/KICKOFF_INPUT_PACKAGE_GUIDE.md`](kickoff/KICKOFF_INPUT_PACKAGE_GUIDE.md) + [`kickoff/templates/`](kickoff/templates/) | the per-project kickoff input package (intro + business-facing asks + per-domain value files) — internal guide + project-agnostic templates; reference instance: `strtd8/docs/kickoff/` | — |

---

## 7. Non-Goals

- No change to the deterministic, $0 generation model — inputs are structured data / imported
  documents, not new LLM calls.
- Inputs are not mandatory by default (graceful degradation; FR-X3 governs the exceptions).
- The staged pipeline does **not** invoke or orchestrate `startd8 generate scaffold/backend/views`
  (bucket separation) — it records and flags their declared inputs only.
- The SDK does **not** author bucket-4 content (FR-G3) — real value content is provided by the
  user / commissioning company.
- Does not implement the REQ-GPC profile consumer or the controlled corpus (cited, owned
  elsewhere), and does not wire `costs/budget.py` `BudgetManager`.
- Does not manage secret **value** storage — receiver targets etc. use env/secret indirection.
  This non-goal is scoped to values only: it does NOT exclude presence-only checks (FR-I6), which
  carry zero secret data.

---

## 8. Acceptance Snapshot (high level)

- The FR-X1 pre-flight report lists provisioning status across **all five classes** for a strtd8
  run, generated against the project's FR-X5 inventory.
- A RUN-028-class failure is structurally prevented: a micro-prime-routed convention-strict task
  either receives convention authority or is re-routed (FR-H2).
- Pages provisioning is honest: an all-placeholder run reports content score ≈ 0; `.md` edits
  still never flag drift (FR-G1/G2).
- Cascade provenance present with drift-header hashes (FR-F1); a defaulted cost budget is visible
  as `config-default` (FR-I4); a declared-vs-inferred language mismatch is flagged (FR-I2).
- Per-class `input_provisioning_score` appears in the run quality report (FR-X4).
- Observability-slice acceptance: per that doc's §8 (unchanged).

---

## 9. Open Questions (cross-class) — ALL RESOLVED (operator walkthrough, 2026-06-05)

Domain-specific OQs live in the slices. Cross-class dispositions:

1. ~~**Convention-manifest home (FR-H1/FR-I2).**~~ **RESOLVED (Q1):** conventions + language are
   **generated by the plan ingestion workflow** (tier G draft derived from `plan.md`/
   `requirements.md`), persisted as a reviewable file, **validated/enhanced by the Architect**,
   then reused across runs as an authored input (provenance flips `templated/inferred` →
   `authored` on validation). Not hand-authored; not a ContextCore schema extension.
2. ~~**Cascade-provenance home (FR-F1).**~~ **CLOSED (Q2): operator-coordinated.** The durable
   record-home machinery was CRP-induced over-formalization — the operator coordinates audit/
   record delivery when a real need arises. FR-F1 keeps the *what* (hashes, statuses); no
   system home is built proactively.
3. ~~**Supplemental-file generalization.**~~ **RESOLVED (Q3): per-class, observability only.**
   `observability-inputs.yaml` as spec'd (FR-C1); generalization deferred until another class
   demonstrates a per-run supplemental need.
4. ~~**Matrix rows for new classes (FR-X3).**~~ **RESOLVED (Q4): not needed for the demo.**
   Observability inputs come from the **industry default dataset**
   ([`kickoff/OBSERVABILITY_DEFAULTS_END_USER_APPLICATION.md`](kickoff/OBSERVABILITY_DEFAULTS_END_USER_APPLICATION.md),
   industry = `end_user_application`, provenance `config-default`); business inputs route to the
   human request list there. The matrix stays observability-only (FR-E1) and earns new rows only
   from observed misses.
5. ~~**Inventory authoring (FR-X5).**~~ **RESOLVED (Q5): hand-authored + CLI drift check.**
   `startd8 assist` diffs the inventory against on-disk manifests/CLI flags — flags drift, never
   writes (FR-F5's 1:1:1 acceptance is this check). *(Note: `startd8 wireframe` now also
   consumes the inventory's machine-readable YAML form — see the template §"Machine-readable
   instantiation".)*

---

*v0.3 — Operator decision walkthrough (2026-06-05): all 5 cross-class OQs resolved (Q1–Q5 above;
Q6–Q8 in the HITM doc). v0.2 — Post-CRP triage: 11 master suggestions applied (Appendix A), 24
more across the four slices. 5 input classes, 5 cross-class FRs (X1–X5), 20 group FRs (incl. new
FR-I6), all `strtd8/docs/v2/ASSEMBLY_INPUTS.md` entries covered (§3).*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-F-master-1 | Reconcile seven-manifest count + pages.yaml dual role | R1 (opus) | §1 class-F row (dual role stated), §5 FR-F5 (seven named), §6 row fixed ("contract + 6 siblings") | 2026-06-05 |
| R1-F-master-2 | Delegation markers on FR-X1/FR-X3; standardize POLISH-vs-preflight | R1 (opus); endorsed R2 | §4 FR-X1 + FR-X3 delegation markers added; slice H FR-H5 / slice I FR-I2 owner named (preflight) | 2026-06-05 |
| R1-F-master-3 | FR-X4 enum mapping + denominator definition | R1 (opus); endorsed R2 | §4 FR-X4: provenance↔status mapping; denominator = applicable MUST/SHOULD inventory entries, MAY-inputs numerator-only | 2026-06-05 |
| R1-F-master-4 | Catalog row for AI-pass prompt files | R1 (opus) | §3 new row (class G → Content slice §2.4) | 2026-06-05 |
| R1-F-master-5 | Credential presence as Group I input (presence-only) | R1 (opus); endorsed R2 | §3 new row + §5 new FR-I6; §7 non-goal scoped to values | 2026-06-05 |
| R2-F-master-1 | Link FR-X1 invention-risk text to a binding FR or mark advisory | R2 (sonnet) | §4 FR-X1: report declared advisory; binding action = FR-H2 routing guard + FR-X3 gating, cross-referenced | 2026-06-05 |
| R2-F-master-2 | Name the FR-X4 "run quality report" artifact | R2 (sonnet) | §4 FR-X4: `input_provisioning` section of `kaizen-metrics.json`, owner `prime_postmortem.py`, keyed by class | 2026-06-05 |
| R2-F-master-3 | FR-X3 testability vs FR-E1 dependency | R2 (sonnet) | §4 FR-X3: FR-E1 named as base table; co-deployed, not independently testable; row set held in OQ-4 | 2026-06-05 |
| R2-F-master-4 | Correct micro_prime bypass claim (hardcoded `convention_guidance` partial bridge) | R2 (sonnet) | §5 FR-H2 note: existing injection = Python house style only; never satisfies FR-H2 alone | 2026-06-05 |
| R2-F-master-5 | Startd8-side testable proxy for delegated FR-X2 | R2 (sonnet, adversarial) | §4 FR-X2: pre-seeded answer → `supplemental:pre-seeded` provenance check | 2026-06-05 |
| R2-F-master-6 | Scope the secrets non-goal to value storage | R2 (sonnet, adversarial) | §7: non-goal scoped; explicitly does not exclude FR-I6 presence checks | 2026-06-05 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-05

- **Reviewer**: claude-opus-4-8-1m (Claude Opus 4.8, 1M context)
- **Date**: 2026-06-05 (UTC)
- **Scope**: Full kickoff doc-set review (master + slices F/G/H/I per focus file); focus asks 1–5 answered below; code anchors spot-verified under `src/startd8/` and cap-dev-pipe (read-only).

##### Focus-file asks

**Ask 1 — Cross-doc consistency (master §5 vs slice FRs)**
- **Summary answer:** Partial — no MUST/MAY contradictions in Groups F/H/I, but three concrete drifts found.
- **Rationale:** (a) Manifest-count arithmetic diverges: §1 class F = contract + 5 cascade manifests, §6 says "contract + the 7 cascade manifests", FR-F5 says "all seven assembly manifests", while slice F §2 details only six inputs — `pages.yaml` (classed G in §3) is the unstated seventh. (b) FR-G1 normative strength: master §5 states marking unconditionally ("Lightweight front-matter status on content prose"); slice G FR-G1 makes the front-matter field **MAY** with defaults-by-origin. (c) Slice G FR-G2 already decides "prompts counted separately" while slice G OQ-2 still poses that as open.
- **Assumptions / conditions:** none.
- **Suggested improvements:** see R1-F-master-1 (count + pages.yaml dual role), R1-F-cnt-1 (FR-G2 vs OQ-2), R1-F-cnt-2 (FR-G1 strength alignment).

**Ask 2 — Ownership boundaries**
- **Summary answer:** Mostly clear; two cross-class FRs silently cross the delegation boundary, and "POLISH/preflight" is used interchangeably across two owners.
- **Rationale:** FR-X2 carries an explicit "delegated / ContextCore-owned" marker, but FR-X1 (report emitted by Stage 1 POLISH = `contextcore polish`, ContextCore-owned) and FR-X3 (gating at Stage 3 VALIDATE, cap-dev-pipe/ContextCore-owned) carry none, despite their mechanics living outside startd8. Slices FR-H5 and FR-I2 say "flagged at POLISH/preflight" — POLISH (ContextCore) and preflight (startd8 `plan_ingestion`) are different owners; an implementer cannot tell which side must raise the flag.
- **Assumptions / conditions:** the delegation split stated in FR-X2 (gather flow + schema: ContextCore/cap-dev-pipe; consumption + injection reach: startd8) is the governing rule.
- **Suggested improvements:** see R1-F-master-2.

**Ask 3 — Testability of the X-machinery (FR-X1–X5)**
- **Summary answer:** Partial — testable for the contract and content classes; under-specified elsewhere.
- **Rationale:** `authored|placeholder|absent` assignment rules are concrete only for `schema.prisma` (slice F §2.1) and content prose (slice G origin defaults). For `app.yaml`, `views.yaml`, `pipeline.env`, `question-answers.yaml` etc. no state-assignment rule exists; the FR-X1 sentinel list is open-ended ("scaffolded stubs" has no detection definition). FR-X4's score denominator ("declared") is undefined — unclear whether MAY-inputs (e.g. FR-G4 fixtures) inflate it. FR-X5 is testable via slice F's round-trip acceptance; FR-X2 is testable only as a delegation citation.
- **Assumptions / conditions:** acceptance tests are to be written against the FR-X5 inventory as ground truth.
- **Suggested improvements:** see R1-F-master-3 (FR-X4 spec), R1-F-asm-4 (FR-F2 stub rule), plus: add a per-class state-assignment table (one row per catalogued input: how each of the three states is assigned) to the FR-X5 template.

**Ask 4 — Unverified anchors (scaffold/views hash parity; explain-content.yaml)**
- **Summary answer:** Hash-parity claims **verified and hold**; the `explain-content.yaml` characterization is overstated.
- **Rationale:** Scaffold-owned files carry `# manifest-sha256:` hashing `app.yaml` (`scaffold_codegen/drift.py:18`, `renderers.py:37–40`); view-owned files carry a two-hash header `# schema-sha256:` + `# views-sha256:` (`view_codegen/renderers.py:33–34, 296–297`) — so FR-F1 can reuse drift-header hashes uniformly, though key names differ per generator (backend three-hash header vs `manifest-sha256` vs `views-sha256`), and views in-sync checking is byte-compare re-render (`view_codegen/drift.py`), not hash-compare — the hash is still present for provenance reuse. `explain-content.yaml` is explain-mode **educational display copy only** ("single source of truth for all explain-mode text", REQ-CDP-EDU-009; loaded with built-in fallback at `cap-dev-pipe/explain-pipeline.py:64, 241–258`) — it never influences generated artifacts. Also re-verified: precedence chain verbatim at `cap-dev-pipe/pipeline/config.py:3` (+ INT-010 exception); `micro_prime/` has zero `project_knowledge` refs; injection at `prime_contractor.py:4543–4601`; `ai_layer.py:42/:297–302` `_PROVENANCE_OMIT` as cited.
- **Assumptions / conditions:** cap-dev-pipe canonical source at `~/Documents/dev/cap-dev-pipe/` is the deployed version.
- **Suggested improvements:** see R1-F-asm-1 (resolve slice F OQ-2 + hash-key mapping), R1-F-bp-1 (reclassify explain-content.yaml).

**Ask 5 — Coverage completeness (missing kickoff input surfaces)**
- **Summary answer:** No missing sixth class; two uncatalogued inputs within existing classes.
- **Rationale:** (a) AI-pass **prompt files** are declared an input in slice G §2.4 (same temporal model as pages prose) but have **no row in the master §3 catalog**, breaking "Every kickoff input, mapped to its class". (b) Provider **credentials presence** (`ANTHROPIC_API_KEY` etc.) is a build-blocking user-provided kickoff input with no catalog row; a presence-only (never value) Group I row is compatible with the secrets non-goal.
- **Assumptions / conditions:** "build-driving" includes "build-blocking" preconditions.
- **Suggested improvements:** see R1-F-master-4, R1-F-master-5.

##### Executive summary

- The set is internally coherent at the FR level; the biggest defect class is **arithmetic/enumeration drift** (the "seven manifests" count) rather than semantic divergence.
- Two Group-X FRs (X1, X3) cross the ContextCore/cap-dev-pipe delegation boundary without the explicit marker FR-X2 has — the most likely source of ownership disputes at implementation time.
- The `authored|placeholder|absent` machinery is only test-ready for 2 of 5 classes; a per-class state-assignment table is the single highest-leverage addition.
- Both weak code anchors check out (scaffold + views hash parity verified in source); `explain-content.yaml` is misclassified as build-driving.
- Master §3's "every kickoff input" claim is currently false by its own slices (prompt files missing).
- FR-X4's provenance enum and FR-X1's status enum are used interchangeably in §8 acceptance without a defined mapping.

##### Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F-master-1 | Data | high | Reconcile the manifest count: enumerate the "seven assembly manifests" by name in FR-F5, fix §6's "contract + the 7 cascade manifests" (which implies 8 items vs §1's contract + 5), and state `pages.yaml`'s dual role explicitly (consumed by the cascade → counted in F's inventory; owned by Group G for content semantics) | §1, §6, and FR-F5 give three different counts; an implementer of FR-F5/FR-X5 cannot enumerate "all seven" from the set as written | §1 class table, §5 FR-F5, §6 row 1 | Cross-check: the named list in FR-F5 matches slice F §2 + the FR-X5 template rows exactly |
| R1-F-master-2 | Interfaces | high | Add delegation markers to FR-X1 and FR-X3 mirroring FR-X2's: report/gate **mechanics** are ContextCore/cap-dev-pipe-owned (POLISH, VALIDATE); startd8 owns the catalog, state semantics, and impact text. Also standardize "flagged at POLISH/preflight" (FR-H5, FR-I2) to name one owning surface per flag | FR-X2 is explicitly delegated but FR-X1/X3 silently require changes to `contextcore polish` / VALIDATE without saying who implements; "POLISH/preflight" spans two repos' code | §4 FR-X1, FR-X3; ripple note to slices H/I | Each FR names an owner per the FR-X2 split; no FR requires startd8 `src/` changes inside a ContextCore-owned stage without a delegation note |
| R1-F-master-3 | Data | medium | Tighten FR-X4: (a) define the mapping between the provenance enum (`authored\|supplemental\|config-default\|templated/inferred`) and the FR-X1 status enum (`authored\|placeholder\|absent`) — §8 shows `config-default` inside the FR-X1 report; (b) define the score denominator "declared" as the applicable FR-X5 inventory entries, stating whether MAY-inputs (FR-G4 fixtures) count | Two vocabularies appear in one report with no mapping; an undefined denominator makes `input_provisioning_score` unreproducible across implementations | §4 FR-X4 + §8 bullet 4 | Unit-testable: fixed inventory + provenance fixture yields one defined score; report renders both enums per the mapping table |
| R1-F-master-4 | Data | medium | Add a master §3 catalog row for AI-pass prompt files (class G, mechanism: referenced by path from `ai_passes.yaml`, detail: Content slice §2.4) | Slice G §2.4 declares prompt prose a kickoff input under FR-G1, but §3 claims to map "every kickoff input" and has no row — slice-to-master coverage break | §3 table, after the `seeds/*.seed.json` row | §3 rows ⊇ union of all slice §2 inventories (mechanical diff) |
| R1-F-master-5 | Security | medium | Catalog provider-credential **presence** (env: `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`/…) as a Group I kickoff input: presence-only check in the FR-X1 report (`authored` = set, `absent` = unset for the providers the routing knobs select); never the value | An unset key for the selected provider fails the run mid-flight — the exact "discovers mid-run" failure FR-I4 prevents for budget; presence-only preserves the secrets non-goal | §3 table + a Group I bullet in §5; detail in build-prefs slice §2 | Run with the lead-agent's provider key unset: FR-X1 report shows the credential row `absent` before any LLM call |

**Endorsements / Disagreements:** none possible — R1, no prior untriaged rounds in Appendix C.

#### Review Round R2 — claude-sonnet-4-6 — 2026-06-05

- **Reviewer**: claude-sonnet-4-6
- **Date**: 2026-06-05 00:00:00 UTC
- **Scope**: Second-pass review of master doc (cross-class requirements, FR-X1–X5); focus-ask answers where R1 can be extended or corrected; adversarial pass on implementability. Code-verified: `micro_prime/context.py`, `repair/convention.py`, `backend_codegen/crud_generator.py`.

##### Focus-file asks (R2 additions — concur with R1 on asks 1, 3, 4, 5 except where noted)

**Ask 1 — Cross-doc consistency**
- Concur with R1. Adding one divergence R1 did not flag: FR-H2's routing precondition "MUST NOT route convention-strict work" appears in the master §5 and slice H §3 FR-H2 without any normative requirement in the master §4 Group-X section. FR-X3 criticality matrix does not mention routing — so the re-routing precondition is Group-H-only with no cross-class hook, yet FR-X1 is asked to report "conventions absent → micro-prime-routed views at invention risk" (§4 example). There is no FR-X requirement that backs up that report text with a gate or action. See R2-F-master-1.

**Ask 2 — Ownership boundaries**
- Concur with R1. One additional gap: FR-X4 requires a per-class `input_provisioning_score` in the "run quality report" — but neither the master nor any slice specifies which component owns that report (kaizen-metrics.json is SDK prime_postmortem; onboarding-metadata.json is ContextCore; run-provenance.json is cap-dev-pipe). FR-X4's "run quality report" is an undefined artifact. See R2-F-master-2.

**Ask 3 — Testability of X-machinery**
- Concur with R1's finding on the denominator and state-assignment gaps. One additional gap: FR-X3 refers to "the observability slice FR-E1 matrix" gaining rows per class, but FR-E1 is in a separate doc. The master never states whether FR-X3 is testable in isolation (independently of the observability doc) or requires FR-E1 as a co-deployed prerequisite. See R2-F-master-3.

**Ask 4 — Unverified anchors**
- Concur with R1 on hash parity and explain-content.yaml. One correction to R1's scope note: R1 states "micro_prime has zero project_knowledge refs" as a supporting anchor, but `micro_prime/context.py:89` and `micro_prime/engine.py:2607` show micro_prime does receive `convention_guidance` — derived from `repair/convention.py:render_convention_guidance()`, which is a **hardcoded** Python-only house-style block (FastAPI/SQLModel/Jinja2 from `CANONICAL_LAYOUT`), not a user-declared manifest. The structural bypass for user-declared conventions (FR-H1) still exists; the RUN-028-specific Python idioms are now partially bridged. See R2-F-master-4 and slice H.

**Ask 5 — Coverage completeness**
- Concur with R1. No additional missing class found.

##### Executive summary

- FR-X4's "run quality report" artifact is undefined — no doc names the file, owner, or schema for the per-class `input_provisioning_score`. This is the single largest implementation blocker in the master.
- The micro_prime `convention_guidance` injection (existing) is hardcoded Python-only house style, not wired to FR-H1's proposed user manifest — the claimed FR-H2 "structural bypass closed" is overstated.
- FR-X3 routing precondition has no cross-class backing requirement; an implementer could satisfy the matrix (FR-X3) without ever implementing the routing guard (FR-H2).
- FR-I1's provenance-tier emission point is unresolved (OQ-2 equivalent for Group I) and the master's §4 FR-X4 + §5 FR-I1 have an unaddressed circular dependency: which component reads `pipeline/config.py`'s resolved values and writes them to the run quality report?

##### Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F-master-1 | Architecture | high | Add a cross-class Group-X requirement (FR-X6 or a note in FR-X3) that links the FR-X1 report's "conventions absent → invention risk" text to an actionable gate or routing precondition — or state explicitly that the report is advisory only for Group H. Without this, FR-X1 requires the report to name affected tiers (§4 example text) but no FR makes the routing precondition binding at the cross-class level | FR-H2's re-routing precondition is scoped to Group H only; FR-X1's example output promises more than any cross-class requirement can deliver; an FR-X1 implementer will omit the tier-naming or hardcode it without a binding cross-class hook | §4 FR-X1 (+ advisory/gate clarification) | FR-X1 report shows "micro-prime-routed views at invention risk" AND FR-H2's routing precondition fires consistently in the same run, or FR-X1 is marked advisory-only for this output |
| R2-F-master-2 | Data | high | Define the "run quality report" artifact that FR-X4 writes the `input_provisioning_score` to: name the file, owner, and schema location. Options: extend `kaizen-metrics.json` (SDK-owned, `prime_postmortem.py`); add to `run-provenance.json` (cap-dev-pipe); add a new `kickoff-report.json`. Without specifying the artifact, FR-X4 is unimplementable — every component that could own it (prime_postmortem, cap-dev-pipe, ContextCore) would implement it independently | FR-X4 says "the run quality report carries an `input_provisioning_score` per class" with no named artifact; the existing `kaizen-metrics.json` contains generation/security/query metrics only — no input provisioning section; no SDK path implements `input_provisioning_score` today | §4 FR-X4 | A strtd8 run produces a named artifact file containing `input_provisioning_score` keyed by class (F/G/H/I + A–E) with values in [0,1] |
| R2-F-master-3 | Validation | medium | State explicitly whether FR-X3's criticality matrix is independently testable or co-deployed with the observability slice's FR-E1. If co-deployed, add a note in §4 FR-X3 that "matrix rows for Groups F–I require the FR-E1 matrix document to be present as the base table" — so an implementer does not attempt to specify a standalone matrix. If independently testable, specify the table format and at least one concrete row for each of Groups F, G, H, I | FR-X3 says "gains rows per class" against "the observability slice FR-E1" without specifying whether FR-E1 is a prerequisite or a reference; an implementer testing FR-X3 in isolation has no base table to extend | §4 FR-X3 | An FR-X3 implementation test can be executed without opening the observability doc: either the extended table rows are defined here, or a note explicitly delegates to FR-E1 |
| R2-F-master-4 | Interfaces | medium | Correct the master's implicit claim that FR-H2's "structural bypass" for micro_prime is still open: `micro_prime/context.py` (FR-CAR-5) already injects `convention_guidance` via `render_convention_guidance()` for Python targets — but the injected text is hardcoded Python idiom (FastAPI/SQLModel from `CANONICAL_LAYOUT`), not driven by a user-declared FR-H1 manifest. State clearly in §5 FR-H2 that the existing Python injection partially closes the bypass for the Python house style only, and FR-H2's remaining requirement is to wire FR-H1 user-declared conventions into the same injection path | Omitting this distinction allows an implementer to mark FR-H2 satisfied by the existing `convention_guidance` injection (which works for Python idioms) without wiring the user-declared `semantic_conventions.yaml`, defeating the FR-H1 purpose | §5 FR-H2 | An FR-H2 acceptance test with a user-declared non-default framework shows that framework in the micro-prime prompt, not the hardcoded "FastAPI/SQLModel" text |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F-master-5 | Risks | high | FR-X2's delegation ("new classes ride the machinery by adding questions") is structurally untestable as written: `guidance.questions[]` and the manifest schema are ContextCore-owned; this doc cannot specify acceptance criteria for them. Add a testable startd8-side acceptance criterion: e.g. for each Group F–I input with a RESOLVE question, a pre-seeded `question-answers.yaml` entry surfaces it in the FR-X4 provenance record as `supplemental` — verifiable entirely within cap-dev-pipe + startd8 scope | FR-X2 is delegated to ContextCore/cap-dev-pipe, so any acceptance test for it hits an ownership boundary. The kickoff requirements need an observable, startd8-owned proxy check; otherwise FR-X2 "passes" whenever ContextCore is present, regardless of actual coverage | §4 FR-X2 + §8 acceptance | A strtd8 run with a pre-seeded `question-answers.yaml` entry for a Group H convention question shows that value in the provenance record as `supplemental`, not `config-default` |
| R2-F-master-6 | Security | low | The §7 non-goal "Does not manage secrets storage — receiver targets etc. use env/secret indirection" may silently exempt provider credential presence from FR-X1 (R1 proposed adding credential presence as a Group I input, R1-F-master-5). Ensure the non-goal is scoped to "does not store secret values" and does not accidentally exclude a presence-only `authored|absent` check, which carries zero secret data | If an implementer reads §7 and §3 together, they may exclude the credential-presence row from FR-X1 entirely. The non-goal should be narrowed to "value storage" only | §7 (scope the non-goal) | The FR-X1 report includes a credential presence row; its value is `authored` or `absent`, never the key string |

**Endorsements:**
- R1-F-master-2: concur — FR-X1 and FR-X3 need delegation markers matching FR-X2's clarity; the "POLISH/preflight" ambiguity is the most likely ownership dispute.
- R1-F-master-3: concur — the provenance enum / FR-X1 status enum mapping gap is real and blocks FR-X4 implementation.
- R1-F-master-5: concur — credential presence is a build-blocking kickoff input that belongs in the catalog.
- R1-F-bp-2: concur — provenance-tier-based (not value-based) determination of `authored` vs `config-default` is essential for FR-I4 correctness.
