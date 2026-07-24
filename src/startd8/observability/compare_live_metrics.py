# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""OTel metrics for the compare-live gate (FR-11 / backlog OP-1).

Emits the derived-vs-emitted gate verdict so o11y *fidelity itself* is trendable in
Grafana — "is my generated o11y getting more or less real over time?" — instead of a
per-run exit code. All recording is **no-op safe**: without a configured MeterProvider
(or without OTel installed) the instruments are NoOp and nothing is emitted. Mirrors the
guarded lazy-init pattern of ``costs/otel_metrics.py``.

The short-lived CLI exports these via the atexit force-flush that ``otel.configure_otel``
registers; the ``--emit-metrics`` handler bootstraps that provider from
``OTEL_EXPORTER_OTLP_ENDPOINT`` when one isn't already set.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import urlparse

try:
    from opentelemetry import metrics as _otel_metrics
    _OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only where OTel is absent
    _otel_metrics = None  # type: ignore[assignment]
    _OTEL_AVAILABLE = False

_METER_NAME = "startd8.observability.compare_live"

#: Observability-manifest descriptor (zero runtime cost; consumed by manifest generation).
_OTEL_DESCRIPTORS = {
    "category": "ai_agent_observability",
    "orientation": "system",
    "metrics": [
        {"name": "startd8.observability.compare_live.gate_runs", "instrument": "counter",
         "unit": "1", "meter": _METER_NAME, "labels": ["status", "subject"],
         "description": "compare-live gate runs by verdict status"},
        {"name": "startd8.observability.compare_live.dead_sli_count", "instrument": "histogram",
         "unit": "1", "meter": _METER_NAME, "labels": ["subject"],
         "description": "dead (fail) SLIs in a compare-live run"},
        {"name": "startd8.observability.compare_live.new_fail_count", "instrument": "histogram",
         "unit": "1", "meter": _METER_NAME, "labels": ["subject"],
         "description": "new-vs-baseline dead SLIs (regressions) in a gated run"},
        {"name": "startd8.observability.compare_live.binding_coverage", "instrument": "histogram",
         "unit": "1", "meter": _METER_NAME, "labels": ["subject"],
         "description": "Tier-B binding coverage of the derived SLIs (0..1)"},
    ],
}


def subject_label(subject_image: Optional[str], prometheus: Optional[str]) -> str:
    """A safe `subject` attribute — the image, or the Prometheus **hostname** only.

    Never the full ``--prometheus`` URL (it may carry credentials/params — FR-7 redaction)."""
    if subject_image:
        return subject_image
    if prometheus:
        return urlparse(prometheus).hostname or "unknown"
    return "unknown"


class _GateMetrics:
    """Lazy-initialised instruments; every method is a no-op when OTel is unavailable."""

    def __init__(self) -> None:
        self._initialized = False
        self._meter = None
        self._runs = None
        self._dead = None
        self._new = None
        self._coverage = None

    def _ensure(self) -> bool:
        if self._initialized:
            return self._meter is not None
        self._initialized = True
        if not _OTEL_AVAILABLE:
            return False
        try:
            self._meter = _otel_metrics.get_meter(_METER_NAME)
        except Exception:  # noqa: BLE001 - degrade to no-op on any meter error
            return False
        self._runs = self._meter.create_counter(
            "startd8.observability.compare_live.gate_runs", unit="1",
            description="compare-live gate runs by verdict status")
        self._dead = self._meter.create_histogram(
            "startd8.observability.compare_live.dead_sli_count", unit="1",
            description="dead (fail) SLIs in a compare-live run")
        self._new = self._meter.create_histogram(
            "startd8.observability.compare_live.new_fail_count", unit="1",
            description="new-vs-baseline dead SLIs (regressions) in a gated run")
        self._coverage = self._meter.create_histogram(
            "startd8.observability.compare_live.binding_coverage", unit="1",
            description="Tier-B binding coverage of the derived SLIs (0..1)")
        return True

    def record(self, report: Any, new_fail_count: int, subject: str) -> bool:
        """Record one gate run. Returns True if it reached a live meter (else no-op)."""
        if not self._ensure():
            return False
        d: Dict[str, Any] = report.to_dict()
        subj = {"subject": subject}
        self._runs.add(1, {"status": str(d.get("status", "unknown")), **subj})
        self._dead.record(len(d.get("fail_verdicts") or []), subj)
        self._new.record(int(new_fail_count), subj)
        tier_b = d.get("tier_b") or {}
        self._coverage.record(float(tier_b.get("binding_coverage", 0.0) or 0.0), subj)
        return True


_GATE_METRICS = _GateMetrics()


def record_gate_metrics(report: Any, new_fail_count: int, subject: str) -> bool:
    """Module-level entry point (mirrors ``costs`` usage). No-op safe."""
    return _GATE_METRICS.record(report, new_fail_count, subject)


__all__ = ["record_gate_metrics", "subject_label", "_OTEL_DESCRIPTORS"]
