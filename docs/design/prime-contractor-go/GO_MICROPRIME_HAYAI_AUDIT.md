# Go MicroPrime Hayai Audit — Run-118 Findings

> **Run:** run-118-20260323T2326 (online-boutique, 40 Go features)
> **Date:** 2026-03-24
> **Principle:** [Hayai Design Principle](../../design-princples/HAYAI_DESIGN_PRINCIPLE.md)
> **Score:** 0.98 (40/40 PASS)

---

## Executive Summary

The Go MicroPrime pipeline is **structurally sound** — the multi-language wiring completed recently has established correct plumbing at every major integration point. Language detection, coding standards injection, template registration, splicer dispatch, syntax validation, and repair routing all operate correctly for Go. The 12 Go elements that entered MicroPrime were classified, generated, repaired, and validated using language-aware paths.

However, **three effectiveness gaps** limit the value MicroPrime delivers for Go compared to Python. These are not broken wiring — they are places where the infrastructure exists but doesn't yet reach its full potential. Each gap maps to a specific Hayai violation (quality knowledge available but not applied at the earliest effective stage).

---

## What's Working (Confirmed by Run-118)

### Enrichment (Grade: A)

- `coding_standards_injected: 40` — all 40 tasks got Go coding standards at plan ingestion time
- `language_id: "go"` persisted in all 40 task contexts
- `sanitize_code_examples()` called (0 transforms needed — plan was clean)
- Go `build_project_context_section()` injected 21+ structural rules into spec prompts

### Element Routing (Grade: B+)

- `_is_non_python_file("src/main.go")` returns `False` — Go files correctly enter MicroPrime
- `_get_microprime_extensions()` returns `.go` alongside all other registered profile extensions
- 12 Go elements classified as SIMPLE tier (correct — these are single-file utility modules)
- 28 features went file-whole (correct — these are multi-function service files, Dockerfiles, go.mod, HTML templates)

### Validation (Grade: A)

- `ast_parse_valid()` dispatches to `_try_parse()` → `gofmt -e` for Go (not Python `ast.parse()`)
- `structural_verify()` uses language-aware `_try_parse()` for non-Python
- `run_repair_pipeline()` receives `language_id="go"` (line 4120)
- The 3 `ast_failure` escalations are genuine Go syntax problems, not cross-language validation errors

### Repair (Grade: A-)

- `fence_strip` fired on 12/12 elements (100% — see gap H-GO-3 below)
- `bare_statement_wrap` applied to 3 elements with syntax issues
- Go repair routes fully wired: syntax, import, contamination, dot-import, unchecked-error
- 9/12 elements recovered successfully (75%)

### Semantic Checks (Grade: B+)

- 28 `unchecked_error` warnings across 11 features — correctly identified
- Zero `python_contamination` — complete elimination of Run-066 failure mode
- Kaizen suggestion emitted for the `unchecked_error` pattern (11 features, above threshold)

---

## Hayai Gaps: Quality Knowledge Available But Not Applied Early

### H-GO-1: Templates Registered But Never Matched (Contamination Distance: 0)

**What:** 7 Go templates are registered in `_LANGUAGE_TEMPLATES["go"]` (go_constructor, go_stringer, go_error, go_close, go_getter, go_setter, go_main). None matched any of the 12 SIMPLE elements in run-118.

**Why:** The 12 elements are file-level modules (tracker.go, money.go, middleware.go), each containing multiple functions. The templates match individual function patterns (e.g., `NewFoo` for constructors). There's a granularity mismatch: the element decomposer produced file-level elements, but the templates expect function-level elements.

**Hayai diagnosis:** The template knowledge exists and IS evaluated (the code reaches `registry.match()` at line 3840). The issue is upstream — the complexity classifier and element decomposer don't break Go files into function-level elements for the SIMPLE tier. Template matching runs but has nothing to match against.

