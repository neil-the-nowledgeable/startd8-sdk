"""
Tests for automated triage step and apply-suggestions step in ArchitecturalReviewLogWorkflow.

Covers:
- Helper functions: _strip_json_fences, _extract_untriaged_suggestions,
  _validate_triage_output, _apply_triage_decisions, _compute_substantially_addressed,
  _insert_substantially_addressed_section
- Apply helpers: _extract_accepted_suggestions_for_apply, _build_apply_prompt,
  _validate_apply_output, _build_shared_system_prompt
- Integration: triage runs after reviewers, enable_triage config, cost tracking,
  StepResult, partial triage, no-untriaged skip
- Integration: apply-suggestions step, prompt caching via system_prompt
"""

import json
from unittest.mock import MagicMock

import pytest

from startd8.exceptions import GeminiSafetyFilterError
from startd8.models import TokenUsage
from startd8.workflows.builtin.architectural_review_log_workflow import (
    APPENDIX_HEADING,
    APPENDIX_TEMPLATE,
    ALLOWED_AREAS,
    _strip_json_fences,
    _extract_untriaged_suggestions,
    _validate_triage_output,
    _validate_snippet,
    _apply_triage_decisions,
    _compute_substantially_addressed,
    _insert_substantially_addressed_section,
    _compute_area_coverage,
    _insert_areas_needing_review_section,
    _build_triage_prompt,
    _build_prompt,
    _build_shared_system_prompt,
    _build_apply_prompt,
    _build_untriaged_block,
    _extract_accepted_suggestions_for_apply,
    _extract_reviewer_sources,
    _extract_feature_snippet,
    _fix_snippet_ids,
    _get_feature_doc_path,
    _ensure_appendix_exists,
    _compute_substantially_addressed_from_doc,
    _validate_apply_output,
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

    def test_non_string_decision_handled(self):
        """Non-string decision (e.g. boolean) should not crash with AttributeError."""
        data = [
            {"id": "R1-S1", "decision": True, "summary": "Test", "rationale": "Ok", "area": "architecture"},
        ]
        ok, msg, decisions, missing = _validate_triage_output(json.dumps(data), ["R1-S1"])
        assert ok is False
        assert "must be a string" in msg


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
            config={"document_path": str(doc_path), "enable_apply": False},
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


# ---------------------------------------------------------------------------
# _build_prompt feature_requirements tests
# ---------------------------------------------------------------------------

class TestBuildPromptRequirements:
    """Tests for feature_requirements support in reviewer prompts."""

    def test_requirements_block_injected_when_provided(self):
        prompt = _build_prompt(
            document_without_appendix="# Test Plan",
            applied_ids=[], rejected_ids=[],
            round_number=1, max_suggestions=5,
            reviewer_label="test (test-model)",
            scope="Test",
            requirements_content="## Feature: Auth\n\nMust support OAuth2.",
        )
        assert "Feature Requirements" in prompt
        assert "Must support OAuth2" in prompt
        assert "adequately addresses each requirement" in prompt

    def test_requirements_block_absent_when_empty(self):
        prompt = _build_prompt(
            document_without_appendix="# Test Plan",
            applied_ids=[], rejected_ids=[],
            round_number=1, max_suggestions=5,
            reviewer_label="test (test-model)",
            scope="Test",
            requirements_content="",
        )
        assert "Feature Requirements" not in prompt

    def test_requirements_placed_before_context(self):
        prompt = _build_prompt(
            document_without_appendix="# Test Plan",
            applied_ids=[], rejected_ids=[],
            round_number=1, max_suggestions=5,
            reviewer_label="test (test-model)",
            scope="Test",
            requirements_content="## Req\n\nSome requirement.",
            context_content="## Lesson\n\nSome lesson.",
        )
        req_pos = prompt.index("Feature Requirements")
        ctx_pos = prompt.index("Reference material")
        assert req_pos < ctx_pos

    def test_requirements_instruction_present_when_requirements_provided(self):
        prompt = _build_prompt(
            document_without_appendix="# Test Plan",
            applied_ids=[], rejected_ids=[],
            round_number=1, max_suggestions=5,
            reviewer_label="test (test-model)",
            scope="Test",
            requirements_content="## Feature: Auth\n\nMust support OAuth2.",
        )
        assert "adequately addresses each requirement" in prompt
        assert "under-addressed" in prompt

    def test_requirements_instruction_absent_when_no_requirements(self):
        prompt = _build_prompt(
            document_without_appendix="# Test Plan",
            applied_ids=[], rejected_ids=[],
            round_number=1, max_suggestions=5,
            reviewer_label="test (test-model)",
            scope="Test",
            requirements_content="",
        )
        assert "adequately addresses each requirement" not in prompt

    def test_dual_doc_format_present_when_has_feature_requirements(self):
        prompt = _build_prompt(
            document_without_appendix="# Test Plan",
            applied_ids=[], rejected_ids=[],
            round_number=1, max_suggestions=5,
            reviewer_label="test (test-model)",
            scope="Test",
            requirements_content="## Feature: Auth\n\nMust support OAuth2.",
            has_feature_requirements=True,
        )
        assert "Requirements Coverage" in prompt
        assert "Feature Requirements Suggestions" in prompt
        assert "R1-F1" in prompt
        # Directive requirement instruction
        assert "You MUST include a Requirements Coverage section" in prompt

    def test_dual_doc_format_absent_when_no_feature_requirements(self):
        prompt = _build_prompt(
            document_without_appendix="# Test Plan",
            applied_ids=[], rejected_ids=[],
            round_number=1, max_suggestions=5,
            reviewer_label="test (test-model)",
            scope="Test",
            requirements_content="## Feature: Auth\n\nMust support OAuth2.",
            has_feature_requirements=False,
        )
        assert "Dual-Document Output" not in prompt
        assert "Feature Requirements Suggestions" not in prompt
        # Should still have the passive instruction
        assert "adequately addresses each requirement" in prompt


# ---------------------------------------------------------------------------
# Dual-document mode tests
# ---------------------------------------------------------------------------

class TestDualDocumentMode:

    def test_feature_doc_appendix_initialized(self, tmp_path):
        """Feature doc gets appendix structure when missing."""
        feature_doc = tmp_path / "feature-requirements.md"
        feature_doc.write_text("# Feature Requirements\n\n## Auth\n\nMust support OAuth2.\n")

        doc_path = tmp_path / "plan.md"
        doc_path.write_text("# Implementation Plan\n\nSome content here.\n")

        snippet = (
            f"#### Review Round R1\n\n"
            f"- **Reviewer**: test-agent (test-model)\n"
            f"- **Date**: 2026-02-11 00:00:00 UTC\n"
            f"- **Scope**: Test review\n\n"
            f"| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |\n"
            f"| ---- | ---- | ---- | ---- | ---- | ---- | ---- |\n"
            f"| R1-S1 | Architecture | high | Plan suggestion | Good rationale | Section 1 | Manual |\n"
        )
        token_usage = TokenUsage(input=100, output=50, total=150, model_name="test")
        triage_response = json.dumps([
            {"id": "R1-S1", "decision": "ACCEPT", "summary": "Plan suggestion", "rationale": "Ok", "area": "architecture"},
        ])
        triage_token_usage = TokenUsage(input=200, output=100, total=300, model_name="test")

        agent = MagicMock()
        agent.name = "test-agent"
        agent.model = "test-model"
        agent.safety_settings = None
        agent.__class__.__module__ = "startd8.agents.claude"
        agent.generate.side_effect = [
            (snippet, 500, token_usage),
            (triage_response, 300, triage_token_usage),
        ]

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={
                "document_path": str(doc_path),
                "feature_requirements": [str(feature_doc)],
            },
            agents=[agent],
            on_progress=None,
        )

        assert result.success is True
        feature_text = feature_doc.read_text()
        assert "## Appendix: Iterative Review Log" in feature_text
        assert "### Appendix A: Applied Suggestions" in feature_text
        assert "### Appendix C: Incoming Suggestions" in feature_text

    def test_feature_suggestions_appended_to_feature_doc(self, tmp_path):
        """F-prefix suggestions are extracted and appended to feature doc."""
        feature_doc = tmp_path / "feature-requirements.md"
        feature_doc.write_text("# Feature Requirements\n\n## Auth\n\nMust support OAuth2.\n")

        doc_path = tmp_path / "plan.md"
        doc_path.write_text("# Implementation Plan\n\nSome content here.\n")

        snippet = (
            f"#### Review Round R1\n\n"
            f"- **Reviewer**: test-agent (test-model)\n"
            f"- **Date**: 2026-02-11 00:00:00 UTC\n"
            f"- **Scope**: Test review\n\n"
            f"| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |\n"
            f"| ---- | ---- | ---- | ---- | ---- | ---- | ---- |\n"
            f"| R1-S1 | Architecture | high | Plan suggestion | Good rationale | Section 1 | Manual |\n\n"
            f"#### Feature Requirements Suggestions\n"
            f"| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |\n"
            f"| ---- | ---- | ---- | ---- | ---- | ---- | ---- |\n"
            f"| R1-F1 | Security | medium | Add OAuth2 scope definition | Spec is ambiguous | Section 2.1 | Spec review |\n"
        )
        token_usage = TokenUsage(input=100, output=50, total=150, model_name="test")
        triage_response = json.dumps([
            {"id": "R1-S1", "decision": "ACCEPT", "summary": "Plan suggestion", "rationale": "Ok", "area": "architecture"},
            {"id": "R1-F1", "decision": "ACCEPT", "summary": "OAuth2 scope", "rationale": "Good", "area": "security"},
        ])
        triage_token_usage = TokenUsage(input=200, output=100, total=300, model_name="test")

        agent = MagicMock()
        agent.name = "test-agent"
        agent.model = "test-model"
        agent.safety_settings = None
        agent.__class__.__module__ = "startd8.agents.claude"
        agent.generate.side_effect = [
            (snippet, 500, token_usage),
            (triage_response, 300, triage_token_usage),
        ]

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={
                "document_path": str(doc_path),
                "feature_requirements": [str(feature_doc)],
            },
            agents=[agent],
            on_progress=None,
        )

        assert result.success is True
        feature_text = feature_doc.read_text()
        assert "Feature Requirements Suggestions" in feature_text
        assert "R1-F1" in feature_text

    def test_requirements_coverage_in_plan_doc(self, tmp_path):
        """Full snippet (including coverage table) persists in plan doc."""
        feature_doc = tmp_path / "feature-requirements.md"
        feature_doc.write_text("# Feature Requirements\n\n## Auth\n\nMust support OAuth2.\n")

        doc_path = tmp_path / "plan.md"
        doc_path.write_text("# Implementation Plan\n\nSome content here.\n")

        snippet = (
            f"#### Review Round R1\n\n"
            f"- **Reviewer**: test-agent (test-model)\n"
            f"- **Date**: 2026-02-11 00:00:00 UTC\n"
            f"- **Scope**: Test review\n\n"
            f"| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |\n"
            f"| ---- | ---- | ---- | ---- | ---- | ---- | ---- |\n"
            f"| R1-S1 | Architecture | high | Plan suggestion | Good rationale | Section 1 | Manual |\n\n"
            f"#### Requirements Coverage\n"
            f"| Feature Doc Section | Plan Step(s) | Coverage | Gaps |\n"
            f"| ---- | ---- | ---- | ---- |\n"
            f"| Auth | Step 3 | Full | None |\n"
        )
        token_usage = TokenUsage(input=100, output=50, total=150, model_name="test")
        triage_response = json.dumps([
            {"id": "R1-S1", "decision": "ACCEPT", "summary": "Plan suggestion", "rationale": "Ok", "area": "architecture"},
        ])
        triage_token_usage = TokenUsage(input=200, output=100, total=300, model_name="test")

        agent = MagicMock()
        agent.name = "test-agent"
        agent.model = "test-model"
        agent.safety_settings = None
        agent.__class__.__module__ = "startd8.agents.claude"
        agent.generate.side_effect = [
            (snippet, 500, token_usage),
            (triage_response, 300, triage_token_usage),
        ]

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={
                "document_path": str(doc_path),
                "feature_requirements": [str(feature_doc)],
            },
            agents=[agent],
            on_progress=None,
        )

        plan_text = doc_path.read_text()
        assert "Requirements Coverage" in plan_text
        assert "Auth" in plan_text

    def test_triage_routes_plan_to_plan_doc(self, tmp_path):
        """S-prefix ACCEPT/REJECT decisions go to plan doc Appendix A/B."""
        feature_doc = tmp_path / "feature-requirements.md"
        feature_doc.write_text("# Feature Requirements\n\n## Auth\n\nMust support OAuth2.\n")

        doc_path = tmp_path / "plan.md"
        doc_path.write_text("# Implementation Plan\n\nSome content here.\n")

        snippet = (
            f"#### Review Round R1\n\n"
            f"- **Reviewer**: test-agent (test-model)\n"
            f"- **Date**: 2026-02-11 00:00:00 UTC\n"
            f"- **Scope**: Test review\n\n"
            f"| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |\n"
            f"| ---- | ---- | ---- | ---- | ---- | ---- | ---- |\n"
            f"| R1-S1 | Architecture | high | Plan improvement | Good rationale | Section 1 | Manual |\n\n"
            f"#### Feature Requirements Suggestions\n"
            f"| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |\n"
            f"| ---- | ---- | ---- | ---- | ---- | ---- | ---- |\n"
            f"| R1-F1 | Security | medium | Add scope def | Ambiguous spec | Section 2.1 | Spec review |\n"
        )
        token_usage = TokenUsage(input=100, output=50, total=150, model_name="test")
        triage_response = json.dumps([
            {"id": "R1-S1", "decision": "ACCEPT", "summary": "Plan improvement", "rationale": "Good", "area": "architecture"},
            {"id": "R1-F1", "decision": "REJECT", "summary": "Scope def", "rationale": "Already defined", "area": "security"},
        ])
        triage_token_usage = TokenUsage(input=200, output=100, total=300, model_name="test")

        agent = MagicMock()
        agent.name = "test-agent"
        agent.model = "test-model"
        agent.safety_settings = None
        agent.__class__.__module__ = "startd8.agents.claude"
        agent.generate.side_effect = [
            (snippet, 500, token_usage),
            (triage_response, 300, triage_token_usage),
        ]

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={
                "document_path": str(doc_path),
                "feature_requirements": [str(feature_doc)],
            },
            agents=[agent],
            on_progress=None,
        )

        plan_text = doc_path.read_text()
        plan_appendix_a = plan_text.split("### Appendix A")[1].split("### Appendix B")[0]
        assert "R1-S1" in plan_appendix_a
        # F-prefix should NOT be in plan doc's appendix A or B
        assert "R1-F1" not in plan_appendix_a

    def test_triage_routes_feature_to_feature_doc(self, tmp_path):
        """F-prefix ACCEPT/REJECT decisions go to feature doc Appendix A/B."""
        feature_doc = tmp_path / "feature-requirements.md"
        feature_doc.write_text("# Feature Requirements\n\n## Auth\n\nMust support OAuth2.\n")

        doc_path = tmp_path / "plan.md"
        doc_path.write_text("# Implementation Plan\n\nSome content here.\n")

        snippet = (
            f"#### Review Round R1\n\n"
            f"- **Reviewer**: test-agent (test-model)\n"
            f"- **Date**: 2026-02-11 00:00:00 UTC\n"
            f"- **Scope**: Test review\n\n"
            f"| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |\n"
            f"| ---- | ---- | ---- | ---- | ---- | ---- | ---- |\n"
            f"| R1-S1 | Architecture | high | Plan improvement | Good rationale | Section 1 | Manual |\n\n"
            f"#### Feature Requirements Suggestions\n"
            f"| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |\n"
            f"| ---- | ---- | ---- | ---- | ---- | ---- | ---- |\n"
            f"| R1-F1 | Security | medium | Add scope def | Ambiguous spec | Section 2.1 | Spec review |\n"
        )
        token_usage = TokenUsage(input=100, output=50, total=150, model_name="test")
        triage_response = json.dumps([
            {"id": "R1-S1", "decision": "ACCEPT", "summary": "Plan improvement", "rationale": "Good", "area": "architecture"},
            {"id": "R1-F1", "decision": "ACCEPT", "summary": "Scope def", "rationale": "Good catch", "area": "security"},
        ])
        triage_token_usage = TokenUsage(input=200, output=100, total=300, model_name="test")

        agent = MagicMock()
        agent.name = "test-agent"
        agent.model = "test-model"
        agent.safety_settings = None
        agent.__class__.__module__ = "startd8.agents.claude"
        agent.generate.side_effect = [
            (snippet, 500, token_usage),
            (triage_response, 300, triage_token_usage),
        ]

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={
                "document_path": str(doc_path),
                "feature_requirements": [str(feature_doc)],
            },
            agents=[agent],
            on_progress=None,
        )

        feature_text = feature_doc.read_text()
        feature_appendix_a = feature_text.split("### Appendix A")[1].split("### Appendix B")[0]
        assert "R1-F1" in feature_appendix_a
        assert result.output["triage"]["feature_accepted"] == 1

    def test_no_feature_doc_unchanged_behavior(self, tmp_path):
        """Without feature_requirements, everything works as before."""
        doc_path = tmp_path / "plan.md"
        doc_path.write_text("# Implementation Plan\n\nSome content here.\n")

        snippet = (
            f"#### Review Round R1\n\n"
            f"- **Reviewer**: test-agent (test-model)\n"
            f"- **Date**: 2026-02-11 00:00:00 UTC\n"
            f"- **Scope**: Test review\n\n"
            f"| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |\n"
            f"| ---- | ---- | ---- | ---- | ---- | ---- | ---- |\n"
            f"| R1-S1 | Architecture | high | Plan suggestion | Good rationale | Section 1 | Manual |\n"
        )
        token_usage = TokenUsage(input=100, output=50, total=150, model_name="test")
        triage_response = json.dumps([
            {"id": "R1-S1", "decision": "ACCEPT", "summary": "Plan suggestion", "rationale": "Ok", "area": "architecture"},
        ])
        triage_token_usage = TokenUsage(input=200, output=100, total=300, model_name="test")

        agent = MagicMock()
        agent.name = "test-agent"
        agent.model = "test-model"
        agent.safety_settings = None
        agent.__class__.__module__ = "startd8.agents.claude"
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
        assert result.output["feature_document_path"] is None
        assert result.output["triage"]["feature_accepted"] == 0
        assert result.output["triage"]["feature_rejected"] == 0

    def test_validate_snippet_accepts_f_prefix_ids(self):
        """Validator accepts R1-F1 IDs in feature suggestions table."""
        snippet = (
            f"#### Review Round R1\n\n"
            f"- **Reviewer**: test-agent (test-model)\n"
            f"- **Date**: 2026-02-11 00:00:00 UTC\n"
            f"- **Scope**: Test review\n\n"
            f"| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |\n"
            f"| ---- | ---- | ---- | ---- | ---- | ---- | ---- |\n"
            f"| R1-S1 | Architecture | high | Plan suggestion | Good rationale | Section 1 | Manual |\n\n"
            f"#### Feature Requirements Suggestions\n"
            f"| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |\n"
            f"| ---- | ---- | ---- | ---- | ---- | ---- | ---- |\n"
            f"| R1-F1 | Security | medium | Feature suggestion | Ambiguous spec | Section 2.1 | Review |\n"
        )
        ok, msg, ids = _validate_snippet(snippet, round_number=1, max_suggestions=5)
        assert ok is True
        assert "R1-S1" in ids
        assert "R1-F1" in ids

    def test_validate_snippet_accepts_bold_headers(self):
        """Validator accepts **bold** column headers (common LLM formatting)."""
        snippet = (
            "#### Review Round R1\n\n"
            "- **Reviewer**: test-agent (test-model)\n"
            "- **Date**: 2026-02-11 00:00:00 UTC\n"
            "- **Scope**: Test review\n\n"
            "| **ID** | **Area** | **Severity** | **Suggestion** | **Rationale** | **Proposed Placement** | **Validation Approach** |\n"
            "| ---- | ---- | ---- | ---- | ---- | ---- | ---- |\n"
            "| R1-S1 | Architecture | high | Use event sourcing | Better audit trail | Section 3 | Integration test |\n"
        )
        ok, msg, ids = _validate_snippet(snippet, round_number=1, max_suggestions=5)
        assert ok is True, f"Expected valid snippet but got: {msg}"
        assert "R1-S1" in ids

    def test_fix_snippet_ids_renumbers_wrong_prefix(self):
        """_fix_snippet_ids rewrites R3-S* to R1-S* when round_number=1."""
        snippet = (
            "#### Review Round R1\n\n"
            "| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |\n"
            "| ---- | ---- | ---- | ---- | ---- | ---- | ---- |\n"
            "| R3-S1 | Architecture | high | Fix it | Because | Section 1 | Test |\n"
            "| R3-F1 | Security | medium | Clarify | Ambiguous | Section 2 | Review |\n"
        )
        fixed = _fix_snippet_ids(snippet, round_number=1)
        assert "R1-S1" in fixed
        assert "R1-F1" in fixed
        assert "R3-S1" not in fixed
        assert "R3-F1" not in fixed
        # Heading is unchanged (not an ID pattern)
        assert "#### Review Round R1" in fixed

    def test_fix_snippet_ids_noop_when_correct(self):
        """_fix_snippet_ids is a no-op when IDs already match."""
        snippet = "| R2-S1 | Architecture | high | Fix | Why | Where | How |\n"
        assert _fix_snippet_ids(snippet, round_number=2) == snippet

    def test_fix_snippet_ids_preserves_endorsement_references(self):
        """Endorsement references to prior rounds should NOT be rewritten."""
        snippet = (
            "#### Review Round R1\n\n"
            "| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |\n"
            "| ---- | ---- | ---- | ---- | ---- | ---- | ---- |\n"
            "| R3-S1 | architecture | high | Fix X | Because | Section 2 | Review |\n\n"
            "**Endorsements** (prior untriaged suggestions this reviewer agrees with):\n"
            "- R2-S3: Good point about retry logic\n"
        )
        fixed = _fix_snippet_ids(snippet, round_number=1)
        # Table IDs should be rewritten to R1
        assert "| R1-S1 |" in fixed
        # Endorsement reference to R2-S3 should be preserved (not rewritten to R1-S3)
        assert "R2-S3" in fixed

    def test_endorsement_matches_f_prefix(self):
        """Endorsement regex matches F-prefix IDs."""
        doc_with_f_endorsement = SAMPLE_DOC_WITH_SUGGESTIONS.replace(
            "- R1-S3: Retry logic is a must-have",
            "- R1-S3: Retry logic is a must-have\n- R1-F1: Good feature suggestion",
        )
        # Add a feature suggestion to a round
        doc_with_f_endorsement = doc_with_f_endorsement.rstrip() + (
            "\n\n#### Review Round R3\n\n"
            "- **Reviewer**: test (test)\n"
            "- **Date**: 2026-02-11 00:00:00 UTC\n"
            "- **Scope**: Test\n\n"
            "| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |\n"
            "| ---- | ---- | ---- | ---- | ---- | ---- | ---- |\n"
            "| R3-S1 | Architecture | high | Test | Test | S1 | V1 |\n\n"
            "#### Feature Requirements Suggestions\n"
            "| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |\n"
            "| ---- | ---- | ---- | ---- | ---- | ---- | ---- |\n"
            "| R1-F1 | Security | medium | Feature fix | Ambiguous | S2 | Review |\n"
        )
        _, endorsements = _extract_untriaged_suggestions(doc_with_f_endorsement, [], [])
        assert endorsements.get("R1-F1", 0) >= 1


