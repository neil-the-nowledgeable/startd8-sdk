# Quality Improvement Plan — Kaizen Run-016 Findings

**Date:** 2026-03-09
**Source:** `KAIZEN_INVESTIGATION_RUN016_ONLINE_BOUTIQUE.md`
**Scope:** 5 lessons (L1–L5) addressing systemic quality gaps in code generation pipeline
**Goal:** Reduce post-generation repair rate from 100% to <20% for Python files,
eliminate semantic bugs surviving into final output
**Design Principle Review:** Reviewed against [Ichigo Ichie](../../design-princples/ICHIGO_ICHIE_DESIGN_PRINCIPLE.md) —
items marked with `[ICHIGO ICHIE VIOLATION]` must be reworked before implementation.

---

## Overview

Run-016 revealed that every generated Python file required import repair, semantic
bugs (hallucinated APIs, stubs) survived repair + review, and the element registry
delivered near-zero value. This plan addresses 5 root causes in priority order.

| # | Lesson | Files Modified | Estimated Tests |
|---|--------|---------------|-----------------|
| L1 | Import tracking in code generator | 3 | 8-12 |
| L3 | Per-service dependency scoping | 2 | 5-8 |
| L5 | Framework import templates | 3 | 6-10 |
| L2 | Semantic validation post-repair | 2 | 10-15 |
| L4 | Structured constraint checking in review | 3 | 6-8 |

---

## L1: Import Tracking in Code Generator

**Problem:** 100% of generated Python files needed `import_completion` repair.
The LLM produces function/class bodies referencing symbols it never imported.
One file (logger.py) required two passes because `import_completion` is
non-idempotent.

**Root Cause:** The draft system prompt says "stdlib-only imports unless listed"
but doesn't tell the LLM which packages are available or required. The spec
template has no import specification section.

### Implementation

#### Step 1: Add `available_imports` section to spec template

**File:** `src/startd8/implementation_engine/prompts/contractor_prompts.yaml`

Add a new spec section between `technical_approach` and `code_structure`:

```yaml
available_imports: |
  ## Available Imports

  The following packages are installed and available for import:

  {available_packages}

  Use ONLY these packages plus Python stdlib. Every non-stdlib symbol you
  reference MUST have a corresponding import statement at the top of the file.
  Do NOT import packages not listed above.
```

#### Step 2: Populate `available_packages` from task dependencies

**File:** `src/startd8/implementation_engine/spec_builder.py`

In `build_spec_prompt()`, extract `runtime_dependencies` from the task context
and format them into the `available_imports` section:

```python
def _build_available_imports_section(self, context: dict) -> str:
    """Build the available imports section from task dependencies."""
    deps = context.get("runtime_dependencies", [])
    if not deps:
        return ""
    # Map package names to importable module names
    package_lines = []
    for dep in sorted(deps):
        # Strip version pins: "grpcio==1.76.0" → "grpcio"
        pkg = dep.split("==")[0].split(">=")[0].split("<=")[0].strip()
        package_lines.append(f"- {pkg}")
    return "\n".join(package_lines)
```

Add this section at P1 priority (same as `critical_parameters`) in the budget
ordering so it survives truncation.

#### Step 3: Add import completeness instruction to draft system prompt

**File:** `src/startd8/implementation_engine/drafter.py`

Append to all 4 draft system prompts (`draft_system_create`, `draft_system_edit`,
`draft_system_search_replace`, `draft_system_skeleton_fill`):

```
CRITICAL: Every file you produce MUST include ALL import statements at the
top. Do not assume imports exist elsewhere. Include stdlib, third-party,
and local imports. Missing imports are the #1 cause of generation failure.
```

#### Step 4: Tests

**File:** `tests/unit/implementation_engine/test_spec_builder_imports.py` (new)

- `test_available_imports_section_populated` — deps list → formatted section
- `test_available_imports_section_empty` — no deps → empty section
- `test_version_pin_stripped` — `grpcio==1.76.0` → `grpcio`
- `test_available_imports_survives_budget_truncation` — P1 priority preserved
- `test_draft_system_prompt_includes_import_instruction` — all 4 modes

**File:** `tests/unit/implementation_engine/test_drafter_imports.py` (new)

- `test_create_mode_has_import_instruction` — instruction present
- `test_edit_mode_has_import_instruction` — instruction present
- `test_skeleton_fill_has_import_instruction` — instruction present

---

## L3: Per-Service Dependency Scoping

**Problem:** All 4 requirements.in files generated identical 19-dependency lists.
emailservice got `locust`, loadgenerator got `langchain`. The LLM used the shared
plan context to populate each service's dependencies.

**Root Cause:** `SeedTask.runtime_dependencies` is a single list per task, but
the enriched seed doesn't scope dependencies to individual target files. When
the plan mentions dependencies globally, each task inherits the full set.

### Implementation

#### Step 1: Add per-file dependency inference during seed enrichment

**File:** `src/startd8/contractors/context_seed/shared.py`

Add a helper that scopes dependencies based on which packages a file actually
imports:

```python
def scope_dependencies_to_file(
    file_path: str,
    file_content: str,
    all_dependencies: list[str],
) -> list[str]:
    """Return only the dependencies that ``file_path`` actually imports.

    Parses ``file_content`` with ``ast`` to extract top-level import names,
    then intersects with ``all_dependencies`` (stripping version pins).
    Falls back to ``all_dependencies`` if parsing fails.
    """
```

This function:
1. AST-parses `file_content` to extract all imported module names
2. Builds a set of top-level package names (e.g., `grpc` from `import grpc`)
3. Maps known package-name → PyPI-name aliases (`grpcio` → `grpc`, `pillow` → `PIL`)
4. Returns the intersection of imported packages and `all_dependencies`
5. Falls back to the full list if AST parsing fails

#### Step 2: Apply scoping during spec construction for requirements files

**File:** `src/startd8/implementation_engine/spec_builder.py`

When building specs for requirements files (detected via `target_files` ending
in `requirements.in` or `requirements.txt`), inject a constraint:

```python
if any(tf.endswith(("requirements.in", "requirements.txt")) for tf in target_files):
    # Scope deps to co-located Python files
    scoped_deps = self._scope_deps_for_requirements_file(context)
    context["scoped_dependencies"] = scoped_deps
```

The scoped list is passed to the spec template as a constraint:
```
Only include packages that are actually imported by Python files in this
service directory. Do NOT include packages used by other services.
The following packages are confirmed imports for this service:
{scoped_dependencies}
```

#### Step 3: Package-name alias map

**File:** `src/startd8/implementation_engine/spec_builder.py`

Add a constant mapping PyPI names to importable names:

```python
_PYPI_TO_IMPORT: dict[str, str] = {
    "grpcio": "grpc",
    "grpcio-health-checking": "grpc_health",
    "pillow": "PIL",
    "python-json-logger": "pythonjsonlogger",
    "google-api-core": "google.api_core",
    "google-cloud-secret-manager": "google.cloud.secretmanager",
    "opentelemetry-distro": "opentelemetry",
    "opentelemetry-exporter-otlp-proto-grpc": "opentelemetry.exporter.otlp",
    "opentelemetry-instrumentation-grpc": "opentelemetry.instrumentation.grpc",
    "python-dateutil": "dateutil",
    "pyyaml": "yaml",
    "beautifulsoup4": "bs4",
}
```

#### Step 4: Tests

**File:** `tests/unit/implementation_engine/test_dependency_scoping.py` (new)

- `test_scope_deps_basic` — file importing `grpc` and `flask` → only `grpcio`, `flask` returned
- `test_scope_deps_alias_mapping` — `import PIL` → `pillow` included
- `test_scope_deps_no_imports` — empty file → empty list
- `test_scope_deps_ast_failure_falls_back` — syntax error → full list returned
- `test_scope_deps_nested_import` — `from google.cloud.secretmanager import X` → `google-cloud-secret-manager`
- `test_requirements_file_gets_scoped_constraint` — spec builder injects scoped list
- `test_non_requirements_file_unaffected` — Python files don't get scoped constraint

