# startd8-coder: Ollama Model & Engine Configuration Spec

**Quick reference** for the current Ollama model and Micro Prime engine configuration.
Companion to [OLLAMA_QUALITY_RESEARCH_AGENDA.md](OLLAMA_QUALITY_RESEARCH_AGENDA.md).

**Last updated:** 2026-03-14

---

## 1. Ollama Model

| Parameter | Value | Source |
|-----------|-------|--------|
| Base model | `qwen2.5-coder:7b` | Modelfile line 1 |
| Custom model name | `startd8-coder` | `ollama create startd8-coder -f Modelfile.startd8-coder` |
| Context window | **8192** tokens | Modelfile `num_ctx` (active — baked into model) |
| Repeat penalty | **1.05** | Modelfile `repeat_penalty` (active — not sent per-call) |
| Repeat last N | **64** | Modelfile `repeat_last_n` (active — not sent per-call) |

**Modelfile location:** `docs/design/micro-prime/Modelfile.startd8-coder`

### What's NOT in the Modelfile (overridden by API)

These were removed from the Modelfile because the per-call API parameters take precedence:

| Parameter | Effective Value | Set By |
|-----------|----------------|--------|
| SYSTEM prompt | See Section 2 | `engine.py` per-call `system_prompt=` |
| temperature | 0.1 | `MicroPrimeConfig.temperature` → API call |
| top_p / top_k | Ollama defaults | Not sent per-call |
| num_predict | 2048 (element) / variable (file-whole) | `MicroPrimeConfig.max_tokens` → API `max_tokens=` |
| stop sequences | See Section 4 | `engine.py` per-call `stop=` |

### Rebuild command

```bash
ollama create startd8-coder -f docs/design/micro-prime/Modelfile.startd8-coder
```

---

## 2. System Prompts

Three system prompts, selected per generation mode. All in `engine.py:613–644`.

### Element — Full Function (default: `element_prompt_mode="full_function"`)

```
You are a Python code generator. Output the complete function implementation.

FORMAT: Output a single Python function with its def line and body.
Use 4-space indentation. Output raw Python code — no ```python fences,
no prose, no explanations.

IMPORTS: Do NOT output import statements. The imports are already provided
in the file.

SCOPE: Output ONLY the single requested function definition (def + body).
Stop after the last line of the function body.
Do not output additional functions, classes, or standalone statements.
```

### Element — Body Only (legacy: `element_prompt_mode="body_only"`)

```
You are a Python code generator. Output the indented body lines of the
target function.

FORMAT: Start every line with exactly 4 spaces. Output raw Python code —
no ```python fences, no prose, no def line.

IMPORTS: Use ONLY imports shown in the prompt. Do not add import statements
to your output.

SCOPE: Output ONLY the body of the single requested function. Stop after
the last line of the body. Do not output additional functions, classes,
or statements.
```

### File-Whole

```
You are a Python code generator. You receive a skeleton Python file with
`raise NotImplementedError` stubs.

TASK: Replace every `raise NotImplementedError` with a working
implementation. Output the COMPLETE file with all stubs filled.

PRESERVE: Keep all existing imports, class definitions, signatures, and
decorators exactly as given. Use 4-space indentation. Each function body
goes directly under its def line — never nest a function inside itself.

FORMAT: Output raw Python code only. No ```python fences, no explanations,
no commentary.
```

---

## 3. MicroPrimeConfig Defaults

All tunable knobs. Source: `src/startd8/micro_prime/models.py:463–554`.

### Core

| Parameter | Default | Description |
|-----------|---------|-------------|
| `model` | `"startd8-coder"` | Ollama model name |
| `provider` | `"ollama"` | Provider backend |
| `temperature` | `0.1` | Sampling temperature (sent per-call) |
| `max_tokens` | `2048` | Output token budget (overrides Modelfile `num_predict`) |
| `input_token_budget` | `1024` | Max tokens for input prompt (element-level) |
| `element_prompt_mode` | `"full_function"` | `"full_function"` (default) or `"body_only"` (legacy) |

### Generation Strategy

| Parameter | Default | Description |
|-----------|---------|-------------|
| `file_ollama_whole_enabled` | `True` | PRIMARY path — generate entire file in one shot |
| `file_ollama_whole_max_elements` | `60` | Max elements for file-whole eligibility |
| `file_ollama_whole_max_loc` | `600` | Max LOC for file-whole eligibility |
| `moderate_ollama_whole_enabled` | `True` | Try file-whole for MODERATE elements before decomposition |
| `moderate_ollama_whole_skip_signals` | `{"external_api", "orchestrator", "app_server_instance"}` | Skip Ollama-whole for these complexity signals |
| `min_element_fill_rate` | `0.5` | Minimum stub fill rate for file-whole acceptance |

### Templates & Repair

| Parameter | Default | Description |
|-----------|---------|-------------|
| `templates_enabled` | `True` | Use deterministic templates for TRIVIAL tier |
| `repair_enabled` | `True` | Run 10-step repair pipeline |
| `few_shot_enabled` | `True` | Include few-shot examples in prompts |
| `max_few_shot_examples` | `2` | Max few-shot examples per prompt |

### Escalation

| Parameter | Default | Description |
|-----------|---------|-------------|
| `escalation_enabled` | `True` | Escalate to cloud on local failure |
| `local_max_attempts` | `2` | Max Ollama attempts before escalation |
| `cloud_escalation_max_attempts` | `3` | Max cloud attempts |
| `cloud_escalation_retry_strategy` | `"same_prompt"` | Retry strategy for cloud |

### Classifier Thresholds

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_simple_imports` | `8` | Import count threshold for SIMPLE tier |
| `max_simple_params` | `4` | Parameter count threshold for SIMPLE tier |
| `class_score_bonus` | `1` | Complexity score bonus for class elements |
| `simple_threshold` | `0` | Score threshold for SIMPLE classification |
| `docstring_length_threshold` | `200` | Docstring length complexity signal |

