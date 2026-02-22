"""
Unit tests for LeadContractorWorkflow.

Tests the cost-efficient multi-agent implementation pattern where
Claude acts as lead contractor and cheaper models draft code.
"""

import pytest
from unittest.mock import Mock, patch

from startd8.workflows.builtin.lead_contractor_workflow import (
    LeadContractorWorkflow,
    SPEC_PROMPT_TEMPLATE,
    DRAFT_PROMPT_TEMPLATE,
    REVIEW_PROMPT_TEMPLATE,
    INTEGRATION_PROMPT_TEMPLATE,
)
from startd8.workflows.builtin.lead_contractor_models import (
    LeadContractorConfig,
    ImplementationSpec,
    ReviewResult,
    LeadContractorResult,
    WorkflowPhase,
    TestCase,
)
from startd8.model_catalog import Models


class TestLeadContractorConfig:
    """Tests for LeadContractorConfig data model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = LeadContractorConfig(task_description="Test task")
        assert config.task_description == "Test task"
        # Use Models constants to stay in sync with config defaults
        assert config.lead_agent == Models.LEAD_CONTRACTOR_LEAD
        assert config.drafter_agent == Models.LEAD_CONTRACTOR_DRAFTER
        assert config.max_iterations == 3
        assert config.pass_threshold == 80

    def test_custom_values(self):
        """Test custom configuration values."""
        config = LeadContractorConfig(
            task_description="Custom task",
            lead_agent="anthropic:claude-opus-4-5-20251101",
            drafter_agent="openai:gpt-4.1-nano",
            max_iterations=5,
            pass_threshold=90,
        )
        assert config.max_iterations == 5
        assert config.pass_threshold == 90
        assert config.drafter_agent == "openai:gpt-4.1-nano"


class TestLeadContractorResult:
    """Tests for LeadContractorResult data model."""

    def test_cost_efficiency_ratio_zero_lead(self):
        """Test cost efficiency ratio when lead cost is zero."""
        result = LeadContractorResult(
            workflow_id="test-123",
            success=True,
            final_implementation="code",
            lead_cost=0.0,
            drafter_cost=0.05,
        )
        assert result.get_cost_efficiency_ratio() == 0.0

    def test_cost_efficiency_ratio_normal(self):
        """Test cost efficiency ratio with normal values."""
        result = LeadContractorResult(
            workflow_id="test-123",
            success=True,
            final_implementation="code",
            lead_cost=0.10,
            drafter_cost=0.02,
        )
        assert result.get_cost_efficiency_ratio() == pytest.approx(0.2)

    def test_to_summary(self):
        """Test summary generation."""
        result = LeadContractorResult(
            workflow_id="test-123",
            success=True,
            final_implementation="code",
            total_iterations=2,
            total_time_ms=5000,
            lead_cost=0.10,
            drafter_cost=0.02,
            total_cost=0.12,
        )
        summary = result.to_summary()
        assert summary["workflow_id"] == "test-123"
        assert summary["success"] is True
        assert summary["total_iterations"] == 2
        assert "$0.1200" in summary["total_cost"]


class TestValidateConfig:
    """Tests for workflow configuration validation."""

    def test_valid_config(self):
        """Test validation of valid configuration."""
        workflow = LeadContractorWorkflow()
        result = workflow.validate_config({
            "task_description": "Implement a feature",
            "max_iterations": 3,
            "pass_threshold": 80,
        })
        assert result.valid is True

    def test_missing_task_description(self):
        """Test validation fails when task_description is missing."""
        workflow = LeadContractorWorkflow()
        result = workflow.validate_config({})
        assert result.valid is False
        assert "Missing required input: task_description" in result.errors

    def test_empty_task_description(self):
        """Test validation fails when task_description is empty."""
        workflow = LeadContractorWorkflow()
        result = workflow.validate_config({"task_description": "   "})
        assert result.valid is False
        assert "task_description cannot be empty" in result.errors

    def test_invalid_max_iterations_too_low(self):
        """Test validation fails when max_iterations is too low."""
        workflow = LeadContractorWorkflow()
        result = workflow.validate_config({
            "task_description": "Test",
            "max_iterations": 0,
        })
        assert result.valid is False
        assert any("max_iterations" in e for e in result.errors)

    def test_invalid_max_iterations_too_high(self):
        """Test validation fails when max_iterations is too high."""
        workflow = LeadContractorWorkflow()
        result = workflow.validate_config({
            "task_description": "Test",
            "max_iterations": 15,
        })
        assert result.valid is False
        assert any("max_iterations" in e for e in result.errors)

    def test_invalid_pass_threshold(self):
        """Test validation fails when pass_threshold is invalid."""
        workflow = LeadContractorWorkflow()
        result = workflow.validate_config({
            "task_description": "Test",
            "pass_threshold": 150,
        })
        assert result.valid is False
        assert any("pass_threshold" in e for e in result.errors)


class TestMetadata:
    """Tests for workflow metadata."""

    def test_workflow_id(self):
        """Test workflow ID is correct."""
        workflow = LeadContractorWorkflow()
        assert workflow.metadata.workflow_id == "lead-contractor"

    def test_capabilities(self):
        """Test workflow capabilities."""
        workflow = LeadContractorWorkflow()
        assert "cost-optimization" in workflow.metadata.capabilities
        assert "multi-agent" in workflow.metadata.capabilities
        assert "iterative-development" in workflow.metadata.capabilities

    def test_inputs_defined(self):
        """Test required inputs are defined."""
        workflow = LeadContractorWorkflow()
        input_names = [i.name for i in workflow.metadata.inputs]
        assert "task_description" in input_names
        assert "lead_agent" in input_names
        assert "drafter_agent" in input_names
        assert "max_iterations" in input_names
        assert "pass_threshold" in input_names

    def test_truncation_inputs_defined(self):
        """Test truncation protection inputs are defined with correct defaults."""
        workflow = LeadContractorWorkflow()
        inputs_by_name = {i.name: i for i in workflow.metadata.inputs}

        # check_truncation should exist and default to True
        assert "check_truncation" in inputs_by_name
        assert inputs_by_name["check_truncation"].default is True

        # Granular truncation flags
        assert "fail_on_api_truncation" in inputs_by_name
        assert inputs_by_name["fail_on_api_truncation"].default is True

        assert "fail_on_heuristic_truncation" in inputs_by_name
        assert inputs_by_name["fail_on_heuristic_truncation"].default is False

        # Legacy flag should exist with None default (backward compat)
        assert "fail_on_truncation" in inputs_by_name
        assert inputs_by_name["fail_on_truncation"].default is None

        # strict_truncation should exist and default to False
        assert "strict_truncation" in inputs_by_name
        assert inputs_by_name["strict_truncation"].default is False


class TestScoreParsing:
    """Tests for review score parsing."""

    def test_parse_score_simple(self):
        """Test parsing simple score format."""
        workflow = LeadContractorWorkflow()
        score = workflow._parse_score("### Score: 85\nSome review text")
        assert score == 85

    def test_parse_score_with_spaces(self):
        """Test parsing score with extra spaces."""
        workflow = LeadContractorWorkflow()
        score = workflow._parse_score("Score:   92  \n")
        assert score == 92

    def test_parse_score_case_insensitive(self):
        """Test parsing score is case insensitive."""
        workflow = LeadContractorWorkflow()
        score = workflow._parse_score("SCORE: 78")
        assert score == 78

    def test_parse_score_missing(self):
        """Test parsing returns 0 when score not found."""
        workflow = LeadContractorWorkflow()
        score = workflow._parse_score("No score here")
        assert score == 0

    def test_parse_score_clamps_high(self):
        """Test score is clamped to max 100."""
        workflow = LeadContractorWorkflow()
        score = workflow._parse_score("Score: 150")
        assert score == 100

    def test_parse_score_clamps_low(self):
        """Test score is clamped to min 0."""
        workflow = LeadContractorWorkflow()
        score = workflow._parse_score("Score: -5")
        assert score == 0


class TestListParsing:
    """Tests for parsing bulleted list sections."""

    def test_parse_issues(self):
        """Test parsing issues list."""
        workflow = LeadContractorWorkflow()
        text = """### Issues
