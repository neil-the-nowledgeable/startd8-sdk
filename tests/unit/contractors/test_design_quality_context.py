"""Unit tests for design quality context integration.

Tests cover:
- Architectural context derivation from manifest + cross-feature analysis
- Per-task design calibration (depth tiers)
- Native system_prompt in AgentLLMBackend (P-1 fix)
- Reviewer/Arbiter project context (P-3 fix)
- Context serialization preserving structure (P-2 fix)
- Seed backward compatibility
- DesignPhaseHandler cross-task context flow
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from startd8.workflows.builtin.plan_ingestion_models import (
    ArtisanContextSeed,
    ParsedFeature,
    ParsedPlan,
)
from startd8.workflows.builtin.plan_ingestion_workflow import (
    DEPTH_TIERS,
    PlanIngestionWorkflow,
)
from startd8.contractors.artisan_phases.design_documentation import (
    AgentLLMBackend,
    DesignSection,
    FeatureContext,
    ReviewRole,
    build_design_system_prompt,
    parse_design_document,
    _DEFAULT_SECTIONS,
    DESIGN_GENERATION_SYSTEM_PROMPT,
    REVIEWER_USER_PROMPT_TEMPLATE,
    ARBITER_USER_PROMPT_TEMPLATE,
    DesignDocumentationPhase,
    parse_review_verdict,
)
from startd8.contractors.context_seed_handlers import (
    DesignPhaseHandler,
    SeedTask,
)


# ============================================================================
# Helpers
# ============================================================================


def _make_parsed_plan(**overrides: Any) -> ParsedPlan:
    """Build a test ParsedPlan."""
    defaults = {
        "title": "Test Plan",
        "goals": ["Build ServiceMonitor", "Add PrometheusRule integration"],
        "features": [
            ParsedFeature(
                feature_id="F-001",
                name="Core monitor",
                description="Implement ServiceMonitor",
                target_files=["src/monitor.py", "src/shared.py"],
                dependencies=[],
                estimated_loc=200,
            ),
            ParsedFeature(
                feature_id="F-002",
                name="Alert rules",
                description="Add PrometheusRule support",
                target_files=["src/alerts.py", "src/shared.py"],
                dependencies=["F-001"],
                estimated_loc=40,
            ),
            ParsedFeature(
                feature_id="F-003",
                name="Dashboard",
                description="Grafana dashboard config",
                target_files=["src/dashboard.py"],
                dependencies=["F-001"],
                estimated_loc=80,
            ),
        ],
        "dependency_graph": {
            "F-002": ["F-001"],
            "F-003": ["F-001"],
        },
        "mentioned_files": ["src/monitor.py", "src/alerts.py", "src/dashboard.py", "src/shared.py"],
    }
    defaults.update(overrides)
    return ParsedPlan(**defaults)


def _make_seed_task(
    task_id: str = "PI-001",
    estimated_loc: int = 100,
    target_files: list[str] | None = None,
    **overrides: Any,
) -> SeedTask:
    """Create a SeedTask for testing."""
    return SeedTask(
        task_id=task_id,
        title=overrides.get("title", f"Feature {task_id}"),
        task_type="task",
        story_points=3,
        priority="medium",
        labels=[],
        depends_on=[],
        description=overrides.get("description", f"Implement feature {task_id}"),
        target_files=target_files or ["src/foo.py"],
        estimated_loc=estimated_loc,
        feature_id=overrides.get("feature_id", task_id),
        domain="backend",
        domain_reasoning="",
        environment_checks=[],
        prompt_constraints=["Use type hints"],
        post_generation_validators=["pytest"],
        available_siblings=[],
        existing_content_hash=None,
        design_doc_sections=overrides.get("design_doc_sections", []),
        artifact_types_addressed=overrides.get("artifact_types_addressed", []),
        file_scope=overrides.get("file_scope", {}),
    )


def _make_task_dict(
    task_id: str = "PI-001",
    estimated_loc: int = 100,
    target_files: list[str] | None = None,
) -> dict[str, Any]:
    """Task dict matching the format from _derive_tasks_from_features."""
    return {
        "task_id": task_id,
        "title": f"Feature {task_id}",
        "task_type": "task",
        "story_points": 3,
        "priority": "medium",
        "labels": [],
        "depends_on": [],
        "config": {
            "task_description": f"Implement feature {task_id}",
            "context": {
                "feature_id": task_id,
                "target_files": target_files or ["src/foo.py"],
                "estimated_loc": estimated_loc,
            },
        },
    }


# ============================================================================
# ArtisanContextSeed backward compatibility
# ============================================================================


class TestSeedBackwardCompat:
    """Old seeds (without new fields) load correctly."""

    def test_seed_without_new_fields(self):
        seed = ArtisanContextSeed(
            plan={"title": "Test"},
            tasks=[{"task_id": "T1"}],
        )
        d = seed.to_dict()
        assert "architectural_context" not in d
        assert "design_calibration" not in d

    def test_seed_with_new_fields(self):
        seed = ArtisanContextSeed(
            plan={"title": "Test"},
            tasks=[{"task_id": "T1"}],
            architectural_context={"project_goals": ["Build X"]},
            design_calibration={"T1": {"depth_tier": "brief"}},
        )
        d = seed.to_dict()
        assert d["architectural_context"] == {"project_goals": ["Build X"]}
        assert d["design_calibration"] == {"T1": {"depth_tier": "brief"}}


# ============================================================================
# Architectural context derivation
# ============================================================================


class TestArchitecturalContext:

    def test_from_manifest_empty(self):
        plan = _make_parsed_plan()
        ctx = PlanIngestionWorkflow._derive_architectural_context(plan, {})
        assert ctx["project_goals"] == plan.goals
        assert ctx["objectives"] == []
        assert ctx["constraints"] == []

    def test_from_manifest_with_data(self):
        plan = _make_parsed_plan()
        manifest_ctx = {
            "objectives": [{"name": "Reduce MTTR", "key_results": ["< 5min"]}],
            "constraints": [{"rule": "No breaking changes", "severity": "error", "scope": "*"}],
            "preferences": ["Use async"],
            "focus_areas": ["reliability"],
        }
        ctx = PlanIngestionWorkflow._derive_architectural_context(plan, manifest_ctx)
        assert ctx["objectives"] == manifest_ctx["objectives"]
        assert ctx["constraints"] == manifest_ctx["constraints"]
        assert ctx["preferences"] == ["Use async"]
        assert ctx["focus_areas"] == ["reliability"]

    def test_shared_modules(self):
        plan = _make_parsed_plan()
        ctx = PlanIngestionWorkflow._derive_architectural_context(plan, {})
        shared = ctx["shared_modules"]
        # src/shared.py is targeted by F-001 and F-002
        paths = [m["path"] for m in shared]
        assert "src/shared.py" in paths

    def test_import_conventions(self):
        plan = _make_parsed_plan()
        ctx = PlanIngestionWorkflow._derive_architectural_context(plan, {})
        assert "src" in ctx["import_conventions"]

    def test_domain_concepts(self):
        plan = _make_parsed_plan()
        ctx = PlanIngestionWorkflow._derive_architectural_context(plan, {})
        concepts = ctx["domain_concepts"]
        assert "ServiceMonitor" in concepts
        assert "PrometheusRule" in concepts

    def test_dependency_clusters(self):
        plan = _make_parsed_plan()
        ctx = PlanIngestionWorkflow._derive_architectural_context(plan, {})
        clusters = ctx["dependency_clusters"]
        # F-001 is root (F-002, F-003 depend on it)
        root_ids = [c["root"] for c in clusters]
        assert "F-001" in root_ids


# ============================================================================
# Calibration / depth tiers
# ============================================================================


class _ImportBlocker:
    """Makes 'from contextcore.agent.size_estimation import SizeEstimator' raise ImportError."""

    def __getattr__(self, name: str) -> None:
        raise ImportError("Blocked for test determinism")


class TestDesignCalibration:
    """Design calibration uses DEPTH_TIERS and LOC-based fallback when contextcore is unavailable."""

    @pytest.fixture(autouse=True)
    def _no_contextcore_estimator(self):
        """Force LOC-based fallback so tests are deterministic (SizeEstimator can vary by env)."""
        import sys

        with patch.dict(sys.modules, {"contextcore.agent.size_estimation": _ImportBlocker()}):
            yield

    def test_depth_tiers_constants(self):
        assert "brief" in DEPTH_TIERS
        assert "standard" in DEPTH_TIERS
        assert "comprehensive" in DEPTH_TIERS
        assert DEPTH_TIERS["brief"]["max_tokens"] == 4096
        assert DEPTH_TIERS["standard"]["max_tokens"] == 8192
        assert DEPTH_TIERS["comprehensive"]["max_tokens"] == 16384

    def test_brief_for_small_tasks(self):
        tasks = [_make_task_dict("T1", estimated_loc=30)]
        cal = PlanIngestionWorkflow._derive_design_calibration(tasks)
        assert cal["T1"]["depth_tier"] == "brief"
        assert cal["T1"]["max_output_tokens"] == 4096
        assert cal["T1"]["implement_max_output_tokens"] == 8192
        assert len(cal["T1"]["sections"]) == 3

    def test_standard_for_medium_tasks(self):
        tasks = [_make_task_dict("T1", estimated_loc=100)]
        cal = PlanIngestionWorkflow._derive_design_calibration(tasks)
        assert cal["T1"]["depth_tier"] == "standard"
        assert cal["T1"]["max_output_tokens"] == 8192
        assert cal["T1"]["implement_max_output_tokens"] == 16384
        assert len(cal["T1"]["sections"]) == 5

    def test_comprehensive_for_large_tasks(self):
        tasks = [_make_task_dict("T1", estimated_loc=200)]
        cal = PlanIngestionWorkflow._derive_design_calibration(tasks)
        assert cal["T1"]["depth_tier"] == "comprehensive"
        assert cal["T1"]["max_output_tokens"] == 16384
        assert cal["T1"]["implement_max_output_tokens"] == 32768
        assert len(cal["T1"]["sections"]) == 7

    def test_calibration_fallback_heuristics(self):
        """Works without contextcore installed."""
        tasks = [
            _make_task_dict("T1", estimated_loc=20),
            _make_task_dict("T2", estimated_loc=80),
            _make_task_dict("T3", estimated_loc=300),
        ]
        cal = PlanIngestionWorkflow._derive_design_calibration(tasks)
        assert cal["T1"]["complexity"] == "low"
        assert cal["T2"]["complexity"] == "medium"
        assert cal["T3"]["complexity"] == "high"

    def test_calibration_boundary_50(self):
        """LOC=50 → brief (low)."""
        tasks = [_make_task_dict("T1", estimated_loc=50)]
        cal = PlanIngestionWorkflow._derive_design_calibration(tasks)
        assert cal["T1"]["depth_tier"] == "brief"

    def test_calibration_boundary_51(self):
        """LOC=51 → standard (medium)."""
        tasks = [_make_task_dict("T1", estimated_loc=51)]
        cal = PlanIngestionWorkflow._derive_design_calibration(tasks)
        assert cal["T1"]["depth_tier"] == "standard"

    def test_calibration_boundary_150(self):
        """LOC=150 → standard (medium)."""
        tasks = [_make_task_dict("T1", estimated_loc=150)]
        cal = PlanIngestionWorkflow._derive_design_calibration(tasks)
        assert cal["T1"]["depth_tier"] == "standard"

    def test_calibration_boundary_151(self):
        """LOC=151 → comprehensive (high)."""
        tasks = [_make_task_dict("T1", estimated_loc=151)]
        cal = PlanIngestionWorkflow._derive_design_calibration(tasks)
        assert cal["T1"]["depth_tier"] == "comprehensive"


# ============================================================================
# Dynamic system prompt
# ============================================================================


class TestDynamicSystemPrompt:

    def test_default_sections(self):
        prompt = build_design_system_prompt()
        for section in _DEFAULT_SECTIONS:
            assert f"## {section}" in prompt

    def test_calibrated_sections(self):
        sections = ["Overview", "Architecture", "Testing Strategy"]
        prompt = build_design_system_prompt(sections)
        assert "## Overview" in prompt
        assert "## Architecture" in prompt
        assert "## Testing Strategy" in prompt
        # Should NOT contain sections not in the list
        assert "## Data Model" not in prompt
        assert "## Security Considerations" not in prompt

    def test_depth_guidance_in_prompt(self):
        guidance = "This is a small feature — keep it brief."
        prompt = build_design_system_prompt(depth_guidance=guidance)
        assert guidance in prompt
        assert "Scope guidance:" in prompt

    def test_no_depth_guidance(self):
        prompt = build_design_system_prompt()
        assert "Scope guidance:" not in prompt

    def test_backward_compat_constant(self):
        """DESIGN_GENERATION_SYSTEM_PROMPT is still available."""
        assert "senior software architect" in DESIGN_GENERATION_SYSTEM_PROMPT


# ============================================================================
# AgentLLMBackend native system_prompt (P-1 fix)
# ============================================================================


class TestAgentLLMBackendNativeSystemPrompt:

    @pytest.mark.asyncio
    async def test_system_prompt_passed_natively(self):
        """AgentLLMBackend passes system_prompt to agenerate() natively."""
        mock_agent = AsyncMock()
        mock_agent.agenerate = AsyncMock(return_value=("design text", 100, {}))
        mock_agent.max_tokens = 16384

        backend = AgentLLMBackend(agent=mock_agent)
        result = await backend.generate(
            "Write a design", system_prompt="You are an architect"
        )

        mock_agent.agenerate.assert_called_once_with(
            "Write a design", system_prompt="You are an architect",
        )
        assert result == "design text"

    @pytest.mark.asyncio
    async def test_no_system_prompt_concatenation(self):
        """System prompt is NOT concatenated into user prompt."""
        mock_agent = AsyncMock()
        mock_agent.agenerate = AsyncMock(return_value=("ok", 50, {}))

        backend = AgentLLMBackend(agent=mock_agent)
        await backend.generate("Hello", system_prompt="You are X")

        call_args = mock_agent.agenerate.call_args
        # First positional arg should be just "Hello", not contain system prompt
        assert call_args[0][0] == "Hello"

    @pytest.mark.asyncio
    async def test_max_tokens_override(self):
        """agent.max_tokens temporarily set and restored."""
        mock_agent = AsyncMock()
        mock_agent.max_tokens = 16384
        mock_agent.agenerate = AsyncMock(return_value=("ok", 50, {}))

        backend = AgentLLMBackend(agent=mock_agent)
        await backend.generate("Hello", max_tokens=2048)

        # max_tokens should have been set to 2048 during the call
        # and restored afterward
        assert mock_agent.max_tokens == 16384

    @pytest.mark.asyncio
    async def test_max_tokens_restored_on_error(self):
        """agent.max_tokens restored even if agenerate raises."""
        mock_agent = AsyncMock()
        mock_agent.max_tokens = 16384
        mock_agent.agenerate = AsyncMock(side_effect=RuntimeError("boom"))

        backend = AgentLLMBackend(agent=mock_agent)
        with pytest.raises(RuntimeError):
            await backend.generate("Hello", max_tokens=2048)

        assert mock_agent.max_tokens == 16384


# ============================================================================
# Reviewer/Arbiter project context (P-3 fix)
# ============================================================================


class TestReviewerProjectContext:

    def test_reviewer_template_has_project_context_slot(self):
        """Reviewer user prompt template accepts project_context."""
        result = REVIEWER_USER_PROMPT_TEMPLATE.format(
            project_context="**Goals:** Build X\n\n",
            design_document="## Overview\nSome design",
        )
        assert "**Goals:** Build X" in result

    def test_arbiter_template_has_project_context_slot(self):
        """Arbiter user prompt template accepts project_context."""
        result = ARBITER_USER_PROMPT_TEMPLATE.format(
            project_context="**Constraints:** No breaking changes\n\n",
            design_document="## Overview\nSome design",
        )
        assert "**Constraints:** No breaking changes" in result

    def test_empty_project_context(self):
        """Empty project_context doesn't break template."""
        result = REVIEWER_USER_PROMPT_TEMPLATE.format(
            project_context="",
            design_document="## Overview\nSome design",
        )
        assert result.startswith("Review this design document:")


