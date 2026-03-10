"""Tests for RV-9xx Structured Review Output (JSON-first review pipeline).

Covers:
- RV-901: Dual-format validator (_validate_json_review, _validate_review_output)
- RV-902: JSON-to-markdown renderer (_render_review_json_to_markdown)
- RV-903: YAML prompt produces valid JSON example
- RV-905: Retry prompt references JSON schema
"""

from __future__ import annotations

import json
import textwrap

import pytest

from startd8.workflows.builtin.architectural_review_log_helpers import (
    _validate_json_review,
    _validate_review_output,
    _render_review_json_to_markdown,
    _validate_snippet,
    _extract_untriaged_suggestions,
)
from startd8.workflows.builtin.architectural_review_log_constants import (
    ALLOWED_AREAS,
    ALLOWED_SEVERITIES,
    REQUIRED_COLUMNS,
)


# ---------------------------------------------------------------------------
# Fixtures — reusable JSON payloads
# ---------------------------------------------------------------------------

def _make_review_json(
    round_number: int = 1,
    suggestions: list | None = None,
    endorsements: list | None = None,
    **overrides,
) -> dict:
    """Build a review JSON payload for testing.

    Uses ``is None`` (not ``or``) so ``suggestions=[]`` produces an
    empty list rather than falling back to the default suggestion.
    """
    if suggestions is None:
        suggestions = [
            {
                "id": f"R{round_number}-S1",
                "area": "architecture",
                "severity": "high",
                "suggestion": "Add circuit breaker around payment calls",
                "rationale": "Payment API has 2% timeout rate",
                "proposed_placement": "Section 3.2",
                "validation_approach": "Inject 5s delay",
            },
        ]
    data: dict = {
        "round": round_number,
        "reviewer": "claude-4 (claude-opus-4-6)",
        "date": "2026-03-10",
        "scope": "architecture, risks",
        "suggestions": suggestions,
    }
    if endorsements is not None:
        data["endorsements"] = endorsements
    data.update(overrides)
    return data


def _wrap_json(data: dict) -> str:
    """Wrap a dict as a ```json fenced block (LLM-style)."""
    return f"```json\n{json.dumps(data, indent=2)}\n```"


# =========================================================================
# RV-901: _validate_json_review
# =========================================================================

