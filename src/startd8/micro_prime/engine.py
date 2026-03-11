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
from collections.abc import Iterator
from dataclasses import dataclass, field as dc_field
from typing import Any, Optional

from startd8.element_id import make_element_id
from startd8.element_registry import (
    ElementEntry,
    ElementRegistry,
    compute_element_context_checksum,
    is_stale,
)
from startd8.forward_manifest import (
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
    run_repair_pipeline,
    to_escalation_repair_outcome,
)
from startd8.micro_prime.splicer import splice_body_into_skeleton
from startd8.micro_prime.templates import TemplateRegistry
from startd8.utils.code_manifest import ElementKind, Param, ParamKind, Signature

logger = get_logger(__name__)

# OTel decomposition metrics (REQ-MP-906) — optional dependency
try:
    from opentelemetry import metrics as otel_metrics

    _meter = otel_metrics.get_meter("startd8.micro_prime")
    _decomp_attempted = _meter.create_counter(
        "micro_prime.decomposition_attempted",
        description="Decomposition plans created",
    )
    _decomp_succeeded = _meter.create_counter(
        "micro_prime.decomposition_succeeded",
        description="Decomposition plans where all sub-elements succeeded",
    )
    _decomp_failed = _meter.create_counter(
        "micro_prime.decomposition_failed",
        description="Decomposition plans abandoned (sub-element or assembly failure)",
    )
    _decomp_rejected = _meter.create_counter(
        "micro_prime.decomposition_rejected",
        description="Elements where decompose() returned None",
    )
    _sub_elements_generated = _meter.create_counter(
        "micro_prime.sub_elements_generated",
        description="Individual sub-element generation attempts",
    )
    _decomp_time_ms = _meter.create_histogram(
        "micro_prime.decomposition_time_ms",
        description="End-to-end time for decompose + generate + assemble",
        unit="ms",
    )
    _assembly_time_ms = _meter.create_histogram(
        "micro_prime.assembly_time_ms",
        description="Time spent in decomposer assembly step",
        unit="ms",
    )
    # Phase 3: Simple decompose OTel counters
    _simple_decompose_attempted = _meter.create_counter(
        "micro_prime.simple_decompose_attempted",
        description="SIMPLE function body decomposition attempts",
    )
    _simple_decompose_succeeded = _meter.create_counter(
        "micro_prime.simple_decompose_succeeded",
        description="SIMPLE function body decompositions that produced code",
    )
    _simple_decompose_rejected = _meter.create_counter(
        "micro_prime.simple_decompose_rejected",
        description="SIMPLE function body decompositions that fell back to LLM",
    )
    # Recursion metrics (REQ-MP-914)
    _recursion_attempted = _meter.create_counter(
        "micro_prime.recursion_attempted",
        description="Recursive decomposition attempts",
    )
    _recursion_succeeded = _meter.create_counter(
        "micro_prime.recursion_succeeded",
        description="Recursive decomposition successes",
    )
    _recursion_rejected = _meter.create_counter(
        "micro_prime.recursion_rejected",
        description="Recursive decomposition rejections",
    )
    # Ollama-whole for MODERATE elements (Kaizen run-017 recalibration)
    _moderate_ollama_whole_attempted = _meter.create_counter(
        "micro_prime.moderate_ollama_whole_attempted",
        description="MODERATE elements where Ollama-whole was tried before decomposition",
    )
    _moderate_ollama_whole_succeeded = _meter.create_counter(
        "micro_prime.moderate_ollama_whole_succeeded",
        description="MODERATE elements resolved by Ollama-whole (no decomposition needed)",
    )
except ImportError:
    _decomp_attempted = None
    _decomp_succeeded = None
    _decomp_failed = None
    _decomp_rejected = None
    _sub_elements_generated = None
    _decomp_time_ms = None
    _simple_decompose_attempted = None
    _simple_decompose_succeeded = None
    _simple_decompose_rejected = None
    _recursion_attempted = None
    _recursion_succeeded = None
    _recursion_rejected = None
    _moderate_ollama_whole_attempted = None
    _moderate_ollama_whole_succeeded = None


def _record_decomp_attempted(strategy: str, file_path: str) -> None:
    if _decomp_attempted is not None:
        _decomp_attempted.add(1, {"strategy": strategy, "file_path": file_path})


def _record_decomp_succeeded(strategy: str, file_path: str) -> None:
    if _decomp_succeeded is not None:
        _decomp_succeeded.add(1, {"strategy": strategy, "file_path": file_path})


def _record_decomp_failed(
    strategy: str, file_path: str, failure_reason: str,
) -> None:
    if _decomp_failed is not None:
        _decomp_failed.add(1, {
            "strategy": strategy, "file_path": file_path,
            "failure_reason": failure_reason,
        })


def _record_decomp_rejected(file_path: str, rejection_reason: str) -> None:
    if _decomp_rejected is not None:
        _decomp_rejected.add(1, {
            "file_path": file_path, "rejection_reason": rejection_reason,
        })


def _record_sub_element(strategy: str, tier: str) -> None:
    if _sub_elements_generated is not None:
        _sub_elements_generated.add(1, {"strategy": strategy, "tier": tier})


def _record_decomp_time(strategy: str, duration_ms: float) -> None:
    if _decomp_time_ms is not None:
        _decomp_time_ms.record(duration_ms, {"strategy": strategy})


