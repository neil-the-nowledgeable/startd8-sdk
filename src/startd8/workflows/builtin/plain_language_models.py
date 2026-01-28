"""
Data models for the PlainLanguage workflow.

Defines input processing, reading levels, and output structures
for simplifying complex content into accessible explanations.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, ConfigDict, Field


class ReadingLevel(str, Enum):
    """Target reading level for simplified output."""
    ELEMENTARY = "elementary"  # 5th grade, ~10 years old
    MIDDLE_SCHOOL = "middle_school"  # 8th grade, ~13 years old
    HIGH_SCHOOL = "high_school"  # 12th grade, ~17 years old
    GENERAL_PUBLIC = "general_public"  # Average adult, no specialized knowledge


class ContentType(str, Enum):
    """Type of content being simplified."""
    POLICY_ANALYSIS = "policy_analysis"
    LEGAL_DOCUMENT = "legal_document"
    TECHNICAL_REPORT = "technical_report"
    SCIENTIFIC_PAPER = "scientific_paper"
    FINANCIAL_REPORT = "financial_report"
    MEDICAL_INFO = "medical_info"
    GENERAL = "general"


class SimplificationMode(str, Enum):
    """Mode of operation for the workflow."""
    SINGLE_AGENT = "single_agent"
    MULTI_AGENT = "multi_agent"


# ============================================================================
# Input Models
# ============================================================================


@dataclass
class SimplificationInput:
    """
    Input content to be simplified.
    """
    input_id: str
    content: str
    content_type: ContentType = ContentType.GENERAL
    title: Optional[str] = None
    source: Optional[str] = None  # Where the content came from
    metadata: Dict[str, Any] = field(default_factory=dict)
    content_length: int = 0

    def __post_init__(self):
        if self.content_length == 0:
            self.content_length = len(self.content)


# ============================================================================
# Output Models
# ============================================================================


@dataclass
class KeyPoint:
    """A single key point extracted and simplified."""
    point_number: int
    original_concept: str  # What the original text said
    simplified: str  # Plain language version
    importance: str  # "critical", "important", "context"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "point_number": self.point_number,
            "original_concept": self.original_concept,
            "simplified": self.simplified,
            "importance": self.importance,
        }


@dataclass
class JargonTerm:
    """A technical term that was simplified."""
    term: str
    definition: str  # Plain language definition
    context: str  # How it's used in this document


@dataclass
class AgentSimplification:
    """Single agent's simplification of content."""
    agent_id: str
    agent_name: str
    model: str

    # Simplified output
    one_sentence: str  # One-sentence summary
    one_paragraph: str  # One-paragraph summary
    key_points: List[KeyPoint] = field(default_factory=list)
    plain_explanation: str = ""  # Full plain-language explanation

    # Jargon handling
    jargon_glossary: List[JargonTerm] = field(default_factory=list)

    # What matters
    bottom_line: str = ""  # "The bottom line is..."
    who_affected: str = ""  # Who this affects and how
    action_items: List[str] = field(default_factory=list)  # What readers can/should do

    # Metrics
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    time_ms: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class PlainLanguageOutput(BaseModel):
    """
    Structured output from the plain language workflow.
    """
    output_id: str
    title: Optional[str] = None
    content_type: str = "general"
    reading_level: str = "general_public"

    # Core simplified outputs
    one_sentence_summary: str = Field(description="Single sentence capturing the essence")
    one_paragraph_summary: str = Field(description="One paragraph overview")
    plain_explanation: str = Field(description="Full plain-language explanation")

    # Structured breakdown
    key_points: List[Dict[str, Any]] = Field(default_factory=list)

    # Practical information
    bottom_line: str = Field(default="", description="The single most important takeaway")
    who_is_affected: str = Field(default="", description="Who this impacts and how")
    action_items: List[str] = Field(default_factory=list, description="What readers can do")

    # Jargon glossary
    glossary: List[Dict[str, str]] = Field(default_factory=list)

    # Multi-agent info (if applicable)
    agent_count: int = 1
    mode: str = "single_agent"

    # Metadata
    original_length: int = 0
    simplified_length: int = 0
    compression_ratio: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    total_cost: float = 0.0

    model_config = ConfigDict(
        ser_json_timedelta="iso8601",
    )


# ============================================================================
# Complete Result Model
# ============================================================================


