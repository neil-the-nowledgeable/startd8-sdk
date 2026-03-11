# Dockerfile Deterministic Skeleton Assembly — Requirements

> **Version:** 0.2.0
> **Status:** DRAFT
> **Date:** 2026-03-11
> **Scope:** End-to-end Dockerfile support through the MicroPrime pipeline — from manifest extraction through deterministic skeleton assembly, structural validation, and file-level splicing
> **Motivation:** PI-013 (Dockerfile — loadgenerator) fails with score=0.00 because the pipeline has no path for non-Python files when `escalation_enabled=false`. This is the first concrete implementation slice of the polyglot template registry (REQ-MP-3xx).
> **Depends on:** ForwardManifest models, DeterministicFileAssembler, MicroPrime prime_adapter, REQ-MP-3xx Layer 4
> **Implements:** REQ-MP-322, REQ-MP-330, REQ-MP-350–352, REQ-MP-362 (partial)
> **Research:** [docker-file-assembly-via-python.md](../scaffold/docker-file-assembly-via-python.md) — Dockerfile best practices (base image selection, multi-stage builds, security, layer ordering)

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Root Cause Analysis](#2-root-cause-analysis)
3. [Design Goals](#3-design-goals)
4. [Scope](#4-scope)
5. [Data Flow](#5-data-flow)
6. [Functional Requirements](#6-functional-requirements)
7. [Non-Functional Requirements](#7-non-functional-requirements)
8. [Files Created / Modified](#8-files-created--modified)
9. [Test Strategy](#9-test-strategy)
10. [Open Questions](#10-open-questions)
11. [Cross-References](#11-cross-references)

---

## 1. Problem Statement

When the PrimeContractor workflow processes a Dockerfile target file (e.g., `src/loadgenerator/Dockerfile`), the MicroPrime pipeline fails silently with `success=False`:

```
ForwardManifestExtractor → Python-only AST → no ForwardFileSpec for Dockerfiles
DeterministicFileAssembler → no file_spec → no skeleton
prime_adapter._process_target_files() → file_spec=None, skeleton="" → escalated_files
prime_adapter.generate() → escalation_enabled=false → success=False, score=0.00
```

There are two independent problems:

1. **Escalation conflation bug**: The `escalation_enabled` flag gates both element-level escalation (MP tried but failed) AND file-level bypass (files MP fundamentally can't process). These should be separate concerns.

2. **No Dockerfile pipeline path**: Even if escalation were enabled, Dockerfiles have no ForwardFileSpec, no skeleton, no structural validator, and no splicing strategy. They are invisible to the deterministic assembly pipeline.

This document addresses both problems.

---

## 2. Root Cause Analysis

### 2.1 PI-013 Failure Chain

| Step | What Happens | Why |
|------|-------------|-----|
| Plan ingestion | Produces rich seed for PI-013 (6 API signatures, 6 design sections) | Working correctly |
| `ForwardManifestExtractor` | Produces `file_specs` only for `.py` files | `_PYTHON_EXTENSIONS` guard skips Dockerfiles |
| `_generate_skeletons()` | `file_spec is None` → skip | No manifest entry to render |
| `_process_target_files()` | `file_spec is None or not skeleton` → `escalated_files` | Correct: nothing to process locally |
| Escalation gate | `escalation_enabled=false` → warning, no fallback | **Bug**: file-level bypass conflated with element escalation |
| `GenerationResult` | `success = effective_file_count > 0` → `False` | 0 files processed |
| `develop_feature()` | `result.success is False` → "Code generation failed" | PI-013 marked FAIL |

### 2.2 The Conflation Bug

In `prime_adapter.py`, the escalation gate (lines 418–432) treats all entries in `st.escalated_files` identically:

```python
if st.escalated_files and not self._config.escalation_enabled:
    logger.warning("Cloud escalation disabled ...")
```

But `escalated_files` contains two categorically different kinds of entries:

| Category | Description | Should Respect `escalation_enabled`? |
|----------|-------------|--------------------------------------|
| **Element-level escalation** | MP tried to process the file but elements were classified COMPLEX or repair failed | **Yes** — this is what the flag is for |
| **File-level bypass** | MP fundamentally cannot process this file type (no ForwardFileSpec, no language support) | **No** — these should always delegate to fallback |

### 2.3 Why Dockerfiles Are Different from Python

| Dimension | Python | Dockerfile |
|-----------|--------|-----------|
| AST parseable | Yes (`ast.parse()`) | No (not a programming language AST) |
| Has elements (functions/classes) | Yes | No — directives only |
| Stub concept | `raise NotImplementedError` | N/A — no function bodies |
| Skeleton concept | Signatures + stubs for LLM to fill | **Complete file** — the skeleton IS the content |
| Splicing | Replace stub body within function wrapper | **Full-file replacement** |
| Import ordering | isort-compatible groups | N/A |
| Element-level generation | Prompt per element → Ollama | N/A — single-file unit |

---

## 3. Design Goals

1. **Unblock PI-013 immediately** by fixing the escalation conflation bug (independent of skeleton assembly)
2. **Establish the Dockerfile pipeline path** so Dockerfiles can flow through MicroPrime deterministically
3. **Lay groundwork for REQ-MP-3xx** by implementing the first non-Python language support (Layer 2 detection + Layer 4 templates + Layer 1 validation + Layer 5 splicing)
4. **Keep it simple** — Dockerfiles have no element decomposition. The template IS the file. Don't over-engineer.

---

## 4. Scope

### 4.1 In Scope

- **FR-DFA-001**: Fix escalation conflation — separate file-level bypass from element-level escalation
- **FR-DFA-002**: Language detection from file path (implements REQ-MP-330)
- **FR-DFA-003**: ForwardManifestExtractor produces ForwardFileSpec for Dockerfiles
- **FR-DFA-004**: Dockerfile structural validator (implements REQ-MP-322)
- **FR-DFA-005**: Dockerfile templates — multi-stage build and single-stage service (implements REQ-MP-350, REQ-MP-351)
- **FR-DFA-006**: DeterministicFileAssembler Dockerfile rendering path
- **FR-DFA-007**: Full-file splicing for Dockerfiles (implements REQ-MP-362)
- **FR-DFA-008**: Dockerfile template registry integration (implements REQ-MP-352)
- **FR-DFA-009**: Optional `language` field on ForwardFileSpec (implements REQ-MP-331)
- **FR-DFA-010**: prime_adapter integration — route Dockerfiles through the assembly pipeline

### 4.2 Out of Scope

- Go/gRPC templates (REQ-MP-340–346) — separate implementation slice
- Go structural validator (REQ-MP-321) — separate implementation slice
- Go splicer support (REQ-MP-360, REQ-MP-361) — separate implementation slice
- Proto file support — deferred
- Ollama-based Dockerfile generation — future enhancement
- Dockerfile template selection from seed context heuristics (e.g., detecting compiled vs interpreted language from project metadata) — follow-up

### 4.3 Not Changing

- Python templates, validation, and assembly — untouched
- Existing `DeterministicFileAssembler.render_file()` for Python — no changes
- Existing element-level MicroPrime engine flow — unchanged
- `escalation_enabled` behavior for element-level escalation — unchanged

---

## 5. Data Flow

### 5.1 Current (Broken) Flow for Dockerfiles

```
Plan Ingestion
  └→ ParsedFeature: target_files=["src/loadgenerator/Dockerfile"]

ForwardManifestExtractor
  └→ ForwardManifest.file_specs = {} (no Dockerfile entry)

prime_adapter._generate_skeletons()
  └→ skeletons = {} (no file_spec)

prime_adapter._process_target_files()
  └→ file_spec=None → escalated_files=["src/loadgenerator/Dockerfile"]

prime_adapter escalation gate
  └→ escalation_enabled=false → warning → success=False → FAIL
```

### 5.2 Target Flow After Implementation

```
Plan Ingestion
  └→ ParsedFeature: target_files=["src/loadgenerator/Dockerfile"]
      existing_files: {"src/loadgenerator/Dockerfile": "<64-line existing content>"}

ForwardManifestExtractor
  └→ ForwardManifest.file_specs = {
       "src/loadgenerator/Dockerfile": ForwardFileSpec(
           file="src/loadgenerator/Dockerfile",
           language="dockerfile",        ← NEW (FR-DFA-009)
           elements=[],                  ← empty (no functions/classes)
           imports=[],                   ← empty (no imports)
           dependencies=None,
       )
     }

prime_adapter._generate_skeletons()
  └→ detects language="dockerfile"
  └→ calls assembler.render_dockerfile(file_spec, existing_content)
  └→ skeletons = {"src/loadgenerator/Dockerfile": "<skeleton content>"}

prime_adapter._process_target_files()
  └→ file_spec is not None AND skeleton is not empty
  └→ routes to file-level processing (not element-level engine)
  └→ validates via Dockerfile structural validator
  └→ writes file via full-file splicing

GenerationResult
  └→ success=True, effective_file_count=1
```

### 5.3 Escalation Conflation Fix Flow

```
prime_adapter._process_target_files()
  └→ file_spec=None for a target file
  └→ NEW: classify as "unsupported_language_bypass" (not "element_escalation")

prime_adapter escalation gate
  └→ bypass_files: always delegate to fallback (regardless of escalation_enabled)
  └→ element_escalated_files: respect escalation_enabled flag
```

---

## 6. Functional Requirements

### FR-DFA-001: Fix Escalation Conflation

The `prime_adapter.generate()` method SHALL distinguish between two categories of files that cannot be processed locally:

| Category | Identifier | Behavior |
|----------|-----------|----------|
| `bypass_files` | Files where `file_spec is None` AND language detection returns a language the engine does not support, OR files with no ForwardFileSpec in the manifest | Always delegate to fallback generator (ignores `escalation_enabled`) |
| `escalated_files` | Files where MicroPrime attempted processing but elements were classified COMPLEX or repair failed | Respects `escalation_enabled` flag |

The `_FileProcessingState` dataclass SHALL gain a `bypass_files: list[str]` field alongside the existing `escalated_files`.

The escalation gate logic SHALL be updated:

```python
# Bypass files always go to fallback (language/type not supported locally)
if st.bypass_files and self._fallback is not None:
    # delegate bypass_files to fallback regardless of escalation_enabled
    ...

# Element-escalated files respect the escalation_enabled flag
if st.escalated_files and not self._config.escalation_enabled:
    logger.warning("Cloud escalation disabled ...")
elif st.escalated_files and self._fallback is not None and self._config.escalation_enabled:
    # delegate escalated_files to fallback
    ...
```

**Rationale**: A project setting `escalation_enabled=false` communicates "I want local-only generation for files MicroPrime can handle." It should NOT mean "silently fail on file types MicroPrime doesn't support."

### FR-DFA-002: Language Detection from File Path

A `detect_language(file_path: str) -> Language` function SHALL be added (implements REQ-MP-330):

```python
from typing import Literal

Language = Literal["python", "dockerfile", "go", "proto", "unknown"]

_EXTENSION_TO_LANG: dict[str, Language] = {
    ".py": "python",
    ".pyi": "python",
    ".go": "go",
    ".proto": "proto",
}

_FILENAME_TO_LANG: dict[str, Language] = {
    "Dockerfile": "dockerfile",
}

_DOCKERFILE_PATTERN = re.compile(r"^Dockerfile(\..+)?$", re.IGNORECASE)

def detect_language(file_path: str, explicit_lang: Optional[str] = None) -> Language:
    """Detect language from file path or explicit override. Defaults to 'unknown'."""
    filename = Path(file_path).name
    # Check exact filename match first (Dockerfile)
    if filename in _FILENAME_TO_LANG:
        return _FILENAME_TO_LANG[filename]
    # Check Dockerfile variants (Dockerfile.dev, Dockerfile.prod)
    if _DOCKERFILE_PATTERN.match(filename):
        return "dockerfile"
    # Check extension
    ext = Path(file_path).suffix.lower()
    return _EXTENSION_TO_LANG.get(ext, "unknown")
```

**Location**: `src/startd8/micro_prime/lang_detect.py` (new module — shared by assembler, validator, splicer, adapter).

**Default**: Returns `"unknown"` (not `"python"`) for unrecognized extensions. Callers decide how to handle unknown languages. This is a deliberate departure from REQ-MP-330's default-to-python — safer for file-level bypass decisions.

**Dockerfile variants**: Recognizes `Dockerfile`, `Dockerfile.dev`, `Dockerfile.prod`, `dockerfile` (case-insensitive).

### FR-DFA-003: ForwardManifestExtractor Dockerfile Support

The `ForwardManifestExtractor` SHALL produce a `ForwardFileSpec` for Dockerfile target files:

- When a target file is detected as `language="dockerfile"` via `detect_language()`:
  - Create a `ForwardFileSpec(file=path, language="dockerfile", elements=[], imports=[], dependencies=None)`
  - No AST parsing is attempted (Dockerfiles are not parseable via Python's `ast` module)
  - The file_spec has zero elements — this signals downstream that the file is a single-unit target

- The existing Python AST extraction path SHALL be unchanged. The language check happens before AST parsing — non-Python files are handled by the new path, Python files continue through the existing path.

**Key insight**: The ForwardFileSpec for a Dockerfile carries no structural information. Its purpose is to:

1. Signal to the pipeline that this file exists in the manifest (prevents `file_spec is None` bypass)
2. Carry the `language` field for downstream routing
3. Allow the assembler to detect "this is a Dockerfile" and use the appropriate rendering strategy

### FR-DFA-004: Dockerfile Structural Validator

A `validate_dockerfile(content: str) -> DockerfileValidationResult` function SHALL be added (implements REQ-MP-322):

```python
@dataclass(frozen=True)
class DockerfileValidationResult:
    valid: bool
    errors: list[str]
    directives_found: list[str]   # e.g., ["FROM", "RUN", "COPY", ...]
    stage_count: int              # number of FROM directives
```

**Known directives** (Docker BuildKit):

```python
KNOWN_DIRECTIVES = frozenset({
    "FROM", "RUN", "CMD", "ENTRYPOINT", "COPY", "ADD", "WORKDIR",
    "ENV", "EXPOSE", "VOLUME", "USER", "ARG", "LABEL", "HEALTHCHECK",
    "SHELL", "STOPSIGNAL", "ONBUILD",
})
```

**Structural validation rules** (start simple, extend later):

| Rule | ID | Severity | Description |
|------|----|----------|-------------|
| Has at least one FROM | DV-001 | error | Every Dockerfile must begin with FROM (after optional parser directive / ARG) |
| All directive lines use known directives | DV-002 | warning | Unknown directives logged as warning, not hard error (future Docker versions may add new directives) |
| No empty Dockerfile | DV-003 | error | Content must have at least one non-comment, non-blank line |
| Balanced quotes in ENV/LABEL values | DV-004 | warning | Unmatched quotes in ENV or LABEL values |
| Parser directive position | DV-005 | warning | `# syntax=` and `# escape=` must appear before any directive or blank line |

**Best-practice advisory rules** (from [docker-file-assembly-via-python.md](../scaffold/docker-file-assembly-via-python.md)):

These rules produce `advisory` severity results — they inform the LLM prompt or generate review comments but do NOT block pipeline progress:

| Rule | ID | Severity | Description | Priority |
|------|----|----------|-------------|----------|
| Pinned base image version | DV-BP-001 | advisory | FROM should use a versioned tag (e.g., `python:3.12-slim`), not `:latest` or bare name | Critical |
| Non-root USER | DV-BP-002 | advisory | Dockerfile should include a `USER` directive to run as non-root | Critical |
| COPY over ADD | DV-BP-003 | advisory | Prefer `COPY` over `ADD` unless archive extraction is needed | High |
| Exec form CMD/ENTRYPOINT | DV-BP-004 | advisory | `CMD`/`ENTRYPOINT` should use exec form `["binary", "arg"]`, not shell form `"binary arg"` — ensures proper PID 1 signal handling | High |
| Deps before source | DV-BP-005 | advisory | `COPY requirements.txt` (or equivalent) should appear before `COPY . .` for layer cache efficiency | High |
| Combined apt-get | DV-BP-006 | advisory | `apt-get update` and `apt-get install` should be in the same `RUN` directive with cleanup (`rm -rf /var/lib/apt/lists/*`) | High |
| Multi-stage for production | DV-BP-007 | advisory | Production Dockerfiles should use multi-stage builds to separate build tooling from runtime | Medium |
| HEALTHCHECK present | DV-BP-008 | advisory | Dockerfile should include a `HEALTHCHECK` directive for container health monitoring | Medium |
| LABEL metadata | DV-BP-009 | advisory | Dockerfile should include `LABEL` with at least maintainer or version metadata | Nice-to-have |
| Prefer `-slim` over `-alpine` | DV-BP-010 | advisory | Python base images: prefer `-slim` over `-alpine` (musl libc breaks many C-extension wheels, builds 50x slower) | Medium |

The advisory rules SHALL be returned in the `DockerfileValidationResult` as a separate `advisories: list[str]` field. The `valid` field is determined only by structural rules (DV-001 through DV-005).

```python
@dataclass(frozen=True)
class DockerfileValidationResult:
    valid: bool
    errors: list[str]           # from structural rules (DV-001–DV-005)
    warnings: list[str]         # from structural rules with severity=warning
    advisories: list[str]       # from best-practice rules (DV-BP-001–DV-BP-010)
    directives_found: list[str]
    stage_count: int
```

**What is NOT validated** (intentionally deferred):

- Base image existence/validity (requires network access)
- COPY source path existence (requires build context)
- Multi-stage reference validity (e.g., `COPY --from=builder` references a valid stage)
- Shell command syntax within RUN directives
- Platform-specific directives (`--platform=$BUILDPLATFORM`)

**Line parsing rules**:

- Lines starting with `#` are comments — skipped
- Blank lines are skipped
- Lines starting with a known directive (case-insensitive first word) are valid
- Continuation lines: a line ending with `\` means the next line is a continuation of the same directive — do not validate the continuation line as a directive
- `# syntax=` and `# escape=` are parser directives, not comments — recognized specially

**Location**: `src/startd8/micro_prime/validators/dockerfile.py` (new module).

### FR-DFA-005: Dockerfile Templates

Two Dockerfile templates SHALL be defined (implements REQ-MP-350, REQ-MP-351). Template design incorporates best practices from [docker-file-assembly-via-python.md](../scaffold/docker-file-assembly-via-python.md) — specifically the Gold Standard pattern (§12): multi-stage wheels build, non-root user, HEALTHCHECK, exec form CMD, pinned versions, proper layer ordering.

#### Template 1: Multi-Stage Build (`dockerfile_multistage`)

For compiled-language services (Go, Rust, Java, C++) or Python services that benefit from build/runtime separation (the Gold Standard pattern):

```dockerfile
# syntax=docker/dockerfile:1

##############################################
# Stage 1: builder
##############################################
FROM {builder_image} AS builder

{builder_env_block}

WORKDIR {workdir}

# System build deps — combined RUN with cleanup (DV-BP-006)
{build_deps_block}

# Deps before source — maximizes cache reuse (DV-BP-005)
COPY {dependency_files} .
RUN {install_deps_command}

COPY . .
{build_command_block}

##############################################
# Stage 2: runtime
##############################################
FROM {runtime_image}

LABEL maintainer="{maintainer}"

# Non-root user — principle of least privilege (DV-BP-002)
RUN addgroup --gid 1001 --system appuser && \
    adduser --no-create-home --shell /bin/false \
            --uid 1001 --system --gid 1001 appuser

WORKDIR {workdir}

COPY --from=builder {build_artifact} {runtime_artifact_dest}
{runtime_copy_extras}

{runtime_env_block}

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD {healthcheck_command}

EXPOSE {port}

# Exec form — proper PID 1 signal handling (DV-BP-004)
{run_directive} {run_command}
```

**Template variables** (with defaults):

| Variable | Default (Go) | Default (Python) | Source |
|----------|-------------|-----------------|--------|
| `builder_image` | `golang:1.22-alpine` | `python:3.12-slim` | Seed context: `service_metadata.language` |
| `runtime_image` | `alpine:3.19` | `python:3.12-slim` | Seed context: `service_metadata.base_image` |
| `workdir` | `/app` | `/app` | Convention |
| `builder_env_block` | *(empty)* | `ENV PYTHONDONTWRITEBYTECODE=1 \`<br>`    PYTHONUNBUFFERED=1` | Language-specific |
| `runtime_env_block` | *(empty)* | `ENV PYTHONDONTWRITEBYTECODE=1 \`<br>`    PYTHONUNBUFFERED=1` | Language-specific |
| `build_deps_block` | *(empty — Go has no apt deps)* | *(empty — opt-in only for C-extension projects)* | Language-specific |
| `dependency_files` | `go.mod go.sum ./` | `requirements.txt .` | Language-specific |
| `install_deps_command` | `go mod download` | `pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt` | Language-specific |
| `build_command_block` | `RUN CGO_ENABLED=0 go build -o /bin/service .` | *(empty — wheels approach, no compile step)* | Language-specific |
| `build_artifact` | `/bin/service` | `/app/wheels` | Language-specific |
| `runtime_artifact_dest` | `/bin/service` | `/wheels` | Language-specific |
| `runtime_copy_extras` | *(empty)* | `COPY --from=builder /app/requirements.txt .\nRUN pip install --no-cache /wheels/* && rm -rf /wheels` | Language-specific |
| `maintainer` | `team@example.com` | `team@example.com` | Seed context |
| `healthcheck_command` | `wget -qO- http://localhost:{port}/health \|\| exit 1` | `python -c "import urllib.request; urllib.request.urlopen('http://localhost:{port}/health')"` | Language-specific |
| `port` | `8080` | `8080` | Seed context: `service_metadata.port` |
| `run_directive` | `ENTRYPOINT` | `CMD` | Language-specific |
| `run_command` | `["/bin/service"]` | `["gunicorn", "-w", "4", "-b", "0.0.0.0:{port}", "app:app"]` | Seed context |

**Python wheels vs prefix-install**: The Gold Standard research (§2) shows the wheels-based multi-stage approach produces smaller images (156MB vs 259MB) and cleanly separates build tooling from runtime. This is the preferred Python multi-stage pattern. The `--prefix="/install"` pattern (used in PI-013's loadgenerator) is an alternative that works but carries pip itself into the runtime image.

#### Template 2: Single-Stage Service (`dockerfile_singlestage`)

For simple interpreted-language services where multi-stage overhead isn't justified (dev environments, simple scripts, load generators):

```dockerfile
# syntax=docker/dockerfile:1

FROM {base_image}

LABEL maintainer="{maintainer}"

{env_block}

WORKDIR {workdir}

# Deps before source — maximizes cache reuse (DV-BP-005)
COPY {dependency_files} .
RUN {install_deps_command}

# Source last — most likely to change
COPY {source_files} .

EXPOSE {port}

# Exec form — proper PID 1 signal handling (DV-BP-004)
{run_directive} {run_command}
```

**Template variables** (with defaults):

| Variable | Default | Source |
|----------|---------|--------|
| `base_image` | `python:3.12-slim` | Seed context: `service_metadata.language` |
| `env_block` | `ENV PYTHONDONTWRITEBYTECODE=1 \`<br>`    PYTHONUNBUFFERED=1` | Language-specific |
| `maintainer` | `team@example.com` | Seed context |
| `workdir` | `/app` | Convention |
| `dependency_files` | `requirements.txt .` | Seed context: `service_metadata.language` |
| `install_deps_command` | `pip install --no-cache-dir -r requirements.txt` | Seed context |
| `source_files` | `. .` | Convention |
| `port` | `8080` | Seed context: `service_metadata.port` |
| `run_directive` | `CMD` | Seed context (CMD vs ENTRYPOINT) |
| `run_command` | `["python", "-m", "app"]` | Seed context |

**Note**: The single-stage template intentionally omits non-root USER and HEALTHCHECK to keep it minimal for dev/script use cases. The multi-stage template is the production-recommended default. The validator's advisory rules (DV-BP-002, DV-BP-008) will flag these omissions if the single-stage template is used in a production context.

**Base image selection**: Per research §1, `python:X.Y-slim` is the recommended default (~130MB). Alpine should be avoided unless the project has no C-extension packages — musl libc breaks many wheels and builds are 50x slower. The templates default to `-slim`.

**Template selection heuristic** (simple, extend later):

```python
def select_dockerfile_template(
    file_path: str,
    existing_content: str | None,
    context: dict[str, Any],
) -> str:
    """Select which Dockerfile template to use.

    Priority:
    1. If existing_content is available → use existing content as skeleton (edit mode)
    2. If service_metadata hints at compiled language → multi-stage (Go variant)
    3. If service_metadata hints at Python production → multi-stage (Python wheels variant)
    4. Default → single-stage (interpreted language, simple service)
    """
```

**Location**: `src/startd8/micro_prime/templates/dockerfile.py` (new module).

### FR-DFA-006: DeterministicFileAssembler Dockerfile Rendering

The `DeterministicFileAssembler` SHALL gain a `render_dockerfile()` method:

```python
def render_dockerfile(
    self,
    file_spec: ForwardFileSpec,
    existing_content: str | None = None,
    context: dict[str, Any] | None = None,
) -> str:
    """Render a Dockerfile skeleton.

    Rendering modes:
    1. Edit mode (existing_content provided): Return existing content as-is.
       The existing file IS the skeleton — the LLM modifies it.
    2. Create mode (no existing content): Select and render a template
       based on context hints.

    All output is validated via the Dockerfile structural validator.
    """
```

**Edit mode** (existing file available — like PI-013's loadgenerator/Dockerfile):

- Return the existing file content as the skeleton
- This is the "passthrough" path: the existing Dockerfile is already valid
- The LLM's job is to modify it according to the task description (e.g., update base image, add stages)

**Create mode** (new Dockerfile — no existing content):

- Select a template via `select_dockerfile_template()`
- Render template with variable substitution from context
- Validate output via `validate_dockerfile()`

**Validation**: Both modes SHALL validate the output via `validate_dockerfile()`. If validation fails:

- Edit mode: Log warning, return content anyway (existing file may use newer Docker features)
- Create mode: Log error, return template with unresolved variables as fallback

The assembler's `render_file()` method SHALL NOT be modified — `render_dockerfile()` is a separate method called by the adapter when it detects a Dockerfile target.

### FR-DFA-007: Full-File Splicing for Dockerfiles

Dockerfile splicing operates at the file level, not the element level (implements REQ-MP-362):

```python
def splice_dockerfile(
    skeleton: str,
    generated_content: str,
    file_path: str,
) -> str:
    """Full-file replacement for Dockerfiles.

    Unlike Python splicing (which replaces function body stubs),
    Dockerfile splicing replaces the entire file content.
    The generated_content IS the complete Dockerfile.

    Validation:
    - Validates generated_content via Dockerfile structural validator
    - If validation fails, returns skeleton (safer fallback)
    """
```

**Location**: `src/startd8/micro_prime/splicer.py` (existing module — follows naming and error handling conventions of `splice_body_into_skeleton()`).

**Why full-file replacement**: Dockerfiles have no function bodies to splice into. The Dockerfile directive sequence is the entire unit. There's no meaningful "partial replacement" — you either replace the whole file or you don't.

### FR-DFA-008: Dockerfile Template Registry Integration

The template registry SHALL be extended with Dockerfile templates (implements REQ-MP-352):

```python
DOCKERFILE_TEMPLATES: list[CodeTemplate] = [
    CodeTemplate(
        name="dockerfile_multistage",
        match_fn=_match_multistage,
        render_fn=_render_multistage,
        language="dockerfile",
    ),
    CodeTemplate(
        name="dockerfile_singlestage",
        match_fn=_match_singlestage,
        render_fn=_render_singlestage,
        language="dockerfile",
    ),
]
```

The `CodeTemplate` dataclass SHALL gain an optional `language: str = "python"` field. The `TemplateRegistry` SHALL use language detection to select the appropriate template list.

**Backward compatible**: Existing templates default to `language="python"`.

### FR-DFA-009: Language Field on ForwardFileSpec

`ForwardFileSpec` SHALL gain an optional `language` field (implements REQ-MP-331):

```python
class ForwardFileSpec(BaseModel):
    file: str
    elements: list[ForwardElementSpec] = Field(default_factory=list)
    imports: list[ForwardImportSpec] = Field(default_factory=list)
    dependencies: Optional[ForwardDependencies] = None
    language: Optional[Language] = None  # NEW — typed via lang_detect.Language (R1-F5)
```

**Backward compatible**: Optional field with `None` default. Existing manifests and serialized JSON are unaffected.

**Precedence**: When `language` is set on the ForwardFileSpec, `detect_language()` returns it directly without extension inference. When `None`, extension inference is used.

### FR-DFA-010: Prime Adapter Integration

The `prime_adapter` SHALL be updated to route Dockerfiles through the assembly pipeline:

#### 10a: `_generate_skeletons()` update

```python
def _generate_skeletons(self, manifest, target_files):
    ...
    for file_path in target_files:
        file_spec = manifest.file_specs.get(file_path)
        if file_spec is None:
            continue

        lang = detect_language(file_path)  # or file_spec.language

        if lang == "dockerfile":
            existing = existing_files.get(file_path, "")
            source = assembler.render_dockerfile(
                file_spec, existing_content=existing or None, context=context,
            )
            if source:
                skeletons[file_path] = source
        elif lang == "python":
            # existing path: assembler.render_file(file_spec)
            ...
        else:
            logger.debug("Unsupported language %s for %s", lang, file_path)
```

#### 10b: `_process_target_files()` update

For Dockerfile target files (detected via language), the processing SHALL bypass the element-level engine and instead:

1. Use the skeleton directly as the generation output (edit mode — existing content is already the desired result)
2. OR delegate to the fallback generator for LLM-based modification (create mode or significant changes)

```python
if lang == "dockerfile":
    # Dockerfile: file-level processing, not element-level
    skeleton_content = skeletons.get(file_path, "")
    if skeleton_content:
        # Validate and write
        validation = validate_dockerfile(skeleton_content)
        if validation.valid:
            st.effective_file_count += 1
            # Write skeleton as the generation output
            ...
        else:
            # Validation warnings → still write, log warnings
            ...
    continue  # skip element-level engine
```

#### 10c: Bypass classification

Files where `file_spec is None` AND `detect_language()` returns `"unknown"` SHALL be classified as `bypass_files` (FR-DFA-001), not `escalated_files`.

---

## 7. Non-Functional Requirements

### NFR-DFA-001: Zero LLM Cost for Deterministic Path

The Dockerfile skeleton assembly path (edit mode: existing file passthrough, create mode: template rendering) SHALL make **zero** LLM API calls. All rendering is deterministic string manipulation.

### NFR-DFA-002: No New Dependencies

All new code SHALL use only stdlib and existing SDK imports. No Jinja2 or other template engines — Dockerfile templates are simple `str.format()` or f-string based.

### NFR-DFA-003: Python Regression Safety

All existing Python pipeline tests SHALL continue to pass with zero changes. The Dockerfile path is purely additive — no modifications to existing Python rendering, validation, or splicing logic.

### NFR-DFA-004: Validator Extensibility

The Dockerfile validator SHALL be designed so additional rules can be added incrementally. Each rule has an ID (DV-001, DV-002, ...) and a severity. Rules can be added without modifying existing rule implementations.

### NFR-DFA-005: Performance

Dockerfile validation and template rendering for a single file SHALL complete in < 50ms. This is pure string processing — no I/O, no subprocess calls.

---

## 8. Files Created / Modified

| File | Action | Purpose |
|------|--------|---------|
| `src/startd8/micro_prime/lang_detect.py` | **CREATE** | `detect_language()` function, extension/filename maps (FR-DFA-002) |
| `src/startd8/micro_prime/validators/__init__.py` | **CREATE** | Validators package init |
| `src/startd8/micro_prime/validators/dockerfile.py` | **CREATE** | `validate_dockerfile()`, `DockerfileValidationResult`, known directives (FR-DFA-004) |
| `src/startd8/micro_prime/dockerfile_templates.py` | **CREATE** | Dockerfile templates, `select_dockerfile_template()` (FR-DFA-005) |
| `src/startd8/forward_manifest.py` | MODIFY | Add `language: Optional[str] = None` to `ForwardFileSpec` (FR-DFA-009) |
| `src/startd8/forward_manifest_extractor.py` | MODIFY | Produce ForwardFileSpec for Dockerfiles (FR-DFA-003) |
| `src/startd8/utils/file_assembler.py` | MODIFY | Add `render_dockerfile()` method (FR-DFA-006) |
| `src/startd8/micro_prime/prime_adapter.py` | MODIFY | Escalation conflation fix (FR-DFA-001), Dockerfile routing (FR-DFA-010) |
| `src/startd8/micro_prime/splicer.py` | MODIFY | Add `splice_dockerfile()` function (FR-DFA-007) |
| `src/startd8/micro_prime/models.py` | MODIFY | Add `bypass_files` to `_FileProcessingState` if needed |
| `tests/unit/micro_prime/test_lang_detect.py` | **CREATE** | Language detection tests |
| `tests/unit/micro_prime/test_dockerfile_validator.py` | **CREATE** | Dockerfile validator tests |
| `tests/unit/micro_prime/test_dockerfile_templates.py` | **CREATE** | Dockerfile template tests |
| `tests/unit/micro_prime/test_dockerfile_assembly.py` | **CREATE** | End-to-end assembly tests |
| `tests/unit/test_escalation_conflation.py` | **CREATE** | Escalation conflation fix tests |

**Estimated total**: ~400–500 lines of implementation, ~300–400 lines of tests.

---

## 9. Test Strategy

### 9.1 Unit Tests

| Group | Count | Coverage |
|-------|-------|----------|
| Language detection | 8 | `.py`→python, `.go`→go, `Dockerfile`→dockerfile, `Dockerfile.dev`→dockerfile, `dockerfile`→dockerfile, `.proto`→proto, `.rs`→unknown, ForwardFileSpec.language override |
| Dockerfile validator — valid | 6 | Single FROM, multi-stage, with comments, with parser directive, with ARG before FROM, continuation lines |
| Dockerfile validator — invalid | 5 | No FROM, empty, unknown directives, blank-only, only comments |
| Dockerfile validator — edge cases | 4 | Case-insensitive directives, parser directive after blank line, mixed tabs/spaces, very long RUN chains |
| Dockerfile validator — best practice advisories | 6 | No USER → DV-BP-002, `:latest` tag → DV-BP-001, ADD usage → DV-BP-003, shell form CMD → DV-BP-004, source before deps → DV-BP-005, split apt-get → DV-BP-006 |
| Dockerfile templates — multi-stage | 4 | Go defaults, Python wheels defaults, custom variables from context, validates via validator + all DV-BP rules pass |
| Dockerfile templates — single-stage | 3 | Default variables, custom variables, validates via validator |
| Template selection | 4 | Edit mode (existing content), compiled language → multi-stage, interpreted → single-stage, default |
| Assembler render_dockerfile | 4 | Edit mode passthrough, create mode template, validation failure handling, no existing + no context |
| Full-file splicing | 3 | Valid replacement, invalid replacement → fallback to skeleton, empty generated content |
| Escalation conflation | 5 | bypass_files always delegate, escalated_files respect flag, mixed bypass+escalated, no fallback available, all files bypass |
| Python regression | 3 | Existing render_file() unchanged, existing skeleton generation unchanged, existing escalation behavior for Python files |

**Total: ~55 tests**

### 9.2 Integration Tests

| Test | Description |
|------|-------------|
| Dockerfile through full pipeline | ForwardManifestExtractor → DeterministicFileAssembler → prime_adapter → GenerationResult.success=True |
| Edit mode end-to-end | Existing Dockerfile + task description → skeleton = existing content → success |
| Create mode end-to-end | No existing Dockerfile + context hints → template selection → validated output |
| Mixed Python + Dockerfile | Feature with both `.py` and `Dockerfile` targets → both processed correctly |

### 9.3 Regression Validation

- Run the existing test suite (`pytest tests/unit/`) — all must pass
- Specifically verify: `test_file_assembler.py`, `test_prime_adapter.py`, `test_forward_manifest_extractor.py`

---

## 10. Open Questions

### Q1: Should edit-mode Dockerfiles go through the LLM at all?

For PI-013, the existing Dockerfile is 64 lines and already well-structured. The task description asks for specific changes (update base image, add stages, etc.). Two options:

**(a) Passthrough-only (no LLM)**: Return existing content as the generation output. Changes are deferred to a human or future LLM pass. Simplest, zero cost, but doesn't actually modify the file.

**(b) File-level LLM generation**: Send the existing content + task description to the fallback generator (or Ollama via `file_ollama_whole`). The LLM produces a modified Dockerfile. More useful, but adds LLM cost.

**Recommendation**: Start with (a) for the deterministic assembly path. The escalation conflation fix (FR-DFA-001) already enables (b) via the fallback generator for files that need LLM modification. The two paths coexist: deterministic assembly for simple cases, cloud fallback for complex modifications.

### Q2: Template variable resolution from seed context

The Dockerfile templates use variables like `{builder_image}`, `{port}`, etc. Where do these values come from?

**Options**:

- (a) `service_metadata` from the enriched seed context (already available in PI-013's seed)
- (b) Hardcoded defaults per detected language
- (c) Extracted from existing Dockerfile content (if available)

**Recommendation**: Start with (b) hardcoded defaults. Enhance to (a) seed context extraction in a follow-up. Option (c) is essentially edit-mode passthrough.

### Q3: Validator strictness level

Should unknown Dockerfile directives be errors or warnings?

**Recommendation**: Warnings. Docker evolves and adds new directives (e.g., `HEALTHCHECK` was added in Docker 1.12). Being too strict would reject valid Dockerfiles that use newer features. The validator's job is to catch obviously broken content, not enforce a specific Docker version.

---

## 11. Cross-References

| Document | Relationship |
|----------|-------------|
| [docker-file-assembly-via-python.md](../scaffold/docker-file-assembly-via-python.md) | Dockerfile best practices research — Gold Standard template, base image selection, security, layer ordering |
| [REQ-MP-3xx_POLYGLOT_TEMPLATE_REGISTRY.md](REQ-MP-3xx_POLYGLOT_TEMPLATE_REGISTRY.md) | Parent requirements — this doc implements Layers 1 (partial), 2, 4, 5 (partial) |
| [DETERMINISTIC_FILE_ASSEMBLY_REQUIREMENTS.md](../scaffold/DETERMINISTIC_FILE_ASSEMBLY_REQUIREMENTS.md) | Python-specific assembly requirements — pattern reference for Dockerfile extension |
| [MOTTAINAI_PRE_ASSEMBLY_REQUIREMENTS.md](../scaffold/MOTTAINAI_PRE_ASSEMBLY_REQUIREMENTS.md) | Pre-assembly prompt changes — skeleton_fill mode may apply to Dockerfile edit mode |
| `src/startd8/micro_prime/prime_adapter.py` | Primary integration target — escalation fix + Dockerfile routing |
| `src/startd8/utils/file_assembler.py` | Assembly extension target — render_dockerfile() method |
| `src/startd8/forward_manifest_extractor.py` | Extraction extension target — Dockerfile ForwardFileSpec production |
| `src/startd8/forward_manifest.py` | Model extension target — ForwardFileSpec.language field |
| PI-013 run-034 output | `online-boutique-demo/.cap-dev-pipe/pipeline-output/online-boutique/run-034-*/` — test case |
| SDK Lessons: Leg 13 #27 | Line-anchored Dockerfile directive detection |
| SDK Lessons: Leg 13 #44 | Bare top-level import false positive in AST validators — analogous guard needed |

---

## Appendix A: PI-013 Test Case

The loadgenerator Dockerfile from online-boutique serves as the primary validation target:

```dockerfile
# syntax=docker/dockerfile:1

##############################################
# Stage 1: builder — install Python dependencies
##############################################
FROM --platform=$BUILDPLATFORM python:3.14.2-alpine AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /loadgen

COPY requirements.txt .

RUN pip install --prefix="/install" -r requirements.txt

##############################################
# Stage 2: Final image — minimal runtime layer
##############################################
FROM python:3.14.2-alpine

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV GEVENT_SUPPORT=True

COPY --from=builder /install /usr/local

WORKDIR /loadgen

COPY locustfile.py .

ENTRYPOINT locust --host="http://${FRONTEND_ADDR}" --headless -u "${USERS:-10}" -r "${RATE:-1}" 2>&1
```

**Characteristics**:

- Multi-stage build (2 FROM directives)
- Parser directive (`# syntax=docker/dockerfile:1`)
- Platform argument (`--platform=$BUILDPLATFORM`)
- Environment variable expansion in ENTRYPOINT
- Section comments (not directives)

The validator MUST accept this file as valid. The assembler in edit mode MUST return it as-is.

---

## Appendix B: Areas Substantially Addressed

*(Updated per CRP convergent review rounds)*

| Area | Suggestions Addressed | Status |
|------|----------------------|--------|
| Architecture | 1 / 2 | ⚠️ Partial — R1-F5 applied (Language Literal type) |
| Interfaces | 1 / 2 | ⚠️ Partial — R1-F4 applied (splice location) |
| Data | 3 / 3 | ✅ Addressed — R1-F1 (ENV template vars), R1-F2 (file path), R1-F3 (healthcheck) |
| Risks | 0 / 2 | ❌ Open |
| Validation | 0 / 2 | ❌ Open |
| Ops | 0 / 2 | ❌ Open |
| Security | 1 / 2 | ⚠️ Partial — R1-F6 applied (build_deps_block empty default) |

---

## Appendix C: Review Suggestions

### Round 1 (R1)

**R1-F1 (Data, high): Multi-stage template hardcodes Python-specific ENV in template string**

The multi-stage template in FR-DFA-005 includes `PYTHONDONTWRITEBYTECODE=1` and `PYTHONUNBUFFERED=1` as literal text in both builder and runtime stages. For Go builds these are meaningless. The plan (§5.2) says language-specific variants are stored in `_MULTISTAGE_DEFAULTS` dicts, but the template *string itself* bakes in Python ENV vars rather than using a `{env_block}` variable.

**Recommendation**: Replace the hardcoded `ENV PYTHONDONTWRITEBYTECODE=1 \ PYTHONUNBUFFERED=1` blocks with a `{builder_env_block}` and `{runtime_env_block}` template variable. Add these to the variable defaults table with Python and Go values.

---

**R1-F2 (Data, medium): §8 file path inconsistent with plan decision**

§8 "Files Created / Modified" lists `src/startd8/micro_prime/templates/dockerfile.py` for FR-DFA-005/FR-DFA-008. But the implementation plan (§5.1) chose option (b): `src/startd8/micro_prime/dockerfile_templates.py` as a peer module. The requirements doc should match.

**Recommendation**: Update §8 to reference `src/startd8/micro_prime/dockerfile_templates.py`.

---

**R1-F3 (Data, high): HEALTHCHECK uses `curl` but `python:X.Y-slim` doesn't ship curl**

The multi-stage template (FR-DFA-005) specifies `curl -f http://localhost:{port}/health || exit 1` as the Python HEALTHCHECK. However, `python:X.Y-slim` does not include `curl` by default. The Go variant uses `wget`, which is available in Alpine but not in slim. Neither default is reliable without an explicit install step.

**Recommendation**: Use a Python stdlib healthcheck for Python images: `python -c "import urllib.request; urllib.request.urlopen('http://localhost:{port}/health')"`. For Go/Alpine, `wget -qO- ...` is correct. Add `healthcheck_command` to the language-specific defaults table with these values.

---

**R1-F4 (Interfaces, low): FR-DFA-007 splice location is ambiguous**

FR-DFA-007 says the function location is "Added to `splicer.py` ... or as a peer function in the new `validators/dockerfile.py` module." The plan chose splicer.py (§6.2). The requirements should state a single location.

**Recommendation**: Update FR-DFA-007 to specify `splicer.py` as the definitive location, consistent with the plan.

---

**R1-F5 (Architecture, high): `ForwardFileSpec.language` field creates an implicit contract that is not formally specified**

FR-DFA-009 adds `language: Optional[str] = None` to `ForwardFileSpec`. The field values (`"python"`, `"dockerfile"`, `"go"`, `"unknown"`) are defined in `lang_detect.py` as string literals. However, there is no `Language` enum, no `__all__` export, and no schema definition that consumer modules (prime_adapter, file_assembler, splicer, validators) can depend on for type safety.

The guide (Lens C) flags this specifically: "Is `lang_detect.py` the right abstraction? Would a `Language` enum be better than string returns?" With string literals, typos (`"Docker file"`, `"Dockerfile"`) won't be caught by type checkers — they'll silently fall through to the `else` branch in `_generate_skeletons()` and produce a file-level bypass.

**Recommendation**: Define a `Language` string enum (or `Literal` type) in `lang_detect.py`:

```python
from typing import Literal

Language = Literal["python", "dockerfile", "go", "proto", "unknown"]

def detect_language(file_path: str, explicit_lang: Optional[str] = None) -> Language:
    ...
```

Update LR-DFA-009 and FR-DFA-002 to reference `Language` as the type for `ForwardFileSpec.language` and the return type of `detect_language()`. Update the `_EXTENSION_TO_LANG` and `_FILENAME_TO_LANG` dicts to be typed `dict[str, Language]`. This makes missing language values a mypy error rather than a runtime miss.

---

**R1-F6 (Security, medium): Template `build_essential` inclusion in Python multi-stage creates unnecessary attack surface**

The multi-stage template (FR-DFA-005) includes `build-essential` (which pulls in gcc, g++, make, and many dev libraries) as a default in the builder stage. The gold-standard research (§4) notes that `build-essential` is for C-extension compilation — but many Python services have zero C-extension dependencies. For those services, the template's default unnecessarily installs a 200MB+ build toolchain.

Worse, if future refactoring accidentally leaks the builder stage into the final image (e.g., using `FROM builder` in multi-stage rather than copying artifacts), the attack surface triples.

**Recommendation**: Change `build_deps_block` defaults to use a minimal `RUN pip install --upgrade pip` for Python (no apt-get), and add `build-essential` only as an explicit opt-in:

| Variable | Default (Python, no C-exts) | Opt-in (Python, with C-exts) |
|---|---|---|
| `build_deps_block` | *(empty — pip handles it)* | `RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*` |

The `select_dockerfile_template()` heuristic should inspect `requirements.txt` content (if available in context) for known C-extension packages (numpy, scipy, psycopg2, etc.) to determine whether to include `build-essential`. Document this decision clearly in FR-DFA-005 so implementers don't default to the heavier template.
