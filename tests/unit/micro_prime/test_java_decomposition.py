"""Tests for Java decomposition strategy (Phase 4)."""

import pytest
from startd8.micro_prime.decomposer import (
    JavaClassDecomposeStrategy,
    ModerateDecomposer,
    _JAVA_RESERVED,
    _LANGUAGE_RESERVED,
)
from startd8.micro_prime.models import MicroPrimeConfig
from startd8.forward_manifest import ForwardElementSpec, ForwardFileSpec, ForwardManifest
from startd8.utils.code_manifest import ElementKind, Param, Signature


_EMPTY_SIG = Signature(params=[], return_annotation=None)


def _elem(name, kind=ElementKind.METHOD, parent_class=None, sig=None, decorators=None, bases=None, docstring_hint=None):
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
        docstring_hint=docstring_hint,
    )


def _file_spec(elements):
    return ForwardFileSpec(file="MyClass.java", elements=elements, imports=[])


def _manifest(files):
    return ForwardManifest(files=files)


class TestJavaClassDecomposeStrategy:

    def _strategy(self, config=None):
        return JavaClassDecomposeStrategy(config=config or MicroPrimeConfig())

    def test_can_handle_class_with_methods(self):
        cls = _elem("UserService", kind=ElementKind.CLASS)
        methods = [
            _elem("findById", parent_class="UserService"),
            _elem("save", parent_class="UserService"),
            _elem("delete", parent_class="UserService"),
        ]
        fs = _file_spec([cls] + methods)
        manifest = _manifest([fs])
        assert self._strategy().can_handle(cls, fs, manifest, "multiple_methods")

    def test_cannot_handle_too_few_methods(self):
        cls = _elem("Simple", kind=ElementKind.CLASS)
        methods = [_elem("doWork", parent_class="Simple")]
        fs = _file_spec([cls] + methods)
        manifest = _manifest([fs])
        assert not self._strategy().can_handle(cls, fs, manifest, "")

    def test_cannot_handle_non_class(self):
        func = _elem("myFunc", kind=ElementKind.FUNCTION)
        fs = _file_spec([func])
        manifest = _manifest([fs])
        assert not self._strategy().can_handle(func, fs, manifest, "")

    def test_rejects_annotation_processor(self):
        cls = _elem("MyProcessor", kind=ElementKind.CLASS, decorators=["Retention"])
        methods = [
            _elem("m1", parent_class="MyProcessor"),
            _elem("m2", parent_class="MyProcessor"),
            _elem("m3", parent_class="MyProcessor"),
        ]
        fs = _file_spec([cls] + methods)
        manifest = _manifest([fs])
        assert not self._strategy().can_handle(cls, fs, manifest, "")

    def test_plan_produces_sub_elements(self):
        cls = _elem("OrderService", kind=ElementKind.CLASS)
        methods = [
            _elem("createOrder", parent_class="OrderService"),
            _elem("cancelOrder", parent_class="OrderService"),
            _elem("getOrder", parent_class="OrderService"),
        ]
        fs = _file_spec([cls] + methods)
        manifest = _manifest([fs])
        strategy = self._strategy()
        plan = strategy.plan(cls, fs, manifest, "")
        assert plan is not None
        assert len(plan.sub_elements) >= 4  # shell + 3 methods
        assert plan.sub_elements[0].kind == "class_shell"
        assert plan.strategy == "java_class_decompose"

    def test_assembly_order(self):
        cls = _elem("Svc", kind=ElementKind.CLASS)
        methods = [
            _elem("a", parent_class="Svc"),
            _elem("b", parent_class="Svc"),
            _elem("c", parent_class="Svc"),
        ]
        fs = _file_spec([cls] + methods)
        manifest = _manifest([fs])
        plan = self._strategy().plan(cls, fs, manifest, "")
        assert plan is not None
        orders = [s.assembly_order for s in plan.sub_elements]
        assert orders == sorted(orders)

    def test_assemble(self):
        cls = _elem("Svc", kind=ElementKind.CLASS)
        methods = [
            _elem("a", parent_class="Svc"),
            _elem("b", parent_class="Svc"),
            _elem("c", parent_class="Svc"),
        ]
        fs = _file_spec([cls] + methods)
        manifest = _manifest([fs])
        plan = self._strategy().plan(cls, fs, manifest, "")
        sub_results = {
            "class_shell": "pass",
            "a": "return 1;",
            "b": "return 2;",
            "c": "return 3;",
        }
        assembled = self._strategy().assemble(plan, sub_results, "")
        assert assembled is not None
        assert "return 1;" in assembled


class TestJavaReservedInDecomposer:
    def test_java_reserved_in_language_map(self):
        assert "java" in _LANGUAGE_RESERVED
        assert "class" in _LANGUAGE_RESERVED["java"]

    def test_java_reserved_set_exists(self):
        assert len(_JAVA_RESERVED) > 50


class TestModerateDecomposerJava:
    def test_java_language_id_uses_java_strategy(self):
        decomposer = ModerateDecomposer(language_id="java")
        strategy_names = [s.name for s in decomposer._strategies]
        assert "java_class_decompose" in strategy_names

    def test_python_default_no_java_strategy(self):
        decomposer = ModerateDecomposer(language_id="python")
        strategy_names = [s.name for s in decomposer._strategies]
        assert "java_class_decompose" not in strategy_names
        assert "class_decompose" in strategy_names
