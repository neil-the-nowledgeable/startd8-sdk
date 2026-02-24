"""Tests for the v2 modular design prompt system.

Tests cover:
- Each of the 5 seed_mapping extraction functions
- Each of the 5 module render methods
- Budget enforcement (drop order: guidance → prior_art)
- The assemble_design_prompt() integration
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure the conftest FakeSeedTask is importable
sys.path.insert(0, str(Path(__file__).parent))
from conftest import FakeSeedTask  # noqa: E402

from startd8.contractors.artisan_phases.design_prompts.modules import (
    PromptFragment,
    IdentityModule,
    ConstraintsModule,
    EnrichmentModule,
    PriorArtModule,
    ScopeModule,
    GuidanceModule,
)
from startd8.contractors.artisan_phases.design_prompts.seed_mapping import (
    extract_identity,
    extract_constraints,
    extract_enrichment,
    extract_prior_art,
    extract_scope,
    extract_guidance,
)
from startd8.contractors.artisan_phases.design_prompts.budget import (
    enforce_budget,
    DEFAULT_PROMPT_TOKEN_BUDGET,
)
from startd8.contractors.artisan_phases.design_prompts import (
    assemble_design_prompt,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def basic_task():
    """A minimal SeedTask for testing."""
    return FakeSeedTask(
        task_id="PI-001",
        title="Add logging module",
        description="Add structured logging with configurable levels.",
        target_files=["src/logging.py", "src/config.py"],
        estimated_loc=80,
        feature_id="F-001",
        domain="backend",
        prompt_constraints=["[BINDING] Use stdlib logging only"],
        api_signatures=["def setup_logger(name: str) -> Logger"],
        protocol="REST",
        negative_scope=["No file-based logging"],
        file_scope={"src/logging.py": "primary", "src/config.py": "support"},
    )


@pytest.fixture
def empty_task():
    """A task with minimal data to test graceful degradation."""
    return FakeSeedTask(
        task_id="PI-002",
        title="Empty feature",
        description="",
        target_files=[],
        estimated_loc=0,
        feature_id="F-002",
        domain="unknown",
        prompt_constraints=[],
        api_signatures=[],
        protocol="",
        negative_scope=[],
    )


# ============================================================================
# Seed Mapping Tests
# ============================================================================


class TestExtractIdentity:
    def test_basic_extraction(self, basic_task):
        result = extract_identity(basic_task)
        assert result["task_id"] == "PI-001"
        assert result["title"] == "Add logging module"
        assert result["description"] == "Add structured logging with configurable levels."
        assert result["target_files"] == ["src/logging.py", "src/config.py"]
        assert result["feature_id"] == "F-001"

    def test_existing_files_forwarded(self, basic_task):
        result = extract_identity(basic_task, existing_files=["src/config.py"])
        assert result["existing_files"] == ["src/config.py"]

    def test_no_existing_files(self, basic_task):
        result = extract_identity(basic_task)
        assert result["existing_files"] == []

    def test_empty_task(self, empty_task):
        result = extract_identity(empty_task)
        assert result["task_id"] == "PI-002"
        assert result["target_files"] == []


class TestExtractConstraints:
    def test_basic_extraction(self, basic_task):
        result = extract_constraints(basic_task)
        assert result["prompt_constraints"] == ["[BINDING] Use stdlib logging only"]
        assert result["api_signatures"] == ["def setup_logger(name: str) -> Logger"]
        assert result["protocol"] == "REST"
        assert result["negative_scope"] == ["No file-based logging"]

    def test_arch_context_forwarded(self, basic_task):
        arch = {"constraints": [{"rule": "Max 3 dependencies"}]}
        result = extract_constraints(basic_task, arch)
        assert result["arch_constraints"] == [{"rule": "Max 3 dependencies"}]

    def test_no_arch_context(self, basic_task):
        result = extract_constraints(basic_task)
        assert result["arch_constraints"] == []

    def test_empty_task(self, empty_task):
        result = extract_constraints(empty_task)
        assert result["prompt_constraints"] == []
        assert result["api_signatures"] == []


class TestExtractPriorArt:
    def test_returns_none_when_empty(self, empty_task):
        result = extract_prior_art(empty_task)
        assert result is None

    def test_with_summaries(self, basic_task):
        result = extract_prior_art(
            basic_task,
            prior_design_summaries=["PI-000: Base setup"],
        )
        assert result is not None
        assert result["summaries"] == ["PI-000: Base setup"]

    def test_with_dependency_designs(self, basic_task):
        result = extract_prior_art(
            basic_task,
            dependency_designs={"PI-000": "Setup module design"},
        )
        assert result is not None
        assert "PI-000" in result["dependency_designs"]

    def test_existing_files_intersection(self, basic_task):
        result = extract_prior_art(
            basic_task,
            scaffold_existing_files=["src/config.py", "src/other.py"],
        )
        assert result is not None
        # Only src/config.py is in both target_files and scaffold_existing_files
        assert result["existing_files"] == ["src/config.py"]

    def test_staleness_forwarded(self, basic_task):
        result = extract_prior_art(
            basic_task,
            staleness_classification={"src/logging.py": "current"},
        )
        assert result is not None
        assert result["staleness"] == {"src/logging.py": "current"}

    def test_summary_truncation(self, basic_task):
        summaries = [f"PI-{i:03d}: Design {i}" for i in range(10)]
        result = extract_prior_art(basic_task, prior_design_summaries=summaries)
        assert result is not None
        assert len(result["summaries"]) == 5  # Last 5 only


class TestExtractScope:
    def test_basic_extraction(self, basic_task):
        result = extract_scope(basic_task)
        assert result["estimated_loc"] == 80
        assert result["depth_tier"] == "standard"  # default
        assert result["max_output_tokens"] is None

    def test_with_calibration(self, basic_task):
        result = extract_scope(
            basic_task,
            calibration={"depth_tier": "detailed", "max_output_tokens": 2000},
        )
        assert result["depth_tier"] == "detailed"
        assert result["max_output_tokens"] == 2000

    def test_override_trumps_calibration(self, basic_task):
        result = extract_scope(
            basic_task,
            calibration={"max_output_tokens": 2000},
            design_max_tokens_override=4000,
        )
        assert result["max_output_tokens"] == 4000

    def test_wave_metadata(self, basic_task):
        result = extract_scope(
            basic_task,
            wave_index=0,
            wave_metadata={"wave_count": 3},
        )
        assert result["wave_index"] == 0
        assert result["wave_count"] == 3


class TestExtractGuidance:
    def test_returns_none_when_empty(self, empty_task):
        result = extract_guidance(empty_task)
        assert result is None

    def test_with_domain(self, basic_task):
        result = extract_guidance(basic_task)
        assert result is not None
        assert result["domain"] == "backend"

    def test_with_goals(self, basic_task):
        result = extract_guidance(basic_task, plan_goals=["Improve observability"])
        assert result is not None
        assert result["plan_goals"] == ["Improve observability"]

    def test_with_refine_suggestions(self, basic_task):
        result = extract_guidance(
            basic_task,
            refine_suggestions=[{"suggestion": "Add more error handling"}],
        )
        assert result is not None
        assert result["refine_suggestions"] == [{"suggestion": "Add more error handling"}]

    def test_complexity_alerts(self, basic_task):
        result = extract_guidance(
            basic_task,
            complexity_dimensions={"integration": 80, "simple": 30},
        )
        assert result is not None
        # Only values > 70 are flagged
        assert "integration" in result["complexity_alerts"]
        assert "simple" not in result["complexity_alerts"]


class TestExtractEnrichment:
    def test_returns_none_when_empty(self, empty_task):
        result = extract_enrichment(empty_task)
        assert result is None

    def test_with_parameter_sources(self, basic_task):
        sources = {"username": {"origin": "config.user"}, "timeout": "env.TIMEOUT"}
        result = extract_enrichment(basic_task, parameter_sources=sources)
        assert result is not None
        assert result["parameter_sources"] == sources

    def test_with_semantic_conventions(self, basic_task):
        conventions = {"naming": "snake_case", "constants": "UPPER_SNAKE_CASE"}
        result = extract_enrichment(basic_task, semantic_conventions=conventions)
        assert result is not None
        assert result["semantic_conventions"] == conventions

    def test_with_both(self, basic_task):
        sources = {"port": "config.port"}
        conventions = {"naming": "snake_case"}
        result = extract_enrichment(
            basic_task,
            parameter_sources=sources,
            semantic_conventions=conventions,
        )
        assert result is not None
        assert "parameter_sources" in result
        assert "semantic_conventions" in result

    def test_empty_dicts_return_none(self, basic_task):
        result = extract_enrichment(
            basic_task, parameter_sources={}, semantic_conventions={},
        )
        assert result is None


# ============================================================================
# Module Render Tests
# ============================================================================


class TestIdentityModule:
    def test_render_basic(self, basic_task):
        data = extract_identity(basic_task)
        fragment = IdentityModule().render(data)
        assert fragment.category == "identity"
        assert not fragment.droppable
        assert "PI-001" in fragment.text
        assert "Add logging module" in fragment.text
        assert "`src/logging.py` (create)" in fragment.text

    def test_render_with_existing_files(self, basic_task):
        data = extract_identity(basic_task, existing_files=["src/config.py"])
        fragment = IdentityModule().render(data)
        assert "`src/config.py` (modify" in fragment.text
        assert "`src/logging.py` (create" in fragment.text

    def test_token_estimate_positive(self, basic_task):
        data = extract_identity(basic_task)
        fragment = IdentityModule().render(data)
        assert fragment.token_estimate > 0
        assert fragment.token_estimate == len(fragment.text) // 4


class TestConstraintsModule:
    def test_render_with_data(self, basic_task):
        data = extract_constraints(basic_task)
        fragment = ConstraintsModule().render(data)
        assert fragment.category == "constraints"
        assert not fragment.droppable
        assert "## Constraints" in fragment.text
        assert "setup_logger" in fragment.text
        assert "REST" in fragment.text
        assert "No file-based logging" in fragment.text

    def test_render_empty(self, empty_task):
        data = extract_constraints(empty_task)
        fragment = ConstraintsModule().render(data)
        assert fragment.text == ""
        assert fragment.token_estimate == 0


class TestEnrichmentModule:
    def test_render_with_parameter_sources(self):
        data = {
            "parameter_sources": {
                "username": {"origin": "config.user"},
                "timeout": "env.TIMEOUT",
            },
        }
        fragment = EnrichmentModule().render(data)
        assert fragment.category == "enrichment"
        assert not fragment.droppable
        assert "## Parameter Provenance" in fragment.text
        assert "`username`" in fragment.text
        assert "config.user" in fragment.text
        assert "`timeout`" in fragment.text
        assert "env.TIMEOUT" in fragment.text

    def test_render_with_semantic_conventions(self):
        data = {
            "semantic_conventions": {
                "naming": "snake_case",
                "constants": {"rule": "UPPER_SNAKE_CASE"},
            },
        }
        fragment = EnrichmentModule().render(data)
        assert "Semantic Conventions" in fragment.text
        assert "snake_case" in fragment.text
        assert "UPPER_SNAKE_CASE" in fragment.text

    def test_render_empty(self):
        data = {}
        fragment = EnrichmentModule().render(data)
        assert fragment.text == ""
        assert fragment.token_estimate == 0
        assert not fragment.droppable

    def test_token_estimate_positive(self):
        data = {"parameter_sources": {"host": "config.host"}}
        fragment = EnrichmentModule().render(data)
        assert fragment.token_estimate > 0
        assert fragment.token_estimate == len(fragment.text) // 4


class TestPriorArtModule:
    def test_render_with_dependencies(self):
        data = {
            "dependency_designs": {"PI-000": "Setup module\nWith details"},
            "existing_files": ["src/config.py"],
            "staleness": {"src/config.py": "current"},
        }
        fragment = PriorArtModule().render(data)
        assert fragment.category == "prior_art"
        assert fragment.droppable
        assert "## Prior Art" in fragment.text
        assert "PI-000" in fragment.text
        assert "current" in fragment.text

    def test_render_empty(self):
        data = {}
        fragment = PriorArtModule().render(data)
        assert fragment.text == ""
        assert fragment.droppable


class TestScopeModule:
    def test_render_with_data(self):
        data = {
            "estimated_loc": 80,
            "depth_tier": "standard",
            "wave_index": 0,
            "wave_count": 3,
        }
        fragment = ScopeModule().render(data)
        assert fragment.category == "scope"
        assert not fragment.droppable
        assert "80" in fragment.text
        assert "**Wave:** 1 of 3" in fragment.text

    def test_render_empty(self):
        data = {"estimated_loc": 0, "depth_tier": None}
        fragment = ScopeModule().render(data)
        assert fragment.text == ""


class TestGuidanceModule:
    def test_render_with_data(self):
        data = {
            "domain": "backend",
            "plan_goals": ["Improve observability"],
            "refine_suggestions": [{"suggestion": "Add error handling"}],
        }
        fragment = GuidanceModule().render(data)
        assert fragment.category == "guidance"
        assert fragment.droppable
        assert "## Guidance (advisory)" in fragment.text
        assert "backend" in fragment.text
        assert "Improve observability" in fragment.text

    def test_render_empty(self):
        data = {}
        fragment = GuidanceModule().render(data)
        assert fragment.text == ""
        assert fragment.droppable


# ============================================================================
# Budget Enforcement Tests
# ============================================================================


class TestBudgetEnforcement:
    def _make_fragment(self, category, tokens, droppable=False):
        text = "x" * (tokens * 4)  # token_estimate = len // 4
        return PromptFragment(
            category=category,
            text=text,
            token_estimate=tokens,
            droppable=droppable,
        )

    def test_under_budget_keeps_all(self):
        frags = [
            self._make_fragment("identity", 500),
            self._make_fragment("constraints", 500),
            self._make_fragment("guidance", 500, droppable=True),
        ]
        result = enforce_budget(frags, budget=3000)
        assert len(result) == 3

    def test_guidance_dropped_first(self):
        frags = [
            self._make_fragment("identity", 1500),
            self._make_fragment("constraints", 1200),
            self._make_fragment("guidance", 800, droppable=True),
        ]
        result = enforce_budget(frags, budget=3000)
        assert len(result) == 2
        assert all(f.category != "guidance" for f in result)

    def test_droppable_prior_art_dropped_second(self):
        frags = [
            self._make_fragment("identity", 1500),
            self._make_fragment("constraints", 1200),
            self._make_fragment("prior_art", 800, droppable=True),
            self._make_fragment("guidance", 200, droppable=True),
        ]
        result = enforce_budget(frags, budget=2000)
        assert len(result) == 2
        cats = [f.category for f in result]
        assert "identity" in cats
        assert "constraints" in cats

    def test_never_drops_identity_or_constraints(self):
        frags = [
            self._make_fragment("identity", 2000),
            self._make_fragment("constraints", 2000),
        ]
        result = enforce_budget(frags, budget=1000)
        # Even though over budget, identity/constraints are never dropped
        assert len(result) == 2

    def test_default_budget(self):
        assert DEFAULT_PROMPT_TOKEN_BUDGET == 3000


# ============================================================================
# Integration: assemble_design_prompt
# ============================================================================


class TestAssembleDesignPrompt:
    def test_returns_three_tuple(self, basic_task):
        system, user, max_tokens = assemble_design_prompt(basic_task)
        assert isinstance(system, str)
        assert isinstance(user, str)
        assert "CONTRACT" in system  # v2 system prompt mentions "CONTRACT"

    def test_user_prompt_contains_task_info(self, basic_task):
        _, user, _ = assemble_design_prompt(basic_task)
        assert "PI-001" in user
        assert "Add logging module" in user

    def test_user_prompt_contains_constraints(self, basic_task):
        _, user, _ = assemble_design_prompt(basic_task)
        assert "setup_logger" in user

    def test_max_tokens_from_calibration(self, basic_task):
        _, _, max_tokens = assemble_design_prompt(
            basic_task,
            calibration={"max_output_tokens": 2000},
        )
        assert max_tokens == 2000

    def test_max_tokens_override(self, basic_task):
        _, _, max_tokens = assemble_design_prompt(
            basic_task,
            calibration={"max_output_tokens": 2000},
            design_max_tokens_override=4000,
        )
        assert max_tokens == 4000

    def test_refine_path(self, basic_task):
        system, user, _ = assemble_design_prompt(
            basic_task,
            prior_design_text="## What to Build\nPrevious design.",
        )
        assert "refining" in system.lower() or "Refine" in system
        assert "Previous design" in user

    def test_empty_task_graceful_degradation(self, empty_task):
        system, user, max_tokens = assemble_design_prompt(empty_task)
        assert isinstance(system, str)
        assert isinstance(user, str)
        # Should still contain the task id
        assert "PI-002" in user

    def test_prompt_size_under_budget(self, basic_task):
        _, user, _ = assemble_design_prompt(basic_task)
        # v2 prompts should be compact — estimate tokens
        estimated_tokens = len(user) // 4
        assert estimated_tokens < DEFAULT_PROMPT_TOKEN_BUDGET * 2  # generous margin

    def test_with_plan_goals(self, basic_task):
        _, user, _ = assemble_design_prompt(
            basic_task,
            plan_goals=["Ship v2", "Reduce cost"],
        )
        assert "Ship v2" in user

    def test_with_enrichment_data(self, basic_task):
        _, user, _ = assemble_design_prompt(
            basic_task,
            parameter_sources={"username": {"origin": "config.user"}},
            semantic_conventions={"naming": "snake_case"},
        )
        assert "username" in user
        assert "snake_case" in user

    def test_enrichment_empty_dicts_no_section(self, basic_task):
        _, user, _ = assemble_design_prompt(
            basic_task,
            parameter_sources={},
            semantic_conventions={},
        )
        assert "Parameter Provenance" not in user

    def test_with_dependency_designs(self, basic_task):
        _, user, _ = assemble_design_prompt(
            basic_task,
            prior_design_summaries=["PI-000: Base module"],
            dependency_designs={"PI-000": "Base module design summary"},
        )
        assert "PI-000" in user
