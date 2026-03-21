# Prime Contractor Configuration Reference

## Overview

The Prime Contractor reads configuration from `prime-contractor.json` in the project's `.startd8/` directory. CLI arguments override config file values. All sections are optional; missing sections use defaults.

## Configuration File Location

```
{project_root}/.startd8/prime-contractor.json
```

Or specify explicitly: `--config /path/to/config.json`

Resolution order:
1. Explicit `--config` path (CLI argument)
2. `.startd8/prime-contractor.json` in project root
3. Default config (all defaults)

## Complete Schema

### `micro_prime`

Controls the Micro Prime local-first code generation engine (Ollama-based). When enabled, SIMPLE and MODERATE elements are generated locally before falling back to cloud LLM.

Source: `src/startd8/micro_prime/models.py` (`MicroPrimeConfig`)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `false` | Master switch for Micro Prime engine |
| `model` | str | `"startd8-coder"` | Ollama model name for local generation |
| `provider` | str | `"ollama"` | Provider backend for local generation |
| `temperature` | float | `0.1` | Sampling temperature for local model |
| `max_tokens` | int | `2048` | Max output tokens per generation call |
| `input_token_budget` | int | `1024` | Max input tokens per prompt |
| `templates_enabled` | bool | `true` | Enable template-based generation for TRIVIAL elements |
| `repair_enabled` | bool | `true` | Enable post-generation repair pipeline |
| `few_shot_enabled` | bool | `true` | Include few-shot examples in prompts |
| `max_few_shot_examples` | int | `2` | Max few-shot examples to include |
| `escalation_enabled` | bool | `true` | Allow escalation from local to cloud model |
| `local_max_attempts` | int | `2` | Max Ollama generation attempts before escalation (1-10) |
| `cloud_escalation_max_attempts` | int | `3` | Max cloud retry attempts after local failure |
| `cloud_escalation_retry_strategy` | str | `"same_prompt"` | Cloud retry strategy |
| `cloud_escalation_retry_max_chars` | int | `512` | Max chars for cloud retry context |
| `semantic_verification_enabled` | bool | `true` | Enable LLM-based semantic verification |
| `semantic_verification_agent_spec` | str\|null | `null` | Agent spec for verification (null = use default) |
| `semantic_verification_max_tokens` | int | `256` | Max tokens for verification response |
| `semantic_verification_temperature` | float | `0.0` | Temperature for verification (deterministic) |
| `semantic_verification_prompt_max_chars` | int | `4000` | Max chars for verification prompt |
| `dry_run` | bool | `false` | Simulate generation without calling models |
| `max_simple_imports` | int | `8` | Classifier: max imports for SIMPLE tier |
| `max_simple_params` | int | `4` | Classifier: max parameters for SIMPLE tier |
| `class_score_bonus` | int | `1` | Classifier: bonus score for class elements |
| `simple_threshold` | int | `0` | Classifier: score threshold for SIMPLE tier |
| `docstring_length_threshold` | int | `200` | Classifier: docstring length influencing tier |
| `decomposition_enabled` | bool | `false` | Enable element decomposition (fallback path) |
| `max_sub_elements` | int | `5` | Max sub-elements per decomposition |
| `max_helpers_per_function` | int | `4` | Max helper functions per decomposed function |
| `decomposition_confidence_threshold` | float | `0.6` | Min confidence to accept decomposition |
| `class_decompose_enabled` | bool | `true` | Allow class-level decomposition |
| `function_chain_enabled` | bool | `true` | Allow function chain decomposition |
| `enable_simple_decomposer` | bool | `true` | Enable simple decomposer gate |
| `simple_decomposer_confidence_threshold` | float | `0.7` | Confidence threshold for simple decomposer |
| `recursion_enabled` | bool | `false` | Enable recursive decomposition |
| `recursion_max_depth` | int | `2` | Max recursion depth |
| `recursion_max_sub_elements_total` | int | `8` | Max total sub-elements across recursion |
| `recursion_max_llm_calls` | int | `3` | Max LLM calls during recursive decomposition |
| `recursion_monotonicity` | str | `"strict_tier_decrease"` | Recursion monotonicity constraint |
| `orchestrator_decomp_max_external_deps` | int | `3` | Max external deps for orchestrator decomposition |
| `moderate_ollama_whole_enabled` | bool | `true` | Use Ollama file-whole for MODERATE elements |
| `moderate_ollama_whole_skip_signals` | list[str] | `["external_api", "orchestrator", "app_server_instance"]` | Signals that skip MODERATE Ollama-whole |
| `file_ollama_whole_enabled` | bool | `true` | Primary path: generate entire file in one shot |
| `file_ollama_whole_max_elements` | int | `60` | Max elements for file-whole generation |
| `file_ollama_whole_max_loc` | int | `600` | Max LOC for file-whole generation |
| `min_element_fill_rate` | float | `0.5` | Post-generation success criteria (50% fill) |
| `element_prompt_mode` | str | `"full_function"` | Element prompt mode: `"full_function"` or `"body_only"` |
| `external_api_packages` | list[str] | *(see below)* | Package names triggering external API classification |

