# Micro Prime Implementation Plan

## Context

The Micro Prime requirements (41 total across 6 layers) define a **local-first code generation engine** that routes SIMPLE elements to a tuned Ollama model (`startd8-coder`) instead of cloud models. Round 2 experiments achieved 100% syntax success and 42% verification — the remaining gap is addressed by the repair pipeline, structural verification, and escalation logic defined in these requirements.

Currently: 4 requirements are implemented (model tuning REQ-MP-100–103), 1 is partial (REQ-MP-200), and **36 are planned**. The `src/startd8/micro_prime/` package does not exist yet.

> **Status:** DRAFT — Convergent Review R1+R2 triaged (8 applied, 5 rejected)
> **Date:** 2026-03-01

**Goal:** Implement all 36 planned requirements as a new `micro_prime` package, integrated with both the Artisan workflow and Prime Contractor.

---

## Existing Assets to Reuse

| Asset | Location | Reuse |
|-------|----------|-------|
| `extract_code_from_response()` | `src/startd8/utils/code_extraction.py` | Fence stripping (REQ-MP-400) |
| `DeterministicFileAssembler` | `src/startd8/utils/file_assembler.py` | Skeleton rendering (REQ-MP-201) |
| Forward Manifest models | `src/startd8/forward_manifest.py` | Element metadata, signatures, imports |
| `ElementKind`, `Signature`, `Param` | `src/startd8/utils/code_manifest.py` | Element classification |
| `CodeGenerator` protocol | `src/startd8/contractors/protocols.py` | Prime Contractor adapter |
| `ImplementPhaseHandler` | `src/startd8/contractors/context_seed_handlers.py` | Artisan adapter integration point |
| `ArtisanChunkExecutor` | `src/startd8/contractors/artisan_phases/development.py` | Artisan tier routing |
| `ModelCatalogEntry` | `src/startd8/model_catalog.py` | Model registry (REQ-MP-104) |
| Experiment script logic | `scripts/experiment_local_model_routing.py` | Prompt building, repair steps, classification |

### Canonical Ownership Map

Each subsystem has **one canonical module**. Legacy utilities are reused via import, not duplicated.

| Responsibility | Canonical Module | Reuses From | Notes |
|---------------|-----------------|-------------|-------|
| Fence stripping | `micro_prime/repair.py` (Step 1) | `utils/code_extraction.extract_code_from_response()` | Delegates; does not re-implement |
| Over-generation trim | `micro_prime/repair.py` (Step 2) | — | New AST-based logic |
| Bare statement wrap | `micro_prime/repair.py` (Step 3) | — | New; uses manifest signatures |
| Indentation normalize | `micro_prime/repair.py` (Step 4) | — | New; uses skeleton as reference |
| Signature reconcile | `micro_prime/repair.py` (Step 5) | `utils/code_manifest.Signature` | Consumes model; logic is new |
| Import completion | `micro_prime/repair.py` (Step 6) | — | New; uses manifest import list |
| Skeleton rendering | `utils/file_assembler.DeterministicFileAssembler` | — | Unchanged; consumed by engine |
| Body splicing | `micro_prime/splicer.py` | — | New; operates on assembler output |
| Template matching | `micro_prime/templates.py` | `utils/code_manifest.ElementKind` | Consumes model; logic is new |
| Tier classification | `micro_prime/classifier.py` | `forward_manifest.ForwardElementSpec` | Consumes model; logic is new |

---

## Phase 1: Foundation — Template Registry + Repair Pipeline

**Requirements:** REQ-MP-300–304 (Templates), REQ-MP-400–407 (Repair)

These two subsystems are independent and can be built in parallel.

### Phase 1A: Template Registry (`~15 tests`)

**New file:** `src/startd8/micro_prime/templates.py`

- `TemplateRegistry` class with `match(element) -> Optional[str]` (REQ-MP-300)
- Built-in templates for `__init__`, `__repr__`, `__str__`, `__eq__`, `__hash__`, constants (REQ-MP-301)
- Async-aware: check `element.kind` for `ASYNC_FUNCTION`/`ASYNC_METHOD` (from `ElementKind` enum) and emit `async def` accordingly — no `is_async` boolean exists on `ForwardElementSpec`
- Template selection criteria using manifest metadata (element kind, body complexity) (REQ-MP-302)
- Bypass flag: `templates_enabled` config toggle (REQ-MP-303)
- Template validation: output must pass `ast.parse()` (REQ-MP-304)

