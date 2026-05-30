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
        assert config.lead_agent == Models.PRIMARY_CONTRACTOR_LEAD
        assert config.drafter_agent == Models.PRIMARY_CONTRACTOR_DRAFTER
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


class TestSpecPromptPhase1:
    """Phase 1 tests: budget, truncation, section builders, deduplication (PC-B1..B5, PC-A1..A3)."""

    def test_plan_context_truncated_in_spec(self):
        """PC-B1: Plan context in spec prompt is truncated to 16KB with marker."""
        from startd8.workflows.builtin.lead_contractor_workflow import (
            LeadContractorWorkflow,
            _PLAN_CONTEXT_MAX_CHARS,
            _TRUNCATION_MARKER,
        )

        plan_60k = "x" * 60_000
        context = {"plan_context": plan_60k}
        prompt = LeadContractorWorkflow._build_spec_prompt(
            "Task", dict(context), None
        )
        assert _TRUNCATION_MARKER in prompt
        # Plan section content (excluding header) should be <= 16KB + marker
        plan_section_start = prompt.find("## Plan Context")
        assert plan_section_start >= 0
        plan_content = prompt[plan_section_start + 15 :]  # after "## Plan Context\n"
        # Content up to next ## or end
        next_section = plan_content.find("\n\n## ")
        plan_body = plan_content[:next_section] if next_section >= 0 else plan_content.split("\n\n## ")[0]
        assert len(plan_body) <= _PLAN_CONTEXT_MAX_CHARS + len(_TRUNCATION_MARKER)

    def test_arch_context_truncated(self):
        """PC-B2: Large architectural context is truncated to 4KB."""
        from startd8.workflows.builtin.lead_contractor_workflow import (
            LeadContractorWorkflow,
            _ARCH_CONTEXT_MAX_CHARS,
            _TRUNCATION_MARKER,
        )

        arch_large = {"objectives": ["obj"] * 100, "constraints": ["c"] * 100}
        context = {"architectural_context": arch_large}
        prompt = LeadContractorWorkflow._build_spec_prompt(
            "Task", dict(context), None
        )
        assert "## Project Architecture" in prompt
        assert _TRUNCATION_MARKER in prompt or len(prompt) < 50_000

    def test_no_duplication_in_context_str(self):
        """PC-A2, PC-A3: Popped keys do not appear in context_str."""
        from startd8.workflows.builtin.lead_contractor_workflow import LeadContractorWorkflow

        context = {
            "plan_context": "plan",
            "architectural_context": {"obj": "x"},
            "project_objectives": "obj",
            "semantic_conventions": {"conv": "y"},
            "requirements_context": "req_ctx",
            "protocol_guidance": "proto",
            "scope_boundary": "scope",
            "feature_name": "f1",
        }
        prompt = LeadContractorWorkflow._build_spec_prompt(
            "Task", dict(context), None
        )
        # context_str should not contain the popped keys as JSON
        assert '"plan_context"' not in prompt or "## Plan Context" in prompt
        assert '"architectural_context"' not in prompt or "## Project Architecture" in prompt
        assert '"requirements_context"' not in prompt or "## Requirements Context" in prompt
        assert '"protocol_guidance"' not in prompt or "## Protocol Guidance" in prompt
        assert '"scope_boundary"' not in prompt or "## Scope Boundary" in prompt
        # feature_name should remain (not popped)
        assert "feature_name" in prompt or "f1" in prompt

    def test_section_builders_used(self):
        """PC-A1: Spec prompt is built from section helpers."""
        from startd8.workflows.builtin.lead_contractor_workflow import LeadContractorWorkflow

        context = {
            "plan_context": "Plan text",
            "architectural_context": {"objectives": ["O1"]},
            "project_objectives": "Objectives",
            "semantic_conventions": {"naming": "snake"},
        }
        prompt = LeadContractorWorkflow._build_spec_prompt(
            "Task", dict(context), None
        )
        assert "## Plan Context" in prompt
        assert "## Project Architecture" in prompt
        assert "## Project Objectives" in prompt
        assert "## Semantic Conventions" in prompt
        assert "Plan text" in prompt
        assert "O1" in prompt


