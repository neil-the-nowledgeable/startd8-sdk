"""Tests for Phase 1 — Signal Preservation (REQ-MSR-*, REQ-RFL-*).

Verifies that computed signals are persisted in metadata rather than discarded.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# REQ-RFL-128 / REQ-MSR-A15: Repair effectiveness API
# ---------------------------------------------------------------------------


class TestRepairEffectivenessAPI:
    """get_step_effectiveness_summary() returns serializable dicts."""

    def test_summary_format(self):
        from startd8.repair.models import StepEffectiveness
        from startd8.repair.orchestrator import (
            _step_effectiveness,
            get_step_effectiveness_summary,
            reset_step_effectiveness,
        )

        reset_step_effectiveness()
        se = StepEffectiveness(step_name="fence_strip")
        se.attempts = 10
        se.modifications = 7
        se.reverts = 1
        se.contributed_to_success = 5
        _step_effectiveness["fence_strip"] = se

        summary = get_step_effectiveness_summary()
        assert "fence_strip" in summary
        entry = summary["fence_strip"]
        assert entry["attempts"] == 10
        assert entry["success_rate"] == pytest.approx(0.5)  # 5/10
        assert entry["modifications"] == 7
        assert entry["reverts"] == 1
        assert entry["contributed_to_success"] == 5
        # Must be JSON-serializable
        json.dumps(summary)

        reset_step_effectiveness()

    def test_empty_returns_empty(self):
        from startd8.repair.orchestrator import (
            get_step_effectiveness_summary,
            reset_step_effectiveness,
        )

        reset_step_effectiveness()
        assert get_step_effectiveness_summary() == {}


# ---------------------------------------------------------------------------
# REQ-RFL-110: compute_disk_quality_score extraction
# ---------------------------------------------------------------------------


class TestQualityScoreExtraction:
    """Verify compute_disk_quality_score works from both import paths."""

    def test_import_from_validator(self):
        from startd8.forward_manifest_validator import compute_disk_quality_score

        ns = SimpleNamespace(
            ast_valid=True,
            stubs_remaining=0,
            duplicate_definitions=0,
            import_completeness=1.0,
            contract_compliance=1.0,
            semantic_issues=[],
        )
        score = compute_disk_quality_score(ns)
        assert score == pytest.approx(1.0)

    def test_import_from_postmortem(self):
        from startd8.contractors.prime_postmortem import compute_disk_quality_score

        ns = SimpleNamespace(
            ast_valid=True,
            stubs_remaining=0,
            import_completeness=1.0,
            contract_compliance=1.0,
            semantic_issues=[],
        )
        score = compute_disk_quality_score(ns)
        assert score == pytest.approx(1.0)

    def test_low_score_with_issues(self):
        from startd8.forward_manifest_validator import compute_disk_quality_score

        ns = SimpleNamespace(
            ast_valid=True,
            stubs_remaining=5,
            import_completeness=0.5,
            contract_compliance=0.5,
            semantic_issues=[
                {"severity": "error", "message": "phantom import"},
                {"severity": "error", "message": "duplicate def"},
            ],
        )
        score = compute_disk_quality_score(ns)
        assert score < 0.7  # degraded

    def test_ast_invalid_returns_zero(self):
        from startd8.forward_manifest_validator import compute_disk_quality_score

        ns = SimpleNamespace(ast_valid=False)
        assert compute_disk_quality_score(ns) == 0.0

    def test_none_returns_zero(self):
        from startd8.forward_manifest_validator import compute_disk_quality_score

        assert compute_disk_quality_score(None) == 0.0

    def test_works_with_dict_via_simplenamespace(self):
        """Verify the SimpleNamespace wrapper pattern used in integration engine."""
        from startd8.forward_manifest_validator import compute_disk_quality_score

        data = {
            "ast_valid": True,
            "stubs_remaining": 2,
            "import_completeness": 0.8,
            "contract_compliance": 0.9,
            "semantic_issues": [{"severity": "warning", "message": "test"}],
        }
        score = compute_disk_quality_score(SimpleNamespace(**data))
        assert 0.0 < score < 1.0


# ---------------------------------------------------------------------------
# REQ-MSR-110: Budget decision tracking
# ---------------------------------------------------------------------------


class TestBudgetDecisionTracking:
    """enforce_prompt_budget returns (prompt, budget_decision) tuple."""

    def test_returns_tuple(self):
        from startd8.implementation_engine.budget import enforce_prompt_budget

        sections = [(0, "task", "Hello world")]
        result = enforce_prompt_budget(sections, 1000)
        assert isinstance(result, tuple)
        prompt, decision = result
        assert isinstance(prompt, str)
        assert isinstance(decision, dict)
        assert "tokens_before" in decision
        assert "tokens_after" in decision
        assert "sections_dropped" in decision

    def test_no_drops_when_under_budget(self):
        from startd8.implementation_engine.budget import enforce_prompt_budget

        sections = [
            (0, "task", "x" * 100),
            (1, "context", "y" * 100),
        ]
        prompt, decision = enforce_prompt_budget(sections, 1000)
        assert decision["sections_dropped"] == []
        assert decision["tokens_before"] == decision["tokens_after"]

    def test_tracks_dropped_sections(self):
        from startd8.implementation_engine.budget import enforce_prompt_budget

        sections = [
            (0, "task", "x" * 100),
            (3, "examples", "y" * 20000),  # Will be dropped
        ]
        prompt, decision = enforce_prompt_budget(sections, 100)
        assert "examples" in decision["sections_dropped"]

    def test_decision_is_serializable(self):
        from startd8.implementation_engine.budget import enforce_prompt_budget

        sections = [(0, "task", "Hello")]
        _, decision = enforce_prompt_budget(sections, 1000)
        json.dumps(decision)

    def test_all_sections_listed(self):
        from startd8.implementation_engine.budget import enforce_prompt_budget

        sections = [
            (0, "task", "x"),
            (1, "arch", "y"),
            (2, "plan", "z"),
        ]
        _, decision = enforce_prompt_budget(sections, 1000)
        assert set(decision["all_sections"]) == {"task", "arch", "plan"}


# ---------------------------------------------------------------------------
# REQ-MSR-200: Context resolution field skip tracking
# ---------------------------------------------------------------------------


class TestContextResolutionFieldSkips:
    """_sanitize_context returns structured skip reasons."""

    def test_skipped_fields_are_dicts(self):
        from startd8.contractors.context_resolution import (
            PipelineContextStrategy,
            SanitizationMode,
        )

        strategy = PipelineContextStrategy(
            sanitization_mode=SanitizationMode.LENIENT,
        )
        # Inject a value that triggers path traversal
        ctx = {"safe_key": "hello", "../evil": "malicious"}
        sanitized, skipped = strategy._sanitize_context(ctx)

        assert "safe_key" in sanitized
        assert "../evil" not in sanitized
        assert len(skipped) >= 1
        assert isinstance(skipped[0], dict)
        assert "field" in skipped[0]
        assert "reason" in skipped[0]

    def test_resolved_context_has_skipped_fields(self):
        from startd8.contractors.context_resolution import ResolvedContext

        # Verify the field exists on the dataclass
        rc = ResolvedContext(mode="pipeline")
        assert hasattr(rc, "skipped_fields")
        assert rc.skipped_fields == ()


# ---------------------------------------------------------------------------
# REQ-MSR-210: Seed metadata preservation
# ---------------------------------------------------------------------------


class TestSeedMetadataPreservation:
    """add_features_from_seed preserves priority, effort_estimate, etc."""

    def test_seed_metadata_forwarded(self, tmp_path):
        from startd8.contractors.queue import FeatureQueue

        seed = {
            "tasks": [{
                "task_id": "T-001",
                "title": "Test task",
                "priority": "high",
                "effort_estimate": "2d",
                "labels": ["backend", "api"],
                "config": {
                    "task_description": "Do something",
                    "context": {"target_files": ["src/main.py"]},
                },
            }],
        }
        seed_path = tmp_path / "seed.json"
        seed_path.write_text(json.dumps(seed))

        queue = FeatureQueue(state_file=tmp_path / "state" / "queue.json")
        features = queue.add_features_from_seed(seed_path)

        assert len(features) == 1
        meta = features[0].metadata
        assert "seed_metadata" in meta
        assert meta["seed_metadata"]["priority"] == "high"
        assert meta["seed_metadata"]["effort_estimate"] == "2d"
        assert meta["seed_metadata"]["labels"] == ["backend", "api"]

    def test_no_seed_metadata_when_absent(self, tmp_path):
        from startd8.contractors.queue import FeatureQueue

        seed = {
            "tasks": [{
                "task_id": "T-002",
                "title": "Minimal task",
                "config": {
                    "task_description": "Simple",
                    "context": {"target_files": []},
                },
            }],
        }
        seed_path = tmp_path / "seed.json"
        seed_path.write_text(json.dumps(seed))

        queue = FeatureQueue(state_file=tmp_path / "state" / "queue.json")
        features = queue.add_features_from_seed(seed_path)

        assert "seed_metadata" not in features[0].metadata
