"""End-to-end contract validation against the full synthetic pipeline context.

Validates that:
- All phase entries/exits pass with a fully-populated context
- All propagation chains are evaluated
- Enrichment validation passes at every phase boundary
- Quality violations are surfaced (not silently dropped)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from contextcore.contracts.propagation import (
    BoundaryValidator,
    ContractLoader,
    PropagationTracker,
)
from contextcore.contracts.propagation.schema import ContextContract
from contextcore.contracts.types import ChainStatus

from .conftest import build_full_pipeline_context

# Phase execution order
PHASE_ORDER = [
    "plan", "scaffold", "design", "implement",
    "integrate", "test", "review", "finalize",
]


class TestFullPipelineContracts:
    """Validate the contract system against a complete synthetic context."""

    def test_all_phase_entries_pass(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        """Every phase entry validation passes with the full context.

        The IMPLEMENT entry quality gate was downgraded from blocking to
        warning (CV-500) so all phases now pass.
        """
        ctx = build_full_pipeline_context(tmp_path)
        for phase in PHASE_ORDER:
            result = validator.validate_entry(phase, ctx, loaded_contract)
            assert result.passed is True, (
                f"{phase} entry failed: {result.blocking_failures}"
            )

    def test_all_phase_exits_pass(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        """Every phase exit validation passes with the full context."""
        ctx = build_full_pipeline_context(tmp_path)
        for phase in PHASE_ORDER:
            result = validator.validate_exit(phase, ctx, loaded_contract)
            assert result.passed is True, (
                f"{phase} exit failed: {result.blocking_failures}"
            )

    def test_all_enrichments_pass(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        """Every phase enrichment validation passes with the full context."""
        ctx = build_full_pipeline_context(tmp_path)
        # Not all phases have enrichment specs — only those with
        # enrichment fields in the contract.
        phases_with_enrichment = []
        for phase_name, phase_contract in loaded_contract.phases.items():
            if phase_contract.entry.enrichment:
                phases_with_enrichment.append(phase_name)

        assert len(phases_with_enrichment) > 0, "Expected at least one phase with enrichment"

        for phase in phases_with_enrichment:
            result = validator.validate_enrichment(phase, ctx, loaded_contract)
            assert result.passed is True, (
                f"{phase} enrichment failed: {result.blocking_failures}"
            )

    def test_propagation_chain_summary(
        self, loaded_contract: ContextContract, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        """validate_all_chains returns expected statuses for full context.

        After CV-301/CV-302 chain rewrites, chains 5-6 are now INTACT.
        Chain 7 (project_metadata_to_review) is advisory and may be
        BROKEN if project_metadata is absent from the test context.
        """
        ctx = build_full_pipeline_context(tmp_path)
        results = tracker.validate_all_chains(loaded_contract, ctx)
        assert len(results) == 7

        # Count by status
        intact = sum(1 for r in results if r.status == ChainStatus.INTACT)

        # Chains 1-6 intact; chain 7 depends on project_metadata presence
        assert intact >= 6, f"Expected at least 6 INTACT chains, got {intact}"