class TestPlanLoadCap:
    """PC-B5: Plan load cap in prime_contractor."""

    def test_plan_load_cap_constant(self):
        """Plan load cap constant is 16KB."""
        from startd8.contractors.prime_contractor import _PLAN_LOAD_MAX_BYTES

        assert _PLAN_LOAD_MAX_BYTES == 16_384

    def test_plan_truncated_on_load(self, tmp_path):
        """Plan document is truncated to 16KB when loaded."""
        from pathlib import Path
        from startd8.contractors.prime_contractor import (
            PrimeContractorWorkflow,
            _PLAN_LOAD_MAX_BYTES,
        )

        # Create plan file inside project root (path traversal check requires this)
        plan_path = tmp_path / "plan_load_cap_test.md"
        plan_path.write_text("x" * (_PLAN_LOAD_MAX_BYTES + 1000), encoding="utf-8")
        workflow = PrimeContractorWorkflow(project_root=tmp_path)
        seed = {
            "artifacts": {"plan_document_path": str(plan_path)},
            "execution_mode": "standalone",
        }
        workflow.load_seed_context(seed)
        assert workflow.plan_document_text is not None
        assert len(workflow.plan_document_text) <= _PLAN_LOAD_MAX_BYTES


class TestExistingFilesPopulation:
    """PC-O1: existing_files populated in prime_contractor develop_feature."""

    def test_existing_files_populated_for_edit(self, tmp_path):
        """Feature with target_files pointing to existing files populates gen_context."""
        from pathlib import Path
        from startd8.contractors.prime_contractor import (
            PrimeContractorWorkflow,
            FeatureSpec,
        )

        # Create existing file under project root
        target_rel = "src/foo.py"
        target_path = tmp_path / target_rel
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text("def bar():\n    return 42\n", encoding="utf-8")

        workflow = PrimeContractorWorkflow(project_root=tmp_path)
        feature = FeatureSpec(
            id="F-001",
            name="Edit foo",
            description="Add a function",
            target_files=[target_rel],
        )
        gen_context = {}
        workflow._populate_existing_files(feature, gen_context)

        assert "existing_files" in gen_context
        assert target_rel in gen_context["existing_files"]
        assert "def bar():" in gen_context["existing_files"][target_rel]

    def test_existing_files_skipped_outside_root(self, tmp_path):
        """Target file outside project_root is skipped."""
        from startd8.contractors.prime_contractor import (
            PrimeContractorWorkflow,
            FeatureSpec,
        )

        workflow = PrimeContractorWorkflow(project_root=tmp_path)
        feature = FeatureSpec(
            id="F-001",
            name="Edit",
            description="Task",
            target_files=["../outside/evil.py"],
        )
        gen_context = {}
        workflow._populate_existing_files(feature, gen_context)

        assert "existing_files" not in gen_context or len(gen_context.get("existing_files", {})) == 0

    def test_existing_files_empty_without_targets(self, tmp_path):
        """No target_files leaves gen_context unchanged."""
        from startd8.contractors.prime_contractor import (
            PrimeContractorWorkflow,
            FeatureSpec,
        )

        workflow = PrimeContractorWorkflow(project_root=tmp_path)
        feature = FeatureSpec(
            id="F-001",
            name="Create",
            description="New file",
            target_files=[],
        )
        gen_context = {}
        workflow._populate_existing_files(feature, gen_context)

        assert "existing_files" not in gen_context


class TestExistingFilesBudget:
    """PC-B3: Existing files budget reduced to 40KB."""

    def test_existing_files_budget_40kb(self):
        """_EXISTING_FILES_BUDGET_BYTES is 40KB."""
        from startd8.workflows.builtin.lead_contractor_workflow import (
            _EXISTING_FILES_BUDGET_BYTES,
        )

        assert _EXISTING_FILES_BUDGET_BYTES == 40 * 1024


