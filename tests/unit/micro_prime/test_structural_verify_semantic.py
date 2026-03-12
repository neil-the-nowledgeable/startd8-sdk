"""Tests for semantic validation in _structural_verify (Kaizen run-042 P0).

These tests cover the four new semantic checks added to catch defects that
AST parsing and lint alone miss:
1. pass-only function body rejection
2. Missing self/cls on methods
3. Class body bare-expression rejection
4. Factory function return check
"""

from __future__ import annotations

import pytest

from startd8.forward_manifest import ForwardElementSpec
from startd8.micro_prime.structural_verify import (
    check_class_body_statements as _check_class_body_statements,
    structural_verify as _structural_verify,
)
from startd8.utils.code_manifest import ElementKind, Param, Signature


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def method_element() -> ForwardElementSpec:
    """A method element with self and return annotation."""
    return ForwardElementSpec(
        kind=ElementKind.METHOD,
        name="send_email",
        signature=Signature(
            params=[Param(name="self"), Param(name="address", annotation="str")],
            return_annotation="bool",
        ),
        parent_class="EmailService",
    )


@pytest.fixture
def static_method_element() -> ForwardElementSpec:
    """A @staticmethod element — no self/cls required."""
    return ForwardElementSpec(
        kind=ElementKind.METHOD,
        name="validate",
        signature=Signature(
            params=[Param(name="data", annotation="dict")],
            return_annotation="bool",
        ),
        parent_class="EmailService",
        is_static=True,
    )


@pytest.fixture
def classmethod_element() -> ForwardElementSpec:
    """A @classmethod element — expects cls as first param."""
    return ForwardElementSpec(
        kind=ElementKind.METHOD,
        name="from_config",
        signature=Signature(
            params=[Param(name="cls"), Param(name="path", annotation="str")],
            return_annotation="EmailService",
        ),
        parent_class="EmailService",
        is_classmethod=True,
    )


@pytest.fixture
def function_element() -> ForwardElementSpec:
    """A standalone function (not a method)."""
    return ForwardElementSpec(
        kind=ElementKind.FUNCTION,
        name="process_data",
        signature=Signature(
            params=[Param(name="data", annotation="list")],
            return_annotation="dict",
        ),
    )


@pytest.fixture
def factory_function_element() -> ForwardElementSpec:
    """A factory function that should return a value."""
    return ForwardElementSpec(
        kind=ElementKind.FUNCTION,
        name="create_app",
        signature=Signature(
            params=[],
            return_annotation="Flask",
        ),
    )


@pytest.fixture
def class_element() -> ForwardElementSpec:
    """A class element."""
    return ForwardElementSpec(
        kind=ElementKind.CLASS,
        name="EmailService",
        bases=["BaseService"],
    )


# ── 1. Pass-only body rejection ────────────────────────────────────────


class TestPassOnlyBodyRejection:
    """Verify pass-only function bodies are rejected (Grade F files)."""

    def test_pass_only_body_rejected(self, method_element):
        """Single pass statement should fail — matches email_client.py Grade F."""
        code = "def send_email(self, address: str) -> bool:\n    pass"
        ok, reason = _structural_verify(code, method_element)
        assert ok is False
        # Rejected by either return-annotation check or pass-only check
        assert "missing return" in reason or "pass-only stub" in reason

    def test_pass_with_docstring_rejected(self, method_element):
        """Docstring + pass is still a stub."""
        code = (
            'def send_email(self, address: str) -> bool:\n'
            '    """Send an email."""\n'
            '    pass'
        )
        ok, reason = _structural_verify(code, method_element)
        assert ok is False
        assert "missing return" in reason or "pass-only stub" in reason

    def test_pass_with_real_code_accepted(self, method_element):
        """pass + actual code should pass (defensive pattern)."""
        code = (
            "def send_email(self, address: str) -> bool:\n"
            "    if not address:\n"
            "        pass\n"
            "    return True"
        )
        ok, reason = _structural_verify(code, method_element)
        assert ok is True

    def test_pass_only_no_return_annotation_rejected(self):
        """pass-only body without return annotation hits the pass-only check directly."""
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="send_confirmation_email",
            signature=Signature(
                params=[Param(name="email"), Param(name="order")],
            ),
        )
        code = "def send_confirmation_email(email, order):\n    pass"
        ok, reason = _structural_verify(code, elem)
        assert ok is False
        assert "pass-only stub" in reason

    def test_real_body_accepted(self, method_element):
        """Normal method body passes."""
        code = "def send_email(self, address: str) -> bool:\n    return True"
        ok, reason = _structural_verify(code, method_element)
        assert ok is True


