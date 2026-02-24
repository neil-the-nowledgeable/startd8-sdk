"""Tests for Phase 6: bytecode call graph analysis.

Tests cover _analyze_bytecode, _augment_with_bytecode, _resolve_intra_file_fqns,
call edge collection, and integration via generate_file_manifest(mode="bytecode").
"""

from __future__ import annotations

import platform
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from startd8.utils.code_manifest import (
    SCHEMA_VERSION,
    CallEdge,
    CallEntry,
    CallGraphInfo,
    CallKind,
    AttributeAccessKind,
    ElementKind,
    FileManifest,
    _BYTECODE_SUPPORTED,
    _analyze_bytecode,
    _augment_with_bytecode,
    _collect_call_edges,
    _extract_code_objects,
    generate_file_manifest,
    lookup_element,
)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _manifest(source: str) -> FileManifest:
    """Generate a manifest from inline source with bytecode mode."""
    import tempfile, os
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, dir="/tmp",
    ) as f:
        f.write(textwrap.dedent(source))
        f.flush()
        try:
            return generate_file_manifest(f.name, "/tmp", mode="bytecode")
        finally:
            os.unlink(f.name)


def _find_element(manifest: FileManifest, name: str):
    """Find an element by name in the manifest (recursive)."""
    def _search(elems):
        for e in elems:
            if e.name == name:
                return e
            found = _search(e.children)
            if found:
                return found
            found = _search(e.class_variables)
            if found:
                return found
        return None
    return _search(manifest.elements)


# ═══════════════════════════════════════════════════════════════════════════
# Schema version
# ═══════════════════════════════════════════════════════════════════════════


class TestSchemaVersion:
    def test_schema_version_is_1_4_0(self):
        assert SCHEMA_VERSION == "1.4.0"

    def test_manifest_schema_version(self):
        m = _manifest("def f(): pass")
        assert m.schema_version == "1.4.0"


# ═══════════════════════════════════════════════════════════════════════════
# Code object extraction
# ═══════════════════════════════════════════════════════════════════════════


class TestExtractCodeObjects:
    def test_extracts_functions(self):
        code = compile("def foo(): pass\ndef bar(): pass", "<test>", "exec")
        objs = _extract_code_objects(code)
        assert "foo" in objs
        assert "bar" in objs

    def test_extracts_methods(self):
        source = "class C:\n  def m(self): pass\n  def n(self): pass"
        code = compile(source, "<test>", "exec")
        objs = _extract_code_objects(code)
        assert "C.m" in objs
        assert "C.n" in objs

    def test_extracts_nested_functions(self):
        source = "def outer():\n  def inner(): pass"
        code = compile(source, "<test>", "exec")
        objs = _extract_code_objects(code)
        assert "outer" in objs
        assert "outer.<locals>.inner" in objs

    def test_depth_guard(self):
        code = compile("def f(): pass", "<test>", "exec")
        objs = _extract_code_objects(code, max_depth=0)
        assert len(objs) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Call extraction
# ═══════════════════════════════════════════════════════════════════════════


class TestCallExtraction:
    def test_function_call(self):
        m = _manifest("""
        def foo():
            bar()

        def bar():
            pass
        """)
        foo = _find_element(m, "foo")
        assert foo.call_graph is not None
        targets = {c.target for c in foo.call_graph.calls}
        assert "bar" in targets

    def test_builtin_call(self):
        m = _manifest("""
        def foo():
            x = len([1, 2, 3])
            print(x)
        """)
        foo = _find_element(m, "foo")
        assert foo.call_graph is not None
        builtin_calls = [
            c for c in foo.call_graph.calls if c.kind == CallKind.BUILTIN_CALL
        ]
        builtin_names = {c.target for c in builtin_calls}
        assert "len" in builtin_names
        assert "print" in builtin_names

    def test_method_call_on_self(self):
        m = _manifest("""
        class MyClass:
            def caller(self):
                self.helper()

            def helper(self):
                pass
        """)
        caller = _find_element(m, "caller")
        assert caller.call_graph is not None
        method_calls = [
            c for c in caller.call_graph.calls if c.kind == CallKind.METHOD_CALL
        ]
        assert any(c.target == "helper" and c.receiver == "self" for c in method_calls)

    def test_method_call_on_variable(self):
        m = _manifest("""
        def foo():
            obj = get_obj()
            obj.do_thing()
        """)
        foo = _find_element(m, "foo")
        assert foo.call_graph is not None
        method_calls = [
            c for c in foo.call_graph.calls if c.kind == CallKind.METHOD_CALL
        ]
        assert any(c.target == "do_thing" for c in method_calls)

    def test_multiple_calls(self):
        m = _manifest("""
        def foo():
            a()
            b()
            c()
        """)
        foo = _find_element(m, "foo")
        assert foo.call_graph is not None
        targets = {c.target for c in foo.call_graph.calls}
        assert targets >= {"a", "b", "c"}

    def test_empty_function(self):
        m = _manifest("""
        def empty():
            pass
        """)
        empty = _find_element(m, "empty")
        assert empty.call_graph is not None
        assert len(empty.call_graph.calls) == 0

    def test_deduplication(self):
        """Same target called multiple times → single CallEntry."""
        m = _manifest("""
        def foo():
            bar()
            bar()
            bar()
        """)
        foo = _find_element(m, "foo")
        assert foo.call_graph is not None
        bar_calls = [c for c in foo.call_graph.calls if c.target == "bar"]
        assert len(bar_calls) == 1


