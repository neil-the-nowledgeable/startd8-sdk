"""Micro Prime Engine — Main Orchestrator (REQ-MP-502, 512).

Routes elements through the local-first code generation pipeline:
  TRIVIAL  → template registry → splice → done
  SIMPLE   → prompt builder → Ollama → repair → verify → splice or escalate
  MODERATE → Ollama-whole (if eligible) → decompose → escalate
  COMPLEX  → passthrough for cloud handling
"""

from __future__ import annotations

import ast
import hashlib
import json
import time
import textwrap
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any, Optional

from startd8.element_id import make_element_id
from startd8.element_registry import (
    ElementEntry,
    ElementRegistry,
    compute_element_context_checksum,
    is_stale,
)
from startd8.forward_manifest import (
    ContractConfidence,
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardManifest,
    InterfaceContract,
)
from startd8.logging_config import get_logger
from startd8.micro_prime.classifier import classify_element_with_details
from startd8.micro_prime.metrics import MetricsCollector
from startd8.micro_prime.decomposer import ModerateDecomposer
from startd8.micro_prime.decomposition.core import (
    DecompositionContext,
    DecompositionNode,
    DecompositionPlanGraph,
    RECURSION_REJECTION_REASONS,
    RecursionPolicy,
    make_fingerprint,
    policy_from_config,
)
from startd8.micro_prime.context import MicroPrimeContext
from startd8.complexity.models import RejectionReason, TaskComplexitySignals
from startd8.micro_prime.models import (
    SKELETON_MARKER,
    ElementResult,
    EscalationContext,
    EscalationHandoff,
    EscalationReason,
    EscalationRepairOutcome,
    EscalationResult,
    FileResult,
    MicroPrimeConfig,
    SeedResult,
    TierClassification,
)
from startd8.micro_prime.prompt_builder import build_body_prompt, find_few_shot_examples
from startd8.micro_prime.repair import (
    RepairResult,
    build_repair_attribution,
    run_file_repair_pipeline,
    run_file_whole_contractor_repair,
    run_repair_pipeline,
    to_escalation_repair_outcome,
)
from startd8.micro_prime.splicer import SpliceResult, SpliceViolation, splice_body_into_skeleton
from startd8.repair.models import ContractViolationDiagnostic, RepairContext
from startd8.repair.steps.contract_violation_fix import ContractViolationFixStep
from startd8.micro_prime.templates import TemplateRegistry
from startd8.utils.code_extraction import extract_code_from_response
from startd8.utils.code_manifest import ElementKind, Param, ParamKind, Signature

logger = get_logger(__name__)

# Singleton repair step for contract violation repair after splice
_contract_violation_fix_step = ContractViolationFixStep()


_SPLICE_VIOLATION_TYPE_MAP = {
    "parameter_count_mismatch": "missing_parameter",
    "parameter_name_mismatch": "missing_parameter",
    "return_type_mismatch": "wrong_return_type",
    "base_class_mismatch": "missing_base_class",
}


def _attempt_splice_violation_repair(
    spliced_code: str,
    violations: list[SpliceViolation],
    file_path: str,
) -> tuple[str, list[str]]:
    """Convert structured splicer violations to diagnostics and attempt repair.

    Consumes ``SpliceViolation`` dataclass objects (not strings) so that
    downstream repair gets typed fields without fragile string parsing.

    Returns (possibly-repaired code, list of fix descriptions).
    Non-fatal: returns original code if repair fails.
    """
    diagnostics: list[ContractViolationDiagnostic] = []
    for v in violations:
        repair_type = _SPLICE_VIOLATION_TYPE_MAP.get(v.violation_type)
        if not repair_type:
            continue
        diagnostics.append(ContractViolationDiagnostic(
            category="contract_violation",
            file=file_path,
            message=v.message,
            violation_type=repair_type,
            expected=v.expected,
            actual=v.actual,
            element_name=v.element_name,
        ))

    if not diagnostics:
        return spliced_code, []

    ctx = RepairContext(diagnostics=diagnostics)
    result = _contract_violation_fix_step(
        spliced_code, ctx, Path(file_path),
    )
    if result.modified:
        # Validate repaired code still parses
        try:
            ast.parse(result.code)
            fixes = result.metrics.get("fixes", [])
            logger.info(
                "Splice violation repair applied %d fix(es) to %s: %s",
                len(fixes), file_path, "; ".join(fixes),
            )
            return result.code, fixes
        except SyntaxError:
            logger.warning(
                "Splice violation repair produced invalid syntax for %s — reverting",
                file_path,
            )
    return spliced_code, []


# ── OTel decomposition metrics (REQ-MP-906, AC-R5) ──────────────────
#
# Consolidated into _EngineMetrics to eliminate 15 counters × 15 wrappers
# of repeating try/except + None-check boilerplate.


class _EngineMetrics:
    """Lazy OTel metric registry — single try/except for all counters."""

    _COUNTERS = {
        "decomp_attempted": ("micro_prime.decomposition_attempted", "Decomposition plans created"),
        "decomp_succeeded": ("micro_prime.decomposition_succeeded", "Decomposition plans where all sub-elements succeeded"),
        "decomp_failed": ("micro_prime.decomposition_failed", "Decomposition plans abandoned (sub-element or assembly failure)"),
        "decomp_rejected": ("micro_prime.decomposition_rejected", "Elements where decompose() returned None"),
        "sub_elements_generated": ("micro_prime.sub_elements_generated", "Individual sub-element generation attempts"),
        "simple_decompose_attempted": ("micro_prime.simple_decompose_attempted", "SIMPLE function body decomposition attempts"),
        "simple_decompose_succeeded": ("micro_prime.simple_decompose_succeeded", "SIMPLE function body decompositions that produced code"),
        "simple_decompose_rejected": ("micro_prime.simple_decompose_rejected", "SIMPLE function body decompositions that fell back to LLM"),
        "recursion_attempted": ("micro_prime.recursion_attempted", "Recursive decomposition attempts"),
        "recursion_succeeded": ("micro_prime.recursion_succeeded", "Recursive decomposition successes"),
        "recursion_rejected": ("micro_prime.recursion_rejected", "Recursive decomposition rejections"),
        "moderate_ollama_whole_attempted": ("micro_prime.moderate_ollama_whole_attempted", "MODERATE elements where Ollama-whole was tried before decomposition"),
        "moderate_ollama_whole_succeeded": ("micro_prime.moderate_ollama_whole_succeeded", "MODERATE elements resolved by Ollama-whole (no decomposition needed)"),
        "generation_path": ("micro_prime.generation_path_total", "Generation path routing decisions"),
        "generation_path_outcome": ("micro_prime.generation_path_outcome_total", "Generation path outcomes (success/failure)"),
        "ollama_finish_reason": ("micro_prime.ollama_finish_reason_total", "Ollama generation finish reasons (stop/length) for stop-sequence verification"),
    }

    _HISTOGRAMS = {
        "decomp_time_ms": ("micro_prime.decomposition_time_ms", "End-to-end time for decompose + generate + assemble", "ms"),
        "assembly_time_ms": ("micro_prime.assembly_time_ms", "Time spent in decomposer assembly step", "ms"),
    }

    def __init__(self) -> None:
        self._counters: dict[str, Any] = {}
        self._histograms: dict[str, Any] = {}
        self._available = False
        try:
            from opentelemetry import metrics as otel_metrics

            meter = otel_metrics.get_meter("startd8.micro_prime")
            for key, (name, desc) in self._COUNTERS.items():
                self._counters[key] = meter.create_counter(name, description=desc)
            for key, (name, desc, unit) in self._HISTOGRAMS.items():
                self._histograms[key] = meter.create_histogram(name, description=desc, unit=unit)
            self._available = True
        except ImportError:
            pass

    def record(self, name: str, value: int, attrs: dict[str, str]) -> None:
        """Increment a counter by *value* with *attrs*."""
        counter = self._counters.get(name)
        if counter is not None:
            counter.add(value, attrs)

    def record_histogram(self, name: str, value: float, attrs: dict[str, str]) -> None:
        """Record a histogram observation."""
        histogram = self._histograms.get(name)
        if histogram is not None:
            histogram.record(value, attrs)


_engine_metrics = _EngineMetrics()

# Backward-compatible module-level counter aliases for tests that patch
# these directly (e.g., test_recursion_observability.py).
_recursion_attempted = _engine_metrics._counters.get("recursion_attempted")
_recursion_succeeded = _engine_metrics._counters.get("recursion_succeeded")
_recursion_rejected = _engine_metrics._counters.get("recursion_rejected")


def _record_decomp_attempted(strategy: str, file_path: str) -> None:
    _engine_metrics.record("decomp_attempted", 1, {"strategy": strategy, "file_path": file_path})


def _record_decomp_succeeded(strategy: str, file_path: str) -> None:
    _engine_metrics.record("decomp_succeeded", 1, {"strategy": strategy, "file_path": file_path})


def _record_decomp_failed(strategy: str, file_path: str, failure_reason: str) -> None:
    _engine_metrics.record("decomp_failed", 1, {"strategy": strategy, "file_path": file_path, "failure_reason": failure_reason})


def _record_decomp_rejected(file_path: str, rejection_reason: str) -> None:
    _engine_metrics.record("decomp_rejected", 1, {"file_path": file_path, "rejection_reason": rejection_reason})


def _record_sub_element(strategy: str, tier: str) -> None:
    _engine_metrics.record("sub_elements_generated", 1, {"strategy": strategy, "tier": tier})


def _record_decomp_time(strategy: str, duration_ms: float) -> None:
    _engine_metrics.record_histogram("decomp_time_ms", duration_ms, {"strategy": strategy})


def _record_assembly_time(strategy: str, file_path: str, duration_ms: float) -> None:
    _engine_metrics.record_histogram("assembly_time_ms", duration_ms, {"strategy": strategy, "file": file_path})


def _record_simple_decompose_attempted(file_path: str) -> None:
    _engine_metrics.record("simple_decompose_attempted", 1, {"file_path": file_path})


def _record_simple_decompose_succeeded(file_path: str) -> None:
    _engine_metrics.record("simple_decompose_succeeded", 1, {"file_path": file_path})


def _record_simple_decompose_rejected(file_path: str) -> None:
    _engine_metrics.record("simple_decompose_rejected", 1, {"file_path": file_path})


def _record_moderate_ollama_whole_attempted(file_path: str) -> None:
    _engine_metrics.record("moderate_ollama_whole_attempted", 1, {"file_path": file_path})


def _record_moderate_ollama_whole_succeeded(file_path: str) -> None:
    _engine_metrics.record("moderate_ollama_whole_succeeded", 1, {"file_path": file_path})


def _record_generation_path(path: str, file_path: str) -> None:
    """Record a generation path routing decision (R2-S3)."""
    _engine_metrics.record("generation_path", 1, {"path": path, "file_path": file_path})


def _record_generation_path_outcome(path: str, outcome: str, file_path: str) -> None:
    """Record the outcome of a generation path attempt (R2-S3)."""
    _engine_metrics.record("generation_path_outcome", 1, {"path": path, "outcome": outcome, "file_path": file_path})


# Depth label cardinality cap (REQ-MP-914, R2-F3): depths beyond this
# value are bucketed as "N+" to prevent unbounded label cardinality.
_RECURSION_DEPTH_LABEL_CAP = 3

# Max chars for sub-element docstring hint context injection.
_MAX_DOC_HINT_CHARS = 512


def _cap_depth_label(depth: int) -> str:
    """Cap depth for metric labels to avoid high-cardinality (REQ-MP-914)."""
    if depth > _RECURSION_DEPTH_LABEL_CAP:
        return f"{_RECURSION_DEPTH_LABEL_CAP}+"
    return str(depth)


def _record_recursion_attempted(strategy: str, depth: int) -> None:
    """Emit recursion_attempted counter with capped depth label."""
    if _recursion_attempted is not None:
        _recursion_attempted.add(1, {
            "strategy": strategy, "depth": _cap_depth_label(depth),
        })


def _record_recursion_succeeded(strategy: str, depth: int) -> None:
    """Emit recursion_succeeded counter with capped depth label."""
    if _recursion_succeeded is not None:
        _recursion_succeeded.add(1, {
            "strategy": strategy, "depth": _cap_depth_label(depth),
        })


def _record_recursion_rejected(
    strategy: str, depth: int, rejection_reason: str,
) -> None:
    """Emit recursion_rejected counter with capped depth and bounded reason label."""
    if _recursion_rejected is not None:
        _recursion_rejected.add(1, {
            "strategy": strategy,
            "depth": _cap_depth_label(depth),
            "rejection_reason": rejection_reason,
        })


# ── Graph execution result types (REQ-MP-912) ──────────────────────


@dataclass
class _ClassifiedElement:
    """Pre-classified element with tier and contracts for process_file (M-3).

    Replaces the 9-element bare tuple that was fragile to positional
    destructuring errors.
    """

    priority: int
    element: ForwardElementSpec
    contracts: list[InterfaceContract]
    tier: TierClassification
    reasoning: str
    file_import_bump: int
    element_api_adjustment: int
    classification_signals: frozenset[str]

    @property
    def sort_key(self) -> tuple[int, str]:
        return (self.priority, self.element.name)


@dataclass
class _GraphExecutionResult:
    """Result from executing a full DecompositionPlanGraph."""

    success: bool
    sub_results: dict[str, str] = dc_field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    llm_calls: int = 0
    rejection_reason: Optional[str] = None
    # Recursion metadata for postmortem (REQ-MP-913, R1-S3)
    recursion_depth: int = 0
    decomposition_path: list[str] = dc_field(default_factory=list)


@dataclass
class _NodeExecutionResult:
    """Result from executing a single DecompositionNode."""

    success: bool
    code: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    llm_calls: int = 0
    rejection_reason: Optional[str] = None


@dataclass
class _GenerationOutcome:
    """Carries state from the Ollama retry loop to post-loop verification.

    Replaces ~15 scattered local variables that were shared between the
    generation loop and the structural/semantic verification sections
    of ``_handle_simple``.
    """

    code: str
    raw_output: str
    input_tokens: int = 0
    output_tokens: int = 0
    local_attempt: int = 1
    ast_valid_before: bool = False
    ast_valid_after: bool = False
    repair_recovered: bool = False
    repaired_code: Optional[str] = None
    repair_steps: list[str] = dc_field(default_factory=list)
    repair_attribution: Optional[RepairAttribution] = None
    repair_result: Optional[RepairResult] = None
    # If the loop exhausted all attempts, this holds the failure result.
    failure: Optional[ElementResult] = None


@dataclass
class _OllamaRetryOutcome:
    """Result from the unified Ollama retry loop (R2).

    Used by both file-whole and element-body paths.  The ``code`` field
    is ``None`` when all attempts failed.
    """

    code: str | None  # None = all attempts failed
    raw_output: str  # last raw LLM output
    input_tokens: int = 0
    output_tokens: int = 0
    llm_calls: int = 0
    elapsed_ms: float = 0.0
    last_failure_reason: str = ""  # empty on success


def _signature_from_ast_args(
    func_node: "ast.FunctionDef | ast.AsyncFunctionDef",
) -> Signature:
    """Build a Signature from an AST function node's arguments and return annotation.

    Handles positional-only, regular, *args, keyword-only, and **kwargs params.
    Skips individual parameters whose annotations fail to unparse rather than
    aborting the entire signature.
    """
    params: list[Param] = []
    args = func_node.args

    all_args = args.posonlyargs + args.args
    defaults_offset = len(all_args) - len(args.defaults)
    for i, arg in enumerate(all_args):
        try:
            annotation = ast.unparse(arg.annotation) if arg.annotation else None
        except (ValueError, TypeError):
            annotation = None
        default = None
        default_idx = i - defaults_offset
        if 0 <= default_idx < len(args.defaults):
            try:
                default = ast.unparse(args.defaults[default_idx])
            except (ValueError, TypeError):
                default = None
        params.append(Param(
            name=arg.arg,
            annotation=annotation,
            default=default,
            kind=ParamKind.POSITIONAL_ONLY if arg in args.posonlyargs else ParamKind.POSITIONAL,
        ))

    if args.vararg:
        ann = ast.unparse(args.vararg.annotation) if args.vararg.annotation else None
        params.append(Param(name=args.vararg.arg, annotation=ann, kind=ParamKind.VAR_POSITIONAL))

    for j, kwarg in enumerate(args.kwonlyargs):
        ann = ast.unparse(kwarg.annotation) if kwarg.annotation else None
        default = None
        if j < len(args.kw_defaults) and args.kw_defaults[j] is not None:
            default = ast.unparse(args.kw_defaults[j])
        params.append(Param(name=kwarg.arg, annotation=ann, default=default, kind=ParamKind.KEYWORD_ONLY))

    if args.kwarg:
        ann = ast.unparse(args.kwarg.annotation) if args.kwarg.annotation else None
        params.append(Param(name=args.kwarg.arg, annotation=ann, kind=ParamKind.VAR_KEYWORD))

    ret_ann = ast.unparse(func_node.returns) if func_node.returns else None
    return Signature(params=params, return_annotation=ret_ann)