**Impact:** Low for this run — all 12 elements succeeded via LLM generation. But template matching is zero-cost and deterministic (no LLM call), so every missed match is a wasted opportunity.

**Fix direction:** Enable the SIMPLE decomposer for Go. The `_function_body_decomposer` (line 3877) can break multi-function files into individual function elements, but it currently requires Python AST decomposition. The Go parser (`go_parser.py`) can extract function declarations, but the decomposer doesn't use it yet.

### H-GO-2: Go Splicer Available But Not Exercised (Contamination Distance: 0)

**What:** `go_splicer.py:splice_go_bodies()` is a tested, working splicer with brace-matching body replacement and gofmt normalization. `splicer.py:splice_body_into_skeleton()` has a Go dispatch (line 179: `_splice_go_dispatch()`). But in run-118, **no element used the splicer**.

**Why:** The splicer is called when MicroPrime generates a function body and needs to splice it into an existing skeleton. In run-118, the SIMPLE tier generated entire files (file-whole), not individual bodies. The splicer dispatch exists but the generation path doesn't produce body-level output to splice.

**Hayai diagnosis:** The splicer knowledge IS wired (dispatch exists). The gap is the same as H-GO-1 — elements are file-level, not function-level. When function-level decomposition is enabled, the splicer will engage automatically.

**Impact:** Medium. The splicer enables incremental generation (generate one function body, splice into skeleton, validate, repeat). Without it, the entire file is generated in one LLM call, which is more expensive and less controllable.

**Fix direction:** Same as H-GO-1 — enable function-level decomposition. The splicer wiring is already correct.

### H-GO-3: 100% Fence-Strip Rate Signals Prompt Gap (Contamination Distance: 0)

**What:** All 12 Go elements needed the `fence_strip` repair step. The LLM wraps every Go output in `` ```go...``` `` markdown fences despite the system prompt saying "Output raw file content exactly as it should appear on disk."

**Evidence from run-118:**

| Element | Repair Steps |
|---------|-------------|
| shippingservice_test | fence_strip, bare_statement_wrap |
| tracker | fence_strip |
| product_catalog | fence_strip |
| packaging_info | fence_strip |
| validator | fence_strip, bare_statement_wrap |
| rpc | fence_strip |
| product_catalog_test | fence_strip |
| money (frontend) | fence_strip |
| middleware | fence_strip, bare_statement_wrap |
| quote | fence_strip |
| money (checkout) | fence_strip |
| deployment_details | fence_strip |

**Hayai diagnosis:** The drafter system prompt contains the instruction, but for Go the Ollama model ignores it 100% of the time. The `fence_strip` repair step catches it — but every repair step adds latency and risk. This is knowledge the prompt should enforce (contamination distance 0 because the fix is in the same stage).

**Impact:** Low — fence_strip is fast and reliable. But the 100% rate means every Go element pays a ~50ms tax and runs through an unnecessary repair step.

**Fix direction:** Two options:
1. **Prompt reinforcement:** Add Go-specific instruction: "Do NOT wrap output in markdown code fences (no `` ```go `` blocks). Output ONLY the raw Go source code."
2. **Pre-validation strip:** Move fence detection from repair (post-generation) to extraction (pre-validation) — strip fences before validation, not after failure.

### H-GO-4: `unchecked_error` Kaizen Hint is Late-Bound (Contamination Distance: 2)

**What:** 28 `unchecked_error` warnings across 11 features. The Kaizen system correctly generated a suggestion, but the suggestion targets the **next run's** draft prompt — it doesn't affect the current run.

**Hayai diagnosis:** The coding standards already say "ALWAYS check returned errors with `if err != nil`" (injected at enrichment time via `coding_standards`). But the LLM still generates code that ignores errors. The knowledge IS bound early (enrichment), but the enforcement is only post-generation (semantic check → postmortem → next-run hint).