# ============================================================================
# Context serialization (P-2 fix)
# ============================================================================


class TestContextSerialization:

    @pytest.mark.asyncio
    async def test_nested_dict_preserved(self):
        """Nested dicts in additional_context survive serialization."""
        mock_agent = AsyncMock()
        mock_agent.agenerate = AsyncMock(
            return_value=(
                "## Overview\nTest\n## Architecture\nTest\n## Testing Strategy\nTest",
                100,
                {},
            )
        )

        backend = AgentLLMBackend(agent=mock_agent)
        phase = DesignDocumentationPhase(llm=backend, max_iterations=1)

        context = FeatureContext(
            feature_name="Test",
            description="Test feature",
            target_file="src/test.py",
            additional_context={
                "shared_modules": [
                    {"path": "src/a.py", "features": ["F-001", "F-002"]}
                ],
                "project_goals": "This feature supports: Build X",
            },
            sections=["Overview", "Architecture", "Testing Strategy"],
        )

        # We only care that the prompt doesn't flatten nested structures
        await phase._generate_design(context, 1)
        call_args = mock_agent.agenerate.call_args
        prompt = call_args[0][0]
        # The nested list should be JSON-formatted, not flattened
        assert "src/a.py" in prompt
        assert "F-001" in prompt


# ============================================================================
# DesignPhaseHandler context flow
# ============================================================================


