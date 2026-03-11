# Dockerfile Skeleton Assembly — Implementation Plan

> **Requirements:** [REQ-MP-3xx_DOCKERFILE_SKELETON_ASSEMBLY.md](REQ-MP-3xx_DOCKERFILE_SKELETON_ASSEMBLY.md)
> **Date:** 2026-03-11
> **Status:** DRAFT — awaiting review

---

## Implementation Order

The plan is organized into 7 phases, ordered by dependency and testability. Each phase is independently testable and committable. The escalation conflation fix (Phase 1) is independent of all other phases and can ship immediately.

```
Phase 1: Escalation conflation fix          ← unblocks PI-013 via fallback
Phase 2: Language detection module           ← foundation for all polyglot work
Phase 3: ForwardFileSpec.language field      ← model extension
Phase 4: Dockerfile structural validator     ← needed by assembler + adapter
Phase 5: Dockerfile templates               ← template rendering for create mode
Phase 6: Assembler + splicer extensions      ← rendering + full-file splicing
Phase 7: Prime adapter integration           ← wires everything together
```

---

## Phase 1: Escalation Conflation Fix

**FR:** FR-DFA-001
**Files:** `src/startd8/micro_prime/prime_adapter.py`, `tests/unit/test_escalation_conflation.py`
**Effort:** ~30 lines impl, ~60 lines tests
**Risk:** Low — isolated change to escalation gate logic

### 1.1 Add `bypass_files` to `_FileProcessingState`

In `prime_adapter.py`, add a new field to the dataclass:

```python
@dataclasses.dataclass
class _FileProcessingState:
    ...
    escalated_files: list = dataclasses.field(default_factory=list)
    bypass_files: list = dataclasses.field(default_factory=list)  # NEW — FR-DFA-001
    ...
```

### 1.2 Update `_process_target_files()` classification

Currently (line 465):

```python
if file_spec is None or not skeleton:
    st.escalated_files.append(file_path)
    continue
```

Change to:

```python
if file_spec is None or not skeleton:
    # File-level bypass: MP can't process this file type at all
    # (no manifest entry or no skeleton). Distinct from element-level
    # escalation where MP tried but elements were too complex.
    st.bypass_files.append(file_path)
    continue
```

### 1.3 Update escalation gate logic

Currently (lines 418–432), there's a single gate for `st.escalated_files`. Split into two gates:

```python
# 1. Bypass files → always delegate to fallback (regardless of escalation_enabled)
if st.bypass_files and self._fallback is not None:
    logger.info(
        "Delegating %d file(s) to fallback (unsupported locally): %s",
        len(st.bypass_files),
        ", ".join(st.bypass_files),
    )
    # Delegate bypass_files via fallback — reuse _generate_with_fallback
    # but only for bypass_files, not escalated_files
    ...

# 2. Element-escalated files → respect escalation_enabled (existing behavior)
if st.escalated_files and not self._config.escalation_enabled:
    logger.warning(
        "Cloud escalation disabled (escalation_enabled=False) — "
        "keeping %d file(s) as partial local output: %s",
        len(st.escalated_files),
        ", ".join(st.escalated_files),
    )
elif st.escalated_files and self._fallback is not None and self._config.escalation_enabled:
    return self._generate_with_fallback(...)
```

**Implementation detail**: The existing `_generate_with_fallback()` method operates on all escalated files. For the bypass case, we need to either:

- (a) Call `_generate_with_fallback()` with only the bypass files (preferred — reuses existing code)
- (b) Build a minimal fallback path just for bypass files

Option (a) is cleaner. The method signature already accepts `target_files` — pass only `st.bypass_files`.

### 1.4 Update `_generate_with_fallback()` if needed

Check if `_generate_with_fallback()` uses `st.escalated_files` internally. If so, it needs to accept the file list as a parameter rather than reading from state.

### 1.5 Update metadata/logging

Ensure `generation_metadata` in `GenerationResult` tracks `bypass_file_count` separately from `escalated_file_count`.

### 1.6 Tests (`tests/unit/test_escalation_conflation.py`)

| Test | Description |
|------|-------------|
| `test_bypass_files_always_delegate` | File with no file_spec → bypass_files, delegates to fallback even when `escalation_enabled=false` |
| `test_escalated_files_respect_flag` | File with file_spec but COMPLEX elements → escalated_files, blocked when `escalation_enabled=false` |
| `test_mixed_bypass_and_escalated` | Both bypass and escalated files → bypass delegates, escalated respects flag |
| `test_bypass_no_fallback_available` | Bypass files but no fallback generator → warning logged, success based on local files only |
| `test_python_files_unchanged` | Python files with file_spec continue through element-level engine (no behavioral change) |

---

## Phase 2: Language Detection Module

**FR:** FR-DFA-002
**Files:** `src/startd8/micro_prime/lang_detect.py` (new), `tests/unit/micro_prime/test_lang_detect.py` (new)
**Effort:** ~40 lines impl, ~50 lines tests
**Risk:** None — new module, no existing code modified
**Depends on:** Nothing

### 2.1 Create `lang_detect.py`

