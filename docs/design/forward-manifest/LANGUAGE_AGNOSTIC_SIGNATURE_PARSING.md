# Language-Agnostic Signature Parsing & Multi-Language Trivial Assembly

> **Version:** 1.0.0
> **Status:** ACTIVE (fixes landed)
> **Date:** 2026-03-08
> **Scope:** Forward manifest extractor, element registry, complexity classifier, deterministic assembler
> **Kaizen source:** Run 013 post-mortem — Online Boutique gRPC services

---

## 1. The Theme

The forward manifest extractor and downstream decomposer were designed around Python-specific syntax patterns (`def`, `class`, AST parsing). But the pipeline processes **any file type** that appears in a plan — HTML templates, Dockerfiles, YAML configs, shell scripts, requirements files, protobuf stubs. Two related gaps emerged:

1. **LLM-generated signatures use natural language, not Python syntax.** The LLM's `api_signatures` output uses prefixes like `Method`, `Function`, `Class`, `Property`, `Async Method` — descriptive labels, not Python keywords. The extractor must normalize these to Python-parseable forms.

2. **Non-Python files can benefit from the same pipeline at the TRIVIAL tier.** Creating `src/emailservice/templates/confirmation.html` doesn't need Python AST analysis. It needs a file path, a file extension, and content. The complexity classifier should route these to trivial/template-based generation rather than forcing them through Python-centric decomposition or expensive cloud fallback.

These are two facets of the same principle: **the pipeline should be language-aware at the edges (parsing, assembly) but language-agnostic in its core data model** (elements, tiers, contracts, registries).

---

## 2. Problem: LLM Signature Prefix Variance

### What the LLM produces

The PARSE phase extracts `api_signatures` as free-form strings. Across runs, the LLM uses varying prefixes:

| LLM output | Python equivalent | Frequency |
|-----------|-------------------|-----------|
| `def foo(x) -> str` | `def foo(x) -> str` | Common |
| `async def bar()` | `async def bar()` | Common |
| `Method ListRecommendations(self, req, ctx)` | `def ListRecommendations(self, req, ctx)` | Common for gRPC/servicer methods |
| `Class RecommendationService(Base)` | `class RecommendationService(Base)` | Common |
| `Function setup() -> None` | `def setup() -> None` | Occasional |
| `Property name -> str` | `@property name` | Rare |
| `Async Method fetch(self, q)` | `async def fetch(self, q)` | Occasional |
| `CLASS Handler(Base)` | `class Handler(Base)` | Rare (all-caps) |
| `ASYNC DEF fast(x)` | `async def fast(x)` | Rare (all-caps) |

### What went wrong (run 013)

`_strip_def_prefix()` only handled `def ` and `async def `. When the LLM emitted `Method ListRecommendations(self, request, context)`:

1. Prefix not stripped → `_parse_python_signature()` tried `ast.parse("def Method ListRecommendations(...): pass")` → SyntaxError
2. `parsed_sig = None` → guard at line 582 silently skipped element spec creation
3. Contract created (for validation), but element spec lost → method invisible to decomposer
4. `_methods_are_separate()` returned `False` → class rejected as `not_decomposable`
5. Entire `RecommendationService` escalated to cloud fallback ($0.18)

**Compounding factor:** `_link_methods_to_classes()` used a `len(class_names) == 1` guard. The email server file had 4 classes, so even correctly-parsed methods were never linked to their parent class.

### The fix

1. **Case-insensitive prefix stripping** — `_strip_def_prefix()` now handles `Method`, `Function`, `Property`, `async method`, `async function`, plus case variants (`ASYNC DEF`, `Async Method`, etc.)
2. **Async detection before stripping** — `_detect_async_prefix()` checks the original string before the `async` keyword is removed, preserving `ASYNC_FUNCTION`/`ASYNC_METHOD` element kinds
3. **Proximity-based class linking** — When multiple classes exist in a file, methods are linked to the nearest preceding class in list order (matching LLM output ordering: class declaration followed by its methods)
4. **Warning on silent drops** — When `parsed_sig` is `None` but `func_name` was extracted, a `logger.warning` fires instead of silently skipping

---

## 3. Theme: Multi-Language Trivial Assembly

### The opportunity

Not every file in a plan is Python. Run 013 included:

| File | Language | LOC | Actual cost | Should cost |
|------|----------|-----|-------------|-------------|
| `confirmation.html` | Jinja2/HTML | 54 | $0.59 (cloud) | ~$0.00 (template) |
| `logger.py` | Python | 42 | ~$0.00 (local) | ~$0.00 |
| `recommendation_server.py` | Python | 157 | $0.18 (cloud fallback) | ~$0.02 (local after fix) |
| `Dockerfile` | Docker | 50 | not run yet | should be trivial |
| `requirements.in` | text | 9 | not run yet | should be trivial |

