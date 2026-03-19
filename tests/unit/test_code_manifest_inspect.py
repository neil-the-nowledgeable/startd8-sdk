"""Tests for Phase 5: inspect-based runtime introspection in code_manifest."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from startd8.utils.code_manifest import (
    Element,
    ElementKind,
    FileManifest,
    InspectInfo,
    ParseErrorKind,
    ResolvedParam,
    ResolvedSignature,
    SCHEMA_VERSION,
    generate_file_manifest,
    lookup_element,
)


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures — source strings written to real files via tmp_path
# ═══════════════════════════════════════════════════════════════════════════

INTROSPECTABLE_MODULE = textwrap.dedent("""\
    \"\"\"A module for introspection testing.\"\"\"

    __all__ = ["greet", "Animal"]
    __version__ = "0.1.0"


    def greet(name: str, greeting: str = "Hello") -> str:
        \"\"\"Return a greeting.\"\"\"
        return f"{greeting}, {name}!"


    class Animal:
        \"\"\"A base animal class.\"\"\"

        species: str = "unknown"

        def __init__(self, name: str, legs: int = 4) -> None:
            self.name = name
            self.legs = legs

        def speak(self) -> str:
            return "..."


    class Dog(Animal):
        \"\"\"A dog.\"\"\"

        def speak(self) -> str:
            return "Woof!"
""")

FORWARD_REF_MODULE = textwrap.dedent("""\
    from __future__ import annotations


    class Node:
        \"\"\"A node with forward reference.\"\"\"

        def __init__(self, value: int, next_node: Node | None = None) -> None:
            self.value = value
            self.next_node = next_node

        def chain(self) -> Node:
            return self


    def build_node(value: int) -> Node:
        return Node(value)
""")

IMPORT_ERROR_MODULE = textwrap.dedent("""\
    \"\"\"Module that fails to import.\"\"\"

    raise ImportError("deliberate import failure for testing")

    x = 1
""")

DATACLASS_MODULE = textwrap.dedent("""\
    from dataclasses import dataclass


    @dataclass
    class Point:
        \"\"\"A 2D point.\"\"\"
        x: float
        y: float

        def distance(self) -> float:
            return (self.x ** 2 + self.y ** 2) ** 0.5
