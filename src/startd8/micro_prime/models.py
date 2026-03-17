"""Micro Prime data models, enums, and configuration.

Defines the Pydantic models and dataclasses used throughout the Micro Prime
local-first code generation engine.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field


# Sentinel marker injected into skeleton files to signal incomplete
# generation.  Used by file-whole validation (AC-R3) and repair pipeline.
SKELETON_MARKER = "# [STARTD8-SKELETON]"


class TierClassification(str, Enum):
    """Element complexity tier for routing decisions."""

    TRIVIAL = "trivial"
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


class EscalationReason(str, Enum):
    """Why an element was escalated from local to cloud."""

    AST_FAILURE = "ast_failure"
    STRUCTURAL_MISMATCH = "structural_mismatch"
    SEMANTIC_FAILURE = "semantic_failure"
    OLLAMA_UNAVAILABLE = "ollama_unavailable"
    TIER_TOO_HIGH = "tier_too_high"
    REPAIR_EXHAUSTED = "repair_exhausted"
    EMPTY_RESPONSE = "empty_response"
    TIMEOUT = "timeout"
    CIRCUIT_BREAKER = "circuit_breaker"
    DECOMPOSITION_FAILED = "decomposition_failed"
    NOT_DECOMPOSABLE = "not_decomposable"
    OLLAMA_WHOLE_FAILED = "ollama_whole_failed"
    NON_PYTHON_BYPASS = "non_python_bypass"


# Re-export from shared repair package for backward compatibility.
from startd8.repair.models import RepairAttribution, RepairStepResult  # noqa: F401


@dataclass
class EscalationContext:
    """Detailed context for cloud escalation (REQ-MP-502)."""

    element_fqn: str = ""
    local_model: str = ""
    raw_output: str = ""
    repair_steps_applied: list[str] = field(default_factory=list)
    repaired_code: Optional[str] = None
    error: str = ""
    # Keiyaku-compliant structured handoff (K-6) — set when repair data
    # is available, None otherwise. Callers should prefer this over the
    # prose fields above when constructing escalation prompts.
    escalation_handoff: Optional["EscalationHandoff"] = None


@dataclass
class EscalationResult:
    """Captures why an element was escalated to cloud processing."""

    reason: EscalationReason
    detail: str
    last_code: Optional[str] = None
    last_error: Optional[str] = None
    context: Optional[EscalationContext] = None


# ═══════════════════════════════════════════════════════════════════════════
# Keiyaku boundary contracts (K-6, K-9)
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class RepairStepOutcome:
    """Keiyaku-compliant repair step record (K-9).

    Structured representation of a single repair pipeline step outcome,
    preserving machine-readable diagnostics across boundary crossings.
    """

    step: str  # e.g. "fence_strip", "indent_normalize"
    modified: bool
    ast_valid_after: bool
    detail: str  # what the step did, e.g. "Removed ```python fence"


@dataclass(frozen=True)
class EscalationRepairOutcome:
    """Keiyaku-compliant repair pipeline outcome (K-9).

    Structured boundary contract for repair results flowing to
    escalation (K-6) and observability (REQ-MP-603).
    """

    element_fqn: str
    ast_valid_before: bool
    ast_valid_after: bool
    steps: List[RepairStepOutcome]
    final_verdict: str  # "recovered", "failed", "unchanged"
    lines_before: int
    lines_after: int

    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict for escalation handoff."""
        return {
            "repair_outcome": {
                "element_fqn": self.element_fqn,
                "ast_valid_before": self.ast_valid_before,
                "ast_valid_after": self.ast_valid_after,
                "steps": [
                    {
                        "step": s.step,
                        "modified": s.modified,
                        "ast_valid_after": s.ast_valid_after,
                        "detail": s.detail,
                    }
                    for s in self.steps
                ],
                "final_verdict": self.final_verdict,
                "lines_before": self.lines_before,
                "lines_after": self.lines_after,
            }
        }


