"""Design Collision Detection for the Artisan DESIGN phase (REQ-CCD-500-503).

Heuristic-based compatibility check across design documents within a lane.
All checks are string/regex based -- no LLM calls.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from itertools import combinations
from typing import Any, Literal

from startd8.logging_config import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# REQ-CCD-502: Collision Severity Classification
# ---------------------------------------------------------------------------


class CollisionSeverity(str, Enum):
    """Severity of a detected design collision.

    COHERENT    -- No conflicts detected within the lane.
    WARNING     -- Potential conflict (e.g., create+update mode mismatch, uncertain
                   duplicate name match). Implementation should proceed with caution.
    CONFLICTING -- Definite conflict (e.g., two tasks both create the same file from
                   scratch, or two tasks define the same class name for the same file).
    """

    COHERENT = "COHERENT"
    WARNING = "WARNING"
    CONFLICTING = "CONFLICTING"


@dataclass
class DesignCollision:
    """A single detected collision between two task designs."""

    file_path: str  # Shared file where the collision was detected
    task_a: str  # task_id of first task
    task_b: str  # task_id of second task
    conflict_type: Literal[
        "mode_conflict", "duplicate_class", "duplicate_function", "mode_double_create"
    ]
    severity: CollisionSeverity
    detail: str  # Human-readable description


@dataclass
class LaneCollisionResult:
    """Post-lane compatibility check result for a single lane."""

    lane_index: int
    task_ids: list[str]
    shared_files: list[str]
    collisions: list[DesignCollision] = field(default_factory=list)
    status: CollisionSeverity = CollisionSeverity.COHERENT

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict for context propagation."""
        return {
            "lane_index": self.lane_index,
            "task_ids": self.task_ids,
            "shared_files": self.shared_files,
            "collisions": [
                {
                    "file_path": c.file_path,
                    "task_a": c.task_a,
                    "task_b": c.task_b,
                    "conflict_type": c.conflict_type,
                    "severity": c.severity.value,
                    "detail": c.detail,
                }
                for c in self.collisions
            ],
            "status": self.status.value,
        }


# ---------------------------------------------------------------------------
# REQ-CCD-500: Entity Extraction (regex-based)
# ---------------------------------------------------------------------------

_CLASS_PATTERN = re.compile(
    r"^\s*(?:class|Class)\s+([A-Z][A-Za-z0-9_]+)", re.MULTILINE
)
_FUNC_PATTERN = re.compile(
    r"^\s*(?:def|function)\s+([a-z_][A-Za-z0-9_]+)\s*\(", re.MULTILINE
)
_IMPORT_PATTERN = re.compile(
    r"^\s*(?:from|import)\s+([a-zA-Z0-9_.]+)", re.MULTILINE
)


def extract_entities(design_text: str) -> dict[str, set[str]]:
    """Extract named entities from a design document.

    Returns:
        Dict with keys "classes", "functions", "imports" -- each a set of
        extracted names/paths.  Empty sets when text has no matching patterns.
    """
    if not design_text:
        return {"classes": set(), "functions": set(), "imports": set()}
    return {
        "classes": set(_CLASS_PATTERN.findall(design_text)),
        "functions": set(_FUNC_PATTERN.findall(design_text)),
        "imports": set(_IMPORT_PATTERN.findall(design_text)),
    }


# ---------------------------------------------------------------------------
# REQ-CCD-501: Design Mode Conflict Detection
# ---------------------------------------------------------------------------


def _check_mode_conflicts(
    fpath: str,
    task_ids: list[str],
    design_mode_summary: dict[str, str],
    result: LaneCollisionResult,
) -> None:
    """Check for design_mode conflicts among tasks contesting a shared file.

    REQ-CCD-501:
    - create + update  -> WARNING
    - create + create  -> CONFLICTING
    - update + update  -> INFO log only (not a conflict record)
    """
    creators = [
        tid for tid in task_ids if design_mode_summary.get(tid) == "create"
    ]
    updaters = [
        tid for tid in task_ids if design_mode_summary.get(tid) == "update"
    ]

    # Two creators for same file: both would overwrite the file from scratch
    if len(creators) >= 2:
        for ca, cb in combinations(creators, 2):
            result.collisions.append(
                DesignCollision(
                    file_path=fpath,
                    task_a=ca,
                    task_b=cb,
                    conflict_type="mode_double_create",
                    severity=CollisionSeverity.CONFLICTING,
                    detail=(
                        f"Both tasks plan to CREATE {fpath} from scratch. "
                        f"Second write will clobber the first. "
                        f"One task should be redesigned to use 'update' mode."
                    ),
                )
            )

    # Create + update: create assumes file doesn't exist, update assumes it does
    for creator in creators:
        for updater in updaters:
            result.collisions.append(
                DesignCollision(
                    file_path=fpath,
                    task_a=creator,
                    task_b=updater,
                    conflict_type="mode_conflict",
                    severity=CollisionSeverity.WARNING,
                    detail=(
                        f"Task {creator} plans to CREATE {fpath} while "
                        f"task {updater} plans to UPDATE it. Verify ordering "
                        f"and that the create task runs first."
                    ),
                )
            )

    # update + update: informational only (when no creators are present;
    # create+update pairs are already captured above as mode_conflict)
    if len(updaters) >= 2 and not creators:
        logger.info(
            "DESIGN CCD-501: %d tasks update shared file %s -- "
            "lane-peer context should prevent interface conflicts",
            len(updaters),
            fpath,
        )


