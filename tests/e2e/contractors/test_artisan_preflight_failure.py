"""
End-to-end tests for pre-flight check failures in the artisan contractor system.

This module validates that the system fails fast, fails loudly, and fails helpfully
when pre-flight checks fail. It covers four failure scenarios:
1. Missing dependencies (tools, services, packages)
2. Invalid configuration (malformed, incomplete, or invalid values)
3. Zero-cost estimation (indicating misconfiguration or empty task)
4. Actionable errors (containing what went wrong, which field, and how to fix it)

All tests verify that no side effects (partial execution, state mutation) occur
when pre-flight checks fail.

The module is self-contained: all errors, models, contractor simulation, helpers,
fixtures, and tests are defined here with zero relative imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import pytest


# ============================================================
# ERROR CLASSES (Pre-Flight Failure Types)
# ============================================================


class PreFlightError(Exception):
    """
    Base exception for all pre-flight check failures.

    Contains structured information:
    - message: what went wrong (main error description)
    - field_name: which specific field/dependency is at fault
    - suggestion: how to fix it (actionable guidance)
    """

    def __init__(
        self,
        message: str,
        field_name: Optional[str] = None,
        suggestion: Optional[str] = None,
    ) -> None:
        self.field_name = field_name
        self.suggestion = suggestion
        super().__init__(message)


class MissingDependencyError(PreFlightError):
    """
    Raised when a required dependency (tool, service, or package) is not available.

    Attributes:
        dependency_name: the name of the missing dependency
        field_name: same as dependency_name (for consistency)
        suggestion: specific guidance on how to install/enable the dependency
    """

    def __init__(
        self,
        dependency_name: str,
        message: Optional[str] = None,
        suggestion: Optional[str] = None,
    ) -> None:
        self.dependency_name = dependency_name
        msg = message or f"Missing required dependency: '{dependency_name}'"
        suggestion = (
            suggestion
            or f"Install or enable '{dependency_name}' before running this task."
        )
        super().__init__(msg, field_name=dependency_name, suggestion=suggestion)


class InvalidConfigError(PreFlightError):
    """
    Raised when configuration is invalid (malformed, incomplete, or out of range).

    Attributes:
        field_name: the configuration field that is invalid
        reason: description of what is wrong with the value
        suggestion: guidance on how to fix the configuration
    """

    def __init__(
        self,
        field_name: str,
        reason: str,
        suggestion: Optional[str] = None,
    ) -> None:
        msg = f"Invalid configuration for '{field_name}': {reason}"
        suggestion = (
            suggestion or f"Check the value of '{field_name}' in your configuration."
        )
        super().__init__(msg, field_name=field_name, suggestion=suggestion)


class ZeroCostError(PreFlightError):
    """
    Raised when estimated cost is zero, indicating misconfiguration or empty task.

    Zero cost typically means either:
    - task_name is empty (no actual work defined)
    - max_tokens is zero or negative (no output capacity)
    - other configuration that results in no actual work

    Attributes:
        task_name: the task that has zero cost
        field_name: always "cost_estimate" (the field that failed)
        suggestion: guidance on verifying task configuration
    """

    def __init__(
        self,
        task_name: str,
        suggestion: Optional[str] = None,
    ) -> None:
        self.task_name = task_name
        msg = (
            f"Estimated cost for task '{task_name}' is zero. "
            "This likely indicates an empty or misconfigured task."
        )
        suggestion = (
            suggestion
            or f"Verify that task '{task_name}' has valid inputs and a "
            "non-trivial workload."
        )
        super().__init__(msg, field_name="cost_estimate", suggestion=suggestion)


# ============================================================
# DATA MODELS
# ============================================================


class PreFlightStatus(Enum):
    """Status of a pre-flight check."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PreFlightResult:
    """
    Result of running pre-flight checks.

    Attributes:
        status: PASSED, FAILED, or SKIPPED
        errors: list of PreFlightError exceptions found (causes failure)
        warnings: list of warning messages (non-fatal issues)
    """

    status: PreFlightStatus
    errors: List[PreFlightError] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """True if status is PASSED."""
        return self.status == PreFlightStatus.PASSED


