"""
Test Construction Phase - TDD test generation from design documents.

This module implements the Test Construction phase of the Artisan contractor
pattern. It generates pytest test files and implementation stubs from a
design document, then validates pytest can collect all tests.

Two generation strategies are supported:

1. **Template-based** (default) — mechanical boilerplate from parsed
   ``ClassSpec``/``FunctionSpec`` objects.  Fast, deterministic, but produces
   skeleton tests with ``# TODO`` placeholders.
2. **LLM-driven** (when ``agent_spec`` is provided) — an LLM reads the
   design document (and optionally implementation code) and produces
   tests with real assertions, meaningful fixtures, and discovered edge
   cases.  Falls back to template-based generation on failure.
"""

from __future__ import annotations

import asyncio
import enum
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from startd8.contractors.artisan_contractor import _NoOpTracer
from startd8.contractors.protocols import DRAFT_MODEL_CLAUDE_HAIKU
from startd8.utils.token_usage import token_usage_cost, token_usage_input, token_usage_output

# OTel instrumentation (graceful degradation when unavailable)
try:
    from opentelemetry import trace as _trace
    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False

_test_tracer = _trace.get_tracer("startd8.artisan.test") if _HAS_OTEL else _NoOpTracer()

if TYPE_CHECKING:
    from startd8.contractors.artisan_phases.design_documentation import (
        DesignDocument as DesignPhaseDocument,
    )

from startd8.logging_config import get_logger
logger = get_logger(__name__)


# ============================================================================
# ENUMS
# ============================================================================


