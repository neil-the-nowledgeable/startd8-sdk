# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Data models for observability artifact generation.

Extracted verbatim from ``artifact_generator.py`` (Tier-2 refactor, step 1).
Pure dataclasses with no dependency on the generator logic. ``artifact_generator``
re-exports these (``from .artifact_generator_models import *``) so existing
import paths keep working.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple  # noqa: F401

from .spec import Receiver

@dataclass
class ConventionMetric:
    """A single OTel convention-based metric expected for a service."""

    name: str  # e.g. "rpc.server.duration"
    type: str  # e.g. "histogram", "counter"
    source: str  # e.g. "otel_semconv:grpc"
    # REQ-OAT-024 "declare, don't guess": when onboarding metadata carries the
    # structural facts, read them; otherwise the classifier infers (and records
    # the inference). "" = not declared upstream.
    category: str = ""        # declared five-category taxonomy, if present
    route_state: str = ""     # declared route_state, if present (e.g. onboarding_bridge sets sdk_emitted)


@dataclass
class DeclaredEmittedSeries:
    """An author-declared REAL emitted Prometheus series a base RED SLI can bind to
    (#286 / REQ-CCL-107 Part B).

    Carried on ``instrumentation_hints[svc].metrics.declared_emitted_series``. Distinct from
    ``ConventionMetric`` (which has no labels and no RED-kind mapping): this says "series *name*,
    selected by *labels*, grounds these base RED *kinds*" — so the SDK can bind the base SLI to a
    real series (e.g. ``sidekiq_job_duration_seconds{job_name=...}``) instead of the #274
    suppress-or-fabricate. Explicit-only (never inferred): absence ⇒ the SDK keeps #274 suppression.
    """

    name: str  # the REAL emitted series name, e.g. "http_request_duration_seconds"
    type: str = ""  # "histogram" | "counter" | "gauge"
    #: the selector labels the series actually carries ({job_name}, {queue_name}, {type,method,status})
    #: — NOT necessarily service.name. Rendered verbatim into the PromQL selector.
    labels: Dict[str, str] = field(default_factory=dict)
    #: which base RED kinds this series can ground; subset of {availability, latency, throughput}.
    covers: List[str] = field(default_factory=list)
    #: #286 v2: the PromQL matcher fragment selecting the ERROR subset (e.g. ``status=~"5.."``),
    #: needed to build the availability good/total ratio. Empty ⇒ availability stays *deferred* (a
    #: correct ratio can't be built without it); latency/throughput never need it.
    error_selector: str = ""
    enabling_flag: str = ""  # advisory only: the deploy flag that turns the series on. Not load-bearing.
    #: #300 D2 (FR-3): optional author-supplied SLO objective for a FUNCTIONAL kind this series covers
    #: (saturation/queue_depth/lag/…). A raw PromQL/objective string, mirroring
    #: ``FunctionalRequirement.target`` — NOT a float. Absent (``None``) ⇒ the functional SLI binds its
    #: query but is *threshold-deferred* (no SLO written); the SDK never synthesizes a target (NR-1).
    target: Optional[str] = None
    #: contextcore#404: the producer-stamped unit of the series (``"seconds"``/``"milliseconds"``/…).
    #: When present it OVERRIDES the SDK's name-suffix inference for latency threshold scaling — the
    #: producer read the metric, so it beats the guess (retires the fragile inference on suffix-less
    #: names like ``harbor_task_queue_latency``). Absent/unrecognized ⇒ name-inference (byte-identical).
    unit: str = ""


@dataclass
class DeclaredSpanSignal:
    """An author-declared span (name) whose span-metrics RED an SLI can bind to (#307 / option-b1).

    The trace-surface analogue of :class:`DeclaredEmittedSeries`: instead of a Prometheus series
    selected by labels, it names a **span** (e.g. ``FeedInsertWorker``) whose span-metrics connector /
    Tempo metrics-generator RED series (``traces_spanmetrics_*{service_name, span_name}``) an SLI binds
    to — carrying the real ``service.name`` (#275). Carried on
    ``instrumentation_hints[svc].metrics.declared_span_signals`` (ContextCore REQ-CCL-109). Explicit-only
    (never inferred): absence ⇒ no span binding (byte-identical)."""

    name: str  # the declared span name, e.g. "FeedInsertWorker" (bound as span_name="...")
    #: extra span attributes ANDed into the selector (rendered only when non-empty, #300-A discipline).
    attributes: Dict[str, str] = field(default_factory=dict)
    #: which base RED kinds this span grounds (subset of {availability, latency, throughput}); v1 = RED.
    covers: List[str] = field(default_factory=list)
    #: the error matcher fragment for the availability good/total ratio; empty ⇒ use the descriptor's
    #: (Tempo ``status_code="STATUS_CODE_ERROR"``), and if neither, availability stays deferred.
    error_selector: str = ""
    #: forward-compat (functional-over-span, out of v1 scope): author SLO objective, else deferred.
    target: Optional[str] = None
    enabling_flag: str = ""  # advisory only: the flag/connector that turns the span-metrics on.


