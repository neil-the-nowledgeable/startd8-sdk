"""
PipelineContextStrategy — Strategy pattern for context resolution.

Enables two execution modes within a single workflow loop:
  1. Standalone mode (default): Zero-change, exact current behavior
  2. Pipeline mode: Exploits rich pipeline context to build structured
     prompt sections (IMP-P1 through IMP-P5) with security validation

This module is a shared coordination point exposing a clean public interface
(PipelineContextStrategy, ContextValidator, ValidatorRegistry, section constants)
while maintaining stable internals.
"""

from __future__ import annotations

import json
import re
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence

from .context_formatters import (
    SCOPE_BOUNDARY_INSTRUCTION,
    format_architectural_context,
    format_critical_parameters,
    format_domain_constraints,
    format_plan_context,
    format_project_objectives,
    format_protocol_guidance,
    format_requirements_context,
    format_semantic_conventions,
    wrap_user_content,
)

# forensic_log.emit_forensic_log uses a different schema (OT-700);
# context_resolution uses standard structured logging instead.
# Use get_logger() for OTel Loki bridge attachment [SDK Leg 11 #31].
from ..logging_config import get_logger

logger = get_logger(__name__)

# Pipeline signal keys used for auto-detection (shared with prime_contractor)
PIPELINE_SIGNAL_KEYS: frozenset[str] = frozenset({
    "onboarding_metadata",
    "architectural_context",
    "design_calibration",
})


# ──────────────────────────────────────────────────────────────────────────
# Constants: Section IDs, Validation Parameters, Patterns
# ──────────────────────────────────────────────────────────────────────────

SECTION_IMP_P1 = "IMP-P1"
SECTION_IMP_P2 = "IMP-P2"
SECTION_IMP_P3 = "IMP-P3"
SECTION_IMP_P4 = "IMP-P4"
SECTION_IMP_P5 = "IMP-P5"
SECTION_IMP_P6 = "IMP-P6"  # Phase 4: Forward Contract Bindings

VALID_SECTION_IDS: frozenset[str] = frozenset({
    SECTION_IMP_P1,
    SECTION_IMP_P2,
    SECTION_IMP_P3,
    SECTION_IMP_P4,
    SECTION_IMP_P5,
    SECTION_IMP_P6,
})

MAX_FIELD_LENGTH = 50_000
MAX_PATH_DEPTH = 10
FORBIDDEN_PATH_PATTERNS: tuple[str, ...] = ("../", "..\\", "\x00")
DEFAULT_MODE = "standalone"

# ISO 8601 pattern for timestamp validation in IMP-P4
_ISO8601_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)

# Identifier pattern for pipeline_run_id, generator_id, gate names
_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z0-9_\-.:]{1,256}$")

# Valid context key naming convention
_VALID_KEY_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_.\-]{0,127}$")


class ExecutionMode(str, Enum):
    """Execution mode enumeration."""
    STANDALONE = "standalone"
    PIPELINE = "pipeline"


class SanitizationMode(str, Enum):
    """Controls whether security violations raise or log-and-skip."""
    STRICT = "strict"
    LENIENT = "lenient"


# ──────────────────────────────────────────────────────────────────────────
# Section-to-Field Mapping: Single Source of Truth
# ──────────────────────────────────────────────────────────────────────────

SECTION_FIELD_MAP: dict[str, tuple[str, ...]] = {
    SECTION_IMP_P1: ("onboarding_metadata", "project_name", "project_type"),
    SECTION_IMP_P2: ("architecture", "component_map", "dependencies"),
    SECTION_IMP_P3: ("design_doc", "constraints", "calibration_params"),
    SECTION_IMP_P4: ("generator_id", "timestamp", "pipeline_run_id"),
    SECTION_IMP_P5: ("validators", "post_checks", "gate_requirements"),
    SECTION_IMP_P6: ("forward_contracts",),
}

SECTION_HEADINGS: dict[str, str] = {
    SECTION_IMP_P1: "Onboarding Metadata",
    SECTION_IMP_P2: "Architectural Context",
    SECTION_IMP_P3: "Design Calibration",
    SECTION_IMP_P4: "Generation Provenance",
    SECTION_IMP_P5: "Validation Hookpoints",
    SECTION_IMP_P6: "Interface Contract Bindings",
}

# Startup assertions: verify all section IDs are covered
assert SECTION_FIELD_MAP.keys() == VALID_SECTION_IDS, (
    "SECTION_FIELD_MAP keys must match VALID_SECTION_IDS"
)
assert SECTION_HEADINGS.keys() == VALID_SECTION_IDS, (
    "SECTION_HEADINGS keys must match VALID_SECTION_IDS"
)


