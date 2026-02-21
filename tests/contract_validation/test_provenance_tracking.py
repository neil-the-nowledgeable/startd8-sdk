"""Tests for PropagationTracker provenance stamping and retrieval.

Validates that:
- stamp() records origin_phase, set_at (ISO 8601), and value_hash (sha256[:8])
- Provenance survives context mutations (add/remove other keys)
- _cc_propagation key is present after stamping
- All 6 chain source fields can be stamped and retrieved
- stamp_evaluation() adds evaluated_by and evaluation_score
- stamp_evaluation() without prior stamp() creates minimal provenance
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from contextcore.contracts.propagation import PropagationTracker
from contextcore.contracts.propagation.tracker import PROVENANCE_KEY

from .conftest import build_full_pipeline_context


class TestStampBasics:

    def test_stamp_records_origin_phase(self, tracker: PropagationTracker) -> None:
        ctx: dict[str, Any] = {"domain": "web_application"}
        tracker.stamp(ctx, "plan", "domain", "web_application")

        prov = tracker.get_provenance(ctx, "domain")
        assert prov is not None
        assert prov.origin_phase == "plan"

    def test_stamp_records_iso8601_timestamp(self, tracker: PropagationTracker) -> None:
        ctx: dict[str, Any] = {"domain": "web_application"}
        tracker.stamp(ctx, "plan", "domain", "web_application")

        prov = tracker.get_provenance(ctx, "domain")
        assert prov is not None
        # ISO 8601 format: YYYY-MM-DDTHH:MM:SS
        assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", prov.set_at)

    def test_stamp_records_value_hash(self, tracker: PropagationTracker) -> None:
        ctx: dict[str, Any] = {"domain": "web_application"}
        tracker.stamp(ctx, "plan", "domain", "web_application")

        prov = tracker.get_provenance(ctx, "domain")
        assert prov is not None
        # SHA256 truncated to 8 chars
        assert len(prov.value_hash) == 8
        assert re.match(r"[0-9a-f]{8}", prov.value_hash)

    def test_provenance_key_in_context(self, tracker: PropagationTracker) -> None:
        ctx: dict[str, Any] = {}
        tracker.stamp(ctx, "plan", "some_field", "some_value")
        assert PROVENANCE_KEY in ctx
        assert isinstance(ctx[PROVENANCE_KEY], dict)


class TestProvenanceSurvival:

    def test_provenance_survives_adding_keys(self, tracker: PropagationTracker) -> None:
        ctx: dict[str, Any] = {"domain": "web_application"}
        tracker.stamp(ctx, "plan", "domain", "web_application")

        # Add unrelated keys
        ctx["extra_key"] = "extra_value"
        ctx["another_key"] = [1, 2, 3]

        prov = tracker.get_provenance(ctx, "domain")
        assert prov is not None
        assert prov.origin_phase == "plan"

    def test_provenance_survives_removing_other_keys(self, tracker: PropagationTracker) -> None:
        ctx: dict[str, Any] = {"domain": "web_app", "other": "val"}
        tracker.stamp(ctx, "plan", "domain", "web_app")

        del ctx["other"]

        prov = tracker.get_provenance(ctx, "domain")
        assert prov is not None
        assert prov.origin_phase == "plan"


class TestStampAllChainSources:
    """Stamp all 6 chain source fields and verify retrieval."""

    def test_stamp_and_retrieve_all_sources(
        self, tracker: PropagationTracker, tmp_path: Path,
    ) -> None:
        ctx = build_full_pipeline_context(tmp_path)

        # Stamp the 4 chain sources that use simple dict paths
        chain_sources = [
            ("plan", "domain_summary.domain", ctx["domain_summary"]["domain"]),
            ("plan", "domain_summary.post_generation_validators", ctx["domain_summary"]["post_generation_validators"]),
            ("plan", "design_calibration", ctx["design_calibration"]),
            ("implement", "truncation_flags", ctx["truncation_flags"]),
        ]
        for phase, field_path, value in chain_sources:
            tracker.stamp(ctx, phase, field_path, value)

        for phase, field_path, _value in chain_sources:
            prov = tracker.get_provenance(ctx, field_path)
            assert prov is not None, f"No provenance for {field_path}"
            assert prov.origin_phase == phase


class TestStampEvaluation:

    def test_stamp_evaluation_adds_evaluator(self, tracker: PropagationTracker) -> None:
        ctx: dict[str, Any] = {"design_doc": "...content..."}
        tracker.stamp(ctx, "design", "design_doc", "...content...")
        eval_result = tracker.stamp_evaluation(ctx, "design_doc", "model:claude-sonnet", score=85.0)

        assert eval_result.evaluator == "model:claude-sonnet"
        assert eval_result.score == 85.0

        prov = tracker.get_provenance(ctx, "design_doc")
        assert prov is not None
        assert prov.evaluated_by == "model:claude-sonnet"
        assert prov.evaluation_score == 85.0

    def test_stamp_evaluation_without_prior_stamp(self, tracker: PropagationTracker) -> None:
        """stamp_evaluation() without prior stamp() creates minimal provenance."""
        ctx: dict[str, Any] = {}
        eval_result = tracker.stamp_evaluation(ctx, "unstamped_field", "human:reviewer", score=90.0)

        assert eval_result.evaluator == "human:reviewer"
        assert eval_result.score == 90.0

        prov = tracker.get_provenance(ctx, "unstamped_field")
        assert prov is not None
        assert prov.origin_phase == "unknown"
        assert prov.evaluated_by == "human:reviewer"

    def test_stamp_evaluation_without_score(self, tracker: PropagationTracker) -> None:
        ctx: dict[str, Any] = {"field": "value"}
        tracker.stamp(ctx, "plan", "field", "value")
        eval_result = tracker.stamp_evaluation(ctx, "field", "human:bob")

        assert eval_result.score is None
        prov = tracker.get_provenance(ctx, "field")
        assert prov is not None
        assert prov.evaluated_by == "human:bob"
        assert prov.evaluation_score is None
