"""
Data models for the implementation engine.

Defines SpecResult, DraftResult, and ReviewResult in a neutral location
that both LeadContractorWorkflow and Artisan ImplementPhaseHandler can import.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


__all__ = [
    "SpecResult",
    "DraftResult",
    "ReviewResult",
    "EngineRequest",
    "EngineResult",
]


@dataclass
class SpecResult:
    """Implementation specification produced by the spec builder.

    Structurally matches ``ImplementationSpec`` from ``lead_contractor_models``
    with conversion methods for backward compatibility.
    """

    spec_id: str
    task_summary: str
    requirements: List[str]
    technical_approach: str
    acceptance_criteria: List[str]
    code_structure: Optional[str] = None
    edge_cases: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    raw_spec: str = ""

    # Telemetry
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    time_ms: int = 0

    def to_implementation_spec(self) -> Any:
        """Convert to ``ImplementationSpec`` for LeadContractorWorkflow compatibility."""
        from startd8.workflows.builtin.lead_contractor_models import ImplementationSpec

        return ImplementationSpec(
            spec_id=self.spec_id,
            task_summary=self.task_summary,
            requirements=list(self.requirements),
            technical_approach=self.technical_approach,
            acceptance_criteria=list(self.acceptance_criteria),
            code_structure=self.code_structure,
            edge_cases=list(self.edge_cases),
            constraints=list(self.constraints),
            examples=list(self.examples),
            raw_spec=self.raw_spec,
            created_at=self.created_at,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cost=self.cost,
            time_ms=self.time_ms,
        )

    @classmethod
    def from_implementation_spec(cls, spec: Any) -> "SpecResult":
        """Create from ``ImplementationSpec`` for migration."""
        return cls(
            spec_id=spec.spec_id,
            task_summary=spec.task_summary,
            requirements=list(spec.requirements),
            technical_approach=spec.technical_approach,
            acceptance_criteria=list(spec.acceptance_criteria),
            code_structure=spec.code_structure,
            edge_cases=list(spec.edge_cases),
            constraints=list(spec.constraints),
            examples=list(getattr(spec, "examples", [])),
            raw_spec=spec.raw_spec,
            created_at=spec.created_at,
            input_tokens=spec.input_tokens,
            output_tokens=spec.output_tokens,
            cost=spec.cost,
            time_ms=spec.time_ms,
        )


@dataclass
class DraftResult:
    """Implementation draft produced by the drafter."""

    draft_id: str
    iteration: int
    implementation: str
    explanation: Optional[str] = None
    spec_id: str = ""

    # Agent info
    agent_name: str = ""
    model: str = ""

    # Telemetry
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    time_ms: int = 0

    # Truncation
    was_truncated: bool = False
    truncation_source: Optional[str] = None  # "api", "heuristic", "size_regression"
    raw_response: str = ""


@dataclass
class ReviewResult:
    """Review of a draft implementation."""

    review_id: str
    iteration: int
    passed: bool
    score: int  # 0-100

    # Detailed feedback
    strengths: List[str] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    blocking_issues: List[str] = field(default_factory=list)

    review_text: str = ""
    draft_id: str = ""

    # Telemetry
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    time_ms: int = 0


@dataclass
class EngineRequest:
    """Request to the implementation engine for a single task.

    Attributes:
        task_description: What to implement.
        context: Additional context dict (may contain ``design_document``,
            ``existing_files``, ``edit_mode``, ``target_files``, etc.).
        drafter_agent_spec: Agent spec for drafting (e.g. ``gemini:gemini-2.5-flash-lite``).
        reviewer_agent_spec: Agent spec for reviewing (e.g. ``anthropic:claude-sonnet-4-20250514``).
        max_iterations: Maximum draft-review cycles.
        pass_threshold: Minimum review score to pass (0-100).
        output_format: Optional output format guidance.
        existing_files: Existing file contents for edit-mode tasks (path -> content).
        edit_mode: Edit mode classification dict.
        target_files: Target file paths.
        template_key: Override template selection (``spec`` or ``spec_from_design``).
        check_truncation: Enable heuristic truncation detection.
        strict_truncation: Use lower confidence threshold.
        fail_on_api_truncation: Fail on API-level truncation.
        fail_on_heuristic_truncation: Fail on heuristic truncation.
        edit_min_pct: Minimum % of existing lines in edit output.
    """

    task_description: str
    context: Dict[str, Any] = field(default_factory=dict)
    drafter_agent_spec: Optional[str] = None
    reviewer_agent_spec: Optional[str] = None
    max_iterations: int = 3
    pass_threshold: int = 80
    output_format: Optional[str] = None
    existing_files: Optional[Dict[str, str]] = None
    edit_mode: Optional[Dict[str, Any]] = None
    target_files: Optional[List[str]] = None
    template_key: Optional[str] = None
    check_truncation: bool = True
    strict_truncation: bool = False
    fail_on_api_truncation: bool = True
    fail_on_heuristic_truncation: bool = False
    edit_min_pct: Optional[int] = 80


@dataclass
class EngineResult:
    """Result from a full engine run (spec -> draft -> review cycles)."""

    spec: Optional[SpecResult] = None
    drafts: List[DraftResult] = field(default_factory=list)
    reviews: List[ReviewResult] = field(default_factory=list)
    final_code: str = ""
    passed: bool = False
    iterations_used: int = 0

    # Cost breakdown
    spec_cost: float = 0.0
    draft_cost: float = 0.0
    review_cost: float = 0.0
    total_cost: float = 0.0

    # Token totals
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    # Error info
    error: Optional[str] = None

    # Truncation events
    truncation_events: List[Dict[str, Any]] = field(default_factory=list)

    # Raw drafter response (for multi-file extraction)
    last_raw_response: str = ""

    def to_serializable_summary(self) -> Dict[str, Any]:
        """Return a JSON-serializable summary for metadata embedding."""
        return {
            "iterations_used": self.iterations_used,
            "spec_id": self.spec.spec_id if self.spec else None,
            "passed": self.passed,
            "review_scores": [r.score for r in self.reviews],
            "truncation_events": self.truncation_events,
            "total_cost": self.total_cost,
        }
