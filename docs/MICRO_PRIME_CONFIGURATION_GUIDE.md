# Micro Prime Configuration Guide

Micro Prime is StartD8's local code generation engine. It generates Python code element-by-element or file-at-a-time using a local Ollama model, with optional escalation to a cloud LLM when local generation fails.

## Configuration File

**Location:** `.startd8/micro_prime.json` in your project root.

Created automatically by `startd8 init` or manually. If missing, all defaults apply.

### Structure

```json
{
  "cloud_agent_spec": "anthropic:claude-haiku-4-5-20251001",
  "config": {
    "model": "startd8-coder",
    "provider": "ollama",
    "temperature": 0.1,
    "max_tokens": 2048
  }
}
```

- **`cloud_agent_spec`** (top-level, optional): The `provider:model` agent spec used for cloud escalation. Not part of `MicroPrimeConfig`; extracted separately by the config loader.
- **`config`** (nested block): All `MicroPrimeConfig` fields go here.
- Top-level keys (outside `config`) override nested values if both are present.
- Unknown keys are logged as warnings and ignored.
- Parse errors fall back to defaults without crashing.

## Configuration Reference

### Core Generation

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `model` | string | `"startd8-coder"` | Ollama model name. Must be pulled locally via `ollama pull`. |
| `provider` | string | `"ollama"` | LLM provider. Currently only `"ollama"` is used for local generation. |
| `temperature` | float | `0.1` | Generation temperature. Lower = more deterministic. |
| `max_tokens` | int | `2048` | Maximum output tokens per generation call. |
| `input_token_budget` | int | `1024` | Token budget for input context (prompt + skeleton + few-shot). |
| `dry_run` | bool | `false` | When true, classifies elements but skips actual generation. Useful for previewing tier routing. |

### Generation Paths

Micro Prime has two generation strategies. File-whole is the **primary** path; element-by-element is the fallback.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `file_ollama_whole_enabled` | bool | `true` | Generate the entire file skeleton in a single Ollama call. This is the preferred path — it avoids the information loss of element-by-element splitting. |
| `file_ollama_whole_max_elements` | int | `60` | Files with more elements than this fall through to element-by-element. |
| `file_ollama_whole_max_loc` | int | `600` | Files with more skeleton lines than this fall through to element-by-element. Proxy for context window limits. |
| `min_element_fill_rate` | float | `0.5` | Minimum fraction of elements that must be successfully filled for a file-whole result to be accepted (0.0–1.0). |
| `moderate_ollama_whole_enabled` | bool | `true` | Attempt file-whole for MODERATE-tier elements before falling back to decomposition. |
| `moderate_ollama_whole_skip_signals` | set | `["external_api", "orchestrator", "app_server_instance"]` | Complexity signals that skip MODERATE file-whole and go straight to decomposition or escalation. |

### Feature Toggles

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `templates_enabled` | bool | `true` | Use template matching for TRIVIAL elements (e.g., `__init__`, `__repr__`, simple getters). No LLM call needed. |
| `repair_enabled` | bool | `true` | Run the post-generation repair pipeline (syntax fixes, import completion, lint repair). |
| `few_shot_enabled` | bool | `true` | Inject few-shot examples from previously generated elements into prompts. |
| `max_few_shot_examples` | int | `2` | Maximum few-shot examples per element prompt. |
| `escalation_enabled` | bool | `true` | Allow escalation to a cloud LLM when local generation fails. Set to `false` for fully offline operation. |

### Escalation

When local Ollama generation fails (syntax errors, missing elements, validation failures), Micro Prime can escalate to a cloud model.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `local_max_attempts` | int | `2` | Maximum Ollama attempts per element before escalating. Range: 1–10. |
| `cloud_escalation_max_attempts` | int | `3` | Maximum cloud LLM attempts after escalation. |
| `cloud_escalation_retry_strategy` | string | `"same_prompt"` | How to retry cloud calls. Currently only `"same_prompt"` is supported. |
| `cloud_escalation_retry_max_chars` | int | `512` | Maximum characters of error context included in cloud retry prompts. |
| `external_api_packages` | list | *(see below)* | Import packages that trigger immediate escalation to cloud. Elements importing these are too complex for local models. |

**Default `external_api_packages`:**
```
grpc, grpcio, httpx, aiohttp, requests, flask, fastapi, django, starlette,
jinja2, mako, google.cloud, google.auth, google.api_core, boto3, botocore,
azure, sqlalchemy, alembic, asyncpg, psycopg2, celery, redis, kombu,
locust, playwright
```

### Semantic Verification

Optional LLM-based verification that generated code matches the element's contract (signature, docstring intent).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `semantic_verification_enabled` | bool | `true` | Enable semantic verification after generation. |
| `semantic_verification_agent_spec` | string\|null | `null` | Cloud agent spec for verification (e.g., `"anthropic:claude-haiku-4-5-20251001"`). Uses the escalation agent if null. |
| `semantic_verification_max_tokens` | int | `256` | Token limit for verification responses. |
| `semantic_verification_temperature` | float | `0.0` | Temperature for verification (0.0 = deterministic). |
| `semantic_verification_prompt_max_chars` | int | `4000` | Maximum characters in the verification prompt. |

