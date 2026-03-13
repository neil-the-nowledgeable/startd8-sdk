# Ollama Output Quality Research Agenda

**Created:** 2026-03-13
**Status:** Open
**Context:** Micro Prime uses `qwen2.5-coder:7b` via Ollama for local Python code generation. File-whole generation is the primary path; element-by-element is fallback. A 14-step repair pipeline catches common defects post-generation. This document identifies research needed to improve raw output quality before repair.

## Current Baseline

- **Model:** qwen2.5-coder:7b (Modelfile at `docs/design/micro-prime/Modelfile.startd8-coder`)
- **Temperature:** 0.1 (per-call via API; Modelfile sampling params are overridden)
- **Token budget:** input=1024, output=2048 (per-call max_tokens overrides Modelfile num_predict=512)
- **File-whole thresholds:** max_elements=60, max_loc=600
- **Known failure patterns:** import echoing, bare statements, mixed indentation, structural drift, nested duplicate functions, module-level variable blindness (F821)
- **Repair rate (P0 baseline, 2026-03-13):** 91.8% of elements need ≥1 repair step (1,670/1,819). Top steps: extended_lint_fix (69%), fence_strip (35.5%), indent_normalize (5.6%), bracket_balance (3.7%). Invalid→valid recovery rate: 59% (262/444).

---

## 1. Model Selection and Sizing

### Questions
- How does `qwen2.5-coder:7b` compare to `qwen2.5-coder:14b` and `qwen2.5-coder:32b` on our workload? What is the quality/latency tradeoff curve?
- Are there newer code models (DeepSeek-Coder-V2, StarCoder2, CodeGemma, Codestral) that outperform Qwen on body-only and file-whole generation?
- What is the minimum model size that produces zero-repair-needed output for TRIVIAL and SIMPLE elements?
- Does quantization level (Q4_K_M vs Q5_K_M vs Q8_0 vs FP16) measurably affect code generation quality, or only speed/VRAM?
- Would a two-model strategy improve cost-quality (e.g., 7b for TRIVIAL/SIMPLE, 14b+ for MODERATE/file-whole)?

### Research Tasks
- [ ] Benchmark qwen2.5-coder at 7b, 14b, 32b on a fixed corpus of 50 elements across tiers
- [ ] Benchmark 3 alternative code models (DeepSeek-Coder-V2, CodeGemma, Codestral) on the same corpus
- [ ] Measure quality delta between Q4_K_M and Q8_0 quantization on 20 representative elements
- [ ] Profile generation latency per model size on target hardware (Apple Silicon M-series)
- [x] Evaluate whether `num_predict` (Modelfile) conflicts with `max_tokens` (API parameter) — which takes precedence? *(resolved 2026-03-13: API max_tokens overrides Modelfile num_predict. Modelfile had 512, API sends 2048. num_predict removed from Modelfile as dead config.)*

---

## 2. Prompt Engineering

### Questions
- The current element-body prompt uses 8 repetitive negative instructions ("Do NOT output a def line", "Do NOT write standalone statements"). Does this repetition help or hurt small models? Is there an instruction saturation point?
- Would positive-only framing ("Output ONLY indented body lines starting with 4 spaces") outperform negative framing ("Do NOT output a def line")?
- Does the order of prompt sections (imports → context → instructions → stub) matter? Would instructions-first improve compliance?
- How much does the `# Available imports` section contribute to import echoing? Would removing it reduce echoing more than it increases hallucinated imports?
- Does the estimated line count hint (`# The body MUST be 3-6 lines`) improve or constrain quality?
- Would structured output (JSON with a `code` field) eliminate fence/commentary contamination entirely?

### Research Tasks
- [x] A/B test positive-only vs negative-heavy instructions on 30 elements — measure repair rate *(initial rewrite shipped 2026-03-13: `_ELEMENT_BODY_SYSTEM_PROMPT` and `_FILE_WHOLE_SYSTEM_PROMPT` rewritten with structured FORMAT/IMPORTS/SCOPE headers and positive framing. A/B validation pending via eval harness.)*
- [ ] A/B test instructions-first vs instructions-last prompt ordering
- [ ] Measure import echoing rate with and without the `# Available imports` section
- [ ] Test line count hint removal — does output length variance increase? Does correctness change?
- [ ] Prototype JSON-mode generation (`{"code": "..."}`) and measure fence contamination rate vs current approach
- [ ] Test whether 4 vs 8 instruction lines changes compliance rate

---

## 3. File-Whole Generation

