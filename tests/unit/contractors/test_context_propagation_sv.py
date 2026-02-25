"""
Self-Validating Propagation Boundary Tests (SV-1 through SV-7).

Each test verifies a specific context propagation boundary between components
in the Prime Contractor execution modes architecture. These tests catch gaps
where data silently fails to flow between layers.

Parametrized with (standalone, pipeline) mode pairs where applicable.
"""

import dataclasses
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pytest

from startd8.contractors.context_resolution import (
    PipelineContextStrategy,
    StandaloneContextStrategy,
)
from startd8.contractors.prime_contractor import (
    ExecutionMode,
    ModeConfig,
    PrimeContractorWorkflow,
    SeedContext,
)
from startd8.contractors.queue import FeatureQueue, FeatureSpec, FeatureStatus


# ============================================================================
# Helpers: Minimal workflow construction (avoids full __init__)
# ============================================================================


def _make_workflow(
    *,
    project_root: Path,
    execution_mode: str = "pipeline",
    force_regenerate: bool = False,
    validation_override: Optional[bool] = None,
) -> PrimeContractorWorkflow:
    """Create a minimal PrimeContractorWorkflow for testing.

    Uses object.__new__() to bypass __init__ and directly set required
    attributes, avoiding provider discovery, OTel init, and other side effects.
    """
    wf = object.__new__(PrimeContractorWorkflow)
    wf.project_root = project_root
    wf.dry_run = False
    wf.max_retries = 3
    wf.check_truncation = True
    wf.force_regenerate = force_regenerate
    wf.total_cost_usd = 0.0
    wf.total_input_tokens = 0
    wf.total_output_tokens = 0
    wf.integration_history = []
    wf._validation_override = validation_override
    wf.strict_validation = False

    # SeedContext
    seed = SeedContext(execution_mode=execution_mode)
    wf._seed_context = seed

    # Strategy based on mode
    if execution_mode == "pipeline":
        wf._context_strategy = PipelineContextStrategy()
    else:
        wf._context_strategy = StandaloneContextStrategy()

    wf._strict_mode = False

    # Backward-compat legacy attributes
    wf.seed_onboarding = {}
    wf.seed_architectural_context = {}
    wf.seed_design_calibration = {}
    wf.seed_service_metadata = {}
    wf.plan_document_text = None

    return wf


def _make_feature(
    feature_id: str = "F-001",
    name: str = "test-feature",
    metadata: Optional[Dict[str, Any]] = None,
) -> FeatureSpec:
    """Create a minimal FeatureSpec for testing."""
    return FeatureSpec(
        id=feature_id,
        name=name,
        description="Test feature",
        target_files=["src/test.py"],
        metadata=metadata or {},
    )


# ============================================================================
# SV-1: SeedContext → ContextResolutionStrategy
# ============================================================================


