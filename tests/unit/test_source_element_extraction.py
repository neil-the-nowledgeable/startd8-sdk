"""REQ-EE-200: Go/Java source element extraction into ForwardElementSpec.

Tests that GoElement and JavaElement objects from the language parsers are
correctly converted to ForwardElementSpec objects for MicroPrime element-level
generation, and that source-derived elements take precedence over parse-llm
elements.
"""

from __future__ import annotations

import pytest

from startd8.forward_manifest import ForwardElementSpec
from startd8.forward_manifest_extractor import (
    _go_elements_to_specs,
    _java_elements_to_specs,
)
from startd8.languages.go_parser import GoElement
from startd8.languages.java_parser import JavaElement
from startd8.utils.code_manifest import ElementKind, Signature


# ═══════════════════════════════════════════════════════════════════════════
# Go → ForwardElementSpec
# ═══════════════════════════════════════════════════════════════════════════


class TestGoElementsToSpecs:
    """Test _go_elements_to_specs converter."""

    def test_function_element(self):
        elements = [
            GoElement(
                kind="function",
                name="HandleRequest",
                signature="w http.ResponseWriter, r *http.Request",
                return_type="error",
                is_exported=True,
                line_number=10,
            ),
        ]
        specs = _go_elements_to_specs(elements, "pkg/handler.go")
        assert len(specs) == 1
        spec = specs[0]
        assert spec.kind == ElementKind.FUNCTION
        assert spec.name == "HandleRequest"
        assert spec.signature is not None
        assert spec.signature.return_annotation == "error"
        assert spec.decomposition_source == "source-go-parser"
        assert spec.parent_class is None

    def test_method_element(self):
        elements = [
            GoElement(
                kind="method",
                name="Start",
                signature="ctx context.Context",
                return_type="error",
                parent_type="Server",
                receiver_name="s",
                is_pointer_receiver=True,
                is_exported=True,
                line_number=25,
            ),
        ]
        specs = _go_elements_to_specs(elements, "pkg/server.go")
        assert len(specs) == 1
        spec = specs[0]
        assert spec.kind == ElementKind.METHOD
        assert spec.name == "Start"
        assert spec.parent_class == "Server"
        assert spec.signature is not None
        assert spec.decomposition_source == "source-go-parser"

    def test_struct_element(self):
        elements = [
            GoElement(
                kind="class",
                name="Config",
                bases=["BaseConfig"],
                is_exported=True,
                is_interface=False,
                line_number=5,
            ),
        ]
        specs = _go_elements_to_specs(elements, "pkg/config.go")
        assert len(specs) == 1
        spec = specs[0]
        assert spec.kind == ElementKind.CLASS
        assert spec.name == "Config"
        assert spec.bases == ["BaseConfig"]
        assert spec.is_abstract is False
        assert spec.signature is None
        assert spec.decomposition_source == "source-go-parser"

    def test_interface_element(self):
        elements = [
            GoElement(
                kind="class",
                name="Handler",
                is_exported=True,
                is_interface=True,
                line_number=15,
            ),
        ]
        specs = _go_elements_to_specs(elements, "pkg/handler.go")
        assert len(specs) == 1
        spec = specs[0]
        assert spec.kind == ElementKind.CLASS
        assert spec.name == "Handler"
        assert spec.is_abstract is True

    def test_skips_constants_and_variables(self):
        elements = [
            GoElement(kind="constant", name="MaxRetries", is_exported=True, line_number=1),
            GoElement(kind="variable", name="defaultLogger", is_exported=False, line_number=2),
            GoElement(kind="type_alias", name="ID", is_exported=True, line_number=3),
            GoElement(kind="function", name="Run", is_exported=True, line_number=10),
        ]
        specs = _go_elements_to_specs(elements, "pkg/main.go")
        assert len(specs) == 1
        assert specs[0].name == "Run"

    def test_empty_name_skipped(self):
        elements = [GoElement(kind="function", name="", line_number=1)]
        specs = _go_elements_to_specs(elements, "pkg/main.go")
        assert len(specs) == 0

    def test_empty_elements(self):
        specs = _go_elements_to_specs([], "pkg/main.go")
        assert specs == []

    def test_function_no_return_type(self):
        elements = [
            GoElement(kind="function", name="init", is_exported=False, line_number=1),
        ]
        specs = _go_elements_to_specs(elements, "pkg/main.go")
        assert len(specs) == 1
        assert specs[0].signature.return_annotation is None