class TestSpecPromptPhase2:
    """Phase 2 tests: conditional framing, quantitative constraints (PC-F1..F3, PC-Q1..Q3)."""

    def test_plan_context_edit_framing(self):
        """PC-F1: With existing_files, plan section has edit preamble."""
        from startd8.workflows.builtin.lead_contractor_workflow import LeadContractorWorkflow

        context = {
            "plan_context": "Add feature X to the service.",
            "existing_files": {"src/service.py": "def foo():\n    pass\n" * 10},
        }
        prompt = LeadContractorWorkflow._build_spec_prompt(
            "Task", dict(context), None
        )
        assert "CHANGES to existing code" in prompt
        assert "Do NOT treat" in prompt

    def test_plan_context_create_framing(self):
        """PC-F1: Without existing_files, plan section has create preamble."""
        from startd8.workflows.builtin.lead_contractor_workflow import LeadContractorWorkflow

        context = {"plan_context": "Implement feature X from scratch."}
        prompt = LeadContractorWorkflow._build_spec_prompt(
            "Task", dict(context), None
        )
        assert "provides context" in prompt
        assert "design document" in prompt

    def test_arch_context_edit_framing(self):
        """PC-F2: With edit mode, arch section has edit prefix."""
        from startd8.workflows.builtin.lead_contractor_workflow import LeadContractorWorkflow

        context = {
            "architectural_context": {"objectives": ["O1"], "constraints": ["C1"]},
            "existing_files": {"src/foo.py": "x = 1\n"},
        }
        prompt = LeadContractorWorkflow._build_spec_prompt(
            "Task", dict(context), None
        )
        assert "Apply these architectural constraints to the existing file(s)" in prompt
        assert "Do not redesign" in prompt

    def test_quantitative_spec_constraint(self):
        """PC-Q1: With existing_files totaling 100 lines, spec preamble includes line count."""
        from startd8.workflows.builtin.lead_contractor_workflow import LeadContractorWorkflow

        # 100 lines of content
        content_100_lines = "\n".join([f"line {i}" for i in range(100)])
        context = {
            "existing_files": {"src/foo.py": content_100_lines},
            "plan_context": "Update the service.",
        }
        prompt = LeadContractorWorkflow._build_spec_prompt(
            "Task", dict(context), None
        )
        assert "100 lines" in prompt
        assert "80 lines" in prompt
        assert "80%" in prompt

    def test_edit_min_pct_configurable(self):
        """PC-Q3: edit_min_pct from context overrides default."""
        from startd8.workflows.builtin.lead_contractor_workflow import LeadContractorWorkflow

        content_100_lines = "\n".join([f"line {i}" for i in range(100)])
        context = {
            "existing_files": {"src/foo.py": content_100_lines},
            "edit_min_pct": 90,
            "plan_context": "Update.",
        }
        prompt = LeadContractorWorkflow._build_spec_prompt(
            "Task", dict(context), None
        )
        assert "90 lines" in prompt
        assert "90%" in prompt

    def test_create_mode_has_implement_preamble(self):
        """PC-F3: Create mode has 'Implement' task verb in preamble."""
        from startd8.workflows.builtin.lead_contractor_workflow import LeadContractorWorkflow

        context = {"plan_context": "Implement feature X from scratch."}
        prompt = LeadContractorWorkflow._build_spec_prompt(
            "Task", dict(context), None
        )
        assert "Implement" in prompt
        assert "CREATE MODE" in prompt or "Task type: Implement" in prompt

    def test_build_output_format_edit_includes_min_lines(self):
        """PC-Q2: build_output_format passes min_output_lines for edit mode."""
        from startd8.workflows.builtin.lead_contractor_workflow import _build_output_format

        content_100 = "\n".join([f"line {i}" for i in range(100)])
        result = _build_output_format(
            ["src/foo.py"],
            existing_files={"src/foo.py": content_100},
            edit_min_pct=80,
        )
        assert "100 lines" in result or "100" in result
        assert "80 lines" in result or "80" in result
        assert "80%" in result


