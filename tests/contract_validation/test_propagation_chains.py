"""Tests for the 6 propagation chains declared in artisan-pipeline.contract.yaml.

Each chain is tested for INTACT, DEGRADED, and BROKEN status using
``PropagationTracker.check_chain()`` and ``validate_all_chains()``.

Known design tensions documented inline:
- Chain 5 (design_mode_to_implement): source uses wildcard ``*`` in
  ``design_results.*.design_mode`` — ``_resolve_field()`` treats ``*``
  as a literal dict key, not a glob.
- Chains 5-6: destination fields use ``DevelopmentChunk.metadata.*``
  which reference runtime object attributes, not context dict paths.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from contextcore.contracts.propagation import PropagationTracker
from contextcore.contracts.propagation.schema import ContextContract
from contextcore.contracts.types import ChainStatus

from .conftest import build_full_pipeline_context


def _get_chain(contract: ContextContract, chain_id: str):
    """Helper: find a chain spec by ID or fail."""
    for chain in contract.propagation_chains:
        if chain.chain_id == chain_id:
            return chain
    pytest.fail(f"Chain {chain_id!r} not found in contract")


# ============================================================================
# Chain 1: domain_to_implement
# ============================================================================


class TestDomainToImplementChain:
    """domain_summary.domain flows from PLAN → IMPLEMENT."""

    def test_intact_when_domain_populated(
        self, loaded_contract: ContextContract, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        ctx = build_full_pipeline_context(tmp_path)
        assert ctx["domain_summary"]["domain"] == "web_application"
        chain = _get_chain(loaded_contract, "domain_to_implement")
        result = tracker.check_chain(chain, ctx)
        assert result.status == ChainStatus.INTACT
        assert result.source_present is True
        assert result.destination_present is True

    def test_degraded_when_domain_unknown(
        self, loaded_contract: ContextContract, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        ctx = build_full_pipeline_context(tmp_path)
        ctx["domain_summary"]["domain"] = "unknown"
        chain = _get_chain(loaded_contract, "domain_to_implement")
        result = tracker.check_chain(chain, ctx)
        # "unknown" is a degraded value — tracker checks degraded values
        # (None, '', 'unknown', [], {}) before running verification expression.
        assert result.status == ChainStatus.DEGRADED

    def test_broken_when_domain_absent(
        self, loaded_contract: ContextContract, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        ctx = build_full_pipeline_context(tmp_path)
        del ctx["domain_summary"]["domain"]
        chain = _get_chain(loaded_contract, "domain_to_implement")
        result = tracker.check_chain(chain, ctx)
        assert result.status == ChainStatus.BROKEN
        assert result.source_present is False

    def test_broken_when_domain_empty_string(
        self, loaded_contract: ContextContract, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        ctx = build_full_pipeline_context(tmp_path)
        ctx["domain_summary"]["domain"] = ""
        chain = _get_chain(loaded_contract, "domain_to_implement")
        result = tracker.check_chain(chain, ctx)
        # Empty string is a degraded/broken value
        assert result.status in (ChainStatus.DEGRADED, ChainStatus.BROKEN)


# ============================================================================
# Chain 2: validators_to_test
# ============================================================================


class TestValidatorsToTestChain:
    """post_generation_validators flows from PLAN → IMPLEMENT → TEST."""

    def test_intact_when_validators_populated(
        self, loaded_contract: ContextContract, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        ctx = build_full_pipeline_context(tmp_path)
        assert ctx["domain_summary"]["post_generation_validators"] == ["ruff", "mypy"]
        chain = _get_chain(loaded_contract, "validators_to_test")
        result = tracker.check_chain(chain, ctx)
        assert result.status == ChainStatus.INTACT
        assert result.source_present is True
        assert result.destination_present is True

    def test_degraded_when_validators_empty(
        self, loaded_contract: ContextContract, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        ctx = build_full_pipeline_context(tmp_path)
        ctx["domain_summary"]["post_generation_validators"] = []
        chain = _get_chain(loaded_contract, "validators_to_test")
        result = tracker.check_chain(chain, ctx)
        # Empty list is a degraded value ([], {}, None, "" all degrade)
        assert result.status == ChainStatus.DEGRADED

    def test_broken_when_validators_absent(
        self, loaded_contract: ContextContract, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        ctx = build_full_pipeline_context(tmp_path)
        del ctx["domain_summary"]["post_generation_validators"]
        chain = _get_chain(loaded_contract, "validators_to_test")
        result = tracker.check_chain(chain, ctx)
        assert result.status == ChainStatus.BROKEN
        assert result.source_present is False

    def test_waypoint_at_implement(
        self, loaded_contract: ContextContract, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        """Chain 2 declares a waypoint at implement phase."""
        ctx = build_full_pipeline_context(tmp_path)
        chain = _get_chain(loaded_contract, "validators_to_test")
        assert len(chain.waypoints) == 1
        assert chain.waypoints[0].phase == "implement"
        result = tracker.check_chain(chain, ctx)
        assert result.waypoints_present[0] is True


# ============================================================================
# Chain 3: calibration_to_implement
# ============================================================================


class TestCalibrationToImplementChain:
    """design_calibration flows from PLAN → IMPLEMENT (advisory severity)."""

    def test_intact_when_calibration_populated(
        self, loaded_contract: ContextContract, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        ctx = build_full_pipeline_context(tmp_path)
        assert ctx["design_calibration"] == {"max_output_tokens": 4096}
        chain = _get_chain(loaded_contract, "calibration_to_implement")
        result = tracker.check_chain(chain, ctx)
        assert result.status == ChainStatus.INTACT

    def test_degraded_when_calibration_empty(
        self, loaded_contract: ContextContract, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        ctx = build_full_pipeline_context(tmp_path)
        ctx["design_calibration"] = {}
        chain = _get_chain(loaded_contract, "calibration_to_implement")
        result = tracker.check_chain(chain, ctx)
        assert result.status == ChainStatus.DEGRADED

    def test_broken_when_calibration_absent(
        self, loaded_contract: ContextContract, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        ctx = build_full_pipeline_context(tmp_path)
        del ctx["design_calibration"]
        chain = _get_chain(loaded_contract, "calibration_to_implement")
        result = tracker.check_chain(chain, ctx)
        assert result.status == ChainStatus.BROKEN


# ============================================================================
# Chain 4: truncation_to_finalize
# ============================================================================


class TestTruncationToFinalizeChain:
    """truncation_flags flow IMPLEMENT → TEST → REVIEW → FINALIZE."""

    def test_intact_when_flags_populated(
        self, loaded_contract: ContextContract, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        ctx = build_full_pipeline_context(tmp_path)
        assert "truncation_flags" in ctx
        chain = _get_chain(loaded_contract, "truncation_to_finalize")
        result = tracker.check_chain(chain, ctx)
        assert result.status == ChainStatus.INTACT

    def test_broken_when_flags_absent(
        self, loaded_contract: ContextContract, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        ctx = build_full_pipeline_context(tmp_path)
        del ctx["truncation_flags"]
        chain = _get_chain(loaded_contract, "truncation_to_finalize")
        result = tracker.check_chain(chain, ctx)
        assert result.status == ChainStatus.BROKEN
        assert result.source_present is False

    def test_waypoints_at_test_and_review(
        self, loaded_contract: ContextContract, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        """Chain 4 declares waypoints at test and review phases."""
        ctx = build_full_pipeline_context(tmp_path)
        chain = _get_chain(loaded_contract, "truncation_to_finalize")
        assert len(chain.waypoints) == 2
        assert chain.waypoints[0].phase == "test"
        assert chain.waypoints[1].phase == "review"
        result = tracker.check_chain(chain, ctx)
        assert all(result.waypoints_present)


# ============================================================================
# Chain 5: design_mode_to_implement
# ============================================================================


class TestDesignModeToImplementChain:
    """design_results.*.design_mode → DevelopmentChunk.metadata.design_mode.

    KNOWN DESIGN TENSION: The source field uses a wildcard ``*`` that
    ``_resolve_field()`` treats as a literal dict key (not a glob), and
    the destination references a runtime object attribute path, not a
    context dict path.  Both will report BROKEN in their current form.
    """

    def test_current_behavior_is_broken_due_to_wildcard_source(
        self, loaded_contract: ContextContract, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        """Document that _resolve_field treats '*' as a literal key."""
        ctx = build_full_pipeline_context(tmp_path)
        chain = _get_chain(loaded_contract, "design_mode_to_implement")
        result = tracker.check_chain(chain, ctx)
        # Source field "design_results.*.design_mode" won't resolve because
        # there's no literal key "*" in design_results.
        assert result.source_present is False
        assert result.status == ChainStatus.BROKEN

    def test_logical_intent_works_with_concrete_task_path(
        self, loaded_contract: ContextContract, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        """Prove the *intent* works if we use a concrete task ID path."""
        ctx = build_full_pipeline_context(tmp_path)
        chain = _get_chain(loaded_contract, "design_mode_to_implement")
        # Manually inject the source at a resolvable path to prove intent.
        # If the contract used "design_results.T1.design_mode" it would resolve.
        from contextcore.contracts.propagation.tracker import _resolve_field

        present, val = _resolve_field(ctx, "design_results.T1.design_mode")
        assert present is True
        assert val in ("create", "update")

    def test_destination_also_broken_due_to_object_path(
        self, loaded_contract: ContextContract, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        """Destination DevelopmentChunk.metadata.design_mode is not a dict path."""
        ctx = build_full_pipeline_context(tmp_path)
        chain = _get_chain(loaded_contract, "design_mode_to_implement")
        result = tracker.check_chain(chain, ctx)
        assert result.destination_present is False


# ============================================================================
# Chain 6: onboarding_context_to_implement
# ============================================================================


class TestOnboardingContextToImplementChain:
    """service_metadata flows PLAN → IMPLEMENT (DevelopmentChunk.metadata.service_metadata).

    KNOWN DESIGN TENSION: destination uses DevelopmentChunk.metadata.*
    object path — won't resolve as a context dict path.
    """

    def test_source_present_when_metadata_populated(
        self, loaded_contract: ContextContract, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        ctx = build_full_pipeline_context(tmp_path)
        chain = _get_chain(loaded_contract, "onboarding_context_to_implement")
        result = tracker.check_chain(chain, ctx)
        assert result.source_present is True

    def test_destination_broken_due_to_object_path(
        self, loaded_contract: ContextContract, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        """Destination DevelopmentChunk.metadata.service_metadata is not a dict path."""
        ctx = build_full_pipeline_context(tmp_path)
        chain = _get_chain(loaded_contract, "onboarding_context_to_implement")
        result = tracker.check_chain(chain, ctx)
        assert result.destination_present is False
        assert result.status == ChainStatus.BROKEN

    def test_broken_when_metadata_absent(
        self, loaded_contract: ContextContract, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        ctx = build_full_pipeline_context(tmp_path)
        del ctx["service_metadata"]
        chain = _get_chain(loaded_contract, "onboarding_context_to_implement")
        result = tracker.check_chain(chain, ctx)
        assert result.source_present is False
        assert result.status == ChainStatus.BROKEN

    def test_source_degraded_when_metadata_none(
        self, loaded_contract: ContextContract, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        ctx = build_full_pipeline_context(tmp_path)
        ctx["service_metadata"] = None
        chain = _get_chain(loaded_contract, "onboarding_context_to_implement")
        result = tracker.check_chain(chain, ctx)
        # None at source level — _resolve_field returns (True, None)
        # but value is empty → DEGRADED or BROKEN depending on impl
        assert result.status in (ChainStatus.DEGRADED, ChainStatus.BROKEN)


# ============================================================================
# Aggregate: validate_all_chains
# ============================================================================


class TestValidateAllChains:
    """Run validate_all_chains() on a full context and verify all 6 statuses."""

    def test_all_chains_present_in_contract(self, loaded_contract: ContextContract) -> None:
        """Verify the contract declares exactly 6 propagation chains."""
        assert len(loaded_contract.propagation_chains) == 6
        chain_ids = {c.chain_id for c in loaded_contract.propagation_chains}
        assert chain_ids == {
            "domain_to_implement",
            "validators_to_test",
            "calibration_to_implement",
            "truncation_to_finalize",
            "design_mode_to_implement",
            "onboarding_context_to_implement",
        }

    def test_validate_all_returns_6_results(
        self, loaded_contract: ContextContract, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        ctx = build_full_pipeline_context(tmp_path)
        results = tracker.validate_all_chains(loaded_contract, ctx)
        assert len(results) == 6

    def test_first_four_chains_intact(
        self, loaded_contract: ContextContract, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        """Chains 1-4 (simple dict paths) should be INTACT with full context."""
        ctx = build_full_pipeline_context(tmp_path)
        results = tracker.validate_all_chains(loaded_contract, ctx)
        result_map = {r.chain_id: r for r in results}
        for chain_id in [
            "domain_to_implement",
            "validators_to_test",
            "calibration_to_implement",
            "truncation_to_finalize",
        ]:
            assert result_map[chain_id].status == ChainStatus.INTACT, (
                f"{chain_id} expected INTACT, got {result_map[chain_id].status}"
            )

    def test_chains_5_and_6_broken_due_to_path_resolution(
        self, loaded_contract: ContextContract, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        """Chains 5-6 are BROKEN because they use wildcard/object paths."""
        ctx = build_full_pipeline_context(tmp_path)
        results = tracker.validate_all_chains(loaded_contract, ctx)
        result_map = {r.chain_id: r for r in results}
        # Chain 5: wildcard source path
        assert result_map["design_mode_to_implement"].status == ChainStatus.BROKEN
        # Chain 6: object path destination
        assert result_map["onboarding_context_to_implement"].status == ChainStatus.BROKEN