```python
"""Language detection from file paths (REQ-MP-330).

Shared by assembler, validator, splicer, and prime_adapter for
consistent language routing across the MicroPrime pipeline.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional


_EXTENSION_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".go": "go",
    ".proto": "proto",
}

_FILENAME_TO_LANG: dict[str, str] = {
    "Dockerfile": "dockerfile",
}

_DOCKERFILE_PATTERN = re.compile(r"^Dockerfile(\..+)?$", re.IGNORECASE)


def detect_language(file_path: str, explicit_lang: Optional[str] = None) -> str:
    """Detect language from file path or explicit override.

    Args:
        file_path: Relative or absolute file path.
        explicit_lang: Explicit language override (e.g., from ForwardFileSpec.language).
            When provided, returned directly without inference.

    Returns:
        Language identifier string: "python", "dockerfile", "go", "proto", or "unknown".
    """
    if explicit_lang is not None:
        return explicit_lang

    filename = Path(file_path).name

    # Exact filename match (Dockerfile)
    if filename in _FILENAME_TO_LANG:
        return _FILENAME_TO_LANG[filename]

    # Dockerfile variants (Dockerfile.dev, Dockerfile.prod)
    if _DOCKERFILE_PATTERN.match(filename):
        return "dockerfile"

    # Extension-based detection
    ext = Path(file_path).suffix.lower()
    return _EXTENSION_TO_LANG.get(ext, "unknown")


def is_dockerfile(file_path: str, explicit_lang: Optional[str] = None) -> bool:
    """Convenience: check if file is a Dockerfile."""
    return detect_language(file_path, explicit_lang) == "dockerfile"
```

### 2.2 Tests (`tests/unit/micro_prime/test_lang_detect.py`)

| Test | Description |
|------|-------------|
| `test_python_extension` | `.py` → `"python"`, `.pyi` → `"python"` |
| `test_go_extension` | `.go` → `"go"` |
| `test_dockerfile_exact` | `Dockerfile` → `"dockerfile"` |
| `test_dockerfile_variant` | `Dockerfile.dev` → `"dockerfile"`, `Dockerfile.prod` → `"dockerfile"` |
| `test_dockerfile_case_insensitive` | `dockerfile` → `"dockerfile"`, `DOCKERFILE` → `"dockerfile"` |
| `test_proto_extension` | `.proto` → `"proto"` |
| `test_unknown_extension` | `.rs` → `"unknown"`, `.yaml` → `"unknown"` |
| `test_explicit_override` | `explicit_lang="go"` on a `.py` file → `"go"` |
| `test_is_dockerfile_helper` | `is_dockerfile("src/app/Dockerfile")` → `True` |

---

## Phase 3: ForwardFileSpec Language Field + Extractor Update

**FR:** FR-DFA-009, FR-DFA-003
**Files:** `src/startd8/forward_manifest.py`, `src/startd8/forward_manifest_extractor.py`, tests
**Effort:** ~20 lines impl, ~30 lines tests
**Risk:** Low — additive optional field, backward compatible
**Depends on:** Phase 2

### 3.1 Add `language` field to `ForwardFileSpec`

In `forward_manifest.py`:

```python
class ForwardFileSpec(BaseModel):
    file: str
    elements: list[ForwardElementSpec] = Field(default_factory=list)
    imports: list[ForwardImportSpec] = Field(default_factory=list)
    dependencies: Optional[ForwardDependencies] = None
    language: Optional[str] = None  # NEW — FR-DFA-009
```

### 3.2 Update `ForwardManifestExtractor` for Dockerfiles

In `forward_manifest_extractor.py`, the file processing loop currently skips non-Python files via the `_PYTHON_EXTENSIONS` guard. Add a pre-check:

```python
from startd8.micro_prime.lang_detect import detect_language

# Before the Python AST extraction path:
lang = detect_language(file_path)
if lang == "dockerfile":
    # Produce a minimal ForwardFileSpec — no AST parsing
    file_specs[rel_path] = ForwardFileSpec(
        file=rel_path,
        language="dockerfile",
    )
    continue

# Existing Python path continues here...
if ext not in _PYTHON_EXTENSIONS:
    continue
```

### 3.3 Tests

| Test | Description |
|------|-------------|
| `test_dockerfile_produces_file_spec` | Extractor with Dockerfile target → ForwardFileSpec with `language="dockerfile"`, empty elements/imports |
| `test_python_unchanged` | Python files still produce full ForwardFileSpec with elements (regression) |
| `test_language_field_serialization` | ForwardFileSpec with `language="dockerfile"` round-trips through JSON |
| `test_language_field_none_default` | ForwardFileSpec without explicit language → `language is None` |

---

## Phase 4: Dockerfile Structural Validator

**FR:** FR-DFA-004
**Files:** `src/startd8/micro_prime/validators/__init__.py` (new), `src/startd8/micro_prime/validators/dockerfile.py` (new), `tests/unit/micro_prime/test_dockerfile_validator.py` (new)
**Effort:** ~150 lines impl, ~150 lines tests
**Risk:** None — new module, no existing code modified
**Depends on:** Nothing (but Phase 6 and 7 consume it)

### 4.1 Create validators package

```
src/startd8/micro_prime/validators/
├── __init__.py          # Re-exports validate_dockerfile, DockerfileValidationResult
└── dockerfile.py        # Implementation
```

### 4.2 `dockerfile.py` structure

```python
"""Dockerfile structural validator (REQ-MP-322).

Validates Dockerfile content against known directive set and
best-practice rules from docker-file-assembly-via-python.md.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from startd8.logging_config import get_logger

logger = get_logger(__name__)


KNOWN_DIRECTIVES = frozenset({
    "FROM", "RUN", "CMD", "ENTRYPOINT", "COPY", "ADD", "WORKDIR",
    "ENV", "EXPOSE", "VOLUME", "USER", "ARG", "LABEL", "HEALTHCHECK",
    "SHELL", "STOPSIGNAL", "ONBUILD",
})

_PARSER_DIRECTIVE_PATTERN = re.compile(r"^#\s*(syntax|escape)\s*=")


@dataclass(frozen=True)
class DockerfileValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    advisories: list[str] = field(default_factory=list)
    directives_found: list[str] = field(default_factory=list)
    stage_count: int = 0


def validate_dockerfile(content: str) -> DockerfileValidationResult:
    """Validate Dockerfile content.

    Returns a result with:
    - valid: True if no errors (warnings and advisories don't affect validity)
    - errors: Structural problems (DV-001 through DV-005)
    - warnings: Structural issues at warning severity
    - advisories: Best-practice recommendations (DV-BP-001 through DV-BP-010)
    """
    errors: list[str] = []
    warnings: list[str] = []
    advisories: list[str] = []
    directives_found: list[str] = []
    stage_count = 0

    # Structural rules
    _check_structural_rules(content, errors, warnings, directives_found)
    stage_count = directives_found.count("FROM")

    # Best-practice advisory rules
    _check_best_practices(content, directives_found, advisories)

    valid = len(errors) == 0

    return DockerfileValidationResult(
        valid=valid,
        errors=errors,
        warnings=warnings,
        advisories=advisories,
        directives_found=directives_found,
        stage_count=stage_count,
    )
```

