# src/startd8/contractors/artisan_phases/final_testing.py
"""
Final Testing Phase: Orchestrates comprehensive testing workflow including pytest,
coverage reporting, ruff linting, structured failure reports, and re-run support.

This module is self-contained (no relative imports) and handles tool invocation
via subprocess, making it resilient to missing dependencies.

Usage:
    from startd8.contractors.artisan_phases.final_testing import (
        FinalTestingPhase,
        FinalTestingConfig,
    )

    config = FinalTestingConfig(
        project_root=Path("/path/to/project"),
        coverage_threshold=80.0,
    )
    phase = FinalTestingPhase(config)
    report = phase.execute_with_reruns()

    print(report.to_json())
    print(report.summary)
"""

from __future__ import annotations

import datetime
import enum
import json
import logging
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ============================================================================
# ENUMS
# ============================================================================


class PhaseStatus(enum.Enum):
    """Enumeration of phase execution statuses."""

    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


class StepName(enum.Enum):
    """Named steps in the final testing phase."""

    RUFF_LINT = "ruff_lint"
    PYTEST_RUN = "pytest_run"
    COVERAGE_PARSE = "coverage_parse"
    REPORT_BUILD = "report_build"


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class LintViolation:
    """Represents a single linting violation from ruff."""

    file: str
    line: int
    column: int
    rule: str
    message: str
    severity: str = "warning"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "rule": self.rule,
            "message": self.message,
            "severity": self.severity,
        }


@dataclass
class FailureDetail:
    """Represents details of a single test failure."""

    node_id: str  # e.g., "tests/test_foo.py::test_bar"
    test_name: str
    file: str
    line: Optional[int]
    message: str
    traceback: str
    duration: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "node_id": self.node_id,
            "test_name": self.test_name,
            "file": self.file,
            "line": self.line,
            "message": self.message,
            "traceback": self.traceback,
            "duration": self.duration,
        }


@dataclass
class TestSuiteResult:
    """Aggregated results from pytest execution."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    duration_seconds: float = 0.0
    failures: List[FailureDetail] = field(default_factory=list)
    raw_exit_code: int = 0
    raw_stdout: str = ""
    raw_stderr: str = ""

    @property
    def success(self) -> bool:
        """True if no failures or errors."""
        return self.failed == 0 and self.errors == 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
            "skipped": self.skipped,
            "duration_seconds": self.duration_seconds,
            "failures": [f.to_dict() for f in self.failures],
            "raw_exit_code": self.raw_exit_code,
            "success": self.success,
        }


@dataclass
class CoverageReport:
    """Coverage metrics collected during test run."""

    total_statements: int = 0
    covered_statements: int = 0
    missing_statements: int = 0
    coverage_percent: float = 0.0
    file_coverage: Dict[str, float] = field(default_factory=dict)
    meets_threshold: bool = False
    threshold: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "total_statements": self.total_statements,
            "covered_statements": self.covered_statements,
            "missing_statements": self.missing_statements,
            "coverage_percent": self.coverage_percent,
            "file_coverage": dict(self.file_coverage),
            "meets_threshold": self.meets_threshold,
            "threshold": self.threshold,
        }


@dataclass
class StepResult:
    """Result of a single phase step (ruff, pytest, coverage parse, report)."""

    step: str
    status: PhaseStatus
    duration_seconds: float = 0.0
    detail: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "step": self.step,
            "status": self.status.value,
            "duration_seconds": round(self.duration_seconds, 4),
            "detail": self.detail,
        }


@dataclass
class FinalTestingReport:
    """Complete report for the final testing phase."""

    phase_name: str = "final_testing"
    status: PhaseStatus = PhaseStatus.PASSED
    is_rerun: bool = False
    rerun_attempt: int = 0
    timestamp: str = ""  # ISO 8601 format
    steps: List[StepResult] = field(default_factory=list)
    test_results: Optional[TestSuiteResult] = None
    coverage: Optional[CoverageReport] = None
    lint_violations: List[LintViolation] = field(default_factory=list)
    lint_violation_count: int = 0
    failed_test_node_ids: List[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to fully JSON-serializable dictionary."""
        return {
            "phase_name": self.phase_name,
            "status": self.status.value,
            "is_rerun": self.is_rerun,
            "rerun_attempt": self.rerun_attempt,
            "timestamp": self.timestamp,
            "steps": [s.to_dict() for s in self.steps],
            "test_results": self.test_results.to_dict() if self.test_results else None,
            "coverage": self.coverage.to_dict() if self.coverage else None,
            "lint_violations": [v.to_dict() for v in self.lint_violations],
            "lint_violation_count": self.lint_violation_count,
            "failed_test_node_ids": list(self.failed_test_node_ids),
            "summary": self.summary,
        }

    def to_json(self, indent: int = 2) -> str:
        """Return JSON string representation of the report."""
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


