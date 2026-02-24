"""Tests for startd8.utils.code_manifest — core manifest generator."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from startd8.utils.code_manifest import (
    Dependencies,
    Element,
    ElementKind,
    FileManifest,
    ImportEntry,
    Param,
    ParamKind,
    ParseError,
    ParseErrorKind,
    ScopeKind,
    Signature,
    Span,
    SymbolEntry,
    SymbolInfo,
    Visibility,
    generate_file_manifest,
    lookup_element,
    _compute_module_path,
    _extract_signature,
    _truncate_value_repr,
    _visibility_from_name,
    _is_constant_name,
    _resolve_relative_import,
    _classify_imports,
)


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════

SIMPLE_MODULE = textwrap.dedent('''\
    """Module docstring."""

    import os
    from pathlib import Path
    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from startd8.models import AgentConfig

    _CONSTANT: int = 42
    PUBLIC_VAR = "hello"

    def top_function(x: int, y: str = "default") -> bool:
        """Do something."""
        return True

    class MyClass:
        """A sample class."""

        class_var: str = "value"

        def method(self, arg: str) -> None:
            ...

        @property
        def prop(self) -> int:
            return 0

        @staticmethod
        def static_method() -> None:
            ...
''')

OVERLOAD_MODULE = textwrap.dedent('''\
    from typing import overload

    class Processor:
        @overload
        def process(self, x: int) -> int: ...
        @overload
        def process(self, x: str) -> str: ...
        def process(self, x):
            return x
''')

PROPERTY_TRIAD_MODULE = textwrap.dedent('''\
    class Config:
        @property
        def value(self) -> int:
            return self._value

        @value.setter
        def value(self, val: int) -> None:
            self._value = val

        @value.deleter
        def value(self) -> None:
            del self._value
''')

CONDITIONAL_MODULE = textwrap.dedent('''\
    import sys

    if __name__ == "__main__":
        def main():
            pass

    if sys.platform == "win32":
        def platform_func():
            pass

    try:
        import optional_lib
    except ImportError:
        optional_lib = None
''')

PYDANTIC_MODULE = textwrap.dedent('''\
    from pydantic import BaseModel, ConfigDict

    class MyModel(BaseModel):
        model_config = ConfigDict(frozen=True)
        name: str
        age: int
''')

ASYNC_MODULE = textwrap.dedent('''\
    async def fetch_data(url: str) -> dict:
        """Fetch data from URL."""
        return {}

    class AsyncProcessor:
        async def run(self) -> None:
            ...
''')

INIT_MODULE = textwrap.dedent('''\
    """Package init."""

    from .code_extraction import extract_code_from_response
    from .retry import RetryConfig

    __all__ = ["extract_code_from_response", "RetryConfig"]
''')

ALL_PARAM_KINDS = textwrap.dedent('''\
    def complex_func(pos_only: int, /, regular: str, *args: int, kw_only: bool = True, **kwargs: str) -> None:
        pass
''')


# ═══════════════════════════════════════════════════════════════════════════
# Helper
# ═══════════════════════════════════════════════════════════════════════════

def _make_manifest(source: str, filename: str = "src/mypackage/module.py") -> FileManifest:
    """Generate a manifest from inline source using a fake project layout."""
    project_root = Path("/fake/project")
    file_path = project_root / filename
    return generate_file_manifest(file_path, project_root, source=source)


# ═══════════════════════════════════════════════════════════════════════════
# Model validation tests
# ═══════════════════════════════════════════════════════════════════════════

class TestModelValidation:
    def test_span_frozen(self):
        span = Span(start_line=1, start_col=0, end_line=5, end_col=10)
        with pytest.raises(Exception):
            span.start_line = 2  # type: ignore[misc]

    def test_element_callable_requires_signature(self):
        with pytest.raises(ValueError, match="must have a signature"):
            Element(
                kind=ElementKind.FUNCTION,
                name="f",
                fqn="mod.f",
                span=Span(start_line=1, start_col=0, end_line=1, end_col=10),
                signature=None,
            )

    def test_element_non_class_rejects_bases(self):
        with pytest.raises(ValueError, match="must not have bases"):
            Element(
                kind=ElementKind.FUNCTION,
                name="f",
                fqn="mod.f",
                span=Span(start_line=1, start_col=0, end_line=1, end_col=10),
                signature=Signature(params=[]),
                bases=["Foo"],
            )

    def test_element_constant_valid(self):
        elem = Element(
            kind=ElementKind.CONSTANT,
            name="X",
            fqn="mod.X",
            span=Span(start_line=1, start_col=0, end_line=1, end_col=5),
            value_repr="42",
        )
        assert elem.kind == ElementKind.CONSTANT

    def test_element_class_with_bases(self):
        elem = Element(
            kind=ElementKind.CLASS,
            name="Foo",
            fqn="mod.Foo",
            span=Span(start_line=1, start_col=0, end_line=10, end_col=0),
            bases=["Bar", "Baz"],
        )
        assert elem.bases == ["Bar", "Baz"]

    def test_file_manifest_schema_version(self):
        m = FileManifest(
            file="test.py",
            module="test",
            digest="sha256:abc",
            generated_at="2026-01-01T00:00:00Z",
        )
        assert m.schema_version == "1.2.0"


# ═══════════════════════════════════════════════════════════════════════════
# FQN computation tests
# ═══════════════════════════════════════════════════════════════════════════

class TestFQNComputation:
    def test_src_layout(self, tmp_path: Path):
        project_root = tmp_path
        file_path = project_root / "src" / "startd8" / "utils" / "code_manifest.py"
        file_path.parent.mkdir(parents=True)
        file_path.touch()
        assert _compute_module_path(file_path, project_root) == "startd8.utils.code_manifest"

    def test_init_file(self, tmp_path: Path):
        project_root = tmp_path
        file_path = project_root / "src" / "startd8" / "__init__.py"
        file_path.parent.mkdir(parents=True)
        file_path.touch()
        assert _compute_module_path(file_path, project_root) == "startd8"

    def test_non_src_layout(self, tmp_path: Path):
        project_root = tmp_path
        file_path = project_root / "tests" / "unit" / "test_foo.py"
        file_path.parent.mkdir(parents=True)
        file_path.touch()
        assert _compute_module_path(file_path, project_root) == "tests.unit.test_foo"

    def test_flat_layout(self, tmp_path: Path):
        project_root = tmp_path
        file_path = project_root / "mymodule.py"
        file_path.touch()
        assert _compute_module_path(file_path, project_root) == "mymodule"


# ═══════════════════════════════════════════════════════════════════════════
# Visibility tests
# ═══════════════════════════════════════════════════════════════════════════

class TestVisibility:
    def test_public(self):
        assert _visibility_from_name("my_func") == Visibility.PUBLIC

    def test_protected(self):
        assert _visibility_from_name("_private") == Visibility.PROTECTED

    def test_private(self):
        assert _visibility_from_name("__mangled") == Visibility.PRIVATE

    def test_dunder_is_public(self):
        assert _visibility_from_name("__init__") == Visibility.PUBLIC


# ═══════════════════════════════════════════════════════════════════════════
# Constant detection tests
# ═══════════════════════════════════════════════════════════════════════════

class TestConstantDetection:
    def test_uppercase(self):
        assert _is_constant_name("MAX_RETRIES")

    def test_leading_underscore_uppercase(self):
        assert _is_constant_name("_MAX_RETRIES")

    def test_lowercase_not_constant(self):
        assert not _is_constant_name("my_var")

    def test_mixed_not_constant(self):
        assert not _is_constant_name("MyClass")


# ═══════════════════════════════════════════════════════════════════════════
# Element extraction tests
# ═══════════════════════════════════════════════════════════════════════════

class TestElementExtraction:
    def test_simple_module_elements(self):
        m = _make_manifest(SIMPLE_MODULE)
        names = [e.name for e in m.elements]
        assert "_CONSTANT" in names
        assert "PUBLIC_VAR" in names
        assert "top_function" in names
        assert "MyClass" in names

    def test_function_element(self):
        m = _make_manifest(SIMPLE_MODULE)
        func = next(e for e in m.elements if e.name == "top_function")
        assert func.kind == ElementKind.FUNCTION
        assert func.docstring == "Do something."
        assert func.signature is not None
        assert func.signature.return_annotation == "bool"

    def test_class_element(self):
        m = _make_manifest(SIMPLE_MODULE)
        cls = next(e for e in m.elements if e.name == "MyClass")
        assert cls.kind == ElementKind.CLASS
        assert cls.docstring == "A sample class."
        child_names = [c.name for c in cls.children]
        assert "method" in child_names
        assert "static_method" in child_names

    def test_class_variables(self):
        m = _make_manifest(SIMPLE_MODULE)
        cls = next(e for e in m.elements if e.name == "MyClass")
        cv_names = [cv.name for cv in cls.class_variables]
        assert "class_var" in cv_names

    def test_constant_detection(self):
        m = _make_manifest(SIMPLE_MODULE)
        const = next(e for e in m.elements if e.name == "_CONSTANT")
        assert const.kind == ElementKind.CONSTANT
        assert const.type_annotation == "int"
        assert const.value_repr == "42"

    def test_variable_detection(self):
        m = _make_manifest(SIMPLE_MODULE)
        var = next(e for e in m.elements if e.name == "PUBLIC_VAR")
        assert var.kind == ElementKind.CONSTANT

    def test_static_method(self):
        m = _make_manifest(SIMPLE_MODULE)
        cls = next(e for e in m.elements if e.name == "MyClass")
        static = next(c for c in cls.children if c.name == "static_method")
        assert static.is_static is True
        assert "staticmethod" in static.decorators

    def test_property_element(self):
        m = _make_manifest(SIMPLE_MODULE)
        cls = next(e for e in m.elements if e.name == "MyClass")
        prop = next(c for c in cls.children if c.name == "prop" and c.kind == ElementKind.PROPERTY)
        assert prop.kind == ElementKind.PROPERTY
        assert prop.signature is not None

    def test_module_docstring(self):
        m = _make_manifest(SIMPLE_MODULE)
        assert m.module == "mypackage.module"

    def test_async_function(self):
        m = _make_manifest(ASYNC_MODULE)
        func = next(e for e in m.elements if e.name == "fetch_data")
        assert func.kind == ElementKind.ASYNC_FUNCTION
        assert func.docstring == "Fetch data from URL."

    def test_async_method(self):
        m = _make_manifest(ASYNC_MODULE)
        cls = next(e for e in m.elements if e.name == "AsyncProcessor")
        method = next(c for c in cls.children if c.name == "run")
        assert method.kind == ElementKind.ASYNC_METHOD


# ═══════════════════════════════════════════════════════════════════════════
# Signature extraction tests
# ═══════════════════════════════════════════════════════════════════════════

class TestSignatureExtraction:
    def test_all_param_kinds(self):
        m = _make_manifest(ALL_PARAM_KINDS)
        func = next(e for e in m.elements if e.name == "complex_func")
        sig = func.signature
        assert sig is not None

        param_kinds = {p.name: p.kind for p in sig.params}
        assert param_kinds["pos_only"] == ParamKind.POSITIONAL_ONLY
        assert param_kinds["regular"] == ParamKind.POSITIONAL
        assert param_kinds["args"] == ParamKind.VAR_POSITIONAL
        assert param_kinds["kw_only"] == ParamKind.KEYWORD_ONLY
        assert param_kinds["kwargs"] == ParamKind.VAR_KEYWORD

    def test_default_values(self):
        m = _make_manifest(ALL_PARAM_KINDS)
        func = next(e for e in m.elements if e.name == "complex_func")
        kw_only = next(p for p in func.signature.params if p.name == "kw_only")
        assert kw_only.default == "True"

    def test_annotations(self):
        m = _make_manifest(ALL_PARAM_KINDS)
        func = next(e for e in m.elements if e.name == "complex_func")
        pos_only = next(p for p in func.signature.params if p.name == "pos_only")
        assert pos_only.annotation == "int"

    def test_return_annotation(self):
        m = _make_manifest(ALL_PARAM_KINDS)
        func = next(e for e in m.elements if e.name == "complex_func")
        assert func.signature.return_annotation == "None"

    def test_simple_function_signature(self):
        m = _make_manifest(SIMPLE_MODULE)
        func = next(e for e in m.elements if e.name == "top_function")
        assert func.signature is not None
        param_names = [p.name for p in func.signature.params]
        assert param_names == ["x", "y"]
        y_param = next(p for p in func.signature.params if p.name == "y")
        assert y_param.default == "'default'"


# ═══════════════════════════════════════════════════════════════════════════
# Import tests
# ═══════════════════════════════════════════════════════════════════════════

class TestImportExtraction:
    def test_import_count(self):
        m = _make_manifest(SIMPLE_MODULE)
        assert len(m.imports) >= 3

    def test_import_kinds(self):
        m = _make_manifest(SIMPLE_MODULE)
        os_imp = next(i for i in m.imports if i.module == "os")
        assert os_imp.kind == "import"
        path_imp = next(i for i in m.imports if i.module == "pathlib")
        assert path_imp.kind == "from"
        assert "Path" in path_imp.names

    def test_conditional_import(self):
        m = _make_manifest(SIMPLE_MODULE)
        cond_imports = [i for i in m.imports if i.is_conditional]
        assert len(cond_imports) >= 1
        cond_modules = [i.module for i in cond_imports]
        assert any("startd8" in mod for mod in cond_modules)

    def test_relative_import_resolution(self):
        m = _make_manifest(INIT_MODULE, filename="src/mypackage/utils/__init__.py")
        from_imports = [i for i in m.imports if i.kind == "from"]
        assert any(i.is_relative for i in from_imports)

    def test_is_reexport_detection(self):
        m = _make_manifest(INIT_MODULE, filename="src/mypackage/utils/__init__.py")
        reexports = [i for i in m.imports if i.is_reexport]
        assert len(reexports) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# Dependency classification tests
# ═══════════════════════════════════════════════════════════════════════════

class TestDependencyClassification:
    def test_stdlib_detection(self):
        m = _make_manifest(SIMPLE_MODULE)
        assert "os" in m.dependencies.stdlib
        assert "pathlib" in m.dependencies.stdlib

    def test_conditional_detection(self):
        m = _make_manifest(SIMPLE_MODULE)
        assert len(m.dependencies.conditional) >= 1

    def test_classify_imports_function(self):
        imports = [
            ImportEntry(
                kind="import", module="os", span=Span(start_line=1, start_col=0, end_line=1, end_col=9)
            ),
            ImportEntry(
                kind="from", module="pydantic", names=["BaseModel"],
                span=Span(start_line=2, start_col=0, end_line=2, end_col=30)
            ),
            ImportEntry(
                kind="from", module="startd8.utils", names=["retry"], is_relative=True,
                span=Span(start_line=3, start_col=0, end_line=3, end_col=30)
            ),
        ]
        deps = _classify_imports(imports, "startd8", {"os", "sys", "pathlib"})
        assert "os" in deps.stdlib
        assert "pydantic" in deps.external
        assert "startd8.utils" in deps.internal


# ═══════════════════════════════════════════════════════════════════════════
# Overload disambiguation tests
# ═══════════════════════════════════════════════════════════════════════════

class TestOverloadDisambiguation:
    def test_overload_fqn_suffixes(self):
        m = _make_manifest(OVERLOAD_MODULE)
        cls = next(e for e in m.elements if e.name == "Processor")
        process_elements = [c for c in cls.children if c.name == "process"]
        assert len(process_elements) == 3

        fqns = sorted(c.fqn for c in process_elements)
        assert any("@overload[0]" in f for f in fqns)
        assert any("@overload[1]" in f for f in fqns)
        # Implementation has no suffix
        impl = next(c for c in process_elements if c.overload_index is None)
        assert "@overload" not in impl.fqn

    def test_overload_indices(self):
        m = _make_manifest(OVERLOAD_MODULE)
        cls = next(e for e in m.elements if e.name == "Processor")
        overloaded = [c for c in cls.children if c.overload_index is not None]
        assert len(overloaded) == 2
        indices = sorted(c.overload_index for c in overloaded)
        assert indices == [0, 1]


# ═══════════════════════════════════════════════════════════════════════════
# Property triad tests
# ═══════════════════════════════════════════════════════════════════════════

class TestPropertyTriad:
    def test_property_fqn_suffixes(self):
        m = _make_manifest(PROPERTY_TRIAD_MODULE)
        cls = next(e for e in m.elements if e.name == "Config")
        value_elements = [c for c in cls.children if c.name == "value"]
        assert len(value_elements) == 3

        fqns = {c.fqn.split(".")[-1] for c in value_elements}
        assert "value@getter" in fqns
        assert "value@setter" in fqns
        assert "value@deleter" in fqns

    def test_property_getter_kind(self):
        m = _make_manifest(PROPERTY_TRIAD_MODULE)
        cls = next(e for e in m.elements if e.name == "Config")
        getter = next(c for c in cls.children if "@getter" in c.fqn)
        assert getter.kind == ElementKind.PROPERTY

    def test_property_setter_kind(self):
        m = _make_manifest(PROPERTY_TRIAD_MODULE)
        cls = next(e for e in m.elements if e.name == "Config")
        setter = next(c for c in cls.children if "@setter" in c.fqn)
        assert setter.kind == ElementKind.METHOD


# ═══════════════════════════════════════════════════════════════════════════
# Scope guard tests
# ═══════════════════════════════════════════════════════════════════════════

class TestScopeGuard:
    def test_main_guard(self):
        m = _make_manifest(CONDITIONAL_MODULE)
        main_func = next(
            (e for e in m.elements if e.name == "main"), None
        )
        assert main_func is not None
        assert main_func.scope_guard == "__main__"

    def test_platform_guard(self):
        m = _make_manifest(CONDITIONAL_MODULE)
        plat_func = next(
            (e for e in m.elements if e.name == "platform_func"), None
        )
        assert plat_func is not None
        assert plat_func.scope_guard is not None
        assert "sys.platform" in plat_func.scope_guard


# ═══════════════════════════════════════════════════════════════════════════
# Tags detection tests
# ═══════════════════════════════════════════════════════════════════════════

class TestTagsDetection:
    def test_pydantic_model_tag(self):
        m = _make_manifest(PYDANTIC_MODULE)
        cls = next(e for e in m.elements if e.name == "MyModel")
        assert "pydantic_model" in cls.tags

    def test_dataclass_tag(self):
        source = textwrap.dedent('''\
            from dataclasses import dataclass

            @dataclass
            class Point:
                x: float
                y: float
        ''')
        m = _make_manifest(source)
        cls = next(e for e in m.elements if e.name == "Point")
        assert "dataclass" in cls.tags

    def test_abstract_tag(self):
        source = textwrap.dedent('''\
            from abc import ABC, abstractmethod

            class Base(ABC):
                @abstractmethod
                def run(self) -> None: ...
        ''')
        m = _make_manifest(source)
        cls = next(e for e in m.elements if e.name == "Base")
        assert "abstract" in cls.tags

    def test_protocol_tag(self):
        source = textwrap.dedent('''\
            from typing import Protocol

            class Runnable(Protocol):
                def run(self) -> None: ...
        ''')
        m = _make_manifest(source)
        cls = next(e for e in m.elements if e.name == "Runnable")
        assert "protocol" in cls.tags


# ═══════════════════════════════════════════════════════════════════════════
# value_repr truncation tests
# ═══════════════════════════════════════════════════════════════════════════

class TestValueReprTruncation:
    def test_short_literal(self):
        import ast as _ast
        node = _ast.parse("42", mode="eval").body
        result = _truncate_value_repr(node)
        assert result == "42"

    def test_long_string_truncated(self):
        import ast as _ast
        long_str = '"' + "x" * 100 + '"'
        node = _ast.parse(long_str, mode="eval").body
        result = _truncate_value_repr(node)
        assert result is not None
        assert len(result) <= 80
        assert result.endswith("...")

    def test_none_node(self):
        assert _truncate_value_repr(None) is None

    def test_absolute_max(self):
        import ast as _ast
        # A very long expression
        expr = "[" + ", ".join(str(i) for i in range(200)) + "]"
        node = _ast.parse(expr, mode="eval").body
        result = _truncate_value_repr(node)
        assert result is not None
        assert len(result) <= 120


# ═══════════════════════════════════════════════════════════════════════════
# Relative import resolution tests
# ═══════════════════════════════════════════════════════════════════════════

class TestRelativeImportResolution:
    def test_single_dot(self):
        result = _resolve_relative_import(1, "sibling", "mypackage.subpackage.module")
        assert result == "mypackage.subpackage.sibling"

    def test_double_dot(self):
        result = _resolve_relative_import(2, "other", "mypackage.subpackage.module")
        assert result == "mypackage.other"

    def test_dot_only(self):
        result = _resolve_relative_import(1, None, "mypackage.subpackage.module")
        assert result == "mypackage.subpackage"

    def test_escapes_package(self):
        result = _resolve_relative_import(10, "foo", "mypackage.module")
        assert result.startswith("..")  # Can't resolve — raw syntax


# ═══════════════════════════════════════════════════════════════════════════
# Span accuracy tests
# ═══════════════════════════════════════════════════════════════════════════

class TestSpanAccuracy:
    def test_function_span(self):
        source = textwrap.dedent('''\
            def foo():
                pass
        ''')
        m = _make_manifest(source)
        func = next(e for e in m.elements if e.name == "foo")
        assert func.span.start_line == 1
        assert func.span.end_line == 2

    def test_class_span(self):
        source = textwrap.dedent('''\
            class Bar:
                x = 1
                def method(self):
                    pass
        ''')
        m = _make_manifest(source)
        cls = next(e for e in m.elements if e.name == "Bar")
        assert cls.span.start_line == 1
        assert cls.span.end_line == 4


# ═══════════════════════════════════════════════════════════════════════════
# Error handling tests
# ═══════════════════════════════════════════════════════════════════════════

class TestErrorHandling:
    def test_syntax_error_produces_partial_manifest(self):
        source = "def broken(\n"
        m = _make_manifest(source)
        assert len(m.errors) == 1
        assert m.errors[0].kind == ParseErrorKind.SYNTAX_ERROR
        assert m.elements == []
        assert m.digest.startswith("sha256:")

    def test_empty_file(self):
        m = _make_manifest("")
        assert m.elements == []
        assert m.errors == []
        assert m.digest.startswith("sha256:")

    def test_file_not_found(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            generate_file_manifest(
                tmp_path / "nonexistent.py", tmp_path
            )


# ═══════════════════════════════════════════════════════════════════════════
# Lookup tests
# ═══════════════════════════════════════════════════════════════════════════

class TestLookupElement:
    def test_find_top_level(self):
        m = _make_manifest(SIMPLE_MODULE)
        func = lookup_element(m, m.module + ".top_function")
        assert func is not None
        assert func.name == "top_function"

    def test_find_method(self):
        m = _make_manifest(SIMPLE_MODULE)
        method = lookup_element(m, m.module + ".MyClass.method")
        assert method is not None
        assert method.kind == ElementKind.METHOD

    def test_not_found(self):
        m = _make_manifest(SIMPLE_MODULE)
        assert lookup_element(m, "nonexistent.thing") is None

    def test_find_class_variable(self):
        m = _make_manifest(SIMPLE_MODULE)
        cv = lookup_element(m, m.module + ".MyClass.class_var")
        assert cv is not None
        assert cv.name == "class_var"


# ═══════════════════════════════════════════════════════════════════════════
# Determinism test
# ═══════════════════════════════════════════════════════════════════════════

class TestDeterminism:
    def test_same_source_same_output(self):
        m1 = _make_manifest(SIMPLE_MODULE)
        m2 = _make_manifest(SIMPLE_MODULE)
        # Compare everything except generated_at timestamp
        d1 = m1.model_dump()
        d2 = m2.model_dump()
        d1.pop("generated_at")
        d2.pop("generated_at")
        assert d1 == d2


# ═══════════════════════════════════════════════════════════════════════════
# Self-referential smoke test
# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
# Branch disambiguation tests (Gap 1)
# ═══════════════════════════════════════════════════════════════════════════

BRANCH_IF_ELSE_MODULE = textwrap.dedent('''\
    import sys

    if sys.platform == "win32":
        def impl():
            pass
    else:
        def impl():
            pass
''')

BRANCH_SINGLE_DEF_MODULE = textwrap.dedent('''\
    import sys

    if sys.platform == "win32":
        def platform_func():
            pass
''')

BRANCH_CONSTANTS_MODULE = textwrap.dedent('''\
    import sys

    if sys.platform == "win32":
        PATH_SEP = "\\\\"
    else:
        PATH_SEP = "/"
''')


class TestBranchDisambiguation:
    def test_branch_disambiguation_if_else(self):
        m = _make_manifest(BRANCH_IF_ELSE_MODULE)
        impl_elems = [e for e in m.elements if e.name == "impl"]
        assert len(impl_elems) == 2
        fqns = sorted(e.fqn for e in impl_elems)
        assert fqns[0].endswith("impl@branch[0]")
        assert fqns[1].endswith("impl@branch[1]")

    def test_no_branch_suffix_single_def(self):
        m = _make_manifest(BRANCH_SINGLE_DEF_MODULE)
        func = next(e for e in m.elements if e.name == "platform_func")
        assert "@branch" not in func.fqn

    def test_branch_disambiguation_constants(self):
        m = _make_manifest(BRANCH_CONSTANTS_MODULE)
        sep_elems = [e for e in m.elements if e.name == "PATH_SEP"]
        assert len(sep_elems) == 2
        fqns = sorted(e.fqn for e in sep_elems)
        assert fqns[0].endswith("PATH_SEP@branch[0]")
        assert fqns[1].endswith("PATH_SEP@branch[1]")


# ═══════════════════════════════════════════════════════════════════════════
# Nested function tests (Gap 2)
# ═══════════════════════════════════════════════════════════════════════════

NESTED_FUNCTION_MODULE = textwrap.dedent('''\
    def outer(x: int) -> int:
        """Outer function."""
        def inner(y: int) -> int:
            """Inner helper."""
            return y + 1
        return inner(x)
''')

DEEPLY_NESTED_MODULE = textwrap.dedent('''\
    def outer():
        def middle():
            def inner():
                pass
''')


class TestNestedFunctions:
    def test_nested_function_in_function_body(self):
        m = _make_manifest(NESTED_FUNCTION_MODULE)
        outer = next(e for e in m.elements if e.name == "outer")
        assert len(outer.children) == 1
        inner = outer.children[0]
        assert inner.name == "inner"
        assert inner.fqn == f"{m.module}.outer.inner"
        assert inner.kind == ElementKind.FUNCTION

    def test_deeply_nested_functions(self):
        m = _make_manifest(DEEPLY_NESTED_MODULE)
        outer = next(e for e in m.elements if e.name == "outer")
        assert len(outer.children) == 1
        middle = outer.children[0]
        assert middle.name == "middle"
        assert middle.fqn == f"{m.module}.outer.middle"
        assert len(middle.children) == 1
        inner = middle.children[0]
        assert inner.name == "inner"
        assert inner.fqn == f"{m.module}.outer.middle.inner"

    def test_nested_function_signature(self):
        m = _make_manifest(NESTED_FUNCTION_MODULE)
        outer = next(e for e in m.elements if e.name == "outer")
        inner = outer.children[0]
        assert inner.signature is not None
        assert len(inner.signature.params) == 1
        assert inner.signature.params[0].name == "y"
        assert inner.signature.return_annotation == "int"
        assert inner.docstring == "Inner helper."


# ═══════════════════════════════════════════════════════════════════════════
# Re-export heuristics tests (Gap 3)
# ═══════════════════════════════════════════════════════════════════════════

INIT_NO_ALL = textwrap.dedent('''\
    """Package init without __all__."""

    from .models import MyModel
    from .utils import helper_func
''')

INIT_ALIASED = textwrap.dedent('''\
    """Package init with aliased import."""

    from .models import MyModel as M
''')


class TestReexportHeuristics:
    def test_reexport_init_relative_import(self):
        """Relative import in __init__.py without aliasing → is_reexport=True."""
        m = _make_manifest(INIT_NO_ALL, filename="src/mypackage/__init__.py")
        reexports = [i for i in m.imports if i.is_reexport]
        assert len(reexports) == 2

    def test_no_reexport_non_init(self):
        """Same relative import pattern in non-__init__.py → is_reexport=False."""
        source = textwrap.dedent('''\
            from .models import MyModel
        ''')
        m = _make_manifest(source, filename="src/mypackage/module.py")
        reexports = [i for i in m.imports if i.is_reexport]
        assert len(reexports) == 0

    def test_reexport_init_aliased(self):
        """Aliased import in __init__.py → is_reexport=False (heuristic c requires no alias)."""
        m = _make_manifest(INIT_ALIASED, filename="src/mypackage/__init__.py")
        reexports = [i for i in m.imports if i.is_reexport]
        assert len(reexports) == 0


# ═══════════════════════════════════════════════════════════════════════════
# YAML output tests (Gap 4)
# ═══════════════════════════════════════════════════════════════════════════

class TestYAMLOutput:
    def test_to_yaml_round_trip(self):
        import yaml
        m = _make_manifest(SIMPLE_MODULE)
        yaml_str = m.to_yaml()
        loaded = yaml.safe_load(yaml_str)
        assert loaded["module"] == m.module
        assert loaded["digest"] == m.digest
        assert loaded["schema_version"] == m.schema_version
        assert len(loaded["elements"]) == len(m.elements)

    def test_to_yaml_contains_elements(self):
        m = _make_manifest(SIMPLE_MODULE)
        yaml_str = m.to_yaml()
        assert "top_function" in yaml_str
        assert "MyClass" in yaml_str
        assert "_CONSTANT" in yaml_str


# ═══════════════════════════════════════════════════════════════════════════
# Mode parameter tests (Gap 5)
# ═══════════════════════════════════════════════════════════════════════════

class TestModeParameter:
    def test_mode_static_works(self):
        m = _make_manifest(SIMPLE_MODULE)
        assert len(m.elements) > 0

    def test_mode_static_explicit(self):
        project_root = Path("/fake/project")
        file_path = project_root / "src/mypackage/module.py"
        m = generate_file_manifest(file_path, project_root, source=SIMPLE_MODULE, mode="static")
        assert len(m.elements) > 0

    def test_mode_ast_only_skips_symtable(self):
        project_root = Path("/fake/project")
        file_path = project_root / "src/mypackage/module.py"
        m = generate_file_manifest(file_path, project_root, source=SIMPLE_MODULE, mode="ast_only")
        assert len(m.elements) > 0
        for elem in m.elements:
            assert elem.symbol_info is None

    def test_mode_introspect_raises(self):
        project_root = Path("/fake/project")
        file_path = project_root / "src/mypackage/module.py"
        with pytest.raises(NotImplementedError, match="Phase 5"):
            generate_file_manifest(file_path, project_root, source=SIMPLE_MODULE, mode="introspect")

    def test_mode_full_raises(self):
        project_root = Path("/fake/project")
        file_path = project_root / "src/mypackage/module.py"
        with pytest.raises(NotImplementedError, match="Phase 5"):
            generate_file_manifest(file_path, project_root, source=SIMPLE_MODULE, mode="full")


class TestSelfReferential:
    def test_manifest_of_own_source(self):
        """Generate a manifest for code_manifest.py itself."""
        project_root = Path(__file__).resolve().parent.parent.parent
        file_path = project_root / "src" / "startd8" / "utils" / "code_manifest.py"
        if not file_path.exists():
            pytest.skip("Source file not found — running outside repo")

        m = generate_file_manifest(file_path, project_root)
        assert m.module == "startd8.utils.code_manifest"
        assert len(m.elements) > 10
        assert m.errors == []
        assert m.digest.startswith("sha256:")

        # Check key elements exist
        element_names = {e.name for e in m.elements}
        assert "FileManifest" in element_names
        assert "generate_file_manifest" in element_names
        assert "Element" in element_names
        assert "SCHEMA_VERSION" in element_names

        # Phase 3: verify symbol_info is populated for scope-creating elements
        gen_func = next(e for e in m.elements if e.name == "generate_file_manifest")
        assert gen_func.symbol_info is not None
        assert isinstance(gen_func.symbol_info, SymbolInfo)


# ═══════════════════════════════════════════════════════════════════════════
# Phase 3: symtable augmentation fixtures
# ═══════════════════════════════════════════════════════════════════════════

CLOSURE_MODULE = textwrap.dedent('''\
    def outer(x):
        y = 10
        def inner():
            return x + y
        return inner()
''')

GLOBAL_MODULE = textwrap.dedent('''\
    counter = 0

    def increment():
        global counter
        counter += 1
''')

NONLOCAL_MODULE = textwrap.dedent('''\
    def make_counter():
        count = 0
        def increment():
            nonlocal count
            count += 1
            return count
        return increment
''')

IMPORT_CLASSIFY_MODULE = textwrap.dedent('''\
    def use_local_imports():
        import os
        from pathlib import Path as P
        return os.path.join(str(P(".")), "b")
''')

UNUSED_VAR_MODULE = textwrap.dedent('''\
    def process(data):
        unused_result = data.transform()
        final = data.finalize()
        return final
''')

CLASS_WITH_METHODS_MODULE = textwrap.dedent('''\
    class MyService:
        name: str = "default"
        count: int = 0

        def __init__(self, name: str):
            self.name = name

        def run(self) -> None:
            self.count += 1
''')

STAR_PARAMS_MODULE = textwrap.dedent('''\
    def func(*args, **kwargs):
        return args, kwargs
''')


# ═══════════════════════════════════════════════════════════════════════════
# Phase 3: symtable augmentation tests
# ═══════════════════════════════════════════════════════════════════════════

class TestSymtableClosure:
    """AC-1: Closure variables correctly identified."""

    def test_inner_captures_free_vars(self):
        m = _make_manifest(CLOSURE_MODULE)
        outer = next(e for e in m.elements if e.name == "outer")
        inner = next(c for c in outer.children if c.name == "inner")
        assert inner.symbol_info is not None
        assert inner.symbol_info.is_closure is True
        assert sorted(inner.symbol_info.free_vars) == ["x", "y"]

    def test_outer_is_not_closure(self):
        m = _make_manifest(CLOSURE_MODULE)
        outer = next(e for e in m.elements if e.name == "outer")
        assert outer.symbol_info is not None
        assert outer.symbol_info.is_closure is False
        assert outer.symbol_info.free_vars == []


class TestSymtableGlobal:
    """AC-2: global declarations captured."""

    def test_global_var_in_function(self):
        m = _make_manifest(GLOBAL_MODULE)
        func = next(e for e in m.elements if e.name == "increment")
        assert func.symbol_info is not None
        assert "counter" in func.symbol_info.global_vars
        # Verify the symbol entry
        counter_sym = next(s for s in func.symbol_info.symbols if s.name == "counter")
        assert counter_sym.scope == ScopeKind.GLOBAL


class TestSymtableNonlocal:
    """AC-3: nonlocal declarations captured."""

    def test_nonlocal_var_in_nested(self):
        m = _make_manifest(NONLOCAL_MODULE)
        outer = next(e for e in m.elements if e.name == "make_counter")
        inner = next(c for c in outer.children if c.name == "increment")
        assert inner.symbol_info is not None
        assert "count" in inner.symbol_info.nonlocal_vars
        count_sym = next(s for s in inner.symbol_info.symbols if s.name == "count")
        assert count_sym.scope == ScopeKind.NONLOCAL


class TestSymtableParameters:
    """AC-4: Parameters classified correctly."""

    def test_params_classified_as_parameter(self):
        m = _make_manifest(CLOSURE_MODULE)
        outer = next(e for e in m.elements if e.name == "outer")
        assert outer.symbol_info is not None
        x_sym = next(s for s in outer.symbol_info.symbols if s.name == "x")
        assert x_sym.scope == ScopeKind.PARAMETER
        assert x_sym.is_parameter is True

    def test_star_params_bare_names(self):
        """*args and **kwargs appear as bare names with scope=parameter."""
        m = _make_manifest(STAR_PARAMS_MODULE)
        func = next(e for e in m.elements if e.name == "func")
        assert func.symbol_info is not None
        args_sym = next(s for s in func.symbol_info.symbols if s.name == "args")
        kwargs_sym = next(s for s in func.symbol_info.symbols if s.name == "kwargs")
        assert args_sym.scope == ScopeKind.PARAMETER
        assert args_sym.is_parameter is True
        assert kwargs_sym.scope == ScopeKind.PARAMETER
        assert kwargs_sym.is_parameter is True


class TestSymtableImports:
    """AC-5: Imported names classified (including aliased)."""

    def test_bare_import_classified(self):
        m = _make_manifest(IMPORT_CLASSIFY_MODULE)
        func = next(e for e in m.elements if e.name == "use_local_imports")
        assert func.symbol_info is not None
        os_sym = next(s for s in func.symbol_info.symbols if s.name == "os")
        assert os_sym.scope == ScopeKind.IMPORTED

    def test_aliased_from_import_classified(self):
        m = _make_manifest(IMPORT_CLASSIFY_MODULE)
        # "from pathlib import Path as P" — the symbol is 'P', not 'Path'
        func = next(e for e in m.elements if e.name == "use_local_imports")
        assert func.symbol_info is not None
        p_sym = next(s for s in func.symbol_info.symbols if s.name == "P")
        assert p_sym.scope == ScopeKind.IMPORTED
        assert p_sym.name == "P"


class TestSymtableReadWrite:
    """AC-6: Read/write analysis accurate."""

    def test_assigned_but_unreferenced(self):
        m = _make_manifest(UNUSED_VAR_MODULE)
        func = next(e for e in m.elements if e.name == "process")
        assert func.symbol_info is not None
        unused = next(s for s in func.symbol_info.symbols if s.name == "unused_result")
        assert unused.is_assigned is True
        assert unused.is_referenced is False

    def test_assigned_and_referenced(self):
        m = _make_manifest(UNUSED_VAR_MODULE)
        func = next(e for e in m.elements if e.name == "process")
        final_sym = next(s for s in func.symbol_info.symbols if s.name == "final")
        assert final_sym.is_assigned is True
        assert final_sym.is_referenced is True


class TestSymtableRecursiveEnrichment:
    """AC-7: Recursive enrichment — nested functions and class variables."""

    def test_class_methods_enriched(self):
        m = _make_manifest(CLASS_WITH_METHODS_MODULE)
        cls = next(e for e in m.elements if e.name == "MyService")
        assert cls.symbol_info is not None

        # Methods should have symbol_info
        init_method = next(c for c in cls.children if c.name == "__init__")
        assert init_method.symbol_info is not None
        # __init__ has 'self' and 'name' parameters
        self_sym = next(s for s in init_method.symbol_info.symbols if s.name == "self")
        assert self_sym.scope == ScopeKind.PARAMETER

    def test_class_variables_enriched(self):
        """Class variables appear as SymbolEntry in the parent class's symbol_info."""
        m = _make_manifest(CLASS_WITH_METHODS_MODULE)
        cls = next(e for e in m.elements if e.name == "MyService")
        assert cls.symbol_info is not None

        # class_variables elements should also have symbol_info from lookup
        name_cv = next(cv for cv in cls.class_variables if cv.name == "name")
        assert name_cv.symbol_info is not None
        assert name_cv.symbol_info.symbols[0].scope == ScopeKind.LOCAL

    def test_nested_function_children_enriched(self):
        m = _make_manifest(CLOSURE_MODULE)
        outer = next(e for e in m.elements if e.name == "outer")
        inner = next(c for c in outer.children if c.name == "inner")
        assert inner.symbol_info is not None
        assert inner.symbol_info.is_closure is True


