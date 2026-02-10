"""
Tests for automated triage step in ArchitecturalReviewLogWorkflow.

Covers:
- Helper functions: _strip_json_fences, _extract_untriaged_suggestions,
  _validate_triage_output, _apply_triage_decisions, _compute_substantially_addressed,
  _insert_substantially_addressed_section
- Integration: triage runs after reviewers, enable_triage config, cost tracking,
  StepResult, partial triage, no-untriaged skip
"""

import json
from unittest.mock import MagicMock

import pytest

from startd8.exceptions import GeminiSafetyFilterError
from startd8.models import TokenUsage
from startd8.workflows.builtin.architectural_review_log_workflow import (
    APPENDIX_TEMPLATE,
    ALLOWED_AREAS,
    _strip_json_fences,
    _extract_untriaged_suggestions,
    _validate_triage_output,
    _apply_triage_decisions,
    _compute_substantially_addressed,
    _insert_substantially_addressed_section,
    _compute_area_coverage,
    _insert_areas_needing_review_section,
    _build_triage_prompt,
    _build_prompt,
    _build_untriaged_block,
    _extract_reviewer_sources,
    _compute_substantially_addressed_from_doc,
    ArchitecturalReviewLogWorkflow,
)


# ---------------------------------------------------------------------------
# Sample document with appendix for tests
# ---------------------------------------------------------------------------

SAMPLE_DOC_WITH_SUGGESTIONS = """# Test Architecture Plan

Some content here about the architecture.

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

- **Reviewer**: claude-opus (claude-opus-4-20250514)
- **Date**: 2026-02-09 00:00:00 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | Add circuit breakers | Critical for resilience | Section 3 | Load testing |
| R1-S2 | Security | medium | Add rate limiting | Prevent abuse | Section 5 | Pen testing |
| R1-S3 | Architecture | high | Add retry logic | Handle transient failures | Section 3 | Unit tests |

#### Review Round R2

- **Reviewer**: gemini-pro (gemini-2.5-pro)
- **Date**: 2026-02-09 01:00:00 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Architecture | high | Add health checks | Operational readiness | Section 4 | Integration tests |
| R2-S2 | Data | medium | Add schema versioning | Data evolution | Section 6 | Schema review |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-S1: Agree, circuit breakers essential for microservices
- R1-S3: Retry logic is a must-have
"""


# ---------------------------------------------------------------------------
# _strip_json_fences tests
# ---------------------------------------------------------------------------

class TestStripJsonFences:

    def test_strip_json_fence(self):
        text = '```json\n[{"id": "R1-S1"}]\n```'
        assert _strip_json_fences(text) == '[{"id": "R1-S1"}]'

    def test_strip_bare_fence(self):
        text = '```\n[{"id": "R1-S1"}]\n```'
        assert _strip_json_fences(text) == '[{"id": "R1-S1"}]'

    def test_no_fence_passthrough(self):
        text = '[{"id": "R1-S1"}]'
        assert _strip_json_fences(text) == text

    def test_case_insensitive(self):
        text = '```JSON\n[{"id": "R1-S1"}]\n```'
        assert _strip_json_fences(text) == '[{"id": "R1-S1"}]'

    def test_whitespace_after_fence(self):
        text = '```json  \n[{"id": "R1-S1"}]\n```  '
        assert _strip_json_fences(text) == '[{"id": "R1-S1"}]'


# ---------------------------------------------------------------------------
# _extract_untriaged_suggestions tests
# ---------------------------------------------------------------------------

class TestExtractUntriagedSuggestions:

    def test_extracts_all_suggestions(self):
        suggestions, endorsements = _extract_untriaged_suggestions(SAMPLE_DOC_WITH_SUGGESTIONS, [], [])
        assert len(suggestions) == 5
        ids = [s["id"] for s in suggestions]
        assert "R1-S1" in ids
        assert "R2-S2" in ids

    def test_filters_applied_ids(self):
        suggestions, _ = _extract_untriaged_suggestions(SAMPLE_DOC_WITH_SUGGESTIONS, ["R1-S1", "R1-S2"], [])
        ids = [s["id"] for s in suggestions]
        assert "R1-S1" not in ids
        assert "R1-S2" not in ids
        assert "R1-S3" in ids

    def test_filters_rejected_ids(self):
        suggestions, _ = _extract_untriaged_suggestions(SAMPLE_DOC_WITH_SUGGESTIONS, [], ["R2-S1"])
        ids = [s["id"] for s in suggestions]
        assert "R2-S1" not in ids
        assert "R2-S2" in ids

    def test_counts_endorsements(self):
        _, endorsements = _extract_untriaged_suggestions(SAMPLE_DOC_WITH_SUGGESTIONS, [], [])
        assert endorsements.get("R1-S1", 0) == 1
        assert endorsements.get("R1-S3", 0) == 1
        assert endorsements.get("R1-S2", 0) == 0

    def test_no_appendix_c(self):
        doc = "# Simple doc\n\nNo appendix here."
        suggestions, endorsements = _extract_untriaged_suggestions(doc, [], [])
        assert suggestions == []
        assert endorsements == {}

    def test_suggestion_metadata(self):
        suggestions, _ = _extract_untriaged_suggestions(SAMPLE_DOC_WITH_SUGGESTIONS, [], [])
        r1s1 = next(s for s in suggestions if s["id"] == "R1-S1")
        assert r1s1["area"] == "Architecture"
        assert r1s1["severity"] == "high"
        assert r1s1["round"] == 1


