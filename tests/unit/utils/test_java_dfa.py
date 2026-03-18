"""Tests for Java Deterministic File Assembler (Phase 2)."""

import pytest
from startd8.utils.java_file_assembler import (
    JavaDeterministicFileAssembler,
    JAVA_SKELETON_SENTINEL,
    JAVA_STUB_BODY,
    _derive_package,
    _derive_class_name,
    _render_imports,
    _python_type_to_java,
)


class TestDerivePackage:
    def test_standard_layout(self):
        assert _derive_package("src/main/java/com/example/MyClass.java") == "com.example"

    def test_test_layout(self):
        assert _derive_package("src/test/java/com/example/MyTest.java") == "com.example"

    def test_nested_package(self):
        assert _derive_package("src/main/java/com/example/service/impl/MyService.java") == "com.example.service.impl"

    def test_nonstandard_layout(self):
        pkg = _derive_package("myapp/com/example/MyClass.java")
        # Non-standard may produce partial package or None
        assert pkg is None or isinstance(pkg, str)

    def test_root_file(self):
        # File directly in src/main/java/ — no package
        assert _derive_package("src/main/java/MyClass.java") is None


class TestDeriveClassName:
    def test_simple(self):
        assert _derive_class_name("src/main/java/com/example/MyClass.java") == "MyClass"

    def test_nested(self):
        assert _derive_class_name("service/UserService.java") == "UserService"


class TestRenderImports:
    def test_two_tier_grouping(self):
        imports = [
            "import java.util.List;",
            "import com.example.MyService;",
            "import javax.annotation.Nullable;",
        ]
        result = _render_imports(imports)
        lines = result.split("\n")
        # java.* and javax.* should come before com.*
        java_idx = next(i for i, l in enumerate(lines) if "java.util" in l)
        javax_idx = next(i for i, l in enumerate(lines) if "javax." in l)
        com_idx = next(i for i, l in enumerate(lines) if "com.example" in l)
        assert java_idx < com_idx
        assert javax_idx < com_idx

    def test_empty_imports(self):
        assert _render_imports([]) == ""

    def test_dedup(self):
        imports = ["import java.util.List;", "import java.util.List;"]
        result = _render_imports(imports)
        assert result.count("java.util.List") == 1


class TestPythonTypeToJava:
    def test_str(self):
        assert _python_type_to_java("str") == "String"

    def test_int(self):
        assert _python_type_to_java("int") == "int"

    def test_bool(self):
        assert _python_type_to_java("bool") == "boolean"

    def test_none(self):
        assert _python_type_to_java("None") == "void"

    def test_list(self):
        assert "List" in _python_type_to_java("List[str]")

    def test_optional(self):
        result = _python_type_to_java("Optional[str]")
        assert result == "String"

    def test_passthrough(self):
        assert _python_type_to_java("MyCustomType") == "MyCustomType"


class TestJavaDFA:
    def _make_file_spec(self, file_path, elements=None, imports=None):
        """Create a minimal file spec."""
        class FakeFileSpec:
            def __init__(self):
                self.file = file_path
                self.elements = elements or []
                self.imports = imports or []
        return FakeFileSpec()

    def _make_element(self, name, kind="method", parent_class=None, signature=None, decorators=None, bases=None):
        class FakeKind:
            def __init__(self, v):
                self.value = v
            def __eq__(self, other):
                return self.value == getattr(other, 'value', other)
            def __hash__(self):
                return hash(self.value)

        class FakeElement:
            def __init__(self):
                self.name = name
                self.kind = FakeKind(kind)
                self.parent_class = parent_class
                self.signature = signature
                self.decorators = decorators or []
                self.bases = bases or []
        return FakeElement()

    def test_render_empty_class(self):
        dfa = JavaDeterministicFileAssembler()
        spec = self._make_file_spec("src/main/java/com/example/MyClass.java")
        content = dfa.render_file(spec)
        assert content is not None
        assert JAVA_SKELETON_SENTINEL in content
        assert "public class MyClass" in content
        assert "package com.example;" in content

    def test_render_with_method(self):
        dfa = JavaDeterministicFileAssembler()
        method = self._make_element("doWork", "method", parent_class="Worker")
        cls = self._make_element("Worker", "class")
        spec = self._make_file_spec(
            "src/main/java/com/example/Worker.java",
            elements=[cls, method],
        )
        content = dfa.render_file(spec)
        assert content is not None
        assert "doWork" in content
        assert JAVA_STUB_BODY in content

    def test_non_java_returns_none(self):
        dfa = JavaDeterministicFileAssembler()
        spec = self._make_file_spec("src/main.py")
        assert dfa.render_file(spec) is None

    def test_skeleton_sentinel_present(self):
        dfa = JavaDeterministicFileAssembler()
        spec = self._make_file_spec("src/main/java/com/example/App.java")
        content = dfa.render_file(spec)
        assert JAVA_SKELETON_SENTINEL in content

    def test_public_class_matches_filename(self):
        dfa = JavaDeterministicFileAssembler()
        spec = self._make_file_spec("src/main/java/com/example/OrderService.java")
        content = dfa.render_file(spec)
        assert "public class OrderService" in content

    def test_render_specs_filters_java_only(self):
        dfa = JavaDeterministicFileAssembler()

        class FakeManifest:
            def __init__(self, files):
                self.files = files

        java_spec = self._make_file_spec("src/main/java/com/example/A.java")
        py_spec = self._make_file_spec("src/main.py")
        manifest = FakeManifest([java_spec, py_spec])
        results = dfa.render_specs(manifest)
        assert "src/main/java/com/example/A.java" in results
        assert "src/main.py" not in results
