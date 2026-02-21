"""Tests for WARNING-severity enrichment field default application.

When a field with ``severity: warning`` is absent from the context,
``BoundaryValidator.validate_enrichment()`` should apply the declared
default value and set the field's status to DEFAULTED.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from contextcore.contracts.propagation import BoundaryValidator
from contextcore.contracts.propagation.schema import ContextContract
from contextcore.contracts.types import PropagationStatus

from .conftest import (
    build_design_exit_context,
    build_implement_exit_context,
    build_plan_exit_context,
    build_scaffold_exit_context,
)


class TestImplementEnrichmentDefaults:
    """IMPLEMENT phase has the richest enrichment spec (6 fields)."""

    def test_domain_defaults_to_unknown(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        build_design_exit_context(ctx)
        del ctx["domain_summary"]["domain"]

        result = validator.validate_enrichment("implement", ctx, loaded_contract)
        assert result.passed is True
        # Default should have been applied
        assert ctx["domain_summary"]["domain"] == "unknown"
        # Find the field result for domain_summary.domain
        domain_fr = _find_field_result(result, "domain_summary.domain")
        assert domain_fr is not None
        assert domain_fr.default_applied is True
        assert domain_fr.status == PropagationStatus.DEFAULTED

    def test_prompt_constraints_defaults_to_empty_list(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        build_design_exit_context(ctx)
        del ctx["domain_summary"]["prompt_constraints"]

        result = validator.validate_enrichment("implement", ctx, loaded_contract)
        assert result.passed is True
        assert ctx["domain_summary"]["prompt_constraints"] == []

    def test_post_generation_validators_defaults_to_empty_list(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        build_design_exit_context(ctx)
        del ctx["domain_summary"]["post_generation_validators"]

        result = validator.validate_enrichment("implement", ctx, loaded_contract)
        assert result.passed is True
        assert ctx["domain_summary"]["post_generation_validators"] == []

    def test_design_calibration_advisory_not_defaulted(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        """design_calibration is advisory severity — absent field is logged
        but no default is applied (only warning severity gets defaults).
        """
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        build_design_exit_context(ctx)
        del ctx["design_calibration"]

        result = validator.validate_enrichment("implement", ctx, loaded_contract)
        assert result.passed is True
        # Advisory severity: field is NOT injected into context
        assert "design_calibration" not in ctx

    def test_advisory_field_does_not_block(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        """architectural_context is advisory — missing doesn't block or default."""
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        build_design_exit_context(ctx)
        del ctx["architectural_context"]

        result = validator.validate_enrichment("implement", ctx, loaded_contract)
        assert result.passed is True


class TestIntegrateEnrichmentDefaults:
    """INTEGRATE phase enrichment: _staging_dir defaults to ""."""

    def test_staging_dir_defaults_to_empty_string(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        build_design_exit_context(ctx)
        build_implement_exit_context(ctx)
        # _staging_dir not present in context

        result = validator.validate_enrichment("integrate", ctx, loaded_contract)
        assert result.passed is True
        assert ctx.get("_staging_dir") == ""


class TestTestEnrichmentDefaults:
    """TEST phase enrichment: truncation_flags defaults to {}."""

    def test_truncation_flags_defaults_to_empty_dict(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        build_design_exit_context(ctx)
        build_implement_exit_context(ctx)
        del ctx["truncation_flags"]

        result = validator.validate_enrichment("test", ctx, loaded_contract)
        assert result.passed is True
        assert ctx["truncation_flags"] == {}


class TestDesignEnrichmentDefaults:
    """DESIGN phase enrichment: scaffold.existing_target_files defaults to []."""

    def test_existing_target_files_defaults_to_empty_list(
        self, loaded_contract: ContextContract, validator: BoundaryValidator, tmp_path: Path,
    ) -> None:
        ctx = build_plan_exit_context(tmp_path)
        build_scaffold_exit_context(ctx)
        del ctx["scaffold"]["existing_target_files"]

        result = validator.validate_enrichment("design", ctx, loaded_contract)
        assert result.passed is True
        assert ctx["scaffold"]["existing_target_files"] == []


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _find_field_result(result, field_name: str):
    """Find a FieldValidationResult by field name."""
    for fr in result.field_results:
        if fr.field == field_name:
            return fr
    return None
