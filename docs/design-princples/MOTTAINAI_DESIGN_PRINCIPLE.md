# Mottainai Design Principle

Purpose: establish a cross-cutting design principle for the ContextCore + startd8-sdk pipeline — an aversion to wasteful regeneration of artifacts that earlier pipeline stages already produced.

This document is intentionally living guidance. Update it as new reuse opportunities are identified.

---

## The Principle

**Mottainai** (もったいない) — an expression of regret at the full value of something not being put to good use. In contemporary Japanese, mottainai is most commonly used to indicate that something is being discarded needlessly, or to express regret at such a fact.

Applied to the pipeline: **every artifact produced by an earlier stage carries invested computation, context, and deterministic correctness. Discarding it — or regenerating it via an expensive LLM call — when it could be passed forward is mottainai.**

---

## Why This Matters

The 7-step pipeline (init → export → Gate 1 → plan-ingestion → Gate 2 → contractor → Gate 3) produces rich artifacts at each stage. ContextCore export produces deterministic derivation rules, pre-resolved parameters, dependency graphs, and output contracts. Plan-ingestion produces architectural reviews, calibration hints, and structured task decompositions. These artifacts represent:

1. **Deterministic correctness** — ContextCore computes business-to-parameter mappings (e.g., "criticality high → alert severity P2") through explicit derivation rules. An LLM re-deriving the same mapping may produce a different answer.
2. **Invested LLM cost** — plan-ingestion's REFINE phase runs a full architectural review. If that review's suggestions never reach the DESIGN phase, the REFINE LLM call was wasted.
3. **Provenance integrity** — when the DESIGN phase independently re-derives parameters, the provenance chain breaks. The final artifact's parameter values can no longer be traced back to the export's deterministic computation.

---

## The Inventory Problem

The pipeline lacks a single artifact that answers: **"what has already been produced, and where is it?"** Each stage writes its outputs to disk, but downstream stages must know what exists, where it lives, and whether it is still fresh. Without an inventory:

- Downstream stages cannot discover reusable assets.
- Stale artifacts cannot be distinguished from fresh ones.
- The cost of regeneration is invisible — nobody knows what was wasted.

The `run-provenance.json` artifact (produced by export) already tracks input/output file fingerprints. The [Pipeline Artifact Inventory Requirements](./PIPELINE_ARTIFACT_INVENTORY_REQUIREMENTS.md) document extends this into a typed inventory that each pipeline stage can contribute to and consume from.

---

## Current Violations (Baseline)

The following are known mottainai violations as of this writing. Each represents an artifact produced by an earlier stage that a later stage either ignores or regenerates from scratch.

### Gap 1: `derivation_rules` — Export → DESIGN

ContextCore export computes deterministic business-to-parameter derivation rules (e.g., `spec.business.criticality` → alert severity P2). These rules are written to `onboarding-metadata.json` but never reach the artisan DESIGN phase. The DESIGN LLM independently re-derives the same mappings via inference.

**Waste**: Redundant LLM inference for a deterministic computation. Quality risk from inconsistent derivation.

### Gap 2: `resolved_artifact_parameters` — Export → DESIGN / IMPLEMENT

ContextCore export pre-resolves parameter values per artifact (e.g., `alertSeverity: P2`, `availabilityThreshold: 99.9%`). These concrete values are written to `onboarding-metadata.json` but never extracted into the seed or injected into DESIGN/IMPLEMENT prompts. The LLM must re-resolve them.

**Waste**: Redundant LLM parameter resolution. The values exist — they just are not forwarded.

### Gap 3: `expected_output_contracts` — Export → DESIGN / IMPLEMENT / TEST

ContextCore export produces per-artifact-type output contracts with `expected_depth`, `max_lines`, `max_tokens`, `completeness_markers`, and `red_flag` warnings. These are never consumed by any downstream stage.

**Waste**: The DESIGN phase uses LOC-based heuristics to guess depth tiers that the export already computed per artifact type. The TEST phase validates artifacts without knowing what completeness markers to check.

### Gap 4: `artifact_dependency_graph` — Export → Plan-Ingestion / IMPLEMENT

ContextCore export produces a deterministic artifact dependency graph (e.g., notification policy depends on prometheus rules). Plan-ingestion ignores this and uses an LLM to infer task dependencies.

**Waste**: Redundant LLM dependency inference for a deterministic graph.

### Gap 5: REFINE Suggestions — Plan-Ingestion → DESIGN

Plan-ingestion's REFINE phase runs an architectural review that produces structured suggestions (area, severity, rationale, validation approach). These are written into the plan document's Appendix C but never extracted into the seed. The artisan DESIGN phase never reads the plan document.

