"""Unit tests for task_tracking_emitter initial_statuses + honest backfill (T1.1 / FR-3 / R1-F7)."""

import json
from pathlib import Path

from startd8.workflows.builtin.plan_ingestion_models import (
    ComplexityScore,
    ContractorRoute,
    ParsedFeature,
    ParsedPlan,
    TaskTrackingConfig,
)
from startd8.workflows.builtin.task_tracking_emitter import emit_task_tracking_artifacts


def _plan():
    feats = [
        ParsedFeature(
            feature_id="M0", name="Fable + roster", description="add fable",
            target_files=["src/x.py"], dependencies=[], estimated_loc=50, labels=["milestone"],
        ),
        ParsedFeature(
            feature_id="M5", name="Observability", description="loki stream",
            target_files=["src/y.py"], dependencies=["M0"], estimated_loc=80, labels=["milestone"],
        ),
    ]
    return ParsedPlan(
        title="Summer 2026 Benchmark", goals=["measure models"], features=feats,
        dependency_graph={"M5": ["M0"]}, mentioned_files=[],
    )


def _complexity():
    return ComplexityScore(
        composite=60, feature_count=2, cross_file_deps=10, api_surface=10,
        test_complexity=10, integration_depth=10, domain_novelty=10, ambiguity=10,
        reasoning="x", route=ContractorRoute.ARTISAN,
    )


def _tasks():
    return [
        {"task_id": "T-M0", "title": "Fable", "story_points": 1, "priority": "high",
         "labels": [], "depends_on": [], "config": {"task_description": "d",
         "context": {"feature_id": "M0", "target_files": ["src/x.py"], "estimated_loc": 50}}},
        {"task_id": "T-M5", "title": "Obs", "story_points": 1, "priority": "medium",
         "labels": [], "depends_on": ["T-M0"], "config": {"task_description": "d",
         "context": {"feature_id": "M5", "target_files": ["src/y.py"], "estimated_loc": 80}}},
    ]


def _load(tmp_path: Path, task_id: str) -> dict:
    return json.loads((tmp_path / "contextcore-tasks" / f"{task_id}.json").read_text())


def test_default_status_is_todo(tmp_path):
    """No overrides → prior behavior preserved (byte-for-byte status='todo', no end_time)."""
    emit_task_tracking_artifacts(_plan(), _complexity(), _tasks(),
                                 TaskTrackingConfig(project_id="startd8-benchmark"), tmp_path)
    epic = _load(tmp_path, "startd8-benchmark-epic")
    assert epic["attributes"]["task.status"] == "todo"
    assert epic["status"] == "UNSET"
    assert epic["end_time"] is None


def test_initial_statuses_applied(tmp_path):
    emit_task_tracking_artifacts(
        _plan(), _complexity(), _tasks(),
        TaskTrackingConfig(project_id="startd8-benchmark"), tmp_path,
        initial_statuses={"T-M0": "done", "T-M5": "in_progress"},
    )
    done = _load(tmp_path, "T-M0")
    wip = _load(tmp_path, "T-M5")
    assert done["attributes"]["task.status"] == "done"
    assert done["status"] == "OK"            # terminal → top-level OK (SpanState v2)
    assert wip["attributes"]["task.status"] == "in_progress"
    assert wip["status"] == "UNSET"


def test_honest_backfill_completion_event(tmp_path):
    """R1-F7: done task carries a completion event at the merge timestamp; created stays at 0."""
    created_ts = "2026-06-10T09:00:00+00:00"
    merge_ts = "2026-06-13T12:00:00+00:00"
    emit_task_tracking_artifacts(
        _plan(), _complexity(), _tasks(),
        TaskTrackingConfig(project_id="startd8-benchmark"), tmp_path,
        initial_statuses={"T-M0": "done"},
        completion_timestamps={"T-M0": merge_ts},
        creation_timestamps={"T-M0": created_ts},
    )
    done = _load(tmp_path, "T-M0")
    events = done["events"]
    assert events[0]["name"] == "task.created"
    assert events[0]["timestamp"] == created_ts                # real creation, not "now"
    assert events[0]["attributes"]["percent_complete"] == 0    # zero-point invariant preserved
    assert events[-1]["name"] == "task.completed"
    assert events[-1]["timestamp"] == merge_ts                 # real merge date, not now
    assert events[-1]["attributes"]["percent_complete"] == 100
    assert done["end_time"] == merge_ts
    assert done["start_time"] == created_ts
    # created strictly predates completion (honest burndown, R1-F7)
    assert done["start_time"] < done["end_time"]


def test_backfill_without_creation_ts_does_not_postdate_completion(tmp_path):
    """No creation override → created falls back to completion (never future 'now')."""
    merge_ts = "2026-06-13T12:00:00+00:00"
    emit_task_tracking_artifacts(
        _plan(), _complexity(), _tasks(),
        TaskTrackingConfig(project_id="startd8-benchmark"), tmp_path,
        initial_statuses={"T-M0": "done"},
        completion_timestamps={"T-M0": merge_ts},
    )
    done = _load(tmp_path, "T-M0")
    assert done["start_time"] == merge_ts          # falls back to completion, not future "now"
    assert done["start_time"] <= done["end_time"]  # never post-dates completion
