# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Data models for observability artifact generation.

Extracted verbatim from ``artifact_generator.py`` (Tier-2 refactor, step 1).
Pure dataclasses with no dependency on the generator logic. ``artifact_generator``
re-exports these (``from .artifact_generator_models import *``) so existing
import paths keep working.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple  # noqa: F401

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
class ServiceHints:
    """Instrumentation hints for a single service."""

    service_id: str
    transport: str  # "grpc" or "http"
    language: Optional[str] = None
    detected_databases: List[str] = field(default_factory=list)
    convention_metrics: List[ConventionMetric] = field(default_factory=list)
    # Domain-specific metrics declared in the manifest (Closure 1 / Gap 1).
    # Distinct from convention_metrics: these describe what *this* service does
    # (e.g. token burn, cost, truncations) rather than generic OTel HTTP semconv.
    declared_metrics: List[ConventionMetric] = field(default_factory=list)


@dataclass
class BusinessContext:
    """Business context extracted from .contextcore.yaml."""

    criticality: str = "medium"
    availability: Optional[str] = None  # e.g. "99.9"
    latency_p99: Optional[str] = None  # e.g. "500ms"
    throughput: Optional[str] = None  # e.g. "100rps"
    error_budget: Optional[str] = None  # e.g. "0.1"
    dashboard_placement: str = "standard"
    owner: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    slo_window: str = "30d"


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


@dataclass(frozen=True)
class ArtifactTypeSpec:
    """One declarative registry row (REQ-OAT-070a)."""

    declared_type: str
    runtime_type: str
    category: str        # Category value (five-category taxonomy)
    orientation: str     # Orientation value
    requires_declaration: bool
    order: int
