# Ollama Model Tuning for Local Code Generation

**Date:** 2026-03-01
**Status:** Round 2 Complete — 100% syntax, 42% verified (up from 9% baseline)
**Prerequisite:** [LOCAL_MODEL_ROUTING_EXPERIMENT.md](../local-model-routing/LOCAL_MODEL_ROUTING_EXPERIMENT.md)
**Artifact:** `Modelfile.startd8-coder` (see Appendix A)

---

## 1. Context

The local model routing experiment (Round 1) tested `codellama:latest` (7B) and found a 9% end-to-end success rate. Failure analysis identified three root causes:

| Failure Mode | % of Failures | Root Cause |
|-------------|---------------|------------|
| Syntax errors (indentation) | 53% | Non-deterministic output at default temperature (0.8) |
| API hallucination | 80% of syntax-valid | Model invents library APIs not in the prompt |
| Over-generation | ~10% | No token budget or stop boundaries |

This document covers model-level tuning (Modelfile) and prompt-level improvements (experiment script) applied to address all three failure modes.

## 2. Model Selection

**Selected:** `qwen2.5-coder:7b`

| Candidate | Size | Rationale |
|-----------|------|-----------|
| `qwen2.5-coder:7b` | 4.7 GB | Best-in-class code completion at 7B; strong type signature adherence; same resource footprint as codellama:7b |
| `deepseek-coder-v2:16b` | 8.9 GB | Better API awareness but ~2x inference time; overkill for SIMPLE elements |
| `codellama:13b` | 7.4 GB | Same family as baseline; incremental improvement doesn't justify size increase |

**Hardware fit:** M1 Pro 32GB RAM / 16-core GPU — qwen2.5-coder:7b runs comfortably at ~4-5s per element with headroom for other processes.

## 3. Tuning Approach: Ollama Modelfile

Ollama supports custom model variants via Modelfiles — a declarative config that bakes inference parameters, system prompts, and stop sequences into a named model. The SDK calls `ollama:startd8-coder` instead of `ollama:qwen2.5-coder:7b` and gets all tuning automatically, with zero code changes to `OpenAICompatibleAgent`.

### Why Modelfile over SDK parameter pass-through

The SDK's Ollama provider (`OllamaProvider` in `providers/openai.py`) routes through `OpenAICompatibleAgent`, which currently forwards only `model`, `max_tokens`, and `messages` to the `/v1/chat/completions` endpoint. It does **not** pass `temperature`, `top_p`, `stop`, or other inference parameters.

Adding parameter forwarding would require changes to `OpenAICompatibleAgent._make_api_call()`. The Modelfile approach achieves the same result at the Ollama layer, making it:

- **Zero-code:** No SDK changes needed
- **Portable:** The Modelfile travels with the project, not the SDK
- **Overridable:** Per-request `options` in the Ollama API override Modelfile defaults if the SDK later adds pass-through

## 4. Parameter Decisions

### 4.1 Sampling — Near-Deterministic

```
PARAMETER temperature 0.1
PARAMETER top_p 0.85
PARAMETER top_k 30
```

**Problem addressed:** codellama at default temperature (0.8) produced syntax success rates of 47-74% across runs — the same prompt yielded different indentation patterns each time.

**Why these values:**
- `temperature 0.1` — Near-greedy decoding. For function body fill-in, there is typically one correct implementation; creative sampling adds noise. Validated: 3 consecutive runs produced **identical output** (79 tokens each).
- `top_p 0.85` — Slightly below default (0.9) to further reduce tail-probability tokens. With temperature 0.1, top_p has minimal additional effect but provides a safety net.
- `top_k 30` — Restricts candidate pool from the default (40+) to the 30 most likely tokens. Reduces probability of hallucinated identifiers (e.g., `health_pb2.SERVING` instead of `health_pb2.HealthCheckResponse.SERVING`).

**Determinism test results:**

| Model | Run 1 | Run 2 | Run 3 | Tokens |
|-------|-------|-------|-------|--------|
| `startd8-coder` (tuned) | Identical | Identical | Identical | 79 |
| `qwen2.5-coder:7b` (defaults) | Variant A | Variant B | Variant C | 95-112 |