class PhaseStatus(enum.Enum):
    """Status of a phase execution."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class TestType(enum.Enum):
    """Type of test to generate."""

    UNIT = "unit"
    INTEGRATION = "integration"
    EDGE_CASE = "edge_case"


# ============================================================================
# DATACLASSES
# ============================================================================


@dataclass
class MethodSpec:
    """Specification for a single method/function to be tested."""

    name: str
    parameters: List[Dict[str, str]] = field(default_factory=list)
    return_type: str = "None"
    description: str = ""
    raises: List[str] = field(default_factory=list)
    is_async: bool = False
    is_static: bool = False
    is_classmethod: bool = False


@dataclass
class ClassSpec:
    """Specification for a class to be tested."""

    name: str
    module_path: str
    methods: List[MethodSpec] = field(default_factory=list)
    description: str = ""
    base_classes: List[str] = field(default_factory=list)
    init_params: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class FunctionSpec:
    """Specification for a standalone function to be tested."""

    name: str
    module_path: str
    parameters: List[Dict[str, str]] = field(default_factory=list)
    return_type: str = "None"
    description: str = ""
    raises: List[str] = field(default_factory=list)
    is_async: bool = False


@dataclass
class TestCase:
    """A single generated test case."""

    test_name: str
    test_type: TestType
    target_name: str
    target_method: Optional[str]
    description: str
    test_body: str
    markers: List[str] = field(default_factory=list)
    # Internal: track whether this test belongs to a class test group
    _is_class_test: bool = field(default=False, repr=False)


@dataclass
class TestModule:
    """A generated test module (file)."""

    filename: str
    imports: List[str] = field(default_factory=list)
    test_cases: List[TestCase] = field(default_factory=list)
    fixtures: List[str] = field(default_factory=list)


@dataclass
class StubModule:
    """A generated implementation stub module."""

    filepath: str
    content: str


@dataclass
class DesignDocument:
    """Parsed design document containing all specs."""

    feature_name: str
    description: str = ""
    classes: List[ClassSpec] = field(default_factory=list)
    functions: List[FunctionSpec] = field(default_factory=list)
    edge_cases: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class CollectionResult:
    """Result of pytest collection validation."""

    success: bool
    collected_count: int
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    test_node_ids: List[str] = field(default_factory=list)


@dataclass
class PhaseResult:
    """Result of the Test Construction phase execution."""

    status: PhaseStatus
    test_modules: List[TestModule] = field(default_factory=list)
    stub_modules: List[StubModule] = field(default_factory=list)
    collection_result: Optional[CollectionResult] = None
    errors: List[str] = field(default_factory=list)
    output_dir: Optional[str] = None

    total_cost_usd: float = 0.0
    """Total LLM cost in USD across all generation calls."""

    total_input_tokens: int = 0
    """Total input tokens consumed across all generation calls."""

    total_output_tokens: int = 0
    """Total output tokens generated across all generation calls."""


# ============================================================================
# PARSING
# ============================================================================


def parse_design_document(raw: Dict[str, Any]) -> DesignDocument:
    """
    Parse a raw design document dictionary into a DesignDocument.

    Args:
        raw: Dictionary with keys like ``feature_name``, ``classes``,
             ``functions``, ``edge_cases``.

    Returns:
        DesignDocument instance.

    Raises:
        ValueError: If ``feature_name`` is missing or *raw* is empty / None.
    """
    if not raw:
        raise ValueError("Design document cannot be empty")

    if "feature_name" not in raw:
        raise ValueError("Design document must contain 'feature_name' key")

    feature_name = raw["feature_name"]
    description = raw.get("description", "")

    # --- Parse classes ---
    classes: List[ClassSpec] = []
    for class_dict in raw.get("classes", []):
        methods: List[MethodSpec] = []
        for method_dict in class_dict.get("methods", []):
            method = MethodSpec(
                name=method_dict["name"],
                parameters=method_dict.get("parameters", []),
                return_type=method_dict.get("return_type", "None"),
                description=method_dict.get("description", ""),
                raises=method_dict.get("raises", []),
                is_async=method_dict.get("is_async", False),
                is_static=method_dict.get("is_static", False),
                is_classmethod=method_dict.get("is_classmethod", False),
            )
            methods.append(method)

        class_spec = ClassSpec(
            name=class_dict["name"],
            module_path=class_dict["module_path"],
            methods=methods,
            description=class_dict.get("description", ""),
            base_classes=class_dict.get("base_classes", []),
            init_params=class_dict.get("init_params", []),
        )
        classes.append(class_spec)

    # --- Parse functions ---
    functions: List[FunctionSpec] = []
    for func_dict in raw.get("functions", []):
        func_spec = FunctionSpec(
            name=func_dict["name"],
            module_path=func_dict["module_path"],
            parameters=func_dict.get("parameters", []),
            return_type=func_dict.get("return_type", "None"),
            description=func_dict.get("description", ""),
            raises=func_dict.get("raises", []),
            is_async=func_dict.get("is_async", False),
        )
        functions.append(func_spec)

    # --- Parse edge cases ---
    edge_cases = raw.get("edge_cases", [])

    logger.info(
        "Parsed design document '%s' with %d classes, %d functions, %d edge cases",
        feature_name,
        len(classes),
        len(functions),
        len(edge_cases),
    )

    return DesignDocument(
        feature_name=feature_name,
        description=description,
        classes=classes,
        functions=functions,
        edge_cases=edge_cases,
    )


# ============================================================================
# HELPERS
# ============================================================================


def _sanitize_name(name: str) -> str:
    """
    Sanitize a name for use in test function / identifier names.

    ``__str__`` → ``dunder_str``, ``_private`` → ``private``.
    """
    if name.startswith("__") and name.endswith("__") and len(name) > 4:
        return f"dunder_{name[2:-2]}"
    return name.lstrip("_") or name


def _make_init_call(
    class_name: str, init_params: List[Dict[str, str]]
) -> Tuple[str, str]:
    """Return (arrange_lines, instance_creation_line) for a class."""
    if init_params:
        assigns = [
            f"{p['name']} = None  # TODO: provide valid value" for p in init_params
        ]
        arrange = "\n    ".join(assigns)
        args = ", ".join(p["name"] for p in init_params)
        return arrange, f"instance = {class_name}({args})"
    return "", f"instance = {class_name}()"


def _make_method_call(
    method_spec: MethodSpec, instance_var: str = "instance"
) -> Tuple[str, str]:
    """Return (arrange_lines, call_expression) for a method."""
    if method_spec.parameters:
        assigns = [
            f"{p['name']} = None  # TODO: provide valid value"
            for p in method_spec.parameters
        ]
        arrange = "\n    ".join(assigns)
        args = ", ".join(p["name"] for p in method_spec.parameters)
        call = f"{instance_var}.{method_spec.name}({args})"
    else:
        arrange = ""
        call = f"{instance_var}.{method_spec.name}()"
    return arrange, call


def _make_func_call(func_spec: FunctionSpec) -> Tuple[str, str]:
    """Return (arrange_lines, call_expression) for a function."""
    if func_spec.parameters:
        assigns = [
            f"{p['name']} = None  # TODO: provide valid value"
            for p in func_spec.parameters
        ]
        arrange = "\n    ".join(assigns)
        args = ", ".join(p["name"] for p in func_spec.parameters)
        call = f"{func_spec.name}({args})"
    else:
        arrange = ""
        call = f"{func_spec.name}()"
    return arrange, call


def _indent(text: str, prefix: str = "    ") -> str:
    """Indent every non-empty line of *text* by *prefix*."""
    lines = text.split("\n")
    return "\n".join((prefix + line) if line.strip() else line for line in lines)


# ============================================================================
# TEST CASE GENERATION
# ============================================================================


def generate_test_cases_for_class(class_spec: ClassSpec) -> List[TestCase]:
    """
    Generate test cases for a given class specification.

    Generates:
    - ``test_<class>_instantiation`` – class can be instantiated
    - ``test_<class>_<method>_returns`` – each method returns something
    - ``test_<class>_<method>_raises_<exc>`` – for each declared exception
    """
    test_cases: List[TestCase] = []
    cls = class_spec.name
    san_cls = _sanitize_name(cls).lower()

    # ---- Instantiation test ----
    init_arrange, init_call = _make_init_call(cls, class_spec.init_params)
    body_parts = ["# Arrange"]
    if init_arrange:
        body_parts.append(init_arrange)
    body_parts.append("")
    body_parts.append("# Act")
    body_parts.append(init_call)
    body_parts.append("")
    body_parts.append("# Assert")
    body_parts.append("assert instance is not None")

    test_cases.append(
        TestCase(
            test_name=f"test_{san_cls}_instantiation",
            test_type=TestType.UNIT,
            target_name=cls,
            target_method=None,
            description=f"Verify {cls} can be instantiated",
            test_body="\n    ".join(body_parts),
            _is_class_test=True,
        )
    )

    # ---- Per-method tests ----
    for meth in class_spec.methods:
        san_meth = _sanitize_name(meth.name)
        init_arrange, init_call = _make_init_call(cls, class_spec.init_params)
        meth_arrange, meth_call = _make_method_call(meth)

        # -- returns test --
        body_parts = ["# Arrange"]
        if init_arrange:
            body_parts.append(init_arrange)
        if meth_arrange:
            body_parts.append(meth_arrange)
        body_parts.append(init_call)
        body_parts.append("")
        body_parts.append("# Act")
        if meth.is_async:
            body_parts.append(f"result = await {meth_call}")
        else:
            body_parts.append(f"result = {meth_call}")
        body_parts.append("")
        body_parts.append("# Assert")
        body_parts.append("assert result is not None  # TODO: assert specific value")

        markers = ["asyncio"] if meth.is_async else []
        test_cases.append(
            TestCase(
                test_name=f"test_{san_cls}_{san_meth}_returns",
                test_type=TestType.UNIT,
                target_name=cls,
                target_method=meth.name,
                description=f"Verify {cls}.{meth.name} returns expected result",
                test_body="\n    ".join(body_parts),
                markers=markers,
                _is_class_test=True,
            )
        )

        # -- exception tests --
        for exc in meth.raises:
            san_exc = _sanitize_name(exc)
            body_parts = ["# Arrange"]
            if init_arrange:
                body_parts.append(init_arrange)
            if meth_arrange:
                body_parts.append(meth_arrange)
            body_parts.append(init_call)
            body_parts.append("")
            body_parts.append("# Act & Assert")
            body_parts.append(f"with pytest.raises({exc}):")
            if meth.is_async:
                body_parts.append(f"    await {meth_call}")
            else:
                body_parts.append(f"    {meth_call}")

            test_cases.append(
                TestCase(
                    test_name=f"test_{san_cls}_{san_meth}_raises_{san_exc}",
                    test_type=TestType.UNIT,
                    target_name=cls,
                    target_method=meth.name,
                    description=f"Verify {cls}.{meth.name} raises {exc}",
                    test_body="\n    ".join(body_parts),
                    markers=markers,
                    _is_class_test=True,
                )
            )

    return test_cases


def generate_test_cases_for_function(func_spec: FunctionSpec) -> List[TestCase]:
    """
    Generate test cases for a standalone function specification.

    Generates:
    - ``test_<func>_callable``
    - ``test_<func>_returns``
    - ``test_<func>_raises_<exc>`` for each declared exception
    """
    test_cases: List[TestCase] = []
    fn = func_spec.name
    san_fn = _sanitize_name(fn)
    markers = ["asyncio"] if func_spec.is_async else []

    # -- callable test --
    test_cases.append(
        TestCase(
            test_name=f"test_{san_fn}_callable",
            test_type=TestType.UNIT,
            target_name=fn,
            target_method=None,
            description=f"Verify {fn} is callable",
            test_body=f"assert callable({fn})",
            markers=list(markers),
        )
    )

    # -- returns test (template stub — skipped until LLM populates assertions) --
    func_arrange, func_call = _make_func_call(func_spec)
    body_parts = ["# Arrange"]
    if func_arrange:
        body_parts.append(func_arrange)
    body_parts.append("")
    body_parts.append("# Act")
    if func_spec.is_async:
        body_parts.append(f"result = await {func_call}")
    else:
        body_parts.append(f"result = {func_call}")
    body_parts.append("")
    body_parts.append("# Assert")
    body_parts.append("assert result is not None  # Template stub — needs real assertions")

    skip_markers = list(markers) + [
        'skip(reason="Template-generated stub: needs LLM-driven assertions")'
    ]

    test_cases.append(
        TestCase(
            test_name=f"test_{san_fn}_returns",
            test_type=TestType.UNIT,
            target_name=fn,
            target_method=None,
            description=f"Verify {fn} returns expected result [TEMPLATE STUB]",
            test_body="\n    ".join(body_parts),
            markers=skip_markers,
        )
    )

    # -- exception tests --
    for exc in func_spec.raises:
        san_exc = _sanitize_name(exc)
        body_parts = ["# Arrange"]
        if func_arrange:
            body_parts.append(func_arrange)
        body_parts.append("")
        body_parts.append("# Act & Assert")
        body_parts.append(f"with pytest.raises({exc}):")
        if func_spec.is_async:
            body_parts.append(f"    await {func_call}")
        else:
            body_parts.append(f"    {func_call}")

        test_cases.append(
            TestCase(
                test_name=f"test_{san_fn}_raises_{san_exc}",
                test_type=TestType.UNIT,
                target_name=fn,
                target_method=None,
                description=f"Verify {fn} raises {exc}",
                test_body="\n    ".join(body_parts),
                markers=list(markers),
            )
        )

    return test_cases


def generate_edge_case_tests(
    edge_cases: List[Dict[str, str]],
    design: DesignDocument,
) -> List[TestCase]:
    """
    Generate test cases from explicit edge-case descriptions.

    Each edge-case dict should have ``description``, ``target`` and
    ``expected``.
    """
    test_cases: List[TestCase] = []

    for idx, ec in enumerate(edge_cases):
        description = ec.get("description", f"Edge case {idx}")
        target = ec.get("target", "unknown")
        expected = ec.get("expected", "")

        parts = target.split(".")
        if len(parts) >= 2:
            target_name = parts[0]
            target_method = parts[1]
        else:
            target_name = target
            target_method = None

        san_target = _sanitize_name(target_name).lower()
        if target_method:
            san_method = _sanitize_name(target_method)
            test_name = f"test_{san_target}_{san_method}_edge_case_{idx}"
        else:
            test_name = f"test_{san_target}_edge_case_{idx}"

        if "raises" in expected.lower() or "error" in expected.lower():
            body = (
                "# Edge case: " + description + "\n"
                "    # Template stub — needs LLM-driven setup and assertions\n"
                "    with pytest.raises(Exception):  # Needs specific exception type\n"
                "        pass  # Needs target invocation"
            )
        else:
            body = (
                "# Edge case: " + description + "\n"
                "    # Template stub — needs LLM-driven setup and assertions\n"
                "    result = None  # Needs target invocation\n"
                "    assert result is not None  # Needs specific assertion"
            )

        # Determine whether this is a class test
        is_class = target_method is not None

        test_cases.append(
            TestCase(
                test_name=test_name,
                test_type=TestType.EDGE_CASE,
                target_name=target_name,
                target_method=target_method,
                description=f"{description} [TEMPLATE STUB]",
                test_body=body,
                markers=['skip(reason="Template-generated stub: needs LLM-driven assertions")'],
                _is_class_test=is_class,
            )
        )

    return test_cases


# ============================================================================
# TEST MODULE BUILDING
# ============================================================================


def build_test_module(
    module_path: str,
    test_cases: List[TestCase],
    stub_import_path: str,
) -> TestModule:
    """
    Assemble test cases into a TestModule with proper imports and fixtures.

    Args:
        module_path: The module being tested (for naming).
        test_cases: List of test cases to include.
        stub_import_path: The import path for the stub module.

    Returns:
        TestModule instance.
    """
    module_basename = module_path.split(".")[-1]
    filename = f"test_{module_basename}.py"

    imports = [
        "import pytest",
        f"from {stub_import_path} import *",
    ]

    has_async = any("asyncio" in tc.markers for tc in test_cases)
    if has_async:
        imports.append("import asyncio")

    return TestModule(
        filename=filename,
        imports=imports,
        test_cases=test_cases,
        fixtures=[],
    )


def render_test_module(test_module: TestModule) -> str:
    """
    Render a TestModule into valid Python source code.

    Tests that belong to a class (``_is_class_test=True``) are grouped into
    ``class Test<ClassName>:`` blocks.  Standalone function tests are rendered
    as top-level functions.
    """
    lines: List[str] = []

    # Docstring
    lines.append('"""Auto-generated test module."""')
    lines.append("")

    # Imports
    for imp in test_module.imports:
        lines.append(imp)
    lines.append("")
    lines.append("")

    # Separate class tests from standalone tests
    class_tests: Dict[str, List[TestCase]] = {}
    standalone_tests: List[TestCase] = []

    for tc in test_module.test_cases:
        if tc._is_class_test:
            key = tc.target_name
            class_tests.setdefault(key, []).append(tc)
        else:
            standalone_tests.append(tc)

    # Render standalone tests
    for tc in standalone_tests:
        for m in tc.markers:
            lines.append(f"@pytest.mark.{m}")
        if "asyncio" in tc.markers:
            lines.append(f"async def {tc.test_name}():")
        else:
            lines.append(f"def {tc.test_name}():")
        lines.append(f'    """{tc.description}"""')
        for body_line in tc.test_body.split("\n"):
            lines.append(f"    {body_line}")
        lines.append("")
        lines.append("")

    # Render class-grouped tests
    for cls_name, cases in class_tests.items():
        lines.append(f"class Test{cls_name}:")
        lines.append(f'    """Tests for {cls_name}."""')
        lines.append("")

        for tc in cases:
            for m in tc.markers:
                lines.append(f"    @pytest.mark.{m}")
            if "asyncio" in tc.markers:
                lines.append(f"    async def {tc.test_name}(self):")
            else:
                lines.append(f"    def {tc.test_name}(self):")
            lines.append(f'        """{tc.description}"""')
            for body_line in tc.test_body.split("\n"):
                lines.append(f"        {body_line}")
            lines.append("")

        lines.append("")

    source = "\n".join(lines)
    return source


# ============================================================================
# STUB GENERATION
# ============================================================================


def generate_stub_for_class(class_spec: ClassSpec) -> str:
    """
    Generate a stub class implementation.

    * Correct class name and base classes
    * ``__init__`` with correct parameters (body: ``pass``)
    * All methods with correct signatures (body: ``raise NotImplementedError``)
    """
    lines: List[str] = []

    if class_spec.base_classes:
        base_str = ", ".join(class_spec.base_classes)
        lines.append(f"class {class_spec.name}({base_str}):")
    else:
        lines.append(f"class {class_spec.name}:")

    if class_spec.description:
        lines.append(f'    """{class_spec.description}"""')
    lines.append("")

    # __init__
    if class_spec.init_params:
        params = ", ".join(
            f"{p['name']}: {p.get('type', 'Any')}" for p in class_spec.init_params
        )
        lines.append(f"    def __init__(self, {params}):")
    else:
        lines.append("    def __init__(self):")
    lines.append("        pass")
    lines.append("")

    # Methods
    for meth in class_spec.methods:
        # Decorators
        if meth.is_static:
            lines.append("    @staticmethod")
        elif meth.is_classmethod:
            lines.append("    @classmethod")

        # Build parameter list
        if meth.is_static:
            first = []
        elif meth.is_classmethod:
            first = ["cls"]
        else:
            first = ["self"]

        params = first + [
            f"{p['name']}: {p.get('type', 'Any')}" for p in meth.parameters
        ]
        param_str = ", ".join(params)

        async_kw = "async " if meth.is_async else ""
        ret = meth.return_type
        lines.append(f"    {async_kw}def {meth.name}({param_str}) -> {ret}:")

        if meth.description:
            lines.append(f'        """{meth.description}"""')

        lines.append(
            f'        raise NotImplementedError('
            f'"{class_spec.name}.{meth.name} stub — '
            f'requires LLM-driven implementation")'
        )
        lines.append("")

    return "\n".join(lines)


def generate_stub_for_function(func_spec: FunctionSpec) -> str:
    """
    Generate a stub function implementation.

    Correct signature, body: ``raise NotImplementedError``.
    """
    async_kw = "async " if func_spec.is_async else ""
    params = ", ".join(
        f"{p['name']}: {p.get('type', 'Any')}" for p in func_spec.parameters
    )

    lines: List[str] = []
    lines.append(
        f"{async_kw}def {func_spec.name}({params}) -> {func_spec.return_type}:"
    )
    if func_spec.description:
        lines.append(f'    """{func_spec.description}"""')
    lines.append(
        f'    raise NotImplementedError("{func_spec.name} stub — '
        f'requires LLM-driven implementation")'
    )

    return "\n".join(lines)


def build_stub_module(
    module_path: str,
    classes: List[ClassSpec],
    functions: List[FunctionSpec],
) -> StubModule:
    """
    Build a complete stub module from class and function specs.
    """
    lines: List[str] = []
    lines.append(f'"""Stub implementation for {module_path}."""')
    lines.append("")

    # Check if Any is used
    needs_any = False
    for cs in classes:
        for p in cs.init_params:
            if p.get("type", "Any") == "Any":
                needs_any = True
        for m in cs.methods:
            for p in m.parameters:
                if p.get("type", "Any") == "Any":
                    needs_any = True
    for fs in functions:
        for p in fs.parameters:
            if p.get("type", "Any") == "Any":
                needs_any = True

    if needs_any:
        lines.append("from typing import Any")
        lines.append("")

    for cs in classes:
        lines.append(generate_stub_for_class(cs))
        lines.append("")

    for fs in functions:
        lines.append(generate_stub_for_function(fs))
        lines.append("")

    content = "\n".join(lines)
    filepath = module_path.replace(".", os.sep) + ".py"

    return StubModule(filepath=filepath, content=content)


# ============================================================================
# FILESYSTEM OPERATIONS
# ============================================================================


def _ensure_init_py(directory: Path) -> None:
    """Create ``__init__.py`` in *directory* if it doesn't exist."""
    directory.mkdir(parents=True, exist_ok=True)
    init_file = directory / "__init__.py"
    if not init_file.exists():
        init_file.write_text("")