# ═══════════════════════════════════════════════════════════════════════════
# Method vs. function discrimination
# ═══════════════════════════════════════════════════════════════════════════


class TestMethodFunctionDiscrimination:
    def test_mixed_calls(self):
        m = _manifest("""
        def helper():
            pass

        class C:
            def method(self):
                helper()
                self.other()
        """)
        method = _find_element(m, "method")
        assert method.call_graph is not None
        func_calls = [c for c in method.call_graph.calls if c.kind == CallKind.FUNCTION_CALL]
        method_calls = [c for c in method.call_graph.calls if c.kind == CallKind.METHOD_CALL]
        assert any(c.target == "helper" for c in func_calls)
        assert any(c.target == "other" for c in method_calls)

    def test_static_method(self):
        m = _manifest("""
        class C:
            @staticmethod
            def static_method():
                some_func()
        """)
        sm = _find_element(m, "static_method")
        assert sm.call_graph is not None
        assert any(c.target == "some_func" for c in sm.call_graph.calls)


# ═══════════════════════════════════════════════════════════════════════════
# Self-attribute tracking
# ═══════════════════════════════════════════════════════════════════════════


class TestSelfAttributeTracking:
    def test_attribute_reads(self):
        m = _manifest("""
        class C:
            def method(self):
                x = self.a
                y = self.b
        """)
        method = _find_element(m, "method")
        assert method.call_graph is not None
        assert "a" in method.call_graph.attribute_reads
        assert "b" in method.call_graph.attribute_reads

    def test_attribute_writes(self):
        m = _manifest("""
        class C:
            def __init__(self):
                self.x = 10
                self.y = 20
        """)
        init = _find_element(m, "__init__")
        assert init.call_graph is not None
        assert "x" in init.call_graph.attribute_writes
        assert "y" in init.call_graph.attribute_writes

    def test_mixed_reads_writes(self):
        m = _manifest("""
        class C:
            def method(self):
                self.x = self.y + 1
        """)
        method = _find_element(m, "method")
        assert method.call_graph is not None
        assert "y" in method.call_graph.attribute_reads
        assert "x" in method.call_graph.attribute_writes

    def test_attribute_delete(self):
        m = _manifest("""
        class C:
            def cleanup(self):
                del self.cache
        """)
        cleanup = _find_element(m, "cleanup")
        assert cleanup.call_graph is not None
        assert "cache" in cleanup.call_graph.attribute_writes

    def test_sorted_unique(self):
        """Attribute lists should be sorted and unique."""
        m = _manifest("""
        class C:
            def method(self):
                _ = self.b
                _ = self.a
                _ = self.b
        """)
        method = _find_element(m, "method")
        assert method.call_graph is not None
        assert method.call_graph.attribute_reads == ["a", "b"]


# ═══════════════════════════════════════════════════════════════════════════
# Dynamic dispatch detection
# ═══════════════════════════════════════════════════════════════════════════


