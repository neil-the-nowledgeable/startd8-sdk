"""
Design Documentation Phase: Dual-review design document generation system.

This module implements a comprehensive design document generation and review pipeline
where a feature design is independently reviewed by two personas (Reviewer and Arbiter).
If disagreement is detected, the system escalates and provides interactive resolution.

All operations are async, and the LLM backend is injected via a Protocol, allowing
any LLM provider to be plugged in without coupling.

Usage:
    >>> llm = MyLLMBackend()
    >>> phase = DesignDocumentationPhase(llm=llm, max_iterations=3)
    >>> context = FeatureContext(
    ...     feature_name="User Auth",
    ...     description="OAuth2 login flow",
    ...     target_file="src/auth.py",
    ... )
    >>> result = await phase.run(context)
    >>> print(result.agreed, result.iterations)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol, runtime_checkable

__all__ = [
    # Enums
    "DesignSection",
    "ReviewRole",
    "DisagreementType",
    "ResolutionAction",
    # Exceptions
    "DesignDocumentationError",
    # Data models
    "FeatureContext",
    "DesignDocument",
    "ReviewVerdict",
    "Disagreement",
    "EscalationReport",
    "ResolutionDecision",
    "DesignDocumentResult",
    # Protocols
    "LLMBackend",
    "ResolutionCallback",
    # Utility functions
    "parse_design_document",
    "parse_review_verdict",
]

# Configure logging
logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS
# ============================================================================


class DesignSection(Enum):
    """Sections of a design document."""

    OVERVIEW = "Overview"
    ARCHITECTURE = "Architecture"
    DATA_MODEL = "Data Model"
    API_CONTRACTS = "API Contracts"
    ERROR_HANDLING = "Error Handling"
    SECURITY = "Security Considerations"
    TESTING_STRATEGY = "Testing Strategy"


class ReviewRole(Enum):
    """Role of a reviewer in the dual-review pipeline."""

    REVIEWER = "Reviewer"
    ARBITER = "Arbiter"


class DisagreementType(Enum):
    """Types of disagreement between reviewers."""

    APPROVAL_CONFLICT = "approval_conflict"
    CONFIDENCE_DIVERGENCE = "confidence_divergence"
    CONFLICTING_CONCERNS = "conflicting_concerns"


class ResolutionAction(Enum):
    """Actions available to resolve a disagreement."""

    ACCEPT_REVIEWER = "accept_reviewer"
    ACCEPT_ARBITER = "accept_arbiter"
    MERGE = "merge"
    RE_REVIEW = "re_review"


# ============================================================================
# CUSTOM EXCEPTIONS
# ============================================================================


class DesignDocumentationError(Exception):
    """Base exception for design documentation phase errors."""


# ============================================================================
# DATA MODELS
# ============================================================================


@dataclass
class FeatureContext:
    """Context information for a feature design.

    Attributes:
        feature_name: Human-readable name for the feature.
        description: Detailed description of what the feature does.
        target_file: Primary file path where the feature will be implemented.
        constraints: Technical or business constraints to observe.
        additional_context: Arbitrary key-value pairs for extra context.
    """

    feature_name: str
    description: str
    target_file: str
    constraints: list[str] = field(default_factory=list)
    additional_context: dict[str, Any] = field(default_factory=dict)


@dataclass
class DesignDocument:
    """A generated design document.

    Attributes:
        feature_name: Name of the feature this document covers.
        sections: Mapping of ``DesignSection`` to section content text.
        raw_text: The original, unparsed text returned by the LLM.
        generated_at: UTC timestamp of generation.
        iteration: Which review iteration produced this document.
    """

    feature_name: str
    sections: dict[DesignSection, str]
    raw_text: str
    generated_at: datetime
    iteration: int


@dataclass
class ReviewVerdict:
    """Verdict from a single reviewer.

    Attributes:
        role: Whether this came from the Reviewer or Arbiter.
        approved: True if the reviewer approves the design.
        confidence: Confidence score in [0.0, 1.0].
        concerns: List of concern strings.
        suggestions: List of suggestion strings.
        summary: Brief summary of the review.
        reviewed_at: UTC timestamp of when the review was completed.
    """

    role: ReviewRole
    approved: bool
    confidence: float
    concerns: list[str]
    suggestions: list[str]
    summary: str
    reviewed_at: datetime

    def __post_init__(self) -> None:
        """Clamp confidence to [0.0, 1.0] range."""
        self.confidence = max(0.0, min(1.0, self.confidence))


@dataclass
class Disagreement:
    """A single point of disagreement between reviewers.

    Attributes:
        disagreement_type: Category of the disagreement.
        description: Human-readable description.
        reviewer_position: The Reviewer's position on this point.
        arbiter_position: The Arbiter's position on this point.
    """

    disagreement_type: DisagreementType
    description: str
    reviewer_position: str
    arbiter_position: str


@dataclass
class EscalationReport:
    """Report generated when disagreement is detected between reviewers.

    Attributes:
        disagreements: All detected disagreement points.
        reviewer_verdict: The full Reviewer verdict.
        arbiter_verdict: The full Arbiter verdict.
        recommended_action: System-recommended resolution action.
        escalated_at: UTC timestamp of escalation.
    """

    disagreements: list[Disagreement]
    reviewer_verdict: ReviewVerdict
    arbiter_verdict: ReviewVerdict
    recommended_action: ResolutionAction
    escalated_at: datetime


@dataclass
class ResolutionDecision:
    """Decision made to resolve a disagreement.

    Attributes:
        action: The chosen resolution action.
        guidance: Textual guidance for how to apply the decision.
        decided_by: Identifier of who/what made the decision (e.g. "auto", "human").
        decided_at: UTC timestamp of the decision.
    """

    action: ResolutionAction
    guidance: str
    decided_by: str
    decided_at: datetime


@dataclass
class DesignDocumentResult:
    """Final result of the design documentation phase.

    Attributes:
        design_document: The final (possibly revised) design document.
        reviewer_verdict: The last Reviewer verdict.
        arbiter_verdict: The last Arbiter verdict.
        escalation_report: Escalation report if disagreement occurred, else None.
        resolution_decision: Resolution decision if escalation occurred, else None.
        agreed: Whether the reviewers ultimately agreed.
        iterations: Total number of iterations performed.
        completed_at: UTC timestamp of completion.
    """

    design_document: DesignDocument
    reviewer_verdict: ReviewVerdict
    arbiter_verdict: ReviewVerdict
    escalation_report: EscalationReport | None
    resolution_decision: ResolutionDecision | None
    agreed: bool
    iterations: int
    completed_at: datetime


# ============================================================================
# PROTOCOLS
# ============================================================================


@runtime_checkable
class LLMBackend(Protocol):
    """Protocol for LLM backends.

    Any object that implements an async ``generate`` method with the correct
    signature can serve as the LLM backend — no inheritance required.
    """

    async def generate(
        self, prompt: str, system_prompt: str | None = None
    ) -> str:
        """Generate text from the LLM.

        Args:
            prompt: The user prompt.
            system_prompt: Optional system prompt to set context.

        Returns:
            Generated text from the LLM.
        """
        ...


@runtime_checkable
class ResolutionCallback(Protocol):
    """Protocol for interactive resolution callbacks.

    Implement this to provide custom (e.g. human-in-the-loop) resolution logic.
    """

    async def resolve(self, escalation_report: EscalationReport) -> ResolutionDecision:
        """Resolve a disagreement escalation.

        Args:
            escalation_report: The escalation report with disagreement details.

        Returns:
            A resolution decision.
        """
        ...


# ============================================================================
# PROMPT CONSTANTS
# ============================================================================

DESIGN_GENERATION_SYSTEM_PROMPT = (
    "You are a senior software architect responsible for creating comprehensive "
    "design documents.\n\n"
    "Your output must contain exactly these sections with markdown headers "
    "(## Section Name):\n"
    "- ## Overview\n"
    "- ## Architecture\n"
    "- ## Data Model\n"
    "- ## API Contracts\n"
    "- ## Error Handling\n"
    "- ## Security Considerations\n"
    "- ## Testing Strategy\n\n"
    "Be specific, actionable, and include code snippets where appropriate. "
    "Each section should be thorough and address potential concerns."
)

DESIGN_GENERATION_USER_PROMPT_TEMPLATE = (
    "Generate a comprehensive design document for the following feature:\n\n"
    "**Feature Name:** {feature_name}\n\n"
    "**Description:** {description}\n\n"
    "**Target File:** {target_file}\n\n"
    "**Constraints:** {constraints}\n\n"
    "**Additional Context:** {additional_context}\n\n"
    "{revision_guidance}\n\n"
    "Ensure all 7 sections are present and well-developed."
)

_REVIEW_JSON_SCHEMA = (
    '{{\n'
    '    "approved": true or false,\n'
    '    "confidence": 0.0 to 1.0,\n'
    '    "concerns": ["concern1", "concern2", ...],\n'
    '    "suggestions": ["suggestion1", "suggestion2", ...],\n'
    '    "summary": "Brief summary of your review"\n'
    '}}'
)

REVIEWER_SYSTEM_PROMPT = (
    "You are a senior code reviewer with deep expertise in software design "
    "patterns, correctness, completeness, and best practices.\n\n"
    "Your task is to review the provided design document and produce a JSON "
    f"verdict with the following schema:\n{_REVIEW_JSON_SCHEMA}\n\n"
    "Focus on:\n"
    "- Technical correctness and soundness\n"
    "- Completeness of all required sections\n"
    "- Alignment with established best practices\n"
    "- Missing important considerations\n\n"
    "Output ONLY valid JSON, no additional text."
)

REVIEWER_USER_PROMPT_TEMPLATE = (
    "Review this design document:\n\n"
    "{design_document}\n\n"
    "Provide your verdict as JSON matching the specified schema."
)

ARBITER_SYSTEM_PROMPT = (
    "You are a pragmatic arbiter with expertise in project feasibility, "
    "simplicity, and practical implementation constraints.\n\n"
    "Your task is to review the provided design document and produce a JSON "
    f"verdict with the following schema:\n{_REVIEW_JSON_SCHEMA}\n\n"
    "Focus on:\n"
    "- Feasibility and implementability\n"
    "- Simplicity vs. over-engineering\n"
    "- Alignment with project constraints and timeline\n"
    "- Practical concerns and real-world considerations\n\n"
    "Output ONLY valid JSON, no additional text."
)

ARBITER_USER_PROMPT_TEMPLATE = (
    "Review this design document:\n\n"
    "{design_document}\n\n"
    "Provide your verdict as JSON matching the specified schema."
)

REVISION_SYSTEM_PROMPT = (
    "You are a senior software architect tasked with revising a design document "
    "based on review feedback.\n\n"
    "Incorporate the feedback thoughtfully, addressing concerns while maintaining "
    "the document's core objectives.\n"
    "If feedback seems contradictory, use your best judgment to merge the most "
    "valuable insights.\n\n"
    "Output the revised design document with all 7 sections."
)

REVISION_USER_PROMPT_TEMPLATE = (
    "Original design document:\n\n"
    "{original_document}\n\n"
    "Review feedback to incorporate:\n\n"
    "{review_feedback}\n\n"
    "Additional guidance:\n{guidance}\n\n"
    "Revise the design document to address the feedback."
)


# ============================================================================
# PARSING UTILITIES
# ============================================================================


def parse_design_document(
    raw_text: str, feature_name: str, iteration: int
) -> DesignDocument:
    """Parse a raw design document string into a ``DesignDocument``.

    Extracts sections based on markdown ``## <Section Name>`` headers.
    Missing sections are filled with a placeholder and a warning is logged.

    Args:
        raw_text: The raw design document text from the LLM.
        feature_name: Name of the feature.
        iteration: Current iteration number.

    Returns:
        A ``DesignDocument`` instance with all sections populated.
    """
    sections: dict[DesignSection, str] = {}
    placeholder = "[Section not generated — requires manual input]"

    for section in DesignSection:
        # Match section header (case-insensitive), capture until next header or EOF
        pattern = rf"##\s*{re.escape(section.value)}\s*\n(.*?)(?=##\s|\Z)"
        match = re.search(pattern, raw_text, re.IGNORECASE | re.DOTALL)

        if match and match.group(1).strip():
            sections[section] = match.group(1).strip()
        else:
            sections[section] = placeholder
            logger.warning(
                "Design document missing section '%s' in iteration %d",
                section.value,
                iteration,
            )

    return DesignDocument(
        feature_name=feature_name,
        sections=sections,
        raw_text=raw_text,
        generated_at=datetime.now(timezone.utc),
        iteration=iteration,
    )


def parse_review_verdict(raw_text: str, role: ReviewRole) -> ReviewVerdict:
    """Parse a raw review verdict string into a ``ReviewVerdict``.

    Attempts strict JSON parsing first. On failure, falls back to regex
    extraction for partial recovery. Confidence is clamped to [0.0, 1.0].

    Args:
        raw_text: The raw review verdict text from the LLM.
        role: The reviewer role.

    Returns:
        A ``ReviewVerdict`` instance.
    """
    # Strip markdown fences if the LLM wrapped JSON in