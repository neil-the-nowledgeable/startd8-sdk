# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

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
    # Non-request workload profile (#226 FR-6/FR-6a). Bound to the OTel **messaging
    # semantic convention** (`messaging.process.*`) — the grounded convention for
    # queue/worker/stream job processing (OQ-5 established workers may emit NO native
    # metrics, so the series are convention-declared, not subject-sniffed). Maps a
    # worker's real SLIs onto the RED axes: job-processing duration → latency, its
    # histogram `_count` → throughput, `error.type` presence → failures. A worker
    # thus gets job-shaped SLOs (job p99 / job rate / job success), never
    # `http_server_duration`.
    "messaging-semconv": MetricDescriptor(
        profile="messaging-semconv",
        service_label_key="service",
        error_selector='error_type!=""',
        throughput_metric="messaging_process_duration_count",
        latency_bucket_metric="messaging_process_duration_bucket",
        latency_unit="s",
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

#: Service kinds that ARE request-servers — their descriptor comes from transport,
#: not a workload profile (#226 FR-6). Kept explicit so `profile_for_kinds` can tell
#: "this kind means use the transport default" from "no mapping".
REQUEST_KINDS = frozenset({"http_server", "grpc_server"})

#: Non-request workload kind → convention profile (#226 FR-6). The requirement is
#: this TABLE; adding a row (batch/cron with their own grounded series) is additive.
#: `stream`/`async_worker` share the messaging-semconv surface (queue/consumer job
#: processing). batch/cron are intentionally absent until their series are grounded
#: (OQ-5) rather than invented — they fall back to the transport default meanwhile.
_KIND_DEFAULTS = {
    "async_worker": "messaging-semconv",
    "stream": "messaging-semconv",
}

#: Recognized non-request workload kinds whose grounded metric series + threshold
#: magnitudes are deliberately deferred (OQ-5) — we KNOW them but will not invent a
#: profile for them (#230/#231/#233). Distinguishing "recognized-but-ungrounded" from
#: "unknown kind" lets the generator (a) SUPPRESS the incidental transport-derived RED
#: triple — so an `ml_inference` service that exposes an http health port does NOT get
#: a silent 500ms HTTP-latency SLO that passes review (#231's silent danger) — and
#: (b) emit an explicit coverage-gap entry instead of fabricating. Grounding a kind
#: later = move it into `_KIND_DEFAULTS`/`_KIND_SLI_DEFAULTS` and drop it from here.
UNGROUNDED_KINDS = frozenset({"batch", "cron", "ml_inference"})

#: The base RED triplet the OTel convention covers — the SINGLE source for "which signal_kinds are
#: the convention base SLIs" (#226). Imported by every seam that must agree on it so they can't drift:
#: the two-tier suppression gate (``artifact_generator._red``), the declared-series ``covers`` filter
#: (``artifact_generator_context._RED_KINDS``), and the convention-triplet skip/suppress in the
#: generators (``_TRIPLET_SIGNAL_KINDS``). Evolving the base set (e.g. grounding a 4th base kind)
#: is now ONE edit here — miss-one-copy silently re-opened the #274 dead-SLI class before this.
BASE_RED_KINDS = frozenset({"availability", "latency", "throughput"})

#: metrics_surface values (REQ-CCL-106) that do NOT emit the OTel-convention meter metric the base
#: RED SLIs query. Only ``otel_sdk_meter`` emits it; ``traces_only``/``none`` configure no meter, and
#: ``prometheus_exporter``/``node_metrics`` emit DIFFERENT names. #274: on any of these the base RED
#: SLI is dead, so the generator suppresses it + records the declared-but-absent gap. An empty
#: surface is UNKNOWN (don't suppress — the #277 advisory flags the risk instead).
NON_EMITTING_CONVENTION_SURFACES = frozenset(
    {"traces_only", "none", "prometheus_exporter", "node_metrics"}
)

#: metrics_surface values (REQ-CCL-106) that expose NO Prometheus ``/metrics`` scrape endpoint at all,
#: so a ServiceMonitor (a ``/metrics`` scrape config) targeting them is DEAD. Distinct from
#: ``NON_EMITTING_CONVENTION_SURFACES`` (which is about convention metric *names*):
#: ``prometheus_exporter``/``node_metrics`` DON'T emit the convention names but DO serve ``/metrics``,
#: so they keep their ServiceMonitor. Only ``traces_only`` (traces, no meter/endpoint) and ``none``
#: serve nothing to scrape. #285: suppress the ServiceMonitor for these + record the gap. Conservative:
#: ``otel_sdk_meter`` is unchanged (deployments may expose a Prometheus exporter alongside OTLP push).
NON_SCRAPEABLE_SURFACES = frozenset({"traces_only", "none"})

#: The signal_kind SHAPE that fits each ungrounded kind (#230/#231/#233) — the *which
#: SLI applies* axis, NOT a threshold VALUE (magnitudes stay gated on OQ-5 grounding).
#: Used only to make the coverage-gap hint kind-specific ("declare a freshness FR" for a
#: cron) instead of a generic four-option menu. A kind absent here falls back to the full
#: list via `suggested_signals_for`. cron/batch are run-window/exit shapes; ml_inference
#: is a saturation/lag shape — each asserted by its issue (#233/#230/#231 respectively).
_KIND_SUGGESTED_SIGNALS = {
    "cron": ("freshness", "run_success"),
    "batch": ("run_success", "freshness"),
    "ml_inference": ("saturation", "lag"),
}

#: The generic fallback shape when a kind has no specific suggestion — every non-request
#: signal_kind an author might ground a workload with.
_GENERIC_SUGGESTED_SIGNALS = ("run_success", "freshness", "saturation", "lag")


def suggested_signals_for(kind: str) -> "tuple[str, ...]":
    """The signal_kind shape(s) that fit an ungrounded ``kind`` (#230/#231/#233).

    Shape only — never a threshold value (those await OQ-5 grounding). Falls back to the
    generic non-request set for an unrecognized/unmapped kind so the hint is never empty.
    """
    return _KIND_SUGGESTED_SIGNALS.get(kind, _GENERIC_SUGGESTED_SIGNALS)


#: The canonical service-kind vocabulary CR-3 emits (mirrors ContextCore's
#: ``contracts/types.py::ServiceKind``; keep in sync, do not extend unilaterally). The SDK
#: partitions every non-``unknown`` kind into exactly one of REQUEST_KINDS / grounded
#: (`_KIND_DEFAULTS`) / UNGROUNDED_KINDS; a drift test asserts that partition so a kind
#: added upstream can't fall silently to the transport default. ``unknown`` is the
#: producer's "no signal" sentinel and is intentionally handled by the fallback path.
CANONICAL_SERVICE_KINDS = frozenset({
    "http_server", "grpc_server", "async_worker", "stream",
    "batch", "cron", "ml_inference", "unknown",
})

#: The three RED SLI kinds a request-server (or a job worker, on its messaging series)
#: is observed by absent any declaration (#226 FR-12). Its home is here beside the kind
#: tables so the determination model has a single source of truth.
_REQUEST_SLI_KINDS = frozenset({"latency", "availability", "throughput"})

#: Kind → the SLI-kind set it implies absent per-FR declaration (#226 FR-12). Request
#: kinds and job workers/streams resolve to the RED triple (a worker's RED rides its
#: messaging descriptor, so "throughput"=job rate, "availability"=job success). cron/
#: batch (freshness/run_success shapes) are intentionally deferred with their FR-6
#: profiles — an unmapped kind contributes no implied set (falls to the transport tier).
_KIND_SLI_DEFAULTS = {
    "http_server": _REQUEST_SLI_KINDS,
    "grpc_server": _REQUEST_SLI_KINDS,
    "async_worker": _REQUEST_SLI_KINDS,
    "stream": _REQUEST_SLI_KINDS,
}


def resolve_sli_kinds(
    kinds: Optional[Iterable[str]] = None,
    signal_kinds: Optional[Iterable[str]] = None,
    transport: str = "",
) -> "frozenset[str]":
    """The set of SLI kinds a service is observed by (#226 FR-12) — the determination
    core. The RED base applies when the service is **request-serving** (a request
    transport, or a request/worker ``kind``); declared per-FR ``signal_kinds`` (from
    ``functional[]``) are **additive** on top (OQ-6). A non-request service (no
    request transport, no mapped kind) gets only what it declares — ``frozenset()``
    when it declares nothing (the ∅ that FR-9 reports and FR-13 treats as "synthesize
    nothing"). Byte-parity: a plain http/grpc service with no kind/FRs ⇒ the RED
    triple, identical to pre-#226.
    """
    kinds = list(kinds or ())
    resolved: set[str] = set(signal_kinds or ())          # declared FR signals (additive)
    for kind in kinds:
        resolved |= set(_KIND_SLI_DEFAULTS.get(kind, ()))  # kind-implied RED base
    # #231: a service DECLARED as a recognized-but-ungrounded workload (batch/cron/
    # ml_inference) whose transport is incidental (no request kind also declared) must
    # NOT inherit the transport RED triple — that is the silent 500ms-HTTP-latency SLO
    # that lets an ML service pass review. Suppress the transport base for it; it still
    # gets exactly what it DECLARES via functional[] signal_kinds (additive, above).
    incidental_transport = (
        any(k in UNGROUNDED_KINDS for k in kinds)
        and not any(k in REQUEST_KINDS for k in kinds)
    )
    if (transport or "").lower() in _TRANSPORT_DEFAULTS and not incidental_transport:
        resolved |= _REQUEST_SLI_KINDS                     # request-transport RED base
    return frozenset(resolved)


def profile_for_kinds(kinds: Iterable[str], transport: str) -> MetricDescriptor:
    """Descriptor for a service by its workload kind(s), kind winning over transport
    (#226 FR-6). Empty kinds ⇒ the transport default (byte-identical to pre-#226).

    Resolution: the first kind with a non-request workload mapping wins. If no kind
    maps to a workload profile — including hybrids that also serve requests
    (``http_server`` + ``async_worker``) — fall back to the transport default (the
    request surface); a hybrid's worker SLIs are added by the FR-5 signal_kind
    derivation, not the single request-shaped descriptor.
    """
    kinds = list(kinds or ())
    # A hybrid that also serves requests keeps the request surface as its primary
    # descriptor (so its http/grpc RED triplet is intact); its worker SLIs are added
    # by the FR-5 signal_kind derivation, not this single-shape descriptor.
    if any(k in REQUEST_KINDS for k in kinds):
        return profile_for_transport(transport)
    for kind in kinds:
        mapped = _KIND_DEFAULTS.get(kind)
        if mapped:
            return _PROFILES[mapped]
    return profile_for_transport(transport)


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
    kinds: Optional[Iterable[str]] = None,
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
    # Precedence (#226 FR-6): an explicit resolved `profile` (manifest/ContextCore)
    # still wins; else a declared workload `kind` wins over transport; else the
    # transport default. Empty kinds ⇒ transport default (byte-identical to pre-#226).
    if profile:
        try:
            base = profile_for(profile)
        except ValueError:
            logger.warning(
                "unknown metric convention profile %r in onboarding metadata; "
                "falling back to semconv-%s", profile, transport,
            )
            base = profile_for_transport(transport)
    elif kinds:
        base = profile_for_kinds(kinds, transport)
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