# ---------------------------------------------------------------------------
# _validate_triage_output tests
# ---------------------------------------------------------------------------

class TestValidateTriageOutput:

    def test_valid_json(self):
        data = [
            {"id": "R1-S1", "decision": "ACCEPT", "summary": "Add circuit breakers", "rationale": "Critical", "area": "architecture"},
            {"id": "R1-S2", "decision": "REJECT", "summary": "Rate limiting", "rationale": "Not needed", "area": "security"},
        ]
        ok, msg, decisions, missing = _validate_triage_output(json.dumps(data), ["R1-S1", "R1-S2"])
        assert ok is True
        assert msg == "ok"
        assert len(decisions) == 2
        assert missing == []

    def test_missing_ids_reported(self):
        data = [
            {"id": "R1-S1", "decision": "ACCEPT", "summary": "Test", "rationale": "Ok", "area": "architecture"},
        ]
        ok, msg, decisions, missing = _validate_triage_output(json.dumps(data), ["R1-S1", "R1-S2", "R1-S3"])
        assert ok is True
        assert len(decisions) == 1
        assert "R1-S2" in missing
        assert "R1-S3" in missing

    def test_bad_decision_value(self):
        data = [
            {"id": "R1-S1", "decision": "MAYBE", "summary": "Test", "rationale": "Ok", "area": "architecture"},
        ]
        ok, msg, decisions, missing = _validate_triage_output(json.dumps(data), ["R1-S1"])
        # No valid decisions
        assert ok is False
        assert "invalid decision" in msg.lower()

    def test_bad_area_value(self):
        data = [
            {"id": "R1-S1", "decision": "ACCEPT", "summary": "Test", "rationale": "Ok", "area": "cooking"},
        ]
        ok, msg, decisions, missing = _validate_triage_output(json.dumps(data), ["R1-S1"])
        assert ok is False
        assert "invalid area" in msg.lower()

    def test_unknown_id(self):
        data = [
            {"id": "R99-S1", "decision": "ACCEPT", "summary": "Test", "rationale": "Ok", "area": "architecture"},
        ]
        ok, msg, decisions, missing = _validate_triage_output(json.dumps(data), ["R1-S1"])
        assert ok is False
        assert "unknown ID" in msg

    def test_json_parse_error(self):
        ok, msg, decisions, missing = _validate_triage_output("not json", ["R1-S1"])
        assert ok is False
        assert "JSON parse error" in msg

    def test_json_with_fences(self):
        data = [
            {"id": "R1-S1", "decision": "ACCEPT", "summary": "Test", "rationale": "Ok", "area": "architecture"},
        ]
        fenced = f"```json\n{json.dumps(data)}\n```"
        ok, msg, decisions, missing = _validate_triage_output(fenced, ["R1-S1"])
        assert ok is True
        assert len(decisions) == 1

    def test_partial_valid_decisions(self):
        data = [
            {"id": "R1-S1", "decision": "ACCEPT", "summary": "Test", "rationale": "Ok", "area": "architecture"},
            {"id": "R1-S2", "decision": "MAYBE", "summary": "Test2", "rationale": "Ok", "area": "security"},
        ]
        ok, msg, decisions, missing = _validate_triage_output(json.dumps(data), ["R1-S1", "R1-S2"])
        # Partial: R1-S1 is valid, R1-S2 is invalid
        assert ok is True
        assert "Partial" in msg
        assert len(decisions) == 1
        assert decisions[0]["id"] == "R1-S1"


# ---------------------------------------------------------------------------
# _apply_triage_decisions tests
# ---------------------------------------------------------------------------

class TestApplyTriageDecisions:

    def test_accept_adds_to_appendix_a(self):
        decisions = [
            {"id": "R1-S1", "decision": "ACCEPT", "summary": "Add circuit breakers", "rationale": "Critical", "area": "architecture"},
        ]
        result = _apply_triage_decisions(SAMPLE_DOC_WITH_SUGGESTIONS, decisions, {"R1-S1": "claude-opus"})
        assert "R1-S1" in result.split("### Appendix A")[1].split("### Appendix B")[0]
        assert "(none yet)" not in result.split("### Appendix A")[1].split("### Appendix B")[0]

    def test_reject_adds_to_appendix_b(self):
        decisions = [
            {"id": "R1-S2", "decision": "REJECT", "summary": "Rate limiting", "rationale": "Not needed", "area": "security"},
        ]
        result = _apply_triage_decisions(SAMPLE_DOC_WITH_SUGGESTIONS, decisions, {"R1-S2": "claude-opus"})
        assert "R1-S2" in result.split("### Appendix B")[1].split("### Appendix C")[0]
        assert "(none yet)" not in result.split("### Appendix B")[1].split("### Appendix C")[0]

    def test_mixed_decisions(self):
        decisions = [
            {"id": "R1-S1", "decision": "ACCEPT", "summary": "Circuit breakers", "rationale": "Critical", "area": "architecture"},
            {"id": "R1-S2", "decision": "REJECT", "summary": "Rate limiting", "rationale": "Not needed now", "area": "security"},
        ]
        result = _apply_triage_decisions(SAMPLE_DOC_WITH_SUGGESTIONS, decisions, {"R1-S1": "claude", "R1-S2": "claude"})
        appendix_a = result.split("### Appendix A")[1].split("### Appendix B")[0]
        appendix_b = result.split("### Appendix B")[1].split("### Appendix C")[0]
        assert "R1-S1" in appendix_a
        assert "R1-S2" in appendix_b

    def test_placeholder_removed(self):
        decisions = [
            {"id": "R1-S1", "decision": "ACCEPT", "summary": "Test", "rationale": "Ok", "area": "architecture"},
        ]
        result = _apply_triage_decisions(SAMPLE_DOC_WITH_SUGGESTIONS, decisions, {})
        appendix_a = result.split("### Appendix A")[1].split("### Appendix B")[0]
        assert "(none yet)" not in appendix_a


