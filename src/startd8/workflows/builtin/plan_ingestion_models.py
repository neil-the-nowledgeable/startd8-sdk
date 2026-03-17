"""
Data models for the PlanIngestionWorkflow.

Defines enums, intermediate results, and output structures for the
plan ingestion pipeline: parse → assess → transform → refine → emit.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from startd8.seeds.models import ContextSeed

# Deprecated alias — use ContextSeed from startd8.seeds.models directly.
ArtisanContextSeed = ContextSeed


__all__ = [
    "ContractorRoute",
    "IngestionPhase",
    "PlanIngestionConfig",
    "ParsedFeature",
    "ParsedPlan",
    "ComplexityScore",
    "ArtisanContextSeed",
    "ContextSeed",
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


def _as_bool_cfg(raw: Any, default: bool) -> bool:
    """Parse truthy/falsy config values (internal to PlanIngestionConfig)."""
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    text = str(raw).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_file_list_cfg(raw: Union[str, list, None]) -> List[str]:
    """Parse a file list from string (comma-separated) or list."""
    if not raw:
        return []
    if isinstance(raw, str):
        return [f.strip() for f in raw.split(",") if f.strip()]
    return list(raw)


@dataclass
class PlanIngestionConfig:
    """Typed configuration for PlanIngestionWorkflow (AC-R1).

    Consolidates 30+ config.get() calls and their parsing/casting/defaulting
    into a single typed model. Created via ``from_dict(config)`` at the top
    of ``_execute()``.
    """

    # Required
    plan_path: Path = field(default_factory=lambda: Path("."))
    output_dir: Path = field(default_factory=lambda: Path("."))

    # Routing & complexity
    complexity_threshold: int = 40
    force_route: Optional[str] = "prime"  # AC-R3 default

    # Review
    review_rounds: int = 2
    skip_arc_review: bool = False
    review_quality_tier: str = "flagship"
    review_providers: Optional[List[str]] = None

    # LLM settings
    llm_read_timeout_seconds: float = 300.0
    llm_max_attempts: int = 1
    enable_heuristic_parse_fallback: bool = True

    # Scope & files
    scope: Optional[str] = None
    context_files: Optional[List[str]] = None
    contextcore_export_dir: Optional[str] = None
    requirements_files: List[str] = field(default_factory=list)

    # Cost
    warn_cost_usd: Optional[float] = None
    max_cost_usd: Optional[float] = None

    # Quality gates
    min_export_coverage: float = 0.0
    low_quality_policy: str = "bias_artisan"
    min_requirements_coverage: float = 70.0
    min_artifact_mapping_coverage: float = 70.0
    max_contract_conflicts: int = 2

    # Kaizen
    kaizen_capture: bool = False
    kaizen_config_path: Optional[str] = None

    # Task tracking
    generate_task_tracking: bool = False
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    sprint_id: Optional[str] = None
    install_to_contextcore: bool = False
    emit_ndjson_events: bool = True

    # Misc
    project_root: Optional[str] = None
    contextcore_yaml: Optional[str] = None
    force_regenerate: bool = False

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> "PlanIngestionConfig":
        """Parse a raw config dict into a typed PlanIngestionConfig.

        Consolidates all casting, parsing, and defaulting that was previously
        scattered across 30+ lines at the top of ``_execute()``.
        """
        plan_path = Path(str(config["plan_path"])).expanduser().resolve()
        output_dir = Path(str(config.get("output_dir", "."))).expanduser().resolve()

        # Optional float fields
        _raw_warn = config.get("warn_cost_usd")
        warn_cost_usd = float(_raw_warn) if _raw_warn is not None else None
        _raw_max = config.get("max_cost_usd")
        max_cost_usd = float(_raw_max) if _raw_max is not None else None

        # Requirements consolidation
        requirements_files = _parse_file_list_cfg(config.get("requirements_files"))
        requirements_path = config.get("requirements_path")
        if requirements_path:
            requirements_files = [str(requirements_path)] + requirements_files

        # Low quality policy with validation
        _VALID_QUALITY_POLICIES = {"fail", "bias_artisan"}
        low_quality_policy = str(config.get("low_quality_policy", "bias_artisan")).strip().lower()
        if low_quality_policy not in _VALID_QUALITY_POLICIES:
            low_quality_policy = "bias_artisan"

        # Context files parsing
        _raw_cf = config.get("context_files")
        context_files: Optional[List[str]] = None
        if _raw_cf:
            if isinstance(_raw_cf, str):
                context_files = [f.strip() for f in _raw_cf.split(",") if f.strip()]
            else:
                context_files = list(_raw_cf)

        return cls(
            plan_path=plan_path,
            output_dir=output_dir,
            complexity_threshold=int(config.get("complexity_threshold", 40)),
            force_route=config.get("force_route", "prime"),
            review_rounds=int(config.get("review_rounds", 2)),
            skip_arc_review=_as_bool_cfg(config.get("skip_arc_review"), False),
            review_quality_tier=str(config.get("review_quality_tier", "flagship")),
            review_providers=config.get("providers"),
            llm_read_timeout_seconds=float(config.get("llm_read_timeout_seconds", 300)),
            llm_max_attempts=int(config.get("llm_max_attempts", 1)),
            enable_heuristic_parse_fallback=_as_bool_cfg(
                config.get("enable_heuristic_parse_fallback"), True,
            ),
            scope=config.get("scope"),
            context_files=context_files,
            contextcore_export_dir=config.get("contextcore_export_dir"),
            requirements_files=requirements_files,
            warn_cost_usd=warn_cost_usd,
            max_cost_usd=max_cost_usd,
            min_export_coverage=float(config.get("min_export_coverage", 0)),
            low_quality_policy=low_quality_policy,
            min_requirements_coverage=float(config.get("min_requirements_coverage", 70)),
            min_artifact_mapping_coverage=float(config.get("min_artifact_mapping_coverage", 70)),
            max_contract_conflicts=int(config.get("max_contract_conflicts", 2)),
            kaizen_capture=_as_bool_cfg(config.get("kaizen"), False),
            kaizen_config_path=config.get("kaizen_config_path"),
            generate_task_tracking=config.get("generate_task_tracking", False),
            project_id=config.get("project_id"),
            project_name=config.get("project_name"),
            sprint_id=config.get("sprint_id"),
            install_to_contextcore=config.get("install_to_contextcore", False),
            emit_ndjson_events=config.get("emit_ndjson_events", True),
            project_root=config.get("project_root"),
            contextcore_yaml=config.get("contextcore_yaml"),
            force_regenerate=config.get("force_regenerate", False),
        )


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
    # Artifact types this task generates (e.g. "dashboard", "prometheus_rule", "servicemonitor")
    artifact_types_addressed: List[str] = field(default_factory=list)
    # IMP-4: Key function/method signatures (e.g. "def serve(port: int) -> None")
    api_signatures: List[str] = field(default_factory=list)
    # IMP-4: Transport protocol (grpc, http, cli, library, none)
    protocol: str = ""
    # IMP-4: Runtime packages (e.g. grpcio, flask, redis)
    runtime_dependencies: List[str] = field(default_factory=list)
    # IMP-4: Things this feature explicitly does NOT do
    negative_scope: List[str] = field(default_factory=list)
    # Go-specific: module path for go.mod (e.g. "github.com/org/repo/src/svc")
    module_path: str = ""
    # Go-specific: service name for package declaration and directory naming
    service_name: str = ""
    # Phase 6: CG-PI-2 — union of callers across all target FQNs
    affected_callers: List[str] = field(default_factory=list)
    # Phase 6: CG-PI-3 — True when max blast radius exceeds threshold
    high_impact: bool = False
    # Phase 6: CG-PI-4 — True when all FQNs target dead code (zero callers)
    targets_dead_code: bool = False


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
                    "artifact_types_addressed": list(f.artifact_types_addressed),
                    "api_signatures": list(f.api_signatures),
                    "protocol": f.protocol,
                    "runtime_dependencies": list(f.runtime_dependencies),
                    "negative_scope": list(f.negative_scope),
                    "affected_callers": list(f.affected_callers),
                    "high_impact": f.high_impact,
                    "targets_dead_code": f.targets_dead_code,
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
    call_graph_impact: int = 0  # Phase 6: CG-PI-1

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
                "call_graph_impact": self.call_graph_impact,
            },
            "reasoning": self.reasoning,
            "route": self.route.value if self.route else None,
        }



# NOTE: ArtisanContextSeed class was here (lines 328-392) until 2026-03-16.
# It was a duplicate of ContextSeed in startd8.seeds.models with identical
# fields and to_dict() logic. Unified to ContextSeed; the ArtisanContextSeed
# alias above provides backward compatibility.


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
