# Proven Exemplar Pipeline — Requirements

**Version:** 1.0.0
**Created:** 2026-03-18
**Status:** Draft
**Depends on:** `KAIZEN_PRIME_REQUIREMENTS.md` (REQ-KZ-300–601), `PRIME_EXECUTION_MODES_REQUIREMENTS.md` (REQ-PEM-000–012), `TODO_COMPLETION_WORKFLOW_REQUIREMENTS.md` (REQ-TCW-000–403)
**Source:** Cross-run analysis of online-boutique runs 047–070 (20 runs, 3 languages, 93 features, 49 PASS); observation that pipeline preserves complete input→output→validation tuples for every successful feature but never feeds them forward
**Scope:** Cross-system — ContextCore (exemplar registration in export), StartD8 SDK (exemplar consumption in spec/draft prompts, template extraction)

---

## Vision

**Every successful run makes the next run cheaper, faster, and more reliable.**

The Capability Delivery Pipeline already preserves everything needed to learn from success: the spec prompt that described what to build, the code that was generated, the postmortem that validated it, and the metadata connecting all three. But this knowledge dies at the end of each run. The next run for a structurally similar task starts from zero, paying full LLM cost to rediscover patterns that the pipeline has already proven correct.

This document describes a system that accumulates proven-correct (spec, code, validation) tuples into a searchable exemplar registry, injects relevant exemplars into generation prompts, and progressively extracts deterministic patterns into templates — reducing LLM dependency with each successful run.

The trajectory is: **exemplars → templates → deterministic assembly.**

- **Exemplars** show the LLM what correct output looks like for this pipeline's specific format. This is the immediate value — cheaper models succeed more often because they have a concrete target.
- **Templates** emerge when the pipeline detects that certain outputs are invariant across exemplars sharing a configuration. The invariant parts become templates; the variable parts become LLM-filled slots.
- **Deterministic assembly** is the end state: for well-understood configurations, the pipeline assembles output from templates and validated patterns without LLM calls at all. The Dockerfile already works this way ($0.00 cost, 1.00 score). The goal is to expand that to more file types.

---

## Problem Statement

### What the pipeline already preserves

For each successful feature in each run with kaizen enabled:

| Artifact | Location | What it captures |
|----------|----------|-----------------|
| Spec prompt | `kaizen-prompts/standalone/{ID}/spec_user_prompt.md` | The full context + instructions that described the task |
| Draft prompt | `kaizen-prompts/standalone/{ID}/draft_user_prompt.md` | The drafter's instructions including the spec output |
| Generated code | `kaizen-prompts/standalone/{ID}/draft_src_{file}_{lang}_response.md` | The actual code produced |
| Spec artifact | `generated/.artifacts/{Name}-spec.md` | The 8-section spec (requirements, approach, structure, acceptance criteria) |
| Draft artifact | `generated/.artifacts/{Name}-draft-{N}.md` | Draft iterations |
| Review artifact | `generated/.artifacts/{Name}-review-{N}.md` | Review feedback |
| Integration artifact | `generated/.artifacts/{Name}-integration.md` | Final merged code |
| Postmortem | `prime-postmortem-report.json` | Per-feature scores: requirement_score, disk_quality_score, assembly_delta, semantic_error_count |
| Metadata | `kaizen-prompts/standalone/{ID}/metadata.json` | Feature ID, target files, context keys, agent specs, timestamps |
| Seed task | `prime-context-seed.json` | Forward manifest, implementation contracts, element specs |
| Cost | `prime-result.json` | Per-feature cost breakdown (spec LLM vs drafter LLM) |

### What the pipeline doesn't do with it

None of this knowledge feeds forward into subsequent runs. Each new feature starts with:
1. A spec prompt built from the seed task + context (no exemplars)
2. A drafter prompt built from the spec output (no prior successful drafts)
3. Full LLM inference cost for patterns the pipeline has already validated

### The cost of not learning

From the kaizen correlation data (93 data points, 49 PASS):
- `draft_word_count` is the strongest success predictor (ρ=+0.273) — but still weak
- `spec_word_count` is slightly *negatively* correlated (ρ=-0.196) — longer specs don't help
- The pipeline has no mechanism to show models *what correct output looks like* for its specific format

