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

        config_path, data = self.wf._phase_emit(
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

        config_path, data = self.wf._phase_emit(
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
        })

        assert not result.success
        state_file = tmp_path / ".startd8" / "plan_ingestion_state.json"
        assert state_file.exists()
        state = json.loads(state_file.read_text())
        assert state["current_phase"] == "failed"
        assert state["error"] is not None