**Waste**: The entire REFINE LLM call produces output that does not reach DESIGN. The DESIGN LLM regenerates architectural decisions from scratch.

### Gap 6: `design_calibration_hints` — Export → Plan-Ingestion

ContextCore export produces per-artifact-type calibration hints (e.g., "dashboards should be comprehensive"). Plan-ingestion ignores these and computes its own depth tiers from LOC estimates, which are less domain-aware.

**Waste**: Artifact-type-aware calibration is overridden by a blunt LOC heuristic.

### Gap 7: `open_questions` — Export → DESIGN

ContextCore export surfaces unresolved questions from the manifest's `guidance.questions`. These never reach the DESIGN prompt.

**Waste**: DESIGN decisions are made without awareness of flagged uncertainties.

### Gap 8: TRANSFORM Plan Document — Plan-Ingestion → DESIGN

Plan-ingestion's TRANSFORM phase produces a structured plan document with architecture, risk register, and verification strategy sections. The artisan DESIGN phase never reads this document — it builds FeatureContext only from PARSE-level seed data.

**Waste**: Architecture and risk analysis regenerated from scratch.

---

## Prime Contractor Audit (2026-02-17)

The prime route was wired as a symmetric consumer of plan-ingestion output (`prime-context-seed.json` → `run_prime_workflow.py` → `PrimeContractorWorkflow`). An audit of the implementation against the mottainai principle identified the following violations. Gaps 1–8 above are artisan-focused; Gaps 9–14 below are prime-specific.

### Gap 9: Seed `_enrichment` Data Discarded at Queue Boundary — Plan-Ingestion → Prime

`DomainPreflightWorkflow` enriches the seed with per-task `_enrichment` blocks (domain classification, prompt constraints, validation rules). `FeatureQueue.add_features_from_seed()` extracts only `task_id`, `title`, `description`, `target_files`, and `dependencies` — the `_enrichment` block is silently dropped. `PrimeContractorWorkflow` then re-computes enrichment at runtime via `DomainChecklist._get_domain_enrichment()`, which performs the same domain classification a second time.

**Waste**: Redundant domain classification. The enrichment was already computed and written to the seed; the prime workflow re-derives it because `FeatureSpec` has no field for it.

**Fix**: Add an optional `metadata: Dict[str, Any]` field to `FeatureSpec`. Have `add_features_from_seed()` forward `_enrichment` into metadata. Have `_generate_code()` check `feature.metadata.get("_enrichment")` before falling back to `DomainChecklist`.

### Gap 10: `onboarding` Metadata Not Injected into Code Generation Context

The prime seed carries `onboarding` data with `derivation_rules`, `resolved_artifact_parameters`, `expected_output_contracts`, and `semantic_conventions`. The `PrimeContractorWorkflow._generate_code()` method builds `gen_context` with only `feature_name`, `target_file`, and optionally `domain_constraints` — none of the onboarding fields are forwarded to the `LeadContractorCodeGenerator`.

**Waste**: The LLM must infer parameter values, derivation logic, and output structure from scratch. These were deterministically computed by ContextCore export and are sitting in the seed file.

**Fix**: In `run_prime_workflow.py`, load the seed's `onboarding` and `artifacts` sections. Forward relevant fields (`derivation_rules`, `resolved_artifact_parameters`) into the workflow or code generator context so they reach the prompt.

### Gap 11: No Architectural Context for Prime Route

Plan-ingestion computes `architectural_context` (project goals, shared modules, import conventions, dependency clusters) for the artisan route but sets it to `None` for the prime route. The prime `LeadContractorCodeGenerator` therefore has no awareness of cross-feature architectural patterns.

**Waste**: Each prime feature is generated in isolation without knowledge of shared modules, import conventions, or project goals. Features touching the same files may produce inconsistent patterns.

**Mitigation**: The prime workflow is designed for simpler projects (complexity ≤ 40), where cross-feature coordination is less critical. However, even for simple projects, forwarding `plan.goals` and `plan.mentioned_files` would provide cheap context at no LLM cost.

**Fix**: Compute a lightweight architectural summary (goals + mentioned files) for prime seeds. No LLM cost — this is purely deterministic extraction from the parsed plan.

### Gap 12: No Design Calibration for Prime Route

The artisan seed includes `design_calibration` (per-task depth tiers from `SizeEstimator`), which tells the DESIGN phase how much detail each task needs. The prime seed sets this to `None`. The prime workflow uses a flat `max_lines_per_feature=150` / `max_tokens_per_feature=500` limit for all tasks regardless of type.