---

## L5: Framework Import Templates

**Problem:** Framework-specific code (gRPC, Locust, OTel) has 3-6x higher lint
error density (12-19 errors vs 3 for simple utilities). The code generator
doesn't know canonical import patterns for these frameworks.

**Root Cause:** No framework detection in spec/draft construction. The LLM must
independently discover `from locust import FastHttpUser, TaskSet, between` or
`from grpc_health.v1 import health_pb2, health_pb2_grpc` without guidance.

### Implementation

#### Step 1: Framework import template registry

**File:** `src/startd8/implementation_engine/framework_imports.py` (new)

```python
"""Framework-specific import templates for code generation.

When a task targets a known framework domain, the corresponding import
block is injected into the spec as a mandatory preamble, reducing
post-generation import repair.
"""

FRAMEWORK_IMPORTS: dict[str, dict] = {
    "grpc": {
        "detect": ["grpc", "grpcio", "proto", "protobuf", "gRPC"],
        "imports": [
            "import grpc",
            "from concurrent import futures",
            "import demo_pb2",
            "import demo_pb2_grpc",
            "from grpc_health.v1 import health_pb2",
            "from grpc_health.v1 import health_pb2_grpc",
        ],
        "conditional": {
            "opentelemetry": [
                "from opentelemetry import trace",
                "from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer",
            ],
        },
    },
    "locust": {
        "detect": ["locust", "load test", "load generator", "traffic simulation"],
        "imports": [
            "from locust import FastHttpUser, TaskSet, between",
        ],
        "conditional": {
            "faker": ["from faker import Faker"],
        },
    },
    "flask": {
        "detect": ["flask", "web server", "REST API", "HTTP endpoint"],
        "imports": [
            "from flask import Flask, request, jsonify",
        ],
        "conditional": {},
    },
    "opentelemetry": {
        "detect": ["opentelemetry", "OTel", "tracing", "instrumentation"],
        "imports": [
            "from opentelemetry import trace",
            "from opentelemetry.sdk.trace import TracerProvider",
            "from opentelemetry.sdk.trace.export import BatchSpanProcessor",
        ],
        "conditional": {},
    },
}


def detect_frameworks(
    task_description: str,
    target_files: list[str],
    dependencies: list[str],
) -> list[str]:
    """Return framework keys detected from task metadata."""


def get_import_preamble(frameworks: list[str]) -> str:
    """Return formatted import block for detected frameworks."""
```

#### Step 2: Inject framework imports into spec

**File:** `src/startd8/implementation_engine/spec_builder.py`

In `build_spec_prompt()`, after building the available imports section (L1),
detect frameworks and append canonical imports:

```python
from startd8.implementation_engine.framework_imports import (
    detect_frameworks,
    get_import_preamble,
)

frameworks = detect_frameworks(
    task_description=context.get("description", ""),
    target_files=context.get("target_files", []),
    dependencies=context.get("runtime_dependencies", []),
)
if frameworks:
    preamble = get_import_preamble(frameworks)
    # Append to available_imports section
```

#### Step 3: Framework detection from enrichment

Detection sources (checked in order):
1. `task.runtime_dependencies` — if `grpcio` in deps → `grpc` framework
2. `task.description` — keyword match against `detect` lists
3. `target_files` — filename patterns (e.g., `*_server.py` + `grpcio` in deps → gRPC)

#### Step 4: Tests

**File:** `tests/unit/implementation_engine/test_framework_imports.py` (new)

- `test_detect_grpc_from_dependencies` — `grpcio` in deps → `grpc` detected
- `test_detect_locust_from_description` — "Locust traffic simulation" → `locust` detected
- `test_detect_flask_from_dependencies` — `flask` in deps → `flask` detected
- `test_detect_multiple_frameworks` — gRPC + OTel both detected
- `test_no_framework_detected` — plain utility → empty list
- `test_import_preamble_grpc` — correct import block generated
- `test_import_preamble_locust` — correct import block generated
- `test_conditional_imports_included` — OTel in deps + gRPC detected → OTel imports added
- `test_preamble_injected_into_spec` — integration test with spec builder

---

## L2: Semantic Validation Post-Repair

**Problem:** 6 semantic bugs survived repair + review: hallucinated APIs
(`google.cloud.vectordb.VectorStoreClient`), wrong imports (`import jsonlogger`
vs `from pythonjsonlogger import jsonlogger`), stub bodies (`pass`), and
duplicate definitions. The repair pipeline validates syntax and lint but not
semantic correctness.

**Root Cause:** `check_imports()` in checkpoint.py runs `import module` in a
subprocess but only catches `ImportError`. It doesn't validate that specific
symbols exist within imported modules. There is no stub detection.

### Implementation

#### Step 1: Add stub detection to checkpoint

**File:** `src/startd8/contractors/checkpoint.py`

Add `check_stubs()` method to `IntegrationCheckpoint`:

```python
_STUB_PATTERNS: tuple[str, ...] = (
    "raise NotImplementedError",
    "pass",
    "...",
)

def check_stubs(
    self,
    files: list[Path],
    *,
    max_stub_ratio: float = 0.3,
) -> CheckpointResult:
    """Detect files where stub bodies exceed *max_stub_ratio* of functions.

    A function body is considered a stub if it contains only ``pass``,
    ``...``, or ``raise NotImplementedError``.  Files exceeding the
    threshold are reported as warnings (not errors) because partial
    implementations may be intentional during incremental generation.
    """
```

Algorithm:
1. AST-parse each file
2. Walk `ast.FunctionDef` and `ast.AsyncFunctionDef` nodes
3. Check if body is a single `Pass`, `Expr(Constant(...))` (Ellipsis), or
   `Raise(NotImplementedError)`
4. Compute stub ratio = stub_count / total_function_count
5. Warn if ratio > `max_stub_ratio`

#### Step 2: Add duplicate definition detection

**File:** `src/startd8/contractors/checkpoint.py`

Add `check_duplicates()` method:

```python
def check_duplicates(self, files: list[Path]) -> CheckpointResult:
    """Detect duplicate class or function definitions in the same file.

    Two definitions are duplicates if they share the same name at the
    same scope level.  This catches the pattern where the LLM generates
    a class, then redefines it inside a function (as seen in logger.py
    with two ``CustomJsonFormatter`` definitions).
    """
```

Algorithm:
1. AST-parse each file
2. Collect all top-level `ClassDef` and `FunctionDef` names
3. Report duplicates as warnings

#### Step 3: Add import resolution validation

**File:** `src/startd8/contractors/checkpoint.py`

Enhance `check_imports()` to validate that imported symbols actually exist:

```python
def check_import_symbols(
    self,
    files: list[Path],
    *,
    known_local_modules: set[str] | None = None,
) -> CheckpointResult:
    """Validate that ``from X import Y`` statements resolve to real symbols.

    Skips local/proto-generated modules (listed in *known_local_modules*).
    Reports as warnings (not errors) because some modules are only
    available at runtime inside a container.
    """
```

Algorithm:
1. AST-parse each file, extract `ImportFrom` nodes
2. For each `from X import Y`, try `importlib.import_module(X)` then `getattr(module, Y)`
3. Skip modules in `known_local_modules` (proto-generated, local packages)
4. Report missing symbols as warnings

#### Step 4: Wire new checks into `run_all_checkpoints()`

**File:** `src/startd8/contractors/checkpoint.py`

Add the new checks after `check_lint()` but before `check_tests()`:

```python
def run_all_checkpoints(self, files, **kwargs):
    results = []
    results.append(self.check_syntax(files))
    results.append(self.check_imports(files))
    results.append(self.check_lint(files, **kwargs))
    # New semantic checks
    results.append(self.check_stubs(files))
    results.append(self.check_duplicates(files))
    # check_import_symbols is opt-in (requires known_local_modules)
    if kwargs.get("known_local_modules"):
        results.append(self.check_import_symbols(
            files,
            known_local_modules=kwargs["known_local_modules"],
        ))
    results.append(self.check_tests(files))
    return results
```

