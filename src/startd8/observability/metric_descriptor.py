# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Metric-shape descriptor and named convention profiles.

Implements Step 2 of ContextCore ``REQ_TARGET_METRIC_BINDING.md`` (FR-1, FR-1a,
FR-5). A :class:`MetricDescriptor` decouples *metric identity* (name, label key,
error selector, unit) from the hardcoded PromQL templates in
``artifact_generator_generators.py``, so generated artifacts can bind to a
target's *real* metric surface instead of transport-inferred convention names.

Two OTel metric surfaces are **co-equal, first-class** targets (FR-5a):

* the **OTel SDK semantic conventions** (``semconv-http`` / ``semconv-grpc``) —
  ``http_server_duration`` / ``rpc_server_duration``, label ``service``, unit ``s``;
* the **OTel Collector span-metrics connector** (``span-metrics-connector``) —
  ``calls_total`` / ``duration_milliseconds``, label ``service_name``, unit ``ms``,
  error dimension ``status_code="STATUS_CODE_ERROR"``.

The preset values below are the implementation of the **normative FR-5 table**
in ``REQ_TARGET_METRIC_BINDING.md`` (single source of truth). Keep them in sync
with that table; do not fork the values.

This module is intentionally standalone: it defines the descriptor and the
presets only. Wiring the descriptor into the generators is Step 3; building it
from manifest/onboarding inputs via the FR-7 precedence ladder is Step 4.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, fields, replace
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MetricDescriptor:
    """The metric shape a service exposes, across all four mismatch axes.

    Frozen so a resolved descriptor can be safely shared across generators.
    Full metric names are stored (not assembled from suffixes) to keep query
    construction unambiguous across the histogram-derived (semconv) and
    dedicated-counter (span-metrics) throughput shapes.
    """

    #: Originating profile name, or ``"custom"`` when built from explicit axes.
    profile: str

    # --- axis 1: service-identity label -------------------------------------
    #: Label key that carries the service name (``service`` vs ``service_name``).
    service_label_key: str
    #: Template for the label *value*; ``{service_id}`` is substituted.
    service_label_value_tpl: str = "{service_id}"

    # --- axis 2: error selector ---------------------------------------------
    #: Matcher isolating errors, e.g. ``status=~"5.."`` or
    #: ``status_code="STATUS_CODE_ERROR"``. Empty ⇒ error/availability queries
    #: are skipped for this service.
    error_selector: str = ""

    # --- axis 3: metric names ------------------------------------------------
    #: Counter used for throughput and the error/availability ratio
    #: (``calls_total`` or the histogram-derived ``*_duration_count``).
    throughput_metric: str = ""
    #: Histogram ``*_bucket`` series used for latency quantiles.
    latency_bucket_metric: str = ""

    # --- axis 4: unit (drives FR-4a threshold scaling) ----------------------
    #: ``"s"`` or ``"ms"``. ``histogram_quantile`` returns values in this unit,
    #: so latency thresholds must be emitted in it (500ms ⇒ ``> 0.5`` for ``s``,
    #: ``> 500`` for ``ms``).
    latency_unit: str = "s"

    # --- ancillary PromQL knobs ---------------------------------------------
    rate_window: str = "5m"
    quantile: float = 0.99

    # --- compound selectors (FR-1) ------------------------------------------
    #: Extra matchers ANDed into every selector, e.g.
    #: ``('span_kind="SPAN_KIND_SERVER"',)`` — span-metrics often needs a
    #: server-kind filter to avoid double-counting client spans.
    extra_selectors: Tuple[str, ...] = ()

    # --- FR-1a: non-RED / non-PromQL artifacts ------------------------------
    #: LogQL stream label for ``generate_loki_rule``; empty ⇒ reuse
    #: :attr:`service_label_key` (the PromQL and LogQL label keys may differ).
    logql_label_key: str = ""
    #: Label key identifying the database engine on DB panels.
    db_system_label_key: str = "db_system"

    # ------------------------------------------------------------------ helpers
    def service_matcher(self, service_id: str) -> str:
        """``service_name="checkoutservice"`` — the identity matcher only."""
        value = self.service_label_value_tpl.format(service_id=service_id)
        return f'{self.service_label_key}="{value}"'

    def selector(self, service_id: str, *, error: bool = False) -> str:
        """A full ``{...}`` label selector for *service_id*.

        Includes the identity matcher, any :attr:`extra_selectors`, and — when
        *error* is true — the :attr:`error_selector`.
        """
        parts = [self.service_matcher(service_id), *self.extra_selectors]
        if error and self.error_selector:
            parts.append(self.error_selector)
        return "{" + ",".join(parts) + "}"

    def logql_stream_key(self) -> str:
        """LogQL stream label key (FR-1a), falling back to the PromQL key."""
        return self.logql_label_key or self.service_label_key

    def scale_threshold_seconds(self, seconds: float) -> float:
        """Scale a seconds-valued threshold into the descriptor's unit (FR-4a).

        ``500ms`` parses to ``0.5`` seconds upstream; a ``ms`` descriptor must
        emit ``500``. Returns a value comparable against ``histogram_quantile``
        output for this descriptor.
        """
        return seconds * 1000.0 if self.latency_unit == "ms" else seconds


