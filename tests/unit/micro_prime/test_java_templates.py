"""Tests for Java templates (Phase 4)."""

import pytest
from startd8.micro_prime.templates import (
    JAVA_TEMPLATES,
    TemplateRegistry,
    _java_getter_match,
    _java_getter_render,
    _java_setter_match,
    _java_setter_render,
    _java_constructor_match,
    _java_constructor_render,
    _java_equals_match,
    _java_equals_render,
    _java_hashcode_match,
    _java_hashcode_render,
    _java_tostring_match,
    _java_tostring_render,
    _java_builder_match,
    _java_spring_main_match,
    _is_java_safe_identifier,
)
from startd8.forward_manifest import ForwardElementSpec, ForwardFileSpec, InterfaceContract
from startd8.utils.code_manifest import ElementKind, Param, Signature


_EMPTY_SIG = Signature(params=[], return_annotation=None)


def _elem(name, kind=ElementKind.METHOD, parent_class=None, sig=None, decorators=None, bases=None):
    # ForwardElementSpec requires a signature for method/function kinds
    effective_sig = sig
    if effective_sig is None and kind in (
        ElementKind.METHOD, ElementKind.FUNCTION,
        ElementKind.ASYNC_METHOD, ElementKind.ASYNC_FUNCTION,
    ):
        effective_sig = _EMPTY_SIG
    return ForwardElementSpec(
        kind=kind,
        name=name,
        signature=effective_sig,
        parent_class=parent_class,
        decorators=decorators or [],
        bases=bases or [],
    )


def _file_spec():
    return ForwardFileSpec(file="Test.java", elements=[], imports=[])


def _contracts():
    return []


class TestJavaGetterTemplate:
    def test_match_getName(self):
        elem = _elem("getName")
        assert _java_getter_match(elem, _file_spec(), _contracts())

    def test_match_isEnabled(self):
        elem = _elem("isEnabled")
        assert _java_getter_match(elem, _file_spec(), _contracts())

    def test_no_match_doWork(self):
        elem = _elem("doWork")
        assert not _java_getter_match(elem, _file_spec(), _contracts())

    def test_render_getName(self):
        elem = _elem("getName")
        result = _java_getter_render(elem, _file_spec(), _contracts())
        assert result == "return this.name;"

    def test_render_isActive(self):
        elem = _elem("isActive")
        result = _java_getter_render(elem, _file_spec(), _contracts())
        assert result == "return this.active;"


class TestJavaSetterTemplate:
    def test_match_setName(self):
        elem = _elem("setName")
        assert _java_setter_match(elem, _file_spec(), _contracts())

    def test_no_match_get(self):
        elem = _elem("getName")
        assert not _java_setter_match(elem, _file_spec(), _contracts())

    def test_render_setName(self):
        elem = _elem("setName", sig=Signature(
            params=[Param(name="name", annotation="String")],
        ))
        result = _java_setter_render(elem, _file_spec(), _contracts())
        assert result == "this.name = name;"


class TestJavaConstructorTemplate:
    def test_match(self):
        elem = _elem("MyClass", parent_class="MyClass")
        assert _java_constructor_match(elem, _file_spec(), _contracts())

    def test_no_match(self):
        elem = _elem("doWork", parent_class="MyClass")
        assert not _java_constructor_match(elem, _file_spec(), _contracts())

    def test_render(self):
        elem = _elem("MyClass", parent_class="MyClass", sig=Signature(
            params=[
                Param(name="name", annotation="String"),
                Param(name="age", annotation="int"),
            ],
        ))
        result = _java_constructor_render(elem, _file_spec(), _contracts())
        assert "this.name = name;" in result
        assert "this.age = age;" in result


class TestJavaEqualsTemplate:
    def test_match(self):
        elem = _elem("equals")
        assert _java_equals_match(elem, _file_spec(), _contracts())

    def test_render(self):
        elem = _elem("equals", parent_class="User")
        result = _java_equals_render(elem, _file_spec(), _contracts())
        assert "Objects.equals" in result
        assert "User" in result


class TestJavaHashCodeTemplate:
    def test_match(self):
        elem = _elem("hashCode")
        assert _java_hashcode_match(elem, _file_spec(), _contracts())

    def test_render(self):
        result = _java_hashcode_render(_elem("hashCode"), _file_spec(), _contracts())
        assert "Objects.hash" in result


class TestJavaToStringTemplate:
    def test_match(self):
        assert _java_tostring_match(_elem("toString"), _file_spec(), _contracts())

    def test_render(self):
        result = _java_tostring_render(_elem("toString", parent_class="User"), _file_spec(), _contracts())
        assert "User" in result


class TestJavaBuilderTemplate:
    def test_match(self):
        elem = _elem("builder", parent_class="User")
        assert _java_builder_match(elem, _file_spec(), _contracts())

    def test_no_match_without_parent(self):
        elem = _elem("builder")
        assert not _java_builder_match(elem, _file_spec(), _contracts())


class TestJavaSpringMainTemplate:
    def test_match(self):
        elem = _elem("main")
        assert _java_spring_main_match(elem, _file_spec(), _contracts())


class TestIsJavaSafeIdentifier:
    def test_valid(self):
        assert _is_java_safe_identifier("myField")

    def test_keyword_rejected(self):
        assert not _is_java_safe_identifier("class")
        assert not _is_java_safe_identifier("void")

    def test_non_string_rejected(self):
        assert not _is_java_safe_identifier(123)


class TestJavaTemplateRegistry:
    def test_java_registry_uses_java_templates(self):
        reg = TemplateRegistry(language_id="java")
        templates = reg._active_templates()
        names = {t.name for t in templates}
        assert "java_getter" in names
        assert "java_setter" in names

    def test_python_registry_no_java_templates(self):
        reg = TemplateRegistry(language_id="python")
        templates = reg._active_templates()
        names = {t.name for t in templates}
        assert "java_getter" not in names

    def test_no_false_positive_for_python(self):
        """Java getter template should not match Python elements."""
        reg = TemplateRegistry(language_id="java")
        elem = _elem("do_work")
        match = reg.match(elem, _file_spec())
        assert match is None or match.name != "java_getter"