#### Step 5: Tests

**File:** `tests/unit/contractors/test_checkpoint_semantic.py` (new)

- `test_stub_detection_pass_body` — `def f(): pass` detected as stub
- `test_stub_detection_ellipsis` — `def f(): ...` detected as stub
- `test_stub_detection_not_implemented` — `def f(): raise NotImplementedError` detected
- `test_stub_ratio_below_threshold` — 1 stub in 10 functions → PASSED
- `test_stub_ratio_above_threshold` — 5 stubs in 6 functions → WARNING
- `test_stub_real_implementation_not_flagged` — `def f(): return 42` not flagged
- `test_duplicate_class_detected` — two `class Foo` at top level → WARNING
- `test_duplicate_function_detected` — two `def bar` at top level → WARNING
- `test_no_duplicates_different_scope` — top-level + nested → not flagged
- `test_import_symbol_valid` — `from os.path import join` → PASSED
- `test_import_symbol_invalid` — `from os.path import nonexistent` → WARNING
- `test_import_symbol_skips_local` — `from demo_pb2 import X` skipped
- `test_semantic_checks_in_run_all` — new checks called in sequence
- `test_semantic_checks_dont_block` — warnings don't fail the checkpoint

---

## L4: Structured Constraint Checking in Review

**Problem:** The review phase scores implementations 88-100/100 while accepting
violations of explicit spec constraints. "No pip-compile header comments" was
violated (comments added), "plain HealthCheck class" was violated (inheritance
added). Review evaluates functional correctness but not constraint adherence.

**Root Cause:** `ReviewPhaseHandler._build_review_prompt()` passes
`task.prompt_constraints` as prose text. The reviewer treats constraints as
advisory, not mandatory. No structured checklist is extracted from the spec.

### Implementation

#### Step 1: Extract MUST/MUST-NOT assertions from spec

**File:** `src/startd8/implementation_engine/spec_builder.py`

Add a method that extracts structured constraints during spec construction and
stores them for later use by the review phase:

```python
def extract_spec_constraints(self, spec_text: str) -> list[dict]:
    """Extract MUST and MUST NOT assertions from a spec document.

    Scans for patterns like:
    - "MUST ..." / "must ..."
    - "MUST NOT ..." / "Do NOT ..."
    - "Required: ..."
    - "Constraint: ..."

    Returns a list of dicts:
    ``[{"type": "MUST"|"MUST_NOT", "text": "...", "section": "..."}]``
    """
```

Store these in the task context under `spec_constraints` so the review phase
can access them.

#### Step 2: Add constraint checklist to review prompt

**File:** `src/startd8/contractors/context_seed/core.py`

In `ReviewPhaseHandler._build_review_prompt()`, add a new enrichment section
at P0 priority (above forward contracts):

```python
def _build_constraint_checklist_section(self, task) -> str:
    """Build a structured constraint checklist for the reviewer.

    Each constraint is presented as a numbered assertion the reviewer
    must explicitly verify (PASS/FAIL) in their response.
    """
    constraints = task.context.get("spec_constraints", [])
    if not constraints:
        return ""
    lines = ["## Constraint Checklist (MANDATORY)\n"]
    lines.append("You MUST evaluate each constraint below and report")
    lines.append("PASS or FAIL for each. A FAIL on any constraint caps")
    lines.append("the maximum score at 85.\n")
    for i, c in enumerate(constraints, 1):
        lines.append(f"{i}. [{c['type']}] {c['text']}")
    return "\n".join(lines)
```

#### Step 3: Parse constraint verdicts from review response

**File:** `src/startd8/contractors/context_seed/core.py`

In `ReviewPhaseHandler._parse_review_response()`, extract constraint verdicts
from the review output:

```python
def _extract_constraint_verdicts(
    self, review_text: str, constraint_count: int,
) -> list[dict]:
    """Extract PASS/FAIL verdicts for each numbered constraint."""
```

If any constraint is FAIL, cap the review score at 85 and append a
`quality_failed` flag to the review result.

#### Step 4: Tests

**File:** `tests/unit/contractors/test_review_constraints.py` (new)

- `test_extract_must_constraint` — "MUST include X" → `{"type": "MUST", "text": "include X"}`
- `test_extract_must_not_constraint` — "Do NOT add comments" → `{"type": "MUST_NOT", "text": "add comments"}`
- `test_constraint_checklist_in_prompt` — constraints appear in review prompt
- `test_constraint_fail_caps_score` — FAIL on constraint → max 85
- `test_constraint_all_pass_no_cap` — all PASS → score uncapped
- `test_no_constraints_no_checklist` — empty constraints → section omitted

---

## Execution Order and Dependencies

```
L1 (Import tracking) ──────────────┐
                                    ├── L5 (Framework templates) depends on L1's
L3 (Dependency scoping) ───────────┘   available_imports infrastructure

L2 (Semantic validation) ── independent, can run in parallel with L1/L3

L4 (Constraint checking) ── depends on L1's spec_builder changes for
                             constraint extraction; implement last
```

### Recommended Implementation Sequence

| Phase | Lessons | Rationale |
|-------|---------|-----------|
| **Phase 1** | L1 + L3 | Foundation: imports and dependency scoping. L5 builds on L1's infrastructure. |
| **Phase 2** | L5 | Framework templates use L1's `available_imports` section as injection point. |
| **Phase 3** | L2 | Semantic validation is independent. Can be tested against existing run outputs. |
| **Phase 4** | L4 | Constraint checking needs spec_builder changes from L1. Lowest priority. |

### Validation

After each phase, re-run the online-boutique plan against the modified pipeline
and compare:

| Metric | Current (Run-016) | Target |
|--------|-------------------|--------|
| Files needing import repair | 100% (5/5 .py) | <20% |
| Semantic bugs in output | 6 | 0-1 |
| Cross-contaminated deps | 4/4 requirements files | 0 |
| Framework lint error density | 12-19 errors | <5 |
| Stubs reported as PASS | 1 (email_client.py) | 0 |
| Weighted quality score | 83.2/100 | >90/100 |

---
---

## Addendum: Plan Refinements

**Date:** 2026-03-09
**Source:** Code-level review of implementation touchpoints

After reviewing the actual codebase (`spec_builder.py`, `drafter.py`,
`import_completion.py`, `code_extraction.py`, `checkpoint.py`,
`prime_adapter.py`, `domain_checklist.py`, `context_seed/core.py`),
8 refinements are identified. These supersede or strengthen the
original L1–L5 steps and add two new lessons (L6, L7).

---

### Refinement 1: L1 — Add a deterministic import audit pass

**Problem with original plan:** L1 adds an `available_imports` spec section
and "include all imports" draft instruction. This is prompt engineering —
probabilistic by nature. The existing draft prompt already says "stdlib-only
imports unless listed" yet 100% of files still had missing imports. Adding
another instruction is unlikely to achieve <20% repair rate.

**Refinement:** Add a **deterministic import audit pass** between code
extraction and repair. After `extract_code_from_response()` returns code,
AST-parse it, collect all referenced names, diff against actual import
statements, and inject the missing ones before the file ever reaches the
repair pipeline.

**File:** `src/startd8/utils/code_extraction.py`

```python
def audit_and_inject_imports(
    code: str,
    available_packages: list[str],
    *,
    package_alias_map: dict[str, str] | None = None,
) -> tuple[str, list[str]]:
    """Deterministic import audit for extracted code.

    AST-parses *code*, identifies all unresolved names, matches them
    against *available_packages* (using *package_alias_map* for
    PyPI-name → import-name translation), and injects missing import
    statements after the last existing import.

    Returns ``(patched_code, injected_imports)`` so callers can log
    what was added.

    This runs BEFORE the repair pipeline, handling the common case
    deterministically.  The repair pipeline remains as a safety net
    for edge cases this pass misses (e.g. dynamic attribute access,
    conditional imports).
    """
```

