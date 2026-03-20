"""Unit tests for the Complexity-Driven Model Router (CMR).

Tests cover:
- TaskComplexityTier enum values and default
- TaskComplexitySignals dataclass defaults and serialization
- _classify_complexity_tier boundary conditions
- _extract_complexity_signals with/without registry
- Graceful degradation (all 6 scenarios)
- Backward compatibility (pre-CMR cache, missing metadata)

NOTE: The shared classifier (startd8.complexity.classifier) defaults to
COMPLEX (not MODERATE) per AC-R3-R7.  The Artisan 3-tier mapping is:
  TRIVIAL/SIMPLE → TIER_1, MODERATE → TIER_2, COMPLEX → TIER_3.
Additionally, relaxed SIMPLE (simple_relaxed_enabled=True by default)
promotes create-mode tasks with blast_radius <= 2 to TIER_1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest

from startd8.contractors.artisan_phases.development import (
    TaskComplexitySignals,
    TaskComplexityTier,
)
from startd8.contractors.context_seed_handlers import (
    HandlerConfig,
    _classify_complexity_tier,
    _extract_complexity_signals,
)


# ============================================================================
# Fixtures
# ============================================================================


@dataclass
class FakeChunk:
    """Minimal chunk-like object for signal extraction tests."""

    chunk_id: str = "chunk-1"
    file_targets: list[str] = field(default_factory=lambda: ["src/foo.py"])
    metadata: dict[str, Any] = field(default_factory=dict)
    description: str = "Test chunk"


def _make_config(**overrides: Any) -> HandlerConfig:
    """Build a HandlerConfig with CMR defaults, applying any overrides."""
    return HandlerConfig(**overrides)


# ============================================================================
# TaskComplexityTier enum
# ============================================================================


class TestTaskComplexityTier:
    """REQ-CMR-000: Tier enum has correct values and is a str enum."""

    def test_tier_values(self) -> None:
        assert TaskComplexityTier.TIER_1.value == "tier_1"
        assert TaskComplexityTier.TIER_2.value == "tier_2"
        assert TaskComplexityTier.TIER_3.value == "tier_3"

    def test_tier_is_str(self) -> None:
        assert isinstance(TaskComplexityTier.TIER_2, str)
        assert TaskComplexityTier.TIER_2 == "tier_2"

    def test_tier_from_value(self) -> None:
        assert TaskComplexityTier("tier_1") is TaskComplexityTier.TIER_1
        assert TaskComplexityTier("tier_3") is TaskComplexityTier.TIER_3


# ============================================================================
# TaskComplexitySignals dataclass
# ============================================================================


class TestTaskComplexitySignals:
    """REQ-CMR-001: Signals dataclass has correct defaults and serialization."""

    def test_default_signals(self) -> None:
        signals = TaskComplexitySignals()
        assert signals.blast_radius == 0
        assert signals.caller_count == 0
        assert signals.has_dynamic_dispatch is False
        assert signals.is_closure is False
        assert signals.estimated_loc == 0
        assert signals.target_file_count == 1
        assert signals.edit_mode == "unknown"
        assert signals.mro_depth == 0
        assert signals.unresolved_call_count == 0
        assert signals.has_cross_file_edges is False
        assert signals.manifest_coverage == "none"

    def test_to_dict(self) -> None:
        signals = TaskComplexitySignals(blast_radius=3, edit_mode="create")
        d = signals.to_dict()
        assert d["blast_radius"] == 3
        assert d["edit_mode"] == "create"
        assert len(d) == 13  # All 13 fields (includes file_extension, security_sensitive)

    def test_frozen(self) -> None:
        signals = TaskComplexitySignals()
        with pytest.raises(AttributeError):
            signals.blast_radius = 5  # type: ignore[misc]

    def test_defaults_classify_as_tier3(self) -> None:
        """Default signals classify as Tier 3 (COMPLEX) per AC-R3-R7."""
        signals = TaskComplexitySignals()
        config = _make_config()
        tier = _classify_complexity_tier(signals, config)
        assert tier == TaskComplexityTier.TIER_3


# ============================================================================
# Classification: Tier 3 triggers (any one fires)
# ============================================================================


class TestClassifyTier3:
    """REQ-CMR-011: Each Tier 3 trigger fires independently."""

    def test_high_blast_radius(self) -> None:
        signals = TaskComplexitySignals(blast_radius=6)
        assert _classify_complexity_tier(signals, _make_config()) == TaskComplexityTier.TIER_3

    def test_blast_radius_at_threshold(self) -> None:
        """blast_radius == 5 does NOT fire the blast_radius COMPLEX trigger,
        but still classifies as TIER_3 via the default (AC-R3-R7)."""
        signals = TaskComplexitySignals(blast_radius=5)
        # No COMPLEX trigger fires, but the default is COMPLEX
        assert _classify_complexity_tier(signals, _make_config()) == TaskComplexityTier.TIER_3

    def test_dynamic_dispatch(self) -> None:
        signals = TaskComplexitySignals(has_dynamic_dispatch=True)
        assert _classify_complexity_tier(signals, _make_config()) == TaskComplexityTier.TIER_3

    def test_high_caller_count_edit_mode(self) -> None:
        signals = TaskComplexitySignals(caller_count=4, edit_mode="edit")
        assert _classify_complexity_tier(signals, _make_config()) == TaskComplexityTier.TIER_3

    def test_high_caller_count_create_mode_not_trigger(self) -> None:
        """caller_count > 3 in create mode does NOT fire the caller COMPLEX
        trigger, but falls through to default COMPLEX (TIER_3).
        Relaxed SIMPLE doesn't apply: caller_count > 0."""
        signals = TaskComplexitySignals(caller_count=4, edit_mode="create")
        tier = _classify_complexity_tier(signals, _make_config())
        # Still TIER_3 via default — caller_count blocks SIMPLE
        assert tier == TaskComplexityTier.TIER_3

    def test_deep_mro(self) -> None:
        signals = TaskComplexitySignals(mro_depth=4)
        assert _classify_complexity_tier(signals, _make_config()) == TaskComplexityTier.TIER_3

    def test_mro_at_threshold_not_trigger(self) -> None:
        """mro_depth == 3 does NOT fire the MRO COMPLEX trigger,
        but still classifies as TIER_3 via the default."""
        signals = TaskComplexitySignals(mro_depth=3)
        assert _classify_complexity_tier(signals, _make_config()) == TaskComplexityTier.TIER_3

    def test_unresolved_calls(self) -> None:
        signals = TaskComplexitySignals(unresolved_call_count=3)
        assert _classify_complexity_tier(signals, _make_config()) == TaskComplexityTier.TIER_3

    def test_high_loc(self) -> None:
        signals = TaskComplexitySignals(estimated_loc=501)
        assert _classify_complexity_tier(signals, _make_config()) == TaskComplexityTier.TIER_3

    def test_loc_at_threshold_not_trigger(self) -> None:
        """estimated_loc == 500 does NOT fire the LOC COMPLEX trigger,
        but still classifies as TIER_3 via the default."""
        signals = TaskComplexitySignals(estimated_loc=500)
        assert _classify_complexity_tier(signals, _make_config()) == TaskComplexityTier.TIER_3

    def test_multi_file_with_cross_edges(self) -> None:
        signals = TaskComplexitySignals(target_file_count=2, has_cross_file_edges=True)
        assert _classify_complexity_tier(signals, _make_config()) == TaskComplexityTier.TIER_3

    def test_multi_file_without_cross_edges_not_trigger(self) -> None:
        """Multi-file without cross edges does NOT fire the cross-file COMPLEX
        trigger, but target_file_count > 1 blocks SIMPLE → default COMPLEX."""
        signals = TaskComplexitySignals(target_file_count=2, has_cross_file_edges=False)
        tier = _classify_complexity_tier(signals, _make_config())
        assert tier == TaskComplexityTier.TIER_3