This matters most for the cheap-model strategy. Haiku and Ollama models struggle not because they can't write code, but because they can't infer what the pipeline expects from a spec prompt alone. A proven exemplar *is* the inference, pre-computed. It turns "figure out what I want" into "here's exactly what success looks like — do that for this task."

---

## Core Concepts

### Proven Exemplar

A **proven exemplar** is a (configuration, spec, code, validation) tuple from a successful run:

- **Configuration:** The structural fingerprint of the task — language, file type, service transport, archetype (gRPC server, Dockerfile, build config, unit test, etc.)
- **Spec:** The spec prompt or artifact that described the task
- **Code:** The generated code that scored 1.00 with full contract compliance
- **Validation:** The postmortem scores proving correctness (requirement_score=1.0, disk_quality_score=1.0, assembly_delta=0.0, semantic_error_count=0)

An exemplar is not just "good code." It's code that *this pipeline, with this validation system, proved correct.* That distinction matters — it means the exemplar satisfies the exact same checks that the new code will face.

### Configuration Fingerprint

Tasks are grouped by structural similarity, not surface features. A fingerprint includes:

| Dimension | Examples | Why it matters |
|-----------|----------|---------------|
| Language | `java`, `go`, `python`, `nodejs`, `csharp` | SDK patterns, import conventions, build tools differ |
| File type | `source`, `test`, `dockerfile`, `build_config`, `config_file` | Structure expectations differ fundamentally |
| Transport | `grpc`, `http`, `none` | Server setup, interceptor wiring, health check patterns |
| Archetype | `grpc_server`, `grpc_client`, `unit_test`, `multi_stage_dockerfile`, `gradle_build`, `go_mod` | The structural pattern of the file |

Two tasks with the same fingerprint should produce structurally similar output. `run-067:PI-001` (Go gRPC server) and `run-069:PI-001` (Java gRPC server) share `(*, source, grpc, grpc_server)` but differ on language. A future Go gRPC server task would match run-067's exemplar exactly.

### Exemplar Maturity

Exemplars progress through maturity levels based on validation evidence:

| Level | Name | Criteria | Use |
|-------|------|----------|-----|
| 0 | **Candidate** | Generated code exists, postmortem ran | Not used — may have failed |
| 1 | **Validated** | score=1.00, verdict=PASS, disk_quality_score=1.0 | Available as exemplar in prompts |
| 2 | **Confirmed** | Validated in 2+ independent runs with same fingerprint | Higher injection priority |
| 3 | **Invariant** | 3+ confirmed exemplars share >80% identical structure | Template extraction candidate |
| 4 | **Template** | Invariant parts extracted as deterministic template | No LLM needed for invariant portions |

---

## Requirements

### Layer 0: Exemplar Registry (REQ-PEP-000–003)

#### REQ-PEP-000: Exemplar Extraction from Successful Runs

**Priority:** P1
**Status:** Planned
**Source files:** New module: `src/startd8/contractors/exemplar_registry.py`

After each successful Prime Contractor run, the pipeline MUST extract proven exemplars from features that scored 1.00.

**Acceptance criteria:**
1. For each feature with `verdict: "PASS"` and `requirement_score >= 1.0` and `disk_quality_score >= 1.0`:
   - Extract the configuration fingerprint (language, file type, transport, archetype)
   - Capture: spec artifact path, generated code path, draft artifact path, postmortem scores, cost, agent specs used
   - Record the seed task's forward manifest entry (element specs, implementation contract) as the *input specification*
2. Extraction runs automatically as part of the postmortem phase (after `prime-postmortem-report.json` is written)
3. Each exemplar is assigned a unique ID: `ex-{fingerprint_hash}-{run_id}-{feature_id}`
4. Exemplar maturity starts at level 1 (Validated)

#### REQ-PEP-001: Exemplar Registry Persistence

**Priority:** P1
**Status:** Planned

The exemplar registry MUST be persisted as a project-level artifact that accumulates across runs.

