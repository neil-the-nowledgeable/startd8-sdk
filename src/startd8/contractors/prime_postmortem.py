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

import ast
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

# Semantic issue categories that individually disqualify a feature from
# "complete" — a single occurrence means the feature is non-functional,
# regardless of requirement_score or error count (M3 run-021).
_CRITICAL_SEMANTIC_CATEGORIES = frozenset({
    "fake_work_stub",
    # F-6 (RUN-009/010): a phantom from-import means the module raises
    # ImportError at load time — it can never be wired, so a PASS on it is
    # unfalsifiable. One occurrence is disqualifying, same as fake_work_stub.
    "phantom_symbol",
})

# Extracts the unresolved module from a mypy import diagnostic, e.g.
# `Cannot find implementation or library stub for module named "app.ai.extract"`.
_MODULE_NAMED_RE = re.compile(r"""module named ["']([^"']+)["']""")


def _first_party_roots(project_root: str) -> set:
    """Top-level importable names the generator owns under *project_root* (C-3 first-party set).

    A module whose top segment is in this set MUST resolve — a mypy ``import-not-found`` against it
    is a real fault, not third-party "provisioning noise". Derived from disk (packages with
    ``__init__.py`` + top-level ``.py`` modules); always includes the ``app`` codegen convention.
    """
    roots = {"app"}
    try:
        for entry in Path(project_root).iterdir():
            if entry.is_dir() and (entry / "__init__.py").is_file():
                roots.add(entry.name)
            elif entry.is_file() and entry.suffix == ".py":
                roots.add(entry.stem)
    except OSError:
        pass
    return roots


def _is_import_provisioning_noise(diag: Any, first_party_roots: set) -> bool:
    """True iff *diag* is a mypy import error against an absent **third-party** dep (ignorable).

    A first-party (`app.*` / other owned-root) ``import-not-found`` is the C-3 bug class — a real
    fault — and returns ``False`` so it is NOT filtered. Non-import diagnostics also return ``False``.
    """
    code = (getattr(diag, "code", "") or "").lower()
    msg = (getattr(diag, "message", "") or "").lower()
    is_import_diag = (
        code in ("import", "import-not-found", "import-untyped")
        or "cannot find implementation or library stub" in msg
        or "find module" in msg
    )
    if not is_import_diag:
        return False
    m = _MODULE_NAMED_RE.search(getattr(diag, "message", "") or "")
    if m and m.group(1).split(".")[0] in first_party_roots:
        return False  # first-party import failure → real fault, never noise
    return True


_POSTMORTEM_TIMEOUT_S = 300
_COST_OUTLIER_FACTOR = 2.0  # Feature costing 2x+ average is an outlier
_CROSS_FEATURE_PATTERN_MIN = 2  # Minimum occurrences for repeated_root_cause
_ESCALATION_MIN_FEATURES = (
    3  # Minimum distinct features for escalation patterns (REQ-KZ-401a)
)
_ESCALATION_MIN_ELEMENTS = 5  # Minimum total element escalations (REQ-KZ-401a)

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
    REPAIR_LANGUAGE_MISMATCH = "repair_language_mismatch"
    CROSS_FILE_CONTRACT = (
        "cross_file_contract"  # RUN-008 FR-10: Prisma↔Zod / import seam divergence
    )
    TYPE_CLASS_MISMATCH = "type_class_mismatch"  # RUN-011 Gap C: TS231x/232x/234x assignment/overload/binding errors
    PROVIDER_ERROR = "provider_error"  # F-3 (RUN-006): provider API 4xx/5xx (credit, auth, rate limit) — the call never produced code
    TRUNCATION = "truncation"  # F-3 (RUN-008 §4): draft exceeded the output-token ceiling
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
    CROSS_FEATURE_CONTRACT = (
        "cross_feature_contract"  # RUN-008 FR-10: divergence between sibling features
    )
    TYPECHECK = "typecheck"  # RUN-011 Gap C: surfaced by tsc --noEmit, survives per-file isolation
    GENERATION = "generation"  # F-3: the LLM call itself (provider-agnostic — not Ollama-specific)
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Root Cause Classifier
# ---------------------------------------------------------------------------

# Compiled patterns mapping error strings to (RootCause, PipelineStage)
_ERROR_PATTERNS: List[Tuple[re.Pattern, RootCause, PipelineStage]] = [
    (
        re.compile(r"F811|redefinition of unused", re.IGNORECASE),
        RootCause.DUPLICATE_IMPORT,
        PipelineStage.REPAIR,
    ),
    (
        re.compile(r"NotImplementedError|unfilled stub", re.IGNORECASE),
        RootCause.UNFILLED_STUB,
        PipelineStage.OLLAMA_GENERATION,
    ),
    (
        re.compile(r"nested class|scope corruption|unexpected indent", re.IGNORECASE),
        RootCause.SCOPE_CORRUPTION,
        PipelineStage.SPLICER,
    ),
    (
        re.compile(r"phantom import|no module named|cannot import", re.IGNORECASE),
        RootCause.PHANTOM_IMPORT,
        PipelineStage.OLLAMA_GENERATION,
    ),
    (
        re.compile(r"skeleton.*missing|no skeleton|skeleton not found", re.IGNORECASE),
        RootCause.SKELETON_MISSING,
        PipelineStage.SKELETON,
    ),
    (
        re.compile(r"timeout|timed out", re.IGNORECASE),
        RootCause.OLLAMA_TIMEOUT,
        PipelineStage.OLLAMA_GENERATION,
    ),
    (
        re.compile(r"empty response|no response", re.IGNORECASE),
        RootCause.OLLAMA_EMPTY_RESPONSE,
        PipelineStage.OLLAMA_GENERATION,
    ),
    (
        re.compile(r"circuit.?breaker", re.IGNORECASE),
        RootCause.OLLAMA_CIRCUIT_BREAKER,
        PipelineStage.OLLAMA_GENERATION,
    ),
    (
        re.compile(r"repair exhausted|max repair", re.IGNORECASE),
        RootCause.REPAIR_EXHAUSTED,
        PipelineStage.REPAIR,
    ),
    (
        re.compile(r"splice|splicer.*mismatch", re.IGNORECASE),
        RootCause.SPLICER_MISMATCH,
        PipelineStage.SPLICER,
    ),
    (
        re.compile(r"size regression|size.*guard|file.*too large", re.IGNORECASE),
        RootCause.SIZE_REGRESSION,
        PipelineStage.INTEGRATION,
    ),
    (
        re.compile(r"ast.*fail|syntax error|invalid syntax", re.IGNORECASE),
        RootCause.AST_FAILURE,
        PipelineStage.REPAIR,
    ),
    # RUN-011 Gap C — TypeScript type-class errors (assignment/binding/operator):
    # TS231x (operator overload), TS232x (binding/assignment), TS234x (argument
    # assignment, e.g. TS2345 Set<unknown> not assignable to Set<string>). These
    # are REAL type errors that survive per-file isolation (not the module-resolution
    # / target-lib false positives nodejs.py strips) — attribute them, don't leave
    # them as unknown/unknown. Case-sensitive on the TS code to avoid stray matches.
    (
        re.compile(r"error TS23[124]\d\b"),
        RootCause.TYPE_CLASS_MISMATCH,
        PipelineStage.TYPECHECK,
    ),
    # F-3 (RUN-006 §3.2): provider API errors — the most legible failure class in the
    # catalog (an HTTP 4xx/5xx with a request id) used to classify unknown/unknown.
    # Covers Anthropic/OpenAI-style error envelopes: invalid_request_error (incl. the
    # credit-balance 400), auth/permission, rate limit, and overloaded responses.
    (
        re.compile(
            r"Error code: [45]\d\d|invalid_request_error|credit balance|"
            r"authentication_error|permission_error|rate.?limit_error|"
            r"overloaded_error|insufficient[_ ]quota|invalid.?api.?key",
            re.IGNORECASE,
        ),
        RootCause.PROVIDER_ERROR,
        PipelineStage.GENERATION,
    ),
    # F-3 (RUN-008 §4): output-token truncation ("Draft was truncated at iteration N").
    (
        re.compile(r"truncat", re.IGNORECASE),
        RootCause.TRUNCATION,
        PipelineStage.GENERATION,
    ),
    (
        re.compile(r"blocked by.*dependency|dependency.*failed", re.IGNORECASE),
        RootCause.DEPENDENCY_BLOCKED,
        PipelineStage.INTEGRATION,
    ),
    (
        re.compile(r"generation.*error|generation.*fail", re.IGNORECASE),
        RootCause.GENERATION_ERROR,
        PipelineStage.OLLAMA_GENERATION,
    ),
    # Agent API contract errors — TypeError/unexpected keyword from
    # mismatched agent.generate() signatures (Run-027: 'stop' kwarg).
    (
        re.compile(
            r"unexpected keyword argument|TypeError.*agenerate|TypeError.*generate",
            re.IGNORECASE,
        ),
        RootCause.GENERATION_ERROR,
        PipelineStage.OLLAMA_GENERATION,
    ),
    # Catch-all: "Exception during code generation" wrapper from
    # develop_feature()'s except block — the real error is in the suffix.
    (
        re.compile(r"Exception during code generation", re.IGNORECASE),
        RootCause.GENERATION_ERROR,
        PipelineStage.OLLAMA_GENERATION,
    ),
]