def _record_assembly_time(strategy: str, file_path: str, duration_ms: float) -> None:
    """Emit assembly_time_ms OTel histogram (REQ-MP-906)."""
    if _assembly_time_ms is not None:
        _assembly_time_ms.record(duration_ms, {"strategy": strategy, "file": file_path})


def _record_simple_decompose_attempted(file_path: str) -> None:
    if _simple_decompose_attempted is not None:
        _simple_decompose_attempted.add(1, {"file_path": file_path})


def _record_simple_decompose_succeeded(file_path: str) -> None:
    if _simple_decompose_succeeded is not None:
        _simple_decompose_succeeded.add(1, {"file_path": file_path})


def _record_simple_decompose_rejected(file_path: str) -> None:
    if _simple_decompose_rejected is not None:
        _simple_decompose_rejected.add(1, {"file_path": file_path})


def _record_moderate_ollama_whole_attempted(file_path: str) -> None:
    if _moderate_ollama_whole_attempted is not None:
        _moderate_ollama_whole_attempted.add(1, {"file_path": file_path})


def _record_moderate_ollama_whole_succeeded(file_path: str) -> None:
    if _moderate_ollama_whole_succeeded is not None:
        _moderate_ollama_whole_succeeded.add(1, {"file_path": file_path})


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
    same algorithm is used everywhere.
    """
    sig_str = str(element.signature) if element.signature else ""
    return compute_element_context_checksum(
        element_name=element.name,
        element_kind=element.kind.value if hasattr(element.kind, "value") else str(element.kind),
        signature=sig_str,
        parent_class=element.parent_class or "",
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


_CODE_GEN_SYSTEM_PROMPT = (
    "You are a Python code generator for the startd8 pipeline. "
    "Output the COMPLETE function definition including the `def` line, then STOP. "
    "Do NOT include markdown fences, explanations, or any text outside the code. "
    "Do NOT output additional functions, classes, or tests after the target function. "
    "Use ONLY the imports shown in the prompt — do not invent APIs or import new modules. "
    "Use 4-space indentation consistently."
)

# Separate system prompt for element-level body generation (Fix 1).
# The body prompt builder asks for indented body lines only (no def line),
# which contradicts _CODE_GEN_SYSTEM_PROMPT's "include the def line".
# Small local models cannot resolve conflicting system/user instructions
# reliably — they fall back to default behaviour (markdown fences, import
# blocks, wrong indentation).  Aligning the system prompt with the user
# prompt eliminates this confusion.
_ELEMENT_BODY_SYSTEM_PROMPT = (
    "You are a Python code generator. "
    "Output ONLY the indented body lines of the target function — no def line, "
    "no class wrapper, no imports, no markdown fences, no explanations. "
    "Use 4-space indentation consistently. Output code and NOTHING else."
)

# System prompt for file-level Ollama-whole generation.
# Instead of decomposing into individual element bodies, the model receives
# the complete skeleton file and fills ALL stubs in one pass.
_FILE_WHOLE_SYSTEM_PROMPT = (
    "You are a Python code generator. "
    "You are given a skeleton Python file with `raise NotImplementedError` stubs. "
    "Replace EVERY `raise NotImplementedError` with a working implementation. "
    "Output the COMPLETE Python file with all stubs filled in. "
    "Do NOT add markdown fences, explanations, or any text outside the code. "
    "Do NOT remove or rewrite existing imports, class definitions, or signatures. "
    "Preserve the file structure exactly — only replace stub bodies."
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
) -> str:
    """Build a prompt for file-level Ollama-whole generation.

    Instead of asking for individual element bodies, this sends the full
    skeleton and asks the model to fill ALL stubs in one pass.  This matches
    how the model naturally generates code (complete files) and avoids the
    body-only fragmentation that confuses small local models.

    Args:
        skeleton: Complete skeleton file with ``raise NotImplementedError`` stubs.
        file_spec: File spec for context (imports, element names).
        task_description: Optional feature-level description from seed.
        domain_constraints: Optional domain constraints from plan ingestion.

    Returns:
        The constructed prompt string.
    """
    sections: list[str] = []

    sections.append(
        "# Fill in ALL `raise NotImplementedError` stubs in this file."
    )
    sections.append(
        "# Output the COMPLETE file with every stub replaced by a working implementation."
    )
    sections.append(
        "# Do NOT change imports, class names, function signatures, or file structure."
    )
    sections.append("")

    if task_description:
        sections.append(f"# Task context: {task_description}")
        sections.append("")

    if domain_constraints:
        sections.append("# Domain constraints (MUST follow these):")
        for dc in domain_constraints:
            sections.append(f"# - {dc}")
        sections.append("")

    sections.append("# --- Skeleton file (fill in the stubs) ---")
    sections.append(skeleton)

    return "\n".join(sections)


def _validate_file_whole_result(
    generated_code: str,
    skeleton: str,
    file_spec: ForwardFileSpec,
) -> tuple[bool, str]:
    """Validate a file-level Ollama-whole generation result.

    Checks:
    1. AST parses successfully
    2. No remaining ``raise NotImplementedError`` stubs
    3. All expected elements are present in the AST
    4. No skeleton markers remain

    Returns:
        (success, reason) tuple.
    """
    # Strip markdown fences if present
    code = generated_code.strip()
    if code.startswith("```"):
        lines = code.splitlines()
        # Remove first line (```python or ```)
        lines = lines[1:]
        # Remove last line if it's a closing fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        code = "\n".join(lines).strip()

    if not code:
        return False, "empty output"

    # AST parse
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"ast.parse() failed: {e}"

    # Check for remaining stubs
    if "raise NotImplementedError" in code:
        return False, "contains unfilled NotImplementedError stubs"

    # Check for skeleton markers
    if "# [STARTD8-SKELETON]" in code:
        return False, "contains skeleton markers"

    # Verify expected elements exist in AST
    expected_names = {el.name for el in file_spec.elements}
    found_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found_names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found_names.add(target.id)

    missing = expected_names - found_names
    if missing:
        return False, f"missing elements: {', '.join(sorted(missing))}"

    return True, "all checks passed"


class MicroPrimeEngine:
    """Main orchestrator for local-first code generation.

    Processes manifest elements through classification, template matching,
    local model generation, repair, and body splicing.

    Args:
        config: Engine configuration.
        template_registry: Optional custom template registry.
        metrics_collector: Optional metrics collector for observability.
    """

    _CIRCUIT_BREAKER_THRESHOLD: int = 3   # per-file
    _RUN_BREAKER_THRESHOLD: int = 5       # per-run (E1: cross-file systemic failure)
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
            result = ElementResult(
                element_name=element.name,
                file_path=file_path,
                tier=tier,
                classification_reason=reasoning,
                success=True,
                code=cached_code,
                verification_verdict="skipped",
                api_file_import_bump=api_file_import_bump,
                api_element_adjustment=api_element_adjustment,
            )
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
                        result = ElementResult(
                            element_name=element.name,
                            file_path=file_path,
                            tier=tier,
                            classification_reason=reasoning,
                            success=True,
                            code=cached_code,
                            verification_verdict="skipped",
                            api_file_import_bump=api_file_import_bump,
                            api_element_adjustment=api_element_adjustment,
                            decomposition_metadata={"source": "element_registry"},
                        )
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
            result = ElementResult(
                element_name=element.name,
                file_path=file_path,
                tier=tier,
                classification_reason=reasoning,
                success=False,
                verification_verdict="skipped",
                api_file_import_bump=api_file_import_bump,
                api_element_adjustment=api_element_adjustment,
                escalation=build_escalation_context(
                    element_name=element.name,
                    file_path=file_path,
                    tier=tier,
                    reason=EscalationReason.CIRCUIT_BREAKER,
                    detail=(
                        f"Circuit breaker tripped after "
                        f"{self._CIRCUIT_BREAKER_THRESHOLD} consecutive failures"
                    ),
                ),
            )
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
            result = ElementResult(
                element_name=element.name,
                file_path=file_path,
                tier=tier,
                classification_reason=reasoning,
                success=False,
                verification_verdict="skipped",
                api_file_import_bump=api_file_import_bump,
                api_element_adjustment=api_element_adjustment,
                escalation=build_escalation_context(
                    element_name=element.name,
                    file_path=file_path,
                    tier=tier,
                    reason=EscalationReason.OLLAMA_UNAVAILABLE,
                    detail="Ollama unavailable — local generation skipped",
                ),
            )
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
            result = ElementResult(
                element_name=element.name,
                file_path=file_path,
                tier=tier,
                classification_reason=reasoning,
                success=False,
                verification_verdict="skipped",
                escalation=build_escalation_context(
                    element_name=element.name,
                    file_path=file_path,
                    tier=tier,
                    reason=EscalationReason.TIER_TOO_HIGH,
                    detail=f"Tier {tier.value}: {reasoning}",
                ),
            )

        # Stamp parent_class for downstream spec lookup (e.g. cloud escalation)
        result.parent_class = element.parent_class
        result.element_kind = element.kind.value
        result.api_file_import_bump = api_file_import_bump
        result.api_element_adjustment = api_element_adjustment

        # Step 3: Update circuit breaker and cache based on result
        if result.success:
            self._consecutive_failures = 0
            self._run_consecutive_failures = 0  # E1: success proves Ollama is working
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

        # ── File-level Ollama-whole attempt ──
        # For small files, try generating the complete file in one Ollama
        # call before decomposing into individual elements.  This avoids
        # the body-only prompt format that small models handle poorly.
        if ollama_available and self._is_file_ollama_whole_eligible(
            enriched_file_spec, skeleton,
        ):
            file_whole_result = self._attempt_file_ollama_whole(
                enriched_file_spec, skeleton,
                task_description=task_description,
                domain_constraints=domain_constraints,
            )
            if file_whole_result is not None:
                return file_whole_result

        # Pre-classify to determine processing order (REQ-MP-704).
        # Classification results are cached to avoid redundant work in
        # process_element() — each element is classified exactly once.
        classified: list[_ClassifiedElement] = []

        for element in enriched_file_spec.elements:
            contracts = self._get_element_contracts(element, enriched_file_spec, manifest)
            tier, reasoning, details = classify_element_with_details(
                element, enriched_file_spec, contracts,
                template_registry=self._templates,
                config=self._config,
            )
            priority = self._TIER_PRIORITY.get(tier, 2)
            classified.append(
                _ClassifiedElement(
                    priority=priority,
                    element=element,
                    contracts=contracts,
                    tier=tier,
                    reasoning=reasoning,
                    file_import_bump=details.file_import_bump,
                    element_api_adjustment=details.element_api_adjustment,
                    classification_signals=details.classification_signals,
                )
            )

        classified.sort(key=lambda c: c.sort_key)

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
                spliced = splice_body_into_skeleton(
                    result.code, element, current_skeleton,
                )
                if spliced is not None:
                    current_skeleton = spliced
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

        # Post-splice defect detection: if skeleton markers or
        # `raise NotImplementedError` stubs remain, the skeleton is
        # incomplete.  Mark remaining stub elements as failed so the
        # fill-rate gate in prime_adapter catches partial skeletons
        # instead of writing them to disk.
        _has_stubs = "raise NotImplementedError" in current_skeleton
        _has_marker = "# [STARTD8-SKELETON]" in current_skeleton
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

        file_result.filled_skeleton = current_skeleton
        return file_result

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

        Eligible when:
        - Feature is enabled in config
        - Element count ≤ max_elements threshold
        - Estimated LOC ≤ max_loc threshold
        - Skeleton has at least one ``raise NotImplementedError`` stub
        """
        if not self._config.file_ollama_whole_enabled:
            return False
        element_count = len(file_spec.elements)
        if element_count > self._config.file_ollama_whole_max_elements:
            logger.debug(
                "File-whole skipped for %s: %d elements > %d max",
                file_spec.file, element_count,
                self._config.file_ollama_whole_max_elements,
            )
            return False
        skeleton_lines = len(skeleton.splitlines())
        if skeleton_lines > self._config.file_ollama_whole_max_loc:
            logger.debug(
                "File-whole skipped for %s: %d lines > %d max",
                file_spec.file, skeleton_lines,
                self._config.file_ollama_whole_max_loc,
            )
            return False
        if "raise NotImplementedError" not in skeleton:
            logger.debug(
                "File-whole skipped for %s: no stubs in skeleton",
                file_spec.file,
            )
            return False
        return True

    def _attempt_file_ollama_whole(
        self,
        file_spec: ForwardFileSpec,
        skeleton: str,
        task_description: Optional[str] = None,
        domain_constraints: Optional[list[str]] = None,
    ) -> Optional[FileResult]:
        """Attempt to generate all elements in one Ollama call.

        Sends the complete skeleton file to the model and asks it to fill
        ALL ``raise NotImplementedError`` stubs in a single pass.  This avoids
        the body-only fragmentation that confuses small local models.

        Returns:
            FileResult if successful, None if the attempt failed (caller
            should fall through to element-by-element processing).
        """
        file_path = file_spec.file
        logger.info(
            "Attempting file-level Ollama-whole for %s (%d elements, %d lines)",
            file_path, len(file_spec.elements), len(skeleton.splitlines()),
        )

        prompt = _build_file_whole_prompt(
            skeleton, file_spec,
            task_description=task_description,
            domain_constraints=domain_constraints,
        )

        start_time = time.monotonic()
        try:
            raw_code, input_tokens, output_tokens = self._generate_ollama(
                prompt, system_prompt=_FILE_WHOLE_SYSTEM_PROMPT,
            )
        except (ConnectionError, TimeoutError, OSError, RuntimeError, ValueError) as e:
            logger.warning(
                "File-whole Ollama call failed for %s: %s", file_path, e,
            )
            return None

        gen_time = (time.monotonic() - start_time) * 1000

        if not raw_code or not raw_code.strip():
            logger.warning("File-whole returned empty output for %s", file_path)
            return None

        # Validate the generated file
        valid, reason = _validate_file_whole_result(raw_code, skeleton, file_spec)

        if not valid:
            logger.info(
                "File-whole validation failed for %s: %s — falling through to element-by-element",
                file_path, reason,
            )
            return None

        # Strip fences for the final code (validation already handles this
        # internally, but we need the clean version for the result).
        code = raw_code.strip()
        if code.startswith("```"):
            lines = code.splitlines()
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            code = "\n".join(lines).strip()

        logger.info(
            "File-whole succeeded for %s — %d elements filled in one shot",
            file_path, len(file_spec.elements),
        )

        # Build successful element results for each element
        model_name = f"{self._config.provider}:{self._config.model}"
        file_result = FileResult(file_path=file_path)
        per_element_tokens_in = input_tokens // max(len(file_spec.elements), 1)
        per_element_tokens_out = output_tokens // max(len(file_spec.elements), 1)

        for element in file_spec.elements:
            result = ElementResult(
                element_name=element.name,
                file_path=file_path,
                tier=TierClassification.SIMPLE,
                classification_reason="file_ollama_whole",
                parent_class=element.parent_class,
                element_kind=element.kind.value if element.kind else None,
                success=True,
                code=code,
                repair_recovered=False,
                ast_valid_before_repair=True,
                ast_valid_after_repair=True,
                verification_verdict="pass",
                model=model_name,
                generation_time_ms=gen_time / max(len(file_spec.elements), 1),
                input_tokens=per_element_tokens_in,
                output_tokens=per_element_tokens_out,
                decomposition_metadata={
                    "strategy": "file_ollama_whole",
                    "llm_calls": 1,
                },
            )
            file_result.element_results.append(result)

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

        return ElementResult(
            element_name=element.name,
            file_path=file_path,
            tier=TierClassification.MODERATE,
            classification_reason=reasoning,
            success=False,
            verification_verdict=verification_verdict,
            escalation=build_escalation_context(**esc_kwargs),
            decomposition_metadata=decomposition_metadata,
            generation_time_ms=generation_time_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

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
                self._record_local_failure()
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

        # Ollama-whole attempt (Kaizen run-017 recalibration): try single-shot
        # local generation before decomposition.  Many MODERATE elements are
        # generatable as a whole by Ollama — decomposition adds complexity and
        # failure modes (29% moderate vs 10% simple failure rate in run-017).
        if (
            self._config.moderate_ollama_whole_enabled
            and element.decomposition_source is None
            and self._is_ollama_whole_eligible(classification_signals)
        ):
            _record_moderate_ollama_whole_attempted(file_path)
            logger.info(
                "Attempting Ollama-whole for MODERATE element %s before decomposition",
                element.name,
            )
            ollama_result = self._handle_simple(
                element, file_spec, skeleton, contracts, file_path,
                f"moderate_ollama_whole: {reasoning}",
                design_doc_sections=design_doc_sections,
                task_description=task_description,
            )
            if ollama_result.success:
                _record_moderate_ollama_whole_succeeded(file_path)
                # Re-stamp tier as MODERATE (handle_simple stamps SIMPLE)
                ollama_result.tier = TierClassification.MODERATE
                ollama_result.decomposition_metadata = {
                    "strategy": "ollama_whole",
                    "llm_calls": 1,
                }
                logger.info(
                    "Ollama-whole succeeded for MODERATE element %s — skipping decomposition",
                    element.name,
                )
                return ollama_result
            logger.info(
                "Ollama-whole failed for %s — falling through to decomposition",
                element.name,
            )

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

        # Checkpoint few-shot history for rollback on failure
        completed_len = len(self._completed)

        # Generate each sub-element
        sub_results, total_input, total_output, failure = self._generate_sub_elements(
            plan, element, file_spec, skeleton, contracts, file_path,
            reasoning, start_time, design_doc_sections, task_description,
        )
        if failure is not None:
            self._completed = self._completed[:completed_len]
            return failure

        assert sub_results is not None  # guaranteed when failure is None

        # Assemble and verify
        assembled, assembly_time_ms, failure = self._assemble_and_verify_moderate(
            plan, sub_results, skeleton, element, file_path,
            reasoning, start_time, total_input, total_output,
        )
        if failure is not None:
            self._completed = self._completed[:completed_len]
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
            "repair_steps_count": 0,
        })

        # Record success for cache (R1-S7)
        moderate_fingerprint = (
            f"{element.parent_class or ''}:{element.name}"
            f":{file_path}:{TierClassification.MODERATE.value}"
        )
        self._success_cache[moderate_fingerprint] = assembled

        return ElementResult(
            element_name=element.name,
            file_path=file_path,
            tier=TierClassification.MODERATE,
            classification_reason=reasoning,
            success=True,
            code=assembled,
            model=f"{self._config.provider}:{self._config.model}",
            verification_verdict="pass",
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
            generation_time_ms=gen_time,
            input_tokens=total_input,
            output_tokens=total_output,
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
            "repair_steps_count": 0,
        })

        return ElementResult(
            element_name=element.name,
            file_path=file_path,
            tier=TierClassification.TRIVIAL,
            classification_reason=reasoning,
            success=True,
            code=body,
            template_used=True,
            template_name=match.name,
            model="template",
            verification_verdict="skipped",
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
                "repair_steps_count": 0,
            })
            result = ElementResult(
                element_name=element.name,
                file_path=file_path,
                tier=TierClassification.SIMPLE,
                classification_reason=reasoning,
                success=True,
                code=template_match.code,
                template_used=True,
                template_name=template_match.name,
                model="template",
                verification_verdict="skipped",
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
                    "repair_steps_count": 0,
                })
                result = ElementResult(
                    element_name=element.name,
                    file_path=file_path,
                    tier=TierClassification.SIMPLE,
                    classification_reason=reasoning,
                    success=True,
                    code=decomposed_code,
                    template_used=True,
                    template_name="function_body_decompose",
                    model="template",
                    verification_verdict="skipped",
                    decomposition_metadata={
                        "strategy": "function_body_decompose",
                        "llm_calls": 0,
                    },
                )
                self._metrics.record(result)
                return result
            _record_simple_decompose_rejected(file_path)

        return None

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

        max_local_attempts = max(1, self._config.local_max_attempts)
        last_escalation_result = None
        input_tokens = 0
        output_tokens = 0

        for local_attempt in range(1, max_local_attempts + 1):
            is_last_attempt = local_attempt == max_local_attempts

            try:
                code, attempt_in_tokens, attempt_out_tokens = self._generate_ollama(
                    prompt, system_prompt=_ELEMENT_BODY_SYSTEM_PROMPT,
                )
                input_tokens += attempt_in_tokens
                output_tokens += attempt_out_tokens
            except (ConnectionError, TimeoutError, OSError, RuntimeError, ValueError) as e:
                logger.warning(
                    "Ollama generation failed for %s (attempt %d/%d): %s",
                    element.name, local_attempt, max_local_attempts, e,
                )
                last_escalation_result = ElementResult(
                    element_name=element.name,
                    file_path=file_path,
                    tier=TierClassification.SIMPLE,
                    classification_reason=reasoning,
                    success=False,
                    repair_recovered=False,
                    ast_valid_before_repair=False,
                    ast_valid_after_repair=False,
                    verification_verdict="skipped",
                    model=model_name,
                    generation_time_ms=(time.monotonic() - start_time) * 1000,
                    escalation=build_escalation_context(
                        element_name=element.name,
                        file_path=file_path,
                        tier=TierClassification.SIMPLE,
                        reason=EscalationReason.EMPTY_RESPONSE,
                        detail=str(e),
                        local_model=model_name,
                        element_fqn=element_fqn,
                    ),
                )
                if is_last_attempt:
                    return _GenerationOutcome(
                        code="", raw_output="", failure=last_escalation_result,
                    )
                continue

            if not code or not code.strip():
                logger.warning(
                    "Empty Ollama response for %s (attempt %d/%d)",
                    element.name, local_attempt, max_local_attempts,
                )
                last_escalation_result = ElementResult(
                    element_name=element.name,
                    file_path=file_path,
                    tier=TierClassification.SIMPLE,
                    classification_reason=reasoning,
                    success=False,
                    repair_recovered=False,
                    ast_valid_before_repair=False,
                    ast_valid_after_repair=False,
                    verification_verdict="skipped",
                    model=model_name,
                    generation_time_ms=(time.monotonic() - start_time) * 1000,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    escalation=build_escalation_context(
                        element_name=element.name,
                        file_path=file_path,
                        tier=TierClassification.SIMPLE,
                        reason=EscalationReason.EMPTY_RESPONSE,
                        detail="Empty response from Ollama",
                        local_model=model_name,
                        element_fqn=element_fqn,
                    ),
                )
                if is_last_attempt:
                    return _GenerationOutcome(
                        code="", raw_output="",
                        input_tokens=input_tokens, output_tokens=output_tokens,
                        failure=last_escalation_result,
                    )
                continue

            raw_output = code
            ast_valid_before = _ast_parse_valid(code, element)
            ast_valid_after = ast_valid_before
            repair_recovered = False
            repaired_code = None

            # Run repair pipeline
            repair_steps: list[str] = []
            repair_attribution = None
            repair_result = None
            if self._config.repair_enabled:
                repair_result = run_repair_pipeline(
                    code, element, file_spec, skeleton_source=skeleton,
                )
                code = repair_result.code
                repair_steps = repair_result.steps_applied
                repair_attribution = build_repair_attribution(
                    repair_result.step_results,
                )
                ast_valid_after = repair_result.ast_valid_after
                repair_recovered = repair_result.repair_recovered
                repaired_code = code
                if not repair_result.ast_valid:
                    logger.warning(
                        "AST invalid after repair for %s (attempt %d/%d)",
                        element.name, local_attempt, max_local_attempts,
                    )
                    esc_repair = to_escalation_repair_outcome(
                        element_fqn, raw_output, repair_result,
                    )
                    handoff = _build_escalation_handoff(
                        element, TierClassification.SIMPLE, model_name,
                        local_attempt, EscalationReason.AST_FAILURE,
                        repair_result.last_error or "ast.parse() failed",
                        raw_output=raw_output,
                        repair_outcome=esc_repair,
                    )
                    last_escalation_result = ElementResult(
                        element_name=element.name,
                        file_path=file_path,
                        tier=TierClassification.SIMPLE,
                        classification_reason=reasoning,
                        success=False,
                        code=code,
                        repair_steps_applied=repair_steps,
                        repair_attribution=repair_attribution,
                        repair_recovered=repair_recovered,
                        ast_valid_before_repair=ast_valid_before,
                        ast_valid_after_repair=ast_valid_after,
                        verification_verdict="fail",
                        model=model_name,
                        generation_time_ms=(time.monotonic() - start_time) * 1000,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        escalation=build_escalation_context(
                            element_name=element.name,
                            file_path=file_path,
                            tier=TierClassification.SIMPLE,
                            reason=EscalationReason.AST_FAILURE,
                            detail="AST validation failed after repair",
                            last_code=code,
                            last_error=repair_result.last_error or "ast.parse() failed",
                            raw_output=raw_output,
                            repaired_code=repaired_code,
                            repair_steps=repair_steps,
                            local_model=model_name,
                            element_fqn=element_fqn,
                            escalation_handoff=handoff,
                        ),
                    )
                    if is_last_attempt:
                        return _GenerationOutcome(
                            code=code, raw_output=raw_output,
                            input_tokens=input_tokens, output_tokens=output_tokens,
                            failure=last_escalation_result,
                        )
                    continue

            # Generation + repair succeeded
            if local_attempt > 1:
                logger.info(
                    "Ollama succeeded for %s on attempt %d/%d",
                    element.name, local_attempt, max_local_attempts,
                )
            return _GenerationOutcome(
                code=code,
                raw_output=raw_output,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                local_attempt=local_attempt,
                ast_valid_before=ast_valid_before,
                ast_valid_after=ast_valid_after,
                repair_recovered=repair_recovered,
                repaired_code=repaired_code,
                repair_steps=repair_steps,
                repair_attribution=repair_attribution,
                repair_result=repair_result,
            )

        # Should not reach here — loop always returns — but satisfy type checker
        return _GenerationOutcome(  # pragma: no cover
            code="", raw_output="", failure=last_escalation_result,
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
            return ElementResult(
                element_name=element.name,
                file_path=file_path,
                tier=TierClassification.SIMPLE,
                classification_reason=reasoning,
                success=False,
                code=code,
                repair_steps_applied=outcome.repair_steps,
                repair_attribution=outcome.repair_attribution,
                repair_recovered=outcome.repair_recovered,
                ast_valid_before_repair=outcome.ast_valid_before,
                ast_valid_after_repair=outcome.ast_valid_after,
                verification_verdict="fail",
                model=model_name,
                generation_time_ms=(time.monotonic() - start_time) * 1000,
                input_tokens=outcome.input_tokens,
                output_tokens=outcome.output_tokens,
                escalation=build_escalation_context(
                    element_name=element.name,
                    file_path=file_path,
                    tier=TierClassification.SIMPLE,
                    reason=EscalationReason.STRUCTURAL_MISMATCH,
                    detail="Structural verification failed after repair",
                    last_code=code,
                    last_error=structural_reason or "structural_verification_failed",
                    raw_output=outcome.raw_output,
                    repaired_code=outcome.repaired_code or code,
                    repair_steps=outcome.repair_steps,
                    local_model=model_name,
                    element_fqn=element_fqn,
                    escalation_handoff=struct_handoff,
                ),
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
                return ElementResult(
                    element_name=element.name,
                    file_path=file_path,
                    tier=TierClassification.SIMPLE,
                    classification_reason=reasoning,
                    success=False,
                    code=code,
                    repair_steps_applied=outcome.repair_steps,
                    repair_attribution=outcome.repair_attribution,
                    repair_recovered=outcome.repair_recovered,
                    ast_valid_before_repair=outcome.ast_valid_before,
                    ast_valid_after_repair=outcome.ast_valid_after,
                    verification_verdict="fail",
                    model=model_name,
                    generation_time_ms=(time.monotonic() - start_time) * 1000,
                    input_tokens=outcome.input_tokens,
                    output_tokens=outcome.output_tokens,
                    escalation=build_escalation_context(
                        element_name=element.name,
                        file_path=file_path,
                        tier=TierClassification.SIMPLE,
                        reason=EscalationReason.SEMANTIC_FAILURE,
                        detail="Semantic verification failed",
                        last_code=code,
                        last_error=semantic_reason or "semantic_verification_failed",
                        raw_output=outcome.raw_output,
                        repaired_code=outcome.repaired_code or code,
                        repair_steps=outcome.repair_steps,
                        local_model=model_name,
                        element_fqn=element_fqn,
                        escalation_handoff=sem_handoff,
                    ),
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
            "syntax_valid": True,
            "repair_steps_count": len(outcome.repair_steps),
        })

        return ElementResult(
            element_name=element.name,
            file_path=file_path,
            tier=TierClassification.SIMPLE,
            classification_reason=reasoning,
            success=True,
            code=code,
            repair_steps_applied=outcome.repair_steps,
            repair_attribution=outcome.repair_attribution,
            repair_recovered=outcome.repair_recovered,
            ast_valid_before_repair=outcome.ast_valid_before,
            ast_valid_after_repair=outcome.ast_valid_after,
            verification_verdict="pass",
            model=model_name,
            generation_time_ms=gen_time,
            input_tokens=outcome.input_tokens,
            output_tokens=outcome.output_tokens,
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

    def _generate_ollama(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> tuple[str, int, int]:
        """Generate code using the Ollama provider.

        Returns (raw_text, input_tokens, output_tokens).

        The raw LLM text is returned without pre-extraction so that the
        repair pipeline's ``fence_strip`` step can handle fence removal
        in one place (Fix 3 — removes redundant extract_code_from_response).
        """
        if self._ollama_agent is None:
            from startd8.utils.agent_resolution import resolve_agent_spec

            agent_spec = f"{self._config.provider}:{self._config.model}"
            self._ollama_agent = resolve_agent_spec(
                agent_spec, max_tokens=self._config.max_tokens,
            )

        result_text, time_ms, token_usage = self._ollama_agent.generate(
            prompt,
            system_prompt=system_prompt or _CODE_GEN_SYSTEM_PROMPT,
            temperature=self._config.temperature,
            stop=self._OLLAMA_STOP_SEQUENCES,
        )

        input_tokens = 0
        output_tokens = 0
        if token_usage:
            input_tokens = getattr(token_usage, "input", 0) or 0
            output_tokens = getattr(token_usage, "output", 0) or 0

        return result_text, input_tokens, output_tokens

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
            logger.warning("Semantic verification parse failed: %s", exc)
            return False, "semantic verification parse failed"

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


def _ast_parse_valid(code: str, element: ForwardElementSpec) -> bool:
    """Return True if the code parses as a full element (method wrapper-aware)."""
    is_method = bool(element.parent_class)
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        if is_method:
            try:
                import textwrap

                wrapped = "class _Wrapper:\n" + textwrap.indent(code, "    ")
                ast.parse(wrapped)
                return True
            except SyntaxError:
                return False
        return False


def _structural_verify(code: str, element: ForwardElementSpec) -> tuple[bool, str]:
    """Verify structural correctness of generated code.

    Checks:
    - AST parses successfully
    - For functions: target function exists and body is non-empty
    - For constants: target assignment exists
    - No remaining NotImplementedError stubs
    - Return statements present when return annotation is non-None
    """
    is_method = bool(element.parent_class)

    def _render_def_line(target: ForwardElementSpec) -> Optional[str]:
        if target.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE, ElementKind.TYPE_ALIAS):
            return None
        if target.kind == ElementKind.CLASS:
            bases = f"({', '.join(target.bases)})" if target.bases else ""
            return f"class {target.name}{bases}:"
        prefix = "async def" if target.kind in (
            ElementKind.ASYNC_FUNCTION, ElementKind.ASYNC_METHOD,
        ) else "def"
        sig = "()"
        if target.signature:
            from startd8.utils.file_assembler import DeterministicFileAssembler

            assembler = DeterministicFileAssembler(element_registry=None)
            sig = assembler._render_signature(target.signature)
        ret = ""
        if target.signature and target.signature.return_annotation:
            ret = f" -> {target.signature.return_annotation}"
        return f"{prefix} {target.name}{sig}{ret}:"

    def _wrap_body(body: str, target: ForwardElementSpec) -> Optional[str]:
        def_line = _render_def_line(target)
        if def_line is None:
            return None
        wrapped = def_line + "\n" + textwrap.indent(body, "    ")
        if target.parent_class:
            wrapped = "class _Wrapper:\n" + textwrap.indent(wrapped, "    ")
        return wrapped

    # AST parse
    try:
        tree = ast.parse(code)
    except SyntaxError:
        wrapped = _wrap_body(code, element)
        if wrapped is None:
            return False, "ast.parse() failed"
        try:
            tree = ast.parse(wrapped)
        except SyntaxError:
            return False, "ast.parse() failed"

    # Check the target exists
    if element.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE):
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == element.name:
                        return True, "constant assignment found"
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and node.target.id == element.name:
                    return True, "annotated assignment found"
        return False, "constant assignment not found"

    # For CLASS elements, verify the class name exists in the AST (R1-S3)
    if element.kind == ElementKind.CLASS:
        if code.strip() == "pass":
            return True, "class shell pass"
        # Reject any remaining NotImplementedError stubs in class body.
        for node in ast.walk(tree):
            if isinstance(node, ast.Raise) and _is_not_implemented(node):
                return False, "contains NotImplementedError"
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == element.name:
                return True, "class definition found"
        # The assembled code from ModerateDecomposer is the body of the class. 
        # Since it successfully parsed via ast.parse(code) above, and assemble()
        # already verified it can reside inside a class block, we accept it.
        return True, "class body passed syntax check"

    # For functions/methods: verify the target name exists in the AST.
    target_node = None
    if is_method and element.parent_class:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == element.parent_class:
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == element.name:
                        target_node = child
                        break
                if target_node is not None:
                    break
        # Fallback: code may be a bare def without class wrapper (common from
        # body-generation prompts). Check top-level before expensive wrapping.
        if target_node is None:
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == element.name:
                    target_node = node
                    break
    else:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == element.name:
                target_node = node
                break

    if target_node is None:
        # Body-only generation: wrap into a synthetic def and re-parse.
        wrapped = _wrap_body(code, element)
        if wrapped is None:
            return False, "target function not found"
        try:
            tree = ast.parse(wrapped)
        except SyntaxError:
            return False, "target function not found"

        if element.parent_class:
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == "_Wrapper":
                    for child in node.body:
                        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == element.name:
                            target_node = child
                            break
                    if target_node is not None:
                        break
        else:
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == element.name:
                    target_node = node
                    break

        if target_node is None:
            return False, "target function not found"

    # Check for NotImplementedError stub — only direct body, not nested defs
    for node in _walk_body_only(target_node):
        if isinstance(node, ast.Raise) and _is_not_implemented(node):
            return False, "contains NotImplementedError"

    # Check return statements for non-None annotations — direct body only
    if element.signature and element.signature.return_annotation:
        ret_ann = element.signature.return_annotation
        if ret_ann not in ("None", "none"):
            has_return = any(
                isinstance(n, ast.Return) and n.value is not None
                for n in _walk_body_only(target_node)
            )
            if not has_return:
                return False, f"missing return for -> {ret_ann}"

    # Body must have at least one non-docstring statement
    body_stmts = []
    for stmt in target_node.body:
        if isinstance(stmt, ast.Expr) and isinstance(getattr(stmt, "value", None), ast.Constant):
            if isinstance(stmt.value.value, str):
                continue
        body_stmts.append(stmt)
    if not body_stmts:
        return False, "function body empty"

    return True, "structural checks passed"


def _walk_body_only(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> Iterator[ast.AST]:
    """Walk all AST nodes inside *func_node* except nested function bodies.

    This prevents false positives when a generated function contains inner
    helper functions — e.g. a ``raise NotImplementedError`` in a nested stub
    should not flag the outer function as incomplete.
    """
    for child in ast.iter_child_nodes(func_node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Yield the def node itself (for decorators/name checks) but
            # do NOT descend into its body.
            yield child
            continue
        yield child
        yield from ast.walk(child)


def _is_not_implemented(node: ast.Raise) -> bool:
    """Return True if a raise node corresponds to NotImplementedError."""
    if node.exc is None:
        return False
    exc = node.exc
    if isinstance(exc, ast.Call):
        func = exc.func
        if isinstance(func, ast.Name):
            return func.id == "NotImplementedError"
        if isinstance(func, ast.Attribute):
            return func.attr == "NotImplementedError"
    if isinstance(exc, ast.Name):
        return exc.id == "NotImplementedError"
    return False
