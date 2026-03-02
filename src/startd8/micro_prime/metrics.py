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
        self._metrics.append(
            MicroPrimeElementMetrics(
                element_name=result.element_name,
                file_path=result.file_path,
                tier=result.tier,
                success=result.success,
                template_used=result.template_used,
                repair_steps=result.repair_steps_applied,
                repair_attribution=result.repair_attribution,
                generation_time_ms=result.generation_time_ms,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
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

    for fr in seed_result.file_results:
        for er in fr.element_results:
            tier_counts[er.tier] = tier_counts.get(er.tier, 0) + 1
            total_input += er.input_tokens
            total_output += er.output_tokens
            if er.success:
                local_success += 1
            if er.escalation is not None:
                escalated += 1
            if er.template_used:
                template_count += 1

    total = seed_result.total_count

    # Local cost is effectively zero for Ollama
    local_cost = (
        total_input * _LOCAL_COST_PER_M_INPUT / 1_000_000
        + total_output * _LOCAL_COST_PER_M_OUTPUT / 1_000_000
    )

    # Estimated savings: what it would have cost to send successful elements to cloud
    cloud_cost_for_local = (
        total_input * _CLOUD_COST_PER_M_INPUT / 1_000_000
        + total_output * _CLOUD_COST_PER_M_OUTPUT / 1_000_000
    )

    return MicroPrimeCostReport(
        total_elements=total,
        trivial_count=tier_counts.get(TierClassification.TRIVIAL, 0),
        simple_count=tier_counts.get(TierClassification.SIMPLE, 0),
        moderate_count=tier_counts.get(TierClassification.MODERATE, 0),
        complex_count=tier_counts.get(TierClassification.COMPLEX, 0),
        local_success_count=local_success,
        escalated_count=escalated,
        template_count=template_count,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        estimated_local_cost_usd=local_cost,
        estimated_cloud_savings_usd=cloud_cost_for_local,
        success_rate=local_success / total if total > 0 else 0.0,
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

    elements: list[dict[str, Any]] = []
    if collector:
        for m in collector.metrics:
            elements.append(m.model_dump())

    return {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": config.model_dump(),
        "summary": cost_report.model_dump(),
        "elements": elements,
    }