Algorithm:
1. AST-parse `code` to build sets of (a) imported names, (b) all referenced
   names (from `ast.Name`, `ast.Attribute` nodes)
2. Compute `unresolved = referenced - imported - builtins`
3. For each unresolved name, check if it matches a known package or alias
4. Generate `import X` or `from X import Y` statements
5. Insert after the last existing import line (using `_find_import_insertion_line`
   logic already in `import_completion.py`)

**Integration point:** Call from `LeadContractorWorkflow` and
`MicroPrimeCodeGenerator` after code extraction, before file write.

**Why this is better:** Deterministic (no LLM involved), idempotent (safe to
run multiple times), and eliminates the multi-pass convergence problem
(logger.py needed 2 repair passes because `import_completion` is not
idempotent).

The original L1 prompt changes (available_imports section, draft instruction)
are still worth doing — they reduce the number of missing imports the audit
pass must fix. But the audit pass is the primary mechanism.

**Tests:** Add to `tests/unit/test_code_extraction.py`:

- `test_audit_injects_missing_stdlib` — `os.path.join` used without `import os`
- `test_audit_injects_missing_third_party` — `grpc.server()` used → `import grpc`
- `test_audit_idempotent` — running twice produces same output
- `test_audit_preserves_existing_imports` — doesn't duplicate existing imports
- `test_audit_uses_alias_map` — `PIL.Image` → `from PIL import Image` via alias

---

### Refinement 2: L2 — Use existing `STUB_SENTINEL` infrastructure

**Problem with original plan:** L2 proposes AST-based stub detection by
scanning for `pass`/`...`/`raise NotImplementedError` bodies. But the codebase
already has `STUB_SENTINEL = "STARTD8_AUTO_STUB"` (in `code_extraction.py`)
which is embedded in every auto-generated stub. The splicer checks for it
(`splicer.py:469`). The context seed checks for it (`core.py:931`). The lead
contractor counts stubbed files (`lead_contractor.py:405-409`).

**Refinement:** Distinguish two stub types with different failure modes:

| Type | Detection | Severity | Example |
|------|-----------|----------|---------|
| **Pipeline stub** | Contains `STUB_SENTINEL` | WARNING (expected for downstream tasks) | `# STARTD8_AUTO_STUB\n"""module — stub."""` |
| **LLM stub** | Function body is `pass`/`...`/`NotImplementedError` WITHOUT `STUB_SENTINEL` | ERROR (LLM failed to implement) | `def send_email(email, order): pass` |

**File:** `src/startd8/contractors/checkpoint.py`

```python
from startd8.utils.code_extraction import STUB_SENTINEL

def check_stubs(
    self,
    files: list[Path],
    *,
    max_llm_stub_ratio: float = 0.3,
) -> CheckpointResult:
    """Detect LLM-generated stubs (functions the LLM failed to implement).

    Pipeline stubs (carrying ``STUB_SENTINEL``) are expected for
    downstream tasks and reported as info, not errors.

    LLM stubs (function body is ``pass``/``...``/``raise
    NotImplementedError`` without the sentinel) indicate the LLM
    didn't implement the function.  Files exceeding
    *max_llm_stub_ratio* are reported as errors.
    """
```

**Tests:** Update `tests/unit/contractors/test_checkpoint_semantic.py`:

- `test_pipeline_stub_is_info_not_error` — file with `STUB_SENTINEL` → INFO
- `test_llm_stub_pass_is_error` — `def f(): pass` without sentinel → ERROR
- `test_llm_stub_ratio_threshold` — 1 LLM stub in 10 functions → PASSED
- `test_mixed_pipeline_and_llm_stubs` — pipeline stubs don't count toward ratio

---

### Refinement 3: L2 — Replace import symbol validation with known-bad denylist

> **[ICHIGO ICHIE VIOLATION]** This refinement was flagged by the Ichigo Ichie
> design principle review. The hardcoded denylist entries (`jsonlogger`,
> `google.cloud.vectordb`) are calibration-specific observations from the
> online-boutique run-016. `jsonlogger` is a valid import in some package
> versions. See `ICHIGO_ICHIE_DESIGN_PRINCIPLE.md` for the generalized
> alternative: **dependency-aware import validation** — validate that every
> import corresponds to a declared runtime dependency (via the `package_aliases.py`
> alias map), the standard library, or a project-local module. This catches the
> same bugs without a project-specific denylist.

**Problem with original plan:** L2 Step 3 proposes `importlib.import_module(X)`
then `getattr(module, Y)` to validate symbols. This is impractical because:
- Proto-generated modules (`demo_pb2`) are not importable in the SDK env
- Project-local modules (`logger`) are not on PYTHONPATH
- Framework packages (`locust`, `grpc`) may not be installed

**Refinement:** Replace universal import validation with a **known-bad import
denylist** populated from observed hallucinations across runs.

**File:** `src/startd8/contractors/checkpoint.py`

```python
# Known hallucinated imports observed in production runs.
# Maps bad_import → correct_import (or None if no replacement exists).
# Updated as new hallucinations are observed across Kaizen runs.
_KNOWN_BAD_IMPORTS: dict[str, str | None] = {
    "jsonlogger": "pythonjsonlogger.jsonlogger",
    "google.cloud.vectordb": None,  # doesn't exist on PyPI
}

def check_known_bad_imports(
    self,
    files: list[Path],
) -> CheckpointResult:
    """Flag imports known to be hallucinated by LLMs.

    When a corrected import is known, include it in the error message
    so the repair pipeline or human reviewer can fix it.
    """
```

Algorithm:
1. AST-parse each file, extract `Import` and `ImportFrom` nodes
2. Check each module name against `_KNOWN_BAD_IMPORTS`
3. Report as error with suggested replacement (if available)

This is data-driven (from actual failures), low false-positive, and grows
organically as new runs reveal new hallucination patterns. Each Kaizen
investigation should update the denylist.

**Tests:**

- `test_known_bad_jsonlogger` — `import jsonlogger` → error with suggestion
- `test_known_bad_vectordb` — `from google.cloud.vectordb import X` → error, no replacement
- `test_valid_import_not_flagged` — `import grpc` → PASSED
- `test_denylist_extensible` — custom denylist merges with built-in

---

### Refinement 4: L3 — Add task ordering guarantee and bidirectional alias map

**Problem with original plan:** L3 proposes AST-parsing existing Python files
to scope dependencies for requirements.in generation. But if requirements.in
tasks run *before* the Python file tasks for the same service, there are no
files to parse.

**Refinement A — Task ordering precondition:**

The plan should specify that the `scope_dependencies_to_file()` function reads
from *already-generated* files in the pipeline output directory. Add a
validation step in the spec builder:

```python
def _scope_deps_for_requirements_file(self, context: dict) -> list[str]:
    """Scope dependencies to co-located Python files.

    Reads generated Python files from the pipeline output directory
    for this service.  Falls back to the full dependency list with
    a warning if no Python files are found (indicating a task ordering
    issue).
    """
    service_dir = self._resolve_service_dir(context)
    py_files = list(service_dir.glob("*.py"))
    if not py_files:
        logger.warning(
            "No Python files found in %s for dependency scoping — "
            "requirements file tasks should run AFTER Python file tasks. "
            "Falling back to full dependency list.",
            service_dir,
        )
        return context.get("runtime_dependencies", [])
    # ... AST-parse and scope ...
```

**Refinement B — Bidirectional alias map:**

The original plan's `_PYPI_TO_IMPORT` map serves one direction (PyPI→import,
for scoping). But the L1 import audit pass needs the reverse direction
(import→PyPI, to suggest packages). Make it a single source of truth:

**File:** `src/startd8/implementation_engine/package_aliases.py` (new)