# Maps EscalationReason string values to (RootCause, PipelineStage)
_ESCALATION_MAP: Dict[str, Tuple[RootCause, PipelineStage]] = {
    "ast_failure": (RootCause.AST_FAILURE, PipelineStage.REPAIR),
    "structural_mismatch": (RootCause.SPLICER_MISMATCH, PipelineStage.SPLICER),
    "semantic_failure": (RootCause.GENERATION_ERROR, PipelineStage.REPAIR),
    "ollama_unavailable": (RootCause.OLLAMA_TIMEOUT, PipelineStage.OLLAMA_GENERATION),
    "tier_too_high": (RootCause.TIER_ESCALATION, PipelineStage.CLASSIFICATION),
    "repair_exhausted": (RootCause.REPAIR_EXHAUSTED, PipelineStage.REPAIR),
    "empty_response": (
        RootCause.OLLAMA_EMPTY_RESPONSE,
        PipelineStage.OLLAMA_GENERATION,
    ),
    "timeout": (RootCause.OLLAMA_TIMEOUT, PipelineStage.OLLAMA_GENERATION),
    "circuit_breaker": (
        RootCause.OLLAMA_CIRCUIT_BREAKER,
        PipelineStage.OLLAMA_GENERATION,
    ),
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
    # Repair signal enrichment — thread "what broke" through to Kaizen.
    ast_valid_before_repair: Optional[bool] = None
    repair_attribution: Optional[Dict[str, Any]] = None


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
    semantic_error_count: int = 0  # Count of error-severity semantic issues
    # Semantic repair dual scoring (DC-3, REQ-SR)
    pre_semantic_repair_score: Optional[float] = None
    semantic_repairs_applied: int = 0
    semantic_repair_categories: List[str] = dataclasses.field(default_factory=list)
    # Exemplar injection tracking (REQ-PEP-103)
    exemplar_used: bool = False
    exemplar_id: Optional[str] = None
    exemplar_match_type: Optional[str] = None  # "exact" | "partial" | "none"
    # TODO scanner counts (REQ-TCW-100)
    todo_count_a: int = 0
    todo_count_b: int = 0
    todo_count_c: int = 0
    # Determinism provenance (REQ-DET-METRIC) — how the feature's code was produced.
    # "llm" (default) means an LLM authored it; any other value is a $0/no-LLM path
    # stamped by a prime-contractor shortcut: "deterministic_provider" (owned-kind
    # skip-hook), "corpus", "copy", or "uncomment".
    generation_path: str = "llm"
    deterministic: bool = False
    # F-3 attribution (RUN-006 §3.2): who made the call that succeeded/failed. Stamped at
    # the failure site by the prime contractor (feature.metadata["failure_attribution"])
    # and on history entries; None only when genuinely unavailable (e.g. no LLM was called).
    agent: Optional[str] = None  # full agent spec, e.g. "anthropic:claude-sonnet-4-6"
    model: Optional[str] = None  # bare model id, e.g. "claude-sonnet-4-6"
    provider: Optional[str] = None  # e.g. "anthropic"

    @property
    def semantic_issue_summary(self) -> Dict[str, int]:
        """Category → count mapping for Kaizen trend analysis (REQ-SV-903)."""
        if not self.disk_compliance:
            return {}
        summary: Dict[str, int] = {}
        for issue in getattr(self.disk_compliance, "semantic_issues", []):
            if isinstance(issue, dict):
                cat = issue.get("category", "unknown")
                summary[cat] = summary.get(cat, 0) + 1
        return summary


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
    # Repair signal: how many elements needed repair and what broke.
    elements_repaired: int = 0
    repair_before_invalid: int = 0  # AST invalid before repair
    repair_attribution_summary: Dict[str, int] = dataclasses.field(
        default_factory=dict
    )  # e.g. {"fence_stripped": 3, "imports_added": 5}


@dataclasses.dataclass
class CostSummary:
    """Cost summary across all features."""

    total_usd: float = 0.0
    per_feature: Dict[str, float] = dataclasses.field(default_factory=dict)
    avg_per_feature: float = 0.0
    max_feature: str = ""
    max_usd: float = 0.0


@dataclasses.dataclass
class DeterminismMetrics:
    """Deterministic-vs-LLM assembly breakdown for a run (REQ-DET-METRIC).

    Answers "what fraction of this run was assembled deterministically ($0 LLM)?" —
    the measurement the ~60-75% deterministic-ceiling goal was never able to validate.
    A feature is deterministic when it was served by a no-LLM shortcut (owned-kind
    provider skip, corpus, copy, or uncomment); ``by_path`` keeps the per-path split so
    the owned-kind ($0 schema-derived) contribution is distinguishable from copy/uncomment.

    Ratios are reported two ways: by feature count and by generated-file count, because a
    single deterministic feature can own many files (e.g. one ``generate backend`` feature
    owning the whole spine) and the file ratio is the more honest cost lever.
    """

    deterministic_features: int = 0
    llm_features: int = 0
    feature_ratio: float = 0.0  # deterministic_features / total features
    deterministic_files: int = 0
    llm_files: int = 0
    file_ratio: float = 0.0  # deterministic_files / total generated files
    by_path: Dict[str, int] = dataclasses.field(default_factory=dict)  # path -> feature count


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
    determinism: Optional[DeterminismMetrics] = None
    avg_assembly_delta: Optional[float] = None


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Disk quality scoring (Phase E — Kaizen Quality)
# Canonical implementation lives in forward_manifest_validator.py (REQ-RFL-110).
# Re-exported here for backward compatibility.
# ---------------------------------------------------------------------------

from startd8.forward_manifest_validator import compute_disk_quality_score  # noqa: F401

# ---------------------------------------------------------------------------
# Kaizen suggestion generation (Phase C — moved from scripts/)
# ---------------------------------------------------------------------------

# All 16 RootCause values mapped to prompt hints.
CAUSE_TO_SUGGESTION: Dict[str, Dict[str, str]] = {
    # Generic fallback for Semantic Compliance Reviewer findings (FR-10). The SCR emits
    # feature-specific, templated hints directly into kaizen-suggestions.json; this entry
    # is the catch-all used when no per-issue hint is available.
    "requirement_semantic_gap": {
        "phase": "draft",
        "hint": (
            "Re-read the feature's requirement before generating: implement the asked-for "
            "behavior, honor named field authorities (do not compute/invent fields the "
            "requirement marks as caller-provided), and respect the negative scope "
            "('invent X -> use Y')."
        ),
    },
    # F-3 (RUN-006): provider API error — operational, not a prompt defect. No prompt
    # change fixes an account/config-level 4xx; the hint exists so the suggestion
    # pipeline stays exhaustive over RootCause.
    "provider_error": {
        "phase": "draft",
        "hint": (
            "The provider API call itself failed (4xx/5xx: credit balance, auth, rate "
            "limit, or overload) — no code was generated. Fix the provider account/"
            "configuration (and verify the intended provider/model routing) before "
            "re-running; prompt changes cannot fix an account-level failure."
        ),
    },
    # F-3 (RUN-008 §4): output-token truncation — the single-file emission is too large.
    "truncation": {
        "phase": "draft",
        "hint": (
            "The draft exceeded the output-token ceiling and was truncated. Decompose the "
            "task into separable deliverables (e.g. module skeleton vs. templates) rather "
            "than raising max_tokens — a larger ceiling only moves the cliff."
        ),
    },
    # FR-CAR-9 — house-style (convention) violation surfaced by convention-aware repair
    # (repair.convention). Feeds recurring per-tier convention failures back into generation so the
    # next run adheres to the deterministic-generator house style (the RUN-028 class). Pairs with the
    # complexity-classifier signal (postmortem A1 / deterministic-first review D3).
    "requirement_convention_gap": {
        "phase": "draft",
        "hint": (
            "Follow the generated-app house style exactly: FastAPI (APIRouter/Depends/HTMLResponse), "
            "SQLModel access (session.exec(select(...)) / session.get(Model, id)), and "
            "Jinja2Templates/TemplateResponse. Do NOT use Flask, session.query(...), or "
            "render_template(...); import SQLModel tables from app.tables (app.models is Pydantic "
            "*Schema only)."
        ),
    },
    # RUN-008 FR-10 — cross-feature contract divergence (Prisma↔Zod). The
    # categories below match SymmetryViolation.kind so the Kaizen loop maps
    # them directly.
    "cross_file_contract": {
        "phase": "spec",
        "hint": (
            "Source cross-file contracts (imported module names, field/type/FK "
            "shape) from the producing feature's actual output — do not invent them."
        ),
    },
    "type_class_mismatch": {
        "phase": "draft",
        "hint": (
            "Type the generated values to match their consumers — a TS2345/2322/231x "
            "error means an assignment/argument/operator type is incompatible "
            "(e.g. iterating an `unknown`-typed tool-use response into a `Set<string>`). "
            "Annotate the collection (`new Set<string>()`) or narrow/cast the value at "
            "the boundary; do not leave LLM tool-use outputs as `unknown`."
        ),
    },
    "unresolvable_import": {
        "phase": "draft",
        "hint": (
            "Import only from modules that exist — a path generated by an earlier "
            "feature in this batch, or a pre-existing project file. Do not invent a "
            "module path (e.g. `@/lib/prisma`) when the project uses a different one "
            "(`@/lib/db`); inherit the real path from the project's module inventory."
        ),
    },
    "missing_dependency": {
        "phase": "draft",
        "hint": (
            "Import only packages declared in package.json. Do not import a package "
            "(e.g. `pino`) the project does not depend on; use an existing dependency "
            "or the project's established logging/util module."
        ),
    },
    "prisma_unknown_field": {
        "phase": "draft",
        "hint": (
            "Use only field names that exist on the Prisma model. Do not invent or "
            "rename columns (`promptTokens`/`responseTokens`, not `inputTokens`/"
            "`outputTokens`); consult the prisma/schema.prisma model definition."
        ),
    },
    "prisma_where_not_unique": {
        "phase": "draft",
        "hint": (
            "`findUnique`/`upsert`/`update`/`delete` `where` must select by an "
            "`@unique`/`@id` column. Use `findFirst` to filter by a non-unique field, "
            "or add `@unique` to the column in the schema."
        ),
    },
    "prisma_invalid_compound_key": {
        "phase": "draft",
        "hint": (
            "A compound `where` key (e.g. `id_ownerId`) requires a matching "
            "`@@unique([...])`/`@@id([...])` on the Prisma model. Declare the compound "
            "constraint or select by an existing unique key."
        ),
    },
    "field_missing_in_prisma": {
        "phase": "draft",
        "hint": (
            "Every Zod field must exist on the corresponding Prisma model with the "
            "SAME name — no synonyms (use `summary` not `bio`, `yearsExp` not "
            "`yearsOfExperience`). Reconcile against the generated schema."
        ),
    },
    "fk_invented": {
        "phase": "draft",
        "hint": (
            "Do not invent a foreign key the Prisma relation graph does not declare. "
            "If a child links to a parent, the Prisma model must define the FK column "
            "and relation; otherwise omit it from the Zod schema."
        ),
    },
    "field_type_mismatch": {
        "phase": "draft",
        "hint": (
            "Zod field types must match the Prisma column type-class (Prisma String "
            "→ z.string(), Int/Float → z.number(), DateTime → z.string().datetime())."
        ),
    },
    "field_missing_in_zod": {
        "phase": "draft",
        "hint": (
            "A required, non-defaulted Prisma column is absent from the Zod schema; "
            "add it or confirm the input legitimately omits it."
        ),
    },
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
        "hint": (
            "Emit syntactically valid code for the target language. "
            "Python: ensure ast.parse() succeeds. C#: valid braces, file-scoped namespace. "
            "Go: ensure gofmt passes. Java: valid braces, correct package. "
            "Run a mental parse check before returning."
        ),
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
    "repair_language_mismatch": {
        "phase": "repair",
        "hint": (
            "The repair pipeline produced Python syntax for a non-Python file. "
            "This is a pipeline bug — bare_statement_wrap generated a Python def "
            "wrapper for code in another language. Verify REQ-MPL-100 language guard."
        ),
    },
    "unknown": {
        "phase": "draft",
        "hint": "Inspect the failure message and add a targeted fix rather than regenerating the whole file.",
    },
    "repeated_escalation:ast_failure": {
        "phase": "draft",
        "hint": (
            "Emit syntactically valid code for the target language. "
            "If generating function bodies, always include the full signature line. "
            "Python: def line. C#: method signature with braces. Go: func signature. "
            "Java: method signature with braces."
        ),
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
    "language_mismatch_in_generation": {
        "phase": "spec",
        "hint": (
            "Non-Python files received Python stubs. Check template-match routing "
            "for non-Python trivial tasks. Ensure _NON_PYTHON_EXTENSIONS includes "
            "all target file extensions."
        ),
    },
    # --- Python AST semantic check hints (REQ-KZ-003) ---
    "duplicate_main_guard_detected": {
        "phase": "draft",
        "hint": (
            "Files should have at most one `if __name__ == '__main__':` guard. "
            "Multiple guards indicate copy-paste from different sources. "
            "Keep only the bottom-most guard that serves as the entry point."
        ),
    },
    "bare_except_pass_detected": {
        "phase": "draft",
        "hint": (
            "Never use bare `except: pass` — this silently swallows all errors "
            "including KeyboardInterrupt and SystemExit. Use specific exception "
            "types: `except (ValueError, TypeError):` or at minimum `except Exception:`."
        ),
    },
    "phantom_dependency_detected": {
        "phase": "draft",
        "hint": (
            "Every import must resolve to a known module — either stdlib, a declared "
            "dependency, or a sibling file in the project. Unresolvable imports "
            "indicate a missing dependency or typo in the import path."
        ),
    },
    "fake_work_stub_detected": {
        "phase": "draft",
        "hint": (
            "Do NOT simulate work with `asyncio.sleep(...)`/`time.sleep(...)` and "
            "return canned data. Route handlers and service functions must IMPORT "
            "and CALL the real target modules (e.g. `from app.ai.extract import "
            "extract`) — never re-implement them as local placeholder stubs. A "
            "feature that returns fabricated data without invoking real logic is "
            "non-functional even though it compiles."
        ),
    },
    # --- F-6 (RUN-009/010): phantom symbols + referenced template assets ---
    "phantom_symbol_detected": {
        "phase": "draft",
        "hint": (
            "Every `from X import Y` must name a symbol that actually exists in "
            "module X — verify against the real package API instead of inventing "
            "names (e.g. `TemplateResponse` is NOT importable from "
            "`starlette.responses`; follow the project's established import style "
            "such as `from fastapi.templating import Jinja2Templates`). A phantom "
            "from-import makes the whole module fail at load time."
        ),
    },
    "missing_template_asset_detected": {
        "phase": "draft",
        "hint": (
            "Every template name passed to TemplateResponse(...)/get_template(...) "
            "must exist on disk under the project's templates directory. Emit the "
            "template files alongside the code that references them, or render "
            "only templates that already exist."
        ),
    },
    # --- Python L1-L10 disk compliance check hints (P3-4) ---
    "import_resolution_detected": {
        "phase": "draft",
        "hint": (
            "Imports must resolve to existing modules. Check for typos in import "
            "paths, missing __init__.py files, or dependencies not declared in "
            "the project's dependency manifest."
        ),
    },
    "cross_scope_duplicate_detected": {
        "phase": "draft",
        "hint": (
            "Duplicate definitions at module level (same function or class name "
            "defined twice). Remove the duplicate or rename to avoid shadowing."
        ),
    },
    "factory_return_detected": {
        "phase": "draft",
        "hint": (
            "Factory functions (create_*, make_*, build_*) must return a value. "
            "A factory that returns None silently breaks callers."
        ),
    },
    "discarded_return_detected": {
        "phase": "draft",
        "hint": (
            "Function return values must be captured. Calling a function that "
            "returns a value without assigning the result is likely a bug."
        ),
    },
    "method_resolution_detected": {
        "phase": "draft",
        "hint": (
            "self.method() calls must resolve to actual methods on the class. "
            "Check for typos in method names or calls to module-level functions "
            "via self instead of direct call."
        ),
    },
    "service_identity_detected": {
        "phase": "draft",
        "hint": (
            "A module must not import itself. Self-imports create circular "
            "dependencies and indicate a naming collision."
        ),
    },
    # --- Cross-language semantic issue hints ---
    "console_logging_detected": {
        "phase": "draft",
        "hint": (
            "Prior run used console output (Console.WriteLine, System.out.println, "
            "fmt.Println, console.log) instead of structured logging. "
            "C#: inject ILogger<T> via constructor. Java: use SLF4J LoggerFactory. "
            "Go: use slog or zap. Node.js: use winston or pino."
        ),
    },
    "empty_catch_detected": {
        "phase": "draft",
        "hint": (
            "Prior run had empty catch/except blocks that silently swallow errors. "
            "ALWAYS log the exception. Prefer catching specific exception types. "
            "C#: catch (SpecificException ex) { _logger.LogError(ex, ...); } "
            'Java: catch (IOException e) { logger.error("msg", e); } '
            'Go: if err != nil { return fmt.Errorf("context: %w", err) }'
        ),
    },
    "unchecked_error_detected": {
        "phase": "draft",
        "hint": (
            "Prior run assigned error values without checking them. "
            "Go: always check `if err != nil` after every error-returning call. "
            "Never use `_ = someFunc()` to discard errors in production code."
        ),
    },
    "namespace_alignment_issue": {
        "phase": "draft",
        "hint": (
            "Prior run had namespace/package declarations that didn't match the "
            "directory structure. C#: namespace must be PascalCase matching dirs "
            "(src/CartService/Services/ → namespace CartService.Services;). "
            "Java: package must match directory (com/example/service/ → "
            "package com.example.service;). Go: package name must match directory name."
        ),
    },
    "module_system_mixing_detected": {
        "phase": "draft",
        "hint": (
            "Prior run mixed CommonJS (require/module.exports) and ESM "
            "(import/export) in the same file. Pick ONE module system per file. "
            "Check package.json 'type' field: 'module' → use ESM, absent → use CJS."
        ),
    },
    # REQ-KZ-ND-402 Phase 1: Node.js Kaizen hint entries
    "var_usage_detected": {
        "phase": "draft",
        "hint": (
            "Prior run used `var` declarations. Use `const` for bindings that "
            "are never reassigned, `let` for loop counters and mutable bindings. "
            "NEVER use `var` — it has function scope instead of block scope."
        ),
    },
    "duplicate_require_detected": {
        "phase": "draft",
        "hint": (
            "Prior run had duplicate require()/import of the same module. "
            "Each module should be imported ONCE at the top of the file. "
            "Consolidate destructured imports: const {a, b} = require('pkg')."
        ),
    },
    "unhandled_promise_detected": {
        "phase": "draft",
        "hint": (
            "Prior run had async operations without error handling. "
            "Wrap async calls in try/catch blocks. Add "
            "process.on('unhandledRejection', handler) as a safety net "
            "in entry points."
        ),
    },
    "python_contamination_detected": {
        "phase": "spec",
        "hint": (
            "Non-JavaScript artifacts (Python syntax) found in JS/TS files. "
            "Check template-match routing for non-Python trivial tasks. "
            "Ensure language profile is correctly resolved for all target files."
        ),
    },
    "block_scoped_namespace_detected": {
        "phase": "draft",
        "hint": (
            "Prior run used block-scoped namespaces (namespace X { ... }) instead of "
            "file-scoped (namespace X;). For .NET 6+ / C# 10+ targets, ALWAYS use "
            "file-scoped namespaces to reduce nesting."
        ),
    },
    "sql_injection_detected": {
        "phase": "draft",
        "hint": (
            "Prior run generated SQL queries with string interpolation. "
            "CRITICAL: Use ONLY parameterized queries. Example:\n"
            "  BAD:  $\"SELECT * FROM cart WHERE user_id = '{userId}'\"\n"
            '  GOOD: cmd.CommandText = "SELECT * FROM cart WHERE user_id = @userId";\n'
            '        cmd.Parameters.AddWithValue("@userId", userId);\n'
            'For Spanner: new SpannerCommand("SELECT * FROM Cart WHERE UserId = @userId", conn)\n'
            '             { Parameters = { { "userId", SpannerDbType.String, userId } } }'
        ),
        "confidence": 1.0,
    },
    # --- C# semantic issue hints (REQ-CS-MP-400) ---
    "missing_async_await_detected": {
        "phase": "draft",
        "hint": (
            "Prior run had async methods that never use 'await'. "
            "If a method is marked 'async', it MUST contain at least one 'await' expression. "
            "If no async work is needed, remove the 'async' modifier and return the result directly."
        ),
    },
    "missing_access_modifier_detected": {
        "phase": "draft",
        "hint": (
            "Prior run had type or member declarations without explicit access modifiers. "
            "C#: always specify 'public', 'internal', 'private', or 'protected'. "
            "Java: always specify 'public', 'protected', 'private', or package-private. "
            "Do not rely on language defaults."
        ),
    },
    "interface_file_contains_class_detected": {
        "phase": "draft",
        "hint": (
            "Prior run placed concrete class implementations in interface files "
            "(e.g., IFoo.cs or IFoo.java). Interface files should contain ONLY the "
            "interface definition. Move implementations to separate files named "
            "after the implementing class."
        ),
    },
    # --- Go semantic issue hints (REQ-KZ-GO-501) ---
    "duplicate_definition_detected": {
        "phase": "draft",
        "hint": (
            "Prior run declared the same function name twice in a single Go file. "
            "Check for existing definitions before generating new ones. "
            "Each function name must be unique within a file."
        ),
    },
    "dot_import_detected": {
        "phase": "draft",
        "hint": (
            'Prior run used dot-imports (import . "pkg") which pollute the namespace. '
            "Always use explicit package-qualified access (e.g., fmt.Println, not Println)."
        ),
    },
    # --- Cross-language validation hints ---
    "raw_type_usage_detected": {
        "phase": "draft",
        "hint": (
            "Prior run used raw generic types (e.g., List instead of List<String>). "
            "Always specify type parameters for generic types to enable compile-time "
            "type checking and avoid ClassCastException at runtime."
        ),
    },
    "missing_override_detected": {
        "phase": "draft",
        "hint": (
            "Prior run overrode methods without the @Override annotation. "
            "Always add @Override when implementing interface methods or overriding "
            "superclass methods — the compiler catches signature mismatches."
        ),
    },
    "wildcard_import_detected": {
        "phase": "draft",
        "hint": (
            "Prior run used wildcard imports (e.g., import java.util.*). "
            "Use explicit imports for each type to avoid namespace collisions "
            "and make dependencies visible."
        ),
    },
    "duplicate_method_detected": {
        "phase": "draft",
        "hint": (
            "Prior run declared the same method with identical parameter types "
            "twice in a single file. Check for existing method signatures before "
            "generating new ones. Overloading (same name, different param types) "
            "is fine — exact duplicates are not."
        ),
    },
    "invalid_java_version_detected": {
        "phase": "spec",
        "hint": (
            "Prior run specified a Java version outside the known valid range (8–24). "
            "Use a released Java LTS version (11, 17, or 21) for sourceCompatibility "
            "and targetCompatibility in build.gradle."
        ),
    },
    "invalid_node_version_detected": {
        "phase": "spec",
        "hint": (
            "Prior run specified a Node.js engine version outside the known valid "
            "range (14–24). Use a current LTS version (18 or 20) in the "
            '"engines" field of package.json.'
        ),
    },
    "missing_module_type_detected": {
        "phase": "spec",
        "hint": (
            'Prior run package.json was missing the "type" field. Add '
            '"type": "module" for ESM or "type": "commonjs" for CJS '
            "to make the module system explicit and avoid import confusion."
        ),
    },
    "invalid_package_json_detected": {
        "phase": "spec",
        "hint": (
            "Prior run produced an invalid package.json (not valid JSON). "
            "Ensure the generated file is well-formed JSON with required "
            'fields ("name", "version", "dependencies").'
        ),
    },
    "invalid_go_version_detected": {
        "phase": "spec",
        "hint": (
            "Prior run specified a Go version outside the known valid range. "
            "Use a released Go version (1.18–1.24). Verify go.mod and "
            "Dockerfile golang: image tag match."
        ),
    },
    "invalid_go_mod_detected": {
        "phase": "spec",
        "hint": (
            "Prior run produced a malformed go.mod (missing module or go directive). "
            "Every go.mod must start with 'module <path>' followed by 'go <version>'."
        ),
    },
    "missing_nullable_csproj_detected": {
        "phase": "spec",
        "hint": (
            "Prior run .csproj was missing <Nullable>enable</Nullable>. "
            "For .NET 6+, always enable nullable reference types."
        ),
    },
    # --- Query Prime security entries (REQ-KQP-602) ---
    "query_injection_interpolation": {
        "phase": "draft",
        "hint": (
            "Prior run used string interpolation in SQL queries. "
            "Use parameterized queries with bind variables: "
            "@param (SQL Server/Spanner), $N (PostgreSQL), ? (MySQL/SQLite)."
        ),
        "confidence": 0.95,
    },
    "query_injection_concatenation": {
        "phase": "draft",
        "hint": (
            "Prior run used string concatenation to build SQL. "
            "Never concatenate user input into query strings. "
            "Use command parameters or an ORM query builder."
        ),
        "confidence": 0.95,
    },
    "query_credential_logged": {
        "phase": "draft",
        "hint": (
            "Prior run logged connection strings or credentials. "
            "Never pass credential variables to Console.Write, logger, or Debug. "
            "Log only sanitized connection metadata (host, port, database name)."
        ),
        "confidence": 0.90,
    },
    "query_credential_exposed": {
        "phase": "draft",
        "hint": (
            "Prior run exposed credentials in source code (hardcoded or inline). "
            "Load credentials from environment variables, secret managers, or config files. "
            "Never embed passwords or connection strings as string literals."
        ),
        "confidence": 0.85,
    },
    "query_lifecycle_per_request": {
        "phase": "draft",
        "hint": (
            "Prior run created database connections per-request instead of using "
            "connection pooling. Use dependency-injected DbContext/connection pools. "
            "For C#: register DbContext in DI with AddDbContext<T>(). "
            "For Go: use sql.Open() once at startup, not per handler."
        ),
        "confidence": 0.80,
    },
    "query_lifecycle_no_dispose": {
        "phase": "draft",
        "hint": (
            "Prior run created database resources without proper disposal. "
            "C#: wrap in 'using' or 'await using'. Go: defer conn.Close(). "
            "Python: use 'with' context manager. "
            "Undisposed connections cause pool exhaustion under load."
        ),
        "confidence": 0.80,
    },
    "query_t3_insufficient": {
        "phase": "spec",
        "hint": (
            "Prior run required escalation from T3 (Haiku) for queries that "
            "should be simple. Provide more specific query context in the spec: "
            "exact table names, column types, and expected parameter bindings."
        ),
        "confidence": 0.75,
    },
    # --- Observability artifact hints (REQ-KZ-OBS-600) ---
    "obs_phantom_service": {
        "phase": "artifact_gen",
        "hint": (
            "Service '{service}' is not a runtime service — add to non-service "
            "skip list. Phantom services produce valid YAML that would create "
            "empty dashboards and never-firing alerts."
        ),
    },
    "obs_missing_red_panels": {
        "phase": "artifact_gen",
        "hint": (
            "Dashboard for '{service}' is missing RED method panels. "
            "Add error rate and request rate panels alongside latency. "
            "RED coverage requires Rate (request count), Errors (error ratio), "
            "and Duration (latency histogram) panels."
        ),
    },
    "obs_slo_target_mismatch": {
        "phase": "artifact_gen",
        "hint": (
            "SLO target {actual} does not match manifest availability {expected}. "
            "Use manifest value. Ensure load_business_context() reads availability "
            "from .contextcore.yaml correctly."
        ),
    },
    "obs_threshold_mismatch": {
        "phase": "artifact_gen",
        "hint": (
            "Alert/dashboard threshold {actual} does not match manifest "
            "latency_p99 {expected}. Derivation rules must flow through to "
            "all artifact types consistently."
        ),
    },
    "obs_missing_availability_slo": {
        "phase": "artifact_gen",
        "hint": (
            "Service '{service}' has availability requirement but no "
            "availability (ratio-based) SLO. Add an availability SLO alongside "
            "the latency SLO when manifest.spec.requirements.availability is set."
        ),
    },
    "obs_transport_metric_mismatch": {
        "phase": "artifact_gen",
        "hint": (
            "Service '{service}' uses {transport} but metrics reference wrong "
            "protocol family. gRPC services MUST use rpc_server_* metrics; "
            "HTTP services MUST use http_server_* metrics."
        ),
    },
}

# Maps semantic issue categories (from DiskComplianceResult.semantic_issues)
# to CAUSE_TO_SUGGESTION keys for cross-feature pattern generation.
# When 2+ features share the same category, a kaizen suggestion is emitted
# so the next run's LLM prompt gets a corrective hint.
_SEMANTIC_CATEGORY_TO_SUGGESTION: Dict[str, str] = {
    # Security (Query Prime)
    "sql_injection_risk": "sql_injection_detected",
    "query_security_injection": "query_injection_interpolation",
    "query_security_credential_leakage": "query_credential_logged",
    "query_security_lifecycle": "query_lifecycle_per_request",
    # Cross-language logging (C#, Java, Go, Node.js)
    "console_writeline_in_service": "console_logging_detected",
    "system_out_in_service": "console_logging_detected",
    "fmt_println_in_service": "console_logging_detected",
    "console_log_in_service": "console_logging_detected",
    # Exception/error handling
    "empty_catch_block": "empty_catch_detected",
    "unchecked_error": "unchecked_error_detected",
    # Go code style (REQ-KZ-GO-501)
    "duplicate_function": "duplicate_definition_detected",
    "dot_import": "dot_import_detected",
    # Namespace/package alignment
    "namespace_case_mismatch": "namespace_alignment_issue",
    "namespace_filepath_mismatch": "namespace_alignment_issue",
    "package_filepath_mismatch": "namespace_alignment_issue",
    "package_dir_mismatch": "namespace_alignment_issue",
    "package_case_mismatch": "namespace_alignment_issue",
    # Module system
    "module_system_mixing": "module_system_mixing_detected",
    # Cross-language contamination
    "python_contamination": "language_mismatch_in_generation",
    # REQ-KZ-ND-402 Phase 0: Node.js semantic checks → suggestion wiring
    "var_usage": "var_usage_detected",
    "duplicate_require": "duplicate_require_detected",
    "unhandled_promise": "unhandled_promise_detected",
    # Code style
    "block_scoped_namespace": "block_scoped_namespace_detected",
    # C# semantic checks (REQ-CS-MP-400)
    "missing_async_await": "missing_async_await_detected",
    "missing_access_modifier": "missing_access_modifier_detected",
    "interface_file_contains_class": "interface_file_contains_class_detected",
    # Java semantic checks
    "raw_type_usage": "raw_type_usage_detected",
    "missing_override": "missing_override_detected",
    "wildcard_import": "wildcard_import_detected",
    # Go version/mod validation
    "invalid_go_version": "invalid_go_version_detected",
    "invalid_go_mod": "invalid_go_mod_detected",
    # C# csproj validation
    "missing_nullable_in_csproj": "missing_nullable_csproj_detected",
    # Java version validation
    "duplicate_method": "duplicate_method_detected",
    "invalid_java_version": "invalid_java_version_detected",
    # Node.js package.json validation
    "invalid_node_version": "invalid_node_version_detected",
    "missing_module_type": "missing_module_type_detected",
    "invalid_package_json": "invalid_package_json_detected",
    # Observability artifact issues (REQ-KZ-OBS-600)
    "obs_phantom_service": "obs_phantom_service",
    "obs_missing_red_coverage": "obs_missing_red_panels",
    "obs_slo_target_mismatch": "obs_slo_target_mismatch",
    "obs_threshold_mismatch": "obs_threshold_mismatch",
    "obs_missing_availability_slo": "obs_missing_availability_slo",
    "obs_transport_metric_mismatch": "obs_transport_metric_mismatch",
    # Python AST semantic checks (REQ-KZ-003)
    "duplicate_main_guard": "duplicate_main_guard_detected",
    "duplicate_definition": "duplicate_definition_detected",
    "bare_except_pass": "bare_except_pass_detected",
    "phantom_dependency": "phantom_dependency_detected",
    "fake_work_stub": "fake_work_stub_detected",
    # F-6: symbol-level import + referenced-asset checks (L12/L13)
    "phantom_symbol": "phantom_symbol_detected",
    "missing_template_asset": "missing_template_asset_detected",
    # Python L1-L10 disk compliance categories (P3-4 terminology alignment)
    "import_resolution": "import_resolution_detected",
    "cross_scope_duplicate": "cross_scope_duplicate_detected",
    "factory_return": "factory_return_detected",
    "discarded_return": "discarded_return_detected",
    "method_resolution": "method_resolution_detected",
    "service_identity_mismatch": "service_identity_detected",
}


def generate_kaizen_suggestions(
    report: Any,
    output_dir: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Generate structured improvement suggestions from a post-mortem report.

    Args:
        report: PrimePostMortemReport instance.
        output_dir: Run output directory.  When provided, observability
            artifact quality data is scanned to generate ``obs_*``
            suggestions that close the feedback loop (REQ-KZ-OBS-600).

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
        suggestions.append(
            {
                "pattern": getattr(pattern, "description", ""),
                "pattern_type": pattern_type,
                "frequency": pattern.frequency,
                "suggested_action": template["hint"],
                "config_key": "prompt_hints",
                "phase": template["phase"],
                "confidence": "high" if pattern.frequency >= 3 else "medium",
                "auto_applicable": False,
            }
        )

    # Scan per-feature semantic_issues for recurring categories (e.g. sql_injection_risk).
    # When 2+ features share the same semantic issue category, generate a suggestion
    # from CAUSE_TO_SUGGESTION if a matching entry exists.
    semantic_category_features: Dict[str, List[str]] = {}
    for fpm in getattr(report, "features", []) or []:
        issue_summary = getattr(fpm, "semantic_issue_summary", {})
        if callable(issue_summary):
            issue_summary = issue_summary()  # property returns dict
        if not isinstance(issue_summary, dict):
            continue
        feature_name = getattr(fpm, "feature_name", "unknown")
        for category in issue_summary:
            semantic_category_features.setdefault(category, []).append(feature_name)

    for category, affected in semantic_category_features.items():
        if len(affected) < _CROSS_FEATURE_PATTERN_MIN:
            continue
        # Map category to CAUSE_TO_SUGGESTION key (e.g. "sql_injection_risk" -> "sql_injection_detected")
        suggestion_key = _SEMANTIC_CATEGORY_TO_SUGGESTION.get(category)
        if not suggestion_key:
            continue
        template = CAUSE_TO_SUGGESTION.get(suggestion_key)
        if not template:
            continue
        suggestions.append(
            {
                "pattern": f"Semantic issue '{category}' found in {len(affected)} features",
                "pattern_type": suggestion_key,
                "frequency": len(affected),
                "suggested_action": template["hint"],
                "config_key": (
                    template.get("confidence", "prompt_hints")
                    if isinstance(template.get("confidence"), str)
                    else "prompt_hints"
                ),
                "phase": template["phase"],
                "confidence": "high" if len(affected) >= 3 else "medium",
                "auto_applicable": False,
            }
        )

    # --- Observability artifact feedback loop (REQ-KZ-OBS-600) ---
    # Scan observability-quality.json for issues that map to obs_* suggestions.
    # These issues live outside the code-generation postmortem report, so they
    # need a separate scan path.
    if output_dir:
        obs_data = _load_observability_quality(output_dir)
        if obs_data:
            _append_obs_suggestions(obs_data, suggestions)

    return suggestions


def _load_observability_quality(output_dir: str) -> Optional[Dict[str, Any]]:
    """Load observability_artifacts data from available quality files."""
    out = Path(output_dir)
    candidates = [
        out / "kaizen-metrics.json",
        out / "observability-quality.json",
        out.parent / "observability" / "observability-quality.json",
    ]
    for path in candidates:
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                obs = data.get("observability_artifacts")
                if obs:
                    return obs
            except (json.JSONDecodeError, OSError):
                continue
    return None


def _append_obs_suggestions(
    obs: Dict[str, Any],
    suggestions: List[Dict[str, Any]],
) -> None:
    """Scan observability quality data and append obs_* suggestions.

    Examines per-service evaluations for issues that map to
    CAUSE_TO_SUGGESTION obs_* entries.  Each issue category that
    affects 1+ services generates a suggestion (threshold=1 since
    observability artifacts are per-service, not per-feature).
    """
    # Collect issue categories across services
    category_services: Dict[str, List[str]] = {}
    for svc_eval in obs.get("service_evaluations", []):
        svc_id = svc_eval.get("service_id", "unknown")
        for issue in svc_eval.get("issues", []):
            check = issue.get("check", "") if isinstance(issue, dict) else ""
            cat = _obs_check_to_category(check)
            if cat:
                category_services.setdefault(cat, []).append(svc_id)

        # Detect missing artifact types (score == 0 means missing)
        if svc_eval.get("slo_score", 1.0) == 0.0:
            category_services.setdefault("obs_missing_availability_slo", []).append(
                svc_id
            )

    # Cross-artifact issues
    cross = obs.get("cross_artifact_issues", {})
    if cross.get("unvisualized_alerts", 0) > 0:
        category_services.setdefault("obs_missing_red_panels", []).append(
            "cross-artifact"
        )
    if cross.get("misaligned_thresholds", 0) > 0:
        category_services.setdefault("obs_threshold_mismatch", []).append(
            "cross-artifact"
        )

    # Emit suggestions for each observed category
    seen_types = {s.get("pattern_type") for s in suggestions}
    for cat, services in category_services.items():
        if cat in seen_types:
            continue  # already have this suggestion from code-gen scan
        suggestion_key = _SEMANTIC_CATEGORY_TO_SUGGESTION.get(cat, cat)
        template = CAUSE_TO_SUGGESTION.get(suggestion_key)
        if not template:
            continue
        suggestions.append(
            {
                "pattern": f"Observability issue '{cat}' in {len(services)} service(s): {', '.join(services[:5])}",
                "pattern_type": suggestion_key,
                "frequency": len(services),
                "suggested_action": template["hint"],
                "config_key": "prompt_hints",
                "phase": template["phase"],
                "confidence": "high" if len(services) >= 2 else "medium",
                "auto_applicable": False,
            }
        )


def _obs_check_to_category(check_id: str) -> Optional[str]:
    """Map an OBS-xxx check ID to an obs_* CAUSE_TO_SUGGESTION category."""
    _MAP = {
        "OBS-103": "obs_phantom_service",
        "OBS-200a": "obs_missing_red_panels",
        "OBS-200c": "obs_phantom_service",
        "OBS-202a": "obs_slo_target_mismatch",
        "OBS-202d": "obs_missing_availability_slo",
        "OBS-203b": "obs_transport_metric_mismatch",
    }
    return _MAP.get(check_id)


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
        semantic_repair_data: Optional[Dict[str, Any]] = None,
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
                    feature_dict,
                    hist_entry,
                    seed_task,
                    fid,
                    force_regenerated=is_force_regen,
                )
                report.features.append(fpm)
                all_elements.extend(fpm.elements)
            except Exception:
                logger.warning("Error evaluating feature %s", fid, exc_info=True)
                # Create a minimal entry so the feature isn't silently dropped
                fd = feature_dict if isinstance(feature_dict, dict) else {}
                report.features.append(
                    FeaturePostMortem(
                        feature_id=fid,
                        name=fd.get("name", fid),
                        status=fd.get("status", "unknown"),
                        success=False,
                        error_message="Post-mortem evaluation error",
                        root_cause=RootCause.UNKNOWN,
                        pipeline_stage=PipelineStage.UNKNOWN,
                        verdict="ERROR",
                    )
                )

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

        # Build determinism metrics (REQ-DET-METRIC) — measures the $0/no-LLM fraction
        report.determinism = self._build_determinism_metrics(report.features)

        # Disk quality evaluation (opt-in when project_root provided)
        if project_root:
            # Aggregate semantic repair data from history entries (DC-3 dual scoring)
            aggregated_repair: Dict[str, Any] = semantic_repair_data or {}
            if not aggregated_repair:
                # Fallback: collect from per-feature history entries
                agg_pre: Dict[str, float] = {}
                agg_per_file: Dict[str, Dict] = {}
                for entry in history:
                    sem = entry.get("semantic_repair")
                    if isinstance(sem, dict):
                        agg_pre.update(sem.get("pre_repair_scores", {}))
                        agg_per_file.update(sem.get("per_file", {}))
                if agg_pre or agg_per_file:
                    aggregated_repair = {
                        "pre_repair_scores": agg_pre,
                        "per_file": agg_per_file,
                    }

            self._evaluate_disk_quality(
                report.features,
                project_root,
                forward_manifest,
                seed_by_id=seed_by_id,
                semantic_repair_data=aggregated_repair if aggregated_repair else None,
                history_by_id=history_by_id,
            )
            # RUN-008 FR-10: cross-file integrity (Prisma↔Zod symmetry) over the
            # whole generated set. The per-file disk pass above cannot see this —
            # tsc can't either (excess-property checks suppressed on spreads), so
            # this is the only surface that catches the run-008 failure class.
            self._evaluate_cross_file_integrity(report.features, project_root)
            # RUN-008 FR-4/5/9: project-level tsc --noEmit + prisma generate catches
            # the compile-class (unresolvable imports, invalid Prisma where-usage).
            # Env-gated (STARTD8_TS_TYPECHECK) — only runs where the host provisions
            # the Node toolchain (OQ-3). Toolchain-absent is surfaced, never a silent PASS.
            self._evaluate_ts_toolchain(report.features, project_root)
            # OQ-5: project-level Python build gate (compileall + mypy) over a generated
            # all-Python backend (backend_codegen path). Env-gated (STARTD8_PY_TYPECHECK);
            # mypy import-resolution noise from absent app deps is treated as infra, not fault.
            self._evaluate_python_toolchain(report.features, project_root)
            # C-6 runtime boot-smoke: actually BOOT the generated app (target resolved from
            # the scaffold manifest + on-disk entrypoints — see resolve_app_target, F-5)
            # and confirm it serves /openapi.json. Catches the import-class that
            # compileall/mypy/structural scoring miss (run-021..026: `from ai.x` wrong root, bare
            # `import get_session` — modules that pass syntax but fail at import). Default-on;
            # gracefully degrades to a warning (never a silent PASS) when app deps aren't installed.
            self._evaluate_boot_smoke(report.features, project_root)
            # Compute avg_assembly_delta across features that have disk scores
            deltas = [
                f.assembly_delta
                for f in report.features
                if f.assembly_delta is not None
            ]
            if deltas:
                report.avg_assembly_delta = sum(deltas) / len(deltas)
                # Cross-feature pattern: large assembly quality gap
                large_gaps = [
                    f.feature_id
                    for f in report.features
                    if f.assembly_delta is not None and f.assembly_delta > 0.2
                ]
                if len(large_gaps) >= 2:
                    report.cross_feature_patterns.append(
                        CrossFeaturePattern(
                            pattern_type="assembly_quality_gap",
                            description=(
                                f"Assembly degrades quality by >0.2 in "
                                f"{len(large_gaps)} features"
                            ),
                            affected_features=large_gaps,
                            frequency=len(large_gaps),
                            severity="high" if len(large_gaps) >= 3 else "medium",
                        )
                    )

            # Recompute aggregate score using disk quality scores so that
            # semantic validation findings influence the PASS/FAIL verdict.
            # Features without a disk score keep their binary 1.0/0.0.
            disk_scores = []
            for f in report.features:
                if f.disk_quality_score is not None:
                    disk_scores.append(f.disk_quality_score)
                else:
                    disk_scores.append(1.0 if f.success else 0.0)
            if disk_scores:
                report.aggregate_score = sum(disk_scores) / len(disk_scores)

            # Recount successes — disk evaluation may have flipped
            # feature verdicts via the semantic verdict gate.
            report.successful_features = sum(1 for f in report.features if f.success)
            report.failed_features = report.total_features - report.successful_features

            # Re-evaluate verdict with updated score.
            if report.aggregate_score >= _PASS_THRESHOLD:
                report.aggregate_verdict = "PASS"
            elif report.aggregate_score >= _PARTIAL_THRESHOLD:
                report.aggregate_verdict = "PARTIAL"
            else:
                report.aggregate_verdict = "FAIL"

            # REQ-CKG-245 (aggregate any-error rule): a cross-file contract error is
            # build-breaking, so it caps the batch verdict at FAIL regardless of the mean
            # disk score — which otherwise dilutes a single failing feature away (one zeroed
            # feature in ~13 still averages ≈0.92 ≥ PASS threshold, reproducing the inversion).
            report.aggregate_verdict = self._cap_verdict_on_cross_file_errors(
                report.features, report.aggregate_verdict
            )

        # F-3 verdict floor (RUN-006): a run in which NOTHING completed can never read as
        # PASS, regardless of what the disk-quality mean says. RUN-006 scored PASS/1.00
        # with successful=0 because its one failed feature generated no files, so disk
        # validation fell back to its target_files and scored the PRE-EXISTING file on
        # disk a vacuous 1.0 — which the disk-score recompute then averaged into a
        # perfect run. Zero successful completions ⇒ FAIL / 0.0, unconditionally.
        if report.total_features > 0 and report.successful_features == 0:
            report.aggregate_score = 0.0
            report.aggregate_verdict = "FAIL"

        # Extract lessons
        report.lessons = self._extract_lessons(report)

        # Write outputs (stash result_dict for _write_outputs to merge query_security)
        self._result_dict = result_dict
        try:
            self._write_outputs(report, output_dir)
        except Exception:
            logger.warning("Failed to write postmortem outputs", exc_info=True)
        finally:
            self._result_dict = None  # don't hold reference after write

        # Extract exemplars from perfect-scoring features (REQ-PEP-000)
        try:
            self._extract_exemplars(report, output_dir)
        except Exception:
            logger.debug("Exemplar extraction failed (non-fatal)", exc_info=True)

        # Run TODO scanner on generated files (REQ-TCW-100)
        try:
            self._scan_todos(report, project_root, output_dir)
        except Exception:
            logger.debug("TODO scan failed (non-fatal)", exc_info=True)

        # Accumulate the Controlled Corpus (CONTROLLED_CORPUS FR-5/11)
        try:
            self._extract_corpus(report, project_root, output_dir)
        except Exception:
            logger.debug("Corpus extraction failed (non-fatal)", exc_info=True)

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

        # F-3 attribution (RUN-006 §3.2): thread who-made-the-call through to the report.
        # The prime contractor stamps feature.metadata["failure_attribution"] at the
        # failure site and mirrors agent/model/provider onto history entries, so a failed
        # LLM call is never reported as agent/model/provider: null when the failure site
        # knew the answer.
        meta_attr = (feature_dict.get("metadata") or {}).get("failure_attribution") or {}
        hist = history_entry or {}
        agent = hist.get("agent") or meta_attr.get("agent")
        model = hist.get("model") or meta_attr.get("model")
        provider = hist.get("provider") or meta_attr.get("provider")
        if not success and pipeline_stage == PipelineStage.UNKNOWN:
            stage_str = str(hist.get("pipeline_stage") or meta_attr.get("stage") or "")
            try:
                pipeline_stage = PipelineStage(stage_str)
            except ValueError:
                if stage_str == "quality_gate":
                    pipeline_stage = PipelineStage.GENERATION

        # Extract cost from history
        cost_usd = 0.0
        if history_entry:
            cost_usd = history_entry.get("cost_usd", 0.0) or 0.0

        # Determinism provenance (REQ-DET-METRIC) — stamped on feature.metadata by the
        # prime-contractor no-LLM shortcuts; absent for normal LLM-authored features.
        generation_path = (feature_dict.get("metadata") or {}).get(
            "generation_path", "llm"
        )
        deterministic = generation_path != "llm"

        # File coverage — generated_files are often absolute paths while
        # target_files are relative, so check suffix match (endswith) to
        # handle the path-prefix mismatch.
        target_files = feature_dict.get("target_files", [])
        generated_files = feature_dict.get("generated_files", [])
        missing_files = [
            f
            for f in target_files
            if not any(g == f or g.endswith("/" + f) for g in generated_files)
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

                # Thread repair attribution — the data exists in element
                # results, we just need to read it so Kaizen can correlate
                # "what broke" with prompt characteristics.
                raw_attr = er.get("repair_attribution")
                repair_attr = None
                if isinstance(raw_attr, dict):
                    repair_attr = raw_attr
                elif raw_attr is not None and hasattr(raw_attr, "model_dump"):
                    repair_attr = raw_attr.model_dump()

                elements.append(
                    ElementPostMortem(
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
                        ast_valid_before_repair=er.get("ast_valid_before_repair"),
                        repair_attribution=repair_attr,
                    )
                )

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
            generation_path=generation_path,
            deterministic=deterministic,
            agent=agent,
            model=model,
            provider=provider,
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

    def _evaluate_cross_file_integrity(
        self,
        features: List[FeaturePostMortem],
        project_root: str,
    ) -> None:
        """RUN-008 FR-10 — Prisma↔Zod symmetry across the generated batch.

        Runs once over the whole file set, attributes each error to the feature
        that produced the offending Zod file, and forces that feature to FAIL
        (``disk_quality_score=0``, ``success=False``) with a
        ``cross_file_contract`` root cause and ``cross_feature_contract`` stage,
        plus error-severity semantic issues the Kaizen loop turns into
        suggestions. No-op when the batch has no ``.prisma`` + Zod pair, so
        non-TS/Prisma runs are unaffected (no false positives).
        """
        try:
            from startd8.validators.cross_file_verifier import run_checks
            from startd8.forward_manifest_validator import DiskComplianceResult
        except ImportError:
            logger.debug("Cross-file integrity check unavailable — skipping")
            return

        # Map each generated file path → owning feature, and read its content.
        # REQ-CKG-236: a declared-but-unmaterialized file is recorded as unverified,
        # never silently dropped (a missing flush must not look like a clean batch).
        path_to_feature: Dict[str, FeaturePostMortem] = {}
        sources: Dict[str, str] = {}
        not_materialized: List[str] = []
        for fpm in features:
            for fp in fpm.generated_files or fpm.target_files:
                if not str(fp).endswith((".prisma", ".ts", ".tsx")):
                    continue
                candidate = (
                    Path(fp) if Path(fp).is_absolute() else Path(project_root) / fp
                )
                try:
                    if candidate.is_file():
                        sources[fp] = candidate.read_text(
                            encoding="utf-8", errors="replace"
                        )
                        path_to_feature[fp] = fpm
                    else:
                        not_materialized.append(str(fp))
                except OSError:
                    not_materialized.append(str(fp))
        if not_materialized:
            logger.warning(
                "cross-file: %d generated file(s) not materialized on disk — unverified "
                "(skipped_not_materialized): %s",
                len(not_materialized),
                not_materialized[:5],
            )

        # Inc-4: delegate to the unified verifier (REQ-CKG-600) — the 5 shipped signatures
        # (Zod↔Prisma symmetry, unresolvable @/ import, missing dependency, Prisma call-site
        # misuse) + tsconfig path-alias existence + the SCIP-backed external-type check.
        # REQ-CKG-690a proves this is behaviour-preserving for the 5 signatures. The SCIP
        # index is env-gated (STARTD8_CKG_SCIP) so existing runs/CI without a Node toolchain
        # are unaffected; absent -> the external check is skipped_unavailable (advisory,
        # never a silent PASS — REQ-CKG-230).
        scip = None
        import os

        if os.environ.get("STARTD8_CKG_SCIP"):
            try:
                from startd8.code_observability import run_index
                from startd8.code_observability.scip_reader import ScipReader

                _idx = run_index(project_root)
                scip = ScipReader.from_path(_idx) if _idx else None
            except Exception:
                logger.warning(
                    "cross-file: SCIP index unavailable — external check advisory",
                    exc_info=True,
                )

        findings = run_checks(sources, project_root, scip=scip).errors
        if not findings:
            return

        # Attribute findings to the feature that produced the Zod file; if the
        # source file can't be mapped, fall back to the feature owning the
        # Prisma schema (the producer side of the seam).
        prisma_feature = next(
            (
                fpm
                for fpm in features
                if any(
                    str(f).endswith(".prisma")
                    for f in (fpm.generated_files or fpm.target_files)
                )
            ),
            None,
        )
        by_feature: Dict[int, List[Any]] = {}
        for f in findings:
            owner = path_to_feature.get(f.source_file) if f.source_file else None
            owner = owner or prisma_feature
            if owner is None:
                continue
            by_feature.setdefault(id(owner), []).append(f)

        for fpm in features:
            fs = by_feature.get(id(fpm))
            if not fs:
                continue
            if fpm.disk_compliance is None:
                fpm.disk_compliance = DiskComplianceResult(file_path=fpm.feature_id)
            for f in fs:
                fpm.disk_compliance.semantic_issues.append(
                    {
                        "category": f.kind,
                        "severity": "error",
                        "message": f.message,
                    }
                )
            # Hard FAIL: cross-file incoherence is not a successful generation
            # regardless of per-file syntax or requirement score.
            fpm.disk_quality_score = 0.0
            fpm.success = False
            if fpm.verdict not in ("FAIL", "FAIL:semantic", "FAIL:disk_quality"):
                fpm.verdict = "FAIL:cross_file"
            if fpm.root_cause == RootCause.UNKNOWN:
                fpm.root_cause = RootCause.CROSS_FILE_CONTRACT
            if fpm.pipeline_stage == PipelineStage.UNKNOWN:
                fpm.pipeline_stage = PipelineStage.CROSS_FEATURE_CONTRACT
            fpm.semantic_error_count += len(fs)
            if not fpm.error_message:
                shown = "; ".join(f"{f.kind}:{f.locus}" for f in fs[:4])
                more = "" if len(fs) <= 4 else f" (+{len(fs) - 4} more)"
                fpm.error_message = f"cross-file contract violations: {shown}{more}"

    @staticmethod
    def _cap_verdict_on_cross_file_errors(features: List[Any], verdict: str) -> str:
        """REQ-CKG-245: any error-severity cross-file finding caps the batch verdict at FAIL.

        Independent of the mean disk score, which dilutes a single build-breaking failure
        away (one zeroed feature in ~13 averages ≈0.92 ≥ the PASS threshold). A feature that
        `_evaluate_cross_file_integrity` flipped to ``FAIL:cross_file`` forces the run to FAIL.
        """
        if any(getattr(f, "verdict", "") == "FAIL:cross_file" for f in features):
            return "FAIL"
        return verdict

    def _evaluate_ts_toolchain(
        self,
        features: List[FeaturePostMortem],
        project_root: str,
    ) -> None:
        """RUN-008 FR-4/5/9 — project-level ``tsc --noEmit`` + ``prisma generate``.

        Env-gated via ``STARTD8_TS_TYPECHECK`` (off by default) so existing runs
        and CI without a Node toolchain are unaffected. When enabled and the
        batch has TS files:
        - real diagnostics → the owning feature(s) FAIL (`cross_file_contract`);
        - toolchain unavailable → a warning is recorded on TS features (FR-9:
          surfaced, never a silent PASS) without flipping success (absence of a
          provisioned toolchain is an operator/infra condition, not a code fault).
        """
        try:
            from startd8.validators.ts_toolchain import (
                diagnostics_by_file,
                run_project_typecheck,
                typecheck_enabled,
            )
            from startd8.forward_manifest_validator import DiskComplianceResult
        except ImportError:
            return
        if not typecheck_enabled():
            return

        ts_exts = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
        path_to_feature: Dict[str, FeaturePostMortem] = {}
        for fpm in features:
            for fp in fpm.generated_files or fpm.target_files:
                if str(fp).endswith(ts_exts):
                    path_to_feature[Path(fp).name] = fpm
        if not path_to_feature:
            return  # no TS in this batch — nothing to typecheck

        result = run_project_typecheck(project_root)

        if result.verdict == "unavailable":
            # FR-9: do not silently pass an unverifiable TS project — annotate.
            for fpm in {id(f): f for f in path_to_feature.values()}.values():
                if fpm.disk_compliance is None:
                    fpm.disk_compliance = DiskComplianceResult(file_path=fpm.feature_id)
                fpm.disk_compliance.semantic_issues.append(
                    {
                        "category": "ts_verification_unavailable",
                        "severity": "warning",
                        "message": f"TypeScript typecheck unavailable: {result.message}",
                    }
                )
            logger.warning(
                "FR-9: TS typecheck enabled but toolchain unavailable (%s) — "
                "TS features unverified, not silently passed.",
                result.message,
            )
            return

        if result.verdict == "pass":
            return

        # verdict == "fail": attribute each diagnostic to the owning feature.
        by_file = diagnostics_by_file(result.diagnostics)
        affected: Dict[int, FeaturePostMortem] = {}
        for file_key, diags in by_file.items():
            base = Path(file_key).name
            fpm = path_to_feature.get(base)
            if fpm is None:
                continue
            affected[id(fpm)] = fpm
            if fpm.disk_compliance is None:
                fpm.disk_compliance = DiskComplianceResult(file_path=fpm.feature_id)
            for d in diags:
                fpm.disk_compliance.semantic_issues.append(
                    {
                        "category": f"tsc_{d.code}",
                        "severity": "error",
                        "message": f"{d.code} {Path(d.file).name}:{d.line} {d.message}",
                    }
                )
            fpm.semantic_error_count += len(diags)
        for fpm in affected.values():
            fpm.disk_quality_score = 0.0
            fpm.success = False
            if fpm.verdict not in (
                "FAIL",
                "FAIL:semantic",
                "FAIL:disk_quality",
                "FAIL:cross_file",
            ):
                fpm.verdict = "FAIL:typecheck"
            if fpm.root_cause == RootCause.UNKNOWN:
                fpm.root_cause = RootCause.CROSS_FILE_CONTRACT
            if fpm.pipeline_stage == PipelineStage.UNKNOWN:
                fpm.pipeline_stage = PipelineStage.CROSS_FEATURE_CONTRACT
            if not fpm.error_message:
                fpm.error_message = "tsc --noEmit reported errors (see semantic_issues)"

    def _evaluate_python_toolchain(
        self,
        features: List[FeaturePostMortem],
        project_root: str,
    ) -> None:
        """OQ-5 — project-level Python build gate over a generated all-Python backend.

        The Python sibling of :meth:`_evaluate_ts_toolchain` for the contract-codegen path
        (``backend_codegen``). Env-gated via ``STARTD8_PY_TYPECHECK`` (off by default). When
        enabled and the batch has ``.py`` files:
        - real ``compileall``/``mypy`` faults → the owning feature(s) FAIL (`cross_file_contract`);
        - toolchain unavailable → surfaced as a warning (FR-9: never a silent PASS).

        ``mypy`` import-resolution noise ("cannot find stub for fastapi/sqlmodel/...") is filtered:
        the generated app's third-party deps may be absent from the *run host*, which is an
        infra/provisioning condition (like missing ``node_modules`` for the TS gate), not a code
        fault. Real type/name faults still fail. ``pytest`` is not run (gen-gate, not a test run).
        """
        try:
            from startd8.validators.python_toolchain import (
                python_typecheck_enabled,
                run_project_check,
            )
            from startd8.forward_manifest_validator import DiskComplianceResult
        except ImportError:
            return
        if not python_typecheck_enabled():
            return

        path_to_feature: Dict[str, FeaturePostMortem] = {}
        for fpm in features:
            for fp in fpm.generated_files or fpm.target_files:
                if str(fp).endswith(".py"):
                    path_to_feature[Path(fp).name] = fpm
        if not path_to_feature:
            return  # no Python in this batch — nothing to gate

        result = run_project_check(project_root, run_mypy=True, run_pytest=False)

        if result.status != "checked":
            for fpm in {id(f): f for f in path_to_feature.values()}.values():
                if fpm.disk_compliance is None:
                    fpm.disk_compliance = DiskComplianceResult(file_path=fpm.feature_id)
                fpm.disk_compliance.semantic_issues.append(
                    {
                        "category": "py_verification_unavailable",
                        "severity": "warning",
                        "message": f"Python build gate unavailable: {result.message}",
                    }
                )
            logger.warning(
                "FR-9: Python gate enabled but toolchain unavailable (%s) — "
                "Python features unverified, not silently passed.",
                result.message,
            )
            return

        # Drop mypy import-resolution noise (absent third-party deps = provisioning) — but NOT for
        # FIRST-PARTY (`app.*`) imports. A first-party `import-not-found` is the C-3 bug class
        # (e.g. `from app.models import AiCall` when AiCall lives in app.tables; or `from ai.x`
        # with the wrong package root): a real fault that boot would hit. run-021/023/024/025 all
        # produced exactly this, and the old filter swallowed it. (M4 landmine; M-E.)
        first_party_roots = _first_party_roots(project_root)
        real = [
            d
            for d in result.diagnostics
            if not _is_import_provisioning_noise(d, first_party_roots)
        ]
        if not real:
            return  # compileall floor passed; any mypy findings were provisioning noise

        affected: Dict[int, FeaturePostMortem] = {}
        for d in real:
            fpm = path_to_feature.get(Path(d.file).name)
            if fpm is None:
                continue
            affected[id(fpm)] = fpm
            if fpm.disk_compliance is None:
                fpm.disk_compliance = DiskComplianceResult(file_path=fpm.feature_id)
            fpm.disk_compliance.semantic_issues.append(
                {
                    "category": f"py_{d.stage}_{d.code or 'error'}",
                    "severity": "error",
                    "message": f"{d.stage} {Path(d.file).name}:{d.line} {d.code}: {d.message}",
                }
            )
            fpm.semantic_error_count += 1
        for fpm in affected.values():
            fpm.disk_quality_score = 0.0
            fpm.success = False
            if fpm.verdict not in (
                "FAIL",
                "FAIL:semantic",
                "FAIL:disk_quality",
                "FAIL:cross_file",
            ):
                fpm.verdict = "FAIL:typecheck"
            if fpm.root_cause == RootCause.UNKNOWN:
                fpm.root_cause = RootCause.CROSS_FILE_CONTRACT
            if fpm.pipeline_stage == PipelineStage.UNKNOWN:
                fpm.pipeline_stage = PipelineStage.CROSS_FEATURE_CONTRACT
            if not fpm.error_message:
                fpm.error_message = (
                    "Python build gate reported errors (see semantic_issues)"
                )

    def _evaluate_boot_smoke(
        self,
        features: List[FeaturePostMortem],
        project_root: str,
    ) -> None:
        """C-6 Layer 1 — boot the generated app and confirm it serves ``/openapi.json``.

        The target is resolved via ``resolve_app_target`` (F-5, RUN-008 1a-iii): package from
        the scaffold manifest (``app.yaml``) when present, then ``{package}.server:app`` (the AI
        composition entrypoint) if ``server.py`` exists, else ``{package}.main:app`` — never a
        hardcoded variant, so a healthy app passes regardless of which entrypoint was generated.
        A boot **failure** (import error, crash) marks the implicated Python feature(s)
        ``FAIL:boot`` — this is the gate that converts the run-021..026 "compiles but
        won't import" hollow PASS into an honest verdict. App deps absent ⇒ ``unavailable`` ⇒ a
        per-feature **warning**, never a silent PASS (NFR-MA-2 / FR-9). Best-effort blame: features
        whose generated filename appears in the boot trace; if none localize, the whole non-bootable
        app fails (nothing is usable — cf. run-025 "0/4 usable").
        """
        try:
            from startd8.validators.boot_smoke import resolve_app_target, run_boot_smoke
            from startd8.forward_manifest_validator import DiskComplianceResult
        except ImportError:
            return

        app_spec = resolve_app_target(project_root)
        if app_spec is None:
            return  # no generated app entrypoint to boot

        py_features: Dict[int, FeaturePostMortem] = {}
        file_names: Dict[int, List[str]] = {}
        for fpm in features:
            for fp in fpm.generated_files or fpm.target_files:
                if str(fp).endswith(".py"):
                    py_features[id(fpm)] = fpm
                    file_names.setdefault(id(fpm), []).append(Path(fp).name)
        if not py_features:
            return

        result = run_boot_smoke(project_root, app=app_spec)

        if result.verdict == "pass":
            return  # the app boots and serves OpenAPI — good

        if result.status == "unavailable":
            for fpm in py_features.values():
                if fpm.disk_compliance is None:
                    fpm.disk_compliance = DiskComplianceResult(file_path=fpm.feature_id)
                fpm.disk_compliance.semantic_issues.append(
                    {
                        "category": "boot_smoke_unavailable",
                        "severity": "warning",
                        "message": f"Boot-smoke unavailable ({app_spec}): {result.message} "
                        "— app deps not provisioned; not verified to boot, not silently passed.",
                    }
                )
            logger.warning(
                "C-6: boot-smoke unavailable (%s: %s) — app unverified, not silently passed.",
                app_spec,
                result.message,
            )
            return

        # status == checked and NOT a pass → a real boot/serve failure.
        blob = (result.message or "") + " " + " ".join(result.diagnostics)
        culprits = {
            fid: fpm
            for fid, fpm in py_features.items()
            if any(name in blob for name in file_names.get(fid, []))
        }
        affected = culprits or py_features  # can't localize → the whole app is non-bootable
        detail = result.message or "boot failed"
        if result.missing_routes:
            detail += f"; missing routes: {', '.join(result.missing_routes)}"
        for fpm in affected.values():
            if fpm.disk_compliance is None:
                fpm.disk_compliance = DiskComplianceResult(file_path=fpm.feature_id)
            fpm.disk_compliance.semantic_issues.append(
                {
                    "category": "boot_smoke_failure",
                    "severity": "error",
                    "message": f"app does not boot ({app_spec}): {detail}",
                }
            )
            fpm.semantic_error_count += 1
            fpm.disk_quality_score = 0.0
            fpm.success = False
            if not str(fpm.verdict).startswith("FAIL"):
                fpm.verdict = "FAIL:boot"
            if fpm.root_cause == RootCause.UNKNOWN:
                fpm.root_cause = RootCause.CROSS_FILE_CONTRACT
            if fpm.pipeline_stage == PipelineStage.UNKNOWN:
                fpm.pipeline_stage = PipelineStage.CROSS_FEATURE_CONTRACT
            if not fpm.error_message:
                fpm.error_message = f"Runtime boot-smoke failed: app does not boot ({app_spec})"
        logger.warning("C-6: boot-smoke FAILED (%s): %s", app_spec, detail)

    def _evaluate_disk_quality(
        self,
        features: List[FeaturePostMortem],
        project_root: str,
        forward_manifest: Optional[Any] = None,
        *,
        seed_by_id: Optional[Dict[str, Dict]] = None,
        semantic_repair_data: Optional[Dict[str, Any]] = None,
        history_by_id: Optional[Dict[str, Dict]] = None,
    ) -> None:
        """Evaluate disk compliance and compute quality scores for each feature.

        Mutates feature objects in-place to add disk_compliance,
        disk_quality_score, and assembly_delta fields.

        Args:
            seed_by_id: Optional mapping of task_id → seed task dict.
                When provided, ``import_map`` and sibling file context
                are extracted and passed to semantic validation.
            semantic_repair_data: Optional dict from ``run_semantic_repair()``.
                When provided, ``pre_repair_scores`` are used for the Kaizen
                assembly_delta (DC-3: Kaizen sees generator quality, not
                repair quality).
        """
        try:
            from startd8.forward_manifest_validator import validate_disk_compliance
        except ImportError:
            logger.debug("Disk validation unavailable — skipping")
            return

        # Pre-compute the set of all generated files for sibling resolution.
        all_generated: List[str] = []
        for fpm in features:
            all_generated.extend(
                fpm.generated_files if fpm.generated_files else fpm.target_files
            )

        # L5: Build sibling_imports per directory for requirements cross-check.
        # Maps directory → {file_path: {import_module_names}}.
        _dir_imports: Dict[str, Dict[str, Set[str]]] = {}
        for gen_file in all_generated:
            gen_path = Path(gen_file)
            if gen_path.suffix != ".py":
                continue
            try:
                if not gen_path.is_file():
                    continue
                tree = ast.parse(gen_path.read_text(encoding="utf-8", errors="replace"))
                imports: Set[str] = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            imports.add(alias.name.split(".")[0])
                            imports.add(alias.name)
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        if not node.level:  # skip relative imports
                            imports.add(node.module.split(".")[0])
                            imports.add(node.module)
                parent_dir = str(gen_path.parent)
                _dir_imports.setdefault(parent_dir, {})[gen_file] = imports
            except (OSError, SyntaxError):
                pass

        for fpm in features:
            # F-3 vacuous-score guard (RUN-006): a FAILED feature that generated nothing
            # has no disk output of its own to validate. Falling back to target_files
            # here would score whatever pre-existing file sits at the target path (the
            # healthy seam file, in RUN-006's case) a perfect 1.0 — false evidence that
            # then lifts the aggregate. Skip; the feature keeps its honest 0.0.
            if not fpm.success and not fpm.generated_files:
                continue
            # Prefer generated_files (absolute paths to actual output) over
            # target_files (relative paths that may not exist at project root).
            files_to_check = (
                fpm.generated_files if fpm.generated_files else fpm.target_files
            )
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

                    # Build sibling files for import resolution (same directory)
                    effective_parent = str(Path(effective_file).parent)
                    sibling_files = [
                        f
                        for f in all_generated
                        if str(Path(f).parent) == effective_parent
                        and f != effective_file
                    ]

                    # Extract import_map from seed task if available
                    import_map = None
                    if seed_by_id:
                        seed_task = seed_by_id.get(fpm.feature_id, {})
                        import_map = seed_task.get("import_map")

                    # L5: Resolve sibling_imports for this file's directory.
                    abs_parent = str(Path(effective_root) / effective_parent)
                    sib_imports = _dir_imports.get(abs_parent)

                    compliance = validate_disk_compliance(
                        effective_file,
                        effective_root,
                        forward_manifest,
                        sibling_files=sibling_files if sibling_files else None,
                        sibling_imports=sib_imports,
                        import_map=import_map,
                    )
                    fpm.disk_compliance = compliance

                    # Compute disk quality score (P3-2: language-aware severity)
                    _ext = Path(file_path).suffix.lower()
                    _EXT_LANG = {
                        ".py": "python",
                        ".go": "go",
                        ".java": "java",
                        ".kt": "java",
                        ".cs": "csharp",
                        ".csproj": "csharp",
                        ".js": "nodejs",
                        ".ts": "nodejs",
                        ".mjs": "nodejs",
                        ".cjs": "nodejs",
                        ".jsx": "nodejs",
                        ".tsx": "nodejs",
                    }
                    _lang = _EXT_LANG.get(_ext)
                    fpm.disk_quality_score = compute_disk_quality_score(
                        compliance,
                        language_id=_lang,
                    )

                    # Merge Anzen gate findings into semantic_issues so the
                    # Kaizen feedback loop can see security findings (Issues #1-4
                    # from security pipeline audit).
                    _hist = (history_by_id or {}).get(fpm.feature_id, {})
                    anzen_data = _hist.get("anzen_gate") or []
                    for ag_entry in anzen_data:
                        if not isinstance(ag_entry, dict):
                            continue
                        ag_file = ag_entry.get("file_path", "")
                        if not ag_file or not effective_file.endswith(
                            Path(ag_file).name
                        ):
                            continue
                        for finding in ag_entry.get("findings", []):
                            if not isinstance(finding, dict):
                                continue
                            compliance.semantic_issues.append(
                                {
                                    "category": f"query_security_{finding.get('check_type', 'unknown')}",
                                    "severity": finding.get("severity", "error"),
                                    "message": finding.get("message", ""),
                                    "line": finding.get("line"),
                                }
                            )

                    # Count error-severity semantic issues for Kaizen label.
                    sem_issues = getattr(compliance, "semantic_issues", []) or []
                    err_count = sum(
                        1
                        for i in sem_issues
                        if isinstance(i, dict) and i.get("severity") == "error"
                    )
                    fpm.semantic_error_count = err_count

                    # Critical-category gate (M3 run-021): some semantic issues
                    # are individually disqualifying — a single occurrence means
                    # the feature is non-functional, so it cannot score
                    # "complete" no matter how high the requirement_score. A
                    # `fake_work_stub` handler simulates work with sleep() and
                    # returns canned data without calling the real modules: it
                    # compiles and passes shallow checks but does nothing. One is
                    # enough to fail the feature (the "PASS on a non-working
                    # feature" trap).
                    has_critical_semantic = any(
                        isinstance(i, dict)
                        and i.get("category") in _CRITICAL_SEMANTIC_CATEGORIES
                        for i in sem_issues
                    )

                    # Semantic verdict gate: error-severity issues downgrade
                    # the verdict so Kaizen correlations learn from semantic
                    # failures, not just syntactic ones.
                    if has_critical_semantic and fpm.verdict not in (
                        "FAIL",
                        "FAIL:semantic",
                        "FAIL:disk_quality",
                    ):
                        fpm.verdict = "FAIL:semantic"
                        fpm.success = False
                    elif err_count >= 2 and fpm.verdict == "PASS":
                        fpm.verdict = "PARTIAL:semantic"
                    elif err_count >= 4 and fpm.verdict in (
                        "PASS",
                        "PARTIAL",
                        "PARTIAL:semantic",
                    ):
                        fpm.verdict = "FAIL:semantic"
                        fpm.success = False

                    # NR-10: Disk quality floor — a file that cannot parse or
                    # has critical structural defects is not a successful
                    # generation regardless of requirement_score.
                    if (
                        fpm.disk_quality_score is not None
                        and fpm.disk_quality_score < 0.3
                        and fpm.verdict not in ("FAIL", "FAIL:semantic")
                    ):
                        fpm.verdict = "FAIL:disk_quality"
                        fpm.success = False
                        # Surface the disk-validation diagnostic. This flip can
                        # downgrade a feature the generator reported as success,
                        # so root_cause/stage were never classified — leaving a
                        # blind "unknown/unknown/none" in the report. Derive them
                        # from the disk_compliance result instead.
                        _disk_err = getattr(compliance, "error", "") or ""
                        if fpm.root_cause == RootCause.UNKNOWN:
                            fpm.root_cause = RootCause.AST_FAILURE
                        if fpm.pipeline_stage == PipelineStage.UNKNOWN:
                            fpm.pipeline_stage = PipelineStage.INTEGRATION
                        if not fpm.error_message and _disk_err:
                            fpm.error_message = _disk_err

                    # Semantic repair dual scoring (DC-3, REQ-SR)
                    pre_scores = (semantic_repair_data or {}).get(
                        "pre_repair_scores", {}
                    )
                    per_file_data = (semantic_repair_data or {}).get("per_file", {})
                    pre_score = pre_scores.get(file_path) or pre_scores.get(
                        str(abs_file)
                    )
                    if pre_score is not None:
                        fpm.pre_semantic_repair_score = pre_score
                    file_repair = per_file_data.get(file_path) or per_file_data.get(
                        str(abs_file)
                    )
                    if isinstance(file_repair, dict):
                        fpm.semantic_repairs_applied = file_repair.get("repaired", 0)
                        fpm.semantic_repair_categories = file_repair.get(
                            "categories", []
                        )

                    # Assembly delta: use pre-repair score for Kaizen (generator quality)
                    # and post-repair score for display (output quality).
                    if fpm.disk_quality_score is not None:
                        kaizen_score = (
                            pre_score
                            if pre_score is not None
                            else fpm.disk_quality_score
                        )
                        fpm.assembly_delta = fpm.requirement_score - kaizen_score
                except Exception as exc:
                    # Disk validation is deterministic for normal inputs, so a
                    # failure here is almost always a 100%-reproducing bug (e.g.
                    # the ast.Str removal that silently zeroed all disk scoring),
                    # not a per-file edge case. Log LOUD (warning + traceback) so
                    # such poison surfaces in Loki instead of vanishing at debug,
                    # while still degrading gracefully rather than crashing the
                    # whole post-mortem.
                    logger.warning(
                        "Disk validation failed for %s in %s: %s",
                        file_path,
                        fpm.feature_id,
                        exc,
                        exc_info=True,
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
        analysis.escalated_elements = sum(1 for e in elements if e.escalation_reason)

        # Tier distribution
        tier_counter: Counter = Counter()
        esc_counter: Counter = Counter()
        repair_counter: Counter = Counter()
        total_time = 0.0

        attr_counter: Counter = Counter()

        for elem in elements:
            tier_counter[elem.tier] += 1
            if elem.escalation_reason:
                esc_counter[elem.escalation_reason] += 1
            for step in elem.repair_steps:
                repair_counter[step] += 1
            total_time += elem.generation_time_ms

            # Aggregate repair signal: what broke and how often.
            if elem.repair_steps:
                analysis.elements_repaired += 1
            if elem.ast_valid_before_repair is False:
                analysis.repair_before_invalid += 1
            if elem.repair_attribution:
                for key, val in elem.repair_attribution.items():
                    if isinstance(val, bool) and val:
                        attr_counter[key] += 1
                    elif isinstance(val, int) and val > 0:
                        attr_counter[key] += val

        analysis.tier_distribution = dict(tier_counter)
        analysis.escalation_reasons = dict(esc_counter)
        analysis.repair_step_distribution = dict(repair_counter)
        analysis.repair_attribution_summary = dict(attr_counter)
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
                patterns.append(
                    CrossFeaturePattern(
                        pattern_type="repeated_root_cause",
                        description=(
                            f"Root cause '{cause.value}' repeated across "
                            f"{len(fids)} features"
                        ),
                        affected_features=fids,
                        frequency=len(fids),
                        severity="high" if len(fids) >= 3 else "medium",
                    )
                )

        # Pattern 2: Repeated escalation reason — subtyped by reason (REQ-KZ-401a)
        # Track both element count (total escalations) and feature count separately.
        esc_elements: Dict[str, int] = {}  # reason → total element escalations
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
            if (
                len(unique_fids) >= _ESCALATION_MIN_FEATURES
                and element_count >= _ESCALATION_MIN_ELEMENTS
            ):
                # Dynamic severity based on scope
                if len(unique_fids) >= 5 or element_count >= 10:
                    severity = "high"
                else:
                    severity = "medium"
                patterns.append(
                    CrossFeaturePattern(
                        pattern_type=f"repeated_escalation:{reason}",
                        description=(
                            f"Escalation reason '{reason}': {element_count} elements "
                            f"across {len(unique_fids)} features"
                        ),
                        affected_features=unique_fids,
                        frequency=element_count,
                        severity=severity,
                        affected_feature_count=len(unique_fids),
                    )
                )

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
                    patterns.append(
                        CrossFeaturePattern(
                            pattern_type="cost_outlier",
                            description=(
                                f"{len(outliers)} feature(s) cost {_COST_OUTLIER_FACTOR}x+ "
                                f"average (${avg_cost:.4f})"
                            ),
                            affected_features=outliers,
                            frequency=len(outliers),
                            severity="low",
                        )
                    )

        # Pattern 4: Language mismatch in generated files (REQ-MLT-401)
        mismatch_features: List[str] = []
        for fpm in features:
            dc = fpm.disk_compliance
            if dc is not None:
                error = getattr(dc, "error", "") or ""
                if "language_mismatch" in error:
                    mismatch_features.append(fpm.feature_id)
            # Also check per-file disk results if available
            for file_dc in getattr(fpm, "per_file_disk", []) or []:
                error = getattr(file_dc, "error", "") or ""
                if "language_mismatch" in error:
                    if fpm.feature_id not in mismatch_features:
                        mismatch_features.append(fpm.feature_id)
                        break

        if len(mismatch_features) >= 2:
            patterns.append(
                CrossFeaturePattern(
                    pattern_type="language_mismatch_in_generation",
                    description=(
                        f"{len(mismatch_features)} feature(s) have language mismatch "
                        f"errors (non-Python files received Python stubs)"
                    ),
                    affected_features=mismatch_features,
                    frequency=len(mismatch_features),
                    severity="high" if len(mismatch_features) >= 3 else "medium",
                )
            )

        return patterns

    def _build_cost_summary(self, features: List[FeaturePostMortem]) -> CostSummary:
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

    def _build_determinism_metrics(
        self, features: List[FeaturePostMortem]
    ) -> DeterminismMetrics:
        """Build the deterministic-vs-LLM assembly breakdown (REQ-DET-METRIC).

        Counts both features and their generated files so the run can report what
        fraction was assembled deterministically ($0 LLM) — by feature and, more
        honestly, by file. ``by_path`` keeps the per-shortcut split (owned-kind
        provider vs corpus/copy/uncomment).
        """
        metrics = DeterminismMetrics()
        for fpm in features:
            n_files = len(fpm.generated_files)
            if fpm.deterministic:
                metrics.deterministic_features += 1
                metrics.deterministic_files += n_files
                metrics.by_path[fpm.generation_path] = (
                    metrics.by_path.get(fpm.generation_path, 0) + 1
                )
            else:
                metrics.llm_features += 1
                metrics.llm_files += n_files

        total_features = metrics.deterministic_features + metrics.llm_features
        if total_features:
            metrics.feature_ratio = metrics.deterministic_features / total_features
        total_files = metrics.deterministic_files + metrics.llm_files
        if total_files:
            metrics.file_ratio = metrics.deterministic_files / total_files

        return metrics

    def _extract_lessons(self, report: PrimePostMortemReport) -> List[Lesson]:
        """Convert patterns and failures into lessons."""
        lessons: List[Lesson] = []
        now = datetime.datetime.now().isoformat()

        # Lesson from each cross-feature pattern
        for pattern in report.cross_feature_patterns:
            severity = Severity.HIGH if pattern.severity == "high" else Severity.MEDIUM
            lessons.append(
                Lesson(
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
                )
            )

        # Lesson from dominant pipeline stage
        if report.pipeline_attribution:
            top_stage = report.pipeline_attribution[0]
            if top_stage.failure_count >= 2:
                lessons.append(
                    Lesson(
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
                        tags=[
                            "prime-contractor",
                            "pipeline-attribution",
                            top_stage.stage.value,
                        ],
                        source_phase="prime-postmortem",
                        source_context={"report_id": report.report_id},
                        created_at=now,
                    )
                )

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
        # Append observability artifacts section if available (REQ-KZ-OBS-502)
        obs_section = self._render_observability_section(output_dir)
        if obs_section:
            md_content += obs_section
        md_path.write_text(md_content, encoding="utf-8")
        logger.info("Post-mortem summary: %s", md_path)

        # Lessons JSON
        if report.lessons:
            lessons_path = out / "prime-postmortem-lessons.json"
            lessons_data = [dataclasses.asdict(ln) for ln in report.lessons]
            lessons_json = json.dumps(lessons_data, indent=2, default=str)
            lessons_path.write_text(lessons_json, encoding="utf-8")
            logger.info("Post-mortem lessons: %s", lessons_path)

        # Auto-emit kaizen suggestions (REQ-KZ-501 auto-emit)
        # Previously required explicit --emit-suggestions flag on the script.
        # Now emitted automatically so the next run can auto-discover them.
        try:
            suggestions = generate_kaizen_suggestions(report, output_dir=output_dir)
            if suggestions:
                suggestions_path = out / "kaizen-suggestions.json"
                suggestions_data = {
                    "schema_version": "1.0",
                    "source_run": report.report_id,
                    "prompt_hints": suggestions,
                }
                suggestions_path.write_text(
                    json.dumps(suggestions_data, indent=2, default=str),
                    encoding="utf-8",
                )
                logger.info(
                    "Kaizen suggestions auto-emitted: %s (%d hints)",
                    suggestions_path,
                    len(suggestions),
                )
        except Exception:
            logger.debug(
                "Kaizen suggestion auto-emit failed (non-fatal)", exc_info=True
            )

        # REQ-QPA-100: Merge query_security into pipeline-output kaizen-metrics.json.
        # The Anzen gate writes to project root; the postmortem writes to pipeline
        # output.  Bridge the gap by reading _query_security_report from result_dict
        # (stashed by finalize_anzen_metrics) and writing it to the pipeline output.
        if hasattr(self, "_result_dict") and self._result_dict:
            qp_report = self._result_dict.get("_query_security_report")
            if qp_report and qp_report.get("total_work_items", 0) > 0:
                try:
                    from startd8.security_prime.kaizen import (
                        update_query_security_metrics,
                    )

                    update_query_security_metrics(output_dir, qp_report)
                    logger.info(
                        "Query security metrics merged into pipeline output "
                        "(items=%d, score=%.2f)",
                        qp_report.get("total_work_items", 0),
                        qp_report.get("mean_score", 0.0),
                    )
                except (ImportError, OSError) as exc:
                    logger.debug("Pipeline query_security merge skipped: %s", exc)

    def _extract_exemplars(
        self,
        report: PrimePostMortemReport,
        output_dir: str,
    ) -> None:
        """Extract exemplars from features scoring 1.00 (REQ-PEP-000)."""
        from startd8.exemplars.extractor import extract_exemplars_from_run
        from startd8.exemplars.registry import ExemplarRegistry

        registry_path = Path(output_dir) / "exemplar-registry.json"
        registry = ExemplarRegistry.load(registry_path)
        extracted = extract_exemplars_from_run(output_dir, registry=registry)
        if extracted:
            promotions = registry.promote_maturity()
            registry.save(registry_path)
            logger.info(
                "Exemplars: extracted %d, promotions %d, total %d",
                len(extracted),
                len(promotions),
                len(registry),
            )

    def _extract_corpus(
        self,
        report: PrimePostMortemReport,
        project_root: Optional[str],
        output_dir: str,
    ) -> None:
        """Merge this run's terms into the persistent Controlled Corpus (FR-5/11).

        Project-scoped (accumulates across runs), unlike the run-local exemplar
        registry. Idempotent: keyed on a stable run id derived from the output dir.
        """
        import os
        from startd8.corpus.extractor import (
            extract_corpus_from_run, extract_seed_terms_from_context, stable_run_id,
        )
        from startd8.corpus.registry import ControlledCorpusRegistry
        from startd8.paths import controlled_corpus_path

        # R4-S3: operator off-switch (default on).
        if os.getenv("STARTD8_CORPUS_ENABLED", "1") not in ("1", "true", "yes", "on"):
            return

        run_id = stable_run_id(output_dir, fallback=report.report_id)
        # file-outcome terms (determinism) + vocabulary terms from the seed (R4-S1)
        observations = extract_corpus_from_run(report, run_id)
        observations += extract_seed_terms_from_context(output_dir, run_id)
        if not observations:
            return

        if project_root:
            corpus_path = controlled_corpus_path(Path(project_root))
        else:
            # R2-S1: never write to the per-run output_dir — that would defeat
            # cross-run accumulation. Fall back to a stable cwd-scoped location.
            corpus_path = controlled_corpus_path()
            logger.warning(
                "Controlled corpus: project_root not provided; accumulating at %s "
                "(cwd-scoped). Pass project_root for project-scoped accumulation.",
                corpus_path,
            )
        registry = ControlledCorpusRegistry.load(corpus_path)
        before = len(registry)
        registry.merge_run(run_id, observations)
        try:
            registry.save(corpus_path)  # R2-S2: surface save failures to operators
        except OSError as exc:
            logger.warning("Controlled corpus SAVE failed at %s: %s", corpus_path, exc)
            return
        logger.info(
            "Controlled corpus: run=%s merged %d observations, terms %d→%d",
            run_id, len(observations), before, len(registry),
        )

        # I3a: durable proven-content store (FR-9) — DEFAULT-OFF, additive, non-fatal.
        # Persists this run's generated content keyed by (term_id, source_checksum) so a
        # later run can serve it deterministically (the provider's content source). Gated
        # by its own flag so enabling corpus accumulation does NOT start writing content.
        if os.getenv("STARTD8_CORPUS_CONTENT_STORE", "0") in ("1", "true", "yes", "on"):
            try:
                from startd8.corpus.content_store import ContentStore, populate_from_run
                from startd8.corpus.extractor import seed_source_checksum
                from startd8.paths import corpus_content_dir
                checksum = seed_source_checksum(output_dir)
                if checksum:
                    store = ContentStore(
                        corpus_content_dir(Path(project_root)) if project_root
                        else corpus_content_dir()
                    )
                    n = populate_from_run(report, checksum, store)
                    logger.info(
                        "Controlled corpus content store: persisted %d file(s) (checksum=%s)",
                        n, str(checksum)[:12],
                    )
                else:
                    logger.debug("corpus content store: no source_checksum in seed — skipped")
            except Exception:
                logger.warning("Controlled corpus content store write failed", exc_info=True)

    def _scan_todos(
        self,
        report: PrimePostMortemReport,
        project_root: Optional[str],
        output_dir: str,
    ) -> None:
        """Scan generated files for TODO markers (REQ-TCW-100)."""
        from startd8.validators.todo_scanner import scan_file, TodoInventory

        if not project_root:
            return

        inventory = TodoInventory()
        for fpm in report.features:
            for gf in fpm.generated_files:
                gf_path = Path(project_root) / gf
                if not gf_path.is_file():
                    gf_path = Path(output_dir) / "generated" / gf
                entries = scan_file(gf_path)
                inventory.entries.extend(entries)

                # Update per-feature counts
                for e in entries:
                    if e.category == "A":
                        fpm.todo_count_a += 1
                    elif e.category == "B":
                        fpm.todo_count_b += 1
                    else:
                        fpm.todo_count_c += 1

        if inventory.entries:
            inventory.save(Path(output_dir) / "todo-inventory.json")

    def _render_observability_section(self, output_dir: str) -> Optional[str]:
        """Render observability artifacts markdown section (REQ-KZ-OBS-502).

        Reads ``observability_artifacts`` from ``kaizen-metrics.json`` in
        *output_dir*.  Falls back to sibling ``observability-quality.json``
        or ``../observability/observability-quality.json`` when the key is
        absent (pipeline timing: obs artifacts may be generated before
        kaizen-metrics.json exists).  Returns ``None`` when no data found.
        """
        obs = None
        out = Path(output_dir)

        # Primary: kaizen-metrics.json in output_dir
        metrics_path = out / "kaizen-metrics.json"
        if metrics_path.is_file():
            try:
                data = json.loads(metrics_path.read_text(encoding="utf-8"))
                obs = data.get("observability_artifacts")
            except (json.JSONDecodeError, OSError):
                pass

        # Fallback: observability-quality.json (written by artifact generator
        # when kaizen-metrics.json doesn't exist yet)
        if not obs:
            for candidate in [
                out / "observability-quality.json",
                out.parent / "observability" / "observability-quality.json",
            ]:
                if candidate.is_file():
                    try:
                        data = json.loads(candidate.read_text(encoding="utf-8"))
                        obs = data.get("observability_artifacts")
                        if obs:
                            # Merge into kaizen-metrics.json so downstream
                            # consumers (batch_postmortem, trends) see it.
                            if metrics_path.is_file():
                                try:
                                    existing = json.loads(
                                        metrics_path.read_text(encoding="utf-8")
                                    )
                                    existing["observability_artifacts"] = obs
                                    metrics_path.write_text(
                                        json.dumps(existing, indent=2, default=str)
                                        + "\n",
                                        encoding="utf-8",
                                    )
                                    logger.info(
                                        "Merged observability_artifacts into %s",
                                        metrics_path,
                                    )
                                except (json.JSONDecodeError, OSError):
                                    pass
                            break
                    except (json.JSONDecodeError, OSError):
                        continue

        if not obs:
            return None

        cross_issues = obs.get("cross_artifact_issues", {})
        cross_total = sum(
            int(v) for v in cross_issues.values() if isinstance(v, (int, float))
        )

        lines = [
            "",
            "## Observability Artifacts",
            "",
            f"- Services evaluated: {obs.get('services_evaluated', 0)}"
            f" ({obs.get('services_with_complete_triplet', 0)} complete triplets)",
            f"- Average dashboard score: {obs.get('avg_dashboard_spec_score', 0):.0%}",
            f"- Average alert score: {obs.get('avg_alert_rule_score', 0):.0%}",
            f"- Average SLO score: {obs.get('avg_slo_definition_score', 0):.0%}",
            f"- Composite score: {obs.get('avg_composite_score', 0):.0%}",
            f"- Cross-artifact issues: {cross_total}",
            f"- Repairs applied: {obs.get('total_repairs', 0)}",
            "",
        ]
        return "\n".join(lines)

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
            lines.extend(
                [
                    "## Pipeline Attribution",
                    "",
                    "| Stage | Failures | Root Causes |",
                    "|-------|----------|-------------|",
                ]
            )
            for attr in report.pipeline_attribution:
                causes_str = ", ".join(f"{k}({v})" for k, v in attr.root_causes.items())
                lines.append(
                    f"| {attr.stage.value} | {attr.failure_count} | {causes_str} |"
                )
            lines.append("")

        # Failed Features
        failed = [f for f in report.features if not f.success]
        if failed:
            lines.extend(["## Failed Features", ""])
            for fpm in failed:
                lines.extend(
                    [
                        f"### {fpm.name} (`{fpm.feature_id}`)",
                        "",
                        f"- **Root cause:** {fpm.root_cause.value}",
                        f"- **Pipeline stage:** {fpm.pipeline_stage.value}",
                        f"- **Error:** {fpm.error_message or '(none)'}",
                        f"- **Cost:** ${fpm.cost_usd:.4f}",
                        "",
                    ]
                )

        # Micro Prime Analysis
        if report.micro_prime_analysis:
            mpa = report.micro_prime_analysis
            lines.extend(
                [
                    "## Micro Prime Analysis",
                    "",
                    f"- Total elements: {mpa.total_elements}",
                    f"- Successful: {mpa.successful_elements}",
                    f"- Escalated: {mpa.escalated_elements}",
                    f"- Avg generation time: {mpa.avg_generation_time_ms:.1f}ms",
                    "",
                ]
            )
            if mpa.tier_distribution:
                lines.append("**Tier distribution:**")
                for tier, count in sorted(mpa.tier_distribution.items()):
                    lines.append(f"- {tier}: {count}")
                lines.append("")

        # Cross-Feature Patterns
        if report.cross_feature_patterns:
            lines.extend(["## Cross-Feature Patterns", ""])
            for pat in report.cross_feature_patterns:
                lines.extend(
                    [
                        f"- **{pat.pattern_type}** ({pat.severity}): {pat.description}",
                    ]
                )
            lines.append("")

        # Lessons
        if report.lessons:
            lines.extend(["## Lessons", ""])
            for lesson in report.lessons:
                lines.append(f"- [{lesson.severity.value}] {lesson.title}")
            lines.append("")

        # Query Security (REQ-KQP-502)
        # Render when any features have query_security semantic issues
        _qs_features = [
            f
            for f in report.features
            if f.disk_compliance
            and any(
                isinstance(si, dict)
                and si.get("category", "").startswith("query_security")
                for si in (getattr(f.disk_compliance, "semantic_issues", None) or [])
            )
        ]
        _qs_total_issues = sum(
            getattr(f, "semantic_error_count", 0) for f in _qs_features
        )
        if _qs_features or _qs_total_issues > 0:
            lines.extend(
                [
                    "## Query Security",
                    "",
                    f"- Features with query security findings: {len(_qs_features)}",
                    f"- Total security semantic errors: {_qs_total_issues}",
                    "",
                ]
            )
            # Per-database breakdown from semantic issues
            _qs_by_db: dict = {}
            for f in _qs_features:
                for si in getattr(f.disk_compliance, "semantic_issues", None) or []:
                    if isinstance(si, dict) and si.get("category", "").startswith(
                        "query_security"
                    ):
                        db = (
                            getattr(f.disk_compliance, "detected_database", "unknown")
                            or "unknown"
                        )
                        _qs_by_db.setdefault(db, {"findings": 0, "features": set()})
                        _qs_by_db[db]["findings"] += 1
                        _qs_by_db[db]["features"].add(f.name)
            if _qs_by_db:
                lines.extend(
                    [
                        "| Database | Findings | Features |",
                        "|----------|----------|----------|",
                    ]
                )
                for db, data in sorted(_qs_by_db.items()):
                    lines.append(
                        f"| {db} | {data['findings']} | {', '.join(sorted(data['features']))} |"
                    )
                lines.append("")

        # Cost Summary
        if report.cost_summary:
            cs = report.cost_summary
            lines.extend(
                [
                    "## Cost Summary",
                    "",
                    f"- Total: ${cs.total_usd:.4f}",
                    f"- Average per feature: ${cs.avg_per_feature:.4f}",
                    f"- Max: {cs.max_feature} (${cs.max_usd:.4f})",
                    "",
                ]
            )

        # Determinism (REQ-DET-METRIC) — the measured $0/no-LLM assembly fraction
        if report.determinism:
            dm = report.determinism
            by_path = ", ".join(f"{k}={v}" for k, v in sorted(dm.by_path.items())) or "—"
            lines.extend(
                [
                    "## Determinism (deterministic $0 vs LLM)",
                    "",
                    f"- Deterministic features: {dm.deterministic_features} / "
                    f"{dm.deterministic_features + dm.llm_features} "
                    f"({dm.feature_ratio:.0%})",
                    f"- Deterministic files: {dm.deterministic_files} / "
                    f"{dm.deterministic_files + dm.llm_files} ({dm.file_ratio:.0%})",
                    f"- By path: {by_path}",
                    "",
                ]
            )

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Post-mortem launchers (sync gate + async back-compat)
# ---------------------------------------------------------------------------


def _prepare_postmortem_inputs(
    result_dict: Dict[str, Any],
    queue: Any,  # FeatureQueue — Any to avoid circular import
    seed_path: Optional[str] = None,
) -> tuple[Dict[str, Any], Dict[str, Any], Optional[List[Dict]]]:
    """Snapshot the inputs the evaluator needs, decoupled from live state.

    Deep-copies ``result_dict`` and serializes queue state so the evaluation is
    insulated from concurrent mutation (the async path) and produces a
    deterministic snapshot (the sync gate, REQ-CKG-240 NFR-5).
    """
    result_copy = copy.deepcopy(result_dict)

    queue_state: Dict[str, Any] = {}
    if hasattr(queue, "features"):
        queue_state = {
            fid: f.to_dict() if hasattr(f, "to_dict") else {}
            for fid, f in queue.features.items()
        }

    seed_tasks = None
    if seed_path:
        try:
            seed_data = json.loads(Path(seed_path).read_text(encoding="utf-8"))
            seed_tasks = seed_data.get("tasks", [])
        except Exception:
            logger.warning("Failed to load seed for postmortem: %s", seed_path)

    return result_copy, queue_state, seed_tasks


def evaluate_prime_postmortem_sync(
    result_dict: Dict[str, Any],
    queue: Any,  # FeatureQueue — Any to avoid circular import
    seed_path: Optional[str] = None,
    output_dir: str = ".",
    project_root: Optional[str] = None,
) -> PrimePostMortemReport:
    """Run the post-mortem evaluation synchronously and return the report.

    REQ-CKG-240: the cross-file verifier verdict must gate the run, so the
    evaluation runs inline (no detached thread) before ``PrimeContractor.run()``
    returns. The caller folds the verdict into ``result_dict`` via
    :func:`apply_cross_file_gate`. Running inline also removes the race the
    detached ``daemon=False`` thread introduced, satisfying NFR-5 determinism.
    """
    result_copy, queue_state, seed_tasks = _prepare_postmortem_inputs(
        result_dict, queue, seed_path
    )
    evaluator = PrimePostMortemEvaluator()
    report = evaluator.evaluate(
        result_dict=result_copy,
        queue_state=queue_state,
        seed_tasks=seed_tasks,
        output_dir=output_dir,
        project_root=project_root,
    )
    logger.info(
        "Prime postmortem complete (sync): score=%.2f verdict=%s",
        report.aggregate_score,
        report.aggregate_verdict,
    )
    return report


def apply_cross_file_gate(
    result_dict: Dict[str, Any],
    report: PrimePostMortemReport,
) -> Dict[str, Any]:
    """Fold the post-mortem verdict into ``result_dict`` so it gates the run.

    REQ-CKG-240/245: an error-severity cross-file finding flips its owning
    feature to ``FAIL:cross_file`` and caps the batch verdict at FAIL. This
    surfaces that as a consumable gate on ``result_dict`` (and, downstream, the
    CLI exit code) instead of a log line in a thread nobody joins.

    Returns the gate dict (also stored at ``result_dict["cross_file_gate"]``).
    """
    cross_file_failures = [
        {
            "feature_id": getattr(f, "feature_id", "?"),
            "name": getattr(f, "name", ""),
            "error_message": getattr(f, "error_message", "") or "",
        }
        for f in report.features
        if getattr(f, "verdict", "") == "FAIL:cross_file"
    ]
    gate = {
        "passed": not cross_file_failures,
        "available": True,
        "verdict": report.aggregate_verdict,
        "score": report.aggregate_score,
        "cross_file_failures": cross_file_failures,
    }
    result_dict["cross_file_gate"] = gate
    result_dict["postmortem_verdict"] = report.aggregate_verdict
    result_dict["postmortem_score"] = report.aggregate_score
    return gate


def launch_prime_postmortem_async(
    result_dict: Dict[str, Any],
    queue: Any,  # FeatureQueue — Any to avoid circular import
    seed_path: Optional[str] = None,
    output_dir: str = ".",
    project_root: Optional[str] = None,
) -> threading.Thread:
    """Launch post-mortem evaluation in a background thread.

    Retained for backward compatibility (external callers / existing tests).
    The active gating path in ``PrimeContractor.run()`` uses
    :func:`evaluate_prime_postmortem_sync` instead, so the verdict can gate the
    run (REQ-CKG-240). This launcher does **not** gate — its verdict is logged.

    Thread-safe: deep-copies result_dict and snapshots queue state before
    spawning the thread so the caller can continue without contention.

    Returns:
        The started Thread object.
    """
    result_copy, queue_state, seed_tasks = _prepare_postmortem_inputs(
        result_dict, queue, seed_path
    )

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