# ---------------------------------------------------------------------------
# REQ-CCD-500: Entity Collision Detection (pairwise)
# ---------------------------------------------------------------------------


_ENTITY_SINGULAR = {"classes": "class", "functions": "function"}


def _check_entity_collisions(
    fpath: str,
    task_ids: list[str],
    task_entities: dict[str, dict[str, set[str]]],
    result: LaneCollisionResult,
) -> None:
    """Pairwise duplicate class/function detection for a shared file."""
    for ta, tb in combinations(task_ids, 2):
        ents_a = task_entities.get(ta, {})
        ents_b = task_entities.get(tb, {})

        for etype in ("classes", "functions"):
            shared = ents_a.get(etype, set()) & ents_b.get(etype, set())
            if shared:
                singular = _ENTITY_SINGULAR[etype]
                result.collisions.append(
                    DesignCollision(
                        file_path=fpath,
                        task_a=ta,
                        task_b=tb,
                        conflict_type=f"duplicate_{singular}",
                        severity=CollisionSeverity.WARNING,
                        detail=(
                            f"Both tasks define {etype} {sorted(shared)} "
                            f"in {fpath}. Verify they are identical definitions "
                            f"or designed for non-overlapping scopes."
                        ),
                    )
                )


# ---------------------------------------------------------------------------
# REQ-CCD-500: Main Collision Check Orchestrator
# ---------------------------------------------------------------------------


def check_lane_collisions(
    lane_index: int,
    lane_tasks: list,  # list[SeedTask] -- avoids circular import
    design_results: dict[str, dict[str, Any]],
    shared_file_manifest: dict[str, list[str]],
    design_mode_summary: dict[str, str],
) -> LaneCollisionResult:
    """Run post-lane compatibility check for a single lane.

    For each shared file in the lane, extract entities from each task's
    design document and check for duplicate class/function definitions.
    Also checks design_mode_summary for create/update conflicts (REQ-CCD-501).
    """
    lane_task_ids = [t.task_id for t in lane_tasks]
    lane_task_id_set = set(lane_task_ids)
    # Identify shared files that involve 2+ tasks in THIS lane
    lane_shared_files: list[str] = [
        fpath
        for fpath, contesting in shared_file_manifest.items()
        if len(set(contesting) & lane_task_id_set) >= 2
    ]

    result = LaneCollisionResult(
        lane_index=lane_index,
        task_ids=lane_task_ids,
        shared_files=lane_shared_files,
    )

    if not lane_shared_files:
        return result  # No shared files -> COHERENT by definition

    # Build per-task entity map
    task_entities: dict[str, dict[str, set[str]]] = {}
    for tid in lane_task_ids:
        dr = design_results.get(tid, {})
        doc_text = dr.get("design_document", "")
        task_entities[tid] = extract_entities(doc_text)

    for fpath in lane_shared_files:
        contesting_in_lane = [
            tid
            for tid in (shared_file_manifest.get(fpath) or [])
            if tid in lane_task_id_set
        ]
        if len(contesting_in_lane) < 2:
            continue

        # Mode conflict detection (REQ-CCD-501) -- pairwise
        _check_mode_conflicts(
            fpath, contesting_in_lane, design_mode_summary, result
        )

        # Entity collision detection -- pairwise class/function duplicates
        _check_entity_collisions(fpath, contesting_in_lane, task_entities, result)

    # Determine overall lane status from worst collision seen
    if any(
        c.severity == CollisionSeverity.CONFLICTING for c in result.collisions
    ):
        result.status = CollisionSeverity.CONFLICTING
    elif any(
        c.severity == CollisionSeverity.WARNING for c in result.collisions
    ):
        result.status = CollisionSeverity.WARNING
    else:
        result.status = CollisionSeverity.COHERENT

    return result


# ---------------------------------------------------------------------------
# REQ-CCD-503: Collision Context Formatting for Redesign Prompt Injection
# ---------------------------------------------------------------------------


def _format_collision_context(collisions: list[dict[str, Any]]) -> str:
    """Format collision list as human-readable text for redesign prompt injection.

    Args:
        collisions: List of collision dicts (from LaneCollisionResult.to_dict()).

    Returns:
        Formatted multiline string describing each collision, or empty string
        if no collisions are provided.
    """
    if not collisions:
        return ""

    lines: list[str] = []
    for idx, col in enumerate(collisions, start=1):
        severity = col.get("severity", "UNKNOWN")
        conflict_type = col.get("conflict_type", "unknown")
        file_path = col.get("file_path", "<unknown>")
        task_a = col.get("task_a", "?")
        task_b = col.get("task_b", "?")
        detail = col.get("detail", "")

        lines.append(
            f"  {idx}. [{severity}] {conflict_type} in {file_path} "
            f"(tasks: {task_a} vs {task_b})"
        )
        if detail:
            lines.append(f"     Detail: {detail}")

    return "\n".join(lines)