### 4.3 Structural rules implementation

```python
def _check_structural_rules(
    content: str,
    errors: list[str],
    warnings: list[str],
    directives_found: list[str],
) -> None:
    """DV-001 through DV-005."""
    lines = content.splitlines()

    # DV-003: No empty Dockerfile
    non_blank = [l for l in lines if l.strip()]
    non_comment = [l for l in non_blank if not l.strip().startswith("#")]
    if not non_comment:
        errors.append("DV-003: Dockerfile is empty (no directive lines)")
        return

    # DV-005: Parser directives must appear before any directive or blank line
    _check_parser_directives(lines, warnings)

    # Parse directives, tracking continuation lines
    in_continuation = False
    found_from = False
    found_first_directive = False

    for line in lines:
        stripped = line.strip()

        # Skip blank lines and comments
        if not stripped:
            in_continuation = False
            continue
        if stripped.startswith("#"):
            # But parser directives are special
            continue

        # Continuation from previous line
        if in_continuation:
            in_continuation = stripped.endswith("\\")
            continue

        # R1-S5: Degenerate continuation — line is only a backslash
        if stripped == "\\":
            in_continuation = True
            continue

        # This is a directive line
        first_word = stripped.split()[0].upper()

        # Strip flags like --platform from FROM
        directive = first_word.lstrip("-")
        # Handle FROM --platform=$X → first word is "FROM"
        if "=" in directive or directive.startswith("-"):
            # This is a flag continuation, not a directive
            continue

        if first_word in KNOWN_DIRECTIVES:
            directives_found.append(first_word)
            if first_word == "FROM":
                found_from = True
            found_first_directive = True
        else:
            # DV-002: Unknown directive
            warnings.append(f"DV-002: Unknown directive '{first_word}'")

        in_continuation = stripped.endswith("\\")

    # R1-S5: Degenerate continuation — line is only a backslash
    # (handled above: stripped == "\\" → in_continuation check)

    # DV-001: Must have at least one FROM
    if not found_from:
        errors.append("DV-001: No FROM directive found")
```

### 4.4 Best-practice advisory rules

```python
def _check_best_practices(
    content: str,
    directives_found: list[str],
    advisories: list[str],
) -> None:
    """DV-BP-001 through DV-BP-010."""
    lines = content.splitlines()

    # DV-BP-001: Pinned base image version
    for line in lines:
        stripped = line.strip()
        if stripped.upper().startswith("FROM "):
            parts = stripped.split()
            # R1-S10: Skip flags (--platform=..., --network=...)
            image_parts = [p for p in parts[1:] if not p.startswith("--")]
            image_ref = image_parts[0] if image_parts else ""
            if image_ref and (":" not in image_ref or image_ref.endswith(":latest")):
                if image_ref.lower() not in ("scratch",):
                    advisories.append(
                        f"DV-BP-001: FROM '{image_ref}' should use a pinned version tag"
                    )

    # DV-BP-002: Non-root USER
    if "USER" not in directives_found:
        advisories.append("DV-BP-002: No USER directive — container runs as root")

    # DV-BP-003: COPY over ADD
    if "ADD" in directives_found:
        advisories.append("DV-BP-003: Prefer COPY over ADD unless archive extraction is needed")

    # DV-BP-004: Exec form CMD/ENTRYPOINT
    for line in lines:
        stripped = line.strip()
        for directive in ("CMD ", "ENTRYPOINT "):
            if stripped.upper().startswith(directive):
                rest = stripped[len(directive):].strip()
                if rest and not rest.startswith("["):
                    advisories.append(
                        f"DV-BP-004: {directive.strip()} uses shell form — "
                        "prefer exec form [\"binary\", \"arg\"] for proper signal handling"
                    )

    # DV-BP-005: Deps before source (look for COPY . . after COPY requirements)
    _check_layer_ordering(lines, advisories)

    # DV-BP-006: Combined apt-get
    _check_apt_get_combined(lines, advisories)

    # DV-BP-007: Multi-stage for production
    if directives_found.count("FROM") < 2:
        advisories.append("DV-BP-007: Single-stage build — consider multi-stage for production")

    # DV-BP-008: HEALTHCHECK
    if "HEALTHCHECK" not in directives_found:
        advisories.append("DV-BP-008: No HEALTHCHECK directive")

    # DV-BP-009: LABEL metadata
    if "LABEL" not in directives_found:
        advisories.append("DV-BP-009: No LABEL metadata")

    # DV-BP-010: Alpine warning for Python
    for line in lines:
        stripped = line.strip()
        if stripped.upper().startswith("FROM ") and "python" in stripped.lower() and "alpine" in stripped.lower():
            advisories.append(
                "DV-BP-010: Python + Alpine may break C-extension wheels — prefer -slim"
            )

    # DV-BP-011: No plaintext secrets in ENV (R1-S8)
    _SECRET_PATTERN = re.compile(
        r"(?i)(password|secret|token|api_key|private_key|auth)\s*=\s*\S+"
    )
    for line in lines:
        stripped = line.strip()
        if stripped.upper().startswith("ENV ") and _SECRET_PATTERN.search(stripped):
            advisories.append(
                "DV-BP-011: ENV may contain a plaintext secret — "
                "use runtime env vars or Docker secrets instead"
            )
```

