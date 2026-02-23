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

import contextlib

from startd8.contractors.protocols import VALIDATE_MODEL_CLAUDE_SONNET
from startd8.contractors.artisan_phases.prompts import get_template, format_prompt
from startd8.utils.retry import RetryConfig, _is_retryable_exception, _calculate_delay

# OTel instrumentation (graceful degradation when unavailable)
try:
    from opentelemetry import trace as _trace
    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False
from startd8.utils.token_usage import token_usage_cost, token_usage_input, token_usage_output


def _get_design_tracer():
    """Lazy tracer for design phase spans."""
    if _HAS_OTEL:
        return _trace.get_tracer("startd8.artisan.design")
    from startd8.contractors.artisan_contractor import _NoOpTracer
    return _NoOpTracer()

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

# Configure logging — uses get_logger() for OTel log bridge attachment (R3-S7)
from startd8.logging_config import get_logger
logger = get_logger(__name__)


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
        prior_design: Existing design document text for the refine path.
        requirements_text: IMP-1 requirements block from the PLAN phase.
        edit_mode_hint: ``"edit"`` when target files already exist,
            ``"create"`` for greenfield, or ``None`` when unclassified.
        existing_target_files: Paths of target files that already exist on
            disk, populated by the SCAFFOLD phase.
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
    requirements_text: str = ""
    edit_mode_hint: str | None = None
    existing_target_files: list[str] = field(default_factory=list)


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
        "NULL", "TYPE", "MUST", "SHALL", "API", "URL", "SDK",
        "CSS", "HTML", "XML", "SQL", "CLI", "TLS", "SSL",
        "REST", "GRPC", "CRUD", "ACID", "BASE",
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
# PROMPT ACCESSORS — single source of truth is prompts/design.yaml
# ============================================================================

_DEFAULT_SECTIONS = [
    "Overview", "Architecture", "Data Model", "API Contracts",
    "Error Handling", "Security Considerations", "Testing Strategy",
]


_VALID_EDIT_MODE_HINTS = frozenset({"edit", "create", None})


def _build_edit_mode_block(
    edit_mode_hint: str | None = None,
    existing_target_files: list[str] | None = None,
) -> str:
    """Build the edit-mode instruction block for design system prompts.

    When ``edit_mode_hint`` is ``"edit"``, returns instructions directing the
    LLM to describe modifications to existing files rather than greenfield
    implementations.  Returns an empty string otherwise (greenfield unchanged).

    Args:
        edit_mode_hint: ``"edit"`` for surgical modifications, ``"create"``
            for greenfield, or ``None`` when unknown.
        existing_target_files: Paths that already exist on disk.

    Returns:
        A multi-line instruction block, or ``""`` when not in edit mode.
    """
    if edit_mode_hint not in _VALID_EDIT_MODE_HINTS:
        logger.debug(
            "Unexpected edit_mode_hint %r — treating as None", edit_mode_hint,
        )
    if edit_mode_hint != "edit" or not existing_target_files:
        return ""
    file_list = "\n".join(f"        - `{f}`" for f in existing_target_files)
    return (
        "\n      Edit-Mode Guidance (IMPORTANT — this task modifies existing code):\n"
        "      - The following target files ALREADY EXIST in the project:\n"
        f"{file_list}\n"
        "      - Describe CHANGES to existing code, not a greenfield implementation.\n"
        "      - In ### Files Touched, use `(modify)` annotations for existing files.\n"
        "      - Focus on what to add, remove, or alter — preserve existing functionality.\n"
        "      - Do NOT rewrite the entire file; specify surgical modifications.\n"
    )


def _format_system_prompt(
    template_name: str,
    sections: list[str] | None = None,
    depth_guidance: str | None = None,
    edit_mode_hint: str | None = None,
    existing_target_files: list[str] | None = None,
) -> str:
    """Load a design system prompt from YAML and format its placeholders.

    Shared implementation for both fresh-design and refine system prompts.

    Args:
        template_name: YAML template key (e.g. ``"design_system"``,
            ``"refine_system"``).
        sections: Section list for the ``{sections_list}`` placeholder.
            Defaults to :data:`_DEFAULT_SECTIONS`.
        depth_guidance: Optional tier-specific scope guidance injected as
            ``{depth_line}``.
        edit_mode_hint: ``"edit"`` to inject surgical-modification guidance,
            any other value (or ``None``) leaves the block empty.
        existing_target_files: Paths of target files that already exist on
            disk — used by the edit-mode block.

    Returns:
        The fully-formatted system prompt string.
    """
    from startd8.contractors.artisan_phases.prompts import get_template

    if sections is None:
        sections = _DEFAULT_SECTIONS
    section_list = "\n".join(f"- ## {s}" for s in sections)

    depth_line = ""
    if depth_guidance:
        depth_line = f"\n\n**Scope guidance:** {depth_guidance}"

    edit_mode_block = _build_edit_mode_block(edit_mode_hint, existing_target_files)

    template = get_template("design", template_name)
    return template.format(
        sections_list=section_list,
        depth_line=depth_line,
        edit_mode_block=edit_mode_block,
    )


