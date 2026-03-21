"""Tests for BudgetConfig consolidation and backward-compat aliases."""

import pytest

from startd8.implementation_engine.budget import (
    ARCH_CONTEXT_MAX_CHARS,
    CHARS_PER_TOKEN,
    DRAFT_SIZE_EXPLOSION_THRESHOLD,
    DRAFT_SIZE_REGRESSION_MIN_LINES,
    DRAFT_SIZE_REGRESSION_THRESHOLD,
    ENRICHMENT_BUDGET_CHARS,
    EXEMPLAR_BUDGET_CHARS,
    EXISTING_FILES_BUDGET_BYTES,
    PLAN_CONTEXT_MAX_CHARS,
    SEARCH_REPLACE_LINE_THRESHOLD,
    SPEC_CONTEXT_BUDGET_CHARS,
    SUPPLEMENTARY_BUDGET_CHARS,
    TOTAL_DRAFT_BUDGET_TOKENS,
    TOTAL_SPEC_BUDGET_TOKENS,
    BudgetConfig,
    budget_tokens_for_tier,
)


# ---------------------------------------------------------------------------
# BudgetConfig defaults match original module-level constants
# ---------------------------------------------------------------------------


class TestBudgetConfigDefaults:
    """Every BudgetConfig default must match the module-level constant."""

    def test_spec_budget_tokens(self):
        assert BudgetConfig().spec_budget_tokens == TOTAL_SPEC_BUDGET_TOKENS == 4_096

    def test_draft_budget_tokens(self):
        assert BudgetConfig().draft_budget_tokens == TOTAL_DRAFT_BUDGET_TOKENS == 8_192

    def test_plan_context_max_chars(self):
        assert BudgetConfig().plan_context_max_chars == PLAN_CONTEXT_MAX_CHARS == 6_000

    def test_arch_context_max_chars(self):
        assert BudgetConfig().arch_context_max_chars == ARCH_CONTEXT_MAX_CHARS == 4_096

    def test_spec_context_budget_chars(self):
        assert BudgetConfig().spec_context_budget_chars == SPEC_CONTEXT_BUDGET_CHARS == 12_000

    def test_existing_files_budget_bytes(self):
        assert BudgetConfig().existing_files_budget_bytes == EXISTING_FILES_BUDGET_BYTES == 40 * 1024

    def test_exemplar_budget_chars(self):
        assert BudgetConfig().exemplar_budget_chars == EXEMPLAR_BUDGET_CHARS == 3_200

    def test_search_replace_line_threshold(self):
        assert BudgetConfig().search_replace_line_threshold == SEARCH_REPLACE_LINE_THRESHOLD == 50

    def test_draft_size_regression_threshold(self):
        assert BudgetConfig().draft_size_regression_threshold == DRAFT_SIZE_REGRESSION_THRESHOLD == 0.20

    def test_draft_size_explosion_threshold(self):
        assert BudgetConfig().draft_size_explosion_threshold == DRAFT_SIZE_EXPLOSION_THRESHOLD == 3.0

    def test_draft_size_regression_min_lines(self):
        assert BudgetConfig().draft_size_regression_min_lines == DRAFT_SIZE_REGRESSION_MIN_LINES == 50

    def test_supplementary_budget_chars(self):
        assert BudgetConfig().supplementary_budget_chars == SUPPLEMENTARY_BUDGET_CHARS == 4_000

    def test_enrichment_budget_chars(self):
        assert BudgetConfig().enrichment_budget_chars == ENRICHMENT_BUDGET_CHARS == 8_000

    def test_chars_per_token(self):
        assert BudgetConfig().chars_per_token == CHARS_PER_TOKEN == 4


# ---------------------------------------------------------------------------
# Config file override changes values
# ---------------------------------------------------------------------------


class TestBudgetConfigOverride:
    """Constructing BudgetConfig with non-default values works."""

    def test_custom_spec_budget(self):
        cfg = BudgetConfig(spec_budget_tokens=2_048)
        assert cfg.spec_budget_tokens == 2_048

    def test_custom_draft_budget(self):
        cfg = BudgetConfig(draft_budget_tokens=16_384)
        assert cfg.draft_budget_tokens == 16_384

    def test_custom_existing_files_budget(self):
        cfg = BudgetConfig(existing_files_budget_bytes=80 * 1024)
        assert cfg.existing_files_budget_bytes == 80 * 1024

    def test_custom_search_replace_threshold(self):
        cfg = BudgetConfig(search_replace_line_threshold=100)
        assert cfg.search_replace_line_threshold == 100

    def test_custom_regression_threshold(self):
        cfg = BudgetConfig(draft_size_regression_threshold=0.10)
        assert cfg.draft_size_regression_threshold == 0.10


# ---------------------------------------------------------------------------
# Tier multipliers configurable
# ---------------------------------------------------------------------------


