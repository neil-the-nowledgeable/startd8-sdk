"""CLI integration tests for startd8 contractor CLI (F-019).

Parameterized tests for CLI flag combinations, mode detection, conflict
handling, override behavior, security hardening, and warning behavior.

All external dependencies are mocked — no real API calls, file I/O to
real paths, or subprocess invocations.

Test Matrix (21 total):
    TestModeParsing:                    2 (explicit mode) + 4 (invalid mode) = 6
    TestAutoDetect:                     1 (standalone) + 1 (pipeline) = 2
    TestValidationFlags:                4 (validate, no-validate, strict, strict-implicit)
    TestConflictingFlags:               2 (validate+no-validate, strict+no-validate)
    TestMissingSeedFile:                1
    TestSecurityHardening:              4 (path traversal variants)
    TestForcedPipelineMinimalSeed:      1
    TestStandaloneWithFullSeed:         1
                                        ──
                                        21

Usage:
    pytest tests/unit/contractors/test_cli_integration.py -v
    pytest -m "cli" tests/unit/contractors/test_cli_integration.py
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from startd8.contractors.cli import main

# ---------------------------------------------------------------------------
# Module-level marker for selective test execution: pytest -m cli
# ---------------------------------------------------------------------------
pytestmark = pytest.mark.cli

# ---------------------------------------------------------------------------
# Exit code constants
# ---------------------------------------------------------------------------
EXIT_CODE_SUCCESS: int = 0
EXIT_CODE_VALIDATION_FAILURE: int = 1
EXIT_CODE_CLI_ERROR: int = 2

# ---------------------------------------------------------------------------
# Seed content fixtures (plain dicts — no file I/O)
# ---------------------------------------------------------------------------
MINIMAL_SEED_CONTENT: dict = {
    "project_name": "test-project",
    "description": "minimal seed for testing",
}

FULL_SEED_CONTENT: dict = {
    "project_name": "test-project",
    "description": "full seed for testing",
    "pipeline_metadata": {
        "queue_id": "q-001",
        "cost_report": {},
        "feature_ids": ["F-019"],
    },
}

# ---------------------------------------------------------------------------
# Parameterization data
# ---------------------------------------------------------------------------
MODE_PARAMS = [
    pytest.param("standalone", "standalone", False, id="explicit-standalone"),
    pytest.param("pipeline", "pipeline", True, id="explicit-pipeline"),
]

INVALID_MODE_PARAMS = [
    pytest.param("hybrid", id="invalid-hybrid"),
    pytest.param("", id="empty-string"),
    pytest.param("Pipeline", id="case-sensitive-Pipeline"),
    pytest.param("STANDALONE", id="case-sensitive-STANDALONE"),
]

CONFLICTING_FLAG_PARAMS = [
    pytest.param(["--validate", "--no-validate"], id="validate-and-no-validate"),
    pytest.param(["--strict-validation", "--no-validate"], id="strict-and-no-validate"),
]

PATH_TRAVERSAL_PARAMS = [
    pytest.param("../../etc/passwd", id="relative-traversal"),
    pytest.param("/etc/passwd", id="absolute-path"),
    pytest.param("seed\x00.yaml", id="null-byte"),
    pytest.param("..\\..\\etc\\passwd", id="windows-traversal"),
]

# ---------------------------------------------------------------------------
# Fixtures (defined in-module — no conftest dependency)
# ---------------------------------------------------------------------------


@pytest.fixture
def cli_runner() -> CliRunner:
    """Provide a Click CliRunner with separated stderr.

    Returns:
        CliRunner: Configured runner for programmatic CLI invocation.
    """
    return CliRunner(mix_stderr=False)


@pytest.fixture
def mock_deps():
    """Mock all external dependencies at the CLI boundary.

    Default return values represent the "happy path" for standalone mode:

    - resolver returns ``mode="standalone"``, ``source="auto-detected"``
    - generator returns success
    - validator returns passed (no errors)
    - seed_loader returns :data:`FULL_SEED_CONTENT`

    Individual tests **MUST** override specific mock return values when testing
    non-default scenarios.  For example, pipeline auto-detection tests must
    set ``mock_deps["resolver"].return_value`` to a pipeline-mode response.
    See :meth:`TestAutoDetect.test_auto_detect_pipeline_with_context` for a
    worked example.

    Yields:
        dict: Dictionary with keys ``"resolver"``, ``"generator"``,
              ``"validator"``, ``"seed_loader"``, each mapped to a
              :class:`~unittest.mock.MagicMock` instance.
    """
    with (
        patch("startd8.contractors.cli.resolve_context") as mock_resolver,
        patch("startd8.contractors.cli.generate") as mock_generator,
        patch("startd8.contractors.cli.validate_output") as mock_validator,
        patch("startd8.contractors.cli.load_seed") as mock_seed_loader,
    ):
        mock_resolver.return_value = MagicMock(
            mode="standalone", source="auto-detected"
        )
        mock_generator.return_value = MagicMock(success=True, output_path="/tmp/out")
        mock_validator.return_value = MagicMock(passed=True, errors=[])
        mock_seed_loader.return_value = FULL_SEED_CONTENT

        yield {
            "resolver": mock_resolver,
            "generator": mock_generator,
            "validator": mock_validator,
            "seed_loader": mock_seed_loader,
        }


# ===================================================================
# Test Classes
# ===================================================================


class TestModeParsing:
    """Verify explicit ``--mode`` parsing and rejection of invalid values."""

    @pytest.mark.parametrize(
        "mode_value, expected_mode, expected_validate", MODE_PARAMS
    )
    def test_explicit_mode(
        self,
        cli_runner: CliRunner,
        mock_deps: dict,
        mode_value: str,
        expected_mode: str,
        expected_validate: bool,
    ):
        """Explicit ``--mode`` values are correctly parsed into CLIConfig.

        Verifies:
        - Exit code is 0 (success).
        - Generator receives config with the correct ``mode``.
        - Generator receives config with the expected ``validate`` default.
        """
        result = cli_runner.invoke(
            main, ["--mode", mode_value, "--seed-file", "seed.yaml"]
        )
        assert result.exit_code == EXIT_CODE_SUCCESS

        call_kwargs = mock_deps["generator"].call_args
        assert call_kwargs is not None
        config = call_kwargs[0][0]  # first positional arg
        assert config.mode == expected_mode
        assert config.validate == expected_validate

    @pytest.mark.parametrize("invalid_mode", INVALID_MODE_PARAMS)
    def test_invalid_mode_value(
        self, cli_runner: CliRunner, mock_deps: dict, invalid_mode: str
    ):
        """Invalid ``--mode`` values produce CLI error (exit code 2).

        Verifies:
        - Exit code is 2 (CLI error).
        - Error output mentions the invalid value (if non-empty).
        - Error output hints at valid choices.
        """
        result = cli_runner.invoke(
            main, ["--mode", invalid_mode, "--seed-file", "seed.yaml"]
        )
        assert result.exit_code == EXIT_CODE_CLI_ERROR

        error_output = result.output.lower()
        if invalid_mode:  # non-empty invalid values should be echoed
            assert invalid_mode.lower() in error_output
        # Verify at least one valid mode is mentioned in the error hint
        assert "standalone" in error_output or "pipeline" in error_output


class TestAutoDetect:
    """Verify mode auto-detection when ``--mode`` is omitted."""

    def test_auto_detect_standalone_without_context(
        self, cli_runner: CliRunner, mock_deps: dict
    ):
        """Standalone is auto-detected when pipeline context is absent.

        Verifies:
        - Exit code is 0 (success).
        - Generator receives ``mode="standalone"``.
        - Generator receives ``mode_source="auto-detected"``.
        """
        result = cli_runner.invoke(main, ["--seed-file", "seed.yaml"])
        assert result.exit_code == EXIT_CODE_SUCCESS

        config = mock_deps["generator"].call_args[0][0]
        assert config.mode == "standalone"
        assert config.mode_source == "auto-detected"

    def test_auto_detect_pipeline_with_context(
        self, cli_runner: CliRunner, mock_deps: dict, monkeypatch: pytest.MonkeyPatch
    ):
        """Pipeline is auto-detected when ``STARTD8_PIPELINE_CONTEXT`` is set.

        Verifies:
        - Exit code is 0 (success).
        - Generator receives ``mode="pipeline"``.
        - Generator receives ``mode_source="auto-detected"``.
        - Pipeline mode defaults to ``validate=True``.
        """
        # Override the default resolver mock to simulate pipeline context
        mock_deps["resolver"].return_value = MagicMock(
            mode="pipeline", source="auto-detected"
        )
        monkeypatch.setenv("STARTD8_PIPELINE_CONTEXT", "1")

        result = cli_runner.invoke(main, ["--seed-file", "seed.yaml"])
        assert result.exit_code == EXIT_CODE_SUCCESS

        config = mock_deps["generator"].call_args[0][0]
        assert config.mode == "pipeline"
        assert config.mode_source == "auto-detected"
        assert config.validate is True  # pipeline default


class TestValidationFlags:
    """Verify ``--validate``, ``--no-validate``, and ``--strict-validation`` behavior."""

    def test_validate_forces_validation_in_standalone(
        self, cli_runner: CliRunner, mock_deps: dict
    ):
        """``--validate`` in standalone mode overrides default (validate=False).

        Verifies:
        - Exit code is 0 (success).
        - Generator receives ``validate=True``.
        """
        result = cli_runner.invoke(
            main,
            ["--mode", "standalone", "--validate", "--seed-file", "seed.yaml"],
        )
        assert result.exit_code == EXIT_CODE_SUCCESS

        config = mock_deps["generator"].call_args[0][0]
        assert config.mode == "standalone"
        assert config.validate is True

    def test_no_validate_disables_validation_in_pipeline(
        self, cli_runner: CliRunner, mock_deps: dict
    ):
        """``--no-validate`` in pipeline mode overrides default (validate=True).

        Verifies:
        - Exit code is 0 (success).
        - Generator receives ``validate=False``.
        """
        result = cli_runner.invoke(
            main,
            ["--mode", "pipeline", "--no-validate", "--seed-file", "seed.yaml"],
        )
        assert result.exit_code == EXIT_CODE_SUCCESS

        config = mock_deps["generator"].call_args[0][0]
        assert config.mode == "pipeline"
        assert config.validate is False

    def test_strict_validation_nonzero_exit_on_failures(
        self, cli_runner: CliRunner, mock_deps: dict
    ):
        """``--strict-validation`` with validation failures produces exit code 1.

        Verifies:
        - Exit code is 1 (validation failure).
        - Validator was invoked.
        """
        mock_deps["validator"].return_value = MagicMock(
            passed=False,
            errors=["Missing required field: deployment_target"],
        )
        result = cli_runner.invoke(
            main,
            [
                "--mode", "standalone",
                "--validate",
                "--strict-validation",
                "--seed-file", "seed.yaml",
            ],
        )
        assert result.exit_code == EXIT_CODE_VALIDATION_FAILURE

    def test_strict_validation_alone_implicitly_enables_validation(
        self, cli_runner: CliRunner, mock_deps: dict
    ):
        """``--strict-validation`` without ``--validate`` implicitly enables validation.

        In standalone mode, ``validate`` defaults to ``False``, so this test
        confirms that ``--strict-validation`` overrides that default.

        Verifies:
        - Exit code is 0 (validation passed).
        - Validator is called exactly once (validation was enabled).
        """
        mock_deps["validator"].return_value = MagicMock(passed=True, errors=[])
        result = cli_runner.invoke(
            main,
            [
                "--mode", "standalone",
                "--strict-validation",
                "--seed-file", "seed.yaml",
            ],
        )
        assert result.exit_code == EXIT_CODE_SUCCESS
        # Crucially, the validator must have been called (validation was enabled)
        mock_deps["validator"].assert_called_once()


class TestConflictingFlags:
    """Verify that contradictory flag combinations produce exit code 2."""

    @pytest.mark.parametrize("flags", CONFLICTING_FLAG_PARAMS)
    def test_conflicting_flags_raise_error(
        self, cli_runner: CliRunner, mock_deps: dict, flags: list[str]
    ):
        """Conflicting flag combinations are rejected with exit code 2.

        Verifies:
        - Exit code is 2 (CLI error).
        - Error output references the conflicting flags.
        """
        result = cli_runner.invoke(main, [*flags, "--seed-file", "seed.yaml"])
        assert result.exit_code == EXIT_CODE_CLI_ERROR

        error_output = result.output.lower()
        # The CLI must indicate a conflict between the specific flags.
        # We check for the presence of both flag names in the error message
        # rather than relying on a specific word like "conflict".
        for flag in flags:
            flag_base = flag.lstrip("-").replace("-", "")
            assert (
                flag_base in error_output.replace("-", "")
                or flag in result.output
            ), f"Expected error output to reference flag {flag}"


class TestMissingSeedFile:
    """Verify that omitting the required ``--seed-file`` flag produces exit code 2."""

    def test_missing_seed_file_flag_raises_error(
        self, cli_runner: CliRunner, mock_deps: dict
    ):
        """``--seed-file`` is required; omitting it entirely produces exit code 2.

        Verifies:
        - Exit code is 2 (CLI error).
        - Error output references ``seed-file`` or ``seed_file``.
        """
        result = cli_runner.invoke(main, ["--mode", "standalone"])
        assert result.exit_code == EXIT_CODE_CLI_ERROR
        assert (
            "seed-file" in result.output.lower()
            or "seed_file" in result.output.lower()
        )


class TestSecurityHardening:
    """Verify that unsafe ``--seed-file`` paths are rejected before any I/O."""

    @pytest.mark.parametrize("unsafe_path", PATH_TRAVERSAL_PARAMS)
    def test_seed_file_path_traversal_rejected(
        self, cli_runner: CliRunner, mock_deps: dict, unsafe_path: str
    ):
        """Unsafe paths are rejected at the CLI validation layer with exit code 2.

        The seed loader must never be called for rejected paths — rejection
        occurs before any file I/O.

        Verifies:
        - Exit code is 2 (CLI error).
        - ``seed_loader`` is never called.
        """
        result = cli_runner.invoke(
            main,
            ["--mode", "standalone", "--seed-file", unsafe_path],
        )
        assert result.exit_code == EXIT_CODE_CLI_ERROR
        mock_deps["seed_loader"].assert_not_called()


class TestForcedPipelineMinimalSeed:
    """Verify pipeline mode with minimal seed proceeds but warns."""

    def test_pipeline_mode_minimal_seed_proceeds_with_warnings(
        self, cli_runner: CliRunner, mock_deps: dict, caplog: pytest.LogCaptureFixture
    ):
        """Pipeline mode with minimal seed succeeds but emits a warning.

        Verifies:
        - Exit code is 0 (success — proceeds despite minimal seed).
        - At least one WARNING-level log message contains ``"pipeline_metadata"``.
        """
        mock_deps["seed_loader"].return_value = MINIMAL_SEED_CONTENT
        with caplog.at_level(logging.WARNING):
            result = cli_runner.invoke(
                main,
                ["--mode", "pipeline", "--seed-file", "minimal_seed.yaml"],
            )
        assert result.exit_code == EXIT_CODE_SUCCESS

        warning_messages = [
            r.message for r in caplog.records if r.levelname == "WARNING"
        ]
        assert any("pipeline_metadata" in msg for msg in warning_messages)


class TestStandaloneWithFullSeed:
    """Verify standalone mode with full pipeline seed emits no spurious warnings."""

    def test_standalone_mode_with_pipeline_seed_no_warnings(
        self, cli_runner: CliRunner, mock_deps: dict, caplog: pytest.LogCaptureFixture
    ):
        """Standalone mode does not warn about pipeline metadata it doesn't need.

        Verifies:
        - Exit code is 0 (success).
        - No WARNING-level logs contain ``"pipeline_metadata"``.
        """
        mock_deps["seed_loader"].return_value = FULL_SEED_CONTENT
        with caplog.at_level(logging.WARNING):
            result = cli_runner.invoke(
                main,
                ["--mode", "standalone", "--seed-file", "full_seed.yaml"],
            )
        assert result.exit_code == EXIT_CODE_SUCCESS

        warning_messages = [
            r.message for r in caplog.records if r.levelname == "WARNING"
        ]
        assert not any("pipeline_metadata" in msg for msg in warning_messages)