# ──────────────────────────────────────────────────────────────────────────
# Custom Exceptions
# ──────────────────────────────────────────────────────────────────────────

class PathTraversalError(ValueError):
    """Raised when context values contain path traversal patterns."""
    pass


class PromptInjectionError(ValueError):
    """Raised when context values contain prompt injection markers."""
    pass


class FieldLengthError(ValueError):
    """Raised when a field value exceeds maximum allowed length."""
    pass


class InvalidKeyError(ValueError):
    """Raised when a context key name is invalid."""
    pass


class RegistryFrozenError(RuntimeError):
    """Raised when attempting to register into a frozen registry."""
    pass


class DuplicateValidatorError(ValueError):
    """Raised when registering a validator with a name that already exists."""
    pass


# ──────────────────────────────────────────────────────────────────────────
# Prompt Injection Pattern Definitions
# ──────────────────────────────────────────────────────────────────────────

# Patterns that indicate prompt injection attempts.
# This is a denylist and inherently incomplete — see defense-in-depth note
# in module docstring. The primary trust boundary should be at the pipeline
# context ingestion point (context_schema validation and upstream input
# sanitization). Prompt templates should employ content-security boundaries
# (delimiter fencing, output validation) to mitigate injection bypassing input checks.
_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"<\s*/?system\s*>", re.IGNORECASE),
    re.compile(r"\bSYSTEM\s*:", re.IGNORECASE),
    re.compile(r"<<\s*(?:END|OVERRIDE|RESET)\b", re.IGNORECASE),
    re.compile(
        r"(?:ignore|forget|disregard)\s+(?:all\s+)?(?:previous|above)\s+instructions",
        re.IGNORECASE,
    ),
)


# ──────────────────────────────────────────────────────────────────────────
# Data Classes: PromptSection, ResolvedContext, ValidationResult
# ──────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PromptSection:
    """Immutable structured prompt section."""
    section_id: str
    heading: str
    content: str
    source_fields: tuple[str, ...] = ()
    is_populated: bool = True

    def __post_init__(self) -> None:
        if self.section_id not in VALID_SECTION_IDS:
            raise ValueError(f"Invalid section_id: {self.section_id}")


@dataclass(frozen=True)
class ValidationResult:
    """Result from a single validator."""
    validator_name: str
    passed: bool
    message: str = ""


@dataclass(frozen=True)
class ResolvedContext:
    """Immutable resolved context with sections and validation results."""
    mode: str
    sections: tuple[PromptSection, ...] = ()
    raw_context: MappingProxyType = field(
        default_factory=lambda: MappingProxyType({})
    )
    is_pipeline: bool = False
    validation_results: tuple[ValidationResult, ...] = ()

    @property
    def populated_sections(self) -> tuple[PromptSection, ...]:
        """Return only sections with populated content."""
        return tuple(s for s in self.sections if s.is_populated)

    @property
    def all_valid(self) -> bool:
        """Return True if all validators passed."""
        return all(v.passed for v in self.validation_results)


# ──────────────────────────────────────────────────────────────────────────
# Security Validation Functions
# ──────────────────────────────────────────────────────────────────────────

def _check_path_traversal(field_name: str, value: str) -> None:
    """Reject values with directory traversal attack patterns."""
    for pattern in FORBIDDEN_PATH_PATTERNS:
        if pattern in value:
            raise PathTraversalError(
                f"Field '{field_name}' contains forbidden path pattern: {pattern!r}"
            )
    # Check path depth for values that look like file paths
    if "/" in value or "\\" in value:
        segments = re.split(r"[/\\]", value)
        segments = [s for s in segments if s]  # Remove empty
        if len(segments) > MAX_PATH_DEPTH:
            raise PathTraversalError(
                f"Field '{field_name}' path depth {len(segments)} exceeds "
                f"maximum {MAX_PATH_DEPTH}"
            )


def _check_prompt_injection(field_name: str, value: str) -> None:
    """Reject values matching known prompt injection patterns."""
    for pattern in _INJECTION_PATTERNS:
        match = pattern.search(value)
        if match:
            raise PromptInjectionError(
                f"Field '{field_name}' matches prompt injection pattern: "
                f"{match.group()!r}"
            )


def _enforce_field_length(field_name: str, value: str) -> None:
    """Enforce maximum field length."""
    if len(value) > MAX_FIELD_LENGTH:
        raise FieldLengthError(
            f"Field '{field_name}' length {len(value)} exceeds "
            f"maximum {MAX_FIELD_LENGTH}"
        )


