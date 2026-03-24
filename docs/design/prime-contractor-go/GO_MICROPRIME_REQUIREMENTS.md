# Go MicroPrime Requirements — Refinement & Enhancement

> **Version:** 1.0.0
> **Status:** DRAFT
> **Date:** 2026-03-24
> **Parent:** [REQ-MP-12xx Polyglot MicroPrime Enablement](../micro-prime/REQ-MP-12xx_POLYGLOT_MICROPRIME_ENABLEMENT.md)
> **Related:**
>   - [KAIZEN_GO_REQUIREMENTS.md](KAIZEN_GO_REQUIREMENTS.md) — Go quality measurement and feedback
>   - [GO_MICROPRIME_HAYAI_AUDIT.md](GO_MICROPRIME_HAYAI_AUDIT.md) — Run-118 forensic findings
>   - [MICROPRIME_LANGUAGE_ENABLEMENT_PLAYBOOK.md](../micro-prime/MICROPRIME_LANGUAGE_ENABLEMENT_PLAYBOOK.md) — Language-agnostic checklist
>   - [HAYAI_DESIGN_PRINCIPLE.md](../../design-princples/HAYAI_DESIGN_PRINCIPLE.md) — Early enforcement principle
> **Language Profile:** `GoLanguageProfile` (`src/startd8/languages/go.py`)
> **Scope:** Go-specific MicroPrime element generation, decomposition, and repair refinement

---

## 1. Current State (Post Run-118, Post REQ-MPL-100–105)

### What's Working

| Capability | Status | Evidence |
|-----------|--------|---------|
| Enrichment-time language resolution | DONE | `coding_standards_injected: 40` in run-118 diagnostic |
| Element routing (bypass gate) | DONE | `.go` → `_is_non_python_file()` = False |
| SIMPLE tier classification | DONE | 12/40 features classified SIMPLE |
| Language-aware system prompt | DONE | `_build_system_prompt()` dispatches by `language_id` |
| Language-aware user prompt | DONE (REQ-MPL-101) | `stub_marker_text`, indent, keyword from profile |
| Full-function mode for Go | DONE (REQ-MPL-102) | Non-Python forced to `full_function` |
| Pre-extraction fence strip | DONE (REQ-MPL-103) | Fences stripped before validation |
| Repair language guard | DONE (REQ-MPL-100) | `bare_statement_wrap` no-op for Go |
| Syntax validation via `gofmt -e` | DONE | `_try_parse()` dispatches to gofmt |
| Splicer dispatch | DONE | `splice_body_into_skeleton()` → `_splice_go_dispatch()` |
| Go parser (regex) | DONE | `go_parser.py` — functions, methods, types, constants |
| Go splicer (brace-match) | DONE | `go_splicer.py` — body replacement + gofmt |
| 7 Go templates | DONE | `_LANGUAGE_TEMPLATES["go"]` registered |
| 6 semantic checks | DONE | `go_semantic_checks.py` — errors, dups, contamination, etc. |
| Post-gen cleanup (goimports) | DONE | `GoLanguageProfile.post_generation_cleanup()` |
| Repair routes (6 routes) | DONE | syntax, import, contamination, dot-import, unchecked-error, credential |
| Kaizen suggestion mappings | DONE | All 6 categories wired in `_SEMANTIC_CATEGORY_TO_SUGGESTION` |

### What's Not Working (Effectiveness Gaps)

