"""Phase 2 — MULTILANG_MANIFEST_VALIDATION (FR-1 builder, FR-2 adapter, FR-5 tiers).

Covers the authoritative tier (Python/C#/Java). Go/Node/Vue (advisory) land in Phase 3.
"""

from startd8.languages.manifest_adapter import (
    TIER_ADVISORY,
    TIER_AUTHORITATIVE,
    build_multilang_file_manifest,
)
from startd8.utils.code_manifest import ElementKind, generate_file_manifest
from startd8.forward_manifest import ForwardElementSpec, ForwardFileSpec
from startd8.forward_manifest_validator import _validate_file_spec
from startd8.utils.manifest_registry import ManifestRegistry

CSHARP_SRC = """
namespace Demo;
public interface IGreeter { string Hello(); }
public class Greeter : IGreeter {
    public string Hello() { return "hi"; }
}
public enum Color { Red, Green }
"""

JAVA_SRC = """
package demo;
import java.util.List;
public class Greeter {
    public String hello() { return "hi"; }
}
interface Runnable2 { void run(); }
"""


def _names(manifest):
    return {e.name for e in manifest.elements}


def _kinds(manifest):
    return {e.name: e.kind for e in manifest.elements}


class TestBuilderDispatch:
    def test_python_delegates_and_is_authoritative(self):
        src = "EXPECTED = 1\ndef foo():\n    return 1\n"
        manifest = build_multilang_file_manifest("mod.py", src)
        assert manifest.parser_tier == TIER_AUTHORITATIVE
        assert "EXPECTED" in _names(manifest) and "foo" in _names(manifest)

    def test_python_golden_master_matches_generate_file_manifest(self):
        # FR-7/R1-F10: the builder's Python path is byte/structure-identical to the
        # inline generate_file_manifest (modulo the additive parser_tier stamp).
        from pathlib import Path

        src = "import os\nCONST = 2\nclass A:\n    def m(self):\n        return 1\n"
        inline = generate_file_manifest(file_path="m.py", project_root=Path("."), source=src)
        built = build_multilang_file_manifest("m.py", src)
        assert [e.name for e in built.elements] == [e.name for e in inline.elements]
        assert [i.module for i in built.imports] == [i.module for i in inline.imports]

    def test_unsupported_language_empty_no_raise(self):
        manifest = build_multilang_file_manifest("main.rs", "fn main() {}")
        assert manifest.elements == [] and manifest.parser_tier is None


class TestCSharpAdapter:
    def test_elements_and_kinds(self):
        manifest = build_multilang_file_manifest("Greeter.cs", CSHARP_SRC)
        names = _names(manifest)
        assert {"IGreeter", "Greeter", "Hello", "Color"} <= names
        kinds = _kinds(manifest)
        assert kinds["IGreeter"] is ElementKind.INTERFACE
        assert kinds["Greeter"] is ElementKind.CLASS
        assert kinds["Hello"] is ElementKind.METHOD  # callable -> has synthesized Signature
        assert kinds["Color"] is ElementKind.ENUM
        # tier is authoritative (tree-sitter) or advisory (regex fallback) — both valid.
        assert manifest.parser_tier in (TIER_AUTHORITATIVE, TIER_ADVISORY)


class TestJavaAdapter:
    def test_elements_kinds_and_imports(self):
        manifest = build_multilang_file_manifest("Greeter.java", JAVA_SRC)
        names = _names(manifest)
        assert {"Greeter", "hello"} <= names
        assert _kinds(manifest)["hello"] is ElementKind.METHOD
        assert any(i.module == "java.util.List" for i in manifest.imports)
        assert manifest.parser_tier in (TIER_AUTHORITATIVE, TIER_ADVISORY)


