"""
Prime Contractor Post-Mortem Evaluation Module.

Evaluates PrimeContractor run results with:
- Root-cause classification for failures (16 causes across 9 pipeline stages)
- Element-level analysis from Micro Prime FileResult metadata
- Cross-feature pattern detection (repeated causes, cost outliers)
- Actionable lessons extraction

Two entry points:
    1. Async hook: launch_prime_postmortem_async() called from PrimeContractor.run()
    2. Standalone: scripts/run_prime_postmortem.py for post-hoc analysis
"""

from __future__ import annotations

import copy
import dataclasses
import datetime
import json
import re
import threading
import uuid
from collections import Counter
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from startd8.logging_config import get_logger

from .artisan_phases.retrospective import (
    AntiPatternDetector,
    AntiPatternFinding,
    Lesson,
    LessonCategory,
    RetrospectiveContext,
    Sanitizer,
    Severity,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PASS_THRESHOLD = 0.8
_PARTIAL_THRESHOLD = 0.4
_POSTMORTEM_TIMEOUT_S = 300
_COST_OUTLIER_FACTOR = 2.0  # Feature costing 2x+ average is an outlier
_CROSS_FEATURE_PATTERN_MIN = 2  # Minimum occurrences for repeated_root_cause
_ESCALATION_MIN_FEATURES = 3   # Minimum distinct features for escalation patterns (REQ-KZ-401a)
_ESCALATION_MIN_ELEMENTS = 5   # Minimum total element escalations (REQ-KZ-401a)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RootCause(str, Enum):
    """Root cause classification for feature/element failures."""

    DUPLICATE_IMPORT = "duplicate_import"
    UNFILLED_STUB = "unfilled_stub"
    SCOPE_CORRUPTION = "scope_corruption"
    PHANTOM_IMPORT = "phantom_import"
    SKELETON_MISSING = "skeleton_missing"
    OLLAMA_TIMEOUT = "ollama_timeout"
    OLLAMA_EMPTY_RESPONSE = "ollama_empty_response"
    OLLAMA_CIRCUIT_BREAKER = "ollama_circuit_breaker"
    REPAIR_EXHAUSTED = "repair_exhausted"
    SPLICER_MISMATCH = "splicer_mismatch"
    TIER_ESCALATION = "tier_escalation"
    AST_FAILURE = "ast_failure"
    SIZE_REGRESSION = "size_regression"
    GENERATION_ERROR = "generation_error"
    DEPENDENCY_BLOCKED = "dependency_blocked"
    UNKNOWN = "unknown"


class PipelineStage(str, Enum):
    """Pipeline stage where a failure originated."""

    SKELETON = "skeleton"
    CLASSIFICATION = "classification"
    TEMPLATE = "template"
    OLLAMA_GENERATION = "ollama_generation"
    REPAIR = "repair"
    SPLICER = "splicer"
    FALLBACK = "fallback"
    INTEGRATION = "integration"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Root Cause Classifier
# ---------------------------------------------------------------------------

# Compiled patterns mapping error strings to (RootCause, PipelineStage)
_ERROR_PATTERNS: List[Tuple[re.Pattern, RootCause, PipelineStage]] = [
    (re.compile(r"F811|redefinition of unused", re.IGNORECASE),
     RootCause.DUPLICATE_IMPORT, PipelineStage.REPAIR),
    (re.compile(r"NotImplementedError|unfilled stub", re.IGNORECASE),
     RootCause.UNFILLED_STUB, PipelineStage.OLLAMA_GENERATION),
    (re.compile(r"nested class|scope corruption|unexpected indent", re.IGNORECASE),
     RootCause.SCOPE_CORRUPTION, PipelineStage.SPLICER),
    (re.compile(r"phantom import|no module named|cannot import", re.IGNORECASE),
     RootCause.PHANTOM_IMPORT, PipelineStage.OLLAMA_GENERATION),
    (re.compile(r"skeleton.*missing|no skeleton|skeleton not found", re.IGNORECASE),
     RootCause.SKELETON_MISSING, PipelineStage.SKELETON),
    (re.compile(r"timeout|timed out", re.IGNORECASE),
     RootCause.OLLAMA_TIMEOUT, PipelineStage.OLLAMA_GENERATION),
    (re.compile(r"empty response|no response", re.IGNORECASE),
     RootCause.OLLAMA_EMPTY_RESPONSE, PipelineStage.OLLAMA_GENERATION),
    (re.compile(r"circuit.?breaker", re.IGNORECASE),
     RootCause.OLLAMA_CIRCUIT_BREAKER, PipelineStage.OLLAMA_GENERATION),
    (re.compile(r"repair exhausted|max repair", re.IGNORECASE),
     RootCause.REPAIR_EXHAUSTED, PipelineStage.REPAIR),
    (re.compile(r"splice|splicer.*mismatch", re.IGNORECASE),
     RootCause.SPLICER_MISMATCH, PipelineStage.SPLICER),
    (re.compile(r"size regression|size.*guard|file.*too large", re.IGNORECASE),
     RootCause.SIZE_REGRESSION, PipelineStage.INTEGRATION),
    (re.compile(r"ast.*fail|syntax error|invalid syntax", re.IGNORECASE),
     RootCause.AST_FAILURE, PipelineStage.REPAIR),
    (re.compile(r"blocked by.*dependency|dependency.*failed", re.IGNORECASE),
     RootCause.DEPENDENCY_BLOCKED, PipelineStage.INTEGRATION),
    (re.compile(r"generation.*error|generation.*fail", re.IGNORECASE),
     RootCause.GENERATION_ERROR, PipelineStage.OLLAMA_GENERATION),
    # Agent API contract errors — TypeError/unexpected keyword from
    # mismatched agent.generate() signatures (Run-027: 'stop' kwarg).
    (re.compile(r"unexpected keyword argument|TypeError.*agenerate|TypeError.*generate", re.IGNORECASE),
     RootCause.GENERATION_ERROR, PipelineStage.OLLAMA_GENERATION),
    # Catch-all: "Exception during code generation" wrapper from
    # develop_feature()'s except block — the real error is in the suffix.
    (re.compile(r"Exception during code generation", re.IGNORECASE),
     RootCause.GENERATION_ERROR, PipelineStage.OLLAMA_GENERATION),
]

# Maps EscalationReason string values to (RootCause, PipelineStage)
_ESCALATION_MAP: Dict[str, Tuple[RootCause, PipelineStage]] = {
    "ast_failure": (RootCause.AST_FAILURE, PipelineStage.REPAIR),
    "structural_mismatch": (RootCause.SPLICER_MISMATCH, PipelineStage.SPLICER),
    "semantic_failure": (RootCause.GENERATION_ERROR, PipelineStage.REPAIR),
    "ollama_unavailable": (RootCause.OLLAMA_TIMEOUT, PipelineStage.OLLAMA_GENERATION),
    "tier_too_high": (RootCause.TIER_ESCALATION, PipelineStage.CLASSIFICATION),
    "repair_exhausted": (RootCause.REPAIR_EXHAUSTED, PipelineStage.REPAIR),
    "empty_response": (RootCause.OLLAMA_EMPTY_RESPONSE, PipelineStage.OLLAMA_GENERATION),
    "timeout": (RootCause.OLLAMA_TIMEOUT, PipelineStage.OLLAMA_GENERATION),
    "circuit_breaker": (RootCause.OLLAMA_CIRCUIT_BREAKER, PipelineStage.OLLAMA_GENERATION),
}


class RootCauseClassifier:
    """Classifies failures into root causes and pipeline stages."""

    def classify_feature(
        self,
        feature_dict: Dict[str, Any],
        history_entry: Optional[Dict[str, Any]] = None,
    ) -> Tuple[RootCause, PipelineStage]:
        """Classify a feature-level failure from its state and history."""
        error_msg = feature_dict.get("error_message", "") or ""
        if history_entry:
            error_msg = error_msg or history_entry.get("error", "") or ""

        if error_msg:
            for pattern, cause, stage in _ERROR_PATTERNS:
                if pattern.search(error_msg):
                    return cause, stage

        status = feature_dict.get("status", "")
        if status == "blocked":
            return RootCause.DEPENDENCY_BLOCKED, PipelineStage.INTEGRATION

        return RootCause.UNKNOWN, PipelineStage.UNKNOWN

    def classify_element(
        self, element_dict: Dict[str, Any]
    ) -> Tuple[RootCause, PipelineStage]:
        """Classify an element-level failure from micro-prime results."""
        escalation = element_dict.get("escalation")
        if escalation:
            reason = escalation.get("reason", "")
            mapped = _ESCALATION_MAP.get(reason)
            if mapped:
                return mapped

        if not element_dict.get("success", True):
            # Try last_error from escalation
            last_error = ""
            if escalation:
                last_error = escalation.get("last_error", "") or ""
            if last_error:
                for pattern, cause, stage in _ERROR_PATTERNS:
                    if pattern.search(last_error):
                        return cause, stage
            return RootCause.GENERATION_ERROR, PipelineStage.OLLAMA_GENERATION

        return RootCause.UNKNOWN, PipelineStage.UNKNOWN

    def classify_from_code(
        self, code: str, error: str = ""
    ) -> Tuple[RootCause, PipelineStage]:
        """Classify from generated code content and lint errors."""
        combined = f"{code}\n{error}"

        if re.search(r"F811|redefinition of unused", combined, re.IGNORECASE):
            return RootCause.DUPLICATE_IMPORT, PipelineStage.REPAIR

        if "NotImplementedError" in code and "raise NotImplementedError" in code:
            return RootCause.UNFILLED_STUB, PipelineStage.OLLAMA_GENERATION

        if re.search(r"from\s+\S+\s+import\s+\S+", code):
            # Check for phantom imports in error
            if re.search(r"no module named|cannot import", error, re.IGNORECASE):
                return RootCause.PHANTOM_IMPORT, PipelineStage.OLLAMA_GENERATION

        if re.search(r"class\s+\w+.*:\s*\n\s+class\s+\w+", code):
            return RootCause.SCOPE_CORRUPTION, PipelineStage.SPLICER

        return RootCause.UNKNOWN, PipelineStage.UNKNOWN


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class ElementPostMortem:
    """Post-mortem analysis for a single code element."""

    element_name: str
    file_path: str
    tier: str
    success: bool
    root_cause: RootCause = RootCause.UNKNOWN
    pipeline_stage: PipelineStage = PipelineStage.UNKNOWN
    escalation_reason: str = ""
    template_used: bool = False
    repair_steps: List[str] = dataclasses.field(default_factory=list)
    generation_time_ms: float = 0.0


@dataclasses.dataclass
class FeaturePostMortem:
    """Post-mortem analysis for a single feature."""

    feature_id: str
    name: str
    status: str
    success: bool
    cost_usd: float = 0.0
    root_cause: RootCause = RootCause.UNKNOWN
    pipeline_stage: PipelineStage = PipelineStage.UNKNOWN
    error_message: str = ""
    target_files: List[str] = dataclasses.field(default_factory=list)
    generated_files: List[str] = dataclasses.field(default_factory=list)
    missing_files: List[str] = dataclasses.field(default_factory=list)
    elements: List[ElementPostMortem] = dataclasses.field(default_factory=list)
    anti_patterns: List[str] = dataclasses.field(default_factory=list)
    requirement_score: float = 0.0
    verdict: str = ""
    force_regenerated: bool = False
    disk_compliance: Optional[Any] = None  # DiskComplianceResult when available
    disk_quality_score: Optional[float] = None
    assembly_delta: Optional[float] = None


@dataclasses.dataclass
class CrossFeaturePattern:
    """A recurring pattern across multiple features."""

    pattern_type: str
    description: str
    affected_features: List[str] = dataclasses.field(default_factory=list)
    frequency: int = 0
    severity: str = "medium"
    # For escalation patterns: distinct feature count separate from element
    # frequency (REQ-KZ-401a). Defaults to len(affected_features) when not set.
    affected_feature_count: int = 0


@dataclasses.dataclass
class PipelineStageAttribution:
    """Failure attribution to a pipeline stage."""

    stage: PipelineStage
    failure_count: int = 0
    element_count: int = 0
    root_causes: Dict[str, int] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class MicroPrimeAnalysis:
    """Aggregated micro-prime engine statistics."""

    total_elements: int = 0
    successful_elements: int = 0
    escalated_elements: int = 0
    tier_distribution: Dict[str, int] = dataclasses.field(default_factory=dict)
    escalation_reasons: Dict[str, int] = dataclasses.field(default_factory=dict)
    repair_step_distribution: Dict[str, int] = dataclasses.field(default_factory=dict)
    avg_generation_time_ms: float = 0.0


@dataclasses.dataclass
class CostSummary:
    """Cost summary across all features."""

    total_usd: float = 0.0
    per_feature: Dict[str, float] = dataclasses.field(default_factory=dict)
    avg_per_feature: float = 0.0
    max_feature: str = ""
    max_usd: float = 0.0


@dataclasses.dataclass
class PrimePostMortemReport:
    """Top-level post-mortem report for a PrimeContractor run."""

    report_id: str
    timestamp: str
    total_features: int = 0
    successful_features: int = 0
    failed_features: int = 0
    aggregate_score: float = 0.0
    aggregate_verdict: str = ""
    features: List[FeaturePostMortem] = dataclasses.field(default_factory=list)
    pipeline_attribution: List[PipelineStageAttribution] = dataclasses.field(
        default_factory=list
    )
    micro_prime_analysis: Optional[MicroPrimeAnalysis] = None
    cross_feature_patterns: List[CrossFeaturePattern] = dataclasses.field(
        default_factory=list
    )
    lessons: List[Lesson] = dataclasses.field(default_factory=list)
    cost_summary: Optional[CostSummary] = None
    avg_assembly_delta: Optional[float] = None


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Disk quality scoring (Phase E — Kaizen Quality)
# ---------------------------------------------------------------------------


def compute_disk_quality_score(compliance: Any) -> float:
    """Compute a composite disk quality score from DiskComplianceResult.

    Formula:
        composite = (contract_compliance × 0.4) + (import_completeness × 0.2)
                  + (stub_penalty × 0.2) + (semantic_penalty × 0.2)

    Args:
        compliance: DiskComplianceResult instance.

    Returns:
        Float score in [0.0, 1.0].
    """
    if compliance is None:
        return 0.0
    if not getattr(compliance, "ast_valid", True):
        return 0.0

    contract_compliance = getattr(compliance, "contract_compliance", 1.0)
    import_completeness = getattr(compliance, "import_completeness", 1.0)
    stubs = getattr(compliance, "stubs_remaining", 0)
    semantic_issues = getattr(compliance, "semantic_issues", [])
    semantic_count = len(semantic_issues) if semantic_issues else 0

    stub_penalty = max(0.0, 1.0 - stubs * 0.1)
    semantic_penalty = max(0.0, 1.0 - semantic_count * 0.15)

    composite = (
        contract_compliance * 0.4
        + import_completeness * 0.2
        + stub_penalty * 0.2
        + semantic_penalty * 0.2
    )
    return max(0.0, min(1.0, composite))


# ---------------------------------------------------------------------------
# Kaizen suggestion generation (Phase C — moved from scripts/)
# ---------------------------------------------------------------------------

# All 16 RootCause values mapped to prompt hints.
CAUSE_TO_SUGGESTION: Dict[str, Dict[str, str]] = {
    "duplicate_import": {
        "phase": "draft",
        "hint": "Check for existing imports before adding new ones. Deduplicate at file top.",
    },
    "unfilled_stub": {
        "phase": "draft",
        "hint": "Replace every stub/placeholder with real implementation before returning.",
    },
    "scope_corruption": {
        "phase": "draft",
        "hint": "Preserve the existing function and class structure. Do not reorganize scopes.",
    },
    "phantom_import": {
        "phase": "draft",
        "hint": "Validate all imports exist in the target project before referencing them.",
    },
    "indentation_error": {
        "phase": "draft",
        "hint": "Match the indentation style of the surrounding file exactly.",
    },
    "splicer_mismatch": {
        "phase": "draft",
        "hint": "Ensure generated code anchors (function/class names) match the target file exactly.",
    },
    "tier_escalation": {
        "phase": "spec",
        "hint": "Decompose complex features into smaller, independently implementable units.",
    },
    "ast_failure": {
        "phase": "draft",
        "hint": "Emit syntactically valid Python at all times; run a mental parse check before returning.",
    },
    "size_regression": {
        "phase": "draft",
        "hint": "Do not generate significantly more lines than the original file; prefer surgical edits.",
    },
    "generation_error": {
        "phase": "draft",
        "hint": "If generation fails, emit a minimal valid stub rather than an error string.",
    },
    "skeleton_missing": {
        "phase": "spec",
        "hint": "Ensure skeleton files are generated before code generation begins.",
    },
    "ollama_timeout": {
        "phase": "spec",
        "hint": "Reduce element scope to fit within generation time budgets. Split large elements.",
    },
    "ollama_empty_response": {
        "phase": "draft",
        "hint": "Always return code content. If unsure, emit a minimal valid stub rather than nothing.",
    },
    "ollama_circuit_breaker": {
        "phase": "spec",
        "hint": "Reduce batch size or complexity to stay within circuit breaker thresholds.",
    },
    "repair_exhausted": {
        "phase": "draft",
        "hint": "Generate cleaner code that requires fewer repair steps. Match target file conventions exactly.",
    },
    "dependency_blocked": {
        "phase": "spec",
        "hint": "Declare dependencies explicitly in the spec so blocked features are skipped early.",
    },
    "unknown": {
        "phase": "draft",
        "hint": "Inspect the failure message and add a targeted fix rather than regenerating the whole file.",
    },
    "repeated_escalation:ast_failure": {
        "phase": "draft",
        "hint": "Emit syntactically valid Python; run a mental parse check. If generating function bodies, always include the def line.",
    },
    "repeated_escalation:tier_too_high": {
        "phase": "spec",
        "hint": "Decompose into simpler sub-elements; complex features need finer granularity in the spec.",
    },
    "repeated_escalation:not_decomposable": {
        "phase": "spec",
        "hint": "Elements that resist decomposition may need manual splitting or should be routed to cloud-tier generation.",
    },
    "repeated_escalation:structural_mismatch": {
        "phase": "draft",
        "hint": "Match the exact class/function structure of the target file. Do not reorganize or rename anchors.",
    },
    "repeated_escalation:empty_response": {
        "phase": "draft",
        "hint": "Always return code content. If unsure, emit a minimal valid stub rather than nothing.",
    },
    "repeated_escalation:timeout": {
        "phase": "spec",
        "hint": "Reduce element scope to fit within generation time budgets. Split large elements.",
    },
    "repeated_escalation:repair_exhausted": {
        "phase": "draft",
        "hint": "Generate cleaner code that requires fewer repair steps. Match target file conventions exactly.",
    },
    "repeated_escalation:circuit_breaker": {
        "phase": "spec",
        "hint": "Reduce batch size or complexity to stay within circuit breaker thresholds.",
    },
}


def generate_kaizen_suggestions(report: Any) -> List[Dict[str, Any]]:
    """Generate structured improvement suggestions from a post-mortem report.

    Args:
        report: PrimePostMortemReport instance.

    Returns:
        List of suggestion dicts with pattern, hint, phase, confidence.
    """
    suggestions: List[Dict[str, Any]] = []
    for pattern in getattr(report, "cross_feature_patterns", []) or []:
        if getattr(pattern, "frequency", 0) < 2:
            continue
        pattern_type = getattr(pattern, "pattern_type", None)
        template = CAUSE_TO_SUGGESTION.get(pattern_type)
        if not template:
            continue
        suggestions.append({
            "pattern": getattr(pattern, "description", ""),
            "pattern_type": pattern_type,
            "frequency": pattern.frequency,
            "suggested_action": template["hint"],
            "config_key": "prompt_hints",
            "phase": template["phase"],
            "confidence": "high" if pattern.frequency >= 3 else "medium",
            "auto_applicable": False,
        })
    return suggestions


class PrimePostMortemEvaluator:
    """Evaluates PrimeContractor run results into structured post-mortem reports."""

    def __init__(self) -> None:
        self._classifier = RootCauseClassifier()
        self._sanitizer = Sanitizer()
        self._anti_pattern_detector = AntiPatternDetector()

    def evaluate(
        self,
        result_dict: Dict[str, Any],
        queue_state: Dict[str, Any],
        seed_tasks: Optional[List[Dict]] = None,
        output_dir: str = ".",
        force_regenerated_ids: Optional[Set[str]] = None,
        project_root: Optional[str] = None,
        forward_manifest: Optional[Any] = None,
    ) -> PrimePostMortemReport:
        """Evaluate a PrimeContractor run and produce a post-mortem report.

        Args:
            result_dict: The result dictionary from PrimeContractor.run().
            queue_state: Serialized queue state {feature_id: feature_dict}.
            seed_tasks: Optional list of seed task dicts for requirement matching.
            output_dir: Directory for report output files.

        Returns:
            PrimePostMortemReport with per-feature analysis, patterns, and lessons.
        """
        report = PrimePostMortemReport(
            report_id=str(uuid.uuid4()),
            timestamp=datetime.datetime.now().isoformat(),
        )

        # Build history lookup from result_dict
        history = result_dict.get("history", [])
        history_by_id: Dict[str, Dict] = {}
        for entry in history:
            fid = entry.get("feature_id", "")
            if fid:
                history_by_id[fid] = entry

        # Only evaluate features that were actually processed in this run
        processed_ids = set(history_by_id.keys())

        # Build seed task lookup
        seed_by_id: Dict[str, Dict] = {}
        if seed_tasks:
            for task in seed_tasks:
                tid = task.get("task_id", task.get("id", ""))
                if tid:
                    seed_by_id[tid] = task

        # Evaluate each processed feature
        all_elements: List[ElementPostMortem] = []
        for fid in processed_ids:
            feature_dict = queue_state.get(fid, {})
            hist_entry = history_by_id.get(fid)
            seed_task = seed_by_id.get(fid)

            try:
                is_force_regen = (
                    fid in force_regenerated_ids if force_regenerated_ids else False
                )
                fpm = self._evaluate_feature(
                    feature_dict, hist_entry, seed_task, fid,
                    force_regenerated=is_force_regen,
                )
                report.features.append(fpm)
                all_elements.extend(fpm.elements)
            except Exception:
                logger.warning("Error evaluating feature %s", fid, exc_info=True)
                # Create a minimal entry so the feature isn't silently dropped
                fd = feature_dict if isinstance(feature_dict, dict) else {}
                report.features.append(FeaturePostMortem(
                    feature_id=fid,
                    name=fd.get("name", fid),
                    status=fd.get("status", "unknown"),
                    success=False,
                    error_message="Post-mortem evaluation error",
                    root_cause=RootCause.UNKNOWN,
                    pipeline_stage=PipelineStage.UNKNOWN,
                    verdict="ERROR",
                ))

        # Aggregate metrics
        report.total_features = len(report.features)
        report.successful_features = sum(1 for f in report.features if f.success)
        report.failed_features = report.total_features - report.successful_features

        if report.total_features > 0:
            report.aggregate_score = report.successful_features / report.total_features
        else:
            report.aggregate_score = 0.0

        if report.aggregate_score >= _PASS_THRESHOLD:
            report.aggregate_verdict = "PASS"
        elif report.aggregate_score >= _PARTIAL_THRESHOLD:
            report.aggregate_verdict = "PARTIAL"
        else:
            report.aggregate_verdict = "FAIL"

        # Build pipeline attribution
        report.pipeline_attribution = self._build_pipeline_attribution(report.features)

        # Build micro-prime analysis if element data available
        if all_elements:
            report.micro_prime_analysis = self._build_micro_prime_analysis(all_elements)

        # Detect cross-feature patterns
        report.cross_feature_patterns = self._detect_cross_feature_patterns(
            report.features
        )

        # Build cost summary
        report.cost_summary = self._build_cost_summary(report.features)

        # Disk quality evaluation (opt-in when project_root provided)
        if project_root:
            self._evaluate_disk_quality(report.features, project_root, forward_manifest)
            # Compute avg_assembly_delta across features that have disk scores
            deltas = [
                f.assembly_delta for f in report.features
                if f.assembly_delta is not None
            ]
            if deltas:
                report.avg_assembly_delta = sum(deltas) / len(deltas)
                # Cross-feature pattern: large assembly quality gap
                large_gaps = [
                    f.feature_id for f in report.features
                    if f.assembly_delta is not None and f.assembly_delta > 0.2
                ]
                if len(large_gaps) >= 2:
                    report.cross_feature_patterns.append(CrossFeaturePattern(
                        pattern_type="assembly_quality_gap",
                        description=(
                            f"Assembly degrades quality by >0.2 in "
                            f"{len(large_gaps)} features"
                        ),
                        affected_features=large_gaps,
                        frequency=len(large_gaps),
                        severity="high" if len(large_gaps) >= 3 else "medium",
                    ))

        # Extract lessons
        report.lessons = self._extract_lessons(report)

        # Write outputs
        try:
            self._write_outputs(report, output_dir)
        except Exception:
            logger.warning("Failed to write postmortem outputs", exc_info=True)

        return report

    # -- Private helpers ----------------------------------------------------

    def _evaluate_feature(
        self,
        feature_dict: Dict[str, Any],
        history_entry: Optional[Dict[str, Any]],
        seed_task: Optional[Dict[str, Any]],
        fallback_id: str = "",
        force_regenerated: bool = False,
    ) -> FeaturePostMortem:
        """Evaluate a single feature."""
        fid = feature_dict.get("id", fallback_id)
        name = feature_dict.get("name", fid)
        status = feature_dict.get("status", "")
        # Prefer history entry's authoritative success field when available;
        # fall back to queue-state status for backward compatibility.
        if history_entry is not None and "success" in history_entry:
            success = bool(history_entry["success"])
        else:
            success = status == "complete"

        # Determine root cause for failures
        root_cause = RootCause.UNKNOWN
        pipeline_stage = PipelineStage.UNKNOWN
        if not success:
            root_cause, pipeline_stage = self._classifier.classify_feature(
                feature_dict, history_entry
            )

        # Extract cost from history
        cost_usd = 0.0
        if history_entry:
            cost_usd = history_entry.get("cost_usd", 0.0) or 0.0

        # File coverage — generated_files are often absolute paths while
        # target_files are relative, so check suffix match (endswith) to
        # handle the path-prefix mismatch.
        target_files = feature_dict.get("target_files", [])
        generated_files = feature_dict.get("generated_files", [])
        missing_files = [
            f for f in target_files
            if not any(
                g == f or g.endswith("/" + f)
                for g in generated_files
            )
        ]

        # Element analysis from micro-prime metadata
        elements: List[ElementPostMortem] = []
        gen_meta = (history_entry or {}).get("generation_metadata", {})
        file_results = gen_meta.get("micro_prime_file_results", [])
        for fr in file_results:
            for er in fr.get("element_results", []):
                elem_success = er.get("success", True)
                elem_cause = RootCause.UNKNOWN
                elem_stage = PipelineStage.UNKNOWN
                escalation_reason = ""

                if not elem_success:
                    elem_cause, elem_stage = self._classifier.classify_element(er)
                    esc = er.get("escalation")
                    if esc:
                        escalation_reason = esc.get("reason", "")

                elements.append(ElementPostMortem(
                    element_name=er.get("element_name", ""),
                    file_path=er.get("file_path", fr.get("file_path", "")),
                    tier=er.get("tier", "unknown"),
                    success=elem_success,
                    root_cause=elem_cause,
                    pipeline_stage=elem_stage,
                    escalation_reason=escalation_reason,
                    template_used=er.get("template_used", False),
                    repair_steps=er.get("repair_steps_applied", []),
                    generation_time_ms=er.get("generation_time_ms", 0.0),
                ))

        # Requirement matching — incorporate element-level success rate
        # when micro-prime elements are present.
        element_success_ratio = 1.0
        if elements:
            successful_elements = sum(1 for e in elements if e.success)
            element_success_ratio = successful_elements / len(elements)

        if success:
            # Feature status is "complete" but element failures should
            # reduce the score proportionally.
            requirement_score = element_success_ratio
        elif seed_task:
            requirement_score = self._score_requirements(seed_task, feature_dict)
        else:
            requirement_score = 0.0

        # Per-feature verdict — element success ratio gates the verdict
        # even when the feature status is "complete".
        if success and element_success_ratio >= 0.8:
            verdict = "PASS"
        elif success and element_success_ratio >= 0.5:
            verdict = "PARTIAL"
        elif success:
            verdict = "FAIL:low_element_fill_rate"
        elif root_cause != RootCause.UNKNOWN:
            verdict = f"FAIL:{root_cause.value}"
        else:
            verdict = "FAIL"

        return FeaturePostMortem(
            feature_id=fid,
            name=name,
            status=status,
            success=success,
            cost_usd=cost_usd,
            root_cause=root_cause,
            pipeline_stage=pipeline_stage,
            error_message=feature_dict.get("error_message", "") or "",
            target_files=target_files,
            generated_files=generated_files,
            missing_files=missing_files,
            elements=elements,
            requirement_score=requirement_score,
            verdict=verdict,
            force_regenerated=force_regenerated,
        )

    def _score_requirements(
        self, seed_task: Dict[str, Any], feature_dict: Dict[str, Any]
    ) -> float:
        """Score how well a feature met its requirements (0.0-1.0)."""
        try:
            from .postmortem import _extract_requirement_keywords
        except ImportError:
            return 0.0

        keywords = _extract_requirement_keywords(seed_task)
        if not keywords:
            return 0.0

        description = feature_dict.get("description", "") or ""
        error_msg = feature_dict.get("error_message", "") or ""
        combined = f"{description}\n{error_msg}".lower()

        matched = sum(1 for kw in keywords if kw in combined)
        return matched / len(keywords) if keywords else 0.0

    def _evaluate_disk_quality(
        self,
        features: List[FeaturePostMortem],
        project_root: str,
        forward_manifest: Optional[Any] = None,
    ) -> None:
        """Evaluate disk compliance and compute quality scores for each feature.

        Mutates feature objects in-place to add disk_compliance,
        disk_quality_score, and assembly_delta fields.
        """
        try:
            from startd8.forward_manifest_validator import validate_disk_compliance
        except ImportError:
            logger.debug("Disk validation unavailable — skipping")
            return

        for fpm in features:
            # Prefer generated_files (absolute paths to actual output) over
            # target_files (relative paths that may not exist at project root).
            files_to_check = fpm.generated_files if fpm.generated_files else fpm.target_files
            for file_path in files_to_check:
                try:
                    abs_file = Path(file_path)
                    root_path = Path(project_root)
                    if abs_file.is_absolute():
                        # If the path is under project_root, make it relative
                        # so validate_disk_compliance resolves correctly.
                        try:
                            relative = abs_file.relative_to(root_path)
                            effective_root = project_root
                            effective_file = str(relative)
                        except ValueError:
                            # Path outside project_root (e.g. in generated/ dir)
                            # — use parent as root, filename as file.
                            effective_root = str(abs_file.parent)
                            effective_file = abs_file.name
                    else:
                        effective_root = project_root
                        effective_file = file_path
                    compliance = validate_disk_compliance(
                        effective_file, effective_root, forward_manifest,
                    )
                    fpm.disk_compliance = compliance

                    # Compute disk quality score
                    fpm.disk_quality_score = compute_disk_quality_score(compliance)

                    # Assembly delta: quality_score (from elements) - disk_quality_score
                    if fpm.disk_quality_score is not None:
                        fpm.assembly_delta = fpm.requirement_score - fpm.disk_quality_score
                except Exception as exc:
                    logger.debug(
                        "Disk validation failed for %s in %s: %s",
                        file_path, fpm.feature_id, exc,
                    )

    def _build_pipeline_attribution(
        self, features: List[FeaturePostMortem]
    ) -> List[PipelineStageAttribution]:
        """Aggregate failures by pipeline stage."""
        stage_data: Dict[PipelineStage, PipelineStageAttribution] = {}

        for fpm in features:
            if fpm.success:
                continue

            stage = fpm.pipeline_stage
            if stage not in stage_data:
                stage_data[stage] = PipelineStageAttribution(stage=stage)
            attr = stage_data[stage]
            attr.failure_count += 1
            cause_key = fpm.root_cause.value
            attr.root_causes[cause_key] = attr.root_causes.get(cause_key, 0) + 1

            # Also count element-level attributions
            for elem in fpm.elements:
                if not elem.success:
                    e_stage = elem.pipeline_stage
                    if e_stage not in stage_data:
                        stage_data[e_stage] = PipelineStageAttribution(stage=e_stage)
                    stage_data[e_stage].element_count += 1

        return sorted(stage_data.values(), key=lambda a: a.failure_count, reverse=True)

    def _build_micro_prime_analysis(
        self, elements: List[ElementPostMortem]
    ) -> MicroPrimeAnalysis:
        """Aggregate element-level micro-prime statistics."""
        analysis = MicroPrimeAnalysis()
        analysis.total_elements = len(elements)
        analysis.successful_elements = sum(1 for e in elements if e.success)
        analysis.escalated_elements = sum(
            1 for e in elements if e.escalation_reason
        )

        # Tier distribution
        tier_counter: Counter = Counter()
        esc_counter: Counter = Counter()
        repair_counter: Counter = Counter()
        total_time = 0.0

        for elem in elements:
            tier_counter[elem.tier] += 1
            if elem.escalation_reason:
                esc_counter[elem.escalation_reason] += 1
            for step in elem.repair_steps:
                repair_counter[step] += 1
            total_time += elem.generation_time_ms

        analysis.tier_distribution = dict(tier_counter)
        analysis.escalation_reasons = dict(esc_counter)
        analysis.repair_step_distribution = dict(repair_counter)
        if elements:
            analysis.avg_generation_time_ms = total_time / len(elements)

        return analysis

    def _detect_cross_feature_patterns(
        self, features: List[FeaturePostMortem]
    ) -> List[CrossFeaturePattern]:
        """Detect recurring patterns across features."""
        patterns: List[CrossFeaturePattern] = []

        # Pattern 1: Repeated root cause
        cause_features: Dict[RootCause, List[str]] = {}
        for fpm in features:
            if not fpm.success and fpm.root_cause != RootCause.UNKNOWN:
                cause_features.setdefault(fpm.root_cause, []).append(fpm.feature_id)

        for cause, fids in cause_features.items():
            if len(fids) >= _CROSS_FEATURE_PATTERN_MIN:
                patterns.append(CrossFeaturePattern(
                    pattern_type="repeated_root_cause",
                    description=(
                        f"Root cause '{cause.value}' repeated across "
                        f"{len(fids)} features"
                    ),
                    affected_features=fids,
                    frequency=len(fids),
                    severity="high" if len(fids) >= 3 else "medium",
                ))

        # Pattern 2: Repeated escalation reason — subtyped by reason (REQ-KZ-401a)
        # Track both element count (total escalations) and feature count separately.
        esc_elements: Dict[str, int] = {}       # reason → total element escalations
        esc_feature_sets: Dict[str, List[str]] = {}  # reason → feature IDs (with dupes)
        for fpm in features:
            for elem in fpm.elements:
                if elem.escalation_reason:
                    reason = elem.escalation_reason
                    esc_elements[reason] = esc_elements.get(reason, 0) + 1
                    esc_feature_sets.setdefault(reason, []).append(fpm.feature_id)

        for reason, fids in esc_feature_sets.items():
            unique_fids = list(dict.fromkeys(fids))
            element_count = esc_elements[reason]
            # Dual threshold: enough features AND enough total elements
            if (len(unique_fids) >= _ESCALATION_MIN_FEATURES
                    and element_count >= _ESCALATION_MIN_ELEMENTS):
                # Dynamic severity based on scope
                if len(unique_fids) >= 5 or element_count >= 10:
                    severity = "high"
                else:
                    severity = "medium"
                patterns.append(CrossFeaturePattern(
                    pattern_type=f"repeated_escalation:{reason}",
                    description=(
                        f"Escalation reason '{reason}': {element_count} elements "
                        f"across {len(unique_fids)} features"
                    ),
                    affected_features=unique_fids,
                    frequency=element_count,
                    severity=severity,
                    affected_feature_count=len(unique_fids),
                ))

        # Pattern 3: Cost outliers
        costs = [f.cost_usd for f in features if f.cost_usd > 0]
        if costs:
            avg_cost = sum(costs) / len(costs)
            if avg_cost > 0:
                outliers = [
                    f.feature_id
                    for f in features
                    if f.cost_usd >= avg_cost * _COST_OUTLIER_FACTOR
                ]
                if outliers:
                    patterns.append(CrossFeaturePattern(
                        pattern_type="cost_outlier",
                        description=(
                            f"{len(outliers)} feature(s) cost {_COST_OUTLIER_FACTOR}x+ "
                            f"average (${avg_cost:.4f})"
                        ),
                        affected_features=outliers,
                        frequency=len(outliers),
                        severity="low",
                    ))

        return patterns

    def _build_cost_summary(
        self, features: List[FeaturePostMortem]
    ) -> CostSummary:
        """Build cost summary from feature data."""
        summary = CostSummary()
        for fpm in features:
            summary.per_feature[fpm.feature_id] = fpm.cost_usd
            summary.total_usd += fpm.cost_usd
            if fpm.cost_usd > summary.max_usd:
                summary.max_usd = fpm.cost_usd
                summary.max_feature = fpm.feature_id

        if features:
            summary.avg_per_feature = summary.total_usd / len(features)

        return summary

    def _extract_lessons(self, report: PrimePostMortemReport) -> List[Lesson]:
        """Convert patterns and failures into lessons."""
        lessons: List[Lesson] = []
        now = datetime.datetime.now().isoformat()

        # Lesson from each cross-feature pattern
        for pattern in report.cross_feature_patterns:
            severity = Severity.HIGH if pattern.severity == "high" else Severity.MEDIUM
            lessons.append(Lesson(
                lesson_id=str(uuid.uuid4()),
                title=f"Pattern: {pattern.description}",
                description=(
                    f"{pattern.pattern_type}: {pattern.description}. "
                    f"Affected features: {', '.join(pattern.affected_features)}"
                ),
                category=LessonCategory.PROCESS,
                severity=severity,
                tags=["prime-contractor", "cross-feature", pattern.pattern_type],
                source_phase="prime-postmortem",
                source_context={"report_id": report.report_id},
                created_at=now,
            ))

        # Lesson from dominant pipeline stage
        if report.pipeline_attribution:
            top_stage = report.pipeline_attribution[0]
            if top_stage.failure_count >= 2:
                lessons.append(Lesson(
                    lesson_id=str(uuid.uuid4()),
                    title=(
                        f"Pipeline stage '{top_stage.stage.value}' is the "
                        f"primary failure point ({top_stage.failure_count} failures)"
                    ),
                    description=(
                        f"Root causes at this stage: "
                        f"{json.dumps(top_stage.root_causes)}"
                    ),
                    category=LessonCategory.ARCHITECTURE,
                    severity=Severity.HIGH,
                    tags=["prime-contractor", "pipeline-attribution", top_stage.stage.value],
                    source_phase="prime-postmortem",
                    source_context={"report_id": report.report_id},
                    created_at=now,
                ))

        # Sanitize lessons
        lessons = self._sanitizer.sanitize_lessons(lessons)

        return lessons

    def _write_outputs(self, report: PrimePostMortemReport, output_dir: str) -> None:
        """Write report files to output directory."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # JSON report
        report_path = out / "prime-postmortem-report.json"
        report_dict = dataclasses.asdict(report)
        # Convert enums to their values for JSON serialization
        report_json = json.dumps(report_dict, indent=2, default=str)
        report_path.write_text(report_json, encoding="utf-8")
        logger.info("Post-mortem report: %s", report_path)

        # Markdown summary
        md_path = out / "prime-postmortem-summary.md"
        md_content = self._render_markdown(report)
        md_path.write_text(md_content, encoding="utf-8")
        logger.info("Post-mortem summary: %s", md_path)

        # Lessons JSON
        if report.lessons:
            lessons_path = out / "prime-postmortem-lessons.json"
            lessons_data = [dataclasses.asdict(ln) for ln in report.lessons]
            lessons_json = json.dumps(lessons_data, indent=2, default=str)
            lessons_path.write_text(lessons_json, encoding="utf-8")
            logger.info("Post-mortem lessons: %s", lessons_path)

    def _render_markdown(self, report: PrimePostMortemReport) -> str:
        """Render the report as markdown."""
        lines = [
            "# Prime Contractor Post-Mortem Report",
            "",
            f"**Report ID:** {report.report_id}",
            f"**Timestamp:** {report.timestamp}",
            f"**Score:** {report.aggregate_score:.2f}",
            f"**Verdict:** {report.aggregate_verdict}",
            "",
            "## Summary",
            "",
            f"- Total features: {report.total_features}",
            f"- Successful: {report.successful_features}",
            f"- Failed: {report.failed_features}",
            "",
        ]

        # Pipeline Attribution
        if report.pipeline_attribution:
            lines.extend([
                "## Pipeline Attribution",
                "",
                "| Stage | Failures | Root Causes |",
                "|-------|----------|-------------|",
            ])
            for attr in report.pipeline_attribution:
                causes_str = ", ".join(
                    f"{k}({v})" for k, v in attr.root_causes.items()
                )
                lines.append(
                    f"| {attr.stage.value} | {attr.failure_count} | {causes_str} |"
                )
            lines.append("")

        # Failed Features
        failed = [f for f in report.features if not f.success]
        if failed:
            lines.extend(["## Failed Features", ""])
            for fpm in failed:
                lines.extend([
                    f"### {fpm.name} (`{fpm.feature_id}`)",
                    "",
                    f"- **Root cause:** {fpm.root_cause.value}",
                    f"- **Pipeline stage:** {fpm.pipeline_stage.value}",
                    f"- **Error:** {fpm.error_message or '(none)'}",
                    f"- **Cost:** ${fpm.cost_usd:.4f}",
                    "",
                ])

        # Micro Prime Analysis
        if report.micro_prime_analysis:
            mpa = report.micro_prime_analysis
            lines.extend([
                "## Micro Prime Analysis",
                "",
                f"- Total elements: {mpa.total_elements}",
                f"- Successful: {mpa.successful_elements}",
                f"- Escalated: {mpa.escalated_elements}",
                f"- Avg generation time: {mpa.avg_generation_time_ms:.1f}ms",
                "",
            ])
            if mpa.tier_distribution:
                lines.append("**Tier distribution:**")
                for tier, count in sorted(mpa.tier_distribution.items()):
                    lines.append(f"- {tier}: {count}")
                lines.append("")

        # Cross-Feature Patterns
        if report.cross_feature_patterns:
            lines.extend(["## Cross-Feature Patterns", ""])
            for pat in report.cross_feature_patterns:
                lines.extend([
                    f"- **{pat.pattern_type}** ({pat.severity}): {pat.description}",
                ])
            lines.append("")

        # Lessons
        if report.lessons:
            lines.extend(["## Lessons", ""])
            for lesson in report.lessons:
                lines.append(f"- [{lesson.severity.value}] {lesson.title}")
            lines.append("")

        # Cost Summary
        if report.cost_summary:
            cs = report.cost_summary
            lines.extend([
                "## Cost Summary",
                "",
                f"- Total: ${cs.total_usd:.4f}",
                f"- Average per feature: ${cs.avg_per_feature:.4f}",
                f"- Max: {cs.max_feature} (${cs.max_usd:.4f})",
                "",
            ])

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Async launcher
# ---------------------------------------------------------------------------


def launch_prime_postmortem_async(
    result_dict: Dict[str, Any],
    queue: Any,  # FeatureQueue — Any to avoid circular import
    seed_path: Optional[str] = None,
    output_dir: str = ".",
    project_root: Optional[str] = None,
) -> threading.Thread:
    """Launch post-mortem evaluation in a background thread.

    Thread-safe: deep-copies result_dict and snapshots queue state before
    spawning the thread so the caller can continue without contention.

    Args:
        result_dict: Result from PrimeContractor.run().
        queue: FeatureQueue instance.
        seed_path: Optional path to seed file for requirement matching.
        output_dir: Directory for report output files.

    Returns:
        The started Thread object.
    """
    # Deep-copy for thread safety
    result_copy = copy.deepcopy(result_dict)

    # Snapshot queue state
    queue_state = {}
    if hasattr(queue, "features"):
        queue_state = {
            fid: f.to_dict() if hasattr(f, "to_dict") else {}
            for fid, f in queue.features.items()
        }

    # Load seed tasks if path provided
    seed_tasks = None
    if seed_path:
        try:
            seed_data = json.loads(Path(seed_path).read_text(encoding="utf-8"))
            seed_tasks = seed_data.get("tasks", [])
        except Exception:
            logger.warning("Failed to load seed for postmortem: %s", seed_path)

    def _run() -> None:
        try:
            evaluator = PrimePostMortemEvaluator()
            report = evaluator.evaluate(
                result_dict=result_copy,
                queue_state=queue_state,
                seed_tasks=seed_tasks,
                output_dir=output_dir,
                project_root=project_root,
            )
            logger.info(
                "Prime postmortem complete: score=%.2f verdict=%s",
                report.aggregate_score,
                report.aggregate_verdict,
            )
        except Exception:
            logger.warning("Prime postmortem evaluation failed", exc_info=True)

    thread = threading.Thread(
        target=_run,
        name="prime-postmortem",
        daemon=False,
    )
    thread.start()
    return thread