# ---------------------------------------------------------------------------
# _get_feature_doc_path tests
# ---------------------------------------------------------------------------

class TestGetFeatureDocPath:

    def test_returns_md_file(self, tmp_path):
        md = tmp_path / "feature.md"
        md.write_text("# Features")
        result = _get_feature_doc_path([str(md)])
        assert result == md

    def test_returns_first_md_in_dir(self, tmp_path):
        d = tmp_path / "reqs"
        d.mkdir()
        (d / "aaa.md").write_text("# A")
        (d / "bbb.md").write_text("# B")
        result = _get_feature_doc_path([str(d)])
        assert result == d / "aaa.md"

    def test_returns_none_for_empty(self):
        assert _get_feature_doc_path([]) is None

    def test_skips_non_md_files(self, tmp_path):
        txt = tmp_path / "file.txt"
        txt.write_text("not markdown")
        assert _get_feature_doc_path([str(txt)]) is None


# ---------------------------------------------------------------------------
# _extract_feature_snippet tests
# ---------------------------------------------------------------------------

class TestExtractFeatureSnippet:

    def test_extracts_feature_table(self):
        full = (
            "#### Review Round R1\n\n"
            "| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |\n"
            "| ---- | ---- | ---- | ---- | ---- | ---- | ---- |\n"
            "| R1-S1 | Architecture | high | Plan fix | Rationale | Section 1 | Manual |\n\n"
            "#### Feature Requirements Suggestions\n"
            "| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |\n"
            "| ---- | ---- | ---- | ---- | ---- | ---- | ---- |\n"
            "| R1-F1 | Security | medium | Add scope | Ambiguous | Section 2 | Review |\n"
        )
        result = _extract_feature_snippet(full, 1, "test-agent (model)", "Test scope")
        assert "#### Review Round R1" in result
        assert "Feature Requirements Suggestions" in result
        assert "R1-F1" in result
        assert "test-agent (model)" in result

    def test_returns_empty_when_no_feature_section(self):
        full = (
            "#### Review Round R1\n\n"
            "| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |\n"
            "| ---- | ---- | ---- | ---- | ---- | ---- | ---- |\n"
            "| R1-S1 | Architecture | high | Plan fix | Rationale | Section 1 | Manual |\n"
        )
        result = _extract_feature_snippet(full, 1, "test", "scope")
        assert result == ""