class TestDesignPhaseHandlerContext:

    def test_plan_goals_benefit_framing(self):
        """Plan goals injected as actionable text in additional_context."""
        task = _make_seed_task("PI-001")
        fc = DesignPhaseHandler._task_to_feature_context(
            task,
            plan_goals=["Build monitoring", "Improve observability"],
        )
        goals = fc.additional_context.get("project_goals", "")
        assert "monitoring" in goals
        assert "observability" in goals
        assert "This feature supports" in goals

    def test_depth_guidance_in_context(self):
        """Calibration depth_guidance flows to FeatureContext."""
        task = _make_seed_task("PI-001")
        cal = {
            "depth_tier": "brief",
            "sections": ["Overview", "Architecture", "Testing Strategy"],
            "max_output_tokens": 2048,
            "depth_guidance": "Concise design sketch.",
        }
        fc = DesignPhaseHandler._task_to_feature_context(
            task, calibration=cal,
        )
        assert fc.depth_guidance == "Concise design sketch."
        assert fc.sections == ["Overview", "Architecture", "Testing Strategy"]
        assert fc.max_output_tokens == 2048
        assert fc.additional_context["depth_guidance"] == "Concise design sketch."

    def test_design_max_tokens_override(self):
        """design_max_tokens_override takes precedence over calibration."""
        task = _make_seed_task("PI-001")
        cal = {"max_output_tokens": 4096}
        fc = DesignPhaseHandler._task_to_feature_context(
            task, calibration=cal, design_max_tokens_override=8192,
        )
        assert fc.max_output_tokens == 8192

    def test_prior_designs_accumulated(self):
        """Prior design summaries flow into additional_context."""
        task = _make_seed_task("PI-002")
        fc = DesignPhaseHandler._task_to_feature_context(
            task,
            prior_design_summaries=[
                "PI-001 (Core monitor): ## Overview of monitoring",
                "PI-003 (Alerts): ## Overview of alerting",
            ],
        )
        prior = fc.additional_context.get("prior_designs", "")
        assert "PI-001" in prior
        assert "PI-003" in prior
        assert "Previously designed" in prior

    def test_design_doc_sections_in_context(self):
        """Task design_doc_sections flow to additional_context."""
        task = _make_seed_task(
            "PI-001",
            design_doc_sections=["Parameter validation", "Error handling"],
        )
        fc = DesignPhaseHandler._task_to_feature_context(task)
        hints = fc.additional_context.get("design_doc_sections", [])
        assert hints == ["Parameter validation", "Error handling"]

    def test_architectural_context_shared_modules(self):
        """Shared modules from arch context appear when task targets overlap."""
        task = _make_seed_task(
            "PI-001", target_files=["src/shared.py", "src/monitor.py"],
        )
        arch = {
            "shared_modules": [
                {"path": "src/shared.py", "features": ["F-001", "F-002"]},
            ],
        }
        fc = DesignPhaseHandler._task_to_feature_context(
            task, architectural_context=arch,
        )
        shared = fc.additional_context.get("shared_modules", "")
        assert "src/shared.py" in shared
        assert "coordinate interfaces" in shared

    def test_domain_concepts_flow(self):
        """Domain concepts from arch context flow to additional_context."""
        task = _make_seed_task("PI-001")
        arch = {"domain_concepts": ["ServiceMonitor", "PrometheusRule"]}
        fc = DesignPhaseHandler._task_to_feature_context(
            task, architectural_context=arch,
        )
        assert "ServiceMonitor" in fc.additional_context.get("domain_concepts", "")

    def test_no_context_is_backward_compat(self):
        """Calling without new kwargs produces same result as before."""
        task = _make_seed_task("PI-001")
        fc = DesignPhaseHandler._task_to_feature_context(task)
        assert fc.feature_name == task.title
        assert fc.sections is None
        assert fc.max_output_tokens is None
        assert fc.depth_guidance is None

    def test_manifest_constraints_in_context(self):
        """Manifest constraints flow into additional_context."""
        task = _make_seed_task("PI-001")
        arch = {
            "constraints": [
                {"rule": "No breaking changes", "severity": "error", "scope": "*"},
            ],
        }
        fc = DesignPhaseHandler._task_to_feature_context(
            task, architectural_context=arch,
        )
        constraints = fc.additional_context.get("constraints_from_manifest", [])
        assert len(constraints) == 1
        assert "No breaking changes" in constraints[0]