@dataclass(frozen=True)
class EscalationHandoff:
    """Keiyaku-compliant escalation contract (K-6).

    Structured handoff from local agent (Ollama) to cloud agent,
    replacing prose '## Prior Local Model Attempt' injection.
    """

    element_fqn: str
    original_tier: str  # "SIMPLE" or "MODERATE"
    local_model: str  # e.g. "startd8-coder"
    attempt_count: int
    failure_category: str  # matches EscalationReason enum value
    failure_message: str
    raw_output_lines: int
    repair: Optional[EscalationRepairOutcome]  # None if repair wasn't attempted
    element_signature: str  # canonical signature from manifest
    element_kind: str  # "METHOD", "FUNCTION", "CLASS"
    parent_class: Optional[str]

    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict for prompt injection."""
        d: dict = {
            "escalation": {
                "element_fqn": self.element_fqn,
                "original_tier": self.original_tier,
                "local_model": self.local_model,
                "attempt_count": self.attempt_count,
                "failure": {
                    "category": self.failure_category,
                    "message": self.failure_message,
                    "raw_output_lines": self.raw_output_lines,
                },
                "element_spec": {
                    "signature": self.element_signature,
                    "kind": self.element_kind,
                    "parent_class": self.parent_class,
                },
            }
        }
        if self.repair is not None:
            d["escalation"]["repair_applied"] = self.repair.to_dict()[
                "repair_outcome"
            ]["steps"]
        return d

    def to_prompt_section(self) -> str:
        """Render as structured prompt section for cloud model.

        Produces both JSON (machine-readable) and summary (human-readable)
        so the cloud model can parse either format.
        """
        data = self.to_dict()
        lines = [
            "## Prior Local Model Attempt (Structured)",
            "",
            "```json",
            json.dumps(data, indent=2),
            "```",
            "",
            (
                f"**Summary:** {self.failure_category} after "
                f"{self.attempt_count} attempt(s) "
                f"on {self.local_model}. {self.failure_message}"
            ),
        ]
        if self.repair and self.repair.steps:
            applied = [s.step for s in self.repair.steps if s.modified]
            if applied:
                lines.append(
                    f"**Repair steps applied:** {', '.join(applied)}"
                )
        return "\n".join(lines)


@dataclass
class ElementResult:
    """Result from processing a single element through the engine."""

    element_name: str
    file_path: str
    tier: TierClassification
    success: bool
    classification_reason: str = ""
    parent_class: Optional[str] = None
    element_kind: Optional[str] = None
    api_file_import_bump: int = 0
    api_element_adjustment: int = 0
    code: Optional[str] = None
    escalation: Optional[EscalationResult] = None
    template_used: bool = False
    template_name: Optional[str] = None
    repair_steps_applied: list[str] = field(default_factory=list)
    repair_attribution: Optional[RepairAttribution] = None
    repair_recovered: bool = False
    ast_valid_before_repair: Optional[bool] = None
    ast_valid_after_repair: Optional[bool] = None
    verification_verdict: Optional[str] = None
    model: Optional[str] = None
    cloud_retry_attempts: int = 0
    cloud_retry_success: bool = False
    cloud_retry_strategy: Optional[str] = None
    cloud_retry_last_error: Optional[str] = None
    generation_time_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    decomposition_metadata: Optional[dict] = None
    generation_strategy: Optional[str] = None

    # ── Factory methods (AC-R15/R22) ─────────────────────────────────────

    @classmethod
    def make_success(
        cls,
        element_name: str,
        file_path: str,
        tier: TierClassification,
        classification_reason: str,
        code: Optional[str],
        *,
        model: Optional[str] = None,
        generation_time_ms: float = 0.0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        repair_steps_applied: Optional[list[str]] = None,
        repair_attribution: Optional[RepairAttribution] = None,
        repair_recovered: bool = False,
        ast_valid_before_repair: Optional[bool] = None,
        ast_valid_after_repair: Optional[bool] = None,
        verification_verdict: Optional[str] = None,
        template_used: bool = False,
        template_name: Optional[str] = None,
        decomposition_metadata: Optional[dict] = None,
        generation_strategy: Optional[str] = None,
    ) -> "ElementResult":
        return cls(
            element_name=element_name,
            file_path=file_path,
            tier=tier,
            success=True,
            classification_reason=classification_reason,
            code=code,
            model=model,
            generation_time_ms=generation_time_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            repair_steps_applied=repair_steps_applied or [],
            repair_attribution=repair_attribution,
            repair_recovered=repair_recovered,
            ast_valid_before_repair=ast_valid_before_repair,
            ast_valid_after_repair=ast_valid_after_repair,
            verification_verdict=verification_verdict,
            template_used=template_used,
            template_name=template_name,
            decomposition_metadata=decomposition_metadata,
            generation_strategy=generation_strategy,
        )

    @classmethod
    def make_escalation(
        cls,
        element_name: str,
        file_path: str,
        tier: TierClassification,
        classification_reason: str,
        escalation: Optional[EscalationResult] = None,
        *,
        code: Optional[str] = None,
        model: Optional[str] = None,
        generation_time_ms: float = 0.0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        repair_steps_applied: Optional[list[str]] = None,
        repair_attribution: Optional[RepairAttribution] = None,
        repair_recovered: bool = False,
        ast_valid_before_repair: Optional[bool] = None,
        ast_valid_after_repair: Optional[bool] = None,
        verification_verdict: Optional[str] = None,
        decomposition_metadata: Optional[dict] = None,
        generation_strategy: Optional[str] = None,
    ) -> "ElementResult":
        return cls(
            element_name=element_name,
            file_path=file_path,
            tier=tier,
            success=False,
            classification_reason=classification_reason,
            code=code,
            escalation=escalation,
            model=model,
            generation_time_ms=generation_time_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            repair_steps_applied=repair_steps_applied or [],
            repair_attribution=repair_attribution,
            repair_recovered=repair_recovered,
            ast_valid_before_repair=ast_valid_before_repair,
            ast_valid_after_repair=ast_valid_after_repair,
            verification_verdict=verification_verdict,
            decomposition_metadata=decomposition_metadata,
            generation_strategy=generation_strategy,
        )

    @classmethod
    def make_cached(
        cls,
        element_name: str,
        file_path: str,
        tier: TierClassification,
        classification_reason: str,
        code: Optional[str],
        *,
        source: str = "in_memory",
    ) -> "ElementResult":
        return cls(
            element_name=element_name,
            file_path=file_path,
            tier=tier,
            success=True,
            classification_reason=classification_reason,
            code=code,
            model=f"cache:{source}",
            decomposition_metadata={"source": source},
        )

    @classmethod
    def make_template_match(
        cls,
        element_name: str,
        file_path: str,
        tier: TierClassification,
        classification_reason: str,
        code: str,
        template_name: str,
        *,
        generation_strategy: Optional[str] = None,
    ) -> "ElementResult":
        return cls(
            element_name=element_name,
            file_path=file_path,
            tier=tier,
            success=True,
            classification_reason=classification_reason,
            code=code,
            template_used=True,
            template_name=template_name,
            model="template",
            verification_verdict="pass",
            generation_strategy=generation_strategy,
        )

    @classmethod
    def make_decomposition_success(
        cls,
        element_name: str,
        file_path: str,
        tier: TierClassification,
        classification_reason: str,
        code: str,
        *,
        decomposition_metadata: Optional[dict] = None,
        model: Optional[str] = None,
        generation_time_ms: float = 0.0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        generation_strategy: Optional[str] = None,
    ) -> "ElementResult":
        return cls(
            element_name=element_name,
            file_path=file_path,
            tier=tier,
            success=True,
            classification_reason=classification_reason,
            code=code,
            decomposition_metadata=decomposition_metadata,
            model=model,
            generation_time_ms=generation_time_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            generation_strategy=generation_strategy,
        )


@dataclass
class FileResult:
    """Result from processing all elements in a file."""

    file_path: str
    element_results: list[ElementResult] = field(default_factory=list)
    filled_skeleton: Optional[str] = None

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.element_results if r.success)

    @property
    def escalated_count(self) -> int:
        return sum(1 for r in self.element_results if r.escalation is not None)

    @property
    def total_count(self) -> int:
        return len(self.element_results)


@dataclass
class SeedResult:
    """Result from processing all elements across all files in a seed."""

    file_results: list[FileResult] = field(default_factory=list)
    total_generation_time_ms: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    @property
    def success_count(self) -> int:
        return sum(fr.success_count for fr in self.file_results)

    @property
    def escalated_count(self) -> int:
        return sum(fr.escalated_count for fr in self.file_results)

    @property
    def total_count(self) -> int:
        return sum(fr.total_count for fr in self.file_results)


class MicroPrimeConfig(BaseModel):
    """Configuration for the Micro Prime engine."""

    model: str = "startd8-coder"
    provider: str = "ollama"
    temperature: float = 0.1
    max_tokens: int = 2048
    input_token_budget: int = 1024
    templates_enabled: bool = True
    repair_enabled: bool = True
    few_shot_enabled: bool = True
    max_few_shot_examples: int = 2
    escalation_enabled: bool = True
    external_api_packages: list[str] = [
        # Network / RPC
        "grpc", "grpcio", "httpx", "aiohttp", "requests",
        # Web frameworks
        "flask", "fastapi", "django", "starlette",
        # Template engines
        "jinja2", "mako",
        # Cloud SDKs
        "google.cloud", "google.auth", "google.api_core",
        "boto3", "botocore",
        "azure",
        # Database / ORM
        "sqlalchemy", "alembic", "asyncpg", "psycopg2",
        # Task queues / caching
        "celery", "redis", "kombu",
        # Testing / load
        "locust", "playwright",
    ]
    # Max Ollama generation attempts before escalating to cloud
    local_max_attempts: int = Field(default=2, ge=1, le=10)
    cloud_escalation_max_attempts: int = 3
    cloud_escalation_retry_strategy: str = "same_prompt"
    cloud_escalation_retry_max_chars: int = 512
    # Semantic verification (REQ-MP-512)
    semantic_verification_enabled: bool = True
    semantic_verification_agent_spec: Optional[str] = None
    semantic_verification_max_tokens: int = 256
    semantic_verification_temperature: float = 0.0
    semantic_verification_prompt_max_chars: int = 4000
    semantic_verification_fn: Optional[Any] = Field(default=None, exclude=True)
    dry_run: bool = False
    # Classifier thresholds
    max_simple_imports: int = 8
    max_simple_params: int = 4
    # Scoring tuning knobs
    class_score_bonus: int = 1
    simple_threshold: int = 0
    docstring_length_threshold: int = 200
    # Decomposer settings (REQ-MP-908)
    # FALLBACK — decomposition is the primary source of accidental complexity
    # (decomposer 1,029 + splicer 856 + element repair 1,015 lines).
    # Only used when file-whole is ineligible or fails.
    # MODERATE elements now prefer Ollama-whole (moderate_ollama_whole_enabled)
    # or escalate to cloud.  Pass decomposition_enabled=True to opt in.
    decomposition_enabled: bool = False
    max_sub_elements: int = 5
    max_helpers_per_function: int = 4
    decomposition_confidence_threshold: float = 0.6
    class_decompose_enabled: bool = True
    function_chain_enabled: bool = True
    # Simple decomposer gate (Phase 1, Step 6)
    enable_simple_decomposer: bool = True
    simple_decomposer_confidence_threshold: float = 0.7
    # Recursive decomposition settings (REQ-MP-915)
    recursion_enabled: bool = False
    recursion_max_depth: int = 2
    recursion_max_sub_elements_total: int = 8
    recursion_max_llm_calls: int = 3
    recursion_monotonicity: str = "strict_tier_decrease"
    # Orchestrator decomposition relaxation (Kaizen run-017)
    orchestrator_decomp_max_external_deps: int = 3
    # Ollama-whole for MODERATE elements (before decomposition)
    moderate_ollama_whole_enabled: bool = True
    moderate_ollama_whole_skip_signals: set[str] = {"external_api", "orchestrator", "app_server_instance"}
    # PRIMARY generation path — generate the entire file in one shot instead
    # of decomposing into individual element-body prompts.  File-whole avoids
    # the 5 lossy information boundaries of element-by-element processing.
    # Thresholds raised aggressively (AC-R3-R4) to route most files here.
    # Only files above these thresholds fall through to element-by-element.
    file_ollama_whole_enabled: bool = True
    file_ollama_whole_max_elements: int = 60
    file_ollama_whole_max_loc: int = 600
    # Post-generation success criteria (REQ-MP-504)
    min_element_fill_rate: float = 0.5
    # Element prompt mode: "full_function" asks the model to output the complete
    # function (def line + body), then deterministically extracts the body via AST.
    # "body_only" is the legacy mode that asks for indented body lines only.
    # full_function eliminates bare_statement_wrap + import_completion repairs.
    element_prompt_mode: str = "full_function"


@dataclass(frozen=True)
class VerificationIssue:
    """Single issue found during semantic verification (K-7)."""

    severity: str  # "critical", "high", "medium", "low" (aligned with GateSeverity)
    category: str  # e.g. "missing_error_handling", "type_mismatch", "unused_parameter"
    description: str  # human-readable explanation
    line_hint: Optional[int] = None  # approximate line number, if known
    suggested_fix: Optional[str] = None  # optional remediation hint


@dataclass(frozen=True)
class SemanticVerificationResult:
    """Keiyaku-compliant semantic verification output contract (K-7).

    Defines the expected JSON schema for LLM-based semantic verification.
    The LLM prompt should request output in this shape; the validator
    parses and constructs this dataclass from the response.

    Schema version: 1.0.0 (frozen per Keiyaku Rule 6 / ContextCore v1 policy).

    JSON schema for LLM prompt::

        {
          "verdict": "pass|fail|inconclusive",
          "confidence": 0.85,
          "issues": [
            {
              "severity": "high",
              "category": "missing_error_handling",
              "description": "Division by total_count without zero check",
              "line_hint": 7,
              "suggested_fix": "Add guard: if total_count == 0: return 0.0"
            }
          ],
          "element_fqn": "module.ClassName.calculate_ratio"
        }
    """

    verdict: str  # "pass", "fail", "inconclusive"
    confidence: float  # 0.0-1.0
    issues: tuple  # tuple[VerificationIssue, ...] (frozen requires hashable)
    element_fqn: str

    # Valid verdict values (for validation)
    VALID_VERDICTS = ("pass", "fail", "inconclusive")

    @classmethod
    def from_json(cls, data: dict, element_fqn: str) -> "SemanticVerificationResult":
        """Parse LLM JSON output into typed result.

        Applies Keiyaku Rule 5: fail-open on format, fail-closed on content.
        Auto-corrects where unambiguous, warns on non-standard values.
        """
        verdict = data.get("verdict", "inconclusive")
        if verdict not in cls.VALID_VERDICTS:
            verdict = "inconclusive"  # auto-correct unknown verdicts

        confidence = data.get("confidence", 0.5)
        confidence = max(0.0, min(1.0, float(confidence)))  # clamp to [0, 1]

        issues = []
        for item in data.get("issues", []):
            issues.append(VerificationIssue(
                severity=item.get("severity", "medium"),
                category=item.get("category", "unknown"),
                description=item.get("description", "(not provided)"),
                line_hint=item.get("line_hint"),
                suggested_fix=item.get("suggested_fix"),
            ))

        return cls(
            verdict=verdict,
            confidence=confidence,
            issues=tuple(issues),
            element_fqn=data.get("element_fqn", element_fqn),
        )

    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict."""
        return {
            "verification": {
                "verdict": self.verdict,
                "confidence": self.confidence,
                "issues": [
                    {
                        "severity": i.severity,
                        "category": i.category,
                        "description": i.description,
                        "line_hint": i.line_hint,
                        "suggested_fix": i.suggested_fix,
                    }
                    for i in self.issues
                ],
                "element_fqn": self.element_fqn,
            }
        }

    @property
    def passed(self) -> bool:
        """Convenience: did verification pass?"""
        return self.verdict == "pass"

    @property
    def has_critical_issues(self) -> bool:
        """Convenience: any critical issues?"""
        return any(i.severity == "critical" for i in self.issues)


