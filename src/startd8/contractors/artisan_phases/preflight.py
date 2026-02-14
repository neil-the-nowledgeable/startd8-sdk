"""
Pre-Flight Validation Module

Performs comprehensive validation checks before main workflow execution:
- Python/system dependency availability
- API endpoint reachability
- AI model availability
- Workspace directory structure and disk space
- Git repository state
- Environment variable configuration

All checks produce structured results with pass/fail/warning statuses.

Usage:
    from preflight import run_preflight, run_preflight_or_exit, PreFlightConfig

    # Quick validation with defaults
    report = run_preflight()
    print(report.summary)

    # Custom configuration
    config = PreFlightConfig(
        dependencies=[DependencySpec("requests", min_version="2.28.0")],
        env_vars=[EnvVarSpec("API_KEY", is_secret=True)],
    )
    report = run_preflight_or_exit(config)  # Exits on failure

    # Selective categories
    config = PreFlightConfig(
        enabled_categories={CheckCategory.DEPENDENCY, CheckCategory.ENVIRONMENT},
        dependencies=[DependencySpec("numpy")],
    )
"""

import importlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import socket
import ssl
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from startd8.contractors.gate_contracts import GateEmitter

__all__ = [
    "CheckStatus",
    "CheckCategory",
    "CheckResult",
    "PreFlightConfig",
    "PreFlightReport",
    "PreFlightChecker",
    "DependencySpec",
    "EndpointSpec",
    "ModelSpec",
    "WorkspaceSpec",
    "GitSpec",
    "EnvVarSpec",
    "run_preflight",
    "run_preflight_or_exit",
]


# ============================================================================
# Enums
# ============================================================================


class CheckStatus(Enum):
    """Status of a pre-flight check."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


class CheckCategory(Enum):
    """Categories of pre-flight checks."""

    DEPENDENCY = "dependency"
    PROTOCOL = "protocol"
    MODEL = "model"
    WORKSPACE = "workspace"
    GIT = "git"
    ENVIRONMENT = "environment"


# ============================================================================
# Dataclasses — Specifications
# ============================================================================


@dataclass
class DependencySpec:
    """Specification for a required dependency (Python package or CLI tool)."""

    name: str
    """Package or CLI tool name."""

    min_version: Optional[str] = None
    """Minimum version string (e.g., ``'1.2.0'``). ``None`` means any version."""

    is_cli_tool: bool = False
    """If ``True``, check PATH for a CLI tool; otherwise check Python import."""

    required: bool = True
    """If ``False``, absence produces WARN instead of FAIL."""


@dataclass
class EndpointSpec:
    """Specification for a required endpoint/protocol check."""

    url: str
    """Full URL (``http``/``https``) or ``'host:port'`` for raw TCP check."""

    name: Optional[str] = None
    """Human-readable name; defaults to *url* when ``None``."""

    timeout_seconds: float = 30.0
    """Connection timeout in seconds."""

    expected_status_codes: Tuple[int, ...] = (200,)
    """Acceptable HTTP status codes."""

    method: str = "GET"
    """HTTP method (``GET`` or ``HEAD``)."""

    required: bool = True
    """If ``False``, unreachable endpoints produce WARN instead of FAIL."""


@dataclass
class ModelSpec:
    """Specification for a required AI model."""

    model_id: str
    """Model identifier (e.g., ``'gpt-4'``, ``'claude-3-opus'``, or a local path)."""

    provider: str = "openai"
    """Provider key: ``'openai'``, ``'anthropic'``, ``'ollama'``, ``'local_file'``."""

    api_base_url: Optional[str] = None
    """Override base URL for the provider's API."""

    api_key_env_var: Optional[str] = None
    """Environment variable name that holds the API key."""

    required: bool = True
    """If ``False``, unavailable models produce WARN instead of FAIL."""


@dataclass
class WorkspaceSpec:
    """Specification for workspace validation."""

    path: str = "."
    """Workspace root path."""

    required_subdirs: List[str] = field(default_factory=list)
    """Subdirectories that must exist (e.g., ``['src', 'tests']``)."""

    required_files: List[str] = field(default_factory=list)
    """Files that must exist (e.g., ``['pyproject.toml']``)."""

    min_disk_space_mb: int = 100
    """Minimum free disk space in megabytes."""

    must_be_writable: bool = True
    """Fail if workspace is not writable."""


@dataclass
class GitSpec:
    """Specification for git state validation."""

    path: str = "."
    """Path to the git repository root."""

    require_clean: bool = False
    """Fail if there are uncommitted changes."""

    require_branch: Optional[str] = None
    """Fail if not on this specific branch."""

    require_repo: bool = True
    """Fail if the path is not a git repository."""


@dataclass
class EnvVarSpec:
    """Specification for a required environment variable."""

    name: str
    """Variable name."""

    required: bool = True
    """If ``False``, absence produces WARN instead of FAIL."""

    must_be_non_empty: bool = True
    """Fail/warn if set but empty."""

    is_secret: bool = False
    """Mask the value in all output (never reveal the actual content)."""


# ============================================================================
# Dataclasses — Results & Report
# ============================================================================


@dataclass
class CheckResult:
    """Result of a single pre-flight check."""

    category: CheckCategory
    """Check category."""

    name: str
    """Short check name (e.g., ``'python_dep:requests'``)."""

    status: CheckStatus
    """Pass, warn, fail, or skip."""

    message: str
    """Human-readable result description."""

    details: Optional[Dict[str, Any]] = None
    """Structured extra information."""

    duration_ms: Optional[float] = None
    """How long the check took in milliseconds."""