@dataclass
class ArtisanConfig:
    """
    Configuration for an artisan contractor task.

    Attributes:
        task_name: human-readable identifier for the task
        model: AI model to use (e.g., "gpt-4")
        max_tokens: maximum output tokens allowed
        temperature: sampling temperature (0.0 to 2.0)
        output_format: desired output format (json, text, markdown)
        api_key: API key for model access
        endpoint: custom API endpoint URL (optional)
        extra: arbitrary extra configuration fields
    """

    task_name: str = ""
    model: str = ""
    max_tokens: int = 0
    temperature: float = 0.0
    output_format: str = ""
    api_key: str = ""
    endpoint: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DependencyManifest:
    """
    Specification of required dependencies for a task.

    Attributes:
        required_tools: command-line tools that must be available on PATH
        required_services: services that must be running (e.g., redis, postgres)
        required_packages: Python packages that must be installed
    """

    required_tools: List[str] = field(default_factory=list)
    required_services: List[str] = field(default_factory=list)
    required_packages: List[str] = field(default_factory=list)


# ============================================================
# HELPER FUNCTIONS
# ============================================================


def assert_actionable_error(
    error: PreFlightError,
    expected_field: Optional[str] = None,
    must_contain: Optional[List[str]] = None,
) -> None:
    """
    Assert that a PreFlightError is actionable and well-formed.

    An actionable error must have:
    1. Non-empty error message (preferably > 10 chars)
    2. field_name identifying what's wrong (if expected_field provided, must match)
    3. Non-empty suggestion (preferably > 5 chars)
    4. All strings in must_contain present in the message

    Args:
        error: the PreFlightError to validate
        expected_field: if provided, error.field_name must equal this
        must_contain: if provided, all strings in this list must appear in str(error)

    Raises:
        AssertionError: if any actionability requirement is not met
    """
    error_msg = str(error)
    assert error_msg, "Error message must not be empty"
    assert (
        len(error_msg) > 10
    ), f"Error message too short to be actionable: '{error_msg}'"

    if expected_field is not None:
        assert (
            error.field_name == expected_field
        ), f"Expected field_name='{expected_field}', got '{error.field_name}'"

    assert error.suggestion is not None, "Error must have a suggestion"
    assert (
        len(error.suggestion) > 5
    ), f"Suggestion too short to be actionable: '{error.suggestion}'"

    if must_contain:
        for substring in must_contain:
            assert (
                substring in error_msg
            ), f"Error message should contain '{substring}', got: '{error_msg}'"


def make_valid_config() -> ArtisanConfig:
    """
    Create a fully valid configuration for testing.

    Returns:
        ArtisanConfig with all required fields properly set.
    """
    return ArtisanConfig(
        task_name="test-task",
        model="gpt-4",
        max_tokens=1000,
        temperature=0.7,
        output_format="json",
        api_key="sk-test-key-12345",
        endpoint="https://api.example.com/v1",
    )


def make_valid_dependencies() -> DependencyManifest:
    """
    Create a dependency manifest with no requirements (always passes).

    Returns:
        DependencyManifest with empty requirement lists.
    """
    return DependencyManifest(
        required_tools=[],
        required_services=[],
        required_packages=[],
    )


# ============================================================
# CONTRACTOR SIMULATION (Mock Artisan)
# ============================================================