@dataclass
class PlainLanguageResult:
    """
    Complete result of the PlainLanguage workflow.
    """
    workflow_id: str
    success: bool

    # Input info
    input_content: Optional[SimplificationInput] = None

    # Agent outputs (one for single-agent, multiple for multi-agent)
    agent_outputs: List[AgentSimplification] = field(default_factory=list)

    # Final output
    output: Optional[PlainLanguageOutput] = None

    # Metrics
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
            "mode": self.output.mode if self.output else "unknown",
            "agent_count": len(self.agent_outputs),
            "key_points_count": len(self.output.key_points) if self.output else 0,
            "compression_ratio": f"{self.output.compression_ratio:.1%}" if self.output else "N/A",
            "total_cost": f"${self.total_cost:.4f}",
            "total_time_ms": self.total_time_ms,
        }


# ============================================================================
# Helper Functions
# ============================================================================


def parse_content_type(type_str: Optional[str]) -> ContentType:
    """Parse content type string to enum."""
    if not type_str:
        return ContentType.GENERAL

    type_lower = type_str.lower().strip().replace(" ", "_").replace("-", "_")
    type_map = {
        "policy_analysis": ContentType.POLICY_ANALYSIS,
        "policy": ContentType.POLICY_ANALYSIS,
        "legal_document": ContentType.LEGAL_DOCUMENT,
        "legal": ContentType.LEGAL_DOCUMENT,
        "technical_report": ContentType.TECHNICAL_REPORT,
        "technical": ContentType.TECHNICAL_REPORT,
        "scientific_paper": ContentType.SCIENTIFIC_PAPER,
        "scientific": ContentType.SCIENTIFIC_PAPER,
        "science": ContentType.SCIENTIFIC_PAPER,
        "financial_report": ContentType.FINANCIAL_REPORT,
        "financial": ContentType.FINANCIAL_REPORT,
        "finance": ContentType.FINANCIAL_REPORT,
        "medical_info": ContentType.MEDICAL_INFO,
        "medical": ContentType.MEDICAL_INFO,
        "health": ContentType.MEDICAL_INFO,
    }
    return type_map.get(type_lower, ContentType.GENERAL)


def parse_reading_level(level_str: Optional[str]) -> ReadingLevel:
    """Parse reading level string to enum."""
    if not level_str:
        return ReadingLevel.GENERAL_PUBLIC

    level_lower = level_str.lower().strip().replace(" ", "_").replace("-", "_")
    level_map = {
        "elementary": ReadingLevel.ELEMENTARY,
        "5th_grade": ReadingLevel.ELEMENTARY,
        "fifth_grade": ReadingLevel.ELEMENTARY,
        "middle_school": ReadingLevel.MIDDLE_SCHOOL,
        "8th_grade": ReadingLevel.MIDDLE_SCHOOL,
        "eighth_grade": ReadingLevel.MIDDLE_SCHOOL,
        "high_school": ReadingLevel.HIGH_SCHOOL,
        "12th_grade": ReadingLevel.HIGH_SCHOOL,
        "twelfth_grade": ReadingLevel.HIGH_SCHOOL,
        "general_public": ReadingLevel.GENERAL_PUBLIC,
        "general": ReadingLevel.GENERAL_PUBLIC,
        "adult": ReadingLevel.GENERAL_PUBLIC,
    }
    return level_map.get(level_lower, ReadingLevel.GENERAL_PUBLIC)


def get_reading_level_description(level: ReadingLevel) -> str:
    """Get description of reading level for prompts."""
    descriptions = {
        ReadingLevel.ELEMENTARY: (
            "a 5th grader (age 10-11). Use very simple words, short sentences, "
            "and concrete examples. Avoid any technical terms."
        ),
        ReadingLevel.MIDDLE_SCHOOL: (
            "an 8th grader (age 13-14). Use straightforward language with some "
            "complexity allowed. Explain any technical terms simply."
        ),
        ReadingLevel.HIGH_SCHOOL: (
            "a high school student (age 17-18). Use clear language but can include "
            "more nuance. Define specialized terms when first used."
        ),
        ReadingLevel.GENERAL_PUBLIC: (
            "an average adult with no specialized knowledge in this area. "
            "Use everyday language, avoid jargon, and explain concepts clearly."
        ),
    }
    return descriptions.get(level, descriptions[ReadingLevel.GENERAL_PUBLIC])
