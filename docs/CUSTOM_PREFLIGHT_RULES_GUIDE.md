# Custom Preflight Rules Guide

## Overview

Preflight rules are the extensibility mechanism of the StartD8 Domain Preflight system. Before the Artisan Contractor or PrimeContractor generates code for a task, the `DomainPreflightWorkflow` classifies the target file into a domain (Python module, test file, config file, etc.) and then evaluates all registered preflight rules against it. Each rule can contribute:

- **Environment checks** -- readiness signals (PASS, WARN, FAIL, SKIP) that flag issues before generation starts
- **Prompt constraints** -- text injected into the LLM prompt to steer code generation
- **Validators** -- named validator functions that run on generated code before merge

Custom rules let you encode project-specific, team-specific, or domain-specific constraints that the built-in rules do not cover. Examples include enforcing internal coding standards, checking for proprietary library availability, or injecting domain-specific LLM prompt constraints.

## Quick Start

Here is the minimal code to create and register a custom preflight rule:

```python
# my_rules.py
from startd8.workflows.builtin.preflight_rules import (
    PreflightRule,
    RuleContext,
    RuleContribution,
    preflight_rule,
    ALL_DOMAINS,
)
from startd8.workflows.builtin.domain_preflight_models import (
    CheckStatus,
    EnvironmentCheck,
)


@preflight_rule(domains=ALL_DOMAINS, priority=100)
class ReadmeExistsRule(PreflightRule):
    """Check that a README exists in the project root."""

    rule_id = "readme_exists"

    def evaluate(self, ctx: RuleContext):
        readme = ctx.project_root / "README.md"
        if readme.exists():
            return RuleContribution(checks=[
                EnvironmentCheck(
                    check_name="readme_exists",
                    status=CheckStatus.PASS,
                    message="README.md found in project root",
                )
            ])
        return RuleContribution(checks=[
            EnvironmentCheck(
                check_name="readme_exists",
                status=CheckStatus.WARN,
                message="No README.md in project root",
                detail="Consider adding a README for project documentation",
            )
        ])
```

Import this module before calling `PreflightRuleRegistry.discover()` (or use entry-point registration, described below) and the rule is active.


## Architecture

### PreflightRuleRegistry

`PreflightRuleRegistry` is a thread-safe singleton that holds all registered rules. It uses a class-level lock and class-level dictionaries, so there is exactly one registry per process.

Source: `src/startd8/workflows/builtin/preflight_rules/_registry.py`

Key methods:

| Method | Purpose |
|--------|---------|
| `register(rule)` | Register a `PreflightRule` instance. Warns on duplicate `rule_id`. |
| `discover(force=False)` | Import built-in rules, then load entry-point rules. Idempotent unless `force=True`. |
| `evaluate_all(ctx)` | Filter rules by domain, sort by priority, evaluate each, merge contributions. |
| `get_rule(rule_id)` | Look up a single rule by its id. |
| `list_rules()` | Return all registered rule ids. |
| `clear()` | Remove all rules (testing only). |

### Discovery Order

1. **Built-in rules** -- The registry explicitly imports and instantiates all built-in rule classes from the `rules_*.py` modules.
2. **Entry-point rules** -- The registry scans the `startd8.preflight_rules` entry-point group via `importlib.metadata`. Each entry point is loaded, instantiated, and registered.

Built-in rules are always registered first. If a third-party entry point uses the same `rule_id` as a built-in rule, it will overwrite the built-in (with a logged warning).

### Evaluation Pipeline

When `evaluate_all(ctx)` is called:

1. `discover()` is called (idempotent).
2. All rules whose `domains` set contains `ctx.domain` are selected.
3. Selected rules are sorted by `priority` (ascending -- lower numbers run first).
4. Each rule's `evaluate(ctx)` is called. Exceptions are caught and logged; they do not abort evaluation.
5. Non-`None` contributions are merged into a single `RuleContribution` (lists are extended, dicts are updated).

```
  All registered rules
        |
  [filter: ctx.domain in rule.domains]
        |
  [sort by priority ascending]
        |
  [evaluate each -> RuleContribution | None]
        |
  [merge all contributions]
        |
  Final RuleContribution (checks + constraints + validators + validator_fns)
```


## Creating a Rule

### Step 1: Define Your Rule Class

Every custom rule extends `PreflightRule` (defined in `src/startd8/workflows/builtin/preflight_rules/_base.py`).

Required:

- **`rule_id`** (property or class attribute) -- A unique string identifier. Use snake_case. Examples: `"readme_exists"`, `"internal_api_version_check"`, `"no_print_statements"`.
- **`evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]`** -- The rule logic. Return a `RuleContribution` to contribute checks/constraints/validators, or `None` to contribute nothing.