@dataclass
class DeclaredProbe:
    """An author-declared SYNTHETIC PROBE for a signal the subject emits no metric for (#308 P0 / option-b2).

    Grounds a *derive-value* SLI — e.g. Mastodon fan-out freshness (create-status → feed-visible latency),
    which is cross-trace (``propagation_style: :link``) so neither a scrape (#286) nor a span-metrics
    connector (#307) can produce it. The author declares the probe SHAPE (do X, poll until Y, measure the
    delta); the threshold stays inferred. **P0 is static/$0**: it records the derived SLO in
    ``pending_probes`` (no SLO YAML on disk — a query on the not-yet-published metric would be replayed as a
    dead SLI); the runner + live binding are P1/P2. ``action``/``poll``/``assert_`` are carried opaque (P0
    never executes them). Carried on ``instrumentation_hints[svc].metrics.declared_probes``."""

    name: str  # probe id, e.g. "fanout_freshness" (drives the default metric probe_<name>_seconds)
    action: str = ""     # opaque: the request that triggers the behaviour (P1 runs it), e.g. POST /statuses
    poll: str = ""       # opaque: what to poll until the assertion holds, e.g. GET /timelines/home
    assert_: str = ""    # opaque: the assertion that ends the measurement (id visible)
    measure: str = ""    # opaque: what delta is measured, e.g. t(visible) - t(created)
    interval: str = "60s"
    timeout: str = "30s"
    #: v1 = "freshness" only; any other kind defers (no query shape defined for a synthetic availability yet).
    signal_kind: str = "freshness"
    #: the metric the runner (P1) will publish + the SLI (P0) queries — single-sourced. Empty ⇒ default
    #: ``probe_<name>_seconds``. For a histogram probe the runner publishes ``<published_metric>_bucket``.
    published_metric: str = ""
    #: closed enum ``gauge|histogram`` — the query shape; any other value defers (never a fabricated query).
    metric_kind: str = "gauge"
    #: author SLO objective; absent ⇒ threshold-deferred (the SDK never infers a freshness threshold, NR-1).
    target: Optional[str] = None