# ═══════════════════════════════════════════════════════════════════════════
# Java → ForwardElementSpec
# ═══════════════════════════════════════════════════════════════════════════


class TestJavaElementsToSpecs:
    """Test _java_elements_to_specs converter."""

    def test_class_element(self):
        elements = [
            JavaElement(
                kind="class",
                name="UserService",
                modifiers=["public"],
                extends="BaseService",
                implements=["Serializable", "Cloneable"],
                line_number=10,
            ),
        ]
        specs = _java_elements_to_specs(elements, "src/UserService.java")
        assert len(specs) == 1
        spec = specs[0]
        assert spec.kind == ElementKind.CLASS
        assert spec.name == "UserService"
        assert "BaseService" in spec.bases
        assert "Serializable" in spec.bases
        assert "Cloneable" in spec.bases
        assert spec.is_abstract is False
        assert spec.decomposition_source == "source-java-parser"

    def test_interface_element(self):
        elements = [
            JavaElement(
                kind="interface",
                name="Repository",
                modifiers=["public"],
                line_number=5,
            ),
        ]
        specs = _java_elements_to_specs(elements, "src/Repository.java")
        assert len(specs) == 1
        spec = specs[0]
        assert spec.kind == ElementKind.CLASS
        assert spec.name == "Repository"
        assert spec.is_abstract is True

    def test_enum_element(self):
        elements = [
            JavaElement(
                kind="enum",
                name="Status",
                modifiers=["public"],
                line_number=3,
            ),
        ]
        specs = _java_elements_to_specs(elements, "src/Status.java")
        assert len(specs) == 1
        spec = specs[0]
        assert spec.kind == ElementKind.CLASS
        assert spec.name == "Status"
        assert spec.is_abstract is False

    def test_method_element(self):
        elements = [
            JavaElement(
                kind="method",
                name="findById",
                modifiers=["public"],
                parent="UserService",
                return_type="User",
                signature="long id",
                line_number=20,
            ),
        ]
        specs = _java_elements_to_specs(elements, "src/UserService.java")
        assert len(specs) == 1
        spec = specs[0]
        assert spec.kind == ElementKind.METHOD
        assert spec.name == "findById"
        assert spec.parent_class == "UserService"
        assert spec.signature is not None
        assert spec.signature.return_annotation == "User"
        assert spec.is_static is False
        assert spec.decomposition_source == "source-java-parser"

    def test_static_method(self):
        elements = [
            JavaElement(
                kind="method",
                name="getInstance",
                modifiers=["public", "static"],
                parent="Factory",
                return_type="Factory",
                line_number=15,
            ),
        ]
        specs = _java_elements_to_specs(elements, "src/Factory.java")
        assert len(specs) == 1
        assert specs[0].is_static is True

    def test_abstract_method(self):
        elements = [
            JavaElement(
                kind="method",
                name="process",
                modifiers=["abstract", "public"],
                parent="Handler",
                return_type="void",
                line_number=12,
            ),
        ]
        specs = _java_elements_to_specs(elements, "src/Handler.java")
        assert len(specs) == 1
        assert specs[0].is_abstract is True

    def test_constructor_element(self):
        elements = [
            JavaElement(
                kind="constructor",
                name="UserService",
                modifiers=["public"],
                parent="UserService",
                signature="UserRepository repo",
                line_number=8,
            ),
        ]
        specs = _java_elements_to_specs(elements, "src/UserService.java")
        assert len(specs) == 1
        spec = specs[0]
        assert spec.kind == ElementKind.METHOD
        assert spec.name == "UserService"
        assert spec.parent_class == "UserService"

    def test_skips_fields_and_constants(self):
        elements = [
            JavaElement(kind="field", name="logger", modifiers=["private"], line_number=3),
            JavaElement(kind="constant", name="MAX_SIZE", modifiers=["public", "static", "final"], line_number=4),
            JavaElement(kind="method", name="run", modifiers=["public"], parent="App", line_number=10),
        ]
        specs = _java_elements_to_specs(elements, "src/App.java")
        assert len(specs) == 1
        assert specs[0].name == "run"

    def test_empty_name_skipped(self):
        elements = [JavaElement(kind="method", name="", line_number=1)]
        specs = _java_elements_to_specs(elements, "src/App.java")
        assert len(specs) == 0

    def test_empty_elements(self):
        specs = _java_elements_to_specs([], "src/App.java")
        assert specs == []

    def test_record_element(self):
        elements = [
            JavaElement(
                kind="record",
                name="Point",
                modifiers=["public"],
                line_number=1,
            ),
        ]
        specs = _java_elements_to_specs(elements, "src/Point.java")
        assert len(specs) == 1
        assert specs[0].kind == ElementKind.CLASS
        assert specs[0].name == "Point"


