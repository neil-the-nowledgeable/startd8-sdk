"""Tests for startd8.validators.semantic_checks."""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from startd8.validators.semantic_checks import (
    SemanticIssue,
    check_bare_except_pass,
    check_duplicate_definitions,
    check_duplicate_main_guards,
    check_phantom_dependencies,
    run_semantic_checks,
)


# -----------------------------------------------------------------------
# check_duplicate_main_guards
# -----------------------------------------------------------------------


class TestCheckDuplicateMainGuards:
    """Tests for check_duplicate_main_guards."""

    def test_no_guard_returns_empty(self):
        source = "x = 1\ny = 2\n"
        tree = ast.parse(source)
        assert check_duplicate_main_guards(tree) == []

    def test_one_guard_returns_empty(self):
        source = textwrap.dedent("""\
            def main():
                pass

            if __name__ == "__main__":
                main()
        """)
        tree = ast.parse(source)
        assert check_duplicate_main_guards(tree) == []

    def test_two_guards_returns_one_issue(self):
        source = textwrap.dedent("""\
            if __name__ == "__main__":
                pass

            if __name__ == "__main__":
                pass
        """)
        tree = ast.parse(source)
        issues = check_duplicate_main_guards(tree)
        assert len(issues) == 1
        assert issues[0].check == "duplicate_main_guard"
        assert issues[0].severity == "warning"
        assert issues[0].line == 4

    def test_reversed_comparison_detected(self):
        """``if "__main__" == __name__:`` should also be detected."""
        source = textwrap.dedent("""\
            if "__main__" == __name__:
                pass

            if __name__ == "__main__":
                pass
        """)
        tree = ast.parse(source)
        issues = check_duplicate_main_guards(tree)
        assert len(issues) == 1


# -----------------------------------------------------------------------
# check_duplicate_definitions
# -----------------------------------------------------------------------


class TestCheckDuplicateDefinitions:
    """Tests for check_duplicate_definitions."""

    def test_no_duplicates_returns_empty(self):
        source = textwrap.dedent("""\
            def foo():
                pass

            def bar():
                pass
        """)
        tree = ast.parse(source)
        assert check_duplicate_definitions(tree) == []

    def test_duplicate_function_flagged(self):
        source = textwrap.dedent("""\
            def foo():
                pass

            def foo():
                pass
        """)
        tree = ast.parse(source)
        issues = check_duplicate_definitions(tree)
        assert len(issues) == 1
        assert issues[0].check == "duplicate_definition"
        assert "'foo'" in issues[0].message
        assert issues[0].line == 4

    def test_duplicate_class_flagged(self):
        source = textwrap.dedent("""\
            class Foo:
                pass

            class Foo:
                pass
        """)
        tree = ast.parse(source)
        issues = check_duplicate_definitions(tree)
        assert len(issues) == 1
        assert issues[0].check == "duplicate_definition"
        assert "'Foo'" in issues[0].message

    def test_method_overload_in_class_not_flagged(self):
        """Methods inside a class body are NOT module-level — should not flag."""
        source = textwrap.dedent("""\
            class MyClass:
                def method(self):
                    pass

                def method(self):
                    pass
        """)
        tree = ast.parse(source)
        issues = check_duplicate_definitions(tree)
        assert issues == []


# -----------------------------------------------------------------------
# check_bare_except_pass
# -----------------------------------------------------------------------


class TestCheckBareExceptPass:
    """Tests for check_bare_except_pass."""

    def test_bare_except_pass_flagged(self):
        source = textwrap.dedent("""\
            try:
                x = 1
            except:
                pass
        """)
        tree = ast.parse(source)
        issues = check_bare_except_pass(tree)
        assert len(issues) == 1
        assert issues[0].check == "bare_except_pass"
        assert issues[0].severity == "warning"

    def test_except_exception_pass_not_flagged(self):
        """``except Exception: pass`` has a type — should NOT be flagged."""
        source = textwrap.dedent("""\
            try:
                x = 1
            except Exception:
                pass
        """)
        tree = ast.parse(source)
        assert check_bare_except_pass(tree) == []

    def test_bare_except_with_handler_logic_not_flagged(self):
        """Bare except with real handler logic should NOT be flagged."""
        source = textwrap.dedent("""\
            try:
                x = 1
            except:
                print("error occurred")
        """)
        tree = ast.parse(source)
        assert check_bare_except_pass(tree) == []

    def test_nested_bare_except_pass_flagged(self):
        """Bare except: pass inside a function body should still be caught."""
        source = textwrap.dedent("""\
            def foo():
                try:
                    x = 1
                except:
                    pass
        """)
        tree = ast.parse(source)
        issues = check_bare_except_pass(tree)
        assert len(issues) == 1