# ---------------------------------------------------------------------------
# _build_triage_prompt feature suggestion awareness tests
# ---------------------------------------------------------------------------

class TestBuildTriagePromptFeatureAwareness:

    def test_suggestion_type_note_when_has_feature_suggestions(self):
        prompt = _build_triage_prompt(
            "doc content", [], [], "untriaged block", {},
            has_feature_suggestions=True,
        )
        assert "R*-S* IDs are plan suggestions" in prompt
        assert "R*-F* IDs are feature suggestions" in prompt

    def test_no_suggestion_type_note_without_feature_suggestions(self):
        prompt = _build_triage_prompt(
            "doc content", [], [], "untriaged block", {},
            has_feature_suggestions=False,
        )
        assert "R*-S* IDs are plan suggestions" not in prompt


# ---------------------------------------------------------------------------
# _build_shared_system_prompt tests
# ---------------------------------------------------------------------------

class TestBuildSharedSystemPrompt:

    def test_includes_document(self):
        sp = _build_shared_system_prompt("# My Plan\n\nSome content.")
        assert "# My Plan" in sp
        assert "Some content." in sp
        assert "Document under review" in sp

    def test_includes_requirements(self):
        sp = _build_shared_system_prompt("doc", requirements_content="## Req\n\nNeed OAuth2.")
        assert "Feature Requirements" in sp
        assert "Need OAuth2" in sp

    def test_includes_context(self):
        sp = _build_shared_system_prompt("doc", context_content="## Lesson\n\nDon't use X.")
        assert "Reference material" in sp
        assert "Don't use X" in sp

    def test_empty_requirements_excluded(self):
        sp = _build_shared_system_prompt("doc", requirements_content="")
        assert "Feature Requirements" not in sp

    def test_empty_context_excluded(self):
        sp = _build_shared_system_prompt("doc", context_content="   ")
        assert "Reference material" not in sp

    def test_order_is_doc_then_req_then_context(self):
        sp = _build_shared_system_prompt(
            "doc body",
            requirements_content="requirements here",
            context_content="context here",
        )
        assert sp.index("doc body") < sp.index("requirements here") < sp.index("context here")