# ═══════════════════════════════════════════════════════════════════════════
# Source precedence
# ═══════════════════════════════════════════════════════════════════════════


class TestSourcePrecedence:
    """Test that source-derived elements replace parse-llm elements."""

    def test_source_go_replaces_parse_llm(self):
        file_elements: dict[str, list[ForwardElementSpec]] = {
            "pkg/handler.go": [
                ForwardElementSpec(
                    kind=ElementKind.FUNCTION,
                    name="OldFunction",
                    signature=Signature(params=[], return_annotation=None),
                    decomposition_source="parse-llm",
                ),
            ],
        }

        go_elements = [
            GoElement(kind="function", name="HandleRequest", is_exported=True, line_number=1),
        ]
        go_specs = _go_elements_to_specs(go_elements, "pkg/handler.go")

        # Simulate the precedence logic from _reconcile_go_file
        existing = file_elements.get("pkg/handler.go", [])
        non_parse = [e for e in existing if e.decomposition_source != "parse-llm"]
        file_elements["pkg/handler.go"] = non_parse + go_specs

        specs = file_elements["pkg/handler.go"]
        assert len(specs) == 1
        assert specs[0].name == "HandleRequest"
        assert specs[0].decomposition_source == "source-go-parser"

    def test_source_java_replaces_parse_llm(self):
        file_elements: dict[str, list[ForwardElementSpec]] = {
            "src/App.java": [
                ForwardElementSpec(
                    kind=ElementKind.CLASS,
                    name="OldClass",
                    decomposition_source="parse-llm",
                ),
            ],
        }

        java_elements = [
            JavaElement(kind="class", name="App", modifiers=["public"], line_number=1),
        ]
        java_specs = _java_elements_to_specs(java_elements, "src/App.java")

        # Simulate the precedence logic from _reconcile_java_file
        existing = file_elements.get("src/App.java", [])
        non_parse = [e for e in existing if e.decomposition_source != "parse-llm"]
        file_elements["src/App.java"] = non_parse + java_specs

        specs = file_elements["src/App.java"]
        assert len(specs) == 1
        assert specs[0].name == "App"
        assert specs[0].decomposition_source == "source-java-parser"

    def test_non_parse_elements_preserved(self):
        """Non-parse-llm elements (e.g., human-yaml) are preserved alongside source."""
        yaml_spec = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="YamlDefined",
            signature=Signature(params=[], return_annotation=None),
            decomposition_source="human-yaml",
        )
        parse_spec = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="ParseDerived",
            signature=Signature(params=[], return_annotation=None),
            decomposition_source="parse-llm",
        )
        file_elements: dict[str, list[ForwardElementSpec]] = {
            "pkg/main.go": [yaml_spec, parse_spec],
        }

        go_elements = [
            GoElement(kind="function", name="NewFunc", is_exported=True, line_number=1),
        ]
        go_specs = _go_elements_to_specs(go_elements, "pkg/main.go")

        existing = file_elements.get("pkg/main.go", [])
        non_parse = [e for e in existing if e.decomposition_source != "parse-llm"]
        file_elements["pkg/main.go"] = non_parse + go_specs

        specs = file_elements["pkg/main.go"]
        names = {s.name for s in specs}
        assert "YamlDefined" in names, "human-yaml element should be preserved"
        assert "NewFunc" in names, "source-go-parser element should be added"
        assert "ParseDerived" not in names, "parse-llm element should be removed"

    def test_no_existing_elements(self):
        """Source elements populate empty file_elements entry."""
        file_elements: dict[str, list[ForwardElementSpec]] = {}

        go_elements = [
            GoElement(kind="function", name="New", is_exported=True, line_number=1),
        ]
        go_specs = _go_elements_to_specs(go_elements, "pkg/new.go")

        existing = file_elements.get("pkg/new.go", [])
        non_parse = [e for e in existing if e.decomposition_source != "parse-llm"]
        file_elements["pkg/new.go"] = non_parse + go_specs

        assert len(file_elements["pkg/new.go"]) == 1
        assert file_elements["pkg/new.go"][0].name == "New"
