"""Tests for skeleton_spec_extractor — REQ-MP-1104."""

import pytest

from startd8.micro_prime.skeleton_spec_extractor import extract_skeleton_specs
from startd8.utils.code_manifest import ElementKind, ParamKind


class TestStubDetection:
    """Functions with raise NotImplementedError produce specs; real bodies do not."""

    def test_function_with_raise_not_implemented(self):
        source = "def do_work(x: int) -> str:\n    raise NotImplementedError\n"
        specs = extract_skeleton_specs(source, "pkg/module.py")
        assert len(specs) == 1
        spec = specs[0]
        assert spec.name == "do_work"
        assert spec.kind == ElementKind.FUNCTION
        assert spec.source_contract_id == "flcm-skel-pkg/module.py:1:do_work"
        assert spec.parent_class is None

    def test_function_with_raise_not_implemented_call(self):
        source = 'def do_work():\n    raise NotImplementedError("todo")\n'
        specs = extract_skeleton_specs(source, "mod.py")
        assert len(specs) == 1
        assert specs[0].name == "do_work"

    def test_function_with_docstring_and_raise(self):
        source = (
            'def do_work():\n'
            '    """Docstring."""\n'
            '    raise NotImplementedError\n'
        )
        specs = extract_skeleton_specs(source, "mod.py")
        assert len(specs) == 1

    def test_function_with_real_body_no_spec(self):
        source = "def do_work():\n    return 42\n"
        specs = extract_skeleton_specs(source, "mod.py")
        assert len(specs) == 0

    def test_function_with_multiple_statements_no_spec(self):
        source = (
            "def do_work():\n"
            "    x = 1\n"
            "    raise NotImplementedError\n"
        )
        specs = extract_skeleton_specs(source, "mod.py")
        assert len(specs) == 0

    def test_function_with_pass_no_spec(self):
        source = "def do_work():\n    pass\n"
        specs = extract_skeleton_specs(source, "mod.py")
        assert len(specs) == 0

    def test_bare_raise_no_spec(self):
        """raise without an exception type is not a stub marker."""
        source = "def do_work():\n    raise\n"
        specs = extract_skeleton_specs(source, "mod.py")
        assert len(specs) == 0


class TestClassMethods:
    """Stub methods inside classes produce specs with parent_class set."""

    def test_class_with_stub_methods(self):
        source = (
            "class MyService:\n"
            "    def fetch(self, url: str) -> bytes:\n"
            "        raise NotImplementedError\n"
            "\n"
            "    def parse(self, data: bytes) -> dict:\n"
            "        raise NotImplementedError\n"
        )
        specs = extract_skeleton_specs(source, "svc.py")
        assert len(specs) == 2
        assert all(s.parent_class == "MyService" for s in specs)
        assert all(s.kind == ElementKind.METHOD for s in specs)
        names = {s.name for s in specs}
        assert names == {"fetch", "parse"}

    def test_class_with_mixed_methods(self):
        """Only stub methods produce specs; implemented methods are skipped."""
        source = (
            "class MyService:\n"
            "    def implemented(self):\n"
            "        return 42\n"
            "\n"
            "    def stub(self):\n"
            "        raise NotImplementedError\n"
        )
        specs = extract_skeleton_specs(source, "svc.py")
        assert len(specs) == 1
        assert specs[0].name == "stub"

    def test_parent_class_set_correctly(self):
        source = (
            "class Alpha:\n"
            "    def method_a(self):\n"
            "        raise NotImplementedError\n"
            "\n"
            "class Beta:\n"
            "    def method_b(self):\n"
            "        raise NotImplementedError\n"
        )
        specs = extract_skeleton_specs(source, "mod.py")
        assert len(specs) == 2
        by_name = {s.name: s for s in specs}
        assert by_name["method_a"].parent_class == "Alpha"
        assert by_name["method_b"].parent_class == "Beta"


class TestAsyncFunctions:
    """Async stub functions/methods get the correct kind."""

    def test_async_function(self):
        source = "async def fetch_data(url: str) -> bytes:\n    raise NotImplementedError\n"
        specs = extract_skeleton_specs(source, "mod.py")
        assert len(specs) == 1
        assert specs[0].kind == ElementKind.ASYNC_FUNCTION

    def test_async_method(self):
        source = (
            "class Client:\n"
            "    async def connect(self):\n"
            "        raise NotImplementedError\n"
        )
        specs = extract_skeleton_specs(source, "mod.py")
        assert len(specs) == 1
        assert specs[0].kind == ElementKind.ASYNC_METHOD
        assert specs[0].parent_class == "Client"