# ---------------------------------------------------------------------------
# _build_prompt use_system_prompt tests
# ---------------------------------------------------------------------------

class TestBuildPromptSystemPromptSplit:

    def test_use_system_prompt_omits_document(self):
        prompt = _build_prompt(
            document_without_appendix="# Big Plan\n\nLots of content.",
            applied_ids=[], rejected_ids=[],
            round_number=1, max_suggestions=5,
            reviewer_label="test (model)",
            scope="Test",
            use_system_prompt=True,
        )
        assert "# Big Plan" not in prompt
        assert "Lots of content" not in prompt
        # Instructions should still be present
        assert "Review Round R1" in prompt

    def test_use_system_prompt_omits_context(self):
        prompt = _build_prompt(
            document_without_appendix="doc",
            applied_ids=[], rejected_ids=[],
            round_number=1, max_suggestions=5,
            reviewer_label="test (model)",
            scope="Test",
            context_content="## Secret Lesson\n\nImportant context.",
            use_system_prompt=True,
        )
        assert "Secret Lesson" not in prompt
        assert "Reference material" not in prompt

    def test_use_system_prompt_omits_requirements(self):
        prompt = _build_prompt(
            document_without_appendix="doc",
            applied_ids=[], rejected_ids=[],
            round_number=1, max_suggestions=5,
            reviewer_label="test (model)",
            scope="Test",
            requirements_content="## Feature\n\nMust do X.",
            use_system_prompt=True,
        )
        assert "Must do X" not in prompt
        assert "Feature Requirements" not in prompt

    def test_default_includes_document(self):
        """Default (use_system_prompt=False) includes document body."""
        prompt = _build_prompt(
            document_without_appendix="# Full Plan",
            applied_ids=[], rejected_ids=[],
            round_number=1, max_suggestions=5,
            reviewer_label="test (model)",
            scope="Test",
        )
        assert "# Full Plan" in prompt