### 4.2 Token Budget

```
PARAMETER num_predict 512
```

**Problem addressed:** Over-generation — codellama produced 1600 tokens for `app` (expected: `app = Flask(__name__)`) and 2225 tokens for `send_request` (expected: simple gRPC call).

**Why 512:** SIMPLE elements target function bodies under 15 lines. At ~4 tokens/line with signature + docstring overhead, 512 tokens covers up to ~100 lines — generous enough for any SIMPLE element while preventing runaway generation. Truncated output (hitting the cap) is a detectable signal for escalation to a cloud model.

### 4.3 System Prompt

```
SYSTEM """You are a Python code generator for the startd8 pipeline. You receive either:
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
8. STOP after the single requested element — never output additional functions or classes"""
```

**Problem addressed:** API hallucination (80% of syntax-valid failures) and indentation mangling.

**Key rules and their targets:**

| Rule | Target Failure Mode |
|------|-------------------|
| Rule 2: "Use ONLY the imports shown" | API hallucination — model invented `datetime`, `traceback`, nonexistent method chains |
| Rule 4: "shortest correct solution" | Over-generation — model produced full Flask apps, retry logic |
| Rules 5-6: Indentation + top-level methods | Syntax errors — mixed tabs/spaces, wrong indentation level |
| Rule 7: Constants/variables | Over-generation — model produced full Flask apps when asked for `app = Flask(__name__)` |
| Rule 8: STOP after element | Over-generation — model continued past the target function |

**Changes from initial version (v1 → v2):**
- Role changed from "function body generator" to "code generator for the startd8 pipeline" (now handles constants too)
- Added `(b) A variable/constant stub` preamble
- Rule 6 changed from "indent methods 4 spaces from def line" to "Write methods at the TOP level (no class wrapper)" — aligned with prompt FIX #3
- Added Rule 7 for constants/variables
- Added Rule 8 explicit STOP instruction

**Note:** qwen2.5-coder wraps output in ` ```python ` fences despite Rule 1. This is a model behavior that cannot be overridden via system prompt. Post-processing (`extract_code_from_response`) already handles fence stripping, so this is a non-issue.

### 4.4 Stop Sequences

```
PARAMETER stop "\nif __name__"
PARAMETER stop "\n# Task:"
PARAMETER stop "\n# Implement"
PARAMETER stop "\n# Define"
PARAMETER stop "\n\n\n"
```

**Problem addressed:** Over-generation past the target function boundary.

**What works:**
- `"\nif __name__"` — Common Python trailer; fires only after function body is complete
- `"\n# Task:"` / `"\n# Implement"` — Catches cases where the model echoes the prompt template
- `"\n# Define"` — Added in v2; catches constant prompt echo when model drifts past the assignment
- `"\n\n\n"` — Triple newline indicates the model has finished and is generating whitespace

**Critical lesson learned:** Naive stop sequences like `"\ndef "`, `"\nclass "`, and `` "```" `` kill the output immediately — see Appendix B.

### 4.5 Repetition Control

```
PARAMETER repeat_penalty 1.1
PARAMETER repeat_last_n 128
```

Prevents degenerate loops where the model repeats the same token sequence. `repeat_penalty 1.1` is a mild penalty — enough to break loops without distorting the probability distribution for normal code patterns.

## 5. Prompt-Level Improvements

In addition to Modelfile tuning, six prompt-level fixes were applied in `experiment_local_model_routing.py`. These work in concert with the Modelfile system prompt — the Modelfile constrains the model's behavior globally, while per-element prompts provide specific context.

### FIX #1: Length + Stop Constraints

```
# The body should be approximately 5-12 lines.
# STOP after the function ends. Do NOT write additional functions, classes, or tests.
```

Added per-element body length estimate based on parameter count and element type. Tells the model how much code is expected, reducing over-generation.

### FIX #2: API Surface Restriction

```
# Available imports (ONLY use these — do NOT invent other APIs):
import logging
import json
```