# ── 2. Missing self/cls parameter ──────────────────────────────────────


class TestMissingSelfParameter:
    """Verify methods without self/cls are rejected (email_server.py Grade D)."""

    def test_method_missing_self_rejected(self, method_element):
        """Method without self should fail — matches email_server.py send_email()."""
        code = (
            "def send_email(client, email_address, content):\n"
            "    return True"
        )
        ok, reason = _structural_verify(code, method_element)
        assert ok is False
        assert "self" in reason

    def test_method_with_self_accepted(self, method_element):
        """Normal method with self passes."""
        code = "def send_email(self, address: str) -> bool:\n    return True"
        ok, reason = _structural_verify(code, method_element)
        assert ok is True

    def test_staticmethod_no_self_accepted(self, static_method_element):
        """@staticmethod should not require self."""
        code = "def validate(data: dict) -> bool:\n    return bool(data)"
        ok, reason = _structural_verify(code, static_method_element)
        assert ok is True

    def test_classmethod_missing_cls_rejected(self, classmethod_element):
        """@classmethod without cls should fail."""
        code = (
            "def from_config(path: str) -> EmailService:\n"
            "    return EmailService()"
        )
        ok, reason = _structural_verify(code, classmethod_element)
        assert ok is False
        assert "cls" in reason

    def test_classmethod_with_cls_accepted(self, classmethod_element):
        """@classmethod with cls passes."""
        code = (
            "def from_config(cls, path: str) -> EmailService:\n"
            "    return cls()"
        )
        ok, reason = _structural_verify(code, classmethod_element)
        assert ok is True

    def test_standalone_function_no_self_check(self, function_element):
        """Standalone functions should not require self/cls."""
        code = "def process_data(data: list) -> dict:\n    return {}"
        ok, reason = _structural_verify(code, function_element)
        assert ok is True


# ── 3. Class body bare-expression rejection ────────────────────────────


class TestClassBodyStatements:
    """Verify class body validation catches splicer assembly defects."""

    def test_bare_print_at_class_level_rejected(self, class_element):
        """print() at class body level — matches email_server.py line 20."""
        code = (
            "class EmailService(BaseService):\n"
            '    print(f"Starting service")\n'
            "    def __init__(self):\n"
            "        pass"
        )
        ok, reason = _structural_verify(code, class_element)
        assert ok is False
        assert "bare expression" in reason

    def test_bare_function_call_rejected(self, class_element):
        """Bare function call at class body level."""
        code = (
            "class EmailService(BaseService):\n"
            "    logging.info('init')\n"
            "    def serve(self):\n"
            "        return True"
        )
        ok, reason = _structural_verify(code, class_element)
        assert ok is False
        assert "bare expression" in reason

    def test_return_at_class_level_rejected(self, class_element):
        """return at class body level — splicer assembly error."""
        code = (
            "class EmailService(BaseService):\n"
            "    return None\n"
            "    def serve(self):\n"
            "        return True"
        )
        ok, reason = _structural_verify(code, class_element)
        assert ok is False
        assert "return statement at class body level" in reason

    def test_valid_class_body_accepted(self, class_element):
        """Normal class body with methods and class variables."""
        code = (
            "class EmailService(BaseService):\n"
            '    """An email service."""\n'
            "    DEFAULT_PORT = 587\n"
            "    def __init__(self):\n"
            "        self.port = self.DEFAULT_PORT\n"
            "    def serve(self):\n"
            "        return True"
        )
        ok, reason = _structural_verify(code, class_element)
        assert ok is True

    def test_class_with_assignments_accepted(self, class_element):
        """Class variables (assignments) are valid at class level."""
        code = (
            "class EmailService(BaseService):\n"
            "    port: int = 587\n"
            "    host: str = 'localhost'"
        )
        ok, reason = _structural_verify(code, class_element)
        assert ok is True

    def test_class_shell_pass_accepted(self, class_element):
        """Class shell with only pass is accepted (existing behavior)."""
        ok, reason = _structural_verify("pass", class_element)
        assert ok is True


# ── 4. Factory function return check ───────────────────────────────────


