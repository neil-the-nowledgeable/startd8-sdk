"""
Unit tests for the Workflow Help System
Tests workflow-specific help, intro panels, step guidance, and examples.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from rich.console import Console

from startd8.tui_workflow_help import WorkflowHelper, WorkflowHelp, WorkflowExample


class TestWorkflowHelperInitialization:
    """Test WorkflowHelper initialization and configuration loading"""

    def test_init_with_default_config_dir(self):
        """Test initialization with default config directory"""
        helper = WorkflowHelper()
        assert helper.config_dir is not None
        assert helper.console is not None

    def test_init_with_custom_console(self):
        """Test initialization with custom console"""
        custom_console = Console()
        helper = WorkflowHelper(console=custom_console)
        assert helper.console == custom_console

    def test_init_with_custom_config_dir(self):
        """Test initialization with custom config directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            helper = WorkflowHelper(config_dir=tmpdir)
            assert helper.config_dir == Path(tmpdir)

    def test_workflows_loaded(self):
        """Test that workflows are loaded from configuration"""
        helper = WorkflowHelper()
        assert len(helper.workflows) > 0
        assert "iterative_workflow" in helper.workflows

    def test_examples_loaded(self):
        """Test that examples are loaded from configuration"""
        helper = WorkflowHelper()
        assert len(helper.examples) > 0
        assert "iterative_workflow" in helper.examples


class TestWorkflowHelps:
    """Test workflow help functionality"""

    def test_workflow_help_creation(self):
        """Test WorkflowHelp dataclass creation"""
        workflow = WorkflowHelp(
            key="test_workflow",
            title="Test Workflow",
            icon="🧪",
            description="Test description",
            what_it_does="Test",
            how_it_works="Test",
            use_cases="Test",
            requirements="None",
            tips="Test",
            steps=3,
            step_names=["Step 1", "Step 2", "Step 3"]
        )
        assert workflow.key == "test_workflow"
        assert workflow.title == "Test Workflow"
        assert workflow.steps == 3
        assert len(workflow.step_names) == 3

    def test_get_workflow_list(self):
        """Test getting list of available workflows"""
        helper = WorkflowHelper()
        workflows_list = helper.get_workflow_list()
        assert isinstance(workflows_list, list)
        assert len(workflows_list) > 0
        assert "iterative_workflow" in workflows_list

    def test_workflow_has_required_fields(self):
        """Test that loaded workflows have required fields"""
        helper = WorkflowHelper()
        
        for key, workflow in helper.workflows.items():
            assert workflow.key == key
            assert workflow.title != ""
            assert workflow.icon != ""
            assert workflow.description != ""
            assert workflow.steps > 0
            assert len(workflow.step_names) > 0

    def test_all_core_workflows_exist(self):
        """Test that all core workflows are available"""
        helper = WorkflowHelper()
        core_workflows = [
            "create_prompt",
            "prompt_builder",
            "iterative_workflow",
            "enhancement_chain",
            "design_pipeline",
            "job_queue"
        ]
        
        for workflow in core_workflows:
            assert workflow in helper.workflows, f"Missing core workflow: {workflow}"


class TestWorkflowExamples:
    """Test workflow examples functionality"""

    def test_workflow_example_creation(self):
        """Test WorkflowExample dataclass creation"""
        example = WorkflowExample(
            workflow_key="test_workflow",
            title="Example 1",
            task="Test task",
            why="For testing",
            use_case="Testing",
            agents="Claude, GPT-4"
        )
        assert example.workflow_key == "test_workflow"
        assert example.title == "Example 1"
        assert example.agents is not None

    def test_examples_loaded_for_workflows(self):
        """Test that examples are loaded for workflows"""
        helper = WorkflowHelper()
        
        # Check that examples exist for core workflows
        for workflow_key in ["iterative_workflow", "enhancement_chain"]:
            assert workflow_key in helper.examples
            assert len(helper.examples[workflow_key]) > 0

    def test_examples_have_required_fields(self):
        """Test that examples have required fields"""
        helper = WorkflowHelper()
        
        for workflow_key, examples_list in helper.examples.items():
            for example in examples_list:
                assert example.workflow_key == workflow_key
                assert example.title != ""
                assert example.task != ""
                assert example.why != ""
                assert example.use_case != ""

    def test_has_examples_method(self):
        """Test has_examples method"""
        helper = WorkflowHelper()
        
        assert helper.has_examples("iterative_workflow")
        assert not helper.has_examples("nonexistent_workflow")


