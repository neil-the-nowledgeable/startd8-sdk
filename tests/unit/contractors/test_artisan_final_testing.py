"""
Comprehensive unit tests for the Final Testing Artisan.

This module tests the Final Testing artisan/contractor functionality,
which is responsible for: running pytest execution, integrating ruff
(linter/formatter), formatting failure output, enforcing coverage
thresholds (>80%), and reporting coverage results.

All tests use mocking to avoid actual subprocess calls.

Test Classes:
    - TestPytestExecution: Tests for pytest runner and output parsing
    - TestRuffIntegration: Tests for ruff linter integration and JSON parsing
    - TestFailureFormatting: Tests for human-readable failure output formatting
    - TestCoverageThreshold: Tests for coverage threshold enforcement (>80%)
    - TestCoverageReporting: Tests for coverage output parsing and reporting
    - TestFinalTestingEndToEnd: Integration tests for the full check pipeline
"""

import dataclasses
import enum
import json
import re
import subprocess
from typing import List, Optional
from unittest.mock import patch

import pytest


# ============================================================================
# PRODUCTION CLASSES (System Under Test)
# ============================================================================


class TestStatus(enum.Enum):
    """Enum for pytest execution status."""

    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


class LintStatus(enum.Enum):
    """Enum for ruff linting status."""

    CLEAN = "clean"
    VIOLATIONS_FOUND = "violations_found"
    ERROR = "error"


@dataclasses.dataclass
class FailureDetail:
    """Details of a single test or lint failure.

    Attributes:
        file_path: Path to the file containing the failure.
        line_number: Line number of the failure (0 if unknown).
        error_message: Human-readable error description.
        context: Optional additional context (e.g., suggested fix).
    """

    file_path: str
    line_number: int
    error_message: str
    context: str = ""


@dataclasses.dataclass
class TestResult:
    """Structured result from pytest execution.

    Attributes:
        status: Overall test run status.
        passed: Number of passing tests.
        failed: Number of failing tests.
        errors: Number of test errors (collection errors, etc.).
        total: Total number of tests (passed + failed + errors).
        failures: List of individual failure details.
        output: Raw combined stdout/stderr output.
    """

    status: TestStatus
    passed: int
    failed: int
    errors: int
    total: int
    failures: List[FailureDetail]
    output: str = ""


@dataclasses.dataclass
class LintResult:
    """Structured result from ruff linting.

    Attributes:
        status: Overall lint status.
        violations: List of individual violation details.
        output: Raw output from ruff.
    """

    status: LintStatus
    violations: List[FailureDetail]
    output: str = ""


@dataclasses.dataclass
class CoverageResult:
    """Structured result from coverage check.

    Attributes:
        percentage: Coverage percentage (0.0-100.0).
        threshold: Required minimum coverage threshold.
        meets_threshold: Whether coverage strictly exceeds the threshold.
        output: Raw coverage output.
    """

    percentage: float
    threshold: float
    meets_threshold: bool
    output: str = ""


