"""Tests for PrimeContractorWorkflowAdapter — WorkflowBase wrapper."""

import json
from unittest.mock import MagicMock, patch

import pytest

from startd8.workflows.builtin.prime_contractor_workflow import (
    PrimeContractorWorkflowAdapter,
)


@pytest.fixture
def adapter():
    return PrimeContractorWorkflowAdapter()


@pytest.fixture
def seed_file(tmp_path):
    """Create a minimal seed JSON file."""
    seed = {
        "tasks": [
            {
                "task_id": "T-001",
                "title": "Add widget",
                "config": {
                    "task_description": "Add a widget component",
                    "context": {"target_files": ["src/widget.py"]},
                },
            }
        ],
    }
    path = tmp_path / "seed.json"
    path.write_text(json.dumps(seed))
    return path


class TestMetadata:
    def test_workflow_id(self, adapter):
        assert adapter.metadata.workflow_id == "prime-contractor"

    def test_name(self, adapter):
        assert adapter.metadata.name == "Prime Contractor Workflow"

    def test_inputs_include_seed_path(self, adapter):
        names = [i.name for i in adapter.metadata.inputs]
        assert "seed_path" in names

    def test_inputs_include_micro_prime(self, adapter):
        names = [i.name for i in adapter.metadata.inputs]
        assert "micro_prime" in names

    def test_seed_path_required(self, adapter):
        for inp in adapter.metadata.inputs:
            if inp.name == "seed_path":
                assert inp.required is True


class TestValidation:
    def test_missing_seed_path(self, adapter):
        result = adapter.validate_config({})
        assert not result.valid
        assert any("seed_path" in e for e in result.errors)

    def test_seed_path_not_found(self, adapter):
        result = adapter.validate_config({"seed_path": "/nonexistent/seed.json"})
        assert not result.valid
        assert any("not found" in e for e in result.errors)

    def test_valid_config(self, adapter, seed_file):
        result = adapter.validate_config({"seed_path": str(seed_file)})
        assert result.valid

    def test_invalid_project_root(self, adapter, seed_file):
        result = adapter.validate_config({
            "seed_path": str(seed_file),
            "project_root": "/nonexistent/dir",
        })
        assert not result.valid
        assert any("Project root" in e for e in result.errors)


_PCW_PATH = "startd8.contractors.prime_contractor.PrimeContractorWorkflow"
_GEN_PATH = "startd8.contractors.generators.primary_contractor.LeadContractorCodeGenerator"


def _make_mock_wf(run_return=None):
    """Build a mock PrimeContractorWorkflow with sensible defaults."""
    mock_wf = MagicMock()
    mock_wf.run.return_value = run_return or {
        "processed": 1, "succeeded": 1, "failed": 0,
        "total_cost_usd": 0.01, "total_input_tokens": 100,
        "total_output_tokens": 200, "progress": 100.0,
        "history": [],
    }
    mock_wf.queue = MagicMock()
    mock_wf._micro_prime_enabled = False
    mock_wf._original_code_generator = None
    return mock_wf


