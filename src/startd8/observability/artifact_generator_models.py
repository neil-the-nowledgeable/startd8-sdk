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


@dataclass(frozen=True)
class ArtifactTypeSpec:
    """One declarative registry row (REQ-OAT-070a)."""

    declared_type: str
    runtime_type: str
    category: str        # Category value (five-category taxonomy)
    orientation: str     # Orientation value
    requires_declaration: bool
    order: int
