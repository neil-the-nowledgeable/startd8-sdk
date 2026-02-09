"""
Data models for the PlanIngestionWorkflow.

Defines enums, intermediate results, and output structures for the
plan ingestion pipeline: parse → assess → transform → refine → emit.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


__all__ = [
    "ContractorRoute",
    "IngestionPhase",
    "ParsedFeature",
    "ParsedPlan",
    "ComplexityScore",
    "IngestionState",
    "PlanIngestionResult",
]


class ContractorRoute(str, Enum):
    """Target contractor format for the transformed plan."""
    PRIME = "prime"
    ARTISAN = "artisan"


class IngestionPhase(str, Enum):
    """Phases of the plan ingestion pipeline."""
    PARSE = "parse"
    ASSESS = "assess"
    TRANSFORM = "transform"
    REFINE = "refine"
    EMIT = "emit"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ParsedFeature:
    """A single feature extracted from the plan."""
    feature_id: str
    name: str
    description: str = ""
    target_files: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    estimated_loc: int = 0
    labels: List[str] = field(default_factory=list)


@dataclass
class ParsedPlan:
    """Structured representation of a parsed plan document."""
    title: str
    goals: List[str] = field(default_factory=list)
    features: List[ParsedFeature] = field(default_factory=list)
    dependency_graph: Dict[str, List[str]] = field(default_factory=dict)
    mentioned_files: List[str] = field(default_factory=list)
    raw_text: str = ""

    # LLM metrics from parsing
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0


@dataclass
class ComplexityScore:
    """Complexity assessment with dimensional breakdown."""
    # Dimensional scores (0-100 each)
    feature_count: int = 0
    cross_file_deps: int = 0
    api_surface: int = 0
    test_complexity: int = 0
    integration_depth: int = 0
    domain_novelty: int = 0
    ambiguity: int = 0

    # Composite
    composite: int = 0
    reasoning: str = ""
    route: Optional[ContractorRoute] = None

    # LLM metrics
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0


@dataclass
class IngestionState:
    """Mutable workflow state for debugging and checkpointing."""
    current_phase: IngestionPhase = IngestionPhase.PARSE
    parsed_plan: Optional[ParsedPlan] = None
    complexity: Optional[ComplexityScore] = None
    route: Optional[ContractorRoute] = None
    plan_document_path: Optional[str] = None
    review_config_path: Optional[str] = None
    total_cost: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "current_phase": self.current_phase.value,
            "route": self.route.value if self.route else None,
            "plan_document_path": self.plan_document_path,
            "review_config_path": self.review_config_path,
            "total_cost": self.total_cost,
            "error": self.error,
        }
        if self.parsed_plan:
            d["parsed_plan_title"] = self.parsed_plan.title
            d["parsed_plan_feature_count"] = len(self.parsed_plan.features)
        if self.complexity:
            d["complexity_composite"] = self.complexity.composite
            d["complexity_route"] = self.complexity.route.value if self.complexity.route else None
        return d


@dataclass
class PlanIngestionResult:
    """Final output of the plan ingestion workflow."""
    success: bool
    route: Optional[ContractorRoute] = None
    plan_document_path: Optional[str] = None
    review_config_path: Optional[str] = None
    complexity_score: int = 0
    total_cost: float = 0.0
    error: Optional[str] = None
    refine_rounds_completed: int = 0
