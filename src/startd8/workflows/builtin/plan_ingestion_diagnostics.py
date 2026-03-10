"""Plan Ingestion Diagnostics — Kaizen Phase 0 (REQ-KPI-1xx, 3xx).

Typed dataclasses and deterministic quality metrics for the plan ingestion
pipeline.  Produces ``plan-ingestion-diagnostic.json`` with per-phase metrics
and a composite seed quality score.

Advisory persistence — I/O failures never block a successful ingestion run.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ...logging_config import get_logger

logger = get_logger(__name__)


# ── Dataclasses ──────────────────────────────────────────────────────


@dataclass
class PhaseDiagnostic:
    """Per-phase diagnostic metrics."""

    phase: str = ""
    success: bool = True
    time_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    code_extraction_fallback: bool = False
    quality_signals: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskDensity:
    """Per-task description density metrics."""

    task_id: str = ""
    description_chars: int = 0
    description_lines: int = 0
    has_code_examples: bool = False
    has_requirements_refs: bool = False
    has_negative_scope: bool = False


@dataclass
class IngestionDiagnostic:
    """Complete diagnostic report for a plan ingestion run."""

    schema_version: str = "1.0.0"
    run_timestamp: str = ""
    plan_source: str = ""
    plan_checksum: str = ""
    route: str = ""
    overall_success: bool = False
    phases: Dict[str, PhaseDiagnostic] = field(default_factory=dict)
    totals: Dict[str, Any] = field(default_factory=dict)
    seed_quality_score: float = 0.0
    quality_warnings: List[str] = field(default_factory=list)
    task_density: List[TaskDensity] = field(default_factory=list)
    enrichment: Optional[EnrichmentDiagnostic] = None


@dataclass
class EnrichmentDiagnostic:
    """Diagnostic metrics for deterministic task enrichment (REQ-TDE-400)."""

    enabled: bool = True
    negative_scope_added: int = 0
    requirement_refs_added: int = 0
    target_files_inferred: int = 0
    api_signatures_added: int = 0
    refine_suggestions_mapped: int = 0
    tasks_enriched: int = 0
    tasks_skipped: int = 0
    time_ms: int = 0


@dataclass
class PlanIngestionKaizenConfig:
    """Kaizen overrides for plan ingestion runs (REQ-KPI-500)."""

    parse_prompt_suffix: str = ""
    assess_prompt_suffix: str = ""
    transform_prompt_suffix: str = ""
    complexity_threshold_override: Optional[int] = None

    # REFINE phase overrides (REQ-KPI-500 extension)
    refine_scope_override: str = ""
    refine_review_profile: Optional[Dict[str, Any]] = field(default_factory=dict)
    refine_rounds_override: Optional[int] = None

    # Option A: Deterministic enrichment (REQ-TDE-3xx) — always runs
    enrich_negative_scope: bool = True       # REQ-TDE-100
    enrich_requirement_refs: bool = True     # REQ-TDE-101
    enrich_target_files: bool = True         # REQ-TDE-102
    enrich_api_signatures: bool = True       # REQ-TDE-103
    enrich_refine_suggestions: bool = True   # REQ-TDE-104
    enrich_req_proximity_chars: int = 500    # REQ-TDE-101 proximity window


def load_kaizen_config(path: Path) -> PlanIngestionKaizenConfig:
    """Load kaizen config from a JSON file.

    Expected format::

        {
            "plan_ingestion_kaizen": {
                "parse_prompt_suffix": "...",
                "complexity_threshold_override": 50,
                "refine_scope_override": "Focus on ...",
                "refine_review_profile": {
                    "persona": "...",
                    "focus": "...",
                    "areas": ["completeness", "clarity"]
                },
                "refine_rounds_override": 2
            }
        }

    Unknown keys are silently ignored.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    section = data.get("plan_ingestion_kaizen", {})
    known = {f for f in PlanIngestionKaizenConfig.__dataclass_fields__}
    return PlanIngestionKaizenConfig(**{
        k: v for k, v in section.items() if k in known
    })