def _validate_key_name(key: str) -> None:
    """Validate that a context key name matches allowed pattern."""
    if not _VALID_KEY_PATTERN.match(key):
        raise InvalidKeyError(
            f"Context key {key!r} does not match allowed pattern "
            f"^[a-zA-Z_][a-zA-Z0-9_.\\-]{{0,127}}$"
        )


# ──────────────────────────────────────────────────────────────────────────
# Field-Specific Validators
# ──────────────────────────────────────────────────────────────────────────

def _validate_timestamp(field_name: str, value: str) -> str:
    """Validate that a timestamp string conforms to ISO 8601."""
    if not _ISO8601_PATTERN.match(value):
        raise ValueError(
            f"Field '{field_name}' is not a valid ISO 8601 timestamp: {value!r}"
        )
    return value


def _validate_identifier(field_name: str, value: str) -> str:
    """Validate that a value is a well-formed identifier."""
    if not _IDENTIFIER_PATTERN.match(value):
        raise ValueError(
            f"Field '{field_name}' is not a valid identifier: {value!r}"
        )
    return value


def _validate_hookpoint_list(field_name: str, value: Any) -> Any:
    """Validate that hookpoint entries are strings or dicts with 'name' keys."""
    if not isinstance(value, list):
        return value  # Will be serialized as-is
    for i, item in enumerate(value):
        if isinstance(item, dict):
            if "name" not in item:
                raise ValueError(
                    f"Field '{field_name}[{i}]' is a dict but missing required "
                    f"'name' key"
                )
        elif not isinstance(item, str):
            raise ValueError(
                f"Field '{field_name}[{i}]' must be a string or dict, "
                f"got {type(item).__name__}"
            )
    return value


# Per-field validator dispatch.
_FIELD_VALIDATORS: dict[str, Callable[[str, Any], Any]] = {
    "timestamp": _validate_timestamp,
    "generator_id": _validate_identifier,
    "pipeline_run_id": _validate_identifier,
    "validators": _validate_hookpoint_list,
    "post_checks": _validate_hookpoint_list,
    "gate_requirements": _validate_hookpoint_list,
}


# ──────────────────────────────────────────────────────────────────────────
# Value Conversion and Extraction
# ──────────────────────────────────────────────────────────────────────────

