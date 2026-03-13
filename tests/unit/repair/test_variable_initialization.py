"""Tests for the variable_initialization repair step."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from startd8.repair.models import LintDiagnostic, RepairContext
from startd8.repair.steps.variable_initialization import (
    VariableInitializationStep,
    _WELL_KNOWN_VARIABLE_INITS,
    _collect_defined_names,
    _extract_module_level_assignments,
    _find_init_insertion_line,
)


@pytest.fixture
def step():
    return VariableInitializationStep()


def _make_context(*diags):
    return RepairContext(diagnostics=list(diags))


def _f821(name: str, file: str = "test.py") -> LintDiagnostic:
    return LintDiagnostic(
        category="lint",
        file=file,
        message=f"Undefined name `{name}`",
        rule="F821",
        line=10,
        fixable=True,
    )


class TestVariableInitialization:
    """Core functionality tests."""

    def test_inserts_faker_init(self, step):
        code = textwrap.dedent("""\
            from locust import HttpUser

            class UserBehavior(HttpUser):
                def on_start(self):
                    self.name = fake.first_name()
        """)
        ctx = _make_context(_f821("fake"))
        result = step(code, ctx, Path("test.py"))
        assert result.modified
        assert "fake = Faker()" in result.code
        assert "from faker import Faker" in result.code

    def test_skips_when_already_defined(self, step):
        code = textwrap.dedent("""\
            from faker import Faker

            fake = Faker()

            class UserBehavior:
                def on_start(self):
                    self.name = fake.first_name()
        """)
        ctx = _make_context(_f821("fake"))
        result = step(code, ctx, Path("test.py"))
        assert not result.modified

    def test_skips_unknown_names_without_skeleton(self, step):
        """Without skeleton, unknown names (not in well-known map) are skipped."""
        code = "x = unknown_thing.do()"
        ctx = _make_context(_f821("unknown_thing"))
        result = step(code, ctx, Path("test.py"))
        assert not result.modified

    def test_no_f821_diagnostics(self, step):
        code = "x = 1"
        ctx = _make_context()
        result = step(code, ctx, Path("test.py"))
        assert not result.modified

    def test_file_path_matching(self, step):
        """F821 diagnostic for a different file is ignored."""
        code = "x = fake.name()"
        ctx = _make_context(_f821("fake", file="other.py"))
        result = step(code, ctx, Path("test.py"))
        assert not result.modified

    def test_import_not_duplicated(self, step):
        """If import already present, only init is added."""
        code = textwrap.dedent("""\
            from faker import Faker

            def use_it():
                return fake.name()
        """)
        ctx = _make_context(_f821("fake"))
        result = step(code, ctx, Path("test.py"))
        assert result.modified
        assert "fake = Faker()" in result.code
        # Should NOT duplicate the import
        assert result.code.count("from faker import Faker") == 1

    def test_init_placed_after_imports(self, step):
        code = textwrap.dedent("""\
            import os
            from locust import HttpUser

            class UserBehavior(HttpUser):
                pass
        """)
        ctx = _make_context(_f821("fake"))
        result = step(code, ctx, Path("test.py"))
        assert result.modified
        lines = result.code.splitlines()
        # Find positions
        faker_import_idx = next(
            i for i, l in enumerate(lines)
            if "from faker import Faker" in l
        )
        init_idx = next(
            i for i, l in enumerate(lines)
            if l.strip() == "fake = Faker()"
        )
        class_idx = next(
            i for i, l in enumerate(lines)
            if "class UserBehavior" in l
        )
        # Init should be after imports, before class
        assert faker_import_idx < init_idx < class_idx

    def test_metrics_populated(self, step):
        code = "x = fake.name()"
        ctx = _make_context(_f821("fake"))
        result = step(code, ctx, Path("test.py"))
        assert result.metrics["variables_initialized"] == ["fake = Faker()"]
        assert "from faker import Faker" in result.metrics["imports_added"]


class TestHelpers:
    """Tests for helper functions."""

    def test_collect_defined_names(self):
        code = textwrap.dedent("""\
            import os
            from pathlib import Path

            MY_CONST = 42
            x: int = 10

            def foo():
                pass

            class Bar:
                pass
        """)
        names = _collect_defined_names(code)
        assert "os" in names
        assert "Path" in names
        assert "MY_CONST" in names
        assert "x" in names
        assert "foo" in names
        assert "Bar" in names

    def test_collect_defined_names_syntax_error(self):
        assert _collect_defined_names("def broken(") == set()

    def test_find_init_insertion_line(self):
        lines = [
            "import os",
            "from pathlib import Path",
            "",
            "def foo():",
            "    pass",
        ]
        idx = _find_init_insertion_line(lines)
        assert idx == 2  # After the last import

    def test_find_init_insertion_line_no_imports(self):
        lines = ["def foo():", "    pass"]
        idx = _find_init_insertion_line(lines)
        assert idx == 0


class TestSkeletonRecovery:
    """Tests for skeleton-based variable recovery (F821 ground truth)."""

    def test_recovers_variable_from_skeleton(self, step):
        """F821 for a name present in skeleton → re-insert from skeleton."""
        skeleton = textwrap.dedent("""\
            import os

            product_ids = ["OLJCESPC7Z", "66VCHSJNUP"]

            def get_products():
                return product_ids
        """)
        code = textwrap.dedent("""\
            import os

            def get_products():
                return product_ids
        """)
        ctx = RepairContext(
            diagnostics=[_f821("product_ids")],
            skeleton_content=skeleton,
        )
        result = step(code, ctx, Path("test.py"))
        assert result.modified
        assert 'product_ids = ["OLJCESPC7Z", "66VCHSJNUP"]' in result.code
        assert "product_ids" in result.metrics.get("skeleton_recovered", [])

    def test_skeleton_recovery_skips_already_defined(self, step):
        skeleton = textwrap.dedent("""\
            config = {"key": "value"}

            def use_config():
                return config
        """)
        code = textwrap.dedent("""\
            config = {"key": "value"}

            def use_config():
                return config
        """)
        ctx = RepairContext(
            diagnostics=[_f821("config")],
            skeleton_content=skeleton,
        )
        result = step(code, ctx, Path("test.py"))
        assert not result.modified

    def test_skeleton_recovery_with_annotated_assignment(self, step):
        skeleton = textwrap.dedent("""\
            api_client: ApiClient = ApiClient("https://example.com")

            def call_api():
                return api_client.get("/data")
        """)
        code = textwrap.dedent("""\
            def call_api():
                return api_client.get("/data")
        """)
        ctx = RepairContext(
            diagnostics=[_f821("api_client")],
            skeleton_content=skeleton,
        )
        result = step(code, ctx, Path("test.py"))
        assert result.modified
        assert 'api_client: ApiClient = ApiClient("https://example.com")' in result.code

    def test_well_known_takes_precedence_over_skeleton(self, step):
        """Well-known patterns are used even when skeleton has a different init."""
        skeleton = textwrap.dedent("""\
            from faker import Faker

            fake = Faker("en_US")  # skeleton has locale arg

            def gen():
                return fake.name()
        """)
        code = textwrap.dedent("""\
            def gen():
                return fake.name()
        """)
        ctx = RepairContext(
            diagnostics=[_f821("fake")],
            skeleton_content=skeleton,
        )
        result = step(code, ctx, Path("test.py"))
        assert result.modified
        # Well-known pattern wins
        assert "fake = Faker()" in result.code
        # NOT the skeleton's locale-specific version
        assert 'Faker("en_US")' not in result.code

    def test_no_skeleton_no_recovery(self, step):
        """Without skeleton_content, unknown names are not recovered."""
        code = textwrap.dedent("""\
            def use_it():
                return product_ids[0]
        """)
        ctx = RepairContext(diagnostics=[_f821("product_ids")])
        result = step(code, ctx, Path("test.py"))
        assert not result.modified

    def test_skeleton_syntax_error_fallback(self, step):
        """Skeleton with syntax errors doesn't crash — falls back to no-op."""
        code = textwrap.dedent("""\
            def use_it():
                return product_ids[0]
        """)
        ctx = RepairContext(
            diagnostics=[_f821("product_ids")],
            skeleton_content="def broken(",
        )
        result = step(code, ctx, Path("test.py"))
        assert not result.modified


class TestExtractModuleLevelAssignments:
    """Tests for _extract_module_level_assignments helper."""

    def test_extracts_simple_assignment(self):
        code = textwrap.dedent("""\
            x = 42
            y = [1, 2, 3]
        """)
        assignments = _extract_module_level_assignments(code)
        assert "x" in assignments
        assert "y" in assignments
        assert assignments["x"] == "x = 42"

    def test_extracts_annotated_assignment(self):
        code = "client: HttpClient = HttpClient()"
        assignments = _extract_module_level_assignments(code)
        assert "client" in assignments

    def test_ignores_functions_and_classes(self):
        code = textwrap.dedent("""\
            def foo():
                pass

            class Bar:
                pass
        """)
        assignments = _extract_module_level_assignments(code)
        assert "foo" not in assignments
        assert "Bar" not in assignments

    def test_syntax_error_returns_empty(self):
        assert _extract_module_level_assignments("def broken(") == {}


class TestWellKnownMapping:
    """Verify the well-known mapping is consistent."""

    def test_all_entries_have_import_and_init(self):
        for name, (imp, init) in _WELL_KNOWN_VARIABLE_INITS.items():
            assert imp.startswith(("from ", "import "))
            assert f"{name} =" in init or f"{name}=" in init