# ── Quality metric functions ─────────────────────────────────────────


def compute_parse_quality(
    features: list,
    dependency_graph: Dict[str, Any],
    mentioned_files: list,
) -> Dict[str, Any]:
    """Compute PARSE phase quality signals (REQ-KPI-300).

    Args:
        features: List of ParsedFeature (or similar with .target_files, etc.)
        dependency_graph: Feature dependency graph dict.
        mentioned_files: Files mentioned in the plan.
    """
    total = len(features) or 1
    return {
        "features_extracted": len(features),
        "files_mentioned": len(mentioned_files),
        "features_with_targets": sum(
            1 for f in features if getattr(f, "target_files", None)
        ),
        "features_with_deps": sum(
            1 for f in features if getattr(f, "dependencies", None)
        ),
        "multi_file_features": sum(
            1 for f in features if len(getattr(f, "target_files", []) or []) > 1
        ),
        "features_with_signatures": sum(
            1 for f in features if getattr(f, "api_signatures", None)
        ),
        "dep_graph_coverage": round(len(dependency_graph) / total, 3),
    }


def compute_assess_quality(
    composite: int,
    route_value: str,
    threshold: int,
    dimensions: List[int],
) -> Dict[str, Any]:
    """Compute ASSESS phase quality signals (REQ-KPI-301).

    Args:
        composite: Composite complexity score.
        route_value: Route decision string ("prime" or "artisan").
        threshold: Complexity threshold used for routing.
        dimensions: List of dimensional scores (7 or 8 values).
    """
    return {
        "composite_score": composite,
        "route_decision": route_value,
        "route_margin": abs(composite - threshold),
        "dimension_spread": (max(dimensions) - min(dimensions)) if dimensions else 0,
    }


# ── Density thresholds (REQ-KPI-303 extension) ─────────────────────

_MIN_DESCRIPTION_CHARS = 500  # Tasks below this produce poor code generation


def compute_density_warnings(
    density: List[TaskDensity],
) -> List[str]:
    """Generate warnings for shallow task descriptions (REQ-KPI-303 extension)."""
    warnings: List[str] = []
    if not density:
        return warnings
    shallow_count = sum(1 for d in density if d.description_chars < _MIN_DESCRIPTION_CHARS)
    if shallow_count > 0:
        warnings.append(
            f"{shallow_count}/{len(density)} task(s) have descriptions < {_MIN_DESCRIPTION_CHARS} chars"
        )
    no_code = sum(1 for d in density if not d.has_code_examples)
    if no_code == len(density):
        warnings.append("no tasks have code examples in descriptions")
    no_refs = sum(1 for d in density if not d.has_requirements_refs)
    if no_refs > len(density) * 0.5:
        warnings.append(
            f"{no_refs}/{len(density)} task(s) missing requirements references"
        )
    return warnings


