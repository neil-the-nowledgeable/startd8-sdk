# Polyglot Template Registry — Requirements

> **Version:** 0.1.0
> **Status:** DRAFT
> **Date:** 2026-03-09
> **Scope:** Extend the template registry (REQ-MP-300–313) to support non-Python languages, starting with Go/gRPC and Dockerfiles
> **Motivation:** [KAIZEN_SEED_UTILIZATION_IMPLEMENTATION_PLAN.md](../kaizen/KAIZEN_SEED_UTILIZATION_IMPLEMENTATION_PLAN.md) Phase 4 — online-boutique run-020 had 0/38 elements pre-filled because the template registry is Python-only
> **Depends on:** REQ-MP-300–313 (existing template registry), forward manifest models, splicer

---

## Table of Contents

1. [Overview](#1-overview)
2. [Status Dashboard](#2-status-dashboard)
3. [Layer 1 — Language-Aware AST Validation (REQ-MP-320–324)](#3-layer-1--language-aware-ast-validation-req-mp-320324)
4. [Layer 2 — Language Detection (REQ-MP-330–332)](#4-layer-2--language-detection-req-mp-330332)
5. [Layer 3 — Go/gRPC Templates (REQ-MP-340–346)](#5-layer-3--gogrpc-templates-req-mp-340346)
6. [Layer 4 — Dockerfile Templates (REQ-MP-350–352)](#6-layer-4--dockerfile-templates-req-mp-350352)
7. [Layer 5 — Splicer Polyglot Support (REQ-MP-360–362)](#7-layer-5--splicer-polyglot-support-req-mp-360362)
8. [Existing Capabilities Leveraged](#8-existing-capabilities-leveraged)
9. [Constraints](#9-constraints)
10. [Verification Strategy](#10-verification-strategy)
11. [Cross-References](#11-cross-references)

---

## 1. Overview

### 1.1 Problem

The template registry (`micro_prime/templates.py`) provides deterministic code generation for TRIVIAL elements, bypassing LLM calls entirely. Today it is hardcoded to Python:

| Coupling Point | Python Assumption | Impact on Non-Python |
|---------------|-------------------|---------------------|
| `_validate_ast()` | Calls `ast.parse()` (Python AST) | Go/Dockerfile code always fails validation → template rejected |
| `_is_safe_identifier()` | Uses `str.isidentifier()` + `keyword.iskeyword()` | Go identifiers use different rules (exported = uppercase first letter) |
| `_is_dfa_stub()` | Checks for `raise NotImplementedError`, `pass`, `...` | Go stubs are `panic("not implemented")` or empty function bodies |
| Render contract (R4-S2) | Body-only output, splicer handles `def`/`class` wrapper | Go has `func`/`type` wrappers with different indentation rules |
| `_safe_default_repr()` | Uses `ast.literal_eval()` + `repr()` | Go literal syntax differs (`nil` vs `None`, `true` vs `True`) |
| `ElementKind` enum | Values map to Python constructs (`method`, `property`, `async_function`) | Go has no properties, async functions, or decorators; has interfaces, struct methods, receivers |
| `ForwardFileSpec.file` | No language field | Language must be inferred from file extension |

### 1.2 Design Approach

**Strategy: Language-dispatch at the validation layer, language-specific template lists**

Rather than making every existing template language-aware, the design adds:

1. A **language-aware validation dispatcher** that replaces `_validate_ast()` — routes to the right parser based on detected language
2. A **language detection function** derived from `ForwardFileSpec.file` extension
3. **Per-language template lists** (Go templates, Dockerfile templates) alongside the existing `TEMPLATES` list
4. **Per-language safety guards** (identifier validation, stub detection, literal serialization)
5. **Splicer language awareness** for correct indentation and wrapper handling

The existing Python templates and validation are untouched — this is purely additive.

### 1.3 What Languages

| Language | File Extensions | Template Types | AST Validation |
|----------|----------------|---------------|----------------|
| Python (existing) | `.py` | 9 templates + relaxed | `ast.parse()` |
| **Go** (new) | `.go` | 6 templates (see Layer 3) | `go/parser` via subprocess or regex-based structural check |
| **Dockerfile** (new) | `Dockerfile`, `*.dockerfile` | 2 templates (see Layer 4) | Directive-level structural check |
| **Proto** (future) | `.proto` | Deferred | Deferred |

---

## 2. Status Dashboard

| Req ID | Description | Status |
|--------|-------------|--------|
| **Layer 1 — Language-Aware AST Validation** | | |
| REQ-MP-320 | Validation dispatcher with language routing | PLANNED |
| REQ-MP-321 | Go structural validator | PLANNED |
| REQ-MP-322 | Dockerfile structural validator | PLANNED |
| REQ-MP-323 | Python validation unchanged (backward compat) | PLANNED |
| REQ-MP-324 | Validation error reporting with language context | PLANNED |
| **Layer 2 — Language Detection** | | |
| REQ-MP-330 | Language detection from file extension | PLANNED |
| REQ-MP-331 | Language field on ForwardFileSpec (optional) | PLANNED |
| REQ-MP-332 | Per-language safety guards | PLANNED |
| **Layer 3 — Go/gRPC Templates** | | |
| REQ-MP-340 | Go HTTP handler template | PLANNED |
| REQ-MP-341 | gRPC servicer method template | PLANNED |
| REQ-MP-342 | Go struct definition template | PLANNED |
| REQ-MP-343 | Go interface implementation template | PLANNED |
| REQ-MP-344 | Go table-driven test template | PLANNED |
| REQ-MP-345 | Go constant block template | PLANNED |
| REQ-MP-346 | GO_TEMPLATES list and registry integration | PLANNED |
| **Layer 4 — Dockerfile Templates** | | |
| REQ-MP-350 | Multi-stage build template | PLANNED |
| REQ-MP-351 | Single-stage service template | PLANNED |
| REQ-MP-352 | DOCKERFILE_TEMPLATES list and registry integration | PLANNED |
| **Layer 5 — Splicer Polyglot Support** | | |
| REQ-MP-360 | Language-aware indentation in splicer | PLANNED |
| REQ-MP-361 | Go function/method wrapper detection | PLANNED |
| REQ-MP-362 | Dockerfile directive-level splicing | PLANNED |

---

## 3. Layer 1 — Language-Aware AST Validation (REQ-MP-320–324)

**Goal:** Replace the Python-only `_validate_ast()` with a dispatcher that routes to the appropriate validator based on detected language.

### REQ-MP-320: Validation Dispatcher

Replace the current `_validate_ast(body, element)` call site (line 648) with a language-aware dispatcher:

```python
def _validate_output(
    body: str,
    element: ForwardElementSpec,
    file_spec: ForwardFileSpec,
) -> bool:
    """Validate template output for the target language."""
    lang = _detect_language(file_spec)
    validator = _VALIDATORS.get(lang, _validate_python)
    return validator(body, element)

_VALIDATORS: dict[str, Callable] = {
    "python": _validate_python,
    "go": _validate_go,
    "dockerfile": _validate_dockerfile,
}
```

**Backward compatibility:** The existing `_validate_ast()` is renamed to `_validate_python()` with no behavior change. The dispatcher defaults to `_validate_python` for unknown languages.

**Call site change:** `try_template_match_with_name()` (line 648) gains a `file_spec` parameter that it already receives — just needs to pass it through to validation.

### REQ-MP-321: Go Structural Validator

Go AST validation without requiring the Go toolchain on the host:

**Option A — Regex-based structural check (recommended for v1):**

```python
def _validate_go(body: str, element: ForwardElementSpec) -> bool:
    """Structural validation for Go template output."""
    if not body.strip():
        return False
    # Body-only: should not contain func/type declarations
    # (those are added by the splicer/skeleton)
    lines = body.strip().splitlines()
    for line in lines:
        stripped = line.strip()
        # Reject if body contains its own func/type wrapper
        if stripped.startswith("func ") or stripped.startswith("type "):
            return False
    # Check balanced braces
    if body.count("{") != body.count("}"):
        return False
    # Check no unclosed strings
    if body.count('"') % 2 != 0:
        return False
    return True
```

**Option B — Go toolchain validation (future):**

If the Go toolchain is available, use `go vet` or `go/parser` via subprocess:

```python
def _validate_go_toolchain(body: str, element: ForwardElementSpec) -> bool:
    """Full Go AST validation via go toolchain (requires go binary)."""
    wrapped = f"package _check\n\nfunc _check() {{\n{_indent_go(body)}\n}}\n"
    result = subprocess.run(
        ["go", "vet", "-"],
        input=wrapped, capture_output=True, text=True, timeout=5,
    )
    return result.returncode == 0
```

**v1 recommendation:** Use Option A (regex). It catches the most common template errors (unbalanced braces, stray declarations) without requiring Go on the build host. Option B can be added later as an optional upgrade when the Go toolchain is detected.

### REQ-MP-322: Dockerfile Structural Validator

```python
def _validate_dockerfile(body: str, element: ForwardElementSpec) -> bool:
    """Structural validation for Dockerfile template output."""
    if not body.strip():
        return False
    lines = [l for l in body.strip().splitlines() if l.strip() and not l.strip().startswith("#")]
    if not lines:
        return False
    # Each non-comment line must start with a known directive or continuation
    known_directives = {
        "FROM", "RUN", "CMD", "ENTRYPOINT", "COPY", "ADD", "WORKDIR",
        "ENV", "EXPOSE", "VOLUME", "USER", "ARG", "LABEL", "HEALTHCHECK",
        "SHELL", "STOPSIGNAL", "ONBUILD",
    }
    for line in lines:
        first_word = line.strip().split()[0].upper()
        # Allow continuation lines (start with &&, ||, or \)
        if first_word.startswith("&&") or first_word.startswith("||"):
            continue
        if first_word not in known_directives:
            return False
    return True
```

### REQ-MP-323: Python Validation Unchanged

The existing `_validate_ast()` is renamed to `_validate_python()` with identical behavior. All existing Python templates continue to use `ast.parse()`. No regression.

### REQ-MP-324: Validation Error Reporting

When validation fails, the log message (line 649–652) SHALL include the detected language:

```python
logger.warning(
    "Template output for %s failed %s validation, skipping",
    element.name, lang,
)
```

---

## 4. Layer 2 — Language Detection (REQ-MP-330–332)

### REQ-MP-330: Language Detection from File Extension

```python
_EXTENSION_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".go": "go",
    ".proto": "proto",
}

_FILENAME_TO_LANG: dict[str, str] = {
    "Dockerfile": "dockerfile",
}

def _detect_language(file_spec: ForwardFileSpec) -> str:
    """Detect language from file path. Defaults to 'python'."""
    filename = Path(file_spec.file).name
    if filename in _FILENAME_TO_LANG:
        return _FILENAME_TO_LANG[filename]
    ext = Path(file_spec.file).suffix.lower()
    return _EXTENSION_TO_LANG.get(ext, "python")
```

**Default to Python:** Preserves backward compatibility. Unknown extensions fall through to Python validation, which is the existing behavior.

**Extensibility:** New languages are added by inserting into the dicts — no conditional logic.

### REQ-MP-331: Language Field on ForwardFileSpec (Optional)

Add an optional `language` field to `ForwardFileSpec`:

```python
class ForwardFileSpec(BaseModel):
    file: str
    elements: list[ForwardElementSpec] = Field(default_factory=list)
    imports: list[ForwardImportSpec] = Field(default_factory=list)
    dependencies: Optional[ForwardDependencies] = None
    language: Optional[str] = None  # NEW — explicit override
```

When `language` is set, `_detect_language()` returns it directly without extension inference. This allows manifests to specify language explicitly for ambiguous cases (e.g., `.h` files could be C or C++).

**Backward compatible:** Optional field with `None` default. Existing manifests are unaffected.

### REQ-MP-332: Per-Language Safety Guards

Each language needs its own equivalents of the Python safety guards:

| Guard | Python (existing) | Go | Dockerfile |
|-------|-------------------|-----|-----------|
| Identifier validation | `str.isidentifier()` + `keyword.iskeyword()` | `re.match(r'^[a-zA-Z_]\w*$')` + Go keyword set | N/A (directives, not identifiers) |
| Stub detection | `raise NotImplementedError`, `pass`, `...` | `panic("not implemented")`, empty body `{}` | N/A |
| Literal serialization | `ast.literal_eval()` + `repr()` | `nil`/`true`/`false` + Go literal syntax | `"quoted strings"` |
| Export detection | N/A | Uppercase first letter = exported | N/A |

```python
def _is_safe_go_identifier(name: str) -> bool:
    """Check that name is a valid Go identifier."""
    return bool(re.match(r'^[a-zA-Z_]\w*$', name)) and name not in _GO_KEYWORDS

_GO_KEYWORDS = frozenset({
    "break", "case", "chan", "const", "continue", "default", "defer",
    "else", "fallthrough", "for", "func", "go", "goto", "if", "import",
    "interface", "map", "package", "range", "return", "select", "struct",
    "switch", "type", "var",
})

_GO_STUB_PATTERNS = frozenset({
    'panic("not implemented")',
    'panic("TODO")',
    "// TODO",
})

def _is_go_stub(code: str) -> bool:
    """Check whether code is equivalent to a Go stub placeholder."""
    stripped = code.strip()
    return stripped in _GO_STUB_PATTERNS or stripped == ""
```

---

## 5. Layer 3 — Go/gRPC Templates (REQ-MP-340–346)

### Render Contract for Go (R4-S2-Go)

Go templates follow the same body-only contract as Python, adapted for Go syntax:

- Return the **function/method body** only — no `func` line, no receiver, no signature
- Zero-indented; splicer re-indents with tabs (Go convention)
- For structs: return field declarations only (no `type X struct {` wrapper)
- For constants: return the full `const` or `var` declaration
- Multi-line bodies use `\n`

### REQ-MP-340: Go HTTP Handler Template

Matches: `ElementKind.FUNCTION`, name matches `*Handler` or `*handler`, file imports `net/http`

```go
// Body-only output for an HTTP handler:
w.Header().Set("Content-Type", "application/json")
w.WriteHeader(http.StatusOK)
json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
```

### REQ-MP-341: gRPC Servicer Method Template

Matches: `ElementKind.METHOD`, parent struct name ends with `Server` or `Servicer`, file imports `google.golang.org/grpc`

```go
// Body-only output for a gRPC servicer method:
return &pb.{response_type}{}, nil
```

### REQ-MP-342: Go Struct Definition Template

Matches: `ElementKind.CLASS` (mapped from struct), has fields in signature

```go
// Body-only output (field declarations only):
Field1 string
Field2 int
Field3 *OtherType
```

### REQ-MP-343: Go Interface Implementation Template

Matches: `ElementKind.METHOD`, element has `bases` containing an interface name, signature has receiver

```go
// Body-only: minimal implementation satisfying the interface
return nil
```

### REQ-MP-344: Go Table-Driven Test Template

Matches: `ElementKind.FUNCTION`, name starts with `Test`, file path contains `_test.go`

```go
// Body-only:
tests := []struct {
	name string
	want error
}{
	{"valid", nil},
}
for _, tt := range tests {
	t.Run(tt.name, func(t *testing.T) {
		// TODO: implement test
	})
}
```

### REQ-MP-345: Go Constant Block Template

Matches: `ElementKind.CONSTANT`, Go file

```go
// Full declaration (not body-only — constants are top-level):
const {name} = {default_value}
```

### REQ-MP-346: GO_TEMPLATES List and Registry Integration

```python
GO_TEMPLATES: list[CodeTemplate] = [
    CodeTemplate(name="go_http_handler", ...),
    CodeTemplate(name="grpc_servicer_method", ...),
    CodeTemplate(name="go_struct_definition", ...),
    CodeTemplate(name="go_interface_impl", ...),
    CodeTemplate(name="go_table_driven_test", ...),
    CodeTemplate(name="go_constant", ...),
]
```

The `TemplateRegistry` gains a language-dispatch path:

```python
class TemplateRegistry:
    def _try_match(self, element, file_spec, contracts):
        lang = _detect_language(file_spec)
        templates = _LANG_TEMPLATES.get(lang, TEMPLATES)
        # ... existing match loop with language-appropriate validation
```

```python
_LANG_TEMPLATES: dict[str, list[CodeTemplate]] = {
    "python": TEMPLATES,
    "go": GO_TEMPLATES,
    "dockerfile": DOCKERFILE_TEMPLATES,
}
```

---

## 6. Layer 4 — Dockerfile Templates (REQ-MP-350–352)

### Render Contract for Dockerfiles (R4-S2-Docker)

Dockerfile templates emit **complete Dockerfile content** (not body-only), since Dockerfiles have no function/method wrapper concept. The template IS the file.

### REQ-MP-350: Multi-Stage Build Template

Matches: file named `Dockerfile`, element has `labels` containing `multi-stage` or file references a compiled language (Go, Rust, Java)

```dockerfile
FROM golang:1.22-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /bin/service .

FROM alpine:3.19
RUN apk --no-cache add ca-certificates
COPY --from=builder /bin/service /bin/service
EXPOSE 8080
ENTRYPOINT ["/bin/service"]
```

### REQ-MP-351: Single-Stage Service Template

Matches: file named `Dockerfile`, element has `labels` containing interpreted language (Python, Node)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
CMD ["python", "-m", "app"]
```

### REQ-MP-352: DOCKERFILE_TEMPLATES List

```python
DOCKERFILE_TEMPLATES: list[CodeTemplate] = [
    CodeTemplate(name="dockerfile_multistage", ...),
    CodeTemplate(name="dockerfile_single_stage", ...),
]
```

---

## 7. Layer 5 — Splicer Polyglot Support (REQ-MP-360–362)

The splicer (`micro_prime/splicer.py`) currently locates `raise NotImplementedError` stubs and replaces them with template output, re-indenting to match. Non-Python languages need different stub patterns and indentation rules.

### REQ-MP-360: Language-Aware Indentation

| Language | Indentation | Convention |
|----------|------------|------------|
| Python | Spaces (typically 4) | Match existing file's indentation |
| Go | Tabs | `gofmt` mandates tabs |
| Dockerfile | N/A | No indentation hierarchy (directives are top-level) |

The splicer SHALL detect the target language (via file extension) and apply the correct indentation character when re-indenting template output.

### REQ-MP-361: Go Stub Detection in Splicer

The splicer locates stubs to replace. Go stubs differ from Python:

| Python Stub | Go Stub |
|-------------|---------|
| `raise NotImplementedError` | `panic("not implemented")` |
| `raise NotImplementedError()` | `panic("TODO")` |
| `pass` | `// TODO: implement` |
| `...` | Empty function body `{}` |

The splicer SHALL support a per-language stub pattern set:

```python
_STUB_PATTERNS: dict[str, frozenset[str]] = {
    "python": frozenset({"raise NotImplementedError", "raise NotImplementedError()", "pass", "..."}),
    "go": frozenset({'panic("not implemented")', 'panic("TODO")', "// TODO: implement", "// TODO"}),
}
```

### REQ-MP-362: Dockerfile Directive-Level Splicing

Dockerfiles don't have function bodies with stubs. Splicing for Dockerfiles operates at the **directive level** — the template replaces the entire file content (since the template IS the Dockerfile). The splicer SHALL detect Dockerfile targets and use full-file replacement rather than stub-level splicing.

---

## 8. Existing Capabilities Leveraged

| Capability | Source | Polyglot Use |
|-----------|--------|-------------|
| `CodeTemplate` dataclass | `templates.py:65-86` | Unchanged — match_fn/render_fn signature works for any language |
| `_safe_match()` / `_safe_render()` | `templates.py:88-113` | Unchanged — exception guardrails are language-agnostic |
| `try_template_match_with_name()` | `templates.py:622-655` | Modified: pass `file_spec` to validation dispatcher |
| `TemplateRegistry` class | `templates.py:663-764` | Modified: language-dispatch in `_try_match()` |
| `ForwardFileSpec.file` | `forward_manifest.py:292` | Used for language detection via extension |
| `ForwardElementSpec` | `forward_manifest.py:111` | Element kind, name, signature — used by all language templates |
| `ElementKind` enum | `code_manifest.py:70-79` | Shared across languages (FUNCTION, CLASS, CONSTANT, etc.) |
| `RELAXED_TEMPLATES` pattern | `templates.py:658-660` | Same opt-in pattern can apply per-language |
| `infer_code_language()` | `truncation_detection.py` | Existing language inference from file extension (different purpose, but same mapping) |
| Framework import detection | `implementation_engine/framework_imports.py` | gRPC detection patterns already defined |

---

## 9. Constraints

- **Python templates untouched** — all existing Python templates, validation, and safety guards remain exactly as-is. New code is additive.
- **No Go toolchain required** — v1 uses regex-based structural validation. Go toolchain validation is an optional upgrade (REQ-MP-321 Option B).
- **No new dependencies** — validation uses only stdlib (`re`, `subprocess` for optional Go toolchain).
- **Render contract preserved** — body-only output, zero-indented, splicer handles wrapper. Exception: Dockerfiles use full-file output (REQ-MP-362).
- **ElementKind reuse** — Go structs map to `CLASS`, Go functions map to `FUNCTION`, Go methods map to `METHOD`. No new enum values needed. Go-specific concepts (receivers, interfaces) are detected via naming conventions and signature inspection.
- **ForwardFileSpec change is additive** — optional `language` field with `None` default. Existing manifests unaffected.

---

## 10. Verification Strategy

### Unit Tests

1. **Language detection:** Verify `.go` → `"go"`, `Dockerfile` → `"dockerfile"`, `.py` → `"python"`, unknown → `"python"`
2. **Go validator:** Valid Go body passes; unbalanced braces fail; stray `func` declaration fails
3. **Dockerfile validator:** Valid directives pass; unknown directives fail; empty body fails
4. **Python regression:** All 45 existing diagnostics tests still pass; all 9 Python templates produce identical output
5. **Go template matching:** Each of 6 Go templates matches the correct element kind/name pattern and rejects non-matching elements
6. **Go template rendering:** Each template produces valid Go body that passes `_validate_go()`
7. **Dockerfile template rendering:** Each template produces valid Dockerfile that passes `_validate_dockerfile()`
8. **Stub detection:** Go stubs detected correctly; Python stubs unchanged
9. **Safety guards:** `_is_safe_go_identifier()` rejects Go keywords, accepts valid Go identifiers including exported names

### Integration Tests

10. **Pre-assembly with Go files:** Run `_mottainai_pre_assembly()` with Go file specs → template fills > 0
11. **Splicer with Go body:** Splice a Go template into a skeleton → correct tab indentation
12. **Dockerfile full-file replacement:** Splice a Dockerfile template → replaces entire file content

### End-to-End

13. **online-boutique re-run:** Plan ingestion on online-boutique with Go templates registered → `template_fills > 0` in diagnostic report

---

## 11. Cross-References

| Document | Relationship |
|----------|-------------|
| [KAIZEN_SEED_UTILIZATION_IMPLEMENTATION_PLAN.md](../kaizen/KAIZEN_SEED_UTILIZATION_IMPLEMENTATION_PLAN.md) | Phase 4 motivation — 0/38 pre-fills in run-020 |
| [KAIZEN_SEED_UTILIZATION_REQUIREMENTS.md](../kaizen/KAIZEN_SEED_UTILIZATION_REQUIREMENTS.md) | Section 1.3 consumption map — `element_tiers` + `skeleton_sources` |
| REQ-MP-300–313 | Existing template registry requirements (Python-only) |
| `micro_prime/templates.py` | Implementation target — template definitions, validation, registry |
| `micro_prime/splicer.py` | Implementation target — stub detection, indentation, splicing |
| `forward_manifest.py` | ForwardFileSpec language field addition |
| `truncation_detection.py` | Existing `infer_code_language()` — language detection reference |
| SDK Lessons: Leg 13 #27 | Line-anchored Dockerfile directive detection (`startswith` vs regex) |
| SDK Lessons: Leg 10 #43 | Circuit breaker granularity — relevant for subprocess-based Go validation timeout |