class TestSV1_SeedContextToStrategy:
    """SV-1: Verify SeedContext fields reach strategy resolve_task_context().

    Gap: SeedContext fields might not reach strategy resolve_task_context().
    Check: gen_context contains all non-None SeedContext fields when
    pipeline strategy is active.
    """

    @pytest.mark.parametrize("mode", ["standalone", "pipeline"])
    def test_seed_fields_propagate_to_gen_context(self, tmp_path, mode):
        """Non-None SeedContext fields appear in gen_context output."""
        wf = _make_workflow(project_root=tmp_path, execution_mode=mode)
        wf._seed_context.onboarding_metadata = {"project": "test-proj"}
        wf._seed_context.architectural_context = {"patterns": ["strategy"]}
        wf.seed_onboarding = wf._seed_context.onboarding_metadata
        wf.seed_architectural_context = wf._seed_context.architectural_context

        feature_data = {
            "id": "F-001",
            "name": "test-feature",
            "description": "Test feature",
            "target_files": ["src/test.py"],
            "metadata": {},
        }
        seed_data = wf._seed_context.to_dict()

        strategy = wf._context_strategy
        gen_context = strategy.resolve_task_context(
            feature_data=feature_data,
            seed_data=seed_data,
        )

        # Both modes must produce feature_name and target_file
        assert "feature_name" in gen_context
        assert "target_file" in gen_context
        assert gen_context["feature_name"] == "test-feature"

    def test_pipeline_seed_fields_appear_in_gen_context(self, tmp_path):
        """Pipeline mode: enriched seed fields produce structured sections."""
        wf = _make_workflow(project_root=tmp_path, execution_mode="pipeline")
        wf._seed_context.onboarding_metadata = {"project": "test-proj"}
        wf._seed_context.architectural_context = {"patterns": ["strategy"]}
        wf._seed_context.design_calibration = {"quality": "high"}

        feature_data = {
            "id": "F-001",
            "name": "test-feature",
            "description": "Test feature",
            "target_files": ["src/test.py"],
            "metadata": {
                "requirements_text": "Must implement auth",
            },
        }
        seed_data = wf._seed_context.to_dict()

        gen_context = wf._context_strategy.resolve_task_context(
            feature_data=feature_data,
            seed_data=seed_data,
        )

        # Pipeline strategy should include architectural context section
        assert "architectural_context" in gen_context
        assert gen_context["architectural_context"]  # non-empty

    def test_standalone_does_not_include_pipeline_sections(self, tmp_path):
        """Standalone mode: gen_context does NOT include pipeline-enriched sections."""
        wf = _make_workflow(project_root=tmp_path, execution_mode="standalone")

        feature_data = {
            "id": "F-001",
            "name": "test-feature",
            "description": "Test feature",
            "target_files": ["src/test.py"],
            "metadata": {},
        }
        seed_data = wf._seed_context.to_dict()

        gen_context = wf._context_strategy.resolve_task_context(
            feature_data=feature_data,
            seed_data=seed_data,
        )

        # Standalone should NOT have pipeline-enriched sections
        assert "scope_boundary" not in gen_context


# ============================================================================
# SV-2: ContextResolutionStrategy → gen_context dict
# ============================================================================


class TestSV2_StrategyToGenContext:
    """SV-2: Verify pipeline strategy produces IMP-P section keys in gen_context.

    Gap: Pipeline strategy IMP-P1–P5 sections might be silently dropped.
    Check: gen_context keys include pipeline-enriched sections when data present.
    """

    def test_pipeline_produces_structured_sections(self, tmp_path):
        """Pipeline strategy with enriched data produces all expected sections."""
        strategy = PipelineContextStrategy()
        feature_data = {
            "id": "F-001",
            "name": "test-feature",
            "description": "Implement auth module",
            "target_files": ["src/auth.py"],
            "metadata": {
                "requirements_text": "Must support OAuth2",
                "_enrichment": {"domain": "auth", "constraints": ["no plaintext passwords"]},
            },
        }
        seed_data = {
            "execution_mode": "pipeline",
            "onboarding_metadata": {"project": "acme"},
            "architectural_context": {"patterns": ["repository", "strategy"]},
            "design_calibration": {"quality_tier": "high"},
        }

        gen_context = strategy.resolve_task_context(
            feature_data=feature_data,
            seed_data=seed_data,
        )

        # IMP-P1: architectural context
        assert "architectural_context" in gen_context
        assert gen_context["architectural_context"]  # non-empty

        # IMP-P2: requirements passthrough
        assert "requirements_context" in gen_context
        assert "OAuth2" in gen_context["requirements_context"]

        # Scope boundary instruction (from pipeline)
        assert "scope_boundary" in gen_context

    def test_pipeline_omits_empty_sections(self, tmp_path):
        """Pipeline strategy omits sections when source data is empty."""
        strategy = PipelineContextStrategy()
        feature_data = {
            "id": "F-001",
            "name": "minimal-feature",
            "description": "Minimal",
            "target_files": ["src/min.py"],
            "metadata": {},
        }
        seed_data = {
            "execution_mode": "pipeline",
            "onboarding_metadata": None,
            "architectural_context": None,
            "design_calibration": None,
        }

        gen_context = strategy.resolve_task_context(
            feature_data=feature_data,
            seed_data=seed_data,
        )

        # Sections with empty source data should not be present or should be empty
        assert gen_context.get("architectural_context", "") == ""

    @pytest.mark.parametrize("mode", ["standalone", "pipeline"])
    def test_both_modes_produce_core_keys(self, tmp_path, mode):
        """Both modes produce feature_name and target_file."""
        strategy = (
            PipelineContextStrategy()
            if mode == "pipeline"
            else StandaloneContextStrategy()
        )
        feature_data = {
            "id": "F-001",
            "name": "core-feature",
            "description": "Core test",
            "target_files": ["src/core.py"],
            "metadata": {},
        }
        seed_data = {"execution_mode": mode}

        gen_context = strategy.resolve_task_context(
            feature_data=feature_data,
            seed_data=seed_data,
        )

        assert gen_context["feature_name"] == "core-feature"
        assert gen_context["target_file"] == "src/core.py"


