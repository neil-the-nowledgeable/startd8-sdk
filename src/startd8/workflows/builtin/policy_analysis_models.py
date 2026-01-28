"""
Data models for the PolicyAnalysis workflow.

Defines input processing, analysis criteria, scoring structures,
and output formats for multi-agent policy analysis.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, ConfigDict, Field


class InputSource(str, Enum):
    """Type of input provided."""
    RAW_TEXT = "raw_text"
    URL = "url"
    FILE = "file"


class PolicyInputType(str, Enum):
    """Type of policy document."""
    BILL = "bill"
    LAW = "law"
    REGULATION = "regulation"
    EXECUTIVE_ORDER = "executive_order"
    COURT_RULING = "court_ruling"
    TREATY = "treaty"
    POLICY = "policy"
    OTHER = "other"


class AnalysisCriterion(str, Enum):
    """
    Critical analysis criteria for policy evaluation.

    Each criterion centers the wellbeing and empowerment of ordinary people
    while identifying structures of power imbalance and historical injustice.
    """
    BENEFIT_TO_PEOPLE = "benefit_to_people"
    PEOPLE_EMPOWERMENT = "people_empowerment"
    POWER_IMBALANCE = "power_imbalance"
    CORPORATE_PRIVILEGE = "corporate_privilege"
    DOCTRINE_OF_DISCOVERY = "doctrine_of_discovery"
    SUPREMACY_IDEOLOGY = "supremacy_ideology"
    SLAVERY_LEGACY = "slavery_legacy"


class OverallAssessment(str, Enum):
    """Overall assessment category based on score."""
    HARMFUL = "harmful"  # 0-20
    CONCERNING = "concerning"  # 21-40
    NEUTRAL = "neutral"  # 41-60
    BENEFICIAL = "beneficial"  # 61-80
    HIGHLY_BENEFICIAL = "highly_beneficial"  # 81-100


class Severity(str, Enum):
    """Severity level for red flags."""
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class ConsensusLevel(str, Enum):
    """Level of consensus among agents."""
    HIGH = "high"  # std dev < 10
    MODERATE = "moderate"  # std dev 10-20
    LOW = "low"  # std dev 20-30
    DIVERGENT = "divergent"  # std dev > 30


# ============================================================================
# Input Models
# ============================================================================


@dataclass
class PolicyInput:
    """
    Processed policy document input.

    Represents the normalized input after fetching/reading from
    text, URL, or file sources.
    """
    input_id: str
    source_type: InputSource
    original_source: str  # URL, file path, or "raw_text"
    content: str
    title: Optional[str] = None
    policy_type: PolicyInputType = PolicyInputType.OTHER
    jurisdiction: Optional[str] = None  # e.g., "US Federal", "California", "EU"
    date_introduced: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    extraction_error: Optional[str] = None
    content_length: int = 0

    def __post_init__(self):
        if self.content_length == 0:
            self.content_length = len(self.content)


# ============================================================================
# Scoring Models
# ============================================================================


@dataclass
class CriterionScore:
    """
    Score for a single analysis criterion.

    Scores range from 0-100 where:
    - 0 = Completely harmful/problematic for this criterion
    - 100 = Fully beneficial/no concerns for this criterion
    """
    criterion: AnalysisCriterion
    score: int  # 0-100
    confidence: float  # 0.0-1.0
    rationale: str
    evidence: List[str] = field(default_factory=list)
    red_flags: List[str] = field(default_factory=list)

    def __post_init__(self):
        # Clamp values
        self.score = max(0, min(100, self.score))
        self.confidence = max(0.0, min(1.0, self.confidence))


@dataclass
class RedFlag:
    """
    A significant concern identified in the policy.

    Red flags are issues that warrant special attention due to
    potential harm to people or entrenchment of unjust power structures.
    """
    flag_id: str
    severity: Severity
    category: AnalysisCriterion
    title: str
    description: str
    affected_sections: List[str] = field(default_factory=list)
    evidence_quotes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON output."""
        return {
            "flag_id": self.flag_id,
            "severity": self.severity.value,
            "category": self.category.value,
            "title": self.title,
            "description": self.description,
            "affected_sections": self.affected_sections,
            "evidence_quotes": self.evidence_quotes,
        }