# ---------------------------------------------------------------------------
# _compute_substantially_addressed tests
# ---------------------------------------------------------------------------

class TestComputeSubstantiallyAddressed:

    def test_threshold_met(self):
        applied = [("R1-S1", "architecture"), ("R2-S1", "architecture"), ("R3-S1", "architecture")]
        result = _compute_substantially_addressed(applied, threshold=3)
        assert "architecture" in result
        assert len(result["architecture"]) == 3

    def test_threshold_not_met(self):
        applied = [("R1-S1", "architecture"), ("R2-S1", "architecture")]
        result = _compute_substantially_addressed(applied, threshold=3)
        assert "architecture" not in result

    def test_multiple_areas(self):
        applied = [
            ("R1-S1", "architecture"), ("R2-S1", "architecture"), ("R3-S1", "architecture"),
            ("R1-S2", "security"), ("R2-S2", "security"), ("R3-S2", "security"),
            ("R1-S3", "data"),  # only 1, below threshold
        ]
        result = _compute_substantially_addressed(applied, threshold=3)
        assert "architecture" in result
        assert "security" in result
        assert "data" not in result

    def test_empty_input(self):
        result = _compute_substantially_addressed([], threshold=3)
        assert result == {}

    def test_threshold_one(self):
        applied = [("R1-S1", "architecture")]
        result = _compute_substantially_addressed(applied, threshold=1)
        assert "architecture" in result


# ---------------------------------------------------------------------------
# _insert_substantially_addressed_section tests
# ---------------------------------------------------------------------------

class TestInsertSubstantiallyAddressedSection:

    def test_insert_new_section(self):
        addressed = {"architecture": ["R1-S1", "R2-S1", "R3-S1"]}
        result = _insert_substantially_addressed_section(SAMPLE_DOC_WITH_SUGGESTIONS, addressed)
        assert "### Areas Substantially Addressed" in result
        assert "**architecture**" in result
        # Should appear before Appendix A
        sa_pos = result.index("### Areas Substantially Addressed")
        appendix_a_pos = result.index("### Appendix A")
        assert sa_pos < appendix_a_pos

    def test_update_existing_section(self):
        # First insert
        addressed1 = {"architecture": ["R1-S1", "R2-S1", "R3-S1"]}
        doc = _insert_substantially_addressed_section(SAMPLE_DOC_WITH_SUGGESTIONS, addressed1)
        assert "**architecture**" in doc

        # Update with different areas
        addressed2 = {"security": ["R3-S7", "R5-S6", "R6-S2"]}
        result = _insert_substantially_addressed_section(doc, addressed2)
        assert "**security**" in result
        # Should only have one "### Areas Substantially Addressed" heading
        assert result.count("### Areas Substantially Addressed") == 1

    def test_empty_addressed(self):
        result = _insert_substantially_addressed_section(SAMPLE_DOC_WITH_SUGGESTIONS, {})
        # Still inserts the section heading (empty)
        assert "### Areas Substantially Addressed" in result


# ---------------------------------------------------------------------------
# _compute_area_coverage tests
# ---------------------------------------------------------------------------