class TestFr5SeverityCalibration:
    def _spec(self, path):
        return ForwardFileSpec(
            file=path,
            elements=[ForwardElementSpec(kind=ElementKind.CLASS, name="Missing")],
        )

    def test_authoritative_miss_is_error(self):
        # A C#/Java/Python manifest with an authoritative tier yields an `error` for a
        # genuinely-missing element. Use Python (always authoritative) for determinism.
        manifest = build_multilang_file_manifest("mod.py", "X = 1\n")
        reg = ManifestRegistry({"mod.py": manifest})
        viols = _validate_file_spec("mod.py", self._spec("mod.py"), reg)
        assert len(viols) == 1
        assert viols[0].severity == "error"
        assert viols[0].tier == TIER_AUTHORITATIVE

    def test_advisory_miss_is_warning_with_tier(self):
        # Simulate an advisory (regex-grade) parse via model_copy; the validator must demote
        # the missing-element violation to `warning` and stamp tier="advisory" (FR-5/R1-F9).
        manifest = build_multilang_file_manifest("mod.py", "X = 1\n").model_copy(
            update={"parser_tier": TIER_ADVISORY}
        )
        reg = ManifestRegistry({"mod.py": manifest})
        viols = _validate_file_spec("mod.py", self._spec("mod.py"), reg)
        assert len(viols) == 1
        assert viols[0].severity == "warning"
        assert viols[0].tier == TIER_ADVISORY


GO_SRC = (
    "package main\n"
    'import "fmt"\n'
    "func Hello() string { return \"hi\" }\n"
    "type Greeter struct{}\n"
)
NODE_SRC = "export function hello() {}\nexport class Greeter {}\n"
VUE_SRC = "<script setup>\nfunction hello() {}\n</script>\n<template><div/></template>\n"


class TestAdvisoryTierAdapters:
    """Phase 3 (FR-2 advisory tier): Go/Node/Vue regex parsers feed the registry at the
    advisory tier — extraction works and a miss is a `warning`, never blocking."""

    def test_go_extraction_and_advisory_tier(self):
        m = build_multilang_file_manifest("svc.go", GO_SRC)
        names = {e.name for e in m.elements}
        assert {"Hello", "Greeter"} <= names
        assert m.parser_tier == TIER_ADVISORY
        assert any(i.module == "fmt" for i in m.imports)

    def test_nodejs_extraction_and_advisory_tier(self):
        m = build_multilang_file_manifest("app.ts", NODE_SRC)
        names = {e.name for e in m.elements}
        assert {"hello", "Greeter"} <= names
        assert m.parser_tier == TIER_ADVISORY

    def test_vue_extraction_and_advisory_tier(self):
        m = build_multilang_file_manifest("App.vue", VUE_SRC)
        assert "hello" in {e.name for e in m.elements}
        assert m.parser_tier == TIER_ADVISORY

    def test_node_jsx_routes_to_node_adapter(self):
        m = build_multilang_file_manifest("Component.jsx", NODE_SRC)
        assert m.parser_tier == TIER_ADVISORY
        assert "hello" in {e.name for e in m.elements}


class TestAdvisoryEndToEndSeverity:
    """FR-5 acceptance via a REAL advisory parse (not a simulated tier): a Go/Node file whose
    spec declares a missing element yields a `warning` (tier=advisory), never a blocking error."""

    def test_go_missing_element_is_warning_not_error(self):
        m = build_multilang_file_manifest("svc.go", GO_SRC)
        reg = ManifestRegistry({"svc.go": m})
        # Use a non-callable kind: ForwardElementSpec (like Element) requires a Signature
        # for callable kinds, and the missing-element assertion doesn't need one.
        spec = ForwardFileSpec(
            file="svc.go",
            elements=[ForwardElementSpec(kind=ElementKind.CLASS, name="NotThere")],
        )
        viols = _validate_file_spec("svc.go", spec, reg)
        assert len(viols) == 1
        assert viols[0].severity == "warning"   # advisory → never blocks
        assert viols[0].tier == TIER_ADVISORY

    def test_node_present_element_no_violation(self):
        m = build_multilang_file_manifest("app.ts", NODE_SRC)
        reg = ManifestRegistry({"app.ts": m})
        spec = ForwardFileSpec(
            file="app.ts",
            elements=[ForwardElementSpec(kind=ElementKind.CLASS, name="Greeter")],
        )
        assert _validate_file_spec("app.ts", spec, reg) == []


