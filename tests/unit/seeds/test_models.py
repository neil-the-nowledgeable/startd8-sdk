"""Tests for startd8.seeds.models — ContextSeed + SeedTask."""

import pytest

from startd8.seeds.models import ContextSeed, SeedTask


class TestContextSeed:
    """ContextSeed dataclass tests."""

    def test_default_fields(self):
        seed = ContextSeed()
        assert seed.version == "1.0.0"
        assert seed.schema_version == "1.0"
        assert seed.generator == "plan-ingestion"
        assert seed.tasks == []
        assert seed.artifacts == {}
        assert seed.route is None

    def test_to_dict_minimal(self):
        seed = ContextSeed(generated_at="2026-01-01T00:00:00+00:00")
        d = seed.to_dict()
        assert d["version"] == "1.0.0"
        assert d["schema_version"] == "1.0"
        assert d["generated_at"] == "2026-01-01T00:00:00+00:00"
        assert d["tasks"] == []
        assert d["artifacts"] == {}
        assert d["ingestion_metrics"] == {}
        # Optional fields should NOT appear when None
        assert "architectural_context" not in d
        assert "design_calibration" not in d
        assert "onboarding" not in d
        assert "context_files" not in d
        assert "service_metadata" not in d
        assert "wave_metadata" not in d
        assert "lane_assignments" not in d
        assert "project_metadata" not in d
        assert "forward_manifest" not in d
        assert "route" not in d

    def test_to_dict_with_optional_fields(self):
        seed = ContextSeed(
            architectural_context={"project_goals": ["goal1"]},
            design_calibration={"PI-001": {"depth_tier": "brief"}},
            onboarding={"artifact_manifest_path": "/path"},
            context_files=[{"path": "f.py", "checksum": "abc"}],
            service_metadata={"transport_protocol": "http"},
            wave_metadata={"wave_count": 2},
            lane_assignments={"PI-001": 0},
            project_metadata={"criticality": "medium"},
            forward_manifest={"contracts": []},
            route="artisan",
        )
        d = seed.to_dict()
        assert d["architectural_context"]["project_goals"] == ["goal1"]
        assert d["design_calibration"]["PI-001"]["depth_tier"] == "brief"
        assert d["onboarding"]["artifact_manifest_path"] == "/path"
        assert len(d["context_files"]) == 1
        assert d["service_metadata"]["transport_protocol"] == "http"
        assert d["wave_metadata"]["wave_count"] == 2
        assert d["lane_assignments"]["PI-001"] == 0
        assert d["project_metadata"]["criticality"] == "medium"
        assert d["forward_manifest"]["contracts"] == []
        assert d["route"] == "artisan"

    def test_to_dict_roundtrip(self):
        """to_dict output can be used to reconstruct key fields."""
        seed = ContextSeed(
            tasks=[{"task_id": "PI-001", "title": "Test", "config": {}}],
            artifacts={"plan_document_path": "/p.md"},
        )
        d = seed.to_dict()
        assert d["tasks"][0]["task_id"] == "PI-001"
        assert d["artifacts"]["plan_document_path"] == "/p.md"

    def test_tasks_and_artifacts_are_copies(self):
        """to_dict returns copies, not references."""
        tasks = [{"task_id": "PI-001", "title": "Test", "config": {}}]
        seed = ContextSeed(tasks=tasks)
        d = seed.to_dict()
        d["tasks"].append({"task_id": "PI-002", "title": "X", "config": {}})
        assert len(seed.tasks) == 1  # Original unchanged