def _extract_field_to_str(value: Any) -> str:
    """Convert a field value to its string representation."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, indent=2, default=str)
    except (TypeError, ValueError):
        return str(value)


def _validate_field_value(field_name: str, value: Any) -> str:
    """Validate and convert a field value to its string representation.

    Applies domain-specific validation if a validator is registered for the
    field, then delegates to _extract_field_to_str for string conversion.
    """
    # Apply domain-specific validation if available
    validator = _FIELD_VALIDATORS.get(field_name)
    if validator is not None:
        value = validator(field_name, value)

    # Convert to string representation
    return _extract_field_to_str(value)


def _extract_field(ctx: dict[str, Any], field_name: str) -> str | None:
    """Extract and convert a context field to string, returning None if absent."""
    value = ctx.get(field_name)
    if value is None:
        return None
    return _extract_field_to_str(value)


# ──────────────────────────────────────────────────────────────────────────
# Recursive Sanitization
# ──────────────────────────────────────────────────────────────────────────

def _sanitize_value(field_name: str, value: Any, *, _depth: int = 0) -> Any:
    """Recursively sanitize a context value.

    Applies path traversal, prompt injection, and field length checks to
    all string values found at any nesting depth. Non-string leaves are
    returned as-is.

    A recursion depth limit of 20 prevents stack overflow on pathological input.
    """
    if _depth > 20:
        raise ValueError(
            f"Field '{field_name}' exceeds maximum nesting depth of 20"
        )

    if isinstance(value, str):
        _check_path_traversal(field_name, value)
        _check_prompt_injection(field_name, value)
        _enforce_field_length(field_name, value)
        return value
    elif isinstance(value, dict):
        return {
            k: _sanitize_value(f"{field_name}.{k}", v, _depth=_depth + 1)
            for k, v in value.items()
        }
    elif isinstance(value, (list, tuple)):
        return type(value)(
            _sanitize_value(f"{field_name}[{i}]", item, _depth=_depth + 1)
            for i, item in enumerate(value)
        )
    else:
        # Numeric, bool, None — pass through
        return value


# ──────────────────────────────────────────────────────────────────────────
# Generic Section Builder
# ──────────────────────────────────────────────────────────────────────────

def _build_section(
    section_id: str,
    ctx: dict[str, Any],
) -> PromptSection:
    """Generic section builder driven by SECTION_FIELD_MAP.

    Looks up the field tuple and heading from the canonical maps,
    validates each field, and assembles the PromptSection.
    """
    fields = SECTION_FIELD_MAP[section_id]
    heading = SECTION_HEADINGS[section_id]
    content_parts: list[str] = []

    for f in fields:
        val = ctx.get(f)
        if val is not None:
            validated = _validate_field_value(f, val)
            if validated:  # Skip empty strings
                content_parts.append(f"**{f}**: {validated}")

    if not content_parts:
        return PromptSection(
            section_id=section_id,
            heading=heading,
            content="",
            source_fields=fields,
            is_populated=False,
        )

    return PromptSection(
        section_id=section_id,
        heading=heading,
        content="\n".join(content_parts),
        source_fields=fields,
    )


# Section builder dispatch — all builders use generic helper.
# Double-lambda captures `sid` by value (outer lambda default arg) to avoid
# the classic closure-over-loop-variable bug where all lambdas would share
# the final value of `sid`.
SECTION_BUILDERS: dict[str, Callable[[dict[str, Any]], PromptSection]] = {
    sid: (lambda section_id: lambda ctx: _build_section(section_id, ctx))(sid)
    for sid in sorted(VALID_SECTION_IDS)
}


# ──────────────────────────────────────────────────────────────────────────
# Validator Protocol and Registry
# ──────────────────────────────────────────────────────────────────────────

class ContextValidator(Protocol):
    """Protocol for pluggable context validators."""

    @property
    def name(self) -> str:
        """Return the unique name of this validator."""
        ...

    def validate(
        self, sections: Sequence[PromptSection], context: dict[str, Any]
    ) -> ValidationResult:
        """Validate the given sections and context.

        Should return a ValidationResult with passed=True if validation succeeds,
        False otherwise. Validators that raise are caught and recorded as failures.
        """
        ...


class ValidatorRegistry:
    """Thread-safe, locked-after-init registry for context validators.

    Uses a threading.Lock to ensure that concurrent register() and run_all()
    calls do not race on the frozen flag.
    """

    def __init__(self) -> None:
        self._validators: dict[str, ContextValidator] = {}
        self._frozen = False
        self._lock = threading.Lock()

    def register(self, validator: ContextValidator) -> None:
        """Register a context validator.

        Raises RegistryFrozenError if the registry has been frozen.
        Raises DuplicateValidatorError if a validator with this name already exists.
        """
        with self._lock:
            if self._frozen:
                raise RegistryFrozenError(
                    f"Cannot register '{validator.name}': registry is frozen"
                )
            if validator.name in self._validators:
                raise DuplicateValidatorError(
                    f"Validator '{validator.name}' already registered"
                )
            self._validators[validator.name] = validator

    def freeze(self) -> None:
        """Lock the registry — no further registrations allowed."""
        with self._lock:
            self._frozen = True

    @property
    def is_frozen(self) -> bool:
        """Return True if the registry is frozen."""
        return self._frozen

    @property
    def validator_names(self) -> frozenset[str]:
        """Return the set of registered validator names."""
        return frozenset(self._validators.keys())

    def __len__(self) -> int:
        """Return the number of registered validators."""
        return len(self._validators)

    def __contains__(self, name: str) -> bool:
        """Check if a validator with the given name is registered."""
        return name in self._validators

    def run_all(
        self,
        sections: Sequence[PromptSection],
        context: dict[str, Any],
    ) -> list[ValidationResult]:
        """Execute all registered validators. Auto-freezes on first run.

        Validators that raise exceptions are caught and recorded as failures
        with the exception details in the message.
        """
        with self._lock:
            if not self._frozen:
                self._frozen = True

        results: list[ValidationResult] = []
        for name, validator in self._validators.items():
            try:
                result = validator.validate(sections, context)
                results.append(result)
            except Exception as exc:
                results.append(
                    ValidationResult(
                        validator_name=name,
                        passed=False,
                        message=f"Validator raised: {exc!r}",
                    )
                )
        return results


# ──────────────────────────────────────────────────────────────────────────
# Strategy Classes
# ──────────────────────────────────────────────────────────────────────────

class ContextStrategy(ABC):
    """Abstract base for context resolution strategies.

    Subclasses must implement:
    - mode (property): Return "standalone" or "pipeline"
    - resolve(seed): Resolve seed into structured ResolvedContext (IMP-P sections)
    - resolve_task_context(feature_data, seed_data, ...): Build flat gen_context
      dict for code generation. This is the primary method called per-feature
      by PrimeContractorWorkflow.develop_feature().
    """

    @property
    @abstractmethod
    def mode(self) -> str:
        """Return the execution mode identifier."""
        ...

    @abstractmethod
    def resolve(self, seed: dict[str, Any]) -> ResolvedContext:
        """Resolve seed context into structured output."""
        ...

    @abstractmethod
    def resolve_task_context(
        self,
        feature_data: Dict[str, Any],
        seed_data: Dict[str, Any],
        *,
        domain_constraints: Optional[List[str]] = None,
        output_constraint: Optional[str] = None,
        prior_error_feedback: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build the gen_context dict for a single feature's code generation.

        This extracts the context-building logic from develop_feature() into
        the strategy, allowing standalone and pipeline modes to produce
        different context shapes from the same inputs.

        Args:
            feature_data: Dict with keys: name, id, target_files, description,
                metadata (from FeatureSpec).
            seed_data: Dict with keys: onboarding_metadata, architectural_context,
                design_calibration, plan_document_text, service_metadata.
            domain_constraints: Pre-computed domain constraints from
                DomainChecklist (optional).
            output_constraint: Fallback output constraint template when no
                domain constraints are available (standalone mode).
            prior_error_feedback: Pre-formatted error feedback from a prior
                failed attempt (optional).

        Returns:
            gen_context dict ready for code_generator.generate(context=...).
        """
        ...