class FinalTestingArtisan:
    """
    Artisan for running final testing checks: pytest, ruff, coverage.

    This class orchestrates external tools (pytest, ruff, coverage.py) and
    parses their output into structured results. It provides methods for
    running individual checks or all checks together.

    Attributes:
        project_path: Root path of the project under test.
        coverage_threshold: Minimum required coverage percentage (exclusive).
    """

    def __init__(
        self, project_path: str = ".", coverage_threshold: float = 80.0
    ) -> None:
        """Initialize the FinalTestingArtisan.

        Args:
            project_path: Root path of the project (default: current directory).
            coverage_threshold: Minimum required coverage percentage.
                Coverage must strictly exceed this value (>80, not >=80).
        """
        self.project_path = project_path
        self.coverage_threshold = coverage_threshold

    def run_pytest(
        self,
        test_path: Optional[str] = None,
        extra_args: Optional[List[str]] = None,
    ) -> TestResult:
        """Run pytest and return structured results.

        Args:
            test_path: Optional path to specific test file or directory.
            extra_args: Optional list of extra arguments to pass to pytest.

        Returns:
            TestResult with status, counts, and failure details.
        """
        cmd = ["python", "-m", "pytest"]
        if test_path:
            cmd.append(test_path)
        if extra_args:
            cmd.extend(extra_args)
        cmd.extend(["--tb=short", "-q"])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.project_path,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            return TestResult(
                status=TestStatus.ERROR,
                passed=0,
                failed=0,
                errors=1,
                total=0,
                failures=[
                    FailureDetail(
                        file_path="",
                        line_number=0,
                        error_message="Pytest execution timed out",
                    )
                ],
                output="Timeout expired",
            )
        except FileNotFoundError:
            return TestResult(
                status=TestStatus.ERROR,
                passed=0,
                failed=0,
                errors=1,
                total=0,
                failures=[
                    FailureDetail(
                        file_path="",
                        line_number=0,
                        error_message="Pytest not found",
                    )
                ],
                output="pytest not found",
            )

        return self._parse_pytest_output(result)

    def _parse_pytest_output(
        self, result: subprocess.CompletedProcess
    ) -> TestResult:
        """Parse pytest output into structured TestResult.

        Extracts pass/fail/error counts from the summary line and parses
        individual failure details from FAILED lines.

        Args:
            result: CompletedProcess from pytest subprocess call.

        Returns:
            TestResult with parsed counts and failures.
        """
        output = result.stdout + result.stderr
        failures: List[FailureDetail] = []
        passed = failed = errors = 0

        # Parse summary line like "5 passed, 2 failed, 1 error"
        summary_match = re.search(r"(\d+)\s+passed", output)
        if summary_match:
            passed = int(summary_match.group(1))

        failed_match = re.search(r"(\d+)\s+failed", output)
        if failed_match:
            failed = int(failed_match.group(1))

        error_match = re.search(r"(\d+)\s+error", output)
        if error_match:
            errors = int(error_match.group(1))

        # Parse FAILED lines like "FAILED tests/test_foo.py::test_bar - ..."
        failure_pattern = re.compile(
            r"FAILED\s+([\w/\\.]+)::(\w+)(?:\s*-\s*(.+))?"
        )
        for match in failure_pattern.finditer(output):
            file_path = match.group(1)
            test_name = match.group(2)
            error_msg = match.group(3) or "Test failed"
            failures.append(
                FailureDetail(
                    file_path=file_path,
                    line_number=0,
                    error_message=f"{test_name}: {error_msg}",
                )
            )

        total = passed + failed + errors

        if result.returncode == 0:
            status = TestStatus.PASSED
        elif failed > 0:
            status = TestStatus.FAILED
        else:
            status = TestStatus.ERROR

        return TestResult(
            status=status,
            passed=passed,
            failed=failed,
            errors=errors,
            total=total,
            failures=failures,
            output=output,
        )

    def run_ruff(self, check_only: bool = True) -> LintResult:
        """Run ruff linter and return structured results.

        Args:
            check_only: If True, only check (don't fix). If False, apply fixes.

        Returns:
            LintResult with status and violations.
        """
        cmd = ["ruff", "check", self.project_path]
        if not check_only:
            cmd.append("--fix")
        cmd.append("--output-format=json")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            return LintResult(
                status=LintStatus.ERROR,
                violations=[],
                output="Ruff execution timed out",
            )
        except FileNotFoundError:
            return LintResult(
                status=LintStatus.ERROR,
                violations=[],
                output="Ruff not found",
            )

        return self._parse_ruff_output(result)

    def _parse_ruff_output(
        self, result: subprocess.CompletedProcess
    ) -> LintResult:
        """Parse ruff JSON output into structured LintResult.

        Args:
            result: CompletedProcess from ruff subprocess call.

        Returns:
            LintResult with status and violation details.
        """
        violations: List[FailureDetail] = []
        output = result.stdout

        try:
            if output.strip():
                items = json.loads(output)
                for item in items:
                    fix_msg = ""
                    if item.get("fix"):
                        fix_msg = item["fix"].get("message", "")
                    violations.append(
                        FailureDetail(
                            file_path=item.get("filename", ""),
                            line_number=item.get("location", {}).get("row", 0),
                            error_message=(
                                f"{item.get('code', 'UNKNOWN')}: "
                                f"{item.get('message', '')}"
                            ),
                            context=fix_msg,
                        )
                    )
        except (json.JSONDecodeError, KeyError, TypeError):
            if result.returncode != 0:
                return LintResult(
                    status=LintStatus.ERROR,
                    violations=[],
                    output=output + result.stderr,
                )

        if not violations:
            status = LintStatus.CLEAN
        else:
            status = LintStatus.VIOLATIONS_FOUND

        return LintResult(
            status=status,
            violations=violations,
            output=output,
        )

    def check_coverage(
        self, test_path: Optional[str] = None
    ) -> CoverageResult:
        """Run pytest with coverage and check against threshold.

        Args:
            test_path: Optional path to specific tests.

        Returns:
            CoverageResult with percentage and threshold check.
        """
        cmd = [
            "python",
            "-m",
            "pytest",
            f"--cov={self.project_path}",
            "--cov-report=term-missing",
        ]
        if test_path:
            cmd.append(test_path)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.project_path,
                timeout=300,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            return CoverageResult(
                percentage=0.0,
                threshold=self.coverage_threshold,
                meets_threshold=False,
                output=str(exc),
            )

        return self._parse_coverage_output(result)

    def _parse_coverage_output(
        self, result: subprocess.CompletedProcess
    ) -> CoverageResult:
        """Parse coverage output to extract percentage.

        Looks for the TOTAL line in coverage report output and extracts
        the percentage value.

        Args:
            result: CompletedProcess from coverage subprocess call.

        Returns:
            CoverageResult with parsed percentage and threshold check.
        """
        output = result.stdout + result.stderr
        percentage = 0.0

        # Look for TOTAL line like "TOTAL    1000    200    80%"
        total_match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", output)
        if total_match:
            percentage = float(total_match.group(1))

        # Threshold is EXCLUSIVE: coverage must strictly exceed it (>80, not >=80)
        meets = percentage > self.coverage_threshold

        return CoverageResult(
            percentage=percentage,
            threshold=self.coverage_threshold,
            meets_threshold=meets,
            output=output,
        )

    def format_failures(
        self,
        test_result: Optional[TestResult] = None,
        lint_result: Optional[LintResult] = None,
    ) -> str:
        """Format failures from test and lint results into readable output.

        Produces a structured, human-readable report of all failures and
        violations found during testing and linting.

        Args:
            test_result: Optional TestResult with failures.
            lint_result: Optional LintResult with violations.

        Returns:
            Formatted string output of all failures and violations,
            or a success message if no failures found.
        """
        lines: List[str] = []

        if test_result and test_result.failures:
            lines.append("=" * 60)
            lines.append("TEST FAILURES")
            lines.append("=" * 60)
            for idx, failure in enumerate(test_result.failures, 1):
                lines.append(f"\n  {idx}. {failure.file_path}")
                if failure.line_number:
                    lines.append(f"     Line: {failure.line_number}")
                lines.append(f"     Error: {failure.error_message}")
                if failure.context:
                    lines.append(f"     Context: {failure.context}")

        if lint_result and lint_result.violations:
            lines.append("")
            lines.append("=" * 60)
            lines.append("LINT VIOLATIONS")
            lines.append("=" * 60)
            for idx, violation in enumerate(lint_result.violations, 1):
                lines.append(
                    f"\n  {idx}. {violation.file_path}:"
                    f"{violation.line_number}"
                )
                lines.append(f"     {violation.error_message}")
                if violation.context:
                    lines.append(f"     Fix: {violation.context}")

        if not lines:
            return "All checks passed successfully!"

        return "\n".join(lines)

    def run_all_checks(self, test_path: Optional[str] = None) -> dict:
        """Run all checks: pytest, ruff, coverage.

        Executes all three check types sequentially and aggregates results.

        Args:
            test_path: Optional path to specific tests.

        Returns:
            Dictionary with keys:
                - test_result: TestResult from pytest execution
                - lint_result: LintResult from ruff linting
                - coverage_result: CoverageResult from coverage check
                - formatted_output: Human-readable failure summary
                - all_passed: True only if all checks pass
        """
        test_result = self.run_pytest(test_path)
        lint_result = self.run_ruff()
        coverage_result = self.check_coverage(test_path)
        formatted = self.format_failures(test_result, lint_result)

        return {
            "test_result": test_result,
            "lint_result": lint_result,
            "coverage_result": coverage_result,
            "formatted_output": formatted,
            "all_passed": (
                test_result.status == TestStatus.PASSED
                and lint_result.status == LintStatus.CLEAN
                and coverage_result.meets_threshold
            ),
        }


