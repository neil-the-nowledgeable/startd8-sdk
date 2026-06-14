"""
ContextCore task tracking artifact emitter.

Transforms parsed plan features and derived tasks into ContextCore-compatible
state files and NDJSON event logs with zero-point initialization.

Outputs are consumable by ContextCoreTaskSource, ContextCoreTaskRunner, and
the /time-series-progress-tracker skill.

Ownership boundary (REQ-PRO-001, Project Observability):
    startd8 PRODUCES the raw lifecycle signals — task state files (SpanState v2),
    a one-time zero-point seed, and the NDJSON event log. ContextCore OWNS the
    metric-ified gauges (``contextcore_task_progress``/``status``/
    ``install_completeness_percent``), the live progress computation (deltas off
    the seed — ``percent_complete`` is structurally 0 from startd8), and the
    burndown/velocity dashboards. startd8 MUST NOT build a progress-delta emitter
    (REQ-PRO-004): the observability generator reports the ``contextcore_*`` gauges
    as ContextCore-owned (``route_state=contextcore_owned``), not startd8-emitted.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...logging_config import get_logger
from ...utils.file_operations import atomic_write_json

from .plan_ingestion_models import (
    ComplexityScore,
    ParsedFeature,
    ParsedPlan,
    TaskTrackingConfig,
)

logger = get_logger(__name__)

_SCHEMA_VERSION = 2


def _slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    return re.sub(r"-+", "-", slug).strip("-")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_span_id() -> str:
    return os.urandom(8).hex()


# Terminal task statuses → a completed span (top-level status "OK", end_time set, percent 100).
_TERMINAL_STATUSES = frozenset({"done", "cancelled"})


def _top_level_status(task_status: str) -> str:
    """Map a ContextCore ``task.status`` to a SpanState v2 top-level ``status`` (OK/ERROR/UNSET)."""
    if task_status in _TERMINAL_STATUSES:
        return "OK"
    return "UNSET"


def _build_state_file(
    *,
    task_id: str,
    title: str,
    task_type: str,
    status: str,
    priority: str,
    story_points: int,
    prompt: str,
    depends_on: List[str],
    labels: List[str],
    feature_id: str,
    target_files: List[str],
    estimated_loc: int,
    project_id: str,
    sprint_id: str,
    trace_id: str,
    span_id: str,
    parent_span_id: Optional[str],
    timestamp: str,
    completion_timestamp: Optional[str] = None,
    creation_timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a single ContextCore state file dict.

    For a terminal ``status`` (done/cancelled), set the SpanState v2 top-level ``status`` to ``OK``,
    set ``end_time``, and append a completion event after the zero-point ``task.created`` event —
    this gives an honest burndown (CRP R1-F7) while preserving the zero-point invariant
    (``task.created`` stays at ``percent_complete: 0``).

    For a backfilled terminal task the ``task.created`` event MUST predate its completion
    (CRP R1-F7). ``creation_timestamp`` supplies the real start (e.g. a milestone-start or
    merge-parent date). When absent for a backfilled terminal task, ``created`` falls back to the
    completion time (so it is never *after* completion); otherwise ``created`` is the generation
    time.
    """
    is_terminal = status in _TERMINAL_STATUSES
    end_time = (completion_timestamp or timestamp) if is_terminal else None
    # Created must never post-date completion (honest burndown). Prefer an explicit creation
    # timestamp; for a backfilled terminal task fall back to its completion time; else "now".
    created_time = creation_timestamp or (end_time if is_terminal else None) or timestamp
    events: List[Dict[str, Any]] = [
        {
            "name": "task.created",
            "timestamp": created_time,
            "attributes": {"percent_complete": 0},
        }
    ]
    if is_terminal:
        events.append(
            {
                "name": "task.completed" if status == "done" else "task.cancelled",
                "timestamp": end_time,
                "attributes": {"percent_complete": 100 if status == "done" else 0},
            }
        )
    return {
        "task_id": task_id,
        "span_name": f"{task_type}:{task_id}",
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "start_time": created_time,
        "end_time": end_time,
        "status": _top_level_status(status),
        "attributes": {
            "task.id": task_id,
            "task.title": title,
            "task.type": task_type,
            "task.status": status,
            "task.priority": priority,
            "task.story_points": story_points,
            "task.prompt": prompt,
            "task.depends_on": depends_on,
            "task.labels": labels,
            "task.feature_id": feature_id,
            "task.target_files": target_files,
            "task.estimated_loc": estimated_loc,
            "project.id": project_id,
            "sprint.id": sprint_id,
        },
        "events": events,
        "schema_version": _SCHEMA_VERSION,
        "project_id": project_id,
    }