@dataclass
class SynthesizedScore:
    """
    Synthesized score from multiple agents for a single criterion.

    Includes statistical measures to understand agent consensus.
    """
    criterion: AnalysisCriterion
    mean_score: float
    min_score: int
    max_score: int
    std_deviation: float
    consensus_level: ConsensusLevel
    synthesized_rationale: str
    individual_scores: List[int] = field(default_factory=list)

    @classmethod
    def from_scores(
        cls,
        criterion: AnalysisCriterion,
        scores: List[int],
        rationale: str = "",
    ) -> "SynthesizedScore":
        """Create synthesized score from list of individual scores."""
        import statistics

        if not scores:
            return cls(
                criterion=criterion,
                mean_score=0.0,
                min_score=0,
                max_score=0,
                std_deviation=0.0,
                consensus_level=ConsensusLevel.DIVERGENT,
                synthesized_rationale=rationale,
                individual_scores=[],
            )

        mean = statistics.mean(scores)
        std_dev = statistics.stdev(scores) if len(scores) > 1 else 0.0

        # Determine consensus level based on standard deviation
        if std_dev < 10:
            consensus = ConsensusLevel.HIGH
        elif std_dev < 20:
            consensus = ConsensusLevel.MODERATE
        elif std_dev < 30:
            consensus = ConsensusLevel.LOW
        else:
            consensus = ConsensusLevel.DIVERGENT

        return cls(
            criterion=criterion,
            mean_score=mean,
            min_score=min(scores),
            max_score=max(scores),
            std_deviation=std_dev,
            consensus_level=consensus,
            synthesized_rationale=rationale,
            individual_scores=scores,
        )


# ============================================================================
# Agent Analysis Models
# ============================================================================


@dataclass
class AgentAnalysis:
    """
    Single agent's complete analysis of a policy.

    Contains per-criterion scores, identified red flags,
    narrative sections, and execution metrics.
    """
    analysis_id: str
    agent_name: str
    model: str

    # Overall assessment
    overall_score: int  # 0-100
    overall_assessment: OverallAssessment

    # Per-criterion scores
    criterion_scores: List[CriterionScore] = field(default_factory=list)

    # Red flags identified
    red_flags: List[RedFlag] = field(default_factory=list)

    # Narrative sections
    executive_summary: str = ""
    detailed_analysis: str = ""
    recommendations: List[str] = field(default_factory=list)

    # Raw response for debugging
    raw_response: str = ""

    # Execution metrics
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    time_ms: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def get_score_for_criterion(self, criterion: AnalysisCriterion) -> Optional[int]:
        """Get score for a specific criterion."""
        for cs in self.criterion_scores:
            if cs.criterion == criterion:
                return cs.score
        return None


# ============================================================================
# Output Models (Pydantic for JSON Schema)
# ============================================================================


class RedFlagOutput(BaseModel):
    """Red flag in structured output format."""
    flag_id: str
    severity: str = Field(description="critical|major|minor")
    category: str = Field(description="Analysis criterion category")
    title: str
    description: str
    evidence_quotes: List[str] = Field(default_factory=list)
    agents_identifying: int = Field(default=1, description="Number of agents that identified this flag")


class CriterionScoreOutput(BaseModel):
    """Criterion score in structured output format."""
    criterion: str
    mean_score: float = Field(ge=0, le=100)
    min_score: int = Field(ge=0, le=100)
    max_score: int = Field(ge=0, le=100)
    consensus_level: str = Field(description="high|moderate|low|divergent")
    rationale: str = ""