@dataclass
class PreFlightConfig:
    """Configuration for all pre-flight checks."""

    dependencies: List[DependencySpec] = field(default_factory=list)
    """Python packages and CLI tools to check."""

    endpoints: List[EndpointSpec] = field(default_factory=list)
    """API endpoints and services to verify."""

    models: List[ModelSpec] = field(default_factory=list)
    """AI/LLM models to validate."""

    workspace: Optional[WorkspaceSpec] = field(default_factory=WorkspaceSpec)
    """Workspace directory validation. ``None`` to skip."""

    git: Optional[GitSpec] = field(default_factory=GitSpec)
    """Git repository state validation. ``None`` to skip."""

    env_vars: List[EnvVarSpec] = field(default_factory=list)
    """Environment variables to check."""

    enabled_categories: Optional[Set[CheckCategory]] = None
    """Categories to run. ``None`` means *all* categories are enabled."""

    fail_fast: bool = False
    """Stop on first FAIL result."""


@dataclass
class PreFlightReport:
    """Aggregated report of all pre-flight checks."""

    results: List[CheckResult]
    """All individual check results."""

    started_at: str
    """ISO 8601 timestamp of start (UTC)."""

    finished_at: str
    """ISO 8601 timestamp of finish (UTC)."""

    total_duration_ms: float
    """Total wall-clock duration in milliseconds."""

    # -- Computed properties -------------------------------------------------

    @property
    def passed(self) -> bool:
        """``True`` when no results have status FAIL."""
        return not any(r.status == CheckStatus.FAIL for r in self.results)

    @property
    def failed_checks(self) -> List[CheckResult]:
        """Return all checks with FAIL status."""
        return [r for r in self.results if r.status == CheckStatus.FAIL]

    @property
    def warnings(self) -> List[CheckResult]:
        """Return all checks with WARN status."""
        return [r for r in self.results if r.status == CheckStatus.WARN]

    @property
    def summary(self) -> str:
        """Return a human-readable summary string suitable for terminal output."""
        lines: List[str] = ["Pre-Flight Check Report", "=" * 70]

        for result in self.results:
            icon = self._status_icon(result.status)
            lines.append(f"{icon} {result.status.value.upper():4s}: {result.name}")
            lines.append(f"   {result.message}")
            if result.duration_ms is not None:
                lines.append(f"   (took {result.duration_ms:.1f} ms)")

        lines.append("")
        lines.append("=" * 70)

        counts = {s: sum(1 for r in self.results if r.status == s) for s in CheckStatus}
        verdict = "✅ PASSED" if self.passed else "❌ FAILED"

        parts = [f"{counts[CheckStatus.PASS]} passed"]
        if counts[CheckStatus.WARN]:
            parts.append(f"{counts[CheckStatus.WARN]} warnings")
        if counts[CheckStatus.FAIL]:
            parts.append(f"{counts[CheckStatus.FAIL]} failures")
        if counts[CheckStatus.SKIP]:
            parts.append(f"{counts[CheckStatus.SKIP]} skipped")

        lines.append(f"{verdict}: {', '.join(parts)}")
        lines.append(f"Total time: {self.total_duration_ms:.1f} ms")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "passed": self.passed,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_duration_ms": self.total_duration_ms,
            "counts": {
                "pass": sum(1 for r in self.results if r.status == CheckStatus.PASS),
                "warn": sum(1 for r in self.results if r.status == CheckStatus.WARN),
                "fail": sum(1 for r in self.results if r.status == CheckStatus.FAIL),
                "skip": sum(1 for r in self.results if r.status == CheckStatus.SKIP),
            },
            "results": [
                {
                    "category": result.category.value,
                    "name": result.name,
                    "status": result.status.value,
                    "message": result.message,
                    "details": result.details,
                    "duration_ms": result.duration_ms,
                }
                for result in self.results
            ],
        }

    @staticmethod
    def _status_icon(status: CheckStatus) -> str:
        return {
            CheckStatus.PASS: "✅",
            CheckStatus.WARN: "⚠️ ",
            CheckStatus.FAIL: "❌",
            CheckStatus.SKIP: "⏭️ ",
        }.get(status, "❓")


# ============================================================================
# Internal Helpers
# ============================================================================


def _parse_version(version_str: str) -> Tuple[int, ...]:
    """Parse ``'1.2.3'`` into ``(1, 2, 3)`` for comparison.

    Strips a leading ``'v'``/``'V'``, splits on ``'.'``, and extracts the
    leading numeric portion of each segment.
    """
    version_str = version_str.lstrip("vV").strip()
    parts: List[int] = []
    for segment in version_str.split("."):
        match = re.match(r"(\d+)", segment)
        if match:
            parts.append(int(match.group(1)))
        else:
            break
    return tuple(parts) if parts else (0,)


def _compare_versions(installed: str, required: str) -> bool:
    """Return ``True`` if *installed* >= *required*."""
    try:
        return _parse_version(installed) >= _parse_version(required)
    except Exception:
        return False