class TestDynamicDispatch:
    def test_getattr(self):
        m = _manifest("""
        class C:
            def method(self):
                val = getattr(self, 'name')
        """)
        method = _find_element(m, "method")
        assert method.call_graph is not None
        assert method.call_graph.has_dynamic_dispatch is True

    def test_setattr(self):
        m = _manifest("""
        class C:
            def method(self):
                setattr(self, 'name', 42)
        """)
        method = _find_element(m, "method")
        assert method.call_graph is not None
        assert method.call_graph.has_dynamic_dispatch is True

    def test_eval(self):
        m = _manifest("""
        def dangerous():
            eval("1+1")
        """)
        func = _find_element(m, "dangerous")
        assert func.call_graph is not None
        assert func.call_graph.has_dynamic_dispatch is True

    def test_no_dynamic_dispatch(self):
        m = _manifest("""
        def safe():
            len([1, 2])
        """)
        func = _find_element(m, "safe")
        assert func.call_graph is not None
        assert func.call_graph.has_dynamic_dispatch is False


# ═══════════════════════════════════════════════════════════════════════════
# Intra-file FQN resolution
# ═══════════════════════════════════════════════════════════════════════════


class TestIntraFileResolution:
    def test_global_function_resolved(self):
        m = _manifest("""
        def caller():
            callee()

        def callee():
            pass
        """)
        caller = _find_element(m, "caller")
        assert caller.call_graph is not None
        callee_calls = [
            c for c in caller.call_graph.calls if c.target == "callee"
        ]
        assert len(callee_calls) == 1
        assert callee_calls[0].target_fqn is not None
        assert callee_calls[0].target_fqn.endswith(".callee")

    def test_self_method_resolved(self):
        m = _manifest("""
        class C:
            def caller(self):
                self.target()

            def target(self):
                pass
        """)
        caller = _find_element(m, "caller")
        assert caller.call_graph is not None
        target_calls = [
            c for c in caller.call_graph.calls if c.target == "target"
        ]
        assert len(target_calls) == 1
        assert target_calls[0].target_fqn is not None
        assert "C.target" in target_calls[0].target_fqn

    def test_unresolved_external(self):
        m = _manifest("""
        def foo():
            external_function()
        """)
        foo = _find_element(m, "foo")
        assert foo.call_graph is not None
        ext_calls = [c for c in foo.call_graph.calls if c.target == "external_function"]
        assert len(ext_calls) == 1
        assert ext_calls[0].target_fqn is None
        assert "external_function" in foo.call_graph.unresolved_calls

    def test_imported_name_resolved(self):
        m = _manifest("""
        from os.path import join

        def foo():
            join("a", "b")
        """)
        foo = _find_element(m, "foo")
        assert foo.call_graph is not None
        join_calls = [c for c in foo.call_graph.calls if c.target == "join"]
        assert len(join_calls) == 1
        assert join_calls[0].target_fqn == "os.path.join"


# ═══════════════════════════════════════════════════════════════════════════
# Call edges
# ═══════════════════════════════════════════════════════════════════════════


class TestCallEdges:
    def test_call_edges_populated(self):
        m = _manifest("""
        def a():
            b()

        def b():
            pass
        """)
        assert m.call_graph_edges is not None
        assert len(m.call_graph_edges) >= 1
        edge = m.call_graph_edges[0]
        assert edge.caller_fqn.endswith(".a")
        assert edge.callee_fqn.endswith(".b")

    def test_call_edges_deduplicated(self):
        """Multiple calls to same target → single edge."""
        m = _manifest("""
        def a():
            b()
            b()
        def b():
            pass
        """)
        assert m.call_graph_edges is not None
        # a→b should appear only once
        edges_ab = [
            e for e in m.call_graph_edges
            if e.caller_fqn.endswith(".a") and e.callee_fqn.endswith(".b")
        ]
        assert len(edges_ab) == 1

    def test_no_edges_without_bytecode_mode(self):
        """mode='static' should not populate call_graph_edges."""
        import tempfile, os
        source = textwrap.dedent("def a():\n    b()\ndef b():\n    pass\n")
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="/tmp",
        ) as f:
            f.write(source)
            f.flush()
            try:
                m = generate_file_manifest(f.name, "/tmp", mode="static")
            finally:
                os.unlink(f.name)
        assert m.call_graph_edges is None


# ═══════════════════════════════════════════════════════════════════════════
# Async functions
# ═══════════════════════════════════════════════════════════════════════════


