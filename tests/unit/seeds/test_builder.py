"""Tests for startd8.seeds.builder — SeedBuilder."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from startd8.seeds.builder import SeedBuilder


# ── Fake objects for builder inputs ──────────────────────────────────

@dataclass
class FakeParsedPlan:
    title: str = "Test Plan"
    goals: List[str] = field(default_factory=list)
    features: List[Any] = field(default_factory=list)
    dependency_graph: dict = field(default_factory=dict)
    mentioned_files: List[str] = field(default_factory=list)

    def to_seed_dict(self) -> Dict[str, Any]:
        return {"title": self.title, "goals": self.goals}


@dataclass
class FakeComplexity:
    overall: str = "medium"

    def to_seed_dict(self) -> Dict[str, Any]:
        return {"overall": self.overall}


@dataclass
class FakeFeature:
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


# ── Tests ────────────────────────────────────────────────────────────

class TestSeedBuilderInit:
    def test_fresh_builder_has_empty_state(self):
        b = SeedBuilder()
        assert b.tasks == []
        assert b.refine_suggestions == []


class TestSeedBuilderSetters:
    def test_set_plan(self):
        b = SeedBuilder()
        plan = FakeParsedPlan(title="My Plan", goals=["G1"])
        result = b.set_plan(plan)
        assert result is b  # fluent
        d = b.build()
        assert d["plan"]["title"] == "My Plan"
        assert d["plan"]["goals"] == ["G1"]

    def test_set_complexity(self):
        b = SeedBuilder()
        cx = FakeComplexity(overall="high")
        result = b.set_complexity(cx)
        assert result is b
        d = b.build()
        assert d["complexity"]["overall"] == "high"

    def test_set_route(self):
        b = SeedBuilder()
        result = b.set_route("artisan")
        assert result is b
        d = b.build()
        assert d["route"] == "artisan"

    def test_set_tasks(self):
        b = SeedBuilder()
        tasks = [{"task_id": "PI-001", "title": "T1", "config": {}}]
        result = b.set_tasks(tasks)
        assert result is b
        assert b.tasks == tasks
        # Verify it's a copy
        tasks.append({"task_id": "PI-002", "title": "T2", "config": {}})
        assert len(b.tasks) == 1

    def test_set_ingestion_metrics(self):
        b = SeedBuilder()
        result = b.set_ingestion_metrics({"parse": 0.05, "emit": 0.10})
        assert result is b
        d = b.build()
        assert d["ingestion_metrics"]["cost_parse"] == 0.05
        assert d["ingestion_metrics"]["cost_emit"] == 0.10
        assert d["ingestion_metrics"]["total_cost"] == pytest.approx(0.15)
        assert sorted(d["ingestion_metrics"]["_cost_phases_included"]) == [
            "emit", "parse"
        ]

    def test_set_ingestion_metrics_empty(self):
        b = SeedBuilder()
        b.set_ingestion_metrics()
        d = b.build()
        assert d["ingestion_metrics"]["total_cost"] == 0

    def test_set_wave_metadata(self):
        b = SeedBuilder()
        result = b.set_wave_metadata({"wave_count": 3})
        assert result is b
        d = b.build()
        assert d["wave_metadata"]["wave_count"] == 3

    def test_set_lane_assignments(self):
        b = SeedBuilder()
        result = b.set_lane_assignments({"PI-001": 0, "PI-002": 1})
        assert result is b
        d = b.build()
        assert d["lane_assignments"]["PI-001"] == 0

    def test_set_project_metadata(self):
        b = SeedBuilder()
        result = b.set_project_metadata({"criticality": "high"})
        assert result is b
        d = b.build()
        assert d["project_metadata"]["criticality"] == "high"

    def test_set_forward_manifest(self):
        b = SeedBuilder()
        manifest = {"contracts": [{"name": "C1"}]}
        result = b.set_forward_manifest(manifest)
        assert result is b
        d = b.build()
        assert d["forward_manifest"]["contracts"][0]["name"] == "C1"


class TestSeedBuilderDeriveTasks:
    def test_derive_tasks_from_features(self):
        b = SeedBuilder()
        features = [
            FakeFeature(
                feature_id="F1", name="Auth",
                target_files=["src/auth.py"],
            ),
        ]
        result = b.derive_tasks(features, {})
        assert result is b
        assert len(b.tasks) == 1
        assert b.tasks[0]["task_id"] == "PI-001"

    def test_derive_design_calibration(self):
        b = SeedBuilder()
        b.set_tasks([{
            "task_id": "T1",
            "config": {
                "task_description": "desc",
                "context": {"target_files": ["a.py"], "estimated_loc": 20},
            },
        }])
        result = b.derive_design_calibration()
        assert result is b
        d = b.build()
        assert "T1" in d["design_calibration"]
        assert d["design_calibration"]["T1"]["depth_tier"] == "brief"

    def test_derive_design_calibration_no_tasks(self):
        b = SeedBuilder()
        b.derive_design_calibration()
        d = b.build()
        assert "design_calibration" not in d

    def test_derive_architectural_context(self):
        b = SeedBuilder()
        plan = FakeParsedPlan(
            goals=["Build API"],
            features=[
                FakeFeature(
                    feature_id="F1", name="Auth",
                    target_files=["src/auth.py"],
                ),
            ],
            dependency_graph={},
        )
        result = b.derive_architectural_context(plan)
        assert result is b
        d = b.build()
        assert d["architectural_context"]["project_goals"] == ["Build API"]


class TestSeedBuilderArtifacts:
    def test_set_artifacts_doc_and_config(self):
        b = SeedBuilder()
        b.set_artifacts(
            doc_path=Path("/tmp/plan.md"),
            config_path=Path("/tmp/config.yaml"),
        )
        d = b.build()
        assert d["artifacts"]["plan_document_path"] == "/tmp/plan.md"
        assert d["artifacts"]["review_config_path"] == "/tmp/config.yaml"

    def test_set_artifacts_onboarding(self):
        b = SeedBuilder()
        onboarding = {
            "artifact_manifest_path": "/m.json",
            "source_checksum": "abc123",
        }
        b.set_artifacts(onboarding=onboarding)
        d = b.build()
        assert d["artifacts"]["artifact_manifest_path"] == "/m.json"
        assert d["onboarding"]["artifact_manifest_path"] == "/m.json"
        assert d["source_checksum"] == "abc123"

    def test_set_artifacts_review_output(self):
        b = SeedBuilder()
        review_output = {
            "triage": {
                "accepted": 3,
                "rejected": 1,
                "applied_suggestion_ids": ["s1"],
            }
        }
        b.set_artifacts(review_output=review_output)
        d = b.build()
        assert d["artifacts"]["refine_provenance"]["triage_accepted"] == 3
        assert d["artifacts"]["refine_provenance"]["applied_suggestion_ids"] == ["s1"]
        assert len(b.refine_suggestions) > 0

    def test_set_artifacts_stub_manifest(self):
        b = SeedBuilder()
        b.set_artifacts(stub_manifest=[{"file": "stub.py"}])
        d = b.build()
        assert d["artifacts"]["stub_manifest"] == [{"file": "stub.py"}]


class TestSeedBuilderContextFiles:
    def test_set_context_files(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("pass")
        b = SeedBuilder()
        result = b.set_context_files(["a.py"], base_dir=tmp_path)
        assert result is b
        d = b.build()
        assert len(d["context_files"]) == 1
        assert d["context_files"][0]["path"] == "a.py"
        assert d["context_files"][0]["checksum"] is not None

    def test_set_context_files_none(self):
        b = SeedBuilder()
        b.set_context_files(None)
        d = b.build()
        assert "context_files" not in d or d.get("context_files") == []


class TestSeedBuilderServiceMetadata:
    def test_set_service_metadata(self):
        features = [
            FakeFeature(
                feature_id="F1", name="API",
                target_files=["src/app.py"],
                protocol="http",
            ),
        ]
        b = SeedBuilder()
        result = b.set_service_metadata(features)
        assert result is b
        d = b.build()
        assert d["service_metadata"]["transport_protocol"] == "http"


class TestRewriteForwardManifestTaskIds:
    def test_rewrites_feature_ids_to_task_ids(self):
        b = SeedBuilder()
        b.set_tasks([
            {
                "task_id": "PI-001",
                "title": "Auth",
                "config": {"context": {"feature_id": "F1"}},
            },
            {
                "task_id": "PI-002",
                "title": "API",
                "config": {"context": {"feature_id": "F2"}},
            },
        ])
        b.set_forward_manifest({
            "contracts": [
                {"name": "C1", "applicable_task_ids": ["F1", "F2"]},
            ],
        })
        result = b.rewrite_forward_manifest_task_ids()
        assert result is b
        d = b.build()
        ids = d["forward_manifest"]["contracts"][0]["applicable_task_ids"]
        assert "PI-001" in ids
        assert "PI-002" in ids
        assert "F1" not in ids

    def test_preserves_unmapped_ids(self):
        b = SeedBuilder()
        b.set_tasks([{
            "task_id": "PI-001",
            "title": "T",
            "config": {"context": {"feature_id": "F1"}},
        }])
        b.set_forward_manifest({
            "contracts": [
                {"name": "C1", "applicable_task_ids": ["F1", "UNKNOWN"]},
            ],
        })
        b.rewrite_forward_manifest_task_ids()
        d = b.build()
        ids = d["forward_manifest"]["contracts"][0]["applicable_task_ids"]
        assert "PI-001" in ids
        assert "UNKNOWN" in ids

    def test_noop_without_manifest(self):
        b = SeedBuilder()
        b.set_tasks([{"task_id": "T1", "config": {"context": {"feature_id": "F1"}}}])
        result = b.rewrite_forward_manifest_task_ids()
        assert result is b  # fluent, no crash

    def test_noop_without_tasks(self):
        b = SeedBuilder()
        b.set_forward_manifest({"contracts": [{"name": "C1"}]})
        result = b.rewrite_forward_manifest_task_ids()
        assert result is b


class TestSeedBuilderValidate:
    def test_validate_warns_on_missing_calibration(self):
        """Unified validation warns on missing context fields regardless of route."""
        b = SeedBuilder()
        b.set_tasks([{
            "task_id": "PI-001",
            "title": "Test",
            "config": {"task_description": "d", "context": {"target_files": ["a.py"]}},
        }])
        warnings = b.validate(route="artisan")
        assert any("design_calibration" in w for w in warnings)
        assert any("architectural_context" in w for w in warnings)

    def test_validate_warns_on_missing_onboarding(self):
        """Unified validation warns on missing onboarding regardless of route."""
        b = SeedBuilder()
        b.set_tasks([{
            "task_id": "PI-001",
            "title": "Test",
            "config": {"task_description": "d", "context": {"target_files": ["a.py"]}},
        }])
        warnings = b.validate(route="prime")
        assert any("onboarding" in w for w in warnings)

    def test_validate_uses_builder_route(self):
        """Builder route is passed to validate_for_route; unified warnings appear."""
        b = SeedBuilder()
        b.set_route("artisan")
        b.set_tasks([{
            "task_id": "PI-001",
            "title": "Test",
            "config": {"task_description": "d", "context": {"target_files": ["a.py"]}},
        }])
        warnings = b.validate()
        assert any("design_calibration" in w for w in warnings)

    def test_validate_no_route_uses_base_schema(self):
        b = SeedBuilder()
        b.set_tasks([{
            "task_id": "PI-001",
            "title": "Test",
            "config": {"task_description": "d", "context": {"target_files": ["a.py"]}},
        }])
        warnings = b.validate()
        # Should still produce field coverage warnings
        assert any("architectural_context" in w for w in warnings)


class TestSeedBuilderBuild:
    def test_build_minimal(self):
        b = SeedBuilder()
        d = b.build()
        assert d["version"] == "1.0.0"
        assert d["schema_version"] == "1.0"
        assert d["generator"] == "plan-ingestion"
        assert d["tasks"] == []
        assert d["artifacts"] == {}
        assert "generated_at" in d

    def test_build_full(self):
        b = SeedBuilder()
        plan = FakeParsedPlan(title="Plan", goals=["G1"])
        cx = FakeComplexity(overall="low")
        b.set_plan(plan)
        b.set_complexity(cx)
        b.set_route("artisan")
        b.set_tasks([{
            "task_id": "PI-001",
            "title": "Task",
            "config": {
                "task_description": "desc",
                "context": {"target_files": ["a.py"], "estimated_loc": 50},
            },
        }])
        b.derive_design_calibration()
        b.set_project_metadata({"criticality": "low"})
        b.set_ingestion_metrics({"parse": 0.01})

        d = b.build()
        assert d["plan"]["title"] == "Plan"
        assert d["complexity"]["overall"] == "low"
        assert d["route"] == "artisan"
        assert len(d["tasks"]) == 1
        assert "PI-001" in d["design_calibration"]
        assert d["project_metadata"]["criticality"] == "low"
        assert d["ingestion_metrics"]["total_cost"] == pytest.approx(0.01)

    def test_build_omits_none_optional_fields(self):
        b = SeedBuilder()
        d = b.build()
        assert "architectural_context" not in d
        assert "design_calibration" not in d
        assert "onboarding" not in d
        assert "service_metadata" not in d
        assert "wave_metadata" not in d
        assert "lane_assignments" not in d
        assert "project_metadata" not in d
        assert "forward_manifest" not in d
        assert "route" not in d


class TestSeedBuilderWrite:
    def test_write_creates_file(self, tmp_path):
        b = SeedBuilder()
        b.set_tasks([{
            "task_id": "PI-001",
            "title": "T",
            "config": {"task_description": "d", "context": {"target_files": ["a.py"]}},
        }])
        out = tmp_path / "output" / "context-seed.json"
        result = b.write(out)
        assert result == out
        assert out.exists()

        import json
        with open(out) as f:
            data = json.load(f)
        assert data["version"] == "1.0.0"
        assert len(data["tasks"]) == 1

    def test_write_creates_parent_dirs(self, tmp_path):
        b = SeedBuilder()
        out = tmp_path / "deep" / "nested" / "context-seed.json"
        b.write(out)
        assert out.exists()


class TestSeedBuilderFluent:
    """Verify the full fluent chain works end-to-end."""

    def test_fluent_chain(self, tmp_path):
        features = [
            FakeFeature(
                feature_id="F1", name="Auth",
                target_files=["src/auth.py"],
            ),
        ]
        plan = FakeParsedPlan(
            title="Plan", goals=["Build"],
            features=features,
        )

        f = tmp_path / "src" / "auth.py"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("# auth module")

        b = (
            SeedBuilder()
            .set_plan(plan)
            .set_complexity(FakeComplexity())
            .set_route("artisan")
            .derive_tasks(features, {})
            .derive_architectural_context(plan)
            .derive_design_calibration()
            .set_service_metadata(features)
            .set_context_files(["src/auth.py"], base_dir=tmp_path)
            .set_project_metadata({"criticality": "low"})
            .set_ingestion_metrics({"parse": 0.01, "emit": 0.02})
        )

        d = b.build()
        assert d["version"] == "1.0.0"
        assert d["route"] == "artisan"
        assert len(d["tasks"]) >= 1
        assert "architectural_context" in d
        assert "design_calibration" in d
        assert d["ingestion_metrics"]["total_cost"] == pytest.approx(0.03)