**`external_api_packages` default:** `["grpc", "grpcio", "httpx", "aiohttp", "requests", "flask", "fastapi", "django", "starlette", "jinja2", "mako", "google.cloud", "google.auth", "google.api_core", "boto3", "botocore", "azure", "sqlalchemy", "alembic", "asyncpg", "psycopg2", "celery", "redis", "kombu", "locust", "playwright"]`

### `complexity_routing`

Controls how tasks are classified into complexity tiers (TRIVIAL/SIMPLE/MODERATE/COMPLEX) for model routing.

Source: `src/startd8/complexity/models.py` (`ComplexityRoutingConfig`)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `false` | Master switch for complexity-based routing |
| `blast_radius_complex_threshold` | int | `5` | Blast radius above which task is COMPLEX |
| `loc_simple_max` | int | `150` | Max estimated LOC for SIMPLE tier |
| `loc_complex_min` | int | `500` | Min estimated LOC for COMPLEX tier |
| `caller_count_complex_threshold` | int | `3` | Caller count above which task is COMPLEX |
| `mro_depth_complex_threshold` | int | `3` | MRO depth above which task is COMPLEX |
| `unresolved_calls_complex_threshold` | int | `2` | Unresolved calls above which task is COMPLEX |
| `templates_enabled` | bool | `true` | Enable template matching for TRIVIAL tier |
| `simple_relaxed_enabled` | bool | `true` | Relax SIMPLE boundary for create-mode elements |
| `simple_relaxed_blast_radius_max` | int | `2` | Max blast radius for relaxed SIMPLE |
| `non_python_trivial_loc_max` | int | `100` | Max LOC for non-Python TRIVIAL routing |
| `non_python_simple_loc_max` | int | `300` | Max LOC for non-Python SIMPLE routing |

### `repair`

Controls the post-generation repair pipeline for syntax, import, and lint errors.

Source: `src/startd8/repair/config.py` (`RepairConfig`)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `true` | Master switch for repair pipeline |
| `repairable_categories` | list[str] | `["syntax", "import", "lint", "semantic"]` | Diagnostic categories eligible for repair |
| `pre_checkpoint_repair` | bool | `false` | Run repair before first checkpoint |
| `circuit_breaker_threshold` | int | `3` | Consecutive failures before disabling repair |
| `per_step_timeout_s` | float | `2.0` | Timeout per individual repair step (seconds) |
| `total_timeout_s` | float | `5.0` | Total timeout for entire repair pipeline (seconds) |
| `delta_threshold` | float | `0.5` | Skip step if it changes more than this fraction of lines |
| `staging_retention_hours` | int | `24` | Hours to retain failed staging dirs |
| `semantic_repair_categories` | list[str] | `[]` | Per-category enable for semantic repair |
| `max_semantic_repairs_per_file` | int | `5` | Safety bound on semantic repairs per file |
| `semantic_repair_circuit_breaker_threshold` | int | `3` | Consecutive failures before disabling semantic repair |

### `validation`

Controls post-generation validation behavior.

Source: `src/startd8/contractors/prime_contractor_config.py` (`ValidationConfig`)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool\|null | `null` | Enable validation; `null` = mode-default |
| `strict` | bool | `false` | Strict validation mode (fail on warnings) |

### `agents`

Agent specifications for code generation tiers, using `provider:model` format.