### 4.5 Tests (`tests/unit/micro_prime/test_dockerfile_validator.py`)

**Valid Dockerfiles:**

| Test | Input |
|------|-------|
| `test_valid_single_stage` | `FROM python:3.12-slim\nWORKDIR /app\nCMD ["python", "app.py"]` |
| `test_valid_multi_stage` | PI-013 loadgenerator Dockerfile (from Appendix A) |
| `test_valid_with_comments` | Dockerfile with `#` comment lines interspersed |
| `test_valid_with_parser_directive` | `# syntax=docker/dockerfile:1\nFROM ...` |
| `test_valid_arg_before_from` | `ARG VERSION=3.12\nFROM python:${VERSION}-slim` |
| `test_valid_continuation_lines` | `RUN apt-get update && \\\n    apt-get install -y gcc` |
| `test_continuation_backslash_only_line` | R1-S5: Line with only `\` between continuation lines → no DV-002 warning |

**Invalid Dockerfiles:**

| Test | Input | Expected Error |
|------|-------|---------------|
| `test_no_from` | `RUN echo hello` | DV-001 |
| `test_empty` | `""` | DV-003 |
| `test_only_comments` | `# just a comment` | DV-003 |
| `test_blank_only` | `\n\n\n` | DV-003 |

**Best-practice advisories:**

| Test | Input | Expected Advisory |
|------|-------|-------------------|
| `test_no_user` | Valid Dockerfile without USER | DV-BP-002 |
| `test_latest_tag` | `FROM python:latest` | DV-BP-001 |
| `test_add_usage` | `FROM python:3.12\nADD . .` | DV-BP-003 |
| `test_shell_form_cmd` | `CMD python app.py` | DV-BP-004 |
| `test_python_alpine` | `FROM python:3.12-alpine` | DV-BP-010 |
| `test_from_with_platform_flag` | R1-S10: `FROM --platform=$BUILDPLATFORM python:3.14-alpine` | No DV-BP-001 (image IS pinned) |
| `test_secret_in_env` | R1-S8: `ENV DB_PASSWORD=foo` | DV-BP-011 |
| `test_non_secret_env_no_advisory` | R1-S8: `ENV PYTHONDONTWRITEBYTECODE=1` | No DV-BP-011 |
| `test_gold_standard_no_advisories` | Gold Standard Dockerfile from research doc §12 | No advisories (all best practices satisfied) |

---

## Phase 5: Dockerfile Templates

**FR:** FR-DFA-005, FR-DFA-008
**Files:** `src/startd8/micro_prime/templates/dockerfile.py` (new — but note: `templates.py` is currently a file, not a package)
**Effort:** ~120 lines impl, ~60 lines tests
**Risk:** Low — new module
**Depends on:** Phase 4 (validator used for template output validation)

### 5.1 File location decision

`templates.py` is currently a single file. Two options:

- (a) Create `templates/dockerfile.py` and refactor `templates.py` → `templates/__init__.py` (disruptive)
- (b) Create `dockerfile_templates.py` as a peer module (non-disruptive)

**Decision: Option (b)** — create `src/startd8/micro_prime/dockerfile_templates.py`. No refactoring of existing code. The template registry integration (FR-DFA-008) imports from both modules.

### 5.2 Template strings

Define two template strings as module-level constants. Each template embeds comments referencing the DV-BP rules it satisfies.

The **multi-stage template** has two language-specific variants stored as dicts:

- `_MULTISTAGE_DEFAULTS["go"]` — Go-specific defaults
- `_MULTISTAGE_DEFAULTS["python"]` — Python wheels-based defaults (Gold Standard pattern)

The **single-stage template** is language-agnostic with Python defaults.

### 5.3 Template selection function

```python
def select_dockerfile_template(
    file_path: str,
    existing_content: str | None,
    context: dict[str, Any] | None,
) -> tuple[str, dict[str, str]]:
    """Select template and populate variable defaults.

    Returns:
        (template_string, variables_dict) — ready for str.format_map()
    """
```

### 5.4 `render_dockerfile_template()` function

```python
def render_dockerfile_template(
    file_path: str,
    existing_content: str | None = None,
    context: dict[str, Any] | None = None,
) -> str:
    """Render a complete Dockerfile from template.

    Edit mode: returns existing_content as-is.
    Create mode: selects template, substitutes variables, validates.
    """
```

### 5.6 Template registry integration (R1-S3)

Add `language: str = "python"` field to `CodeTemplate` in `templates.py`. Update `TemplateRegistry.get_templates()` to accept an optional `language` filter parameter. Register Dockerfile templates in the registry so `TemplateRegistry.get_templates(language="dockerfile")` returns only Dockerfile templates.

### 5.7 Tests (`tests/unit/micro_prime/test_dockerfile_templates.py`)

| Test | Description |
|------|-------------|
| `test_multistage_go_defaults` | Render multi-stage with Go defaults → valid Dockerfile, has 2 FROM stages |
| `test_multistage_python_defaults` | Render multi-stage with Python defaults → valid, uses wheels pattern, has non-root USER |
| `test_singlestage_defaults` | Render single-stage with defaults → valid, has COPY before source |
| `test_edit_mode_passthrough` | Existing content provided → returned as-is |
| `test_custom_variables` | Context overrides port, base_image → rendered correctly |
| `test_template_output_validates` | All template outputs pass `validate_dockerfile()` |
| `test_multistage_satisfies_best_practices` | Multi-stage template output has no DV-BP advisories (except DV-BP-001 if using default image) |

---

## Phase 6: Assembler + Splicer Extensions

