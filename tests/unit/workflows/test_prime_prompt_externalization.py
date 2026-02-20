"""Tests for Prime Contractor Prompt Externalization (REQ-PPE-001 through REQ-PPE-006).

Validates:
- YAML prompt loading and parsing
- Backward compatibility of module-level constants
- Structured context formatting (IMP-P1)
- Requirements text passthrough (IMP-P2)
- Critical parameter elevation (IMP-P3)
- Protocol-aware spec guidance (IMP-P4)
- Constraint categorization (IMP-P5)
- Spec-to-draft validation (IMP-P6)
- Shared prompt utilities (REQ-PPE-005, REQ-PPE-006)
"""

import json

import pytest


# =========================================================================
# REQ-PPE-001: YAML Prompt Storage
# =========================================================================


class TestYAMLPromptLoading:
    """Verify YAML files are parseable and contain expected prompts."""

    def test_lead_contractor_yaml_all_prompts_parseable(self):
        """Test 1: Load lead_contractor.yaml — all 6 prompts parseable."""
        from startd8.workflows.builtin.prompts import get_template

        expected_prompts = [
            "spec", "draft", "single_file_output",
            "multi_file_output", "review", "integration",
        ]
        for name in expected_prompts:
            template = get_template("lead_contractor", name)
            assert isinstance(template, str), f"Prompt '{name}' should be a string"
            assert len(template) > 10, f"Prompt '{name}' should have content"

    def test_prime_context_yaml_all_prompts_parseable(self):
        """Test 2: Load prime_context.yaml — all 5+ prompts parseable."""
        from startd8.workflows.builtin.prompts import get_template

        expected_prompts = [
            "output_constraint", "prior_error_feedback", "file_manifest",
            "multi_file_retry", "role_hints_init", "role_hints_module",
        ]
        for name in expected_prompts:
            template = get_template("prime_context", name)
            assert isinstance(template, str), f"Prompt '{name}' should be a string"
            assert len(template) > 5, f"Prompt '{name}' should have content"


# =========================================================================
# REQ-PPE-002: Loader Module
# =========================================================================


class TestLoaderModule:
    """Verify loader API works correctly."""

    def test_get_template_returns_string_with_placeholders(self):
        """Test 3: get_template returns string with {task_description}."""
        from startd8.workflows.builtin.prompts import get_template

        spec = get_template("lead_contractor", "spec")
        assert "{task_description}" in spec
        assert "{domain_constraints}" in spec

    def test_format_prompt_fills_placeholders(self):
        """Test 4: format_prompt fills placeholders correctly."""
        from startd8.workflows.builtin.prompts import format_prompt

        result = format_prompt(
            "prime_context", "prior_error_feedback",
            prior_error="SyntaxError on line 42",
        )
        assert "SyntaxError on line 42" in result
        assert "{prior_error}" not in result

    def test_missing_yaml_raises_file_not_found(self):
        """Test 5: Missing YAML file raises FileNotFoundError."""
        from startd8.workflows.builtin.prompts import get_template

        with pytest.raises(FileNotFoundError):
            get_template("nonexistent_file", "spec")

    def test_missing_prompt_name_raises_key_error(self):
        """Test 6: Missing prompt name raises KeyError."""
        from startd8.workflows.builtin.prompts import get_template

        with pytest.raises(KeyError):
            get_template("lead_contractor", "nonexistent_prompt")


# =========================================================================
# REQ-PPE-004: Backward Compatibility
# =========================================================================