Optional:

- **`domains`** -- A `FrozenSet[TaskDomain]` controlling which file types this rule applies to. Defaults to `ALL_DOMAINS` (every file type). Can be overridden on the class or via the `@preflight_rule()` decorator.
- **`priority`** -- An integer controlling execution order. Defaults to `100`. Lower values run earlier. Conventions: `10`=early checks, `50`=environment checks, `100`=default/constraints, `150`=validators, `200`=late/cleanup.

```python
from startd8.workflows.builtin.preflight_rules import (
    PreflightRule,
    RuleContext,
    RuleContribution,
    PYTHON_DOMAINS,
)


class NoPrintStatementsRule(PreflightRule):
    """Inject a constraint forbidding print() in production code."""

    rule_id = "no_print_statements"
    domains = PYTHON_DOMAINS
    priority = 100

    def evaluate(self, ctx: RuleContext):
        return RuleContribution(
            constraints=["Do not use print() -- use logging.getLogger(__name__) instead"],
        )
```

### Step 2: Understanding RuleContext

Every call to `evaluate()` receives a `RuleContext` -- a frozen (immutable) dataclass with everything the rule needs to inspect the environment.

Source: `src/startd8/workflows/builtin/preflight_rules/_base.py`

```python
@dataclass(frozen=True)
class RuleContext:
    target_file: str            # Relative path, e.g. "src/mylib/models.py"
    target_path: Path           # Absolute: project_root / target_file
    target_dir: Path            # target_path.parent
    project_root: Path          # Absolute path to project root
    domain: TaskDomain          # Classified domain for this target file
    available_deps: AvailableDeps  # Discovered dependencies
```

**Fields in detail:**

| Field | Type | Description |
|-------|------|-------------|
| `target_file` | `str` | The relative file path being generated (e.g., `"src/mylib/utils.py"`). |
| `target_path` | `Path` | Absolute path: `project_root / target_file`. May not exist yet if the file is being created. |
| `target_dir` | `Path` | Parent directory of `target_path`. Useful for checking siblings, `__init__.py`, etc. |
| `project_root` | `Path` | Absolute path to the project root directory. |
| `domain` | `TaskDomain` | The domain classification for this target file (see Domain Constants below). |
| `available_deps` | `AvailableDeps` | Discovered dependency information (runtime, optional, stdlib, project, installed). |

**`AvailableDeps`** (source: `src/startd8/workflows/builtin/domain_preflight_models.py`):

```python
@dataclass
class AvailableDeps:
    runtime: Set[str]               # Runtime dependencies from pyproject.toml
    optional: Dict[str, Set[str]]   # Optional dependency groups
    stdlib: Set[str]                # Standard library modules
    project: Set[str]               # Project's own packages
    installed: Set[str]             # Currently installed packages

    @property
    def all_importable(self) -> Set[str]:
        """Union of all importable package names."""
```

### Step 3: Returning RuleContribution

`RuleContribution` is a mutable dataclass with four fields. Return an instance to contribute to the preflight result. Return `None` to skip (contribute nothing).

Source: `src/startd8/workflows/builtin/preflight_rules/_base.py`

```python
@dataclass
class RuleContribution:
    checks: List[EnvironmentCheck] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    validators: List[str] = field(default_factory=list)
    validator_fns: Dict[str, Callable] = field(default_factory=dict)
```

#### checks: `List[EnvironmentCheck]`

Environment readiness checks with a status and message. These surface in preflight reports.

```python
from startd8.workflows.builtin.domain_preflight_models import (
    CheckStatus,
    EnvironmentCheck,
)

EnvironmentCheck(
    check_name="my_check",          # Unique name for this check
    status=CheckStatus.PASS,        # PASS | WARN | FAIL | SKIP
    message="Everything looks good", # Human-readable summary
    detail="Optional extra context", # Optional detail string
)
```

Status semantics:
- `PASS` -- Check passed; no issues.
- `WARN` -- Non-blocking issue detected; generation proceeds but the LLM is informed.
- `FAIL` -- Blocking issue; downstream consumers may abort generation.
- `SKIP` -- Check was not applicable or could not be evaluated.

#### constraints: `List[str]`

Plain-text strings injected into the LLM prompt as generation constraints. The LLM sees these as instructions it should follow when generating code.

```python
RuleContribution(
    constraints=[
        "All database queries must use parameterized statements",
        "Do not import from the deprecated mylib.legacy module",
    ],
)
```

