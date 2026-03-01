# Local Model Routing Experiment — Results & Analysis

**Date:** 2026-03-01
**Status:** Experiment Complete (Round 1)
**Seed:** online-boutique-demo (17 tasks, 7 Python microservices)
**Local Model:** codellama:latest (7B) via Ollama
**Cloud Models:** Opus 4.6 (manifest synthesis), Sonnet 4.6 (verification)

---

## 1. Hypothesis

The Forward Manifest + Deterministic File Assembly pipeline produces enough structural context (full signatures, type hints, imports, binding constraints) that a local coding model can reliably fill in function bodies for simple elements — reducing cloud API cost while maintaining code quality.

## 2. Architecture

```
Opus (T1)  ──►  Synthesize ForwardManifest from task descriptions
                 (one-time cost: ~$0.20)
                      │
                      ▼
Heuristic  ──►  Classify each ForwardElementSpec:
                 SIMPLE / MODERATE / COMPLEX
                 (zero cost — manifest signal analysis)
                      │
                      ▼
Ollama     ──►  Generate function bodies for SIMPLE elements
                 (zero cloud cost — local inference)
                      │
                      ▼
Sonnet     ──►  Verify generated code for semantic correctness
                 (batch review: ~$0.03)
```

### What the local model receives per element

Each Ollama prompt is self-contained and includes:
- The function stub with full signature (params, types, return annotation)
- The file's import block (stdlib / third-party / local)
- Sibling method signatures (for class context)
- Binding constraints from InterfaceContracts (`[BINDING]` / `[ADVISORY]`)
- Docstring hint describing intent

This mirrors what the deterministic file assembler would produce — the LLM just fills in `raise NotImplementedError` bodies.

## 3. Experiment Setup

### Seed

The online-boutique-demo enriched seed had 17 tasks across 7 Python services but an empty `ForwardManifest.file_specs` (plan ingestion did not populate `api_signatures`). A synthesis step was added where Opus extracts `ForwardElementSpec` entries from task descriptions.

### Script

`scripts/experiment_local_model_routing.py` — standalone experiment script that:
1. Loads an enriched seed JSON
2. Optionally synthesizes manifest via Opus (`--synthesize-manifest`)
3. Classifies elements via heuristic or Opus (`--heuristic-classify`)
4. Generates SIMPLE element bodies with Ollama
5. Validates syntax with `ast.parse()`
6. Optionally verifies semantics with Sonnet

### Heuristic Classifier Signals

| Signal | Effect on Score |
|--------|----------------|
| 0-2 real params (excl. self/cls) | -1 (simpler) |
| 5+ params | +2 (complex) |
| `*args` / `**kwargs` | +1 |
| Simple return type (str, int, bool, etc.) | -1 |
| Simple name prefix (get_, is_, has_, to_, from_, as_) | -1 |
| No binding constraints | -1 |
| 3+ binding constraints | +2 |
| Complex decorators (abstractmethod, overload, contextmanager) | +2 |
| Async function/method | +1 |
| Class definition | +2 |
| Long docstring hint (>100 chars) | +1 |
| **Orchestrator name** (start, serve, main, run, setup, etc.) | → MODERATE |
| **Orchestrator suffix** (_handler, _pipeline, _workflow, _server) | → MODERATE |
| **Orchestrator docstring** (standalone functions only) | → MODERATE |
| **App instance constant** (app, server, api) | → MODERATE |

Score ≤ -1 → SIMPLE, score ≤ 2 → MODERATE, score > 2 → COMPLEX.

## 4. Results

### Classification (after heuristic tuning)

| Classification | Count | Examples |
|---------------|-------|---------|
| SIMPLE | 28-32 | `JSONFormatter.format`, `get_secret`, `WebsiteUser.viewCart` |
| MODERATE | 4-7 | `start`, `serve`, `app`, `init_alloydb_engine`, `chat` |
| COMPLEX | 0 | (none in this seed — microservice glue code) |