### Decomposition (fallback only)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `decomposition_enabled` | `False` | Decompose MODERATE elements (off by default) |
| `max_sub_elements` | `5` | Max sub-elements per decomposition |
| `recursion_enabled` | `False` | Recursive decomposition |

### Semantic Verification

| Parameter | Default | Description |
|-----------|---------|-------------|
| `semantic_verification_enabled` | `True` | LLM-based semantic check post-generation |
| `semantic_verification_temperature` | `0.0` | Greedy for verification |
| `semantic_verification_max_tokens` | `256` | Max tokens for verification response |

---

## 4. Stop Sequences

### Element-Level (9 sequences)

```python
_OLLAMA_STOP_SEQUENCES = [
    "\n\ndef ",          # Second function boundary
    "\n\nasync def ",    # Second async function boundary
    "\n\nclass ",        # Class boundary after function
    "\nif __name__",     # Common Python trailer
    "\n# Task:",         # Model echoing prompt template
    "\n# Implement",     # Model echoing prompt template
    "\n# Define",        # Model echoing constant prompt template
    "\n# Now implement", # Model echoing "Now implement this:" marker
    "\n\n\n",            # Triple newline — generation exhausted
]
```

### File-Whole (6 sequences)

```python
_FILE_WHOLE_STOP_SEQUENCES = [
    "\nif __name__",     # Common Python trailer
    "\n# Task:",         # Model echoing prompt template
    "\n# Implement",     # Model echoing prompt template
    "\n# Define",        # Model echoing constant prompt template
    "\n# Now implement", # Model echoing "Now implement this:" marker
    "\n\n\n\n",          # Quadruple newline (triple is too aggressive — PEP 8)
]
```

**Note:** Element-level stops (`\n\ndef `, `\n\nclass `) are suppressed in file-whole mode to allow multi-definition output.

---

## 5. Repair Pipeline (10 steps)

Source: `src/startd8/micro_prime/repair.py`

| Step | Name | Applies To | What It Fixes |
|------|------|-----------|---------------|
| 1 | `fence_strip` | element, file | Markdown ` ```python ``` ` fences |
| 2 | `octal_literal_fix` | element, file | Py2 octals `0755` → `0o755` |
| 3 | `over_generation_trim` | element | Extra functions/classes beyond target |
| 4 | `bare_statement_wrap` | element | Body-only output → wrapped in def line |
| 5 | `future_import_reorder` | element | `from __future__` moved to file top |
| 6 | `indent_normalize` | element | Mixed tabs/spaces → 4-space |
| 7 | `signature_reconcile` | element | Restore canonical signature from manifest |
| 8 | `import_completion` | element | Add missing imports from manifest |
| 9 | `duplicate_removal` | element, file | Remove duplicate import lines |
| 10 | `ast_validate` | element, file | Final AST parse gate |

**Non-destructive guarantee (REQ-MP-406):** If a step breaks previously valid code, its changes are reverted.

---

## 6. Generation Routing

```
Element arrives
  │
  ├─ TRIVIAL → Template Registry (no LLM) → splice
  │
  ├─ SIMPLE/MODERATE → file-whole eligible?
  │    ├─ Yes → File-Whole Ollama → repair → validate
  │    │    ├─ Success (fill rate ≥ 50%) → accept
  │    │    └─ Fail → element-by-element fallback
  │    └─ No → element-by-element
  │
  ├─ Element-by-element → prompt builder → Ollama → repair → verify → splice
  │    ├─ Success → done
  │    └─ Fail (after local_max_attempts=2) → escalate to cloud
  │
  └─ COMPLEX → direct cloud escalation
```

---

## 7. Baseline Quality (2026-03-14)

From eval harness (`scripts/run_eval_ollama.py`), 39-entry corpus, 2 runs:

| Metric | Value |
|--------|-------|
| Syntax rate | 97.5% |
| Pass rate | 67.1% |
| Mean semantic | 2.08 / 3.00 |
| Lint rate | 45.6% |
| Repair rate | 36.7% |
| File-whole fill rate | 100% |

Per-tier: trivial 50%, simple 72%, moderate 56%.

---

## 8. File Locations

| Component | Path |
|-----------|------|
| Modelfile | `docs/design/micro-prime/Modelfile.startd8-coder` |
| This spec | `docs/design/micro-prime/STARTD8_CODER_SPEC.md` |
| Research agenda | `docs/design/micro-prime/OLLAMA_QUALITY_RESEARCH_AGENDA.md` |
| Config class | `src/startd8/micro_prime/models.py:463–554` |
| System prompts | `src/startd8/micro_prime/engine.py:613–644` |
| Stop sequences | `src/startd8/micro_prime/engine.py:3775–3801` |
| User prompt (element) | `src/startd8/micro_prime/prompt_builder.py` |
| User prompt (file-whole) | `src/startd8/micro_prime/engine.py:749–846` |
| Repair pipeline | `src/startd8/micro_prime/repair.py` |
| Template registry | `src/startd8/micro_prime/templates.py` |
| Eval scoring | `src/startd8/micro_prime/eval_scoring.py` |
| Eval harness | `scripts/run_eval_ollama.py` |
| Golden corpus | `tests/evaluation/golden_corpus/corpus.json` |
| Corpus grower | `scripts/grow_eval_corpus.py` |
| Persisted config | `.startd8/micro_prime.json` |