class TestWorkflowHelperAvailability:
    """Test workflow help availability checking"""

    def test_has_workflow_help_valid(self):
        """Test checking help availability for valid workflows"""
        helper = WorkflowHelper()
        
        assert helper.has_workflow_help("iterative_workflow")
        assert helper.has_workflow_help("enhancement_chain")
        assert helper.has_workflow_help("design_pipeline")

    def test_has_workflow_help_invalid(self):
        """Test checking help availability for invalid workflows"""
        helper = WorkflowHelper()
        
        assert not helper.has_workflow_help("nonexistent_workflow")

    def test_get_workflow_list_complete(self):
        """Test that workflow list is complete and accurate"""
        helper = WorkflowHelper()
        workflows_list = helper.get_workflow_list()
        
        # Should have at least 6 core workflows
        assert len(workflows_list) >= 6
        
        # Check all workflows are unique
        assert len(workflows_list) == len(set(workflows_list))


class TestWorkflowHelperValidation:
    """Test workflow helper validation"""

    def test_validate_configuration_success(self):
        """Test successful configuration validation"""
        helper = WorkflowHelper()
        validation = helper.validate_configuration()
        
        assert validation["workflows_loaded"] is True
        assert validation["examples_loaded"] is True
        assert validation["workflows_count"] > 0
        assert validation["examples_count"] > 0

    def test_validate_configuration_returns_dict(self):
        """Test that validation returns expected dictionary structure"""
        helper = WorkflowHelper()
        validation = helper.validate_configuration()
        
        expected_keys = {
            "workflows_loaded",
            "examples_loaded",
            "workflows_count",
            "examples_count",
            "yaml_available",
            "questionary_available",
            "config_directory",
            "config_directory_exists"
        }
        assert all(key in validation for key in expected_keys)

    def test_workflows_have_valid_step_count(self):
        """Test that workflows have valid step counts"""
        helper = WorkflowHelper()
        
        for workflow in helper.workflows.values():
            assert workflow.steps > 0
            assert len(workflow.step_names) == workflow.steps


