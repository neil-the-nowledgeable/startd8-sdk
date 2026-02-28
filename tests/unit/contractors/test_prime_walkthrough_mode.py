"""Tests for PrimeContractor walkthrough mode (prompt persistence without LLM calls)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from startd8.contractors.prime_contractor import PrimeContractorWorkflow
from startd8.contractors.queue import FeatureSpec, FeatureStatus
from startd8.contractors.protocols import CodeGenerator, GenerationResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeCodeGenerator:
    """Stub code generator that tracks whether generate() was called."""

    def __init__(self) -> None:
        self.generate_called = False
        self.output_dir = None
        self.lead_agent = "mock:lead-model"
        self.drafter_agent = "mock:drafter-model"

    def generate(self, **kwargs: Any) -> GenerationResult:
        self.generate_called = True
        return GenerationResult(
            success=True,
            generated_files=["gen/code.py"],
            cost_usd=0.01,
            input_tokens=100,
            output_tokens=200,
            model="mock",
        )


def _make_feature(**overrides: Any) -> FeatureSpec:
    defaults = {
        "id": "PI-001",
        "name": "Add widget module",
        "description": "Implement a widget module with proper typing.",
        "target_files": ["src/widget.py"],
        "dependencies": [],
    }
    defaults.update(overrides)
    return FeatureSpec(**defaults)


def _make_workflow(tmp_path: Path, **overrides: Any) -> PrimeContractorWorkflow:
    """Build a PrimeContractorWorkflow with walkthrough=True and mocked internals."""
    defaults = {
        "project_root": tmp_path,
        "walkthrough": True,
        "dry_run": False,
        "allow_dirty": True,
        "code_generator": FakeCodeGenerator(),
    }
    defaults.update(overrides)

    with patch.object(PrimeContractorWorkflow, "__init__", lambda self, **kw: None):
        wf = PrimeContractorWorkflow.__new__(PrimeContractorWorkflow)

    wf.project_root = defaults["project_root"]
    wf.walkthrough = defaults["walkthrough"]
    wf.dry_run = defaults["dry_run"]
    wf.allow_dirty = defaults["allow_dirty"]
    wf.code_generator = defaults["code_generator"]
    wf.force_regenerate = False
    wf.auto_commit = False
    wf.strict_checkpoints = False
    wf.max_retries = 3
    wf.auto_stash = False
    wf.check_truncation = False
    wf.max_lines_per_feature = 150
    wf.max_tokens_per_feature = 500
    wf.total_cost_usd = 0.0
    wf.total_input_tokens = 0
    wf.total_output_tokens = 0
    wf.integration_history = []
    wf.files_modified_this_session = {}
    wf.on_feature_complete = None
    wf.on_checkpoint_failed = None
    wf._current_enrichment = None
    wf._domain_checklist = None
    wf._validation_override = None
    wf.strict_validation = False
    wf.seed_onboarding = {}
    wf.seed_architectural_context = {}
    wf.seed_design_calibration = {}
    wf.seed_service_metadata = {}
    wf.seed_forward_manifest = None
    wf.plan_document_text = None
    wf._seed_context = None

    # Mock collaborators
    wf.queue = MagicMock()
    wf.instrumentor = MagicMock()
    wf.size_estimator = MagicMock()
    wf.size_estimator.estimate.return_value = MagicMock(
        lines=50, complexity="low", confidence=0.9, tokens=100,
    )
    wf.checkpoint = MagicMock()
    wf._engine = MagicMock()
    wf._prime_listener = MagicMock()
    wf._context_strategy = MagicMock()
    wf._context_strategy.mode = "standalone"
    wf._context_strategy.resolve_task_context.return_value = {
        "task_description": "test",
    }
    wf._strict_mode = False

    # Stub methods that aren't under test
    wf._save_queue_state_with_mode = MagicMock()
    wf._check_staleness = MagicMock(return_value=True)
    wf._populate_existing_files = MagicMock()
    wf._get_domain_enrichment = MagicMock(return_value=None)

    # Execution mode property
    wf._resume_mode = None

    return wf


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestWalkthroughPersistsAllPromptFiles:
    """Verify that walkthrough mode creates all expected prompt files."""

    def test_walkthrough_persists_all_prompt_files(self, tmp_path: Path) -> None:
        wf = _make_workflow(tmp_path)
        feature = _make_feature()

        wf._persist_walkthrough_prompts(feature, {"task_description": "test"})

        wt_dir = tmp_path / ".startd8" / "walkthrough" / "prime" / "PI-001"
        assert wt_dir.is_dir()

        expected_files = [
            "spec_user_prompt.md",
            "spec_system_prompt.md",
            "draft_system_prompt.md",
            "draft_user_prompt.md",
            "review_system_prompt.md",
            "review_user_prompt.md",
            "metadata.json",
        ]
        for fname in expected_files:
            fpath = wt_dir / fname
            assert fpath.exists(), f"Missing: {fname}"
            assert fpath.stat().st_size > 0, f"Empty: {fname}"


class TestWalkthroughMetadataJsonContent:
    """Verify metadata.json contains expected fields."""

    def test_walkthrough_metadata_json_content(self, tmp_path: Path) -> None:
        wf = _make_workflow(tmp_path)
        feature = _make_feature()

        wf._persist_walkthrough_prompts(feature, {"task_description": "test"})

        meta_path = tmp_path / ".startd8" / "walkthrough" / "prime" / "PI-001" / "metadata.json"
        meta = json.loads(meta_path.read_text())

        assert meta["feature_id"] == "PI-001"
        assert meta["feature_name"] == "Add widget module"
        assert meta["target_files"] == ["src/widget.py"]
        assert meta["lead_agent_spec"] == "mock:lead-model"
        assert meta["drafter_agent_spec"] == "mock:drafter-model"
        assert "context_keys" in meta
        assert "has_existing_files" in meta


class TestWalkthroughSkipsCodeGenerator:
    """Verify that generate() is never called in walkthrough mode."""

    def test_walkthrough_skips_code_generator(self, tmp_path: Path) -> None:
        wf = _make_workflow(tmp_path)
        feature = _make_feature()
        gen = wf.code_generator

        result = wf.develop_feature(feature)

        assert result is True
        assert not gen.generate_called
        assert feature.status == FeatureStatus.GENERATED


class TestWalkthroughSkipsIntegration:
    """Verify that integrate_feature() is never called in walkthrough mode."""

    def test_walkthrough_skips_integration(self, tmp_path: Path) -> None:
        wf = _make_workflow(tmp_path)
        feature = _make_feature(status=FeatureStatus.GENERATED)
        feature.generated_files = ["walkthrough/PI-001/widget.py"]

        result = wf.process_feature(feature)

        assert result is True
        wf.queue.complete_feature.assert_called_once_with("PI-001")
        wf._engine.integrate.assert_not_called()


class TestWalkthroughMarksComplete:
    """Verify that walkthrough features reach COMPLETE status via process_feature."""

    def test_walkthrough_marks_complete(self, tmp_path: Path) -> None:
        wf = _make_workflow(tmp_path)
        feature = _make_feature()

        # develop_feature -> GENERATED
        wf.develop_feature(feature)
        assert feature.status == FeatureStatus.GENERATED

        # process_feature -> COMPLETE (via queue.complete_feature mock)
        feature_gen = _make_feature(status=FeatureStatus.GENERATED)
        feature_gen.generated_files = ["walkthrough/PI-001/widget.py"]
        wf.process_feature(feature_gen)
        wf.queue.complete_feature.assert_called()


class TestWalkthroughDecomposedSkipsIntegration:
    """Verify decomposed multi-file features skip integration in walkthrough."""

    def test_walkthrough_decomposed_skips_integration(self, tmp_path: Path) -> None:
        wf = _make_workflow(tmp_path)
        feature = _make_feature(
            target_files=["src/widget.py", "src/utils.py"],
        )

        result = wf._process_decomposed_feature(feature)

        assert result is True
        # integrate_feature should NOT have been called
        wf._engine.integrate.assert_not_called()
        wf.queue.complete_feature.assert_called_once_with("PI-001")


class TestPostmortemEvaluatorScansPrimeDir:
    """Verify the walkthrough postmortem evaluator finds prompts under prime/."""

    def test_postmortem_evaluator_scans_prime_dir(self, tmp_path: Path) -> None:
        from startd8.contractors.postmortem import WalkthroughPromptEvaluator

        # Create prime walkthrough directory with a prompt file
        prime_dir = tmp_path / "prime" / "PI-001"
        prime_dir.mkdir(parents=True)
        (prime_dir / "spec_user_prompt.md").write_text(
            "# Spec Prompt\nImplement a widget module with proper typing."
        )
        (prime_dir / "draft_system_prompt.md").write_text(
            "# Draft System\nYou are a code generator."
        )

        task_dict = {
            "task_id": "PI-001",
            "title": "Add widget module",
            "description": "Implement a widget module",
            "target_files": ["src/widget.py"],
        }

        evaluator = WalkthroughPromptEvaluator()
        result = evaluator._evaluate_task(task_dict, tmp_path)

        assert len(result.prompt_files) >= 2
        assert result.prompt_quality_score > 0.0