### Classifier Thresholds

Controls how elements are classified into complexity tiers (TRIVIAL / SIMPLE / MODERATE / COMPLEX).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_simple_imports` | int | `8` | Elements with more imports than this are classified above SIMPLE. |
| `max_simple_params` | int | `4` | Elements with more parameters than this are classified above SIMPLE. |
| `class_score_bonus` | int | `1` | Bonus complexity points for class elements. |
| `simple_threshold` | int | `0` | Base complexity score threshold for SIMPLE tier. |
| `docstring_length_threshold` | int | `200` | Docstring length (chars) used as a complexity heuristic. |

### Decomposer

Decomposition breaks MODERATE elements into SIMPLE sub-elements. It is a **fallback path** — file-whole and cloud escalation are preferred. Decomposition adds significant complexity (decomposer + splicer + element repair).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `decomposition_enabled` | bool | `false` | Enable MODERATE element decomposition. Off by default; file-whole handles most cases. |
| `max_sub_elements` | int | `5` | Maximum sub-elements per decomposition. |
| `max_helpers_per_function` | int | `4` | Maximum helper functions generated per function decomposition. |
| `decomposition_confidence_threshold` | float | `0.6` | Minimum decomposer confidence to proceed (0.0–1.0). Below this, the element escalates instead. |
| `class_decompose_enabled` | bool | `true` | Enable class decomposition strategy (split class into methods). |
| `function_chain_enabled` | bool | `true` | Enable function chain decomposition strategy. |
| `enable_simple_decomposer` | bool | `true` | Enable function-body decomposer for SIMPLE tier elements. |
| `simple_decomposer_confidence_threshold` | float | `0.7` | Confidence threshold for simple decomposer. |

### Recursive Decomposition

Experimental. Allows decomposed sub-elements to be further decomposed.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `recursion_enabled` | bool | `false` | Enable recursive decomposition. |
| `recursion_max_depth` | int | `2` | Maximum recursion depth. |
| `recursion_max_sub_elements_total` | int | `8` | Maximum total sub-elements across all recursion levels. |
| `recursion_max_llm_calls` | int | `3` | Maximum LLM calls during recursive decomposition. |
| `recursion_monotonicity` | string | `"strict_tier_decrease"` | Enforce that each recursion level produces simpler tiers. |
| `orchestrator_decomp_max_external_deps` | int | `3` | Maximum external dependencies for orchestrator decomposition. |

## Common Configurations

### Fully Offline (No Cloud)

```json
{
  "config": {
    "model": "startd8-coder",
    "escalation_enabled": false,
    "semantic_verification_enabled": false
  }
}
```

### Fast Iteration (Skip Verification)

```json
{
  "cloud_agent_spec": "anthropic:claude-haiku-4-5-20251001",
  "config": {
    "semantic_verification_enabled": false,
    "local_max_attempts": 1,
    "cloud_escalation_max_attempts": 1
  }
}
```

### Maximum Quality (All Features)

```json
{
  "cloud_agent_spec": "anthropic:claude-sonnet-4-20250514",
  "config": {
    "semantic_verification_enabled": true,
    "semantic_verification_agent_spec": "anthropic:claude-haiku-4-5-20251001",
    "repair_enabled": true,
    "few_shot_enabled": true,
    "decomposition_enabled": true,
    "local_max_attempts": 2,
    "cloud_escalation_max_attempts": 3
  }
}
```

### Dry Run (Classification Only)

```json
{
  "config": {
    "dry_run": true
  }
}
```

## Generation Flow

```
File → file-whole eligible?
  ├─ YES → Ollama file-whole (single call)
  │         ├─ fill rate ≥ min_element_fill_rate → success
  │         └─ fill rate too low → fall through
  └─ NO (or file-whole failed)
      → Element-by-element:
          Element → classify tier
            ├─ TRIVIAL → template match (no LLM)
            ├─ SIMPLE → Ollama body generation
            │            ├─ success → splice into skeleton
            │            └─ fail (×local_max_attempts) → escalate to cloud
            ├─ MODERATE → Ollama-whole attempt (if enabled)
            │              ├─ success → done
            │              └─ fail → decompose (if enabled) or escalate
            └─ COMPLEX → escalate to cloud immediately
```

## File Location

The config loader (`micro_prime/config_loader.py`) looks for:

```
<project_root>/.startd8/micro_prime.json
```

The project root is determined by the PrimeContractor workflow context. If the file is missing, all defaults apply. Loading errors are logged as warnings but never crash the pipeline.

## Related Documentation

- [Prime Contractor Workflow Guide](PRIME_CONTRACTOR_WORKFLOW_GUIDE.md) — how Micro Prime fits into the batch generation pipeline
- [Agent Configuration Guide](AGENT_CONFIGURATION_GUIDE_v1.md) — agent spec format (`provider:model`)
- `docs/design/micro-prime/MICRO_PRIME_REQUIREMENTS.md` — design specifications (REQ-MP-xxx)
