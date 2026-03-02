"""Micro Prime data models, enums, and configuration.

Defines the Pydantic models and dataclasses used throughout the Micro Prime
local-first code generation engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class TierClassification(str, Enum):
    """Element complexity tier for routing decisions."""

    TRIVIAL = "trivial"
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


class EscalationReason(str, Enum):
    """Why an element was escalated from local to cloud."""

    AST_FAILURE = "ast_failure"
    STRUCTURAL_MISMATCH = "structural_mismatch"
    TIER_TOO_HIGH = "tier_too_high"
    REPAIR_EXHAUSTED = "repair_exhausted"
    EMPTY_RESPONSE = "empty_response"
    TIMEOUT = "timeout"
    CIRCUIT_BREAKER = "circuit_breaker"


class RepairAttribution(BaseModel):
    """Per-step repair attribution (REQ-MP-601).

    Granular boolean/int fields tracking what each repair step actually did
    during a pipeline run. Populated by ``build_repair_attribution()`` in
    the repair module from the list of ``RepairStepResult`` objects.
    """

    fence_stripped: bool = False
    trimmed: bool = False
    nodes_removed: int = 0
    bare_wrapped: bool = False
    indent_source: str = ""
    params_changed: int = 0
    return_type_restored: bool = False


@dataclass
class RepairStepResult:
    """Result from a single repair pipeline step.

    Provides per-step attribution for observability (REQ-MP-601).
    """

    step_name: str
    modified: bool
    code: str
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class EscalationResult:
    """Captures why an element was escalated to cloud processing."""

    reason: EscalationReason
    detail: str
    last_code: Optional[str] = None
    last_error: Optional[str] = None


@dataclass
class ElementResult:
    """Result from processing a single element through the engine."""

    element_name: str
    file_path: str
    tier: TierClassification
    success: bool
    classification_reason: str = ""
    code: Optional[str] = None
    escalation: Optional[EscalationResult] = None
    template_used: bool = False
    repair_steps_applied: list[str] = field(default_factory=list)
    repair_attribution: Optional[RepairAttribution] = None
    generation_time_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class FileResult:
    """Result from processing all elements in a file."""

    file_path: str
    element_results: list[ElementResult] = field(default_factory=list)
    filled_skeleton: Optional[str] = None

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.element_results if r.success)

    @property
    def escalated_count(self) -> int:
        return sum(1 for r in self.element_results if r.escalation is not None)

    @property
    def total_count(self) -> int:
        return len(self.element_results)


@dataclass
class SeedResult:
    """Result from processing all elements across all files in a seed."""

    file_results: list[FileResult] = field(default_factory=list)
    total_generation_time_ms: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    @property
    def success_count(self) -> int:
        return sum(fr.success_count for fr in self.file_results)

    @property
    def escalated_count(self) -> int:
        return sum(fr.escalated_count for fr in self.file_results)

    @property
    def total_count(self) -> int:
        return sum(fr.total_count for fr in self.file_results)


class MicroPrimeConfig(BaseModel):
    """Configuration for the Micro Prime engine."""

    model: str = "startd8-coder"
    provider: str = "ollama"
    temperature: float = 0.1
    max_tokens: int = 512
    input_token_budget: int = 1024
    templates_enabled: bool = True
    repair_enabled: bool = True
    few_shot_enabled: bool = True
    max_few_shot_examples: int = 2
    escalation_enabled: bool = True
    # Classifier thresholds
    max_simple_imports: int = 8
    max_simple_params: int = 4


class MicroPrimeElementMetrics(BaseModel):
    """Per-element metrics for observability (REQ-MP-600)."""

    element_name: str
    file_path: str
    tier: TierClassification
    success: bool
    classification_reason: str = ""
    template_used: bool = False
    repair_steps: list[str] = Field(default_factory=list)
    repair_attribution: Optional[RepairAttribution] = None
    generation_time_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    escalation_reason: Optional[str] = None


class MicroPrimeCostReport(BaseModel):
    """Cost accounting for a Micro Prime run (REQ-MP-602)."""

    total_elements: int = 0
    trivial_count: int = 0
    simple_count: int = 0
    moderate_count: int = 0
    complex_count: int = 0
    local_success_count: int = 0
    escalated_count: int = 0
    template_count: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    estimated_local_cost_usd: float = 0.0
    estimated_cloud_savings_usd: float = 0.0
    success_rate: float = 0.0
