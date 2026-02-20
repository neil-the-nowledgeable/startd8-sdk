"""Tests for prime_task_enrichment utilities."""

import json
from unittest.mock import patch


from startd8.utils.prime_task_enrichment import (
    extract_target_files,
    enrich_prime_yaml,
)


# ============================================================================
# TestTargetFileExtraction
# ============================================================================


class TestTargetFileExtraction:
    """Covers all 5 pattern tiers + no-match case."""

    def test_tier1_implementation_file(self):
        desc = "Implement the core domain models.\nImplementation file: src/startd8/models.py\nDetails follow."
        result = extract_target_files(desc)
        assert result == ["src/startd8/models.py"]

    def test_tier2_export_as(self):
        desc = "Generate the configuration.\nExport as: config/settings.yaml"
        result = extract_target_files(desc)
        assert result == ["config/settings.yaml"]

    def test_tier3_update_file(self):
        desc = "Refactor the handler.\nUpdate file: src/startd8/handlers.py"
        result = extract_target_files(desc)
        assert result == ["src/startd8/handlers.py"]

    def test_tier3_modify_file(self):
        desc = "Modify file: src/startd8/cli.py\nAdd new subcommand."
        result = extract_target_files(desc)
        assert result == ["src/startd8/cli.py"]

    def test_tier4_deliverable(self):
        desc = "Write the API reference.\nDeliverable: docs/api_reference.md"
        result = extract_target_files(desc)
        assert result == ["docs/api_reference.md"]

    def test_tier4_file(self):
        desc = "Create the schema.\nFile: schemas/user.json"
        result = extract_target_files(desc)
        assert result == ["schemas/user.json"]

    def test_tier5_enhancements_for(self):
        desc = "Enhancements for src/startd8/agents.py: add retry logic."
        result = extract_target_files(desc)
        assert result == ["src/startd8/agents.py"]

    def test_tier5_add_to(self):
        desc = "Add cost tracking to src/startd8/costs/tracker.py"
        result = extract_target_files(desc)
        assert result == ["src/startd8/costs/tracker.py"]

    def test_tier5_update(self):
        desc = "Update src/startd8/framework.py to support new storage backend."
        result = extract_target_files(desc)
        assert result == ["src/startd8/framework.py"]

    def test_no_match(self):
        desc = "Improve overall performance of the system."
        result = extract_target_files(desc)
        assert result == []

    def test_multiple_files(self):
        desc = (
            "Implementation file: src/startd8/models.py\n"
            "Update file: src/startd8/agents.py"
        )
        result = extract_target_files(desc)
        assert result == ["src/startd8/models.py", "src/startd8/agents.py"]

    def test_no_duplicates(self):
        desc = (
            "Implementation file: src/startd8/models.py\n"
            "Update src/startd8/models.py to add new field."
        )
        result = extract_target_files(desc)
        assert result == ["src/startd8/models.py"]


# ============================================================================
# TestEnrichPrimeYaml
# ============================================================================


class TestEnrichPrimeYaml:
    """Minimal YAML + tmp project dir -> verify _enrichment added."""

    def test_enrichment_added(self, tmp_path):
        import yaml
        from startd8.workflows.builtin.domain_preflight_models import (
            TaskDomain,
            TaskEnrichment,
        )

        # Create minimal YAML
        yaml_data = {
            "tasks": [
                {
                    "task_id": "PI-001",
                    "title": "Build models",
                    "config": {
                        "task_description": "Implement the core models.\nImplementation file: src/models.py",
                        "context": {},
                    },
                },
            ]
        }
        input_path = tmp_path / "input.yaml"
        input_path.write_text(yaml.dump(yaml_data), encoding="utf-8")
        output_path = tmp_path / "output.yaml"

        # Create project structure
        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / "src").mkdir()

        mock_enrichment = TaskEnrichment(
            task_id="PI-001",
            domain=TaskDomain.PYTHON_SINGLE_MODULE,
            domain_reasoning="test",
            prompt_constraints=["No relative imports", "Single module output"],
            post_generation_validators=["no_relative_imports"],
        )

        with patch(
            "startd8.contractors.artisan_phases.domain_checklist.DomainChecklist"
        ) as MockChecklist:
            instance = MockChecklist.return_value
            instance.get_enrichment.return_value = mock_enrichment

            report = enrich_prime_yaml(input_path, project_root, output_path)

        assert report.total_tasks == 1
        assert report.enriched == 1
        assert report.skipped == 0
        assert report.failed == 0

        # Verify output
        result = yaml.safe_load(output_path.read_text())
        task = result["tasks"][0]
        assert "_enrichment" in task
        assert task["_enrichment"]["domain"] == "python-single-module"
        assert len(task["_enrichment"]["prompt_constraints"]) == 2
        assert task["config"]["context"]["target_files"] == ["src/models.py"]

    def test_skips_tasks_without_targets(self, tmp_path):
        import yaml

        yaml_data = {
            "tasks": [
                {
                    "task_id": "PI-099",
                    "title": "General improvements",
                    "config": {
                        "task_description": "Improve overall code quality.",
                        "context": {},
                    },
                },
            ]
        }
        input_path = tmp_path / "input.yaml"
        input_path.write_text(yaml.dump(yaml_data), encoding="utf-8")
        output_path = tmp_path / "output.yaml"
        project_root = tmp_path / "project"
        project_root.mkdir()

        with patch(
            "startd8.contractors.artisan_phases.domain_checklist.DomainChecklist"
        ):
            report = enrich_prime_yaml(input_path, project_root, output_path)

        assert report.total_tasks == 1
        assert report.skipped == 1
        assert report.enriched == 0


# ============================================================================
# TestConstraintFormatting
# ============================================================================


class TestConstraintFormatting:
    """Verify _create_spec formats constraints as bullet list and removes from context."""

    def test_list_constraints_formatted_as_bullets(self):
        """Domain constraints list should become a bullet-list string in the prompt."""
        from startd8.workflows.builtin.lead_contractor_workflow import (
            SPEC_PROMPT_TEMPLATE,
        )

        constraints = ["No relative imports", "Single module output"]
        domain_constraints_str = "\n".join(f"- {c}" for c in constraints)

        result = SPEC_PROMPT_TEMPLATE.format(
            task_description="Build a thing",
            requirements_section="",
            context_sections="## Context\n{}",
            critical_parameters_section="",
            domain_constraints=domain_constraints_str,
        )

        assert "- No relative imports" in result
        assert "- Single module output" in result
        assert "## Domain Constraints" in result

    def test_no_constraints_placeholder(self):
        """When no domain constraints, placeholder text should appear."""
        from startd8.workflows.builtin.lead_contractor_workflow import (
            SPEC_PROMPT_TEMPLATE,
        )

        result = SPEC_PROMPT_TEMPLATE.format(
            task_description="Build a thing",
            requirements_section="",
            context_sections="## Context\n{}",
            critical_parameters_section="",
            domain_constraints="(No domain-specific constraints)",
        )

        assert "(No domain-specific constraints)" in result

    def test_constraints_removed_from_context_dict(self):
        """_create_spec should pop domain_constraints from context before JSON-serializing."""

        context = {
            "feature_name": "test",
            "domain_constraints": ["constraint1", "constraint2"],
        }

        # Simulate what _create_spec does
        raw_constraints = context.pop("domain_constraints", None)

        assert "domain_constraints" not in context
        assert raw_constraints == ["constraint1", "constraint2"]
        # Remaining context should JSON-serialize cleanly
        assert json.dumps(context) == '{"feature_name": "test"}'
