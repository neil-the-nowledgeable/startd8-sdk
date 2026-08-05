"""Canonical RED metric convention — the ONE importable source of the RED PromQL a
consumer needs, so it never has to mirror the shape.

Requested by ContextCore's legacy-generator convergence (§4,
``docs/CONTEXTCORE_GENERATOR_CONVERGENCE_NEEDS_2026-08-05.md``): before this module the
canonical error-ratio / p99 exprs were built inline in the artifact generator and the
family names lived in ``observability_fidelity_static`` + ``red_taxonomy`` with no single
import, so a consumer that wanted "the canonical HTTP error-ratio expr" had to duplicate
it — the exact drift ``red_taxonomy`` exists to kill, one level up. This closes it at the
source: ``canonical_red_exprs(descriptor, service)`` returns the RED exprs keyed by
:class:`RedRole`, and the artifact generator itself builds from here (single source).
"""

from __future__ import annotations

from typing import Any, Dict

from startd8.observability.red_taxonomy import RedRole

_RATE_WINDOW = "$__rate_interval"


def canonical_red_exprs(
    descriptor: Any,
    service_id: str = "",
    *,
    rate_window: str = _RATE_WINDOW,
) -> Dict[RedRole, str]:
    """The canonical Rate / Error / Duration PromQL for a service, built from its resolved
    :class:`~startd8.observability.metric_descriptor.MetricDescriptor` — the **same** shape
    the artifact generator emits.

    A role is present only when the descriptor carries its identity (FR-4a null-safety):
    no ``throughput_metric`` ⇒ no RATE/ERROR; empty ``error_selector`` (e.g. Harbor
    jobservice — no error dimension) ⇒ no ERROR; empty ``latency_bucket_metric`` (a
    summary-latency subject — Harbor core) ⇒ no DURATION.
    """
    tm = getattr(descriptor, "throughput_metric", "") or ""
    lb = getattr(descriptor, "latency_bucket_metric", "") or ""
    err_sel = getattr(descriptor, "error_selector", "") or ""
    total = descriptor.selector(service_id)
    error = descriptor.selector(service_id, error=True)

    out: Dict[RedRole, str] = {}
    if tm:
        out[RedRole.RATE] = f"sum(rate({tm}{total}[{rate_window}]))"
        if err_sel:
            out[RedRole.ERROR] = (
                f"sum(rate({tm}{error}[{rate_window}]))\n"
                f"/ sum(rate({tm}{total}[{rate_window}]))"
            )
    if lb:
        out[RedRole.DURATION] = (
            f"histogram_quantile(0.99, rate({lb}{total}[{rate_window}]))"
        )
    return out


def red_http(service_id: str = "") -> Dict[RedRole, str]:
    """Convenience: the canonical RED exprs for the default HTTP semconv profile —
    ``rate(http_server_duration_count…)`` etc. The stable "RED_HTTP" a consumer can import
    instead of hardcoding ``http_requests_total{status=~"5.."}`` (the divergent legacy shape)."""
    from startd8.observability.metric_descriptor import profile_for

    return canonical_red_exprs(profile_for("semconv-http"), service_id)
