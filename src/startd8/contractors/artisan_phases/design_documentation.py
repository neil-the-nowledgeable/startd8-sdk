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

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from startd8.contractors.protocols import VALIDATE_MODEL_CLAUDE_SONNET
from startd8.utils.retry import RetryConfig, _is_retryable_exception, _calculate_delay
from startd8.utils.token_usage import token_usage_cost, token_usage_input, token_usage_output

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
    # Concrete implementations
    "AgentLLMBackend",
    "AutoResolutionCallback",
    "DesignDocumentationPhase",
    # Utility functions
    "extract_critical_parameters",
    "check_design_parameter_fidelity",
    "parse_design_document",
    "parse_review_verdict",
    "build_design_system_prompt",
    "build_refine_system_prompt",
    "REFINE_DESIGN_USER_PROMPT_TEMPLATE",
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
        sections: Calibrated section list (None = all 7 default sections).
        max_output_tokens: Output token cap (None = provider default).
        depth_guidance: Tier-specific guidance for system prompt.
    """

    feature_name: str
    description: str
    target_file: str
    constraints: list[str] = field(default_factory=list)
    additional_context: dict[str, Any] = field(default_factory=dict)
    sections: list[str] | None = None
    max_output_tokens: int | None = None
    depth_guidance: str | None = None
    prior_design: str | None = None
    # IMP-1: Verbatim requirements text from plan
    requirements_text: str = ""


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
# PARAMETER EXTRACTION UTILITIES
# ============================================================================


def extract_critical_parameters(design_text: str) -> list[dict[str, Any]]:
    """Extract critical implementation parameters from a design document.

    Scans the design document for parameter-like declarations that downstream
    IMPLEMENT phase must preserve (e.g., port numbers, buffer sizes, timeout values,
    function signatures, environment variable names).

    Returns:
        List of dicts with keys: name, value, section, confidence.
    """
    parameters: list[dict[str, Any]] = []

    # Pattern: Port numbers
    port_re = re.compile(r"\bport\s*[:=]\s*(\d{2,5})\b", re.IGNORECASE)
    # Pattern: Environment variable references
    env_re = re.compile(r"\b([A-Z][A-Z0-9_]{2,})\b")
    # Pattern: Function/method signatures
    sig_re = re.compile(r"(?:def|func|function)\s+(\w+)\s*\([^)]*\)")

    _common_words = {
        "THE", "AND", "FOR", "NOT", "ARE", "BUT", "THIS", "THAT",
        "WITH", "FROM", "HAVE", "WILL", "TODO", "FIXME", "NOTE",
        "HTTP", "HTTPS", "JSON", "YAML", "TRUE", "FALSE", "NONE",
        "NULL", "TYPE", "MUST", "SHALL",
    }
    seen_names: set[str] = set()

    # Extract ports
    for m in port_re.finditer(design_text):
        name = f"port:{m.group(1)}"
        if name not in seen_names:
            seen_names.add(name)
            parameters.append({
                "name": name,
                "value": m.group(1),
                "section": "configuration",
                "confidence": 0.9,
            })

    # Extract environment variables (underscored UPPER_CASE names)
    for m in env_re.finditer(design_text):
        name = m.group(1)
        if name not in seen_names and name not in _common_words and len(name) >= 4:
            if "_" in name:
                seen_names.add(name)
                parameters.append({
                    "name": name,
                    "value": name,
                    "section": "environment",
                    "confidence": 0.7,
                })

    # Extract function signatures
    for m in sig_re.finditer(design_text):
        name = f"fn:{m.group(1)}"
        if name not in seen_names:
            seen_names.add(name)
            parameters.append({
                "name": name,
                "value": m.group(0),
                "section": "api",
                "confidence": 0.85,
            })

    return parameters


def check_design_parameter_fidelity(
    design_parameters: list[dict[str, Any]],
    generated_code: str,
) -> list[dict[str, Any]]:
    """Check whether critical parameters from design doc survive in generated code.

    Compares parameters extracted by extract_critical_parameters() against
    the generated implementation to detect parameter drift.

    Returns:
        List of fidelity issue dicts with keys: parameter, status, confidence.
        status is one of: "present", "missing", "modified".
    """
    issues: list[dict[str, Any]] = []
    code_lower = generated_code.lower()

    for param in design_parameters:
        name = param.get("name", "")
        value = param.get("value", "")
        section = param.get("section", "")
        confidence = param.get("confidence", 0.5)

        if name.startswith("port:"):
            port_val = value
            status = "present" if port_val in generated_code else "missing"
            if status == "missing":
                confidence = min(confidence, 0.8)
        elif name.startswith("fn:"):
            fn_name = name[3:]
            status = "present" if fn_name in generated_code else "missing"
        elif section == "environment":
            if name in generated_code:
                status = "present"
            elif name.lower() in code_lower:
                status = "modified"
                confidence = min(confidence, 0.6)
            else:
                status = "missing"
        else:
            if value and value in generated_code:
                status = "present"
            elif name in generated_code:
                status = "present"
            else:
                status = "missing"
                confidence = min(confidence, 0.6)

        if status != "present":
            issues.append({
                "parameter": name,
                "expected_value": value,
                "status": status,
                "section": section,
                "confidence": confidence,
            })

    return issues


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
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Generate text from the LLM.

        Args:
            prompt: The user prompt.
            system_prompt: Optional system prompt to set context.
            max_tokens: Optional output token limit override.

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

_DEFAULT_SECTIONS = [
    "Overview", "Architecture", "Data Model", "API Contracts",
    "Error Handling", "Security Considerations", "Testing Strategy",
]


def build_design_system_prompt(
    sections: list[str] | None = None,
    depth_guidance: str | None = None,
) -> str:
    """Build a dynamic system prompt with calibrated section list.

    Loads the template from design.yaml and injects sections_list and depth_line.
    """
    from startd8.contractors.artisan_phases.prompts import get_template

    if sections is None:
        sections = _DEFAULT_SECTIONS
    section_list = "\n".join(f"- ## {s}" for s in sections)

    depth_line = ""
    if depth_guidance:
        depth_line = f"\n\n**Scope guidance:** {depth_guidance}"

    template = get_template("design", "design_system")
    return template.format(sections_list=section_list, depth_line=depth_line)


# Backward-compatible constant for code that references it directly
DESIGN_GENERATION_SYSTEM_PROMPT = build_design_system_prompt()

DESIGN_GENERATION_USER_PROMPT_TEMPLATE = (
    "Generate a design document for the following feature:\n\n"
    "**Feature Name:** {feature_name}\n\n"
    "**Description:** {description}\n\n"
    "**Target File:** {target_file}\n\n"
    "**Constraints:** {constraints}\n\n"
    "**Additional Context:** {additional_context}\n\n"
    "{revision_guidance}"
)

REFINE_DESIGN_USER_PROMPT_TEMPLATE = (
    "Refine and improve the following existing design document for this feature.\n\n"
    "**Feature Name:** {feature_name}\n\n"
    "**Description:** {description}\n\n"
    "**Target File:** {target_file}\n\n"
    "**Constraints:** {constraints}\n\n"
    "**Additional Context:** {additional_context}\n\n"
    "---\n\n"
    "**Existing Design Document (to refine):**\n\n"
    "{prior_design}\n\n"
    "---\n\n"
    "**Refinement Instructions:**\n"
    "- Preserve sections and decisions that are still valid.\n"
    "- Improve specificity, correctness, and completeness.\n"
    "- Address any gaps, ambiguities, or inconsistencies.\n"
    "- Update sections that conflict with the constraints or additional context above.\n"
    "- Maintain the same section structure (## headers).\n\n"
    "{revision_guidance}"
)


def build_refine_system_prompt(
    sections: list[str] | None = None,
    depth_guidance: str | None = None,
) -> str:
    """Build a system prompt for refining an existing design document.

    Loads the template from design.yaml and injects sections_list and depth_line.
    """
    from startd8.contractors.artisan_phases.prompts import get_template

    if sections is None:
        sections = _DEFAULT_SECTIONS
    section_list = "\n".join(f"- ## {s}" for s in sections)

    depth_line = ""
    if depth_guidance:
        depth_line = f"\n\n**Scope guidance:** {depth_guidance}"

    template = get_template("design", "refine_system")
    return template.format(sections_list=section_list, depth_line=depth_line)


_REVIEW_JSON_SCHEMA = (
    "{{\n"
    '    "approved": true or false,\n'
    '    "confidence": 0.0 to 1.0,\n'
    '    "concerns": ["concern1", "concern2", ...],\n'
    '    "suggestions": ["suggestion1", "suggestion2", ...],\n'
    '    "summary": "Brief summary of your review"\n'
    "}}"
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
    "{project_context}"
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
    "{project_context}"
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
    "Output the revised design document preserving all existing sections."
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
# FEEDBACK TRUNCATION LIMITS
# ============================================================================

_REVIEWER_FEEDBACK_LIMIT = 3
_MERGED_FEEDBACK_LIMIT = 5


# ============================================================================
# PARSING UTILITIES
# ============================================================================


def parse_design_document(
    raw_text: str,
    feature_name: str,
    iteration: int,
    *,
    expected_sections: list[str] | None = None,
) -> DesignDocument:
    """Parse a raw design document string into a ``DesignDocument``.

    Extracts sections based on markdown ``## <Section Name>`` headers.
    Missing sections are filled with a placeholder. A warning is logged only
    for sections in ``expected_sections`` (or all DesignSection values when
    ``expected_sections`` is None).

    When the context seed provides a calibrated section list (e.g., reduced
    sections for a simpler task), pass it as ``expected_sections`` to avoid
    noisy warnings for intentionally omitted sections.

    Args:
        raw_text: The raw design document text from the LLM.
        feature_name: Name of the feature.
        iteration: Current iteration number.
        expected_sections: Section names to validate and warn about if missing.
            None = validate all DesignSection values (legacy behavior).

    Returns:
        A ``DesignDocument`` instance with all sections populated.
    """
    sections: dict[DesignSection, str] = {}
    placeholder = "[Section not generated — requires manual input]"

    # Determine which sections to validate (and warn on missing)
    if expected_sections is not None:
        section_names_to_check = expected_sections
    else:
        section_names_to_check = [s.value for s in DesignSection]

    # Build name -> DesignSection mapping for lookup
    name_to_section = {s.value: s for s in DesignSection}

    for section_name in section_names_to_check:
        section = name_to_section.get(section_name)
        if section is None:
            continue  # Unknown section name, skip
        pattern = rf"##\s*{re.escape(section_name)}\s*\n(.*?)(?=##\s|\Z)"
        match = re.search(pattern, raw_text, re.IGNORECASE | re.DOTALL)

        if match and match.group(1).strip():
            sections[section] = match.group(1).strip()
        else:
            sections[section] = placeholder
            logger.warning(
                "Design document missing section '%s' in iteration %d",
                section_name,
                iteration,
            )

    # Fill any remaining DesignSection values not yet populated (no warning)
    for section in DesignSection:
        if section not in sections:
            pattern = rf"##\s*{re.escape(section.value)}\s*\n(.*?)(?=##\s|\Z)"
            match = re.search(pattern, raw_text, re.IGNORECASE | re.DOTALL)
            sections[section] = (
                match.group(1).strip() if match and match.group(1).strip() else placeholder
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
    # Strip markdown fences if the LLM wrapped JSON in ```json ... ```
    cleaned = raw_text.strip()
    fence_pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
    fence_match = re.search(fence_pattern, cleaned, re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    # Try strict JSON parsing first
    try:
        data = json.loads(cleaned)
        return ReviewVerdict(
            role=role,
            approved=bool(data.get("approved", False)),
            confidence=float(data.get("confidence", 0.0)),
            concerns=[str(c) for c in data.get("concerns", [])],
            suggestions=[str(s) for s in data.get("suggestions", [])],
            summary=str(data.get("summary", "")),
            reviewed_at=datetime.now(timezone.utc),
        )
    except (json.JSONDecodeError, ValueError, TypeError):
        logger.warning(
            "Failed to parse review verdict as JSON for role %s, "
            "attempting regex fallback",
            role.value,
        )

    # Regex fallback for partial recovery
    approved = False
    approved_match = re.search(
        r'"approved"\s*:\s*(true|false)', cleaned, re.IGNORECASE
    )
    if approved_match:
        approved = approved_match.group(1).lower() == "true"

    confidence = 0.0
    conf_match = re.search(r'"confidence"\s*:\s*([\d.]+)', cleaned)
    if conf_match:
        try:
            confidence = float(conf_match.group(1))
        except ValueError:
            pass

    summary = ""
    summary_match = re.search(r'"summary"\s*:\s*"((?:[^"\\]|\\.)*)"', cleaned)
    if summary_match:
        summary = summary_match.group(1).replace('\\\\', '\\').replace('\\"', '"')

    # Extract list items via regex
    concerns_match = re.search(
        r'"concerns"\s*:\s*\[(.*?)\]', cleaned, re.DOTALL
    )
    if concerns_match:
        concern_list: list[str] = [
            c.replace('\\\\', '\\').replace('\\"', '"')
            for c in re.findall(r'"((?:[^"\\]|\\.)*)"', concerns_match.group(1))
            if c.strip()
        ]
    else:
        concern_list: list[str] = []

    suggestions_match = re.search(
        r'"suggestions"\s*:\s*\[(.*?)\]', cleaned, re.DOTALL
    )
    if suggestions_match:
        suggestion_list: list[str] = [
            s.replace('\\\\', '\\').replace('\\"', '"')
            for s in re.findall(r'"((?:[^"\\]|\\.)*)"', suggestions_match.group(1))
            if s.strip()
        ]
    else:
        suggestion_list: list[str] = []

    return ReviewVerdict(
        role=role,
        approved=approved,
        confidence=confidence,
        concerns=concern_list,
        suggestions=suggestion_list,
        summary=summary or f"[Parsed via regex fallback for {role.value}]",
        reviewed_at=datetime.now(timezone.utc),
    )


# ============================================================================
# CONCRETE LLM BACKEND ADAPTER
# ============================================================================


class AgentLLMBackend:
    """Concrete ``LLMBackend`` adapter wrapping a startd8 ``BaseAgent``.

    Bridges the ``LLMBackend`` protocol (async ``generate(prompt, system_prompt)``)
    to the SDK's ``BaseAgent.agenerate(prompt)`` interface.

    Because ``BaseAgent.agenerate`` does not natively accept a separate
    ``system_prompt`` parameter, this adapter prepends the system prompt to
    the user prompt with a clear separator.

    Usage::

        backend = AgentLLMBackend(VALIDATE_MODEL_CLAUDE_SONNET.agent_spec)
        text = await backend.generate(
            "Write a design doc",
            system_prompt="You are an architect",
        )

    Args:
        agent_spec: Agent specification string (e.g.
            ``VALIDATE_MODEL_CLAUDE_SONNET.agent_spec``).  Ignored when
            *agent* is provided.
        agent: Pre-built ``BaseAgent`` instance.  Takes precedence over
            *agent_spec* when both are supplied.
        **agent_kwargs: Additional keyword arguments forwarded to
            ``resolve_agent_spec`` (e.g. ``max_tokens``).
    """

    def __init__(
        self,
        agent_spec: str | None = None,
        agent: Any = None,
        **agent_kwargs: Any,
    ) -> None:
        if agent is None and agent_spec is None:
            raise ValueError("Either agent_spec or agent must be provided")
        self._agent = agent
        self._agent_spec = agent_spec
        self._agent_kwargs = agent_kwargs
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.total_cost_usd: float = 0.0

    def _resolve_agent(self) -> Any:
        """Lazily resolve the agent from its spec string."""
        if self._agent is not None:
            return self._agent

        from startd8.utils.agent_resolution import resolve_agent_spec

        self._agent = resolve_agent_spec(
            self._agent_spec,  # type: ignore[arg-type]
            **self._agent_kwargs,
        )
        return self._agent

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Generate text from the LLM.

        Satisfies the ``LLMBackend`` protocol.

        Uses the native ``system_prompt`` parameter supported by all agent
        types (claude, openai, gemini, mock).

        Args:
            prompt: The user prompt.
            system_prompt: Optional system prompt to set context.
            max_tokens: Optional output token limit override.

        Returns:
            Generated text from the LLM.
        """
        agent = self._resolve_agent()

        # Temporarily override max_tokens if calibrated
        original_max = getattr(agent, "max_tokens", None)
        if max_tokens is not None and hasattr(agent, "max_tokens"):
            agent.max_tokens = max_tokens
        try:
            # Use native system_prompt parameter (all agents support it)
            response_text, response_time_ms, token_usage = await agent.agenerate(
                prompt, system_prompt=system_prompt,
            )
            self.total_input_tokens += token_usage_input(token_usage)
            self.total_output_tokens += token_usage_output(token_usage)
            self.total_cost_usd += token_usage_cost(token_usage)
            return response_text
        finally:
            if max_tokens is not None and original_max is not None:
                agent.max_tokens = original_max