@dataclass
class ServiceHints:
    """Instrumentation hints for a single service."""

    service_id: str
    # #275: the subject's real OTel `service.name` (slash preserved, e.g. "mastodon/web"),
    # carried on instrumentation_hints[svc].service_name (contextcore#39/#40). Distinct from
    # the sanitized graph `service_id` ("mastodonweb"). Used as the SLI label VALUE so the
    # selector matches real telemetry; absent ⇒ fall back to service_id (byte-identical).
    service_name: str = ""
    # #274 (ADR-003): the subject carries trace instrumentation (a `traces` block). With
    # convention metrics but NO manifest_declared, this is the traces-only RISK profile —
    # the base SLIs rest on an unverified convention metric. Advisory only (see fr_coverage).
    has_traces: bool = False
    # #274 / REQ-CCL-106: the subject's DECLARED metrics emission surface, when ContextCore
    # captured an explicit self-declaration — `otel_sdk_meter | traces_only | prometheus_exporter
    # | node_metrics | none`. Empty ⇒ unknown (SDK falls back to the #277 advisory, never a
    # fabricated gap). Anything but `otel_sdk_meter` means the OTel-convention meter metric the
    # base RED SLIs query is NOT emitted → suppress those SLIs + record the declared-but-absent gap.
    metrics_surface: str = ""
    # FR-14 (#226): optional — a service that declares a `kind` need not have a
    # listen transport (workers/cron/batch don't). Absent transport + absent kinds
    # is still skipped upstream (extract_service_hints).
    transport: str = ""  # "grpc" | "http" | "" (non-request workload)
    language: Optional[str] = None
    # FR-12b (#226): service workload kind(s), producer-supplied (CR-3). Modeled as
    # one-or-more to support hybrid services (e.g. http_server + async_worker). Empty
    # ⇒ determination falls back to transport (byte-identical to pre-#226).
    kinds: List[str] = field(default_factory=list)
    detected_databases: List[str] = field(default_factory=list)
    convention_metrics: List[ConventionMetric] = field(default_factory=list)
    # Domain-specific metrics declared in the manifest (Closure 1 / Gap 1).
    # Distinct from convention_metrics: these describe what *this* service does
    # (e.g. token burn, cost, truncations) rather than generic OTel HTTP semconv.
    declared_metrics: List[ConventionMetric] = field(default_factory=list)
    # #286 / REQ-CCL-107: author-declared REAL emitted series the base RED SLIs can bind to
    # (name + labels + which RED kinds they ground). Explicit-only; absent ⇒ keep #274 suppression.
    declared_emitted_series: List[DeclaredEmittedSeries] = field(default_factory=list)
    # #307 / REQ-CCL-109: author-declared SPAN signals whose span-metrics RED an SLI can bind to
    # (span_name + covers). The trace-surface analogue of declared_emitted_series; explicit-only.
    declared_span_signals: List[DeclaredSpanSignal] = field(default_factory=list)
    # #308 P0: author-declared synthetic probes for a signal the subject emits no metric for
    # (fan-out freshness). Recorded as pending_probes (P0 is static/$0); explicit-only.
    declared_probes: List[DeclaredProbe] = field(default_factory=list)
    # Target metric binding (REQ_TARGET_METRIC_BINDING FR-2/FR-3/FR-6): the
    # effective convention profile ContextCore resolved for this service, plus
    # any per-axis descriptor overrides. "" / {} => fall back to the transport
    # default (semconv-{transport}). Consumed by metric_descriptor.resolve_descriptor.
    metric_profile: str = ""
    descriptor_overrides: Dict[str, Any] = field(default_factory=dict)
    # Datasource UID binding (REQ_DATASOURCE_UID_BINDING FR-3): the effective Grafana
    # datasource UIDs ContextCore resolved for this service, keyed by kind
    # (prometheus|loki|tempo). {} => fall back to today's name-based binding (FR-7).
    # Consumed by the dashboard renderer to emit `datasource: {type, uid}`.
    datasource_uids: Dict[str, str] = field(default_factory=dict)
    # collector_enrichment FR-1b (REQ_COLLECTOR_ENRICHMENT): per-service business context,
    # ALREADY resolved (per-target over project, field-by-field) by the ContextCore producer and
    # forwarded on instrumentation_hints[svc].business = {criticality?, owner?}. Consumed only by
    # generate_collector_enrichment to source the OTTL transform/business processor. Absent ⇒
    # ""/None ⇒ the service contributes no enrichment statement (byte-identical to pre-feature).
    # No SDK-side project fallback (the producer already applied it — NR-2).
    criticality: str = ""
    owner: Optional[str] = None


@dataclass
class FunctionalRequirement:
    """A per-FR observability intent forwarded from the plan (#226 FR-4/FR-5, CR-1).

    ``signal_kind`` is the normative enum owned by the #226 requirements doc
    (availability|latency|throughput|queue_depth|retry_rate|freshness|run_success|
    saturation|lag|custom). ``target`` is an optional threshold; ``service`` optionally
    binds the FR to one service. Absent ``functional[]`` ⇒ empty list ⇒ pre-#226 path.
    """

    id: str = ""
    signal_kind: str = ""
    description: str = ""
    target: Optional[str] = None
    service: Optional[str] = None


