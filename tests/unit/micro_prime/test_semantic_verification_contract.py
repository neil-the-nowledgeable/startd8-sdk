"""Tests for SemanticVerificationResult contract (Keiyaku Gap A-2).

Validates the JSON output contract for semantic verification before
the capability gets wired into the engine.
"""

from __future__ import annotations

import json

import pytest

from startd8.micro_prime.models import (
    SemanticVerificationResult,
    VerificationIssue,
    validate_semantic_verification_json,
)


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def happy_path_data() -> dict:
    """Complete, well-formed LLM JSON output."""
    return {
        "verdict": "fail",
        "confidence": 0.85,
        "issues": [
            {
                "severity": "high",
                "category": "missing_error_handling",
                "description": "Division by total_count without zero check",
                "line_hint": 7,
                "suggested_fix": "Add guard: if total_count == 0: return 0.0",
            },
            {
                "severity": "low",
                "category": "naming",
                "description": "Variable 'x' is non-descriptive",
                "line_hint": 3,
                "suggested_fix": None,
            },
        ],
        "element_fqn": "module.ClassName.calculate_ratio",
    }


@pytest.fixture()
def element_fqn() -> str:
    return "module.ClassName.calculate_ratio"


# ── from_json happy path ─────────────────────────────────────────────


class TestFromJsonHappyPath:
    def test_verdict_preserved(self, happy_path_data: dict, element_fqn: str) -> None:
        result = SemanticVerificationResult.from_json(happy_path_data, element_fqn)
        assert result.verdict == "fail"

    def test_confidence_preserved(self, happy_path_data: dict, element_fqn: str) -> None:
        result = SemanticVerificationResult.from_json(happy_path_data, element_fqn)
        assert result.confidence == pytest.approx(0.85)

    def test_issues_count(self, happy_path_data: dict, element_fqn: str) -> None:
        result = SemanticVerificationResult.from_json(happy_path_data, element_fqn)
        assert len(result.issues) == 2

    def test_issue_fields(self, happy_path_data: dict, element_fqn: str) -> None:
        result = SemanticVerificationResult.from_json(happy_path_data, element_fqn)
        issue = result.issues[0]
        assert isinstance(issue, VerificationIssue)
        assert issue.severity == "high"
        assert issue.category == "missing_error_handling"
        assert issue.line_hint == 7
        assert issue.suggested_fix is not None

    def test_element_fqn_from_data(self, happy_path_data: dict, element_fqn: str) -> None:
        result = SemanticVerificationResult.from_json(happy_path_data, element_fqn)
        assert result.element_fqn == "module.ClassName.calculate_ratio"

    def test_element_fqn_fallback(self, element_fqn: str) -> None:
        """When element_fqn missing from data, uses the argument."""
        data = {"verdict": "pass", "confidence": 0.9, "issues": []}
        result = SemanticVerificationResult.from_json(data, element_fqn)
        assert result.element_fqn == element_fqn


# ── from_json auto-correction ────────────────────────────────────────


class TestFromJsonAutoCorrection:
    def test_missing_verdict_defaults_inconclusive(self, element_fqn: str) -> None:
        result = SemanticVerificationResult.from_json({}, element_fqn)
        assert result.verdict == "inconclusive"

    def test_unknown_verdict_corrected(self, element_fqn: str) -> None:
        data = {"verdict": "maybe", "confidence": 0.5}
        result = SemanticVerificationResult.from_json(data, element_fqn)
        assert result.verdict == "inconclusive"

    def test_missing_confidence_defaults_half(self, element_fqn: str) -> None:
        result = SemanticVerificationResult.from_json({}, element_fqn)
        assert result.confidence == pytest.approx(0.5)

    def test_confidence_clamped_above_one(self, element_fqn: str) -> None:
        data = {"confidence": 1.5}
        result = SemanticVerificationResult.from_json(data, element_fqn)
        assert result.confidence == pytest.approx(1.0)

    def test_confidence_clamped_below_zero(self, element_fqn: str) -> None:
        data = {"confidence": -0.3}
        result = SemanticVerificationResult.from_json(data, element_fqn)
        assert result.confidence == pytest.approx(0.0)

    def test_missing_issues_defaults_empty(self, element_fqn: str) -> None:
        result = SemanticVerificationResult.from_json({}, element_fqn)
        assert result.issues == ()

    def test_issue_missing_fields_get_defaults(self, element_fqn: str) -> None:
        data = {"issues": [{}]}
        result = SemanticVerificationResult.from_json(data, element_fqn)
        issue = result.issues[0]
        assert issue.severity == "medium"
        assert issue.category == "unknown"
        assert issue.description == "(not provided)"
        assert issue.line_hint is None
        assert issue.suggested_fix is None


# ── to_dict and round-trip ───────────────────────────────────────────