class TestSeedTask:
    """SeedTask.from_seed_entry tests."""

    @staticmethod
    def _make_entry(**overrides):
        """Build a minimal valid seed entry dict."""
        entry = {
            "task_id": "PI-001",
            "title": "Test Task",
            "task_type": "task",
            "story_points": 3,
            "priority": "medium",
            "labels": ["core"],
            "depends_on": [],
            "config": {
                "task_description": "Implement feature",
                "context": {
                    "feature_id": "F1",
                    "target_files": ["src/mod.py"],
                    "estimated_loc": 50,
                },
            },
            "_enrichment": {
                "domain": "python-single-module",
                "domain_reasoning": "Single .py file",
                "environment_checks": [],
                "prompt_constraints": ["No wildcard imports"],
                "post_generation_validators": [],
                "available_siblings": [],
            },
        }
        entry.update(overrides)
        return entry

    def test_basic_parse(self):
        entry = self._make_entry()
        task = SeedTask.from_seed_entry(entry)
        assert task.task_id == "PI-001"
        assert task.title == "Test Task"
        assert task.domain == "python-single-module"
        assert task.feature_id == "F1"
        assert task.target_files == ["src/mod.py"]
        assert task.estimated_loc == 50
        assert "No wildcard imports" in task.prompt_constraints

    def test_missing_task_id_raises(self):
        entry = self._make_entry()
        entry["task_id"] = ""
        with pytest.raises(ValueError, match="task_id"):
            SeedTask.from_seed_entry(entry)

    def test_missing_title_raises(self):
        entry = self._make_entry()
        entry["title"] = ""
        with pytest.raises(ValueError, match="title"):
            SeedTask.from_seed_entry(entry)

    def test_domain_defaults_to_unknown(self):
        entry = self._make_entry()
        entry["_enrichment"] = {}
        task = SeedTask.from_seed_entry(entry)
        assert task.domain == "unknown"

    def test_prompt_hints_merged_into_constraints(self):
        entry = self._make_entry()
        entry["config"]["context"]["prompt_hints"] = ["Use type hints"]
        task = SeedTask.from_seed_entry(entry)
        assert "Use type hints" in task.prompt_constraints
        assert "No wildcard imports" in task.prompt_constraints

    def test_wave_index_valid(self):
        entry = self._make_entry(wave_index=2)
        task = SeedTask.from_seed_entry(entry)
        assert task.wave_index == 2

    def test_wave_index_negative_ignored(self):
        entry = self._make_entry(wave_index=-1)
        task = SeedTask.from_seed_entry(entry)
        assert task.wave_index is None

    def test_wave_index_bool_ignored(self):
        entry = self._make_entry(wave_index=True)
        task = SeedTask.from_seed_entry(entry)
        assert task.wave_index is None

    def test_complexity_tier_override_valid(self):
        entry = self._make_entry()
        entry["config"]["context"]["complexity_tier_override"] = "tier_2"
        task = SeedTask.from_seed_entry(entry)
        assert task.complexity_tier_override == "tier_2"

    def test_complexity_tier_override_invalid_ignored(self):
        entry = self._make_entry()
        entry["config"]["context"]["complexity_tier_override"] = "tier_99"
        task = SeedTask.from_seed_entry(entry)
        assert task.complexity_tier_override is None

    def test_deps_confidence_from_source(self):
        entry = self._make_entry()
        entry["_enrichment"]["deps_source"] = "pyproject"
        task = SeedTask.from_seed_entry(entry)
        assert task.deps_confidence == 1.0
        assert task.deps_source == "pyproject"

    def test_deps_confidence_venv_only(self):
        entry = self._make_entry()
        entry["_enrichment"]["deps_source"] = "venv_only"
        task = SeedTask.from_seed_entry(entry)
        assert task.deps_confidence == 0.5


class TestBackwardCompat:
    """Verify backward-compat imports from original locations."""

    def test_artisan_context_seed_import(self):
        from startd8.workflows.builtin.plan_ingestion_models import ArtisanContextSeed
        # ArtisanContextSeed should still work
        seed = ArtisanContextSeed()
        assert seed.version == "1.0.0"

    def test_seed_task_from_handlers(self):
        from startd8.contractors.context_seed_handlers import SeedTask as HandlerSeedTask
        # Should be the same class (or at least functionally identical)
        assert hasattr(HandlerSeedTask, "from_seed_entry")

    def test_schema_versions_from_workflow(self):
        from startd8.workflows.builtin.schema_versions import (
            ARTISAN_SCHEMA_VERSION,
            SUPPORTED_SEED_SCHEMA_VERSIONS,
        )
        assert ARTISAN_SCHEMA_VERSION == "1.0"
        assert "1.0.0" in SUPPORTED_SEED_SCHEMA_VERSIONS