### Generation (3 runs, codellama:latest 7B)

| Metric | Run 1 | Run 2 | Run 3 |
|--------|-------|-------|-------|
| Heuristic version | v1 | v1 | v2 (orchestrator detection) |
| SIMPLE attempted | 34 | 34 | 32 |
| Syntax valid | 25 (74%) | 20 (59%) | 15 (47%) |
| Avg time per element | 10.5s | — | 11.6s |
| Avg tokens per element | 585 | — | 555 |

Syntax success rate varied 47-74% across runs — codellama is non-deterministic, with indentation being the primary failure mode.

### Verification (Sonnet semantic review)

| Metric | Run 2 | Run 3 |
|--------|-------|-------|
| Syntax-valid reviewed | 20 | 15 |
| Sonnet PASS | 1 (5%) | **3 (20%)** |
| Sonnet FAIL | 1 | **12** |
| Not matched (FQN bug) | 18 | 0 |

**End-to-end usable code: 3/32 = 9%**

### Elements That Passed Verification

| Element | File | Why It Worked |
|---------|------|---------------|
| `JSONFormatter.format` | emailservice/logger.py | Pure data transform: log record → ordered JSON dict → string |
| `JSONFormatter.format` | recommendationservice/logger.py | Same pattern, different service |
| `get_secret` | shoppingassistantservice.py | Simple GCP Secret Manager lookup with clear API |

### Cost Summary

| Component | Cost |
|-----------|------|
| Manifest synthesis (Opus, one-time) | ~$0.20 |
| Heuristic classification | $0.00 |
| Ollama generation (32 elements) | $0.00 |
| Sonnet verification | ~$0.03 |
| **Total per run** | **~$0.23** |

For comparison, generating all 32 elements with Sonnet would cost approximately $1.50-2.00 (est. 500 tokens/element at Sonnet pricing), and with Haiku approximately $0.15-0.20.

## 5. Failure Analysis

### Failure Mode 1: Syntax Errors (53% of attempts)

**Primary cause: Indentation mangling during code extraction.**

The code extractor (`extract_code_from_response`) strips markdown fences but does not normalize indentation. codellama frequently returns code with:
- Extra leading whitespace (method body indented as if inside a class the LLM imagined)
- Mixed tabs and spaces
- Unindented continuation lines

| Error Type | Count | Example |
|------------|-------|---------|
| `unexpected indent` | 7 | Method code starts at wrong indentation level |
| `invalid syntax` | 6 | Over-generation runs past the function into invalid territory |
| `unindent does not match` | 2 | Mixed indentation levels |
| `unterminated string literal` | 1 | Multi-line string truncated |
| `unmatched ')'` | 1 | Over-generated code with unclosed parens |

**Key insight:** ~60% of syntax failures are indentation-related and mechanically fixable.

### Failure Mode 2: API Hallucination (80% of syntax-valid code)

Even when code parses, codellama invents APIs it doesn't know:

| Issue | Count | Example |
|-------|-------|---------|
| Wrong enum/constant path | 3 | `health_pb2.SERVING` instead of `health_pb2.HealthCheckResponse.SERVING` |
| Missing imports used in body | 3 | Uses `datetime`, `traceback` without importing |
| Wrong behavior | 2 | Logs to file instead of stdout (container anti-pattern) |
| Hallucinated class names | 2 | Generated `UserBehavior` class instead of implementing `WebsiteUser` method |
| Local variables never stored | 1 | `init_clients` initializes clients into locals that are never returned |
| Wrong method signature usage | 1 | `getJSONLogger().name().build()` — nonexistent method chain |

**Key insight:** codellama succeeds only when the function body requires **no knowledge of external library APIs**. Pure data transforms and simple stdlib usage work; anything requiring gRPC, Jinja2, GCP client libraries, or Locust APIs fails.

