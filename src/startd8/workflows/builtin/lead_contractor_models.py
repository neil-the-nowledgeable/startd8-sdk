"""
Data models for the LeadContractor workflow.

Defines configuration, intermediate results, and output structures
for the cost-efficient multi-agent implementation pattern.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field

from startd8.model_catalog import Models


__all__ = [
    "DrafterChoice",
    "WorkflowPhase",
    "LeadContractorConfig",
    "ImplementationSpec",
    "DraftResult",
    "ReviewResult",
    "IntegrationResult",
    "PhaseMetrics",
    "LeadContractorResult",
    "TestCase",
    "TestPlanJSON",
    "TestPlanMarkdown",
]


class DrafterChoice(str, Enum):
    """Available drafter models (cheaper options for drafting work)."""
    # OpenAI GPT-4.1 family (1M context, April 2025)
    GPT_4_1_MINI = "openai:gpt-4.1-mini"       # $0.40/$1.60 per 1M tokens - fast, cost-efficient
    GPT_4_1_NANO = "openai:gpt-4.1-nano"       # $0.10/$0.40 per 1M tokens - ultra-fast, lowest cost
    # OpenAI GPT-4o family (legacy but still good)
    GPT_4O_MINI = "openai:gpt-4o-mini"         # $0.15/$0.60 per 1M tokens
    # Google Gemini 2.5 family (recommended)
    GEMINI_2_5_FLASH = "gemini:gemini-2.5-flash"         # $0.15/$0.60 per 1M tokens
    GEMINI_2_5_FLASH_LITE = "gemini:gemini-2.5-flash-lite"  # $0.075/$0.30 per 1M tokens
    # Google Gemini 3.x family (latest)
    GEMINI_3_FLASH_PREVIEW = "gemini:gemini-3-flash-preview"  # $0.10/$0.40 per 1M tokens
    # Google Gemini 2.0 family (retiring March 2026)
    GEMINI_2_0_FLASH = "gemini:gemini-2.0-flash"          # $0.10/$0.40 per 1M tokens
    GEMINI_2_0_FLASH_LITE = "gemini:gemini-2.0-flash-lite"  # $0.075/$0.30 per 1M tokens


class WorkflowPhase(str, Enum):
    """Phases of the lead contractor workflow."""
    SPEC_CREATION = "spec_creation"
    DRAFTING = "drafting"
    REVIEW = "review"
    REVISION = "revision"
    INTEGRATION = "integration"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class LeadContractorConfig:
    """
    Configuration for the LeadContractor workflow.

    Attributes:
        task_description: What needs to be implemented
        context: Additional context (existing code, requirements, constraints)
        lead_agent: Lead agent spec (default: Models.LEAD_CONTRACTOR_LEAD)
        drafter_agent: Drafter agent spec (default: Models.LEAD_CONTRACTOR_DRAFTER)
        max_iterations: Maximum draft/review cycles (default: 3)
        pass_threshold: Minimum review score to pass (0-100, default: 80)
        output_format: Expected output format guidance for drafter
        integration_instructions: Instructions for final integration

    Note:
        Default models are defined in startd8.model_catalog.Models.
        Update Models.LEAD_CONTRACTOR_LEAD and Models.LEAD_CONTRACTOR_DRAFTER
        when newer models are available.
    """
    task_description: str
    context: Optional[Dict[str, Any]] = None
    lead_agent: str = Models.LEAD_CONTRACTOR_LEAD  # Claude Sonnet (latest)
    drafter_agent: str = Models.LEAD_CONTRACTOR_DRAFTER  # Gemini Flash Lite (cheapest)
    max_iterations: int = 3
    pass_threshold: int = 80
    output_format: Optional[str] = None
    integration_instructions: Optional[str] = None


@dataclass
class ImplementationSpec:
    """
    Specification created by Claude (lead contractor).

    Contains detailed instructions for the drafter agent.
    """
    spec_id: str
    task_summary: str
    requirements: List[str]
    technical_approach: str
    acceptance_criteria: List[str]
    code_structure: Optional[str] = None  # Expected file/class structure
    edge_cases: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    raw_spec: str = ""  # Full spec text from Claude

    # Metrics
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    time_ms: int = 0


@dataclass
class DraftResult:
    """
    Implementation draft from the drafter agent.
    """
    draft_id: str
    iteration: int
    implementation: str  # The actual code/content
    explanation: Optional[str] = None  # Drafter's notes

    # From which spec
    spec_id: str = ""

    # Metrics
    agent_name: str = ""
    model: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    time_ms: int = 0
    was_truncated: bool = False  # Whether output was truncated
    truncation_source: Optional[str] = None  # "api" or "heuristic"


@dataclass
class ReviewResult:
    """
    Review result from Claude (lead contractor).

    Extends ReviewFeedback pattern from IterativeDevWorkflow.
    """
    review_id: str
    iteration: int
    passed: bool
    score: int  # 0-100

    # Detailed feedback
    strengths: List[str] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    blocking_issues: List[str] = field(default_factory=list)  # Must fix

    # Full review text
    review_text: str = ""

    # Reference
    draft_id: str = ""

    # Metrics
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    time_ms: int = 0


@dataclass
class IntegrationResult:
    """
    Final integration result from Claude.
    """
    integration_id: str
    final_implementation: str
    integration_notes: str = ""
    final_review_passed: bool = True

    # Metrics
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    time_ms: int = 0


@dataclass
class PhaseMetrics:
    """
    Metrics for a single workflow phase.

    Note: Reserved for future detailed per-phase tracking. Currently defined
    for API completeness but not actively populated during workflow execution.
    Phase metrics are instead tracked via StepResult in the workflow output.
    """
    phase: WorkflowPhase
    agent_name: str
    model: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    time_ms: int = 0
    iteration: Optional[int] = None  # For drafting/review phases
    success: bool = True
    error: Optional[str] = None


@dataclass
class LeadContractorResult:
    """
    Complete result of the LeadContractor workflow.
    """
    workflow_id: str
    success: bool
    final_implementation: str

    # Phase results
    spec: Optional[ImplementationSpec] = None
    drafts: List[DraftResult] = field(default_factory=list)
    reviews: List[ReviewResult] = field(default_factory=list)
    integration: Optional[IntegrationResult] = None

    # Aggregated metrics
    total_iterations: int = 0
    total_time_ms: int = 0
    phase_metrics: List[PhaseMetrics] = field(default_factory=list)

    # Cost breakdown by role
    lead_cost: float = 0.0  # Claude (spec + reviews + integration)
    drafter_cost: float = 0.0  # Cheaper model (drafts)
    total_cost: float = 0.0

    # Token breakdown
    lead_input_tokens: int = 0
    lead_output_tokens: int = 0
    drafter_input_tokens: int = 0
    drafter_output_tokens: int = 0

    # Status
    final_phase: WorkflowPhase = WorkflowPhase.COMPLETED
    error: Optional[str] = None

    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

    def get_cost_efficiency_ratio(self) -> float:
        """
        Calculate ratio of drafter cost to lead cost.
        Lower is better (more work done by cheaper model).
        """
        if self.lead_cost == 0:
            return 0.0
        return self.drafter_cost / self.lead_cost

    def to_summary(self) -> Dict[str, Any]:
        """Return summary suitable for logging/display."""
        return {
            "workflow_id": self.workflow_id,
            "success": self.success,
            "total_iterations": self.total_iterations,
            "total_time_ms": self.total_time_ms,
            "lead_cost": f"${self.lead_cost:.4f}",
            "drafter_cost": f"${self.drafter_cost:.4f}",
            "total_cost": f"${self.total_cost:.4f}",
            "cost_efficiency_ratio": f"{self.get_cost_efficiency_ratio():.2f}",
            "final_phase": self.final_phase.value,
        }


# ============================================================================
# Test Plan Models (Output Formats)
# ============================================================================

class TestCase(BaseModel):
    """Single test case in the test plan."""
    id: str
    name: str
    description: str
    priority: str = Field(description="P0 (critical), P1 (high), P2 (medium), P3 (low)")
    category: str = Field(description="unit, integration, e2e, performance, security")
    preconditions: List[str] = Field(default_factory=list)
    steps: List[str] = Field(default_factory=list)
    expected_result: str
    automation_status: str = Field(default="pending", description="pending, automated, manual")


class TestPlanJSON(BaseModel):
    """
    Machine-parseable test plan output.

    Used for integration with test runners and CI/CD.
    """
    plan_id: str
    task_description: str
    created_at: datetime
    workflow_id: str

    # Test cases
    test_cases: List[TestCase] = Field(default_factory=list)

    # Summary
    total_tests: int = 0
    by_priority: Dict[str, int] = Field(default_factory=dict)
    by_category: Dict[str, int] = Field(default_factory=dict)

    # Coverage notes
    coverage_notes: List[str] = Field(default_factory=list)
    gaps_identified: List[str] = Field(default_factory=list)


class TestPlanMarkdown(BaseModel):
    """
    Human-readable test plan output.
    """
    title: str
    summary: str
    content: str  # Full markdown content

    # Sections
    overview: str = ""
    test_strategy: str = ""
    test_cases_md: str = ""
    execution_plan: str = ""
    coverage_analysis: str = ""
