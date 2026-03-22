# Review Feedback Loop — Requirements

**Version:** 2.0.0
**Created:** 2026-03-22
**Updated:** 2026-03-22 (v2.0 — review step via Artisan adapter, upstream amplification, seed unification alignment)
**Pattern:** Kaizen (cross-phase signal propagation), Mottainai (don't discard validation artifacts), Warm Up (don't discard context across toolchain transitions)
**Domain:** Cap-Dev-Pipe → Plan Ingestion → Prime Contractor → Integration → Review → Spec Builder

---

## Overview

The Prime Contractor pipeline generates rich validation and repair signals during integration but discards them. It also lacks a review step — unlike Artisan, which has `ReviewPhaseHandler`. The existing Artisan review infrastructure is nearly standalone and reusable.

This design adds:
1. A **per-feature review step** to Prime Contractor by reusing the Artisan `ReviewPhaseHandler` via a lightweight adapter (~100 lines)
2. **Within-run feedback** where review insights from feature A inform feature B's spec
3. A **quality gate** where review FAIL + low disk quality score triggers re-draft with the reviewer's issues as corrective guidance
4. **Upstream amplification** where plan ingestion and seed enrichment carry quality signals per-task, closing the cross-run loop at the seed level (not just the spec level)

### Why a Review Step (Not Just a Numeric Gate)

A numeric quality gate (score < 0.3 → re-draft) can detect bad output but can't explain *why* it's bad. An LLM review produces structured issues: "circular import between logger and server", "factory doesn't return the interface type", "error handling missing for timeout path." These specific issues become dramatically better corrective hints for re-draft AND dramatically better spec hints for subsequent features.

### Iterative Delivery

The requirements are organized into three iterations of increasing risk:

| Iteration | What | Risk | LLM Cost | Test With |
|-----------|------|------|----------|-----------|
| **I1: Plumbing + Review** | Persist signals, review adapter, log-only mode | None/Low | +1 call/feature | Single feature run |
| **I2: Gate + Feedback** | Re-draft on FAIL, accumulator, spec injection | Medium | +1 call/gate fire | Multi-feature run |
| **I3: Upstream Amplification** | Seed quality_hints, plan ingestion threading, cap-dev-pipe enrichment | Low | Zero | Full pipeline run |

---

## Status Dashboard

| Req ID | Title | Priority | Status | Iteration |
|--------|-------|----------|--------|-----------|
| **Iteration 1 — Plumbing + Review** | | | | |
| REQ-RFL-100 | Persist DiskComplianceResult in integration metadata | P0 | planned | I1 |
| REQ-RFL-105 | Persist RepairOutcome summary in integration metadata | P0 | planned | I1 |
| REQ-RFL-110 | Extract compute_disk_quality_score() as standalone utility | P0 | planned | I1 |
| REQ-RFL-115 | Compute disk quality score at integration time | P0 | planned | I1 |
| REQ-RFL-120 | Prime review adapter (FeatureSpec → ReviewPhaseHandler) | P0 | planned | I1 |
| REQ-RFL-125 | Review step wiring in PrimeContractor (optional, on by default) | P0 | planned | I1 |
| REQ-RFL-128 | Repair effectiveness public query API | P1 | planned | I1 |
| **Iteration 2 — Gate + Feedback** | | | | |
| REQ-RFL-200 | RunQualityAccumulator — within-run signal aggregator | P0 | planned | I2 |
| REQ-RFL-210 | Review issue classification (heuristic) | P1 | planned | I2 |
| REQ-RFL-220 | Quality gate: review FAIL + low score → re-draft | P0 | planned | I2 |
| REQ-RFL-225 | Re-draft uses review issues as corrective P0 hint | P0 | planned | I2 |
| REQ-RFL-230 | Re-draft budget guard and attempt cap | P0 | planned | I2 |
| REQ-RFL-240 | Accumulator feeds review + validation signals → next spec | P0 | planned | I2 |
| REQ-RFL-250 | Spec builder "Prior Run Findings" section (P2) | P0 | planned | I2 |
| REQ-RFL-260 | Quality trend detection (declining slope warning) | P2 | planned | I2 |
| REQ-RFL-270 | Repair effectiveness → spec emphasis calibration | P2 | planned | I2 |
| **Iteration 3 — Upstream Amplification** | | | | |
| REQ-RFL-300 | SeedTask.quality_hints field | P1 | planned | I3 |
| REQ-RFL-310 | Plan ingestion: distribute kaizen suggestions per-task | P1 | planned | I3 |
| REQ-RFL-320 | Post-ingestion enrichment step (cap-dev-pipe) | P1 | planned | I3 |
| REQ-RFL-330 | Context resolution: thread quality_hints to prompt_constraints | P1 | planned | I3 |
| REQ-RFL-340 | Seed unification: shared review-relevant fields | P2 | planned | I3 |
| **Cross-Cutting** | | | | |
| REQ-RFL-500 | OTel attributes for feedback loop observability | P2 | planned | I1+ |
| REQ-RFL-510 | Backward compatibility (no required param changes) | P0 | planned | All |
| REQ-RFL-520 | Checkpoint/resume compatibility | P0 | planned | All |