### Questions
- The file-whole path now handles files up to 60 elements / 600 LOC. What is the empirical quality cliff — at what file size does fill rate drop below 80%?
- Does providing the full skeleton (with `raise NotImplementedError` stubs) produce better output than providing element specs and asking the model to generate the file from scratch?
- Would a two-pass file-whole strategy (generate → validate → re-generate failed elements in context) outperform single-pass + element fallback?
- How does file-whole quality vary by file archetype (utility functions vs class hierarchies vs Flask/FastAPI routes vs test files)?
- Does the system prompt instruction "Do NOT define a function inside itself" actually prevent nested duplicates, or is the model ignoring it?

### Research Tasks
- [ ] Measure fill rate vs file size (elements and LOC) across 100 files to find the quality cliff
- [ ] Compare skeleton-based vs spec-based file-whole on 20 files
- [ ] Track nested duplicate rate before and after the system prompt fix
- [ ] Categorize file-whole failures by archetype to identify weak spots
- [ ] Prototype two-pass generation: full file → targeted re-generation of unfilled stubs

---

## 4. Sampling Parameters

### Questions
- Is temperature=0.1 optimal? Does 0.0 (greedy) produce measurably different quality?
- What is the effect of top_p and top_k on code correctness? The current values (0.85, 30) were chosen without empirical validation.
- Does `repeat_penalty=1.1` help prevent import echoing, or does it introduce subtle bugs by penalizing legitimate repeated patterns (e.g., `self.x`, repeated method calls)? *(Reduced to 1.05 / repeat_last_n 64 on 2026-03-13 based on analysis; empirical validation pending.)*
- Would `mirostat` sampling (Ollama-specific) produce more consistent output than top_p/top_k?
- Does `num_ctx` (context window size) affect quality when prompts are well within budget? Default Ollama num_ctx=2048 may be too small for file-whole.

### Research Tasks
- [ ] Sweep temperature [0.0, 0.05, 0.1, 0.2, 0.3] on 30 elements — measure syntax error rate and semantic correctness
- [ ] Sweep repeat_penalty [1.0, 1.05, 1.1, 1.15, 1.2] — measure echoing rate vs bug introduction
- [ ] Test mirostat_mode=2 (Mirostat 2.0) vs top_p/top_k on 20 elements
- [ ] Verify num_ctx is set appropriately for file-whole (needs to exceed skeleton + output tokens)
- [ ] Test num_ctx=[2048, 4096, 8192] on file-whole quality for files near the LOC threshold

---

## 5. Context and Few-Shot Strategy

### Questions
- The input token budget is 1024. Is this the right number? What happens at 512 vs 2048?
- Few-shot examples are capped at 2. Would 3-4 examples improve consistency, or does it crowd out the target element?
- Few-shot examples come from sibling elements. Would curated golden examples (per pattern type) outperform dynamic siblings?
- Does the quality-weighting of few-shot examples (non-repaired first) actually improve output? Or are repaired examples equally useful as demonstrations?
- How much does the module-level variable context (Fix 2 from the F821 investigation) improve generation for files with shared state?

### Research Tasks
- [ ] Sweep input_token_budget [512, 768, 1024, 1536, 2048] — measure quality vs prompt truncation rate
- [ ] Sweep max_few_shot_examples [0, 1, 2, 3, 4] — measure body correctness
- [ ] Create 10 curated golden examples per element type (getter, setter, init, handler, validator) and compare vs dynamic siblings
- [ ] A/B test repaired vs non-repaired few-shot example weighting
- [ ] Measure F821 rate on files with module-level variables before and after the module variable context injection

---

## 6. Stop Sequences and Output Boundaries

### Questions
- Are the current 9 element-body stop sequences sufficient? Are any false-positive (triggering too early)?
- The `\n\n\n` (triple newline) stop was changed to `\n\n\n\n` for file-whole because PEP 8 spacing triggered it. Are there other PEP 8 patterns that cause false stops?
- Would a sentinel-based approach (e.g., `# END_IMPLEMENTATION`) be more reliable than pattern-based stops?
- Does Ollama honor all stop sequences equally, or is there a limit/priority?
- How often does generation exhaust max_tokens vs hitting a stop sequence? If max_tokens is the primary terminator, stop sequences may be undertested.

