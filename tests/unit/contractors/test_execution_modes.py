"""
Phase 1 Tests — ExecutionMode, ModeConfig, SeedContext, Auto-Detection, Property Accessors

This test suite validates the core execution mode infrastructure for the two-mode execution
model (standalone / pipeline). It covers:

1. ExecutionMode enum — value correctness and exhaustiveness
2. ModeConfig factory — construction for each mode with correct defaults
3. SeedContext — data container for pipeline context propagation
4. Auto-detection — logic that determines mode from available context
5. Property accessors — backward compatibility ensuring standalone behavior is the zero-change default
6. State persistence round-trip — serialization/deserialization of mode configuration

All tests are pure unit tests with no external dependencies. No fixtures are required beyond
standard pytest.

Critical Parameters:
- ExecutionMode.STANDALONE: must equal string "standalone" (exact match via ==)
- ExecutionMode.PIPELINE: must equal string "pipeline" (exact match via ==)
- ModeConfig.mode: attribute name for the active execution mode
- ModeConfig.tags: list of string tags; matched with ==, never 'in' substring checks
- ModeConfig.capabilities: list of string capabilities; matched with ==, never 'in' substring checks
- SeedContext attributes: onboarding_metadata, architectural_context, design_calibration
- Auto-detection function signature: detect_execution_mode(seed_context: Optional[SeedContext] = None) -> ExecutionMode
- Auto-detection considers empty dicts ({}) as **not populated** — only non-None, non-empty-dict values trigger pipeline mode
- No OpenTelemetry instrumentation in the test suite or tested modules
"""

import pytest
import json
from unittest.mock import MagicMock, PropertyMock

from startd8.contractors.execution_modes import (
    ExecutionMode,
    ModeConfig,
    SeedContext,
    detect_execution_mode,
)


# ============================================================================
# Module-Level Expected Default Constants
# ============================================================================
# Defined at module level to reduce duplication and enable single-point edits.

# Expected defaults for standalone mode
STANDALONE_DEFAULT_TAGS = ["standalone"]
STANDALONE_DEFAULT_CAPABILITIES = ["generation"]

# Expected defaults for pipeline mode
PIPELINE_DEFAULT_TAGS = ["pipeline", "context-aware"]
PIPELINE_DEFAULT_CAPABILITIES = ["generation", "validation", "context-exploitation"]


# ============================================================================
# TestExecutionModeEnum — Enum value tests
# ============================================================================


class TestExecutionModeEnum:
    """Validate ExecutionMode enum: value correctness and exhaustiveness."""

    def test_standalone_value(self):
        """ExecutionMode.STANDALONE must equal string 'standalone'."""
        assert ExecutionMode.STANDALONE == "standalone"
        assert ExecutionMode.STANDALONE.value == "standalone"

    def test_pipeline_value(self):
        """ExecutionMode.PIPELINE must equal string 'pipeline'."""
        assert ExecutionMode.PIPELINE == "pipeline"
        assert ExecutionMode.PIPELINE.value == "pipeline"

    def test_enum_is_exhaustive_two_members(self):
        """ExecutionMode enum must have exactly two members."""
        members = list(ExecutionMode)
        assert len(members) == 2
        assert set(m.value for m in members) == {"standalone", "pipeline"}

    def test_invalid_value_raises(self):
        """Constructing ExecutionMode with invalid value raises ValueError."""
        with pytest.raises(ValueError):
            ExecutionMode("nonexistent")

    def test_string_identity(self):
        """ExecutionMode members are str subclass instances."""
        assert isinstance(ExecutionMode.STANDALONE, str)
        assert isinstance(ExecutionMode.PIPELINE, str)


# ============================================================================
# TestModeConfigFactory — ModeConfig factory tests
# ============================================================================


