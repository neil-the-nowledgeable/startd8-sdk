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

# Feature names shorter than this are too generic for proximity matching
# (e.g., "API", "Service") and would match ubiquitously in plan text.
_MIN_FEATURE_NAME_CHARS = 8


def _task_density_key(task: Dict[str, Any]) -> tuple:
    """Snapshot the 5 density-relevant signals of a task for change detection."""
    cfg = task.get("config", {})
    ctx = cfg.get("context", {})
    desc = cfg.get("task_description", "") or ""
    return (
        bool(ctx.get("negative_scope")),
        bool(ctx.get("target_files")),
        bool(_REQ_PATTERN.search(desc)),
        "```" in desc,
        "## Review Guidance" in desc,
    )


def _compute_density_snapshot(tasks: List[Dict[str, Any]]) -> Any:
    """Compute a DensitySnapshot summarising signal counts across all tasks."""
    from .plan_ingestion_diagnostics import DensitySnapshot

    snap = DensitySnapshot(total_tasks=len(tasks))
    for t in tasks:
        cfg = t.get("config", {})
        ctx = cfg.get("context", {})
        desc = cfg.get("task_description", "") or ""
        if ctx.get("negative_scope"):
            snap.with_negative_scope += 1
        if ctx.get("target_files"):
            snap.with_target_files += 1
        if _REQ_PATTERN.search(desc):
            snap.with_requirement_refs += 1
        if "```" in desc:
            snap.with_code_examples += 1
        if "## Review Guidance" in desc:
            snap.with_review_guidance += 1
    return snap


