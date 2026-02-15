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
        rounds, steps, cost = self.wf._phase_refine(
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

        mock_instance = MagicMock()
        mock_instance.run.return_value = mock_result
        MockReviewWf.return_value = mock_instance

        rounds, steps, cost = self.wf._phase_refine(
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

        # Verify the config passed to the review workflow
        call_config = mock_instance.run.call_args[0][0]
        assert call_config["document_path"] == str(plan_file)
        assert call_config["quality_tier"] == "flagship"
        assert call_config["reviewer_count"] == 2
        assert call_config["scope"] == "Review scope"
        assert call_config["context_files"] == ["src/a.py"]
        assert call_config["feature_requirements"] == ["reqs/feature.md"]


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

    def test_shared_module_detection_adds_prompt_hints(self):
        """Tasks with multi-file targets that include shared files get prompt_hints."""
        features = [
            ParsedFeature(
                feature_id="F-001", name="Skeleton",
                target_files=["src/pkg/__init__.py", "src/pkg/shared.py"],
            ),
            ParsedFeature(
                feature_id="F-002", name="Generator A",
                target_files=["src/pkg/shared.py"],
                dependencies=["F-001"],
            ),
        ]
        tasks = PlanIngestionWorkflow._derive_tasks_from_features(features, {})

        # F-001 has multi-file targets with shared.py → should get prompt_hints
        ctx1 = tasks[0]["config"]["context"]
        assert "prompt_hints" in ctx1
        assert len(ctx1["prompt_hints"]) == 1
        assert "shared.py" in ctx1["prompt_hints"][0]
        assert "PI-002" in ctx1["prompt_hints"][0]
        assert "stub" in ctx1["prompt_hints"][0].lower()

        # F-002 has only one target file → no prompt_hints (single-file tasks skip)
        ctx2 = tasks[1]["config"]["context"]
        assert "prompt_hints" not in ctx2

    def test_no_shared_files_no_prompt_hints(self):
        """Tasks with multi-file targets but no shared files get no prompt_hints."""
        features = [
            ParsedFeature(
                feature_id="F-001", name="Module",
                target_files=["src/a.py", "src/b.py"],
            ),
            ParsedFeature(
                feature_id="F-002", name="Other",
                target_files=["src/c.py"],
            ),
        ]
        tasks = PlanIngestionWorkflow._derive_tasks_from_features(features, {})
        # F-001 has multi-file but no file overlap → no prompt_hints
        assert "prompt_hints" not in tasks[0]["config"]["context"]

    def test_single_file_task_no_prompt_hints(self):
        """Single-file tasks never get prompt_hints even if file is shared."""
        features = [
            ParsedFeature(
                feature_id="F-001", name="A",
                target_files=["src/shared.py"],
            ),
            ParsedFeature(
                feature_id="F-002", name="B",
                target_files=["src/shared.py"],
            ),
        ]
        tasks = PlanIngestionWorkflow._derive_tasks_from_features(features, {})
        # Both are single-file → no prompt_hints (multi-file constraint doesn't apply)
        assert "prompt_hints" not in tasks[0]["config"]["context"]
        assert "prompt_hints" not in tasks[1]["config"]["context"]

    # ── __init__.py ordering tests ────────────────────────────────────

    def test_init_py_ordered_first(self):
        """__init__.py should be first in target_files regardless of input order."""
        features = [
            ParsedFeature(
                feature_id="F-001", name="Package",
                target_files=["src/pkg/module.py", "src/pkg/__init__.py"],
            ),
        ]
        tasks = PlanIngestionWorkflow._derive_tasks_from_features(features, {})
        target_files = tasks[0]["config"]["context"]["target_files"]
        assert target_files[0] == "src/pkg/__init__.py"
        assert target_files[1] == "src/pkg/module.py"

    def test_ordering_stable_without_init_py(self):
        """Files without __init__.py are sorted alphabetically."""
        features = [
            ParsedFeature(
                feature_id="F-001", name="Modules",
                target_files=["src/pkg/zebra.py", "src/pkg/alpha.py"],
            ),
        ]
        tasks = PlanIngestionWorkflow._derive_tasks_from_features(features, {})
        target_files = tasks[0]["config"]["context"]["target_files"]
        assert target_files == ["src/pkg/alpha.py", "src/pkg/zebra.py"]

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

    # ── Multi-file risk metadata tests ────────────────────────────────

    def test_multi_file_risk_metadata_present(self):
        """Multi-file tasks get _multi_file_risk metadata in context."""
        features = [
            ParsedFeature(
                feature_id="F-001", name="Package",
                target_files=["src/pkg/__init__.py", "src/pkg/module.py"],
                estimated_loc=100,
            ),
        ]
        tasks = PlanIngestionWorkflow._derive_tasks_from_features(features, {})
        ctx = tasks[0]["config"]["context"]
        assert "_multi_file_risk" in ctx
        risk = ctx["_multi_file_risk"]
        assert risk["file_count"] == 2
        assert risk["has_init_py"] is True
        assert risk["high_loc"] is False

    def test_multi_file_risk_high_loc(self):
        """High estimated_loc (>200) is flagged in multi-file risk metadata."""
        features = [
            ParsedFeature(
                feature_id="F-001", name="BigPkg",
                target_files=["src/a.py", "src/b.py"],
                estimated_loc=300,
            ),
        ]
        tasks = PlanIngestionWorkflow._derive_tasks_from_features(features, {})
        risk = tasks[0]["config"]["context"]["_multi_file_risk"]
        assert risk["high_loc"] is True
        assert risk["has_init_py"] is False

    def test_single_file_no_risk_metadata(self):
        """Single-file tasks have no _multi_file_risk metadata."""
        features = [
            ParsedFeature(
                feature_id="F-001", name="Single",
                target_files=["src/module.py"],
            ),
        ]
        tasks = PlanIngestionWorkflow._derive_tasks_from_features(features, {})
        assert "_multi_file_risk" not in tasks[0]["config"]["context"]

    def test_four_plus_files_logs_warning(self, caplog):
        """Features with 4+ target files produce a warning log."""
        import logging
        features = [
            ParsedFeature(
                feature_id="F-001", name="BigFeature",
                target_files=["a.py", "b.py", "c.py", "d.py"],
            ),
        ]
        with caplog.at_level(logging.WARNING):
            tasks = PlanIngestionWorkflow._derive_tasks_from_features(features, {})
        assert any("4 target files" in r.message for r in caplog.records)
        assert any("exceeds recommended" in r.message for r in caplog.records)


# ===================================================================
# File scope classification tests
# ===================================================================


class TestFileScopeClassification:
    """Tests for _file_scope metadata in _derive_tasks_from_features."""

    def test_shared_files_get_scope(self):
        """Files appearing in multiple features get non-primary scope."""
        features = [
            ParsedFeature(
                feature_id="F-001", name="Init",
                description="Package init", target_files=["pkg/__init__.py", "pkg/shared.py"],
                estimated_loc=50,
            ),
            ParsedFeature(
                feature_id="F-002", name="Consumer",
                description="Uses shared", target_files=["pkg/shared.py", "pkg/consumer.py"],
                dependencies=["F-001"], estimated_loc=80,
            ),
        ]
        tasks = PlanIngestionWorkflow._derive_tasks_from_features(
            features, {"F-002": ["F-001"]},
        )

        # F-001 owns shared.py (first claimer) — scope is "shared"
        scope_1 = tasks[0]["config"]["context"].get("_file_scope", {})
        assert scope_1.get("pkg/shared.py") == "shared"

        # F-002 also claims shared.py but is not first — scope is "stub"
        scope_2 = tasks[1]["config"]["context"].get("_file_scope", {})
        assert scope_2.get("pkg/shared.py") == "stub"

    def test_single_file_no_scope(self):
        """Single-file features don't produce _file_scope."""
        features = [
            ParsedFeature(
                feature_id="F-001", name="Module",
                description="Single module", target_files=["src/module.py"],
                estimated_loc=50,
            ),
        ]
        tasks = PlanIngestionWorkflow._derive_tasks_from_features(features, {})
        ctx = tasks[0]["config"]["context"]
        # No shared files → _file_scope may be absent or all primary
        scope = ctx.get("_file_scope", {})
        assert all(v == "primary" for v in scope.values())

    def test_file_ownership_from_export(self):
        """file_ownership from ContextCore export is used for classification."""
        features = [
            ParsedFeature(
                feature_id="F-001", name="Dashboard",
                description="Generate dashboard",
                target_files=["grafana/dashboards/api-dashboard.json", "grafana/dashboards/shared.json"],
                estimated_loc=200,
            ),
        ]
        file_ownership = {
            "grafana/dashboards/api-dashboard.json": {
                "artifact_ids": ["api-dashboard"],
                "artifact_types": ["dashboard"],
                "scope": "primary",
                "task_ids": ["PI-001"],
            },
            "grafana/dashboards/shared.json": {
                "artifact_ids": ["api-dashboard", "web-dashboard"],
                "artifact_types": ["dashboard"],
                "scope": "shared",
                "task_ids": ["PI-001", "PI-002"],
            },
        }
        tasks = PlanIngestionWorkflow._derive_tasks_from_features(
            features, {}, file_ownership=file_ownership,
        )
        scope = tasks[0]["config"]["context"].get("_file_scope", {})
        assert scope.get("grafana/dashboards/shared.json") == "shared"

    def test_no_file_ownership_still_detects_cross_feature_sharing(self):
        """Without export file_ownership, cross-feature sharing is still detected."""
        features = [
            ParsedFeature(
                feature_id="F-001", name="A",
                target_files=["pkg/__init__.py", "pkg/shared.py"],
                estimated_loc=50,
            ),
            ParsedFeature(
                feature_id="F-002", name="B",
                target_files=["pkg/shared.py"],
                dependencies=["F-001"], estimated_loc=30,
            ),
        ]
        tasks = PlanIngestionWorkflow._derive_tasks_from_features(
            features, {"F-002": ["F-001"]}, file_ownership=None,
        )
        # F-001 has shared.py and is first claimer
        scope_1 = tasks[0]["config"]["context"].get("_file_scope", {})
        assert scope_1.get("pkg/shared.py") == "shared"


# ===================================================================
# Gate 2a: _split_oversized_tasks tests
# ===================================================================


class TestSplitOversizedTasks:
    """Tests for PlanIngestionWorkflow._split_oversized_tasks.

    Gate 2a (defense-in-depth Principle 2): structurally enforce
    max file count per task, even if the PARSE LLM ignored guidance.
    """

    def test_small_tasks_pass_through(self):
        """Tasks with ≤3 files are returned unchanged."""
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
                        "target_files": ["src/a.py", "src/b.py"],
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
        result = PlanIngestionWorkflow._split_oversized_tasks(tasks)
        # PI-007 passes through, PI-008 is split into 4
        assert len(result) == 5
        assert result[0]["task_id"] == "PI-007"
        assert result[1]["task_id"] == "PI-008a"


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

    def test_prime_does_not_emit_context_seed(self, tmp_path):
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

        assert seed_path is None
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
        assert "context_seed_path" not in result.output
        assert not (tmp_path / "artisan-context-seed.json").exists()
