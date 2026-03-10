"""Task Density Enrichment — Deterministic post-REFINE enrichment (Option A).

Maps document-level REFINE suggestions and ParsedFeature metadata to per-task
density improvements: negative scope, requirement references, target files,
API signature stubs, and review guidance.

Pipeline position::

    PARSE → ASSESS → TRANSFORM → REFINE → [ENRICH-A] → EMIT

Zero LLM cost.  Runs unconditionally unless individual steps are disabled
via ``PlanIngestionKaizenConfig``.

See: docs/design/plan-ingestion/TASK_DENSITY_ENRICHMENT_REQUIREMENTS.md
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional

from ...logging_config import get_logger
from ...utils.prime_task_enrichment import extract_target_files

logger = get_logger(__name__)

# Match multi-segment requirement IDs like REQ-PI-003, REQ_KPI_500, REQ-TDE-100
_REQ_PATTERN = re.compile(r"\bREQ(?:[-_]\w+)+", re.IGNORECASE)

# Maximum API signatures appended per task (REQ-TDE-103)
_MAX_SIGNATURES_PER_TASK = 5


def _build_feature_index(
    features: list,
) -> Dict[str, Any]:
    """Build feature_id → ParsedFeature lookup from a list of features."""
    return {f.feature_id: f for f in features}


def _get_task_feature_id(task: Dict[str, Any]) -> str:
    """Extract feature_id from a task dict."""
    return task.get("config", {}).get("context", {}).get("feature_id", "")


# ── Step 1: Negative Scope Forwarding (REQ-TDE-100) ──────────────────


def _enrich_negative_scope(
    tasks: List[Dict[str, Any]],
    feature_index: Dict[str, Any],
) -> int:
    """Copy ParsedFeature.negative_scope to task context (no-clobber)."""
    count = 0
    for task in tasks:
        ctx = task.get("config", {}).get("context", {})
        if ctx.get("negative_scope"):
            logger.debug(
                "ENRICH-A: skipping negative_scope for %s (already set)",
                task.get("task_id", "?"),
            )
            continue
        fid = _get_task_feature_id(task)
        feat = feature_index.get(fid)
        if feat and feat.negative_scope:
            ctx["negative_scope"] = list(feat.negative_scope)
            count += 1
    return count


# ── Step 2: Target Files Inference (REQ-TDE-102) ─────────────────────


def _enrich_target_files(
    tasks: List[Dict[str, Any]],
    feature_index: Dict[str, Any],
) -> int:
    """3-tier target_files inference (no-clobber).

    Tier 1: Copy from ParsedFeature.target_files
    Tier 2: Regex extraction from description via extract_target_files()
    Tier 3: Convention-based (not implemented yet — tagged as _inferred)
    """
    count = 0
    for task in tasks:
        ctx = task.get("config", {}).get("context", {})
        if ctx.get("target_files"):
            continue

        fid = _get_task_feature_id(task)
        feat = feature_index.get(fid)

        # Tier 1: feature-level target files
        if feat and feat.target_files:
            ctx["target_files"] = list(feat.target_files)
            count += 1
            continue

        # Tier 2: regex extraction from description
        desc = task.get("config", {}).get("task_description", "") or ""
        extracted = extract_target_files(desc)
        if extracted:
            ctx["target_files"] = extracted
            count += 1
            continue

    return count


# ── Step 3: Requirement Reference Injection (REQ-TDE-101) ────────────


def _extract_req_refs_near_feature(
    plan_text: str,
    feature_name: str,
    proximity_chars: int = 500,
) -> List[str]:
    """Find REQ-* patterns within ±proximity_chars of feature_name in plan text."""
    if not plan_text or not feature_name:
        return []

    refs: List[str] = []
    seen: set = set()
    # Find all occurrences of the feature name in the plan text
    name_lower = feature_name.lower()
    text_lower = plan_text.lower()
    start = 0
    while True:
        pos = text_lower.find(name_lower, start)
        if pos == -1:
            break
        # Extract window around this mention
        window_start = max(0, pos - proximity_chars)
        window_end = min(len(plan_text), pos + len(feature_name) + proximity_chars)
        window = plan_text[window_start:window_end]

        for match in _REQ_PATTERN.finditer(window):
            ref = match.group(0)
            if ref not in seen:
                seen.add(ref)
                refs.append(ref)
        start = pos + 1

    return refs


def _enrich_requirement_refs(
    tasks: List[Dict[str, Any]],
    plan_text: str,
    proximity_chars: int = 500,
) -> int:
    """Append ## Requirements References section to task descriptions."""
    count = 0
    for task in tasks:
        cfg = task.get("config", {})
        desc = cfg.get("task_description", "") or ""

        # No-clobber: skip if description already has requirement refs
        if _REQ_PATTERN.search(desc):
            logger.debug(
                "ENRICH-A: skipping requirement_refs for %s (already present)",
                task.get("task_id", "?"),
            )
            continue

        title = task.get("title", "")
        refs = _extract_req_refs_near_feature(plan_text, title, proximity_chars)
        if not refs:
            continue

        ref_section = "\n\n## Requirements References\n" + "\n".join(
            f"- {r}" for r in refs
        )
        cfg["task_description"] = desc + ref_section
        count += 1

    return count


