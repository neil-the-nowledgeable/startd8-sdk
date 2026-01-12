"""
Tests for the self-diagnostic workflow.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
import tempfile
from pathlib import Path


class TestHealthStatus:
    """Tests for HealthStatus enum"""

    def test_all_status_values(self):
        """All expected status values exist"""
        from startd8.diagnostics import HealthStatus

        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.WARNING.value == "warning"
        assert HealthStatus.CRITICAL.value == "critical"
        assert HealthStatus.UNKNOWN.value == "unknown"
        assert HealthStatus.SKIPPED.value == "skipped"


class TestCheckCategory:
    """Tests for CheckCategory enum"""

    def test_all_category_values(self):
        """All expected category values exist"""
        from startd8.diagnostics import CheckCategory

        assert CheckCategory.AGENTS.value == "agents"
        assert CheckCategory.COSTS.value == "costs"
        assert CheckCategory.STORAGE.value == "storage"
        assert CheckCategory.FRAMEWORK.value == "framework"


class TestHealthCheck:
    """Tests for HealthCheck dataclass"""

    def test_create_health_check(self):
        """Can create a HealthCheck with required fields"""
        from startd8.diagnostics import HealthCheck, HealthStatus, CheckCategory

        check = HealthCheck(
            name="test_check",
            category=CheckCategory.AGENTS,
            status=HealthStatus.HEALTHY,
            message="All good",
        )

        assert check.name == "test_check"
        assert check.category == CheckCategory.AGENTS
        assert check.status == HealthStatus.HEALTHY
        assert check.message == "All good"

    def test_is_healthy_property(self):
        """is_healthy returns True only for HEALTHY status"""
        from startd8.diagnostics import HealthCheck, HealthStatus, CheckCategory

        healthy = HealthCheck(
            name="test", category=CheckCategory.AGENTS,
            status=HealthStatus.HEALTHY, message="ok"
        )
        warning = HealthCheck(
            name="test", category=CheckCategory.AGENTS,
            status=HealthStatus.WARNING, message="warn"
        )

        assert healthy.is_healthy is True
        assert warning.is_healthy is False

    def test_is_failure_property(self):
        """is_failure returns True for WARNING, CRITICAL, UNKNOWN"""
        from startd8.diagnostics import HealthCheck, HealthStatus, CheckCategory

        for status in [HealthStatus.WARNING, HealthStatus.CRITICAL, HealthStatus.UNKNOWN]:
            check = HealthCheck(
                name="test", category=CheckCategory.AGENTS,
                status=status, message="fail"
            )
            assert check.is_failure is True

        healthy = HealthCheck(
            name="test", category=CheckCategory.AGENTS,
            status=HealthStatus.HEALTHY, message="ok"
        )
        assert healthy.is_failure is False

    def test_to_dict(self):
        """to_dict serializes correctly"""
        from startd8.diagnostics import HealthCheck, HealthStatus, CheckCategory

        check = HealthCheck(
            name="test_check",
            category=CheckCategory.AGENTS,
            status=HealthStatus.WARNING,
            message="Warning message",
            details={"key": "value"},
            fix_hint="some_fix",
        )

        d = check.to_dict()

        assert d["name"] == "test_check"
        assert d["category"] == "agents"
        assert d["status"] == "warning"
        assert d["message"] == "Warning message"
        assert d["details"] == {"key": "value"}
        assert d["fix_hint"] == "some_fix"


class TestDiagnosticReport:
    """Tests for DiagnosticReport dataclass"""

    def test_summary_counts_correctly(self):
        """summary correctly counts checks by status"""
        from startd8.diagnostics import DiagnosticReport, HealthCheck, HealthStatus, CheckCategory

        checks = [
            HealthCheck("c1", CheckCategory.AGENTS, HealthStatus.HEALTHY, "ok"),
            HealthCheck("c2", CheckCategory.AGENTS, HealthStatus.HEALTHY, "ok"),
            HealthCheck("c3", CheckCategory.COSTS, HealthStatus.WARNING, "warn"),
            HealthCheck("c4", CheckCategory.STORAGE, HealthStatus.CRITICAL, "fail"),
        ]

        report = DiagnosticReport(checks=checks)
        summary = report.summary

        assert summary["healthy"] == 2
        assert summary["warning"] == 1
        assert summary["critical"] == 1

    def test_has_failures(self):
        """has_failures detects failures correctly"""
        from startd8.diagnostics import DiagnosticReport, HealthCheck, HealthStatus, CheckCategory

        all_healthy = DiagnosticReport(checks=[
            HealthCheck("c1", CheckCategory.AGENTS, HealthStatus.HEALTHY, "ok"),
        ])
        assert all_healthy.has_failures() is False

        has_warning = DiagnosticReport(checks=[
            HealthCheck("c1", CheckCategory.AGENTS, HealthStatus.WARNING, "warn"),
        ])
        assert has_warning.has_failures() is True

    def test_get_failures(self):
        """get_failures returns only failed checks"""
        from startd8.diagnostics import DiagnosticReport, HealthCheck, HealthStatus, CheckCategory

        checks = [
            HealthCheck("c1", CheckCategory.AGENTS, HealthStatus.HEALTHY, "ok"),
            HealthCheck("c2", CheckCategory.COSTS, HealthStatus.WARNING, "warn"),
            HealthCheck("c3", CheckCategory.STORAGE, HealthStatus.CRITICAL, "fail"),
        ]

        report = DiagnosticReport(checks=checks)
        failures = report.get_failures()

        assert len(failures) == 2
        assert all(f.status != HealthStatus.HEALTHY for f in failures)

    def test_get_by_category(self):
        """get_by_category filters correctly"""
        from startd8.diagnostics import DiagnosticReport, HealthCheck, HealthStatus, CheckCategory

        checks = [
            HealthCheck("c1", CheckCategory.AGENTS, HealthStatus.HEALTHY, "ok"),
            HealthCheck("c2", CheckCategory.AGENTS, HealthStatus.WARNING, "warn"),
            HealthCheck("c3", CheckCategory.COSTS, HealthStatus.HEALTHY, "ok"),
        ]

        report = DiagnosticReport(checks=checks)
        agent_checks = report.get_by_category(CheckCategory.AGENTS)

        assert len(agent_checks) == 2
        assert all(c.category == CheckCategory.AGENTS for c in agent_checks)

    def test_to_markdown(self):
        """to_markdown generates valid markdown"""
        from startd8.diagnostics import DiagnosticReport, HealthCheck, HealthStatus, CheckCategory

        checks = [
            HealthCheck("c1", CheckCategory.AGENTS, HealthStatus.HEALTHY, "ok"),
            HealthCheck("c2", CheckCategory.COSTS, HealthStatus.WARNING, "warn"),
        ]

        report = DiagnosticReport(checks=checks)
        md = report.to_markdown()

        assert "# Diagnostic Report" in md
        assert "## Summary" in md
        assert "Healthy: 1" in md
        assert "Warnings: 1" in md


class TestDiagnosticRunner:
    """Tests for DiagnosticRunner"""

    def test_run_all_returns_report(self):
        """run_all returns a DiagnosticReport"""
        from startd8.diagnostics import DiagnosticRunner, DiagnosticReport

        runner = DiagnosticRunner()
        report = runner.run_all(include_api_checks=False)

        assert isinstance(report, DiagnosticReport)
        assert len(report.checks) > 0

    def test_run_quick_skips_api_checks(self):
        """run_quick doesn't include API checks"""
        from startd8.diagnostics import DiagnosticRunner

        runner = DiagnosticRunner()
        report = runner.run_quick()

        # Connectivity checks should be skipped
        check_names = [c.name for c in report.checks]
        # These are the API checks that should NOT be in quick mode
        assert "claude_connectivity" not in check_names
        assert "openai_connectivity" not in check_names
        assert "gemini_connectivity" not in check_names

    def test_run_category_filters_correctly(self):
        """run_category only runs checks for specified category"""
        from startd8.diagnostics import DiagnosticRunner, CheckCategory

        runner = DiagnosticRunner()
        report = runner.run_category(CheckCategory.STORAGE)

        # All checks should be storage category
        for check in report.checks:
            assert check.category == CheckCategory.STORAGE


