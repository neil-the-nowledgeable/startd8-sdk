# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""
Tests for the workflow scaffold capability.

Tests scaffold_constants, templates, WorkflowScaffolder, and CLI command.
Following SDK Leg 9 patterns for test organization.
"""

import pytest
from pathlib import Path
from typing import Generator
import tempfile
import shutil

# Test scaffold_constants
from startd8.workflows.scaffold_constants import (
    TEMPLATE_BASIC,
    TEMPLATE_PIPELINE,
    TEMPLATE_MULTI_AGENT,
    TEMPLATE_ASYNC,
    VALID_TEMPLATES,
    DEFAULT_TEMPLATE,
    TEMPLATE_DESCRIPTIONS,
    WORKFLOW_CLASS_SUFFIX,
    ERR_INVALID_TEMPLATE,
    ERR_FILE_EXISTS,
    ERR_INVALID_NAME,
)

# Test scaffold
from startd8.workflows.scaffold import (
    WorkflowScaffolder,
    ScaffoldConfig,
    ScaffoldResult,
    scaffold_workflow,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_output_dir() -> Generator[Path, None, None]:
    """Create a temporary output directory for scaffold tests.

    Following SDK Leg 9 #3: Use yield not return for temp dir fixtures.
    """
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def scaffolder() -> WorkflowScaffolder:
    """Create a WorkflowScaffolder instance."""
    return WorkflowScaffolder()


# =============================================================================
# Test scaffold_constants
# =============================================================================


class TestScaffoldConstants:
    """Test scaffold_constants module."""

    def test_valid_templates_contains_expected_types(self):
        """Test that VALID_TEMPLATES contains all expected types."""
        assert TEMPLATE_BASIC in VALID_TEMPLATES
        assert TEMPLATE_PIPELINE in VALID_TEMPLATES
        assert TEMPLATE_MULTI_AGENT in VALID_TEMPLATES
        assert TEMPLATE_ASYNC in VALID_TEMPLATES
        assert len(VALID_TEMPLATES) == 4

    def test_default_template_is_basic(self):
        """Test that default template is basic."""
        assert DEFAULT_TEMPLATE == TEMPLATE_BASIC

    def test_template_descriptions_has_all_templates(self):
        """Test that all templates have descriptions."""
        for template in VALID_TEMPLATES:
            assert template in TEMPLATE_DESCRIPTIONS
            assert len(TEMPLATE_DESCRIPTIONS[template]) > 0

    def test_workflow_class_suffix(self):
        """Test workflow class suffix."""
        assert WORKFLOW_CLASS_SUFFIX == "Workflow"

    def test_error_messages_are_formatted_strings(self):
        """Test that error messages can be formatted."""
        # These should not raise
        ERR_INVALID_TEMPLATE.format(template="foo", valid="basic, pipeline")
        ERR_FILE_EXISTS.format(path="/some/path")
        ERR_INVALID_NAME.format(name="bad name")


# =============================================================================
# Test templates module
# =============================================================================


class TestTemplatesModule:
    """Test templates module."""

    def test_jinja2_availability_check(self):
        """Test check_jinja2_available function."""
        from startd8.workflows.templates import check_jinja2_available
        # Should return True if Jinja2 is installed
        result = check_jinja2_available()
        assert isinstance(result, bool)

    @pytest.mark.skipif(
        not __import__("startd8.workflows.templates", fromlist=["check_jinja2_available"]).check_jinja2_available(),
        reason="Jinja2 not installed"
    )
    def test_template_loader_initialization(self):
        """Test TemplateLoader can be initialized."""
        from startd8.workflows.templates import TemplateLoader
        loader = TemplateLoader()
        assert loader is not None

    @pytest.mark.skipif(
        not __import__("startd8.workflows.templates", fromlist=["check_jinja2_available"]).check_jinja2_available(),
        reason="Jinja2 not installed"
    )
    def test_template_loader_list_templates(self):
        """Test TemplateLoader.list_templates returns available templates."""
        from startd8.workflows.templates import TemplateLoader
        loader = TemplateLoader()
        templates = loader.list_templates()

        assert isinstance(templates, list)
        # At least basic should be available
        assert TEMPLATE_BASIC in templates

    @pytest.mark.skipif(
        not __import__("startd8.workflows.templates", fromlist=["check_jinja2_available"]).check_jinja2_available(),
        reason="Jinja2 not installed"
    )
    def test_template_context_to_dict(self):
        """Test TemplateContext.to_dict method."""
        from startd8.workflows.templates import TemplateContext

        context = TemplateContext(
            workflow_id="my-workflow",
            module_name="my_workflow",
            class_name="MyWorkflowWorkflow",
            name="My Workflow",
            description="Test description",
            version="1.0.0",
            capabilities=["test"],
            tags=["custom"],
        )

        d = context.to_dict()
        assert d["workflow_id"] == "my-workflow"
        assert d["class_name"] == "MyWorkflowWorkflow"
        assert d["capabilities"] == ["test"]


# =============================================================================
# Test WorkflowScaffolder
# =============================================================================


class TestWorkflowScaffolder:
    """Test WorkflowScaffolder class."""

    def test_scaffolder_initialization(self, scaffolder):
        """Test WorkflowScaffolder can be initialized."""
        assert scaffolder is not None

    def test_list_templates(self, scaffolder):
        """Test list_templates returns template info."""
        templates = scaffolder.list_templates()

        assert isinstance(templates, list)
        assert len(templates) == 4

        names = [t["name"] for t in templates]
        assert TEMPLATE_BASIC in names
        assert TEMPLATE_PIPELINE in names

    def test_name_conversion_kebab_to_snake(self, scaffolder):
        """Test kebab-case to snake_case conversion."""
        result = scaffolder._to_snake_case("my-workflow")
        assert result == "my_workflow"

    def test_name_conversion_snake_to_kebab(self, scaffolder):
        """Test snake_case to kebab-case conversion."""
        result = scaffolder._to_kebab_case("my_workflow")
        assert result == "my-workflow"

    def test_name_conversion_to_pascal(self, scaffolder):
        """Test conversion to PascalCase."""
        assert scaffolder._to_pascal_case("my-workflow") == "MyWorkflow"
        assert scaffolder._to_pascal_case("my_workflow") == "MyWorkflow"
        assert scaffolder._to_pascal_case("simple") == "Simple"

    def test_name_conversion_to_display(self, scaffolder):
        """Test conversion to display name."""
        assert scaffolder._to_display_name("my-workflow") == "My Workflow"
        assert scaffolder._to_display_name("my_complex_workflow") == "My Complex Workflow"

    def test_invalid_name_raises_error(self, scaffolder):
        """Test invalid name validation."""
        with pytest.raises(ValueError):
            scaffolder._validate_name("123-invalid")  # Starts with number

        with pytest.raises(ValueError):
            scaffolder._validate_name("has spaces")  # Contains spaces

        with pytest.raises(ValueError):
            scaffolder._validate_name("special!chars")  # Contains special chars

    def test_scaffold_invalid_template(self, scaffolder, temp_output_dir):
        """Test scaffold with invalid template returns error."""
        config = ScaffoldConfig(
            name="test-workflow",
            template="invalid-template",
            output_dir=temp_output_dir,
        )

        result = scaffolder.scaffold(config)

        assert not result.success
        assert "Invalid template type" in result.error

    def test_scaffold_invalid_name(self, scaffolder, temp_output_dir):
        """Test scaffold with invalid name returns error."""
        config = ScaffoldConfig(
            name="123-bad-name",
            template=TEMPLATE_BASIC,
            output_dir=temp_output_dir,
        )

        result = scaffolder.scaffold(config)

        assert not result.success
        assert "Invalid workflow name" in result.error

    def test_scaffold_nonexistent_output_dir(self, scaffolder):
        """Test scaffold with non-existent output dir returns error."""
        config = ScaffoldConfig(
            name="test-workflow",
            template=TEMPLATE_BASIC,
            output_dir=Path("/nonexistent/directory"),
        )

        result = scaffolder.scaffold(config)

        assert not result.success
        assert "does not exist" in result.error

    @pytest.mark.skipif(
        not __import__("startd8.workflows.templates", fromlist=["check_jinja2_available"]).check_jinja2_available(),
        reason="Jinja2 not installed"
    )
    def test_scaffold_basic_template(self, scaffolder, temp_output_dir):
        """Test scaffold with basic template creates file."""
        config = ScaffoldConfig(
            name="test-workflow",
            template=TEMPLATE_BASIC,
            output_dir=temp_output_dir,
            description="A test workflow",
        )

        result = scaffolder.scaffold(config)

        assert result.success
        assert result.file_path is not None
        assert result.file_path.exists()
        assert result.workflow_id == "test-workflow"
        assert result.class_name == "TestWorkflowWorkflow"

        # Verify file content
        content = result.file_path.read_text()
        assert "class TestWorkflowWorkflow" in content
        assert 'workflow_id="test-workflow"' in content
        assert "A test workflow" in content

    @pytest.mark.skipif(
        not __import__("startd8.workflows.templates", fromlist=["check_jinja2_available"]).check_jinja2_available(),
        reason="Jinja2 not installed"
    )
    def test_scaffold_pipeline_template(self, scaffolder, temp_output_dir):
        """Test scaffold with pipeline template creates file."""
        config = ScaffoldConfig(
            name="my-pipeline",
            template=TEMPLATE_PIPELINE,
            output_dir=temp_output_dir,
        )

        result = scaffolder.scaffold(config)

        assert result.success
        content = result.file_path.read_text()
        assert "class MyPipelineWorkflow" in content
        assert "min_agents=2" in content  # Pipeline requires 2+ agents

    @pytest.mark.skipif(
        not __import__("startd8.workflows.templates", fromlist=["check_jinja2_available"]).check_jinja2_available(),
        reason="Jinja2 not installed"
    )
    def test_scaffold_multi_agent_template(self, scaffolder, temp_output_dir):
        """Test scaffold with multi_agent template creates file."""
        config = ScaffoldConfig(
            name="parallel-work",
            template=TEMPLATE_MULTI_AGENT,
            output_dir=temp_output_dir,
        )

        result = scaffolder.scaffold(config)

        assert result.success
        content = result.file_path.read_text()
        assert "class ParallelWorkWorkflow" in content
        assert "ThreadPoolExecutor" in content  # Uses parallel execution

    @pytest.mark.skipif(
        not __import__("startd8.workflows.templates", fromlist=["check_jinja2_available"]).check_jinja2_available(),
        reason="Jinja2 not installed"
    )
    def test_scaffold_async_template(self, scaffolder, temp_output_dir):
        """Test scaffold with async template creates file."""
        config = ScaffoldConfig(
            name="async-flow",
            template=TEMPLATE_ASYNC,
            output_dir=temp_output_dir,
        )

        result = scaffolder.scaffold(config)

        assert result.success
        content = result.file_path.read_text()
        assert "class AsyncFlowWorkflow" in content
        assert "async def _aexecute" in content  # Uses async execution

    @pytest.mark.skipif(
        not __import__("startd8.workflows.templates", fromlist=["check_jinja2_available"]).check_jinja2_available(),
        reason="Jinja2 not installed"
    )
    def test_scaffold_file_exists_without_force(self, scaffolder, temp_output_dir):
        """Test scaffold fails if file exists and force=False."""
        config = ScaffoldConfig(
            name="existing",
            template=TEMPLATE_BASIC,
            output_dir=temp_output_dir,
        )

        # First scaffold
        result1 = scaffolder.scaffold(config)
        assert result1.success

        # Second scaffold without force
        result2 = scaffolder.scaffold(config)
        assert not result2.success
        assert "already exists" in result2.error

    @pytest.mark.skipif(
        not __import__("startd8.workflows.templates", fromlist=["check_jinja2_available"]).check_jinja2_available(),
        reason="Jinja2 not installed"
    )
    def test_scaffold_file_exists_with_force(self, scaffolder, temp_output_dir):
        """Test scaffold succeeds if file exists and force=True."""
        config = ScaffoldConfig(
            name="overwrite",
            template=TEMPLATE_BASIC,
            output_dir=temp_output_dir,
            description="Original",
        )

        # First scaffold
        result1 = scaffolder.scaffold(config)
        assert result1.success

        # Second scaffold with force
        config.force = True
        config.description = "Updated"
        result2 = scaffolder.scaffold(config)
        assert result2.success

        # Verify content was updated
        content = result2.file_path.read_text()
        assert "Updated" in content


# =============================================================================
# Test scaffold_workflow convenience function
# =============================================================================


class TestScaffoldWorkflowFunction:
    """Test scaffold_workflow convenience function."""

    @pytest.mark.skipif(
        not __import__("startd8.workflows.templates", fromlist=["check_jinja2_available"]).check_jinja2_available(),
        reason="Jinja2 not installed"
    )
    def test_scaffold_workflow_basic(self, temp_output_dir):
        """Test scaffold_workflow convenience function."""
        result = scaffold_workflow(
            name="quick-test",
            output_dir=temp_output_dir,
            description="Quick test workflow",
        )

        assert result.success
        assert result.file_path.exists()

    @pytest.mark.skipif(
        not __import__("startd8.workflows.templates", fromlist=["check_jinja2_available"]).check_jinja2_available(),
        reason="Jinja2 not installed"
    )
    def test_scaffold_workflow_with_template(self, temp_output_dir):
        """Test scaffold_workflow with template parameter."""
        result = scaffold_workflow(
            name="my-pipe",
            template=TEMPLATE_PIPELINE,
            output_dir=temp_output_dir,
        )

        assert result.success
        content = result.file_path.read_text()
        assert "class MyPipeWorkflow" in content


# =============================================================================
# Test ScaffoldResult
# =============================================================================


class TestScaffoldResult:
    """Test ScaffoldResult dataclass."""

    def test_ok_factory(self, temp_output_dir):
        """Test ScaffoldResult.ok factory method."""
        path = temp_output_dir / "test.py"
        result = ScaffoldResult.ok(path, "test-id", "TestClass")

        assert result.success
        assert result.file_path == path
        assert result.workflow_id == "test-id"
        assert result.class_name == "TestClass"
        assert result.error is None

    def test_fail_factory(self):
        """Test ScaffoldResult.fail factory method."""
        result = ScaffoldResult.fail("Something went wrong")

        assert not result.success
        assert result.error == "Something went wrong"
        assert result.file_path is None


# =============================================================================
# Test ScaffoldConfig
# =============================================================================


class TestScaffoldConfig:
    """Test ScaffoldConfig dataclass."""

    def test_config_defaults(self):
        """Test ScaffoldConfig has sensible defaults."""
        config = ScaffoldConfig(name="test")

        assert config.name == "test"
        assert config.template == DEFAULT_TEMPLATE
        assert config.output_dir is None
        assert config.force is False
        assert isinstance(config.capabilities, list)
        assert isinstance(config.tags, list)

    def test_config_with_all_options(self, temp_output_dir):
        """Test ScaffoldConfig with all options."""
        config = ScaffoldConfig(
            name="full-config",
            template=TEMPLATE_PIPELINE,
            output_dir=temp_output_dir,
            description="Full description",
            version="2.0.0",
            capabilities=["cap1", "cap2"],
            tags=["tag1"],
            force=True,
        )

        assert config.name == "full-config"
        assert config.template == TEMPLATE_PIPELINE
        assert config.output_dir == temp_output_dir
        assert config.description == "Full description"
        assert config.version == "2.0.0"
        assert config.capabilities == ["cap1", "cap2"]
        assert config.tags == ["tag1"]
        assert config.force is True
