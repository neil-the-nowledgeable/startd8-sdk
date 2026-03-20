"""OTel instrumentation for Security Prime — SP-OBS-001 through SP-OBS-013.

Emits spans, events, and metrics for Anzen gate executions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from startd8.logging_config import get_logger

logger = get_logger(__name__)

# Lazy tracer/meter — initialized on first use to avoid import-time side effects
_tracer: Optional[Any] = None
_meter: Optional[Any] = None


def _get_tracer() -> Any:
    """Get or create the security_prime tracer."""
    global _tracer
    if _tracer is None:
        try:
            from opentelemetry import trace
            _tracer = trace.get_tracer("security_prime")
        except ImportError:
            _tracer = None
    return _tracer


def _get_meter() -> Any:
    """Get or create the security_prime meter."""
    global _meter
    if _meter is None:
        try:
            from opentelemetry import metrics
            _meter = metrics.get_meter("security_prime")
        except ImportError:
            _meter = None
    return _meter


def record_gate_result(
    file_path: str,
    verdict: str,
    score: float,
    database: str,
    language: str,
    finding_count: int,
) -> None:
    """Record an Anzen gate result as OTel span + metrics.

    Args:
        file_path: Path to the verified file.
        verdict: "pass", "warn", or "fail".
        database: Detected database type.
        language: Source language.
        finding_count: Number of security findings.
    """
    tracer = _get_tracer()
    if tracer is not None:
        try:
            with tracer.start_as_current_span("security_prime.gate") as span:
                span.set_attribute("security.file_path", file_path)
                span.set_attribute("security.verdict", verdict)
                span.set_attribute("security.score", score)
                span.set_attribute("security.database", database)
                span.set_attribute("security.language", language)
                span.set_attribute("security.finding_count", finding_count)

                # SP-OBS-002: FAIL findings emit span events for Loki alerting
                if verdict == "fail":
                    span.add_event(
                        "security_violation",
                        attributes={
                            "file": file_path,
                            "database": database,
                            "findings": finding_count,
                        },
                    )
        except Exception as exc:
            logger.debug("OTel span recording failed: %s", exc)

    # Metrics (SP-OBS-003)
    meter = _get_meter()
    if meter is not None:
        try:
            score_histogram = meter.create_histogram(
                "security_prime.score",
                description="Security score per file",
            )
            score_histogram.record(score, {"database": database, "language": language})

            verdict_counter = meter.create_counter(
                "security_prime.gate_verdicts",
                description="Gate verdict counts",
            )
            verdict_counter.add(1, {"verdict": verdict, "database": database})
        except Exception as exc:
            logger.debug("OTel metric recording failed: %s", exc)
