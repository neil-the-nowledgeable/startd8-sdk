"""
Context Seed Phase Handlers for ArtisanContractorWorkflow.

Bridges enriched context seeds (from PlanIngestionWorkflow + DomainPreflightWorkflow)
to the ArtisanContractorWorkflow orchestrator by providing concrete AbstractPhaseHandler
implementations for each WorkflowPhase.

WorkflowPhase mapping (from artisan_contractor.py docstring):
    PLAN      → Load seed + validate + build task plan
    SCAFFOLD  → Verify target directories + resolve dependencies
    DESIGN    → Generate design docs per task (single LLM call)
    IMPLEMENT → Generate code per task to staging dir
    INTEGRATE → Merge staged files into project_root with validation/rollback
    TEST      → Run post-generation validators against generated code
    REVIEW    → LLM-based quality review of generated implementations
    FINALIZE  → Collect artifacts + write comprehensive execution report

Context dict contract (keys populated by each phase):
    After PLAN:      tasks, task_index, plan_title, preflight_summary, domain_summary,
                     enriched_seed_path
    After SCAFFOLD:  scaffold (summary dict)
    After DESIGN:    design_results (Dict[task_id, dict] with design_document, agreed, iterations, cost)
    After IMPLEMENT: implementation (output dict), generation_results (Dict[task_id, GenerationResult])
    After INTEGRATE: integration_results (Dict[task_id, dict] with success, integrated_files)
    After TEST:      test_results (Dict with test_plan, per_task, total_cost)
    After REVIEW:    review_results (Dict with review_items, per_task, total_cost)
    After FINALIZE:  workflow_summary (final manifest dict)

Usage::

    from startd8.contractors.context_seed_handlers import ContextSeedHandlers
    from startd8.contractors.artisan_contractor import (
        ArtisanContractorWorkflow, WorkflowConfig, WorkflowPhase,
    )

    config = WorkflowConfig(dry_run=True, project_root="/path/to/project")
    workflow = ArtisanContractorWorkflow(config=config)

    handlers = ContextSeedHandlers.create_all(
        enriched_seed_path="out/<route>-context-seed-enriched.json",
        # e.g. "out/prime-context-seed-enriched.json" or
        #      "out/artisan-context-seed-enriched.json"
    )
    for phase, handler in handlers.items():
        workflow.register_handler(phase, handler)

    result = workflow.execute(context={})
"""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import json
import os.path
import re
import shlex
import subprocess
import sys
import threading
import time
import warnings
from collections import defaultdict
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

from startd8.contractors.artisan_contractor import (
    AbstractPhaseHandler,
    WorkflowPhase,
    _SAFE_TASK_ID_PATTERN,
    compute_lanes,
)
from startd8.contractors.protocols import (
    CodeGenerator,
    DRAFT_MODEL_CLAUDE_HAIKU,
    GenerationResult,
    REVIEW_MODEL_CLAUDE_OPUS,
    VALIDATE_MODEL_CLAUDE_SONNET,
)
from startd8.utils.file_operations import atomic_write_json
from startd8.utils.retry import RetryConfig, _is_retryable_exception, _calculate_delay
from startd8.utils.token_usage import (
    token_usage_cost,
    token_usage_input,
    token_usage_output,
)

from startd8.contractors.context_schema import (
    FinalizePhaseOutput,
    ImplementPhaseOutput,
    ReviewPhaseOutput,
    ValidationPhaseOutput,
)
from startd8.contractors.context_seed.shared import (
    SeedTask,
    _ensure_context_loaded,
    _load_enriched_seed,
    _log_context_completeness,
    _parse_tasks,
    _topological_sort,
    _track_onboarding_consumption,
)
from startd8.contractors.context_seed.phases.plan import PlanPhaseHandler
from startd8.contractors.context_seed.phases.scaffold import ScaffoldPhaseHandler
from startd8.contractors.context_seed.design_support import (
    _classify_complexity_tier,
    _compute_ccd_task_metadata,
    _detect_cross_file_edges,
    _extract_design_target_files,
    _extract_referenced_elements,
    _extract_structural_delta,
    _extract_complexity_signals,
    _infer_path_prefix,
    _normalize_target_path,
    _set_default_complexity_metadata,
    build_shared_file_manifest,
    compute_critical_path_tasks,
    compute_lane_to_file_mapping,
)
from startd8.contractors.artisan_contractor import HAS_OTEL, _NoOpSpan
from startd8.exceptions import Startd8Error
from startd8.logging_config import get_logger
from startd8.otel import attach_context, capture_context, detach_context
from startd8.utils.artifact_inventory import (
    load_artifact_content,
    load_inventory,
    lookup_artifact,
)
from startd8.contractors.artisan_phases.self_consistency import (
    validate_protocol_fidelity,
    validate_dockerfile_coherence,
)

logger = get_logger("startd8.contractors.context_seed_handlers")

if TYPE_CHECKING:  # pragma: no cover - typing-only imports
    from startd8.contractors.context_seed.phases.design import DesignPhaseHandler

from startd8.contractors.context_seed.tracing import _HAS_OTEL, _phase_tracer

_CACHE_SCHEMA_VERSION = 3

# Maximum file size for hash computation (50 MB).  Files larger than this
# are skipped to prevent memory spikes during cache validation.
_MAX_GEN_FILE_HASH_BYTES = 50 * 1024 * 1024

# PCA-603: Gate 4 size regression detection thresholds (configurable).
_SIZE_REGRESSION_THRESHOLD = 0.70
_SIZE_REGRESSION_MIN_LINES = 50


def _dict_to_gen_result(d: dict) -> GenerationResult:
    """Convert a plain dict (e.g. from JSON cache) to a GenerationResult dataclass.

    This is used as a normalization step after loading cached generation_results
    from disk so that downstream phases can safely access attributes like
    ``.cost_usd`` and ``.success`` without risking AttributeError on raw dicts.
    """
    return GenerationResult(
        success=d.get("success", False),
        generated_files=[Path(p) for p in d.get("generated_files", [])],
        error=d.get("error"),
        input_tokens=d.get("input_tokens", 0),
        output_tokens=d.get("output_tokens", 0),
        cost_usd=d.get("cost_usd", 0.0),
        iterations=d.get("iterations", 1),
        model=d.get("model", ""),
        metadata=d.get("metadata", {}),
    )


# ---------------------------------------------------------------------------
# E6: Cross-phase provenance linking helpers
# ---------------------------------------------------------------------------

# Maps phase names to the context key holding per-task results for that phase.
_PHASE_RESULT_KEYS: dict[str, str] = {
    "design": "design_results",
    "implement": "generation_results",
    "integrate": "integration_results",
}


def _capture_task_span_context(span: Any) -> dict[str, str] | None:
    """Extract trace_id + span_id from a task span.

    Returns ``None`` when OTel is unavailable, the span is a ``_NoOpSpan``,
    or the span context is invalid.  Uses hex format matching
    ``forensic_log._extract_exemplars()`` for consistency.
    """
    if not _HAS_OTEL:
        return None
    try:
        ctx = span.get_span_context()
        if ctx is None or not getattr(ctx, "is_valid", False):
            return None
        return {
            "trace_id": format(ctx.trace_id, "032x"),
            "span_id": format(ctx.span_id, "016x"),
        }
    except Exception:
        return None


def _build_provenance_links(
    task_id: str,
    context: dict[str, Any],
    link_phases: list[str],
) -> list:
    """Build OTel ``Link`` objects from upstream phase span contexts.

    Returns ``[]`` when OTel is unavailable or no upstream span contexts
    are found for *task_id* in the requested *link_phases*.
    """
    if not _HAS_OTEL:
        return []
    from opentelemetry.trace import Link, SpanContext, TraceFlags

    links: list = []
    for phase in link_phases:
        result_key = _PHASE_RESULT_KEYS.get(phase)
        if not result_key:
            continue
        task_result = context.get(result_key, {}).get(task_id)
        if task_result is None:
            continue
        # Handle both plain dicts and objects with .metadata dict
        if isinstance(task_result, dict):
            span_ctx = task_result.get("_span_context")
        elif hasattr(task_result, "metadata") and isinstance(
            task_result.metadata, dict
        ):
            span_ctx = task_result.metadata.get("_span_context")
        else:
            continue
        if not isinstance(span_ctx, dict):
            continue
        try:
            links.append(
                Link(
                    context=SpanContext(
                        trace_id=int(span_ctx["trace_id"], 16),
                        span_id=int(span_ctx["span_id"], 16),
                        is_remote=False,
                        trace_flags=TraceFlags(0x01),
                    ),
                    attributes={"link.phase": phase, "link.task_id": task_id},
                )
            )
        except (KeyError, ValueError, TypeError):
            continue
    return links


# ---------------------------------------------------------------------------
# PCA-600: Typed data structures for edit-mode classification
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PerFileMode:
    """Per-file edit/create classification with supporting signals."""

    mode: str  # "edit" or "create"
    staleness: str  # "fresh", "stale", or ""
    has_hash: bool
    edit_weight: int = 0
    manifest_element_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "staleness": self.staleness,
            "has_hash": self.has_hash,
            "edit_weight": self.edit_weight,
            "manifest_element_count": self.manifest_element_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PerFileMode:
        return cls(
            mode=data["mode"],
            staleness=data.get("staleness", ""),
            has_hash=data.get("has_hash", False),
            edit_weight=data.get("edit_weight", 0),
            manifest_element_count=data.get("manifest_element_count", 0),
        )


@dataclass(frozen=True)
class EditModeClassification:
    """Typed result of edit-mode classification for a task.

    Consumed by Steps 0b, 0c, 0d, and Layers A, B, C, D.
    JSON-serializable for checkpoint persistence and resume.
    """

    mode: str  # "edit" or "create"
    per_file: dict[str, PerFileMode]
    confidence: str  # "high", "medium", or "low"
    signal_conflicts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "per_file": {k: v.to_dict() for k, v in self.per_file.items()},
            "confidence": self.confidence,
            "signal_conflicts": list(self.signal_conflicts),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EditModeClassification:
        per_file_raw = data.get("per_file", {})
        per_file = {
            k: PerFileMode.from_dict(v) if isinstance(v, dict) else v
            for k, v in per_file_raw.items()
        }
        return cls(
            mode=data.get("mode", "create"),
            per_file=per_file,
            confidence=data.get("confidence", "low"),
            signal_conflicts=data.get("signal_conflicts", []),
        )


def _compute_gen_file_hash(
    file_paths: list[Any],
    max_file_size: int = _MAX_GEN_FILE_HASH_BYTES,
) -> str | None:
    """Compute SHA-256 of concatenated generated file contents.

    Files are sorted by string path before hashing so the digest is
    deterministic regardless of file ordering in GenerationResult.

    Args:
        file_paths: Paths to generated files (Path objects or strings).
        max_file_size: Skip files larger than this (bytes) to prevent
            memory spikes on unexpectedly large artifacts.

    Returns:
        Hex digest, or ``None`` if no files are readable.
    """
    h = hashlib.sha256()
    any_read = False
    for fp in sorted(str(p) for p in file_paths):
        p = Path(fp)
        try:
            if not p.is_file():
                continue
            st = p.stat()
            if st.st_size > max_file_size:
                logger.debug(
                    "Skipping oversized file for hash: %s (%d bytes)",
                    p, st.st_size,
                )
                continue
            h.update(p.read_bytes())
            any_read = True
        except OSError:
            continue
    return h.hexdigest() if any_read else None


def _compute_design_results_hash(design_results: dict[str, Any]) -> str | None:
    """Compute SHA-256 over design_results for cache invalidation.

    When the design changes between runs (e.g. ``--force-design``),
    cached TEST/REVIEW results are stale because the implementation
    they validated was built from a different design.

    Returns hex digest, or ``None`` if design_results is empty.
    """
    if not design_results:
        return None
    # Deterministic: sort by task_id, then serialize
    h = hashlib.sha256()
    for tid in sorted(design_results.keys()):
        entry = design_results[tid]
        # Hash the design document content (primary driver of implementation)
        doc = ""
        if isinstance(entry, dict):
            doc = entry.get("design_document", "") or ""
        h.update(tid.encode("utf-8"))
        h.update(doc.encode("utf-8"))
    return h.hexdigest()


from startd8.contractors.gate_contracts import GateEmitter

__all__ = [
    "HandlerConfig",
    "ContextSeedHandlers",
    "PlanPhaseHandler",
    "ScaffoldPhaseHandler",
    "DesignPhaseHandler",
    "ImplementPhaseHandler",
    "TestPhaseHandler",
    "ReviewPhaseHandler",
    "FinalizePhaseHandler",
]


def __getattr__(name: str) -> Any:
    if name == "DesignPhaseHandler":
        from startd8.contractors.context_seed.phases.design import DesignPhaseHandler
        return DesignPhaseHandler
    raise AttributeError(name)


def _log_task_timing(
    phase: str,
    task_id: str,
    index: int,
    total: int,
    phase_started_mono: float,
    previous_task_started_mono: Optional[float],
) -> float:
    """Log elapsed and inter-task timing for a phase task loop."""
    now = time.monotonic()
    elapsed_s = now - phase_started_mono
    elapsed_m = elapsed_s / 60.0
    delta_s = 0.0 if previous_task_started_mono is None else now - previous_task_started_mono
    logger.info(
        "%s task %d/%d: %s (elapsed %.1fs / %.2fmin, +%.1fs since previous task)",
        phase,
        index,
        total,
        task_id,
        elapsed_s,
        elapsed_m,
        delta_s,
    )
    return now


def _log_task_boundary_start(task: Any, *, phase: str) -> None:
    """Emit AL-202 task-start debug log with structured fields."""
    logger.debug(
        "Processing task %s: %s",
        task.task_id,
        task.title,
        extra={
            "task_id": task.task_id,
            "task_title": task.title,
            "phase": phase,
            "domain": task.domain,
        },
    )


def _log_task_boundary_complete(
    task_id: str,
    *,
    status: str,
    phase: str,
    cost_usd: Optional[float] = None,
) -> None:
    """Emit AL-202 task-completion debug log with structured fields."""
    extra: dict[str, Any] = {
        "task_id": task_id,
        "status": status,
        "phase": phase,
    }
    if cost_usd is not None:
        extra["cost_usd"] = cost_usd
    logger.debug("Task %s completed: %s", task_id, status, extra=extra)


def _coerce_optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ============================================================================
# Handler configuration
# ============================================================================


@dataclass
class HandlerConfig:
    """Shared configuration propagated to all phase handlers.

    Attributes:
        lead_agent: Agent spec for architect/reviewer.
            Defaults to ``REVIEW_MODEL_CLAUDE_OPUS`` from the model catalog.
        drafter_agent: Agent spec for drafter.
            Defaults to ``DRAFT_MODEL_CLAUDE_HAIKU`` from the model catalog.
        max_iterations: Maximum draft → review iterations per task.
        pass_threshold: Minimum review score (0-100) to pass.
        max_tokens: Override max_tokens for agent creation (None = provider default).
        design_max_tokens: Override max_output_tokens for design phase LLM calls.
            When set, overrides per-task design_calibration max_output_tokens.
            Use to avoid truncation for complex design docs (e.g., 8192).
        design_task_retries: Number of retries per task on transient API errors
            during the DESIGN phase. 0 = no retry; total attempts = 1 + retries.
            Uses exponential backoff (5s base, 60s max). Default: 2.
        fail_on_truncation: Fail workflow on detected truncation.
        check_truncation: Enable heuristic truncation detection.
        strict_truncation: Use strict detection threshold.
        test_timeout_seconds: Timeout for each validator subprocess.
        review_temperature: Temperature for LLM review calls.
        review_max_code_chars: Max characters of generated code to include in review prompt.
        review_task_retries: Number of retries per task on transient API errors
            during the REVIEW phase. 0 = no retry; total attempts = 1 + retries.
            Uses exponential backoff (5s base, 60s max). Default: 2.
        development_timeout_seconds: Timeout for the DevelopmentPhase thread (None = no limit).
        scaffold_test_first: For artifact generator tasks, ensure test scaffolding exists
            before implementation (Item 12). Default True.
        force_implement: If True, ignore cached generation_results and always run fresh
            IMPLEMENT (no resume from .startd8/state/generation_results.json).
    """

    lead_agent: str = REVIEW_MODEL_CLAUDE_OPUS.agent_spec
    drafter_agent: str = DRAFT_MODEL_CLAUDE_HAIKU.agent_spec
    max_iterations: int = 3
    pass_threshold: int = 80
    max_tokens: Optional[int] = None
    design_max_tokens: Optional[int] = None
    design_task_retries: int = 2
    fail_on_truncation: bool = True
    check_truncation: bool = True
    strict_truncation: bool = False
    test_timeout_seconds: int = 300  # Aligned with FinalTestingPhase.pytest_timeout
    review_temperature: float = 0.0
    review_max_code_chars: int = 32000
    review_task_retries: int = 2
    development_timeout_seconds: Optional[float] = None
    auto_commit: bool = True
    scaffold_test_first: bool = True
    force_implement: bool = False
    force_design: bool = False
    refine_design: bool = False
    force_rewrite: bool = False
    force_review: bool = False
    force_test: bool = False
    design_agent: Optional[str] = None
    review_agent: Optional[str] = None
    enable_prompt_caching: bool = False
    staging_dir: Optional[str] = None  # None = .startd8/staging/
    forensic_log_level: str = "INFO"  # "DEBUG" | "INFO" | "WARNING"
    # CCD-503: Collision resolution strategy ("warn" | "redesign" | "abort")
    design_collision_strategy: str = "warn"
    enforce_post_revision_rereview: bool = True
    # Phase 4: Manifest consumption control
    manifest_consumption_enabled: bool = True  # Kill switch (req R1-S10)
    manifest_context_budget: int = 4000  # Max chars for element summary in prompts
    manifest_registry: Any = None  # ManifestRegistry instance (avoid import)
    # Phase 5: Introspect pipeline (PI-1, PI-2, PI-3)
    enable_introspect: bool = False  # Use resolved types + module_version when True
    # Phase 6: Call graph pipeline control
    call_graph_context_budget: int = 2000  # Max chars for call graph in IMPLEMENT prompts
    call_graph_review_budget: int = 1500  # Max chars for call graph in REVIEW prompts
    blast_radius_warning_threshold: int = 20  # Blast radius count triggering WARNING
    blast_radius_max_depth: int = 3  # Max BFS depth for blast radius computation
    enable_call_graph_preflight: bool = True  # Enable call graph preflight rule
    # Multi-tier model architecture (T1/T2/T3)
    tier2_agent: Optional[str] = None          # T2 refiner spec; resolved in __post_init__
    skip_refinement: bool = False              # Bypass T2 entirely
    # Walk-through mode: build and persist all LLM prompts without calling LLMs
    walkthrough: bool = False
    # Complexity-Driven Model Router (CMR) — REQ-CMR-003
    complexity_routing_enabled: bool = True     # Kill switch: False → all chunks Tier 2
    tier3_agent: Optional[str] = None           # Opus drafter spec; resolved in __post_init__
    complexity_blast_radius_tier3: int = 5      # Blast radius threshold for Tier 3
    complexity_loc_tier1_max: int = 150         # Max LOC for Tier 1 eligibility
    complexity_loc_tier3_min: int = 500         # Min LOC to trigger Tier 3
    complexity_caller_tier3: int = 3            # Caller count threshold for Tier 3 (edit mode)
    # REQ-CMR-022: Gate-driven Tier 2 escalation mode (bounded to one T2 pass)
    complexity_tier2_gate_escalation: bool = False

    # REQ-DSR-005: Inner loop enabled by default — uses implementation_engine
    # (spec → drafter → reviewer score loop) instead of single-shot DevelopmentPhase.
    # Cost: ~$2-5 per 10 tasks at avg 2 iterations (1 spec + up to 3 draft + 3 review).
    enable_inner_loop: bool = True
    inner_loop_drafter: Optional[str] = None   # Override drafter agent for inner loop
    inner_loop_reviewer: Optional[str] = None  # Override reviewer agent for inner loop
    inner_loop_max_iterations: int = 3         # Max draft-review cycles per task
    inner_loop_pass_threshold: int = 80        # Min review score (0-100)

    # Micro Prime: local-first code generation for TRIVIAL/SIMPLE elements (REQ-MP-503)
    micro_prime_enabled: bool = False          # Kill switch for Micro Prime pre-pass

    _VALID_COLLISION_STRATEGIES = frozenset({"warn", "redesign", "abort"})

    def __post_init__(self) -> None:
        if self.force_design and self.refine_design:
            raise ValueError(
                "force_design and refine_design are mutually exclusive"
            )
        if self.forensic_log_level not in ("DEBUG", "INFO", "WARNING"):
            raise ValueError(
                f"forensic_log_level must be DEBUG, INFO, or WARNING; "
                f"got {self.forensic_log_level!r}"
            )
        if self.design_collision_strategy not in self._VALID_COLLISION_STRATEGIES:
            raise ValueError(
                f"design_collision_strategy must be one of "
                f"{sorted(self._VALID_COLLISION_STRATEGIES)}; "
                f"got {self.design_collision_strategy!r}"
            )
        # Resolve T2 default: Sonnet unless skip_refinement is set
        if self.tier2_agent is None and not self.skip_refinement:
            self.tier2_agent = VALIDATE_MODEL_CLAUDE_SONNET.agent_spec
        # Resolve T3 default: Opus for complex tasks (REQ-CMR-003)
        if self.tier3_agent is None:
            self.tier3_agent = REVIEW_MODEL_CLAUDE_OPUS.agent_spec

    @classmethod
    def from_config(
        cls,
        cli_overrides: Optional[dict[str, Any]] = None,
    ) -> "HandlerConfig":
        """Build a HandlerConfig using the 3-tier priority chain.

        Priority: *cli_overrides* > env vars / config file (via
        ``ConfigManager.get_artisan_setting``) > dataclass defaults.

        Args:
            cli_overrides: Dict of field-name → value from CLI args.
                Only non-``None`` entries are considered overrides.

        Returns:
            A fully resolved ``HandlerConfig``.
        """
        from startd8.config import get_config_manager

        cfg_mgr = get_config_manager()
        overrides = cli_overrides or {}
        kwargs: dict[str, Any] = {}

        for f in fields(cls):
            # CLI override wins
            cli_val = overrides.get(f.name)
            if cli_val is not None:
                kwargs[f.name] = cli_val
                continue

            # Config manager checks env var → config file
            cfg_val = cfg_mgr.get_artisan_setting(f.name)
            if cfg_val is not None:
                kwargs[f.name] = cfg_val
                continue

            # Otherwise let the dataclass default apply (omit from kwargs)

        return cls(**kwargs)


class ImplementPhaseHandler(AbstractPhaseHandler):
    """IMPLEMENT phase: Generate code per task via DevelopmentPhase engine.

    In dry-run mode: reports what would be implemented per task (unchanged).
    In real mode: delegates to :class:`DevelopmentPhase` with a
    :class:`LeadContractorChunkExecutor`, gaining parallelism, state
    persistence, crash recovery, and retry with error-informed feedback.

    Bridges the sync ``handler.execute()`` call from
    :class:`ArtisanContractorWorkflow` to the async ``DevelopmentPhase.run()``
    via ``asyncio.run()``.

    Data flow:
        1. ``SeedTask`` list → ``DevelopmentChunk`` list (``_tasks_to_chunks``)
        2. Build ``DevelopmentPlan`` → ``DevelopmentPhase.run()``
        3. ``DevelopmentResult`` → output dict + ``context["generation_results"]``
           (``_map_development_result``)
    """

    def __init__(
        self,
        handler_config: Optional[HandlerConfig] = None,
        code_generator: Optional[CodeGenerator] = None,  # deprecated, ignored
        enriched_seed_path: Optional[Path] = None,
        project_root: Optional[Path] = None,
    ) -> None:
        if code_generator is not None:
            warnings.warn(
                "ImplementPhaseHandler: 'code_generator' parameter is deprecated "
                "and ignored. The artisan pipeline now uses DevelopmentPhase with "
                "'drafter_spec' from HandlerConfig instead. This parameter will "
                "be removed in a future release.",
                DeprecationWarning,
                stacklevel=2,
            )
        self.config = handler_config or HandlerConfig()
        self._enriched_seed_path = enriched_seed_path
        self._project_root = project_root

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_environment(task: SeedTask) -> list[dict[str, Any]]:
        """Check environment readiness for a task.

        Returns list of environment issues (fail/warn checks).
        """
        return [
            c for c in task.environment_checks
            if c.get("status") in ("fail", "warn")
        ]

    @staticmethod
    def _validate_multi_file_tasks(tasks: list[SeedTask]) -> None:
        """Pre-IMPLEMENT validation: warn about risky multi-file tasks.

        Logs structured warnings for tasks that are likely to encounter
        multi-file split failures so operators can monitor and intervene
        early. This is a defense-in-depth layer — it doesn't block
        execution but makes risk visible.

        Checks:
        1. Multi-file tasks (>1 target) — higher split failure risk.
        2. Multi-file tasks with ``__init__.py`` — often confuses LLMs.
        3. Tasks whose prompt_constraints mention "shared module" — known
           shared files that the LLM may skip.
        4. Cross-task file overlap — files targeted by multiple tasks.
        """
        multi_file_tasks = [t for t in tasks if len(t.target_files) > 1]
        if not multi_file_tasks:
            return

        # Only build the file→tasks index when there are multi-file tasks
        # to check (avoids iterating all tasks when none are multi-file).
        file_to_tasks: dict[str, list[str]] = {}
        for task in tasks:
            for tf in task.target_files:
                file_to_tasks.setdefault(tf, []).append(task.task_id)

        logger.info(
            "IMPLEMENT pre-validation: %d of %d tasks are multi-file",
            len(multi_file_tasks),
            len(tasks),
        )

        for task in multi_file_tasks:
            risk_flags: list[str] = []

            # __init__.py is often omitted by LLMs
            init_files = [f for f in task.target_files if f.endswith("__init__.py")]
            if init_files:
                risk_flags.append(f"includes __init__.py ({', '.join(init_files)})")

            # Shared module hint present
            shared_hints = [
                c for c in task.prompt_constraints
                if "shared module" in c.lower() or "shared file" in c.lower()
            ]
            if shared_hints:
                risk_flags.append("contains shared-module constraint")

            # Files targeted by other tasks too
            overlapping = [
                f for f in task.target_files
                if len(file_to_tasks.get(f, [])) > 1
            ]
            if overlapping:
                risk_flags.append(
                    f"overlapping files: {', '.join(overlapping)}"
                )

            # File scope from seed — contract-level classification
            if task.file_scope:
                non_primary = {
                    f: s for f, s in task.file_scope.items()
                    if s != "primary"
                }
                if non_primary:
                    risk_flags.append(
                        f"file_scope: {non_primary} (Gate 2c will pre-stub)"
                    )

            if risk_flags:
                logger.warning(
                    "IMPLEMENT pre-validation: task %s (%d files) has elevated "
                    "multi-file split risk — %s. Stub generation will activate "
                    "if LLM omits files.",
                    task.task_id,
                    len(task.target_files),
                    "; ".join(risk_flags),
                )
            else:
                logger.info(
                    "IMPLEMENT pre-validation: task %s has %d target files",
                    task.task_id,
                    len(task.target_files),
                )

    def _run_micro_prime_prepass(
        self, context: dict[str, Any], project_root: Path,
    ) -> None:
        """Run Micro Prime pre-pass to fill TRIVIAL/SIMPLE element bodies.

        Reads the forward manifest and skeleton files from context, runs the
        Micro Prime engine, and stores results in context for downstream use.
        """
        try:
            from startd8.micro_prime.artisan_adapter import MicroPrimePrePass
            from startd8.micro_prime.models import MicroPrimeConfig
        except ImportError:
            logger.warning(
                "IMPLEMENT: micro_prime package not available, skipping pre-pass",
            )
            return

        manifest_path = context.get("manifest_path")
        if not manifest_path:
            logger.info("IMPLEMENT: no manifest_path in context, skipping Micro Prime pre-pass")
            return

        manifest = context.get("manifest")
        skeletons = context.get("skeletons", {})

        if not manifest or not skeletons:
            logger.info("IMPLEMENT: no manifest/skeletons in context, skipping Micro Prime pre-pass")
            return

        config = MicroPrimeConfig()
        pre_pass = MicroPrimePrePass(
            config=config,
            manifest=manifest,
            skeletons=skeletons,
            project_root=project_root,
        )
        result = pre_pass.run()

        # Store results in context for downstream phases
        context["micro_prime_result"] = {
            "filled_skeletons": result.filled_skeletons,
            "escalated_elements": result.escalated_elements,
            "metrics": result.metrics,
            "element_metrics": result.element_metrics,
            "elements_filled": result.elements_filled,
        }
        # Update skeletons with filled versions
        if result.filled_skeletons:
            context["skeletons"] = result.filled_skeletons

        logger.info(
            "IMPLEMENT: Micro Prime pre-pass completed — %d local, %d escalated",
            result.local_success_count,
            result.escalated_count,
        )

    @staticmethod
    def _validate_generation_completeness(
        tasks: list[SeedTask],
        generation_results: dict[str, "GenerationResult"],
        project_root: Path,
        downstream_map: dict[str, list[str]] | None = None,
    ) -> list[dict[str, Any]]:
        """Gate 3: post-IMPLEMENT validation of multi-file split completeness.

        Per the Export Pipeline Analysis Guide's defense-in-depth Principle 1
        (validate at every boundary): verifies that multi-file tasks actually
        produced all their target files on disk.

        Returns a list of validation findings (one per multi-file task that
        has issues).  Empty list means all multi-file tasks are complete.

        This is the last gate before output is accepted — it catches cases
        where Gate 2 warnings were present but the drafter still omitted
        files despite all mitigation layers.

        Enhancement (defense-in-depth): ``downstream_map`` from Gate 2c
        allows distinguishing **downstream stubs** (expected, pre-created)
        from **generation failure stubs** (unexpected, needs attention).
        """
        findings: list[dict[str, Any]] = []
        downstream_map = downstream_map or {}

        for task in tasks:
            if len(task.target_files) <= 1:
                continue

            gr = generation_results.get(task.task_id)
            if gr is None:
                continue  # Task wasn't processed (dep-blocked, skipped, etc.)

            task_downstream = set(downstream_map.get(task.task_id, []))

            # Check which target files actually exist on disk
            generated_paths = {str(p) for p in (gr.generated_files or [])}
            missing_on_disk: list[str] = []
            stubbed: list[str] = []
            downstream_stubbed: list[str] = []

            for tf in task.target_files:
                full_path = project_root / tf
                if not full_path.exists():
                    if tf in task_downstream:
                        # Downstream file not on disk — unexpected since
                        # Gate 2c should have pre-created it.
                        missing_on_disk.append(tf)
                    else:
                        missing_on_disk.append(tf)
                elif full_path.exists():
                    # Check for stub sentinel (auto-generated placeholder)
                    try:
                        content = full_path.read_text(encoding="utf-8")
                        is_stub = (
                            "STUB_PLACEHOLDER" in content
                            or "# AUTO-STUB" in content
                            or "# STARTD8_AUTO_STUB" in content
                            or "downstream — will be implemented by later tasks" in content
                        )
                        if is_stub:
                            if tf in task_downstream:
                                downstream_stubbed.append(tf)
                            else:
                                stubbed.append(tf)
                    except Exception:
                        logger.debug(
                            "IMPLEMENT Gate 3: stub sentinel check failed for %s in task %s",
                            tf, task.task_id, exc_info=True,
                        )

            # Only report as issues if there are true failures (not downstream)
            has_real_issues = bool(missing_on_disk or stubbed)

            if has_real_issues or downstream_stubbed:
                finding: dict[str, Any] = {
                    "task_id": task.task_id,
                    "target_file_count": len(task.target_files),
                    "target_files": task.target_files,
                    "missing_on_disk": missing_on_disk,
                    "stubbed_files": stubbed,
                    "downstream_stubbed": downstream_stubbed,
                    "generation_success": gr.success,
                    "has_real_issues": has_real_issues,
                }
                findings.append(finding)

                if has_real_issues:
                    level = "ERROR" if missing_on_disk else "WARN"
                    logger.warning(
                        "Gate 3 [%s]: task %s multi-file split incomplete — "
                        "%d/%d files verified. Missing: %s. Stubbed: %s",
                        level,
                        task.task_id,
                        len(task.target_files) - len(missing_on_disk) - len(stubbed),
                        len(task.target_files),
                        missing_on_disk or "(none)",
                        stubbed or "(none)",
                    )
                if downstream_stubbed:
                    logger.info(
                        "Gate 3 [OK/downstream]: task %s — %d file(s) are "
                        "expected downstream stubs (pre-created by Gate 2c): %s",
                        task.task_id,
                        len(downstream_stubbed),
                        downstream_stubbed,
                    )
            else:
                logger.info(
                    "Gate 3 [OK]: task %s — all %d target files verified on disk",
                    task.task_id,
                    len(task.target_files),
                )

        return findings

    @staticmethod
    def _validate_generation_content(
        tasks: list[SeedTask],
        generation_results: dict[str, "GenerationResult"],
        project_root: Path,
        service_metadata: dict[str, Any] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Gate 3b: post-IMPLEMENT semantic content validation.

        Runs all 5 self-consistency validators (AR-143 through AR-147)
        against generated files to catch production-blocking defects
        before TEST/REVIEW/FINALIZE.

        Returns:
            Dict mapping task_id to a list of issue dicts.
            Empty dict means all tasks are clean.
        """
        from startd8.contractors.artisan_phases.self_consistency import (
            validate_placeholder_detection,
            validate_import_dependency,
            validate_intra_project_imports,
            validate_proto_field_references,
            validate_protocol_fidelity,
            validate_dockerfile_coherence,
            validate_function_call_completeness,
            validate_dockerfile_runtime_deps,
        )
        from startd8.workflows.builtin.preflight_rules.rules_validators import (
            _StubEnrichment,
        )

        enrichment = _StubEnrichment(cwd=str(project_root))
        all_findings: dict[str, list[dict[str, Any]]] = {}

        for task in tasks:
            gr = generation_results.get(task.task_id)
            if gr is None or not gr.success:
                continue

            task_issues: list[dict[str, Any]] = []
            for rel_path in task.target_files:
                full_path = project_root / rel_path
                if not full_path.exists():
                    continue
                try:
                    code = full_path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue

                # AR-146: Placeholder detection (all files)
                task_issues.extend(validate_placeholder_detection(code, enrichment))

                # AR-143, AR-145, AR-150: Python-specific validators
                if rel_path.endswith(".py"):
                    task_issues.extend(validate_import_dependency(code, enrichment))
                    task_issues.extend(validate_intra_project_imports(code, enrichment))
                    task_issues.extend(validate_proto_field_references(code, enrichment))

                # AR-144: Protocol fidelity (with service_metadata)
                task_issues.extend(
                    validate_protocol_fidelity(code, rel_path, service_metadata)
                )

                # AR-147: Dockerfile coherence
                task_issues.extend(
                    validate_dockerfile_coherence(code, rel_path, service_metadata)
                )

                # AR-148: Function call completeness
                task_issues.extend(
                    validate_function_call_completeness(code, rel_path, service_metadata)
                )

                # AR-149: Dockerfile runtime dependencies
                task_issues.extend(
                    validate_dockerfile_runtime_deps(code, rel_path, service_metadata)
                )

            if task_issues:
                all_findings[task.task_id] = task_issues

        return all_findings

    @staticmethod
    def _validate_truncation(
        tasks: list[SeedTask],
        generation_results: dict[str, "GenerationResult"],
        project_root: Path,
        existing_file_sizes: dict[str, dict[str, int]] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Gate 4: post-IMPLEMENT truncation detection on generated files.

        For each successfully generated task, reads every generated file from
        disk and runs four checks:

        1. ``detect_truncation()`` with ``code_mode=None`` (auto-detect).
        2. ``compile()`` syntax validation for Python files.
        3. Line-count ratio against ``task.estimated_loc`` (flag if < 30%).
        4. Size regression vs existing file (PCA-603): flag when generated
           file is < ``_SIZE_REGRESSION_THRESHOLD`` (default 70%) of existing
           file, for files > ``_SIZE_REGRESSION_MIN_LINES`` lines.

        Args:
            existing_file_sizes: Optional mapping of task_id → {path: line_count}
                for existing files on disk. Used for Check 4 size regression.

        Returns:
            Dict mapping task_id to a flag dict with keys:
            ``detected`` (bool), ``max_confidence`` (float),
            ``source`` (str: syntax|heuristic_high|ratio|size_regression|heuristic),
            ``indicators`` (list[str]), ``file_results`` (list[dict]),
            ``syntax_errors`` (list[str]), ``total_lines`` (int),
            ``estimated_loc`` (int|None), and optionally ``ratio`` (float)
            or ``size_regression_ratio`` (float).
            Only tasks with at least one positive signal are included;
            clean tasks are omitted (empty dict for a fully clean run).
        """
        from startd8.truncation_detection import (
            CONFIDENCE_HIGH,
            detect_truncation,
            log_truncation_result,
        )

        # OTel span for event emission.  When OTel is installed but no
        # tracer is configured, get_current_span() returns a
        # NonRecordingSpan whose add_event() is a safe no-op.
        _span = None
        try:
            from opentelemetry import trace as _trace
            _span = _trace.get_current_span()
        except ImportError:
            logger.debug("Optional import not available", exc_info=True)

        flags: dict[str, dict[str, Any]] = {}

        for task in tasks:
            gr = generation_results.get(task.task_id)
            if gr is None or not gr.success:
                continue  # skip failed / unprocessed tasks

            file_results: list[dict[str, Any]] = []
            syntax_errors: list[str] = []
            max_confidence = 0.0
            any_detected = False
            total_lines = 0

            for fpath in (gr.generated_files or []):
                fp = Path(fpath)
                if not fp.exists():
                    continue
                # Respect existing 50 MB ceiling
                try:
                    fsize = fp.stat().st_size
                except OSError as exc:
                    logger.debug("Gate 4: skipping %s — stat failed: %s", fp, exc)
                    continue
                if fsize > _MAX_GEN_FILE_HASH_BYTES:
                    continue

                try:
                    content = fp.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError) as exc:
                    logger.debug("Gate 4: skipping unreadable file %s: %s", fp, exc)
                    continue

                line_count = len(content.splitlines())
                total_lines += line_count

                # --- Check 1: heuristic truncation detection ---
                tr = detect_truncation(content, code_mode=None)
                fr: dict[str, Any] = {
                    "file": str(fp),
                    "lines": line_count,
                    "truncation_detected": tr.is_truncated,
                    "truncation_confidence": tr.confidence,
                    "truncation_indicators": tr.indicators,
                }
                if tr.is_truncated:
                    any_detected = True
                    max_confidence = max(max_confidence, tr.confidence)
                    log_truncation_result(
                        tr,
                        source_file=str(fp),
                        feature_name=task.task_id,
                        step_name="IMPLEMENT.gate4",
                    )

                # --- Check 2: syntax validation (Python only) ---
                if fp.suffix == ".py":
                    try:
                        compile(content, str(fp), "exec")
                        fr["syntax_valid"] = True
                    except (SyntaxError, ValueError) as se:
                        fr["syntax_valid"] = False
                        msg = getattr(se, "msg", str(se))
                        lineno = getattr(se, "lineno", None)
                        fr["syntax_error"] = (
                            f"{msg} (line {lineno})" if lineno else msg
                        )
                        syntax_errors.append(str(fp))
                        any_detected = True
                        if _span:
                            _span.add_event(
                                "syntax.validation_failed",
                                attributes={
                                    "task_id": task.task_id,
                                    "file": str(fp),
                                    "error": fr["syntax_error"],
                                },
                            )

                file_results.append(fr)

            # --- Check 3: line-count ratio ---
            ratio_flag = False
            if task.estimated_loc and task.estimated_loc > 0 and total_lines > 0:
                ratio = total_lines / task.estimated_loc
                if ratio < 0.3:
                    ratio_flag = True
                    any_detected = True

            # --- Check 4: Size regression vs existing file (PCA-603) ---
            size_regression_flag = False
            size_regression_details: list[dict[str, Any]] = []
            if existing_file_sizes:
                task_sizes = existing_file_sizes.get(task.task_id, {})
                # Build a map of generated file paths → line counts from file_results
                gen_line_counts: dict[str, int] = {}
                for fr_item in file_results:
                    gen_line_counts[fr_item["file"]] = fr_item.get("lines", 0)

                for existing_path, existing_lines in task_sizes.items():
                    if existing_lines <= _SIZE_REGRESSION_MIN_LINES:
                        continue
                    # Find matching generated file — match by relative path suffix
                    gen_lines = 0
                    for gen_path, gen_lc in gen_line_counts.items():
                        if gen_path.endswith(existing_path) or str(Path(gen_path)) == str(Path(existing_path)):
                            gen_lines = gen_lc
                            break
                    if gen_lines <= 0:
                        continue  # File not generated — skip (handled by Gate 3)
                    if existing_lines > 0 and gen_lines / existing_lines < _SIZE_REGRESSION_THRESHOLD:
                        size_regression_flag = True
                        any_detected = True
                        size_regression_details.append({
                            "file": existing_path,
                            "existing_lines": existing_lines,
                            "generated_lines": gen_lines,
                            "ratio": gen_lines / existing_lines,
                        })
                        logger.warning(
                            "Gate 4 [size_regression]: task %s file %s — "
                            "%d generated / %d existing (%.0f%% < %.0f%% threshold)",
                            task.task_id, existing_path,
                            gen_lines, existing_lines,
                            (gen_lines / existing_lines) * 100,
                            _SIZE_REGRESSION_THRESHOLD * 100,
                        )

            if not any_detected:
                continue

            # Determine primary source for the flag
            if syntax_errors:
                source = "syntax"
            elif max_confidence >= CONFIDENCE_HIGH:
                source = "heuristic_high"
            elif size_regression_flag:
                source = "size_regression"
            elif ratio_flag:
                source = "ratio"
            else:
                source = "heuristic"

            task_flag: dict[str, Any] = {
                "detected": True,
                "max_confidence": max_confidence,
                "source": source,
                "indicators": [],
                "file_results": file_results,
                "syntax_errors": syntax_errors,
                "total_lines": total_lines,
                "estimated_loc": task.estimated_loc,
            }
            if ratio_flag:
                task_flag["ratio"] = (
                    total_lines / task.estimated_loc
                    if task.estimated_loc and task.estimated_loc > 0
                    else None
                )
            if size_regression_flag:
                task_flag["size_regression"] = size_regression_details
            # AR-816: Mark tasks that should be blocked at INTEGRATE
            from startd8.truncation_detection import (
                CONFIDENCE_TRUNCATION_BLOCKED,
                MIN_LINES_TRUNCATION_BLOCKING,
            )
            # Compute blocking confidence from files large enough to be meaningful.
            # Tiny files (e.g., 1-line __init__.py) produce false-positive prose
            # heuristics that shouldn't prevent integration.
            _blocking_confidence = max(
                (
                    fr["truncation_confidence"]
                    for fr in file_results
                    if fr["lines"] >= MIN_LINES_TRUNCATION_BLOCKING
                    and fr.get("truncation_detected", False)
                ),
                default=0.0,
            )
            task_flag["truncation_blocked"] = (
                task_flag["detected"]
                and _blocking_confidence >= CONFIDENCE_TRUNCATION_BLOCKED
            )
            # Aggregate unique indicators
            for fr in file_results:
                task_flag["indicators"].extend(fr.get("truncation_indicators", []))
            task_flag["indicators"] = sorted(set(task_flag["indicators"]))

            flags[task.task_id] = task_flag

            if _span:
                _span.add_event(
                    "truncation.detected",
                    attributes={
                        "task_id": task.task_id,
                        "source": source,
                        "max_confidence": max_confidence,
                        "syntax_errors": len(syntax_errors),
                        "total_lines": total_lines,
                        "estimated_loc": task.estimated_loc or 0,
                    },
                )

        return flags

    @staticmethod
    def _ensure_test_scaffolding_for_artifact_tasks(
        tasks: list[SeedTask],
        project_root: Path,
    ) -> None:
        """Ensure test scaffolding exists for artifact generator tasks (Item 12).

        For tasks with artifact_types_addressed, derive the expected test path
        from the first target file and create minimal scaffolding if missing.
        Uses convention: target path/to/foo.py or path/to/foo.yaml → tests/test_foo.py.
        """
        for task in tasks:
            if not task.artifact_types_addressed or not task.target_files:
                continue

            tests_dir = project_root / "tests"
            target = Path(task.target_files[0])
            stem = target.stem.replace("-", "_")
            if not stem:
                continue
            test_path = tests_dir / f"test_{stem}.py"

            if test_path.exists():
                continue

            tests_dir.mkdir(parents=True, exist_ok=True)

            # Minimal scaffolding: test class skeleton
            artifact_label = "_".join(
                t.replace("-", "_") for t in task.artifact_types_addressed[:2]
            )
            class_name = "".join(
                p.capitalize() for p in stem.split("_") if p
            ) or "Artifact"
            content = f'''"""Tests for {artifact_label} — scaffold-first (Item 12)."""

import pytest


class Test{class_name}:
    """Test scaffold for {artifact_label} — implement before generation."""
    pass
'''
            test_path.write_text(content, encoding="utf-8")
            logger.info(
                "IMPLEMENT: scaffolded test file for artifact task %s: %s",
                task.task_id,
                test_path.relative_to(project_root),
            )

    @staticmethod
    def _reconcile_design_downstream(
        tasks: list[SeedTask],
        design_results: dict[str, Any],
        project_root: Path,
    ) -> dict[str, list[str]]:
        """Gate 2c: Reconcile design doc downstream designations with target_files.

        Uses a two-layer detection strategy (defense-in-depth Principle 1):

        **Layer 1 — Contract-level (seed ``_file_scope``):**
        Plan ingestion already classified files as "primary", "shared", or
        "stub" using ContextCore export's ``file_ownership`` and cross-feature
        analysis.  When ``_file_scope`` is present, we trust it as the
        authoritative source — it represents the contract answer to
        "Is the contract complete?" (Principle 6, Question 1).

        **Layer 2 — Runtime fallback (design doc parsing):**
        When ``_file_scope`` is absent (older seeds, manual seeds), falls
        back to scanning the design doc for downstream signals (e.g.
        "F-002+", "implemented by later tasks").

        For downstream/stub files:
        1. **Pre-creates a stub** on disk so downstream tasks have a valid
           import target immediately.
        2. **Returns a mapping** task_id → [downstream_files] so callers can
           shrink the drafter's target list and annotate metadata.

        Args:
            tasks: Parsed seed tasks from the PLAN phase.
            design_results: Per-task design results from the DESIGN phase.
            project_root: Root of the project for writing pre-stubs.

        Returns:
            Dict mapping task_id → list of downstream file paths that were
            pre-stubbed. Empty dict if no downstream files found.
        """
        from startd8.contractors.generators.lead_contractor import (
            _detect_downstream_files,
        )
        from startd8.utils.code_extraction import STUB_SENTINEL

        downstream_map: dict[str, list[str]] = {}

        for task in tasks:
            if len(task.target_files) < 2:
                continue

            downstream: list[str] = []

            # ── Layer 1: contract-level file scope from seed ──────────
            # This is the authoritative source when available.
            if task.file_scope:
                downstream = [
                    f for f in task.target_files
                    if task.file_scope.get(f) in ("stub", "shared")
                ]
                if downstream:
                    logger.info(
                        "Gate 2c [contract]: task %s has %d non-primary files "
                        "from seed _file_scope: %s",
                        task.task_id, len(downstream),
                        {f: task.file_scope[f] for f in downstream},
                    )

            # ── Layer 2: runtime fallback — parse design doc ──────────
            # Only fall through when file_scope is absent (older/manual seeds).
            # If file_scope exists, it's authoritative even if all files are
            # "primary" — that means the contract says to implement everything.
            if not downstream and not task.file_scope:
                task_design = design_results.get(task.task_id, {})
                if task_design.get("status") in ("designed", "adopted", "refined"):
                    design_doc = task_design.get("design_document", "")
                    if design_doc:
                        downstream = _detect_downstream_files(
                            task.target_files, design_doc,
                        )
                        if downstream:
                            logger.info(
                                "Gate 2c [runtime]: task %s has %d downstream "
                                "files from design doc parsing: %s",
                                task.task_id, len(downstream), downstream,
                            )

            if not downstream:
                continue

            # Safety: never remove ALL files — at least one must remain for
            # the drafter to implement.
            if len(downstream) >= len(task.target_files):
                logger.warning(
                    "Gate 2c: all %d target files for %s flagged as downstream "
                    "— keeping all to avoid empty task. Files: %s",
                    len(task.target_files), task.task_id, downstream,
                )
                continue

            # Pre-create stubs on disk for downstream files
            for fpath in downstream:
                abs_path = project_root / fpath
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                if not abs_path.exists():
                    # Generate a meaningful stub based on file type
                    module_name = abs_path.stem
                    if module_name == "__init__":
                        stub_content = (
                            f'"""{abs_path.parent.name} package."""\n'
                            f"{STUB_SENTINEL}  # downstream — will be implemented by later tasks\n"
                        )
                    else:
                        stub_content = (
                            f'"""{module_name} module — stub for downstream implementation."""\n'
                            f"{STUB_SENTINEL}  # downstream — will be implemented by later tasks\n"
                        )
                    abs_path.write_text(stub_content, encoding="utf-8")
                    logger.info(
                        "Gate 2c: pre-stubbed downstream file %s for task %s",
                        fpath, task.task_id,
                    )

            downstream_map[task.task_id] = downstream
            logger.info(
                "Gate 2c: task %s has %d downstream files (pre-stubbed): %s. "
                "These will be excluded from drafter targets.",
                task.task_id, len(downstream), downstream,
            )

        return downstream_map

    @staticmethod
    def _classify_edit_mode(
        task: SeedTask,
        scaffold: dict[str, Any],
        design_mode_summary: dict[str, str],
        design_mode_evidence: dict[str, dict[str, Any]] | None = None,
        manifest_registry: Any = None,
    ) -> EditModeClassification:
        """Classify each target file as 'create' or 'edit' using upstream signals.

        Consumes 6+ signals computed but previously unconsumed by IMPLEMENT:
          - scaffold["existing_target_files"] (Tier 1, weight 2)
          - task.existing_content_hash (Tier 1, weight 2)
          - manifest_registry.public_element_count (Tier 1, weight 2) [REQ-EMM-001]
          - manifest_registry.fqn_exists for api_signatures (Tier 1, weight 2) [REQ-EMM-002]
          - design_mode_summary[task_id] (Tier 2, weight 1; elevated to
            weight 2 when design_mode_evidence has >=2 corroborating signals)
          - scaffold["staleness_classification"] (Tier 2, weight 1)
          - task.file_scope (Tier 2, weight 1)

        When manifest_registry is None, produces identical results to the
        original 5-signal system (REQ-EMM-003).

        Args:
            design_mode_evidence: Gap 4 enrichment — when provided with >=2
                evidence signals, the design_mode_summary weight is elevated
                from Tier 2 (1) to Tier 1 (2), reflecting higher confidence.
            manifest_registry: Optional ManifestRegistry instance providing
                AST-based code intelligence (fqn_exists, public_element_count).

        Returns EditModeClassification with typed fields for mode, per_file,
        confidence, and signal_conflicts.
        """
        existing_targets = set(scaffold.get("existing_target_files", []))
        staleness_map = scaffold.get("staleness_classification", {})
        design_mode = design_mode_summary.get(task.task_id, "")

        # Gap 4: Determine design mode weight based on evidence strength
        _evidence = (design_mode_evidence or {}).get(task.task_id, {})
        _evidence_signals = _evidence.get("evidence", [])
        # Elevate from Tier 2 (weight 1) to Tier 1 (weight 2) when DESIGN
        # has >=2 corroborating signals (e.g. scaffold + doc annotation)
        _design_mode_weight = 2 if len(_evidence_signals) >= 2 else 1

        per_file: dict[str, PerFileMode] = {}
        signal_conflicts: list[str] = []

        for fpath in task.target_files:
            # Collect per-file signals with tier weights
            edit_weight = 0
            create_weight = 0
            file_signals_edit: list[str] = []
            file_signals_create: list[str] = []

            # Tier 1 (weight 2): existing_content_hash — non-None means file
            # physically existed at preflight time
            has_hash = task.existing_content_hash is not None

            # Tier 1 (weight 2): scaffold.existing_target_files
            in_existing = fpath in existing_targets

            # I-2: Only apply hash signal to files confirmed on disk
            if has_hash and in_existing:
                edit_weight += 2
                file_signals_edit.append("existing_content_hash")
            if in_existing:
                edit_weight += 2
                file_signals_edit.append("scaffold.existing_target_files")

            # Tier 2 (weight 1, elevated to 2 with evidence): design_mode_summary
            if design_mode == "update":
                edit_weight += _design_mode_weight
                file_signals_edit.append(
                    f"design_mode_summary=update(w={_design_mode_weight})"
                )
            elif design_mode == "create":
                create_weight += _design_mode_weight
                file_signals_create.append(
                    f"design_mode_summary=create(w={_design_mode_weight})"
                )

            # Tier 2 (weight 1): staleness_classification
            staleness = staleness_map.get(fpath, "")
            if staleness in ("fresh", "stale"):
                edit_weight += 1
                file_signals_edit.append(f"staleness={staleness}")

            # Tier 2 (weight 1): file_scope
            scope = (task.file_scope or {}).get(fpath, "")
            if scope == "primary":
                edit_weight += 1
                file_signals_edit.append("file_scope=primary")

            # Tier 1 (weight 2): manifest.public_element_count (REQ-EMM-001)
            _manifest_elem_count = 0
            if manifest_registry is not None:
                try:
                    _manifest_elem_count = manifest_registry.public_element_count(fpath)
                    if _manifest_elem_count > 0:
                        edit_weight += 2
                        file_signals_edit.append(
                            f"manifest.public_element_count={_manifest_elem_count}"
                        )
                        logger.info(
                            "Edit-mode manifest signal: %s has %d public elements",
                            fpath, _manifest_elem_count,
                        )
                except (AttributeError, TypeError, OSError):
                    logger.debug("Graceful degradation: file summary extraction failed", exc_info=True)

            # Tier 1 (weight 2): manifest.fqn_exists for api_signatures (REQ-EMM-002, PI-3)
            if manifest_registry is not None and task.api_signatures:
                try:
                    _matched_fqns = [
                        s for s in task.api_signatures
                        if manifest_registry.fqn_exists(s)
                    ]
                    if _matched_fqns:
                        edit_weight += 2
                        file_signals_edit.append(
                            f"manifest.fqn_exists={len(_matched_fqns)}/{len(task.api_signatures)}"
                        )
                        logger.info(
                            "Edit-mode manifest signal: %d/%d FQNs confirmed for task %s: %s",
                            len(_matched_fqns), len(task.api_signatures),
                            task.task_id, _matched_fqns[:3],
                        )
                except (AttributeError, TypeError):
                    logger.debug("Graceful degradation: manifest query failed", exc_info=True)

            # Classify this file
            if edit_weight >= 1:
                file_mode = "edit"
            else:
                file_mode = "create"

            # Detect Tier 1 vs Tier 2 conflicts
            tier1_edit = has_hash or in_existing or _manifest_elem_count > 0
            tier2_create = design_mode == "create"
            if tier1_edit and tier2_create:
                conflict = (
                    f"Signal conflict for file {fpath}: Tier 1 signals "
                    f"{file_signals_edit} indicate 'edit' but Tier 2 signals "
                    f"{file_signals_create} indicate 'create'. "
                    f"Tier 1 precedence applied."
                )
                signal_conflicts.append(conflict)
                logger.warning(conflict)

            per_file[fpath] = PerFileMode(
                mode=file_mode,
                staleness=staleness,
                has_hash=has_hash,
                edit_weight=edit_weight,
                manifest_element_count=_manifest_elem_count,
            )

        # Task-level aggregation: "edit" if ANY per_file is "edit"
        any_edit = any(pf.mode == "edit" for pf in per_file.values())
        task_mode = "edit" if any_edit else "create"

        # Confidence from max edit weight across files
        max_weight = max(
            (pf.edit_weight for pf in per_file.values()), default=0,
        )
        if max_weight >= 3:
            confidence = "high"
        elif max_weight >= 1:
            confidence = "medium"
        else:
            confidence = "low"

        return EditModeClassification(
            mode=task_mode,
            per_file=per_file,
            confidence=confidence,
            signal_conflicts=signal_conflicts,
        )

    @staticmethod
    def _tasks_to_chunks(
        tasks: list[SeedTask],
        max_retries: int = 2,
        design_results: dict[str, Any] | None = None,
        calibration_map: dict[str, dict[str, Any]] | None = None,
        downstream_map: dict[str, list[str]] | None = None,
        staleness_classification: dict[str, str] | None = None,
        parameter_sources: dict[str, Any] | None = None,
        semantic_conventions: dict[str, Any] | None = None,
        # PCA-300/301/400: project-level context for IMPLEMENT prompts
        architectural_context: dict[str, Any] | None = None,
        plan_goals: list[str] | None = None,
        plan_context: str | None = None,
        service_metadata: dict[str, Any] | None = None,
        # PCA-401/403/404: additional IMPLEMENT enrichment
        calibration_hints: dict[str, Any] | None = None,
        prior_impl_summaries: list[dict[str, Any]] | None = None,
        # PCA-501: project identity for edit-first behavior
        project_name: str | None = None,
        project_root_path: str | None = None,
        preflight_safe_loc_limit: int = 800,
        preflight_safe_token_limit: int = 64000,
        # PCA-600: edit mode classification from upstream signals
        edit_mode_map: dict[str, EditModeClassification] | None = None,
        # AR-822: module inventory from SCAFFOLD for import grounding
        module_inventory: list[str] | None = None,
        # Scaffold output for skeleton file detection
        scaffold_output: dict[str, Any] | None = None,
        # Micro Prime pre-pass results for local-first skip / partial injection
        micro_prime_result: dict[str, Any] | None = None,
        **kwargs: Any,  # Allow forward_manifest via kwargs to avoid massive signature change
    ) -> tuple[list[Any], list[dict[str, Any]]]:
        """Convert SeedTasks to DevelopmentChunks, pre-filtering env-blocked.

        Args:
            tasks: Parsed seed tasks from the PLAN phase.
            max_retries: Max retry count for each chunk.
            design_results: Per-task design results from the DESIGN phase.
                Maps task_id → dict with 'design_document' key containing the
                raw design document text to inject into implementation prompts.
            calibration_map: Per-task calibration (design_calibration) with
                optional implement_max_output_tokens for per-task token caps.
            downstream_map: Gate 2c output — maps task_id → list of files
                that were pre-stubbed as downstream.  These are excluded
                from the drafter's ``file_targets`` and annotated in
                chunk metadata so retry/review layers can distinguish
                expected stubs from generation failures.

        Returns:
            Tuple of (chunks, skipped_reports). ``skipped_reports`` contains
            task report dicts for env-blocked tasks.
        """
        from startd8.contractors.artisan_phases.development import DevelopmentChunk

        chunks: list[DevelopmentChunk] = []
        skipped: list[dict[str, Any]] = []
        design_results = design_results or {}
        downstream_map = downstream_map or {}
        staleness_classification = staleness_classification or {}
        active_task_ids = {t.task_id for t in tasks}

        env_blocked_ids: set[str] = set()
        for task in tasks:
            _log_task_boundary_start(task, phase="implement")
            env_fails = [
                c for c in task.environment_checks
                if c.get("status") == "fail"
            ]
            if env_fails:
                env_blocked_ids.add(task.task_id)
                logger.warning(
                    "IMPLEMENT: skipping task %s (%s) — env_blocked (%d failing check(s))",
                    task.task_id,
                    task.title,
                    len(env_fails),
                )
                skipped.append({
                    "task_id": task.task_id,
                    "title": task.title,
                    "status": "env_blocked",
                    "complexity_tier": "tier_2",
                    "environment_issues": [
                        c for c in task.environment_checks
                        if c.get("status") in ("fail", "warn")
                    ],
                })
                _log_task_boundary_complete(
                    task.task_id,
                    status="env_blocked",
                    phase="implement",
                )

        for task in tasks:
            if task.task_id in env_blocked_ids:
                continue

            blocked_deps = [d for d in task.depends_on if d in env_blocked_ids]
            if blocked_deps:
                logger.warning(
                    "IMPLEMENT: skipping task %s (%s) — dep_blocked_env (blocked by: %s)",
                    task.task_id,
                    task.title,
                    ", ".join(blocked_deps),
                )
                skipped.append({
                    "task_id": task.task_id,
                    "title": task.title,
                    "status": "dep_blocked_env",
                    "complexity_tier": "tier_2",
                    "blocked_dependencies": blocked_deps,
                    "depends_on": task.depends_on,
                })
                _log_task_boundary_complete(
                    task.task_id,
                    status="dep_blocked_env",
                    phase="implement",
                )
                continue

            task_design = design_results.get(task.task_id, {})
            if task_design.get("status") == "design_failed":
                fail_reason = (
                    task_design.get("quality_failure_reason")
                    or task_design.get("error")
                    or "design_failed"
                )
                logger.warning(
                    "IMPLEMENT: skipping task %s (%s) — design_blocked (%s)",
                    task.task_id,
                    task.title,
                    fail_reason,
                )
                skipped.append({
                    "task_id": task.task_id,
                    "title": task.title,
                    "status": "design_blocked",
                    "complexity_tier": "tier_2",
                    "reason": str(fail_reason),
                })
                _log_task_boundary_complete(
                    task.task_id,
                    status="design_blocked",
                    phase="implement",
                )
                continue

            # Extract design document from DESIGN phase results (if available).
            # "adopted" status indicates reuse from a prior run (dress-rehearsal).
            design_doc_text = None
            if task_design.get("status") in ("designed", "adopted", "refined"):
                design_doc_text = task_design.get("design_document")

            # ── Layer 1: DESIGN→IMPLEMENT boundary validation (DP-2) ────
            # Defense-in-depth: per-task line-count pre-check before the
            # phase-level contract exit validator (BP-3).  Metric aligned
            # with artisan-pipeline.contract.yaml: line_count >= 50.
            # Pre-compute design doc metrics once (used for DP-2 boundary
            # check, scope logging, B-5 framing, and post-gen validation).
            _design_lines = 0
            _design_sections = 0
            if task_design.get("status") in ("designed", "adopted", "refined"):
                if design_doc_text:
                    for _dl in design_doc_text.strip().splitlines():
                        _design_lines += 1
                        if _dl.strip().startswith("##"):
                            _design_sections += 1
                if not design_doc_text or _design_lines < 10:
                    logger.warning(
                        "DESIGN→IMPLEMENT boundary: task %s has status '%s' but "
                        "design_document is empty/trivial (%d lines) — falling back "
                        "to task description only (DP-2: no silent defaults)",
                        task.task_id,
                        task_design.get("status"),
                        _design_lines,
                    )
                    design_doc_text = None
                    _design_lines = 0
                    _design_sections = 0
                else:
                    logger.info(
                        "DESIGN→IMPLEMENT boundary: task %s design document "
                        "propagated (%d chars, %d lines, %d sections)",
                        task.task_id,
                        len(design_doc_text),
                        _design_lines,
                        _design_sections,
                    )

            # Per-task implement token cap from design_calibration
            task_cal = (calibration_map or {}).get(task.task_id, {})
            max_output_tokens = task_cal.get("implement_max_output_tokens")

            # Initialize env_checks early so LOC mismatch and multi-file
            # checks can both append to it.
            env_checks = list(task.environment_checks)

            # ── Fix 3: LOC estimation mismatch detection ─────────────────
            # If the design doc exists, estimate its implied LOC from code
            # blocks and compare against the seed's estimated_loc.  A large
            # mismatch (>3x) means the depth tier was likely too low, which
            # causes truncation, incomplete output, and wasted retries.
            if design_doc_text and task.estimated_loc:
                _code_line_count = sum(
                    1 for line in design_doc_text.split("\n")
                    if line.strip()
                    and not line.strip().startswith("#")
                    and not line.strip().startswith("```")
                )
                # Rough heuristic: design doc code blocks ≈ 60% of total
                # lines are actual code.  Compare against seed estimate.
                _implied_loc = int(_code_line_count * 0.6)
                if _implied_loc > task.estimated_loc * 3:
                    env_checks.append({
                        "check_name": "loc_estimation_mismatch",
                        "status": "warn",
                        "message": (
                            f"Design doc implies ~{_implied_loc} LOC but seed "
                            f"estimates {task.estimated_loc} LOC (>{3}x mismatch)"
                        ),
                        "detail": (
                            f"The design document for {task.task_id} contains "
                            f"~{_code_line_count} non-empty lines, implying "
                            f"~{_implied_loc} LOC of implementation. The seed "
                            f"estimated {task.estimated_loc} LOC, which placed "
                            f"this task in the '{task_cal.get('depth_tier', 'standard')}' "
                            f"depth tier. Token budget will be auto-recalibrated "
                            f"based on design-implied LOC."
                        ),
                    })
                    logger.warning(
                        "LOC mismatch for task %s: design implies ~%d LOC, "
                        "seed estimates %d LOC (depth_tier=%s). "
                        "Token budget will be auto-recalibrated.",
                        task.task_id,
                        _implied_loc,
                        task.estimated_loc,
                        task_cal.get("depth_tier", "standard"),
                    )

                    # ── Defense-in-depth: auto-recalibrate token budget ────
                    # The design phase expanded scope beyond the seed
                    # estimate.  Bump implement tokens to prevent
                    # truncation rather than just warning about it.
                    # Tiers: <=150 LOC → 32768, <=400 LOC → 49152, >400 → 64000
                    # Cap at 64000: lowest common max across lead (opus)
                    # and drafter (haiku) models in the pipeline.
                    if _implied_loc <= 150:
                        _recal_tokens = 32768
                    elif _implied_loc <= 400:
                        _recal_tokens = 49152
                    else:
                        _recal_tokens = 64000
                    if max_output_tokens is None or _recal_tokens > max_output_tokens:
                        logger.info(
                            "Auto-recalibrating implement tokens for %s: "
                            "%s → %d (design implies ~%d LOC)",
                            task.task_id,
                            max_output_tokens,
                            _recal_tokens,
                            _implied_loc,
                        )
                        max_output_tokens = _recal_tokens

            # ── Multi-file preflight checks ──────────────────────────────
            # Surface risk signals as environment checks so they appear in
            # preflight reports.  These are task-level (not per-file) checks
            # derived from real-world failure patterns (PI-001 post-mortem).
            if len(task.target_files) > 1:
                env_checks.append({
                    "check_name": "multi_file_split_risk",
                    "status": "warn",
                    "message": (
                        f"Task targets {len(task.target_files)} files — "
                        f"LLM may omit some code blocks"
                    ),
                    "detail": (
                        f"Target files: {', '.join(task.target_files)}. "
                        f"Multi-file tasks have higher risk of incomplete output. "
                        f"Defense layers: prompt checklist, __init__.py constraint, "
                        f"content-heuristic extraction, retry with role hints, "
                        f"stub fallback."
                    ),
                })
                init_files = [
                    f for f in task.target_files if f.endswith("__init__.py")
                ]
                if init_files:
                    env_checks.append({
                        "check_name": "init_py_in_multi_file",
                        "status": "warn",
                        "message": (
                            f"__init__.py among {len(task.target_files)} targets — "
                            f"commonly skipped by LLM drafters"
                        ),
                        "detail": (
                            f"Files: {', '.join(init_files)}. "
                            f"Models treat __init__.py as optional because it's "
                            f"'just imports'. Dedicated constraints and extraction "
                            f"heuristics are active."
                        ),
                    })
                # High-LOC multi-file: truncation risk compounds with split risk
                if task.estimated_loc and task.estimated_loc > 200:
                    env_checks.append({
                        "check_name": "multi_file_high_loc",
                        "status": "warn",
                        "message": (
                            f"Multi-file task with {task.estimated_loc} estimated LOC — "
                            f"truncation may compound split failure"
                        ),
                        "detail": (
                            "Consider splitting into single-file tasks, or increase "
                            "implement_max_output_tokens in design_calibration."
                        ),
                    })

            # Multi-file format constraint: ensure LLM produces distinct blocks per file
            prompt_constraints = list(task.prompt_constraints)

            # Domain-aware output format constraint: prevent test code generation
            # for non-code artifacts (config YAML, JSON dashboards, runbooks, etc.).
            # The design doc may contain test examples that confuse the LLM into
            # generating test code instead of the target artifact.
            _target_ext = (
                Path(task.target_files[0]).suffix.lower()
                if task.target_files else ""
            )
            if _target_ext in (".yaml", ".yml") and task.domain in (
                "config-yaml", "unknown",
            ):
                prompt_constraints.append(
                    f"TARGET FILE FORMAT — you MUST generate ONLY a valid YAML "
                    f"configuration file for: {task.target_files[0]}. "
                    f"The output MUST be parseable by yaml.safe_load(). "
                    f"Do NOT generate Python test code, validation scripts, or "
                    f"documentation — even if the design document contains test "
                    f"examples. Those are for reference only, not implementation."
                )
            elif _target_ext == ".json":
                prompt_constraints.append(
                    f"TARGET FILE FORMAT — you MUST generate ONLY valid JSON "
                    f"for: {task.target_files[0]}. "
                    f"The output MUST be parseable by json.loads(). "
                    f"Do NOT generate Python test code or scripts."
                )
            elif _target_ext == ".md":
                prompt_constraints.append(
                    f"TARGET FILE FORMAT — you MUST generate a Markdown document "
                    f"for: {task.target_files[0]}. "
                    f"Do NOT generate Python code or test scripts."
                )

            if len(task.target_files) > 1:
                _task_mode = "create"
                if edit_mode_map and task.task_id in edit_mode_map:
                    _task_mode = edit_mode_map[task.task_id].mode

                if _task_mode != "edit":
                    file_list = ", ".join(task.target_files)
                    prompt_constraints.append(
                        f"MULTI-FILE OUTPUT REQUIRED — you MUST produce a SEPARATE fenced "
                        f"code block for EACH of these {len(task.target_files)} target files: "
                        f"{file_list}. "
                        f"First line of each block MUST be a comment with the full path "
                        f"(e.g. # src/package/__init__.py). "
                        f"If a file is a shared module implemented by downstream tasks, "
                        f"produce a minimal stub (imports, docstring, empty registrations). "
                        f"Every target file MUST have its own code block — omitting any "
                        f"file will cause the build to fail."
                    )
                    # Layer 3 (defense-in-depth): dedicated __init__.py constraint.
                    # Models commonly skip __init__.py because it's "just imports".
                    # This makes the requirement explicit and impossible to miss.
                    init_files = [f for f in task.target_files if f.endswith("__init__.py")]
                    if init_files:
                        init_list = ", ".join(init_files)
                        prompt_constraints.append(
                            f"PACKAGE __init__.py REQUIRED — {init_list} MUST have "
                            f"its own separate code block. Even a minimal file with "
                            f"imports and __all__ is required. The build will FAIL "
                            f"if any __init__.py is missing its own block."
                        )

                    # ── Downstream file detection ──────────────────────────────
                    # Reuse the already-computed downstream_map from Gate 2c
                    # (via _reconcile_design_downstream) instead of re-calling
                    # _detect_downstream_files() on the same design doc text.
                    _task_downstream_prompt = downstream_map.get(task.task_id, [])
                    if _task_downstream_prompt:
                        ds_list = ", ".join(_task_downstream_prompt)
                        prompt_constraints.append(
                            f"DOWNSTREAM FILE STUBS — the following files are marked "
                            f"as shared/downstream in the design doc: {ds_list}. "
                            f"You MUST still produce a code block for each one, but "
                            f"it can be a MINIMAL stub: module docstring, imports, "
                            f"empty __all__, and placeholder functions/classes. "
                            f"A 5-line stub is acceptable — omitting the file is NOT."
                        )
                        logger.info(
                            "IMPLEMENT: detected %d downstream files for task %s: %s",
                            len(_task_downstream_prompt), task.task_id, _task_downstream_prompt,
                        )

            # ── Gate 2c: shrink file_targets for downstream files ────────
            # If Gate 2c pre-stubbed some files, remove them from the
            # drafter's target list so it only implements files it's supposed
            # to.  Downstream files are already on disk as stubs.
            task_downstream = downstream_map.get(task.task_id, [])
            effective_targets = [
                f for f in task.target_files
                if f not in task_downstream
            ] if task_downstream else task.target_files

            # ── PCA-605c: merge design-discovered files into targets ──────
            # The DESIGN phase may split code into new files not in the
            # original target_files.  Merge them so IMPLEMENT generates
            # code for the right set of files.
            _discovered_targets = (
                design_results.get(task.task_id, {}).get("discovered_target_files")
            )
            if _discovered_targets:
                _before = list(effective_targets)
                effective_targets = list(
                    dict.fromkeys(effective_targets + _discovered_targets)
                )
                if effective_targets != _before:
                    logger.info(
                        "PCA-605c: task %s effective_targets expanded %s → %s",
                        task.task_id,
                        _before,
                        effective_targets,
                    )

            # ── AR-138: preflight output-size guard + split guidance ─────
            _effective_loc = task.estimated_loc
            if _design_lines:
                _effective_loc = max(_effective_loc, int(_design_lines * 0.6))
            _estimated_tokens = int((_effective_loc * 24) + (len(effective_targets) * 512))
            if isinstance(max_output_tokens, int) and max_output_tokens > 0:
                _estimated_tokens = max(_estimated_tokens, max_output_tokens)
            preflight_estimate = {
                "estimated_loc": _effective_loc,
                "estimated_tokens": _estimated_tokens,
                "safe_loc_limit": preflight_safe_loc_limit,
                "safe_token_limit": preflight_safe_token_limit,
                "target_file_count": len(effective_targets),
            }
            if (
                _effective_loc > preflight_safe_loc_limit
                or _estimated_tokens > preflight_safe_token_limit
            ):
                split_guidance = (
                    f"Task {task.task_id} exceeds IMPLEMENT preflight safe limits "
                    f"(loc={_effective_loc}, tokens={_estimated_tokens}). "
                    "Split into smaller execution units before regeneration."
                )
                logger.warning("IMPLEMENT: %s", split_guidance)
                skipped.append({
                    "task_id": task.task_id,
                    "title": task.title,
                    "status": "preflight_blocked_size",
                    "complexity_tier": "tier_2",
                    "reason": "preflight_size_limit_exceeded",
                    "split_guidance": split_guidance,
                    "preflight_estimate": preflight_estimate,
                })
                _log_task_boundary_complete(
                    task.task_id,
                    status="preflight_blocked_size",
                    phase="implement",
                )
                continue

            # ── AR-138: staleness/provenance classification metadata ─────
            provenance_files: list[dict[str, Any]] = []
            current_count = 0
            stale_count = 0
            missing_count = 0
            for _target in effective_targets:
                _state_hint = staleness_classification.get(_target)
                _exists = False
                if project_root_path:
                    try:
                        _exists = (Path(project_root_path) / _target).exists()
                    except (OSError, ValueError):
                        _exists = False
                if _exists:
                    if _state_hint == "stale":
                        _status = "stale"
                        stale_count += 1
                    else:
                        _status = "current"
                        current_count += 1
                else:
                    _status = "missing"
                    missing_count += 1
                provenance_files.append({
                    "path": _target,
                    "status": _status,
                    "staleness_hint": _state_hint,
                })
            artifact_provenance = {
                "files": provenance_files,
                "summary": {
                    "current": current_count,
                    "stale": stale_count,
                    "missing": missing_count,
                },
            }
            reuse_decision = (
                "reuse_candidate"
                if stale_count == 0 and missing_count == 0 and current_count > 0
                else "regenerate_required"
            )

            # Strip dependencies on tasks not in this run (already completed
            # or filtered out by --task-filter).  The plan validator rejects
            # references to non-existent chunks.
            in_scope_deps = [d for d in task.depends_on if d in active_task_ids]

            # ── IMP-7: DESIGN→IMPLEMENT parameter completeness validation ──
            # Check that resolved_parameters from the seed are present in the
            # design document. Missing parameters indicate information loss at
            # the DESIGN bottleneck.
            design_completeness_warning = ""
            _param_completeness = task_design.get("parameter_completeness")
            if (
                isinstance(_param_completeness, dict)
                and _param_completeness.get("missing_count", 0)
            ):
                _missing = _param_completeness.get("missing", []) or []
                _missing_preview = ", ".join(
                    f"{m.get('key')}={m.get('value')}"
                    for m in _missing[:5]
                    if isinstance(m, dict)
                )
                design_completeness_warning = (
                    f"WARNING: {_param_completeness.get('missing_count', 0)} "
                    f"resolved parameter(s) missing from DESIGN specification: "
                    f"{_missing_preview}. Include them verbatim in implementation."
                )
            elif design_doc_text:
                _task_seed = design_results.get(task.task_id, {})
                _seed_config = _task_seed.get("_seed_config", {})
                _resolved = _seed_config.get("resolved_parameters", {})
                if not _resolved:
                    # Also check additional_context from the task
                    _resolved = {}
                    for atype in task.artifact_types_addressed:
                        for k, v in (parameter_sources or {}).get(atype, {}).items():
                            if isinstance(v, str):
                                _resolved[k] = v
                missing_params: list[str] = []
                for param_key, param_val in _resolved.items():
                    val_str = str(param_val)
                    if val_str and val_str not in design_doc_text:
                        missing_params.append(f"{param_key}={val_str}")
                if missing_params:
                    design_completeness_warning = (
                        f"WARNING: {len(missing_params)} resolved parameter(s) "
                        f"not found in design document: {', '.join(missing_params[:5])}. "
                        f"These may have been lost at the DESIGN bottleneck. "
                        f"Include them verbatim in your implementation."
                    )
                    logger.warning(
                        "IMP-7 DESIGN→IMPLEMENT gate: task %s missing %d parameter(s) "
                        "in design doc: %s",
                        task.task_id,
                        len(missing_params),
                        ", ".join(missing_params[:5]),
                    )

            # ── Phase 5: Forward Manifest Interface Contracts ──────
            _forward_contracts = None
            forward_manifest = kwargs.get("forward_manifest")
            if forward_manifest is not None:
                # Lazy import inside the loop to avoid circular import overhead
                from startd8.contractors.artisan_phases.design_prompts.seed_mapping import map_forward_contracts_for_task
                from startd8.contractors.artisan_phases.design_prompts.modules import ContractModule
                _contract_data = map_forward_contracts_for_task(task, forward_manifest=forward_manifest)
                if _contract_data:
                    _fragment = ContractModule().render(_contract_data)
                    if _fragment and _fragment.text:
                        _forward_contracts = _fragment.text
                        logger.info(
                            "IMPLEMENT: injected forward contracts for task %s",
                            task.task_id,
                        )

            # ── Phase 6: Skeleton file detection for body-only prompting ──
            _skeleton_file_list: str | None = None
            _skeleton_files_present = False
            _scaffold_data = scaffold_output or {}
            _file_stubs = _scaffold_data.get("file_stubs", [])
            _asm_degraded = _scaffold_data.get("assembly_degraded", False)
            if _file_stubs and not _asm_degraded:
                _task_skeleton_lines: list[str] = []
                for stub in _file_stubs:
                    stub_status = stub.get("status", "") if isinstance(stub, dict) else getattr(stub, "status", "")
                    stub_path = stub.get("file_path", "") if isinstance(stub, dict) else getattr(stub, "file_path", "")
                    if stub_status == "created" and stub_path in set(effective_targets):
                        _task_skeleton_lines.append(f"- `{stub_path}`")
                if _task_skeleton_lines:
                    _skeleton_files_present = True
                    _skeleton_file_list = "\n".join(_task_skeleton_lines)
                    logger.info(
                        "IMPLEMENT: %d skeleton file(s) detected for task %s",
                        len(_task_skeleton_lines), task.task_id,
                    )

            # Micro Prime pre-pass: determine if this chunk was fully filled locally
            _mp_complete = False
            _mp_skeletons: dict[str, str] | None = None
            _mp_escalated: list[dict[str, Any]] | None = None
            if micro_prime_result:
                _mp_filled = micro_prime_result.get("filled_skeletons") or {}
                _mp_esc_all = micro_prime_result.get("escalated_elements") or []
                _target_set = set(effective_targets)
                _mp_skeletons = {t: _mp_filled[t] for t in effective_targets if t in _mp_filled}
                _mp_escalated = [e for e in _mp_esc_all if e.get("file_path") in _target_set]
                _mp_complete = (
                    len(_mp_skeletons) == len(effective_targets)
                    and len(effective_targets) > 0
                    and len(_mp_escalated) == 0
                )

            chunks.append(DevelopmentChunk(
                chunk_id=task.task_id,
                description=task.description,
                dependencies=in_scope_deps,
                file_targets=effective_targets,
                implementation_prompt=task.description,
                test_commands=[],  # Post-gen validation via DomainChecklist
                max_retries=max_retries,
                metadata={
                    "feature_id": task.feature_id,
                    "domain": task.domain,
                    "estimated_loc": task.estimated_loc,
                    "prompt_constraints": prompt_constraints,
                    "environment_checks": env_checks,
                    "post_generation_validators": task.post_generation_validators,
                    "title": task.title,
                    "design_document": design_doc_text,
                    "design_document_missing": design_doc_text is None,
                    "_design_lines": _design_lines,
                    "_design_sections": _design_sections,
                    "max_output_tokens": max_output_tokens,
                    "preflight_estimate": preflight_estimate,
                    "artifact_provenance": artifact_provenance,
                    "reuse_decision": reuse_decision,
                    "artifact_types_addressed": task.artifact_types_addressed,
                    "downstream_files": task_downstream,
                    "original_target_files": task.target_files if task_downstream else None,
                    # IMP-7: DESIGN→IMPLEMENT parameter completeness warning
                    "design_completeness_warning": design_completeness_warning,
                    # PCA-300: project architecture for code generation
                    "architectural_context": architectural_context or {},
                    "plan_goals": (plan_goals or [])[:5],
                    "plan_context": (plan_context or "")[:4000] or None,
                    # PCA-301/400: service metadata for protocol compliance
                    "service_metadata": service_metadata if service_metadata else None,
                    # PCA-403: cross-feature context accumulation
                    "prior_implementations": (prior_impl_summaries or [])[-3:] if prior_impl_summaries else None,
                    # PCA-404: requirements text for IMPLEMENT prompt
                    "requirements_text": task.requirements_text[:3000] if task.requirements_text else None,
                    # PCA-501: project identity for edit-first behavior
                    "project_name": project_name,
                    "project_root_path": project_root_path,
                    # PCA-600: edit mode classification from upstream signals
                    "_edit_mode": (edit_mode_map or {}).get(task.task_id, EditModeClassification(
                        mode="create", per_file={}, confidence="low",
                    )).to_dict() if edit_mode_map else None,
                    # AR-822: module inventory from SCAFFOLD for import grounding
                    "module_inventory": module_inventory or [],
                    # Mottainai Rule 5: parameter provenance for IMPLEMENT prompt
                    "parameter_sources": parameter_sources or {},
                    "semantic_conventions": semantic_conventions or {},
                    # Phase 5: Forward interface contracts
                    "forward_contracts": _forward_contracts,
                    # Phase 6: Skeleton file detection for body-only prompting
                    "skeleton_file_list": _skeleton_file_list,
                    "skeleton_files_present": _skeleton_files_present,
                    # REQ-CMR-042: per-task override from seed JSON
                    "complexity_tier_override": task.complexity_tier_override,
                    # Micro Prime pre-pass: per-chunk fill status
                    "_micro_prime_complete": _mp_complete,
                    "_micro_prime_filled_skeletons": _mp_skeletons if _mp_skeletons else None,
                    "_micro_prime_escalated": _mp_escalated if _mp_escalated else None,
                },
            ))

        # ── Layer 1: aggregate handoff log ────────────────────────────
        tasks_with_design = sum(
            1 for c in chunks if c.metadata.get("design_document")
        )
        logger.info(
            "DESIGN→IMPLEMENT handoff: %d/%d tasks have design documents",
            tasks_with_design,
            len(chunks),
        )

        return chunks, skipped

    def _map_development_result(
        self,
        dev_result: Any,  # DevelopmentResult
        chunks: list[Any],  # list[DevelopmentChunk]
        tasks: list[SeedTask],
        skipped_reports: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], dict[str, GenerationResult], float]:
        """Map DevelopmentResult back to the output format downstream expects.

        Reconstructs ``generation_results`` (dict[str, GenerationResult])
        from chunk metadata where ``LeadContractorChunkExecutor`` stored them.

        Args:
            dev_result: The DevelopmentResult from DevelopmentPhase.run().
            chunks: The DevelopmentChunk list (with metadata populated).
            tasks: Original SeedTask list for domain grouping.
            skipped_reports: Pre-filtered env-blocked task reports.

        Returns:
            Tuple of (output_dict, generation_results, total_cost).
        """
        from startd8.contractors.artisan_phases.development import ChunkStatus

        chunk_map = {c.chunk_id: c for c in chunks}
        generation_results: dict[str, GenerationResult] = {}
        task_reports: list[dict[str, Any]] = list(skipped_reports)
        total_cost = 0.0

        for chunk_id, state in dev_result.chunk_states.items():
            chunk = chunk_map.get(chunk_id)
            if chunk is None:
                continue

            meta = chunk.metadata
            gen_result = meta.get("_generation_result")

            task_report: dict[str, Any] = {
                "task_id": chunk_id,
                "feature_id": meta.get("feature_id", ""),
                "title": meta.get("title", ""),
                "domain": meta.get("domain", "unknown"),
                "complexity_tier": meta.get("_complexity_tier", "tier_2"),
                "target_files": chunk.file_targets,
                "estimated_loc": meta.get("estimated_loc", 0),
                "depends_on": chunk.dependencies,
                "prompt_constraints_count": len(meta.get("prompt_constraints", [])),
                "validators": meta.get("post_generation_validators", []),
                # PCA-505: track whether existing files were present for review
                "had_existing_files": bool(meta.get("_existing_file_contents")),
                # AR-138: IMPLEMENT preflight + provenance audit fields
                "preflight_estimate": meta.get("preflight_estimate"),
                "artifact_provenance": meta.get("artifact_provenance"),
                "reuse_decision": meta.get("reuse_decision"),
            }

            # Surface missing target files (Fix 3: missing file detection)
            missing_targets = meta.get("_missing_targets")
            if missing_targets:
                task_report["missing_targets"] = missing_targets

            # Surface design document absence for downstream phases (Issue 4)
            if meta.get("design_document_missing"):
                task_report["design_document_missing"] = True

            if state.status == ChunkStatus.PASSED and gen_result is not None:
                task_report["status"] = "generated"
                task_report["cost"] = gen_result.cost_usd
                task_report["tokens"] = {
                    "input": gen_result.input_tokens,
                    "output": gen_result.output_tokens,
                }
                task_report["iterations"] = gen_result.iterations
                generation_results[chunk_id] = gen_result
                total_cost += gen_result.cost_usd
            elif state.status == ChunkStatus.FAILED:
                task_report["status"] = "generation_failed"
                task_report["error"] = state.last_error or "Unknown failure"
                if gen_result is not None:
                    task_report["cost"] = gen_result.cost_usd
                    task_report["tokens"] = {
                        "input": gen_result.input_tokens,
                        "output": gen_result.output_tokens,
                    }
                    task_report["iterations"] = gen_result.iterations
                    generation_results[chunk_id] = gen_result
                    total_cost += gen_result.cost_usd
            elif state.status == ChunkStatus.SKIPPED:
                task_report["status"] = "dep_blocked"
                task_report["error"] = state.last_error or "Dependency not satisfied"
            else:
                task_report["status"] = "unknown"

            _log_task_boundary_complete(
                chunk_id,
                status=str(task_report.get("status", "unknown")),
                phase="implement",
                cost_usd=_coerce_optional_float(task_report.get("cost")),
            )
            task_reports.append(task_report)

        # Domain breakdown
        domain_tasks: dict[str, list[str]] = defaultdict(list)
        for task in tasks:
            domain_tasks[task.domain].append(task.task_id)

        output: dict[str, Any] = {
            "task_reports": task_reports,
            "tasks_processed": len(task_reports),
            "domain_breakdown": {d: len(ids) for d, ids in domain_tasks.items()},
            "total_estimated_loc": sum(t.estimated_loc for t in tasks),
            "total_cost": total_cost,
            "generation_results": {
                tid: {"success": r.success, "error": r.error, "cost": r.cost_usd}
                for tid, r in generation_results.items()
            },
            "development_result_summary": dev_result.summary,
            "execution_order": dev_result.execution_order,
        }

        return output, generation_results, total_cost

    @staticmethod
    def _run_development_phase(
        dev_phase: Any,
        plan: Any,
        timeout: Optional[float] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> Any:
        """Run DevelopmentPhase in a dedicated thread-owned event loop.

        Using a dedicated thread avoids nested event-loop errors when the
        caller is already inside an async runtime (e.g. notebooks, test
        harnesses, or async servers).

        Args:
            dev_phase: The DevelopmentPhase instance.
            plan: The DevelopmentPlan to execute.
            timeout: Maximum seconds to wait for the thread. ``None``
                means wait indefinitely (the orchestrator's own timeout
                still applies at the outer level).
            cancel_event: Optional :class:`threading.Event` for cooperative
                cancellation. When set after a timeout, signals the background
                thread to stop initiating new LLM calls.
        """
        result_box: dict[str, Any] = {}
        error_box: dict[str, Exception] = {}
        parent_ctx = capture_context()
        # OT-710: Capture boundary result for thread propagation
        from startd8.contractors.forensic_log import (
            get_boundary_result,
            set_boundary_result,
            reset_boundary_result,
        )
        parent_boundary_result = get_boundary_result()

        def _runner() -> None:
            token = attach_context(parent_ctx)
            br_token = set_boundary_result(parent_boundary_result)
            try:
                loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(loop)
                    result_box["result"] = loop.run_until_complete(
                        dev_phase.run(plan)
                    )
                except Exception as exc:  # pragma: no cover - propagated
                    error_box["error"] = exc
                finally:
                    loop.close()
                    asyncio.set_event_loop(None)
            finally:
                reset_boundary_result(br_token)
                detach_context(token)

        # daemon=True is intentional: if the main process exits (e.g.
        # KeyboardInterrupt or SIGTERM), we don't want this thread to keep
        # the process alive indefinitely.  For *cooperative* shutdown the
        # cancel_event is preferred — setting it tells the DevelopmentPhase
        # to stop initiating new LLM calls.  daemon=True is the fallback
        # for uncooperative exits where cancel_event alone isn't enough.
        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            # M-12: Race guard — the thread may have completed between
            # join() returning and the is_alive() check.  If result_box
            # was populated the work *did* finish; treat it as success
            # rather than raising a false TimeoutError.
            if "result" in result_box or "error" in error_box:
                logger.debug(
                    "DevelopmentPhase thread reported alive after join() "
                    "but result_box is populated — treating as completed",
                )
            else:
                if cancel_event:
                    cancel_event.set()
                    logger.warning(
                        "Cancel event set — signalling background DevelopmentPhase "
                        "thread to stop initiating new LLM calls",
                    )
                logger.error(
                    "DevelopmentPhase did not complete within %.0fs — "
                    "abandoning background thread (daemon=True)",
                    timeout,
                )
                raise TimeoutError(
                    f"DevelopmentPhase.run() did not complete within {timeout}s"
                )

        if "error" in error_box:
            raise error_box["error"]
        return result_box["result"]

    # ------------------------------------------------------------------
    # Resume cache validation (v2 format)
    # ------------------------------------------------------------------

    def _validate_resume_cache(
        self,
        saved: dict[str, Any],
        tasks: list[SeedTask],
        project_root: Path,
        source_checksum: str | None,
        design_results: dict[str, Any] | None = None,
    ) -> dict[str, GenerationResult] | None:
        """Validate a saved generation_results cache through 8 ordered layers.

        Returns a dict of task_id → GenerationResult if all layers pass,
        or None if the cache should be rejected (caller falls through to
        fresh IMPLEMENT).

        Layers (cheapest → most expensive):
            0: Schema version — _cache_meta exists, schema_version == _CACHE_SCHEMA_VERSION
            1: Filter success:false entries (info log)
            2: Coverage — all current task IDs present in successful entries
            3: Source checksum — _cache_meta.source_checksum matches context
            3b: Design hash — design_results hash matches context (catches
                ``--force-design`` invalidation; mirrors TEST/REVIEW Layer 1.5)
            4: Path validation — cached generated_files match task.target_files
            5: File existence — every cached file exists on disk
            6: Content hash — sha256(file_bytes) matches cached content_hashes
        """
        # Layer 0: Schema version
        cache_meta = saved.get("_cache_meta")
        if not isinstance(cache_meta, dict):
            logger.warning(
                "IMPLEMENT --resume: cache missing _cache_meta (v1 or corrupt) — re-running"
            )
            return None
        schema_version = cache_meta.get("schema_version")
        if schema_version != _CACHE_SCHEMA_VERSION:
            logger.warning(
                "IMPLEMENT --resume: cache schema_version=%s (expected %d) — re-running",
                schema_version, _CACHE_SCHEMA_VERSION,
            )
            return None

        tasks_data = saved.get("tasks", {})

        # Layer 1: Filter out failed entries
        successful: dict[str, dict[str, Any]] = {}
        filtered_count = 0
        for tid, data in tasks_data.items():
            if data.get("success"):
                successful[tid] = data
            else:
                filtered_count += 1
        if filtered_count:
            logger.info(
                "IMPLEMENT --resume: filtered %d failed entries from cache",
                filtered_count,
            )

        # Layer 2: Coverage — all current task IDs in successful cache entries
        current_ids = {t.task_id for t in tasks}
        missing = current_ids - set(successful)
        if missing:
            logger.warning(
                "IMPLEMENT --resume: cache missing tasks %s — re-running",
                sorted(missing),
            )
            return None

        # Layer 3: Source checksum
        cached_checksum = cache_meta.get("source_checksum")
        if (
            cached_checksum is not None
            and source_checksum is not None
            and cached_checksum != source_checksum
        ):
            logger.warning(
                "IMPLEMENT --resume: source_checksum mismatch "
                "(cached=%s, current=%s) — re-running",
                cached_checksum, source_checksum,
            )
            return None
        elif cached_checksum is not None or source_checksum is not None:
            logger.warning(
                "IMPLEMENT --resume: Layer 3 (source checksum): partial checksum — "
                "cache has %s, current has %s — cannot verify integrity",
                "checksum" if cached_checksum else "None",
                "checksum" if source_checksum else "None",
            )

        # Layer 3b: Design hash — invalidate when design changes
        # (mirrors TEST/REVIEW Layer 1.5; catches --force-design)
        cached_design_hash = cache_meta.get("design_hash")
        if cached_design_hash is not None and design_results is not None:
            current_design_hash = _compute_design_results_hash(design_results)
            if (
                current_design_hash is not None
                and current_design_hash != cached_design_hash
            ):
                logger.warning(
                    "IMPLEMENT --resume: design_hash mismatch "
                    "(cached=%s, current=%s) — design changed since last "
                    "IMPLEMENT; re-running to regenerate from new design",
                    cached_design_hash[:16], current_design_hash[:16],
                )
                return None
            logger.debug(
                "IMPLEMENT --resume: Layer 3b (design hash): match",
            )
        elif cached_design_hash is not None:
            logger.info(
                "IMPLEMENT --resume: Layer 3b: cache has design_hash but "
                "current context has no design_results — cannot verify; "
                "proceeding (design may not have changed)",
            )

        # Parse GenerationResult objects from successful entries
        generation_results: dict[str, GenerationResult] = {}
        task_map = {t.task_id: t for t in tasks}
        for tid in current_ids:
            data = successful[tid]
            generation_results[tid] = GenerationResult(
                success=data["success"],
                generated_files=[Path(p) for p in data.get("generated_files", [])],
                error=data.get("error"),
                input_tokens=data.get("input_tokens", 0),
                output_tokens=data.get("output_tokens", 0),
                cost_usd=data.get("cost_usd", 0.0),
                iterations=data.get("iterations", 0),
                model=data.get("model", "unknown"),
                metadata=data.get("metadata", {}),
            )

        # Layer 4: Path validation — cached generated_files match task.target_files
        for tid, gr in generation_results.items():
            task = task_map.get(tid)
            if task is None or not gr.generated_files:
                continue
            expected = {
                str((project_root / tf).resolve())
                for tf in task.target_files
            }
            actual = {str(Path(p).resolve()) for p in gr.generated_files}
            if actual != expected:
                logger.warning(
                    "IMPLEMENT --resume: path mismatch for %s "
                    "(expected %s, got %s) — re-running",
                    tid, sorted(expected), sorted(actual),
                )
                return None

        # Layer 5: File existence — every cached file exists on disk
        for tid, gr in generation_results.items():
            for p in gr.generated_files:
                if not Path(p).exists():
                    logger.warning(
                        "IMPLEMENT --resume: cached file missing from disk: %s "
                        "(task %s) — re-running",
                        p, tid,
                    )
                    return None

        # Layer 6: Content hash — sha256(file_bytes) matches cached content_hashes
        for tid in current_ids:
            data = successful[tid]
            content_hashes = data.get("content_hashes", {})
            for fpath, expected_hash in content_hashes.items():
                fp = Path(fpath)
                if not fp.exists():
                    # Already caught by Layer 5, but guard anyway
                    logger.warning(
                        "IMPLEMENT --resume: hash check file missing: %s — re-running",
                        fpath,
                    )
                    return None
                actual_hash = hashlib.sha256(fp.read_bytes()).hexdigest()
                if actual_hash != expected_hash:
                    logger.warning(
                        "IMPLEMENT --resume: content hash mismatch for %s "
                        "(task %s, expected %s, got %s) — re-running",
                        fpath, tid, expected_hash[:12], actual_hash[:12],
                    )
                    return None

        logger.info(
            "IMPLEMENT --resume: all %d layers passed for %d tasks",
            8, len(generation_results),
        )
        return generation_results

    @staticmethod
    def _build_implementation_metadata(context: dict[str, Any]) -> dict[str, Any]:
        """Build the metadata sub-dict mirroring propagation chain fields."""
        tier_distribution = context.get("_tier_distribution")
        if not isinstance(tier_distribution, dict):
            tier_distribution = {"tier_1": 0, "tier_2": 0, "tier_3": 0}
            for report in context.get("implementation", {}).get("task_reports", []):
                tier = report.get("complexity_tier", "tier_2")
                if tier in tier_distribution:
                    tier_distribution[tier] += 1
        return {
            "design_mode_summary": context.get("design_mode_summary", {}),
            "service_metadata": context.get("service_metadata"),
            "_tier_distribution": tier_distribution,
        }

    # ------------------------------------------------------------------
    # REQ-IME-300: Inner loop implementation engine path
    # ------------------------------------------------------------------

    def _execute_with_inner_loop(
        self,
        tasks: list[SeedTask],
        context: dict[str, Any],
        project_root: Path,
        start_time: float,
    ) -> dict[str, Any]:
        """Execute IMPLEMENT phase using the implementation engine's
        iterative spec-draft-review loop.

        This replaces the single-shot DevelopmentPhase with a per-task
        engine pipeline that produces a spec, then iterates draft-review
        cycles until the review passes or max iterations are reached.

        Falls back to logging errors on per-task failures
        (REQ-IME-502: Mottainai Rule 3).

        Returns the same output structure as the standard execute() path
        so downstream phases (INTEGRATE, TEST, REVIEW, FINALIZE) require
        zero code changes (REQ-IME-303).
        """
        from startd8.implementation_engine import (
            DefaultImplementationEngine,
        )

        config = self.config
        staging_dir = Path(config.staging_dir) if config.staging_dir else (
            project_root / ".startd8" / "staging"
        )
        staging_dir.mkdir(parents=True, exist_ok=True)

        # Resolve agent specs
        drafter_spec = config.inner_loop_drafter or config.drafter_agent
        reviewer_spec = config.inner_loop_reviewer or config.lead_agent

        # REQ-IME-502: Validate reviewer is configured (don't mutate shared config)
        if not reviewer_spec:
            logger.warning(
                "IMPLEMENT inner loop: no reviewer agent configured — "
                "falling back to single-shot DevelopmentPhase for all tasks"
            )
            return {
                "output": {"error": "inner_loop_reviewer not configured"},
                "cost": 0.0,
                "metadata": {"duration": time.monotonic() - start_time},
            }

        engine = DefaultImplementationEngine()
        generation_results: dict[str, GenerationResult] = {}
        task_reports: list[dict[str, Any]] = []
        total_cost = 0.0
        truncation_flags: dict[str, dict[str, Any]] = {}

        # --- Pre-IMPLEMENT setup (mirrors standard path) ---

        # Pre-IMPLEMENT: warn about risky multi-file tasks (Gap 4)
        self._validate_multi_file_tasks(tasks)

        # Item 12 (Gap 5): scaffold test files for artifact generator tasks
        if config.scaffold_test_first:
            self._ensure_test_scaffolding_for_artifact_tasks(
                tasks, project_root,
            )

        # Gate 2c (Gap 2): pre-stub downstream files and build downstream_map
        design_results = context.get("design_results", {})
        pre_computed_dm = context.get("_downstream_map")
        if pre_computed_dm is not None:
            downstream_map: dict[str, list[str]] = pre_computed_dm
            logger.debug(
                "IMPLEMENT inner loop: using pre-computed "
                "_downstream_map (%d entries)",
                len(downstream_map),
            )
        else:
            downstream_map = self._reconcile_design_downstream(
                tasks, design_results, project_root,
            )

        # PCA-600: Build per-task edit mode classification
        # (mirrors standard path edit_mode_map computation)
        scaffold = context.get("scaffold", {})
        design_mode_summary = context.get("design_mode_summary", {})
        _mode_evidence = context.get("design_mode_evidence", {})
        _manifest_registry_for_edit = None
        if config.manifest_consumption_enabled:
            _manifest_registry_for_edit = (
                config.manifest_registry or context.get("project_manifests")
            )
        edit_mode_map: dict[str, EditModeClassification] = {}
        for task in tasks:
            edit_mode_map[task.task_id] = self._classify_edit_mode(
                task, scaffold, design_mode_summary,
                design_mode_evidence=_mode_evidence,
                manifest_registry=_manifest_registry_for_edit,
            )
        context["edit_mode_classifications"] = {
            tid: cls.to_dict() for tid, cls in edit_mode_map.items()
        }
        edit_tasks = sum(1 for v in edit_mode_map.values() if v.mode == "edit")
        logger.info(
            "IMPLEMENT inner loop: edit mode classification: %d edit, %d create",
            edit_tasks, len(tasks) - edit_tasks,
        )

        # --- Gap 6: Manifest staleness check (advisory) ---
        _design_checksums = context.get("manifest_file_checksums", {})
        if _design_checksums and project_root:
            _current_checksums = _compute_manifest_file_checksums(
                list(_design_checksums.keys()), str(project_root),
            )
            _stale_files = [
                fpath for fpath, expected in _design_checksums.items()
                if fpath in _current_checksums
                and _current_checksums[fpath] != expected
            ]
            if _stale_files:
                logger.warning(
                    "IMPLEMENT inner loop Gap 6: %d target file(s) "
                    "changed since DESIGN: %s",
                    len(_stale_files),
                    ", ".join(_stale_files[:5]),
                )
                context["_manifest_stale_files"] = _stale_files

        # --- Gap 6: Phantom element warnings (advisory) ---
        _phantom_warnings: dict[str, list[str]] = {}
        _design_refs = context.get("design_referenced_elements", {})
        if _design_refs and _manifest_registry_for_edit is not None:
            for tid, file_refs in _design_refs.items():
                for fpath, elements in file_refs.items():
                    try:
                        _current_summary = (
                            _manifest_registry_for_edit.file_element_summary(
                                fpath, 5000,
                            )
                        )
                    except (AttributeError, TypeError, OSError):
                        _current_summary = None
                    if not _current_summary:
                        continue
                    for elem in elements:
                        if elem not in _current_summary:
                            _phantom_warnings.setdefault(tid, []).append(
                                f"{fpath}:{elem}",
                            )
            if _phantom_warnings:
                context["_phantom_element_warnings"] = _phantom_warnings
                logger.warning(
                    "IMPLEMENT inner loop Gap 6: %d task(s) have "
                    "phantom element references",
                    len(_phantom_warnings),
                )

        # CMR: Complexity-Driven Model Router (mirrors standard path 8563-8630)
        from startd8.contractors.artisan_phases.development import (
            TaskComplexityTier,
        )
        import types as _types

        task_tiers: dict[str, TaskComplexityTier] = {}
        _tier_distribution: dict[str, int] = {"tier_1": 0, "tier_2": 0, "tier_3": 0}

        if config.complexity_routing_enabled:
            _cmr_manifest = None
            if config.manifest_consumption_enabled:
                _cmr_manifest = (
                    config.manifest_registry or context.get("project_manifests")
                )

            for task in tasks:
                try:
                    _cmr_meta: dict[str, Any] = {}
                    # Inject call graph callers from manifest registry
                    if _cmr_manifest and task.target_files:
                        _cg_callers_cmr: list[dict[str, Any]] = []
                        for tf in task.target_files:
                            try:
                                callers_map = _cmr_manifest.callers_of_file(tf)
                                for fqn, callers in callers_map.items():
                                    br = _cmr_manifest.blast_radius(
                                        fqn,
                                        max_depth=config.blast_radius_max_depth,
                                    )
                                    _cg_callers_cmr.append({
                                        "fqn": fqn,
                                        "direct_callers": sorted(callers),
                                        "blast_radius": len(br),
                                    })
                            except Exception:
                                logger.debug(
                                    "IMPLEMENT CMR: call graph callers enrichment "
                                    "failed for %s in task %s",
                                    tf, task.task_id, exc_info=True,
                                )
                        if _cg_callers_cmr:
                            _cmr_meta["_call_graph_callers"] = _cg_callers_cmr

                    # Edit mode from classification
                    _edit_cls = edit_mode_map.get(task.task_id)
                    if _edit_cls:
                        _cmr_meta["_edit_mode"] = _edit_cls.to_dict()

                    # Estimated LOC from task
                    if hasattr(task, "estimated_loc") and task.estimated_loc:
                        _cmr_meta["estimated_loc"] = task.estimated_loc

                    # Build chunk-like object for CMR functions
                    _chunk_like = _types.SimpleNamespace(
                        metadata=_cmr_meta,
                        file_targets=task.target_files or [],
                        chunk_id=task.task_id,
                    )

                    signals = _extract_complexity_signals(_chunk_like, _cmr_manifest)
                    tier = _classify_complexity_tier(signals, config)
                    task_tiers[task.task_id] = tier
                    _tier_distribution[tier.value] += 1

                    logger.info(
                        "CMR inner loop: task=%s tier=%s blast=%d callers=%d "
                        "edit=%s loc=%d",
                        task.task_id, tier.value,
                        signals.blast_radius, signals.caller_count,
                        signals.edit_mode, signals.estimated_loc,
                    )
                except Exception:
                    task_tiers[task.task_id] = TaskComplexityTier.TIER_2
                    _tier_distribution["tier_2"] += 1
                    logger.warning(
                        "CMR inner loop: classification failed for %s, "
                        "defaulting to tier_2",
                        task.task_id, exc_info=True,
                    )
        else:
            for task in tasks:
                task_tiers[task.task_id] = TaskComplexityTier.TIER_2
                _tier_distribution["tier_2"] += 1

        context["_tier_distribution"] = _tier_distribution

        # Resume check: load prior generation results if available
        results_path = project_root / ".startd8" / "state" / "generation_results.json"
        resumed = False
        resumed_cost = 0.0

        _is_retry_inner = bool(context.get("_retry_attempt", 0))
        if not config.force_implement and not _is_retry_inner and results_path.exists():
            try:
                saved = json.loads(results_path.read_text(encoding="utf-8"))
                cached_results = self._validate_resume_cache(
                    saved, tasks, project_root,
                    source_checksum=context.get("source_checksum"),
                    design_results=context.get("design_results"),
                )
                if cached_results is not None:
                    generation_results = cached_results
                    resumed = True
                    resumed_cost = sum(
                        gr.cost_usd for gr in cached_results.values()
                    )
                    total_cost = resumed_cost
                    truncation_flags = saved.get("truncation_flags", {})
                    logger.info(
                        "IMPLEMENT inner loop: resumed %d tasks from cache ($%.4f)",
                        len(cached_results), resumed_cost,
                    )
            except (
                json.JSONDecodeError, KeyError, TypeError,
                OSError, ValueError, UnicodeDecodeError,
            ) as exc:
                logger.warning(
                    "IMPLEMENT inner loop: cache load failed: "
                    "%s — running fresh",
                    exc, exc_info=True,
                )

        if not resumed:
            self._execute_inner_loop_tasks(
                tasks, engine, config, context,
                design_results, staging_dir, project_root,
                drafter_spec, reviewer_spec,
                edit_mode_map, task_tiers,
                generation_results, task_reports,
                truncation_flags,
                downstream_map=downstream_map,
            )
            total_cost = sum(
                gr.cost_usd for gr in generation_results.values()
            )

        # --- Post-generation gates (mirrors standard path) ---

        # Gate 3: multi-file completeness
        gate3 = self._validate_generation_completeness(
            tasks, generation_results, project_root,
            downstream_map=downstream_map,
        )

        # Gate 3b: semantic content validation
        _svc_meta = context.get("service_metadata")
        gate3b = self._validate_generation_content(
            tasks, generation_results, project_root,
            service_metadata=_svc_meta,
        )

        # Gate 4: truncation detection
        existing_file_sizes: dict[str, dict[str, int]] = {}
        for task in tasks:
            task_sizes: dict[str, int] = {}
            task_edit_cls = edit_mode_map.get(task.task_id)
            if task_edit_cls and task_edit_cls.mode == "edit":
                for fpath in (task.target_files or []):
                    fp = project_root / fpath
                    if fp.is_file():
                        try:
                            task_sizes[fpath] = len(
                                fp.read_text(encoding="utf-8").splitlines()
                            )
                        except (OSError, UnicodeDecodeError):
                            logger.debug("Could not read file for size check: %s", fp, exc_info=True)
            if task_sizes:
                existing_file_sizes[task.task_id] = task_sizes

        truncation_flags_gate4 = self._validate_truncation(
            tasks, generation_results, project_root,
            existing_file_sizes=existing_file_sizes,
        )
        truncation_flags.update(truncation_flags_gate4)

        # ── Gate 5: Edit-First Enforcement (REQ-EFE-020) ──
        from startd8.contractors.edit_first_gate import (
            validate_task_size_regression,
            resolve_threshold,
            emit_rejection_telemetry,
        )
        from startd8.utils.code_extraction import extract_code_from_response
        import types as _types_g5

        gate5_results: dict[str, Any] = {}
        _output_contracts = context.get("onboarding_output_contracts")
        _schema_features = context.get("onboarding_schema_features")

        # Resolve a retry agent lazily (only if needed)
        _retry_agent = None
        _retry_executor = None

        for task in tasks:
            gr = generation_results.get(task.task_id)
            if gr is None or not gr.success:
                continue

            task_edit_cls = edit_mode_map.get(task.task_id)
            if not task_edit_cls or task_edit_cls.mode != "edit":
                continue  # New-file task — no size regression possible

            # Read existing file contents for comparison
            chunk_efc: dict[str, str] = {}
            for fpath in (task.target_files or []):
                fp = project_root / fpath
                if fp.is_file():
                    try:
                        chunk_efc[fpath] = fp.read_text(
                            encoding="utf-8", errors="replace",
                        )
                    except OSError:
                        logger.debug("Could not read existing file: %s", fp, exc_info=True)
            if not chunk_efc:
                continue

            # Read generated file content from staging
            gen_file_contents: dict[str, str] = {}
            for gen_path in gr.generated_files:
                fp = Path(gen_path)
                if fp.exists():
                    try:
                        rel_key = str(fp.relative_to(staging_dir))
                    except ValueError:
                        # Fallback: use full path string to avoid
                        # name-only collisions across directories.
                        rel_key = str(fp)
                    try:
                        gen_file_contents[rel_key] = fp.read_text(
                            encoding="utf-8",
                        )
                    except (OSError, UnicodeDecodeError):
                        logger.debug("Could not read generated file: %s", fp, exc_info=True)
            if not gen_file_contents:
                continue

            # Resolve threshold
            artifact_types = [
                task.artifact_type,
            ] if hasattr(task, "artifact_type") and task.artifact_type else [
                "source_code",
            ]
            threshold = resolve_threshold(
                artifact_types=artifact_types,
                output_contracts=_output_contracts,
                schema_features=_schema_features,
            )

            gate_result = validate_task_size_regression(
                task_id=task.task_id,
                generated_files=gen_file_contents,
                existing_contents=chunk_efc,
                threshold=threshold,
                artifact_type=(
                    artifact_types[0] if artifact_types else "unknown"
                ),
                force_rewrite=config.force_rewrite,
            )

            if gate_result.any_rejected:
                # Emit rejection telemetry
                try:
                    from opentelemetry import trace as _g5_trace
                    _g5_span = _g5_trace.get_current_span()
                    emit_rejection_telemetry(gate_result, _g5_span)
                except (
                    ImportError, TypeError, AttributeError,
                    RuntimeError, NameError,
                ):
                    logger.debug("Auto-lint import failed", exc_info=True)

                # Lazy-resolve retry agent (once per run)
                if _retry_agent is None:
                    try:
                        from startd8.utils.agent_resolution import (
                            resolve_agent_spec,
                        )
                        _retry_agent = resolve_agent_spec(drafter_spec)
                        _retry_executor = _types_g5.SimpleNamespace(
                            agent=_retry_agent,
                        )
                    except Exception as agent_exc:
                        logger.warning(
                            "Gate 5: cannot resolve retry agent %s: %s",
                            drafter_spec, agent_exc,
                        )

                if _retry_executor is not None:
                    retry_succeeded = self._attempt_edit_first_retry(
                        task, gate_result, chunk_efc, context,
                        gr, _retry_executor, staging_dir, threshold,
                        extract_code_from_response,
                    )

                    # Re-evaluate after retry
                    still_rejected = any(
                        f.action == "rejected"
                        for f in gate_result.file_results
                    )
                    gate_result.any_rejected = still_rejected
                    gate_result.retry_succeeded = (
                        retry_succeeded and not still_rejected
                    )

            gate5_results[task.task_id] = {
                "any_rejected": gate_result.any_rejected,
                "retry_needed": gate_result.retry_needed,
                "retry_succeeded": gate_result.retry_succeeded,
                "file_results": [
                    {
                        "file_path": fr.file_path,
                        "input_chars": fr.input_chars,
                        "output_chars": fr.output_chars,
                        "ratio": round(fr.ratio, 2),
                        "threshold": fr.threshold,
                        "artifact_type": fr.artifact_type,
                        "passed": fr.passed,
                        "action": fr.action,
                    }
                    for fr in gate_result.file_results
                ],
            }

        if gate5_results:
            rejected_count = sum(
                1 for r in gate5_results.values() if r["any_rejected"]
            )
            if rejected_count:
                logger.warning(
                    "Gate 5: %d task(s) with edit-first size regression",
                    rejected_count,
                )
            else:
                logger.info(
                    "Gate 5: edit-first gate passed for %d task(s)",
                    len(gate5_results),
                )
        context["edit_first_gate_results"] = gate5_results

        # Persist generation_results to disk for crash recovery (v2 envelope)
        try:
            save_path = project_root / ".startd8" / "state" / "generation_results.json"
            serializable_tasks: dict[str, dict[str, Any]] = {}
            for tid, gr in generation_results.items():
                content_hashes: dict[str, str] = {}
                for p in gr.generated_files:
                    fp = Path(p)
                    if fp.exists():
                        content_hashes[str(p)] = hashlib.sha256(
                            fp.read_bytes()
                        ).hexdigest()
                serializable_tasks[tid] = {
                    "success": gr.success,
                    "generated_files": [str(p) for p in gr.generated_files],
                    "content_hashes": content_hashes,
                    "error": gr.error,
                    "input_tokens": gr.input_tokens,
                    "output_tokens": gr.output_tokens,
                    "cost_usd": gr.cost_usd,
                    "iterations": gr.iterations,
                    "model": gr.model,
                }
            cache_envelope: dict[str, Any] = {
                "_cache_meta": {
                    "schema_version": _CACHE_SCHEMA_VERSION,
                    "created_at": datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat(),
                    "source_checksum": context.get("source_checksum"),
                    "design_hash": _compute_design_results_hash(
                        context.get("design_results", {})
                    ),
                },
                "truncation_flags": truncation_flags,
                "downstream_map": downstream_map,
                "edit_first_gate_results": gate5_results,
                "tasks": serializable_tasks,
            }
            save_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(save_path, cache_envelope, indent=2)
            logger.info(
                "IMPLEMENT inner loop: saved %d generation results to %s",
                len(generation_results), save_path,
            )
        except Exception as exc:
            logger.warning(
                "IMPLEMENT inner loop: failed to write cache: %s (non-fatal)",
                exc, exc_info=True,
            )

        # --- Assemble output (same structure as DevelopmentPhase path) ---
        if not task_reports:
            # Build task reports for resumed path
            for task in tasks:
                gr = generation_results.get(task.task_id)
                report: dict[str, Any] = {
                    "task_id": task.task_id,
                    "feature_id": task.feature_id,
                    "title": task.title,
                    "status": "resumed",
                    "complexity_tier": task_tiers.get(
                        task.task_id, TaskComplexityTier.TIER_2,
                    ).value,
                }
                if gr is not None:
                    report["cost_usd"] = gr.cost_usd
                    report["iterations"] = gr.iterations
                    report["files_generated"] = len(gr.generated_files)
                task_reports.append(report)

        output: dict[str, Any] = {
            "task_reports": task_reports,
            "tasks_processed": len(task_reports),
            "total_cost": total_cost,
            "generation_results": generation_results,
        }

        if gate3:
            output["_gate3_validation"] = gate3
        if gate3b:
            output["_gate3b_content_validation"] = gate3b
        if truncation_flags_gate4:
            output["_gate4_truncation"] = truncation_flags_gate4
        # Gate 5 results (only include if any rejections)
        if gate5_results:
            rejected_count = sum(
                1 for r in gate5_results.values() if r["any_rejected"]
            )
            if rejected_count:
                output["_gate5_edit_first"] = gate5_results

        context["implementation"] = output
        # C-2 fix: normalize any dict entries to GenerationResult so downstream
        # phases can safely access .cost_usd / .success without AttributeError.
        generation_results = {
            tid: _dict_to_gen_result(v) if isinstance(v, dict) else v
            for tid, v in generation_results.items()
        }
        context["generation_results"] = generation_results
        context["truncation_flags"] = truncation_flags
        output["metadata"] = self._build_implementation_metadata(context)

        # Gap 3: Context propagation for downstream phases (REVIEW, TEST)
        # PCA-403: accumulate prior implementation summaries
        prior_summaries = context.get("_prior_impl_summaries", [])
        for task_id_ps, gr_ps in generation_results.items():
            if gr_ps.success:
                prior_summaries.append({
                    "task_id": task_id_ps,
                    "files": [str(p) for p in gr_ps.generated_files[:5]],
                })
        context["_prior_impl_summaries"] = prior_summaries[-3:]

        # Propagate downstream_map to REVIEW phase
        if downstream_map:
            context["_downstream_map"] = downstream_map

        # Context contract validation
        ImplementPhaseOutput(
            implementation=context["implementation"],
            generation_results=context["generation_results"],
            truncation_flags=context["truncation_flags"],
        )

        duration = time.monotonic() - start_time
        logger.info(
            "IMPLEMENT phase complete (inner loop): %d tasks, $%.4f (%.2fs)",
            len(task_reports), total_cost, duration,
        )
        return {
            "output": output,
            "cost": total_cost,
            "metadata": {
                "duration": duration,
                "resumed": resumed,
                "engine": "implementation_engine",
                **({"resumed_cost": resumed_cost} if resumed else {}),
            },
        }

    def _execute_inner_loop_tasks(
        self,
        tasks: list[SeedTask],
        engine: Any,
        config: "HandlerConfig",
        context: dict[str, Any],
        design_results: dict[str, Any],
        staging_dir: Path,
        project_root: Path,
        drafter_spec: str,
        reviewer_spec: str,
        edit_mode_map: dict[str, EditModeClassification],
        task_tiers: dict[str, Any],
        generation_results: dict[str, GenerationResult],
        task_reports: list[dict[str, Any]],
        truncation_flags: dict[str, dict[str, Any]],
        *,
        downstream_map: dict[str, list[str]] | None = None,
    ) -> None:
        """Run the inner loop engine for each task, populating results in-place."""
        from startd8.implementation_engine import EngineRequest
        from startd8.contractors.artisan_phases.development import (
            TaskComplexityTier,
        )

        for task in tasks:
            task_id = task.task_id
            _log_task_boundary_start(task, phase="implement")

            try:
                # --- Build EngineRequest ---
                engine_context: dict[str, Any] = {}

                # REQ-IME-301: Design document forwarding
                task_design = design_results.get(task_id, {})
                design_doc = task_design.get("design_document")
                _design_doc_missing = False

                # Gate: skip tasks whose DESIGN phase explicitly failed.
                _design_status = task_design.get("status", "")
                if _design_status == "design_failed":
                    _gate_mode = context.get("quality_gate_summary", {}).get(
                        "policy_mode", "warn"
                    )
                    if _gate_mode == "block":
                        logger.warning(
                            "Inner loop task %s: DESIGN failed — skipping "
                            "IMPLEMENT per block policy",
                            task_id,
                        )
                        generation_results[task_id] = GenerationResult(
                            text="", time_ms=0,
                            token_usage={"input": 0, "output": 0},
                            success=False,
                            error="design_failed: skipped by quality gate (block)",
                            metadata={"design_gated": True},
                        )
                        task_reports.append({
                            "task_id": task_id, "status": "design_gated",
                            "error": "DESIGN failed — skipped per block policy",
                        })
                        _log_task_boundary_complete(
                            task_id, status="design_gated",
                            phase="implement",
                        )
                        continue
                    else:
                        logger.warning(
                            "Inner loop task %s: DESIGN failed — skipping "
                            "per %s policy (no design document)",
                            task_id, _gate_mode,
                        )
                        generation_results[task_id] = GenerationResult(
                            text="", time_ms=0,
                            token_usage={"input": 0, "output": 0},
                            success=False,
                            error=f"design_failed: skipped by quality gate ({_gate_mode})",
                            metadata={"design_gated": True},
                        )
                        task_reports.append({
                            "task_id": task_id, "status": "design_gated",
                            "error": f"DESIGN failed — skipped per {_gate_mode} policy",
                        })
                        _log_task_boundary_complete(
                            task_id, status="design_gated",
                            phase="implement",
                        )
                        continue

                if design_doc:
                    engine_context["design_document"] = design_doc
                else:
                    _design_doc_missing = True
                    logger.warning(
                        "Inner loop task %s: no design document available — "
                        "falling back to spec template (Prime route). "
                        "Downstream phases will see design_document_missing flag.",
                        task_id,
                    )

                # REQ-IME-305: Existing file content injection
                existing_files: dict[str, str] = {}
                task_edit_cls = edit_mode_map.get(task_id)
                task_edit_mode = task_edit_cls.to_dict() if task_edit_cls else None
                for target_file in (task.target_files or []):
                    fpath = project_root / target_file
                    if fpath.is_file():
                        try:
                            existing_files[target_file] = fpath.read_text(
                                encoding="utf-8", errors="replace"
                            )
                        except OSError as err:
                            logger.warning(
                                "Inner loop: cannot read %s: %s",
                                target_file, err,
                            )

                # Forward pipeline context
                for key in (
                    "plan_context", "architectural_context",
                    "project_objectives", "semantic_conventions",
                    "domain_constraints", "requirements_text",
                    # Keys already handled by spec_builder but not previously forwarded
                    "forward_contracts", "critical_parameters",
                    "parameter_sources", "requirements_context",
                    "protocol_guidance", "scope_boundary",
                    # FLCM: full manifest object for task-specific constraints
                    "forward_manifest",
                ):
                    val = context.get(key)
                    if val:
                        engine_context[key] = val

                # Phase 4/5/6: Manifest + call graph enrichment
                # (mirrors ImplementPhaseHandler lines 8375-8428)
                _manifest_registry = None
                if config.manifest_consumption_enabled:
                    _manifest_registry = (
                        config.manifest_registry
                        or context.get("project_manifests")
                    )
                if _manifest_registry is not None and task.target_files:
                    _enable_introspect = getattr(
                        config, "enable_introspect", False,
                    )
                    _manifest_budget = config.manifest_context_budget

                    # Phase 4 (IM-1–IM-4) + Phase 5 (IM-1): element summaries
                    _mc_parts: list[str] = []
                    for tf in task.target_files:
                        summary = _manifest_registry.file_element_summary(
                            tf, _manifest_budget,
                            include_resolved_types=_enable_introspect,
                        )
                        if summary:
                            _mc_parts.append(f"### {tf}\n{summary}")
                    if _mc_parts:
                        engine_context["manifest_context"] = "\n\n".join(
                            _mc_parts,
                        )

                    # Phase 6 (CG-IM-1,2,4): call graph summary + callers
                    _cg_budget = config.call_graph_context_budget
                    _cg_parts: list[str] = []
                    _cg_callers: list[dict[str, Any]] = []
                    for tf in task.target_files:
                        try:
                            cg_summary = _manifest_registry.call_graph_summary(
                                tf, _cg_budget,
                            )
                            if cg_summary:
                                _cg_parts.append(f"### {tf}\n{cg_summary}")
                            callers_map = _manifest_registry.callers_of_file(tf)
                            for fqn, callers in callers_map.items():
                                br = _manifest_registry.blast_radius(
                                    fqn,
                                    max_depth=config.blast_radius_max_depth,
                                )
                                _cg_callers.append({
                                    "fqn": fqn,
                                    "direct_callers": sorted(callers),
                                    "blast_radius": len(br),
                                })
                        except Exception:
                            logger.debug(
                                "Inner loop: call graph enrichment failed "
                                "for %s", tf, exc_info=True,
                            )
                    if _cg_parts:
                        engine_context["call_graph_context"] = "\n\n".join(
                            _cg_parts,
                        )
                    if _cg_callers:
                        engine_context["call_graph_callers"] = _cg_callers

                    # Phase 5 (DS-2, DS-4): MRO + runtime attributes
                    if _enable_introspect:
                        _introspect_parts: list[str] = []
                        for tf in task.target_files:
                            try:
                                mro_map = _manifest_registry.file_mro_summary(
                                    tf,
                                )
                                if mro_map:
                                    for cls, chain in mro_map.items():
                                        if len(chain) > 2:
                                            _introspect_parts.append(
                                                f"- {cls} MRO: "
                                                f"{' → '.join(chain)}"
                                            )
                                ra_map = (
                                    _manifest_registry.file_runtime_attributes(
                                        tf,
                                    )
                                )
                                if ra_map:
                                    for elem, attrs in ra_map.items():
                                        _introspect_parts.append(
                                            f"- {elem} runtime attrs: "
                                            f"{', '.join(attrs)}"
                                        )
                            except Exception:
                                logger.debug(
                                    "Inner loop: introspect enrichment "
                                    "failed for %s", tf, exc_info=True,
                                )
                        if _introspect_parts:
                            engine_context[
                                "manifest_introspect_context"
                            ] = "\n".join(_introspect_parts)

                # CMR: select per-task drafter based on complexity tier
                _task_tier = task_tiers.get(
                    task_id, TaskComplexityTier.TIER_2,
                )
                if (
                    _task_tier == TaskComplexityTier.TIER_3
                    and config.tier3_agent
                ):
                    _task_drafter = config.tier3_agent
                else:
                    _task_drafter = drafter_spec

                request = EngineRequest(
                    task_description=task.description or task.title,
                    context=engine_context,
                    drafter_agent_spec=_task_drafter,
                    reviewer_agent_spec=reviewer_spec,
                    max_iterations=config.inner_loop_max_iterations,
                    pass_threshold=config.inner_loop_pass_threshold,
                    existing_files=existing_files or None,
                    edit_mode=task_edit_mode,
                    target_files=task.target_files,
                    check_truncation=config.check_truncation,
                    strict_truncation=config.strict_truncation,
                    fail_on_api_truncation=config.fail_on_truncation,
                    fail_on_heuristic_truncation=False,
                )

                # --- Execute engine ---
                result = engine.build_and_execute(request)

                # --- Map to GenerationResult format (REQ-IME-303) ---
                generated_files: dict[str, str] = {}
                if result.final_code and task.target_files:
                    if len(task.target_files) == 1:
                        generated_files[task.target_files[0]] = result.final_code
                    else:
                        from startd8.utils.code_extraction import (
                            extract_multi_file_code,
                        )
                        raw = result.last_raw_response or result.final_code
                        generated_files = extract_multi_file_code(
                            raw, task.target_files,
                        )

                # Write to staging
                for rel_path, code in generated_files.items():
                    out_path = staging_dir / rel_path
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(code, encoding="utf-8")

                _gen_file_paths: list[Path] = [
                    staging_dir / rel_path for rel_path in generated_files
                ]
                gen_result = GenerationResult(
                    success=bool(result.final_code),
                    generated_files=_gen_file_paths,
                    error=result.error,
                    input_tokens=result.total_input_tokens,
                    output_tokens=result.total_output_tokens,
                    cost_usd=result.total_cost,
                    iterations=result.iterations_used,
                    model=_task_drafter,
                    metadata={
                        "engine_result": result.to_serializable_summary(),
                        "_edit_mode": (
                            task_edit_cls.to_dict()
                            if task_edit_cls
                            else None
                        ),
                        "_complexity_tier": _task_tier.value,
                        **({"design_document_missing": True} if _design_doc_missing else {}),
                    },
                )

                generation_results[task_id] = gen_result

                if result.truncation_events:
                    truncation_flags[task_id] = {
                        "events": result.truncation_events,
                    }

                _task_report: dict[str, Any] = {
                    "task_id": task_id,
                    "feature_id": task.feature_id,
                    "title": task.title,
                    "status": (
                        "engine_passed" if result.passed else "engine_completed"
                    ),
                    "iterations": result.iterations_used,
                    "review_passed": result.passed,
                    "cost_usd": result.total_cost,
                    "files_generated": len(gen_result.generated_files),
                    "complexity_tier": _task_tier.value,
                }
                if _design_doc_missing:
                    _task_report["design_document_missing"] = True
                task_reports.append(_task_report)

                _log_task_boundary_complete(
                    task_id,
                    status="passed" if result.passed else "completed",
                    phase="implement",
                )

            except Exception as exc:
                # REQ-IME-304: Per-task error guard
                logger.warning(
                    "IMPLEMENT inner loop: task %s failed — %s. "
                    "Marking as failed (graceful degradation).",
                    task_id, exc, exc_info=True,
                )
                _err_tier = task_tiers.get(
                    task_id, TaskComplexityTier.TIER_2,
                )
                generation_results[task_id] = GenerationResult(
                    success=False,
                    generated_files=[],
                    error=str(exc),
                    input_tokens=0,
                    output_tokens=0,
                    cost_usd=0.0,
                    iterations=0,
                    model=drafter_spec,
                    metadata={"_complexity_tier": _err_tier.value},
                )
                task_reports.append({
                    "task_id": task_id,
                    "feature_id": task.feature_id,
                    "title": task.title,
                    "status": "engine_error",
                    "error": str(exc),
                    "iterations": 0,
                    "review_passed": False,
                    "cost_usd": 0.0,
                    "files_generated": 0,
                    "complexity_tier": _err_tier.value,
                })
                _log_task_boundary_complete(
                    task_id, status="error", phase="implement",
                )

    # ------------------------------------------------------------------
    # Public execute
    # ------------------------------------------------------------------

    @staticmethod
    def _bridge_retry_feedback(context: dict[str, Any]) -> bool:
        """Bridge AR-153 orchestrator retry feedback into DevelopmentPhase keys.

        The orchestrator (_execute_feature) sets ``prior_error_feedback`` and
        ``retry_feedback`` when rewinding to IMPLEMENT after an
        INTEGRATE/TEST/REVIEW failure.  DevelopmentPhase reads
        ``last_error`` and ``test_output``.  This method bridges the two
        so the LLM receives error-informed retry context.

        Returns True if retry feedback was bridged (i.e. this is a retry).
        """
        retry_attempt = context.get("_retry_attempt", 0)
        if not retry_attempt:
            return False

        # Bridge primary error feedback
        prior_feedback = context.get("prior_error_feedback")
        if prior_feedback and not context.get("last_error"):
            context["last_error"] = prior_feedback

        # Extract structured test/review failure details for the LLM
        retry_fb = context.get("retry_feedback")
        if isinstance(retry_fb, dict) and not context.get("test_output"):
            details = retry_fb.get("details", {})
            source_phase = retry_fb.get("source_phase", "")
            detail_parts: list[str] = []

            test_failures = details.get("test_failures")
            if isinstance(test_failures, dict):
                for tid, info in test_failures.items():
                    if isinstance(info, dict):
                        failures = info.get("failures", [])
                        detail_parts.append(
                            f"Task {tid}: {len(failures)} validator(s) failed — "
                            + ", ".join(str(f) for f in failures[:5])
                        )

            review_failures = details.get("review_failures")
            if isinstance(review_failures, dict):
                for tid, info in review_failures.items():
                    score = info.get("score", "?") if isinstance(info, dict) else info
                    detail_parts.append(f"Task {tid}: review score {score}")

            integration_failures = details.get("integration_failures")
            if isinstance(integration_failures, dict):
                for tid, info in integration_failures.items():
                    reason = (
                        info.get("error", "unknown")
                        if isinstance(info, dict) else str(info)
                    )
                    detail_parts.append(f"Task {tid}: integration failed — {reason}")

            if detail_parts:
                context["test_output"] = (
                    f"[{source_phase.upper()} phase failures]\n"
                    + "\n".join(detail_parts)
                )

        logger.info(
            "IMPLEMENT: AR-153 retry %d — bridged prior_error_feedback → last_error",
            retry_attempt,
        )
        return True

    def execute(
        self,
        phase: WorkflowPhase,
        context: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        start = time.monotonic()
        _log_context_completeness("IMPLEMENT", context)
        tasks: list[SeedTask] = _ensure_context_loaded(context)
        _project_root_str = context.get("project_root")
        project_root = Path(_project_root_str) if _project_root_str and _project_root_str.strip() else Path(".")
        _has_explicit_project_root = bool(_project_root_str and _project_root_str.strip())

        # AR-153: Bridge orchestrator retry feedback into DevelopmentPhase keys.
        # Must run before cache check so _is_retry can gate cache loading.
        _is_retry = self._bridge_retry_feedback(context)

        logger.info(
            "IMPLEMENT phase: processing %d tasks (dry_run=%s, retry=%s)",
            len(tasks), dry_run, _is_retry,
        )

        # --- Pre-IMPLEMENT validation: warn about risky multi-file tasks ---
        self._validate_multi_file_tasks(tasks)

        # --- Dry-run path (unchanged) ---
        if dry_run:
            task_reports: list[dict[str, Any]] = []
            for task in tasks:
                _log_task_boundary_start(task, phase="implement")
                env_checks = self._check_environment(task)
                task_report: dict[str, Any] = {
                    "task_id": task.task_id,
                    "feature_id": task.feature_id,
                    "title": task.title,
                    "domain": task.domain,
                    "complexity_tier": "tier_2",
                    "target_files": task.target_files,
                    "estimated_loc": task.estimated_loc,
                    "depends_on": task.depends_on,
                    "prompt_constraints_count": len(task.prompt_constraints),
                    "validators": task.post_generation_validators,
                    "status": "dry_run_skipped",
                }
                if env_checks:
                    task_report["environment_issues"] = env_checks
                task_reports.append(task_report)
                _log_task_boundary_complete(
                    task.task_id,
                    status=str(task_report["status"]),
                    phase="implement",
                )

            domain_tasks: dict[str, list[str]] = defaultdict(list)
            for task in tasks:
                domain_tasks[task.domain].append(task.task_id)

            output = {
                "task_reports": task_reports,
                "tasks_processed": len(task_reports),
                "domain_breakdown": {d: len(ids) for d, ids in domain_tasks.items()},
                "total_estimated_loc": sum(t.estimated_loc for t in tasks),
                "total_cost": 0.0,
                "generation_results": {},
            }
            context["implementation"] = output
            output["metadata"] = self._build_implementation_metadata(context)
            context["generation_results"] = {}
            context["truncation_flags"] = {}

            # Context contract: validate IMPLEMENT output model (dry-run path)
            ImplementPhaseOutput(
                implementation=context["implementation"],
                generation_results=context["generation_results"],
                truncation_flags=context["truncation_flags"],
            )

            duration = time.monotonic() - start
            logger.info(
                "IMPLEMENT phase complete (dry-run): %d tasks (%.2fs)",
                len(task_reports), duration,
            )
            return {"output": output, "cost": 0.0, "metadata": {"duration": duration, "resumed": False}}

        # --- REQ-MP-503: Micro Prime pre-pass (opt-in) ---
        if self.config.micro_prime_enabled:
            self._run_micro_prime_prepass(context, project_root)

        # --- REQ-IME-300: Inner loop path (opt-in) ---
        if self.config.enable_inner_loop:
            return self._execute_with_inner_loop(
                tasks, context, project_root, start,
            )

        # --- Real-mode path: delegate to DevelopmentPhase ---
        from startd8.contractors.artisan_phases.development import (
            ArtisanChunkExecutor,
            DevelopmentPhase,
            DevelopmentPlan,
            DefaultTestRunner,
            JsonFileStateStore,
        )

        # --- Resume check: load prior generation results if available ---
        # Skip resume when force_implement is set (ignore cache, always run fresh).
        # Skip when no explicit project_root (matches REVIEW's pattern).
        results_path = project_root / ".startd8" / "state" / "generation_results.json"
        # Backward compat: check legacy location
        if not results_path.exists():
            _legacy = project_root / ".startd8_state" / "generation_results.json"
            if _legacy.exists():
                results_path = _legacy
        resumed = False
        downstream_map: dict[str, list[str]] = {}
        truncation_flags: dict[str, dict[str, Any]] = {}
        if not _has_explicit_project_root:
            logger.info("IMPLEMENT: no explicit project_root — skipping cache load")
        # AR-153: On retry, determine which tasks need regeneration.
        # Only failed tasks are regenerated; passing tasks reuse cache.
        _retry_failed_tasks: set[str] = set()
        if _is_retry:
            _rfb = context.get("retry_feedback")
            if isinstance(_rfb, dict):
                _rft = _rfb.get("failed_tasks", [])
                if isinstance(_rft, list):
                    _retry_failed_tasks = set(_rft)
            # If no specific failed tasks identified, fall back to
            # regenerating all tasks (original behavior).
            if not _retry_failed_tasks:
                logger.info(
                    "IMPLEMENT: AR-153 retry with no specific failed_tasks — "
                    "regenerating all tasks",
                )

        if (
            _has_explicit_project_root
            and results_path.exists()
            and not dry_run
            and not self.config.force_implement
            and not (_is_retry and not _retry_failed_tasks)  # AR-153: skip cache only when no specific failed tasks
        ):
            try:
                with open(results_path) as f:
                    saved = json.load(f)
                validated = self._validate_resume_cache(
                    saved, tasks, project_root,
                    source_checksum=context.get("source_checksum"),
                    design_results=context.get("design_results"),
                )
                if validated is not None:
                    generation_results = validated
                    current_task_ids = {t.task_id for t in tasks}

                    # AR-153 scoped retry: evict failed tasks from cache
                    # so they get regenerated while passing tasks are reused.
                    if _retry_failed_tasks:
                        _evicted = {
                            tid for tid in _retry_failed_tasks
                            if tid in generation_results
                        }
                        for tid in _evicted:
                            del generation_results[tid]
                        if _evicted:
                            logger.info(
                                "IMPLEMENT: AR-153 scoped retry — evicted %d/%d "
                                "failed task(s) from cache, reusing %d passing: %s",
                                len(_evicted),
                                len(_retry_failed_tasks),
                                len(generation_results),
                                sorted(_evicted),
                            )
                        else:
                            logger.info(
                                "IMPLEMENT: AR-153 scoped retry — none of %d "
                                "failed task(s) found in cache; full regeneration "
                                "will run: %s",
                                len(_retry_failed_tasks),
                                sorted(_retry_failed_tasks),
                            )
                        # Don't mark as fully resumed — the evicted tasks
                        # will fall through to the fresh generation path.
                        # Store partial cache for merging after regeneration.
                        context["_retry_cached_results"] = dict(generation_results)
                    else:
                        # Fix 1: Restore downstream_map from cache
                        downstream_map = saved.get("downstream_map", {})
                        if not isinstance(downstream_map, dict):
                            logger.warning(
                                "IMPLEMENT resume: downstream_map is not a dict, resetting"
                            )
                            downstream_map = {}

                        # Restore truncation_flags from cache (v3+; graceful for v2)
                        truncation_flags = saved.get("truncation_flags", {})
                        if not isinstance(truncation_flags, dict):
                            logger.warning(
                                "IMPLEMENT resume: truncation_flags is not a dict, resetting"
                            )
                            truncation_flags = {}

                        # Fix 2: Report zero cost for resumed phase (no LLM
                        # calls were made).  Track historical cost separately.
                        total_cost = 0.0
                        resumed_cost = sum(
                            r.cost_usd for tid, r in generation_results.items()
                            if tid in current_task_ids
                        )
                        if resumed_cost == 0.0:
                            logger.info(
                                "IMPLEMENT --resume: historical cost is $0.00 "
                                "(%d cached results, %d current tasks)",
                                len(generation_results),
                                len(current_task_ids),
                            )

                        domain_tasks: dict[str, list[str]] = defaultdict(list)
                        for task in tasks:
                            domain_tasks[task.domain].append(task.task_id)

                        task_reports: list[dict[str, Any]] = []
                        for task in tasks:
                            _log_task_boundary_start(task, phase="implement")
                            gr = generation_results.get(task.task_id)
                            report: dict[str, Any] = {
                                "task_id": task.task_id,
                                "feature_id": task.feature_id,
                                "title": task.title,
                                "domain": task.domain,
                                "complexity_tier": "tier_2",
                                "target_files": task.target_files,
                                "estimated_loc": task.estimated_loc,
                                "depends_on": task.depends_on,
                                "prompt_constraints_count": len(task.prompt_constraints),
                                "validators": task.post_generation_validators,
                            }
                            if gr is not None:
                                report["status"] = "generated" if gr.success else "generation_failed"
                                report["cost"] = gr.cost_usd
                                report["tokens"] = {
                                    "input": gr.input_tokens,
                                    "output": gr.output_tokens,
                                }
                                report["iterations"] = gr.iterations
                                if gr.error:
                                    report["error"] = gr.error
                            else:
                                report["status"] = "not_in_saved_results"
                            task_reports.append(report)
                            _log_task_boundary_complete(
                                task.task_id,
                                status=str(report["status"]),
                                phase="implement",
                                cost_usd=_coerce_optional_float(report.get("cost")),
                            )

                        output: dict[str, Any] = {
                            "task_reports": task_reports,
                            "tasks_processed": len(task_reports),
                            "domain_breakdown": {d: len(ids) for d, ids in domain_tasks.items()},
                            "total_estimated_loc": sum(t.estimated_loc for t in tasks),
                            "total_cost": total_cost,
                            "generation_results": {
                                tid: {"success": r.success, "error": r.error, "cost": r.cost_usd}
                                for tid, r in generation_results.items()
                                if tid in current_task_ids
                            },
                            # Structural parity with fresh-run output
                            "development_result_summary": "resumed from cache",
                            "execution_order": [list(current_task_ids)],
                        }
                        resumed = True
            except (json.JSONDecodeError, KeyError, TypeError, OSError, ValueError, UnicodeDecodeError) as exc:
                logger.warning(
                    "IMPLEMENT --resume: could not load cache: %s — re-running",
                    exc,
                )

        _retry_cached: dict[str, Any] | None = None
        _generation_tasks = tasks
        if not resumed:
            # AR-153 scoped retry: filter tasks to only regenerate failed ones
            # when partial cache was loaded above.
            _retry_cached = context.pop("_retry_cached_results", None)
            if _retry_cached and _retry_failed_tasks:
                _generation_tasks = [
                    t for t in tasks if t.task_id in _retry_failed_tasks
                ]
                logger.info(
                    "IMPLEMENT: AR-153 scoped retry — regenerating %d/%d tasks: %s",
                    len(_generation_tasks),
                    len(tasks),
                    [t.task_id for t in _generation_tasks],
                )

            # Item 12: scaffold test files for artifact generator tasks first
            if self.config.scaffold_test_first:
                self._ensure_test_scaffolding_for_artifact_tasks(
                    _generation_tasks, project_root
                )

            # Convert SeedTasks → DevelopmentChunks (with env pre-filter)
            # Inject design documents from the DESIGN phase into chunk metadata
            design_results = context.get("design_results", {})
            calibration_map = context.get("design_calibration", {})

            # Gate 2c: Reconcile design doc downstream designations.
            # Pre-stubs downstream files on disk and returns a mapping so
            # _tasks_to_chunks can exclude them from drafter targets.
            #
            # In wave mode, pre-stubbing runs on the main thread BEFORE
            # lane dispatch (R8-S6) to prevent filesystem write races.
            # The pre-computed result is stored in context["_downstream_map"].
            # If present, reuse it; otherwise compute here (non-wave modes).
            pre_computed_dm = context.get("_downstream_map")
            if pre_computed_dm is not None:
                downstream_map = pre_computed_dm
                logger.debug(
                    "IMPLEMENT: using pre-computed _downstream_map (%d entries)",
                    len(downstream_map),
                )
            else:
                downstream_map = self._reconcile_design_downstream(
                    tasks, design_results, project_root,
                )

            # PCA-501: derive project name from plan_title with fallback
            _project_name = context.get("plan_title") or project_root.name

            # REQ-EMM-007: Resolve manifest registry BEFORE classification
            # so it is available as the 6th signal in _classify_edit_mode().
            _impl_manifest_registry = None
            if self.config.manifest_consumption_enabled:
                _impl_manifest_registry = (
                    self.config.manifest_registry
                    or context.get("project_manifests")
                )

            # PCA-600: Build per-task edit mode classification from upstream signals
            scaffold = context.get("scaffold", {})
            design_mode_summary = context.get("design_mode_summary", {})
            _mode_evidence = context.get("design_mode_evidence", {})
            edit_mode_map: dict[str, EditModeClassification] = {}
            for task in tasks:
                edit_mode_map[task.task_id] = self._classify_edit_mode(
                    task, scaffold, design_mode_summary,
                    design_mode_evidence=_mode_evidence,
                    manifest_registry=_impl_manifest_registry,
                )
            edit_tasks = sum(1 for v in edit_mode_map.values() if v.mode == "edit")
            conflict_tasks = sum(1 for v in edit_mode_map.values() if v.signal_conflicts)
            _signal_count = 6 if _impl_manifest_registry is not None else 5
            logger.info(
                "IMPLEMENT: edit mode classification: %d edit, %d create "
                "(%d with signal conflicts) (from %d upstream signals, 2-tier weighted consensus)",
                edit_tasks, len(tasks) - edit_tasks, conflict_tasks, _signal_count,
            )
            # PCA-600 AC 9: Persist structured classifications for post-hoc debugging
            context["edit_mode_classifications"] = {
                task_id: classification.to_dict()
                for task_id, classification in edit_mode_map.items()
            }

            # Gap 2: Manifest staleness check — compare design-time checksums
            # against current file state to detect drift between split runs.
            _design_checksums = context.get("manifest_file_checksums", {})
            if _design_checksums and project_root:
                _current_checksums = _compute_manifest_file_checksums(
                    list(_design_checksums.keys()), str(project_root),
                )
                _stale_files = [
                    fpath for fpath, expected in _design_checksums.items()
                    if fpath in _current_checksums
                    and _current_checksums[fpath] != expected
                ]
                if _stale_files:
                    logger.warning(
                        "IMPLEMENT Gap 2: %d target file(s) changed since DESIGN — "
                        "design docs may reference stale structure: %s",
                        len(_stale_files),
                        ", ".join(_stale_files[:5]),
                    )
                    context["_manifest_stale_files"] = _stale_files

            # Gap 1: Phantom element warnings — elements referenced in design
            # but not found in manifest at IMPLEMENT time.
            # NOTE: _impl_manifest_registry was resolved above (REQ-EMM-007).
            _phantom_warnings: dict[str, list[str]] = {}
            _design_refs = context.get("design_referenced_elements", {})
            if _design_refs and _impl_manifest_registry is not None:
                for tid, file_refs in _design_refs.items():
                    for fpath, elements in file_refs.items():
                        try:
                            _current_summary = _impl_manifest_registry.file_element_summary(
                                fpath, 5000,
                            )
                        except (AttributeError, TypeError, OSError):
                            _current_summary = None
                        if not _current_summary:
                            continue
                        for elem in elements:
                            if elem not in _current_summary:
                                _phantom_warnings.setdefault(tid, []).append(
                                    f"{fpath}:{elem}"
                                )
                if _phantom_warnings:
                    logger.warning(
                        "IMPLEMENT Gap 1: phantom element references in %d task(s): %s",
                        len(_phantom_warnings),
                        {tid: refs[:3] for tid, refs in _phantom_warnings.items()},
                    )
                    context["_phantom_element_warnings"] = _phantom_warnings

            chunks, skipped_reports = self._tasks_to_chunks(
                _generation_tasks,
                max_retries=2,
                design_results=design_results,
                calibration_map=calibration_map,
                downstream_map=downstream_map,
                staleness_classification=context.get("scaffold", {}).get(
                    "staleness_classification", {},
                ),
                parameter_sources=context.get("parameter_sources", {}),
                semantic_conventions=context.get("semantic_conventions", {}),
                # PCA-300/301/400: project-level context
                architectural_context=context.get("architectural_context"),
                plan_goals=context.get("plan_goals"),
                plan_context=(context.get("plan_document_text") or "")[:4000] or None,
                service_metadata=context.get("service_metadata"),
                # PCA-401/403/404
                calibration_hints=context.get("onboarding_calibration_hints"),
                prior_impl_summaries=context.get("_prior_impl_summaries"),
                # PCA-501: project identity
                project_name=_project_name,
                project_root_path=str(project_root),
                # PCA-600: edit mode classification
                edit_mode_map=edit_mode_map,
                # AR-822: module inventory from SCAFFOLD
                module_inventory=context.get("scaffold", {}).get("module_inventory"),
                # Scaffold output for skeleton file detection
                scaffold_output=context.get("scaffold", {}),
                # Phase 5: Forward interface contracts
                forward_manifest=context.get("forward_manifest"),
                # Micro Prime pre-pass results
                micro_prime_result=context.get("micro_prime_result"),
            )

            # Phase 4: Enrich chunks with manifest context (IM-1 through IM-4)
            _manifest_registry = None
            if self.config.manifest_consumption_enabled:
                _manifest_registry = self.config.manifest_registry or context.get("project_manifests")
            if _manifest_registry is not None:
                _manifest_budget = self.config.manifest_context_budget
                _enable_introspect = getattr(self.config, "enable_introspect", False)
                for chunk in chunks:
                    _mc_parts = []
                    for tf in getattr(chunk, "target_files", []):
                        summary = _manifest_registry.file_element_summary(
                            tf, _manifest_budget,
                            include_resolved_types=_enable_introspect,  # IM-1: Phase 5
                        )
                        if summary:
                            _mc_parts.append(f"### {tf}\n{summary}")
                    if _mc_parts:
                        chunk.metadata["_manifest_context"] = "\n\n".join(_mc_parts)
                logger.debug(
                    "IMPLEMENT: manifest context injected into %d chunks",
                    sum(1 for c in chunks if c.metadata.get("_manifest_context")),
                )

                # Phase 6: Enrich chunks with call graph context (CG-IM-1,2,3,4)
                _cg_budget = self.config.call_graph_context_budget
                for chunk in chunks:
                    try:
                        _cg_parts: list[str] = []
                        _cg_callers: list[dict[str, Any]] = []
                        for tf in getattr(chunk, "target_files", []):
                            cg_summary = _manifest_registry.call_graph_summary(tf, _cg_budget)
                            if cg_summary:
                                _cg_parts.append(f"### {tf}\n{cg_summary}")
                            callers_map = _manifest_registry.callers_of_file(tf)
                            for fqn, callers in callers_map.items():
                                br = _manifest_registry.blast_radius(fqn, max_depth=self.config.blast_radius_max_depth)
                                _cg_callers.append({
                                    "fqn": fqn,
                                    "direct_callers": sorted(callers),
                                    "blast_radius": len(br),
                                })
                        if _cg_parts:
                            chunk.metadata["_call_graph_context"] = "\n\n".join(_cg_parts)
                        if _cg_callers:
                            chunk.metadata["_call_graph_callers"] = _cg_callers
                    except (AttributeError, TypeError, OSError, KeyError, ValueError):
                        logger.debug(
                            "IMPLEMENT: call graph enrichment failed for chunk %s",
                            getattr(chunk, "chunk_id", "?"), exc_info=True,
                        )
                logger.debug(
                    "IMPLEMENT: call graph context injected into %d chunks",
                    sum(1 for c in chunks if c.metadata.get("_call_graph_context")),
                )
            else:
                logger.info(
                    "manifest.fallback",
                    extra={"surface": "implement_enrichment", "reason": "registry_unavailable" if not self.config.manifest_consumption_enabled else "no_registry"},
                )

            # Gaps 3/4/5: Enrich chunks with handoff improvement data
            _structural_delta = context.get("design_structural_delta", {})
            _mode_evidence = context.get("design_mode_evidence", {})
            _trunc_tier = context.get("manifest_truncation_tier", {})
            _phantom_warns = context.get("_phantom_element_warnings", {})
            for chunk in chunks:
                tid = chunk.chunk_id
                # Gap 3: structural delta for element-level guidance
                if tid in _structural_delta:
                    chunk.metadata["_design_structural_delta"] = _structural_delta[tid]
                # Gap 4: design mode evidence
                if tid in _mode_evidence:
                    chunk.metadata["_design_mode_evidence"] = _mode_evidence[tid]
                # Gap 5: truncation tier per target file
                _chunk_trunc = {}
                for tf in getattr(chunk, "target_files", []):
                    if tf in _trunc_tier:
                        _chunk_trunc[tf] = _trunc_tier[tf]
                if _chunk_trunc:
                    chunk.metadata["_manifest_truncation_tier"] = _chunk_trunc
                # Gap 1: phantom element warnings
                if tid in _phantom_warns:
                    chunk.metadata["_phantom_element_warnings"] = _phantom_warns[tid]

            # CMR: Complexity-Driven Model Router (REQ-CMR-012)
            # Classification runs after Phase 6 call graph enrichment, before
            # executor construction.
            _tier_distribution = {"tier_1": 0, "tier_2": 0, "tier_3": 0}
            if chunks:
                from startd8.contractors.artisan_phases.development import (
                    TaskComplexitySignals,
                    TaskComplexityTier,
                )

                for chunk in chunks:
                    try:
                        if not self.config.complexity_routing_enabled:
                            _set_default_complexity_metadata(chunk, force=True)
                            _tier_distribution["tier_2"] += 1
                            continue

                        signals = _extract_complexity_signals(
                            chunk, _manifest_registry,
                        )
                        override_raw = chunk.metadata.get("complexity_tier_override")
                        if isinstance(override_raw, str):
                            override_norm = override_raw.strip().lower()
                            try:
                                tier = TaskComplexityTier(override_norm)
                                logger.info(
                                    "CMR: chunk=%s using complexity_tier_override=%s",
                                    getattr(chunk, "chunk_id", "?"),
                                    tier.value,
                                )
                            except ValueError:
                                logger.warning(
                                    "CMR: invalid complexity_tier_override=%r for chunk %s; using classifier",
                                    override_raw,
                                    getattr(chunk, "chunk_id", "?"),
                                )
                                tier = _classify_complexity_tier(signals, self.config)
                        else:
                            tier = _classify_complexity_tier(signals, self.config)
                        chunk.metadata["_complexity_tier"] = tier.value
                        chunk.metadata["_complexity_signals"] = signals.to_dict()
                        _tier_distribution[tier.value] += 1
                        logger.info(
                            "CMR: chunk=%s tier=%s blast=%d callers=%d edit=%s loc=%d",
                            getattr(chunk, "chunk_id", "?"),
                            tier.value,
                            signals.blast_radius,
                            signals.caller_count,
                            signals.edit_mode,
                            signals.estimated_loc,
                        )
                    except Exception:
                        # Graceful degradation — default to Tier 2
                        _set_default_complexity_metadata(chunk, force=False)
                        _tier_distribution["tier_2"] += 1
                        logger.warning(
                            "CMR: classification failed for chunk %s, defaulting to tier_2",
                            getattr(chunk, "chunk_id", "?"),
                            exc_info=True,
                        )
                logger.info(
                    "CMR: T1=%d, T2=%d, T3=%d across %d chunks",
                    _tier_distribution["tier_1"],
                    _tier_distribution["tier_2"],
                    _tier_distribution["tier_3"],
                    len(chunks),
                )
            context["_tier_distribution"] = _tier_distribution

            # PCA-402: track onboarding field consumption
            if context.get("service_metadata") is not None:
                _track_onboarding_consumption(context, "service_metadata", "IMPLEMENT")
            if context.get("onboarding_calibration_hints") is not None:
                _track_onboarding_consumption(context, "onboarding_calibration_hints", "IMPLEMENT")
            if context.get("architectural_context"):
                _track_onboarding_consumption(context, "architectural_context", "IMPLEMENT")

            if not chunks:
                logger.warning("IMPLEMENT: no eligible tasks after env pre-filter")
                output = {
                    "task_reports": skipped_reports,
                    "tasks_processed": len(skipped_reports),
                    "domain_breakdown": {},
                    "total_estimated_loc": 0,
                    "total_cost": 0.0,
                    "generation_results": {},
                }
                context["implementation"] = output
                output["metadata"] = self._build_implementation_metadata(context)
                context["generation_results"] = {}
                context["truncation_flags"] = {}

                # Context contract: validate IMPLEMENT output model (no-chunks path)
                ImplementPhaseOutput(
                    implementation=context["implementation"],
                    generation_results=context["generation_results"],
                    truncation_flags=context["truncation_flags"],
                )

                duration = time.monotonic() - start
                return {"output": output, "cost": 0.0, "metadata": {"duration": duration, "resumed": False}}

            # Build executor (inject pre-configured generator if provided)
            # Write to staging_dir so INTEGRATE merges into project_root
            staging_dir = project_root / (self.config.staging_dir or ".startd8/staging")
            staging_dir.mkdir(parents=True, exist_ok=True)
            context["_staging_dir"] = str(staging_dir)

            executor = ArtisanChunkExecutor(
                drafter_spec=self.config.drafter_agent,
                refiner_spec=(
                    self.config.tier2_agent
                    if not self.config.skip_refinement
                    else None
                ),
                tier3_drafter_spec=(
                    self.config.tier3_agent
                    if self.config.complexity_routing_enabled
                    else None
                ),
                tier2_gate_escalation=self.config.complexity_tier2_gate_escalation,
                output_dir=staging_dir,
                max_tokens=self.config.max_tokens,
                project_root=project_root,
            )

            # Cooperative cancellation token — set on timeout to signal
            # the background thread to stop initiating new LLM calls.
            cancel_event = threading.Event()

            # Build plan
            plan = DevelopmentPlan(
                plan_id=f"artisan-implement-{int(time.time())}",
                chunks=chunks,
                config={
                    "dry_run": False,
                    "walkthrough": self.config.walkthrough,
                    "state_dir": str(project_root / ".startd8" / "state"),
                    "cancel_event": cancel_event,
                    "example_artifacts": context.get("example_artifacts", {}),
                },
            )

            # Build phase with test runner (no shell test commands — tests are
            # handled by DomainChecklist and the TEST phase handler)
            state_store = JsonFileStateStore(
                directory=str(project_root / ".startd8" / "state"),
            )
            # --- WCP-006: Wire DomainChecklist to DevelopmentPhase ---
            domain_checklist = None
            enriched_seed_path = (
                self._enriched_seed_path
                or context.get("enriched_seed_path")
            )
            if enriched_seed_path:
                try:
                    from startd8.contractors.artisan_phases.domain_checklist import DomainChecklist
                    domain_checklist = DomainChecklist(
                        project_root=project_root,
                        enriched_seed_path=Path(enriched_seed_path),
                    )
                    logger.info(
                        "IMPLEMENT: DomainChecklist configured (seed=%s)",
                        enriched_seed_path,
                    )
                except Exception as e:
                    logger.warning(
                        "IMPLEMENT: DomainChecklist init failed (non-fatal): %s", e,
                    )

            dev_phase = DevelopmentPhase(
                executor=executor,
                test_runner=DefaultTestRunner(),
                state_store=state_store,
                max_parallel=4,
                domain_checklist=domain_checklist,
            )

            # Bridge sync → async
            logger.info(
                "IMPLEMENT: delegating %d chunks to DevelopmentPhase (plan=%s)",
                len(chunks), plan.plan_id,
            )
            dev_result = self._run_development_phase(
                dev_phase, plan,
                timeout=self.config.development_timeout_seconds,
                cancel_event=cancel_event,
            )

            if dev_result is None or not hasattr(dev_result, "chunk_states"):
                raise RuntimeError(
                    "DevelopmentPhase returned an invalid result "
                    f"(type={type(dev_result).__name__}). "
                    "Expected DevelopmentResult with chunk_states attribute."
                )

            mp_result = context.get("micro_prime_result")
            if mp_result:
                logger.info(
                    "IMPLEMENT: Micro Prime savings — %d local ($0), %d escalated to cloud",
                    (mp_result.get("metrics") or {}).get("local_success_count", 0),
                    len(mp_result.get("escalated_elements") or []),
                )

            # Map results back to downstream contract
            output, generation_results, total_cost = self._map_development_result(
                dev_result, chunks, tasks, skipped_reports,
            )

            # ── All-tasks-failed guard ────────────────────────────────
            # When chunks were dispatched but zero generation results came
            # back, every task failed (e.g. API overloaded, auth error).
            # Raise so the orchestrator marks the phase FAILED instead of
            # silently passing empty results to INTEGRATE/TEST/REVIEW.
            if chunks and not generation_results and not self.config.walkthrough:
                failed_reports = [
                    r for r in output.get("task_reports", [])
                    if r.get("status") == "generation_failed"
                ]
                error_details = "; ".join(
                    f"{r['task_id']}: {r.get('error', 'unknown')}"
                    for r in failed_reports[:3]
                )
                raise RuntimeError(
                    f"IMPLEMENT: all {len(chunks)} task(s) failed generation. "
                    f"No code was produced. Details: {error_details or 'no error details'}"
                )

            # ── Gate 3: post-IMPLEMENT multi-file split validation ────
            # Per defense-in-depth Principle 1 (validate at every
            # boundary): verify that every multi-file task actually
            # produced all its target files.  This is the last gate
            # before output is accepted.
            gate3 = self._validate_generation_completeness(
                tasks, generation_results, project_root,
                downstream_map=downstream_map,
            )
            if gate3:
                output["_gate3_validation"] = gate3

            # ── Gate 3b: post-IMPLEMENT semantic content validation ──
            # Runs 5 self-consistency validators (AR-143–AR-147) to
            # catch placeholder literals, undeclared imports, proto
            # field mismatches, protocol fidelity issues, and
            # Dockerfile coherence problems.  Advisory in v1.
            _svc_meta = context.get("service_metadata")
            gate3b = self._validate_generation_content(
                tasks, generation_results, project_root,
                service_metadata=_svc_meta,
            )
            if gate3b:
                output["_gate3b_content_validation"] = gate3b
                flagged_ids = sorted(gate3b.keys())
                total_issues = sum(len(v) for v in gate3b.values())
                logger.warning(
                    "Gate 3b: %d task(s) with %d content issue(s): %s",
                    len(flagged_ids), total_issues, flagged_ids,
                )
            else:
                logger.info(
                    "Gate 3b: no content issues across %d task(s)",
                    len(generation_results),
                )

            # ── PCA-603: Build existing file sizes for Gate 4 size regression ──
            # Uses _existing_file_contents populated by PCA-502 disk reads.
            # PCA-603 AC 6: When edit-mode file has no cached content,
            # attempt fresh disk read as fallback before skipping.
            existing_file_sizes: dict[str, dict[str, int]] = {}
            for chunk in chunks:
                _efc = chunk.metadata.get("_existing_file_contents", {})
                _edit_mode_dict = chunk.metadata.get("_edit_mode")
                task_sizes: dict[str, int] = {}

                if _efc:
                    for epath, econtent in _efc.items():
                        task_sizes[epath] = len(econtent.splitlines())

                # Fallback: check for edit-mode files missing from cache
                if _edit_mode_dict and _edit_mode_dict.get("mode") == "edit":
                    per_file_modes = _edit_mode_dict.get("per_file", {})
                    for fpath, finfo in per_file_modes.items():
                        if finfo.get("mode") == "edit" and fpath not in task_sizes:
                            logger.warning(
                                "Edit-mode file %s has no cached content for "
                                "size regression check — attempting fresh disk "
                                "read as fallback.",
                                fpath,
                            )
                            try:
                                fallback_path = project_root / fpath
                                fallback_content = fallback_path.read_text(
                                    encoding="utf-8",
                                )
                                task_sizes[fpath] = len(
                                    fallback_content.splitlines(),
                                )
                            except (OSError, UnicodeDecodeError) as exc:
                                logger.warning(
                                    "Edit-mode file %s: fallback disk read "
                                    "failed (%s) — size regression guard "
                                    "bypassed for this file.",
                                    fpath, exc,
                                )

                if task_sizes:
                    existing_file_sizes[chunk.chunk_id] = task_sizes

            # ── Gate 4: post-IMPLEMENT truncation detection ─────────
            # Per Context Correctness by Construction: detect truncated
            # or syntactically broken generated files BEFORE they
            # propagate to TEST/REVIEW/FINALIZE.
            truncation_flags = self._validate_truncation(
                tasks, generation_results, project_root,
                existing_file_sizes=existing_file_sizes,
            )
            if truncation_flags:
                output["_gate4_truncation"] = truncation_flags
                flagged_ids = sorted(truncation_flags.keys())
                logger.warning(
                    "Gate 4: %d task(s) flagged for truncation: %s",
                    len(flagged_ids), flagged_ids,
                )
            else:
                logger.info(
                    "Gate 4: no truncation detected across %d task(s)",
                    len(generation_results),
                )

            # ── Gate 5: Edit-First Enforcement (REQ-EFE-020) ─────────
            from startd8.contractors.edit_first_gate import (
                validate_task_size_regression,
                resolve_threshold,
                emit_rejection_telemetry,
                build_edit_retry_prompt,
            )
            from startd8.utils.code_extraction import extract_code_from_response

            gate5_results: dict[str, Any] = {}
            _output_contracts = context.get("onboarding_output_contracts")
            _schema_features = context.get("onboarding_schema_features")

            for task in tasks:
                gr = generation_results.get(task.task_id)
                if gr is None or not gr.success:
                    continue

                # Get existing content from chunk metadata
                chunk_efc: dict[str, str] = {}
                for chunk in chunks:
                    if chunk.chunk_id == task.task_id:
                        chunk_efc = chunk.metadata.get(
                            "_existing_file_contents", {},
                        )
                        break

                if not chunk_efc:
                    continue  # New-file task — no size regression possible

                # Read generated file content from staging
                gen_file_contents: dict[str, str] = {}
                for gen_path in gr.generated_files:
                    fp = Path(gen_path)
                    if fp.exists():
                        try:
                            rel_key = str(fp.relative_to(staging_dir))
                        except ValueError:
                            # Fallback: use full path string to avoid
                            # name-only collisions across directories.
                            rel_key = str(fp)
                        try:
                            gen_file_contents[rel_key] = fp.read_text(
                                encoding="utf-8",
                            )
                        except (OSError, UnicodeDecodeError) as read_exc:
                            logger.debug(
                                "Gate 5: skipping unreadable generated file %s: %s",
                                fp, read_exc,
                            )

                if not gen_file_contents:
                    continue

                # Resolve threshold for this task's artifact types
                artifact_types = [
                    task.artifact_type
                ] if hasattr(task, "artifact_type") and task.artifact_type else ["source_code"]
                threshold = resolve_threshold(
                    artifact_types=artifact_types,
                    output_contracts=_output_contracts,
                    schema_features=_schema_features,
                )

                gate_result = validate_task_size_regression(
                    task_id=task.task_id,
                    generated_files=gen_file_contents,
                    existing_contents=chunk_efc,
                    threshold=threshold,
                    artifact_type=artifact_types[0] if artifact_types else "unknown",
                    force_rewrite=self.config.force_rewrite,
                )

                if gate_result.any_rejected:
                    # Emit telemetry for initial rejection
                    try:
                        from opentelemetry import trace as _g5_trace
                        _g5_span = _g5_trace.get_current_span()
                        emit_rejection_telemetry(gate_result, _g5_span)
                    except (ImportError, TypeError, AttributeError, RuntimeError, NameError):
                        logger.debug("Auto-lint import failed", exc_info=True)

                    # REQ-EFE-023: single retry with edit-focused prompt
                    retry_succeeded = self._attempt_edit_first_retry(
                        task, gate_result, chunk_efc, context,
                        gr, executor, staging_dir, threshold,
                        extract_code_from_response,
                    )

                    # Re-evaluate after retry
                    still_rejected = any(
                        f.action == "rejected" for f in gate_result.file_results
                    )
                    gate_result.any_rejected = still_rejected
                    gate_result.retry_succeeded = retry_succeeded and not still_rejected
                    if still_rejected:
                        # Emit telemetry for post-retry rejection
                        try:
                            from opentelemetry import trace as _g5_trace2
                            _g5_span2 = _g5_trace2.get_current_span()
                            emit_rejection_telemetry(gate_result, _g5_span2)
                        except (ImportError, TypeError, AttributeError, RuntimeError, NameError):
                            logger.debug("Auto-lint import failed", exc_info=True)

                gate5_results[task.task_id] = {
                    "any_rejected": gate_result.any_rejected,
                    "retry_needed": gate_result.retry_needed,
                    "retry_succeeded": gate_result.retry_succeeded,
                    "file_results": [
                        {
                            "file_path": fr.file_path,
                            "input_chars": fr.input_chars,
                            "output_chars": fr.output_chars,
                            "ratio": round(fr.ratio, 2),
                            "threshold": fr.threshold,
                            "artifact_type": fr.artifact_type,
                            "passed": fr.passed,
                            "action": fr.action,
                        }
                        for fr in gate_result.file_results
                    ],
                }

            if gate5_results:
                rejected_count = sum(
                    1 for r in gate5_results.values() if r["any_rejected"]
                )
                if rejected_count:
                    output["_gate5_edit_first"] = gate5_results
                    logger.warning(
                        "Gate 5: %d task(s) with edit-first size regression: %s",
                        rejected_count,
                        sorted(
                            tid for tid, r in gate5_results.items()
                            if r["any_rejected"]
                        ),
                    )
                else:
                    logger.info(
                        "Gate 5: edit-first gate passed for %d task(s)",
                        len(gate5_results),
                    )
            else:
                logger.info(
                    "Gate 5: no existing-file tasks to check (all new files)"
                )

            context["edit_first_gate_results"] = gate5_results

            # Persist generation_results to disk for crash recovery (v2 envelope)
            # Always write to the canonical .startd8/state/ location.
            # Skip when no explicit project_root (matches REVIEW's pattern).
            if not _has_explicit_project_root:
                logger.info("IMPLEMENT: no explicit project_root — skipping cache save")
            else:
                try:
                    save_path = project_root / ".startd8" / "state" / "generation_results.json"
                    serializable_tasks = {}
                    for tid, gr in generation_results.items():
                        content_hashes: dict[str, str] = {}
                        for p in gr.generated_files:
                            fp = Path(p)
                            if fp.exists():
                                content_hashes[str(p)] = hashlib.sha256(
                                    fp.read_bytes()
                                ).hexdigest()
                        serializable_tasks[tid] = {
                            "success": gr.success,
                            "generated_files": [str(p) for p in gr.generated_files],
                            "content_hashes": content_hashes,
                            "error": gr.error,
                            "input_tokens": gr.input_tokens,
                            "output_tokens": gr.output_tokens,
                            "cost_usd": gr.cost_usd,
                            "iterations": gr.iterations,
                            "model": gr.model,
                        }
                    # Persist downstream_map so REVIEW can restore it on resume
                    cache_envelope: dict[str, Any] = {
                        "_cache_meta": {
                            "schema_version": _CACHE_SCHEMA_VERSION,
                            "created_at": datetime.datetime.now(
                                datetime.timezone.utc
                            ).isoformat(),
                            "source_checksum": context.get("source_checksum"),
                            "design_hash": _compute_design_results_hash(
                                context.get("design_results", {})
                            ),
                        },
                        "downstream_map": downstream_map,
                        "truncation_flags": truncation_flags,
                        "edit_first_gate_results": gate5_results,
                        "tasks": serializable_tasks,
                    }
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    atomic_write_json(save_path, cache_envelope, indent=2)
                    logger.info(
                        "IMPLEMENT: saved %d generation results (v2) to %s",
                        len(generation_results), save_path,
                    )
                except Exception as exc:
                    logger.warning(
                        "IMPLEMENT: failed to write cache: %s (non-fatal)",
                        exc, exc_info=True,
                    )

        # NOTE: Auto-commit moved to INTEGRATE phase.
        # The IMPLEMENT phase now writes to staging_dir; INTEGRATE merges
        # into project_root and commits if auto_commit is enabled.

        # AR-153 scoped retry: merge cached passing-task results back in
        # so INTEGRATE/TEST/REVIEW see the full set of generation results.
        if _retry_cached:
            _merged_count = 0
            for _cached_tid, _cached_gr in _retry_cached.items():
                if _cached_tid not in generation_results:
                    generation_results[_cached_tid] = _cached_gr
                    _merged_count += 1
            if _merged_count:
                logger.info(
                    "IMPLEMENT: AR-153 merged %d cached passing-task "
                    "result(s) into generation_results",
                    _merged_count,
                )

        context["implementation"] = output
        output["metadata"] = self._build_implementation_metadata(context)
        # C-2 fix: normalize any dict entries to GenerationResult so downstream
        # phases can safely access .cost_usd / .success without AttributeError.
        generation_results = {
            tid: _dict_to_gen_result(v) if isinstance(v, dict) else v
            for tid, v in generation_results.items()
        }
        context["generation_results"] = generation_results
        context["truncation_flags"] = truncation_flags

        # PCA-403: accumulate prior implementation summaries for cross-feature context
        prior_summaries = context.get("_prior_impl_summaries", [])
        for task_id, gen_result in generation_results.items():
            if hasattr(gen_result, "success") and gen_result.success:
                files = [str(p) for p in (gen_result.generated_files or [])[:5]] if hasattr(gen_result, "generated_files") and gen_result.generated_files else []
                prior_summaries.append({"task_id": task_id, "files": files})
        context["_prior_impl_summaries"] = prior_summaries[-3:]
        # Propagate downstream_map to REVIEW phase so it can distinguish
        # expected downstream stubs from generation failures.
        if downstream_map:
            context["_downstream_map"] = downstream_map

        # Context contract: validate IMPLEMENT output model (normal path)
        ImplementPhaseOutput(
            implementation=context["implementation"],
            generation_results=context["generation_results"],
            truncation_flags=context["truncation_flags"],
        )

        duration = time.monotonic() - start

        logger.info(
            "IMPLEMENT phase complete: %d tasks, %d passed, $%.4f cost (%.2fs)",
            len(tasks),
            sum(1 for r in generation_results.values() if r.success),
            total_cost,
            duration,
        )

        # Fix 5: Include resumed flag in metadata so orchestrator can
        # distinguish cached from fresh phases.
        metadata: dict[str, Any] = {"duration": duration, "resumed": resumed}
        if resumed:
            metadata["resumed_cost"] = resumed_cost  # type: ignore[possibly-undefined]

        return {"output": output, "cost": total_cost, "metadata": metadata}

    def _attempt_edit_first_retry(
        self,
        task: SeedTask,
        gate_result: Any,
        chunk_efc: dict[str, str],
        context: dict[str, Any],
        gr: GenerationResult,
        executor: Any,
        staging_dir: Path,
        threshold: float,
        extract_code_fn: Any,
    ) -> bool:
        """Attempt a single edit-focused retry for each rejected file (REQ-EFE-023).

        Returns True if at least one file was successfully retried.
        """
        from startd8.contractors.edit_first_gate import build_edit_retry_prompt

        # Guard: executor must expose a usable drafter agent
        if not (
            hasattr(executor, "agent")
            and executor.agent is not None
            and hasattr(executor.agent, "generate")
        ):
            logger.debug(
                "Gate 5: executor has no usable agent for retry — skipping "
                "edit-first retry for %s", task.task_id,
            )
            return False

        retry_succeeded = False
        for fr in gate_result.file_results:
            if fr.action != "rejected":
                continue

            existing_content = chunk_efc.get(fr.file_path, "")
            design_doc = (
                context.get("design_results", {})
                .get(task.task_id, {})
                .get("design_document", "")
            )
            retry_prompt = build_edit_retry_prompt(
                original_content=existing_content,
                design_doc=design_doc,
                task_description=getattr(task, "description", str(task.task_id)),
                ratio=fr.ratio,
                threshold=fr.threshold,
            )
            logger.info(
                "Gate 5: retrying %s file %s with edit-focused prompt "
                "(ratio=%.1f%% < threshold=%.1f%%)",
                task.task_id, fr.file_path, fr.ratio, fr.threshold,
            )

            try:
                retry_response = executor.agent.generate(retry_prompt)
                retry_text = (
                    retry_response.text
                    if hasattr(retry_response, "text")
                    else str(retry_response)
                )
                retry_code = extract_code_fn(retry_text)

                min_chars = len(existing_content) * (threshold / 100.0)
                if not retry_code or len(retry_code) < min_chars:
                    logger.warning(
                        "Gate 5: retry for %s file %s still below threshold",
                        task.task_id, fr.file_path,
                    )
                    continue

                # Write retry result to staging
                for gen_path in gr.generated_files:
                    gfp = Path(gen_path)
                    try:
                        rel = str(gfp.relative_to(staging_dir))
                    except ValueError:
                        # Fallback: use full path string to avoid
                        # name-only collisions across directories.
                        rel = str(gfp)
                    if rel == fr.file_path and gfp.exists():
                        gfp.write_text(retry_code, encoding="utf-8")
                        fr.output_chars = len(retry_code)
                        new_ratio = (
                            (len(retry_code) / fr.input_chars) * 100.0
                            if fr.input_chars > 0
                            else 100.0
                        )
                        fr.ratio = new_ratio
                        fr.passed = True
                        fr.action = "passed"
                        retry_succeeded = True
                        logger.info(
                            "Gate 5: retry succeeded for %s file %s "
                            "(new ratio=%.1f%%)",
                            task.task_id, fr.file_path, fr.ratio,
                        )
                        break
            except (OSError, RuntimeError, ValueError, Startd8Error) as retry_exc:
                logger.warning(
                    "Gate 5: retry failed for %s file %s: %s",
                    task.task_id, fr.file_path, retry_exc,
                    exc_info=True,
                )

        return retry_succeeded

    def _commit_features(
        self,
        generation_results: dict[str, GenerationResult],
        tasks: list[SeedTask],
        project_root: Path,
    ) -> None:
        """Commit each successful feature's generated files to git individually.

        Produces one commit per task, mirroring the PrimeContractor pattern.
        Failures are logged as warnings but do not abort the workflow.
        """
        task_map = {t.task_id: t for t in tasks}
        for task_id, gr in generation_results.items():
            if not gr.success or not gr.generated_files:
                continue
            task = task_map.get(task_id)
            title = task.title if task else task_id
            staged_files: list[str] = []
            for fpath in gr.generated_files:
                add_result = subprocess.run(
                    ["git", "add", str(fpath)],
                    cwd=project_root,
                    capture_output=True,
                    timeout=30,
                )
                if add_result.returncode != 0:
                    stderr = getattr(add_result, "stderr", b"")
                    if isinstance(stderr, bytes):
                        stderr = stderr.decode("utf-8", errors="replace")
                    logger.warning(
                        "git add failed for %s (task %s): %s",
                        fpath,
                        task_id,
                        stderr.strip(),
                    )
                else:
                    staged_files.append(str(fpath))
            if not staged_files:
                logger.warning(
                    "Skipping commit for %s: all git-add calls failed",
                    task_id,
                )
                continue
            msg = (
                f"feat({task_id}): {title}\n\n"
                "Generated by Artisan IMPLEMENT phase"
            )
            # Commit only the specific generated files to avoid capturing
            # unrelated staged changes from the user's working tree.
            files_to_commit = staged_files
            result = subprocess.run(
                ["git", "commit", "-m", msg, "--"] + files_to_commit,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                logger.info("Committed %s: %s", task_id, title)
            else:
                logger.warning(
                    "Commit failed for %s: %s",
                    task_id,
                    result.stderr.strip(),
                )


# ============================================================================
# INTEGRATE phase — merge staged files into project_root
# ============================================================================


class SeedTaskUnit:
    """Mottainai-compliant adapter: SeedTask + GenerationResult → IntegrationUnit.

    Forwards ALL SeedTask fields via ``dataclasses.asdict()`` in ``context``,
    plus generation metadata (_generation key).
    """

    __slots__ = ("_task", "_gen", "_edit_mode", "_extra_context")

    def __init__(
        self,
        task: SeedTask,
        gen_result: GenerationResult,
        edit_mode: dict[str, Any] | None = None,
        extra_context: dict[str, Any] | None = None,
    ) -> None:
        self._task = task
        self._gen = gen_result
        self._edit_mode = edit_mode
        self._extra_context = extra_context or {}

    @property
    def id(self) -> str:
        return self._task.task_id

    @property
    def name(self) -> str:
        return self._task.title

    @property
    def generated_files(self) -> list[str]:
        return [str(f) for f in self._gen.generated_files]

    @property
    def target_files(self) -> list[str]:
        return self._task.target_files

    @property
    def context(self) -> dict[str, Any]:
        from dataclasses import asdict
        ctx = asdict(self._task)
        ctx["_generation"] = {
            "model": self._gen.model,
            "cost_usd": self._gen.cost_usd,
            "iterations": self._gen.iterations,
            "input_tokens": self._gen.input_tokens,
            "output_tokens": self._gen.output_tokens,
        }
        if self._edit_mode is not None:
            ctx["_edit_mode"] = self._edit_mode
        if self._extra_context:
            ctx.update(self._extra_context)
        return ctx


class ArtisanIntegrationListener:
    """Logs integration events at INFO/WARNING level per existing patterns."""

    def __init__(self, task_id: str) -> None:
        self._task_id = task_id

    def on_integration_started(self, unit: Any) -> None:
        logger.info(
            "INTEGRATE: started for task %s (%s)",
            self._task_id, unit.name,
        )

    def on_file_integrated(self, unit: Any, source: Path, target: Path) -> None:
        logger.info(
            "INTEGRATE: merged %s → %s",
            source.name, target,
            extra={"task_id": self._task_id},
        )

    def on_checkpoint_result(self, unit: Any, result: Any) -> None:
        pass  # gate emission handled inside engine

    def on_integration_failed(self, unit: Any, error: str) -> None:
        logger.warning(
            "INTEGRATE: task %s failed: %s",
            self._task_id, error,
            extra={"task_id": self._task_id},
        )

    def on_integration_completed(self, unit: Any, files: list[Path]) -> None:
        logger.info(
            "INTEGRATE: task %s completed (%d files)",
            self._task_id, len(files),
            extra={"task_id": self._task_id},
        )


class OTelIntegrationListener:
    """Wraps ``ArtisanIntegrationListener`` with OTel span events (E5).

    Enriches the per-task integration span via the existing
    ``IntegrationListener`` callback protocol.  Calls
    ``_task_span.add_event()`` which is a no-op on ``_NoOpSpan``,
    so no ``_HAS_OTEL`` guards are needed.
    """

    def __init__(
        self,
        task_id: str,
        task_span: Any,
        wrapped: Any | None = None,
    ) -> None:
        self._task_id = task_id
        self._task_span = task_span
        self._wrapped = wrapped or ArtisanIntegrationListener(task_id)
        self._file_count = 0
        self._checkpoint_count = 0

    def on_integration_started(self, unit: Any) -> None:
        self._wrapped.on_integration_started(unit)
        self._task_span.add_event(
            "integration.started",
            attributes={
                "integration.task_id": self._task_id,
                "integration.file_count": len(
                    getattr(unit, "generated_files", [])
                ),
            },
        )

    def on_file_integrated(self, unit: Any, source: Path, target: Path) -> None:
        self._wrapped.on_file_integrated(unit, source, target)
        self._file_count += 1
        self._task_span.add_event(
            "integration.file.merged",
            attributes={
                "file.source": source.name,
                "file.target": str(target),
                "file.sequence": self._file_count,
            },
        )

    def on_checkpoint_result(self, unit: Any, result: Any) -> None:
        self._wrapped.on_checkpoint_result(unit, result)
        self._checkpoint_count += 1
        _name = getattr(result, "name", "unknown")
        _status = getattr(result, "status", None)
        _status_str = _status.value if hasattr(_status, "value") else str(_status)
        attrs: dict[str, Any] = {
            "checkpoint.name": _name,
            "checkpoint.status": _status_str,
            "checkpoint.sequence": self._checkpoint_count,
        }
        _errors = getattr(result, "errors", None)
        if _errors:
            attrs["checkpoint.error_count"] = len(_errors)
        self._task_span.add_event("integration.checkpoint", attributes=attrs)

    def on_integration_failed(self, unit: Any, error: str) -> None:
        self._wrapped.on_integration_failed(unit, error)
        self._task_span.add_event(
            "integration.failed",
            attributes={"error.message": str(error)[:500]},
        )

    def on_integration_completed(self, unit: Any, files: list[Path]) -> None:
        self._wrapped.on_integration_completed(unit, files)
        self._task_span.add_event(
            "integration.completed",
            attributes={"files.merged_count": len(files)},
        )


class IntegratePhaseHandler(AbstractPhaseHandler):
    """INTEGRATE phase: merge staged files into project_root with validation.

    Reads ``generation_results`` from context (populated by IMPLEMENT),
    runs each task through IntegrationEngine, and writes
    ``integration_results`` back to context.

    Files are merged from ``_staging_dir`` (or ``.startd8/staging/``)
    into the project root.  Auto-commit (if enabled) happens here,
    not in IMPLEMENT.
    """

    def __init__(self, config: Optional[HandlerConfig] = None) -> None:
        self.config = config or HandlerConfig()

    def execute(
        self,
        phase: WorkflowPhase,
        context: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        import shutil as _shutil
        from startd8.contractors.checkpoint import IntegrationCheckpoint
        from startd8.contractors.integration_engine import IntegrationEngine
        from startd8.contractors.registry import get_registry

        start = time.monotonic()
        _log_context_completeness("INTEGRATE", context)
        project_root = Path(context.get("project_root", ".")).resolve()
        staging_dir = Path(
            context.get("_staging_dir", str(project_root / ".startd8/staging"))
        )
        tasks = _ensure_context_loaded(context)
        generation_results: dict[str, GenerationResult] = context.get(
            "generation_results", {},
        )
        task_map = {t.task_id: t for t in tasks}
        truncation_flags: dict[str, Any] = context.get("truncation_flags", {})

        # Build engine
        registry = get_registry()
        registry.discover()
        merge_strategy = registry.get_default_merge_strategy(for_python=True)()

        engine = IntegrationEngine(
            project_root=project_root,
            merge_strategy=merge_strategy,
            checkpoint=IntegrationCheckpoint(
                project_root=project_root, run_tests=False,
            ),
            dry_run=dry_run,
            auto_commit=False,  # Workflow commits once at FINALIZE
            allow_dirty=False,
            check_truncation=self.config.check_truncation,
        )
        # R2-O6: Thread manifest_registry from orchestrator context so
        # INTEGRATE can use manifest data for validation/conflict detection.
        engine.manifest_registry = context.get("project_manifests")

        # Capture original generated file paths before integration overwrites them
        _original_gen_files: dict[str, list[str]] = {}
        for task_id, gr in generation_results.items():
            if gr.success:
                _original_gen_files[task_id] = [str(f) for f in gr.generated_files]

        # Integrate each task
        integration_results: dict[str, dict[str, Any]] = {}
        for task_id, gr in generation_results.items():
            if not gr.success:
                continue
            task = task_map.get(task_id)
            if not task:
                logger.warning(
                    "INTEGRATE: task %s has generation_results but is not in task_map "
                    "— skipping integration (task may have been removed from seed)",
                    task_id,
                )
                continue
            _log_task_boundary_start(task, phase="integrate")

            _links = _build_provenance_links(task_id, context, ["design", "implement"])
            with _phase_tracer.start_as_current_span(
                f"task.{task_id}",
                attributes={
                    "task.id": task_id,
                    "task.phase": "integrate",
                },
                links=_links,
            ) as _int_span:
                # AR-816: Skip integration for truncation-blocked tasks
                _task_trunc = truncation_flags.get(task_id, {})
                if _task_trunc.get("truncation_blocked"):
                    integration_results[task_id] = {
                        "success": False,
                        "integrated_files": [],
                        "errors": [
                            f"Truncation blocked (confidence="
                            f"{_task_trunc.get('max_confidence', 0):.2f})"
                        ],
                        "warnings": [],
                        "rollback_performed": False,
                        "skipped_files": [
                            {"path": str(f), "reason": "truncation_blocked"}
                            for f in gr.generated_files
                        ],
                        "status": "BLOCKED",
                    }
                    _int_span.set_attribute("task.truncation_blocked", True)
                    _int_span.set_attribute(
                        "truncation.confidence",
                        _task_trunc.get("max_confidence", 0),
                    )
                    _int_span.add_event(
                        "truncation.rejection",
                        attributes={
                            "truncation.confidence": _task_trunc.get("max_confidence", 0),
                            "truncation.action": "rejected",
                            "truncation.source": _task_trunc.get("source", "unknown"),
                        },
                    )
                    _log_task_boundary_complete(
                        task_id,
                        status="BLOCKED",
                        phase="integrate",
                    )
                    continue

                # Pass edit mode classification so the integration engine
                # can skip merge strategy for edit-mode tasks (the staging
                # file IS the complete file after search/replace).
                _edit_classifications = context.get(
                    "edit_mode_classifications", {},
                )
                _task_edit_mode = _edit_classifications.get(task_id)
                # AR-818/AR-823: Thread truncation and module inventory into unit context
                _unit_extra: dict[str, Any] = {}
                if _task_trunc:
                    _unit_extra["_truncation_flags"] = _task_trunc
                _scaffold = context.get("scaffold", {})
                _module_inv = _scaffold.get("module_inventory", [])
                if _module_inv:
                    _unit_extra["module_inventory"] = _module_inv
                unit = SeedTaskUnit(
                    task, gr, edit_mode=_task_edit_mode,
                    extra_context=_unit_extra if _unit_extra else None,
                )
                listener = OTelIntegrationListener(
                    task_id=task_id,
                    task_span=_int_span,
                    wrapped=ArtisanIntegrationListener(task_id),
                )
                result = engine.integrate(unit, listener=listener)
                integration_results[task_id] = {
                    "success": result.success,
                    "integrated_files": [str(f) for f in result.integrated_files],
                    "errors": result.errors,
                    "warnings": result.warnings,
                    "rollback_performed": result.rollback_performed,
                    "skipped_files": result.skipped_files,
                    "status": result.status.value if hasattr(result.status, "value") else str(result.status),
                }
                _int_span.set_attribute("task.success", result.success)
                _int_span.set_attribute(
                    "integration.status",
                    result.status.value if hasattr(result.status, "value") else str(result.status),
                )
                _int_span.set_attribute("integration.files_merged", len(result.integrated_files))
                _int_span.set_attribute("integration.error_count", len(result.errors))
                _int_span.set_attribute("integration.warning_count", len(result.warnings))
                _int_span.set_attribute("integration.rollback", result.rollback_performed)
                _int_span.set_attribute("integration.skipped_count", len(result.skipped_files))

                # AR-825: Import validation OTel span attributes
                _import_skipped = [
                    s for s in result.skipped_files
                    if isinstance(s, dict) and s.get("reason") == "unresolved_imports"
                ]
                _unresolved_modules: list[str] = []
                for s in _import_skipped:
                    _unresolved_modules.extend(s.get("unresolved", []))
                _int_span.set_attribute(
                    "task.import_validation.unresolved_count", len(_unresolved_modules),
                )
                _int_span.set_attribute(
                    "task.import_validation.unresolved_modules",
                    ", ".join(_unresolved_modules) if _unresolved_modules else "",
                )

                _sc = _capture_task_span_context(_int_span)
                if _sc:
                    integration_results[task_id]["_span_context"] = _sc
                _log_task_boundary_complete(
                    task_id,
                    status=str(integration_results[task_id].get("status", "unknown")),
                    phase="integrate",
                )

                # Update generation_results paths: staging → project_root
                if result.success:
                    gr.generated_files = [Path(f) for f in result.integrated_files]

        # ── Reconcile expected vs merged files ─────────────────────
        # Detect files that IMPLEMENT generated but INTEGRATE didn't
        # merge (silent file loss). This catches the gap where a
        # multi-file generation produces N files but only N-1 appear
        # in the merged output.
        _total_missing = 0
        for task_id, gr in generation_results.items():
            if not gr.success:
                continue
            ir = integration_results.get(task_id, {})
            if ir.get("status") == "BLOCKED":
                continue

            integrated = {str(Path(f)) for f in ir.get("integrated_files", [])}
            expected = set(_original_gen_files.get(task_id, []))

            # Also count skipped files as "accounted for"
            skipped_paths = ir.get("skipped_files", [])
            for sf in skipped_paths:
                if isinstance(sf, dict):
                    sp = sf.get("path", "")
                    if sp:
                        integrated.add(str(Path(sp)))
                elif isinstance(sf, str):
                    integrated.add(str(Path(sf)))

            missing = expected - integrated
            if missing:
                _total_missing += len(missing)
                ir["_missing_files"] = sorted(missing)
                logger.warning(
                    "INTEGRATE: task %s — %d file(s) generated but not merged: %s",
                    task_id,
                    len(missing),
                    sorted(missing),
                )

        if _total_missing:
            logger.error(
                "INTEGRATE: %d file(s) lost during merge across all tasks "
                "— check integration warnings above",
                _total_missing,
            )

        # R2-O1: Before cleaning staging, update generated_files for tasks
        # whose integration failed or was blocked — their staging paths are
        # about to be deleted, so downstream phases must not reference them.
        for task_id, gr in generation_results.items():
            if not gr.success:
                continue
            ir = integration_results.get(task_id, {})
            if not ir:
                # Task had no integration attempt — clear staging paths
                gr.generated_files = []
            elif not ir.get("success", False):
                # Integration failed or blocked — staging paths are stale
                gr.generated_files = []

        # Clean staging dir
        if staging_dir.exists() and not dry_run:
            _shutil.rmtree(staging_dir, ignore_errors=True)

        # C-4: Guard against silent empty integration_results when
        # generation_results has successful entries.  This catches the
        # scenario where a cache load failure causes generation_results
        # to be empty (or mismatched) — FINALIZE would otherwise see
        # every task as "failed integration" without any warning.
        _successful_gen = sum(
            1 for gr in generation_results.values() if gr.success
        )
        if _successful_gen > 0 and not integration_results:
            logger.warning(
                "INTEGRATE: generation_results has %d successful "
                "entry(ies) but integration_results is empty — "
                "a fresh integration pass will be performed on retry. "
                "Cached integration results could not be loaded.",
                _successful_gen,
            )
        elif not generation_results and not integration_results:
            logger.warning(
                "INTEGRATE: generation_results is empty — "
                "cached generation results could not be loaded; "
                "a fresh integration pass will be required after "
                "re-running IMPLEMENT.",
            )

        # Log skipped files summary for visibility
        skipped_total = sum(
            len(r.get("skipped_files", [])) for r in integration_results.values()
        )
        if skipped_total:
            skipped_tasks = sum(
                1 for r in integration_results.values() if r.get("skipped_files")
            )
            logger.error(
                "INTEGRATE: %d file(s) skipped due to size regression "
                "across %d task(s)",
                skipped_total,
                skipped_tasks,
            )

        # Validate output structure before writing to context.
        # In "block" quality gate mode, validation failure is fatal.
        from startd8.contractors.context_schema import IntegratePhaseOutput
        _validation_failed = False
        try:
            IntegratePhaseOutput.model_validate(
                {"integration_results": integration_results}
            )
        except Exception as exc:
            _gate_mode = context.get("quality_gate_summary", {}).get(
                "policy_mode", "warn"
            )
            if _gate_mode == "block":
                raise RuntimeError(
                    f"INTEGRATE output validation failed (block policy): {exc}"
                ) from exc
            _validation_failed = True
            logger.warning(
                "INTEGRATE output validation failed (continuing per %s "
                "policy): %s", _gate_mode, exc,
            )
        if _validation_failed:
            for ir_val in integration_results.values():
                if isinstance(ir_val, dict):
                    ir_val["_validation_failed"] = True

        # Write to context
        context["integration_results"] = integration_results
        # generation_results already mutated with project_root paths

        duration = time.monotonic() - start
        passed = sum(1 for r in integration_results.values() if r["success"])
        # R2-O2: Include design-failed and other non-generated tasks in the
        # denominator so they don't inflate the pass rate.  Tasks whose
        # generation failed (including design_gated) are counted but not passed.
        _design_failed_count = sum(
            1 for gr in generation_results.values()
            if not gr.success and getattr(gr, "metadata", None)
            and isinstance(gr.metadata, dict)
            and gr.metadata.get("design_gated")
        )
        _gen_failed_count = sum(
            1 for gr in generation_results.values()
            if not gr.success
        )
        # Total = tasks that went through integration + tasks that were
        # skipped due to generation failure (design_gated, impl errors, etc.)
        total = len(integration_results) + _gen_failed_count

        logger.info(
            "INTEGRATE phase complete: %d/%d tasks merged "
            "(%d design-failed, %d gen-failed) (%.2fs)",
            passed, total, _design_failed_count,
            _gen_failed_count - _design_failed_count, duration,
        )

        return {
            "output": integration_results,
            "cost": 0.0,  # no LLM cost — only subprocess validation
            "metadata": {
                "duration": duration,
                "passed": passed,
                "total": total,
                "design_failed": _design_failed_count,
                "gen_failed": _gen_failed_count,
            },
        }


class TestPhaseHandler(AbstractPhaseHandler):
    """TEST phase: Run post-generation validators against generated code.

    In dry-run mode: reports the test plan per task (unchanged).
    In real mode: executes validator commands (pytest, mypy, ruff, etc.)
    as subprocesses and collects pass/fail results.

    Helpers:
        * ``_resolve_validator_command`` — maps validator names to CLI commands.
        * ``_run_validator`` — executes a single validator subprocess with
          timeout handling.
        * ``_run_validators_for_task`` — runs all validators for one task,
          skipping tasks whose generation was not successful.
    """

    def __init__(self, handler_config: Optional[HandlerConfig] = None) -> None:
        self.config = handler_config or HandlerConfig()

    # ------------------------------------------------------------------
    # Validator command mapping
    # ------------------------------------------------------------------

    def _resolve_validator_command(
        self,
        validator_name: str,
        target_files: list[str],
        project_root: Path,
    ) -> Optional[list[str]]:
        """Resolve a validator name to runnable subprocess args.

        Args:
            validator_name: Name from ``task.post_generation_validators``.
            target_files: List of file paths (relative to project_root).
            project_root: The project root directory.

        Returns:
            List of command arguments, or None if validator is unknown.
        """
        py = sys.executable  # use the running interpreter, not "python"
        file_args = [str(project_root / f) for f in target_files]

        if validator_name == "pytest":
            return [py, "-m", "pytest", *file_args, "--tb=short", "-q"]
        if validator_name == "mypy":
            return [py, "-m", "mypy", *file_args, "--ignore-missing-imports"]
        if validator_name == "ruff":
            return [py, "-m", "ruff", "check", *file_args]
        if validator_name == "ruff_format":
            return [py, "-m", "ruff", "format", "--check", *file_args]
        if validator_name == "black":
            return [py, "-m", "black", "--check", *file_args]
        if validator_name == "pylint":
            return [py, "-m", "pylint", *file_args]
        if validator_name == "syntax_check":
            return [py, "-m", "py_compile", *file_args]
        if validator_name in ("import_check", "imports_resolve"):
            modules = [
                self._file_to_module(f, project_root)
                for f in target_files
            ] if target_files else []
            modules = [m for m in modules if m]
            if modules:
                imports = "; ".join(f"import {m}" for m in modules)
                return [py, "-c", imports]
            return None

        # --- WCP-008: Enrichment-produced domain validators ---
        # These are AST-based validators from domain preflight rules.
        # They run as in-process checks via a wrapper script.
        enrichment_validators = {
            "relative_imports_valid",
            "deps_available",
            "no_circular_imports",
            "no_markdown_fences",
            "merge_damage",
            "no_relative_imports",
            "definition_ordering",
            "test_naming",
            "no_hardcoded_secrets",
            "no_substring_tag_matching",
            "placeholder_detection",
            "import_dependency",
            "intra_project_imports",
            "proto_field_references",
        }
        if validator_name in enrichment_validators:
            # Run the validator via the preflight rules_validators module
            return [
                py, "-c",
                f"from startd8.workflows.builtin.preflight_rules.rules_validators import run_validator; "
                f"run_validator({validator_name!r}, {file_args!r})",
            ]

        logger.warning("TEST: unknown validator %r — skipping", validator_name)
        return None

    @staticmethod
    def _file_to_module(rel_path: str, project_root: Path) -> str:
        """Convert a relative file path to a Python module name.

        Strips common source prefixes (``src/``) and the ``.py`` extension,
        then validates that the resulting dotted path looks importable.

        Returns:
            Dotted module name (e.g. ``"startd8.contractors.foo"``), or
            empty string if the path cannot be converted.
        """
        # Normalize and strip .py
        p = rel_path.replace("\\", "/")
        if not p.endswith(".py"):
            return ""
        p = p[:-3]  # strip .py

        # Strip common source-tree prefixes
        for prefix in ("src/", "lib/"):
            if p.startswith(prefix):
                p = p[len(prefix):]
                break

        # Convert path separators to dots
        module = p.replace("/", ".")

        # Basic sanity: no leading/trailing dots, no double dots
        if module.startswith(".") or module.endswith(".") or ".." in module:
            return ""
        return module

    @staticmethod
    def _truncate_output(text: str, limit: int = 4000) -> str:
        """Truncate output keeping both head and tail for context.

        When *text* exceeds *limit* characters the middle is replaced with
        a marker showing how many characters were elided.  This preserves
        the first lines (often file paths / summary) **and** the last lines
        (often the actual error message) instead of discarding the head.
        """
        if len(text) <= limit:
            return text
        half = limit // 2
        return (
            text[:half]
            + f"\n\n... [{len(text) - limit} chars truncated] ...\n\n"
            + text[-half:]
        )

    def _run_validator(
        self,
        command: list[str],
        project_root: Path,
        timeout: int,
    ) -> dict[str, Any]:
        """Execute a single validator command as a subprocess.

        Args:
            command: The CLI command args to run.
            project_root: Working directory for the subprocess.
            timeout: Timeout in seconds.

        Returns:
            Dict with keys: ``passed``, ``returncode``, ``stdout``,
            ``stderr``, ``timed_out``.
        """
        logger.debug("TEST: running validator: %s (cwd=%s)", command, project_root)
        try:
            proc = subprocess.run(
                command,
                cwd=str(project_root),
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            passed = proc.returncode == 0
            result = {
                "passed": passed,
                "returncode": proc.returncode,
                "stdout": self._truncate_output(proc.stdout) if proc.stdout else "",
                "stderr": self._truncate_output(proc.stderr) if proc.stderr else "",
                "timed_out": False,
            }
            if not passed:
                logger.info(
                    "TEST: validator failed (rc=%d): %s",
                    proc.returncode,
                    command,
                )
            return result
        except subprocess.TimeoutExpired:
            logger.warning(
                "TEST: validator timed out after %ds: %s", timeout, command
            )
            return {
                "passed": False,
                "returncode": -1,
                "stdout": "",
                "stderr": f"Timed out after {timeout}s",
                "timed_out": True,
            }
        except (OSError, UnicodeDecodeError) as exc:
            logger.error("TEST: validator command failed to start: %s", exc)
            return {
                "passed": False,
                "returncode": -1,
                "stdout": "",
                "stderr": f"Command failed to start: {exc}",
                "timed_out": False,
            }

    def _run_in_process_validators(
        self,
        task: SeedTask,
        project_root: Path,
        generation_result: GenerationResult | None,
        service_metadata: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """Run in-process validators (protocol fidelity, Dockerfile coherence).

        These validators need cross-file context (service_metadata) that
        cannot be passed through the subprocess boundary.

        Returns a list of result dicts matching the subprocess shape::

            {"validator": str, "passed": bool, "issues": list, "file": str, "command": "(in-process)"}
        """
        results: list[dict[str, Any]] = []
        if generation_result is None or not generation_result.success:
            return results

        for rel_path in task.target_files:
            full_path = project_root / rel_path
            if not full_path.exists():
                logger.debug("In-process validators: skipping %s (not found)", rel_path)
                continue
            try:
                code = full_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                logger.debug("In-process validators: skipping %s: %s", rel_path, exc)
                continue

            for validator_fn, validator_name in [
                (validate_protocol_fidelity, "protocol_fidelity"),
                (validate_dockerfile_coherence, "dockerfile_coherence"),
            ]:
                issues = validator_fn(code, rel_path, service_metadata)
                passed = len(issues) == 0
                results.append({
                    "validator": validator_name,
                    "passed": passed,
                    "issues": issues,
                    "file": rel_path,
                    "command": "(in-process)",
                })

        return results

    def _run_validators_for_task(
        self,
        task: SeedTask,
        project_root: Path,
        generation_result: Optional[GenerationResult],
        service_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run all validators for a single task.

        Validators are only executed when *generation_result* indicates
        success.  If the generation failed or was not attempted the task
        is reported as skipped with ``all_passed = False``.

        Args:
            task: The seed task.
            project_root: Project root directory.
            generation_result: The generation result from IMPLEMENT phase
                (if any).
            service_metadata: Service metadata from onboarding for
                protocol fidelity and Dockerfile coherence validators.

        Returns:
            Dict with per-validator results and overall pass/fail.
        """
        # Skip if generation was not successful
        if generation_result is None or not generation_result.success:
            return {
                "task_id": task.task_id,
                "title": task.title,
                "domain": task.domain,
                "validators_run": 0,
                "all_passed": False,
                "results": [],
                "skipped_reason": "generation_not_successful",
            }

        validator_results: list[dict[str, Any]] = []
        all_passed = True

        for validator_name in task.post_generation_validators:
            command = self._resolve_validator_command(
                validator_name, task.target_files, project_root,
            )
            if command is None:
                validator_results.append({
                    "validator": validator_name,
                    "skipped": True,
                    "reason": "unknown_validator",
                    "passed": False,
                })
                all_passed = False
                continue

            result = self._run_validator(
                command, project_root, self.config.test_timeout_seconds,
            )
            result["validator"] = validator_name
            result["command"] = " ".join(shlex.quote(part) for part in command)
            validator_results.append(result)

            if not result.get("passed", False):
                all_passed = False

        # In-process validators (AR-144 protocol fidelity, AR-147 Dockerfile coherence)
        in_process_results = self._run_in_process_validators(
            task, project_root, generation_result, service_metadata,
        )
        for ip_result in in_process_results:
            validator_results.append(ip_result)
            if not ip_result.get("passed", True):
                all_passed = False

        return {
            "task_id": task.task_id,
            "title": task.title,
            "domain": task.domain,
            "validators_run": len(validator_results),
            "all_passed": all_passed,
            "results": validator_results,
        }

    # ------------------------------------------------------------------
    # Resume cache validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_test_cache(
        saved: dict[str, Any],
        tasks: list[Any],
        generation_results: dict[str, Any],
        source_checksum: str | None,
        design_results: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Validate a saved test_results cache through 4 ordered layers.

        Returns the cached output dict if all layers pass, or None if the
        cache should be rejected (caller falls through to fresh TEST).

        Layers (cheapest → most expensive):
            0: Schema version — _cache_meta exists, schema_version == _CACHE_SCHEMA_VERSION
            1: Source checksum — _cache_meta.source_checksum matches context
            1.5: Design hash — design_results hash matches context (catches
                 ``--force-design`` invalidation)
            2: Per-task generation file hash — cached results valid only if
               generated code hasn't changed since tests ran.
        """
        # Layer 0: Schema version
        cache_meta = saved.get("_cache_meta")
        if not isinstance(cache_meta, dict):
            logger.warning(
                "TEST: cache missing _cache_meta (v1 or corrupt) — re-running"
            )
            return None
        schema_version = cache_meta.get("schema_version")
        if schema_version != _CACHE_SCHEMA_VERSION:
            logger.warning(
                "TEST: cache schema_version=%s (expected %d) — re-running",
                schema_version, _CACHE_SCHEMA_VERSION,
            )
            return None

        # Layer 1: Source checksum
        cached_checksum = cache_meta.get("source_checksum")
        if (
            cached_checksum is not None
            and source_checksum is not None
            and cached_checksum != source_checksum
        ):
            logger.warning(
                "TEST: source_checksum mismatch "
                "(cached=%s, current=%s) — re-running",
                cached_checksum, source_checksum,
            )
            return None
        elif cached_checksum is not None or source_checksum is not None:
            # One side has a checksum and the other doesn't — we can't
            # confirm integrity but this is common during the first run
            # after cache creation (seed lacks checksum) or after a
            # rebuild (context gains one).  Log for visibility.
            logger.warning(
                "TEST: only one side has source_checksum "
                "(cached=%s, context=%s) — skipping Layer 1 comparison",
                "present" if cached_checksum else "absent",
                "present" if source_checksum else "absent",
            )
        else:
            # Both checksums are None — Layer 1 integrity check is disabled
            logger.warning(
                "Cache validation: neither cached nor current has source_checksum — "
                "Layer 1 integrity check is disabled"
            )

        # Layer 1.5: Design hash — invalidate when design changes
        # (e.g. --force-design re-ran DESIGN but IMPLEMENT cache was
        # also invalidated, producing new code from the new design).
        cached_design_hash = cache_meta.get("design_hash")
        if cached_design_hash is not None and design_results is not None:
            current_design_hash = _compute_design_results_hash(design_results)
            if (
                current_design_hash is not None
                and current_design_hash != cached_design_hash
            ):
                logger.warning(
                    "TEST: design_hash mismatch "
                    "(cached=%s, current=%s) — re-running",
                    cached_design_hash[:12], current_design_hash[:12],
                )
                return None

        # Layer 2: Per-task generation file hash — verify generated code
        # hasn't changed since tests were run.
        cached_gen_hashes = cache_meta.get("generation_file_hashes", {})
        if cached_gen_hashes:
            for tid, cached_hash in cached_gen_hashes.items():
                gen_result = generation_results.get(tid)
                if gen_result is None:
                    continue
                current_files = getattr(gen_result, "generated_files", [])
                if not current_files:
                    continue
                current_hash = _compute_gen_file_hash(current_files)
                if current_hash is not None and current_hash != cached_hash:
                    logger.warning(
                        "TEST: generation file hash mismatch for %s "
                        "(cached=%s, current=%s) — re-running",
                        tid, cached_hash[:12], current_hash[:12],
                    )
                    return None

        cached_output = saved.get("output")
        if not isinstance(cached_output, dict):
            logger.warning("TEST: cache missing 'output' key — re-running")
            return None

        # Verify all current task IDs are covered
        current_ids = {t.task_id for t in tasks}
        cached_per_task = cached_output.get("per_task", {})
        missing = current_ids - set(cached_per_task.keys())
        if missing:
            logger.warning(
                "TEST: cache missing tasks %s — re-running", sorted(missing),
            )
            return None

        logger.info(
            "TEST: cache valid — resuming with %d cached task results",
            len(cached_per_task),
        )
        return cached_output

    # ------------------------------------------------------------------
    # Public execute
    # ------------------------------------------------------------------

    def execute(
        self,
        phase: WorkflowPhase,
        context: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        start = time.monotonic()
        _log_context_completeness("TEST", context)
        tasks: list[SeedTask] = _ensure_context_loaded(context)
        project_root = Path(context.get("project_root", "."))
        generation_results: dict[str, GenerationResult] = context.get("generation_results", {})
        truncation_flags: dict[str, Any] = context.get("truncation_flags", {})
        integration_results_ctx: dict[str, Any] = context.get("integration_results", {})

        logger.info("TEST phase: processing %d tasks (dry_run=%s)", len(tasks), dry_run)

        # --- Resume check: load prior test results if available ---
        _has_explicit_project_root = bool(context.get("project_root", "").strip())
        test_cache_path = (
            project_root / ".startd8" / "state" / "test_results.json"
            if _has_explicit_project_root else None
        )
        if (
            test_cache_path
            and test_cache_path.exists()
            and not dry_run
            and not self.config.force_test
        ):
            try:
                with open(test_cache_path, encoding="utf-8") as f:
                    raw_cache = json.load(f)
                cached_output = self._validate_test_cache(
                    raw_cache,
                    tasks,
                    generation_results,
                    context.get("source_checksum"),
                    context.get("design_results"),
                )
                if cached_output is not None:
                    # C-3 fix: assign the validated result back so that any
                    # Pydantic validator transforms (filled defaults, coerced
                    # types) are preserved instead of discarded.
                    validated = ValidationPhaseOutput(test_results=cached_output)
                    cached_output = validated.test_results
                    context["test_results"] = cached_output
                    duration = time.monotonic() - start
                    logger.info(
                        "TEST phase complete (resumed from cache): "
                        "%d passed, %d failed (%.2fs)",
                        cached_output.get("total_passed", 0),
                        cached_output.get("total_failed", 0),
                        duration,
                    )
                    return {"output": cached_output, "cost": 0.0, "metadata": {"duration": duration, "resumed": True}}
            except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError, UnicodeDecodeError) as exc:
                logger.warning("TEST: failed to load cache from %s: %s", test_cache_path, exc)

        test_plan: list[dict[str, Any]] = []
        validator_counts: dict[str, int] = defaultdict(int)
        total_passed = 0
        total_failed = 0
        previous_task_started_mono: Optional[float] = None
        _service_metadata = context.get("service_metadata")

        # Note: idx is ordinal position (not completed count) — may skip if tasks are filtered
        for idx, task in enumerate(tasks, start=1):
            _links = _build_provenance_links(task.task_id, context, ["design", "implement"])
            _task_span_cm = _phase_tracer.start_as_current_span(
                f"task.{task.task_id}",
                attributes={
                    "task.id": task.task_id,
                    "task.title": task.title,
                    "task.domain": task.domain or "",
                    "task.phase": "test",
                },
                links=_links,
            )
            _task_span = _task_span_cm.__enter__()
            previous_task_started_mono = _log_task_timing(
                "TEST",
                task.task_id,
                idx,
                len(tasks),
                start,
                previous_task_started_mono,
            )
            _log_task_boundary_start(task, phase="test")
            task_status = "unknown"
            validators = task.post_generation_validators
            for v in validators:
                validator_counts[v] += 1

            if dry_run:
                # --- Dry-run path (unchanged) ---
                test_entry = {
                    "task_id": task.task_id,
                    "title": task.title,
                    "domain": task.domain,
                    "validators": validators,
                    "validator_count": len(validators),
                    "status": "dry_run_planned",
                }
                test_plan.append(test_entry)
                _task_span.set_attribute("task.status", "dry_run_planned")
                _sc = _capture_task_span_context(_task_span)
                if _sc:
                    test_entry["_span_context"] = _sc
                _log_task_boundary_complete(
                    task.task_id,
                    status="dry_run_planned",
                    phase="test",
                )
                _task_span_cm.__exit__(None, None, None)
                continue

            # --- Real-mode path ---
            try:
                gen_result = generation_results.get(task.task_id)

                # Skip tasks that were not generated
                if gen_result is None or not gen_result.success:
                    logger.warning(
                        "TEST: skipping task %s (%s) — no successful generation result",
                        task.task_id, task.title,
                    )
                    test_plan.append({
                        "task_id": task.task_id,
                        "title": task.title,
                        "domain": task.domain,
                        "validators": validators,
                        "validator_count": len(validators),
                        "status": "skipped_no_generation",
                    })
                    _task_span.set_attribute("task.status", "skipped_no_generation")
                    task_status = "skipped_no_generation"
                    continue

                # Skip tasks that failed INTEGRATE (e.g. truncation-blocked)
                _int_result = integration_results_ctx.get(task.task_id, {})
                if isinstance(_int_result, dict) and _int_result.get("success") is False:
                    _int_status = _int_result.get("status", "unknown")
                    logger.warning(
                        "TEST: skipping task %s (%s) — integration failed (status=%s)",
                        task.task_id, task.title, _int_status,
                    )
                    test_plan.append({
                        "task_id": task.task_id,
                        "title": task.title,
                        "domain": task.domain,
                        "validators": validators,
                        "validator_count": len(validators),
                        "status": "skipped_integration_failed",
                        "integration_status": _int_status,
                    })
                    _task_span.set_attribute("task.status", "skipped_integration_failed")
                    _task_span.set_attribute("task.integration_status", _int_status)
                    task_status = "skipped_integration_failed"
                    continue

                # Run validators
                task_test_result = self._run_validators_for_task(
                    task, project_root, gen_result,
                    service_metadata=_service_metadata,
                )

                # Determine status: distinguish zero-validator tasks from
                # genuinely-passing tasks so they don't inflate the pass rate.
                if task_test_result.get("validators_run", 0) == 0:
                    # No validators ran — mark as uncovered, NOT passed
                    task_test_result["status"] = "uncovered"
                    _task_span.set_attribute("task.status", "uncovered")
                    task_status = "uncovered"
                elif task_test_result["all_passed"]:
                    task_test_result["status"] = "passed"
                    total_passed += 1
                    _task_span.set_attribute("task.status", "passed")
                    task_status = "passed"
                else:
                    task_test_result["status"] = "failed"
                    total_failed += 1
                    _task_span.set_attribute("task.status", "failed")
                    task_status = "failed"
                test_plan.append(task_test_result)
            except Exception as exc:
                logger.warning(
                    "TEST: unexpected error for task %s: %s",
                    task.task_id, exc, exc_info=True,
                )
                test_plan.append({
                    "task_id": task.task_id,
                    "title": task.title,
                    "domain": task.domain,
                    "validators": validators,
                    "validator_count": len(validators),
                    "validators_run": 0,
                    "all_passed": False,
                    "results": [],
                    "status": "error",
                    "error": str(exc),
                })
                total_failed += 1
                _task_span.set_attribute("task.status", "error")
                task_status = "error"
            finally:
                _sc = _capture_task_span_context(_task_span)
                if _sc and test_plan:
                    test_plan[-1]["_span_context"] = _sc
                _log_task_boundary_complete(
                    task.task_id,
                    status=task_status,
                    phase="test",
                )
                _task_span_cm.__exit__(None, None, None)

        per_task: dict[str, Any] = {}
        for entry in test_plan:
            task_id = entry.get("task_id")
            if not task_id:
                continue
            if entry.get("status") == "passed":
                per_task[task_id] = {
                    "status": "passed",
                    "passed": True,
                    "validators_run": entry.get("validators_run", 0),
                }
            elif entry.get("status") == "uncovered":
                # R2-T1: Zero-validator tasks — not a validated pass
                per_task[task_id] = {
                    "status": "uncovered",
                    "passed": None,
                    "validators_run": 0,
                    "reason": "no_applicable_validators",
                }
            elif entry.get("status") == "failed":
                per_task[task_id] = {
                    "status": "failed",
                    "passed": False,
                    "validators_run": entry.get("validators_run", 0),
                    "failures": [
                        r.get("validator")
                        for r in entry.get("results", [])
                        if not r.get("passed", True)
                    ],
                }
            elif entry.get("status") == "skipped_no_generation":
                per_task[task_id] = {
                    "status": "skipped",
                    "passed": None,
                    "validators_run": 0,
                    "reason": "no_successful_generation",
                }
            elif entry.get("status") == "skipped_integration_failed":
                per_task[task_id] = {
                    "status": "skipped",
                    "passed": None,
                    "validators_run": 0,
                    "reason": "integration_failed",
                    "integration_status": entry.get("integration_status"),
                }
            elif entry.get("status") == "error":
                per_task[task_id] = {
                    "status": "error",
                    "passed": False,
                    "validators_run": 0,
                    "error": entry.get("error", ""),
                }
            else:
                per_task[task_id] = {
                    "status": entry.get("status", "unknown"),
                    "passed": None,
                    "validators_run": entry.get("validators_run", 0),
                }

        # ── Gate 4 propagation: annotate per-task with truncation warnings ──
        # Propagate the minimum fields needed for downstream dashboards
        # and the REVIEW prompt injection.  Full details stay in
        # context["truncation_flags"] for FINALIZE summary.
        if truncation_flags:
            for task_id, tf in truncation_flags.items():
                if task_id in per_task:
                    per_task[task_id]["truncation_warning"] = True
                    per_task[task_id]["truncation_confidence"] = tf.get("max_confidence", 0.0)
                    per_task[task_id]["truncation_source"] = tf.get("source", "unknown")

        total_skipped = sum(
            1 for v in per_task.values()
            if v.get("status") == "skipped"
        )
        # R2-T1: Count tasks with no applicable validators separately
        total_uncovered = sum(
            1 for v in per_task.values()
            if v.get("status") == "uncovered"
        )
        output = {
            "test_plan": test_plan,
            "total_validators": sum(len(t.post_generation_validators) for t in tasks),
            "unique_validators": dict(validator_counts),
            "tasks_with_tests": len([t for t in test_plan if t.get("validator_count", 0) > 0 or t.get("validators_run", 0) > 0]),
            "total_passed": total_passed,
            "total_failed": total_failed,
            "total_skipped": total_skipped,
            "tests_uncovered": total_uncovered,
            "per_task": per_task,
        }

        context["test_results"] = output

        # Context contract: validate TEST output model.
        # R2-T6: Respect gate mode — block raises, warn flags, skip ignores.
        try:
            ValidationPhaseOutput(test_results=context["test_results"])
        except Exception as _val_exc:
            _gate_mode = context.get("quality_gate_summary", {}).get(
                "policy_mode", "warn",
            )
            if _gate_mode == "block":
                raise RuntimeError(
                    f"TEST output validation failed (block policy): {_val_exc}"
                ) from _val_exc
            logger.warning(
                "TEST output validation failed (continuing per %s policy): %s",
                _gate_mode,
                _val_exc,
            )
            if _gate_mode == "warn":
                # Flag the output so downstream phases know validation failed
                output["_validation_failed"] = True
                output["_validation_error"] = str(_val_exc)

        # --- Cache write: persist test results for resume ---
        if test_cache_path and not dry_run:
            try:
                # Compute per-task generation file hashes for cache invalidation
                gen_file_hashes: dict[str, str] = {}
                for task in tasks:
                    gen_result = generation_results.get(task.task_id)
                    if gen_result is None:
                        continue
                    gen_files = getattr(gen_result, "generated_files", [])
                    if not gen_files:
                        continue
                    file_hash = _compute_gen_file_hash(gen_files)
                    if file_hash is not None:
                        gen_file_hashes[task.task_id] = file_hash

                # Compute design hash for cache invalidation (Layer 1.5)
                _design_hash = _compute_design_results_hash(
                    context.get("design_results", {})
                )

                cache_envelope: dict[str, Any] = {
                    "_cache_meta": {
                        "schema_version": _CACHE_SCHEMA_VERSION,
                        "created_at": datetime.datetime.now(
                            datetime.timezone.utc
                        ).isoformat(),
                        "source_checksum": context.get("source_checksum"),
                        "generation_file_hashes": gen_file_hashes,
                        "design_hash": _design_hash,
                    },
                    "output": output,
                }
                test_cache_path.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_json(test_cache_path, cache_envelope, indent=2)
                logger.info(
                    "TEST: saved %d task results (v2) to %s",
                    len(per_task), test_cache_path,
                )
            except Exception as exc:
                logger.warning(
                    "TEST: failed to write cache to %s: %s (non-fatal)",
                    test_cache_path, exc, exc_info=True,
                )

        duration = time.monotonic() - start

        logger.info(
            "TEST phase complete: %d validators across %d tasks, %d passed, %d failed (%.2fs)",
            output["total_validators"], len(test_plan), total_passed, total_failed, duration,
        )

        return {"output": output, "cost": 0.0, "metadata": {"duration": duration}}


def _format_review_prompt(template_name: str, **kwargs: Any) -> str | None:
    """Load and format a template from ``review.yaml``.

    Returns the formatted string on success, or ``None`` when the YAML
    file or template is unavailable (e.g. downstream installs that
    haven't updated).  Failures are logged at DEBUG so they're
    traceable without cluttering normal output.
    """
    try:
        from startd8.contractors.artisan_phases.prompts import format_prompt

        return format_prompt("review", template_name, **kwargs)
    except (FileNotFoundError, KeyError) as exc:
        logger.debug(
            "YAML template review/%s unavailable, using inline fallback: %s",
            template_name,
            exc,
        )
        return None


def _get_review_template(template_name: str) -> str | None:
    """Load a raw template from ``review.yaml`` without formatting.

    Returns the template string on success, or ``None`` when unavailable.
    """
    try:
        from startd8.contractors.artisan_phases.prompts import get_template

        return get_template("review", template_name)
    except (FileNotFoundError, KeyError) as exc:
        logger.debug(
            "YAML template review/%s unavailable, using inline fallback: %s",
            template_name,
            exc,
        )
        return None


class ReviewPhaseHandler(AbstractPhaseHandler):
    """REVIEW phase: LLM-based quality review of generated implementations.

    In dry-run mode: reports review checklist (unchanged).
    In real mode: sends generated code to a review agent for
    quality scoring, then aggregates pass/fail verdicts.
    """

    def __init__(self, handler_config: Optional[HandlerConfig] = None) -> None:
        self.config = handler_config or HandlerConfig()
        self._review_agent: Any = None
        self._last_review_prompt_diagnostics: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Review prompt template — loaded from review.yaml
    # ------------------------------------------------------------------

    # Inline fallback used only when review.yaml is missing (e.g.
    # downstream installs that haven't updated).
    _REVIEW_PROMPT_TEMPLATE_FALLBACK = """You are reviewing generated code for quality and correctness.

## Task
**ID:** {task_id}
**Title:** {title}
**Domain:** {domain}

## Task Description
{description}

## Prompt Constraints
{constraints}

## Generated Code
```
{generated_code}
```

## Test Results
{test_results}

## Review Instructions
Evaluate the implementation against the task description and constraints.

## Required Output Format

### Score: [0-100]

### Verdict: [PASS/FAIL]
PASS if score >= {pass_threshold} and no blocking issues.

### Strengths
- [What was done well]

### Issues
- [severity: BLOCKING/MAJOR/MINOR] [description]

### Suggestions
- [Specific improvements]
"""

    # PAQ-102/502: deterministic REVIEW section budgets and global cap.
    _REVIEW_SECTION_BUDGETS: dict[str, int] = {
        "project_context": 2000,
        "design_compliance": 8000,
        "parameter_sources": 1200,
        "semantic_conventions": 1200,
        "service_metadata": 1200,
        "refine_compliance": 1400,
        "truncation_warning": 800,
        "deps_advisory": 600,
        "call_graph": 2000,
        "forward_contract_violations": 1800,
    }
    _REVIEW_TOTAL_SECTION_BUDGET = 14000

    @staticmethod
    def _get_review_user_template() -> str:
        """Return the review_user template, preferring YAML over fallback."""
        tmpl = _get_review_template("review_user")
        if tmpl is not None:
            return tmpl
        return ReviewPhaseHandler._REVIEW_PROMPT_TEMPLATE_FALLBACK

    def _resolve_review_agent(self) -> Any:
        """Lazily resolve the review agent from config.

        Creates a :class:`BaseAgent` instance using the lead_agent spec
        with low temperature for consistent reviews.

        Returns:
            A BaseAgent instance.
        """
        if self._review_agent is not None:
            return self._review_agent

        from startd8.utils.agent_resolution import resolve_agent_spec

        agent_spec = self.config.review_agent or self.config.lead_agent

        resolve_kwargs: dict[str, Any] = {
            "name": "context-seed-reviewer",
            "temperature": self.config.review_temperature,
            "enable_prompt_caching": self.config.enable_prompt_caching,
        }
        if self.config.max_tokens is not None:
            resolve_kwargs["max_tokens"] = self.config.max_tokens

        self._review_agent = resolve_agent_spec(
            agent_spec,
            **resolve_kwargs,
        )
        return self._review_agent

    def _build_review_prompt(
        self,
        task: SeedTask,
        generated_code: str,
        test_results: dict[str, Any],
        design_document: str | None = None,
        parameter_sources: dict[str, Any] | None = None,
        semantic_conventions: dict[str, Any] | None = None,
        truncation_info: dict[str, Any] | None = None,
        project_context: dict[str, Any] | None = None,
        service_metadata: dict[str, Any] | None = None,
        refine_provenance: dict[str, Any] | None = None,
        forward_contract_violations: list[Any] | None = None,  # GAP1-A
    ) -> str:
        """Build the review prompt for a single task.

        Each logical section is built by a helper method that loads its
        template from ``review.yaml`` (falling back to inline assembly
        when the YAML file is absent).  The orchestrator builds the base
        prompt, then inserts enrichment sections before
        ``## Review Instructions``.

        Insertion order (preserved from the original monolithic method):
          1. project_context  (PCA-302/505)
          2. design_document  (Layer 4 — Gap 17, 19)
          3. parameter_sources + semantic_conventions (Gap 2, 28, 35)
          4. service_metadata (PCA-303, Gap 29)
          5. refine_provenance (IMP-9b)
          6. truncation_info  (Gate 4 — Gap 32)
          7. deps_advisory    (Gate 5)

        Args:
            task: The seed task.
            generated_code: The code that was generated.
            test_results: Test results from the TEST phase.
            design_document: Optional design document from DESIGN phase.
            parameter_sources: Optional parameter source mappings.
            semantic_conventions: Optional semantic convention mappings.
            truncation_info: Optional Gate 4 truncation detection result.
            project_context: Optional project-level context.
            service_metadata: Optional service metadata for protocol checks.
            refine_provenance: Optional REFINE apply provenance.

        Returns:
            Formatted review prompt string.
        """
        # -- Base prompt --
        prompt = self._build_review_base(task, generated_code, test_results)

        # -- Enrichment sections (inserted before "## Review Instructions") --
        # Each helper returns a list of strings.  Empty list = no injection.
        # R2-T10: Sections are ordered by priority (highest first) so that
        # when the total budget overflows, lower-priority sections are
        # dropped first.  FM violations and design compliance are the most
        # actionable and must survive budget trimming.
        named_sections: list[tuple[str, str]] = []
        for text in self._build_project_context_section(project_context):
            named_sections.append(("project_context", text))
        for text in self._build_design_compliance_section(design_document):
            named_sections.append(("design_compliance", text))
        # R2-T10: FM violations moved up — they are as important as design
        # compliance and core review score; must not be dropped on overflow.
        for text in self._build_forward_contract_violations_section(forward_contract_violations):
            named_sections.append(("forward_contract_violations", text))
        for text in self._build_parameter_sources_section(parameter_sources):
            named_sections.append(("parameter_sources", text))
        for text in self._build_semantic_conventions_section(semantic_conventions):
            named_sections.append(("semantic_conventions", text))
        for text in self._build_service_metadata_section(service_metadata):
            named_sections.append(("service_metadata", text))
        for text in self._build_refine_compliance_section(refine_provenance):
            named_sections.append(("refine_compliance", text))
        for text in self._build_truncation_warning_section(truncation_info):
            named_sections.append(("truncation_warning", text))
        for text in self._build_deps_advisory_section(task, test_results):
            named_sections.append(("deps_advisory", text))
        for text in self._build_call_graph_section(task, generated_code):
            named_sections.append(("call_graph", text))

        if named_sections:
            budgeted_sections, diagnostics = self._apply_review_section_budgets(
                named_sections
            )
            self._last_review_prompt_diagnostics = diagnostics
            enrichment = "\n".join(budgeted_sections)
            if "## Review Instructions" in prompt:
                prompt = prompt.replace(
                    "## Review Instructions",
                    enrichment + "\n\n## Review Instructions",
                )
            else:
                logger.warning(
                    "'## Review Instructions' heading not found in review "
                    "prompt — appending enrichment sections at end"
                )
                prompt += "\n" + enrichment
        else:
            self._last_review_prompt_diagnostics = {
                "section_budget_total": self._REVIEW_TOTAL_SECTION_BUDGET,
                "section_char_total": 0,
                "section_count": 0,
                "rendered_section_count": 0,
                "dropped_sections": [],
                "dropped_section_count": 0,
                "truncated_sections": {},
                "truncation_count": 0,
            }

        # GAP3-B CG-CR: Inject call graph context for review focus (CG-CR-1..CG-CR-5)
        try:
            _review_registry = None
            if self.config.manifest_consumption_enabled:
                _review_registry = self.config.manifest_registry
            if _review_registry is not None:
                from startd8.contractors.review_call_graph_context import (
                    enrich_review_prompt_with_call_graph,
                )
                prompt = enrich_review_prompt_with_call_graph(
                    prompt,
                    file_paths=list(task.target_files),
                    registry=_review_registry,
                    budget_chars=2000,
                )
        except Exception as _cg_cr_err:
            logger.debug("REVIEW CG-CR: call graph enrichment failed: %s", _cg_cr_err)

        return prompt

    @classmethod
    def _apply_review_section_budgets(
        cls,
        sections: list[tuple[str, str]],
    ) -> tuple[list[str], dict[str, Any]]:
        """Apply deterministic de-dup + overflow budgeting to REVIEW sections."""
        rendered: list[str] = []
        normalized_seen: set[str] = set()
        dropped_sections: list[str] = []
        truncated_sections: dict[str, int] = {}
        total_chars = 0

        for section_name, section_text in sections:
            normalized = re.sub(r"\s+", " ", section_text.strip()).lower()
            if normalized in normalized_seen:
                dropped_sections.append(f"{section_name}:duplicate")
                continue
            normalized_seen.add(normalized)

            budget = cls._REVIEW_SECTION_BUDGETS.get(section_name, 1200)
            text = section_text
            if len(text) > budget:
                truncated_sections[section_name] = len(text) - budget
                text = text[:budget] + (
                    f"\n... [truncated — {len(section_text) - budget} chars omitted] ..."
                )
            if total_chars + len(text) > cls._REVIEW_TOTAL_SECTION_BUDGET:
                dropped_sections.append(f"{section_name}:overflow")
                continue
            rendered.append(text)
            total_chars += len(text)

        overflow_lines: list[str] = []
        if truncated_sections:
            overflow_lines.append(
                "truncated_sections: "
                + ", ".join(
                    f"{name}(-{omitted} chars)"
                    for name, omitted in sorted(truncated_sections.items())
                )
            )
        if dropped_sections:
            overflow_lines.append(
                "dropped_sections: " + ", ".join(sorted(dropped_sections))
            )
        if overflow_lines:
            rendered.append(
                "## Overflow Summary\n"
                + "\n".join(f"- {line}" for line in overflow_lines)
            )

        diagnostics = {
            "section_budget_total": cls._REVIEW_TOTAL_SECTION_BUDGET,
            "section_char_total": total_chars,
            "section_count": len(sections),
            "rendered_section_count": len(rendered),
            "dropped_sections": dropped_sections,
            "dropped_section_count": len(dropped_sections),
            "truncated_sections": truncated_sections,
            "truncation_count": len(truncated_sections),
        }
        return rendered, diagnostics

    # -- helper: base prompt ------------------------------------------------

    def _build_review_base(
        self,
        task: SeedTask,
        generated_code: str,
        test_results: dict[str, Any],
    ) -> str:
        """Format the base review prompt with task data.

        Loads the ``review_user`` template from YAML when available,
        falling back to the inline ``_REVIEW_PROMPT_TEMPLATE_FALLBACK``.
        """
        constraints_str = "\n".join(
            f"- {c}" for c in task.prompt_constraints
        ) or "None specified"

        test_str = (
            json.dumps(test_results, indent=2, default=str)
            if test_results
            else "No test results available for this task"
        )

        max_code = self.config.review_max_code_chars
        code_for_prompt = generated_code[:max_code]
        if len(generated_code) > max_code:
            code_for_prompt += (
                f"\n\n# ... [truncated — "
                f"{len(generated_code) - max_code} chars omitted] ..."
            )

        max_test = 2000
        test_for_prompt = test_str[:max_test]
        if len(test_str) > max_test:
            test_for_prompt += (
                f"\n... [truncated — {len(test_str) - max_test} chars omitted] ..."
            )

        template = self._get_review_user_template()
        return template.format(
            task_id=task.task_id,
            title=task.title,
            domain=task.domain,
            description=task.description,
            constraints=constraints_str,
            generated_code=code_for_prompt,
            test_results=test_for_prompt,
            pass_threshold=self.config.pass_threshold,
        )

    # -- helper: project context (PCA-302/505) ------------------------------

    @staticmethod
    def _build_project_context_section(
        project_context: dict[str, Any] | None,
    ) -> list[str]:
        """PCA-302/505: Project-level context for architectural review.

        Returns a list with a single formatted section string, or ``[]``
        if *project_context* is None/empty.
        """
        if not project_context:
            return []

        # Assemble project lines
        project_lines_parts: list[str] = []
        _pn = project_context.get("project_name")
        if _pn:
            project_lines_parts.append(f"**Project:** {_pn}")
        _pt = project_context.get("plan_title")
        if _pt:
            project_lines_parts.append(f"**Plan:** {_pt}")
        _pg = project_context.get("plan_goals", [])
        for g in _pg[:5]:
            project_lines_parts.append(f"- {g}")
        project_lines = "\n".join(project_lines_parts)

        # Architectural objectives
        _arch = project_context.get("architectural_context", {})
        _objs = _arch.get("objectives", [])
        if _objs:
            obj_items = (list(_objs) if isinstance(_objs, list) else [_objs])[:3]
            arch_objectives = (
                "**Architectural Objectives:**\n"
                + "\n".join(f"- {o}" for o in obj_items)
            )
        else:
            arch_objectives = ""

        # Architectural constraints
        _cons = _arch.get("constraints", [])
        if _cons:
            con_items = (list(_cons) if isinstance(_cons, list) else [_cons])[:5]
            arch_constraints = (
                "**Constraints:**\n"
                + "\n".join(f"- {c}" for c in con_items)
            )
        else:
            arch_constraints = ""

        # Edit-first verification
        if project_context.get("had_existing_files"):
            edit_first_block = (
                "\n**Edit-First Verification:**\n"
                "This task modified EXISTING production files. Verify the "
                "implementation preserves existing functionality and does not "
                "remove or break existing code that was not part of the change scope."
            )
        else:
            edit_first_block = ""

        text = _format_review_prompt(
            "project_context",
            project_lines=project_lines,
            arch_objectives=arch_objectives,
            arch_constraints=arch_constraints,
            edit_first_block=edit_first_block,
        )
        if text is None:
            # Inline fallback
            _parts = ["## Project Context"]
            if project_lines:
                _parts.append(project_lines)
            if arch_objectives:
                _parts.append(arch_objectives)
            if arch_constraints:
                _parts.append(arch_constraints)
            if edit_first_block:
                _parts.append(edit_first_block)
            text = "\n".join(_parts)

        if len(text) > 2000:
            text = text[:2000] + "\n... [truncated for prompt budget]"
        return [text]

    # -- helper: design compliance (Layer 4 — Gap 17, 19) -------------------

    @staticmethod
    def _build_design_compliance_section(
        design_document: str | None,
    ) -> list[str]:
        """Inject design document with compliance instructions."""
        if not design_document:
            return []

        max_design = 8000
        design_for_prompt = design_document[:max_design]
        if len(design_document) > max_design:
            design_for_prompt += (
                f"\n\n# ... [{len(design_document) - max_design} chars truncated] ..."
            )
        design_lines = len(design_document.strip().splitlines())
        design_sections = sum(
            1
            for line in design_document.splitlines()
            if line.strip().startswith("##")
        )

        text = _format_review_prompt(
            "design_compliance",
            design_lines=design_lines,
            design_sections=design_sections,
            design_for_prompt=design_for_prompt,
        )
        if text is None:
            text = (
                f"\n## Design Document (from DESIGN phase — {design_lines} lines, "
                f"{design_sections} sections)\n"
                f"The implementation was built from this design specification. "
                f"**You MUST check that the implementation covers ALL sections "
                f"and requirements from this design.** Score lower if major "
                f"sections are missing or only partially implemented.\n\n"
                f"```\n{design_for_prompt}\n```\n"
            )
        return [text]

    # -- helper: parameter sources (Gap 2, 35) ------------------------------

    @staticmethod
    def _build_parameter_sources_section(
        parameter_sources: dict[str, Any] | None,
    ) -> list[str]:
        """Inject parameter source verification section."""
        if not parameter_sources:
            return []

        param_lines = "\n".join(
            f"- **{k}**: {v}" for k, v in parameter_sources.items()
        )
        text = _format_review_prompt(
            "parameter_sources",
            param_lines=param_lines,
        )
        if text is None:
            text = (
                "\n## Parameter Sources\n"
                + param_lines
                + "\nVerify the implementation uses the correct parameter names and sources.\n"
            )
        return [text]

    # -- helper: semantic conventions (Gap 28) ------------------------------

    @staticmethod
    def _build_semantic_conventions_section(
        semantic_conventions: dict[str, Any] | None,
    ) -> list[str]:
        """Inject naming convention compliance section."""
        if not semantic_conventions:
            return []

        convention_lines = "\n".join(
            f"- **{k}**: {v}" for k, v in semantic_conventions.items()
        )
        text = _format_review_prompt(
            "semantic_conventions",
            convention_lines=convention_lines,
        )
        if text is None:
            text = (
                "\n## Semantic Conventions\n"
                + convention_lines
                + "\nVerify the implementation follows these naming conventions.\n"
            )
        return [text]

    # -- helper: service metadata (PCA-303, Gap 29) -------------------------

    @staticmethod
    def _build_service_metadata_section(
        service_metadata: dict[str, Any] | None,
    ) -> list[str]:
        """Inject service metadata compliance check."""
        if not service_metadata:
            return []

        metadata_parts: list[str] = []
        _tp = service_metadata.get("transport_protocol")
        if _tp:
            metadata_parts.append(f"- Expected transport protocol: **{_tp}**")
        _rd = service_metadata.get("runtime_dependencies")
        if _rd and isinstance(_rd, list):
            metadata_parts.append(
                f"- Expected runtime dependencies: {', '.join(str(d) for d in _rd)}"
            )
        metadata_lines = "\n".join(metadata_parts)

        text = _format_review_prompt(
            "service_metadata",
            metadata_lines=metadata_lines,
        )
        if text is None:
            _smc_parts = ["## Service Metadata Compliance"]
            if metadata_lines:
                _smc_parts.append(metadata_lines)
            _smc_parts.append(
                "Check that HEALTHCHECK mechanism matches transport_protocol. "
                "Flag any capabilities added that the service metadata declares as absent."
            )
            text = "\n".join(_smc_parts)
        return [text]

    # -- helper: REFINE compliance (IMP-9b) ---------------------------------

    @staticmethod
    def _build_refine_compliance_section(
        refine_provenance: dict[str, Any] | None,
    ) -> list[str]:
        """Inject REFINE applied/warning IDs section."""
        if not refine_provenance:
            return []

        applied_ids = refine_provenance.get("applied_ids", [])
        if not applied_ids:
            return []

        applied_lines = "\n".join(f"- {aid}" for aid in applied_ids[:20])

        warning_ids = refine_provenance.get("warning_ids", [])
        if warning_ids:
            warning_block = (
                "\nThe following suggestions had apply warnings "
                "(may not be fully integrated):\n"
                + "\n".join(f"- {wid} (verify manually)" for wid in warning_ids[:10])
            )
        else:
            warning_block = ""

        text = _format_review_prompt(
            "refine_compliance",
            applied_lines=applied_lines,
            warning_block=warning_block,
        )
        if text is None:
            _rc_parts = [
                "\n## REFINE Compliance\n",
                "The following REFINE phase suggestions were integrated into "
                "the plan document before code generation. **Verify that the "
                "implementation reflects these applied changes:**",
            ]
            for aid in applied_ids[:20]:
                _rc_parts.append(f"- {aid}")
            if warning_block:
                _rc_parts.append(warning_block)
            _rc_parts.append(
                "\nScore lower if the implementation ignores changes "
                "that were explicitly applied to the plan.\n"
            )
            text = "\n".join(_rc_parts)
        return [text]

    # -- helper: truncation warning (Gate 4) --------------------------------

    @staticmethod
    def _build_truncation_warning_section(
        truncation_info: dict[str, Any] | None,
    ) -> list[str]:
        """Inject Gate 4 truncation detection results."""
        if not truncation_info:
            return []

        source = truncation_info.get("source", "unknown")
        confidence = truncation_info.get("max_confidence", 0.0)
        syntax_errs = truncation_info.get("syntax_errors", [])
        total_lines = truncation_info.get("total_lines", 0)
        estimated = truncation_info.get("estimated_loc", 0)

        syntax_line = (
            f"Syntax errors in: {', '.join(syntax_errs)}."
            if syntax_errs
            else ""
        )
        ratio_line = (
            f"Generated {total_lines} lines vs {estimated} estimated "
            f"({total_lines / estimated:.0%} ratio)."
            if estimated and total_lines
            else ""
        )

        text = _format_review_prompt(
            "truncation_warning",
            source=source,
            confidence=f"{confidence:.2f}",
            syntax_line=syntax_line,
            ratio_line=ratio_line,
        )
        if text is None:
            parts = [
                "\n## TRUNCATION WARNING (Gate 4)\n",
                f"Automated analysis flagged this task's output as potentially truncated "
                f"(source={source}, confidence={confidence:.2f}).",
            ]
            if syntax_line:
                parts.append(syntax_line)
            if ratio_line:
                parts.append(ratio_line)
            parts.append(
                "**Pay special attention to completeness.** "
                "Score lower if the implementation appears incomplete or has syntax errors.\n"
            )
            text = "\n".join(parts)
        return [text]

    # -- helper: call graph blast radius (Phase 6, CG-RV-1,2,3,4,5) --------

    def _build_call_graph_section(
        self,
        task: SeedTask,
        generated_code: str,
    ) -> list[str]:
        """Phase 6: Call graph context for review prompt.

        CG-RV-1: For each target file, list modified functions with caller counts.
        CG-RV-2: Flag generated functions with zero callers (dead code candidates).
        CG-RV-3: Combine signature changes + callers for high-priority review.
        Budget-constrained by ``call_graph_review_budget``.
        """
        if not self.config.manifest_consumption_enabled:
            return []
        registry = self.config.manifest_registry
        if registry is None:
            return []

        try:
            budget = self.config.call_graph_review_budget
            parts: list[str] = ["\n## CALL GRAPH IMPACT (Phase 6)\n"]
            current_len = len(parts[0])

            # CG-RV-1: Caller counts for target files
            for tf in getattr(task, "target_files", []) or []:
                try:
                    callers_map = registry.callers_of_file(tf)
                    if callers_map:
                        section = f"**{tf}** — functions with external callers:\n"
                        for fqn, callers in sorted(callers_map.items()):
                            br = registry.blast_radius(fqn, max_depth=self.config.blast_radius_max_depth)
                            line = f"- `{fqn}`: {len(callers)} direct callers, blast radius {len(br)}\n"
                            if current_len + len(section) + len(line) > budget:
                                break
                            section += line
                        parts.append(section)
                        current_len += len(section)
                except Exception:
                    logger.debug(
                        "REVIEW: CG-RV-1 callers_of_file failed for %s",
                        tf, exc_info=True,
                    )

            # CG-RV-2: Dead code candidates in generated output
            try:
                dead = set(registry.dead_candidates())
                if dead and task.target_files:
                    dead_in_task: list[str] = []
                    for tf in task.target_files:
                        manifest = registry.get(tf)
                        if manifest is None:
                            continue
                        from startd8.utils.manifest_registry import _flatten_elements
                        for elem in _flatten_elements(manifest.elements):
                            if elem.fqn and elem.fqn in dead:
                                dead_in_task.append(elem.fqn)
                    if dead_in_task:
                        dead_section = (
                            "**Dead code candidates** (public, zero callers):\n"
                            + "".join(f"- `{fqn}`\n" for fqn in dead_in_task[:10])
                        )
                        if current_len + len(dead_section) <= budget:
                            parts.append(dead_section)
                            current_len += len(dead_section)
            except Exception:
                logger.debug("REVIEW: CG-RV-2 dead candidates failed", exc_info=True)

            if len(parts) <= 1:
                return []  # Only header, no content
            return parts

        except Exception:
            logger.debug("REVIEW: call graph section failed", exc_info=True)
            return []

    # -- helper: Forward Manifest contract violations (GAP1-A) ---------------

    @staticmethod
    def _build_forward_contract_violations_section(
        violations: list[Any] | None,
    ) -> list[str]:
        """GAP1-A: Inject pre-computed Forward Manifest violations into review prompt.

        When violations are present the reviewer LLM sees them BEFORE evaluating
        the code, enabling it to write a contextual review that explicitly calls
        out each structural defect.

        Args:
            violations: List of ContractViolation instances (or None).

        Returns:
            List of text strings to inject, or empty list when no violations.
        """
        if not violations:
            return []

        error_viols = [v for v in violations if getattr(v, "severity", "error") == "error"]
        warn_viols = [v for v in violations if getattr(v, "severity", "error") == "warning"]

        if not error_viols and not warn_viols:
            return []

        lines = [
            "\n## Forward Manifest Contract Violations\n"
            "The following structural contracts were violated by the generated code.\n"
            "**BLOCKING** entries MUST be explicitly called out in the review score and issues list.\n"
        ]

        for v in error_viols:
            cid = getattr(v, "contract_id", "?")
            vtype = getattr(v, "violation_type", "?")
            expected = getattr(v, "expected", "?")
            actual = getattr(v, "actual", None) or "absent"
            fpath = getattr(v, "file_path", None)
            line = f"- **[BLOCKING]** `{cid}` | {vtype} | expected=`{expected}` | actual=`{actual}`"
            if fpath:
                line += f" | file=`{fpath}`"
            lines.append(line)

        for v in warn_viols:
            cid = getattr(v, "contract_id", "?")
            vtype = getattr(v, "violation_type", "?")
            expected = getattr(v, "expected", "?")
            line = f"- [WARN] `{cid}` | {vtype} | expected=`{expected}`"
            lines.append(line)

        lines.append(
            "\nIf BLOCKING violations are present, the review score MUST be below the pass threshold "
            "and the verdict MUST be FAIL.\n"
        )
        return lines

    # -- helper: deps allowlist advisory (Gate 5) ---------------------------

    @staticmethod
    def _build_deps_advisory_section(
        task: SeedTask,
        test_results: dict[str, Any],
    ) -> list[str]:
        """Inject Gate 5 confidence-stratified dependency guidance."""
        deps_confidence = getattr(task, "deps_confidence", 1.0)
        deps_source = getattr(task, "deps_source", None)

        if deps_confidence >= 0.8 or not test_results:
            return []

        # Check if any deps_available failures exist
        has_deps_issues = any(
            r.get("validator") == "deps_available" and not r.get("passed", True)
            for r in test_results.get("results", [])
        )
        if not has_deps_issues:
            return []

        if deps_confidence <= 0.2:
            confidence_guidance = (
                "Only stdlib modules are known — third-party import "
                "violations are **likely false positives**."
            )
        elif deps_confidence <= 0.5:
            confidence_guidance = (
                "Allowlist was built from venv scan only — some "
                "dependencies may be missing from the known set."
            )
        else:
            confidence_guidance = ""

        text = _format_review_prompt(
            "deps_allowlist_advisory",
            deps_source=repr(deps_source),
            deps_confidence=f"{deps_confidence:.2f}",
            confidence_guidance=confidence_guidance,
        )
        if text is None:
            parts = [
                "\n## DEPENDENCY ALLOWLIST ADVISORY (Gate 5)\n",
                f"The dependency allowlist was built from source={deps_source!r} "
                f"(confidence={deps_confidence:.2f}).",
            ]
            if confidence_guidance:
                parts.append(confidence_guidance)
            parts.append(
                "**Do NOT penalize the score for import violations when "
                "allowlist confidence is low.** Focus review on code "
                "quality, correctness, and design compliance instead.\n"
            )
            text = "\n".join(parts)
        return [text]

    def _parse_review_response(self, response: str) -> dict[str, Any]:
        """Parse score, verdict, and issues from the LLM review response.

        Args:
            response: Raw LLM output.

        Returns:
            Dict with ``score``, ``verdict``, ``strengths``, ``issues``, ``suggestions``.

        """
        import re

        score: int | None = None
        verdict = "FAIL"

        # Extract score — handles bold-wrapped variants like **85**,
        # **Score: 85**, Score: **85**/100
        # R2-T2: \*{0,2} tolerates optional markdown bold around score digits
        score_match = re.search(r"###\s*\*{0,2}Score:\s*\*{0,2}\s*(\d+)", response)
        if score_match:
            score = min(100, max(0, int(score_match.group(1))))
        else:
            # Fallback: try without markdown headers, bold-aware
            score_fallback = re.search(
                r"(?:^|\n)\s*\*{0,2}Score\s*[:=]\s*\*{0,2}\s*(\d+)\s*\*{0,2}\s*(?:/\s*100)?\s*\*{0,2}",
                response, re.IGNORECASE | re.MULTILINE,
            )
            if score_fallback:
                score = min(100, max(0, int(score_fallback.group(1))))
            else:
                # Last resort: standalone bold-wrapped number on its own line
                # e.g. **85** as the score
                score_bold_standalone = re.search(
                    r"(?:^|\n)\s*\*{2}(\d+)\*{2}\s*(?:/\s*100)?\s*$",
                    response, re.MULTILINE,
                )
                if score_bold_standalone:
                    score = min(100, max(0, int(score_bold_standalone.group(1))))
                else:
                    logger.warning(
                        "REVIEW: could not extract score from response (score=None); "
                        "first 200 chars: %s", response[:200],
                    )

        # Extract verdict
        verdict_match = re.search(r"###\s*Verdict:\s*\**\s*(PASS|FAIL)\s*\**", response, re.IGNORECASE)
        if verdict_match:
            verdict = verdict_match.group(1).upper()
        else:
            # Fallback: try without markdown headers
            verdict_fallback = re.search(r"(?:^|\n)\s*Verdict\s*[:=]\s*\**\s*(PASS|FAIL)\s*\**", response, re.IGNORECASE)
            if verdict_fallback:
                verdict = verdict_fallback.group(1).upper()
            else:
                logger.warning(
                    "REVIEW: could not extract verdict from response (defaulting to FAIL)"
                )

        def extract_section(section: str) -> list[str]:
            pattern = rf"###\s*{section}\s*\n(.*?)(?=\n###\s|\Z)"
            match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
            if not match:
                return []
            items: list[str] = []
            for line in match.group(1).splitlines():
                cleaned = line.strip()
                if cleaned.startswith("- "):
                    items.append(cleaned[2:].strip())
                elif cleaned.startswith("* "):
                    items.append(cleaned[2:].strip())
                elif re.match(r"^\d+\.\s+", cleaned):
                    items.append(re.sub(r"^\d+\.\s+", "", cleaned).strip())
            return items

        return {
            "score": score,
            "verdict": verdict,
            "passed": verdict == "PASS" and score is not None and score >= self.config.pass_threshold,
            "raw_response": response[:4000],  # truncate for storage
            "strengths": extract_section("Strengths"),
            "issues": extract_section("Issues"),
            "suggestions": extract_section("Suggestions"),
        }

    _REVIEW_PHASE_SYSTEM_PROMPT_FALLBACK = (
        "You are an expert code quality reviewer. Evaluate the implementation "
        "against the design document, checking for correctness, completeness, "
        "and adherence to stated constraints."
    )

    @staticmethod
    def _get_review_system_prompt() -> str:
        """Return the review system prompt, preferring YAML over fallback."""
        tmpl = _format_review_prompt("review_system")
        if tmpl is not None:
            return tmpl.strip()
        return ReviewPhaseHandler._REVIEW_PHASE_SYSTEM_PROMPT_FALLBACK

    def _review_task(
        self,
        task: SeedTask,
        generated_code: str,
        test_results: dict[str, Any],
        design_document: str | None = None,
        parameter_sources: dict[str, Any] | None = None,
        semantic_conventions: dict[str, Any] | None = None,
        truncation_info: dict[str, Any] | None = None,
        project_context: dict[str, Any] | None = None,
        service_metadata: dict[str, Any] | None = None,
        refine_provenance: dict[str, Any] | None = None,
        forward_contract_violations: list[Any] | None = None,  # GAP1-A: pre-computed FM violations
    ) -> dict[str, Any]:
        """Conduct LLM review for a single task.

        Args:
            task: The seed task.
            generated_code: Code to review.
            test_results: Test results for context.
            design_document: Optional design document from DESIGN phase
                for compliance checking.
            parameter_sources: Optional parameter source mappings.
            semantic_conventions: Optional semantic convention mappings.
            truncation_info: Optional Gate 4 truncation detection result for
                this task.  When present, a warning section is injected into
                the review prompt so the LLM reviewer can assess completeness.
            refine_provenance: Optional REFINE apply provenance for
                compliance checking against applied suggestions.

        Returns:
            Review result dict with score, verdict, cost.
        """
        _review_retry_config = RetryConfig(
            max_attempts=1,  # Placeholder for API compat — retry orchestration is handled by the outer _max_attempts loop with phase-aware backoff
            base_delay=5.0,
            max_delay=60.0,
            retryable_exceptions=(ConnectionError, TimeoutError, OSError),
            retryable_status_codes=(429, 500, 502, 503, 504, 529),
        )
        _max_attempts = 1 + self.config.review_task_retries

        for _attempt in range(_max_attempts):
            try:
                agent = self._resolve_review_agent()
                prompt = self._build_review_prompt(
                    task, generated_code, test_results,
                    design_document=design_document,
                    parameter_sources=parameter_sources,
                    semantic_conventions=semantic_conventions,
                    truncation_info=truncation_info,
                    project_context=project_context,
                    service_metadata=service_metadata,
                    refine_provenance=refine_provenance,
                    forward_contract_violations=forward_contract_violations,  # GAP1-A
                )
                _prompt_diag = dict(self._last_review_prompt_diagnostics or {})
                _prompt_diag.update(
                    {
                        "prompt_chars": len(prompt),
                        "prompt_tokens_estimate": len(prompt) // 4,
                    }
                )

                # OT-306: review.evaluate span (child of OT-304 task span)
                with _phase_tracer.start_as_current_span(
                    "review.evaluate",
                    attributes={
                        "review.task_id": task.task_id,
                        "review.attempt": _attempt + 1,
                        "review.has_design_doc": design_document is not None,
                        "review.has_parameter_sources": parameter_sources is not None,
                    },
                ) as _eval_span:
                    try:
                        response_text, _time_ms, token_usage = agent.generate(
                            prompt, system_prompt=self._get_review_system_prompt(),
                        )
                        review = self._parse_review_response(response_text)
                        review["task_id"] = task.task_id
                        review["cost"] = token_usage_cost(token_usage)
                        review["tokens"] = {
                            "input": token_usage_input(token_usage),
                            "output": token_usage_output(token_usage),
                        }
                        review["status"] = "reviewed"
                        review["prompt_telemetry"] = _prompt_diag

                        # OT-306 AC-3: set verdict attribute
                        _eval_span.set_attribute(
                            "review.verdict", review.get("verdict", "UNKNOWN"),
                        )

                        # CS7: Forensic log for review.evaluate
                        from startd8.contractors.forensic_log import emit_forensic_log
                        _agent_spec = self.config.review_agent or self.config.lead_agent
                        emit_forensic_log(
                            call_type="review.evaluate",
                            call={
                                "prompt_length": len(prompt),
                                "model_spec": _agent_spec,
                                "response_time_ms": _time_ms,
                                "tokens_input": token_usage_input(token_usage),
                                "tokens_output": token_usage_output(token_usage),
                                "cost_usd": token_usage_cost(token_usage),
                                "attempt": _attempt + 1,
                                "max_attempts": _max_attempts,
                            },
                            task={
                                "task_id": task.task_id,
                                "title": task.title,
                                "domain": task.domain,
                                "phase": "review",
                                "target_files": list(task.file_scope) if task.file_scope else None,
                            },
                            context_propagation={
                                "design_doc_present": design_document is not None,
                                "design_doc_line_count": len(design_document.splitlines()) if design_document else None,
                                "parameter_sources_present": parameter_sources is not None,
                                "prompt_constraints_count": len(task.prompt_constraints) if task.prompt_constraints else 0,
                                "prompt_section_count": _prompt_diag.get("section_count", 0),
                                "prompt_dropped_sections": _prompt_diag.get("dropped_section_count", 0),
                                "prompt_truncation_count": _prompt_diag.get("truncation_count", 0),
                            },
                            forensic_log_level=self.config.forensic_log_level,
                        )

                        return review
                    except Exception as _eval_err:
                        # OT-507: record error on span before re-raising
                        if _HAS_OTEL:
                            from opentelemetry.trace.status import (
                                Status as _OTelStatus,
                                StatusCode as _OTelStatusCode,
                            )
                            _eval_span.record_exception(_eval_err)
                            _eval_span.set_status(
                                _OTelStatus(_OTelStatusCode.ERROR, str(_eval_err))
                            )
                        else:
                            _eval_span.record_exception(_eval_err)
                            _eval_span.set_status("ERROR")
                        raise
            except Exception as exc:
                if (
                    _attempt < _max_attempts - 1
                    and _is_retryable_exception(exc, _review_retry_config)
                ):
                    _delay = _calculate_delay(_attempt, _review_retry_config)
                    logger.warning(
                        "REVIEW: task %s failed (attempt %d/%d), retrying in %.1fs: %s",
                        task.task_id,
                        _attempt + 1,
                        _max_attempts,
                        _delay,
                        exc,
                    )
                    time.sleep(_delay)
                    continue

                # Final attempt or non-retryable — return error
                logger.warning("REVIEW: agent error for %s: %s", task.task_id, exc)
                return {
                    "task_id": task.task_id,
                    "score": None,
                    "verdict": "ERROR",
                    "passed": False,
                    "cost": 0.0,
                    "tokens": {"input": 0, "output": 0},
                    "error": str(exc),
                    "status": "review_error",
                }
        # Unreachable — loop always returns — but satisfies type checker
        return {
            "task_id": task.task_id, "score": None, "verdict": "ERROR",
            "passed": False, "cost": 0.0, "tokens": {"input": 0, "output": 0},
            "error": "retry loop exhausted", "status": "review_error",
        }

    # ------------------------------------------------------------------
    # Review helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_error_review_entry(
        task: SeedTask,
        exc: Exception,
        env_fails: list[dict[str, Any]],
        env_warns: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build a review_items entry for a task that raised during review."""
        return {
            "task_id": task.task_id,
            "title": task.title,
            "domain": task.domain,
            "constraint_count": len(task.prompt_constraints),
            "env_failures": len(env_fails),
            "env_warnings": len(env_warns),
            "review_status": "error",
            "error": str(exc),
            "passed": False,
            "score": None,
            "verdict": "ERROR",
            "cost": 0.0,
            "tokens": {"input": 0, "output": 0},
        }

    # ------------------------------------------------------------------
    # Resume-cache helpers (v2 defense-in-depth)
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_generated_code(gen_result: GenerationResult) -> str | None:
        """Compute SHA-256 of concatenated generated file contents.

        Delegates to the module-level ``_compute_gen_file_hash`` helper
        which sorts files by path for deterministic digests and skips
        oversized files.

        Returns hex digest, or None if no files are readable.
        """
        return _compute_gen_file_hash(gen_result.generated_files)

    def _validate_review_cache(
        self,
        saved: dict[str, Any],
        generation_results: dict[str, GenerationResult],
        source_checksum: str | None,
        design_results: dict[str, Any] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Validate a saved review cache through 5 ordered layers.

        Returns a dict of task_id → cached review data for entries that
        pass all layers. Empty dict if cache-wide validation fails.

        Layers (cheapest → most expensive):
            0: Schema version — _cache_meta exists, schema_version == _CACHE_SCHEMA_VERSION
            1: Source checksum — _cache_meta.source_checksum matches context
            1.5: Design hash — design_results hash matches context
            2: Per-task status — entry has status == "reviewed"
            3: Per-task code hash — reviewed_code_hash matches current generated code
        """
        # Layer 0: Schema version
        cache_meta = saved.get("_cache_meta")
        if not isinstance(cache_meta, dict):
            logger.warning(
                "REVIEW: cache missing _cache_meta (v1 or corrupt) — ignoring"
            )
            return {}
        schema_version = cache_meta.get("schema_version")
        if schema_version != _CACHE_SCHEMA_VERSION:
            logger.warning(
                "REVIEW: cache schema_version=%s (expected %d) — ignoring",
                schema_version, _CACHE_SCHEMA_VERSION,
            )
            return {}

        # Layer 1: Source checksum
        cached_checksum = cache_meta.get("source_checksum")
        if (
            cached_checksum is not None
            and source_checksum is not None
            and cached_checksum != source_checksum
        ):
            logger.warning(
                "REVIEW: source_checksum mismatch "
                "(cached=%s, current=%s) — ignoring entire cache",
                cached_checksum, source_checksum,
            )
            return {}
        elif cached_checksum is not None or source_checksum is not None:
            # One side has a checksum and the other doesn't — we can't
            # confirm integrity but this is common during the first run
            # after cache creation or after a rebuild.
            logger.warning(
                "REVIEW: only one side has source_checksum "
                "(cached=%s, context=%s) — skipping Layer 1 comparison",
                "present" if cached_checksum else "absent",
                "present" if source_checksum else "absent",
            )
        else:
            # Both checksums are None — Layer 1 integrity check is disabled
            logger.warning(
                "Cache validation: neither cached nor current has source_checksum — "
                "Layer 1 integrity check is disabled"
            )

        # Layer 1.5: Design hash — invalidate when design changes
        cached_design_hash = cache_meta.get("design_hash")
        if cached_design_hash is not None and design_results is not None:
            current_design_hash = _compute_design_results_hash(design_results)
            if (
                current_design_hash is not None
                and current_design_hash != cached_design_hash
            ):
                logger.warning(
                    "REVIEW: design_hash mismatch "
                    "(cached=%s, current=%s) — ignoring entire cache",
                    cached_design_hash[:12], current_design_hash[:12],
                )
                return {}

        tasks_data = saved.get("tasks", {})
        valid: dict[str, dict[str, Any]] = {}

        for tid, entry in tasks_data.items():
            # Layer 2: Per-task status
            if entry.get("status") != "reviewed":
                logger.info(
                    "REVIEW: skipping cached entry %s (status=%s)",
                    tid, entry.get("status"),
                )
                continue

            # Layer 3: Per-task code hash
            cached_hash = entry.get("reviewed_code_hash")
            if cached_hash is not None:
                gen_result = generation_results.get(tid)
                if gen_result is not None:
                    current_hash = self._hash_generated_code(gen_result)
                    if current_hash is not None and current_hash != cached_hash:
                        logger.warning(
                            "REVIEW: code hash mismatch for %s "
                            "(cached=%s, current=%s) — skipping entry",
                            tid, cached_hash[:12], current_hash[:12],
                        )
                        continue

            valid[tid] = entry

        return valid

    # ------------------------------------------------------------------
    # Public execute
    # ------------------------------------------------------------------

    def execute(
        self,
        phase: WorkflowPhase,
        context: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        start = time.monotonic()
        _log_context_completeness("REVIEW", context)
        tasks: list[SeedTask] = _ensure_context_loaded(context)
        preflight_summary = context.get("preflight_summary", {})
        generation_results: dict[str, GenerationResult] = context.get("generation_results", {})
        test_results_ctx: dict[str, Any] = context.get("test_results", {})
        test_plan = test_results_ctx.get("test_plan", [])
        test_by_task = {t["task_id"]: t for t in test_plan if isinstance(t, dict)}
        integration_results_ctx: dict[str, Any] = context.get("integration_results", {})

        # Gate 2c downstream map — used to exclude downstream stubs from
        # review scoring so they don't unfairly penalize the task.
        downstream_map: dict[str, list[str]] = context.get("_downstream_map", {})
        truncation_flags: dict[str, Any] = context.get("truncation_flags", {})

        logger.info("REVIEW phase: reviewing %d tasks (dry_run=%s)", len(tasks), dry_run)

        review_items: list[dict[str, Any]] = []
        constraint_coverage: dict[str, int] = defaultdict(int)
        total_cost = 0.0
        total_passed = 0
        total_failed = 0
        previous_task_started_mono: Optional[float] = None

        # --- Resume check: load prior review results if available ---
        project_root_str = context.get("project_root")
        review_cache_path = (
            Path(project_root_str) / ".startd8" / "state" / "review_results.json"
            if project_root_str and project_root_str.strip() else None
        )
        cached_reviews: dict[str, dict[str, Any]] = {}

        if (
            review_cache_path
            and review_cache_path.exists()
            and not dry_run
            and not self.config.force_review
        ):
            try:
                with open(review_cache_path, encoding="utf-8") as f:
                    raw_cache = json.load(f)
                cached_reviews = self._validate_review_cache(
                    raw_cache,
                    generation_results,
                    context.get("source_checksum"),
                    context.get("design_results"),
                )
                logger.info(
                    "REVIEW: loaded %d validated cached review result(s) from %s",
                    len(cached_reviews), review_cache_path,
                )
            except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError, UnicodeDecodeError) as exc:
                logger.warning("REVIEW: failed to load cache from %s: %s", review_cache_path, exc)
                cached_reviews = {}

        for idx, task in enumerate(tasks, start=1):
            _links = _build_provenance_links(task.task_id, context, ["design", "implement"])
            _task_span_cm = _phase_tracer.start_as_current_span(
                f"task.{task.task_id}",
                attributes={
                    "task.id": task.task_id,
                    "task.title": task.title,
                    "task.domain": task.domain or "",
                    "task.phase": "review",
                },
                links=_links,
            )
            _task_span = _task_span_cm.__enter__()
            previous_task_started_mono = _log_task_timing(
                "REVIEW",
                task.task_id,
                idx,
                len(tasks),
                start,
                previous_task_started_mono,
            )
            _log_task_boundary_start(task, phase="review")
            task_status = "unknown"
            task_cost: Optional[float] = None
            # Count constraint types (always, for coverage report)
            for constraint in task.prompt_constraints:
                key = constraint.split("(")[0].strip()[:60]
                constraint_coverage[key] += 1

            env_fails = [
                c for c in task.environment_checks
                if c.get("status") == "fail"
            ]
            env_warns = [
                c for c in task.environment_checks
                if c.get("status") == "warn"
            ]

            if dry_run:
                # --- Dry-run path (unchanged) ---
                review_items.append({
                    "task_id": task.task_id,
                    "title": task.title,
                    "domain": task.domain,
                    "constraint_count": len(task.prompt_constraints),
                    "env_failures": len(env_fails),
                    "env_warnings": len(env_warns),
                    "review_status": "dry_run_pending",
                })
                _task_span.set_attribute("task.status", "dry_run_pending")
                _log_task_boundary_complete(
                    task.task_id,
                    status="dry_run_pending",
                    phase="review",
                )
                _task_span_cm.__exit__(None, None, None)
                continue

            # --- Real-mode path ---
            try:
                gen_result = generation_results.get(task.task_id)

                # Skip tasks that were not generated successfully
                if gen_result is None or not gen_result.success:
                    logger.warning(
                        "REVIEW: skipping task %s (%s) — no successful generation result",
                        task.task_id, task.title,
                    )
                    review_items.append({
                        "task_id": task.task_id,
                        "title": task.title,
                        "domain": task.domain,
                        "constraint_count": len(task.prompt_constraints),
                        "env_failures": len(env_fails),
                        "env_warnings": len(env_warns),
                        "review_status": "skipped_no_generation",
                    })
                    task_status = "skipped_no_generation"
                    continue

                # Skip tasks that failed INTEGRATE (e.g. truncation-blocked)
                _int_result = integration_results_ctx.get(task.task_id, {})
                if isinstance(_int_result, dict) and _int_result.get("success") is False:
                    _int_status = _int_result.get("status", "unknown")
                    logger.warning(
                        "REVIEW: skipping task %s (%s) — integration failed (status=%s)",
                        task.task_id, task.title, _int_status,
                    )
                    review_items.append({
                        "task_id": task.task_id,
                        "title": task.title,
                        "domain": task.domain,
                        "constraint_count": len(task.prompt_constraints),
                        "env_failures": len(env_fails),
                        "env_warnings": len(env_warns),
                        "review_status": "skipped_integration_failed",
                        "integration_status": _int_status,
                    })
                    task_status = "skipped_integration_failed"
                    continue

                # Read generated code for review.
                # Exclude downstream stub files (Gate 2c) from the review body
                # so the reviewer doesn't penalize minimal placeholders that are
                # intentionally deferred to later tasks.
                task_downstream = set(downstream_map.get(task.task_id, []))
                code_parts = []
                excluded_downstream = []
                for fpath in gen_result.generated_files:
                    try:
                        if not fpath.exists():
                            continue
                        # Check if this file is a downstream stub
                        rel_path = str(fpath)
                        is_downstream = any(
                            rel_path.endswith(ds) for ds in task_downstream
                        )
                        if is_downstream:
                            excluded_downstream.append(fpath.name)
                            continue

                        content = fpath.read_text(encoding="utf-8")
                        code_parts.append(f"# File: {fpath.name}\n{content}")
                    except (OSError, UnicodeDecodeError) as exc:
                        logger.warning("REVIEW: could not read %s: %s", fpath, exc)
                if excluded_downstream:
                    code_parts.append(
                        f"# NOTE: {len(excluded_downstream)} file(s) excluded from review "
                        f"(downstream stubs for later tasks): {', '.join(excluded_downstream)}"
                    )
                    logger.info(
                        "REVIEW: excluded %d downstream stub(s) from review for %s: %s",
                        len(excluded_downstream), task.task_id, excluded_downstream,
                    )
                generated_code = "\n\n".join(code_parts)
                if not generated_code.strip():
                    logger.warning(
                        "REVIEW: skipping task %s (%s) — generated code is empty",
                        task.task_id, task.title,
                    )
                    review_items.append({
                        "task_id": task.task_id,
                        "title": task.title,
                        "domain": task.domain,
                        "constraint_count": len(task.prompt_constraints),
                        "env_failures": len(env_fails),
                        "env_warnings": len(env_warns),
                        "review_status": "skipped_no_code",
                    })
                    task_status = "skipped_no_code"
                    continue
                task_test = test_by_task.get(task.task_id, {})

                # Warn when a generated task has no test results — the
                # reviewer should be aware that test coverage is absent.
                if not task_test or task_test.get("status") in (
                    "skipped_no_generation", "skipped_integration_failed",
                ):
                    logger.warning(
                        "REVIEW: task %s has no test results (test_status=%s) "
                        "— review will proceed without test coverage signal",
                        task.task_id,
                        task_test.get("status", "missing"),
                    )
                    task_test.setdefault("_no_test_coverage", True)

                # Check pre-validated cache before LLM call
                cached = cached_reviews.get(task.task_id)
                if cached:
                    # R2-T5: Validate cached entry has required fields before
                    # accepting.  If critical fields are missing the entry was
                    # written under an older schema — fall through to fresh review.
                    _REQUIRED_CACHED_FIELDS = {"score", "verdict", "passed", "status"}
                    _missing_fields = _REQUIRED_CACHED_FIELDS - set(cached.keys())
                    if _missing_fields:
                        logger.warning(
                            "REVIEW: cached entry for %s missing fields %s "
                            "(schema drift) — regenerating",
                            task.task_id, sorted(_missing_fields),
                        )
                        cached = None  # fall through to fresh review below
                    else:
                        review = {**cached, "review_status": "cached"}
                        review["title"] = task.title
                        review["domain"] = task.domain
                        review["constraint_count"] = len(task.prompt_constraints)
                        review["env_failures"] = len(env_fails)
                        review["env_warnings"] = len(env_warns)

                        # R2-T8: If cached review has no FM validation data,
                        # run FM validation now and append violations.
                        if (
                            "fm_violations" not in review
                            and self.config.manifest_consumption_enabled
                        ):
                            _registry = self.config.manifest_registry
                            _fwd_manifest = context.get("forward_manifest")
                            if _registry is not None and _fwd_manifest is not None:
                                try:
                                    from startd8.forward_manifest_validator import validate_forward_manifest
                                    _all_fm = validate_forward_manifest(_fwd_manifest, _registry) or []
                                    _task_files = set(task.target_files) if task.target_files else set()
                                    _task_fm = []
                                    for _v in _all_fm:
                                        _vp = getattr(_v, "file_path", None)
                                        if _vp is None:
                                            _task_fm.append(_v)
                                        elif _vp in _task_files or any(
                                            _vp.endswith(tf) or tf.endswith(_vp)
                                            for tf in _task_files
                                        ):
                                            _task_fm.append(_v)
                                    _err_v = [v for v in _task_fm if getattr(v, "severity", "error") == "error"]
                                    _warn_v = [v for v in _task_fm if getattr(v, "severity", "error") == "warning"]
                                    if _err_v:
                                        review["passed"] = False
                                        review["verdict"] = "FAIL"
                                        review.setdefault("issues", []).extend([
                                            f"[BLOCKING] Contract Violation: {v.violation_type} ({v.contract_id}) - Expected: {v.expected}, Actual: {v.actual}"
                                            for v in _err_v
                                        ])
                                    if _warn_v:
                                        review.setdefault("issues", []).extend([
                                            f"[MINOR] Contract Advisory: {v.violation_type} ({v.contract_id}) - {v.expected}"
                                            for v in _warn_v
                                        ])
                                    review["fm_violations"] = {
                                        "error_count": len(_err_v),
                                        "warning_count": len(_warn_v),
                                        "violation_ids": [
                                            getattr(v, "contract_id", "?") for v in _task_fm
                                        ],
                                        "retroactive": True,
                                    }
                                    logger.info(
                                        "REVIEW: retroactively validated FM for cached %s "
                                        "(%d errors, %d warnings)",
                                        task.task_id, len(_err_v), len(_warn_v),
                                    )
                                except Exception as _fm_cache_err:
                                    logger.debug(
                                        "REVIEW: FM validation on cached %s failed: %s",
                                        task.task_id, _fm_cache_err,
                                    )

                        if review.get("passed", False):
                            total_passed += 1
                        else:
                            total_failed += 1
                        review_items.append(review)
                        task_status = "cached"
                        task_cost = _coerce_optional_float(review.get("cost"))
                        logger.info(
                            "REVIEW: using cached result for %s (score=%s, passed=%s)",
                            task.task_id, cached.get("score"), cached.get("passed"),
                        )
                        continue

                # ── Layer 4: Thread design document into REVIEW ────────────
                design_results = context.get("design_results", {})
                task_design = design_results.get(task.task_id, {})
                task_design_doc = (
                    task_design.get("design_document")
                    if task_design.get("status") in ("designed", "adopted", "refined")
                    else None
                )
                # Gate 4: truncation info for this task (if flagged)
                task_truncation = truncation_flags.get(task.task_id)

                # PCA-302/505: assemble project context for review
                _project_name = context.get("plan_title") or (
                    Path(context.get("project_root", ".")).name
                    if context.get("project_root") else None
                )
                # PCA-505: check if this task had existing files during IMPLEMENT
                _gen_meta = getattr(gen_result, "metadata", {}) or {}
                _had_existing = bool(_gen_meta.get("had_existing_files"))
                # Also check generation_results for existing file info
                if not _had_existing:
                    _impl_results = context.get("implementation", {})
                    for _tr in _impl_results.get("task_reports", []):
                        if _tr.get("task_id") == task.task_id and _tr.get("had_existing_files"):
                            _had_existing = True
                            break
                _project_context = {
                    "plan_title": context.get("plan_title"),
                    "plan_goals": context.get("plan_goals", []),
                    "architectural_context": context.get("architectural_context", {}),
                    "project_name": _project_name,
                    "had_existing_files": _had_existing,
                }

                # PCA-402: track onboarding field consumption in REVIEW
                if context.get("service_metadata") is not None:
                    _track_onboarding_consumption(context, "service_metadata", "REVIEW")
                if context.get("architectural_context"):
                    _track_onboarding_consumption(context, "architectural_context", "REVIEW")

                # GAP1-A: Pre-compute FM violations so they appear in the review PROMPT
                # R2-T3: Filter violations to only those affecting this task's files
                _pre_fm_violations: list[Any] = []
                if self.config.manifest_consumption_enabled:
                    _registry = self.config.manifest_registry
                    _fwd_manifest = context.get("forward_manifest")
                    if _registry is not None and _fwd_manifest is not None:
                        try:
                            from startd8.forward_manifest_validator import validate_forward_manifest
                            _all_fm_violations = validate_forward_manifest(_fwd_manifest, _registry) or []
                            # Filter: only include violations whose file_path
                            # matches one of this task's target files
                            _task_files = set(task.target_files) if task.target_files else set()
                            for _v in _all_fm_violations:
                                _vpath = getattr(_v, "file_path", None)
                                if _vpath is None:
                                    # No file_path on violation — include it
                                    # (project-wide structural violation)
                                    _pre_fm_violations.append(_v)
                                elif _vpath in _task_files or any(
                                    _vpath.endswith(tf) or tf.endswith(_vpath)
                                    for tf in _task_files
                                ):
                                    _pre_fm_violations.append(_v)
                        except Exception as _pre_fm_err:
                            logger.debug(
                                "REVIEW: pre-prompt FM validation failed for %s: %s",
                                task.task_id, _pre_fm_err,
                            )

                review = self._review_task(
                    task, generated_code, task_test,
                    design_document=task_design_doc,
                    parameter_sources=context.get("parameter_sources"),
                    semantic_conventions=context.get("semantic_conventions"),
                    truncation_info=task_truncation,
                    project_context=_project_context,
                    service_metadata=context.get("service_metadata"),
                    refine_provenance=context.get("refine_provenance"),
                    forward_contract_violations=_pre_fm_violations or None,  # GAP1-A
                )
                review["title"] = task.title
                review["domain"] = task.domain
                review["constraint_count"] = len(task.prompt_constraints)
                review["env_failures"] = len(env_fails)
                review["env_warnings"] = len(env_warns)
                review["review_status"] = review.get("status", "reviewed")
                if task_truncation is not None:
                    review["truncation_warning"] = True
                    review["truncation_confidence"] = task_truncation.get("max_confidence", 0.0)
                    review["truncation_source"] = task_truncation.get("source", "unknown")

                # Phase 5: FM enforcement gate — reuse pre-computed violations
                # from GAP1-A (above) to avoid redundant validate_forward_manifest call.
                # R2-T4: The pre-prompt computation and this enforcement gate used
                # identical inputs; deduplicating removes the redundant second call.
                # R2-T3: violations are already filtered per-task by target file paths.
                if _pre_fm_violations:
                    try:
                        error_violations = [
                            v for v in _pre_fm_violations
                            if getattr(v, "severity", "error") == "error"
                        ]
                        warning_violations = [
                            v for v in _pre_fm_violations
                            if getattr(v, "severity", "error") == "warning"
                        ]

                        if error_violations:
                            review["passed"] = False
                            review["verdict"] = "FAIL"
                            review.setdefault("issues", []).extend([
                                f"[BLOCKING] Contract Violation: {v.violation_type} ({v.contract_id}) - Expected: {v.expected}, Actual: {v.actual}"
                                for v in error_violations
                            ])
                            logger.warning(
                                "REVIEW: task %s failed ForwardManifest validation with %d error(s)",
                                task.task_id, len(error_violations)
                            )

                        if warning_violations:
                            review.setdefault("issues", []).extend([
                                f"[MINOR] Contract Advisory: {v.violation_type} ({v.contract_id}) - {v.expected}"
                                for v in warning_violations
                            ])

                        # R2-T8: Persist FM violation summary in review for cache consumers
                        review["fm_violations"] = {
                            "error_count": len(error_violations),
                            "warning_count": len(warning_violations),
                            "violation_ids": [
                                getattr(v, "contract_id", "?") for v in _pre_fm_violations
                            ],
                        }
                    except Exception as val_error:
                        logger.error(
                            "REVIEW: ForwardManifest enforcement failed for %s: %s",
                            task.task_id, val_error, exc_info=True
                        )
                
                total_cost += review.get("cost", 0.0)
                if review.get("passed", False):
                    total_passed += 1
                else:
                    total_failed += 1

                review_items.append(review)
                task_status = str(review.get("review_status", "reviewed"))
                task_cost = _coerce_optional_float(review.get("cost"))

                # Emit quality gate result (Item 10)
                try:
                    gate_result = GateEmitter.from_review_result(
                        task_id=task.task_id,
                        review_dict=review,
                        workflow_id=context.get("workflow_id", "unknown"),
                        trace_id=context.get("trace_id"),
                    )
                    GateEmitter.emit(gate_result)
                except Exception as e:
                    logger.warning("Failed to emit review gate result for %s: %s", task.task_id, e)
            except Exception as exc:
                logger.warning(
                    "REVIEW: unexpected error for task %s: %s",
                    task.task_id, exc, exc_info=True,
                )
                review_items.append(
                    self._make_error_review_entry(task, exc, env_fails, env_warns)
                )
                total_failed += 1
                _task_span.set_attribute("task.status", "error")
                task_status = "error"
            finally:
                _sc = _capture_task_span_context(_task_span)
                if _sc and review_items:
                    review_items[-1]["_span_context"] = _sc
                _log_task_boundary_complete(
                    task.task_id,
                    status=task_status,
                    phase="review",
                    cost_usd=task_cost,
                )
                _task_span_cm.__exit__(None, None, None)

        _SKIPPED_STATUSES = {
            "skipped_no_generation",
            "skipped_integration_failed",
            "skipped_no_code",
        }
        per_task: dict[str, Any] = {}
        for item in review_items:
            task_id = item.get("task_id")
            if not task_id:
                continue
            status = item.get("review_status", "unknown")
            if status == "error":
                per_task[task_id] = {
                    "status": "error",
                    "passed": False,
                    "score": None,
                    "verdict": "ERROR",
                    "error": item.get("error", ""),
                }
            elif status in _SKIPPED_STATUSES:
                per_task[task_id] = {
                    "status": "skipped",
                    "passed": None,
                    "score": None,
                    "verdict": "SKIPPED",
                    "skip_reason": status,
                }
            else:
                # R2-T9: Preserve detail fields in per_task rollup so
                # downstream consumers have access to specific issues,
                # reviewed sections, and reviewer feedback.
                _raw_response = item.get("raw_response", "")
                _reviewer_feedback = (
                    _raw_response[:2000] if _raw_response else ""
                )
                per_task[task_id] = {
                    "status": status,
                    "passed": item.get("passed") if status in ("reviewed", "cached") else None,
                    "score": item.get("score"),
                    "verdict": item.get("verdict"),
                    "issues": item.get("issues", []),
                    "strengths": item.get("strengths", []),
                    "suggestions": item.get("suggestions", []),
                    "reviewer_feedback": _reviewer_feedback,
                }

        review_prompt_summary: dict[str, Any] = {
            "tasks_with_telemetry": 0,
            "prompt_chars_total": 0,
            "dropped_sections_total": 0,
            "truncation_count_total": 0,
        }
        _truncated_section_names: set[str] = set()
        _dropped_section_names: set[str] = set()
        for item in review_items:
            telemetry = item.get("prompt_telemetry")
            if not isinstance(telemetry, dict):
                continue
            review_prompt_summary["tasks_with_telemetry"] += 1
            review_prompt_summary["prompt_chars_total"] += int(
                telemetry.get("prompt_chars", 0) or 0
            )
            review_prompt_summary["dropped_sections_total"] += int(
                telemetry.get("dropped_section_count", 0) or 0
            )
            review_prompt_summary["truncation_count_total"] += int(
                telemetry.get("truncation_count", 0) or 0
            )
            # Collect which sections were truncated/dropped across all tasks
            _ts = telemetry.get("truncated_sections")
            if isinstance(_ts, dict):
                _truncated_section_names.update(_ts.keys())
            _ds = telemetry.get("dropped_sections")
            if isinstance(_ds, list):
                _dropped_section_names.update(_ds)
        if _truncated_section_names:
            review_prompt_summary["truncated_section_names"] = sorted(
                _truncated_section_names
            )
        if _dropped_section_names:
            review_prompt_summary["dropped_section_names"] = sorted(
                _dropped_section_names
            )

        output = {
            "review_items": review_items,
            "preflight_summary": preflight_summary,
            "constraint_coverage": dict(constraint_coverage),
            "tasks_with_env_issues": len([
                r for r in review_items
                if r.get("env_failures", 0) > 0 or r.get("env_warnings", 0) > 0
            ]),
            "total_cost": total_cost,
            "total_passed": total_passed,
            "total_failed": total_failed,
            "per_task": per_task,
            "prompt_telemetry": review_prompt_summary,
        }

        context["review_results"] = output

        # Context contract: validate REVIEW output model.
        # R2-T6: Respect gate mode — block raises, warn flags, skip ignores.
        try:
            ReviewPhaseOutput(review_results=context["review_results"])
        except Exception as _val_exc:
            _gate_mode = context.get("quality_gate_summary", {}).get(
                "policy_mode", "warn",
            )
            if _gate_mode == "block":
                raise RuntimeError(
                    f"REVIEW output validation failed (block policy): {_val_exc}"
                ) from _val_exc
            logger.warning(
                "REVIEW output validation failed (continuing per %s policy): %s",
                _gate_mode,
                _val_exc,
            )
            if _gate_mode == "warn":
                # Flag the output so downstream phases know validation failed
                output["_validation_failed"] = True
                output["_validation_error"] = str(_val_exc)

        # Persist review results for cache on re-run (v2 envelope)
        if review_cache_path and not dry_run:
            try:
                serializable_tasks: dict[str, Any] = {}
                for item in review_items:
                    tid = item.get("task_id")
                    if tid and item.get("review_status") in ("reviewed", "cached"):
                        # Compute code hash for staleness detection on next load
                        code_hash: str | None = None
                        gen_result = generation_results.get(tid)
                        if gen_result is not None:
                            code_hash = self._hash_generated_code(gen_result)
                        _serialized_entry: dict[str, Any] = {
                            "task_id": tid,
                            "score": item.get("score"),
                            "verdict": item.get("verdict"),
                            "passed": item.get("passed"),
                            "cost": item.get("cost", 0.0),
                            "tokens": item.get("tokens", {}),
                            "status": "reviewed",
                            "strengths": item.get("strengths", []),
                            "issues": item.get("issues", []),
                            "suggestions": item.get("suggestions", []),
                            "reviewed_code_hash": code_hash,
                        }
                        # R2-T8: Persist FM validation data so cached reviews
                        # can be loaded without re-running FM validation.
                        _fm_viols = item.get("fm_violations")
                        if _fm_viols is not None:
                            _serialized_entry["fm_violations"] = _fm_viols
                        serializable_tasks[tid] = _serialized_entry
                if serializable_tasks:
                    cache_envelope: dict[str, Any] = {
                        "_cache_meta": {
                            "schema_version": _CACHE_SCHEMA_VERSION,
                            "created_at": datetime.datetime.now(
                                datetime.timezone.utc
                            ).isoformat(),
                            "source_checksum": context.get("source_checksum"),
                            "design_hash": _compute_design_results_hash(
                                context.get("design_results", {})
                            ),
                        },
                        "tasks": serializable_tasks,
                    }
                    review_cache_path.parent.mkdir(parents=True, exist_ok=True)
                    atomic_write_json(review_cache_path, cache_envelope, indent=2)
                    logger.info(
                        "REVIEW: saved %d review results (v2) to %s",
                        len(serializable_tasks), review_cache_path,
                    )
            except Exception as exc:
                logger.warning(
                    "REVIEW: failed to write cache to %s: %s (non-fatal)",
                    review_cache_path, exc, exc_info=True,
                )

        duration = time.monotonic() - start

        logger.info(
            "REVIEW phase complete: %d items, %d passed, %d failed, $%.4f cost (%.2fs)",
            len(review_items), total_passed, total_failed, total_cost, duration,
        )

        # Fix 5: Track per-task cache usage for metadata
        cached_task_count = sum(
            1 for item in review_items
            if item.get("review_status") == "cached"
        )
        fresh_task_count = sum(
            1 for item in review_items
            if item.get("review_status") == "reviewed"
        )
        resumed_any = cached_task_count > 0

        # "cost" is the authoritative phase cost; output["total_cost"] is for reporting
        return {
            "output": output,
            "cost": total_cost,
            "metadata": {
                "duration": duration,
                "resumed": resumed_any,
                "cached_task_count": cached_task_count,
                "fresh_task_count": fresh_task_count,
            },
        }


class FinalizePhaseHandler(AbstractPhaseHandler):
    """FINALIZE phase: Collect artifacts and write comprehensive execution report.

    Produces a workflow execution report aggregating all phase results,
    lists generated files with checksums and line counts, computes a
    per-task status rollup joining generation/test/review outcomes, and
    writes both a human-readable report and a machine-readable manifest.

    Key outputs written to ``output_dir``:

    * ``workflow-execution-report.json`` — full summary with cost
      breakdown, artifact inventory, and per-phase stats.
    * ``generation-manifest.json`` — machine-readable manifest with
      per-task status, artifact checksums, and cost attribution.
    """

    def __init__(
        self,
        output_dir: Optional[str] = None,
        handler_config: Optional[HandlerConfig] = None,
    ) -> None:
        self.output_dir = output_dir
        self.config = handler_config or HandlerConfig()

    # ------------------------------------------------------------------
    # WCP-004: Propagation completeness validation
    # ------------------------------------------------------------------

    REQUIRED_CONTEXT_FIELDS = ["domain", "domain_reasoning", "prompt_constraints"]

    def _validate_propagation_completeness(
        self, context: dict[str, Any],
    ) -> dict[str, Any]:
        """Check that all tasks received expected context fields.

        Attempts to use the contract-based PropagationTracker for chain
        validation with OTel emission.  Falls back to the original inline
        implementation if contextcore propagation module is not available.

        Args:
            context: Workflow context containing ``tasks`` list.

        Returns:
            Dict with ``total``, ``complete``, ``defaulted``, and
            optionally ``defaulted_tasks`` listing task IDs that fell back.
        """
        # Try contract-based validation first
        try:
            from contextcore.contracts.propagation import (
                ContractLoader,
                PropagationTracker,
                emit_propagation_summary,
            )
            from pathlib import Path

            contract_yaml = Path(__file__).parent / "contracts" / "artisan-pipeline.contract.yaml"
            if contract_yaml.exists():
                contract = ContractLoader().load(contract_yaml)
                tracker = PropagationTracker()
                chain_results = tracker.validate_all_chains(contract, context)
                emit_propagation_summary(chain_results)

                # Convert chain results to legacy format for backward compat
                from contextcore.contracts.types import ChainStatus
                intact = sum(1 for r in chain_results if r.status == ChainStatus.INTACT)
                total = len(chain_results)
                return {
                    "total": total,
                    "complete": intact,
                    "defaulted": total - intact,
                    "defaulted_tasks": [
                        r.chain_id for r in chain_results
                        if r.status != ChainStatus.INTACT
                    ],
                }
        except ImportError:
            logger.debug("contextcore propagation not available", exc_info=True)
        except Exception as exc:
            logger.warning(
                "Contract-based propagation validation failed, using fallback: %s", exc
            )

        # Fallback: original inline implementation
        tasks = context.get("tasks", [])
        results: dict[str, Any] = {
            "total": len(tasks),
            "complete": 0,
            "defaulted": 0,
            "defaulted_tasks": [],
        }

        for task in tasks:
            all_present = True
            for field in self.REQUIRED_CONTEXT_FIELDS:
                value = getattr(task, field, None)
                if value in (None, "", "unknown", []):
                    results["defaulted"] += 1
                    results["defaulted_tasks"].append(
                        getattr(task, "task_id", "?"),
                    )
                    logger.warning(
                        "FINALIZE: context field '%s' not propagated for task %s",
                        field,
                        getattr(task, "task_id", "?"),
                    )
                    all_present = False
                    break
            if all_present:
                results["complete"] += 1

        # Emit span event for propagation summary
        try:
            from opentelemetry import trace
            span = trace.get_current_span()
            if span and span.is_recording():
                span.add_event("context.propagation_summary", attributes={
                    "context.total_tasks": results["total"],
                    "context.complete": results["complete"],
                    "context.defaulted": results["defaulted"],
                    "context.completeness_pct": round(
                        results["complete"] / max(results["total"], 1) * 100, 1
                    ),
                })
        except Exception:
            logger.debug("OTel span not available", exc_info=True)

        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _collect_generated_artifacts(
        self,
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Inventory all files generated during the IMPLEMENT phase.

        Reads ``context["generation_results"]`` and lists output files
        with sizes, hashes, line counts, and domain tags.

        Args:
            context: Shared workflow context.

        Returns:
            List of artifact dicts with keys: ``task_id``, ``path``,
            ``exists``, ``size_bytes``, ``line_count``, ``sha256``,
            ``domain``.
        """
        artifacts: list[dict[str, Any]] = []
        generation_results: dict[str, GenerationResult] = context.get(
            "generation_results", {}
        )

        # Build task_id → SeedTask lookup for domain metadata
        tasks: list[SeedTask] = context.get("tasks", [])
        id_to_task: dict[str, SeedTask] = {t.task_id: t for t in tasks}

        # R2-T7: Collect artifacts from ALL tasks, not just fully successful
        # ones.  Partial-success tasks may have some files generated — track
        # per-artifact source_status so downstream consumers can distinguish.
        for task_id, result in generation_results.items():
            task = id_to_task.get(task_id)
            source_status = "success" if result.success else "partial"
            for fpath in result.generated_files:
                artifact: dict[str, Any] = {
                    "task_id": task_id,
                    "path": str(fpath),
                    "exists": (
                        fpath.exists() if hasattr(fpath, "exists") else False
                    ),
                    "domain": task.domain if task else "unknown",
                    "source_status": source_status,
                }
                if hasattr(fpath, "exists") and fpath.exists():
                    try:
                        raw_bytes = fpath.read_bytes()
                        artifact["size_bytes"] = len(raw_bytes)
                        artifact["sha256"] = hashlib.sha256(raw_bytes).hexdigest()
                        try:
                            text = raw_bytes.decode("utf-8", errors="strict")
                            artifact["line_count"] = len(text.splitlines())
                        except (UnicodeDecodeError, ValueError):
                            # Binary file — line count not applicable
                            artifact["line_count"] = None
                    except OSError as exc:
                        logger.warning(
                            "FINALIZE: could not read artifact %s: %s",
                            fpath, exc,
                        )
                        artifact["read_error"] = str(exc)
                artifacts.append(artifact)

        return artifacts

    def _persist_forensic_artifacts(
        self,
        *,
        context: dict[str, Any],
        output_dir: Path,
        dry_run: bool,
    ) -> dict[str, dict[str, Any]]:
        """AR-166: Persist Prime-style per-task forensic artifacts.

        Stores best-effort artifacts under:
          ``<output_dir>/.artifacts/<task_id>/``
        with deterministic names:
          - ``spec.md``
          - ``draft-<n>.md``
          - ``review-<n>.json``
          - ``integration.json``

        In dry-run mode, records planned paths only.
        """
        tasks: list[SeedTask] = _ensure_context_loaded(context)
        design_results: dict[str, Any] = context.get("design_results", {}) or {}
        integration_results: dict[str, Any] = context.get("integration_results", {}) or {}
        forensic_map: dict[str, dict[str, Any]] = {}

        for task in tasks:
            task_id = task.task_id
            task_dir = output_dir / ".artifacts" / task_id
            task_design = design_results.get(task_id, {}) if isinstance(design_results, dict) else {}
            task_integration = integration_results.get(task_id, {}) if isinstance(integration_results, dict) else {}

            pointers: dict[str, Any] = {
                "spec": str(task_dir / "spec.md"),
                "drafts": [str(task_dir / "draft-1.md")],
                "reviews": [str(task_dir / "review-1.json")],
                "integration": str(task_dir / "integration.json"),
                "planned_only": bool(dry_run),
                "persisted": False,
            }
            forensic_map[task_id] = pointers
            if dry_run:
                continue

            try:
                task_dir.mkdir(parents=True, exist_ok=True)

                spec_text = str(
                    task_design.get("implementation_spec")
                    or task.description
                    or ""
                )
                (task_dir / "spec.md").write_text(spec_text, encoding="utf-8")

                draft_text = str(
                    task_design.get("design_document")
                    or task_design.get("implementation_spec")
                    or ""
                )
                (task_dir / "draft-1.md").write_text(draft_text, encoding="utf-8")

                review_payload = {
                    "reviewer_verdict": task_design.get("reviewer_verdict"),
                    "arbiter_verdict": task_design.get("arbiter_verdict"),
                    "reviewer_summary": task_design.get("reviewer_summary"),
                    "arbiter_summary": task_design.get("arbiter_summary"),
                    "status": task_design.get("status"),
                    "agreed": task_design.get("agreed"),
                    "iterations": task_design.get("iterations"),
                }
                atomic_write_json(
                    task_dir / "review-1.json",
                    review_payload,
                    indent=2,
                    default=str,
                )

                integration_payload = task_integration if isinstance(task_integration, dict) else {}
                atomic_write_json(
                    task_dir / "integration.json",
                    integration_payload,
                    indent=2,
                    default=str,
                )
                pointers["persisted"] = True
            except OSError as exc:
                logger.warning(
                    "FINALIZE: forensic artifact write failed for %s: %s",
                    task_id,
                    exc,
                )
            except Exception as exc:
                logger.warning(
                    "FINALIZE: forensic artifact persistence error for %s: %s",
                    task_id,
                    exc,
                )

        return forensic_map

    @staticmethod
    def _build_cost_summary(context: dict[str, Any]) -> dict[str, Any]:
        """Aggregate costs across all phases.

        Args:
            context: Shared workflow context.

        Returns:
            Dict with per-phase and total cost breakdowns.

        Note:
            PLAN and SCAFFOLD phases are zero-cost (no LLM calls) and
            excluded for clarity.  TEST phase cost is included even
            though current validators are subprocess-based (zero cost);
            this future-proofs for LLM-based test generation.
        """
        implementation = context.get("implementation", {})
        test_results = context.get("test_results", {})
        review_results = context.get("review_results", {})
        design_results = context.get("design_results", {})

        def _safe_cost(d: dict, key: str = "total_cost") -> float:
            try:
                return float(d.get(key, 0.0))
            except (TypeError, ValueError):
                return 0.0

        # Design cost: sum per-task costs from design_results dict
        design_cost = 0.0
        if isinstance(design_results, dict):
            for entry in design_results.values():
                if isinstance(entry, dict):
                    try:
                        design_cost += float(entry.get("cost", 0.0) or 0.0)
                    except (TypeError, ValueError):
                        logger.debug("Cost computation failed", exc_info=True)

        impl_cost = _safe_cost(implementation)
        test_cost = _safe_cost(test_results)
        review_cost = _safe_cost(review_results)
        total = design_cost + impl_cost + test_cost + review_cost

        return {
            "design_cost": design_cost,
            "implementation_cost": impl_cost,
            "test_cost": test_cost,
            "review_cost": review_cost,
            "total_cost": total,
            "currency": "USD",
        }

    def _write_manifest(
        self,
        artifacts: list[dict[str, Any]],
        summary: dict[str, Any],
        context: dict[str, Any],
        output_dir: Path,
    ) -> Optional[Path]:
        """Write a machine-readable manifest of all changes.

        Includes per-task status rollup joining generation results with
        test and review outcomes, artifact checksums (from enriched
        ``_collect_generated_artifacts``), and cost breakdown.

        Args:
            artifacts: List of generated artifact dicts (with ``sha256``).
            summary: The full workflow summary.
            context: Shared workflow context (for test/review joining).
            output_dir: Directory to write the manifest.

        Returns:
            Path to the manifest file, or None if no artifacts.
        """
        if not artifacts:
            return None

        # Per-task status rollup: join generation, test, and review data
        generation_results: dict[str, GenerationResult] = context.get(
            "generation_results", {}
        )
        test_results_ctx: dict[str, Any] = context.get("test_results", {})
        review_results_ctx: dict[str, Any] = context.get("review_results", {})

        test_results_map: dict[str, Any] = dict(
            test_results_ctx.get("per_task", {}) or {}
        )
        if not test_results_map:
            logger.debug("FINALIZE: rebuilding test_results_map from test_plan entries")
            for entry in test_results_ctx.get("test_plan", []):
                if not isinstance(entry, dict):
                    continue
                task_id = entry.get("task_id")
                if not task_id:
                    continue
                status = entry.get("status", "unknown")
                passed = (
                    True if status == "passed"
                    else False if status == "failed"
                    else None
                )
                validators_run = entry.get("validators_run", 0)
                results = entry.get("results", [])
                failures = [
                    r.get("validator", "unknown")
                    for r in results
                    if isinstance(r, dict) and not r.get("passed", True)
                ]
                test_results_map[task_id] = {
                    "status": status,
                    "passed": passed,
                    "validators_run": validators_run,
                    "failures": failures,
                }

        review_results_map: dict[str, Any] = dict(
            review_results_ctx.get("per_task", {}) or {}
        )
        if not review_results_map:
            logger.debug("FINALIZE: rebuilding review_results_map from review_items entries")
            for entry in review_results_ctx.get("review_items", []):
                if not isinstance(entry, dict):
                    continue
                task_id = entry.get("task_id")
                if not task_id:
                    continue
                review_results_map[task_id] = {
                    "status": entry.get("review_status", "unknown"),
                    "passed": entry.get("passed"),
                    "score": entry.get("score"),
                    "verdict": entry.get("verdict"),
                }

        forensic_artifacts_map: dict[str, Any] = context.get("forensic_artifacts", {}) or {}
        all_task_ids: set[str] = set(t.task_id for t in context.get("tasks", []) or [])
        all_task_ids.update(generation_results.keys())
        all_task_ids.update(forensic_artifacts_map.keys())

        task_status: dict[str, dict[str, Any]] = {}
        for task_id in sorted(all_task_ids):
            try:
                gen_result = generation_results.get(task_id)
                test_info = test_results_map.get(task_id, {})
                review_info = review_results_map.get(task_id, {})
                # Surface missing target files if IMPLEMENT flagged them
                _impl_reports = context.get("implementation", {}).get("task_reports", [])
                _task_report = next(
                    (r for r in _impl_reports if r.get("task_id") == task_id),
                    {},
                )
                _entry: dict[str, Any] = {
                    "generated": bool(gen_result.success) if gen_result is not None else False,
                    "files_count": len(gen_result.generated_files) if gen_result is not None else 0,
                    "generation_cost_usd": gen_result.cost_usd if gen_result is not None else 0.0,
                    "tests_passed": test_info.get("passed", None),
                    "review_score": review_info.get("score", None),
                    "review_passed": review_info.get("passed", None),
                }
                if task_id in forensic_artifacts_map:
                    _entry["forensic_artifacts"] = forensic_artifacts_map[task_id]
                _missing = _task_report.get("missing_targets")
                if _missing:
                    _entry["missing_targets"] = _missing
                task_status[task_id] = _entry
            except Exception as exc:
                logger.warning(
                    "FINALIZE: error building status for task %s: %s",
                    task_id, exc, exc_info=True,
                )
                task_status[task_id] = {
                    "generated": False,
                    "error": str(exc),
                }

        manifest = {
            "workflow_version": "0.4.0",
            # Fix 1b: provenance chain — record source_checksum for Gate 3
            "provenance": {
                "source_checksum": context.get("source_checksum"),
                "enriched_seed_path": str(context.get("enriched_seed_path", "")),
            },
            "artifacts": artifacts,
            "task_status": task_status,
            "summary": {
                "plan_title": summary.get("plan_title", ""),
                "task_count": summary.get("task_count", 0),
                "total_cost": summary.get("cost_summary", {}).get(
                    "total_cost", 0.0
                ),
                "status": summary.get("status", "unknown"),
            },
            # CCD-603: Design coherence data at manifest root
            "design_coherence": summary.get(
                "design_coherence", {"status": "NOT_COMPUTED"},
            ),
        }

        manifest_path = output_dir / "generation-manifest.json"
        try:
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(manifest_path, manifest, indent=2, default=str)
            logger.info("Wrote manifest: %s", manifest_path)
        except OSError as exc:
            logger.warning("Failed to write manifest to %s: %s", manifest_path, exc)
            return None
        return manifest_path

    # ------------------------------------------------------------------
    # Gate 3b severity rollup
    # ------------------------------------------------------------------

    @staticmethod
    def _build_design_coherence_summary(
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Build design coherence summary for generation-manifest.json (CCD-603)."""
        lane_conflicts: list[dict[str, Any]] = context.get("lane_conflicts", [])
        lane_to_file_mapping: dict[int, list[str]] = context.get(
            "lane_to_file_mapping", {},
        )
        shared_file_manifest: dict[str, list[str]] = context.get(
            "shared_file_manifest", {},
        )

        if context.get("_design_lane_computation_skipped", False):
            return {
                "status": "NOT_COMPUTED",
                "reason": "lane computation fell back to flat iteration",
            }

        total_lanes = context.get("_design_lane_count", 0)
        shared_file_lanes = len(lane_to_file_mapping)

        coherent_lanes = sum(
            1 for lc in lane_conflicts if lc.get("status") == "COHERENT"
        )
        warning_lanes = sum(
            1 for lc in lane_conflicts if lc.get("status") == "WARNING"
        )
        conflicting_lanes = sum(
            1 for lc in lane_conflicts if lc.get("status") == "CONFLICTING"
        )

        lane_details: list[dict[str, Any]] = []
        for lc in lane_conflicts:
            lane_idx = lc.get("lane_index")
            if lane_idx is None:
                continue
            shared_files = lane_to_file_mapping.get(lane_idx, [])
            lane_details.append({
                "lane_index": lane_idx,
                "task_ids": lc.get("task_ids", []),
                "shared_files": shared_files,
                "status": lc.get("status", "COHERENT"),
            })

        return {
            "total_lanes": total_lanes,
            "shared_file_lanes": shared_file_lanes,
            "coherent_lanes": coherent_lanes,
            "warning_lanes": warning_lanes,
            "conflicting_lanes": conflicting_lanes,
            "shared_file_count": len(shared_file_manifest),
            "lane_details": lane_details,
        }

    @staticmethod
    def _count_gate3b_by_severity(
        gate3b: dict[str, list[dict[str, Any]]],
    ) -> dict[str, int]:
        """Count Gate 3b validation issues grouped by severity.

        Severity is inferred from confidence:
          >= 0.8 -> high
          >= 0.6 -> medium
          < 0.6 -> low
        """
        counts: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
        for task_issues in gate3b.values():
            for issue in task_issues:
                confidence = issue.get("confidence", 0.5)
                if confidence >= 0.8:
                    counts["high"] += 1
                elif confidence >= 0.6:
                    counts["medium"] += 1
                else:
                    counts["low"] += 1
        return counts

    # ------------------------------------------------------------------
    # Public execute
    # ------------------------------------------------------------------

    def execute(
        self,
        phase: WorkflowPhase,
        context: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        start = time.monotonic()
        _log_context_completeness("FINALIZE", context)
        logger.info("FINALIZE phase: generating summary (dry_run=%s)", dry_run)

        plan_title = context.get("plan_title", "Untitled")
        tasks: list[SeedTask] = _ensure_context_loaded(context)
        domain_summary = context.get("domain_summary", {})
        preflight_summary = context.get("preflight_summary", {})
        scaffold = context.get("scaffold", {})
        implementation = context.get("implementation", {})
        test_results = context.get("test_results", {})
        review_results = context.get("review_results", {})
        truncation_flags: dict[str, Any] = context.get("truncation_flags", {})

        # Collect artifacts and costs
        artifacts = self._collect_generated_artifacts(context)
        cost_summary = self._build_cost_summary(context)
        forensic_base_dir = Path(self.output_dir) if self.output_dir else Path(
            context.get("project_root", ".")
        )
        forensic_artifacts = self._persist_forensic_artifacts(
            context=context,
            output_dir=forensic_base_dir,
            dry_run=(dry_run or not bool(self.output_dir)),
        )
        context["forensic_artifacts"] = forensic_artifacts

        # Compute overall status rollup
        generation_results: dict[str, GenerationResult] = context.get(
            "generation_results", {}
        )
        total_tasks = len(tasks)
        generated_ok = sum(
            1 for r in generation_results.values() if r.success
        )
        generated_fail = sum(
            1 for r in generation_results.values() if not r.success
        )

        # Consider test/review outcomes in status rollup
        tests_failed = test_results.get("total_failed", 0)
        reviews_failed = review_results.get("total_failed", 0)
        tests_skipped = test_results.get("total_skipped", 0)

        if generated_fail == 0 and generated_ok == total_tasks:
            if tests_failed > 0 or reviews_failed > 0:
                overall_status = "quality_failed"
            elif tests_skipped > 0:
                overall_status = "partial"
            else:
                overall_status = "success"
        elif generated_ok == 0:
            overall_status = "failed"
        else:
            overall_status = "partial"

        summary: dict[str, Any] = {
            "plan_title": plan_title,
            "task_count": total_tasks,
            "status": overall_status,
            "tasks_succeeded": generated_ok,
            "tasks_failed": generated_fail,
            "domain_summary": domain_summary,
            "preflight_summary": preflight_summary,
            "scaffold_summary": {
                "dirs_needed": len(scaffold.get("directories_needed", [])),
                "dirs_created": len(scaffold.get("directories_created", [])),
                "existing_files": len(scaffold.get("existing_target_files", [])),
            },
            "implementation_summary": {
                "tasks_processed": implementation.get("tasks_processed", 0),
                "total_estimated_loc": implementation.get("total_estimated_loc", 0),
                "generation_results": {
                    tid: {
                        "success": r.success,
                        "error": r.error,
                        "cost_usd": r.cost_usd,
                        "files": [str(f) for f in r.generated_files],
                        "model": r.model,
                        "iterations": r.iterations,
                    }
                    for tid, r in generation_results.items()
                },
            },
            "test_summary": {
                "total_validators": test_results.get("total_validators", 0),
                "tasks_with_tests": test_results.get("tasks_with_tests", 0),
                "total_passed": test_results.get("total_passed", 0),
                "total_failed": test_results.get("total_failed", 0),
            },
            "review_summary": {
                "tasks_with_env_issues": review_results.get("tasks_with_env_issues", 0),
                "total_passed": review_results.get("total_passed", 0),
                "total_failed": review_results.get("total_failed", 0),
                "total_cost": review_results.get("total_cost", 0.0),
            },
            "quality_gate": context.get(
                "quality_gate_summary",
                {
                    "policy_mode": "warn",
                    "gate_count": 0,
                    "violation_count": 0,
                    "violations": [],
                },
            ),
            "truncation_summary": {
                "tasks_flagged": len(truncation_flags),
                "tasks_with_syntax_errors": sum(
                    1 for tf in truncation_flags.values()
                    if tf.get("syntax_errors")
                ),
                "max_confidence": max(
                    (tf.get("max_confidence", 0.0) for tf in truncation_flags.values()),
                    default=0.0,
                ),
                "flagged_task_ids": sorted(truncation_flags.keys()),
                "details": truncation_flags,
            } if truncation_flags else {"tasks_flagged": 0},
            "gate3b_validation": {},
            "cost_summary": cost_summary,
            "generated_artifacts": artifacts,
            "forensic_artifacts": forensic_artifacts,
            "artifact_count": len(artifacts),
            "dry_run": dry_run,
        }

        # PCA-402: attach onboarding consumption audit trail to provenance
        _onb_consumption = context.get("_onboarding_consumption")
        if _onb_consumption:
            summary.setdefault("provenance", {})["onboarding_fields_consumed"] = _onb_consumption

        # Task 11a: Gate 3b content validation summary
        gate3b_data: dict[str, Any] = implementation.get("_gate3b_content_validation", {})
        severity_counts: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
        if gate3b_data:
            try:
                severity_counts = FinalizePhaseHandler._count_gate3b_by_severity(gate3b_data)
                total_issues = sum(len(v) for v in gate3b_data.values())
                summary["gate3b_validation"] = {
                    "tasks_with_issues": len(gate3b_data),
                    "total_issues": total_issues,
                    "by_severity": severity_counts,
                    "flagged_task_ids": sorted(gate3b_data.keys()),
                }
                logger.info(
                    "FINALIZE: Gate 3b summary — %d task(s), %d issue(s) (high=%d, medium=%d, low=%d)",
                    len(gate3b_data), total_issues,
                    severity_counts["high"], severity_counts["medium"], severity_counts["low"],
                )
            except Exception as exc:
                logger.warning("FINALIZE: Gate 3b summary failed: %s", exc, exc_info=True)
                summary["gate3b_validation"] = {"error": str(exc)}

        # Task 11b: Strict validation blocking check
        strict_mode = context.get("strict_validation", False)
        if strict_mode and gate3b_data:
            high_count = severity_counts.get("high", 0)
            if high_count > 0:
                error_msg = (
                    f"--strict-validation: {high_count} high-severity Gate 3b issue(s) "
                    f"detected — failing FINALIZE. Review _gate3b_content_validation in "
                    f"implementation output for details."
                )
                logger.error(error_msg)
                summary["status"] = "failed"
                summary["strict_validation_error"] = error_msg

        # CCD-603: Design coherence summary
        summary["design_coherence"] = self._build_design_coherence_summary(context)

        # Write report and manifest
        if self.output_dir and not dry_run:
            output_dir = Path(self.output_dir)
            try:
                output_path = output_dir / "workflow-execution-report.json"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_json(output_path, summary, indent=2, default=str)
                logger.info("Wrote execution report to %s", output_path)
                summary["report_path"] = str(output_path)

                # Write manifest of generated files
                manifest_path = self._write_manifest(
                    artifacts, summary, context, output_dir,
                )
                if manifest_path:
                    summary["manifest_path"] = str(manifest_path)
            except Exception as exc:
                logger.error(
                    "FINALIZE: crash during report/manifest write: %s",
                    exc, exc_info=True,
                )
                # AR-815: Write partial manifest so prior phases' work is not lost
                try:
                    partial = {
                        "workflow_version": "0.4.0",
                        "incomplete": True,
                        "error": str(exc),
                        "artifacts": artifacts,
                        "task_status": {},
                        "summary": {"status": "incomplete"},
                    }
                    partial_path = output_dir / "generation-manifest.json"
                    partial_path.parent.mkdir(parents=True, exist_ok=True)
                    atomic_write_json(partial_path, partial, indent=2, default=str)
                    logger.info("Wrote partial manifest: %s", partial_path)
                    summary["manifest_path"] = str(partial_path)
                    summary["manifest_incomplete"] = True
                except OSError as write_exc:
                    logger.error("Failed to write partial manifest: %s", write_exc)

        context["workflow_summary"] = summary

        # Context contract: validate FINALIZE output model
        # R2-T6: Respect gate mode — block raises, warn flags, skip ignores.
        try:
            FinalizePhaseOutput(workflow_summary=context["workflow_summary"])
        except Exception as _val_exc:
            _gate_mode = context.get("quality_gate_summary", {}).get(
                "policy_mode", "warn",
            )
            if _gate_mode == "block":
                raise RuntimeError(
                    f"FINALIZE output validation failed (block policy): {_val_exc}"
                ) from _val_exc
            logger.warning(
                "FINALIZE output validation failed (continuing per %s policy): %s",
                _gate_mode,
                _val_exc,
            )
            if _gate_mode == "warn":
                summary["_validation_failed"] = True
                summary["_validation_error"] = str(_val_exc)

        duration = time.monotonic() - start

        logger.info(
            "FINALIZE phase complete: %s — %d artifacts, $%.4f total cost (%.2fs)",
            overall_status, len(artifacts),
            cost_summary.get("total_cost", 0.0), duration,
        )

        return {"output": summary, "cost": 0.0, "metadata": {"duration": duration}}


# ============================================================================
# Factory
# ============================================================================


class ContextSeedHandlers:
    """Factory for creating all phase handlers from an enriched context seed.

    Accepts optional agent configuration that is propagated to all handlers
    requiring LLM access (IMPLEMENT, TEST, REVIEW) and artifact generation
    (FINALIZE).

    Example::

        handlers = ContextSeedHandlers.create_all(
            enriched_seed_path="out/<route>-context-seed-enriched.json",
            output_dir="out/artifacts",
        )
    """

    @staticmethod
    def create_all(
        enriched_seed_path: str,
        output_dir: Optional[str] = None,
        *,
        # Agent configuration (keyword-only) — all Optional so callers
        # only pass what they explicitly want to override.  Missing keys
        # are resolved via the config-file / env-var / dataclass-default
        # priority chain in HandlerConfig.from_config().
        lead_agent: Optional[str] = None,
        drafter_agent: Optional[str] = None,
        max_iterations: Optional[int] = None,
        pass_threshold: Optional[int] = None,
        max_tokens: Optional[int] = None,
        design_max_tokens: Optional[int] = None,
        design_task_retries: Optional[int] = None,
        fail_on_truncation: Optional[bool] = None,
        check_truncation: Optional[bool] = None,
        strict_truncation: Optional[bool] = None,
        test_timeout_seconds: Optional[int] = None,
        review_temperature: Optional[float] = None,
        review_max_code_chars: Optional[int] = None,
        review_task_retries: Optional[int] = None,
        development_timeout_seconds: Optional[float] = None,
        auto_commit: Optional[bool] = None,
        scaffold_test_first: Optional[bool] = None,
        force_implement: Optional[bool] = None,
        force_design: Optional[bool] = None,
        refine_design: Optional[bool] = None,
        force_review: Optional[bool] = None,
        force_test: Optional[bool] = None,
        design_agent: Optional[str] = None,
        review_agent: Optional[str] = None,
        enable_prompt_caching: Optional[bool] = None,
        tier2_agent: Optional[str] = None,
        skip_refinement: Optional[bool] = None,
        walkthrough: Optional[bool] = None,
        enforce_post_revision_rereview: Optional[bool] = None,
        complexity_routing_enabled: Optional[bool] = None,
        tier3_agent: Optional[str] = None,
        complexity_blast_radius_tier3: Optional[int] = None,
        complexity_loc_tier1_max: Optional[int] = None,
        complexity_loc_tier3_min: Optional[int] = None,
        complexity_caller_tier3: Optional[int] = None,
        complexity_tier2_gate_escalation: Optional[bool] = None,
        code_generator: Optional[CodeGenerator] = None,
    ) -> dict[WorkflowPhase, AbstractPhaseHandler]:
        """Create handlers for all eight workflow phases.

        Args:
            enriched_seed_path: Path to the enriched context seed JSON.
            output_dir: Optional output directory for artifacts.
            lead_agent: Agent spec for architect/reviewer.
            drafter_agent: Agent spec for drafter.
            max_iterations: Maximum draft → review iterations per task.
            pass_threshold: Minimum review score (0-100) to pass.
            max_tokens: Override max_tokens for agent creation.
            fail_on_truncation: Fail workflow on detected truncation.
            check_truncation: Enable heuristic truncation detection.
            strict_truncation: Use strict detection threshold.
            test_timeout_seconds: Timeout for each validator subprocess.
            review_temperature: Temperature for LLM review calls.
            review_max_code_chars: Max chars of code in review prompt.
            development_timeout_seconds: Timeout for development thread.
            auto_commit: Commit each feature's generated code to git.
            scaffold_test_first: Scaffold test files for artifact tasks before impl.
            force_design: Ignore cached design handoff; always run fresh DESIGN.
            refine_design: Pass prior designs to LLM for refinement instead of adopting.
            force_review: Ignore cached review results; always run fresh REVIEW.
            force_test: Ignore cached test results; always run fresh TEST.
            design_agent: Agent spec for design phase (falls back to lead_agent).
            review_agent: Agent spec for review phase (falls back to lead_agent).
            enable_prompt_caching: Enable Anthropic prompt caching.
            tier2_agent: T2 refinement agent spec (default: Sonnet).
            skip_refinement: Skip T2 refinement (use T1 draft directly).
            walkthrough: Build and persist all LLM prompts without calling LLMs.
            enforce_post_revision_rereview: Require reviewer+arbiter re-review after revision.
            complexity_routing_enabled: Enable/disable complexity routing.
            tier3_agent: Tier 3 drafter agent spec override.
            complexity_blast_radius_tier3: Tier 3 blast radius threshold.
            complexity_loc_tier1_max: Tier 1 maximum estimated LOC.
            complexity_loc_tier3_min: Tier 3 minimum estimated LOC.
            complexity_caller_tier3: Tier 3 caller threshold (edit mode).
            complexity_tier2_gate_escalation: Gate-driven T2 escalation for Tier 2.
            code_generator: Deprecated. Previously used for code generation;
                now ignored. The artisan pipeline uses DevelopmentPhase with
                ``drafter_spec`` from HandlerConfig instead.

        Returns:
            Dict mapping WorkflowPhase → handler instance.
        """
        if code_generator is not None:
            warnings.warn(
                "ContextSeedHandlers.create_all(): 'code_generator' parameter "
                "is deprecated and ignored. The artisan pipeline now uses "
                "DevelopmentPhase with 'drafter_spec' from HandlerConfig "
                "instead. This parameter will be removed in a future release.",
                DeprecationWarning,
                stacklevel=2,
            )

        # Build cli_overrides from non-None kwargs
        cli_overrides: dict[str, Any] = {}
        for name, val in [
            ("lead_agent", lead_agent),
            ("drafter_agent", drafter_agent),
            ("max_iterations", max_iterations),
            ("pass_threshold", pass_threshold),
            ("max_tokens", max_tokens),
            ("design_max_tokens", design_max_tokens),
            ("design_task_retries", design_task_retries),
            ("fail_on_truncation", fail_on_truncation),
            ("check_truncation", check_truncation),
            ("strict_truncation", strict_truncation),
            ("test_timeout_seconds", test_timeout_seconds),
            ("review_temperature", review_temperature),
            ("review_max_code_chars", review_max_code_chars),
            ("review_task_retries", review_task_retries),
            ("development_timeout_seconds", development_timeout_seconds),
            ("auto_commit", auto_commit),
            ("scaffold_test_first", scaffold_test_first),
            ("force_implement", force_implement),
            ("force_design", force_design),
            ("refine_design", refine_design),
            ("force_review", force_review),
            ("force_test", force_test),
            ("design_agent", design_agent),
            ("review_agent", review_agent),
            ("enable_prompt_caching", enable_prompt_caching),
            ("tier2_agent", tier2_agent),
            ("skip_refinement", skip_refinement),
            ("walkthrough", walkthrough),
            ("enforce_post_revision_rereview", enforce_post_revision_rereview),
            ("complexity_routing_enabled", complexity_routing_enabled),
            ("tier3_agent", tier3_agent),
            ("complexity_blast_radius_tier3", complexity_blast_radius_tier3),
            ("complexity_loc_tier1_max", complexity_loc_tier1_max),
            ("complexity_loc_tier3_min", complexity_loc_tier3_min),
            ("complexity_caller_tier3", complexity_caller_tier3),
            ("complexity_tier2_gate_escalation", complexity_tier2_gate_escalation),
        ]:
            if val is not None:
                cli_overrides[name] = val

        config = HandlerConfig.from_config(cli_overrides or None)

        from startd8.contractors.context_seed.phases.design import (
            DesignPhaseHandler as _DesignPhaseHandler,
        )

        return {
            WorkflowPhase.PLAN: PlanPhaseHandler(enriched_seed_path),
            WorkflowPhase.SCAFFOLD: ScaffoldPhaseHandler(),
            WorkflowPhase.DESIGN: _DesignPhaseHandler(
                handler_config=config,
                output_dir=output_dir,
            ),
            WorkflowPhase.IMPLEMENT: ImplementPhaseHandler(
                handler_config=config,
                enriched_seed_path=Path(enriched_seed_path),
            ),
            WorkflowPhase.INTEGRATE: IntegratePhaseHandler(config=config),
            WorkflowPhase.TEST: TestPhaseHandler(handler_config=config),
            WorkflowPhase.REVIEW: ReviewPhaseHandler(handler_config=config),
            WorkflowPhase.FINALIZE: FinalizePhaseHandler(
                output_dir=output_dir,
                handler_config=config,
            ),
        }