# ============================================================================
# DEFAULT RESOLUTION CALLBACK
# ============================================================================


class AutoResolutionCallback:
    """Default auto-resolution callback for disagreement escalations.

    Resolves disagreements based on confidence scores and a simple heuristic:

    - If both reviewers have very low confidence → recommend re-review.
    - If one reviewer has significantly higher confidence → accept theirs.
    - Otherwise → merge both sets of feedback.

    This class satisfies the ``ResolutionCallback`` protocol.

    Args:
        confidence_gap_threshold: Minimum confidence difference to prefer
            one reviewer over the other (default ``0.2``).
        min_confidence: Below this threshold for *both* reviewers, recommend
            re-review (default ``0.3``).
    """

    def __init__(
        self,
        confidence_gap_threshold: float = 0.2,
        min_confidence: float = 0.3,
    ) -> None:
        self.confidence_gap_threshold = confidence_gap_threshold
        self.min_confidence = min_confidence

    async def resolve(
        self, escalation_report: EscalationReport
    ) -> ResolutionDecision:
        """Auto-resolve a disagreement escalation.

        Args:
            escalation_report: The escalation report with disagreement details.

        Returns:
            A ``ResolutionDecision``.
        """
        reviewer = escalation_report.reviewer_verdict
        arbiter = escalation_report.arbiter_verdict

        # Both very low confidence → re-review
        if (
            reviewer.confidence < self.min_confidence
            and arbiter.confidence < self.min_confidence
        ):
            return ResolutionDecision(
                action=ResolutionAction.RE_REVIEW,
                guidance=(
                    "Both reviewers have low confidence. Re-generate and "
                    "re-review the design document with additional context."
                ),
                decided_by="auto",
                decided_at=datetime.now(timezone.utc),
            )

        gap = reviewer.confidence - arbiter.confidence

        if gap >= self.confidence_gap_threshold:
            return ResolutionDecision(
                action=ResolutionAction.ACCEPT_REVIEWER,
                guidance=(
                    f"Reviewer confidence ({reviewer.confidence:.2f}) is "
                    f"significantly higher than Arbiter "
                    f"({arbiter.confidence:.2f}). Accepting Reviewer verdict. "
                    f"Arbiter concerns to note: "
                    f"{'; '.join(arbiter.concerns[:_REVIEWER_FEEDBACK_LIMIT]) or 'none'}."
                ),
                decided_by="auto",
                decided_at=datetime.now(timezone.utc),
            )

        if gap <= -self.confidence_gap_threshold:
            return ResolutionDecision(
                action=ResolutionAction.ACCEPT_ARBITER,
                guidance=(
                    f"Arbiter confidence ({arbiter.confidence:.2f}) is "
                    f"significantly higher than Reviewer "
                    f"({reviewer.confidence:.2f}). Accepting Arbiter verdict. "
                    f"Reviewer concerns to note: "
                    f"{'; '.join(reviewer.concerns[:_REVIEWER_FEEDBACK_LIMIT]) or 'none'}."
                ),
                decided_by="auto",
                decided_at=datetime.now(timezone.utc),
            )

        # Close confidence → merge
        all_concerns = list(
            dict.fromkeys(reviewer.concerns + arbiter.concerns)
        )
        all_suggestions = list(
            dict.fromkeys(reviewer.suggestions + arbiter.suggestions)
        )
        return ResolutionDecision(
            action=ResolutionAction.MERGE,
            guidance=(
                f"Confidence is comparable (Reviewer: {reviewer.confidence:.2f}"
                f", Arbiter: {arbiter.confidence:.2f}). Merging feedback. "
                f"Combined concerns: "
                f"{'; '.join(all_concerns[:_MERGED_FEEDBACK_LIMIT]) or 'none'}. "
                f"Suggestions: "
                f"{'; '.join(all_suggestions[:_MERGED_FEEDBACK_LIMIT]) or 'none'}."
            ),
            decided_by="auto",
            decided_at=datetime.now(timezone.utc),
        )