@dataclass
class BusinessContext:
    """Business context extracted from .contextcore.yaml."""

    criticality: str = "medium"
    # Deployment topology (importance-scaled-slo Increment 2): "installed" (local/single-user) ⇒
    # extremely forgiving SLOs; "deployed"/None ⇒ the criticality scale. From spec.deployment.mode.
    deployment_mode: Optional[str] = None
    # From spec.deployment.runtime (compose | kubernetes | unknown | None). Drives the runtime-correct
    # artifact set — notably: an explicit 'unknown' fails the ServiceMonitor gate closed (k8s CRD needs
    # POSITIVE k8s evidence; a defaulted Deployment target on an unknown runtime is a dead-k8s FP-3).
    deployment_runtime: Optional[str] = None
    availability: Optional[str] = None  # e.g. "99.9"
    latency_p99: Optional[str] = None  # e.g. "500ms"
    throughput: Optional[str] = None  # e.g. "100rps"
    error_budget: Optional[str] = None  # e.g. "0.1"
    dashboard_placement: str = "standard"
    owner: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    slo_window: str = "30d"
    # Delivery fields consumed from the ContextCore-authored manifest (FR-CONS-1).
    # Replace hardcoded placeholders in notification_policy / service_monitor /
    # loki_rule / runbook. Shapes verified against real .contextcore.yaml (plan Phase 0).
    alert_channels: List[str] = field(default_factory=list)  # spec.observability.alertChannels
    owners: List[Dict[str, Any]] = field(default_factory=list)  # metadata.owners: [{team,slack?,email?}]
    # Authored alert receivers from observability.yaml `alerting.receivers`, parsed by
    # `spec.from_observability_yaml` (the ONE canonical receiver-parsing entry point —
    # REQ_NOTIFICATION_POLICY FR-1/FR-2). Each Receiver{name,type,target,severities} carries
    # the DECLARED channel type + env-indirected secret (`target`). notification_policy binds
    # to this instead of guessing channel type from string shape. Empty ⇒ routed channels with
    # no matching receiver are emitted UNRESOLVED-REQUIRED (FR-3/FR-3a), never silently Slack.
    receivers: List[Receiver] = field(default_factory=list)
    metrics_interval: Optional[str] = None  # spec.observability.metricsInterval, e.g. "30s"
    targets: List[Dict[str, Any]] = field(default_factory=list)  # spec.targets: [{kind,name,namespace}]
    # OQ-8 resolved (pipeline-requirements R2-F1/F2): optional manifest fields, env-overridable.
    # Precedence env > manifest > default/omit; the env tier is read at the call sites.
    prometheus_datasource: Optional[str] = None  # spec.observability.prometheusDatasource
    runbook_base: Optional[str] = None  # spec.observability.runbookBase (HTTPS prefix)
    # Declarative policy maps resolved from spec.observability (None → consumers use hardcoded
    # defaults). Populated by load_business_context via obs_config; same precedence as personas.
    severity_map: Optional[Dict[str, str]] = None        # criticality → alert severity
    default_thresholds: Optional[Dict[str, str]] = None  # SLO default thresholds
    # Importance-scaled SLO thresholds from the config file (+ manifest override). Nested
    # <criticality>.<deployment_mode|default>.{availability, latency_p99}. None ⇒ resolver loads the
    # config-file base itself (design: importance-scaled-slo, FR-7).
    importance_thresholds: Optional[Dict[str, Any]] = None
    quality_thresholds: Optional[Dict[str, float]] = None  # portal quality-gauge bands
    # REQ_NOTIFICATION_POLICY FR-9: overridable Alertmanager route grouping. Keys:
    # group_by (list), group_wait (str), repeat_interval (str). None ⇒ built-in defaults.
    notification_grouping: Optional[Dict[str, Any]] = None
    # #226 FR-4/FR-5: per-FR observability intents forwarded from the plan
    # (spec.requirements.functional[]). Empty until CR-1 ships upstream ⇒ pre-#226 path.
    functional_requirements: List["FunctionalRequirement"] = field(default_factory=list)
    # REQ-01 FR-3: manifest-declarable metric profiles. ``name -> descriptor-axis
    # dict`` from spec.observability.metricsProfiles (or a top-level metadata
    # ``metricsProfiles`` on the export path). Resolved by ``resolve_descriptor``
    # with the same precedence as the built-in ``_PROFILES`` (built-in name wins on
    # collision). Empty ⇒ built-in profiles only (byte-identical to pre-FR-3).
    metric_profiles: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def routing_channels(self) -> List[str]:
        """Channel identifiers for alert routing, with the Phase-0 fallback chain:
        spec.observability.alertChannels → metadata.owners[].slack → []
        (empty → the consumer treats notification routing as required-unresolved,
        never fabricating a webhook URL)."""
        if self.alert_channels:
            return [str(c) for c in self.alert_channels]
        return [str(o["slack"]) for o in self.owners if isinstance(o, dict) and o.get("slack")]


@dataclass
class DerivationTrace:
    """Records how a value was derived for traceability (REQ-UOM-040)."""

    field: str  # e.g. "alert_severity"
    source: str  # e.g. "manifest.spec.business.criticality"
    transformation: str  # e.g. "high → critical"
    tier: str  # "explicit", "manifest", "default"