**Acceptance criteria:**
1. Registry stored at `{project_output_dir}/exemplar-registry.json`
2. Schema includes: `schema_version`, `project_id`, `last_updated`, `exemplars: List[ExemplarEntry]`
3. Each `ExemplarEntry` includes:
   - `id`: Stable unique ID
   - `fingerprint`: `{language, file_type, transport, archetype}`
   - `maturity`: 0–4 integer
   - `source_run_id`, `source_feature_id`
   - `spec_artifact_path`: Relative path to spec .md
   - `code_artifact_path`: Relative path to generated code
   - `draft_artifact_path`: Relative path to draft .md
   - `seed_task_digest`: Hash of the seed task's implementation contract (for similarity matching)
   - `scores`: `{requirement_score, disk_quality_score, assembly_delta, semantic_error_count, cost_usd}`
   - `agent_specs`: `{lead, drafter}` (which models produced this)
   - `code_summary`: First 50 lines of generated code (for quick preview without loading full file)
   - `timestamp`: When the exemplar was extracted
4. Registry size is bounded: maximum 500 exemplars, oldest low-maturity entries evicted first
5. Registry is included in the kaizen index for cross-project discoverability

#### REQ-PEP-002: Configuration Fingerprint Computation

**Priority:** P1
**Status:** Planned

Each task MUST have a computable configuration fingerprint for exemplar matching.

**Acceptance criteria:**
1. **Language:** Derived from target file extension via `LanguageRegistry.resolve_language()` or seed task `language` field
2. **File type:** Classified from filename patterns:
   - `source` — `.java`, `.go`, `.py`, `.js`, `.ts`, `.cs` (not test files)
   - `test` — files matching `*_test.go`, `*Test.java`, `test_*.py`, `*.test.js`
   - `dockerfile` — `Dockerfile`, `Dockerfile.*`
   - `build_config` — `build.gradle`, `build.gradle.kts`, `go.mod`, `package.json`, `pyproject.toml`, `*.csproj`
   - `config_file` — `.xml`, `.yaml`, `.yml`, `.json`, `.properties`, `.gradle` (non-build)
3. **Transport:** Inferred from seed task metadata (`service_metadata.transport_protocol`), or from imports in generated code (presence of `grpc` imports → `grpc`; presence of `http`/`net/http` → `http`; otherwise `none`)
4. **Archetype:** Derived from a combination of filename, element specs, and content patterns:
   - `grpc_server` — source file containing gRPC server setup + service registration
   - `grpc_client` — source file containing gRPC channel/stub creation
   - `unit_test` — test file
   - `multi_stage_dockerfile` — Dockerfile with 2+ FROM stages
   - `gradle_build` / `go_mod` / `package_json` — build configuration by type
   - `logging_config` — XML/YAML logging configuration
   - `properties_file` — key=value configuration
   - `settings_file` — single-line project settings (e.g., `settings.gradle`)
5. Fingerprint is a 4-tuple serialized as `"{language}:{file_type}:{transport}:{archetype}"`

#### REQ-PEP-003: Maturity Promotion

**Priority:** P2
**Status:** Planned

Exemplar maturity MUST be automatically promoted based on cross-run evidence.

**Acceptance criteria:**
1. When a new exemplar is extracted with the same fingerprint as an existing level-1 exemplar from a different run, both are promoted to level 2 (Confirmed)
2. When 3+ level-2 exemplars exist for the same fingerprint, the pipeline computes structural similarity (shared imports, shared function signatures, shared code blocks). If >80% of lines are shared across all exemplars, all are promoted to level 3 (Invariant)
3. Maturity promotion runs as part of exemplar extraction (REQ-PEP-000)
4. Maturity changes are logged in kaizen metrics: `exemplar_promotions: [{id, old_level, new_level}]`

---

### Layer 1: Exemplar Injection into Prompts (REQ-PEP-100–103)

#### REQ-PEP-100: Exemplar Selection for Task

**Priority:** P1
**Status:** Planned
**Depends on:** REQ-PEP-002

Before spec prompt construction, the pipeline MUST select the best-matching exemplar for the current task.

**Acceptance criteria:**
1. Compute the current task's configuration fingerprint
2. Search the exemplar registry for entries with matching fingerprint (exact match on all 4 dimensions)
3. If no exact match, fall back to partial match: same (language, file_type, archetype) with any transport
4. If multiple matches, rank by: maturity level (descending) → disk_quality_score (descending) → cost_usd (ascending, prefer cheaper exemplars that still scored perfectly) → timestamp (most recent)
5. Select the top-ranked exemplar. If no match exists, proceed without exemplar (graceful degradation).
6. Record the selection in task metadata: `exemplar_id`, `exemplar_fingerprint`, `match_type` (`exact` | `partial` | `none`)

#### REQ-PEP-101: Spec Prompt Exemplar Injection