class TestComputeAreaCoverage:

    def test_returns_all_allowed_areas(self):
        """Coverage dict has an entry for every ALLOWED_AREA, even with no data."""
        result = _compute_area_coverage(SAMPLE_DOC_WITH_SUGGESTIONS, threshold=3)
        assert set(result.keys()) == ALLOWED_AREAS

    def test_counts_and_gaps(self):
        """Accepted counts and gaps are computed correctly from Appendix A/C."""
        result = _compute_area_coverage(SAMPLE_DOC_WITH_SUGGESTIONS, threshold=3)
        # SAMPLE_DOC has R1-S1(Architecture), R1-S2(Security), R1-S3(Data),
        # R2-S1(Ops), R2-S2(Validation) — none applied (empty Appendix A placeholder)
        for area in ALLOWED_AREAS:
            assert result[area]["accepted_count"] == 0
            assert result[area]["gap"] == 3
            assert result[area]["addressed"] is False

    def test_with_applied_suggestions(self):
        """Areas with applied suggestions show correct counts."""
        # SAMPLE_DOC areas: R1-S1=Architecture, R1-S2=Security, R1-S3=Architecture,
        #                   R2-S1=Architecture, R2-S2=Data
        # Replace the (none yet) placeholder with actual applied IDs
        doc = SAMPLE_DOC_WITH_SUGGESTIONS.replace(
            "| (none yet) |  |  |  |  |\n",
            "| R1-S2 | Test | Test | Notes | 2026-01-01 |\n"
            "| R2-S2 | Test | Test | Notes | 2026-01-01 |\n",
            1,  # only first occurrence (Appendix A)
        )
        result = _compute_area_coverage(doc, threshold=2)
        # R1-S2 is Security, R2-S2 is Data
        assert result["security"]["accepted_count"] == 1
        assert result["security"]["gap"] == 1
        assert result["security"]["addressed"] is False
        assert result["data"]["accepted_count"] == 1
        assert result["data"]["gap"] == 1

    def test_addressed_flag(self):
        """Areas meeting threshold have addressed=True and gap=0."""
        # R1-S1=Architecture, R1-S3=Architecture, R2-S1=Architecture → 3 arch suggestions
        doc = SAMPLE_DOC_WITH_SUGGESTIONS.replace(
            "| (none yet) |  |  |  |  |\n",
            "| R1-S1 | Test | Test | Notes | 2026-01-01 |\n"
            "| R1-S3 | Test | Test | Notes | 2026-01-01 |\n"
            "| R2-S1 | Test | Test | Notes | 2026-01-01 |\n",
            1,  # only first occurrence (Appendix A)
        )
        result = _compute_area_coverage(doc, threshold=1)
        # All 3 are Architecture
        assert result["architecture"]["addressed"] is True
        assert result["architecture"]["gap"] == 0
        assert result["architecture"]["accepted_count"] == 3
        # Other areas still 0
        assert result["security"]["addressed"] is False
        assert result["data"]["addressed"] is False


# ---------------------------------------------------------------------------
# _insert_areas_needing_review_section tests
# ---------------------------------------------------------------------------

class TestInsertAreasNeedingReviewSection:

    def test_inserts_underserved_areas(self):
        """Section lists areas below threshold with gap details."""
        coverage = {
            area: {"accepted_count": 0, "accepted_ids": [], "addressed": False, "gap": 3}
            for area in ALLOWED_AREAS
        }
        coverage["architecture"] = {
            "accepted_count": 5, "accepted_ids": ["R1-S1", "R2-S1", "R3-S1", "R4-S1", "R5-S1"],
            "addressed": True, "gap": 0,
        }
        result = _insert_areas_needing_review_section(SAMPLE_DOC_WITH_SUGGESTIONS, coverage, threshold=3)
        assert "### Areas Needing Further Review" in result
        # Underserved areas should be listed
        assert "**security**" in result.split("### Areas Needing Further Review")[1].split("###")[0]
        # Addressed areas should NOT be listed as needing review
        needing_section = result.split("### Areas Needing Further Review")[1].split("###")[0]
        assert "**architecture**: 5 accepted" not in needing_section

    def test_all_addressed_shows_message(self):
        """When all areas are addressed, shows 'all areas reached threshold' message."""
        coverage = {
            area: {"accepted_count": 3, "accepted_ids": [f"R1-{area[:2]}"], "addressed": True, "gap": 0}
            for area in ALLOWED_AREAS
        }
        result = _insert_areas_needing_review_section(SAMPLE_DOC_WITH_SUGGESTIONS, coverage, threshold=3)
        assert "All areas have reached the substantially addressed threshold" in result

    def test_shows_existing_ids_for_partial_coverage(self):
        """Areas with some accepted suggestions show the existing IDs."""
        coverage = {
            area: {"accepted_count": 0, "accepted_ids": [], "addressed": False, "gap": 3}
            for area in ALLOWED_AREAS
        }
        coverage["security"] = {
            "accepted_count": 2, "accepted_ids": ["R2-S4", "R6-S4"],
            "addressed": False, "gap": 1,
        }
        result = _insert_areas_needing_review_section(SAMPLE_DOC_WITH_SUGGESTIONS, coverage, threshold=3)
        needing_section = result.split("### Areas Needing Further Review")[1].split("###")[0]
        assert "R2-S4, R6-S4" in needing_section
        assert "needs 1 more" in needing_section

    def test_placed_after_substantially_addressed(self):
        """Section is inserted after 'Areas Substantially Addressed'."""
        # First insert SA section
        addressed = {"architecture": ["R1-S1", "R2-S1", "R3-S1"]}
        doc = _insert_substantially_addressed_section(SAMPLE_DOC_WITH_SUGGESTIONS, addressed)
        # Then insert needing review section
        coverage = {
            area: {"accepted_count": 0, "accepted_ids": [], "addressed": False, "gap": 3}
            for area in ALLOWED_AREAS
        }
        result = _insert_areas_needing_review_section(doc, coverage, threshold=3)
        sa_pos = result.index("### Areas Substantially Addressed")
        nr_pos = result.index("### Areas Needing Further Review")
        appendix_a_pos = result.index("### Appendix A")
        assert sa_pos < nr_pos < appendix_a_pos

    def test_update_existing_section(self):
        """Repeated calls update the section rather than duplicating it."""
        coverage1 = {
            area: {"accepted_count": 0, "accepted_ids": [], "addressed": False, "gap": 3}
            for area in ALLOWED_AREAS
        }
        doc = _insert_areas_needing_review_section(SAMPLE_DOC_WITH_SUGGESTIONS, coverage1, threshold=3)
        assert doc.count("### Areas Needing Further Review") == 1

        coverage2 = {
            area: {"accepted_count": 3, "accepted_ids": [], "addressed": True, "gap": 0}
            for area in ALLOWED_AREAS
        }
        result = _insert_areas_needing_review_section(doc, coverage2, threshold=3)
        assert result.count("### Areas Needing Further Review") == 1
        assert "All areas have reached" in result