**Impact:** Medium. 11/40 features (27.5%) have unchecked errors. The Kaizen feedback loop will address this across runs, but within a single run, the error handling pattern isn't enforced at generation time.

**Fix direction:** This is a known limitation of LLM compliance with structural rules. Two mitigations:
1. **Stronger spec-time instruction:** Elevate `err != nil` from coding standards (general) to a P0 constraint (like the SQL injection security constraint).
2. **Template-level enforcement:** The `go_constructor` template could include `if err != nil` patterns. When function-level decomposition is enabled (H-GO-1), templates for common patterns (HTTP handlers, gRPC methods) could embed error handling.

---

## The 28 Non-MicroPrime Features

28/40 features went through file-whole LLM generation without element-level MicroPrime processing. Breakdown:

| Category | Count | Correct? | Notes |
|----------|-------|----------|-------|
| HTML templates (Go html/template) | 10 | Yes | `.html` files correctly bypass MicroPrime |
| go.mod files | 4 | Yes | Deterministic generation via `_try_generate_go_mod()` |
| Dockerfiles | 4 | Yes | Deterministic or file-whole (correct for Dockerfiles) |
| products.json | 1 | Yes | Data file — no element decomposition |
| Large Go service files | 9 | **Debatable** | main.go, handlers.go, server.go — multi-function files that could benefit from decomposition |

The 9 large Go service files are the opportunity. These include:
- PI-001: `main.go` (gRPC server bootstrap)
- PI-016: `main.go` (checkout orchestration)
- PI-023: `main.go` (frontend server, many routes)
- PI-024: `handlers.go` (cost outlier at $0.36 — largest file)

These files have 5-20+ functions each. With function-level decomposition, they could be generated incrementally with per-function validation, template matching, and splicer assembly — reducing cost and improving quality control.

---

## Scorecard

| Dimension | Grade | Status |
|-----------|-------|--------|
| Enrichment-time language binding | A | Fully Hayai-compliant |
| Spec-time coding standards | A | Forward-propagated from enrichment |
| Bypass gate (`.go` enters MicroPrime) | A | Correctly returns False for Go |
| Complexity classification | B+ | 12 elements classified; conservative but correct |
| Template matching | C | Registered, evaluated, but no matches (granularity mismatch) |
| Splicer dispatch | B- | Wired but not exercised (depends on function-level decomposition) |
| Validation gate | A | Language-aware — uses gofmt, not ast.parse() |
| Repair pipeline | A- | Fully wired; fence_strip saving all elements |
| Semantic checks | B+ | 6 checks firing; 28 findings correctly identified |
| Kaizen feedback loop | B+ | Suggestion generated; awaiting cross-run verification |

**Overall Go MicroPrime: B+**

The wiring is correct. The gaps are in element decomposition granularity (H-GO-1, H-GO-2), prompt compliance (H-GO-3), and enforcement strength (H-GO-4) — not in broken plumbing.

---

## Forensic Deep-Dive: Corrected Root Cause Analysis (Post-Planning)

The initial audit identified 4 gaps. A subsequent forensic deep-dive with 3 parallel code traces corrected and sharpened the analysis. The most significant finding: **the 3 `ast_failure` escalations were NOT caused by validation using Python AST on Go code** (as initially hypothesized). The validation gate IS language-aware (`ast_parse_valid()` → `_try_parse()` → `gofmt -e` for Go). The escalations were caused by **`bare_statement_wrap` producing Python `def` wrappers around Go code**.

### Corrected Escalation Root Cause Chain

```
Go element body generated by Ollama
  → fence_strip removes ```go fences (succeeds)
  → bare_statement_wrap checks _detect_definition_line(code)
  → _detect_definition_line() checks for "def ", "async def ", "class ", "@"
  → Go func body doesn't start with any of these → returns False
  → _build_def_line(element) generates "def tracker():" (Python syntax)
  → _wrap_body_in_def() wraps Go body in Python def signature
  → _ast_parse_valid() receives Python-Go hybrid → gofmt rejects it
  → ast_failure escalation