**FR:** FR-DFA-006, FR-DFA-007
**Files:** `src/startd8/utils/file_assembler.py`, `src/startd8/micro_prime/splicer.py`, tests
**Effort:** ~60 lines impl, ~50 lines tests
**Risk:** Low — additive methods, no existing behavior changed
**Depends on:** Phase 4, Phase 5

### 6.1 Add `render_dockerfile()` to `DeterministicFileAssembler`

In `file_assembler.py`, add method after the existing `render_file()`:

```python
def render_dockerfile(
    self,
    file_spec: ForwardFileSpec,
    existing_content: str | None = None,
    context: dict[str, Any] | None = None,
) -> str:
    """Render a Dockerfile skeleton (FR-DFA-006).

    Edit mode: returns existing_content (passthrough).
    Create mode: renders from template.
    """
    from startd8.micro_prime.dockerfile_templates import render_dockerfile_template

    return render_dockerfile_template(
        file_path=file_spec.file,
        existing_content=existing_content,
        context=context,
    )
```

This is a thin delegation to the template module — keeps the assembler's role as the routing layer.

### 6.2 Add `splice_dockerfile()` to splicer

> **R1-S2 scope note**: Phase 7.2 calls `splice_dockerfile(skeleton, skeleton, file_path)` even when `generated_content == skeleton` (passthrough mode). This establishes the call path so future LLM modification has an integration point. The splice function validates the content and falls back to skeleton on failure.

In `splicer.py`, add a new function:

```python
def splice_dockerfile(
    skeleton: str,
    generated_content: str,
    file_path: str,
) -> str:
    """Full-file replacement for Dockerfiles (FR-DFA-007, REQ-MP-362).

    Replaces entire file content. Validates generated content;
    falls back to skeleton if validation fails.
    """
    from startd8.micro_prime.validators.dockerfile import validate_dockerfile

    if not generated_content or not generated_content.strip():
        logger.warning("Empty generated content for %s, keeping skeleton", file_path)
        return skeleton

    result = validate_dockerfile(generated_content)
    if not result.valid:
        logger.warning(
            "Generated Dockerfile for %s failed validation (%s), keeping skeleton",
            file_path, "; ".join(result.errors),
        )
        return skeleton

    return generated_content
```

### 6.3 Tests

| Test | Description |
|------|-------------|
| `test_render_dockerfile_edit_mode` | Existing content → returns it unchanged |
| `test_render_dockerfile_create_mode` | No existing content → renders from template |
| `test_splice_valid_replacement` | Valid generated content → replaces skeleton |
| `test_splice_invalid_fallback` | Invalid generated content → returns skeleton |
| `test_splice_empty_fallback` | Empty generated content → returns skeleton |
| `test_render_file_unchanged` | Existing `render_file()` for Python still works (regression) |

---

## Phase 7: Prime Adapter Integration

**FR:** FR-DFA-010
**Files:** `src/startd8/micro_prime/prime_adapter.py`, `src/startd8/forward_manifest_extractor.py`, `tests/unit/micro_prime/test_dockerfile_assembly.py` (new)
**Effort:** ~60 lines impl, ~80 lines tests
**Risk:** Medium — modifies core pipeline routing. Test thoroughly.
**Depends on:** Phase 1–6

> **R1-S6 scope note**: Phase 7 implements **skeleton passthrough only**. Dockerfiles are written to output as-is (edit mode) or from template (create mode). LLM-based modification of Dockerfiles is deferred to a follow-up (likely via the `file_ollama_whole` path or cloud fallback). The escalation conflation fix (Phase 1) enables this future path by ensuring bypass files reach the fallback generator.

### 7.1 Update `_generate_skeletons()`

Add language-aware dispatch:

```python
def _generate_skeletons(self, manifest, target_files):
    from startd8.utils.file_assembler import DeterministicFileAssembler
    from startd8.micro_prime.lang_detect import detect_language

    assembler = DeterministicFileAssembler(
        element_registry=self._element_registry,
    )
    skeletons: dict[str, str] = {}

    for file_path in target_files:
        file_spec = manifest.file_specs.get(file_path)
        if file_spec is None:
            logger.debug("No file_spec for %s, skipping skeleton", file_path)
            continue

        lang = detect_language(file_path, explicit_lang=getattr(file_spec, "language", None))

        if lang == "dockerfile":
            # R1-S1: Use existing_files dict (passed via context), not non-existent methods
            existing = existing_files.get(file_path, "")
            source = assembler.render_dockerfile(
                file_spec, existing_content=existing or None, context=context,
            )
            if source:
                skeletons[file_path] = source
                logger.debug("Generated Dockerfile skeleton for %s (%d lines)",
                             file_path, source.count("\n") + 1)
        elif lang == "python":
            # Existing path — unchanged
            try:
                source = assembler.render_file(file_spec)
                skeletons[file_path] = source
                ...
            except (...) as exc:
                ...
        else:
            logger.debug("Unsupported language '%s' for %s, skipping skeleton", lang, file_path)

    return skeletons
```

### 7.2 Update `_process_target_files()`

Add Dockerfile routing before the element-level engine:

```python
for file_path in target_files:
    file_spec = manifest.file_specs.get(file_path)
    skeleton = skeletons.get(file_path, "")

    if file_spec is None or not skeleton:
        st.bypass_files.append(file_path)  # Phase 1 change
        continue

    lang = detect_language(file_path, explicit_lang=getattr(file_spec, "language", None))

    if lang == "dockerfile":
        # Dockerfile: file-level processing, not element-level
        from startd8.micro_prime.validators.dockerfile import validate_dockerfile
        validation = validate_dockerfile(skeleton)

        if validation.errors:
            logger.warning("Dockerfile skeleton for %s has errors: %s",
                          file_path, "; ".join(validation.errors))

        # Write skeleton as the output file
        output_path = self._resolve_output_path(file_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(skeleton, encoding="utf-8")

        st.generated_files.append(output_path)
        st.written_file_paths.add(file_path)
        st.effective_file_count += 1

        # Create a minimal FileResult for metadata
        ...
        continue

    # Existing Python element-level processing
    ...
```