def validate_semantic_verification_json(
    raw_text: str,
    element_fqn: str,
) -> tuple:  # (ok: bool, result_or_error: SemanticVerificationResult | str)
    """Validate and parse LLM semantic verification output.

    Applies Keiyaku dual-format pattern:
    1. Strip ``json`` fences
    2. Parse JSON
    3. Construct SemanticVerificationResult via from_json()
    4. Return (True, result) or (False, error_message)
    """
    import json
    import re

    text = raw_text.strip()
    # Strip ```json ... ``` fences
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        return (False, f"JSON parse error: {exc}")

    if not isinstance(data, dict):
        return (False, f"Expected JSON object, got {type(data).__name__}")

    try:
        result = SemanticVerificationResult.from_json(data, element_fqn)
        return (True, result)
    except (TypeError, KeyError, ValueError) as exc:
        return (False, f"Schema construction error: {exc}")


class MicroPrimeElementMetrics(BaseModel):
    """Per-element metrics for observability (REQ-MP-600)."""

    element_name: str
    element_fqn: str = ""
    element_kind: str = ""
    api_file_import_bump: int = 0
    api_element_adjustment: int = 0
    file_path: str
    tier: TierClassification
    success: bool
    classification_reason: str = ""
    template_used: bool = False
    template_name: Optional[str] = None
    repair_steps: list[str] = Field(default_factory=list)
    repair_attribution: Optional[RepairAttribution] = None
    repair_recovered: bool = False
    ast_valid_before_repair: Optional[bool] = None
    ast_valid_after_repair: Optional[bool] = None
    verification_verdict: Optional[str] = None
    escalated: bool = False
    generation_time_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    generation_tokens: int = 0
    model: Optional[str] = None
    escalation_reason: Optional[str] = None