class StandaloneContextStrategy(ContextStrategy):
    """Zero-change default — preserves exact current develop_feature() behavior.

    resolve_task_context() reproduces the inline context-building logic from
    PrimeContractorWorkflow.develop_feature() lines 1350-1426 (as of Phase 1).
    This is a pure extraction: same logic, same output, different home.
    """

    @property
    def mode(self) -> str:
        return ExecutionMode.STANDALONE.value

    def resolve(self, seed: dict[str, Any]) -> ResolvedContext:
        """Return context pass-through with no transformation."""
        return ResolvedContext(
            mode=self.mode,
            sections=(),
            raw_context=MappingProxyType(seed),
            is_pipeline=False,
        )

    def resolve_task_context(
        self,
        feature_data: Dict[str, Any],
        seed_data: Dict[str, Any],
        *,
        domain_constraints: Optional[List[str]] = None,
        output_constraint: Optional[str] = None,
        prior_error_feedback: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build gen_context preserving exact current standalone behavior.

        This is a line-for-line extraction of the inline context building
        from develop_feature(). Dict equality with the original output is
        the acceptance criterion.
        """
        gen_context: Dict[str, Any] = {"feature_name": feature_data.get("name", "")}
        
        # Phase 4 Threading: Inject forward manifest contracts verbatim (REQ-PC-FM-004)
        fm = seed_data.get("forward_manifest")
        if fm:
            # Hydrate dict from JSON to ForwardManifest model when needed
            if isinstance(fm, dict):
                try:
                    from ..forward_manifest import ForwardManifest
                    fm = ForwardManifest.model_validate(fm)
                except Exception as exc:
                    logger.debug("Forward manifest hydration failed: %s", exc)
                    fm = None
            if fm and hasattr(fm, "binding_constraints_for_task"):
                bindings = fm.binding_constraints_for_task(feature_data.get("id", ""))
                if bindings:
                    gen_context.setdefault("domain_constraints", []).extend(bindings)

        # Target file + domain constraints
        target_files = feature_data.get("target_files") or []
        if target_files:
            gen_context["target_file"] = target_files[0]

        if domain_constraints is not None:
            gen_context["domain_constraints"] = domain_constraints
        elif output_constraint is not None:
            gen_context["output_constraint"] = output_constraint

        # Seed-level context injection (Mottainai Gaps 9-13)
        onboarding = seed_data.get("onboarding_metadata")
        if onboarding:
            objectives = onboarding.get("project_objectives")
            if isinstance(objectives, (str, list, dict)):
                gen_context["project_objectives"] = objectives
            sem_conv = onboarding.get("semantic_conventions")
            if isinstance(sem_conv, (dict, list)):
                gen_context["semantic_conventions"] = sem_conv

        arch_ctx = seed_data.get("architectural_context")
        if arch_ctx:
            gen_context["architectural_context"] = arch_ctx

        # Per-task calibration: implement_max_output_tokens
        feature_id = feature_data.get("id", "")
        calibration = seed_data.get("design_calibration")
        task_cal = calibration.get(feature_id, {}) if calibration else {}
        if isinstance(task_cal, dict) and task_cal.get("implement_max_output_tokens"):
            gen_context["implement_max_output_tokens"] = task_cal[
                "implement_max_output_tokens"
            ]

        # Plan document context
        plan_text = seed_data.get("plan_document_text")
        if plan_text:
            gen_context["plan_context"] = plan_text

        # IMP-P2: requirements text passthrough
        metadata = feature_data.get("metadata") or {}
        if metadata.get("requirements_text"):
            gen_context["requirements_text"] = metadata["requirements_text"]

        # REQ-PC-014: inject service metadata
        service_meta = seed_data.get("service_metadata")
        if service_meta:
            gen_context["service_metadata"] = service_meta

        # Gap 9: per-task metadata from seed enrichment
        self._inject_enrichment(gen_context, metadata)

        # Prior error feedback
        if prior_error_feedback:
            gen_context["prior_error_feedback"] = prior_error_feedback

        return gen_context

    @staticmethod
    def _inject_enrichment(
        gen_context: Dict[str, Any], metadata: Dict[str, Any]
    ) -> None:
        """Inject per-task enrichment from feature metadata into gen_context.

        Extracted as a static method for reuse by both strategies.
        """
        if not metadata:
            return
        meta_enrichment = metadata.get("_enrichment", {})
        if not isinstance(meta_enrichment, dict) or not meta_enrichment:
            return

        gen_context.setdefault("domain_constraints", [])
        if isinstance(gen_context["domain_constraints"], list):
            gen_context["domain_constraints"].extend(
                meta_enrichment.get("prompt_constraints", [])
            )

        # IMP-P3: Critical parameter elevation
        resolved_params = meta_enrichment.get("resolved_parameters", [])
        param_sources = meta_enrichment.get("parameter_sources", [])
        if resolved_params or param_sources:
            cp_lines: list[str] = []
            for rp in resolved_params:
                kv = rp.get("key_value", "")
                if kv:
                    cp_lines.append(kv)
            for ps in param_sources:
                kv = ps.get("key_value", "")
                if kv and kv not in cp_lines:
                    cp_lines.append(kv)
            if cp_lines:
                gen_context["critical_parameters"] = cp_lines
                gen_context["resolved_parameters"] = resolved_params


class PipelineContextStrategy(ContextStrategy):
    """Builds structured IMP-P1..P5 sections from pipeline context.

    Constructor takes validator_registry and sanitization_mode as kwargs.
    This is a plain class (not Pydantic) — follows the @property pattern for
    computed attributes, consistent with artisan_contractor.
    """

    def __init__(
        self,
        validator_registry: ValidatorRegistry | None = None,
        *,
        sanitization_mode: SanitizationMode = SanitizationMode.STRICT,
    ) -> None:
        """Initialize the PipelineContextStrategy.

        Args:
            validator_registry: Optional validator registry. If None, a new
                                empty registry is created.
            sanitization_mode: Controls whether security violations raise (STRICT)
                             or log-and-skip (LENIENT). Default: STRICT.
        """
        self._registry = validator_registry if validator_registry is not None else ValidatorRegistry()
        self._sanitization_mode = sanitization_mode

    @property
    def mode(self) -> str:
        return ExecutionMode.PIPELINE.value

    @property
    def registry(self) -> ValidatorRegistry:
        """Access the validator registry."""
        return self._registry

    @property
    def sanitization_mode(self) -> SanitizationMode:
        """Access the sanitization mode."""
        return self._sanitization_mode

    def resolve_task_context(
        self,
        feature_data: Dict[str, Any],
        seed_data: Dict[str, Any],
        *,
        domain_constraints: Optional[List[str]] = None,
        output_constraint: Optional[str] = None,
        prior_error_feedback: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build enriched gen_context with structured pipeline sections.

        Starts with the same base context as standalone, then replaces
        raw passthrough fields with formatted Markdown sections.
        Empty source data ({} or []) produces no section (omitted from context).

        User-controlled data is wrapped in safe XML delimiters to mitigate
        prompt injection (REQ-PEM-018).
        """
        gen_context: Dict[str, Any] = {
            "feature_name": feature_data.get("name", ""),
        }

        # Phase 4 Threading: Inject forward manifest contracts verbatim (REQ-PC-FM-004)
        fm = seed_data.get("forward_manifest")
        if fm:
            # Hydrate dict from JSON to ForwardManifest model when needed
            if isinstance(fm, dict):
                try:
                    from ..forward_manifest import ForwardManifest
                    fm = ForwardManifest.model_validate(fm)
                except Exception as exc:
                    logger.debug("Forward manifest hydration failed: %s", exc)
                    fm = None
            if fm and hasattr(fm, "binding_constraints_for_task"):
                bindings = fm.binding_constraints_for_task(feature_data.get("id", ""))
                if bindings:
                    gen_context["forward_contracts"] = "\n".join(
                        f"- {b}" for b in bindings
                    )

        # Target file (same as standalone)
        target_files = feature_data.get("target_files") or []
        if target_files:
            gen_context["target_file"] = target_files[0]

        # Domain constraints (same base logic, formatted for pipeline)
        if domain_constraints is not None:
            formatted = format_domain_constraints(domain_constraints)
            if formatted:
                gen_context["domain_constraints"] = formatted
        elif output_constraint is not None:
            gen_context["output_constraint"] = output_constraint

        # --- Pipeline-enriched sections (IMP-P1 through IMP-P5) ---

        # Log missing pipeline signal keys (REQ-PEM-007: warn on absent keys)
        for signal_key in PIPELINE_SIGNAL_KEYS:
            if signal_key not in seed_data or seed_data[signal_key] is None:
                logger.warning(
                    "Pipeline mode: seed missing '%s' — section will be omitted",
                    signal_key,
                    extra={"missing_key": signal_key, "mode": "pipeline"},
                )

        # IMP-P1: Onboarding metadata → project objectives + semantic conventions
        onboarding = seed_data.get("onboarding_metadata")
        if onboarding:
            objectives = onboarding.get("project_objectives")
            if isinstance(objectives, (str, list, dict)):
                formatted = format_project_objectives(objectives)
                if formatted:
                    gen_context["project_objectives"] = wrap_user_content(
                        formatted, "project_objectives"
                    )
            sem_conv = onboarding.get("semantic_conventions")
            if isinstance(sem_conv, (dict, list)):
                formatted = format_semantic_conventions(sem_conv)
                if formatted:
                    gen_context["semantic_conventions"] = wrap_user_content(
                        formatted, "semantic_conventions"
                    )

        # IMP-P2: Architectural context → formatted Markdown (not raw JSON)
        arch_ctx = seed_data.get("architectural_context")
        if arch_ctx:
            formatted = format_architectural_context(arch_ctx)
            if formatted:
                gen_context["architectural_context"] = wrap_user_content(
                    formatted, "architectural_context"
                )

        # Per-task calibration (same as standalone — numeric, not user-controlled)
        feature_id = feature_data.get("id", "")
        calibration = seed_data.get("design_calibration")
        task_cal = calibration.get(feature_id, {}) if calibration else {}
        if isinstance(task_cal, dict) and task_cal.get("implement_max_output_tokens"):
            gen_context["implement_max_output_tokens"] = task_cal[
                "implement_max_output_tokens"
            ]

        # Plan context → formatted section
        plan_text = seed_data.get("plan_document_text")
        if plan_text:
            formatted = format_plan_context(plan_text)
            if formatted:
                gen_context["plan_context"] = wrap_user_content(
                    formatted, "plan_context"
                )

        # IMP-P2: Requirements text → formatted section
        metadata = feature_data.get("metadata") or {}
        req_text = metadata.get("requirements_text")
        if req_text:
            formatted = format_requirements_context(req_text)
            if formatted:
                gen_context["requirements_context"] = wrap_user_content(
                    formatted, "requirements"
                )

        # IMP-P4: Protocol guidance from service metadata
        service_meta = seed_data.get("service_metadata")
        if service_meta:
            formatted = format_protocol_guidance(service_meta)
            if formatted:
                gen_context["protocol_guidance"] = wrap_user_content(
                    formatted, "protocol_guidance"
                )
            # Also pass raw for backward compat
            gen_context["service_metadata"] = service_meta

        # IMP-P3: Per-task enrichment (critical parameters, domain constraints)
        StandaloneContextStrategy._inject_enrichment(gen_context, metadata)

        # Format critical_parameters if present
        cp = gen_context.get("critical_parameters")
        if cp and isinstance(cp, list):
            formatted = format_critical_parameters(cp)
            if formatted:
                gen_context["critical_parameters"] = formatted

        # Prior error feedback
        if prior_error_feedback:
            gen_context["prior_error_feedback"] = prior_error_feedback

        # IMP-P5: Scope boundary instruction (pipeline only)
        gen_context["scope_boundary"] = SCOPE_BOUNDARY_INSTRUCTION

        return gen_context

    def resolve(self, seed: dict[str, Any]) -> ResolvedContext:
        """Resolve seed into structured sections with security validation.

        Steps:
        1. Sanitize all input (recursive) with security checks
        2. Build sections IMP-P1 through IMP-P5
        3. Run registered validators
        4. Log provenance event
        5. Return immutable ResolvedContext
        """
        # 1. Security validation on all input (recursive)
        sanitized, skipped_fields = self._sanitize_context(seed)

        # 2. Build sections IMP-P1 through IMP-P5
        sections: list[PromptSection] = []
        for section_id in sorted(VALID_SECTION_IDS):
            builder = SECTION_BUILDERS[section_id]
            section = builder(sanitized)
            sections.append(section)

        # 3. Run registered validators
        validation_results = self._registry.run_all(sections, sanitized)

        # 4. Log provenance
        logger.info(
            "Pipeline context resolved: %d populated sections, validation=%s",
            len([s for s in sections if s.is_populated]),
            all(v.passed for v in validation_results),
            extra={
                "event": "pipeline_context_resolved",
                "populated_sections": [
                    s.section_id for s in sections if s.is_populated
                ],
                "validation_passed": all(v.passed for v in validation_results),
                "skipped_fields": skipped_fields,
            },
        )

        # 5. Return immutable ResolvedContext
        return ResolvedContext(
            mode=self.mode,
            sections=tuple(sections),
            raw_context=MappingProxyType(sanitized),
            is_pipeline=True,
            validation_results=tuple(validation_results),
        )

    def _sanitize_context(
        self, ctx: dict[str, Any]
    ) -> tuple[dict[str, Any], list[str]]:
        """Apply security validations to all context values, recursively.

        Returns (sanitized_dict, skipped_fields). In strict mode, violations
        raise immediately. In lenient mode, offending fields are omitted and
        logged.
        """
        sanitized: dict[str, Any] = {}
        skipped: list[str] = []

        for key, value in ctx.items():
            try:
                _validate_key_name(key)
                sanitized[key] = _sanitize_value(key, value)
            except (
                PathTraversalError,
                PromptInjectionError,
                FieldLengthError,
                InvalidKeyError,
            ) as exc:
                if self._sanitization_mode == SanitizationMode.STRICT:
                    raise
                logger.warning(
                    "Sanitization: skipping field '%s': %s",
                    key,
                    exc,
                    extra={
                        "event": "sanitization_field_skipped",
                        "field": key,
                        "reason": str(exc),
                    },
                )
                skipped.append(key)

        return sanitized, skipped


# ──────────────────────────────────────────────────────────────────────────
# Factory Function
# ──────────────────────────────────────────────────────────────────────────

def create_strategy(
    mode: str = DEFAULT_MODE,
    *,
    validator_registry: ValidatorRegistry | None = None,
    sanitization_mode: SanitizationMode = SanitizationMode.STRICT,
) -> ContextStrategy:
    """Factory that returns the appropriate strategy for the given mode.

    Args:
        mode: Execution mode ("standalone" or "pipeline"). Default: "standalone".
        validator_registry: Optional validator registry for pipeline mode.
        sanitization_mode: Sanitization mode for pipeline strategy.

    Returns:
        A ContextStrategy instance (StandaloneContextStrategy or
        PipelineContextStrategy).

    Raises:
        ValueError: If mode is not recognized.
    """
    if mode == ExecutionMode.STANDALONE.value:
        return StandaloneContextStrategy()
    elif mode == ExecutionMode.PIPELINE.value:
        return PipelineContextStrategy(
            validator_registry=validator_registry,
            sanitization_mode=sanitization_mode,
        )
    else:
        raise ValueError(f"Unknown execution mode: {mode!r}")


# ──────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────

__all__ = [
    # Constants
    "PIPELINE_SIGNAL_KEYS",
    "SECTION_IMP_P1",
    "SECTION_IMP_P2",
    "SECTION_IMP_P3",
    "SECTION_IMP_P4",
    "SECTION_IMP_P5",
    "SECTION_IMP_P6",
    "VALID_SECTION_IDS",
    "MAX_FIELD_LENGTH",
    "MAX_PATH_DEPTH",
    "FORBIDDEN_PATH_PATTERNS",
    "DEFAULT_MODE",
    "SECTION_FIELD_MAP",
    "SECTION_HEADINGS",
    # Enums
    "ExecutionMode",
    "SanitizationMode",
    # Data Classes
    "PromptSection",
    "ValidationResult",
    "ResolvedContext",
    # Exceptions
    "PathTraversalError",
    "PromptInjectionError",
    "FieldLengthError",
    "InvalidKeyError",
    "RegistryFrozenError",
    "DuplicateValidatorError",
    # Validator Protocol and Registry
    "ContextValidator",
    "ValidatorRegistry",
    # Strategy Classes
    "ContextStrategy",
    "StandaloneContextStrategy",
    "PipelineContextStrategy",
    # Factory
    "create_strategy",
]