The HTML template cost $0.59 — **76% of the entire run's cost** — for a file that is essentially "create this file with this template content." The complexity classifier currently has no concept of non-Python files at the TRIVIAL tier.

### Design direction

The pipeline's data model (`ForwardElementSpec`, `ForwardFileSpec`, element registry, `TierClassification`) is already language-agnostic. The language-specific parts are:

| Component | Current language scope | Extension needed |
|-----------|----------------------|------------------|
| `_parse_python_signature()` | Python only | N/A — signatures are Python-specific |
| `_strip_def_prefix()` | Python + LLM prefixes | Done (this fix) |
| `classify_element_with_details()` | Python-centric signals | Needs file-extension awareness |
| `DeterministicFileAssembler` | Python skeletons | Needs language-specific skeleton templates |
| `MicroPrimeEngine` | Python AST validation | Needs to skip AST for non-Python |
| Template registry | Python templates | Needs file-type templates (HTML, Docker, etc.) |

### Trivial operations that are language-agnostic

These operations apply to **any** file type at the lowest complexity levels:

1. **Create a file with a given name and extension** — `confirmation.html`, `Dockerfile`, `requirements.in`
2. **Copy/adapt from a reference** — "This file is identical to PI-001" (the logger duplication case)
3. **Fill a template with variables** — Jinja2-style substitution from task context
4. **Concatenate sections** — requirements files, config files, dependency lists
5. **Wrap content in boilerplate** — HTML `<head>`/`<body>`, Dockerfile `FROM`/`COPY`/`RUN` stages

None of these need Python AST parsing, Ollama generation, or cloud LLM calls.

### Recommended classifier extension

```
if file_extension not in ('.py',):
    if estimated_loc < TRIVIAL_LOC_THRESHOLD:
        return TRIVIAL, "non-Python file below LOC threshold"
    if estimated_loc < SIMPLE_LOC_THRESHOLD:
        return SIMPLE, "non-Python file — single LLM generation"
    # Non-Python files above SIMPLE threshold → cloud fallback
    return COMPLEX, "non-Python file above local generation threshold"
```

This would route `confirmation.html` (54 LOC) to TRIVIAL/SIMPLE tier instead of cloud fallback, saving $0.59 per run.

---

## 4. Traceability

| Issue | Root cause | Fix | Files changed |
|-------|-----------|-----|---------------|
| `Method ` prefix dropped 5 methods | `_strip_def_prefix()` only handled `def`/`async def` | Case-insensitive prefix list with `Method`/`Function`/`Property` | `forward_manifest_extractor.py` |
| Multi-class files had 0 linked methods | `_link_methods_to_classes()` required exactly 1 class | Proximity heuristic: link to nearest preceding class | `forward_manifest_extractor.py` |
| Async-ness lost after prefix stripping | `_parse_python_signature()` wraps as sync `def` | `_detect_async_prefix()` checks before stripping | `forward_manifest_extractor.py` |
| Parse failure silently dropped element specs | `if parsed_sig and target_files:` guard | `logger.warning` on contract-without-element mismatch | `forward_manifest_extractor.py` |
| HTML template routed to $0.59 cloud | Classifier has no non-Python awareness | Future: file-extension-aware tier routing | `complexity/classifier.py` (planned) |

### Kaizen run metrics impact (projected for run 013)

| Metric | Before fix | After fix (projected) |
|--------|-----------|----------------------|
| Elements in `email_server.py` manifest | 8 (0 linked) | 12 (7 linked) |
| Elements in `recommendation_server.py` manifest | 2 (0 linked) | 5 (3 linked) |
| `RecommendationService` decomposable | No (`not_decomposable`) | Yes (shell + 3 methods) |
| PI-006 cost | $0.18 (cloud fallback) | ~$0.02 (local Ollama) |
| Total element registry entries (plan-wide) | 26 | ~35+ |

---

## 5. Cross-References

| Document | Relationship |
|----------|-------------|
| [Phase 3 Extractor Requirements](Phase_3_Forward_Manifest_Extractor_Requirements.md) | REQ-3.1.1 (method-to-class linkage) — extended for multi-class |
| [REQ-MP-901](../micro-prime/REQ-MP-9xx_MODERATE_DECOMPOSER.md) | ClassDecomposeStrategy — `_methods_are_separate()` now succeeds |
| [KAIZEN_PLAN_INGESTION_REQUIREMENTS](../plan-ingestion/KAIZEN_PLAN_INGESTION_REQUIREMENTS.md) | Layer 3 quality metrics — element registry hit/miss now meaningful |
| [MOTTAINAI_DESIGN_PRINCIPLE](../../design-princples/MOTTAINAI_DESIGN_PRINCIPLE.md) | Don't discard: LLM-produced method signatures were being silently dropped |
| SDK Lessons Learned | Leg 13 #64 (synthetic element re-classification), Leg 13 #44 (bare import false positive) |