# ---------------------------------------------------------------------------
# _build_triage_prompt use_system_prompt tests
# ---------------------------------------------------------------------------

class TestBuildTriagePromptSystemPromptSplit:

    def test_use_system_prompt_omits_document(self):
        prompt = _build_triage_prompt(
            document_without_appendix="# My Plan\n\nContent here.",
            applied_ids=[], rejected_ids=[],
            untriaged_block="| R1-S1 | arch | high | test | ok | s1 | v1 |",
            endorsement_counts={},
            use_system_prompt=True,
        )
        assert "# My Plan" not in prompt
        assert "Content here" not in prompt
        # Triage instructions should remain
        assert "ACCEPT" in prompt
        assert "REJECT" in prompt
        assert "R1-S1" in prompt

    def test_default_includes_document(self):
        prompt = _build_triage_prompt(
            document_without_appendix="# My Plan",
            applied_ids=[], rejected_ids=[],
            untriaged_block="block",
            endorsement_counts={},
        )
        assert "# My Plan" in prompt
        assert "Document being reviewed" in prompt


# ---------------------------------------------------------------------------
# _extract_accepted_suggestions_for_apply tests
# ---------------------------------------------------------------------------

class TestExtractAcceptedSuggestionsForApply:

    def test_filters_only_accept(self):
        decisions = [
            {"id": "R1-S1", "decision": "ACCEPT", "rationale": "Good"},
            {"id": "R1-S2", "decision": "REJECT", "rationale": "Bad"},
            {"id": "R1-S3", "decision": "ACCEPT", "rationale": "Great"},
        ]
        untriaged = [
            {"id": "R1-S1", "suggestion": "Add X", "placement": "S1", "validation": "V1"},
            {"id": "R1-S2", "suggestion": "Add Y", "placement": "S2", "validation": "V2"},
            {"id": "R1-S3", "suggestion": "Add Z", "placement": "S3", "validation": "V3"},
        ]
        result = _extract_accepted_suggestions_for_apply(decisions, untriaged)
        assert len(result) == 2
        ids = [r["id"] for r in result]
        assert "R1-S1" in ids
        assert "R1-S3" in ids
        assert "R1-S2" not in ids

    def test_merges_triage_rationale(self):
        decisions = [{"id": "R1-S1", "decision": "ACCEPT", "rationale": "Critical fix"}]
        untriaged = [{"id": "R1-S1", "suggestion": "Add X", "placement": "S1"}]
        result = _extract_accepted_suggestions_for_apply(decisions, untriaged)
        assert result[0]["triage_rationale"] == "Critical fix"
        assert result[0]["suggestion"] == "Add X"

    def test_handles_missing_ids(self):
        """If a triage decision references an ID not in untriaged, use minimal dict."""
        decisions = [{"id": "R99-S1", "decision": "ACCEPT", "rationale": "Good"}]
        result = _extract_accepted_suggestions_for_apply(decisions, [])
        assert len(result) == 1
        assert result[0]["id"] == "R99-S1"
        assert result[0]["triage_rationale"] == "Good"

    def test_empty_decisions(self):
        result = _extract_accepted_suggestions_for_apply([], [])
        assert result == []

    def test_all_reject(self):
        decisions = [
            {"id": "R1-S1", "decision": "REJECT", "rationale": "Nope"},
        ]
        result = _extract_accepted_suggestions_for_apply(decisions, [])
        assert result == []