### 7.3 ForwardManifestExtractor integration

The Phase 3 change to the extractor must be verified to produce correct results for the prime adapter. Specifically:

- The `file_specs` dict must include the Dockerfile entry when target files contain a Dockerfile
- The adapter's `_generate_skeletons()` must find the entry via `manifest.file_specs.get(file_path)`

### 7.4 Tests (`tests/unit/micro_prime/test_dockerfile_assembly.py`)

| Test | Description |
|------|-------------|
| `test_dockerfile_through_full_pipeline` | Mock ForwardManifest with Dockerfile entry → adapter processes it → GenerationResult.success=True |
| `test_edit_mode_end_to_end` | Existing Dockerfile content in context → skeleton = existing content → file written to output |
| `test_create_mode_end_to_end` | No existing content → template rendered → file written to output |
| `test_mixed_python_and_dockerfile` | Feature with both `.py` and `Dockerfile` targets → Python goes through engine, Dockerfile through file-level path → both succeed |
| `test_dockerfile_validation_logged` | Dockerfile with DV-BP advisories → advisories logged at info level |
| `test_dockerfile_bypass_when_no_file_spec` | Dockerfile not in manifest → bypass_files (not escalated_files) |
| `test_effective_file_count_includes_dockerfiles` | Dockerfile processed → `effective_file_count` incremented |
| `test_generation_metadata_tracks_dockerfile` | Metadata includes `dockerfile_file_count` |
| `test_advisories_in_metadata` | R1-S9: Validation advisories appear in GenerationResult metadata (not just logs) |

---

## Commit Strategy

| Phase | Branch | Commit Message Pattern |
|-------|--------|----------------------|
| Phase 1 | `fix/escalation-conflation` | `fix(micro-prime): separate file-level bypass from element escalation in prime_adapter` |
| Phase 2 | `feat/dockerfile-assembly` | `feat(micro-prime): add language detection module (REQ-MP-330)` |
| Phase 3 | same branch | `feat(forward-manifest): add language field to ForwardFileSpec (REQ-MP-331)` |
| Phase 4 | same branch | `feat(micro-prime): add Dockerfile structural validator (REQ-MP-322)` |
| Phase 5 | same branch | `feat(micro-prime): add Dockerfile templates (REQ-MP-350, REQ-MP-351)` |
| Phase 6 | same branch | `feat(micro-prime): add Dockerfile assembly and splicing (REQ-MP-362)` |
| Phase 7 | same branch | `feat(micro-prime): wire Dockerfile assembly into prime_adapter pipeline` |

Phase 1 is on a separate branch because it's a standalone bug fix that can ship independently.

Phases 2–7 build on each other and should be on a single feature branch. Each phase is a separate commit for clean review.

---

## Verification Checklist

After all phases are complete:

- [ ] `pytest tests/unit/` — all existing tests pass (Python regression safety)
- [ ] `pytest tests/unit/micro_prime/test_lang_detect.py` — 9 tests pass
- [ ] `pytest tests/unit/micro_prime/test_dockerfile_validator.py` — ~15 tests pass
- [ ] `pytest tests/unit/micro_prime/test_dockerfile_templates.py` — ~7 tests pass
- [ ] `pytest tests/unit/test_escalation_conflation.py` — 5 tests pass
- [ ] `pytest tests/unit/micro_prime/test_dockerfile_assembly.py` — ~8 tests pass
- [ ] PI-013 re-run: `run_prime_workflow.py` with online-boutique PI-013 seed → `success=True`
- [ ] Gold Standard Dockerfile (from research doc §12) passes validator with zero advisories
- [ ] PI-013 loadgenerator Dockerfile passes validator (structural: valid)
- [ ] ForwardFileSpec JSON serialization round-trip includes `language` field
- [ ] No new dependencies added to `pyproject.toml`

---

## Appendix A: Areas Substantially Addressed

*(Updated per CRP convergent review rounds)*

| Area | Suggestions Addressed | Status |
|------|----------------------|--------|
| Architecture | 0 / 2 | ⚠️ Partial — R1-S7 deferred (premature LanguageHandler abstraction) |
| Interfaces | 1 / 2 | ⚠️ Partial — R1-S3 applied (CodeTemplate.language sub-step) |
| Data | 1 / 2 | ⚠️ Partial — R1-S10 applied (--platform parsing fix) |
| Risks | 4 / 4 | ✅ Addressed — R1-S1 (method fix), S2 (splice scope), S4 (bypass handling), S6 (scope note) |
| Validation | 1 / 2 | ⚠️ Partial — R1-S5 applied (continuation edge case) |
| Ops | 1 / 2 | ⚠️ Partial — R1-S9 applied (advisory metadata test) |
| Security | 1 / 2 | ⚠️ Partial — R1-S8 applied (DV-BP-011 secrets) |

---

## Appendix B: Requirements Coverage

