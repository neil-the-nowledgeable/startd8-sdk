# Kaizen Investigation: PI-001/PI-002 Shared JSON Logger — Micro Prime Root Cause Analysis

## Summary

PI-001 (emailservice logger) and PI-002 (recommendationservice logger) implement identical ~30-line "Shared JSON Logger" specs for different microservices. Both consistently fail micro prime local generation across ALL online-boutique runs (run-008 through run-033), requiring cloud fallback at ~$0.09/feature. The root cause is architectural: element-by-element body-only decomposition is an unnatural output format for the local Ollama model on small files.

## Runs Analyzed

- online-boutique run-008 through run-033 (2026-03-07 through 2026-03-10)
- All runs from `/Users/neilyashinsky/Documents/dev/online-boutique-demo/.cap-dev-pipe/pipeline-output/online-boutique/`

## Evidence: Micro Prime Has Never Completed This File Locally

Every run shows `mp_cost=0.0` with cloud fallback rescuing:

| Run | Feature | mp_cost | fb_cost | fb_delegated | Outcome |
|-----|---------|---------|---------|--------------|---------|
| run-008 | PI-002 | $0.00 | $0.11 | 1 | SUCCESS (cloud) |
| run-015 | PI-002 | $0.00 | $0.11 | 1 | SUCCESS (cloud) |
| run-019 | PI-002 | $0.00 | $0.10 | 2 | SUCCESS (cloud) |
| run-020 | PI-001 | $0.00 | $0.09 | 2 | SUCCESS (cloud) |
| run-022 | PI-002 | $0.00 | $0.10 | 2 | SUCCESS (cloud) |
| run-024 | PI-001 | $0.00 | $0.10 | 2 | SUCCESS (cloud) |
| run-027 | PI-001 | $0.00 | $0.09 | 2 | SUCCESS (cloud) |
| run-028 | PI-001 | $0.00 | $0.09 | 2 | SUCCESS (cloud) |
| run-029 | PI-001 | N/A | N/A | N/A | FAILED ("No files integrated") |
| run-033 | PI-002 | $0.00 | $0.09 | 1 | SUCCESS (cloud) |

**Zero local successes across 10+ runs.**

## Element-Level Failure Analysis (run-033, PI-002)

The file has 3 elements. Micro prime processes them individually:

| Element | Tier | Ollama Output | Result |
|---------|------|---------------|--------|
| `add_fields` (method) | SIMPLE | Body code with mixed indentation; missing `self` | SUCCESS (repaired) |
| `CustomJsonFormatter` (class) | MODERATE | Class body with bare conditionals (no method structure) | SUCCESS (ollama_whole) |
| `getJSONLogger` (function) | SIMPLE | Only imports (5 lines, 26 tokens) — no function body at all | **FAILED -> escalated** |

### `getJSONLogger` raw Ollama output

```
\`\`\`python
import json
import logging
from logging.handlers import StreamHandler
from pythonjsonlogger import jsonlogger
```

The model produced 4 import lines, hit a stop boundary, and stopped. The repair pipeline stripped the fence and wrapped bare statements into `def getJSONLogger(name: str) -> logging.Logger: pass`, but structural verification caught `missing return for -> logging.Logger` and escalated.

### Why the model produced imports instead of a function body

The element prompt contains an `# Available imports` section that lists concrete import statements as context. The model echoed these back instead of generating the function body. The system prompt says "no imports" but the user prompt contains literal import lines — a conflict that small models resolve by following the concrete pattern.

## Root Cause: Architectural Mismatch

**The engine decomposes a trivial ~30-line file into 3 separate element-body prompts.** Each prompt asks Ollama to produce "only the indented body lines — no def line, no imports, no fences." This output format is:

1. **Unnatural**: The model is trained on complete Python files, not isolated body fragments
2. **Fragile**: 3 independent LLM calls x repair x splice x verify = many failure points
3. **Confusing**: The prompt contains import lines as context, which the model echoes back
4. **Unnecessary**: A 30-line file with 3 elements doesn't need decomposition — the model can generate the whole file in one shot

Meanwhile, the cloud fallback succeeds every time by generating the **complete file at once**. The cloud path (spec -> draft -> review) produces a full, correct `logger.py` in a single LLM call.

### Symptom Fixes Applied (Insufficient)

Three fixes were attempted as uncommitted changes to address downstream symptoms:

| Fix | Target | What It Does | Why It's Insufficient |
|-----|--------|-------------|----------------------|
| Fix 1: `_ELEMENT_BODY_SYSTEM_PROMPT` | engine.py | Separate system prompt for body-only generation | Doesn't prevent model from echoing imports |
| Fix 2: `_structural_reindent` | indent_normalize.py | New repair strategy for non-uniform indentation | Fixes `add_fields` indentation but doesn't help `getJSONLogger` which produces no body at all |
| Fix 3: Raw text passthrough | engine.py | Returns raw Ollama text to repair pipeline instead of pre-extracting | Better separation of concerns but doesn't fix the generation quality |

None of these address the core issue: **the decomposition strategy doesn't match the model's capability for small files.**

## Solution: File-Level Ollama-Whole Strategy

Added `_attempt_file_ollama_whole()` to `MicroPrimeEngine.process_file()` — generates the **complete file** in a single Ollama call before falling through to element-by-element decomposition.

### Implementation

- **Config**: `file_ollama_whole_enabled` (default: `True`), `file_ollama_whole_max_elements` (default: 5), `file_ollama_whole_max_loc` (default: 60)
- **Prompt**: `_build_file_whole_prompt()` sends the skeleton with `raise NotImplementedError` stubs and asks the model to fill ALL stubs, outputting the complete Python file
- **System prompt**: `_FILE_WHOLE_SYSTEM_PROMPT` — "Replace EVERY raise NotImplementedError with a working implementation. Output the COMPLETE Python file."
- **Validation**: `_validate_file_whole_result()` checks AST parse, no remaining stubs, no skeleton markers, all expected elements present
- **Fallthrough**: If file-whole fails (validation, empty output, Ollama error), falls through to the existing element-by-element path with no side effects

### Eligibility Criteria

- `file_ollama_whole_enabled` is `True`
- Element count <= `file_ollama_whole_max_elements` (default: 5)
- Skeleton LOC <= `file_ollama_whole_max_loc` (default: 60)
- Skeleton has at least one `raise NotImplementedError` stub

### Expected Impact

- PI-001 and PI-002 should complete locally at $0.00 instead of $0.09/feature
- Reduces Ollama calls from 3 per file to 1 for eligible files
- Eliminates splicing/assembly failure modes for small files
- Cloud fallback still available as safety net if file-whole also fails

### Files Changed

- `src/startd8/micro_prime/models.py` — 3 new config fields
- `src/startd8/micro_prime/engine.py` — `_FILE_WHOLE_SYSTEM_PROMPT`, `_build_file_whole_prompt()`, `_validate_file_whole_result()`, `_is_file_ollama_whole_eligible()`, `_attempt_file_ollama_whole()`
- `tests/unit/micro_prime/test_file_ollama_whole.py` — 21 tests (prompt, validation, eligibility, integration)

## Cross-Reference

- Guide: `docs/design/prime/KAIZEN_DATA_ANALYSIS_GUIDE.md` (Section 6: Micro-Prime Artifacts, Section 8: Cross-Feature Comparison)
- Related: `docs/design/kaizen/KAIZEN_INVESTIGATION_RUN005_ONLINE_BOUTIQUE.md`
- Design Principle: Mottainai — don't waste cloud budget on files the local model can handle