class TestDiagnosticAnalyzer:
    """Tests for DiagnosticAnalyzer"""

    def test_uses_mock_agent_by_default(self):
        """DiagnosticAnalyzer defaults to MockAgent"""
        from startd8.diagnostics import DiagnosticAnalyzer
        from startd8.agents import MockAgent

        analyzer = DiagnosticAnalyzer()

        assert isinstance(analyzer.agent, MockAgent)

    def test_analyze_failures_with_no_failures(self):
        """analyze_failures returns early message when no failures"""
        from startd8.diagnostics import DiagnosticAnalyzer, DiagnosticReport

        analyzer = DiagnosticAnalyzer()
        report = DiagnosticReport(checks=[])  # No failures

        result = analyzer.analyze_failures(report)

        assert "No failures to analyze" in result

    def test_analyze_failures_uses_agent(self):
        """analyze_failures calls agent.generate"""
        from startd8.diagnostics import (
            DiagnosticAnalyzer, DiagnosticReport, HealthCheck,
            HealthStatus, CheckCategory
        )

        mock_agent = MagicMock()
        mock_agent.generate.return_value = ("Analysis result", 100, None)

        analyzer = DiagnosticAnalyzer(agent=mock_agent)

        report = DiagnosticReport(checks=[
            HealthCheck("c1", CheckCategory.AGENTS, HealthStatus.WARNING, "warn"),
        ])

        result = analyzer.analyze_failures(report)

        assert mock_agent.generate.called
        assert "Analysis result" == result