def _get_cli_tool_version(tool_name: str) -> Optional[str]:
    """Try ``<tool> --version`` and extract a semver-like version string."""
    try:
        result = subprocess.run(
            [tool_name, "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            combined = result.stdout + result.stderr
            match = re.search(r"(\d+\.\d+(?:\.\d+)?)", combined)
            if match:
                return match.group(1)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def _elapsed_ms(start: float) -> float:
    """Milliseconds since *start* (from ``time.monotonic()``)."""
    return (time.monotonic() - start) * 1000.0


def _utc_iso() -> str:
    """Current UTC time in ISO 8601 format with ``Z`` suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _status_for(required: bool) -> CheckStatus:
    """Return FAIL if *required*, otherwise WARN."""
    return CheckStatus.FAIL if required else CheckStatus.WARN


# ============================================================================
# PreFlightChecker
# ============================================================================


class PreFlightChecker:
    """Orchestrates all pre-flight validation checks.

    Typical usage::

        checker = PreFlightChecker(config)
        report = checker.run_all()
        if not report.passed:
            print(report.summary, file=sys.stderr)
            raise SystemExit(1)
    """

    def __init__(self, config: Optional[PreFlightConfig] = None) -> None:
        self.config = config or PreFlightConfig()
        self._results: List[CheckResult] = []

    # -- Public entry point --------------------------------------------------

    def run_all(self) -> PreFlightReport:
        """Execute all enabled check categories and return an aggregated report."""
        self._results = []
        started_at = _utc_iso()
        wall_start = time.monotonic()

        category_runners = {
            CheckCategory.DEPENDENCY: self.check_dependencies,
            CheckCategory.PROTOCOL: self.check_endpoints,
            CheckCategory.MODEL: self.check_models,
            CheckCategory.WORKSPACE: self.check_workspace,
            CheckCategory.GIT: self.check_git,
            CheckCategory.ENVIRONMENT: self.check_environment,
        }

        for category, runner in category_runners.items():
            if not self._is_category_enabled(category):
                continue

            try:
                results = runner()
                self._results.extend(results)
            except Exception as exc:
                self._results.append(
                    CheckResult(
                        category=category,
                        name=f"{category.value}:unexpected_error",
                        status=CheckStatus.FAIL,
                        message=f"Unexpected error in {category.value} checks: {exc}",
                        details={
                            "error": str(exc),
                            "traceback": traceback.format_exc(),
                        },
                    )
                )

            if self.config.fail_fast and any(
                r.status == CheckStatus.FAIL for r in self._results
            ):
                break

        finished_at = _utc_iso()
        total_ms = _elapsed_ms(wall_start)

        report = PreFlightReport(
            results=self._results,
            started_at=started_at,
            finished_at=finished_at,
            total_duration_ms=total_ms,
        )

        try:
            # Emit quality gate result (Item 10)
            # Try to get workflow_id from config if available, otherwise fallback
            workflow_id = getattr(self.config, "workflow_id", "unknown")
            gate_result = GateEmitter.from_preflight_report(
                report=report,
                workflow_id=workflow_id,
            )
            GateEmitter.emit(gate_result)
        except Exception:
            pass  # Fail safe

        return report

    def _is_category_enabled(self, category: CheckCategory) -> bool:
        if self.config.enabled_categories is None:
            return True
        return category in self.config.enabled_categories

    def _should_stop(self, results: List[CheckResult]) -> bool:
        """Return ``True`` when fail-fast is active and a failure exists."""
        return self.config.fail_fast and any(
            r.status == CheckStatus.FAIL for r in results
        )

    # ========================================================================
    # Dependency Checks
    # ========================================================================

    def check_dependencies(self) -> List[CheckResult]:
        """Check all specified dependencies (Python packages and CLI tools)."""
        results: List[CheckResult] = []
        for spec in self.config.dependencies:
            if self._should_stop(results):
                break
            try:
                fn = (
                    self._check_cli_tool
                    if spec.is_cli_tool
                    else self._check_python_dependency
                )
                results.append(fn(spec))
            except Exception as exc:
                results.append(
                    CheckResult(
                        category=CheckCategory.DEPENDENCY,
                        name=f"dep:{spec.name}",
                        status=CheckStatus.FAIL,
                        message=f"Unexpected error checking {spec.name}: {exc}",
                        details={"error": str(exc)},
                    )
                )
        return results

    def _check_python_dependency(self, spec: DependencySpec) -> CheckResult:
        start = time.monotonic()
        check_name = f"python_dep:{spec.name}"

        # Attempt import
        try:
            importlib.import_module(spec.name)
        except ImportError:
            return CheckResult(
                category=CheckCategory.DEPENDENCY,
                name=check_name,
                status=_status_for(spec.required),
                message=(
                    f"Package '{spec.name}' not found"
                    " (not installed or not importable)"
                ),
                duration_ms=_elapsed_ms(start),
            )

        # Attempt version lookup
        installed_version: Optional[str] = None
        try:
            installed_version = importlib.metadata.version(spec.name)
        except importlib.metadata.PackageNotFoundError:
            # Importable but no metadata (namespace packages, etc.)
            if spec.min_version:
                return CheckResult(
                    category=CheckCategory.DEPENDENCY,
                    name=check_name,
                    status=CheckStatus.WARN,
                    message=(
                        f"Package '{spec.name}' is importable but version metadata "
                        f"not found; cannot verify >= {spec.min_version}"
                    ),
                    details={"package": spec.name},
                    duration_ms=_elapsed_ms(start),
                )
            return CheckResult(
                category=CheckCategory.DEPENDENCY,
                name=check_name,
                status=CheckStatus.PASS,
                message=(
                    f"Package '{spec.name}' is importable"
                    " (version metadata unavailable)"
                ),
                details={"package": spec.name},
                duration_ms=_elapsed_ms(start),
            )
        except Exception as exc:
            return CheckResult(
                category=CheckCategory.DEPENDENCY,
                name=check_name,
                status=CheckStatus.WARN,
                message=(
                    f"Package '{spec.name}' imported"
                    f" but version check failed: {exc}"
                ),
                duration_ms=_elapsed_ms(start),
            )

        # Version comparison
        if spec.min_version:
            if _compare_versions(installed_version, spec.min_version):
                return CheckResult(
                    category=CheckCategory.DEPENDENCY,
                    name=check_name,
                    status=CheckStatus.PASS,
                    message=(
                        f"Package '{spec.name}'"
                        f" v{installed_version}"
                        f" >= {spec.min_version}"
                    ),
                    details={
                        "installed_version": installed_version,
                        "required_version": spec.min_version,
                    },
                    duration_ms=_elapsed_ms(start),
                )
            return CheckResult(
                category=CheckCategory.DEPENDENCY,
                name=check_name,
                status=_status_for(spec.required),
                message=(
                    f"Package '{spec.name}' v{installed_version} "
                    f"< {spec.min_version} (requirement not met)"
                ),
                details={
                    "installed_version": installed_version,
                    "required_version": spec.min_version,
                },
                duration_ms=_elapsed_ms(start),
            )

        return CheckResult(
            category=CheckCategory.DEPENDENCY,
            name=check_name,
            status=CheckStatus.PASS,
            message=f"Package '{spec.name}' v{installed_version} is installed",
            details={"installed_version": installed_version},
            duration_ms=_elapsed_ms(start),
        )

    def _check_cli_tool(self, spec: DependencySpec) -> CheckResult:
        start = time.monotonic()
        check_name = f"cli_tool:{spec.name}"

        tool_path = shutil.which(spec.name)
        if not tool_path and platform.system() == "Windows":
            tool_path = shutil.which(spec.name + ".exe")

        if not tool_path:
            return CheckResult(
                category=CheckCategory.DEPENDENCY,
                name=check_name,
                status=_status_for(spec.required),
                message=f"CLI tool '{spec.name}' not found on PATH",
                details={"tool": spec.name},
                duration_ms=_elapsed_ms(start),
            )

        version = _get_cli_tool_version(spec.name)
        base_details: Dict[str, Any] = {"tool": spec.name, "path": tool_path}

        if spec.min_version and version:
            base_details.update(
                installed_version=version, required_version=spec.min_version
            )
            if _compare_versions(version, spec.min_version):
                return CheckResult(
                    category=CheckCategory.DEPENDENCY,
                    name=check_name,
                    status=CheckStatus.PASS,
                    message=f"CLI tool '{spec.name}' v{version} >= {spec.min_version}",
                    details=base_details,
                    duration_ms=_elapsed_ms(start),
                )
            return CheckResult(
                category=CheckCategory.DEPENDENCY,
                name=check_name,
                status=_status_for(spec.required),
                message=f"CLI tool '{spec.name}' v{version} < {spec.min_version}",
                details=base_details,
                duration_ms=_elapsed_ms(start),
            )

        if version:
            base_details["version"] = version
            msg = f"CLI tool '{spec.name}' v{version} is available"
        else:
            msg = f"CLI tool '{spec.name}' is available (version unknown)"

        return CheckResult(
            category=CheckCategory.DEPENDENCY,
            name=check_name,
            status=CheckStatus.PASS,
            message=msg,
            details=base_details,
            duration_ms=_elapsed_ms(start),
        )

    # ========================================================================
    # Protocol / Endpoint Checks
    # ========================================================================

    def check_endpoints(self) -> List[CheckResult]:
        """Check all specified endpoints for reachability."""
        results: List[CheckResult] = []
        for spec in self.config.endpoints:
            if self._should_stop(results):
                break
            try:
                if spec.url.startswith(("http://", "https://")):
                    results.append(self._check_http_endpoint(spec))
                else:
                    results.append(self._check_tcp_endpoint(spec))
            except Exception as exc:
                results.append(
                    CheckResult(
                        category=CheckCategory.PROTOCOL,
                        name=f"endpoint:{spec.name or spec.url}",
                        status=CheckStatus.FAIL,
                        message=f"Unexpected error checking endpoint: {exc}",
                        details={"error": str(exc)},
                    )
                )
        return results

    def _check_http_endpoint(self, spec: EndpointSpec) -> CheckResult:
        start = time.monotonic()
        label = spec.name or spec.url

        try:
            request = Request(spec.url, method=spec.method)
            with urlopen(request, timeout=spec.timeout_seconds) as response:
                status_code = response.status

            if status_code in spec.expected_status_codes:
                return CheckResult(
                    category=CheckCategory.PROTOCOL,
                    name=f"endpoint:{label}",
                    status=CheckStatus.PASS,
                    message=f"Endpoint reachable (HTTP {status_code})",
                    details={"url": spec.url, "status_code": status_code},
                    duration_ms=_elapsed_ms(start),
                )
            return CheckResult(
                category=CheckCategory.PROTOCOL,
                name=f"endpoint:{label}",
                status=_status_for(spec.required),
                message=(
                    f"Unexpected status {status_code} "
                    f"(expected {spec.expected_status_codes})"
                ),
                details={"url": spec.url, "status_code": status_code},
                duration_ms=_elapsed_ms(start),
            )

        except HTTPError as exc:
            # HTTPError is a subclass of URLError — check it first
            if exc.code in spec.expected_status_codes:
                return CheckResult(
                    category=CheckCategory.PROTOCOL,
                    name=f"endpoint:{label}",
                    status=CheckStatus.PASS,
                    message=f"Endpoint reachable (HTTP {exc.code})",
                    details={"url": spec.url, "status_code": exc.code},
                    duration_ms=_elapsed_ms(start),
                )
            return CheckResult(
                category=CheckCategory.PROTOCOL,
                name=f"endpoint:{label}",
                status=_status_for(spec.required),
                message=f"HTTP error: {exc.code} {exc.reason}",
                details={"url": spec.url, "http_error": f"{exc.code} {exc.reason}"},
                duration_ms=_elapsed_ms(start),
            )
        except ssl.SSLError as exc:
            return CheckResult(
                category=CheckCategory.PROTOCOL,
                name=f"endpoint:{label}",
                status=_status_for(spec.required),
                message=f"SSL certificate error: {exc}",
                details={"url": spec.url, "ssl_error": str(exc)},
                duration_ms=_elapsed_ms(start),
            )
        except (socket.timeout, TimeoutError):
            return CheckResult(
                category=CheckCategory.PROTOCOL,
                name=f"endpoint:{label}",
                status=_status_for(spec.required),
                message=f"Timeout after {spec.timeout_seconds}s",
                details={"url": spec.url, "timeout_seconds": spec.timeout_seconds},
                duration_ms=_elapsed_ms(start),
            )
        except URLError as exc:
            reason = str(getattr(exc, "reason", exc))
            return CheckResult(
                category=CheckCategory.PROTOCOL,
                name=f"endpoint:{label}",
                status=_status_for(spec.required),
                message=f"Connection error: {reason}",
                details={"url": spec.url, "error": reason},
                duration_ms=_elapsed_ms(start),
            )
        except Exception as exc:
            return CheckResult(
                category=CheckCategory.PROTOCOL,
                name=f"endpoint:{label}",
                status=_status_for(spec.required),
                message=f"Unexpected error: {exc}",
                details={"url": spec.url, "error": str(exc)},
                duration_ms=_elapsed_ms(start),
            )

    def _check_tcp_endpoint(self, spec: EndpointSpec) -> CheckResult:
        start = time.monotonic()
        label = spec.name or spec.url

        # Parse host:port
        parts = spec.url.rsplit(":", 1)
        if len(parts) != 2:
            return CheckResult(
                category=CheckCategory.PROTOCOL,
                name=f"endpoint:{label}",
                status=CheckStatus.FAIL,
                message=f"Invalid host:port format: {spec.url}",
                details={"url": spec.url},
                duration_ms=_elapsed_ms(start),
            )

        host, port_str = parts
        try:
            port = int(port_str)
        except ValueError:
            return CheckResult(
                category=CheckCategory.PROTOCOL,
                name=f"endpoint:{label}",
                status=CheckStatus.FAIL,
                message=f"Invalid port number: {port_str}",
                details={"url": spec.url, "port": port_str},
                duration_ms=_elapsed_ms(start),
            )

        try:
            with socket.create_connection((host, port), timeout=spec.timeout_seconds):
                pass
            return CheckResult(
                category=CheckCategory.PROTOCOL,
                name=f"endpoint:{label}",
                status=CheckStatus.PASS,
                message=f"TCP connection successful to {host}:{port}",
                details={"host": host, "port": port},
                duration_ms=_elapsed_ms(start),
            )
        except socket.timeout:
            return CheckResult(
                category=CheckCategory.PROTOCOL,
                name=f"endpoint:{label}",
                status=_status_for(spec.required),
                message=f"TCP timeout to {host}:{port} after {spec.timeout_seconds}s",
                details={
                    "host": host,
                    "port": port,
                    "timeout_seconds": spec.timeout_seconds,
                },
                duration_ms=_elapsed_ms(start),
            )
        except (socket.error, ConnectionRefusedError, OSError) as exc:
            return CheckResult(
                category=CheckCategory.PROTOCOL,
                name=f"endpoint:{label}",
                status=_status_for(spec.required),
                message=f"TCP connection failed to {host}:{port}: {exc}",
                details={"host": host, "port": port, "error": str(exc)},
                duration_ms=_elapsed_ms(start),
            )

    # ========================================================================
    # Model Availability Checks
    # ========================================================================

    def check_models(self) -> List[CheckResult]:
        """Check all specified AI/LLM models."""
        results: List[CheckResult] = []
        _dispatch = {
            "openai": self._check_openai_model,
            "anthropic": self._check_anthropic_model,
            "ollama": self._check_ollama_model,
            "local_file": self._check_local_model_file,
        }

        for spec in self.config.models:
            if self._should_stop(results):
                break
            try:
                handler = _dispatch.get(spec.provider)
                if handler is None:
                    results.append(
                        CheckResult(
                            category=CheckCategory.MODEL,
                            name=f"model:{spec.model_id}",
                            status=CheckStatus.FAIL,
                            message=f"Unknown provider: {spec.provider}",
                            details={"provider": spec.provider, "model": spec.model_id},
                        )
                    )
                else:
                    results.append(handler(spec))
            except Exception as exc:
                results.append(
                    CheckResult(
                        category=CheckCategory.MODEL,
                        name=f"model:{spec.model_id}",
                        status=CheckStatus.FAIL,
                        message=f"Unexpected error checking model: {exc}",
                        details={"error": str(exc)},
                    )
                )
        return results

    def _check_openai_model(self, spec: ModelSpec) -> CheckResult:
        start = time.monotonic()
        api_key_env = spec.api_key_env_var or "OPENAI_API_KEY"
        api_key = os.environ.get(api_key_env)

        if not api_key:
            return CheckResult(
                category=CheckCategory.MODEL,
                name=f"model:{spec.model_id}",
                status=_status_for(spec.required),
                message=f"API key not found in env var '{api_key_env}'",
                details={"model": spec.model_id, "provider": "openai"},
                duration_ms=_elapsed_ms(start),
            )

        base_url = (spec.api_base_url or "https://api.openai.com/v1").rstrip("/")
        url = f"{base_url}/models"

        try:
            request = Request(url)
            request.add_header("Authorization", f"Bearer {api_key}")
            with urlopen(request, timeout=30.0) as response:
                data = json.loads(response.read().decode())

            models = [m["id"] for m in data.get("data", [])]

            if spec.model_id in models:
                return CheckResult(
                    category=CheckCategory.MODEL,
                    name=f"model:{spec.model_id}",
                    status=CheckStatus.PASS,
                    message=f"Model '{spec.model_id}' is available via OpenAI API",
                    details={"model": spec.model_id, "provider": "openai"},
                    duration_ms=_elapsed_ms(start),
                )
            return CheckResult(
                category=CheckCategory.MODEL,
                name=f"model:{spec.model_id}",
                status=_status_for(spec.required),
                message=f"Model '{spec.model_id}' not found in available models",
                details={
                    "model": spec.model_id,
                    "provider": "openai",
                    "sample_available": models[:5],
                },
                duration_ms=_elapsed_ms(start),
            )

        except HTTPError as exc:
            return CheckResult(
                category=CheckCategory.MODEL,
                name=f"model:{spec.model_id}",
                status=_status_for(spec.required),
                message=f"API request failed: HTTP {exc.code}",
                details={
                    "model": spec.model_id,
                    "provider": "openai",
                    "http_error": exc.code,
                },
                duration_ms=_elapsed_ms(start),
            )
        except (socket.timeout, TimeoutError):
            return CheckResult(
                category=CheckCategory.MODEL,
                name=f"model:{spec.model_id}",
                status=_status_for(spec.required),
                message="API request timeout",
                details={"model": spec.model_id, "provider": "openai"},
                duration_ms=_elapsed_ms(start),
            )
        except Exception as exc:
            return CheckResult(
                category=CheckCategory.MODEL,
                name=f"model:{spec.model_id}",
                status=_status_for(spec.required),
                message=f"API request error: {exc}",
                details={
                    "model": spec.model_id,
                    "provider": "openai",
                    "error": str(exc),
                },
                duration_ms=_elapsed_ms(start),
            )

    def _check_anthropic_model(self, spec: ModelSpec) -> CheckResult:
        """Validate Anthropic model.

        Anthropic does not expose a public model-list endpoint, so we verify
        the API key exists and compare against a list of known model families.
        """
        start = time.monotonic()
        api_key_env = spec.api_key_env_var or "ANTHROPIC_API_KEY"
        api_key = os.environ.get(api_key_env)

        if not api_key:
            return CheckResult(
                category=CheckCategory.MODEL,
                name=f"model:{spec.model_id}",
                status=_status_for(spec.required),
                message=f"API key not found in env var '{api_key_env}'",
                details={"model": spec.model_id, "provider": "anthropic"},
                duration_ms=_elapsed_ms(start),
            )

        # Known model family prefixes (new models added frequently)
        known_prefixes = (
            # Current generation (4.5/4.6) — name-first convention
            "claude-opus-4",
            "claude-sonnet-4",
            "claude-haiku-4",
            # Legacy generation (3.x) — version-first convention
            "claude-3-opus",
            "claude-3-sonnet",
            "claude-3-haiku",
            "claude-3.5-sonnet",
            "claude-3.5-haiku",
            "claude-3-5-sonnet",
            "claude-3-5-haiku",
            "claude-4",
            "claude-2.1",
            "claude-2",
            "claude-instant",
        )

        if any(spec.model_id.startswith(p) for p in known_prefixes):
            return CheckResult(
                category=CheckCategory.MODEL,
                name=f"model:{spec.model_id}",
                status=CheckStatus.PASS,
                message=(
                    f"Model '{spec.model_id}' matches"
                    " a known Anthropic model family"
                ),
                details={"model": spec.model_id, "provider": "anthropic"},
                duration_ms=_elapsed_ms(start),
            )

        return CheckResult(
            category=CheckCategory.MODEL,
            name=f"model:{spec.model_id}",
            status=CheckStatus.WARN,
            message=f"Model '{spec.model_id}' not in known list (may still be valid)",
            details={"model": spec.model_id, "provider": "anthropic"},
            duration_ms=_elapsed_ms(start),
        )

    def _check_ollama_model(self, spec: ModelSpec) -> CheckResult:
        start = time.monotonic()
        base_url = (spec.api_base_url or "http://localhost:11434").rstrip("/")
        url = f"{base_url}/api/tags"

        try:
            with urlopen(url, timeout=30.0) as response:
                data = json.loads(response.read().decode())

            model_names: List[str] = []
            for m in data.get("models", []):
                name = m.get("name", "")
                model_names.append(name)
                # Also store the base name (without tag)
                if ":" in name:
                    model_names.append(name.split(":")[0])

            model_base = spec.model_id.split(":")[0]
            if spec.model_id in model_names or model_base in model_names:
                return CheckResult(
                    category=CheckCategory.MODEL,
                    name=f"model:{spec.model_id}",
                    status=CheckStatus.PASS,
                    message=f"Model '{spec.model_id}' is available in Ollama",
                    details={"model": spec.model_id, "provider": "ollama"},
                    duration_ms=_elapsed_ms(start),
                )
            return CheckResult(
                category=CheckCategory.MODEL,
                name=f"model:{spec.model_id}",
                status=_status_for(spec.required),
                message=f"Model '{spec.model_id}' not found in Ollama",
                details={
                    "model": spec.model_id,
                    "provider": "ollama",
                    "available": sorted(set(model_names)),
                },
                duration_ms=_elapsed_ms(start),
            )

        except (socket.timeout, TimeoutError, ConnectionRefusedError, URLError):
            return CheckResult(
                category=CheckCategory.MODEL,
                name=f"model:{spec.model_id}",
                status=_status_for(spec.required),
                message=f"Ollama not reachable (expected at {base_url})",
                details={"model": spec.model_id, "provider": "ollama", "url": base_url},
                duration_ms=_elapsed_ms(start),
            )
        except Exception as exc:
            return CheckResult(
                category=CheckCategory.MODEL,
                name=f"model:{spec.model_id}",
                status=_status_for(spec.required),
                message=f"Error checking Ollama: {exc}",
                details={
                    "model": spec.model_id,
                    "provider": "ollama",
                    "error": str(exc),
                },
                duration_ms=_elapsed_ms(start),
            )

    def _check_local_model_file(self, spec: ModelSpec) -> CheckResult:
        start = time.monotonic()
        file_path = Path(spec.model_id)

        if file_path.exists():
            size_mb = (
                file_path.stat().st_size / (1024 * 1024)
                if file_path.is_file()
                else None
            )
            return CheckResult(
                category=CheckCategory.MODEL,
                name=f"model:{spec.model_id}",
                status=CheckStatus.PASS,
                message=f"Local model file exists: {spec.model_id}",
                details={
                    "path": str(file_path.resolve()),
                    "exists": True,
                    "size_mb": round(size_mb, 2) if size_mb is not None else None,
                },
                duration_ms=_elapsed_ms(start),
            )
        return CheckResult(
            category=CheckCategory.MODEL,
            name=f"model:{spec.model_id}",
            status=_status_for(spec.required),
            message=f"Local model file not found: {spec.model_id}",
            details={"path": str(file_path), "exists": False},
            duration_ms=_elapsed_ms(start),
        )

    # ========================================================================
    # Workspace Checks
    # ========================================================================

    def check_workspace(self) -> List[CheckResult]:
        """Check workspace directory structure, writability, and disk space."""
        if self.config.workspace is None:
            return []

        ws = self.config.workspace
        results: List[CheckResult] = []

        # Root directory existence
        result = self._check_directory_exists(ws.path)
        results.append(result)
        if result.status == CheckStatus.FAIL:
            return results

        # Writable
        if ws.must_be_writable:
            results.append(self._check_writable(ws.path))
            if self._should_stop(results):
                return results

        # Required subdirectories
        for subdir in ws.required_subdirs:
            if self._should_stop(results):
                break
            full_path = os.path.join(ws.path, subdir)
            exists = os.path.isdir(full_path)
            results.append(
                CheckResult(
                    category=CheckCategory.WORKSPACE,
                    name=f"workspace:subdir:{subdir}",
                    status=CheckStatus.PASS if exists else CheckStatus.FAIL,
                    message=(
                        f"Required subdirectory exists: {subdir}"
                        if exists
                        else f"Required subdirectory missing: {subdir}"
                    ),
                    details={"path": os.path.abspath(full_path)},
                )
            )

        # Required files
        for filename in ws.required_files:
            if self._should_stop(results):
                break
            full_path = os.path.join(ws.path, filename)
            exists = os.path.isfile(full_path)
            results.append(
                CheckResult(
                    category=CheckCategory.WORKSPACE,
                    name=f"workspace:file:{filename}",
                    status=CheckStatus.PASS if exists else CheckStatus.FAIL,
                    message=(
                        f"Required file exists: {filename}"
                        if exists
                        else f"Required file missing: {filename}"
                    ),
                    details={"path": os.path.abspath(full_path)},
                )
            )

        # Disk space
        results.append(self._check_disk_space(ws.path, ws.min_disk_space_mb))
        return results

    def _check_directory_exists(self, path: str) -> CheckResult:
        start = time.monotonic()
        abs_path = os.path.abspath(path)

        if os.path.isdir(path):
            return CheckResult(
                category=CheckCategory.WORKSPACE,
                name="workspace:exists",
                status=CheckStatus.PASS,
                message=f"Workspace directory exists: {abs_path}",
                details={"path": abs_path},
                duration_ms=_elapsed_ms(start),
            )
        if os.path.exists(path):
            return CheckResult(
                category=CheckCategory.WORKSPACE,
                name="workspace:exists",
                status=CheckStatus.FAIL,
                message=f"Path exists but is not a directory: {abs_path}",
                details={"path": abs_path},
                duration_ms=_elapsed_ms(start),
            )
        return CheckResult(
            category=CheckCategory.WORKSPACE,
            name="workspace:exists",
            status=CheckStatus.FAIL,
            message=f"Workspace directory does not exist: {abs_path}",
            details={"path": abs_path},
            duration_ms=_elapsed_ms(start),
        )

    def _check_writable(self, path: str) -> CheckResult:
        start = time.monotonic()
        abs_path = os.path.abspath(path)
        writable = os.access(path, os.W_OK)
        return CheckResult(
            category=CheckCategory.WORKSPACE,
            name="workspace:writable",
            status=CheckStatus.PASS if writable else CheckStatus.FAIL,
            message=(
                f"Workspace directory is writable: {abs_path}"
                if writable
                else f"Workspace directory is not writable: {abs_path}"
            ),
            details={"path": abs_path},
            duration_ms=_elapsed_ms(start),
        )

    def _check_disk_space(self, path: str, min_mb: int) -> CheckResult:
        start = time.monotonic()
        abs_path = os.path.abspath(path)

        try:
            usage = shutil.disk_usage(path)
            free_mb = usage.free / (1024 * 1024)
            free_gb = free_mb / 1024

            if free_mb >= min_mb:
                return CheckResult(
                    category=CheckCategory.WORKSPACE,
                    name="workspace:disk_space",
                    status=CheckStatus.PASS,
                    message=(
                        f"Sufficient disk space:"
                        f" {free_gb:.1f} GB free"
                        f" (>= {min_mb} MB required)"
                    ),
                    details={
                        "path": abs_path,
                        "free_mb": round(free_mb, 2),
                        "free_gb": round(free_gb, 2),
                        "required_mb": min_mb,
                        "total_gb": round(usage.total / (1024**3), 2),
                    },
                    duration_ms=_elapsed_ms(start),
                )
            return CheckResult(
                category=CheckCategory.WORKSPACE,
                name="workspace:disk_space",
                status=CheckStatus.FAIL,
                message=(
                    f"Insufficient disk space:"
                    f" {free_mb:.1f} MB free"
                    f" < {min_mb} MB required"
                ),
                details={
                    "path": abs_path,
                    "free_mb": round(free_mb, 2),
                    "required_mb": min_mb,
                },
                duration_ms=_elapsed_ms(start),
            )
        except OSError as exc:
            return CheckResult(
                category=CheckCategory.WORKSPACE,
                name="workspace:disk_space",
                status=CheckStatus.WARN,
                message=f"Could not check disk space: {exc}",
                details={"path": abs_path, "error": str(exc)},
                duration_ms=_elapsed_ms(start),
            )

    # ========================================================================
    # Git Checks
    # ========================================================================

    def check_git(self) -> List[CheckResult]:
        """Check git repository state (existence, branch, cleanliness)."""
        if self.config.git is None:
            return []

        git_spec = self.config.git
        results: List[CheckResult] = []

        # Is it a git repo?
        result = self._check_is_git_repo(git_spec.path)
        results.append(result)
        if result.status == CheckStatus.FAIL:
            return results

        # Branch check
        if git_spec.require_branch:
            results.append(
                self._check_git_branch(git_spec.path, git_spec.require_branch)
            )
            if self._should_stop(results):
                return results

        # Clean check
        if git_spec.require_clean:
            results.append(self._check_git_clean(git_spec.path))

        return results

    def _run_git_command(self, args: List[str], cwd: str) -> Tuple[int, str, str]:
        """Run a git command and return ``(returncode, stdout, stderr)``."""
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode, result.stdout, result.stderr
        except FileNotFoundError:
            return 127, "", "git: command not found"
        except subprocess.TimeoutExpired:
            return -1, "", "git command timed out"

    def _check_is_git_repo(self, path: str) -> CheckResult:
        start = time.monotonic()
        rc, _out, _err = self._run_git_command(["rev-parse", "--git-dir"], path)

        if rc == 0:
            return CheckResult(
                category=CheckCategory.GIT,
                name="git:is_repo",
                status=CheckStatus.PASS,
                message=f"Valid git repository: {os.path.abspath(path)}",
                details={"path": os.path.abspath(path)},
                duration_ms=_elapsed_ms(start),
            )
        return CheckResult(
            category=CheckCategory.GIT,
            name="git:is_repo",
            status=_status_for(self.config.git.require_repo),
            message=f"Not a git repository: {os.path.abspath(path)}",
            details={"path": os.path.abspath(path), "stderr": _err.strip()},
            duration_ms=_elapsed_ms(start),
        )

    def _check_git_clean(self, path: str) -> CheckResult:
        start = time.monotonic()
        rc, stdout, stderr = self._run_git_command(["status", "--porcelain"], path)

        if rc != 0:
            return CheckResult(
                category=CheckCategory.GIT,
                name="git:clean",
                status=CheckStatus.FAIL,
                message=f"Failed to check git status: {stderr.strip()}",
                details={"path": os.path.abspath(path)},
                duration_ms=_elapsed_ms(start),
            )

        if stdout.strip():
            lines = stdout.strip().splitlines()
            return CheckResult(
                category=CheckCategory.GIT,
                name="git:clean",
                status=CheckStatus.FAIL,
                message=f"Uncommitted changes detected ({len(lines)} file(s))",
                details={"path": os.path.abspath(path), "changed_files": len(lines)},
                duration_ms=_elapsed_ms(start),
            )
        return CheckResult(
            category=CheckCategory.GIT,
            name="git:clean",
            status=CheckStatus.PASS,
            message="Working directory is clean",
            details={"path": os.path.abspath(path)},
            duration_ms=_elapsed_ms(start),
        )

    def _check_git_branch(self, path: str, expected_branch: str) -> CheckResult:
        start = time.monotonic()
        rc, stdout, stderr = self._run_git_command(["branch", "--show-current"], path)

        if rc != 0:
            return CheckResult(
                category=CheckCategory.GIT,
                name="git:branch",
                status=CheckStatus.FAIL,
                message=f"Failed to check git branch: {stderr.strip()}",
                details={"path": os.path.abspath(path)},
                duration_ms=_elapsed_ms(start),
            )

        current_branch = stdout.strip()
        if current_branch == expected_branch:
            return CheckResult(
                category=CheckCategory.GIT,
                name="git:branch",
                status=CheckStatus.PASS,
                message=f"On expected branch: {expected_branch}",
                details={"path": os.path.abspath(path), "branch": current_branch},
                duration_ms=_elapsed_ms(start),
            )
        return CheckResult(
            category=CheckCategory.GIT,
            name="git:branch",
            status=CheckStatus.FAIL,
            message=f"Wrong branch: '{current_branch}' (expected '{expected_branch}')",
            details={
                "path": os.path.abspath(path),
                "current": current_branch,
                "expected": expected_branch,
            },
            duration_ms=_elapsed_ms(start),
        )

    # ========================================================================
    # Environment Variable Checks
    # ========================================================================

    def check_environment(self) -> List[CheckResult]:
        """Check all specified environment variables."""
        results: List[CheckResult] = []
        for spec in self.config.env_vars:
            if self._should_stop(results):
                break
            try:
                results.append(self._check_env_var(spec))
            except Exception as exc:
                results.append(
                    CheckResult(
                        category=CheckCategory.ENVIRONMENT,
                        name=f"env:{spec.name}",
                        status=CheckStatus.FAIL,
                        message=f"Unexpected error checking env var: {exc}",
                        details={"error": str(exc)},
                    )
                )
        return results

    def _check_env_var(self, spec: EnvVarSpec) -> CheckResult:
        start = time.monotonic()
        value = os.environ.get(spec.name)

        if value is None:
            return CheckResult(
                category=CheckCategory.ENVIRONMENT,
                name=f"env:{spec.name}",
                status=_status_for(spec.required),
                message=f"Environment variable '{spec.name}' is not set",
                details={"variable": spec.name},
                duration_ms=_elapsed_ms(start),
            )

        if spec.must_be_non_empty and not value:
            return CheckResult(
                category=CheckCategory.ENVIRONMENT,
                name=f"env:{spec.name}",
                status=_status_for(spec.required),
                message=f"Environment variable '{spec.name}' is set but empty",
                details={"variable": spec.name},
                duration_ms=_elapsed_ms(start),
            )

        # Build a safe message — never leak secret values
        if spec.is_secret:
            display = f"'{spec.name}' is set (value masked, {len(value)} chars)"
        else:
            truncated = value if len(value) <= 50 else value[:47] + "..."
            display = f"'{spec.name}' = {truncated!r}"

        return CheckResult(
            category=CheckCategory.ENVIRONMENT,
            name=f"env:{spec.name}",
            status=CheckStatus.PASS,
            message=f"Environment variable {display}",
            details={"variable": spec.name, "length": len(value)},
            duration_ms=_elapsed_ms(start),
        )


# ============================================================================
# Module-Level Convenience Functions
# ============================================================================


def run_preflight(config: Optional[PreFlightConfig] = None) -> PreFlightReport:
    """Run all pre-flight checks and return the report.

    Args:
        config: Optional configuration. Uses sensible defaults when ``None``.

    Returns:
        A :class:`PreFlightReport` with aggregated results.
    """
    checker = PreFlightChecker(config)
    return checker.run_all()


def run_preflight_or_exit(
    config: Optional[PreFlightConfig] = None,
    exit_code: int = 1,
    print_on_success: bool = False,
) -> PreFlightReport:
    """Run pre-flight checks; exit the process if any check fails.

    On failure the summary is printed to *stderr* and :func:`sys.exit` is
    called with *exit_code*.  On success the report is returned (and
    optionally printed to *stdout* when *print_on_success* is ``True``).

    Args:
        config: Optional configuration.
        exit_code: Process exit code on failure.
        print_on_success: Print the summary even when all checks pass.

    Returns:
        :class:`PreFlightReport` — only reachable when all checks pass.

    Raises:
        SystemExit: When any check has status FAIL.
    """
    report = run_preflight(config)

    if not report.passed:
        print(report.summary, file=sys.stderr)
        sys.exit(exit_code)

    if print_on_success:
        print(report.summary)

    return report