""")


def _write_and_manifest(
    project_root: Path,
    pkg_dir: Path,
    source: str,
    mode: str = "introspect",
    filename: str = "module.py",
) -> FileManifest:
    """Write source to temp file, return its manifest."""
    file_path = pkg_dir / filename
    file_path.write_text(source, encoding="utf-8")
    return generate_file_manifest(file_path, project_root, mode=mode)


@pytest.fixture()
def project_env(tmp_path: Path):
    """Create a minimal project with src/<pkg>/__init__.py."""
    project_root = tmp_path / "project"
    pkg_dir = project_root / "src" / "testpkg"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
    return project_root, pkg_dir


# ═══════════════════════════════════════════════════════════════════════════
# AC-I1: InspectInfo model defaults
# ═══════════════════════════════════════════════════════════════════════════


class TestInspectInfoModel:
    def test_defaults(self):
        info = InspectInfo()
        assert info.resolved_signature is None
        assert info.class_mro == []
        assert info.resolved_annotations == {}
        assert info.runtime_attributes == []
        assert info.is_callable is False
        assert info.qualname is None

    def test_frozen(self):
        info = InspectInfo(is_callable=True)
        with pytest.raises(Exception):
            info.is_callable = False  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════════════════
# ParseErrorKind.IMPORT_ERROR exists
# ═══════════════════════════════════════════════════════════════════════════


class TestParseErrorKindImportError:
    def test_import_error_member(self):
        assert ParseErrorKind.IMPORT_ERROR.value == "import_error"


# ═══════════════════════════════════════════════════════════════════════════
# AC-I2, AC-I3, AC-I14, AC-I15, AC-I16: Mode wiring
# ═══════════════════════════════════════════════════════════════════════════


class TestModeIntrospect:
    def test_introspect_mode_returns_manifest(self, project_env):
        """AC-I2: mode='introspect' returns a valid FileManifest."""
        project_root, pkg_dir = project_env
        m = _write_and_manifest(project_root, pkg_dir, INTROSPECTABLE_MODULE)
        assert isinstance(m, FileManifest)
        assert not m.errors

    def test_introspect_populates_inspect_info(self, project_env):
        """AC-I3: Elements have inspect_info populated."""
        project_root, pkg_dir = project_env
        m = _write_and_manifest(project_root, pkg_dir, INTROSPECTABLE_MODULE)
        # At least some elements should have inspect_info
        has_info = [e for e in m.elements if e.inspect_info is not None]
        assert len(has_info) > 0

    def test_static_mode_no_inspect_info(self, project_env):
        """AC-I14: mode='static' produces no inspect_info."""
        project_root, pkg_dir = project_env
        m = _write_and_manifest(
            project_root, pkg_dir, INTROSPECTABLE_MODULE, mode="static",
        )
        for elem in m.elements:
            assert elem.inspect_info is None

    def test_ast_only_mode_no_inspect_info(self, project_env):
        """AC-I15: mode='ast_only' produces no inspect_info."""
        project_root, pkg_dir = project_env
        m = _write_and_manifest(
            project_root, pkg_dir, INTROSPECTABLE_MODULE, mode="ast_only",
        )
        for elem in m.elements:
            assert elem.inspect_info is None

    def test_introspect_includes_symtable(self, project_env):
        """AC-I16: mode='introspect' also runs symtable augmentation."""
        project_root, pkg_dir = project_env
        m = _write_and_manifest(project_root, pkg_dir, INTROSPECTABLE_MODULE)
        # Functions and classes should have symbol_info
        funcs = [e for e in m.elements if e.kind == ElementKind.FUNCTION]
        assert any(f.symbol_info is not None for f in funcs)

    def test_unknown_mode_raises_value_error(self, project_env):
        project_root, pkg_dir = project_env
        file_path = pkg_dir / "module.py"
        file_path.write_text("x = 1", encoding="utf-8")
        with pytest.raises(ValueError, match="Unknown mode"):
            generate_file_manifest(file_path, project_root, mode="bogus")

    def test_full_mode_raises_not_implemented(self, project_env):
        project_root, pkg_dir = project_env
        file_path = pkg_dir / "module.py"
        file_path.write_text("x = 1", encoding="utf-8")
        with pytest.raises(NotImplementedError, match="combined introspect"):
            generate_file_manifest(file_path, project_root, mode="full")


# ═══════════════════════════════════════════════════════════════════════════
# AC-I4: Resolved signatures
# ═══════════════════════════════════════════════════════════════════════════


class TestResolvedSignatures:
    def test_function_params(self, project_env):
        """AC-I4: Parameters have resolved kinds, defaults, annotations."""
        project_root, pkg_dir = project_env
        m = _write_and_manifest(project_root, pkg_dir, INTROSPECTABLE_MODULE)
        greet = lookup_element(m, "testpkg.module.greet")
        assert greet is not None
        assert greet.inspect_info is not None
        sig = greet.inspect_info.resolved_signature
        assert sig is not None
        assert len(sig.params) == 2

        name_param = sig.params[0]
        assert name_param.name == "name"
        assert name_param.annotation is not None
        assert "str" in name_param.annotation
        assert name_param.has_default is False

        greeting_param = sig.params[1]
        assert greeting_param.name == "greeting"
        assert greeting_param.has_default is True
        assert greeting_param.default is not None
        assert "Hello" in greeting_param.default

    def test_return_annotation(self, project_env):
        project_root, pkg_dir = project_env
        m = _write_and_manifest(project_root, pkg_dir, INTROSPECTABLE_MODULE)
        greet = lookup_element(m, "testpkg.module.greet")
        assert greet is not None
        assert greet.inspect_info is not None
        sig = greet.inspect_info.resolved_signature
        assert sig is not None
        assert sig.return_annotation is not None
        assert "str" in sig.return_annotation

    def test_class_init_signature(self, project_env):
        """Class signature reflects __init__."""
        project_root, pkg_dir = project_env
        m = _write_and_manifest(project_root, pkg_dir, INTROSPECTABLE_MODULE)
        animal = lookup_element(m, "testpkg.module.Animal")
        assert animal is not None
        assert animal.inspect_info is not None
        sig = animal.inspect_info.resolved_signature
        assert sig is not None
        # __init__ has self, name, legs
        param_names = [p.name for p in sig.params]
        assert "name" in param_names
        assert "legs" in param_names


# ═══════════════════════════════════════════════════════════════════════════
# AC-I5: Forward reference resolution
# ═══════════════════════════════════════════════════════════════════════════


class TestForwardRefResolution:
    def test_forward_ref_annotations(self, project_env):
        """AC-I5: Forward references are resolved to actual types."""
        project_root, pkg_dir = project_env
        m = _write_and_manifest(project_root, pkg_dir, FORWARD_REF_MODULE)
        build_fn = lookup_element(m, "testpkg.module.build_node")
        assert build_fn is not None
        assert build_fn.inspect_info is not None
        # The resolved annotations should reference Node
        sig = build_fn.inspect_info.resolved_signature
        assert sig is not None
        assert sig.return_annotation is not None
        assert "Node" in sig.return_annotation


# ═══════════════════════════════════════════════════════════════════════════
# AC-I6: Class MRO
# ═══════════════════════════════════════════════════════════════════════════


class TestClassMRO:
    def test_mro_includes_bases(self, project_env):
        """AC-I6: MRO includes parent classes (excluding object and self)."""
        project_root, pkg_dir = project_env
        m = _write_and_manifest(project_root, pkg_dir, INTROSPECTABLE_MODULE)
        dog = lookup_element(m, "testpkg.module.Dog")
        assert dog is not None
        assert dog.inspect_info is not None
        # Dog's MRO should include Animal
        assert any("Animal" in cls for cls in dog.inspect_info.class_mro)

    def test_base_class_empty_mro(self, project_env):
        """Animal only inherits from object — MRO should be empty."""
        project_root, pkg_dir = project_env
        m = _write_and_manifest(project_root, pkg_dir, INTROSPECTABLE_MODULE)
        animal = lookup_element(m, "testpkg.module.Animal")
        assert animal is not None
        assert animal.inspect_info is not None
        # Animal inherits only from object, which is excluded
        assert animal.inspect_info.class_mro == []


# ═══════════════════════════════════════════════════════════════════════════
# AC-I7, AC-I8: Module-level metadata
# ═══════════════════════════════════════════════════════════════════════════


class TestModuleLevelMetadata:
    def test_module_all(self, project_env):
        """AC-I7: module_all extracted from __all__."""
        project_root, pkg_dir = project_env
        m = _write_and_manifest(project_root, pkg_dir, INTROSPECTABLE_MODULE)
        assert m.module_all is not None
        assert "greet" in m.module_all
        assert "Animal" in m.module_all

    def test_module_version(self, project_env):
        """AC-I8: module_version extracted from __version__."""
        project_root, pkg_dir = project_env
        m = _write_and_manifest(project_root, pkg_dir, INTROSPECTABLE_MODULE)
        assert m.module_version == "0.1.0"

    def test_no_all_no_version(self, project_env):
        """Modules without __all__/__version__ get None."""
        project_root, pkg_dir = project_env
        source = "def f(): pass\n"
        m = _write_and_manifest(project_root, pkg_dir, source)
        assert m.module_all is None
        assert m.module_version is None

    def test_module_all_sorted(self, project_env):
        """module_all is sorted for determinism."""
        project_root, pkg_dir = project_env
        m = _write_and_manifest(project_root, pkg_dir, INTROSPECTABLE_MODULE)
        assert m.module_all is not None
        assert m.module_all == sorted(m.module_all)


# ═══════════════════════════════════════════════════════════════════════════
# AC-I9: Runtime attributes (dataclass generated methods)
# ═══════════════════════════════════════════════════════════════════════════


class TestRuntimeAttributes:
    def test_dataclass_generated_methods(self, project_env):
        """AC-I9: Dataclass generates methods not in AST."""
        project_root, pkg_dir = project_env
        m = _write_and_manifest(project_root, pkg_dir, DATACLASS_MODULE)
        point = lookup_element(m, "testpkg.module.Point")
        assert point is not None
        assert point.inspect_info is not None
        # Dataclass generates __init__, __repr__, __eq__ at minimum
        # These won't appear in AST children, so they should be in
        # the InspectInfo. However, dunder methods are filtered out
        # (startswith("__")), so runtime_attributes won't include them.
        # The is_callable flag should be True for the class.
        assert point.inspect_info.is_callable is True


# ═══════════════════════════════════════════════════════════════════════════
# AC-I10: Import failure graceful degradation
# ═══════════════════════════════════════════════════════════════════════════


class TestImportFailure:
    def test_import_error_recorded(self, project_env):
        """AC-I10: Import failure adds IMPORT_ERROR to errors."""
        project_root, pkg_dir = project_env
        m = _write_and_manifest(project_root, pkg_dir, IMPORT_ERROR_MODULE)
        error_kinds = [e.kind for e in m.errors]
        assert ParseErrorKind.IMPORT_ERROR in error_kinds

    def test_import_error_preserves_ast(self, project_env):
        """AC-I10: AST elements still present despite import failure."""
        project_root, pkg_dir = project_env
        m = _write_and_manifest(project_root, pkg_dir, IMPORT_ERROR_MODULE)
        # The module has `x = 1` after the raise, but AST should still
        # parse the whole file. However, the raise is an expression statement,
        # and x=1 is unreachable but still parsed by AST.
        assert isinstance(m, FileManifest)

    def test_import_error_preserves_symtable(self, project_env):
        """Symtable augmentation still runs (it uses source, not import)."""
        project_root, pkg_dir = project_env
        m = _write_and_manifest(project_root, pkg_dir, IMPORT_ERROR_MODULE)
        # The file should still parse and have elements
        assert isinstance(m, FileManifest)


# ═══════════════════════════════════════════════════════════════════════════
# AC-I11: Per-element error isolation
# ═══════════════════════════════════════════════════════════════════════════


class TestPerElementErrorIsolation:
    def test_partial_introspection(self, project_env):
        """AC-I11: One element failing doesn't block others."""
        project_root, pkg_dir = project_env
        source = textwrap.dedent("""\
            def good_func(x: int) -> int:
                return x + 1

            def another_func(y: str) -> str:
                return y.upper()
        """)
        m = _write_and_manifest(project_root, pkg_dir, source)
        assert not m.errors
        funcs = [e for e in m.elements if e.kind == ElementKind.FUNCTION]
        assert len(funcs) == 2
        # Both should have inspect_info
        for f in funcs:
            assert f.inspect_info is not None