---

## Iteration 1: Plumbing + Review (Low Risk)

Goal: Persist existing signals, add a per-feature review step to Prime Contractor, log results. No behavioral change to generation — the review produces data but doesn't gate or re-draft.

### REQ-RFL-100: Persist DiskComplianceResult in Integration Metadata
**Status:** planned | **Priority:** P0 | **Quick Win:** Yes

The integration engine's `_run_semantic_checks()` computes `DiskComplianceResult` per file, logs warnings, discards results. This is a void method that modifies state via side effects on the unit/context.

**Requirements:**
1. `_run_semantic_checks()` MUST accumulate per-file compliance data in the integration unit's metadata.
2. Storage MUST happen via mutation of the unit or integration_results dict (since the method returns None).
3. Values MUST be serializable dicts (all primitive types) for checkpoint compatibility.
4. Each entry: `ast_valid`, `stubs_remaining`, `duplicate_definitions`, `import_completeness`, `contract_compliance`, `semantic_issues` (list of `{category, severity, message}`).
5. Clean results (no issues, all scores 1.0) SHOULD be omitted.

---

### REQ-RFL-105: Persist RepairOutcome Summary in Integration Metadata
**Status:** planned | **Priority:** P0 | **Quick Win:** Yes

**Requirements:**
1. After repair calls, a condensed summary MUST be stored under `"repair_summary"` in integration metadata.
2. Summary: `total_repairs`, `steps_applied` (list), `any_modified` (bool), per-file `before_valid` → `after_valid` transitions.
3. Pre-merge and post-merge summaries combined under `"pre_merge"` / `"post_merge"` sub-keys.

---

### REQ-RFL-110: Extract compute_disk_quality_score() as Standalone Utility
**Status:** planned | **Priority:** P0 | **Quick Win:** Yes

**Requirements:**
1. Move to `forward_manifest_validator.py` (co-located with `DiskComplianceResult`).
2. Re-export from `prime_postmortem.py` for backward compatibility.
3. Formula unchanged: `(contract_compliance × 0.4) + (import_completeness × 0.2) + (stub_penalty × 0.2) + (semantic_penalty × 0.2)`.
4. Must work with both `DiskComplianceResult` objects and dicts-wrapped-in-SimpleNamespace (for serialized data).

---

### REQ-RFL-115: Compute Disk Quality Score at Integration Time
**Status:** planned | **Priority:** P0

**Requirements:**
1. After `_run_semantic_checks()`, compute per-file scores and store task-level aggregate as `"disk_quality_score"` (min of per-file scores = weakest link).
2. If no Python files validated, score is `None`.

---

### REQ-RFL-120: Prime Review Adapter
**Status:** planned | **Priority:** P0

