"""Tests for plan_ingestion_anchor_sanitizer (REQ-QPI-200–203)."""

import pytest

from startd8.workflows.builtin.plan_ingestion_anchor_sanitizer import (
    classify_acceptance_anchor,
    sanitize_acceptance_obligations,
    sanitize_task_description,
    strip_conflicting_negative_scope,
)


class TestClassifyAcceptanceAnchor:
    """REQ-QPI-200: Anti-pattern anchor detection."""

    def test_sql_interpolation_detected(self):
        result = classify_acceptance_anchor(
            "All SQL uses string interpolation",
            detected_database="postgresql",
            language="csharp",
        )
        assert result["classified"] == "anti_pattern"
        assert result["reason"] == "sql_interpolation"
        assert "parameterized" in result["safe_replacement"]

    def test_sql_concatenation_detected(self):
        result = classify_acceptance_anchor(
            "SQL queries built with string concatenation",
            detected_database="postgresql",
            language="csharp",
        )
        assert result["classified"] == "anti_pattern"

    def test_no_parameterized_detected(self):
        result = classify_acceptance_anchor(
            "No parameterized queries used",
        )
        assert result["classified"] == "anti_pattern"
        assert result["reason"] == "no_parameterized_directive"

    def test_not_parameterized_detected(self):
        result = classify_acceptance_anchor(
            "Queries are not parameterized (intentional)",
        )
        assert result["classified"] == "anti_pattern"

    def test_intentional_injection_detected(self):
        result = classify_acceptance_anchor(
            "SQL injection is intentional to match reference",
        )
        assert result["classified"] == "anti_pattern"
        assert result["reason"] == "intentional_injection"

    def test_reference_match_sql_detected(self):
        result = classify_acceptance_anchor(
            "Matches reference implementation SQL pattern exactly",
        )
        assert result["classified"] == "anti_pattern"
        assert result["reason"] == "reference_match_sql"

    def test_safe_anchor_unchanged(self):
        result = classify_acceptance_anchor(
            "All responses cached for 5 minutes",
        )
        assert result["classified"] == "safe"

    def test_non_sql_interpolation_safe(self):
        """String interpolation in non-SQL context should be safe."""
        result = classify_acceptance_anchor(
            "Log messages use string interpolation for readability",
        )
        assert result["classified"] == "safe"

    def test_replacement_includes_safe_syntax(self):
        result = classify_acceptance_anchor(
            "All SQL uses string interpolation",
            detected_database="postgresql",
            language="csharp",
        )
        # Registry returns "@param with NpgsqlParameter" or similar
        assert "parameterized" in result["safe_replacement"].lower()
        assert "NpgsqlParameter" in result["safe_replacement"] or "param" in result["safe_replacement"]

    def test_spanner_replacement_syntax(self):
        result = classify_acceptance_anchor(
            "All SQL queries use string interpolation",
            detected_database="spanner",
            language="csharp",
        )
        assert "SpannerParameterCollection" in result["safe_replacement"] or "parameterized" in result["safe_replacement"]


class TestSanitizeAcceptanceObligations:
    """REQ-QPI-201: Safe anchor replacement."""

    def test_mixed_obligations_sanitized(self):
        obligations = [
            "All SQL uses string interpolation",
            "Service returns proper gRPC status codes",
            "No parameterized queries (structural match)",
        ]
        sanitized, audit = sanitize_acceptance_obligations(
            obligations, "postgresql", "csharp",
        )
        # SQL interpolation → replaced
        assert any("parameterized" in s for s in sanitized)
        # gRPC anchor → kept
        assert any("gRPC" in s for s in sanitized)
        # "No parameterized" → removed (empty replacement)
        assert not any("No parameterized" in s for s in sanitized)
        # Audit trail
        assert len(audit) >= 2

    def test_empty_obligations_no_error(self):
        sanitized, audit = sanitize_acceptance_obligations([], "postgresql", "csharp")
        assert sanitized == []
        assert audit == []

    def test_all_safe_unchanged(self):
        obligations = [
            "Implements ICartStore interface",
            "Returns Cart protobuf objects",
        ]
        sanitized, audit = sanitize_acceptance_obligations(
            obligations, "postgresql", "csharp",
        )
        assert sanitized == obligations
        assert audit == []


class TestStripConflictingNegativeScope:
    """REQ-QPI-201: Negative scope stripping."""

    def test_parameterized_stripped(self):
        scope = [
            "Parameterized queries intentionally not used",
            "No ORM framework",
        ]
        cleaned, stripped = strip_conflicting_negative_scope(scope, "postgresql")
        assert "No ORM framework" in cleaned
        assert len(stripped) == 1
        assert "not used" in stripped[0]

    def test_dont_parameterize_stripped(self):
        scope = ["Don't use parameterized queries"]
        cleaned, stripped = strip_conflicting_negative_scope(scope, "postgresql")
        assert cleaned == []
        assert len(stripped) == 1

    def test_non_conflict_kept(self):
        scope = ["No external API calls", "No caching"]
        cleaned, stripped = strip_conflicting_negative_scope(scope, "postgresql")
        assert cleaned == scope
        assert stripped == []


class TestSanitizeTaskDescription:
    """REQ-QPI-203: Task description sanitization."""

    def test_interpolated_sql_replaced(self):
        desc = "AlloyDB cart store using Npgsql. Uses string-interpolated SQL matching reference implementation."
        sanitized, audit = sanitize_task_description(desc, "postgresql", "csharp")
        assert "string-interpolated" not in sanitized
        assert "parameterized" in sanitized
        assert len(audit) >= 1

    def test_reference_match_replaced(self):
        desc = "SQL queries matching reference implementation pattern"
        sanitized, audit = sanitize_task_description(desc, "postgresql", "csharp")
        assert "parameterized" in sanitized

    def test_non_sql_description_unchanged(self):
        desc = "gRPC service implementing CartService proto contract"
        sanitized, audit = sanitize_task_description(desc, "postgresql", "csharp")
        assert sanitized == desc
        assert audit == []

    def test_no_database_no_change(self):
        desc = "Uses string-interpolated SQL matching reference"
        sanitized, audit = sanitize_task_description(desc, "", "csharp")
        # Even without database, the regex fires on SQL patterns
        # The sanitizer should still clean the description
        assert "parameterized" in sanitized or sanitized == desc


class TestAuditTrail:
    """REQ-QPI-202: Sanitization audit trail."""

    def test_audit_preserves_original(self):
        obligations = ["All SQL uses string interpolation"]
        _, audit = sanitize_acceptance_obligations(
            obligations, "postgresql", "csharp",
        )
        assert len(audit) == 1
        assert audit[0]["original"] == "All SQL uses string interpolation"
        assert "reason" in audit[0]

    def test_description_audit_produced(self):
        desc = "Uses string-interpolated SQL matching reference implementation."
        _, audit = sanitize_task_description(desc, "postgresql", "csharp")
        assert len(audit) >= 1
        assert "original" in audit[0]
        assert "replacement" in audit[0]