**Waste**: A ServiceMonitor YAML (10 lines) gets the same token budget as a full Grafana dashboard JSON (500+ lines). The uniform limit either under-generates complex artifacts or wastes tokens on simple ones.

**Fix**: Compute lightweight per-task token budgets from estimated LOC (already available in `ParsedFeature.estimated_loc`). No LLM call needed — just arithmetic.

### Gap 13: REFINE Suggestions Not Forwarded to Code Generation

Same as Gap 5 but for the prime route. Plan-ingestion's REFINE phase produces architectural review suggestions that are written to the plan document appendix. The prime workflow never reads the plan document — it works exclusively from the seed's task list.

**Waste**: The full REFINE LLM call produces suggestions that do not reach the code generator. The generator may make decisions that the REFINE phase already flagged as problematic.

**Fix**: Extract structured REFINE suggestions into the seed (or a sidecar file) during EMIT. Forward per-task suggestions into the code generation context as advisory constraints.

### Gap 14: No Generation Result Caching in Prime Workflow

The artisan workflow saves per-task `generation_results` and `design_results` in `.startd8/state/` for resume. The `--resume` and `--force-implement` flags enable incremental re-runs. The prime workflow has no equivalent — re-running `run_prime_workflow.py` regenerates all non-complete features from scratch, even if a prior run produced valid code that failed only at the integration step.

**Waste**: If a feature generates successfully ($0.50 LLM cost) but fails integration checkpoint, the next retry regenerates the code rather than re-attempting integration with the existing generated files.

**Fix**: Check `FeatureSpec.generated_files` before calling `code_generator.generate()`. If generated files exist on disk and are non-empty, skip generation and go straight to integration. The `FeatureQueue` state already preserves `generated_files` and `status=GENERATED` across invocations.

### Gap 15: Source Artifact Types Not Registered — Export → DESIGN / IMPLEMENT

> **Status: PARTIALLY RESOLVED (2026-02-20)** — CID-018 source types registered in `ArtifactType` enum. See below.

The `ArtifactType` registry covers 14 types (8 observability, 4 onboarding, 2 integrity) but no source artifacts (Dockerfiles, requirements.in, proto schemas). The manifest declares these as tactic deliverables (TAC-PLAN-004) but the export cannot produce `design_calibration_hints`, `expected_output_contracts`, or `resolved_artifact_parameters` for unregistered types. The DESIGN phase re-derives Docker specifications from scratch. Additionally, four existing detection fragments (export `scan_existing_artifacts`, capability-index `_discovery_paths.yaml`, artifact inventory, SCAFFOLD `target_path.exists()`) each know something about existing assets but no signal flows end-to-end to prevent regeneration.

**Waste**: $1.43 and 21 minutes for 4 Dockerfile tasks in Run 1 artisan. The DESIGN phase produced 2,178 lines of design documents re-deriving base image selection, multi-stage patterns, SHA256 pinning, and environment variables that plan-ingestion had already computed in the artisan-context-seed.

**Fix**: Modular artifact type registry (`ArtifactTypeModule` ABC) with drop-in source modules under `artifact_types/source/`. Leverage capability-index `_discovery_paths.yaml` for actual filesystem scanning (currently metadata-only). End-to-end signal: discovery → `ArtifactStatus.EXISTS` → `skip_existing` task status → contractor skips generation for fresh existing files.

**Partial fix applied (2026-02-20)**: CID-018 amendment implemented — 5 source artifact types (dockerfile, python_requirements, protobuf_schema, editorconfig, ci_workflow) registered in `ArtifactType` enum with `SOURCE_TYPES` frozenset. All 4 onboarding dicts (parameter_sources, example_outputs, output_contracts, parameter_schema) and artifact conventions updated. Export scan patterns extended to discover source artifacts. Remaining: end-to-end `ArtifactStatus.EXISTS` → `skip_existing` flow for contractor generation bypass.

**Detail**: [GAP_15_EXPORT_ARTIFACT_TYPE_COVERAGE.md](~/Documents/Processes/cap-dev-pipe-test/GAP_15_EXPORT_ARTIFACT_TYPE_COVERAGE.md)

### Gap 16: `service_metadata` Never Auto-Derived — Export → DESIGN / IMPLEMENT

> **Status: RESOLVED (2026-02-20)** — Auto-derivation from manifest artifacts implemented.