def write_modules_to_disk(
    test_modules: List[TestModule],
    stub_modules: List[StubModule],
    output_dir: Path,
) -> Tuple[List[Path], List[Path]]:
    """
    Write generated test and stub modules to the filesystem.

    Creates necessary directories and ``__init__.py`` files.

    Returns:
        Tuple of ``(test_file_paths, stub_file_paths)``.

    Raises:
        SyntaxError: If generated code has syntax errors.
        OSError: On filesystem failures.
    """
    test_files: List[Path] = []
    stub_files: List[Path] = []

    # -- Write stub modules first (tests import them) --
    stub_dir = output_dir / "src"
    for stub_module in stub_modules:
        stub_path = stub_dir / stub_module.filepath
        stub_path.parent.mkdir(parents=True, exist_ok=True)

        # Create __init__.py up the tree
        current = stub_path.parent
        while current >= stub_dir:
            _ensure_init_py(current)
            if current == stub_dir:
                break
            current = current.parent

        compile(stub_module.content, str(stub_path), "exec")
        stub_path.write_text(stub_module.content)
        logger.info("Wrote stub module %s", stub_path)
        stub_files.append(stub_path)

    # -- Write test modules --
    test_dir = output_dir / "tests"
    _ensure_init_py(test_dir)

    for test_module in test_modules:
        test_path = test_dir / test_module.filename
        code = render_test_module(test_module)

        compile(code, str(test_path), "exec")
        test_path.write_text(code)
        logger.info("Wrote test module %s", test_path)
        test_files.append(test_path)

    return test_files, stub_files