### Phase 1B: Repair Pipeline (`~25 tests`)

**New file:** `src/startd8/micro_prime/repair.py`

7-step ordered pipeline, each step is a function `(code: str, element: ManifestElement) -> RepairStepResult`:

1. **Fence stripping** — delegate to existing `extract_code_from_response()` (REQ-MP-400)
2. **Over-generation trim** — AST parse, remove nodes not matching target FQN (REQ-MP-401)
3. **Bare statement wrapping** — detect body-only output, wrap in manifest's `def` line (REQ-MP-407)
4. **Indentation normalize** — re-indent to 4-space using skeleton as reference (REQ-MP-402)
5. **Signature reconcile** — diff params/return type against manifest, restore canonical (REQ-MP-403)
6. **Import completion** — add missing imports from manifest's import list (REQ-MP-404)
7. **AST validation** — `ast.parse()` gate, rollback if step made valid→invalid (REQ-MP-405)

**Key constraint:** Non-destructive guarantee (REQ-MP-406) — each step checks AST validity before/after; if a step breaks valid code, its changes are reverted.

**Implementation pattern:** `@repair_step` decorator/context manager wraps each step with attempt→verify→rollback logic. Centralizes the REQ-MP-406 guarantee so individual steps don't duplicate the before/after AST check boilerplate.

**New dataclass:** `RepairStepResult(modified: bool, code: str, metrics: dict)` — per-step attribution for REQ-MP-601.

---

## Phase 2: Skeleton-First Prompting + Body Splicing

**Requirements:** REQ-MP-200–205

**Depends on:** Phase 1B (repair pipeline for post-splice validation)

### New files

**`src/startd8/micro_prime/prompt_builder.py`** (`~12 tests`)

- `build_body_prompt(element, manifest, skeleton)` — constructs the local model prompt (REQ-MP-200)
- Skeleton context injection: surrounding methods, class docstring, imports (REQ-MP-201)
- Body-only instruction: "Fill in ONLY the function body" with signature echo (REQ-MP-202)
- Few-shot examples: 1-2 similar completed elements from same file (REQ-MP-203)
- Constant/variable prompts: "Output ONLY the assignment" (REQ-MP-204)
- Prompt token budget: hard cap at 1024 tokens input (REQ-MP-205)

**`src/startd8/micro_prime/splicer.py`** (`~8 tests`)

- `splice_body_into_skeleton(body: str, element: ManifestElement, skeleton: str) -> str`
- Locates the `raise NotImplementedError` stub in the skeleton
- Replaces with repaired body, preserving surrounding code
- Validates spliced file passes `ast.parse()`

---

## Phase 3: Engine, Models, Classifier, Observability

**Requirements:** REQ-MP-104, REQ-MP-500–512, REQ-MP-600–603

**Depends on:** Phases 1 and 2

### New files

**`src/startd8/micro_prime/models.py`** — Pydantic models

- `MicroPrimeConfig` — engine configuration:
  - Model settings: `model`, `temperature`, `templates_enabled`, `repair_enabled`
  - Runtime resource controls: `max_concurrent_generations` (default 1 — sequential, safe for laptops), `per_element_timeout_s` (default 30), `queue_overflow_policy` (`"escalate"` | `"drop"`) — on timeout or queue saturation, elements escalate to cloud rather than blocking
- `MicroPrimeElementMetrics` — per-element metrics (REQ-MP-600)
- `MicroPrimeCostReport` — cost accounting (REQ-MP-602)
- `TierClassification` enum — `TRIVIAL | SIMPLE | MODERATE | COMPLEX`
- `EscalationResult` — escalation reason + context for cloud retry

**`src/startd8/micro_prime/classifier.py`** (`~15 tests`)

- `classify_element(element, manifest) -> TierClassification` (REQ-MP-500)
- TRIVIAL gate: element matches template registry (REQ-MP-500a)
- SIMPLE gate: element has ≤N unique imports, all from manifest's known set (REQ-MP-501)
- Per-element API dependency analysis: two-pass algorithm (REQ-MP-511)
  - Pass 1: file-level import gate (reject if file imports unknown APIs)
  - Pass 2: per-element binding constraint check (docstring hints, name patterns, import usage)
- MODERATE/COMPLEX: passthrough to existing cloud routing

**`src/startd8/micro_prime/engine.py`** (`~15 tests`)

- `MicroPrimeEngine` — main orchestrator class
  - `process_element(element, manifest, skeleton) -> ElementResult`
  - `process_file(file_elements, manifest) -> FileResult`
  - `process_seed(all_elements, manifest) -> SeedResult`