class ArtisanContractor:
    """
    Simulated artisan contractor that performs pre-flight checks before execution.

    This models the real contractor lifecycle:
    1. validate_dependencies() — check all required tools, services, packages exist
    2. validate_config() — check all configuration fields are valid
    3. validate_cost() — check estimated cost is non-zero (not misconfigured)
    4. _execute() — perform the actual work (only if all checks pass)

    Pre-flight failures prevent execution and record no side effects.

    Attributes:
        config: ArtisanConfig for this task.
        dependencies: DependencyManifest of required dependencies.
        executed: bool, True only if _execute() was successfully called.
        _side_effects: list of state changes (for verifying no side effects on failure).
    """

    def __init__(self, config: ArtisanConfig, dependencies: DependencyManifest) -> None:
        self.config = config
        self.dependencies = dependencies
        self.executed = False
        self._side_effects: List[str] = []

    def preflight_check(self) -> PreFlightResult:
        """
        Run all pre-flight validations without executing the task.

        Checks are performed in order:
        1. Dependencies (tools, services, packages)
        2. Configuration (all fields validated)
        3. Cost estimation (must be non-zero)

        Returns:
            PreFlightResult with status, errors, and warnings.
            If any errors are found, status is FAILED and execution must not proceed.
        """
        errors: List[PreFlightError] = []
        warnings: List[str] = []

        # 1. Check dependencies
        errors.extend(self._validate_dependencies())

        # 2. Check config
        errors.extend(self._validate_config())

        # 3. Check cost
        cost_errors, cost_warnings = self._validate_cost()
        errors.extend(cost_errors)
        warnings.extend(cost_warnings)

        if errors:
            return PreFlightResult(
                status=PreFlightStatus.FAILED, errors=errors, warnings=warnings
            )
        return PreFlightResult(
            status=PreFlightStatus.PASSED, errors=[], warnings=warnings
        )

    def run(self) -> Any:
        """
        Run the full lifecycle: preflight check then execute.

        Raises:
            PreFlightError: if any pre-flight check fails
                (the first/most critical error is raised).

        Returns:
            Result from _execute() if all checks pass.
        """
        result = self.preflight_check()
        if not result.passed:
            raise result.errors[0]
        return self._execute()

    def _validate_dependencies(self) -> List[PreFlightError]:
        """
        Check that all required tools, services, and packages are available.

        Returns:
            List of MissingDependencyError for each unavailable dependency.
        """
        errors: List[PreFlightError] = []
        available_tools = self._get_available_tools()
        available_services = self._get_available_services()
        available_packages = self._get_available_packages()

        for tool in self.dependencies.required_tools:
            if tool not in available_tools:
                errors.append(
                    MissingDependencyError(
                        dependency_name=tool,
                        suggestion=(
                            f"Install tool '{tool}' via your package manager "
                            "or ensure it is on PATH."
                        ),
                    )
                )

        for service in self.dependencies.required_services:
            if service not in available_services:
                errors.append(
                    MissingDependencyError(
                        dependency_name=service,
                        suggestion=(
                            f"Start service '{service}' or check "
                            "connection settings."
                        ),
                    )
                )

        for package in self.dependencies.required_packages:
            if package not in available_packages:
                errors.append(
                    MissingDependencyError(
                        dependency_name=package,
                        suggestion=(
                            f"Install package '{package}' via pip: "
                            f"`pip install {package}`."
                        ),
                    )
                )

        return errors

    def _validate_config(self) -> List[PreFlightError]:
        """
        Validate all configuration fields.

        Checks:
        - task_name: non-empty and non-whitespace
        - model: non-empty and non-whitespace
        - max_tokens: >= 1
        - temperature: between 0.0 and 2.0 (inclusive)
        - output_format: if set, must be one of (json, text, markdown)
        - api_key: non-empty and non-whitespace
        - endpoint: if set, must be a valid HTTP(S) URL

        Returns:
            List of InvalidConfigError for each invalid field.
        """
        errors: List[PreFlightError] = []

        if not self.config.task_name or not self.config.task_name.strip():
            errors.append(InvalidConfigError("task_name", "must not be empty"))

        if not self.config.model or not self.config.model.strip():
            errors.append(
                InvalidConfigError(
                    "model",
                    "must not be empty",
                    "Set 'model' to a valid model identifier, e.g., 'gpt-4'.",
                )
            )

        if self.config.max_tokens < 1:
            errors.append(
                InvalidConfigError(
                    "max_tokens",
                    f"must be >= 1, got {self.config.max_tokens}",
                )
            )

        if not (0.0 <= self.config.temperature <= 2.0):
            errors.append(
                InvalidConfigError(
                    "temperature",
                    f"must be between 0.0 and 2.0, got {self.config.temperature}",
                )
            )

        if (
            self.config.output_format
            and self.config.output_format not in ("json", "text", "markdown")
        ):
            errors.append(
                InvalidConfigError(
                    "output_format",
                    f"unsupported format '{self.config.output_format}'",
                    "Use one of: 'json', 'text', 'markdown'.",
                )
            )

        if not self.config.api_key or not self.config.api_key.strip():
            errors.append(
                InvalidConfigError(
                    "api_key",
                    "must not be empty",
                    "Set the API key via environment variable or config file.",
                )
            )

        if self.config.endpoint and not self.config.endpoint.startswith(
            ("http://", "https://")
        ):
            errors.append(
                InvalidConfigError(
                    "endpoint",
                    f"invalid URL '{self.config.endpoint}'",
                    "Provide a valid HTTP(S) URL.",
                )
            )

        return errors

    def _validate_cost(self) -> Tuple[List[PreFlightError], List[str]]:
        """
        Validate that estimated cost is non-zero.

        Zero cost typically indicates misconfiguration (empty task, zero tokens, etc.)
        and should be flagged as an error.
        Negative cost is also an error (invalid configuration).

        Returns:
            Tuple of (errors, warnings).
        """
        errors: List[PreFlightError] = []
        warnings: List[str] = []
        estimated_cost = self._estimate_cost()

        if estimated_cost == 0:
            errors.append(ZeroCostError(task_name=self.config.task_name or "<unnamed>"))
        elif estimated_cost < 0:
            errors.append(
                InvalidConfigError(
                    "cost_estimate",
                    f"negative cost ({estimated_cost}) is invalid",
                )
            )

        return errors, warnings

    def _estimate_cost(self) -> float:
        """
        Estimate the cost of this task.

        Cost model: proportional to max_tokens.
        Cost is zero if task is empty (task_name empty or max_tokens <= 0).

        Returns:
            Estimated cost as a float. Zero means empty/misconfigured.
        """
        if not self.config.task_name or self.config.max_tokens <= 0:
            return 0.0
        return self.config.max_tokens * 0.001

    def _get_available_tools(self) -> List[str]:
        """Return list of available tools. Override or mock in tests."""
        return []

    def _get_available_services(self) -> List[str]:
        """Return list of available services. Override or mock in tests."""
        return []

    def _get_available_packages(self) -> List[str]:
        """Return list of available packages. Override or mock in tests."""
        return []

    def _execute(self) -> Any:
        """
        Perform the actual work. Only called if preflight_check() passed.

        Records side effect for test validation.

        Returns:
            dict with status "completed".
        """
        self.executed = True
        self._side_effects.append("executed")
        return {"status": "completed"}