```python
"""Bidirectional mapping between PyPI package names and Python import names.

Single source of truth used by:
- Dependency scoping (L3): PyPI → import direction
- Import audit pass (L1): import → PyPI direction
- Framework detection (L5): both directions
"""

_PYPI_TO_IMPORT: dict[str, str] = {
    "grpcio": "grpc",
    "grpcio-health-checking": "grpc_health",
    "pillow": "PIL",
    "python-json-logger": "pythonjsonlogger",
    "google-api-core": "google.api_core",
    "google-cloud-secret-manager": "google.cloud.secretmanager",
    "opentelemetry-distro": "opentelemetry",
    "opentelemetry-exporter-otlp-proto-grpc": "opentelemetry.exporter.otlp",
    "opentelemetry-instrumentation-grpc": "opentelemetry.instrumentation.grpc",
    "python-dateutil": "dateutil",
    "pyyaml": "yaml",
    "beautifulsoup4": "bs4",
}

# Auto-generated reverse map
_IMPORT_TO_PYPI: dict[str, str] = {v: k for k, v in _PYPI_TO_IMPORT.items()}


def pypi_to_import(package_name: str) -> str:
    """Map a PyPI package name to its Python import name."""
    return _PYPI_TO_IMPORT.get(package_name, package_name)


def import_to_pypi(import_name: str) -> str:
    """Map a Python import name to its PyPI package name."""
    # Try exact match first, then prefix match for nested imports
    if import_name in _IMPORT_TO_PYPI:
        return _IMPORT_TO_PYPI[import_name]
    for imp, pypi in _IMPORT_TO_PYPI.items():
        if import_name.startswith(imp + "."):
            return pypi
    return import_name
```

**Tests:** `tests/unit/implementation_engine/test_package_aliases.py` (new)

- `test_pypi_to_import_known` — `grpcio` → `grpc`
- `test_pypi_to_import_unknown_passthrough` — `flask` → `flask`
- `test_import_to_pypi_known` — `grpc` → `grpcio`
- `test_import_to_pypi_nested` — `google.api_core.retry` → `google-api-core`
- `test_bidirectional_consistency` — all entries round-trip correctly

---

### Refinement 5: L5 — Derive imports from sibling files, not hardcoded templates

**Problem with original plan:** L5 proposes a hardcoded `FRAMEWORK_IMPORTS`
dict with static import blocks. This is brittle:
- Proto module names vary by project (not always `demo_pb2`)
- The `detect` keyword lists produce false positives/negatives
- New frameworks require code changes to the registry

**Refinement:** Instead of hardcoding imports, **derive them from existing
files in the same service directory**. The enriched seed already carries
`existing_content` for files that exist. If `recommendation_server.py` is
being generated and `logger.py` already exists in `src/recommendationservice/`,
extract its import block and inject it as "imports used by sibling files in
this service."

**File:** `src/startd8/implementation_engine/spec_builder.py`

```python
def _build_sibling_imports_section(self, context: dict) -> str:
    """Extract imports from existing sibling files in the same directory.

    When generating a new file, knowing what its neighbors import
    provides project-specific framework context that no hardcoded
    template can match (e.g. the exact proto module names, the
    project's logging pattern, the OTel setup convention).
    """
    existing_files = context.get("existing_files_content", {})
    target_dir = self._target_directory(context)
    sibling_imports = set()

    for path, content in existing_files.items():
        if not path.endswith(".py"):
            continue
        if os.path.dirname(path) != target_dir:
            continue
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                sibling_imports.add(ast.unparse(node))

    if not sibling_imports:
        return ""

    lines = ["## Imports Used by Sibling Files in This Directory\n"]
    lines.append("The following imports are used by other files in this")
    lines.append("service. Use the same packages and import patterns")
    lines.append("where applicable:\n")
    lines.append("```python")
    lines.extend(sorted(sibling_imports))
    lines.append("```")
    return "\n".join(lines)
```

**The original hardcoded templates become a fallback** for greenfield projects
where no sibling files exist. Rename from `FRAMEWORK_IMPORTS` to
`FRAMEWORK_IMPORT_DEFAULTS` and only use when `_build_sibling_imports_section`
returns empty.

**Why this is better:**
- Project-specific: uses exact proto module names from this project
- Self-maintaining: no code changes needed when frameworks are added
- Accurate: reflects what actually works in this codebase, not generic patterns

**Tests:** `tests/unit/implementation_engine/test_sibling_imports.py` (new)

- `test_sibling_imports_extracted` — logger.py imports → included in section
- `test_sibling_imports_different_dir_excluded` — files in other dirs ignored
- `test_sibling_imports_syntax_error_skipped` — broken file doesn't crash
- `test_sibling_imports_empty_returns_empty` — no siblings → no section
- `test_fallback_to_framework_defaults` — no siblings + gRPC detected → defaults used
- `test_non_python_siblings_excluded` — Dockerfile not parsed

---

### NEW — L6: Cloud Fallback → Element Registry Backfill

**Problem:** The element registry has a 1.2% hit rate (1 hit across 86 element
events in runs 013-016). A major reason: cloud fallback generates complete
files but never decomposes them back into elements for the registry. When a
feature escalates to cloud, the resulting code is used but never cached. The
next run on the same project starts from scratch.

**Root Cause:** `_delegate_to_fallback()` in `prime_adapter.py` returns a
`GenerationResult` with generated files, but `_persist_registry_entries()` is
only called for micro-prime-generated elements (line 830-885). Cloud-generated
files are invisible to the registry.

### Implementation

#### Step 1: Add `_backfill_registry_from_cloud()` to prime adapter

**File:** `src/startd8/micro_prime/prime_adapter.py`

```python
def _backfill_registry_from_cloud(
    self,
    generated_files: list[str],
    feature_id: str,
) -> int:
    """Decompose cloud-generated files into registry entries.

    After cloud fallback produces files that pass validation,
    AST-decompose each Python file into individual function/class
    elements and ``registry.put()`` each one.  This populates the
    registry for future runs on the same project.

    Returns the number of elements backfilled.
    """
    if self._element_registry is None:
        return 0

    backfilled = 0
    for file_path in generated_files:
        if not file_path.endswith(".py"):
            continue
        try:
            source = Path(file_path).read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, SyntaxError):
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                     ast.ClassDef)):
                continue
            # Extract source lines for this definition
            start = node.lineno - 1
            end = node.end_lineno or start + 1
            code_lines = source.splitlines()[start:end]
            code = "\n".join(code_lines)

            # Determine parent class (for methods)
            parent_class = None
            for parent in ast.walk(tree):
                if isinstance(parent, ast.ClassDef):
                    if node in ast.walk(parent) and parent is not node:
                        parent_class = parent.name
                        break

            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            rel_path = os.path.relpath(file_path, self._project_root)

            element_id = self._element_registry.compute_element_id(
                kind=kind,
                name=node.name,
                file_path=rel_path,
                parent_class=parent_class,
            )

            entry = ElementEntry(
                element_id=element_id,
                kind=kind,
                name=node.name,
                file_path=rel_path,
                parent_class=parent_class,
                extra={
                    "code": code,
                    "generator": "cloud-backfill",
                    "feature_id": feature_id,
                },
            )
            self._element_registry.put(entry)
            self._element_registry.set_phase_status(
                element_id, "cloud_backfill", "validated",
            )
            backfilled += 1

    return backfilled
```

#### Step 2: Call after successful cloud fallback

**File:** `src/startd8/micro_prime/prime_adapter.py`

In `generate()`, after `_delegate_to_fallback()` returns successfully:

```python
fallback_result = self._delegate_to_fallback(
    task, fallback_context, escalated_files,
)
generated_files.extend(fallback_result.generated_files)

# Backfill registry from cloud output for future run reuse
if fallback_result.success and self._element_registry is not None:
    backfill_count = self._backfill_registry_from_cloud(
        fallback_result.generated_files,
        feature_id=context.get("feature_id", "unknown"),
    )
    if backfill_count > 0:
        logger.info(
            "Backfilled %d elements from cloud fallback into registry",
            backfill_count,
        )