### Research Tasks
- [x] Log which stop sequence terminates each generation over 100 runs — build a frequency table *(partial: finish_reason "stop" vs "length" now logged + OTel; API does not report which specific sequence)*
- [ ] Test sentinel-based stopping (`# END`) and measure false-stop rate vs pattern-based
- [ ] Verify Ollama's stop sequence limit (documentation says up to 4; we send 9 for element-body)
- [x] Measure max_tokens exhaustion rate — if high, output may be truncated rather than naturally completed *(instrumentation in place: `micro_prime.ollama_finish_reason_total{finish_reason="length"})*

---

## 7. Repair Pipeline Analysis

### Questions
- What is the current repair rate (% of elements needing ≥1 repair step)? Is it improving over time?
- Which repair steps fire most frequently? This indicates the most common model failure modes.
- What fraction of repairs are "cosmetic" (fence strip, import reorder) vs "structural" (bracket balance, indent normalize)?
- Are there failure patterns that repair cannot fix, causing escalation? What are they?
- Does the repair pipeline ever introduce new bugs (repair makes code worse)?
- Would feeding repair statistics back into prompt engineering reduce the repair rate?

### Research Tasks
- [x] Instrument repair pipeline to log step-level metrics per run (step name, file, element, before/after diff) *(done: `micro_prime.repair.*` OTel + structured log)*
- [x] Aggregate repair metrics over 10 production runs to build a failure mode histogram *(done 2026-03-13: 1,819 artifacts analyzed from `.startd8/repair/artifacts/`. See P0 Baseline above.)*
- [x] Identify top-3 repair steps by frequency — these are the highest-leverage prompt improvements *(done 2026-03-13: #1 extended_lint_fix 69%, #2 fence_strip 35.5%, #3 indent_normalize 5.6%. System prompts rewritten to target #1 and #2.)*
- [ ] Audit 20 repair outcomes for correctness (did repair actually fix the issue?)
- [x] Prototype "repair feedback loop": inject most-common-error guidance into system prompt *(done 2026-03-13: `_ELEMENT_BODY_SYSTEM_PROMPT` now includes explicit import-output ban targeting the 69% lint-fix rate, and specific ` ```python ` token targeting the 35.5% fence rate.)*

---

## 8. Evaluation Framework

### Questions
- How should we systematically measure output quality? Current metrics are binary (AST parses / stubs filled).
- Would a multi-dimensional quality score (syntax, imports, semantics, style, fill rate) be more useful?
- Can we build an automated regression test that runs the same seed through Micro Prime and compares output quality across model/prompt changes?
- Should we use an LLM-as-judge approach for semantic correctness, or is AST + lint sufficient?
- What is the right corpus size for statistically significant A/B tests?

### Research Tasks
- [x] Define a quality scoring rubric: syntax (0/1), imports correct (0/1), lint clean (0/1), semantic match (0-3), fill rate (0.0-1.0) *(done 2026-03-13: `src/startd8/micro_prime/eval_scoring.py` — ElementScore, FileScore, CorpusReport with 5 dimensions + weighted composite + pass threshold)*
- [x] Build a golden corpus of 50 elements with known-good implementations for regression testing *(done 2026-03-13: `tests/evaluation/golden_corpus/corpus.json` — 20 entries: 15 element-level (gc-001–gc-015) + 5 file-whole (gc-016–gc-020) covering getters, predicates, dunders, converters, filters, constants, validators, handlers, exceptions, class hierarchies, data models, utility modules)*
- [x] Prototype an automated evaluation harness: run generation → score → report *(done 2026-03-13: `scripts/run_eval_ollama.py` — --model, --mode, --repeat N, --dry-run, --output, --temperature, per-tier breakdown, multi-run statistics)*
- [ ] Determine minimum corpus size for 95% confidence in A/B comparisons (likely 30-50 elements per arm)
- [ ] Evaluate LLM-as-judge (Haiku scoring Ollama output) vs rule-based scoring cost/accuracy tradeoff

---

## 9. Ollama Runtime Configuration

### Questions
- What `num_ctx` does startd8-coder actually use? If the Modelfile doesn't set it, Ollama defaults to 2048, which may be too small for file-whole prompts.
- Does `num_gpu` (GPU layer offloading) affect generation quality, or only speed?
- Is there a measurable quality difference between Ollama's default KV cache and flash attention?
- Would running Ollama with `--verbose` logging reveal generation patterns (token probabilities, stop reasons) that inform prompt design?
- Does Ollama's `keep_alive` parameter (model caching) affect quality, or only cold-start latency?

