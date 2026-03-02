"""Tests for the Micro Prime data models."""

from __future__ import annotations

import pytest

from startd8.micro_prime.models import (
    ElementResult,
    EscalationReason,
    EscalationResult,
    FileResult,
    MicroPrimeConfig,
    MicroPrimeCostReport,
    MicroPrimeElementMetrics,
    RepairAttribution,
    RepairStepResult,
    SeedResult,
    TierClassification,
)


class TestTierClassification:
    def test_enum_values(self):
        assert TierClassification.TRIVIAL.value == "trivial"
        assert TierClassification.SIMPLE.value == "simple"
        assert TierClassification.MODERATE.value == "moderate"
        assert TierClassification.COMPLEX.value == "complex"

    def test_from_string(self):
        assert TierClassification("trivial") == TierClassification.TRIVIAL


class TestEscalationReason:
    def test_all_reasons(self):
        assert len(EscalationReason) == 7
        assert EscalationReason.AST_FAILURE.value == "ast_failure"


class TestRepairStepResult:
    def test_creation(self):
        result = RepairStepResult(
            step_name="fence_strip",
            modified=True,
            code="clean code",
            metrics={"had_fences": True},
        )
        assert result.step_name == "fence_strip"
        assert result.modified is True
        assert result.metrics["had_fences"] is True


class TestElementResult:
    def test_default_values(self):
        result = ElementResult(
            element_name="get_name",
            file_path="src/utils.py",
            tier=TierClassification.SIMPLE,
            success=True,
        )
        assert result.code is None
        assert result.escalation is None
        assert result.template_used is False
        assert result.repair_steps_applied == []
        assert result.generation_time_ms == 0.0

    def test_classification_reason_on_element_result(self):
        """R3-S1: classification_reason defaults to empty string."""
        result = ElementResult(
            element_name="get_name",
            file_path="src/utils.py",
            tier=TierClassification.SIMPLE,
            success=True,
        )
        assert result.classification_reason == ""

        result_with_reason = ElementResult(
            element_name="get_name",
            file_path="src/utils.py",
            tier=TierClassification.SIMPLE,
            classification_reason="2 params; simple return (str)",
            success=True,
        )
        assert result_with_reason.classification_reason == "2 params; simple return (str)"

    def test_with_escalation(self):
        esc = EscalationResult(
            reason=EscalationReason.AST_FAILURE,
            detail="Could not parse",
        )
        result = ElementResult(
            element_name="bad_func",
            file_path="src/utils.py",
            tier=TierClassification.SIMPLE,
            success=False,
            escalation=esc,
        )
        assert result.escalation.reason == EscalationReason.AST_FAILURE


class TestFileResult:
    def test_counts(self):
        fr = FileResult(
            file_path="src/utils.py",
            element_results=[
                ElementResult(
                    element_name="a", file_path="src/utils.py",
                    tier=TierClassification.TRIVIAL, success=True,
                ),
                ElementResult(
                    element_name="b", file_path="src/utils.py",
                    tier=TierClassification.SIMPLE, success=True,
                ),
                ElementResult(
                    element_name="c", file_path="src/utils.py",
                    tier=TierClassification.MODERATE, success=False,
                    escalation=EscalationResult(
                        reason=EscalationReason.TIER_TOO_HIGH, detail="",
                    ),
                ),
            ],
        )
        assert fr.success_count == 2
        assert fr.escalated_count == 1
        assert fr.total_count == 3


class TestSeedResult:
    def test_aggregate_counts(self):
        fr1 = FileResult(
            file_path="a.py",
            element_results=[
                ElementResult("a", "a.py", TierClassification.TRIVIAL, True),
            ],
        )
        fr2 = FileResult(
            file_path="b.py",
            element_results=[
                ElementResult("b", "b.py", TierClassification.SIMPLE, True),
                ElementResult("c", "b.py", TierClassification.MODERATE, False),
            ],
        )
        sr = SeedResult(file_results=[fr1, fr2])
        assert sr.success_count == 2
        assert sr.total_count == 3


class TestMicroPrimeConfig:
    def test_defaults(self):
        config = MicroPrimeConfig()
        assert config.model == "startd8-coder"
        assert config.provider == "ollama"
        assert config.temperature == 0.1
        assert config.max_tokens == 512
        assert config.templates_enabled is True
        assert config.repair_enabled is True

    def test_custom_config(self):
        config = MicroPrimeConfig(
            model="custom-model",
            temperature=0.3,
            templates_enabled=False,
        )
        assert config.model == "custom-model"
        assert config.templates_enabled is False


