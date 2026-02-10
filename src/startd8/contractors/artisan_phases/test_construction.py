"""
Test Construction Phase - TDD test generation from design documents.

This module implements the Test Construction phase of the Artisan contractor
pattern. It generates pytest test files and implementation stubs from a
design document, then validates pytest can collect all tests.
"""

import enum
import logging
import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


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

    # -- returns test --
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
    body_parts.append("assert result is not None  # TODO: assert specific value")

    test_cases.append(
        TestCase(
            test_name=f"test_{san_fn}_returns",
            test_type=TestType.UNIT,
            target_name=fn,
            target_method=None,
            description=f"Verify {fn} returns expected result",
            test_body="\n    ".join(body_parts),
            markers=list(markers),
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
                "    # TODO: set up edge-case conditions\n"
                "    with pytest.raises(Exception):  # TODO: specific exception\n"
                "        pass  # TODO: call target"
            )
        else:
            body = (
                "# Edge case: " + description + "\n"
                "    # TODO: set up edge-case conditions\n"
                "    result = None  # TODO: call target\n"
                "    assert result is not None  # TODO: assert expected"
            )

        # Determine whether this is a class test
        is_class = target_method is not None

        test_cases.append(
            TestCase(
                test_name=test_name,
                test_type=TestType.EDGE_CASE,
                target_name=target_name,
                target_method=target_method,
                description=description,
                test_body=body,
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
        if tc.markers and "asyncio" in tc.markers:
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
            if tc.markers and "asyncio" in tc.markers:
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
            f"        raise NotImplementedError("
            f'"{class_spec.name}.{meth.name} is not yet implemented")'
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
        f'    raise NotImplementedError("{func_spec.name} is not yet implemented")'
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

        success = (
            exit_code == 0 or exit_code == _pytest.ExitCode.NO_TESTS_COLLECTED
            if hasattr(exit_code, "value")
            else exit_code == 0
        ) and len(plugin.errors) == 0
        # Simpler: just check exit code 0 and no errors
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
# PHASE CLASS
# ============================================================================


class TestConstructionPhase:
    """
    Artisan phase that generates tests from a design document.

    Usage::

        phase = TestConstructionPhase(design_doc=my_design_dict)
        result = phase.execute()
        assert result.status == PhaseStatus.SUCCESS
    """

    def __init__(
        self,
        design_doc: Dict[str, Any],
        output_dir: Optional[Path] = None,
        validate: bool = True,
    ):
        """
        Initialize the Test Construction Phase.

        Args:
            design_doc: Raw design document as a dictionary.
            output_dir: Where to write generated files.  Defaults to a temp
                        directory.
            validate: Whether to run pytest collection validation after
                      generation.
        """
        self.raw_design = design_doc
        self.output_dir = output_dir or Path(
            tempfile.mkdtemp(prefix="test_construction_")
        )
        self.validate = validate
        self.status = PhaseStatus.NOT_STARTED
        self._result: Optional[PhaseResult] = None

    def execute(self) -> PhaseResult:
        """
        Execute the test construction phase.

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
            logger.info("Step 1: Parsing design document")
            try:
                design = parse_design_document(self.raw_design)
            except ValueError as exc:
                logger.error("Failed to parse design document: %s", exc)
                result.status = PhaseStatus.FAILED
                result.errors.append(f"Design document parsing failed: {exc}")
                self.status = result.status
                self._result = result
                return result

            # 2. Generate test cases for classes & functions
            logger.info("Step 2: Generating test cases")
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

            # 4. Build test modules (group by module_path)
            logger.info("Step 4: Building test modules")
            # Build a lookup: target_name -> module_path
            target_to_module: Dict[str, str] = {}
            for cls_spec in design.classes:
                target_to_module[cls_spec.name] = cls_spec.module_path
            for fn_spec in design.functions:
                target_to_module[fn_spec.name] = fn_spec.module_path

            tests_by_module: Dict[str, List[TestCase]] = {}
            for tc in all_test_cases:
                mod_path = target_to_module.get(tc.target_name)
                if mod_path is None:
                    # Edge case with unknown target — put in a default module
                    mod_path = design.feature_name.replace(" ", "_").lower()
                tests_by_module.setdefault(mod_path, []).append(tc)

            test_modules: List[TestModule] = []
            for mod_path, cases in tests_by_module.items():
                tm = build_test_module(mod_path, cases, mod_path)
                test_modules.append(tm)

            result.test_modules = test_modules

            # 5. Build stub modules
            logger.info("Step 5: Building stub modules")
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
                sm = build_stub_module(mod_path, specs["classes"], specs["functions"])
                stub_modules.append(sm)

            result.stub_modules = stub_modules

            # 6. Write to disk
            logger.info("Step 6: Writing modules to disk")
            try:
                self.output_dir.mkdir(parents=True, exist_ok=True)
                write_modules_to_disk(test_modules, stub_modules, self.output_dir)
            except SyntaxError as exc:
                logger.error("Syntax error in generated code: %s", exc)
                result.status = PhaseStatus.FAILED
                result.errors.append(f"Syntax error in generated code: {exc}")
                self.status = result.status
                self._result = result
                return result
            except OSError as exc:
                logger.error("Filesystem error: %s", exc)
                result.status = PhaseStatus.FAILED
                result.errors.append(f"Filesystem error: {exc}")
                self.status = result.status
                self._result = result
                return result

            # 7. Validate pytest collection
            if self.validate:
                logger.info("Step 7: Validating pytest collection")
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
                        "Pytest collection OK: %d tests", collection.collected_count
                    )
                    result.status = PhaseStatus.SUCCESS
            else:
                logger.info("Pytest validation skipped")
                result.status = PhaseStatus.SUCCESS

        except Exception as exc:
            logger.exception("Unexpected error during phase execution")
            result.status = PhaseStatus.FAILED
            result.errors.append(f"Unexpected error: {exc}")

        self.status = result.status
        self._result = result
        logger.info("Test Construction Phase completed: %s", result.status.value)
        return result

    @property
    def result(self) -> Optional[PhaseResult]:
        """Return the phase result, or ``None`` if not yet executed."""
        return self._result
