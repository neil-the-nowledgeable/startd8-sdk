"""Unit tests for milestone_tracking (T1.2/T1.3 / FR-1/2/3/4/5)."""

import json
from pathlib import Path

from startd8.integrations.milestone_tracking import (
    build_milestone_tracking_inputs,
    emit_milestone_tracking,
)

SPEC = {
    "project": {
        "id": "startd8-benchmark",
        "name": "Benchmark",
        "sprint": "summer-2026",
        "created": "2026-06-08T00:00:00+00:00",
        "goals": ["measure models"],
    },
    "milestones": [
        {
            "id": "M0", "name": "Roster", "status": "done",
            "created": "2026-06-08T00:00:00+00:00", "completed": "2026-06-13T00:00:00+00:00",
            "depends_on": [],
            "work_items": [
                {"id": "M0-roster", "title": "Fable + roster", "status": "done",
                 "completed": "2026-06-13T00:00:00+00:00"},
            ],
        },
        {
            "id": "M5", "name": "Observability", "status": "todo",
            "depends_on": ["M0"],
            "work_items": [{"id": "M5-loki", "title": "Loki stream", "status": "todo"}],
        },
    ],
}


def test_build_inputs_hierarchy_and_statuses():
    inp = build_milestone_tracking_inputs(SPEC)
    # epic + 2 stories' worth of features, 2 tasks
    assert len(inp.plan.features) == 2
    assert len(inp.tasks) == 2
    assert inp.config.project_id == "startd8-benchmark"
    assert inp.config.sprint_id == "summer-2026"
    # epic rolls up to in_progress (some done, some todo)
    assert inp.initial_statuses["startd8-benchmark-epic"] == "in_progress"
    assert inp.initial_statuses["M0-story"] == "done"
    assert inp.initial_statuses["M5-story"] == "todo"
    assert inp.initial_statuses["M0-roster"] == "done"
    # completion + creation timestamps recorded for the done entities only
    assert inp.completion_timestamps["M0-story"] == "2026-06-13T00:00:00+00:00"
    assert "M5-story" not in inp.completion_timestamps
    assert inp.creation_timestamps["startd8-benchmark-epic"] == "2026-06-08T00:00:00+00:00"


def test_epic_all_done_rolls_up_done():
    spec = {"project": {"id": "p"}, "milestones": [
        {"id": "A", "status": "done", "completed": "2026-06-13T00:00:00+00:00", "work_items": []},
    ]}
    inp = build_milestone_tracking_inputs(spec)
    assert inp.initial_statuses["p-epic"] == "done"


def test_milestone_dependencies_threaded(tmp_path):
    """FR-5: M5 depends_on M0 → story carries the prerequisite story id."""
    emit_milestone_tracking(SPEC, tmp_path)
    m5 = json.loads((tmp_path / "contextcore-tasks" / "M5-story.json").read_text())
    assert m5["attributes"]["task.depends_on"] == ["M0-story"]


def test_emit_done_milestone_honest_backfill(tmp_path):
    """FR-3/R1-F7: done story has top-level OK + completion event at the real merge date."""
    emit_milestone_tracking(SPEC, tmp_path)
    m0 = json.loads((tmp_path / "contextcore-tasks" / "M0-story.json").read_text())
    assert m0["status"] == "OK"
    assert m0["end_time"] == "2026-06-13T00:00:00+00:00"
    assert m0["events"][0]["name"] == "task.created"
    assert m0["events"][0]["timestamp"] == "2026-06-08T00:00:00+00:00"  # created predates completion
    assert m0["events"][-1]["name"] == "task.completed"
    assert m0["start_time"] < m0["end_time"]


def test_real_benchmark_spec_emits(tmp_path):
    """The shipped milestones.yaml is valid and emits without error."""
    import yaml
    spec_path = (
        Path(__file__).resolve().parents[2]
        / "docs/design/benchmark-observability-tracking/milestones.yaml"
    )
    spec = yaml.safe_load(spec_path.read_text())
    result = emit_milestone_tracking(spec, tmp_path)
    assert result["counts"]["epics"] == 1
    assert result["counts"]["stories"] == len(spec["milestones"])
    assert result["counts"]["tasks"] >= len(spec["milestones"])
    # epic is in_progress (benchmark not fully done)
    epic = json.loads((tmp_path / "contextcore-tasks" / "startd8-benchmark-epic.json").read_text())
    assert epic["attributes"]["task.status"] == "in_progress"