class TestMicroPrimeCostReport:
    def test_creation(self):
        report = MicroPrimeCostReport(
            total_elements=10,
            trivial_count=3,
            simple_count=5,
            moderate_count=2,
            local_success_count=8,
            success_rate=0.8,
        )
        assert report.total_elements == 10
        assert report.success_rate == 0.8


class TestRepairAttribution:
    """Tests for RepairAttribution model (REQ-MP-601)."""

    def test_defaults(self):
        attr = RepairAttribution()
        assert attr.fence_stripped is False
        assert attr.trimmed is False
        assert attr.nodes_removed == 0
        assert attr.bare_wrapped is False
        assert attr.indent_source == ""
        assert attr.params_changed == 0
        assert attr.return_type_restored is False

    def test_custom_values(self):
        attr = RepairAttribution(
            fence_stripped=True,
            trimmed=True,
            nodes_removed=3,
            bare_wrapped=True,
            indent_source="dedent",
            params_changed=1,
            return_type_restored=True,
        )
        assert attr.fence_stripped is True
        assert attr.trimmed is True
        assert attr.nodes_removed == 3
        assert attr.bare_wrapped is True
        assert attr.indent_source == "dedent"
        assert attr.params_changed == 1
        assert attr.return_type_restored is True

    def test_serialization(self):
        attr = RepairAttribution(fence_stripped=True, nodes_removed=2)
        d = attr.model_dump()
        assert d["fence_stripped"] is True
        assert d["nodes_removed"] == 2
        assert d["trimmed"] is False

    def test_optional_on_element_result(self):
        result = ElementResult(
            element_name="foo",
            file_path="src/foo.py",
            tier=TierClassification.SIMPLE,
            success=True,
        )
        assert result.repair_attribution is None

    def test_present_on_element_result(self):
        attr = RepairAttribution(fence_stripped=True)
        result = ElementResult(
            element_name="foo",
            file_path="src/foo.py",
            tier=TierClassification.SIMPLE,
            success=True,
            repair_attribution=attr,
        )
        assert result.repair_attribution is not None
        assert result.repair_attribution.fence_stripped is True


class TestMicroPrimeElementMetrics:
    def test_serialization(self):
        metrics = MicroPrimeElementMetrics(
            element_name="get_name",
            file_path="src/utils.py",
            tier=TierClassification.SIMPLE,
            success=True,
            generation_time_ms=150.5,
        )
        d = metrics.model_dump()
        assert d["element_name"] == "get_name"
        assert d["tier"] == "simple"

    def test_serialization_with_repair_attribution(self):
        attr = RepairAttribution(
            fence_stripped=True,
            trimmed=True,
            nodes_removed=2,
        )
        metrics = MicroPrimeElementMetrics(
            element_name="get_name",
            file_path="src/utils.py",
            tier=TierClassification.SIMPLE,
            success=True,
            repair_attribution=attr,
        )
        d = metrics.model_dump()
        assert d["repair_attribution"] is not None
        assert d["repair_attribution"]["fence_stripped"] is True
        assert d["repair_attribution"]["nodes_removed"] == 2

    def test_classification_reason_on_metrics(self):
        """R3-S1: classification_reason defaults to empty string on metrics."""
        metrics = MicroPrimeElementMetrics(
            element_name="get_name",
            file_path="src/utils.py",
            tier=TierClassification.SIMPLE,
            success=True,
        )
        assert metrics.classification_reason == ""

        metrics_with_reason = MicroPrimeElementMetrics(
            element_name="get_name",
            file_path="src/utils.py",
            tier=TierClassification.SIMPLE,
            classification_reason="property accessor",
            success=True,
        )
        assert metrics_with_reason.classification_reason == "property accessor"
        d = metrics_with_reason.model_dump()
        assert d["classification_reason"] == "property accessor"

    def test_repair_attribution_none_by_default(self):
        metrics = MicroPrimeElementMetrics(
            element_name="get_name",
            file_path="src/utils.py",
            tier=TierClassification.SIMPLE,
            success=True,
        )
        assert metrics.repair_attribution is None
