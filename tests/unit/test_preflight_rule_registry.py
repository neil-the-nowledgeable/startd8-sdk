"""
Tests for the PreflightRuleRegistry mechanics.

Covers: register, discover, evaluate_all, clear, duplicate handling,
priority ordering, domain filtering, decorator, entry-point discovery.
"""

from __future__ import annotations

from pathlib import Path
from typing import FrozenSet, Optional
from unittest.mock import patch, MagicMock

import pytest

from startd8.workflows.builtin.domain_preflight_models import (
    AvailableDeps,
    CheckStatus,
    EnvironmentCheck,
    TaskDomain,
)
from startd8.workflows.builtin.preflight_rules import (
    ALL_DOMAINS,
    CONFIG_DOMAINS,
    PYTHON_DOMAINS,
    PreflightRule,
    PreflightRuleRegistry,
    RuleContext,
    RuleContribution,
    preflight_rule,
)


# ============================================================================
# Helpers
# ============================================================================


def _make_ctx(
    tmp_path: Path,
    target_file: str = "src/foo.py",
    domain: TaskDomain = TaskDomain.PYTHON_SINGLE_MODULE,
) -> RuleContext:
    target_path = tmp_path / target_file
    return RuleContext(
        target_file=target_file,
        target_path=target_path,
        target_dir=target_path.parent,
        project_root=tmp_path,
        domain=domain,
        available_deps=AvailableDeps(
            runtime={"httpx"}, stdlib={"os", "sys"}, project={"startd8"},
        ),
    )


class DummyRule(PreflightRule):
    """Concrete rule for testing."""

    domains = ALL_DOMAINS
    priority = 100

    @property
    def rule_id(self) -> str:
        return "dummy_rule"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        return RuleContribution(
            checks=[EnvironmentCheck(
                check_name="dummy", status=CheckStatus.PASS, message="ok",
            )],
            constraints=["dummy constraint"],
        )


class HighPriorityRule(PreflightRule):
    """Runs first (priority=10)."""

    domains = ALL_DOMAINS
    priority = 10

    @property
    def rule_id(self) -> str:
        return "high_priority"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        return RuleContribution(constraints=["high first"])


class LowPriorityRule(PreflightRule):
    """Runs last (priority=200)."""

    domains = ALL_DOMAINS
    priority = 200

    @property
    def rule_id(self) -> str:
        return "low_priority"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        return RuleContribution(constraints=["low last"])


class PythonOnlyRule(PreflightRule):
    """Only applies to Python domains."""

    domains = PYTHON_DOMAINS
    priority = 100

    @property
    def rule_id(self) -> str:
        return "python_only"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        return RuleContribution(constraints=["python only"])


class ReturnsNoneRule(PreflightRule):
    """Returns None from evaluate."""

    domains = ALL_DOMAINS
    priority = 100

    @property
    def rule_id(self) -> str:
        return "returns_none"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        return None


class RaisingRule(PreflightRule):
    """Raises an exception in evaluate."""

    domains = ALL_DOMAINS
    priority = 100

    @property
    def rule_id(self) -> str:
        return "raising_rule"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleContribution]:
        raise ValueError("intentional test error")


# ============================================================================
# Tests
# ============================================================================


@pytest.fixture(autouse=True)
def clean_registry():
    """Clear registry before and after each test.

    Sets _discovered=True to suppress auto-discovery of built-in rules
    so that unit tests can test with only manually-registered rules.
    Tests for discover() should call discover(force=True) explicitly.
    """
    PreflightRuleRegistry.clear()
    # Suppress auto-discovery so evaluate_all only sees test rules
    PreflightRuleRegistry._discovered = True
    yield
    PreflightRuleRegistry.clear()


class TestRegister:
    def test_register_valid_rule(self):
        rule = DummyRule()
        PreflightRuleRegistry.register(rule)
        assert "dummy_rule" in PreflightRuleRegistry.list_rules()

    def test_register_non_rule_raises_type_error(self):
        with pytest.raises(TypeError, match="not a PreflightRule"):
            PreflightRuleRegistry.register("not a rule")

    def test_duplicate_overwrites_with_warning(self):
        PreflightRuleRegistry.register(DummyRule())
        PreflightRuleRegistry.register(DummyRule())
        assert PreflightRuleRegistry.list_rules().count("dummy_rule") == 1


class TestClear:
    def test_clear_removes_all_rules(self):
        PreflightRuleRegistry.register(DummyRule())
        PreflightRuleRegistry.register(HighPriorityRule())
        assert len(PreflightRuleRegistry.list_rules()) == 2

        PreflightRuleRegistry.clear()
        # Suppress auto-discovery so list_rules doesn't re-populate
        PreflightRuleRegistry._discovered = True
        assert len(PreflightRuleRegistry.list_rules()) == 0

    def test_clear_resets_discovered_flag(self):
        PreflightRuleRegistry.discover()
        PreflightRuleRegistry.clear()
        # After clear, _discovered is reset so next access re-imports
        assert not PreflightRuleRegistry._discovered