- Pipeline per element:
  1. Classify tier
  2. TRIVIAL → template registry → splice → done
  3. SIMPLE → prompt builder → Ollama inference → repair pipeline → structural verify → splice or escalate
  4. MODERATE/COMPLEX → return as `needs_cloud` for caller to handle
- Verification-gated escalation (REQ-MP-512): AST validate → structural verify → accept or batch-escalate
- Ollama invocation via existing `OllamaProvider` (REQ-MP-502)
- **Mixed-tier merge contract**: The skeleton file is the merge anchor. Micro Prime fills TRIVIAL/SIMPLE stubs in-place (replacing `raise NotImplementedError`). Remaining stubs stay as-is for the cloud executor. The cloud executor operates on the *same skeleton file*, filling its assigned stubs. Since each element occupies a distinct stub location, there is no merge conflict — elements are slot-addressed, not appended. Integration test: one file with both local-filled and cloud-filled elements must produce deterministic output.

**`src/startd8/micro_prime/metrics.py`** (`~8 tests`)

- `MetricsCollector` — accumulates per-element metrics during engine run
- `generate_cost_report(metrics, config) -> MicroPrimeCostReport` (REQ-MP-602)
- `generate_experiment_result(metrics, config, run_id) -> dict` — JSON schema v1.0.0 (REQ-MP-603)

### Modified file

**`src/startd8/model_catalog.py`** — Add `startd8-coder` entry (REQ-MP-104)

- Context window: 32,768
- Default max_tokens: 512
- Provider: ollama

---

## Phase 4: Workflow Integration Adapters

**Requirements:** REQ-MP-503–510

**Depends on:** Phase 3

### New files

**`src/startd8/micro_prime/artisan_adapter.py`** (`~8 tests`)

- `MicroPrimePrePass` — runs before `ArtisanChunkExecutor` processes chunks
- Input: skeleton files + manifest from SCAFFOLD phase
- Output: skeletons with TRIVIAL/SIMPLE bodies filled in + list of remaining MODERATE/COMPLEX chunks
- Escalated elements added back to chunk list with `last_error` context (REQ-MP-506)
- Wired into `development.py` via a config flag `micro_prime_enabled` (REQ-MP-503)
- Cost savings summary: log `"Micro Prime saved $X.XX (N TRIVIAL + M SIMPLE elements handled locally)"` at end of pre-pass

**`src/startd8/micro_prime/prime_adapter.py`** (`~9 tests`)

- `MicroPrimeCodeGenerator(CodeGenerator)` — implements the `CodeGenerator` protocol
- `generate(task, context, target_files) -> GenerationResult`
- Wraps `MicroPrimeEngine.process_file()` → returns `GenerationResult` with filled skeleton
- For MODERATE/COMPLEX elements, delegates to a fallback `CodeGenerator` (REQ-MP-504)
- **Ollama availability guard**: Before invoking engine, check Ollama reachability (mirrors `_check_ollama_model()` pattern from `preflight.py`). If unavailable, route all SIMPLE elements to fallback without hard failure.

### Rollout Controls

- **Default off**: `micro_prime_enabled` defaults to `false` in both Artisan config and Prime config
- **Single config-only rollback**: Setting `micro_prime_enabled=false` disables all Micro Prime routing — existing cloud-only behavior is fully preserved with no code changes
- **Graceful degradation**: If Ollama is unavailable at runtime, all elements route to cloud (no failure, just cost savings lost)

### Modified files

**`src/startd8/contractors/artisan_phases/development.py`** (~20 lines)

- Add `micro_prime_enabled` config check in `ArtisanChunkExecutor`
- If enabled, call `MicroPrimePrePass.run()` before the main generation loop
- Filter out already-filled elements from chunk list

**`src/startd8/contractors/context_seed_handlers.py`** (~20 lines)

- `ImplementPhaseHandler`: forward `micro_prime_enabled` config to `DevelopmentPhase`
- Pass manifest path from context for the pre-pass

---

## Phase 5: Experiment Script Refactor + E2E Validation

**Depends on:** Phase 4

### Modified file

**`scripts/experiment_local_model_routing.py`**

- Refactor to use `MicroPrimeEngine` instead of inline logic
- Keep as a standalone experiment runner but delegate to SDK classes
- Add `--use-sdk-engine` flag for A/B comparison during transition

### New files

**`tests/unit/micro_prime/`** — unit tests for all modules (created during each phase)

