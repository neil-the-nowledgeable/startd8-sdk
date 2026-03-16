"""Tests for generation profile consumer integration — shared.py resume path.

REQ-GPC-202: Resume/recovery preserves generation_profile.
REQ-GPC-201: Omitted markers stay None on resume.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


def _make_seed_data(
    *,
    onboarding: dict | None = None,
) -> dict:
    """Minimal seed data for _ensure_context_loaded resume path."""
    return {
        "plan": {"title": "Test Plan", "goals": []},
        "tasks": [
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


def _write_seed(tmp_path: Path, seed_data: dict) -> Path:
    seed_file = tmp_path / "context-seed.json"
    seed_file.write_text(json.dumps(seed_data), encoding="utf-8")
    return seed_file


class TestResumeRestoresProfile:
    """REQ-GPC-202: generation_profile restored on resume."""

    def test_restores_source_profile(self, tmp_path):
        from startd8.contractors.context_seed.shared import _ensure_context_loaded

        seed_data = _make_seed_data(
            onboarding={"generation_profile": "source"}
        )
        seed_file = _write_seed(tmp_path, seed_data)

        # Simulate resume: context has enriched_seed_path but no tasks
        context = {"enriched_seed_path": str(seed_file)}
        _ensure_context_loaded(context)

        assert context["generation_profile"] == "source"

    def test_defaults_to_full_on_resume(self, tmp_path):
        from startd8.contractors.context_seed.shared import _ensure_context_loaded

        seed_data = _make_seed_data(onboarding={})
        seed_file = _write_seed(tmp_path, seed_data)

        context = {"enriched_seed_path": str(seed_file)}
        _ensure_context_loaded(context)

        assert context["generation_profile"] == "full"

    def test_does_not_clobber_existing_profile(self, tmp_path):
        from startd8.contractors.context_seed.shared import _ensure_context_loaded

        seed_data = _make_seed_data(
            onboarding={"generation_profile": "source"}
        )
        seed_file = _write_seed(tmp_path, seed_data)

        # Profile already in context from PLAN phase
        context = {
            "enriched_seed_path": str(seed_file),
            "generation_profile": "operator",
        }
        _ensure_context_loaded(context)

        # Should NOT be overwritten
        assert context["generation_profile"] == "operator"


class TestResumeOmittedMarkers:
    """REQ-GPC-201 on resume path: omitted markers → None."""

    def test_omitted_fields_become_none_on_resume(self, tmp_path):
        from startd8.contractors.context_seed.shared import _ensure_context_loaded

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
        seed_data = _make_seed_data(onboarding=onboarding)
        seed_file = _write_seed(tmp_path, seed_data)

        context = {"enriched_seed_path": str(seed_file)}
        _ensure_context_loaded(context)

        assert context["onboarding_derivation_rules"] is None
        assert context["onboarding_resolved_parameters"] is None
        assert context["onboarding_output_contracts"] is None
        assert context["onboarding_calibration_hints"] is None
        assert context["onboarding_open_questions"] is None
        assert context["onboarding_dependency_graph"] is None
        assert context["service_metadata"] is None
        assert context["onboarding_schema_features"] is None

    def test_real_fields_preserved_on_resume(self, tmp_path):
        from startd8.contractors.context_seed.shared import _ensure_context_loaded

        real_rules = {"dashboard": [{"source": "manifest"}]}
        onboarding = {
            "generation_profile": "full",
            "derivation_rules": real_rules,
            "design_calibration_hints": _make_marker(),
        }
        seed_data = _make_seed_data(onboarding=onboarding)
        seed_file = _write_seed(tmp_path, seed_data)

        context = {"enriched_seed_path": str(seed_file)}
        _ensure_context_loaded(context)

        assert context["onboarding_derivation_rules"] == real_rules
        assert context["onboarding_calibration_hints"] is None
