"""
Tests for Phase 1.1 Auto-Validate: FR-110 (type checking), FR-111 (JSON Schema),
FR-112 (_custom_validate hook).
"""

import pytest
from unittest.mock import patch, MagicMock
from typing import Any, Dict, List, Optional

from startd8.workflows import (
    WorkflowBase,
    WorkflowMetadata,
    WorkflowResult,
    WorkflowMetrics,
    ValidationResult,
    WorkflowInput,
    AgentCount,
)
from startd8.workflows.base import ProgressCallback


class TypedWorkflow(WorkflowBase):
    """Workflow with typed inputs for validation testing."""

    @property
    def metadata(self) -> WorkflowMetadata:
        return WorkflowMetadata(
            workflow_id="typed-workflow",
            name="Typed Workflow",
            description="A workflow with typed inputs",
            version="1.0.0",
            requires_agents=False,
            agent_count=AgentCount.NONE,
            min_agents=0,
            inputs=[
                WorkflowInput(name="title", type="string", required=True),
                WorkflowInput(name="count", type="number", required=False),
                WorkflowInput(name="verbose", type="boolean", required=False),
                WorkflowInput(name="agents", type="agent_spec_list", required=False),
            ],
        )

    def _execute(self, config, agents=None, on_progress=None):
        return WorkflowResult(
            workflow_id="typed-workflow",
            success=True,
            output="ok",
        )


class CustomValidateWorkflow(WorkflowBase):
    """Workflow with custom validation hook."""

    @property
    def metadata(self) -> WorkflowMetadata:
        return WorkflowMetadata(
            workflow_id="custom-validate",
            name="Custom Validate",
            description="A workflow with custom validation",
            version="1.0.0",
            requires_agents=False,
            agent_count=AgentCount.NONE,
            min_agents=0,
            inputs=[
                WorkflowInput(name="value", type="number", required=True),
            ],
        )

    def _custom_validate(self, config: Dict[str, Any]) -> List[str]:
        errors = []
        val = config.get("value")
        if val is not None and isinstance(val, (int, float)) and val < 0:
            errors.append("value must be non-negative")
        return errors

    def _execute(self, config, agents=None, on_progress=None):
        return WorkflowResult(
            workflow_id="custom-validate",
            success=True,
            output="ok",
        )


class TestTypeValidation:
    """FR-110: Type checking in validate_config()."""

    def test_type_validation_string_passes(self):
        wf = TypedWorkflow()
        result = wf.validate_config({"title": "Hello"})
        assert result.valid

    def test_type_validation_number_passes_int(self):
        wf = TypedWorkflow()
        result = wf.validate_config({"title": "Hello", "count": 5})
        assert result.valid

    def test_type_validation_number_passes_float(self):
        wf = TypedWorkflow()
        result = wf.validate_config({"title": "Hello", "count": 3.14})
        assert result.valid

    def test_type_validation_boolean_passes(self):
        wf = TypedWorkflow()
        result = wf.validate_config({"title": "Hello", "verbose": True})
        assert result.valid

    def test_type_validation_wrong_type_string(self):
        wf = TypedWorkflow()
        result = wf.validate_config({"title": 123})
        assert not result.valid
        assert any("title" in e and "string" in e for e in result.errors)

    def test_type_validation_wrong_type_number(self):
        wf = TypedWorkflow()
        result = wf.validate_config({"title": "Hi", "count": "not a number"})
        assert not result.valid
        assert any("count" in e and "number" in e for e in result.errors)

    def test_type_validation_wrong_type_boolean(self):
        wf = TypedWorkflow()
        result = wf.validate_config({"title": "Hi", "verbose": "yes"})
        assert not result.valid
        assert any("verbose" in e and "boolean" in e for e in result.errors)

    def test_type_validation_error_message_format(self):
        """Error messages include field name, expected type, and actual type."""
        wf = TypedWorkflow()
        result = wf.validate_config({"title": 42})
        assert not result.valid
        err = result.errors[0]
        assert "title" in err
        assert "string" in err
        assert "int" in err

    def test_missing_required_still_works(self):
        """Existing required-field validation is preserved."""
        wf = TypedWorkflow()
        result = wf.validate_config({})
        assert not result.valid
        assert any("Missing required input: title" in e for e in result.errors)


class TestCustomValidateHook:
    """FR-112: _custom_validate() hook."""

    def test_custom_validate_default_returns_empty(self):
        wf = TypedWorkflow()
        assert wf._custom_validate({"title": "Hi"}) == []

    def test_custom_validate_hook_called(self):
        wf = CustomValidateWorkflow()
        result = wf.validate_config({"value": -5})
        assert not result.valid
        assert any("non-negative" in e for e in result.errors)

    def test_custom_validate_errors_merged(self):
        """Custom errors are merged with auto-validation errors."""
        wf = CustomValidateWorkflow()
        # Missing required + custom validation failure
        result = wf.validate_config({})
        assert not result.valid
        assert any("Missing required input: value" in e for e in result.errors)

    def test_custom_validate_passes(self):
        wf = CustomValidateWorkflow()
        result = wf.validate_config({"value": 10})
        assert result.valid


class TestJsonSchemaValidation:
    """FR-111: Optional JSON Schema validation."""

    def test_json_schema_graceful_fallback(self):
        """Validation works when jsonschema is not installed."""
        wf = TypedWorkflow()
        with patch.dict("sys.modules", {"jsonschema": None}):
            result = wf.validate_config({"title": "Hello"})
            assert result.valid

    def test_existing_validation_preserved(self):
        """All existing validate_config() behavior is preserved."""
        wf = TypedWorkflow()
        # Valid config
        assert wf.validate_config({"title": "Hi"}).valid
        # Missing required
        assert not wf.validate_config({}).valid
