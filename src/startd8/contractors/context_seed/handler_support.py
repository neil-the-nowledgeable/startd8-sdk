"""Leaf support module for context_seed phase handlers.

Holds the shared config/mode dataclasses, integration listeners, telemetry /
hash / provenance helpers, and the review-template loaders that the phase
handlers consume. Extracted from ``core.py`` (Step 0a of the phases/ extraction)
to break the dependency inversion: this module imports only external deps +
``shared`` + ``tracing`` — NEVER ``core`` — so ``phases/*`` can depend on it
without a cycle. See docs/design/context-seed-refactor/.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Optional

from startd8.contractors.protocols import (
    CodeGenerator,
    DRAFT_MODEL_CLAUDE_HAIKU,
    GenerationResult,
    REVIEW_MODEL_CLAUDE_OPUS,
    VALIDATE_MODEL_CLAUDE_SONNET,
)
from startd8.contractors.context_seed.shared import SeedTask
from startd8.contractors.context_seed.tracing import _HAS_OTEL
from startd8.logging_config import get_logger

logger = get_logger("startd8.contractors.context_seed_handlers")


_CACHE_SCHEMA_VERSION = 3


_MAX_GEN_FILE_HASH_BYTES = 50 * 1024 * 1024


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