# ============================================================
# FIXTURES
# ============================================================


@pytest.fixture
def valid_config() -> ArtisanConfig:
    """Fixture: a fully valid configuration."""
    return make_valid_config()


@pytest.fixture
def valid_dependencies() -> DependencyManifest:
    """Fixture: a dependency manifest with no requirements."""
    return make_valid_dependencies()


@pytest.fixture
def execution_tracker() -> List[str]:
    """Fixture: empty list for tracking side effects."""
    return []


# ============================================================
# TEST CLASSES
# ============================================================


class TestPreFlightMissingDependencies:
    """Tests for pre-flight failure when dependencies are missing."""

    def test_missing_single_tool(self, valid_config: ArtisanConfig) -> None:
        """Single missing tool should be caught and reported."""
        deps = DependencyManifest(required_tools=["ripgrep"])
        contractor = ArtisanContractor(valid_config, deps)
        result = contractor.preflight_check()
        assert not result.passed
        assert len(result.errors) == 1
        assert isinstance(result.errors[0], MissingDependencyError)
        assert "ripgrep" in str(result.errors[0])
        assert_actionable_error(result.errors[0], expected_field="ripgrep")

    def test_missing_multiple_tools(self, valid_config: ArtisanConfig) -> None:
        """Multiple missing tools should all be caught."""
        deps = DependencyManifest(required_tools=["ripgrep", "fd", "jq"])
        contractor = ArtisanContractor(valid_config, deps)
        result = contractor.preflight_check()
        assert not result.passed
        assert len(result.errors) == 3
        missing_names = {e.dependency_name for e in result.errors}
        assert missing_names == {"ripgrep", "fd", "jq"}

    def test_missing_service(self, valid_config: ArtisanConfig) -> None:
        """Missing service should be caught and reported."""
        deps = DependencyManifest(required_services=["redis"])
        contractor = ArtisanContractor(valid_config, deps)
        result = contractor.preflight_check()
        assert not result.passed
        assert isinstance(result.errors[0], MissingDependencyError)
        assert "redis" in str(result.errors[0])

    def test_missing_package(self, valid_config: ArtisanConfig) -> None:
        """Missing package should suggest pip install."""
        deps = DependencyManifest(required_packages=["numpy"])
        contractor = ArtisanContractor(valid_config, deps)
        result = contractor.preflight_check()
        assert not result.passed
        assert isinstance(result.errors[0], MissingDependencyError)
        assert "pip install numpy" in result.errors[0].suggestion

    def test_missing_mixed_dependencies(self, valid_config: ArtisanConfig) -> None:
        """Mix of missing tools, services, and packages should all be caught."""
        deps = DependencyManifest(
            required_tools=["ripgrep"],
            required_services=["redis"],
            required_packages=["numpy"],
        )
        contractor = ArtisanContractor(valid_config, deps)
        result = contractor.preflight_check()
        assert not result.passed
        assert len(result.errors) == 3

    def test_run_raises_on_missing_deps(self, valid_config: ArtisanConfig) -> None:
        """run() should raise MissingDependencyError, never execute."""
        deps = DependencyManifest(required_tools=["nonexistent-tool"])
        contractor = ArtisanContractor(valid_config, deps)
        with pytest.raises(MissingDependencyError) as exc_info:
            contractor.run()
        assert "nonexistent-tool" in str(exc_info.value)
        assert not contractor.executed

    def test_no_missing_deps_passes(self, valid_config: ArtisanConfig) -> None:
        """When no deps are required, dependency check passes."""
        deps = DependencyManifest()
        contractor = ArtisanContractor(valid_config, deps)
        result = contractor.preflight_check()
        dep_errors = [
            e for e in result.errors if isinstance(e, MissingDependencyError)
        ]
        assert len(dep_errors) == 0

    def test_available_tools_are_not_flagged(
        self, valid_config: ArtisanConfig
    ) -> None:
        """When a tool IS available, it should not be flagged as missing."""
        deps = DependencyManifest(required_tools=["git"])
        contractor = ArtisanContractor(valid_config, deps)
        contractor._get_available_tools = lambda: ["git"]  # type: ignore[assignment]
        result = contractor.preflight_check()
        dep_errors = [
            e for e in result.errors if isinstance(e, MissingDependencyError)
        ]
        assert len(dep_errors) == 0


