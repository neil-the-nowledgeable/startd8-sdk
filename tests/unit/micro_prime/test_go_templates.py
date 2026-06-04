"""Tests for Go MicroPrime templates."""

from startd8.forward_manifest import ForwardElementSpec, ForwardFileSpec, InterfaceContract
from startd8.micro_prime.templates import GO_TEMPLATES
from startd8.utils.code_manifest import ElementKind, Param, ParamKind, Signature


_EMPTY_SIG = Signature(params=[], return_annotation=None)


def _elem(name, kind=ElementKind.METHOD, parent_class=None, sig=None):
    effective_sig = sig
    if effective_sig is None and kind in (
        ElementKind.METHOD, ElementKind.FUNCTION,
        ElementKind.ASYNC_METHOD, ElementKind.ASYNC_FUNCTION,
    ):
        effective_sig = _EMPTY_SIG
    return ForwardElementSpec(
        kind=kind, name=name, signature=effective_sig, parent_class=parent_class,
    )


def _file():
    return ForwardFileSpec(file="main.go", elements=[], imports=[])


def _match(name, elem):
    for t in GO_TEMPLATES:
        if t.name == name:
            return t.match_fn(elem, _file(), [])
    raise ValueError(f"Template {name} not found")


def _render(name, elem):
    for t in GO_TEMPLATES:
        if t.name == name:
            return t.render_fn(elem, _file(), [])
    raise ValueError(f"Template {name} not found")


class TestGoConstructor:
    def test_matches_new_prefix(self):
        assert _match("go_constructor", _elem("NewCartStore")) is True

    def test_no_match_lowercase(self):
        assert _match("go_constructor", _elem("newcart")) is False

    def test_render_empty(self):
        body = _render("go_constructor", _elem("NewCartStore"))
        assert body is not None
        assert "CartStore{}" in body

    def test_render_with_params(self):
        sig = Signature(params=[
            Param(name="addr", kind=ParamKind.POSITIONAL, annotation="string"),
        ])
        body = _render("go_constructor", _elem("NewServer", sig=sig))
        assert body is not None
        assert "addr: addr" in body


class TestGoStringer:
    def test_matches(self):
        assert _match("go_stringer", _elem("String", parent_class="CartStore")) is True

    def test_render(self):
        body = _render("go_stringer", _elem("String", parent_class="CartStore"))
        assert body is not None
        assert "CartStore" in body


class TestGoError:
    def test_matches(self):
        assert _match("go_error", _elem("Error")) is True

    def test_render(self):
        body = _render("go_error", _elem("Error"))
        assert body is not None
        assert "Sprintf" in body


class TestGoClose:
    def test_matches(self):
        assert _match("go_close", _elem("Close")) is True

    def test_render(self):
        assert _render("go_close", _elem("Close")) == "return nil"


class TestGoGetter:
    def test_matches(self):
        assert _match("go_getter", _elem("GetName")) is True

    def test_no_match_short(self):
        assert _match("go_getter", _elem("Get")) is False

    def test_render(self):
        body = _render("go_getter", _elem("GetName"))
        assert body == "return s.name"


class TestGoSetter:
    def test_matches(self):
        assert _match("go_setter", _elem("SetName")) is True

    def test_render(self):
        body = _render("go_setter", _elem("SetName"))
        assert body is not None
        assert "s.name = name" in body


class TestGoMain:
    def test_matches(self):
        assert _match("go_main", _elem("main")) is True

    def test_no_match_other(self):
        assert _match("go_main", _elem("init")) is False

    def test_render(self):
        body = _render("go_main", _elem("main"))
        assert body is not None
        assert "log" in body


class TestGoTemplateRegistration:
    def test_ten_templates(self):
        # Tripwire on the registered Go template count (was 7; grew to 10 with
        # go_main / go_test_func / go_http_handler / go_grpc_method).
        assert len(GO_TEMPLATES) == 10

    def test_all_names_unique(self):
        names = [t.name for t in GO_TEMPLATES]
        assert len(names) == len(set(names))

    def test_all_start_with_go(self):
        for t in GO_TEMPLATES:
            assert t.name.startswith("go_"), f"{t.name} doesn't start with go_"
