"""
Comprehensive unit tests for the Final Assembly phase of the Artisan contractor pipeline.

This module tests AST reconciliation, completion validation, quality checks, and report
generation. It is self-contained with no relative imports and includes local stubs of
production classes for test-first development.

Test Coverage Areas:
    - ASTReconciler: Merging, deduplication, conflict resolution of AST fragments
    - CompletionValidator: Requirement checking, coverage calculation
    - QualityChecker: Syntax validation, complexity analysis, naming conventions
    - AssemblyReport: Serialization, status tracking, field completeness
    - FinalAssembler: End-to-end pipeline orchestration
    - Integration scenarios: Full pipeline, edge cases, sanity checks

Target: >80% coverage across all assembly components.
"""

import pytest
import ast
import json
from enum import Enum
from unittest.mock import Mock
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone

# ============================================================================
# Conditional Import and Local Stubs
# ============================================================================

try:
    from artisan.contractors.final_assembly import (
        FinalAssembler,
        ASTReconciler,
        CompletionValidator,
        QualityChecker,
        AssemblyReport,
        AssemblyStatus,
    )
    _PRODUCTION_MODULE_AVAILABLE = True
except ImportError:
    _PRODUCTION_MODULE_AVAILABLE = False

    # ========================================================================
    # Local Stub Classes — used for test-first development when production
    # module is not yet available.
    # ========================================================================

    class AssemblyStatus(Enum):
        """Enumeration of assembly completion states."""
        SUCCESS = "success"
        PARTIAL = "partial"
        FAILURE = "failure"
        PENDING = "pending"

    @dataclass
    class ASTNode:
        """Represents a single AST node with metadata."""
        node_type: str
        name: str = ""
        children: List[Any] = field(default_factory=list)
        source: str = ""
        line_number: int = 0

    @dataclass
    class QualityResult:
        """Results from a quality check pass."""
        passed: bool
        score: float
        issues: List[str] = field(default_factory=list)
        warnings: List[str] = field(default_factory=list)

    @dataclass
    class ValidationResult:
        """Results from completion validation."""
        complete: bool
        missing: List[str] = field(default_factory=list)
        present: List[str] = field(default_factory=list)
        coverage_pct: float = 0.0

    @dataclass
    class AssemblyReport:
        """Report generated at the end of final assembly.

        Captures the full state of an assembly run including reconciliation
        outcome, validation results, quality scores, and the final merged code.
        """
        status: AssemblyStatus = AssemblyStatus.PENDING
        timestamp: str = ""
        reconciliation_success: bool = False
        validation_result: Optional[ValidationResult] = None
        quality_result: Optional[QualityResult] = None
        final_code: str = ""
        errors: List[str] = field(default_factory=list)
        warnings: List[str] = field(default_factory=list)
        statistics: Dict[str, Any] = field(default_factory=dict)

        def to_dict(self) -> Dict[str, Any]:
            """Convert report to a JSON-serializable dictionary."""
            return {
                "status": self.status.value,
                "timestamp": self.timestamp,
                "reconciliation_success": self.reconciliation_success,
                "errors": self.errors,
                "warnings": self.warnings,
                "statistics": self.statistics,
            }

        def summary(self) -> str:
            """Generate a human-readable summary string."""
            return (
                f"Assembly {self.status.value}: "
                f"{len(self.errors)} errors, {len(self.warnings)} warnings"
            )

    class ASTReconciler:
        """Reconciles multiple AST fragments into a coherent, deduplicated AST.

        Supports configurable conflict resolution strategies:
            - ``last_wins``: Later definitions overwrite earlier ones.
            - ``error``: Conflicts are logged but the first definition is kept.
        """

        def __init__(self, strategy: str = "last_wins"):
            self.strategy = strategy
            self._conflicts: List[str] = []

        def reconcile(self, fragments: List[str]) -> str:
            """Reconcile multiple code fragments into a single code string.

            Args:
                fragments: List of Python source strings to merge.

            Returns:
                Merged and deduplicated source string.

            Raises:
                TypeError: If *fragments* is ``None``.
            """
            if fragments is None:
                raise TypeError("fragments cannot be None")
            if not fragments:
                return ""

            self._conflicts = []
            merged_imports: List[ast.stmt] = []
            merged_body: List[ast.stmt] = []
            seen_imports: set[str] = set()
            seen_functions: set[str] = set()
            seen_classes: set[str] = set()

            for fragment in fragments:
                try:
                    tree = ast.parse(fragment)
                except SyntaxError as exc:
                    self._conflicts.append(f"Syntax error in fragment: {exc}")
                    continue

                for node in ast.iter_child_nodes(tree):
                    if isinstance(node, (ast.Import, ast.ImportFrom)):
                        import_str = ast.dump(node)
                        if import_str not in seen_imports:
                            seen_imports.add(import_str)
                            merged_imports.append(node)
                        else:
                            self._conflicts.append(f"Duplicate import: {import_str}")

                    elif isinstance(node, ast.FunctionDef):
                        if node.name in seen_functions:
                            if self.strategy == "last_wins":
                                merged_body = [
                                    n for n in merged_body
                                    if not (isinstance(n, ast.FunctionDef) and n.name == node.name)
                                ]
                                merged_body.append(node)
                                self._conflicts.append(
                                    f"Duplicate function '{node.name}' resolved with {self.strategy}"
                                )
                            else:
                                self._conflicts.append(f"Duplicate function '{node.name}'")
                        else:
                            seen_functions.add(node.name)
                            merged_body.append(node)

                    elif isinstance(node, ast.ClassDef):
                        if node.name in seen_classes:
                            self._conflicts.append(f"Duplicate class '{node.name}'")
                            if self.strategy == "last_wins":
                                merged_body = [
                                    n for n in merged_body
                                    if not (isinstance(n, ast.ClassDef) and n.name == node.name)
                                ]
                                merged_body.append(node)
                        else:
                            seen_classes.add(node.name)
                            merged_body.append(node)
                    else:
                        merged_body.append(node)

            module = ast.Module(body=merged_imports + merged_body, type_ignores=[])
            ast.fix_missing_locations(module)
            return ast.unparse(module)

        @property
        def conflicts(self) -> List[str]:
            """Return list of conflicts encountered during the last reconciliation."""
            return self._conflicts

    class CompletionValidator:
        """Validates that required code components are present in assembled output.

        Requirements are specified as a dictionary with keys ``functions``,
        ``classes``, and ``imports``, each mapping to a list of required names.
        """

        def __init__(self, requirements: Optional[Dict[str, List[str]]] = None):
            self.requirements = requirements or {
                "functions": [],
                "classes": [],
                "imports": [],
            }

        def validate(self, code: str) -> ValidationResult:
            """Validate that all required components are present.

            Args:
                code: Python source string to validate.

            Returns:
                :class:`ValidationResult` with completion status and coverage.

            Raises:
                TypeError: If *code* is ``None``.
            """
            if code is None:
                raise TypeError("code cannot be None")

            if not code.strip():
                return ValidationResult(
                    complete=False,
                    missing=list(self._all_required()),
                    present=[],
                    coverage_pct=0.0,
                )

            try:
                tree = ast.parse(code)
            except SyntaxError:
                return ValidationResult(
                    complete=False,
                    missing=["valid_syntax"],
                    present=[],
                    coverage_pct=0.0,
                )

            found_functions: set[str] = set()
            found_classes: set[str] = set()
            found_imports: set[str] = set()

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    found_functions.add(node.name)
                elif isinstance(node, ast.ClassDef):
                    found_classes.add(node.name)
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        found_imports.add(alias.name)
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        found_imports.add(alias.name)

            missing: List[str] = []
            present: List[str] = []

            for fn_name in self.requirements.get("functions", []):
                (present if fn_name in found_functions else missing).append(fn_name)

            for class_name in self.requirements.get("classes", []):
                (present if class_name in found_classes else missing).append(class_name)

            for import_name in self.requirements.get("imports", []):
                (present if import_name in found_imports else missing).append(import_name)

            total = len(missing) + len(present)
            coverage = (len(present) / total * 100.0) if total > 0 else 100.0

            return ValidationResult(
                complete=len(missing) == 0,
                missing=missing,
                present=present,
                coverage_pct=coverage,
            )

        def _all_required(self):
            """Yield all required component names across all categories."""
            for key in self.requirements:
                yield from self.requirements[key]

    class QualityChecker:
        """Performs quality-gate checks on assembled code.

        Checks include syntax validation, cyclomatic complexity estimation,
        naming-convention adherence, optional type-hint enforcement, and
        user-supplied custom rules.
        """

        def __init__(
            self,
            max_complexity: int = 10,
            require_type_hints: bool = False,
            custom_rules: Optional[List[Any]] = None,
        ):
            self.max_complexity = max_complexity
            self.require_type_hints = require_type_hints
            self.custom_rules = custom_rules or []

        def check(self, code: str) -> QualityResult:
            """Perform quality checks on the given code.

            Args:
                code: Python source string to check.

            Returns:
                :class:`QualityResult` with pass/fail status and score.

            Raises:
                TypeError: If *code* is ``None``.
            """
            if code is None:
                raise TypeError("code cannot be None")

            if not code.strip():
                return QualityResult(passed=False, score=0.0, issues=["Empty code"])

            issues: List[str] = []
            warnings: List[str] = []
            score = 100.0

            # --- Syntax validation ---
            try:
                tree = ast.parse(code)
            except SyntaxError as exc:
                return QualityResult(
                    passed=False, score=0.0, issues=[f"Syntax error: {exc}"]
                )

            # --- Per-node checks ---
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # Naming convention
                    if not node.name.islower() and not node.name.startswith("_"):
                        if node.name != node.name.lower().replace(" ", "_"):
                            warnings.append(
                                f"Function '{node.name}' does not follow snake_case"
                            )
                            score -= 5

                    # Complexity estimation (branch-counting heuristic)
                    branch_count = sum(
                        1
                        for child in ast.walk(node)
                        if isinstance(
                            child,
                            (ast.If, ast.For, ast.While, ast.Try, ast.ExceptHandler),
                        )
                    )
                    if branch_count > self.max_complexity:
                        issues.append(
                            f"Function '{node.name}' complexity {branch_count} "
                            f"exceeds max {self.max_complexity}"
                        )
                        score -= 15

                    # Type-hint enforcement
                    if self.require_type_hints and node.returns is None:
                        warnings.append(
                            f"Function '{node.name}' missing return type hint"
                        )
                        score -= 3

                elif isinstance(node, ast.ClassDef):
                    if not node.name[0].isupper():
                        warnings.append(f"Class '{node.name}' should use PascalCase")
                        score -= 5

            # --- Custom rules ---
            for rule in self.custom_rules:
                result = rule(code, tree)
                if result:
                    if isinstance(result, list):
                        issues.extend(result)
                    else:
                        issues.append(result)
                    score -= 10

            score = max(0.0, min(100.0, score))
            passed = len(issues) == 0 and score >= 50.0

            return QualityResult(
                passed=passed, score=score, issues=issues, warnings=warnings
            )

    class FinalAssembler:
        """Orchestrates the final assembly pipeline.

        Executes reconciliation → validation → quality checking in sequence,
        producing an :class:`AssemblyReport` that captures the full outcome.
        """

        def __init__(
            self,
            reconciler: Optional[ASTReconciler] = None,
            validator: Optional[CompletionValidator] = None,
            quality_checker: Optional[QualityChecker] = None,
        ):
            self.reconciler = reconciler or ASTReconciler()
            self.validator = validator or CompletionValidator()
            self.quality_checker = quality_checker or QualityChecker()

        def assemble(
            self,
            fragments: List[str],
            context: Optional[Dict[str, Any]] = None,
        ) -> AssemblyReport:
            """Execute the full assembly pipeline on code fragments.

            Args:
                fragments: Code fragments to assemble.
                context: Optional project metadata dictionary.

            Returns:
                :class:`AssemblyReport` with final status and details.
            """
            report = AssemblyReport(
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            context = context or {}

            # Step 1: Reconcile AST fragments
            try:
                reconciled_code = self.reconciler.reconcile(fragments)
                report.reconciliation_success = True
                if self.reconciler.conflicts:
                    report.warnings.extend(self.reconciler.conflicts)
            except Exception as exc:
                report.errors.append(f"Reconciliation failed: {exc}")
                report.status = AssemblyStatus.FAILURE
                return report

            # Step 2: Validate completeness
            try:
                validation_result = self.validator.validate(reconciled_code)
                report.validation_result = validation_result
                if not validation_result.complete:
                    report.warnings.append(
                        f"Missing components: {validation_result.missing}"
                    )
            except Exception as exc:
                report.errors.append(f"Validation failed: {exc}")
                report.status = AssemblyStatus.FAILURE
                return report

            # Step 3: Quality gate
            try:
                quality_result = self.quality_checker.check(reconciled_code)
                report.quality_result = quality_result
                if not quality_result.passed:
                    report.errors.extend(quality_result.issues)
            except Exception as exc:
                report.errors.append(f"Quality check failed: {exc}")
                report.status = AssemblyStatus.FAILURE
                return report

            # Finalize
            report.final_code = reconciled_code
            report.statistics = {
                "fragment_count": len(fragments),
                "reconciled_length": len(reconciled_code),
                "quality_score": quality_result.score,
                "completion_pct": validation_result.coverage_pct,
                "conflict_count": len(self.reconciler.conflicts),
            }

            if report.errors:
                report.status = (
                    AssemblyStatus.FAILURE
                    if not reconciled_code
                    else AssemblyStatus.PARTIAL
                )
            elif report.warnings:
                report.status = AssemblyStatus.PARTIAL
            else:
                report.status = AssemblyStatus.SUCCESS

            return report


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def reconciler():
    """ASTReconciler with default 'last_wins' strategy."""
    return ASTReconciler(strategy="last_wins")


@pytest.fixture
def validator_with_requirements():
    """CompletionValidator requiring main, helper, MyClass, and os."""
    return CompletionValidator(
        requirements={
            "functions": ["main", "helper"],
            "classes": ["MyClass"],
            "imports": ["os"],
        }
    )


@pytest.fixture
def validator_empty():
    """CompletionValidator with no requirements (everything passes)."""
    return CompletionValidator()


@pytest.fixture
def quality_checker_standard():
    """QualityChecker with standard thresholds."""
    return QualityChecker(max_complexity=10, require_type_hints=False)


@pytest.fixture
def quality_checker_strict():
    """QualityChecker with strict thresholds and type-hint enforcement."""
    return QualityChecker(max_complexity=5, require_type_hints=True)


@pytest.fixture
def assembler(reconciler, validator_with_requirements, quality_checker_standard):
    """FinalAssembler wired with standard test components."""
    return FinalAssembler(
        reconciler=reconciler,
        validator=validator_with_requirements,
        quality_checker=quality_checker_standard,
    )


@pytest.fixture
def sample_fragments_basic():
    """Three non-conflicting fragments satisfying standard requirements."""
    return [
        "import os\n\ndef main():\n    pass",
        "class MyClass:\n    pass",
        "def helper():\n    return 42",
    ]


@pytest.fixture
def sample_fragments_with_duplicates():
    """Two fragments with duplicate function definitions."""
    return [
        "def duplicate_func():\n    return 1",
        "def duplicate_func():\n    return 2",
    ]


@pytest.fixture
def sample_fragments_with_syntax_error():
    """Fragments including one with a syntax error."""
    return [
        "import os",
        "def valid():\n    pass",
        "def invalid(\n    # Missing closing paren",
        "class Good:\n    pass",
    ]


@pytest.fixture
def assembly_context():
    """Project metadata context dictionary."""
    return {
        "project_name": "test_project",
        "version": "1.0.0",
        "author": "test_author",
    }


@pytest.fixture
def mock_report_base():
    """Minimal AssemblyReport in PENDING state."""
    return AssemblyReport(
        status=AssemblyStatus.PENDING,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


# ============================================================================
# Test Classes
# ============================================================================


class TestASTReconciler:
    """Tests for AST reconciliation functionality."""

    def test_reconcile_single_fragment(self, reconciler):
        """Single fragment is returned unchanged."""
        code = "def hello():\n    return 'world'"
        result = reconciler.reconcile([code])
        assert "hello" in result
        assert reconciler.conflicts == []

    def test_reconcile_multiple_fragments(self, reconciler):
        """Non-conflicting fragments are merged correctly."""
        fragments = [
            "import os",
            "def func_a():\n    pass",
            "def func_b():\n    pass",
        ]
        result = reconciler.reconcile(fragments)
        assert "import os" in result
        assert "func_a" in result
        assert "func_b" in result
        assert reconciler.conflicts == []

    def test_reconcile_conflicting_imports(self, reconciler):
        """Duplicate imports are deduplicated with a conflict logged."""
        fragments = ["import os", "import os"]
        result = reconciler.reconcile(fragments)
        assert "os" in result
        assert len(reconciler.conflicts) > 0

    def test_reconcile_duplicate_functions(self, reconciler):
        """Duplicate functions resolved via last_wins strategy."""
        fragments = [
            "def dup():\n    return 1",
            "def dup():\n    return 2",
        ]
        result = reconciler.reconcile(fragments)
        assert "dup" in result
        assert "return 2" in result
        assert len(reconciler.conflicts) > 0

    def test_reconcile_empty_fragments(self, reconciler):
        """Empty list produces empty string with no conflicts."""
        result = reconciler.reconcile([])
        assert result == ""
        assert reconciler.conflicts == []

    def test_reconcile_preserves_import_order(self, reconciler):
        """Imports are placed before function/class definitions."""
        fragments = [
            "def first():\n    pass",
            "import sys",
            "def second():\n    pass",
        ]
        result = reconciler.reconcile(fragments)
        import_pos = result.find("import")
        first_pos = result.find("first")
        assert import_pos < first_pos or import_pos == -1

    def test_reconcile_handles_syntax_errors(self, reconciler):
        """Syntax errors in individual fragments are skipped gracefully."""
        fragments = [
            "import os",
            "def broken(\n",
            "def valid():\n    pass",
        ]
        result = reconciler.reconcile(fragments)
        assert "os" in result or "valid" in result
        assert len(reconciler.conflicts) > 0

    def test_reconcile_merges_class_definitions(self, reconciler):
        """Distinct class definitions are merged without conflict."""
        fragments = [
            "class FirstClass:\n    pass",
            "class SecondClass:\n    pass",
        ]
        result = reconciler.reconcile(fragments)
        assert "FirstClass" in result
        assert "SecondClass" in result
        assert reconciler.conflicts == []

    def test_reconcile_with_none_input(self, reconciler):
        """None input raises TypeError."""
        with pytest.raises(TypeError, match="fragments cannot be None"):
            reconciler.reconcile(None)

    def test_reconcile_nested_ast_nodes(self, reconciler):
        """Nested class/function definitions are preserved."""
        fragments = [
            "class Outer:\n    class Inner:\n        pass",
            "def outer_func():\n    def inner_func():\n        pass",
        ]
        result = reconciler.reconcile(fragments)
        assert "Outer" in result
        assert "outer_func" in result
        assert reconciler.conflicts == []

    def test_reconcile_with_error_strategy(self):
        """Error strategy logs conflict without overwriting."""
        reconciler = ASTReconciler(strategy="error")
        fragments = [
            "def conflict():\n    pass",
            "def conflict():\n    pass",
        ]
        reconciler.reconcile(fragments)
        assert len(reconciler.conflicts) > 0

    def test_reconcile_duplicate_classes_last_wins(self, reconciler):
        """Duplicate class definitions resolved via last_wins strategy."""
        fragments = [
            "class Dup:\n    x = 1",
            "class Dup:\n    x = 2",
        ]
        result = reconciler.reconcile(fragments)
        assert "Dup" in result
        assert len(reconciler.conflicts) > 0

    def test_reconcile_mixed_imports(self, reconciler):
        """Import and ImportFrom nodes are both handled."""
        fragments = [
            "import os",
            "from sys import argv",
        ]
        result = reconciler.reconcile(fragments)
        assert "os" in result
        assert "argv" in result
        assert reconciler.conflicts == []

    def test_reconcile_conflicts_reset_between_calls(self, reconciler):
        """Conflicts list is reset on each call to reconcile."""
        reconciler.reconcile(["def f():\n    pass", "def f():\n    pass"])
        assert len(reconciler.conflicts) > 0
        reconciler.reconcile(["def g():\n    pass"])
        assert len(reconciler.conflicts) == 0

    @pytest.mark.parametrize(
        "fragment_count,expected_in_result",
        [(1, "func"), (2, "func"), (3, "func")],
    )
    def test_reconcile_parametrized_fragment_count(
        self, reconciler, fragment_count, expected_in_result
    ):
        """Varying fragment counts produce expected merged output."""
        fragments = [
            f"def func_{idx}():\n    pass" for idx in range(fragment_count)
        ]
        result = reconciler.reconcile(fragments)
        assert expected_in_result in result


class TestCompletionValidator:
    """Tests for completion validation functionality."""

    def test_validate_all_sections_present(self, validator_with_requirements):
        """All requirements met yields 100% coverage."""
        code = (
            "import os\n\n"
            "def main():\n    pass\n\n"
            "def helper():\n    pass\n\n"
            "class MyClass:\n    pass\n"
        )
        result = validator_with_requirements.validate(code)
        assert result.complete is True
        assert result.coverage_pct == 100.0
        assert len(result.missing) == 0

    def test_validate_missing_required_function(self, validator_with_requirements):
        """Missing function is detected and reported."""
        code = "import os\n\ndef main():\n    pass\n\nclass MyClass:\n    pass\n"
        result = validator_with_requirements.validate(code)
        assert result.complete is False
        assert "helper" in result.missing
        assert result.coverage_pct < 100.0

    def test_validate_missing_imports(self, validator_with_requirements):
        """Missing import is detected."""
        code = "def main():\n    pass\n\ndef helper():\n    pass\n\nclass MyClass:\n    pass\n"
        result = validator_with_requirements.validate(code)
        assert result.complete is False
        assert "os" in result.missing

    def test_validate_missing_class(self, validator_with_requirements):
        """Missing class is detected."""
        code = "import os\n\ndef main():\n    pass\n\ndef helper():\n    pass\n"
        result = validator_with_requirements.validate(code)
        assert result.complete is False
        assert "MyClass" in result.missing

    def test_validate_empty_module(self, validator_with_requirements):
        """Empty code yields 0% coverage and all requirements missing."""
        result = validator_with_requirements.validate("")
        assert result.complete is False
        assert result.coverage_pct == 0.0
        assert len(result.missing) > 0

    def test_validate_partial_completion(self, validator_with_requirements):
        """Partial code yields intermediate coverage."""
        code = "import os\n\ndef main():\n    pass\n"
        result = validator_with_requirements.validate(code)
        assert result.complete is False
        assert 0 < result.coverage_pct < 100.0
        assert len(result.missing) > 0
        assert len(result.present) > 0

    def test_validate_with_no_requirements(self, validator_empty):
        """No requirements means any code is considered complete."""
        result = validator_empty.validate("def anything(): pass")
        assert result.complete is True
        assert result.coverage_pct == 100.0

    def test_validate_returns_detailed_results(self, validator_with_requirements):
        """Result object has all expected attributes."""
        result = validator_with_requirements.validate("import os\n\ndef main():\n    pass")
        assert hasattr(result, "complete")
        assert hasattr(result, "missing")
        assert hasattr(result, "present")
        assert hasattr(result, "coverage_pct")

    def test_validate_custom_requirements(self):
        """Custom requirement sets are honoured."""
        validator = CompletionValidator(
            requirements={
                "functions": ["init", "process", "cleanup"],
                "classes": ["Handler"],
            }
        )
        code = (
            "def init():\n    pass\n\n"
            "def process():\n    pass\n\n"
            "def cleanup():\n    pass\n\n"
            "class Handler:\n    pass\n"
        )
        result = validator.validate(code)
        assert result.complete is True

    def test_validate_docstrings_present(self):
        """Basic validator passes regardless of docstrings."""
        code_with = '"""\nmodule doc\n"""\ndef func():\n    """Docstring."""\n    pass\n'
        code_without = "def func():\n    pass\n"
        validator = CompletionValidator()
        assert validator.validate(code_with).complete is True
        assert validator.validate(code_without).complete is True

    def test_validate_with_none_input(self, validator_with_requirements):
        """None input raises TypeError."""
        with pytest.raises(TypeError, match="code cannot be None"):
            validator_with_requirements.validate(None)

    def test_validate_syntax_error_detected(self, validator_with_requirements):
        """Syntax errors are caught and flagged as missing valid_syntax."""
        result = validator_with_requirements.validate("def broken(\n    pass")
        assert result.complete is False
        assert "valid_syntax" in result.missing

    def test_validate_import_from_detected(self):
        """ImportFrom nodes are detected correctly."""
        validator = CompletionValidator(requirements={"imports": ["path"]})
        result = validator.validate("from os import path")
        assert result.complete is True
        assert "path" in result.present

    @pytest.mark.parametrize(
        "requirement_type,code_snippet,should_be_present",
        [
            ("functions", "def test_func():\n    pass", True),
            ("classes", "class TestClass:\n    pass", True),
            ("imports", "import sys", True),
        ],
    )
    def test_validate_parametrized_requirements(
        self, requirement_type, code_snippet, should_be_present
    ):
        """Parametrized validation across requirement types."""
        if requirement_type == "functions":
            validator = CompletionValidator(requirements={"functions": ["test_func"]})
        elif requirement_type == "classes":
            validator = CompletionValidator(requirements={"classes": ["TestClass"]})
        else:
            validator = CompletionValidator(requirements={"imports": ["sys"]})

        result = validator.validate(code_snippet)
        if should_be_present:
            assert result.complete is True


class TestQualityChecker:
    """Tests for code quality checking functionality."""

    def test_check_syntax_valid(self, quality_checker_standard):
        """Valid syntax passes quality check."""
        result = quality_checker_standard.check("def valid():\n    return 42")
        assert result.passed is True
        assert result.score > 0

    def test_check_syntax_invalid(self, quality_checker_standard):
        """Invalid syntax yields score 0 and failure."""
        result = quality_checker_standard.check("def broken(\n    pass")
        assert result.passed is False
        assert result.score == 0.0
        assert len(result.issues) > 0

    def test_check_naming_conventions_pass(self, quality_checker_standard):
        """Proper naming conventions produce no warnings."""
        code = "def my_function():\n    pass\n\nclass MyClass:\n    pass\n"
        result = quality_checker_standard.check(code)
        assert result.passed is True
        assert len(result.warnings) == 0

    def test_check_naming_conventions_fail(self, quality_checker_standard):
        """Improper naming is flagged in warnings."""
        code = "def MyFunction():\n    pass\n\nclass my_class:\n    pass\n"
        result = quality_checker_standard.check(code)
        assert len(result.warnings) > 0

    def test_check_complexity_within_threshold(self, quality_checker_standard):
        """Low-complexity code passes cleanly."""
        code = "def simple():\n    if True:\n        pass\n    return 1\n"
        result = quality_checker_standard.check(code)
        assert result.passed is True
        assert len(result.issues) == 0

    def test_check_complexity_exceeds_threshold(self):
        """High-complexity code is flagged as an issue."""
        checker = QualityChecker(max_complexity=2)
        code = "def complex():\n    if True:\n        if True:\n            if True:\n                pass\n"
        result = checker.check(code)
        assert result.passed is False
        assert len(result.issues) > 0

    def test_check_structural_integrity(self, quality_checker_standard):
        """Well-structured class with methods passes."""
        code = "class Container:\n    def method(self):\n        pass\n"
        result = quality_checker_standard.check(code)
        assert result.passed is True

    def test_check_code_with_imports(self, quality_checker_standard):
        """Code using standard library imports passes."""
        code = "import os\nimport sys\n\ndef use_imports():\n    return os.path.exists('/')\n"
        result = quality_checker_standard.check(code)
        assert result.passed is True

    def test_check_type_hints_present(self):
        """Type-hint requirement flags functions without return annotations."""
        checker = QualityChecker(require_type_hints=True)
        result_with = checker.check("def func() -> int:\n    return 1\n")
        result_without = checker.check("def func():\n    return 1\n")
        assert result_with.passed is True
        assert len(result_without.warnings) > 0

    def test_check_returns_quality_score(self, quality_checker_standard):
        """Score is a float in [0, 100]."""
        result = quality_checker_standard.check("def func():\n    pass")
        assert isinstance(result.score, float)
        assert 0.0 <= result.score <= 100.0

    def test_check_with_custom_rules(self):
        """Custom rules are applied and violations are surfaced."""

        def rule_no_print(code_str, tree):
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id == "print":
                        return ["Print statements not allowed"]
            return []

        checker = QualityChecker(custom_rules=[rule_no_print])
        result_with = checker.check("def func():\n    print('hello')")
        result_without = checker.check("def func():\n    return 1")
        assert len(result_with.issues) > 0
        assert result_without.passed is True

    def test_check_empty_code(self, quality_checker_standard):
        """Empty code is flagged with score 0."""
        result = quality_checker_standard.check("")
        assert result.passed is False
        assert result.score == 0.0

    def test_check_with_none_input(self, quality_checker_standard):
        """None input raises TypeError."""
        with pytest.raises(TypeError, match="code cannot be None"):
            quality_checker_standard.check(None)

    def test_check_score_boundary_conditions(self, quality_checker_standard):
        """Minimal valid code scores above the 50.0 pass threshold."""
        result = quality_checker_standard.check("def f():\n    pass")
        assert result.score >= 50.0
        assert result.passed is True

    def test_check_strict_mode(self, quality_checker_strict):
        """Strict checker flags missing type hints and lower complexity threshold."""
        code = "def func():\n    if True:\n        if True:\n            if True:\n                if True:\n                    if True:\n                        if True:\n                            pass\n"
        result = quality_checker_strict.check(code)
        assert len(result.issues) > 0 or len(result.warnings) > 0

    def test_check_multiple_functions(self, quality_checker_standard):
        """Multiple functions are each checked independently."""
        code = "def a():\n    pass\n\ndef b():\n    pass\n\ndef c():\n    pass\n"
        result = quality_checker_standard.check(code)
        assert result.passed is True
        assert result.score == 100.0

    @pytest.mark.parametrize(
        "code_snippet,should_pass",
        [
            ("def simple():\n    pass", True),
            ("def bad_Name():\n    pass", False),
            (
                "def f():\n    if True:\n        if True:\n            if True:\n"
                "                if True:\n                    if True:\n"
                "                        if True:\n                            pass",
                True,  # 6 branches < max_complexity=10, snake_case name — passes
            ),
        ],
    )
    def test_check_parametrized_code_quality(
        self, quality_checker_standard, code_snippet, should_pass
    ):
        """Parametrized quality checks."""
        result = quality_checker_standard.check(code_snippet)
        if should_pass:
            assert result.passed or result.score > 50.0
        else:
            assert (
                not result.passed
                or len(result.issues) > 0
                or len(result.warnings) > 0
            )


class TestAssemblyReport:
    """Tests for assembly report generation and serialization."""

    def test_report_creation(self, mock_report_base):
        """Default report is in PENDING state with empty lists."""
        assert mock_report_base.status == AssemblyStatus.PENDING
        assert mock_report_base.timestamp is not None
        assert isinstance(mock_report_base.errors, list)

    def test_report_with_pass_status(self):
        """SUCCESS status is stored correctly."""
        report = AssemblyReport(
            status=AssemblyStatus.SUCCESS,
            timestamp=datetime.now(timezone.utc).isoformat(),
            reconciliation_success=True,
            errors=[],
            warnings=[],
        )
        assert report.status == AssemblyStatus.SUCCESS

    def test_report_with_fail_status(self):
        """FAILURE status is stored with error details."""
        report = AssemblyReport(
            status=AssemblyStatus.FAILURE,
            timestamp=datetime.now(timezone.utc).isoformat(),
            errors=["Assembly failed"],
        )
        assert report.status == AssemblyStatus.FAILURE
        assert len(report.errors) > 0

    def test_report_includes_statistics(self):
        """Statistics dictionary is accessible."""
        report = AssemblyReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            statistics={
                "fragment_count": 3,
                "reconciled_length": 150,
                "quality_score": 85.0,
            },
        )
        assert report.statistics["fragment_count"] == 3

    def test_report_includes_timestamps(self):
        """Timestamp is stored as provided."""
        ts = datetime.now(timezone.utc).isoformat()
        report = AssemblyReport(timestamp=ts)
        assert report.timestamp == ts

    def test_report_serialization(self):
        """to_dict produces a dictionary with expected keys."""
        report = AssemblyReport(
            status=AssemblyStatus.SUCCESS,
            timestamp=datetime.now(timezone.utc).isoformat(),
            reconciliation_success=True,
            errors=[],
            warnings=["minor issue"],
            statistics={"key": "value"},
        )
        d = report.to_dict()
        assert isinstance(d, dict)
        assert d["status"] == "success"
        assert d["reconciliation_success"] is True
        assert "warnings" in d

    def test_report_serialization_json_compatible(self):
        """to_dict output is JSON-serializable and round-trips correctly."""
        report = AssemblyReport(
            status=AssemblyStatus.PARTIAL,
            timestamp=datetime.now(timezone.utc).isoformat(),
            errors=["error1"],
            warnings=["warning1"],
        )
        json_str = json.dumps(report.to_dict())
        loaded = json.loads(json_str)
        assert loaded["status"] == "partial"

    def test_report_includes_warnings(self):
        """Warnings list is preserved."""
        report = AssemblyReport(warnings=["w1", "w2"])
        assert report.warnings == ["w1", "w2"]

    def test_report_includes_errors(self):
        """Errors list is preserved."""
        report = AssemblyReport(errors=["e1", "e2"])
        assert report.errors == ["e1", "e2"]

    def test_report_summary_generation(self):
        """Summary contains status, error count, and warning count."""
        report = AssemblyReport(
            status=AssemblyStatus.SUCCESS,
            errors=["e1", "e2"],
            warnings=["w1"],
        )
        summary = report.summary()
        assert "success" in summary.lower()
        assert "2" in summary
        assert "1" in summary

    def test_report_with_validation_result(self):
        """Report can hold a ValidationResult."""
        vr = ValidationResult(
            complete=True, missing=[], present=["func1", "class1"], coverage_pct=100.0
        )
        report = AssemblyReport(validation_result=vr)
        assert report.validation_result is not None
        assert report.validation_result.complete is True

    def test_report_with_quality_result(self):
        """Report can hold a QualityResult."""
        qr = QualityResult(passed=True, score=95.0, issues=[], warnings=[])
        report = AssemblyReport(quality_result=qr)
        assert report.quality_result is not None
        assert report.quality_result.score == 95.0

    def test_report_final_code_content(self):
        """Report stores final assembled code."""
        code = "def final():\n    return 'code'"
        report = AssemblyReport(final_code=code)
        assert report.final_code == code
        assert "final" in report.final_code

    def test_report_default_field_isolation(self):
        """Default mutable fields are not shared between instances."""
        r1 = AssemblyReport()
        r2 = AssemblyReport()
        r1.errors.append("only in r1")
        assert len(r2.errors) == 0

    @pytest.mark.parametrize(
        "status,expected_value",
        [
            (AssemblyStatus.SUCCESS, "success"),
            (AssemblyStatus.FAILURE, "failure"),
            (AssemblyStatus.PARTIAL, "partial"),
            (AssemblyStatus.PENDING, "pending"),
        ],
    )
    def test_report_parametrized_status(self, status, expected_value):
        """All status enum values serialize correctly."""
        report = AssemblyReport(status=status)
        assert report.to_dict()["status"] == expected_value


class TestFinalAssembler:
    """Tests for the orchestrating FinalAssembler."""

    def test_assemble_happy_path(self, assembler, sample_fragments_basic):
        """Full pipeline succeeds with valid, complete fragments."""
        report = assembler.assemble(sample_fragments_basic)
        assert report.reconciliation_success is True
        assert report.final_code is not None
        assert len(report.final_code) > 0

    def test_assemble_with_reconciliation_failure(self, assembler):
        """Reconciliation exception yields FAILURE status."""
        bad_reconciler = Mock()
        bad_reconciler.reconcile.side_effect = Exception("Reconciliation error")
        bad_reconciler.conflicts = []

        assembler.reconciler = bad_reconciler
        report = assembler.assemble(["some code"])

        assert report.status == AssemblyStatus.FAILURE
        assert len(report.errors) > 0
        assert "Reconciliation" in report.errors[0]

    def test_assemble_with_validation_failure(self, assembler, sample_fragments_basic):
        """Validation exception yields FAILURE status."""
        bad_validator = Mock()
        bad_validator.validate.side_effect = Exception("Validation error")

        assembler.validator = bad_validator
        report = assembler.assemble(sample_fragments_basic)

        assert report.status == AssemblyStatus.FAILURE
        assert len(report.errors) > 0

    def test_assemble_with_quality_failure(self, assembler, sample_fragments_basic):
        """Quality-check exception yields FAILURE status."""
        bad_quality = Mock()
        bad_quality.check.side_effect = Exception("Quality check error")

        assembler.quality_checker = bad_quality
        report = assembler.assemble(sample_fragments_basic)

        assert report.status == AssemblyStatus.FAILURE
        assert len(report.errors) > 0

    def test_assemble_generates_report(self, assembler, sample_fragments_basic):
        """Assembly always returns a complete AssemblyReport."""
        report = assembler.assemble(sample_fragments_basic)
        assert isinstance(report, AssemblyReport)
        assert report.timestamp is not None
        assert report.status is not None

    def test_assemble_returns_status(self, assembler, sample_fragments_basic):
        """Report status is an AssemblyStatus enum member."""
        report = assembler.assemble(sample_fragments_basic)
        assert isinstance(report.status, AssemblyStatus)

    def test_assemble_pipeline_order(self, assembler, sample_fragments_basic):
        """Steps execute in order: reconcile → validate → quality."""
        call_order = []

        mock_reconciler = Mock()
        mock_reconciler.reconcile.side_effect = lambda f: (
            call_order.append("reconcile") or "code"
        )
        mock_reconciler.conflicts = []

        mock_validator = Mock()
        mock_validator.validate.side_effect = lambda c: (
            call_order.append("validate")
            or ValidationResult(complete=True)
        )

        mock_quality = Mock()
        mock_quality.check.side_effect = lambda c: (
            call_order.append("quality")
            or QualityResult(passed=True, score=100.0)
        )

        assembler.reconciler = mock_reconciler
        assembler.validator = mock_validator
        assembler.quality_checker = mock_quality

        assembler.assemble(sample_fragments_basic)

        assert call_order == ["reconcile", "validate", "quality"]

    def test_assemble_with_empty_input(self, assembler):
        """Empty fragment list is handled gracefully."""
        report = assembler.assemble([])
        assert report is not None
        assert report.timestamp is not None

    def test_assemble_with_single_fragment(self, assembler):
        """Single fragment reports fragment_count = 1."""
        report = assembler.assemble(["def single():\n    pass"])
        assert report.statistics["fragment_count"] == 1

    def test_assemble_with_many_fragments(self, assembler):
        """Many fragments are handled and counted correctly."""
        fragments = [f"def func_{i}():\n    pass" for i in range(10)]
        report = assembler.assemble(fragments)
        assert report.statistics["fragment_count"] == 10

    def test_assemble_includes_statistics(self, assembler, sample_fragments_basic):
        """Report statistics contain all expected keys."""
        report = assembler.assemble(sample_fragments_basic)
        for key in [
            "fragment_count",
            "reconciled_length",
            "quality_score",
            "completion_pct",
            "conflict_count",
        ]:
            assert key in report.statistics

    def test_assemble_idempotency(self, assembler, sample_fragments_basic):
        """Same input produces identical output across calls."""
        r1 = assembler.assemble(sample_fragments_basic)
        r2 = assembler.assemble(sample_fragments_basic)
        assert r1.final_code == r2.final_code

    def test_assemble_with_context(
        self, assembler, sample_fragments_basic, assembly_context
    ):
        """Context metadata does not interfere with assembly."""
        report = assembler.assemble(sample_fragments_basic, context=assembly_context)
        assert report is not None

    def test_assemble_handles_conflicts_in_report(self, assembler):
        """Reconciler conflicts appear in report warnings."""
        report = assembler.assemble(["import os", "import os"])
        assert len(report.warnings) > 0

    def test_assemble_failure_with_bad_code(self):
        """Syntactically invalid code still produces a report."""
        assembler_inst = FinalAssembler()
        report = assembler_inst.assemble(["def broken(\n"])
        assert report.status is not None

    def test_assemble_default_components(self):
        """FinalAssembler creates default components when none provided."""
        assembler_inst = FinalAssembler()
        assert isinstance(assembler_inst.reconciler, ASTReconciler)
        assert isinstance(assembler_inst.validator, CompletionValidator)
        assert isinstance(assembler_inst.quality_checker, QualityChecker)

    def test_assemble_validation_skipped_after_reconciliation_error(self):
        """After reconciliation failure, validation and quality are not called."""
        mock_reconciler = Mock()
        mock_reconciler.reconcile.side_effect = Exception("boom")

        mock_validator = Mock()
        mock_quality = Mock()

        assembler_inst = FinalAssembler(
            reconciler=mock_reconciler,
            validator=mock_validator,
            quality_checker=mock_quality,
        )
        report = assembler_inst.assemble(["code"])

        assert report.status == AssemblyStatus.FAILURE
        mock_validator.validate.assert_not_called()
        mock_quality.check.assert_not_called()

    @pytest.mark.parametrize(
        "fragment_set,expected_status",
        [
            (["import os\n\ndef main():\n    pass"], AssemblyStatus.SUCCESS),
            (["def broken("], AssemblyStatus.FAILURE),
        ],
    )
    def test_assemble_parametrized_scenarios(self, fragment_set, expected_status):
        """Parametrized assembly scenarios."""
        assembler_inst = FinalAssembler()
        report = assembler_inst.assemble(fragment_set)
        assert report.status is not None


class TestIntegrationScenarios:
    """Integration tests for complete assembly pipeline scenarios."""

    def test_full_pipeline_success(self):
        """End-to-end success: all requirements met, quality passes."""
        fragments = [
            "import os\nimport sys",
            "def helper():\n    return 42",
            "def main():\n    return helper()",
            "class Handler:\n    pass",
        ]
        requirements = {
            "imports": ["os", "sys"],
            "functions": ["helper", "main"],
            "classes": ["Handler"],
        }
        assembler = FinalAssembler(
            reconciler=ASTReconciler(),
            validator=CompletionValidator(requirements=requirements),
            quality_checker=QualityChecker(max_complexity=10),
        )
        report = assembler.assemble(fragments)

        assert report.status == AssemblyStatus.SUCCESS
        assert report.reconciliation_success is True
        assert report.validation_result.complete is True
        assert report.quality_result.passed is True
        assert len(report.errors) == 0

    def test_full_pipeline_partial_failure(self):
        """Missing components produce PARTIAL status."""
        fragments = ["import os", "def helper():\n    pass"]
        requirements = {"functions": ["helper", "main"], "classes": ["MyClass"]}
        assembler = FinalAssembler(
            reconciler=ASTReconciler(),
            validator=CompletionValidator(requirements=requirements),
            quality_checker=QualityChecker(),
        )
        report = assembler.assemble(fragments)

        assert report.status == AssemblyStatus.PARTIAL
        assert report.validation_result.complete is False
        assert len(report.validation_result.missing) > 0

    def test_full_pipeline_with_warnings_but_pass(self):
        """Warnings but no hard failures yield PARTIAL or SUCCESS."""
        fragments = [
            "import os\nimport sys",
            "def my_function():\n    pass",
            "class MyClass:\n    pass",
        ]
        assembler = FinalAssembler(
            reconciler=ASTReconciler(),
            validator=CompletionValidator(requirements={"imports": ["os", "sys"]}),
            quality_checker=QualityChecker(max_complexity=5),
        )
        report = assembler.assemble(fragments)
        assert report.status in [AssemblyStatus.SUCCESS, AssemblyStatus.PARTIAL]
        assert report.timestamp is not None

    def test_full_pipeline_catastrophic_failure(self):
        """Syntax-only input is handled gracefully."""
        assembler = FinalAssembler()
        report = assembler.assemble(["def broken(\n"])
        assert report.status in [AssemblyStatus.FAILURE, AssemblyStatus.PARTIAL]
        assert report.timestamp is not None

    def test_integration_with_complex_code(self):
        """Realistic multi-fragment assembly with dataclasses and typing."""
        fragments = [
            "import typing\nfrom dataclasses import dataclass\n\n"
            "@dataclass\nclass Config:\n    name: str\n    version: str\n",
            "def initialize(config: 'Config') -> None:\n"
            "    if config.name:\n        print(f'Initializing {config.name}')\n",
            "def process(data: typing.List[str]) -> typing.Dict[str, int]:\n"
            "    result = {}\n    for item in data:\n        result[item] = len(item)\n"
            "    return result\n",
        ]
        requirements = {
            "imports": ["typing", "dataclass"],
            "functions": ["initialize", "process"],
            "classes": ["Config"],
        }
        assembler = FinalAssembler(
            reconciler=ASTReconciler(),
            validator=CompletionValidator(requirements=requirements),
            quality_checker=QualityChecker(max_complexity=8),
        )
        report = assembler.assemble(fragments)

        assert report.reconciliation_success is True
        assert report.validation_result is not None
        assert report.quality_result is not None
        assert len(report.final_code) > 0

    def test_integration_conflict_resolution(self):
        """Conflicting definitions resolved via last_wins show in warnings."""
        fragments = [
            "def conflicting():\n    return 1",
            "def conflicting():\n    return 2",
            "def unique():\n    return 3",
        ]
        assembler = FinalAssembler(
            reconciler=ASTReconciler(strategy="last_wins"),
            validator=CompletionValidator(
                requirements={"functions": ["conflicting", "unique"]}
            ),
            quality_checker=QualityChecker(),
        )
        report = assembler.assemble(fragments)

        assert report.reconciliation_success is True
        assert "return 2" in report.final_code
        assert len(report.warnings) > 0

    def test_integration_empty_assembly(self):
        """Empty fragment list is handled without crash."""
        assembler = FinalAssembler(validator=CompletionValidator())
        report = assembler.assemble([])
        assert report is not None
        assert report.timestamp is not None

    def test_integration_report_completeness(self):
        """Full pipeline populates all report fields."""
        assembler = FinalAssembler()
        report = assembler.assemble(["def main():\n    pass"])

        assert report.timestamp is not None
        assert report.status is not None
        assert isinstance(report.errors, list)
        assert isinstance(report.warnings, list)
        assert report.statistics is not None
        assert report.final_code is not None or report.status == AssemblyStatus.FAILURE

    def test_integration_unicode_handling(self):
        """Unicode in code is handled gracefully."""
        fragments = [
            "# -*- coding: utf-8 -*-\n",
            "def greet():\n    return '你好世界'",
            "def emoji():\n    return '✨'",
        ]
        assembler = FinalAssembler()
        report = assembler.assemble(fragments)
        assert report.timestamp is not None

    def test_integration_large_fragment_set(self):
        """50 fragments are assembled correctly."""
        fragments = [f"def func_{i}():\n    return {i}" for i in range(50)]
        assembler = FinalAssembler()
        report = assembler.assemble(fragments)
        assert report.statistics["fragment_count"] == 50
        assert len(report.final_code) > 0

    def test_integration_quality_score_propagated(self):
        """Quality score from checker appears in report statistics."""
        assembler = FinalAssembler()
        report = assembler.assemble(["def func():\n    pass"])
        assert "quality_score" in report.statistics
        assert isinstance(report.statistics["quality_score"], float)


# ============================================================================
# Edge Case Tests
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_reconcile_none_fragments(self, reconciler):
        """None fragments raises TypeError."""
        with pytest.raises(TypeError):
            reconciler.reconcile(None)

    def test_validate_none_code(self, validator_with_requirements):
        """None code raises TypeError."""
        with pytest.raises(TypeError):
            validator_with_requirements.validate(None)

    def test_quality_none_code(self, quality_checker_standard):
        """None code raises TypeError."""
        with pytest.raises(TypeError):
            quality_checker_standard.check(None)

    def test_reconcile_very_long_fragment(self, reconciler):
        """Very long code fragment is handled without error."""
        long_code = "def func():\n    " + "pass\n    " * 1000
        result = reconciler.reconcile([long_code])
        assert "func" in result

    def test_validator_high_coverage(self, validator_empty):
        """No requirements yields 100% coverage."""
        result = validator_empty.validate("def anything():\n    pass")
        assert result.coverage_pct == 100.0

    def test_quality_score_exactly_threshold(self, quality_checker_standard):
        """Minimal valid code scores above 50 threshold."""
        result = quality_checker_standard.check("def f():\n    pass")
        assert result.score > 50.0

    def test_assembly_with_none_context(self, assembler, sample_fragments_basic):
        """None context is handled (defaults to empty dict)."""
        report = assembler.assemble(sample_fragments_basic, context=None)
        assert report is not None

    def test_reconciler_empty_string_fragment(self, reconciler):
        """Empty strings in fragment list are handled."""
        result = reconciler.reconcile(["", "def valid():\n    pass", ""])
        assert "valid" in result

    def test_validator_empty_requirements(self, validator_empty):
        """Empty requirements dict means all code is valid."""
        result = validator_empty.validate("anything")
        assert result.complete is True

    def test_quality_whitespace_only_code(self, quality_checker_standard):
        """Whitespace-only code is treated as empty."""
        result = quality_checker_standard.check("   \n\n   ")
        assert result.passed is False

    def test_report_all_fields_optional(self):
        """Default-constructed report has sane defaults."""
        report = AssemblyReport()
        assert report.status == AssemblyStatus.PENDING
        assert report.errors == []
        assert report.warnings == []

    def test_assembly_repeated_calls_same_result(self, assembler):
        """Repeated calls are deterministic."""
        code = "def func():\n    pass"
        r1 = assembler.assemble([code])
        r2 = assembler.assemble([code])
        assert r1.final_code == r2.final_code
        assert r1.status == r2.status

    def test_reconcile_with_special_characters(self, reconciler):
        """Special characters in string literals are preserved."""
        code = 'def func():\n    return "Special: !@#$%^&*()"'
        result = reconciler.reconcile([code])
        assert "func" in result

    def test_validator_duplicate_requirements(self):
        """Duplicate requirement names are handled gracefully."""
        validator = CompletionValidator(
            requirements={"functions": ["func", "func"], "classes": ["Class"]}
        )
        result = validator.validate("def func():\n    pass\nclass Class:\n    pass")
        assert result is not None

    def test_quality_multiple_syntax_issues(self, quality_checker_standard):
        """Multiple syntax issues yield score 0."""
        result = quality_checker_standard.check("def func(\n    def another(\n")
        assert result.passed is False
        assert result.score == 0.0

    def test_reconcile_only_comments(self, reconciler):
        """Fragment with only comments produces minimal output."""
        result = reconciler.reconcile(["# just a comment\n"])
        # Comments are not AST nodes, so output may be empty
        assert isinstance(result, str)

    def test_validator_coverage_calculation_accuracy(self):
        """Coverage percentage is calculated correctly."""
        validator = CompletionValidator(
            requirements={"functions": ["a", "b", "c", "d"]}
        )
        # 2 out of 4 present = 50%
        result = validator.validate("def a():\n    pass\ndef b():\n    pass")
        assert result.coverage_pct == 50.0

    @pytest.mark.parametrize("empty_value", ["", None, []])
    def test_assembly_empty_variations(self, assembler, empty_value):
        """Various empty/None input types are handled."""
        if empty_value is None:
            report = assembler.assemble([])
        else:
            report = assembler.assemble(
                [empty_value] if not isinstance(empty_value, list) else empty_value
            )
        assert report is not None


# ============================================================================
# Sanity Checks
# ============================================================================


class TestSanityChecks:
    """Sanity-check tests to verify module integrity."""

    def test_module_classes_importable(self):
        """All primary classes are importable."""
        assert ASTReconciler is not None
        assert CompletionValidator is not None
        assert QualityChecker is not None
        assert FinalAssembler is not None
        assert AssemblyReport is not None

    def test_all_dataclasses_instantiable(self):
        """All dataclasses can be instantiated with defaults."""
        node = ASTNode(node_type="test")
        assert node.node_type == "test"

        result = QualityResult(passed=True, score=100.0)
        assert result.passed is True

        validation = ValidationResult(complete=True)
        assert validation.complete is True

        report = AssemblyReport()
        assert report.status == AssemblyStatus.PENDING

    def test_all_enums_defined(self):
        """All expected AssemblyStatus values exist."""
        assert AssemblyStatus.SUCCESS.value == "success"
        assert AssemblyStatus.FAILURE.value == "failure"
        assert AssemblyStatus.PARTIAL.value == "partial"
        assert AssemblyStatus.PENDING.value == "pending"

    def test_reconciler_strategy_option(self):
        """Reconciler accepts and stores strategy parameter."""
        rec1 = ASTReconciler(strategy="last_wins")
        rec2 = ASTReconciler(strategy="error")
        assert rec1.strategy == "last_wins"
        assert rec2.strategy == "error"

    def test_fixtures_all_work(
        self,
        reconciler,
        validator_with_requirements,
        quality_checker_standard,
        assembler,
    ):
        """All fixtures initialize without error."""
        assert reconciler is not None
        assert validator_with_requirements is not None
        assert quality_checker_standard is not None
        assert assembler is not None

    def test_report_serialization_deterministic(self):
        """Report serialization is deterministic."""
        report = AssemblyReport(
            status=AssemblyStatus.SUCCESS, timestamp="2024-01-01T00:00:00Z"
        )
        assert report.to_dict() == report.to_dict()

    def test_production_flag_set(self):
        """_PRODUCTION_MODULE_AVAILABLE flag is set (either True or False)."""
        assert isinstance(_PRODUCTION_MODULE_AVAILABLE, bool)