# ============================================================================
# TEST CLASSES
# ============================================================================


class TestPytestExecution:
    """Test suite for pytest execution functionality."""

    @patch("subprocess.run")
    def test_run_pytest_all_pass(self, mock_run):
        """Test pytest when all tests pass returns PASSED status with correct counts."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["python", "-m", "pytest"],
            returncode=0,
            stdout="10 passed in 0.5s\n",
            stderr="",
        )
        artisan = FinalTestingArtisan(project_path="/fake/path")
        result = artisan.run_pytest()

        assert result.status == TestStatus.PASSED
        assert result.passed == 10
        assert result.failed == 0
        assert result.errors == 0
        assert result.total == 10
        assert len(result.failures) == 0
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_run_pytest_with_failures(self, mock_run):
        """Test pytest when some tests fail returns FAILED status with failure details."""
        output = (
            "FAILED tests/test_foo.py::test_bar - AssertionError: expected True\n"
            "3 passed, 1 failed in 0.5s\n"
        )
        mock_run.return_value = subprocess.CompletedProcess(
            args=["python", "-m", "pytest"],
            returncode=1,
            stdout=output,
            stderr="",
        )
        artisan = FinalTestingArtisan()
        result = artisan.run_pytest()

        assert result.status == TestStatus.FAILED
        assert result.passed == 3
        assert result.failed == 1
        assert result.errors == 0
        assert result.total == 4
        assert len(result.failures) == 1
        assert result.failures[0].file_path == "tests/test_foo.py"
        assert "test_bar" in result.failures[0].error_message

    @patch("subprocess.run")
    def test_run_pytest_with_errors(self, mock_run):
        """Test pytest when there are collection/runtime errors returns ERROR status."""
        output = (
            "ERROR tests/test_broken.py - SyntaxError\n"
            "1 error in 0.2s\n"
        )
        mock_run.return_value = subprocess.CompletedProcess(
            args=["python", "-m", "pytest"],
            returncode=1,
            stdout=output,
            stderr="",
        )
        artisan = FinalTestingArtisan()
        result = artisan.run_pytest()

        assert result.status == TestStatus.ERROR
        assert result.errors == 1
        assert result.passed == 0
        assert result.failed == 0

    @patch("subprocess.run")
    def test_run_pytest_with_custom_path(self, mock_run):
        """Test pytest with custom test path includes path in command."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["python", "-m", "pytest", "tests/unit"],
            returncode=0,
            stdout="5 passed in 0.3s\n",
            stderr="",
        )
        artisan = FinalTestingArtisan()
        result = artisan.run_pytest(test_path="tests/unit")

        assert result.passed == 5
        call_args = mock_run.call_args
        assert "tests/unit" in call_args[0][0]

    @patch("subprocess.run")
    def test_run_pytest_with_extra_args(self, mock_run):
        """Test pytest with extra arguments passes them through."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["python", "-m", "pytest", "-v"],
            returncode=0,
            stdout="5 passed in 0.3s\n",
            stderr="",
        )
        artisan = FinalTestingArtisan()
        result = artisan.run_pytest(extra_args=["-v"])

        assert result.status == TestStatus.PASSED
        call_args = mock_run.call_args
        assert "-v" in call_args[0][0]

    @patch("subprocess.run")
    def test_run_pytest_timeout(self, mock_run):
        """Test pytest timeout produces ERROR result with descriptive message."""
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd="pytest", timeout=300
        )
        artisan = FinalTestingArtisan()
        result = artisan.run_pytest()

        assert result.status == TestStatus.ERROR
        assert result.errors == 1
        assert len(result.failures) == 1
        assert "timed out" in result.failures[0].error_message.lower()

    @patch("subprocess.run")
    def test_run_pytest_not_found(self, mock_run):
        """Test missing pytest binary produces ERROR result."""
        mock_run.side_effect = FileNotFoundError("pytest not found")
        artisan = FinalTestingArtisan()
        result = artisan.run_pytest()

        assert result.status == TestStatus.ERROR
        assert result.errors == 1
        assert len(result.failures) == 1
        assert "not found" in result.failures[0].error_message.lower()

    @patch("subprocess.run")
    def test_parse_pytest_output_mixed_results(self, mock_run):
        """Test parsing pytest output with mixed pass/fail correctly identifies all failures."""
        output = (
            "FAILED tests/test_a.py::test_one - AssertionError\n"
            "FAILED tests/test_b.py::test_two - ValueError: invalid\n"
            "5 passed, 2 failed in 0.6s\n"
        )
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout=output,
            stderr="",
        )
        artisan = FinalTestingArtisan()
        result = artisan.run_pytest()

        assert result.passed == 5
        assert result.failed == 2
        assert len(result.failures) == 2
        assert result.failures[0].file_path == "tests/test_a.py"
        assert result.failures[1].file_path == "tests/test_b.py"

    @patch("subprocess.run")
    def test_run_pytest_empty_output(self, mock_run):
        """Test pytest with empty output yields zero counts."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="",
            stderr="",
        )
        artisan = FinalTestingArtisan()
        result = artisan.run_pytest()

        assert result.passed == 0
        assert result.failed == 0
        assert result.errors == 0

    @patch("subprocess.run")
    def test_run_pytest_return_code_zero_means_passed(self, mock_run):
        """Test that return code 0 maps to PASSED status."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="1 passed in 0.1s\n",
            stderr="",
        )
        artisan = FinalTestingArtisan()
        result = artisan.run_pytest()

        assert result.status == TestStatus.PASSED

    @patch("subprocess.run")
    def test_run_pytest_return_code_nonzero_with_failures(self, mock_run):
        """Test that non-zero return code with failures gives FAILED status."""
        output = (
            "FAILED tests/test_x.py::test_fail - Error\n"
            "1 failed in 0.1s\n"
        )
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout=output,
            stderr="",
        )
        artisan = FinalTestingArtisan()
        result = artisan.run_pytest()

        assert result.status == TestStatus.FAILED

    @patch("subprocess.run")
    def test_run_pytest_multiple_failures_parsed(self, mock_run):
        """Test parsing multiple test failures extracts correct file paths."""
        output = (
            "FAILED tests/test_foo.py::test_one - AssertionError: a != b\n"
            "FAILED tests/test_foo.py::test_two - AssertionError: c != d\n"
            "FAILED tests/test_bar.py::test_three - ValueError: bad value\n"
            "2 failed in 0.2s\n"
        )
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout=output,
            stderr="",
        )
        artisan = FinalTestingArtisan()
        result = artisan.run_pytest()

        assert len(result.failures) == 3
        assert result.failures[0].file_path == "tests/test_foo.py"
        assert result.failures[1].file_path == "tests/test_foo.py"
        assert result.failures[2].file_path == "tests/test_bar.py"

    @patch("subprocess.run")
    def test_run_pytest_output_captured(self, mock_run):
        """Test that raw output is captured in the result."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="1 passed in 0.1s\n",
            stderr="some warning\n",
        )
        artisan = FinalTestingArtisan()
        result = artisan.run_pytest()

        assert "1 passed" in result.output
        assert "some warning" in result.output