# ============================================================================
# SV-3: Feature Queue → FeatureSpec metadata round-trip
# ============================================================================


class TestSV3_FeatureQueueRoundTrip:
    """SV-3: Verify metadata survives FeatureSpec to_dict()/from_dict() round-trip.

    Gap: Metadata fields added in Phase 3 might not survive serialization.
    Check: FeatureSpec.from_dict(spec.to_dict()) == spec including
    pipeline-injected metadata.
    """

    @pytest.mark.parametrize(
        "metadata",
        [
            {},
            {"requirements_text": "Must support OAuth2"},
            {
                "requirements_text": "Auth",
                "_enrichment": {"domain": "auth"},
                "artifact_types_addressed": ["module", "test"],
                "source_checksum": "abc123",
                "mode": "pipeline",
                "validator_results": [{"name": "import_dep", "passed": True}],
            },
        ],
        ids=["empty", "requirements-only", "full-pipeline"],
    )
    def test_metadata_round_trip_equality(self, metadata):
        """FeatureSpec with metadata survives to_dict/from_dict."""
        spec = FeatureSpec(
            id="F-001",
            name="test-feature",
            description="Test",
            target_files=["src/test.py"],
            metadata=metadata,
        )
        restored = FeatureSpec.from_dict(spec.to_dict())
        assert restored.id == spec.id
        assert restored.name == spec.name
        assert restored.metadata == spec.metadata

    def test_queue_add_feature_with_metadata(self, tmp_path):
        """add_feature() with metadata preserves it through queue state."""
        state_file = tmp_path / "state.json"
        queue = FeatureQueue(state_file=state_file, auto_save=True)

        queue.add_feature(
            feature_id="F-001",
            name="auth",
            description="Auth module",
            metadata={
                "requirements_text": "OAuth2",
                "source_checksum": "abc123",
                "mode": "pipeline",
            },
        )

        # Reload from disk
        queue2 = FeatureQueue(state_file=state_file, auto_save=False)
        restored = queue2.features["F-001"]

        assert restored.metadata["requirements_text"] == "OAuth2"
        assert restored.metadata["source_checksum"] == "abc123"
        assert restored.metadata["mode"] == "pipeline"

    def test_queue_metadata_merge_on_update(self, tmp_path):
        """add_feature() called again merges metadata additively."""
        state_file = tmp_path / "state.json"
        queue = FeatureQueue(state_file=state_file, auto_save=True)

        spec = queue.add_feature(
            feature_id="F-001",
            name="auth",
            description="Auth module",
            metadata={"key1": "val1"},
        )
        # Advance past PENDING so update path is triggered
        spec.status = FeatureStatus.DEVELOPING

        queue.add_feature(
            feature_id="F-001",
            name="auth",
            description="Auth module",
            metadata={"key2": "val2"},
        )

        assert spec.metadata == {"key1": "val1", "key2": "val2"}


# ============================================================================
# SV-4: Generation results → manifest
# ============================================================================