class TestValidateJsonReview:
    """Unit tests for the JSON review validator."""

    def test_happy_path(self):
        data = _make_review_json()
        raw = _wrap_json(data)
        ok, msg, ids, parsed = _validate_json_review(raw, 1, 5)
        assert ok is True
        assert ids == ["R1-S1"]
        assert parsed is not None
        assert parsed["suggestions"][0]["area"] == "architecture"

    def test_multiple_suggestions(self):
        suggestions = [
            {"id": "R2-S1", "area": "data", "severity": "critical",
             "suggestion": "Add index", "rationale": "Slow queries"},
            {"id": "R2-S2", "area": "ops", "severity": "medium",
             "suggestion": "Add health check", "rationale": "No liveness probe"},
        ]
        raw = _wrap_json(_make_review_json(round_number=2, suggestions=suggestions))
        ok, msg, ids, parsed = _validate_json_review(raw, 2, 5)
        assert ok is True
        assert ids == ["R2-S1", "R2-S2"]

    def test_too_many_suggestions_rejected(self):
        suggestions = [
            {"id": f"R1-S{i}", "area": "ops", "severity": "low",
             "suggestion": f"s{i}", "rationale": f"r{i}"}
            for i in range(1, 7)
        ]
        raw = _wrap_json(_make_review_json(suggestions=suggestions))
        ok, msg, ids, _ = _validate_json_review(raw, 1, 5)
        assert ok is False
        assert "Too many" in msg

    def test_empty_suggestions_valid(self):
        raw = _wrap_json(_make_review_json(suggestions=[]))
        ok, msg, ids, parsed = _validate_json_review(raw, 1, 5)
        assert ok is True
        assert ids == []
        assert "No suggestions" in msg

    def test_not_json_returns_false(self):
        ok, msg, ids, parsed = _validate_json_review("This is plain text", 1, 5)
        assert ok is False
        assert "Not valid JSON" in msg
        assert parsed is None

    def test_json_array_instead_of_object(self):
        raw = _wrap_json([{"id": "R1-S1"}])  # array, not object
        ok, msg, _, _ = _validate_json_review(raw, 1, 5)
        assert ok is False
        assert "Expected a JSON object" in msg

    def test_missing_suggestions_key(self):
        raw = _wrap_json({"round": 1, "reviewer": "test"})
        ok, msg, _, _ = _validate_json_review(raw, 1, 5)
        assert ok is False
        assert "suggestions" in msg.lower()

    def test_id_auto_correction_wrong_round(self):
        """IDs with wrong round prefix are auto-corrected to current round."""
        suggestions = [
            {"id": "R5-S1", "area": "risks", "severity": "high",
             "suggestion": "Fix", "rationale": "Because"},
        ]
        raw = _wrap_json(_make_review_json(round_number=3, suggestions=suggestions))
        ok, msg, ids, parsed = _validate_json_review(raw, 3, 5)
        assert ok is True
        assert ids == ["R3-S1"]
        assert parsed["suggestions"][0]["id"] == "R3-S1"

    def test_id_auto_assignment_when_malformed(self):
        """Completely malformed IDs get sequential assignment."""
        suggestions = [
            {"id": "bad-id", "area": "data", "severity": "low",
             "suggestion": "Fix", "rationale": "Because"},
        ]
        raw = _wrap_json(_make_review_json(suggestions=suggestions))
        ok, msg, ids, _ = _validate_json_review(raw, 1, 5)
        assert ok is True
        assert ids == ["R1-S1"]

    def test_missing_required_fields_defaulted(self):
        """Missing area/severity default rather than rejecting."""
        suggestions = [
            {"id": "R1-S1", "suggestion": "Do X", "rationale": "Why"},
        ]
        raw = _wrap_json(_make_review_json(suggestions=suggestions))
        ok, msg, ids, parsed = _validate_json_review(raw, 1, 5)
        assert ok is True
        assert parsed["suggestions"][0]["area"] == "unknown"
        assert parsed["suggestions"][0]["severity"] == "medium"

    def test_non_standard_area_accepted(self):
        """Non-canonical area values are accepted (warn, don't reject)."""
        suggestions = [
            {"id": "R1-S1", "area": "compliance", "severity": "high",
             "suggestion": "Add audit", "rationale": "SOC2"},
        ]
        raw = _wrap_json(_make_review_json(suggestions=suggestions))
        ok, _, _, _ = _validate_json_review(raw, 1, 5)
        assert ok is True

    def test_non_standard_severity_accepted(self):
        """Non-canonical severity values are accepted (warn, don't reject)."""
        suggestions = [
            {"id": "R1-S1", "area": "ops", "severity": "urgent",
             "suggestion": "Fix", "rationale": "Now"},
        ]
        raw = _wrap_json(_make_review_json(suggestions=suggestions))
        ok, _, _, _ = _validate_json_review(raw, 1, 5)
        assert ok is True

    def test_endorsements_preserved(self):
        endorsements = [
            {"id": "R1-S3", "reason": "Agree — critical for resilience"},
        ]
        data = _make_review_json(round_number=2, endorsements=endorsements)
        raw = _wrap_json(data)
        ok, _, _, parsed = _validate_json_review(raw, 2, 5)
        assert ok is True
        assert len(parsed["endorsements"]) == 1

    def test_raw_json_without_fences(self):
        """JSON without code fences should still parse."""
        data = _make_review_json()
        raw = json.dumps(data)
        ok, _, ids, _ = _validate_json_review(raw, 1, 5)
        assert ok is True
        assert len(ids) == 1


# =========================================================================
# RV-902: _render_review_json_to_markdown
# =========================================================================