class TestTierMultipliers:
    """Tier budget multipliers default and override."""

    def test_default_tier_multipliers(self):
        cfg = BudgetConfig()
        assert cfg.tier_multipliers == {
            "TRIVIAL": 0.75,
            "SIMPLE": 1.0,
            "MODERATE": 1.75,
            "COMPLEX": 1.75,
        }

    def test_custom_tier_multipliers(self):
        custom = {"TRIVIAL": 0.5, "SIMPLE": 1.0, "MODERATE": 1.5, "COMPLEX": 2.0}
        cfg = BudgetConfig(tier_multipliers=custom)
        assert cfg.tier_multipliers == custom

    def test_budget_tokens_for_tier_uses_module_multipliers(self):
        """budget_tokens_for_tier() uses the module-level _TIER_BUDGET_MULTIPLIERS."""
        base = 4_096
        assert budget_tokens_for_tier(base, "TRIVIAL") == int(base * 0.75)
        assert budget_tokens_for_tier(base, "SIMPLE") == base
        assert budget_tokens_for_tier(base, "COMPLEX") == int(base * 1.75)

    def test_budget_tokens_for_tier_unknown(self):
        """Unknown tier returns base budget unchanged."""
        assert budget_tokens_for_tier(4_096, "UNKNOWN") == 4_096

    def test_budget_tokens_for_tier_none(self):
        """None tier returns base budget unchanged."""
        assert budget_tokens_for_tier(4_096, None) == 4_096

    def test_tier_multiplier_instances_are_independent(self):
        """Each BudgetConfig instance gets its own tier_multipliers dict."""
        cfg1 = BudgetConfig()
        cfg2 = BudgetConfig()
        cfg1.tier_multipliers["TRIVIAL"] = 0.0
        assert cfg2.tier_multipliers["TRIVIAL"] == 0.75


# ---------------------------------------------------------------------------
# EXISTING_FILES_BUDGET_BYTES single source (no duplication)
# ---------------------------------------------------------------------------


class TestNoDuplication:
    """Verify that prime_contractor uses the canonical constant."""

    def test_prime_contractor_uses_budget_constant(self):
        """prime_contractor._EXISTING_FILES_BUDGET_BYTES is the same object
        as budget.EXISTING_FILES_BUDGET_BYTES — not a duplicate definition."""
        from startd8.contractors.prime_contractor import (
            _EXISTING_FILES_BUDGET_BYTES as pc_budget,
        )

        assert pc_budget == EXISTING_FILES_BUDGET_BYTES
        assert pc_budget == 40 * 1024


# ---------------------------------------------------------------------------
# SEARCH_REPLACE_LINE_THRESHOLD consistent between budget.py and drafter.py
# ---------------------------------------------------------------------------


class TestSearchReplaceConsistency:
    """drafter.py imports SEARCH_REPLACE_LINE_THRESHOLD from budget.py."""

    def test_drafter_uses_budget_threshold(self):
        from startd8.implementation_engine import drafter

        # drafter imports SEARCH_REPLACE_LINE_THRESHOLD from .budget
        assert drafter.SEARCH_REPLACE_LINE_THRESHOLD == SEARCH_REPLACE_LINE_THRESHOLD
        assert drafter.SEARCH_REPLACE_LINE_THRESHOLD == 50


# ---------------------------------------------------------------------------
# PrimeContractorConfig budget section parsing
# ---------------------------------------------------------------------------


class TestPrimeContractorConfigBudget:
    """Budget section in prime-contractor.json is parsed into BudgetConfig."""

    def test_default_budget_on_empty_config(self):
        from startd8.contractors.prime_contractor_config import _parse_config

        config = _parse_config({})
        assert config.budget.spec_budget_tokens == 4_096
        assert config.budget.draft_budget_tokens == 8_192
        assert config.budget.existing_files_budget_bytes == 40 * 1024

    def test_budget_override_from_config(self):
        from startd8.contractors.prime_contractor_config import _parse_config

        raw = {
            "budget": {
                "spec_budget_tokens": 2_048,
                "draft_budget_tokens": 16_384,
                "existing_files_budget_bytes": 80 * 1024,
            }
        }
        config = _parse_config(raw)
        assert config.budget.spec_budget_tokens == 2_048
        assert config.budget.draft_budget_tokens == 16_384
        assert config.budget.existing_files_budget_bytes == 80 * 1024
        # Non-overridden fields keep defaults
        assert config.budget.plan_context_max_chars == 6_000

    def test_budget_tier_multipliers_override(self):
        from startd8.contractors.prime_contractor_config import _parse_config

        custom = {"TRIVIAL": 0.5, "SIMPLE": 1.0, "MODERATE": 2.0, "COMPLEX": 2.5}
        raw = {"budget": {"tier_multipliers": custom}}
        config = _parse_config(raw)
        assert config.budget.tier_multipliers == custom

    def test_budget_non_dict_ignored(self):
        from startd8.contractors.prime_contractor_config import _parse_config

        config = _parse_config({"budget": "invalid"})
        assert config.budget.spec_budget_tokens == 4_096
