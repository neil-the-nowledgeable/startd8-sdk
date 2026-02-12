"""
Tests for built-in preflight rules.

Each rule is tested in isolation with tmp_path fixtures,
asserting that its RuleContribution matches current behavior.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Optional

import pytest

from startd8.workflows.builtin.domain_preflight_models import (
    AvailableDeps,
    CheckStatus,
    EnvironmentCheck,
    TaskDomain,
)
from startd8.workflows.builtin.preflight_rules import (
    PreflightRuleRegistry,
    RuleContext,
    RuleContribution,
)
from startd8.workflows.builtin.preflight_rules.rules_common import (
    LoggerReservedFieldsRule,
    ParentDirExistsRule,
)
from startd8.workflows.builtin.preflight_rules.rules_python_single import (
    NotInPackageRule,
    OptionalDepGuardsSingleRule,
    SingleModuleConstraintsRule,
)
from startd8.workflows.builtin.preflight_rules.rules_python_package import (
    CircularImportsRule,
    InitPyExistsRule,
    OptionalDepGuardsPackageRule,
    PackageModuleConstraintsRule,
    ParentPackageImportableRule,
    PydanticPropertyConfusionRule,
)
from startd8.workflows.builtin.preflight_rules.rules_python_test import (
    ConftestScannableRule,
    PatchPathValidRule,
    SourceModuleExistsRule,
    TestConstraintsRule,
    TestDirExistsRule,
    ThreadAwareTeardownRule,
)
from startd8.workflows.builtin.preflight_rules.rules_config import (
    ConfigConstraintsRule,
    ConfigFileValidRule,
    EntryPointReinstallRule,
)
from startd8.workflows.builtin.preflight_rules.rules_validators import (
    DefinitionOrderingValidatorRule,
    DepsAvailableValidatorRule,
    MergeDamageDetectorRule,
    NoRelativeImportsValidatorRule,
)


# ============================================================================
# Helpers
# ============================================================================


def _make_deps(**kw) -> AvailableDeps:
    defaults = dict(
        runtime={"httpx", "rich"},
        stdlib={"os", "sys"},
        project={"startd8"},
    )
    defaults.update(kw)
    return AvailableDeps(**defaults)


def _ctx(
    tmp_path: Path,
    target_file: str = "src/foo.py",
    domain: TaskDomain = TaskDomain.PYTHON_SINGLE_MODULE,
    deps: Optional[AvailableDeps] = None,
) -> RuleContext:
    target_path = tmp_path / target_file
    return RuleContext(
        target_file=target_file,
        target_path=target_path,
        target_dir=target_path.parent,
        project_root=tmp_path,
        domain=domain,
        available_deps=deps or _make_deps(),
    )


# ============================================================================
# Common rules
# ============================================================================


class TestParentDirExistsRule:
    def test_pass_when_dir_exists(self, tmp_path):
        (tmp_path / "src").mkdir()
        rule = ParentDirExistsRule()
        result = rule.evaluate(_ctx(tmp_path))
        assert result is not None
        assert result.checks[0].status == CheckStatus.PASS

    def test_warn_when_dir_missing(self, tmp_path):
        rule = ParentDirExistsRule()
        result = rule.evaluate(_ctx(tmp_path, target_file="nonexistent/foo.py"))
        assert result is not None
        assert result.checks[0].status == CheckStatus.WARN


class TestLoggerReservedFieldsRule:
    def test_pass_when_file_uses_logging(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "foo.py").write_text(
            "import logging\nlogger = logging.getLogger(__name__)\n"
        )
        rule = LoggerReservedFieldsRule()
        result = rule.evaluate(_ctx(tmp_path))
        assert result is not None
        assert result.checks[0].status == CheckStatus.PASS
        assert any("LogRecord" in c for c in result.constraints)

    def test_none_when_no_logging(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "foo.py").write_text("import os\n")
        rule = LoggerReservedFieldsRule()
        result = rule.evaluate(_ctx(tmp_path))
        assert result is None

    def test_none_when_file_missing(self, tmp_path):
        rule = LoggerReservedFieldsRule()
        result = rule.evaluate(_ctx(tmp_path))
        assert result is None


# ============================================================================
# Python single module rules
# ============================================================================


class TestNotInPackageRule:
    def test_pass_when_no_init(self, tmp_path):
        (tmp_path / "src").mkdir()
        rule = NotInPackageRule()
        result = rule.evaluate(_ctx(tmp_path))
        assert result.checks[0].status == CheckStatus.PASS

    def test_warn_when_init_exists(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "__init__.py").touch()
        rule = NotInPackageRule()
        result = rule.evaluate(_ctx(tmp_path))
        assert result.checks[0].status == CheckStatus.WARN


class TestOptionalDepGuardsSingleRule:
    def test_warns_on_unguarded(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "foo.py").write_text(textwrap.dedent("""\
            try:
                import tiktoken
            except ImportError:
                tiktoken = None
        """))
        rule = OptionalDepGuardsSingleRule()
        result = rule.evaluate(_ctx(tmp_path))
        assert result is not None
        check_names = [c.check_name for c in result.checks]
        assert "optional_dep_guards" in check_names
        assert any("tiktoken" in c for c in result.constraints)

    def test_none_when_file_missing(self, tmp_path):
        rule = OptionalDepGuardsSingleRule()
        result = rule.evaluate(_ctx(tmp_path))
        assert result is None


class TestSingleModuleConstraintsRule:
    def test_produces_constraints_and_validators(self, tmp_path):
        rule = SingleModuleConstraintsRule()
        result = rule.evaluate(_ctx(tmp_path))
        assert any("single Python module" in c for c in result.constraints)
        assert "no_relative_imports" in result.validators
        assert "deps_available" in result.validators
        assert "definition_ordering" in result.validators
        assert "no_markdown_fences" in result.validators


# ============================================================================
# Python package module rules
# ============================================================================


class TestInitPyExistsRule:
    def test_pass_when_init_exists(self, tmp_path):
        pkg = tmp_path / "src" / "pkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").touch()
        rule = InitPyExistsRule()
        result = rule.evaluate(_ctx(
            tmp_path, "src/pkg/module.py", TaskDomain.PYTHON_PACKAGE_MODULE,
        ))
        assert result.checks[0].status == CheckStatus.PASS

    def test_fail_when_init_missing(self, tmp_path):
        pkg = tmp_path / "src" / "pkg"
        pkg.mkdir(parents=True)
        rule = InitPyExistsRule()
        result = rule.evaluate(_ctx(
            tmp_path, "src/pkg/module.py", TaskDomain.PYTHON_PACKAGE_MODULE,
        ))
        assert result.checks[0].status == CheckStatus.FAIL


class TestParentPackageImportableRule:
    def test_pass_when_parent_has_init(self, tmp_path):
        pkg = tmp_path / "src" / "pkg"
        pkg.mkdir(parents=True)
        (tmp_path / "src" / "__init__.py").touch()
        rule = ParentPackageImportableRule()
        result = rule.evaluate(_ctx(
            tmp_path, "src/pkg/module.py", TaskDomain.PYTHON_PACKAGE_MODULE,
        ))
        assert result.checks[0].status == CheckStatus.PASS

    def test_warn_when_parent_has_no_init(self, tmp_path):
        pkg = tmp_path / "src" / "pkg"
        pkg.mkdir(parents=True)
        rule = ParentPackageImportableRule()
        result = rule.evaluate(_ctx(
            tmp_path, "src/pkg/module.py", TaskDomain.PYTHON_PACKAGE_MODULE,
        ))
        assert result.checks[0].status == CheckStatus.WARN


class TestCircularImportsRule:
    def test_detects_circular(self, tmp_path):
        pkg = tmp_path / "src" / "pkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").touch()
        (pkg / "module_a.py").write_text("from .module_b import foo\n")
        (pkg / "module_b.py").write_text("from .module_a import bar\n")
        rule = CircularImportsRule()
        result = rule.evaluate(_ctx(
            tmp_path, "src/pkg/module_a.py", TaskDomain.PYTHON_PACKAGE_MODULE,
        ))
        assert result is not None
        assert result.checks[0].check_name == "circular_imports"
        assert result.checks[0].status == CheckStatus.WARN

    def test_no_circular_when_one_way(self, tmp_path):
        pkg = tmp_path / "src" / "pkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").touch()
        (pkg / "module_a.py").write_text("from .module_b import foo\n")
        (pkg / "module_b.py").write_text("import os\n")
        rule = CircularImportsRule()
        result = rule.evaluate(_ctx(
            tmp_path, "src/pkg/module_a.py", TaskDomain.PYTHON_PACKAGE_MODULE,
        ))
        assert result is None


class TestPydanticPropertyConfusionRule:
    def test_warns_when_sibling_has_property(self, tmp_path):
        pkg = tmp_path / "src" / "pkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").touch()
        (pkg / "base.py").write_text(
            "class Base:\n    @property\n    def name(self): return 'x'\n"
        )
        rule = PydanticPropertyConfusionRule()
        result = rule.evaluate(_ctx(
            tmp_path, "src/pkg/models.py", TaskDomain.PYTHON_PACKAGE_MODULE,
        ))
        assert result is not None
        assert any("@property" in c and "Pydantic" in c for c in result.constraints)

    def test_none_when_no_property(self, tmp_path):
        pkg = tmp_path / "src" / "pkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").touch()
        (pkg / "base.py").write_text("class Base: pass\n")
        rule = PydanticPropertyConfusionRule()
        result = rule.evaluate(_ctx(
            tmp_path, "src/pkg/models.py", TaskDomain.PYTHON_PACKAGE_MODULE,
        ))
        assert result is None


class TestPackageModuleConstraintsRule:
    def test_produces_constraints_and_validators(self, tmp_path):
        pkg = tmp_path / "src" / "pkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").touch()
        (pkg / "base.py").touch()
        (pkg / "utils.py").touch()
        rule = PackageModuleConstraintsRule()
        result = rule.evaluate(_ctx(
            tmp_path, "src/pkg/models.py", TaskDomain.PYTHON_PACKAGE_MODULE,
        ))
        assert any("pkg" in c for c in result.constraints)
        assert "relative_imports_valid" in result.validators
        assert "no_markdown_fences" in result.validators


# ============================================================================
# Python test rules
# ============================================================================


class TestSourceModuleExistsRule:
    def test_pass_when_source_found(self, tmp_path):
        src = tmp_path / "src" / "mylib"
        src.mkdir(parents=True)
        (src / "__init__.py").touch()
        (src / "models.py").touch()
        (tmp_path / "tests").mkdir()
        rule = SourceModuleExistsRule()
        result = rule.evaluate(_ctx(
            tmp_path, "tests/test_models.py", TaskDomain.PYTHON_TEST,
        ))
        assert result is not None
        assert result.checks[0].status == CheckStatus.PASS

    def test_warn_when_source_not_found(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        rule = SourceModuleExistsRule()
        result = rule.evaluate(_ctx(
            tmp_path, "tests/test_models.py", TaskDomain.PYTHON_TEST,
        ))
        assert result is not None
        assert result.checks[0].status == CheckStatus.WARN


class TestTestDirExistsRule:
    def test_pass_when_dir_exists(self, tmp_path):
        (tmp_path / "tests").mkdir()
        rule = TestDirExistsRule()
        result = rule.evaluate(_ctx(
            tmp_path, "tests/test_foo.py", TaskDomain.PYTHON_TEST,
        ))
        assert result.checks[0].status == CheckStatus.PASS

    def test_warn_when_missing(self, tmp_path):
        rule = TestDirExistsRule()
        result = rule.evaluate(_ctx(
            tmp_path, "tests/test_foo.py", TaskDomain.PYTHON_TEST,
        ))
        assert result.checks[0].status == CheckStatus.WARN


class TestConftestScannableRule:
    def test_pass_when_conftest_exists(self, tmp_path):
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "conftest.py").touch()
        rule = ConftestScannableRule()
        result = rule.evaluate(_ctx(
            tmp_path, "tests/test_foo.py", TaskDomain.PYTHON_TEST,
        ))
        assert result.checks[0].status == CheckStatus.PASS

    def test_skip_when_no_conftest(self, tmp_path):
        (tmp_path / "tests").mkdir()
        rule = ConftestScannableRule()
        result = rule.evaluate(_ctx(
            tmp_path, "tests/test_foo.py", TaskDomain.PYTHON_TEST,
        ))
        assert result.checks[0].status == CheckStatus.SKIP


class TestPatchPathValidRule:
    def test_warns_on_stale_patch(self, tmp_path):
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "test_foo.py").write_text(textwrap.dedent("""\
            from unittest.mock import patch

            @patch("nonexistent.module.SomeClass")
            def test_something(mock_cls):
                pass
        """))
        rule = PatchPathValidRule()
        result = rule.evaluate(_ctx(
            tmp_path, "tests/test_foo.py", TaskDomain.PYTHON_TEST,
        ))
        assert result is not None
        patch_checks = [c for c in result.checks if c.check_name == "patch_path_valid"]
        assert len(patch_checks) >= 1

    def test_none_when_file_missing(self, tmp_path):
        rule = PatchPathValidRule()
        result = rule.evaluate(_ctx(
            tmp_path, "tests/test_foo.py", TaskDomain.PYTHON_TEST,
        ))
        assert result is None


class TestThreadAwareTeardownRule:
    def test_warns_when_source_uses_threading(self, tmp_path):
        src = tmp_path / "src" / "mylib"
        src.mkdir(parents=True)
        (src / "__init__.py").touch()
        (src / "worker.py").write_text(
            "import threading\nclass Worker(threading.Thread): pass\n"
        )
        (tmp_path / "tests").mkdir()
        rule = ThreadAwareTeardownRule()
        result = rule.evaluate(_ctx(
            tmp_path, "tests/test_worker.py", TaskDomain.PYTHON_TEST,
        ))
        assert result is not None
        assert result.checks[0].check_name == "thread_aware_teardown"
        assert any("threading" in c for c in result.constraints)

    def test_none_when_no_threading(self, tmp_path):
        src = tmp_path / "src" / "mylib"
        src.mkdir(parents=True)
        (src / "__init__.py").touch()
        (src / "worker.py").write_text("import os\n")
        (tmp_path / "tests").mkdir()
        rule = ThreadAwareTeardownRule()
        result = rule.evaluate(_ctx(
            tmp_path, "tests/test_worker.py", TaskDomain.PYTHON_TEST,
        ))
        assert result is None


class TestTestConstraintsRule:
    def test_produces_constraints_and_validators(self, tmp_path):
        (tmp_path / "tests").mkdir()
        rule = TestConstraintsRule()
        result = rule.evaluate(_ctx(
            tmp_path, "tests/test_foo.py", TaskDomain.PYTHON_TEST,
        ))
        assert any("pytest" in c.lower() for c in result.constraints)
        assert "imports_resolve" in result.validators
        assert "test_naming" in result.validators

    def test_scans_conftest_fixtures(self, tmp_path):
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "conftest.py").write_text(textwrap.dedent("""\
            import pytest

            @pytest.fixture()
            def sample_data():
                return {}
        """))
        rule = TestConstraintsRule()
        result = rule.evaluate(_ctx(
            tmp_path, "tests/test_foo.py", TaskDomain.PYTHON_TEST,
        ))
        assert any("sample_data" in c for c in result.constraints)


# ============================================================================
# Config rules
# ============================================================================


class TestConfigFileValidRule:
    def test_pass_valid_json(self, tmp_path):
        (tmp_path / "config.json").write_text('{"key": "value"}')
        rule = ConfigFileValidRule()
        result = rule.evaluate(_ctx(
            tmp_path, "config.json", TaskDomain.CONFIG_JSON,
        ))
        exists_checks = [c for c in result.checks if c.check_name == "config_file_exists"]
        assert exists_checks[0].status == CheckStatus.PASS
        format_checks = [c for c in result.checks if c.check_name == "config_format_valid"]
        assert format_checks[0].status == CheckStatus.PASS

    def test_skip_when_missing(self, tmp_path):
        rule = ConfigFileValidRule()
        result = rule.evaluate(_ctx(
            tmp_path, "config.json", TaskDomain.CONFIG_JSON,
        ))
        assert result.checks[0].check_name == "config_file_exists"
        assert result.checks[0].status == CheckStatus.SKIP


class TestEntryPointReinstallRule:
    def test_warns_for_pyproject_toml(self, tmp_path):
        rule = EntryPointReinstallRule()
        result = rule.evaluate(_ctx(
            tmp_path, "pyproject.toml", TaskDomain.CONFIG_TOML,
        ))
        assert result is not None
        assert result.checks[0].check_name == "entry_point_reinstall"
        assert any("pip install" in c for c in result.constraints)

    def test_none_for_other_toml(self, tmp_path):
        rule = EntryPointReinstallRule()
        result = rule.evaluate(_ctx(
            tmp_path, "config.toml", TaskDomain.CONFIG_TOML,
        ))
        assert result is None


class TestConfigConstraintsRule:
    def test_constraints_with_existing_file(self, tmp_path):
        (tmp_path / "config.json").write_text("{}")
        rule = ConfigConstraintsRule()
        result = rule.evaluate(_ctx(
            tmp_path, "config.json", TaskDomain.CONFIG_JSON,
        ))
        assert "Preserve existing sections" in result.constraints
        assert "Current content provided as context" in result.constraints
        assert "valid_format" in result.validators

    def test_constraints_without_existing_file(self, tmp_path):
        rule = ConfigConstraintsRule()
        result = rule.evaluate(_ctx(
            tmp_path, "config.json", TaskDomain.CONFIG_JSON,
        ))
        assert "Preserve existing sections" in result.constraints
        assert "Current content provided as context" not in result.constraints


# ============================================================================
# Validator rules
# ============================================================================


class TestValidatorRules:
    def test_no_relative_imports_validator_rule(self, tmp_path):
        rule = NoRelativeImportsValidatorRule()
        result = rule.evaluate(_ctx(tmp_path))
        assert "no_relative_imports" in result.validator_fns

    def test_deps_available_validator_rule(self, tmp_path):
        rule = DepsAvailableValidatorRule()
        result = rule.evaluate(_ctx(tmp_path))
        assert "deps_available" in result.validator_fns

    def test_definition_ordering_validator_rule(self, tmp_path):
        rule = DefinitionOrderingValidatorRule()
        result = rule.evaluate(_ctx(tmp_path))
        assert "definition_ordering" in result.validator_fns


class TestMergeDamageDetectorRule:
    def test_rule_contributes_validator(self, tmp_path):
        rule = MergeDamageDetectorRule()
        result = rule.evaluate(_ctx(tmp_path))
        assert "merge_damage" in result.validator_fns

    def test_detects_duplicate_definitions(self, tmp_path):
        # Code with same function defined twice
        code = textwrap.dedent("""\
            def helper():
                return 1

            class Foo:
                pass

            def helper():
                return 2
        """)
        rule = MergeDamageDetectorRule()
        result = rule.evaluate(_ctx(tmp_path))
        fn = result.validator_fns["merge_damage"]
        issues = fn(code, None)
        assert any("duplicate" in i["message"].lower() for i in issues)

    def test_detects_duplicate_class_definitions(self, tmp_path):
        # Code with same class defined twice
        code = textwrap.dedent("""\
            class Config:
                x = 1

            class Config:
                x = 2
        """)
        rule = MergeDamageDetectorRule()
        result = rule.evaluate(_ctx(tmp_path))
        fn = result.validator_fns["merge_damage"]
        issues = fn(code, None)
        assert any("duplicate" in i["message"].lower() for i in issues)
        assert any("Config" in i["message"] for i in issues)

    def test_detects_ordering_damage(self, tmp_path):
        # Class uses default_factory=make_list, but make_list defined after
        code = textwrap.dedent("""\
            class Config:
                items: list = Field(default_factory=make_list)

            def make_list():
                return []
        """)
        rule = MergeDamageDetectorRule()
        result = rule.evaluate(_ctx(tmp_path))
        fn = result.validator_fns["merge_damage"]
        issues = fn(code, None)
        assert any("make_list" in i["message"] for i in issues)

    def test_passes_clean_code(self, tmp_path):
        code = textwrap.dedent("""\
            def make_list():
                return []

            class Config:
                items: list = Field(default_factory=make_list)
        """)
        rule = MergeDamageDetectorRule()
        result = rule.evaluate(_ctx(tmp_path))
        fn = result.validator_fns["merge_damage"]
        issues = fn(code, None)
        assert issues == []

    def test_applies_to_all_python_domains(self, tmp_path):
        """MergeDamageDetectorRule should apply to all Python domains."""
        rule = MergeDamageDetectorRule()
        from startd8.workflows.builtin.preflight_rules._base import PYTHON_DOMAINS
        assert rule.domains == PYTHON_DOMAINS

    def test_handles_syntax_error_gracefully(self, tmp_path):
        code = "def foo(:\n    pass\n"
        rule = MergeDamageDetectorRule()
        result = rule.evaluate(_ctx(tmp_path))
        fn = result.validator_fns["merge_damage"]
        issues = fn(code, None)
        assert issues == []