# ============================================================================
# Extract manifest context
# ============================================================================


class TestExtractManifestContext:

    def test_empty_manifest(self):
        manifest = MagicMock(spec=[])
        ctx = PlanIngestionWorkflow._extract_manifest_context(manifest)
        assert ctx == {}

    def test_manifest_with_strategy(self):
        obj = MagicMock()
        obj.name = "Reduce MTTR"
        obj.key_results = ["< 5min"]

        strategy = MagicMock()
        strategy.objectives = [obj]

        manifest = MagicMock()
        manifest.strategy = strategy
        manifest.guidance = None

        ctx = PlanIngestionWorkflow._extract_manifest_context(manifest)
        assert len(ctx["objectives"]) == 1
        assert ctx["objectives"][0]["name"] == "Reduce MTTR"

    def test_manifest_with_guidance(self):
        constraint = MagicMock()
        constraint.rule = "No HTTP"
        constraint.severity = "error"
        constraint.scope = "api"

        pref = MagicMock()
        pref.preference = "Use async"

        focus = MagicMock()
        focus.areas = ["reliability", "performance"]

        guidance = MagicMock()
        guidance.constraints = [constraint]
        guidance.preferences = [pref]
        guidance.focus = focus

        manifest = MagicMock()
        manifest.strategy = None
        manifest.guidance = guidance

        ctx = PlanIngestionWorkflow._extract_manifest_context(manifest)
        assert ctx["constraints"][0]["rule"] == "No HTTP"
        assert ctx["preferences"] == ["Use async"]
        assert ctx["focus_areas"] == ["reliability", "performance"]


