# Domain-Aware Pre-Flight Checklists

> **Status**: Concept / deferred until artisan workflow is online
> **Date**: 2026-02-09
> **Context**: Patterns observed during PrimeContractor execution of artisan contractor foundation tasks

## Problem Statement

During PrimeContractor execution of 37 artisan contractor tasks, several classes of failure repeated predictably:

| Failure | Root Cause | When Detectable |
|---------|-----------|-----------------|
| `from .base import ...` in single-file target | LLM designed a package, target is one file | **Before generation** — target path is known |
| `ModuleNotFoundError: tiktoken` | LLM used dep not in pyproject.toml | **Before generation** — deps are scannable |
| `NameError: generate_id` after merge | Merge reordered functions below their callers | **After generation, before integration** |
| Target dir `artisan_phases/` missing | No `__init__.py` for package | **Before generation** — path is known |
| INTEGRATING status deadlock | Status not in retry-reset list | Structural (already fixed) |

Every one of these was **predictable from information available before code generation started**. The current `pre_flight_validation()` only checks estimated size. It knows nothing about the target environment, available dependencies, or structural constraints.

## Core Insight

The PrimeContractor pipeline has three phases where domain knowledge can prevent errors:

```
[1] PRE-GENERATION          [2] POST-GENERATION           [3] POST-INTEGRATION
    (before LLM call)           (before merge/copy)            (existing checkpoints)

    Target analysis              Output validation              Syntax check
    Dep scanning                 Pattern enforcement            Import check
    Constraint injection         Ordering verification          Lint check
    Environment readiness                                       Test check
```

Phase [3] already exists (IntegrationCheckpoint). Phases [1] and [2] are missing. Phase [1] is the highest-leverage — it prevents errors rather than detecting them.

## Design: Domain-Specific Pre-Flight Checklists

### Domain Detection

Given a target file path, infer the domain:

```
src/startd8/contractors/artisan_models.py     → python-single-module
src/startd8/contractors/artisan_phases/*.py    → python-package-module
tests/unit/contractors/test_artisan_models.py  → python-test
pyproject.toml                                 → config-toml
```

Detection heuristic:
- Path contains `test` or filename starts with `test_` → `python-test`
- Target dir has `__init__.py` or other `.py` siblings → `python-package-module`
- Single `.py` file in a directory without it being a package root → `python-single-module`
- Known config extensions (`.toml`, `.yaml`, `.json`) → `config-*`

### Checklist per Domain

#### `python-single-module`
**Pre-generation constraints** (injected into LLM prompt context):
- [ ] "Output a single Python module — not a package with `__init__.py`"
- [ ] "Do not use relative imports (`from .module import ...`)"
- [ ] "Define utility functions before classes that reference them in `Field(default_factory=...)`"
- [ ] Only import from packages listed in pyproject.toml `[project.dependencies]` + stdlib

**Environment readiness**:
- [ ] Parent directory exists
- [ ] If target file exists: read it, include current content as context

**Post-generation validation** (before integration):
- [ ] No `from .` imports in output
- [ ] No `import <pkg>` where `<pkg>` is not in available deps
- [ ] Functions referenced in `default_factory=` are defined before the class

#### `python-package-module`
**Pre-generation constraints**:
- [ ] "This file is part of the `{package_name}` package"
- [ ] "Use relative imports for sibling modules: `from .sibling import ...`"
- [ ] "Use absolute imports for SDK modules: `from startd8.x.y import ...`"
- [ ] Provide list of existing sibling modules and their exports

**Environment readiness**:
- [ ] Package `__init__.py` exists
- [ ] Sibling modules that the task description references actually exist
- [ ] Parent package is importable

**Post-generation validation**:
- [ ] Relative imports reference modules that exist (or are being created in this batch)
- [ ] No circular imports with siblings

#### `python-test`
**Pre-generation constraints**:
- [ ] "Use pytest conventions (functions starting with `test_`, classes with `Test`)"
- [ ] "Use fixtures from conftest.py: {list available fixtures}"
- [ ] "Mock external dependencies — do not make real API calls"
- [ ] Provide the source module's public API (class names, function signatures)

**Environment readiness**:
- [ ] Source module under test exists and is importable
- [ ] conftest.py fixtures are scannable
- [ ] Test directory exists

**Post-generation validation**:
- [ ] All imports from source module resolve
- [ ] Test functions are named `test_*`
- [ ] No hardcoded API keys or external service URLs

#### `config-toml` / `config-yaml`
**Pre-generation constraints**:
- [ ] "Preserve existing sections — only add/modify specified keys"
- [ ] Provide current file content as context