#### validators: `List[str]`

Names of post-generation validators that should be applied to the generated code. These are referenced by name in `domain_checklist.py` and matched against `validator_fns`.

```python
RuleContribution(
    validators=["no_sql_injection", "no_deprecated_imports"],
)
```

#### validator_fns: `Dict[str, Callable]`

Actual validator function implementations keyed by name. These are the functions that `domain_checklist.py` calls to validate generated code before merge.

```python
def _validate_no_sql_injection(code: str, enrichment) -> list:
    issues = []
    if "execute(" in code and "?" not in code and "%s" not in code:
        issues.append({
            "validator": "no_sql_injection",
            "message": "Possible SQL injection: raw string in execute()",
            "line": 0,
        })
    return issues

RuleContribution(
    validator_fns={"no_sql_injection": _validate_no_sql_injection},
)
```


### Step 4: Registration

There are three ways to register a rule.

#### Method 1: `@preflight_rule()` Decorator (Simplest)

The decorator instantiates the class and registers it immediately on import. This is the recommended approach for rules defined in your own codebase.

```python
from startd8.workflows.builtin.preflight_rules import preflight_rule, PreflightRule

@preflight_rule(domains=ALL_DOMAINS, priority=100)
class MyRule(PreflightRule):
    rule_id = "my_rule"

    def evaluate(self, ctx):
        ...
```

The decorator accepts optional `domains` and `priority` arguments that override the class defaults. If you omit them, the class-level values are used.

**Important**: The decorator fires on import. If you use `PreflightRuleRegistry.clear()` in tests and then re-import, the decorator will not re-fire because Python's module cache prevents re-execution. Use Method 2 or the `_import_builtin_rules()` pattern for test scenarios.

#### Method 2: `PreflightRuleRegistry.register()` (Programmatic)

For dynamic registration or when you need control over instantiation:

```python
from startd8.workflows.builtin.preflight_rules import PreflightRuleRegistry

rule = MyRule()
PreflightRuleRegistry.register(rule)
```

This is useful when:
- You want to register rules conditionally
- You need to pass constructor arguments
- You are working in a test where you called `clear()` first

#### Method 3: Entry-Point Discovery (Third-Party Packages)

For rules distributed as separate Python packages. See the dedicated section below.


## Entry-Point Registration (Third-Party Packages)

If you are publishing a preflight rule as part of a separate Python package (not inside the StartD8 SDK repo), use setuptools entry points.

### pyproject.toml Configuration

In your package's `pyproject.toml`:

```toml
[project.entry-points."startd8.preflight_rules"]
my_rule = "my_package.rules:MyRule"
another_rule = "my_package.rules:AnotherRule"
```

Each entry maps a name (used for logging/debugging) to a `module:ClassName` reference. The class must be a subclass of `PreflightRule`.

### How It Works

1. When `PreflightRuleRegistry.discover()` is called, it scans the `startd8.preflight_rules` entry-point group using `importlib.metadata.entry_points()`.
2. Each entry point is loaded (`ep.load()` returns the class).
3. The class is instantiated with no arguments (`rule_class()`).
4. The instance is registered via `PreflightRuleRegistry.register()`.
5. If loading fails, a warning is logged and discovery continues with the next entry point.

### Complete Third-Party Example

Package structure:

```
my-preflight-rules/
  pyproject.toml
  src/
    my_preflight_rules/
      __init__.py
      rules.py
```

`pyproject.toml`:

```toml
[project]
name = "my-preflight-rules"
version = "0.1.0"
dependencies = ["startd8>=0.4.0"]

[project.entry-points."startd8.preflight_rules"]
license_header = "my_preflight_rules.rules:LicenseHeaderRule"
```

`src/my_preflight_rules/rules.py`:

```python
from startd8.workflows.builtin.preflight_rules import (
    PreflightRule,
    RuleContext,
    RuleContribution,
    PYTHON_DOMAINS,
)
from startd8.workflows.builtin.domain_preflight_models import (
    CheckStatus,
    EnvironmentCheck,
)


class LicenseHeaderRule(PreflightRule):
    """Inject a constraint requiring a license header in all Python files."""

    rule_id = "license_header"
    domains = PYTHON_DOMAINS
    priority = 200  # Late -- runs after other constraints

    def evaluate(self, ctx: RuleContext):
        return RuleContribution(
            constraints=[
                "Include the Apache 2.0 license header comment at the top of the file"
            ],
        )
```

After installing the package (`pip install -e .` or `pip install my-preflight-rules`), the rule will be discovered automatically.

### StartD8 pyproject.toml Reference

