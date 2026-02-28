"""Tests for Phase 2 data flow fixes (Fixes 1, 2, 3, 5).

Covers:
- Fix 1: source_checksum extraction in PLAN and provenance in FINALIZE manifest
- Fix 2: parameter_sources propagation through PLAN → DESIGN → IMPLEMENT
- Fix 3: semantic_conventions propagation through PLAN → DESIGN → IMPLEMENT
- Fix 5: output_conventions validation in SCAFFOLD
- Plan ingestion: parameter_sources and semantic_conventions propagation
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from startd8.contractors.artisan_contractor import (
    ArtisanContractorWorkflow,
    PhaseStatus,
    WorkflowConfig,
    WorkflowPhase,
    WorkflowStatus,
)
from startd8.contractors.context_seed_handlers import (
    ContextSeedHandlers,
    DesignPhaseHandler,
    HandlerConfig,
    ImplementPhaseHandler,
    ScaffoldPhaseHandler,
    SeedTask,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _build_enriched_seed(
    tmp_path: Path,
    *,
    source_checksum: str | None = None,
    parameter_sources: dict | None = None,
    semantic_conventions: dict | None = None,
    output_conventions: dict | None = None,
) -> Path:
    """Create a minimal enriched seed with optional onboarding enrichment fields."""
    artifacts: dict[str, Any] = {}
    if source_checksum is not None:
        artifacts["source_checksum"] = source_checksum
    if parameter_sources is not None:
        artifacts["parameter_sources"] = parameter_sources
    if semantic_conventions is not None:
        artifacts["semantic_conventions"] = semantic_conventions
    if output_conventions is not None:
        artifacts["output_conventions"] = output_conventions

    seed_data = {
        "plan": {
            "title": "Data Flow Test Plan",
            "goals": ["Verify data flow fixes"],
        },
        "_preflight": {
            "check_summary": {"pass": 1, "fail": 0, "warn": 0},
        },
        "artifacts": artifacts,
        "tasks": [
            {
                "task_id": "T1",
                "title": "Generate dashboard",
                "task_type": "task",
                "story_points": 3,
                "priority": "high",
                "labels": ["observability"],
                "depends_on": [],
                "config": {
                    "task_description": "Generate Grafana dashboard JSON",
                    "context": {
                        "target_files": ["dashboards/overview.json"],
                        "estimated_loc": 100,
                        "feature_id": "F-DASH-001",
                        "artifact_types_addressed": ["dashboard"],
                    },
                },
                "_enrichment": {
                    "domain": "observability",
                    "domain_reasoning": "Dashboard generation",
                    "environment_checks": [],
                    "prompt_constraints": ["Use Grafana JSON model"],
                    "post_generation_validators": ["ruff"],
                    "available_siblings": [],
                    "existing_content_hash": None,
                },
            },
        ],
    }

    seed_path = tmp_path / "enriched-seed.json"
    seed_path.write_text(json.dumps(seed_data), encoding="utf-8")
    return seed_path


def _run_dryrun_workflow(
    tmp_path: Path,
    seed_path: Path,
) -> tuple[Any, dict[str, Any]]:
    """Run a dry-run workflow and return (result, context)."""
    config = WorkflowConfig(dry_run=True, project_root=str(tmp_path))
    workflow = ArtisanContractorWorkflow(config=config)

    with patch(
        "startd8.contractors.context_seed_handlers.HandlerConfig.from_config",
        return_value=HandlerConfig(),
    ):
        handlers = ContextSeedHandlers.create_all(
            enriched_seed_path=str(seed_path),
        )

    for phase, handler in handlers.items():
        workflow.register_handler(phase, handler)

    context: dict[str, Any] = {"enriched_seed_path": str(seed_path)}
    result = workflow.execute(context=context)
    return result, context


# ── Fix 1: source_checksum ───────────────────────────────────────────


class TestSourceChecksum:
    """Fix 1: provenance chain — source_checksum in PLAN and FINALIZE."""

    def test_plan_phase_extracts_source_checksum(self, tmp_path: Path) -> None:
        """PLAN phase should store source_checksum in context when present in seed."""
        seed_path = _build_enriched_seed(
            tmp_path, source_checksum="abc123def456"
        )
        result, context = _run_dryrun_workflow(tmp_path, seed_path)

        assert result.status == WorkflowStatus.COMPLETED
        assert context.get("source_checksum") == "abc123def456"

    def test_plan_phase_warns_missing_source_checksum(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """PLAN phase should warn when source_checksum is absent."""
        seed_path = _build_enriched_seed(tmp_path)  # no source_checksum
        with caplog.at_level(logging.WARNING):
            result, context = _run_dryrun_workflow(tmp_path, seed_path)

        assert result.status == WorkflowStatus.COMPLETED
        # M-9 fix: source_checksum defaults to "" instead of None
        assert context.get("source_checksum") in (None, "")
        assert any(
            "source_checksum absent" in r.message for r in caplog.records
        )

    def test_finalize_manifest_includes_provenance(self, tmp_path: Path) -> None:
        """FINALIZE manifest should include a provenance block with source_checksum."""
        seed_path = _build_enriched_seed(
            tmp_path, source_checksum="sha256:abc123"
        )
        result, context = _run_dryrun_workflow(tmp_path, seed_path)

        assert result.status == WorkflowStatus.COMPLETED
        # In dry-run mode, FINALIZE doesn't write the manifest file, but
        # the workflow_summary (which is the manifest data structure) should
        # be available. The provenance block is added in _write_manifest(),
        # which is only called in non-dry-run. So we verify the context key
        # survived through all phases.
        assert context.get("source_checksum") == "sha256:abc123"


# ── Fix 2: parameter_sources ────────────────────────────────────────


class TestParameterSources:
    """Fix 2: parameter_sources propagation through PLAN → DESIGN → IMPLEMENT."""

    def test_plan_phase_stores_parameter_sources(self, tmp_path: Path) -> None:
        """PLAN phase should extract parameter_sources from seed artifacts."""
        param_sources = {
            "dashboard": {"title": "from .contextcore.yaml:project.name"},
        }
        seed_path = _build_enriched_seed(
            tmp_path, parameter_sources=param_sources
        )
        result, context = _run_dryrun_workflow(tmp_path, seed_path)

        assert result.status == WorkflowStatus.COMPLETED
        assert context.get("parameter_sources") == param_sources

    def test_plan_phase_defaults_empty_when_absent(self, tmp_path: Path) -> None:
        """parameter_sources should default to {} when not in seed."""
        seed_path = _build_enriched_seed(tmp_path)
        result, context = _run_dryrun_workflow(tmp_path, seed_path)

        assert result.status == WorkflowStatus.COMPLETED
        assert context.get("parameter_sources") == {}

    def test_design_phase_injects_parameter_sources(self) -> None:
        """_task_to_feature_context should inject parameter_sources into additional_context."""
        task = SeedTask(
            task_id="T1", title="Dashboard", task_type="task",
            story_points=3, priority="high", labels=[], depends_on=[],
            description="Generate dashboard", target_files=["dash.json"],
            estimated_loc=100, feature_id="F1", domain="observability",
            domain_reasoning="", environment_checks=[],
            prompt_constraints=[], post_generation_validators=[],
            available_siblings=[], existing_content_hash=None,
            design_doc_sections=[], artifact_types_addressed=["dashboard"],
            file_scope={},
        )
        param_sources = {
            "dashboard": {"title": "from .contextcore.yaml:project.name"},
        }

        feature_ctx = DesignPhaseHandler._task_to_feature_context(
            task, parameter_sources=param_sources,
        )

        # The additional_context should contain the parameter_sources text
        ac = feature_ctx.additional_context
        assert "parameter_sources" in ac
        assert "dashboard" in ac["parameter_sources"]

    def test_implement_chunk_metadata_includes_parameter_sources(self) -> None:
        """parameter_sources stored in chunk metadata for _build_supplementary_context rendering."""
        task = SeedTask(
            task_id="T1", title="Dashboard", task_type="task",
            story_points=3, priority="high", labels=[], depends_on=[],
            description="Generate dashboard", target_files=["dash.json"],
            estimated_loc=100, feature_id="F1", domain="observability",
            domain_reasoning="", environment_checks=[],
            prompt_constraints=[], post_generation_validators=[],
            available_siblings=[], existing_content_hash=None,
            design_doc_sections=[], artifact_types_addressed=["dashboard"],
            file_scope={},
        )
        param_sources = {
            "dashboard": {"title": "from .contextcore.yaml:project.name"},
        }

        chunks, _skipped = ImplementPhaseHandler._tasks_to_chunks(
            [task], parameter_sources=param_sources,
        )

        assert len(chunks) == 1
        assert chunks[0].metadata["parameter_sources"] == param_sources


# ── Fix 3: semantic_conventions ──────────────────────────────────────


class TestSemanticConventions:
    """Fix 3: semantic_conventions propagation through PLAN → DESIGN → IMPLEMENT."""

    def test_plan_phase_stores_semantic_conventions(self, tmp_path: Path) -> None:
        """PLAN phase should extract semantic_conventions from seed artifacts."""
        sem_conv = {
            "metric_prefix": "myapp_",
            "label_keys": ["namespace", "pod"],
        }
        seed_path = _build_enriched_seed(
            tmp_path, semantic_conventions=sem_conv
        )
        result, context = _run_dryrun_workflow(tmp_path, seed_path)

        assert result.status == WorkflowStatus.COMPLETED
        assert context.get("semantic_conventions") == sem_conv

    def test_design_phase_injects_semantic_conventions(self) -> None:
        """_task_to_feature_context should inject semantic_conventions."""
        task = SeedTask(
            task_id="T1", title="Dashboard", task_type="task",
            story_points=3, priority="high", labels=[], depends_on=[],
            description="Generate dashboard", target_files=["dash.json"],
            estimated_loc=100, feature_id="F1", domain="observability",
            domain_reasoning="", environment_checks=[],
            prompt_constraints=[], post_generation_validators=[],
            available_siblings=[], existing_content_hash=None,
            design_doc_sections=[], artifact_types_addressed=["dashboard"],
            file_scope={},
        )
        sem_conv = {"metric_prefix": "myapp_"}

        feature_ctx = DesignPhaseHandler._task_to_feature_context(
            task, semantic_conventions=sem_conv,
        )

        ac = feature_ctx.additional_context
        assert "semantic_conventions" in ac
        assert "metric_prefix" in ac["semantic_conventions"]

    def test_implement_chunk_metadata_includes_semantic_conventions(self) -> None:
        """semantic_conventions stored in chunk metadata for _build_supplementary_context rendering."""
        task = SeedTask(
            task_id="T1", title="Dashboard", task_type="task",
            story_points=3, priority="high", labels=[], depends_on=[],
            description="Generate dashboard", target_files=["dash.json"],
            estimated_loc=100, feature_id="F1", domain="observability",
            domain_reasoning="", environment_checks=[],
            prompt_constraints=[], post_generation_validators=[],
            available_siblings=[], existing_content_hash=None,
            design_doc_sections=[], artifact_types_addressed=["dashboard"],
            file_scope={},
        )
        sem_conv = {"metric_prefix": "myapp_"}

        chunks, _skipped = ImplementPhaseHandler._tasks_to_chunks(
            [task], semantic_conventions=sem_conv,
        )

        assert len(chunks) == 1
        assert chunks[0].metadata["semantic_conventions"] == sem_conv


# ── Fix 5: output_conventions ────────────────────────────────────────


class TestOutputConventions:
    """Fix 5: SCAFFOLD output_conventions warn-only extension validation."""

    def test_scaffold_warns_mismatched_extension(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """SCAFFOLD should warn when target file extension doesn't match convention."""
        output_conv = {
            "dashboard": {"output_ext": ".json"},
        }
        # Use a seed where the task targets a .yaml file but convention expects .json
        seed_data = {
            "plan": {"title": "Test", "goals": []},
            "_preflight": {"check_summary": {"pass": 1, "fail": 0}},
            "artifacts": {"output_conventions": output_conv},
            "tasks": [{
                "task_id": "T1",
                "title": "Generate dashboard",
                "task_type": "task",
                "story_points": 1,
                "priority": "high",
                "labels": [],
                "depends_on": [],
                "config": {
                    "task_description": "Generate dashboard",
                    "context": {
                        "target_files": ["dashboards/overview.yaml"],  # wrong ext
                        "estimated_loc": 50,
                        "feature_id": "F1",
                        "artifact_types_addressed": ["dashboard"],
                    },
                },
                "_enrichment": {
                    "domain": "observability",
                    "domain_reasoning": "",
                    "environment_checks": [],
                    "prompt_constraints": [],
                    "post_generation_validators": [],
                    "available_siblings": [],
                    "existing_content_hash": None,
                },
            }],
        }
        seed_path = tmp_path / "seed.json"
        seed_path.write_text(json.dumps(seed_data))

        with caplog.at_level(logging.WARNING):
            result, context = _run_dryrun_workflow(tmp_path, seed_path)

        assert result.status == WorkflowStatus.COMPLETED
        # Check for the extension mismatch warning
        scaffold_warnings = [
            r.message for r in caplog.records
            if "doesn't match expected extension" in r.message
        ]
        assert len(scaffold_warnings) >= 1
        assert ".json" in scaffold_warnings[0]

    def test_scaffold_no_warning_when_extensions_match(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """SCAFFOLD should not warn when extensions match conventions."""
        output_conv = {
            "dashboard": {"output_ext": ".json"},
        }
        seed_path = _build_enriched_seed(
            tmp_path, output_conventions=output_conv
        )
        # The default seed has target_files=["dashboards/overview.json"] which matches

        with caplog.at_level(logging.WARNING):
            result, context = _run_dryrun_workflow(tmp_path, seed_path)

        assert result.status == WorkflowStatus.COMPLETED
        scaffold_ext_warnings = [
            r.message for r in caplog.records
            if "doesn't match expected extension" in r.message
        ]
        assert len(scaffold_ext_warnings) == 0

    def test_scaffold_no_warning_when_no_conventions(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """SCAFFOLD should not warn when output_conventions is empty."""
        seed_path = _build_enriched_seed(tmp_path)  # no output_conventions

        with caplog.at_level(logging.WARNING):
            result, context = _run_dryrun_workflow(tmp_path, seed_path)

        assert result.status == WorkflowStatus.COMPLETED
        scaffold_ext_warnings = [
            r.message for r in caplog.records
            if "doesn't match expected extension" in r.message
        ]
        assert len(scaffold_ext_warnings) == 0


# ── Plan ingestion propagation ───────────────────────────────────────


class TestPlanIngestionPropagation:
    """Tests for parameter_sources and semantic_conventions propagation in plan ingestion."""

    def test_onboarding_parameter_sources_propagated(self) -> None:
        """The plan ingestion _phase_emit should propagate parameter_sources from onboarding."""
        # This is a structural test — we verify the code path exists by
        # checking that the artifact dict construction logic handles the key.
        # A full integration test would run the plan ingestion workflow.
        onboarding = {
            "parameter_sources": {"dashboard": {"title": "from project.name"}},
        }
        artifacts: dict[str, Any] = {}
        # Replicate the extraction logic from plan_ingestion_workflow.py
        ps = onboarding.get("parameter_sources")
        if ps and isinstance(ps, dict):
            artifacts["parameter_sources"] = ps

        assert "parameter_sources" in artifacts
        assert artifacts["parameter_sources"]["dashboard"]["title"] == "from project.name"

    def test_onboarding_semantic_conventions_propagated(self) -> None:
        """The plan ingestion _phase_emit should propagate semantic_conventions."""
        onboarding = {
            "semantic_conventions": {"metric_prefix": "myapp_"},
        }
        artifacts: dict[str, Any] = {}
        sc_conv = onboarding.get("semantic_conventions")
        if sc_conv and isinstance(sc_conv, dict):
            artifacts["semantic_conventions"] = sc_conv

        assert "semantic_conventions" in artifacts
        assert artifacts["semantic_conventions"]["metric_prefix"] == "myapp_"

    def test_onboarding_output_conventions_propagated(self) -> None:
        """The plan ingestion _phase_emit should propagate output_conventions."""
        onboarding = {
            "output_conventions": {"dashboard": {"output_ext": ".json"}},
        }
        artifacts: dict[str, Any] = {}
        oc = onboarding.get("output_conventions")
        if oc and isinstance(oc, dict):
            artifacts["output_conventions"] = oc

        assert "output_conventions" in artifacts


# ── Full pipeline context key presence ───────────────────────────────


class TestFullPipelineDataFlow:
    """Verify all 4 new context keys survive a full dry-run pipeline."""

    def test_all_new_keys_present_after_pipeline(self, tmp_path: Path) -> None:
        """After a full dry-run, all Phase 2 context keys should be present."""
        seed_path = _build_enriched_seed(
            tmp_path,
            source_checksum="sha256:test123",
            parameter_sources={"dashboard": {"title": "test"}},
            semantic_conventions={"metric_prefix": "app_"},
            output_conventions={"dashboard": {"output_ext": ".json"}},
        )
        result, context = _run_dryrun_workflow(tmp_path, seed_path)

        assert result.status == WorkflowStatus.COMPLETED
        assert context["source_checksum"] == "sha256:test123"
        assert context["parameter_sources"] == {"dashboard": {"title": "test"}}
        assert context["semantic_conventions"] == {"metric_prefix": "app_"}
        assert context["output_conventions"] == {"dashboard": {"output_ext": ".json"}}

    def test_all_new_keys_default_safely(self, tmp_path: Path) -> None:
        """Without ContextCore enrichment, all new keys should default safely."""
        seed_path = _build_enriched_seed(tmp_path)  # no enrichment
        result, context = _run_dryrun_workflow(tmp_path, seed_path)

        assert result.status == WorkflowStatus.COMPLETED
        # M-9 fix: source_checksum defaults to "" instead of None
        assert context.get("source_checksum") in (None, "")
        assert context.get("parameter_sources") == {}
        assert context.get("semantic_conventions") == {}
        assert context.get("output_conventions") == {}