class TestModeConfigFactory:
    """Validate ModeConfig factory methods and defaults."""

    def test_standalone_factory_defaults(self):
        """ModeConfig.standalone() creates config with correct defaults."""
        config = ModeConfig.standalone()
        assert config.mode == ExecutionMode.STANDALONE
        assert config.seed_context is None
        assert config.tags == STANDALONE_DEFAULT_TAGS
        assert config.capabilities == STANDALONE_DEFAULT_CAPABILITIES

    def test_pipeline_factory_with_seed(self):
        """ModeConfig.pipeline(seed_context=...) creates config with provided seed."""
        seed = SeedContext(
            onboarding_metadata={"key": "value"},
            architectural_context={"patterns": ["strategy"]},
            design_calibration={"depth": "standard"},
        )
        config = ModeConfig.pipeline(seed_context=seed)
        assert config.mode == ExecutionMode.PIPELINE
        assert config.seed_context is seed
        assert config.tags == PIPELINE_DEFAULT_TAGS
        assert config.capabilities == PIPELINE_DEFAULT_CAPABILITIES

    def test_pipeline_factory_without_seed_defaults_to_empty_seed_context(self):
        """Pipeline mode without explicit context defaults to empty SeedContext()."""
        config = ModeConfig.pipeline()
        assert config.mode == ExecutionMode.PIPELINE
        assert config.seed_context is not None
        assert config.seed_context.onboarding_metadata is None
        assert config.seed_context.architectural_context is None
        assert config.seed_context.design_calibration is None

    def test_none_mode_rejected(self):
        """ModeConfig cannot be constructed with mode=None."""
        with pytest.raises((TypeError, ValueError)):
            ModeConfig(mode=None, tags=[], capabilities=[])


# ============================================================================
# TestSeedContext — SeedContext construction & round-trip
# ============================================================================


class TestSeedContext:
    """Validate SeedContext data container and serialization."""

    def test_empty_construction(self):
        """SeedContext() initializes all fields to None."""
        ctx = SeedContext()
        assert ctx.onboarding_metadata is None
        assert ctx.architectural_context is None
        assert ctx.design_calibration is None

    def test_full_construction(self):
        """SeedContext accepts all three domain concept fields."""
        ctx = SeedContext(
            onboarding_metadata={"project": "test"},
            architectural_context={"patterns": ["strategy"]},
            design_calibration={"depth": "full"},
        )
        assert ctx.onboarding_metadata == {"project": "test"}
        assert ctx.architectural_context == {"patterns": ["strategy"]}
        assert ctx.design_calibration == {"depth": "full"}

    def test_partial_construction(self):
        """SeedContext accepts partial field initialization."""
        ctx = SeedContext(onboarding_metadata={"only": "this"})
        assert ctx.onboarding_metadata == {"only": "this"}
        assert ctx.architectural_context is None
        assert ctx.design_calibration is None

    def test_seed_context_to_dict_empty(self):
        """Empty SeedContext.to_dict() includes all fields as None."""
        ctx = SeedContext()
        serialized = ctx.to_dict()
        assert serialized["onboarding_metadata"] is None
        assert serialized["architectural_context"] is None
        assert serialized["design_calibration"] is None

    def test_seed_context_to_dict_partial(self):
        """SeedContext.to_dict() preserves partial population."""
        ctx = SeedContext(onboarding_metadata={"key": "value"})
        serialized = ctx.to_dict()
        assert serialized["onboarding_metadata"] == {"key": "value"}
        assert serialized["architectural_context"] is None
        assert serialized["design_calibration"] is None

    def test_seed_context_from_dict_empty(self):
        """SeedContext.from_dict() with null fields creates empty context."""
        data = {
            "onboarding_metadata": None,
            "architectural_context": None,
            "design_calibration": None,
        }
        ctx = SeedContext.from_dict(data)
        assert ctx.onboarding_metadata is None
        assert ctx.architectural_context is None
        assert ctx.design_calibration is None

    def test_seed_context_from_dict_partial(self):
        """SeedContext.from_dict() deserializes partial data correctly."""
        data = {
            "onboarding_metadata": {"project": "test"},
            "architectural_context": None,
            "design_calibration": {"depth": "standard"},
        }
        ctx = SeedContext.from_dict(data)
        assert ctx.onboarding_metadata == {"project": "test"}
        assert ctx.architectural_context is None
        assert ctx.design_calibration == {"depth": "standard"}


# ============================================================================
# TestAutoDetection — Auto-detection scenarios
# ============================================================================


