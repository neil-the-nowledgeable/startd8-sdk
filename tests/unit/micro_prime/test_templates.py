"""Tests for the Micro Prime Template Registry (REQ-MP-300–304)."""

from __future__ import annotations

import ast

import pytest

from startd8.forward_manifest import ForwardElementSpec
from startd8.micro_prime.templates import TemplateRegistry
from startd8.utils.code_manifest import ElementKind, Param, Signature


class TestTemplateRegistry:
    """Tests for TemplateRegistry.match()."""

    def test_disabled_returns_none(self, simple_function_element):
        """REQ-MP-303: Bypass flag disables template matching."""
        registry = TemplateRegistry(enabled=False)
        assert registry.match(simple_function_element) is None

    def test_enabled_toggle(self):
        registry = TemplateRegistry(enabled=True)
        assert registry.enabled is True
        registry.enabled = False
        assert registry.enabled is False

    def test_no_match_for_regular_function(self, simple_function_element):
        """Regular functions should not match any template."""
        registry = TemplateRegistry()
        assert registry.match(simple_function_element) is None


class TestInitTemplate:
    """Tests for __init__ template (REQ-MP-301)."""

    def test_init_with_params(self, init_element):
        registry = TemplateRegistry()
        body = registry.match(init_element)
        assert body is not None
        assert "self.name = name" in body
        assert "self.value = value" in body

    def test_init_no_params(self):
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="__init__",
            signature=Signature(params=[Param(name="self")]),
            parent_class="Empty",
        )
        registry = TemplateRegistry()
        body = registry.match(elem)
        assert body is not None
        assert body == "pass"

    def test_init_body_is_valid_python(self, init_element):
        registry = TemplateRegistry()
        body = registry.match(init_element)
        # Wrap in function and parse
        code = f"def __init__(self, name, value):\n"
        code += "\n".join(f"    {line}" for line in body.splitlines())
        ast.parse(code)  # Should not raise


class TestReprTemplate:
    """Tests for __repr__ template (REQ-MP-301)."""

    def test_repr_generates_fstring(self, repr_element):
        registry = TemplateRegistry()
        body = registry.match(repr_element)
        assert body is not None
        assert "return" in body
        assert "Config" in body

    def test_repr_is_valid_python(self, repr_element):
        registry = TemplateRegistry()
        body = registry.match(repr_element)
        code = f"def __repr__(self):\n    {body}"
        ast.parse(code)


class TestStrTemplate:
    """Tests for __str__ template (REQ-MP-301)."""

    def test_str_template(self):
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="__str__",
            signature=Signature(params=[Param(name="self")]),
            parent_class="MyModel",
        )
        registry = TemplateRegistry()
        body = registry.match(elem)
        assert body is not None
        assert "return" in body


class TestEqTemplate:
    """Tests for __eq__ template (REQ-MP-301)."""

    def test_eq_template(self):
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="__eq__",
            signature=Signature(
                params=[Param(name="self"), Param(name="other")],
                return_annotation="bool",
            ),
            parent_class="Item",
        )
        registry = TemplateRegistry()
        body = registry.match(elem)
        assert body is not None
        assert "isinstance" in body
        assert "NotImplemented" in body

    def test_eq_is_valid_python(self):
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="__eq__",
            signature=Signature(
                params=[Param(name="self"), Param(name="other")],
            ),
            parent_class="Item",
        )
        registry = TemplateRegistry()
        body = registry.match(elem)
        code = f"def __eq__(self, other):\n"
        code += "\n".join(f"    {line}" for line in body.splitlines())
        ast.parse(code)


class TestHashTemplate:
    """Tests for __hash__ template (REQ-MP-301)."""

    def test_hash_template(self):
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="__hash__",
            signature=Signature(
                params=[Param(name="self")],
                return_annotation="int",
            ),
            parent_class="Item",
        )
        registry = TemplateRegistry()
        body = registry.match(elem)
        assert body is not None
        assert "hash" in body


class TestConstantTemplate:
    """Tests for constant template (REQ-MP-301)."""

    def test_int_constant(self, constant_element):
        registry = TemplateRegistry()
        body = registry.match(constant_element)
        assert body is not None
        assert "DEFAULT_TIMEOUT" in body
        assert "0" in body

    def test_str_constant(self):
        elem = ForwardElementSpec(
            kind=ElementKind.CONSTANT,
            name="APP_NAME",
            signature=Signature(params=[], return_annotation="str"),
        )
        registry = TemplateRegistry()
        body = registry.match(elem)
        assert body is not None
        assert 'APP_NAME = ""' in body

    def test_optional_constant(self):
        elem = ForwardElementSpec(
            kind=ElementKind.CONSTANT,
            name="MAYBE",
            signature=Signature(params=[], return_annotation="Optional[str]"),
        )
        registry = TemplateRegistry()
        body = registry.match(elem)
        assert body is not None
        assert "MAYBE = None" in body

    def test_constant_no_annotation_returns_none(self):
        elem = ForwardElementSpec(
            kind=ElementKind.CONSTANT,
            name="UNKNOWN",
        )
        registry = TemplateRegistry()
        body = registry.match(elem)
        assert body is None


class TestPropertyTemplate:
    """Tests for property template (REQ-MP-301)."""

    def test_property_template(self, property_element):
        registry = TemplateRegistry()
        body = registry.match(property_element)
        assert body is not None
        assert "return self._total" in body

    def test_property_is_valid_python(self, property_element):
        registry = TemplateRegistry()
        body = registry.match(property_element)
        code = f"def total(self):\n    {body}"
        ast.parse(code)


class TestIsTrivial:
    """Tests for TemplateRegistry.is_trivial()."""

    def test_constant_is_trivial(self, constant_element):
        registry = TemplateRegistry()
        assert registry.is_trivial(constant_element) is True

    def test_property_is_trivial(self, property_element):
        registry = TemplateRegistry()
        assert registry.is_trivial(property_element) is True

    def test_init_is_trivial(self, init_element):
        registry = TemplateRegistry()
        assert registry.is_trivial(init_element) is True

    def test_regular_function_not_trivial(self, simple_function_element):
        registry = TemplateRegistry()
        assert registry.is_trivial(simple_function_element) is False

    def test_disabled_never_trivial(self, init_element):
        registry = TemplateRegistry(enabled=False)
        assert registry.is_trivial(init_element) is False


class TestASTValidation:
    """Tests for template AST validation (REQ-MP-304)."""

    def test_valid_template_passes(self, init_element):
        registry = TemplateRegistry()
        body = registry.match(init_element)
        assert body is not None  # Would be None if AST validation failed
