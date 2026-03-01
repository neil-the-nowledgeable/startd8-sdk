# Layer 1 — Model Selection & Tuning (REQ-MP-1xx)

> **Parent:** [MICRO_PRIME_REQUIREMENTS.md](./MICRO_PRIME_REQUIREMENTS.md)
> **Status:** Mostly implemented
> **Artifact:** `Modelfile.startd8-coder`
> **Design detail:** [OLLAMA_MODEL_TUNING.md](../OLLAMA_MODEL_TUNING.md)

---

## Overview

This layer covers the selection, configuration, and registration of the local coding model used for SIMPLE element generation. The goal is to maximize output quality from a 7B parameter model through inference parameter tuning, system prompt engineering, and stop sequence design — all without modifying SDK code.

## Rationale

The Round 1 experiment used `codellama:latest` (7B) with default Ollama parameters (temperature 0.8, top_p 0.9, no stop sequences, no system prompt). The result was a 9% end-to-end success rate with high variance across runs.

Three of the four failure modes (indentation, over-generation, non-determinism) are controllable through inference parameters. The fourth (API hallucination) is mitigated by system prompt constraints and addressed more fully by the import-based complexity gate (REQ-MP-501).

## Requirements

### REQ-MP-100: Base Model Selection

**Status:** implemented
**Priority:** P0
**Evidence:** `ollama list` shows `qwen2.5-coder:7b` (4.7 GB)

The base model SHALL be `qwen2.5-coder:7b`. Selection was based on:

| Criterion | qwen2.5-coder:7b | codellama:7b | deepseek-coder-v2:16b |
|-----------|------------------|-------------|----------------------|
| Code completion benchmarks (7B class) | Best in class | Baseline | N/A (16B) |
| Type signature adherence | Strong | Weak | Strong |
| RAM requirement | ~6-8 GB | ~6-8 GB | ~12-14 GB |
| Inference time (M1 Pro) | ~4-5s | ~10-11s | ~15-20s (est.) |

**Acceptance criteria:**
1. Model is pullable: `ollama pull qwen2.5-coder:7b` succeeds
2. Inference completes in <6s per element on M1 Pro 32GB
3. Model produces syntactically valid Python for a `JSONFormatter.format` prompt (baseline test)

---

### REQ-MP-101: Modelfile Configuration

**Status:** implemented
**Priority:** P0
**Evidence:** `ollama list` shows `startd8-coder:latest` (4.7 GB); determinism validated

The Modelfile SHALL configure inference parameters to produce near-deterministic, concise output:

```
PARAMETER temperature 0.1     # Near-greedy decoding
PARAMETER top_p 0.85          # Reduce tail-probability hallucinations
PARAMETER top_k 30            # Restrict candidate pool
PARAMETER num_predict 512     # Cap output tokens for SIMPLE elements
PARAMETER repeat_penalty 1.1  # Prevent degenerate loops
PARAMETER repeat_last_n 128   # Repetition window
```

**Parameter justification:**

| Parameter | Default | Tuned | Effect |
|-----------|---------|-------|--------|
| temperature | 0.8 | 0.1 | Eliminates run-to-run variance (47-74% → identical across 3 runs) |
| top_p | 0.9 | 0.85 | Marginal effect at temp=0.1 but provides safety net against rare hallucinations |
| top_k | 40+ | 30 | Reduces probability of hallucinated identifiers (e.g., wrong enum paths) |
| num_predict | 2048 | 512 | Prevents worst over-generation (1600-2225 token outputs → bounded at 512) |
| repeat_penalty | 1.0 | 1.1 | Mild suppression; avoids distorting short code while preventing loops |

**Acceptance criteria:**
1. `ollama create startd8-coder -f Modelfile.startd8-coder` succeeds
2. 3 consecutive runs of `JSONFormatter.format` prompt produce identical output (79 tokens each)
3. Average tokens per element: <100 (vs 555 baseline with codellama)

---

### REQ-MP-102: System Prompt

**Status:** implemented
**Priority:** P0
**Evidence:** Model does not emit explanation text in smoke tests

The Modelfile SYSTEM prompt SHALL constrain output to code-only and prevent API hallucination:

```
You are a Python code generator for the startd8 pipeline. You receive either:
(a) A function stub with signature, type hints, imports, and constraints — fill in the body.
(b) A variable/constant stub — output only the assignment statement.

Rules:
1. Output ONLY the code — no explanation, no markdown fences, no extra text before or after
2. Use ONLY the imports shown in the prompt — do not invent APIs or import new modules
3. Match the exact function signature provided — do not rename parameters or change types
4. Keep the implementation minimal — prefer the shortest correct solution
5. Use 4-space indentation consistently — no tabs, no mixed indentation
6. Write methods at the TOP level (no class wrapper) — the prompt provides class context separately
7. For constants/variables, output ONLY the assignment (e.g. `x = [...]`), nothing else
8. STOP after the single requested element — never output additional functions or classes
```

**Rule-to-failure-mode mapping:**

| Rule | Target Failure Mode | Round 1/2 Impact |
|------|-------------------|----------------|
| Rule 2 | API hallucination | 80% of syntax-valid failures (wrong enum paths, missing imports, nonexistent methods) |
| Rule 4 | Over-generation | ~10% (full Flask apps, retry logic for simple calls) |
| Rules 5-6 | Indentation | 53% of all failures (Round 1); 0% (Round 2, with top-level method rendering) |
| Rule 7 | Constant over-generation | Model producing full functions when asked for `app = Flask(__name__)` |
| Rule 8 | Secondary element generation | Model continuing past the target function |

**v2 changes:** Role broadened from "function body generator" to "code generator for the startd8 pipeline" (handles constants/variables). Rule 6 changed from "indent methods 4 spaces from def line" to "Write methods at the TOP level (no class wrapper)" — aligned with prompt FIX #3. Rules 7-8 added.

**Known limitation:** qwen2.5-coder ignores Rule 1 for markdown fences — it wraps output in ` ```python ` blocks regardless. This is acceptable because `extract_code_from_response()` already strips fences.

**Acceptance criteria:**
1. Model does not generate explanation text (e.g., "Here is the implementation:")
2. Model does not import modules not present in the prompt context
3. Model uses 4-space indentation consistently

---

### REQ-MP-103: Stop Sequences

**Status:** implemented
**Priority:** P1
**Evidence:** Zero elements truncated in Round 2 (24/24 complete); all stop sequences validated

The Modelfile SHALL define stop sequences that prevent over-generation without prematurely truncating the target function.

**Empirically validated stop sequences:**

| Sequence | Purpose |
|----------|---------|
| `"\nif __name__"` | Halt at common Python trailer |
| `"\n# Task:"` | Halt when model echoes prompt template |
| `"\n# Implement"` | Same |
| `"\n# Define"` | Halt when model echoes constant prompt template (added in v2) |
| `"\n\n\n"` | Halt at triple newline (generation exhausted) |

**Empirically invalidated stop sequences (DO NOT USE):**

| Sequence | Failure Mode |
|----------|-------------|
| `` ``` `` | Model starts output with `` ```python `` — killed on first token |
| `"\ndef "` | Model outputs `\ndef target_name(...)` — killed before body generated |
| `"\nclass "` | Same issue for class methods |
| `"\n\ndef "` | Response starts with `\n` then `\ndef` — matches on second token |

**Acceptance criteria:**
1. Model generates complete function bodies for all SIMPLE element types
2. Model does not generate secondary functions/classes after the target
3. No premature truncation on any of the 32 online-boutique-demo elements

---

### REQ-MP-104: Model Registry Entry

**Status:** planned
**Priority:** P2
**Depends on:** REQ-MP-500

The `startd8-coder` model SHALL be added to the SDK's model catalog and supported models list.

**Changes required:**

| File | Change |
|------|--------|
| `src/startd8/providers/openai.py` (OllamaProvider.supported_models) | Add `"startd8-coder"` |
| `src/startd8/session_tracking.py` | Add context window entry (32,768) |
| `src/startd8/tui_improved.py` | Add to Ollama model picker list |

**Acceptance criteria:**
1. `resolve_agent_spec("ollama:startd8-coder")` returns a valid `OpenAICompatibleAgent`
2. Agent's `max_tokens` defaults to 512 (matching Modelfile `num_predict`)
3. Preflight model check passes for `startd8-coder`

---

## Files

| File | Purpose |
|------|---------|
| `docs/design/micro-prime/Modelfile.startd8-coder` | Modelfile artifact |
| `docs/design/micro-prime/OLLAMA_MODEL_TUNING.md` | Design analysis and validation results |
| `src/startd8/providers/openai.py` | OllamaProvider (REQ-MP-104) |