```

#### Step 3: Tests

**File:** `tests/unit/micro_prime/test_registry_backfill.py` (new)

- `test_backfill_extracts_functions` — file with 3 functions → 3 registry entries
- `test_backfill_extracts_classes` — file with class → class entry
- `test_backfill_extracts_methods_with_parent` — method → entry with parent_class
- `test_backfill_skips_non_python` — Dockerfile → 0 entries
- `test_backfill_skips_syntax_error` — broken file → 0 entries, no crash
- `test_backfill_sets_generator_cloud` — entry has `generator: "cloud-backfill"`
- `test_backfill_entries_retrievable` — put then get round-trips correctly
- `test_backfill_not_called_on_failure` — failed fallback → no backfill

---

### NEW — L7: Repair Marker Cleanup

**Problem:** Generated output files contain `# [REPAIRED BY STARTD8: fence_strip, import_completion]`
at the top (injected by `_inject_traceability_comment()` in `repair/orchestrator.py:364-369`).
These markers are useful for debugging but leak into production output that
users receive.

**Root Cause:** The traceability comment is injected during repair and never
removed. The markers remain in the pipeline artifacts AND in the final deployed
files.

### Implementation

#### Step 1: Add marker stripping to integration engine

**File:** `src/startd8/repair/orchestrator.py`

```python
def strip_repair_markers(code: str) -> str:
    """Remove STARTD8 repair traceability comments from final output.

    Called before writing files to the project directory.  The markers
    remain in ``.artifacts/`` pipeline copies for debugging.
    """
    lines = code.splitlines(keepends=True)
    cleaned = [
        line for line in lines
        if not line.strip().startswith(_TRACEABILITY_PREFIX.rstrip())
    ]
    # Strip leading blank line if marker removal left one
    while cleaned and cleaned[0].strip() == "":
        cleaned.pop(0)
    return "".join(cleaned)
```

#### Step 2: Call during file write in lead contractor

**File:** `src/startd8/contractors/generators/lead_contractor.py`

Before writing the final file to the project directory, strip markers:

```python
from startd8.repair.orchestrator import strip_repair_markers

# Before file write:
clean_code = strip_repair_markers(code)
```

#### Step 3: Tests

**File:** `tests/unit/repair/test_marker_cleanup.py` (new)

- `test_strip_single_marker` — `# [REPAIRED BY STARTD8: ...]` removed
- `test_strip_preserves_other_comments` — normal comments preserved
- `test_strip_no_markers_unchanged` — clean file returns unchanged
- `test_strip_leading_blank_cleaned` — blank line after removal cleaned up

---

### Refinement 8: L4 — Emit structured constraints from spec builder, don't extract from prose

**Problem with original plan:** L4 proposes regex extraction of MUST/MUST NOT
from spec prose. This is fragile:
- Over-extracts from narrative ("the server MUST listen on port 8080")
- Misses constraints phrased differently ("Omit X", "Do NOT add Y")
- Produces noisy checklists the reviewer ignores

**Refinement:** Instead of extracting constraints from prose, **emit them as
a structured block during spec construction**. The spec builder already knows
the constraints (from `critical_parameters`, `domain_constraints`,
`prompt_constraints`). Emit them explicitly rather than trying to recover
them later.

**File:** `src/startd8/implementation_engine/spec_builder.py`

```python
def _build_constraint_block(self, context: dict) -> tuple[str, list[dict]]:
    """Build a structured constraint block for the spec AND a machine-
    readable list for the review phase.

    Returns ``(spec_section_text, constraint_list)`` where
    ``constraint_list`` is stored in the task context for review.
    """
    constraints = []

    # From critical_parameters
    for param in context.get("critical_parameters", []):
        constraints.append({
            "type": "MUST",
            "text": param,
            "source": "critical_parameters",
        })

    # From domain_constraints
    for dc in context.get("domain_constraints", []):
        ctype = "MUST_NOT" if dc.lower().startswith(("do not", "never")) else "MUST"
        constraints.append({
            "type": ctype,
            "text": dc,
            "source": "domain_constraints",
        })

    # From prompt_constraints
    for pc in context.get("prompt_constraints", []):
        ctype = "MUST_NOT" if pc.lower().startswith(("do not", "never")) else "MUST"
        constraints.append({
            "type": ctype,
            "text": pc,
            "source": "prompt_constraints",
        })

    if not constraints:
        return "", []

    lines = ["## Constraints\n"]
    for i, c in enumerate(constraints, 1):
        lines.append(f"{i}. **[{c['type']}]** {c['text']}")
    spec_text = "\n".join(lines)

    return spec_text, constraints
```

The `constraint_list` is stored in `context["spec_constraints"]` and flows
through to the review phase via the task context — no regex extraction
needed. The review prompt receives the exact constraints that the spec
builder emitted, with full fidelity.

**Tests:** Update `tests/unit/contractors/test_review_constraints.py`:

- `test_constraints_from_critical_params` — critical param → MUST constraint
- `test_constraints_from_domain_do_not` — "Do not add X" → MUST_NOT
- `test_constraints_round_trip_to_review` — spec builder emits, review receives same list
- `test_empty_constraints_no_block` — no constraints → no section in spec

---

### Revised Execution Order

```
Phase 1: L1+ (import audit pass) + L3+ (dependency scoping + alias map)
    │     Foundation — deterministic import injection, scoped deps,
    │     shared package_aliases.py module
    │
Phase 2: L5+ (sibling-file imports) + L6 (cloud → registry backfill)
    │     Both use AST decomposition; L5 builds on L1's spec sections;
    │     L6 is independent but architecturally adjacent (prime_adapter)
    │
Phase 3: L2+ (stub detection + known-bad denylist) + L7 (marker cleanup)
    │     Both are checkpoint/post-processing changes, independent
    │     of prompt pipeline
    │
Phase 4: L4+ (structured constraint emission)
          Needs spec_builder changes from Phase 1; lowest priority
```

### Revised Validation Targets

> **[ICHIGO ICHIE NOTE]** These targets should be validated against a *new*
> project the pipeline has never seen, not only re-runs of online-boutique.
> The "Element registry" metric is reframed as within-run element reuse
> (features sharing elements in a single run), which is meaningful for
> first-run projects. Cross-run hit rate is a secondary metric.

| Metric | Current (Run-016) | After Phase 1-2 | After Phase 3-4 |
|--------|-------------------|-----------------|-----------------|
| Files needing import repair | 100% (5/5 .py) | <20% | <10% |
| Semantic bugs in output | 6 | 3-4 | 0-1 |
| Cross-contaminated deps | 4/4 req files | 0 | 0 |
| Framework lint error density | 12-19 errors | <5 | <3 |
| Stubs reported as PASS | 1 | 1 | 0 |
| Repair markers in output | 5 files | 5 files | 0 |
| Within-run element reuse | 0% (no sharing) | 5-10% (backfill) | 10-20% |
| Weighted quality score | 83.2/100 | >88/100 | >92/100 |

### Revised File Manifest

| Lesson | New Files | Modified Files |
|--------|-----------|---------------|
| L1+ | `tests/unit/test_code_extraction.py` (extend) | `src/startd8/utils/code_extraction.py`, `src/startd8/implementation_engine/prompts/contractor_prompts.yaml`, `src/startd8/implementation_engine/drafter.py` |
| L3+ | `src/startd8/implementation_engine/package_aliases.py`, `tests/unit/implementation_engine/test_package_aliases.py`, `tests/unit/implementation_engine/test_dependency_scoping.py` | `src/startd8/implementation_engine/spec_builder.py`, `src/startd8/contractors/context_seed/shared.py` |
| L5+ | `src/startd8/implementation_engine/framework_imports.py`, `tests/unit/implementation_engine/test_sibling_imports.py`, `tests/unit/implementation_engine/test_framework_imports.py` | `src/startd8/implementation_engine/spec_builder.py` |
| L6 | `tests/unit/micro_prime/test_registry_backfill.py` | `src/startd8/micro_prime/prime_adapter.py` |
| L2+ | `tests/unit/contractors/test_checkpoint_semantic.py` | `src/startd8/contractors/checkpoint.py` |
| L7 | `tests/unit/repair/test_marker_cleanup.py` | `src/startd8/repair/orchestrator.py`, `src/startd8/contractors/generators/lead_contractor.py` |
| L4+ | `tests/unit/contractors/test_review_constraints.py` | `src/startd8/implementation_engine/spec_builder.py`, `src/startd8/contractors/context_seed/core.py` |