```

**Evidence chain:**
- `repair.py:237-240`: `_detect_definition_line()` only recognizes Python keywords
- `repair.py:391`: `_build_def_line(element)` delegates to `models.py:render_def_line()`
- `models.py:826-848`: `render_def_line()` always produces `def {name}():` or `class {name}:`
- `repair.py:614`: `_current_repair_language_id` is set but `_step_bare_statement_wrap()` never reads it
- `repair.py:363-426`: No language guard in the step function

### Corrected Finding: User Prompt is Python-Centric

The system prompt (`engine.py:_build_system_prompt()`, line 767) IS language-aware — it uses Go-specific indentation (tabs), stub markers (`panic("not implemented")`), and language role. But the user prompt (`prompt_builder.py:_build_element_prompt_core()`, line 142) contains:

- Line 230: `"Replace the \`raise NotImplementedError\` line"` — Python stub marker
- Line 234: `f"Indent every line with exactly {indent_spaces} spaces"` — Python indentation (Go uses tabs)
- Line 203: `"Output the full function: the \`def\` line"` — Python `def` keyword

No `language_id` or `language_profile` parameter is accepted. All 12 Go elements received Python-centric user prompts despite having Go-aware system prompts.

### Corrected Finding: Body-Only Mode is the Root Enabler

The 3 escalations wouldn't have occurred if Go elements used `full_function` mode instead of `body_only` mode. In `full_function` mode:
1. The LLM outputs the complete `func` declaration + body
2. `extract_function_body()` extracts the body (line 4103)
3. `bare_statement_wrap` detects the `func` keyword → returns no-op

But `extract_function_body()` at line 4103 uses Python `ast.parse()` — it would also fail for Go. So the correct fix is TWO-layered:
- Force `full_function` mode for non-Python (so the LLM returns `func` declarations)
- Guard `bare_statement_wrap` against non-Python (so body-only fallback doesn't produce Python wrappers)

### Planning-Derived Insight: This is a Multi-Language Issue, Not Go-Specific

Every finding above applies equally to Java, C#, and Node.js:
- `_detect_definition_line()` doesn't recognize `public void`, `private async Task`, `function`, `export default`
- `render_def_line()` would produce `def handle():` for a Java `public void handle()`
- The user prompt would tell a C# element to "use 4-space indentation" and "replace `raise NotImplementedError`"

These are systemic Python assumptions in code paths that all languages traverse. The requirements are formalized as language-agnostic **REQ-MPL-100 through REQ-MPL-105** in the [MicroPrime Language Enablement Playbook](../micro-prime/MICROPRIME_LANGUAGE_ENABLEMENT_PLAYBOOK.md).

---

## Requirements Cross-Reference

| Go Gap | Requirement | Scope | Status |
|--------|------------|-------|--------|
| H-GO-1 (templates) | Deferred | Go decomposer needed — separate effort | OPEN |
| H-GO-2 (splicer) | Deferred | Depends on H-GO-1 decomposer | OPEN |
| H-GO-3 (fence strip) | REQ-MPL-103 | All languages — pre-extraction strip | PLANNED |
| H-GO-4 (unchecked_error) | Existing Kaizen feedback | Cross-run improvement | IN PROGRESS |
| **NEW: bare_statement_wrap** | REQ-MPL-100 | All languages — repair isolation | PLANNED |
| **NEW: Python-centric prompt** | REQ-MPL-101 | All languages — profile-based prompts | PLANNED |
| **NEW: body-only mode** | REQ-MPL-102 | All non-Python — force full_function | PLANNED |
| **NEW: postmortem blind spot** | REQ-MPL-104 | All languages — new root cause | PLANNED |
| **NEW: leakage audit** | REQ-MPL-105 | Playbook — preventive checkpoint | PLANNED |