| Gap | Severity | Description | Impact | Root Cause | Polyglot Req |
|-----|----------|-------------|--------|-----------|-------------|
| **Element stub is Python** | CRITICAL | `_build_element_stub()` renders `def quote(): raise NotImplementedError` for Go elements | LLM sees contradictory instructions (Go-aware) vs stub (Python) | Function is hardcoded Python, no language param | REQ-MP-1211a |
| **Imports are Python** | HIGH | `_render_imports()` renders `import fmt` instead of `import "fmt"` | LLM sees wrong import syntax | Function is hardcoded Python, no language dispatch | REQ-MP-1211b |
| **Signature parsing skips Go** | HIGH | `_parse_api_signature()` calls `ast.parse()` on Go signatures → `SyntaxError` → zero ForwardElementSpec | All Go elements routed to Tier 3 (escalation) despite Go signature parser existing | Python AST parser used; `go_signature_parser.py` exists but not called | REQ-MP-1211c |
| **Template granularity mismatch** | MEDIUM | 7 Go templates registered but 0/12 matched in run-118 | Templates provide zero-cost generation, but never fire | Elements are file-level modules, templates match function-level patterns | Deferred (REQ-GO-MP-300) |
| **Splicer never exercised** | MEDIUM | Go splicer dispatch wired but zero splices in run-118 | Incremental generation unavailable | Depends on function-level decomposition | Deferred (REQ-GO-MP-300) |
| **Python AST decomposer** | MEDIUM | `FunctionBodyDecomposer` uses `ast.parse()` — can't decompose Go | Multi-function Go files stay as single elements | Decomposer is Python-only | Deferred (REQ-GO-MP-300) |
| **`unchecked_error` recurrence** | MEDIUM | 28 warnings across 11 features despite coding standards injection | 27.5% of features have unchecked errors | LLM compliance gap | REQ-GO-MP-200 |
| **go.mod deterministic gen** | LOW | `_try_generate_go_mod()` exists but coverage is limited | Some go.mod files fall through to LLM | Missing indirect deps | REQ-GO-MP-400 |
| **Interface method extraction** | MEDIUM | `go_parser.py` detects interfaces but doesn't extract method signatures from body | Interface contracts incomplete in ForwardManifest | `_find_struct_body()` skips interface bodies | Go parser enhancement |
| **Skeleton enrichment Python-only** | MEDIUM | `skeleton_spec_extractor.py` only handles Python (`ast.parse`) | Go skeletons with `panic("not implemented")` not auto-enriched | No Go equivalent | Go skeleton enrichment |

### Forensic Evidence: The Prompt Mismatch (Run-118)

The forensic audit traced the exact prompt a Go element receives. The **instructions** are language-aware (REQ-MPL-101), but the **stub and imports** are Python:

```
# Task: Write the complete implementation of function `quote`.          ← Go-aware ✓
# Output the full function: the `func` declaration and the function body. ← Go-aware ✓

# Available imports (ONLY use these):
import context                    ← PYTHON (should be: import "context")  ✗
import github.com.example.pb      ← PYTHON (should be: "github.com/example/pb") ✗

# Now implement this function:
def quote(ctx: context.Context, items: []*pb.CartItem) -> error:  ← PYTHON ✗
    raise NotImplementedError                                      ← PYTHON ✗
```

**Expected Go prompt:**
```
func quote(ctx context.Context, items []*pb.CartItem) error {
    panic("not implemented")
}
```

This mismatch forces the LLM to resolve a contradiction between instructions and stub. The three new REQ-MP-1211a/b/c requirements address the root causes.

---

## 2. Phase 1: Template Coverage Expansion (REQ-GO-MP-100)

### Problem

The 7 existing Go templates match narrow patterns:

| Template | Pattern | Match Rate (Run-118) |
|----------|---------|---------------------|
| `go_constructor` | `NewXxx` | 0/12 — no constructors in utility modules |
| `go_stringer` | `String` | 0/12 |
| `go_error` | `Error` | 0/12 |
| `go_close` | `Close` | 0/12 |
| `go_getter` | `GetXxx` | 0/12 |
| `go_setter` | `SetXxx` | 0/12 |
| `go_main` | `main` | 0/12 — main.go files went file-whole (28 non-MP features) |

The templates are correctly designed for **function-level elements**. They will start matching when decomposition (Phase 3) breaks multi-function files into individual functions. However, there are additional Go-specific patterns worth templating that would increase coverage even at file-level.

### REQ-GO-MP-100: Go File-Level Templates

Add templates for common Go file archetypes that can be matched at the file-level (before decomposition):

| Template | Match Condition | Generates |
|----------|----------------|-----------|
| `go_test_file` | Element name ends in `_test`, target file is `*_test.go` | `package {pkg}_test` + `func Test{Name}(t *testing.T) { ... }` with table-driven test skeleton |
| `go_grpc_server` | Element name contains `server` AND design_doc_sections mention `gRPC` | gRPC server bootstrap: `grpc.NewServer()`, service registration, `lis.Accept()` |
| `go_http_handler` | Element name contains `handler` AND target file is `handlers.go` or `handler.go` | HTTP handler with `http.ResponseWriter` + `*http.Request` signature, error response pattern |
| `go_middleware` | Element name is `middleware` or contains `Middleware` | `func(next http.Handler) http.Handler` wrapper pattern |

**Acceptance criteria:**
- Templates produce compilable Go with `gofmt -e` validation
- Template bodies use `panic("not implemented")` stubs for business logic (filled by LLM if not decomposed)
- Each template includes correct import block for its pattern (e.g., `"net/http"` for HTTP handler)
- Templates registered in `_LANGUAGE_TEMPLATES["go"]`
- Match functions check `element.name` and available context (design_doc_sections, target_files)