class TestBackwardCompatibility:
    """Verify module-level constants match YAML-loaded values."""

    def test_spec_prompt_constant_matches_yaml(self):
        """Test 7: SPEC_PROMPT_TEMPLATE constant matches YAML-loaded value."""
        from startd8.workflows.builtin.lead_contractor_workflow import (
            SPEC_PROMPT_TEMPLATE,
        )
        from startd8.workflows.builtin.prompts import get_template

        assert SPEC_PROMPT_TEMPLATE == get_template("lead_contractor", "spec")

    def test_build_output_format_single_file(self):
        """Test 8a: _build_output_format() returns single-file format."""
        from startd8.workflows.builtin.lead_contractor_workflow import (
            SINGLE_FILE_OUTPUT_FORMAT,
            _build_output_format,
        )

        result = _build_output_format(None)
        assert result == SINGLE_FILE_OUTPUT_FORMAT

        result = _build_output_format(["single_file.py"])
        assert result == SINGLE_FILE_OUTPUT_FORMAT

    def test_build_output_format_multi_file(self):
        """Test 8b: _build_output_format() returns multi-file format."""
        from startd8.workflows.builtin.lead_contractor_workflow import (
            _build_output_format,
        )

        result = _build_output_format(["__init__.py", "module.py"])
        assert "__init__.py" in result
        assert "module.py" in result
        assert "VERIFICATION CHECKLIST" in result

    def test_all_six_constants_loadable(self):
        """All 6 prompt constants are importable from lead_contractor_workflow."""
        from startd8.workflows.builtin.lead_contractor_workflow import (
            DRAFT_PROMPT_TEMPLATE,
            INTEGRATION_PROMPT_TEMPLATE,
            MULTI_FILE_OUTPUT_FORMAT,
            REVIEW_PROMPT_TEMPLATE,
            SINGLE_FILE_OUTPUT_FORMAT,
            SPEC_PROMPT_TEMPLATE,
        )

        for name, const in [
            ("SPEC", SPEC_PROMPT_TEMPLATE),
            ("DRAFT", DRAFT_PROMPT_TEMPLATE),
            ("SINGLE_FILE", SINGLE_FILE_OUTPUT_FORMAT),
            ("MULTI_FILE", MULTI_FILE_OUTPUT_FORMAT),
            ("REVIEW", REVIEW_PROMPT_TEMPLATE),
            ("INTEGRATION", INTEGRATION_PROMPT_TEMPLATE),
        ]:
            assert isinstance(const, str), f"{name} should be a string"
            assert len(const) > 20, f"{name} should have content"


# =========================================================================
# IMP-P1: Structured Context in Spec Prompt
# =========================================================================


class TestStructuredContext:
    """Verify _create_spec builds structured context sections."""

    def test_spec_with_structured_context_has_sections(self, lead_workflow, mock_agent):
        """Test 9: Spec prompt with structured context has dedicated sections."""
        context = {
            "architectural_context": {"layers": ["api", "data"]},
            "plan_context": "Build the auth module",
            "project_objectives": ["Secure auth", "JWT tokens"],
            "semantic_conventions": ["Use snake_case"],
        }
        lead_workflow._create_spec(mock_agent, "Implement auth", context, None)

        prompt = mock_agent.generate.call_args[0][0]
        assert "## Project Architecture" in prompt
        assert "## Plan Context" in prompt
        assert "## Project Objectives" in prompt
        assert "## Semantic Conventions" in prompt

    def test_spec_with_empty_arch_context_omits_section(self, lead_workflow, mock_agent):
        """Test 10: Spec prompt with empty architectural_context omits section."""
        context = {"feature_name": "test"}
        lead_workflow._create_spec(mock_agent, "Simple task", context, None)

        prompt = mock_agent.generate.call_args[0][0]
        assert "## Project Architecture" not in prompt


# =========================================================================
# IMP-P2: Requirements Text Passthrough
# =========================================================================