def _build_ndjson_event(
    *,
    timestamp: str,
    trace_id: str,
    span_id: str,
    parent_span_id: Optional[str],
    project_id: str,
    task_id: str,
    task_type: str,
    status: str,
    message: str,
) -> Dict[str, Any]:
    """Build a single NDJSON event line dict."""
    return {
        "timestamp": timestamp,
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "project": project_id,
        "event": "task.created",
        "task_id": task_id,
        "task_type": task_type,
        "status": "not_started",
        "percent_complete": 0,
        "message": message,
    }


def emit_task_tracking_artifacts(
    parsed_plan: ParsedPlan,
    complexity: ComplexityScore,
    tasks: List[Dict[str, Any]],
    config: TaskTrackingConfig,
    output_dir: Path,
    initial_statuses: Optional[Dict[str, str]] = None,
    completion_timestamps: Optional[Dict[str, str]] = None,
    creation_timestamps: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Generate ContextCore-compatible task tracking artifacts.

    Creates a hierarchy: plan title -> epic, each feature -> story, each task -> task.
    Every entity gets a state file with a zero-point ``task.created`` event.

    Args:
        parsed_plan: The parsed plan with features.
        complexity: Complexity assessment.
        tasks: Derived task dicts (from ``_derive_tasks_from_features``).
        config: Tracking configuration.
        output_dir: Base output directory; artifacts go into ``contextcore-tasks/`` subdir.
        initial_statuses: Optional ``{task_id: task.status}`` overrides (FR-3). Keyed by the
            emitted entity id (``{project_id}-epic``, ``{feature_id}-story``, or a task id).
            Unlisted entities default to ``"todo"`` (prior behavior, byte-for-byte).
        completion_timestamps: Optional ``{task_id: ISO-8601}`` completion times for terminal
            (done/cancelled) entities — used for an honest backfilled burndown (CRP R1-F7).
            Falls back to the generation timestamp when absent.

    Returns:
        Summary dict with project_id, trace_id, counts, and output paths.
    """
    initial_statuses = initial_statuses or {}
    completion_timestamps = completion_timestamps or {}
    creation_timestamps = creation_timestamps or {}
    timestamp = _now_iso()
    trace_id = uuid.uuid4().hex
    project_id = config.project_id or _slugify(parsed_plan.title)
    project_name = config.project_name or parsed_plan.title
    sprint_id = config.sprint_id or "sprint-1"

    tasks_dir = output_dir / "contextcore-tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    state_files: List[Dict[str, Any]] = []
    ndjson_events: List[Dict[str, Any]] = []

    # --- Epic (plan-level) ---
    epic_id = f"{project_id}-epic"
    epic_span_id = _new_span_id()

    epic_state = _build_state_file(
        task_id=epic_id,
        title=project_name,
        task_type="epic",
        status=initial_statuses.get(epic_id, "todo"),
        priority="high",
        story_points=0,
        prompt=f"Epic: {project_name}. Goals: {'; '.join(parsed_plan.goals)}",
        depends_on=[],
        labels=["epic"],
        feature_id="",
        target_files=[],
        estimated_loc=0,
        project_id=project_id,
        sprint_id=sprint_id,
        trace_id=trace_id,
        span_id=epic_span_id,
        parent_span_id=None,
        timestamp=timestamp,
        completion_timestamp=completion_timestamps.get(epic_id),
        creation_timestamp=creation_timestamps.get(epic_id),
    )
    state_files.append(epic_state)
    ndjson_events.append(_build_ndjson_event(
        timestamp=timestamp,
        trace_id=trace_id,
        span_id=epic_span_id,
        parent_span_id=None,
        project_id=project_id,
        task_id=epic_id,
        task_type="epic",
        status="todo",
        message=project_name,
    ))

    # --- Stories (one per feature) ---
    feature_span_ids: Dict[str, str] = {}
    for feat in parsed_plan.features:
        story_id = f"{feat.feature_id}-story"
        story_span_id = _new_span_id()
        feature_span_ids[feat.feature_id] = story_span_id

        story_state = _build_state_file(
            task_id=story_id,
            title=feat.name,
            task_type="story",
            status=initial_statuses.get(story_id, "todo"),
            priority="high",
            story_points=0,
            prompt=feat.description or feat.name,
            depends_on=list(feat.dependencies),  # T1.3 (FR-5): milestone deps → task.depends_on
            labels=list(feat.labels),
            feature_id=feat.feature_id,
            target_files=list(feat.target_files),
            estimated_loc=feat.estimated_loc,
            project_id=project_id,
            sprint_id=sprint_id,
            trace_id=trace_id,
            span_id=story_span_id,
            parent_span_id=epic_span_id,
            timestamp=timestamp,
            completion_timestamp=completion_timestamps.get(story_id),
            creation_timestamp=creation_timestamps.get(story_id),
        )
        state_files.append(story_state)
        ndjson_events.append(_build_ndjson_event(
            timestamp=timestamp,
            trace_id=trace_id,
            span_id=story_span_id,
            parent_span_id=epic_span_id,
            project_id=project_id,
            task_id=story_id,
            task_type="story",
            status="todo",
            message=feat.name,
        ))

    # --- Tasks ---
    # Build feature_id lookup from tasks
    task_feature_map: Dict[str, str] = {}
    for t in tasks:
        cfg = t.get("config", {})
        ctx = cfg.get("context", {})
        fid = ctx.get("feature_id", "")
        task_feature_map[t["task_id"]] = fid

    for t in tasks:
        tid = t["task_id"]
        fid = task_feature_map.get(tid, "")
        parent_story_span = feature_span_ids.get(fid)
        task_span_id = _new_span_id()

        cfg = t.get("config", {})
        ctx = cfg.get("context", {})

        task_state = _build_state_file(
            task_id=tid,
            title=t.get("title", tid),
            task_type="task",
            status=initial_statuses.get(tid, "todo"),
            priority=t.get("priority", "medium"),
            story_points=t.get("story_points", 1),
            prompt=cfg.get("task_description", t.get("title", "")),
            depends_on=t.get("depends_on", []),
            labels=t.get("labels", []),
            feature_id=fid,
            target_files=ctx.get("target_files", []),
            estimated_loc=ctx.get("estimated_loc", 0),
            project_id=project_id,
            sprint_id=sprint_id,
            trace_id=trace_id,
            span_id=task_span_id,
            parent_span_id=parent_story_span,
            timestamp=timestamp,
            completion_timestamp=completion_timestamps.get(tid),
            creation_timestamp=creation_timestamps.get(tid),
        )
        state_files.append(task_state)
        ndjson_events.append(_build_ndjson_event(
            timestamp=timestamp,
            trace_id=trace_id,
            span_id=task_span_id,
            parent_span_id=parent_story_span,
            project_id=project_id,
            task_id=tid,
            task_type="task",
            status="todo",
            message=t.get("title", tid),
        ))

    # --- Write state files ---
    for sf in state_files:
        file_path = tasks_dir / f"{sf['task_id']}.json"
        atomic_write_json(file_path, sf, indent=2)

    logger.info("Wrote %d state files to %s", len(state_files), tasks_dir)

    # --- Write NDJSON events ---
    ndjson_path: Optional[Path] = None
    if config.emit_ndjson_events:
        ndjson_path = tasks_dir / "task-events.ndjson"
        lines = [json.dumps(ev, separators=(",", ":")) for ev in ndjson_events]
        ndjson_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        logger.info("Wrote %d NDJSON events to %s", len(ndjson_events), ndjson_path)

    # --- Write manifest ---
    epic_count = sum(1 for sf in state_files if sf["attributes"]["task.type"] == "epic")
    story_count = sum(1 for sf in state_files if sf["attributes"]["task.type"] == "story")
    task_count = sum(1 for sf in state_files if sf["attributes"]["task.type"] == "task")

    manifest = {
        "project_id": project_id,
        "project_name": project_name,
        "sprint_id": sprint_id,
        "trace_id": trace_id,
        "generated_at": timestamp,
        "complexity_score": complexity.composite,
        "counts": {
            "total": len(state_files),
            "epics": epic_count,
            "stories": story_count,
            "tasks": task_count,
        },
        "output_dir": str(tasks_dir),
    }

    manifest_path = tasks_dir / "tracking-manifest.json"
    atomic_write_json(manifest_path, manifest, indent=2)

    # --- Install to ~/.contextcore/state/{project_id}/ ---
    installed_path: Optional[str] = None
    if config.install_to_contextcore:
        cc_dir = Path.home() / ".contextcore" / "state" / project_id
        cc_dir.mkdir(parents=True, exist_ok=True)
        for sf in state_files:
            dest = cc_dir / f"{sf['task_id']}.json"
            atomic_write_json(dest, sf, indent=2)
        installed_path = str(cc_dir)
        logger.info("Installed %d state files to %s", len(state_files), cc_dir)

    result: Dict[str, Any] = {
        "project_id": project_id,
        "trace_id": trace_id,
        "tasks_dir": str(tasks_dir),
        "state_file_count": len(state_files),
        "ndjson_event_count": len(ndjson_events),
        "manifest_path": str(manifest_path),
    }
    if ndjson_path:
        result["ndjson_path"] = str(ndjson_path)
    if installed_path:
        result["installed_to"] = installed_path

    return result