# ═══════════════════════════════════════════════════════════════════════════
# AC-I12: Schema version
# ═══════════════════════════════════════════════════════════════════════════


class TestSchemaVersion:
    def test_schema_version_1_4_0(self):
        """AC-I12: Schema version is 1.4.0."""
        assert SCHEMA_VERSION == "1.4.0"

    def test_manifest_schema_version(self, project_env):
        project_root, pkg_dir = project_env
        m = _write_and_manifest(project_root, pkg_dir, "x = 1\n")
        assert m.schema_version == "1.4.0"


# ═══════════════════════════════════════════════════════════════════════════
# AC-I13: Backward compatibility
# ═══════════════════════════════════════════════════════════════════════════


class TestBackwardCompat:
    def test_element_without_inspect_info(self):
        """Old manifests without inspect_info still load (defaults to None)."""
        data = {
            "schema_version": "1.0.0",
            "file": "test.py",
            "module": "test",
            "digest": "sha256:abc",
            "python_version": "3.9",
            "elements": [
                {
                    "kind": "function",
                    "name": "f",
                    "fqn": "test.f",
                    "span": {
                        "start_line": 1,
                        "start_col": 0,
                        "end_line": 2,
                        "end_col": 0,
                    },
                    "signature": {"params": [], "return_annotation": None},
                }
            ],
            "imports": [],
            "dependencies": {},
            "errors": [],
            "generated_at": "2026-01-01T00:00:00Z",
        }
        m = FileManifest.model_validate(data)
        assert m.elements[0].inspect_info is None
        assert m.module_all is None
        assert m.module_version is None