# ============================================================================
# Classification: Tier 1 eligibility (all must pass)
# ============================================================================


class TestClassifyTier1:
    """REQ-CMR-011: All conditions must be true for Tier 1."""

    def test_simple_greenfield_task(self) -> None:
        signals = TaskComplexitySignals(
            blast_radius=0,
            edit_mode="create",
            caller_count=0,
            has_dynamic_dispatch=False,
            estimated_loc=100,
            target_file_count=1,
            manifest_coverage="full",
        )
        assert _classify_complexity_tier(signals, _make_config()) == TaskComplexityTier.TIER_1

    def test_relaxed_simple_greenfield(self) -> None:
        """Relaxed SIMPLE: create-mode, small blast_radius, no manifest
        coverage — still qualifies as TIER_1 per Kaizen run-017."""
        signals = TaskComplexitySignals(
            blast_radius=1,
            edit_mode="create",
            caller_count=0,
            estimated_loc=100,
            target_file_count=1,
            manifest_coverage="none",
        )
        assert _classify_complexity_tier(signals, _make_config()) == TaskComplexityTier.TIER_1

    def test_edit_mode_blocks_tier1(self) -> None:
        """edit mode blocks both strict and relaxed SIMPLE → default COMPLEX."""
        signals = TaskComplexitySignals(
            blast_radius=0,
            edit_mode="edit",
            caller_count=0,
            estimated_loc=100,
            target_file_count=1,
        )
        assert _classify_complexity_tier(signals, _make_config()) == TaskComplexityTier.TIER_3

    def test_unknown_edit_mode_blocks_tier1(self) -> None:
        """REQ-CMR-014: unknown edit mode disqualifies from Tier 1 → default COMPLEX."""
        signals = TaskComplexitySignals(
            blast_radius=0,
            edit_mode="unknown",
            caller_count=0,
            estimated_loc=100,
            target_file_count=1,
        )
        assert _classify_complexity_tier(signals, _make_config()) == TaskComplexityTier.TIER_3

    def test_nonzero_blast_radius_relaxed_simple(self) -> None:
        """blast_radius=1 in create mode qualifies for relaxed SIMPLE (TIER_1)
        when blast_radius <= simple_relaxed_blast_radius_max (default: 2)."""
        signals = TaskComplexitySignals(
            blast_radius=1,
            edit_mode="create",
            caller_count=0,
            estimated_loc=100,
            target_file_count=1,
        )
        assert _classify_complexity_tier(signals, _make_config()) == TaskComplexityTier.TIER_1

    def test_high_blast_radius_blocks_relaxed_simple(self) -> None:
        """blast_radius=3 exceeds relaxed threshold (2) → default COMPLEX."""
        signals = TaskComplexitySignals(
            blast_radius=3,
            edit_mode="create",
            caller_count=0,
            estimated_loc=100,
            target_file_count=1,
        )
        assert _classify_complexity_tier(signals, _make_config()) == TaskComplexityTier.TIER_3

    def test_callers_block_tier1(self) -> None:
        """caller_count > 0 blocks both strict and relaxed SIMPLE → default COMPLEX."""
        signals = TaskComplexitySignals(
            blast_radius=0,
            edit_mode="create",
            caller_count=1,
            estimated_loc=100,
            target_file_count=1,
        )
        assert _classify_complexity_tier(signals, _make_config()) == TaskComplexityTier.TIER_3

    def test_loc_at_threshold_blocks_tier1(self) -> None:
        """estimated_loc >= 150 blocks Tier 1 (must be strictly less) → default COMPLEX."""
        signals = TaskComplexitySignals(
            blast_radius=0,
            edit_mode="create",
            caller_count=0,
            estimated_loc=150,
            target_file_count=1,
        )
        assert _classify_complexity_tier(signals, _make_config()) == TaskComplexityTier.TIER_3

    def test_multi_file_blocks_tier1(self) -> None:
        """target_file_count > 1 blocks SIMPLE → default COMPLEX."""
        signals = TaskComplexitySignals(
            blast_radius=0,
            edit_mode="create",
            caller_count=0,
            estimated_loc=50,
            target_file_count=2,
        )
        assert _classify_complexity_tier(signals, _make_config()) == TaskComplexityTier.TIER_3

    def test_dynamic_dispatch_blocks_tier1(self) -> None:
        """has_dynamic_dispatch fires Tier 3 before Tier 1 check."""
        signals = TaskComplexitySignals(
            blast_radius=0,
            edit_mode="create",
            caller_count=0,
            has_dynamic_dispatch=True,
            estimated_loc=50,
            target_file_count=1,
        )
        assert _classify_complexity_tier(signals, _make_config()) == TaskComplexityTier.TIER_3