class TestAutoFixer:
    """Tests for AutoFixer"""

    def test_get_available_fixes_empty_for_healthy(self):
        """get_available_fixes returns empty for healthy report"""
        from startd8.diagnostics import (
            AutoFixer, DiagnosticReport, HealthCheck,
            HealthStatus, CheckCategory
        )

        fixer = AutoFixer()
        report = DiagnosticReport(checks=[
            HealthCheck("c1", CheckCategory.AGENTS, HealthStatus.HEALTHY, "ok"),
        ])

        fixes = fixer.get_available_fixes(report)

        assert len(fixes) == 0

    def test_get_available_fixes_finds_fixable(self):
        """get_available_fixes finds checks with fix_hints"""
        from startd8.diagnostics import (
            AutoFixer, DiagnosticReport, HealthCheck,
            HealthStatus, CheckCategory
        )

        fixer = AutoFixer()
        report = DiagnosticReport(checks=[
            HealthCheck(
                "c1", CheckCategory.STORAGE, HealthStatus.WARNING,
                "warn", fix_hint="create_log_directory"
            ),
        ])

        fixes = fixer.get_available_fixes(report)

        assert "create_log_directory" in fixes

    def test_apply_fix_unknown_returns_message(self):
        """apply_fix with unknown hint returns message"""
        from startd8.diagnostics import AutoFixer

        fixer = AutoFixer()
        result = fixer.apply_fix("unknown_fix_that_doesnt_exist")

        assert "No auto-fix available" in result


class TestConvenienceFunctions:
    """Tests for module-level convenience functions"""

    def test_run_diagnostics_function(self):
        """run_diagnostics convenience function works"""
        from startd8.diagnostics import run_diagnostics, DiagnosticReport

        report = run_diagnostics(include_api_checks=False)

        assert isinstance(report, DiagnosticReport)

    def test_analyze_report_function(self):
        """analyze_report convenience function works"""
        from startd8.diagnostics import (
            analyze_report, DiagnosticReport, HealthCheck,
            HealthStatus, CheckCategory
        )

        report = DiagnosticReport(checks=[
            HealthCheck("c1", CheckCategory.AGENTS, HealthStatus.WARNING, "warn"),
        ])

        # Uses MockAgent by default
        result = analyze_report(report)

        assert isinstance(result, str)

    def test_apply_safe_fixes_function(self):
        """apply_safe_fixes convenience function works"""
        from startd8.diagnostics import (
            apply_safe_fixes, DiagnosticReport, HealthCheck,
            HealthStatus, CheckCategory
        )

        report = DiagnosticReport(checks=[
            HealthCheck("c1", CheckCategory.AGENTS, HealthStatus.HEALTHY, "ok"),
        ])

        results = apply_safe_fixes(report)

        assert isinstance(results, list)