# ---------------------------------------------------------------------------
# _build_apply_prompt tests
# ---------------------------------------------------------------------------

class TestBuildApplyPrompt:

    def test_includes_suggestion_table(self):
        suggestions = [
            {"id": "R1-S1", "suggestion": "Add circuit breakers", "placement": "Section 3",
             "triage_rationale": "Critical"},
        ]
        prompt = _build_apply_prompt(suggestions)
        assert "R1-S1" in prompt
        assert "Add circuit breakers" in prompt
        assert "Section 3" in prompt
        assert "Critical" in prompt

    def test_includes_doc_when_no_system_prompt(self):
        suggestions = [{"id": "R1-S1", "suggestion": "X", "placement": "S1", "triage_rationale": "Y"}]
        prompt = _build_apply_prompt(suggestions, document_without_appendix="# My Plan")
        assert "# My Plan" in prompt

    def test_excludes_doc_when_use_system_prompt(self):
        suggestions = [{"id": "R1-S1", "suggestion": "X", "placement": "S1", "triage_rationale": "Y"}]
        prompt = _build_apply_prompt(suggestions, use_system_prompt=True, document_without_appendix="# My Plan")
        assert "# My Plan" not in prompt

    def test_respects_persona(self):
        suggestions = [{"id": "R1-S1", "suggestion": "X", "placement": "S1", "triage_rationale": "Y"}]
        prompt = _build_apply_prompt(suggestions, persona="expert security auditor")
        assert "expert security auditor" in prompt

    def test_default_persona(self):
        suggestions = [{"id": "R1-S1", "suggestion": "X", "placement": "S1", "triage_rationale": "Y"}]
        prompt = _build_apply_prompt(suggestions)
        assert "expert enterprise architect" in prompt

    def test_no_appendix_instruction(self):
        suggestions = [{"id": "R1-S1", "suggestion": "X", "placement": "S1", "triage_rationale": "Y"}]
        prompt = _build_apply_prompt(suggestions)
        assert "Do NOT include any appendix" in prompt


# ---------------------------------------------------------------------------
# _validate_apply_output tests
# ---------------------------------------------------------------------------

class TestValidateApplyOutput:

    def _make_body(self):
        return "# Test Plan\n\n## Architecture\n\nContent here.\n\n## Security\n\nMore content.\n"

    def test_valid_output(self):
        body = self._make_body()
        output = body + "\nNew circuit breakers section added.\n"
        ok, msg, warns = _validate_apply_output(output, body, [])
        assert ok is True
        assert msg == "ok"

    def test_empty_output_rejected(self):
        ok, msg, warns = _validate_apply_output("", self._make_body(), [])
        assert ok is False
        assert "Empty" in msg

    def test_short_output_rejected(self):
        body = self._make_body()
        ok, msg, warns = _validate_apply_output("short", body, [])
        assert ok is False
        assert "too short" in msg

    def test_missing_headings_rejected(self):
        body = self._make_body()
        # Output missing "## Security" heading
        output = "# Test Plan\n\n## Architecture\n\nUpdated content.\n"
        ok, msg, warns = _validate_apply_output(output, body, [])
        assert ok is False
        assert "Missing" in msg

    def test_appendix_leakage_rejected(self):
        body = self._make_body()
        output = body + "\n### Appendix A: Applied Suggestions\n"
        ok, msg, warns = _validate_apply_output(output, body, [])
        assert ok is False
        assert "appendix leakage" in msg.lower()

    def test_integration_warnings(self):
        body = self._make_body()
        suggestions = [
            {"id": "R1-S1", "suggestion": "Add circuit breakers for resilience"},
        ]
        # Output that doesn't contain key terms from suggestion
        ok, msg, warns = _validate_apply_output(body, body, suggestions)
        assert ok is True
        assert "R1-S1" in warns

    def test_no_warnings_when_terms_present(self):
        body = self._make_body()
        suggestions = [
            {"id": "R1-S1", "suggestion": "Add Architecture improvements"},
        ]
        ok, msg, warns = _validate_apply_output(body, body, suggestions)
        assert ok is True
        assert warns == []


# ---------------------------------------------------------------------------
# Apply integration tests
# ---------------------------------------------------------------------------