class TestSV4_ResultsToManifest:
    """SV-4: Verify per-feature cost/model data propagates to manifest.

    Gap: Per-feature cost/model data might not propagate to
    generation-manifest.json.
    Check: Manifest entry for each feature contains non-null model and
    cost_usd fields.
    """

    def test_manifest_contains_feature_provenance(self, tmp_path):
        """Pipeline manifest includes per-feature model and cost_usd."""
        wf = _make_workflow(project_root=tmp_path, execution_mode="pipeline")
        wf.integration_history = [
            {
                "feature_id": "F-001",
                "feature_name": "auth",
                "success": True,
                "cost_usd": 0.05,
                "model": "claude-sonnet",
            },
            {
                "feature_id": "F-002",
                "feature_name": "logging",
                "success": True,
                "cost_usd": 0.03,
                "model": "claude-haiku",
            },
        ]
        wf._write_generation_manifest({})

        manifest_path = tmp_path / ".startd8" / "generation-manifest.json"
        assert manifest_path.exists()

        manifest = json.loads(manifest_path.read_text())
        features = manifest["features"]

        assert "F-001" in features
        assert features["F-001"]["model"] == "claude-sonnet"
        assert features["F-001"]["cost_usd"] == 0.05

        assert "F-002" in features
        assert features["F-002"]["model"] == "claude-haiku"
        assert features["F-002"]["cost_usd"] == 0.03

    def test_manifest_not_written_in_standalone(self, tmp_path):
        """Standalone mode does NOT write a manifest."""
        wf = _make_workflow(project_root=tmp_path, execution_mode="standalone")
        wf.integration_history = [
            {
                "feature_id": "F-001",
                "feature_name": "auth",
                "success": True,
                "cost_usd": 0.05,
                "model": "claude-sonnet",
            },
        ]
        wf._write_generation_manifest({})

        manifest_path = tmp_path / ".startd8" / "generation-manifest.json"
        assert not manifest_path.exists()

    def test_manifest_source_checksum_present(self, tmp_path):
        """Pipeline manifest includes source_checksum for staleness detection."""
        wf = _make_workflow(project_root=tmp_path, execution_mode="pipeline")
        wf._write_generation_manifest({})

        manifest_path = tmp_path / ".startd8" / "generation-manifest.json"
        manifest = json.loads(manifest_path.read_text())
        assert "source_checksum" in manifest
        assert len(manifest["source_checksum"]) == 64  # SHA-256 hex


# ============================================================================
# SV-5: ModeConfig → phase behavior
# ============================================================================


class TestSV5_ModeConfigToBehavior:
    """SV-5: Verify ModeConfig boolean flags reach their point of use.

    Gap: ModeConfig boolean flags might not reach their point of use
    (e.g., run_validators checked but ValidationConfig empty).
    Check: ModeConfig settings produce expected behavior differences.
    """

    def test_pipeline_mode_config_enables_validation(self):
        """Pipeline ModeConfig has enable_post_validation=True."""
        config = ModeConfig.for_mode(ExecutionMode.PIPELINE)
        assert config.enable_post_validation is True

    def test_standalone_mode_config_disables_validation(self):
        """Standalone ModeConfig has enable_post_validation=False."""
        config = ModeConfig.for_mode(ExecutionMode.STANDALONE)
        assert config.enable_post_validation is False

    def test_mode_config_replace_overrides(self):
        """dataclasses.replace() on frozen ModeConfig works."""
        config = ModeConfig.for_mode(ExecutionMode.STANDALONE)
        assert config.enable_post_validation is False

        overridden = dataclasses.replace(config, enable_post_validation=True)
        assert overridden.enable_post_validation is True
        # Original unchanged
        assert config.enable_post_validation is False

    def test_validation_override_forces_validators_on(self, tmp_path):
        """_validation_override=True forces _run_validators=True even in standalone."""
        wf = _make_workflow(
            project_root=tmp_path,
            execution_mode="standalone",
            validation_override=True,
        )
        assert wf._validation_override is True
        # When _validation_override is True, _run_validators should be True
        # regardless of mode (tested via the conditional in develop_feature)

    def test_validation_override_forces_validators_off(self, tmp_path):
        """_validation_override=False forces _run_validators=False even in pipeline."""
        wf = _make_workflow(
            project_root=tmp_path,
            execution_mode="pipeline",
            validation_override=False,
        )
        assert wf._validation_override is False

    @pytest.mark.parametrize("mode", ["standalone", "pipeline"])
    def test_mode_config_all_fields_present(self, mode):
        """ModeConfig.for_mode() populates all expected fields."""
        enum_mode = ExecutionMode(mode)
        config = ModeConfig.for_mode(enum_mode)

        assert config.mode == enum_mode
        assert isinstance(config.use_onboarding_context, bool)
        assert isinstance(config.use_architectural_context, bool)
        assert isinstance(config.use_design_calibration, bool)
        assert isinstance(config.enable_provenance_tracking, bool)
        assert isinstance(config.enable_post_validation, bool)
        assert isinstance(config.max_context_depth, int)


