"""Tests for SQL injection Kaizen prompt escalation.

Validates that:
1. CAUSE_TO_SUGGESTION contains the sql_injection_detected entry.
2. generate_kaizen_suggestions() produces a suggestion when 2+ features
   have sql_injection_risk semantic issues.
3. Security-related kaizen hints are escalated to P0 in spec_builder.
4. C#-specific parameterized query examples appear when Npgsql/Spanner
   client libraries are detected.
"""

import dataclasses
import pytest
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# 1. CAUSE_TO_SUGGESTION has sql_injection entry
# ---------------------------------------------------------------------------


class TestCauseToSuggestionEntry:
    """Verify sql_injection_detected is in the CAUSE_TO_SUGGESTION mapping."""

    def test_sql_injection_key_exists(self):
        from startd8.contractors.prime_postmortem import CAUSE_TO_SUGGESTION

        assert "sql_injection_detected" in CAUSE_TO_SUGGESTION

    def test_sql_injection_has_required_fields(self):
        from startd8.contractors.prime_postmortem import CAUSE_TO_SUGGESTION

        entry = CAUSE_TO_SUGGESTION["sql_injection_detected"]
        assert "phase" in entry
        assert "hint" in entry
        assert entry["phase"] == "draft"

    def test_sql_injection_hint_mentions_parameterized(self):
        from startd8.contractors.prime_postmortem import CAUSE_TO_SUGGESTION

        entry = CAUSE_TO_SUGGESTION["sql_injection_detected"]
        hint = entry["hint"]
        assert "parameterized" in hint.lower()
        assert "string interpolation" in hint.lower()

    def test_sql_injection_hint_has_examples(self):
        from startd8.contractors.prime_postmortem import CAUSE_TO_SUGGESTION

        hint = CAUSE_TO_SUGGESTION["sql_injection_detected"]["hint"]
        assert "BAD:" in hint
        assert "GOOD:" in hint
        assert "SpannerCommand" in hint


# ---------------------------------------------------------------------------
# 2. Kaizen suggestions from semantic issues
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class _FakeFeaturePM:
    """Minimal stand-in for FeaturePostMortem."""

    feature_name: str = "feat-1"
    disk_compliance: Optional[Any] = None

    @property
    def semantic_issue_summary(self) -> Dict[str, int]:
        if not self.disk_compliance:
            return {}
        issues = getattr(self.disk_compliance, "semantic_issues", [])
        summary: Dict[str, int] = {}
        for issue in issues:
            if isinstance(issue, dict):
                cat = issue.get("category", "unknown")
                summary[cat] = summary.get(cat, 0) + 1
        return summary


@dataclasses.dataclass
class _FakeDiskCompliance:
    semantic_issues: List[Dict[str, str]] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class _FakeReport:
    features: List[_FakeFeaturePM] = dataclasses.field(default_factory=list)
    cross_feature_patterns: List[Any] = dataclasses.field(default_factory=list)


class TestKaizenSqlInjectionSuggestions:
    """Verify generate_kaizen_suggestions handles sql_injection_risk."""

    def test_no_suggestion_with_one_feature(self):
        from startd8.contractors.prime_postmortem import generate_kaizen_suggestions

        compliance = _FakeDiskCompliance(
            semantic_issues=[{"category": "sql_injection_risk", "severity": "error"}]
        )
        report = _FakeReport(
            features=[_FakeFeaturePM(feature_name="f1", disk_compliance=compliance)]
        )
        suggestions = generate_kaizen_suggestions(report)
        sql_suggestions = [s for s in suggestions if s["pattern_type"] == "sql_injection_detected"]
        assert len(sql_suggestions) == 0, "Should not suggest for < 2 features"

    def test_suggestion_with_two_features(self):
        from startd8.contractors.prime_postmortem import generate_kaizen_suggestions

        compliance1 = _FakeDiskCompliance(
            semantic_issues=[{"category": "sql_injection_risk", "severity": "error"}]
        )
        compliance2 = _FakeDiskCompliance(
            semantic_issues=[{"category": "sql_injection_risk", "severity": "error"}]
        )
        report = _FakeReport(
            features=[
                _FakeFeaturePM(feature_name="AlloyDBCartStore", disk_compliance=compliance1),
                _FakeFeaturePM(feature_name="SpannerCartStore", disk_compliance=compliance2),
            ]
        )
        suggestions = generate_kaizen_suggestions(report)
        sql_suggestions = [s for s in suggestions if s["pattern_type"] == "sql_injection_detected"]
        assert len(sql_suggestions) == 1
        assert sql_suggestions[0]["frequency"] == 2
        assert "parameterized" in sql_suggestions[0]["suggested_action"].lower()

    def test_suggestion_with_three_features_high_confidence(self):
        from startd8.contractors.prime_postmortem import generate_kaizen_suggestions

        features = []
        for i in range(3):
            compliance = _FakeDiskCompliance(
                semantic_issues=[{"category": "sql_injection_risk", "severity": "error"}]
            )
            features.append(_FakeFeaturePM(feature_name=f"store-{i}", disk_compliance=compliance))

        report = _FakeReport(features=features)
        suggestions = generate_kaizen_suggestions(report)
        sql_suggestions = [s for s in suggestions if s["pattern_type"] == "sql_injection_detected"]
        assert len(sql_suggestions) == 1
        assert sql_suggestions[0]["confidence"] == "high"


