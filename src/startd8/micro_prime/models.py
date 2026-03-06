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
    SEMANTIC_FAILURE = "semantic_failure"
    OLLAMA_UNAVAILABLE = "ollama_unavailable"
    TIER_TOO_HIGH = "tier_too_high"
    REPAIR_EXHAUSTED = "repair_exhausted"
    EMPTY_RESPONSE = "empty_response"
    TIMEOUT = "timeout"
    CIRCUIT_BREAKER = "circuit_breaker"
    DECOMPOSITION_FAILED = "decomposition_failed"
    NOT_DECOMPOSABLE = "not_decomposable"


# Re-export from shared repair package for backward compatibility.
from startd8.repair.models import RepairAttribution, RepairStepResult  # noqa: F401


@dataclass
class EscalationContext:
    """Detailed context for cloud escalation (REQ-MP-502)."""

    element_fqn: str = ""
    local_model: str = ""
    raw_output: str = ""
    repair_steps_applied: list[str] = field(default_factory=list)
    repaired_code: Optional[str] = None
    error: str = ""


@dataclass
class EscalationResult:
    """Captures why an element was escalated to cloud processing."""

    reason: EscalationReason
    detail: str
    last_code: Optional[str] = None
    last_error: Optional[str] = None
    context: Optional[EscalationContext] = None


@dataclass
class ElementResult:
    """Result from processing a single element through the engine."""

    element_name: str
    file_path: str
    tier: TierClassification
    success: bool
    classification_reason: str = ""
    parent_class: Optional[str] = None
    element_kind: Optional[str] = None
    api_file_import_bump: int = 0
    api_element_adjustment: int = 0
    code: Optional[str] = None
    escalation: Optional[EscalationResult] = None
    template_used: bool = False
    template_name: Optional[str] = None
    repair_steps_applied: list[str] = field(default_factory=list)
    repair_attribution: Optional[RepairAttribution] = None
    repair_recovered: bool = False
    ast_valid_before_repair: Optional[bool] = None
    ast_valid_after_repair: Optional[bool] = None
    verification_verdict: Optional[str] = None
    model: Optional[str] = None
    cloud_retry_attempts: int = 0
    cloud_retry_success: bool = False
    cloud_retry_strategy: Optional[str] = None
    cloud_retry_last_error: Optional[str] = None
    generation_time_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    decomposition_metadata: Optional[dict] = None


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
    max_tokens: int = 2048
    input_token_budget: int = 1024
    templates_enabled: bool = True
    repair_enabled: bool = True
    few_shot_enabled: bool = True
    max_few_shot_examples: int = 2
    escalation_enabled: bool = True
    external_api_packages: list[str] = [
        # Network / RPC
        "grpc", "grpcio", "httpx", "aiohttp", "requests",
        # Web frameworks
        "flask", "fastapi", "django", "starlette",
        # Template engines
        "jinja2", "mako",
        # Cloud SDKs
        "google.cloud", "google.auth", "google.api_core",
        "boto3", "botocore",
        "azure",
        # Database / ORM
        "sqlalchemy", "alembic", "asyncpg", "psycopg2",
        # Task queues / caching
        "celery", "redis", "kombu",
        # Testing / load
        "locust", "playwright",
    ]
    cloud_escalation_max_attempts: int = 1
    cloud_escalation_retry_strategy: str = "same_prompt"
    cloud_escalation_retry_max_chars: int = 512
    dry_run: bool = False
    # Classifier thresholds
    max_simple_imports: int = 8
    max_simple_params: int = 4
    # Scoring tuning knobs
    class_score_bonus: int = 1
    simple_threshold: int = 0
    docstring_length_threshold: int = 200
    # Decomposer settings (REQ-MP-908)
    decomposition_enabled: bool = True
    max_sub_elements: int = 5
    max_helpers_per_function: int = 4
    decomposition_confidence_threshold: float = 0.6
    class_decompose_enabled: bool = True
    function_chain_enabled: bool = True
    # Post-generation success criteria (REQ-MP-504)
    min_element_fill_rate: float = 0.5


class MicroPrimeElementMetrics(BaseModel):
    """Per-element metrics for observability (REQ-MP-600)."""

    element_name: str
    element_fqn: str = ""
    element_kind: str = ""
    api_file_import_bump: int = 0
    api_element_adjustment: int = 0
    file_path: str
    tier: TierClassification
    success: bool
    classification_reason: str = ""
    template_used: bool = False
    template_name: Optional[str] = None
    repair_steps: list[str] = Field(default_factory=list)
    repair_attribution: Optional[RepairAttribution] = None
    repair_recovered: bool = False
    ast_valid_before_repair: Optional[bool] = None
    ast_valid_after_repair: Optional[bool] = None
    verification_verdict: Optional[str] = None
    escalated: bool = False
    generation_time_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    generation_tokens: int = 0
    model: Optional[str] = None
    escalation_reason: Optional[str] = None


class MicroPrimeCostReport(BaseModel):
    """Cost accounting for a Micro Prime run (REQ-MP-602)."""

    total_elements: int = 0
    trivial_count: int = 0
    simple_count: int = 0
    simple_escalated_count: int = 0
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
    baseline_all_cloud_usd: float = 0.0
    actual_cloud_usd: float = 0.0
    savings_usd: float = 0.0
    savings_pct: float = 0.0
    local_inference_time_total_s: float = 0.0
    local_tokens_total: int = 0
    decomposed_count: int = 0
    decomposition_failure_count: int = 0