class TestRequirementsText:
    """Verify requirements_text flows through to spec prompt."""

    def test_spec_with_requirements_text_shows_section(self, lead_workflow, mock_agent):
        """Test 11: Spec prompt with requirements_text shows Requirements section."""
        context = {
            "requirements_text": "The service MUST use port 8080 and PostgreSQL user='postgres'.",
        }
        lead_workflow._create_spec(mock_agent, "Implement service", context, None)

        prompt = mock_agent.generate.call_args[0][0]
        assert "## Requirements (verbatim" in prompt
        assert "port 8080" in prompt

    def test_spec_without_requirements_text_omits_section(self, lead_workflow, mock_agent):
        """Test 12: Spec prompt without requirements_text omits Requirements section."""
        context = {"feature_name": "test"}
        lead_workflow._create_spec(mock_agent, "Simple task", context, None)

        prompt = mock_agent.generate.call_args[0][0]
        assert "## Requirements (verbatim" not in prompt

    def test_queue_bridges_requirements_text(self):
        """Verify add_features_from_seed populates requirements_text in metadata."""
        import tempfile

        from startd8.contractors.queue import FeatureQueue

        seed = {
            "tasks": [{
                "task_id": "T-001",
                "title": "Test Task",
                "config": {
                    "task_description": "Do stuff",
                    "requirements_text": "Use PostgreSQL user='postgres'",
                    "context": {"target_files": ["app.py"]},
                },
                "depends_on": [],
            }],
        }
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump(seed, f)
            f.flush()
            queue = FeatureQueue(auto_save=False)
            specs = queue.add_features_from_seed(f.name)
            assert len(specs) == 1
            assert specs[0].metadata.get("requirements_text") == "Use PostgreSQL user='postgres'"


# =========================================================================
# IMP-P3: Critical Parameter Elevation
# =========================================================================


class TestCriticalParameters:
    """Verify critical parameters appear as dedicated section."""

    def test_critical_parameters_appear_as_section(self, lead_workflow, mock_agent):
        """Test 13: Critical parameters extracted from enrichment appear as dedicated section."""
        context = {
            "critical_parameters": [
                "user='postgres'",
                "embedding_service=GoogleGenerativeAIEmbeddings",
            ],
        }
        lead_workflow._create_spec(mock_agent, "Implement storage", context, None)

        prompt = mock_agent.generate.call_args[0][0]
        assert "## Critical Parameters" in prompt
        assert "user='postgres'" in prompt
        assert "GoogleGenerativeAIEmbeddings" in prompt

    def test_no_critical_parameters_no_section(self, lead_workflow, mock_agent):
        """Test 14: No critical parameters → no Critical Parameters section."""
        context = {"feature_name": "test"}
        lead_workflow._create_spec(mock_agent, "Simple task", context, None)

        prompt = mock_agent.generate.call_args[0][0]
        assert "## Critical Parameters" not in prompt


# =========================================================================
# IMP-P4: Protocol-Aware Spec Guidance
# =========================================================================


class TestProtocolGuidance:
    """Verify spec prompt contains protocol guidance text."""

    def test_spec_prompt_contains_protocol_guidance(self):
        """Test 15: Spec prompt contains protocol guidance text."""
        from startd8.workflows.builtin.lead_contractor_workflow import (
            SPEC_PROMPT_TEMPLATE,
        )

        assert "Protocol and Implementation Guidance" in SPEC_PROMPT_TEMPLATE
        assert "HEALTHCHECK" in SPEC_PROMPT_TEMPLATE
        assert "grpc_health_probe" in SPEC_PROMPT_TEMPLATE
        assert "transport_protocol" in SPEC_PROMPT_TEMPLATE


# =========================================================================
# IMP-P5: Constraint Categorization
# =========================================================================