**Priority:** P1
**Status:** Planned
**Depends on:** REQ-PEP-100
**Source files:** `src/startd8/implementation_engine/spec_builder.py`

When an exemplar is selected, it MUST be injected into the spec prompt as a P1-priority section.

**Acceptance criteria:**
1. Injection point: the existing `build_spec_prompt()` function's prioritized section list, at P1 priority (same level as kaizen hints)
2. Section format:
   ```markdown
   ## Verified Reference (from {run_id}, score: {score})

   The following implementation was generated by this pipeline for a structurally
   similar task ({fingerprint}) and scored {score} with full contract compliance.
   Use the same patterns, import structure, and architectural approach.

   ### Spec that produced it:
   [first 80 lines of spec artifact, or full spec if under 80 lines]

   ### Code that was validated:
   [first 100 lines of generated code, or full code if under 100 lines]
   ```
3. Budget handling: exemplar section participates in `enforce_prompt_budget()`. If budget is tight, the code excerpt is truncated before the spec excerpt (the spec is more valuable as a pattern guide).
4. If no exemplar is selected, no section is injected (no empty placeholder).

#### REQ-PEP-102: Draft Prompt Exemplar Injection

**Priority:** P1
**Status:** Planned
**Depends on:** REQ-PEP-100
**Source files:** `src/startd8/implementation_engine/drafter.py`

When an exemplar is selected, the drafter prompt SHOULD include the exemplar's generated code as a reference.

**Acceptance criteria:**
1. Injection point: `build_supplementary_sections()` in `drafter.py`, at P1 priority
2. Section format:
   ```markdown
   ## Verified Reference Implementation

   This code scored 1.00 in a prior run for a {fingerprint} task.
   Match its structure, import ordering, and patterns.

   ```{language}
   [full generated code from exemplar]
   ```
   ```
3. Budget handling: if the exemplar code would exceed the draft budget, truncate to the first N lines that fit within `TOTAL_DRAFT_BUDGET_TOKENS`
4. The exemplar is injected *in addition to* the spec output, not replacing it

#### REQ-PEP-103: Exemplar Impact Tracking

**Priority:** P2
**Status:** Planned

The pipeline MUST track whether exemplar injection improved outcomes.

**Acceptance criteria:**
1. Each feature's postmortem records: `exemplar_used` (bool), `exemplar_id` (if used), `exemplar_fingerprint`, `match_type`
2. Kaizen correlation data includes `exemplar_used` as a feature alongside `spec_word_count`, `draft_word_count`, etc.
3. After 20+ runs with exemplar data, the correlation analysis can answer: "Do tasks with exemplars succeed more often than tasks without?"
4. If exemplar injection shows negative or neutral correlation after 50+ data points, the system should log a warning for human review

---

### Layer 2: Template Extraction (REQ-PEP-200–202)

#### REQ-PEP-200: Invariant Detection

**Priority:** P2
**Status:** Planned
**Depends on:** REQ-PEP-003

When 3+ exemplars reach maturity level 3 (Invariant) for the same fingerprint, the pipeline MUST identify the invariant and variable portions of the code.

**Acceptance criteria:**
1. Align the code from all level-3 exemplars using a line-level diff algorithm
2. Classify each line as:
   - **Invariant:** Identical across all exemplars (e.g., import blocks, boilerplate, framework setup)
   - **Variable-bounded:** Different across exemplars but follows a pattern (e.g., service name, method names, port numbers — parameterizable)
   - **Variable-free:** Different across exemplars with no discernible pattern (e.g., business logic, ad catalog data)
3. Compute `invariant_ratio` = invariant lines / total lines
4. Record the analysis in the exemplar registry: `invariant_analysis: {invariant_ratio, invariant_lines: List[int], variable_bounded_lines: List[int], variable_free_lines: List[int]}`

#### REQ-PEP-201: Template Extraction

**Priority:** P2
**Status:** Planned
**Depends on:** REQ-PEP-200

When `invariant_ratio >= 0.6` for a fingerprint, the pipeline SHOULD extract a template.

