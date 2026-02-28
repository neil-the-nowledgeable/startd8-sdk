"""
Context Seed Phase Handlers for ArtisanContractorWorkflow.

Bridges enriched context seeds (from PlanIngestionWorkflow + DomainPreflightWorkflow)
to the ArtisanContractorWorkflow orchestrator by providing concrete AbstractPhaseHandler
implementations for each WorkflowPhase.

WorkflowPhase mapping (from artisan_contractor.py docstring):
    PLAN      → Load seed + validate + build task plan
    SCAFFOLD  → Verify target directories + resolve dependencies
    DESIGN    → Generate design docs per task via DesignDocumentationPhase
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
from typing import Any, Optional

from startd8.contractors.artisan_contractor import (
    AbstractPhaseHandler,
    WorkflowPhase,
    _SAFE_TASK_ID_PATTERN,
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
    DesignPhaseOutput,
    FinalizePhaseOutput,
    ImplementPhaseOutput,
    PlanPhaseOutput,
    ReviewPhaseOutput,
    ScaffoldPhaseOutput,
    ValidationPhaseOutput,
)
from startd8.contractors.artisan_contractor import HAS_OTEL, _NoOpTracer, _NoOpSpan
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

logger = get_logger(__name__)

# Module-level tracer — reuses the HAS_OTEL/_NoOpTracer pattern from
# artisan_contractor.py for per-task span instrumentation.
try:
    from opentelemetry import trace as _trace

    _phase_tracer = _trace.get_tracer("startd8.artisan.phases")
    _HAS_OTEL = True
except ImportError:
    _phase_tracer = _NoOpTracer()
    _HAS_OTEL = False

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
            mode=data["mode"],
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
    # CCD-203: Token budget for lane-peer design context injection
    design_lane_peer_token_budget: int = 8000
    # CCD-503: Collision resolution strategy ("warn" | "redesign" | "abort")
    design_collision_strategy: str = "warn"
    # V2 modular design prompts (single-pass, no dual-review)
    use_modular_prompts: bool = False
    # REQ-PAQ-701: rollout guardrail toggles.
    force_canonical_design_route: bool = False
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

    # REQ-IME-300: Opt-in inner loop — uses implementation_engine instead of
    # single-shot DevelopmentPhase.  Default False = no behavior change.
    # Cost: ~$2-5 per 10 tasks at avg 2 iterations (1 spec + up to 3 draft + 3 review).
    enable_inner_loop: bool = False
    inner_loop_drafter: Optional[str] = None   # Override drafter agent for inner loop
    inner_loop_reviewer: Optional[str] = None  # Override reviewer agent for inner loop
    inner_loop_max_iterations: int = 3         # Max draft-review cycles per task
    inner_loop_pass_threshold: int = 80        # Min review score (0-100)

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


# ============================================================================
# Shared data structures
# ============================================================================


@dataclass
class SeedTask:
    """Parsed task from an enriched context seed."""

    task_id: str
    title: str
    task_type: str
    story_points: int
    priority: str
    labels: list[str]
    depends_on: list[str]
    description: str
    target_files: list[str]
    estimated_loc: int
    feature_id: str
    # Enrichment fields
    domain: str
    domain_reasoning: str
    environment_checks: list[dict[str, Any]]
    prompt_constraints: list[str]
    post_generation_validators: list[str]
    available_siblings: list[str]
    existing_content_hash: Optional[str]
    # Task-specific design doc content hints (supplement calibration sections)
    design_doc_sections: list[str]
    # Artifact types this task generates (e.g. dashboard, prometheus_rule, servicemonitor)
    artifact_types_addressed: list[str]
    # File scope from plan ingestion (defense-in-depth Principle 1):
    # Maps target_file → "primary" | "shared" | "stub".
    # When present, artisan uses this instead of re-deriving from design docs.
    file_scope: dict[str, str]
    # Dependency allowlist source and confidence (Gate 5)
    deps_source: Optional[str] = None
    deps_confidence: float = 1.0
    # IMP-1: Verbatim requirements text from plan
    requirements_text: str = ""
    # IMP-4: Extended schema fields from ParsedFeature
    api_signatures: list[str] = field(default_factory=list)
    protocol: str = ""
    runtime_dependencies: list[str] = field(default_factory=list)
    negative_scope: list[str] = field(default_factory=list)
    # Wave+Lane execution: dependency-depth wave assignment
    wave_index: Optional[int] = None
    # REQ-CMR-042: Optional seed override of complexity tier
    complexity_tier_override: Optional[str] = None

    @classmethod
    def from_seed_entry(cls, entry: dict[str, Any]) -> SeedTask:
        """Parse a task entry from the enriched context seed JSON."""
        config = entry.get("config", {})
        context = config.get("context", {})
        enrichment = entry.get("_enrichment", {})

        # Merge prompt_hints (from plan ingestion shared-module detection)
        # with enrichment prompt_constraints (from domain preflight rules).
        constraints = list(enrichment.get("prompt_constraints", []))
        for hint in context.get("prompt_hints", []):
            if hint not in constraints:
                constraints.append(hint)

        # --- WCP-003: Emit context.defaulted span event when domain is missing ---
        domain = enrichment.get("domain", "unknown")
        if domain == "unknown":
            try:
                from opentelemetry import trace
                span = trace.get_current_span()
                if span and span.is_recording():
                    span.add_event("context.defaulted", attributes={
                        "context.field": "domain",
                        "context.default_value": "unknown",
                        "context.expected_source": "domain_preflight._enrichment",
                        "context.task_id": entry.get("task_id", ""),
                    })
            except Exception:
                logger.debug("OTel context not available", exc_info=True)
            logger.debug(
                "SeedTask %s: domain defaulted to 'unknown' (enrichment missing or incomplete)",
                entry.get("task_id", "?"),
            )

        # Compute deps_confidence from deps_source
        deps_source = enrichment.get("deps_source")
        _source_confidence = {
            "pyproject": 1.0,
            "requirements_txt": 0.85,
            "setup_cfg": 0.85,
            "venv_only": 0.5,
            "stdlib_only": 0.2,
        }
        deps_confidence = _source_confidence.get(deps_source, 1.0) if deps_source else 1.0

        # --- Task ID safety validation (defense-in-depth) ---
        raw_task_id = entry.get("task_id", "")
        if raw_task_id and not _SAFE_TASK_ID_PATTERN.match(raw_task_id):
            logger.warning(
                "Task ID %r contains unsafe characters (must match %s) — "
                "this may cause errors in wave computation, checkpoint keys, "
                "or file path construction",
                raw_task_id, _SAFE_TASK_ID_PATTERN.pattern,
            )

        # Validate depends_on entries for safe characters
        raw_depends = entry.get("depends_on") or []
        for dep_id in raw_depends:
            if isinstance(dep_id, str) and dep_id and not _SAFE_TASK_ID_PATTERN.match(dep_id):
                logger.warning(
                    "Task %s: depends_on reference %r contains unsafe characters "
                    "(must match %s)",
                    raw_task_id, dep_id, _SAFE_TASK_ID_PATTERN.pattern,
                )

        # --- Wave index parsing with validation ---
        raw_wave = entry.get("wave_index")
        if raw_wave is not None:
            if not isinstance(raw_wave, int) or isinstance(raw_wave, bool):
                logger.warning(
                    "Task %s: wave_index=%r is not an integer — ignoring",
                    entry.get("task_id"), raw_wave,
                )
                raw_wave = None
            elif raw_wave < 0:
                logger.warning(
                    "Task %s: wave_index=%d is negative — ignoring",
                    entry.get("task_id"), raw_wave,
                )
                raw_wave = None
        wave_index = raw_wave

        _override_raw = (
            context.get("complexity_tier_override")
            or config.get("complexity_tier_override")
            or entry.get("complexity_tier_override")
        )
        complexity_tier_override: Optional[str] = None
        if isinstance(_override_raw, str):
            _normalized = _override_raw.strip().lower()
            if _normalized in {"tier_1", "tier_2", "tier_3"}:
                complexity_tier_override = _normalized
            elif _normalized:
                logger.warning(
                    "Task %s: invalid complexity_tier_override %r (expected tier_1|tier_2|tier_3) — ignoring",
                    entry.get("task_id", "?"),
                    _override_raw,
                )

        task = cls(
            task_id=entry.get("task_id", ""),
            title=entry.get("title", ""),
            task_type=entry.get("task_type", "task"),
            story_points=entry.get("story_points", 0),
            priority=entry.get("priority", "medium"),
            labels=entry.get("labels", []),
            depends_on=entry.get("depends_on", []),
            description=config.get("task_description", ""),
            target_files=context.get("target_files", []),
            estimated_loc=context.get("estimated_loc", 0),
            feature_id=context.get("feature_id", ""),
            domain=domain,
            domain_reasoning=enrichment.get("domain_reasoning", ""),
            environment_checks=enrichment.get("environment_checks", []),
            prompt_constraints=constraints,
            post_generation_validators=enrichment.get(
                "post_generation_validators", []
            ),
            available_siblings=enrichment.get("available_siblings", []),
            existing_content_hash=enrichment.get("existing_content_hash"),
            design_doc_sections=context.get("design_doc_sections", []),
            artifact_types_addressed=context.get("artifact_types_addressed", []),
            file_scope=context.get("_file_scope", {}),
            deps_source=deps_source,
            deps_confidence=deps_confidence,
            requirements_text=config.get("requirements_text", ""),
            api_signatures=context.get("api_signatures", []),
            protocol=context.get("protocol", ""),
            runtime_dependencies=context.get("runtime_dependencies", []),
            negative_scope=context.get("negative_scope", []),
            wave_index=wave_index,
            complexity_tier_override=complexity_tier_override,
        )
        if not task.task_id:
            raise ValueError(f"Seed entry missing required field 'task_id': {entry}")
        if not task.title:
            raise ValueError(f"Seed entry missing required field 'title': {entry}")
        return task


def _load_enriched_seed(seed_path: str) -> dict[str, Any]:
    """Load and validate an enriched context seed JSON file."""
    path = Path(seed_path)
    if not path.exists():
        raise FileNotFoundError(f"Enriched seed not found: {seed_path}")

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("Enriched seed must be a JSON object")

    # Tasks live at the top level (from PlanIngestionWorkflow), not under plan
    if "tasks" not in data:
        raise ValueError("Enriched seed must contain a 'tasks' list")

    return data


def _parse_tasks(seed_data: dict[str, Any]) -> list[SeedTask]:
    """Parse all tasks from the enriched seed."""
    raw_tasks = seed_data.get("tasks", [])
    tasks = []
    for entry in raw_tasks:
        if isinstance(entry, dict):
            tasks.append(SeedTask.from_seed_entry(entry))
    return tasks


# --------------------------------------------------------------------------
# PCA-605d: Defense-in-depth design→implement file discovery (4 layers)
# --------------------------------------------------------------------------

# Layer 1: bold file markers (original PCA-605c)
_DESIGN_FILE_MARKER_RE = re.compile(r'\*\*File:\s*`([^`]+)`\*\*', re.MULTILINE)

# Layer 2: fenced code block file paths
_DESIGN_FENCED_BLOCK_RE = re.compile(r'```(\S*)\s*\n(.*?)```', re.DOTALL)
_DESIGN_FIRST_LINE_FILE_RE = re.compile(r'^(?://|#)\s*(\S+\.\w+)')

# Layer 3: prose "new file" signals near backtick-quoted filenames
_PROSE_NEW_FILE_RE = re.compile(
    r'(?:new\s+(?:file|module)|extract(?:ed)?\s+to|dedicated\s+(?:module|file)|'
    r'separate\s+(?:module|file)|split\s+(?:into|to)|'
    r'create\s+(?:a\s+)?(?:new\s+)?(?:module|file))'
    r'[^`]{0,80}`([^`]+\.\w{1,5})`',
    re.IGNORECASE | re.MULTILINE,
)
_CONDITIONAL_FILTER_RE = re.compile(
    r'\b(?:when|if\s+(?:needed|required)|eventually|later|future|'
    r'could\s+be|might\s+be)\b',
    re.IGNORECASE,
)

# Layer 4: structured ### Files Touched section (prompt-guided, primary)
_FILES_TOUCHED_SECTION_RE = re.compile(
    r'###\s*Files?\s+Touched\s*\n(.*?)(?=\n##|\n###|\Z)',
    re.IGNORECASE | re.DOTALL,
)
_FILES_TOUCHED_ENTRY_RE = re.compile(r'-\s*`([^`]+\.\w{1,5})`')

# Shared validation
_VALID_FILE_EXTENSIONS = frozenset({
    '.py', '.ts', '.tsx', '.js', '.jsx', '.yaml', '.yml',
    '.json', '.toml', '.cfg', '.sh', '.sql', '.html', '.css',
    '.go', '.rs', '.java', '.kt', '.rb',
})


def _infer_path_prefix(targets: list[str]) -> str:
    """Infer common directory prefix from existing target files."""
    if not targets:
        return ""
    first_target = targets[0]
    slash_idx = first_target.rfind("/")
    if slash_idx >= 0:
        return first_target[: slash_idx + 1]  # includes trailing '/'
    return ""


def _has_valid_extension(path: str) -> bool:
    """Check if path has a recognized source file extension."""
    dot_idx = path.rfind(".")
    if dot_idx < 0:
        return False
    return path[dot_idx:].lower() in _VALID_FILE_EXTENSIONS


def _extract_design_target_files(
    design_doc: str,
    current_targets: list[str],
) -> list[str]:
    """Parse a design document for file decisions and merge with current targets.

    Uses 4 extraction layers in priority order for defense-in-depth:

    - **Layer 4** (primary): ``### Files Touched`` structured section — the
      prompt-guided output format, most reliable when present.
    - **Layer 1** (fallback): ``**File: \\`name\\`**`` bold markers from
      PCA-605c.
    - **Layer 2** (fallback): Fenced code blocks with file paths in the
      language tag or a first-line comment.
    - **Layer 3** (fallback): Prose "new file" signals within 80 chars of a
      backtick-quoted filename, with a conditional-language filter to avoid
      false positives (e.g. "when a second consumer…").

    All layers accumulate into a single list → normalize bare filenames using
    prefix → filter by extension → dedup with ``dict.fromkeys`` → return
    merged list.

    Returns:
        Merged list of target files — original targets first (order preserved),
        then any newly discovered files appended.  Deduped via ``dict.fromkeys``.
    """
    prefix = _infer_path_prefix(current_targets)
    discovered: list[str] = []
    layer_counts: dict[str, int] = {}

    # --- Layer 4 (primary): ### Files Touched section ---
    section_match = _FILES_TOUCHED_SECTION_RE.search(design_doc)
    if section_match:
        entries = _FILES_TOUCHED_ENTRY_RE.findall(section_match.group(1))
        layer_counts["layer4_files_touched"] = len(entries)
        discovered.extend(entries)

    # --- Layer 1 (fallback): **File: `name`** bold markers ---
    bold_matches = _DESIGN_FILE_MARKER_RE.findall(design_doc)
    layer_counts["layer1_bold_markers"] = len(bold_matches)
    discovered.extend(bold_matches)

    # --- Layer 2 (fallback): fenced code blocks with file paths ---
    layer2_count = 0
    for block_match in _DESIGN_FENCED_BLOCK_RE.finditer(design_doc):
        lang_tag = block_match.group(1)
        block_body = block_match.group(2)

        # Check language tag for a file path (must contain '/' and valid ext)
        if lang_tag and "/" in lang_tag and _has_valid_extension(lang_tag):
            discovered.append(lang_tag)
            layer2_count += 1
            continue

        # Check first line for a file-path comment (# path/to/file.py)
        first_line = block_body.split("\n", 1)[0].strip()
        fl_match = _DESIGN_FIRST_LINE_FILE_RE.match(first_line)
        if fl_match:
            candidate = fl_match.group(1)
            if "/" in candidate and _has_valid_extension(candidate):
                discovered.append(candidate)
                layer2_count += 1
    layer_counts["layer2_fenced_blocks"] = layer2_count

    # --- Layer 3 (fallback): prose "new file" signals ---
    layer3_count = 0
    for prose_match in _PROSE_NEW_FILE_RE.finditer(design_doc):
        candidate = prose_match.group(1)
        # Conditional filter: check a 200-char window around the match
        start = max(0, prose_match.start() - 100)
        end = min(len(design_doc), prose_match.end() + 100)
        window = design_doc[start:end]
        if _CONDITIONAL_FILTER_RE.search(window):
            continue
        discovered.append(candidate)
        layer3_count += 1
    layer_counts["layer3_prose_signals"] = layer3_count

    if not discovered:
        return current_targets

    # Build lookups for contradictory-path deduplication (PCA-605d).
    # When current_targets already specify a path for a given basename,
    # the plan's path is authoritative — discovered paths that contradict
    # it are dropped to prevent mixed-layout target lists.
    _current_set = set(current_targets)
    _bn_to_target: dict[str, list[str]] = {}
    for _t in current_targets:
        _bn = _t.rsplit("/", 1)[-1] if "/" in _t else _t
        _bn_to_target.setdefault(_bn, []).append(_t)

    # Normalize bare filenames, filter by valid extension, and exclude test
    # files.  Test files are the TEST phase's responsibility — including them
    # here causes the drafter to generate test code instead of the primary
    # implementation artifact.
    normalized: list[str] = []
    _test_filtered: list[str] = []
    for raw in discovered:
        if "/" not in raw and prefix:
            # PCA-605d: if the bare filename already exists verbatim in
            # current_targets, keep it bare.  Prevents turning root-level
            # ``pyproject.toml`` into ``src/pkg/pyproject.toml``.
            if raw in _current_set:
                path = raw
            else:
                path = prefix + raw
        else:
            path = raw
        if not _has_valid_extension(path):
            continue
        # Exclude test files: tests/ directory, test_*.py, *_test.py
        _basename = path.rsplit("/", 1)[-1] if "/" in path else path
        if (
            path.startswith("tests/")
            or "/tests/" in path
            or _basename.startswith("test_")
            or _basename.endswith("_test.py")
        ):
            _test_filtered.append(path)
            continue
        normalized.append(path)
    if _test_filtered:
        logger.info(
            "PCA-605d: filtered %d test file(s) from design doc discovery "
            "(TEST phase handles these): %s",
            len(_test_filtered),
            _test_filtered,
        )

    if not normalized:
        return current_targets

    # PCA-605d: deduplicate contradictory paths — if a discovered path
    # shares a basename with exactly one current target but at a different
    # directory depth, drop it.  Prevents Layer 2 from injecting e.g.
    # ``src/pkg/pyproject.toml`` when the plan already has ``pyproject.toml``
    # at project root.
    _contradictions: list[str] = []
    _deduped: list[str] = []
    for path in normalized:
        _bn = path.rsplit("/", 1)[-1] if "/" in path else path
        target_paths = _bn_to_target.get(_bn, [])
        if (
            len(target_paths) == 1
            and path != target_paths[0]
            and path not in _current_set
        ):
            _contradictions.append(path)
            continue
        _deduped.append(path)
    if _contradictions:
        logger.info(
            "PCA-605d: dropped %d contradictory path(s) "
            "(basename conflicts with current targets): %s",
            len(_contradictions),
            _contradictions,
        )
    normalized = _deduped

    if not normalized:
        return current_targets

    # Merge: original order first, then new discoveries (deduped).
    merged = list(dict.fromkeys(current_targets + normalized))

    logger.debug(
        "PCA-605d file discovery layers: %s, discovered=%d, merged=%d",
        layer_counts, len(normalized), len(merged),
    )

    return merged


# ============================================================================
# Handoff enrichment helpers — Gaps 1-5
# ============================================================================

# Regex for file-level action annotations: `path/to/file.py` (modify)
_FILE_ACTION_RE = re.compile(
    r'-\s*`([^`]+\.\w{1,5})`\s*(?:\((\w+)\))?',
)

# Regex for element-level references: backtick-quoted identifiers
_ELEMENT_REF_RE = re.compile(
    r'`(\w[\w.]*(?:\([^)]*\))?)`',
)

# Common element action verbs in design docs
_ACTION_VERB_RE = re.compile(
    r'^(add|create|new|introduce|modify|update|change|alter|preserve|keep|retain)',
    re.IGNORECASE,
)


def _extract_structural_delta(
    design_doc: str,
) -> dict[str, list[dict[str, str]]]:
    """Extract per-file structural intent from a design document.

    Parses the ``### Files Touched`` section for file-level create/modify
    annotations and element-level action descriptions.

    Args:
        design_doc: The raw design document text.

    Returns:
        ``{filepath: [{"element": "...", "action": "add|modify|preserve",
        "detail": "..."}]}``  Empty dict if no ``### Files Touched`` section
        is found or the section has no parseable entries.
    """
    delta: dict[str, list[dict[str, str]]] = {}
    section_match = _FILES_TOUCHED_SECTION_RE.search(design_doc)
    if not section_match:
        return delta

    section_text = section_match.group(1)
    current_file: str | None = None
    current_action = "modify"

    for line in section_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        # File entry: - `path/to/file.py` (modify)
        file_match = _FILE_ACTION_RE.match(stripped)
        if file_match:
            current_file = file_match.group(1)
            action_hint = (file_match.group(2) or "modify").lower()
            if action_hint in ("create", "new"):
                current_action = "add"
            elif action_hint in ("modify", "update", "change"):
                current_action = "modify"
            elif action_hint in ("preserve", "keep"):
                current_action = "preserve"
            else:
                current_action = action_hint
            delta.setdefault(current_file, [])
            continue

        # Sub-item under a file (indented bullet or description)
        if current_file and stripped.startswith("-"):
            element_text = stripped.lstrip("- ").strip()
            element_action = current_action
            element_name = ""

            # Detect action verb at start of line
            verb_match = _ACTION_VERB_RE.match(element_text)
            if verb_match:
                verb = verb_match.group(1).lower()
                if verb in ("add", "create", "new", "introduce"):
                    element_action = "add"
                elif verb in ("modify", "update", "change", "alter"):
                    element_action = "modify"
                elif verb in ("preserve", "keep", "retain"):
                    element_action = "preserve"

            # Extract element name from backtick references
            elem_refs = _ELEMENT_REF_RE.findall(element_text)
            if elem_refs:
                element_name = elem_refs[0]

            delta[current_file].append({
                "element": element_name,
                "action": element_action,
                "detail": element_text,
            })

    return delta


def _extract_referenced_elements(
    design_doc: str,
    manifest_elements: dict[str, list[str]] | None = None,
) -> dict[str, list[str]]:
    """Extract element names referenced in a design document.

    Scans the entire design doc for backtick-quoted identifiers that look
    like code elements (class names, function names, FQNs).  When a manifest
    is provided, only elements that match known manifest entries are included
    (reducing noise from prose references like ``True`` or ``None``).

    Args:
        design_doc: The raw design document text.
        manifest_elements: Optional ``{filepath: [element_name, ...]}`` from
            the manifest registry for cross-validation.

    Returns:
        ``{filepath: [element_name, ...]}`` of elements referenced in the
        design doc that correspond to manifest entries.  Empty dict when
        no manifest is provided or no cross-references are found.
    """
    if not manifest_elements:
        return {}

    # Build reverse lookup: element_name → filepath
    elem_to_file: dict[str, str] = {}
    for fpath, elements in manifest_elements.items():
        for elem in elements:
            # Store both full FQN and simple name
            elem_to_file[elem] = fpath
            if "." in elem:
                simple = elem.rsplit(".", 1)[-1]
                elem_to_file.setdefault(simple, fpath)

    # Scan design doc for backtick-quoted references
    referenced: dict[str, list[str]] = {}
    for ref in _ELEMENT_REF_RE.findall(design_doc):
        # Strip trailing parentheses for matching
        clean_ref = ref.rstrip(")")
        if "(" in clean_ref:
            clean_ref = clean_ref[:clean_ref.index("(")]
        fpath = elem_to_file.get(clean_ref) or elem_to_file.get(ref)
        if fpath:
            referenced.setdefault(fpath, [])
            if clean_ref not in referenced[fpath]:
                referenced[fpath].append(clean_ref)

    return referenced


def _compute_manifest_file_checksums(
    target_files: list[str],
    project_root: str,
) -> dict[str, str]:
    """Compute SHA-256 checksums for target files at design time.

    Args:
        target_files: List of file paths (relative to project_root).
        project_root: Absolute path to the project root.

    Returns:
        ``{filepath: sha256_hex}`` for files that exist and are readable.
    """
    checksums: dict[str, str] = {}
    root = Path(project_root) if project_root else None
    if not root:
        return checksums

    for fpath in target_files:
        full = root / fpath
        if full.exists() and full.is_file():
            try:
                content = full.read_bytes()
                checksums[fpath] = hashlib.sha256(content).hexdigest()
            except OSError as exc:
                logger.debug("Checksum computation failed for %s: %s", fpath, exc)
    return checksums


# ============================================================================
# CCD: Context Correctness by Design helpers
# ============================================================================

# CCD-601/602: Canonical span attribute names for design-phase lane-awareness.
# Changing these names breaks dashboard queries documented in
# docs/design/artisan/plans/CCD_LAYER6_TEMPO_QUERIES.md
_CCD_DESIGN_SPAN_ATTRS = frozenset({
    "task.lane_index",
    "task.lane_peer_count",
    "task.shared_file_count",
    "task.lane_prior_designs_count",
    "task.lane_prior_designs_truncated",
    "design.collision_severity",
})


def _normalize_target_path(path: str) -> str:
    """Normalize a target file path for comparison (CCD-300)."""
    return os.path.normpath(path).replace("\\", "/")


def build_shared_file_manifest(
    tasks: list[SeedTask],
) -> dict[str, list[str]]:
    """Build mapping from target file paths to task IDs that target them.

    Only files targeted by 2+ tasks are included (CCD-300).
    """
    file_to_tasks: dict[str, list[str]] = defaultdict(list)
    for task in tasks:
        for tf in (task.target_files or []):
            normalized = _normalize_target_path(tf)
            file_to_tasks[normalized].append(task.task_id)
    return {
        path: task_ids
        for path, task_ids in file_to_tasks.items()
        if len(task_ids) >= 2
    }


def compute_lane_to_file_mapping(
    lanes: list[list[SeedTask]],
    shared_file_manifest: dict[str, list[str]],
) -> dict[int, list[str]]:
    """For each lane, which shared files caused its formation (CCD-302)."""
    mapping: dict[int, list[str]] = {}
    for lane_idx, lane_tasks in enumerate(lanes):
        lane_task_ids = {t.task_id for t in lane_tasks}
        lane_files = [
            fpath for fpath, contesting_ids in shared_file_manifest.items()
            if len(lane_task_ids & set(contesting_ids)) >= 2
        ]
        if lane_files:
            mapping[lane_idx] = sorted(lane_files)
    return mapping


def compute_critical_path_tasks(
    tasks: list[SeedTask],
    shared_file_manifest: dict[str, list[str]],
    top_fraction: float = 0.20,
) -> set[str]:
    """Identify tasks with highest shared-file contention score (CCD-403).

    Contention score = sum of (len(contesting_task_ids) - 1) across
    all of a task's target files that appear in the manifest.
    """
    if not tasks or not shared_file_manifest:
        return set()

    scores: dict[str, int] = {}
    for task in tasks:
        score = 0
        for tf in (task.target_files or []):
            normalized = _normalize_target_path(tf)
            contesting = shared_file_manifest.get(normalized, [])
            score += max(0, len(contesting) - 1)
        scores[task.task_id] = score

    contested_scores = [s for s in scores.values() if s > 0]
    if not contested_scores:
        return set()

    threshold_idx = max(0, int(len(contested_scores) * (1 - top_fraction)))
    sorted_scores = sorted(contested_scores)
    score_threshold = (
        sorted_scores[threshold_idx]
        if threshold_idx < len(sorted_scores)
        else sorted_scores[-1]
    )
    return {
        tid for tid, score in scores.items()
        if score >= score_threshold and score > 0
    }


def _format_lane_peer_context(
    lane_prior_designs: list[dict[str, Any]],
    shared_file_manifest: dict[str, list[str]] | None,
    current_task: SeedTask,
) -> str:
    """Format lane-peer designs with compatibility instruction (CCD-202)."""
    if not lane_prior_designs:
        return ""

    lines = [
        "=== LANE-PEER DESIGN CONTEXT ===",
        "The following tasks share files with this task. Your design MUST be "
        "compatible with their designs.\n",
    ]
    current_files = set(
        _normalize_target_path(f) for f in (current_task.target_files or [])
    )
    for peer in lane_prior_designs:
        tid = peer.get("task_id", "unknown")
        title = peer.get("title", "")
        doc = peer.get("design_document", "")

        # Find shared files between current task and this peer
        shared = []
        if shared_file_manifest:
            for fpath, contesting in shared_file_manifest.items():
                if tid in contesting and fpath in current_files:
                    shared.append(fpath)

        lines.append(f"--- Peer: {tid} ({title}) ---")
        if shared:
            lines.append(f"  Shared files: {', '.join(sorted(shared))}")
        lines.append(doc)
        lines.append(f"--- End: {tid} ---\n")

    lines.append("=== END LANE-PEER DESIGN CONTEXT ===")
    return "\n".join(lines)


def _apply_lane_peer_token_budget(
    lane_prior_designs: list[dict[str, Any]],
    budget_tokens: int,
) -> tuple[list[dict[str, Any]], bool]:
    """Apply token budget guard to lane-peer designs (CCD-203).

    Estimate tokens via chars / 4. When over budget, truncate oldest
    peers to 300-char summaries (most recent keeps full doc).

    Returns:
        (designs, was_truncated) — designs with oldest truncated if needed.
    """
    if not lane_prior_designs or budget_tokens <= 0:
        return lane_prior_designs, False

    total_chars = sum(
        len(d.get("design_document", "")) for d in lane_prior_designs
    )
    estimated_tokens = total_chars // 4

    if estimated_tokens <= budget_tokens:
        return lane_prior_designs, False

    # Truncate oldest peers first, keep most recent full
    result = list(lane_prior_designs)
    was_truncated = False
    for i in range(len(result) - 1):  # Skip last (most recent)
        doc = result[i].get("design_document", "")
        if len(doc) > 300:
            result[i] = {
                **result[i],
                "design_document": doc[:300].split("\n")[0] + " [truncated]",
            }
            was_truncated = True
            # Re-check budget
            total_chars = sum(
                len(d.get("design_document", "")) for d in result
            )
            if total_chars // 4 <= budget_tokens:
                break

    if was_truncated:
        logger.warning(
            "CCD-203: lane-peer token budget exceeded — truncated %d/%d older peers",
            sum(1 for d in result[:-1] if "[truncated]" in d.get("design_document", "")),
            len(result) - 1,
        )
    return result, was_truncated


def _compute_ccd_task_metadata(
    task: SeedTask,
    lane_assignments: dict[str, int],
    design_lanes: list[list] | None,
    total_task_count: int,
    shared_file_manifest: dict[str, list[str]],
    critical_task_ids: set[str],
) -> dict[str, Any]:
    """Compute CCD metadata fields for a single design result entry (CCD-401).

    Returns a dict to merge into ``design_results[task.task_id]``.
    Shared between adopted-design and fresh-design success paths.
    """
    return {
        "wave_index": task.wave_index,
        "lane_index": lane_assignments.get(task.task_id, 0),
        "lane_peer_count": (
            len(design_lanes[lane_assignments[task.task_id]]) - 1
            if design_lanes and task.task_id in lane_assignments
            else total_task_count - 1
        ),
        "shared_file_count": sum(
            1 for f in (task.target_files or [])
            if _normalize_target_path(f) in shared_file_manifest
        ),
        "critical_path": task.task_id in critical_task_ids,
    }


def _topological_sort(tasks: list[SeedTask]) -> list[SeedTask]:
    """Sort tasks by dependency order (tasks with no deps first).

    Uses DFS with gray/black coloring to detect cycles.  If a cycle is
    found, logs a warning with the involved task IDs and falls back to
    the original input order (safe — the orchestrator can still run, it
    just won't guarantee prerequisite ordering).
    """
    id_to_task = {t.task_id: t for t in tasks}
    # WHITE = not visited, GRAY = in current DFS path, BLACK = finished
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {t.task_id: WHITE for t in tasks}
    result: list[str] = []
    cycle_members: list[str] = []

    def visit(task_id: str) -> bool:
        """Return True if a cycle was detected."""
        state = color.get(task_id, BLACK)  # unknown IDs treated as done
        if state == BLACK:
            return False
        if state == GRAY:
            cycle_members.append(task_id)
            return True

        color[task_id] = GRAY
        task = id_to_task.get(task_id)
        if task:
            for dep_id in task.depends_on:
                if visit(dep_id):
                    cycle_members.append(task_id)
                    return True
        color[task_id] = BLACK
        result.append(task_id)
        return False

    has_cycle = False
    for t in tasks:
        if color[t.task_id] == WHITE:
            if visit(t.task_id):
                has_cycle = True
                break

    if has_cycle:
        logger.warning(
            "Dependency cycle detected among tasks: %s — "
            "falling back to original seed order",
            " → ".join(reversed(cycle_members)),
        )
        return list(tasks)

    return [id_to_task[tid] for tid in result if tid in id_to_task]


def _ensure_context_loaded(context: dict[str, Any]) -> list[SeedTask]:
    """Return the task list from context, reloading from seed if needed.

    After a checkpoint resume the context dict is empty because the
    orchestrator does not persist it.  Every handler that needs tasks
    calls this helper, which transparently reloads the seed when the
    PLAN phase's data is absent.
    """
    def _apply_runtime_task_selection(tasks_in: list[SeedTask]) -> list[SeedTask]:
        """Apply runtime selection (feature-serial single-task execution).

        PLAN-level ``task_filter`` is already applied when tasks are loaded.
        Here we only apply per-feature narrowing used by feature-serial mode.
        """
        current_feature_id = context.get("current_feature_id")
        if not current_feature_id:
            return tasks_in

        selected = [t for t in tasks_in if t.task_id == current_feature_id]
        if not selected:
            known = [t.task_id for t in tasks_in]
            raise RuntimeError(
                "Feature-serial execution requested unknown current_feature_id="
                f"{current_feature_id!r}. Available task_ids: {known}"
            )
        return selected

    tasks: list[SeedTask] | None = context.get("tasks")
    if tasks is not None:
        return _apply_runtime_task_selection(tasks)

    seed_path = context.get("enriched_seed_path")
    if not seed_path:
        raise RuntimeError(
            "Context missing 'tasks' and 'enriched_seed_path' — "
            "cannot reload seed. If resuming from checkpoint, ensure "
            "'enriched_seed_path' is provided in the initial context."
        )

    seed_path_obj = Path(seed_path)
    if not seed_path_obj.exists():
        raise FileNotFoundError(
            f"Enriched seed not found at '{seed_path}' — cannot reload tasks. "
            f"Ensure the seed file exists and the path is correct."
        )

    logger.info("Reloading enriched seed for resumed workflow from %s", seed_path)
    seed_data = _load_enriched_seed(seed_path)
    tasks = _topological_sort(_parse_tasks(seed_data))

    # Apply task filter so resumed workflows honour --task-filter.
    task_filter = context.get("task_filter")
    if task_filter:
        filter_set = set(task_filter)
        tasks = [t for t in tasks if t.task_id in filter_set]
        logger.info(
            "Applied task filter on reload — %d task(s): %s",
            len(tasks),
            [t.task_id for t in tasks],
        )

    # Re-populate the keys that PlanPhaseHandler normally sets
    plan_meta = seed_data.get("plan", {})
    preflight = seed_data.get("_preflight", {})

    context["tasks"] = tasks
    context["task_index"] = {t.task_id: t for t in tasks}
    context["plan_title"] = plan_meta.get("title", "Untitled Plan")
    context["plan_goals"] = plan_meta.get("goals", [])
    context["preflight_summary"] = preflight.get("check_summary", {})
    domain_counts: dict[str, int] = defaultdict(int)
    for t in tasks:
        domain_counts[t.domain] += 1
    context["domain_summary"] = dict(domain_counts)
    context["total_estimated_loc"] = sum(t.estimated_loc for t in tasks)
    context["example_artifacts"] = (seed_data.get("artifacts") or {}).get(
        "example_artifacts", {}
    )

    # Restore Phase 2 data flow keys as defense-in-depth fallback.
    # These originate from PLAN phase (via the enriched seed's artifacts and
    # top-level keys) and are persisted via _CHECKPOINT_CONTEXT_KEYS, but if
    # checkpoint serialization dropped any of them, re-extract from the seed
    # rather than silently losing them.
    _artifacts = seed_data.get("artifacts") or {}
    context.setdefault("source_checksum", _artifacts.get("source_checksum") or "")
    context.setdefault("parameter_sources", _artifacts.get("parameter_sources", {}))
    context.setdefault("semantic_conventions", _artifacts.get("semantic_conventions", {}))
    context.setdefault("output_conventions", _artifacts.get("output_conventions", {}))
    context.setdefault("architectural_context", seed_data.get("architectural_context", {}))
    context.setdefault("design_calibration", seed_data.get("design_calibration", {}))
    context.setdefault("project_metadata", seed_data.get("project_metadata", {}))

    # PCA-201: re-extract onboarding fields as defense-in-depth.
    _onboarding = seed_data.get("onboarding") or {}
    _pca_fields = {
        "onboarding_derivation_rules": _onboarding.get("derivation_rules"),
        "onboarding_resolved_parameters": _onboarding.get("resolved_artifact_parameters"),
        "onboarding_output_contracts": _onboarding.get("expected_output_contracts"),
        "onboarding_calibration_hints": _onboarding.get("design_calibration_hints"),
        "onboarding_open_questions": _onboarding.get("open_questions"),
        "onboarding_dependency_graph": _onboarding.get("artifact_dependency_graph"),
        "service_metadata": _onboarding.get("service_metadata"),
        "onboarding_schema_features": (
            _onboarding.get("capabilities", {}).get("schema_features")
            or _onboarding.get("schema_features")
        ),
    }
    _restored = 0
    for key, value in _pca_fields.items():
        if key not in context:
            context[key] = value
            _restored += 1
    if _restored:
        logger.info("Restored %d/8 onboarding fields from seed on resume", _restored)

    # IMP-8b: extract structured refine suggestions from onboarding
    if "onboarding_refine_suggestions" not in context:
        _refine_sug = _onboarding.get("refine_suggestions")
        if _refine_sug and isinstance(_refine_sug, list):
            context["onboarding_refine_suggestions"] = _refine_sug
            logger.info(
                "Restored onboarding_refine_suggestions from seed (%d entries)",
                len(_refine_sug),
            )

    # IMP-9c: extract refine provenance from seed artifacts
    if "refine_provenance" not in context:
        _refine_prov = _artifacts.get("refine_provenance")
        if _refine_prov and isinstance(_refine_prov, dict):
            context["refine_provenance"] = _refine_prov
            logger.info("Restored refine_provenance from seed artifacts")

    # PCA-201: re-load plan_document_text from seed artifacts
    if "plan_document_text" not in context:
        plan_doc_path_str = _artifacts.get("plan_document_path")
        if plan_doc_path_str:
            _pdp = Path(plan_doc_path_str)
            if not _pdp.is_absolute():
                _pdp = Path(seed_path).parent / _pdp
            if _pdp.exists():
                try:
                    context["plan_document_text"] = _pdp.read_text(encoding="utf-8")
                    logger.info("Restored plan_document_text from seed on resume")
                except OSError:
                    logger.debug("Could not read file: %s", _pdp, exc_info=True)

    return _apply_runtime_task_selection(tasks)


# ============================================================================
# Phase Handlers
# ============================================================================

# PCA-104: project-level context fields for completeness logging.
_PCA_CONTEXT_FIELDS = (
    "project_root", "service_metadata", "plan_document_text",
    "architectural_context", "project_metadata",
    "onboarding_derivation_rules",
    "onboarding_resolved_parameters", "onboarding_output_contracts",
    "onboarding_calibration_hints", "onboarding_open_questions",
    "onboarding_dependency_graph", "onboarding_schema_features",
)


def _log_context_completeness(phase_name: str, context: dict[str, Any]) -> None:
    """PCA-104: Log which project-level context fields are present at phase entry."""
    present = [f for f in _PCA_CONTEXT_FIELDS if context.get(f) is not None]
    count = len(present)
    total = len(_PCA_CONTEXT_FIELDS)
    logger.info(
        "%s: project context %d/%d fields present", phase_name, count, total,
    )
    if count < 3:
        logger.warning(
            "%s: degraded project context — only %d/%d fields available, "
            "code quality may be reduced",
            phase_name, count, total,
        )


def _track_onboarding_consumption(
    context: dict[str, Any], field_name: str, phase_name: str,
) -> None:
    """PCA-402: Record that a phase consumed an onboarding field."""
    audit = context.setdefault("_onboarding_consumption", {})
    audit.setdefault(field_name, [])
    if phase_name not in audit[field_name]:
        audit[field_name].append(phase_name)


class PlanPhaseHandler(AbstractPhaseHandler):
    """PLAN phase: Load enriched seed, validate, build execution plan.

    Populates context with parsed tasks, dependency order, and domain summary.
    """

    def __init__(self, enriched_seed_path: str) -> None:
        self.enriched_seed_path = enriched_seed_path

    def execute(
        self,
        phase: WorkflowPhase,
        context: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        start = time.monotonic()
        logger.info("PLAN phase: loading enriched seed from %s", self.enriched_seed_path)

        # Load and parse
        seed_data = _load_enriched_seed(self.enriched_seed_path)
        tasks = _parse_tasks(seed_data)
        sorted_tasks = _topological_sort(tasks)

        # Apply task filter if provided (e.g. --task-filter PI-001,PI-002).
        # This narrows the execution to a subset of tasks while preserving
        # the full seed's architectural context and calibration data.
        task_filter = context.get("task_filter")
        if task_filter:
            filter_set = set(task_filter)
            all_ids = {t.task_id for t in sorted_tasks}
            all_count = len(sorted_tasks)
            sorted_tasks = [t for t in sorted_tasks if t.task_id in filter_set]
            missing = filter_set - all_ids
            if missing:
                # Show available IDs so the user can spot typos (e.g. P1-001 vs PI-001)
                sample = sorted(all_ids)[:10]
                suffix = f" ... ({all_count} total)" if all_count > 10 else ""
                raise ValueError(
                    f"Task filter IDs not found in seed: {', '.join(sorted(missing))}. "
                    f"Available IDs: {', '.join(sample)}{suffix}"
                )
            logger.info(
                "PLAN phase: task filter applied — %d of %d tasks selected: %s",
                len(sorted_tasks), all_count,
                [t.task_id for t in sorted_tasks],
            )



        # Extract plan metadata
        plan_meta = seed_data.get("plan", {})
        preflight = seed_data.get("_preflight", {})

        # Domain summary (computed over filtered tasks)
        domain_counts: dict[str, int] = defaultdict(int)
        for t in sorted_tasks:
            domain_counts[t.domain] += 1

        # Check summary from preflight
        check_summary = preflight.get("check_summary", {})
        fail_count = check_summary.get("fail", 0)

        # Populate context for downstream phases.
        # Note: we intentionally do NOT store the raw seed_data blob in
        # context — it can be large and is not needed after parsing.  If a
        # checkpoint resume needs it, _ensure_context_loaded re-reads the file.
        context["enriched_seed_path"] = self.enriched_seed_path
        context["tasks"] = sorted_tasks
        context["task_index"] = {t.task_id: t for t in sorted_tasks}
        context["plan_title"] = plan_meta.get("title", "Untitled Plan")
        context["plan_goals"] = plan_meta.get("goals", [])
        context["domain_summary"] = dict(domain_counts)
        context["preflight_summary"] = check_summary
        context["total_estimated_loc"] = sum(t.estimated_loc for t in sorted_tasks)
        context["architectural_context"] = seed_data.get("architectural_context", {})
        context["design_calibration"] = seed_data.get("design_calibration", {})
        # Operational project metadata (criticality, risks, SLOs) from ContextCore manifest
        context["project_metadata"] = seed_data.get("project_metadata", {})
        # Item 9: example artifacts per type for implement phase
        context["example_artifacts"] = (seed_data.get("artifacts") or {}).get(
            "example_artifacts", {}
        )

        # REQ-PD-002: Forward complexity data from seed to context
        _complexity = seed_data.get("complexity") or {}
        context["complexity_dimensions"] = _complexity.get("dimensions", {})
        context["complexity_composite"] = _complexity.get("composite")

        # -- Phase 2 data flow fixes: extract ContextCore enrichment --
        _artifacts = seed_data.get("artifacts") or {}

        # Fix 1a: provenance chain — source_checksum
        source_checksum = _artifacts.get("source_checksum")
        context["source_checksum"] = source_checksum or ""
        if source_checksum:
            logger.info(
                "PLAN phase: source_checksum present — provenance chain active: %s",
                source_checksum[:16],
            )
        else:
            logger.warning(
                "PLAN phase: source_checksum absent in seed — provenance chain broken"
            )

        # Fix 2b: parameter_sources for DESIGN/IMPLEMENT prompt injection
        context["parameter_sources"] = _artifacts.get("parameter_sources", {})

        # Fix 3b: semantic_conventions for DESIGN/IMPLEMENT prompt injection
        context["semantic_conventions"] = _artifacts.get("semantic_conventions", {})

        # Fix 5a: output_conventions for SCAFFOLD extension validation
        context["output_conventions"] = _artifacts.get("output_conventions", {})

        # Mottainai: forward inventory-equivalent fields from onboarding so
        # DESIGN phase can fall back to them when artifact inventory is absent.
        _onboarding = seed_data.get("onboarding") or {}
        context["onboarding_derivation_rules"] = _onboarding.get("derivation_rules")
        context["onboarding_resolved_parameters"] = _onboarding.get(
            "resolved_artifact_parameters"
        )
        context["onboarding_output_contracts"] = _onboarding.get(
            "expected_output_contracts"
        )
        context["onboarding_calibration_hints"] = _onboarding.get(
            "design_calibration_hints"
        )
        context["onboarding_open_questions"] = _onboarding.get("open_questions")
        # B4: artifact dependency graph from ContextCore export
        context["onboarding_dependency_graph"] = _onboarding.get(
            "artifact_dependency_graph"
        )
        # AR-144/AR-147: service metadata for protocol fidelity validators
        context["service_metadata"] = _onboarding.get("service_metadata")
        # REQ-EFE-021: schema_features for edit-first enforcement gate
        context["onboarding_schema_features"] = (
            _onboarding.get("capabilities", {}).get("schema_features")
            or _onboarding.get("schema_features")
        )
        _fwd_count = sum(
            1 for k in [
                "onboarding_derivation_rules", "onboarding_resolved_parameters",
                "onboarding_output_contracts", "onboarding_calibration_hints",
                "onboarding_open_questions", "onboarding_dependency_graph",
                "service_metadata", "onboarding_schema_features",
            ] if context.get(k)
        )
        if _fwd_count:
            logger.info(
                "PLAN phase: forwarded %d/8 onboarding inventory fields into context",
                _fwd_count,
            )

        # Mottainai B2+B3: read the plan document (produced by TRANSFORM)
        # directly from the seed's artifacts so DESIGN can use it as fallback
        # when the inventory path (run-provenance.json) is unavailable.
        plan_doc_path_str = _artifacts.get("plan_document_path")
        if plan_doc_path_str:
            plan_doc_path = Path(plan_doc_path_str)
            # Resolve relative to enriched_seed_path parent (same output dir)
            if not plan_doc_path.is_absolute():
                seed_parent = Path(self.enriched_seed_path).parent
                plan_doc_path = seed_parent / plan_doc_path
            if plan_doc_path.exists():
                try:
                    plan_text = plan_doc_path.read_text(encoding="utf-8")
                    context["plan_document_text"] = plan_text
                    logger.info(
                        "PLAN phase: loaded plan document (%d chars) for DESIGN fallback",
                        len(plan_text),
                    )
                except OSError:
                    logger.debug("Could not read file: %s", plan_doc_path, exc_info=True)

        output = {
            "plan_title": context["plan_title"],
            "task_count": len(sorted_tasks),
            "execution_order": [t.task_id for t in sorted_tasks],
            "domain_summary": dict(domain_counts),
            "preflight_check_summary": check_summary,
            "total_estimated_loc": context["total_estimated_loc"],
            "preflight_failures": fail_count,
            "goals": context["plan_goals"],
        }
        if task_filter:
            output["task_filter"] = task_filter

        duration = time.monotonic() - start
        logger.info(
            "PLAN phase complete: %d tasks, %d domains, %d preflight failures (%.2fs)",
            len(sorted_tasks), len(domain_counts), fail_count, duration,
        )

        if fail_count > 0 and not dry_run:
            logger.warning(
                "PLAN phase: %d preflight failures detected — review before implementing",
                fail_count,
            )
            if context.get("abort_on_preflight_fail"):
                raise ValueError(
                    f"PLAN phase aborted: {fail_count} preflight failure(s) detected. "
                    "Address preflight issues before proceeding, or run without --abort-on-preflight-fail."
                )

        # Context contract: validate PLAN output model
        PlanPhaseOutput(
            enriched_seed_path=context["enriched_seed_path"],
            tasks=context["tasks"],
            task_index=context["task_index"],
            plan_title=context["plan_title"],
            plan_goals=context["plan_goals"],
            domain_summary=context["domain_summary"],
            preflight_summary=context["preflight_summary"],
            total_estimated_loc=context["total_estimated_loc"],
            architectural_context=context.get("architectural_context", {}),
            design_calibration=context.get("design_calibration", {}),
            example_artifacts=context.get("example_artifacts", {}),
            source_checksum=context.get("source_checksum"),
            parameter_sources=context.get("parameter_sources", {}),
            semantic_conventions=context.get("semantic_conventions", {}),
            output_conventions=context.get("output_conventions", {}),
            onboarding_derivation_rules=context.get("onboarding_derivation_rules"),
            onboarding_resolved_parameters=context.get("onboarding_resolved_parameters"),
            onboarding_output_contracts=context.get("onboarding_output_contracts"),
            onboarding_calibration_hints=context.get("onboarding_calibration_hints"),
            onboarding_open_questions=context.get("onboarding_open_questions"),
            onboarding_dependency_graph=context.get("onboarding_dependency_graph"),
            plan_document_text=context.get("plan_document_text"),
        )

        return {"output": output, "cost": 0.0, "metadata": {"duration": duration}}


def _check_stub_drift(
    emit_manifest: list[dict[str, Any]],
    scaffold_metadata: list,
) -> None:
    """Log-only drift detection: compare EMIT-time vs SCAFFOLD-time SHA-256 hashes.

    If the ForwardManifest changed between EMIT and SCAFFOLD (e.g., manual edit
    to the seed), the hashes will differ. This is advisory — no error is raised.
    """
    emit_by_path = {e["file_path"]: e["sha256"] for e in emit_manifest if "sha256" in e}
    for entry in scaffold_metadata:
        path = entry.file_path if hasattr(entry, "file_path") else entry.get("file_path", "")
        sha = entry.sha256 if hasattr(entry, "sha256") else entry.get("sha256", "")
        if path in emit_by_path and sha and emit_by_path[path] != sha:
            logger.warning(
                "SCAFFOLD: stub drift detected for %s — "
                "EMIT sha256=%s, SCAFFOLD sha256=%s",
                path, emit_by_path[path][:12], sha[:12],
            )


class ScaffoldPhaseHandler(AbstractPhaseHandler):
    """SCAFFOLD phase: Verify target directories, check dependencies.

    Creates missing directories and validates the project environment.
    """

    def execute(
        self,
        phase: WorkflowPhase,
        context: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        start = time.monotonic()
        _log_context_completeness("SCAFFOLD", context)
        tasks: list[SeedTask] = _ensure_context_loaded(context)
        project_root = Path(context.get("project_root", "."))

        logger.info("SCAFFOLD phase: checking %d tasks against %s", len(tasks), project_root)

        dirs_needed: set[str] = set()
        dirs_exist: set[str] = set()
        dirs_created: set[str] = set()
        files_existing: list[str] = []

        skipped_targets: list[str] = []

        for task in tasks:
            for target in task.target_files:
                target_path = project_root / target
                parent = target_path.parent

                # Guard: skip targets whose resolved parent falls outside
                # project_root (e.g. absolute paths in target_files).
                try:
                    parent_rel = str(parent.relative_to(project_root))
                except ValueError:
                    logger.warning(
                        "SCAFFOLD: target %r resolves outside project root, skipping",
                        target,
                    )
                    skipped_targets.append(target)
                    continue

                dirs_needed.add(parent_rel)

                if parent.exists():
                    dirs_exist.add(parent_rel)
                elif not dry_run:
                    try:
                        parent.mkdir(parents=True, exist_ok=True)
                        dirs_created.add(parent_rel)
                        logger.info("Created directory: %s", parent)
                    except OSError as exc:
                        logger.warning(
                            "SCAFFOLD: could not create directory %s: %s",
                            parent, exc,
                        )

                if target_path.exists():
                    files_existing.append(target)

        # Task 8: Staleness classification for existing target files
        staleness: dict[str, str] = {}  # path -> "current" | "stale" | "unknown"
        if files_existing:
            # Use seed mtime as staleness reference
            seed_path = context.get("enriched_seed_path")
            seed_mtime: float | None = None
            if seed_path:
                try:
                    seed_mtime = Path(str(seed_path)).stat().st_mtime
                except OSError as exc:
                    logger.debug("SCAFFOLD: could not stat seed path %s: %s", seed_path, exc)

            for target in files_existing:
                target_path = project_root / target
                try:
                    file_mtime = target_path.stat().st_mtime
                except OSError:
                    staleness[target] = "unknown"
                    continue

                if seed_mtime is not None:
                    if file_mtime >= seed_mtime:
                        staleness[target] = "current"
                    else:
                        staleness[target] = "stale"
                else:
                    staleness[target] = "unknown"

            stale_count = sum(1 for v in staleness.values() if v == "stale")
            if stale_count > 0:
                logger.warning(
                    "SCAFFOLD: %d/%d existing target file(s) are stale (older than seed)",
                    stale_count, len(files_existing),
                )

        dirs_missing = dirs_needed - dirs_exist - dirs_created

        # Fix 5b: soft-validate target file extensions against output_conventions
        output_conventions = context.get("output_conventions", {})
        extension_warnings: list[str] = []
        if output_conventions:
            for task in tasks:
                for atype in task.artifact_types_addressed:
                    expected_ext = output_conventions.get(atype, {}).get("output_ext")
                    if expected_ext:
                        for tf in task.target_files:
                            if not tf.endswith(expected_ext):
                                msg = (
                                    f"task {task.task_id} file {tf} doesn't match "
                                    f"expected extension {expected_ext} for {atype}"
                                )
                                extension_warnings.append(msg)
                                logger.warning("SCAFFOLD: %s", msg)

        # AR-821: Collect importable Python module inventory
        module_inventory = ScaffoldPhaseHandler._collect_module_inventory(project_root)
        if module_inventory:
            logger.info("SCAFFOLD: discovered %d importable packages", len(module_inventory))

        # Mottainai: deterministic file assembly — materialize skeleton stubs
        file_stubs: list = []
        file_stubs_created = file_stubs_skipped = file_stubs_failed = 0
        assembly_degraded = False

        try:
            forward_manifest = context.get("forward_manifest")
            if (
                forward_manifest is not None
                and hasattr(forward_manifest, "file_specs")
                and forward_manifest.file_specs
                and not dry_run
            ):
                from startd8.utils.file_assembler import DeterministicFileAssembler

                assembler = DeterministicFileAssembler(
                    module_inventory=module_inventory,
                )

                # Recompute source text from ForwardManifest
                render_result = assembler.render_specs(forward_manifest)
                file_stubs.extend(
                    r.model_dump() for r in render_result.failures
                )

                # Validate against seed manifest for drift detection
                stub_manifest = context.get("artifacts", {}).get("stub_manifest")
                if stub_manifest and render_result.metadata:
                    _check_stub_drift(stub_manifest, render_result.metadata)

                # Materialize validated specs to disk
                if render_result.specs:
                    mat_results = assembler.materialize(
                        render_result.specs, project_root, dry_run=False,
                    )
                    file_stubs.extend(r.model_dump() for r in mat_results)

                # Telemetry counters
                for stub_dict in file_stubs:
                    status = stub_dict.get("status", "")
                    if status == "created":
                        file_stubs_created += 1
                    elif status == "skipped_exists":
                        file_stubs_skipped += 1
                    elif status == "syntax_error":
                        file_stubs_failed += 1

                logger.info(
                    "SCAFFOLD: file assembly complete — created=%d skipped=%d failed=%d",
                    file_stubs_created, file_stubs_skipped, file_stubs_failed,
                )
        except Exception:
            logger.warning(
                "SCAFFOLD: deterministic file assembly failed — degrading gracefully",
                exc_info=True,
            )
            assembly_degraded = True

        output = {
            "directories_needed": sorted(dirs_needed),
            "directories_exist": sorted(dirs_exist),
            "directories_created": sorted(dirs_created),
            "directories_missing": sorted(dirs_missing) if dry_run else [],
            "existing_target_files": files_existing,
            "staleness_classification": staleness,
            "skipped_targets": skipped_targets,
            "project_root": str(project_root),
            "extension_warnings": extension_warnings,
            "module_inventory": module_inventory,
            "file_stubs": file_stubs,
            "file_stubs_created": file_stubs_created,
            "file_stubs_skipped": file_stubs_skipped,
            "file_stubs_failed": file_stubs_failed,
            "assembly_degraded": assembly_degraded,
        }

        # Store scaffold results in context
        context["scaffold"] = output

        # Context contract: validate SCAFFOLD output model
        ScaffoldPhaseOutput(
            scaffold=context["scaffold"],
            module_inventory=module_inventory,
            file_stubs=file_stubs,
            file_stubs_created=file_stubs_created,
            file_stubs_skipped=file_stubs_skipped,
            file_stubs_failed=file_stubs_failed,
            assembly_degraded=assembly_degraded,
        )

        duration = time.monotonic() - start
        logger.info(
            "SCAFFOLD phase complete: %d dirs needed, %d exist, %d created, %d existing files (%.2fs)",
            len(dirs_needed), len(dirs_exist), len(dirs_created), len(files_existing), duration,
        )

        return {"output": output, "cost": 0.0, "metadata": {"duration": duration}}

    @staticmethod
    def _collect_module_inventory(project_root: Path) -> list[str]:
        """AR-821: Collect importable Python module names under project_root.

        Walks src/ (or project_root if no src/) for directories
        containing __init__.py. Returns dotted module paths.
        """
        src_dir = project_root / "src"
        search_root = src_dir if src_dir.is_dir() else project_root
        modules: list[str] = []
        try:
            for init_file in search_root.rglob("__init__.py"):
                pkg_dir = init_file.parent
                try:
                    rel = pkg_dir.relative_to(search_root)
                    dotted = ".".join(rel.parts)
                    if dotted:
                        modules.append(dotted)
                except ValueError:
                    continue
        except OSError as exc:
            logger.warning("SCAFFOLD: module inventory walk failed: %s", exc)
        return sorted(set(modules))


class DesignPhaseHandler(AbstractPhaseHandler):
    """DESIGN phase: Generate design docs per task via DesignDocumentationPhase.

    In dry-run mode: reports what would be designed per task (no LLM calls).
    In real mode: delegates to :class:`DesignDocumentationPhase` for each task,
    running the async dual-review design pipeline via a thread-owned event loop
    (same pattern as :class:`ImplementPhaseHandler`).

    Data flow:
        1. ``SeedTask`` → ``FeatureContext`` (per task)
        2. ``DesignDocumentationPhase.run(context)`` → ``DesignDocumentResult``
        3. Results serialized → ``context["design_results"]``

    Output files:
        When ``output_dir`` is set, writes ``{task_id}-design.md`` files
        containing the raw design document text.
    """

    def __init__(
        self,
        handler_config: Optional[HandlerConfig] = None,
        output_dir: Optional[str] = None,
    ) -> None:
        self.config = handler_config or HandlerConfig()
        self.output_dir = output_dir
        self._llm_backend: Any = None
        self._design_phase: Any = None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_llm_backend(self) -> Any:
        """Lazily create the AgentLLMBackend."""
        if self._llm_backend is not None:
            return self._llm_backend

        from startd8.contractors.artisan_phases.design_documentation import (
            AgentLLMBackend,
        )

        agent_spec = self.config.design_agent or self.config.lead_agent
        self._llm_backend = AgentLLMBackend(
            agent_spec=agent_spec,
            enable_prompt_caching=self.config.enable_prompt_caching,
        )
        return self._llm_backend

    def _get_design_phase(
        self,
        prompt_capture_dir: Optional[Path] = None,
    ) -> Any:
        """Lazily create the DesignDocumentationPhase.

        When ``prompt_capture_dir`` is set (walkthrough mode), a fresh
        instance is created per call so each task gets its own capture
        directory.  Otherwise the instance is cached.
        """
        if prompt_capture_dir is not None:
            from startd8.contractors.artisan_phases.design_documentation import (
                DesignDocumentationPhase,
            )
            return DesignDocumentationPhase(
                llm=self._get_llm_backend(),
                max_iterations=self.config.max_iterations,
                enforce_post_revision_rereview=self.config.enforce_post_revision_rereview,
                prompt_capture_dir=prompt_capture_dir,
            )

        if self._design_phase is not None:
            return self._design_phase

        from startd8.contractors.artisan_phases.design_documentation import (
            DesignDocumentationPhase,
        )

        self._design_phase = DesignDocumentationPhase(
            llm=self._get_llm_backend(),
            max_iterations=self.config.max_iterations,
            enforce_post_revision_rereview=self.config.enforce_post_revision_rereview,
        )
        return self._design_phase

    @staticmethod
    def _task_to_feature_context(
        task: SeedTask,
        *,
        plan_goals: list[str] | None = None,
        architectural_context: dict[str, Any] | None = None,
        prior_design_summaries: list[str] | None = None,
        calibration: dict[str, Any] | None = None,
        design_max_tokens_override: Optional[int] = None,
        parameter_sources: dict[str, Any] | None = None,
        semantic_conventions: dict[str, Any] | None = None,
        prior_design_text: str | None = None,
        prior_quality_feedback: str | None = None,
        inv_derivation_rules: dict[str, Any] | None = None,
        inv_resolved_parameters: dict[str, Any] | None = None,
        inv_output_contracts: dict[str, Any] | None = None,
        inv_refine_suggestions: str | list[dict[str, Any]] | None = None,
        inv_plan_document: str | None = None,
        inv_calibration_hints: dict[str, Any] | None = None,
        inv_open_questions: list[dict[str, Any]] | None = None,
        inv_dependency_graph: dict[str, list[str]] | None = None,
        scaffold_existing_files: list[str] | None = None,
        # CCD-204: Lane-aware design context parameters
        lane_prior_designs: list[dict[str, Any]] | None = None,
        shared_file_manifest: dict[str, list[str]] | None = None,
        wave_index: int | None = None,
        lane_peer_token_budget: int = 8000,
        # CCD-303: Task title lookup for contested file annotations
        task_title_lookup: dict[str, str] | None = None,
        # CCD-503: Collision resolution context for redesign
        lane_collision_context: str | None = None,
        # REQ-PD-002/007/008/009: Bridge context from Plan Ingestion
        bridge_context: dict[str, Any] | None = None,
        # Phase 5: Manifest context for DESIGN phase (CS-1 through CS-6)
        manifest_registry: Any = None,
        manifest_context_budget: int = 2000,
        # Phase 6: Call graph context budget for DESIGN (CG-DS-4)
        call_graph_context_budget: int = 2000,
        # Phase 5: Introspect enrichment toggle for DESIGN (DS-1..DS-4)
        enable_introspect: bool = False,
    ) -> Any:
        """Convert a SeedTask to a FeatureContext for the design phase.

        Args:
            task: The seed task.
            plan_goals: Project-level goals for benefit-driven framing.
            architectural_context: Shared context from manifest + cross-feature analysis.
            prior_design_summaries: Summaries of earlier design docs for cross-task context.
            calibration: Per-task calibration dict (depth_tier, sections, max_output_tokens).
            design_max_tokens_override: Override max_output_tokens for all design tasks
                (from HandlerConfig.design_max_tokens). Takes precedence over calibration.
            parameter_sources: Per-artifact-type parameter origin mapping from onboarding.
            semantic_conventions: Metric/label naming conventions from onboarding.
        """
        from startd8.contractors.artisan_phases.design_documentation import (
            FeatureContext,
        )

        additional_context: dict[str, Any] = {}
        if task.domain != "unknown":
            additional_context["domain"] = task.domain
        if task.domain_reasoning:
            additional_context["domain_reasoning"] = task.domain_reasoning
        if task.available_siblings:
            additional_context["siblings"] = ", ".join(task.available_siblings)
        if task.feature_id:
            additional_context["feature_id"] = task.feature_id

        # Benefit-driven framing: inject project goals
        if plan_goals:
            additional_context["project_goals"] = (
                "This feature supports these project goals:\n"
                + "\n".join(f"- {g}" for g in plan_goals[:5])
            )

        # Architectural context from manifest + cross-feature analysis
        arch = architectural_context or {}
        objectives = arch.get("objectives", [])
        if objectives:
            additional_context["objectives"] = ", ".join(
                o.get("name", str(o)) if isinstance(o, dict) else str(o)
                for o in objectives[:5]
            )
        constraints = arch.get("constraints", [])
        if constraints:
            additional_context["constraints_from_manifest"] = [
                f"[{c.get('severity', 'info')}] {c.get('rule', str(c))}"
                if isinstance(c, dict) else str(c)
                for c in constraints
            ]

        # Shared modules (only those overlapping with this task's targets)
        shared = arch.get("shared_modules", [])
        if shared and task.target_files:
            task_targets = set(task.target_files)
            overlapping = [
                m["path"] for m in shared
                if isinstance(m, dict) and m.get("path") in task_targets
            ]
            if overlapping:
                additional_context["shared_modules"] = (
                    f"These files are also targeted by other features — "
                    f"coordinate interfaces: {', '.join(overlapping)}"
                )

        domain_concepts = arch.get("domain_concepts", [])
        if domain_concepts:
            additional_context["domain_concepts"] = ", ".join(domain_concepts[:10])

        import_conventions = arch.get("import_conventions", [])
        if import_conventions:
            additional_context["import_conventions"] = ", ".join(import_conventions[:5])

        # CCD-201: Two-tier context model
        # Tier 1: Lane-peer designs (full documents)
        if lane_prior_designs:
            budgeted, _truncated = _apply_lane_peer_token_budget(
                lane_prior_designs, lane_peer_token_budget,
            )
            additional_context["lane_peer_designs"] = _format_lane_peer_context(
                budgeted, shared_file_manifest, task,
            )

        # Tier 2: Cross-lane summaries (exclude lane peers to avoid duplication)
        if prior_design_summaries:
            lane_peer_ids = {d["task_id"] for d in (lane_prior_designs or [])}
            cross_lane = [
                s for s in prior_design_summaries
                if not any(s.startswith(f"{pid} (") for pid in lane_peer_ids)
            ]
            if cross_lane:
                additional_context["prior_designs"] = (
                    "Previously designed tasks (other lanes):\n"
                    + "\n".join(f"- {s}" for s in cross_lane[-5:])
                )

        # CCD-303: Contested files prompt injection
        if shared_file_manifest and task.target_files:
            task_contested: list[str] = []
            for tf in task.target_files:
                normalized_tf = _normalize_target_path(tf)
                contesting_ids = shared_file_manifest.get(normalized_tf)
                if contesting_ids:
                    others = [tid for tid in contesting_ids if tid != task.task_id]
                    if others:
                        other_descs = [
                            f"{tid} ({(task_title_lookup or {}).get(tid, '')})"
                            for tid in others
                        ]
                        task_contested.append(
                            f"  - `{tf}`: {', '.join(other_descs)}"
                        )
            if task_contested:
                additional_context["contested_files"] = (
                    "SHARED FILE WARNING: These files are targeted by multiple "
                    "tasks. Coordinate your design with theirs.\n"
                    + "\n".join(task_contested)
                )

        # CCD-503: Inject collision resolution context when redesigning
        if lane_collision_context:
            additional_context["collision_resolution"] = (
                "DESIGN COLLISION ALERT: Your previous design conflicted with "
                "another task in the same lane. Please redesign with these "
                "constraints:\n" + lane_collision_context
            )

        # Calibration: depth guidance
        cal = calibration or {}
        depth_guidance = cal.get("depth_guidance")
        if depth_guidance:
            additional_context["depth_guidance"] = depth_guidance

        # Task-specific design doc content hints (supplement structural sections)
        if task.design_doc_sections:
            additional_context["design_doc_sections"] = task.design_doc_sections

        if prior_quality_feedback and prior_quality_feedback.strip():
            additional_context["quality_feedback"] = (
                "Quality feedback from previous design attempt (must be addressed):\n"
                + prior_quality_feedback.strip()
            )

        # Fix 2c: inject parameter_sources relevant to this task's artifact types
        all_param_sources = parameter_sources or {}
        if all_param_sources and task.artifact_types_addressed:
            task_param_sources = {
                atype: all_param_sources[atype]
                for atype in task.artifact_types_addressed
                if atype in all_param_sources
            }
            if task_param_sources:
                param_lines = ["Parameter sources (from ContextCore manifest):"]
                for atype, sources in task_param_sources.items():
                    param_lines.append(f"  {atype}: {json.dumps(sources, indent=2)}")
                additional_context["parameter_sources"] = "\n".join(param_lines)

        # Fix 3c: inject semantic_conventions
        sem_conv = semantic_conventions or {}
        if sem_conv:
            conv_lines = ["Semantic conventions:"]
            for key, val in sem_conv.items():
                conv_lines.append(f"  {key}: {val}")
            additional_context["semantic_conventions"] = "\n".join(conv_lines)

        # Mottainai: inject inventory artifacts into additional_context
        if inv_derivation_rules and task.artifact_types_addressed:
            task_rules = {
                atype: inv_derivation_rules[atype]
                for atype in task.artifact_types_addressed
                if atype in inv_derivation_rules
            }
            if task_rules:
                additional_context["derivation_rules"] = task_rules

        if inv_resolved_parameters and task.artifact_types_addressed:
            # resolved_parameters may be keyed by artifact ID or artifact type
            task_params = {
                k: v for k, v in inv_resolved_parameters.items()
                if any(atype in k for atype in task.artifact_types_addressed)
            }
            if task_params:
                additional_context["resolved_parameters"] = task_params

        if inv_output_contracts and task.artifact_types_addressed:
            task_contracts = {
                atype: inv_output_contracts[atype]
                for atype in task.artifact_types_addressed
                if atype in inv_output_contracts
            }
            if task_contracts:
                additional_context["output_contracts"] = task_contracts

        # Mottainai: inject refine suggestions relevant to this task
        # IMP-8a: handle both structured List[Dict] (from REFINE forwarding)
        # and text str (from inventory/plan document fallback)
        if inv_refine_suggestions:
            if isinstance(inv_refine_suggestions, list):
                # Structured suggestions from REFINE triage forwarding
                formatted = DesignPhaseHandler._format_structured_suggestions(
                    inv_refine_suggestions,
                )
                if formatted:
                    additional_context["refine_suggestions"] = formatted
            else:
                # Legacy text path: S-/F- prefix line extraction
                task_suggestions = DesignPhaseHandler._extract_task_suggestions(
                    inv_refine_suggestions, task.task_id,
                    getattr(task, "feature_id", None),
                )
                if task_suggestions:
                    additional_context["refine_suggestions"] = task_suggestions

        # Mottainai + REQ-PD-001: inject plan architecture, risks, and
        # verification strategy with FOUNDATION prefix instructing the LLM
        # to elaborate rather than regenerate from scratch.
        _FOUNDATION_PREFIX = (
            "FOUNDATION (from Plan Ingestion TRANSFORM — elaborate and "
            "add implementation detail, do NOT regenerate from scratch):\n"
        )
        if inv_plan_document:
            arch_section = DesignPhaseHandler._extract_plan_section(
                inv_plan_document, "Architecture",
            )
            risk_section = DesignPhaseHandler._extract_plan_section(
                inv_plan_document, "Risk",
            )
            verification_section = DesignPhaseHandler._extract_plan_section(
                inv_plan_document, "Verification",
            )

            # REQ-PD-001: enforce 6000-char combined cap with priority
            # truncation: architecture (highest) > risk > verification
            _foundation_budget = 6000
            _foundation_parts: list[tuple[str, str]] = []
            if arch_section:
                _foundation_parts.append(("plan_architecture", arch_section))
            if risk_section:
                _foundation_parts.append(("plan_risks", risk_section))
            if verification_section:
                _foundation_parts.append(
                    ("plan_verification_strategy", verification_section)
                )

            _remaining = _foundation_budget
            for _fkey, _ftext in _foundation_parts:
                if _remaining <= 0:
                    break
                truncated = _ftext[:_remaining]
                if len(_ftext) > _remaining:
                    truncated += "\n... (truncated)"
                additional_context[_fkey] = _FOUNDATION_PREFIX + truncated
                _remaining -= len(truncated)

        # REQ-PD-004: inject api_signatures and protocol from seed task
        if task.api_signatures:
            additional_context["api_signatures"] = (
                "PLAN-SPECIFIED API SIGNATURES (preserve exactly):\n"
                + "\n".join(f"- {sig}" for sig in task.api_signatures)
            )
        if task.protocol:
            additional_context["transport_protocol"] = (
                f"Transport protocol constraint: {task.protocol}. "
                "All network interfaces, health checks, and client "
                "configurations MUST use this protocol."
            )

        # Mottainai: calibration hints override depth_guidance when not already set.
        # When artifact_types_addressed is empty (Gap 6 / Phase 2.1), fall back
        # to the most common depth hint across all artifact types so project-wide
        # calibration data still reaches the DESIGN prompt.
        if inv_calibration_hints and not depth_guidance:
            if task.artifact_types_addressed:
                for atype in task.artifact_types_addressed:
                    hint = inv_calibration_hints.get(atype)
                    if hint and hint.get("expected_depth"):
                        depth_guidance = hint["expected_depth"]
                        additional_context["calibration_override_source"] = (
                            "export.calibration_hints"
                        )
                        break  # Use first matching type's calibration
            else:
                # Project-level fallback: use most common depth across all types
                depth_counts: dict[str, int] = {}
                for hint in inv_calibration_hints.values():
                    if isinstance(hint, dict) and hint.get("expected_depth"):
                        d = hint["expected_depth"]
                        depth_counts[d] = depth_counts.get(d, 0) + 1
                if depth_counts:
                    depth_guidance = max(depth_counts, key=depth_counts.get)  # type: ignore[arg-type]
                    additional_context["calibration_override_source"] = (
                        "export.calibration_hints (project-level fallback)"
                    )

        # Mottainai: surface open questions from ContextCore guidance so DESIGN
        # decisions are made with awareness of flagged uncertainties (Gap 7).
        if inv_open_questions and isinstance(inv_open_questions, list):
            formatted = "\n".join(
                f"- {q['question'] if isinstance(q, dict) else q}"
                for q in inv_open_questions[:10]
            )
            if formatted.strip():
                additional_context["open_questions"] = (
                    "The following questions are flagged as unresolved:\n" + formatted
                )

        # Task 9b: Inject critical parameters checklist guidance
        # Tell the design phase to explicitly enumerate critical parameters
        additional_context["critical_parameters_checklist"] = (
            "IMPORTANT: Your design document MUST include a 'Critical Parameters' "
            "section listing all configuration values, port numbers, environment "
            "variable names, timeout values, buffer sizes, and function signatures "
            "that the IMPLEMENT phase must preserve exactly. Format each as:\n"
            "- `PARAM_NAME`: value (rationale)\n"
            "This enables automated fidelity checking between design and implementation."
        )

        # Task 9d: Scope boundary instruction
        if task.negative_scope:
            additional_context["scope_boundary"] = (
                "SCOPE BOUNDARY: The following items are explicitly OUT OF SCOPE "
                "for this feature. Do NOT design or implement them:\n"
                + "\n".join(f"- {ns}" for ns in task.negative_scope)
                + "\nIf any of these are prerequisites, note them as external "
                "dependencies but do not include implementation details."
            )

        # Mottainai B4: inject artifact dependency info so DESIGN decisions
        # account for deterministic inter-artifact dependencies from export
        # rather than re-inferring them via LLM (Gap 4).
        if inv_dependency_graph and task.artifact_types_addressed:
            task_deps: dict[str, list[str]] = {}
            for atype in task.artifact_types_addressed:
                # Graph may be keyed by artifact_id or artifact_type
                deps = inv_dependency_graph.get(atype, [])
                if deps:
                    task_deps[atype] = deps
            if task_deps:
                formatted_deps = "; ".join(
                    f"{k} depends on: {', '.join(v)}" for k, v in task_deps.items()
                )
                additional_context["artifact_dependencies"] = (
                    f"Known artifact dependencies: {formatted_deps}"
                )

        sections = cal.get("sections")
        max_output_tokens = (
            design_max_tokens_override
            if design_max_tokens_override is not None
            else cal.get("max_output_tokens")
        )

        # ── REQ-PD-002/007/008/009: Process bridge_context ──
        _bc = bridge_context or {}

        # REQ-PD-002: Complexity-aware depth calibration
        _complexity_dims = _bc.get("complexity_dimensions", {})
        _complexity_composite = _bc.get("complexity_composite")
        if _complexity_dims:
            _high_dims = [
                (dim, score) for dim, score in _complexity_dims.items()
                if isinstance(score, (int, float)) and score > 70
            ]
            if _high_dims:
                _guidance_parts = [
                    f"- {dim} (score {score}): provide extra detail"
                    for dim, score in _high_dims
                ]
                additional_context["complexity_guidance"] = (
                    "COMPLEXITY ALERT — these dimensions scored high:\n"
                    + "\n".join(_guidance_parts)
                )
        if (
            _complexity_composite is not None
            and _complexity_composite > 60
            and not depth_guidance
        ):
            depth_guidance = "comprehensive"

        # REQ-PD-007: Dependency-ordered cross-task context
        _dep_designs = _bc.get("dependency_designs", {})
        if _dep_designs:
            _dep_parts: list[str] = []
            for _dep_id, _dep_summary in list(_dep_designs.items())[:3]:
                _dep_parts.append(
                    f"- {_dep_id}: {_dep_summary[:500]}"
                )
            if _dep_parts:
                additional_context["dependency_designs"] = (
                    "DEPENDENCY DESIGNS (tasks this task depends on):\n"
                    + "\n".join(_dep_parts)
                )

        # REQ-PD-008: Wave-aware context accumulation
        _wave_meta = _bc.get("wave_metadata")
        _wave_idx = _bc.get("wave_index")
        if _wave_meta and _wave_idx is not None:
            _wave_count = _wave_meta.get("wave_count", 1)
            additional_context["wave_context"] = (
                f"Wave {_wave_idx + 1} of {_wave_count}. "
                "Tasks in the same wave execute in parallel — avoid "
                "design decisions that create implicit ordering dependencies "
                "with same-wave peers."
            )

        # REQ-PD-009: Staleness-aware design mode
        _staleness = _bc.get("staleness_classification", {})
        if _staleness and task.target_files:
            _stale_files = [
                f for f in task.target_files
                if _staleness.get(f) == "stale"
            ]
            _current_files = [
                f for f in task.target_files
                if _staleness.get(f) == "current"
            ]
            if _stale_files:
                additional_context["staleness_guidance"] = (
                    "STALE FILES (older than plan seed): "
                    + ", ".join(_stale_files)
                    + ". Focus design on delta changes needed."
                )
            elif _current_files:
                additional_context["staleness_guidance"] = (
                    "CURRENT FILES (newer than plan seed): "
                    + ", ".join(_current_files)
                    + ". Minimize changes — these files are up to date."
                )

        # REQ-PD-011: Plan-delta indicator
        if task.design_doc_sections and cal.get("sections"):
            _plan_sections = set(task.design_doc_sections)
            _cal_sections = set(cal["sections"])
            if _plan_sections != _cal_sections:
                additional_context["plan_delta"] = (
                    "NOTE: Task design_doc_sections differ from calibration "
                    "sections. Task sections: "
                    + ", ".join(sorted(_plan_sections))
                    + ". Calibration sections: "
                    + ", ".join(sorted(_cal_sections))
                )
        if task.api_signatures:
            additional_context["api_signature_verification"] = (
                "VERIFY: Implementation must match these plan-specified "
                "API signatures exactly: "
                + "; ".join(task.api_signatures)
            )

        # B-6: Compute edit_mode_hint from filesystem ground truth
        _scaffold_existing = set(scaffold_existing_files or [])
        _existing_targets = [
            f for f in (task.target_files or []) if f in _scaffold_existing
        ]
        _edit_mode_hint: str | None = None
        if _existing_targets:
            _edit_mode_hint = "edit"
        elif task.target_files:
            _edit_mode_hint = "create"

        # REQ-PD-005: Compute has_plan_foundation flag
        _foundation_keys = {
            "plan_architecture", "plan_risks", "plan_verification_strategy",
            "refine_suggestions", "complexity_guidance",
        }
        _has_plan_foundation = bool(
            _foundation_keys & set(additional_context.keys())
        )

        # Phase 5: Manifest context injection (CS-1 through CS-6)
        # Mirror the IMPLEMENT manifest pattern (lines 5658-5680)
        _manifest_summary = ""
        if manifest_registry is not None and task.target_files:
            _mc_parts: list[str] = []
            for tf in task.target_files:
                try:
                    summary = manifest_registry.file_element_summary(
                        tf, manifest_context_budget,
                    )
                    if summary:
                        _mc_parts.append(f"### {tf}\n{summary}")
                except Exception:
                    logger.debug(
                        "DESIGN: manifest lookup failed for %s", tf,
                        exc_info=True,
                    )
            if _mc_parts:
                _manifest_summary = "\n\n".join(_mc_parts)
                additional_context["manifest_context"] = _manifest_summary
                logger.debug(
                    "DESIGN: manifest context injected for %d/%d target files",
                    len(_mc_parts), len(task.target_files),
                )

            # CS-4: Cross-task dependency extraction via dependency_graph()
            try:
                dep_graph = manifest_registry.dependency_graph()
                if dep_graph and isinstance(dep_graph, dict):
                    dep_lines: list[str] = []
                    for tf in task.target_files:
                        if tf in dep_graph:
                            dep_lines.append(
                                f"- {tf} imports from: "
                                f"{', '.join(dep_graph[tf])}"
                            )
                    if dep_lines:
                        additional_context["manifest_dependencies"] = (
                            "\n".join(dep_lines)
                        )
            except Exception:
                logger.debug(
                    "DESIGN: dependency_graph() failed", exc_info=True,
                )

            # Phase 6: CG-DS-1,2,3 — call graph context for DESIGN
            _cg_budget = call_graph_context_budget // 2  # CG-DS-4: share budget
            try:
                _cg_parts: list[str] = []
                for tf in task.target_files:
                    cg_summary = manifest_registry.call_graph_summary(tf, _cg_budget)
                    if cg_summary:
                        _cg_parts.append(f"### {tf}\n{cg_summary}")
                    # CG-DS-2: For edit-mode tasks, annotate with caller counts
                    if _edit_mode_hint == "edit":
                        callers_map = manifest_registry.callers_of_file(tf)
                        if callers_map:
                            caller_lines: list[str] = []
                            for fqn, callers in sorted(callers_map.items()):
                                caller_lines.append(
                                    f"- `{fqn}`: {len(callers)} external callers"
                                )
                            _cg_parts.append(
                                f"**External callers of {tf}:**\n"
                                + "\n".join(caller_lines[:10])
                            )
                if _cg_parts:
                    additional_context["call_graph_context"] = "\n\n".join(_cg_parts)
                    logger.debug(
                        "DESIGN: call graph context injected for %d/%d target files",
                        len(_cg_parts), len(task.target_files),
                    )
            except Exception:
                logger.debug(
                    "DESIGN: call graph context failed", exc_info=True,
                )

        # CS-3: Edit-mode manifest context key
        if _edit_mode_hint == "edit" and _manifest_summary:
            additional_context["manifest_edit_context"] = _manifest_summary

        # Phase 5: Introspect enrichment for DESIGN context (DS-1..DS-4)
        if enable_introspect and manifest_registry is not None and task.target_files:

            # DS-1: Resolved types (T1 context). Built once; edit-mode registers
            # manifest_edit_context separately below via its own key.
            # C2: collapsed from two near-identical loops (edit vs non-edit path).
            if "manifest_resolved_types" not in additional_context:
                _rts_parts: list[str] = []
                for tf in task.target_files:
                    try:
                        rts = manifest_registry.file_resolved_type_summary(tf)
                        if rts:
                            _rts_parts.append(f"### {tf}\n{rts}")
                    except Exception:
                        logger.debug(
                            "DESIGN DS-1: resolved type summary failed for %s",
                            tf, exc_info=True,
                        )
                if _rts_parts:
                    additional_context["manifest_resolved_types"] = "\n\n".join(_rts_parts)

            # DS-2: MRO chains as supplemental manifest_context annotation
            _mro_lines: list[str] = []
            for tf in task.target_files:
                try:
                    mro_map = manifest_registry.file_mro_summary(tf)
                    for fqn, mro in sorted(mro_map.items()):
                        chain = " \u2192 ".join(mro)
                        _mro_lines.append(f"- {fqn}: [{chain}]")
                except Exception:
                    logger.debug(
                        "DESIGN DS-2: MRO summary failed for %s",
                        tf, exc_info=True,
                    )
            if _mro_lines:
                _mro_section = "### Class Hierarchy\n" + "\n".join(_mro_lines)
                existing_mc = additional_context.get("manifest_context", "")
                additional_context["manifest_context"] = (
                    existing_mc + "\n\n" + _mro_section if existing_mc else _mro_section
                )

            # DS-3: module __all__ as public_api_surface (T3 advisory)
            _all_parts: list[str] = []
            for tf in task.target_files:
                try:
                    mod_all = manifest_registry.module_all_for(tf)
                    if mod_all:
                        _all_parts.append(f"{tf}: [{', '.join(mod_all)}]")
                except Exception:
                    logger.debug(
                        "DESIGN DS-3: module __all__ lookup failed for %s",
                        tf, exc_info=True,
                    )
            if _all_parts:
                additional_context["public_api_surface"] = "\n".join(_all_parts)

            # DS-4: Runtime attributes for dataclass/namedtuple elements
            _ra_lines: list[str] = []
            for tf in task.target_files:
                try:
                    ra_map = manifest_registry.file_runtime_attributes(tf)
                    for fqn, attrs in sorted(ra_map.items()):
                        _ra_lines.append(
                            f"- {fqn} (dataclass/namedtuple) \u2014 Generated members "
                            f"(do NOT redefine): {', '.join(attrs)}"
                        )
                except Exception:
                    logger.debug(
                        "DESIGN DS-4: runtime attributes lookup failed for %s",
                        tf, exc_info=True,
                    )
            if _ra_lines:
                _ra_section = "### Generated Members (dataclass/namedtuple)\n" + "\n".join(_ra_lines)
                existing_mc = additional_context.get("manifest_context", "")
                additional_context["manifest_context"] = (
                    existing_mc + "\n\n" + _ra_section if existing_mc else _ra_section
                )
                logger.debug(
                    "DESIGN DS-4: injected runtime attributes for %d/%d target files",
                    len(_ra_lines), len(task.target_files),
                )

        # DU-4 (Tier 2): ManifestDiff for redesign iterations
        # When prior manifest snapshot is available, compute diff here
        # via ManifestDiff.diff(old_manifest, new_manifest) and render as
        # "### Structural Changes Since Last Design" in additional_context.

        return FeatureContext(
            feature_name=task.title,
            description=task.description,
            target_file=", ".join(task.target_files) if task.target_files else "",
            constraints=list(task.prompt_constraints),
            additional_context=additional_context,
            sections=sections,
            max_output_tokens=max_output_tokens,
            depth_guidance=depth_guidance,
            prior_design=prior_design_text,
            requirements_text=task.requirements_text,
            edit_mode_hint=_edit_mode_hint,
            existing_target_files=_existing_targets,
            has_plan_foundation=_has_plan_foundation,
            manifest_summary=_manifest_summary,
        )

    @staticmethod
    def _extract_task_suggestions(
        refine_text: str, task_id: str, feature_id: str | None
    ) -> str:
        """Extract refine suggestions relevant to a specific task.

        Extracts plan-level suggestions (S-prefix) and feature-matching
        suggestions (F-prefix) from the REFINE phase output text.
        """
        if not refine_text:
            return ""
        lines = refine_text.splitlines()
        relevant: list[str] = []
        for line in lines:
            stripped = line.strip()
            # Plan-level suggestions start with S- prefix
            if stripped.startswith("S-"):
                relevant.append(stripped)
            # Feature-specific suggestions start with F- prefix
            elif stripped.startswith("F-"):
                # Match by task_id or feature_id
                if task_id and task_id in stripped:
                    relevant.append(stripped)
                elif feature_id and feature_id in stripped:
                    relevant.append(stripped)
        return "\n".join(relevant) if relevant else ""

    @staticmethod
    def _format_structured_suggestions(
        suggestions: list[dict[str, Any]],
    ) -> str:
        """Format structured REFINE triage suggestions as markdown for prompt injection.

        Handles two formats:
        - Individual ACCEPT decisions with id/area/severity/rationale
        - Aggregate triage summary (fallback when per-decision data unavailable)
        """
        if not suggestions:
            return ""

        parts: list[str] = []
        parts.append("REFINE Phase Accepted Suggestions:")

        for sug in suggestions:
            if sug.get("source") == "triage_summary":
                # Aggregate summary format
                accepted = sug.get("triage_accepted_count", 0)
                areas = sug.get("substantially_addressed_areas", [])
                needs_review = sug.get("areas_needing_review", [])
                parts.append(f"- {accepted} suggestion(s) accepted by triage")
                if areas:
                    parts.append(
                        f"  Addressed areas: {', '.join(str(a) for a in areas)}"
                    )
                if needs_review:
                    parts.append(
                        f"  Areas needing review: {', '.join(str(a) for a in needs_review)}"
                    )
            else:
                # Individual decision format
                sid = sug.get("id", "?")
                area = sug.get("area", "")
                severity = sug.get("severity", "")
                rationale = sug.get("rationale", "")
                line = f"- [{sid}]"
                if area:
                    line += f" ({area}"
                    if severity:
                        line += f", {severity}"
                    line += ")"
                if rationale:
                    line += f": {rationale}"
                parts.append(line)

        return "\n".join(parts)

    @staticmethod
    def _extract_plan_section(plan_text: str, section_name: str) -> str:
        """Extract a named markdown section from plan text.

        Looks for ``## {section_name}`` or ``### {section_name}`` headers
        and returns content up to the next header of same or higher level.
        """
        import re

        if not plan_text:
            return ""
        # Find the section header (## or ###)
        pattern = rf"^(#{{2,3}})\s+{re.escape(section_name)}.*$"
        match = re.search(pattern, plan_text, re.MULTILINE | re.IGNORECASE)
        if not match:
            return ""

        start = match.end()
        header_level = len(match.group(1))

        # Find the next header of same or higher level
        next_header = re.search(
            rf"^#{{{1},{header_level}}}\s+",
            plan_text[start:],
            re.MULTILINE,
        )
        if next_header:
            end = start + next_header.start()
        else:
            end = len(plan_text)

        section = plan_text[start:end].strip()
        # Truncate to avoid massive context injection
        if len(section) > 2000:
            section = section[:2000] + "\n... (truncated)"
        return section

    @staticmethod
    def _run_design_async(
        design_phase: Any,
        feature_context: Any,
        timeout: float | None = None,
    ) -> Any:
        """Run DesignDocumentationPhase.run() in a dedicated thread-owned event loop.

        Uses the same pattern as ImplementPhaseHandler._run_development_phase()
        to avoid nested event-loop errors.

        Args:
            design_phase: The DesignDocumentationPhase instance.
            feature_context: The FeatureContext for the design task.
            timeout: Maximum seconds to wait for the thread. ``None``
                means wait indefinitely.
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
                        design_phase.run(feature_context)
                    )
                except Exception as exc:
                    error_box["error"] = exc
                finally:
                    loop.close()
                    asyncio.set_event_loop(None)
            finally:
                reset_boundary_result(br_token)
                detach_context(token)

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            # Race guard — thread may have completed between join() and is_alive()
            if "result" in result_box or "error" in error_box:
                logger.debug(
                    "_run_design_async thread reported alive after join() "
                    "but result_box is populated — treating as completed",
                )
            else:
                logger.error(
                    "DesignDocumentationPhase did not complete within %.0fs — "
                    "abandoning background thread (daemon=True)",
                    timeout,
                )
                raise TimeoutError(
                    f"DesignDocumentationPhase.run() did not complete within {timeout}s"
                )

        if "error" in error_box:
            raise error_box["error"]
        if "result" not in result_box:
            raise RuntimeError(
                "_run_design_async: thread completed but produced neither result nor error"
            )
        return result_box["result"]

    @staticmethod
    def _run_v2_generate(
        backend: Any,
        prompt: str,
        system_prompt: str,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> str:
        """Run backend.generate() in a dedicated thread-owned event loop.

        Mirrors ``_run_design_async`` but invokes a single LLM call
        (no dual-review, no revision loop) for the v2 modular prompt path.
        """
        result_box: dict[str, Any] = {}
        error_box: dict[str, Exception] = {}
        parent_ctx = capture_context()
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
                        backend.generate(
                            prompt,
                            system_prompt=system_prompt,
                            max_tokens=max_tokens,
                        )
                    )
                except Exception as exc:
                    error_box["error"] = exc
                finally:
                    loop.close()
                    asyncio.set_event_loop(None)
            finally:
                reset_boundary_result(br_token)
                detach_context(token)

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            # Race guard — thread may have completed between join() and is_alive()
            if "result" in result_box or "error" in error_box:
                logger.debug(
                    "_run_v2_generate thread reported alive after join() "
                    "but result_box is populated — treating as completed",
                )
            else:
                logger.error(
                    "v2 design generate did not complete within %.0fs — "
                    "abandoning background thread (daemon=True)",
                    timeout,
                )
                raise TimeoutError(
                    f"v2 design generate did not complete within {timeout}s"
                )

        if "error" in error_box:
            raise error_box["error"]
        if "result" not in result_box:
            raise RuntimeError(
                "_run_v2_generate: thread completed but produced neither result nor error"
            )
        return result_box["result"]

    @staticmethod
    def _run_v2_reviews_async(
        design_phase: Any,
        design_document: Any,
        *,
        feature_context: Any | None = None,
        timeout: float | None = None,
    ) -> tuple[Any, Any, list[Any]]:
        """Run reviewer+arbiter evaluation for v2 design output in one async loop.

        Enforces the same review envelope semantics as the canonical v1 path:
        v2 output cannot be accepted without reviewer and arbiter evidence.
        """
        result_box: dict[str, Any] = {}
        error_box: dict[str, Exception] = {}
        parent_ctx = capture_context()
        from startd8.contractors.forensic_log import (
            get_boundary_result,
            set_boundary_result,
            reset_boundary_result,
        )
        parent_boundary_result = get_boundary_result()

        async def _run_pair() -> tuple[Any, Any, list[Any]]:
            reviewer = await design_phase._review_design(  # noqa: SLF001
                design_document, ReviewRole.REVIEWER, feature_context=feature_context,
            )
            arbiter = await design_phase._review_design(  # noqa: SLF001
                design_document, ReviewRole.ARBITER, feature_context=feature_context,
            )
            disagreements = design_phase._detect_disagreements(  # noqa: SLF001
                reviewer, arbiter,
            )
            return reviewer, arbiter, disagreements

        def _runner() -> None:
            token = attach_context(parent_ctx)
            br_token = set_boundary_result(parent_boundary_result)
            try:
                loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(loop)
                    result_box["result"] = loop.run_until_complete(_run_pair())
                except Exception as exc:
                    error_box["error"] = exc
                finally:
                    loop.close()
                    asyncio.set_event_loop(None)
            finally:
                reset_boundary_result(br_token)
                detach_context(token)

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            # Race guard — thread may have completed between join() and is_alive()
            if "result" in result_box or "error" in error_box:
                logger.debug(
                    "_run_v2_reviews_async thread reported alive after join() "
                    "but result_box is populated — treating as completed",
                )
            else:
                logger.error(
                    "v2 design review did not complete within %.0fs — "
                    "abandoning background thread (daemon=True)",
                    timeout,
                )
                raise TimeoutError(
                    f"v2 design review did not complete within {timeout}s"
                )

        if "error" in error_box:
            raise error_box["error"]
        if "result" not in result_box:
            raise RuntimeError(
                "_run_v2_reviews_async: thread completed but produced neither result nor error"
            )
        return result_box["result"]

    @staticmethod
    def _serialize_result(result: Any) -> dict[str, Any]:
        """Serialize a DesignDocumentResult to a checkpoint-safe dict."""
        payload = {
            "design_document": result.design_document.raw_text,
            "feature_name": result.design_document.feature_name,
            "agreed": result.agreed,
            "iterations": result.iterations,
            "completed_at": result.completed_at.isoformat(),
        }
        reviewer_verdict = DesignPhaseHandler._serialize_review_verdict(
            getattr(result, "reviewer_verdict", None),
        )
        if reviewer_verdict:
            payload["reviewer_verdict"] = reviewer_verdict
        arbiter_verdict = DesignPhaseHandler._serialize_review_verdict(
            getattr(result, "arbiter_verdict", None),
        )
        if arbiter_verdict:
            payload["arbiter_verdict"] = arbiter_verdict
        reason_code = getattr(result, "non_agreement_reason_code", None)
        if reason_code:
            payload["non_agreement_reason_code"] = reason_code
        final_iteration = getattr(result, "final_iteration", None)
        if final_iteration is not None:
            payload["final_iteration"] = final_iteration
        resolution_audit = getattr(result, "resolution_audit", None)
        if resolution_audit:
            payload["resolution_audit"] = resolution_audit
        prompt_telemetry = getattr(result, "prompt_telemetry", None)
        if prompt_telemetry:
            payload["prompt_telemetry"] = prompt_telemetry
        disagreement_telemetry = getattr(result, "disagreement_telemetry", None)
        if disagreement_telemetry:
            payload["disagreement_telemetry"] = disagreement_telemetry
        return payload

    @staticmethod
    def _coerce_float(value: Any, default: float = 0.0) -> float:
        """Best-effort float coercion with sane fallback."""
        try:
            if value is None:
                return default
            coerced = float(value)
            if coerced != coerced:  # NaN guard
                return default
            return coerced
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _serialize_review_verdict(verdict: Any) -> dict[str, Any] | None:
        """Serialize a review verdict object into a JSON-safe dict."""
        if verdict is None:
            return None
        role_value = getattr(verdict, "role", None)
        if role_value is not None and hasattr(role_value, "value"):
            role_value = role_value.value
        reviewed_at = getattr(verdict, "reviewed_at", None)
        if reviewed_at is not None and hasattr(reviewed_at, "isoformat"):
            reviewed_at = reviewed_at.isoformat()
        return {
            "role": str(role_value) if role_value is not None else "",
            "approved": bool(getattr(verdict, "approved", False)),
            "confidence": max(
                0.0,
                min(
                    1.0,
                    DesignPhaseHandler._coerce_float(
                        getattr(verdict, "confidence", 0.0),
                    ),
                ),
            ),
            "concerns": list(getattr(verdict, "concerns", []) or []),
            "suggestions": list(getattr(verdict, "suggestions", []) or []),
            "summary": str(getattr(verdict, "summary", "") or ""),
            "reviewed_at": reviewed_at,
        }

    @staticmethod
    def _extract_review_feedback(verdict: dict[str, Any] | None) -> list[str]:
        """Extract actionable feedback lines from a serialized verdict."""
        if not isinstance(verdict, dict):
            return []
        feedback: list[str] = []
        summary = str(verdict.get("summary", "") or "").strip()
        if summary:
            feedback.append(summary)
        for concern in verdict.get("concerns", []) or []:
            c = str(concern or "").strip()
            if c:
                feedback.append(c)
        for suggestion in verdict.get("suggestions", []) or []:
            s = str(suggestion or "").strip()
            if s:
                feedback.append(s)
        deduped: list[str] = []
        seen: set[str] = set()
        for item in feedback:
            if item not in seen:
                seen.add(item)
                deduped.append(item)
        return deduped

    @staticmethod
    def _build_review_gate(
        entry: dict[str, Any],
        *,
        pass_threshold: int,
    ) -> dict[str, Any]:
        """Compute AR-129 review threshold gate from dual-review evidence."""
        reviewer = entry.get("reviewer_verdict")
        arbiter = entry.get("arbiter_verdict")
        reviewer_dict = reviewer if isinstance(reviewer, dict) else {}
        arbiter_dict = arbiter if isinstance(arbiter, dict) else {}

        has_dual_verdict = bool(reviewer_dict) and bool(arbiter_dict)
        reviewer_approved = bool(
            reviewer_dict.get("approved", entry.get("agreed", False))
        )
        arbiter_approved = bool(
            arbiter_dict.get("approved", entry.get("agreed", False))
        )

        if has_dual_verdict:
            reviewer_conf = max(
                0.0,
                min(
                    1.0,
                    DesignPhaseHandler._coerce_float(
                        reviewer_dict.get("confidence"),
                        0.0,
                    ),
                ),
            )
            arbiter_conf = max(
                0.0,
                min(
                    1.0,
                    DesignPhaseHandler._coerce_float(
                        arbiter_dict.get("confidence"),
                        0.0,
                    ),
                ),
            )
            score = int(round(min(reviewer_conf, arbiter_conf) * 100))
            evidence_mode = "dual_verdict"
        else:
            # Backward-compatible fallback for older handoff payloads/tests
            # that only persisted "agreed" without verdict objects.
            # Use pass_threshold as the score when agreed (not a binary 100)
            # to avoid inflating gate outcomes.
            score = pass_threshold if entry.get("agreed") else 0
            reviewer_conf = (pass_threshold / 100.0) if entry.get("agreed") else 0.0
            arbiter_conf = (pass_threshold / 100.0) if entry.get("agreed") else 0.0
            evidence_mode = "agreement_fallback"

        passed = bool(entry.get("agreed")) and reviewer_approved and arbiter_approved and (
            score >= pass_threshold
        )
        feedback = []
        if score < pass_threshold:
            feedback.append(
                f"Review score {score} is below pass_threshold {pass_threshold}."
            )
        if not reviewer_approved or not arbiter_approved:
            feedback.append("Reviewer and Arbiter must both approve the design.")
        feedback.extend(DesignPhaseHandler._extract_review_feedback(reviewer_dict))
        feedback.extend(DesignPhaseHandler._extract_review_feedback(arbiter_dict))
        deduped_feedback: list[str] = []
        seen_feedback: set[str] = set()
        for item in feedback:
            if item not in seen_feedback:
                seen_feedback.add(item)
                deduped_feedback.append(item)

        return {
            "score": score,
            "threshold": pass_threshold,
            "passed": passed,
            "verdict": "pass" if passed else "fail",
            "evidence_mode": evidence_mode,
            "reviewer_approved": reviewer_approved,
            "arbiter_approved": arbiter_approved,
            "reviewer_confidence": reviewer_conf,
            "arbiter_confidence": arbiter_conf,
            "iterations": int(entry.get("iterations", 0) or 0),
            "actionable_feedback": deduped_feedback[:12],
        }

    @staticmethod
    def _flatten_parameter_values(
        value: Any,
        *,
        key_prefix: str = "",
    ) -> list[tuple[str, str]]:
        """Flatten nested parameter structures into key/value scalar pairs."""
        flattened: list[tuple[str, str]] = []
        if isinstance(value, dict):
            for key, child in value.items():
                next_prefix = f"{key_prefix}.{key}" if key_prefix else str(key)
                flattened.extend(
                    DesignPhaseHandler._flatten_parameter_values(
                        child,
                        key_prefix=next_prefix,
                    )
                )
            return flattened
        if isinstance(value, (list, tuple, set)):
            for idx, child in enumerate(value):
                next_prefix = f"{key_prefix}[{idx}]" if key_prefix else str(idx)
                flattened.extend(
                    DesignPhaseHandler._flatten_parameter_values(
                        child,
                        key_prefix=next_prefix,
                    )
                )
            return flattened
        if value is None:
            return flattened
        value_text = str(value).strip()
        if not value_text:
            return flattened
        flattened.append((key_prefix or "value", value_text))
        return flattened

    @staticmethod
    def _collect_resolved_parameters_for_task(
        task: SeedTask,
        *,
        inv_resolved_parameters: dict[str, Any] | None,
        onboarding_resolved_parameters: dict[str, Any] | None,
        parameter_sources: dict[str, Any] | None,
    ) -> list[dict[str, str]]:
        """Collect resolved parameter key/value pairs relevant to a task."""
        artifact_types = set(task.artifact_types_addressed or [])
        task_markers = {
            str(task.task_id or "").lower(),
            str(task.feature_id or "").lower(),
        } - {""}
        collected: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()

        def _emit(key: str, value: str, source: str) -> None:
            pair = (key, value)
            if pair in seen:
                return
            seen.add(pair)
            collected.append({"key": key, "value": value, "source": source})

        def _collect_from_mapping(data: dict[str, Any], source: str) -> None:
            for raw_key, raw_value in data.items():
                key_str = str(raw_key)
                key_lc = key_str.lower()
                if artifact_types:
                    if not any(atype in key_str for atype in artifact_types):
                        continue
                elif task_markers and not any(marker in key_lc for marker in task_markers):
                    # Without artifact typing, only evaluate task-scoped keys.
                    continue
                for param_key, param_val in DesignPhaseHandler._flatten_parameter_values(
                    raw_value,
                    key_prefix=key_str,
                ):
                    _emit(param_key, param_val, source)

        for source_name, mapping in [
            ("inventory", inv_resolved_parameters or {}),
            ("onboarding", onboarding_resolved_parameters or {}),
        ]:
            if isinstance(mapping, dict) and mapping:
                _collect_from_mapping(mapping, source_name)

        # Fallback path for seeds that only include parameter_sources.
        if (
            not collected
            and artifact_types
            and isinstance(parameter_sources, dict)
            and parameter_sources
        ):
            source_subset = parameter_sources
            if artifact_types:
                source_subset = {
                    atype: parameter_sources.get(atype)
                    for atype in artifact_types
                    if atype in parameter_sources
                }
            for source_key, source_val in source_subset.items():
                if isinstance(source_val, dict):
                    for param_key, param_val in source_val.items():
                        if isinstance(param_val, (str, int, float, bool)):
                            _emit(str(param_key), str(param_val), f"parameter_sources:{source_key}")

        return collected[:60]

    @staticmethod
    def _evaluate_parameter_completeness(
        implementation_spec: str,
        resolved_parameters: list[dict[str, str]],
        *,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Evaluate AR-139 parameter completeness against implementation spec text."""
        if not resolved_parameters:
            return {
                "status": "not_applicable",
                "passed": True,
                "evaluated_count": 0,
                "present_count": 0,
                "missing_count": 0,
                "missing": [],
                "dry_run": dry_run,
            }

        spec_text = implementation_spec or ""
        spec_lc = spec_text.lower()
        missing: list[dict[str, str]] = []
        present_count = 0

        for param in resolved_parameters:
            key = str(param.get("key", "") or "")
            value = str(param.get("value", "") or "")
            source = str(param.get("source", "unknown") or "unknown")
            value_candidates = {
                value.lower(),
                value.strip('"').strip("'").lower(),
            }
            key_candidate = key.lower()

            found = False
            for candidate in value_candidates:
                if candidate and len(candidate) >= 2 and candidate in spec_lc:
                    found = True
                    break
            if not found and key_candidate and len(key_candidate) >= 3 and key_candidate in spec_lc:
                found = True

            if found:
                present_count += 1
                continue

            missing.append({
                "key": key,
                "value": value,
                "source": source,
            })

        missing_count = len(missing)
        status = "pass" if missing_count == 0 else "fail"
        return {
            "status": status,
            "passed": missing_count == 0,
            "evaluated_count": len(resolved_parameters),
            "present_count": present_count,
            "missing_count": missing_count,
            "missing": missing,
            "dry_run": dry_run,
        }

    def _apply_design_quality_gates(
        self,
        *,
        task: SeedTask,
        entry: dict[str, Any],
        resolved_parameters: list[dict[str, str]],
        quality_policy_mode: str,
        dry_run: bool,
    ) -> None:
        """Apply AR-129 and AR-139 quality gates to a task design result."""
        design_text = str(entry.get("design_document", "") or "")
        if not design_text:
            design_text = str(entry.get("implementation_spec", "") or "")
        entry["implementation_spec"] = design_text
        entry["implementation_spec_artifact"] = {
            "kind": "inline_design_spec",
            "present": bool(design_text.strip()),
            "char_count": len(design_text),
            "line_count": len(design_text.splitlines()) if design_text else 0,
        }

        review_gate = self._build_review_gate(
            entry,
            pass_threshold=self.config.pass_threshold,
        )
        if dry_run:
            entry["review_gate"] = {
                "score": None,
                "threshold": self.config.pass_threshold,
                "passed": True,
                "verdict": "not_evaluated",
                "evidence_mode": "dry_run",
                "actionable_feedback": [],
            }
            entry["review_score"] = None
            entry["review_passed"] = True
            entry["review_verdict"] = "not_evaluated"
        else:
            entry["review_gate"] = review_gate
            entry["review_score"] = review_gate["score"]
            entry["review_passed"] = review_gate["passed"]
            entry["review_verdict"] = review_gate["verdict"]

        completeness = self._evaluate_parameter_completeness(
            design_text,
            resolved_parameters,
            dry_run=dry_run,
        )
        entry["parameter_completeness"] = completeness

        if completeness.get("missing_count", 0):
            missing_preview = ", ".join(
                f"{p['key']}={p['value']}"
                for p in completeness.get("missing", [])[:5]
            )
            feedback = (
                "Resolved parameters are missing from the implementation spec: "
                f"{missing_preview}. Add them verbatim to a Critical Parameters "
                "section and implementation steps."
            )
            entry["completeness_feedback"] = feedback
            prior_feedback = str(entry.get("next_iteration_feedback", "") or "").strip()
            entry["next_iteration_feedback"] = (
                f"{prior_feedback}\n{feedback}".strip()
                if prior_feedback
                else feedback
            )

        if not dry_run and review_gate.get("actionable_feedback"):
            review_feedback = "\n".join(
                f"- {line}" for line in review_gate["actionable_feedback"][:8]
            )
            entry["review_feedback"] = review_feedback
            prior_feedback = str(entry.get("next_iteration_feedback", "") or "").strip()
            entry["next_iteration_feedback"] = (
                f"{prior_feedback}\n{review_feedback}".strip()
                if prior_feedback
                else review_feedback
            )

        if dry_run:
            entry["completeness_gate_decision"] = "dry_run_report_only"
            return

        review_failed = not review_gate.get("passed", False)
        completeness_failed = not completeness.get("passed", True)

        if review_failed:
            entry["quality_failure_reason"] = "REVIEW_THRESHOLD_NOT_MET"
            entry.setdefault("non_agreement_reason_code", "REVIEW_THRESHOLD_NOT_MET")
            if entry.get("status") in ("designed", "refined", "adopted"):
                entry["status"] = "design_failed"
            if review_gate.get("actionable_feedback"):
                entry["error"] = (
                    "AR-129 threshold gate failed after "
                    f"{int(entry.get('iterations', 0) or 0)}/{self.config.max_iterations} "
                    "iterations. " + " ".join(review_gate["actionable_feedback"][:3])
                )
            entry["completeness_gate_decision"] = "not_evaluated_due_to_review_failure"
            return

        if completeness_failed:
            if quality_policy_mode == "block":
                entry["quality_failure_reason"] = "PARAMETER_COMPLETENESS_FAILED"
                entry.setdefault(
                    "non_agreement_reason_code",
                    "PARAMETER_COMPLETENESS_FAILED",
                )
                if entry.get("status") in ("designed", "refined", "adopted"):
                    entry["status"] = "design_failed"
                entry["error"] = (
                    "AR-139 completeness gate failed in block mode for "
                    f"{task.task_id}: {completeness.get('missing_count', 0)} parameter(s) missing."
                )
                entry["completeness_gate_decision"] = "blocked"
            else:
                entry["quality_failure_reason"] = "PARAMETER_COMPLETENESS_DEGRADED"
                entry["completeness_gate_decision"] = "degraded"
            return

        entry["completeness_gate_decision"] = "pass"

    @staticmethod
    def _task_quality_passed(entry: dict[str, Any]) -> bool:
        """Return whether a DESIGN task entry passes all quality gates."""
        status = entry.get("status", "")
        if status not in ("designed", "refined", "adopted"):
            return False
        if not bool(entry.get("agreed")):
            return False
        review_gate = entry.get("review_gate")
        if isinstance(review_gate, dict) and not bool(review_gate.get("passed", False)):
            return False
        completeness = entry.get("parameter_completeness")
        if isinstance(completeness, dict) and not bool(completeness.get("passed", False)):
            return False
        return True

    @staticmethod
    def _task_quality_reason(entry: dict[str, Any]) -> str | None:
        """Return machine-friendly reason for DESIGN quality failure."""
        if entry.get("status") == "design_failed":
            return str(
                entry.get("quality_failure_reason")
                or entry.get("non_agreement_reason_code")
                or "DESIGN_FAILED"
            )
        if not bool(entry.get("agreed")):
            return str(entry.get("non_agreement_reason_code") or "DESIGN_NOT_AGREED")
        review_gate = entry.get("review_gate")
        if isinstance(review_gate, dict) and not bool(review_gate.get("passed", True)):
            return "REVIEW_THRESHOLD_NOT_MET"
        completeness = entry.get("parameter_completeness")
        if isinstance(completeness, dict) and not bool(completeness.get("passed", False)):
            decision = str(entry.get("completeness_gate_decision", "") or "")
            if decision == "degraded":
                return "PARAMETER_COMPLETENESS_DEGRADED"
            return "PARAMETER_COMPLETENESS_FAILED"
        return None

    @staticmethod
    def _evaluate_high_signal_floor(feature_context: Any) -> list[str]:
        """Return missing high-signal context fields for design quality floor."""
        missing: list[str] = []
        requirements_text = (getattr(feature_context, "requirements_text", "") or "")
        if not requirements_text.strip():
            missing.append("requirements_text")
        additional_context = getattr(feature_context, "additional_context", {}) or {}
        has_arch_or_goals = bool(
            additional_context.get("plan_architecture")
            or additional_context.get("project_goals")
        )
        if not has_arch_or_goals:
            missing.append("plan_architecture_or_project_goals")
        if not additional_context.get("critical_parameters_checklist"):
            missing.append("critical_parameters_checklist")
        return missing

    @staticmethod
    def _is_truthy_flag(value: Any) -> bool:
        """Parse permissive truthy values from context/env/config."""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return False

    @staticmethod
    def _select_design_route(
        task: SeedTask,
        *,
        use_modular_prompts: bool,
        force_canonical: bool,
        shared_file_manifest: dict[str, list[str]],
        scaffold_existing_files: set[str],
    ) -> dict[str, Any]:
        """Policy-driven DESIGN routing with auditable criteria values."""
        contested_file_count = sum(
            1 for tf in task.target_files
            if _normalize_target_path(tf) in shared_file_manifest
        )
        dependency_density = len(task.depends_on) / max(1, len(task.target_files))
        edit_mode = any(tf in scaffold_existing_files for tf in task.target_files) or bool(
            task.existing_content_hash
        )
        target_file_count = len(task.target_files)
        estimated_loc = int(task.estimated_loc or 0)

        risk_signals: list[str] = []
        risk_score = 0
        if estimated_loc >= 500:
            risk_signals.append("large_loc")
            risk_score += 2
        elif estimated_loc >= 250:
            risk_signals.append("medium_loc")
            risk_score += 1
        if contested_file_count > 0:
            risk_signals.append("contested_files")
            risk_score += 2
        if dependency_density >= 1.0:
            risk_signals.append("high_dependency_density")
            risk_score += 1
        if edit_mode:
            risk_signals.append("edit_mode")
            risk_score += 1
        if target_file_count > 2:
            risk_signals.append("wide_file_scope")
            risk_score += 1

        route = "v1"
        reason = "modular_disabled"
        if force_canonical:
            route = "v1"
            reason = "kill_switch_force_canonical"
        elif use_modular_prompts:
            if risk_score >= 3:
                route = "v1"
                reason = "policy_high_risk_canonical"
            else:
                route = "v2"
                reason = "policy_low_risk_modular"

        return {
            "selected_prompt_version": route,
            "reason": reason,
            "criteria": {
                "estimated_loc": estimated_loc,
                "contested_file_count": contested_file_count,
                "dependency_density": round(dependency_density, 3),
                "edit_mode": edit_mode,
                "target_file_count": target_file_count,
                "depends_on_count": len(task.depends_on),
            },
            "risk_score": risk_score,
            "risk_signals": risk_signals,
            "force_canonical": force_canonical,
            "modular_opt_in": use_modular_prompts,
        }

    @staticmethod
    def _path_tag_for_prompt_version(prompt_version: str) -> str:
        """Normalize prompt_version into canonical/variant path tags."""
        if prompt_version == "v1":
            return "canonical"
        if prompt_version == "v2":
            return "variant"
        return "unknown"

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
        _log_context_completeness("DESIGN", context)
        tasks: list[SeedTask] = _ensure_context_loaded(context)

        logger.info("DESIGN phase: processing %d tasks (dry_run=%s)", len(tasks), dry_run)
        if self.config.use_modular_prompts:
            logger.warning(
                "DESIGN: modular prompt path explicitly enabled "
                "(use_modular_prompts=True)"
            )
        _force_canonical_flag = context.get(
            "force_canonical_design_route",
            (
                self.config.force_canonical_design_route
                or os.getenv("STARTD8_FORCE_CANONICAL_DESIGN_ROUTE")
            ),
        )
        _force_canonical_design_route = self._is_truthy_flag(_force_canonical_flag)
        if _force_canonical_design_route:
            logger.warning(
                "DESIGN: canonical route kill switch enabled "
                "(force_canonical_design_route=%r)",
                _force_canonical_flag,
            )

        # REQ-PD-010: Source checksum drift detection (advisory only)
        _source_checksum = context.get("source_checksum")
        _source_checksum_status = "unavailable"
        if _source_checksum:
            # Try to find a reference file to verify against
            _ref_file: Path | None = None
            for _candidate_dir in [
                Path(self.output_dir) if self.output_dir else None,
                Path(context.get("enriched_seed_path", "")).parent if context.get("enriched_seed_path") else None,
            ]:
                if _candidate_dir is None:
                    continue
                for _fname in (".contextcore.yaml", "onboarding-metadata.json"):
                    _cpath = _candidate_dir / _fname
                    if _cpath.exists():
                        _ref_file = _cpath
                        break
                if _ref_file:
                    break

            if _ref_file:
                try:
                    _ref_hash = hashlib.sha256(
                        _ref_file.read_bytes()
                    ).hexdigest()
                    if _ref_hash == _source_checksum:
                        _source_checksum_status = "match"
                        logger.info(
                            "DESIGN: source_checksum MATCH — provenance intact "
                            "(ref=%s)", _ref_file.name,
                        )
                    else:
                        _source_checksum_status = "mismatch"
                        logger.warning(
                            "DESIGN: source_checksum MISMATCH — reference file "
                            "%s may have changed since plan ingestion "
                            "(expected %s..., got %s...)",
                            _ref_file.name,
                            _source_checksum[:16],
                            _ref_hash[:16],
                        )
                except OSError:
                    logger.debug(
                        "DESIGN: could not read reference file for checksum verification"
                    )
            else:
                logger.debug(
                    "DESIGN: no reference file found for source_checksum verification"
                )
        else:
            logger.debug("DESIGN: source_checksum not present in context")
        context["_source_checksum_status"] = _source_checksum_status

        # REQ-PD-013: Chain status logging — assess Plan→Design data chain
        _chain_signals = {
            "plan_document_text": bool(context.get("plan_document_text")),
            "complexity_dimensions": bool(context.get("complexity_dimensions")),
            "complexity_composite": context.get("complexity_composite") is not None,
            "wave_metadata": bool(context.get("wave_metadata")),
            "architectural_context": bool(context.get("architectural_context")),
            "design_calibration": bool(context.get("design_calibration")),
            "source_checksum": bool(context.get("source_checksum")),
        }
        _chain_present = sum(1 for v in _chain_signals.values() if v)
        _chain_total = len(_chain_signals)
        if _chain_present == _chain_total:
            _pi_design_chain_status = "INTACT"
        elif _chain_present > 0:
            _pi_design_chain_status = "DEGRADED"
        else:
            _pi_design_chain_status = "BROKEN"
        context["_pi_design_chain_status"] = _pi_design_chain_status
        logger.info(
            "DESIGN: Plan→Design chain status: %s (%d/%d signals present: %s)",
            _pi_design_chain_status, _chain_present, _chain_total,
            {k for k, v in _chain_signals.items() if v},
        )
        _quality_gate_summary = context.get("quality_gate_summary", {}) or {}
        quality_policy_mode = str(
            _quality_gate_summary.get("policy_mode", "warn")
        ).lower()
        if quality_policy_mode not in {"skip", "warn", "block"}:
            quality_policy_mode = "warn"

        design_results: dict[str, dict[str, Any]] = {}
        total_cost = 0.0
        tasks_designed = 0
        tasks_agreed = 0
        tasks_failed = 0
        tasks_adopted = 0
        tasks_refined = 0
        route_decision_counts: dict[str, int] = defaultdict(int)
        route_quality_counts: dict[str, dict[str, int]] = defaultdict(
            lambda: {"passed": 0, "failed": 0}
        )
        path_quality_counts: dict[str, dict[str, int]] = defaultdict(
            lambda: {"passed": 0, "failed": 0}
        )

        # Prior design_results injected via --adopt-prior (or checkpoint resume)
        prior_design_results: dict[str, dict[str, Any]] = context.get("design_results", {})

        # --- Auto-load prior design results from disk (handoff.json) ---
        # Mirror IMPLEMENT's auto-cache pattern: check disk first, adopt
        # automatically. --adopt-prior injects via context; this covers the
        # case where no flag was passed but a handoff exists from a prior run.
        if not prior_design_results and not dry_run and not self.config.force_design:
            if self.output_dir:
                from startd8.contractors.handoff import (
                    load_design_handoff,
                    DESIGN_HANDOFF_FILENAME,
                    validate_handoff_against_context,
                    verify_context_checksums,
                )
                handoff_path = Path(self.output_dir) / DESIGN_HANDOFF_FILENAME
                if handoff_path.exists():
                    try:
                        handoff = load_design_handoff(handoff_path)
                        if handoff.design_results:
                            # Cross-validate handoff against current context
                            validation_warnings = validate_handoff_against_context(
                                handoff, context,
                            )
                            # Verify context file checksums for drift
                            if handoff.context_files:
                                checksum_warnings = verify_context_checksums(
                                    handoff.context_files,
                                )
                                for w in checksum_warnings:
                                    logger.warning("DESIGN: handoff checksum: %s", w)
                                validation_warnings.extend(checksum_warnings)

                            if validation_warnings:
                                for w in validation_warnings:
                                    logger.warning("DESIGN: handoff validation: %s", w)
                                logger.warning(
                                    "DESIGN: handoff has %d validation warning(s) — "
                                    "adopting anyway (use --force-design to regenerate)",
                                    len(validation_warnings),
                                )

                            prior_design_results = handoff.design_results
                            logger.info(
                                "DESIGN: auto-loaded %d prior design result(s) from %s",
                                len(prior_design_results), handoff_path,
                            )
                            # C-5: Compute design_quality from prior results
                            # so that downstream consumers (handoff write,
                            # DesignPhaseOutput validation) have it available
                            # even before the end-of-phase quality loop runs.
                            _adopted_passed = 0
                            _adopted_failed = 0
                            for _adr in prior_design_results.values():
                                if not isinstance(_adr, dict):
                                    continue
                                _adr_status = _adr.get("status", "")
                                if _adr_status in (
                                    "dry_run_skipped", "env_blocked",
                                ):
                                    continue
                                if _adr.get("agreed"):
                                    _adopted_passed += 1
                                else:
                                    _adopted_failed += 1
                            _adopted_total = _adopted_passed + _adopted_failed
                            _adopted_agreement = (
                                _adopted_passed / _adopted_total
                                if _adopted_total > 0
                                else 0.0
                            )
                            context["design_quality"] = {
                                "total_passed": _adopted_passed,
                                "total_failed": _adopted_failed,
                                "agreement_rate": _adopted_agreement,
                                "evaluated_task_count": _adopted_total,
                            }
                            logger.info(
                                "DESIGN: pre-seeded design_quality from "
                                "prior results: passed=%d, failed=%d, "
                                "agreement_rate=%.2f",
                                _adopted_passed,
                                _adopted_failed,
                                _adopted_agreement,
                            )
                    except (FileNotFoundError, ValueError, KeyError, TypeError) as exc:
                        logger.warning(
                            "DESIGN: failed to auto-load handoff from %s: %s",
                            handoff_path, exc,
                        )

        # Phase 5: Manifest registry resolution for DESIGN (CS-1)
        _design_manifest_registry = None
        if self.config.manifest_consumption_enabled:
            _design_manifest_registry = (
                self.config.manifest_registry
                or context.get("project_manifests")
            )
        if _design_manifest_registry is not None:
            logger.info("DESIGN: manifest registry available for structural context")
        else:
            logger.info(
                "manifest.fallback",
                extra={
                    "surface": "design_enrichment",
                    "reason": (
                        "registry_unavailable"
                        if not self.config.manifest_consumption_enabled
                        else "no_registry"
                    ),
                },
            )

        # Extract shared context for cross-task design quality
        plan_goals = context.get("plan_goals", [])
        arch_context = context.get("architectural_context", {})
        calibration_map = context.get("design_calibration", {})
        prior_summaries: list[str] = []
        previous_task_started_mono: Optional[float] = None
        # REQ-PD-007: Completed design summaries for dependency injection
        completed_designs: dict[str, str] = {}
        # REQ-PD-008: Wave boundary tracking
        _prev_wave_index: int | None = None

        # Mottainai: load artifact inventory from export-stage provenance
        inv_derivation_rules: dict[str, Any] | None = None
        inv_resolved_parameters: dict[str, Any] | None = None
        inv_output_contracts: dict[str, Any] | None = None
        inv_refine_suggestions: str | list[dict[str, Any]] | None = None
        inv_plan_document: str | None = None
        inv_calibration_hints: dict[str, Any] | None = None

        inventory_dir = None
        if self.output_dir:
            # Derive export output dir: check output_dir first, then parent
            for candidate in [Path(self.output_dir), Path(self.output_dir).parent]:
                if (candidate / "run-provenance.json").exists():
                    inventory_dir = candidate
                    break
        # Also check enriched_seed_path parent (common in artisan runs)
        if not inventory_dir:
            seed_path = context.get("enriched_seed_path", "")
            if seed_path:
                candidate = Path(seed_path).parent
                if (candidate / "run-provenance.json").exists():
                    inventory_dir = candidate

        if inventory_dir:
            inventory = load_inventory(inventory_dir)
            if inventory:
                for role, var_name in [
                    ("derivation_rules", "inv_derivation_rules"),
                    ("resolved_parameters", "inv_resolved_parameters"),
                    ("output_contracts", "inv_output_contracts"),
                    ("calibration_hints", "inv_calibration_hints"),
                ]:
                    entry, outcome = lookup_artifact(inventory, role)
                    if entry and outcome == "hit":
                        data = load_artifact_content(entry, inventory_dir)
                        if data and isinstance(data, dict):
                            if var_name == "inv_derivation_rules":
                                inv_derivation_rules = data
                            elif var_name == "inv_resolved_parameters":
                                inv_resolved_parameters = data
                            elif var_name == "inv_output_contracts":
                                inv_output_contracts = data
                            elif var_name == "inv_calibration_hints":
                                inv_calibration_hints = data

                # Refine suggestions (text, not dict)
                entry, outcome = lookup_artifact(inventory, "refine_suggestions")
                if entry and outcome == "hit":
                    data = load_artifact_content(entry, inventory_dir)
                    if isinstance(data, str):
                        inv_refine_suggestions = data

                # Plan document (text)
                entry, outcome = lookup_artifact(inventory, "plan_document")
                if entry and outcome == "hit":
                    # plan_document may be a markdown file read as text
                    source_file = entry.get("source_file", "")
                    if source_file:
                        plan_path = inventory_dir / source_file
                        if plan_path.exists():
                            try:
                                inv_plan_document = plan_path.read_text(
                                    encoding="utf-8"
                                )
                            except OSError:
                                logger.debug("Could not read file: %s", plan_path, exc_info=True)

        # Mottainai fallback: when inventory lookup didn't find these fields,
        # try the onboarding-metadata forwarded through the seed by PLAN phase.
        _fallback_map = [
            ("inv_derivation_rules", "onboarding_derivation_rules"),
            ("inv_resolved_parameters", "onboarding_resolved_parameters"),
            ("inv_output_contracts", "onboarding_output_contracts"),
            ("inv_calibration_hints", "onboarding_calibration_hints"),
        ]
        _fb_count = 0
        for local_var, ctx_key in _fallback_map:
            if locals()[local_var] is None:
                fb_val = context.get(ctx_key)
                if fb_val and isinstance(fb_val, dict):
                    if local_var == "inv_derivation_rules":
                        inv_derivation_rules = fb_val
                    elif local_var == "inv_resolved_parameters":
                        inv_resolved_parameters = fb_val
                    elif local_var == "inv_output_contracts":
                        inv_output_contracts = fb_val
                    elif local_var == "inv_calibration_hints":
                        inv_calibration_hints = fb_val
                    _fb_count += 1
        if _fb_count:
            logger.info(
                "DESIGN: %d inventory field(s) loaded from onboarding fallback",
                _fb_count,
            )

        # IMP-8a: structured onboarding fallback — prefer structured triage
        # decisions from REFINE forwarding (REQ-RF-003) over text extraction
        if inv_refine_suggestions is None:
            structured = context.get("onboarding_refine_suggestions")
            if structured and isinstance(structured, list):
                inv_refine_suggestions = structured
                logger.info(
                    "DESIGN: refine_suggestions loaded from onboarding (%d entries)",
                    len(structured),
                )

        # Mottainai B2+B3 fallback: when inventory didn't find plan_document
        # or refine_suggestions, use the plan document text loaded by PLAN phase
        # directly from the seed's artifacts.plan_document_path.
        if inv_plan_document is None:
            plan_text = context.get("plan_document_text")
            if plan_text and isinstance(plan_text, str):
                inv_plan_document = plan_text
                logger.info(
                    "DESIGN: plan_document loaded from seed fallback (%d chars)",
                    len(plan_text),
                )
        if inv_refine_suggestions is None and inv_plan_document:
            # REFINE suggestions live inside the plan document (Appendix C).
            # When loaded via seed fallback, the full plan text IS the source.
            inv_refine_suggestions = inv_plan_document
            logger.info("DESIGN: refine_suggestions derived from plan document text")

        # ==============================================================
        # CCD-100: Compute lane assignments at DESIGN time
        # ==============================================================
        _design_lanes: list[list[SeedTask]] | None = None
        _lane_assignments: dict[str, int] = {}
        try:
            _design_lanes = compute_lanes(tasks)
            for _lane_idx, _lane_tasks in enumerate(_design_lanes):
                for _lt in _lane_tasks:
                    _lane_assignments[_lt.task_id] = _lane_idx
            logger.info(
                "DESIGN: computed %d lane(s) for %d tasks",
                len(_design_lanes), len(tasks),
            )
        except Exception as _lane_exc:
            # CCD-104: Graceful fallback
            logger.warning(
                "DESIGN: compute_lanes() failed — falling back to flat "
                "iteration: %s",
                _lane_exc,
            )
            _design_lanes = None

        # CCD-603: Lane computation state flags for FINALIZE coherence summary
        context["_design_lane_computation_skipped"] = _design_lanes is None
        context["_design_lane_count"] = (
            len(_design_lanes) if _design_lanes else 0
        )

        # CCD-101: Wave-sort tasks within each lane
        if _design_lanes is not None:
            for _li, _lane in enumerate(_design_lanes):
                _design_lanes[_li] = sorted(
                    _lane,
                    key=lambda t: (
                        t.wave_index if t.wave_index is not None else float("inf"),
                        t.task_id,
                    ),
                )

        # CCD-300: Build shared-file manifest
        shared_file_manifest: dict[str, list[str]] = {}
        try:
            shared_file_manifest = build_shared_file_manifest(tasks)
            if shared_file_manifest:
                logger.info(
                    "DESIGN: %d contested file(s) across %d tasks",
                    len(shared_file_manifest),
                    len({tid for tids in shared_file_manifest.values() for tid in tids}),
                )
        except Exception as exc:
            logger.warning("DESIGN: manifest computation failed: %s", exc)
            shared_file_manifest = {}
        _scaffold_existing_for_route = set(
            context.get("scaffold", {}).get("existing_target_files", [])
        )

        # CCD-302: Lane-to-file mapping
        lane_to_file_mapping: dict[int, list[str]] = {}
        if _design_lanes is not None and shared_file_manifest:
            lane_to_file_mapping = compute_lane_to_file_mapping(
                _design_lanes, shared_file_manifest,
            )

        # CCD-400: Validate wave_index populated at DESIGN time
        _tasks_without_wave = [t.task_id for t in tasks if t.wave_index is None]
        if _tasks_without_wave:
            logger.warning(
                "DESIGN: %d task(s) have no wave_index: %s",
                len(_tasks_without_wave),
                ", ".join(_tasks_without_wave[:10]),
            )

        # CCD-403: Critical-path task detection
        _critical_task_ids: set[str] = set()
        try:
            _critical_task_ids = compute_critical_path_tasks(
                tasks, shared_file_manifest,
            )
            if _critical_task_ids:
                logger.info(
                    "DESIGN: %d critical-path task(s): %s",
                    len(_critical_task_ids),
                    ", ".join(sorted(_critical_task_ids)),
                )
        except Exception as _crit_exc:
            logger.warning("DESIGN: critical-path detection failed: %s", _crit_exc)

        # CCD-200: Lane-peer design accumulator
        lane_prior_designs: list[dict[str, Any]] = []
        # CCD-303: Task title lookup for contested file annotations
        _task_title_lookup = {t.task_id: t.title for t in tasks}

        # CCD-102: Lane-sequential design iteration
        _current_lane_idx: int = -1
        if _design_lanes is not None:
            _iteration_order: list[tuple[int, SeedTask, int]] = []
            _global_idx = 0
            for _li, _lane in enumerate(_design_lanes):
                for _task in _lane:
                    _global_idx += 1
                    _iteration_order.append((_global_idx, _task, _li))
        else:
            # CCD-104: Flat iteration fallback
            _iteration_order = [
                (i, t, 0) for i, t in enumerate(tasks, start=1)
            ]

        for idx, task, _task_lane_idx in _iteration_order:
            # CCD-200: Reset lane-peer accumulator at lane boundary
            if _task_lane_idx != _current_lane_idx:
                lane_prior_designs = []
                _current_lane_idx = _task_lane_idx
            _task_span_cm = _phase_tracer.start_as_current_span(
                f"task.{task.task_id}",
                attributes={
                    "task.id": task.task_id,
                    "task.title": task.title,
                    "task.domain": task.domain or "",
                    "task.phase": "design",
                    "task.target_files": ",".join(task.target_files[:5]),
                    # CCD-601: lane-awareness attributes
                    "task.lane_index": _lane_assignments.get(task.task_id, 0),
                    "task.lane_peer_count": (
                        len(_design_lanes[_lane_assignments[task.task_id]]) - 1
                        if _design_lanes and task.task_id in _lane_assignments
                        else -1
                    ),
                    "task.shared_file_count": sum(
                        1 for tf in task.target_files
                        if _normalize_target_path(tf) in shared_file_manifest
                    ) if shared_file_manifest else 0,
                },
            )
            _task_span = _task_span_cm.__enter__()
            previous_task_started_mono = _log_task_timing(
                "DESIGN",
                task.task_id,
                idx,
                len(tasks),
                start,
                previous_task_started_mono,
            )
            _log_task_boundary_start(task, phase="design")
            # Skip tasks with env failures
            env_fails = [
                c for c in task.environment_checks
                if c.get("status") == "fail"
            ]
            if env_fails:
                logger.warning(
                    "DESIGN: skipping task %s — env_blocked (%d failing check(s): %s)",
                    task.task_id,
                    len(env_fails),
                    ", ".join(c.get("check_name", "?") for c in env_fails),
                )
                design_results[task.task_id] = {
                    "status": "env_blocked",
                    "environment_issues": env_fails,
                    "prompt_version": "n/a",
                    "path_tag": "unknown",
                    "quality_outcome": "not_evaluated",
                }
                _task_span.set_attribute("task.status", "env_blocked")
                _sc = _capture_task_span_context(_task_span)
                if _sc:
                    design_results[task.task_id]["_span_context"] = _sc
                _log_task_boundary_complete(
                    task.task_id,
                    status="env_blocked",
                    phase="design",
                )
                _task_span_cm.__exit__(None, None, None)
                continue

            # ----------------------------------------------------------
            # Three-way branch: adopt / refine / fresh generation
            # ----------------------------------------------------------
            prior = prior_design_results.get(task.task_id, {})
            prior_design_text: str | None = None
            carry_forward_quality_feedback = "\n".join(
                part.strip()
                for part in [
                    str(prior.get("next_iteration_feedback", "") or ""),
                    str(prior.get("completeness_feedback", "") or ""),
                    str(prior.get("review_feedback", "") or ""),
                ]
                if part and part.strip()
            ).strip()
            task_resolved_parameters = self._collect_resolved_parameters_for_task(
                task,
                inv_resolved_parameters=inv_resolved_parameters,
                onboarding_resolved_parameters=context.get(
                    "onboarding_resolved_parameters"
                ),
                parameter_sources=context.get("parameter_sources", {}),
            )

            if (
                prior.get("status") in ("designed", "adopted")
                and prior.get("design_document")
            ):
                if self.config.refine_design:
                    # Refine mode: pass prior design to LLM for improvement
                    prior_design_text = prior["design_document"]
                    logger.info(
                        "DESIGN: will refine prior design for %s via LLM",
                        task.task_id,
                    )
                else:
                    # Adopt as-is (existing behavior)
                    adopted_entry = {
                        **prior,
                        "status": "adopted",
                        "adopted_from": "prior_design_results",
                    }
                    adopted_prompt_version = adopted_entry.get(
                        "prompt_version", "v1",
                    )
                    adopted_path_tag = self._path_tag_for_prompt_version(
                        adopted_prompt_version
                    )
                    adopted_entry["path_tag"] = adopted_path_tag
                    adopted_entry.setdefault(
                        "route_policy",
                        {
                            "selected_prompt_version": adopted_prompt_version,
                            "reason": "adopted_prior_result",
                            "criteria": {},
                            "risk_score": 0,
                            "risk_signals": [],
                            "force_canonical": _force_canonical_design_route,
                            "modular_opt_in": self.config.use_modular_prompts,
                        },
                    )
                    self._apply_design_quality_gates(
                        task=task,
                        entry=adopted_entry,
                        resolved_parameters=task_resolved_parameters,
                        quality_policy_mode=quality_policy_mode,
                        dry_run=False,
                    )
                    design_results[task.task_id] = adopted_entry
                    route_decision_counts[adopted_prompt_version] += 1
                    if adopted_entry.get("status") == "design_failed":
                        tasks_failed += 1
                    else:
                        tasks_adopted += 1
                    if adopted_entry.get("agreed"):
                        tasks_agreed += 1
                    adopted_quality_passed = self._task_quality_passed(adopted_entry)
                    if adopted_quality_passed:
                        route_quality_counts[adopted_prompt_version]["passed"] += 1
                        path_quality_counts[adopted_path_tag]["passed"] += 1
                        adopted_entry["quality_outcome"] = "pass"
                    else:
                        route_quality_counts[adopted_prompt_version]["failed"] += 1
                        path_quality_counts[adopted_path_tag]["failed"] += 1
                        adopted_entry["quality_outcome"] = "fail"

                    doc_text = prior["design_document"]
                    if adopted_entry.get("status") != "design_failed":
                        # Feed into cross-task progressive context
                        first_line = doc_text[:300].split("\n")[0]
                        summary = f"{task.task_id} ({task.title}): {first_line}"
                        prior_summaries.append(summary)
                        # REQ-PD-007: Track completed designs for dependency injection
                        completed_designs[task.task_id] = summary
                        # CCD-200/205: Lane-peer design accumulation
                        lane_prior_designs.append({
                            "task_id": task.task_id,
                            "title": task.title,
                            "design_document": doc_text,
                        })
                    # CCD-401: Wave/lane metadata in design results
                    design_results[task.task_id].update(
                        _compute_ccd_task_metadata(
                            task, _lane_assignments, _design_lanes,
                            len(tasks), shared_file_manifest, _critical_task_ids,
                        )
                    )

                    # Copy design doc to current output_dir if configured
                    if self.output_dir:
                        out_path = Path(self.output_dir) / f"{task.task_id}-design.md"
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        out_path.write_text(doc_text, encoding="utf-8")
                        design_results[task.task_id]["output_file"] = str(out_path)

                    # PCA-605c: extract file decisions from adopted design doc
                    if doc_text and task.target_files:
                        if "discovered_target_files" not in design_results[task.task_id]:
                            _discovered = _extract_design_target_files(
                                doc_text, task.target_files,
                            )
                            if _discovered != task.target_files:
                                design_results[task.task_id]["discovered_target_files"] = _discovered
                                logger.info(
                                    "DESIGN→IMPLEMENT file propagation (adopted): task %s "
                                    "target_files expanded %s → %s",
                                    task.task_id,
                                    task.target_files,
                                    _discovered,
                                )

                    logger.info(
                        "DESIGN: adopted prior result for %s (agreed=%s, cost=$%.4f)",
                        task.task_id, prior.get("agreed"), prior.get("cost", 0.0),
                    )
                    _task_span.set_attribute(
                        "task.status",
                        str(adopted_entry.get("status", "adopted")),
                    )
                    _sc = _capture_task_span_context(_task_span)
                    if _sc:
                        design_results[task.task_id]["_span_context"] = _sc
                    _log_task_boundary_complete(
                        task.task_id,
                        status=str(adopted_entry.get("status", "adopted")),
                        phase="design",
                        cost_usd=_coerce_optional_float(
                            design_results[task.task_id].get("cost")
                        ),
                    )
                    _task_span_cm.__exit__(None, None, None)
                    continue

            if dry_run:
                dry_run_entry = {
                    "status": "dry_run_skipped",
                    "title": task.title,
                    "target_file": task.target_files[0] if task.target_files else "",
                    "constraints_count": len(task.prompt_constraints),
                    "domain": task.domain,
                    "prompt_version": "n/a",
                    "path_tag": "unknown",
                    "quality_outcome": "not_evaluated",
                    "implementation_spec": task.description,
                }
                self._apply_design_quality_gates(
                    task=task,
                    entry=dry_run_entry,
                    resolved_parameters=task_resolved_parameters,
                    quality_policy_mode=quality_policy_mode,
                    dry_run=True,
                )
                design_results[task.task_id] = dry_run_entry
                _task_span.set_attribute("task.status", "dry_run_skipped")
                _sc = _capture_task_span_context(_task_span)
                if _sc:
                    design_results[task.task_id]["_span_context"] = _sc
                _log_task_boundary_complete(
                    task.task_id,
                    status="dry_run_skipped",
                    phase="design",
                )
                _task_span_cm.__exit__(None, None, None)
                continue

            # REQ-PD-008: Wave boundary logging
            if task.wave_index is not None and task.wave_index != _prev_wave_index:
                if _prev_wave_index is not None:
                    _wave_task_count = sum(
                        1 for _, t, _ in _iteration_order
                        if t.wave_index == task.wave_index
                    )
                    logger.info(
                        "DESIGN: wave boundary %d → %d (%d tasks in wave %d)",
                        _prev_wave_index, task.wave_index,
                        _wave_task_count, task.wave_index,
                    )
                _prev_wave_index = task.wave_index

            # REQ-PD-007: Build dependency designs from completed_designs
            _dep_designs: dict[str, str] = {}
            for _dep_id in (task.depends_on or []):
                if _dep_id in completed_designs:
                    _dep_designs[_dep_id] = completed_designs[_dep_id]
                else:
                    logger.debug(
                        "DESIGN: task %s depends on %s but design not yet "
                        "available (may be in a later wave or failed)",
                        task.task_id, _dep_id,
                    )

            # REQ-PD-002/007/008/009: Build bridge_context
            _bridge_context: dict[str, Any] = {}
            if context.get("complexity_dimensions"):
                _bridge_context["complexity_dimensions"] = context["complexity_dimensions"]
            if context.get("complexity_composite") is not None:
                _bridge_context["complexity_composite"] = context["complexity_composite"]
            if _dep_designs:
                _bridge_context["dependency_designs"] = _dep_designs
            _scaffold = context.get("scaffold", {})
            if _scaffold.get("staleness_classification"):
                _bridge_context["staleness_classification"] = _scaffold["staleness_classification"]
            if context.get("wave_metadata"):
                _bridge_context["wave_metadata"] = context["wave_metadata"]
            if task.wave_index is not None:
                _bridge_context["wave_index"] = task.wave_index

            # Real-mode: run design documentation phase per task
            task_calibration = calibration_map.get(task.task_id, {})

            # Snapshot cost before this task
            backend = self._get_llm_backend()
            cost_before = backend.total_cost_usd

            # Retry loop for transient API errors (e.g. APIConnectionError, 529)
            _design_retry_config = RetryConfig(
                max_attempts=1,  # Placeholder for API compat — retry orchestration is handled by the outer _max_attempts loop with phase-aware backoff
                base_delay=5.0,
                max_delay=60.0,
                retryable_exceptions=(ConnectionError, TimeoutError, OSError),
                retryable_status_codes=(429, 500, 502, 503, 504, 529),
            )
            _max_attempts = 1 + self.config.design_task_retries
            route_policy = self._select_design_route(
                task,
                use_modular_prompts=self.config.use_modular_prompts,
                force_canonical=_force_canonical_design_route,
                shared_file_manifest=shared_file_manifest,
                scaffold_existing_files=_scaffold_existing_for_route,
            )
            selected_prompt_version = route_policy["selected_prompt_version"]
            logger.info(
                "DESIGN route policy: task=%s -> %s (%s) criteria=%s risk=%d",
                task.task_id,
                selected_prompt_version,
                route_policy["reason"],
                route_policy["criteria"],
                route_policy["risk_score"],
            )

            for _attempt in range(_max_attempts):
                try:
                    _wt_capture_dir: Optional[Path] = None
                    if self.config.walkthrough:
                        _wt_root = (
                            Path(context.get("project_root", ""))
                            if context.get("project_root")
                            else Path(".")
                        )
                        _wt_capture_dir = (
                            _wt_root / ".startd8" / "walkthrough"
                            / "design" / task.task_id
                        )
                    feature_context = None
                    if selected_prompt_version == "v2":
                        # ── V2: modular prompt + single LLM call ──
                        # Dual-review envelope is still required for acceptance.
                        from startd8.contractors.artisan_phases.design_prompts import (
                            assemble_design_prompt,
                        )
                        from startd8.contractors.artisan_phases.design_documentation import (
                            DesignDocument,
                        )
                        _v2_system, _v2_user, _v2_max_tokens = assemble_design_prompt(
                            task,
                            plan_goals=plan_goals,
                            architectural_context=arch_context,
                            prior_design_summaries=prior_summaries,
                            calibration=task_calibration,
                            design_max_tokens_override=self.config.design_max_tokens,
                            dependency_designs=_dep_designs,
                            scaffold_existing_files=context.get(
                                "scaffold", {},
                            ).get("existing_target_files", []),
                            staleness_classification=_scaffold.get(
                                "staleness_classification",
                            ),
                            wave_index=task.wave_index,
                            wave_metadata=context.get("wave_metadata"),
                            parameter_sources=context.get("parameter_sources", {}),
                            semantic_conventions=context.get(
                                "semantic_conventions", {},
                            ),
                            refine_suggestions=inv_refine_suggestions,
                            open_questions=context.get("onboarding_open_questions"),
                            calibration_hints=inv_calibration_hints,
                            complexity_dimensions=context.get("complexity_dimensions"),
                            prior_design_text=prior_design_text,
                            # Phase 5: Manifest context for V2 path
                            manifest_registry=_design_manifest_registry,
                            manifest_context_budget=self.config.manifest_context_budget,
                            enable_introspect=self.config.enable_introspect,
                        )
                        if carry_forward_quality_feedback:
                            _v2_user = (
                                _v2_user
                                + "\n\n# Prior Quality Feedback\n"
                                + carry_forward_quality_feedback
                            )
                        _high_signal_missing: list[str] = []
                        if not (
                            (task.requirements_text or "").strip()
                            or (context.get("plan_document_text") or "").strip()
                        ):
                            _high_signal_missing.append("requirements_text")
                        if not (arch_context or plan_goals):
                            _high_signal_missing.append("plan_architecture_or_project_goals")
                        if not context.get("parameter_sources"):
                            _high_signal_missing.append("critical_parameters_checklist")
                        if _high_signal_missing:
                            logger.warning(
                                "DESIGN task %s high-signal floor degraded (v2): %s",
                                task.task_id,
                                ", ".join(_high_signal_missing),
                            )
                        if _wt_capture_dir is not None:
                            _wt_capture_dir.mkdir(parents=True, exist_ok=True)
                            (_wt_capture_dir / "generate_system_prompt.md").write_text(
                                _v2_system,
                                encoding="utf-8",
                            )
                            (_wt_capture_dir / "generate_user_prompt.md").write_text(
                                _v2_user,
                                encoding="utf-8",
                            )
                            (_wt_capture_dir / "prompt_diagnostics.json").write_text(
                                json.dumps(
                                    {
                                        "generate": {
                                            "kind": "design_generate",
                                            "iteration": 1,
                                            "prompt_chars": len(_v2_user),
                                            "system_prompt_chars": len(_v2_system),
                                            "prompt_tokens_estimate": len(_v2_user) // 4,
                                            "system_prompt_tokens_estimate": len(_v2_system) // 4,
                                            "max_tokens": _v2_max_tokens,
                                        }
                                    },
                                    indent=2,
                                    default=str,
                                ),
                                encoding="utf-8",
                            )
                            _v2_raw = "[walkthrough placeholder]"
                        else:
                            _v2_raw = self._run_v2_generate(
                                backend, _v2_user, _v2_system,
                                max_tokens=_v2_max_tokens,
                                timeout=self.config.development_timeout_seconds,
                            )
                        _v2_design = DesignDocument(
                            feature_name=task.title,
                            sections={},
                            raw_text=_v2_raw,
                            generated_at=datetime.datetime.now(
                                tz=datetime.timezone.utc,
                            ),
                            iteration=1,
                        )
                        _v2_design_phase = self._get_design_phase(
                            prompt_capture_dir=_wt_capture_dir,
                        )
                        _reviewer_verdict, _arbiter_verdict, _v2_disagreements = (
                            self._run_v2_reviews_async(
                                _v2_design_phase,
                                _v2_design,
                                timeout=self.config.development_timeout_seconds,
                            )
                        )
                        _v2_agreed = (
                            not _v2_disagreements
                            and _reviewer_verdict.approved
                            and _arbiter_verdict.approved
                        )
                        task_cost = backend.total_cost_usd - cost_before
                        total_cost += task_cost
                        serialized = {
                            "design_document": _v2_raw,
                            "feature_name": task.title,
                            "agreed": _v2_agreed,
                            "iterations": 1,
                            "completed_at": datetime.datetime.now(
                                tz=datetime.timezone.utc,
                            ).isoformat(),
                            "prompt_version": "v2",
                            "reviewer_verdict": self._serialize_review_verdict(
                                _reviewer_verdict
                            ),
                            "arbiter_verdict": self._serialize_review_verdict(
                                _arbiter_verdict
                            ),
                            "reviewer_summary": _reviewer_verdict.summary,
                            "arbiter_summary": _arbiter_verdict.summary,
                            "review_disagreement_count": len(_v2_disagreements),
                            "prompt_telemetry": {
                                "total_calls": 1,
                                "calls": [
                                    {
                                        "kind": "design_generate",
                                        "iteration": 1,
                                        "prompt_chars": len(_v2_user),
                                        "system_prompt_chars": len(_v2_system),
                                        "prompt_tokens_estimate": len(_v2_user) // 4,
                                        "system_prompt_tokens_estimate": len(_v2_system) // 4,
                                        "max_tokens": _v2_max_tokens,
                                    }
                                ],
                            },
                            "disagreement_telemetry": {
                                "review_pair_count": 1,
                                "re_review_pair_count": 0,
                                "re_review_rate": 0.0,
                                "disagreement_iteration_count": (
                                    1 if _v2_disagreements else 0
                                ),
                                "disagreement_count": len(_v2_disagreements),
                                "disagreement_categories": [
                                    (
                                        d.disagreement_type.value
                                        if hasattr(d, "disagreement_type")
                                        else str(
                                            (
                                                d.get("type")
                                                if isinstance(d, dict)
                                                else "unknown"
                                            )
                                        )
                                    )
                                    for d in _v2_disagreements
                                ],
                                "max_confidence_gap": abs(
                                    _reviewer_verdict.confidence
                                    - _arbiter_verdict.confidence
                                ),
                            },
                        }
                        if not _v2_agreed:
                            serialized["non_agreement_reason_code"] = (
                                "DISAGREEMENT_UNRESOLVED"
                                if _v2_disagreements
                                else "DUAL_REJECTION"
                            )
                        serialized["high_signal_floor_status"] = (
                            "degraded" if _high_signal_missing else "ok"
                        )
                        if _high_signal_missing:
                            serialized["high_signal_floor_missing"] = _high_signal_missing
                    else:
                        # ── V1: monolithic context + DesignDocumentationPhase ──
                        feature_context = self._task_to_feature_context(
                            task,
                            plan_goals=plan_goals,
                            architectural_context=arch_context,
                            prior_design_summaries=prior_summaries,
                            calibration=task_calibration,
                            design_max_tokens_override=self.config.design_max_tokens,
                            parameter_sources=context.get("parameter_sources", {}),
                            semantic_conventions=context.get("semantic_conventions", {}),
                            prior_design_text=prior_design_text,
                            prior_quality_feedback=(
                                carry_forward_quality_feedback or None
                            ),
                            inv_derivation_rules=inv_derivation_rules,
                            inv_resolved_parameters=inv_resolved_parameters,
                            inv_output_contracts=inv_output_contracts,
                            inv_refine_suggestions=inv_refine_suggestions,
                            inv_plan_document=inv_plan_document,
                            inv_calibration_hints=inv_calibration_hints,
                            inv_open_questions=context.get("onboarding_open_questions"),
                            inv_dependency_graph=context.get("onboarding_dependency_graph"),
                            scaffold_existing_files=context.get(
                                "scaffold", {},
                            ).get("existing_target_files", []),
                            # CCD-204: Lane-aware design context
                            lane_prior_designs=lane_prior_designs,
                            shared_file_manifest=shared_file_manifest,
                            wave_index=task.wave_index,
                            lane_peer_token_budget=self.config.design_lane_peer_token_budget,
                            task_title_lookup=_task_title_lookup,
                            bridge_context=_bridge_context if _bridge_context else None,
                            # Phase 5: Manifest context for DESIGN
                            manifest_registry=_design_manifest_registry,
                            manifest_context_budget=self.config.manifest_context_budget,
                            # Phase 6: Call graph budget for DESIGN
                            call_graph_context_budget=self.config.call_graph_context_budget,
                            # Phase 5: Introspect enrichment toggle for DESIGN
                            enable_introspect=self.config.enable_introspect,
                        )
                        _high_signal_missing = self._evaluate_high_signal_floor(
                            feature_context
                        )
                        if _high_signal_missing:
                            logger.warning(
                                "DESIGN task %s high-signal floor degraded (v1): %s",
                                task.task_id,
                                ", ".join(_high_signal_missing),
                            )
                        design_phase = self._get_design_phase(
                            prompt_capture_dir=_wt_capture_dir,
                        )
                        result = self._run_design_async(
                            design_phase, feature_context,
                            timeout=self.config.development_timeout_seconds,
                        )
                        task_cost = backend.total_cost_usd - cost_before
                        total_cost += task_cost
                        serialized = self._serialize_result(result)
                        serialized.setdefault("prompt_version", "v1")
                        serialized["high_signal_floor_status"] = (
                            "degraded" if _high_signal_missing else "ok"
                        )
                        if _high_signal_missing:
                            serialized["high_signal_floor_missing"] = _high_signal_missing

                    # ── Shared post-processing (both v1 and v2) ──
                    serialized["status"] = "refined" if prior_design_text else "designed"
                    serialized["cost"] = task_cost
                    serialized["prompt_version"] = selected_prompt_version
                    serialized["path_tag"] = self._path_tag_for_prompt_version(
                        selected_prompt_version
                    )
                    serialized["route_policy"] = route_policy
                    self._apply_design_quality_gates(
                        task=task,
                        entry=serialized,
                        resolved_parameters=task_resolved_parameters,
                        quality_policy_mode=quality_policy_mode,
                        dry_run=False,
                    )
                    design_results[task.task_id] = serialized

                    # PCA-605c: extract file decisions from design doc
                    _design_text = serialized.get("design_document", "")
                    if _design_text and task.target_files:
                        _discovered = _extract_design_target_files(
                            _design_text, task.target_files,
                        )
                        if _discovered != task.target_files:
                            design_results[task.task_id]["discovered_target_files"] = _discovered
                            logger.info(
                                "DESIGN→IMPLEMENT file propagation: task %s "
                                "target_files expanded %s → %s",
                                task.task_id,
                                task.target_files,
                                _discovered,
                            )

                    if serialized.get("status") == "design_failed":
                        tasks_failed += 1
                    elif prior_design_text:
                        tasks_refined += 1
                    else:
                        tasks_designed += 1
                    if serialized.get("agreed"):
                        tasks_agreed += 1
                    route_decision_counts[selected_prompt_version] += 1
                    task_quality_passed = self._task_quality_passed(serialized)
                    if task_quality_passed:
                        route_quality_counts[selected_prompt_version]["passed"] += 1
                        path_quality_counts[serialized["path_tag"]]["passed"] += 1
                        serialized["quality_outcome"] = "pass"
                    else:
                        route_quality_counts[selected_prompt_version]["failed"] += 1
                        path_quality_counts[serialized["path_tag"]]["failed"] += 1
                        serialized["quality_outcome"] = "fail"

                    # Accumulate cross-task summary for progressive context
                    doc_text = serialized["design_document"]
                    if serialized.get("status") != "design_failed":
                        first_line = doc_text[:300].split("\n")[0]
                        summary = f"{task.task_id} ({task.title}): {first_line}"
                        prior_summaries.append(summary)
                        # REQ-PD-007: Track completed designs for dependency injection
                        completed_designs[task.task_id] = summary
                        # CCD-200/205: Lane-peer design accumulation
                        lane_prior_designs.append({
                            "task_id": task.task_id,
                            "title": task.title,
                            "design_document": doc_text,
                        })
                    # CCD-401: Wave/lane metadata in design results
                    design_results[task.task_id].update(
                        _compute_ccd_task_metadata(
                            task, _lane_assignments, _design_lanes,
                            len(tasks), shared_file_manifest, _critical_task_ids,
                        )
                    )

                    # REQ-PD-012/014: Foundation coverage + provenance (v1 only —
                    # v2 modules track their own fragment-level coverage)
                    if selected_prompt_version == "v1" and feature_context is not None:
                        _foundation_field_keys = [
                            "plan_architecture", "plan_risks",
                            "plan_verification_strategy", "refine_suggestions",
                            "complexity_guidance", "api_signatures",
                            "transport_protocol", "dependency_designs",
                            "wave_context", "staleness_guidance",
                        ]
                        _fc_additional = feature_context.additional_context
                        _fc_count = sum(
                            1 for k in _foundation_field_keys if k in _fc_additional
                        )
                        # +1 for requirements_text
                        if feature_context.requirements_text:
                            _fc_count += 1
                        _foundation_coverage = _fc_count / 11.0
                        design_results[task.task_id]["foundation_coverage"] = _foundation_coverage
                        if _foundation_coverage < 0.3:
                            logger.warning(
                                "DESIGN: task %s foundation_coverage=%.1f%% (<30%%)",
                                task.task_id, _foundation_coverage * 100,
                            )
                        # REQ-PD-014: Foundation provenance
                        design_results[task.task_id]["foundation_provenance"] = {
                            "chain_status": context.get("_pi_design_chain_status", "unknown"),
                            "fields_consumed": [
                                k for k in _foundation_field_keys if k in _fc_additional
                            ] + (["requirements_text"] if feature_context.requirements_text else []),
                            "foundation_coverage": _foundation_coverage,
                            "source_checksum_status": context.get("_source_checksum_status", "unavailable"),
                            "complexity_composite": context.get("complexity_composite"),
                        }

                    # Write design doc to output_dir if configured
                    if self.output_dir:
                        out_path = Path(self.output_dir) / f"{task.task_id}-design.md"
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        out_path.write_text(doc_text, encoding="utf-8")
                        design_results[task.task_id]["output_file"] = str(out_path)
                        logger.info("Wrote design doc: %s", out_path)

                    _task_span.set_attribute("task.cost", task_cost)
                    _task_span.set_attribute("task.attempts", _attempt + 1)
                    _task_span.set_attribute(
                        "task.status",
                        str(serialized.get("status", "designed")),
                    )
                    _task_span.set_attribute("task.prompt_version", selected_prompt_version)
                    # CCD-601: lane-peer context injection attributes
                    # Compute truncation flag: same estimation as _apply_lane_peer_token_budget
                    _has_current_task_context = bool(
                        lane_prior_designs
                        and lane_prior_designs[-1].get("task_id") == task.task_id
                    )
                    if _has_current_task_context:
                        _peer_count = len(lane_prior_designs) - 1
                        _peers_before_this = lane_prior_designs[:-1]
                    else:
                        _peer_count = len(lane_prior_designs)
                        _peers_before_this = lane_prior_designs
                    _peer_chars = sum(len(d.get("design_document", "")) for d in _peers_before_this)
                    _was_truncated = (
                        _peer_chars // 4 > self.config.design_lane_peer_token_budget
                        if _peers_before_this and self.config.design_lane_peer_token_budget > 0
                        else False
                    )
                    _task_span.set_attribute(
                        "task.lane_prior_designs_count", _peer_count,
                    )
                    _task_span.set_attribute(
                        "task.lane_prior_designs_truncated", _was_truncated,
                    )
                    break  # success — exit retry loop

                except Exception as exc:
                    if (
                        _attempt < _max_attempts - 1
                        and _is_retryable_exception(exc, _design_retry_config)
                    ):
                        _delay = _calculate_delay(_attempt, _design_retry_config)
                        logger.warning(
                            "DESIGN: task %s failed (attempt %d/%d), retrying in %.1fs: %s",
                            task.task_id,
                            _attempt + 1,
                            _max_attempts,
                            _delay,
                            exc,
                        )
                        time.sleep(_delay)
                        continue

                    # Final attempt or non-retryable — fail as before
                    task_cost = backend.total_cost_usd - cost_before
                    total_cost += task_cost
                    tasks_failed += 1
                    logger.warning(
                        "DESIGN: failed for task %s: %s", task.task_id, exc
                    )
                    design_results[task.task_id] = {
                        "status": "design_failed",
                        "error": str(exc),
                        "cost": task_cost,
                        "prompt_version": selected_prompt_version,
                        "path_tag": self._path_tag_for_prompt_version(
                            selected_prompt_version
                        ),
                        "quality_outcome": "fail",
                    }
                    route_decision_counts[selected_prompt_version] += 1
                    route_quality_counts[selected_prompt_version]["failed"] += 1
                    path_quality_counts[design_results[task.task_id]["path_tag"]][
                        "failed"
                    ] += 1
                    break  # non-retryable or final attempt — exit retry loop

            # Capture span context before closing (E6 provenance linking)
            _sc = _capture_task_span_context(_task_span)
            if _sc and task.task_id in design_results:
                design_results[task.task_id]["_span_context"] = _sc
            _design_entry = design_results.get(task.task_id, {})
            _log_task_boundary_complete(
                task.task_id,
                status=str(_design_entry.get("status", "unknown")),
                phase="design",
                cost_usd=(
                    _coerce_optional_float(_design_entry.get("cost"))
                    if isinstance(_design_entry, dict)
                    else None
                ),
            )
            # Close the per-task span after the retry loop completes
            _task_span_cm.__exit__(None, None, None)

        # REQ-PD-015: Artifact inventory extension — aggregate foundation stats
        _tasks_with_foundation = sum(
            1 for r in design_results.values()
            if isinstance(r, dict) and r.get("foundation_coverage", 0) > 0
        )
        _tasks_without_foundation = sum(
            1 for r in design_results.values()
            if isinstance(r, dict) and r.get("foundation_coverage", 0) == 0
            and r.get("status") not in ("env_blocked", "dry_run_skipped", "design_failed")
        )
        _coverages = [
            r["foundation_coverage"]
            for r in design_results.values()
            if isinstance(r, dict) and "foundation_coverage" in r
        ]
        _mean_coverage = (
            sum(_coverages) / len(_coverages) if _coverages else 0.0
        )
        # Collect all consumed fields across tasks
        _all_fields: set[str] = set()
        for r in design_results.values():
            if isinstance(r, dict):
                prov = r.get("foundation_provenance", {})
                if isinstance(prov, dict):
                    _all_fields.update(prov.get("fields_consumed", []))

        _inventory_entry = {
            "phase": "design",
            "bridge": "plan_to_design",
            "tasks_with_foundation": _tasks_with_foundation,
            "tasks_without_foundation": _tasks_without_foundation,
            "mean_foundation_coverage": round(_mean_coverage, 3),
            "fields_consumed_summary": sorted(_all_fields),
            "chain_status": context.get("_pi_design_chain_status", "unknown"),
        }
        context.setdefault("_artifact_inventory", []).append(_inventory_entry)

        context["design_results"] = design_results
        # CCD-301: Persist shared-file manifest in context
        context["shared_file_manifest"] = shared_file_manifest
        # CCD-302: Lane-to-file mapping
        context["lane_to_file_mapping"] = lane_to_file_mapping

        # B-6: Derive design_mode_summary from filesystem ground truth
        # (scaffold.existing_target_files) instead of design iteration status.
        # Used by chain 5 (design_mode_to_implement) for verifiable propagation.
        _scaffold_data = context.get("scaffold", {})
        _scaffold_existing = set(
            _scaffold_data.get("existing_target_files", [])
        )
        _task_by_id = {t.task_id: t for t in tasks}

        # H-9: On DESIGN resume (auto-load from handoff.json), scaffold may
        # not be in context.  If scaffold data is absent, mode classification
        # cannot distinguish create vs update reliably — skip overwriting
        # design_mode_summary so any previously-computed values are preserved.
        if not _scaffold_data:
            logger.warning(
                "design_mode_summary: scaffold data missing from context — "
                "mode classification may be inaccurate (DESIGN resume?). "
                "Retaining existing design_mode_summary if present."
            )
            context.setdefault("design_mode_summary_degraded", True)
            context.setdefault("design_mode_summary", {})
        else:
            context["design_mode_summary"] = {}
            for tid, entry in design_results.items():
                if not isinstance(entry, dict) or entry.get("status") in (
                    "design_failed", "env_blocked", "dry_run_skipped",
                ):
                    context["design_mode_summary"][tid] = "skipped"
                elif _task_by_id.get(tid) and any(
                    f in _scaffold_existing
                    for f in _task_by_id[tid].target_files
                ):
                    context["design_mode_summary"][tid] = "update"
                elif _task_by_id.get(tid) and getattr(
                    _task_by_id[tid], "existing_content_hash", None
                ) is not None:
                    context["design_mode_summary"][tid] = "update"
                elif entry.get("status") == "refined":
                    context["design_mode_summary"][tid] = "update"
                else:
                    context["design_mode_summary"][tid] = "create"

        # ── Gaps 1-5: Handoff enrichment extraction ────────────────────
        _design_structural_delta: dict[str, dict[str, list[dict[str, str]]]] = {}
        _design_referenced_elements: dict[str, dict[str, list[str]]] = {}
        _manifest_file_checksums: dict[str, str] = {}
        _design_mode_evidence: dict[str, dict[str, Any]] = {}
        _manifest_truncation_tier: dict[str, str] = {}

        _project_root = context.get("project_root", "")

        # Build manifest element index for cross-validation (Gap 1)
        _manifest_elements: dict[str, list[str]] = {}
        if _design_manifest_registry is not None:
            try:
                for _task in tasks:
                    for _tf in _task.target_files:
                        if _tf not in _manifest_elements:
                            _summary = _design_manifest_registry.file_element_summary(
                                _tf, 500,
                            )
                            if _summary:
                                # Extract element names from summary lines
                                _elems: list[str] = []
                                for _sl in _summary.splitlines():
                                    _sl = _sl.strip()
                                    # Lines like "  ClassName(Base)" or "  func_name(x, y)"
                                    _em = re.match(r'^(\w[\w.]*)', _sl)
                                    if _em and _em.group(1) not in (
                                        "Classes", "Functions", "Imports", "Lines",
                                    ):
                                        _elems.append(_em.group(1))
                                _manifest_elements[_tf] = _elems
            except (AttributeError, TypeError, ValueError) as exc:
                logger.warning(
                    "DESIGN: manifest element index build failed: %s", exc,
                    exc_info=True,
                )

        for tid, entry in design_results.items():
            if not isinstance(entry, dict):
                continue
            doc_text = entry.get("design_document", "")
            if not doc_text or entry.get("status") in (
                "design_failed", "env_blocked", "dry_run_skipped",
            ):
                continue

            # Gap 3: Structural delta from ### Files Touched section
            try:
                delta = _extract_structural_delta(doc_text)
                if delta:
                    _design_structural_delta[tid] = delta
            except (re.error, ValueError, KeyError) as exc:
                logger.debug("DESIGN Gap 3: delta extraction failed for %s: %s", tid, exc)

            # Gap 1: Referenced elements cross-validated against manifest
            _task_manifest_elems = {}
            _task_obj = _task_by_id.get(tid)
            if _task_obj:
                for _tf in _task_obj.target_files:
                    if _tf in _manifest_elements:
                        _task_manifest_elems[_tf] = _manifest_elements[_tf]
            try:
                refs = _extract_referenced_elements(doc_text, _task_manifest_elems)
                if refs:
                    _design_referenced_elements[tid] = refs
            except (re.error, ValueError, KeyError) as exc:
                logger.debug("DESIGN Gap 1: element extraction failed for %s: %s", tid, exc)

            # Gap 4: Design mode evidence — collect signals that informed the mode
            mode = context["design_mode_summary"].get(tid, "create")
            evidence: list[str] = []
            if _task_obj:
                if any(f in _scaffold_existing for f in _task_obj.target_files):
                    evidence.append("scaffold.existing_target_files")
                if getattr(_task_obj, "existing_content_hash", None) is not None:
                    evidence.append("existing_content_hash")
            if entry.get("status") == "refined":
                evidence.append("design_status=refined")
            # Check design doc for edit signals
            doc_lower = doc_text.lower()
            if "(modify)" in doc_lower or "(update)" in doc_lower:
                evidence.append("design_doc_modify_annotation")
            if "(create)" in doc_lower or "(new)" in doc_lower:
                evidence.append("design_doc_create_annotation")
            _design_mode_evidence[tid] = {
                "mode": mode,
                "evidence": evidence,
                "reasoning": (
                    f"{len(evidence)} signal(s): {', '.join(evidence)}"
                    if evidence else "no upstream signals"
                ),
            }

        # Gap 2: Manifest file checksums for all target files at design time
        _all_target_files = list(dict.fromkeys(
            f for _task in tasks for f in _task.target_files
        ))
        _manifest_file_checksums = _compute_manifest_file_checksums(
            _all_target_files, _project_root,
        )

        # Gap 5: Record manifest truncation tier per file
        # Threshold fractions for classifying truncation fidelity
        _TIER_FULL_THRESHOLD = 0.95
        _TIER_COMPACT_THRESHOLD = 0.50
        if _design_manifest_registry is not None:
            # Ensure the "full" probe budget always exceeds the design budget
            _full_probe_budget = max(10_000, self.config.manifest_context_budget * 5)
            for _tf in _all_target_files:
                try:
                    full_summary = _design_manifest_registry.file_element_summary(
                        _tf, _full_probe_budget,
                    )
                    if not full_summary:
                        _manifest_truncation_tier[_tf] = "unavailable"
                        continue
                    budget_summary = _design_manifest_registry.file_element_summary(
                        _tf, self.config.manifest_context_budget,
                    )
                    if budget_summary and len(budget_summary) >= len(full_summary) * _TIER_FULL_THRESHOLD:
                        _manifest_truncation_tier[_tf] = "full"
                    elif budget_summary and len(budget_summary) >= len(full_summary) * _TIER_COMPACT_THRESHOLD:
                        _manifest_truncation_tier[_tf] = "compact"
                    elif budget_summary:
                        _manifest_truncation_tier[_tf] = "public_only"
                    else:
                        _manifest_truncation_tier[_tf] = "fqn_only"
                except (AttributeError, TypeError, ValueError):
                    _manifest_truncation_tier[_tf] = "unavailable"

        # Persist enrichment data in context for downstream consumption
        context["design_structural_delta"] = _design_structural_delta
        context["design_referenced_elements"] = _design_referenced_elements
        context["manifest_file_checksums"] = _manifest_file_checksums
        context["design_mode_evidence"] = _design_mode_evidence
        context["manifest_truncation_tier"] = _manifest_truncation_tier

        logger.info(
            "DESIGN enrichment: delta=%d, refs=%d, checksums=%d, "
            "evidence=%d, truncation=%d (of %d tasks)",
            len(_design_structural_delta),
            len(_design_referenced_elements),
            len(_manifest_file_checksums),
            len(_design_mode_evidence),
            len(_manifest_truncation_tier),
            len(design_results),
        )

        # CCD-500: Post-lane compatibility check
        _lane_conflicts: list[dict[str, Any]] = []
        if _design_lanes is not None and shared_file_manifest:
            try:
                from startd8.contractors.design_collision import (
                    CollisionSeverity,
                    check_lane_collisions,
                )
                for _li, _lane_tasks in enumerate(_design_lanes):
                    _lc = check_lane_collisions(
                        lane_index=_li,
                        lane_tasks=_lane_tasks,
                        design_results=design_results,
                        shared_file_manifest=shared_file_manifest,
                        design_mode_summary=context["design_mode_summary"],
                    )
                    _lane_conflicts.append(_lc.to_dict())

                # CCD-503: Apply collision resolution strategy
                _conflicting_lanes = [
                    lc for lc in _lane_conflicts
                    if lc.get("status") == "CONFLICTING"
                ]
                if _conflicting_lanes:
                    _strategy = self.config.design_collision_strategy
                    if _strategy == "warn":
                        logger.warning(
                            "DESIGN CCD-503 [warn]: %d lane(s) have CONFLICTING designs",
                            len(_conflicting_lanes),
                        )
                    elif _strategy == "abort":
                        logger.error(
                            "DESIGN CCD-503 [abort]: marking %d conflicting lane(s) "
                            "as design_failed",
                            len(_conflicting_lanes),
                        )
                        for _clc in _conflicting_lanes:
                            for _tid in _clc.get("task_ids", []):
                                design_results[_tid] = {
                                    **design_results.get(_tid, {}),
                                    "status": "design_failed",
                                    "error": (
                                        f"CCD-503 abort: design collision in lane "
                                        f"{_clc['lane_index']}"
                                    ),
                                }
            except ImportError:
                logger.debug("DESIGN: design_collision module not available — skipping")
        context["lane_conflicts"] = _lane_conflicts

        # Context contract validation runs after aggregate quality metrics
        # are computed and attached to context.

        # Persist design results for auto-adoption on re-run
        if design_results and not dry_run and self.output_dir:
            from startd8.contractors.handoff import write_design_handoff
            try:
                handoff_path = write_design_handoff(
                    output_dir=self.output_dir,
                    enriched_seed_path=context.get("enriched_seed_path", ""),
                    project_root=context.get("project_root", ""),
                    workflow_id=context.get("workflow_id", "unknown"),
                    completed_phases=["design"],
                    design_results=design_results,
                    scaffold=context.get("scaffold", {}),
                    source_checksum=context.get("source_checksum"),
                    design_mode_summary=context.get("design_mode_summary", {}),
                    shared_file_manifest=shared_file_manifest,
                    design_structural_delta=_design_structural_delta,
                    design_referenced_elements=_design_referenced_elements,
                    manifest_file_checksums=_manifest_file_checksums,
                    design_mode_evidence=_design_mode_evidence,
                    manifest_truncation_tier=_manifest_truncation_tier,
                    design_quality=context.get("design_quality"),
                )
                logger.info("DESIGN: wrote handoff for auto-adoption: %s", handoff_path)
            except (OSError, ValueError, TypeError) as exc:
                logger.warning("DESIGN: failed to write handoff: %s", exc, exc_info=True)

        env_blocked = sum(
            1 for r in design_results.values()
            if r.get("status") == "env_blocked"
        )
        # REQ-PAQ-400: deterministic DESIGN quality metrics for gate policy.
        quality_per_task: dict[str, dict[str, Any]] = {}
        quality_failed = 0
        quality_passed = 0
        for tid, entry in design_results.items():
            status = entry.get("status", "")
            if status in ("dry_run_skipped", "env_blocked"):
                continue
            passed = self._task_quality_passed(entry)
            reason = self._task_quality_reason(entry)
            if passed:
                quality_passed += 1
            else:
                quality_failed += 1
            quality_per_task[tid] = {
                "passed": passed,
                "status": status,
                "reason": reason,
                "prompt_version": entry.get("prompt_version", "n/a"),
                "path_tag": entry.get("path_tag", "unknown"),
                "quality_outcome": "pass" if passed else "fail",
                "review_gate": entry.get("review_gate"),
                "parameter_completeness": entry.get("parameter_completeness"),
            }
        quality_total = quality_passed + quality_failed
        agreement_rate = (
            quality_passed / quality_total if quality_total > 0 else 0.0
        )
        design_quality = {
            "total_passed": quality_passed,
            "total_failed": quality_failed,
            "agreement_rate": agreement_rate,
            "evaluated_task_count": quality_total,
        }
        context["design_quality"] = design_quality

        prompt_calls_total = 0
        prompt_chars_total = 0
        prompt_system_chars_total = 0
        prompt_tasks_with_telemetry = 0
        prompt_dropped_field_total = 0
        prompt_truncation_event_count = 0
        disagreement_count_total = 0
        disagreement_pair_total = 0
        re_review_pair_total = 0
        resolution_action_summary: dict[str, int] = defaultdict(int)
        resolution_outcome_summary: dict[str, int] = defaultdict(int)
        for entry in design_results.values():
            if not isinstance(entry, dict):
                continue
            prompt_info = entry.get("prompt_telemetry")
            if isinstance(prompt_info, dict):
                prompt_tasks_with_telemetry += 1
                prompt_calls_total += int(prompt_info.get("total_calls", 0) or 0)
                prompt_chars_total += int(prompt_info.get("total_prompt_chars", 0) or 0)
                prompt_system_chars_total += int(
                    prompt_info.get("total_system_prompt_chars", 0) or 0
                )
                for call in prompt_info.get("calls", []):
                    if not isinstance(call, dict):
                        continue
                    ctx_budget = call.get("context_budget")
                    if not isinstance(ctx_budget, dict):
                        continue
                    dropped = int(ctx_budget.get("dropped_field_count", 0) or 0)
                    prompt_dropped_field_total += dropped
                    if ctx_budget.get("compression_steps"):
                        prompt_truncation_event_count += 1
            disagreement_info = entry.get("disagreement_telemetry")
            if isinstance(disagreement_info, dict):
                disagreement_count_total += int(
                    disagreement_info.get("disagreement_count", 0) or 0
                )
                disagreement_pair_total += int(
                    disagreement_info.get("review_pair_count", 0) or 0
                )
                re_review_pair_total += int(
                    disagreement_info.get("re_review_pair_count", 0) or 0
                )
            resolution_info = entry.get("resolution_audit")
            if isinstance(resolution_info, dict):
                for action, count in (resolution_info.get("resolution_action_counts", {}) or {}).items():
                    resolution_action_summary[action] += int(count or 0)
                for event in resolution_info.get("events", []) or []:
                    if not isinstance(event, dict):
                        continue
                    outcome = event.get("outcome")
                    if outcome:
                        resolution_outcome_summary[str(outcome)] += 1

        prompt_telemetry_summary = {
            "tasks_with_telemetry": prompt_tasks_with_telemetry,
            "prompt_calls_total": prompt_calls_total,
            "prompt_chars_total": prompt_chars_total,
            "system_prompt_chars_total": prompt_system_chars_total,
            "dropped_field_total": prompt_dropped_field_total,
            "truncation_event_count": prompt_truncation_event_count,
        }
        disagreement_summary = {
            "disagreement_count_total": disagreement_count_total,
            "review_pair_total": disagreement_pair_total,
            "re_review_pair_total": re_review_pair_total,
            "re_review_rate": (
                re_review_pair_total / disagreement_pair_total
                if disagreement_pair_total > 0
                else 0.0
            ),
            "resolution_action_counts": dict(resolution_action_summary),
            "resolution_outcome_counts": dict(resolution_outcome_summary),
        }
        route_quality_summary = {
            route: {
                "passed": counts["passed"],
                "failed": counts["failed"],
                "agreement_rate": (
                    counts["passed"] / (counts["passed"] + counts["failed"])
                    if (counts["passed"] + counts["failed"]) > 0
                    else 0.0
                ),
            }
            for route, counts in route_quality_counts.items()
        }
        path_quality_summary = {
            path_tag: {
                "passed": counts["passed"],
                "failed": counts["failed"],
                "agreement_rate": (
                    counts["passed"] / (counts["passed"] + counts["failed"])
                    if (counts["passed"] + counts["failed"]) > 0
                    else 0.0
                ),
            }
            for path_tag, counts in path_quality_counts.items()
        }
        canonical_stats = path_quality_summary.get(
            "canonical", {"passed": 0, "failed": 0, "agreement_rate": 0.0}
        )
        variant_stats = path_quality_summary.get(
            "variant", {"passed": 0, "failed": 0, "agreement_rate": 0.0}
        )
        path_comparison = {
            "canonical": canonical_stats,
            "variant": variant_stats,
            "agreement_rate_delta_canonical_minus_variant": (
                canonical_stats["agreement_rate"] - variant_stats["agreement_rate"]
            ),
        }
        context["design_path_quality"] = path_quality_summary
        context["design_path_comparison"] = path_comparison
        output: dict[str, Any] = {
            "tasks_designed": tasks_designed,
            "tasks_refined": tasks_refined,
            "tasks_adopted": tasks_adopted,
            "tasks_agreed": tasks_agreed,
            "tasks_failed": tasks_failed,
            "tasks_skipped": len(tasks) - tasks_designed - tasks_refined - tasks_adopted - tasks_failed - env_blocked,
            "total_passed": quality_passed,
            "total_failed": quality_failed,
            "agreement_rate": agreement_rate,
            "per_task": quality_per_task,
            "design_quality": design_quality,
            "route_decisions": dict(route_decision_counts),
            "route_quality": route_quality_summary,
            "path_quality": path_quality_summary,
            "path_comparison": path_comparison,
            "prompt_telemetry": prompt_telemetry_summary,
            "disagreement_summary": disagreement_summary,
            "total_cost": total_cost,
        }
        if self.output_dir:
            output["output_dir"] = self.output_dir

        # Context contract: validate DESIGN output model with quality payload.
        DesignPhaseOutput(
            design_results=context["design_results"],
            design_quality=context["design_quality"],
        )

        duration = time.monotonic() - start
        logger.info(
            "DESIGN phase complete: %d designed, %d refined, %d adopted, %d agreed, %d failed, $%.4f cost (%.2fs)",
            tasks_designed, tasks_refined, tasks_adopted, tasks_agreed, tasks_failed, total_cost, duration,
        )

        return {"output": output, "cost": total_cost, "metadata": {"duration": duration}}


# ============================================================================
# Complexity-Driven Model Router (CMR) — REQ-CMR-010, REQ-CMR-011
# ============================================================================


def _detect_cross_file_edges(
    target_files: list[str],
    manifest_registry: Any,
    flatten_fn: Any,
) -> bool:
    """Check whether any target files have call edges to each other (C1 extract).

    Args:
        target_files: List of relative file paths (must have len > 1).
        manifest_registry: ManifestRegistry with call_graph() method.
        flatten_fn: The ``_flatten_elements`` helper from manifest_registry.

    Returns:
        ``True`` if any element in one target file calls an element in another.
    """
    try:
        forward = manifest_registry.call_graph()
        fqn_to_file: dict[str, str] = {}
        for tf in target_files:
            m = manifest_registry.get(tf)
            if m:
                for e in flatten_fn(m.elements):
                    if e.fqn:
                        fqn_to_file[e.fqn] = tf
        for fqn, file_path in fqn_to_file.items():
            for callee in forward.get(fqn, set()):
                callee_file = fqn_to_file.get(callee)
                if callee_file and callee_file != file_path:
                    return True
    except (AttributeError, TypeError, KeyError) as exc:
        logger.debug("CMR: cross-file edge detection failed: %s", exc)
    return False


def _extract_complexity_signals(
    chunk: Any,
    manifest_registry: Any,
) -> "TaskComplexitySignals":
    """Extract complexity signals from chunk metadata and manifest registry.

    Reads from existing enrichment data (``_call_graph_callers``,
    ``_edit_mode``, ``estimated_loc``) and queries the registry for
    ``has_dynamic_dispatch``, ``is_closure``, ``unresolved_calls``,
    ``mro_depth``.

    Args:
        chunk: A ``DevelopmentChunk``-like object with ``metadata`` dict
            and ``file_targets`` list.
        manifest_registry: A ``ManifestRegistry`` instance, or ``None``
            when manifest data is unavailable.

    Returns:
        A ``TaskComplexitySignals`` with all fields populated from available
        data, falling back to safe defaults on any extraction failure.

    Never raises — all lookups wrapped in try/except (REQ-CMR-010).
    """
    from startd8.contractors.artisan_phases.development import TaskComplexitySignals

    meta = getattr(chunk, "metadata", {}) or {}
    _chunk_id = getattr(chunk, "chunk_id", "?")

    # --- Signals from chunk metadata (populated by earlier enrichment) ---
    blast_radius = 0
    caller_count = 0
    has_cross_file_edges = False
    manifest_coverage = "none"
    cg_callers = []

    try:
        cg_callers = meta.get("_call_graph_callers", [])
        if cg_callers:
            blast_radius = max(
                (entry.get("blast_radius", 0) for entry in cg_callers),
                default=0,
            )
            caller_count = sum(
                len(entry.get("direct_callers", []))
                for entry in cg_callers
            )
    except (TypeError, AttributeError) as exc:
        logger.debug("CMR: call graph caller extraction failed for %s: %s", _chunk_id, exc)

    # Edit mode from classification (normalized at extraction boundary)
    edit_mode = "unknown"
    try:
        edit_mode_dict = meta.get("_edit_mode")
        if edit_mode_dict and isinstance(edit_mode_dict, dict):
            edit_mode = str(edit_mode_dict.get("mode", "unknown")).strip().lower()
        elif isinstance(edit_mode_dict, str):
            edit_mode = edit_mode_dict.strip().lower()
    except (TypeError, AttributeError) as exc:
        logger.debug("CMR: edit mode extraction failed for %s: %s", _chunk_id, exc)

    # Estimated LOC from seed task
    estimated_loc = 0
    try:
        estimated_loc = int(meta.get("estimated_loc", 0) or 0)
    except (ValueError, TypeError):
        logger.debug("estimated_loc coercion failed", exc_info=True)

    # Target file count
    target_files = getattr(chunk, "file_targets", []) or []
    target_file_count = max(len(target_files), 1)

    # --- Signals from manifest registry (Phase 5/6 data) ---
    has_dynamic_dispatch = False
    is_closure = False
    mro_depth = 0
    unresolved_call_count = 0

    manifests_found = 0
    if manifest_registry is not None:
        # Single import of _flatten_elements for reuse (R1)
        try:
            from startd8.utils.manifest_registry import _flatten_elements
        except ImportError:
            logger.debug("CMR: manifest_registry import failed for %s", _chunk_id)
            _flatten_elements = None  # type: ignore[assignment]

        if _flatten_elements is not None:
            try:
                for tf in target_files:
                    manifest = manifest_registry.get(tf)
                    if manifest is None:
                        continue
                    manifests_found += 1
                    try:
                        elements = _flatten_elements(manifest.elements)
                    except (TypeError, AttributeError) as exc:
                        logger.debug("CMR: element flattening failed for %s in %s: %s", tf, _chunk_id, exc)
                        continue

                    for elem in elements:
                        # Dynamic dispatch + unresolved call detection
                        try:
                            cg = getattr(elem, "call_graph", None)
                            if cg is not None:
                                for call in getattr(cg, "calls", []):
                                    if getattr(call, "is_dynamic", False):
                                        has_dynamic_dispatch = True
                                        break
                                unresolved_call_count += sum(
                                    1 for c in getattr(cg, "calls", [])
                                    if getattr(c, "target_fqn", None) is None
                                )
                        except (TypeError, AttributeError) as exc:
                            logger.debug("CMR: call graph inspection failed for element in %s: %s", _chunk_id, exc)

                        # Closure detection
                        if getattr(elem, "is_closure", False):
                            is_closure = True

                        # MRO depth (Phase 5)
                        try:
                            inspect_info = getattr(elem, "inspect_info", None)
                            if inspect_info is not None:
                                depth = getattr(inspect_info, "mro_depth", 0) or 0
                                mro_depth = max(mro_depth, depth)
                        except (TypeError, AttributeError) as exc:
                            logger.debug("CMR: MRO depth extraction failed for element in %s: %s", _chunk_id, exc)

                # Cross-file call edges (C1: extracted helper)
                if len(target_files) > 1:
                    has_cross_file_edges = _detect_cross_file_edges(
                        target_files, manifest_registry, _flatten_elements,
                    )
            except Exception:
                logger.debug("CMR: manifest signal extraction failed for %s", _chunk_id, exc_info=True)

    # Simplified confidence signal: binary manifest coverage.
    manifest_coverage = (
        "full"
        if manifest_registry is not None
        and target_files
        and manifests_found == len(target_files)
        else "none"
    )

    return TaskComplexitySignals(
        blast_radius=blast_radius,
        caller_count=caller_count,
        has_dynamic_dispatch=has_dynamic_dispatch,
        is_closure=is_closure,
        estimated_loc=estimated_loc,
        target_file_count=target_file_count,
        edit_mode=edit_mode,
        mro_depth=mro_depth,
        unresolved_call_count=unresolved_call_count,
        has_cross_file_edges=has_cross_file_edges,
        manifest_coverage=manifest_coverage,
    )


def _classify_complexity_tier(
    signals: "TaskComplexitySignals",
    config: "HandlerConfig",
) -> "TaskComplexityTier":
    """Classify a task into a complexity tier (REQ-CMR-011).

    Pure function, stateless, deterministic. Evaluation order:
    1. Tier 3 triggers (any one triggers)
    2. Tier 1 eligibility (all must pass)
    3. Default: Tier 2

    Args:
        signals: Complexity signals extracted from chunk metadata and
            manifest registry.
        config: Handler configuration with tier threshold fields.

    Returns:
        The classified ``TaskComplexityTier``.
    """
    from startd8.contractors.artisan_phases.development import TaskComplexityTier

    # --- Tier 3: any trigger fires ---
    if signals.blast_radius > config.complexity_blast_radius_tier3:
        return TaskComplexityTier.TIER_3
    if signals.has_dynamic_dispatch:
        return TaskComplexityTier.TIER_3
    if (
        signals.edit_mode == "edit"
        and signals.caller_count > config.complexity_caller_tier3
    ):
        return TaskComplexityTier.TIER_3
    if signals.mro_depth > 3:
        return TaskComplexityTier.TIER_3
    if signals.unresolved_call_count > 2:
        return TaskComplexityTier.TIER_3
    if signals.estimated_loc > config.complexity_loc_tier3_min:
        return TaskComplexityTier.TIER_3
    if signals.target_file_count > 1 and signals.has_cross_file_edges:
        return TaskComplexityTier.TIER_3

    # --- Tier 1: all must pass ---
    if (
        signals.manifest_coverage == "full"
        and signals.blast_radius == 0
        and signals.edit_mode == "create"
        and signals.caller_count == 0
        and not signals.has_dynamic_dispatch
        and signals.estimated_loc < config.complexity_loc_tier1_max
        and signals.target_file_count == 1
    ):
        return TaskComplexityTier.TIER_1

    # --- Default: Tier 2 ---
    return TaskComplexityTier.TIER_2


def _set_default_complexity_metadata(
    chunk: Any,
    *,
    force: bool,
) -> None:
    """Set Tier 2 fallback metadata in one place."""
    from startd8.contractors.artisan_phases.development import (
        TaskComplexitySignals,
        TaskComplexityTier,
    )

    if force:
        chunk.metadata["_complexity_tier"] = TaskComplexityTier.TIER_2.value
        chunk.metadata["_complexity_signals"] = TaskComplexitySignals().to_dict()
        return

    chunk.metadata.setdefault("_complexity_tier", TaskComplexityTier.TIER_2.value)
    chunk.metadata.setdefault("_complexity_signals", TaskComplexitySignals().to_dict())


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
            if has_hash:
                edit_weight += 2
                file_signals_edit.append("existing_content_hash")

            # Tier 1 (weight 2): scaffold.existing_target_files
            in_existing = fpath in existing_targets
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
                    or task_design.get("non_agreement_reason_code")
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
                if not design_doc_text or _design_lines < 50:
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
                            "Inner loop task %s: DESIGN failed — proceeding "
                            "per %s policy (quality may be degraded)",
                            task_id, _gate_mode,
                        )

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

                        # Restore truncation_flags from cache (v3+; graceful for v2)
                        truncation_flags = saved.get("truncation_flags", {})

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
                files = list((gen_result.files or {}).keys())[:5] if hasattr(gen_result, "files") and gen_result.files else []
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

        # Integrate each task
        integration_results: dict[str, dict[str, Any]] = {}
        for task_id, gr in generation_results.items():
            if not gr.success:
                continue
            task = task_map.get(task_id)
            if not task:
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
            expected = {str(f) for f in gr.generated_files}

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
        total = len(integration_results)

        logger.info(
            "INTEGRATE phase complete: %d/%d tasks merged (%.2fs)",
            passed, total, duration,
        )

        return {
            "output": integration_results,
            "cost": 0.0,  # no LLM cost — only subprocess validation
            "metadata": {"duration": duration, "passed": passed, "total": total},
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
                })
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
            except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError, UnicodeDecodeError, Exception) as exc:
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
                task_test_result["status"] = (
                    "passed" if task_test_result["all_passed"] else "failed"
                )
                test_plan.append(task_test_result)

                if task_test_result["all_passed"]:
                    total_passed += 1
                    _task_span.set_attribute("task.status", "passed")
                    task_status = "passed"
                else:
                    total_failed += 1
                    _task_span.set_attribute("task.status", "failed")
                    task_status = "failed"
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
        output = {
            "test_plan": test_plan,
            "total_validators": sum(len(t.post_generation_validators) for t in tasks),
            "unique_validators": dict(validator_counts),
            "tasks_with_tests": len([t for t in test_plan if t.get("validator_count", 0) > 0 or t.get("validators_run", 0) > 0]),
            "total_passed": total_passed,
            "total_failed": total_failed,
            "total_skipped": total_skipped,
            "per_task": per_task,
        }

        context["test_results"] = output

        # Context contract: validate TEST output model.
        # Wrap in try-except so Pydantic validation failures respect the
        # quality gate policy (block vs warn) instead of crashing the phase.
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
        named_sections: list[tuple[str, str]] = []
        for text in self._build_project_context_section(project_context):
            named_sections.append(("project_context", text))
        for text in self._build_design_compliance_section(design_document):
            named_sections.append(("design_compliance", text))
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
        for text in self._build_forward_contract_violations_section(forward_contract_violations):
            named_sections.append(("forward_contract_violations", text))

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

        # Extract score
        score_match = re.search(r"###\s*Score:\s*(\d+)", response)
        if score_match:
            score = min(100, max(0, int(score_match.group(1))))
        else:
            # Fallback: try without markdown headers
            score_fallback = re.search(r"(?:^|\n)\s*Score\s*[:=]\s*(\d+)", response, re.IGNORECASE)
            if score_fallback:
                score = min(100, max(0, int(score_fallback.group(1))))
            else:
                logger.warning(
                    "REVIEW: could not extract score from response (score=None); "
                    "first 200 chars: %s", response[:200],
                )

        # Extract verdict
        verdict_match = re.search(r"###\s*Verdict:\s*(PASS|FAIL)", response, re.IGNORECASE)
        if verdict_match:
            verdict = verdict_match.group(1).upper()
        else:
            # Fallback: try without markdown headers
            verdict_fallback = re.search(r"(?:^|\n)\s*Verdict\s*[:=]\s*(PASS|FAIL)", response, re.IGNORECASE)
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
                    review = {**cached, "review_status": "cached"}
                    review["title"] = task.title
                    review["domain"] = task.domain
                    review["constraint_count"] = len(task.prompt_constraints)
                    review["env_failures"] = len(env_fails)
                    review["env_warnings"] = len(env_warns)
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
                _pre_fm_violations: list[Any] = []
                if self.config.manifest_consumption_enabled:
                    _registry = self.config.manifest_registry
                    _fwd_manifest = context.get("forward_manifest")
                    if _registry is not None and _fwd_manifest is not None:
                        try:
                            from startd8.forward_manifest_validator import validate_forward_manifest
                            _pre_fm_violations = validate_forward_manifest(_fwd_manifest, _registry) or []
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

                # Phase 5: Run ForwardManifest Validator if applicable
                if self.config.manifest_consumption_enabled:
                    registry = self.config.manifest_registry
                    forward_manifest = context.get("forward_manifest")
                    if registry is not None and forward_manifest is not None:
                        from startd8.forward_manifest_validator import validate_forward_manifest
                        
                        try:
                            fm_violations = validate_forward_manifest(forward_manifest, registry)
                            
                            error_violations = [v for v in fm_violations if v.severity == "error"]
                            warning_violations = [v for v in fm_violations if v.severity == "warning"]
                            
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
                                
                        except Exception as val_error:
                            logger.error(
                                "REVIEW: ForwardManifest validation engine failed for %s: %s", 
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
                per_task[task_id] = {
                    "status": status,
                    "passed": item.get("passed") if status in ("reviewed", "cached") else None,
                    "score": item.get("score"),
                    "verdict": item.get("verdict"),
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
        # Wrap in try-except so Pydantic validation failures respect the
        # quality gate policy (block vs warn) instead of crashing the phase.
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
                        serializable_tasks[tid] = {
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

        for task_id, result in generation_results.items():
            if result.success:
                task = id_to_task.get(task_id)
                for fpath in result.generated_files:
                    artifact: dict[str, Any] = {
                        "task_id": task_id,
                        "path": str(fpath),
                        "exists": (
                            fpath.exists() if hasattr(fpath, "exists") else False
                        ),
                        "domain": task.domain if task else "unknown",
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

        if generated_fail == 0 and generated_ok == total_tasks:
            if tests_failed > 0 or reviews_failed > 0:
                overall_status = "quality_failed"
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
        FinalizePhaseOutput(workflow_summary=context["workflow_summary"])

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
        force_canonical_design_route: Optional[bool] = None,
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
            force_canonical_design_route: Force canonical DESIGN path (v1) for all tasks.
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
            ("force_canonical_design_route", force_canonical_design_route),
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

        return {
            WorkflowPhase.PLAN: PlanPhaseHandler(enriched_seed_path),
            WorkflowPhase.SCAFFOLD: ScaffoldPhaseHandler(),
            WorkflowPhase.DESIGN: DesignPhaseHandler(
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