When `--service-metadata` is not explicitly provided, downstream validators (AR-144, AR-147, AR-810) silently degrade to no-ops because `service_metadata` is `None`. This causes protocol mismatches (e.g., gRPC-vs-Flask defect DEV-R2-001) to go undetected. The information needed to derive service metadata already exists in the artifact manifest — PROTOBUF_SCHEMA artifacts indicate gRPC transport, and artifact parameters carry port hints.

**Waste**: Protocol mismatch defects discovered only at integration testing. Validators designed to catch these mismatches are silently skipped because the metadata they validate against is absent.

**Fix applied (2026-02-20)**: `_derive_service_metadata_from_manifest()` in `onboarding.py` scans `artifact_manifest.artifacts` for protocol indicators per target. PROTOBUF_SCHEMA artifacts trigger `transport_protocol: "grpc"` and `healthcheck_type: "grpc_health_probe"`; all other targets default to HTTP. Called automatically when `service_metadata is None` in `build_onboarding_metadata()`. Explicit `--service-metadata` CLI flag always takes precedence.

---

## Observed Failures — Artisan Run 1 Retry (2026-02-19)

The following violations were observed during a `--retry-incomplete` run against the Online Boutique Python artisan pipeline (17 tasks, 10 passed review, 7 failed). These are not hypothetical — they caused measurable waste in a real pipeline execution.

### Failure 1: `--retry-incomplete` Misidentified All 17 Tasks as Incomplete