# ── Step 4: API Signature Code Stubs (REQ-TDE-103) ───────────────────


def _enrich_api_signatures(
    tasks: List[Dict[str, Any]],
    feature_index: Dict[str, Any],
) -> int:
    """Append ## API Signatures code block from ParsedFeature.api_signatures."""
    count = 0
    for task in tasks:
        cfg = task.get("config", {})
        desc = cfg.get("task_description", "") or ""

        # No-clobber: skip if description already has code blocks
        if "```" in desc:
            logger.debug(
                "ENRICH-A: skipping api_signatures for %s (code blocks exist)",
                task.get("task_id", "?"),
            )
            continue

        fid = _get_task_feature_id(task)
        feat = feature_index.get(fid)
        if not feat or not feat.api_signatures:
            continue

        sigs = feat.api_signatures[:_MAX_SIGNATURES_PER_TASK]
        sig_block = "\n\n## API Signatures\n```python\n" + "\n\n".join(sigs) + "\n```"
        cfg["task_description"] = desc + sig_block
        count += 1

    return count


# ── Step 5: REFINE Suggestion Mapping (REQ-TDE-104) ──────────────────


def _enrich_refine_suggestions(
    tasks: List[Dict[str, Any]],
    refine_suggestions: List[Dict[str, Any]],
) -> int:
    """Map accepted REFINE suggestions to tasks by placement/area match."""
    if not refine_suggestions:
        return 0

    count = 0
    # Build target_files → task index for placement matching
    file_to_tasks: Dict[str, List[Dict[str, Any]]] = {}
    for task in tasks:
        ctx = task.get("config", {}).get("context", {})
        for tf in ctx.get("target_files", []):
            file_to_tasks.setdefault(tf, []).append(task)

    # Area → title keyword mapping for area-based matching
    _AREA_KEYWORDS: Dict[str, List[str]] = {
        "interfaces": ["grpc", "api", "service", "server", "client", "rpc", "endpoint"],
        "data": ["model", "schema", "database", "store", "repository", "data"],
        "validation": ["valid", "check", "verify", "sanitize", "input"],
        "testing": ["test", "spec", "mock", "fixture"],
        "config": ["config", "setting", "env", "environment"],
    }

    mapped_suggestions: Dict[str, List[str]] = {}  # task_id → suggestion texts
    unmapped: List[str] = []

    for suggestion in refine_suggestions:
        placement = suggestion.get("placement", "")
        area = suggestion.get("area", "")
        rationale = suggestion.get("rationale", "")
        text = f"[{area}] {rationale}" if area and rationale else rationale or str(suggestion)

        matched = False

        # Strategy 1: placement field matches a task's target_files
        if placement:
            for tf, tf_tasks in file_to_tasks.items():
                if placement in tf or tf in placement:
                    for t in tf_tasks:
                        tid = t.get("task_id", "")
                        mapped_suggestions.setdefault(tid, []).append(text)
                        matched = True

        # Strategy 2: area keyword matching against task titles
        if not matched and area:
            keywords = _AREA_KEYWORDS.get(area.lower(), [])
            if keywords:
                for task in tasks:
                    title_lower = task.get("title", "").lower()
                    if any(kw in title_lower for kw in keywords):
                        tid = task.get("task_id", "")
                        mapped_suggestions.setdefault(tid, []).append(text)
                        matched = True

        if not matched:
            unmapped.append(text)

    # Apply mapped suggestions to task descriptions
    for task in tasks:
        tid = task.get("task_id", "")
        suggestions = mapped_suggestions.get(tid, [])
        if not suggestions and not unmapped:
            continue

        cfg = task.get("config", {})
        desc = cfg.get("task_description", "") or ""

        # No-clobber: skip if description already has review guidance
        if "## Review Guidance" in desc:
            continue

        # Combine task-specific + shared unmapped (top 3)
        all_suggestions = suggestions + unmapped[:3]
        if not all_suggestions:
            continue

        # Deduplicate
        seen: set = set()
        deduped: List[str] = []
        for s in all_suggestions:
            if s not in seen:
                seen.add(s)
                deduped.append(s)

        guidance = "\n\n## Review Guidance (from REFINE)\n" + "\n".join(
            f"- {s}" for s in deduped
        )
        cfg["task_description"] = desc + guidance
        count += 1

    return count