def _extract_docstring_hint(func_node: "ast.FunctionDef | ast.AsyncFunctionDef") -> Optional[str]:
    """Extract the first line of a function's docstring, or None."""
    if (
        func_node.body
        and isinstance(func_node.body[0], ast.Expr)
        and isinstance(func_node.body[0].value, ast.Constant)
        and isinstance(func_node.body[0].value.value, str)
    ):
        first_line = func_node.body[0].value.value.strip().split("\n")[0]
        return first_line or None
    return None


def _enrich_file_spec_from_skeleton(
    element: ForwardElementSpec,
    file_spec: ForwardFileSpec,
    skeleton: str,
) -> ForwardFileSpec:
    """Add missing method elements extracted from the skeleton AST.

    When plan ingestion produces a CLASS element without separate method
    entries (e.g. gRPC service classes), the ClassDecomposeStrategy rejects
    it because ``_methods_are_separate()`` fails. This function parses the
    skeleton to discover method stubs inside the class and adds them as
    synthetic ForwardElementSpec entries so decomposition can proceed.

    Only adds methods that are not already present in file_spec.elements.
    Returns the original file_spec unchanged if no new methods are found.
    """
    if element.kind != ElementKind.CLASS or not skeleton:
        return file_spec

    try:
        tree = ast.parse(skeleton)
    except SyntaxError:
        logger.debug("Skeleton parse failed for enrichment of %s", element.name)
        return file_spec

    # Find the class node in the skeleton
    class_node = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == element.name:
            class_node = node
            break
    if class_node is None:
        return file_spec

    # Collect existing child element names for this class
    existing_names = {
        e.name for e in file_spec.elements
        if e.parent_class == element.name
    }

    new_specs: list[ForwardElementSpec] = []
    for child in class_node.body:
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if child.name in existing_names:
            continue

        kind = (
            ElementKind.ASYNC_METHOD if isinstance(child, ast.AsyncFunctionDef)
            else ElementKind.METHOD
        )
        new_specs.append(ForwardElementSpec(
            kind=kind,
            name=child.name,
            signature=_signature_from_ast_args(child),
            parent_class=element.name,
            docstring_hint=_extract_docstring_hint(child),
            source_contract_id=f"skeleton-enrichment-{element.name}.{child.name}",
        ))

    if not new_specs:
        return file_spec

    logger.info(
        "Enriched file_spec for class %s with %d method(s) from skeleton: %s",
        element.name, len(new_specs),
        ", ".join(s.name for s in new_specs),
    )

    # Create new ForwardFileSpec with enriched elements (model is frozen)
    return ForwardFileSpec(
        file=file_spec.file,
        elements=list(file_spec.elements) + new_specs,
        imports=file_spec.imports,
        dependencies=file_spec.dependencies,
    )


def _compute_context_checksum(
    element: ForwardElementSpec,
    file_path: str,
) -> str:
    """Compute a structural context checksum for cache staleness detection.

    Delegates to the shared ``compute_element_context_checksum`` so that the
    same algorithm is used everywhere (plan ingestion EMIT, engine, backfill).
    """
    sig_str = str(element.signature) if element.signature else ""
    bases_list = [str(b) for b in (getattr(element, "bases", None) or [])]
    dec_list = [str(d) for d in (getattr(element, "decorators", None) or [])]
    return compute_element_context_checksum(
        element_name=element.name,
        element_kind=element.kind.value if hasattr(element.kind, "value") else str(element.kind),
        signature=sig_str,
        parent_class=element.parent_class or "",
        bases=bases_list or None,
        decorators=dec_list or None,
    )


def _resolve_element_id(element: ForwardElementSpec, file_path: str) -> Optional[str]:
    """Derive a stable element ID from the ForwardElementSpec.

    Uses ``source_contract_id`` when present; otherwise falls back to
    ``make_element_id()`` derived from (file_path, parent_class, name).
    Returns ``None`` only when name is missing (should never happen).

    **ID stability**: ``source_contract_id`` is set by the forward manifest
    extractor using category abbreviations (``"fn"``, ``"cls"``) rather than
    element kinds.  This keeps IDs stable across element kind reclassifications
    (e.g. FUNCTION→METHOD after class linking).  The fallback path uses
    ``element.kind.value`` and is therefore kind-sensitive — always prefer
    ``source_contract_id`` for cross-run cache stability.
    """
    if element.source_contract_id:
        return element.source_contract_id
    if not element.name:
        return None
    return make_element_id(
        kind=element.kind.value if hasattr(element.kind, "value") else str(element.kind),
        name=element.name,
        file_path=file_path,
        parent_class=element.parent_class,
    )


# AC-R7/F7: _CODE_GEN_SYSTEM_PROMPT was the old default that contradicted
# body-only prompts.  Retained as alias for prime_adapter cloud escalation
# (full-element generation, not body-only).
_CODE_GEN_SYSTEM_PROMPT = (
    "You are a Python code generator. "
    "Output ONLY valid Python code — no markdown fences, no explanations. "
    "Use 4-space indentation consistently."
)

_ELEMENT_BODY_SYSTEM_PROMPT = (
    "You are a Python code generator. "
    "Output the indented body lines of the target function.\n"
    "\n"
    "FORMAT: Start every line with exactly 4 spaces. "
    "Output raw Python code — no ```python fences, no prose, no def line.\n"
    "\n"
    "IMPORTS: Use ONLY imports shown in the prompt. "
    "Do not add import statements to your output.\n"
    "\n"
    "SCOPE: Output ONLY the body of the single requested function. "
    "Stop after the last line of the body. "
    "Do not output additional functions, classes, or statements."
)

# System prompt for file-level Ollama-whole generation.
# Instead of decomposing into individual element bodies, the model receives
# the complete skeleton file and fills ALL stubs in one pass.
_FILE_WHOLE_SYSTEM_PROMPT = (
    "You are a Python code generator. "
    "You receive a skeleton Python file with `raise NotImplementedError` stubs.\n"
    "\n"
    "TASK: Replace every `raise NotImplementedError` with a working implementation. "
    "Output the COMPLETE file with all stubs filled.\n"
    "\n"
    "PRESERVE: Keep all existing imports, class definitions, signatures, and decorators "
    "exactly as given. Use 4-space indentation. "
    "Each function body goes directly under its def line — never nest a function inside itself.\n"
    "\n"
    "FORMAT: Output raw Python code only. "
    "No ```python fences, no explanations, no commentary."
)


def build_escalation_context(
    element_name: str,
    file_path: str,
    tier: TierClassification,
    reason: EscalationReason,
    detail: str,
    last_code: Optional[str] = None,
    last_error: Optional[str] = None,
    raw_output: Optional[str] = None,
    repaired_code: Optional[str] = None,
    repair_steps: Optional[list[str]] = None,
    local_model: Optional[str] = None,
    element_fqn: Optional[str] = None,
    escalation_handoff: Optional[EscalationHandoff] = None,
) -> EscalationResult:
    """Build a reusable EscalationResult for element escalation.

    Centralises escalation payload construction so that all call-sites
    produce consistently structured results.

    Args:
        element_name: Name of the element being escalated.
        file_path: Source file path for the element.
        tier: Tier classification at time of escalation.
        reason: Why the element is being escalated.
        detail: Human-readable detail string.
        last_code: Optional last generated code before escalation.
        last_error: Optional error string.
        escalation_handoff: Optional Keiyaku-compliant structured handoff
            (K-6). When provided, attached to the EscalationContext for
            downstream consumers to use instead of prose fields.

    Returns:
        An EscalationResult populated with the provided context.
    """
    if element_fqn is None:
        element_fqn = element_name
    context = None
    if raw_output or repaired_code or repair_steps or local_model or escalation_handoff:
        context = EscalationContext(
            element_fqn=element_fqn,
            local_model=local_model or "",
            raw_output=raw_output or "",
            repair_steps_applied=repair_steps or [],
            repaired_code=repaired_code,
            error=last_error or detail,
            escalation_handoff=escalation_handoff,
        )

    return EscalationResult(
        reason=reason,
        detail=detail,
        last_code=last_code,
        last_error=last_error,
        context=context,
    )


def _build_escalation_handoff(
    element: ForwardElementSpec,
    tier: TierClassification,
    local_model: str,
    attempt_count: int,
    reason: EscalationReason,
    failure_message: str,
    raw_output: Optional[str] = None,
    repair_outcome: Optional[EscalationRepairOutcome] = None,
) -> EscalationHandoff:
    """Build a Keiyaku-compliant EscalationHandoff from element data (K-6).

    Centralises handoff construction so that all escalation sites in
    ``_handle_simple`` produce consistently structured contracts.
    """
    sig_str = ""
    if element.signature:
        params = ", ".join(
            f"{p.name}: {p.annotation}" if p.annotation else p.name
            for p in element.signature.params
        )
        ret = f" -> {element.signature.return_annotation}" if element.signature.return_annotation else ""
        sig_str = f"({params}){ret}"

    element_fqn = (
        f"{element.parent_class}.{element.name}"
        if element.parent_class else element.name
    )

    return EscalationHandoff(
        element_fqn=element_fqn,
        original_tier=tier.value.upper(),
        local_model=local_model,
        attempt_count=attempt_count,
        failure_category=reason.value,
        failure_message=failure_message,
        raw_output_lines=len((raw_output or "").splitlines()),
        repair=repair_outcome,
        element_signature=sig_str,
        element_kind=element.kind.value.upper(),
        parent_class=element.parent_class,
    )


def _build_file_whole_prompt(
    skeleton: str,
    file_spec: ForwardFileSpec,
    task_description: Optional[str] = None,
    domain_constraints: Optional[list[str]] = None,
    design_doc_sections: Optional[list[str]] = None,
    contracts: Optional[list[InterfaceContract]] = None,
    completed_file_examples: Optional[list[str]] = None,
) -> str:
    """Build a prompt for file-level Ollama-whole generation.

    Instead of asking for individual element bodies, this sends the full
    skeleton and asks the model to fill ALL stubs in one pass.  This matches
    how the model naturally generates code (complete files) and avoids the
    body-only fragmentation that confuses small local models.

    AC-R16: Enriched with design docs, binding constraints, and completed
    file examples so the file-whole path has context parity with the
    element-by-element path.

    Args:
        skeleton: Complete skeleton file with ``raise NotImplementedError`` stubs.
        file_spec: File spec for context (imports, element names).
        task_description: Optional feature-level description from seed.
        domain_constraints: Optional domain constraints from plan ingestion.
        design_doc_sections: Optional design doc sections for implementation context.
        contracts: Optional binding constraints for elements in this file.
        completed_file_examples: Optional successfully-generated file snippets
            from earlier files in the same seed (file-level few-shot).

    Returns:
        The constructed prompt string.
    """
    # Prompt structure: plain-text instructions ABOVE the skeleton, separated
    # by a clear delimiter.  Prior format used Python comments for everything,
    # which caused small models to echo the instruction block as part of the
    # file — burning output tokens on prompt repetition and triggering stop
    # sequences before the actual implementation.
    instructions: list[str] = []

    instructions.append(
        "Complete this Python file by replacing every `raise NotImplementedError` "
        "with a working implementation."
    )
    instructions.append(
        "Output ONLY the complete Python file. No markdown fences, no explanations, "
        "no comments that aren't in the original skeleton."
    )

    if task_description:
        instructions.append(f"\nTask: {task_description}")

    if domain_constraints:
        instructions.append("\nConstraints:")
        for dc in domain_constraints:
            instructions.append(f"- {dc}")

    # AC-R16: Design documentation context
    if design_doc_sections:
        instructions.append("\nImplementation context:")
        for section in design_doc_sections:
            instructions.append(section)

    # AC-R16: Binding constraints
    if contracts:
        constraint_lines: list[str] = []
        for c in contracts:
            level = "BINDING" if c.confidence == ContractConfidence.EXPLICIT else "ADVISORY"
            desc = c.binding_text or c.description or "unspecified"
            cat = f" ({c.category.value})" if c.category else ""
            constraint_lines.append(f"- [{level}]{cat} {desc}")
        if constraint_lines:
            instructions.append("\nInterface constraints:")
            instructions.extend(constraint_lines)

    # Element manifest
    implementable = [e for e in file_spec.elements if e.kind != ElementKind.CLASS]
    if implementable:
        instructions.append(f"\nElements to implement ({len(implementable)}):")
        for i, el in enumerate(implementable, 1):
            fqn = f"{el.parent_class}.{el.name}" if el.parent_class else el.name
            hint = ""
            if el.docstring_hint:
                hint = f' — "{el.docstring_hint}"'
            elif el.signature and el.signature.return_annotation:
                hint = f" -> {el.signature.return_annotation}"
            instructions.append(f"{i}. {fqn}{hint}")

    # AC-R16: Completed file examples from earlier files in the same seed.
    if completed_file_examples:
        for idx, example in enumerate(completed_file_examples[:2], 1):
            instructions.append(f"\n--- Example of a completed file ({idx}) ---")
            instructions.append(example)

    # Clear delimiter between instructions and skeleton
    instructions.append("\n--- Skeleton file (fill in the stubs) ---\n")

    return "\n".join(instructions) + skeleton


def _strip_fences(code: str) -> str:
    """Strip markdown code fences from LLM output."""
    stripped = code.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped


from startd8.utils.ast_checks import is_stub_only_body as _is_stub_only_body  # noqa: E402


def _skeleton_has_stubs(skeleton: str) -> bool:
    """Return True if any function/method body in *skeleton* is a NotImplementedError stub.

    Uses AST parsing + ``is_stub_only_body()`` to avoid false positives on
    conditional ``raise NotImplementedError`` branches and string literals
    containing the phrase.  Falls back to string search if AST parsing fails
    (e.g. skeleton has placeholder syntax).
    """
    try:
        tree = ast.parse(skeleton)
    except SyntaxError:
        # Fallback: if the skeleton can't be parsed, use the string check
        # as a conservative approximation.
        return "raise NotImplementedError" in skeleton
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if _is_stub_only_body(node.body):
                return True
    return False