class TestEvaluateAll:
    def test_merges_contributions(self, tmp_path):
        PreflightRuleRegistry.register(DummyRule())
        ctx = _make_ctx(tmp_path)
        result = PreflightRuleRegistry.evaluate_all(ctx)

        assert len(result.checks) == 1
        assert result.checks[0].check_name == "dummy"
        assert "dummy constraint" in result.constraints

    def test_none_contributions_skipped(self, tmp_path):
        PreflightRuleRegistry.register(ReturnsNoneRule())
        ctx = _make_ctx(tmp_path)
        result = PreflightRuleRegistry.evaluate_all(ctx)

        assert result.checks == []
        assert result.constraints == []

    def test_exceptions_logged_not_propagated(self, tmp_path):
        PreflightRuleRegistry.register(RaisingRule())
        PreflightRuleRegistry.register(DummyRule())
        ctx = _make_ctx(tmp_path)
        result = PreflightRuleRegistry.evaluate_all(ctx)

        # DummyRule still contributed despite RaisingRule error
        assert len(result.checks) == 1
        assert result.checks[0].check_name == "dummy"


class TestPriorityOrdering:
    def test_lower_priority_runs_first(self, tmp_path):
        PreflightRuleRegistry.register(LowPriorityRule())
        PreflightRuleRegistry.register(HighPriorityRule())
        ctx = _make_ctx(tmp_path)
        result = PreflightRuleRegistry.evaluate_all(ctx)

        assert result.constraints == ["high first", "low last"]


class TestDomainFiltering:
    def test_python_only_rule_excluded_for_config(self, tmp_path):
        PreflightRuleRegistry.register(PythonOnlyRule())
        ctx = _make_ctx(tmp_path, domain=TaskDomain.CONFIG_TOML)
        result = PreflightRuleRegistry.evaluate_all(ctx)

        assert result.constraints == []

    def test_python_only_rule_included_for_python(self, tmp_path):
        PreflightRuleRegistry.register(PythonOnlyRule())
        ctx = _make_ctx(tmp_path, domain=TaskDomain.PYTHON_SINGLE_MODULE)
        result = PreflightRuleRegistry.evaluate_all(ctx)

        assert "python only" in result.constraints

    def test_all_domains_matches_everything(self, tmp_path):
        PreflightRuleRegistry.register(DummyRule())
        for domain in TaskDomain:
            ctx = _make_ctx(tmp_path, domain=domain)
            result = PreflightRuleRegistry.evaluate_all(ctx)
            assert len(result.checks) >= 1, f"DummyRule should match {domain}"


class TestDecorator:
    def test_decorator_registers_class(self):
        @preflight_rule(domains=frozenset({TaskDomain.PYTHON_TEST}), priority=42)
        class TestOnlyRule(PreflightRule):
            @property
            def rule_id(self):
                return "test_only_decorated"

            def evaluate(self, ctx):
                return RuleContribution(constraints=["test decorated"])

        assert "test_only_decorated" in PreflightRuleRegistry.list_rules()
        rule = PreflightRuleRegistry.get_rule("test_only_decorated")
        assert rule is not None
        assert rule.priority == 42
        assert rule.domains == frozenset({TaskDomain.PYTHON_TEST})


class TestGetRule:
    def test_get_existing_rule(self):
        PreflightRuleRegistry.register(DummyRule())
        rule = PreflightRuleRegistry.get_rule("dummy_rule")
        assert rule is not None
        assert rule.rule_id == "dummy_rule"

    def test_get_nonexistent_returns_none(self):
        assert PreflightRuleRegistry.get_rule("nonexistent") is None


class TestDomainConstants:
    def test_all_domains_has_all(self):
        assert ALL_DOMAINS == frozenset(TaskDomain)
        assert len(ALL_DOMAINS) == 8

    def test_python_domains(self):
        assert TaskDomain.PYTHON_SINGLE_MODULE in PYTHON_DOMAINS
        assert TaskDomain.PYTHON_PACKAGE_MODULE in PYTHON_DOMAINS
        assert TaskDomain.PYTHON_TEST in PYTHON_DOMAINS
        assert TaskDomain.CONFIG_TOML not in PYTHON_DOMAINS

    def test_config_domains(self):
        assert TaskDomain.CONFIG_TOML in CONFIG_DOMAINS
        assert TaskDomain.CONFIG_YAML in CONFIG_DOMAINS
        assert TaskDomain.CONFIG_JSON in CONFIG_DOMAINS
        assert TaskDomain.PYTHON_TEST not in CONFIG_DOMAINS


class TestDiscoverBuiltins:
    def test_discover_registers_builtin_rules(self):
        PreflightRuleRegistry.discover(force=True)
        rules = PreflightRuleRegistry.list_rules()

        # Check that key built-in rules are registered
        assert "parent_dir_exists" in rules
        assert "logger_reserved_fields" in rules
        assert "not_in_package" in rules
        assert "init_py_exists" in rules
        assert "source_module_exists" in rules
        assert "config_file_valid" in rules
        assert "single_module_constraints" in rules
        assert "package_module_constraints" in rules
        assert "test_constraints" in rules
        assert "config_constraints" in rules

    def test_discover_idempotent(self):
        PreflightRuleRegistry.discover()
        count1 = len(PreflightRuleRegistry.list_rules())
        PreflightRuleRegistry.discover()
        count2 = len(PreflightRuleRegistry.list_rules())
        assert count1 == count2


class TestEntryPointDiscovery:
    def test_entry_point_loading(self):
        """Mock entry-point discovery to verify the loading path works."""
        mock_ep = MagicMock()
        mock_ep.name = "test_ep_rule"
        mock_ep.load.return_value = DummyRule

        with patch(
            "startd8.workflows.builtin.preflight_rules._registry.sys"
        ) as mock_sys:
            mock_sys.version_info = (3, 12)
            with patch(
                "importlib.metadata.entry_points",
                return_value=[mock_ep],
            ):
                PreflightRuleRegistry._discover_entry_points()

        assert "dummy_rule" in PreflightRuleRegistry.list_rules()