class TestRuffIntegration:
    """Test suite for ruff linting integration."""

    @patch("subprocess.run")
    def test_run_ruff_clean(self, mock_run):
        """Test ruff when code is clean returns CLEAN status."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["ruff", "check", "."],
            returncode=0,
            stdout="",
            stderr="",
        )
        artisan = FinalTestingArtisan()
        result = artisan.run_ruff()

        assert result.status == LintStatus.CLEAN
        assert len(result.violations) == 0

    @patch("subprocess.run")
    def test_run_ruff_with_violations(self, mock_run):
        """Test ruff when violations are found parses them correctly."""
        ruff_json = json.dumps(
            [
                {
                    "filename": "src/main.py",
                    "location": {"row": 10, "column": 1},
                    "code": "F401",
                    "message": "os imported but unused",
                    "fix": {"message": "Remove unused import"},
                }
            ]
        )
        mock_run.return_value = subprocess.CompletedProcess(
            args=["ruff", "check", "."],
            returncode=1,
            stdout=ruff_json,
            stderr="",
        )
        artisan = FinalTestingArtisan()
        result = artisan.run_ruff()

        assert result.status == LintStatus.VIOLATIONS_FOUND
        assert len(result.violations) == 1
        assert result.violations[0].file_path == "src/main.py"
        assert result.violations[0].line_number == 10
        assert "F401" in result.violations[0].error_message

    @patch("subprocess.run")
    def test_run_ruff_with_fix_mode(self, mock_run):
        """Test ruff with fix mode enabled includes --fix flag."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["ruff", "check", ".", "--fix"],
            returncode=0,
            stdout="",
            stderr="",
        )
        artisan = FinalTestingArtisan()
        result = artisan.run_ruff(check_only=False)

        assert result.status == LintStatus.CLEAN
        call_args = mock_run.call_args
        assert "--fix" in call_args[0][0]

    @patch("subprocess.run")
    def test_run_ruff_check_only_omits_fix_flag(self, mock_run):
        """Test ruff in check-only mode does not include --fix flag."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["ruff", "check", "."],
            returncode=0,
            stdout="",
            stderr="",
        )
        artisan = FinalTestingArtisan()
        artisan.run_ruff(check_only=True)

        call_args = mock_run.call_args
        assert "--fix" not in call_args[0][0]

    @patch("subprocess.run")
    def test_run_ruff_json_parse_error(self, mock_run):
        """Test ruff handling of invalid JSON output returns ERROR status."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["ruff", "check", "."],
            returncode=1,
            stdout="invalid json {{{ [",
            stderr="",
        )
        artisan = FinalTestingArtisan()
        result = artisan.run_ruff()

        assert result.status == LintStatus.ERROR
        assert len(result.violations) == 0

    @patch("subprocess.run")
    def test_run_ruff_timeout(self, mock_run):
        """Test ruff timeout handling returns ERROR with descriptive output."""
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd="ruff", timeout=120
        )
        artisan = FinalTestingArtisan()
        result = artisan.run_ruff()

        assert result.status == LintStatus.ERROR
        assert len(result.violations) == 0
        assert "timed out" in result.output.lower()

    @patch("subprocess.run")
    def test_run_ruff_not_found(self, mock_run):
        """Test ruff not found handling returns ERROR with descriptive output."""
        mock_run.side_effect = FileNotFoundError("ruff not found")
        artisan = FinalTestingArtisan()
        result = artisan.run_ruff()

        assert result.status == LintStatus.ERROR
        assert len(result.violations) == 0
        assert "not found" in result.output.lower()

    @patch("subprocess.run")
    def test_parse_ruff_output_multiple_violations(self, mock_run):
        """Test parsing multiple ruff violations extracts all details."""
        ruff_json = json.dumps(
            [
                {
                    "filename": "src/a.py",
                    "location": {"row": 5, "column": 1},
                    "code": "E501",
                    "message": "line too long",
                    "fix": None,
                },
                {
                    "filename": "src/b.py",
                    "location": {"row": 15, "column": 10},
                    "code": "F841",
                    "message": "local variable assigned but never used",
                    "fix": {"message": "Remove assignment"},
                },
            ]
        )
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout=ruff_json,
            stderr="",
        )
        artisan = FinalTestingArtisan()
        result = artisan.run_ruff()

        assert result.status == LintStatus.VIOLATIONS_FOUND
        assert len(result.violations) == 2
        assert result.violations[0].file_path == "src/a.py"
        assert result.violations[1].file_path == "src/b.py"
        assert result.violations[1].line_number == 15

    @patch("subprocess.run")
    def test_parse_ruff_output_empty(self, mock_run):
        """Test parsing empty ruff output returns CLEAN status."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="",
            stderr="",
        )
        artisan = FinalTestingArtisan()
        result = artisan.run_ruff()

        assert result.status == LintStatus.CLEAN
        assert len(result.violations) == 0

    @patch("subprocess.run")
    def test_ruff_violation_has_file_and_line(self, mock_run):
        """Test that ruff violations include correct file path and line number."""
        ruff_json = json.dumps(
            [
                {
                    "filename": "src/main.py",
                    "location": {"row": 42, "column": 5},
                    "code": "W293",
                    "message": "blank line contains whitespace",
                    "fix": None,
                }
            ]
        )
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout=ruff_json,
            stderr="",
        )
        artisan = FinalTestingArtisan()
        result = artisan.run_ruff()

        assert result.violations[0].file_path == "src/main.py"
        assert result.violations[0].line_number == 42

    @patch("subprocess.run")
    def test_ruff_violation_context_present(self, mock_run):
        """Test that ruff violations include fix context when available."""
        ruff_json = json.dumps(
            [
                {
                    "filename": "src/main.py",
                    "location": {"row": 1, "column": 1},
                    "code": "F401",
                    "message": "unused import",
                    "fix": {"message": "Delete unused import"},
                }
            ]
        )
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout=ruff_json,
            stderr="",
        )
        artisan = FinalTestingArtisan()
        result = artisan.run_ruff()

        assert result.violations[0].context == "Delete unused import"

    @patch("subprocess.run")
    def test_ruff_violation_no_fix_has_empty_context(self, mock_run):
        """Test that ruff violations without fix have empty context."""
        ruff_json = json.dumps(
            [
                {
                    "filename": "src/main.py",
                    "location": {"row": 1, "column": 1},
                    "code": "E501",
                    "message": "line too long",
                    "fix": None,
                }
            ]
        )
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout=ruff_json,
            stderr="",
        )
        artisan = FinalTestingArtisan()
        result = artisan.run_ruff()

        assert result.violations[0].context == ""


class TestFailureFormatting:
    """Test suite for failure formatting functionality."""

    def test_format_no_failures(self):
        """Test formatting when there are no failures returns success message."""
        artisan = FinalTestingArtisan()
        output = artisan.format_failures(
            test_result=None, lint_result=None
        )

        assert "All checks passed successfully!" in output

    def test_format_test_failures_only(self):
        """Test formatting with only test failures includes TEST FAILURES header."""
        test_result = TestResult(
            status=TestStatus.FAILED,
            passed=3,
            failed=1,
            errors=0,
            total=4,
            failures=[
                FailureDetail(
                    file_path="tests/test_foo.py",
                    line_number=42,
                    error_message="AssertionError: expected True",
                    context="",
                )
            ],
        )
        artisan = FinalTestingArtisan()
        output = artisan.format_failures(test_result=test_result)

        assert "TEST FAILURES" in output
        assert "tests/test_foo.py" in output
        assert "AssertionError" in output

    def test_format_lint_violations_only(self):
        """Test formatting with only lint violations includes LINT VIOLATIONS header."""
        lint_result = LintResult(
            status=LintStatus.VIOLATIONS_FOUND,
            violations=[
                FailureDetail(
                    file_path="src/main.py",
                    line_number=10,
                    error_message="F401: os imported but unused",
                    context="Remove unused import",
                )
            ],
        )
        artisan = FinalTestingArtisan()
        output = artisan.format_failures(lint_result=lint_result)

        assert "LINT VIOLATIONS" in output
        assert "src/main.py" in output
        assert "F401" in output

    def test_format_both_test_and_lint_failures(self):
        """Test formatting with both test and lint failures includes both sections."""
        test_result = TestResult(
            status=TestStatus.FAILED,
            passed=1,
            failed=1,
            errors=0,
            total=2,
            failures=[
                FailureDetail(
                    file_path="tests/test_a.py",
                    line_number=20,
                    error_message="ValueError: invalid",
                    context="",
                )
            ],
        )
        lint_result = LintResult(
            status=LintStatus.VIOLATIONS_FOUND,
            violations=[
                FailureDetail(
                    file_path="src/b.py",
                    line_number=5,
                    error_message="E501: line too long",
                    context="",
                )
            ],
        )
        artisan = FinalTestingArtisan()
        output = artisan.format_failures(
            test_result=test_result, lint_result=lint_result
        )

        assert "TEST FAILURES" in output
        assert "LINT VIOLATIONS" in output
        assert "tests/test_a.py" in output
        assert "src/b.py" in output

    def test_format_includes_file_path(self):
        """Test that formatted output includes the file path."""
        test_result = TestResult(
            status=TestStatus.FAILED,
            passed=0,
            failed=1,
            errors=0,
            total=1,
            failures=[
                FailureDetail(
                    file_path="tests/special/test_name.py",
                    line_number=1,
                    error_message="Error",
                    context="",
                )
            ],
        )
        artisan = FinalTestingArtisan()
        output = artisan.format_failures(test_result=test_result)

        assert "tests/special/test_name.py" in output

    def test_format_includes_line_number(self):
        """Test that formatted output includes the line number."""
        test_result = TestResult(
            status=TestStatus.FAILED,
            passed=0,
            failed=1,
            errors=0,
            total=1,
            failures=[
                FailureDetail(
                    file_path="test.py",
                    line_number=123,
                    error_message="Error",
                    context="",
                )
            ],
        )
        artisan = FinalTestingArtisan()
        output = artisan.format_failures(test_result=test_result)

        assert "123" in output

    def test_format_includes_error_message(self):
        """Test that formatted output includes the error message."""
        test_result = TestResult(
            status=TestStatus.FAILED,
            passed=0,
            failed=1,
            errors=0,
            total=1,
            failures=[
                FailureDetail(
                    file_path="test.py",
                    line_number=1,
                    error_message="CustomError: something went wrong",
                    context="",
                )
            ],
        )
        artisan = FinalTestingArtisan()
        output = artisan.format_failures(test_result=test_result)

        assert "CustomError: something went wrong" in output

    def test_format_includes_context_when_available(self):
        """Test that formatted output includes context when provided."""
        test_result = TestResult(
            status=TestStatus.FAILED,
            passed=0,
            failed=1,
            errors=0,
            total=1,
            failures=[
                FailureDetail(
                    file_path="test.py",
                    line_number=1,
                    error_message="Error",
                    context="Fix this by doing X",
                )
            ],
        )
        artisan = FinalTestingArtisan()
        output = artisan.format_failures(test_result=test_result)

        assert "Fix this by doing X" in output

    def test_format_omits_line_when_zero(self):
        """Test that line number label is omitted when line_number is 0."""
        test_result = TestResult(
            status=TestStatus.FAILED,
            passed=0,
            failed=1,
            errors=0,
            total=1,
            failures=[
                FailureDetail(
                    file_path="test.py",
                    line_number=0,
                    error_message="Error",
                    context="",
                )
            ],
        )
        artisan = FinalTestingArtisan()
        output = artisan.format_failures(test_result=test_result)

        lines = output.split("\n")
        line_lines = [line for line in lines if "Line:" in line]
        assert len(line_lines) == 0

    def test_format_multiple_failures_numbered(self):
        """Test that multiple failures are numbered sequentially."""
        test_result = TestResult(
            status=TestStatus.FAILED,
            passed=0,
            failed=2,
            errors=0,
            total=2,
            failures=[
                FailureDetail(
                    file_path="test1.py",
                    line_number=1,
                    error_message="Error 1",
                    context="",
                ),
                FailureDetail(
                    file_path="test2.py",
                    line_number=2,
                    error_message="Error 2",
                    context="",
                ),
            ],
        )
        artisan = FinalTestingArtisan()
        output = artisan.format_failures(test_result=test_result)

        assert "1. test1.py" in output
        assert "2. test2.py" in output

    def test_format_empty_failures_list(self):
        """Test formatting when result has empty failures list returns success."""
        test_result = TestResult(
            status=TestStatus.PASSED,
            passed=5,
            failed=0,
            errors=0,
            total=5,
            failures=[],
        )
        artisan = FinalTestingArtisan()
        output = artisan.format_failures(test_result=test_result)

        assert "All checks passed successfully!" in output

    def test_format_lint_fix_context_shown(self):
        """Test that lint violation fix suggestions appear in output."""
        lint_result = LintResult(
            status=LintStatus.VIOLATIONS_FOUND,
            violations=[
                FailureDetail(
                    file_path="src/main.py",
                    line_number=1,
                    error_message="F401: unused import",
                    context="Remove the import statement",
                )
            ],
        )
        artisan = FinalTestingArtisan()
        output = artisan.format_failures(lint_result=lint_result)

        assert "Fix: Remove the import statement" in output


class TestCoverageThreshold:
    """Test suite for coverage threshold checking (>80% required)."""

    @patch("subprocess.run")
    def test_coverage_above_threshold_passes(self, mock_run):
        """Test coverage above threshold reports meets_threshold=True."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="TOTAL    1000    100    90%\n",
            stderr="",
        )
        artisan = FinalTestingArtisan(coverage_threshold=80.0)
        result = artisan.check_coverage()

        assert result.percentage == 90.0
        assert result.meets_threshold is True

    @patch("subprocess.run")
    def test_coverage_below_threshold_fails(self, mock_run):
        """Test coverage below threshold reports meets_threshold=False."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="TOTAL    1000    500    50%\n",
            stderr="",
        )
        artisan = FinalTestingArtisan(coverage_threshold=80.0)
        result = artisan.check_coverage()

        assert result.percentage == 50.0
        assert result.meets_threshold is False

    @patch("subprocess.run")
    def test_coverage_exactly_at_threshold_fails(self, mock_run):
        """Test coverage at exactly threshold value fails (>80, not >=80)."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="TOTAL    1000    200    80%\n",
            stderr="",
        )
        artisan = FinalTestingArtisan(coverage_threshold=80.0)
        result = artisan.check_coverage()

        assert result.percentage == 80.0
        assert result.meets_threshold is False

    @patch("subprocess.run")
    def test_coverage_just_above_threshold_passes(self, mock_run):
        """Test coverage at 81% passes the >80 threshold."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="TOTAL    1000    190    81%\n",
            stderr="",
        )
        artisan = FinalTestingArtisan(coverage_threshold=80.0)
        result = artisan.check_coverage()

        assert result.percentage == 81.0
        assert result.meets_threshold is True

    @patch("subprocess.run")
    @pytest.mark.parametrize(
        "percentage,expected_meets",
        [
            (80, False),
            (81, True),
            (100, True),
            (79, False),
            (0, False),
            (50, False),
            (85, True),
            (99, True),
        ],
    )
    def test_coverage_threshold_boundary(
        self, mock_run, percentage, expected_meets
    ):
        """Parametrized test of coverage threshold boundary conditions."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=f"TOTAL    1000    100    {percentage}%\n",
            stderr="",
        )
        artisan = FinalTestingArtisan(coverage_threshold=80.0)
        result = artisan.check_coverage()

        assert result.percentage == float(percentage)
        assert result.meets_threshold == expected_meets

    @patch("subprocess.run")
    def test_custom_threshold(self, mock_run):
        """Test custom coverage threshold is applied correctly."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="TOTAL    1000    100    75%\n",
            stderr="",
        )
        artisan = FinalTestingArtisan(coverage_threshold=70.0)
        result = artisan.check_coverage()

        assert result.threshold == 70.0
        assert result.percentage == 75.0
        assert result.meets_threshold is True

    @patch("subprocess.run")
    def test_coverage_default_threshold_is_80(self, mock_run):
        """Test that default coverage threshold is 80.0."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="TOTAL    1000    100    85%\n",
            stderr="",
        )
        artisan = FinalTestingArtisan()
        result = artisan.check_coverage()

        assert result.threshold == 80.0

    @patch("subprocess.run")
    def test_coverage_timeout(self, mock_run):
        """Test coverage timeout returns 0% and fails threshold."""
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd="pytest", timeout=300
        )
        artisan = FinalTestingArtisan()
        result = artisan.check_coverage()

        assert result.percentage == 0.0
        assert result.meets_threshold is False

    @patch("subprocess.run")
    def test_coverage_tool_not_found(self, mock_run):
        """Test coverage tool not found returns 0% and fails threshold."""
        mock_run.side_effect = FileNotFoundError("pytest not found")
        artisan = FinalTestingArtisan()
        result = artisan.check_coverage()

        assert result.percentage == 0.0
        assert result.meets_threshold is False

    @patch("subprocess.run")
    def test_coverage_with_test_path(self, mock_run):
        """Test coverage check passes test_path to command."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="TOTAL    1000    100    90%\n",
            stderr="",
        )
        artisan = FinalTestingArtisan()
        result = artisan.check_coverage(test_path="tests/unit")

        call_args = mock_run.call_args
        assert "tests/unit" in call_args[0][0]
        assert result.percentage == 90.0


class TestCoverageReporting:
    """Test suite for coverage reporting and output parsing."""

    @patch("subprocess.run")
    def test_parse_coverage_total_line(self, mock_run):
        """Test parsing coverage percentage from TOTAL line."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="src/__init__.py    10    0    100%\nTOTAL    1000    150    85%\n",
            stderr="",
        )
        artisan = FinalTestingArtisan()
        result = artisan.check_coverage()

        assert result.percentage == 85.0

    @patch("subprocess.run")
    def test_parse_coverage_no_total_line(self, mock_run):
        """Test parsing coverage with no TOTAL line returns 0%."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="src/__init__.py    10    0    100%\n",
            stderr="",
        )
        artisan = FinalTestingArtisan()
        result = artisan.check_coverage()

        assert result.percentage == 0.0

    def test_coverage_result_has_percentage(self):
        """Test that CoverageResult dataclass has percentage field."""
        result = CoverageResult(
            percentage=85.5, threshold=80.0, meets_threshold=True
        )
        assert result.percentage == 85.5

    def test_coverage_result_has_threshold(self):
        """Test that CoverageResult dataclass has threshold field."""
        result = CoverageResult(
            percentage=85.0, threshold=80.0, meets_threshold=True
        )
        assert result.threshold == 80.0

    def test_coverage_result_has_meets_threshold(self):
        """Test that CoverageResult dataclass has meets_threshold field."""
        result = CoverageResult(
            percentage=85.0, threshold=80.0, meets_threshold=True
        )
        assert result.meets_threshold is True

    def test_coverage_result_has_output(self):
        """Test that CoverageResult dataclass has output field."""
        result = CoverageResult(
            percentage=85.0,
            threshold=80.0,
            meets_threshold=True,
            output="test output",
        )
        assert result.output == "test output"

    def test_coverage_result_default_output_empty(self):
        """Test that CoverageResult default output is empty string."""
        result = CoverageResult(
            percentage=85.0, threshold=80.0, meets_threshold=True
        )
        assert result.output == ""

    @patch("subprocess.run")
    @pytest.mark.parametrize(
        "coverage_output,expected_percentage",
        [
            ("TOTAL    1000    0    100%", 100.0),
            ("TOTAL    1000    500    50%", 50.0),
            ("TOTAL    1000    250    75%", 75.0),
            ("TOTAL    5000    1000    80%", 80.0),
            ("TOTAL    100    5    95%", 95.0),
        ],
    )
    def test_parse_various_coverage_percentages(
        self, mock_run, coverage_output, expected_percentage
    ):
        """Parametrized test for various coverage percentage values."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=coverage_output + "\n",
            stderr="",
        )
        artisan = FinalTestingArtisan()
        result = artisan.check_coverage()

        assert result.percentage == expected_percentage

    @patch("subprocess.run")
    def test_coverage_output_captured_in_result(self, mock_run):
        """Test that raw coverage output is captured in result."""
        stdout_text = "TOTAL    1000    100    90%\n"
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=stdout_text,
            stderr="",
        )
        artisan = FinalTestingArtisan()
        result = artisan.check_coverage()

        assert "TOTAL" in result.output


