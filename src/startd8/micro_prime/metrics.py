"""Metrics Collection and Cost Reporting (REQ-MP-600–603).

Accumulates per-element metrics during engine runs and generates
cost reports and experiment result JSON.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from startd8.logging_config import get_logger
from startd8.micro_prime.models import (
    ElementResult,
    EscalationReason,
    MicroPrimeConfig,
    MicroPrimeCostReport,
    MicroPrimeElementMetrics,
    SeedResult,
    TierClassification,
)

logger = get_logger(__name__)

# Approximate cost per 1M tokens for local Ollama models (effectively free)
_LOCAL_COST_PER_M_INPUT = 0.0
_LOCAL_COST_PER_M_OUTPUT = 0.0

# Cloud model cost estimates for savings calculation (Haiku tier)
_CLOUD_COST_PER_M_INPUT = 0.80   # $/1M input tokens (Haiku)
_CLOUD_COST_PER_M_OUTPUT = 4.00  # $/1M output tokens (Haiku)


class MetricsCollector:
    """Accumulates per-element metrics during an engine run (REQ-MP-600)."""

    def __init__(self) -> None:
        self._metrics: list[MicroPrimeElementMetrics] = []

    def record(self, result: ElementResult) -> None:
        """Record metrics from an element result."""
        parent = result.parent_class
        element_fqn = f"{parent}.{result.element_name}" if parent else result.element_name
        kind = result.element_kind or ""
        if hasattr(kind, "value"):
            kind = kind.value
        generation_tokens = result.input_tokens + result.output_tokens
        self._metrics.append(
            MicroPrimeElementMetrics(
                element_name=result.element_name,
                element_fqn=element_fqn,
                element_kind=str(kind),
                api_file_import_bump=result.api_file_import_bump,
                api_element_adjustment=result.api_element_adjustment,
                file_path=result.file_path,
                tier=result.tier,
                classification_reason=result.classification_reason,
                success=result.success,
                template_used=result.template_used,
                template_name=result.template_name,
                repair_steps=result.repair_steps_applied,
                repair_attribution=result.repair_attribution,
                repair_recovered=result.repair_recovered,
                ast_valid_before_repair=result.ast_valid_before_repair,
                ast_valid_after_repair=result.ast_valid_after_repair,
                verification_verdict=result.verification_verdict,
                escalated=result.escalation is not None,
                generation_time_ms=result.generation_time_ms,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                generation_tokens=generation_tokens,
                model=result.model,
                escalation_reason=(
                    result.escalation.reason.value if result.escalation else None
                ),
            )
        )

    @property
    def metrics(self) -> list[MicroPrimeElementMetrics]:
        return list(self._metrics)

    def clear(self) -> None:
        self._metrics.clear()


def generate_cost_report(
    seed_result: SeedResult,
    config: MicroPrimeConfig,
) -> MicroPrimeCostReport:
    """Generate a cost report from a seed result (REQ-MP-602).

    Calculates local processing costs (effectively zero for Ollama) and
    estimated cloud savings compared to sending all elements to cloud.
    """
    tier_counts = {t: 0 for t in TierClassification}
    local_success = 0
    escalated = 0
    template_count = 0
    total_input = 0
    total_output = 0
    simple_escalated = 0
    local_inference_time_total_s = 0.0
    local_tokens_total = 0
    decomposed_count = 0
    decomposition_failure_count = 0

    for fr in seed_result.file_results:
        for er in fr.element_results:
            tier_counts[er.tier] = tier_counts.get(er.tier, 0) + 1
            total_input += er.input_tokens
            total_output += er.output_tokens
            local_inference_time_total_s += (er.generation_time_ms or 0.0) / 1000.0
            local_tokens_total += er.input_tokens + er.output_tokens
            if er.success:
                local_success += 1
            if er.escalation is not None:
                escalated += 1
                if er.tier == TierClassification.SIMPLE:
                    simple_escalated += 1
            if er.template_used:
                template_count += 1
            if er.decomposition_metadata is not None:
                decomposed_count += 1
            if (
                er.escalation is not None
                and er.escalation.reason == EscalationReason.DECOMPOSITION_FAILED
            ):
                decomposition_failure_count += 1

    total = seed_result.total_count

    # Local cost is effectively zero for Ollama
    local_cost = (
        total_input * _LOCAL_COST_PER_M_INPUT / 1_000_000
        + total_output * _LOCAL_COST_PER_M_OUTPUT / 1_000_000
    )

    baseline_input_tokens = 500
    baseline_output_tokens = 500
    baseline_per_element_usd = (
        baseline_input_tokens * _CLOUD_COST_PER_M_INPUT / 1_000_000
        + baseline_output_tokens * _CLOUD_COST_PER_M_OUTPUT / 1_000_000
    )
    baseline_all_cloud_usd = total * baseline_per_element_usd
    actual_cloud_usd = escalated * baseline_per_element_usd
    savings_usd = baseline_all_cloud_usd - actual_cloud_usd
    savings_pct = savings_usd / baseline_all_cloud_usd if baseline_all_cloud_usd > 0 else 0.0

    return MicroPrimeCostReport(
        total_elements=total,
        trivial_count=tier_counts.get(TierClassification.TRIVIAL, 0),
        simple_count=tier_counts.get(TierClassification.SIMPLE, 0),
        simple_escalated_count=simple_escalated,
        moderate_count=tier_counts.get(TierClassification.MODERATE, 0),
        complex_count=tier_counts.get(TierClassification.COMPLEX, 0),
        local_success_count=local_success,
        escalated_count=escalated,
        template_count=template_count,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        estimated_local_cost_usd=local_cost,
        estimated_cloud_savings_usd=savings_usd,
        success_rate=local_success / total if total > 0 else 0.0,
        baseline_all_cloud_usd=baseline_all_cloud_usd,
        actual_cloud_usd=actual_cloud_usd,
        savings_usd=savings_usd,
        savings_pct=savings_pct,
        local_inference_time_total_s=local_inference_time_total_s,
        local_tokens_total=local_tokens_total,
        decomposed_count=decomposed_count,
        decomposition_failure_count=decomposition_failure_count,
    )


def generate_experiment_result(
    seed_result: SeedResult,
    config: MicroPrimeConfig,
    run_id: str,
    collector: Optional[MetricsCollector] = None,
) -> dict[str, Any]:
    """Generate a JSON-serializable experiment result (REQ-MP-603).

    Returns a dict conforming to the experiment result schema v1.0.0.
    """
    cost_report = generate_cost_report(seed_result, config)

    trivial_count = 0
    trivial_passed = 0
    simple_count = 0
    simple_ast_before = 0
    simple_ast_after = 0
    simple_repaired = 0
    simple_verification_pass = 0
    simple_escalated = 0
    moderate_count = 0
    moderate_passed = 0
    complex_count = 0
    complex_passed = 0

    repair_summary = {
        "fence_stripped": 0,
        "trimmed": 0,
        "bare_wrapped": 0,
        "indent_normalized": 0,
        "signature_reconciled": 0,
        "imports_added": 0,
        "total_recovered": 0,
    }

    for fr in seed_result.file_results:
        for er in fr.element_results:
            if er.tier == TierClassification.TRIVIAL:
                trivial_count += 1
                if er.success:
                    trivial_passed += 1
            elif er.tier == TierClassification.SIMPLE:
                simple_count += 1
                if er.ast_valid_before_repair:
                    simple_ast_before += 1
                if er.ast_valid_after_repair:
                    simple_ast_after += 1
                if er.repair_recovered:
                    simple_repaired += 1
                if er.verification_verdict == "pass":
                    simple_verification_pass += 1
                if er.escalation is not None:
                    simple_escalated += 1
            elif er.tier == TierClassification.MODERATE:
                moderate_count += 1
                if er.success:
                    moderate_passed += 1
            else:
                complex_count += 1
                if er.success:
                    complex_passed += 1

            if er.repair_recovered:
                repair_summary["total_recovered"] += 1
            if er.repair_attribution:
                attr = er.repair_attribution
                if attr.fence_stripped:
                    repair_summary["fence_stripped"] += 1
                if attr.trimmed:
                    repair_summary["trimmed"] += 1
                if attr.bare_wrapped:
                    repair_summary["bare_wrapped"] += 1
                if attr.indent_source:
                    repair_summary["indent_normalized"] += 1
                if attr.params_changed > 0 or attr.return_type_restored:
                    repair_summary["signature_reconciled"] += 1
                repair_summary["imports_added"] += attr.imports_added

    summary = {
        "total_elements": seed_result.total_count,
        "trivial": {
            "count": trivial_count,
            "passed": trivial_passed,
        },
        "simple": {
            "count": simple_count,
            "ast_valid_before_repair": simple_ast_before,
            "ast_valid_after_repair": simple_ast_after,
            "repair_recovered": simple_repaired,
            "verification_pass": simple_verification_pass,
            "escalated": simple_escalated,
        },
        "moderate": {
            "count": moderate_count,
            "passed": moderate_passed,
        },
        "complex": {
            "count": complex_count,
            "passed": complex_passed,
        },
    }

    if collector is None:
        collector = MetricsCollector()
        for fr in seed_result.file_results:
            for er in fr.element_results:
                collector.record(er)

    elements = [m.model_dump() for m in collector.metrics]

    return {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": config.model_dump(),
        "summary": summary,
        "repair_summary": repair_summary,
        "cost": cost_report.model_dump(),
        "elements": elements,
    }