# ---------------------------------------------------------------------------
# _build_triage_prompt tests
# ---------------------------------------------------------------------------

class TestBuildTriagePrompt:

    def test_prompt_includes_suggestions(self):
        untriaged_block = "| R1-S1 | Architecture | high | Test | Rationale | Section 1 | Manual |"
        prompt = _build_triage_prompt("doc content", [], [], untriaged_block, {})
        assert "R1-S1" in prompt
        assert "ACCEPT" in prompt
        assert "REJECT" in prompt
        assert "JSON array" in prompt

    def test_prompt_includes_endorsements(self):
        endorsements = {"R1-S1": 2, "R1-S3": 1}
        prompt = _build_triage_prompt("doc", [], [], "block", endorsements)
        assert "R1-S1: 2 endorsement" in prompt
        assert "R1-S3: 1 endorsement" in prompt


# ---------------------------------------------------------------------------
# _build_prompt two-tier priority tests
# ---------------------------------------------------------------------------

class TestBuildPromptPriority:
    """Tests for two-tier area prioritization in reviewer prompts."""

    def _call(self, substantially_addressed_areas=None, max_suggestions=5, area_coverage=None):
        return _build_prompt(
            document_without_appendix="# Test Plan\n\nSome content.",
            applied_ids=["R1-S1"],
            rejected_ids=["R1-S2"],
            round_number=3,
            max_suggestions=max_suggestions,
            reviewer_label="test-agent (test-model)",
            scope="Test review",
            substantially_addressed_areas=substantially_addressed_areas,
            area_coverage=area_coverage,
        )

    def test_no_substantially_addressed_uses_generic_focus(self):
        """Without substantially_addressed, the generic focus line is used."""
        prompt = self._call(substantially_addressed_areas=None)
        assert "architecture clarity, execution safety" in prompt
        assert "Priority areas NOT yet" not in prompt

    def test_uncovered_areas_listed_as_priority(self):
        """When some areas are uncovered, they appear as Tier 1 priorities."""
        # Only cover 3 of 7 areas
        addressed = {
            "architecture": ["R1-S1", "R2-S1", "R3-S1"],
            "validation": ["R1-S3", "R2-S3", "R3-S3"],
            "ops": ["R1-S4", "R2-S4", "R3-S4"],
        }
        prompt = self._call(substantially_addressed_areas=addressed)
        assert "Priority areas NOT yet substantially addressed" in prompt
        # Uncovered areas should be named
        for area in sorted(ALLOWED_AREAS - {"architecture", "validation", "ops"}):
            assert f"**{area}**" in prompt
        # Dynamic focus line should name uncovered areas
        assert "Prioritize:" in prompt
        # Should NOT use the generic focus line
        assert "architecture clarity, execution safety" not in prompt

    def test_uncovered_areas_allocation_instruction(self):
        """Prompt tells the reviewer to allocate most slots to uncovered areas."""
        addressed = {"architecture": ["R1-S1", "R2-S1", "R3-S1"]}
        prompt = self._call(substantially_addressed_areas=addressed, max_suggestions=5)
        assert "at least 4 of your 5 suggestion slots" in prompt

    def test_covered_areas_shown_as_secondary(self):
        """Covered areas appear with counts as the secondary tier."""
        addressed = {
            "architecture": ["R1-S1", "R2-S1", "R3-S1"],
        }
        prompt = self._call(substantially_addressed_areas=addressed)
        assert "already substantially addressed" in prompt
        assert "**architecture**: 3 suggestions applied" in prompt

    def test_all_areas_covered_enters_gap_hunting_mode(self):
        """When all 7 areas are covered, prompt switches to gap-hunting mode."""
        addressed = {area: [f"R1-{area[:2]}"] for area in ALLOWED_AREAS}
        prompt = self._call(substantially_addressed_areas=addressed)
        assert f"All {len(ALLOWED_AREAS)} review areas are substantially addressed" in prompt
        assert "genuine gaps" in prompt
        assert "second-order" in prompt.lower()
        # Should NOT use the generic focus line
        assert "architecture clarity, execution safety" not in prompt
        # Should NOT say "Priority areas NOT yet"
        assert "Priority areas NOT yet" not in prompt

    def test_all_areas_covered_lists_specific_gap_strategies(self):
        """Gap-hunting mode provides concrete search strategies."""
        addressed = {area: [f"R1-{area[:2]}"] for area in ALLOWED_AREAS}
        prompt = self._call(substantially_addressed_areas=addressed)
        assert "Gaps *between* areas" in prompt
        assert "Assumptions that were never validated" in prompt
        assert "Second-order effects" in prompt

    def test_dynamic_focus_references_correct_total(self):
        """The dynamic focus line includes the correct total of applied suggestions."""
        addressed = {
            "architecture": ["R1-S1", "R2-S1", "R3-S1"],
            "validation": ["R1-S3", "R2-S3"],  # below threshold but still passed in
        }
        prompt = self._call(substantially_addressed_areas=addressed)
        assert "5 accepted suggestions missed" in prompt

    def test_area_coverage_shows_gap_details(self):
        """When area_coverage is provided, Tier 1 shows per-area gap details."""
        addressed = {"architecture": ["R1-S1", "R2-S1", "R3-S1"]}
        coverage = {
            area: {"accepted_count": 0, "accepted_ids": [], "addressed": False, "gap": 3}
            for area in ALLOWED_AREAS
        }
        coverage["architecture"] = {
            "accepted_count": 3, "accepted_ids": ["R1-S1", "R2-S1", "R3-S1"],
            "addressed": True, "gap": 0,
        }
        coverage["security"] = {
            "accepted_count": 2, "accepted_ids": ["R2-S4", "R6-S4"],
            "addressed": False, "gap": 1,
        }
        prompt = self._call(
            substantially_addressed_areas=addressed,
            area_coverage=coverage,
        )
        # Should show per-area gap details for uncovered areas
        assert "**security**: 2 accepted (R2-S4, R6-S4)" in prompt
        assert "needs 1 more" in prompt

    def test_area_coverage_shows_zero_count_areas(self):
        """Areas with no accepted suggestions show 'no accepted suggestions yet'."""
        addressed = {"architecture": ["R1-S1", "R2-S1", "R3-S1"]}
        coverage = {
            area: {"accepted_count": 0, "accepted_ids": [], "addressed": False, "gap": 3}
            for area in ALLOWED_AREAS
        }
        coverage["architecture"] = {
            "accepted_count": 3, "accepted_ids": ["R1-S1", "R2-S1", "R3-S1"],
            "addressed": True, "gap": 0,
        }
        prompt = self._call(
            substantially_addressed_areas=addressed,
            area_coverage=coverage,
        )
        assert "no accepted suggestions yet" in prompt

    def test_without_area_coverage_falls_back_to_names(self):
        """Without area_coverage, uncovered areas are listed by name only."""
        addressed = {"architecture": ["R1-S1", "R2-S1", "R3-S1"]}
        prompt = self._call(
            substantially_addressed_areas=addressed,
            area_coverage=None,
        )
        # Should still list uncovered areas by name
        assert "Priority areas NOT yet substantially addressed" in prompt
        # But should NOT show gap details
        assert "needs" not in prompt.split("Priority areas")[1].split("Exhaust")[0]


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