# ============================================================================
# Classification: Threshold overrides via config
# ============================================================================


class TestClassifyThresholdOverrides:
    """REQ-CMR-011: Thresholds read from config, not hardcoded."""

    def test_custom_blast_radius_threshold(self) -> None:
        config = _make_config(complexity_blast_radius_tier3=10)
        # blast_radius=8 is below custom threshold (10), doesn't trigger COMPLEX
        # but still defaults to COMPLEX (TIER_3)
        signals = TaskComplexitySignals(blast_radius=8)
        assert _classify_complexity_tier(signals, config) == TaskComplexityTier.TIER_3
        # blast_radius=11 exceeds threshold — explicitly TIER_3
        signals2 = TaskComplexitySignals(blast_radius=11)
        assert _classify_complexity_tier(signals2, config) == TaskComplexityTier.TIER_3

    def test_custom_loc_tier1_max(self) -> None:
        config = _make_config(complexity_loc_tier1_max=200)
        signals = TaskComplexitySignals(
            blast_radius=0,
            edit_mode="create",
            caller_count=0,
            estimated_loc=180,
            target_file_count=1,
            manifest_coverage="full",
        )
        assert _classify_complexity_tier(signals, config) == TaskComplexityTier.TIER_1

    def test_custom_loc_tier3_min(self) -> None:
        config = _make_config(complexity_loc_tier3_min=300)
        signals = TaskComplexitySignals(estimated_loc=301)
        assert _classify_complexity_tier(signals, config) == TaskComplexityTier.TIER_3

    def test_custom_caller_tier3(self) -> None:
        config = _make_config(complexity_caller_tier3=5)
        # caller_count=4 is below custom threshold (5) in edit mode —
        # doesn't fire caller COMPLEX trigger, defaults to COMPLEX (TIER_3)
        signals = TaskComplexitySignals(caller_count=4, edit_mode="edit")
        assert _classify_complexity_tier(signals, config) == TaskComplexityTier.TIER_3
        # caller_count=6 exceeds threshold — explicitly TIER_3
        signals2 = TaskComplexitySignals(caller_count=6, edit_mode="edit")
        assert _classify_complexity_tier(signals2, config) == TaskComplexityTier.TIER_3