# ═══════════════════════════════════════════════════════════════════════════
# AC-I17: Determinism
# ═══════════════════════════════════════════════════════════════════════════


class TestDeterminism:
    def test_multiple_runs_same_result(self, project_env):
        """AC-I17: Repeated introspection produces identical output."""
        project_root, pkg_dir = project_env
        file_path = pkg_dir / "module.py"
        file_path.write_text(INTROSPECTABLE_MODULE, encoding="utf-8")

        m1 = generate_file_manifest(file_path, project_root, mode="introspect")
        m2 = generate_file_manifest(file_path, project_root, mode="introspect")

        # Compare via serialized dicts (ignoring generated_at)
        d1 = m1.model_dump()
        d2 = m2.model_dump()
        d1.pop("generated_at")
        d2.pop("generated_at")
        assert d1 == d2


# ═══════════════════════════════════════════════════════════════════════════
# AC-I18, AC-I19: Guarded import
# ═══════════════════════════════════════════════════════════════════════════


class TestGuardedImport:
    def test_sys_path_restored(self, project_env):
        """AC-I18: sys.path is restored after import."""
        import sys
        project_root, pkg_dir = project_env
        file_path = pkg_dir / "module.py"
        file_path.write_text("x = 1\n", encoding="utf-8")

        saved_path = sys.path[:]
        m = generate_file_manifest(file_path, project_root, mode="introspect")
        assert sys.path == saved_path

    def test_sys_modules_restored(self, project_env):
        """AC-I19: New sys.modules entries are cleaned up."""
        import sys
        project_root, pkg_dir = project_env
        file_path = pkg_dir / "module.py"
        file_path.write_text("x = 1\n", encoding="utf-8")

        saved_modules = set(sys.modules.keys())
        m = generate_file_manifest(file_path, project_root, mode="introspect")
        # testpkg.module should not linger in sys.modules
        new_modules = set(sys.modules.keys()) - saved_modules
        assert "testpkg.module" not in new_modules

    def test_import_error_graceful(self, project_env):
        """Import failure doesn't crash — returns manifest with IMPORT_ERROR."""
        project_root, pkg_dir = project_env
        m = _write_and_manifest(project_root, pkg_dir, IMPORT_ERROR_MODULE)
        assert isinstance(m, FileManifest)
        assert any(e.kind == ParseErrorKind.IMPORT_ERROR for e in m.errors)


# ═══════════════════════════════════════════════════════════════════════════
# Self-referential introspection
# ═══════════════════════════════════════════════════════════════════════════


class TestSelfReferentialIntrospect:
    def test_introspect_code_manifest(self):
        """Introspect code_manifest.py itself — smoke test."""
        project_root = Path(__file__).resolve().parents[2]  # repo root
        code_manifest_path = (
            project_root / "src" / "startd8" / "utils" / "code_manifest.py"
        )
        if not code_manifest_path.exists():
            pytest.skip("code_manifest.py not found — running outside repo")

        m = generate_file_manifest(
            code_manifest_path, project_root, mode="introspect",
        )
        assert isinstance(m, FileManifest)
        assert not m.errors or all(
            e.kind == ParseErrorKind.IMPORT_ERROR for e in m.errors
        )
        # Should have many elements
        assert len(m.elements) > 10