A lightweight adapter that bridges Prime Contractor's `FeatureSpec` to the Artisan `ReviewPhaseHandler`.

**Requirements:**
1. New module: `src/startd8/contractors/prime_review.py`.
2. Adapter class `PrimeReviewAdapter` with method `review_feature(feature, project_root, config) → dict`.
3. Field mapping: `FeatureSpec` → synthetic `SeedTask`:
   - `feature.id` → `task.task_id`
   - `feature.name` → `task.title`
   - `feature.description` → `task.description`
   - `feature.target_files` → `task.target_files`
   - `feature.metadata.get("domain", "general")` → `task.domain`
   - `feature.metadata.get("prompt_constraints", [])` → `task.prompt_constraints`
4. Code assembly: Read generated files from disk, concatenate with `# filename` headers.
5. Call `ReviewPhaseHandler._review_task()` with minimal params: `task`, `generated_code`, `test_results={}`.
6. Enrichment: Pass `disk_compliance` and `repair_summary` from integration metadata as structured context. These flow to the review prompt via a new optional parameter (or via the existing `forward_contract_violations` slot — see design decision below).
7. Return: `{score, verdict, strengths, issues, suggestions, cost_usd, tokens}`.
8. The adapter MUST NOT modify `ReviewPhaseHandler` itself.

**Design Decision — How to Pass Validation Signals to Reviewer:**
- **Option A:** Add optional `quality_signals` param to `_build_review_prompt()` — minimal ReviewPhaseHandler modification (one new Optional param, one new section builder).
- **Option B:** Pack validation signals into `test_results` dict (reviewer already renders test results) — zero ReviewPhaseHandler modification.
- **Recommendation:** Option B for I1 (zero modification), migrate to Option A in I2 when Artisan reactivation is closer. The reviewer will see "## Validation Results" instead of "## Test Results" but the LLM doesn't care about header names.

---

### REQ-RFL-125: Review Step Wiring in PrimeContractor
**Status:** planned | **Priority:** P0

Wire the review adapter into the Prime Contractor feature processing loop.

**Requirements:**
1. After `integrate_feature()` succeeds, call `PrimeReviewAdapter.review_feature()`.
2. Store review result in `feature.metadata["review"]` and in `self.review_results[feature.id]`.
3. Log review score and verdict at INFO level.
4. **Configurable:** `review_enabled: bool = True` (on by default), `review_agent: str | None = None` (defaults to `config.lead_agent`).
5. **Cost:** Review uses the same agent as generation. Typically 1 LLM call per feature.
6. **Graceful degradation:** If review fails (LLM error, timeout), log WARNING and continue — do not block feature completion.
7. **I1 behavior:** Review is log-only. Score and issues are recorded but do NOT trigger re-draft or gate. This allows testing the review quality before wiring behavioral changes.

**Acceptance Criteria:**
- Run with `review_enabled=True`: each feature gets a review score logged.
- Run with `review_enabled=False`: identical to current behavior.
- Review failure does not block feature completion.

---

### REQ-RFL-128: Repair Effectiveness Public Query API
**Status:** planned | **Priority:** P1 | **Quick Win:** Yes

**Requirements:**
1. `get_step_effectiveness_summary() → dict[str, dict]` in `repair/orchestrator.py`.
2. Return: `{step_name: {"attempts": int, "success_rate": float, "contributed_to_success": int}}`.
3. Read-only snapshot of module-level state. Safe from any thread.

---

## Iteration 2: Gate + Feedback (Medium Risk)

Goal: Wire the review verdict into a quality gate that triggers re-draft, and close the within-run feedback loop so subsequent features benefit from accumulated review insights.

**Prerequisite:** I1 deployed, review producing reasonable scores verified in ≥1 run.

### REQ-RFL-200: RunQualityAccumulator
**Status:** planned | **Priority:** P0

Within-run signal aggregator. NOT persisted to disk.