The SDK's own `pyproject.toml` has a placeholder for third-party rules:

```toml
[project.entry-points."startd8.preflight_rules"]
# Third-party preflight rules can register here:
# my_rule = "my_package.rules:MyRule"
```

Source: `pyproject.toml` (line 98)


## Domain Constants

The `_base.py` module provides three pre-built domain sets for convenience:

```python
from startd8.workflows.builtin.preflight_rules import (
    ALL_DOMAINS,      # All 8 TaskDomain values
    PYTHON_DOMAINS,   # PYTHON_SINGLE_MODULE, PYTHON_PACKAGE_MODULE, PYTHON_TEST
    CONFIG_DOMAINS,   # CONFIG_TOML, CONFIG_YAML, CONFIG_JSON
)
```

### TaskDomain Enum Values

Source: `src/startd8/workflows/builtin/domain_preflight_models.py`

| Value | String | Description |
|-------|--------|-------------|
| `PYTHON_SINGLE_MODULE` | `"python-single-module"` | Standalone `.py` file not inside a package |
| `PYTHON_PACKAGE_MODULE` | `"python-package-module"` | `.py` file inside a package (has `__init__.py`) |
| `PYTHON_TEST` | `"python-test"` | Test file (typically `test_*.py` in `tests/`) |
| `CONFIG_TOML` | `"config-toml"` | TOML configuration file |
| `CONFIG_YAML` | `"config-yaml"` | YAML configuration file |
| `CONFIG_JSON` | `"config-json"` | JSON configuration file |
| `NON_PYTHON` | `"non-python"` | Non-Python file (Markdown, shell script, etc.) |
| `UNKNOWN` | `"unknown"` | Could not be classified |

### Custom Domain Sets

You can create your own domain sets:

```python
from startd8.workflows.builtin.domain_preflight_models import TaskDomain

# Only Python tests
TEST_ONLY = frozenset({TaskDomain.PYTHON_TEST})

# Python production code (not tests)
PROD_PYTHON = frozenset({
    TaskDomain.PYTHON_SINGLE_MODULE,
    TaskDomain.PYTHON_PACKAGE_MODULE,
})
```


## Available Helpers

The `_helpers.py` module provides utility functions that your rules can use.

Source: `src/startd8/workflows/builtin/preflight_rules/_helpers.py`

### Functions

```python
from startd8.workflows.builtin.preflight_rules._helpers import (
    parse_relative_imports,
    file_has_pattern,
    scan_optional_dep_guards,
    scan_patch_paths,
    normalize_dep_name,
)
```

| Function | Signature | Description |
|----------|-----------|-------------|
| `parse_relative_imports(file_path)` | `(Path) -> List[str]` | Extract relative import target module names from a Python file. Returns names from `from .X import ...` statements. |
| `file_has_pattern(file_path, pattern)` | `(Path, str) -> bool` | Check if a file's content matches a regex pattern. Returns `False` if the file does not exist or cannot be read. |
| `scan_optional_dep_guards(file_path)` | `(Path) -> List[str]` | Find package names guarded by `try: import X / except ImportError` patterns. |
| `scan_patch_paths(file_path)` | `(Path) -> List[str]` | Extract `mock.patch()` / `@patch()` target strings from a test file. |
| `normalize_dep_name(name)` | `(str) -> str` | Normalize a dependency name: strip version specs, lowercase, replace `-` with `_`. |

### Constants

```python
from startd8.workflows.builtin.preflight_rules._helpers import (
    STDLIB_FALLBACK,
    STANDALONE_SCRIPT_DIRS,
    LOGGER_RESERVED_FIELDS,
)
```

| Constant | Type | Description |
|----------|------|-------------|
| `STDLIB_FALLBACK` | `Set[str]` | Standard library module names for Python < 3.10 (where `sys.stdlib_module_names` is unavailable). |
| `STANDALONE_SCRIPT_DIRS` | `Set[str]` | Directory names conventionally used for standalone scripts: `scripts`, `bin`, `tools`, `examples`, `benchmarks`, `utils_scripts`. |
| `LOGGER_RESERVED_FIELDS` | `Set[str]` | Python `LogRecord` field names that must not be used as `extra=` keys in logging calls. |


## Writing Post-Generation Validators

Validators are functions that inspect generated code after the LLM produces it but before it is merged into the project. They catch issues that prompt constraints alone cannot prevent.

### Validator Function Signature