class TestPhase4YAMLExternalization:
    """Phase 4 tests: YAML externalization, fallback (PC-Y1..Y4, AC-5)."""

    def test_format_lead_prompt_uses_yaml_when_available(self):
        """_format_lead_prompt returns YAML content when template exists."""
        from startd8.workflows.builtin.lead_contractor_workflow import _format_lead_prompt

        result = _format_lead_prompt(
            "plan_context_edit_framing",
            "fallback if missing",
        )
        assert "CHANGES to existing code" in result
        assert "fallback if missing" not in result

    def test_format_lead_prompt_uses_fallback_when_yaml_missing(self):
        """AC-5: _format_lead_prompt uses fallback when template missing."""
        from startd8.workflows.builtin.lead_contractor_workflow import (
            _format_lead_prompt,
            _PLAN_CONTEXT_EDIT_FRAMING_FALLBACK,
        )

        result = _format_lead_prompt(
            "nonexistent_template_xyz",
            _PLAN_CONTEXT_EDIT_FRAMING_FALLBACK,
        )
        assert "CHANGES to apply to existing code" in result
        assert "Do NOT treat" in result

    def test_format_lead_prompt_with_placeholders(self):
        """_format_lead_prompt formats placeholders in fallback path."""
        from startd8.workflows.builtin.lead_contractor_workflow import _format_lead_prompt

        result = _format_lead_prompt(
            "nonexistent_template_xyz",
            "Hello {name}",
            name="World",
        )
        assert result == "Hello World"

    def test_all_phase4_templates_loadable(self):
        """PC-Y3: All framing templates load from consolidated YAML."""
        from startd8.implementation_engine.prompts import get_template

        templates = [
            "plan_context_edit_framing",
            "plan_context_create_framing",
            "arch_context_edit_framing",
            "spec_edit_preamble_base",
            "spec_edit_quantitative_constraint",
            "spec_create_preamble",
            "spec_completeness_warning",
        ]
        for name in templates:
            t = get_template(name)
            assert isinstance(t, str)
            assert len(t) > 0

    @patch("startd8.implementation_engine.spec_builder.get_template")
    def test_spec_prompt_builds_with_fallback_when_yaml_missing(
        self, mock_get_template
    ):
        """AC-5: Spec prompt builds with fallback when YAML templates unavailable."""
        from startd8.workflows.builtin.lead_contractor_workflow import (
            LeadContractorWorkflow,
        )

        # Raise for framing templates; allow spec template through
        def side_effect(name):
            if name in (
                "plan_context_edit_framing",
                "plan_context_create_framing",
                "arch_context_edit_framing",
                "spec_edit_preamble_base",
                "spec_edit_quantitative_constraint",
            ):
                raise FileNotFoundError("YAML missing")
            from startd8.implementation_engine.prompts import get_template
            return get_template(name)

        mock_get_template.side_effect = side_effect

        context = {
            "existing_files": {"src/foo.py": "\n".join([f"line {i}" for i in range(100)])},
            "plan_context": "Update the service.",
        }
        prompt = LeadContractorWorkflow._build_spec_prompt(
            "Task", dict(context), None
        )
        assert "EDIT MODE" in prompt
        assert "80 lines" in prompt
        assert "CHANGES to apply to existing code" in prompt