class MicroPrimeCostReport(BaseModel):
    """Cost accounting for a Micro Prime run (REQ-MP-602)."""

    total_elements: int = 0
    trivial_count: int = 0
    simple_count: int = 0
    simple_escalated_count: int = 0
    moderate_count: int = 0
    complex_count: int = 0
    local_success_count: int = 0
    escalated_count: int = 0
    template_count: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    estimated_local_cost_usd: float = 0.0
    estimated_cloud_savings_usd: float = 0.0
    success_rate: float = 0.0
    baseline_all_cloud_usd: float = 0.0
    actual_cloud_usd: float = 0.0
    savings_usd: float = 0.0
    savings_pct: float = 0.0
    local_inference_time_total_s: float = 0.0
    local_tokens_total: int = 0
    decomposed_count: int = 0
    decomposition_failure_count: int = 0


# ═══════════════════════════════════════════════════════════════════════════
# Canonical signature / def-line renderers (AC-R12)
# ═══════════════════════════════════════════════════════════════════════════


def render_signature_str(sig: "Signature") -> str:
    """Render a ``Signature`` to a parameter string, e.g. ``(self, name: str)``.

    Single canonical implementation — all call-sites (decomposer,
    prompt_builder, file_assembler, structural_verify) must delegate here.
    """
    from startd8.utils.code_manifest import ParamKind  # lazy to avoid cycles

    parts: list[str] = []
    saw_positional_only = False
    saw_keyword_only = False

    for param in sig.params:
        rendered = param.name
        if param.annotation:
            rendered += f": {param.annotation}"
        if param.default is not None:
            rendered += f" = {param.default}"

        if param.kind == ParamKind.POSITIONAL_ONLY:
            saw_positional_only = True
            parts.append(rendered)
        elif param.kind == ParamKind.VAR_POSITIONAL:
            if saw_positional_only:
                parts.append("/")
                saw_positional_only = False
            parts.append(f"*{rendered}")
            saw_keyword_only = True
        elif param.kind == ParamKind.KEYWORD_ONLY:
            if saw_positional_only:
                parts.append("/")
                saw_positional_only = False
            if not saw_keyword_only:
                parts.append("*")
                saw_keyword_only = True
            parts.append(rendered)
        elif param.kind == ParamKind.VAR_KEYWORD:
            if saw_positional_only:
                parts.append("/")
                saw_positional_only = False
            parts.append(f"**{rendered}")
        else:
            # POSITIONAL or KEYWORD
            if saw_positional_only:
                parts.append("/")
                saw_positional_only = False
            parts.append(rendered)

    if saw_positional_only:
        parts.append("/")

    return f"({', '.join(parts)})"


def render_def_line(element: "ForwardElementSpec") -> Optional[str]:
    """Build a canonical ``def`` / ``async def`` / ``class`` line.

    Returns ``None`` for element kinds that don't have def lines
    (CONSTANT, VARIABLE, TYPE_ALIAS).
    """
    from startd8.utils.code_manifest import ElementKind  # lazy to avoid cycles

    if element.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE, ElementKind.TYPE_ALIAS):
        return None
    if element.kind == ElementKind.CLASS:
        bases = f"({', '.join(element.bases)})" if element.bases else ""
        return f"class {element.name}{bases}:"
    prefix = "async def" if element.kind in (
        ElementKind.ASYNC_FUNCTION, ElementKind.ASYNC_METHOD,
    ) else "def"
    sig = "()"
    if element.signature:
        sig = render_signature_str(element.signature)
    ret = ""
    if element.signature and element.signature.return_annotation:
        ret = f" -> {element.signature.return_annotation}"
    return f"{prefix} {element.name}{sig}{ret}:"