# ============================================================================
# PYTEST VALIDATION
# ============================================================================


def validate_pytest_collection(
    test_dir: Path,
    stub_dir: Optional[Path] = None,
) -> CollectionResult:
    """
    Validate that pytest can collect all tests in *test_dir*.

    Uses ``pytest.main`` with ``--collect-only`` to verify collection.
    Optionally adds *stub_dir* to ``sys.path`` so stub imports resolve.
    """
    try:
        import pytest as _pytest
    except ImportError:
        return CollectionResult(
            success=False,
            collected_count=0,
            errors=["pytest is not installed"],
        )

    original_path = sys.path[:]
    if stub_dir and stub_dir.exists():
        sys.path.insert(0, str(stub_dir))

    try:

        class _CollectionPlugin:
            def __init__(self):
                self.collected: List[Any] = []
                self.errors: List[str] = []

            def pytest_collection_modifyitems(self, items):
                self.collected.extend(items)

            def pytest_collectreport(self, report):
                if report.failed:
                    self.errors.append(str(report.longrepr))

        plugin = _CollectionPlugin()
        exit_code = _pytest.main(
            ["--collect-only", "-q", str(test_dir)],
            plugins=[plugin],
        )

        success = exit_code == 0 and len(plugin.errors) == 0
        collected_count = len(plugin.collected)
        test_node_ids = [item.nodeid for item in plugin.collected]

        logger.info(
            "Pytest collection: %s, collected %d tests",
            "SUCCESS" if success else "FAILED",
            collected_count,
        )

        return CollectionResult(
            success=success,
            collected_count=collected_count,
            errors=plugin.errors,
            test_node_ids=test_node_ids,
        )
    finally:
        sys.path[:] = original_path


# ============================================================================
# LLM PROMPT TEMPLATES — loaded from test_construction.yaml
# ============================================================================

_log = get_logger(__name__)


def _format_test_prompt(template_name: str, **kwargs: Any) -> Optional[str]:
    """Load and format a template from ``test_construction.yaml``.

    Returns the formatted string on success, or ``None`` when the YAML
    file or template is unavailable (e.g. downstream installs that
    haven't updated).
    """
    try:
        from startd8.contractors.artisan_phases.prompts import format_prompt

        return format_prompt("test_construction", template_name, **kwargs)
    except (FileNotFoundError, KeyError) as exc:
        _log.debug(
            "YAML template test_construction/%s unavailable, using inline fallback: %s",
            template_name,
            exc,
        )
        return None


def _get_test_template(template_name: str) -> Optional[str]:
    """Load a raw template from ``test_construction.yaml`` without formatting.

    Returns the template string on success, or ``None`` when unavailable.
    """
    try:
        from startd8.contractors.artisan_phases.prompts import get_template

        return get_template("test_construction", template_name)
    except (FileNotFoundError, KeyError) as exc:
        _log.debug(
            "YAML template test_construction/%s unavailable, using inline fallback: %s",
            template_name,
            exc,
        )
        return None


# -- Inline fallbacks (used only when test_construction.yaml is missing) ------

_LLM_TEST_SYSTEM_PROMPT_FALLBACK = """\
You are an expert Python test engineer. You write thorough, production-quality
pytest test suites.

Rules:
- Output ONLY valid Python source code inside a single markdown ```python
  code fence.
- Use pytest idioms: fixtures, parametrize, marks, clear AAA structure.
- Every assertion must test a concrete, meaningful property — never use
  ``assert result is not None`` as the sole assertion.
- Include ``import pytest`` and any necessary standard-library imports at the
  top.
- Import the module under test with ``from <module_path> import *`` where
  <module_path> is provided in the spec.
- Group tests for the same class inside ``class Test<ClassName>:``.
- Mark async tests with ``@pytest.mark.asyncio``.
- Provide realistic @pytest.fixture definitions for non-trivial setup.
- Cover happy-path, error-path (pytest.raises), and edge-case scenarios.
- Do NOT include implementation stubs — only test code.
- Do NOT include explanatory prose outside the code fence.
"""

_LLM_TEST_FROM_DESIGN_PROMPT_FALLBACK = """\
Generate a comprehensive pytest test suite for the following feature.

## Feature: {feature_name}

{feature_description}

## Design Document

{design_content}

## Module Paths

{module_paths}

## Requirements

1. Write tests for every class, method, and function described in the design.
2. Include meaningful fixtures that construct objects with realistic data.
3. Discover and test edge cases implied by the design (boundary values,
   empty inputs, concurrent access, type errors, etc.).
4. Each test must have at least one concrete assertion beyond ``is not None``.
5. Group tests by class using ``class Test<ClassName>:`` blocks.
6. Standalone function tests are top-level ``def test_…()`` functions.
"""

_LLM_TEST_FROM_IMPL_PROMPT_FALLBACK = """\
Generate a comprehensive pytest test suite that verifies the following
implementation meets its design specification.

## Feature: {feature_name}

{feature_description}

## Design Document

{design_content}

## Implementation Code

```python
{implementation_code}
```

## Module Paths

{module_paths}

## Requirements

1. Write tests that verify the implementation against the design contract.
2. Test actual return values, side effects, and state changes — not just
   ``is not None``.
3. Include fixtures that construct objects matching the implementation's
   constructor signatures.
4. Test error paths: feed invalid inputs and assert specific exceptions.
5. Cover edge cases visible in the implementation (empty collections,
   boundary values, None parameters, concurrent calls for async code).
6. Group tests by class using ``class Test<ClassName>:`` blocks.
"""

_LLM_TEST_RETRY_PROMPT_FALLBACK = """\
The previously generated test code failed pytest collection with the
following errors.  Please fix the issues and regenerate the complete test
file.

## Previous Test Code

```python
{previous_code}
```

## Collection Errors

{collection_errors}

## Instructions

- Fix all import errors, syntax errors, and name resolution issues.
- Preserve the test intent — do not remove tests, only fix problems.
- Output the complete, corrected test file inside a single ```python fence.
"""


def _get_test_system_prompt() -> str:
    """Return the test system prompt, preferring YAML over fallback."""
    tmpl = _get_test_template("test_system")
    if tmpl is not None:
        return tmpl.rstrip("\n")
    return _LLM_TEST_SYSTEM_PROMPT_FALLBACK


# ============================================================================
# LLM TEST GENERATOR
# ============================================================================