**`tests/integration/test_micro_prime_e2e.py`** (`~5 tests`)

- Full pipeline test: manifest → classify → template/generate → repair → splice → validate
- Mock Ollama responses for deterministic testing
- Verify metrics collection and cost report generation

---

## Package Structure (final)

```
src/startd8/micro_prime/
├── __init__.py          # Public API: MicroPrimeEngine, MicroPrimeConfig
├── models.py            # Pydantic models, enums, dataclasses
├── classifier.py        # Tier classification + API dependency analysis
├── templates.py         # Template registry for TRIVIAL elements
├── repair.py            # 7-step manifest-guided repair pipeline
├── prompt_builder.py    # Skeleton-first prompt construction
├── splicer.py           # Body splicing into skeleton files
├── engine.py            # Main orchestrator
├── metrics.py           # Metrics collection + cost reporting
├── artisan_adapter.py   # Artisan IMPLEMENT phase pre-pass
└── prime_adapter.py     # CodeGenerator protocol implementation
```

**11 new files**, **3 modified files** (`model_catalog.py`, `development.py`, `context_seed_handlers.py`), **~105 tests**

---

## Verification Plan

1. **Unit tests per phase** — run `pytest tests/unit/micro_prime/ -v` after each phase
2. **Integration test** — `pytest tests/integration/test_micro_prime_e2e.py -v` after Phase 4
3. **Experiment script A/B** — run `scripts/experiment_local_model_routing.py` with `--use-sdk-engine` flag against `online-boutique-demo` seed, verify metrics match or improve Round 2 results (100% syntax, ≥42% verification)
4. **Existing test suite** — `pytest` full suite must pass (no regressions)
5. **Type checking** — `mypy src/startd8/micro_prime/` passes
6. **Lint** — `ruff check src/startd8/micro_prime/` passes

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal - suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-S1 | Canonical ownership map for template/repair logic | codex (gpt-5) | Added "Canonical Ownership Map" table to Existing Assets section. Each subsystem maps to one module; legacy utils are consumed via import, not duplicated. | 2026-03-01 |
| R1-S2 | Mixed-tier merge contract for partial local/cloud file assembly | codex (gpt-5) | Added merge contract to Phase 3 `engine.py` section. Skeleton is the merge anchor — elements are slot-addressed (each fills a distinct `raise NotImplementedError` stub), so no merge conflict. Integration test specified. | 2026-03-01 |
| R1-S4 | Staged rollout controls with default-off and config-only rollback | codex (gpt-5) | Added "Rollout Controls" subsection to Phase 4: `micro_prime_enabled` defaults `false`, single-config rollback, graceful Ollama degradation. | 2026-03-01 |
| R1-S6 | Runtime resource controls (concurrency, timeout, queue overflow) | codex (gpt-5) | Added `max_concurrent_generations`, `per_element_timeout_s`, `queue_overflow_policy` to `MicroPrimeConfig` in Phase 3. Default sequential (1) for laptop safety; timeout escalates to cloud. | 2026-03-01 |
| R1-S8 | Ollama availability guard in Prime adapter | codex (gpt-5) | Added Ollama reachability check to `prime_adapter.py` mirroring `preflight.py` `_check_ollama_model()` pattern. Unavailable → route all to fallback, no hard failure. | 2026-03-01 |
| R2-S1 | `is_async` awareness in Template Registry | Antigravity | Added async-aware template matching to Phase 1A. Uses `ElementKind` enum (`ASYNC_FUNCTION`/`ASYNC_METHOD`) — no `is_async` boolean exists on `ForwardElementSpec`. | 2026-03-01 |
| R2-S2 | Cost reduction visualization in Artisan adapter | Antigravity | Added cost savings summary log line to `artisan_adapter.py`: `"Micro Prime saved $X.XX (N TRIVIAL + M SIMPLE elements handled locally)"`. | 2026-03-01 |
| R2-S3 | Step rollback as shared decorator/context manager | Antigravity | Added `@repair_step` decorator pattern to Phase 1B. Centralizes attempt→verify→rollback logic for REQ-MP-406 non-destructive guarantee. | 2026-03-01 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R1-S3 | Per-REQ traceability table in the plan | codex (gpt-5) | Already exists: `MICRO_PRIME_REQUIREMENTS.md` Section 11 (Traceability Matrix) maps every REQ-MP to implementation file and test file. Duplicating in the plan creates maintenance burden with no audit benefit. | 2026-03-01 |
| R1-S5 | Phase exit gates with measurable thresholds | codex (gpt-5) | Premature. Requirements Section 1.3 defines success criteria; the Verification Plan Phase 5 runs A/B comparison against Round 2 baselines (100% syntax, ≥42% verification). Adding CI gate thresholds before we have real SDK-engine metrics would be arbitrary. Will revisit after Phase 5 data. | 2026-03-01 |
| R1-S7 | Prompt/telemetry sanitization for secrets | codex (gpt-5) | Low risk. The pipeline processes code scaffolds generated from manifests — not user-supplied data, credentials, or PII. Prompts contain function signatures, imports, and skeleton context from the project's own codebase. Standard `get_logger()` practices apply. | 2026-03-01 |
| R2-S4 | RequirementStatus tracker in metrics | Antigravity | Requirements are design-time artifacts, not runtime entities. Experiment results already show which tiers and repair steps were exercised per run. Tracking REQ IDs at runtime conflates specification with instrumentation. | 2026-03-01 |
| R2-S5 | Project scaffolding detection for Prime adapter | Antigravity | Tier classification operates at **element level** using manifest metadata and complexity analysis (REQ-MP-500/501/511), not at project level. Whether a project is "scaffolded core" or "feature code" is irrelevant — each element is independently classified by its imports, signature, and body complexity. The classifier works identically on new and existing projects. | 2026-03-01 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

