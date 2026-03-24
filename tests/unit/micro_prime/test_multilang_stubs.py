"""Tests for language-aware element stub and import rendering — REQ-MP-1211a/b.

Verifies that _build_element_stub() and _render_imports() produce
language-native syntax for Go, Java, C#, and Node.js elements.
"""

import pytest

from startd8.micro_prime.prompt_builder import (
    _build_element_stub,
    _render_imports,
    _render_sibling_stubs,
)
from startd8.forward_manifest import (
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardImportSpec,
)
from startd8.utils.code_manifest import ElementKind, Param, Signature
from startd8.languages.registry import LanguageRegistry


@pytest.fixture(autouse=True, scope="module")
def discover():
    LanguageRegistry.discover()


def _sig(params=None, ret=None):
    return Signature(
        params=[Param(name=n, annotation=a) for n, a in (params or [])],
        return_annotation=ret,
    )


def _elem(name="doWork", kind=ElementKind.FUNCTION, sig=None, parent=None,
           is_static=False, is_abstract=False):
    return ForwardElementSpec(
        name=name, kind=kind,
        signature=sig or _sig(),
        parent_class=parent,
        is_static=is_static,
        is_abstract=is_abstract,
    )


# ---------------------------------------------------------------------------
# Go stubs (REQ-MP-1211a)
# ---------------------------------------------------------------------------

class TestGoStubRendering:
    def _profile(self):
        return LanguageRegistry.get("go")

    def test_func_keyword(self):
        stub = _build_element_stub(_elem(), self._profile())
        assert "func " in stub
        assert "def " not in stub

    def test_params_go_style(self):
        """Go params: name Type (no colon)."""
        elem = _elem(sig=_sig([("ctx", "context.Context"), ("id", "string")]))
        stub = _build_element_stub(elem, self._profile())
        assert "ctx context.Context" in stub
        assert "ctx: context.Context" not in stub

    def test_return_after_params(self):
        """Go return type: after ) before {."""
        elem = _elem(sig=_sig(ret="error"))
        stub = _build_element_stub(elem, self._profile())
        assert ") error {" in stub
        assert "-> error" not in stub

    def test_panic_stub_body(self):
        stub = _build_element_stub(_elem(), self._profile())
        assert 'panic("not implemented")' in stub
        assert "raise NotImplementedError" not in stub

    def test_method_with_receiver(self):
        elem = _elem(name="Handle", kind=ElementKind.METHOD, parent="Server")
        stub = _build_element_stub(elem, self._profile())
        assert "(s *Server)" in stub
        assert "func (s *Server) Handle" in stub

    def test_struct(self):
        elem = _elem(name="CartItem", kind=ElementKind.CLASS)
        stub = _build_element_stub(elem, self._profile())
        assert "type CartItem struct" in stub


# ---------------------------------------------------------------------------
# Java stubs
# ---------------------------------------------------------------------------

class TestJavaStubRendering:
    def _profile(self):
        return LanguageRegistry.get("java")

    def test_public_keyword(self):
        elem = _elem(sig=_sig(ret="void"))
        stub = _build_element_stub(elem, self._profile())
        assert "public" in stub
        assert "def " not in stub

    def test_return_before_name(self):
        """Java: public ReturnType name(...)."""
        elem = _elem(name="calculate", sig=_sig(ret="int"))
        stub = _build_element_stub(elem, self._profile())
        assert "public int calculate" in stub

    def test_params_type_first(self):
        """Java: Type name (not name: Type)."""
        elem = _elem(sig=_sig([("x", "String"), ("y", "int")]))
        stub = _build_element_stub(elem, self._profile())
        assert "String x" in stub
        assert "x: String" not in stub


# ---------------------------------------------------------------------------
# C# stubs
# ---------------------------------------------------------------------------

class TestCSharpStubRendering:
    def _profile(self):
        return LanguageRegistry.get("csharp")

    def test_public_keyword(self):
        elem = _elem(sig=_sig(ret="void"))
        stub = _build_element_stub(elem, self._profile())
        assert "public" in stub

    def test_async_task(self):
        """C# async methods return Task."""
        elem = _elem(kind=ElementKind.ASYNC_FUNCTION, sig=_sig(ret="void"))
        stub = _build_element_stub(elem, self._profile())
        assert "async" in stub
        assert "Task" in stub

    def test_throws_not_implemented(self):
        stub = _build_element_stub(_elem(), self._profile())
        assert "NotImplementedException" in stub


# ---------------------------------------------------------------------------
# Node.js stubs
# ---------------------------------------------------------------------------

class TestNodeStubRendering:
    def _profile(self):
        return LanguageRegistry.get("nodejs")

    def test_function_keyword(self):
        stub = _build_element_stub(_elem(), self._profile())
        assert "function " in stub
        assert "def " not in stub

    def test_throws_error(self):
        stub = _build_element_stub(_elem(), self._profile())
        assert 'throw new Error("not implemented")' in stub

    def test_async_function(self):
        elem = _elem(kind=ElementKind.ASYNC_FUNCTION)
        stub = _build_element_stub(elem, self._profile())
        assert "async function" in stub


# ---------------------------------------------------------------------------
# Python regression
# ---------------------------------------------------------------------------

class TestPythonStubUnchanged:
    def _profile(self):
        return LanguageRegistry.get("python")

    def test_def_keyword(self):
        stub = _build_element_stub(_elem(), self._profile())
        assert "def doWork" in stub

    def test_raise_not_implemented(self):
        stub = _build_element_stub(_elem(), self._profile())
        assert "raise NotImplementedError" in stub

    def test_none_profile_defaults_python(self):
        stub = _build_element_stub(_elem(), None)
        assert "def doWork" in stub
        assert "raise NotImplementedError" in stub


# ---------------------------------------------------------------------------
# Import rendering (REQ-MP-1211b)
# ---------------------------------------------------------------------------

def _file_spec_with_imports():
    return ForwardFileSpec(
        file="src/main.go",
        elements=[],
        imports=[
            ForwardImportSpec(kind="import", module="fmt"),
            ForwardImportSpec(kind="from", module="net/http", names=["Handler", "Server"]),
        ],
    )


class TestGoImportRendering:
    def test_quoted_paths(self):
        lines = _render_imports(_file_spec_with_imports(), LanguageRegistry.get("go"))
        assert any('"fmt"' in line for line in lines)

    def test_no_python_from(self):
        lines = _render_imports(_file_spec_with_imports(), LanguageRegistry.get("go"))
        assert not any("from " in line for line in lines)


class TestJavaImportRendering:
    def test_semicolon(self):
        lines = _render_imports(_file_spec_with_imports(), LanguageRegistry.get("java"))
        assert all(line.endswith(";") for line in lines)


class TestCSharpImportRendering:
    def test_using_keyword(self):
        lines = _render_imports(_file_spec_with_imports(), LanguageRegistry.get("csharp"))
        assert all("using " in line for line in lines)


class TestNodeImportRendering:
    def test_esm_syntax(self):
        lines = _render_imports(_file_spec_with_imports(), LanguageRegistry.get("nodejs"))
        assert any("from '" in line for line in lines)


class TestPythonImportUnchanged:
    def test_python_from_import(self):
        lines = _render_imports(_file_spec_with_imports(), LanguageRegistry.get("python"))
        assert any("from " in line and "import " in line for line in lines)

    def test_none_profile_defaults_python(self):
        lines = _render_imports(_file_spec_with_imports(), None)
        assert any("import fmt" in line for line in lines)