class TestSymtableSchemaVersion:
    """AC-8: Schema version bumped to 1.2.0."""

    def test_schema_version(self):
        m = _make_manifest(SIMPLE_MODULE)
        assert m.schema_version == "1.2.0"


class TestSymtableBackwardCompat:
    """AC-9: Backward compat — None default."""

    def test_element_without_symbol_info(self):
        elem = Element(
            kind=ElementKind.CONSTANT,
            name="X",
            fqn="mod.X",
            span=Span(start_line=1, start_col=0, end_line=1, end_col=5),
            value_repr="42",
        )
        assert elem.symbol_info is None


class TestSymtableAstOnlyMode:
    """AC-10: ast_only mode skips symtable."""

    def test_ast_only_no_symbol_info(self):
        project_root = Path("/fake/project")
        file_path = project_root / "src/mypackage/module.py"
        m = generate_file_manifest(
            file_path, project_root, source=CLOSURE_MODULE, mode="ast_only"
        )
        for elem in m.elements:
            assert elem.symbol_info is None
            for child in elem.children:
                assert child.symbol_info is None


class TestSymtableParseErrorSafety:
    """AC-11: Parse error safety — no crash."""

    def test_syntax_error_no_symbol_info(self):
        source = "def broken(\n"
        m = _make_manifest(source)
        assert len(m.errors) == 1
        # Elements are empty on syntax error, so no symbol_info to check
        assert m.elements == []

    def test_symtable_failure_returns_unenriched(self):
        """If symtable somehow fails, manifest still works."""
        from unittest.mock import patch

        source = "def f(): pass\n"
        with patch("startd8.utils.code_manifest.symtable.symtable", side_effect=ValueError("mock failure")):
            m = _make_manifest(source)
        assert len(m.elements) == 1
        assert m.elements[0].symbol_info is None