class TestSignatureExtraction:
    """Signatures are correctly extracted from AST."""

    def test_simple_params(self):
        source = "def add(a: int, b: int) -> int:\n    raise NotImplementedError\n"
        specs = extract_skeleton_specs(source, "mod.py")
        sig = specs[0].signature
        assert sig is not None
        assert len(sig.params) == 2
        assert sig.params[0].name == "a"
        assert sig.params[0].annotation == "int"
        assert sig.params[1].name == "b"
        assert sig.return_annotation == "int"

    def test_no_annotations(self):
        source = "def work(x, y):\n    raise NotImplementedError\n"
        specs = extract_skeleton_specs(source, "mod.py")
        sig = specs[0].signature
        assert sig.params[0].annotation is None
        assert sig.return_annotation is None

    def test_default_values(self):
        source = "def work(x: int = 5):\n    raise NotImplementedError\n"
        specs = extract_skeleton_specs(source, "mod.py")
        sig = specs[0].signature
        assert sig.params[0].default == "5"

    def test_kwargs_and_args(self):
        source = "def work(*args, **kwargs):\n    raise NotImplementedError\n"
        specs = extract_skeleton_specs(source, "mod.py")
        sig = specs[0].signature
        assert len(sig.params) == 2
        assert sig.params[0].kind == ParamKind.VAR_POSITIONAL
        assert sig.params[0].name == "args"
        assert sig.params[1].kind == ParamKind.VAR_KEYWORD
        assert sig.params[1].name == "kwargs"

    def test_keyword_only_params(self):
        source = "def work(*, key: str):\n    raise NotImplementedError\n"
        specs = extract_skeleton_specs(source, "mod.py")
        sig = specs[0].signature
        assert len(sig.params) == 1
        assert sig.params[0].kind == ParamKind.KEYWORD_ONLY
        assert sig.params[0].name == "key"

    def test_self_param_included(self):
        """Methods include 'self' as a positional param."""
        source = (
            "class Svc:\n"
            "    def run(self, x: int) -> None:\n"
            "        raise NotImplementedError\n"
        )
        specs = extract_skeleton_specs(source, "mod.py")
        sig = specs[0].signature
        assert sig.params[0].name == "self"
        assert sig.params[1].name == "x"


class TestDecorators:
    """Decorator detection for staticmethod, classmethod, abstractmethod."""

    def test_staticmethod(self):
        source = (
            "class Svc:\n"
            "    @staticmethod\n"
            "    def create() -> 'Svc':\n"
            "        raise NotImplementedError\n"
        )
        specs = extract_skeleton_specs(source, "mod.py")
        assert specs[0].is_static is True
        assert "staticmethod" in specs[0].decorators

    def test_classmethod(self):
        source = (
            "class Svc:\n"
            "    @classmethod\n"
            "    def from_config(cls) -> 'Svc':\n"
            "        raise NotImplementedError\n"
        )
        specs = extract_skeleton_specs(source, "mod.py")
        assert specs[0].is_classmethod is True

    def test_abstractmethod(self):
        source = (
            "import abc\n"
            "class Base:\n"
            "    @abc.abstractmethod\n"
            "    def do(self):\n"
            "        raise NotImplementedError\n"
        )
        specs = extract_skeleton_specs(source, "mod.py")
        assert specs[0].is_abstract is True


class TestEdgeCases:
    """Empty files, syntax errors, and other edge cases."""

    def test_empty_file(self):
        specs = extract_skeleton_specs("", "mod.py")
        assert specs == []

    def test_whitespace_only(self):
        specs = extract_skeleton_specs("   \n\n  ", "mod.py")
        assert specs == []

    def test_syntax_error(self):
        specs = extract_skeleton_specs("def broken(\n", "mod.py")
        assert specs == []

    def test_no_stubs(self):
        source = (
            "def implemented():\n"
            "    return 42\n"
            "\n"
            "class Foo:\n"
            "    def bar(self):\n"
            "        return 'hello'\n"
        )
        specs = extract_skeleton_specs(source, "mod.py")
        assert specs == []

    def test_id_format(self):
        source = "def work():\n    raise NotImplementedError\n"
        specs = extract_skeleton_specs(source, "src/pkg/service.py")
        assert specs[0].source_contract_id == "flcm-skel-src/pkg/service.py:1:work"

    def test_multiple_top_level_functions(self):
        source = (
            "def a():\n    raise NotImplementedError\n\n"
            "def b():\n    return 1\n\n"
            "def c():\n    raise NotImplementedError\n"
        )
        specs = extract_skeleton_specs(source, "mod.py")
        assert len(specs) == 2
        assert {s.name for s in specs} == {"a", "c"}