class TestWorkflowHelperGracefulFailure:
    """Test workflow helper graceful failure handling"""

    def test_invalid_config_dir_graceful(self):
        """Test that invalid config directory doesn't crash"""
        with tempfile.TemporaryDirectory() as tmpdir:
            helper = WorkflowHelper(config_dir=tmpdir)
            # Should not raise exception, workflows will be empty
            assert len(helper.workflows) == 0

    def test_missing_yaml_file_graceful(self):
        """Test that missing YAML files are handled gracefully"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create empty directory without YAML files
            helper = WorkflowHelper(config_dir=tmpdir)
            validation = helper.validate_configuration()
            assert validation["workflows_loaded"] is False

    @patch('startd8.tui_workflow_help.HAS_YAML', False)
    def test_missing_yaml_library_graceful(self, mock_has_yaml):
        """Test graceful handling when YAML library is not available"""
        helper = WorkflowHelper()
        # Should not crash, will fail gracefully
        assert helper.workflows is not None


class TestWorkflowHelperMethods:
    """Test public methods of WorkflowHelper"""

    def test_show_workflow_intro_valid(self):
        """Test showing intro for valid workflow"""
        helper = WorkflowHelper()
        
        with patch.object(helper.console, 'print'):
            # Should not raise exception
            helper.show_workflow_intro("iterative_workflow")

    def test_show_workflow_intro_invalid(self):
        """Test showing intro for invalid workflow"""
        helper = WorkflowHelper()
        
        with patch.object(helper.console, 'print'):
            # Should handle gracefully
            helper.show_workflow_intro("nonexistent_workflow")

    def test_show_step_guidance_valid(self):
        """Test showing step guidance"""
        helper = WorkflowHelper()
        
        with patch.object(helper.console, 'print'):
            # Should not raise exception
            helper.show_step_guidance(
                "iterative_workflow",
                1,
                "Describe your task"
            )

    def test_show_step_guidance_invalid_step(self):
        """Test showing step guidance with invalid step number"""
        helper = WorkflowHelper()
        
        with patch.object(helper.console, 'print'):
            # Should handle gracefully
            helper.show_step_guidance(
                "iterative_workflow",
                999,
                "Invalid step"
            )

    def test_show_workflow_examples_valid(self):
        """Test showing examples for valid workflow"""
        helper = WorkflowHelper()
        
        with patch.object(helper.console, 'print'):
            with patch('startd8.tui_workflow_help.questionary'):
                # Should not raise exception
                helper.show_workflow_examples("iterative_workflow")

    def test_show_workflow_examples_invalid(self):
        """Test showing examples for invalid workflow"""
        helper = WorkflowHelper()
        
        with patch.object(helper.console, 'print'):
            # Should handle gracefully
            helper.show_workflow_examples("nonexistent_workflow")


class TestWorkflowHelperContentStructure:
    """Test the structure and content of workflows"""

    def test_all_workflows_have_required_fields(self):
        """Test that all workflows have required fields"""
        helper = WorkflowHelper()
        
        for key, workflow in helper.workflows.items():
            assert workflow.key == key
            assert workflow.title != ""
            assert workflow.icon != ""
            assert workflow.description != ""
            assert workflow.what_it_does != ""
            assert workflow.how_it_works != ""
            assert workflow.use_cases != ""
            assert workflow.requirements != ""
            assert workflow.tips != ""
            assert workflow.steps > 0

    def test_step_names_match_step_count(self):
        """Test that step names count matches steps count"""
        helper = WorkflowHelper()
        
        for workflow in helper.workflows.values():
            assert len(workflow.step_names) == workflow.steps

    def test_workflow_icons_are_valid(self):
        """Test that workflow icons are present"""
        helper = WorkflowHelper()
        
        for workflow in helper.workflows.values():
            # Icons should be emoji or symbols
            assert len(workflow.icon) > 0
            assert workflow.icon.strip() != ""


class TestWorkflowHelperIntegration:
    """Integration tests for the workflow helper"""

    def test_complete_workflow_help_workflow(self):
        """Test complete workflow help workflow"""
        helper = WorkflowHelper()
        
        # Validate configuration
        validation = helper.validate_configuration()
        assert validation["workflows_loaded"]
        assert validation["examples_loaded"]
        
        # Check workflow availability
        workflows = helper.get_workflow_list()
        assert len(workflows) > 0
        
        # Check workflow help is available
        assert helper.has_workflow_help("iterative_workflow")
        
        # Check examples are available
        assert helper.has_examples("iterative_workflow")

    def test_all_workflows_have_consistency(self):
        """Test that all workflows are consistent"""
        helper = WorkflowHelper()
        
        for workflow_key, workflow in helper.workflows.items():
            # Check step names match step count
            assert len(workflow.step_names) == workflow.steps
            
            # Check all required text fields are non-empty
            assert workflow.what_it_does.strip() != ""
            assert workflow.how_it_works.strip() != ""
            assert workflow.use_cases.strip() != ""
            assert workflow.requirements.strip() != ""
            assert workflow.tips.strip() != ""

    def test_examples_reference_existing_workflows(self):
        """Test that examples reference only existing workflows"""
        helper = WorkflowHelper()
        
        for workflow_key, examples_list in helper.examples.items():
            assert workflow_key in helper.workflows, \
                f"Examples for non-existent workflow: {workflow_key}"
            
            for example in examples_list:
                assert example.workflow_key == workflow_key


class TestWorkflowHelperWithoutYAML:
    """Test workflow helper behavior without YAML"""

    def test_graceful_failure_without_yaml(self):
        """Test system gracefully fails without YAML"""
        with patch('startd8.tui_workflow_help.HAS_YAML', False):
            helper = WorkflowHelper()
            # Should not crash
            assert helper.workflows is not None
            assert isinstance(helper.workflows, dict)