**Violated rules**: 1 (Inventory before generating), 2 (Forward, don't regenerate)

**Root cause**: `run_artisan_workflow.py:472` globs for `workflow-result-*.json` (per-task result files) but the artisan produces a single batch `workflow-result.json` (no task-ID suffix). The glob matched nothing, so all 17 tasks — including the 10 that passed review with scores 82-95 — were classified as incomplete and queued for full regeneration.

**Observed waste**: The DESIGN phase ran fresh LLM calls for all 17 tasks instead of only the 7 failures. At ~$0.15/task, this wasted ~$1.50 on designs that already existed and were valid. 11 design documents were overwritten before the run was manually killed.

**Evidence**: Design doc timestamps showed 11 files rewritten at Feb 19 10:46-11:04 (all 17 were queued; process killed before completing). The 10 passing tasks had untouched generated source files from Feb 18.

**Fix applied**: `21548e4` — `--retry-incomplete` now falls back to the batch `workflow-result.json` and reads per-task review verdicts from `.startd8/state/review_results.json`. Tasks with `verdict: PASS` are skipped.

### Failure 2: Design Auto-Adopt Rejected Previously Adopted Designs

**Violated rule**: 2 (Forward, don't regenerate)

**Root cause**: The DESIGN three-way branch (`context_seed_handlers.py:1580`) checked `prior.get("status") == "designed"` but the design handoff also stores entries with `status == "adopted"` — designs that were themselves adopted from a prior run. These entries carry valid `design_document` content but were rejected by the status check and regenerated from scratch.

**Observed waste**: Of the 7 retry tasks, 3 (PI-009, PI-010, PI-011) had `status: "adopted"` in the handoff with valid design documents. All 3 were regenerated via fresh LLM calls instead of being adopted.

**Evidence**: `design-handoff.json` inspection:
```
PI-009: status=adopted, has_doc=True, cost=$0.4806  → regenerated
PI-010: status=adopted, has_doc=True, cost=$0.3365  → regenerated
PI-011: status=adopted, has_doc=True, cost=$0.3388  → regenerated
```

**Fix applied**: `21548e4` — Status check now accepts `status in ("designed", "adopted")`.

### Failure 3: Onboarding Data Not Bridged from Export to Seed (Gaps 1-7 Confirmed)

**Violated rules**: 2 (Forward, don't regenerate), 5 (Prefer deterministic over stochastic)

**Root cause**: Plan-ingestion's EMIT phase writes the artisan-context-seed without reading or forwarding the export's `onboarding-metadata.json`. The seed's `onboarding` section is empty. Additionally, all 17 tasks have `artifact_types_addressed: []`, so the DESIGN handler's per-artifact-type matching logic (lines 1096-1200) produces nothing even where injection code exists.

**Observed waste**: The DESIGN handler has complete injection logic for all 7 onboarding fields — `derivation_rules`, `resolved_parameters`, `output_contracts`, `refine_suggestions`, `plan_architecture`, `calibration_hints`, `open_questions`, `dependency_graph` — but every field was `None` at runtime. The DESIGN LLM re-derived all of these independently for each of the 17 tasks.

**Evidence**: Runtime inspection of the enriched seed:
```
onboarding keys: (empty)
task.artifact_types_addressed: [] (all 17 tasks)
```

While `onboarding-metadata.json` (same pipeline-output directory) contains:
```
derivation_rules:              7 entries
resolved_artifact_parameters:  8 entries
expected_output_contracts:     8 entries
design_calibration_hints:      8 entries
open_questions:                4 entries
artifact_dependency_graph:     4 entries
semantic_conventions:          4 entries
```

**Fix**: Not yet applied. Requires plan-ingestion to read `onboarding-metadata.json` from the export directory and inject it into the seed's `onboarding` field during EMIT. Also requires plan-ingestion to populate `artifact_types_addressed` per task based on target file patterns or manifest artifact-type mappings.

**Estimated cost of violation**: Across 17 tasks, the DESIGN phase spent $2.61 on LLM calls that re-derived parameter values, calibration hints, and architectural patterns that ContextCore had already computed deterministically. The quality cost is harder to quantify — DESIGN documents may contain parameter values inconsistent with the export's deterministic computations, breaking provenance integrity.

---

## Artisan Internal Audit (2026-02-21)

Gaps 1–16 cover the **export → artisan** and **prime** boundaries. This audit examines waste *within* the artisan 7-phase pipeline itself — data produced by one phase that a downstream phase either discards, re-derives, or never reads. Findings are grouped by anti-pattern.

### Anti-Pattern 1: Serialize-and-Forget

A phase produces rich structured data, then serializes only a subset. Downstream phases see a degraded view and must re-parse or operate blind.

#### Gap 17: Reviewer / Arbiter Verdicts Discarded — DESIGN → IMPLEMENT

`DesignPhaseHandler._serialize_result()` (`context_seed_handlers.py:~1435`) extracts 5 of 9 `DesignDocumentResult` fields. **Discarded**: `reviewer_verdict` (approved, confidence, concerns, suggestions), `arbiter_verdict` (same), `escalation_report`, `resolution_decision`. IMPLEMENT receives the final design text but has no signal about review confidence, flagged concerns, or whether the design survived dual-review or was auto-accepted despite disagreement.

**Waste**: 2 LLM review personas × ~4 structured fields each. IMPLEMENT cannot calibrate caution based on design confidence. **Violated rules**: 4 (Register what you produce), 2 (Forward, don't regenerate).

#### Gap 18: `extract_critical_parameters()` Defined But Never Called — DESIGN

`design_documentation.py:~287-353` defines `extract_critical_parameters()` and `check_design_parameter_fidelity()`, both exported in `__all__`. The DESIGN prompt asks the LLM to produce a "Critical Parameters" section (~500-1k tokens/task). Neither function is ever called. Parameters are generated, written into the design document, and never extracted or validated against generated code.

**Waste**: LLM token cost for the critical parameters section with no downstream fidelity check. Port numbers, timeout values, and function signatures may drift between DESIGN and IMPLEMENT with no detection. **Violated rules**: 4, 1 (Inventory before generating).

#### Gap 19: Design Document Sections Not Serialized — DESIGN → IMPLEMENT / TEST

`parse_design_document()` parses raw text into 7 named `DesignSection` entries with completeness metadata. `_serialize_result()` stores only `design_document: raw_text` — the structured sections dict is discarded. Downstream phases that need a specific section (e.g., "API Contracts", "Testing Strategy") must re-parse the blob.

**Waste**: Parsed section structure and completeness flags. When a section was empty (logged as missing during parse), downstream phases cannot distinguish weak vs. strong sections. **Violated rules**: 4, 3 (Degrade gracefully).

#### Gap 20: Plan Architecture / Risk Sections Extracted But Not Stored — DESIGN

`DesignPhaseHandler` extracts "Architecture" and "Risk" sections from the plan document via `_extract_plan_section()` (`context_seed_handlers.py:~1208-1219`) and injects them into the LLM prompt. These sections are **not stored** in `design_results`. IMPLEMENT cannot trace which design decisions were anchored in plan constraints vs. ad-hoc LLM inference.

**Waste**: Plan-level architectural constraints and risk identification (deterministic extraction). Traceability chain Plan → Design → Implement is broken at DESIGN serialization. **Violated rules**: 4, 2.

### Anti-Pattern 2: Compute-But-Don't-Forward

Data is computed and stored in one phase's context, but the downstream phase that would benefit never reads it — forcing recomputation or blind operation.

#### Gap 21: Lessons Discovery Results Never Forwarded — SCAFFOLD → DESIGN / IMPLEMENT

`LessonsDiscovery.discover()` (`lessons_discovery.py:~654-750`) produces ranked lessons categorized by workflow phase, scored by relevance, with a 3600s TTL cache. This result is **never injected** into `DesignPhaseHandler` or `ImplementPhaseHandler` context. Lessons are computed, cached, then ignored.

**Waste**: Relevance scoring and phase categorization cost. Downstream phases cannot incorporate prior project lessons into prompts. **Violated rules**: 2, 4.

#### Gap 22: SCAFFOLD Staleness Not Forwarded to IMPLEMENT

SCAFFOLD computes `staleness_classification` (current/stale/unknown per target file) at `context_seed_handlers.py:~893-927`. Stored in `context["scaffold"]["staleness_classification"]`. AR-127/AR-128 addresses forwarding to DESIGN, but IMPLEMENT **never reads staleness data** — it cannot decide whether a stale file needs regeneration or a current file should be preserved.

**Waste**: File staleness metadata computed once but not reused at generation time. **Violated rules**: 4, 3.

#### Gap 23: Preflight Results Not Forwarded to IMPLEMENT

`PreFlightChecker.run_all()` (`preflight.py:~515-527`) produces a comprehensive `PreFlightReport` covering dependency availability, endpoint reachability, model access, workspace writability, and git state. Stored during PLAN phase, then **never forwarded** to IMPLEMENT. IMPLEMENT re-checks dependencies via `DomainPreflightWorkflow._scan_available_deps()`.

**Waste**: Duplicate endpoint and dependency availability checks. **Violated rules**: 2, 3.

#### Gap 24: Domain Checklist Silent Fallback — IMPLEMENT

`DomainChecklist.get_enrichment()` (`domain_checklist.py:~325-354`) has two resolution paths: load from enriched seed, or fallback to inline computation (`_compute_inline()`). When the task ID isn't found in the enrichment map, code **silently falls back** to recomputing domain classification, dep scanning, and environment checks. No log indicates whether enrichment came from the seed (deterministic) or was freshly computed (stochastic).

**Waste**: Pre-computed domain enrichments discarded without visibility. **Violated rules**: 2, 3.

#### Gap 25: `file_scope` Metadata Not Forwarded to IMPLEMENT

`SeedTask.file_scope` dict (`context_seed_handlers.py:~337, ~417`) maps target file paths to `"primary" | "shared" | "stub"`. Parsed from the enriched seed but **never forwarded to IMPLEMENT**. IMPLEMENT cannot skip stub files, avoid modifying shared files without coordination, or prioritize primary files.

**Waste**: File classification metadata. **Violated rules**: 2.

#### Gap 26: Downstream Files Re-Derived in IMPLEMENT

IMPLEMENT runs `_detect_downstream_files()` (`context_seed_handlers.py:~2880-2906`) against design doc text to build prompt constraints. This detection was **already performed** in Gate 2c (`_reconcile_design_downstream`, lines ~2440-2566) and stored in `downstream_map`. The re-derivation parses the same design doc a second time and risks divergent results if detection logic changes between the two call sites.

**Waste**: Duplicate design doc parsing for downstream file detection. **Violated rules**: 2, 3.

### Anti-Pattern 3: Inject-But-Don't-Validate

Deterministic data is injected into LLM prompts but there's no post-generation check that the LLM honored it, no audit trail when fallbacks occur, and no measurement of the cost when data is silently lost.

#### Gap 27: TEST Phase Blind to Design Documents

TEST phase (`context_seed_handlers.py:~4311-4563`) **never accesses `design_results`** from context. Design documents contain API contracts, class signatures, and behavioral specs that could drive deterministic compliance checks (e.g., "does implementation export the classes the design specified?"). Only REVIEW (which runs after TEST) reads design docs. Catching design violations in TEST would be cheaper — subprocess validators vs. LLM review.

**Waste**: Design artifacts available but unused for deterministic pre-review validation. **Violated rules**: 5 (Prefer deterministic over stochastic), 1.

#### Gap 28: Semantic Conventions Not Validated Deterministically

`semantic_conventions` are forwarded to IMPLEMENT chunks (`context_seed_handlers.py:~2989`) and added to the REVIEW LLM prompt for verification. TEST phase **never validates them deterministically** — a regex/AST check against metric names and label keys would catch naming violations at a fraction of the LLM review cost.

**Waste**: Deterministic validation deferred to stochastic (LLM) review. **Violated rules**: 5.

#### Gap 29: `service_metadata` Availability Not Logged at TEST Boundary

TEST receives `service_metadata` from context and passes it to in-process validators (`context_seed_handlers.py:~4366-4421`), but **never logs whether the metadata is available**. If absent, protocol fidelity and Dockerfile coherence validators silently skip. No degradation warning.

**Waste**: Invisible validator degradation. **Violated rules**: 1, 3.

#### Gap 30: Per-Validator Test Results Lost in FINALIZE Manifest

TEST produces per-validator results (`[{validator, passed, error, message}]` per task). FINALIZE (`context_seed_handlers.py:~5763-5819`) extracts only a boolean `tests_passed` per task in the manifest. Validator-level diagnostic breakdown — which validators are most problematic, failure patterns across tasks — is lost to downstream tooling.

**Waste**: Structured test diagnostics. **Violated rules**: 1, 4.

#### Gap 31: REVIEW Findings Not Structured in FINALIZE Summary

REVIEW produces structured `issues` (with severity classification) and `suggestions` per task. FINALIZE (`context_seed_handlers.py:~5957-5962`) aggregates only totals (`total_passed`, `total_failed`, `total_cost`). No severity breakdown, no top findings, no remediation guidance in the workflow report.

**Waste**: Structured review analysis (severity, suggestions). **Violated rules**: 1, 3.

#### Gap 32: Truncation Confidence Not in Manifest

Truncation detection runs expensive heuristics (line-count ratios, syntax error detection) during IMPLEMENT. Results flow through REVIEW prompts and the human-readable FINALIZE summary. But the **manifest omits truncation confidence per task** (`context_seed_handlers.py:~5821-5838`). Downstream tooling must re-run detection to prioritize follow-up work.

**Waste**: Expensive heuristic analysis recomputed downstream. **Violated rules**: 2, 4.

#### Gap 33: Onboarding Inventory Fallback — No Audit Trail

Onboarding inventory fields (derivation_rules, resolved_parameters, output_contracts, calibration_hints, etc.) are loaded from either export inventory.json or onboarding context keys (`context_seed_handlers.py:~1172-1298, ~1596-1640`). **No audit trail** records which source each field came from. Operators cannot distinguish deterministic (export) from stochastic (onboarding fallback) resolution paths.

**Waste**: Auditability of data provenance within the pipeline. **Violated rules**: 2, 3.

#### Gap 34: Open Questions and Dependency Graph — No Satisfaction Tracking

`open_questions` (from ContextCore guidance) and `dependency_graph` (artifact interdependencies) are injected into the DESIGN prompt (`context_seed_handlers.py:~1248-1297`). No post-generation check validates whether the design addressed the questions or honored the dependency ordering. Long question lists are truncated to first 10 without logging how many were dropped.

**Waste**: Deterministic guidance injected without validation of consumption. **Violated rules**: 4, 3.

#### Gap 35: IMP-7 Parameter Loss Detected But Never Measured

IMP-7 (`context_seed_handlers.py:~2922-2957`) checks for missing `resolved_parameters` in design documents. Findings are appended to `design_completeness_warning` in chunk metadata but **never used downstream** by TEST or REVIEW. No measurement of how often parameter loss causes implementation defects or how much rework it costs.

**Waste**: Detection without measurement violates rule 6. **Violated rules**: 1, 6 (Measure the gap).

#### Gap 36: Generated File Checksums Not Persisted Until TEST

Generated file checksums are first computed at **TEST cache time** (`context_seed_handlers.py:~4517-4555`), not at IMPLEMENT output time. IMPLEMENT artifacts lack self-describing integrity metadata. If IMPLEMENT resumes multiple times before reaching TEST, checksums are recomputed each time.

**Waste**: Redundant hash computation on resume. **Violated rules**: 4.

### Summary — Artisan Internal Audit

| Anti-Pattern | Gap IDs | Core Issue |
|-------------|---------|------------|
| **Serialize-and-forget** | 17, 18, 19, 20 | DESIGN produces rich structured data, serializes only raw_text blob |
| **Compute-but-don't-forward** | 21, 22, 23, 24, 25, 26 | Data computed in one phase, never read by the phase that needs it |
| **Inject-but-don't-validate** | 27, 28, 29, 30, 31, 32, 33, 34, 35, 36 | Deterministic data injected into prompts with no post-generation audit |

**Recommended priority**:
- **P0 (high impact, easy)**: Gaps 17, 19, 26 — store data already computed; minimal code change
- **P1 (high impact, moderate)**: Gaps 18, 27, 28, 30 — wire up existing functions/data to downstream consumers
- **P2 (medium impact)**: Gaps 21, 22, 23, 24, 25, 33 — cross-phase forwarding and audit trail
- **P3 (lower impact)**: Gaps 20, 29, 31, 32, 34, 35, 36 — measurement, manifest completeness

> **Formalized**: All 20 gaps (17–36) are now tracked as formal requirements **AR-900 through AR-908** in [`startd8.artisan.functional-requirements.yaml`](../capability-index/startd8.artisan.functional-requirements.yaml). See [ARTISAN_REQUIREMENTS.md](../artisan/ARTISAN_REQUIREMENTS.md) Layer 9 for the narrative companion.

---

## Application Rules

When designing new pipeline stages or modifying existing ones:

1. **Inventory before generating.** Before an LLM call that produces design decisions, parameter values, or architectural context, check the pipeline artifact inventory for existing assets that cover the same ground.

2. **Forward, don't regenerate.** If an earlier stage deterministically computed a value (derivation rules, resolved parameters, dependency ordering), pass it through to later stages rather than asking an LLM to re-derive it.

3. **Degrade gracefully.** If an earlier artifact is missing or stale, fall back to LLM generation — but log the fallback and the reason. The fallback is acceptable; silently ignoring available assets is not.

4. **Register what you produce.** Each stage that produces artifacts useful to downstream stages should register them in the pipeline artifact inventory with: semantic role, file path, freshness indicator (checksum + timestamp), and the stage that produced them.

5. **Prefer deterministic over stochastic.** When both a deterministic value (from export) and an LLM-generated value are available, prefer the deterministic one. The LLM value is useful as a fallback or validation signal, not as the primary source.

6. **Measure the gap.** When closing a mottainai violation, log the before/after cost. This makes the value of reuse visible and builds the case for future investment.

---

## Relationship to Other Requirements

| Document | Relationship |
|----------|-------------|
| [Pipeline Artifact Inventory Requirements](./PIPELINE_ARTIFACT_INVENTORY_REQUIREMENTS.md) | The inventory mechanism that enables mottainai — tracks what exists so downstream stages can find it |
| [Manifest Export Requirements](./MANIFEST_EXPORT_REQUIREMENTS.md) | Defines the export outputs that are the primary source of reusable artifacts |
| [A2A Gate Requirements](./A2A_GATE_REQUIREMENTS.md) | Gates validate artifact integrity at boundaries — mottainai adds the question "are we using what we validated?" |
| [Export Pipeline Analysis Guide](../guides/EXPORT_PIPELINE_ANALYSIS_GUIDE.md) | The operational guide that describes the 7-step pipeline where mottainai violations occur |
| [`startd8.artisan.functional-requirements.yaml`](../capability-index/startd8.artisan.functional-requirements.yaml) (AR-900..AR-908) | Formal requirements for Mottainai compliance within the artisan 7-phase pipeline — maps Gaps 17–36 to testable acceptance criteria |
| [REFINE Forwarding Requirements](../REFINE_FORWARDING_REQUIREMENTS.md) (REQ-RF-001..012) | Closes Gaps 5 and 13 — forwards REFINE triage, apply, and area coverage output through the seed to downstream consumers |

---

## Changelog

| Date | Change |
|------|--------|
| 2026-02-16 | Initial version: principle statement, 8 known violations from pipeline analysis, application rules |
| 2026-02-17 | Prime Contractor audit: added Gaps 9–14 (seed enrichment discarded, onboarding not injected, no architectural context, no design calibration, REFINE suggestions not forwarded, no generation result caching) |
| 2026-02-18 | Gap 15: source artifact types not registered in export; modular artifact type registry proposed with end-to-end existing-asset detection (detail in separate doc) |
| 2026-02-19 | Added Observed Failures section: 3 violations from artisan Run 1 retry — batch result detection (fixed `21548e4`), adopted-status rejection (fixed `21548e4`), onboarding data not bridged from export to seed (Gaps 1-7 confirmed with evidence, not yet fixed) |
| 2026-02-20 | Gap 15 partially resolved: CID-018 source types (5) registered in ArtifactType enum with full onboarding dict coverage. Gap 16 resolved: auto-derive service_metadata from manifest artifacts |
| 2026-02-21 | Artisan Internal Audit: added Gaps 17–36 (20 intra-pipeline violations across 3 anti-patterns: serialize-and-forget, compute-but-don't-forward, inject-but-don't-validate). A-15 addressed by AR-127/AR-128 |
| 2026-02-21 | Added [REFINE Forwarding Requirements](../REFINE_FORWARDING_REQUIREMENTS.md) (REQ-RF-001..012) to close Gaps 5 and 13 — REFINE triage/apply/config forwarding through the seed, informed by ContextCore propagation contract model |
