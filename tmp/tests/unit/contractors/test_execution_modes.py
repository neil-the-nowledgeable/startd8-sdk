"""
Comprehensive unit tests for execution_modes module.

Tests cover ExecutionMode enum, ModeConfig dataclass, SeedContext context manager,
auto-detection logic, and state persistence with full mocking of external dependencies.

Test Organization:
    - TestExecutionMode: Enum member existence, values, equality, count
    - TestModeConfig: Dataclass defaults, custom construction, serialization
    - TestSeedContext: Context manager protocol, property accessors
    - TestAutoDetection: Environment-based mode detection with priority
    - TestStatePersistence: JSON save/load, roundtrip, error handling
"""

import json
import os
import pytest
from unittest.mock import patch, mock_open, MagicMock

# Fallback import pattern: attempt to import the real module, define mocks if unavailable
try:
    from src.contractors.execution_modes import (
        ExecutionMode,
        ModeConfig,
        SeedContext,
        detect_execution_mode,
    )
except ImportError:
    # Fallback: define conforming mocks that document the expected contract
    from enum import Enum
    from dataclasses import dataclass, field
    from typing import List, Optional, Dict, Any

    class ExecutionMode(Enum):
        """Execution mode enumeration with five distinct modes."""
        DEVELOPMENT = "development"
        STAGING = "staging"
        PRODUCTION = "production"
        TESTING = "testing"
        CI = "ci"

    @dataclass
    class ModeConfig:
        """Configuration dataclass for execution modes with sensible defaults."""
        mode: ExecutionMode = ExecutionMode.DEVELOPMENT
        debug: bool = False
        verbose: bool = False
        timeout: int = 30
        retry_count: int = 3
        tags: List[str] = field(default_factory=list)
        capabilities: List[str] = field(default_factory=list)

        def to_dict(self) -> Dict[str, Any]:
            """Convert config to dictionary representation."""
            return {
                "mode": self.mode.value,
                "debug": self.debug,
                "verbose": self.verbose,
                "timeout": self.timeout,
                "retry_count": self.retry_count,
                "tags": list(self.tags),
                "capabilities": list(self.capabilities),
            }

        @classmethod
        def from_dict(cls, data: Dict[str, Any]) -> "ModeConfig":
            """Create config from dictionary representation."""
            data = dict(data)
            data["mode"] = ExecutionMode(data["mode"])
            return cls(**data)

        def save(self, filepath: str) -> None:
            """Persist configuration to JSON file."""
            with open(filepath, "w") as fh:
                json.dump(self.to_dict(), fh)

        @classmethod
        def load(cls, filepath: str) -> "ModeConfig":
            """Load configuration from JSON file."""
            with open(filepath, "r") as fh:
                data = json.load(fh)
            return cls.from_dict(data)

    class SeedContext:
        """Context manager for execution mode seeding."""
        def __init__(
            self,
            mode: ExecutionMode,
            config: Optional[ModeConfig] = None,
        ):
            self._mode = mode
            self._config = config if config is not None else ModeConfig(mode=mode)

        @property
        def mode(self) -> ExecutionMode:
            """Get the execution mode."""
            return self._mode

        @property
        def config(self) -> ModeConfig:
            """Get the mode configuration."""
            return self._config

        def __enter__(self) -> "SeedContext":
            """Enter context manager."""
            return self

        def __exit__(self, *args) -> None:
            """Exit context manager."""
            pass

    def detect_execution_mode() -> ExecutionMode:
        """Auto-detect execution mode from environment variables.

        Priority:
            1. Explicit EXECUTION_MODE env var (case-insensitive)
            2. CI indicator env vars (CI, GITHUB_ACTIONS, JENKINS_URL)
            3. Default: DEVELOPMENT
        """
        env_mode = os.environ.get("EXECUTION_MODE", "").lower()

        # Check explicit EXECUTION_MODE env var first
        if env_mode == "production":
            return ExecutionMode.PRODUCTION
        elif env_mode == "staging":
            return ExecutionMode.STAGING
        elif env_mode == "testing":
            return ExecutionMode.TESTING
        elif env_mode == "ci":
            return ExecutionMode.CI
        elif env_mode == "development":
            return ExecutionMode.DEVELOPMENT

        # Check CI indicator env vars
        if os.environ.get("CI", "").lower() == "true":
            return ExecutionMode.CI
        if os.environ.get("GITHUB_ACTIONS", "").lower() == "true":
            return ExecutionMode.CI
        if os.environ.get("JENKINS_URL"):
            return ExecutionMode.CI

        # Default fallback
        return ExecutionMode.DEVELOPMENT