# ============================================================================
# CONFIGURATION
# ============================================================================


@dataclass
class FinalTestingConfig:
    """
    Configuration for the FinalTestingPhase.

    Attributes:
        project_root: Root directory of the project under test.
        source_dirs: Directories containing source code (for coverage).
        test_dirs: Directories containing test files.
        coverage_threshold: Minimum acceptable coverage percentage.
        extra_pytest_args: Additional arguments passed to pytest.
        extra_ruff_args: Additional arguments passed to ruff.
        max_rerun_attempts: Maximum number of failure re-run attempts.
        pytest_timeout: Timeout for pytest execution in seconds.
        ruff_timeout: Timeout for ruff execution in seconds.
        collect_coverage: Whether to collect coverage metrics.
        run_lint: Whether to run ruff linting.
        json_report_enabled: Whether to use pytest-json-report plugin.
        verbose: Enable verbose output.
        max_output_size: Maximum captured output size before truncation (bytes).
    """

    project_root: Path = field(default_factory=lambda: Path.cwd())
    source_dirs: List[str] = field(default_factory=lambda: ["src"])
    test_dirs: List[str] = field(default_factory=lambda: ["tests"])
    coverage_threshold: float = 80.0
    extra_pytest_args: List[str] = field(default_factory=list)
    extra_ruff_args: List[str] = field(default_factory=list)
    max_rerun_attempts: int = 6
    pytest_timeout: int = 300
    ruff_timeout: int = 60
    collect_coverage: bool = True
    run_lint: bool = True
    json_report_enabled: bool = True
    verbose: bool = False
    max_output_size: int = 102400  # 100 KB

    def __post_init__(self) -> None:
        """Normalize project_root to Path object and validate config."""
        self.project_root = Path(self.project_root)
        if self.coverage_threshold < 0:
            self.coverage_threshold = 0.0
        elif self.coverage_threshold > 100:
            self.coverage_threshold = 100.0
        if self.max_rerun_attempts < 0:
            self.max_rerun_attempts = 0
        if self.pytest_timeout < 1:
            self.pytest_timeout = 1
        if self.ruff_timeout < 1:
            self.ruff_timeout = 1


# ============================================================================
# CONSTANTS AND REGEX PATTERNS
# ============================================================================

# Pytest summary line: "====== 3 passed, 1 failed in 4.56s ======"
_PYTEST_SUMMARY_RE = re.compile(
    r"=+\s*(.*?)\s+in\s+[\d.]+s\s*=+",
    re.MULTILINE,
)

# Individual test count tokens
_COUNT_RE = re.compile(r"(\d+)\s+(passed|failed|error(?:s|ed)?|skipped|warning(?:s)?)")

# Pytest FAILED line: "FAILED tests/test_x.py::test_y - AssertionError: ..."
_FAILURE_HEADER_RE = re.compile(
    r"^FAILED\s+(.*?)(?:\s*-\s*(.*?))?$",
    re.MULTILINE,
)

# Sentinel exit codes used by _run_command
_EXIT_TIMEOUT = -1
_EXIT_NOT_FOUND = -2
_EXIT_OTHER_ERROR = -3


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def _iso_timestamp() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _truncate_string(s: str, max_len: int = 102400) -> str:
    """Truncate a string to max_len, adding ellipsis marker if truncated."""
    if len(s) <= max_len:
        return s
    return s[: max_len - 20] + "\n... [truncated] ..."


# ============================================================================
# MAIN PHASE CLASS
# ============================================================================