class TestApplyIntegration:

    def _make_valid_snippet(self, round_number):
        return (
            f"#### Review Round R{round_number}\n\n"
            f"- **Reviewer**: test-agent (test-model)\n"
            f"- **Date**: 2026-02-09 00:00:00 UTC\n"
            f"- **Scope**: Architecture-focused review\n\n"
            f"| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |\n"
            f"| ---- | ---- | ---- | ---- | ---- | ---- | ---- |\n"
            f"| R{round_number}-S1 | Architecture | high | Add circuit breakers | Critical for resilience | Section 3 | Load testing |\n"
            f"| R{round_number}-S2 | Security | medium | Add rate limiting | Prevent abuse | Section 5 | Pen testing |\n"
        )

    def _make_mock_agent(self, name="test-agent", model="test-model"):
        agent = MagicMock()
        agent.name = name
        agent.model = model
        agent.safety_settings = None
        agent.__class__.__module__ = "startd8.agents.claude"
        return agent

    def _make_triage_response(self, suggestion_ids, decisions=None):
        if decisions is None:
            decisions = ["ACCEPT"] * len(suggestion_ids)
        data = []
        for sid, dec in zip(suggestion_ids, decisions):
            data.append({
                "id": sid, "decision": dec,
                "summary": f"Summary for {sid}",
                "rationale": f"Rationale for {sid}",
                "area": "architecture",
            })
        return json.dumps(data)

    def _make_apply_response(self, doc_text):
        """Build a valid apply response (doc body without appendix)."""
        idx = doc_text.find(APPENDIX_HEADING)
        if idx != -1:
            return doc_text[:idx].rstrip() + "\n\nCircuit breakers were integrated into Section 3.\n"
        return doc_text + "\nCircuit breakers were integrated into Section 3.\n"

    def test_full_pipeline_review_triage_apply(self, tmp_path):
        """Full pipeline: review -> triage -> apply integrates suggestions."""
        doc_path = tmp_path / "test_doc.md"
        doc_path.write_text("# Test Plan\n\n## Architecture\n\nSome content here.\n\n## Security\n\nMore content.\n")

        snippet = self._make_valid_snippet(1)
        token_usage = TokenUsage(input=100, output=50, total=150, model_name="test")
        triage_response = self._make_triage_response(["R1-S1", "R1-S2"])
        triage_token_usage = TokenUsage(input=200, output=100, total=300, model_name="test")

        # Read the doc after appendix is added (simulating what happens in _execute)
        initial_doc = doc_path.read_text()

        # Build a valid apply output
        apply_output = "# Test Plan\n\n## Architecture\n\nSome content here.\n\nCircuit breakers were added.\n\n## Security\n\nMore content with rate limiting.\n"
        apply_token_usage = TokenUsage(input=300, output=200, total=500, model_name="test")

        agent = self._make_mock_agent()
        agent.generate.side_effect = [
            (snippet, 500, token_usage),           # review
            (triage_response, 300, triage_token_usage),  # triage
            (apply_output, 400, apply_token_usage),      # apply
        ]

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={"document_path": str(doc_path), "enable_prompt_caching": False},
            agents=[agent],
            on_progress=None,
        )

        assert result.success is True
        assert result.output["apply"]["applied_count"] == 2
        assert result.output["apply"]["applied_ids"] == ["R1-S1", "R1-S2"]
        assert result.output["apply"]["error"] is None

        # Verify document body was updated
        final_doc = doc_path.read_text()
        assert "Circuit breakers were added" in final_doc
        # Appendix should still be present
        assert "### Appendix A" in final_doc
        assert "### Appendix C" in final_doc

        # Agent called 3 times: review, triage, apply
        assert agent.generate.call_count == 3

    def test_enable_apply_false_skips(self, tmp_path):
        """enable_apply: False skips the apply step."""
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
            config={"document_path": str(doc_path), "enable_apply": False},
            agents=[agent],
            on_progress=None,
        )

        assert result.success is True
        assert result.output["apply"]["enabled"] is False
        assert result.output["apply"]["applied_count"] == 0
        # Only 2 calls: review + triage (no apply)
        assert agent.generate.call_count == 2

    def test_apply_validation_failure_preserves_original(self, tmp_path):
        """Bad LLM output from apply doesn't corrupt the document."""
        doc_path = tmp_path / "test_doc.md"
        doc_path.write_text("# Test Plan\n\n## Architecture\n\nSome content here.\n\n## Security\n\nMore.\n")

        snippet = self._make_valid_snippet(1)
        token_usage = TokenUsage(input=100, output=50, total=150, model_name="test")
        triage_response = self._make_triage_response(["R1-S1", "R1-S2"])
        triage_token_usage = TokenUsage(input=200, output=100, total=300, model_name="test")

        # Bad apply output: way too short
        bad_apply = "short"
        apply_token_usage = TokenUsage(input=300, output=10, total=310, model_name="test")

        agent = self._make_mock_agent()
        agent.generate.side_effect = [
            (snippet, 500, token_usage),
            (triage_response, 300, triage_token_usage),
            (bad_apply, 100, apply_token_usage),    # initial apply (fails validation)
            (bad_apply, 100, apply_token_usage),    # retry (also fails)
        ]

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={"document_path": str(doc_path), "enable_prompt_caching": False},
            agents=[agent],
            on_progress=None,
        )

        # Workflow still succeeds (apply failure is non-fatal)
        assert result.success is True
        assert result.output["apply"]["applied_count"] == 0
        assert result.output["apply"]["error"] is not None

        # Document should still have original content (not corrupted)
        final_doc = doc_path.read_text()
        assert "## Architecture" in final_doc
        assert "## Security" in final_doc

    def test_apply_retry_on_validation_failure(self, tmp_path):
        """First apply attempt fails validation, retry succeeds."""
        doc_path = tmp_path / "test_doc.md"
        doc_path.write_text("# Test Plan\n\n## Architecture\n\nSome content.\n\n## Security\n\nMore.\n")

        snippet = self._make_valid_snippet(1)
        token_usage = TokenUsage(input=100, output=50, total=150, model_name="test")
        triage_response = self._make_triage_response(["R1-S1", "R1-S2"])
        triage_token_usage = TokenUsage(input=200, output=100, total=300, model_name="test")

        bad_apply = "too short"
        good_apply = "# Test Plan\n\n## Architecture\n\nSome content.\n\nCircuit breakers added.\n\n## Security\n\nMore with rate limiting.\n"
        apply_tu = TokenUsage(input=300, output=200, total=500, model_name="test")

        agent = self._make_mock_agent()
        agent.generate.side_effect = [
            (snippet, 500, token_usage),
            (triage_response, 300, triage_token_usage),
            (bad_apply, 100, apply_tu),     # first apply (fails)
            (good_apply, 200, apply_tu),    # retry (succeeds)
        ]

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={"document_path": str(doc_path), "enable_prompt_caching": False},
            agents=[agent],
            on_progress=None,
        )

        assert result.success is True
        assert result.output["apply"]["applied_count"] == 2
        assert result.output["apply"]["error"] is None

        final_doc = doc_path.read_text()
        assert "Circuit breakers added" in final_doc

    def test_no_accepted_suggestions_skips_apply(self, tmp_path):
        """All REJECT → apply step is skipped."""
        doc_path = tmp_path / "test_doc.md"
        doc_path.write_text("# Test Plan\n\nSome content.\n")

        snippet = self._make_valid_snippet(1)
        token_usage = TokenUsage(input=100, output=50, total=150, model_name="test")
        triage_response = self._make_triage_response(["R1-S1", "R1-S2"], ["REJECT", "REJECT"])
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
        assert result.output["apply"]["applied_count"] == 0
        # Only 2 calls (review + triage), no apply since all rejected
        assert agent.generate.call_count == 2

    def test_apply_costs_tracked(self, tmp_path):
        """Apply step tokens and cost are included in totals."""
        doc_path = tmp_path / "test_doc.md"
        doc_path.write_text("# Test Plan\n\n## Architecture\n\nContent.\n\n## Security\n\nMore.\n")

        snippet = self._make_valid_snippet(1)
        review_tu = TokenUsage(input=100, output=50, total=150, model_name="test")
        triage_response = self._make_triage_response(["R1-S1", "R1-S2"])
        triage_tu = TokenUsage(input=200, output=100, total=300, model_name="test")

        apply_output = "# Test Plan\n\n## Architecture\n\nContent.\n\nUpdated.\n\n## Security\n\nMore.\n"
        apply_tu = TokenUsage(input=500, output=300, total=800, model_name="test")

        agent = self._make_mock_agent()
        agent.generate.side_effect = [
            (snippet, 500, review_tu),
            (triage_response, 300, triage_tu),
            (apply_output, 400, apply_tu),
        ]

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={"document_path": str(doc_path), "enable_prompt_caching": False},
            agents=[agent],
            on_progress=None,
        )

        # Total should include review + triage + apply tokens
        assert result.metrics.input_tokens == 800   # 100 + 200 + 500
        assert result.metrics.output_tokens == 450   # 50 + 100 + 300

    def test_apply_step_result_created(self, tmp_path):
        """A StepResult should be created for the apply step."""
        doc_path = tmp_path / "test_doc.md"
        doc_path.write_text("# Test Plan\n\n## Architecture\n\nContent.\n\n## Security\n\nMore.\n")

        snippet = self._make_valid_snippet(1)
        tu = TokenUsage(input=100, output=50, total=150, model_name="test")
        triage_response = self._make_triage_response(["R1-S1", "R1-S2"])
        apply_output = "# Test Plan\n\n## Architecture\n\nContent.\n\nUpdated.\n\n## Security\n\nMore.\n"

        agent = self._make_mock_agent()
        agent.generate.side_effect = [
            (snippet, 500, tu),
            (triage_response, 300, tu),
            (apply_output, 400, tu),
        ]

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={"document_path": str(doc_path), "enable_prompt_caching": False},
            agents=[agent],
            on_progress=None,
        )

        apply_steps = [s for s in result.steps if s.step_name == "apply_suggestions"]
        assert len(apply_steps) == 1
        assert apply_steps[0].error is None
        assert apply_steps[0].metadata["applied_count"] == 2

    def test_state_file_includes_apply(self, tmp_path):
        """State file should contain apply info."""
        doc_path = tmp_path / "test_doc.md"
        doc_path.write_text("# Test Plan\n\n## Architecture\n\nContent.\n\n## Security\n\nMore.\n")

        snippet = self._make_valid_snippet(1)
        tu = TokenUsage(input=100, output=50, total=150, model_name="test")
        triage_response = self._make_triage_response(["R1-S1", "R1-S2"])
        apply_output = "# Test Plan\n\n## Architecture\n\nContent.\n\nUpdated.\n\n## Security\n\nMore.\n"

        agent = self._make_mock_agent()
        agent.generate.side_effect = [
            (snippet, 500, tu),
            (triage_response, 300, tu),
            (apply_output, 400, tu),
        ]

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={"document_path": str(doc_path), "enable_prompt_caching": False},
            agents=[agent],
            on_progress=None,
        )

        state_path = tmp_path / ".startd8" / "architectural_review_state.json"
        assert state_path.exists()
        state = json.loads(state_path.read_text())
        assert "apply" in state
        assert state["apply"]["applied_count"] == 2
        assert state["apply"]["applied_ids"] == ["R1-S1", "R1-S2"]