class TestAgentChecks:
    """Tests for agent health checks"""

    def test_check_anthropic_api_key_not_set(self):
        """check_anthropic_api_key handles missing key"""
        with patch.dict('os.environ', {}, clear=True):
            from startd8.diagnostics.checks.agent_checks import check_anthropic_api_key
            from startd8.diagnostics import HealthStatus

            result = check_anthropic_api_key()

            assert result.status == HealthStatus.WARNING
            assert "not set" in result.message

    def test_check_anthropic_api_key_set(self):
        """check_anthropic_api_key handles valid key"""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'sk-ant-test123'}):
            from startd8.diagnostics.checks.agent_checks import check_anthropic_api_key
            from startd8.diagnostics import HealthStatus

            result = check_anthropic_api_key()

            assert result.status == HealthStatus.HEALTHY
            assert "configured" in result.message

    def test_check_agent_imports(self):
        """check_agent_imports verifies all agent imports"""
        from startd8.diagnostics.checks.agent_checks import check_agent_imports
        from startd8.diagnostics import HealthStatus

        result = check_agent_imports()

        # Should at least have ClaudeAgent and MockAgent
        assert result.status == HealthStatus.HEALTHY
        assert "ClaudeAgent" in result.details
        assert "MockAgent" in result.details


class TestStorageChecks:
    """Tests for storage health checks"""

    def test_check_disk_space(self):
        """check_disk_space returns valid result"""
        from startd8.diagnostics.checks.storage_checks import check_disk_space
        from startd8.diagnostics import HealthStatus

        result = check_disk_space()

        # Should succeed on any system with disk
        assert result.status in [HealthStatus.HEALTHY, HealthStatus.WARNING, HealthStatus.CRITICAL]
        assert "free_bytes" in result.details

    def test_check_data_dir_permissions(self):
        """check_data_dir_permissions returns valid result"""
        from startd8.diagnostics.checks.storage_checks import check_data_dir_permissions
        from startd8.diagnostics import HealthStatus

        result = check_data_dir_permissions()

        assert result.status in [HealthStatus.HEALTHY, HealthStatus.CRITICAL]


class TestFrameworkChecks:
    """Tests for framework health checks"""

    def test_check_python_environment(self):
        """check_python_environment returns valid result"""
        from startd8.diagnostics.checks.framework_checks import check_python_environment
        from startd8.diagnostics import HealthStatus

        result = check_python_environment()

        assert result.status in [HealthStatus.HEALTHY, HealthStatus.WARNING, HealthStatus.CRITICAL]
        assert "version" in result.details

    def test_check_startd8_import(self):
        """check_startd8_import succeeds"""
        from startd8.diagnostics.checks.framework_checks import check_startd8_import
        from startd8.diagnostics import HealthStatus

        result = check_startd8_import()

        assert result.status == HealthStatus.HEALTHY
        assert "imported successfully" in result.message

    def test_check_dependency_versions(self):
        """check_dependency_versions returns valid result"""
        from startd8.diagnostics.checks.framework_checks import check_dependency_versions
        from startd8.diagnostics import HealthStatus

        result = check_dependency_versions()

        assert result.status in [HealthStatus.HEALTHY, HealthStatus.CRITICAL]
        # Should have checked anthropic at least
        assert "anthropic" in result.details


class TestCostChecks:
    """Tests for cost system checks"""

    def test_check_pricing_coverage(self):
        """check_pricing_coverage returns valid result"""
        from startd8.diagnostics.checks.cost_checks import check_pricing_coverage
        from startd8.diagnostics import HealthStatus

        result = check_pricing_coverage()

        assert result.status in [
            HealthStatus.HEALTHY, HealthStatus.WARNING, HealthStatus.UNKNOWN
        ]

    def test_check_cost_tracking_imports(self):
        """check_cost_tracking_imports returns valid result"""
        from startd8.diagnostics.checks.cost_checks import check_cost_tracking_imports
        from startd8.diagnostics import HealthStatus

        result = check_cost_tracking_imports()

        assert result.status in [HealthStatus.HEALTHY, HealthStatus.CRITICAL]
