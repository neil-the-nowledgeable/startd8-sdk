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
from startd8.contractors.context_seed.phases.finalize import FinalizePhaseHandler  # noqa: F401
from startd8.contractors.context_seed.phases.integrate import IntegratePhaseHandler  # noqa: F401
from startd8.contractors.context_seed.phases.test_phase import TestPhaseHandler  # noqa: F401
from startd8.contractors.context_seed.phases.review import ReviewPhaseHandler  # noqa: F401
from startd8.contractors.context_seed.phases.implement import ImplementPhaseHandler  # noqa: F401
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

# --- Step 0a: shared substrate moved to handler_support.py (leaf). core re-imports
# them so still-in-core handlers + the compat wrapper keep resolving. Removed when
# core becomes the pure aggregator (final step).
from startd8.contractors.context_seed.handler_support import (  # noqa: F401
    ArtisanIntegrationListener,
    EditModeClassification,
    HandlerConfig,
    OTelIntegrationListener,
    PerFileMode,
    SeedTaskUnit,
    _CACHE_SCHEMA_VERSION,
    _MAX_GEN_FILE_HASH_BYTES,
    _PHASE_RESULT_KEYS,
    _SIZE_REGRESSION_MIN_LINES,
    _SIZE_REGRESSION_THRESHOLD,
    _build_provenance_links,
    _capture_task_span_context,
    _coerce_optional_float,
    _compute_design_results_hash,
    _compute_gen_file_hash,
    _dict_to_gen_result,
    _format_review_prompt,
    _get_review_template,
    _log_task_boundary_complete,
    _log_task_boundary_start,
    _log_task_timing,
)

# Maximum file size for hash computation (50 MB).  Files larger than this
# are skipped to prevent memory spikes during cache validation.

# PCA-603: Gate 4 size regression detection thresholds (configurable).




# ---------------------------------------------------------------------------
# E6: Cross-phase provenance linking helpers
# ---------------------------------------------------------------------------

# Maps phase names to the context key holding per-task results for that phase.






# ---------------------------------------------------------------------------
# PCA-600: Typed data structures for edit-mode classification
# ---------------------------------------------------------------------------









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










# ============================================================================
# Handler configuration
# ============================================================================






# ============================================================================
# INTEGRATE phase — merge staged files into project_root
# ============================================================================




















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