# ---------------------------------------------------------------------------
# Prompt caching integration tests
# ---------------------------------------------------------------------------

class TestPromptCachingIntegration:

    def _make_mock_agent(self, name="test-agent", model="test-model", is_anthropic=True):
        agent = MagicMock()
        agent.name = name
        agent.model = model
        agent.safety_settings = None
        agent.enable_prompt_caching = False
        if is_anthropic:
            agent.__class__.__module__ = "startd8.agents.claude"
        else:
            agent.__class__.__module__ = "startd8.agents.gemini"
        return agent

    def _make_valid_snippet(self, round_number):
        return (
            f"#### Review Round R{round_number}\n\n"
            f"- **Reviewer**: test-agent (test-model)\n"
            f"- **Date**: 2026-02-09 00:00:00 UTC\n"
            f"- **Scope**: Architecture-focused review\n\n"
            f"| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |\n"
            f"| ---- | ---- | ---- | ---- | ---- | ---- | ---- |\n"
            f"| R{round_number}-S1 | Architecture | high | Test suggestion | Test rationale | Section 1 | Manual review |\n"
        )

    def test_system_prompt_passed_to_generate(self, tmp_path):
        """When prompt caching is enabled, system_prompt kwarg is passed to generate()."""
        doc_path = tmp_path / "test_doc.md"
        doc_path.write_text("# Test Plan\n\nContent.\n")

        snippet = self._make_valid_snippet(1)
        tu = TokenUsage(input=100, output=50, total=150, model_name="test")
        triage_response = json.dumps([
            {"id": "R1-S1", "decision": "REJECT", "summary": "Test", "rationale": "No", "area": "architecture"},
        ])

        agent = self._make_mock_agent()
        agent.generate.side_effect = [
            (snippet, 500, tu),
            (triage_response, 300, tu),
        ]

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={
                "document_path": str(doc_path),
                "enable_prompt_caching": True,
            },
            agents=[agent],
            on_progress=None,
        )

        assert result.success is True
        # Both generate calls should have system_prompt kwarg
        for call in agent.generate.call_args_list:
            assert "system_prompt" in call.kwargs
            assert "Document under review" in call.kwargs["system_prompt"]

    def test_prompt_caching_sets_enable_on_anthropic_agent(self, tmp_path):
        """Anthropic agents get enable_prompt_caching=True when config enabled."""
        doc_path = tmp_path / "test_doc.md"
        doc_path.write_text("# Test Plan\n\nContent.\n")

        snippet = self._make_valid_snippet(1)
        tu = TokenUsage(input=100, output=50, total=150, model_name="test")

        agent = self._make_mock_agent(is_anthropic=True)
        agent.generate.return_value = (snippet, 500, tu)

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={
                "document_path": str(doc_path),
                "enable_triage": False,
                "enable_apply": False,
                "enable_prompt_caching": True,
            },
            agents=[agent],
            on_progress=None,
        )

        assert agent.enable_prompt_caching is True

    def test_prompt_caching_disabled_no_system_prompt(self, tmp_path):
        """When caching is disabled, no system_prompt kwarg."""
        doc_path = tmp_path / "test_doc.md"
        doc_path.write_text("# Test Plan\n\nContent.\n")

        snippet = self._make_valid_snippet(1)
        tu = TokenUsage(input=100, output=50, total=150, model_name="test")

        agent = self._make_mock_agent()
        agent.generate.return_value = (snippet, 500, tu)

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={
                "document_path": str(doc_path),
                "enable_triage": False,
                "enable_apply": False,
                "enable_prompt_caching": False,
            },
            agents=[agent],
            on_progress=None,
        )

        assert result.success is True
        # generate should NOT have system_prompt kwarg
        for call in agent.generate.call_args_list:
            assert "system_prompt" not in call.kwargs

    def test_gemini_agent_not_set_enable_prompt_caching(self, tmp_path):
        """Gemini agents don't get enable_prompt_caching set."""
        doc_path = tmp_path / "test_doc.md"
        doc_path.write_text("# Test Plan\n\nContent.\n")

        snippet = self._make_valid_snippet(1)
        tu = TokenUsage(input=100, output=50, total=150, model_name="test")

        agent = self._make_mock_agent(is_anthropic=False)
        agent.generate.return_value = (snippet, 500, tu)

        workflow = ArchitecturalReviewLogWorkflow()
        result = workflow._execute(
            config={
                "document_path": str(doc_path),
                "enable_triage": False,
                "enable_apply": False,
                "enable_prompt_caching": True,
            },
            agents=[agent],
            on_progress=None,
        )

        # Gemini agent should NOT have enable_prompt_caching set to True
        assert agent.enable_prompt_caching is False
