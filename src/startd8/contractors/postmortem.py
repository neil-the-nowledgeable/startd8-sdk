"""
Post-Mortem Evaluation Module for Artisan Contractor Workflow.

Evaluates how well generated artifacts satisfy the input seed task
requirements. Produces structured JSON and Markdown reports with
per-task scores, aggregate metrics, and extracted lessons learned.

Modes:
    - Rules-only (default): deterministic scoring, no LLM calls
    - Hybrid: rules + LLM-as-judge (requires judge_agent_spec)

Usage:
    # Programmatic
    evaluator = PostMortemEvaluator()
    report = evaluator.evaluate(seed_tasks, workflow_result, context, output_dir)

    # Async launcher (daemon thread)
    thread = launch_postmortem_async(
        seed_path="out/run-1/artisan-context-seed-enriched.json",
        workflow_result=result,
        context=initial_context,
        output_dir="out/run-1",
    )
"""

from __future__ import annotations

import copy
import dataclasses
import datetime
import json
import re
import threading
import uuid
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
_MAX_TASK_OUTPUT_BYTES = 50 * 1024  # 50 KB truncation ceiling for scoring
# See also: scripts/run_artisan_workflow.py for phase/test timeout constants
# (_MIN_PHASE_TIMEOUT_SECONDS, _MIN_IMPLEMENT_TIMEOUT_SECONDS, _DEFAULT_TEST_TIMEOUT_SECONDS)
_POSTMORTEM_THREAD_TIMEOUT = 300.0  # rules-only
_POSTMORTEM_LLM_THREAD_TIMEOUT = 600.0  # with LLM judge


class VerdictLevel(str, Enum):
    """Verdict classification for post-mortem evaluation results."""

    PASS = "PASS"
    PARTIAL = "PARTIAL"
    FAIL = "FAIL"


# Backward-compatible aliases for external consumers
_VERDICT_PASS = VerdictLevel.PASS
_VERDICT_PARTIAL = VerdictLevel.PARTIAL
_VERDICT_FAIL = VerdictLevel.FAIL
_CURRENCY_SYMBOL = "$"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class TaskPostMortem:
    """Per-task evaluation result."""

    task_id: str
    title: str
    requirement_score: float  # 0.0–1.0
    file_coverage_score: float  # 0.0–1.0
    quality_score: Optional[Dict[str, Any]] = None  # QualityScore.to_dict() or None
    requirements_met: List[str] = dataclasses.field(default_factory=list)
    requirements_missed: List[str] = dataclasses.field(default_factory=list)
    files_expected: List[str] = dataclasses.field(default_factory=list)
    files_produced: List[str] = dataclasses.field(default_factory=list)
    files_missing: List[str] = dataclasses.field(default_factory=list)
    anti_pattern_findings: List[Dict[str, Any]] = dataclasses.field(
        default_factory=list
    )
    verdict: str = VerdictLevel.FAIL

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class PostMortemReport:
    """Aggregate post-mortem report."""

    report_id: str
    workflow_id: str
    timestamp: str
    method: str  # "rules" or "hybrid"
    tasks: List[TaskPostMortem] = dataclasses.field(default_factory=list)
    aggregate_score: float = 0.0
    aggregate_verdict: str = VerdictLevel.FAIL
    total_tasks: int = 0
    tasks_evaluated: int = 0
    lessons: List[Dict[str, Any]] = dataclasses.field(default_factory=list)
    phase_summary: Dict[str, Any] = dataclasses.field(default_factory=dict)
    cost_summary: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "workflow_id": self.workflow_id,
            "timestamp": self.timestamp,
            "method": self.method,
            "aggregate_score": self.aggregate_score,
            "aggregate_verdict": self.aggregate_verdict,
            "total_tasks": self.total_tasks,
            "tasks_evaluated": self.tasks_evaluated,
            "tasks": [t.to_dict() for t in self.tasks],
            "lessons": self.lessons,
            "phase_summary": self.phase_summary,
            "cost_summary": self.cost_summary,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)


@dataclasses.dataclass
class WalkthroughTaskPostMortem:
    """Per-task walkthrough prompt quality result."""

    task_id: str
    title: str
    prompt_files: List[str] = dataclasses.field(default_factory=list)
    requirements_considered: List[str] = dataclasses.field(default_factory=list)
    requirements_matched: List[str] = dataclasses.field(default_factory=list)
    requirements_missed: List[str] = dataclasses.field(default_factory=list)
    constraints_considered: List[str] = dataclasses.field(default_factory=list)
    constraints_matched: List[str] = dataclasses.field(default_factory=list)
    constraints_missed: List[str] = dataclasses.field(default_factory=list)
    requirement_coverage_score: float = 0.0
    constraint_coverage_score: float = 0.0
    prompt_quality_score: float = 0.0
    verdict: str = VerdictLevel.FAIL

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class WalkthroughPostMortemReport:
    """Aggregate walkthrough prompt-quality report."""

    report_id: str
    workflow_id: str
    timestamp: str
    walkthrough_root: str
    total_tasks: int = 0
    tasks_evaluated: int = 0
    aggregate_score: float = 0.0
    aggregate_verdict: str = VerdictLevel.FAIL
    tasks: List[WalkthroughTaskPostMortem] = dataclasses.field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "workflow_id": self.workflow_id,
            "timestamp": self.timestamp,
            "walkthrough_root": self.walkthrough_root,
            "total_tasks": self.total_tasks,
            "tasks_evaluated": self.tasks_evaluated,
            "aggregate_score": self.aggregate_score,
            "aggregate_verdict": self.aggregate_verdict,
            "tasks": [t.to_dict() for t in self.tasks],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_verdict(score: float) -> str:
    if score >= _PASS_THRESHOLD:
        return VerdictLevel.PASS
    if score >= _PARTIAL_THRESHOLD:
        return VerdictLevel.PARTIAL
    return VerdictLevel.FAIL


