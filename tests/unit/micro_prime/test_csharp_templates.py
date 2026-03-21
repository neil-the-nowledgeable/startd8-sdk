"""Tests for C# MicroPrime templates."""

from startd8.forward_manifest import ForwardElementSpec, ForwardFileSpec, InterfaceContract
from startd8.micro_prime.templates import CSHARP_TEMPLATES
from startd8.utils.code_manifest import ElementKind, Param, ParamKind, Signature


_EMPTY_SIG = Signature(params=[], return_annotation=None)


def _elem(name, kind=ElementKind.METHOD, parent_class=None, sig=None):
    effective_sig = sig
    if effective_sig is None and kind in (
        ElementKind.METHOD, ElementKind.FUNCTION,
        ElementKind.ASYNC_METHOD, ElementKind.ASYNC_FUNCTION,
        ElementKind.PROPERTY,
    ):
        effective_sig = _EMPTY_SIG
    return ForwardElementSpec(
        kind=kind,
        name=name,
        signature=effective_sig,
        parent_class=parent_class,
    )


def _file():
    return ForwardFileSpec(file="Test.cs", elements=[], imports=[])


def _match(name, elem):
    for t in CSHARP_TEMPLATES:
        if t.name == name:
            return t.match_fn(elem, _file(), [])
    raise ValueError(f"Template {name} not found")


def _render(name, elem):
    for t in CSHARP_TEMPLATES:
        if t.name == name:
            return t.render_fn(elem, _file(), [])
    raise ValueError(f"Template {name} not found")


class TestCSharpProperty:
    def test_matches_property(self):
        elem = _elem("Name", kind=ElementKind.PROPERTY)
        assert _match("csharp_property", elem) is True

    def test_no_match_method(self):
        elem = _elem("GetName")
        assert _match("csharp_property", elem) is False

    def test_render(self):
        elem = _elem("Name", kind=ElementKind.PROPERTY)
        assert _render("csharp_property", elem) == "get; set;"


class TestCSharpConstructor:
    def test_matches_constructor(self):
        sig = Signature(params=[
            Param(name="name", kind=ParamKind.POSITIONAL, annotation="string"),
        ])
        elem = _elem("CartService", parent_class="CartService", sig=sig)
        assert _match("csharp_constructor", elem) is True

    def test_no_match_different_name(self):
        elem = _elem("Process", parent_class="CartService")
        assert _match("csharp_constructor", elem) is False

    def test_render_field_assignments(self):
        sig = Signature(params=[
            Param(name="store", kind=ParamKind.POSITIONAL, annotation="ICartStore"),
        ])
        elem = _elem("CartService", parent_class="CartService", sig=sig)
        body = _render("csharp_constructor", elem)
        assert body is not None
        assert "_store = store" in body


class TestCSharpEquals:
    def test_matches(self):
        elem = _elem("Equals", parent_class="CartItem")
        assert _match("csharp_equals", elem) is True

    def test_render(self):
        elem = _elem("Equals", parent_class="CartItem")
        body = _render("csharp_equals", elem)
        assert body is not None
        assert "ReferenceEquals" in body
        assert "CartItem" in body


class TestCSharpGetHashCode:
    def test_matches(self):
        elem = _elem("GetHashCode")
        assert _match("csharp_gethashcode", elem) is True

    def test_render(self):
        elem = _elem("GetHashCode")
        body = _render("csharp_gethashcode", elem)
        assert body == "return HashCode.Combine();"


class TestCSharpToString:
    def test_matches(self):
        elem = _elem("ToString", parent_class="CartItem")
        assert _match("csharp_tostring", elem) is True

    def test_render(self):
        elem = _elem("ToString", parent_class="CartItem")
        body = _render("csharp_tostring", elem)
        assert body is not None
        assert "CartItem" in body


class TestCSharpDispose:
    def test_matches(self):
        elem = _elem("Dispose")
        assert _match("csharp_dispose", elem) is True

    def test_render(self):
        elem = _elem("Dispose")
        body = _render("csharp_dispose", elem)
        assert body is not None
        assert "SuppressFinalize" in body


class TestCSharpAsyncMethod:
    def test_matches_async_suffix(self):
        elem = _elem("GetCartAsync")
        assert _match("csharp_async_method", elem) is True

    def test_no_match_sync(self):
        elem = _elem("GetCart")
        assert _match("csharp_async_method", elem) is False

    def test_render(self):
        elem = _elem("GetCartAsync")
        body = _render("csharp_async_method", elem)
        assert body is not None
        assert "await" in body


class TestCSharpDIConstructor:
    def test_matches_interface_params(self):
        sig = Signature(params=[
            Param(name="store", kind=ParamKind.POSITIONAL, annotation="ICartStore"),
            Param(name="logger", kind=ParamKind.POSITIONAL, annotation="ILogger"),
        ])
        elem = _elem("CartService", parent_class="CartService", sig=sig)
        assert _match("csharp_di_constructor", elem) is True

    def test_no_match_no_interfaces(self):
        sig = Signature(params=[
            Param(name="name", kind=ParamKind.POSITIONAL, annotation="string"),
        ])
        elem = _elem("CartService", parent_class="CartService", sig=sig)
        assert _match("csharp_di_constructor", elem) is False

    def test_render_null_guard(self):
        sig = Signature(params=[
            Param(name="store", kind=ParamKind.POSITIONAL, annotation="ICartStore"),
        ])
        elem = _elem("CartService", parent_class="CartService", sig=sig)
        body = _render("csharp_di_constructor", elem)
        assert body is not None
        assert "ArgumentNullException" in body
        assert "_store" in body


class TestTemplateRegistration:
    def test_eight_templates_registered(self):
        assert len(CSHARP_TEMPLATES) == 8

    def test_all_names_unique(self):
        names = [t.name for t in CSHARP_TEMPLATES]
        assert len(names) == len(set(names))

    def test_all_start_with_csharp(self):
        for t in CSHARP_TEMPLATES:
            assert t.name.startswith("csharp_"), f"{t.name} doesn't start with csharp_"