| Requirement | Plan Phase | Status | Notes |
|-------------|-----------|--------|-------|
| FR-DFA-001 | Phase 1 | ✅ Covered | `bypass_files` + split escalation gate |
| FR-DFA-002 | Phase 2 | ✅ Covered | `lang_detect.py` with extension/filename maps |
| FR-DFA-003 | Phase 3 | ✅ Covered | Extractor pre-check before Python AST path |
| FR-DFA-004 | Phase 4 | ✅ Covered | Structural rules + advisory rules |
| FR-DFA-005 | Phase 5 | ✅ Covered | Two templates with language-specific defaults |
| FR-DFA-006 | Phase 6 | ✅ Covered | `render_dockerfile()` thin delegation |
| FR-DFA-007 | Phase 6 | ⚠️ Partial | splice_dockerfile() now called in Phase 7.2 passthrough — R1-S2 |
| FR-DFA-008 | Phase 5 | ⚠️ Partial | Phase 5.6 sub-step added for CodeTemplate.language — R1-S3 |
| FR-DFA-009 | Phase 3 | ✅ Covered | Optional field + serialization |
| FR-DFA-010 | Phase 7 | ⚠️ Partial | Skeleton passthrough only (R1-S6 scope note added) — LLM modification deferred |
| NFR-DFA-001 | All | ✅ Covered | Zero LLM calls in deterministic path |
| NFR-DFA-002 | All | ✅ Covered | stdlib + existing imports only |
| NFR-DFA-003 | All | ✅ Covered | Regression tests specified per phase |
| NFR-DFA-004 | Phase 4 | ✅ Covered | Rule ID system, separate functions |
| NFR-DFA-005 | Phase 4, 5 | ⚠️ Partial | No performance benchmarks in test plan |

---

## Appendix C: Review Suggestions

### Round 1 (R1)

**R1-S1 (Risks, critical): Phase 7 references non-existent adapter methods**

Phase 7.1 `_generate_skeletons()` calls `self._get_existing_content(file_path)` and `self._get_task_context()`. Neither method exists on the adapter class. The existing adapter accesses existing file content through `mp_context.existing_files` (a dict passed into `generate()`), and task context through `mp_context.seed_task` or the feature's context dict.

**Recommendation**: Replace `self._get_existing_content(file_path)` with `mp_context.existing_files.get(file_path, "")` (or whichever dict carries existing file content). Replace `self._get_task_context()` with `mp_context.seed_task.context` or equivalent. Document the exact data access pattern so the implementer doesn't need to reverse-engineer the adapter's internal state.

---

**R1-S2 (Risks, high): `splice_dockerfile()` is defined but never called**

Phase 6.2 defines `splice_dockerfile()` in splicer.py. Phase 7.2 `_process_target_files()` writes the skeleton directly to disk via `output_path.write_text(skeleton)`. The splice function is never invoked. This means:

- The validation inside `splice_dockerfile()` (fallback to skeleton on invalid content) is dead code
- If a future LLM modification path is added, it has no integration point

**Recommendation**: Either (a) call `splice_dockerfile(skeleton, generated_content, file_path)` in Phase 7.2 where the file is written (even if `generated_content == skeleton` for now — establishes the call path), or (b) explicitly defer `splice_dockerfile()` to a follow-up phase and document that Phase 7 writes skeletons directly. Option (a) is preferred — it's cheap and future-proofs the integration.

---

**R1-S3 (Interfaces, high): FR-DFA-008 `CodeTemplate.language` field has no implementation step**

FR-DFA-008 requires adding a `language: str = "python"` field to the `CodeTemplate` dataclass and updating `TemplateRegistry` to use language-aware selection. No plan phase covers this change. Phase 5 creates `dockerfile_templates.py` but doesn't touch `templates.py` or `CodeTemplate`.

**Recommendation**: Add a sub-step to Phase 5 (e.g., §5.6) that: (1) adds `language: str = "python"` to `CodeTemplate` in `templates.py`, (2) updates `TemplateRegistry.get_templates()` to accept an optional `language` filter, (3) registers the Dockerfile templates in the registry. Include a test verifying `TemplateRegistry.get_templates(language="dockerfile")` returns only Dockerfile templates.

---

**R1-S4 (Risks, high): Phase 1 bypass with no fallback — silent file loss**

Phase 1.3 shows the bypass gate: `if st.bypass_files and self._fallback is not None: ...`. When `self._fallback is None` (no cloud fallback configured), bypass files are never processed and never logged as failed. They silently drop out. The plan mentions a `test_bypass_no_fallback_available` test case but the implementation code doesn't show the handling.