def _truncate_for_scoring(text: str) -> str:
    """Truncate text to _MAX_TASK_OUTPUT_BYTES for scoring."""
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= _MAX_TASK_OUTPUT_BYTES:
        return text
    return encoded[:_MAX_TASK_OUTPUT_BYTES].decode("utf-8", errors="replace")


def _extract_requirement_keywords(task_dict: Dict[str, Any]) -> List[str]:
    """Extract requirement keywords from a seed task dict.

    Pulls text from ``requirements_text``, ``prompt_constraints``,
    ``config.task_description``, ``config.context.design_doc_sections``,
    and ``_enrichment.prompt_constraints``.  Splits on newlines and
    bullet characters, returns deduplicated non-empty phrases (lowercased).
    """
    sources: List[str] = []

    req_text = task_dict.get("requirements_text", "") or ""
    if req_text:
        sources.append(req_text)

    # Top-level prompt_constraints
    constraints = task_dict.get("prompt_constraints", []) or []
    if isinstance(constraints, list):
        sources.extend(str(c) for c in constraints)
    elif isinstance(constraints, str):
        sources.append(constraints)

    # Enrichment-level prompt_constraints (plan-ingestion enriched seeds)
    enrichment = task_dict.get("_enrichment", {}) or {}
    enr_constraints = enrichment.get("prompt_constraints", []) or []
    if isinstance(enr_constraints, list):
        sources.extend(str(c) for c in enr_constraints)

    # config.task_description
    config = task_dict.get("config", {}) or {}
    task_desc = config.get("task_description", "") or ""
    if task_desc:
        sources.append(task_desc)

    # config.context.design_doc_sections
    ctx = config.get("context", {}) or {}
    doc_sections = ctx.get("design_doc_sections", []) or []
    if isinstance(doc_sections, list):
        sources.extend(str(s) for s in doc_sections)

    keywords: List[str] = []
    for source in sources:
        # Split on newlines, bullet markers, and numbered lists.
        # Hyphens are NOT used as split chars to preserve compound words
        # like "error-handling" and "rate-limiting" (M-19).
        lines = re.split(r"\n|•|\d+\.\s", source)
        for line in lines:
            # Strip leading bullet markers ("- ", "* ") without splitting on
            # mid-word hyphens.
            cleaned = re.sub(r"^\s*[-*]\s+", "", line).strip().lower()
            # Skip very short fragments (< 3 words) — likely not a requirement
            if cleaned and len(cleaned.split()) >= 3:
                keywords.append(cleaned)

    # Deduplicate preserving order
    seen: set[str] = set()
    result: List[str] = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            result.append(kw)
    return result


def _extract_prompt_constraints(task_dict: Dict[str, Any]) -> List[str]:
    """Extract normalized prompt constraints from seed task dict."""
    constraints: List[str] = []

    top_level = task_dict.get("prompt_constraints", []) or []
    if isinstance(top_level, list):
        constraints.extend(str(c).strip().lower() for c in top_level if str(c).strip())
    elif isinstance(top_level, str) and top_level.strip():
        constraints.append(top_level.strip().lower())

    enrichment = task_dict.get("_enrichment", {}) or {}
    enr = enrichment.get("prompt_constraints", []) or []
    if isinstance(enr, list):
        constraints.extend(str(c).strip().lower() for c in enr if str(c).strip())

    # Deduplicate preserving order.
    seen: set[str] = set()
    deduped: List[str] = []
    for item in constraints:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def extract_prompt_characteristics(prompt_dir: Path) -> Dict[str, Any]:
    """Extract measurable characteristics from a kaizen-prompts feature directory (REQ-KZ-600).

    Reads the spec/draft/review user prompt files and metadata.json from a
    kaizen-prompts/{run_id}/{feature_id}/ directory (the same format as walkthrough).

    Args:
        prompt_dir: Path to the feature-level prompt directory containing
                    {phase}_user_prompt.md files and metadata.json.

    Returns:
        dict with scalar metrics:
            {phase}_word_count, {phase}_char_count (for spec, draft, review),
            context_key_count, has_existing_files, target_file_count,
            total_prompt_words (composite across all phases).
        Missing files result in None for their metrics.
    """
    chars: Dict[str, Any] = {}

    for phase in ("spec", "draft", "review"):
        up = prompt_dir / f"{phase}_user_prompt.md"
        if up.exists():
            text = up.read_text(encoding="utf-8", errors="replace")
            chars[f"{phase}_word_count"] = len(text.split())
            chars[f"{phase}_char_count"] = len(text)
        else:
            chars[f"{phase}_word_count"] = None
            chars[f"{phase}_char_count"] = None

    meta_path = prompt_dir / "metadata.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            chars["context_key_count"] = len(meta.get("context_keys") or [])
            chars["has_existing_files"] = bool(meta.get("has_existing_files"))
            chars["target_file_count"] = int(meta.get("target_file_count") or 0)
            chars["feature_id"] = meta.get("feature_id", prompt_dir.name)
        except (json.JSONDecodeError, OSError):
            chars["context_key_count"] = None
            chars["has_existing_files"] = None
            chars["target_file_count"] = None
            chars["feature_id"] = prompt_dir.name
    else:
        chars["context_key_count"] = None
        chars["has_existing_files"] = None
        chars["target_file_count"] = None
        chars["feature_id"] = prompt_dir.name

    words = [chars[f"{p}_word_count"] for p in ("spec", "draft", "review") if chars.get(f"{p}_word_count") is not None]
    chars["total_prompt_words"] = sum(words) if words else None

    return chars