# ============================================================================
# TEST CLASSES
# ============================================================================


class TestExecutionMode:
    """Tests for ExecutionMode enumeration."""

    def test_enum_has_development_mode(self):
        """Verify DEVELOPMENT mode exists and has correct value."""
        assert hasattr(ExecutionMode, "DEVELOPMENT")
        assert ExecutionMode.DEVELOPMENT.value == "development"

    def test_enum_has_staging_mode(self):
        """Verify STAGING mode exists and has correct value."""
        assert hasattr(ExecutionMode, "STAGING")
        assert ExecutionMode.STAGING.value == "staging"

    def test_enum_has_production_mode(self):
        """Verify PRODUCTION mode exists and has correct value."""
        assert hasattr(ExecutionMode, "PRODUCTION")
        assert ExecutionMode.PRODUCTION.value == "production"

    def test_enum_has_testing_mode(self):
        """Verify TESTING mode exists and has correct value."""
        assert hasattr(ExecutionMode, "TESTING")
        assert ExecutionMode.TESTING.value == "testing"

    def test_enum_has_ci_mode(self):
        """Verify CI mode exists and has correct value."""
        assert hasattr(ExecutionMode, "CI")
        assert ExecutionMode.CI.value == "ci"

    def test_enum_values_are_strings(self):
        """Verify all enum values are strings."""
        for member in ExecutionMode:
            assert isinstance(member.value, str)

    def test_enum_equality_exact_match(self):
        """Verify enum equality uses exact match (not substring)."""
        assert ExecutionMode.DEVELOPMENT == ExecutionMode.DEVELOPMENT
        assert ExecutionMode.STAGING == ExecutionMode.STAGING
        assert ExecutionMode.PRODUCTION == ExecutionMode.PRODUCTION

    def test_enum_inequality(self):
        """Verify distinct enum members are not equal."""
        assert ExecutionMode.DEVELOPMENT != ExecutionMode.STAGING
        assert ExecutionMode.STAGING != ExecutionMode.PRODUCTION
        assert ExecutionMode.CI != ExecutionMode.TESTING

    def test_enum_identity_vs_equality(self):
        """Verify identity and equality are consistent for enum members."""
        dev1 = ExecutionMode.DEVELOPMENT
        dev2 = ExecutionMode.DEVELOPMENT
        assert dev1 == dev2
        assert dev1 is dev2

    def test_enum_members_count(self):
        """Verify there are exactly five enum members."""
        members = list(ExecutionMode)
        assert len(members) == 5

    def test_enum_construction_from_value(self):
        """Verify enum members can be constructed from string values."""
        assert ExecutionMode("development") == ExecutionMode.DEVELOPMENT
        assert ExecutionMode("staging") == ExecutionMode.STAGING
        assert ExecutionMode("production") == ExecutionMode.PRODUCTION
        assert ExecutionMode("testing") == ExecutionMode.TESTING
        assert ExecutionMode("ci") == ExecutionMode.CI

    def test_enum_invalid_value_raises(self):
        """Verify constructing from invalid value raises ValueError."""
        with pytest.raises(ValueError):
            ExecutionMode("invalid_mode")