class TestAutoDetection:
    """Validate detect_execution_mode logic and edge cases."""

    def test_no_context_returns_standalone(self):
        """detect_execution_mode() with no argument returns STANDALONE."""
        result = detect_execution_mode()
        assert result == ExecutionMode.STANDALONE

    def test_none_context_returns_standalone(self):
        """detect_execution_mode(seed_context=None) returns STANDALONE."""
        result = detect_execution_mode(seed_context=None)
        assert result == ExecutionMode.STANDALONE

    def test_empty_seed_context_returns_standalone(self):
        """detect_execution_mode with empty SeedContext returns STANDALONE."""
        result = detect_execution_mode(seed_context=SeedContext())
        assert result == ExecutionMode.STANDALONE

    def test_populated_seed_context_returns_pipeline(self):
        """detect_execution_mode with non-empty context returns PIPELINE."""
        ctx = SeedContext(onboarding_metadata={"project": "real"})
        result = detect_execution_mode(seed_context=ctx)
        assert result == ExecutionMode.PIPELINE

    def test_full_seed_context_returns_pipeline(self):
        """detect_execution_mode with all fields populated returns PIPELINE."""
        ctx = SeedContext(
            onboarding_metadata={"project": "real"},
            architectural_context={"arch": True},
            design_calibration={"depth": "full"},
        )
        result = detect_execution_mode(seed_context=ctx)
        assert result == ExecutionMode.PIPELINE

    @pytest.mark.parametrize("field,value", [
        ("onboarding_metadata", {"key": "val"}),
        ("architectural_context", {"key": "val"}),
        ("design_calibration", {"key": "val"}),
    ])
    def test_any_single_populated_field_triggers_pipeline(self, field, value):
        """Any single non-empty field in context triggers PIPELINE mode."""
        ctx = SeedContext(**{field: value})
        result = detect_execution_mode(seed_context=ctx)
        assert result == ExecutionMode.PIPELINE

    @pytest.mark.parametrize("field", [
        "onboarding_metadata",
        "architectural_context",
        "design_calibration",
    ])
    def test_empty_dict_field_treated_as_not_populated(self, field):
        """Empty dict ({}) is not considered populated for auto-detection."""
        ctx = SeedContext(**{field: {}})
        result = detect_execution_mode(seed_context=ctx)
        assert result == ExecutionMode.STANDALONE

    def test_all_fields_empty_dicts_returns_standalone(self):
        """SeedContext with all fields as empty dicts returns STANDALONE."""
        ctx = SeedContext(
            onboarding_metadata={},
            architectural_context={},
            design_calibration={},
        )
        result = detect_execution_mode(seed_context=ctx)
        assert result == ExecutionMode.STANDALONE

    def test_mix_of_empty_and_populated_returns_pipeline(self):
        """One populated field among empty dicts is enough for PIPELINE."""
        ctx = SeedContext(
            onboarding_metadata={},
            architectural_context={"patterns": ["strategy"]},
            design_calibration={},
        )
        result = detect_execution_mode(seed_context=ctx)
        assert result == ExecutionMode.PIPELINE

    def test_corrupt_context_attribute_error_falls_back_to_standalone(self):
        """Context where attribute access raises AttributeError falls back to STANDALONE."""
        mock_ctx = MagicMock(spec=SeedContext)
        type(mock_ctx).onboarding_metadata = PropertyMock(side_effect=AttributeError)
        type(mock_ctx).architectural_context = PropertyMock(side_effect=AttributeError)
        type(mock_ctx).design_calibration = PropertyMock(side_effect=AttributeError)
        result = detect_execution_mode(seed_context=mock_ctx)
        assert result == ExecutionMode.STANDALONE

    def test_corrupt_context_type_error_falls_back_to_standalone(self):
        """Context where attribute access raises TypeError falls back to STANDALONE."""
        mock_ctx = MagicMock(spec=SeedContext)
        type(mock_ctx).onboarding_metadata = PropertyMock(side_effect=TypeError)
        type(mock_ctx).architectural_context = PropertyMock(side_effect=TypeError)
        type(mock_ctx).design_calibration = PropertyMock(side_effect=TypeError)
        result = detect_execution_mode(seed_context=mock_ctx)
        assert result == ExecutionMode.STANDALONE

    def test_one_field_attribute_error_mixed_with_valid(self):
        """If one field raises AttributeError but others are accessible, logic gracefully handles it."""
        mock_ctx = MagicMock(spec=SeedContext)
        type(mock_ctx).onboarding_metadata = PropertyMock(side_effect=AttributeError)
        type(mock_ctx).architectural_context = PropertyMock(return_value={"valid": "data"})
        type(mock_ctx).design_calibration = PropertyMock(return_value=None)
        result = detect_execution_mode(seed_context=mock_ctx)
        # One valid populated field should trigger pipeline, or AttributeError fallback occurs
        # The test verifies the function does not crash and returns a valid ExecutionMode
        assert result in (ExecutionMode.PIPELINE, ExecutionMode.STANDALONE)