def build_design_system_prompt(
    sections: list[str] | None = None,
    depth_guidance: str | None = None,
    edit_mode_hint: str | None = None,
    existing_target_files: list[str] | None = None,
) -> str:
    """Build a dynamic system prompt for fresh design generation."""
    return _format_system_prompt(
        "design_system", sections, depth_guidance,
        edit_mode_hint, existing_target_files,
    )


# Backward-compatible constant for code that references it directly
DESIGN_GENERATION_SYSTEM_PROMPT = build_design_system_prompt()

REFINE_DESIGN_USER_PROMPT_TEMPLATE = get_template("design", "refine_user")


def build_refine_system_prompt(
    sections: list[str] | None = None,
    depth_guidance: str | None = None,
    edit_mode_hint: str | None = None,
    existing_target_files: list[str] | None = None,
) -> str:
    """Build a system prompt for refining an existing design document."""
    return _format_system_prompt(
        "refine_system", sections, depth_guidance,
        edit_mode_hint, existing_target_files,
    )


# Backward-compatible prompt constants — single source of truth is design.yaml.
# Internal methods use format_prompt()/get_template() directly.
# format_prompt() resolves {{ → { in YAML templates with escaped braces.
REVIEWER_SYSTEM_PROMPT = format_prompt("design", "reviewer_system")
REVIEWER_USER_PROMPT_TEMPLATE = get_template("design", "reviewer_user")
ARBITER_SYSTEM_PROMPT = format_prompt("design", "arbiter_system")
ARBITER_USER_PROMPT_TEMPLATE = get_template("design", "arbiter_user")
REVISION_SYSTEM_PROMPT = format_prompt("design", "revision_system")
REVISION_USER_PROMPT_TEMPLATE = get_template("design", "revision_user")


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

    def get_model_spec(self) -> str | None:
        """Return the model spec string for forensic logging (OT-714)."""
        return self._agent_spec

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
            if _HAS_OTEL:
                span = _trace.get_current_span()
                if span and span.is_recording():
                    span.add_event("llm.call.start", attributes={
                        "llm.prompt_length": len(prompt),
                        "llm.max_tokens": max_tokens or -1,
                    })
            # Use native system_prompt parameter (all agents support it)
            response_text, response_time_ms, token_usage = await agent.agenerate(
                prompt, system_prompt=system_prompt,
            )
            self.total_input_tokens += token_usage_input(token_usage)
            self.total_output_tokens += token_usage_output(token_usage)
            self.total_cost_usd += token_usage_cost(token_usage)
            if _HAS_OTEL:
                span = _trace.get_current_span()
                if span and span.is_recording():
                    span.add_event("llm.call.complete", attributes={
                        "llm.response_time_ms": response_time_ms,
                        "llm.tokens_input": token_usage_input(token_usage),
                        "llm.tokens_output": token_usage_output(token_usage),
                        "llm.cost_usd": token_usage_cost(token_usage),
                    })
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
    # Forensic log metric helpers
    # ------------------------------------------------------------------

    def _capture_pre_metrics(self) -> tuple[int, int, float]:
        """Snapshot cumulative LLM counters before a call (delta tracking)."""
        return (
            self.llm.total_input_tokens,
            self.llm.total_output_tokens,
            self.llm.total_cost_usd,
        )

    def _build_call_metrics(
        self,
        prompt_length: int,
        pre: tuple[int, int, float],
        *,
        max_tokens: int | None = None,
    ) -> dict:
        """Build the ``call`` section for ``emit_forensic_log()``."""
        pre_input, pre_output, pre_cost = pre
        return {
            "prompt_length": prompt_length,
            "max_tokens": max_tokens,
            "model_spec": self.llm.get_model_spec(),
            "tokens_input": self.llm.total_input_tokens - pre_input,
            "tokens_output": self.llm.total_output_tokens - pre_output,
            "cost_usd": self.llm.total_cost_usd - pre_cost,
        }

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

        # IMP-1: Build requirements block from plan requirements
        requirements_block = ""
        if context.requirements_text:
            requirements_block = (
                "**Requirements (verbatim — authoritative for "
                "parameter details):**\n"
                f"{context.requirements_text}\n\n"
            )

        is_refine = context.prior_design is not None

        # Shared parameters for both fresh and refine user prompts
        prompt_params = dict(
            feature_name=context.feature_name,
            description=context.description,
            target_file=context.target_file,
            constraints=constraints_str,
            additional_context=additional_context_str,
            requirements_block=requirements_block,
            revision_guidance=revision_guidance,
        )

        if is_refine:
            prompt_params["prior_design"] = context.prior_design
            prompt = format_prompt("design", "refine_user", **prompt_params)
            system_prompt = build_refine_system_prompt(
                context.sections,
                depth_guidance=context.depth_guidance,
                edit_mode_hint=context.edit_mode_hint,
                existing_target_files=context.existing_target_files,
            )
            logger.info(
                "Refining existing design document for '%s' (iteration %d)",
                context.feature_name,
                iteration,
            )
        else:
            prompt = format_prompt("design", "design_user", **prompt_params)
            system_prompt = build_design_system_prompt(
                context.sections,
                depth_guidance=context.depth_guidance,
                edit_mode_hint=context.edit_mode_hint,
                existing_target_files=context.existing_target_files,
            )
            logger.info(
                "Generating design document for '%s' (iteration %d)",
                context.feature_name,
                iteration,
            )

        _tracer = _get_design_tracer()
        with _tracer.start_as_current_span(
            "design.generate",
            attributes={
                "design.feature_name": context.feature_name,
                "design.iteration": iteration,
                "design.is_refine": context.prior_design is not None,
            },
        ):
            # Delta tracking for per-call token/cost accuracy (R2-S5)
            _pre = self._capture_pre_metrics()
            raw_text = await self.llm.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=context.max_output_tokens,
            )
            # CS1: Forensic log for design.generate
            from startd8.contractors.forensic_log import emit_forensic_log
            emit_forensic_log(
                call_type="design.generate",
                call=self._build_call_metrics(
                    len(prompt), _pre, max_tokens=context.max_output_tokens,
                ),
                task={
                    "task_id": None,
                    "title": context.feature_name,
                    "domain": None,
                    "feature_id": context.feature_name,
                    "phase": "design",
                    "target_files": [context.target_file] if context.target_file else None,
                },
                context_propagation={
                    "design_calibration_present": bool(context.sections),
                    "depth_tier": context.depth_guidance,
                    "prompt_constraints_count": len(context.constraints) if context.constraints else 0,
                    "environment_checks_count": len(context.environment_checks) if getattr(context, "environment_checks", None) else None,
                    "design_doc_present": context.prior_design is not None,
                    "design_doc_line_count": len(context.prior_design.splitlines()) if context.prior_design else None,
                },
                provenance={
                    "iteration": iteration,
                    "prior_design_available": context.prior_design is not None,
                },
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
        role_key = "reviewer" if role == ReviewRole.REVIEWER else "arbiter"

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

        system_prompt = format_prompt("design", f"{role_key}_system")
        prompt = format_prompt(
            "design", f"{role_key}_user",
            design_document=design.raw_text,
            project_context=project_context,
        )

        logger.info(
            "Requesting %s review for '%s' (iteration %d)",
            role.value,
            design.feature_name,
            design.iteration,
        )

        _tracer = _get_design_tracer()
        with _tracer.start_as_current_span(
            f"design.review.{role.value}",
            attributes={
                "design.review_role": role.value,
                "design.iteration": design.iteration,
            },
        ):
            _pre = self._capture_pre_metrics()
            raw_text = await self.llm.generate(
                prompt=prompt,
                system_prompt=system_prompt,
            )
            # CS2: Forensic log for design.review
            from startd8.contractors.forensic_log import emit_forensic_log
            emit_forensic_log(
                call_type="design.review",
                call=self._build_call_metrics(len(prompt), _pre),
                task={
                    "title": design.feature_name,
                    "phase": "design",
                },
                context_propagation={
                    "design_calibration_present": True,
                    "design_doc_present": True,
                    "design_doc_line_count": len(design.raw_text.splitlines()) if design.raw_text else 0,
                },
                provenance={
                    "iteration": design.iteration,
                    "reviewer_verdict": role.value,
                },
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

        prompt = format_prompt(
            "design", "revision_user",
            original_document=design.raw_text,
            review_feedback=review_feedback,
            guidance=guidance,
        )

        logger.info(
            "Revising design document for '%s' (iteration %d)",
            design.feature_name,
            iteration,
        )

        _tracer = _get_design_tracer()
        with _tracer.start_as_current_span(
            "design.revision",
            attributes={"design.iteration": iteration},
        ):
            _pre = self._capture_pre_metrics()
            raw_text = await self.llm.generate(
                prompt=prompt,
                system_prompt=format_prompt("design", "revision_system"),
            )
            # CS3: Forensic log for design.revise
            from startd8.contractors.forensic_log import emit_forensic_log
            emit_forensic_log(
                call_type="design.revise",
                call=self._build_call_metrics(len(prompt), _pre),
                task={
                    "title": design.feature_name,
                    "phase": "design",
                },
                context_propagation={
                    "design_calibration_present": True,
                    "design_doc_present": True,
                    "design_doc_line_count": len(design.raw_text.splitlines()) if design.raw_text else 0,
                },
                provenance={
                    "iteration": iteration,
                    "reviewer_verdict": reviewer.summary if reviewer else None,
                    "arbiter_verdict": arbiter.summary if arbiter else None,
                },
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

        _tracer = _get_design_tracer()
        for iteration in range(1, self.max_iterations + 1):
            _iter_span_cm = _tracer.start_as_current_span(
                f"design.iteration.{iteration}",
                attributes={"design.iteration": iteration},
            )
            _iter_span_cm.__enter__()
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
            finally:
                _iter_span_cm.__exit__(None, None, None)

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
