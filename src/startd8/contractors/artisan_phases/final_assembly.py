"""
Final Assembly Phase: AST-based design reconciliation, work item validation,
code quality checks, and reconciliation report generation.

This module implements the final assembly phase of an artisan contractor pipeline.
It validates that generated code matches the intended design specification,
all work items are complete, and code quality standards are met.

All code is self-contained with no relative imports or external dependencies
beyond Python 3.10+ standard library.

Usage:
    phase = FinalAssemblyPhase()
    report = phase.run({
        "design_specs": [...],
        "work_items": [...],
        "quality_config": {...},
        "source_files": {"path/to/file.py": "source code..."},
    })
    print(report.to_json())
"""

import ast
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from startd8.logging_config import get_logger


# ============================================================================
# ENUMS
# ============================================================================


class Severity(Enum):
    """Severity level of a finding."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class FindingCategory(Enum):
    """Category of finding from reconciliation, work-item, or quality checks."""

    DESIGN_MISSING_CLASS = "design_missing_class"
    DESIGN_MISSING_FUNCTION = "design_missing_function"
    DESIGN_MISSING_METHOD = "design_missing_method"
    DESIGN_SIGNATURE_MISMATCH = "design_signature_mismatch"
    DESIGN_MISSING_DECORATOR = "design_missing_decorator"
    DESIGN_MISSING_ATTRIBUTE = "design_missing_attribute"
    DESIGN_EXTRA_CLASS = "design_extra_class"
    DESIGN_EXTRA_FUNCTION = "design_extra_function"
    DESIGN_EXTRA_METHOD = "design_extra_method"
    DESIGN_PARSE_ERROR = "design_parse_error"
    WORK_ITEM_INCOMPLETE = "work_item_incomplete"
    WORK_ITEM_ARTIFACT_MISSING = "work_item_artifact_missing"
    QUALITY_NO_DOCSTRING = "quality_no_docstring"
    QUALITY_FUNCTION_TOO_LONG = "quality_function_too_long"
    QUALITY_UNUSED_IMPORT = "quality_unused_import"
    QUALITY_BARE_EXCEPT = "quality_bare_except"
    QUALITY_MUTABLE_DEFAULT = "quality_mutable_default"
    QUALITY_MISSING_TYPE_HINT = "quality_missing_type_hint"
    QUALITY_PARSE_ERROR = "quality_parse_error"


class WorkItemStatus(Enum):
    """Status of a work item."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    SKIPPED = "skipped"


class Verdict(Enum):
    """Overall verdict of the reconciliation report."""

    PASS = "pass"
    FAIL = "fail"
    PASS_WITH_WARNINGS = "pass_with_warnings"


# ============================================================================
# DATACLASSES
# ============================================================================