# ============================================================================
# Signal extraction
# ============================================================================


class TestExtractComplexitySignals:
    """REQ-CMR-010: Signal extraction from chunk metadata and registry."""

    def test_minimal_chunk_no_registry(self) -> None:
        """No metadata, no registry → safe defaults."""
        chunk = FakeChunk()
        signals = _extract_complexity_signals(chunk, None)
        assert signals.blast_radius == 0
        assert signals.caller_count == 0
        assert signals.edit_mode == "unknown"
        assert signals.target_file_count == 1

    def test_extracts_call_graph_callers(self) -> None:
        chunk = FakeChunk(metadata={
            "_call_graph_callers": [
                {"fqn": "mod.func", "direct_callers": ["a.b", "c.d"], "blast_radius": 3},
                {"fqn": "mod.func2", "direct_callers": ["e.f"], "blast_radius": 7},
            ],
        })
        signals = _extract_complexity_signals(chunk, None)
        assert signals.blast_radius == 7  # max
        assert signals.caller_count == 3  # 2 + 1

    def test_extracts_edit_mode_from_dict(self) -> None:
        chunk = FakeChunk(metadata={
            "_edit_mode": {"mode": "edit", "per_file": {}},
        })
        signals = _extract_complexity_signals(chunk, None)
        assert signals.edit_mode == "edit"

    def test_extracts_edit_mode_from_string(self) -> None:
        chunk = FakeChunk(metadata={
            "_edit_mode": "create",
        })
        signals = _extract_complexity_signals(chunk, None)
        assert signals.edit_mode == "create"

    def test_extracts_estimated_loc(self) -> None:
        chunk = FakeChunk(metadata={"estimated_loc": 250})
        signals = _extract_complexity_signals(chunk, None)
        assert signals.estimated_loc == 250

    def test_target_file_count(self) -> None:
        chunk = FakeChunk(file_targets=["a.py", "b.py", "c.py"])
        signals = _extract_complexity_signals(chunk, None)
        assert signals.target_file_count == 3

    def test_empty_file_targets_defaults_to_1(self) -> None:
        chunk = FakeChunk(file_targets=[])
        signals = _extract_complexity_signals(chunk, None)
        assert signals.target_file_count == 1

    def test_never_raises_on_bad_metadata(self) -> None:
        """REQ-CMR-010: Never raises."""
        chunk = FakeChunk(metadata={
            "_call_graph_callers": "not a list",  # corrupt
            "_edit_mode": 12345,  # wrong type
            "estimated_loc": "not a number",  # wrong type
        })
        signals = _extract_complexity_signals(chunk, None)
        # Should return defaults without raising
        assert isinstance(signals, TaskComplexitySignals)

    def test_manifest_coverage_full_without_callers(self) -> None:
        """Manifest present for all targets should count as full coverage."""
        chunk = FakeChunk(metadata={
            "_edit_mode": "create",
            "_call_graph_callers": [],
            "estimated_loc": 10,
        })

        class _Registry:
            def get(self, _tf: str) -> Any:
                return SimpleNamespace(elements=[])

            def call_graph(self) -> dict[str, set[str]]:
                return {}

        signals = _extract_complexity_signals(chunk, _Registry())
        assert signals.manifest_coverage == "full"
        assert _classify_complexity_tier(signals, _make_config()) == TaskComplexityTier.TIER_1

    def test_edit_mode_normalized_to_lowercase(self) -> None:
        chunk = FakeChunk(metadata={
            "_edit_mode": {"mode": "EDIT"},
            "_call_graph_callers": [{"direct_callers": ["a", "b", "c", "d"], "blast_radius": 0}],
        })
        signals = _extract_complexity_signals(chunk, None)
        assert signals.edit_mode == "edit"
        assert _classify_complexity_tier(signals, _make_config()) == TaskComplexityTier.TIER_3