### Failure Mode 3: Over-Generation

Some elements triggered codellama to generate far more code than needed:

| Element | Expected | Got | Tokens |
|---------|----------|-----|--------|
| `app` (constant) | `app = Flask(__name__)` | Entire Flask app with routes | 1600 |
| `start` (function) | 10-15 line server setup | Full gRPC server with interceptors | 752 |
| `send_request` | Simple gRPC call | Full client with retry logic | 2225 |

The orchestrator heuristic (v2) now catches most of these, but over-generation also occurs within SIMPLE elements when the prompt doesn't constrain output length.

## 6. Viable Surface for Local Models

Based on the experiment, the elements where a 7B local model succeeds reliably share these properties:

| Property | Required |
|----------|----------|
| Pure data transformation | Yes — no external API calls in the body |
| 0-2 real parameters | Strong signal |
| Simple return type | Helpful but not sufficient alone |
| Parent class exists | Constrains scope (method vs. free function) |
| All types in stdlib or builtins | Required — local model can't learn library APIs from a prompt |
| Short expected body (<15 lines) | Reduces over-generation risk |

**Estimated viable surface:** For a typical Python microservices project, ~10-15% of elements meet all these criteria. For a library/SDK project with more pure logic and less I/O, this could be higher (20-30%).

## 7. Suggested Improvements

### 7.1 Indentation Normalization (High Impact, Low Effort)

Add a post-processing step before `ast.parse()`:

```python
import textwrap

def normalize_indentation(code: str, is_method: bool) -> str:
    """Strip common leading whitespace, then re-indent if method."""
    dedented = textwrap.dedent(code)
    if is_method:
        # Re-indent to 4 spaces for method body
        return textwrap.indent(dedented, "    ")
    return dedented
```

**Expected impact:** Recover 7-10 of the ~17 syntax failures per run (the indentation-only errors). Would raise syntax success rate from ~50% to ~75%.

### 7.2 Stronger Local Model (High Impact, Medium Effort)

`codellama:latest` is a general-purpose coding model. Alternatives with better structured output:

| Model | Size | Strength |
|-------|------|----------|
| `qwen2.5-coder:7b` | 7B | Best-in-class for code completion at 7B; strong at following type signatures |
| `deepseek-coder-v2:16b` | 16B | Better API awareness, fewer hallucinations |
| `codellama:13b` | 13B | Same family, better reasoning |

**Expected impact:** qwen2.5-coder:7b likely raises Sonnet-verified pass rate from 20% to 40-50% based on published benchmarks for function-level completion.

### 7.3 Import-Based Complexity Gate (Medium Impact, Low Effort)

Add a signal to the heuristic classifier: if the file's imports include external libraries (gRPC, Flask, Jinja2, cloud SDKs), bump the complexity score. The local model can't learn library APIs from a single prompt.

```python
_EXTERNAL_API_PACKAGES = {
    "grpc", "grpcio", "flask", "fastapi", "jinja2", "django",
    "google.cloud", "google.auth", "boto3", "azure",
    "sqlalchemy", "alembic", "celery", "redis",
    "locust",  # caught by this experiment
}

# In classify_element_heuristic:
external_imports = set()
for imp in file_spec.imports:
    pkg = imp.module.split(".")[0]
    if pkg in _EXTERNAL_API_PACKAGES:
        external_imports.add(pkg)

if external_imports:
    complexity_score += len(external_imports)
    reasons.append(f"external APIs: {', '.join(external_imports)}")
```

**Expected impact:** Would have caught 8 of the 12 Sonnet failures (gRPC, Jinja2, GCP, Locust elements).

### 7.4 Max Token Cap Per Element (Low Effort)

Reduce `--max-tokens` from 2048 to 512 for SIMPLE elements. Over-generation happens when the model has too much token budget. A 512-token cap forces the model to produce concise implementations.

