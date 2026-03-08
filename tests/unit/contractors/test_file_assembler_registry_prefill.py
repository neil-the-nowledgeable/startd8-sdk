"""
Unit tests for REQ-MP-1106: Element registry pre-fill in DeterministicFileAssembler.

Covers:
- Element in registry -> pre-filled code emitted
- Element not in registry -> stub emitted
- Cached code fails ast.parse -> falls back to stub
- Traceability comment present
- Registry error -> stub emitted (non-fatal)
- Pre-filled elements skipped by skeleton spec extractor (micro-prime skip)
"""

from __future__ import annotations

import ast
from typing import Optional
from unittest.mock import MagicMock

import pytest

from startd8.element_registry import ElementEntry, ElementRegistry
from startd8.forward_manifest import (
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardManifest,
)
from startd8.utils.code_manifest import (
    ElementKind,
    Param,
    Signature,
    Visibility,
)
from startd8.utils.file_assembler import (
    SKELETON_SENTINEL,
    DeterministicFileAssembler,
)


# ── Helpers ───────────────────────────────────────────────────────────────


def _make_func_with_contract_id(
    name: str = "compute",
    contract_id: str = "flcm-test:1:compute",
    params: Optional[list[Param]] = None,
    return_annotation: Optional[str] = None,
    parent_class: Optional[str] = None,
) -> ForwardElementSpec:
    """Create a ForwardElementSpec with a source_contract_id for registry lookup."""
    kind = ElementKind.METHOD if parent_class else ElementKind.FUNCTION
    return ForwardElementSpec(
        kind=kind,
        name=name,
        signature=Signature(
            params=params or [],
            return_annotation=return_annotation,
        ),
        visibility=Visibility.PUBLIC,
        source_contract_id=contract_id,
        parent_class=parent_class,
    )


def _make_registry_with_code(
    element_id: str,
    code: str,
) -> ElementRegistry:
    """Create an ElementRegistry with a single entry containing cached code."""
    reg = ElementRegistry()
    entry = ElementEntry(
        element_id=element_id,
        kind="function",
        name="test",
        extra={"code": code},
    )
    reg.put(entry)
    return reg


def _make_manifest_single(
    elements: list[ForwardElementSpec],
    file_path: str = "src/mod.py",
) -> ForwardManifest:
    return ForwardManifest(
        file_specs={
            file_path: ForwardFileSpec(
                file=file_path,
                elements=elements,
            ),
        }
    )


def _render_single(
    elements: list[ForwardElementSpec],
    element_registry: Optional[ElementRegistry] = None,
) -> str:
    """Render a single file with optional element registry."""
    manifest = _make_manifest_single(elements)
    assembler = DeterministicFileAssembler(element_registry=element_registry)
    result = assembler.render_specs(manifest)
    assert len(result.specs) == 1, f"Expected 1 file, got {len(result.specs)}"
    return list(result.specs.values())[0]


# ═══════════════════════════════════════════════════════════════════════════
# Element in registry -> pre-filled code emitted
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestRegistryPreFill:

    def test_registry_code_emitted(self):
        """When element is in registry with valid code, emit it instead of stub."""
        contract_id = "flcm-test:1:compute"
        reg = _make_registry_with_code(contract_id, "return 42")
        elem = _make_func_with_contract_id("compute", contract_id)

        src = _render_single([elem], element_registry=reg)

        assert "return 42" in src
        assert "raise NotImplementedError" not in src

    def test_multiline_registry_code_emitted(self):
        """Multi-line cached code should be properly indented."""
        contract_id = "flcm-test:1:process"
        code = "result = x + y\nreturn result"
        reg = _make_registry_with_code(contract_id, code)
        elem = _make_func_with_contract_id("process", contract_id)

        src = _render_single([elem], element_registry=reg)

        assert "    result = x + y" in src
        assert "    return result" in src
        assert "raise NotImplementedError" not in src

    def test_registry_code_passes_ast_parse(self):
        """Rendered file with registry code must pass ast.parse."""
        contract_id = "flcm-test:1:compute"
        reg = _make_registry_with_code(contract_id, "return 42")
        elem = _make_func_with_contract_id("compute", contract_id)

        src = _render_single([elem], element_registry=reg)
        ast.parse(src)  # Should not raise

    def test_method_in_class_prefilled(self):
        """Registry pre-fill works for methods inside classes."""
        contract_id = "flcm-test:1:MyClass.run"
        reg = _make_registry_with_code(contract_id, "return self._data")

        class_elem = ForwardElementSpec(
            kind=ElementKind.CLASS,
            name="MyClass",
        )
        method_elem = _make_func_with_contract_id(
            "run", contract_id,
            params=[Param(name="self")],
            parent_class="MyClass",
        )

        src = _render_single([class_elem, method_elem], element_registry=reg)

        assert "return self._data" in src
        assert "raise NotImplementedError" not in src