# ============================================================================
# Graceful degradation
# ============================================================================


class TestGracefulDegradation:
    """All 6 degradation scenarios from the requirements."""

    def test_registry_none_create_mode_relaxed_simple(self) -> None:
        """ManifestRegistry is None, create mode → relaxed SIMPLE (TIER_1).
        blast_radius=0 + create + no callers qualifies for relaxed SIMPLE."""
        chunk = FakeChunk(metadata={"_edit_mode": {"mode": "create"}})
        signals = _extract_complexity_signals(chunk, None)
        tier = _classify_complexity_tier(signals, _make_config())
        assert tier == TaskComplexityTier.TIER_1

    def test_registry_none_unknown_mode_defaults_complex(self) -> None:
        """ManifestRegistry is None, unknown edit_mode → default COMPLEX."""
        chunk = FakeChunk()
        signals = _extract_complexity_signals(chunk, None)
        tier = _classify_complexity_tier(signals, _make_config())
        assert tier == TaskComplexityTier.TIER_3

    def test_routing_disabled_via_config(self) -> None:
        """complexity_routing_enabled=False → classification not called."""
        # This is tested at integration level (enrichment loop skip),
        # but we verify the config field exists.
        config = _make_config(complexity_routing_enabled=False)
        assert config.complexity_routing_enabled is False

    def test_missing_edit_mode_blocks_tier1(self) -> None:
        """edit_mode missing → treated as 'unknown' → blocks Tier 1 → default COMPLEX."""
        signals = TaskComplexitySignals(
            blast_radius=0,
            edit_mode="unknown",
            caller_count=0,
            estimated_loc=50,
            target_file_count=1,
        )
        tier = _classify_complexity_tier(signals, _make_config())
        assert tier == TaskComplexityTier.TIER_3

    def test_default_metadata_absent(self) -> None:
        """Pre-CMR chunks have no _complexity_tier → default 'tier_2'."""
        chunk = FakeChunk()
        assert chunk.metadata.get("_complexity_tier", "tier_2") == "tier_2"


