"""Tests for HandoffContract wrapping and contract file generation.

Covers:
  - wrap_handoff_in_contract() produces a valid contract (dict or model)
  - write_design_handoff() writes the contract file alongside the handoff
  - Fallback dict shape when contextcore is not installed
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from startd8.contractors.handoff import (
    DESIGN_HANDOFF_CONTRACT_FILENAME,
    DESIGN_HANDOFF_FILENAME,
    HandoffData,
    wrap_handoff_in_contract,
    write_design_handoff,
)


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def mock_validation():
    """Mock jsonschema validation to avoid jsonschema dependency."""
    with patch("startd8.contractors.handoff._validate_handoff"):
        yield


@pytest.fixture
def sample_handoff():
    return HandoffData(
        enriched_seed_path="/tmp/seed.json",
        project_root="/tmp/proj",
        output_dir="/tmp/out",
        workflow_id="wf-123",
        completed_phases=["plan", "scaffold", "design"],
        design_results={"T1": {"status": "agreed"}},
        scaffold={"directories_created": ["/tmp/proj/src"]},
        context_files=[{"path": "foo.txt", "checksum": "abc123"}],
    )


# ── wrap_handoff_in_contract ──────────────────────────────────────────


class TestWrapHandoffInContract:
    def test_produces_contract_with_correct_fields(self, sample_handoff):
        contract = wrap_handoff_in_contract(sample_handoff, project_id="proj-1")

        # Works for both model and dict
        if isinstance(contract, dict):
            assert contract["schema_version"] == "v1"
            assert contract["handoff_id"] == "wf-123"
            assert contract["from_agent"] == "artisan-design-half"
            assert contract["to_agent"] == "artisan-implement-half"
            assert contract["capability_id"] == "artisan.design-to-implement"
            assert contract["project_id"] == "proj-1"
            assert contract["status"] == "pending"
            assert contract["inputs"]["workflow_id"] == "wf-123"
            assert contract["inputs"]["context_files"][0]["checksum"] == "abc123"
            assert contract["expected_output"]["type"] == "implementation_artifacts"
            assert contract["expected_output"]["schema_ref"] == "generation-manifest.json"
        else:
            # ContextCore model path
            assert contract.handoff_id == "wf-123"
            assert contract.from_agent == "artisan-design-half"
            assert contract.to_agent == "artisan-implement-half"
            assert contract.inputs["workflow_id"] == "wf-123"

    def test_without_project_id(self, sample_handoff):
        contract = wrap_handoff_in_contract(sample_handoff)
        if isinstance(contract, dict):
            assert contract["project_id"] is None
        else:
            assert contract.project_id is None

    def test_with_trace_id(self, sample_handoff):
        contract = wrap_handoff_in_contract(
            sample_handoff, project_id="p1", trace_id="trace-abc"
        )
        if isinstance(contract, dict):
            assert contract["trace_id"] == "trace-abc"
        else:
            assert contract.trace_id == "trace-abc"


# ── Fallback when contextcore unavailable ─────────────────────────────


class TestFallbackDict:
    def test_returns_dict_when_contextcore_unavailable(self, sample_handoff):
        with patch("startd8.contractors.handoff.CONTEXTCORE_AVAILABLE", False):
            contract = wrap_handoff_in_contract(sample_handoff, project_id="proj-2")
            assert isinstance(contract, dict)
            assert contract["schema_version"] == "v1"
            assert contract["handoff_id"] == "wf-123"
            # created_at should be an ISO string
            assert isinstance(contract["created_at"], str)


# ── Contract file written alongside handoff ───────────────────────────


class TestContractFileWritten:
    def test_write_design_handoff_creates_contract_file(self, tmp_path):
        output_dir = tmp_path / "designs"
        write_design_handoff(
            output_dir=str(output_dir),
            enriched_seed_path="/tmp/seed.json",
            project_root="/tmp/proj",
            workflow_id="wf-test",
        )

        # Handoff file should exist
        handoff_file = output_dir / DESIGN_HANDOFF_FILENAME
        assert handoff_file.exists()

        # Contract file should also exist
        contract_file = output_dir / DESIGN_HANDOFF_CONTRACT_FILENAME
        assert contract_file.exists()

        data = json.loads(contract_file.read_text())
        assert data["handoff_id"] == "wf-test"
        assert data["from_agent"] == "artisan-design-half"
        assert data["to_agent"] == "artisan-implement-half"
        assert data["status"] == "pending"

    def test_contract_includes_context_files_from_handoff(self, tmp_path):
        # Create a real file so checksums can be computed
        ctx_file = tmp_path / "plan.md"
        ctx_file.write_text("# My Plan", encoding="utf-8")

        output_dir = tmp_path / "out"
        write_design_handoff(
            output_dir=str(output_dir),
            enriched_seed_path="/tmp/seed.json",
            project_root="/tmp/proj",
            workflow_id="wf-ctx",
            context_files=[{"path": str(ctx_file)}],
        )

        contract_file = output_dir / DESIGN_HANDOFF_CONTRACT_FILENAME
        data = json.loads(contract_file.read_text())
        ctx = data["inputs"]["context_files"]
        assert len(ctx) == 1
        # Checksum should have been computed by compute_context_checksums
        assert ctx[0].get("checksum") is not None