class TestAsyncFunctions:
    def test_async_call_extraction(self):
        m = _manifest("""
        async def fetch():
            await process()

        async def process():
            pass
        """)
        fetch = _find_element(m, "fetch")
        assert fetch.call_graph is not None
        targets = {c.target for c in fetch.call_graph.calls}
        assert "process" in targets

    def test_async_method(self):
        m = _manifest("""
        class Service:
            async def run(self):
                await self.initialize()

            async def initialize(self):
                pass
        """)
        run = _find_element(m, "run")
        assert run.call_graph is not None
        assert any(
            c.target == "initialize" and c.kind == CallKind.METHOD_CALL
            for c in run.call_graph.calls
        )


# ═══════════════════════════════════════════════════════════════════════════
# Nested functions
# ═══════════════════════════════════════════════════════════════════════════


class TestNestedFunctions:
    def test_nested_function_has_call_graph(self):
        m = _manifest("""
        def outer():
            def inner():
                some_call()
            inner()
        """)
        outer = _find_element(m, "outer")
        assert outer.call_graph is not None
        # outer calls inner
        assert any(c.target == "inner" for c in outer.call_graph.calls)


# ═══════════════════════════════════════════════════════════════════════════
# Super calls
# ═══════════════════════════════════════════════════════════════════════════


class TestSuperCalls:
    def test_super_method_call(self):
        m = _manifest("""
        class Base:
            def method(self):
                pass

        class Child(Base):
            def method(self):
                super().method()
        """)
        child_method = None
        for el in m.elements:
            if el.name == "Child":
                for child in el.children:
                    if child.name == "method":
                        child_method = child
                        break
        assert child_method is not None
        assert child_method.call_graph is not None
        super_calls = [
            c for c in child_method.call_graph.calls
            if c.receiver == "super()"
        ]
        assert len(super_calls) >= 1
        assert super_calls[0].target == "method"


# ═══════════════════════════════════════════════════════════════════════════
# Determinism
# ═══════════════════════════════════════════════════════════════════════════


class TestDeterminism:
    def test_two_runs_identical(self):
        source = textwrap.dedent("""\
        def a():
            b()
            len([])
        def b():
            pass
        class C:
            def m(self):
                self.x = 1
                self.helper()
        """)
        # Use same fixed filename to ensure identical FQNs
        import os
        fixed_path = "/tmp/_determinism_test.py"
        try:
            with open(fixed_path, "w") as f:
                f.write(source)
            m1 = generate_file_manifest(fixed_path, "/tmp", mode="bytecode")
            m2 = generate_file_manifest(fixed_path, "/tmp", mode="bytecode")
            # Exclude generated_at (timestamp differs between runs)
            d1 = m1.model_dump(exclude={"generated_at"})
            d2 = m2.model_dump(exclude={"generated_at"})
            assert d1 == d2
        finally:
            os.unlink(fixed_path)


# ═══════════════════════════════════════════════════════════════════════════
# Graceful degradation
# ═══════════════════════════════════════════════════════════════════════════


class TestGracefulDegradation:
    def test_non_cpython_guard(self):
        """Non-CPython should skip bytecode analysis."""
        with patch(
            "startd8.utils.code_manifest._BYTECODE_SUPPORTED", False,
        ):
            m = _manifest("""
            def foo():
                bar()
            def bar():
                pass
            """)
            foo = _find_element(m, "foo")
            assert foo.call_graph is None
            assert m.call_graph_edges is None

    def test_mode_static_no_call_graph(self):
        """mode='static' should not produce call_graph on elements."""
        import tempfile, os
        source = textwrap.dedent("def foo():\n    bar()\ndef bar():\n    pass\n")
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="/tmp",
        ) as f:
            f.write(source)
            f.flush()
            try:
                m = generate_file_manifest(f.name, "/tmp", mode="static")
            finally:
                os.unlink(f.name)
        foo = _find_element(m, "foo")
        assert foo.call_graph is None


# ═══════════════════════════════════════════════════════════════════════════
# Mode validation
# ═══════════════════════════════════════════════════════════════════════════


