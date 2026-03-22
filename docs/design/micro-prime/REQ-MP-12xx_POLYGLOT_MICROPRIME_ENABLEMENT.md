# Polyglot MicroPrime Enablement Requirements

> **Version:** 1.0.0
> **Status:** DRAFT
> **Date:** 2026-03-22
> **Parent:** [MICRO_PRIME_REQUIREMENTS.md](MICRO_PRIME_REQUIREMENTS.md)
> **Related:** [REQ-MP-3xx_POLYGLOT_TEMPLATE_REGISTRY.md](REQ-MP-3xx_POLYGLOT_TEMPLATE_REGISTRY.md), REQ-MLT-100–401
> **Scope:** Remove the non-Python bypass gate and enable local code generation for Go, Java, C#, and Node.js

---

## 1. Problem Statement

MicroPrime classifies all languages correctly (TRIVIAL/SIMPLE/MODERATE/COMPLEX) but immediately escalates every non-Python element to cloud LLM via `EscalationReason.NON_PYTHON_BYPASS` at `engine.py:3531–3616`. This wastes the existing infrastructure:

- **System prompts** already dispatch by language (`engine.py:767` — `system_prompt_role`, `coding_standards`, language-aware stub markers for Go/Java)
- **Splicers** exist for Go (`go_splicer.py`), Java (`java_splicer.py`), C# (`csharp_splicer.py`)
- **Parsers** exist for all 5 languages (AST or regex-based structure extraction)
- **Language profiles** provide `validate_syntax()`, `stub_patterns`, `post_generation_cleanup()`
- **Prompt builder** (`prompt_builder.py`) is language-agnostic at the structural level

The bypass was a safety choice (REQ-MLT-100/101) to prevent Python stubs in non-Python files. That risk is now mitigatable via existing language-aware validation.

### Cost Impact

Run-101 (40 Go tasks): every task uses `claude-sonnet-4-6` at ~$0.12/task = $4.80 total. If TRIVIAL/SIMPLE elements (estimated 60% of elements) used local Ollama, cost would drop to ~$2.00 — a 58% reduction matching the Python savings pattern.

---

## 2. Design Constraints

| ID | Constraint | Rationale |
|----|-----------|-----------|
| DC-1 | Non-Python bypass removal MUST be gated per-language and per-tier | Allows incremental rollout; one broken language doesn't block others |
| DC-2 | Post-generation validation MUST use `LanguageProfile.validate_syntax()` | Catches malformed output before splicing; existing infrastructure |
| DC-3 | Escalation on validation failure MUST preserve existing fallback behavior | If local generation fails, escalate to cloud — no worse than current bypass |
| DC-4 | Node.js MUST NOT be enabled until a splicer exists | Only language without a splicer; template-only (TRIVIAL) can proceed |
| DC-5 | Prompt builder MUST NOT hardcode Python syntax | All language-specific content comes from `LanguageProfile` properties |
| DC-6 | Zero regression for Python MicroPrime | Python path untouched; new code paths are additive |

---

## 3. Phase 1 — TRIVIAL Tier Enablement (REQ-MP-1200)

TRIVIAL elements are boilerplate: config constants, empty stubs, DTOs, type aliases. They use the **template registry**, not LLM calls.

### REQ-MP-1200: Conditional Bypass Removal for TRIVIAL

**Replace** the blanket bypass in `_handle_trivial()` (engine.py:3531–3547) with a language-capability check:

```
IF language has templates registered (via polyglot template registry):
    try template match → splice → validate
    IF validation fails: escalate (same as current bypass)
ELSE:
    escalate (preserve current behavior for unsupported languages)
```

**Acceptance criteria:**
1. Go/Java/C# TRIVIAL elements attempt template match before escalating
2. Node.js TRIVIAL elements attempt template match (no splicer needed for templates)
3. If no template matches, escalation fires with `EscalationReason.NO_TEMPLATE_MATCH` (not `NON_PYTHON_BYPASS`)
4. If template matches but `validate_syntax()` fails, escalation fires with `EscalationReason.SYNTAX_VALIDATION_FAILED`
5. Python TRIVIAL path unchanged

