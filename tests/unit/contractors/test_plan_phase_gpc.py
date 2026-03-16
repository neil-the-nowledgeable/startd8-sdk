"""Tests for generation profile consumer integration — PLAN phase.

REQ-GPC-200: Extract generation_profile from onboarding.
REQ-GPC-201: Skip omitted markers, set to None.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


def _make_seed_data(
    *,
    onboarding: dict | None = None,
    tasks: list | None = None,
) -> dict:
    """Minimal seed data dict accepted by PlanPhaseHandler.execute()."""
    return {
        "plan": {"title": "Test Plan", "goals": ["g1"]},
        "tasks": tasks or [
            {
                "task_id": "T-1",
                "title": "Widget",
                "task_type": "task",
                "story_points": 1,
                "priority": "P1",
                "labels": [],
                "depends_on": [],
                "config": {
                    "task_description": "Build widget",
                    "context": {
                        "target_files": ["widget.py"],
                        "estimated_loc": 50,
                        "feature_id": "F-1",
                    },
                },
                "_enrichment": {"domain": "backend"},
            }
        ],
        "onboarding": onboarding,
        "artifacts": {},
    }


def _make_marker(profile: str = "source") -> dict:
    return {"_omitted": f"profile={profile}"}


class TestPlanPhaseExtractsProfile:
    """REQ-GPC-200: generation_profile extracted at PLAN phase."""

    @patch("startd8.contractors.context_seed.phases.plan._load_enriched_seed")
    def test_extracts_source_profile(self, mock_load):
        from startd8.contractors.context_seed.phases.plan import PlanPhaseHandler

        mock_load.return_value = _make_seed_data(
            onboarding={"generation_profile": "source"}
        )
        handler = PlanPhaseHandler("/fake/seed.json")
        context: dict = {}
        handler.execute(None, context, dry_run=True)

        assert context["generation_profile"] == "source"

    @patch("startd8.contractors.context_seed.phases.plan._load_enriched_seed")
    def test_defaults_to_full(self, mock_load):
        from startd8.contractors.context_seed.phases.plan import PlanPhaseHandler

        mock_load.return_value = _make_seed_data(onboarding={})
        handler = PlanPhaseHandler("/fake/seed.json")
        context: dict = {}
        handler.execute(None, context, dry_run=True)

        assert context["generation_profile"] == "full"

    @patch("startd8.contractors.context_seed.phases.plan._load_enriched_seed")
    def test_defaults_to_full_when_no_onboarding(self, mock_load):
        from startd8.contractors.context_seed.phases.plan import PlanPhaseHandler

        mock_load.return_value = _make_seed_data(onboarding=None)
        handler = PlanPhaseHandler("/fake/seed.json")
        context: dict = {}
        handler.execute(None, context, dry_run=True)

        assert context["generation_profile"] == "full"


class TestPlanPhaseOmittedMarkers:
    """REQ-GPC-201: omitted markers converted to None."""

    @patch("startd8.contractors.context_seed.phases.plan._load_enriched_seed")
    def test_omitted_fields_become_none(self, mock_load):
        from startd8.contractors.context_seed.phases.plan import PlanPhaseHandler

        onboarding = {
            "generation_profile": "source",
            "derivation_rules": _make_marker(),
            "resolved_artifact_parameters": _make_marker(),
            "expected_output_contracts": _make_marker(),
            "design_calibration_hints": _make_marker(),
            "open_questions": _make_marker(),
            "artifact_dependency_graph": _make_marker(),
            "service_metadata": _make_marker(),
            "schema_features": _make_marker(),
        }
        mock_load.return_value = _make_seed_data(onboarding=onboarding)

        handler = PlanPhaseHandler("/fake/seed.json")
        context: dict = {}
        handler.execute(None, context, dry_run=True)

        # All 8 fields should be None, not marker dicts
        assert context["onboarding_derivation_rules"] is None
        assert context["onboarding_resolved_parameters"] is None
        assert context["onboarding_output_contracts"] is None
        assert context["onboarding_calibration_hints"] is None
        assert context["onboarding_open_questions"] is None
        assert context["onboarding_dependency_graph"] is None
        assert context["service_metadata"] is None
        assert context["onboarding_schema_features"] is None

    @patch("startd8.contractors.context_seed.phases.plan._load_enriched_seed")
    def test_non_omitted_fields_pass_through(self, mock_load):
        from startd8.contractors.context_seed.phases.plan import PlanPhaseHandler

        real_rules = {"dashboard": [{"source": "manifest"}]}
        real_params = {"param1": {"origin": "manifest"}}
        onboarding = {
            "generation_profile": "full",
            "derivation_rules": real_rules,
            "resolved_artifact_parameters": real_params,
        }
        mock_load.return_value = _make_seed_data(onboarding=onboarding)

        handler = PlanPhaseHandler("/fake/seed.json")
        context: dict = {}
        handler.execute(None, context, dry_run=True)

        assert context["onboarding_derivation_rules"] == real_rules
        assert context["onboarding_resolved_parameters"] == real_params

    @patch("startd8.contractors.context_seed.phases.plan._load_enriched_seed")
    def test_mixed_omitted_and_real_fields(self, mock_load):
        from startd8.contractors.context_seed.phases.plan import PlanPhaseHandler

        real_service_meta = {"emailservice": {"transport_protocol": "grpc"}}
        onboarding = {
            "generation_profile": "source",
            "derivation_rules": _make_marker(),
            "service_metadata": real_service_meta,
            "design_calibration_hints": _make_marker(),
        }
        mock_load.return_value = _make_seed_data(onboarding=onboarding)

        handler = PlanPhaseHandler("/fake/seed.json")
        context: dict = {}
        handler.execute(None, context, dry_run=True)

        # Omitted → None
        assert context["onboarding_derivation_rules"] is None
        assert context["onboarding_calibration_hints"] is None
        # Real → preserved
        assert context["service_metadata"] == real_service_meta