class FinalTestingPhase:
    """
    Orchestrates the final testing phase: linting, pytest, coverage, and reporting.

    This class drives a multi-step quality-assurance workflow:
    1. **Ruff linting** – static analysis for style/bug violations.
    2. **Pytest execution** – full or targeted test suite run with coverage.
    3. **Coverage parsing** – extract and evaluate coverage metrics.
    4. **Report assembly** – produce a structured ``FinalTestingReport``.

    Re-run support allows automatic retrying of failed tests up to a
    configurable number of attempts.
    """

    def __init__(self, config: Optional[FinalTestingConfig] = None) -> None:
        """
        Initialize the phase with optional configuration.

        Args:
            config: Phase configuration. Uses defaults if not provided.
        """
        self.config = config or FinalTestingConfig()
        self.logger = logging.getLogger("startd8.final_testing")
        self._last_report: Optional[FinalTestingReport] = None

    # ========================================================================
    # PUBLIC API
    # ========================================================================

    def execute(self) -> FinalTestingReport:
        """
        Execute the full final testing phase.

        Steps:
            1. Validate project root exists.
            2. Run ruff linting (if enabled).
            3. Run pytest with coverage (if enabled).
            4. Parse coverage metrics.
            5. Build comprehensive structured report.

        Returns:
            ``FinalTestingReport`` with complete results.
        """
        self.logger.info("Starting final testing phase execution")
        steps: List[StepResult] = []
        test_results: Optional[TestSuiteResult] = None
        coverage: Optional[CoverageReport] = None
        lint_violations: List[LintViolation] = []

        # --- Validate project root ---
        if not self.config.project_root.exists():
            self.logger.error(
                "Project root does not exist: %s", self.config.project_root
            )
            error_report = FinalTestingReport(
                status=PhaseStatus.ERROR,
                timestamp=_iso_timestamp(),
                summary=f"Project root not found: {self.config.project_root}",
            )
            self._last_report = error_report
            return error_report

        # --- Create a single temporary directory for all artifacts ---
        with tempfile.TemporaryDirectory(prefix="startd8_final_testing_") as temp_dir:
            temp_path = Path(temp_dir)

            # Step 1: Ruff linting
            if self.config.run_lint:
                lint_violations, lint_step = self._run_ruff_lint()
                steps.append(lint_step)
                self.logger.info(
                    "Ruff linting complete: %d violation(s) found",
                    len(lint_violations),
                )
            else:
                self.logger.debug("Ruff linting disabled by configuration")

            # Step 2: Pytest execution with coverage
            json_report_path = temp_path / "report.json"
            coverage_json_path = temp_path / "coverage.json"

            test_results, pytest_step = self._run_pytest(
                node_ids=None,
                json_report_path=json_report_path,
                coverage_json_path=coverage_json_path,
            )
            steps.append(pytest_step)
            self.logger.info(
                "Pytest execution complete: %d passed, %d failed, %d errors",
                test_results.passed,
                test_results.failed,
                test_results.errors,
            )

            # Step 3: Parse coverage
            if self.config.collect_coverage and test_results.raw_exit_code in (0, 1, 5):
                coverage, coverage_step = self._parse_coverage(coverage_json_path)
                steps.append(coverage_step)
                self.logger.info(
                    "Coverage parsing complete: %.1f%% (threshold: %.1f%%)",
                    coverage.coverage_percent,
                    coverage.threshold,
                )
            else:
                coverage = CoverageReport(threshold=self.config.coverage_threshold)
                steps.append(
                    StepResult(
                        step=StepName.COVERAGE_PARSE.value,
                        status=PhaseStatus.SKIPPED,
                        detail="Coverage collection disabled or pytest errored",
                    )
                )

            # Step 4: Build report
            report_start = time.monotonic()
            report = self._build_report(
                test_results=test_results,
                coverage=coverage,
                lint_violations=lint_violations,
                steps=steps,
                is_rerun=False,
                rerun_attempt=0,
            )
            report.steps.append(
                StepResult(
                    step=StepName.REPORT_BUILD.value,
                    status=PhaseStatus.PASSED,
                    duration_seconds=time.monotonic() - report_start,
                )
            )

        self.logger.info("Final testing phase complete: %s", report.status.value)
        self._last_report = report
        return report

    def rerun_failures(
        self,
        prior_report: Optional[FinalTestingReport] = None,
        failed_node_ids: Optional[List[str]] = None,
        attempt: int = 1,
    ) -> FinalTestingReport:
        """
        Re-run only the tests that previously failed.

        Args:
            prior_report: A prior ``FinalTestingReport`` to extract
                failed test IDs from.
            failed_node_ids: Explicit list of test node IDs to run
                (overrides prior_report).
            attempt: Which re-run attempt this is (for reporting).

        Returns:
            ``FinalTestingReport`` with re-run results.
        """
        self.logger.info("Starting re-run of failed tests (attempt %d)", attempt)

        # Determine which tests to re-run
        node_ids_to_run: List[str] = []
        if failed_node_ids:
            node_ids_to_run = list(failed_node_ids)
        elif prior_report:
            node_ids_to_run = list(prior_report.failed_test_node_ids)

        if not node_ids_to_run:
            self.logger.info("No failed tests to re-run")
            report = FinalTestingReport(
                status=PhaseStatus.PASSED,
                timestamp=_iso_timestamp(),
                is_rerun=True,
                rerun_attempt=attempt,
                summary="No failed tests to re-run",
            )
            self._last_report = report
            return report

        self.logger.info(
            "Re-running %d previously failed test(s)", len(node_ids_to_run)
        )

        with tempfile.TemporaryDirectory(prefix="startd8_rerun_") as temp_dir:
            temp_path = Path(temp_dir)
            json_report_path = temp_path / "report.json"
            coverage_json_path = temp_path / "coverage.json"

            test_results, pytest_step = self._run_pytest(
                node_ids=node_ids_to_run,
                json_report_path=json_report_path,
                coverage_json_path=coverage_json_path,
            )
            steps: List[StepResult] = [pytest_step]

            # Parse coverage for re-run
            coverage: Optional[CoverageReport] = None
            if self.config.collect_coverage and test_results.raw_exit_code in (0, 1):
                coverage, coverage_step = self._parse_coverage(coverage_json_path)
                steps.append(coverage_step)
            else:
                coverage = CoverageReport(threshold=self.config.coverage_threshold)

            # Build report
            report_start = time.monotonic()
            report = self._build_report(
                test_results=test_results,
                coverage=coverage,
                lint_violations=[],  # Don't re-lint on rerun
                steps=steps,
                is_rerun=True,
                rerun_attempt=attempt,
            )
            report.steps.append(
                StepResult(
                    step=StepName.REPORT_BUILD.value,
                    status=PhaseStatus.PASSED,
                    duration_seconds=time.monotonic() - report_start,
                )
            )

        self.logger.info(
            "Re-run attempt %d complete: %s (%d/%d passed)",
            attempt,
            report.status.value,
            test_results.passed,
            test_results.total,
        )
        self._last_report = report
        return report

    def execute_with_reruns(self) -> FinalTestingReport:
        """
        Execute full testing phase, then automatically re-run failures up to
        ``config.max_rerun_attempts`` times, stopping early if all tests pass.

        Returns:
            Final report (from last re-run, or initial if all passed).
        """
        self.logger.info(
            "Executing with up to %d re-run attempt(s)",
            self.config.max_rerun_attempts,
        )

        report = self.execute()

        for attempt in range(1, self.config.max_rerun_attempts + 1):
            if report.test_results is None or report.test_results.success:
                self.logger.info("All tests passing; no re-runs needed")
                break

            if not report.failed_test_node_ids:
                self.logger.info(
                    "No specific failed node IDs extracted; stopping re-runs"
                )
                break

            self.logger.info(
                "Re-run %d/%d: %d test(s) to retry",
                attempt,
                self.config.max_rerun_attempts,
                len(report.failed_test_node_ids),
            )
            report = self.rerun_failures(prior_report=report, attempt=attempt)

        return report

    @property
    def last_report(self) -> Optional[FinalTestingReport]:
        """Return the most recent report generated by this phase."""
        return self._last_report

    # ========================================================================
    # INTERNAL STEPS
    # ========================================================================

    def _run_ruff_lint(self) -> Tuple[List[LintViolation], StepResult]:
        """
        Execute ruff linting in JSON output format.

        Returns:
            Tuple of (violations list, step result).
        """
        step_start = time.monotonic()
        self.logger.debug("Starting ruff linting")

        cmd: List[str] = [
            "ruff",
            "check",
            str(self.config.project_root),
            "--output-format=json",
        ]
        cmd.extend(self.config.extra_ruff_args)

        exit_code, stdout, stderr, duration = self._run_command(
            cmd,
            self.config.project_root,
            self.config.ruff_timeout,
            self.logger,
        )

        violations: List[LintViolation] = []
        step_status = PhaseStatus.PASSED
        detail: Optional[str] = None

        if exit_code == _EXIT_NOT_FOUND:
            self.logger.warning("ruff command not found; skipping lint check")
            step_status = PhaseStatus.ERROR
            detail = "ruff not installed or not on PATH"
        elif exit_code == _EXIT_TIMEOUT:
            self.logger.error("ruff check timed out")
            step_status = PhaseStatus.ERROR
            detail = f"ruff timed out after {self.config.ruff_timeout}s"
        elif exit_code in (0, 1):
            # 0 = no violations, 1 = violations found
            violations = self._parse_ruff_json_output(stdout)
            if violations:
                detail = f"Found {len(violations)} violation(s)"
            # Lint violations are informational; they don't fail the step
        else:
            self.logger.error("ruff check failed with exit code %d", exit_code)
            step_status = PhaseStatus.ERROR
            detail = f"ruff exited with code {exit_code}: {stderr[:200]}"

        return violations, StepResult(
            step=StepName.RUFF_LINT.value,
            status=step_status,
            duration_seconds=time.monotonic() - step_start,
            detail=detail,
        )

    def _run_pytest(
        self,
        node_ids: Optional[List[str]] = None,
        json_report_path: Optional[Path] = None,
        coverage_json_path: Optional[Path] = None,
    ) -> Tuple[TestSuiteResult, StepResult]:
        """
        Execute pytest with coverage collection.

        Args:
            node_ids: If provided, run only these specific test node IDs.
            json_report_path: Path to write pytest-json-report JSON file.
            coverage_json_path: Path to write coverage.json file.

        Returns:
            Tuple of (test suite result, step result).
        """
        step_start = time.monotonic()
        self.logger.debug("Starting pytest execution")

        if json_report_path is None:
            json_report_path = (
                Path(tempfile.gettempdir()) / f"pytest_report_{os.getpid()}.json"
            )
        if coverage_json_path is None:
            coverage_json_path = (
                Path(tempfile.gettempdir()) / f"coverage_{os.getpid()}.json"
            )

        cmd = self._build_pytest_command(json_report_path, coverage_json_path, node_ids)

        exit_code, stdout, stderr, duration = self._run_command(
            cmd,
            self.config.project_root,
            self.config.pytest_timeout,
            self.logger,
        )

        detail: Optional[str] = None

        if exit_code == _EXIT_NOT_FOUND:
            self.logger.error("pytest command not found")
            test_result = TestSuiteResult(errors=1, raw_exit_code=exit_code)
            step_status = PhaseStatus.ERROR
            detail = "pytest not installed"
        elif exit_code == _EXIT_TIMEOUT:
            self.logger.error("pytest timed out after %ds", self.config.pytest_timeout)
            test_result = TestSuiteResult(errors=1, raw_exit_code=exit_code)
            step_status = PhaseStatus.ERROR
            detail = f"pytest timed out after {self.config.pytest_timeout}s"
        elif exit_code == _EXIT_OTHER_ERROR:
            self.logger.error("pytest execution error: %s", stderr[:200])
            test_result = TestSuiteResult(errors=1, raw_exit_code=exit_code)
            step_status = PhaseStatus.ERROR
            detail = f"Execution error: {stderr[:200]}"
        else:
            # Parse results: try JSON report first, then fall back to stdout
            test_result = self._parse_pytest_json_report(
                json_report_path, stdout, stderr, exit_code, duration
            )
            test_result.raw_exit_code = exit_code
            test_result.raw_stdout = _truncate_string(
                stdout, self.config.max_output_size
            )
            test_result.raw_stderr = _truncate_string(
                stderr, self.config.max_output_size
            )

            if exit_code == 5:
                # Exit code 5 = no tests collected
                self.logger.warning("No tests collected by pytest (exit code 5)")
                detail = "No tests collected"
                step_status = PhaseStatus.PASSED
            elif test_result.failed > 0 or test_result.errors > 0:
                step_status = PhaseStatus.FAILED
                parts = []
                if test_result.failed:
                    parts.append(f"{test_result.failed} failed")
                if test_result.errors:
                    parts.append(f"{test_result.errors} error(s)")
                detail = ", ".join(parts)
            else:
                step_status = PhaseStatus.PASSED

        return test_result, StepResult(
            step=StepName.PYTEST_RUN.value,
            status=step_status,
            duration_seconds=time.monotonic() - step_start,
            detail=detail,
        )

    def _build_pytest_command(
        self,
        json_report_path: Path,
        coverage_json_path: Path,
        node_ids: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Construct pytest command line arguments.

        Args:
            json_report_path: Where to write JSON report.
            coverage_json_path: Where to write coverage JSON.
            node_ids: Specific tests to run (if any).

        Returns:
            List of command arguments.
        """
        cmd: List[str] = ["python", "-m", "pytest"]

        # Test targets: either specific node_ids or test directories
        if node_ids:
            cmd.extend(node_ids)
        else:
            cmd.extend(self.config.test_dirs)

        # Standard arguments
        cmd.extend(["-v", "--tb=short"])

        # JSON report (if enabled and plugin is expected to be available)
        if self.config.json_report_enabled:
            cmd.extend(
                [
                    "--json-report",
                    f"--json-report-file={json_report_path}",
                ]
            )

        # Coverage (if enabled)
        if self.config.collect_coverage:
            for source_dir in self.config.source_dirs:
                cmd.append(f"--cov={source_dir}")
            cmd.extend(
                [
                    f"--cov-report=json:{coverage_json_path}",
                    "--cov-report=term",
                ]
            )

        # Extra user-supplied args
        cmd.extend(self.config.extra_pytest_args)

        self.logger.debug("Pytest command: %s", " ".join(cmd))
        return cmd

    def _parse_pytest_json_report(
        self,
        json_report_path: Path,
        raw_stdout: str,
        raw_stderr: str,
        exit_code: int,
        duration: float,
    ) -> TestSuiteResult:
        """
        Parse pytest-json-report output, with fallback to stdout parsing.

        Args:
            json_report_path: Path to pytest JSON report file.
            raw_stdout: Raw stdout from pytest execution.
            raw_stderr: Raw stderr from pytest execution.
            exit_code: Exit code from pytest.
            duration: Wall-clock duration of pytest execution.

        Returns:
            Parsed ``TestSuiteResult``.
        """
        if json_report_path.exists():
            try:
                with open(json_report_path, encoding="utf-8") as f:
                    report_data = json.load(f)
                return self._extract_from_json_report(report_data, duration)
            except Exception as e:
                self.logger.warning(
                    "Failed to parse pytest-json-report (%s); using stdout fallback",
                    e,
                )

        self.logger.debug(
            "pytest-json-report not available; using stdout fallback parsing"
        )
        return self._parse_pytest_stdout_fallback(
            raw_stdout, raw_stderr, exit_code, duration
        )

    def _extract_from_json_report(
        self, report_data: Dict[str, Any], fallback_duration: float
    ) -> TestSuiteResult:
        """
        Extract test results from parsed pytest-json-report data.

        Args:
            report_data: Parsed JSON report dictionary.
            fallback_duration: Duration to use if not in report.

        Returns:
            ``TestSuiteResult`` populated from JSON data.
        """
        summary = report_data.get("summary", {})
        total = summary.get("total", 0)
        passed = summary.get("passed", 0)
        failed = summary.get("failed", 0)
        errors = summary.get("error", 0)
        skipped = summary.get("skipped", 0)
        duration_seconds = summary.get("duration", fallback_duration)

        # Parse failure details
        failures: List[FailureDetail] = []
        for test in report_data.get("tests", []):
            outcome = test.get("outcome", "")
            if outcome not in ("failed", "error"):
                continue

            call = test.get("call", {})
            longrepr = call.get("longrepr", "")
            node_id = test.get("nodeid", "unknown")

            # Decompose node_id: "tests/test_x.py::TestClass::test_method"
            parts = node_id.split("::")
            test_name = parts[-1] if len(parts) > 1 else node_id
            file_part = parts[0] if parts else node_id

            # Attempt to extract line number from lineno field
            line_num = test.get("lineno")

            failures.append(
                FailureDetail(
                    node_id=node_id,
                    test_name=test_name,
                    file=file_part,
                    line=line_num,
                    message=str(longrepr)[:200],
                    traceback=_truncate_string(str(longrepr), 500),
                    duration=call.get("duration"),
                )
            )

        return TestSuiteResult(
            total=total,
            passed=passed,
            failed=failed,
            errors=errors,
            skipped=skipped,
            duration_seconds=duration_seconds,
            failures=failures,
        )

    def _parse_pytest_stdout_fallback(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
        duration: float,
    ) -> TestSuiteResult:
        """
        Regex-based fallback parsing of pytest terminal output.

        Args:
            stdout: Pytest stdout.
            stderr: Pytest stderr.
            exit_code: Exit code.
            duration: Execution duration.

        Returns:
            Parsed ``TestSuiteResult``.
        """
        self.logger.debug("Parsing pytest output with regex fallback")

        passed = failed = errors = skipped = 0

        summary_match = _PYTEST_SUMMARY_RE.search(stdout)
        if summary_match:
            summary_text = summary_match.group(1)
            for count_match in _COUNT_RE.finditer(summary_text):
                count = int(count_match.group(1))
                label = count_match.group(2).lower()
                if "passed" in label:
                    passed = count
                elif "failed" in label:
                    failed = count
                elif "error" in label:
                    errors = count
                elif "skipped" in label:
                    skipped = count
        else:
            self.logger.debug("Could not parse pytest summary line from output")

        total = passed + failed + errors + skipped

        # Extract failure details from "FAILED ..." lines
        failures: List[FailureDetail] = []
        for failure_match in _FAILURE_HEADER_RE.finditer(stdout):
            node_id = failure_match.group(1).strip()
            message = (failure_match.group(2) or "").strip()

            if "::" in node_id:
                parts = node_id.split("::")
                file_part = parts[0]
                test_name = parts[-1]
            else:
                file_part = node_id
                test_name = "unknown"

            failures.append(
                FailureDetail(
                    node_id=node_id,
                    test_name=test_name,
                    file=file_part,
                    line=None,
                    message=message[:200],
                    traceback="",  # Not available in fallback mode
                )
            )

        return TestSuiteResult(
            total=total,
            passed=passed,
            failed=failed,
            errors=errors,
            skipped=skipped,
            duration_seconds=duration,
            failures=failures,
        )

    def _parse_coverage(
        self, coverage_json_path: Path
    ) -> Tuple[CoverageReport, StepResult]:
        """
        Parse coverage.json into ``CoverageReport``.

        Args:
            coverage_json_path: Path to coverage.json file.

        Returns:
            Tuple of (coverage report, step result).
        """
        step_start = time.monotonic()
        self.logger.debug("Parsing coverage metrics")

        coverage = CoverageReport(threshold=self.config.coverage_threshold)
        step_status = PhaseStatus.PASSED
        detail: Optional[str] = None

        if not coverage_json_path.exists():
            self.logger.warning("Coverage JSON file not found: %s", coverage_json_path)
            step_status = PhaseStatus.ERROR
            detail = "coverage.json not found (pytest-cov may not be installed)"
        else:
            try:
                with open(coverage_json_path, encoding="utf-8") as f:
                    coverage_data = json.load(f)

                totals = coverage_data.get("totals", {})
                coverage.total_statements = totals.get("num_statements", 0)
                coverage.covered_statements = totals.get("covered_lines", 0)
                coverage.missing_statements = (
                    coverage.total_statements - coverage.covered_statements
                )

                if coverage.total_statements > 0:
                    coverage.coverage_percent = round(
                        (coverage.covered_statements / coverage.total_statements) * 100,
                        2,
                    )
                else:
                    coverage.coverage_percent = 0.0

                # Per-file coverage
                for file_path, file_data in coverage_data.get("files", {}).items():
                    file_summary = file_data.get("summary", {})
                    file_total = file_summary.get("num_statements", 0)
                    file_covered = file_summary.get("covered_lines", 0)
                    if file_total > 0:
                        coverage.file_coverage[file_path] = round(
                            (file_covered / file_total) * 100, 2
                        )

                coverage.meets_threshold = (
                    coverage.coverage_percent >= coverage.threshold
                )

                detail = f"{coverage.coverage_percent:.1f}% coverage"
                if not coverage.meets_threshold:
                    detail += f" (below threshold {coverage.threshold:.1f}%)"

            except Exception as e:
                self.logger.error("Failed to parse coverage.json: %s", e)
                step_status = PhaseStatus.ERROR
                detail = f"Error parsing coverage: {str(e)[:200]}"

        return coverage, StepResult(
            step=StepName.COVERAGE_PARSE.value,
            status=step_status,
            duration_seconds=time.monotonic() - step_start,
            detail=detail,
        )

    def _parse_ruff_json_output(self, stdout: str) -> List[LintViolation]:
        """
        Parse ruff JSON output into list of violations.

        Args:
            stdout: JSON output from ``ruff check --output-format=json``.

        Returns:
            List of ``LintViolation`` objects.
        """
        violations: List[LintViolation] = []

        if not stdout.strip():
            return violations

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as e:
            self.logger.warning("Failed to parse ruff JSON output: %s", e)
            return violations

        if not isinstance(data, list):
            self.logger.warning(
                "Expected ruff JSON output to be a list, got %s", type(data).__name__
            )
            return violations

        for item in data:
            try:
                location = item.get("location", {})
                violations.append(
                    LintViolation(
                        file=item.get("filename", "unknown"),
                        line=location.get("row", 0),
                        column=location.get("column", 0),
                        rule=item.get("code", "unknown"),
                        message=item.get("message", ""),
                        severity=str(item.get("severity", "warning")).lower(),
                    )
                )
            except Exception as e:
                self.logger.debug("Error parsing individual ruff violation: %s", e)

        return violations

    # ========================================================================
    # REPORT BUILDING
    # ========================================================================

    def _build_report(
        self,
        test_results: Optional[TestSuiteResult],
        coverage: Optional[CoverageReport],
        lint_violations: List[LintViolation],
        steps: List[StepResult],
        is_rerun: bool = False,
        rerun_attempt: int = 0,
    ) -> FinalTestingReport:
        """
        Assemble the final structured report from all phase outputs.

        Args:
            test_results: Results from pytest execution.
            coverage: Coverage metrics.
            lint_violations: List of linting violations.
            steps: List of step results.
            is_rerun: Whether this is a re-run.
            rerun_attempt: Re-run attempt number.

        Returns:
            Complete ``FinalTestingReport``.
        """
        failed_node_ids: List[str] = []
        if test_results and test_results.failures:
            failed_node_ids = [f.node_id for f in test_results.failures]

        overall_status = self._determine_overall_status(test_results, coverage, steps)

        report = FinalTestingReport(
            phase_name="final_testing",
            status=overall_status,
            is_rerun=is_rerun,
            rerun_attempt=rerun_attempt,
            timestamp=_iso_timestamp(),
            steps=list(steps),
            test_results=test_results,
            coverage=coverage,
            lint_violations=list(lint_violations),
            lint_violation_count=len(lint_violations),
            failed_test_node_ids=failed_node_ids,
        )
        report.summary = self._generate_summary(report)
        return report

    @staticmethod
    def _determine_overall_status(
        test_results: Optional[TestSuiteResult],
        coverage: Optional[CoverageReport],
        steps: List[StepResult],
    ) -> PhaseStatus:
        """
        Determine overall phase status based on all components.

        Rules (evaluated in order):
            1. ERROR if any step has ERROR status.
            2. FAILED if tests failed or coverage is below threshold.
            3. PASSED otherwise.

        Note: Lint violations are informational and do not cause FAILED status.

        Args:
            test_results: Pytest results.
            coverage: Coverage metrics.
            steps: Step results.

        Returns:
            Overall ``PhaseStatus``.
        """
        # Check for step-level errors
        if any(step.status == PhaseStatus.ERROR for step in steps):
            return PhaseStatus.ERROR

        # Check test failures
        if test_results and (test_results.failed > 0 or test_results.errors > 0):
            return PhaseStatus.FAILED

        # Check coverage threshold (only when there are statements to cover)
        if coverage and coverage.total_statements > 0 and not coverage.meets_threshold:
            return PhaseStatus.FAILED

        return PhaseStatus.PASSED

    @staticmethod
    def _generate_summary(report: FinalTestingReport) -> str:
        """
        Generate a human-readable summary of the report.

        Args:
            report: The ``FinalTestingReport``.

        Returns:
            Summary string.
        """
        parts: List[str] = []

        # Test summary
        if report.test_results:
            tr = report.test_results
            test_summary = f"{tr.passed}/{tr.total} tests passed"
            if tr.failed > 0:
                test_summary += f", {tr.failed} failed"
            if tr.errors > 0:
                test_summary += f", {tr.errors} error(s)"
            if tr.skipped > 0:
                test_summary += f", {tr.skipped} skipped"
            parts.append(test_summary)

        # Coverage summary
        if report.coverage and report.coverage.total_statements > 0:
            cov = report.coverage
            cov_text = f"Coverage: {cov.coverage_percent:.1f}%"
            cov_text += f" (threshold: {cov.threshold:.1f}%)"
            if not cov.meets_threshold:
                cov_text += " [BELOW THRESHOLD]"
            parts.append(cov_text)

        # Lint summary
        if report.lint_violation_count > 0:
            parts.append(f"Lint: {report.lint_violation_count} violation(s)")

        # Re-run note
        if report.is_rerun:
            parts.append(f"(re-run attempt {report.rerun_attempt})")

        status_label = report.status.value.upper()
        return f"{status_label}: {', '.join(parts)}" if parts else status_label

    # ========================================================================
    # UTILITY METHODS
    # ========================================================================

    @staticmethod
    def _run_command(
        cmd: List[str],
        cwd: Path,
        timeout: int,
        logger: logging.Logger,
    ) -> Tuple[int, str, str, float]:
        """
        Run a subprocess command, capturing output and timing.

        Args:
            cmd: Command as list of arguments (no shell).
            cwd: Working directory.
            timeout: Timeout in seconds.
            logger: Logger for diagnostics.

        Returns:
            Tuple of ``(exit_code, stdout, stderr, duration_seconds)``.

            Special exit codes:
            - ``-1``: Timeout
            - ``-2``: ``FileNotFoundError`` (command not found)
            - ``-3``: Other exception
            - ``>= 0``: Actual process exit code
        """
        logger.debug("Running: %s", " ".join(cmd))
        start_time = time.monotonic()

        try:
            result = subprocess.run(
                cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
                errors="replace",
            )
            duration = time.monotonic() - start_time
            return result.returncode, result.stdout, result.stderr, duration

        except subprocess.TimeoutExpired:
            duration = time.monotonic() - start_time
            logger.error("Command timed out after %ds: %s", timeout, cmd[0])
            return _EXIT_TIMEOUT, "", f"Timeout after {timeout}s", duration

        except FileNotFoundError:
            duration = time.monotonic() - start_time
            logger.error("Command not found: %s", cmd[0])
            return _EXIT_NOT_FOUND, "", f"Command not found: {cmd[0]}", duration

        except KeyboardInterrupt:
            duration = time.monotonic() - start_time
            logger.error("Command interrupted by user")
            return _EXIT_OTHER_ERROR, "", "Interrupted by user", duration

        except Exception as e:
            duration = time.monotonic() - start_time
            logger.error("Unexpected error running command: %s", e)
            return _EXIT_OTHER_ERROR, "", str(e), duration