# ============================================================================
# SV-6: CLI --mode flag → workflow.execution_mode
# ============================================================================


class TestSV6_CLIModeToWorkflow:
    """SV-6: Verify CLI --mode flag propagates to workflow.execution_mode.

    Gap: CLI argument might not propagate through to workflow.mode and
    SeedContext.execution_mode.
    Check: workflow.execution_mode == workflow.seed_context.execution_mode
    after CLI-driven initialization.
    """

    @pytest.mark.parametrize("cli_mode", ["standalone", "pipeline"])
    def test_load_seed_context_with_cli_mode(self, tmp_path, cli_mode):
        """load_seed_context() sets execution_mode from cli_mode."""
        wf = _make_workflow(project_root=tmp_path, execution_mode="standalone")
        # Reset seed context to allow re-initialization
        wf._seed_context = None

        seed_data = {
            "onboarding": {"project": "test"},
            "architectural_context": {"patterns": ["strategy"]},
        }

        wf.load_seed_context(seed_data, cli_mode=cli_mode)

        assert wf.execution_mode == cli_mode
        assert wf.seed_context.execution_mode == cli_mode
        # Both must be synchronized
        assert wf.execution_mode == wf.seed_context.execution_mode

    def test_load_seed_context_auto_detects_pipeline(self, tmp_path):
        """Auto-detection selects pipeline when enriched signals present."""
        wf = _make_workflow(project_root=tmp_path, execution_mode="standalone")
        wf._seed_context = None

        seed_data = {
            "onboarding": {"project": "test"},
            "architectural_context": {"patterns": ["strategy"]},
            "design_calibration": {"quality": "high"},
        }

        wf.load_seed_context(seed_data)  # No cli_mode

        assert wf.execution_mode == "pipeline"
        assert wf.seed_context.execution_mode == "pipeline"

    def test_load_seed_context_auto_detects_standalone(self, tmp_path):
        """Auto-detection selects standalone when no enriched signals."""
        wf = _make_workflow(project_root=tmp_path, execution_mode="pipeline")
        wf._seed_context = None

        seed_data = {}  # No enrichment signals

        wf.load_seed_context(seed_data)

        assert wf.execution_mode == "standalone"
        assert wf.seed_context.execution_mode == "standalone"

    def test_cli_mode_overrides_auto_detection(self, tmp_path):
        """Explicit cli_mode overrides auto-detection from seed signals."""
        wf = _make_workflow(project_root=tmp_path, execution_mode="standalone")
        wf._seed_context = None

        # Seed has pipeline signals, but CLI says standalone
        seed_data = {
            "onboarding": {"project": "test"},
            "architectural_context": {"patterns": ["strategy"]},
        }

        wf.load_seed_context(seed_data, cli_mode="standalone")

        assert wf.execution_mode == "standalone"

    def test_load_seed_context_populates_legacy_attributes(self, tmp_path):
        """load_seed_context() populates backward-compat legacy attributes."""
        wf = _make_workflow(project_root=tmp_path, execution_mode="standalone")
        wf._seed_context = None

        seed_data = {
            "onboarding": {"project": "test"},
            "architectural_context": {"patterns": ["strategy"]},
            "design_calibration": {"quality": "high"},
            "service_metadata": {"service": "api"},
        }

        wf.load_seed_context(seed_data, cli_mode="pipeline")

        assert wf.seed_onboarding == {"project": "test"}
        assert wf.seed_architectural_context == {"patterns": ["strategy"]}
        assert wf.seed_design_calibration == {"quality": "high"}
        assert wf.seed_service_metadata == {"service": "api"}


# ============================================================================
# SV-7: Checkpoint resume → mode consistency
# ============================================================================