class TestFinalTestingEndToEnd:
    """End-to-end integration tests for the FinalTestingArtisan pipeline."""

    @patch("subprocess.run")
    def test_run_all_checks_all_pass(self, mock_run):
        """Test run_all_checks when everything passes returns all_passed=True."""
        mock_run.side_effect = [
            subprocess.CompletedProcess(
                args=["python", "-m", "pytest"],
                returncode=0,
                stdout="10 passed in 0.5s\n",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=["ruff", "check", "."],
                returncode=0,
                stdout="",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=["python", "-m", "pytest", "--cov"],
                returncode=0,
                stdout="TOTAL    1000    100    90%\n",
                stderr="",
            ),
        ]
        artisan = FinalTestingArtisan()
        results = artisan.run_all_checks()

        assert results["all_passed"] is True
        assert results["test_result"].status == TestStatus.PASSED
        assert results["lint_result"].status == LintStatus.CLEAN
        assert results["coverage_result"].meets_threshold is True

    @patch("subprocess.run")
    def test_run_all_checks_test_failure(self, mock_run):
        """Test run_all_checks when tests fail returns all_passed=False."""
        output = "FAILED tests/test_foo.py::test_bar - Error\n1 failed\n"
        mock_run.side_effect = [
            subprocess.CompletedProcess(
                args=["python", "-m", "pytest"],
                returncode=1,
                stdout=output,
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=["ruff", "check", "."],
                returncode=0,
                stdout="",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=["python", "-m", "pytest", "--cov"],
                returncode=0,
                stdout="TOTAL    1000    100    90%\n",
                stderr="",
            ),
        ]
        artisan = FinalTestingArtisan()
        results = artisan.run_all_checks()

        assert results["all_passed"] is False
        assert results["test_result"].status == TestStatus.FAILED

    @patch("subprocess.run")
    def test_run_all_checks_lint_failure(self, mock_run):
        """Test run_all_checks when linting fails returns all_passed=False."""
        ruff_json = json.dumps(
            [
                {
                    "filename": "src/main.py",
                    "location": {"row": 10, "column": 1},
                    "code": "F401",
                    "message": "unused import",
                    "fix": None,
                }
            ]
        )
        mock_run.side_effect = [
            subprocess.CompletedProcess(
                args=["python", "-m", "pytest"],
                returncode=0,
                stdout="10 passed in 0.5s\n",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=["ruff", "check", "."],
                returncode=1,
                stdout=ruff_json,
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=["python", "-m", "pytest", "--cov"],
                returncode=0,
                stdout="TOTAL    1000    100    90%\n",
                stderr="",
            ),
        ]
        artisan = FinalTestingArtisan()
        results = artisan.run_all_checks()

        assert results["all_passed"] is False
        assert results["lint_result"].status == LintStatus.VIOLATIONS_FOUND

    @patch("subprocess.run")
    def test_run_all_checks_coverage_failure(self, mock_run):
        """Test run_all_checks when coverage is below threshold returns all_passed=False."""
        mock_run.side_effect = [
            subprocess.CompletedProcess(
                args=["python", "-m", "pytest"],
                returncode=0,
                stdout="10 passed in 0.5s\n",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=["ruff", "check", "."],
                returncode=0,
                stdout="",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=["python", "-m", "pytest", "--cov"],
                returncode=0,
                stdout="TOTAL    1000    500    50%\n",
                stderr="",
            ),
        ]
        artisan = FinalTestingArtisan(coverage_threshold=80.0)
        results = artisan.run_all_checks()

        assert results["all_passed"] is False
        assert results["coverage_result"].meets_threshold is False

    @patch("subprocess.run")
    def test_run_all_checks_returns_dict_with_expected_keys(self, mock_run):
        """Test run_all_checks returns dict with all required keys."""
        mock_run.side_effect = [
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="1 passed\n",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="TOTAL    1000    100    90%\n",
                stderr="",
            ),
        ]
        artisan = FinalTestingArtisan()
        results = artisan.run_all_checks()

        expected_keys = {
            "test_result",
            "lint_result",
            "coverage_result",
            "formatted_output",
            "all_passed",
        }
        assert set(results.keys()) == expected_keys

    @patch("subprocess.run")
    def test_run_all_checks_all_passed_flag_true_when_all_pass(self, mock_run):
        """Test all_passed flag is True only when all three checks pass."""
        mock_run.side_effect = [
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="5 passed\n",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="TOTAL    1000    100    85%\n",
                stderr="",
            ),
        ]
        artisan = FinalTestingArtisan()
        results = artisan.run_all_checks()

        assert results["all_passed"] is True

    @patch("subprocess.run")
    def test_run_all_checks_all_passed_flag_false_when_any_fail(self, mock_run):
        """Test all_passed flag is False when any single check fails."""
        output = "FAILED tests/test.py::test_x - Error\n1 failed\n"
        mock_run.side_effect = [
            subprocess.CompletedProcess(
                args=[],
                returncode=1,
                stdout=output,
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="TOTAL    1000    100    85%\n",
                stderr="",
            ),
        ]
        artisan = FinalTestingArtisan()
        results = artisan.run_all_checks()

        assert results["all_passed"] is False

    def test_artisan_default_project_path(self):
        """Test that default project path is current directory."""
        artisan = FinalTestingArtisan()
        assert artisan.project_path == "."

    def test_artisan_custom_project_path(self):
        """Test that custom project path is set correctly."""
        artisan = FinalTestingArtisan(project_path="/custom/path")
        assert artisan.project_path == "/custom/path"

    @patch("subprocess.run")
    def test_run_all_checks_with_custom_test_path(self, mock_run):
        """Test run_all_checks passes custom test path to sub-checks."""
        mock_run.side_effect = [
            subprocess.CompletedProcess(
                args=["python", "-m", "pytest", "tests/unit"],
                returncode=0,
                stdout="3 passed\n",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="TOTAL    1000    100    85%\n",
                stderr="",
            ),
        ]
        artisan = FinalTestingArtisan()
        results = artisan.run_all_checks(test_path="tests/unit")

        assert results["test_result"].passed == 3

    @patch("subprocess.run")
    def test_run_all_checks_formatted_output_present(self, mock_run):
        """Test run_all_checks includes non-empty formatted output."""
        mock_run.side_effect = [
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="1 passed\n",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="TOTAL    1000    100    85%\n",
                stderr="",
            ),
        ]
        artisan = FinalTestingArtisan()
        results = artisan.run_all_checks()

        assert isinstance(results["formatted_output"], str)
        assert len(results["formatted_output"]) > 0

    @patch("subprocess.run")
    def test_run_all_checks_with_failures_includes_them_in_output(
        self, mock_run
    ):
        """Test formatted output includes failure details when present."""
        output = "FAILED tests/test.py::test_x - Error\n1 failed\n"
        mock_run.side_effect = [
            subprocess.CompletedProcess(
                args=[],
                returncode=1,
                stdout=output,
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="TOTAL    1000    100    85%\n",
                stderr="",
            ),
        ]
        artisan = FinalTestingArtisan()
        results = artisan.run_all_checks()

        assert "TEST FAILURES" in results["formatted_output"]
        assert "tests/test.py" in results["formatted_output"]

    @patch("subprocess.run")
    def test_run_all_checks_calls_subprocess_three_times(self, mock_run):
        """Test that run_all_checks invokes subprocess exactly 3 times."""
        mock_run.side_effect = [
            subprocess.CompletedProcess(
                args=[], returncode=0, stdout="1 passed\n", stderr=""
            ),
            subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            ),
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="TOTAL    100    10    90%\n",
                stderr="",
            ),
        ]
        artisan = FinalTestingArtisan()
        artisan.run_all_checks()

        assert mock_run.call_count == 3

    @patch("subprocess.run")
    def test_run_all_checks_result_types(self, mock_run):
        """Test that run_all_checks returns correct types for each result."""
        mock_run.side_effect = [
            subprocess.CompletedProcess(
                args=[], returncode=0, stdout="1 passed\n", stderr=""
            ),
            subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            ),
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="TOTAL    100    10    90%\n",
                stderr="",
            ),
        ]
        artisan = FinalTestingArtisan()
        results = artisan.run_all_checks()

        assert isinstance(results["test_result"], TestResult)
        assert isinstance(results["lint_result"], LintResult)
        assert isinstance(results["coverage_result"], CoverageResult)
        assert isinstance(results["formatted_output"], str)
        assert isinstance(results["all_passed"], bool)