- **Reviewer**: codex (gpt-5)
- **Date**: 2026-03-01 19:12:31 UTC
- **Scope**: Implementation-plan review for execution sequencing, cross-workflow contract fidelity, and operational readiness

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | Add a migration map that declares canonical ownership for template/repair logic and explicitly deprecates or wraps overlapping legacy utils modules. | The plan both reuses existing utilities and introduces new modules with similar responsibilities; without an ownership map, duplication drift is likely. | Phase 1 and Package Structure sections | Verify each subsystem (templates, repair, splicing) has one canonical module and any compatibility wrappers are time-bounded. |
| R1-S2 | Interfaces | high | Define the merge contract for mixed-tier file assembly when Prime fallback generation returns content for escalated elements in files already partially filled by Micro Prime. | The plan states fallback occurs for MODERATE/COMPLEX but does not define deterministic merge behavior for partial local/cloud outcomes. | Phase 3 `engine.py` and Phase 4 `prime_adapter.py` | Add an integration test where one file has both local and fallback-generated elements and assert deterministic final output. |
| R1-S3 | Data | medium | Add a per-REQ traceability table in the plan (REQ-MP-100..603) mapping each requirement to phase step, file, and test owner. | Current phase grouping obscures coverage at individual requirement granularity and makes audit/review expensive. | New section after phase overview | Verify every REQ-MP id appears exactly once with implementation and validation targets. |
| R1-S4 | Risks | high | Add staged rollout controls: default `micro_prime_enabled=false`, pilot allowlist (seed/service), and rollback switch for both Artisan and Prime paths. | The plan introduces major routing behavior changes across two workflows but lacks an explicit deployment safety strategy. | Phase 4 and Verification Plan | Validate one config-only rollback path disables Micro Prime without code changes and preserves existing behavior. |
| R1-S5 | Validation | high | Convert success criteria into explicit phase exit gates (latency, verification rate, cost reduction) with pass/fail thresholds tied to REQ metrics. | The plan references experiment targets but does not gate phase completion on measurable thresholds. | End of each phase + Verification Plan | Verify CI/reporting emits threshold checks and blocks promotion when metrics regress. |
| R1-S6 | Ops | high | Add runtime resource controls in implementation scope: max concurrent local generations, per-element timeout budget, and queue overflow policy. | Operational constraints are required to keep local inference predictable in CI and developer laptops. | Phase 3 `engine.py` and config model | Load tests should confirm bounded concurrency and deterministic fallback on timeout/queue saturation. |
| R1-S7 | Security | medium | Add explicit sanitization steps for prompt context and telemetry payloads before logging, metric export, or escalation to cloud prompts. | Existing files and domain constraints can contain sensitive strings; the plan currently lacks data-handling controls. | Phase 3 `metrics.py`, Phase 4 adapters, Verification Plan | Add redaction tests with synthetic secrets and assert no raw secret values appear in logs/results/prompts. |
| R1-S8 | Interfaces | medium | Add a Prime-path equivalent for Ollama availability/degradation behavior instead of relying on Artisan preflight assumptions. | REQ-MP-503 is reflected in Artisan integration, but the plan does not clearly show the same guard in `MicroPrimeCodeGenerator`. | Phase 4 `prime_adapter.py` | Add tests where Prime mode runs with Ollama unavailable and routes SIMPLE elements to fallback without hard failure. |