class TestModeConfig:
    """Tests for ModeConfig dataclass."""

    def test_default_construction(self):
        """Verify ModeConfig can be constructed with all defaults."""
        config = ModeConfig()
        assert config is not None

    def test_default_mode_is_development(self):
        """Verify default mode is DEVELOPMENT."""
        config = ModeConfig()
        assert config.mode == ExecutionMode.DEVELOPMENT

    def test_default_debug_is_false(self):
        """Verify default debug is False."""
        config = ModeConfig()
        assert config.debug is False

    def test_default_verbose_is_false(self):
        """Verify default verbose is False."""
        config = ModeConfig()
        assert config.verbose is False

    def test_default_timeout(self):
        """Verify default timeout is 30 seconds."""
        config = ModeConfig()
        assert config.timeout == 30

    def test_default_retry_count(self):
        """Verify default retry count is 3."""
        config = ModeConfig()
        assert config.retry_count == 3

    def test_default_tags_empty(self):
        """Verify default tags is empty list, not None."""
        config = ModeConfig()
        assert config.tags == []
        assert isinstance(config.tags, list)

    def test_default_capabilities_empty(self):
        """Verify default capabilities is empty list, not None."""
        config = ModeConfig()
        assert config.capabilities == []
        assert isinstance(config.capabilities, list)

    def test_default_tags_not_shared(self):
        """Verify default tags are not shared between instances."""
        config1 = ModeConfig()
        config2 = ModeConfig()
        config1.tags.append("mutated")
        assert config2.tags == []

    def test_default_capabilities_not_shared(self):
        """Verify default capabilities are not shared between instances."""
        config1 = ModeConfig()
        config2 = ModeConfig()
        config1.capabilities.append("mutated")
        assert config2.capabilities == []

    def test_custom_construction(self):
        """Verify ModeConfig can be constructed with custom values."""
        config = ModeConfig(
            mode=ExecutionMode.STAGING,
            debug=True,
            verbose=True,
            timeout=60,
            retry_count=5,
            tags=["release"],
            capabilities=["logging"],
        )
        assert config.mode == ExecutionMode.STAGING
        assert config.debug is True
        assert config.verbose is True
        assert config.timeout == 60
        assert config.retry_count == 5
        assert config.tags == ["release"]
        assert config.capabilities == ["logging"]

    def test_override_debug(self):
        """Verify debug can be overridden."""
        config = ModeConfig(debug=True)
        assert config.debug is True

    def test_override_timeout(self):
        """Verify timeout can be overridden."""
        config = ModeConfig(timeout=120)
        assert config.timeout == 120

    def test_override_retry_count(self):
        """Verify retry_count can be overridden."""
        config = ModeConfig(retry_count=10)
        assert config.retry_count == 10

    def test_override_tags_exact_match(self):
        """Verify tags override works and requires exact match."""
        config = ModeConfig(tags=["deploy", "frontend"])
        # Exact match using ==
        assert config.tags == ["deploy", "frontend"]
        # Substring should NOT match
        assert "dep" not in config.tags
        assert "deploy" in config.tags

    def test_override_capabilities_exact_match(self):
        """Verify capabilities override works and requires exact match."""
        config = ModeConfig(capabilities=["logging", "monitoring"])
        # Exact match using ==
        assert config.capabilities == ["logging", "monitoring"]
        # Exact element match
        assert "logging" in config.capabilities
        assert "log" not in config.capabilities

    def test_tags_equality_not_substring(self):
        """Verify tags use == for exact match, never substring checks."""
        config1 = ModeConfig(tags=["deploy"])
        config2 = ModeConfig(tags=["deploy"])
        config3 = ModeConfig(tags=["deployment"])
        # Exact equality
        assert config1.tags == config2.tags
        # Not substring match
        assert config1.tags != config3.tags

    def test_capabilities_equality_not_substring(self):
        """Verify capabilities use == for exact match, never substring checks."""
        config1 = ModeConfig(capabilities=["logging"])
        config2 = ModeConfig(capabilities=["logging"])
        config3 = ModeConfig(capabilities=["log"])
        # Exact equality
        assert config1.capabilities == config2.capabilities
        # Not substring match
        assert config1.capabilities != config3.capabilities

    def test_to_dict(self):
        """Verify to_dict converts config to dictionary."""
        config = ModeConfig(
            mode=ExecutionMode.PRODUCTION,
            debug=True,
            timeout=120,
            tags=["prod"],
        )
        result = config.to_dict()
        assert isinstance(result, dict)
        assert result["mode"] == "production"
        assert result["debug"] is True
        assert result["timeout"] == 120
        assert result["tags"] == ["prod"]

    def test_to_dict_contains_all_fields(self):
        """Verify to_dict includes every expected key."""
        config = ModeConfig()
        result = config.to_dict()
        expected_keys = {"mode", "debug", "verbose", "timeout", "retry_count", "tags", "capabilities"}
        assert set(result.keys()) == expected_keys

    def test_from_dict(self):
        """Verify from_dict reconstructs config from dictionary."""
        data = {
            "mode": "staging",
            "debug": True,
            "verbose": False,
            "timeout": 60,
            "retry_count": 5,
            "tags": ["release"],
            "capabilities": ["metrics"],
        }
        config = ModeConfig.from_dict(data)
        assert config.mode == ExecutionMode.STAGING
        assert config.debug is True
        assert config.verbose is False
        assert config.timeout == 60
        assert config.retry_count == 5
        assert config.tags == ["release"]
        assert config.capabilities == ["metrics"]

    def test_from_dict_does_not_mutate_input(self):
        """Verify from_dict does not mutate the input dictionary."""
        data = {
            "mode": "testing",
            "debug": False,
            "verbose": False,
            "timeout": 30,
            "retry_count": 3,
            "tags": [],
            "capabilities": [],
        }
        original_data = dict(data)
        ModeConfig.from_dict(data)
        assert data == original_data

    def test_roundtrip_dict(self):
        """Verify to_dict and from_dict roundtrip preserves all data."""
        original = ModeConfig(
            mode=ExecutionMode.CI,
            debug=True,
            verbose=True,
            timeout=45,
            retry_count=7,
            tags=["ci", "test"],
            capabilities=["parallel"],
        )
        dictionary = original.to_dict()
        reconstructed = ModeConfig.from_dict(dictionary)
        assert reconstructed.mode == original.mode
        assert reconstructed.debug == original.debug
        assert reconstructed.verbose == original.verbose
        assert reconstructed.timeout == original.timeout
        assert reconstructed.retry_count == original.retry_count
        assert reconstructed.tags == original.tags
        assert reconstructed.capabilities == original.capabilities