**Implementation:**
- `engine.py:_handle_trivial()` — Replace `_is_non_python_file()` check with `_has_language_templates(file_path)` check
- `micro_prime/templates.py` — Register Go/Java/C#/Node.js templates per REQ-MP-3xx_POLYGLOT_TEMPLATE_REGISTRY

### REQ-MP-1201: Go Trivial Templates

Register templates for:
- `go.mod` — module declaration with Go version
- Empty `main.go` — `package main` + `func main() {}`
- Test file skeleton — `package x_test` + `func TestX(t *testing.T) {}`
- Constant block — `const ( ... )`

### REQ-MP-1202: Java Trivial Templates

Register templates for:
- Interface file — `public interface IFoo { ... }`
- DTO/record — `public record Foo(String x, int y) {}`
- Constants class — `public final class Constants { ... }`
- `pom.xml` / `build.gradle` dependency file

### REQ-MP-1203: C# Trivial Templates

Register templates for:
- Interface file — `public interface IFoo { ... }`
- Record — `public record Foo(string X, int Y);`
- `.csproj` skeleton (via existing `generate_dependency_file()`)
- `.sln` skeleton (via existing `generate_solution_file()`)

### REQ-MP-1204: Node.js Trivial Templates

Register templates for:
- `package.json` skeleton
- Empty module — `module.exports = {}` (CJS) or `export {}` (ESM)
- Test file skeleton — `describe('X', () => { it('should...', () => {}); });`

---

## 4. Phase 2 — SIMPLE Tier Skeleton Fill (REQ-MP-1210)

SIMPLE elements have a skeleton with stub bodies. The LLM fills one body at a time, and the splicer inserts it. This is the core MicroPrime value proposition for cheap-model generation.

### REQ-MP-1210: Conditional Bypass Removal for SIMPLE

**Replace** the blanket bypass in `_handle_simple()` (engine.py:3600–3616) with:

```
IF language has splicer (Go, Java, C#):
    build prompt → call local LLM → validate → splice
    IF validation fails: escalate
ELIF language has no splicer (Node.js):
    escalate (preserve bypass)
ELSE:
    escalate
```

**Acceptance criteria:**
1. Go SIMPLE elements use local Ollama with `GoLanguageProfile.system_prompt_role` system prompt
2. Java SIMPLE elements use local Ollama with Java system prompt
3. C# SIMPLE elements use local Ollama with C# system prompt
4. Node.js SIMPLE elements remain bypassed (no splicer)
5. Post-generation: `validate_syntax()` runs on spliced output
6. On syntax failure: escalate to cloud (no worse than current state)
7. Python SIMPLE path unchanged

### REQ-MP-1211: Language-Aware Prompt Builder

Extend `prompt_builder.py:_build_element_prompt_core()` to use `LanguageProfile` properties:

1. System prompt uses `profile.system_prompt_role` (already wired at engine.py:767)
2. Stub marker uses language-specific pattern from `profile.stub_patterns[0]`
3. Import context uses `profile.import_pattern_template` for import formatting
4. Indentation instruction uses Go tabs vs 4-space convention (already wired at engine.py:774)

**Acceptance criteria:**
- Go prompts reference `panic("not implemented")` not `raise NotImplementedError`
- Java prompts reference `throw new UnsupportedOperationException` not `raise NotImplementedError`
- C# prompts reference `throw new NotImplementedException()` not `raise NotImplementedError`
- Prompt contains skeleton context with the actual stub body to be replaced

### REQ-MP-1212: Post-Splice Validation Gate

After splicer inserts generated body into skeleton:

1. Run `LanguageProfile.validate_syntax(spliced_code)` — catches syntax errors
2. Run language-specific post-generation cleanup if available:
   - Go: `goimports -w` (resolves imports, formats)
   - Java: (none — javalang parse check only)
   - C#: tree-sitter parse check
3. If validation fails, escalate with `EscalationReason.SYNTAX_VALIDATION_FAILED`
4. Log validation result to OTel span attributes