# ═══════════════════════════════════════════════════════════════════════════
# Element not in registry -> stub emitted
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestRegistryMiss:

    def test_no_registry_emits_stub(self):
        """Without a registry, emit raise NotImplementedError."""
        elem = _make_func_with_contract_id("compute", "flcm-test:1:compute")
        src = _render_single([elem])
        assert "raise NotImplementedError" in src

    def test_element_not_in_registry_emits_stub(self):
        """Element with contract_id not in registry should emit stub."""
        reg = ElementRegistry()  # empty
        elem = _make_func_with_contract_id("compute", "flcm-test:1:compute")
        src = _render_single([elem], element_registry=reg)
        assert "raise NotImplementedError" in src

    def test_no_contract_id_emits_stub(self):
        """Element without source_contract_id should emit stub."""
        reg = _make_registry_with_code("some-id", "return 42")
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="compute",
            signature=Signature(params=[]),
        )
        src = _render_single([elem], element_registry=reg)
        assert "raise NotImplementedError" in src

    def test_empty_code_in_registry_emits_stub(self):
        """Entry with empty code string should fall back to stub."""
        contract_id = "flcm-test:1:compute"
        reg = ElementRegistry()
        entry = ElementEntry(
            element_id=contract_id,
            kind="function",
            name="compute",
            extra={"code": ""},
        )
        reg.put(entry)
        elem = _make_func_with_contract_id("compute", contract_id)
        src = _render_single([elem], element_registry=reg)
        assert "raise NotImplementedError" in src

    def test_non_string_code_in_registry_emits_stub(self):
        """Entry with non-string code should fall back to stub."""
        contract_id = "flcm-test:1:compute"
        reg = ElementRegistry()
        entry = ElementEntry(
            element_id=contract_id,
            kind="function",
            name="compute",
            extra={"code": 12345},
        )
        reg.put(entry)
        elem = _make_func_with_contract_id("compute", contract_id)
        src = _render_single([elem], element_registry=reg)
        assert "raise NotImplementedError" in src


# ═══════════════════════════════════════════════════════════════════════════
# Cached code fails ast.parse -> falls back to stub
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestRegistryAstValidation:

    def test_invalid_syntax_falls_back_to_stub(self):
        """Cached code with syntax errors should fall back to stub."""
        contract_id = "flcm-test:1:compute"
        reg = _make_registry_with_code(contract_id, "return (((")
        elem = _make_func_with_contract_id("compute", contract_id)

        src = _render_single([elem], element_registry=reg)

        assert "raise NotImplementedError" in src
        assert "return (((" not in src

    def test_invalid_syntax_logs_warning(self, caplog):
        """Cached code with syntax errors should log a warning."""
        contract_id = "flcm-test:1:compute"
        reg = _make_registry_with_code(contract_id, "def broken(:")
        elem = _make_func_with_contract_id("compute", contract_id)

        with caplog.at_level("WARNING"):
            _render_single([elem], element_registry=reg)

        assert any("ast.parse" in r.message or "validation" in r.message
                    for r in caplog.records)

    def test_valid_complex_code_accepted(self):
        """Valid multi-statement code should pass validation."""
        contract_id = "flcm-test:1:process"
        code = (
            "items = []\n"
            "for i in range(10):\n"
            "    items.append(i * 2)\n"
            "return items"
        )
        reg = _make_registry_with_code(contract_id, code)
        elem = _make_func_with_contract_id("process", contract_id)

        src = _render_single([elem], element_registry=reg)

        assert "items = []" in src
        assert "raise NotImplementedError" not in src
        ast.parse(src)  # Full file must parse