class LLMTestGenerator:
    """LLM-driven test generator that produces meaningful pytest suites.

    Replaces the mechanical template generator when an LLM agent is
    available.  The LLM reads the design document (and optionally the
    implementation code) and writes tests with real assertions,
    meaningful fixtures, and discovered edge cases.

    Follows the same lazy-resolution, cost-tracking patterns as
    :class:`~startd8.contractors.artisan_phases.development.LLMChunkExecutor`
    and :class:`~startd8.contractors.artisan_phases.design_documentation.AgentLLMBackend`.

    Args:
        agent_spec: Agent specification string (e.g.
            ``DRAFT_MODEL_CLAUDE_HAIKU.agent_spec``).
        max_tokens: ``max_tokens`` override for the agent.
        max_retries: Maximum error-informed retry attempts when pytest
            collection fails (default ``2``).

    Example::

        gen = LLMTestGenerator(DRAFT_MODEL_CLAUDE_HAIKU.agent_spec)
        modules = await gen.generate_tests(design_doc)
        print(modules[0].filename)
    """

    def __init__(
        self,
        agent_spec: str,
        max_tokens: int = 64000,
        max_retries: int = 2,
        parameter_sources: Optional[Dict[str, Any]] = None,
        semantic_conventions: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._agent_spec = agent_spec
        self._max_tokens = max_tokens
        if max_retries < 0:
            raise ValueError(f"max_retries must be >= 0, got {max_retries}")
        self._max_retries = max_retries
        self._parameter_sources = parameter_sources
        self._semantic_conventions = semantic_conventions

        # Lazily resolved agent (cached after first call)
        self._agent: Optional[Any] = None

        # Accumulated cost metrics
        self.total_cost_usd: float = 0.0
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0

        self.logger = get_logger(__name__)

    # ------------------------------------------------------------------
    # Agent resolution (lazy, cached)
    # ------------------------------------------------------------------

    def _resolve_agent(self) -> Any:
        """Resolve the agent spec to a BaseAgent (cached)."""
        if self._agent is not None:
            return self._agent

        from startd8.utils.agent_resolution import resolve_agent_spec

        self.logger.info("Resolving test-gen agent: %s", self._agent_spec)
        self._agent = resolve_agent_spec(
            self._agent_spec,
            name="test-generator",
            max_tokens=self._max_tokens,
        )
        return self._agent

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    def _build_design_content(
        self,
        design: DesignDocument,
        design_phase_doc: Optional["DesignPhaseDocument"] = None,
    ) -> str:
        """Build the design content string for the prompt.

        Uses the rich markdown from the design documentation phase when
        available (Option A bridging), falling back to a structured
        rendering of the parsed ``DesignDocument`` specs.

        Args:
            design: Parsed test-construction ``DesignDocument``.
            design_phase_doc: Optional design-phase ``DesignDocument``
                with rich markdown sections.

        Returns:
            Formatted design content string.
        """
        # Option A: use raw markdown from the design documentation phase
        if design_phase_doc is not None and design_phase_doc.raw_text:
            return design_phase_doc.raw_text

        # Fallback: structured rendering from parsed specs
        parts: List[str] = []
        if design.description:
            parts.append(f"**Description:** {design.description}")

        if design.classes:
            parts.append("\n### Classes\n")
            for cls in design.classes:
                parts.append(f"**{cls.name}** (`{cls.module_path}`)")
                if cls.description:
                    parts.append(f"  {cls.description}")
                if cls.base_classes:
                    parts.append(
                        f"  Inherits: {', '.join(cls.base_classes)}"
                    )
                if cls.init_params:
                    param_strs = [
                        f"{p['name']}: {p.get('type', 'Any')}"
                        for p in cls.init_params
                    ]
                    parts.append(f"  __init__({', '.join(param_strs)})")
                for meth in cls.methods:
                    async_kw = "async " if meth.is_async else ""
                    param_strs = [
                        f"{p['name']}: {p.get('type', 'Any')}"
                        for p in meth.parameters
                    ]
                    sig = f"{async_kw}{meth.name}({', '.join(param_strs)}) -> {meth.return_type}"
                    parts.append(f"  - `{sig}`")
                    if meth.description:
                        parts.append(f"    {meth.description}")
                    if meth.raises:
                        parts.append(
                            f"    Raises: {', '.join(meth.raises)}"
                        )

        if design.functions:
            parts.append("\n### Functions\n")
            for fn in design.functions:
                async_kw = "async " if fn.is_async else ""
                param_strs = [
                    f"{p['name']}: {p.get('type', 'Any')}"
                    for p in fn.parameters
                ]
                sig = f"{async_kw}{fn.name}({', '.join(param_strs)}) -> {fn.return_type}"
                parts.append(f"**`{sig}`** (`{fn.module_path}`)")
                if fn.description:
                    parts.append(f"  {fn.description}")
                if fn.raises:
                    parts.append(f"  Raises: {', '.join(fn.raises)}")

        if design.edge_cases:
            parts.append("\n### Edge Cases\n")
            for ec in design.edge_cases:
                desc = ec.get("description", "")
                target = ec.get("target", "")
                expected = ec.get("expected", "")
                parts.append(f"- **{target}**: {desc} → {expected}")

        return "\n".join(parts)

    def _collect_module_paths(self, design: DesignDocument) -> str:
        """Collect unique module paths from the design for import hints."""
        paths: Dict[str, None] = {}
        for cls in design.classes:
            paths[cls.module_path] = None
        for fn in design.functions:
            paths[fn.module_path] = None
        if not paths:
            fallback = design.feature_name.replace(" ", "_").lower()
            paths[fallback] = None
        lines = [f"- `{p}`" for p in paths]
        return "\n".join(lines)

    def _build_generation_prompt(
        self,
        design: DesignDocument,
        implementation_code: Optional[str] = None,
        design_phase_doc: Optional["DesignPhaseDocument"] = None,
    ) -> str:
        """Build the full user prompt for test generation.

        When *implementation_code* is provided the prompt asks the LLM
        to verify the implementation against the design.  Otherwise it
        generates tests from the design spec alone.

        Args:
            design: Parsed test-construction ``DesignDocument``.
            implementation_code: Optional source code from the
                development phase.
            design_phase_doc: Optional rich design-phase document.

        Returns:
            Formatted prompt string.
        """
        design_content = self._build_design_content(
            design, design_phase_doc
        )
        module_paths = self._collect_module_paths(design)

        # Build optional context sections
        extra_sections: List[str] = []
        if self._parameter_sources:
            extra_sections.append(
                "\n## Parameter Sources\n\n"
                + "\n".join(f"- **{k}**: {v}" for k, v in self._parameter_sources.items())
            )
        if self._semantic_conventions:
            extra_sections.append(
                "\n## Semantic Conventions\n\n"
                + "\n".join(f"- **{k}**: {v}" for k, v in self._semantic_conventions.items())
            )
        extra_context = "\n".join(extra_sections)

        if implementation_code:
            prompt = _format_test_prompt(
                "test_from_impl",
                feature_name=design.feature_name,
                feature_description=design.description or "(no description)",
                design_content=design_content,
                implementation_code=implementation_code,
                module_paths=module_paths,
            )
            if prompt is None:
                prompt = _LLM_TEST_FROM_IMPL_PROMPT_FALLBACK.format(
                    feature_name=design.feature_name,
                    feature_description=design.description or "(no description)",
                    design_content=design_content,
                    implementation_code=implementation_code,
                    module_paths=module_paths,
                )
        else:
            prompt = _format_test_prompt(
                "test_from_design",
                feature_name=design.feature_name,
                feature_description=design.description or "(no description)",
                design_content=design_content,
                module_paths=module_paths,
            )
            if prompt is None:
                prompt = _LLM_TEST_FROM_DESIGN_PROMPT_FALLBACK.format(
                    feature_name=design.feature_name,
                    feature_description=design.description or "(no description)",
                    design_content=design_content,
                    module_paths=module_paths,
                )
        if extra_context:
            prompt += extra_context
        return prompt

    def _build_retry_prompt(
        self,
        previous_code: str,
        collection_errors: List[str],
    ) -> str:
        """Build the retry prompt when pytest collection fails."""
        prompt = _format_test_prompt(
            "test_retry",
            previous_code=previous_code,
            collection_errors="\n".join(collection_errors),
        )
        if prompt is not None:
            return prompt
        return _LLM_TEST_RETRY_PROMPT_FALLBACK.format(
            previous_code=previous_code,
            collection_errors="\n".join(collection_errors),
        )

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _extract_code(self, response: str) -> str:
        """Extract Python code from the LLM response.

        Uses the SDK's :func:`extract_code_from_response` utility.
        """
        from startd8.utils.code_extraction import extract_code_from_response

        return extract_code_from_response(response, language="python")

    def _parse_into_test_modules(
        self,
        code: str,
        design: DesignDocument,
    ) -> List[TestModule]:
        """Parse extracted code into ``TestModule`` objects.

        For simplicity, the LLM-generated code is wrapped in a single
        ``TestModule`` with the source stored directly.  The module's
        ``test_cases`` list receives a single synthetic ``TestCase``
        whose ``test_body`` is the full rendered source, allowing the
        phase to still inspect it structurally if needed.

        Multiple-module output (one per module_path) is attempted by
        scanning for ``# --- module: <path> ---`` markers the LLM may
        emit; otherwise everything goes into one module.
        """
        modules: List[TestModule] = []

        # Attempt multi-module split via markers
        marker_pattern = r"# ---\s*module:\s*(\S+)\s*---"
        marker_splits = re.split(marker_pattern, code)

        if len(marker_splits) > 1:
            # marker_splits = [preamble, mod1_path, mod1_code, mod2_path, ...]
            preamble = marker_splits[0].strip()
            _is_first_module = True
            for i in range(1, len(marker_splits), 2):
                mod_path = marker_splits[i]
                mod_code = (
                    marker_splits[i + 1].strip()
                    if i + 1 < len(marker_splits)
                    else ""
                )
                # M-13: Only prepend preamble (shared imports, docstring) to
                # the first/primary module. Secondary modules get their own
                # imports as generated by the LLM — prepending the primary
                # module's preamble to every file produces invalid code.
                if preamble and _is_first_module:
                    mod_code = preamble + "\n\n" + mod_code
                    _is_first_module = False
                if not mod_code.strip():
                    logger.warning(
                        "Skipping empty module: %s", mod_path
                    )
                    continue
                basename = mod_path.split(".")[-1]
                filename = f"test_{basename}.py"
                modules.append(
                    TestModule(
                        filename=filename,
                        imports=["import pytest"],  # metadata only; LLM modules render from test_body
                        test_cases=[
                            TestCase(
                                test_name="__llm_generated__",
                                test_type=TestType.UNIT,
                                target_name=mod_path,
                                target_method=None,
                                description="LLM-generated test suite",
                                test_body=mod_code,
                            )
                        ],
                        fixtures=[],
                    )
                )
            return modules

        # Single module — derive filename from the first module_path
        module_paths: List[str] = []
        for cls in design.classes:
            if cls.module_path not in module_paths:
                module_paths.append(cls.module_path)
        for fn in design.functions:
            if fn.module_path not in module_paths:
                module_paths.append(fn.module_path)

        if module_paths:
            basename = module_paths[0].split(".")[-1]
        else:
            basename = design.feature_name.replace(" ", "_").lower()
        filename = f"test_{basename}.py"

        modules.append(
            TestModule(
                filename=filename,
                imports=["import pytest"],  # metadata only; LLM modules render from test_body
                test_cases=[
                    TestCase(
                        test_name="__llm_generated__",
                        test_type=TestType.UNIT,
                        target_name=design.feature_name,
                        target_method=None,
                        description="LLM-generated test suite",
                        test_body=code,
                    )
                ],
                fixtures=[],
            )
        )
        return modules

    # ------------------------------------------------------------------
    # Core generation
    # ------------------------------------------------------------------

    async def generate_tests(
        self,
        design: DesignDocument,
        implementation_code: Optional[str] = None,
        design_phase_doc: Optional["DesignPhaseDocument"] = None,
    ) -> List[TestModule]:
        """Generate a test suite via the LLM.

        Args:
            design: Parsed test-construction ``DesignDocument``.
            implementation_code: Optional implementation source code.
                When provided the LLM writes tests that verify the
                implementation against the design contract.
            design_phase_doc: Optional rich ``DesignDocument`` from the
                design documentation phase (provides full markdown
                sections for richer context).

        Returns:
            List of ``TestModule`` objects containing LLM-generated tests.

        Raises:
            RuntimeError: If the LLM returns empty code after extraction.
        """
        agent = self._resolve_agent()

        prompt = self._build_generation_prompt(
            design, implementation_code, design_phase_doc
        )

        self.logger.info(
            "Generating tests via LLM for '%s' (prompt %d chars, "
            "has implementation: %s)",
            design.feature_name,
            len(prompt),
            implementation_code is not None,
        )

        _span_ctx = _test_tracer.start_as_current_span(
            "test.generate",
            attributes={
                "test.feature_name": design.feature_name,
                "test.prompt_length": len(prompt),
                "test.has_implementation": implementation_code is not None,
            },
        )
        with _span_ctx as _test_span:
            response_text, time_ms, token_usage = await agent.agenerate(
                prompt, system_prompt=_get_test_system_prompt(),
            )

            # Accumulate cost metrics
            self.total_cost_usd += token_usage_cost(token_usage)
            self.total_input_tokens += token_usage_input(token_usage)
            self.total_output_tokens += token_usage_output(token_usage)

            self.logger.info(
                "LLM test generation for '%s': %dms, %d in / %d out tokens, "
                "$%.4f",
                design.feature_name,
                time_ms,
                token_usage_input(token_usage),
                token_usage_output(token_usage),
                token_usage_cost(token_usage),
            )

            if _test_span and hasattr(_test_span, "set_attribute"):
                _test_span.set_attribute("test.response_time_ms", time_ms)
                _test_span.set_attribute("test.tokens_input", token_usage_input(token_usage))
                _test_span.set_attribute("test.tokens_output", token_usage_output(token_usage))
                _test_span.set_attribute("test.cost_usd", token_usage_cost(token_usage))

            # CS5: Forensic log for test.generate
            from startd8.contractors.forensic_log import emit_forensic_log
            emit_forensic_log(
                call_type="test.generate",
                call={
                    "prompt_length": len(prompt),
                    "max_tokens": self._max_tokens,
                    "model_spec": self._agent_spec,
                    "response_time_ms": time_ms,
                    "tokens_input": token_usage_input(token_usage),
                    "tokens_output": token_usage_output(token_usage),
                    "cost_usd": token_usage_cost(token_usage),
                },
                task={
                    "title": design.feature_name,
                    "phase": "test",
                },
                context_propagation={
                    "design_doc_present": implementation_code is not None or design_phase_doc is not None,
                    "existing_file_inventory_present": implementation_code is not None,
                },
            )

        code = self._extract_code(response_text)
        if not code or not code.strip():
            raise RuntimeError(
                f"LLM returned empty test code for '{design.feature_name}'"
            )

        return self._parse_into_test_modules(code, design)

    async def retry_with_errors(
        self,
        previous_code: str,
        collection_errors: List[str],
        design: DesignDocument,
    ) -> List[TestModule]:
        """Re-generate tests incorporating pytest collection errors.

        Args:
            previous_code: The test code that failed collection.
            collection_errors: Error messages from pytest collection.
            design: The design document (for module path derivation).

        Returns:
            List of corrected ``TestModule`` objects.
        """
        agent = self._resolve_agent()

        prompt = self._build_retry_prompt(previous_code, collection_errors)

        self.logger.info(
            "Retrying test generation for '%s' with %d collection errors",
            design.feature_name,
            len(collection_errors),
        )

        response_text, time_ms, token_usage = await agent.agenerate(
            prompt, system_prompt=_get_test_system_prompt(),
        )

        self.total_cost_usd += token_usage_cost(token_usage)
        self.total_input_tokens += token_usage_input(token_usage)
        self.total_output_tokens += token_usage_output(token_usage)

        self.logger.info(
            "LLM retry for '%s': %dms, $%.4f",
            design.feature_name,
            time_ms,
            token_usage_cost(token_usage),
        )

        # CS6: Forensic log for test.retry
        from startd8.contractors.forensic_log import emit_forensic_log
        emit_forensic_log(
            call_type="test.retry",
            call={
                "prompt_length": len(prompt),
                "max_tokens": self._max_tokens,
                "model_spec": self._agent_spec,
                "response_time_ms": time_ms,
                "tokens_input": token_usage_input(token_usage),
                "tokens_output": token_usage_output(token_usage),
                "cost_usd": token_usage_cost(token_usage),
                "attempt": 2,  # retry is always attempt >= 2
            },
            task={
                "title": design.feature_name,
                "phase": "test",
            },
            context_propagation={
                "design_doc_present": True,
            },
        )

        code = self._extract_code(response_text)
        if not code or not code.strip():
            raise RuntimeError(
                f"LLM returned empty test code for '{design.feature_name}' (retry)"
            )

        return self._parse_into_test_modules(code, design)


# ============================================================================
# PHASE CLASS
# ============================================================================


class TestConstructionPhase:
    """Artisan phase that generates tests from a design document.

    Supports two generation strategies:

    - **Template-based** (default, synchronous) — produces mechanical
      boilerplate from parsed specs.  Use via :meth:`execute`.
    - **LLM-driven** (when ``agent_spec`` is provided, async) — an LLM
      generates meaningful tests with real assertions, fixtures, and
      discovered edge cases.  Use via :meth:`execute_async`.

    Usage::

        # Template-based (original behaviour)
        phase = TestConstructionPhase(design_doc=my_design_dict)
        result = phase.execute()

        # LLM-driven
        phase = TestConstructionPhase(
            design_doc=my_design_dict,
            agent_spec=DRAFT_MODEL_CLAUDE_HAIKU.agent_spec,
            implementation_code=src_code,
        )
        result = await phase.execute_async()
    """

    def __init__(
        self,
        design_doc: Dict[str, Any],
        output_dir: Optional[Path] = None,
        validate: bool = True,
        agent_spec: Optional[str] = None,
        implementation_code: Optional[str] = None,
        design_phase_doc: Optional["DesignPhaseDocument"] = None,
        max_retries: int = 2,
        parameter_sources: Optional[Dict[str, Any]] = None,
        semantic_conventions: Optional[Dict[str, Any]] = None,
        element_registry: Optional[Any] = None,
    ):
        """
        Initialize the Test Construction Phase.

        Args:
            design_doc: Raw design document as a dictionary.
            output_dir: Where to write generated files.  Defaults to a
                temp directory.
            validate: Whether to run pytest collection validation after
                generation.
            agent_spec: Optional LLM agent specification.  When set the
                phase uses :class:`LLMTestGenerator` for intelligent
                test authoring instead of the template generator.
            implementation_code: Optional source code from the
                development phase.  Passed to the LLM for writing tests
                that verify the implementation against the design.
            design_phase_doc: Optional rich ``DesignDocument`` from the
                design documentation phase (the one with 7 markdown
                sections).  Provides richer context to the LLM.
            max_retries: Maximum error-informed retry attempts when
                pytest collection fails (LLM path only).
            parameter_sources: Optional dict of parameter source
                mappings forwarded to the LLM for context.
            semantic_conventions: Optional dict of semantic convention
                mappings forwarded to the LLM for context.
            element_registry: Optional element registry for recording
                test coverage per element (ER-009).
        """
        self.raw_design = design_doc
        self.output_dir = output_dir or Path(
            tempfile.mkdtemp(prefix="test_construction_")
        )
        self.validate = validate
        self.agent_spec = agent_spec
        self.implementation_code = implementation_code
        self.design_phase_doc = design_phase_doc
        self.max_retries = max_retries
        self.parameter_sources = parameter_sources
        self.semantic_conventions = semantic_conventions
        self._element_registry = element_registry
        self.status = PhaseStatus.NOT_STARTED
        self._result: Optional[PhaseResult] = None

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _parse_design(self, result: PhaseResult) -> Optional[DesignDocument]:
        """Parse the raw design document.  Mutates *result* on failure."""
        logger.info("Step 1: Parsing design document")
        try:
            return parse_design_document(self.raw_design)
        except ValueError as exc:
            logger.error("Failed to parse design document: %s", exc)
            result.status = PhaseStatus.FAILED
            result.errors.append(f"Design document parsing failed: {exc}")
            return None

    def _build_stubs(
        self, design: DesignDocument
    ) -> List[StubModule]:
        """Build stub modules from the parsed design."""
        logger.info("Building stub modules from parsed design")
        stubs_by_module: Dict[str, Dict[str, list]] = {}
        for cls_spec in design.classes:
            stubs_by_module.setdefault(
                cls_spec.module_path, {"classes": [], "functions": []}
            )["classes"].append(cls_spec)
        for fn_spec in design.functions:
            stubs_by_module.setdefault(
                fn_spec.module_path, {"classes": [], "functions": []}
            )["functions"].append(fn_spec)

        stub_modules: List[StubModule] = []
        for mod_path, specs in stubs_by_module.items():
            sm = build_stub_module(
                mod_path, specs["classes"], specs["functions"]
            )
            stub_modules.append(sm)
        return stub_modules

    def _write_to_disk(
        self,
        test_modules: List[TestModule],
        stub_modules: List[StubModule],
        result: PhaseResult,
    ) -> bool:
        """Write modules to disk.  Returns False on failure."""
        logger.info("Writing test and stub modules to disk")
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            write_modules_to_disk(
                test_modules, stub_modules, self.output_dir
            )
            return True
        except SyntaxError as exc:
            logger.error("Syntax error in generated code: %s", exc)
            result.status = PhaseStatus.FAILED
            result.errors.append(f"Syntax error in generated code: {exc}")
            return False
        except OSError as exc:
            logger.error("Filesystem error: %s", exc)
            result.status = PhaseStatus.FAILED
            result.errors.append(f"Filesystem error: {exc}")
            return False

    def _validate_collection(self, result: PhaseResult) -> None:
        """Run pytest collection validation.  Mutates *result*."""
        if not self.validate:
            logger.info("Pytest validation skipped")
            result.status = PhaseStatus.SUCCESS
            return

        logger.info("Validating pytest collection")
        test_dir = self.output_dir / "tests"
        stub_dir = self.output_dir / "src"
        collection = validate_pytest_collection(test_dir, stub_dir)
        result.collection_result = collection

        if not collection.success:
            logger.warning(
                "Pytest collection had issues: %s", collection.errors
            )
            result.status = PhaseStatus.PARTIAL
            result.errors.extend(collection.errors)
        else:
            logger.info(
                "Pytest collection OK: %d tests",
                collection.collected_count,
            )
            result.status = PhaseStatus.SUCCESS

    def _record_test_coverage(self, result: PhaseResult) -> None:
        """Record test coverage in element registry (ER-009).

        For each test module, mark the target elements as having test
        coverage in the element registry.  Advisory — never blocks.
        """
        if self._element_registry is None:
            return
        try:
            test_count = 0
            for module in (result.test_modules or []):
                for tc in module.test_cases:
                    target_name = getattr(tc, "target_name", "")
                    if not target_name:
                        continue
                    # Look up elements matching this target
                    for entry in self._element_registry.all_entries():
                        if entry.name == target_name:
                            self._element_registry.set_phase_status(
                                entry.element_id,
                                "test",
                                "covered",
                                metadata={
                                    "test_name": tc.test_name,
                                    "status": result.status.value,
                                },
                            )
                            test_count += 1
            if test_count > 0:
                logger.info(
                    "ER-009: Recorded test coverage for %d elements",
                    test_count,
                )
        except Exception as exc:
            logger.debug("Element registry test coverage recording failed: %s", exc)

    # ------------------------------------------------------------------
    # LLM helpers
    # ------------------------------------------------------------------

    def _render_llm_module_source(self, module: TestModule) -> str:
        """Render an LLM-generated module to source code.

        If the module was produced by ``LLMTestGenerator`` it contains
        a single ``TestCase`` whose ``test_body`` is the entire file.
        """
        if (
            len(module.test_cases) == 1
            and module.test_cases[0].test_name == "__llm_generated__"
        ):
            return module.test_cases[0].test_body
        return render_test_module(module)

    def _write_llm_modules_to_disk(
        self,
        test_modules: List[TestModule],
        stub_modules: List[StubModule],
        result: PhaseResult,
    ) -> bool:
        """Write LLM-generated test modules and stubs to disk.

        LLM modules bypass ``render_test_module`` because the test_body
        is already complete Python source.
        """
        logger.info("Writing LLM-generated test and stub modules to disk")
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)

            # Write stubs first
            stub_dir = self.output_dir / "src"
            for stub_module in stub_modules:
                stub_path = stub_dir / stub_module.filepath
                stub_path.parent.mkdir(parents=True, exist_ok=True)
                current = stub_path.parent
                while current >= stub_dir:
                    _ensure_init_py(current)
                    if current == stub_dir:
                        break
                    current = current.parent
                compile(stub_module.content, str(stub_path), "exec")
                stub_path.write_text(stub_module.content)
                logger.info("Wrote stub module %s", stub_path)

            # Write test modules
            test_dir = self.output_dir / "tests"
            _ensure_init_py(test_dir)
            for module in test_modules:
                test_path = test_dir / module.filename
                code = self._render_llm_module_source(module)
                compile(code, str(test_path), "exec")
                test_path.write_text(code)
                logger.info("Wrote test module %s", test_path)

            return True
        except SyntaxError as exc:
            logger.error("Syntax error in generated code: %s", exc)
            result.status = PhaseStatus.FAILED
            result.errors.append(f"Syntax error in generated code: {exc}")
            return False
        except OSError as exc:
            logger.error("Filesystem error: %s", exc)
            result.status = PhaseStatus.FAILED
            result.errors.append(f"Filesystem error: {exc}")
            return False

    # ------------------------------------------------------------------
    # Synchronous execute (template path — original behaviour)
    # ------------------------------------------------------------------

    def execute(self) -> PhaseResult:
        """Execute the test construction phase (template-based).

        Steps:
            1. Parse design document
            2. Generate test cases for all classes and functions
            3. Generate edge-case tests
            4. Build test modules
            5. Generate and build stub modules
            6. Write all modules to disk
            7. (Optional) Validate pytest collection

        Returns:
            PhaseResult with status and all generated artifacts.
        """
        self.status = PhaseStatus.IN_PROGRESS
        result = PhaseResult(
            status=PhaseStatus.NOT_STARTED,
            output_dir=str(self.output_dir),
        )

        try:
            # 1. Parse design document
            design = self._parse_design(result)
            if design is None:
                self.status = result.status
                self._result = result
                return result

            # 2. Generate test cases for classes & functions
            logger.info("Step 2: Generating template-based test cases")
            all_test_cases: List[TestCase] = []

            for cls_spec in design.classes:
                cases = generate_test_cases_for_class(cls_spec)
                all_test_cases.extend(cases)

            for fn_spec in design.functions:
                cases = generate_test_cases_for_function(fn_spec)
                all_test_cases.extend(cases)

            # 3. Edge cases
            logger.info("Step 3: Generating edge-case tests")
            edge_tests = generate_edge_case_tests(design.edge_cases, design)
            all_test_cases.extend(edge_tests)

            # Warn about template-generated stubs — these have skip markers
            # and should be replaced by LLM-driven tests when agent_spec is
            # provided.
            stub_count = sum(
                1 for tc in all_test_cases
                if any("Template-generated stub" in m for m in tc.markers)
            )
            if stub_count > 0:
                logger.warning(
                    "Template-based generation produced %d stub test(s) "
                    "marked @pytest.mark.skip. These do NOT validate real "
                    "behavior — provide agent_spec for LLM-driven test "
                    "generation to get meaningful assertions.",
                    stub_count,
                )

            # 4. Build test modules (group by module_path)
            logger.info("Step 4: Building test modules")
            target_to_module: Dict[str, str] = {}
            for cls_spec in design.classes:
                target_to_module[cls_spec.name] = cls_spec.module_path
            for fn_spec in design.functions:
                target_to_module[fn_spec.name] = fn_spec.module_path

            tests_by_module: Dict[str, List[TestCase]] = {}
            for tc in all_test_cases:
                mod_path = target_to_module.get(tc.target_name)
                if mod_path is None:
                    mod_path = design.feature_name.replace(" ", "_").lower()
                tests_by_module.setdefault(mod_path, []).append(tc)

            test_modules: List[TestModule] = []
            for mod_path, cases in tests_by_module.items():
                tm = build_test_module(mod_path, cases, mod_path)
                test_modules.append(tm)

            result.test_modules = test_modules

            # 5. Build stub modules
            stub_modules = self._build_stubs(design)
            result.stub_modules = stub_modules

            # 6. Write to disk
            if not self._write_to_disk(test_modules, stub_modules, result):
                self.status = result.status
                self._result = result
                return result

            # 7. Validate pytest collection
            self._validate_collection(result)

            # 8. Record test coverage in element registry (ER-009)
            self._record_test_coverage(result)

        except Exception as exc:
            logger.exception("Unexpected error during phase execution")
            result.status = PhaseStatus.FAILED
            result.errors.append(f"Unexpected error: {exc}")

        self.status = result.status
        self._result = result
        logger.info(
            "Test Construction Phase completed: %s", result.status.value
        )
        return result

    # ------------------------------------------------------------------
    # Async execute (LLM path)
    # ------------------------------------------------------------------

    async def execute_async(self) -> PhaseResult:
        """Execute the test construction phase with LLM-driven generation.

        When ``agent_spec`` was provided at construction time the phase
        uses :class:`LLMTestGenerator` for intelligent test authoring.
        If no ``agent_spec`` is set this falls back to the synchronous
        template-based ``execute()`` method directly.

        Steps:
            1. Parse design document
            2. Generate tests via LLM (with optional implementation code)
            3. Build stub modules
            4. Write all modules to disk
            5. Validate pytest collection
            6. Error-informed retry (if collection failed, up to
               ``max_retries`` times)

        Returns:
            PhaseResult with status, generated artifacts, and cost
            metrics.
        """
        if self.agent_spec is None:
            # No LLM — fall back to template path
            return await asyncio.to_thread(self.execute)

        self.status = PhaseStatus.IN_PROGRESS
        result = PhaseResult(
            status=PhaseStatus.NOT_STARTED,
            output_dir=str(self.output_dir),
        )

        try:
            # 1. Parse design document
            design = self._parse_design(result)
            if design is None:
                self.status = result.status
                self._result = result
                return result

            # 2. Generate tests via LLM
            logger.info("Step 2: Generating tests via LLM (%s)", self.agent_spec)
            llm_gen = LLMTestGenerator(
                agent_spec=self.agent_spec,
                max_retries=self.max_retries,
                parameter_sources=self.parameter_sources,
                semantic_conventions=self.semantic_conventions,
            )

            try:
                test_modules = await llm_gen.generate_tests(
                    design=design,
                    implementation_code=self.implementation_code,
                    design_phase_doc=self.design_phase_doc,
                )
            except Exception as gen_exc:
                logger.warning(
                    "LLM test generation failed (%s), falling back to "
                    "template generator",
                    gen_exc,
                )
                result.errors.append(
                    f"LLM generation failed (falling back to templates): "
                    f"{gen_exc}"
                )
                # Preserve partial costs from agent resolution / LLM call
                partial_cost = llm_gen.total_cost_usd
                partial_input = llm_gen.total_input_tokens
                partial_output = llm_gen.total_output_tokens
                # Fall back to synchronous template path
                template_result = await asyncio.to_thread(self.execute)
                template_result.total_cost_usd += partial_cost
                template_result.total_input_tokens += partial_input
                template_result.total_output_tokens += partial_output
                return template_result

            result.test_modules = test_modules

            # 3. Build stub modules
            stub_modules = self._build_stubs(design)
            result.stub_modules = stub_modules

            # 4. Write to disk (LLM path)
            if not self._write_llm_modules_to_disk(
                test_modules, stub_modules, result
            ):
                self.status = result.status
                self._result = result
                return result

            # 5. Validate pytest collection
            self._validate_collection(result)

            # 6. Error-informed retry loop
            retries = 0
            while (
                self.validate
                and result.collection_result is not None
                and not result.collection_result.success
                and retries < self.max_retries
            ):
                retries += 1
                logger.info(
                    "Error-informed retry %d/%d for '%s'",
                    retries,
                    self.max_retries,
                    design.feature_name,
                )

                # Gather the code that failed
                previous_code_parts: List[str] = []
                for mod in test_modules:
                    previous_code_parts.append(
                        self._render_llm_module_source(mod)
                    )
                previous_code = "\n\n".join(previous_code_parts)

                try:
                    test_modules = await llm_gen.retry_with_errors(
                        previous_code=previous_code,
                        collection_errors=result.collection_result.errors,
                        design=design,
                    )
                except Exception as retry_exc:
                    logger.warning(
                        "Retry %d failed: %s", retries, retry_exc
                    )
                    result.errors.append(
                        f"Retry {retries} failed: {retry_exc}"
                    )
                    break

                result.test_modules = test_modules

                # Re-write and re-validate
                if not self._write_llm_modules_to_disk(
                    test_modules, stub_modules, result
                ):
                    break

                # Clear prior collection errors before re-validating
                result.errors = [
                    e
                    for e in result.errors
                    if "collection" not in e.lower()
                    or "pytest" not in e.lower()
                ]
                result.collection_result = None
                self._validate_collection(result)

            # Populate cost metrics
            result.total_cost_usd = llm_gen.total_cost_usd
            result.total_input_tokens = llm_gen.total_input_tokens
            result.total_output_tokens = llm_gen.total_output_tokens

        except Exception as exc:
            logger.exception("Unexpected error during async phase execution")
            result.status = PhaseStatus.FAILED
            result.errors.append(f"Unexpected error: {exc}")

        self.status = result.status
        self._result = result
        logger.info(
            "Test Construction Phase (LLM) completed: %s "
            "(cost: $%.4f, tokens: %d in / %d out)",
            result.status.value,
            result.total_cost_usd,
            result.total_input_tokens,
            result.total_output_tokens,
        )
        return result

    @property
    def result(self) -> Optional[PhaseResult]:
        """Return the phase result, or ``None`` if not yet executed."""
        return self._result