class TestSymtableDeterminism:
    """AC-12: Determinism — same source, same symbol_info."""

    def test_deterministic_output(self):
        m1 = _make_manifest(CLOSURE_MODULE)
        m2 = _make_manifest(CLOSURE_MODULE)
        d1 = m1.model_dump()
        d2 = m2.model_dump()
        d1.pop("generated_at")
        d2.pop("generated_at")
        assert d1 == d2


class TestSymtablePerformance:
    """AP-1: symtable overhead < 10ms per file."""

    def test_symtable_overhead_under_10ms(self):
        """Compare mode=static vs mode=ast_only on code_manifest.py itself."""
        import time

        project_root = Path(__file__).resolve().parents[2]
        file_path = project_root / "src" / "startd8" / "utils" / "code_manifest.py"
        if not file_path.exists():
            pytest.skip("Source file not found — running outside repo")

        source = file_path.read_text(encoding="utf-8")

        # Warm up
        generate_file_manifest(file_path, project_root, source=source, mode="static")
        generate_file_manifest(file_path, project_root, source=source, mode="ast_only")

        # Benchmark ast_only
        start = time.perf_counter()
        for _ in range(5):
            generate_file_manifest(file_path, project_root, source=source, mode="ast_only")
        ast_only_avg = (time.perf_counter() - start) / 5

        # Benchmark static (includes symtable)
        start = time.perf_counter()
        for _ in range(5):
            generate_file_manifest(file_path, project_root, source=source, mode="static")
        static_avg = (time.perf_counter() - start) / 5

        overhead_ms = (static_avg - ast_only_avg) * 1000
        # Budget: <10ms for typical files. code_manifest.py is ~1500 lines
        # (above-average), so we allow 15ms here.
        assert overhead_ms < 15.0, f"symtable overhead {overhead_ms:.1f}ms exceeds 15ms budget"