Source: `src/startd8/contractors/prime_contractor_config.py` (`AgentConfig`)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `lead` | str\|null | `null` | Lead/architect agent spec (null = catalog default) |
| `drafter` | str\|null | `null` | Drafter/coder agent spec (null = catalog default) |
| `tier3` | str\|null | `null` | COMPLEX tier agent spec (null = catalog default) |

### Top-level flags

These are top-level fields on `PrimeContractorConfig` derived from section `enabled` flags during parsing.

Source: `src/startd8/contractors/prime_contractor_config.py` (`PrimeContractorConfig`)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `micro_prime_enabled` | bool | `false` | Resolved from `micro_prime.enabled` |
| `complexity_routing_enabled` | bool | `false` | Resolved from `complexity_routing.enabled` |
| `repair_enabled` | bool | `true` | Resolved from `repair.enabled` |

### Budget constants (module-level)

These are module-level constants in `implementation_engine/budget.py`. They are not configurable via `prime-contractor.json` but affect prompt construction.

| Constant | Type | Value | Description |
|----------|------|-------|-------------|
| `PLAN_CONTEXT_MAX_CHARS` | int | `6000` | Max chars for plan context in spec prompt |
| `ARCH_CONTEXT_MAX_CHARS` | int | `4096` | Max chars for architectural context |
| `SPEC_CONTEXT_BUDGET_CHARS` | int | `12000` | Total spec context budget |
| `EXISTING_FILES_BUDGET_BYTES` | int | `40960` | Max bytes for existing file content in drafts (40 KB) |
| `SEARCH_REPLACE_LINE_THRESHOLD` | int | `50` | Line threshold for search/replace vs whole-file edit |
| `DRAFT_SIZE_REGRESSION_THRESHOLD` | float | `0.20` | Draft below 20% of existing = truncated |
| `DRAFT_SIZE_REGRESSION_MIN_LINES` | int | `50` | Min lines before regression check applies |
| `DRAFT_SIZE_EXPLOSION_THRESHOLD` | float | `3.0` | Draft above 300% of existing = hallucinated |
| `SUPPLEMENTARY_BUDGET_CHARS` | int | `4000` | Optional prompt section budget (T1 drafter) |
| `ENRICHMENT_BUDGET_CHARS` | int | `8000` | Review prompt budget (T2 reviewer) |
| `TOTAL_SPEC_BUDGET_TOKENS` | int | `4096` | Hard cap for spec prompts |
| `TOTAL_DRAFT_BUDGET_TOKENS` | int | `8192` | Hard cap for draft prompts |
| `CHARS_PER_TOKEN` | int | `4` | Rough chars-per-token estimate |
| `EXEMPLAR_BUDGET_CHARS` | int | `3200` | Exemplar injection budget (~800 tokens) |

### Tier budget multipliers

Tier-aware budget multipliers applied via `budget_tokens_for_tier()`:

| Tier | Multiplier | Effective spec budget | Effective draft budget |
|------|------------|----------------------|----------------------|
| TRIVIAL | 0.75 | 3072 | 6144 |
| SIMPLE | 1.0 | 4096 | 8192 |
| MODERATE | 1.75 | 7168 | 14336 |
| COMPLEX | 1.75 | 7168 | 14336 |

### Integration engine constants (module-level)

Module-level constants in `contractors/integration_engine.py`:

| Constant | Type | Value | Description |
|----------|------|-------|-------------|
| `_INTEGRATION_SIZE_REGRESSION_THRESHOLD` | float | `0.60` | Merged file below 60% of target = regression |
| `_INTEGRATION_MIN_LINES` | int | `50` | Min lines before regression check applies |

### Quality gate constant (module-level)

Module-level constant in `contractors/prime_contractor.py`:

| Constant | Type | Value | Description |
|----------|------|-------|-------------|
| `_MIN_QUALITY_SCORE` | int | `60` | Min quality score for a feature to pass |

## CLI Override Reference

CLI arguments take precedence over config file values. Only non-None CLI values override.