```python
def my_validator(code: str, enrichment) -> list:
    """
    Args:
        code: The generated source code as a string.
        enrichment: A TaskEnrichment object with domain, constraints, etc.

    Returns:
        A list of issue dicts. Empty list means no issues found.
        Each dict should have:
            - "validator": str  -- the validator name
            - "message": str    -- human-readable description of the issue
            - "line": int       -- line number (0 if unknown)
    """
    issues = []
    # ... inspection logic ...
    return issues
```

### Connecting Validators to Rules

A validator rule contributes both the validator name (in `validators`) and the function implementation (in `validator_fns`). It should also expose the function via a `_validator_fns` class attribute so the registry can discover it for fallback lookups.

```python
import ast
from startd8.workflows.builtin.preflight_rules import (
    preflight_rule,
    PreflightRule,
    RuleContext,
    RuleContribution,
    PYTHON_DOMAINS,
)


def _validate_no_bare_except(code: str, enrichment) -> list:
    """Flag bare 'except:' clauses that catch KeyboardInterrupt."""
    issues = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return issues

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            issues.append({
                "validator": "no_bare_except",
                "message": "Bare 'except:' clause catches KeyboardInterrupt -- use specific exception types",
                "line": node.lineno,
            })
    return issues


@preflight_rule(domains=PYTHON_DOMAINS, priority=150)
class NoBareExceptValidatorRule(PreflightRule):
    """Contribute the no_bare_except validator function."""

    rule_id = "no_bare_except_validator"
    _validator_fns = {"no_bare_except": _validate_no_bare_except}

    def evaluate(self, ctx: RuleContext):
        return RuleContribution(
            validators=["no_bare_except"],
            validator_fns={"no_bare_except": _validate_no_bare_except},
        )
```

### Pattern Notes

- Define the validator function at module level, not as a method. This keeps it testable in isolation.
- Set `_validator_fns` as a class attribute so `PreflightRuleRegistry.get_validator_fn()` can find it without running `evaluate_all()`.
- Use `ast.parse()` for structural analysis when possible. It is more reliable than regex for Python code inspection.
- Return an empty list (not `None`) when no issues are found.
- Include the `line` field in issue dicts even if approximate -- it helps developers locate problems.


## Testing Your Rule

### Test Setup Pattern

Use pytest's `tmp_path` fixture to create isolated filesystem structures. The helper pattern from the SDK's own tests is recommended.

Source: `tests/unit/test_preflight_rules_builtin.py`

```python
import pytest
from pathlib import Path
from typing import Optional

from startd8.workflows.builtin.domain_preflight_models import (
    AvailableDeps,
    CheckStatus,
    TaskDomain,
)
from startd8.workflows.builtin.preflight_rules import (
    RuleContext,
    RuleContribution,
)


def _make_deps(**kw) -> AvailableDeps:
    """Create an AvailableDeps with sensible defaults."""
    defaults = dict(
        runtime={"httpx", "rich"},
        stdlib={"os", "sys"},
        project={"mylib"},
    )
    defaults.update(kw)
    return AvailableDeps(**defaults)


def _ctx(
    tmp_path: Path,
    target_file: str = "src/foo.py",
    domain: TaskDomain = TaskDomain.PYTHON_SINGLE_MODULE,
    deps: Optional[AvailableDeps] = None,
) -> RuleContext:
    """Build a RuleContext for testing."""
    target_path = tmp_path / target_file
    return RuleContext(
        target_file=target_file,
        target_path=target_path,
        target_dir=target_path.parent,
        project_root=tmp_path,
        domain=domain,
        available_deps=deps or _make_deps(),
    )
```

### Example Test Class

```python
from my_rules import ReadmeExistsRule


class TestReadmeExistsRule:
    def test_pass_when_readme_exists(self, tmp_path):
        (tmp_path / "README.md").write_text("# My Project\n")
        rule = ReadmeExistsRule()
        result = rule.evaluate(_ctx(tmp_path))
        assert result is not None
        assert len(result.checks) == 1
        assert result.checks[0].status == CheckStatus.PASS
        assert result.checks[0].check_name == "readme_exists"

    def test_warn_when_readme_missing(self, tmp_path):
        rule = ReadmeExistsRule()
        result = rule.evaluate(_ctx(tmp_path))
        assert result is not None
        assert result.checks[0].status == CheckStatus.WARN

    def test_domains(self):
        rule = ReadmeExistsRule()
        # ALL_DOMAINS means it applies to every domain
        assert TaskDomain.PYTHON_SINGLE_MODULE in rule.domains
        assert TaskDomain.CONFIG_JSON in rule.domains
```

### Testing Validator Functions

Test validator functions directly, independent of the rule:

```python
def test_no_bare_except_validator():
    code_with_bare_except = """\
try:
    risky()
except:
    pass
"""
    issues = _validate_no_bare_except(code_with_bare_except, None)
    assert len(issues) == 1
    assert issues[0]["validator"] == "no_bare_except"
    assert issues[0]["line"] == 3

def test_no_bare_except_clean():
    clean_code = """\
try:
    risky()
except ValueError:
    pass
"""
    issues = _validate_no_bare_except(clean_code, None)
    assert len(issues) == 0
```

### Testing with the Registry

If you need to test registry integration:

```python
from startd8.workflows.builtin.preflight_rules import PreflightRuleRegistry


class TestRegistryIntegration:
    def setup_method(self):
        PreflightRuleRegistry.clear()

    def teardown_method(self):
        PreflightRuleRegistry.clear()

    def test_rule_is_registered(self):
        from my_rules import MyRule
        PreflightRuleRegistry.register(MyRule())
        assert "my_rule" in PreflightRuleRegistry.list_rules()

    def test_evaluate_all_includes_rule(self, tmp_path):
        from my_rules import MyRule
        PreflightRuleRegistry.register(MyRule())

        ctx = _ctx(tmp_path)
        merged = PreflightRuleRegistry.evaluate_all(ctx)
        # Note: evaluate_all calls discover() which loads built-in rules too
        assert any(c.check_name == "my_check" for c in merged.checks)
```


## Complete Examples

### Example 1: Simple Environment Check Rule

Check that a `.env` file exists in the project root when generating Python code:

```python
from startd8.workflows.builtin.preflight_rules import (
    preflight_rule,
    PreflightRule,
    RuleContext,
    RuleContribution,
    PYTHON_DOMAINS,
)
from startd8.workflows.builtin.domain_preflight_models import (
    CheckStatus,
    EnvironmentCheck,
)


@preflight_rule(domains=PYTHON_DOMAINS, priority=50)
class DotEnvExistsRule(PreflightRule):
    """Check that a .env file exists for environment variable configuration."""

    rule_id = "dotenv_exists"

    def evaluate(self, ctx: RuleContext):
        dotenv = ctx.project_root / ".env"
        if dotenv.exists():
            return RuleContribution(checks=[
                EnvironmentCheck(
                    check_name="dotenv_exists",
                    status=CheckStatus.PASS,
                    message=".env file found in project root",
                )
            ])
        # Not blocking -- just informational
        return RuleContribution(checks=[
            EnvironmentCheck(
                check_name="dotenv_exists",
                status=CheckStatus.SKIP,
                message="No .env file in project root",
                detail="Environment variables may need to be set via other means",
            )
        ])
```

### Example 2: Constraint-Injecting Rule

Inject project-specific coding standards into the LLM prompt:

```python
from startd8.workflows.builtin.preflight_rules import (
    preflight_rule,
    PreflightRule,
    RuleContext,
    RuleContribution,
    PYTHON_DOMAINS,
)
from startd8.workflows.builtin.preflight_rules._helpers import file_has_pattern


@preflight_rule(domains=PYTHON_DOMAINS, priority=100)
class InternalCodingStandardsRule(PreflightRule):
    """Inject internal coding standards as LLM prompt constraints."""

    rule_id = "internal_coding_standards"

    def evaluate(self, ctx: RuleContext):
        constraints = [
            "Use type hints on all public function signatures",
            "Use dataclasses or Pydantic models for structured data -- not plain dicts",
            "Raise specific exception types -- never raise bare Exception",
        ]

        # Add async constraint if the file uses async patterns
        if ctx.target_path.exists() and file_has_pattern(ctx.target_path, r"\basync\b"):
            constraints.append(
                "Existing code uses async/await -- preserve async patterns"
            )

        return RuleContribution(constraints=constraints)
```

### Example 3: Post-Generation Validator Rule

Validate that generated code does not contain hardcoded secrets:

```python
import ast
import re

from startd8.workflows.builtin.preflight_rules import (
    preflight_rule,
    PreflightRule,
    RuleContext,
    RuleContribution,
    PYTHON_DOMAINS,
)


SECRET_PATTERNS = [
    (r"(?i)(api[_-]?key|secret|password|token)\s*=\s*['\"][^'\"]{8,}['\"]",
     "Possible hardcoded secret"),
    (r"sk-[a-zA-Z0-9]{20,}",
     "Possible OpenAI API key"),
    (r"ghp_[a-zA-Z0-9]{36}",
     "Possible GitHub personal access token"),
]


def _validate_no_hardcoded_secrets(code: str, enrichment) -> list:
    """Detect possible hardcoded secrets in generated code."""
    issues = []
    for i, line in enumerate(code.splitlines(), start=1):
        for pattern, description in SECRET_PATTERNS:
            if re.search(pattern, line):
                issues.append({
                    "validator": "no_hardcoded_secrets",
                    "message": f"{description} on line {i}",
                    "line": i,
                })
    return issues


@preflight_rule(domains=PYTHON_DOMAINS, priority=150)
class NoHardcodedSecretsValidatorRule(PreflightRule):
    """Contribute a validator that detects hardcoded secrets."""

    rule_id = "no_hardcoded_secrets_validator"
    _validator_fns = {"no_hardcoded_secrets": _validate_no_hardcoded_secrets}

    def evaluate(self, ctx: RuleContext):
        return RuleContribution(
            validators=["no_hardcoded_secrets"],
            validator_fns={"no_hardcoded_secrets": _validate_no_hardcoded_secrets},
        )
```

### Example 4: Combined Check + Constraint + Validator Rule

A rule that checks for a project convention, injects a constraint, and validates the output:

```python
import re

from startd8.workflows.builtin.preflight_rules import (
    preflight_rule,
    PreflightRule,
    RuleContext,
    RuleContribution,
)
from startd8.workflows.builtin.domain_preflight_models import (
    CheckStatus,
    EnvironmentCheck,
    TaskDomain,
)


def _validate_docstring_present(code: str, enrichment) -> list:
    """Check that all public functions and classes have docstrings."""
    issues = []
    try:
        import ast
        tree = ast.parse(code)
    except SyntaxError:
        return issues

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name.startswith("_"):
                continue
            if not (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                issues.append({
                    "validator": "docstring_present",
                    "message": f"Public {type(node).__name__} '{node.name}' missing docstring",
                    "line": node.lineno,
                })
    return issues


_PROD_PYTHON = frozenset({
    TaskDomain.PYTHON_SINGLE_MODULE,
    TaskDomain.PYTHON_PACKAGE_MODULE,
})


@preflight_rule(domains=_PROD_PYTHON, priority=120)
class DocstringRequiredRule(PreflightRule):
    """Enforce docstrings on all public functions and classes."""

    rule_id = "docstring_required"
    _validator_fns = {"docstring_present": _validate_docstring_present}

    def evaluate(self, ctx: RuleContext):
        checks = []
        # Check if existing file follows the convention
        if ctx.target_path.exists():
            try:
                import ast
                tree = ast.parse(ctx.target_path.read_text(encoding="utf-8"))
                public_count = 0
                documented_count = 0
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        if not node.name.startswith("_"):
                            public_count += 1
                            if (node.body and isinstance(node.body[0], ast.Expr)
                                    and isinstance(node.body[0].value, ast.Constant)):
                                documented_count += 1
                if public_count > 0:
                    ratio = documented_count / public_count
                    status = CheckStatus.PASS if ratio >= 0.8 else CheckStatus.WARN
                    checks.append(EnvironmentCheck(
                        check_name="docstring_coverage",
                        status=status,
                        message=f"Docstring coverage: {documented_count}/{public_count} ({ratio:.0%})",
                    ))
            except Exception:
                pass

        return RuleContribution(
            checks=checks,
            constraints=[
                "All public functions and classes must have docstrings",
                "Use Google-style docstrings with Args/Returns/Raises sections",
            ],
            validators=["docstring_present"],
            validator_fns={"docstring_present": _validate_docstring_present},
        )
```


## Built-in Rules Reference

The following 24 rules are shipped with StartD8 v0.4.0. They are defined in the `src/startd8/workflows/builtin/preflight_rules/` directory.

### Common Rules (`rules_common.py`)

| Rule ID | Priority | Domains | Description |
|---------|----------|---------|-------------|
| `parent_dir_exists` | 10 | ALL | Check that the parent directory of the target file exists. |
| `logger_reserved_fields` | 200 | PYTHON | Detect logging usage and inject a constraint to avoid reserved `LogRecord` field names as `extra=` keys. |

### Python Single Module Rules (`rules_python_single.py`)

| Rule ID | Priority | Domains | Description |
|---------|----------|---------|-------------|
| `not_in_package` | 50 | SINGLE | Verify target is not inside a package (no `__init__.py` in directory). |
| `optional_dep_guards_single` | 60 | SINGLE | Detect optional imports guarded by `try/except ImportError` that are not declared in `pyproject.toml`. |
| `single_module_constraints` | 100 | SINGLE | Inject prompt constraints (no relative imports, importable deps list) and validators for single-module domain. |

