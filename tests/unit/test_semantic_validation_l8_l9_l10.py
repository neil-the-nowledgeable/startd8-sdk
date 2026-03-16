"""Tests for L8 (service identity), L9 (method resolution), L10 (reachability)."""

import ast
import pytest

from startd8.forward_manifest_validator import (
    _validate_service_identity,
    _validate_method_resolution,
    _validate_reachability,
)


# ---------------------------------------------------------------------------
# L8: Service Identity Mismatch (REQ-SV2-400)
# ---------------------------------------------------------------------------


class TestServiceIdentity:
    def test_correct_service_name_passes(self):
        code = "import logging\nlogger = logging.getLogger('recommendationservice-server')\n"
        tree = ast.parse(code)
        issues = _validate_service_identity(
            tree, "src/recommendationservice/logger.py",
            sibling_files=["src/emailservice/logger.py"],
        )
        assert len(issues) == 0

    def test_wrong_service_name_in_call_flagged(self):
        code = "import logging\nlogger = logging.getLogger('emailservice-server')\n"
        tree = ast.parse(code)
        issues = _validate_service_identity(
            tree, "src/recommendationservice/logger.py",
            sibling_files=["src/emailservice/logger.py"],
        )
        assert len(issues) == 1
        assert issues[0]["category"] == "service_identity_mismatch"
        assert issues[0]["severity"] == "error"
        assert "emailservice" in issues[0]["symbol"]

    def test_wrong_service_name_in_default_param_flagged(self):
        code = "def get_logger(name='emailservice'):\n    pass\n"
        tree = ast.parse(code)
        issues = _validate_service_identity(
            tree, "src/recommendationservice/logger.py",
            sibling_files=["src/emailservice/logger.py"],
        )
        assert len(issues) == 1
        assert issues[0]["category"] == "service_identity_mismatch"
        assert "emailservice" in issues[0]["symbol"]

    def test_wrong_component_keyword_flagged(self):
        code = "class Fmt:\n    def __init__(self, component='emailservice'):\n        pass\n"
        tree = ast.parse(code)
        issues = _validate_service_identity(
            tree, "src/recommendationservice/logger.py",
            sibling_files=["src/emailservice/logger.py"],
        )
        assert len(issues) == 1
        assert "component" in issues[0]["message"]

    def test_no_siblings_skips_check(self):
        code = "import logging\nlogger = logging.getLogger('emailservice')\n"
        tree = ast.parse(code)
        issues = _validate_service_identity(
            tree, "src/recommendationservice/logger.py",
            sibling_files=None,
        )
        assert len(issues) == 0

    def test_no_sibling_services_skips_check(self):
        code = "import logging\nlogger = logging.getLogger('emailservice')\n"
        tree = ast.parse(code)
        # Only siblings in same service dir — no other service to compare
        issues = _validate_service_identity(
            tree, "src/recommendationservice/logger.py",
            sibling_files=["src/recommendationservice/server.py"],
        )
        assert len(issues) == 0

    def test_generic_name_not_flagged(self):
        code = "import logging\nlogger = logging.getLogger('myapp')\n"
        tree = ast.parse(code)
        issues = _validate_service_identity(
            tree, "src/recommendationservice/logger.py",
            sibling_files=["src/emailservice/logger.py"],
        )
        assert len(issues) == 0

    def test_getjsonlogger_flagged(self):
        code = "def getJSONLogger(name='emailservice'):\n    pass\n"
        tree = ast.parse(code)
        issues = _validate_service_identity(
            tree, "src/recommendationservice/logger.py",
            sibling_files=["src/emailservice/logger.py"],
        )
        assert len(issues) == 1

    def test_correct_service_in_default_passes(self):
        code = "def get_logger(name='recommendationservice'):\n    pass\n"
        tree = ast.parse(code)
        issues = _validate_service_identity(
            tree, "src/recommendationservice/logger.py",
            sibling_files=["src/emailservice/logger.py"],
        )
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# L9: Method Resolution (REQ-SV2-500)
# ---------------------------------------------------------------------------