# ── Orchestrator ──────────────────────────────────────────────────────


def enrich_tasks_deterministic(
    tasks: List[Dict[str, Any]],
    features: list,
    plan_text: str = "",
    refine_suggestions: Optional[List[Dict[str, Any]]] = None,
    *,
    enrich_negative_scope: bool = True,
    enrich_requirement_refs: bool = True,
    enrich_target_files: bool = True,
    enrich_api_signatures: bool = True,
    enrich_refine_suggestions: bool = True,
    enrich_req_proximity_chars: int = 500,
) -> Dict[str, Any]:
    """Run all deterministic enrichment steps on *tasks* in-place (REQ-TDE-105).

    Returns an enrichment diagnostic dict (REQ-TDE-400).
    """
    from .plan_ingestion_diagnostics import EnrichmentDiagnostic

    t0 = time.monotonic()
    diag = EnrichmentDiagnostic()
    feature_index = _build_feature_index(features)

    tasks_before = set()
    for t in tasks:
        cfg = t.get("config", {})
        ctx = cfg.get("context", {})
        desc = cfg.get("task_description", "") or ""
        key = (
            bool(ctx.get("negative_scope")),
            bool(ctx.get("target_files")),
            bool(_REQ_PATTERN.search(desc)),
            "```" in desc,
        )
        tasks_before.add((t.get("task_id", ""), key))

    # Step 1: Negative scope forwarding (REQ-TDE-100)
    if enrich_negative_scope:
        diag.negative_scope_added = _enrich_negative_scope(tasks, feature_index)

    # Step 2: Target files inference (REQ-TDE-102)
    if enrich_target_files:
        diag.target_files_inferred = _enrich_target_files(tasks, feature_index)

    # Step 3: Requirement reference injection (REQ-TDE-101)
    if enrich_requirement_refs:
        diag.requirement_refs_added = _enrich_requirement_refs(
            tasks, plan_text, enrich_req_proximity_chars,
        )

    # Step 4: API signature stubs (REQ-TDE-103)
    if enrich_api_signatures:
        diag.api_signatures_added = _enrich_api_signatures(tasks, feature_index)

    # Step 5: REFINE suggestion mapping (REQ-TDE-104)
    if enrich_refine_suggestions and refine_suggestions:
        diag.refine_suggestions_mapped = _enrich_refine_suggestions(
            tasks, refine_suggestions,
        )

    # Count enriched vs skipped tasks
    for t in tasks:
        cfg = t.get("config", {})
        ctx = cfg.get("context", {})
        desc = cfg.get("task_description", "") or ""
        key = (
            bool(ctx.get("negative_scope")),
            bool(ctx.get("target_files")),
            bool(_REQ_PATTERN.search(desc)),
            "```" in desc,
        )
        tid = t.get("task_id", "")
        before_key = next(
            (bk for bt, bk in tasks_before if bt == tid), None,
        )
        if before_key is not None and key != before_key:
            diag.tasks_enriched += 1
        else:
            diag.tasks_skipped += 1

    diag.time_ms = int((time.monotonic() - t0) * 1000)

    logger.info(
        "ENRICH-A: %d/%d tasks enriched (neg_scope=%d, req_refs=%d, "
        "target_files=%d, api_sigs=%d, refine_sug=%d) in %dms",
        diag.tasks_enriched,
        len(tasks),
        diag.negative_scope_added,
        diag.requirement_refs_added,
        diag.target_files_inferred,
        diag.api_signatures_added,
        diag.refine_suggestions_mapped,
        diag.time_ms,
    )

    return diag
