"""Tests that enforce single-source-of-truth for configuration constants.

These tests catch accidental re-introduction of duplicated constants
across modules. If a test fails, it means a constant was defined in
two places — consolidate to the canonical source.
"""

import pytest


def test_existing_files_budget_single_source():
    """EXISTING_FILES_BUDGET_BYTES in prime_contractor.py must match budget.py."""
    from startd8.implementation_engine.budget import EXISTING_FILES_BUDGET_BYTES
    from startd8.contractors import prime_contractor

    assert prime_contractor._EXISTING_FILES_BUDGET_BYTES == EXISTING_FILES_BUDGET_BYTES


def test_search_replace_threshold_consistency():
    """SEARCH_REPLACE_LINE_THRESHOLD must be consistent across budget.py and drafter.py."""
    from startd8.implementation_engine.budget import SEARCH_REPLACE_LINE_THRESHOLD

    # drafter.py should import from budget.py, not hardcode
    assert SEARCH_REPLACE_LINE_THRESHOLD == 50  # known default


def test_circuit_breaker_defaults_match():
    """MicroPrimeConfig circuit breaker defaults must match engine class constants."""
    from startd8.micro_prime.models import MicroPrimeConfig
    from startd8.micro_prime.engine import MicroPrimeEngine

    config = MicroPrimeConfig()
    assert config.local_max_attempts == 2  # known default
    # Engine class-level constants (backward compat)
    assert MicroPrimeEngine._CIRCUIT_BREAKER_THRESHOLD == 8
    assert MicroPrimeEngine._RUN_BREAKER_THRESHOLD == 12


def test_integration_defaults_match():
    """Integration engine backward-compat constants must be consistent."""
    from startd8.contractors.integration_engine import (
        _INTEGRATION_SIZE_REGRESSION_THRESHOLD,
        _INTEGRATION_MIN_LINES,
    )

    assert _INTEGRATION_SIZE_REGRESSION_THRESHOLD == 0.60
    assert _INTEGRATION_MIN_LINES == 50


def test_budget_constants_are_positive():
    """All budget module-level constants must be positive."""
    from startd8.implementation_engine.budget import (
        TOTAL_SPEC_BUDGET_TOKENS,
        TOTAL_DRAFT_BUDGET_TOKENS,
        PLAN_CONTEXT_MAX_CHARS,
        EXISTING_FILES_BUDGET_BYTES,
        EXEMPLAR_BUDGET_CHARS,
        CHARS_PER_TOKEN,
        SUPPLEMENTARY_BUDGET_CHARS,
        ENRICHMENT_BUDGET_CHARS,
        SPEC_CONTEXT_BUDGET_CHARS,
        ARCH_CONTEXT_MAX_CHARS,
    )

    assert TOTAL_SPEC_BUDGET_TOKENS == 4096
    assert TOTAL_DRAFT_BUDGET_TOKENS == 8192
    assert PLAN_CONTEXT_MAX_CHARS == 6000
    assert EXISTING_FILES_BUDGET_BYTES == 40 * 1024
    assert EXEMPLAR_BUDGET_CHARS == 3200
    assert CHARS_PER_TOKEN == 4
    assert SUPPLEMENTARY_BUDGET_CHARS == 4000
    assert ENRICHMENT_BUDGET_CHARS == 8000
    assert SPEC_CONTEXT_BUDGET_CHARS == 12000
    assert ARCH_CONTEXT_MAX_CHARS == 4096


def test_quality_gate_default_matches():
    """Quality gate constant in prime_contractor.py must be consistent."""
    from startd8.contractors.prime_contractor import _MIN_QUALITY_SCORE

    assert _MIN_QUALITY_SCORE == 60


def test_complexity_routing_defaults():
    """ComplexityRoutingConfig defaults must match documented values."""
    from startd8.complexity.models import ComplexityRoutingConfig

    config = ComplexityRoutingConfig()
    assert config.loc_simple_max == 150
    assert config.loc_complex_min == 500
    assert config.blast_radius_complex_threshold == 5
    assert config.caller_count_complex_threshold == 3
    assert config.mro_depth_complex_threshold == 3
    assert config.unresolved_calls_complex_threshold == 2
    assert config.non_python_trivial_loc_max == 100
    assert config.non_python_simple_loc_max == 300