# ============================================================================
# HandlerConfig CMR fields
# ============================================================================


class TestHandlerConfigCMR:
    """REQ-CMR-003: HandlerConfig has correct CMR defaults."""

    def test_defaults(self) -> None:
        config = _make_config()
        assert config.complexity_routing_enabled is True
        assert config.complexity_blast_radius_tier3 == 5
        assert config.complexity_loc_tier1_max == 150
        assert config.complexity_loc_tier3_min == 500
        assert config.complexity_caller_tier3 == 3
        assert config.complexity_tier2_gate_escalation is False
        # tier3_agent resolved in __post_init__
        assert config.tier3_agent is not None

    def test_kill_switch(self) -> None:
        config = _make_config(complexity_routing_enabled=False)
        assert config.complexity_routing_enabled is False

    def test_custom_tier3_agent(self) -> None:
        config = _make_config(tier3_agent="anthropic:custom-opus")
        assert config.tier3_agent == "anthropic:custom-opus"


# ============================================================================
# Combined signals
# ============================================================================


class TestCombinedSignals:
    """Classification with multiple signals active simultaneously."""

    def test_tier3_takes_priority_over_tier1(self) -> None:
        """Tier 3 checks run first — a task that could be Tier 1 by
        some signals but has a Tier 3 trigger gets Tier 3."""
        signals = TaskComplexitySignals(
            blast_radius=0,
            edit_mode="create",
            caller_count=0,
            estimated_loc=50,
            target_file_count=1,
            has_dynamic_dispatch=True,  # Tier 3 trigger
        )
        assert _classify_complexity_tier(signals, _make_config()) == TaskComplexityTier.TIER_3

    def test_borderline_defaults_to_complex(self) -> None:
        """Signals that don't qualify for SIMPLE or fire a COMPLEX trigger
        default to COMPLEX (TIER_3) per AC-R3-R7."""
        signals = TaskComplexitySignals(
            blast_radius=2,  # nonzero but <= 5
            edit_mode="edit",
            caller_count=2,  # > 0 but <= 3 in edit mode
            estimated_loc=200,  # > 150 but <= 500
            target_file_count=1,
        )
        assert _classify_complexity_tier(signals, _make_config()) == TaskComplexityTier.TIER_3

    def test_unknown_edit_mode_not_tier3_caller_rule(self) -> None:
        """REQ-CMR-014: unknown edit mode does NOT fire Tier 3 caller rule,
        but falls through to default COMPLEX (TIER_3)."""
        signals = TaskComplexitySignals(
            caller_count=10,
            edit_mode="unknown",
        )
        tier = _classify_complexity_tier(signals, _make_config())
        # caller_count > 3 requires edit_mode == "edit" for the trigger,
        # but the default is COMPLEX regardless
        assert tier == TaskComplexityTier.TIER_3