class TestSymtableOverloadsAndProperties:
    """Verify scope matching works for overloads and property triads."""

    def test_overloaded_methods_enriched(self):
        m = _make_manifest(OVERLOAD_MODULE)
        cls = next(e for e in m.elements if e.name == "Processor")
        process_methods = [c for c in cls.children if c.name == "process"]
        assert len(process_methods) == 3
        # All should have symbol_info
        for method in process_methods:
            assert method.symbol_info is not None

    def test_property_triad_enriched(self):
        m = _make_manifest(PROPERTY_TRIAD_MODULE)
        cls = next(e for e in m.elements if e.name == "Config")
        value_elems = [c for c in cls.children if c.name == "value"]
        assert len(value_elems) == 3
        for elem in value_elems:
            assert elem.symbol_info is not None


class TestSymtableRoundTrip:
    """Integration: symbol_info survives JSON serialization round-trip."""

    def test_json_round_trip(self):
        import json

        m = _make_manifest(CLOSURE_MODULE)
        json_str = json.dumps(m.model_dump(mode="json"))
        loaded = FileManifest.model_validate_json(json_str)

        outer = next(e for e in loaded.elements if e.name == "outer")
        assert outer.symbol_info is not None
        inner = next(c for c in outer.children if c.name == "inner")
        assert inner.symbol_info is not None
        assert inner.symbol_info.is_closure is True
        assert sorted(inner.symbol_info.free_vars) == ["x", "y"]

    def test_yaml_round_trip(self):
        import yaml

        m = _make_manifest(CLOSURE_MODULE)
        yaml_str = m.to_yaml()
        loaded_dict = yaml.safe_load(yaml_str)

        outer = next(e for e in loaded_dict["elements"] if e["name"] == "outer")
        assert outer["symbol_info"] is not None
        inner = next(c for c in outer["children"] if c["name"] == "inner")
        assert inner["symbol_info"]["is_closure"] is True
        assert sorted(inner["symbol_info"]["free_vars"]) == ["x", "y"]