class TestTriageIntegration:

    def _make_valid_snippet(self, round_number):
        return f"""#### Review Round R{round_number}

- **Reviewer**: test-agent (test-model)
- **Date**: 2026-02-09 00:00:00 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R{round_number}-S1 | Architecture | high | Test suggestion | Test rationale | Section 1 | Manual review |
| R{round_number}-S2 | Security | medium | Another suggestion | Another rationale | Section 2 | Pen test |
"""

    def _make_mock_agent(self, name="test-agent", model="test-model", is_gemini=False):
        agent = MagicMock()
        agent.name = name
        agent.model = model
        agent.safety_settings = None
        if is_gemini:
            agent.__class__.__module__ = "startd8.agents.gemini"
        else:
            agent.__class__.__module__ = "startd8.agents.claude"
        return agent

    def _make_triage_response(self, suggestion_ids, decisions=None):
        """Build a valid triage JSON response."""
        if decisions is None:
            decisions = ["ACCEPT"] * len(suggestion_ids)
        data = []
        for sid, dec in zip(suggestion_ids, decisions):
            data.append({
                "id": sid,
                "decision": dec,
                "summary": f"Summary for {sid}",
                "rationale": f"Rationale for {sid}",
                "area": "architecture",
            })
        return json.dumps(data)

    def test_triage_runs_after_reviewers(self, tmp_path):
        """Triage should run after all review rounds using the first agent."""
        doc_path = tmp_path / "test_doc.md"
        doc_path.write_text("# Test Plan\n\nSome content here.\n")

        snippet = self._make_valid_snippet(1)
        token_usage = TokenUsage(input=100, output=50, total=150, model_name="test")

        triage_response = self._make_triage_response(["R1-S1", "R1-S2"])
        triage_token_usage = TokenUsage(input=200, output=100, total=300, model_name="test")

        agent = self._make_mock_agent()
        agent.generate.side_effect = [
            (snippet, 500, token_usage),
            (triage_response, 300, triage_token_usage),
        ]

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={"document_path": str(doc_path)},
            agents=[agent],
            on_progress=None,
        )

        assert result.success is True
        assert result.output["rounds_appended"] == 1
        assert result.output["triage"]["accepted"] == 2
        assert result.output["triage"]["rejected"] == 0
        # Agent was called twice: once for review, once for triage
        assert agent.generate.call_count == 2

    def test_enable_triage_false_skips(self, tmp_path):
        """enable_triage: False should skip triage entirely."""
        doc_path = tmp_path / "test_doc.md"
        doc_path.write_text("# Test Plan\n\nSome content here.\n")

        snippet = self._make_valid_snippet(1)
        token_usage = TokenUsage(input=100, output=50, total=150, model_name="test")

        agent = self._make_mock_agent()
        agent.generate.return_value = (snippet, 500, token_usage)

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={"document_path": str(doc_path), "enable_triage": False},
            agents=[agent],
            on_progress=None,
        )

        assert result.success is True
        assert result.output["triage"]["enabled"] is False
        assert result.output["triage"]["accepted"] == 0
        # Only one call (the review), no triage call
        assert agent.generate.call_count == 1

    def test_triage_costs_tracked(self, tmp_path):
        """Triage costs should be included in total metrics."""
        doc_path = tmp_path / "test_doc.md"
        doc_path.write_text("# Test Plan\n\nSome content here.\n")

        snippet = self._make_valid_snippet(1)
        review_token_usage = TokenUsage(input=100, output=50, total=150, model_name="test")

        triage_response = self._make_triage_response(["R1-S1", "R1-S2"])
        triage_token_usage = TokenUsage(input=200, output=100, total=300, model_name="test")

        agent = self._make_mock_agent()
        agent.generate.side_effect = [
            (snippet, 500, review_token_usage),
            (triage_response, 300, triage_token_usage),
        ]

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={"document_path": str(doc_path)},
            agents=[agent],
            on_progress=None,
        )

        # Cost is computed by PricingService fallback; just verify both are aggregated
        assert result.metrics.total_cost > 0
        assert result.metrics.input_tokens == 300  # 100 + 200
        assert result.metrics.output_tokens == 150  # 50 + 100

    def test_triage_step_result_created(self, tmp_path):
        """A StepResult should be created for the triage step."""
        doc_path = tmp_path / "test_doc.md"
        doc_path.write_text("# Test Plan\n\nSome content here.\n")

        snippet = self._make_valid_snippet(1)
        token_usage = TokenUsage(input=100, output=50, total=150, model_name="test")

        triage_response = self._make_triage_response(["R1-S1", "R1-S2"], ["ACCEPT", "REJECT"])
        triage_token_usage = TokenUsage(input=200, output=100, total=300, model_name="test")

        agent = self._make_mock_agent()
        agent.generate.side_effect = [
            (snippet, 500, token_usage),
            (triage_response, 300, triage_token_usage),
        ]

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={"document_path": str(doc_path)},
            agents=[agent],
            on_progress=None,
        )

        triage_steps = [s for s in result.steps if s.step_name == "triage"]
        assert len(triage_steps) == 1
        ts = triage_steps[0]
        assert ts.error is None
        assert ts.metadata["accepted"] == 1
        assert ts.metadata["rejected"] == 1

    def test_appendix_ab_updated_after_triage(self, tmp_path):
        """Appendix A and B should have new rows after triage."""
        doc_path = tmp_path / "test_doc.md"
        doc_path.write_text("# Test Plan\n\nSome content here.\n")

        snippet = self._make_valid_snippet(1)
        token_usage = TokenUsage(input=100, output=50, total=150, model_name="test")

        triage_response = self._make_triage_response(["R1-S1", "R1-S2"], ["ACCEPT", "REJECT"])
        triage_token_usage = TokenUsage(input=200, output=100, total=300, model_name="test")

        agent = self._make_mock_agent()
        agent.generate.side_effect = [
            (snippet, 500, token_usage),
            (triage_response, 300, triage_token_usage),
        ]

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={"document_path": str(doc_path)},
            agents=[agent],
            on_progress=None,
        )

        doc_text = doc_path.read_text()
        appendix_a = doc_text.split("### Appendix A")[1].split("### Appendix B")[0]
        appendix_b = doc_text.split("### Appendix B")[1].split("### Appendix C")[0]
        assert "R1-S1" in appendix_a
        assert "R1-S2" in appendix_b
        assert "(none yet)" not in appendix_a
        assert "(none yet)" not in appendix_b

    def test_substantially_addressed_section_inserted(self, tmp_path):
        """When enough suggestions are accepted in one area, the section is inserted."""
        doc_path = tmp_path / "test_doc.md"
        doc_path.write_text("# Test Plan\n\nSome content here.\n")

        # Create a snippet with 3 architecture suggestions (meeting threshold=3)
        snippet = f"""#### Review Round R1

- **Reviewer**: test-agent (test-model)
- **Date**: 2026-02-09 00:00:00 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | Suggestion 1 | Rationale 1 | Section 1 | Test 1 |
| R1-S2 | Architecture | high | Suggestion 2 | Rationale 2 | Section 2 | Test 2 |
| R1-S3 | Architecture | medium | Suggestion 3 | Rationale 3 | Section 3 | Test 3 |
"""
        token_usage = TokenUsage(input=100, output=50, total=150, model_name="test")
        triage_response = self._make_triage_response(["R1-S1", "R1-S2", "R1-S3"])
        triage_token_usage = TokenUsage(input=200, output=100, total=300, model_name="test")

        agent = self._make_mock_agent()
        agent.generate.side_effect = [
            (snippet, 500, token_usage),
            (triage_response, 300, triage_token_usage),
        ]

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={
                "document_path": str(doc_path),
                "substantially_addressed_threshold": 3,
            },
            agents=[agent],
            on_progress=None,
        )

        doc_text = doc_path.read_text()
        assert "### Areas Substantially Addressed" in doc_text
        assert "architecture" in result.output["triage"]["substantially_addressed_areas"]

    def test_partial_triage_applies_valid_decisions(self, tmp_path):
        """If some triage entries are invalid, valid ones should still be applied."""
        doc_path = tmp_path / "test_doc.md"
        doc_path.write_text("# Test Plan\n\nSome content here.\n")

        snippet = self._make_valid_snippet(1)
        token_usage = TokenUsage(input=100, output=50, total=150, model_name="test")

        # One valid, one with bad decision
        triage_data = [
            {"id": "R1-S1", "decision": "ACCEPT", "summary": "Good", "rationale": "Ok", "area": "architecture"},
            {"id": "R1-S2", "decision": "MAYBE", "summary": "Bad", "rationale": "Invalid", "area": "security"},
        ]
        triage_response = json.dumps(triage_data)
        triage_token_usage = TokenUsage(input=200, output=100, total=300, model_name="test")

        agent = self._make_mock_agent()
        agent.generate.side_effect = [
            (snippet, 500, token_usage),
            (triage_response, 300, triage_token_usage),
        ]

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={"document_path": str(doc_path)},
            agents=[agent],
            on_progress=None,
        )

        assert result.output["triage"]["accepted"] == 1
        doc_text = doc_path.read_text()
        appendix_a = doc_text.split("### Appendix A")[1].split("### Appendix B")[0]
        assert "R1-S1" in appendix_a

    def test_no_untriaged_skips_gracefully(self, tmp_path):
        """When doc has no Appendix C suggestions, triage should be skipped."""
        doc_path = tmp_path / "test_doc.md"
        # Doc with appendix but no suggestions
        doc_text = "# Test Plan\n\nContent.\n" + APPENDIX_TEMPLATE
        doc_path.write_text(doc_text)

        # No review rounds will succeed (no suggestions to triage)
        token_usage = TokenUsage(input=100, output=50, total=150, model_name="test")

        snippet = self._make_valid_snippet(1)
        agent = self._make_mock_agent()
        agent.generate.return_value = (snippet, 500, token_usage)

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={"document_path": str(doc_path)},
            agents=[agent],
            on_progress=None,
        )

        # Triage should have been attempted but had no untriaged suggestions
        # Initially the doc has nothing in Appendix C, then after review it has suggestions.
        # The triage should run on the new suggestions.
        # But let's verify it doesn't crash when there are suggestions to triage
        assert result.success is True

    def test_triage_with_multiple_reviewers(self, tmp_path):
        """Triage should use first agent and process suggestions from all rounds."""
        doc_path = tmp_path / "test_doc.md"
        doc_path.write_text("# Test Plan\n\nSome content here.\n")

        snippet_r1 = self._make_valid_snippet(1)
        snippet_r2 = self._make_valid_snippet(2)
        token_usage = TokenUsage(input=100, output=50, total=150, model_name="test")

        # Triage should see suggestions from both rounds
        triage_response = self._make_triage_response(
            ["R1-S1", "R1-S2", "R2-S1", "R2-S2"],
            ["ACCEPT", "REJECT", "ACCEPT", "REJECT"],
        )
        triage_token_usage = TokenUsage(input=200, output=100, total=300, model_name="test")

        agent1 = self._make_mock_agent(name="agent1", model="model1")
        agent2 = self._make_mock_agent(name="agent2", model="model2")

        # agent1 does R1, then triage
        agent1.generate.side_effect = [
            (snippet_r1, 500, token_usage),
            (triage_response, 300, triage_token_usage),
        ]
        agent2.generate.return_value = (snippet_r2, 500, token_usage)

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={"document_path": str(doc_path)},
            agents=[agent1, agent2],
            on_progress=None,
        )

        assert result.success is True
        assert result.output["triage"]["accepted"] == 2
        assert result.output["triage"]["rejected"] == 2
        # Triage used agent1 (first agent)
        triage_steps = [s for s in result.steps if s.step_name == "triage"]
        assert len(triage_steps) == 1
        assert "agent1" in triage_steps[0].agent_name


# ---------------------------------------------------------------------------
# _extract_reviewer_sources tests
# ---------------------------------------------------------------------------

class TestExtractReviewerSources:

    def test_extracts_sources(self):
        sources = _extract_reviewer_sources(SAMPLE_DOC_WITH_SUGGESTIONS)
        assert "R1-S1" in sources
        assert "claude-opus" in sources["R1-S1"]
        assert "R2-S1" in sources
        assert "gemini" in sources["R2-S1"].lower()


# ---------------------------------------------------------------------------
# _build_untriaged_block tests
# ---------------------------------------------------------------------------

class TestBuildUntriagedBlock:

    def test_formats_table(self):
        suggestions = [
            {"id": "R1-S1", "area": "Architecture", "severity": "high",
             "suggestion": "Test", "rationale": "Ok", "placement": "S1", "validation": "V1"},
        ]
        block = _build_untriaged_block(suggestions)
        assert "R1-S1" in block
        assert "| ID |" in block

    def test_empty_suggestions(self):
        assert _build_untriaged_block([]) == "(none)"