class TestExecute:
    @patch(_GEN_PATH)
    @patch(_PCW_PATH)
    def test_basic_execution(self, MockPCW, MockGen, adapter, seed_file):
        mock_wf = _make_mock_wf()
        MockPCW.return_value = mock_wf

        result = adapter._execute(
            {"seed_path": str(seed_file)}, None, None,
        )

        assert result.success
        assert result.metrics.total_cost == 0.01
        assert result.metrics.input_tokens == 100
        mock_wf.queue.add_features_from_seed.assert_called_once()
        mock_wf.load_seed_context.assert_called_once()
        mock_wf.run.assert_called_once()

    @patch(_GEN_PATH)
    @patch(_PCW_PATH)
    def test_micro_prime_enabled(self, MockPCW, MockGen, adapter, seed_file):
        mock_wf = _make_mock_wf()
        MockPCW.return_value = mock_wf

        adapter._execute(
            {"seed_path": str(seed_file), "micro_prime": True},
            None, None,
        )

        mock_wf.enable_micro_prime.assert_called_once()

    @patch(_GEN_PATH)
    @patch(_PCW_PATH)
    def test_micro_prime_model_forwarded(self, MockPCW, MockGen, adapter, seed_file):
        mock_wf = _make_mock_wf()
        MockPCW.return_value = mock_wf

        with patch(
            "startd8.micro_prime.models.MicroPrimeConfig"
        ) as MockMPC:
            mock_mp_config = MagicMock()
            MockMPC.return_value = mock_mp_config

            adapter._execute(
                {
                    "seed_path": str(seed_file),
                    "micro_prime": True,
                    "micro_prime_model": "codellama",
                },
                None, None,
            )

            MockMPC.assert_called_once_with(model="codellama")
            mock_wf.enable_micro_prime.assert_called_once_with(mock_mp_config)

    @patch(_GEN_PATH)
    @patch(_PCW_PATH)
    def test_complexity_routing_enabled(self, MockPCW, MockGen, adapter, seed_file):
        mock_wf = _make_mock_wf()
        MockPCW.return_value = mock_wf

        adapter._execute(
            {"seed_path": str(seed_file), "complexity_routing": True},
            None, None,
        )

        mock_wf.enable_complexity_routing.assert_called_once()

    @patch(_GEN_PATH)
    @patch(_PCW_PATH)
    def test_task_filter_applied(self, MockPCW, MockGen, adapter, seed_file):
        mock_feature_a = MagicMock()
        mock_feature_b = MagicMock()
        mock_wf = _make_mock_wf()
        mock_wf.queue.features = {"T-001": mock_feature_a, "T-002": mock_feature_b}
        MockPCW.return_value = mock_wf

        adapter._execute(
            {"seed_path": str(seed_file), "task_filter": "T-001"},
            None, None,
        )

        # T-002 should have been marked COMPLETE (filtered out)
        from startd8.contractors.queue import FeatureStatus
        assert mock_feature_b.status == FeatureStatus.COMPLETE
        # T-001 should NOT have been modified
        assert mock_feature_a.status != FeatureStatus.COMPLETE

    @patch(_GEN_PATH)
    @patch(_PCW_PATH)
    def test_failure_returns_error_result(self, MockPCW, MockGen, adapter, seed_file):
        MockPCW.side_effect = RuntimeError("boom")

        result = adapter._execute(
            {"seed_path": str(seed_file)}, None, None,
        )

        assert not result.success
        assert "boom" in result.error

    @patch(_GEN_PATH)
    @patch(_PCW_PATH)
    def test_failed_features_not_success(self, MockPCW, MockGen, adapter, seed_file):
        mock_wf = _make_mock_wf({
            "processed": 2, "succeeded": 1, "failed": 1,
            "total_cost_usd": 0.05, "total_input_tokens": 500,
            "total_output_tokens": 1000, "progress": 50.0,
            "history": [],
        })
        MockPCW.return_value = mock_wf

        result = adapter._execute(
            {"seed_path": str(seed_file)}, None, None,
        )

        assert not result.success

    @patch(_GEN_PATH)
    @patch(_PCW_PATH)
    def test_lead_agent_creates_generator(self, MockPCW, MockGen, adapter, seed_file):
        mock_wf = _make_mock_wf()
        MockPCW.return_value = mock_wf

        adapter._execute(
            {
                "seed_path": str(seed_file),
                "lead_agent": "anthropic:claude-sonnet-4-6",
                "drafter_agent": "openai:gpt-4.1-nano",
            },
            None, None,
        )

        MockGen.assert_called_once()
        call_kwargs = MockGen.call_args
        assert call_kwargs.kwargs.get("lead_agent") == "anthropic:claude-sonnet-4-6"
        assert call_kwargs.kwargs.get("drafter_agent") == "openai:gpt-4.1-nano"


class TestRegistration:
    def test_registered_via_builtin(self):
        from startd8.workflows.registry import WorkflowRegistry
        WorkflowRegistry.clear()
        WorkflowRegistry._register_builtin_workflows()
        wf = WorkflowRegistry.get_workflow("prime-contractor")
        assert wf is not None
        assert wf.metadata.workflow_id == "prime-contractor"


class TestCLIFlags:
    def test_cli_flags_populate_config(self):
        """Verify CLI flags inject into config dict correctly."""
        from typer.testing import CliRunner
        from startd8.cli import app

        runner = CliRunner()
        # Use a non-existent workflow to verify flags parse without error.
        # The run will fail at validation, but we just want to verify flag parsing.
        result = runner.invoke(app, [
            "workflow", "run", "prime-contractor",
            "--seed", "/tmp/nonexistent-seed.json",
            "--micro-prime",
            "--cost-budget", "5.0",
        ])
        # Should fail with seed file not found (validation error), not a CLI parse error
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "failed" in result.output.lower()