| CLI Arg | Config Path | Example |
|---------|-------------|---------|
| `--micro-prime` | `micro_prime.enabled = true` | `--micro-prime` |
| `--no-micro-prime` | `micro_prime.enabled = false` | `--no-micro-prime` |
| `--micro-prime-dry-run` | `micro_prime.enabled = true, micro_prime.dry_run = true` | `--micro-prime-dry-run` |
| `--micro-prime-model` | `micro_prime.model` | `--micro-prime-model deepseek-coder` |
| `--micro-prime-max-tokens` | `micro_prime.max_tokens` | `--micro-prime-max-tokens 4096` |
| `--micro-prime-cloud-retry-attempts` | `micro_prime.cloud_escalation_max_attempts` | `--micro-prime-cloud-retry-attempts 5` |
| `--micro-prime-cloud-retry-strategy` | `micro_prime.cloud_escalation_retry_strategy` | `--micro-prime-cloud-retry-strategy same_prompt` |
| `--micro-prime-cloud-retry-max-chars` | `micro_prime.cloud_escalation_retry_max_chars` | `--micro-prime-cloud-retry-max-chars 1024` |
| `--micro-prime-no-templates` | `micro_prime.templates_enabled = false` | `--micro-prime-no-templates` |
| `--micro-prime-no-repair` | `micro_prime.repair_enabled = false` | `--micro-prime-no-repair` |
| `--complexity-routing` | `complexity_routing.enabled = true` | `--complexity-routing` |
| `--complexity-loc-simple-max` | `complexity_routing.loc_simple_max` | `--complexity-loc-simple-max 200` |
| `--tier3-agent` | `agents.tier3` | `--tier3-agent anthropic:claude-opus-4-20250514` |
| `--no-repair` | `repair.enabled = false` | `--no-repair` |
| `--strict-validation` | `validation.enabled = true, validation.strict = true` | `--strict-validation` |
| `--validate` | `validation.enabled = true` | `--validate` |
| `--no-validate` | `validation.enabled = false` | `--no-validate` |
| `--lead-agent` | `agents.lead` | `--lead-agent anthropic:claude-sonnet-4-20250514` |
| `--drafter-agent` | `agents.drafter` | `--drafter-agent openai:gpt-4-turbo-preview` |

## Example Configuration

See `docs/examples/prime-contractor.example.json` for a complete example with all sections.

## Tuning Guide

### When to increase circuit breaker thresholds

The Micro Prime engine has two circuit breakers:
- **Per-file** (`circuit_breaker_per_file` on `MicroPrimeConfig`, default 8): Trips after N consecutive failures within a single file. Increase if files have many small elements that fail individually but don't indicate systemic issues.
- **Per-run** (`circuit_breaker_per_run` on `MicroPrimeConfig`, default 12): Trips after N consecutive cross-file failures. Increase for large projects where early files may fail but later ones succeed.

The repair pipeline also has a circuit breaker (`repair.circuit_breaker_threshold`, default 3). This is intentionally lower since repair failures tend to be systemic.

### When to adjust quality gate

The quality gate (`_MIN_QUALITY_SCORE = 60`) determines the minimum quality score for accepting generated code. This is a module-level constant, not configurable via JSON. To adjust, modify `src/startd8/contractors/prime_contractor.py`.

### When to tune complexity routing

Enable complexity routing (`complexity_routing.enabled = true`) when:
- Your project has a mix of trivial config files and complex business logic
- You want to save costs by routing simple tasks to cheaper models
- You have Ollama running locally for SIMPLE/MODERATE tasks

Key thresholds to adjust:
- `loc_simple_max` (default 150): Lower for stricter SIMPLE classification
- `loc_complex_min` (default 500): Lower to classify more tasks as COMPLEX
- `blast_radius_complex_threshold` (default 5): Lower for more conservative routing

### Language-specific considerations

- **Python**: Full Micro Prime support (AST repair, Ruff lint, element-level generation)
- **Go, Node.js, Java**: Non-Python tasks bypass Micro Prime element-level generation and use file-whole generation. Adjust `non_python_trivial_loc_max` and `non_python_simple_loc_max` for tier routing thresholds.
- **External API packages**: Add domain-specific packages to `external_api_packages` to ensure tasks using those packages are classified appropriately (avoids local model attempts for API-heavy code).

### When to disable decomposition

Decomposition (`decomposition_enabled`, default `false`) breaks MODERATE elements into SIMPLE sub-elements. It is disabled by default because it introduces accidental complexity (~2,900 lines of decomposer + splicer + repair code). Enable only if:
- Ollama file-whole generation consistently fails for your codebase
- Elements are genuinely decomposable (classes with independent methods)
- You've verified the decomposition confidence threshold is appropriate
