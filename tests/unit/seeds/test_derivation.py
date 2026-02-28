"""Tests for startd8.seeds.derivation."""

from dataclasses import dataclass, field
from typing import List

from startd8.seeds.derivation import (
    DEPTH_TIERS,
    derive_architectural_context,
    derive_design_calibration,
    derive_tasks_from_features,
    estimate_story_points,
    extract_refine_suggestions_for_seed,
    filter_trivial_test_init_tasks,
    infer_artifact_types_from_files,
    infer_service_metadata,
    is_trivial_test_init,
    split_oversized_tasks,
)


@dataclass
class FakeFeature:
    """Minimal ParsedFeature-like object for testing."""
    feature_id: str
    name: str
    description: str = ""
    target_files: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    estimated_loc: int = 50
    labels: List[str] = field(default_factory=list)
    design_doc_sections: List[str] = field(default_factory=list)
    artifact_types_addressed: List[str] = field(default_factory=list)
    api_signatures: List[str] = field(default_factory=list)
    protocol: str = ""
    runtime_dependencies: List[str] = field(default_factory=list)
    negative_scope: List[str] = field(default_factory=list)
    affected_callers: List[str] = field(default_factory=list)
    high_impact: bool = False
    targets_dead_code: bool = False


@dataclass
class FakeParsedPlan:
    """Minimal ParsedPlan-like object for testing."""
    title: str = "Test Plan"
    goals: List[str] = field(default_factory=list)
    features: List[FakeFeature] = field(default_factory=list)
    dependency_graph: dict = field(default_factory=dict)
    mentioned_files: List[str] = field(default_factory=list)


class TestEstimateStoryPoints:
    def test_tiny(self):
        assert estimate_story_points(10) == 1

    def test_small(self):
        assert estimate_story_points(30) == 2

    def test_medium(self):
        assert estimate_story_points(80) == 3

    def test_large(self):
        assert estimate_story_points(150) == 5

    def test_xlarge(self):
        assert estimate_story_points(300) == 8

    def test_boundary_20(self):
        assert estimate_story_points(20) == 1

    def test_boundary_21(self):
        assert estimate_story_points(21) == 2


class TestIsTrivialTestInit:
    def test_test_init(self):
        assert is_trivial_test_init("tests/__init__.py") is True

    def test_nested_test_init(self):
        assert is_trivial_test_init("tests/unit/__init__.py") is True

    def test_source_init(self):
        assert is_trivial_test_init("src/mypackage/__init__.py") is False

    def test_non_init(self):
        assert is_trivial_test_init("tests/test_foo.py") is False

    def test_windows_path(self):
        assert is_trivial_test_init("tests\\unit\\__init__.py") is True


class TestExtractRefineSuggestions:
    def test_no_triage(self):
        assert extract_refine_suggestions_for_seed({}) == []

    def test_empty_triage(self):
        assert extract_refine_suggestions_for_seed({"triage": {}}) == []

    def test_summary_fallback(self):
        result = extract_refine_suggestions_for_seed({
            "triage": {"accepted": 3, "rejected": 1}
        })
        assert len(result) == 1
        assert result[0]["source"] == "triage_summary"
        assert result[0]["triage_accepted_count"] == 3

    def test_decisions_filtered(self):
        result = extract_refine_suggestions_for_seed({
            "triage": {
                "decisions": [
                    {"id": "1", "decision": "ACCEPT", "area": "security"},
                    {"id": "2", "decision": "REJECT", "area": "perf"},
                ]
            }
        })
        assert len(result) == 1
        assert result[0]["id"] == "1"
        assert result[0]["decision"] == "ACCEPT"


class TestInferArtifactTypes:
    def test_python_files(self):
        types = infer_artifact_types_from_files(["src/foo.py", "src/bar.py"])
        assert "source_module" in types

    def test_dockerfile(self):
        types = infer_artifact_types_from_files(["Dockerfile"])
        assert "dockerfile" in types

    def test_proto(self):
        types = infer_artifact_types_from_files(["api/service.proto"])
        assert "proto_contract" in types

    def test_dependency_manifest(self):
        types = infer_artifact_types_from_files(["pyproject.toml"])
        assert "dependency_manifest" in types

    def test_deduplication(self):
        types = infer_artifact_types_from_files(["a.py", "b.py"])
        assert types.count("source_module") == 1


class TestDeriveTasksFromFeatures:
    def test_basic_derivation(self):
        features = [
            FakeFeature(feature_id="F1", name="Auth", target_files=["src/auth.py"]),
            FakeFeature(feature_id="F2", name="DB", target_files=["src/db.py"]),
        ]
        tasks = derive_tasks_from_features(features, {})
        assert len(tasks) == 2
        assert tasks[0]["task_id"] == "PI-001"
        assert tasks[1]["task_id"] == "PI-002"

    def test_dependency_resolution(self):
        features = [
            FakeFeature(feature_id="F1", name="Auth", target_files=["src/auth.py"]),
            FakeFeature(feature_id="F2", name="API", target_files=["src/api.py"],
                       dependencies=["F1"]),
        ]
        tasks = derive_tasks_from_features(features, {"F2": ["F1"]})
        api_task = next(t for t in tasks if t["title"] == "API")
        assert "PI-001" in api_task["depends_on"]

    def test_priority_from_dependents(self):
        features = [
            FakeFeature(feature_id="F1", name="Core", target_files=["src/core.py"]),
            FakeFeature(feature_id="F2", name="A", target_files=["src/a.py"],
                       dependencies=["F1"]),
            FakeFeature(feature_id="F3", name="B", target_files=["src/b.py"],
                       dependencies=["F1"]),
        ]
        tasks = derive_tasks_from_features(features, {})
        core_task = next(t for t in tasks if t["title"] == "Core")
        assert core_task["priority"] == "high"

    def test_trivial_test_init_filtered(self):
        features = [
            FakeFeature(feature_id="F1", name="Init",
                       target_files=["tests/__init__.py"]),
        ]
        tasks = derive_tasks_from_features(features, {})
        assert len(tasks) == 0

    def test_multi_file_split(self):
        features = [
            FakeFeature(feature_id="F1", name="Multi",
                       target_files=["src/a.py", "src/b.py"],
                       estimated_loc=100),
        ]
        tasks = derive_tasks_from_features(features, {})
        assert len(tasks) == 2
        assert tasks[0]["task_id"].startswith("PI-001")
        assert tasks[1]["task_id"].startswith("PI-001")