### Python Package Module Rules (`rules_python_package.py`)

| Rule ID | Priority | Domains | Description |
|---------|----------|---------|-------------|
| `init_py_exists` | 50 | PACKAGE | Check that `__init__.py` exists in the target directory. |
| `parent_package_importable` | 55 | PACKAGE | Check that the parent package has `__init__.py` (is importable). |
| `circular_imports` | 60 | PACKAGE | Detect potential circular imports between sibling modules. |
| `optional_dep_guards_package` | 65 | PACKAGE | Detect optional imports not declared in project deps (package module variant). |
| `pydantic_property_confusion` | 70 | PACKAGE | Warn when sibling modules use `@property`, which could be confused with Pydantic model constructor kwargs. |
| `package_module_constraints` | 100 | PACKAGE | Inject prompt constraints (relative imports for siblings, absolute for SDK) and validators for package-module domain. |

### Python Test Rules (`rules_python_test.py`)

| Rule ID | Priority | Domains | Description |
|---------|----------|---------|-------------|
| `source_module_exists` | 50 | TEST | Check that the source module under test exists in `src/`. |
| `test_dir_exists` | 55 | TEST | Check that the test directory exists. |
| `conftest_scannable` | 60 | TEST | Check for `conftest.py` in the test directory. |
| `patch_path_valid` | 65 | TEST | Detect stale `mock.patch()` target paths and inject a constraint to verify them. |
| `thread_aware_teardown` | 70 | TEST | Detect when the source module uses `threading` and inject a constraint for proper teardown. |
| `test_constraints` | 100 | TEST | Inject pytest conventions, available fixtures from `conftest.py`, and test validators. |

### Config Rules (`rules_config.py`)

| Rule ID | Priority | Domains | Description |
|---------|----------|---------|-------------|
| `config_file_valid` | 50 | CONFIG | Validate that an existing config file is parseable (JSON, TOML, or YAML). |
| `entry_point_reinstall` | 60 | TOML only | Warn that `pyproject.toml` entry-point changes require `pip install -e .` to take effect. |
| `config_constraints` | 100 | CONFIG | Inject constraints to preserve existing sections and validators for format correctness. |

### Validator Rules (`rules_validators.py`)

| Rule ID | Priority | Domains | Description |
|---------|----------|---------|-------------|
| `no_relative_imports_validator` | 150 | SINGLE | Contribute the `no_relative_imports` validator function (flags relative imports in single modules). |
| `deps_available_validator` | 150 | SINGLE | Contribute the `deps_available` validator function (checks imported packages against available deps). |
| `definition_ordering_validator` | 150 | SINGLE | Contribute the `definition_ordering` validator function (ensures `default_factory` references are defined before use). |
| `merge_damage_detector` | 200 | PYTHON | Contribute the `merge_damage` validator (detects duplicate definitions and ordering violations after merge). |

**Domain abbreviations used above:**
- ALL = `ALL_DOMAINS` (all 8 `TaskDomain` values)
- PYTHON = `PYTHON_DOMAINS` (`PYTHON_SINGLE_MODULE`, `PYTHON_PACKAGE_MODULE`, `PYTHON_TEST`)
- SINGLE = `PYTHON_SINGLE_MODULE` only
- PACKAGE = `PYTHON_PACKAGE_MODULE` only
- TEST = `PYTHON_TEST` only
- CONFIG = `CONFIG_DOMAINS` (`CONFIG_TOML`, `CONFIG_YAML`, `CONFIG_JSON`)
- TOML only = `CONFIG_TOML` only


## Troubleshooting

### Rule not being evaluated

1. Check that `domains` includes the domain of the target file being processed.
2. Verify the rule is registered: `PreflightRuleRegistry.list_rules()` should include your `rule_id`.
3. For entry-point rules, ensure the package is installed in the active environment (`pip install -e .`).
4. Check logs for discovery warnings: the registry logs at `DEBUG` level for successful registration and `WARNING` for failures.

### Duplicate rule_id warning

Each `rule_id` must be unique across all registered rules. If you see `"Overwriting existing preflight rule: X"`, two rules share the same id. Rename one of them.

### Decorator not re-firing after clear()

The `@preflight_rule` decorator runs on import. After `PreflightRuleRegistry.clear()`, Python's module cache means re-importing the module will not re-execute the decorator. In tests, use `PreflightRuleRegistry.register(MyRule())` explicitly after `clear()`.

### Validator function not found

Ensure the rule contributes both the validator name in `validators` and the function in `validator_fns`. Also set the `_validator_fns` class attribute for `get_validator_fn()` fallback lookups.
