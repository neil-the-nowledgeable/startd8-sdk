"""Tests for plan section extractor (REQ-SU-500)."""

from startd8.seeds.plan_section_extractor import extract_plan_sections


class TestExtractPlanSections:
    """Plan section extraction tests."""

    def test_extract_risk_h2_heading(self):
        plan = "## Overview\nSome text\n## Risk Register\n| Risk | Mitigation |\n|---|---|\n| Data loss | Backups |\n## Next\n"
        result = extract_plan_sections(plan)
        assert result["plan_risk_register"] is not None
        assert len(result["plan_risk_register"]) == 1
        assert result["plan_risk_register"][0]["risk"] == "Data loss"
        assert result["plan_risk_register"][0]["mitigation"] == "Backups"

    def test_extract_risk_h3_heading(self):
        plan = "### Risks\n- Server crash — restart automatically\n"
        result = extract_plan_sections(plan)
        assert result["plan_risk_register"] is not None
        assert len(result["plan_risk_register"]) >= 1

    def test_extract_verification_section(self):
        plan = "## Verification\n- All tests pass\n- Coverage > 80%\n## End\n"
        result = extract_plan_sections(plan)
        assert result["plan_verification_criteria"] is not None
        assert len(result["plan_verification_criteria"]) == 2
        assert "All tests pass" in result["plan_verification_criteria"][0]

    def test_extract_acceptance_criteria_alias(self):
        plan = "## Acceptance Criteria\n1. Login works\n2. Logout works\n"
        result = extract_plan_sections(plan)
        assert result["plan_verification_criteria"] is not None
        assert len(result["plan_verification_criteria"]) == 2

    def test_extract_test_plan_alias(self):
        plan = "## Test Plan\n- Unit tests for auth module\n"
        result = extract_plan_sections(plan)
        assert result["plan_verification_criteria"] is not None

    def test_no_matching_sections(self):
        plan = "## Overview\nJust an overview\n## Implementation\nSome code\n"
        result = extract_plan_sections(plan)
        assert result["plan_risk_register"] is None
        assert result["plan_verification_criteria"] is None

    def test_section_stops_at_next_header(self):
        plan = "## Risk Register\n- Data loss\n## Architecture\nArch details\n"
        result = extract_plan_sections(plan)
        risks = result["plan_risk_register"]
        assert risks is not None
        # Should not include "Arch details"
        assert all("Arch details" not in r["risk"] for r in risks)

    def test_risk_table_format(self):
        plan = (
            "## Risks\n"
            "| Risk | Mitigation |\n"
            "|------|------------|\n"
            "| Timeout | Retry with backoff |\n"
            "| OOM | Increase limits |\n"
        )
        result = extract_plan_sections(plan)
        assert result["plan_risk_register"] is not None
        assert len(result["plan_risk_register"]) == 2

    def test_risk_bullet_format(self):
        plan = "## Risks\n- API rate limiting\n- Network partition\n"
        result = extract_plan_sections(plan)
        assert result["plan_risk_register"] is not None
        assert len(result["plan_risk_register"]) == 2

    def test_empty_plan(self):
        result = extract_plan_sections("")
        assert result["plan_risk_register"] is None
        assert result["plan_verification_criteria"] is None

    def test_none_like_plan(self):
        result = extract_plan_sections("   \n\n  ")
        assert result["plan_risk_register"] is None
        assert result["plan_verification_criteria"] is None