**Post-generation validation**:
- [ ] Output is valid TOML/YAML
- [ ] Existing keys not removed unless explicitly requested

### Available Dependencies Scanner

Scan once per workflow run, cache for duration:

```python
def scan_available_deps(project_root: Path) -> set[str]:
    """Return set of importable package names."""
    # 1. Parse pyproject.toml [project.dependencies]
    # 2. Parse pyproject.toml [project.optional-dependencies]
    # 3. Scan .venv/lib/pythonX.Y/site-packages/ for installed packages
    # 4. Include stdlib modules
    # 5. Include project's own packages (src/startd8/*)
    return available
```

This enables the constraint: "Only import from: {available_deps}". The LLM can still use any package, but the constraint steers it away from unavailable ones.

### Architecture

```
PrimeContractorWorkflow.develop_feature(feature)
    │
    ├── pre_flight_validation(feature)          ← existing (size check)
    │
    ├── domain_preflight(feature)               ← NEW
    │   ├── detect_domain(target_path)
    │   ├── run_environment_checks(domain, target_path)
    │   │   └── create dirs, verify packages, scan deps
    │   └── build_prompt_constraints(domain, target_path, available_deps)
    │       └── returns list of constraint strings
    │
    ├── code_generator.generate(
    │       task=feature.description,
    │       context={
    │           'feature_name': ...,
    │           'target_file': ...,
    │           'output_constraint': ...,        ← existing (our fix today)
    │           'domain_constraints': [...],      ← NEW (from domain_preflight)
    │           'available_imports': [...],        ← NEW
    │           'existing_code': '...',            ← NEW (current target content)
    │       },
    │   )
    │
    ├── post_generation_validation(domain, generated_code)  ← NEW
    │   ├── check_forbidden_imports(code, domain)
    │   ├── check_dependency_availability(code, available_deps)
    │   └── check_definition_ordering(code)     ← catches functions-after-classes
    │
    └── integrate_feature(feature)              ← existing
        └── IntegrationCheckpoint.run_all()     ← existing (syntax/import/lint/test)
```

### Constraint Injection Point

The `output_constraint` string we added today is the seed of this system. It's a single hardcoded constraint. The domain preflight generalizes it:

```python
# Today (hardcoded):
gen_context['output_constraint'] = 'Output a single Python module...'

# Future (domain-driven):
domain = detect_domain(feature.target_files[0])
checklist = get_checklist(domain)
constraints = checklist.build_prompt_constraints(
    target_path=feature.target_files[0],
    available_deps=self._available_deps,
    existing_siblings=scan_siblings(target_path),
)
gen_context['domain_constraints'] = constraints
```

### Post-Generation Validators

Lightweight AST-based checks that run after the LLM produces code but before the merge strategy touches the target:

1. **Import validator**: Parse imports, check against available deps
2. **Relative import detector**: Flag `from .x import` in single-module domain
3. **Definition order checker**: Ensure names used in `Field(default_factory=X)` are defined above
4. **Merge damage detector**: After merge, re-validate that definition ordering is preserved

These are cheap (AST parse, no subprocess) and catch issues that the import checkpoint would find anyway — but earlier, with better error messages, and with the option to auto-fix.

## Priority Order for Implementation

1. **Available deps scanner** — highest leverage, prevents tiktoken-class errors across all domains
2. **Domain detection + prompt constraints** — generalizes our hardcoded `output_constraint`
3. **Post-generation import validator** — catches errors before merge can make them worse
4. **Definition order checker** — catches the functions-after-classes pattern
5. **Merge damage detector** — post-merge validation of ordering invariants

## Open Questions

- Should failed domain pre-flight block generation (strict) or just warn and inject constraints (advisory)?
- Should the available deps list include dev dependencies or just runtime?
- How to handle tasks that intentionally introduce new dependencies (e.g., PI-003 legitimately needs token counting — should it suggest `tiktoken` as an optional dep or use the existing heuristic)?
- Should post-generation validators attempt auto-fix (reorder functions, replace imports) or just fail with actionable messages?

## Relationship to Existing Components

- **PI-004 (Pre-Flight Checks)**: The artisan workflow's pre-flight is about workspace/git/env readiness. This proposal is about code-generation-specific constraints. They're complementary — PI-004 runs once at workflow start, domain preflight runs per-feature.
- **IntegrationCheckpoint**: Existing post-integration validation. Domain preflight is the pre-generation counterpart.
- **`output_constraint` in develop_feature()**: The seed implementation. Domain preflight replaces and generalizes it.