class TestRenderReviewJsonToMarkdown:
    """Unit tests for the JSON-to-markdown renderer."""

    def test_basic_render(self):
        data = _make_review_json()
        md = _render_review_json_to_markdown(data, 1, "claude-4", "architecture")
        assert "#### Review Round R1" in md
        assert "**Reviewer**: claude-4" in md
        assert "R1-S1" in md
        assert "circuit breaker" in md

    def test_round_trip_through_validate_snippet(self):
        """Rendered markdown passes _validate_snippet() (RV-902 acceptance criterion)."""
        data = _make_review_json()
        md = _render_review_json_to_markdown(data, 1, "test", "all")
        ok, msg, ids = _validate_snippet(md, 1, 5)
        assert ok is True, f"Round-trip failed: {msg}"
        assert "R1-S1" in ids

    def test_optional_columns_default_to_na(self):
        """Missing optional fields render as N/A."""
        suggestions = [
            {"id": "R1-S1", "area": "risks", "severity": "high",
             "suggestion": "Fix crash", "rationale": "Critical bug"},
        ]
        data = _make_review_json(suggestions=suggestions)
        md = _render_review_json_to_markdown(data, 1, "test", "all")
        assert "N/A" in md

    def test_pipe_escaping(self):
        """Pipe characters in suggestion text are escaped (RV-902 AC)."""
        suggestions = [
            {"id": "R1-S1", "area": "data", "severity": "medium",
             "suggestion": "Use SELECT col1 | col2 pattern",
             "rationale": "Better | filtering"},
        ]
        data = _make_review_json(suggestions=suggestions)
        md = _render_review_json_to_markdown(data, 1, "test", "all")
        # Pipes in cell values should be escaped
        assert "\\|" in md
        # Rendered table should still validate
        ok, msg, _ = _validate_snippet(md, 1, 5)
        assert ok is True, f"Pipe-escaped table failed validation: {msg}"

    def test_endorsements_rendered(self):
        endorsements = [
            {"id": "R1-S2", "reason": "Agree with circuit breaker"},
            {"id": "R1-S3", "reason": "Good point on retry"},
        ]
        data = _make_review_json(round_number=2, endorsements=endorsements)
        md = _render_review_json_to_markdown(data, 2, "test", "all")
        assert "**Endorsements**" in md
        assert "R1-S2" in md
        assert "R1-S3" in md

    def test_no_endorsements_section_when_empty(self):
        data = _make_review_json(endorsements=[])
        md = _render_review_json_to_markdown(data, 1, "test", "all")
        assert "Endorsements" not in md

    def test_extraction_from_rendered_markdown(self):
        """_extract_untriaged_suggestions can extract from rendered markdown."""
        suggestions = [
            {"id": "R1-S1", "area": "architecture", "severity": "high",
             "suggestion": "Add retry", "rationale": "Resilience"},
            {"id": "R1-S2", "area": "ops", "severity": "medium",
             "suggestion": "Add dashboard", "rationale": "Visibility"},
        ]
        data = _make_review_json(suggestions=suggestions)
        md = _render_review_json_to_markdown(data, 1, "test", "all")
        # Build a minimal document with Appendix C containing the rendered block
        doc = f"# Plan\n\n---\n\n### Appendix C: Incoming Suggestions (Untriaged, append-only)\n\n{md}"
        result = _extract_untriaged_suggestions(doc, set(), set())
        # Returns a tuple; first element is the list of suggestion dicts
        extracted = result[0] if isinstance(result, tuple) else result
        assert len(extracted) == 2
        ids = {s["id"] for s in extracted}
        assert "R1-S1" in ids
        assert "R1-S2" in ids

    def test_multiple_suggestions_table_format(self):
        """Table has correct number of rows for multiple suggestions."""
        suggestions = [
            {"id": f"R1-S{i}", "area": "data", "severity": "low",
             "suggestion": f"Item {i}", "rationale": f"Reason {i}"}
            for i in range(1, 4)
        ]
        data = _make_review_json(suggestions=suggestions)
        md = _render_review_json_to_markdown(data, 1, "test", "all")
        # Count data rows (lines starting with | that aren't header or separator)
        table_lines = [l for l in md.split("\n") if l.startswith("|")]
        # header + separator + 3 data rows = 5
        assert len(table_lines) == 5


# =========================================================================
# RV-901: _validate_review_output (dual-format dispatcher)
# =========================================================================