### Research Tasks
- [x] Add `num_ctx: 8192` to Modelfile and verify file-whole prompts fit within context *(done in Modelfile.startd8-coder)*
- [ ] Test with `OLLAMA_DEBUG=1` on 10 generations — extract token-level log probabilities for quality analysis
- [ ] Measure cold-start vs warm-model quality (is there a JIT/compilation effect on first run?)

---

## 10. Fine-Tuning and Custom Models

### Questions
- Can we fine-tune qwen2.5-coder:7b on our own successful generation outputs to improve body-only compliance?
- How much training data would we need? We have production run logs with before/after repair pairs.
- Would LoRA fine-tuning on 500 successful body-only examples eliminate the import echoing pattern?
- Is Ollama's `ollama create` with a Modelfile + system prompt sufficient, or do we need actual weight updates?
- What is the cost/effort of maintaining a fine-tuned model vs improving prompts?

### Research Tasks
- [ ] Extract 200 successful (zero-repair) element generations from production logs as training data
- [ ] Extract 100 failed generations (pre-repair) as negative examples
- [ ] Evaluate LoRA fine-tuning feasibility on Apple Silicon (VRAM requirements, training time)
- [ ] Research Unsloth/Axolotl for efficient local fine-tuning of code models
- [ ] Compare fine-tuned model quality vs prompt-only improvements on the golden corpus

---

## Priority Ranking

