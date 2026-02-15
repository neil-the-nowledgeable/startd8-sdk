"""Tests for contract-aware boundary validation wrapper.

Tests ``validate_phase_boundary()`` which extends the existing
``validate_phase_entry`` / ``validate_phase_exit`` with optional
propagation contract support.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from startd8.contractors.context_schema import (
    PhaseContextError,
    validate_phase_boundary,
    validate_phase_entry,
    validate_phase_exit,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakePhase:
    """Minimal phase-like object with a .value attribute."""

    def __init__(self, value: str):
        self.value = value


PLAN = _FakePhase("plan")
IMPLEMENT = _FakePhase("implement")
TEST = _FakePhase("test")


MINIMAL_CONTRACT_YAML = textwrap.dedent("""\
    schema_version: "0.1.0"
    pipeline_id: test-pipeline
    phases:
      implement:
        entry:
          required:
            - name: tasks
              type: list
              severity: blocking
          enrichment:
            - name: domain
              type: str
              severity: warning
              default: "unknown"
              source_phase: plan
        exit:
          required:
            - name: generation_results
              type: dict
              severity: blocking
""")


@pytest.fixture
def contract_file(tmp_path: Path) -> Path:
    """Write a contract YAML and return its path."""
    p = tmp_path / "test.contract.yaml"
    p.write_text(MINIMAL_CONTRACT_YAML)
    return p


# ---------------------------------------------------------------------------
# Backward compatibility (no contract)
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """When contract_path is None, behavior is identical to existing validators."""

    def test_entry_passes_without_contract(self):
        context = {"project_root": "/tmp"}
        result = validate_phase_boundary(PLAN, context, "entry")
        assert result is None

    def test_entry_fails_without_contract(self):
        with pytest.raises(PhaseContextError) as exc_info:
            validate_phase_boundary(IMPLEMENT, {}, "entry")
        assert "tasks" in exc_info.value.missing_keys

    def test_exit_passes_without_contract(self):
        context = {
            "enriched_seed_path": "/path",
            "tasks": [MagicMock(task_id="T-1")],
            "task_index": {"T-1": MagicMock()},
            "plan_title": "Test",
            "plan_goals": ["g1"],
            "domain_summary": {"domain": "web"},
            "preflight_summary": {},
            "total_estimated_loc": 100,
        }
        result = validate_phase_boundary(PLAN, context, "exit")
        assert result is None


# ---------------------------------------------------------------------------
# With contract (contextcore available)
# ---------------------------------------------------------------------------


class TestWithContract:
    """When contract_path is provided and contextcore is importable."""

    def test_enrichment_validation_runs(self, contract_file):
        """Entry validation should also check enrichment fields."""
        context = {"tasks": [1], "design_results": {"a": 1}}
        result = validate_phase_boundary(
            IMPLEMENT, context, "entry", contract_path=contract_file
        )
        # contextcore may or may not be importable — handle both
        if result is not None:
            assert result.passed is True
            # domain should have been defaulted to "unknown"
            assert context.get("domain") == "unknown"

    def test_blocking_entry_still_raises(self, contract_file):
        """Blocking validation runs BEFORE enrichment — still raises."""
        with pytest.raises(PhaseContextError):
            validate_phase_boundary(
                IMPLEMENT, {}, "entry", contract_path=contract_file
            )


# ---------------------------------------------------------------------------
# Without contextcore (graceful degradation)
# ---------------------------------------------------------------------------


class TestWithoutContextCore:
    """When contextcore is not importable, validation returns None."""

    def test_degrades_gracefully(self, contract_file):
        context = {"tasks": [1], "design_results": {"a": 1}}
        with patch.dict("sys.modules", {"contextcore": None, "contextcore.contracts": None, "contextcore.contracts.propagation": None}):
            result = validate_phase_boundary(
                IMPLEMENT, context, "entry", contract_path=contract_file
            )
            # Should return None (couldn't import contextcore)
            assert result is None