#### Review Round R2

- **Reviewer**: Antigravity
- **Date**: 2026-03-01
- **Scope**: Implementation plan review for alignment with refined requirements and operational observability.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Templates | medium | Add `is_async` awareness to Phase 1A (Template Registry). | To support R2-S1 in requirements, the template matching and rendering logic must explicitly check the `is_async` property of the `ForwardElementSpec`. | Phase 1A `templates.py` | Unit tests for `match_fn` and `render_fn` with async inputs. |
| R2-S2 | Observability| medium | Add "Cost Reduction" visualization to the Artisan adapter. | Users should see the value of Micro Prime in the TUI/logs. The adapter should compute and log the delta between local (free) and estimated cloud cost. | Phase 4 `artisan_adapter.py` | Verify "Micro Prime saved $X.XX" appears in the workflow logs/summary. |
| R2-S3 | Repair | low | Implement "Step Rollback" as a shared decorator or context manager in Phase 1B. | To enforce the non-destructive guarantee (REQ-MP-406), a shared mechanism for "attempt-verify-rollback" will prevent duplicate boilerplate in each repair step. | Phase 1B `repair.py` | Ensure a failing repair step does not mutate the code string passed to the next step. |
| R2-S4 | Lifecycle | low | Add a `RequirementStatus` tracker to the metrics system. | To support the retirement policy (R2-S4 in requirements), the metrics should report which REQs were exercised, skipped, or marked as superseded during a run. | Phase 3 `metrics.py` | Verify the experiment result JSON contains a dictionary of REQ ids and their runtime status. |
| R2-S5 | Integration | high | Define the "Project Scaffolding" detection logic for the Prime adapter. | Prime Contractor often runs on existing projects. The adapter needs a reliable way to distinguish "scaffolded core" from "feature code" to apply TRIVIAL/SIMPLE routing correctly. | Phase 4 `prime_adapter.py` | Integration test with an existing project where core files are skipped by Micro Prime. |

#### Review Round R3

- **Reviewer**: codex (gpt-5)
- **Date**: 2026-03-01 21:08:26 UTC
- **Scope**: Novel low-hanging fruit with outsized value, de-duplicated against REQ-MP-7xx and prior rounds

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | Interfaces | high | Extend `classifier.py` and `metrics.py` with `classification_reason_codes` and persist them in experiment output. | This is a small data-shape extension with outsized debugging value for routing mistakes and tuning loops. | Phase 3 `classifier.py`, `models.py`, `metrics.py` | Verify each element result includes at least one reason code and that reason codes are stable across identical runs. |
| R3-S2 | Ops | high | Implement a `local_failure_circuit_breaker` in `engine.py` with config defaults (`trip_after_consecutive_failures`, optional cooldown). | Lightweight protection against pathological runs where local generation repeatedly fails, reducing wasted latency and preserving throughput. | Phase 3 `engine.py` + `models.py` config | Simulate consecutive local failures and assert breaker trips, routing remaining SIMPLE elements to cloud for the run. |
| R3-S3 | Validation | high | Add a reusable `build_escalation_context()` helper that enforces token budget and context-priority ordering before fallback calls. | Small helper centralizes escalation quality and prevents oversized fallback prompts from increasing cost and variance. | Phase 3 `engine.py` or new `escalation.py`; Phase 4 adapters call site | Unit test payload trimming order and integration test that fallback prompts stay within configured budget. |
| R3-S4 | Data | medium | Add a strict element-fingerprint cache (`success_cache`) for successful SIMPLE outputs to skip duplicate local inference on unchanged inputs. | High leverage for iterative runs and retries with minimal implementation complexity (hash + dict/file-backed cache). | Phase 3 `engine.py` + optional cache persistence in `models.py` config | Re-run identical input and confirm cache hit path avoids local model call while assembled output remains byte-equivalent. |
| R3-S5 | Validation | medium | Add a compact golden-corpus test suite (10-20 representative elements) and run it in CI as a fast regression gate. | Very small fixture set provides outsized protection against routing/repair regressions before broader integration runs. | Phase 5 tests (`tests/integration/test_micro_prime_golden_corpus.py`) + CI step | Verify corpus expectations (tier, AST validity, escalation behavior) and fail fast on drift. |