### REQ-GO-MP-101: Go Template Test Coverage

Each new template requires:
- Unit test for match function (positive + negative cases)
- Unit test for render function (output compiles via `gofmt -e`)
- Integration test showing template match during a SIMPLE element processing

---

## 3. Phase 2: Error Handling Enforcement (REQ-GO-MP-200)

### Problem

28 `unchecked_error` warnings across 11/40 features in run-118. The coding standards say "ALWAYS check returned errors with `if err != nil`" but the LLM generates `_, err := someFunc()` without the subsequent check.

### REQ-GO-MP-200: P0 Error Handling Constraint

Elevate the `err != nil` pattern from coding standards (general P0 section in spec prompt) to a **Go-specific P0 constraint** (analogous to the SQL injection security constraint in `drafter.py:252`).

**Implementation:**
- In `GoLanguageProfile`, add a `get_p0_constraints()` method (or equivalent) that returns:
  ```
  CRITICAL GO CONSTRAINT: Every function call that returns an error MUST have
  the error checked on the next line with `if err != nil { return ..., err }`.
  NEVER use `_` to discard error values. NEVER proceed past an error-returning
  call without checking the error. This is the #1 Go quality defect.
  ```
- Inject this at P0 priority in the spec prompt (same mechanism as database security constraint)
- Inject in the drafter system prompt (appended after template formatting, same as security constraint at line 264)

**Acceptance criteria:**
- Run with P0 constraint produces < 10 `unchecked_error` warnings (vs 28 in run-118)
- Constraint survives budget enforcement (P0 = never dropped)
- Python/Java/C#/Node.js unaffected

### REQ-GO-MP-201: Error Handling Template Patterns

When function-level decomposition is available (Phase 3), Go templates for common patterns should embed `if err != nil` handling:

```go
// go_grpc_method template
func (s *{Service}Server) {Method}(ctx context.Context, req *pb.{Request}) (*pb.{Response}, error) {
    // TODO: implement
    panic("not implemented")
}
```

The template signature includes `error` return type, and the Kaizen hint for `unchecked_error` reinforces the pattern in subsequent runs.

---

## 4. Phase 3: Go Function-Level Decomposition (REQ-GO-MP-300)

### Problem

The single largest effectiveness gap: Go files enter MicroPrime as **file-level** elements (one element per file). The `FunctionBodyDecomposer` uses Python `ast.parse()` and cannot decompose Go. This means:
- Templates can't match individual functions (they see "tracker" not "NewTracker" + "GenerateID" + "Format")
- Splicer can't insert individual function bodies (no skeleton with stubs to fill)
- No per-function validation (entire file generated in one LLM call)

### REQ-GO-MP-300: Go Decompose Strategy

Implement `GoDecomposeStrategy` that uses `go_parser.py:parse_go_source()` to break a Go file into individual function/method elements.

**Input:** A `ForwardFileSpec` with a single file-level element + the Go skeleton source.

**Output:** A `DecompositionPlan` with one `SubElement` per function/method in the skeleton.

**Algorithm:**
1. Parse skeleton with `parse_go_source(skeleton)` → list of `GoElement` (functions, methods, types)
2. Filter to functions/methods with stub bodies (`panic("not implemented")` or `// TODO`)
3. Create `ForwardElementSpec` per stub:
   - `name`: function name
   - `kind`: `FUNCTION` or `METHOD`
   - `parent_class`: receiver type (for methods) or None
   - `signature`: from `GoElement.signature`
4. Return plan with ordered sub-elements (respecting dependency order if determinable)

**Dependencies:**
- `go_parser.py:parse_go_source()` — already extracts functions, methods, types, constants
- `go_parser.py:parse_go_imports()` — already extracts imports
- `go_splicer.py:_is_stub_body()` — already detects stub bodies

**Acceptance criteria:**
- A Go file with 5 functions produces 5 `ForwardElementSpec` objects
- Each spec has correct name, kind, receiver type, and signature
- Stub functions are identified; non-stub functions are skipped (already implemented)
- The decomposition plan is consumed by `_handle_moderate()` (or a new `_handle_simple_decomposed()`)

### REQ-GO-MP-301: Decomposer Language Dispatch

Add Go dispatch to the decomposer selection in `engine.py`:

```python
if language_id == "go":
    strategy = GoDecomposeStrategy(go_parser, go_splicer)
elif language_id == "python":
    strategy = ClassDecomposeStrategy(...)  # existing
```

**Prerequisite:** REQ-MP-1221 (language dispatch in decomposer) from the polyglot enablement doc.

### REQ-GO-MP-302: Per-Function Generation with Go Splicer

After decomposition, each sub-element goes through:
1. Template match attempt (existing 7 + new Phase 1 templates)
2. If no match: local LLM generation (Ollama with Go system prompt)
3. Validate generated body with `gofmt -e`
4. Splice into skeleton with `splice_go_bodies()`
5. Run `goimports -w` on the assembled file
6. Final `gofmt -e` validation

This is the core value loop — incremental, per-function generation with validation at each step.

**Acceptance criteria:**
- A file with 5 stubs generates 5 independent LLM calls (not 1 file-whole call)
- Each generated body is validated independently (bad body doesn't block others)
- Splicer assembles all bodies into the skeleton
- `goimports` resolves imports for the assembled file
- Cost per element is significantly lower than file-whole generation

---

## 5. Phase 4: go.mod Deterministic Generation (REQ-GO-MP-400)

### Problem

`_try_generate_go_mod()` in `prime_adapter.py` produces deterministic go.mod files, but coverage is limited. Some go.mod files fall through to LLM generation because:
- Indirect dependencies not captured from the plan
- Module path not always derivable from service metadata
- Go version not always specified in seed context

### REQ-GO-MP-400: Comprehensive go.mod Assembly

Enhance `_try_generate_go_mod()` to handle more cases:

1. **Module path resolution priority:**
   - `service_metadata.module_path` (explicit from seed)
   - `service_metadata.service_name` → `github.com/{org}/{service}` (convention)
   - Target file path → infer from directory structure

2. **Dependency resolution:**
   - Direct deps from `design_doc_sections` (extract `import "..."` blocks)
   - Direct deps from sibling `.go` files' imports (cross-task context)
   - Known framework deps from `GoLanguageProfile.framework_imports`

3. **Go version:**
   - From `service_metadata.go_version`
   - From `GoLanguageProfile.default_go_version` (e.g., `1.23`)
   - Fallback: latest stable

**Acceptance criteria:**
- go.mod files that currently fall through to LLM are generated deterministically
- Generated go.mod passes `go mod tidy` validation (when deps are available)
- Cost savings: go.mod generation is zero LLM cost

---

## 6. Observability & Kaizen Integration

### REQ-GO-MP-500: Go MicroPrime Metrics

Extend MicroPrime OTel metrics with Go-specific dimensions:

| Metric | Labels | Purpose |
|--------|--------|---------|
| `microprime.element.generation.count` | `language=go, tier=SIMPLE, result={success\|escalation}` | Track Go local generation success rate |
| `microprime.element.template.match` | `language=go, template={name}` | Track which Go templates fire (currently 0%) |
| `microprime.element.splice.count` | `language=go, result={success\|failure}` | Track Go splicer usage (currently 0) |
| `microprime.element.fence_strip.pre_extraction` | `language=go` | Track pre-extraction fence strip rate (target: 100% replaced by pre-strip) |
| `microprime.element.decomposition.count` | `language=go, strategy={GoDecomposeStrategy}` | Track decomposition when Phase 3 lands |

### REQ-GO-MP-501: Go Quality Feedback Loop

When run N produces `unchecked_error` findings, run N+1 should show improvement. Track:
- `unchecked_error` count per run (trend should decrease)
- Correlation between P0 error handling constraint (REQ-GO-MP-200) and finding count
- Template match rate per run (should increase as templates and decomposition improve)

---

## 7. Playbook Compliance Status

Current Go status against the [MicroPrime Language Enablement Playbook](../micro-prime/MICROPRIME_LANGUAGE_ENABLEMENT_PLAYBOOK.md):

| Stage | Checkpoint | Go Status |
|-------|-----------|-----------|
| 0 (Foundation) | 0.1–0.8 | All DONE |
| 1 (Enrichment) | 1.1–1.6 | All DONE |
| 2 (Spec Building) | 2.1–2.5 | All DONE |
| 3 (Element Routing) | 3.1–3.5 | All DONE |
| 4 (Templates) | 4.1–4.2 | DONE |
| 4 (Templates) | 4.3 Match functions evaluate | **Gap** — 0/12 matches (granularity) |
| 4 (Templates) | 4.5 Templates match in practice | **Gap** — need Phase 1 + Phase 3 |
| 5 (Decomposition) | 5.1–5.3 | DONE (parser + splicer exist) |
| 5 (Decomposition) | 5.4 Decomposer produces function-level | **Gap** — need Phase 3 |
| 5 (Decomposition) | 5.5 Splicer exercised in practice | **Gap** — depends on 5.4 |
| 6 (Generation) | 6.1–6.8 | All DONE (post REQ-MPL) |
| 7 (Repair) | 7.0–7.6 | All DONE |
| 7.5 (Leakage Audit) | 7.5.1–7.5.8 | All DONE (post REQ-MPL) |
| 8 (Semantic/Postmortem) | 8.1–8.7 | All DONE |

**Summary:** 42/54 checkpoints DONE. Remaining gaps span prompt rendering (CRITICAL), signature parsing (HIGH), and decomposition (MEDIUM).

---

## 8. Implementation Priority

**Revised priority based on forensic findings (2026-03-24).** The prompt rendering gaps (REQ-MP-1211a/b/c) are higher priority than template expansion or decomposition because they affect the quality of EVERY element the LLM generates, not just a subset.

| Phase | Requirements | Effort | Dependency | Expected Impact |
|-------|-------------|--------|------------|-----------------|
| **0 (CRITICAL)** | REQ-MP-1211a (language-aware stub rendering) | 4–6 hours | LanguageProfile protocol extension | LLM sees correct Go syntax in prompt — eliminates instruction/stub contradiction |
| **0 (HIGH)** | REQ-MP-1211b (language-aware import rendering) | 2 hours | None | LLM sees `import "fmt"` not `import fmt` |
| **0 (HIGH)** | REQ-MP-1211c (Go signature parser wiring) | 2 hours | REQ-TDE-200 (done) | Go elements get ForwardElementSpec from plan → Tier 0-2 routing instead of Tier 3 escalation |
| **1** | REQ-GO-MP-200 (error handling P0 constraint) | 1 hour | None | Reduce `unchecked_error` from 28 to < 10 |
| **2** | REQ-GO-MP-100 (file-level templates) | 2–3 hours | None | 2–4 template matches per run |
| **3** | REQ-GO-MP-300 (decomposer) | 6–8 hours | Go parser + splicer (exist) | Enable function-level generation; unlock templates + splicer |
| **4** | REQ-GO-MP-400 (go.mod assembly) | 2 hours | None | Eliminate LLM cost for go.mod files |
| **5** | REQ-GO-MP-500 (metrics) | 1 hour | None | Visibility into Go MicroPrime effectiveness |

**Critical path:** Phase 0 (stub + imports + signature parsing) is the highest-value work. Every Go element benefits immediately. Phases 1-5 have narrower per-item impact.

**Critical path:** Phase 3 (decomposer) is the highest-value change — it unlocks template matching, splicer integration, and per-function validation. Phases 1 and 2 can proceed in parallel.

---

## 9. Verification

### Run-Level Validation

After each phase, run Go Prime Contractor on the online-boutique seed and verify:

| Phase | Metric | Run-118 Baseline | Target |
|-------|--------|-----------------|--------|
| 1 | Template match rate | 0/12 (0%) | 2–4/12 (17–33%) |
| 2 | `unchecked_error` warnings | 28 across 11 features | < 10 across < 5 features |
| 3 | Elements per file (avg) | 1.0 (file-level) | 3–5 (function-level) |
| 3 | Splicer operations | 0 | > 0 (proportional to decomposed elements) |
| 3 | Template match rate | (from Phase 1) | 5–10/50+ (10–20% of function-level elements) |
| 4 | go.mod LLM generation | 4 (all go.mod files) | 0 (all deterministic) |
| 5 | OTel metric cardinality | 0 Go-specific | Full coverage per table above |

### Unit Tests Per Phase

| Phase | Test File | Tests |
|-------|-----------|-------|
| 1 | `tests/unit/micro_prime/test_go_file_templates.py` | Template match + render for each new template |
| 2 | `tests/unit/micro_prime/test_go_error_constraint.py` | P0 constraint present in Go spec/draft prompts |
| 3 | `tests/unit/micro_prime/test_go_decomposer.py` | Decomposition of multi-function Go files |
| 3 | `tests/unit/micro_prime/test_go_splice_integration.py` | End-to-end: decompose → generate → splice → validate |
| 4 | `tests/unit/micro_prime/test_go_mod_assembly.py` | Deterministic go.mod from various metadata states |