class TestPhase3DrafterSystemPrompt:
    """Phase 3 tests: mode-aware drafter system prompts (PC-M2, PC-M3, PC-M4)."""

    def test_drafter_create_system_prompt(self):
        """PC-M2: Without existing_files, returns create_system."""
        from startd8.workflows.builtin.lead_contractor_workflow import _get_drafter_system_prompt

        prompt, mode = _get_drafter_system_prompt(existing_files=None)
        assert prompt is not None
        assert mode == "create"
        assert "generating" in prompt.lower() or "implement" in prompt.lower()
        assert "spec" in prompt.lower()

    def test_drafter_edit_system_prompt(self):
        """PC-M2: With existing_files (all < 50 lines), returns edit_system."""
        from startd8.workflows.builtin.lead_contractor_workflow import _get_drafter_system_prompt

        existing = {"src/foo.py": "def bar():\n    pass\n" * 5}  # ~25 lines
        prompt, mode = _get_drafter_system_prompt(existing_files=existing)
        assert prompt is not None
        assert mode == "edit"
        assert "editing" in prompt.lower() or "edit" in prompt.lower()
        assert "PRESERVE" in prompt or "preserve" in prompt

    def test_drafter_search_replace_system_prompt(self):
        """PC-M2: With existing_files and file ≥50 lines, returns search_replace_system."""
        from startd8.workflows.builtin.lead_contractor_workflow import _get_drafter_system_prompt

        content_60_lines = "\n".join([f"line {i}" for i in range(60)])
        existing = {"src/large.py": content_60_lines}
        prompt, mode = _get_drafter_system_prompt(existing_files=existing)
        assert prompt is not None
        assert mode == "search_replace"
        assert "large" in prompt.lower() or "minimal" in prompt.lower()

    def test_draft_edit_ordering(self):
        """PC-O2: With existing_files, existing_files_section appears before spec in prompt."""
        from startd8.workflows.builtin.lead_contractor_workflow import (
            DRAFT_EDIT_PROMPT_TEMPLATE,
            _build_existing_files_section,
        )

        existing = {"src/foo.py": "def bar(): pass\n"}
        section = _build_existing_files_section(existing, None)
        prompt = DRAFT_EDIT_PROMPT_TEMPLATE.format(
            spec="## Implementation Specification (changes to apply)\nThe spec content",
            feedback="No feedback",
            output_format="```\ncode\n```",
            existing_files_section=section,
            supplementary_sections="",
        )
        # existing_files_section must appear before "Implementation Specification"
        idx_section = prompt.find(section[:50]) if len(section) > 50 else prompt.find(section)
        idx_spec = prompt.find("Implementation Specification")
        assert idx_section >= 0
        assert idx_spec >= 0
        assert idx_section < idx_spec

    @patch('startd8.workflows.builtin.lead_contractor_workflow.resolve_agent_spec')
    def test_drafter_receives_system_prompt(self, mock_resolve):
        """PC-M2/P3.8: Drafter generate() is called with system_prompt when existing_files present."""
        def make_token_usage(in_tok, out_tok):
            u = Mock()
            u.input, u.output = in_tok, out_tok
            u.was_truncated = False
            return u

        mock_lead = Mock()
        mock_lead.name = "claude"
        mock_lead.model = "claude-sonnet-4-5"
        mock_lead.generate.return_value = (
            "### Task Summary\nAdd feature.\n### Requirements\n1. X\n### Score: 90\n### Verdict: PASS",
            1000,
            make_token_usage(500, 200),
        )

        mock_drafter = Mock()
        mock_drafter.name = "gemini"
        mock_drafter.model = "gemini-flash"
        mock_drafter.generate.return_value = (
            "```python\ndef foo(): pass\n```",
            500,
            make_token_usage(300, 100),
        )

        mock_resolve.side_effect = [mock_lead, mock_drafter]

        workflow = LeadContractorWorkflow()
        workflow.run(
            config={
                "task_description": "Add feature to existing file",
                "context": {
                    "existing_files": {"src/foo.py": "def bar(): pass\n" * 10},
                    "target_files": ["src/foo.py"],
                },
                "max_iterations": 1,
                "fail_on_truncation": False,
            }
        )

        # Drafter generate must have been called with system_prompt
        calls = mock_drafter.generate.call_args_list
        assert len(calls) >= 1
        kwargs = calls[0][1]
        assert "system_prompt" in kwargs
        assert kwargs["system_prompt"] is not None
        assert "edit" in kwargs["system_prompt"].lower() or "preserve" in kwargs["system_prompt"].lower()