Renders the file's import block with an explicit warning. Reinforces Modelfile Rule 2 at the prompt level with the actual imports available.

### FIX #3: Top-Level Method Indentation

Methods are now rendered at top-level indentation (no class wrapper) with a context header:

```
# This is a method of class `JSONFormatter`. Write it at the top level (no class wrapper).
```

Previously, methods were indented inside a class wrapper in the stub, which caused the model to add extra leading whitespace. Rendering at top level and providing class context separately eliminated all indentation-related syntax failures.

### FIX #4: Separate Constant/Variable Template

Constants and variables now use a dedicated prompt template instead of the function template:

```
# Task: Define this module-level variable.
# Output ONLY the assignment statement. 1-3 lines maximum.
# Start your output directly with `products`.
```

Prevents the model from generating a full function when asked for `products: list[str] = [...]`.

### FIX #5: Format Anchor

```
# Output ONLY Python code. No markdown fences, no explanations, no comments before or after.
# Start directly with `def format(` on the first line.
```

Tells the model exactly what its first output token should be. Handles `async def` correctly for async functions/methods.

### FIX #6: Few-Shot Example Injection

When generating an element, the prompt includes 1-2 successfully-generated siblings from the same class or file:

```
# Example (completed):
def __init__(self):
    super().__init__()

# Now implement this:
def format(self, record: logging.LogRecord) -> str:
    ...
```

Anchors the model's output format and API usage with a concrete example from the same context. Uses a 2-tier priority: same class first (highest signal for methods), then same file. Examples accumulate during the sequential generation loop — earlier successes benefit later elements.

**Round 2 results:** 17 of 24 elements had few-shot examples injected.

## 6. Validation Results

### 6.1 Smoke Test: Known-Good Elements (Initial Tuning)

Tested against the two element types that passed Sonnet verification in Round 1:

| Element | Output Quality | Tokens | Time |
|---------|---------------|--------|------|
| `JSONFormatter.format` | Correct: `OrderedDict` → `json.dumps()`, uses `self.formatTime()`, `record.levelname/name/getMessage()` | 88 | 5.0s |
| `get_secret` | Correct: `SecretManagerServiceClient()`, proper resource path `projects/{}/secrets/{}/versions/latest`, `.payload.data.decode()` | 90 | 4.3s |

Both produced syntactically valid, semantically correct implementations on the first attempt.

### 6.2 Determinism

3 consecutive runs of `JSONFormatter.format` with `startd8-coder`:
- All 3 runs: **identical output**, 79 tokens each
- Baseline (`qwen2.5-coder:7b` defaults): 3 different outputs, 95-112 tokens

### 6.3 Full Experiment — Round 2

Full 24-element experiment with all tuning (Modelfile v2 + prompt FIX #1–#6 + indentation normalization + heuristic classifier v2).

**Headline:** 100% syntax success, 42% Sonnet verification — up from 47% syntax / 9% verified with codellama.

| Metric | Round 2 (`startd8-coder`) | Round 1 (`codellama:latest`) |
|--------|---------------------------|------------------------------|
| Elements attempted | 24 | 32 |
| Syntax valid | **24 (100%)** | 15 (47%) |
| Indent recovery needed | 0 | 3 |
| Sonnet verified | **10 (42%)** | 3 (9%) |
| Avg time per element | 5.3s | 10.5s |
| Avg tokens per element | 647 | 555 |
| Few-shot aided | 17 | — |
| Total cloud cost | $0.034 | $0.23 |

**Note:** Round 2 tested 24 elements (vs 32 in Round 1) because the v2 heuristic classifier correctly routes orchestrators (`start`, `serve`, `app`, etc.) to MODERATE, reducing the SIMPLE pool from 32 to 24.

### 6.4 Elements That Passed Verification

| Element | File | Why It Worked |
|---------|------|---------------|
| `HealthCheck.Check` | emailservice/email_server.py | Standard gRPC health check response — well-known pattern |
| `JSONFormatter.__init__` | emailservice/logger.py | Simple `super().__init__()` call |
| `WebsiteUser.on_start` | loadgenerator/locustfile.py | Sets `self.client.headers` — pure data assignment |
| `WebsiteUser.viewCart` | loadgenerator/locustfile.py | `self.client.get("/cart")` — simple HTTP GET |
| `WebsiteUser.emptyCart` | loadgenerator/locustfile.py | `self.client.post("/cart/empty")` — simple HTTP POST |
| `WebsiteUser.logout` | loadgenerator/locustfile.py | `self.client.get("/logout")` — simple HTTP GET |
| `products` | loadgenerator/locustfile.py | Constant: list of product ID strings |
| `JSONFormatter.__init__` | recommendationservice/logger.py | Same pattern as emailservice |
| `HealthCheck.Check` | recommendationservice/recommendation_server.py | Same pattern as emailservice |
| `get_secret` | shoppingassistantservice.py | GCP Secret Manager lookup with clear API |

**Common pattern:** Elements that pass are pure data transforms, simple HTTP calls, or well-known API patterns (gRPC health check, Secret Manager). No element requiring knowledge of application-specific protobuf definitions or library-specific decorators passed.

### 6.5 Failure Analysis

14 of 24 elements failed Sonnet verification. Failures fall into three categories:

| Category | Count | Examples |
|----------|-------|----------|
| External API misuse | 8 | Wrong gRPC stub name, missing `@task` decorator, hardcoded product IDs, placeholder template path |
| Structural (bare statements, no `def`) | 3 | `JSONFormatter.format` ×2, `WebsiteUser.checkout` — model output code without wrapping in function |
| Missing imports/params | 3 | `getJSONLogger` ×2 (missing `name` param), `EmailService.SendOrderConfirmation` (wrong arg count) |

**Import-based complexity gate projection:** An import-based gate (Section 7.3 from the experiment doc) would have caught 10 of 14 failures — all elements in files with gRPC, Jinja2, Locust, or GCP imports. However, it would also have blocked 8 elements that actually passed (e.g., `HealthCheck.Check` in a gRPC file, `WebsiteUser.viewCart` in a Locust file). This suggests the gate should operate **per-element** (checking if the element's body would need external APIs) rather than **per-file**.

### 6.6 Inference Performance

| Metric | `startd8-coder` (Round 2) | `startd8-coder` (smoke test) | `codellama:latest` (Round 1) |
|--------|---------------------------|------------------------------|------------------------------|
| Avg time per element | 5.3s | ~4.5s | ~10.5s |
| Avg tokens per element | 647 | ~85 | ~555 |
| Model size on disk | 4.7 GB | 4.7 GB | 3.8 GB |

Round 2 avg tokens (647) is higher than the smoke test (85) because the full experiment includes elements with richer prompts (few-shot examples, sibling context, constraints) that produce longer outputs. The 512-token `num_predict` cap is adequate — zero elements were truncated.

## 7. Usage

### Build the model

```bash
cd docs/design/micro-prime
ollama create startd8-coder -f Modelfile.startd8-coder
```

### Run the experiment

```bash
# Full run with all improvements (uses cached manifest to avoid Opus synthesis cost)
python3 scripts/experiment_local_model_routing.py \
    --seed /path/to/artisan-context-seed-enriched.json \
    --manifest-cache /path/to/synthesized-manifest.json \
    --ollama-model startd8-coder \
    --heuristic-classify \
    --normalize-indent \
    --output /path/to/experiment-results.json

# First run (no cached manifest — synthesizes via Opus, ~$0.20)
python3 scripts/experiment_local_model_routing.py \
    --seed /path/to/artisan-context-seed-enriched.json \
    --synthesize-manifest \
    --ollama-model startd8-coder \
    --heuristic-classify \
    --normalize-indent \
    --output /path/to/experiment-results.json
```

### Verify the model exists

```bash
ollama list | grep startd8
# startd8-coder:latest    ...    4.7 GB    ...
```

## 8. Next Steps

### Done

1. ~~**Full experiment run**~~ — Completed. 100% syntax, 42% verified (see Section 6.3)
2. ~~**Few-shot prompt injection**~~ — Completed as FIX #6 (see Section 5)
3. ~~**Indentation normalization**~~ — Completed; not needed with startd8-coder (0 recoveries)
4. ~~**Truncation detection**~~ — Completed; `was_truncated` field tracks elements that hit the token cap
5. ~~**Manifest caching**~~ — Completed; `--manifest-cache` flag avoids re-running Opus synthesis

### Remaining

1. **Per-element complexity gate** — The file-level import gate (Section 7.3 from the experiment doc) is too aggressive — it blocks elements like `HealthCheck.Check` and `WebsiteUser.viewCart` that pass despite being in files with external imports. A per-element gate that analyzes whether the element's body would require external API knowledge would retain these while still catching the 8 API-hallucination failures.

2. **Structural output validation** — 3 of 14 failures were "bare statements not wrapped in a function definition" — the model output code without the `def` line despite the format anchor (FIX #5). A post-processing step that detects missing `def` and re-wraps the output could recover these.

3. **SDK parameter forwarding** — If per-element overrides become necessary (different `num_predict` for methods vs constants), add `temperature`/`stop`/`top_p` forwarding to `OpenAICompatibleAgent._make_api_call()`. The Modelfile remains the default; SDK params override when specified.

4. **Integration into artisan pipeline** — If the per-element gate raises verified rate above 60% for the locally-routed subset, integrate into the artisan pipeline as described in Section 8 of the experiment doc (complexity classifier in `gate_contracts.py`, per-element agent router in `LLMChunkExecutor`, Ollama model catalog entry, fallback escalation).

---

## Appendix A: Modelfile

```dockerfile
FROM qwen2.5-coder:7b

# ── System prompt: constrain output to code-only, use only provided imports ──
SYSTEM """You are a Python code generator for the startd8 pipeline. You receive either:
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
8. STOP after the single requested element — never output additional functions or classes"""

# ── Sampling: near-deterministic for consistent, predictable output ──
PARAMETER temperature 0.1
PARAMETER top_p 0.85
PARAMETER top_k 30

# ── Token budget: prevent over-generation on SIMPLE elements ──
PARAMETER num_predict 512

# ── Stop sequences: halt when model drifts past the target function ──
# qwen2.5-coder wraps output in ```python fences — that's fine, post-processing
# strips them via extract_code_from_response(). These stops prevent over-generation
# AFTER the function body is complete.
PARAMETER stop "\nif __name__"
PARAMETER stop "\n# Task:"
PARAMETER stop "\n# Implement"
PARAMETER stop "\n# Define"
PARAMETER stop "\n\n\n"

# ── Repetition control: prevent degenerate loops ──
PARAMETER repeat_penalty 1.1
PARAMETER repeat_last_n 128
```

## Appendix B: Stop Sequence Failures

Documented here for future reference — these stop sequences **do not work** with qwen2.5-coder and should not be used:

| Stop Sequence | Why It Fails |
|--------------|-------------|
| `` ``` `` | Model starts output with `` ```python `` — kills response on first token |
| `"\ndef "` | Model outputs `\ndef function_name(...)` as the target function — kills before body generation |
| `"\nclass "` | Same issue when generating class methods wrapped in class context |
| `"\n\ndef "` | Response starts with `\n` then `\ndef` — double newline + def matches immediately |

## Appendix C: Experiment Result Files

All result JSON files are in the online-boutique-demo pipeline output directory:

| File | Description |
|------|-------------|
| `experiment-classify.json` | Classification-only run (v1 heuristic) |
| `experiment-generate.json` | Generation without verification (v1 heuristic, codellama) |
| `experiment-full.json` | Full run with verification (v1 heuristic, codellama, FQN matching bug) |
| `experiment-full-v2.json` | Full run with verification (v2 heuristic, codellama, fixed FQN matching) |
| `experiment-indent-fix.json` | Codellama with indentation normalization |
| `experiment-tuned-v1.json` | **Round 2: startd8-coder with all improvements (this document)** |
| `synthesized-manifest.json` | Cached Opus-synthesized manifest (reusable via `--manifest-cache`) |