class TestPreFlightInvalidConfig:
    """Tests for pre-flight failure when configuration is invalid."""

    def test_empty_task_name(self, valid_dependencies: DependencyManifest) -> None:
        """Empty task_name should be flagged."""
        config = make_valid_config()
        config.task_name = ""
        contractor = ArtisanContractor(config, valid_dependencies)
        result = contractor.preflight_check()
        assert not result.passed
        config_errors = [
            e for e in result.errors if isinstance(e, InvalidConfigError)
        ]
        assert any(e.field_name == "task_name" for e in config_errors)

    def test_empty_model(self, valid_dependencies: DependencyManifest) -> None:
        """Empty model should be flagged."""
        config = make_valid_config()
        config.model = ""
        contractor = ArtisanContractor(config, valid_dependencies)
        result = contractor.preflight_check()
        assert not result.passed
        assert any(
            e.field_name == "model"
            for e in result.errors
            if isinstance(e, InvalidConfigError)
        )

    def test_zero_max_tokens(self, valid_dependencies: DependencyManifest) -> None:
        """max_tokens=0 should be flagged as invalid."""
        config = make_valid_config()
        config.max_tokens = 0
        contractor = ArtisanContractor(config, valid_dependencies)
        result = contractor.preflight_check()
        assert not result.passed
        assert any(
            e.field_name == "max_tokens"
            for e in result.errors
            if isinstance(e, InvalidConfigError)
        )

    def test_negative_max_tokens(
        self, valid_dependencies: DependencyManifest
    ) -> None:
        """Negative max_tokens should be flagged."""
        config = make_valid_config()
        config.max_tokens = -100
        contractor = ArtisanContractor(config, valid_dependencies)
        result = contractor.preflight_check()
        assert not result.passed

    def test_temperature_out_of_range_high(
        self, valid_dependencies: DependencyManifest
    ) -> None:
        """Temperature > 2.0 should be flagged."""
        config = make_valid_config()
        config.temperature = 5.0
        contractor = ArtisanContractor(config, valid_dependencies)
        result = contractor.preflight_check()
        assert not result.passed
        assert any(
            e.field_name == "temperature"
            for e in result.errors
            if isinstance(e, InvalidConfigError)
        )

    def test_temperature_out_of_range_negative(
        self, valid_dependencies: DependencyManifest
    ) -> None:
        """Negative temperature should be flagged."""
        config = make_valid_config()
        config.temperature = -0.1
        contractor = ArtisanContractor(config, valid_dependencies)
        result = contractor.preflight_check()
        assert not result.passed

    def test_invalid_output_format(
        self, valid_dependencies: DependencyManifest
    ) -> None:
        """Unsupported output_format should be flagged."""
        config = make_valid_config()
        config.output_format = "xml"
        contractor = ArtisanContractor(config, valid_dependencies)
        result = contractor.preflight_check()
        assert not result.passed
        err = [
            e
            for e in result.errors
            if isinstance(e, InvalidConfigError) and e.field_name == "output_format"
        ]
        assert len(err) == 1
        assert "xml" in str(err[0])

    def test_empty_api_key(self, valid_dependencies: DependencyManifest) -> None:
        """Empty api_key should be flagged."""
        config = make_valid_config()
        config.api_key = ""
        contractor = ArtisanContractor(config, valid_dependencies)
        result = contractor.preflight_check()
        assert not result.passed
        assert any(
            e.field_name == "api_key"
            for e in result.errors
            if isinstance(e, InvalidConfigError)
        )

    def test_invalid_endpoint_url(
        self, valid_dependencies: DependencyManifest
    ) -> None:
        """Non-URL endpoint should be flagged."""
        config = make_valid_config()
        config.endpoint = "not-a-url"
        contractor = ArtisanContractor(config, valid_dependencies)
        result = contractor.preflight_check()
        assert not result.passed
        assert any(
            e.field_name == "endpoint"
            for e in result.errors
            if isinstance(e, InvalidConfigError)
        )

    def test_multiple_invalid_fields(
        self, valid_dependencies: DependencyManifest
    ) -> None:
        """Multiple invalid fields should all be reported."""
        config = ArtisanConfig()  # all defaults are invalid
        contractor = ArtisanContractor(config, valid_dependencies)
        result = contractor.preflight_check()
        assert not result.passed
        # At least: task_name, model, max_tokens, api_key
        assert len(result.errors) >= 3

    def test_run_raises_on_invalid_config(
        self, valid_dependencies: DependencyManifest
    ) -> None:
        """run() should raise PreFlightError, never execute."""
        config = make_valid_config()
        config.task_name = ""
        contractor = ArtisanContractor(config, valid_dependencies)
        with pytest.raises(PreFlightError):
            contractor.run()
        assert not contractor.executed

    def test_valid_config_passes(self, valid_dependencies: DependencyManifest) -> None:
        """Valid config should have no InvalidConfigError."""
        config = make_valid_config()
        contractor = ArtisanContractor(config, valid_dependencies)
        result = contractor.preflight_check()
        config_errors = [
            e for e in result.errors if isinstance(e, InvalidConfigError)
        ]
        assert len(config_errors) == 0

    def test_whitespace_only_task_name(
        self, valid_dependencies: DependencyManifest
    ) -> None:
        """Whitespace-only task_name should be treated as empty."""
        config = make_valid_config()
        config.task_name = "   "
        contractor = ArtisanContractor(config, valid_dependencies)
        result = contractor.preflight_check()
        assert not result.passed

    def test_valid_output_formats_accepted(
        self, valid_dependencies: DependencyManifest
    ) -> None:
        """All supported output_format values should be accepted."""
        for fmt in ("json", "text", "markdown"):
            config = make_valid_config()
            config.output_format = fmt
            contractor = ArtisanContractor(config, valid_dependencies)
            result = contractor.preflight_check()
            fmt_errors = [
                e
                for e in result.errors
                if isinstance(e, InvalidConfigError)
                and e.field_name == "output_format"
            ]
            assert len(fmt_errors) == 0, f"Format '{fmt}' should be valid"

    def test_empty_endpoint_is_ok(self, valid_dependencies: DependencyManifest) -> None:
        """Empty endpoint (use default) should not be flagged."""
        config = make_valid_config()
        config.endpoint = ""
        contractor = ArtisanContractor(config, valid_dependencies)
        result = contractor.preflight_check()
        endpoint_errors = [
            e
            for e in result.errors
            if isinstance(e, InvalidConfigError) and e.field_name == "endpoint"
        ]
        assert len(endpoint_errors) == 0


