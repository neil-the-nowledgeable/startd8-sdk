"""Tests for REQ-ICD-106: Security contract wiring through the pipeline."""

from __future__ import annotations

import pytest
from typing import Any, Dict


# ---------------------------------------------------------------------------
# ContextSeed model tests
# ---------------------------------------------------------------------------


class TestContextSeedSecurityContract:
    """ContextSeed includes/excludes security_contract in to_dict()."""

    def test_security_contract_included_when_set(self):
        from startd8.seeds.models import ContextSeed

        contract = {
            "databases": {"postgres_main": {"type": "postgresql", "sensitivity": "high"}},
            "sensitivity": "high",
            "source": "onboarding",
        }
        seed = ContextSeed(security_contract=contract)
        d = seed.to_dict()
        assert "security_contract" in d
        assert d["security_contract"] == contract

    def test_security_contract_excluded_when_none(self):
        from startd8.seeds.models import ContextSeed

        seed = ContextSeed()
        d = seed.to_dict()
        assert "security_contract" not in d


# ---------------------------------------------------------------------------
# SeedTask tests (seeds/models.py)
# ---------------------------------------------------------------------------


class TestSeedTaskSecurityFields:
    """SeedTask.from_seed_entry() extracts security_sensitive and detected_database."""

    def _make_entry(self, **context_overrides: Any) -> Dict[str, Any]:
        context = {"target_files": ["main.py"], "estimated_loc": 100}
        context.update(context_overrides)
        return {
            "task_id": "T-001",
            "title": "Test task",
            "config": {"context": context},
        }

    def test_extracts_security_sensitive_true(self):
        from startd8.seeds.models import SeedTask

        entry = self._make_entry(security_sensitive=True, detected_database="postgresql")
        task = SeedTask.from_seed_entry(entry)
        assert task.security_sensitive is True
        assert task.detected_database == "postgresql"

    def test_defaults_when_absent(self):
        from startd8.seeds.models import SeedTask

        entry = self._make_entry()
        task = SeedTask.from_seed_entry(entry)
        assert task.security_sensitive is False
        assert task.detected_database == ""


# ---------------------------------------------------------------------------
# SeedBuilder tests
# ---------------------------------------------------------------------------


class TestSeedBuilderSecurityContract:
    """SeedBuilder.set_security_contract() flows to build output."""

    def test_set_security_contract_flows_to_build(self):
        from startd8.seeds.builder import SeedBuilder

        builder = SeedBuilder()
        contract = {
            "databases": {"redis": {"type": "redis", "sensitivity": "medium"}},
            "sensitivity": "medium",
            "source": "onboarding",
        }
        builder.set_security_contract(contract)
        result = builder.build()
        assert result.get("security_contract") == contract

    def test_no_security_contract_when_none(self):
        from startd8.seeds.builder import SeedBuilder

        builder = SeedBuilder()
        result = builder.build()
        assert "security_contract" not in result


# ---------------------------------------------------------------------------
# Spec builder security guidance section
# ---------------------------------------------------------------------------


class TestBuildSecurityGuidanceSection:
    """_build_security_guidance_section() produces correct output."""

    def test_with_databases_produces_guidance(self):
        from startd8.implementation_engine.spec_builder import (
            _build_security_guidance_section,
        )

        context: Dict[str, Any] = {
            "security_contract": {
                "databases": {
                    "postgres_main": {
                        "type": "postgresql",
                        "sensitivity": "high",
                        "client_library": "psycopg2",
                        "credential_source": "AWS_SSM",
                    },
                },
                "sensitivity": "high",
            },
        }
        result = _build_security_guidance_section(context)
        assert "## Security Constraints" in result
        assert "parameterized queries" in result
        assert "Credentials MUST NOT be hardcoded" in result
        assert "**postgres_main** (postgresql)" in result
        assert "Client library: `psycopg2`" in result
        assert "Credential source: `AWS_SSM`" in result
        assert "HIGH sensitivity" in result
        assert "audit logging" in result

    def test_without_contract_returns_empty(self):
        from startd8.implementation_engine.spec_builder import (
            _build_security_guidance_section,
        )

        assert _build_security_guidance_section({}) == ""
        assert _build_security_guidance_section({"security_contract": None}) == ""

    def test_with_empty_databases_returns_empty(self):
        from startd8.implementation_engine.spec_builder import (
            _build_security_guidance_section,
        )

        context: Dict[str, Any] = {
            "security_contract": {"databases": {}, "sensitivity": "low"},
        }
        assert _build_security_guidance_section(context) == ""

    def test_medium_sensitivity_no_audit_note(self):
        from startd8.implementation_engine.spec_builder import (
            _build_security_guidance_section,
        )

        context: Dict[str, Any] = {
            "security_contract": {
                "databases": {
                    "cache": {"type": "redis", "sensitivity": "medium"},
                },
                "sensitivity": "medium",
            },
        }
        result = _build_security_guidance_section(context)
        assert "audit logging" not in result
        assert "**cache** (redis)" in result


# ---------------------------------------------------------------------------
# PLAN phase security contract extraction
# ---------------------------------------------------------------------------


class TestPlanPhaseSecurityContract:
    """Security contract extracted from PLAN phase seed data."""

    def test_security_contract_set_in_context(self):
        """PlanPhaseHandler populates context['security_contract'] from seed."""
        from unittest.mock import patch, MagicMock

        seed_data = {
            "plan": {"title": "Test", "goals": []},
            "tasks": [
                {
                    "task_id": "T-001",
                    "title": "Task 1",
                    "config": {"context": {"target_files": ["a.py"], "estimated_loc": 50}},
                }
            ],
            "artifacts": {},
            "security_contract": {
                "databases": {"db1": {"type": "mysql"}},
                "sensitivity": "medium",
                "source": "onboarding",
            },
        }

        with patch(
            "startd8.contractors.context_seed.phases.plan._load_enriched_seed",
            return_value=seed_data,
        ):
            from startd8.contractors.context_seed.phases.plan import PlanPhaseHandler

            handler = PlanPhaseHandler(enriched_seed_path="/fake/seed.json")
            context: Dict[str, Any] = {}

            # WorkflowPhase mock
            phase = MagicMock()

            handler.execute(phase, context)

            assert "security_contract" in context
            assert context["security_contract"]["databases"]["db1"]["type"] == "mysql"


# ---------------------------------------------------------------------------
# PCA fields include security_contract
# ---------------------------------------------------------------------------


class TestPCAFieldsIncludeSecurityContract:
    """_PCA_CONTEXT_FIELDS includes security_contract."""

    def test_security_contract_in_pca_fields(self):
        from startd8.contractors.context_seed.shared import _PCA_CONTEXT_FIELDS

        assert "security_contract" in _PCA_CONTEXT_FIELDS