class TestSplitOversizedTasks:
    def test_single_file_passthrough(self):
        tasks = [{"task_id": "T1", "config": {"context": {"target_files": ["a.py"]}}}]
        result = split_oversized_tasks(tasks, max_files=1)
        assert len(result) == 1
        assert result[0]["task_id"] == "T1"

    def test_multi_file_split(self):
        tasks = [{
            "task_id": "T1",
            "title": "Multi",
            "depends_on": [],
            "config": {
                "task_description": "desc",
                "context": {
                    "feature_id": "F1",
                    "target_files": ["a.py", "b.py"],
                    "estimated_loc": 100,
                },
            },
        }]
        result = split_oversized_tasks(tasks, max_files=1)
        assert len(result) == 2
        assert result[0]["task_id"] == "T1a"
        assert result[1]["task_id"] == "T1b"


class TestFilterTrivialTestInitTasks:
    def test_filters_test_init(self):
        tasks = [
            {"task_id": "T1", "depends_on": [],
             "config": {"context": {"target_files": ["tests/__init__.py"]}}},
            {"task_id": "T2", "depends_on": ["T1"],
             "config": {"context": {"target_files": ["tests/test_foo.py"]}}},
        ]
        result = filter_trivial_test_init_tasks(tasks)
        assert len(result) == 1
        assert result[0]["task_id"] == "T2"
        assert "T1" not in result[0]["depends_on"]


class TestDeriveArchitecturalContext:
    def test_basic_context(self):
        plan = FakeParsedPlan(
            goals=["Build a REST API"],
            features=[
                FakeFeature(feature_id="F1", name="Auth",
                           target_files=["src/auth.py"]),
                FakeFeature(feature_id="F2", name="API",
                           target_files=["src/api.py", "src/auth.py"]),
            ],
            dependency_graph={"F2": ["F1"]},
        )
        ctx = derive_architectural_context(plan, {})
        assert ctx["project_goals"] == ["Build a REST API"]
        # auth.py is shared by both features
        shared = ctx["shared_modules"]
        assert any(m["path"] == "src/auth.py" for m in shared)


class TestDeriveDesignCalibration:
    def test_low_complexity(self):
        tasks = [{
            "task_id": "T1",
            "config": {
                "task_description": "Small task",
                "context": {"target_files": ["a.py"], "estimated_loc": 20},
            },
        }]
        cal = derive_design_calibration(tasks)
        assert cal["T1"]["depth_tier"] == "brief"
        assert cal["T1"]["complexity"] == "low"

    def test_high_complexity(self):
        tasks = [{
            "task_id": "T1",
            "config": {
                "task_description": "Big task",
                "context": {"target_files": ["a.py"], "estimated_loc": 200},
            },
        }]
        cal = derive_design_calibration(tasks)
        assert cal["T1"]["depth_tier"] == "comprehensive"
        assert cal["T1"]["complexity"] == "high"

    def test_domain_token_adjustment_config(self):
        tasks = [{
            "task_id": "T1",
            "config": {
                "task_description": "Config task",
                "context": {"target_files": ["config.toml"], "estimated_loc": 100},
            },
        }]
        cal = derive_design_calibration(tasks)
        # config files get 0.5x multiplier on implement tokens
        assert cal["T1"]["implement_max_output_tokens"] < 32768


class TestDepthTiers:
    def test_all_tiers_present(self):
        assert "brief" in DEPTH_TIERS
        assert "standard" in DEPTH_TIERS
        assert "comprehensive" in DEPTH_TIERS

    def test_tiers_have_required_keys(self):
        for name, tier in DEPTH_TIERS.items():
            assert "sections" in tier, f"{name} missing sections"
            assert "max_tokens" in tier, f"{name} missing max_tokens"
            assert "guidance" in tier, f"{name} missing guidance"


class TestInferServiceMetadata:
    def test_empty_features(self):
        metadata = infer_service_metadata([])
        assert metadata == {}

    def test_protocol_from_features(self):
        features = [
            FakeFeature(feature_id="F1", name="API", protocol="http"),
        ]
        metadata = infer_service_metadata(features)
        assert metadata["transport_protocol"] == "http"

    def test_language_from_files(self):
        features = [
            FakeFeature(feature_id="F1", name="Mod",
                       target_files=["src/mod.py"]),
        ]
        metadata = infer_service_metadata(features)
        assert metadata["primary_language"] == "python"
