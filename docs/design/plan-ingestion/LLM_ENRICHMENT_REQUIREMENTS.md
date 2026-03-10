# LLM-Assisted Task Enrichment — Requirements (Option B)

> **Version:** 0.1.0
> **Status:** PLANNED
> **Date:** 2026-03-10
> **Scope:** Opt-in LLM enrichment pass for tasks that Option A could not fully populate
> **Parent:** [TASK_DENSITY_ENRICHMENT_REQUIREMENTS.md](./TASK_DENSITY_ENRICHMENT_REQUIREMENTS.md) (REQ-TDE-2xx extraction)
> **Prerequisite:** Option A (REQ-TDE-1xx) — deterministic enrichment must run first

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Architecture](#2-architecture)
3. [Functional Requirements (REQ-TDE-2xx)](#3-functional-requirements-req-tde-2xx)
4. [Configuration (REQ-TDE-3xx extension)](#4-configuration-req-tde-3xx-extension)
5. [Observability (REQ-TDE-4xx extension)](#5-observability-req-tde-4xx-extension)
6. [Status Dashboard](#6-status-dashboard)
7. [Verification Strategy](#7-verification-strategy)
8. [Risk Register](#8-risk-register)
9. [Cross-References](#9-cross-references)

---

## 1. Problem Statement

### 1.1 What Option A Cannot Do

Option A (deterministic enrichment) extracts and forwards signals that already exist in the pipeline — negative scope from ParsedFeature, REQ-* patterns from plan text, API signatures from PARSE output, REFINE suggestions. It cannot:

1. **Generate code examples** when the plan contains only prose descriptions (no API signatures parsed)
2. **Synthesize negative scope** when PARSE didn't extract explicit exclusions
3. **Map requirements to tasks** when the plan uses non-standard requirement identifiers (e.g., "Requirement 3" instead of `REQ-003`)
4. **Produce implementation hints** that require understanding of cross-task dependencies and architectural context

### 1.2 When Option B Fires

Option B runs **after** Option A, targeting only tasks that still lack density signals:

```
PARSE → ASSESS → TRANSFORM → REFINE → [ENRICH-A] → [ENRICH-B] → EMIT
                                         always        opt-in
                                         0 LLM calls   1 LLM call (batch)
```

A task needs LLM enrichment when **any** of these signals are still absent after Option A:
- `has_code_examples == False` (no ` ``` ` blocks in description)
- `has_requirements_refs == False` (no `REQ-*` patterns in description)
- `has_negative_scope == False` (empty `context.negative_scope`)

### 1.3 Cost Envelope

| Metric | Target |
|--------|--------|
| LLM calls per run | 1 (single batch) |
| Max cost per call | $0.10 (configurable) |
| Token budget | 4096 output tokens (configurable) |
| Fallback on failure | Preserve Option A results unchanged |

### 1.4 Constraints

- **Opt-in only** — disabled by default; enabled via `enrich_llm_enabled: true` or `--enrich-llm` CLI flag
- **No-clobber** — inherits REQ-TDE-106; never overwrites Option A enrichments
- **Advisory** — enrichment failure never fails the pipeline
- **Observable** — prompt/response captured via existing kaizen prompt persistence
- **Selective** — skips tasks already fully enriched by Option A

---

## 2. Architecture

### 2.1 Data Flow

```
                    ┌──────────────────────────────────┐
                    │   enrich_tasks_llm()              │
                    │                                    │
  tasks (post-A) ──→│  1. Compute TaskDensity per task   │
                    │  2. Filter: skip fully-enriched    │
                    │  3. Build batch prompt              │
                    │  4. Cost guard check                │
                    │  5. LLM call (single batch)        │
                    │  6. Parse JSON response             │
                    │  7. Merge into tasks (no-clobber)  │
                    │  8. Return LLMEnrichmentDiagnostic │
                    └──────────────────────────────────┘
```

### 2.2 Prompt Input Assembly

The batch prompt includes per-task context blocks:

```
For each task below, generate:
1. A ```{language} code example (function/class signature with docstring)
2. Requirement references (REQ-*) this task addresses
3. Negative scope: explicit "do NOT" constraints
4. Implementation hints from the architectural context

Context for all tasks:
- Project: {plan_title}
- Goals: {plan_goals}
{optional_prompt_suffix}

---
Task 1: {task_id} — {title}
Description: {task_description}
Feature: {feature_name}
API signatures: {api_signatures_if_any}
Dependencies: {dependencies}
Target files: {target_files}
Accepted REFINE suggestions: {mapped_suggestions}
---
Task 2: ...
```

### 2.3 Response Format

```json
[
  {
    "task_id": "PI-001",
    "code_example": "```python\ndef send_email(to: str, subject: str, body: str) -> bool:\n    \"\"\"Send email via SMTP backend.\"\"\"\n    ...\n```",
    "requirement_refs": ["REQ-PI-003", "REQ-PI-005"],
    "negative_scope": ["Do NOT implement authentication", "Do NOT handle attachments"],
    "implementation_hints": "Use grpcio for server setup. Health check must return HealthCheckResponse, not product IDs."
  }
]
```

### 2.4 Agent Resolution

```python
def _resolve_enrichment_agent(
    config: Dict[str, Any],
    kaizen_config: PlanIngestionKaizenConfig,
    timeout_config: Optional[TimeoutConfig] = None,
    retry_config: Optional[RetryConfig] = None,
) -> BaseAgent:
    # Priority: kaizen override > config override > TRANSFORM agent default
    spec = (
        kaizen_config.enrich_agent_spec
        or config.get("enrich_agent_spec")
        or config.get("transformer_agent")
        or Models.CLAUDE_SONNET_LATEST
    )
    return resolve_agent_spec(
        str(spec),
        name="plan-enricher",
        timeout_config=timeout_config,
        retry_config=retry_config,
    )
```

---

## 3. Functional Requirements (REQ-TDE-2xx)

### REQ-TDE-200: Enrichment Prompt Generation

When `enrich_llm_enabled` is True, the enrichment pass SHALL construct a prompt that instructs the LLM to enrich task descriptions with:

1. **Code examples** — function signatures, class skeletons, usage patterns in the task's target language (inferred from file extension or defaulting to Python)
2. **Requirement references** — `REQ-*` identifiers mapped from the plan that this task addresses
3. **Negative scope constraints** — explicit "do NOT" instructions derived from architectural context, dependencies, and cross-task boundaries
4. **Implementation hints** — derived from API signatures, dependencies, accepted REFINE suggestions, and service metadata

The prompt SHALL use `_fmt_prompt("enrich_batch", ...)` with a YAML template in `prompts/plan_ingestion.yaml` and an inline fallback string.

**Prompt suffix:** If `enrich_prompt_suffix` is non-empty in kaizen config, it SHALL be appended to the prompt. This allows operators to steer enrichment toward project-specific conventions (e.g., "All gRPC services must use `grpc.aio` async server pattern").

### REQ-TDE-201: Batch Processing

The LLM enrichment SHALL process all targeted tasks in a **single batch call** (not per-task) to minimize cost.

The batch prompt SHALL include:
- All targeted task descriptions (current state, including Option A enrichments)
- Per-task feature context: API signatures, dependencies, negative scope from ParsedFeature
- Plan excerpt: feature-relevant sections from `parsed_plan.raw_text`
- Accepted REFINE suggestions (already mapped by Option A)
- Service metadata: protocol, runtime dependencies (from `_infer_service_metadata()`)

**Token budget:** The enrichment prompt SHALL enforce a maximum output token budget via the `enrich_token_budget` config field (default: 4096). If the input prompt exceeds the model's context window minus the output budget, tasks SHALL be batched into multiple calls (ordered by task_id) with each batch staying within limits. The total cost across all batches is checked against `enrich_max_cost_usd`.

### REQ-TDE-202: Selective Enrichment

The LLM enrichment SHALL only target tasks that still lack density signals after Option A.

**Selection criteria** — a task is targeted when **any** of these conditions hold:
- `has_code_examples == False` (description lacks ` ``` ` blocks)
- `has_requirements_refs == False` (description lacks `REQ-*` patterns)
- `has_negative_scope == False` (`context.negative_scope` is empty)

Tasks where all three signals are present are fully enriched and SHALL be skipped.

**Logging:**
```
INFO  ENRICH-B: targeting 4/6 tasks (2 already enriched by Option A)
INFO  ENRICH-B: skipping PI-003, PI-005 (all density signals present)
```

### REQ-TDE-203: Response Parsing and Merge

The LLM response SHALL be parsed as a JSON array and merged into task descriptions following the **no-clobber rule** (REQ-TDE-106):

| Signal | Merge rule |
|--------|-----------|
| `code_example` | Append to `task_description` only if no ` ``` ` blocks present |
| `requirement_refs` | Append `## Requirements References` section only if no `REQ-*` patterns in description |
| `negative_scope` | Set `context.negative_scope` only if currently empty |
| `implementation_hints` | Append `## Implementation Hints (from LLM)` section (always — no conflict with Option A sections) |

**Response matching:** Each response entry SHALL be matched to a task by `task_id`. Entries with unknown `task_id` are logged at WARNING and discarded.

**Fallback behavior:**

| Failure mode | Action |
|-------------|--------|
| LLM returns empty response | Log WARNING, preserve tasks unchanged |
| Response is not valid JSON | Attempt line-by-line JSON object extraction; if still fails, log WARNING, preserve |
| Response is JSON but wrong schema | Extract available fields, skip missing ones, log WARNING per missing field |
| Response has fewer entries than tasks targeted | Enrich matched tasks, log WARNING for missing task_ids |
| LLM call raises exception | Log WARNING with exception details, preserve tasks unchanged |

The pipeline SHALL **never fail** on enrichment errors. All failures are advisory.

### REQ-TDE-204: Agent Configuration

The LLM enrichment SHALL use a configurable agent spec with this resolution order:

1. `enrich_agent_spec` in kaizen config (highest priority)
2. `enrich_agent_spec` in workflow config
3. `transformer_agent` in workflow config (same agent as TRANSFORM phase)
4. `Models.CLAUDE_SONNET_LATEST` (default fallback)

The agent spec supports all `provider:model` formats:
- `anthropic:claude-sonnet-4-6`
- `openai:gpt-4-turbo-preview`
- `ollama:startd8-coder`

The agent SHALL be created with the same `timeout_config` and `retry_config` as other pipeline phases.

### REQ-TDE-205: Cost Guard

The LLM enrichment SHALL enforce a cost ceiling **before** making the LLM call:

1. **Pre-call estimate:** Estimate cost from prompt token count using the agent's pricing model. If estimated cost exceeds `enrich_max_cost_usd`, skip enrichment entirely.
2. **Post-call check:** After the call, log actual cost. If actual cost exceeds ceiling, log WARNING (the call already happened — this is for operator awareness).
3. **Multi-batch accumulation:** If batching is required (REQ-TDE-201), accumulate cost across batches. Stop issuing further batches if cumulative cost reaches the ceiling.

**Default ceiling:** `$0.10` per enrichment run (configurable via `enrich_max_cost_usd`).

**Logging:**
```
WARNING ENRICH-B: estimated cost $0.14 exceeds ceiling $0.10 — skipping LLM enrichment
INFO    ENRICH-B: actual cost $0.07 (within $0.10 ceiling)
```

---

## 4. Configuration (REQ-TDE-3xx extension)

### REQ-TDE-301: CLI Flag

The workflow SHALL accept an `--enrich-llm` CLI flag that enables Option B.

**Mapping:**
- `--enrich-llm` → `config["enrich_llm_enabled"] = True`
- Kaizen config `enrich_llm_enabled: true` → same effect
- CLI flag takes precedence over kaizen config if both are present

**No flag for Option A:** Option A runs unconditionally (unless individual steps are disabled via kaizen config). The CLI flag only controls Option B.

### Config Fields (extension to PlanIngestionKaizenConfig)

```python
# Option B: LLM-assisted enrichment (opt-in)
enrich_llm_enabled: bool = False         # REQ-TDE-200 master switch
enrich_agent_spec: str = ""              # REQ-TDE-204 agent override (empty = use TRANSFORM agent)
enrich_max_cost_usd: float = 0.10        # REQ-TDE-205 cost ceiling
enrich_prompt_suffix: str = ""           # Custom prompt instructions appended to enrichment prompt
enrich_token_budget: int = 4096          # REQ-TDE-201 max output tokens
```

### Kaizen Config JSON

```json
{
  "plan_ingestion_kaizen": {
    "enrich_llm_enabled": true,
    "enrich_agent_spec": "anthropic:claude-sonnet-4-6",
    "enrich_max_cost_usd": 0.15,
    "enrich_prompt_suffix": "All gRPC services must use grpc.aio async server pattern.",
    "enrich_token_budget": 8192
  }
}
```

---

## 5. Observability (REQ-TDE-4xx extension)

### REQ-TDE-400 Extension: Option B Diagnostic Block

The `enrichment` section in `plan-ingestion-diagnostic.json` SHALL include an `option_b` block:

```json
{
  "enrichment": {
    "option_a": { "...": "existing fields" },
    "option_b": {
      "enabled": true,
      "tasks_targeted": 4,
      "tasks_enriched": 3,
      "tasks_skipped": 2,
      "cost_usd": 0.07,
      "time_ms": 2340,
      "agent_spec": "anthropic:claude-sonnet-4-6",
      "batches": 1,
      "skipped_reason": null,
      "parse_errors": 0,
      "fields_merged": {
        "code_examples": 3,
        "requirement_refs": 2,
        "negative_scope": 1,
        "implementation_hints": 3
      }
    }
  }
}
```

When Option B is disabled:

```json
{
  "option_b": {
    "enabled": false,
    "tasks_targeted": 0,
    "tasks_enriched": 0,
    "cost_usd": 0.0,
    "time_ms": 0,
    "skipped_reason": "disabled"
  }
}
```

When Option B is enabled but skipped due to cost guard:

```json
{
  "option_b": {
    "enabled": true,
    "tasks_targeted": 4,
    "tasks_enriched": 0,
    "cost_usd": 0.0,
    "time_ms": 0,
    "skipped_reason": "estimated_cost_exceeded",
    "estimated_cost_usd": 0.14
  }
}
```

### REQ-TDE-403: Kaizen Prompt Capture

When Option B is enabled and kaizen prompt capture is active (`--kaizen` flag), the enrichment prompt and response SHALL be persisted to:
- `kaizen-prompts/enrich_prompt.txt`
- `kaizen-prompts/enrich_response.txt`

Uses the existing `persist_prompt_response(output_dir, "enrich", prompt, response)` pattern.

### OTel Span

The LLM call SHALL be wrapped in an OTel span:

```python
with _tracer.start_as_current_span("llm.plan_ingestion.enrich") as span:
    span.set_attribute("enrich.tasks_targeted", tasks_targeted)
    span.set_attribute("enrich.agent_spec", agent_spec)
    response_text, time_ms, token_usage = agent.generate(prompt)
    span.set_attribute("enrich.cost_usd", token_usage_cost(token_usage))
    span.set_attribute("enrich.tasks_enriched", tasks_enriched)
```

---

## 6. Status Dashboard

| Req ID | Description | Status |
|--------|-------------|--------|
| REQ-TDE-200 | Enrichment prompt generation | PLANNED |
| REQ-TDE-201 | Batch processing with token budget | PLANNED |
| REQ-TDE-202 | Selective enrichment (skip fully-enriched) | PLANNED |
| REQ-TDE-203 | Response parsing and merge (no-clobber) | PLANNED |
| REQ-TDE-204 | Agent configuration (4-level resolution) | PLANNED |
| REQ-TDE-205 | Cost guard (pre-call estimate + ceiling) | PLANNED |
| REQ-TDE-301 | CLI flag `--enrich-llm` | PLANNED |
| REQ-TDE-403 | Kaizen prompt capture | PLANNED |

---

## 7. Verification Strategy

### Unit Tests

| Test | REQ | What |
|------|-----|------|
| `test_llm_enrichment_disabled_by_default` | 200 | No config → no LLM call |
| `test_llm_enrichment_enabled` | 200 | Config `enrich_llm_enabled: true` → agent.generate() called |
| `test_selective_skip_fully_enriched` | 202 | Task with all signals → skipped, not in prompt |
| `test_selective_targets_partial` | 202 | Task missing code examples → targeted |
| `test_cost_guard_blocks` | 205 | Estimated cost > ceiling → skipped with WARNING |
| `test_cost_guard_allows` | 205 | Estimated cost < ceiling → LLM called |
| `test_response_parse_valid_json` | 203 | Valid JSON array → merged into tasks |
| `test_response_parse_invalid_json` | 203 | Bad JSON → tasks unchanged, WARNING logged |
| `test_response_merge_no_clobber` | 203 | Task already has code block → LLM code_example not merged |
| `test_response_merge_hints_always` | 203 | Implementation hints section always appended |
| `test_response_missing_task_ids` | 203 | Response has fewer entries → matched tasks enriched, WARNING for missing |
| `test_prompt_suffix_appended` | 200 | `enrich_prompt_suffix` config → appears in prompt |
| `test_prompt_capture` | 403 | Kaizen enabled → prompt/response written to kaizen-prompts/ |
| `test_agent_resolution_priority` | 204 | Kaizen override > config > transformer > default |
| `test_multi_batch_cost_accumulation` | 201, 205 | Large task set → batched; stops at cost ceiling |
| `test_exception_preserves_tasks` | 203 | Agent.generate() raises → tasks unchanged |
| `test_otel_span_attributes` | — | Span has expected attributes |

### Integration Tests

| Test | What |
|------|------|
| `test_option_b_after_option_a` | Full pipeline: Option A partially enriches, Option B fills gaps |
| `test_density_score_with_option_b` | Quality score higher than Option A alone |
| `test_diagnostic_report_both_options` | Diagnostic JSON has both `option_a` and `option_b` blocks |

---

## 8. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| LLM generates incorrect code examples | Medium | Medium | Downstream DESIGN/REVIEW phases catch errors; code examples are advisory only |
| LLM halluccinates requirement refs | Medium | Low | No-clobber prevents overwriting Option A refs; fake refs produce warnings in REVIEW |
| Cost ceiling too low for large plans | Low | Low | Default $0.10 covers ~4000 output tokens at Sonnet pricing; configurable per-run |
| JSON parse failures on LLM response | Medium | Low | Multi-layer fallback (full array → line-by-line → discard); tasks always preserved |
| Prompt too large for model context | Low | Medium | Token budget enforcement; automatic batching by task count |
| Enrichment contradicts Option A results | Low | Low | No-clobber rule prevents overwrites; hints section is additive only |
| Agent unavailable (API key missing, model 404) | Low | Low | Standard agent resolution fallback chain; advisory failure mode |

---

## 9. Cross-References

| Document | Relationship |
|----------|-------------|
| [TASK_DENSITY_ENRICHMENT_REQUIREMENTS.md](./TASK_DENSITY_ENRICHMENT_REQUIREMENTS.md) | Parent: original combined requirements (Option A + B) |
| [KAIZEN_INVESTIGATION_RUN019](../kaizen/KAIZEN_INVESTIGATION_RUN019_ONLINE_BOUTIQUE.md) | Trigger: 0/6 density signals despite working REFINE |
| `plan_ingestion_enrichment.py` | Option A implementation (prerequisite; this builds on it) |
| `plan_ingestion_diagnostics.py` | Config fields, diagnostic dataclasses |
| `plan_ingestion_workflow.py` | Integration point: `_phase_emit()` after Option A call |
| `utils/agent_resolution.py` | `resolve_agent_spec()` for agent creation |
| `utils/token_usage.py` | `token_usage_cost()` for cost extraction |
| `prompts/plan_ingestion.yaml` | YAML template source (`enrich_batch` key) |
| SDK Lessons: Leg 13 #33 | Requirements layer gap — data injection ≠ prompt consumption |
| SDK Lessons: Leg 10 #31 | LLM JSON type instability guard — isinstance before string ops |
| SDK Lessons: Leg 7 #10 | Response truncation detection for large outputs |