**Expected impact:** Would prevent the worst over-generation cases (`app` at 1600 tokens, `send_request` at 2225 tokens). Truncated output is detectable and can be re-routed to a cloud model.

### 7.5 Few-Shot Examples in Prompt (Medium Impact, Medium Effort)

Include 1-2 completed function examples from the same file or project. This gives the local model a concrete output format and API usage pattern to follow.

```
# Example (completed):
def getJSONLogger(name: str) -> logging.Logger:
    """Get a logger that outputs JSON to stdout."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)
    return logger

# Now implement this:
def send_confirmation_email(email: str, order: dict) -> None:
    ...
```

**Expected impact:** Anchors the model's output style and API usage. Particularly effective for repetitive patterns (multiple services with identical logger setup, similar gRPC handlers).

### 7.6 Retry with Indentation Fix Before Escalation (Low Effort)

Before routing a syntax failure to a cloud model, try:
1. `textwrap.dedent()` + re-parse
2. Strip first/last line (often explanation text) + re-parse
3. Only then escalate

This creates a "fix locally, escalate only if needed" pattern that maximizes local model value.

### 7.7 Synthesized Manifest Caching (Low Effort)

The Opus synthesis step ($0.20) produces the same manifest every time for the same seed. Cache it:
- The script already saves `synthesized-manifest.json` when `--output` is set
- Add `--manifest-cache` flag to load a pre-synthesized manifest instead of re-running Opus
- Reduces repeat experiment cost from $0.23 to $0.03 (verification only)

## 8. Integration Path

If the experiment proves viable at higher success rates (>60% end-to-end with a stronger model), integration into the artisan pipeline would require:

1. **Complexity classifier** in `gate_contracts.py` — reads `ForwardElementSpec` signals, outputs tier
2. **Per-element agent router** in `LLMChunkExecutor` — selects `ollama:{model}` for SIMPLE, cloud agent for MODERATE/COMPLEX
3. **Ollama model catalog entry** in `model_catalog.py` — with appropriate `max_tokens` defaults
4. **Indentation normalizer** in `code_extraction.py` — post-processing step for local model outputs
5. **Fallback escalation** — syntax-invalid or verification-failed elements re-queued to cloud model

The existing `ArtisanChunkExecutor` already processes tasks individually and supports multiple agent specs (`drafter_spec`, `refiner_spec`, `tier3_drafter_spec`). Adding an `ollama_spec` for SIMPLE elements is architecturally straightforward.

## 9. Conclusion

**codellama:latest (7B) is not viable for production use** in this pipeline — 9% end-to-end success rate is too low. However, the experiment validated the architecture:

- The Forward Manifest provides sufficient structural context for per-element routing
- The heuristic classifier correctly separates orchestrators from simple functions
- The prompt format (stub + imports + sibling context + constraints) is sound
- The verification step reliably catches semantic errors

The bottleneck is the local model's capability, not the pipeline design. A stronger model (qwen2.5-coder, deepseek-coder) combined with indentation normalization and import-based complexity gating could push the viable surface to 30-50% of elements at zero marginal cloud cost.

## Appendix A: Files

| File | Purpose |
|------|---------|
| `scripts/experiment_local_model_routing.py` | Experiment runner script |
| `docs/design/scaffold/DETERMINISTIC_FILE_ASSEMBLY_REQUIREMENTS.md` | Foundation: stub generation from ForwardManifest |
| `src/startd8/forward_manifest.py` | ForwardManifest schema models |
| `src/startd8/utils/code_manifest.py` | ElementKind, Signature, Param models |

## Appendix B: Raw Results

Results JSON files in the online-boutique-demo pipeline output:
- `experiment-classify.json` — classification-only run (v1 heuristic)
- `experiment-generate.json` — generation without verification (v1)
- `experiment-full.json` — full run with verification (v1 heuristic, FQN matching bug)
- `experiment-full-v2.json` — full run with verification (v2 heuristic, fixed FQN matching)