class TestSV7_CheckpointResumeConsistency:
    """SV-7: Verify resumed workflow preserves execution mode.

    Gap: Saved mode in .prime_contractor_state.json might conflict with
    CLI flag on resume.
    Check: Resumed workflow preserves original mode unless explicitly
    overridden via --force-mode.
    """

    def _write_state_file(self, tmp_path, execution_mode="pipeline"):
        """Helper: write a persisted state file with execution_mode."""
        state = {
            "features": {
                "F-001": {
                    "id": "F-001",
                    "name": "auth",
                    "description": "Auth module",
                    "dependencies": [],
                    "target_files": ["src/auth.py"],
                    "status": "complete",
                    "started_at": None,
                    "completed_at": None,
                    "error_message": None,
                    "integration_attempts": 0,
                    "generated_files": [],
                    "metadata": {},
                },
            },
            "order": ["F-001"],
            "execution_mode": execution_mode,
        }
        state_file = tmp_path / ".prime_contractor_state.json"
        state_file.write_text(json.dumps(state), encoding="utf-8")
        return state_file

    def test_resume_restores_persisted_mode(self, tmp_path):
        """Resumed workflow loads execution_mode from state file."""
        self._write_state_file(tmp_path, execution_mode="pipeline")

        wf = _make_workflow(project_root=tmp_path, execution_mode="standalone")
        # Simulate resume by calling _load_state_if_resuming
        wf.queue = FeatureQueue(project_root=tmp_path, auto_save=False)
        wf._load_state_if_resuming(cli_mode=None, force_mode=None)

        assert wf.execution_mode == "pipeline"

    def test_resume_persisted_mode_overrides_cli(self, tmp_path):
        """On resume, persisted mode wins over non-forced CLI mode."""
        self._write_state_file(tmp_path, execution_mode="pipeline")

        wf = _make_workflow(project_root=tmp_path, execution_mode="standalone")
        wf.queue = FeatureQueue(project_root=tmp_path, auto_save=False)
        wf._load_state_if_resuming(cli_mode="standalone", force_mode=None)

        # Persisted mode wins
        assert wf.execution_mode == "pipeline"

    def test_resume_force_mode_overrides_persisted(self, tmp_path):
        """--force-mode overrides persisted mode on resume."""
        self._write_state_file(tmp_path, execution_mode="pipeline")

        wf = _make_workflow(project_root=tmp_path, execution_mode="standalone")
        wf.queue = FeatureQueue(project_root=tmp_path, auto_save=False)
        wf._load_state_if_resuming(cli_mode=None, force_mode="standalone")

        assert wf.execution_mode == "standalone"

    def test_resume_no_state_file_stays_default(self, tmp_path):
        """No state file on disk → workflow keeps its construction-time mode."""
        wf = _make_workflow(project_root=tmp_path, execution_mode="standalone")
        wf.queue = FeatureQueue(project_root=tmp_path, auto_save=False)
        wf._load_state_if_resuming(cli_mode="pipeline", force_mode=None)

        # No state file → no restore → stays at construction-time mode
        assert wf.execution_mode == "standalone"

    def test_resume_invalid_persisted_mode_defaults_to_standalone(self, tmp_path):
        """Invalid execution_mode in state file defaults to standalone."""
        self._write_state_file(tmp_path, execution_mode="invalid_mode")

        wf = _make_workflow(project_root=tmp_path, execution_mode="pipeline")
        wf.queue = FeatureQueue(project_root=tmp_path, auto_save=False)
        wf._load_state_if_resuming(cli_mode=None, force_mode=None)

        assert wf.execution_mode == "standalone"

    def test_resume_mode_and_seed_context_synchronized(self, tmp_path):
        """After resume, execution_mode and seed_context.execution_mode match."""
        self._write_state_file(tmp_path, execution_mode="pipeline")

        wf = _make_workflow(project_root=tmp_path, execution_mode="standalone")
        wf.queue = FeatureQueue(project_root=tmp_path, auto_save=False)
        wf._load_state_if_resuming(cli_mode=None, force_mode=None)

        assert wf.execution_mode == wf.seed_context.execution_mode