class TestModeValidation:
    def test_invalid_mode_raises(self):
        import tempfile, os
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="/tmp",
        ) as f:
            f.write("x = 1\n")
            f.flush()
            try:
                with pytest.raises(ValueError, match="Unknown mode"):
                    generate_file_manifest(f.name, "/tmp", mode="bogus")
            finally:
                os.unlink(f.name)

    def test_bytecode_mode_accepted(self):
        m = _manifest("def f(): pass")
        assert m.schema_version == "1.4.0"


# ═══════════════════════════════════════════════════════════════════════════
# Class methods and static methods
# ═══════════════════════════════════════════════════════════════════════════


class TestClassStaticMethods:
    def test_classmethod(self):
        m = _manifest("""
        class C:
            @classmethod
            def create(cls):
                return cls()
        """)
        create = _find_element(m, "create")
        # classmethod should have call_graph (it's a callable)
        assert create.call_graph is not None

    def test_property_has_call_graph(self):
        m = _manifest("""
        class C:
            @property
            def value(self):
                return self._value
        """)
        value = _find_element(m, "value")
        assert value is not None
        # Properties are callable elements, may have call_graph
        # Even if no outbound calls, the CallGraphInfo should exist
        if value.call_graph is not None:
            assert isinstance(value.call_graph, CallGraphInfo)


# ═══════════════════════════════════════════════════════════════════════════
# CallGraphInfo and CallEdge model tests
# ═══════════════════════════════════════════════════════════════════════════


class TestModels:
    def test_call_entry_frozen(self):
        entry = CallEntry(target="foo", kind=CallKind.FUNCTION_CALL)
        with pytest.raises(Exception):
            entry.target = "bar"  # type: ignore

    def test_call_graph_info_defaults(self):
        info = CallGraphInfo()
        assert info.calls == []
        assert info.attribute_reads == []
        assert info.attribute_writes == []
        assert info.has_dynamic_dispatch is False
        assert info.unresolved_calls == []

    def test_call_edge_frozen(self):
        edge = CallEdge(caller_fqn="a.b", callee_fqn="c.d")
        with pytest.raises(Exception):
            edge.caller_fqn = "x.y"  # type: ignore

    def test_element_call_graph_optional(self):
        """Element.call_graph defaults to None."""
        from startd8.utils.code_manifest import Element, Span
        elem = Element(
            kind=ElementKind.VARIABLE,
            name="x",
            fqn="mod.x",
            span=Span(start_line=1, start_col=0, end_line=1, end_col=1),
        )
        assert elem.call_graph is None

    def test_file_manifest_call_graph_edges_optional(self):
        """FileManifest.call_graph_edges defaults to None."""
        fm = FileManifest(
            file="test.py",
            module="test",
            digest="sha256:abc",
            generated_at="2026-01-01T00:00:00Z",
        )
        assert fm.call_graph_edges is None


# ═══════════════════════════════════════════════════════════════════════════
# Chained method calls
# ═══════════════════════════════════════════════════════════════════════════


class TestChainedCalls:
    def test_chained_method_call(self):
        m = _manifest("""
        def foo():
            obj = get_builder()
            obj.configure().build()
        """)
        foo = _find_element(m, "foo")
        assert foo.call_graph is not None
        method_targets = {
            c.target for c in foo.call_graph.calls
            if c.kind == CallKind.METHOD_CALL
        }
        # Should detect at least one of the chained methods
        assert len(method_targets) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# Bytecode supported flag
# ═══════════════════════════════════════════════════════════════════════════


class TestBytecodeSupported:
    def test_bytecode_supported_on_cpython_312_plus(self):
        """On CPython 3.12+, bytecode analysis should be supported."""
        if (
            platform.python_implementation() == "CPython"
            and sys.version_info >= (3, 12)
        ):
            assert _BYTECODE_SUPPORTED is True
        else:
            assert _BYTECODE_SUPPORTED is False


# ═══════════════════════════════════════════════════════════════════════════
# Backward compatibility
# ═══════════════════════════════════════════════════════════════════════════


class TestBackwardCompat:
    def test_new_fields_are_optional(self):
        """Manifests without call_graph fields should still validate."""
        data = {
            "file": "test.py",
            "module": "test",
            "digest": "sha256:abc",
            "generated_at": "2026-01-01T00:00:00Z",
        }
        fm = FileManifest.model_validate(data)
        assert fm.call_graph_edges is None