# ============================================================================
# TestPropertyAccessors — Backward compatibility
# ============================================================================


class TestPropertyAccessors:
    """Verify backward compatibility: standalone is zero-change default."""

    def test_standalone_config_has_no_seed_context(self):
        """ModeConfig.standalone() sets seed_context to None."""
        config = ModeConfig.standalone()
        assert config.seed_context is None

    def test_standalone_is_default_mode(self):
        """Default standalone mode is ExecutionMode.STANDALONE."""
        config = ModeConfig.standalone()
        assert config.mode == ExecutionMode.STANDALONE

    def test_is_standalone_property_true_for_standalone(self):
        """is_standalone property returns True for standalone mode."""
        config = ModeConfig.standalone()
        assert config.is_standalone is True

    def test_is_pipeline_property_false_for_standalone(self):
        """is_pipeline property returns False for standalone mode."""
        config = ModeConfig.standalone()
        assert config.is_pipeline is False

    def test_is_pipeline_property_true_for_pipeline(self):
        """is_pipeline property returns True for pipeline mode."""
        seed = SeedContext(onboarding_metadata={"p": "v"})
        config = ModeConfig.pipeline(seed_context=seed)
        assert config.is_pipeline is True

    def test_is_standalone_property_false_for_pipeline(self):
        """is_standalone property returns False for pipeline mode."""
        seed = SeedContext(onboarding_metadata={"p": "v"})
        config = ModeConfig.pipeline(seed_context=seed)
        assert config.is_standalone is False

    def test_mode_accessor_returns_enum(self):
        """mode attribute is an ExecutionMode enum instance."""
        config = ModeConfig.standalone()
        assert isinstance(config.mode, ExecutionMode)
        assert config.mode == ExecutionMode.STANDALONE


# ============================================================================
# TestStatePersistence — State persistence round-trip
# ============================================================================