- First issue
- Second issue
- Third issue

### Suggestions
- A suggestion
"""
        issues = workflow._parse_list_section(text, "Issues")
        assert len(issues) == 3
        assert "First issue" in issues
        assert "Second issue" in issues

    def test_parse_empty_section(self):
        """Test parsing empty section returns empty list."""
        workflow = LeadContractorWorkflow()
        text = "### Other\n- Item"
        issues = workflow._parse_list_section(text, "Issues")
        assert issues == []

    def test_parse_with_asterisks(self):
        """Test parsing with asterisk bullets."""
        workflow = LeadContractorWorkflow()
        text = """### Strengths
* Good structure
* Clean code
"""
        strengths = workflow._parse_list_section(text, "Strengths")
        assert len(strengths) == 2
        assert "Good structure" in strengths


class TestReviewFeedbackFormatting:
    """Tests for formatting review feedback."""

    def test_format_review_feedback(self):
        """Test feedback formatting includes key sections."""
        workflow = LeadContractorWorkflow()
        review = ReviewResult(
            review_id="r-123",
            iteration=1,
            passed=False,
            score=65,
            issues=["Bug in function X", "Missing error handling"],
            blocking_issues=["Critical bug"],
            suggestions=["Add tests", "Improve naming"],
            review_text="Full review..."
        )
        feedback = workflow._format_review_feedback(review)

        assert "Score: 65/100" in feedback
        assert "Bug in function X" in feedback
        assert "Critical bug" in feedback
        assert "Add tests" in feedback

    def test_format_review_feedback_empty_lists(self):
        """Test feedback formatting with empty lists."""
        workflow = LeadContractorWorkflow()
        review = ReviewResult(
            review_id="r-123",
            iteration=1,
            passed=True,
            score=90,
            review_text="LGTM"
        )
        feedback = workflow._format_review_feedback(review)

        assert "None" in feedback  # Should show "None" for empty lists


class TestTestPlanGeneration:
    """Tests for test plan generation."""

    def test_generate_test_plan_json_empty(self):
        """Test JSON test plan generation with empty result."""
        workflow = LeadContractorWorkflow()
        result = LeadContractorResult(
            workflow_id="lc-123",
            success=True,
            final_implementation="code"
        )
        plan = workflow.generate_test_plan_json(result)

        assert plan.plan_id == "test-lc-123"
        assert plan.workflow_id == "lc-123"
        assert plan.total_tests == 0

    def test_generate_test_plan_json_with_criteria(self):
        """Test JSON test plan generation with acceptance criteria."""
        workflow = LeadContractorWorkflow()
        result = LeadContractorResult(
            workflow_id="lc-123",
            success=True,
            final_implementation="code",
            spec=ImplementationSpec(
                spec_id="s-123",
                task_summary="Test task",
                requirements=[],
                technical_approach="approach",
                acceptance_criteria=[
                    "Function returns correct value",
                    "Error cases are handled"
                ],
                edge_cases=["Empty input"]
            )
        )
        plan = workflow.generate_test_plan_json(result)

        assert plan.total_tests == 3  # 2 criteria + 1 edge case
        assert plan.by_priority.get("P1", 0) == 2
        assert plan.by_priority.get("P2", 0) == 1

    def test_generate_test_plan_markdown(self):
        """Test Markdown test plan generation."""
        workflow = LeadContractorWorkflow()
        result = LeadContractorResult(
            workflow_id="lc-123",
            success=True,
            final_implementation="code",
            total_iterations=2,
            total_cost=0.05,
            spec=ImplementationSpec(
                spec_id="s-123",
                task_summary="Test task",
                requirements=[],
                technical_approach="approach",
                acceptance_criteria=["Criterion 1"]
            ),
            reviews=[ReviewResult(
                review_id="r-1",
                iteration=2,
                passed=True,
                score=90,
                review_text="Good"
            )]
        )
        md = workflow.generate_test_plan_markdown(result)

        assert "lc-123" in md
        assert "**Iterations**: 2" in md
        assert "**Final Score**: 90" in md
        assert "$0.05" in md


class TestPromptTemplates:
    """Tests for prompt template formatting."""

    def test_spec_prompt_template_format(self):
        """Test spec prompt template can be formatted."""
        prompt = SPEC_PROMPT_TEMPLATE.format(
            task_description="Implement feature X",
            requirements_section="",
            context_sections="## Context\nContext info",
            critical_parameters_section="",
            domain_constraints="(No domain-specific constraints)",
        )
        assert "Implement feature X" in prompt
        assert "Context info" in prompt
        assert "Implementation Specification" not in prompt  # That's in draft prompt
        assert "Domain Constraints" in prompt

    def test_draft_prompt_template_format(self):
        """Test draft prompt template can be formatted (single-file)."""
        from startd8.workflows.builtin.lead_contractor_workflow import _build_output_format
        prompt = DRAFT_PROMPT_TEMPLATE.format(
            spec="Detailed spec...",
            feedback="No feedback yet",
            existing_files_section="",
            output_format=_build_output_format(None),
        )
        assert "Detailed spec..." in prompt
        assert "No feedback yet" in prompt
        assert "[Your implementation code here]" in prompt

    def test_draft_prompt_template_multi_file(self):
        """Test draft prompt template with multi-file output format."""
        from startd8.workflows.builtin.lead_contractor_workflow import _build_output_format
        target_files = ["src/main.py", "data/output.csv"]
        prompt = DRAFT_PROMPT_TEMPLATE.format(
            spec="Multi-file spec",
            feedback="No feedback",
            existing_files_section="",
            output_format=_build_output_format(target_files),
        )
        assert "SEPARATE fenced code block" in prompt
        assert "`src/main.py`" in prompt
        assert "`data/output.csv`" in prompt

    def test_review_prompt_template_format(self):
        """Test review prompt template can be formatted."""
        prompt = REVIEW_PROMPT_TEMPLATE.format(
            task_description="Task description",
            spec="The spec",
            implementation="The code",
            pass_threshold=80
        )
        assert "Task description" in prompt
        assert "The spec" in prompt
        assert "80" in prompt

    def test_integration_prompt_template_format(self):
        """Test integration prompt template can be formatted."""
        prompt = INTEGRATION_PROMPT_TEMPLATE.format(
            task_description="Task",
            implementation="Code",
            review_history="History",
            integration_instructions="Instructions"
        )
        assert "Task" in prompt
        assert "Code" in prompt
        assert "Instructions" in prompt


class TestWorkflowExecution:
    """Tests for workflow execution with mocked agents."""

    @patch('startd8.workflows.builtin.lead_contractor_workflow.resolve_agent_spec')
    def test_workflow_run_success(self, mock_resolve):
        """Test successful workflow execution."""
        # Create mock token usage objects with was_truncated=False
        def make_token_usage(input_tokens, output_tokens):
            usage = Mock()
            usage.input = input_tokens
            usage.output = output_tokens
            usage.was_truncated = False
            return usage

        # Create mock agents
        mock_lead = Mock()
        mock_lead.name = "claude"
        mock_lead.model = "claude-sonnet-4-5-20250929"
        mock_lead.generate.return_value = (
            "### Score: 90\n### Verdict: PASS\n### Strengths\n- Good code",
            1000,
            make_token_usage(500, 200)
        )

        mock_drafter = Mock()
        mock_drafter.name = "gemini"
        mock_drafter.model = "gemini-2.5-flash-lite"
        mock_drafter.generate.return_value = (
            "```python\ndef feature():\n    pass\n```",
            500,
            make_token_usage(300, 100)
        )

        mock_resolve.side_effect = [mock_lead, mock_drafter]

        workflow = LeadContractorWorkflow()
        result = workflow.run(
            config={
                "task_description": "Implement a test feature",
                "max_iterations": 2,
                "fail_on_truncation": False,  # Disable for mock tests
            }
        )

        assert result.success is True
        assert result.workflow_id == "lead-contractor"
        assert "lead_cost" in result.metadata
        assert "drafter_cost" in result.metadata

    @patch('startd8.workflows.builtin.lead_contractor_workflow.resolve_agent_spec')
    def test_workflow_run_agent_resolution_failure(self, mock_resolve):
        """Test workflow fails gracefully when agent resolution fails."""
        mock_resolve.side_effect = Exception("API key not found")

        workflow = LeadContractorWorkflow()
        result = workflow.run(
            config={"task_description": "Test task"}
        )

        assert result.success is False
        assert "Failed to resolve agents" in result.error

    @patch('startd8.workflows.builtin.lead_contractor_workflow.resolve_agent_spec')
    def test_workflow_tracks_iterations(self, mock_resolve):
        """Test workflow correctly tracks iteration count."""
        # Create mock token usage objects with was_truncated=False
        def make_token_usage(input_tokens, output_tokens):
            usage = Mock()
            usage.input = input_tokens
            usage.output = output_tokens
            usage.was_truncated = False
            return usage

        mock_lead = Mock()
        mock_lead.name = "claude"
        mock_lead.model = "claude-sonnet-4-5-20250929"

        # First review fails, second passes
        mock_lead.generate.side_effect = [
            ("Spec content", 1000, make_token_usage(500, 200)),
            ("### Score: 60\n### Verdict: FAIL\n### Issues\n- Fix X", 800, make_token_usage(400, 150)),
            ("### Score: 85\n### Verdict: PASS", 800, make_token_usage(400, 150)),
            ("Final code", 600, make_token_usage(300, 200)),
        ]

        mock_drafter = Mock()
        mock_drafter.name = "gemini"
        mock_drafter.model = "gemini-2.5-flash-lite"
        mock_drafter.generate.return_value = (
            "```python\ndef implementation():\n    pass\n```",  # Proper code block
            500,
            make_token_usage(300, 100)
        )

        mock_resolve.side_effect = [mock_lead, mock_drafter]

        workflow = LeadContractorWorkflow()
        result = workflow.run(
            config={
                "task_description": "Test task",
                "max_iterations": 3,
                "fail_on_truncation": False,  # Disable for mock tests
            }
        )

        assert result.metadata["total_iterations"] == 2


class TestWorkflowPhaseEnum:
    """Tests for WorkflowPhase enum."""

    def test_all_phases_defined(self):
        """Test all expected phases are defined."""
        phases = list(WorkflowPhase)
        phase_values = [p.value for p in phases]

        assert "spec_creation" in phase_values
        assert "drafting" in phase_values
        assert "review" in phase_values
        assert "integration" in phase_values
        assert "completed" in phase_values
        assert "failed" in phase_values


class TestTestCaseModel:
    """Tests for TestCase Pydantic model."""

    def test_test_case_creation(self):
        """Test creating a TestCase instance."""
        tc = TestCase(
            id="TC-001",
            name="Test feature",
            description="Test description",
            priority="P1",
            category="unit",
            steps=["Step 1", "Step 2"],
            expected_result="Success"
        )
        assert tc.id == "TC-001"
        assert tc.automation_status == "pending"

    def test_test_case_defaults(self):
        """Test TestCase default values."""
        tc = TestCase(
            id="TC-001",
            name="Test",
            description="Desc",
            priority="P0",
            category="integration",
            expected_result="Pass"
        )
        assert tc.preconditions == []
        assert tc.steps == []
        assert tc.automation_status == "pending"