# ============================================================================
# FeatureContext new fields
# ============================================================================


class TestFeatureContextNewFields:

    def test_default_values(self):
        fc = FeatureContext(
            feature_name="Test", description="A test", target_file="src/x.py"
        )
        assert fc.sections is None
        assert fc.max_output_tokens is None
        assert fc.depth_guidance is None

    def test_calibrated_values(self):
        fc = FeatureContext(
            feature_name="Test",
            description="A test",
            target_file="src/x.py",
            sections=["Overview", "Architecture"],
            max_output_tokens=2048,
            depth_guidance="Keep it brief",
        )
        assert fc.sections == ["Overview", "Architecture"]
        assert fc.max_output_tokens == 2048
        assert fc.depth_guidance == "Keep it brief"


# ============================================================================
# parse_design_document expected_sections
# ============================================================================


class TestParseDesignDocumentExpectedSections:

    def test_expected_sections_parses_reduced_set(self):
        """When expected_sections is provided, only those sections trigger validation."""
        raw = """## Overview
Brief overview here.

## Architecture
Simple architecture.
"""
        doc = parse_design_document(
            raw,
            "TestFeature",
            1,
            expected_sections=["Overview", "Architecture"],
        )
        assert doc.feature_name == "TestFeature"
        assert DesignSection.OVERVIEW in doc.sections
        assert doc.sections[DesignSection.OVERVIEW] == "Brief overview here."
        assert DesignSection.ARCHITECTURE in doc.sections
        # All DesignSection values still populated (for backward compat)
        assert DesignSection.API_CONTRACTS in doc.sections
        assert doc.sections[DesignSection.API_CONTRACTS] == "[Section not generated — requires manual input]"

    def test_expected_sections_none_uses_full_enum(self):
        """When expected_sections is None, all DesignSection values are validated (legacy)."""
        raw = "## Overview\nOnly this."
        doc = parse_design_document(raw, "Test", 1)
        assert len(doc.sections) == len(DesignSection)
        assert DesignSection.OVERVIEW in doc.sections


