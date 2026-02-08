"""
Integration Checkpoint - Validates code before proceeding to next feature.

Checkpoints ensure that each feature is:
1. Syntactically valid (compiles)
2. Imports work correctly
3. Tests pass (or at least don't regress)
4. No conflicts with existing code

This prevents the accumulation of technical debt that happens when
features are developed without integration validation.

This module is now part of startd8-sdk and works without ContextCore.
"""

import logging
import os
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class CheckpointStatus(Enum):
    """Status of an integration checkpoint."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WARNING = "warning"


@dataclass
class CheckpointResult:
    """Result of running an integration checkpoint."""

    status: CheckpointStatus
    name: str  # Alias for checkpoint_name for compatibility
    message: str
    details: Dict = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Compatibility alias
    @property
    def checkpoint_name(self) -> str:
        return self.name

    @property
    def passed(self) -> bool:
        return self.status in (CheckpointStatus.PASSED, CheckpointStatus.WARNING)

    def __str__(self) -> str:
        icon = {
            CheckpointStatus.PASSED: "✓",
            CheckpointStatus.FAILED: "✗",
            CheckpointStatus.SKIPPED: "○",
            CheckpointStatus.WARNING: "⚠",
        }.get(self.status, "?")
        return f"{icon} {self.name}: {self.message}"


class IntegrationCheckpoint:
    """
    Validates integrated code before proceeding to the next feature.

    This is the key mechanism that prevents regression issues:
    - Each feature must pass all checkpoints before the next feature starts
    - If a checkpoint fails, the feature must be fixed before continuing
    - This keeps the mainline always in a working state

    Example:
        checkpoint = IntegrationCheckpoint(project_root=Path.cwd())
        results = checkpoint.run_all_checkpoints([Path("src/auth.py")], "auth")
        if checkpoint.summarize_results(results):
            print("All checkpoints passed!")
    """

    def __init__(
        self,
        project_root: Optional[Path] = None,
        run_tests: bool = True,
        strict_mode: bool = False,
        src_dirs: Optional[List[str]] = None,
    ):
        """
        Initialize the checkpoint runner.

        Args:
            project_root: Root directory of the project
            run_tests: Whether to run tests as part of validation
            strict_mode: Whether to fail on warnings
            src_dirs: List of source directories to check (default: ["src"])
        """
        self.project_root = project_root or Path.cwd()
        self.run_tests = run_tests
        self.strict_mode = strict_mode
        self.src_dirs = src_dirs or ["src"]
        self._test_baseline: Optional[Set[str]] = None

    def capture_test_baseline(self) -> Set[str]:
        """
        Capture the current set of passing tests as a baseline.

        This allows us to detect regressions (tests that were passing
        before but fail after integration).
        """
        try:
            result = subprocess.run(
                ["python3", "-m", "pytest", "--collect-only", "-q"],
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            logger.warning("Test baseline collection timed out after 60s")
            self._test_baseline = set()
            return self._test_baseline

        passing_tests = set()
        for line in result.stdout.split("\n"):
            line = line.strip()
            if "::" in line and not line.startswith(("=", "-", " ")):
                passing_tests.add(line.split()[0])

        self._test_baseline = passing_tests
        return passing_tests

    def run_all_checkpoints(
        self,
        integrated_files: List[Path],
        feature_name: str,
    ) -> List[CheckpointResult]:
        """
        Run all integration checkpoints for the given files.

        Args:
            integrated_files: List of files that were integrated
            feature_name: Name of the feature (for logging)

        Returns:
            List of checkpoint results
        """
        results = []

        # 1. Syntax check
        results.append(self.check_syntax(integrated_files))

        # 2. Import validation
        results.append(self.check_imports(integrated_files))

        # 3. Lint check (basic)
        results.append(self.check_lint(integrated_files))

        # 4. Test check (if enabled)
        if self.run_tests:
            results.append(self.check_tests(feature_name))

        return results

    def check_syntax(self, files: List[Path]) -> CheckpointResult:
        """Check that all Python files have valid syntax."""
        errors = []
        checked = 0

        for file_path in files:
            if file_path.suffix != ".py":
                continue

            checked += 1
            try:
                result = subprocess.run(
                    ["python3", "-m", "py_compile", str(file_path)],
                    capture_output=True,
                    text=True,
                    cwd=self.project_root,
                    timeout=30,
                )
            except subprocess.TimeoutExpired:
                errors.append(f"{file_path.name}: syntax check timed out")
                continue

            if result.returncode != 0:
                errors.append(f"{file_path.name}: {result.stderr.strip()}")

        if errors:
            return CheckpointResult(
                status=CheckpointStatus.FAILED,
                name="Syntax Check",
                message=f"{len(errors)} file(s) have syntax errors",
                errors=errors,
            )

        return CheckpointResult(
            status=CheckpointStatus.PASSED,
            name="Syntax Check",
            message=f"{checked} file(s) have valid syntax",
            details={"files_checked": checked},
        )

    def check_imports(self, files: List[Path]) -> CheckpointResult:
        """Check that all imports in the files can be resolved."""
        errors = []
        warnings = []
        checked = 0

        for file_path in files:
            if file_path.suffix != ".py":
                continue

            checked += 1

            # Check if file is in any of the src directories
            for src_dir in self.src_dirs:
                src_path = self.project_root / src_dir
                if not src_path.exists():
                    continue

                try:
                    rel_path = file_path.relative_to(src_path)
                    module_path = str(rel_path).replace("/", ".").replace(".py", "")

                    # Build PYTHONPATH with all src directories
                    pythonpath = ":".join(
                        str(self.project_root / d)
                        for d in self.src_dirs
                        if (self.project_root / d).exists()
                    )

                    try:
                        result = subprocess.run(
                            ["python3", "-c", f"import {module_path}"],
                            capture_output=True,
                            text=True,
                            cwd=self.project_root,
                            env={
                                **os.environ,
                                "PYTHONPATH": pythonpath,
                            },
                            timeout=30,
                        )
                    except subprocess.TimeoutExpired:
                        errors.append(f"{file_path.name}: import check timed out")
                        break

                    if result.returncode != 0:
                        error_msg = result.stderr.strip().split("\n")[-1]
                        if "ImportError" in error_msg or "ModuleNotFoundError" in error_msg:
                            errors.append(f"{file_path.name}: {error_msg}")
                        else:
                            # Other errors might be runtime issues, not import issues
                            warnings.append(f"{file_path.name}: {error_msg}")
                    break  # Found the file in this src dir, don't check others
                except ValueError:
                    continue  # File not in this src dir
                except Exception as e:
                    warnings.append(f"{file_path.name}: Could not check imports: {e}")

        if errors:
            return CheckpointResult(
                status=CheckpointStatus.FAILED,
                name="Import Check",
                message=f"{len(errors)} file(s) have import errors",
                errors=errors,
                warnings=warnings,
            )

        if warnings:
            return CheckpointResult(
                status=CheckpointStatus.WARNING,
                name="Import Check",
                message=f"{checked} file(s) checked, {len(warnings)} warning(s)",
                warnings=warnings,
                details={"files_checked": checked},
            )

        return CheckpointResult(
            status=CheckpointStatus.PASSED,
            name="Import Check",
            message=f"{checked} file(s) have valid imports",
            details={"files_checked": checked},
        )

    def check_lint(self, files: List[Path]) -> CheckpointResult:
        """Run basic lint checks on the files."""
        errors = []
        warnings = []
        checked = 0

        for file_path in files:
            if file_path.suffix != ".py":
                continue

            checked += 1

            # Try ruff if available
            try:
                result = subprocess.run(
                    ["python3", "-m", "ruff", "check", str(file_path), "--select=E,F"],
                    capture_output=True,
                    text=True,
                    cwd=self.project_root,
                    timeout=60,
                )
            except subprocess.TimeoutExpired:
                errors.append(f"{file_path.name}: lint check timed out")
                continue

            if result.returncode != 0:
                # Parse ruff output for errors vs warnings
                for line in result.stdout.strip().split("\n"):
                    if line.strip():
                        if ": F" in line or ": E9" in line:  # Fatal errors
                            errors.append(line)
                        else:
                            warnings.append(line)

        if errors:
            return CheckpointResult(
                status=CheckpointStatus.FAILED,
                name="Lint Check",
                message=f"{len(errors)} lint error(s) found",
                errors=errors[:10],  # Limit to first 10
                warnings=warnings[:5],
            )

        if warnings and self.strict_mode:
            return CheckpointResult(
                status=CheckpointStatus.WARNING,
                name="Lint Check",
                message=f"{len(warnings)} lint warning(s) found",
                warnings=warnings[:10],
                details={"files_checked": checked},
            )

        return CheckpointResult(
            status=CheckpointStatus.PASSED,
            name="Lint Check",
            message=f"{checked} file(s) pass lint checks",
            details={"files_checked": checked},
        )

    def check_tests(self, feature_name: str) -> CheckpointResult:
        """
        Run tests and check for regressions.

        A regression is when a test that was passing before integration
        now fails after integration.
        """
        # Run pytest
        try:
            result = subprocess.run(
                ["python3", "-m", "pytest", "-v", "--tb=short", "-q"],
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            return CheckpointResult(
                status=CheckpointStatus.FAILED,
                name="Test Check",
                message="Test suite timed out after 120s",
                errors=["pytest timed out — tests may be hanging"],
            )

        # Parse results
        output = result.stdout + result.stderr

        # Count passed/failed
        passed = 0
        failed = 0
        failed_tests = []

        for line in output.split("\n"):
            if " passed" in line:
                try:
                    passed = int(line.split()[0])
                except (ValueError, IndexError):
                    pass
            if " failed" in line:
                try:
                    failed = int(line.split()[0])
                except (ValueError, IndexError):
                    pass
            if "FAILED" in line and "::" in line:
                failed_tests.append(line.strip())

        # Check for regressions
        regressions = []
        if self._test_baseline and failed_tests:
            for test in failed_tests:
                test_name = test.split()[0] if test else ""
                if test_name in self._test_baseline:
                    regressions.append(test_name)

        if regressions:
            return CheckpointResult(
                status=CheckpointStatus.FAILED,
                name="Test Check",
                message=f"REGRESSION: {len(regressions)} test(s) that were passing now fail",
                errors=regressions,
                details={
                    "passed": passed,
                    "failed": failed,
                    "regressions": len(regressions),
                },
            )

        if failed > 0:
            return CheckpointResult(
                status=CheckpointStatus.WARNING,
                name="Test Check",
                message=f"{failed} test(s) failed (but no regressions)",
                warnings=failed_tests[:5],
                details={"passed": passed, "failed": failed},
            )

        return CheckpointResult(
            status=CheckpointStatus.PASSED,
            name="Test Check",
            message=f"{passed} test(s) passed",
            details={"passed": passed, "failed": failed},
        )

    def summarize_results(self, results: List[CheckpointResult]) -> bool:
        """
        Print summary of checkpoint results.

        Returns:
            True if all checkpoints passed (or warned), False if any failed
        """
        print("\n" + "=" * 60)
        print("INTEGRATION CHECKPOINT RESULTS")
        print("=" * 60)

        all_passed = True
        for result in results:
            print(f"  {result}")
            if result.status == CheckpointStatus.FAILED:
                all_passed = False
                for error in result.errors[:3]:
                    print(f"    → {error}")
                if len(result.errors) > 3:
                    print(f"    → ... and {len(result.errors) - 3} more")
            elif result.warnings:
                for warning in result.warnings[:2]:
                    print(f"    ⚠ {warning}")

        print("=" * 60)

        if all_passed:
            print("✓ All checkpoints passed - ready for next feature")
        else:
            print("✗ Checkpoint(s) failed - must fix before continuing")

        return all_passed
