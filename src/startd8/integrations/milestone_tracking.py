# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Project delivery tracking from a hand-authored milestone spec (T1.2 / FR-1/2/3/4/5).

Turns a simple ``{project, milestones[]}`` spec into ContextCore SpanState v2 task artifacts via
:func:`startd8.workflows.builtin.task_tracking_emitter.emit_task_tracking_artifacts` — an
epic→story→task hierarchy with honest backfilled statuses/timestamps and milestone dependencies.

This is the **delivery** half of benchmark observability tracking (Business Observability, Section A):
it models the M0–M7 build milestones as a ContextCore project so a burndown/velocity dashboard can be
derived — no plan-ingestion or LLM required. Generic over any milestone spec, not benchmark-specific.

Spec shape (YAML/JSON)::

    project: {id, name, sprint, goals: [...], created: <iso>}
    milestones:
      - id: M0
        name: "..."
        status: done|in_progress|todo|in_review|blocked|cancelled
        created: <iso>            # optional
        completed: <iso>          # required-ish for done/cancelled (honest burndown)
        depends_on: [M-...]       # milestone ids
        work_items:
          - {id, title, status, created?, completed?, depends_on?: [...]}
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from ..workflows.builtin.plan_ingestion_models import (
    ComplexityScore,
    ContractorRoute,
    ParsedFeature,
    ParsedPlan,
    TaskTrackingConfig,
)
from ..workflows.builtin.task_tracking_emitter import emit_task_tracking_artifacts
from ..logging_config import get_logger

logger = get_logger(__name__)

_TERMINAL = {"done", "cancelled"}
_ACTIVE = {"in_progress", "in_review", "blocked"}


def _epic_status(milestone_statuses: List[str]) -> str:
    """Roll milestone statuses up to the epic: all-done → done; any active/done → in_progress; else todo."""
    if milestone_statuses and all(s == "done" for s in milestone_statuses):
        return "done"
    if any(s in _ACTIVE or s in _TERMINAL for s in milestone_statuses):
        return "in_progress"
    return "todo"


@dataclass
class MilestoneTrackingInputs:
    """Everything ``emit_task_tracking_artifacts`` needs, derived from a milestone spec."""

    plan: ParsedPlan
    complexity: ComplexityScore
    tasks: List[Dict[str, Any]]
    config: TaskTrackingConfig
    initial_statuses: Dict[str, str]
    completion_timestamps: Dict[str, str]
    creation_timestamps: Dict[str, str]


def build_milestone_tracking_inputs(spec: Dict[str, Any]) -> MilestoneTrackingInputs:
    """Project a milestone spec dict into emitter inputs (pure; no I/O)."""
    project = spec.get("project", {})
    project_id = project.get("id", "project")
    milestones = spec.get("milestones", [])

    epic_id = f"{project_id}-epic"
    initial_statuses: Dict[str, str] = {}
    completion_timestamps: Dict[str, str] = {}
    creation_timestamps: Dict[str, str] = {}

    features: List[ParsedFeature] = []
    tasks: List[Dict[str, Any]] = []
    dependency_graph: Dict[str, List[str]] = {}

    def _record(entity_id: str, status: str, created: Any, completed: Any) -> None:
        initial_statuses[entity_id] = status
        if created:
            creation_timestamps[entity_id] = created
        if status in _TERMINAL and completed:
            completion_timestamps[entity_id] = completed

    for m in milestones:
        mid = m["id"]
        story_id = f"{mid}-story"
        m_status = m.get("status", "todo")
        # Story deps reference the prerequisite milestone's story task id.
        story_deps = [f"{d}-story" for d in m.get("depends_on", [])]
        if story_deps:
            dependency_graph[story_id] = story_deps

        features.append(
            ParsedFeature(
                feature_id=mid,
                name=m.get("name", mid),
                description=m.get("description", m.get("name", mid)),
                target_files=[],
                dependencies=story_deps,
                estimated_loc=0,
                labels=["milestone", m_status],
            )
        )
        _record(story_id, m_status, m.get("created"), m.get("completed"))

        for wi in m.get("work_items", []):
            wid = wi["id"]
            wi_status = wi.get("status", m_status)
            tasks.append(
                {
                    "task_id": wid,
                    "title": wi.get("title", wid),
                    "story_points": wi.get("story_points", 1),
                    "priority": wi.get("priority", "medium"),
                    "labels": wi.get("labels", []),
                    "depends_on": wi.get("depends_on", []),
                    "config": {
                        "task_description": wi.get("title", wid),
                        "context": {"feature_id": mid, "target_files": [], "estimated_loc": 0},
                    },
                }
            )
            _record(wid, wi_status, wi.get("created"), wi.get("completed"))

    initial_statuses[epic_id] = _epic_status([m.get("status", "todo") for m in milestones])
    if project.get("created"):
        creation_timestamps[epic_id] = project["created"]

    plan = ParsedPlan(
        title=project.get("name", project_id),
        goals=project.get("goals", []),
        features=features,
        dependency_graph=dependency_graph,
        mentioned_files=[],
    )
    complexity = ComplexityScore(
        composite=len(milestones),
        feature_count=len(milestones),
        cross_file_deps=0,
        api_surface=0,
        test_complexity=0,
        integration_depth=0,
        domain_novelty=0,
        ambiguity=0,
        reasoning="Delivery-tracking spec (not a code-complexity assessment).",
        route=ContractorRoute.ARTISAN,
    )
    config = TaskTrackingConfig(
        project_id=project_id,
        project_name=project.get("name", project_id),
        sprint_id=project.get("sprint"),
        install_to_contextcore=False,
        emit_ndjson_events=True,
    )
    return MilestoneTrackingInputs(
        plan=plan,
        complexity=complexity,
        tasks=tasks,
        config=config,
        initial_statuses=initial_statuses,
        completion_timestamps=completion_timestamps,
        creation_timestamps=creation_timestamps,
    )


def emit_milestone_tracking(
    spec: Dict[str, Any], output_dir: Path, *, install: bool = False
) -> Dict[str, Any]:
    """Build inputs from ``spec`` and emit the SpanState artifacts under ``output_dir``."""
    inp = build_milestone_tracking_inputs(spec)
    inp.config.install_to_contextcore = install
    result = emit_task_tracking_artifacts(
        inp.plan,
        inp.complexity,
        inp.tasks,
        inp.config,
        output_dir,
        initial_statuses=inp.initial_statuses,
        completion_timestamps=inp.completion_timestamps,
        creation_timestamps=inp.creation_timestamps,
    )
    # Augment the emitter's summary with explicit per-type counts (the emitter returns
    # state_file_count/tasks_dir; counts live in the on-disk manifest).
    result["counts"] = {
        "epics": 1,
        "stories": len(spec.get("milestones", [])),
        "tasks": len(inp.tasks),
        "total": result.get("state_file_count"),
    }
    logger.info(
        "Emitted milestone tracking for project=%s (%d milestones) → %s",
        inp.config.project_id,
        len(spec.get("milestones", [])),
        result.get("tasks_dir"),
    )
    return result
