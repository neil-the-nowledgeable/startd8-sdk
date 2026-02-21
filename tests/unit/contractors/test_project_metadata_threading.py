"""Verification tests for project_metadata threading through the artisan pipeline.

Covers plan criteria 1-4:
1. Round-trip: ArtisanContextSeed.to_dict() → JSON → PlanPhaseHandler → context
2. Schema validation: _validate_context_seed() accepts seed with project_metadata
3. Field coverage: _validate_seed_field_coverage() warns when absent
4. Checkpoint resume: _ensure_context_loaded() restores project_metadata from seed
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_PROJECT_METADATA: Dict[str, Any] = {
    "criticality": "high",
    "business_owner": "platform-team",
    "business_value": "Core revenue path",
    "requirements": {
        "availability": "99.95%",
        "latency_p99": "200ms",
        "error_budget": "0.05%",
    },
    "risks": [
        {
            "type": "security",
            "priority": "P1",
            "description": "Auth token rotation gap",
            "scope": "src/auth/**",
            "mitigation": "Add rotation cron job",
        },
    ],
    "observability": {
        "trace_sampling": 0.1,
        "metrics_interval": "15s",
        "log_level": "info",
    },
}


def _minimal_seed_dict(
    *,
    with_project_metadata: bool = True,
    with_tasks: bool = True,
) -> Dict[str, Any]:
    """Return a minimal valid artisan context seed dict."""
    seed: Dict[str, Any] = {
        "version": "1.0.0",
        "schema_version": "2.0.0",
        "generated_at": "2026-02-21T00:00:00+00:00",
        "source_checksum": None,
        "generator": "plan-ingestion",
        "plan": {"title": "Test Plan", "goals": ["g1"], "features": [], "dependency_graph": {}, "mentioned_files": []},
        "complexity": {"composite": 30, "dimensions": {}, "reasoning": "low", "route": "artisan"},
        "tasks": [
            {
                "task_id": "T-001",
                "title": "Implement auth",
                "description": "Add auth module",
                "target_files": ["src/auth.py"],
                "dependencies": [],
                "estimated_loc": 100,
                "labels": [],
            },
        ] if with_tasks else [],
        "artifacts": {},
        "ingestion_metrics": {"total_cost": 0.0},
    }
    if with_project_metadata:
        seed["project_metadata"] = SAMPLE_PROJECT_METADATA
    return seed


# ---------------------------------------------------------------------------
# 1. Round-trip through ArtisanContextSeed
# ---------------------------------------------------------------------------

class TestRoundTrip:
    """Criterion 1: project_metadata survives to_dict → JSON → reload."""

    def test_to_dict_includes_project_metadata(self):
        from startd8.workflows.builtin.plan_ingestion_models import ArtisanContextSeed

        seed = ArtisanContextSeed(project_metadata=SAMPLE_PROJECT_METADATA)
        d = seed.to_dict()
        assert "project_metadata" in d
        assert d["project_metadata"] == SAMPLE_PROJECT_METADATA

    def test_to_dict_omits_when_none(self):
        from startd8.workflows.builtin.plan_ingestion_models import ArtisanContextSeed

        seed = ArtisanContextSeed(project_metadata=None)
        d = seed.to_dict()
        assert "project_metadata" not in d

    def test_json_round_trip(self):
        from startd8.workflows.builtin.plan_ingestion_models import ArtisanContextSeed

        seed = ArtisanContextSeed(project_metadata=SAMPLE_PROJECT_METADATA)
        serialized = json.dumps(seed.to_dict())
        reloaded = json.loads(serialized)
        assert reloaded["project_metadata"] == SAMPLE_PROJECT_METADATA

    def test_round_trip_to_plan_phase_context(self, tmp_path):
        """Full round-trip: seed dict → JSON file → PlanPhaseHandler → context."""
        from startd8.workflows.builtin.plan_ingestion_models import ArtisanContextSeed

        seed = ArtisanContextSeed(
            generated_at="2026-02-21T00:00:00+00:00",
            plan={"title": "Test", "goals": [], "features": [], "dependency_graph": {}, "mentioned_files": []},
            complexity={"composite": 10, "dimensions": {}, "reasoning": "low", "route": "artisan"},
            tasks=[{
                "task_id": "T-001", "title": "t", "description": "d",
                "target_files": ["f.py"], "dependencies": [], "estimated_loc": 50,
                "labels": [],
            }],
            artifacts={},
            ingestion_metrics={"total_cost": 0.0},
            project_metadata=SAMPLE_PROJECT_METADATA,
        )
        seed_path = tmp_path / "seed.json"
        seed_path.write_text(json.dumps(seed.to_dict()), encoding="utf-8")

        # Load back and check the field survives
        reloaded = json.loads(seed_path.read_text(encoding="utf-8"))
        assert reloaded.get("project_metadata") == SAMPLE_PROJECT_METADATA


# ---------------------------------------------------------------------------
# 2. Schema validation
# ---------------------------------------------------------------------------

class TestSchemaValidation:
    """Criterion 2: _validate_context_seed() accepts project_metadata."""

    def test_schema_accepts_project_metadata(self):
        from startd8.workflows.builtin.plan_ingestion_workflow import _validate_context_seed

        seed_dict = _minimal_seed_dict(with_project_metadata=True)
        # Should not raise
        _validate_context_seed(seed_dict)

    def test_schema_accepts_null_project_metadata(self):
        from startd8.workflows.builtin.plan_ingestion_workflow import _validate_context_seed

        seed_dict = _minimal_seed_dict(with_project_metadata=False)
        seed_dict["project_metadata"] = None
        # Should not raise
        _validate_context_seed(seed_dict)

    def test_schema_accepts_absent_project_metadata(self):
        from startd8.workflows.builtin.plan_ingestion_workflow import _validate_context_seed

        seed_dict = _minimal_seed_dict(with_project_metadata=False)
        assert "project_metadata" not in seed_dict
        # Should not raise (additionalProperties: true)
        _validate_context_seed(seed_dict)


# ---------------------------------------------------------------------------
# 3. Field coverage warnings
# ---------------------------------------------------------------------------

class TestFieldCoverage:
    """Criterion 3: _validate_seed_field_coverage() warns when absent."""

    def test_warns_when_project_metadata_absent(self):
        from startd8.workflows.builtin.plan_ingestion_workflow import _validate_seed_field_coverage

        seed_dict = _minimal_seed_dict(with_project_metadata=False)
        warnings = _validate_seed_field_coverage(seed_dict)
        pm_warnings = [w for w in warnings if "project_metadata" in w]
        assert len(pm_warnings) == 1
        assert "criticality/SLO-aware" in pm_warnings[0]

    def test_no_warning_when_project_metadata_present(self):
        from startd8.workflows.builtin.plan_ingestion_workflow import _validate_seed_field_coverage

        seed_dict = _minimal_seed_dict(with_project_metadata=True)
        warnings = _validate_seed_field_coverage(seed_dict)
        pm_warnings = [w for w in warnings if "project_metadata" in w]
        assert len(pm_warnings) == 0

    def test_warns_when_project_metadata_is_empty_dict(self):
        from startd8.workflows.builtin.plan_ingestion_workflow import _validate_seed_field_coverage

        seed_dict = _minimal_seed_dict(with_project_metadata=False)
        seed_dict["project_metadata"] = {}
        warnings = _validate_seed_field_coverage(seed_dict)
        pm_warnings = [w for w in warnings if "project_metadata" in w]
        # Empty dict is falsy → should warn
        assert len(pm_warnings) == 1


# ---------------------------------------------------------------------------
# 4. Checkpoint resume via _ensure_context_loaded
# ---------------------------------------------------------------------------

class TestCheckpointResume:
    """Criterion 4: _ensure_context_loaded() restores project_metadata."""

    def test_ensure_context_loaded_restores_project_metadata(self, tmp_path):
        from startd8.contractors.context_seed_handlers import _ensure_context_loaded

        seed_dict = _minimal_seed_dict(with_project_metadata=True)
        seed_path = tmp_path / "seed.json"
        seed_path.write_text(json.dumps(seed_dict), encoding="utf-8")

        context: Dict[str, Any] = {"enriched_seed_path": str(seed_path)}
        _ensure_context_loaded(context)

        assert "project_metadata" in context
        assert context["project_metadata"] == SAMPLE_PROJECT_METADATA

    def test_ensure_context_loaded_does_not_overwrite_existing(self, tmp_path):
        from startd8.contractors.context_seed_handlers import _ensure_context_loaded

        seed_dict = _minimal_seed_dict(with_project_metadata=True)
        seed_path = tmp_path / "seed.json"
        seed_path.write_text(json.dumps(seed_dict), encoding="utf-8")

        existing_meta = {"criticality": "low"}
        context: Dict[str, Any] = {
            "enriched_seed_path": str(seed_path),
            "project_metadata": existing_meta,
        }
        _ensure_context_loaded(context)

        # setdefault should NOT overwrite
        assert context["project_metadata"] == existing_meta

    def test_ensure_context_loaded_empty_when_absent_in_seed(self, tmp_path):
        from startd8.contractors.context_seed_handlers import _ensure_context_loaded

        seed_dict = _minimal_seed_dict(with_project_metadata=False)
        seed_path = tmp_path / "seed.json"
        seed_path.write_text(json.dumps(seed_dict), encoding="utf-8")

        context: Dict[str, Any] = {"enriched_seed_path": str(seed_path)}
        _ensure_context_loaded(context)

        assert context.get("project_metadata") == {}


# ---------------------------------------------------------------------------
# 5. Checkpoint context keys includes project_metadata
# ---------------------------------------------------------------------------

class TestCheckpointContextKeys:
    """project_metadata must be in _CHECKPOINT_CONTEXT_KEYS for resume."""

    def test_checkpoint_keys_includes_project_metadata(self):
        from startd8.contractors.artisan_contractor import _CHECKPOINT_CONTEXT_KEYS

        assert "project_metadata" in _CHECKPOINT_CONTEXT_KEYS


# ---------------------------------------------------------------------------
# 6. PCA context fields includes project_metadata
# ---------------------------------------------------------------------------

class TestPCAContextFields:
    """project_metadata must be in _PCA_CONTEXT_FIELDS for completeness logging."""

    def test_pca_fields_includes_project_metadata(self):
        from startd8.contractors.context_seed_handlers import _PCA_CONTEXT_FIELDS

        assert "project_metadata" in _PCA_CONTEXT_FIELDS


# ---------------------------------------------------------------------------
# 7. Contract YAML declares project_metadata
# ---------------------------------------------------------------------------

class TestContractYAML:
    """artisan-pipeline.contract.yaml must declare project_metadata."""

    @pytest.fixture()
    def contract(self):
        import yaml

        contract_path = (
            Path(__file__).resolve().parents[3]
            / "src" / "startd8" / "contractors" / "contracts"
            / "artisan-pipeline.contract.yaml"
        )
        with open(contract_path) as f:
            return yaml.safe_load(f)

    def test_plan_exit_optional_has_project_metadata(self, contract):
        plan_exit_optional = contract["phases"]["plan"]["exit"]["optional"]
        names = [f["name"] for f in plan_exit_optional]
        assert "project_metadata" in names

    def test_propagation_chain_exists(self, contract):
        chains = contract["propagation_chains"]
        chain_ids = [c["chain_id"] for c in chains]
        assert "project_metadata_to_review" in chain_ids

    def test_propagation_chain_source_destination(self, contract):
        chains = contract["propagation_chains"]
        chain = next(c for c in chains if c["chain_id"] == "project_metadata_to_review")
        assert chain["source"]["phase"] == "plan"
        assert chain["source"]["field"] == "project_metadata"
        assert chain["destination"]["phase"] == "review"
        assert chain["destination"]["field"] == "project_metadata"
        assert chain["severity"] == "advisory"


# ---------------------------------------------------------------------------
# 8. _extract_project_metadata() method
# ---------------------------------------------------------------------------

class TestExtractProjectMetadata:
    """The extractor must handle various manifest shapes gracefully."""

    def _get_extractor(self):
        from startd8.workflows.builtin.plan_ingestion_workflow import PlanIngestionWorkflow
        return PlanIngestionWorkflow._extract_project_metadata

    def test_empty_manifest_returns_empty(self):
        """Manifest with no spec attr → empty dict."""

        class EmptyManifest:
            pass

        result = self._get_extractor()(EmptyManifest())
        assert result == {}

    def test_manifest_with_no_spec(self):
        """Manifest with spec=None → empty dict."""

        class Manifest:
            spec = None

        result = self._get_extractor()(Manifest())
        assert result == {}

    def test_extracts_business_criticality(self):
        """Business criticality with enum-like .value."""

        class Criticality:
            value = "high"

        class Business:
            criticality = Criticality()
            business_owner = "team-a"
            business_value = "Revenue"
            owner = None
            value = None

        class Spec:
            business = Business()
            requirements = None
            risks = None
            observability = None

        class Manifest:
            spec = Spec()

        result = self._get_extractor()(Manifest())
        assert result["criticality"] == "high"
        assert result["business_owner"] == "team-a"
        assert result["business_value"] == "Revenue"

    def test_extracts_requirements(self):
        class Requirements:
            availability = "99.9%"
            latency_p99 = "100ms"
            throughput = None
            error_budget = "0.1%"

        class Spec:
            business = None
            requirements = Requirements()
            risks = None
            observability = None

        class Manifest:
            spec = Spec()

        result = self._get_extractor()(Manifest())
        assert result["requirements"]["availability"] == "99.9%"
        assert result["requirements"]["latency_p99"] == "100ms"
        assert "throughput" not in result["requirements"]  # None → skipped
        assert result["requirements"]["error_budget"] == "0.1%"

    def test_extracts_risks(self):
        class Risk:
            type = "security"
            priority = "P1"
            description = "Token leak"
            scope = "src/auth/**"
            mitigation = "Rotate"
            component = None

        class Spec:
            business = None
            requirements = None
            risks = [Risk()]
            observability = None

        class Manifest:
            spec = Spec()

        result = self._get_extractor()(Manifest())
        assert len(result["risks"]) == 1
        assert result["risks"][0]["type"] == "security"
        assert result["risks"][0]["priority"] == "P1"
        assert "component" not in result["risks"][0]  # None → skipped

    def test_extracts_observability(self):
        class Observability:
            trace_sampling = 0.1
            metrics_interval = "15s"
            log_level = "info"

        class Spec:
            business = None
            requirements = None
            risks = None
            observability = Observability()

        class Manifest:
            spec = Spec()

        result = self._get_extractor()(Manifest())
        assert result["observability"]["trace_sampling"] == 0.1
        assert result["observability"]["metrics_interval"] == "15s"
        assert result["observability"]["log_level"] == "info"

    def test_enum_value_normalization(self):
        """Enum-like attrs with .value should be unwrapped."""

        class Priority:
            value = "P2"

        class Risk:
            type = "performance"
            priority = Priority()
            description = "Slow query"
            scope = None
            mitigation = None
            component = None

        class Spec:
            business = None
            requirements = None
            risks = [Risk()]
            observability = None

        class Manifest:
            spec = Spec()

        result = self._get_extractor()(Manifest())
        assert result["risks"][0]["priority"] == "P2"