class TestFactoryReturnCheck:
    """Verify factory functions must return a value (shoppingassistantservice.py Grade C)."""

    def test_factory_no_return_rejected(self, factory_function_element):
        """create_app() that doesn't return — matches shoppingassistantservice.py."""
        code = (
            "def create_app() -> Flask:\n"
            "    app = Flask(__name__)\n"
            "    app.config['KEY'] = 'value'"
        )
        ok, reason = _structural_verify(code, factory_function_element)
        assert ok is False
        # Caught by either existing return-annotation check or factory check
        assert "missing return" in reason or "factory" in reason

    def test_factory_returns_none_not_caught(self, factory_function_element):
        """return None with a non-None annotation passes — AST node is not None.

        This is a known limitation: ``return None`` produces
        ``ast.Return(value=ast.Constant(value=None))`` where ``n.value is not
        None`` is True.  Return-type validation would be a separate P1 check.
        """
        code = (
            "def create_app() -> Flask:\n"
            "    app = Flask(__name__)\n"
            "    return None"
        )
        ok, _reason = _structural_verify(code, factory_function_element)
        # Known gap: return None passes current checks
        assert ok is True

    def test_factory_with_return_accepted(self, factory_function_element):
        """create_app() that returns the app passes."""
        code = (
            "def create_app() -> Flask:\n"
            "    app = Flask(__name__)\n"
            "    return app"
        )
        ok, reason = _structural_verify(code, factory_function_element)
        assert ok is True

    def test_non_factory_no_return_check(self, function_element):
        """Non-factory functions use the existing return annotation check."""
        # process_data has return annotation -> dict, handled by existing logic
        code = "def process_data(data: list) -> dict:\n    return {}"
        ok, reason = _structural_verify(code, function_element)
        assert ok is True

    def test_factory_with_none_return_annotation_accepted(self):
        """Factory with -> None should not be checked."""
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="create_context",
            signature=Signature(params=[], return_annotation="None"),
        )
        code = "def create_context() -> None:\n    setup_globals()"
        ok, reason = _structural_verify(code, elem)
        assert ok is True


# ── 5. _check_class_body_statements unit tests ────────────────────────


class TestCheckClassBodyStatements:
    """Direct unit tests for the _check_class_body_statements helper."""

    def _parse_class(self, code: str):
        import ast
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                return node
        raise ValueError("No class found")

    def test_methods_only(self):
        code = "class A:\n    def m(self):\n        return 1"
        assert _check_class_body_statements(self._parse_class(code)) is None

    def test_bare_print(self):
        code = "class A:\n    print('hello')"
        result = _check_class_body_statements(self._parse_class(code))
        assert result is not None
        assert "bare expression" in result

    def test_docstring_accepted(self):
        code = 'class A:\n    """Docstring."""\n    x = 1'
        assert _check_class_body_statements(self._parse_class(code)) is None

    def test_return_rejected(self):
        code = "class A:\n    return None"
        result = _check_class_body_statements(self._parse_class(code))
        assert result is not None
        assert "return" in result

    def test_if_statement_accepted(self):
        """Conditional class body (e.g., platform checks) is valid."""
        code = (
            "class A:\n"
            "    import sys\n"
            "    if sys.platform == 'win32':\n"
            "        _impl = 'win'\n"
            "    else:\n"
            "        _impl = 'posix'"
        )
        assert _check_class_body_statements(self._parse_class(code)) is None

    def test_try_except_accepted(self):
        """Try/except at class level (optional import pattern) is valid."""
        code = (
            "class A:\n"
            "    try:\n"
            "        import fast_impl as _impl\n"
            "    except ImportError:\n"
            "        import slow_impl as _impl"
        )
        assert _check_class_body_statements(self._parse_class(code)) is None


# ── 6. Regression: existing valid code still passes ────────────────────


class TestExistingBehaviorPreserved:
    """Ensure existing passing tests still work with new checks."""

    def test_simple_method_still_passes(self):
        """Exact code from TestStructuralVerify.test_valid_function."""
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="get_name",
            signature=Signature(
                params=[Param(name="self"), Param(name="key", annotation="str")],
                return_annotation="str",
            ),
            parent_class="MyClass",
        )
        code = "def get_name(self, key: str) -> str:\n    return key"
        ok, reason = _structural_verify(code, elem)
        assert ok is True

    def test_constant_still_passes(self):
        """Constants should be unaffected by new checks."""
        elem = ForwardElementSpec(
            kind=ElementKind.CONSTANT,
            name="DEFAULT_TIMEOUT",
            signature=Signature(params=[], return_annotation="int"),
        )
        code = "DEFAULT_TIMEOUT = 30"
        ok, reason = _structural_verify(code, elem)
        assert ok is True

    def test_method_body_only_still_passes(self):
        """Body-only code (no def line) should still work via wrapping."""
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="helper",
            parent_class="MyClass",
            signature=Signature(params=[Param(name="self")]),
        )
        code = "    return 1"
        ok, reason = _structural_verify(code, elem)
        assert ok is True