def compute_seed_quality(
    seed_dict: Dict[str, Any],
    schema_valid: bool = True,
    task_density: Optional[List[TaskDensity]] = None,
) -> Tuple[float, List[str]]:
    """Compute weighted seed quality score and warnings (REQ-KPI-302).

    When *task_density* is provided, the formula includes description depth
    and richness components that penalise shallow single-line descriptions.
    Without it the original 4-component formula is used (backward compat).

    Returns:
        (score, warnings) where score is 0.0–1.0.
    """
    tasks = seed_dict.get("tasks", [])
    total = len(tasks) or 1

    # Task description coverage
    tasks_with_desc = sum(
        1 for t in tasks
        if t.get("config", {}).get("task_description")
    )
    desc_ratio = tasks_with_desc / total

    # Target file coverage
    tasks_with_targets = sum(
        1 for t in tasks
        if t.get("config", {}).get("context", {}).get("target_files")
    )
    target_ratio = tasks_with_targets / total

    # Schema validity
    schema_score = 1.0 if schema_valid else 0.0

    # Field coverage — 6 optional enrichment fields
    _OPTIONAL_FIELDS = [
        "architectural_context", "design_calibration", "service_metadata",
        "onboarding", "context_files", "project_metadata",
    ]
    warnings: List[str] = []
    for fld in _OPTIONAL_FIELDS:
        if not seed_dict.get(fld):
            warnings.append(f"no {fld}")
    coverage_score = max(0.0, 1.0 - len(warnings) / len(_OPTIONAL_FIELDS))

    # Additional structural warnings
    if not tasks:
        warnings.insert(0, "seed has no tasks")
    tasks_missing_desc = total - tasks_with_desc
    if tasks_missing_desc > 0:
        warnings.append(f"{tasks_missing_desc}/{len(tasks)} task(s) missing description")
    tasks_missing_targets = total - tasks_with_targets
    if tasks_missing_targets > 0:
        warnings.append(
            f"{tasks_missing_targets}/{len(tasks)} task(s) missing target_files"
        )

    if task_density is not None:
        # Recalibrated 6-component formula with depth + richness
        # Description depth: average of min(chars/500, 1.0)
        if task_density:
            depth_score = sum(
                min(d.description_chars / _MIN_DESCRIPTION_CHARS, 1.0)
                for d in task_density
            ) / len(task_density)
        else:
            depth_score = 0.0

        # Description richness: fraction with code examples OR requirements refs
        if task_density:
            rich_count = sum(
                1 for d in task_density
                if d.has_code_examples or d.has_requirements_refs
            )
            richness_score = rich_count / len(task_density)
        else:
            richness_score = 0.0

        score = round(
            0.20 * desc_ratio
            + 0.20 * target_ratio
            + 0.15 * schema_score
            + 0.15 * coverage_score
            + 0.15 * depth_score
            + 0.15 * richness_score,
            4,
        )

        # Merge density warnings
        warnings.extend(compute_density_warnings(task_density))
    else:
        # Original 4-component formula (backward compat)
        score = round(
            0.3 * desc_ratio
            + 0.3 * target_ratio
            + 0.2 * schema_score
            + 0.2 * coverage_score,
            4,
        )

    return score, warnings