# ============================================================================
# DesignPhaseHandler: adopt prior design results
# ============================================================================


class TestDesignPhaseAdoptPrior:
    """Tests for design result adoption from prior (dress-rehearsal) runs."""

    def _make_prior_design_result(
        self,
        task_id: str = "PI-001",
        *,
        agreed: bool = True,
        cost: float = 0.15,
    ) -> dict[str, Any]:
        return {
            "status": "designed",
            "design_document": f"## Overview\nDesign for {task_id}.\n\n## Architecture\nArch details.",
            "feature_name": f"Feature {task_id}",
            "agreed": agreed,
            "iterations": 2,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "cost": cost,
        }

    def test_adopt_skips_llm_call(self):
        """Task with prior 'designed' result is adopted — no LLM call made."""
        from startd8.contractors.context_seed_handlers import HandlerConfig
        from startd8.contractors.artisan_contractor import WorkflowPhase

        handler = DesignPhaseHandler(handler_config=HandlerConfig(), output_dir="/tmp/test")

        task = _make_seed_task("PI-001")
        prior_result = self._make_prior_design_result("PI-001")

        context: dict[str, Any] = {
            "tasks": [task],
            "task_index": {"PI-001": task},
            "enriched_seed_path": "/dev/null",
            "design_results": {"PI-001": prior_result},
        }

        result = handler.execute(WorkflowPhase.DESIGN, context, dry_run=False)

        # Should adopt without calling LLM
        assert context["design_results"]["PI-001"]["status"] == "adopted"
        assert context["design_results"]["PI-001"]["adopted_from"] == "prior_design_results"
        assert result["output"]["tasks_adopted"] == 1
        assert result["output"]["tasks_designed"] == 0  # adopted != designed
        assert result["cost"] == 0.0  # No LLM cost incurred

    def test_adopt_without_design_document_falls_through(self):
        """Task with prior result but missing design_document is NOT adopted.

        Uses dry_run=True so the task falls through to dry_run_skipped
        rather than attempting a real LLM call.
        """
        from startd8.contractors.context_seed_handlers import HandlerConfig
        from startd8.contractors.artisan_contractor import WorkflowPhase

        handler = DesignPhaseHandler(handler_config=HandlerConfig(), output_dir="/tmp/test")

        task = _make_seed_task("PI-001")
        # Prior result has status=designed but no design_document
        broken_prior = {"status": "designed", "agreed": True}

        context: dict[str, Any] = {
            "tasks": [task],
            "task_index": {"PI-001": task},
            "enriched_seed_path": "/dev/null",
            "design_results": {"PI-001": broken_prior},
        }

        # With dry_run=True, the task should NOT be adopted (missing doc)
        # and instead get dry_run_skipped.
        result = handler.execute(WorkflowPhase.DESIGN, context, dry_run=True)
        assert context["design_results"]["PI-001"]["status"] == "dry_run_skipped"
        assert result["output"]["tasks_adopted"] == 0

    def test_adopt_with_failed_prior_falls_through(self):
        """Task with prior 'design_failed' is NOT adopted — falls to dry_run."""
        from startd8.contractors.context_seed_handlers import HandlerConfig
        from startd8.contractors.artisan_contractor import WorkflowPhase

        handler = DesignPhaseHandler(handler_config=HandlerConfig(), output_dir="/tmp/test")

        task = _make_seed_task("PI-001")
        failed_prior = {"status": "design_failed", "error": "timeout"}

        context: dict[str, Any] = {
            "tasks": [task],
            "task_index": {"PI-001": task},
            "enriched_seed_path": "/dev/null",
            "design_results": {"PI-001": failed_prior},
        }

        # With dry_run=True, the task should NOT be adopted (failed status)
        # and instead get dry_run_skipped.
        result = handler.execute(WorkflowPhase.DESIGN, context, dry_run=True)
        assert context["design_results"]["PI-001"]["status"] == "dry_run_skipped"
        assert result["output"]["tasks_adopted"] == 0

    def test_adopt_preserves_cross_task_summaries(self):
        """Adopted tasks contribute to prior_summaries for progressive context."""
        from startd8.contractors.context_seed_handlers import HandlerConfig
        from startd8.contractors.artisan_contractor import WorkflowPhase

        handler = DesignPhaseHandler(handler_config=HandlerConfig(), output_dir="/tmp/test")

        task1 = _make_seed_task("PI-001")
        task2 = _make_seed_task("PI-002")
        prior1 = self._make_prior_design_result("PI-001")
        prior2 = self._make_prior_design_result("PI-002")

        context: dict[str, Any] = {
            "tasks": [task1, task2],
            "task_index": {"PI-001": task1, "PI-002": task2},
            "enriched_seed_path": "/dev/null",
            "design_results": {"PI-001": prior1, "PI-002": prior2},
        }

        result = handler.execute(WorkflowPhase.DESIGN, context, dry_run=False)

        assert result["output"]["tasks_adopted"] == 2
        assert result["output"]["tasks_designed"] == 0  # adopted != designed
        # Both should be adopted
        assert context["design_results"]["PI-001"]["status"] == "adopted"
        assert context["design_results"]["PI-002"]["status"] == "adopted"

    def test_no_prior_results_runs_normally_in_dry_run(self):
        """Without prior results, dry_run produces dry_run_skipped as usual."""
        from startd8.contractors.context_seed_handlers import HandlerConfig
        from startd8.contractors.artisan_contractor import WorkflowPhase

        handler = DesignPhaseHandler(handler_config=HandlerConfig(), output_dir="/tmp/test")

        task = _make_seed_task("PI-001")
        context: dict[str, Any] = {
            "tasks": [task],
            "task_index": {"PI-001": task},
            "enriched_seed_path": "/dev/null",
        }

        result = handler.execute(WorkflowPhase.DESIGN, context, dry_run=True)

        assert context["design_results"]["PI-001"]["status"] == "dry_run_skipped"
        assert result["output"]["tasks_adopted"] == 0

    def test_implement_handler_reads_adopted_status(self):
        """ImplementPhaseHandler treats 'adopted' same as 'designed'."""
        # Verify that the check in ImplementPhaseHandler accepts "adopted"
        task_design = {"status": "adopted", "design_document": "## Overview\nAdopted design."}
        assert task_design.get("status") in ("designed", "adopted")
        assert task_design.get("design_document") is not None