**Requirements:**
1. New class in `src/startd8/contractors/run_quality_accumulator.py`.
2. Records per-feature: disk quality score, semantic issue categories, repair counts, **review score, review classified issues**.
3. Provides:
   - `get_run_level_patterns() → dict[str, int]`: Semantic + review issue categories with count ≥ 2.
   - `build_spec_hints(existing_kaizen_categories) → str | None`: Condensed hint ≤500 chars.
   - `get_quality_trend() → str | None`: "declining" if last 3 scores decreasing.
4. Instantiated in `PrimeContractor.run()`, reset per run.
5. Sequential processing → no concurrency concerns.

---

### REQ-RFL-210: Review Issue Classification (Heuristic)
**Status:** planned | **Priority:** P1

Lightweight keyword-based classification of review issues for accumulator pattern detection.

**Requirements:**
1. Classify each extracted review issue into: `syntax`, `semantics`, `design`, `naming`, `testing`, `performance`, `security`, `other`.
2. Heuristic (keyword matching), not LLM-based — zero additional API calls.
3. Added to `_parse_review_response()` output as `classified_issues: list[dict]` alongside existing raw `issues: list[str]`.

---

### REQ-RFL-220: Quality Gate — Review FAIL + Low Score → Re-Draft
**Status:** planned | **Priority:** P0

The quality gate uses the review verdict as primary signal, disk quality score as secondary.

**Requirements:**
1. After review completes, if `verdict == "FAIL"` AND `disk_quality_score < threshold` (default 0.5, configurable), trigger re-draft.
2. The dual condition prevents: re-drafting on a harsh reviewer when code is actually fine (FAIL but score 0.85), or re-drafting on bad code that the reviewer couldn't parse (score 0.2 but no structured issues).
3. The gate MUST fire at most once per feature.
4. The gate MUST be configurable: `quality_gate_enabled: bool = True`, `quality_gate_threshold: float = 0.5`.
5. When the gate fires, the feature is NOT marked failed — it gets one re-draft attempt.

---

### REQ-RFL-225: Re-Draft Uses Review Issues as Corrective P0 Hint
**Status:** planned | **Priority:** P0

This is the core value of the review step — the re-draft gets *specific guidance*.

**Requirements:**
1. When re-draft is triggered, build a corrective hint from the review's `issues` list (BLOCKING and MAJOR only).
2. Corrective hint format:
   ```
   CRITICAL: Previous generation was reviewed and rejected.
   Fix these specific issues:
   - [BLOCKING] Circular import between logger.py and server.py
   - [MAJOR] Factory create_handler() returns None instead of Handler instance
   - [MAJOR] No error handling for timeout in async request path
   Your score was [X]/100. Target: [threshold].
   ```
3. Corrective hint MUST be injected as P0 section in the re-draft's spec (highest priority, never dropped by budget).
4. Corrective hint MUST be capped at 800 chars (the issues themselves are already concise).
5. The re-draft MUST use the same model as the original draft (no escalation in I2; escalation is a separate future requirement).

---

### REQ-RFL-230: Re-Draft Budget Guard and Attempt Cap
**Status:** planned | **Priority:** P0