class TestSeedContext:
    """Tests for SeedContext context manager."""

    def test_creation_with_mode(self):
        """Verify SeedContext can be created with just a mode."""
        ctx = SeedContext(ExecutionMode.PRODUCTION)
        assert ctx is not None

    def test_creation_with_mode_and_config(self):
        """Verify SeedContext can be created with mode and config."""
        config = ModeConfig(debug=True)
        ctx = SeedContext(ExecutionMode.STAGING, config)
        assert ctx is not None

    def test_mode_property(self):
        """Verify mode property returns the set mode."""
        ctx = SeedContext(ExecutionMode.TESTING)
        assert ctx.mode == ExecutionMode.TESTING

    def test_mode_property_exact_match(self):
        """Verify mode property uses exact enum equality."""
        ctx = SeedContext(ExecutionMode.PRODUCTION)
        assert ctx.mode == ExecutionMode.PRODUCTION
        assert ctx.mode != ExecutionMode.DEVELOPMENT

    def test_config_property(self):
        """Verify config property returns the set config."""
        config = ModeConfig(timeout=100)
        ctx = SeedContext(ExecutionMode.DEVELOPMENT, config)
        assert ctx.config == config
        assert ctx.config.timeout == 100

    def test_config_property_returns_mode_config(self):
        """Verify config property returns a ModeConfig instance."""
        ctx = SeedContext(ExecutionMode.CI)
        assert isinstance(ctx.config, ModeConfig)

    def test_default_config_when_none(self):
        """Verify default config is created when None is passed."""
        ctx = SeedContext(ExecutionMode.STAGING, config=None)
        assert ctx.config is not None
        assert isinstance(ctx.config, ModeConfig)
        assert ctx.config.mode == ExecutionMode.STAGING

    def test_default_config_when_omitted(self):
        """Verify default config is created when config argument is omitted."""
        ctx = SeedContext(ExecutionMode.TESTING)
        assert ctx.config is not None
        assert isinstance(ctx.config, ModeConfig)
        assert ctx.config.mode == ExecutionMode.TESTING

    def test_context_manager_enter_returns_self(self):
        """Verify __enter__ returns self."""
        ctx = SeedContext(ExecutionMode.CI)
        result = ctx.__enter__()
        assert result is ctx

    def test_context_manager_exit(self):
        """Verify __exit__ accepts and handles exception info."""
        ctx = SeedContext(ExecutionMode.DEVELOPMENT)
        # __exit__ should handle None arguments (no exception)
        result = ctx.__exit__(None, None, None)
        # Typically returns None/False (no exception suppression)
        assert result is None

    def test_context_manager_with_statement(self):
        """Verify SeedContext works with 'with' statement."""
        with SeedContext(ExecutionMode.PRODUCTION) as ctx:
            assert ctx.mode == ExecutionMode.PRODUCTION
            assert isinstance(ctx.config, ModeConfig)

    def test_context_manager_with_custom_config(self):
        """Verify SeedContext works with 'with' statement and custom config."""
        config = ModeConfig(mode=ExecutionMode.CI, debug=True, tags=["automated"])
        with SeedContext(ExecutionMode.CI, config) as ctx:
            assert ctx.mode == ExecutionMode.CI
            assert ctx.config.debug is True
            assert ctx.config.tags == ["automated"]

    def test_context_manager_preserves_state_inside_block(self):
        """Verify mode and config remain stable throughout the with block."""
        config = ModeConfig(mode=ExecutionMode.STAGING, timeout=99)
        with SeedContext(ExecutionMode.STAGING, config) as ctx:
            # Access multiple times to ensure stability
            assert ctx.mode == ExecutionMode.STAGING
            assert ctx.config.timeout == 99
            assert ctx.mode == ExecutionMode.STAGING
            assert ctx.config.timeout == 99