class TestStatePersistence:
    """Validate serialization/deserialization and error handling."""

    def test_standalone_config_round_trip(self):
        """Standalone ModeConfig serializes and deserializes correctly."""
        original = ModeConfig.standalone()
        serialized = original.to_dict()
        restored = ModeConfig.from_dict(serialized)
        assert restored.mode == original.mode
        assert restored.tags == original.tags
        assert restored.capabilities == original.capabilities
        assert restored.seed_context == original.seed_context

    def test_pipeline_config_round_trip(self):
        """Pipeline ModeConfig with seed serializes and deserializes correctly."""
        seed = SeedContext(
            onboarding_metadata={"project": "test"},
            architectural_context={"patterns": ["strategy"]},
            design_calibration={"depth": "standard"},
        )
        original = ModeConfig.pipeline(seed_context=seed)
        serialized = original.to_dict()
        restored = ModeConfig.from_dict(serialized)
        assert restored.mode == original.mode
        assert restored.seed_context.onboarding_metadata == seed.onboarding_metadata
        assert restored.seed_context.architectural_context == seed.architectural_context
        assert restored.seed_context.design_calibration == seed.design_calibration

    def test_empty_seed_context_round_trip(self):
        """Empty SeedContext serializes with null fields via to_dict()."""
        ctx = SeedContext()
        serialized = ctx.to_dict()
        assert serialized["onboarding_metadata"] is None
        assert serialized["architectural_context"] is None
        assert serialized["design_calibration"] is None
        restored = SeedContext.from_dict(serialized)
        assert restored.onboarding_metadata is None
        assert restored.architectural_context is None
        assert restored.design_calibration is None

    def test_json_serialization_round_trip(self):
        """ModeConfig serializes to JSON and deserializes correctly."""
        seed = SeedContext(onboarding_metadata={"key": "value"})
        config = ModeConfig.pipeline(seed_context=seed)
        json_str = json.dumps(config.to_dict())
        restored_dict = json.loads(json_str)
        restored = ModeConfig.from_dict(restored_dict)
        assert restored.mode == ExecutionMode.PIPELINE
        assert restored.seed_context.onboarding_metadata == {"key": "value"}

    def test_from_dict_missing_keys_raises(self):
        """from_dict with empty dict raises due to missing required keys."""
        with pytest.raises((KeyError, ValueError)):
            ModeConfig.from_dict({})

    def test_from_dict_invalid_mode_raises(self):
        """from_dict with invalid mode value raises ValueError."""
        with pytest.raises(ValueError):
            ModeConfig.from_dict({
                "mode": "invalid",
                "tags": [],
                "capabilities": [],
            })

    def test_from_dict_missing_mode_raises(self):
        """from_dict without 'mode' key raises KeyError or ValueError."""
        with pytest.raises((KeyError, ValueError)):
            ModeConfig.from_dict({
                "tags": ["standalone"],
                "capabilities": ["generation"],
            })

    def test_from_dict_missing_tags_raises(self):
        """from_dict without 'tags' key raises KeyError or ValueError."""
        with pytest.raises((KeyError, ValueError)):
            ModeConfig.from_dict({
                "mode": "standalone",
                "capabilities": ["generation"],
            })

    def test_from_dict_missing_capabilities_raises(self):
        """from_dict without 'capabilities' key raises KeyError or ValueError."""
        with pytest.raises((KeyError, ValueError)):
            ModeConfig.from_dict({
                "mode": "standalone",
                "tags": ["standalone"],
            })

    def test_tags_preserved_in_round_trip(self):
        """Tags list is preserved exactly during round-trip."""
        original = ModeConfig.standalone()
        serialized = original.to_dict()
        restored = ModeConfig.from_dict(serialized)
        assert restored.tags == STANDALONE_DEFAULT_TAGS
        # Exact equality check, not substring matching
        assert restored.tags == ["standalone"]

    def test_capabilities_preserved_in_round_trip(self):
        """Capabilities list is preserved exactly during round-trip."""
        original = ModeConfig.standalone()
        serialized = original.to_dict()
        restored = ModeConfig.from_dict(serialized)
        assert restored.capabilities == STANDALONE_DEFAULT_CAPABILITIES
        # Exact equality check, not substring matching
        assert restored.capabilities == ["generation"]

    def test_pipeline_tags_preserved_in_round_trip(self):
        """Pipeline mode tags are preserved exactly during round-trip."""
        original = ModeConfig.pipeline()
        serialized = original.to_dict()
        restored = ModeConfig.from_dict(serialized)
        assert restored.tags == PIPELINE_DEFAULT_TAGS
        assert restored.tags == ["pipeline", "context-aware"]

    def test_pipeline_capabilities_preserved_in_round_trip(self):
        """Pipeline mode capabilities are preserved exactly during round-trip."""
        original = ModeConfig.pipeline()
        serialized = original.to_dict()
        restored = ModeConfig.from_dict(serialized)
        assert restored.capabilities == PIPELINE_DEFAULT_CAPABILITIES
        assert restored.capabilities == ["generation", "validation", "context-exploitation"]

    def test_seed_context_none_preserved_in_round_trip(self):
        """None seed_context is preserved during round-trip."""
        original = ModeConfig.standalone()
        assert original.seed_context is None
        serialized = original.to_dict()
        restored = ModeConfig.from_dict(serialized)
        assert restored.seed_context is None

    def test_mode_enum_value_in_dict(self):
        """Serialized dict contains mode as string value, not enum."""
        config = ModeConfig.standalone()
        serialized = config.to_dict()
        # Mode should be serialized as string, not as enum object
        assert isinstance(serialized["mode"], str)
        assert serialized["mode"] == "standalone"

    def test_from_dict_with_string_mode_value(self):
        """from_dict correctly converts string mode to ExecutionMode enum."""
        data = {
            "mode": "standalone",
            "tags": STANDALONE_DEFAULT_TAGS,
            "capabilities": STANDALONE_DEFAULT_CAPABILITIES,
        }
        restored = ModeConfig.from_dict(data)
        assert restored.mode == ExecutionMode.STANDALONE
        assert isinstance(restored.mode, ExecutionMode)

    def test_complex_seed_context_round_trip(self):
        """Complex nested SeedContext serializes and deserializes correctly."""
        seed = SeedContext(
            onboarding_metadata={
                "team": "artisans",
                "version": "1.0.0",
                "features": ["gen", "val"],
            },
            architectural_context={
                "patterns": ["strategy", "factory"],
                "services": {"api": "v2", "db": "v3"},
            },
            design_calibration={
                "depth": "full",
                "strictness": "high",
                "thresholds": {"coverage": 0.95},
            },
        )
        config = ModeConfig.pipeline(seed_context=seed)
        serialized = config.to_dict()
        restored = ModeConfig.from_dict(serialized)
        
        assert restored.seed_context.onboarding_metadata == seed.onboarding_metadata
        assert restored.seed_context.architectural_context == seed.architectural_context
        assert restored.seed_context.design_calibration == seed.design_calibration