def _remove_toplevel_nested_duplicates(
    code: str,
    original_skeleton: Optional[str] = None,
) -> str:
    """Remove top-level functions that duplicate nested functions.

    When the decomposer creates separate elements for inner functions
    (e.g. Flask ``@app.route`` handlers nested inside a factory function),
    the splicer may insert the generated code as a top-level function,
    creating a duplicate.  This function detects and removes the
    top-level copy, keeping the nested definition intact.

    If *original_skeleton* is provided, functions that were defined at top
    level in the skeleton are preserved — they belong at top level and the
    nested copy is the accidental duplicate (e.g. an LLM inlining a helper
    inside a factory function).
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code

    # Determine which function names were originally at top level in the
    # skeleton.  These should never be removed from the top level.
    skeleton_toplevel_names: set[str] = set()
    if original_skeleton:
        try:
            skel_tree = ast.parse(original_skeleton)
            for node in ast.iter_child_nodes(skel_tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    skeleton_toplevel_names.add(node.name)
        except SyntaxError:
            pass

    # Collect names of functions defined *inside* other top-level functions
    nested_names: set[str] = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                if (
                    child is not node
                    and isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                ):
                    nested_names.add(child.name)

    if not nested_names:
        return code

    # Find top-level functions whose name matches a nested function
    to_remove: list[ast.AST] = []
    for node in ast.iter_child_nodes(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in nested_names
            # Never remove a function that was top-level in the skeleton
            and node.name not in skeleton_toplevel_names
            # Only remove if it's NOT the parent that contains the nested def
            and not any(
                isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                and child.name == node.name
                and child is not node
                for child in ast.walk(node)
            )
        ):
            to_remove.append(node)

    # Log functions preserved because they exist at top level in skeleton
    preserved = nested_names & skeleton_toplevel_names
    if preserved:
        logger.info(
            "Preserved top-level functions also in skeleton: %s",
            ", ".join(sorted(preserved)),
        )

    if not to_remove:
        return code

    # Remove by line range (process bottom-up to preserve line numbers)
    lines = code.splitlines()
    for node in sorted(to_remove, key=lambda n: n.lineno, reverse=True):
        start = node.lineno - 1  # 0-based
        end = node.end_lineno  # already 1-based, so this is exclusive
        # Include any decorators
        if node.decorator_list:
            start = node.decorator_list[0].lineno - 1
        # Remove trailing blank lines
        while end < len(lines) and lines[end].strip() == "":
            end += 1
        logger.info(
            "Removed duplicate top-level function '%s' (lines %d–%d) "
            "— already defined as nested function",
            node.name, start + 1, end,
        )
        del lines[start:end]

    return "\n".join(lines)


def _validate_file_whole_result(
    generated_code: str,
    skeleton: str,
    file_spec: ForwardFileSpec,
) -> tuple[bool, str, list[str]]:
    """Validate a file-level Ollama-whole generation result.

    Checks:
    1. AST parses successfully
    2. No stub-only function/method bodies (AST-based)
    3. No nested duplicate function definitions
    4. Structural position: elements at correct nesting level
    5. No skeleton markers remain

    Returns:
        (success, reason, missing_elements) tuple.  ``missing_elements`` is
        populated for soft failures (stubs/missing) but empty for hard failures
        (syntax error, nested duplicates, skeleton markers).  Callers can use
        the missing list for partial acceptance.
    """
    # Strip markdown fences if present
    code = extract_code_from_response(generated_code)

    if not code:
        return False, "empty output", []

    # AST parse — hard fail
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"ast.parse() failed: {e}", []

    # Check for nested duplicate function definitions — hard fail
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                if (
                    child is not node
                    and isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and child.name == node.name
                ):
                    return False, f"nested duplicate function: {node.name}", []

    # Check for skeleton markers — hard fail
    if SKELETON_MARKER in code:
        return False, "contains skeleton markers", []

    # ── Soft-fail collection ──
    # Stubs and missing elements are collected for partial acceptance.
    soft_missing: list[str] = []

    # Check for stub-only bodies (AST-based — no false positives on branch usage)
    stub_names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if _is_stub_only_body(node.body):
                stub_names.append(node.name)
    if stub_names:
        soft_missing.extend(stub_names)

    # Structural position check: elements at correct nesting level
    top_classes: dict[str, set[str]] = {}
    top_functions: set[str] = set()
    top_assigns: set[str] = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            methods: set[str] = set()
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.add(child.name)
            top_classes[node.name] = methods
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            top_functions.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    top_assigns.add(target.id)

    missing: list[str] = []
    missing_element_names: list[str] = []
    for el in file_spec.elements:
        if el.kind == ElementKind.CLASS:
            if el.name not in top_classes:
                missing.append(f"class {el.name}")
                missing_element_names.append(el.name)
        elif el.parent_class:
            fqn = f"{el.parent_class}.{el.name}"
            if el.parent_class not in top_classes:
                missing.append(f"class {el.parent_class} (parent of {el.name})")
                missing_element_names.append(el.name)
            elif el.name not in top_classes.get(el.parent_class, set()):
                missing.append(fqn)
                missing_element_names.append(el.name)
        elif el.kind in (ElementKind.FUNCTION, ElementKind.ASYNC_FUNCTION):
            if el.name not in top_functions:
                missing.append(f"function {el.name}")
                missing_element_names.append(el.name)
        elif el.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE):
            if el.name not in top_assigns:
                missing.append(f"constant {el.name}")
                missing_element_names.append(el.name)

    soft_missing.extend(missing_element_names)

    if stub_names and missing:
        reason = (
            f"stub-only NotImplementedError bodies: {', '.join(stub_names)}; "
            f"missing elements: {', '.join(missing)}"
        )
        return False, reason, soft_missing
    if stub_names:
        return False, f"stub-only NotImplementedError bodies: {', '.join(stub_names)}", soft_missing
    if missing:
        return False, f"missing elements: {', '.join(missing)}", soft_missing

    return True, "all checks passed", []


class MicroPrimeEngine:
    """Main orchestrator for local-first code generation.

    Processes manifest elements through classification, template matching,
    local model generation, repair, and body splicing.

    Args:
        config: Engine configuration.
        template_registry: Optional custom template registry.
        metrics_collector: Optional metrics collector for observability.
    """

    _CIRCUIT_BREAKER_THRESHOLD: int = 8   # per-file (raised from 3: run-038 showed 3 is too aggressive for files with many elements)
    _RUN_BREAKER_THRESHOLD: int = 12     # per-run (E1: cross-file systemic failure; raised proportionally)
    _TIER_PRIORITY: dict[TierClassification, int] = {
        TierClassification.TRIVIAL: 0,
        TierClassification.SIMPLE: 1,
        TierClassification.MODERATE: 2,
        TierClassification.COMPLEX: 3,
    }

    def __init__(
        self,
        config: Optional[MicroPrimeConfig] = None,
        template_registry: Optional[TemplateRegistry] = None,
        metrics_collector: Optional[MetricsCollector] = None,
        element_registry: Optional[ElementRegistry] = None,
    ) -> None:
        self._config = config or MicroPrimeConfig()
        self._templates = template_registry or TemplateRegistry(
            enabled=self._config.templates_enabled,
        )
        self._metrics = metrics_collector or MetricsCollector()
        self._completed: list[dict[str, Any]] = []
        # Circuit breaker state (R3-S2 + E1)
        self._consecutive_failures: int = 0       # per-file, reset between files
        self._run_consecutive_failures: int = 0   # per-run (E1), persists across files
        self._file_circuit_open: bool = False      # per-file breaker state
        # Element fingerprint success cache (R3-S4)
        self._success_cache: dict[str, Optional[str]] = {}
        # Element registry for cross-task/cross-run caching (ER-007)
        self._element_registry = element_registry
        # Decomposer for MODERATE elements (REQ-MP-900)
        self._decomposer = ModerateDecomposer(config=self._config, template_registry=self._templates)
        # Phase 3: Function-body decomposer for SIMPLE elements (lazy import, Leg 11 #55)
        self._function_body_decomposer: Optional[Any] = None
        if self._config.enable_simple_decomposer:
            from startd8.micro_prime.clause_mapper import FunctionBodyDecomposer
            self._function_body_decomposer = FunctionBodyDecomposer(
                template_registry=self._templates,
                confidence_threshold=self._config.simple_decomposer_confidence_threshold,
            )
        # Manifest reference for _handle_moderate (set by process_file, None for process_element)
        self._current_manifest: Optional[ForwardManifest] = None
        # Domain constraints set by process_file, None for process_element
        self._current_domain_constraints: Optional[list[str]] = None
        # Cached Ollama agent (C-1: avoid re-creation per element)
        self._ollama_agent: Optional[Any] = None
        # Cached semantic verification agent (optional)
        self._semantic_agent: Optional[Any] = None

    @property
    def config(self) -> MicroPrimeConfig:
        return self._config

    @property
    def metrics_collector(self) -> MetricsCollector:
        return self._metrics

    @property
    def _circuit_open(self) -> bool:
        """True if either per-file or per-run breaker is tripped (E1)."""
        return (
            self._file_circuit_open
            or self._run_consecutive_failures >= self._RUN_BREAKER_THRESHOLD
        )

    def _record_local_failure(self) -> None:
        """Increment circuit breaker counters and trip breakers if thresholds are met.

        Centralises the per-file and per-run breaker mutation that was
        previously duplicated in ``_process_element_with_tier`` and
        ``_handle_moderate``.
        """
        self._consecutive_failures += 1
        self._run_consecutive_failures += 1
        if (
            self._consecutive_failures >= self._CIRCUIT_BREAKER_THRESHOLD
            and not self._file_circuit_open
        ):
            self._file_circuit_open = True
            logger.warning(
                "Circuit breaker tripped (per-file): %d consecutive local failures",
                self._consecutive_failures,
            )
        if self._run_consecutive_failures == self._RUN_BREAKER_THRESHOLD:
            logger.warning(
                "Circuit breaker tripped (per-run): %d consecutive failures across files",
                self._run_consecutive_failures,
            )

    def reset_circuit_breaker(self) -> None:
        """Reset the per-file circuit breaker to closed state.

        Callers should invoke this between files to allow local
        generation to resume after transient failures.  The per-run
        breaker (E1) persists across files — use ``clear_cache()``
        or a new engine instance to reset it.
        """
        self._consecutive_failures = 0
        self._file_circuit_open = False

    def clear_cache(self) -> None:
        """Clear the element fingerprint success cache and reset per-run breaker."""
        self._success_cache.clear()  # dict[fingerprint, code]
        self._run_consecutive_failures = 0

    def process_element(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        skeleton: str,
        contracts: Optional[list[InterfaceContract]] = None,
        design_doc_sections: Optional[list[str]] = None,
        task_description: Optional[str] = None,
    ) -> ElementResult:
        """Process a single element through the pipeline.

        Classifies the element, then delegates to ``_process_element_with_tier``.
        Use this entry point when the tier is not yet known.  When calling
        from ``process_file`` (which pre-classifies for sorting), prefer
        ``_process_element_with_tier`` directly to avoid double classification.

        Args:
            element: Manifest element to process.
            file_spec: File spec for context.
            skeleton: Current skeleton file content.
            contracts: Binding constraints for this element.
            design_doc_sections: Optional design doc sections for prompt context.
            task_description: Optional feature-level task description from seed.

        Returns:
            ElementResult with success/failure and optional code.
        """
        element_contracts = contracts or []

        # Enrich file_spec with skeleton-derived methods (D6: standalone path parity)
        if element.kind == ElementKind.CLASS and skeleton:
            file_spec = _enrich_file_spec_from_skeleton(element, file_spec, skeleton)

        tier, reasoning, details = classify_element_with_details(
            element, file_spec, element_contracts,
            template_registry=self._templates,
            config=self._config,
        )

        return self._process_element_with_tier(
            element, file_spec, skeleton, element_contracts,
            tier=tier, reasoning=reasoning,
            api_file_import_bump=details.file_import_bump,
            api_element_adjustment=details.element_api_adjustment,
            design_doc_sections=design_doc_sections,
            task_description=task_description,
            classification_signals=details.classification_signals,
        )

    def _process_element_with_tier(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        skeleton: str,
        contracts: list[InterfaceContract],
        tier: TierClassification,
        reasoning: str,
        api_file_import_bump: int = 0,
        api_element_adjustment: int = 0,
        ollama_available: bool = True,
        design_doc_sections: Optional[list[str]] = None,
        task_description: Optional[str] = None,
        classification_signals: Optional[frozenset[str]] = None,
        complexity_signals: Optional[TaskComplexitySignals] = None,
    ) -> ElementResult:
        """Process a single element with a pre-computed tier classification.

        This is the core processing method.  ``process_element`` classifies
        first, then calls here.  ``process_file`` pre-classifies for sorting
        and calls here directly, avoiding redundant classification.

        Args:
            element: Manifest element to process.
            file_spec: File spec for context.
            skeleton: Current skeleton file content.
            contracts: Binding constraints for this element.
            tier: Pre-computed tier classification.
            reasoning: Classification reasoning string.
            design_doc_sections: Optional design doc sections for prompt context.
            task_description: Optional feature-level task description from seed.
            classification_signals: Structured signal names from classification
                (e.g. ``{"orchestrator", "external_api"}``).  Forwarded to
                the decomposer for strategy selection (REQ-MP-902).
            complexity_signals: Optional TaskComplexitySignals threaded from
                classify_tier() via ClassificationResult (Keiyaku D-1).

        Returns:
            ElementResult with success/failure and optional code.
        """
        file_path = file_spec.file

        logger.debug(
            "Classified %s as %s: %s", element.name, tier.value, reasoning,
        )

        # Step 1a: Check success cache (R3-S4) — skip re-generation
        fingerprint = f"{element.parent_class or ''}:{element.name}:{file_path}:{tier.value}"
        if fingerprint in self._success_cache:
            cached_code = self._success_cache[fingerprint]
            logger.debug(
                "Cache hit for %s — returning cached success (code=%s)",
                fingerprint, "present" if cached_code else "none",
            )
            result = ElementResult.make_cached(
                element.name, file_path, tier, reasoning, cached_code,
            )
            result.api_file_import_bump = api_file_import_bump
            result.api_element_adjustment = api_element_adjustment
            self._metrics.record(result)
            return result

        # Step 1a′: Element registry cache-through (REQ-MP-1102)
        element_id = _resolve_element_id(element, file_path)
        ctx_checksum = _compute_context_checksum(element, file_path)
        if self._element_registry is not None and element_id:
            try:
                t0 = time.monotonic()
                cached = self._element_registry.get(element_id)
                lookup_ms = (time.monotonic() - t0) * 1000
                if lookup_ms > 100:
                    logger.warning(
                        "Element registry lookup took %.1fms for %s — exceeds 100ms threshold",
                        lookup_ms, element_id,
                    )
                if cached is not None and cached.extra.get("code"):
                    # Staleness check: verify context_checksum matches current context
                    if is_stale(cached, ctx_checksum):
                        logger.info(
                            "Element registry STALE: %s (checksum %s != %s) — regenerating",
                            element_id, cached.context_checksum, ctx_checksum,
                        )
                    else:
                        cached_code = cached.extra["code"]
                        logger.info("Element registry HIT: %s", element_id)
                        result = ElementResult.make_cached(
                            element.name, file_path, tier, reasoning, cached_code,
                            source="element_registry",
                        )
                        result.api_file_import_bump = api_file_import_bump
                        result.api_element_adjustment = api_element_adjustment
                        self._metrics.record(result)
                        return result
                else:
                    logger.info(
                        "Element registry MISS: %s (element=%s, kind=%s)",
                        element_id, element.name,
                        element.kind.value if hasattr(element.kind, "value") else element.kind,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Element registry lookup failed for %s: %s — falling through to generation",
                    element_id, exc,
                )

        # Step 1b: Circuit breaker (R3-S2) — escalate immediately if open
        if self._circuit_open and tier in (
            TierClassification.TRIVIAL,
            TierClassification.SIMPLE,
        ):
            logger.warning(
                "Circuit breaker open — escalating %s without local attempt",
                element.name,
            )
            result = ElementResult.make_escalation(
                element.name, file_path, tier, reasoning,
                build_escalation_context(
                    element_name=element.name, file_path=file_path, tier=tier,
                    reason=EscalationReason.CIRCUIT_BREAKER,
                    detail=f"Circuit breaker tripped after {self._CIRCUIT_BREAKER_THRESHOLD} consecutive failures",
                ),
                generation_strategy="circuit_breaker",
            )
            result.api_file_import_bump = api_file_import_bump
            result.api_element_adjustment = api_element_adjustment
            self._metrics.record(result)
            return result

        # Ollama availability gate (REQ-MP-503)
        if not ollama_available and tier in (
            TierClassification.SIMPLE,
            TierClassification.MODERATE,
        ):
            logger.warning(
                "Ollama unavailable — escalating %s (%s) without local attempt",
                element.name, tier.value,
            )
            result = ElementResult.make_escalation(
                element.name, file_path, tier, reasoning,
                build_escalation_context(
                    element_name=element.name, file_path=file_path, tier=tier,
                    reason=EscalationReason.OLLAMA_UNAVAILABLE,
                    detail="Ollama unavailable — local generation skipped",
                ),
                generation_strategy="ollama_unavailable",
            )
            result.api_file_import_bump = api_file_import_bump
            result.api_element_adjustment = api_element_adjustment
            self._metrics.record(result)
            return result

        # Step 2: Route by tier
        if tier == TierClassification.TRIVIAL:
            result = self._handle_trivial(
                element, file_spec, skeleton, contracts, file_path, reasoning,
            )
        elif tier == TierClassification.SIMPLE:
            result = self._handle_simple(
                element, file_spec, skeleton, contracts, file_path, reasoning,
                design_doc_sections=design_doc_sections,
                task_description=task_description,
            )
        elif tier == TierClassification.MODERATE:
            result = self._handle_moderate(
                element, file_spec, self._current_manifest, skeleton, contracts,
                file_path, reasoning,
                design_doc_sections=design_doc_sections,
                task_description=task_description,
                classification_signals=set(classification_signals) if classification_signals else None,
                complexity_signals=complexity_signals,
            )
        else:
            # COMPLEX only — immediate escalation
            logger.info(
                "Element %s in %s classified as COMPLEX — immediate escalation "
                "(reason: %s)",
                element.name, file_path, reasoning,
            )
            result = ElementResult.make_escalation(
                element.name, file_path, tier, reasoning,
                build_escalation_context(
                    element_name=element.name, file_path=file_path, tier=tier,
                    reason=EscalationReason.TIER_TOO_HIGH,
                    detail=f"Tier {tier.value}: {reasoning}",
                ),
                generation_strategy="complex_escalation",
            )

        # Stamp parent_class for downstream spec lookup (e.g. cloud escalation)
        result.parent_class = element.parent_class
        result.element_kind = element.kind.value
        result.api_file_import_bump = api_file_import_bump
        result.api_element_adjustment = api_element_adjustment

        # Step 3: Update circuit breaker and cache based on result
        if result.success:
            self._consecutive_failures = 0
            if not result.template_used:
                self._run_consecutive_failures = 0  # E1: only Ollama success proves Ollama is working
            self._success_cache[fingerprint] = result.code
            # REQ-MP-1102: Persist to element registry after successful generation
            if self._element_registry is not None and element_id and result.code:
                try:
                    existing = self._element_registry.get(element_id)
                    if existing is not None:
                        existing.extra["code"] = result.code
                        existing.extra["generator"] = self._config.model or "ollama:unknown"
                        existing.extra["tier"] = tier.value
                        existing.context_checksum = ctx_checksum
                        self._element_registry.put(existing)
                    else:
                        new_entry = ElementEntry(
                            element_id=element_id,
                            kind=element.kind.value if hasattr(element.kind, "value") else str(element.kind),
                            name=element.name,
                            file_path=file_path,
                            parent_class=element.parent_class,
                            source_contract_id=element.source_contract_id,
                            context_checksum=ctx_checksum,
                            extra={
                                "code": result.code,
                                "generator": self._config.model or "ollama:unknown",
                                "tier": tier.value,
                            },
                        )
                        self._element_registry.put(new_entry)
                    self._element_registry.set_phase_status(
                        element_id, "implement", "generated",
                        metadata={
                            "generation_strategy": result.generation_strategy,
                            "model": result.model,
                            "generation_time_ms": result.generation_time_ms,
                            "input_tokens": result.input_tokens,
                            "output_tokens": result.output_tokens,
                            "ast_valid_before_repair": result.ast_valid_before_repair,
                        },
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Element registry write failed for %s: %s — generation result not persisted",
                        element_id, exc,
                    )
        elif tier in (TierClassification.TRIVIAL, TierClassification.SIMPLE):
            self._record_local_failure()

        self._metrics.record(result)
        return result

    def process_file(
        self,
        file_spec: ForwardFileSpec,
        manifest: ForwardManifest,
        skeleton: str,
        design_doc_sections: Optional[list[str]] = None,
        ollama_available: bool = True,
        task_description: Optional[str] = None,
        domain_constraints: Optional[list[str]] = None,
    ) -> FileResult:
        """Process all elements in a file.

        Elements are processed in tier-sorted order (REQ-MP-704 AC-2):
        TRIVIAL first (alphabetical), then SIMPLE (alphabetical), then
        MODERATE/COMPLEX. This ensures TRIVIAL template results feed as
        few-shot examples into subsequent SIMPLE generation.

        Args:
            file_spec: File spec with elements to process.
            manifest: Full manifest for contract lookup.
            skeleton: Skeleton file content.
            design_doc_sections: Optional design doc sections for prompt context.
            task_description: Optional feature-level task description from seed.

        Returns:
            FileResult with all element results and updated skeleton.
        """
        # Routing hierarchy (AC-R1):
        # 1. File-whole Ollama (primary) — complete file in one shot
        # 2. Element-by-element (fallback) — when file-whole ineligible or fails
        # 3. Cloud escalation (last resort) — per-element cloud retry
        file_result = FileResult(file_path=file_spec.file)
        self.reset_circuit_breaker()
        self._current_manifest = manifest
        self._current_domain_constraints = domain_constraints
        current_skeleton = skeleton

        # Enrich file_spec with methods from skeleton for classes whose
        # methods aren't separate manifest elements (e.g. gRPC servicers).
        # Must happen before classification so enriched methods enter the
        # processing loop as individual SIMPLE/TRIVIAL elements.
        enriched_file_spec = file_spec
        for element in file_spec.elements:
            if element.kind == ElementKind.CLASS:
                enriched_file_spec = _enrich_file_spec_from_skeleton(
                    element, enriched_file_spec, skeleton,
                )

        # Defense-in-depth: warn if any CLASS element still has no child
        # methods after enrichment.  This means class_decompose will reject
        # it, forcing cloud fallback.  Root cause is usually a dotted
        # api_signature that _parse_python_signature couldn't handle.
        for element in enriched_file_spec.elements:
            if element.kind == ElementKind.CLASS:
                child_count = sum(
                    1 for e in enriched_file_spec.elements
                    if e.parent_class == element.name
                )
                if child_count == 0:
                    logger.warning(
                        "Class %s in %s has no child method elements after "
                        "enrichment — class_decompose will fail. Check if "
                        "api_signatures used dotted method names that failed "
                        "to parse.",
                        element.name, file_spec.file,
                    )

        # ── Pre-classify all elements once (AC-R17, R1-S1) ──
        # Build full _ClassifiedElement objects upfront.  The tiers dict
        # feeds file-whole prompt construction; the full objects are reused
        # by the element-by-element fallback path (no re-classification).
        _pre_tiers: dict[str, TierClassification] = {}
        _all_contracts: list[InterfaceContract] = []
        _pre_classified: list[_ClassifiedElement] = []
        for element in enriched_file_spec.elements:
            elem_contracts = self._get_element_contracts(element, enriched_file_spec, manifest)
            tier, reasoning, details = classify_element_with_details(
                element, enriched_file_spec, elem_contracts,
                template_registry=self._templates,
                config=self._config,
            )
            _pre_tiers[element.name] = tier
            _all_contracts.extend(elem_contracts)
            priority = self._TIER_PRIORITY.get(tier, 2)
            _pre_classified.append(
                _ClassifiedElement(
                    priority=priority,
                    element=element,
                    contracts=elem_contracts,
                    tier=tier,
                    reasoning=reasoning,
                    file_import_bump=details.file_import_bump,
                    element_api_adjustment=details.element_api_adjustment,
                    classification_signals=details.classification_signals,
                )
            )

        # ── File-level Ollama-whole attempt ──
        # For small files, try generating the complete file in one Ollama
        # call before decomposing into individual elements.  This avoids
        # the body-only prompt format that small models handle poorly.
        if ollama_available and self._is_file_ollama_whole_eligible(
            enriched_file_spec, skeleton,
        ):
            _record_generation_path("file_whole_primary", file_spec.file)
            file_whole_result = self._attempt_file_ollama_whole(
                enriched_file_spec, skeleton,
                task_description=task_description,
                domain_constraints=domain_constraints,
                design_doc_sections=design_doc_sections,
                contracts=_all_contracts or None,
                pre_classified_tiers=_pre_tiers,
            )
            if file_whole_result is not None:
                _record_generation_path_outcome("file_whole_primary", "success", file_spec.file)
                return file_whole_result
            _record_generation_path_outcome("file_whole_primary", "failure", file_spec.file)

        # File-whole was either ineligible or failed — fall through to
        # element-by-element generation (AC-R1 fallback path).
        _record_generation_path("element_by_element_fallback", file_spec.file)
        logger.info(
            "File-whole ineligible or failed for %s — falling through to element-by-element (fallback path)",
            file_spec.file,
        )

        # Reuse pre-classified elements (R1-S1) — no redundant classification.
        classified = sorted(_pre_classified, key=lambda c: c.sort_key)

        if classified:
            _summary = ", ".join(
                f"{c.element.name}={c.tier.value}" for c in classified
            )
            logger.info(
                "Element classification for %s: %s",
                file_spec.file, _summary,
            )

        for c in classified:
            element = c.element
            contracts = c.contracts
            result = self._process_element_with_tier(
                element, enriched_file_spec, current_skeleton, contracts,
                tier=c.tier, reasoning=c.reasoning,
                api_file_import_bump=c.file_import_bump,
                api_element_adjustment=c.element_api_adjustment,
                ollama_available=ollama_available,
                design_doc_sections=design_doc_sections,
                task_description=task_description,
                classification_signals=c.classification_signals,
            )
            file_result.element_results.append(result)

            # If successful, splice into skeleton
            if result.success and result.code:
                splice_result = splice_body_into_skeleton(
                    result.code, element, current_skeleton,
                )
                if splice_result.code is not None:
                    current_skeleton = splice_result.code
                    # Fix 1: Attempt repair if splicer detected contract violations
                    if splice_result.violations:
                        repaired_code, fixes = _attempt_splice_violation_repair(
                            current_skeleton, splice_result.violations, file_spec.file,
                        )
                        if fixes:
                            current_skeleton = repaired_code
                            # Fix 4: Update registry with repaired code
                            eid = _resolve_element_id(element, file_spec.file)
                            if self._element_registry is not None and eid:
                                try:
                                    entry = self._element_registry.get(eid)
                                    if entry is not None:
                                        entry.extra["code"] = result.code
                                        entry.extra["contract_repairs"] = fixes
                                        self._element_registry.put(entry)
                                        self._element_registry.set_phase_status(
                                            eid, "implement", "repaired",
                                            metadata={"repairs": fixes},
                                        )
                                except Exception as exc:  # noqa: BLE001
                                    logger.debug(
                                        "Registry update after repair failed for %s: %s",
                                        eid, exc,
                                    )
                else:
                    # Splice failed — mark as escalated
                    result.success = False
                    result.escalation = build_escalation_context(
                        element_name=element.name,
                        file_path=file_spec.file,
                        tier=result.tier,
                        reason=EscalationReason.STRUCTURAL_MISMATCH,
                        detail="Body splicing into skeleton failed",
                        last_code=result.code,
                    )

        # ── File-whole retry on total escalation ──
        # When every element escalated (0% fill) and the file is small,
        # retry file-whole generation instead of giving up.  The element
        # classifier may have been too aggressive (e.g. import-heavy but
        # structurally simple files).  File-whole uses the full skeleton
        # prompt which gives the model more context than body-only.
        success_count = sum(1 for er in file_result.element_results if er.success)
        escalated_count = sum(1 for er in file_result.element_results if er.escalation)
        if (
            success_count == 0
            and escalated_count > 0
            and ollama_available
            and self._is_file_ollama_whole_eligible(enriched_file_spec, skeleton)
        ):
            _record_generation_path("file_whole_escalation_retry", file_spec.file)
            logger.info(
                "All %d elements escalated for %s — retrying file-whole generation",
                escalated_count, file_spec.file,
            )
            retry_result = self._attempt_file_ollama_whole(
                enriched_file_spec, skeleton,
                task_description=task_description,
                domain_constraints=domain_constraints,
                design_doc_sections=design_doc_sections,
                contracts=_all_contracts or None,
                pre_classified_tiers=_pre_tiers,
            )
            if retry_result is not None:
                _record_generation_path_outcome("file_whole_escalation_retry", "success", file_spec.file)
                logger.info(
                    "File-whole retry succeeded for %s (%d elements)",
                    file_spec.file, escalated_count,
                )
                return retry_result
            _record_generation_path_outcome("file_whole_escalation_retry", "failure", file_spec.file)
            logger.info(
                "File-whole retry also failed for %s — proceeding with escalation",
                file_spec.file,
            )

        # Post-splice defect detection: if skeleton markers or
        # `raise NotImplementedError` stubs remain, the skeleton is
        # incomplete.  Mark remaining stub elements as failed so the
        # fill-rate gate in prime_adapter catches partial skeletons
        # instead of writing them to disk.  Uses AST-based stub detection
        # (AC-R3) to avoid false positives on branch/comment usage.
        _has_stubs = _skeleton_has_stubs(current_skeleton)
        _has_marker = SKELETON_MARKER in current_skeleton
        if _has_stubs or _has_marker:
            for er in file_result.element_results:
                if er.success and not er.code:
                    # Cache-hit with no code — splice was skipped
                    er.success = False
                    er.escalation = build_escalation_context(
                        element_name=er.element_name,
                        file_path=file_spec.file,
                        tier=er.tier,
                        reason=EscalationReason.STRUCTURAL_MISMATCH,
                        detail="Element had no code (cache hit without code); skeleton stub remains",
                    )
                    logger.warning(
                        "Stub remains for %s after splice loop — marking as failed",
                        er.element_name,
                    )

        # Post-splice cleanup: remove top-level functions that duplicate
        # nested functions inside another top-level function.  This happens
        # when the decomposer creates separate elements for a factory's inner
        # functions (e.g. Flask @app.route handlers inside create_app()).
        current_skeleton = _remove_toplevel_nested_duplicates(
            current_skeleton, original_skeleton=skeleton,
        )

        file_result.filled_skeleton = current_skeleton

        # Within-run contract completeness check (Ichigo Ichie compliant):
        # Verify every contract-bound element in this file has a registry
        # entry with a successful generation status.
        self._check_contract_completeness(file_spec, file_result)

        return file_result

    def _check_contract_completeness(
        self,
        file_spec: ForwardFileSpec,
        file_result: "FileResult",
    ) -> None:
        """Log warnings for contract-bound elements that weren't generated.

        Within-run check: for each element in the file_spec that has a
        source_contract_id, verify the registry has a corresponding entry
        with a successful generation phase.  Gaps indicate the contract
        was defined but generation failed or was skipped.
        """
        if self._element_registry is None:
            return

        successful_names = {
            er.element_name for er in file_result.element_results if er.success
        }

        for element in file_spec.elements:
            if not element.source_contract_id:
                continue
            # Check if any registry entry for this contract was generated
            entries = self._element_registry.get_by_contract_id(element.source_contract_id)
            if not entries:
                # No registry entry at all — element may have been skipped
                if element.name not in successful_names:
                    logger.warning(
                        "Contract %s for element %s in %s has no registry entry "
                        "and generation did not succeed",
                        element.source_contract_id, element.name, file_spec.file,
                    )

    def process_file_with_context(
        self,
        file_spec: ForwardFileSpec,
        skeleton: str,
        context: MicroPrimeContext,
        design_doc_sections: Optional[list[str]] = None,
        task_description: Optional[str] = None,
    ) -> FileResult:
        """Process a file using normalized MicroPrimeContext (REQ-MP-509)."""
        return self.process_file(
            file_spec,
            context.manifest,
            skeleton,
            design_doc_sections=design_doc_sections,
            ollama_available=context.ollama_available,
            task_description=task_description,
            domain_constraints=context.binding_constraints or None,
        )

    def reset_for_seed(self) -> None:
        """Clear per-seed state to prevent cross-seed contamination (AC-R20).

        Must be called at the start of each seed in a multi-seed batch
        (e.g. PrimeContractor). Prevents few-shot examples from prior
        seeds leaking into the current seed's prompts.
        """
        self._completed.clear()

    def process_seed(
        self,
        manifest: ForwardManifest,
        skeletons: dict[str, str],
        ollama_available: bool = True,
    ) -> SeedResult:
        """Process all elements across all files in a seed.

        Args:
            manifest: Full forward manifest.
            skeletons: Dict mapping file paths to skeleton content.

        Returns:
            SeedResult with all file results.
        """
        # AC-R20: Clear cross-seed few-shot contamination
        self.reset_for_seed()

        seed_result = SeedResult()
        start_time = time.monotonic()

        for file_path, file_spec in manifest.file_specs.items():
            skeleton = skeletons.get(file_path, "")
            if not skeleton:
                logger.warning("No skeleton for %s, skipping", file_path)
                continue

            file_result = self.process_file(
                file_spec, manifest, skeleton,
                ollama_available=ollama_available,
            )
            seed_result.file_results.append(file_result)

        seed_result.total_generation_time_ms = (
            (time.monotonic() - start_time) * 1000
        )

        # Sum tokens
        for fr in seed_result.file_results:
            for er in fr.element_results:
                seed_result.total_input_tokens += er.input_tokens
                seed_result.total_output_tokens += er.output_tokens

        return seed_result

    def process_seed_with_context(
        self,
        skeletons: dict[str, str],
        context: MicroPrimeContext,
    ) -> SeedResult:
        """Process a seed using normalized MicroPrimeContext (REQ-MP-509)."""
        return self.process_seed(
            context.manifest,
            skeletons,
            ollama_available=context.ollama_available,
        )

    def inspect_decomposition(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        manifest: Optional[ForwardManifest],
        reason: str,
    ) -> dict[str, Any]:
        """Lightweight decomposition viability check for dry-run reports.

        Returns:
            {"viable": bool, "strategy": Optional[str], "sub_count": int}
        """
        if manifest is None or not self._config.decomposition_enabled:
            return {"viable": False, "strategy": None, "sub_count": 0}

        plan = self._decomposer.decompose(
            element, file_spec, manifest, reason,
        )
        if plan is None:
            return {"viable": False, "strategy": None, "sub_count": 0}

        return {
            "viable": True,
            "strategy": plan.strategy,
            "sub_count": len(plan.sub_elements),
        }

    # ─── Ollama-whole eligibility ────────────────────────────────────

    def _is_ollama_whole_eligible(
        self,
        classification_signals: Optional[set[str]],
    ) -> bool:
        """Check if a MODERATE element should attempt Ollama-whole generation.

        Elements with signals in ``moderate_ollama_whole_skip_signals`` (e.g.
        ``external_api``, ``orchestrator``) are skipped — these have external
        dependencies that make single-shot local generation unreliable.
        """
        if classification_signals is None:
            return True  # No signal data — try optimistically
        skip = self._config.moderate_ollama_whole_skip_signals
        overlap = classification_signals & skip
        if overlap:
            logger.debug(
                "Ollama-whole skipped: signals %s overlap skip list", overlap,
            )
            return False
        return True

    # ─── File-level Ollama-whole ────────────────────────────────────

    def _is_file_ollama_whole_eligible(
        self,
        file_spec: ForwardFileSpec,
        skeleton: str,
    ) -> bool:
        """Check if a file qualifies for single-shot Ollama generation.

        AC-R1: File-whole is the PRIMARY generation path. Only files that
        exceed the LOC threshold (context-window proxy) fall through to
        element-by-element. The element count gate has been removed — it
        was the main source of unnecessary element-by-element routing.

        Eligible when:
        - Feature is enabled in config
        - Estimated LOC ≤ max_loc threshold (context-window proxy)
        - Skeleton has at least one ``raise NotImplementedError`` stub
        """
        if not self._config.file_ollama_whole_enabled:
            return False
        if not _skeleton_has_stubs(skeleton):
            logger.debug(
                "File-whole skipped for %s: no stubs in skeleton",
                file_spec.file,
            )
            return False

        # Coupling override: prefer file-whole for coupled files regardless
        # of size, because element-by-element generation loses cross-element
        # context (run-042 PI-003, PI-008, PI-009 first-pass failures).
        if _has_high_within_file_coupling(file_spec, skeleton):
            logger.info(
                "File-whole PREFERRED for %s: high within-file coupling detected",
                file_spec.file,
            )
            return True

        # AC-R1: Only LOC gate remains — context-window proxy.
        # Element count gate removed (was the primary source of unnecessary
        # element-by-element routing for small-to-medium files).
        skeleton_lines = len(skeleton.splitlines())
        if skeleton_lines > self._config.file_ollama_whole_max_loc:
            logger.debug(
                "File-whole skipped for %s: %d lines > %d max",
                file_spec.file, skeleton_lines,
                self._config.file_ollama_whole_max_loc,
            )
            return False
        return True

    def _attempt_file_ollama_whole(
        self,
        file_spec: ForwardFileSpec,
        skeleton: str,
        task_description: Optional[str] = None,
        domain_constraints: Optional[list[str]] = None,
        design_doc_sections: Optional[list[str]] = None,
        contracts: Optional[list[InterfaceContract]] = None,
        pre_classified_tiers: Optional[dict[str, TierClassification]] = None,
    ) -> Optional[FileResult]:
        """Attempt to generate all elements in one Ollama call.

        Sends the complete skeleton file to the model and asks it to fill
        ALL ``raise NotImplementedError`` stubs in a single pass.  This avoids
        the body-only fragmentation that confuses small local models.

        Uses the unified ``_generate_with_ollama_retry`` loop (R2) with a
        file-whole-specific ``validate_and_repair`` closure.

        Returns:
            FileResult if successful (full or partial), None if the attempt
            failed entirely (caller should fall through to element-by-element).
        """
        file_path = file_spec.file
        skeleton_lines = len(skeleton.splitlines())
        logger.info(
            "Attempting file-level Ollama-whole for %s (%d elements, %d lines)",
            file_path, len(file_spec.elements), skeleton_lines,
        )

        # AC-R16: Collect completed file examples from prior files in this seed
        completed_file_examples: list[str] = []
        for ce in self._completed:
            if (
                ce.get("file_path") != file_path
                and ce.get("generation_strategy") == "file_ollama_whole"
                and ce.get("code")
            ):
                snippet_lines = ce["code"].splitlines()[:60]
                if len(snippet_lines) == 60:
                    snippet_lines.append("# ... (truncated)")
                completed_file_examples.append("\n".join(snippet_lines))
                if len(completed_file_examples) >= 2:
                    break

        # Strip skeleton marker before prompting — if the model echoes it,
        # validation fails with "contains skeleton markers."
        _prompt_skeleton = skeleton.replace(
            SKELETON_MARKER + "\n", ""
        ).replace(SKELETON_MARKER, "")

        prompt = _build_file_whole_prompt(
            _prompt_skeleton, file_spec,
            task_description=task_description,
            domain_constraints=domain_constraints,
            design_doc_sections=design_doc_sections,
            contracts=contracts,
            completed_file_examples=completed_file_examples or None,
        )

        # Adaptive max_tokens: scale output budget with skeleton size
        file_whole_max_tokens = max(
            self._config.max_tokens,
            skeleton_lines * 4,  # ~4 tokens per output line
        )

        # ── Validate-and-repair closure for file-whole path ──
        # Mutable state shared between closure and post-loop code.
        _fw_state: dict[str, Any] = {"valid": False, "missing": []}

        def _validate_file_whole(raw_code: str, attempt: int) -> tuple[str | None, str | None]:
            valid, reason, missing = _validate_file_whole_result(raw_code, skeleton, file_spec)
            if valid:
                _fw_state.update(valid=True, missing=[])
                return raw_code, None

            # Try repair — two-tier strategy
            logger.info(
                "File-whole validation failed for %s (attempt %d): %s — attempting file repair",
                file_path, attempt + 1, reason,
            )
            if file_spec.elements:
                # Tier 1: thin file-whole pipeline
                repair_result = run_file_repair_pipeline(raw_code, file_spec)
                if repair_result.ast_valid:
                    re_valid, re_reason, re_missing = _validate_file_whole_result(
                        repair_result.code, skeleton, file_spec,
                    )
                    if re_valid:
                        logger.info(
                            "File-whole repair succeeded for %s (tier 1, steps: %s)",
                            file_path, repair_result.steps_applied,
                        )
                        _fw_state.update(valid=True, missing=[])
                        return repair_result.code, None
                    reason = re_reason
                    missing = re_missing

                # Tier 2: full contractor repair pipeline
                contractor_result = run_file_whole_contractor_repair(
                    raw_code, reason, file_path,
                )
                if contractor_result.ast_valid:
                    re_valid, re_reason, re_missing = _validate_file_whole_result(
                        contractor_result.code, skeleton, file_spec,
                    )
                    if re_valid:
                        logger.info(
                            "File-whole repair succeeded for %s (tier 2, steps: %s)",
                            file_path, contractor_result.steps_applied,
                        )
                        _fw_state.update(valid=True, missing=[])
                        return contractor_result.code, None
                    reason = re_reason
                    missing = re_missing

            _fw_state.update(valid=False, missing=missing)
            return None, reason

        retry_outcome = self._generate_with_ollama_retry(
            prompt, _FILE_WHOLE_SYSTEM_PROMPT, file_path,
            max_tokens=file_whole_max_tokens,
            stop_sequences=self._FILE_WHOLE_STOP_SEQUENCES,
            validate_and_repair=_validate_file_whole,
        )

        # ── Interpret outcome ──
        valid = _fw_state["valid"]
        missing: list[str] = _fw_state["missing"]
        total_llm_calls = retry_outcome.llm_calls
        gen_time = retry_outcome.elapsed_ms

        # Use validated code on success, last raw output for partial acceptance
        final_raw = retry_outcome.code if retry_outcome.code is not None else retry_outcome.raw_output
        if not final_raw:
            return None

        code = extract_code_from_response(final_raw)

        # ── Partial acceptance ──
        missing_set: set[str] = set()
        if not valid and missing:
            total_elements = len(file_spec.elements)
            filled_count = total_elements - len(missing)
            fill_rate = filled_count / max(total_elements, 1)

            if fill_rate >= self._config.min_element_fill_rate:
                logger.info(
                    "File-whole partial acceptance for %s: %d/%d filled (%.0f%%), "
                    "escalating %d elements: %s",
                    file_path, filled_count, total_elements,
                    fill_rate * 100, len(missing), missing,
                )
                missing_set = set(missing)
            else:
                logger.info(
                    "File-whole fill rate too low for %s: %d/%d (%.0f%% < %.0f%% threshold)",
                    file_path, filled_count, total_elements,
                    fill_rate * 100, self._config.min_element_fill_rate * 100,
                )
                return None
        elif not valid:
            return None

        if valid:
            logger.info(
                "File-whole succeeded for %s — %d elements filled in %d call(s)",
                file_path, len(file_spec.elements), total_llm_calls,
            )

        # Build element results — AC-R15 factory methods, AC-R17 pre-classified tiers
        model_name = f"{self._config.provider}:{self._config.model}"
        tiers = pre_classified_tiers or {}
        file_result = FileResult(file_path=file_path)
        total_input_tokens = retry_outcome.input_tokens
        total_output_tokens = retry_outcome.output_tokens
        per_element_tokens_in = total_input_tokens // max(len(file_spec.elements), 1)
        per_element_tokens_out = total_output_tokens // max(len(file_spec.elements), 1)
        per_element_time = gen_time / max(len(file_spec.elements), 1)
        meta_strategy = {"strategy": "file_ollama_whole", "llm_calls": total_llm_calls}

        for element in file_spec.elements:
            elem_tier = tiers.get(element.name, TierClassification.SIMPLE)
            is_missing = element.name in missing_set
            if is_missing:
                esc_tier = max(elem_tier, TierClassification.MODERATE, key=lambda t: t.value)
                result = ElementResult.make_escalation(
                    element.name, file_path, esc_tier,
                    "file_ollama_whole_partial",
                    EscalationResult(
                        reason=EscalationReason.OLLAMA_WHOLE_FAILED,
                        detail=f"file-whole partial: element {element.name} not filled",
                    ),
                    model=model_name,
                    generation_time_ms=per_element_time,
                    input_tokens=per_element_tokens_in,
                    output_tokens=per_element_tokens_out,
                    decomposition_metadata={**meta_strategy, "strategy": "file_ollama_whole_partial"},
                    generation_strategy="file_ollama_whole",
                )
            else:
                result = ElementResult.make_success(
                    element.name, file_path, elem_tier,
                    "file_ollama_whole",
                    code,
                    model=model_name,
                    generation_time_ms=per_element_time,
                    input_tokens=per_element_tokens_in,
                    output_tokens=per_element_tokens_out,
                    ast_valid_before_repair=True,
                    ast_valid_after_repair=True,
                    decomposition_metadata=meta_strategy,
                    generation_strategy="file_ollama_whole",
                )
            result.parent_class = element.parent_class
            result.element_kind = element.kind.value if element.kind else None
            file_result.element_results.append(result)

        # AC-R16: Record file-whole success for few-shot in subsequent files
        if valid:
            self._completed.append({
                "file_path": file_path,
                "code": code,
                "generation_strategy": "file_ollama_whole",
                "syntax_valid": True,
                "repair_recovered": False,
            })

        file_result.filled_skeleton = code
        return file_result

    # ─── Private handlers ─────────────────────────────────────────────

    def _moderate_escalation_result(
        self,
        element: ForwardElementSpec,
        file_path: str,
        reasoning: str,
        reason: "EscalationReason",
        detail: str,
        *,
        verification_verdict: str = "skipped",
        decomposition_metadata: Optional[dict] = None,
        generation_time_ms: float = 0.0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        last_code: Optional[str] = None,
        last_error: Optional[str] = None,
    ) -> ElementResult:
        """Build a failure ElementResult for MODERATE tier with escalation."""
        esc_kwargs: dict = dict(
            element_name=element.name,
            file_path=file_path,
            tier=TierClassification.MODERATE,
            reason=reason,
            detail=detail,
        )
        if last_code is not None:
            esc_kwargs["last_code"] = last_code
        if last_error is not None:
            esc_kwargs["last_error"] = last_error

        return ElementResult.make_escalation(
            element.name, file_path, TierClassification.MODERATE, reasoning,
            build_escalation_context(**esc_kwargs),
            verification_verdict=verification_verdict,
            decomposition_metadata=decomposition_metadata,
            generation_time_ms=generation_time_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            generation_strategy="moderate_escalation",
        )

    def _try_moderate_ollama_whole(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        skeleton: str,
        contracts: list[InterfaceContract],
        file_path: str,
        reasoning: str,
        classification_signals: Optional[set[str]],
        design_doc_sections: Optional[list[str]],
        task_description: Optional[str],
    ) -> Optional[ElementResult]:
        """Attempt single-shot Ollama generation for a MODERATE element.

        Returns an ElementResult on success, None to fall through to decomposition.
        Many MODERATE elements are generatable as a whole — decomposition adds
        complexity and failure modes (29% moderate vs 10% simple in run-017).
        """
        if not (
            self._config.moderate_ollama_whole_enabled
            and element.decomposition_source is None
            and self._is_ollama_whole_eligible(classification_signals)
        ):
            return None

        _record_moderate_ollama_whole_attempted(file_path)
        logger.info(
            "Attempting Ollama-whole for MODERATE element %s before decomposition",
            element.name,
        )
        result = self._handle_simple(
            element, file_spec, skeleton, contracts, file_path,
            f"moderate_ollama_whole: {reasoning}",
            design_doc_sections=design_doc_sections,
            task_description=task_description,
        )
        if result.success:
            _record_moderate_ollama_whole_succeeded(file_path)
            result.tier = TierClassification.MODERATE
            result.decomposition_metadata = {
                "strategy": "ollama_whole",
                "llm_calls": 1,
            }
            logger.info(
                "Ollama-whole succeeded for MODERATE element %s — skipping decomposition",
                element.name,
            )
            return result
        logger.info(
            "Ollama-whole failed for %s — falling through to decomposition",
            element.name,
        )
        return None

    def _generate_sub_elements(
        self,
        plan: "GenerationPlan",
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        skeleton: str,
        contracts: list[InterfaceContract],
        file_path: str,
        reasoning: str,
        start_time: float,
        design_doc_sections: Optional[list[str]],
        task_description: Optional[str],
    ) -> "tuple[Optional[dict[str, str]], int, int, Optional[ElementResult]]":
        """Generate all sub-elements from a decomposition plan.

        Returns:
            (sub_results, total_input, total_output, failure) where failure
            is None on success and an ElementResult on any sub-element failure.
            Does NOT rollback self._completed — caller handles that.
        """
        sub_results: dict[str, str] = {}
        total_input = 0
        total_output = 0

        for sub in sorted(plan.sub_elements, key=lambda s: s.assembly_order):
            if sub.deterministic:
                code = self._extract_class_shell(element, skeleton)
                if code is not None:
                    sub_results[sub.name] = code
                    logger.info(
                        "Sub-element %s: deterministic extraction (0ms)", sub.name,
                    )
                    continue
                logger.warning(
                    "Shell extraction failed for %s, abandoning decomposition",
                    element.name,
                )
                _record_decomp_failed(plan.strategy, file_path, "shell_extraction")
                return None, total_input, total_output, self._moderate_escalation_result(
                    element, file_path, reasoning,
                    EscalationReason.DECOMPOSITION_FAILED,
                    "Shell extraction failed",
                    decomposition_metadata={
                        "rejection_reason": RejectionReason.SKELETON_MISMATCH.value,
                    },
                    generation_time_ms=(time.monotonic() - start_time) * 1000,
                    input_tokens=total_input,
                    output_tokens=total_output,
                )

            if sub.element_spec is None:
                return None, total_input, total_output, self._moderate_escalation_result(
                    element, file_path, reasoning,
                    EscalationReason.DECOMPOSITION_FAILED,
                    f"Missing element_spec for sub-element {sub.name}",
                    decomposition_metadata={
                        "rejection_reason": RejectionReason.EMPTY_OUTPUT.value,
                    },
                    generation_time_ms=(time.monotonic() - start_time) * 1000,
                    input_tokens=total_input,
                    output_tokens=total_output,
                )

            sub_spec = sub.element_spec
            if sub.prompt_context:
                doc_hint = (
                    f"{sub_spec.docstring_hint}\nContext: {sub.prompt_context}"
                    if sub_spec.docstring_hint
                    else sub.prompt_context
                )
                if len(doc_hint) > 512:
                    doc_hint = doc_hint[:509] + "..."
                sub_spec = sub_spec.model_copy(update={"docstring_hint": doc_hint})

            _record_sub_element(plan.strategy, "simple")
            sub_result = self._handle_simple(
                sub_spec, file_spec, skeleton, contracts,
                file_path, f"sub-element of {element.name}",
                design_doc_sections=design_doc_sections,
                task_description=task_description,
            )
            total_input += sub_result.input_tokens
            total_output += sub_result.output_tokens

            if not sub_result.success or not sub_result.code:
                # AC-R13: Do NOT call _record_local_failure() for each
                # sub-element — correlated sub-element failures within a
                # single MODERATE decomposition should count as one parent
                # failure, not N independent failures.  The parent-level
                # failure is recorded by _process_element_with_tier (line 1362).
                logger.warning(
                    "Sub-element %s failed — abandoning decomposition of %s",
                    sub.name, element.name,
                )
                _record_decomp_failed(plan.strategy, file_path, "sub_element_failed")
                return None, total_input, total_output, self._moderate_escalation_result(
                    element, file_path, reasoning,
                    EscalationReason.DECOMPOSITION_FAILED,
                    f"Sub-element {sub.name} failed",
                    last_code=sub_result.code,
                    last_error=(
                        sub_result.escalation.detail
                        if sub_result.escalation else None
                    ),
                    decomposition_metadata={
                        "rejection_reason": RejectionReason.EMPTY_OUTPUT.value,
                    },
                    generation_time_ms=(time.monotonic() - start_time) * 1000,
                    input_tokens=total_input,
                    output_tokens=total_output,
                )

            # Sub-element success does not reset the breaker — the outer
            # _process_element_with_tier handles that based on the overall
            # MODERATE result.
            sub_results[sub.name] = sub_result.code

        return sub_results, total_input, total_output, None

    def _assemble_and_verify_moderate(
        self,
        plan: "GenerationPlan",
        sub_results: dict[str, str],
        skeleton: str,
        element: ForwardElementSpec,
        file_path: str,
        reasoning: str,
        start_time: float,
        total_input: int,
        total_output: int,
    ) -> "tuple[Optional[str], float, Optional[ElementResult]]":
        """Assemble sub-element results and run structural verification.

        Returns:
            (assembled_code, assembly_time_ms, failure) where failure is None
            on success and an ElementResult on assembly/verification failure.
        """
        assemble_start = time.monotonic()
        assembled = self._decomposer.assemble(plan, sub_results, skeleton)
        assembly_time_ms = (time.monotonic() - assemble_start) * 1000
        _record_assembly_time(plan.strategy, file_path, assembly_time_ms)
        gen_time = (time.monotonic() - start_time) * 1000

        if assembled is None:
            _record_decomp_failed(plan.strategy, file_path, "assembly_failed")
            return None, assembly_time_ms, self._moderate_escalation_result(
                element, file_path, reasoning,
                EscalationReason.DECOMPOSITION_FAILED,
                "Assembly failed",
                decomposition_metadata={
                    "rejection_reason": RejectionReason.RENDER_CONTRACT_VIOLATION.value,
                },
                generation_time_ms=gen_time,
                input_tokens=total_input,
                output_tokens=total_output,
            )

        structural_ok, structural_reason = _structural_verify(assembled, element)
        if not structural_ok:
            _record_decomp_failed(plan.strategy, file_path, "structural_verification")
            return None, assembly_time_ms, self._moderate_escalation_result(
                element, file_path, reasoning,
                EscalationReason.DECOMPOSITION_FAILED,
                "Assembled code failed structural verification",
                verification_verdict="fail",
                last_code=assembled,
                last_error=structural_reason or "structural_verification_failed",
                decomposition_metadata={
                    "rejection_reason": RejectionReason.RENDER_CONTRACT_VIOLATION.value,
                },
                generation_time_ms=gen_time,
                input_tokens=total_input,
                output_tokens=total_output,
            )

        return assembled, assembly_time_ms, None

    def _handle_moderate(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        manifest: Optional[ForwardManifest],
        skeleton: str,
        contracts: list[InterfaceContract],
        file_path: str,
        reasoning: str = "",
        design_doc_sections: Optional[list[str]] = None,
        task_description: Optional[str] = None,
        classification_signals: Optional[set[str]] = None,
        complexity_signals: Optional[TaskComplexitySignals] = None,
    ) -> ElementResult:
        """Handle MODERATE tier: attempt decomposition, then escalate.

        Args:
            complexity_signals: Optional TaskComplexitySignals threaded from
                classify_tier() via ClassificationResult (Keiyaku D-1).
                Forwarded to the decomposer for strategy-level decisions.
        """
        start_time = time.monotonic()

        # Leaf-only constraint (Phase 1, Step 7): decomposed sub-elements
        # must never re-enter the decomposer.
        if element.decomposition_source is not None:
            raise RuntimeError("Recursive decomposition blocked")

        # Circuit breaker gate (R1-S1)
        if self._circuit_open:
            return self._moderate_escalation_result(
                element, file_path, reasoning,
                EscalationReason.CIRCUIT_BREAKER,
                "Circuit breaker open",
            )

        # Ollama-whole attempt before decomposition (Kaizen run-017).
        ollama_result = self._try_moderate_ollama_whole(
            element, file_spec, skeleton, contracts, file_path,
            reasoning, classification_signals, design_doc_sections,
            task_description,
        )
        if ollama_result is not None:
            return ollama_result

        # Null-guard for standalone process_element() path (R1-S5)
        if manifest is None:
            return self._moderate_escalation_result(
                element, file_path, reasoning,
                EscalationReason.TIER_TOO_HIGH,
                "Manifest unavailable — cannot decompose",
            )

        if not self._config.decomposition_enabled:
            return self._moderate_escalation_result(
                element, file_path, reasoning,
                EscalationReason.TIER_TOO_HIGH,
                "Decomposition disabled",
            )

        # Single entry point (R3-S2)
        # file_spec is already enriched at the process_file() level with
        # skeleton-derived method elements for classes.
        plan = self._decomposer.decompose(
            element, file_spec, manifest, reasoning,
            classification_signals=classification_signals,
            complexity_signals=complexity_signals,
        )
        if plan is None:
            _record_decomp_rejected(file_path, "no_strategy")
            # Run-038 fix (extended): MODERATE elements rejected by the
            # decomposer get a direct Ollama attempt before escalating.
            # Originally limited to standalone functions, but methods
            # classified as MODERATE (e.g. via file-level import bump)
            # also benefit — they're already leaf-level elements that
            # can't be decomposed further.
            _fallback_kinds = (
                ElementKind.FUNCTION, ElementKind.ASYNC_FUNCTION,
                ElementKind.METHOD, ElementKind.ASYNC_METHOD,
            )
            if element.kind in _fallback_kinds:
                _ctx = "method" if element.parent_class else "standalone function"
                logger.info(
                    "Decomposition rejected for %s %s — "
                    "trying direct Ollama generation as fallback",
                    _ctx, element.name,
                )
                ollama_fallback = self._handle_simple(
                    element, file_spec, skeleton, contracts, file_path,
                    f"moderate_decomp_fallback: {reasoning}",
                    design_doc_sections=design_doc_sections,
                    task_description=task_description,
                )
                if ollama_fallback.success:
                    ollama_fallback.tier = TierClassification.MODERATE
                    ollama_fallback.decomposition_metadata = {
                        "strategy": "decomp_fallback_simple",
                        "rejection_reason": RejectionReason.NO_TEMPLATE_MATCH.value,
                    }
                    return ollama_fallback
                logger.info(
                    "Direct Ollama fallback also failed for %s — escalating",
                    element.name,
                )
            return self._moderate_escalation_result(
                element, file_path, reasoning,
                EscalationReason.NOT_DECOMPOSABLE,
                "No decomposition strategy applies",
                decomposition_metadata={
                    "rejection_reason": RejectionReason.NO_TEMPLATE_MATCH.value,
                },
            )

        logger.info(
            "Decomposing %s (MODERATE) via %s: %d sub-elements",
            element.name, plan.strategy, len(plan.sub_elements),
        )
        _record_decomp_attempted(plan.strategy, file_path)

        # Generate each sub-element (partial results preserved in _completed for few-shot)
        sub_results, total_input, total_output, failure = self._generate_sub_elements(
            plan, element, file_spec, skeleton, contracts, file_path,
            reasoning, start_time, design_doc_sections, task_description,
        )
        if failure is not None:
            # Pass partial sub-element code as escalation context
            if sub_results:
                partial_code = "\n\n".join(sub_results.values())
                if failure.escalation is not None:
                    failure.escalation.last_code = partial_code
            return failure

        assert sub_results is not None  # guaranteed when failure is None

        # Assemble and verify
        assembled, assembly_time_ms, failure = self._assemble_and_verify_moderate(
            plan, sub_results, skeleton, element, file_path,
            reasoning, start_time, total_input, total_output,
        )
        if failure is not None:
            return failure

        assert assembled is not None  # guaranteed when failure is None
        gen_time = (time.monotonic() - start_time) * 1000

        logger.info(
            "Decomposition succeeded for %s: %d/%d sub-elements, %.0fms",
            element.name, len(sub_results), len(plan.sub_elements), gen_time,
        )
        _record_decomp_succeeded(plan.strategy, file_path)
        _record_decomp_time(plan.strategy, gen_time)

        # Record as completed for few-shot (REQ-MP-903)
        self._completed.append({
            "element": {
                "name": element.name,
                "parent_class": element.parent_class,
                "kind": element.kind,
            },
            "file_path": file_path,
            "code": assembled,
            "syntax_valid": True,
            "repair_recovered": False,
            "repair_steps_count": 0,
        })

        # Record success for cache (R1-S7)
        moderate_fingerprint = (
            f"{element.parent_class or ''}:{element.name}"
            f":{file_path}:{TierClassification.MODERATE.value}"
        )
        self._success_cache[moderate_fingerprint] = assembled

        return ElementResult.make_decomposition_success(
            element.name, file_path, TierClassification.MODERATE, reasoning,
            assembled,
            decomposition_metadata={
                "strategy": plan.strategy,
                "sub_elements": len(plan.sub_elements),
                "sub_element_results": [
                    {
                        "name": s.name,
                        "kind": s.kind,
                        "success": s.name in sub_results,
                    }
                    for s in plan.sub_elements
                ],
                "assembly_time_ms": assembly_time_ms,
                "total_time_ms": gen_time,
            },
            model=f"{self._config.provider}:{self._config.model}",
            generation_time_ms=gen_time,
            input_tokens=total_input,
            output_tokens=total_output,
            generation_strategy="decomposition",
        )

    # ── Plan Graph Executor (REQ-MP-912) ─────────────────────────────

    def _execute_plan_graph(
        self,
        graph: DecompositionPlanGraph,
        file_spec: ForwardFileSpec,
        manifest: ForwardManifest,
        skeleton: str,
        contracts: list[InterfaceContract],
        file_path: str,
        design_doc_sections: Optional[list[str]] = None,
        task_description: Optional[str] = None,
        *,
        depth: int = 0,
        decomposition_path: Optional[list[str]] = None,
        policy: Optional[RecursionPolicy] = None,
    ) -> "_GraphExecutionResult":
        """Execute a plan graph with staged results and policy enforcement.

        Staging contract (R2-S2):
            Staged artifacts: sub_results dict (code strings per sub-element name)
            Rollback: On any sub-element failure, returns success=False with
            empty sub_results — no results are committed to caller
            Commit boundary: Only when ALL sub-elements succeed are results returned
            Partial sub-element successes are NOT persisted on parent failure

        Scope of atomicity (R2-F8): The write guarantee applies within a single
        _execute_plan_graph call. Nested recursive calls each have their own
        staged scope — a failure at depth N+1 only discards depth N+1's staged
        results and causes the depth N caller to fail the sub-element.

        Returns:
            _GraphExecutionResult with success flag, sub_results, and token counts.
        """
        if policy is None:
            policy = policy_from_config(self._config)
        if decomposition_path is None:
            decomposition_path = []

        staged_results: dict[str, str] = {}
        total_input = 0
        total_output = 0
        llm_calls = 0

        # Emit recursion_attempted only when recursion is enabled (REQ-MP-914)
        if policy.enabled and depth > 0:
            _record_recursion_attempted(graph.strategy, depth)

        for node in graph.root_nodes:
            node_result = self._execute_graph_node(
                node=node,
                element=graph.original_element,
                file_spec=file_spec,
                manifest=manifest,
                skeleton=skeleton,
                contracts=contracts,
                file_path=file_path,
                design_doc_sections=design_doc_sections,
                task_description=task_description,
                depth=depth,
                decomposition_path=decomposition_path,
                policy=policy,
                llm_calls_so_far=llm_calls,
                sub_elements_so_far=len(staged_results),
            )

            if not node_result.success:
                # Rollback: discard all staged results
                logger.debug(
                    "Graph execution failed at node %s depth=%d — "
                    "discarding %d staged results",
                    getattr(node.sub_element, "name", "?"),
                    depth,
                    len(staged_results),
                )
                if policy.enabled and depth > 0:
                    reason = node_result.rejection_reason or "sub_element_failed"
                    _record_recursion_rejected(graph.strategy, depth, reason)
                return _GraphExecutionResult(
                    success=False,
                    sub_results={},
                    input_tokens=total_input + node_result.input_tokens,
                    output_tokens=total_output + node_result.output_tokens,
                    llm_calls=llm_calls + node_result.llm_calls,
                    rejection_reason=node_result.rejection_reason,
                    recursion_depth=depth,
                    decomposition_path=list(decomposition_path),
                )

            sub_name = getattr(node.sub_element, "name", f"node_{id(node)}")
            staged_results[sub_name] = node_result.code
            total_input += node_result.input_tokens
            total_output += node_result.output_tokens
            llm_calls += node_result.llm_calls

        # All nodes succeeded — commit staged results
        if policy.enabled and depth > 0:
            _record_recursion_succeeded(graph.strategy, depth)
        return _GraphExecutionResult(
            success=True,
            sub_results=staged_results,
            input_tokens=total_input,
            output_tokens=total_output,
            llm_calls=llm_calls,
            recursion_depth=depth,
            decomposition_path=list(decomposition_path),
        )

    def _execute_graph_node(
        self,
        node: DecompositionNode,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        manifest: ForwardManifest,
        skeleton: str,
        contracts: list[InterfaceContract],
        file_path: str,
        design_doc_sections: Optional[list[str]],
        task_description: Optional[str],
        depth: int,
        decomposition_path: list[str],
        policy: RecursionPolicy,
        llm_calls_so_far: int,
        sub_elements_so_far: int,
    ) -> "_NodeExecutionResult":
        """Execute a single graph node, potentially recursing into children.

        Execution flow (REQ-MP-912):
            1. Deterministic sub-elements: extract from skeleton (no LLM, no budget)
            2. If node has children and recursion policy allows: recurse
            3. Otherwise: fall back to _handle_simple
        """
        sub = node.sub_element
        sub_name = getattr(sub, "name", "?")
        is_deterministic = getattr(sub, "deterministic", False)

        # Step 1: Deterministic — no LLM, no budget impact
        if is_deterministic:
            code = self._extract_class_shell(element, skeleton)
            if code is not None:
                return _NodeExecutionResult(
                    success=True, code=code,
                    input_tokens=0, output_tokens=0, llm_calls=0,
                )
            return _NodeExecutionResult(
                success=False, code="",
                input_tokens=0, output_tokens=0, llm_calls=0,
                rejection_reason="shell_extraction_failed",
            )

        # Step 2: Recursive children — requires policy check
        if node.children and policy.enabled:
            # Policy checks
            fp: Optional[str] = None
            sub_spec = getattr(sub, "element_spec", None)
            if sub_spec is not None:
                fp = make_fingerprint(
                    getattr(sub_spec, "parent_class", None),
                    getattr(sub_spec, "name", sub_name),
                    file_path,
                    TierClassification.SIMPLE,  # children are at lower tier
                )

                # Cycle detection
                cycle_reason = policy.check_cycle(fp, decomposition_path)
                if cycle_reason:
                    logger.debug(
                        "Recursion cycle detected for %s at depth %d",
                        sub_name, depth,
                    )
                    return _NodeExecutionResult(
                        success=False, code="",
                        input_tokens=0, output_tokens=0, llm_calls=0,
                        rejection_reason=cycle_reason,
                    )

                # Depth check
                depth_reason = policy.check_depth(depth + 1)
                if depth_reason:
                    logger.debug(
                        "Recursion depth exceeded for %s: depth=%d > max=%d",
                        sub_name, depth + 1, policy.max_depth,
                    )
                    return _NodeExecutionResult(
                        success=False, code="",
                        input_tokens=0, output_tokens=0, llm_calls=0,
                        rejection_reason=depth_reason,
                    )

                # Budget check
                budget_reason = policy.check_budget(
                    sub_elements_so_far + len(node.children),
                    llm_calls_so_far,
                )
                if budget_reason:
                    logger.debug(
                        "Recursion budget exceeded for %s at depth %d",
                        sub_name, depth,
                    )
                    return _NodeExecutionResult(
                        success=False, code="",
                        input_tokens=0, output_tokens=0, llm_calls=0,
                        rejection_reason=budget_reason,
                    )

            # Build child graph and recurse
            child_graph = DecompositionPlanGraph(
                original_element=getattr(sub, "element_spec", element),
                root_nodes=node.children,
                strategy=f"recursive_{depth + 1}",
                assembly_kind="sequential_body",
                confidence=0.0,
            )
            child_path = decomposition_path + [fp] if fp is not None else decomposition_path
            child_result = self._execute_plan_graph(
                graph=child_graph,
                file_spec=file_spec,
                manifest=manifest,
                skeleton=skeleton,
                contracts=contracts,
                file_path=file_path,
                design_doc_sections=design_doc_sections,
                task_description=task_description,
                depth=depth + 1,
                decomposition_path=child_path,
                policy=policy,
            )

            if child_result.success:
                # Combine child results into this node's code
                code = "\n".join(child_result.sub_results.values())
                return _NodeExecutionResult(
                    success=True, code=code,
                    input_tokens=child_result.input_tokens,
                    output_tokens=child_result.output_tokens,
                    llm_calls=child_result.llm_calls,
                )
            return _NodeExecutionResult(
                success=False, code="",
                input_tokens=child_result.input_tokens,
                output_tokens=child_result.output_tokens,
                llm_calls=child_result.llm_calls,
                rejection_reason=child_result.rejection_reason,
            )

        # Step 3: Leaf node — fall back to _handle_simple
        sub_spec = getattr(sub, "element_spec", None)
        if sub_spec is None:
            logger.debug(
                "Leaf node %s has no element_spec — cannot generate",
                sub_name,
            )
            return _NodeExecutionResult(
                success=False, code="",
                input_tokens=0, output_tokens=0, llm_calls=0,
                rejection_reason="missing_element_spec",
            )

        prompt_context = getattr(sub, "prompt_context", "")
        if prompt_context:
            doc_hint = (
                f"{sub_spec.docstring_hint}\nContext: {prompt_context}"
                if sub_spec.docstring_hint
                else prompt_context
            )
            if len(doc_hint) > _MAX_DOC_HINT_CHARS:
                doc_hint = doc_hint[:_MAX_DOC_HINT_CHARS - 3] + "..."
            sub_spec = sub_spec.model_copy(update={"docstring_hint": doc_hint})

        sub_result = self._handle_simple(
            sub_spec, file_spec, skeleton, contracts,
            file_path, f"sub-element of {element.name}",
            design_doc_sections=design_doc_sections,
            task_description=task_description,
        )

        if sub_result.success and sub_result.code:
            return _NodeExecutionResult(
                success=True,
                code=sub_result.code,
                input_tokens=sub_result.input_tokens,
                output_tokens=sub_result.output_tokens,
                llm_calls=1,  # One LLM call for _handle_simple
            )
        return _NodeExecutionResult(
            success=False, code="",
            input_tokens=sub_result.input_tokens,
            output_tokens=sub_result.output_tokens,
            llm_calls=1,
            rejection_reason="sub_element_failed",
        )

    def _extract_class_shell(
        self,
        element: ForwardElementSpec,
        skeleton: str,
    ) -> Optional[str]:
        """Extract class shell from skeleton — returns 'pass' as body token.

        The class declaration + docstring are already in the skeleton.
        The methods are separate elements spliced by the normal engine loop.
        """
        try:
            tree = ast.parse(skeleton)
        except SyntaxError:
            return None

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == element.name:
                return "pass"

        return None

    def _handle_trivial(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        skeleton: str,
        contracts: list[InterfaceContract],
        file_path: str,
        reasoning: str = "",
    ) -> ElementResult:
        """Handle TRIVIAL tier: use template registry."""
        match = self._templates.match(element, file_spec, contracts)
        if match is None:
            # Template failed — escalate to SIMPLE
            return self._handle_simple(element, file_spec, skeleton, [], file_path, reasoning)

        body = match.code

        # Structural verification of template output
        struct_ok, struct_reason = _structural_verify(body, element)
        if not struct_ok:
            logger.info(
                "Template output failed structural verify for %s: %s — escalating to SIMPLE",
                element.name, struct_reason,
            )
            return self._handle_simple(element, file_spec, skeleton, contracts, file_path, reasoning)

        # Record as completed for few-shot (REQ-MP-704)
        self._completed.append({
            "element": {
                "name": element.name,
                "parent_class": element.parent_class,
                "kind": element.kind,
            },
            "file_path": file_path,
            "code": body,
            "syntax_valid": True,
            "repair_recovered": False,
            "repair_steps_count": 0,
        })

        return ElementResult.make_success(
            element.name, file_path, TierClassification.TRIVIAL, reasoning, body,
            template_used=True,
            template_name=match.name,
            model="template",
            verification_verdict="pass",
            generation_strategy="template",
        )

    def _handle_simple(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        skeleton: str,
        contracts: list[InterfaceContract],
        file_path: str,
        reasoning: str = "",
        design_doc_sections: Optional[list[str]] = None,
        task_description: Optional[str] = None,
    ) -> ElementResult:
        """Handle SIMPLE tier: local model generation + repair."""
        start_time = time.monotonic()
        model_name = f"{self._config.provider}:{self._config.model}"
        element_fqn = (
            f"{element.parent_class}.{element.name}"
            if element.parent_class else element.name
        )

        # Sections 2–3: template / decomposer short-circuits
        shortcircuit = self._try_simple_shortcircuit(
            element, file_spec, contracts, file_path, reasoning,
        )
        if shortcircuit is not None:
            return shortcircuit

        # Sections 4–6: prompt construction + Ollama retry loop
        outcome = self._generate_with_retry(
            element, file_spec, skeleton, contracts, file_path,
            reasoning, model_name, element_fqn, start_time,
            design_doc_sections=design_doc_sections,
            task_description=task_description,
        )
        if outcome.failure is not None:
            return outcome.failure

        # Sections 7–9: structural + semantic verification, success assembly
        return self._verify_and_build_result(
            element, file_spec, skeleton, contracts, file_path,
            reasoning, model_name, element_fqn, start_time, outcome,
        )

    def _try_simple_shortcircuit(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        contracts: list[InterfaceContract],
        file_path: str,
        reasoning: str,
    ) -> Optional[ElementResult]:
        """Attempt template match or function-body decomposition.

        Returns an ``ElementResult`` if the element was handled without
        invoking Ollama, or ``None`` to proceed to generation.
        """
        # REQ-MP-1006: Template-first short-circuit
        template_match = self._templates.match(element, file_spec, contracts)
        if template_match is not None:
            struct_ok, struct_reason = _structural_verify(template_match.code, element)
            if not struct_ok:
                logger.info(
                    "Template short-circuit failed structural verify for %s: %s",
                    element.name, struct_reason,
                )
                return None  # fall through to Ollama
            logger.info(
                "Template short-circuit in _handle_simple for %s (template=%s)",
                element.name, template_match.name,
            )
            self._completed.append({
                "element": {
                    "name": element.name,
                    "parent_class": element.parent_class,
                    "kind": element.kind,
                },
                "file_path": file_path,
                "code": template_match.code,
                "syntax_valid": True,
                "repair_recovered": False,
                "repair_steps_count": 0,
            })
            result = ElementResult.make_template_match(
                element.name, file_path, TierClassification.SIMPLE, reasoning,
                template_match.code, template_match.name,
                generation_strategy="template",
            )
            self._metrics.record(result)
            return result

        # Phase 3: Function-body decomposition
        decomposer = self._function_body_decomposer
        if self._config.enable_simple_decomposer and decomposer is not None:
            _record_simple_decompose_attempted(file_path)
            decomposed_code = decomposer.try_decompose(
                element, file_spec, contracts,
            )
            if decomposed_code is not None:
                logger.info(
                    "Function-body decomposition succeeded for %s (0 LLM calls)",
                    element.name,
                )
                _record_simple_decompose_succeeded(file_path)
                self._completed.append({
                    "element": {
                        "name": element.name,
                        "parent_class": element.parent_class,
                        "kind": element.kind,
                    },
                    "file_path": file_path,
                    "code": decomposed_code,
                    "syntax_valid": True,
                    "repair_recovered": False,
                    "repair_steps_count": 0,
                })
                result = ElementResult.make_template_match(
                    element.name, file_path, TierClassification.SIMPLE, reasoning,
                    decomposed_code, "function_body_decompose",
                    generation_strategy="function_body_decompose",
                )
                result.decomposition_metadata = {
                    "strategy": "function_body_decompose",
                    "llm_calls": 0,
                }
                self._metrics.record(result)
                return result
            _record_simple_decompose_rejected(file_path)

        return None

    def _generate_with_ollama_retry(
        self,
        prompt: str,
        system_prompt: str,
        entity_name: str,
        *,
        max_tokens: int | None = None,
        stop_sequences: list[str] | None = None,
        validate_and_repair: Callable[[str, int], tuple[str | None, str | None]],
    ) -> _OllamaRetryOutcome:
        """Unified Ollama retry loop for both file-whole and element-body (R2).

        Args:
            prompt: The generation prompt.
            system_prompt: System prompt for the LLM.
            entity_name: Human-readable name for logging (element or file).
            max_tokens: Override max output tokens.
            stop_sequences: Override stop sequences.
            validate_and_repair: Callback ``(raw_code, attempt) -> (code, feedback)``.
                Returns ``(code, None)`` on success (break loop).
                Returns ``(None, "reason")`` on retriable failure (prepend feedback).
                Returns ``(None, None)`` on terminal failure (break loop).

        Returns:
            ``_OllamaRetryOutcome`` with ``code=None`` when all attempts failed.
        """
        max_attempts = max(1, self._config.local_max_attempts)
        input_tokens = 0
        output_tokens = 0
        llm_calls = 0
        last_failure_reason = ""
        last_raw = ""
        start = time.monotonic()

        for attempt in range(max_attempts):
            current_prompt = prompt
            if attempt > 0 and last_failure_reason:
                current_prompt = (
                    f"# RETRY: Previous attempt issues: {last_failure_reason}\n"
                    f"# Fix ONLY the issues above. Keep everything else.\n\n"
                    + prompt
                )

            try:
                raw_code, inp_tok, out_tok, finish_reason = self._generate_ollama(
                    current_prompt,
                    system_prompt=system_prompt,
                    max_tokens=max_tokens,
                    stop_sequences=stop_sequences,
                )
                # OLLAMA_QUALITY_RESEARCH_AGENDA Section 6: log finish_reason for
                # stop sequence verification (frequency table over 100+ runs).
                # OpenAI-compatible API returns "stop" (natural) or "length" (max_tokens).
                if finish_reason is not None:
                    logger.debug(
                        "ollama.generation.finish reason=%s entity=%s output_tokens=%d",
                        finish_reason,
                        entity_name,
                        out_tok,
                        extra={
                            "ollama": {
                                "finish_reason": finish_reason,
                                "entity_name": entity_name,
                                "output_tokens": out_tok,
                                "input_tokens": inp_tok,
                            }
                        },
                    )
                    _engine_metrics.record(
                        "ollama_finish_reason",
                        1,
                        {"finish_reason": finish_reason},
                    )
            except (ConnectionError, TimeoutError, OSError, RuntimeError, ValueError) as e:
                logger.warning(
                    "Ollama call failed for %s (attempt %d/%d): %s",
                    entity_name, attempt + 1, max_attempts, e,
                )
                self._record_local_failure()
                return _OllamaRetryOutcome(
                    code=None, raw_output=last_raw,
                    input_tokens=input_tokens, output_tokens=output_tokens,
                    llm_calls=llm_calls,
                    elapsed_ms=(time.monotonic() - start) * 1000,
                    last_failure_reason=str(e),
                )

            input_tokens += inp_tok
            output_tokens += out_tok
            llm_calls += 1

            if not raw_code or not raw_code.strip():
                logger.warning(
                    "Empty Ollama response for %s (attempt %d/%d)",
                    entity_name, attempt + 1, max_attempts,
                )
                last_failure_reason = "empty output"
                continue

            last_raw = raw_code

            repaired_code, feedback = validate_and_repair(raw_code, attempt)
            if repaired_code is not None:
                # Success
                return _OllamaRetryOutcome(
                    code=repaired_code, raw_output=raw_code,
                    input_tokens=input_tokens, output_tokens=output_tokens,
                    llm_calls=llm_calls,
                    elapsed_ms=(time.monotonic() - start) * 1000,
                )
            if feedback is None:
                # Terminal failure — no retry
                break
            last_failure_reason = feedback

        return _OllamaRetryOutcome(
            code=None, raw_output=last_raw,
            input_tokens=input_tokens, output_tokens=output_tokens,
            llm_calls=llm_calls,
            elapsed_ms=(time.monotonic() - start) * 1000,
            last_failure_reason=last_failure_reason,
        )

    def _generate_with_retry(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        skeleton: str,
        contracts: list[InterfaceContract],
        file_path: str,
        reasoning: str,
        model_name: str,
        element_fqn: str,
        start_time: float,
        *,
        design_doc_sections: Optional[list[str]] = None,
        task_description: Optional[str] = None,
    ) -> _GenerationOutcome:
        """Build prompt, call Ollama with retry, run repair pipeline.

        Returns a ``_GenerationOutcome``.  If all attempts fail,
        ``outcome.failure`` holds the escalation ``ElementResult``.
        """
        # Build few-shot examples
        few_shot = None
        if self._config.few_shot_enabled:
            few_shot = find_few_shot_examples(
                element, file_path, self._completed,
                max_examples=self._config.max_few_shot_examples,
            )

        prompt = build_body_prompt(
            element, file_spec, contracts,
            skeleton=skeleton,
            few_shot_examples=few_shot or None,
            token_budget=self._config.input_token_budget,
            design_doc_sections=design_doc_sections,
            task_description=task_description,
            domain_constraints=self._current_domain_constraints,
        )

        # ── Validate-and-repair closure for element-body path ──
        # Captures element, file_spec, skeleton from enclosing scope.
        # Each call runs the repair pipeline and returns (code, None) on
        # success or (None, feedback) on retriable AST failure.
        _last_repair_state: dict[str, Any] = {}

        def _validate_element(raw_code: str, attempt: int) -> tuple[str | None, str | None]:
            ast_valid_before = _ast_parse_valid(raw_code, element)
            code = raw_code
            repair_steps: list[str] = []
            repair_attribution = None
            repair_result = None
            repair_recovered = False

            if self._config.repair_enabled:
                repair_result = run_repair_pipeline(
                    code, element, file_spec, skeleton_source=skeleton,
                )
                code = repair_result.code
                repair_steps = repair_result.steps_applied
                repair_attribution = build_repair_attribution(
                    repair_result.step_results,
                )
                repair_recovered = repair_result.repair_recovered

                if not repair_result.ast_valid:
                    logger.warning(
                        "AST invalid after repair for %s (attempt %d)",
                        element.name, attempt + 1,
                    )
                    _last_repair_state.update(
                        ast_valid_before=ast_valid_before,
                        ast_valid_after=repair_result.ast_valid_after,
                        repair_recovered=repair_recovered,
                        repaired_code=code,
                        repair_steps=repair_steps,
                        repair_attribution=repair_attribution,
                        repair_result=repair_result,
                        raw_output=raw_code,
                    )
                    return None, repair_result.last_error or "ast.parse() failed"

            _last_repair_state.update(
                ast_valid_before=ast_valid_before,
                ast_valid_after=repair_result.ast_valid_after if repair_result else ast_valid_before,
                repair_recovered=repair_recovered,
                repaired_code=code,
                repair_steps=repair_steps,
                repair_attribution=repair_attribution,
                repair_result=repair_result,
                raw_output=raw_code,
            )
            return code, None

        retry_outcome = self._generate_with_ollama_retry(
            prompt, _ELEMENT_BODY_SYSTEM_PROMPT, element.name,
            validate_and_repair=_validate_element,
        )

        # Convert _OllamaRetryOutcome → _GenerationOutcome
        if retry_outcome.code is None:
            # All attempts failed — build escalation result
            esc_reason = EscalationReason.EMPTY_RESPONSE
            esc_detail = retry_outcome.last_failure_reason or "All attempts failed"
            esc_code: str | None = None

            repair_state = _last_repair_state
            repair_steps_out = repair_state.get("repair_steps", [])
            repair_attr_out = repair_state.get("repair_attribution")
            ast_before = repair_state.get("ast_valid_before", False)
            ast_after = repair_state.get("ast_valid_after", False)
            repair_recovered_out = repair_state.get("repair_recovered", False)
            repaired_code_out = repair_state.get("repaired_code")
            raw_out = repair_state.get("raw_output", retry_outcome.raw_output)
            repair_result_out = repair_state.get("repair_result")

            if repair_result_out is not None and not repair_result_out.ast_valid:
                esc_reason = EscalationReason.AST_FAILURE
                esc_detail = "AST validation failed after repair"
                esc_code = repaired_code_out
                esc_repair = to_escalation_repair_outcome(
                    element_fqn, raw_out, repair_result_out,
                )
                handoff = _build_escalation_handoff(
                    element, TierClassification.SIMPLE, model_name,
                    retry_outcome.llm_calls, esc_reason,
                    repair_result_out.last_error or "ast.parse() failed",
                    raw_output=raw_out,
                    repair_outcome=esc_repair,
                )
                failure = ElementResult.make_escalation(
                    element.name, file_path, TierClassification.SIMPLE, reasoning,
                    build_escalation_context(
                        element_name=element.name, file_path=file_path,
                        tier=TierClassification.SIMPLE,
                        reason=esc_reason, detail=esc_detail,
                        last_code=esc_code,
                        last_error=repair_result_out.last_error or "ast.parse() failed",
                        raw_output=raw_out, repaired_code=repaired_code_out,
                        repair_steps=repair_steps_out, local_model=model_name,
                        element_fqn=element_fqn, escalation_handoff=handoff,
                    ),
                    code=esc_code,
                    model=model_name,
                    generation_time_ms=(time.monotonic() - start_time) * 1000,
                    input_tokens=retry_outcome.input_tokens,
                    output_tokens=retry_outcome.output_tokens,
                    repair_steps_applied=repair_steps_out,
                    repair_attribution=repair_attr_out,
                    repair_recovered=repair_recovered_out,
                    ast_valid_before_repair=ast_before,
                    ast_valid_after_repair=ast_after,
                    verification_verdict="fail",
                    generation_strategy="element_body",
                )
            else:
                # Connection/timeout or empty-response failure
                if "Timeout" in esc_detail or "timeout" in esc_detail:
                    esc_reason = EscalationReason.TIMEOUT
                elif any(kw in esc_detail for kw in ("Connection", "connect", "Ollama", "Failed to create")):
                    esc_reason = EscalationReason.OLLAMA_UNAVAILABLE

                failure = ElementResult.make_escalation(
                    element.name, file_path, TierClassification.SIMPLE, reasoning,
                    build_escalation_context(
                        element_name=element.name, file_path=file_path,
                        tier=TierClassification.SIMPLE,
                        reason=esc_reason, detail=esc_detail,
                        local_model=model_name, element_fqn=element_fqn,
                    ),
                    model=model_name,
                    generation_time_ms=(time.monotonic() - start_time) * 1000,
                    input_tokens=retry_outcome.input_tokens,
                    output_tokens=retry_outcome.output_tokens,
                    generation_strategy="element_body",
                )

            return _GenerationOutcome(
                code=esc_code or "", raw_output=retry_outcome.raw_output,
                input_tokens=retry_outcome.input_tokens,
                output_tokens=retry_outcome.output_tokens,
                failure=failure,
            )

        # Success — extract repair state
        rs = _last_repair_state
        if retry_outcome.llm_calls > 1:
            logger.info(
                "Ollama succeeded for %s on attempt %d",
                element.name, retry_outcome.llm_calls,
            )
        return _GenerationOutcome(
            code=retry_outcome.code,
            raw_output=rs.get("raw_output", retry_outcome.raw_output),
            input_tokens=retry_outcome.input_tokens,
            output_tokens=retry_outcome.output_tokens,
            local_attempt=retry_outcome.llm_calls,
            ast_valid_before=rs.get("ast_valid_before", False),
            ast_valid_after=rs.get("ast_valid_after", False),
            repair_recovered=rs.get("repair_recovered", False),
            repaired_code=rs.get("repaired_code"),
            repair_steps=rs.get("repair_steps", []),
            repair_attribution=rs.get("repair_attribution"),
            repair_result=rs.get("repair_result"),
        )

    def _verify_and_build_result(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        skeleton: str,
        contracts: list[InterfaceContract],
        file_path: str,
        reasoning: str,
        model_name: str,
        element_fqn: str,
        start_time: float,
        outcome: _GenerationOutcome,
    ) -> ElementResult:
        """Run structural + semantic verification and build the final result."""
        code = outcome.code

        # Structural verification (REQ-MP-512)
        structural_ok, structural_reason = _structural_verify(code, element)
        if not structural_ok:
            struct_handoff = None
            if self._config.repair_enabled and outcome.repair_result is not None:
                struct_repair = to_escalation_repair_outcome(
                    element_fqn, outcome.raw_output, outcome.repair_result,
                )
                struct_handoff = _build_escalation_handoff(
                    element, TierClassification.SIMPLE, model_name,
                    outcome.local_attempt, EscalationReason.STRUCTURAL_MISMATCH,
                    structural_reason or "structural_verification_failed",
                    raw_output=outcome.raw_output,
                    repair_outcome=struct_repair,
                )
            return ElementResult.make_escalation(
                element.name, file_path, TierClassification.SIMPLE, reasoning,
                build_escalation_context(
                    element_name=element.name, file_path=file_path,
                    tier=TierClassification.SIMPLE,
                    reason=EscalationReason.STRUCTURAL_MISMATCH,
                    detail="Structural verification failed after repair",
                    last_code=code,
                    last_error=structural_reason or "structural_verification_failed",
                    raw_output=outcome.raw_output,
                    repaired_code=outcome.repaired_code or code,
                    repair_steps=outcome.repair_steps, local_model=model_name,
                    element_fqn=element_fqn, escalation_handoff=struct_handoff,
                ),
                code=code, model=model_name,
                generation_time_ms=(time.monotonic() - start_time) * 1000,
                input_tokens=outcome.input_tokens, output_tokens=outcome.output_tokens,
                repair_steps_applied=outcome.repair_steps,
                repair_attribution=outcome.repair_attribution,
                repair_recovered=outcome.repair_recovered,
                ast_valid_before_repair=outcome.ast_valid_before,
                ast_valid_after_repair=outcome.ast_valid_after,
                verification_verdict="fail",
                generation_strategy="element_body",
            )

        # Optional semantic verification (REQ-MP-512)
        if self._config.semantic_verification_enabled:
            semantic_ok, semantic_reason = self._semantic_verify(
                code, element, file_spec, contracts, skeleton,
            )
            if not semantic_ok:
                sem_handoff = None
                if self._config.repair_enabled and outcome.repair_result is not None:
                    sem_repair = to_escalation_repair_outcome(
                        element_fqn, outcome.raw_output, outcome.repair_result,
                    )
                    sem_handoff = _build_escalation_handoff(
                        element, TierClassification.SIMPLE, model_name,
                        outcome.local_attempt, EscalationReason.SEMANTIC_FAILURE,
                        semantic_reason or "semantic_verification_failed",
                        raw_output=outcome.raw_output,
                        repair_outcome=sem_repair,
                    )
                return ElementResult.make_escalation(
                    element.name, file_path, TierClassification.SIMPLE, reasoning,
                    build_escalation_context(
                        element_name=element.name, file_path=file_path,
                        tier=TierClassification.SIMPLE,
                        reason=EscalationReason.SEMANTIC_FAILURE,
                        detail="Semantic verification failed",
                        last_code=code,
                        last_error=semantic_reason or "semantic_verification_failed",
                        raw_output=outcome.raw_output,
                        repaired_code=outcome.repaired_code or code,
                        repair_steps=outcome.repair_steps, local_model=model_name,
                        element_fqn=element_fqn, escalation_handoff=sem_handoff,
                    ),
                    code=code, model=model_name,
                    generation_time_ms=(time.monotonic() - start_time) * 1000,
                    input_tokens=outcome.input_tokens, output_tokens=outcome.output_tokens,
                    repair_steps_applied=outcome.repair_steps,
                    repair_attribution=outcome.repair_attribution,
                    repair_recovered=outcome.repair_recovered,
                    ast_valid_before_repair=outcome.ast_valid_before,
                    ast_valid_after_repair=outcome.ast_valid_after,
                    verification_verdict="fail",
                    generation_strategy="element_body",
                )

        gen_time = (time.monotonic() - start_time) * 1000

        # Record as completed for few-shot
        self._completed.append({
            "element": {
                "name": element.name,
                "parent_class": element.parent_class,
                "kind": element.kind,
            },
            "file_path": file_path,
            "code": code,
            "syntax_valid": outcome.ast_valid_after,
            "repair_recovered": outcome.repair_recovered,
            "repair_steps_count": len(outcome.repair_steps),
        })

        return ElementResult.make_success(
            element.name, file_path, TierClassification.SIMPLE, reasoning, code,
            model=model_name,
            generation_time_ms=gen_time,
            input_tokens=outcome.input_tokens,
            output_tokens=outcome.output_tokens,
            repair_steps_applied=outcome.repair_steps,
            repair_attribution=outcome.repair_attribution,
            repair_recovered=outcome.repair_recovered,
            ast_valid_before_repair=outcome.ast_valid_before,
            ast_valid_after_repair=outcome.ast_valid_after,
            generation_strategy="element_body",
        )

    # Stop sequences for complete-function output mode (REQ-MP-206).
    # Safe because the model now outputs one complete `def` — a second
    # `\n\ndef ` means it's generating a second function.
    _OLLAMA_STOP_SEQUENCES: list[str] = [
        "\n\ndef ",          # Second function boundary
        "\n\nasync def ",    # Second async function boundary
        "\n\nclass ",        # Class boundary after function
        "\nif __name__",     # Common Python trailer
        "\n# Task:",         # Model echoing prompt template
        "\n# Implement",     # Model echoing prompt template
        "\n# Define",        # Model echoing constant prompt template
        "\n# Now implement",  # Model echoing "Now implement this:" marker
        "\n\n\n",            # Triple newline — generation exhausted
    ]

    # File-whole mode needs the LLM to produce a complete multi-definition
    # file, so the element-level stop sequences (which cut at ``\n\ndef ``,
    # ``\n\nclass ``, etc.) must be suppressed.  We keep only the
    # prompt-echo guards and the triple-newline exhaustion marker.
    _FILE_WHOLE_STOP_SEQUENCES: list[str] = [
        "\nif __name__",     # Common Python trailer
        "\n# Task:",         # Model echoing prompt template
        "\n# Implement",     # Model echoing prompt template
        "\n# Define",        # Model echoing constant prompt template
        "\n# Now implement",  # Model echoing "Now implement this:" marker
        "\n\n\n\n",          # Quadruple newline — generation exhausted
        # NOTE: triple newline (\n\n\n) was too aggressive — PEP 8 uses
        # two blank lines between top-level definitions, which produces
        # \n\n\n in the output and prematurely truncates file-whole generation.
    ]

    def _generate_ollama(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        *,
        stop_sequences: list[str] | None = None,
    ) -> tuple[str, int, int, str | None]:
        """Generate code using the Ollama provider.

        Returns (raw_text, input_tokens, output_tokens, finish_reason).

        Args:
            stop_sequences: Override stop sequences.  Pass an explicit list
                to replace the default element-level stops (e.g. use
                ``_FILE_WHOLE_STOP_SEQUENCES`` for file-whole mode).
                ``None`` uses ``_OLLAMA_STOP_SEQUENCES`` (element-body default).

        The raw LLM text is returned without pre-extraction so that the
        repair pipeline's ``fence_strip`` step can handle fence removal
        in one place (Fix 3 — removes redundant extract_code_from_response).

        finish_reason supports OLLAMA_QUALITY_RESEARCH_AGENDA Section 6
        (stop sequence verification): "stop" = natural stop, "length" =
        max_tokens exhausted.
        """
        if self._ollama_agent is None:
            from startd8.utils.agent_resolution import resolve_agent_spec

            agent_spec = f"{self._config.provider}:{self._config.model}"
            try:
                self._ollama_agent = resolve_agent_spec(
                    agent_spec, max_tokens=self._config.max_tokens,
                )
            except Exception as exc:
                raise ConnectionError(
                    f"Failed to create Ollama agent ({agent_spec}): {exc}"
                ) from exc

        effective_stops = (
            stop_sequences if stop_sequences is not None
            else self._OLLAMA_STOP_SEQUENCES
        )
        gen_kwargs: dict[str, Any] = dict(
            system_prompt=system_prompt or _ELEMENT_BODY_SYSTEM_PROMPT,
            temperature=self._config.temperature,
            stop=effective_stops,
        )
        if max_tokens is not None:
            gen_kwargs["max_tokens"] = max_tokens

        result_text, time_ms, token_usage = self._ollama_agent.generate(
            prompt, **gen_kwargs,
        )

        input_tokens = 0
        output_tokens = 0
        finish_reason: str | None = None
        if token_usage:
            input_tokens = getattr(token_usage, "input", 0) or 0
            output_tokens = getattr(token_usage, "output", 0) or 0
            finish_reason = getattr(token_usage, "finish_reason", None)
            if finish_reason and isinstance(finish_reason, str):
                pass
            else:
                finish_reason = None

        return result_text, input_tokens, output_tokens, finish_reason

    def _semantic_verify(
        self,
        code: str,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        contracts: list[InterfaceContract],
        skeleton: str,
    ) -> tuple[bool, str]:
        """Optional semantic verification hook (REQ-MP-512)."""
        verifier = self._config.semantic_verification_fn
        if verifier:
            try:
                return verifier(code, element, file_spec, contracts, skeleton)
            except Exception as exc:
                logger.warning("Semantic verifier failed: %s", exc)
                return False, f"semantic verifier error: {exc}"

        spec = self._config.semantic_verification_agent_spec
        if not spec:
            return True, "semantic verification skipped"

        if self._semantic_agent is None:
            from startd8.utils.agent_resolution import resolve_agent_spec

            self._semantic_agent = resolve_agent_spec(
                spec, max_tokens=self._config.semantic_verification_max_tokens,
            )

        prompt = [
            "You are verifying generated code for a target element.",
            f"Element: {element.name}",
        ]
        if element.parent_class:
            prompt.append(f"Parent class: {element.parent_class}")
        if element.signature:
            prompt.append(f"Signature: {element.signature.signature_text}")
        if element.docstring_hint:
            prompt.append(f"Docstring hint: {element.docstring_hint}")
        if contracts:
            prompt.append("Binding constraints:")
            for c in contracts:
                if c.binding_text:
                    prompt.append(f"- {c.binding_text}")
        if skeleton:
            skel = skeleton
            if len(skel) > self._config.semantic_verification_prompt_max_chars:
                skel = skel[: self._config.semantic_verification_prompt_max_chars] + "\n... [truncated]"
            prompt.append("Skeleton context:")
            prompt.append(skel)
        prompt.append("Generated code:")
        prompt.append("```python")
        prompt.append(code)
        prompt.append("```")
        prompt.append(
            "Return JSON: {\"pass\": true|false, \"reason\": \"short explanation\"}."
        )

        result_text, _time_ms, _tokens = self._semantic_agent.generate(
            "\n".join(prompt),
            temperature=self._config.semantic_verification_temperature,
        )

        try:
            start = result_text.find("{")
            end = result_text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise ValueError("no JSON object found")
            payload = json.loads(result_text[start : end + 1])
            passed = bool(payload.get("pass", False))
            reason = str(payload.get("reason", "")) or "semantic verification result"
            return passed, reason
        except Exception as exc:
            # AC-R9: Default to rejection on inconclusive verification.
            # The previous accept-on-failure policy meant any verifier
            # timeout, refusal, or malformed JSON silently bypassed
            # verification.  Rejecting triggers the retry loop and
            # eventual escalation — a safer failure mode.
            logger.warning("Semantic verification parse inconclusive: %s — rejecting", exc)
            return False, f"semantic verification inconclusive: {exc}"

    def _get_element_contracts(
        self,
        element: ForwardElementSpec,
        file_spec: ForwardFileSpec,
        manifest: ForwardManifest,
    ) -> list[InterfaceContract]:
        """Get contracts relevant to a specific element."""
        # Check if element has a source contract ID
        if element.source_contract_id:
            return [
                c for c in manifest.contracts
                if c.contract_id == element.source_contract_id
            ]
        # No source_contract_id — return empty rather than all contracts
        return []


def _has_high_within_file_coupling(
    file_spec: ForwardFileSpec,
    skeleton: str,
) -> bool:
    """Detect within-file element coupling that makes element-by-element risky.

    Returns True when the skeleton shows signs of cross-element dependencies:
    1. Module-level globals referenced by multiple functions/methods
    2. Functions/methods that call other functions/methods in the same file
    3. Classes with methods sharing instance state (``self.x`` writes in one
       method, reads in another)

    This is a skeleton-based heuristic (no call graph required) so it works
    even when the manifest doesn't carry call graph data.
    """
    try:
        tree = ast.parse(skeleton)
    except SyntaxError:
        return False

    # Collect element names from the file spec for reference matching.
    element_names = {e.name for e in file_spec.elements}

    # 1. Module-level global assignments (e.g., fake = Faker(), product_ids = [...])
    # AC-R10: Exclude common infrastructure globals that don't indicate
    # meaningful coupling (logger, log, app are universally referenced
    # but don't require cross-element context for generation).
    _INFRA_GLOBALS = {"logger", "log", "logging", "LOG", "LOGGER", "app", "db", "engine"}
    module_globals: set[str] = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id not in _INFRA_GLOBALS:
                    module_globals.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(
            getattr(node, "target", None), ast.Name
        ):
            if node.target.id not in _INFRA_GLOBALS:
                module_globals.add(node.target.id)

    # Also count CONSTANT/VARIABLE manifest elements that may not be in
    # the skeleton yet.  When the manifest declares module-level variables
    # (e.g. fake, product_ids), element-by-element generation may produce
    # code referencing them without knowing they exist.  Including them
    # here biases the routing toward file-whole, which sees the full
    # skeleton and handles module-level state correctly.
    for el in file_spec.elements:
        if (
            el.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE)
            and el.name not in _INFRA_GLOBALS
        ):
            module_globals.add(el.name)

    # 2. Scan function/method bodies for references to sibling elements
    #    or module-level globals.
    functions: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node)

    cross_refs = 0
    global_refs = 0
    for func in functions:
        for node in ast.walk(func):
            if isinstance(node, ast.Name):
                if node.id in element_names and node.id != func.name:
                    cross_refs += 1
                if node.id in module_globals:
                    global_refs += 1

    # 3. Class instance state sharing: count self.X writes in __init__ vs reads
    #    in other methods.
    init_writes: set[str] = set()
    other_reads: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    is_init = child.name == "__init__"
                    for sub in ast.walk(child):
                        if isinstance(sub, ast.Attribute) and isinstance(
                            getattr(sub, "value", None), ast.Name
                        ):
                            if sub.value.id == "self":
                                if is_init:
                                    init_writes.add(sub.attr)
                                else:
                                    other_reads.add(sub.attr)

    shared_attrs = init_writes & other_reads

    # Coupling thresholds — tuned after PI-008/run-042 analysis.
    # Previous thresholds (>=4) missed files where 2-3 functions each
    # referenced module-level state (product_ids, fake, config dicts).
    # Lowered global_refs threshold to 3 and added a density signal:
    # when module-level variables outnumber function/class elements,
    # element-by-element generation almost always loses state.
    n_elements = len([e for e in file_spec.elements if e.kind not in (
        ElementKind.CONSTANT, ElementKind.VARIABLE,
    )])
    module_var_ratio = len(module_globals) / max(n_elements, 1)

    has_coupling = (
        (global_refs >= 3 and len(module_globals) >= 2)
        or cross_refs >= 4
        or len(shared_attrs) >= 3
        # High module-variable density: more globals than functions/classes
        # strongly indicates cross-element state sharing.
        or (module_var_ratio >= 1.0 and len(module_globals) >= 2 and global_refs >= 1)
    )

    if has_coupling:
        logger.debug(
            "Coupling signals for %s: global_refs=%d, cross_refs=%d, "
            "shared_attrs=%d (%s), module_var_ratio=%.1f",
            file_spec.file, global_refs, cross_refs,
            len(shared_attrs), ", ".join(sorted(shared_attrs)[:5]),
            module_var_ratio,
        )

    return has_coupling


# ── Structural verification (AC-R4) ──────────────────────────────────
# Extracted to startd8.micro_prime.structural_verify for testability.
# Aliased here to preserve all 4 internal call sites unchanged.
from startd8.micro_prime.structural_verify import (  # noqa: E402
    ast_parse_valid as _ast_parse_valid,
    check_class_body_statements as _check_class_body_statements,
    structural_verify as _structural_verify,
    _is_not_implemented,
    _walk_body_only,
)