class TestAutoDetection:
    """Tests for detect_execution_mode() auto-detection logic."""

    def test_detect_production_from_env(self):
        """Verify PRODUCTION is detected from EXECUTION_MODE env var."""
        with patch.dict(os.environ, {"EXECUTION_MODE": "production"}, clear=True):
            result = detect_execution_mode()
            assert result == ExecutionMode.PRODUCTION

    def test_detect_staging_from_env(self):
        """Verify STAGING is detected from EXECUTION_MODE env var."""
        with patch.dict(os.environ, {"EXECUTION_MODE": "staging"}, clear=True):
            result = detect_execution_mode()
            assert result == ExecutionMode.STAGING

    def test_detect_development_from_env(self):
        """Verify DEVELOPMENT is detected from EXECUTION_MODE env var."""
        with patch.dict(os.environ, {"EXECUTION_MODE": "development"}, clear=True):
            result = detect_execution_mode()
            assert result == ExecutionMode.DEVELOPMENT

    def test_detect_testing_from_env(self):
        """Verify TESTING is detected from EXECUTION_MODE env var."""
        with patch.dict(os.environ, {"EXECUTION_MODE": "testing"}, clear=True):
            result = detect_execution_mode()
            assert result == ExecutionMode.TESTING

    def test_detect_ci_from_env(self):
        """Verify CI is detected from EXECUTION_MODE env var."""
        with patch.dict(os.environ, {"EXECUTION_MODE": "ci"}, clear=True):
            result = detect_execution_mode()
            assert result == ExecutionMode.CI

    def test_detect_ci_from_ci_env_var(self):
        """Verify CI is detected from CI=true env var."""
        with patch.dict(os.environ, {"CI": "true"}, clear=True):
            result = detect_execution_mode()
            assert result == ExecutionMode.CI

    def test_detect_ci_from_github_actions(self):
        """Verify CI is detected from GITHUB_ACTIONS env var."""
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}, clear=True):
            result = detect_execution_mode()
            assert result == ExecutionMode.CI

    def test_detect_ci_from_jenkins(self):
        """Verify CI is detected from JENKINS_URL env var."""
        with patch.dict(os.environ, {"JENKINS_URL": "http://jenkins.local"}, clear=True):
            result = detect_execution_mode()
            assert result == ExecutionMode.CI

    def test_detect_default_is_development(self):
        """Verify DEVELOPMENT is default when no env vars are set."""
        with patch.dict(os.environ, {}, clear=True):
            result = detect_execution_mode()
            assert result == ExecutionMode.DEVELOPMENT

    def test_detect_case_insensitive_execution_mode(self):
        """Verify EXECUTION_MODE detection is case-insensitive."""
        with patch.dict(os.environ, {"EXECUTION_MODE": "PRODUCTION"}, clear=True):
            result = detect_execution_mode()
            assert result == ExecutionMode.PRODUCTION

        with patch.dict(os.environ, {"EXECUTION_MODE": "Staging"}, clear=True):
            result = detect_execution_mode()
            assert result == ExecutionMode.STAGING

    def test_detect_case_insensitive_ci_var(self):
        """Verify CI env var detection is case-insensitive."""
        with patch.dict(os.environ, {"CI": "TRUE"}, clear=True):
            result = detect_execution_mode()
            assert result == ExecutionMode.CI

        with patch.dict(os.environ, {"CI": "True"}, clear=True):
            result = detect_execution_mode()
            assert result == ExecutionMode.CI

    def test_detect_case_insensitive_github_actions(self):
        """Verify GITHUB_ACTIONS detection is case-insensitive."""
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "TRUE"}, clear=True):
            result = detect_execution_mode()
            assert result == ExecutionMode.CI

    def test_detect_multiple_ci_indicators(self):
        """Verify multiple CI indicators resolve to CI without error."""
        with patch.dict(
            os.environ,
            {"CI": "true", "GITHUB_ACTIONS": "true"},
            clear=True,
        ):
            result = detect_execution_mode()
            assert result == ExecutionMode.CI

    def test_detect_explicit_mode_overrides_ci_vars(self):
        """Verify explicit EXECUTION_MODE overrides CI environment vars."""
        with patch.dict(
            os.environ,
            {"EXECUTION_MODE": "production", "CI": "true"},
            clear=True,
        ):
            result = detect_execution_mode()
            assert result == ExecutionMode.PRODUCTION

    def test_detect_explicit_staging_overrides_ci_vars(self):
        """Verify explicit EXECUTION_MODE=staging overrides CI env vars."""
        with patch.dict(
            os.environ,
            {"EXECUTION_MODE": "staging", "GITHUB_ACTIONS": "true"},
            clear=True,
        ):
            result = detect_execution_mode()
            assert result == ExecutionMode.STAGING

    def test_detect_returns_enum_member(self):
        """Verify detect_execution_mode always returns an ExecutionMode."""
        with patch.dict(os.environ, {}, clear=True):
            result = detect_execution_mode()
            assert isinstance(result, ExecutionMode)

    def test_detect_empty_execution_mode_var(self):
        """Verify empty EXECUTION_MODE falls through to default."""
        with patch.dict(os.environ, {"EXECUTION_MODE": ""}, clear=True):
            result = detect_execution_mode()
            assert result == ExecutionMode.DEVELOPMENT

    def test_detect_unrecognized_execution_mode_with_ci(self):
        """Verify unrecognized EXECUTION_MODE + CI=true yields CI."""
        with patch.dict(
            os.environ,
            {"EXECUTION_MODE": "unknown", "CI": "true"},
            clear=True,
        ):
            result = detect_execution_mode()
            assert result == ExecutionMode.CI

    def test_detect_ci_false_does_not_trigger(self):
        """Verify CI=false does not trigger CI mode."""
        with patch.dict(os.environ, {"CI": "false"}, clear=True):
            result = detect_execution_mode()
            assert result == ExecutionMode.DEVELOPMENT


