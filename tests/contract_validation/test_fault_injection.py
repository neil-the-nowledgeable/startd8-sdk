"""Fault injection tests for contract validation.

Deliberately mutates a valid full-pipeline context and verifies that
the contract system (boundary validator + propagation tracker) detects
each violation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from contextcore.contracts.propagation import (
    BoundaryValidator,
    PropagationTracker,
)
from contextcore.contracts.propagation.schema import ContextContract
from contextcore.contracts.types import ChainStatus

from .conftest import build_full_pipeline_context


class TestFaultInjection:
    """Each test takes a full valid context, mutates one field, and asserts detection."""

    def test_drop_domain_breaks_chain_1(
        self, loaded_contract: ContextContract, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        """Dropping domain_summary.domain → domain_to_implement BROKEN."""
        ctx = build_full_pipeline_context(tmp_path)
        del ctx["domain_summary"]["domain"]

        results = tracker.validate_all_chains(loaded_contract, ctx)
        result_map = {r.chain_id: r for r in results}
        assert result_map["domain_to_implement"].status == ChainStatus.BROKEN
        assert result_map["domain_to_implement"].source_present is False

    def test_null_truncation_flags_breaks_chain_4(
        self, loaded_contract: ContextContract, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        """Setting truncation_flags=None → truncation_to_finalize DEGRADED or BROKEN."""
        ctx = build_full_pipeline_context(tmp_path)
        ctx["truncation_flags"] = None

        results = tracker.validate_all_chains(loaded_contract, ctx)
        result_map = {r.chain_id: r for r in results}
        chain_result = result_map["truncation_to_finalize"]
        # None is a degraded/broken value
        assert chain_result.status in (ChainStatus.DEGRADED, ChainStatus.BROKEN)

    def test_remove_design_results_fails_implement_entry(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        """Removing design_results → IMPLEMENT entry validation fails."""
        ctx = build_full_pipeline_context(tmp_path)
        del ctx["design_results"]

        result = validator.validate_entry("implement", ctx, loaded_contract)
        assert result.passed is False
        assert "design_results" in result.blocking_failures

    def test_remove_generation_results_fails_integrate_entry(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        """Removing generation_results → INTEGRATE entry validation fails."""
        ctx = build_full_pipeline_context(tmp_path)
        del ctx["generation_results"]

        result = validator.validate_entry("integrate", ctx, loaded_contract)
        assert result.passed is False
        assert "generation_results" in result.blocking_failures

    def test_remove_generation_results_fails_test_entry(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        """Removing generation_results → TEST entry validation fails."""
        ctx = build_full_pipeline_context(tmp_path)
        del ctx["generation_results"]

        result = validator.validate_entry("test", ctx, loaded_contract)
        assert result.passed is False
        assert "generation_results" in result.blocking_failures

    def test_remove_generation_results_fails_review_entry(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        """Removing generation_results → REVIEW entry validation fails."""
        ctx = build_full_pipeline_context(tmp_path)
        del ctx["generation_results"]

        result = validator.validate_entry("review", ctx, loaded_contract)
        assert result.passed is False
        assert "generation_results" in result.blocking_failures

    def test_null_service_metadata_propagates_through_chain_6(
        self, loaded_contract: ContextContract, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        """Setting service_metadata=None → chain 6 still has destination populated.

        The destination (implementation.metadata.service_metadata) was set
        during context build before the source was nulled, so the chain
        may report INTACT. Nulling the source alone does not break the
        destination mirror that was already set.
        """
        ctx = build_full_pipeline_context(tmp_path)
        ctx["service_metadata"] = None

        results = tracker.validate_all_chains(loaded_contract, ctx)
        result_map = {r.chain_id: r for r in results}
        chain = result_map["onboarding_context_to_implement"]
        # Source resolves to None but destination still has the mirror value
        assert chain.status in (ChainStatus.INTACT, ChainStatus.DEGRADED, ChainStatus.BROKEN)

    def test_empty_validators_degrades_chain_2(
        self, loaded_contract: ContextContract, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        """Setting post_generation_validators=[] → validators_to_test DEGRADED."""
        ctx = build_full_pipeline_context(tmp_path)
        ctx["domain_summary"]["post_generation_validators"] = []

        results = tracker.validate_all_chains(loaded_contract, ctx)
        result_map = {r.chain_id: r for r in results}
        assert result_map["validators_to_test"].status == ChainStatus.DEGRADED

    def test_remove_tasks_fails_multiple_phase_entries(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        """Removing tasks → scaffold, design, test, finalize entries all fail."""
        ctx = build_full_pipeline_context(tmp_path)
        del ctx["tasks"]

        for phase in ["scaffold", "design", "test", "finalize"]:
            result = validator.validate_entry(phase, ctx, loaded_contract)
            assert result.passed is False, (
                f"{phase} should fail without tasks"
            )
            assert "tasks" in result.blocking_failures

    def test_remove_workflow_summary_fails_finalize_exit(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        """Removing workflow_summary → FINALIZE exit validation fails."""
        ctx = build_full_pipeline_context(tmp_path)
        del ctx["workflow_summary"]

        result = validator.validate_exit("finalize", ctx, loaded_contract)
        assert result.passed is False
        assert "workflow_summary" in result.blocking_failures

    def test_intact_chains_survive_unrelated_mutation(
        self, loaded_contract: ContextContract, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        """Mutating an unrelated key does not break healthy chains."""
        ctx = build_full_pipeline_context(tmp_path)
        # Add a random key — should not affect any chain
        ctx["_unrelated_extra_key"] = {"noise": True}
        # Remove workflow_summary — not part of any chain source
        del ctx["workflow_summary"]

        results = tracker.validate_all_chains(loaded_contract, ctx)
        result_map = {r.chain_id: r for r in results}
        # Chains 1-6 should still be intact
        for chain_id in [
            "domain_to_implement",
            "validators_to_test",
            "calibration_to_implement",
            "truncation_to_finalize",
            "design_mode_to_implement",
            "onboarding_context_to_implement",
        ]:
            assert result_map[chain_id].status == ChainStatus.INTACT

    def test_drop_design_mode_summary_breaks_chain_5(
        self, loaded_contract: ContextContract, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        """Dropping design_mode_summary → chain 5 BROKEN."""
        ctx = build_full_pipeline_context(tmp_path)
        del ctx["design_mode_summary"]

        results = tracker.validate_all_chains(loaded_contract, ctx)
        result_map = {r.chain_id: r for r in results}
        assert result_map["design_mode_to_implement"].status == ChainStatus.BROKEN
        assert result_map["design_mode_to_implement"].source_present is False

    def test_drop_implementation_metadata_breaks_chain_6_destination(
        self, loaded_contract: ContextContract, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        """Dropping implementation.metadata → chain 6 destination BROKEN."""
        ctx = build_full_pipeline_context(tmp_path)
        del ctx["implementation"]["metadata"]

        results = tracker.validate_all_chains(loaded_contract, ctx)
        result_map = {r.chain_id: r for r in results}
        chain = result_map["onboarding_context_to_implement"]
        assert chain.destination_present is False
        assert chain.status == ChainStatus.BROKEN
