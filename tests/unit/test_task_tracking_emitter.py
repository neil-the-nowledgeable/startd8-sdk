"""Unit tests for task_tracking_emitter module."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from startd8.workflows.builtin.plan_ingestion_models import (
    ComplexityScore,
    ContractorRoute,
    ParsedFeature,
    ParsedPlan,
    TaskTrackingConfig,
)
from startd8.workflows.builtin.task_tracking_emitter import emit_task_tracking_artifacts


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_features(count: int = 3) -> list:
    features = []
    for i in range(1, count + 1):
        features.append(ParsedFeature(
            feature_id=f"F-{i:03d}",
            name=f"Feature {i}",
            description=f"Description for feature {i}",
            target_files=[f"src/mod{i}.py"],
            dependencies=[f"F-{i - 1:03d}"] if i > 1 else [],
            estimated_loc=100 * i,
            labels=["core"],
        ))
    return features


def _make_parsed_plan(features=None) -> ParsedPlan:
    if features is None:
        features = _make_features()
    dep_graph = {}
    for f in features:
        if f.dependencies:
            dep_graph[f.feature_id] = f.dependencies
    return ParsedPlan(
        title="Test Plan Alpha",
        goals=["Build the system", "Ship it"],
        features=features,
        dependency_graph=dep_graph,
        mentioned_files=["src/main.py"],
    )


def _make_complexity() -> ComplexityScore:
    return ComplexityScore(
        composite=65,
        feature_count=60,
        cross_file_deps=50,
        api_surface=40,
        test_complexity=55,
        integration_depth=70,
        domain_novelty=30,
        ambiguity=20,
        reasoning="Moderately complex plan",
        route=ContractorRoute.ARTISAN,
    )


def _make_tasks(features=None) -> list:
    """Create derived tasks matching _derive_tasks_from_features output."""
    if features is None:
        features = _make_features()
    tasks = []
    for idx, f in enumerate(features, start=1):
        deps = []
        for dep_fid in f.dependencies:
            # Find index of the dependency feature
            for j, other in enumerate(features, start=1):
                if other.feature_id == dep_fid:
                    deps.append(f"PI-{j:03d}")
        tasks.append({
            "task_id": f"PI-{idx:03d}",
            "title": f.name,
            "task_type": "task",
            "story_points": 3,
            "priority": "high" if idx == 1 else "medium",
            "labels": list(f.labels),
            "depends_on": deps,
            "config": {
                "task_description": f.description,
                "context": {
                    "feature_id": f.feature_id,
                    "target_files": list(f.target_files),
                    "estimated_loc": f.estimated_loc,
                },
            },
        })
    return tasks


def _run_emitter(tmp_path, **config_overrides):
    """Helper to run emitter with defaults."""
    plan = _make_parsed_plan()
    complexity = _make_complexity()
    tasks = _make_tasks()
    config = TaskTrackingConfig(**config_overrides)
    result = emit_task_tracking_artifacts(plan, complexity, tasks, config, tmp_path)
    return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHierarchyStructure:
    """Epic + stories + tasks created, parent_span_id links correct."""

    def test_epic_story_task_counts(self, tmp_path):
        result = _run_emitter(tmp_path)
        tasks_dir = tmp_path / "contextcore-tasks"

        # 1 epic + 3 stories + 3 tasks = 7
        json_files = [f for f in tasks_dir.glob("*.json") if f.name != "tracking-manifest.json"]
        assert len(json_files) == 7

    def test_epic_has_no_parent(self, tmp_path):
        _run_emitter(tmp_path)
        tasks_dir = tmp_path / "contextcore-tasks"
        epic_file = tasks_dir / "test-plan-alpha-epic.json"
        assert epic_file.exists()
        data = json.loads(epic_file.read_text())
        assert data["parent_span_id"] is None
        assert data["attributes"]["task.type"] == "epic"

    def test_stories_parent_to_epic(self, tmp_path):
        _run_emitter(tmp_path)
        tasks_dir = tmp_path / "contextcore-tasks"
        epic_data = json.loads((tasks_dir / "test-plan-alpha-epic.json").read_text())
        epic_span = epic_data["span_id"]

        for fid in ["F-001", "F-002", "F-003"]:
            story_data = json.loads((tasks_dir / f"{fid}-story.json").read_text())
            assert story_data["parent_span_id"] == epic_span
            assert story_data["attributes"]["task.type"] == "story"

    def test_tasks_parent_to_stories(self, tmp_path):
        _run_emitter(tmp_path)
        tasks_dir = tmp_path / "contextcore-tasks"

        # Build story span_id map
        story_spans = {}
        for fid in ["F-001", "F-002", "F-003"]:
            story_data = json.loads((tasks_dir / f"{fid}-story.json").read_text())
            story_spans[fid] = story_data["span_id"]

        # Each task should point to its feature's story
        for idx, fid in enumerate(["F-001", "F-002", "F-003"], start=1):
            task_data = json.loads((tasks_dir / f"PI-{idx:03d}.json").read_text())
            assert task_data["parent_span_id"] == story_spans[fid]
            assert task_data["attributes"]["task.type"] == "task"


class TestZeroPointEvents:
    """Every state file has task.created with percent_complete: 0."""

    def test_all_files_have_created_event(self, tmp_path):
        _run_emitter(tmp_path)
        tasks_dir = tmp_path / "contextcore-tasks"

        for f in tasks_dir.glob("*.json"):
            if f.name == "tracking-manifest.json":
                continue
            data = json.loads(f.read_text())
            events = data.get("events", [])
            assert len(events) >= 1, f"{f.name} has no events"
            assert events[0]["name"] == "task.created"
            assert events[0]["attributes"]["percent_complete"] == 0


class TestSchemaV2Keys:
    """Required keys present in state files."""

    REQUIRED_TOP_KEYS = {
        "task_id", "span_name", "trace_id", "span_id", "parent_span_id",
        "start_time", "end_time", "attributes", "events", "schema_version",
        "project_id",
    }
    REQUIRED_ATTR_KEYS = {
        "task.id", "task.title", "task.type", "task.status", "task.priority",
        "task.story_points", "task.prompt", "task.depends_on", "task.labels",
        "task.feature_id", "task.target_files", "task.estimated_loc",
        "project.id", "sprint.id",
    }

    def test_state_file_keys(self, tmp_path):
        _run_emitter(tmp_path)
        tasks_dir = tmp_path / "contextcore-tasks"

        for f in tasks_dir.glob("*.json"):
            if f.name == "tracking-manifest.json":
                continue
            data = json.loads(f.read_text())
            assert self.REQUIRED_TOP_KEYS.issubset(data.keys()), (
                f"{f.name} missing keys: {self.REQUIRED_TOP_KEYS - data.keys()}"
            )
            assert data["schema_version"] == 2
            attrs = data["attributes"]
            assert self.REQUIRED_ATTR_KEYS.issubset(attrs.keys()), (
                f"{f.name} missing attrs: {self.REQUIRED_ATTR_KEYS - attrs.keys()}"
            )


class TestContextCoreSourceCompatible:
    """Files loadable by ContextCoreTaskSource._load_task_from_file()."""

    def test_files_have_attributes_dict(self, tmp_path):
        _run_emitter(tmp_path)
        tasks_dir = tmp_path / "contextcore-tasks"

        for f in tasks_dir.glob("*.json"):
            if f.name == "tracking-manifest.json":
                continue
            data = json.loads(f.read_text())
            attrs = data["attributes"]
            # ContextCoreTaskSource expects these to resolve a WorkflowTaskSpec
            assert isinstance(attrs.get("task.id"), str)
            assert isinstance(attrs.get("task.title"), str)
            assert isinstance(attrs.get("task.depends_on"), list)

    def test_task_ids_match_filenames(self, tmp_path):
        _run_emitter(tmp_path)
        tasks_dir = tmp_path / "contextcore-tasks"

        for f in tasks_dir.glob("*.json"):
            if f.name == "tracking-manifest.json":
                continue
            data = json.loads(f.read_text())
            expected_stem = data["task_id"]
            assert f.stem == expected_stem, f"Filename {f.name} doesn't match task_id {expected_stem}"


class TestNdjsonFormat:
    """Each line valid JSON with progress tracker fields."""

    REQUIRED_FIELDS = {
        "timestamp", "trace_id", "span_id", "parent_span_id", "project",
        "event", "task_id", "task_type", "status", "percent_complete", "message",
    }

    def test_ndjson_lines_valid(self, tmp_path):
        _run_emitter(tmp_path)
        ndjson_path = tmp_path / "contextcore-tasks" / "task-events.ndjson"
        assert ndjson_path.exists()

        lines = ndjson_path.read_text().strip().split("\n")
        # 1 epic + 3 stories + 3 tasks = 7 lines
        assert len(lines) == 7

        for line in lines:
            data = json.loads(line)
            assert self.REQUIRED_FIELDS.issubset(data.keys()), (
                f"Missing fields: {self.REQUIRED_FIELDS - data.keys()}"
            )
            assert data["event"] == "task.created"
            assert data["percent_complete"] == 0

    def test_no_ndjson_when_disabled(self, tmp_path):
        _run_emitter(tmp_path, emit_ndjson_events=False)
        ndjson_path = tmp_path / "contextcore-tasks" / "task-events.ndjson"
        assert not ndjson_path.exists()


class TestTraceIdShared:
    """All state files share the same trace_id."""

    def test_single_trace_id(self, tmp_path):
        _run_emitter(tmp_path)
        tasks_dir = tmp_path / "contextcore-tasks"

        trace_ids = set()
        for f in tasks_dir.glob("*.json"):
            if f.name == "tracking-manifest.json":
                continue
            data = json.loads(f.read_text())
            trace_ids.add(data["trace_id"])

        assert len(trace_ids) == 1, f"Expected 1 trace_id, got {len(trace_ids)}: {trace_ids}"

    def test_trace_id_in_manifest(self, tmp_path):
        _run_emitter(tmp_path)
        tasks_dir = tmp_path / "contextcore-tasks"
        manifest = json.loads((tasks_dir / "tracking-manifest.json").read_text())
        assert "trace_id" in manifest
        assert len(manifest["trace_id"]) == 32  # uuid4 hex


class TestDependencyPreserved:
    """task.depends_on matches input."""

    def test_dependency_preserved(self, tmp_path):
        _run_emitter(tmp_path)
        tasks_dir = tmp_path / "contextcore-tasks"

        # PI-001 has no deps, PI-002 depends on PI-001, PI-003 depends on PI-002
        task1 = json.loads((tasks_dir / "PI-001.json").read_text())
        assert task1["attributes"]["task.depends_on"] == []

        task2 = json.loads((tasks_dir / "PI-002.json").read_text())
        assert "PI-001" in task2["attributes"]["task.depends_on"]

        task3 = json.loads((tasks_dir / "PI-003.json").read_text())
        assert "PI-002" in task3["attributes"]["task.depends_on"]


class TestInstallToContextCore:
    """Files written to mocked home dir when flag set."""

    def test_install_creates_files(self, tmp_path):
        fake_home = tmp_path / "fakehome"
        fake_home.mkdir()

        with patch("startd8.workflows.builtin.task_tracking_emitter.Path.home", return_value=fake_home):
            result = _run_emitter(
                tmp_path,
                project_id="test-project",
                install_to_contextcore=True,
            )

        cc_dir = fake_home / ".contextcore" / "state" / "test-project"
        assert cc_dir.exists()
        installed_files = list(cc_dir.glob("*.json"))
        # 1 epic + 3 stories + 3 tasks = 7
        assert len(installed_files) == 7
        assert result.get("installed_to") == str(cc_dir)

    def test_no_install_by_default(self, tmp_path):
        result = _run_emitter(tmp_path)
        assert "installed_to" not in result


class TestManifest:
    """Manifest contains expected summary data."""

    def test_manifest_counts(self, tmp_path):
        result = _run_emitter(tmp_path)
        tasks_dir = tmp_path / "contextcore-tasks"
        manifest = json.loads((tasks_dir / "tracking-manifest.json").read_text())

        assert manifest["counts"]["epics"] == 1
        assert manifest["counts"]["stories"] == 3
        assert manifest["counts"]["tasks"] == 3
        assert manifest["counts"]["total"] == 7
        assert manifest["complexity_score"] == 65

    def test_project_id_from_config(self, tmp_path):
        _run_emitter(tmp_path, project_id="my-custom-project")
        tasks_dir = tmp_path / "contextcore-tasks"
        manifest = json.loads((tasks_dir / "tracking-manifest.json").read_text())
        assert manifest["project_id"] == "my-custom-project"

    def test_project_id_from_title(self, tmp_path):
        result = _run_emitter(tmp_path)
        assert result["project_id"] == "test-plan-alpha"