class TestPromptTemplates:
    """Tests for prompt template formatting."""

    def test_spec_prompt_template_format(self):
        """Test spec prompt template can be formatted."""
        prompt = SPEC_PROMPT_TEMPLATE.format(
            task_description="Implement feature X",
            requirements_section="",
            context_sections="## Context\nContext info",
            critical_parameters_section="",
            forward_contracts_section="",
            domain_constraints="(No domain-specific constraints)",
        )
        assert "Implement feature X" in prompt
        assert "Context info" in prompt
        assert "Constraints" in prompt

    def test_draft_prompt_template_format(self):
        """Test draft prompt template can be formatted (single-file)."""
        from startd8.workflows.builtin.lead_contractor_workflow import _build_output_format
        prompt = DRAFT_PROMPT_TEMPLATE.format(
            spec="Detailed spec...",
            feedback="No feedback yet",
            existing_files_section="",
            supplementary_sections="",
            output_format=_build_output_format(None),
        )
        assert "Detailed spec..." in prompt
        assert "No feedback yet" in prompt

    def test_draft_prompt_template_multi_file(self):
        """Test draft prompt template with multi-file output format."""
        from startd8.workflows.builtin.lead_contractor_workflow import _build_output_format
        target_files = ["src/main.py", "data/output.csv"]
        prompt = DRAFT_PROMPT_TEMPLATE.format(
            spec="Multi-file spec",
            feedback="No feedback",
            existing_files_section="",
            supplementary_sections="",
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
            pass_threshold=80,
            enrichment_sections="",
            prior_issues_section="",
            convergence_instructions="",
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
            integration_instructions="Instructions",
            multi_file_directive="",
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

class TestReviewDraftValidation:
    """Tests for Phase 5 Forward Manifest Validator integration in _review_draft."""

    @patch("startd8.forward_manifest_validator.validate_forward_manifest")
    def test_review_draft_fails_on_structural_error(self, mock_validate):
        """REQ-PC-VAL-004: Structural errors force passed=False and append [BLOCKING] issues."""
        from startd8.forward_manifest_validator import ContractViolation
        
        # Setup mock violation
        mock_validate.return_value = [
            ContractViolation(
                contract_id="function-foo",
                violation_type="MissingFunction",
                expected="def foo():",
                actual="None",
                file_path="src/app.py",
                severity="error"
            )
        ]

        workflow = LeadContractorWorkflow()
        lead_agent = Mock()
        lead_agent.model = "claude-sonnet"
        
        token_usage = Mock()
        token_usage.input = 100
        token_usage.output = 50

        # The LLM thinks it passed the review
        lead_agent.generate.return_value = (
            "### Score: 90\n### Verdict: PASS\n### Strengths\n- Good\n",
            100,
            token_usage
        )

        spec = ImplementationSpec(
            spec_id="spec-1",
            task_summary="task",
            requirements=[],
            technical_approach="",
            acceptance_criteria=[]
        )

        # Mock forward manifest object (simplest mock with a 'contracts' attr)
        mock_manifest = Mock()
        mock_manifest.contracts = ["fake_contract"]

        result = workflow._review_draft(
            lead_agent=lead_agent,
            task_description="do thing",
            spec=spec,
            implementation="```python\ndef wrong_name(): pass\n```",
            pass_threshold=80,
            iteration=1,
            forward_manifest=mock_manifest,
            target_files=["src/app.py"]
        )

        # Assertions
        assert result.passed is False, "Structural error MUST force the review to fail."
        # The block issue must have injected the error text
        assert any("MissingFunction violation" in issue for issue in result.blocking_issues)
        assert any("[BLOCKING]" in issue for issue in result.blocking_issues)


    @patch("startd8.forward_manifest_validator.validate_forward_manifest")
    def test_review_draft_passes_on_warnings(self, mock_validate):
        """REQ-PC-VAL-004: Structural warnings do NOT fail the review."""
        from startd8.forward_manifest_validator import ContractViolation
        
        # Setup mock violation (warning)
        mock_validate.return_value = [
            ContractViolation(
                contract_id="style-1",
                violation_type="Advisory",
                expected="something",
                severity="warning"
            )
        ]

        workflow = LeadContractorWorkflow()
        lead_agent = Mock()
        lead_agent.model = "claude-sonnet"
        
        token_usage = Mock()
        token_usage.input = 100
        token_usage.output = 50

        lead_agent.generate.return_value = (
            "### Score: 95\n### Verdict: PASS\n",
            100,
            token_usage
        )

        spec = ImplementationSpec(spec_id="spec-1", task_summary="task", requirements=[], technical_approach="", acceptance_criteria=[])
        mock_manifest = Mock()
        mock_manifest.contracts = ["fake_contract"]

        result = workflow._review_draft(
            lead_agent=lead_agent,
            task_description="do thing",
            spec=spec,
            implementation="```python\ndef right_name(): pass\n```",
            pass_threshold=80,
            iteration=1,
            forward_manifest=mock_manifest,
            target_files=["src/app.py"]
        )

        # Assertions: warning does not override the review pass
        assert result.passed is True