**Acceptance criteria:**
1. Invariant lines become literal template content
2. Variable-bounded lines become named slots: `{{service_name}}`, `{{port}}`, `{{grpc_methods}}`, derived from the seed task's forward manifest fields
3. Variable-free lines become a `{{GENERATE}}` marker indicating LLM generation is needed for this section only
4. Template stored at `{project_output_dir}/templates/{fingerprint}.tmpl` with metadata: source exemplar IDs, invariant_ratio, slot definitions
5. Template maturity: a template is `draft` until it produces a 1.00-scoring output, then `validated`

#### REQ-PEP-202: Template-Assisted Generation

**Priority:** P3
**Status:** Planned
**Depends on:** REQ-PEP-201

When a validated template exists for a task's fingerprint, the pipeline SHOULD use template-assisted generation.

**Acceptance criteria:**
1. Fill invariant portions from the template (zero LLM cost)
2. Fill variable-bounded slots from seed task metadata (zero LLM cost)
3. Generate only `{{GENERATE}}` sections via LLM (reduced cost proportional to variable-free ratio)
4. The drafter prompt includes the partially-filled template and instructs: "Complete the marked sections. Do not modify the template portions."
5. Post-generation validation: verify that invariant lines were not modified (template compliance check)
6. Track cost savings: `template_coverage_ratio` = (invariant + bounded) / total lines; `llm_cost_savings` = baseline cost × template_coverage_ratio

---

### Layer 3: Cross-Project and Cross-Language Accumulation (REQ-PEP-300–301)

#### REQ-PEP-300: Cross-Project Exemplar Sharing

**Priority:** P3
**Status:** Planned

Exemplars SHOULD be shareable across projects that use the same language and service patterns.

**Acceptance criteria:**
1. A global exemplar registry at `~/.contextcore/exemplar-registry.json` aggregates entries from all project registries
2. When a project has no local exemplar for a fingerprint, the global registry is consulted as fallback
3. Cross-project exemplars are injected with a disclaimer: "This reference is from a different project ({project_id}) but shares the same structural pattern."
4. Cross-project exemplars are never promoted beyond level 2 (Confirmed) in the local registry — they must be locally validated to reach level 3

#### REQ-PEP-301: Cross-Language Pattern Recognition

**Priority:** P3
**Status:** Planned

The pipeline SHOULD recognize that certain archetypes share structural patterns across languages.

**Acceptance criteria:**
1. `multi_stage_dockerfile` is language-independent at the structural level (builder + runtime stages). A Java Dockerfile exemplar can inform a Go Dockerfile prompt with language-specific substitutions.
2. `unit_test` shares structural patterns across languages (setup, act, assert). A Go test exemplar's *structure* (not syntax) can inform a Java test prompt.
3. Cross-language exemplar injection uses an abstracted form: structural description rather than literal code
4. This is explicitly P3 — only pursue after single-language exemplar injection is validated

---

## The Accumulation Flywheel

```
Run N: Generate → Validate → Extract Exemplars
                                    │
                                    ▼
                          Exemplar Registry
                          ├── java:source:grpc:grpc_server (2 exemplars, level 2)
                          ├── go:source:grpc:grpc_server (1 exemplar, level 1)
                          ├── java:dockerfile:none:multi_stage_dockerfile (2 exemplars, level 2)
                          ├── java:build_config:none:gradle_build (2 exemplars, level 2)
                          └── go:build_config:none:go_mod (1 exemplar, level 1)
                                    │
                                    ▼
Run N+1: Select Exemplar → Inject into Spec/Draft → Generate → Validate
                                                                    │
                                    ┌───────────────────────────────┘
                                    ▼
                          Exemplar Registry (updated)
                          ├── java:source:grpc:grpc_server (3 exemplars, level 3 — INVARIANT)
                          │   └── invariant_ratio: 0.72 → Template extraction candidate
                          ├── go:source:grpc:grpc_server (2 exemplars, level 2)
                          └── ...
                                    │
                                    ▼
Run N+2: Template-Assisted Generation
         ├── Invariant portions: $0.00 (from template)
         ├── Bounded slots: $0.00 (from seed metadata)
         └── Variable sections: $0.05 (LLM fills only the unique parts)
         Total: $0.05 vs $0.33 baseline (85% cost reduction)
                                    │
                                    ▼
                          More exemplars → More templates → More deterministic assembly
                          Lower cost → Can afford more runs → More exemplars
                          ════════════════════════════════════════════════════
                                    THE FLYWHEEL TURNS
```

---

## Connection to Cheap-Model Strategy