# ---------------------------------------------------------------------------
# 3. Security kaizen hints get P0 priority in spec builder
# ---------------------------------------------------------------------------


class TestSecurityKaizenP0:
    """Verify sql_injection kaizen hints are escalated to P0."""

    def test_sql_injection_hint_is_p0(self):
        from startd8.implementation_engine.spec_builder import build_spec_prompt

        context = {
            "kaizen_hints": (
                "- Prior run generated SQL queries with string interpolation. "
                "CRITICAL: Use ONLY parameterized queries."
            ),
        }
        prompt = build_spec_prompt("Implement cart store", context.copy(), output_format=None)
        # The security hint should appear under the P0 security heading
        assert "Security Constraints" in prompt
        assert "parameterized" in prompt.lower()

    def test_non_security_hint_stays_p1(self):
        from startd8.implementation_engine.spec_builder import build_spec_prompt

        context = {
            "kaizen_hints": "- Replace every stub/placeholder with real implementation.",
        }
        prompt = build_spec_prompt("Implement feature", context.copy(), output_format=None)
        # Non-security hints should use the regular quality hints heading
        assert "Quality Hints" in prompt
        assert "Security Constraints" not in prompt

    def test_mixed_hints_split_correctly(self):
        from startd8.implementation_engine.spec_builder import build_spec_prompt

        context = {
            "kaizen_hints": (
                "- Replace every stub/placeholder with real implementation.\n"
                "- Prior run generated SQL queries with string interpolation. "
                "CRITICAL: Use ONLY parameterized queries."
            ),
        }
        prompt = build_spec_prompt("Implement cart", context.copy(), output_format=None)
        assert "Security Constraints" in prompt
        assert "Quality Hints" in prompt


# ---------------------------------------------------------------------------
# 4. C#-specific parameterized examples for database client libraries
# ---------------------------------------------------------------------------


class TestSecurityGuidanceSection:
    """Verify _build_security_guidance_section produces library-specific examples."""

    def test_npgsql_example(self):
        from startd8.implementation_engine.spec_builder import _build_security_guidance_section

        context = {
            "security_contract": {
                "client_libraries": ["Npgsql"],
            },
        }
        section = _build_security_guidance_section(context)
        assert "NpgsqlCommand" in section
        assert "@param" in section.lower() or "@id" in section

    def test_spanner_example(self):
        from startd8.implementation_engine.spec_builder import _build_security_guidance_section

        context = {
            "security_contract": {
                "client_libraries": ["Google.Cloud.Spanner.Data"],
            },
        }
        section = _build_security_guidance_section(context)
        assert "SpannerCommand" in section
        assert "SpannerDbType" in section

    def test_sqlclient_example(self):
        from startd8.implementation_engine.spec_builder import _build_security_guidance_section

        context = {
            "security_contract": {
                "client_libraries": ["Microsoft.Data.SqlClient"],
            },
        }
        section = _build_security_guidance_section(context)
        assert "SqlCommand" in section

    def test_no_libraries_returns_empty(self):
        from startd8.implementation_engine.spec_builder import _build_security_guidance_section

        section = _build_security_guidance_section({})
        assert section == ""

    def test_unrecognized_library_returns_empty(self):
        from startd8.implementation_engine.spec_builder import _build_security_guidance_section

        context = {
            "security_contract": {
                "client_libraries": ["some-unknown-db-driver"],
            },
        }
        section = _build_security_guidance_section(context)
        assert section == ""

    def test_security_guidance_in_spec_prompt(self):
        """Verify that security guidance is injected into the spec prompt as P0."""
        from startd8.implementation_engine.spec_builder import build_spec_prompt

        context = {
            "security_contract": {
                "client_libraries": ["Google.Cloud.Spanner.Data"],
            },
        }
        prompt = build_spec_prompt("Implement SpannerCartStore", context.copy(), output_format=None)
        assert "Database Security Guidance" in prompt
        assert "SpannerCommand" in prompt