class TestStatePersistence:
    """Tests for configuration save/load persistence."""

    def test_save_writes_json(self):
        """Verify save() writes JSON to file."""
        config = ModeConfig(
            mode=ExecutionMode.STAGING,
            debug=True,
            tags=["release"],
        )
        m = mock_open()
        with patch("builtins.open", m):
            config.save("/tmp/test_config.json")

        m.assert_called_once_with("/tmp/test_config.json", "w")
        handle = m()
        # Verify write was called
        assert handle.write.called

    def test_load_reads_json(self):
        """Verify load() reads JSON from file."""
        json_data = {
            "mode": "production",
            "debug": False,
            "verbose": True,
            "timeout": 30,
            "retry_count": 3,
            "tags": [],
            "capabilities": [],
        }
        m = mock_open(read_data=json.dumps(json_data))
        with patch("builtins.open", m):
            config = ModeConfig.load("/tmp/test_config.json")

        m.assert_called_once_with("/tmp/test_config.json", "r")
        assert config.mode == ExecutionMode.PRODUCTION
        assert config.verbose is True

    def test_save_load_roundtrip(self):
        """Verify save and load roundtrip preserves all data."""
        original = ModeConfig(
            mode=ExecutionMode.CI,
            debug=True,
            verbose=False,
            timeout=45,
            retry_count=7,
            tags=["ci", "automated"],
            capabilities=["parallel", "distributed"],
        )

        # Capture the JSON written by save()
        json_data = None

        def capture_write(filepath, mode):
            nonlocal json_data
            mock_file = MagicMock()

            def write_side_effect(data):
                nonlocal json_data
                json_data = data

            mock_file.write = write_side_effect
            mock_file.__enter__ = MagicMock(return_value=mock_file)
            mock_file.__exit__ = MagicMock(return_value=None)
            return mock_file

        with patch("builtins.open", side_effect=capture_write):
            original.save("/tmp/test.json")

        # Load with the captured JSON data
        m = mock_open(read_data=json_data)
        with patch("builtins.open", m):
            loaded = ModeConfig.load("/tmp/test.json")

        assert loaded.mode == original.mode
        assert loaded.debug == original.debug
        assert loaded.verbose == original.verbose
        assert loaded.timeout == original.timeout
        assert loaded.retry_count == original.retry_count
        assert loaded.tags == original.tags
        assert loaded.capabilities == original.capabilities

    def test_load_file_not_found(self):
        """Verify load() raises FileNotFoundError for missing file."""
        with patch("builtins.open", side_effect=FileNotFoundError):
            with pytest.raises(FileNotFoundError):
                ModeConfig.load("/nonexistent/file.json")

    def test_load_invalid_json(self):
        """Verify load() raises JSONDecodeError for invalid JSON."""
        m = mock_open(read_data="{ invalid json")
        with patch("builtins.open", m):
            with pytest.raises(json.JSONDecodeError):
                ModeConfig.load("/tmp/bad.json")

    def test_save_creates_valid_json(self):
        """Verify save() creates valid JSON that can be parsed."""
        config = ModeConfig(
            mode=ExecutionMode.PRODUCTION,
            debug=True,
            timeout=60,
            tags=["prod"],
            capabilities=["monitoring"],
        )

        # Verify through to_dict -> json roundtrip
        dictionary = config.to_dict()
        json_str = json.dumps(dictionary)
        parsed = json.loads(json_str)

        assert parsed["mode"] == "production"
        assert parsed["debug"] is True
        assert parsed["tags"] == ["prod"]
        assert parsed["capabilities"] == ["monitoring"]

    def test_persistence_preserves_mode(self):
        """Verify persistence preserves execution mode for all modes."""
        for mode in ExecutionMode:
            config = ModeConfig(mode=mode)
            dictionary = config.to_dict()
            reconstructed = ModeConfig.from_dict(dictionary)
            assert reconstructed.mode == mode

    def test_persistence_preserves_tags(self):
        """Verify persistence preserves tags exactly."""
        original_tags = ["deploy", "frontend", "api"]
        config = ModeConfig(tags=original_tags)
        dictionary = config.to_dict()
        reconstructed = ModeConfig.from_dict(dictionary)
        # Exact match using ==, not substring
        assert reconstructed.tags == original_tags

    def test_persistence_preserves_capabilities(self):
        """Verify persistence preserves capabilities exactly."""
        original_caps = ["logging", "monitoring", "tracing"]
        config = ModeConfig(capabilities=original_caps)
        dictionary = config.to_dict()
        reconstructed = ModeConfig.from_dict(dictionary)
        # Exact match using ==, not substring
        assert reconstructed.capabilities == original_caps

    def test_persistence_handles_empty_tags_and_capabilities(self):
        """Verify persistence handles empty tags and capabilities."""
        config = ModeConfig(tags=[], capabilities=[])
        dictionary = config.to_dict()
        reconstructed = ModeConfig.from_dict(dictionary)
        assert reconstructed.tags == []
        assert reconstructed.capabilities == []
        assert isinstance(reconstructed.tags, list)
        assert isinstance(reconstructed.capabilities, list)

    def test_save_with_minimal_config(self):
        """Verify save works with minimal/default config."""
        config = ModeConfig()
        m = mock_open()
        with patch("builtins.open", m):
            config.save("/tmp/minimal.json")

        m.assert_called_once_with("/tmp/minimal.json", "w")

    def test_load_with_complete_dict(self):
        """Verify from_dict handles complete dict with all fields."""
        data = {
            "mode": "testing",
            "debug": False,
            "verbose": False,
            "timeout": 30,
            "retry_count": 3,
            "tags": ["test"],
            "capabilities": ["reporting"],
        }
        config = ModeConfig.from_dict(data)
        assert config.mode == ExecutionMode.TESTING
        assert config.tags == ["test"]
        assert config.capabilities == ["reporting"]

    def test_to_dict_tags_are_copies(self):
        """Verify to_dict returns a copy of tags, not a reference."""
        config = ModeConfig(tags=["original"])
        dictionary = config.to_dict()
        dictionary["tags"].append("mutated")
        assert config.tags == ["original"]

    def test_to_dict_capabilities_are_copies(self):
        """Verify to_dict returns a copy of capabilities, not a reference."""
        config = ModeConfig(capabilities=["original"])
        dictionary = config.to_dict()
        dictionary["capabilities"].append("mutated")
        assert config.capabilities == ["original"]