"""Shared complexity classification data models.

Provides the canonical ``ComplexityTier`` enum, ``TaskComplexitySignals``
dataclass, and ``ComplexityRoutingConfig`` used across Artisan, Prime
Contractor, and Micro Prime subsystems.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict


class ComplexityTier(str, Enum):
    """Unified 4-tier complexity classification.

    Maps to routing decisions across all subsystems:
        TRIVIAL  — template-only, no LLM call needed
        SIMPLE   — economy model (e.g. Haiku)
        MODERATE — standard model (e.g. Sonnet)  [default]
        COMPLEX  — premium model (e.g. Opus)
    """

    TRIVIAL = "trivial"
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"

    @classmethod
    def from_artisan_tier(cls, value: str) -> ComplexityTier:
        """Map Artisan 3-tier values to shared 4-tier enum.

        Mapping:
            tier_1 → SIMPLE
            tier_2 → MODERATE
            tier_3 → COMPLEX
        """
        mapping = {
            "tier_1": cls.SIMPLE,
            "tier_2": cls.MODERATE,
            "tier_3": cls.COMPLEX,
        }
        try:
            return mapping[value]
        except KeyError:
            raise ValueError(
                f"Unknown Artisan tier {value!r}; expected one of {list(mapping)}"
            ) from None


@dataclass(frozen=True)
class TaskComplexitySignals:
    """Per-task complexity signals for classification.

    All fields use primitive types with safe defaults that classify as
    MODERATE (the current default behavior) when no data is available.
    """

    blast_radius: int = 0
    caller_count: int = 0
    has_dynamic_dispatch: bool = False
    is_closure: bool = False
    estimated_loc: int = 0
    target_file_count: int = 1
    edit_mode: str = "unknown"
    mro_depth: int = 0
    unresolved_call_count: int = 0
    has_cross_file_edges: bool = False
    manifest_coverage: str = "none"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for JSON storage and forensic logging."""
        return asdict(self)


@dataclass
class ComplexityRoutingConfig:
    """Threshold configuration for complexity classification.

    Field names are subsystem-neutral.  Use ``from_handler_config`` to
    populate from an Artisan ``HandlerConfig`` instance without importing it.
    """

    enabled: bool = True
    blast_radius_complex_threshold: int = 5
    loc_simple_max: int = 150
    loc_complex_min: int = 500
    caller_count_complex_threshold: int = 3
    mro_depth_complex_threshold: int = 3
    unresolved_calls_complex_threshold: int = 2
    templates_enabled: bool = True

    @classmethod
    def from_handler_config(cls, config: Any) -> ComplexityRoutingConfig:
        """Build from an Artisan HandlerConfig via duck-typed attribute access.

        Avoids importing ``HandlerConfig`` — uses ``getattr`` with defaults
        matching the HandlerConfig field defaults.
        """
        return cls(
            enabled=getattr(config, "complexity_routing_enabled", True),
            blast_radius_complex_threshold=getattr(
                config, "complexity_blast_radius_tier3", 5
            ),
            loc_simple_max=getattr(config, "complexity_loc_tier1_max", 150),
            loc_complex_min=getattr(config, "complexity_loc_tier3_min", 500),
            caller_count_complex_threshold=getattr(
                config, "complexity_caller_tier3", 3
            ),
            # These were hardcoded in Artisan — now configurable
            mro_depth_complex_threshold=3,
            unresolved_calls_complex_threshold=2,
            templates_enabled=True,
        )