The exemplar pipeline directly enables the cheap-model strategy documented in `project_cheap_model_strategy.md`:

| Without exemplars | With exemplars |
|-------------------|----------------|
| Haiku sees a spec prompt and must infer what correct output looks like | Haiku sees the spec prompt AND a verified-correct example of what the pipeline expects |
| Ollama generates from patterns learned during pretraining (generic) | Ollama generates from patterns validated by this pipeline (specific) |
| 67.1% pass rate (baseline-v4, from eval harness) | Target: 80%+ pass rate with exemplar injection |
| Cost savings come from using cheaper models (quality tradeoff) | Cost savings come from needing less LLM inference (no quality tradeoff) |

The exemplar isn't just a prompt engineering trick. It's a **knowledge transfer mechanism** from the pipeline's validation system to the generation system. The postmortem *knows* what correct output looks like. The exemplar pipeline makes that knowledge available at generation time.

---

## Connection to Deterministic Observability (REQ-TCW)

The exemplar pipeline amplifies the instrumentation contract work:

1. **First run:** Pipeline generates `initStats()` from the instrumentation contract. Postmortem validates it scores 1.00.
2. **Second run:** The validated `initStats()` implementation becomes an exemplar with fingerprint `java:source:grpc:grpc_server`. The next Java gRPC service gets this exemplar in its spec prompt.
3. **Third+ runs:** If the `initStats()` implementation is invariant across exemplars (same OTel SDK setup, same exporter config, same interceptor wiring), it becomes a template. Future services get deterministic OTel instrumentation at $0.00.

The instrumentation contract (REQ-TCW) tells the pipeline *what* to instrument. The exemplar pipeline (REQ-PEP) teaches the pipeline *how* to instrument it — and eventually makes the "how" deterministic.

---

## Phasing

### Phase 1: Registry + Extraction (REQ-PEP-000–003)

**Scope:** Extract exemplars from successful runs, persist in registry, compute fingerprints, auto-promote maturity.
**Prerequisite for:** All subsequent phases.
**Estimated effort:** Medium (new module + postmortem integration + fingerprint logic).
**Can start immediately:** Yes — runs retroactively on existing kaizen prompt archives.

### Phase 2: Prompt Injection (REQ-PEP-100–103)

**Scope:** Select best exemplar per task, inject into spec and draft prompts, track impact.
**Prerequisite:** Phase 1 complete with 10+ exemplars accumulated.
**Estimated effort:** Small-Medium (spec_builder.py + drafter.py integration at existing injection points).
**Validation:** A/B comparison — run same tasks with and without exemplar injection, compare scores and costs.

### Phase 3: Template Extraction (REQ-PEP-200–202)

**Scope:** Detect invariant patterns, extract templates, template-assisted generation.
**Prerequisite:** Phase 2 validated + 3+ exemplars per fingerprint for at least 2 fingerprints.
**Estimated effort:** Medium (diff algorithm + template engine + partial generation).
**Validation:** Template-generated output must score >= non-template output on same tasks.

### Phase 4: Cross-Project + Cross-Language (REQ-PEP-300–301)

**Scope:** Global registry, cross-project sharing, cross-language structural patterns.
**Prerequisite:** Phase 2 validated across 2+ projects.
**Estimated effort:** Small (registry aggregation) to Medium (cross-language abstraction).

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Exemplar overfitting — model copies exemplar too literally, ignores task-specific differences | Medium | High | Exemplar injection includes explicit instruction: "Use the same patterns and structure, but implement the current task's specific requirements." Postmortem catches contract violations. |
| Stale exemplars — registry accumulates exemplars from early runs with lower-quality pipeline versions | Low | Medium | Registry eviction policy (REQ-PEP-001 criterion 4); maturity promotion requires recent validation |
| Fingerprint granularity — too coarse (false matches) or too fine (no matches) | Medium | Medium | Start with 4-dimension fingerprint; if match rate is <30%, relax archetype dimension; if false match rate is >10%, add sub-archetype |
| Template rigidity — extracted templates don't accommodate legitimate structural variation | Medium | Medium | Template compliance check is advisory, not blocking; if template-assisted generation scores lower, fall back to full generation |
| Budget pressure — exemplar injection consumes prompt tokens that could be used for task context | Low | Low | Exemplar participates in `enforce_prompt_budget()`; task-specific context (P0) always takes priority over exemplar (P1) |