# ---------------------------------------------------------------------------
# Named profiles — normative FR-5 table (single source of truth).
# ---------------------------------------------------------------------------
_PROFILES: Dict[str, MetricDescriptor] = {
    "semconv-http": MetricDescriptor(
        profile="semconv-http",
        service_label_key="service",
        error_selector='status=~"5.."',
        throughput_metric="http_server_duration_count",
        latency_bucket_metric="http_server_duration_bucket",
        latency_unit="s",
    ),
    "semconv-grpc": MetricDescriptor(
        profile="semconv-grpc",
        service_label_key="service",
        error_selector='grpc_code=~"Unavailable|Internal|Unimplemented|DataLoss"',
        throughput_metric="rpc_server_duration_count",
        latency_bucket_metric="rpc_server_duration_bucket",
        latency_unit="s",
    ),
    "span-metrics-connector": MetricDescriptor(
        profile="span-metrics-connector",
        service_label_key="service_name",
        error_selector='status_code="STATUS_CODE_ERROR"',
        throughput_metric="calls_total",
        latency_bucket_metric="duration_milliseconds_bucket",
        latency_unit="ms",
    ),
}

#: Profiles that model the OTel SDK semantic-convention surface (FR-5a).
SEMCONV_PROFILES = ("semconv-http", "semconv-grpc")
#: Profile modelling the OTel Collector span-metrics surface (FR-5a).
SPAN_METRICS_PROFILE = "span-metrics-connector"

#: Transport → default SDK-semconv profile (FR-7 tier 6 back-compat default).
_TRANSPORT_DEFAULTS = {
    "grpc": "semconv-grpc",
    "grpc-web": "semconv-grpc",
    "http": "semconv-http",
}


def available_profiles() -> Tuple[str, ...]:
    """Names of all built-in convention profiles."""
    return tuple(_PROFILES)


def match_profiles(metric_names: Iterable[str]) -> List[str]:
    """Which built-in profiles does a live backend's metric set actually match?

    Given the metric names a running Prometheus emits, return the profiles whose
    **signature metrics** — the throughput + latency-bucket names of the FR-5
    table — are ALL present. In other words: which conventions is the target
    *really* using. An empty result means no built-in profile matches (a per-axis
    descriptor override is needed).

    This is the single canonical profile-matcher, reused by the ``detect-profile``
    CLI (an authoring aid) and by the ``validate-promql`` suggested-fix — so the
    two never drift.
    """
    names = set(metric_names)
    return [
        name
        for name, d in _PROFILES.items()
        if d.throughput_metric in names and d.latency_bucket_metric in names
    ]


def profile_signatures() -> Dict[str, Tuple[str, str]]:
    """``{profile_name: (throughput_metric, latency_bucket_metric)}`` for all profiles.

    The signature metrics ``match_profiles`` keys on, exposed so authoring aids
    (the ``detect-profile`` CLI) can show *which* series each profile needs and
    which are present live — without reaching into the private ``_PROFILES`` map.
    """
    return {
        name: (d.throughput_metric, d.latency_bucket_metric)
        for name, d in _PROFILES.items()
    }


def profile_for(name: str) -> MetricDescriptor:
    """Resolve a named convention profile to its :class:`MetricDescriptor`.

    Accepts the three built-in profile names (FR-5) and the back-compat aliases
    ``semconv-{transport}``. Raises :class:`ValueError` on an unknown name so a
    typo fails loudly rather than silently falling back.
    """
    if name in _PROFILES:
        return _PROFILES[name]
    raise ValueError(
        f"unknown metric convention profile {name!r}; "
        f"expected one of {', '.join(sorted(_PROFILES))}"
    )


def profile_for_transport(transport: str) -> MetricDescriptor:
    """The default SDK-semconv descriptor for *transport* (FR-7 tier 6).

    Unknown transports fall back to ``semconv-http`` (matching today's
    generator behavior, where ``http`` is the transport default).
    """
    name = _TRANSPORT_DEFAULTS.get((transport or "").lower(), "semconv-http")
    return _PROFILES[name]


#: MetricDescriptor axis fields an override block may set (FR-1/FR-1a). Anything
#: else in an overrides dict is unknown and ignored-with-warning (FR-3 skew).
_OVERRIDABLE_AXES = frozenset(
    f.name for f in fields(MetricDescriptor) if f.name != "profile"
)


def resolve_descriptor(
    *,
    profile: Optional[str] = None,
    transport: str = "http",
    overrides: Optional[Dict[str, Any]] = None,
) -> MetricDescriptor:
    """Build the effective descriptor for a service (terminus of the FR-7 ladder).

    ContextCore resolves project-vs-target precedence at export and passes the
    *effective* ``profile`` + ``overrides`` here (via onboarding metadata). This
    function applies the last two ladder tiers and the axis overrides:

    * ``profile`` — the resolved convention profile name, or ``None`` to fall
      back to ``semconv-{transport}`` (tier 6, today's behavior).
    * ``overrides`` — per-axis values that override the profile field-by-field
      (FR-1 escape hatch / FR-7 tier-1 descriptor).

    FR-3 leniency: an **unknown profile name** logs a warning and falls back to
    the transport default rather than raising (so a newer manifest cannot crash
    an older generator); **unknown override keys** are ignored with a warning.
    ``profile_for`` stays strict for authoring-time validation.
    """
    if profile:
        try:
            base = profile_for(profile)
        except ValueError:
            logger.warning(
                "unknown metric convention profile %r in onboarding metadata; "
                "falling back to semconv-%s", profile, transport,
            )
            base = profile_for_transport(transport)
    else:
        base = profile_for_transport(transport)

    if not overrides:
        return base

    known: Dict[str, Any] = {}
    for key, value in overrides.items():
        if key in _OVERRIDABLE_AXES:
            known[key] = tuple(value) if key == "extra_selectors" else value
        else:
            logger.warning(
                "ignoring unknown metric descriptor override %r=%r "
                "(not a recognized axis)", key, value,
            )
    if not known:
        return base
    return replace(base, profile=f"{base.profile}+override", **known)