**Requirements:**
1. Re-draft cost tracked in CostTracker (not hidden).
2. Re-draft counts toward feature total cost.
3. If run's total cost exceeds budget, quality gate MUST be disabled for remaining features.
4. Exactly 1 re-draft attempt per feature. If re-draft also fails review, accept the better-scoring version.
5. Gate fires track: compare original disk_quality_score vs re-draft disk_quality_score. Accept whichever scores higher (Mottainai — don't discard the better output).

---

### REQ-RFL-240: Accumulator Feeds Review + Validation Signals → Next Spec
**Status:** planned | **Priority:** P0

**Requirements:**
1. After each feature (including any re-draft), feed to accumulator:
   - Disk compliance results (semantic categories)
   - Review classified issues (category + severity)
   - Disk quality score
   - Repair step counts
2. Before building next feature's spec, call `accumulator.build_spec_hints()`.
3. Inject hints via `context["run_quality_hints"]` (separate key from kaizen, not destructive).

---

### REQ-RFL-250: Spec Builder "Prior Run Findings" Section
**Status:** planned | **Priority:** P0

**Requirements:**
1. `build_spec_prompt()` MUST check `context.get("run_quality_hints")`.
2. Section header: `## Prior Integration Findings (This Run)`.
3. Priority P2 (between kaizen P1 and arch context P3).
4. Budget: 500 chars. Dropped for first feature (no data yet).
5. Content from `accumulator.build_spec_hints()` — deduped against existing kaizen categories.

---

### REQ-RFL-260: Quality Trend Detection
**Status:** planned | **Priority:** P2

**Requirements:**
1. `accumulator.get_quality_trend()` → "declining" if last 3 scores strictly decreasing.
2. When declining, spec builder injects P1 "Quality Trend Warning" (200 chars).
3. Requires ≥3 completed features with scores.

---

### REQ-RFL-270: Repair Effectiveness → Spec Emphasis Calibration
**Status:** planned | **Priority:** P2

**Requirements:**
1. Spec builder queries `get_step_effectiveness_summary()`.
2. Steps with success_rate < 0.2 and ≥5 attempts: inject P1 warning.
3. Steps with success_rate > 0.8: no spec emphasis (repair will catch it).

---

## Iteration 3: Upstream Amplification (Cross-Run, Seed Unification)

Goal: Close the cross-run feedback loop at the seed level so quality signals persist across runs, flow per-task (not just per-run), and work identically for Prime and Artisan.

**Prerequisite:** I2 deployed, within-run feedback producing measurable quality improvement.

### REQ-RFL-300: SeedTask.quality_hints Field
**Status:** planned | **Priority:** P1

**Requirements:**
1. Add optional field to `SeedTask`: `quality_hints: list[str] = []`.
2. Populated from `context.get("quality_hints", [])` in `SeedTask.from_seed_entry()`.
3. Distinct from `prompt_constraints` (which come from the plan/domain). `quality_hints` come from previous run postmortems.
4. Both Prime and Artisan consume `quality_hints` — shared field, no pipeline-specific logic.
5. When both `quality_hints` and `prompt_constraints` are present, spec builder renders them as separate sections (constraints = structural requirements, hints = learned quality guidance).

**Seed Unification Value:** This field is the first review-relevant field shared by both pipelines. It moves toward the goal of "a single seed no different between Prime and Artisan."

---

### REQ-RFL-310: Plan Ingestion — Distribute Kaizen Suggestions Per-Task
**Status:** planned | **Priority:** P1

Currently `SeedBuilder.set_artifacts()` extracts `refine_suggestions` but stores them in the onboarding appendix, not distributed to individual tasks.

**Requirements:**
1. Plan ingestion's transform phase MUST match kaizen suggestions to individual tasks by pattern.
2. Matching heuristic: suggestion's `pattern_type` (e.g., `phantom_import`) mapped to tasks whose `target_files` or `domain` overlap with the pattern's observed context.
3. Matched suggestions MUST be injected into the task's `quality_hints` field (REQ-RFL-300).
4. Unmatched suggestions (no task affinity) MUST be injected into ALL tasks as run-level hints.
5. Budget: ≤3 quality hints per task (highest-confidence first).

**Value:** Feature A gets "watch for phantom imports in server modules" while Feature B gets "ensure factory methods return interface types" — targeted, not generic.

---

### REQ-RFL-320: Post-Ingestion Enrichment Step (Cap-Dev-Pipe)
**Status:** planned | **Priority:** P1

A new step in the cap-dev-pipe that enriches a seed with quality signals from a previous run's postmortem.

**Requirements:**
1. New script: `scripts/enrich_seed_from_postmortem.py`.
2. Input: seed JSON path + postmortem report JSON path (or kaizen-suggestions.json path).
3. Output: enriched seed JSON with per-task `quality_hints` populated.
4. Wired into `.cap-dev-pipe/run-prime-contractor.sh` as optional pre-step: `--postmortem <path>`.
5. If no postmortem provided, seed is used unchanged (backward compatible).
6. The enrichment step MUST be idempotent — re-running with the same postmortem produces identical output.

**Value:** Closes the cross-run loop at the pipeline level. The operator runs: `./run-prime-contractor.sh --postmortem previous-run/kaizen-suggestions.json` and every task gets per-task quality guidance from the last run.

---

### REQ-RFL-330: Context Resolution — Thread quality_hints to Prompt Constraints
**Status:** planned | **Priority:** P1

**Requirements:**
1. Both `StandaloneContextStrategy` and `PipelineContextStrategy` MUST extract `quality_hints` from feature metadata and thread to spec builder context.
2. `quality_hints` MUST be rendered as a separate section from `prompt_constraints` in the spec prompt.
3. The spec builder MUST render quality hints under `## Quality Guidance (From Previous Runs)` header.
4. Budget: 600 chars for quality hints section (P1.5 — between kaizen hints P1 and run quality hints P2).

---

### REQ-RFL-340: Seed Unification — Shared Review-Relevant Fields
**Status:** planned | **Priority:** P2

Progress toward a single seed format for both Prime and Artisan.

**Requirements:**
1. `SeedTask` MUST carry all fields needed for review: `quality_hints`, `review_constraints` (structural requirements the reviewer should check), `review_threshold` (per-task pass threshold, default None = use global).
2. `FeatureSpec` metadata MUST preserve these fields during `queue.add_features_from_seed()` flattening.
3. `ReviewPhaseHandler` (Artisan) and `PrimeReviewAdapter` (Prime) MUST both consume these fields from the same seed model.
4. The `PrimeReviewAdapter`'s synthetic SeedTask construction (REQ-RFL-120) MUST forward all review-relevant fields from the original seed, not just the core fields.

**Acceptance Criteria:**
- A single seed JSON file, run through both Prime and Artisan, produces review prompts that include task-specific quality hints.
- No pipeline-specific field mapping needed for review-relevant data.

---

## Cross-Cutting Concerns

### REQ-RFL-500: OTel Attributes for Feedback Loop Observability
**Status:** planned | **Priority:** P2

**Requirements:**
1. Integration span: `integration.disk_quality_score` (float), `integration.semantic_issue_count` (int), `integration.repair_steps_applied` (int).
2. Review span: `review.score` (int), `review.verdict` (str), `review.issue_count` (int), `review.cost_usd` (float).
3. Quality gate span (if triggered): `quality_gate.triggered` (bool), `quality_gate.pre_score` (float), `quality_gate.post_score` (float), `quality_gate.accepted_version` (str: "original" or "redraft").
4. Spec builder span: `spec.run_quality_hints.present` (bool), `spec.quality_hints.count` (int).

---

### REQ-RFL-510: Backward Compatibility
**Status:** planned | **Priority:** P0

**Requirements:**
1. All new config fields default to enabling the feature (`review_enabled=True`, `quality_gate_enabled=True`).
2. All new `SeedTask` fields default to empty (`quality_hints=[]`).
3. All new context keys consumed via `.get()` with `None` default.
4. Review failure MUST NOT block feature completion (graceful degradation).
5. No existing test MUST break.

---

### REQ-RFL-520: Checkpoint/Resume Compatibility
**Status:** planned | **Priority:** P0

**Requirements:**
1. Review results stored in feature metadata MUST survive checkpoint serialization.
2. Run quality hints MUST NOT affect spec hash (advisory, not structural).
3. On resume, accumulator starts empty (not persisted). Features re-processed from checkpoint will re-accumulate.
4. Review results from before checkpoint MUST be loadable (so resumed runs can compare pre/post re-draft scores).

---

## Data Flow Diagram (Full Pipeline)

```
  ┌─────────────────────────────────────────────────────────────────┐
  │                    CAP-DEV-PIPE                                 │
  │                                                                 │
  │  Plan Doc ──► Plan Ingestion ──► Base Seed                     │
  │                                     │                           │
  │                                     ▼                           │
  │                    ┌────────────────────────────────────┐       │
  │                    │ Post-Ingestion Enrichment (I3)     │       │
  │                    │ + Previous run's kaizen-suggestions│       │
  │                    │ → per-task quality_hints           │       │
  │                    └────────────────┬───────────────────┘       │
  │                                     │                           │
  │                                     ▼                           │
  │                              Enriched Seed                      │
  │                    (quality_hints per task)                     │
  └─────────────────────────────┬───────────────────────────────────┘
                                │
          ┌─────────────────────┼─────────────────────┐
          │                     │                     │
          ▼                     ▼                     ▼
     Prime Contractor      Artisan (ON HOLD)     Future Pipeline
          │
  ┌───────┴──────────────────────────────────────────────────────┐
  │  PRIME CONTRACTOR — SEQUENTIAL LOOP                          │
  │                                                              │
  │  ┌────────────────────────────────────────────────────────┐  │
  │  │  RunQualityAccumulator (I2)                            │  │
  │  │  semantic_patterns, review_issues, quality_scores      │  │
  │  └──────────┬──────────────────────────────┬──────────────┘  │
  │             │                              │                  │
  │             ▼                              │                  │
  │  ┌──────────────────────────────────────┐  │                  │
  │  │  SPEC BUILDER (per feature)          │  │                  │
  │  │  P0: corrective hint (re-draft only) │  │                  │
  │  │  P1: kaizen hints (prev run)         │  │                  │
  │  │ P1.5: quality_hints (seed, I3)       │  │                  │
  │  │  P2: run_quality_hints (this run,I2) │  │                  │
  │  │  P3: architectural context           │  │                  │
  │  └──────────────┬───────────────────────┘  │                  │
  │                 ▼                          │                  │
  │  ┌──────────────────────────────────────┐  │                  │
  │  │  DRAFT (code generation)             │  │                  │
  │  └──────────────┬───────────────────────┘  │                  │
  │                 ▼                          │                  │
  │  ┌──────────────────────────────────────┐  │                  │
  │  │  INTEGRATION ENGINE                  │  │                  │
  │  │  validate + repair + persist signals │  │                  │
  │  │  → disk_compliance (I1)              │  │                  │
  │  │  → repair_summary (I1)              │  │                  │
  │  │  → disk_quality_score (I1)          │  │                  │
  │  └──────────────┬───────────────────────┘  │                  │
  │                 ▼                          │                  │
  │  ┌──────────────────────────────────────┐  │                  │
  │  │  REVIEW (I1) — PrimeReviewAdapter    │  │                  │
  │  │  FeatureSpec → synthetic SeedTask    │  │                  │
  │  │  + disk_compliance as "test_results" │  │                  │
  │  │  → score, verdict, issues            │  │                  │
  │  └──────────────┬───────────────────────┘  │                  │
  │                 │                          │                  │
  │                 ▼                          │                  │
  │  ┌──────────────────────────────────────┐  │                  │
  │  │  QUALITY GATE (I2)                   │  │                  │
  │  │  FAIL + score < threshold?           │  │                  │
  │  │  ├─ yes → re-draft with review       │  │                  │
  │  │  │        issues as P0 hint          │  │                  │
  │  │  │        (max 1 attempt)            │  │                  │
  │  │  │        accept better-scoring ver  │  │                  │
  │  │  └─ no → continue                   │  │                  │
  │  └──────────────┬───────────────────────┘  │                  │
  │                 │                          │                  │
  │                 ▼                          │                  │
  │  Feed signals to accumulator ──────────────┘                  │
  │  Next feature (loop)                                         │
  │                                                              │
  └──────────────────────────────────────────────────────────────┘
                    │
                    ▼ (after all features)
  ┌──────────────────────────────────────────────────────────────┐
  │  POSTMORTEM                                                  │
  │  → kaizen-suggestions.json (feeds I3 enrichment)            │
  │  → batch trends                                              │
  └──────────────────────────────────────────────────────────────┘
```

---

## Post-Plan Reflection (Carried Forward from v1.1, Updated)

### Insight 1: Artisan ReviewPhaseHandler Is Reusable With ~100 Lines of Adapter
The `_build_review_prompt()` + `_parse_review_response()` methods are nearly standalone. All 9 enrichment parameters are optional with None defaults. The adapter is field mapping + file reading, not a redesign.

### Insight 2: Pack Validation Signals Into test_results (Zero Modification Path)
For I1, passing disk compliance and repair data via the `test_results` dict parameter avoids any modification to ReviewPhaseHandler. The reviewer renders them under "## Test Results" — the LLM doesn't care about header names, it cares about the content.

### Insight 3: Review Issues Are Dramatically Better Re-Draft Hints Than Numeric Scores
A quality gate saying "score 0.25, try again" produces nearly identical re-draft output. A review saying "circular import between logger and server, factory returns None" gives the model specific fixes to make. This is the core value proposition.

### Insight 4: Dual Condition Prevents False Positives
Gate fires on `FAIL AND score < threshold`, not just FAIL. A harsh reviewer might FAIL code that's actually decent (score 0.85). A broken generation might get a nonsensical review. The dual condition requires both signals to agree.

### Insight 5: Accept the Better Version (Mottainai)
If re-draft also fails, compare disk quality scores and accept whichever version is better. Don't discard the original if the re-draft is worse.

### Insight 6: Upstream Per-Task Quality Hints Are Higher Value Than Per-Run
Plan ingestion currently stores kaizen suggestions in the onboarding appendix (applied to all tasks generically). Distributing them per-task based on pattern affinity means Feature A gets "watch for phantom imports in server modules" while Feature B gets "ensure factory returns the interface type." Targeted beats generic.

### Insight 7: Sequential Processing Means the Accumulator Is Trivial
No locks, no thread-safe collections, no race conditions. Just a dataclass that appends.

### Insight 8: context.pop("kaizen_hints") Requires Separate Key
Existing kaizen hint injection destructively pops the key. All new feedback data uses separate keys (`run_quality_hints`, `quality_hints`) to avoid interference.

### Insight 9: Seed Unification Starts With Shared Review Fields
`quality_hints` on SeedTask is the first field that both pipelines consume identically. Each additional shared field (review_constraints, review_threshold) brings the models closer to unification.

### Insight 10: I1 Is Log-Only = Safe to Ship and Observe
The review step in I1 produces data but doesn't gate or re-draft. This lets you verify review quality, measure cost, and tune thresholds before wiring behavioral changes in I2.

### Seed Unification Alignment

REQ-RFL-340 (Seed Unification — Shared Review-Relevant Fields) is architecturally aligned with [SEED_UNIFICATION_REQUIREMENTS.md](../SEED_UNIFICATION_REQUIREMENTS.md), which elevates seed unification from a P2/I3 afterthought to the architectural north star. All new SeedTask fields introduced by this document (quality_hints, review_constraints, review_threshold) are pipeline-agnostic by design, directly contributing to REQ-SU-301 (Consumption Contract).

**Cross-requirement consolidation (REQ-SU-200):** REQ-RFL-100, REQ-RFL-105, and REQ-RFL-115 collectively implement REQ-PC-009 (Post-Generation Validation). The Review Feedback Loop I1 is the implementation vehicle for all four requirements.

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2026-03-22 | human:neil + agent:claude-code | Initial requirements (assumed review phase in Prime) |
| 1.1.0 | 2026-03-22 | human:neil + agent:claude-code | Post-plan correction: Prime has no review phase; reframed as integration→spec feedback + quality gate |
| 2.0.0 | 2026-03-22 | human:neil + agent:claude-code | Review step via Artisan adapter (Option C), upstream amplification, seed unification alignment, iterative delivery (I1/I2/I3) |