### REQ-MP-1213: Node.js Splicer

**Prerequisite for Node.js SIMPLE tier enablement.**

Implement `nodejs_splicer.py` following the text-based brace-matching pattern used by `go_splicer.py` and `java_splicer.py`:

1. Detect function/method stubs by matching `stub_patterns` from `NodeLanguageProfile`
2. Replace stub body with generated body
3. Preserve surrounding code unchanged
4. Handle both CJS (`function foo() {}`) and ESM (`export function foo() {}`) syntax
5. Handle arrow functions (`const foo = () => {}`)

---

## 5. Phase 3 — MODERATE Decomposition (REQ-MP-1220)

MODERATE elements are too complex for a single local LLM call. The decomposer breaks them into SIMPLE sub-elements. Currently only Python has decomposition strategies.

### REQ-MP-1220: Language-Pluggable Decomposer

Extend the `DecompositionStrategy` protocol to support non-Python languages:

1. `GoDecomposeStrategy` — Uses `go_parser.py` regex extraction to identify struct methods, interface implementations, and standalone functions. Decomposes into SIMPLE sub-elements per method/function.
2. `JavaDecomposeStrategy` — Uses `java_parser.py` to identify class methods. Decomposes into SIMPLE sub-elements per method.
3. `CSharpDecomposeStrategy` — Uses `csharp_parser.py` tree-sitter extraction. Decomposes into SIMPLE sub-elements per method/property.

### REQ-MP-1221: Decomposer Language Dispatch

Add language dispatch to `decomposer.py:decompose()`:

```
IF language == "python": use ClassDecomposeStrategy / FunctionChainStrategy
ELIF language == "go": use GoDecomposeStrategy
ELIF language == "java": use JavaDecomposeStrategy
ELIF language == "csharp": use CSharpDecomposeStrategy
ELSE: return NOT_DECOMPOSABLE (escalate to cloud)
```

---

## 6. Rollout Strategy

| Phase | Languages | Tier | Dependency | Risk | Expected Savings |
|-------|-----------|------|------------|------|-----------------|
| **1** | Go, Java, C#, Node.js | TRIVIAL | Polyglot templates (REQ-MP-3xx) | Low — templates are deterministic, no LLM | 10-15% of elements (config files, empty stubs) |
| **2** | Go, Java, C# | SIMPLE | Splicers (exist), prompt builder update | Medium — LLM output quality varies by language | 40-50% of elements (method bodies, handlers) |
| **2b** | Node.js | SIMPLE | Node.js splicer (REQ-MP-1213) | Medium — arrow function parsing is complex | 40-50% of Node.js elements |
| **3** | Go, Java, C# | MODERATE | Language decomposers (REQ-MP-1220) | Higher — decomposition quality affects sub-element boundaries | 10-20% of elements (complex classes) |

### Gating Criteria Per Phase

**Phase 1 → 2:** All Phase 1 template tests pass. Postmortem shows 0 Python-stub contamination in non-Python files.

**Phase 2 → 3:** Phase 2 local generation achieves ≥ 80% syntax validation pass rate on first attempt across all enabled languages.

---

## 7. Configuration

### REQ-MP-1230: Per-Language MicroPrime Config

Extend `prime-contractor.json` micro_prime section:

```json
{
  "micro_prime": {
    "enabled": true,
    "enabled_languages": ["python", "go", "java", "csharp"],
    "max_tier_by_language": {
      "python": "MODERATE",
      "go": "SIMPLE",
      "java": "SIMPLE",
      "csharp": "SIMPLE",
      "nodejs": "TRIVIAL"
    }
  }
}
```

`max_tier_by_language` controls the highest tier that uses local generation per language. Tasks above this tier escalate to cloud. This replaces the binary bypass with a per-language dial.

---

## 8. Observability

### REQ-MP-1240: Language-Aware Metrics

Extend existing MicroPrime OTel metrics with language dimension:

- `microprime.element.generation.count{language=go,tier=SIMPLE,result=success}` — tracks local generation by language
- `microprime.element.escalation.count{language=go,reason=SYNTAX_VALIDATION_FAILED}` — tracks validation-driven escalation by language
- `microprime.element.cost_usd{language=go,tier=SIMPLE}` — tracks cost savings by language

### REQ-MP-1241: Escalation Reason Refinement

Replace `EscalationReason.NON_PYTHON_BYPASS` with specific reasons:
- `LANGUAGE_TIER_EXCEEDED` — task tier exceeds `max_tier_by_language` config
- `NO_SPLICER_AVAILABLE` — language lacks splicer (Node.js before REQ-MP-1213)
- `NO_TEMPLATE_MATCH` — TRIVIAL tier but no template registered
- `SYNTAX_VALIDATION_FAILED` — local generation failed validation

---

## 9. Traceability Matrix

| Requirement | Phase | Languages | Depends On | Implementation |
|-------------|-------|-----------|------------|----------------|
| REQ-MP-1200 | 1 | All | REQ-MP-3xx polyglot templates | engine.py:_handle_trivial() |
| REQ-MP-1201–1204 | 1 | Go/Java/C#/Node.js | REQ-MP-1200 | micro_prime/templates.py |
| REQ-MP-1210 | 2 | Go/Java/C# | Splicers (exist) | engine.py:_handle_simple() |
| REQ-MP-1211 | 2 | All | REQ-MP-1210 | prompt_builder.py |
| REQ-MP-1212 | 2 | Go/Java/C# | LanguageProfile.validate_syntax() | engine.py post-splice gate |
| REQ-MP-1213 | 2b | Node.js | — | languages/nodejs_splicer.py |
| REQ-MP-1220 | 3 | Go/Java/C# | Language parsers (exist) | micro_prime/decomposer.py |
| REQ-MP-1221 | 3 | All | REQ-MP-1220 | decomposer.py dispatch |
| REQ-MP-1230 | 1 | All | — | config_loader.py |
| REQ-MP-1240–1241 | 1 | All | — | engine.py OTel spans |

---

## 10. Verification Strategy

### Unit Tests

| Test | Phase | Target |
|------|-------|--------|
| Go TRIVIAL template match → no escalation | 1 | REQ-MP-1200, 1201 |
| Java TRIVIAL template match → no escalation | 1 | REQ-MP-1200, 1202 |
| C# TRIVIAL template match → no escalation | 1 | REQ-MP-1200, 1203 |
| Node.js TRIVIAL template match → no escalation | 1 | REQ-MP-1200, 1204 |
| Unsupported language TRIVIAL → escalation preserved | 1 | REQ-MP-1200 (DC-3) |
| Go SIMPLE skeleton fill + splice + validate | 2 | REQ-MP-1210, 1212 |
| Java SIMPLE skeleton fill + splice + validate | 2 | REQ-MP-1210, 1212 |
| C# SIMPLE skeleton fill + splice + validate | 2 | REQ-MP-1210, 1212 |
| Go SIMPLE syntax failure → escalation | 2 | REQ-MP-1212 (DC-3) |
| Node.js SIMPLE → escalation (no splicer) | 2 | REQ-MP-1210 (DC-4) |
| Python TRIVIAL/SIMPLE → unchanged behavior | 1,2 | DC-6 |
| `max_tier_by_language` config respected | 1 | REQ-MP-1230 |

### Integration Tests

| Test | Phase | Target |
|------|-------|--------|
| Go microservice generation with MicroPrime SIMPLE enabled | 2 | REQ-MP-1210 end-to-end |
| Mixed-language project (Go + Dockerfile) with tier routing | 2 | REQ-MP-1230 |
| Postmortem shows language-specific escalation reasons (not NON_PYTHON_BYPASS) | 1 | REQ-MP-1241 |

### Smoke Test

Run a Go microservice generation (online-boutique shippingservice, ~10 tasks) with Phase 2 enabled. Compare:
- Cost vs previous run with full bypass
- Syntax validation pass rate on first local attempt
- Escalation rate to cloud
- DQS scores (should be unchanged or improved)