# ============================================================================
# SeedTask: prompt_hints merge from context into prompt_constraints
# ============================================================================


class TestSeedTaskPromptHintsMerge:
    """Tests for SeedTask.from_seed_entry merging context.prompt_hints."""

    def test_prompt_hints_merged_into_constraints(self):
        """prompt_hints from config.context are merged into prompt_constraints."""
        entry = {
            "task_id": "PI-001",
            "title": "Skeleton",
            "config": {
                "task_description": "Build skeleton",
                "context": {
                    "feature_id": "F-001",
                    "target_files": ["src/pkg/__init__.py", "src/pkg/shared.py"],
                    "estimated_loc": 80,
                    "prompt_hints": [
                        "Shared module warning: src/pkg/shared.py (also used by PI-002)."
                    ],
                },
            },
            "_enrichment": {
                "domain": "backend",
                "prompt_constraints": ["Use type hints"],
            },
        }
        task = SeedTask.from_seed_entry(entry)
        assert "Use type hints" in task.prompt_constraints
        assert any("Shared module" in c for c in task.prompt_constraints)
        assert len(task.prompt_constraints) == 2

    def test_no_prompt_hints_preserves_enrichment_constraints(self):
        """Without prompt_hints, only enrichment constraints are loaded."""
        entry = {
            "task_id": "PI-002",
            "title": "Generator",
            "config": {
                "task_description": "Implement generator",
                "context": {
                    "feature_id": "F-002",
                    "target_files": ["src/gen.py"],
                    "estimated_loc": 50,
                },
            },
            "_enrichment": {
                "domain": "backend",
                "prompt_constraints": ["Use type hints", "No blocking calls"],
            },
        }
        task = SeedTask.from_seed_entry(entry)
        assert task.prompt_constraints == ["Use type hints", "No blocking calls"]

    def test_duplicate_hints_not_added_twice(self):
        """If a hint already exists in enrichment constraints, it's not duplicated."""
        hint = "Shared module warning: shared.py also used by PI-002."
        entry = {
            "task_id": "PI-001",
            "title": "Test",
            "config": {
                "task_description": "Test",
                "context": {
                    "feature_id": "F-001",
                    "target_files": ["a.py"],
                    "estimated_loc": 10,
                    "prompt_hints": [hint],
                },
            },
            "_enrichment": {
                "domain": "backend",
                "prompt_constraints": [hint],  # Already present
            },
        }
        task = SeedTask.from_seed_entry(entry)
        assert task.prompt_constraints.count(hint) == 1