**Recommendation**: Add an explicit `elif st.bypass_files and self._fallback is None:` branch that (1) logs a WARNING listing the unprocessable files, (2) does NOT set `success=False` if local files were still processed (bypass files shouldn't penalize local success), but (3) includes `bypass_file_count` in metadata so the caller knows files were skipped. Show this code in §1.3.

---

**R1-S5 (Validation, medium): Validator continuation-line edge case with whitespace-only lines**

Phase 4.3 resets `in_continuation = False` on blank lines (`if not stripped: in_continuation = False`). But a whitespace-only line (e.g., spaces/tabs with a trailing `\`) has `stripped = "\\"`, which is not blank. It enters the directive-parsing logic with `first_word = "\\"` → not in KNOWN_DIRECTIVES → generates a DV-002 warning. In practice this is unlikely, but the PI-013 Dockerfile uses continuation lines and we should handle edge cases cleanly.

**Recommendation**: Before the directive-parsing section, add a check: `if stripped == "\\":  in_continuation = True; continue`. This handles the degenerate case of a continuation marker on an otherwise empty line. Add a test case for this edge.

---

**R1-S6 (Risks, high): Phase 7 is pure passthrough — no LLM modification capability for Dockerfiles**

Phase 7.2 writes the skeleton directly as the output. For edit-mode Dockerfiles (PI-013), the skeleton IS the existing content, so the output is the *unchanged* existing Dockerfile. The pipeline successfully "processes" the file but doesn't modify it. FR-DFA-010b says "OR delegate to the fallback generator for LLM-based modification" but Phase 7 never implements this path.

This is acceptable for MVP (skeleton assembly is deterministic, modifications are a follow-up), but should be explicitly documented as a known limitation. Currently the plan reads as if Dockerfiles will be fully processed.

**Recommendation**: Add a "Phase 7 Scope Note" box clarifying: "Phase 7 implements skeleton passthrough only. Dockerfiles are written to output as-is (edit mode) or from template (create mode). LLM-based modification of Dockerfiles is deferred to a follow-up (likely via the `file_ollama_whole` path or cloud fallback). The escalation conflation fix (Phase 1) enables this future path by ensuring bypass files reach the fallback generator." Also update the Verification Checklist item for PI-013: the expected result is that the existing Dockerfile is written to output unchanged, not that it's meaningfully modified.

---

**R1-S7 (Architecture, high): `_generate_skeletons()` and `_process_target_files()` dispatch will diverge across languages — no registry pattern**

The Phase 7 plan adds `if lang == "dockerfile": ... elif lang == "python": ...` branches directly into both `_generate_skeletons()` and `_process_target_files()`. When Go support ships (REQ-MP-340–346), a third `elif lang == "go"` block will be added to each method. This creates a growing if/elif chain in two places — a pattern that scales poorly and creates two separate maintenance surfaces.

The guide (Lens C) flags this as critical: patterns established for Dockerfiles will be copied for Go. If the dispatch pattern is a raw if/elif, Go will copy the anti-pattern.

**Recommendation**: Define a `LanguageHandler` protocol (or simple dataclass) before Phase 7 that encapsulates skeleton generation and file processing per language:

```python
@dataclass
class LanguageHandler:
    lang: str
    render_skeleton: Callable[[ForwardFileSpec, str | None, dict], str]
    process_file: Callable[[str, str, _FileProcessingState], None]

_HANDLERS: dict[str, LanguageHandler] = {
    "dockerfile": LanguageHandler(...),
    "python": LanguageHandler(...),
}
```

The `_generate_skeletons()` and `_process_target_files()` methods then do `handler = _HANDLERS.get(lang)` — a single lookup, no branching. Adding Go requires registering a new handler, not modifying existing methods. This does not need to be a full plugin system — a module-level dict is sufficient.

---

**R1-S8 (Security, high): Advisor rules don't detect secrets in ENV — DV-BP gap**

The research doc (§9) identifies ENV-based secret storage as a critical security anti-pattern: `ENV DATABASE_PASSWORD "SuperSecretSauce"`. The advisory rule set (DV-BP-001–010) has no rule for this. The validator checks for USER, COPY vs ADD, pinned images, and exec form — but not for obvious secret patterns in ENV directives.

This is particularly relevant for template-generated Dockerfiles: if a user passes `{env_block}` context that includes secrets, the template will bake them in and the validator will not flag it.

**Recommendation**: Add DV-BP-011:

```python
# DV-BP-011: No plaintext secrets in ENV
_SECRET_PATTERN = re.compile(
    r"(?i)(password|secret|token|api_key|private_key|auth)\s*=\s*\S+"
)
for line in lines:
    stripped = line.strip()
    if stripped.upper().startswith("ENV ") and _SECRET_PATTERN.search(stripped):
        advisories.append(
            "DV-BP-011: ENV may contain a plaintext secret — "
            "use runtime env vars or Docker secrets instead"
        )
```

This is a heuristic, not a guarantee — it catches obvious patterns like `ENV DB_PASSWORD=foo` without false-positiving on `ENV PYTHONDONTWRITEBYTECODE=1`. Add a test case for this rule and a negative test (PYTHONDONTWRITEBYTECODE should not trigger it).

---

**R1-S9 (Ops, medium): Advisories are logged but never surfaced in pipeline output or FileResult metadata**

Phase 7.2 logs validation advisories (`logger.warning`) but they never appear in the `FileResult` or `GenerationResult` metadata that the caller uses to display pipeline output. The research doc (§8) notes `DockerfileValidationResult` should carry enough information for debugging — but if advisories are only in logs (Loki), they're invisible to the user running `run-prime-contractor.sh` without log access.

For the PI-013 loadgenerator, the validator will fire DV-BP-004 (shell ENTRYPOINT), DV-BP-010 (Alpine), and DV-BP-002 (no USER). These are high-value observations that a developer would want to see.

**Recommendation**: Thread advisories into the `GenerationResult` or a new `FileProcessingNote` structure that's included in `prime-result.json`. Alternatively, add an advisory summary to the prime adapter's existing stdout summary block (the one that prints per-file outcomes). At minimum, define where advisories surface in the pipeline output so the implementer has a clear target. Add a test in §7.4 that verifies advisories from the validator appear in the output (not just logs).

---

**R1-S10 (Data, high): Validator `--platform` parsing in `_check_structural_rules()` is broken for multi-word FROM lines**

Phase 4.3 strips `--platform` flags with this logic:

```python
first_word = stripped.split()[0].upper()
directive = first_word.lstrip("-")
if "=" in directive or directive.startswith("-"):
    continue  # treats as flag continuation, not directive
```

For `FROM --platform=$BUILDPLATFORM python:3.14.2-alpine AS builder`, `first_word` is `"FROM"` — which IS in KNOWN_DIRECTIVES — so it proceeds correctly. But then the best-practice code in `_check_best_practices()` for DV-BP-001 does:

```python
if stripped.upper().startswith("FROM "):
    image_ref = stripped.split()[1]
```

For `FROM --platform=$BUILDPLATFORM python:3.14.2-alpine AS builder`, `stripped.split()[1]` returns `"--platform=$BUILDPLATFORM"` — not the image reference. The `":" not in image_ref` check then fires and adds a false-positive DV-BP-001 advisory ("should use a pinned version tag") even though `python:3.14.2-alpine` IS pinned.

This is a concrete bug for PI-013 (Appendix A) which uses exactly this pattern.

**Recommendation**: Fix the FROM image extraction to skip `--platform` and `--network` flags:

```python
if stripped.upper().startswith("FROM "):
    parts = stripped.split()
    # Skip flags (--platform=..., --network=...)
    image_parts = [p for p in parts[1:] if not p.startswith("--")]
    image_ref = image_parts[0] if image_parts else ""
```

Add `test_from_with_platform_flag` as a required test in §4.5 (currently missing from the test plan).