class TestConstraintCategorization:
    """Verify constraints are grouped by [BINDING]/[STRUCTURAL]/[ADVISORY]."""

    def test_constraints_grouped_by_category(self, lead_workflow, mock_agent):
        """Test 16: Constraints grouped by [BINDING]/[STRUCTURAL]/[ADVISORY]."""
        context = {
            "domain_constraints": [
                "[BINDING] Only import from: os, sys",
                "[STRUCTURAL] Define utility functions before classes",
                "[ADVISORY] Prefer stdlib when sufficient",
            ],
        }
        lead_workflow._create_spec(mock_agent, "Test task", context, None)

        prompt = mock_agent.generate.call_args[0][0]
        assert "### Binding (must not violate)" in prompt
        assert "### Structural (code organization)" in prompt
        assert "### Advisory (prefer but not blocking)" in prompt

    def test_untagged_constraints_rendered_flat(self, lead_workflow, mock_agent):
        """Test 17: Untagged constraints rendered as flat list."""
        context = {
            "domain_constraints": [
                "Use Python 3.9+",
                "Follow PEP 8",
            ],
        }
        lead_workflow._create_spec(mock_agent, "Test task", context, None)

        prompt = mock_agent.generate.call_args[0][0]
        assert "- Use Python 3.9+" in prompt
        assert "- Follow PEP 8" in prompt


# =========================================================================
# IMP-P6: Spec-to-Draft Validation
# =========================================================================


class TestSpecToDraftValidation:
    """Verify missing parameters generate spec completeness warning."""

    def test_missing_parameters_generate_warning(self):
        """Test 18: Missing parameters generate spec completeness warning."""
        from startd8.contractors.prompt_utils import find_missing_parameters

        spec_text = "Implement a database connection using AlloyDB"
        resolved = [
            {"key_value": "user='postgres'"},
            {"key_value": "AlloyDB"},
        ]
        missing = find_missing_parameters(spec_text, resolved)
        assert len(missing) == 1
        assert missing[0]["key_value"] == "user='postgres'"

    def test_all_parameters_present_no_warning(self):
        """Test 19: All parameters present → no warning."""
        from startd8.contractors.prompt_utils import find_missing_parameters

        spec_text = "Use user='postgres' with AlloyDB connection"
        resolved = [
            {"key_value": "user='postgres'"},
            {"key_value": "AlloyDB"},
        ]
        missing = find_missing_parameters(spec_text, resolved)
        assert len(missing) == 0


# =========================================================================
# REQ-PPE-005: Shared format_constraints
# =========================================================================


class TestSharedFormatConstraints:
    """Verify format_constraints matches artisan behavior."""

    def test_shared_format_constraints_matches_artisan(self):
        """Test 20: Shared format_constraints matches artisan behavior."""
        from startd8.contractors.artisan_phases.prompts import format_constraints as artisan_fc
        from startd8.contractors.prompt_utils import format_constraints as shared_fc

        constraints = [
            "[BINDING] Must use Python 3.9+",
            "[STRUCTURAL] Functions before classes",
            "[ADVISORY] Prefer pathlib over os.path",
            "Generic constraint",
        ]
        # Both should produce identical output
        assert shared_fc(constraints) == artisan_fc(constraints)

    def test_format_constraints_importable_from_both(self):
        """Verify format_constraints is importable from both locations."""
        from startd8.contractors.artisan_phases.prompts import format_constraints as fc1
        from startd8.contractors.prompt_utils import format_constraints as fc2

        # They should be the same function (re-export)
        assert fc1 is fc2


# =========================================================================
# REQ-PPE-006: Shared find_missing_parameters
# =========================================================================


class TestSharedFindMissingParameters:
    """Verify find_missing_parameters detects absent keys."""

    def test_find_missing_parameters_detects_absent_keys(self):
        """Test 21: Shared find_missing_parameters detects absent keys."""
        from startd8.contractors.prompt_utils import find_missing_parameters

        text = "Connect to the database using host=localhost"
        params = [
            {"key_value": "host=localhost"},
            {"key_value": "port=5432"},
            {"key_value": ""},  # empty key_value should be skipped
        ]
        missing = find_missing_parameters(text, params)
        assert len(missing) == 1
        assert missing[0]["key_value"] == "port=5432"

    def test_find_missing_parameters_empty_list(self):
        """Empty resolved_parameters returns empty list."""
        from startd8.contractors.prompt_utils import find_missing_parameters

        missing = find_missing_parameters("some text", [])
        assert missing == []