# ---------------------------------------------------------------------------
# PostMortemEvaluator
# ---------------------------------------------------------------------------


class PostMortemEvaluator:
    """Evaluates workflow output against seed task requirements.

    Args:
        use_llm_judge: Enable LLM-as-judge for hybrid scoring.
        judge_agent_spec: Agent spec string (e.g. ``anthropic:claude-haiku-4-5-20251001``).
    """

    def __init__(
        self,
        use_llm_judge: bool = False,
        judge_agent_spec: Optional[str] = None,
    ) -> None:
        self._use_llm_judge = use_llm_judge
        self._judge_agent_spec = judge_agent_spec
        self._sanitizer = Sanitizer()
        self._anti_pattern_detector = AntiPatternDetector()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        seed_tasks: List[Dict[str, Any]],
        workflow_result: Dict[str, Any],
        context: Dict[str, Any],
        output_dir: str,
        filter_slug: Optional[str] = None,
    ) -> PostMortemReport:
        """Run post-mortem evaluation.

        Args:
            seed_tasks: List of seed task dicts from the enriched seed JSON.
            workflow_result: Serialized WorkflowResult dict.
            context: The initial_context dict (contains generation_results,
                     test_results, review_results).
            output_dir: Directory to write report files.
            filter_slug: Optional slug for filtered runs (appended to filenames).

        Returns:
            PostMortemReport with per-task and aggregate results.
        """
        gen_results = context.get("generation_results", {})
        test_results = context.get("test_results", {})
        review_results = context.get("review_results", {})

        # Handle cached state format: { "_cache_meta": ..., "tasks": { "PI-012": ... } }
        if "tasks" in gen_results and "_cache_meta" in gen_results:
            gen_results = gen_results["tasks"]
        if "tasks" in review_results and "_cache_meta" in review_results:
            review_results = review_results["tasks"]
        if "tasks" in test_results and "_cache_meta" in test_results:
            test_results = test_results["tasks"]

        task_postmortems: List[TaskPostMortem] = []

        for task_dict in seed_tasks:
            try:
                tpm = self._evaluate_task(
                    task_dict, gen_results, test_results, review_results
                )
                task_postmortems.append(tpm)
            except Exception:
                task_id = task_dict.get("task_id", "unknown")
                logger.exception(
                    "Post-mortem evaluation failed for task %s — scoring as FAIL",
                    task_id,
                )
                task_postmortems.append(
                    TaskPostMortem(
                        task_id=task_id,
                        title=task_dict.get("title", ""),
                        requirement_score=0.0,
                        file_coverage_score=0.0,
                        verdict=VerdictLevel.FAIL,
                    )
                )

        # Aggregate
        evaluated = [t for t in task_postmortems if t.verdict != VerdictLevel.FAIL or
                     t.requirement_score > 0.0 or t.file_coverage_score > 0.0]
        if task_postmortems:
            avg_req = sum(t.requirement_score for t in task_postmortems) / len(
                task_postmortems
            )
            avg_file = sum(t.file_coverage_score for t in task_postmortems) / len(
                task_postmortems
            )
            aggregate_score = (avg_req + avg_file) / 2.0
        else:
            aggregate_score = 0.0

        # Phase summary from workflow result
        phase_summary = self._build_phase_summary(workflow_result)
        cost_summary = {
            "total_cost": workflow_result.get("total_cost", 0.0),
            "total_duration_seconds": workflow_result.get(
                "total_duration_seconds", 0.0
            ),
        }

        # Extract lessons
        lessons_objs = self._extract_lessons(task_postmortems)

        report = PostMortemReport(
            report_id=str(uuid.uuid4()),
            workflow_id=workflow_result.get("workflow_id", "unknown"),
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            method="hybrid" if self._use_llm_judge else "rules",
            tasks=task_postmortems,
            aggregate_score=round(aggregate_score, 4),
            aggregate_verdict=_compute_verdict(aggregate_score),
            total_tasks=len(seed_tasks),
            tasks_evaluated=len(evaluated),
            lessons=[dataclasses.asdict(les) for les in lessons_objs],
            phase_summary=phase_summary,
            cost_summary=cost_summary,
        )

        self._write_outputs(report, output_dir, filter_slug)
        return report

    # ------------------------------------------------------------------
    # Per-task evaluation
    # ------------------------------------------------------------------

    def _evaluate_task(
        self,
        task_dict: Dict[str, Any],
        gen_results: Dict[str, Any],
        test_results: Dict[str, Any],
        review_results: Dict[str, Any],
    ) -> TaskPostMortem:
        task_id = task_dict.get("task_id", "unknown")
        title = task_dict.get("title", "")

        # 1. Requirement checking
        generated_code = self._collect_generated_code(task_id, gen_results)
        req_met, req_missed = self._check_requirements(task_dict, generated_code)
        total_reqs = len(req_met) + len(req_missed)
        req_score = len(req_met) / total_reqs if total_reqs > 0 else 0.0

        # 2. File coverage
        expected, produced, missing = self._check_file_coverage(
            task_dict, gen_results
        )
        file_score = (
            len(produced) / len(expected) if expected else 1.0 if not expected else 0.0
        )

        # 3. Quality scoring (rules-based)
        quality_dict = self._score_quality(generated_code, task_dict)

        # 4. Anti-pattern detection
        ap_findings = self._detect_anti_patterns(task_id, generated_code)

        # 5. Incorporate test and review results when available
        task_test = test_results.get(task_id, {}) if isinstance(test_results, dict) else {}
        task_review = review_results.get(task_id, {}) if isinstance(review_results, dict) else {}
        test_passed = bool(task_test.get("passed")) if task_test else None
        review_score_raw = task_review.get("score")
        review_norm = (
            float(review_score_raw) / 100.0
            if review_score_raw is not None
            else None
        )
        quality_overall = (
            float(quality_dict["overall"])
            if quality_dict and "overall" in quality_dict
            else None
        )

        # Composite score: weighted average of available signals.
        # Weights: requirements 30%, file coverage 30%, quality 20%,
        # review 20%.  Absent signals are excluded and weights re-normalised.
        _components: list[tuple[float, float]] = [
            (req_score, 0.3),
            (file_score, 0.3),
        ]
        if quality_overall is not None:
            _components.append((quality_overall, 0.2))
        if review_norm is not None:
            _components.append((max(0.0, min(1.0, review_norm)), 0.2))
        _total_weight = sum(w for _, w in _components)
        composite = (
            sum(s * w for s, w in _components) / _total_weight
            if _total_weight > 0
            else 0.0
        )
        # Apply a penalty when tests explicitly failed
        if test_passed is False:
            composite *= 0.7

        return TaskPostMortem(
            task_id=task_id,
            title=title,
            requirement_score=round(req_score, 4),
            file_coverage_score=round(file_score, 4),
            quality_score=quality_dict,
            requirements_met=req_met,
            requirements_missed=req_missed,
            files_expected=expected,
            files_produced=produced,
            files_missing=missing,
            anti_pattern_findings=[
                dataclasses.asdict(f) for f in ap_findings
            ],
            verdict=_compute_verdict(composite),
        )

    # ------------------------------------------------------------------
    # Requirement checking
    # ------------------------------------------------------------------

    def _check_requirements(
        self, task_dict: Dict[str, Any], generated_code: str
    ) -> Tuple[List[str], List[str]]:
        """Check which requirement keywords appear in generated code."""
        keywords = _extract_requirement_keywords(task_dict)
        if not keywords:
            return [], []

        # Normalize underscores to spaces so snake_case identifiers
        # (e.g. implement_authentication_middleware) match requirement
        # keywords (e.g. "implement authentication middleware"), while
        # using word-boundary matching to avoid substring false positives
        # (e.g. "set" matching inside "result", "run" inside "runtime").
        code_lower = generated_code.lower().replace("_", " ")
        met: List[str] = []
        missed: List[str] = []

        for kw in keywords:
            words = kw.split()
            if not words:
                continue
            present = sum(
                1 for w in words
                if re.search(rf'\b{re.escape(w)}\b', code_lower)
            )
            if present / len(words) >= 0.5:
                met.append(kw)
            else:
                missed.append(kw)

        return met, missed

    # ------------------------------------------------------------------
    # File coverage
    # ------------------------------------------------------------------

    def _check_file_coverage(
        self,
        task_dict: Dict[str, Any],
        gen_results: Dict[str, Any],
    ) -> Tuple[List[str], List[str], List[str]]:
        """Compare target_files against generated_files."""
        # target_files may be top-level or nested under config.context
        target_files = task_dict.get("target_files", []) or []
        if not target_files:
            config = task_dict.get("config", {}) or {}
            ctx = config.get("context", {}) or {}
            target_files = ctx.get("target_files", []) or []
        if not target_files:
            return [], [], []

        task_id = task_dict.get("task_id", "unknown")
        task_gen = gen_results.get(task_id, {})

        # generated_files may be:
        #   - dict (filepath → content) — in-memory format
        #   - list of absolute paths — cached state format
        if hasattr(task_gen, "generated_files"):
            generated_files = getattr(task_gen, "generated_files")
        else:
            generated_files = task_gen.get("generated_files", {})

        if isinstance(generated_files, dict):
            produced_set = set(generated_files.keys())
        elif isinstance(generated_files, list):
            # Normalize to basenames for comparison
            produced_set = set(generated_files)
            # Also add just the relative suffixes for matching
            for fp in generated_files:
                produced_set.add(Path(fp).name)
                # Try to extract relative path from common prefixes
                parts = Path(fp).parts
                for idx in range(len(parts)):
                    produced_set.add(str(Path(*parts[idx:])))
        else:
            produced_set = set()

        expected = list(target_files)
        produced = [f for f in expected if f in produced_set]
        missing = [f for f in expected if f not in produced_set]

        return expected, produced, missing

    # ------------------------------------------------------------------
    # Quality scoring
    # ------------------------------------------------------------------

    def _score_quality(
        self, generated_code: str, task_dict: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Score generated code quality using RuleBasedScorer."""
        if not generated_code.strip():
            return None

        truncated = _truncate_for_scoring(generated_code)

        try:
            from startd8.evaluation.rules import RuleBasedScorer
            from startd8.evaluation.tasks import Task, TaskCategory, TaskDifficulty

            scorer = RuleBasedScorer()
            eval_task = Task(
                id=task_dict.get("task_id", "pm-task").lower().replace(" ", "-"),
                name=task_dict.get("title", "Post-mortem task"),
                category=TaskCategory.CODING,
                difficulty=TaskDifficulty.MEDIUM,
                prompt_template=task_dict.get("requirements_text", "evaluate"),
            )
            dim_scores = scorer.score_response(truncated, eval_task)

            # Aggregate
            if dim_scores:
                avg = sum(ds.score for ds in dim_scores.values()) / len(dim_scores)
            else:
                avg = 0.0

            return {
                "overall": round(avg, 4),
                "method": "rules",
                "dimensions": {
                    dim.value: {
                        "score": ds.score,
                        "confidence": ds.confidence,
                        "explanation": ds.explanation,
                    }
                    for dim, ds in dim_scores.items()
                },
            }
        except Exception:
            logger.debug("Quality scoring failed for task %s",
                         task_dict.get("task_id", "unknown"), exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Anti-pattern detection
    # ------------------------------------------------------------------

    def _detect_anti_patterns(
        self, task_id: str, generated_code: str
    ) -> List[AntiPatternFinding]:
        """Run anti-pattern detection on generated code."""
        if not generated_code.strip():
            return []

        ctx = RetrospectiveContext(
            phase_name="postmortem",
            task_description=f"Post-mortem analysis for {task_id}",
            artifacts={f"{task_id}_generated": generated_code},
            process_log=[],
            metadata={"task_id": task_id},
        )
        return self._anti_pattern_detector.detect(ctx)

    # ------------------------------------------------------------------
    # Lessons extraction
    # ------------------------------------------------------------------

    def _extract_lessons(
        self, task_postmortems: List[TaskPostMortem]
    ) -> List[Lesson]:
        """Convert failed requirements and anti-patterns into Lesson objects."""
        lessons: List[Lesson] = []
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        for tpm in task_postmortems:
            # Lessons from missed requirements
            if tpm.requirements_missed:
                lessons.append(
                    Lesson(
                        lesson_id=str(uuid.uuid4()),
                        title=f"Requirements gap in {tpm.task_id}",
                        description=(
                            f"Task '{tpm.title}' missed {len(tpm.requirements_missed)} "
                            f"requirement(s): {'; '.join(tpm.requirements_missed[:5])}"
                        ),
                        category=LessonCategory.IMPLEMENTATION,
                        severity=(
                            Severity.HIGH
                            if tpm.requirement_score < _PARTIAL_THRESHOLD
                            else Severity.MEDIUM
                        ),
                        tags=["postmortem", "requirements-gap", tpm.task_id],
                        source_phase="postmortem",
                        source_context={
                            "task_id": tpm.task_id,
                            "requirement_score": tpm.requirement_score,
                            "missed": tpm.requirements_missed[:5],
                        },
                        created_at=now,
                    )
                )

            # Lessons from anti-pattern findings
            for finding in tpm.anti_pattern_findings:
                lessons.append(
                    Lesson(
                        lesson_id=str(uuid.uuid4()),
                        title=(
                            f"Anti-pattern in {tpm.task_id}: "
                            f"{finding.get('pattern_type', 'unknown')}"
                        ),
                        description=finding.get("description", ""),
                        category=LessonCategory.IMPLEMENTATION,
                        severity=Severity.MEDIUM,
                        tags=[
                            "postmortem",
                            "anti-pattern",
                            tpm.task_id,
                            finding.get("pattern_type", "unknown"),
                        ],
                        source_phase="postmortem",
                        source_context={
                            "task_id": tpm.task_id,
                            "evidence": finding.get("evidence", ""),
                            "location": finding.get("location", ""),
                        },
                        created_at=now,
                        anti_pattern=finding.get("pattern_type"),
                    )
                )

            # Lessons from missing files
            if tpm.files_missing:
                lessons.append(
                    Lesson(
                        lesson_id=str(uuid.uuid4()),
                        title=f"Missing files in {tpm.task_id}",
                        description=(
                            f"Task '{tpm.title}' is missing "
                            f"{len(tpm.files_missing)} expected file(s): "
                            f"{', '.join(tpm.files_missing[:5])}"
                        ),
                        category=LessonCategory.PROCESS,
                        severity=Severity.HIGH,
                        tags=["postmortem", "missing-files", tpm.task_id],
                        source_phase="postmortem",
                        source_context={
                            "task_id": tpm.task_id,
                            "files_missing": tpm.files_missing[:5],
                            "file_coverage_score": tpm.file_coverage_score,
                        },
                        created_at=now,
                    )
                )

        return lessons

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _collect_generated_code(
        self, task_id: str, gen_results: Dict[str, Any]
    ) -> str:
        """Collect all generated code for a task into a single string."""
        task_gen = gen_results.get(task_id, {})
        if hasattr(task_gen, "generated_files"):
            generated_files = getattr(task_gen, "generated_files")
        else:
            generated_files = task_gen.get("generated_files", {})

        parts: List[str] = []

        if isinstance(generated_files, dict):
            for filepath, content in generated_files.items():
                if isinstance(content, str):
                    parts.append(f"# --- {filepath} ---\n{content}")
        elif isinstance(generated_files, list):
            # List of file paths — read from disk
            for filepath in generated_files:
                fp = Path(filepath)
                if fp.is_file():
                    try:
                        content = fp.read_text(encoding="utf-8", errors="replace")
                        parts.append(f"# --- {filepath} ---\n{content}")
                    except OSError:
                        logger.debug("Could not read generated file: %s", filepath)

        return "\n\n".join(parts)

    def _build_phase_summary(
        self, workflow_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract phase-level summary from workflow result."""
        summary: Dict[str, Any] = {}
        for pr in workflow_result.get("phase_results", []):
            phase = pr.get("phase", "unknown")
            summary[phase] = {
                "status": pr.get("status", "unknown"),
                "cost": pr.get("cost", 0.0),
                "duration_seconds": pr.get("duration_seconds", 0.0),
                "error_message": pr.get("error_message"),
            }
        return summary

    # ------------------------------------------------------------------
    # Output writing
    # ------------------------------------------------------------------

    def _write_outputs(
        self,
        report: PostMortemReport,
        output_dir: str,
        filter_slug: Optional[str] = None,
    ) -> None:
        """Write JSON report, Markdown summary, and lessons JSON."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        suffix = f"-{filter_slug}" if filter_slug else ""

        # Sanitize before writing
        sanitized_json = self._sanitizer.sanitize_text(report.to_json())

        # 1. JSON report
        json_path = out / f"postmortem-report{suffix}.json"
        json_path.write_text(sanitized_json, encoding="utf-8")
        logger.info("Wrote postmortem report: %s", json_path)

        # 2. Markdown summary
        md_path = out / f"postmortem-summary{suffix}.md"
        md_content = self._render_markdown(report)
        sanitized_md = self._sanitizer.sanitize_text(md_content)
        md_path.write_text(sanitized_md, encoding="utf-8")
        logger.info("Wrote postmortem summary: %s", md_path)
        print(f"\n{sanitized_md}\n", flush=True)

        # 3. Lessons JSON
        if report.lessons:
            lessons_path = out / f"postmortem-lessons{suffix}.json"
            sanitized_lessons = self._sanitizer.sanitize_text(
                json.dumps(report.lessons, indent=2, default=str)
            )
            lessons_path.write_text(sanitized_lessons, encoding="utf-8")
            logger.info("Wrote postmortem lessons: %s", lessons_path)

    def _render_markdown(self, report: PostMortemReport) -> str:
        """Render a human-readable Markdown summary."""
        lines: List[str] = []
        lines.append("# Post-Mortem Evaluation Report")
        lines.append("")
        lines.append(f"- **Report ID:** {report.report_id}")
        lines.append(f"- **Workflow ID:** {report.workflow_id}")
        lines.append(f"- **Timestamp:** {report.timestamp}")
        lines.append(f"- **Method:** {report.method}")
        lines.append(
            f"- **Aggregate Score:** {report.aggregate_score:.2f} "
            f"({report.aggregate_verdict})"
        )
        lines.append(
            f"- **Tasks Evaluated:** {report.tasks_evaluated}/{report.total_tasks}"
        )
        lines.append("")

        # Phase summary
        if report.phase_summary:
            lines.append("## Phase Summary")
            lines.append("")
            lines.append("| Phase | Status | Cost | Duration (s) |")
            lines.append("|-------|--------|------|-------------|")
            for phase, info in report.phase_summary.items():
                lines.append(
                    f"| {phase} | {info.get('status', '-')} | "
                    f"{_CURRENCY_SYMBOL}{info.get('cost', 0):.4f} | "
                    f"{info.get('duration_seconds', 0):.1f} |"
                )
            lines.append("")

        # Per-task results
        lines.append("## Per-Task Results")
        lines.append("")
        lines.append(
            "| Task | Verdict | Req Score | File Score | Reqs Met | Files Missing |"
        )
        lines.append(
            "|------|---------|-----------|------------|----------|--------------|"
        )
        for t in report.tasks:
            total_reqs = len(t.requirements_met) + len(t.requirements_missed)
            lines.append(
                f"| {t.task_id} | {t.verdict} | "
                f"{t.requirement_score:.2f} | {t.file_coverage_score:.2f} | "
                f"{len(t.requirements_met)}/{total_reqs} | "
                f"{len(t.files_missing)} |"
            )
        lines.append("")

        # Task details
        for t in report.tasks:
            if t.requirements_missed or t.files_missing or t.anti_pattern_findings:
                lines.append(f"### {t.task_id}: {t.title}")
                lines.append("")
                if t.requirements_missed:
                    lines.append("**Missed Requirements:**")
                    for r in t.requirements_missed:
                        lines.append(f"- [ ] {r}")
                    lines.append("")
                if t.files_missing:
                    lines.append("**Missing Files:**")
                    for f in t.files_missing:
                        lines.append(f"- {f}")
                    lines.append("")
                if t.anti_pattern_findings:
                    lines.append(
                        f"**Anti-Patterns:** {len(t.anti_pattern_findings)} finding(s)"
                    )
                    lines.append("")

        # Lessons
        if report.lessons:
            lines.append("## Lessons Extracted")
            lines.append("")
            for les in report.lessons:
                lines.append(f"- **{les.get('title', '')}**: {les.get('description', '')}")
            lines.append("")

        # Cost summary
        lines.append("## Cost Summary")
        lines.append("")
        lines.append(
            f"- **Total Cost:** {_CURRENCY_SYMBOL}{report.cost_summary.get('total_cost', 0):.4f}"
        )
        lines.append(
            f"- **Total Duration:** "
            f"{report.cost_summary.get('total_duration_seconds', 0):.1f}s"
        )
        lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Walkthrough Prompt Evaluator
# ---------------------------------------------------------------------------


class WalkthroughPromptEvaluator:
    """Evaluate saved walkthrough prompts against task requirements."""

    def evaluate(
        self,
        seed_tasks: List[Dict[str, Any]],
        walkthrough_root: str,
        workflow_result: Dict[str, Any],
        output_dir: str,
        filter_slug: Optional[str] = None,
    ) -> WalkthroughPostMortemReport:
        wt_root = Path(walkthrough_root)
        task_results: List[WalkthroughTaskPostMortem] = []

        for task_dict in seed_tasks:
            task_results.append(self._evaluate_task(task_dict, wt_root))

        scored = [t for t in task_results if t.prompt_files]
        if task_results:
            agg_score = sum(t.prompt_quality_score for t in task_results) / len(task_results)
        else:
            agg_score = 0.0

        report = WalkthroughPostMortemReport(
            report_id=str(uuid.uuid4()),
            workflow_id=workflow_result.get("workflow_id", "unknown"),
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            walkthrough_root=str(wt_root),
            total_tasks=len(seed_tasks),
            tasks_evaluated=len(scored),
            aggregate_score=round(agg_score, 4),
            aggregate_verdict=_compute_verdict(agg_score),
            tasks=task_results,
        )
        self._write_outputs(report, output_dir, filter_slug)
        return report

    def _evaluate_task(
        self,
        task_dict: Dict[str, Any],
        walkthrough_root: Path,
    ) -> WalkthroughTaskPostMortem:
        task_id = task_dict.get("task_id", "unknown")
        title = task_dict.get("title", "")

        prompt_texts: List[Tuple[str, str]] = []
        implement_dir = walkthrough_root / "implement" / task_id
        design_dir = walkthrough_root / "design" / task_id
        prime_dir = walkthrough_root / "prime" / task_id

        prompt_texts.extend(self._read_prompt_files(implement_dir))
        prompt_texts.extend(self._read_prompt_files(design_dir))
        prompt_texts.extend(self._read_prompt_files(prime_dir))

        combined = "\n\n".join(content for _, content in prompt_texts).lower()
        prompt_files = [rel for rel, _ in prompt_texts]

        reqs = _extract_requirement_keywords(task_dict)
        req_matched, req_missed = self._match_phrases(reqs, combined)

        constraints = _extract_prompt_constraints(task_dict)
        c_matched, c_missed = self._match_phrases(constraints, combined)

        req_score = len(req_matched) / len(reqs) if reqs else (1.0 if prompt_files else 0.0)
        c_score = len(c_matched) / len(constraints) if constraints else (1.0 if prompt_files else 0.0)
        quality = (req_score + c_score) / 2.0 if prompt_files else 0.0

        return WalkthroughTaskPostMortem(
            task_id=task_id,
            title=title,
            prompt_files=prompt_files,
            requirements_considered=reqs,
            requirements_matched=req_matched,
            requirements_missed=req_missed,
            constraints_considered=constraints,
            constraints_matched=c_matched,
            constraints_missed=c_missed,
            requirement_coverage_score=round(req_score, 4),
            constraint_coverage_score=round(c_score, 4),
            prompt_quality_score=round(quality, 4),
            verdict=_compute_verdict(quality),
        )

    def _read_prompt_files(self, directory: Path) -> List[Tuple[str, str]]:
        if not directory.is_dir():
            return []
        result: List[Tuple[str, str]] = []
        for fp in sorted(directory.glob("*.md")):
            try:
                result.append((str(fp), fp.read_text(encoding="utf-8", errors="replace")))
            except OSError:
                logger.debug("Walkthrough postmortem: failed reading prompt file %s", fp)
        return result

    def _match_phrases(
        self,
        phrases: List[str],
        haystack: str,
    ) -> Tuple[List[str], List[str]]:
        matched: List[str] = []
        missed: List[str] = []

        for phrase in phrases:
            words = [w for w in re.findall(r"[a-z0-9_]+", phrase.lower()) if len(w) > 2]
            if not words:
                continue
            present = sum(1 for w in words if w in haystack)
            if present / len(words) >= 0.5:
                matched.append(phrase)
            else:
                missed.append(phrase)
        return matched, missed

    def _write_outputs(
        self,
        report: WalkthroughPostMortemReport,
        output_dir: str,
        filter_slug: Optional[str] = None,
    ) -> None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        suffix = f"-{filter_slug}" if filter_slug else ""

        json_path = out / f"walkthrough-postmortem-report{suffix}.json"
        json_path.write_text(report.to_json(), encoding="utf-8")
        logger.info("Wrote walkthrough postmortem report: %s", json_path)

        md_path = out / f"walkthrough-postmortem-summary{suffix}.md"
        md_content = self._render_markdown(report)
        md_path.write_text(md_content, encoding="utf-8")
        logger.info("Wrote walkthrough postmortem summary: %s", md_path)
        print(f"\n{md_content}\n", flush=True)

    def _render_markdown(self, report: WalkthroughPostMortemReport) -> str:
        lines: List[str] = []
        lines.append("# Walkthrough Prompt Post-Mortem Report")
        lines.append("")
        lines.append(f"- **Report ID:** {report.report_id}")
        lines.append(f"- **Workflow ID:** {report.workflow_id}")
        lines.append(f"- **Walkthrough Root:** `{report.walkthrough_root}`")
        lines.append(f"- **Aggregate Score:** {report.aggregate_score:.2f} ({report.aggregate_verdict})")
        lines.append(f"- **Tasks Evaluated:** {report.tasks_evaluated}/{report.total_tasks}")
        lines.append("")
        lines.append(
            "| Task | Verdict | Prompt Score | Req Coverage | Constraint Coverage | Prompt Files |"
        )
        lines.append(
            "|------|---------|--------------|--------------|---------------------|--------------|"
        )
        for t in report.tasks:
            lines.append(
                f"| {t.task_id} | {t.verdict} | {t.prompt_quality_score:.2f} | "
                f"{t.requirement_coverage_score:.2f} | {t.constraint_coverage_score:.2f} | "
                f"{len(t.prompt_files)} |"
            )
        lines.append("")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Async Launcher
# ---------------------------------------------------------------------------


def launch_postmortem_async(
    seed_path: str,
    workflow_result: Dict[str, Any],
    context: Dict[str, Any],
    output_dir: str,
    use_llm_judge: bool = False,
    judge_agent_spec: Optional[str] = None,
    filter_slug: Optional[str] = None,
) -> threading.Thread:
    """Launch post-mortem evaluation in a daemon thread.

    Args:
        seed_path: Path to the enriched context seed JSON.
        workflow_result: Serialized WorkflowResult dict.
        context: Deep-copied initial_context dict.
        output_dir: Directory for output files.
        use_llm_judge: Enable LLM-as-judge.
        judge_agent_spec: Agent spec for the judge.
        filter_slug: Optional filter slug for filenames.

    Returns:
        The started daemon thread (join with timeout to wait).
    """
    # Deep-copy context to avoid race conditions with the main thread
    ctx_copy = copy.deepcopy(context)

    def _run() -> None:
        try:
            # Load seed tasks
            seed = Path(seed_path)
            if not seed.exists():
                logger.error("Postmortem: seed file not found: %s", seed_path)
                return

            with open(seed, "r", encoding="utf-8") as fh:
                seed_data = json.load(fh)

            seed_tasks = seed_data.get("tasks", [])
            if not seed_tasks:
                logger.warning("Postmortem: no tasks in seed file")
                return

            evaluator = PostMortemEvaluator(
                use_llm_judge=use_llm_judge,
                judge_agent_spec=judge_agent_spec,
            )
            report = evaluator.evaluate(
                seed_tasks=seed_tasks,
                workflow_result=workflow_result,
                context=ctx_copy,
                output_dir=output_dir,
                filter_slug=filter_slug,
            )
            logger.info(
                "Postmortem complete: %s (score=%.2f, verdict=%s)",
                report.report_id,
                report.aggregate_score,
                report.aggregate_verdict,
            )
        except Exception:
            logger.exception("Postmortem evaluation failed")

    thread = threading.Thread(target=_run, name="postmortem-evaluator", daemon=False)
    thread.start()
    return thread


def launch_walkthrough_postmortem_async(
    seed_path: str,
    workflow_result: Dict[str, Any],
    walkthrough_root: str,
    output_dir: str,
    filter_slug: Optional[str] = None,
) -> threading.Thread:
    """Launch walkthrough prompt-quality postmortem in a daemon thread."""

    def _run() -> None:
        try:
            seed = Path(seed_path)
            if not seed.exists():
                logger.error("Walkthrough postmortem: seed file not found: %s", seed_path)
                return

            with open(seed, "r", encoding="utf-8") as fh:
                seed_data = json.load(fh)

            seed_tasks = seed_data.get("tasks", [])
            if not seed_tasks:
                logger.warning("Walkthrough postmortem: no tasks in seed file")
                return

            evaluator = WalkthroughPromptEvaluator()
            report = evaluator.evaluate(
                seed_tasks=seed_tasks,
                walkthrough_root=walkthrough_root,
                workflow_result=workflow_result,
                output_dir=output_dir,
                filter_slug=filter_slug,
            )
            logger.info(
                "Walkthrough postmortem complete: %s (score=%.2f, verdict=%s)",
                report.report_id,
                report.aggregate_score,
                report.aggregate_verdict,
            )
        except Exception:
            logger.exception("Walkthrough postmortem evaluation failed")

    thread = threading.Thread(
        target=_run,
        name="walkthrough-postmortem-evaluator",
        daemon=False,
    )
    thread.start()
    return thread