class TestToDict:
    def test_round_trip(self, happy_path_data: dict, element_fqn: str) -> None:
        """from_json → to_dict → from_json produces equivalent result."""
        original = SemanticVerificationResult.from_json(happy_path_data, element_fqn)
        serialized = original.to_dict()
        # to_dict wraps under "verification" key
        inner = serialized["verification"]
        restored = SemanticVerificationResult.from_json(inner, element_fqn)
        assert restored.verdict == original.verdict
        assert restored.confidence == pytest.approx(original.confidence)
        assert len(restored.issues) == len(original.issues)
        assert restored.element_fqn == original.element_fqn

    def test_to_dict_structure(self, element_fqn: str) -> None:
        data = {"verdict": "pass", "confidence": 1.0, "issues": []}
        result = SemanticVerificationResult.from_json(data, element_fqn)
        d = result.to_dict()
        assert "verification" in d
        v = d["verification"]
        assert v["verdict"] == "pass"
        assert v["confidence"] == 1.0
        assert v["issues"] == []
        assert v["element_fqn"] == element_fqn

    def test_to_dict_issues_serialized(self, happy_path_data: dict, element_fqn: str) -> None:
        result = SemanticVerificationResult.from_json(happy_path_data, element_fqn)
        d = result.to_dict()
        issues = d["verification"]["issues"]
        assert len(issues) == 2
        assert issues[0]["severity"] == "high"
        assert issues[0]["line_hint"] == 7


# ── Properties ───────────────────────────────────────────────────────


class TestProperties:
    def test_passed_true(self, element_fqn: str) -> None:
        data = {"verdict": "pass", "confidence": 0.9}
        result = SemanticVerificationResult.from_json(data, element_fqn)
        assert result.passed is True

    def test_passed_false_on_fail(self, element_fqn: str) -> None:
        data = {"verdict": "fail", "confidence": 0.9}
        result = SemanticVerificationResult.from_json(data, element_fqn)
        assert result.passed is False

    def test_passed_false_on_inconclusive(self, element_fqn: str) -> None:
        data = {"verdict": "inconclusive"}
        result = SemanticVerificationResult.from_json(data, element_fqn)
        assert result.passed is False

    def test_has_critical_issues_true(self, element_fqn: str) -> None:
        data = {
            "verdict": "fail",
            "issues": [{"severity": "critical", "description": "boom"}],
        }
        result = SemanticVerificationResult.from_json(data, element_fqn)
        assert result.has_critical_issues is True

    def test_has_critical_issues_false(self, element_fqn: str) -> None:
        data = {
            "verdict": "fail",
            "issues": [{"severity": "high", "description": "not critical"}],
        }
        result = SemanticVerificationResult.from_json(data, element_fqn)
        assert result.has_critical_issues is False

    def test_has_critical_issues_empty(self, element_fqn: str) -> None:
        data = {"verdict": "pass", "issues": []}
        result = SemanticVerificationResult.from_json(data, element_fqn)
        assert result.has_critical_issues is False


# ── validate_semantic_verification_json ──────────────────────────────


class TestValidateSemanticVerificationJson:
    def test_plain_json(self, element_fqn: str) -> None:
        raw = json.dumps({"verdict": "pass", "confidence": 0.95, "issues": []})
        ok, result = validate_semantic_verification_json(raw, element_fqn)
        assert ok is True
        assert isinstance(result, SemanticVerificationResult)
        assert result.verdict == "pass"

    def test_fenced_json(self, element_fqn: str) -> None:
        inner = json.dumps({"verdict": "fail", "confidence": 0.7, "issues": []})
        raw = f"```json\n{inner}\n```"
        ok, result = validate_semantic_verification_json(raw, element_fqn)
        assert ok is True
        assert isinstance(result, SemanticVerificationResult)
        assert result.verdict == "fail"

    def test_fenced_without_language_tag(self, element_fqn: str) -> None:
        inner = json.dumps({"verdict": "pass", "confidence": 0.8, "issues": []})
        raw = f"```\n{inner}\n```"
        ok, result = validate_semantic_verification_json(raw, element_fqn)
        assert ok is True
        assert isinstance(result, SemanticVerificationResult)

    def test_invalid_json_returns_error(self, element_fqn: str) -> None:
        raw = "this is not json at all"
        ok, error = validate_semantic_verification_json(raw, element_fqn)
        assert ok is False
        assert isinstance(error, str)
        assert "JSON parse error" in error

    def test_non_object_json_returns_error(self, element_fqn: str) -> None:
        raw = json.dumps([1, 2, 3])
        ok, error = validate_semantic_verification_json(raw, element_fqn)
        assert ok is False
        assert "Expected JSON object" in error

    def test_empty_issues_list(self, element_fqn: str) -> None:
        raw = json.dumps({"verdict": "pass", "confidence": 1.0, "issues": []})
        ok, result = validate_semantic_verification_json(raw, element_fqn)
        assert ok is True
        assert isinstance(result, SemanticVerificationResult)
        assert result.issues == ()
        assert result.passed is True

    def test_auto_correction_through_validator(self, element_fqn: str) -> None:
        """Unknown verdict auto-corrected when going through validator."""
        raw = json.dumps({"verdict": "unknown_value", "confidence": 2.0})
        ok, result = validate_semantic_verification_json(raw, element_fqn)
        assert ok is True
        assert isinstance(result, SemanticVerificationResult)
        assert result.verdict == "inconclusive"
        assert result.confidence == pytest.approx(1.0)


# ── Frozen dataclass invariants ──────────────────────────────────────


class TestFrozenInvariants:
    def test_result_is_frozen(self, element_fqn: str) -> None:
        result = SemanticVerificationResult.from_json(
            {"verdict": "pass"}, element_fqn,
        )
        with pytest.raises(AttributeError):
            result.verdict = "fail"  # type: ignore[misc]

    def test_issue_is_frozen(self) -> None:
        issue = VerificationIssue(
            severity="high", category="test", description="desc",
        )
        with pytest.raises(AttributeError):
            issue.severity = "low"  # type: ignore[misc]