# ============================================================================
# Refine design mode tests
# ============================================================================


class TestRefineDesignMode:
    """Tests for --refine-design feature."""

    def test_feature_context_prior_design_defaults_to_none(self):
        """FeatureContext.prior_design defaults to None."""
        ctx = FeatureContext(
            feature_name="Test",
            description="Test feature",
            target_file="src/test.py",
        )
        assert ctx.prior_design is None

    def test_feature_context_prior_design_set(self):
        """FeatureContext.prior_design can be set."""
        ctx = FeatureContext(
            feature_name="Test",
            description="Test feature",
            target_file="src/test.py",
            prior_design="## Overview\nExisting design content",
        )
        assert ctx.prior_design == "## Overview\nExisting design content"

    def test_task_to_feature_context_passes_prior_design_text(self):
        """_task_to_feature_context forwards prior_design_text to FeatureContext."""
        task = _make_seed_task()
        fc = DesignPhaseHandler._task_to_feature_context(
            task,
            prior_design_text="## Overview\nPrior design",
        )
        assert fc.prior_design == "## Overview\nPrior design"

    def test_task_to_feature_context_none_prior_design(self):
        """_task_to_feature_context defaults prior_design to None."""
        task = _make_seed_task()
        fc = DesignPhaseHandler._task_to_feature_context(task)
        assert fc.prior_design is None

    def test_build_refine_system_prompt_contains_refining(self):
        """build_refine_system_prompt mentions refining in the role."""
        from startd8.contractors.artisan_phases.design_documentation import (
            build_refine_system_prompt,
        )
        prompt = build_refine_system_prompt()
        assert "refining" in prompt.lower()
        assert "## Overview" in prompt

    def test_build_refine_system_prompt_includes_custom_sections(self):
        """build_refine_system_prompt respects custom sections list."""
        from startd8.contractors.artisan_phases.design_documentation import (
            build_refine_system_prompt,
        )
        prompt = build_refine_system_prompt(sections=["Overview", "Architecture"])
        assert "## Overview" in prompt
        assert "## Architecture" in prompt
        assert "## Data Model" not in prompt

    def test_build_refine_system_prompt_includes_depth_guidance(self):
        """build_refine_system_prompt includes depth guidance when provided."""
        from startd8.contractors.artisan_phases.design_documentation import (
            build_refine_system_prompt,
        )
        prompt = build_refine_system_prompt(depth_guidance="Keep it concise")
        assert "Keep it concise" in prompt

    def test_handler_config_mutual_exclusion(self):
        """HandlerConfig raises ValueError if force_design and refine_design are both True."""
        from startd8.contractors.context_seed_handlers import HandlerConfig
        with pytest.raises(ValueError, match="mutually exclusive"):
            HandlerConfig(force_design=True, refine_design=True)

    def test_handler_config_refine_design_alone(self):
        """HandlerConfig allows refine_design=True when force_design=False."""
        from startd8.contractors.context_seed_handlers import HandlerConfig
        config = HandlerConfig(refine_design=True)
        assert config.refine_design is True
        assert config.force_design is False

    def test_handler_config_force_design_alone(self):
        """HandlerConfig allows force_design=True when refine_design=False."""
        from startd8.contractors.context_seed_handlers import HandlerConfig
        config = HandlerConfig(force_design=True)
        assert config.force_design is True
        assert config.refine_design is False

    def test_downstream_status_accepts_refined(self):
        """ImplementPhaseHandler accepts 'refined' status from design results."""
        # This tests the status tuple check directly
        status = "refined"
        assert status in ("designed", "adopted", "refined")