def _ensure_task_context(task: Dict[str, Any]) -> Dict[str, Any]:
    """Return the task's context dict, creating it if absent.

    Uses ``setdefault`` to guarantee the returned dict is the *same*
    reference stored in the task — writes to the returned dict persist.
    """
    config = task.setdefault("config", {})
    return config.setdefault("context", {})


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
        ctx = _ensure_task_context(task)
        if ctx.get("negative_scope"):
            logger.debug(
                "ENRICH-A: skipping negative_scope for %s (already set)",
                task.get("task_id", "?"),
            )
            continue
        fid = _get_task_feature_id(task)
        feat = feature_index.get(fid)
        if feat and feat.negative_scope:
            # Guard against schema drift: if negative_scope is a bare
            # string instead of a list, wrap it rather than exploding
            # into a list of characters.
            ns = feat.negative_scope
            if isinstance(ns, str):
                ns = [ns]
            ctx["negative_scope"] = list(ns)
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
    Tier 3: Convention-based from task title (tagged ``_inferred: true``)
    """
    count = 0
    for task in tasks:
        ctx = _ensure_task_context(task)
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

        # Tier 3: convention-based from task title (REQ-TDE-102)
        inferred = _infer_target_files_from_title(task.get("title", ""))
        if inferred:
            ctx["target_files"] = inferred
            ctx["_target_files_inferred"] = True
            count += 1

    return count


def _infer_target_files_from_title(title: str) -> List[str]:
    """Derive a plausible target file path from a task title.

    Uses simple naming conventions:
    - "X Service — gRPC Server" → ``x_service/x_service_server.py``
    - "X Service — Client" → ``x_service/x_service_client.py``

    Returns an empty list if no convention matches.
    """
    if not title:
        return []

    # Normalise: "Email Service — gRPC Server" → ("email_service", "grpc_server")
    parts = re.split(r"\s*[—–-]\s*", title, maxsplit=1)
    service_slug = re.sub(r"[^a-z0-9]+", "_", parts[0].strip().lower()).strip("_")
    if not service_slug:
        return []

    suffix_slug = ""
    if len(parts) > 1:
        suffix_slug = re.sub(r"[^a-z0-9]+", "_", parts[1].strip().lower()).strip("_")

    # Only infer when the title follows the "Service — Role" pattern
    if not suffix_slug:
        return []

    filename = f"{service_slug}_{suffix_slug}.py"
    return [f"{service_slug}/{filename}"]


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
    """Append ## Requirements References section and populate structured field."""
    count = 0
    for task in tasks:
        title = task.get("title", "")
        # Skip proximity search for very short titles — generic names like
        # "API" or "Service" would match ubiquitously and inject spurious refs.
        if len(title) < _MIN_FEATURE_NAME_CHARS:
            continue
        refs = _extract_req_refs_near_feature(plan_text, title, proximity_chars)
        if not refs:
            continue

        # Always populate the structured context field (merge-with-dedup)
        ctx = _ensure_task_context(task)
        existing = set(ctx.get("requirements_refs") or [])
        merged = list(existing | set(refs))
        if merged:
            ctx["requirements_refs"] = merged

        # No-clobber on description text: skip section if refs already inline
        cfg = task.get("config", {})
        desc = cfg.get("task_description", "") or ""
        if _REQ_PATTERN.search(desc):
            logger.debug(
                "ENRICH-A: skipping requirement_refs text for %s (already present)",
                task.get("task_id", "?"),
            )
        else:
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
    """Append ## API Signatures code block and populate structured field."""
    count = 0
    for task in tasks:
        fid = _get_task_feature_id(task)
        feat = feature_index.get(fid)
        if not feat or not feat.api_signatures:
            continue

        sigs = feat.api_signatures[:_MAX_SIGNATURES_PER_TASK]

        # Always populate the structured context field (merge-with-dedup)
        ctx = _ensure_task_context(task)
        existing = set(ctx.get("api_signatures") or [])
        merged = list(existing | set(sigs))
        if merged:
            ctx["api_signatures"] = merged

        # No-clobber on description text: skip fenced block if already present
        cfg = task.get("config", {})
        desc = cfg.get("task_description", "") or ""
        if "```" in desc:
            logger.debug(
                "ENRICH-A: skipping api_signatures text for %s (code blocks exist)",
                task.get("task_id", "?"),
            )
        else:
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

        # Strategy 1: placement field matches a task's target_files.
        # Use exact match or parent-containment (not bare substring `in`)
        # to avoid false positives like "server.py" matching "test_server.py".
        if placement:
            for tf, tf_tasks in file_to_tasks.items():
                if tf == placement or tf.endswith("/" + placement) or placement.endswith("/" + tf):
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
) -> Any:
    """Run all deterministic enrichment steps on *tasks* in-place (REQ-TDE-105).

    Each step is wrapped in a try/except so a failure in one step never
    blocks subsequent steps — enrichment is advisory, like diagnostic
    persistence.

    Returns an ``EnrichmentDiagnostic`` (REQ-TDE-400).
    """
    from .plan_ingestion_diagnostics import EnrichmentDiagnostic

    t0 = time.monotonic()
    diag = EnrichmentDiagnostic()
    feature_index = _build_feature_index(features)

    # Snapshot density signals before enrichment
    diag.before = _compute_density_snapshot(tasks)
    keys_before: Dict[str, tuple] = {
        t.get("task_id", ""): _task_density_key(t) for t in tasks
    }

    # Step 1: Negative scope forwarding (REQ-TDE-100)
    if enrich_negative_scope:
        try:
            diag.negative_scope_added = _enrich_negative_scope(tasks, feature_index)
        except Exception:
            logger.warning("ENRICH-A: negative_scope step failed", exc_info=True)

    # Step 2: Target files inference (REQ-TDE-102)
    if enrich_target_files:
        try:
            diag.target_files_inferred = _enrich_target_files(tasks, feature_index)
        except Exception:
            logger.warning("ENRICH-A: target_files step failed", exc_info=True)

    # Step 3: Requirement reference injection (REQ-TDE-101)
    if enrich_requirement_refs:
        try:
            diag.requirement_refs_added = _enrich_requirement_refs(
                tasks, plan_text, enrich_req_proximity_chars,
            )
        except Exception:
            logger.warning("ENRICH-A: requirement_refs step failed", exc_info=True)

    # Step 4: API signature stubs (REQ-TDE-103)
    if enrich_api_signatures:
        try:
            diag.api_signatures_added = _enrich_api_signatures(tasks, feature_index)
        except Exception:
            logger.warning("ENRICH-A: api_signatures step failed", exc_info=True)

    # Step 5: REFINE suggestion mapping (REQ-TDE-104)
    if enrich_refine_suggestions and refine_suggestions:
        try:
            diag.refine_suggestions_mapped = _enrich_refine_suggestions(
                tasks, refine_suggestions,
            )
        except Exception:
            logger.warning("ENRICH-A: refine_suggestions step failed", exc_info=True)

    # Snapshot density signals after enrichment
    diag.after = _compute_density_snapshot(tasks)

    # Count enriched vs skipped tasks (O(n) with dict lookup)
    for t in tasks:
        tid = t.get("task_id", "")
        before_key = keys_before.get(tid)
        if before_key is not None and _task_density_key(t) != before_key:
            diag.tasks_enriched += 1
        else:
            diag.tasks_skipped += 1

    diag.time_ms = int((time.monotonic() - t0) * 1000)

    # Per-step counts
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

    # Before/after delta summary
    b, a = diag.before, diag.after
    if b and a:
        n = a.total_tasks
        logger.info(
            "ENRICH-A delta: neg_scope %d/%d→%d/%d (+%d), "
            "req_refs %d/%d→%d/%d (+%d), "
            "code %d/%d→%d/%d (+%d), "
            "target %d/%d→%d/%d (+%d), "
            "guidance %d/%d→%d/%d (+%d)",
            b.with_negative_scope, n, a.with_negative_scope, n,
            a.with_negative_scope - b.with_negative_scope,
            b.with_requirement_refs, n, a.with_requirement_refs, n,
            a.with_requirement_refs - b.with_requirement_refs,
            b.with_code_examples, n, a.with_code_examples, n,
            a.with_code_examples - b.with_code_examples,
            b.with_target_files, n, a.with_target_files, n,
            a.with_target_files - b.with_target_files,
            b.with_review_guidance, n, a.with_review_guidance, n,
            a.with_review_guidance - b.with_review_guidance,
        )

    return diag
