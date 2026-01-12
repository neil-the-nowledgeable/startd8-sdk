"""
Diagnostic runner that orchestrates all health checks.

The DiagnosticRunner collects and executes health checks from all categories,
producing a comprehensive DiagnosticReport.
"""

import time
from datetime import datetime
from typing import Any, List, Optional

from .models import (
    CheckCategory,
    DiagnosticReport,
    HealthCheck,
    HealthStatus,
)
from .checks import (
    get_all_checks,
    get_checks_by_category,
    get_quick_checks,
    CheckDefinition,
)


class DiagnosticRunner:
    """
    Orchestrates diagnostic checks and produces reports.

    Example:
        # Run all diagnostics
        runner = DiagnosticRunner()
        report = runner.run_all()

        # Run with framework context
        runner = DiagnosticRunner(framework=my_framework)
        report = runner.run_all()

        # Run only quick checks (no API calls)
        report = runner.run_quick()

        # Run specific category
        report = runner.run_category(CheckCategory.AGENTS)
    """

    def __init__(self, framework: Optional[Any] = None):
        """
        Initialize the diagnostic runner.

        Args:
            framework: Optional AgentFramework for framework-aware checks.
                       When provided, resilience settings control diagnostic behavior.
        """
        self.framework = framework

    def _is_enabled(self) -> bool:
        """Check if diagnostics are enabled via resilience config."""
        if self.framework and hasattr(self.framework, 'should_run_diagnostics'):
            return self.framework.should_run_diagnostics()
        return True  # Default to enabled if no framework

    def _should_include_api_checks(self) -> bool:
        """Get include_api_checks setting from resilience config."""
        if self.framework and hasattr(self.framework, 'resilience_config'):
            config = self.framework.resilience_config
            if config and config.diagnostics:
                return config.diagnostics.include_api_checks
        return False  # Default to False if no framework config

    def run_all(self, include_api_checks: Optional[bool] = None) -> DiagnosticReport:
        """
        Run all diagnostic checks.

        Args:
            include_api_checks: Include checks that make real API calls.
                               If None, uses framework's resilience config setting.
                               If no framework, defaults to True.

        Returns:
            DiagnosticReport with all check results
        """
        # Check if diagnostics are disabled
        if not self._is_enabled():
            return DiagnosticReport(
                checks=[
                    HealthCheck(
                        name="diagnostics_disabled",
                        category=CheckCategory.FRAMEWORK,
                        status=HealthStatus.SKIPPED,
                        message="Diagnostics disabled in resilience configuration",
                    )
                ],
                generated_at=datetime.utcnow(),
            )

        # Determine include_api_checks setting
        if include_api_checks is None:
            include_api_checks = self._should_include_api_checks()
            # Default to True if no framework config
            if self.framework is None:
                include_api_checks = True

        if include_api_checks:
            checks = get_all_checks()
        else:
            checks = get_quick_checks()

        return self._run_checks(checks)

    def run_quick(self) -> DiagnosticReport:
        """
        Run only quick checks (no API calls).

        Returns:
            DiagnosticReport with quick check results
        """
        return self._run_checks(get_quick_checks())

    def run_category(self, category: CheckCategory) -> DiagnosticReport:
        """
        Run checks for a specific category.

        Args:
            category: Category to run checks for

        Returns:
            DiagnosticReport with category check results
        """
        checks = get_checks_by_category(category)
        return self._run_checks(checks)

    def run_single(self, check_name: str) -> DiagnosticReport:
        """
        Run a single check by name.

        Args:
            check_name: Name of the check to run

        Returns:
            DiagnosticReport with single check result
        """
        from .checks import get_check

        check_def = get_check(check_name)
        if not check_def:
            # Return report with error
            error_check = HealthCheck(
                name=check_name,
                category=CheckCategory.FRAMEWORK,
                status=HealthStatus.UNKNOWN,
                message=f"Check not found: {check_name}",
            )
            return DiagnosticReport(checks=[error_check])

        return self._run_checks([check_def])

    def _run_checks(self, check_defs: List[CheckDefinition]) -> DiagnosticReport:
        """
        Execute a list of check definitions and return a report.

        Args:
            check_defs: List of check definitions to run

        Returns:
            DiagnosticReport with results
        """
        results: List[HealthCheck] = []

        for check_def in check_defs:
            result = self._run_single_check(check_def)
            results.append(result)

        return DiagnosticReport(
            checks=results,
            generated_at=datetime.utcnow(),
        )

    def _run_single_check(self, check_def: CheckDefinition) -> HealthCheck:
        """
        Execute a single check definition.

        Args:
            check_def: Check definition to run

        Returns:
            HealthCheck result
        """
        start = time.time()

        try:
            # Determine if we need to pass framework
            if check_def.requires_framework:
                if self.framework is None:
                    return HealthCheck(
                        name=check_def.name,
                        category=check_def.category,
                        status=HealthStatus.SKIPPED,
                        message="Skipped: Requires framework but none provided",
                        duration_ms=(time.time() - start) * 1000,
                    )
                result = check_def.check_func(framework=self.framework)
            else:
                result = check_def.check_func()

            return result

        except Exception as e:
            return HealthCheck(
                name=check_def.name,
                category=check_def.category,
                status=HealthStatus.UNKNOWN,
                message=f"Check failed with exception: {type(e).__name__}: {e}",
                details={"exception": str(e)},
                duration_ms=(time.time() - start) * 1000,
            )


def run_diagnostics(
    framework: Optional[Any] = None,
    include_api_checks: Optional[bool] = None,
) -> DiagnosticReport:
    """
    Convenience function to run all diagnostics.

    Args:
        framework: Optional AgentFramework for framework-aware checks.
                   When provided, uses resilience config for settings.
        include_api_checks: Include checks that make real API calls.
                           If None, uses framework's resilience config setting.
                           If no framework, defaults to True.

    Returns:
        DiagnosticReport with all check results

    Example:
        # With framework (uses resilience config)
        report = run_diagnostics(framework=my_framework)

        # Without framework (defaults to True for API checks)
        report = run_diagnostics()

        # Explicit override
        report = run_diagnostics(include_api_checks=False)

        if report.has_critical():
            print("Critical issues found!")
            for check in report.get_failures():
                print(f"  - {check.name}: {check.message}")
    """
    runner = DiagnosticRunner(framework=framework)
    return runner.run_all(include_api_checks=include_api_checks)