---
---

## Addendum 2: Near-Ready Capabilities and Quick Wins (Ichigo Ichie Reviewed)

**Date:** 2026-03-09
**Source:** Codebase audit for disabled features, unwired integrations, and low-effort improvements
**Design Principle Review:** All items below pass the [Ichigo Ichie test](../../design-princples/ICHIGO_ICHIE_DESIGN_PRINCIPLE.md) —
each improves first-run quality for any project, not just calibration re-runs.

---

### Category A: Near-Ready Capabilities (Config Flip / Minimal Wiring)

#### A1: Wire DFA Pre-Fill to Element Registry

**Effort:** ~5 lines across 5 call sites | **Impact:** HIGH | **Ichigo Ichie:** PASS
(benefits within-run element sharing — earlier features populate the registry,
later features in the same run can reuse them)

**Problem:** `DeterministicFileAssembler` accepts an `element_registry` constructor
parameter and has pre-fill logic (REQ-MP-1106) that uses cached implementations
to populate skeletons instead of `raise NotImplementedError`. But none of the
5 instantiation sites pass a registry:

| Call Site | File | Line |
|-----------|------|------|
| 1 | `src/startd8/micro_prime/prime_adapter.py` | 1256 |
| 2 | `src/startd8/micro_prime/repair.py` | 696 |
| 3 | `src/startd8/micro_prime/engine.py` | 2017 |
| 4 | `src/startd8/contractors/context_seed/phases/scaffold.py` | 189 |
| 5 | `src/startd8/workflows/builtin/plan_ingestion_workflow.py` | 4040 |

**Fix:** Pass `element_registry=self._element_registry` (or the equivalent
registry reference) at each call site where a registry is available.

Sites 1-3 are in the micro_prime package where the registry is already
instantiated. Sites 4-5 may not have a registry in scope — pass `None`
(the parameter is already optional with `None` default).

```python
# prime_adapter.py:1256 — registry is self._element_registry
assembler = DeterministicFileAssembler(element_registry=self._element_registry)

# engine.py:2017 — registry is self._element_registry
assembler = DeterministicFileAssembler(element_registry=self._element_registry)

# repair.py:696 — registry may not be in scope, pass None explicitly
assembler = DeterministicFileAssembler(element_registry=None)
```

**Tests:** Existing DFA pre-fill tests should already cover the behavior
once the registry is wired. Verify with:
- `pytest tests/unit/micro_prime/ -k "prefill or pre_fill" -v`

---

#### A2: Enable Semantic Verification

**Effort:** Config toggle | **Impact:** MEDIUM | **Ichigo Ichie:** PASS
(validates generated code semantically for any project)

**Problem:** A complete semantic verification engine exists in
`src/startd8/micro_prime/engine.py:1881-1954` (REQ-MP-512). It supports
two modes:

1. **Custom function hook** — `semantic_verification_fn` callback
2. **LLM-based verification** — Uses a separate agent to verify generated
   code against element contracts and binding constraints

On failure, the element is escalated to cloud with
`EscalationReason.SEMANTIC_FAILURE`. The engine is fully implemented but
gated behind `semantic_verification_enabled: false` in `MicroPrimeConfig`
(`src/startd8/micro_prime/models.py:181`).

**Configuration:**
```json
// .startd8/micro_prime.json
{
    "semantic_verification_enabled": true,
    "semantic_verification_agent_spec": "anthropic:claude-sonnet-4-20250514",
    "semantic_verification_max_tokens": 256,
    "semantic_verification_temperature": 0.0,
    "semantic_verification_prompt_max_chars": 4000
}
```

**Trade-off:** Enabling adds one LLM call per element (cost increase of
~$0.003-0.01 per element at Sonnet pricing). For projects where correctness
matters more than cost, this catches hallucinated APIs, wrong method
signatures, and contract violations before they reach the output.

**Recommendation:** Enable by default in the pipeline config with a CLI
flag to disable (`--no-semantic-verify`) for cost-sensitive runs.

---

#### A3: Enable Simple-to-Trivial Decomposer

**Effort:** Config toggle | **Impact:** HIGH | **Ichigo Ichie:** PASS
(reduces LLM calls for any project with SIMPLE-tier elements)

**Problem:** A `FunctionBodyDecomposer` exists in
`src/startd8/micro_prime/clause_mapper.py` that decomposes SIMPLE function
bodies into template-renderable clauses — generating code with **zero LLM
calls**. It's gated behind `enable_simple_decomposer: false` in
`MicroPrimeConfig` (`src/startd8/micro_prime/models.py:204`).

**How it works** (`engine.py:1535-1575`):
1. Before calling Ollama for a SIMPLE element, tries `decomposer.try_decompose()`
2. If confidence exceeds `simple_decomposer_confidence_threshold` (default 0.6):
   code is assembled from templates (0 LLM calls, deterministic)
3. If decomposition fails: falls through to Ollama as normal

**Configuration:**
```json
// .startd8/micro_prime.json
{
    "enable_simple_decomposer": true,
    "simple_decomposer_confidence_threshold": 0.6
}
```

**Trade-off:** Lower confidence threshold = more elements decomposed locally
(cheaper, faster, deterministic) but with higher risk of incorrect output.
Higher threshold = fewer elements decomposed but more reliable.

**Recommendation:** Enable with default 0.6 threshold. The fallback to
Ollama means incorrect decompositions are caught — the only cost of a
false-positive decomposition is one wasted template render before Ollama
takes over.

**Correction:** The decomposer does NOT fall back to Ollama on bad output —
`try_decompose()` returns `None` (rejected) or code (accepted). If it
returns code, that code is used directly. The confidence threshold is
therefore the primary quality gate. Start at 0.7 to be conservative.

---

### Category B: Prompt and Observability Quick Wins

#### B1: Strengthen Import Instructions in Draft Prompt

**Effort:** YAML edit (1 file) | **Impact:** HIGH | **Ichigo Ichie:** PASS
(benefits any Python code generation)

**Problem:** The spec template already includes an `available_imports` section
(`spec_builder.py:210-242`) that says:

> "Use ONLY these packages plus Python stdlib. Every non-stdlib symbol you
> reference MUST have a corresponding import statement at the top of the file."

But 100% of Python files in run-016 still needed import repair. The instruction
is in the *spec* but the LLM generates code from the *draft* prompt, which
lacks a reinforcing instruction.

**Fix:** Add an explicit import reinforcement to the draft template.

**File:** `src/startd8/implementation_engine/prompts/contractor_prompts.yaml`

Add to the `draft_code` template's instruction block:

```yaml
draft_code:
  template: |
    ...existing template...

    CRITICAL — Import Completeness:
    Every module, class, function, constant, or type you reference MUST have
    a corresponding import statement at the top of the file. Do NOT assume
    any name is available without an explicit import. Include stdlib imports
    (os, sys, pathlib, typing, etc.) even if they seem obvious. The file
    must be independently parseable by `python3 -c "import ast; ast.parse(open('file').read())"`.
```

**Why it helps:** The spec tells the LLM *what* to import; the draft
instruction tells it *that it must import*. The gap is procedural — the
LLM writes code first and forgets to add imports. A strongly worded
per-file instruction at draft time addresses this directly.

**Tests:** No unit test needed — this is prompt content. Validate by
running the pipeline on a test project and measuring import repair rate.

---

#### B2: Log Escalation Reasons in Micro Prime

**Effort:** ~10 lines | **Impact:** HIGH (observability) | **Ichigo Ichie:** PASS