def compute_refine_quality(review_output: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute REFINE phase quality signals (REQ-KPI-304)."""
    if not review_output:
        return {
            "rounds_completed": 0,
            "suggestions_total": 0,
            "suggestions_accepted": 0,
            "suggestions_rejected": 0,
            "acceptance_rate": 0.0,
        }
    triage = review_output.get("triage") or {}
    _acc = triage.get("accepted", [])
    accepted = _acc if isinstance(_acc, int) else len(_acc)
    _rej = triage.get("rejected", [])
    rejected = _rej if isinstance(_rej, int) else len(_rej)
    total = accepted + rejected
    return {
        "rounds_completed": review_output.get("rounds_completed", 0),
        "suggestions_total": total,
        "suggestions_accepted": accepted,
        "suggestions_rejected": rejected,
        "acceptance_rate": round(accepted / total, 3) if total else 0.0,
    }


_REQ_PATTERN = re.compile(r"\bREQ[-_]?\w+", re.IGNORECASE)


def compute_task_density(tasks: List[Dict[str, Any]]) -> List[TaskDensity]:
    """Compute per-task description density (REQ-KPI-303)."""
    results = []
    for t in tasks:
        cfg = t.get("config", {})
        desc = cfg.get("task_description", "") or ""
        ctx = cfg.get("context", {})
        neg_scope = ctx.get("negative_scope") or cfg.get("negative_scope")
        results.append(TaskDensity(
            task_id=t.get("task_id", ""),
            description_chars=len(desc),
            description_lines=desc.count("\n") + 1 if desc else 0,
            has_code_examples="```" in desc,
            has_requirements_refs=bool(_REQ_PATTERN.search(desc)),
            has_negative_scope=bool(neg_scope),
        ))
    return results


# ── Assembly ─────────────────────────────────────────────────────────


def build_diagnostic(
    *,
    run_timestamp: str,
    plan_source: str,
    plan_checksum: str,
    route: str,
    overall_success: bool,
    phase_diagnostics: Dict[str, PhaseDiagnostic],
    seed_quality_score: float = 0.0,
    quality_warnings: Optional[List[str]] = None,
    task_density: Optional[List[TaskDensity]] = None,
    enrichment: Optional[EnrichmentDiagnostic] = None,
) -> IngestionDiagnostic:
    """Assemble a complete diagnostic report."""
    totals: Dict[str, Any] = {
        "time_ms": sum(p.time_ms for p in phase_diagnostics.values()),
        "cost_usd": round(
            sum(p.cost_usd for p in phase_diagnostics.values()), 6
        ),
        "input_tokens": sum(p.input_tokens for p in phase_diagnostics.values()),
        "output_tokens": sum(p.output_tokens for p in phase_diagnostics.values()),
        "llm_calls": sum(
            1 for p in phase_diagnostics.values()
            if p.phase in ("parse", "assess", "transform", "refine") and p.success
        ),
    }
    return IngestionDiagnostic(
        run_timestamp=run_timestamp,
        plan_source=plan_source,
        plan_checksum=plan_checksum,
        route=route,
        overall_success=overall_success,
        phases=phase_diagnostics,
        totals=totals,
        seed_quality_score=seed_quality_score,
        quality_warnings=quality_warnings or [],
        task_density=task_density or [],
        enrichment=enrichment,
    )


# ── Persistence ──────────────────────────────────────────────────────


def persist_diagnostic(diag: IngestionDiagnostic, output_dir: Path) -> None:
    """Write diagnostic report to ``plan-ingestion-diagnostic.json``.

    Advisory — never raises on I/O failure.
    """
    try:
        path = output_dir / "plan-ingestion-diagnostic.json"
        output_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(diag), indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        logger.info("Kaizen diagnostic written to %s", path)
    except OSError as err:
        logger.warning("Kaizen diagnostic write failed: %s", err)


# ── Prompt-response capture (Phase 1, REQ-KPI-2xx) ──────────────────


_DEFAULT_MAX_BYTES = 2 * 1024 * 1024  # 2 MiB


def _write_with_limit(path: Path, text: str, max_bytes: int) -> None:
    """Write text to *path*, truncating if encoded size exceeds *max_bytes*."""
    encoded = text.encode("utf-8")
    if len(encoded) > max_bytes:
        truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
        path.write_text(
            truncated
            + f"\n<!-- TRUNCATED at {max_bytes} bytes"
            + f" (original: {len(encoded)}) -->",
            encoding="utf-8",
        )
    else:
        path.write_text(text, encoding="utf-8")


def persist_prompt_response(
    output_dir: Path,
    phase: str,
    prompt: str,
    response: str,
    *,
    max_bytes: int = _DEFAULT_MAX_BYTES,
) -> None:
    """Persist full prompt and response text for a phase.

    Files are written to ``<output_dir>/kaizen-prompts/<phase>_prompt.txt``
    and ``<phase>_response.txt``.

    Advisory — never raises on I/O failure.
    """
    kaizen_dir = output_dir / "kaizen-prompts"
    try:
        kaizen_dir.mkdir(parents=True, exist_ok=True)
        _write_with_limit(kaizen_dir / f"{phase}_prompt.txt", prompt, max_bytes)
        _write_with_limit(kaizen_dir / f"{phase}_response.txt", response, max_bytes)
        logger.debug("Kaizen prompt capture: %s (%d+%d bytes)",
                      phase, len(prompt), len(response))
    except OSError as err:
        logger.warning("Kaizen prompt capture failed for %s: %s", phase, err)