class TestPreFlightZeroCost:
    """Tests for pre-flight failure when estimated cost is zero."""

    def test_zero_cost_from_zero_max_tokens(
        self, valid_dependencies: DependencyManifest
    ) -> None:
        """max_tokens=0 results in zero cost, which is flagged."""
        config = make_valid_config()
        config.max_tokens = 0
        contractor = ArtisanContractor(config, valid_dependencies)
        result = contractor.preflight_check()
        assert not result.passed
        # max_tokens=0 triggers both InvalidConfigError and ZeroCostError
        all_error_types = {type(e) for e in result.errors}
        assert InvalidConfigError in all_error_types
        assert ZeroCostError in all_error_types

    def test_zero_cost_from_empty_task_name(
        self, valid_dependencies: DependencyManifest
    ) -> None:
        """Empty task_name results in zero cost, which is flagged."""
        config = make_valid_config()
        config.task_name = ""
        contractor = ArtisanContractor(config, valid_dependencies)
        result = contractor.preflight_check()
        assert not result.passed
        zero_cost_errors = [
            e for e in result.errors if isinstance(e, ZeroCostError)
        ]
        assert len(zero_cost_errors) >= 1

    def test_zero_cost_error_is_actionable(
        self, valid_dependencies: DependencyManifest
    ) -> None:
        """ZeroCostError should be actionable."""
        config = make_valid_config()
        config.task_name = ""
        contractor = ArtisanContractor(config, valid_dependencies)
        result = contractor.preflight_check()
        zero_cost_errors = [
            e for e in result.errors if isinstance(e, ZeroCostError)
        ]
        for err in zero_cost_errors:
            assert_actionable_error(err, expected_field="cost_estimate")

    def test_nonzero_cost_passes(self, valid_dependencies: DependencyManifest) -> None:
        """Valid config with nonzero cost should pass zero-cost check."""
        config = make_valid_config()
        contractor = ArtisanContractor(config, valid_dependencies)
        result = contractor.preflight_check()
        zero_cost_errors = [
            e for e in result.errors if isinstance(e, ZeroCostError)
        ]
        assert len(zero_cost_errors) == 0

    def test_run_raises_on_zero_cost(self) -> None:
        """When only zero cost is the issue, run() should raise ZeroCostError."""
        config = make_valid_config()
        deps = make_valid_dependencies()
        contractor = ArtisanContractor(config, deps)
        contractor._estimate_cost = lambda: 0.0  # type: ignore[assignment]
        with pytest.raises(ZeroCostError):
            contractor.run()
        assert not contractor.executed


