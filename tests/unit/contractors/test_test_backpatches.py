"""Tests for TEST phase back-patches (TP-1 through TP-6).

TP-1: QualitySpec on TEST exit contract YAML
TP-2: ValidationPhaseOutput field validator
TP-3: parameter_sources/semantic_conventions forwarded to LLMTestGenerator
TP-4: Validator timeout default aligned to 300s
TP-5: Resume cache for TEST phase
TP-6: Per-task exception handler prevents phase abort
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from startd8.contractors.context_schema import ValidationPhaseOutput
from startd8.contractors.protocols import GenerationResult

from conftest import FakeSeedTask as _FakeSeedTask


def _make_valid_test_results(
    total_passed: int = 1,
    total_failed: int = 0,
) -> dict[str, Any]:
    """Return a minimal valid test_results dict."""
    return {
        "test_plan": [],
        "total_validators": 1,
        "unique_validators": {},
        "tasks_with_tests": 1,
        "total_passed": total_passed,
        "total_failed": total_failed,
        "per_task": {"T-1": {"status": "passed", "passed": True, "validators_run": 1}},
    }


# ============================================================================
# TP-1: QualitySpec on TEST exit contract YAML
# ============================================================================


class TestTP1QualitySpecInContract:
    """Verify the contract YAML includes a quality gate on test_results."""

    def test_quality_spec_present_in_yaml(self):
        """The test exit contract should have a quality spec."""
        import yaml

        contract_path = (
            Path(__file__).resolve().parents[3]
            / "src"
            / "startd8"
            / "contractors"
            / "contracts"
            / "artisan-pipeline.contract.yaml"
        )
        with open(contract_path) as f:
            contract = yaml.safe_load(f)

        test_exit = contract["phases"]["test"]["exit"]
        test_results_req = next(
            r for r in test_exit["required"] if r["name"] == "test_results"
        )
        assert "quality" in test_results_req, "test_results should have a quality spec"
        quality = test_results_req["quality"]
        assert quality["metric"] == "total_passed"
        assert quality["threshold"] == 1
        assert quality["on_below"] == "warning"


# ============================================================================
# TP-2: ValidationPhaseOutput field validator
# ============================================================================


class TestTP2ValidationPhaseOutputValidator:
    """ValidationPhaseOutput should reject malformed test_results."""

    def test_valid_test_results_accepted(self):
        """A well-formed test_results dict should be accepted."""
        data = _make_valid_test_results()
        obj = ValidationPhaseOutput(test_results=data)
        assert obj.test_results["total_passed"] == 1

    def test_missing_required_keys_rejected(self):
        """Missing required keys should raise ValueError."""
        with pytest.raises(Exception, match="missing required keys"):
            ValidationPhaseOutput(test_results={"test_plan": []})

    def test_per_task_not_dict_rejected(self):
        """per_task must be a dict, not a list."""
        data = _make_valid_test_results()
        data["per_task"] = []
        with pytest.raises(Exception, match="per_task.*must be a dict"):
            ValidationPhaseOutput(test_results=data)

    def test_empty_dict_rejected(self):
        """An empty dict should be rejected for missing keys."""
        with pytest.raises(Exception, match="missing required keys"):
            ValidationPhaseOutput(test_results={})


# ============================================================================
# TP-3: parameter_sources/semantic_conventions forwarded to LLMTestGenerator
# ============================================================================


class TestTP3ParameterSourcesForwarding:
    """LLMTestGenerator should inject parameter_sources into the prompt."""

    def test_parameter_sources_in_prompt(self):
        from startd8.contractors.artisan_phases.test_construction import (
            DesignDocument,
            LLMTestGenerator,
        )

        gen = LLMTestGenerator(
            agent_spec="mock:mock-model",
            parameter_sources={"config_file": "settings.yaml", "env_var": "APP_PORT"},
            semantic_conventions={"trace.id": "OTel trace identifier"},
        )
        design = DesignDocument(
            feature_name="widget",
            description="A widget module",
        )
        prompt = gen._build_generation_prompt(design)
        assert "Parameter Sources" in prompt
        assert "config_file" in prompt
        assert "settings.yaml" in prompt
        assert "Semantic Conventions" in prompt
        assert "trace.id" in prompt

    def test_no_parameter_sources_no_section(self):
        from startd8.contractors.artisan_phases.test_construction import (
            DesignDocument,
            LLMTestGenerator,
        )

        gen = LLMTestGenerator(agent_spec="mock:mock-model")
        design = DesignDocument(feature_name="widget")
        prompt = gen._build_generation_prompt(design)
        assert "Parameter Sources" not in prompt
        assert "Semantic Conventions" not in prompt

    def test_phase_forwards_to_generator(self):
        """TestConstructionPhase should store parameter_sources for forwarding."""
        from startd8.contractors.artisan_phases.test_construction import (
            TestConstructionPhase,
        )

        phase = TestConstructionPhase(
            design_doc={"feature_name": "widget"},
            validate=False,
            parameter_sources={"k": "v"},
            semantic_conventions={"s": "c"},
        )
        assert phase.parameter_sources == {"k": "v"}
        assert phase.semantic_conventions == {"s": "c"}


# ============================================================================
# TP-4: Validator timeout default aligned to 300s
# ============================================================================


class TestTP4ValidatorTimeoutDefault:
    """HandlerConfig.test_timeout_seconds should default to 300."""

    def test_default_timeout_is_300(self):
        from startd8.contractors.context_seed_handlers import HandlerConfig

        config = HandlerConfig()
        assert config.test_timeout_seconds == 300


# ============================================================================
# TP-5: Resume cache for TEST phase
# ============================================================================


class TestTP5ResumeCache:
    """TEST phase resume cache: write, validate, invalidate."""

    def test_validate_test_cache_valid(self):
        """A valid cache with matching schema and tasks should return output."""
        from startd8.contractors.context_seed_handlers import (
            TestPhaseHandler,
            _CACHE_SCHEMA_VERSION,
        )

        tasks = [_FakeSeedTask(task_id="T-1"), _FakeSeedTask(task_id="T-2")]
        output = _make_valid_test_results()
        output["per_task"]["T-2"] = {"status": "passed", "passed": True, "validators_run": 1}

        saved = {
            "_cache_meta": {
                "schema_version": _CACHE_SCHEMA_VERSION,
                "created_at": "2026-02-17T00:00:00Z",
                "source_checksum": None,
                "generation_file_hashes": {},
            },
            "output": output,
        }
        result = TestPhaseHandler._validate_test_cache(
            saved, tasks, {}, source_checksum=None,
        )
        assert result is not None
        assert result["total_passed"] == 1

    def test_validate_test_cache_wrong_schema(self):
        """Cache with wrong schema_version should be rejected."""
        from startd8.contractors.context_seed_handlers import TestPhaseHandler

        saved = {
            "_cache_meta": {"schema_version": 999},
            "output": _make_valid_test_results(),
        }
        result = TestPhaseHandler._validate_test_cache(
            saved, [_FakeSeedTask()], {}, source_checksum=None,
        )
        assert result is None

    def test_validate_test_cache_missing_task(self):
        """Cache missing a current task should be rejected."""
        from startd8.contractors.context_seed_handlers import (
            TestPhaseHandler,
            _CACHE_SCHEMA_VERSION,
        )

        saved = {
            "_cache_meta": {
                "schema_version": _CACHE_SCHEMA_VERSION,
                "source_checksum": None,
                "generation_file_hashes": {},
            },
            "output": _make_valid_test_results(),  # only has T-1
        }
        tasks = [_FakeSeedTask(task_id="T-1"), _FakeSeedTask(task_id="T-99")]
        result = TestPhaseHandler._validate_test_cache(
            saved, tasks, {}, source_checksum=None,
        )
        assert result is None

    def test_validate_test_cache_checksum_mismatch(self):
        """Cache with mismatched source_checksum should be rejected."""
        from startd8.contractors.context_seed_handlers import (
            TestPhaseHandler,
            _CACHE_SCHEMA_VERSION,
        )

        saved = {
            "_cache_meta": {
                "schema_version": _CACHE_SCHEMA_VERSION,
                "source_checksum": "old_hash",
                "generation_file_hashes": {},
            },
            "output": _make_valid_test_results(),
        }
        result = TestPhaseHandler._validate_test_cache(
            saved, [_FakeSeedTask()], {}, source_checksum="new_hash",
        )
        assert result is None

    def test_validate_test_cache_gen_file_hash_mismatch(self, tmp_path):
        """Cache should be rejected when generated code changed."""
        from startd8.contractors.context_seed_handlers import (
            TestPhaseHandler,
            _CACHE_SCHEMA_VERSION,
        )

        # Write a generated file
        gen_file = tmp_path / "widget.py"
        gen_file.write_text("# original content")
        old_hash = hashlib.sha256(gen_file.read_bytes()).hexdigest()

        # Now change the file
        gen_file.write_text("# modified content")

        gen_result = GenerationResult(success=True, generated_files=[gen_file])

        saved = {
            "_cache_meta": {
                "schema_version": _CACHE_SCHEMA_VERSION,
                "source_checksum": None,
                "generation_file_hashes": {"T-1": old_hash},
            },
            "output": _make_valid_test_results(),
        }
        result = TestPhaseHandler._validate_test_cache(
            saved,
            [_FakeSeedTask()],
            {"T-1": gen_result},
            source_checksum=None,
        )
        assert result is None

    def test_force_test_config_exists(self):
        """HandlerConfig should have force_test field."""
        from startd8.contractors.context_seed_handlers import HandlerConfig

        config = HandlerConfig()
        assert config.force_test is False

        config_force = HandlerConfig(force_test=True)
        assert config_force.force_test is True


# ============================================================================
# TP-6: Per-task exception handler prevents phase abort
# ============================================================================


class TestTP6PerTaskExceptionHandler:
    """TEST phase should not abort when a single task raises."""

    def test_single_task_error_does_not_abort_phase(self):
        """If _run_validators_for_task raises, remaining tasks should still run."""
        from startd8.contractors.context_seed_handlers import (
            HandlerConfig,
            TestPhaseHandler,
        )
        from startd8.contractors.artisan_contractor import WorkflowPhase

        handler = TestPhaseHandler(handler_config=HandlerConfig())

        task_ok = _FakeSeedTask(task_id="T-ok", post_generation_validators=["python_syntax"])
        task_bad = _FakeSeedTask(task_id="T-bad", post_generation_validators=["python_syntax"])

        gen_ok = GenerationResult(success=True, generated_files=[])
        gen_bad = GenerationResult(success=True, generated_files=[])

        context = {
            "tasks": [task_bad, task_ok],
            "task_index": {"T-bad": task_bad, "T-ok": task_ok},
            "project_root": "/tmp/fake",
            "generation_results": {"T-bad": gen_bad, "T-ok": gen_ok},
        }

        # First call raises, second returns normally
        call_count = {"n": 0}
        original_run = handler._run_validators_for_task

        def mock_run(task, project_root, gen_result, service_metadata=None):
            call_count["n"] += 1
            if task.task_id == "T-bad":
                raise RuntimeError("corrupt shlex input")
            return {
                "task_id": task.task_id,
                "title": task.title,
                "domain": task.domain,
                "validators_run": 1,
                "all_passed": True,
                "results": [{"validator": "python_syntax", "passed": True}],
            }

        handler._run_validators_for_task = mock_run

        result = handler.execute(WorkflowPhase.TEST, context, dry_run=False)

        # Both tasks should have been attempted
        assert call_count["n"] == 2

        # Output should have both tasks
        output = result["output"]
        per_task = output["per_task"]
        assert "T-bad" in per_task
        assert "T-ok" in per_task
        assert per_task["T-bad"]["status"] == "error"
        assert per_task["T-bad"]["passed"] is False
        assert per_task["T-ok"]["status"] == "passed"
        assert per_task["T-ok"]["passed"] is True

        # Totals: 1 passed, 1 failed
        assert output["total_passed"] == 1
        assert output["total_failed"] == 1

    def test_error_task_has_error_field_in_test_plan(self):
        """Error entries in test_plan should have the error message."""
        from startd8.contractors.context_seed_handlers import (
            HandlerConfig,
            TestPhaseHandler,
        )
        from startd8.contractors.artisan_contractor import WorkflowPhase

        handler = TestPhaseHandler(handler_config=HandlerConfig())
        task = _FakeSeedTask(task_id="T-err", post_generation_validators=["flake8"])
        gen = GenerationResult(success=True, generated_files=[])

        context = {
            "tasks": [task],
            "task_index": {"T-err": task},
            "project_root": "/tmp/fake",
            "generation_results": {"T-err": gen},
        }

        handler._run_validators_for_task = MagicMock(
            side_effect=ValueError("bad validator config")
        )

        result = handler.execute(WorkflowPhase.TEST, context, dry_run=False)
        test_plan = result["output"]["test_plan"]
        error_entry = next(e for e in test_plan if e["task_id"] == "T-err")
        assert error_entry["status"] == "error"
        assert "bad validator config" in error_entry["error"]