class TestMethodResolution:
    def test_self_dot_module_func_flagged(self):
        code = (
            "def index(l):\n    l.client.get('/')\n\n"
            "class UserBehavior:\n"
            "    def on_start(self):\n"
            "        self.index()\n"
        )
        tree = ast.parse(code)
        issues = _validate_method_resolution(tree)
        assert len(issues) == 1
        assert issues[0]["category"] == "method_resolution"
        assert issues[0]["severity"] == "warning"
        assert issues[0]["symbol"] == "index"
        assert "UserBehavior" in issues[0]["message"]

    def test_self_dot_real_method_passes(self):
        code = (
            "def index(l):\n    pass\n\n"
            "class UserBehavior:\n"
            "    def index(self):\n        pass\n"
            "    def on_start(self):\n"
            "        self.index()\n"
        )
        tree = ast.parse(code)
        issues = _validate_method_resolution(tree)
        assert len(issues) == 0

    def test_module_func_called_normally_passes(self):
        code = (
            "def index(l):\n    pass\n\n"
            "class UserBehavior:\n"
            "    def on_start(self):\n"
            "        index(self)\n"
        )
        tree = ast.parse(code)
        issues = _validate_method_resolution(tree)
        assert len(issues) == 0

    def test_no_classes_passes(self):
        code = "def foo():\n    pass\ndef bar():\n    foo()\n"
        tree = ast.parse(code)
        issues = _validate_method_resolution(tree)
        assert len(issues) == 0

    def test_no_module_funcs_passes(self):
        code = (
            "class Foo:\n"
            "    def bar(self):\n        self.baz()\n"
            "    def baz(self):\n        pass\n"
        )
        tree = ast.parse(code)
        issues = _validate_method_resolution(tree)
        assert len(issues) == 0

    def test_multiple_classes_independent(self):
        code = (
            "def helper():\n    pass\n\n"
            "class A:\n"
            "    def helper(self):\n        pass\n"
            "    def run(self):\n        self.helper()\n\n"
            "class B:\n"
            "    def run(self):\n        self.helper()\n"
        )
        tree = ast.parse(code)
        issues = _validate_method_resolution(tree)
        # Class A has helper as a method — no issue
        # Class B does NOT have helper as a method — flagged
        assert len(issues) == 1
        assert "B" in issues[0]["message"]


# ---------------------------------------------------------------------------
# L10: Reachability (REQ-SV2-600)
# ---------------------------------------------------------------------------


class TestReachability:
    def test_uncalled_function_flagged(self):
        code = "def foo():\n    pass\n\ndef bar():\n    pass\n"
        tree = ast.parse(code)
        issues = _validate_reachability(tree)
        assert len(issues) == 2
        symbols = {i["symbol"] for i in issues}
        assert symbols == {"foo", "bar"}

    def test_called_function_passes(self):
        code = "def foo():\n    pass\n\nfoo()\n"
        tree = ast.parse(code)
        issues = _validate_reachability(tree)
        assert len(issues) == 0

    def test_dict_value_reference_passes(self):
        code = "def foo():\n    pass\n\ntasks = {foo: 1}\n"
        tree = ast.parse(code)
        issues = _validate_reachability(tree)
        assert len(issues) == 0

    def test_list_reference_passes(self):
        code = "def foo():\n    pass\n\ntasks = [foo]\n"
        tree = ast.parse(code)
        issues = _validate_reachability(tree)
        assert len(issues) == 0

    def test_private_function_not_flagged(self):
        code = "def _helper():\n    pass\n"
        tree = ast.parse(code)
        issues = _validate_reachability(tree)
        assert len(issues) == 0

    def test_main_not_flagged(self):
        code = "def main():\n    pass\n"
        tree = ast.parse(code)
        issues = _validate_reachability(tree)
        assert len(issues) == 0

    def test_all_export_not_flagged(self):
        code = 'def foo():\n    pass\n\n__all__ = ["foo"]\n'
        tree = ast.parse(code)
        issues = _validate_reachability(tree)
        assert len(issues) == 0

    def test_class_methods_not_flagged(self):
        code = "class Foo:\n    def bar(self):\n        pass\n"
        tree = ast.parse(code)
        issues = _validate_reachability(tree)
        # bar is a class method, not module-level
        assert len(issues) == 0

    def test_severity_is_warning(self):
        code = "def orphan():\n    pass\n"
        tree = ast.parse(code)
        issues = _validate_reachability(tree)
        assert len(issues) == 1
        assert issues[0]["severity"] == "warning"
        assert issues[0]["category"] == "unreachable_function"

    def test_decorator_reference_passes(self):
        code = (
            "def my_decorator(f):\n    return f\n\n"
            "@my_decorator\n"
            "def decorated():\n    pass\n"
        )
        tree = ast.parse(code)
        issues = _validate_reachability(tree)
        # my_decorator is referenced as decorator → Name(Load)
        # decorated is defined but never called → flagged
        assert len(issues) == 1
        assert issues[0]["symbol"] == "decorated"