class TestPreFlightActionableErrors:
    """Tests that ALL pre-flight errors are actionable."""

    def test_missing_dep_error_is_actionable(self) -> None:
        """MissingDependencyError must be actionable."""
        err = MissingDependencyError("some-tool")
        assert_actionable_error(
            err, expected_field="some-tool", must_contain=["some-tool"]
        )

    def test_invalid_config_error_is_actionable(self) -> None:
        """InvalidConfigError must be actionable."""
        err = InvalidConfigError("temperature", "out of range")
        assert_actionable_error(
            err,
            expected_field="temperature",
            must_contain=["temperature", "out of range"],
        )

    def test_zero_cost_error_is_actionable(self) -> None:
        """ZeroCostError must be actionable."""
        err = ZeroCostError("my-task")
        assert_actionable_error(
            err, expected_field="cost_estimate", must_contain=["my-task", "zero"]
        )

    def test_all_errors_from_full_failure_are_actionable(self) -> None:
        """All errors from maximally broken contractor are actionable."""
        config = ArtisanConfig()  # all defaults are invalid
        deps = DependencyManifest(
            required_tools=["nonexistent"],
            required_services=["fake-service"],
            required_packages=["fake-package"],
        )
        contractor = ArtisanContractor(config, deps)
        result = contractor.preflight_check()
        assert not result.passed
        assert len(result.errors) >= 5  # deps + config + cost
        for error in result.errors:
            assert_actionable_error(error)

    def test_error_message_not_generic(self) -> None:
        """Error messages must not be generic."""
        err = MissingDependencyError("docker")
        msg = str(err)
        generic_phrases = ["an error occurred", "something went wrong", "unknown error"]
        for phrase in generic_phrases:
            assert (
                phrase not in msg.lower()
            ), f"Error message is too generic: '{msg}'"

    def test_suggestion_is_specific(self) -> None:
        """Suggestion must mention the specific dependency/field."""
        err = MissingDependencyError("docker")
        assert "docker" in err.suggestion.lower()

    def test_all_preflight_errors_inherit_from_base(self) -> None:
        """All error subclasses must inherit from PreFlightError."""
        assert issubclass(MissingDependencyError, PreFlightError)
        assert issubclass(InvalidConfigError, PreFlightError)
        assert issubclass(ZeroCostError, PreFlightError)

    def test_errors_are_catchable_as_base_type(self) -> None:
        """Errors raised must be catchable as PreFlightError."""
        config = make_valid_config()
        config.task_name = ""
        deps = make_valid_dependencies()
        contractor = ArtisanContractor(config, deps)
        with pytest.raises(PreFlightError):
            contractor.run()