class TestValidateReviewOutput:
    """Tests for the dual-format validator dispatcher."""

    def test_json_path(self):
        raw = _wrap_json(_make_review_json())
        ok, msg, ids, fmt, parsed = _validate_review_output(raw, 1, 5)
        assert ok is True
        assert fmt == "json"
        assert parsed is not None

    def test_markdown_fallback(self):
        md = textwrap.dedent("""\
            #### Review Round R1

            | ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
            | ---- | ---- | ---- | ---- | ---- | ---- | ---- |
            | R1-S1 | Architecture | High | Add retry | Resilience | Section 2 | Unit test |
        """)
        ok, msg, ids, fmt, parsed = _validate_review_output(md, 1, 5)
        assert ok is True
        assert fmt == "markdown_table"
        assert parsed is None
        assert "R1-S1" in ids

    def test_both_fail(self):
        ok, msg, ids, fmt, _ = _validate_review_output("garbage text", 1, 5)
        assert ok is False
        assert fmt == "unknown"
        assert "JSON:" in msg and "Markdown:" in msg

    def test_json_preferred_over_markdown(self):
        """When input is valid JSON, JSON path is taken (not markdown)."""
        data = _make_review_json()
        raw = _wrap_json(data)
        ok, _, _, fmt, _ = _validate_review_output(raw, 1, 5)
        assert fmt == "json"

    def test_malformed_json_falls_back_to_markdown(self):
        """Broken JSON with a valid markdown table falls back correctly."""
        text = textwrap.dedent("""\
            ```json
            {invalid json here}
            ```

            #### Review Round R1

            | ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
            | ---- | ---- | ---- | ---- | ---- | ---- | ---- |
            | R1-S1 | Architecture | High | Add retry | Fix it | Section 2 | Test |
        """)
        ok, _, ids, fmt, _ = _validate_review_output(text, 1, 5)
        assert ok is True
        assert fmt == "markdown_table"


# =========================================================================
# RV-903: YAML prompt template
# =========================================================================

class TestReviewPromptTemplate:
    """Verify the updated review prompt produces valid JSON example."""

    def test_json_example_has_single_braces(self):
        from startd8.workflows.builtin.prompts import format_prompt

        result = format_prompt(
            "architectural_review", "review",
            role="architect", round_number=1, iteration_context="ctx",
            req_block="", context_block="", max_suggestions=5,
            req_instruction="", focus_line="", context_instruction="",
            dual_doc_instruction="", reviewer_label="test",
            now_utc="2026-03-10", scope="architecture",
            areas_list="architecture, data, ops", document_section="",
        )
        # The JSON example should contain valid single braces
        assert "{{" not in result, "Double braces found — brace escaping bug"
        assert "}}" not in result, "Double braces found — brace escaping bug"
        # Should contain the JSON schema
        assert '"suggestions"' in result
        assert '"endorsements"' in result

    def test_prompt_requests_json_output(self):
        from startd8.workflows.builtin.prompts import format_prompt

        result = format_prompt(
            "architectural_review", "review",
            role="architect", round_number=1, iteration_context="",
            req_block="", context_block="", max_suggestions=5,
            req_instruction="", focus_line="", context_instruction="",
            dual_doc_instruction="", reviewer_label="test",
            now_utc="now", scope="all", areas_list="architecture",
            document_section="",
        )
        assert "```json" in result
        assert "Return ONLY the JSON object" in result


# =========================================================================
# RV-903: Plan ingestion YAML prompt template
# =========================================================================

class TestPlanIngestionPromptTemplate:
    """Verify plan ingestion prompts produce valid JSON examples."""

    def test_parse_prompt_single_braces(self):
        from startd8.workflows.builtin.prompts import format_prompt

        result = format_prompt("plan_ingestion", "parse", plan_text="test")
        assert "{{" not in result
        assert "}}" not in result
        # Verify it has the JSON structure
        assert '"feature_id"' in result

    def test_assess_prompt_single_braces(self):
        from startd8.workflows.builtin.prompts import format_prompt

        result = format_prompt(
            "plan_ingestion", "assess",
            title="t", goals="g", feature_count=3,
            feature_summary="fs", file_count=5, threshold=60,
        )
        assert "{{" not in result
        assert "}}" not in result
        assert '"composite"' in result