# ═══════════════════════════════════════════════════════════════════════════
# Traceability comment present
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestTraceabilityComment:

    def test_traceability_comment_emitted(self):
        """Pre-filled code should include ELEMENT-REGISTRY traceability comment."""
        contract_id = "flcm-test:1:compute"
        reg = _make_registry_with_code(contract_id, "return 42")
        elem = _make_func_with_contract_id("compute", contract_id)

        src = _render_single([elem], element_registry=reg)

        assert f"# [ELEMENT-REGISTRY: {contract_id}]" in src

    def test_traceability_comment_before_code(self):
        """Traceability comment should appear before the cached code."""
        contract_id = "flcm-test:1:compute"
        reg = _make_registry_with_code(contract_id, "return 42")
        elem = _make_func_with_contract_id("compute", contract_id)

        src = _render_single([elem], element_registry=reg)

        comment_idx = src.index(f"# [ELEMENT-REGISTRY: {contract_id}]")
        code_idx = src.index("return 42")
        assert comment_idx < code_idx

    def test_no_traceability_comment_on_stub(self):
        """Stub fallback should not include ELEMENT-REGISTRY comment."""
        elem = _make_func_with_contract_id("compute", "flcm-test:1:compute")
        src = _render_single([elem])
        assert "ELEMENT-REGISTRY" not in src

    def test_traceability_comment_parseable(self):
        """File with traceability comment must still pass ast.parse."""
        contract_id = "flcm-test:1:compute"
        reg = _make_registry_with_code(contract_id, "return 42")
        elem = _make_func_with_contract_id("compute", contract_id)

        src = _render_single([elem], element_registry=reg)
        ast.parse(src)  # Should not raise


# ═══════════════════════════════════════════════════════════════════════════
# Registry error -> stub emitted (non-fatal)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestRegistryErrors:

    def test_registry_get_raises_falls_back_to_stub(self):
        """If registry.get() raises, fall back to stub gracefully."""
        mock_registry = MagicMock()
        mock_registry.get.side_effect = RuntimeError("Registry corrupted")

        elem = _make_func_with_contract_id("compute", "flcm-test:1:compute")
        src = _render_single([elem], element_registry=mock_registry)

        assert "raise NotImplementedError" in src
        assert "ELEMENT-REGISTRY" not in src

    def test_registry_error_logs_warning(self, caplog):
        """Registry errors should log a warning."""
        mock_registry = MagicMock()
        mock_registry.get.side_effect = RuntimeError("Disk failure")

        elem = _make_func_with_contract_id("compute", "flcm-test:1:compute")

        with caplog.at_level("WARNING"):
            _render_single([elem], element_registry=mock_registry)

        assert any("registry lookup failed" in r.message.lower()
                    for r in caplog.records)

    def test_registry_extra_missing_code_key(self):
        """Entry.extra without 'code' key should fall back to stub."""
        contract_id = "flcm-test:1:compute"
        reg = ElementRegistry()
        entry = ElementEntry(
            element_id=contract_id,
            kind="function",
            name="compute",
            extra={"other_data": "value"},
        )
        reg.put(entry)
        elem = _make_func_with_contract_id("compute", contract_id)
        src = _render_single([elem], element_registry=reg)
        assert "raise NotImplementedError" in src


# ═══════════════════════════════════════════════════════════════════════════
# Micro-prime skip: pre-filled elements not seen as stubs
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestMicroPrimeSkip:

    def test_prefilled_element_not_detected_as_stub(self):
        """Pre-filled elements should not be detected as stubs by skeleton extractor."""
        from startd8.micro_prime.skeleton_spec_extractor import extract_skeleton_specs

        contract_id = "flcm-test:1:compute"
        reg = _make_registry_with_code(contract_id, "return 42")
        elem = _make_func_with_contract_id("compute", contract_id)

        src = _render_single([elem], element_registry=reg)

        # The skeleton spec extractor should find zero stubs
        specs = extract_skeleton_specs(src, "src/mod.py")
        assert len(specs) == 0, (
            f"Expected 0 stub specs for pre-filled element, got {len(specs)}"
        )

    def test_stub_element_detected_by_extractor(self):
        """Elements with raise NotImplementedError should be detected as stubs."""
        from startd8.micro_prime.skeleton_spec_extractor import extract_skeleton_specs

        elem = _make_func_with_contract_id("compute", "flcm-test:1:compute")
        src = _render_single([elem])  # No registry -> stub

        specs = extract_skeleton_specs(src, "src/mod.py")
        assert len(specs) == 1, (
            f"Expected 1 stub spec for NotImplementedError element, got {len(specs)}"
        )

    def test_mixed_prefilled_and_stub(self):
        """File with both pre-filled and stub elements: only stubs detected."""
        from startd8.micro_prime.skeleton_spec_extractor import extract_skeleton_specs

        contract_id = "flcm-test:1:prefilled"
        reg = _make_registry_with_code(contract_id, "return 42")

        prefilled = _make_func_with_contract_id("prefilled", contract_id)
        stub = _make_func_with_contract_id("stub_fn", "flcm-test:1:stub_fn")

        src = _render_single([prefilled, stub], element_registry=reg)

        specs = extract_skeleton_specs(src, "src/mod.py")
        assert len(specs) == 1
        assert specs[0].name == "stub_fn"