@dataclass
class Finding:
    """Represents a single finding from the reconciliation process."""

    category: FindingCategory
    severity: Severity
    message: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert finding to a JSON-serializable dictionary."""
        return {
            "category": self.category.value,
            "severity": self.severity.value,
            "message": self.message,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "details": self.details,
        }


@dataclass
class WorkItem:
    """Represents a work item to be validated."""

    id: str
    description: str
    status: WorkItemStatus
    artifact_path: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkItem":
        """Create WorkItem from dictionary.

        Args:
            data: Dictionary with keys 'id', 'description', 'status',
                  and optionally 'artifact_path'.

        Returns:
            Parsed WorkItem instance.
        """
        status = data["status"]
        if isinstance(status, str):
            status = WorkItemStatus(status)
        return cls(
            id=data["id"],
            description=data["description"],
            status=status,
            artifact_path=data.get("artifact_path"),
        )


@dataclass
class DesignElement:
    """Describes one expected element in the design specification."""

    kind: str  # "class", "function", "method", "attribute"
    name: str
    parent: Optional[str] = None  # For methods, the owning class name
    parameters: Optional[List[str]] = None  # Expected parameter names (excluding self)
    decorators: Optional[List[str]] = None  # Expected decorator names
    return_annotation: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DesignElement":
        """Create DesignElement from dictionary."""
        return cls(
            kind=data["kind"],
            name=data["name"],
            parent=data.get("parent"),
            parameters=data.get("parameters"),
            decorators=data.get("decorators"),
            return_annotation=data.get("return_annotation"),
        )


@dataclass
class DesignSpec:
    """Full design specification for a single source file."""

    file_path: str
    elements: List[DesignElement] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DesignSpec":
        """Create DesignSpec from dictionary."""
        elements = [DesignElement.from_dict(e) for e in data.get("elements", [])]
        return cls(file_path=data["file_path"], elements=elements)


@dataclass
class QualityConfig:
    """Configuration knobs for code quality checks."""

    max_function_length: int = 50
    require_docstrings: bool = True
    check_type_hints: bool = True
    check_unused_imports: bool = True
    check_bare_except: bool = True
    check_mutable_defaults: bool = True

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "QualityConfig":
        """Create QualityConfig from dictionary, falling back to defaults."""
        if not data:
            return cls()
        return cls(
            max_function_length=data.get("max_function_length", 50),
            require_docstrings=data.get("require_docstrings", True),
            check_type_hints=data.get("check_type_hints", True),
            check_unused_imports=data.get("check_unused_imports", True),
            check_bare_except=data.get("check_bare_except", True),
            check_mutable_defaults=data.get("check_mutable_defaults", True),
        )


@dataclass
class ReconciliationReport:
    """Final reconciliation report aggregating all findings and verdict."""

    timestamp: str  # ISO 8601
    verdict: Verdict
    total_findings: int
    error_count: int
    warning_count: int
    info_count: int
    findings: List[Finding] = field(default_factory=list)
    work_items_total: int = 0
    work_items_complete: int = 0
    design_specs_checked: int = 0
    files_quality_checked: int = 0
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to a JSON-serializable dictionary."""
        return {
            "timestamp": self.timestamp,
            "verdict": self.verdict.value,
            "total_findings": self.total_findings,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "work_items_total": self.work_items_total,
            "work_items_complete": self.work_items_complete,
            "design_specs_checked": self.design_specs_checked,
            "files_quality_checked": self.files_quality_checked,
            "summary": self.summary,
            "findings": [f.to_dict() for f in self.findings],
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize report to a formatted JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


# ============================================================================
# DESIGN RECONCILER
# ============================================================================


class DesignReconciler:
    """Compares an AST tree against a DesignSpec and produces findings.

    The reconciler parses Python source, extracts top-level classes, functions,
    methods, and module-level attribute assignments, then compares them against
    the expected design elements.  Missing, extra, and mismatched elements are
    reported.
    """

    def __init__(self, file_path: str = "<unknown>") -> None:
        """Initialize reconciler for a given source file path."""
        self.file_path = file_path
        self.findings: List[Finding] = []

    def reconcile(self, source_code: str, design_spec: DesignSpec) -> List[Finding]:
        """Parse source code into an AST and compare against the design spec.

        Args:
            source_code: Python source code as a string.
            design_spec: DesignSpec describing the expected structure.

        Returns:
            List of findings (errors, warnings, info).
        """
        self.findings = []

        try:
            tree = ast.parse(source_code)
        except SyntaxError as exc:
            return [
                Finding(
                    category=FindingCategory.DESIGN_PARSE_ERROR,
                    severity=Severity.ERROR,
                    message=f"Source file parse error: {exc}",
                    file_path=self.file_path,
                    line_number=getattr(exc, "lineno", None),
                )
            ]

        actual = self._extract_actual_elements(tree)
        expected_by_key = self._index_design_elements(design_spec.elements)

        # Check for missing / mismatched elements
        for key, expected_elem in expected_by_key.items():
            if key not in actual:
                self.findings.append(self._missing_element_finding(expected_elem))
            else:
                actual_elem = actual[key]
                self._check_parameters(expected_elem, actual_elem)
                self._check_decorators(expected_elem, actual_elem)

        # Check for extra (unexpected) elements
        for key, actual_elem in actual.items():
            if key not in expected_by_key:
                self._report_extra_element(actual_elem)

        return self.findings

    # ------------------------------------------------------------------
    # AST extraction helpers
    # ------------------------------------------------------------------

    def _extract_actual_elements(self, tree: ast.Module) -> Dict[str, Dict[str, Any]]:
        """Extract classes, functions, methods, and module attributes from AST.

        Returns:
            Dict keyed by canonical strings like ``"class:Foo"``,
            ``"function:bar"``, ``"method:Foo.baz"``, ``"attribute:X"``.
        """
        elements: Dict[str, Dict[str, Any]] = {}

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                key = f"class:{node.name}"
                elements[key] = {
                    "kind": "class",
                    "name": node.name,
                    "line": node.lineno,
                    "decorators": [
                        self._get_decorator_name(d) for d in node.decorator_list
                    ],
                }
                # Extract methods within the class body
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_key = f"method:{node.name}.{item.name}"
                        elements[method_key] = {
                            "kind": "method",
                            "name": item.name,
                            "parent": node.name,
                            "line": item.lineno,
                            "parameters": self._extract_parameters(item),
                            "decorators": [
                                self._get_decorator_name(d) for d in item.decorator_list
                            ],
                        }

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                key = f"function:{node.name}"
                elements[key] = {
                    "kind": "function",
                    "name": node.name,
                    "line": node.lineno,
                    "parameters": self._extract_parameters(node),
                    "decorators": [
                        self._get_decorator_name(d) for d in node.decorator_list
                    ],
                }

            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        key = f"attribute:{target.id}"
                        elements[key] = {
                            "kind": "attribute",
                            "name": target.id,
                            "line": node.lineno,
                        }

            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                key = f"attribute:{node.target.id}"
                elements[key] = {
                    "kind": "attribute",
                    "name": node.target.id,
                    "line": node.lineno,
                }

        return elements

    def _extract_parameters(
        self, func: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> List[str]:
        """Extract parameter names from a function definition, excluding ``self``."""
        args = func.args
        params: List[str] = []

        for arg in args.args:
            if arg.arg != "self":
                params.append(arg.arg)

        if args.vararg:
            params.append(f"*{args.vararg.arg}")

        for arg in args.kwonlyargs:
            params.append(arg.arg)

        if args.kwarg:
            params.append(f"**{args.kwarg.arg}")

        return params

    def _get_decorator_name(self, dec: ast.expr) -> str:
        """Extract a human-readable decorator name from an AST node."""
        if isinstance(dec, ast.Name):
            return dec.id
        if isinstance(dec, ast.Attribute):
            parts: List[str] = []
            node: ast.expr = dec
            while isinstance(node, ast.Attribute):
                parts.insert(0, node.attr)
                node = node.value  # type: ignore[assignment]
            if isinstance(node, ast.Name):
                parts.insert(0, node.id)
            return ".".join(parts)
        if isinstance(dec, ast.Call):
            return self._get_decorator_name(dec.func)
        return "<unknown_decorator>"

    # ------------------------------------------------------------------
    # Comparison helpers
    # ------------------------------------------------------------------

    def _index_design_elements(
        self, elements: List[DesignElement]
    ) -> Dict[str, DesignElement]:
        """Build an index keyed by canonical element identifiers."""
        indexed: Dict[str, DesignElement] = {}
        for elem in elements:
            if elem.kind == "method" and elem.parent:
                key = f"method:{elem.parent}.{elem.name}"
            elif elem.kind == "class":
                key = f"class:{elem.name}"
            elif elem.kind == "function":
                key = f"function:{elem.name}"
            elif elem.kind == "attribute":
                key = f"attribute:{elem.name}"
            else:
                continue
            indexed[key] = elem
        return indexed

    def _check_parameters(
        self, expected_elem: DesignElement, actual_elem: Dict[str, Any]
    ) -> None:
        """Emit a finding if parameter lists diverge."""
        if expected_elem.parameters is None:
            return
        actual_params = actual_elem.get("parameters", [])
        if actual_params != expected_elem.parameters:
            self.findings.append(
                Finding(
                    category=FindingCategory.DESIGN_SIGNATURE_MISMATCH,
                    severity=Severity.WARNING,
                    message=(
                        f"Function/method '{expected_elem.name}' signature mismatch. "
                        f"Expected parameters: {expected_elem.parameters}, "
                        f"got: {actual_params}"
                    ),
                    file_path=self.file_path,
                    line_number=actual_elem.get("line"),
                    details={
                        "expected": expected_elem.parameters,
                        "actual": actual_params,
                    },
                )
            )

    def _check_decorators(
        self, expected_elem: DesignElement, actual_elem: Dict[str, Any]
    ) -> None:
        """Emit findings for any expected decorators that are absent."""
        if not expected_elem.decorators:
            return
        actual_decs = actual_elem.get("decorators", [])
        for expected_dec in expected_elem.decorators:
            if expected_dec not in actual_decs:
                self.findings.append(
                    Finding(
                        category=FindingCategory.DESIGN_MISSING_DECORATOR,
                        severity=Severity.WARNING,
                        message=(
                            f"{expected_elem.kind.capitalize()} "
                            f"'{expected_elem.name}' missing expected "
                            f"decorator: '{expected_dec}'"
                        ),
                        file_path=self.file_path,
                        line_number=actual_elem.get("line"),
                        details={"expected_decorator": expected_dec},
                    )
                )

    def _missing_element_finding(self, elem: DesignElement) -> Finding:
        """Create a finding for a missing design element."""
        category_map = {
            "class": FindingCategory.DESIGN_MISSING_CLASS,
            "function": FindingCategory.DESIGN_MISSING_FUNCTION,
            "method": FindingCategory.DESIGN_MISSING_METHOD,
            "attribute": FindingCategory.DESIGN_MISSING_ATTRIBUTE,
        }
        category = category_map.get(elem.kind, FindingCategory.DESIGN_MISSING_FUNCTION)

        desc = f"{elem.kind.capitalize()} '{elem.name}'"
        if elem.parent:
            desc = f"{elem.kind.capitalize()} '{elem.parent}.{elem.name}'"

        return Finding(
            category=category,
            severity=Severity.ERROR,
            message=f"Missing expected {desc}",
            file_path=self.file_path,
        )

    def _report_extra_element(self, actual_elem: Dict[str, Any]) -> None:
        """Emit an informational finding for an unexpected element."""
        kind = actual_elem["kind"]
        category_map = {
            "class": FindingCategory.DESIGN_EXTRA_CLASS,
            "method": FindingCategory.DESIGN_EXTRA_METHOD,
            "function": FindingCategory.DESIGN_EXTRA_FUNCTION,
        }
        category = category_map.get(kind)
        if category is None:
            return  # Don't report extra attributes as noise
        self.findings.append(
            Finding(
                category=category,
                severity=Severity.INFO,
                message=f"Unexpected {kind} '{actual_elem['name']}' in source",
                file_path=self.file_path,
                line_number=actual_elem.get("line"),
            )
        )


# ============================================================================
# QUALITY CHECKER
# ============================================================================


class QualityChecker(ast.NodeVisitor):
    """AST-based code quality checker.

    Walks the AST of a Python source file and reports on:
    - Missing docstrings on public functions/methods
    - Functions exceeding a configurable line limit
    - Missing type hints on public function parameters
    - Unused imports
    - Bare ``except:`` clauses
    - Mutable default argument values
    """

    def __init__(self, config: QualityConfig, file_path: str = "<unknown>") -> None:
        """Initialize quality checker."""
        self.config = config
        self.file_path = file_path
        self.findings: List[Finding] = []
        self._imported_names: Dict[str, int] = {}  # name -> line number
        self._used_names: Set[str] = set()
        self._current_class: Optional[str] = None

    def check(self, source_code: str) -> List[Finding]:
        """Parse and analyse the source, returning quality findings."""
        self.findings = []
        self._imported_names = {}
        self._used_names = set()
        self._current_class = None

        try:
            tree = ast.parse(source_code)
        except SyntaxError as exc:
            return [
                Finding(
                    category=FindingCategory.QUALITY_PARSE_ERROR,
                    severity=Severity.ERROR,
                    message=f"Source file parse error: {exc}",
                    file_path=self.file_path,
                    line_number=getattr(exc, "lineno", None),
                )
            ]

        self.visit(tree)
        if self.config.check_unused_imports:
            self._finalize_unused_imports()
        return self.findings

    # ------------------------------------------------------------------
    # Visitor methods
    # ------------------------------------------------------------------

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Track current class context and check for docstring."""
        old_class = self._current_class
        self._current_class = node.name

        if self.config.require_docstrings and not node.name.startswith("_"):
            docstring = ast.get_docstring(node)
            if not docstring:
                self.findings.append(
                    Finding(
                        category=FindingCategory.QUALITY_NO_DOCSTRING,
                        severity=Severity.WARNING,
                        message=f"Class '{node.name}' has no docstring",
                        file_path=self.file_path,
                        line_number=node.lineno,
                    )
                )

        self.generic_visit(node)
        self._current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Check a regular function/method for quality issues."""
        self._check_function_quality(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Check an async function/method (same rules as sync)."""
        self._check_function_quality(node)  # type: ignore[arg-type]
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        """Track ``import X`` names."""
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name
            self._imported_names[name] = node.lineno
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Track ``from X import Y`` names."""
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name
            if name != "*":
                self._imported_names[name] = node.lineno
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        """Record name usage for unused-import analysis."""
        if isinstance(node.ctx, ast.Load):
            self._used_names.add(node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Record attribute accesses so ``import os; os.path`` counts as used."""
        if isinstance(node.value, ast.Name):
            self._used_names.add(node.value.id)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        """Detect bare ``except:`` clauses."""
        if self.config.check_bare_except and node.type is None:
            self.findings.append(
                Finding(
                    category=FindingCategory.QUALITY_BARE_EXCEPT,
                    severity=Severity.WARNING,
                    message="Bare 'except:' clause detected",
                    file_path=self.file_path,
                    line_number=node.lineno,
                )
            )
        self.generic_visit(node)

    # ------------------------------------------------------------------
    # Internal checks
    # ------------------------------------------------------------------

    def _check_function_quality(self, node: ast.FunctionDef) -> None:
        """Run all function-level quality checks."""
        qualified_name = (
            f"{self._current_class}.{node.name}" if self._current_class else node.name
        )

        if self.config.require_docstrings:
            self._check_docstring(node, qualified_name)

        if self.config.check_type_hints:
            self._check_type_hints(node, qualified_name)

        self._check_function_length(node, qualified_name)

        if self.config.check_mutable_defaults:
            self._check_mutable_defaults(node, qualified_name)

    def _check_docstring(self, node: ast.FunctionDef, qualified_name: str) -> None:
        """Emit a warning when a public function lacks a docstring."""
        if node.name.startswith("_"):
            return
        if not ast.get_docstring(node):
            self.findings.append(
                Finding(
                    category=FindingCategory.QUALITY_NO_DOCSTRING,
                    severity=Severity.WARNING,
                    message=f"Function '{qualified_name}' has no docstring",
                    file_path=self.file_path,
                    line_number=node.lineno,
                )
            )

    def _check_function_length(
        self, node: ast.FunctionDef, qualified_name: str
    ) -> None:
        """Emit a warning when a function body exceeds the configured limit."""
        end = getattr(node, "end_lineno", None)
        num_lines = (end - node.lineno + 1) if end else 1
        if num_lines > self.config.max_function_length:
            self.findings.append(
                Finding(
                    category=FindingCategory.QUALITY_FUNCTION_TOO_LONG,
                    severity=Severity.WARNING,
                    message=(
                        f"Function '{qualified_name}' is {num_lines} lines "
                        f"(max: {self.config.max_function_length})"
                    ),
                    file_path=self.file_path,
                    line_number=node.lineno,
                    details={
                        "actual_lines": num_lines,
                        "max_lines": self.config.max_function_length,
                    },
                )
            )

    def _check_type_hints(self, node: ast.FunctionDef, qualified_name: str) -> None:
        """Emit a warning for public functions with un-annotated parameters."""
        if node.name.startswith("_"):
            return

        args = node.args
        missing_hints: List[str] = []

        for arg in args.args:
            if arg.arg != "self" and arg.annotation is None:
                missing_hints.append(arg.arg)

        for arg in args.kwonlyargs:
            if arg.annotation is None:
                missing_hints.append(arg.arg)

        if args.vararg and args.vararg.annotation is None:
            missing_hints.append(f"*{args.vararg.arg}")

        if args.kwarg and args.kwarg.annotation is None:
            missing_hints.append(f"**{args.kwarg.arg}")

        if missing_hints:
            self.findings.append(
                Finding(
                    category=FindingCategory.QUALITY_MISSING_TYPE_HINT,
                    severity=Severity.WARNING,
                    message=(
                        f"Function '{qualified_name}' missing type hints "
                        f"on parameters: {missing_hints}"
                    ),
                    file_path=self.file_path,
                    line_number=node.lineno,
                    details={"parameters_without_hints": missing_hints},
                )
            )

    def _check_mutable_defaults(
        self, node: ast.FunctionDef, qualified_name: str
    ) -> None:
        """Detect mutable default argument values (list, dict, set literals/calls)."""
        all_defaults = list(node.args.defaults) + [
            d for d in node.args.kw_defaults if d is not None
        ]
        for default in all_defaults:
            if self._is_mutable_default(default):
                self.findings.append(
                    Finding(
                        category=FindingCategory.QUALITY_MUTABLE_DEFAULT,
                        severity=Severity.WARNING,
                        message=(
                            f"Function '{qualified_name}' has mutable default argument"
                        ),
                        file_path=self.file_path,
                        line_number=node.lineno,
                        details={"type": type(default).__name__},
                    )
                )

    @staticmethod
    def _is_mutable_default(node: ast.expr) -> bool:
        """Return True if the AST node represents a mutable default value."""
        if isinstance(node, (ast.List, ast.Dict, ast.Set)):
            return True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in ("list", "dict", "set"):
                return True
        return False

    def _finalize_unused_imports(self) -> None:
        """After full tree traversal, report any imported names never referenced."""
        for name, line_num in self._imported_names.items():
            if name not in self._used_names:
                self.findings.append(
                    Finding(
                        category=FindingCategory.QUALITY_UNUSED_IMPORT,
                        severity=Severity.WARNING,
                        message=f"Imported name '{name}' is never used",
                        file_path=self.file_path,
                        line_number=line_num,
                    )
                )


# ============================================================================
# WORK ITEM VALIDATOR
# ============================================================================


class WorkItemValidator:
    """Validates that all work items are complete and their artifacts exist."""

    def __init__(self, base_path: Optional[str] = None) -> None:
        """Initialize validator with an optional base directory for resolving paths."""
        self.base_path = Path(base_path) if base_path else Path.cwd()

    def validate(self, work_items: List[WorkItem]) -> List[Finding]:
        """Validate every work item for completion and artifact existence.

        Args:
            work_items: List of work items to validate.

        Returns:
            List of findings.
        """
        findings: List[Finding] = []

        for item in work_items:
            if item.status == WorkItemStatus.COMPLETE:
                if item.artifact_path and item.artifact_path.strip():
                    artifact_path = self.base_path / item.artifact_path
                    if not artifact_path.exists():
                        findings.append(
                            Finding(
                                category=FindingCategory.WORK_ITEM_ARTIFACT_MISSING,
                                severity=Severity.ERROR,
                                message=(
                                    f"Work item '{item.id}' references artifact "
                                    f"that does not exist: {item.artifact_path}"
                                ),
                                details={
                                    "work_item_id": item.id,
                                    "artifact_path": item.artifact_path,
                                },
                            )
                        )
            elif item.status == WorkItemStatus.SKIPPED:
                findings.append(
                    Finding(
                        category=FindingCategory.WORK_ITEM_INCOMPLETE,
                        severity=Severity.INFO,
                        message=f"Work item '{item.id}' was skipped",
                        details={"work_item_id": item.id},
                    )
                )
            else:
                findings.append(
                    Finding(
                        category=FindingCategory.WORK_ITEM_INCOMPLETE,
                        severity=Severity.ERROR,
                        message=(
                            f"Work item '{item.id}' status is "
                            f"'{item.status.value}', expected 'complete'"
                        ),
                        details={
                            "work_item_id": item.id,
                            "status": item.status.value,
                        },
                    )
                )

        return findings


# ============================================================================
# FINAL ASSEMBLY PHASE (ORCHESTRATOR)
# ============================================================================


class FinalAssemblyPhase:
    """Orchestrates the final assembly phase.

    Runs three stages in order:
      1. **Design reconciliation** — AST-parse each source file and compare
         against its design spec.
      2. **Work-item validation** — confirm every work item is complete and
         its artifact exists on disk (or in the cache).
      3. **Code quality checks** — walk each source AST for common issues.

    All findings are aggregated into a :class:`ReconciliationReport`.
    """

    def __init__(self) -> None:
        """Initialize phase."""
        self.logger = get_logger(__name__)

    def run(self, context: Dict[str, Any]) -> ReconciliationReport:
        """Execute the final assembly phase.

        Args:
            context: Dictionary with keys:
                - ``design_specs``: ``List[dict]`` deserializable to
                  :class:`DesignSpec`.
                - ``work_items``: ``List[dict]`` deserializable to
                  :class:`WorkItem`.
                - ``quality_config``: ``Optional[dict]`` deserializable to
                  :class:`QualityConfig`.
                - ``base_path``: ``Optional[str]`` for resolving relative
                  file paths.
                - ``source_files``: ``Optional[Dict[str, str]]`` in-memory
                  file content cache (keyed by path).

        Returns:
            :class:`ReconciliationReport` with all findings and a verdict.
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        all_findings: List[Finding] = []

        # ---- unpack context ----
        design_specs_data: List[Dict[str, Any]] = context.get("design_specs", [])
        work_items_data: List[Dict[str, Any]] = context.get("work_items", [])
        quality_config_data = context.get("quality_config")
        base_path = context.get("base_path", ".")
        source_files_cache: Dict[str, str] = context.get("source_files", {})

        base_path_obj = Path(base_path)
        quality_config = QualityConfig.from_dict(quality_config_data)

        # ---- step 1: parse design specs ----
        design_specs: List[DesignSpec] = []
        for spec_data in design_specs_data:
            try:
                design_specs.append(DesignSpec.from_dict(spec_data))
            except (KeyError, TypeError, ValueError) as exc:
                self.logger.warning("Failed to parse design spec: %s", exc)
                all_findings.append(
                    Finding(
                        category=FindingCategory.DESIGN_PARSE_ERROR,
                        severity=Severity.ERROR,
                        message=f"Failed to parse design spec: {exc}",
                    )
                )

        # ---- step 2: design reconciliation ----
        for design_spec in design_specs:
            source_code = self._read_source(
                design_spec.file_path, source_files_cache, base_path_obj
            )
            if source_code is None:
                all_findings.append(
                    Finding(
                        category=FindingCategory.DESIGN_PARSE_ERROR,
                        severity=Severity.ERROR,
                        message=(
                            f"Could not read source file: {design_spec.file_path}"
                        ),
                        file_path=design_spec.file_path,
                    )
                )
            else:
                reconciler = DesignReconciler(file_path=design_spec.file_path)
                all_findings.extend(reconciler.reconcile(source_code, design_spec))

        # ---- step 3: work-item validation ----
        work_items: List[WorkItem] = []
        for item_data in work_items_data:
            try:
                work_items.append(WorkItem.from_dict(item_data))
            except (KeyError, TypeError, ValueError) as exc:
                self.logger.warning("Failed to parse work item: %s", exc)
                all_findings.append(
                    Finding(
                        category=FindingCategory.WORK_ITEM_INCOMPLETE,
                        severity=Severity.ERROR,
                        message=f"Failed to parse work item: {exc}",
                    )
                )

        validator = WorkItemValidator(base_path=str(base_path_obj))
        all_findings.extend(validator.validate(work_items))

        # ---- step 4: code quality checks ----
        quality_checked_files: Set[str] = set()
        for design_spec in design_specs:
            if design_spec.file_path in quality_checked_files:
                continue
            quality_checked_files.add(design_spec.file_path)

            source_code = self._read_source(
                design_spec.file_path, source_files_cache, base_path_obj
            )
            if source_code is not None:
                checker = QualityChecker(
                    config=quality_config, file_path=design_spec.file_path
                )
                all_findings.extend(checker.check(source_code))

        # ---- step 5: aggregate & report ----
        error_count = sum(1 for f in all_findings if f.severity == Severity.ERROR)
        warning_count = sum(1 for f in all_findings if f.severity == Severity.WARNING)
        info_count = sum(1 for f in all_findings if f.severity == Severity.INFO)
        verdict = self._compute_verdict(all_findings)
        work_items_complete = sum(
            1 for item in work_items if item.status == WorkItemStatus.COMPLETE
        )

        summary = self._generate_summary(
            verdict=verdict,
            error_count=error_count,
            warning_count=warning_count,
            info_count=info_count,
            work_items_total=len(work_items),
            work_items_complete=work_items_complete,
            design_specs_checked=len(design_specs),
            files_quality_checked=len(quality_checked_files),
        )

        report = ReconciliationReport(
            timestamp=timestamp,
            verdict=verdict,
            total_findings=len(all_findings),
            error_count=error_count,
            warning_count=warning_count,
            info_count=info_count,
            findings=all_findings,
            work_items_total=len(work_items),
            work_items_complete=work_items_complete,
            design_specs_checked=len(design_specs),
            files_quality_checked=len(quality_checked_files),
            summary=summary,
        )

        self.logger.info("Reconciliation complete: %s", summary)
        return report

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_source(
        file_path: str,
        source_files: Optional[Dict[str, str]],
        base_path: Path,
    ) -> Optional[str]:
        """Read source code from cache first, then fall back to disk.

        Args:
            file_path: Relative or absolute path to the source file.
            source_files: Optional in-memory cache of file contents.
            base_path: Base directory for resolving relative paths.

        Returns:
            Source code string, or ``None`` if the file cannot be read.
        """
        if source_files and file_path in source_files:
            return source_files[file_path]

        full_path = base_path / file_path
        try:
            return full_path.read_text(encoding="utf-8")
        except (FileNotFoundError, IsADirectoryError, PermissionError, OSError):
            return None

    @staticmethod
    def _compute_verdict(findings: List[Finding]) -> Verdict:
        """Derive the overall verdict from the collected findings."""
        has_error = any(f.severity == Severity.ERROR for f in findings)
        has_warning = any(f.severity == Severity.WARNING for f in findings)

        if has_error:
            return Verdict.FAIL
        if has_warning:
            return Verdict.PASS_WITH_WARNINGS
        return Verdict.PASS

    @staticmethod
    def _generate_summary(
        verdict: Verdict,
        error_count: int,
        warning_count: int,
        info_count: int,
        work_items_total: int,
        work_items_complete: int,
        design_specs_checked: int,
        files_quality_checked: int,
    ) -> str:
        """Build a one-line human-readable summary of the reconciliation."""
        return (
            f"Final Assembly: {verdict.value.upper()} — "
            f"{error_count} error(s), {warning_count} warning(s), "
            f"{info_count} info(s). "
            f"Work items: {work_items_complete}/{work_items_total} complete. "
            f"Design specs checked: {design_specs_checked}. "
            f"Files quality-checked: {files_quality_checked}."
        )