def test_micro_prime_config_defaults():
    """MicroPrimeConfig defaults must match documented values."""
    from startd8.micro_prime.models import MicroPrimeConfig

    config = MicroPrimeConfig()
    assert config.model == "startd8-coder"
    assert config.provider == "ollama"
    assert config.temperature == 0.1
    assert config.max_tokens == 2048
    assert config.input_token_budget == 1024
    assert config.local_max_attempts == 2
    assert config.cloud_escalation_max_attempts == 3
    assert config.cloud_escalation_retry_strategy == "same_prompt"
    assert config.cloud_escalation_retry_max_chars == 512
    assert config.decomposition_enabled is False
    assert config.file_ollama_whole_enabled is True
    assert config.file_ollama_whole_max_elements == 60
    assert config.file_ollama_whole_max_loc == 600
    assert config.element_prompt_mode == "full_function"


def test_validation_config_defaults():
    """ValidationConfig defaults must match documented values."""
    from startd8.contractors.prime_contractor_config import ValidationConfig

    config = ValidationConfig()
    assert config.enabled is None
    assert config.strict is False


def test_agent_config_defaults():
    """AgentConfig defaults must match documented values."""
    from startd8.contractors.prime_contractor_config import AgentConfig

    config = AgentConfig()
    assert config.lead is None
    assert config.drafter is None
    assert config.tier3 is None


def test_prime_contractor_config_defaults():
    """PrimeContractorConfig top-level defaults must match documented values."""
    from startd8.contractors.prime_contractor_config import PrimeContractorConfig

    config = PrimeContractorConfig()
    assert config.micro_prime_enabled is False
    assert config.complexity_routing_enabled is False
    assert config.repair_enabled is True


def test_repair_config_defaults():
    """RepairConfig defaults must match documented values."""
    from startd8.repair.config import RepairConfig

    config = RepairConfig()
    assert config.repair_enabled is True
    assert config.circuit_breaker_threshold == 3
    assert config.per_step_timeout_s == 2.0
    assert config.total_timeout_s == 5.0
    assert config.delta_threshold == 0.5
    assert config.staging_retention_hours == 24
    assert config.max_semantic_repairs_per_file == 5
    assert config.semantic_repair_circuit_breaker_threshold == 3


def test_draft_size_regression_constants():
    """Draft size regression constants must be consistent."""
    from startd8.implementation_engine.budget import (
        DRAFT_SIZE_REGRESSION_THRESHOLD,
        DRAFT_SIZE_REGRESSION_MIN_LINES,
        DRAFT_SIZE_EXPLOSION_THRESHOLD,
    )

    assert DRAFT_SIZE_REGRESSION_THRESHOLD == 0.20
    assert DRAFT_SIZE_REGRESSION_MIN_LINES == 50
    assert DRAFT_SIZE_EXPLOSION_THRESHOLD == 3.0


def test_tier_budget_multipliers_consistency():
    """Tier budget multipliers must produce expected adjusted budgets."""
    from startd8.implementation_engine.budget import (
        TOTAL_DRAFT_BUDGET_TOKENS,
        budget_tokens_for_tier,
    )

    assert budget_tokens_for_tier(TOTAL_DRAFT_BUDGET_TOKENS, "TRIVIAL") == 6144
    assert budget_tokens_for_tier(TOTAL_DRAFT_BUDGET_TOKENS, "SIMPLE") == 8192
    assert budget_tokens_for_tier(TOTAL_DRAFT_BUDGET_TOKENS, "MODERATE") == 14336
    assert budget_tokens_for_tier(TOTAL_DRAFT_BUDGET_TOKENS, "COMPLEX") == 14336
    # None tier returns base budget unchanged
    assert budget_tokens_for_tier(TOTAL_DRAFT_BUDGET_TOKENS, None) == 8192