NEXT_CONFIG_SRC = "const config = { reactStrictMode: true };\nexport default config;\n"
TAILWIND_SRC = "export default {\n  content: ['./src/**/*.{js,ts}'],\n};\n"


class TestFr4DefaultExport:
    """FR-4: nodejs_parser emits DEFAULT_EXPORT (named binding or sentinel), the framework
    registry uses DEFAULT_EXPORT for JS/TS configs, and a default-export config validates
    clean while a wrong-shape (`export class config`) draft is caught."""

    def test_next_config_named_binding_default_export(self):
        m = build_multilang_file_manifest("next.config.mjs", NEXT_CONFIG_SRC)
        de = [e for e in m.elements if e.kind is ElementKind.DEFAULT_EXPORT]
        assert len(de) == 1 and de[0].name == "config"  # the bound name

    def test_tailwind_anonymous_default_export_sentinel(self):
        m = build_multilang_file_manifest("tailwind.config.js", TAILWIND_SRC)
        de = [e for e in m.elements if e.kind is ElementKind.DEFAULT_EXPORT]
        assert len(de) == 1 and de[0].name == "default"

    def test_framework_registry_uses_default_export_for_js(self):
        from startd8.forward_manifest_extractor import apply_framework_defaults

        fe = {"next.config.mjs": []}
        apply_framework_defaults(fe)
        assert fe["next.config.mjs"][0].kind is ElementKind.DEFAULT_EXPORT
        assert fe["next.config.mjs"][0].name == "config"

    def test_compliant_next_config_validates_clean(self):
        # The convention's DEFAULT_EXPORT name="config" matches the parsed default export.
        m = build_multilang_file_manifest("next.config.mjs", NEXT_CONFIG_SRC)
        reg = ManifestRegistry({"next.config.mjs": m})
        spec = ForwardFileSpec(
            file="next.config.mjs",
            elements=[ForwardElementSpec(kind=ElementKind.DEFAULT_EXPORT, name="config")],
        )
        assert _validate_file_spec("next.config.mjs", spec, reg) == []

    def test_wrong_shape_export_class_is_flagged(self):
        # PI-003: drafter emits `export class config` instead of a default-export object.
        # The expected `config` default-export is absent -> a violation (advisory tier=warning).
        wrong = "export class config { foo() {} }\n"
        m = build_multilang_file_manifest("next.config.mjs", wrong)
        reg = ManifestRegistry({"next.config.mjs": m})
        spec = ForwardFileSpec(
            file="next.config.mjs",
            elements=[ForwardElementSpec(kind=ElementKind.DEFAULT_EXPORT, name="config")],
        )
        viols = _validate_file_spec("next.config.mjs", spec, reg)
        assert len(viols) == 1
        assert viols[0].violation_type == "missing_default_export"
        assert viols[0].severity == "warning"  # .mjs is advisory tier

    def test_r1f6_legacy_constant_contract_still_matches(self):
        # R1-F6 / name-based equivalence: a contract authored with the OLD sentinel
        # (CONSTANT name="default") still validates clean against a DEFAULT_EXPORT-extracted
        # element of the same name — matching is by name, so the cutover is non-breaking.
        m = build_multilang_file_manifest("tailwind.config.js", TAILWIND_SRC)
        reg = ManifestRegistry({"tailwind.config.js": m})
        legacy_spec = ForwardFileSpec(
            file="tailwind.config.js",
            elements=[ForwardElementSpec(kind=ElementKind.CONSTANT, name="default")],
        )
        assert _validate_file_spec("tailwind.config.js", legacy_spec, reg) == []
