"""
Unit tests for PlanIngestionWorkflow.

All tests mock BaseAgent.generate() — no real LLM calls.
"""

import json
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from startd8.workflows.builtin.plan_ingestion_models import (
    ArtisanContextSeed,
    ComplexityScore,
    ContractorRoute,
    IngestionPhase,
    IngestionState,
    ParsedFeature,
    ParsedPlan,
    PlanIngestionResult,
)
from startd8.workflows.builtin.plan_ingestion_workflow import (
    PlanIngestionWorkflow,
    _extract_json_from_response,
    _parse_context_files,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_PLAN = textwrap.dedent("""\
    # My Sample Plan

    ## Goals
    - Build a widget
    - Test the widget

    ## Features
    ### F-001: Widget core
    Implement the core widget in `src/widget.py`.

    ### F-002: Widget tests
    Write tests in `tests/test_widget.py`. Depends on F-001.
""")

PARSE_JSON = json.dumps({
    "title": "My Sample Plan",
    "goals": ["Build a widget", "Test the widget"],
    "features": [
        {
            "feature_id": "F-001",
            "name": "Widget core",
            "description": "Implement the core widget",
            "target_files": ["src/widget.py"],
            "dependencies": [],
            "estimated_loc": 100,
            "labels": ["core"],
        },
        {
            "feature_id": "F-002",
            "name": "Widget tests",
            "description": "Write tests",
            "target_files": ["tests/test_widget.py"],
            "dependencies": ["F-001"],
            "estimated_loc": 50,
            "labels": ["tests"],
        },
    ],
    "mentioned_files": ["src/widget.py", "tests/test_widget.py"],
    "dependency_graph": {"F-002": ["F-001"]},
})

ASSESS_JSON_PRIME = json.dumps({
    "feature_count": 20,
    "cross_file_deps": 15,
    "api_surface": 10,
    "test_complexity": 25,
    "integration_depth": 20,
    "domain_novelty": 10,
    "ambiguity": 15,
    "composite": 30,
    "reasoning": "Simple plan with two features and minimal cross-file deps.",
    "route": "prime",
})

ASSESS_JSON_ARTISAN = json.dumps({
    "feature_count": 60,
    "cross_file_deps": 55,
    "api_surface": 50,
    "test_complexity": 65,
    "integration_depth": 70,
    "domain_novelty": 50,
    "ambiguity": 55,
    "composite": 65,
    "reasoning": "Complex plan with many features and deep integration.",
    "route": "artisan",
})

TRANSFORM_YAML = textwrap.dedent("""\
    project:
      id: sample
      name: Sample Project
      sprint_id: sprint-1

    tasks:
      - task_id: PI-001
        title: "Widget core"
        task_type: task
        story_points: 3
        priority: high
        labels: [core]
        config:
          task_description: |
            Implement the core widget.
""")

TRANSFORM_MARKDOWN = textwrap.dedent("""\
    # My Sample Plan

    ## Overview
    Build and test a widget.

    ## Data Models
    Widget data model.

    ## Architecture
    Simple architecture.

    ## Phase Breakdown
    ### Phase 1: Core
    Build the widget core.
""")


def _make_mock_agent(name="test-agent"):
    """Create a MagicMock agent with proper name/model."""
    agent = MagicMock()
    agent.name = name
    agent.model = "mock-model"
    agent.max_tokens = 4096
    return agent


def _mock_generate_return(response_text, in_tok=100, out_tok=50, cost=0.01):
    """Build a 3-tuple return value for agent.generate()."""
    token_usage = MagicMock()
    token_usage.input_tokens = in_tok
    token_usage.input = in_tok
    token_usage.output_tokens = out_tok
    token_usage.output = out_tok
    token_usage.cost = cost
    return (response_text, 150, token_usage)


# ---------------------------------------------------------------------------
# TestPlanIngestionModels
# ---------------------------------------------------------------------------

class TestPlanIngestionModels:
    def test_contractor_route_values(self):
        assert ContractorRoute.PRIME == "prime"
        assert ContractorRoute.ARTISAN == "artisan"

    def test_ingestion_phase_values(self):
        assert IngestionPhase.PARSE == "parse"
        assert IngestionPhase.ASSESS == "assess"
        assert IngestionPhase.TRANSFORM == "transform"
        assert IngestionPhase.REFINE == "refine"
        assert IngestionPhase.EMIT == "emit"
        assert IngestionPhase.COMPLETED == "completed"
        assert IngestionPhase.FAILED == "failed"

    def test_parsed_feature_defaults(self):
        f = ParsedFeature(feature_id="F-001", name="Test")
        assert f.description == ""
        assert f.target_files == []
        assert f.dependencies == []
        assert f.estimated_loc == 0
        assert f.labels == []

    def test_parsed_plan_defaults(self):
        p = ParsedPlan(title="Test Plan")
        assert p.goals == []
        assert p.features == []
        assert p.dependency_graph == {}
        assert p.mentioned_files == []
        assert p.raw_text == ""
        assert p.input_tokens == 0

    def test_complexity_score_defaults(self):
        c = ComplexityScore()
        assert c.composite == 0
        assert c.route is None
        assert c.reasoning == ""

    def test_ingestion_state_to_dict(self):
        state = IngestionState()
        d = state.to_dict()
        assert d["current_phase"] == "parse"
        assert d["route"] is None
        assert d["total_cost"] == 0.0

    def test_ingestion_state_with_route(self):
        state = IngestionState(route=ContractorRoute.PRIME)
        d = state.to_dict()
        assert d["route"] == "prime"

    def test_ingestion_state_to_dict_with_plan_and_complexity(self):
        state = IngestionState(
            parsed_plan=ParsedPlan(
                title="My Plan",
                features=[
                    ParsedFeature(feature_id="F-001", name="A"),
                    ParsedFeature(feature_id="F-002", name="B"),
                ],
            ),
            complexity=ComplexityScore(composite=55, route=ContractorRoute.ARTISAN),
        )
        d = state.to_dict()
        assert d["parsed_plan_title"] == "My Plan"
        assert d["parsed_plan_feature_count"] == 2
        assert d["complexity_composite"] == 55
        assert d["complexity_route"] == "artisan"

    def test_ingestion_state_to_dict_without_plan_omits_keys(self):
        state = IngestionState()
        d = state.to_dict()
        assert "parsed_plan_title" not in d
        assert "complexity_composite" not in d

    def test_plan_ingestion_result_defaults(self):
        r = PlanIngestionResult(success=True)
        assert r.success is True
        assert r.route is None
        assert r.plan_document_path is None
        assert r.total_cost == 0.0
        assert r.refine_rounds_completed == 0


# ---------------------------------------------------------------------------
# TestPlanIngestionMetadata
# ---------------------------------------------------------------------------

class TestPlanIngestionMetadata:
    def setup_method(self):
        self.wf = PlanIngestionWorkflow()

    def test_workflow_id(self):
        assert self.wf.metadata.workflow_id == "plan-ingestion"

    def test_name(self):
        assert "Plan Ingestion" in self.wf.metadata.name

    def test_capabilities(self):
        caps = self.wf.metadata.capabilities
        assert "plan-transformation" in caps
        assert "complexity-assessment" in caps
        assert "document-generation" in caps

    def test_requires_agents_false(self):
        assert self.wf.metadata.requires_agents is False

    def test_required_inputs(self):
        required = [i.name for i in self.wf.metadata.inputs if i.required]
        assert "plan_path" in required

    def test_optional_inputs(self):
        optional = [i.name for i in self.wf.metadata.inputs if not i.required]
        assert "output_dir" in optional
        assert "assessor_agent" in optional
        assert "review_rounds" in optional
        assert "force_route" in optional
        assert "complexity_threshold" in optional


# ---------------------------------------------------------------------------
# TestPlanIngestionValidation
# ---------------------------------------------------------------------------

class TestPlanIngestionValidation:
    def setup_method(self):
        self.wf = PlanIngestionWorkflow()

    def test_missing_plan_path(self):
        result = self.wf.validate_config({})
        assert not result.valid
        assert any("plan_path" in e for e in result.errors)

    def test_nonexistent_file(self):
        result = self.wf.validate_config({"plan_path": "/nonexistent/file.md"})
        assert not result.valid
        assert any("does not exist" in e for e in result.errors)

    def test_valid_config(self, tmp_path):
        plan_file = tmp_path / "plan.md"
        plan_file.write_text("# Plan")
        result = self.wf.validate_config({"plan_path": str(plan_file)})
        assert result.valid

    def test_invalid_force_route(self, tmp_path):
        plan_file = tmp_path / "plan.md"
        plan_file.write_text("# Plan")
        result = self.wf.validate_config({
            "plan_path": str(plan_file),
            "force_route": "invalid",
        })
        assert not result.valid
        assert any("force_route" in e for e in result.errors)

    def test_valid_force_route_prime(self, tmp_path):
        plan_file = tmp_path / "plan.md"
        plan_file.write_text("# Plan")
        result = self.wf.validate_config({
            "plan_path": str(plan_file),
            "force_route": "prime",
        })
        assert result.valid

    def test_valid_force_route_artisan(self, tmp_path):
        plan_file = tmp_path / "plan.md"
        plan_file.write_text("# Plan")
        result = self.wf.validate_config({
            "plan_path": str(plan_file),
            "force_route": "artisan",
        })
        assert result.valid

    def test_invalid_low_quality_policy(self, tmp_path):
        plan_file = tmp_path / "plan.md"
        plan_file.write_text("# Plan")
        result = self.wf.validate_config({
            "plan_path": str(plan_file),
            "low_quality_policy": "unknown",
        })
        assert not result.valid
        assert any("low_quality_policy" in e for e in result.errors)


# ---------------------------------------------------------------------------
# TestExtractJson
# ---------------------------------------------------------------------------

class TestExtractJson:
    def test_plain_json(self):
        data = _extract_json_from_response('{"key": "value"}')
        assert data == {"key": "value"}

    def test_json_in_code_fence(self):
        text = '```json\n{"key": "value"}\n```'
        data = _extract_json_from_response(text)
        assert data == {"key": "value"}

    def test_malformed_json_raises(self):
        with pytest.raises((json.JSONDecodeError, ValueError)):
            _extract_json_from_response("not json at all")


# ---------------------------------------------------------------------------
# TestParsePhase
# ---------------------------------------------------------------------------

class TestParsePhase:
    def setup_method(self):
        self.wf = PlanIngestionWorkflow()

    def test_parse_extracts_features(self):
        agent = _make_mock_agent()
        agent.generate.return_value = _mock_generate_return(PARSE_JSON)

        parsed, step = self.wf._phase_parse(SAMPLE_PLAN, agent)

        assert parsed.title == "My Sample Plan"
        assert len(parsed.features) == 2
        assert parsed.features[0].feature_id == "F-001"
        assert parsed.features[0].name == "Widget core"
        assert parsed.features[1].dependencies == ["F-001"]
        assert "src/widget.py" in parsed.mentioned_files
        assert step.error is None
        assert step.step_name == "parse"

    def test_parse_malformed_json(self):
        agent = _make_mock_agent()
        agent.generate.return_value = _mock_generate_return("not json")

        parsed, step = self.wf._phase_parse(SAMPLE_PLAN, agent)
        assert parsed is None
        assert step.error is not None
        assert "Failed to parse JSON" in step.error

    def test_parse_metrics(self):
        agent = _make_mock_agent()
        agent.generate.return_value = _mock_generate_return(PARSE_JSON, in_tok=200, out_tok=100, cost=0.05)

        parsed, step = self.wf._phase_parse(SAMPLE_PLAN, agent)

        assert step.input_tokens == 200
        assert step.output_tokens == 100
        assert step.cost == 0.05


# ---------------------------------------------------------------------------
# TestAssessPhase
# ---------------------------------------------------------------------------

class TestAssessPhase:
    def setup_method(self):
        self.wf = PlanIngestionWorkflow()
        self.parsed = ParsedPlan(
            title="Test Plan",
            goals=["Goal 1"],
            features=[
                ParsedFeature(feature_id="F-001", name="Feature 1", target_files=["a.py"]),
                ParsedFeature(feature_id="F-002", name="Feature 2", dependencies=["F-001"]),
            ],
            mentioned_files=["a.py", "b.py"],
        )

    def test_prime_route_low_score(self):
        agent = _make_mock_agent()
        agent.generate.return_value = _mock_generate_return(ASSESS_JSON_PRIME)

        score, step = self.wf._phase_assess(self.parsed, agent, threshold=40, force_route=None)

        assert score.composite == 30
        assert score.route == ContractorRoute.PRIME
        assert step.error is None

    def test_artisan_route_high_score(self):
        agent = _make_mock_agent()
        agent.generate.return_value = _mock_generate_return(ASSESS_JSON_ARTISAN)

        score, step = self.wf._phase_assess(self.parsed, agent, threshold=40, force_route=None)

        assert score.composite == 65
        assert score.route == ContractorRoute.ARTISAN

    def test_force_route_overrides_score(self):
        agent = _make_mock_agent()
        # Score is 65 (artisan), but force_route=prime
        agent.generate.return_value = _mock_generate_return(ASSESS_JSON_ARTISAN)

        score, step = self.wf._phase_assess(self.parsed, agent, threshold=40, force_route="prime")

        assert score.route == ContractorRoute.PRIME

    def test_custom_threshold(self):
        agent = _make_mock_agent()
        # Score is 65 but threshold is 70 → should route to prime
        agent.generate.return_value = _mock_generate_return(ASSESS_JSON_ARTISAN)

        score, step = self.wf._phase_assess(self.parsed, agent, threshold=70, force_route=None)

        assert score.composite == 65
        assert score.route == ContractorRoute.PRIME

    def test_malformed_json(self):
        agent = _make_mock_agent()
        agent.generate.return_value = _mock_generate_return("garbage")

        score, step = self.wf._phase_assess(self.parsed, agent, threshold=40, force_route=None)
        assert score is None
        assert step.error is not None
        assert "Failed to parse assessment JSON" in step.error


# ---------------------------------------------------------------------------
# TestTransformPhase
# ---------------------------------------------------------------------------

class TestTransformPhase:
    def setup_method(self):
        self.wf = PlanIngestionWorkflow()
        self.parsed = ParsedPlan(
            title="Test Plan",
            goals=["Goal 1"],
            features=[
                ParsedFeature(
                    feature_id="F-001",
                    name="Feature 1",
                    description="Build it",
                    target_files=["src/a.py"],
                    estimated_loc=50,
                ),
            ],
            mentioned_files=["src/a.py"],
            dependency_graph={},
        )

    def test_prime_yaml_output(self, tmp_path):
        agent = _make_mock_agent()
        agent.generate.return_value = _mock_generate_return(TRANSFORM_YAML)

        doc_path, step = self.wf._phase_transform(
            self.parsed, ContractorRoute.PRIME, agent, tmp_path,
        )

        assert doc_path.name == "plan-ingestion-tasks.yaml"
        assert doc_path.exists()
        assert step.error is None

        import yaml
        content = yaml.safe_load(doc_path.read_text())
        assert "project" in content

    def test_artisan_markdown_output(self, tmp_path):
        agent = _make_mock_agent()
        agent.generate.return_value = _mock_generate_return(TRANSFORM_MARKDOWN)

        doc_path, step = self.wf._phase_transform(
            self.parsed, ContractorRoute.ARTISAN, agent, tmp_path,
        )

        assert doc_path.name == "PLAN-ingested.md"
        assert doc_path.exists()
        assert step.error is None
        assert "## Overview" in doc_path.read_text()

    def test_invalid_yaml_returns_error(self, tmp_path):
        agent = _make_mock_agent()
        agent.generate.return_value = _mock_generate_return("not: valid: yaml: [")

        doc_path, step = self.wf._phase_transform(
            self.parsed, ContractorRoute.PRIME, agent, tmp_path,
        )
        assert doc_path is None
        assert step.error is not None
        assert "Generated YAML is invalid" in step.error


# ---------------------------------------------------------------------------
# TestRefinePhase
# ---------------------------------------------------------------------------

class TestRefinePhase:
    def setup_method(self):
        self.wf = PlanIngestionWorkflow()

    def test_skip_when_zero_rounds(self, tmp_path):
        rounds, steps, cost, review_output = self.wf._phase_refine(
            tmp_path / "plan.md",
            review_rounds=0,
            review_quality_tier="flagship",
            scope=None,
            context_files=None,
            feature_requirements=None,
            warn_cost_usd=None,
            max_cost_usd=None,
        )
        assert rounds == 0
        assert steps == []
        assert cost == 0.0
        assert review_output == {}

    @patch("startd8.workflows.builtin.architectural_review_log_workflow.ArchitecturalReviewLogWorkflow")
    def test_delegates_to_review_workflow(self, MockReviewWf, tmp_path):
        plan_file = tmp_path / "plan.md"
        plan_file.write_text("# Plan")

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.metrics = MagicMock(total_cost=0.15)
        mock_result.steps = [
            MagicMock(
                step_name="review-r1",
                agent_name="reviewer",
                input="",
                output="reviewed",
                time_ms=100,
                input_tokens=50,
                output_tokens=30,
                cost=0.05,
                error=None,
            ),
        ]
        mock_result.error = None
        mock_result.output = {"triage": {"accepted": 1, "rejected": 0}, "apply": {}}

        mock_instance = MagicMock()
        mock_instance.run.return_value = mock_result
        MockReviewWf.return_value = mock_instance

        rounds, steps, cost, review_output = self.wf._phase_refine(
            plan_file,
            review_rounds=2,
            review_quality_tier="flagship",
            scope="Review scope",
            context_files=["src/a.py"],
            feature_requirements=["reqs/feature.md"],
            warn_cost_usd=1.0,
            max_cost_usd=5.0,
        )

        assert rounds == 1  # 1 step in the mocked result
        assert len(steps) == 1
        assert steps[0].step_name == "refine:review-r1"
        assert cost == 0.15
        assert review_output == mock_result.output

        # Verify the config passed to the review workflow
        call_config = mock_instance.run.call_args[0][0]
        assert call_config["document_path"] == str(plan_file)
        assert call_config["quality_tier"] == "flagship"
        assert call_config["reviewer_count"] == 2
        assert call_config["scope"] == "Review scope"
        assert call_config["context_files"] == ["src/a.py"]
        assert call_config["feature_requirements"] == ["reqs/feature.md"]

    @patch("startd8.workflows.builtin.architectural_review_log_workflow.ArchitecturalReviewLogWorkflow")
    def test_config_passthrough_enable_flags(self, MockReviewWf, tmp_path):
        """enable_apply, enable_prompt_caching, enable_triage forwarded to review config."""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text("# Plan")

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.metrics = MagicMock(total_cost=0.0)
        mock_result.steps = []
        mock_result.error = None
        mock_result.output = {}

        mock_instance = MagicMock()
        mock_instance.run.return_value = mock_result
        MockReviewWf.return_value = mock_instance

        self.wf._phase_refine(
            plan_file,
            review_rounds=1,
            review_quality_tier="flagship",
            scope=None,
            context_files=None,
            feature_requirements=None,
            warn_cost_usd=None,
            max_cost_usd=None,
            enable_apply=True,
            enable_prompt_caching=False,
            enable_triage=True,
        )

        call_config = mock_instance.run.call_args[0][0]
        assert call_config["enable_apply"] is True
        assert call_config["enable_prompt_caching"] is False
        assert call_config["enable_triage"] is True

    @patch("startd8.workflows.builtin.architectural_review_log_workflow.ArchitecturalReviewLogWorkflow")
    def test_failure_returns_empty_review_output(self, MockReviewWf, tmp_path):
        """When review workflow fails, review_output is empty dict."""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text("# Plan")

        mock_result = MagicMock()
        mock_result.success = False
        mock_result.metrics = MagicMock(total_cost=0.0)
        mock_result.steps = []
        mock_result.error = "Review failed"
        mock_result.output = {"triage": {"accepted": 2}}

        mock_instance = MagicMock()
        mock_instance.run.return_value = mock_result
        MockReviewWf.return_value = mock_instance

        rounds, steps, cost, review_output = self.wf._phase_refine(
            plan_file,
            review_rounds=1,
            review_quality_tier="flagship",
            scope=None,
            context_files=None,
            feature_requirements=None,
            warn_cost_usd=None,
            max_cost_usd=None,
        )

        assert rounds == 0
        assert review_output == {}


# ---------------------------------------------------------------------------
# TestEmitPhase
# ---------------------------------------------------------------------------

class TestEmitPhase:
    def setup_method(self):
        self.wf = PlanIngestionWorkflow()

    def test_review_config_structure(self, tmp_path):
        doc_path = tmp_path / "PLAN-ingested.md"
        doc_path.write_text("# Plan")
        complexity = ComplexityScore(composite=45, reasoning="Medium")

        config_path, data, _, _tracking = self.wf._phase_emit(
            doc_path,
            ContractorRoute.ARTISAN,
            complexity,
            tmp_path,
            review_rounds=2,
            review_quality_tier="flagship",
            scope="Test scope",
            context_files=["src/a.py", "src/b.py"],
            warn_cost_usd=None,
            max_cost_usd=None,
        )

        assert config_path.name == "review-config.json"
        assert config_path.exists()

        loaded = json.loads(config_path.read_text())
        assert loaded["document_path"] == str(doc_path)
        assert loaded["quality_tier"] == "flagship"
        assert loaded["reviewer_count"] == 2
        assert loaded["scope"] == "Test scope"
        assert loaded["context_files"] == ["src/a.py", "src/b.py"]
        assert loaded["_ingestion_metadata"]["route"] == "artisan"
        assert loaded["_ingestion_metadata"]["complexity_score"] == 45

    def test_document_path_correctness(self, tmp_path):
        doc_path = tmp_path / "plan-ingestion-tasks.yaml"
        doc_path.write_text("project: {}")
        complexity = ComplexityScore(composite=20)

        config_path, data, _, _tracking = self.wf._phase_emit(
            doc_path,
            ContractorRoute.PRIME,
            complexity,
            tmp_path,
            review_rounds=2,
            review_quality_tier="flagship",
            scope=None,
            context_files=None,
            warn_cost_usd=None,
            max_cost_usd=None,
        )

        loaded = json.loads(config_path.read_text())
        assert loaded["document_path"] == str(doc_path)


# ---------------------------------------------------------------------------
# TestParseContextFiles
# ---------------------------------------------------------------------------

class TestParseContextFiles:
    def test_none_returns_none(self):
        assert _parse_context_files(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_context_files("") is None

    def test_empty_list_returns_none(self):
        assert _parse_context_files([]) is None

    def test_comma_separated_string(self):
        result = _parse_context_files("src/a.py, src/b.py")
        assert result == ["src/a.py", "src/b.py"]

    def test_single_string(self):
        result = _parse_context_files("src/a.py")
        assert result == ["src/a.py"]

    def test_list_passthrough(self):
        result = _parse_context_files(["src/a.py", "src/b.py"])
        assert result == ["src/a.py", "src/b.py"]

    def test_strips_whitespace(self):
        result = _parse_context_files("  src/a.py ,  src/b.py  , ")
        assert result == ["src/a.py", "src/b.py"]


# ---------------------------------------------------------------------------
# TestEndToEnd
# ---------------------------------------------------------------------------

class TestEndToEnd:
    def setup_method(self):
        self.wf = PlanIngestionWorkflow()

    @patch("startd8.workflows.builtin.architectural_review_log_workflow.ArchitecturalReviewLogWorkflow")
    @patch("startd8.workflows.builtin.plan_ingestion_workflow.resolve_agent_spec")
    def test_full_prime_flow(self, mock_resolve, MockReviewWf, tmp_path):
        # Setup plan file
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(SAMPLE_PLAN)

        # Mock agent
        agent = _make_mock_agent()
        agent.generate.side_effect = [
            _mock_generate_return(PARSE_JSON, cost=0.01),    # parse
            _mock_generate_return(ASSESS_JSON_PRIME, cost=0.02),  # assess
            _mock_generate_return(TRANSFORM_YAML, cost=0.03),     # transform
        ]
        mock_resolve.return_value = agent

        # Mock review workflow
        mock_review_result = MagicMock()
        mock_review_result.success = True
        mock_review_result.metrics = MagicMock(total_cost=0.05)
        mock_review_result.steps = []
        mock_review_result.error = None
        mock_review_result.output = {}
        mock_review_instance = MagicMock()
        mock_review_instance.run.return_value = mock_review_result
        MockReviewWf.return_value = mock_review_instance

        result = self.wf.run({
            "plan_path": str(plan_file),
            "output_dir": str(tmp_path),
            "review_rounds": 1,
        })

        assert result.success
        assert result.output["route"] == "prime"
        assert Path(result.output["plan_document_path"]).exists()
        assert Path(result.output["review_config_path"]).exists()

        # Verify YAML was written
        yaml_path = tmp_path / "plan-ingestion-tasks.yaml"
        assert yaml_path.exists()

    @patch("startd8.workflows.builtin.architectural_review_log_workflow.ArchitecturalReviewLogWorkflow")
    @patch("startd8.workflows.builtin.plan_ingestion_workflow.resolve_agent_spec")
    def test_full_artisan_flow(self, mock_resolve, MockReviewWf, tmp_path):
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(SAMPLE_PLAN)

        agent = _make_mock_agent()
        agent.generate.side_effect = [
            _mock_generate_return(PARSE_JSON, cost=0.01),
            _mock_generate_return(ASSESS_JSON_ARTISAN, cost=0.02),
            _mock_generate_return(TRANSFORM_MARKDOWN, cost=0.03),
        ]
        mock_resolve.return_value = agent

        mock_review_result = MagicMock()
        mock_review_result.success = True
        mock_review_result.metrics = MagicMock(total_cost=0.05)
        mock_review_result.steps = []
        mock_review_result.error = None
        mock_review_result.output = {}
        mock_review_instance = MagicMock()
        mock_review_instance.run.return_value = mock_review_result
        MockReviewWf.return_value = mock_review_instance

        result = self.wf.run({
            "plan_path": str(plan_file),
            "output_dir": str(tmp_path),
            "review_rounds": 1,
        })

        assert result.success
        assert result.output["route"] == "artisan"
        md_path = tmp_path / "PLAN-ingested.md"
        assert md_path.exists()

    @patch("startd8.workflows.builtin.architectural_review_log_workflow.ArchitecturalReviewLogWorkflow")
    @patch("startd8.workflows.builtin.plan_ingestion_workflow.resolve_agent_spec")
    def test_cost_accumulation(self, mock_resolve, MockReviewWf, tmp_path):
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(SAMPLE_PLAN)

        agent = _make_mock_agent()
        agent.generate.side_effect = [
            _mock_generate_return(PARSE_JSON, cost=0.10),
            _mock_generate_return(ASSESS_JSON_PRIME, cost=0.20),
            _mock_generate_return(TRANSFORM_YAML, cost=0.30),
        ]
        mock_resolve.return_value = agent

        mock_review_result = MagicMock()
        mock_review_result.success = True
        mock_review_result.metrics = MagicMock(total_cost=0.40)
        mock_review_result.steps = []
        mock_review_result.error = None
        mock_review_result.output = {}
        mock_review_instance = MagicMock()
        mock_review_instance.run.return_value = mock_review_result
        MockReviewWf.return_value = mock_review_instance

        result = self.wf.run({
            "plan_path": str(plan_file),
            "output_dir": str(tmp_path),
        })

        assert result.success
        # 0.10 + 0.20 + 0.30 + 0.40 = 1.00
        assert result.metrics.total_cost == pytest.approx(1.0, abs=0.01)

    @patch("startd8.workflows.builtin.plan_ingestion_workflow.resolve_agent_spec")
    def test_max_cost_failfast(self, mock_resolve, tmp_path):
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(SAMPLE_PLAN)

        agent = _make_mock_agent()
        agent.generate.side_effect = [
            _mock_generate_return(PARSE_JSON, cost=0.50),
            # Should not reach assess — cost exceeds max
        ]
        mock_resolve.return_value = agent

        result = self.wf.run({
            "plan_path": str(plan_file),
            "output_dir": str(tmp_path),
            "max_cost_usd": 0.10,
        })

        assert not result.success
        assert "Cost limit exceeded" in result.error

    @patch("startd8.workflows.builtin.architectural_review_log_workflow.ArchitecturalReviewLogWorkflow")
    @patch("startd8.workflows.builtin.plan_ingestion_workflow.resolve_agent_spec")
    def test_skip_refine_when_zero_rounds(self, mock_resolve, MockReviewWf, tmp_path):
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(SAMPLE_PLAN)

        agent = _make_mock_agent()
        agent.generate.side_effect = [
            _mock_generate_return(PARSE_JSON, cost=0.01),
            _mock_generate_return(ASSESS_JSON_PRIME, cost=0.01),
            _mock_generate_return(TRANSFORM_YAML, cost=0.01),
        ]
        mock_resolve.return_value = agent

        result = self.wf.run({
            "plan_path": str(plan_file),
            "output_dir": str(tmp_path),
            "review_rounds": 0,
        })

        assert result.success
        assert result.output["refine_rounds_completed"] == 0
        # Review workflow should never be instantiated
        MockReviewWf.assert_not_called()

    @patch("startd8.workflows.builtin.architectural_review_log_workflow.ArchitecturalReviewLogWorkflow")
    @patch("startd8.workflows.builtin.plan_ingestion_workflow.resolve_agent_spec")
    def test_state_json_written(self, mock_resolve, MockReviewWf, tmp_path):
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(SAMPLE_PLAN)

        agent = _make_mock_agent()
        agent.generate.side_effect = [
            _mock_generate_return(PARSE_JSON, cost=0.01),
            _mock_generate_return(ASSESS_JSON_PRIME, cost=0.01),
            _mock_generate_return(TRANSFORM_YAML, cost=0.01),
        ]
        mock_resolve.return_value = agent

        mock_review_result = MagicMock()
        mock_review_result.success = True
        mock_review_result.metrics = MagicMock(total_cost=0.0)
        mock_review_result.steps = []
        mock_review_result.error = None
        mock_review_result.output = {}
        mock_review_instance = MagicMock()
        mock_review_instance.run.return_value = mock_review_result
        MockReviewWf.return_value = mock_review_instance

        self.wf.run({
            "plan_path": str(plan_file),
            "output_dir": str(tmp_path),
        })

        state_file = tmp_path / ".startd8" / "plan_ingestion_state.json"
        assert state_file.exists()
        state = json.loads(state_file.read_text())
        assert state["current_phase"] == "completed"

    @patch("startd8.workflows.builtin.architectural_review_log_workflow.ArchitecturalReviewLogWorkflow")
    @patch("startd8.workflows.builtin.plan_ingestion_workflow.resolve_agent_spec")
    def test_warn_cost_logs_but_continues(self, mock_resolve, MockReviewWf, tmp_path):
        """warn_cost_usd logs a warning but does not fail the workflow."""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(SAMPLE_PLAN)

        agent = _make_mock_agent()
        agent.generate.side_effect = [
            _mock_generate_return(PARSE_JSON, cost=0.50),
            _mock_generate_return(ASSESS_JSON_PRIME, cost=0.01),
            _mock_generate_return(TRANSFORM_YAML, cost=0.01),
        ]
        mock_resolve.return_value = agent

        mock_review_result = MagicMock()
        mock_review_result.success = True
        mock_review_result.metrics = MagicMock(total_cost=0.0)
        mock_review_result.steps = []
        mock_review_result.error = None
        mock_review_result.output = {}
        mock_review_instance = MagicMock()
        mock_review_instance.run.return_value = mock_review_result
        MockReviewWf.return_value = mock_review_instance

        result = self.wf.run({
            "plan_path": str(plan_file),
            "output_dir": str(tmp_path),
            "warn_cost_usd": 0.10,  # Exceeded after parse ($0.50)
            "review_rounds": 0,
        })

        # Warn doesn't stop the workflow — it still succeeds
        assert result.success

    @patch("startd8.workflows.builtin.plan_ingestion_workflow.resolve_agent_spec")
    def test_state_json_written_on_phase_error(self, mock_resolve, tmp_path):
        """Verify state JSON is persisted even when a phase fails."""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(SAMPLE_PLAN)

        agent = _make_mock_agent()
        agent.generate.return_value = _mock_generate_return("not json")
        mock_resolve.return_value = agent

        result = self.wf.run({
            "plan_path": str(plan_file),
            "output_dir": str(tmp_path),
            "enable_heuristic_parse_fallback": False,
        })

        assert not result.success
        state_file = tmp_path / ".startd8" / "plan_ingestion_state.json"
        assert state_file.exists()
        state = json.loads(state_file.read_text())
        assert state["current_phase"] == "failed"
        assert state["error"] is not None

    @patch("startd8.workflows.builtin.architectural_review_log_workflow.ArchitecturalReviewLogWorkflow")
    @patch("startd8.workflows.builtin.plan_ingestion_workflow.resolve_agent_spec")
    def test_low_quality_policy_fail_blocks_before_transform(self, mock_resolve, MockReviewWf, tmp_path):
        """If translation quality is low and policy=fail, workflow fails with diagnostics."""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(SAMPLE_PLAN)
        req_file = tmp_path / "requirements.md"
        req_file.write_text("## Requirements\n- REQ-101: Must support OAuth2")

        agent = _make_mock_agent()
        agent.generate.side_effect = [
            _mock_generate_return(PARSE_JSON, cost=0.01),
            _mock_generate_return(ASSESS_JSON_PRIME, cost=0.02),
        ]
        mock_resolve.return_value = agent

        mock_review_result = MagicMock()
        mock_review_result.success = True
        mock_review_result.metrics = MagicMock(total_cost=0.0)
        mock_review_result.steps = []
        mock_review_result.error = None
        mock_review_result.output = {}
        mock_review_instance = MagicMock()
        mock_review_instance.run.return_value = mock_review_result
        MockReviewWf.return_value = mock_review_instance

        result = self.wf.run({
            "plan_path": str(plan_file),
            "output_dir": str(tmp_path),
            "requirements_path": str(req_file),
            "low_quality_policy": "fail",
            "review_rounds": 0,
        })

        assert not result.success
        assert "Translation quality gate failed" in result.error

    @patch("startd8.workflows.builtin.architectural_review_log_workflow.ArchitecturalReviewLogWorkflow")
    @patch("startd8.workflows.builtin.plan_ingestion_workflow.resolve_agent_spec")
    def test_traceability_artifact_emitted(self, mock_resolve, MockReviewWf, tmp_path):
        """Workflow emits ingestion-traceability.json for downstream auditing."""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(SAMPLE_PLAN)

        agent = _make_mock_agent()
        agent.generate.side_effect = [
            _mock_generate_return(PARSE_JSON, cost=0.01),
            _mock_generate_return(ASSESS_JSON_PRIME, cost=0.02),
            _mock_generate_return(TRANSFORM_YAML, cost=0.03),
        ]
        mock_resolve.return_value = agent

        mock_review_result = MagicMock()
        mock_review_result.success = True
        mock_review_result.metrics = MagicMock(total_cost=0.05)
        mock_review_result.steps = []
        mock_review_result.error = None
        mock_review_result.output = {}
        mock_review_instance = MagicMock()
        mock_review_instance.run.return_value = mock_review_result
        MockReviewWf.return_value = mock_review_instance

        result = self.wf.run({
            "plan_path": str(plan_file),
            "output_dir": str(tmp_path),
            "review_rounds": 1,
        })

        assert result.success
        assert "traceability_path" in result.output
        trace_path = Path(result.output["traceability_path"])
        assert trace_path.exists()
        trace = json.loads(trace_path.read_text())
        assert "translation_quality" in trace

    @patch("startd8.workflows.builtin.architectural_review_log_workflow.ArchitecturalReviewLogWorkflow")
    @patch("startd8.workflows.builtin.plan_ingestion_workflow.resolve_agent_spec")
    def test_requirements_hints_drive_traceability_without_requirements_docs(
        self, mock_resolve, MockReviewWf, tmp_path
    ):
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(SAMPLE_PLAN)
        export_dir = tmp_path / "export"
        export_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = export_dir / "artifact-manifest.yaml"
        project_context_path = export_dir / "project-context.yaml"
        manifest_path.write_text("apiVersion: contextcore.io/v1\n")
        project_context_path.write_text("apiVersion: contextcore.io/v1\n")
        onboarding = {
            "artifact_manifest_path": str(manifest_path),
            "project_context_path": str(project_context_path),
            "artifact_manifest_checksum": None,
            "project_context_checksum": None,
            "source_checksum": "sha256:test",
            "resolved_artifact_parameters": {"dashboard": {"x": {"resolved": True}}},
            "coverage": {"overallCoverage": 100, "gaps": []},
            "requirements_hints": [
                {
                    "id": "REQ-101",
                    "labels": ["nfr"],
                    "acceptance_anchors": ["manifest.spec.requirements.availability"],
                    "source_references": ["docs/requirements.md#REQ-101"],
                }
            ],
        }
        (export_dir / "onboarding-metadata.json").write_text(json.dumps(onboarding))

        parse_with_requirement = json.dumps({
            "title": "My Sample Plan",
            "goals": ["Build a widget", "Test the widget"],
            "features": [
                {
                    "feature_id": "F-001",
                    "name": "Widget core",
                    "description": "Implement REQ-101 in core widget",
                    "target_files": ["src/widget.py"],
                    "dependencies": [],
                    "estimated_loc": 100,
                    "labels": ["core"],
                }
            ],
            "mentioned_files": ["src/widget.py"],
            "dependency_graph": {},
        })

        agent = _make_mock_agent()
        agent.generate.side_effect = [
            _mock_generate_return(parse_with_requirement, cost=0.01),
            _mock_generate_return(ASSESS_JSON_ARTISAN, cost=0.02),
            _mock_generate_return(TRANSFORM_MARKDOWN, cost=0.03),
        ]
        mock_resolve.return_value = agent

        mock_review_result = MagicMock()
        mock_review_result.success = True
        mock_review_result.metrics = MagicMock(total_cost=0.0)
        mock_review_result.steps = []
        mock_review_result.error = None
        mock_review_result.output = {}
        mock_review_instance = MagicMock()
        mock_review_instance.run.return_value = mock_review_result
        MockReviewWf.return_value = mock_review_instance

        result = self.wf.run({
            "plan_path": str(plan_file),
            "output_dir": str(tmp_path),
            "contextcore_export_dir": str(export_dir),
            "review_rounds": 0,
        })

        assert result.success
        assert result.output["route"] == "artisan"
        assert result.output["translation_quality"]["requirements_coverage_percent"] == 100.0

        seed = json.loads((tmp_path / "artisan-context-seed.json").read_text())
        ctx = seed["tasks"][0]["config"]["context"]
        assert "REQ-101" in ctx["requirement_ids"]
        assert "manifest.spec.requirements.availability" in ctx["acceptance_obligations"]

        trace = json.loads((tmp_path / "ingestion-traceability.json").read_text())
        req = next(r for r in trace["requirement_mappings"] if r["requirement_id"] == "REQ-101")
        assert req["status"] == "mapped"
        assert req["task_ids"]


# ---------------------------------------------------------------------------
# TestArtisanContextSeed
# ---------------------------------------------------------------------------

class TestArtisanContextSeed:
    def test_defaults(self):
        seed = ArtisanContextSeed()
        assert seed.version == "1.0.0"
        assert seed.schema_version == "1.0"
        assert seed.source_checksum is None
        assert seed.generator == "plan-ingestion"
        assert seed.tasks == []
        assert seed.artifacts == {}

    def test_to_dict_roundtrip(self):
        seed = ArtisanContextSeed(
            generated_at="2026-02-10T12:00:00Z",
            plan={"title": "Test"},
            complexity={"composite": 65},
            tasks=[{"task_id": "PI-001", "title": "Do stuff"}],
            artifacts={"plan_document_path": "/tmp/plan.md"},
            ingestion_metrics={"parse_cost": 0.01, "total_cost": 0.01},
        )
        d = seed.to_dict()
        assert d["version"] == "1.0.0"
        assert d["schema_version"] == "1.0"
        assert d["generated_at"] == "2026-02-10T12:00:00Z"
        assert d["plan"]["title"] == "Test"
        assert d["complexity"]["composite"] == 65
        assert len(d["tasks"]) == 1
        assert d["tasks"][0]["task_id"] == "PI-001"
        assert d["artifacts"]["plan_document_path"] == "/tmp/plan.md"
        assert d["ingestion_metrics"]["total_cost"] == 0.01

    def test_to_dict_is_json_serializable(self):
        seed = ArtisanContextSeed(
            plan={"title": "T"},
            tasks=[{"id": 1}],
        )
        text = json.dumps(seed.to_dict())
        assert "T" in text


# ---------------------------------------------------------------------------
# TestParsedPlanToSeedDict
# ---------------------------------------------------------------------------

class TestParsedPlanToSeedDict:
    def test_basic_serialization(self):
        plan = ParsedPlan(
            title="My Plan",
            goals=["G1", "G2"],
            features=[
                ParsedFeature(
                    feature_id="F-001",
                    name="Feat 1",
                    description="Do things",
                    target_files=["a.py"],
                    dependencies=["F-002"],
                    estimated_loc=50,
                    labels=["core"],
                ),
            ],
            dependency_graph={"F-001": ["F-002"]},
            mentioned_files=["a.py", "b.py"],
        )
        d = plan.to_seed_dict()
        assert d["title"] == "My Plan"
        assert d["goals"] == ["G1", "G2"]
        assert len(d["features"]) == 1
        assert d["features"][0]["feature_id"] == "F-001"
        assert d["features"][0]["target_files"] == ["a.py"]
        assert d["dependency_graph"] == {"F-001": ["F-002"]}
        assert d["mentioned_files"] == ["a.py", "b.py"]

    def test_excludes_llm_metrics(self):
        plan = ParsedPlan(
            title="T", input_tokens=500, output_tokens=200, cost=0.05,
        )
        d = plan.to_seed_dict()
        assert "input_tokens" not in d
        assert "output_tokens" not in d
        assert "cost" not in d
        assert "raw_text" not in d


# ---------------------------------------------------------------------------
# TestComplexityScoreToSeedDict
# ---------------------------------------------------------------------------

class TestComplexityScoreToSeedDict:
    def test_basic_serialization(self):
        score = ComplexityScore(
            feature_count=60,
            cross_file_deps=55,
            api_surface=50,
            test_complexity=65,
            integration_depth=70,
            domain_novelty=50,
            ambiguity=55,
            composite=65,
            reasoning="Complex",
            route=ContractorRoute.ARTISAN,
        )
        d = score.to_seed_dict()
        assert d["composite"] == 65
        assert d["dimensions"]["feature_count"] == 60
        assert d["dimensions"]["ambiguity"] == 55
        assert d["reasoning"] == "Complex"
        assert d["route"] == "artisan"

    def test_none_route(self):
        score = ComplexityScore()
        d = score.to_seed_dict()
        assert d["route"] is None

    def test_excludes_llm_metrics(self):
        score = ComplexityScore(input_tokens=100, output_tokens=50, cost=0.02)
        d = score.to_seed_dict()
        assert "input_tokens" not in d
        assert "cost" not in d


# ---------------------------------------------------------------------------
# TestEstimateStoryPoints
# ---------------------------------------------------------------------------

class TestEstimateStoryPoints:
    def test_thresholds(self):
        sp = PlanIngestionWorkflow._estimate_story_points
        assert sp(0) == 1
        assert sp(10) == 1
        assert sp(20) == 1
        assert sp(21) == 2
        assert sp(50) == 2
        assert sp(51) == 3
        assert sp(100) == 3
        assert sp(101) == 5
        assert sp(200) == 5
        assert sp(201) == 8
        assert sp(1000) == 8


# ---------------------------------------------------------------------------
# TestDeriveTasksFromFeatures
# ---------------------------------------------------------------------------

class TestDeriveTasksFromFeatures:
    def test_basic_derivation(self):
        features = [
            ParsedFeature(
                feature_id="F-001", name="Core",
                description="Core impl", target_files=["a.py"],
                estimated_loc=50, labels=["core"],
            ),
            ParsedFeature(
                feature_id="F-002", name="Tests",
                description="Test impl", target_files=["test_a.py"],
                dependencies=["F-001"], estimated_loc=30,
                labels=["tests"],
            ),
        ]
        dep_graph = {"F-002": ["F-001"]}

        tasks = PlanIngestionWorkflow._derive_tasks_from_features(features, dep_graph)

        assert len(tasks) == 2
        assert tasks[0]["task_id"] == "PI-001"
        assert tasks[0]["title"] == "Core"
        assert tasks[0]["story_points"] == 2  # 50 LOC → 2
        assert tasks[0]["depends_on"] == []

        assert tasks[1]["task_id"] == "PI-002"
        assert tasks[1]["title"] == "Tests"
        assert tasks[1]["story_points"] == 2  # 30 LOC → 2
        assert "PI-001" in tasks[1]["depends_on"]

    def test_dependency_deduplication(self):
        """If both feature.dependencies and dep_graph point to same dep, no dupes."""
        features = [
            ParsedFeature(feature_id="F-001", name="A"),
            ParsedFeature(feature_id="F-002", name="B", dependencies=["F-001"]),
        ]
        dep_graph = {"F-002": ["F-001"]}

        tasks = PlanIngestionWorkflow._derive_tasks_from_features(features, dep_graph)
        assert tasks[1]["depends_on"] == ["PI-001"]

    def test_unknown_dep_skipped(self):
        features = [
            ParsedFeature(feature_id="F-001", name="A", dependencies=["F-999"]),
        ]
        tasks = PlanIngestionWorkflow._derive_tasks_from_features(features, {})
        assert tasks[0]["depends_on"] == []

    def test_priority_assignment(self):
        features = [
            ParsedFeature(feature_id=f"F-{i:03d}", name=f"F{i}")
            for i in range(1, 10)
        ]
        tasks = PlanIngestionWorkflow._derive_tasks_from_features(features, {})
        priorities = [t["priority"] for t in tasks]
        # First third (3) = high, second third (3) = medium, rest (3) = low
        assert priorities[:3] == ["high", "high", "high"]
        assert priorities[3:6] == ["medium", "medium", "medium"]
        assert priorities[6:] == ["low", "low", "low"]

    def test_config_context(self):
        features = [
            ParsedFeature(
                feature_id="F-001", name="X",
                description="Do X", target_files=["x.py"],
                estimated_loc=150,
            ),
        ]
        tasks = PlanIngestionWorkflow._derive_tasks_from_features(features, {})
        cfg = tasks[0]["config"]
        assert cfg["task_description"] == "Do X"
        assert cfg["context"]["feature_id"] == "F-001"
        assert cfg["context"]["target_files"] == ["x.py"]
        assert cfg["context"]["estimated_loc"] == 150

    def test_context_includes_requirement_traceability_fields(self):
        features = [
            ParsedFeature(
                feature_id="F-001",
                name="Auth feature",
                description="Implements REQ-101",
                target_files=["src/auth.py"],
                estimated_loc=80,
            ),
        ]
        tasks = PlanIngestionWorkflow._derive_tasks_from_features(
            features,
            {},
            requirement_to_feature={"REQ-101": ["F-001"]},
            artifact_to_feature={"checkout-prometheus_rule": ["F-001"]},
            requirement_hints={
                "REQ-101": {
                    "acceptance_anchors": ["manifest.spec.requirements.availability"],
                    "source_references": ["docs/requirements.md#req-101"],
                }
            },
        )
        ctx = tasks[0]["config"]["context"]
        assert ctx["requirement_ids"] == ["REQ-101"]
        assert "manifest.spec.requirements.availability" in ctx["acceptance_obligations"]
        assert "docs/requirements.md#req-101" in ctx["source_references"]
        assert any("requirement identifier match" in r for r in ctx["mapping_rationale"])

    # ── __init__.py ordering tests ────────────────────────────────────

    def test_init_py_ordered_first_in_subtasks(self):
        """Multi-file feature with __init__.py: __init__.py sub-task comes first."""
        features = [
            ParsedFeature(
                feature_id="F-001", name="Package",
                target_files=["src/pkg/module.py", "src/pkg/__init__.py"],
            ),
        ]
        tasks = PlanIngestionWorkflow._derive_tasks_from_features(features, {})
        # 2-file feature → split into 2 sub-tasks; __init__.py first
        assert len(tasks) == 2
        assert tasks[0]["config"]["context"]["target_files"] == ["src/pkg/__init__.py"]
        assert tasks[1]["config"]["context"]["target_files"] == ["src/pkg/module.py"]

    def test_ordering_stable_without_init_py(self):
        """Multi-file feature without __init__.py: alphabetical sub-tasks."""
        features = [
            ParsedFeature(
                feature_id="F-001", name="Modules",
                target_files=["src/pkg/zebra.py", "src/pkg/alpha.py"],
            ),
        ]
        tasks = PlanIngestionWorkflow._derive_tasks_from_features(features, {})
        # 2-file → 2 sub-tasks, sorted alphabetically
        assert len(tasks) == 2
        assert tasks[0]["config"]["context"]["target_files"] == ["src/pkg/alpha.py"]
        assert tasks[1]["config"]["context"]["target_files"] == ["src/pkg/zebra.py"]

    def test_single_file_ordering_unchanged(self):
        """Single-file tasks are unaffected by ordering logic."""
        features = [
            ParsedFeature(
                feature_id="F-001", name="Single",
                target_files=["src/module.py"],
            ),
        ]
        tasks = PlanIngestionWorkflow._derive_tasks_from_features(features, {})
        assert tasks[0]["config"]["context"]["target_files"] == ["src/module.py"]


# ===================================================================
# Gate 2a: _split_oversized_tasks tests
# ===================================================================


class TestSplitOversizedTasks:
    """Tests for PlanIngestionWorkflow._split_oversized_tasks.

    Gate 2a (defense-in-depth Principle 2): structurally enforce
    max file count per task, even if the PARSE LLM ignored guidance.
    """

    def test_small_tasks_pass_through(self):
        """Tasks with ≤1 file (default max_files) are returned unchanged."""
        tasks = [
            {
                "task_id": "PI-001",
                "title": "Small",
                "task_type": "task",
                "story_points": 3,
                "priority": "high",
                "labels": ["core"],
                "depends_on": [],
                "config": {
                    "task_description": "Implement small module",
                    "context": {
                        "feature_id": "F-001",
                        "target_files": ["src/a.py"],
                        "estimated_loc": 100,
                    },
                },
            }
        ]
        result = PlanIngestionWorkflow._split_oversized_tasks(tasks)
        assert len(result) == 1
        assert result[0]["task_id"] == "PI-001"

    def test_four_files_split_into_four_tasks(self):
        """A 4-file task is split into 4 single-file sub-tasks."""
        tasks = [
            {
                "task_id": "PI-001",
                "title": "Big Feature",
                "task_type": "task",
                "story_points": 5,
                "priority": "high",
                "labels": ["core"],
                "depends_on": ["PI-000"],
                "config": {
                    "task_description": "Implement big module",
                    "context": {
                        "feature_id": "F-001",
                        "target_files": [
                            "src/pkg/__init__.py",
                            "src/pkg/alpha.py",
                            "src/pkg/beta.py",
                            "src/pkg/gamma.py",
                        ],
                        "estimated_loc": 400,
                    },
                },
            }
        ]
        result = PlanIngestionWorkflow._split_oversized_tasks(tasks)
        assert len(result) == 4

        # Each sub-task has exactly one target file
        for task in result:
            ctx = task["config"]["context"]
            assert len(ctx["target_files"]) == 1

        # __init__.py should be first (sub-task 'a')
        assert result[0]["task_id"] == "PI-001a"
        assert result[0]["config"]["context"]["target_files"] == ["src/pkg/__init__.py"]

    def test_init_py_is_first_subtask(self):
        """__init__.py becomes sub-task 'a' so others can depend on it."""
        tasks = [
            {
                "task_id": "PI-002",
                "title": "Package",
                "task_type": "task",
                "story_points": 5,
                "priority": "medium",
                "labels": [],
                "depends_on": [],
                "config": {
                    "task_description": "Build package",
                    "context": {
                        "feature_id": "F-002",
                        "target_files": [
                            "src/x.py",
                            "src/__init__.py",
                            "src/y.py",
                            "src/z.py",
                        ],
                        "estimated_loc": 200,
                    },
                },
            }
        ]
        result = PlanIngestionWorkflow._split_oversized_tasks(tasks)

        # __init__.py is first
        assert "src/__init__.py" in result[0]["config"]["context"]["target_files"][0]
        init_id = result[0]["task_id"]

        # Other sub-tasks depend on the init sub-task
        for sub in result[1:]:
            assert init_id in sub["depends_on"]

    def test_parent_deps_preserved(self):
        """Sub-tasks inherit the parent task's dependencies."""
        tasks = [
            {
                "task_id": "PI-003",
                "title": "Dependent Feature",
                "task_type": "task",
                "story_points": 5,
                "priority": "high",
                "labels": [],
                "depends_on": ["PI-001", "PI-002"],
                "config": {
                    "task_description": "Depends on two others",
                    "context": {
                        "feature_id": "F-003",
                        "target_files": ["a.py", "b.py", "c.py", "d.py"],
                        "estimated_loc": 100,
                    },
                },
            }
        ]
        result = PlanIngestionWorkflow._split_oversized_tasks(tasks)
        for sub in result:
            assert "PI-001" in sub["depends_on"]
            assert "PI-002" in sub["depends_on"]

    def test_split_metadata_present(self):
        """Sub-tasks have _split_from and _split_index metadata."""
        tasks = [
            {
                "task_id": "PI-004",
                "title": "Split Me",
                "task_type": "task",
                "story_points": 5,
                "priority": "low",
                "labels": [],
                "depends_on": [],
                "config": {
                    "task_description": "Should be split",
                    "context": {
                        "feature_id": "F-004",
                        "target_files": ["a.py", "b.py", "c.py", "d.py"],
                        "estimated_loc": 200,
                    },
                },
            }
        ]
        result = PlanIngestionWorkflow._split_oversized_tasks(tasks)
        for idx, sub in enumerate(result):
            ctx = sub["config"]["context"]
            assert ctx["_split_from"] == "PI-004"
            assert ctx["_split_index"] == idx

    def test_loc_divided_proportionally(self):
        """Estimated LOC is divided across sub-tasks."""
        tasks = [
            {
                "task_id": "PI-005",
                "title": "Even Split",
                "task_type": "task",
                "story_points": 8,
                "priority": "high",
                "labels": [],
                "depends_on": [],
                "config": {
                    "task_description": "400 LOC across 4 files",
                    "context": {
                        "feature_id": "F-005",
                        "target_files": ["a.py", "b.py", "c.py", "d.py"],
                        "estimated_loc": 400,
                    },
                },
            }
        ]
        result = PlanIngestionWorkflow._split_oversized_tasks(tasks)
        for sub in result:
            assert sub["config"]["context"]["estimated_loc"] == 100

    def test_custom_max_files(self):
        """max_files parameter controls split threshold."""
        tasks = [
            {
                "task_id": "PI-006",
                "title": "Two Files",
                "task_type": "task",
                "story_points": 2,
                "priority": "low",
                "labels": [],
                "depends_on": [],
                "config": {
                    "task_description": "Two files",
                    "context": {
                        "feature_id": "F-006",
                        "target_files": ["a.py", "b.py"],
                        "estimated_loc": 50,
                    },
                },
            }
        ]
        # With max_files=1, even 2-file tasks get split
        result = PlanIngestionWorkflow._split_oversized_tasks(tasks, max_files=1)
        assert len(result) == 2

    def test_mixed_tasks_only_oversized_split(self):
        """Only tasks exceeding max_files are split; others pass through."""
        tasks = [
            {
                "task_id": "PI-007",
                "title": "Small",
                "task_type": "task",
                "story_points": 1,
                "priority": "high",
                "labels": [],
                "depends_on": [],
                "config": {
                    "task_description": "One file",
                    "context": {
                        "feature_id": "F-007",
                        "target_files": ["src/small.py"],
                        "estimated_loc": 20,
                    },
                },
            },
            {
                "task_id": "PI-008",
                "title": "Big",
                "task_type": "task",
                "story_points": 8,
                "priority": "low",
                "labels": [],
                "depends_on": ["PI-007"],
                "config": {
                    "task_description": "Four files",
                    "context": {
                        "feature_id": "F-008",
                        "target_files": ["a.py", "b.py", "c.py", "d.py"],
                        "estimated_loc": 200,
                    },
                },
            },
        ]
        result = PlanIngestionWorkflow._split_oversized_tasks(tasks, max_files=3)
        # PI-007 passes through (1 file ≤ 3), PI-008 is split into 4
        assert len(result) == 5
        assert result[0]["task_id"] == "PI-007"
        assert result[1]["task_id"] == "PI-008a"


# ===================================================================
# Trivial test __init__.py filter tests
# ===================================================================


class TestFilterTrivialTestInits:
    """Tests for _is_trivial_test_init and pre/post-derivation filtering."""

    def test_is_trivial_test_init_positive(self):
        """Paths that ARE trivial test inits."""
        assert PlanIngestionWorkflow._is_trivial_test_init("tests/__init__.py")
        assert PlanIngestionWorkflow._is_trivial_test_init("tests/unit/__init__.py")
        assert PlanIngestionWorkflow._is_trivial_test_init("test/__init__.py")

    def test_is_trivial_test_init_negative(self):
        """Paths that are NOT trivial test inits."""
        assert not PlanIngestionWorkflow._is_trivial_test_init("src/pkg/__init__.py")
        assert not PlanIngestionWorkflow._is_trivial_test_init("tests/test_auth.py")
        assert not PlanIngestionWorkflow._is_trivial_test_init("__init__.py")

    def test_feature_with_test_init_stripped(self):
        """2-file feature: test __init__.py stripped, 1 task remains."""
        features = [
            ParsedFeature(
                feature_id="F-001", name="Auth tests",
                target_files=["tests/__init__.py", "tests/test_auth.py"],
                estimated_loc=80,
            ),
        ]
        tasks = PlanIngestionWorkflow._derive_tasks_from_features(features, {})
        assert len(tasks) == 1
        assert tasks[0]["config"]["context"]["target_files"] == ["tests/test_auth.py"]

    def test_standalone_test_init_feature_skipped(self):
        """Feature whose sole file is tests/__init__.py → 0 tasks."""
        features = [
            ParsedFeature(
                feature_id="F-001", name="Test init",
                target_files=["tests/__init__.py"],
                estimated_loc=10,
            ),
            ParsedFeature(
                feature_id="F-002", name="Real work",
                target_files=["src/module.py"],
                estimated_loc=50,
            ),
        ]
        tasks = PlanIngestionWorkflow._derive_tasks_from_features(features, {})
        # F-001 is skipped entirely; only F-002 produces a task
        assert len(tasks) == 1
        assert tasks[0]["config"]["context"]["feature_id"] == "F-002"

    def test_non_test_init_preserved(self):
        """src/pkg/__init__.py is NOT filtered — only test dirs are."""
        features = [
            ParsedFeature(
                feature_id="F-001", name="Package init",
                target_files=["src/pkg/__init__.py"],
                estimated_loc=30,
            ),
        ]
        tasks = PlanIngestionWorkflow._derive_tasks_from_features(features, {})
        assert len(tasks) == 1
        assert tasks[0]["config"]["context"]["target_files"] == ["src/pkg/__init__.py"]

    def test_custom_max_files_allows_larger(self):
        """max_files=3 still works as an override to _split_oversized_tasks."""
        tasks = [
            {
                "task_id": "PI-001",
                "title": "Multi",
                "task_type": "task",
                "story_points": 3,
                "priority": "high",
                "labels": [],
                "depends_on": [],
                "config": {
                    "task_description": "Three files",
                    "context": {
                        "feature_id": "F-001",
                        "target_files": ["a.py", "b.py", "c.py"],
                        "estimated_loc": 150,
                    },
                },
            }
        ]
        result = PlanIngestionWorkflow._split_oversized_tasks(tasks, max_files=3)
        # 3 files ≤ max_files=3 → no split
        assert len(result) == 1
        assert result[0]["task_id"] == "PI-001"


# ---------------------------------------------------------------------------
# TestEmitPhaseArtisanRoute
# ---------------------------------------------------------------------------

class TestEmitPhaseArtisanRoute:
    def setup_method(self):
        self.wf = PlanIngestionWorkflow()

    def test_artisan_emits_context_seed(self, tmp_path):
        doc_path = tmp_path / "PLAN-ingested.md"
        doc_path.write_text("# Plan")
        complexity = ComplexityScore(
            composite=65, reasoning="Complex",
            route=ContractorRoute.ARTISAN,
        )
        parsed_plan = ParsedPlan(
            title="Test Plan",
            goals=["G1"],
            features=[
                ParsedFeature(
                    feature_id="F-001", name="Feat",
                    description="Do it", target_files=["a.py"],
                    estimated_loc=80, labels=["core"],
                ),
            ],
            dependency_graph={},
            mentioned_files=["a.py"],
        )

        config_path, _, seed_path, _tracking = self.wf._phase_emit(
            doc_path, ContractorRoute.ARTISAN, complexity, tmp_path,
            review_rounds=2, review_quality_tier="flagship",
            scope=None, context_files=None,
            warn_cost_usd=None, max_cost_usd=None,
            parsed_plan=parsed_plan,
            step_costs={"parse": 0.01, "assess": 0.02, "transform": 0.10},
        )

        assert seed_path is not None
        assert seed_path.name == "artisan-context-seed.json"
        assert seed_path.exists()

        data = json.loads(seed_path.read_text())
        assert data["version"] == "1.0.0"
        assert data["schema_version"] == "1.0"
        assert data["generator"] == "plan-ingestion"
        assert data["plan"]["title"] == "Test Plan"
        assert data["complexity"]["composite"] == 65
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["task_id"] == "PI-001"
        assert data["artifacts"]["plan_document_path"] == str(doc_path)
        assert data["ingestion_metrics"]["parse_cost"] == 0.01
        assert data["ingestion_metrics"]["total_cost"] == pytest.approx(0.13)

    def test_artisan_seed_serializes_manifest_objectives_key_results(self, tmp_path):
        class KeyResult:
            def __init__(self, metric: str, target: str):
                self.metric = metric
                self.target = target

        doc_path = tmp_path / "PLAN-ingested.md"
        doc_path.write_text("# Plan")
        complexity = ComplexityScore(
            composite=65, reasoning="Complex",
            route=ContractorRoute.ARTISAN,
        )
        parsed_plan = ParsedPlan(
            title="Test Plan",
            goals=["G1"],
            features=[
                ParsedFeature(
                    feature_id="F-001",
                    name="Feat",
                    description="Do it",
                    target_files=["a.py"],
                    estimated_loc=80,
                    labels=["core"],
                ),
            ],
            dependency_graph={},
            mentioned_files=["a.py"],
        )
        manifest_context = {
            "objectives": [
                {
                    "name": "Ship feature serial",
                    "key_results": [KeyResult("latency_p95", "<=250ms")],
                }
            ]
        }

        _config_path, _, seed_path, _tracking = self.wf._phase_emit(
            doc_path,
            ContractorRoute.ARTISAN,
            complexity,
            tmp_path,
            review_rounds=2,
            review_quality_tier="flagship",
            scope=None,
            context_files=None,
            warn_cost_usd=None,
            max_cost_usd=None,
            parsed_plan=parsed_plan,
            manifest_context=manifest_context,
        )

        assert seed_path is not None
        data = json.loads(seed_path.read_text())
        kr = data["architectural_context"]["objectives"][0]["key_results"][0]
        assert kr["metric"] == "latency_p95"
        assert kr["target"] == "<=250ms"

    def test_prime_emits_prime_context_seed(self, tmp_path):
        doc_path = tmp_path / "plan-ingestion-tasks.yaml"
        doc_path.write_text("project: {}")
        complexity = ComplexityScore(composite=20, route=ContractorRoute.PRIME)
        parsed_plan = ParsedPlan(title="Simple", features=[])

        config_path, _, seed_path, _tracking = self.wf._phase_emit(
            doc_path, ContractorRoute.PRIME, complexity, tmp_path,
            review_rounds=1, review_quality_tier="flagship",
            scope=None, context_files=None,
            warn_cost_usd=None, max_cost_usd=None,
            parsed_plan=parsed_plan,
        )

        assert seed_path is not None
        assert seed_path.name == "prime-context-seed.json"
        assert not (tmp_path / "artisan-context-seed.json").exists()

    def test_artisan_without_parsed_plan_skips_seed(self, tmp_path):
        doc_path = tmp_path / "PLAN-ingested.md"
        doc_path.write_text("# Plan")
        complexity = ComplexityScore(
            composite=65, route=ContractorRoute.ARTISAN,
        )

        config_path, _, seed_path, _tracking = self.wf._phase_emit(
            doc_path, ContractorRoute.ARTISAN, complexity, tmp_path,
            review_rounds=1, review_quality_tier="flagship",
            scope=None, context_files=None,
            warn_cost_usd=None, max_cost_usd=None,
        )

        assert seed_path is None

    def test_artisan_seed_propagates_source_checksum_from_onboarding(self, tmp_path):
        """Item 16: source_checksum from onboarding-metadata propagates to seed."""
        doc_path = tmp_path / "PLAN-ingested.md"
        doc_path.write_text("# Plan")
        onboarding_path = tmp_path / "onboarding-metadata.json"
        onboarding_path.write_text(
            json.dumps({
                "source_checksum": "sha256:abc123",
                "artifact_manifest_path": str(tmp_path / "manifest.yaml"),
            })
        )

        complexity = ComplexityScore(
            composite=65, reasoning="Complex",
            route=ContractorRoute.ARTISAN,
        )
        parsed_plan = ParsedPlan(
            title="Test Plan",
            goals=["G1"],
            features=[
                ParsedFeature(
                    feature_id="F-001", name="Feat",
                    description="Do it", target_files=["a.py"],
                    estimated_loc=80, labels=["core"],
                ),
            ],
            dependency_graph={},
            mentioned_files=["a.py"],
        )

        _config_path, _, seed_path, _tracking = self.wf._phase_emit(
            doc_path, ContractorRoute.ARTISAN, complexity, tmp_path,
            review_rounds=1, review_quality_tier="flagship",
            scope=None, context_files=[str(onboarding_path)],
            warn_cost_usd=None, max_cost_usd=None,
            parsed_plan=parsed_plan,
            step_costs={"parse": 0.01, "assess": 0.02, "transform": 0.10},
        )

        assert seed_path is not None
        data = json.loads(seed_path.read_text())
        assert data["source_checksum"] == "sha256:abc123"
        assert data["artifacts"]["source_checksum"] == "sha256:abc123"


# ---------------------------------------------------------------------------
# TestIngestionStateContextSeedPath
# ---------------------------------------------------------------------------

class TestIngestionStateContextSeedPath:
    def test_default_is_none(self):
        state = IngestionState()
        assert state.context_seed_path is None
        d = state.to_dict()
        assert d["context_seed_path"] is None

    def test_set_path(self):
        state = IngestionState(context_seed_path="/tmp/seed.json")
        d = state.to_dict()
        assert d["context_seed_path"] == "/tmp/seed.json"


# ---------------------------------------------------------------------------
# TestEndToEndArtisanContextSeed
# ---------------------------------------------------------------------------

class TestEndToEndArtisanContextSeed:
    def setup_method(self):
        self.wf = PlanIngestionWorkflow()

    @patch("startd8.workflows.builtin.architectural_review_log_workflow.ArchitecturalReviewLogWorkflow")
    @patch("startd8.workflows.builtin.plan_ingestion_workflow.resolve_agent_spec")
    def test_artisan_flow_produces_context_seed(self, mock_resolve, MockReviewWf, tmp_path):
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(SAMPLE_PLAN)

        agent = _make_mock_agent()
        agent.generate.side_effect = [
            _mock_generate_return(PARSE_JSON, cost=0.01),
            _mock_generate_return(ASSESS_JSON_ARTISAN, cost=0.02),
            _mock_generate_return(TRANSFORM_MARKDOWN, cost=0.03),
        ]
        mock_resolve.return_value = agent

        mock_review_result = MagicMock()
        mock_review_result.success = True
        mock_review_result.metrics = MagicMock(total_cost=0.05)
        mock_review_result.steps = []
        mock_review_result.error = None
        mock_review_result.output = {}
        mock_review_instance = MagicMock()
        mock_review_instance.run.return_value = mock_review_result
        MockReviewWf.return_value = mock_review_instance

        result = self.wf.run({
            "plan_path": str(plan_file),
            "output_dir": str(tmp_path),
            "review_rounds": 1,
        })

        assert result.success
        assert result.output["route"] == "artisan"
        assert "context_seed_path" in result.output

        seed_path = Path(result.output["context_seed_path"])
        assert seed_path.exists()
        assert seed_path.name == "artisan-context-seed.json"

        data = json.loads(seed_path.read_text())
        assert data["version"] == "1.0.0"
        assert data["schema_version"] == "1.0"
        assert data["plan"]["title"] == "My Sample Plan"
        assert len(data["tasks"]) == 2
        assert data["tasks"][0]["task_id"] == "PI-001"
        assert data["tasks"][1]["task_id"] == "PI-002"
        # F-002 depends on F-001
        assert "PI-001" in data["tasks"][1]["depends_on"]
        assert data["complexity"]["composite"] == 65
        assert data["artifacts"]["plan_document_path"] == str(tmp_path / "PLAN-ingested.md")
        assert data["ingestion_metrics"]["total_cost"] > 0

        # Verify REFINE forwarding fields present (empty when review_output is {})
        onboarding = data.get("onboarding", {})
        assert "refine_suggestions" in onboarding
        assert onboarding["refine_suggestions"] == []
        assert "refine_provenance" in data["artifacts"]
        assert data["artifacts"]["refine_provenance"]["origin_phase"] == "ingestion.refine"

    @patch("startd8.workflows.builtin.architectural_review_log_workflow.ArchitecturalReviewLogWorkflow")
    @patch("startd8.workflows.builtin.plan_ingestion_workflow.resolve_agent_spec")
    def test_prime_flow_no_context_seed(self, mock_resolve, MockReviewWf, tmp_path):
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(SAMPLE_PLAN)

        agent = _make_mock_agent()
        agent.generate.side_effect = [
            _mock_generate_return(PARSE_JSON, cost=0.01),
            _mock_generate_return(ASSESS_JSON_PRIME, cost=0.02),
            _mock_generate_return(TRANSFORM_YAML, cost=0.03),
        ]
        mock_resolve.return_value = agent

        mock_review_result = MagicMock()
        mock_review_result.success = True
        mock_review_result.metrics = MagicMock(total_cost=0.05)
        mock_review_result.steps = []
        mock_review_result.error = None
        mock_review_result.output = {}
        mock_review_instance = MagicMock()
        mock_review_instance.run.return_value = mock_review_result
        MockReviewWf.return_value = mock_review_instance

        result = self.wf.run({
            "plan_path": str(plan_file),
            "output_dir": str(tmp_path),
            "review_rounds": 1,
        })

        assert result.success
        assert result.output["route"] == "prime"
        # Prime route now emits prime-context-seed.json
        assert "context_seed_path" in result.output
        assert Path(result.output["context_seed_path"]).name == "prime-context-seed.json"
        assert not (tmp_path / "artisan-context-seed.json").exists()


# ---------------------------------------------------------------------------
# TestExtractRefineSuggestionsForSeed
# ---------------------------------------------------------------------------

class TestExtractRefineSuggestionsForSeed:
    def test_empty_review_output(self):
        assert PlanIngestionWorkflow._extract_refine_suggestions_for_seed({}) == []

    def test_no_triage_key(self):
        assert PlanIngestionWorkflow._extract_refine_suggestions_for_seed(
            {"apply": {"applied_count": 1}}
        ) == []

    def test_triage_not_dict(self):
        assert PlanIngestionWorkflow._extract_refine_suggestions_for_seed(
            {"triage": "invalid"}
        ) == []

    def test_zero_accepted(self):
        result = PlanIngestionWorkflow._extract_refine_suggestions_for_seed({
            "triage": {"accepted": 0, "rejected": 2, "decisions": []},
        })
        assert result == []

    def test_filters_only_accept(self):
        result = PlanIngestionWorkflow._extract_refine_suggestions_for_seed({
            "triage": {
                "accepted": 2,
                "rejected": 1,
                "decisions": [
                    {"id": "S-001", "decision": "ACCEPT", "rationale": "Good", "area": "arch", "severity": "high"},
                    {"id": "S-002", "decision": "REJECT", "rationale": "Bad", "area": "perf", "severity": "low"},
                    {"id": "S-003", "decision": "ACCEPT", "rationale": "Also good", "area": "sec", "severity": "medium"},
                ],
            },
        })
        assert len(result) == 2
        assert result[0]["id"] == "S-001"
        assert result[0]["decision"] == "ACCEPT"
        assert result[1]["id"] == "S-003"

    def test_extracts_decision_fields(self):
        result = PlanIngestionWorkflow._extract_refine_suggestions_for_seed({
            "triage": {
                "accepted": 1,
                "rejected": 0,
                "decisions": [
                    {
                        "id": "S-010",
                        "decision": "ACCEPT",
                        "rationale": "Important fix",
                        "area": "error_handling",
                        "severity": "critical",
                    },
                ],
            },
        })
        assert len(result) == 1
        d = result[0]
        assert d["id"] == "S-010"
        assert d["decision"] == "ACCEPT"
        assert d["rationale"] == "Important fix"
        assert d["area"] == "error_handling"
        assert d["severity"] == "critical"

    def test_fallback_to_summary_when_no_decisions(self):
        """Old-format triage without decisions key returns aggregate summary."""
        result = PlanIngestionWorkflow._extract_refine_suggestions_for_seed({
            "triage": {
                "accepted": 3,
                "rejected": 1,
                "substantially_addressed_areas": ["architecture", "security"],
                "areas_needing_review": ["performance"],
            },
        })
        assert len(result) == 1
        assert result[0]["source"] == "triage_summary"
        assert result[0]["triage_accepted_count"] == 3
        assert result[0]["triage_rejected_count"] == 1
        assert result[0]["substantially_addressed_areas"] == ["architecture", "security"]
        assert result[0]["areas_needing_review"] == ["performance"]


# ---------------------------------------------------------------------------
# TestRefineForwardingIntegration
# ---------------------------------------------------------------------------

class TestRefineForwardingIntegration:
    def setup_method(self):
        self.wf = PlanIngestionWorkflow()

    @patch("startd8.workflows.builtin.architectural_review_log_workflow.ArchitecturalReviewLogWorkflow")
    @patch("startd8.workflows.builtin.plan_ingestion_workflow.resolve_agent_spec")
    def test_review_output_reaches_artisan_seed(self, mock_resolve, MockReviewWf, tmp_path):
        """Full mock: REFINE output propagates to artisan seed onboarding."""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(SAMPLE_PLAN)

        agent = _make_mock_agent()
        agent.generate.side_effect = [
            _mock_generate_return(PARSE_JSON, cost=0.01),
            _mock_generate_return(ASSESS_JSON_ARTISAN, cost=0.02),
            _mock_generate_return(TRANSFORM_MARKDOWN, cost=0.03),
        ]
        mock_resolve.return_value = agent

        mock_review_result = MagicMock()
        mock_review_result.success = True
        mock_review_result.metrics = MagicMock(total_cost=0.05)
        mock_review_result.steps = []
        mock_review_result.error = None
        mock_review_result.output = {
            "triage": {
                "accepted": 2,
                "rejected": 1,
                "decisions": [
                    {"id": "S-001", "decision": "ACCEPT", "rationale": "Good", "area": "arch", "severity": "high"},
                    {"id": "S-002", "decision": "REJECT", "rationale": "Nope", "area": "perf", "severity": "low"},
                    {"id": "S-003", "decision": "ACCEPT", "rationale": "Yes", "area": "sec", "severity": "medium"},
                ],
            },
            "apply": {
                "applied_count": 1,
                "applied_ids": ["S-001"],
                "warning_ids": [],
                "error": None,
            },
            "state_path": "/tmp/review-state.json",
        }
        mock_review_instance = MagicMock()
        mock_review_instance.run.return_value = mock_review_result
        MockReviewWf.return_value = mock_review_instance

        result = self.wf.run({
            "plan_path": str(plan_file),
            "output_dir": str(tmp_path),
            "review_rounds": 1,
        })

        assert result.success
        seed_path = Path(result.output["context_seed_path"])
        data = json.loads(seed_path.read_text())

        # Verify refine_suggestions in onboarding
        onboarding = data.get("onboarding", {})
        suggestions = onboarding.get("refine_suggestions", [])
        assert len(suggestions) == 2  # Only ACCEPT decisions
        assert suggestions[0]["id"] == "S-001"
        assert suggestions[1]["id"] == "S-003"

        # Verify refine_provenance in artifacts
        provenance = data["artifacts"].get("refine_provenance", {})
        assert provenance["origin_phase"] == "ingestion.refine"
        assert provenance["triage_accepted"] == 2
        assert provenance["triage_rejected"] == 1
        assert provenance["applied_ids"] == ["S-001"]

    @patch("startd8.workflows.builtin.architectural_review_log_workflow.ArchitecturalReviewLogWorkflow")
    @patch("startd8.workflows.builtin.plan_ingestion_workflow.resolve_agent_spec")
    def test_review_output_none_graceful(self, mock_resolve, MockReviewWf, tmp_path):
        """When REFINE is disabled (0 rounds), seed has empty refine_suggestions."""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(SAMPLE_PLAN)

        agent = _make_mock_agent()
        agent.generate.side_effect = [
            _mock_generate_return(PARSE_JSON, cost=0.01),
            _mock_generate_return(ASSESS_JSON_ARTISAN, cost=0.02),
            _mock_generate_return(TRANSFORM_MARKDOWN, cost=0.03),
        ]
        mock_resolve.return_value = agent

        result = self.wf.run({
            "plan_path": str(plan_file),
            "output_dir": str(tmp_path),
            "review_rounds": 0,
        })

        assert result.success
        seed_path = Path(result.output["context_seed_path"])
        data = json.loads(seed_path.read_text())

        onboarding = data.get("onboarding", {})
        assert onboarding.get("refine_suggestions") == []

        provenance = data["artifacts"].get("refine_provenance", {})
        assert provenance["origin_phase"] == "ingestion.refine"
        assert provenance.get("apply_enabled") is False

    @patch("startd8.workflows.builtin.architectural_review_log_workflow.ArchitecturalReviewLogWorkflow")
    @patch("startd8.workflows.builtin.plan_ingestion_workflow.resolve_agent_spec")
    def test_apply_provenance_in_prime_seed(self, mock_resolve, MockReviewWf, tmp_path):
        """Prime seed also receives refine provenance (route parity)."""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(SAMPLE_PLAN)

        agent = _make_mock_agent()
        agent.generate.side_effect = [
            _mock_generate_return(PARSE_JSON, cost=0.01),
            _mock_generate_return(ASSESS_JSON_PRIME, cost=0.02),
            _mock_generate_return(TRANSFORM_YAML, cost=0.03),
        ]
        mock_resolve.return_value = agent

        mock_review_result = MagicMock()
        mock_review_result.success = True
        mock_review_result.metrics = MagicMock(total_cost=0.05)
        mock_review_result.steps = []
        mock_review_result.error = None
        mock_review_result.output = {
            "triage": {
                "accepted": 1,
                "rejected": 0,
                "decisions": [
                    {"id": "S-010", "decision": "ACCEPT", "rationale": "Fix", "area": "arch", "severity": "high"},
                ],
            },
            "apply": {"applied_count": 0, "applied_ids": [], "warning_ids": [], "error": None},
        }
        mock_review_instance = MagicMock()
        mock_review_instance.run.return_value = mock_review_result
        MockReviewWf.return_value = mock_review_instance

        result = self.wf.run({
            "plan_path": str(plan_file),
            "output_dir": str(tmp_path),
            "review_rounds": 1,
        })

        assert result.success
        prime_seed_path = tmp_path / "prime-context-seed.json"
        assert prime_seed_path.exists()
        data = json.loads(prime_seed_path.read_text())

        onboarding = data.get("onboarding", {})
        suggestions = onboarding.get("refine_suggestions", [])
        assert len(suggestions) == 1
        assert suggestions[0]["id"] == "S-010"

        provenance = data["artifacts"].get("refine_provenance", {})
        assert provenance["origin_phase"] == "ingestion.refine"
        assert provenance["triage_accepted"] == 1

    @patch("startd8.workflows.builtin.architectural_review_log_workflow.ArchitecturalReviewLogWorkflow")
    @patch("startd8.workflows.builtin.plan_ingestion_workflow.resolve_agent_spec")
    def test_chain_status_logging(self, mock_resolve, MockReviewWf, tmp_path, caplog):
        """Verify chain status logging (INTACT/N_A)."""
        import logging

        plan_file = tmp_path / "plan.md"
        plan_file.write_text(SAMPLE_PLAN)

        agent = _make_mock_agent()
        agent.generate.side_effect = [
            _mock_generate_return(PARSE_JSON, cost=0.01),
            _mock_generate_return(ASSESS_JSON_ARTISAN, cost=0.02),
            _mock_generate_return(TRANSFORM_MARKDOWN, cost=0.03),
        ]
        mock_resolve.return_value = agent

        mock_review_result = MagicMock()
        mock_review_result.success = True
        mock_review_result.metrics = MagicMock(total_cost=0.05)
        mock_review_result.steps = []
        mock_review_result.error = None
        mock_review_result.output = {
            "triage": {
                "accepted": 1,
                "rejected": 0,
                "decisions": [
                    {"id": "S-001", "decision": "ACCEPT", "rationale": "Ok", "area": "arch", "severity": "high"},
                ],
            },
            "apply": {},
        }
        mock_review_instance = MagicMock()
        mock_review_instance.run.return_value = mock_review_result
        MockReviewWf.return_value = mock_review_instance

        with caplog.at_level(logging.INFO, logger="startd8.workflows.builtin.plan_ingestion_workflow"):
            self.wf.run({
                "plan_path": str(plan_file),
                "output_dir": str(tmp_path),
                "review_rounds": 1,
            })

        assert any("REFINE→seed chain INTACT" in m for m in caplog.messages)


# ---------------------------------------------------------------------------
# TestSkipArcReview
# ---------------------------------------------------------------------------

class TestSkipArcReview:
    """Tests for the skip_arc_review flag."""

    def setup_method(self):
        self.wf = PlanIngestionWorkflow()

    @patch("startd8.workflows.builtin.architectural_review_log_workflow.ArchitecturalReviewLogWorkflow")
    @patch("startd8.workflows.builtin.plan_ingestion_workflow.resolve_agent_spec")
    def test_skip_arc_review_flag_skips_refine(self, mock_resolve, MockReviewWf, tmp_path):
        """When skip_arc_review=True, ArchitecturalReviewLogWorkflow is never instantiated."""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(SAMPLE_PLAN)

        agent = _make_mock_agent()
        agent.generate.side_effect = [
            _mock_generate_return(PARSE_JSON, cost=0.01),
            _mock_generate_return(ASSESS_JSON_PRIME, cost=0.02),
            _mock_generate_return(TRANSFORM_YAML, cost=0.03),
        ]
        mock_resolve.return_value = agent

        result = self.wf.run({
            "plan_path": str(plan_file),
            "output_dir": str(tmp_path),
            "skip_arc_review": True,
            "review_rounds": 3,  # would normally trigger 3 rounds
        })

        assert result.success
        MockReviewWf.assert_not_called()
        # Cost should only include parse + assess + transform (no refine)
        assert result.metrics.total_cost == pytest.approx(0.06, abs=0.01)

    @patch("startd8.workflows.builtin.architectural_review_log_workflow.ArchitecturalReviewLogWorkflow")
    @patch("startd8.workflows.builtin.plan_ingestion_workflow.resolve_agent_spec")
    def test_skip_arc_review_false_runs_refine(self, mock_resolve, MockReviewWf, tmp_path):
        """When skip_arc_review=False, the arc review runs normally."""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(SAMPLE_PLAN)

        agent = _make_mock_agent()
        agent.generate.side_effect = [
            _mock_generate_return(PARSE_JSON, cost=0.01),
            _mock_generate_return(ASSESS_JSON_PRIME, cost=0.02),
            _mock_generate_return(TRANSFORM_YAML, cost=0.03),
        ]
        mock_resolve.return_value = agent

        mock_review_result = MagicMock()
        mock_review_result.success = True
        mock_review_result.metrics = MagicMock(total_cost=0.05)
        mock_review_result.steps = []
        mock_review_result.error = None
        mock_review_result.output = {}
        mock_review_instance = MagicMock()
        mock_review_instance.run.return_value = mock_review_result
        MockReviewWf.return_value = mock_review_instance

        result = self.wf.run({
            "plan_path": str(plan_file),
            "output_dir": str(tmp_path),
            "skip_arc_review": False,
            "review_rounds": 1,
        })

        assert result.success
        MockReviewWf.assert_called_once()

    def test_skip_arc_review_metadata_declared(self):
        """skip_arc_review appears in workflow metadata inputs."""
        wf = PlanIngestionWorkflow()
        input_names = [inp.name for inp in wf.metadata.inputs]
        assert "skip_arc_review" in input_names