class TestPreFlightNoSideEffects:
    """Tests that pre-flight failures cause zero side effects."""

    def test_execute_not_called_on_missing_deps(
        self, valid_config: ArtisanConfig
    ) -> None:
        """Missing deps should not execute or cause side effects."""
        deps = DependencyManifest(required_tools=["missing"])
        contractor = ArtisanContractor(valid_config, deps)
        with pytest.raises(MissingDependencyError):
            contractor.run()
        assert not contractor.executed
        assert len(contractor._side_effects) == 0

    def test_execute_not_called_on_invalid_config(
        self, valid_dependencies: DependencyManifest
    ) -> None:
        """Invalid config should not execute or cause side effects."""
        config = make_valid_config()
        config.model = ""
        contractor = ArtisanContractor(config, valid_dependencies)
        with pytest.raises(PreFlightError):
            contractor.run()
        assert not contractor.executed
        assert len(contractor._side_effects) == 0

    def test_execute_not_called_on_zero_cost(self) -> None:
        """Zero cost should not execute or cause side effects."""
        config = make_valid_config()
        deps = make_valid_dependencies()
        contractor = ArtisanContractor(config, deps)
        contractor._estimate_cost = lambda: 0.0  # type: ignore[assignment]
        with pytest.raises(ZeroCostError):
            contractor.run()
        assert not contractor.executed
        assert len(contractor._side_effects) == 0

    def test_preflight_check_itself_has_no_side_effects(
        self, valid_config: ArtisanConfig
    ) -> None:
        """preflight_check() must not cause any side effects."""
        deps = DependencyManifest(required_tools=["missing"])
        contractor = ArtisanContractor(valid_config, deps)
        result = contractor.preflight_check()
        assert not result.passed
        assert not contractor.executed
        assert len(contractor._side_effects) == 0

    def test_successful_run_does_execute(self) -> None:
        """Sanity check: when preflight passes, execute IS called."""
        config = make_valid_config()
        deps = make_valid_dependencies()
        contractor = ArtisanContractor(config, deps)
        result = contractor.run()
        assert contractor.executed
        assert result == {"status": "completed"}
        assert "executed" in contractor._side_effects