| Priority | Topic | Expected Impact | Effort |
|----------|-------|-----------------|--------|
| **P0** | Evaluation framework (#8) | Enables all other research | Medium |
| **P0** | Repair pipeline analysis (#7) | Identifies highest-leverage improvements | Low |
| **P1** | Model selection benchmarks (#1) | May unlock step-change in quality | Medium |
| **P1** | Prompt engineering A/B tests (#2) | Direct quality improvement, low cost | Medium |
| **P1** | Sampling parameter sweep (#4) | Quick wins if current values are suboptimal | Low |
| **P2** | File-whole quality cliff (#3) | Informs threshold tuning | Medium |
| **P2** | Context and few-shot tuning (#5) | Moderate quality improvement | Medium |
| **P2** | Stop sequence audit (#6) | Prevents false truncation | Low |
| **P3** | Ollama runtime config (#9) | May fix subtle context issues | Low |
| **P3** | Fine-tuning feasibility (#10) | High potential but high effort | High |

## Next Steps

1. ~~Instrument the repair pipeline (P0)~~ — *done 2026-03: OTel + structured logging*
2. ~~Aggregate repair metrics (P0)~~ — *done 2026-03-13: 1,819 artifacts → failure mode histogram*
3. ~~Build the evaluation framework (P0)~~ — *done 2026-03-13: eval_scoring.py + corpus.json + run_eval_ollama.py*
4. ~~Rewrite system prompts (P1)~~ — *done 2026-03-13: positive framing, structured headers, repair-informed import/fence guidance*
5. ~~Strip dead Modelfile config~~ — *done 2026-03-13: SYSTEM, temperature, top_p, top_k, num_predict, stops removed (all overridden by API)*
6. **Rebuild Ollama model** — `ollama create startd8-coder -f Modelfile.startd8-coder` to apply repeat_penalty/repeat_last_n changes
7. **Run baseline evaluation** — `python3 scripts/run_eval_ollama.py --repeat 3 --output results/baseline.json` to establish pre-improvement baseline
8. **A/B validate prompt rewrite** — compare old vs new system prompt on the golden corpus
9. Run model comparison benchmarks (P1) — determine if a model upgrade is the fastest path

---

## Implemented Instrumentation (2026-03)

### Repair Pipeline (Section 7)
- **Structured logging**: `micro_prime.repair.complete` at INFO with `extra.repair` (pipeline_mode, ast_valid_before/after, repair_recovered, steps_applied, wall_clock_ms)
- **OTel metrics**: `micro_prime.repair.attempts_total`, `micro_prime.repair.recovered_total`, `micro_prime.repair.step_applied`, `micro_prime.repair.wall_clock_ms` (labels: pipeline_mode, step)

### Modelfile (Section 9)
- **num_ctx: 8192** added to `Modelfile.startd8-coder` — file-whole prompts need skeleton + output tokens; default 2048 was too small

### P0 Repair Baseline (Section 7) — 2026-03-13
- **Data source**: 1,819 repair artifacts from `.startd8/repair/artifacts/`
- **Overall repair rate**: 91.8% (1,670/1,819 elements need ≥1 repair step)
- **Invalid→valid recovery**: 59.0% (262/444 invalid inputs recovered)
- **Step frequency histogram**:
  | Rank | Step | Fire Rate | Category |
  |------|------|-----------|----------|
  | 1 | `extended_lint_fix` | 69.0% | Cosmetic (unused imports, F821, trailing whitespace) |
  | 2 | `fence_strip` | 35.5% | Cosmetic (markdown code fences) |
  | 3 | `indent_normalize` | 5.6% | Structural (mixed tabs/spaces) |
  | 4 | `bracket_balance` | 3.7% | Structural (unclosed parens) |
  | 5 | `import_completion` | 0.3% | Structural (missing stdlib imports) |
- **Error category routing**: lint_violation 79.2%, syntax_error 12.6%, semantic_error 8.2%, missing_import 0.3%
- **Key insight**: Two cosmetic failure modes (lint + fences) account for ~80% of all repairs

### System Prompt Rewrite (Sections 2, 7, 9) — 2026-03-13
- **Critical finding**: Modelfile SYSTEM prompt (8 rules) was dead code — overridden by per-call `system_prompt` parameter in `engine.py:_generate_ollama()`. Per-call prompts had only 2-4 constraints, missing import ban, scope limits, and tab prohibition.
- **Critical finding**: Modelfile `num_predict=512` overridden by API `max_tokens=2048`. Modelfile `temperature`, `top_p`, `top_k`, and stop sequences also overridden.
- **Fix**: Rewrote `_ELEMENT_BODY_SYSTEM_PROMPT` and `_FILE_WHOLE_SYSTEM_PROMPT` in `engine.py` with:
  - Structured `FORMAT:` / `IMPORTS:` / `SCOPE:` headers (small models parse structured prompts better)
  - Positive framing ("Start every line with exactly 4 spaces") instead of negative ("Do NOT...")
  - Explicit import-output ban targeting the 69% lint-fix rate
  - Specific `` ```python `` token reference targeting the 35.5% fence rate
- **Modelfile cleanup**: Removed all dead config (SYSTEM, temperature, top_p, top_k, num_predict, stop sequences). Only active params remain: `num_ctx 8192`, `repeat_penalty 1.05`, `repeat_last_n 64`.
- **repeat_penalty**: Reduced from 1.1/128 to 1.05/64 — code legitimately repeats `self.`, `return`, `if/elif`.
- **Commit**: `f629932`

### Evaluation Framework (Section 8) — 2026-03-13
- **Scoring rubric**: `src/startd8/micro_prime/eval_scoring.py` — 5 dimensions:
  - `score_syntax()`: AST parse (0/1)
  - `score_imports()`: no hallucinated imports (0/1), stdlib allowlist
  - `score_lint()`: ruff E/F codes (0/1)
  - `score_semantic()`: structural similarity to reference (0-3), with constant-aware fallback
  - `score_fill_rate()`: stub fill fraction (0.0-1.0) for file-whole
  - `score_element()`: composite scorer returning `ElementScore`
  - `CorpusReport`: aggregated report with `to_dict()` for JSON export
- **Golden corpus**: `tests/evaluation/golden_corpus/corpus.json` — 20 entries:
  - 15 element-level (gc-001–gc-015): getters, predicates, dunders, converters, filters, constants, validators, handlers, exceptions, classes with properties
  - 5 file-whole (gc-016–gc-020): utility modules (3-6 functions), class hierarchies, data models with serialization, exception modules
  - Each entry: ForwardFileSpec + skeleton + reference implementation + expected tier
- **Evaluation harness**: `scripts/run_eval_ollama.py`:
  - `--model` for A/B model comparison
  - `--mode element|file_whole` for Section 3 research
  - `--repeat N` for statistical significance
  - `--dry-run` for harness validation (no Ollama)
  - `--output` for JSON report persistence
  - `--temperature` for sampling parameter sweeps
  - Per-tier breakdown, failure detail, multi-run statistics (mean ± std)

### Stop Sequence Verification (Section 6)
- **Structured logging**: `ollama.generation.finish` at DEBUG with `extra.ollama` (finish_reason, entity_name, output_tokens, input_tokens)
- **OTel counter**: `micro_prime.ollama_finish_reason_total` with label `finish_reason` — build frequency table in Grafana (e.g. `rate(micro_prime_ollama_finish_reason_total[1h]) by (finish_reason)`)
- **Note**: OpenAI-compatible API returns `"stop"` (natural stop) or `"length"` (max_tokens exhausted). The API does not report which specific stop sequence triggered; use `finish_reason=length` rate to infer max_tokens exhaustion frequency.
