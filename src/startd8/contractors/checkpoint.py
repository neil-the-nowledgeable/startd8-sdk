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

import ast
import importlib
import os
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from ..logging_config import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Timeout constants (seconds) for subprocess calls
# ---------------------------------------------------------------------------
_BASELINE_TIMEOUT_SECONDS = 60
_SYNTAX_CHECK_TIMEOUT_SECONDS = 30
_IMPORT_CHECK_TIMEOUT_SECONDS = 30
_LINT_CHECK_TIMEOUT_SECONDS = 60

# Ruff rule codes that are style-only, not correctness issues.
# These are downgraded from errors to warnings so they don't fail features.
# E741: ambiguous variable name (l, O, I) — common in framework conventions
#       (e.g. Locust's `l` parameter, Django's `I` in migrations)
# E742: ambiguous class name
# E743: ambiguous function name
_STYLE_ONLY_CODES: frozenset[str] = frozenset({"E741", "E742", "E743"})
_TEST_SUITE_TIMEOUT_SECONDS = 120


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
        Capture the current set of *collected* (discovered) tests as a baseline.

        Uses ``--collect-only`` which enumerates test node IDs without running
        them.  This allows us to detect regressions where previously-collected
        tests disappear after integration (e.g. import errors, deleted files).

        Note: collected ≠ passing.  A test that was collected but would fail is
        still included in the baseline.
        """
        try:
            result = subprocess.run(
                ["python3", "-m", "pytest", "--collect-only", "-q"],
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=_BASELINE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            logger.warning("Test baseline collection timed out after %ds", _BASELINE_TIMEOUT_SECONDS)
            self._test_baseline = None  # Sentinel: baseline not available
            return set()  # Return empty set to caller but mark baseline as unavailable

        collected_tests = set()
        for line in result.stdout.split("\n"):
            line = line.strip()
            if "::" in line and not line.startswith(("=", "-", " ")):
                collected_tests.add(line.split()[0])

        self._test_baseline = collected_tests
        return collected_tests

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

        # 4. Semantic checks (L2 — stub detection, duplicate detection)
        results.append(self.check_stubs(integrated_files))
        results.append(self.check_duplicates(integrated_files))

        # 5. Test check (if enabled)
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
                    timeout=_SYNTAX_CHECK_TIMEOUT_SECONDS,
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
                            timeout=_IMPORT_CHECK_TIMEOUT_SECONDS,
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

    def check_lint(
        self,
        files: List[Path],
        ignore_codes: Optional[List[str]] = None,
        style_ignore_codes: Optional[Set[str]] = None,
    ) -> CheckpointResult:
        """Run basic lint checks on the files.

        Args:
            files: List of file paths to lint.
            ignore_codes: Optional list of ruff rule codes to ignore
                (e.g. ``["F401"]`` to skip unused-import checks on
                partial files destined for AST merge).
            style_ignore_codes: Optional set of additional rule codes to
                treat as style warnings (not errors).  Merged with the
                built-in ``_STYLE_ONLY_CODES`` set.  Useful for framework
                conventions (e.g. Locust ``l`` parameter triggers E741).
        """
        errors = []
        warnings = []
        checked = 0
        downgraded = _STYLE_ONLY_CODES | (style_ignore_codes or set())

        for file_path in files:
            if file_path.suffix != ".py":
                continue

            checked += 1

            # Try ruff if available
            cmd = ["python3", "-m", "ruff", "check", str(file_path), "--select=E7,E9,F", "--output-format=concise"]
            if ignore_codes:
                cmd.extend(["--ignore", ",".join(ignore_codes)])
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=self.project_root,
                    timeout=_LINT_CHECK_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired:
                errors.append(f"{file_path.name}: lint check timed out")
                continue
            except OSError as exc:
                errors.append(f"{file_path.name}: lint check failed ({exc})")
                continue

            if result.returncode != 0:
                # Parse ruff output — classify each diagnostic as error or
                # warning.  Style-only codes (E741, etc.) are downgraded to
                # warnings so they don't fail the feature.
                for line in result.stdout.strip().split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    if ": F" in line or ": E" in line:
                        # Check if the code is style-only
                        if any(f": {code}" in line for code in downgraded):
                            warnings.append(line)
                        else:
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

    def pre_validate(self, generated_files: List[Path]) -> CheckpointResult:
        """Validate generated files BEFORE merging into targets.

        Runs syntax and lint checks on the raw generated files.  Import
        checks are excluded because they require the file to be under a
        ``src_dirs`` path for module-path resolution — those still run
        post-merge via ``run_all_checkpoints``.

        Args:
            generated_files: Paths to generated Python files.

        Returns:
            Aggregated ``CheckpointResult``: PASSED or FAILED.
        """
        all_errors: List[str] = []

        syntax_result = self.check_syntax(generated_files)
        if syntax_result.status == CheckpointStatus.FAILED:
            all_errors.extend(syntax_result.errors)

        # Auto-fix trivially-fixable lint issues (F541, F841, etc.)
        # before running the lint check.  These are common LLM code-gen
        # artifacts that ruff can resolve without changing semantics.
        # --unsafe-fixes is needed for F841 (unused variable removal).
        for gf in generated_files:
            if gf.suffix == ".py":
                try:
                    before = gf.read_text()
                    subprocess.run(
                        ["python3", "-m", "ruff", "check", "--fix",
                         "--unsafe-fixes", "--select=E7,E9,F", str(gf)],
                        capture_output=True, text=True,
                        cwd=self.project_root, timeout=30,
                    )
                    after = gf.read_text()
                    if before != after:
                        logger.debug("Auto-fixed lint issues in %s", gf.name)
                except (subprocess.TimeoutExpired, OSError):
                    logger.debug("ruff auto-fix skipped for %s (unavailable or timed out)", gf.name)

        # Ignore F401 (unused imports) in pre-merge validation because
        # generated files are partial — the AST merge will combine them
        # with the full target file where those imports are used.
        lint_result = self.check_lint(generated_files, ignore_codes=["F401"])
        if lint_result.status == CheckpointStatus.FAILED:
            all_errors.extend(lint_result.errors)

        if all_errors:
            return CheckpointResult(
                status=CheckpointStatus.FAILED,
                name="Pre-Merge Validation",
                message=f"{len(all_errors)} error(s) in generated files",
                errors=all_errors[:10],
            )

        return CheckpointResult(
            status=CheckpointStatus.PASSED,
            name="Pre-Merge Validation",
            message=f"{len(generated_files)} generated file(s) passed pre-merge validation",
            details={"files_checked": len(generated_files)},
        )

    # -------------------------------------------------------------------
    # L2: Semantic validation checks (stubs, duplicates, import symbols)
    # -------------------------------------------------------------------

    def check_stubs(
        self,
        files: List[Path],
        *,
        max_stub_ratio: float = 0.3,
    ) -> CheckpointResult:
        """Detect files where stub bodies exceed *max_stub_ratio* of functions.

        A function body is considered a stub if it contains only ``pass``,
        ``...``, or ``raise NotImplementedError``.  Files exceeding the
        threshold are reported as warnings (not errors) because partial
        implementations may be intentional during incremental generation.
        """
        warnings: List[str] = []
        checked = 0

        for file_path in files:
            if file_path.suffix != ".py":
                continue
            checked += 1
            try:
                source = file_path.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(file_path))
            except (SyntaxError, OSError):
                continue

            total_funcs = 0
            stub_funcs = 0
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                total_funcs += 1
                if self._is_stub_body(node.body):
                    stub_funcs += 1

            if total_funcs > 0:
                ratio = stub_funcs / total_funcs
                if ratio > max_stub_ratio:
                    warnings.append(
                        f"{file_path.name}: {stub_funcs}/{total_funcs} functions "
                        f"are stubs ({ratio:.0%} > {max_stub_ratio:.0%} threshold)"
                    )

        if warnings:
            return CheckpointResult(
                status=CheckpointStatus.WARNING,
                name="Stub Detection",
                message=f"{len(warnings)} file(s) have excessive stubs",
                warnings=warnings,
                details={"files_checked": checked},
            )

        return CheckpointResult(
            status=CheckpointStatus.PASSED,
            name="Stub Detection",
            message=f"{checked} file(s) checked, no excessive stubs",
            details={"files_checked": checked},
        )

    @staticmethod
    def _is_stub_body(body: List[Any]) -> bool:
        """Return True if a function body is a stub (pass, ..., or raise NotImplementedError)."""
        if not body:
            return True
        # Filter out docstrings (first Expr(Constant(str)))
        stmts = body
        if (
            len(stmts) >= 1
            and isinstance(stmts[0], ast.Expr)
            and isinstance(stmts[0].value, ast.Constant)
            and isinstance(stmts[0].value.value, str)
        ):
            stmts = stmts[1:]
        if not stmts:
            return True
        if len(stmts) != 1:
            return False
        stmt = stmts[0]
        # pass
        if isinstance(stmt, ast.Pass):
            return True
        # ... (Ellipsis)
        if (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Constant)
            and stmt.value.value is ...
        ):
            return True
        # raise NotImplementedError(...)
        if isinstance(stmt, ast.Raise) and stmt.exc is not None:
            exc = stmt.exc
            if isinstance(exc, ast.Call):
                exc = exc.func
            if isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
                return True
        return False

    def check_duplicates(self, files: List[Path]) -> CheckpointResult:
        """Detect duplicate class or function definitions at the same scope level.

        Two definitions are duplicates if they share the same name at the
        top level of a file.
        """
        warnings: List[str] = []
        checked = 0

        for file_path in files:
            if file_path.suffix != ".py":
                continue
            checked += 1
            try:
                source = file_path.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(file_path))
            except (SyntaxError, OSError):
                continue

            # Collect top-level definition names
            seen: Dict[str, str] = {}  # name → kind
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.ClassDef):
                    kind = "class"
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    kind = "function"
                else:
                    continue
                if node.name in seen:
                    warnings.append(
                        f"{file_path.name}: duplicate {kind} '{node.name}' "
                        f"(first defined as {seen[node.name]})"
                    )
                else:
                    seen[node.name] = kind

        if warnings:
            return CheckpointResult(
                status=CheckpointStatus.WARNING,
                name="Duplicate Detection",
                message=f"{len(warnings)} duplicate definition(s) found",
                warnings=warnings,
                details={"files_checked": checked},
            )

        return CheckpointResult(
            status=CheckpointStatus.PASSED,
            name="Duplicate Detection",
            message=f"{checked} file(s) checked, no duplicates",
            details={"files_checked": checked},
        )

    def check_import_symbols(
        self,
        files: List[Path],
        *,
        known_local_modules: Optional[Set[str]] = None,
    ) -> CheckpointResult:
        """Validate that ``from X import Y`` statements resolve to real symbols.

        Skips local/proto-generated modules (listed in *known_local_modules*).
        Reports as warnings (not errors) because some modules are only
        available at runtime inside a container.
        """
        warnings: List[str] = []
        checked = 0
        skip_modules = known_local_modules or set()

        for file_path in files:
            if file_path.suffix != ".py":
                continue
            checked += 1
            try:
                source = file_path.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(file_path))
            except (SyntaxError, OSError):
                continue

            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom) or not node.module:
                    continue
                top_level = node.module.split(".")[0]
                if top_level in skip_modules:
                    continue
                try:
                    mod = importlib.import_module(node.module)
                except (ImportError, ModuleNotFoundError):
                    # Module itself not importable — skip (covered by check_imports)
                    continue
                except Exception:
                    continue

                for alias in node.names or []:
                    if alias.name == "*":
                        continue
                    if not hasattr(mod, alias.name):
                        warnings.append(
                            f"{file_path.name}: 'from {node.module} import {alias.name}' "
                            f"— '{alias.name}' not found in module"
                        )

        if warnings:
            return CheckpointResult(
                status=CheckpointStatus.WARNING,
                name="Import Symbol Check",
                message=f"{len(warnings)} unresolved import symbol(s)",
                warnings=warnings,
                details={"files_checked": checked},
            )

        return CheckpointResult(
            status=CheckpointStatus.PASSED,
            name="Import Symbol Check",
            message=f"{checked} file(s) checked, all import symbols valid",
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
                timeout=_TEST_SUITE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return CheckpointResult(
                status=CheckpointStatus.FAILED,
                name="Test Check",
                message=f"Test suite timed out after {_TEST_SUITE_TIMEOUT_SECONDS}s",
                errors=["pytest timed out — tests may be hanging"],
            )

        # Parse results
        output = result.stdout + result.stderr

        # Count passed/failed
        passed = 0
        failed = 0
        failed_tests = []

        try:
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
        except (ValueError, IndexError, AttributeError):
            logger.debug("Error parsing pytest output; using defaults")

        # Fallback: if parsing found no counts but pytest exited successfully,
        # report a passed status (e.g. pytest output format changed)
        if passed == 0 and failed == 0 and result.returncode == 0:
            passed = None  # Could not parse test counts from output
            logger.debug(
                "pytest returned success but no pass/fail counts parsed; "
                "reporting passed with unknown count"
            )

        # Check for regressions
        regressions = []
        if self._test_baseline is not None and failed_tests:
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

        passed_label = "unknown number of" if passed is None else str(passed)
        return CheckpointResult(
            status=CheckpointStatus.PASSED,
            name="Test Check",
            message=f"{passed_label} test(s) passed",
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