**Problem:** `_delegate_to_fallback()` in `prime_adapter.py:1324-1343` silently
delegates to the cloud generator with no logging of *why* the escalation
happened. The `generate()` method has some logging at individual escalation
points, but a summary "this feature escalated because X" log is missing.

**Fix:** Add structured escalation logging before calling `_delegate_to_fallback()`:

**File:** `src/startd8/micro_prime/prime_adapter.py`

```python
# Before each call to self._delegate_to_fallback():
logger.info(
    "Escalating to cloud fallback: feature=%s, reason=%s, "
    "failed_elements=%s, escalated_files=%d",
    context.get("feature_id", "unknown"),
    escalation_reason,  # e.g. "no_manifest", "ollama_unavailable", "element_failure"
    [e.name for e in failed_elements] if failed_elements else [],
    len(escalated_files),
)
```

There are multiple escalation points in `generate()` (lines 315, 327, 387,
471, 500, 508, 513). Each should include the specific reason. The data is
already available at each point — it just isn't logged.

**Tests:** No new tests — this is observability. Verify by checking Loki
logs after a run with escalations.

---

#### B3: Log Repair Step Results with Decision Context

**Effort:** ~5 lines | **Impact:** HIGH (observability) | **Ichigo Ichie:** PASS

**Problem:** The repair orchestrator runs repair steps and returns results,
but doesn't log which steps were applied, which succeeded, and which failed
for each file. This makes post-run debugging difficult.

**Fix:** Add per-step result logging in the repair orchestrator.

**File:** `src/startd8/repair/orchestrator.py`

After each repair step completes, log:

```python
logger.info(
    "Repair step %s on %s: %s (changed=%s)",
    step.name,
    file_path,
    "PASS" if result.success else "FAIL",
    result.changed,
)
```

And a summary after all steps:

```python
logger.info(
    "Repair complete for %s: %d/%d steps succeeded, steps=[%s]",
    file_path,
    sum(1 for r in results if r.success),
    len(results),
    ", ".join(r.step_name for r in results if r.changed),
)
```

---

#### B4: Dependency-Aware Import Validation

**Effort:** MEDIUM (~40 lines) | **Impact:** HIGH | **Ichigo Ichie:** PASS
(replaces the Ichigo Ichie-violating denylist from Refinement 3)

**Problem:** Refinement 3 proposed a hardcoded known-bad import denylist.
This violates Ichigo Ichie because the entries are calibration-specific.
The generalized alternative: validate that every import corresponds to
a declared dependency, stdlib, or project-local module.

**File:** `src/startd8/contractors/checkpoint.py`

```python
def check_import_dependency_alignment(
    self,
    files: list[Path],
    *,
    runtime_dependencies: list[str] | None = None,
    package_alias_map: dict[str, str] | None = None,
) -> CheckpointResult:
    """Validate that imports align with declared runtime dependencies.

    For each import in each file, checks that the imported module is:
    1. A Python stdlib module (``sys.stdlib_module_names`` on 3.10+,
       fallback list for 3.9)
    2. A declared runtime dependency (matched via *package_alias_map*
       for PyPI-name → import-name translation)
    3. A project-local module (relative import or matches project
       package name)

    Imports that match none of these are flagged as warnings (not errors)
    because the dependency list may be incomplete. The warning includes
    the closest alias-map match if available, e.g.:

        "import jsonlogger — not in declared deps. Did you mean
         'pythonjsonlogger' (from python-json-logger)?"
    """
```

**Why this is better than a denylist:**
- Catches `import jsonlogger` when `python-json-logger` is in deps (alias
  map says the correct import is `pythonjsonlogger`) — same bug caught
- Catches `google.cloud.vectordb` when it's not in deps — same bug caught
- Also catches novel hallucinations in *any future project* without
  maintaining a growing denylist
- Zero false positives for projects that legitimately use `jsonlogger`
  as a direct dependency

**Depends on:** `package_aliases.py` from Refinement 4 (L3+)

**Tests:** `tests/unit/contractors/test_checkpoint_import_alignment.py` (new)

- `test_stdlib_import_passes` — `import os` → PASS
- `test_declared_dep_passes` — `import flask`, deps=`["flask"]` → PASS
- `test_aliased_dep_passes` — `import grpc`, deps=`["grpcio"]` → PASS
- `test_undeclared_import_warns` — `import jsonlogger`, deps=`["python-json-logger"]` → WARNING with suggestion
- `test_project_local_passes` — `from . import utils` → PASS
- `test_no_deps_provided_skips` — no deps → skip check entirely

---

#### B5: Review Score Feedback Loop

**Effort:** SMALL (~20 lines) | **Impact:** MEDIUM | **Ichigo Ichie:** PASS
(feeds review quality data back into any project's next run)

**Problem:** The postmortem report collects review scores and success rates
but doesn't generate actionable kaizen suggestions from them. The
`accumulated_patterns` field in `kaizen-trends.json` is always empty.

**Fix:** After postmortem generation, analyze score distributions and emit
concrete suggestions. This is general-purpose pattern extraction, not
calibration-specific memorization.

**File:** `src/startd8/contractors/prime_contractor.py` (or wherever
postmortem is assembled)

```python
def _generate_kaizen_suggestions(
    self,
    postmortem: dict,
    prior_trends: dict | None = None,
) -> list[dict]:
    """Generate actionable suggestions from postmortem metrics.

    Suggestions are general-purpose patterns, not project-specific fixes:
    - "3/5 files needed import repair → consider enabling import audit"
    - "2 elements escalated due to Ollama timeout → increase timeout"
    - "Review score < 0.7 for gRPC files → check framework import coverage"
    """
```

The suggestions reference pipeline configuration knobs (timeouts, thresholds,
enabled features) rather than project-specific content.

---

### Category C: Ichigo Ichie Remediation (Reworked from Violations)

#### C1: Drop Hardcoded Framework Import Defaults

**Effort:** Delete code | **Impact:** Removes calibration bias | **Ichigo Ichie:** REMEDIATION

The original L5 proposed `FRAMEWORK_IMPORTS` with hardcoded gRPC/Locust/OTel
import blocks. Refinement L5+ replaced this with sibling-file derivation
(`_build_sibling_imports_section`), but the plan still mentions
`FRAMEWORK_IMPORT_DEFAULTS` as a fallback.

**Decision:** Drop the fallback entirely. For greenfield projects with no
sibling files, the L1+ deterministic import audit pass handles missing
imports after generation. There is no need for hardcoded framework templates
that encode calibration-project assumptions.

---

### Execution Priority

```
Immediate (config changes, no code risk):
  A1  Wire DFA pre-fill             — 5 lines, 5 files
  A3  Enable simple decomposer      — config toggle
  B1  Strengthen draft import inst   — YAML edit

Phase 1 (small code changes, high observability value):
  B2  Log escalation reasons         — 10 lines
  B3  Log repair step results        — 5 lines

Phase 2 (medium code, high quality value):
  B4  Dependency-aware import valid  — 40 lines, new checkpoint
  A2  Enable semantic verification   — config toggle + cost trade-off

Phase 3 (feedback loop):
  B5  Review score feedback loop     — 20 lines
  C1  Drop framework defaults        — delete code
```

### File Manifest

| Item | New Files | Modified Files |
|------|-----------|---------------|
| A1 | — | `prime_adapter.py:1256`, `engine.py:2017`, `repair.py:696`, `scaffold.py:189`, `plan_ingestion_workflow.py:4040` |
| A2 | — | `.startd8/micro_prime.json` (config) |
| A3 | — | `.startd8/micro_prime.json` (config) |
| B1 | — | `contractor_prompts.yaml` |
| B2 | — | `prime_adapter.py` (~6 escalation points) |
| B3 | — | `repair/orchestrator.py` |
| B4 | `tests/unit/contractors/test_checkpoint_import_alignment.py` | `checkpoint.py` |
| B5 | — | `prime_contractor.py` (postmortem section) |
| C1 | — | `spec_builder.py` (delete fallback) |