@dataclass
class ArtifactResult:
    """Result of generating a single artifact file."""

    artifact_type: str  # runtime label, e.g. "alert_rule", "dashboard_spec", "slo_definition"
    service_id: str
    output_path: str  # relative path within output dir
    status: str  # "generated", "skipped", "error"
    content: str = ""  # YAML content to write
    derivations: List[DerivationTrace] = field(default_factory=list)
    error_message: Optional[str] = None
    quality: Optional[Dict[str, Any]] = None  # REQ-KZ-OBS-706a: {score, checks_passed, checks_total, issues, repairs_applied}
    # Taxonomy keystone (REQ-OAT-023): the five-category domain, the orientation
    # axis, and the declared/runtime type pair. Assigned centrally from
    # _ARTIFACT_TYPE_REGISTRY (REQ-OAT-070a), not hand-set per call site.
    # "" = unset (compat default for records built before stamping).
    category: str = ""        # five-category taxonomy (taxonomy_enums.Category)
    orientation: str = ""     # human | system | bridge (taxonomy_enums.Orientation)
    declared_type: str = ""   # contract/onboarding name (distinct from runtime artifact_type)
    runtime_type: str = ""    # internal generator label (mirrors artifact_type)
    # Emit-vs-cede provenance (REQ-OBS-SHARED-004 / REQ-OAT-052). route_state
    # drives ownership/coverage, NOT category. skip_reason/owner are set only on
    # honest skips; ceded records carry NO source_checksum.
    route_state: str = ""     # taxonomy_enums.RouteState
    skip_reason: Optional[str] = None  # "owned_elsewhere" | "unimplemented"
    owner: Optional[str] = None        # e.g. "contextcore" for owned_elsewhere skips


@dataclass
class CoverageReport:
    """FR-9 coverage/gap accumulator — one typed home for what were previously 11
    parallel local lists (``_fr_empty``/``_ungrounded``/``_suppressed_base``/…) that
    ``generate_observability_artifacts`` assembled by hand into ``report.fr_coverage``.

    Distillation (complexity-distiller D1, S2+S10): the accumulation is the same, but
    the fields are typed and the serialization contract lives in one place next to the
    data instead of being a stringly-typed dict literal built inline in the hot loop.

    ``to_fr_coverage()`` preserves **golden byte-identity**: the first eight keys are
    ALWAYS emitted, in this order; the last three are emitted ONLY when non-empty (an
    empty list would be a new manifest byte versus pre-feature goldens — #300/#307/#308).
    """

    empty_services: List[str] = field(default_factory=list)
    unfulfilled: List[Dict[str, Any]] = field(default_factory=list)
    emitted: List[str] = field(default_factory=list)
    ungrounded_kinds: List[Dict[str, Any]] = field(default_factory=list)
    unverified_base_metrics: List[Dict[str, Any]] = field(default_factory=list)  # #274 advisory (surface unknown)
    suppressed_base_metrics: List[Dict[str, Any]] = field(default_factory=list)  # #274 strict (surface declared non-emitting)
    bound_declared_series: List[Dict[str, Any]] = field(default_factory=list)  # #286 positive (base SLI bound to a real series)
    deferred_declared_kinds: List[Dict[str, Any]] = field(default_factory=list)  # #286 covered-but-not-v1-bindable
    # byte-identity-conditional keys — surfaced only when present (absent, not []):
    bound_declared_functional: List[Dict[str, Any]] = field(default_factory=list)  # #300 D2
    bound_declared_span: List[Dict[str, Any]] = field(default_factory=list)  # #307
    pending_probes: List[Dict[str, Any]] = field(default_factory=list)  # #308 P0

    def to_fr_coverage(self) -> Dict[str, Any]:
        """Serialize to the ``report.fr_coverage`` dict, byte-identical to the prior inline build."""
        fr: Dict[str, Any] = {
            "empty_services": self.empty_services,
            "unfulfilled": self.unfulfilled,
            "emitted": self.emitted,
            "ungrounded_kinds": self.ungrounded_kinds,
            "unverified_base_metrics": self.unverified_base_metrics,
            "suppressed_base_metrics": self.suppressed_base_metrics,
            "bound_declared_series": self.bound_declared_series,
            "deferred_declared_kinds": self.deferred_declared_kinds,
        }
        if self.bound_declared_functional:
            fr["bound_declared_functional"] = self.bound_declared_functional
        if self.bound_declared_span:
            fr["bound_declared_span"] = self.bound_declared_span
        if self.pending_probes:
            fr["pending_probes"] = self.pending_probes
        return fr


