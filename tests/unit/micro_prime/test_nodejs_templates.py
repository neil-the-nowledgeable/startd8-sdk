"""Tests for Node.js MicroPrime templates."""

from startd8.forward_manifest import ForwardElementSpec, ForwardFileSpec, InterfaceContract
from startd8.micro_prime.templates import NODEJS_TEMPLATES
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
    return ForwardFileSpec(file="app.js", elements=[], imports=[])


def _match(name, elem):
    for t in NODEJS_TEMPLATES:
        if t.name == name:
            return t.match_fn(elem, _file(), [])
    raise ValueError(f"Template {name} not found")


def _render(name, elem):
    for t in NODEJS_TEMPLATES:
        if t.name == name:
            return t.render_fn(elem, _file(), [])
    raise ValueError(f"Template {name} not found")


class TestJsConstructor:
    def test_matches(self):
        sig = Signature(params=[
            Param(name="store", kind=ParamKind.POSITIONAL),
        ])
        elem = _elem("constructor", parent_class="CartService", sig=sig)
        assert _match("js_constructor", elem) is True

    def test_no_match_without_parent(self):
        elem = _elem("constructor")
        assert _match("js_constructor", elem) is False

    def test_render(self):
        sig = Signature(params=[
            Param(name="store", kind=ParamKind.POSITIONAL),
            Param(name="logger", kind=ParamKind.POSITIONAL),
        ])
        elem = _elem("constructor", parent_class="CartService", sig=sig)
        body = _render("js_constructor", elem)
        assert body is not None
        assert "this.store = store" in body
        assert "this.logger = logger" in body


class TestJsToString:
    def test_matches(self):
        assert _match("js_tostring", _elem("toString", parent_class="Cart")) is True

    def test_render(self):
        body = _render("js_tostring", _elem("toString", parent_class="Cart"))
        assert body is not None
        assert "Cart" in body


class TestJsGetter:
    def test_matches(self):
        assert _match("js_getter", _elem("getName")) is True

    def test_no_match(self):
        assert _match("js_getter", _elem("process")) is False

    def test_render(self):
        body = _render("js_getter", _elem("getName"))
        assert body == "return this.name;"


class TestJsSetter:
    def test_matches(self):
        assert _match("js_setter", _elem("setName")) is True

    def test_render(self):
        body = _render("js_setter", _elem("setName"))
        assert body is not None
        assert "this.name = name" in body


class TestJsAsyncMethod:
    def test_matches_async_kind(self):
        elem = _elem("fetchData", kind=ElementKind.ASYNC_FUNCTION)
        assert _match("js_async_method", elem) is True

    def test_matches_async_suffix(self):
        elem = _elem("getCartAsync")
        assert _match("js_async_method", elem) is True

    def test_no_match_sync(self):
        elem = _elem("getCart")
        assert _match("js_async_method", elem) is False

    def test_render(self):
        body = _render("js_async_method", _elem("fetchDataAsync"))
        assert body is not None
        assert "Error" in body


class TestJsExpressHandler:
    def test_matches_get(self):
        assert _match("js_express_handler", _elem("get")) is True

    def test_matches_post(self):
        assert _match("js_express_handler", _elem("post")) is True

    def test_matches_handler(self):
        assert _match("js_express_handler", _elem("handler")) is True

    def test_no_match_other(self):
        assert _match("js_express_handler", _elem("process")) is False

    def test_render(self):
        body = _render("js_express_handler", _elem("get"))
        assert body is not None
        assert "200" in body
        assert "json" in body


class TestNodejsTemplateRegistration:
    def test_six_templates(self):
        assert len(NODEJS_TEMPLATES) == 6

    def test_all_names_unique(self):
        names = [t.name for t in NODEJS_TEMPLATES]
        assert len(names) == len(set(names))

    def test_all_start_with_js(self):
        for t in NODEJS_TEMPLATES:
            assert t.name.startswith("js_"), f"{t.name} doesn't start with js_"


class TestNodejsMicroPrimeEnabled:
    def test_flag_is_true(self):
        from startd8.micro_prime.engine import NODEJS_MICROPRIME_ENABLED
        assert NODEJS_MICROPRIME_ENABLED is True

    def test_js_not_bypassed(self):
        from startd8.micro_prime.engine import _is_non_python_file
        assert _is_non_python_file("app.js") is False
        assert _is_non_python_file("server.ts") is False
        assert _is_non_python_file("component.tsx") is False

    def test_decomposer_has_nodejs(self):
        from startd8.micro_prime.decomposer import _LANGUAGE_RESERVED
        assert "nodejs" in _LANGUAGE_RESERVED
