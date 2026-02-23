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
import re
import shlex
import subprocess
import sys
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Optional

from startd8.contractors.artisan_contractor import (
    AbstractPhaseHandler,
    WorkflowPhase,
    _SAFE_TASK_ID_PATTERN,
    compute_wave_index_map,
    compute_wave_metadata,
    compute_waves,
)
from startd8.contractors.protocols import (
    CodeGenerator,
    DRAFT_MODEL_CLAUDE_HAIKU,
    GenerationResult,
    REVIEW_MODEL_CLAUDE_OPUS,
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
except ImportError:
    _phase_tracer = _NoOpTracer()

_CACHE_SCHEMA_VERSION = 3

# Maximum file size for hash computation (50 MB).  Files larger than this
# are skipped to prevent memory spikes during cache validation.
_MAX_GEN_FILE_HASH_BYTES = 50 * 1024 * 1024

# PCA-603: Gate 4 size regression detection thresholds (configurable).
_SIZE_REGRESSION_THRESHOLD = 0.70
_SIZE_REGRESSION_MIN_LINES = 50


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "staleness": self.staleness,
            "has_hash": self.has_hash,
            "edit_weight": self.edit_weight,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PerFileMode:
        return cls(
            mode=data["mode"],
            staleness=data.get("staleness", ""),
            has_hash=data.get("has_hash", False),
            edit_weight=data.get("edit_weight", 0),
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
    force_review: bool = False
    force_test: bool = False
    design_agent: Optional[str] = None
    review_agent: Optional[str] = None
    enable_prompt_caching: bool = False
    staging_dir: Optional[str] = None  # None = .startd8/staging/
    forensic_log_level: str = "INFO"  # "DEBUG" | "INFO" | "WARNING"

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
                pass  # OTel not available — non-fatal
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

    # Normalize bare filenames, filter by valid extension, and exclude test
    # files.  Test files are the TEST phase's responsibility — including them
    # here causes the drafter to generate test code instead of the primary
    # implementation artifact.
    normalized: list[str] = []
    _test_filtered: list[str] = []
    for raw in discovered:
        if "/" not in raw and prefix:
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

    # Merge: original order first, then new discoveries (deduped).
    merged = list(dict.fromkeys(current_targets + normalized))

    logger.debug(
        "PCA-605d file discovery layers: %s, discovered=%d, merged=%d",
        layer_counts, len(normalized), len(merged),
    )

    return merged


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
    context.setdefault("source_checksum", _artifacts.get("source_checksum"))
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
    }
    _restored = 0
    for key, value in _pca_fields.items():
        if key not in context:
            context[key] = value
            _restored += 1
    if _restored:
        logger.info("Restored %d/7 onboarding fields from seed on resume", _restored)

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
                    pass

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
    "onboarding_dependency_graph",
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

        # ── Wave assignment: auto-compute or verify from seed ──
        has_wave = [t for t in sorted_tasks if t.wave_index is not None]
        missing_wave = [t for t in sorted_tasks if t.wave_index is None]

        if not has_wave or missing_wave:
            # Cases 1 & 2: no/partial wave_index → auto-compute all.
            if missing_wave and has_wave:
                logger.warning(
                    "Partial wave_index: %d/%d tasks missing wave_index — "
                    "overriding all with auto-computed waves",
                    len(missing_wave), len(sorted_tasks),
                )
            waves = compute_waves(sorted_tasks)
            wave_map = compute_wave_index_map(waves)
            for t in sorted_tasks:
                t.wave_index = wave_map.get(t.task_id, 0)
        else:
            # Case 3: All wave_index present → trust but verify
            task_count = len(sorted_tasks)
            for t in sorted_tasks:
                if t.wave_index < 0 or t.wave_index >= task_count:
                    logger.warning(
                        "Task %s: wave_index=%d out of range [0, %d) — "
                        "will be overridden by computed value",
                        t.task_id, t.wave_index, task_count,
                    )

            expected_waves = compute_waves(sorted_tasks)
            expected_map = compute_wave_index_map(expected_waves)
            mismatches = [
                (t.task_id, t.wave_index, expected_map.get(t.task_id))
                for t in sorted_tasks
                if t.wave_index != expected_map.get(t.task_id)
            ]
            if mismatches:
                logger.warning(
                    "wave_index mismatch vs depends_on graph for %d tasks: %s "
                    "— overriding with computed values",
                    len(mismatches),
                    [(tid, f"seed={sw}, computed={cw}") for tid, sw, cw in mismatches],
                )
                for t in sorted_tasks:
                    t.wave_index = expected_map.get(t.task_id, 0)
            waves = expected_waves

        # Operational circuit breakers
        wave_meta = compute_wave_metadata(waves)
        if wave_meta["wave_count"] > 1:
            parallelism_ratio = len(sorted_tasks) / wave_meta["wave_count"]
            if parallelism_ratio < 1.5:
                logger.warning(
                    "Low parallelism: %d waves for %d tasks (ratio %.1f). "
                    "This plan is nearly fully serial — consider restructuring "
                    "depends_on to increase per-wave task count.",
                    wave_meta["wave_count"], len(sorted_tasks), parallelism_ratio,
                )
            if wave_meta["critical_path_length"] > 10:
                logger.warning(
                    "Deep dependency chain: critical_path_length=%d. "
                    "Wave barriers will serialize execution across %d waves.",
                    wave_meta["critical_path_length"], wave_meta["wave_count"],
                )

        # Dependency-order assertion (skip for cycle-fallback single wave)
        if len(waves) > 1:
            _wave_map_check = {t.task_id: t.wave_index for t in sorted_tasks}
            violations = []
            for t in sorted_tasks:
                for dep_id in (t.depends_on or []):
                    dep_wave = _wave_map_check.get(dep_id)
                    if (dep_wave is not None
                            and t.wave_index is not None
                            and dep_wave >= t.wave_index):
                        violations.append(
                            (t.task_id, t.wave_index, dep_id, dep_wave)
                        )
            if violations:
                logger.error(
                    "Wave dependency-order violation for %d task pairs: %s "
                    "— falling back to single-wave execution",
                    len(violations),
                    [(tid, f"wave={tw}, dep={did}, dep_wave={dw}")
                     for tid, tw, did, dw in violations],
                )
                for t in sorted_tasks:
                    t.wave_index = 0

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

        # -- Phase 2 data flow fixes: extract ContextCore enrichment --
        _artifacts = seed_data.get("artifacts") or {}

        # Fix 1a: provenance chain — source_checksum
        source_checksum = _artifacts.get("source_checksum")
        context["source_checksum"] = source_checksum
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
        _fwd_count = sum(
            1 for k in [
                "onboarding_derivation_rules", "onboarding_resolved_parameters",
                "onboarding_output_contracts", "onboarding_calibration_hints",
                "onboarding_open_questions", "onboarding_dependency_graph",
                "service_metadata",
            ] if context.get(k)
        )
        if _fwd_count:
            logger.info(
                "PLAN phase: forwarded %d/7 onboarding inventory fields into context",
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
                    pass

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
        }

        # Store scaffold results in context
        context["scaffold"] = output

        # Context contract: validate SCAFFOLD output model
        ScaffoldPhaseOutput(scaffold=context["scaffold"])

        duration = time.monotonic() - start
        logger.info(
            "SCAFFOLD phase complete: %d dirs needed, %d exist, %d created, %d existing files (%.2fs)",
            len(dirs_needed), len(dirs_exist), len(dirs_created), len(files_existing), duration,
        )

        return {"output": output, "cost": 0.0, "metadata": {"duration": duration}}


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

    supports_feature_serial: bool = True

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

    def _get_design_phase(self) -> Any:
        """Lazily create the DesignDocumentationPhase."""
        if self._design_phase is not None:
            return self._design_phase

        from startd8.contractors.artisan_phases.design_documentation import (
            DesignDocumentationPhase,
        )

        self._design_phase = DesignDocumentationPhase(
            llm=self._get_llm_backend(),
            max_iterations=self.config.max_iterations,
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
        inv_derivation_rules: dict[str, Any] | None = None,
        inv_resolved_parameters: dict[str, Any] | None = None,
        inv_output_contracts: dict[str, Any] | None = None,
        inv_refine_suggestions: str | list[dict[str, Any]] | None = None,
        inv_plan_document: str | None = None,
        inv_calibration_hints: dict[str, Any] | None = None,
        inv_open_questions: list[dict[str, Any]] | None = None,
        inv_dependency_graph: dict[str, list[str]] | None = None,
        scaffold_existing_files: list[str] | None = None,
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

        # Cross-task context from prior designs
        if prior_design_summaries:
            additional_context["prior_designs"] = (
                "Previously designed tasks:\n"
                + "\n".join(f"- {s}" for s in prior_design_summaries[-5:])
            )

        # Calibration: depth guidance
        cal = calibration or {}
        depth_guidance = cal.get("depth_guidance")
        if depth_guidance:
            additional_context["depth_guidance"] = depth_guidance

        # Task-specific design doc content hints (supplement structural sections)
        if task.design_doc_sections:
            additional_context["design_doc_sections"] = task.design_doc_sections

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

        # Mottainai: inject plan architecture and risks sections
        if inv_plan_document:
            arch_section = DesignPhaseHandler._extract_plan_section(
                inv_plan_document, "Architecture",
            )
            if arch_section:
                additional_context["plan_architecture"] = arch_section
            risk_section = DesignPhaseHandler._extract_plan_section(
                inv_plan_document, "Risk",
            )
            if risk_section:
                additional_context["plan_risks"] = risk_section

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
        pattern = rf"^(#{2,3})\s+{re.escape(section_name)}.*$"
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
        error_box: dict[str, BaseException] = {}
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
                except BaseException as exc:
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
        return result_box["result"]

    @staticmethod
    def _serialize_result(result: Any) -> dict[str, Any]:
        """Serialize a DesignDocumentResult to a checkpoint-safe dict."""
        return {
            "design_document": result.design_document.raw_text,
            "feature_name": result.design_document.feature_name,
            "agreed": result.agreed,
            "iterations": result.iterations,
            "completed_at": result.completed_at.isoformat(),
        }

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

        design_results: dict[str, dict[str, Any]] = {}
        total_cost = 0.0
        tasks_designed = 0
        tasks_agreed = 0
        tasks_failed = 0
        tasks_adopted = 0
        tasks_refined = 0

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
                    except (FileNotFoundError, ValueError, KeyError, TypeError) as exc:
                        logger.warning(
                            "DESIGN: failed to auto-load handoff from %s: %s",
                            handoff_path, exc,
                        )

        # Extract shared context for cross-task design quality
        plan_goals = context.get("plan_goals", [])
        arch_context = context.get("architectural_context", {})
        calibration_map = context.get("design_calibration", {})
        prior_summaries: list[str] = []
        previous_task_started_mono: Optional[float] = None

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
                                pass

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

        for idx, task in enumerate(tasks, start=1):
            _task_span_cm = _phase_tracer.start_as_current_span(
                f"task.{task.task_id}",
                attributes={
                    "task.id": task.task_id,
                    "task.title": task.title,
                    "task.domain": task.domain or "",
                    "task.phase": "design",
                    "task.target_files": ",".join(task.target_files[:5]),
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
                }
                _task_span.set_attribute("task.status", "env_blocked")
                _task_span_cm.__exit__(None, None, None)
                continue

            # ----------------------------------------------------------
            # Three-way branch: adopt / refine / fresh generation
            # ----------------------------------------------------------
            prior = prior_design_results.get(task.task_id, {})
            prior_design_text: str | None = None

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
                    design_results[task.task_id] = {
                        **prior,
                        "status": "adopted",
                        "adopted_from": "prior_design_results",
                    }
                    tasks_adopted += 1
                    if prior.get("agreed"):
                        tasks_agreed += 1

                    # Feed into cross-task progressive context
                    doc_text = prior["design_document"]
                    first_line = doc_text[:300].split("\n")[0]
                    prior_summaries.append(
                        f"{task.task_id} ({task.title}): {first_line}"
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
                    _task_span.set_attribute("task.status", "adopted")
                    _task_span_cm.__exit__(None, None, None)
                    continue

            if dry_run:
                design_results[task.task_id] = {
                    "status": "dry_run_skipped",
                    "title": task.title,
                    "target_file": task.target_files[0] if task.target_files else "",
                    "constraints_count": len(task.prompt_constraints),
                    "domain": task.domain,
                }
                _task_span.set_attribute("task.status", "dry_run_skipped")
                _task_span_cm.__exit__(None, None, None)
                continue

            # Real-mode: run design documentation phase per task
            task_calibration = calibration_map.get(task.task_id, {})
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
                inv_derivation_rules=inv_derivation_rules,
                inv_resolved_parameters=inv_resolved_parameters,
                inv_output_contracts=inv_output_contracts,
                inv_refine_suggestions=inv_refine_suggestions,
                inv_plan_document=inv_plan_document,
                inv_calibration_hints=inv_calibration_hints,
                inv_open_questions=context.get("onboarding_open_questions"),
                inv_dependency_graph=context.get("onboarding_dependency_graph"),
                scaffold_existing_files=context.get("scaffold", {}).get("existing_target_files", []),
            )

            # Snapshot cost before this task
            backend = self._get_llm_backend()
            cost_before = backend.total_cost_usd

            # Retry loop for transient API errors (e.g. APIConnectionError, 529)
            _design_retry_config = RetryConfig(
                max_attempts=1,  # not used directly — we loop manually
                base_delay=5.0,
                max_delay=60.0,
                retryable_exceptions=(ConnectionError, TimeoutError, OSError),
                retryable_status_codes=(429, 500, 502, 503, 504, 529),
            )
            _max_attempts = 1 + self.config.design_task_retries

            for _attempt in range(_max_attempts):
                try:
                    design_phase = self._get_design_phase()
                    result = self._run_design_async(
                        design_phase, feature_context,
                        timeout=self.config.development_timeout_seconds,
                    )
                    task_cost = backend.total_cost_usd - cost_before
                    total_cost += task_cost

                    serialized = self._serialize_result(result)
                    serialized["status"] = "refined" if prior_design_text else "designed"
                    serialized["cost"] = task_cost
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

                    if prior_design_text:
                        tasks_refined += 1
                    else:
                        tasks_designed += 1
                    if result.agreed:
                        tasks_agreed += 1

                    # Accumulate cross-task summary for progressive context
                    doc_text = result.design_document.raw_text
                    first_line = doc_text[:300].split("\n")[0]
                    summary = f"{task.task_id} ({task.title}): {first_line}"
                    prior_summaries.append(summary)

                    # Write design doc to output_dir if configured
                    if self.output_dir:
                        out_path = Path(self.output_dir) / f"{task.task_id}-design.md"
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        out_path.write_text(
                            result.design_document.raw_text, encoding="utf-8"
                        )
                        design_results[task.task_id]["output_file"] = str(out_path)
                        logger.info("Wrote design doc: %s", out_path)

                    _task_span.set_attribute("task.cost", task_cost)
                    _task_span.set_attribute("task.attempts", _attempt + 1)
                    _task_span.set_attribute("task.status", "designed")
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
                    }
                    break  # non-retryable or final attempt — exit retry loop

            # Close the per-task span after the retry loop completes
            _task_span_cm.__exit__(None, None, None)

        context["design_results"] = design_results

        # B-6: Derive design_mode_summary from filesystem ground truth
        # (scaffold.existing_target_files) instead of design iteration status.
        # Used by chain 5 (design_mode_to_implement) for verifiable propagation.
        _scaffold_existing = set(
            context.get("scaffold", {}).get("existing_target_files", [])
        )
        _task_by_id = {t.task_id: t for t in tasks}

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

        # Context contract: validate DESIGN output model
        DesignPhaseOutput(design_results=context["design_results"])

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
                )
                logger.info("DESIGN: wrote handoff for auto-adoption: %s", handoff_path)
            except (OSError, ValueError, TypeError) as exc:
                logger.warning("DESIGN: failed to write handoff: %s", exc, exc_info=True)

        env_blocked = sum(
            1 for r in design_results.values()
            if r.get("status") == "env_blocked"
        )
        output: dict[str, Any] = {
            "tasks_designed": tasks_designed,
            "tasks_refined": tasks_refined,
            "tasks_adopted": tasks_adopted,
            "tasks_agreed": tasks_agreed,
            "tasks_failed": tasks_failed,
            "tasks_skipped": len(tasks) - tasks_designed - tasks_refined - tasks_adopted - tasks_failed - env_blocked,
            "total_cost": total_cost,
        }
        if self.output_dir:
            output["output_dir"] = self.output_dir

        duration = time.monotonic() - start
        logger.info(
            "DESIGN phase complete: %d designed, %d refined, %d adopted, %d agreed, %d failed, $%.4f cost (%.2fs)",
            tasks_designed, tasks_refined, tasks_adopted, tasks_agreed, tasks_failed, total_cost, duration,
        )

        return {"output": output, "cost": total_cost, "metadata": {"duration": duration}}


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

    supports_feature_serial: bool = True

    def __init__(
        self,
        handler_config: Optional[HandlerConfig] = None,
        code_generator: Optional[CodeGenerator] = None,  # deprecated, ignored
        enriched_seed_path: Optional[Path] = None,
        project_root: Optional[Path] = None,
    ) -> None:
        self.config = handler_config or HandlerConfig()
        self._enriched_seed_path = enriched_seed_path
        self._project_root = project_root

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _check_environment(self, task: SeedTask) -> list[dict[str, Any]]:
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
                        pass

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

                # AR-143, AR-145: Python-specific validators
                if rel_path.endswith(".py"):
                    task_issues.extend(validate_import_dependency(code, enrichment))
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
            pass

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
                    # Find matching generated file — match by filename
                    gen_lines = 0
                    for gen_path, gen_lc in gen_line_counts.items():
                        if gen_path.endswith(existing_path) or Path(gen_path).name == Path(existing_path).name:
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
    ) -> EditModeClassification:
        """Classify each target file as 'create' or 'edit' using upstream signals.

        Consumes 5 signals computed but previously unconsumed by IMPLEMENT:
          - scaffold["existing_target_files"] (Tier 1, weight 2)
          - task.existing_content_hash (Tier 1, weight 2)
          - design_mode_summary[task_id] (Tier 2, weight 1)
          - scaffold["staleness_classification"] (Tier 2, weight 1)
          - task.file_scope (Tier 2, weight 1)

        Returns EditModeClassification with typed fields for mode, per_file,
        confidence, and signal_conflicts.
        """
        existing_targets = set(scaffold.get("existing_target_files", []))
        staleness_map = scaffold.get("staleness_classification", {})
        design_mode = design_mode_summary.get(task.task_id, "")

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

            # Tier 2 (weight 1): design_mode_summary
            if design_mode == "update":
                edit_weight += 1
                file_signals_edit.append("design_mode_summary=update")
            elif design_mode == "create":
                create_weight += 1
                file_signals_create.append("design_mode_summary=create")

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

            # Classify this file
            if edit_weight >= 1:
                file_mode = "edit"
            else:
                file_mode = "create"

            # Detect Tier 1 vs Tier 2 conflicts
            tier1_edit = has_hash or in_existing
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
        # PCA-600: edit mode classification from upstream signals
        edit_mode_map: dict[str, EditModeClassification] | None = None,
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
        active_task_ids = {t.task_id for t in tasks}

        env_blocked_ids: set[str] = set()
        for task in tasks:
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
                    "environment_issues": [
                        c for c in task.environment_checks
                        if c.get("status") in ("fail", "warn")
                    ],
                })

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
                    "blocked_dependencies": blocked_deps,
                    "depends_on": task.depends_on,
                })
                continue

            # Extract design document from DESIGN phase results (if available).
            # "adopted" status indicates reuse from a prior run (dress-rehearsal).
            design_doc_text = None
            task_design = design_results.get(task.task_id, {})
            if task_design.get("status") in ("designed", "adopted", "refined"):
                design_doc_text = task_design.get("design_document")

            # ── Layer 1: DESIGN→IMPLEMENT boundary validation (DP-2) ────
            # Defense-in-depth: per-task line-count pre-check before the
            # phase-level contract exit validator (BP-3).  Metric aligned
            # with artisan-pipeline.contract.yaml: line_count >= 50.
            if task_design.get("status") in ("designed", "adopted", "refined"):
                _line_count = len(design_doc_text.strip().splitlines()) if design_doc_text else 0
                if not design_doc_text or _line_count < 50:
                    logger.warning(
                        "DESIGN→IMPLEMENT boundary: task %s has status '%s' but "
                        "design_document is empty/trivial (%d lines) — falling back "
                        "to task description only (DP-2: no silent defaults)",
                        task.task_id,
                        task_design.get("status"),
                        _line_count,
                    )
                    design_doc_text = None
                else:
                    _design_lines = len(design_doc_text.strip().splitlines())
                    _design_sections = sum(
                        1
                        for line in design_doc_text.splitlines()
                        if line.strip().startswith("##")
                    )
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

                # ── Downstream file detection (Fix 2) ────────────────────
                # If the design doc says a file is for downstream tasks,
                # tell the drafter explicitly to produce a minimal stub for
                # it.  This prevents the drafter from omitting it entirely
                # (thinking "that's someone else's job") and avoids the
                # expensive retry that won't change its mind.
                from startd8.contractors.generators.lead_contractor import (
                    _detect_downstream_files,
                )
                downstream = _detect_downstream_files(
                    task.target_files, design_doc_text or "",
                )
                if downstream:
                    ds_list = ", ".join(downstream)
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
                        len(downstream), task.task_id, downstream,
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

            # Strip dependencies on tasks not in this run (already completed
            # or filtered out by --task-filter).  The plan validator rejects
            # references to non-existent chunks.
            in_scope_deps = [d for d in task.depends_on if d in active_task_ids]

            # ── IMP-7: DESIGN→IMPLEMENT parameter completeness validation ──
            # Check that resolved_parameters from the seed are present in the
            # design document. Missing parameters indicate information loss at
            # the DESIGN bottleneck.
            design_completeness_warning = ""
            if design_doc_text:
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
                    "max_output_tokens": max_output_tokens,
                    "artifact_types_addressed": task.artifact_types_addressed,
                    "downstream_files": task_downstream,
                    "original_target_files": task.target_files if task_downstream else None,
                    # Fix 2d: parameter_sources filtered by task's artifact types
                    # BP-5: merge sources for all artifact types (not just first)
                    "parameter_sources": (
                        {
                            atype: (parameter_sources or {}).get(atype, {})
                            for atype in task.artifact_types_addressed
                            if atype in (parameter_sources or {})
                        } if task.artifact_types_addressed else {}
                    ),
                    # Fix 3c: semantic_conventions for code generation
                    "semantic_conventions": semantic_conventions or {},
                    # IMP-7: DESIGN→IMPLEMENT parameter completeness warning
                    "design_completeness_warning": design_completeness_warning,
                    # PCA-300: project architecture for code generation
                    "architectural_context": architectural_context or {},
                    "plan_goals": (plan_goals or [])[:5],
                    "plan_context": (plan_context or "")[:4000] or None,
                    # PCA-301/400: service metadata for protocol compliance
                    "service_metadata": service_metadata if service_metadata else None,
                    # PCA-401: per-task calibration hints
                    "calibration_hints": (calibration_hints or {}).get(task.task_id) if calibration_hints else None,
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
                "target_files": chunk.file_targets,
                "estimated_loc": meta.get("estimated_loc", 0),
                "depends_on": chunk.dependencies,
                "prompt_constraints_count": len(meta.get("prompt_constraints", [])),
                "validators": meta.get("post_generation_validators", []),
                # PCA-505: track whether existing files were present for review
                "had_existing_files": bool(meta.get("_existing_file_contents")),
            }

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
        error_box: dict[str, BaseException] = {}
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
                except BaseException as exc:  # pragma: no cover - propagated
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
    ) -> dict[str, GenerationResult] | None:
        """Validate a saved generation_results cache through 7 ordered layers.

        Returns a dict of task_id → GenerationResult if all layers pass,
        or None if the cache should be rejected (caller falls through to
        fresh IMPLEMENT).

        Layers (cheapest → most expensive):
            0: Schema version — _cache_meta exists, schema_version == _CACHE_SCHEMA_VERSION
            1: Filter success:false entries (info log)
            2: Coverage — all current task IDs present in successful entries
            3: Source checksum — _cache_meta.source_checksum matches context
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
            7, len(generation_results),
        )
        return generation_results

    @staticmethod
    def _build_implementation_metadata(context: dict[str, Any]) -> dict[str, Any]:
        """Build the metadata sub-dict mirroring propagation chain fields."""
        return {
            "design_mode_summary": context.get("design_mode_summary", {}),
            "service_metadata": context.get("service_metadata"),
        }

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
        _log_context_completeness("IMPLEMENT", context)
        tasks: list[SeedTask] = _ensure_context_loaded(context)
        _project_root_str = context.get("project_root")
        project_root = Path(_project_root_str) if _project_root_str and _project_root_str.strip() else Path(".")
        _has_explicit_project_root = bool(_project_root_str and _project_root_str.strip())

        logger.info("IMPLEMENT phase: processing %d tasks (dry_run=%s)", len(tasks), dry_run)

        # --- Pre-IMPLEMENT validation: warn about risky multi-file tasks ---
        self._validate_multi_file_tasks(tasks)

        # --- Dry-run path (unchanged) ---
        if dry_run:
            task_reports: list[dict[str, Any]] = []
            for task in tasks:
                env_checks = self._check_environment(task)
                task_report: dict[str, Any] = {
                    "task_id": task.task_id,
                    "feature_id": task.feature_id,
                    "title": task.title,
                    "domain": task.domain,
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
        if (
            _has_explicit_project_root
            and results_path.exists()
            and not dry_run
            and not self.config.force_implement
        ):
            try:
                with open(results_path) as f:
                    saved = json.load(f)
                validated = self._validate_resume_cache(
                    saved, tasks, project_root,
                    source_checksum=context.get("source_checksum"),
                )
                if validated is not None:
                    generation_results = validated
                    current_task_ids = {t.task_id for t in tasks}

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

                    domain_tasks: dict[str, list[str]] = defaultdict(list)
                    for task in tasks:
                        domain_tasks[task.domain].append(task.task_id)

                    task_reports: list[dict[str, Any]] = []
                    for task in tasks:
                        gr = generation_results.get(task.task_id)
                        report: dict[str, Any] = {
                            "task_id": task.task_id,
                            "feature_id": task.feature_id,
                            "title": task.title,
                            "domain": task.domain,
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

        if not resumed:
            # Item 12: scaffold test files for artifact generator tasks first
            if self.config.scaffold_test_first:
                self._ensure_test_scaffolding_for_artifact_tasks(
                    tasks, project_root
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

            # PCA-600: Build per-task edit mode classification from upstream signals
            scaffold = context.get("scaffold", {})
            design_mode_summary = context.get("design_mode_summary", {})
            edit_mode_map: dict[str, EditModeClassification] = {}
            for task in tasks:
                edit_mode_map[task.task_id] = self._classify_edit_mode(
                    task, scaffold, design_mode_summary,
                )
            edit_tasks = sum(1 for v in edit_mode_map.values() if v.mode == "edit")
            conflict_tasks = sum(1 for v in edit_mode_map.values() if v.signal_conflicts)
            logger.info(
                "IMPLEMENT: edit mode classification: %d edit, %d create "
                "(%d with signal conflicts) (from 5 upstream signals, 2-tier weighted consensus)",
                edit_tasks, len(tasks) - edit_tasks, conflict_tasks,
            )
            # PCA-600 AC 9: Persist structured classifications for post-hoc debugging
            context["edit_mode_classifications"] = {
                task_id: classification.to_dict()
                for task_id, classification in edit_mode_map.items()
            }

            chunks, skipped_reports = self._tasks_to_chunks(
                tasks,
                max_retries=2,
                design_results=design_results,
                calibration_map=calibration_map,
                downstream_map=downstream_map,
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
            )

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
                        },
                        "downstream_map": downstream_map,
                        "truncation_flags": truncation_flags,
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

        context["implementation"] = output
        output["metadata"] = self._build_implementation_metadata(context)
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

    __slots__ = ("_task", "_gen", "_edit_mode")

    def __init__(
        self,
        task: SeedTask,
        gen_result: GenerationResult,
        edit_mode: dict[str, Any] | None = None,
    ) -> None:
        self._task = task
        self._gen = gen_result
        self._edit_mode = edit_mode

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


class IntegratePhaseHandler(AbstractPhaseHandler):
    """INTEGRATE phase: merge staged files into project_root with validation.

    Reads ``generation_results`` from context (populated by IMPLEMENT),
    runs each task through IntegrationEngine, and writes
    ``integration_results`` back to context.

    Files are merged from ``_staging_dir`` (or ``.startd8/staging/``)
    into the project root.  Auto-commit (if enabled) happens here,
    not in IMPLEMENT.
    """

    supports_feature_serial: bool = True

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
            auto_commit=self.config.auto_commit,
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

            with _phase_tracer.start_as_current_span(
                f"task.{task_id}",
                attributes={
                    "task.id": task_id,
                    "task.phase": "integrate",
                },
            ) as _int_span:
                # Pass edit mode classification so the integration engine
                # can skip merge strategy for edit-mode tasks (the staging
                # file IS the complete file after search/replace).
                _edit_classifications = context.get(
                    "edit_mode_classifications", {},
                )
                _task_edit_mode = _edit_classifications.get(task_id)
                unit = SeedTaskUnit(task, gr, edit_mode=_task_edit_mode)
                listener = ArtisanIntegrationListener(task_id)
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

                # Update generation_results paths: staging → project_root
                if result.success:
                    gr.generated_files = [Path(f) for f in result.integrated_files]

        # Clean staging dir
        if staging_dir.exists() and not dry_run:
            _shutil.rmtree(staging_dir, ignore_errors=True)

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

        # Validate output structure before writing to context
        from startd8.contractors.context_schema import IntegratePhaseOutput
        try:
            IntegratePhaseOutput.model_validate(
                {"integration_results": integration_results}
            )
        except Exception as exc:
            logger.warning(
                "INTEGRATE output validation failed (continuing): %s", exc,
            )

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

    supports_feature_serial: bool = True

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
            module_name = self._file_to_module(target_files[0], project_root) if target_files else ""
            if module_name:
                return [py, "-c", f"import {module_name}"]
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
    ) -> dict[str, Any] | None:
        """Validate a saved test_results cache through 3 ordered layers.

        Returns the cached output dict if all layers pass, or None if the
        cache should be rejected (caller falls through to fresh TEST).

        Layers (cheapest → most expensive):
            0: Schema version — _cache_meta exists, schema_version == _CACHE_SCHEMA_VERSION
            1: Source checksum — _cache_meta.source_checksum matches context
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
                )
                if cached_output is not None:
                    context["test_results"] = cached_output
                    # Construct-to-validate: build the Pydantic model to
                    # verify the cached dict still passes schema checks
                    # (e.g. required keys, per_task type).  Discarded
                    # immediately — we only need the validation side-effect.
                    ValidationPhaseOutput(test_results=cached_output)
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

        for idx, task in enumerate(tasks, start=1):
            _task_span_cm = _phase_tracer.start_as_current_span(
                f"task.{task.task_id}",
                attributes={
                    "task.id": task.task_id,
                    "task.title": task.title,
                    "task.domain": task.domain or "",
                    "task.phase": "test",
                },
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
                else:
                    total_failed += 1
                    _task_span.set_attribute("task.status", "failed")
            except Exception as exc:
                logger.warning(
                    "TEST: unexpected error for task %s: %s",
                    task.task_id, exc, exc_info=True,
                )
                test_plan.append({
                    "task_id": task.task_id,
                    "title": task.title,
                    "domain": task.domain,
                    "validators_run": 0,
                    "all_passed": False,
                    "results": [],
                    "status": "error",
                    "error": str(exc),
                })
                total_failed += 1
                _task_span.set_attribute("task.status", "error")
            finally:
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
                    "status": "skipped_no_generation",
                    "passed": None,
                    "validators_run": 0,
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

        output = {
            "test_plan": test_plan,
            "total_validators": sum(len(t.post_generation_validators) for t in tasks),
            "unique_validators": dict(validator_counts),
            "tasks_with_tests": len([t for t in test_plan if t.get("validator_count", 0) > 0 or t.get("validators_run", 0) > 0]),
            "total_passed": total_passed,
            "total_failed": total_failed,
            "per_task": per_task,
        }

        context["test_results"] = output

        # Context contract: validate TEST output model
        ValidationPhaseOutput(test_results=context["test_results"])

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

                cache_envelope: dict[str, Any] = {
                    "_cache_meta": {
                        "schema_version": _CACHE_SCHEMA_VERSION,
                        "created_at": datetime.datetime.now(
                            datetime.timezone.utc
                        ).isoformat(),
                        "source_checksum": context.get("source_checksum"),
                        "generation_file_hashes": gen_file_hashes,
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


class ReviewPhaseHandler(AbstractPhaseHandler):
    """REVIEW phase: LLM-based quality review of generated implementations.

    In dry-run mode: reports review checklist (unchanged).
    In real mode: sends generated code to a review agent for
    quality scoring, then aggregates pass/fail verdicts.
    """

    supports_feature_serial: bool = True

    def __init__(self, handler_config: Optional[HandlerConfig] = None) -> None:
        self.config = handler_config or HandlerConfig()
        self._review_agent: Any = None

    # ------------------------------------------------------------------
    # Review prompt template
    # ------------------------------------------------------------------

    REVIEW_PROMPT_TEMPLATE = """You are reviewing generated code for quality and correctness.

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
    ) -> str:
        """Build the review prompt for a single task.

        Args:
            task: The seed task.
            generated_code: The code that was generated.
            test_results: Test results from the TEST phase.
            design_document: Optional design document from DESIGN phase
                for compliance checking.
            parameter_sources: Optional parameter source mappings for
                the reviewer to verify correct parameter usage.
            semantic_conventions: Optional semantic convention mappings
                for the reviewer to verify naming compliance.
            truncation_info: Optional Gate 4 truncation detection result.
                When present, a warning is injected so the reviewer
                scrutinizes completeness.

        Returns:
            Formatted review prompt string.
        """
        constraints_str = "\n".join(
            f"- {c}" for c in task.prompt_constraints
        ) or "None specified"

        test_str = json.dumps(test_results, indent=2, default=str) if test_results else "No test results available for this task"

        max_code = self.config.review_max_code_chars
        code_for_prompt = generated_code[:max_code]
        if len(generated_code) > max_code:
            code_for_prompt += f"\n\n# ... [truncated — {len(generated_code) - max_code} chars omitted] ..."

        max_test = 2000
        test_for_prompt = test_str[:max_test]
        if len(test_str) > max_test:
            test_for_prompt += f"\n... [truncated — {len(test_str) - max_test} chars omitted] ..."

        prompt = self.REVIEW_PROMPT_TEMPLATE.format(
            task_id=task.task_id,
            title=task.title,
            domain=task.domain,
            description=task.description,
            constraints=constraints_str,
            generated_code=code_for_prompt,
            test_results=test_for_prompt,
            pass_threshold=self.config.pass_threshold,
        )

        # PCA-302/505: project-level context for architectural review
        if project_context:
            _pc_parts = ["## Project Context"]
            # PCA-505: project name in review
            _pn = project_context.get("project_name")
            if _pn:
                _pc_parts.append(f"**Project:** {_pn}")
            _pt = project_context.get("plan_title")
            if _pt:
                _pc_parts.append(f"**Plan:** {_pt}")
            _pg = project_context.get("plan_goals", [])
            for g in _pg[:5]:
                _pc_parts.append(f"- {g}")
            _arch = project_context.get("architectural_context", {})
            _objs = _arch.get("objectives", [])
            if _objs:
                _pc_parts.append("**Architectural Objectives:**")
                for o in (list(_objs) if isinstance(_objs, list) else [_objs])[:3]:
                    _pc_parts.append(f"- {o}")
            _cons = _arch.get("constraints", [])
            if _cons:
                _pc_parts.append("**Constraints:**")
                for c in (list(_cons) if isinstance(_cons, list) else [_cons])[:5]:
                    _pc_parts.append(f"- {c}")
            # PCA-505: edit-first review check when task had existing files
            if project_context.get("had_existing_files"):
                _pc_parts.append("\n**Edit-First Verification:**")
                _pc_parts.append(
                    "This task modified EXISTING production files. Verify the "
                    "implementation preserves existing functionality and does not "
                    "remove or break existing code that was not part of the change scope."
                )
            _pc_text = "\n".join(_pc_parts)
            if len(_pc_text) > 2000:
                _pc_text = _pc_text[:2000] + "\n... [truncated for prompt budget]"
            prompt = prompt.replace(
                "## Review Instructions",
                _pc_text + "\n\n## Review Instructions",
            )

        # ── Layer 4: Inject design compliance section ────────────────
        if design_document:
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
            design_compliance_section = (
                f"\n## Design Document (from DESIGN phase — {design_lines} lines, "
                f"{design_sections} sections)\n"
                f"The implementation was built from this design specification. "
                f"**You MUST check that the implementation covers ALL sections "
                f"and requirements from this design.** Score lower if major "
                f"sections are missing or only partially implemented.\n\n"
                f"```\n{design_for_prompt}\n```\n"
            )
            prompt = prompt.replace(
                "## Review Instructions",
                design_compliance_section + "\n## Review Instructions",
            )

        # ── Inject parameter_sources / semantic_conventions ────────────
        extra_sections: list[str] = []
        if parameter_sources:
            extra_sections.append(
                "\n## Parameter Sources\n"
                + "\n".join(f"- **{k}**: {v}" for k, v in parameter_sources.items())
                + "\nVerify the implementation uses the correct parameter names and sources.\n"
            )
        if semantic_conventions:
            extra_sections.append(
                "\n## Semantic Conventions\n"
                + "\n".join(f"- **{k}**: {v}" for k, v in semantic_conventions.items())
                + "\nVerify the implementation follows these naming conventions.\n"
            )
        if extra_sections:
            extra = "\n".join(extra_sections)
            prompt = prompt.replace(
                "## Review Instructions",
                extra + "\n## Review Instructions",
            )

        # PCA-303: service metadata compliance check
        if service_metadata:
            _smc_parts = ["## Service Metadata Compliance"]
            _tp = service_metadata.get("transport_protocol")
            if _tp:
                _smc_parts.append(f"- Expected transport protocol: **{_tp}**")
            _rd = service_metadata.get("runtime_dependencies")
            if _rd and isinstance(_rd, list):
                _smc_parts.append(
                    f"- Expected runtime dependencies: {', '.join(str(d) for d in _rd)}"
                )
            _smc_parts.append(
                "Check that HEALTHCHECK mechanism matches transport_protocol. "
                "Flag any capabilities added that the service metadata declares as absent."
            )
            _smc_text = "\n".join(_smc_parts)
            prompt = prompt.replace(
                "## Review Instructions",
                _smc_text + "\n\n## Review Instructions",
            )

        # ── IMP-9b: Inject REFINE compliance section ──────────────────
        if refine_provenance:
            applied_ids = refine_provenance.get("applied_ids", [])
            if applied_ids:
                _rc_parts = [
                    "\n## REFINE Compliance\n",
                    "The following REFINE phase suggestions were integrated into "
                    "the plan document before code generation. **Verify that the "
                    "implementation reflects these applied changes:**",
                ]
                for aid in applied_ids[:20]:
                    _rc_parts.append(f"- {aid}")
                warning_ids = refine_provenance.get("warning_ids", [])
                if warning_ids:
                    _rc_parts.append(
                        "\nThe following suggestions had apply warnings "
                        "(may not be fully integrated):"
                    )
                    for wid in warning_ids[:10]:
                        _rc_parts.append(f"- {wid} (verify manually)")
                _rc_parts.append(
                    "\nScore lower if the implementation ignores changes "
                    "that were explicitly applied to the plan.\n"
                )
                _rc_text = "\n".join(_rc_parts)
                prompt = prompt.replace(
                    "## Review Instructions",
                    _rc_text + "\n## Review Instructions",
                )

        # ── Gate 4: Inject truncation warning into review ────────────
        if truncation_info:
            source = truncation_info.get("source", "unknown")
            confidence = truncation_info.get("max_confidence", 0.0)
            syntax_errs = truncation_info.get("syntax_errors", [])
            total_lines = truncation_info.get("total_lines", 0)
            estimated = truncation_info.get("estimated_loc", 0)
            parts = [
                "\n## TRUNCATION WARNING (Gate 4)\n",
                f"Automated analysis flagged this task's output as potentially truncated "
                f"(source={source}, confidence={confidence:.2f}).",
            ]
            if syntax_errs:
                parts.append(f"Syntax errors in: {', '.join(syntax_errs)}.")
            if estimated and total_lines:
                parts.append(
                    f"Generated {total_lines} lines vs {estimated} estimated "
                    f"({total_lines / estimated:.0%} ratio)."
                )
            parts.append(
                "**Pay special attention to completeness.** "
                "Score lower if the implementation appears incomplete or has syntax errors.\n"
            )
            truncation_section = "\n".join(parts)
            if "## Review Instructions" in prompt:
                prompt = prompt.replace(
                    "## Review Instructions",
                    truncation_section + "\n## Review Instructions",
                )
            else:
                logger.warning(
                    "Gate 4: '## Review Instructions' heading not found in "
                    "review prompt — appending truncation warning at end"
                )
                prompt += "\n" + truncation_section

        # ── Gate 5: Allowlist confidence advisory ──────────────────────
        deps_confidence = getattr(task, "deps_confidence", 1.0)
        deps_source = getattr(task, "deps_source", None)
        if deps_confidence < 0.8 and test_results:
            # Check if any deps_available failures exist
            has_deps_issues = any(
                r.get("validator") == "deps_available" and not r.get("passed", True)
                for r in test_results.get("results", [])
            )
            if has_deps_issues:
                parts = [
                    "\n## DEPENDENCY ALLOWLIST ADVISORY (Gate 5)\n",
                    f"The dependency allowlist was built from source={deps_source!r} "
                    f"(confidence={deps_confidence:.2f}).",
                ]
                if deps_confidence <= 0.2:
                    parts.append(
                        "Only stdlib modules are known — third-party import "
                        "violations are **likely false positives**."
                    )
                elif deps_confidence <= 0.5:
                    parts.append(
                        "Allowlist was built from venv scan only — some "
                        "dependencies may be missing from the known set."
                    )
                parts.append(
                    "**Do NOT penalize the score for import violations when "
                    "allowlist confidence is low.** Focus review on code "
                    "quality, correctness, and design compliance instead.\n"
                )
                advisory_section = "\n".join(parts)
                if "## Review Instructions" in prompt:
                    prompt = prompt.replace(
                        "## Review Instructions",
                        advisory_section + "\n## Review Instructions",
                    )
                else:
                    prompt += "\n" + advisory_section

        return prompt

    def _parse_review_response(self, response: str) -> dict[str, Any]:
        """Parse score, verdict, and issues from the LLM review response.

        Args:
            response: Raw LLM output.

        Returns:
            Dict with ``score``, ``verdict``, ``strengths``, ``issues``, ``suggestions``.

        """
        import re

        score = 0
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
                    "REVIEW: could not extract score from response (defaulting to 0); "
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
            "passed": verdict == "PASS" and score >= self.config.pass_threshold,
            "raw_response": response[:4000],  # truncate for storage
            "strengths": extract_section("Strengths"),
            "issues": extract_section("Issues"),
            "suggestions": extract_section("Suggestions"),
        }

    _REVIEW_PHASE_SYSTEM_PROMPT = (
        "You are an expert code quality reviewer. Evaluate the implementation "
        "against the design document, checking for correctness, completeness, "
        "and adherence to stated constraints."
    )

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
            max_attempts=1,  # not used directly — we loop manually
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
                )
                response_text, _time_ms, token_usage = agent.generate(
                    prompt, system_prompt=self._REVIEW_PHASE_SYSTEM_PROMPT,
                )
                review = self._parse_review_response(response_text)
                review["task_id"] = task.task_id
                review["cost"] = token_usage_cost(token_usage)
                review["tokens"] = {
                    "input": token_usage_input(token_usage),
                    "output": token_usage_output(token_usage),
                }
                review["status"] = "reviewed"

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
                    },
                    forensic_log_level=self.config.forensic_log_level,
                )

                return review
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
                    "score": 0,
                    "verdict": "ERROR",
                    "passed": False,
                    "cost": 0.0,
                    "tokens": {"input": 0, "output": 0},
                    "error": str(exc),
                    "status": "review_error",
                }
        # Unreachable — loop always returns — but satisfies type checker
        return {
            "task_id": task.task_id, "score": 0, "verdict": "ERROR",
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
            "score": 0,
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
    ) -> dict[str, dict[str, Any]]:
        """Validate a saved review cache through 4 ordered layers.

        Returns a dict of task_id → cached review data for entries that
        pass all layers. Empty dict if cache-wide validation fails.

        Layers (cheapest → most expensive):
            0: Schema version — _cache_meta exists, schema_version == _CACHE_SCHEMA_VERSION
            1: Source checksum — _cache_meta.source_checksum matches context
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
                )
                logger.info(
                    "REVIEW: loaded %d validated cached review result(s) from %s",
                    len(cached_reviews), review_cache_path,
                )
            except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError, UnicodeDecodeError) as exc:
                logger.warning("REVIEW: failed to load cache from %s: %s", review_cache_path, exc)
                cached_reviews = {}

        for idx, task in enumerate(tasks, start=1):
            _task_span_cm = _phase_tracer.start_as_current_span(
                f"task.{task.task_id}",
                attributes={
                    "task.id": task.task_id,
                    "task.title": task.title,
                    "task.domain": task.domain or "",
                    "task.phase": "review",
                },
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
                    continue
                task_test = test_by_task.get(task.task_id, {})

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

                review = self._review_task(
                    task, generated_code, task_test,
                    design_document=task_design_doc,
                    parameter_sources=context.get("parameter_sources"),
                    semantic_conventions=context.get("semantic_conventions"),
                    truncation_info=task_truncation,
                    project_context=_project_context,
                    service_metadata=context.get("service_metadata"),
                    refine_provenance=context.get("refine_provenance"),
                )
                review["title"] = task.title
                review["domain"] = task.domain
                review["constraint_count"] = len(task.prompt_constraints)
                review["env_failures"] = len(env_fails)
                review["env_warnings"] = len(env_warns)
                review["review_status"] = review.get("status", "reviewed")
                if task_truncation:
                    review["truncation_warning"] = True
                    review["truncation_confidence"] = task_truncation.get("max_confidence", 0.0)
                    review["truncation_source"] = task_truncation.get("source", "unknown")

                total_cost += review.get("cost", 0.0)
                if review.get("passed", False):
                    total_passed += 1
                else:
                    total_failed += 1

                review_items.append(review)

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
            finally:
                _task_span_cm.__exit__(None, None, None)

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
                    "score": 0,
                    "verdict": "ERROR",
                    "error": item.get("error", ""),
                }
            else:
                per_task[task_id] = {
                    "status": status,
                    "passed": item.get("passed") if status in ("reviewed", "cached") else None,
                    "score": item.get("score"),
                    "verdict": item.get("verdict"),
                }

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
        }

        context["review_results"] = output

        # Context contract: validate REVIEW output model
        ReviewPhaseOutput(review_results=context["review_results"])

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
            pass  # contextcore propagation not available — use fallback
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
            pass  # OTel not available — non-fatal

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

    def _build_cost_summary(self, context: dict[str, Any]) -> dict[str, Any]:
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

        def _safe_cost(d: dict, key: str = "total_cost") -> float:
            try:
                return float(d.get(key, 0.0))
            except (TypeError, ValueError):
                return 0.0

        impl_cost = _safe_cost(implementation)
        test_cost = _safe_cost(test_results)
        review_cost = _safe_cost(review_results)
        total = impl_cost + test_cost + review_cost

        return {
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

        task_status: dict[str, dict[str, Any]] = {}
        for task_id, gen_result in generation_results.items():
            test_info = test_results_map.get(task_id, {})
            review_info = review_results_map.get(task_id, {})
            task_status[task_id] = {
                "generated": gen_result.success,
                "files_count": len(gen_result.generated_files),
                "generation_cost_usd": gen_result.cost_usd,
                "tests_passed": test_info.get("passed", None),
                "review_score": review_info.get("score", None),
                "review_passed": review_info.get("passed", None),
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

        if generated_fail == 0 and generated_ok == total_tasks:
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
            "artifact_count": len(artifacts),
            "dry_run": dry_run,
        }

        # PCA-402: attach onboarding consumption audit trail to provenance
        _onb_consumption = context.get("_onboarding_consumption")
        if _onb_consumption:
            summary.setdefault("provenance", {})["onboarding_fields_consumed"] = _onb_consumption

        # Task 11a: Gate 3b content validation summary
        gate3b_data: dict[str, Any] = implementation.get("_gate3b_content_validation", {})
        if gate3b_data:
            severity_counts = self._count_gate3b_by_severity(gate3b_data)
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

        # Write report and manifest
        if self.output_dir and not dry_run:
            output_path = Path(self.output_dir) / "workflow-execution-report.json"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(output_path, summary, indent=2, default=str)
            logger.info("Wrote execution report to %s", output_path)
            summary["report_path"] = str(output_path)

            # Write manifest of generated files
            manifest_path = self._write_manifest(
                artifacts, summary, context, Path(self.output_dir),
            )
            if manifest_path:
                summary["manifest_path"] = str(manifest_path)

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
            code_generator: Optional pre-configured CodeGenerator instance.

        Returns:
            Dict mapping WorkflowPhase → handler instance.
        """
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