@dataclass
class GenerationReport:
    """Summary of all generated artifacts (REQ-UOM-004)."""

    project_id: Optional[str]
    generated_at: str
    artifacts: List[ArtifactResult] = field(default_factory=list)
    services_processed: int = 0
    services_skipped: int = 0
    # Artifact types the onboarding contract declares as required (Closure 3A).
    declared_artifact_types: List[str] = field(default_factory=list)
    # Per-metric / per-declared-type route_state classification (REQ-OBS-SHARED-004).
    # Each row: {name, category, route_state, status, classification_source, [owner]}.
    # The authoritative emit-vs-cede provenance surface, NOT inferred from category.
    route_states: List[Dict[str, Any]] = field(default_factory=list)
    # #226 FR-9: FR + SLI-kind coverage — distinguishes two gap classes so the pilot's
    # "6 of 7 FRs → nothing" is visible, not masked. Keys: `empty_services` (resolved=∅,
    # no kind/transport), `unfulfilled` (declared signal_kind, ungroundable ⇒ produced=0),
    # `emitted` (FR ids that produced an artifact). Empty when no functional[] (pre-#226).
    fr_coverage: Dict[str, Any] = field(default_factory=dict)
    # product-gap metric-coverage evaluator union (Step 1): per-service expected-set
    # provenance + AffordanceMap disposition (dry-run and non-dry share this shape).
    metric_expected: Dict[str, Any] = field(default_factory=dict)
    # product-gap metric-coverage coverage-bind (Step 2/2a, FR-2/FR-7): per-service
    # AffordanceMap-derived panel-bind evidence (families admitted, panels added).
    coverage_bind: Dict[str, Any] = field(default_factory=dict)
    # product-gap metric-coverage orientation bind (system/bridge residual): AffordanceMap-
    # admitted families into slo_definition (system) + alert_rule (bridge) so
    # avg_metric_coverage_system/bridge move above 0 on the same expected set.
    orientation_bind: Dict[str, Any] = field(default_factory=dict)
    # product-gap red-dashboards RED bind (pilot-gap_red_dashboards Step 2, FR-1/FR-3/
    # FR-7): per-service locus-biased RED (rate/error/duration) panel-bind evidence,
    # plus explicit skip reasons for no_source_locus / transport_only rows (FR-5).
    red_bind: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ArtifactTypeSpec:
    """One declarative registry row (REQ-OAT-070a)."""

    declared_type: str
    runtime_type: str
    category: str        # Category value (five-category taxonomy)
    orientation: str     # Orientation value
    requires_declaration: bool
    order: int


def rollup_avg_by_type(services: Dict[str, Any]) -> Dict[str, float]:
    """Per-artifact-type score rollup (``avg_{atype}_score``) from a quality
    ``services`` dict — the SINGLE source both ``_write_quality_report`` and
    ``merge_quality_services`` use.

    Context-Correctness-by-Construction (REQ-01 FR-7 principle): the per-type
    rollup is derived one way from the same ``services`` shape, so neither
    producer can silently construct an aggregate missing a per-type key for a
    type present in ``services`` — the class that let ``merge_quality_services``
    drop ``avg_dashboard_spec_score`` and leave the grader reading ``0`` (bus
    93e86298 / commit 006fd7ef). Non-artifact per-service keys (``composite_score``
    and the ``metric_coverage_*`` floats, ``expected_sources``) carry no ``score``
    and are excluded.
    """
    by_type: Dict[str, List[float]] = {}
    for block in services.values():
        if not isinstance(block, dict):
            continue
        for atype, entry in block.items():
            if isinstance(entry, dict) and "score" in entry:
                try:
                    by_type.setdefault(atype, []).append(float(entry["score"]))
                except (TypeError, ValueError):
                    continue
    return {
        f"avg_{atype}_score": round(sum(scores) / len(scores), 4)
        for atype, scores in by_type.items()
        if scores
    }