class PolicyAnalysisOutput(BaseModel):
    """
    Structured JSON output for programmatic consumption.

    This is the machine-readable output format containing all
    scores, flags, and metadata in a well-defined schema.
    """
    analysis_id: str
    policy_title: str
    policy_type: str
    jurisdiction: Optional[str] = None

    # Overall assessment
    overall_score: int = Field(ge=0, le=100, description="0=harmful, 100=beneficial")
    overall_assessment: str = Field(description="harmful|concerning|neutral|beneficial|highly_beneficial")
    confidence: float = Field(ge=0.0, le=1.0)

    # Per-criterion scores (synthesized)
    criterion_scores: Dict[str, CriterionScoreOutput] = Field(default_factory=dict)

    # Red flags (consolidated across agents)
    red_flags: List[RedFlagOutput] = Field(default_factory=list)
    critical_flags_count: int = 0
    major_flags_count: int = 0
    minor_flags_count: int = 0

    # Agent consensus information
    agent_count: int = 0
    consensus_level: str = "unknown"
    score_variance: float = 0.0

    # Recommendations (synthesized)
    recommendations: List[str] = Field(default_factory=list)

    # Metadata
    analyzed_at: datetime
    total_cost: float = 0.0
    total_time_ms: int = 0

    model_config = ConfigDict(
        ser_json_timedelta="iso8601",
    )


# ============================================================================
# Complete Result Model
# ============================================================================


@dataclass
class PolicyAnalysisResult:
    """
    Complete result of the PolicyAnalysis workflow.

    Contains the input, individual agent analyses, synthesized
    output, narrative report, and execution metrics.
    """
    workflow_id: str
    success: bool

    # Input info
    policy_input: Optional[PolicyInput] = None

    # Individual analyses from each agent
    agent_analyses: List[AgentAnalysis] = field(default_factory=list)

    # Synthesized outputs
    structured_output: Optional[PolicyAnalysisOutput] = None
    narrative_report: str = ""

    # Aggregated metrics
    total_time_ms: int = 0
    total_cost: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    # Error handling
    error: Optional[str] = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

    def to_summary(self) -> Dict[str, Any]:
        """Return summary suitable for logging/display."""
        return {
            "workflow_id": self.workflow_id,
            "success": self.success,
            "overall_score": self.structured_output.overall_score if self.structured_output else None,
            "overall_assessment": self.structured_output.overall_assessment if self.structured_output else None,
            "agent_count": len(self.agent_analyses),
            "red_flags_count": len(self.structured_output.red_flags) if self.structured_output else 0,
            "critical_flags": self.structured_output.critical_flags_count if self.structured_output else 0,
            "consensus_level": self.structured_output.consensus_level if self.structured_output else "unknown",
            "total_cost": f"${self.total_cost:.4f}",
            "total_time_ms": self.total_time_ms,
        }

    def get_criterion_consensus(self, criterion: AnalysisCriterion) -> Optional[ConsensusLevel]:
        """Get consensus level for a specific criterion."""
        if not self.structured_output or criterion.value not in self.structured_output.criterion_scores:
            return None
        return ConsensusLevel(
            self.structured_output.criterion_scores[criterion.value].consensus_level
        )


# ============================================================================
# Helper Functions
# ============================================================================


def score_to_assessment(score: int) -> OverallAssessment:
    """Convert numeric score to assessment category."""
    if score <= 20:
        return OverallAssessment.HARMFUL
    elif score <= 40:
        return OverallAssessment.CONCERNING
    elif score <= 60:
        return OverallAssessment.NEUTRAL
    elif score <= 80:
        return OverallAssessment.BENEFICIAL
    else:
        return OverallAssessment.HIGHLY_BENEFICIAL


def parse_policy_type(type_str: Optional[str]) -> PolicyInputType:
    """Parse policy type string to enum."""
    if not type_str:
        return PolicyInputType.OTHER

    type_lower = type_str.lower().strip()
    type_map = {
        "bill": PolicyInputType.BILL,
        "law": PolicyInputType.LAW,
        "regulation": PolicyInputType.REGULATION,
        "executive_order": PolicyInputType.EXECUTIVE_ORDER,
        "executive order": PolicyInputType.EXECUTIVE_ORDER,
        "court_ruling": PolicyInputType.COURT_RULING,
        "court ruling": PolicyInputType.COURT_RULING,
        "ruling": PolicyInputType.COURT_RULING,
        "treaty": PolicyInputType.TREATY,
        "policy": PolicyInputType.POLICY,
    }
    return type_map.get(type_lower, PolicyInputType.OTHER)