# ============================================================================
# DESIGN DOCUMENTATION PHASE ORCHESTRATOR
# ============================================================================


class DesignDocumentationPhase:
    """Orchestrates the complete design documentation workflow.

    Pipeline:

    1. **Generate** — produce a design document from a ``FeatureContext``.
    2. **Dual Review** — two independent personas (Reviewer and Arbiter)
       evaluate the design and return JSON verdicts.
    3. **Disagreement Detection** — if the verdicts conflict on approval,
       confidence, or concerns, disagreements are classified.
    4. **Escalation & Resolution** — disagreements produce an
       ``EscalationReport``.  A ``ResolutionCallback`` (auto or
       human-in-the-loop) decides how to proceed.
    5. **Revision** — the design is revised incorporating review feedback
       and the cycle repeats.
    6. **Convergence** — the loop ends when both reviewers agree *or*
       ``max_iterations`` is reached.

    Args:
        llm: An ``LLMBackend`` implementation for text generation.
        max_iterations: Maximum generate→review cycles (default ``3``).
        confidence_threshold: Minimum confidence gap to flag divergence
            (default ``0.3``).
        resolution_callback: Optional callback for resolving disagreements.
            Defaults to ``AutoResolutionCallback()``.

    Usage::

        llm = AgentLLMBackend(VALIDATE_MODEL_CLAUDE_SONNET.agent_spec)
        phase = DesignDocumentationPhase(llm=llm, max_iterations=3)
        context = FeatureContext(
            feature_name="User Auth",
            description="OAuth2 login flow",
            target_file="src/auth.py",
        )
        result = await phase.run(context)
        print(result.agreed, result.iterations)
    """

    def __init__(
        self,
        llm: LLMBackend,
        max_iterations: int = 3,
        confidence_threshold: float = 0.3,
        resolution_callback: ResolutionCallback | None = None,
    ) -> None:
        self.llm = llm
        self.max_iterations = max_iterations
        self.confidence_threshold = confidence_threshold
        if not (0.0 <= confidence_threshold <= 1.0):
            raise ValueError(f"confidence_threshold must be in [0.0, 1.0], got {confidence_threshold}")
        # NOTE: This threshold detects disagreements (higher = fewer flagged).
        # AutoResolutionCallback.confidence_gap_threshold (default 0.2) is
        # a *separate* threshold used to decide which reviewer to trust when
        # a disagreement is escalated.  The gap intentionally:
        #   detection (0.3) > resolution (0.2)
        # so disagreements are escalated conservatively but resolved decisively.
        self.resolution_callback: ResolutionCallback = (
            resolution_callback or AutoResolutionCallback()
        )

    # ------------------------------------------------------------------
    # Design generation
    # ------------------------------------------------------------------

    async def _generate_design(
        self,
        context: FeatureContext,
        iteration: int,
        revision_guidance: str = "",
    ) -> DesignDocument:
        """Generate (or revise) a design document.

        Args:
            context: The feature context.
            iteration: Current iteration number (1-based).
            revision_guidance: Guidance from a previous review (empty on
                the first pass).

        Returns:
            Parsed ``DesignDocument``.
        """
        # Format additional_context preserving structure for nested values
        if context.additional_context:
            ctx_parts: list[str] = []
            for k, v in context.additional_context.items():
                if isinstance(v, str):
                    ctx_parts.append(f"**{k}:** {v}")
                else:
                    ctx_parts.append(
                        f"**{k}:**\n{json.dumps(v, indent=2, default=str)}"
                    )
            additional_context_str = "\n".join(ctx_parts)
        else:
            additional_context_str = "None"

        from startd8.contractors.artisan_phases.prompts import format_constraints
        constraints_str = (
            format_constraints(context.constraints)
            if context.constraints
            else "None"
        )

        if context.prior_design is not None:
            # Refine mode: pass prior design to LLM for improvement
            prompt = REFINE_DESIGN_USER_PROMPT_TEMPLATE.format(
                feature_name=context.feature_name,
                description=context.description,
                target_file=context.target_file,
                constraints=constraints_str,
                additional_context=additional_context_str,
                prior_design=context.prior_design,
                revision_guidance=revision_guidance,
            )
            logger.info(
                "Refining existing design document for '%s' (iteration %d)",
                context.feature_name,
                iteration,
            )
            system_prompt = build_refine_system_prompt(
                context.sections,
                depth_guidance=context.depth_guidance,
            )
        else:
            # Fresh generation (default)
            prompt = DESIGN_GENERATION_USER_PROMPT_TEMPLATE.format(
                feature_name=context.feature_name,
                description=context.description,
                target_file=context.target_file,
                constraints=constraints_str,
                additional_context=additional_context_str,
                revision_guidance=revision_guidance,
            )
            logger.info(
                "Generating design document for '%s' (iteration %d)",
                context.feature_name,
                iteration,
            )
            system_prompt = build_design_system_prompt(
                context.sections,
                depth_guidance=context.depth_guidance,
            )

        raw_text = await self.llm.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=context.max_output_tokens,
        )
        return parse_design_document(
            raw_text,
            context.feature_name,
            iteration,
            expected_sections=context.sections,
        )

    # ------------------------------------------------------------------
    # Review
    # ------------------------------------------------------------------

    async def _review_design(
        self,
        design: DesignDocument,
        role: ReviewRole,
        feature_context: FeatureContext | None = None,
    ) -> ReviewVerdict:
        """Send a design document to one reviewer persona.

        Args:
            design: The design document to review.
            role: Which reviewer role to use.
            feature_context: Optional context for evidence-anchored review.

        Returns:
            Parsed ``ReviewVerdict``.
        """
        if role == ReviewRole.REVIEWER:
            system_prompt = REVIEWER_SYSTEM_PROMPT
            user_template = REVIEWER_USER_PROMPT_TEMPLATE
        else:
            system_prompt = ARBITER_SYSTEM_PROMPT
            user_template = ARBITER_USER_PROMPT_TEMPLATE

        # Format project context for evidence-anchored review
        project_context = ""
        if feature_context and feature_context.additional_context:
            parts: list[str] = []
            goals = feature_context.additional_context.get("project_goals")
            if goals:
                parts.append(f"**Project Goals:** {goals}")
            constraints = feature_context.constraints
            if constraints:
                parts.append(f"**Constraints:** {'; '.join(constraints)}")
            depth = feature_context.additional_context.get("depth_guidance")
            if depth:
                parts.append(f"**Design Scope:** {depth}")
            doc_hints = feature_context.additional_context.get("design_doc_sections")
            if doc_hints:
                parts.append(
                    f"**Content hints to emphasize:** {', '.join(doc_hints)}"
                )
            if parts:
                project_context = (
                    "**Context for Review:**\n"
                    + "\n".join(parts)
                    + "\n\n"
                )

        prompt = user_template.format(
            design_document=design.raw_text,
            project_context=project_context,
        )

        logger.info(
            "Requesting %s review for '%s' (iteration %d)",
            role.value,
            design.feature_name,
            design.iteration,
        )

        raw_text = await self.llm.generate(
            prompt=prompt,
            system_prompt=system_prompt,
        )
        return parse_review_verdict(raw_text, role)

    # ------------------------------------------------------------------
    # Disagreement detection
    # ------------------------------------------------------------------

    def _detect_disagreements(
        self,
        reviewer: ReviewVerdict,
        arbiter: ReviewVerdict,
    ) -> list[Disagreement]:
        """Detect disagreements between the Reviewer and Arbiter verdicts.

        Checks three axes:

        1. **Approval conflict** — one approved, the other rejected.
        2. **Confidence divergence** — gap exceeds ``confidence_threshold``.
        3. **Conflicting concerns** — completely non-overlapping concern sets
           suggest different evaluation priorities.

        Args:
            reviewer: The Reviewer's verdict.
            arbiter: The Arbiter's verdict.

        Returns:
            List of ``Disagreement`` objects (empty when they agree).
        """
        disagreements: list[Disagreement] = []

        # 1. Approval conflict
        if reviewer.approved != arbiter.approved:
            disagreements.append(
                Disagreement(
                    disagreement_type=DisagreementType.APPROVAL_CONFLICT,
                    description=(
                        f"Reviewer {'approved' if reviewer.approved else 'rejected'}"
                        f" but Arbiter "
                        f"{'approved' if arbiter.approved else 'rejected'}."
                    ),
                    reviewer_position=(
                        f"{'Approved' if reviewer.approved else 'Rejected'} "
                        f"(confidence: {reviewer.confidence:.2f})"
                    ),
                    arbiter_position=(
                        f"{'Approved' if arbiter.approved else 'Rejected'} "
                        f"(confidence: {arbiter.confidence:.2f})"
                    ),
                )
            )

        # 2. Confidence divergence
        confidence_gap = abs(reviewer.confidence - arbiter.confidence)
        if confidence_gap >= self.confidence_threshold:
            disagreements.append(
                Disagreement(
                    disagreement_type=DisagreementType.CONFIDENCE_DIVERGENCE,
                    description=(
                        f"Confidence divergence of {confidence_gap:.2f} "
                        f"(threshold: {self.confidence_threshold:.2f})."
                    ),
                    reviewer_position=(
                        f"Confidence: {reviewer.confidence:.2f}"
                    ),
                    arbiter_position=(
                        f"Confidence: {arbiter.confidence:.2f}"
                    ),
                )
            )

        # 3. Conflicting concerns (non-overlapping sets)
        reviewer_concerns = {c.lower().strip() for c in reviewer.concerns}
        arbiter_concerns = {c.lower().strip() for c in arbiter.concerns}
        if reviewer_concerns and arbiter_concerns:
            overlap = reviewer_concerns & arbiter_concerns
            if (
                not overlap
                and len(reviewer_concerns) >= 2
                and len(arbiter_concerns) >= 2
            ):
                disagreements.append(
                    Disagreement(
                        disagreement_type=DisagreementType.CONFLICTING_CONCERNS,
                        description=(
                            "Reviewers raised completely non-overlapping "
                            "concerns, suggesting different evaluation "
                            "priorities."
                        ),
                        reviewer_position=(
                            f"Concerns: "
                            f"{'; '.join(reviewer.concerns[:3])}"
                        ),
                        arbiter_position=(
                            f"Concerns: "
                            f"{'; '.join(arbiter.concerns[:3])}"
                        ),
                    )
                )

        return disagreements

    # ------------------------------------------------------------------
    # Escalation
    # ------------------------------------------------------------------

    def _build_escalation_report(
        self,
        disagreements: list[Disagreement],
        reviewer: ReviewVerdict,
        arbiter: ReviewVerdict,
    ) -> EscalationReport:
        """Build an escalation report from detected disagreements.

        Determines a recommended action based on the nature of the
        disagreements: approval conflicts recommend *merge*, otherwise
        the higher-confidence reviewer is preferred.

        Args:
            disagreements: Detected disagreement points.
            reviewer: The Reviewer's verdict.
            arbiter: The Arbiter's verdict.

        Returns:
            An ``EscalationReport`` with a recommended action.
        """
        has_approval_conflict = any(
            d.disagreement_type == DisagreementType.APPROVAL_CONFLICT
            for d in disagreements
        )

        if has_approval_conflict:
            recommended = ResolutionAction.MERGE
        elif reviewer.confidence >= arbiter.confidence:
            recommended = ResolutionAction.ACCEPT_REVIEWER
        else:
            recommended = ResolutionAction.ACCEPT_ARBITER

        return EscalationReport(
            disagreements=disagreements,
            reviewer_verdict=reviewer,
            arbiter_verdict=arbiter,
            recommended_action=recommended,
            escalated_at=datetime.now(timezone.utc),
        )

    # ------------------------------------------------------------------
    # Revision
    # ------------------------------------------------------------------

    async def _revise_design(
        self,
        design: DesignDocument,
        reviewer: ReviewVerdict,
        arbiter: ReviewVerdict,
        guidance: str,
        iteration: int,
        *,
        expected_sections: list[str] | None = None,
    ) -> DesignDocument:
        """Revise a design document incorporating review feedback.

        Collects concerns and suggestions from both reviewers, formats
        them into a revision prompt, and asks the LLM to produce an
        updated design.

        Args:
            design: The current design document.
            reviewer: The Reviewer's verdict.
            arbiter: The Arbiter's verdict.
            guidance: Additional guidance from the resolution decision.
            iteration: The new iteration number.
            expected_sections: Section names to validate (same as parse_design_document).

        Returns:
            A revised ``DesignDocument``.
        """
        feedback_parts: list[str] = []
        if reviewer.concerns:
            feedback_parts.append(
                f"**Reviewer concerns:** {'; '.join(reviewer.concerns)}"
            )
        if reviewer.suggestions:
            feedback_parts.append(
                f"**Reviewer suggestions:** "
                f"{'; '.join(reviewer.suggestions)}"
            )
        if arbiter.concerns:
            feedback_parts.append(
                f"**Arbiter concerns:** {'; '.join(arbiter.concerns)}"
            )
        if arbiter.suggestions:
            feedback_parts.append(
                f"**Arbiter suggestions:** "
                f"{'; '.join(arbiter.suggestions)}"
            )

        review_feedback = (
            "\n\n".join(feedback_parts) or "No specific feedback."
        )

        prompt = REVISION_USER_PROMPT_TEMPLATE.format(
            original_document=design.raw_text,
            review_feedback=review_feedback,
            guidance=guidance,
        )

        logger.info(
            "Revising design document for '%s' (iteration %d)",
            design.feature_name,
            iteration,
        )

        raw_text = await self.llm.generate(
            prompt=prompt,
            system_prompt=REVISION_SYSTEM_PROMPT,
        )
        return parse_design_document(
            raw_text,
            design.feature_name,
            iteration,
            expected_sections=expected_sections,
        )

    # ------------------------------------------------------------------
    # Main orchestration
    # ------------------------------------------------------------------

    async def run(self, context: FeatureContext) -> DesignDocumentResult:
        """Execute the full design documentation phase.

        Generates a design, runs dual review, handles disagreements via
        escalation and resolution, and iterates until convergence or
        ``max_iterations`` is reached.

        Args:
            context: The feature context to design for.

        Returns:
            A ``DesignDocumentResult`` with the final design and review
            verdicts.

        Raises:
            DesignDocumentationError: If a fatal error occurs during the
                pipeline.
        """
        logger.info(
            "Starting design documentation phase for '%s' "
            "(max %d iterations)",
            context.feature_name,
            self.max_iterations,
        )

        escalation_report: EscalationReport | None = None
        resolution_decision: ResolutionDecision | None = None
        design: DesignDocument | None = None
        reviewer_verdict: ReviewVerdict | None = None
        arbiter_verdict: ReviewVerdict | None = None

        for iteration in range(1, self.max_iterations + 1):
            try:
                # --- Generate or revise ---
                revision_guidance = ""
                if resolution_decision is not None:
                    revision_guidance = (
                        f"Previous review resolution "
                        f"({resolution_decision.action.value}): "
                        f"{resolution_decision.guidance}"
                    )

                design = await self._generate_design(
                    context, iteration, revision_guidance
                )

                # --- Dual review (with project context for evidence-anchored review) ---
                reviewer_verdict = await self._review_design(
                    design, ReviewRole.REVIEWER, feature_context=context
                )
                arbiter_verdict = await self._review_design(
                    design, ReviewRole.ARBITER, feature_context=context
                )

                # --- Check agreement ---
                disagreements = self._detect_disagreements(
                    reviewer_verdict, arbiter_verdict
                )

                if not disagreements:
                    logger.info(
                        "Design for '%s' converged at iteration %d "
                        "(both reviewers agree)",
                        context.feature_name,
                        iteration,
                    )
                    return DesignDocumentResult(
                        design_document=design,
                        reviewer_verdict=reviewer_verdict,
                        arbiter_verdict=arbiter_verdict,
                        escalation_report=None,
                        resolution_decision=None,
                        agreed=True,
                        iterations=iteration,
                        completed_at=datetime.now(timezone.utc),
                    )

                # --- Disagreement detected — escalate ---
                logger.warning(
                    "Disagreement detected for '%s' at iteration %d: "
                    "%d points",
                    context.feature_name,
                    iteration,
                    len(disagreements),
                )

                escalation_report = self._build_escalation_report(
                    disagreements, reviewer_verdict, arbiter_verdict
                )

                resolution_decision = (
                    await self.resolution_callback.resolve(escalation_report)
                )

                logger.info(
                    "Resolution for '%s': %s (decided by %s)",
                    context.feature_name,
                    resolution_decision.action.value,
                    resolution_decision.decided_by,
                )

                # Non-RE_REVIEW resolutions: revise once then return
                if resolution_decision.action != ResolutionAction.RE_REVIEW:
                    actual_iterations = iteration
                    if iteration < self.max_iterations:
                        design = await self._revise_design(
                            design,
                            reviewer_verdict,
                            arbiter_verdict,
                            resolution_decision.guidance,
                            iteration + 1,
                            expected_sections=context.sections,
                        )
                        actual_iterations = iteration + 1

                    return DesignDocumentResult(
                        design_document=design,
                        reviewer_verdict=reviewer_verdict,
                        arbiter_verdict=arbiter_verdict,
                        escalation_report=escalation_report,
                        resolution_decision=resolution_decision,
                        agreed=False,
                        iterations=actual_iterations,
                        completed_at=datetime.now(timezone.utc),
                    )

                # RE_REVIEW — continue to next iteration

            except DesignDocumentationError as exc:
                logger.error("Design documentation phase failed: %s", exc)
                raise
            except Exception as exc:
                # Retry transient API errors (connection, overload) before
                # wrapping in DesignDocumentationError.  Defense-in-depth:
                # the outer handler in context_seed_handlers also retries,
                # but this inner retry prevents wasting a full handler-level
                # attempt on a transient blip mid-iteration.
                _transient_retry_config = RetryConfig(
                    max_attempts=1,
                    base_delay=5.0,
                    max_delay=60.0,
                    retryable_exceptions=(ConnectionError, TimeoutError, OSError),
                    retryable_status_codes=(429, 500, 502, 503, 504, 529),
                )
                if _is_retryable_exception(exc, _transient_retry_config):
                    _delay = _calculate_delay(iteration - 1, _transient_retry_config)
                    logger.warning(
                        "Design iteration %d for '%s' hit transient error, "
                        "retrying in %.1fs: %s",
                        iteration,
                        context.feature_name,
                        _delay,
                        exc,
                    )
                    time.sleep(_delay)
                    continue  # re-enter the iteration loop

                logger.error(
                    "Error in design documentation iteration %d for '%s': %s",
                    iteration,
                    context.feature_name,
                    exc,
                    exc_info=True,
                )
                raise DesignDocumentationError(
                    f"Design documentation failed at iteration "
                    f"{iteration} ({type(exc).__name__}): {exc}"
                ) from exc

        # Max iterations reached without full convergence
        logger.warning(
            "Design for '%s' did not converge after %d iterations",
            context.feature_name,
            self.max_iterations,
        )

        if design is None:
            raise DesignDocumentationError("No design was generated after max iterations")
        if reviewer_verdict is None:
            raise DesignDocumentationError("No reviewer verdict was produced after max iterations")
        if arbiter_verdict is None:
            raise DesignDocumentationError("No arbiter verdict was produced after max iterations")

        return DesignDocumentResult(
            design_document=design,
            reviewer_verdict=reviewer_verdict,
            arbiter_verdict=arbiter_verdict,
            escalation_report=escalation_report,
            resolution_decision=resolution_decision,
            agreed=False,
            iterations=self.max_iterations,
            completed_at=datetime.now(timezone.utc),
        )