# ---------------------------------------------------------------------------
# FieldState — explicit-state emission (CCbC Tier B, Phase 1)
# ---------------------------------------------------------------------------
#
# REQ: docs/design/FIELDSTATE_EXPLICIT_STATE_REQUIREMENTS.md
#
# The `metric_coverage_*` fields on `observability-quality.json` today emit a
# bare `0.0` (computed) OR are ABSENT (the affordance-merge path never ran the
# computation). Both render to the SAME consumer conclusion ("0"), so a real
# `0` and a "never computed" are indistinguishable — the misread class that
# stuck the structural grade at B (bus 93e86298 / gen-report-card.py:158/:299
# `agg.get(...) or 0`).
#
# `FieldState` makes the state EXPLICIT: `{value, state, reason}` where a `null`
# is unambiguously "not measured" and a `0.0` is unambiguously "measured zero"
# (FR-4). `render_field_state` is the SINGLE serializer (FR-9): it produces BOTH
# the plain-value channel (channel A, DERIVED from `FieldState.value`) and the
# structured sidecar (channel B). Neither producer may construct the plain value
# and the sidecar independently — that is the drift this whole feature exists to
# kill (FR-5/FR-8/FR-21).

# The closed enum of states (FR-2). `unbound` is RESERVED for the Phase-3
# live-binding surface (deployed-but-unscraped) and is NOT emitted by the
# statically-computable `metric_coverage_*` Phase-1 producers.
FIELD_STATE_NAMES = ("computed", "not_computed", "excluded", "unbound")


@dataclass(frozen=True)
class FieldState:
    """Explicit state for a migrated scoring field (FR-1..FR-4).

    Serializes to ``{"value": <float|null>, "state": <str>, "reason": <str|null>,
    "expected": [...]?, "covered": [...]?}``. ``value`` is a ``float`` iff
    ``state == "computed"`` (FR-4); ``reason`` is a non-empty ``str`` iff
    ``state != "computed"`` (FR-3). ``expected``/``covered`` are OPTIONAL and
    emitted only when non-empty (byte-identity discipline mirroring
    ``CoverageReport.to_fr_coverage``).

    Validation is enforced by ``__post_init__`` (FR-19) so no ill-formed
    ``FieldState`` can be constructed — the single guard that makes a ``null``
    unambiguously "not measured" and a ``0.0`` unambiguously "measured zero".
    """

    value: Optional[float]
    state: str
    reason: Optional[str] = None
    expected: List[str] = field(default_factory=list)
    covered: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # FR-19 (a): unknown state.
        if self.state not in FIELD_STATE_NAMES:
            raise ValueError(
                f"FieldState.state must be one of {FIELD_STATE_NAMES}, got {self.state!r}"
            )
        if self.state == "computed":
            # FR-19 (b): computed with value None.
            if self.value is None:
                raise ValueError(
                    "FieldState(state='computed') requires a float value, got None"
                )
            # FR-3: reason must be null/omitted when computed.
            if self.reason is not None and self.reason != "":
                raise ValueError(
                    "FieldState(state='computed') must not carry a reason "
                    f"(got {self.reason!r})"
                )
        else:
            # FR-19 (c): non-computed with a value.
            if self.value is not None:
                raise ValueError(
                    f"FieldState(state={self.state!r}) requires value=None, "
                    f"got {self.value!r}"
                )
            # FR-19 (d): non-computed with empty/absent reason.
            if not self.reason:
                raise ValueError(
                    f"FieldState(state={self.state!r}) requires a non-empty reason"
                )


def render_field_state(fs: "FieldState") -> Tuple[Optional[float], Dict[str, Any]]:
    """The SINGLE serializer (FR-9): one ``FieldState`` → (plain_value, sidecar_dict).

    Returns a 2-tuple whose FIRST element is the canonical plain-value channel
    (channel A, FR-6) — ``fs.value`` verbatim (a ``float`` when ``computed``,
    else ``None``) — and whose SECOND element is the structured sidecar (channel
    B, FR-7): ``{"value", "state", "reason"}`` plus the OPTIONAL ``expected`` /
    ``covered`` keys emitted only when non-empty.

    Both channels derive from the SAME instance, so the plain value can never
    drift from the sidecar's ``value`` (FR-5). ``FieldState.__post_init__`` has
    already refused any ill-formed state (FR-19), so this is a pure render.
    """
    sidecar: Dict[str, Any] = {
        "value": fs.value,
        "state": fs.state,
        "reason": fs.reason,
    }
    if fs.expected:
        sidecar["expected"] = list(fs.expected)
    if fs.covered:
        sidecar["covered"] = list(fs.covered)
    return fs.value, sidecar