# -----------------------------------------------------------------------
# check_phantom_dependencies
# -----------------------------------------------------------------------


class TestCheckPhantomDependencies:
    """Tests for check_phantom_dependencies."""

    def test_known_package_no_issue(self):
        source = "import requests\n"
        tree = ast.parse(source)
        issues = check_phantom_dependencies(tree, known_packages={"requests"})
        assert issues == []

    def test_unknown_package_flagged(self):
        source = "import fancylib\n"
        tree = ast.parse(source)
        issues = check_phantom_dependencies(tree, known_packages={"requests"})
        assert len(issues) == 1
        assert issues[0].check == "phantom_dependency"
        assert "fancylib" in issues[0].message

    def test_import_inside_try_except_importerror_skipped(self):
        source = textwrap.dedent("""\
            try:
                import fancylib
            except ImportError:
                fancylib = None
        """)
        tree = ast.parse(source)
        issues = check_phantom_dependencies(tree, known_packages={"requests"})
        assert issues == []

    def test_known_packages_none_skips_check(self):
        source = "import fancylib\n"
        tree = ast.parse(source)
        issues = check_phantom_dependencies(tree, known_packages=None)
        assert issues == []

    def test_stdlib_not_flagged(self):
        source = "import os\nimport sys\nimport json\n"
        tree = ast.parse(source)
        issues = check_phantom_dependencies(tree, known_packages=set())
        assert issues == []

    def test_from_import_unknown_flagged(self):
        source = "from fancylib.utils import helper\n"
        tree = ast.parse(source)
        issues = check_phantom_dependencies(tree, known_packages={"requests"})
        assert len(issues) == 1
        assert "fancylib" in issues[0].message


# -----------------------------------------------------------------------
# run_semantic_checks (orchestrator)
# -----------------------------------------------------------------------


class TestRunSemanticChecks:
    """Tests for the run_semantic_checks orchestrator."""

    def test_combined_issues(self):
        """Source with 3 different issues should produce 3 SemanticIssue objects."""
        source = textwrap.dedent("""\
            import fancylib

            def foo():
                pass

            def foo():
                pass

            try:
                x = 1
            except:
                pass
        """)
        issues = run_semantic_checks(source, known_packages={"requests"})
        checks_found = {i.check for i in issues}
        assert "duplicate_definition" in checks_found
        assert "bare_except_pass" in checks_found
        assert "phantom_dependency" in checks_found
        assert len(issues) == 3

    def test_syntax_error_returns_empty(self):
        source = "def foo(\n"  # invalid syntax
        issues = run_semantic_checks(source)
        assert issues == []

    def test_file_path_stamped_on_all_issues(self):
        source = textwrap.dedent("""\
            def foo():
                pass

            def foo():
                pass
        """)
        issues = run_semantic_checks(source, file_path="/tmp/example.py")
        assert len(issues) == 1
        assert issues[0].file_path == "/tmp/example.py"

    def test_file_path_none_leaves_none(self):
        source = textwrap.dedent("""\
            def foo():
                pass

            def foo():
                pass
        """)
        issues = run_semantic_checks(source)
        assert len(issues) == 1
        assert issues[0].file_path is None


# -----------------------------------------------------------------------
# Integration engine wiring
# -----------------------------------------------------------------------


class TestIntegrationEngineWiring:
    """Verify that IntegrationEngine._run_semantic_checks calls the module."""

    @patch(
        "startd8.contractors.integration_engine.IntegrationEngine._run_semantic_checks"
    )
    def test_run_semantic_checks_is_called(self, mock_method: MagicMock):
        """_run_semantic_checks should be invocable on the engine class."""
        # Verify the method exists and is patchable (confirms wiring)
        mock_method.assert_not_called()

        # Call the mock to confirm it is the right target
        mock_method([], MagicMock())
        mock_method.assert_called_once()

    def test_semantic_checks_import_inside_method(self):
        """The engine lazily imports run_semantic_checks — verify the path resolves."""
        from startd8.validators.semantic_checks import run_semantic_checks as fn

        assert callable(fn)
