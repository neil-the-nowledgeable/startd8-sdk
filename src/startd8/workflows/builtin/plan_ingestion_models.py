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
    "ArtisanContextSeed",
    "IngestionState",
    "PlanIngestionResult",
    "TaskTrackingConfig",
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
    # Task-specific content hints for design doc (e.g. "Parameter validation", "Error handling")
    design_doc_sections: List[str] = field(default_factory=list)


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

    def to_seed_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict for the artisan context seed."""
        return {
            "title": self.title,
            "goals": list(self.goals),
            "features": [
                {
                    "feature_id": f.feature_id,
                    "name": f.name,
                    "description": f.description,
                    "target_files": list(f.target_files),
                    "dependencies": list(f.dependencies),
                    "estimated_loc": f.estimated_loc,
                    "labels": list(f.labels),
                    "design_doc_sections": list(f.design_doc_sections),
                }
                for f in self.features
            ],
            "dependency_graph": dict(self.dependency_graph),
            "mentioned_files": list(self.mentioned_files),
        }


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

    def to_seed_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict for the artisan context seed."""
        return {
            "composite": self.composite,
            "dimensions": {
                "feature_count": self.feature_count,
                "cross_file_deps": self.cross_file_deps,
                "api_surface": self.api_surface,
                "test_complexity": self.test_complexity,
                "integration_depth": self.integration_depth,
                "domain_novelty": self.domain_novelty,
                "ambiguity": self.ambiguity,
            },
            "reasoning": self.reasoning,
            "route": self.route.value if self.route else None,
        }


@dataclass
class ArtisanContextSeed:
    """Structured context seed for the ArtisanContractor pipeline."""
    version: str = "1.0.0"
    generated_at: str = ""
    generator: str = "plan-ingestion"
    plan: Optional[Dict[str, Any]] = None
    complexity: Optional[Dict[str, Any]] = None
    tasks: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    ingestion_metrics: Dict[str, Any] = field(default_factory=dict)
    # Optional onboarding metadata (artifact_manifest_path, project_context_path, etc.)
    onboarding: Optional[Dict[str, Any]] = None
    # Shared architectural context from manifest + cross-feature analysis
    architectural_context: Optional[Dict[str, Any]] = None
    # Per-task design calibration (sections, max_tokens) from SizeEstimator
    design_calibration: Optional[Dict[str, Dict[str, Any]]] = None
    # Context files used for plan ingestion (path + optional checksum)
    context_files: Optional[List[Dict[str, Any]]] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "version": self.version,
            "generated_at": self.generated_at,
            "generator": self.generator,
            "plan": self.plan,
            "complexity": self.complexity,
            "tasks": list(self.tasks),
            "artifacts": dict(self.artifacts),
            "ingestion_metrics": dict(self.ingestion_metrics),
        }
        if self.architectural_context is not None:
            d["architectural_context"] = self.architectural_context
        if self.design_calibration is not None:
            d["design_calibration"] = self.design_calibration
        if self.onboarding is not None:
            d["onboarding"] = self.onboarding
        if self.context_files is not None:
            d["context_files"] = self.context_files
        return d


@dataclass
class IngestionState:
    """Mutable workflow state for debugging and checkpointing."""
    current_phase: IngestionPhase = IngestionPhase.PARSE
    parsed_plan: Optional[ParsedPlan] = None
    complexity: Optional[ComplexityScore] = None
    route: Optional[ContractorRoute] = None
    plan_document_path: Optional[str] = None
    review_config_path: Optional[str] = None
    context_seed_path: Optional[str] = None
    total_cost: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "current_phase": self.current_phase.value,
            "route": self.route.value if self.route else None,
            "plan_document_path": self.plan_document_path,
            "review_config_path": self.review_config_path,
            "context_seed_path": self.context_seed_path,
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


@dataclass
class TaskTrackingConfig:
    """Configuration for ContextCore task tracking artifact generation."""
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    sprint_id: Optional[str] = None
    install_to_contextcore: bool = False
    emit_ndjson_events: bool = True
