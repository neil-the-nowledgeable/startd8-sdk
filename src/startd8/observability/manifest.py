"""
Data classes and generator for the StartD8 observability manifest.

The manifest declares the SDK's full telemetry surface in a machine-readable
format that ContextCore agents and Wayfinder can consume to auto-generate
dashboards, alerts, and SLOs.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import yaml


def _axis_value(value: Any) -> str:
    """Coerce a taxonomy axis to its plain string value.

    Real descriptors declare plain strings, but a ``Category``/``Orientation``
    enum member may be passed programmatically; ``str``-enums serialize to a
    ``!!python/object`` tag under PyYAML, so normalize to the underlying value.
    """
    return value.value if isinstance(value, Enum) else value


# ---------------------------------------------------------------------------
# Descriptor data classes
# ---------------------------------------------------------------------------


@dataclass
class LabelDescriptor:
    """Describes a metric or span label/attribute."""

    name: str
    description: str = ""
    values: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"name": self.name}
        if self.description:
            d["description"] = self.description
        if self.values:
            d["values"] = self.values
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LabelDescriptor":
        return cls(
            name=d["name"],
            description=d.get("description", ""),
            values=d.get("values"),
        )


@dataclass
class MetricDescriptor:
    """Describes an OpenTelemetry metric instrument."""

    name: str
    instrument: str  # counter, histogram, gauge, up_down_counter, observable_gauge
    unit: str
    description: str
    meter: str = ""
    source_file: str = ""
    labels: List[str] = field(default_factory=list)
    prometheus_name: Optional[str] = None
    dashboard_hints: Optional[Dict[str, Any]] = None
    # Taxonomy axes (REQ-OBS-SHARED-001). "" = unset (compat bridge, not an
    # accepted end state — see the completeness gate). Domains: taxonomy_enums.
    category: str = ""
    orientation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "name": self.name,
            "instrument": self.instrument,
            "unit": self.unit,
            "description": self.description,
        }
        if self.meter:
            d["meter"] = self.meter
        if self.source_file:
            d["source_file"] = self.source_file
        if self.labels:
            d["labels"] = self.labels
        if self.prometheus_name:
            d["prometheus_name"] = self.prometheus_name
        if self.dashboard_hints:
            d["dashboard_hints"] = self.dashboard_hints
        if self.category:
            d["category"] = _axis_value(self.category)
        if self.orientation:
            d["orientation"] = _axis_value(self.orientation)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MetricDescriptor":
        return cls(
            name=d["name"],
            instrument=d["instrument"],
            unit=d["unit"],
            description=d["description"],
            meter=d.get("meter", ""),
            source_file=d.get("source_file", ""),
            labels=d.get("labels", []),
            prometheus_name=d.get("prometheus_name"),
            dashboard_hints=d.get("dashboard_hints"),
            category=d.get("category", ""),
            orientation=d.get("orientation", ""),
        )


@dataclass
class SpanDescriptor:
    """Describes an OpenTelemetry span pattern."""

    name_pattern: str
    kind: str = "INTERNAL"  # CLIENT, INTERNAL, SERVER, PRODUCER, CONSUMER
    source_file: str = ""
    attributes: List[str] = field(default_factory=list)
    events: List[str] = field(default_factory=list)
    attributes_dynamic: bool = False
    # Taxonomy axes (REQ-OBS-SHARED-001). "" = unset. Domains: taxonomy_enums.
    category: str = ""
    orientation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "name_pattern": self.name_pattern,
            "kind": self.kind,
        }
        if self.source_file:
            d["source_file"] = self.source_file
        if self.attributes:
            d["attributes"] = self.attributes
        if self.events:
            d["events"] = self.events
        if self.attributes_dynamic:
            d["attributes_dynamic"] = True
        if self.category:
            d["category"] = _axis_value(self.category)
        if self.orientation:
            d["orientation"] = _axis_value(self.orientation)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SpanDescriptor":
        return cls(
            name_pattern=d["name_pattern"],
            kind=d.get("kind", "INTERNAL"),
            source_file=d.get("source_file", ""),
            attributes=d.get("attributes", []),
            events=d.get("events", []),
            attributes_dynamic=d.get("attributes_dynamic", False),
            category=d.get("category", ""),
            orientation=d.get("orientation", ""),
        )


@dataclass
class EventTypeDescriptor:
    """Describes a StartD8 EventBus event type."""

    name: str
    # Instrument-grouping axis (agent, cost, pipeline, truncation, job,
    # enhancement, storage, system) — NOT the 5-category observability taxonomy.
    # Renamed from `category` to `event_group` (REQ-OBS-SHARED-001a) so `category`
    # means the taxonomy uniformly across descriptor classes.
    event_group: str
    data_fields: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "name": self.name,
            "event_group": self.event_group,
        }
        if self.data_fields:
            d["data_fields"] = self.data_fields
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EventTypeDescriptor":
        # Accept the legacy `category` key as an alias for one release so saved
        # manifests/YAML still deserialize (REQ-OBS-SHARED-001a).
        return cls(
            name=d["name"],
            event_group=d.get("event_group", d.get("category", "")),
            data_fields=d.get("data_fields", []),
        )


@dataclass
class DashboardRef:
    """Reference to a Grafana dashboard JSON file."""

    uid: str
    title: str
    file_path: str
    datasources: List[str] = field(default_factory=list)
    metrics_used: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "uid": self.uid,
            "title": self.title,
            "file_path": self.file_path,
            "datasources": self.datasources,
            "metrics_used": self.metrics_used,
        }
        if self.tags:
            d["tags"] = self.tags
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DashboardRef":
        return cls(
            uid=d["uid"],
            title=d["title"],
            file_path=d["file_path"],
            datasources=d.get("datasources", []),
            metrics_used=d.get("metrics_used", []),
            tags=d.get("tags", []),
        )


@dataclass
class SLOTemplate:
    """Template for a Service Level Objective."""

    name: str
    description: str
    metric: str
    query: str
    target: float
    window: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "metric": self.metric,
            "query": self.query,
            "target": self.target,
            "window": self.window,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SLOTemplate":
        return cls(
            name=d["name"],
            description=d["description"],
            metric=d["metric"],
            query=d["query"],
            target=d["target"],
            window=d["window"],
        )


@dataclass
class AlertTemplate:
    """Template for a Prometheus/Grafana alert rule."""

    name: str
    description: str
    severity: str  # warning, critical
    metric: str
    expr: str
    for_duration: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "severity": self.severity,
            "metric": self.metric,
            "expr": self.expr,
            "for_duration": self.for_duration,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AlertTemplate":
        return cls(
            name=d["name"],
            description=d["description"],
            severity=d["severity"],
            metric=d["metric"],
            expr=d["expr"],
            for_duration=d["for_duration"],
        )


# ---------------------------------------------------------------------------
# Top-level manifest
# ---------------------------------------------------------------------------


@dataclass
class ObservabilityManifest:
    """
    Machine-readable declaration of the SDK's full telemetry surface.

    Contains metrics, spans, events, dashboard references, SLO templates,
    and alert templates.
    """

    manifest_id: str = "startd8.observability"
    version: str = "1.0.0"
    description: str = ""
    resource_attributes: List[str] = field(default_factory=list)
    metrics: List[MetricDescriptor] = field(default_factory=list)
    spans: List[SpanDescriptor] = field(default_factory=list)
    event_types: List[EventTypeDescriptor] = field(default_factory=list)
    dashboards: List[DashboardRef] = field(default_factory=list)
    slo_templates: List[SLOTemplate] = field(default_factory=list)
    alert_templates: List[AlertTemplate] = field(default_factory=list)

    # ---- serialization ----------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Convert manifest to a plain dict suitable for YAML serialization."""
        return {
            "manifest_id": self.manifest_id,
            "version": self.version,
            "description": self.description,
            "resource_attributes": self.resource_attributes,
            "metrics": [m.to_dict() for m in self.metrics],
            "spans": [s.to_dict() for s in self.spans],
            "event_types": [e.to_dict() for e in self.event_types],
            "dashboards": [d.to_dict() for d in self.dashboards],
            "slo_templates": [s.to_dict() for s in self.slo_templates],
            "alert_templates": [a.to_dict() for a in self.alert_templates],
        }

    def to_yaml(self) -> str:
        """Serialize the manifest to a YAML string."""
        return yaml.dump(
            self.to_dict(),
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ObservabilityManifest":
        """Construct a manifest from a plain dict."""
        return cls(
            manifest_id=d.get("manifest_id", "startd8.observability"),
            version=d.get("version", "1.0.0"),
            description=d.get("description", ""),
            resource_attributes=d.get("resource_attributes", []),
            metrics=[MetricDescriptor.from_dict(m) for m in d.get("metrics", [])],
            spans=[SpanDescriptor.from_dict(s) for s in d.get("spans", [])],
            event_types=[
                EventTypeDescriptor.from_dict(e) for e in d.get("event_types", [])
            ],
            dashboards=[DashboardRef.from_dict(db) for db in d.get("dashboards", [])],
            slo_templates=[
                SLOTemplate.from_dict(s) for s in d.get("slo_templates", [])
            ],
            alert_templates=[
                AlertTemplate.from_dict(a) for a in d.get("alert_templates", [])
            ],
        )

    @classmethod
    def from_yaml(cls, path: str) -> "ObservabilityManifest":
        """Load a manifest from a YAML file on disk."""
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


def generate_manifest() -> ObservabilityManifest:
    """
    Introspect the SDK and produce a manifest with code-derived signals.

    Calls collector functions for metrics, spans, events, and dashboards.
    Hand-authored sections (SLO/alert templates) are NOT included here;
    they live in the committed YAML and are preserved during drift checks.
    """
    from .collector import (
        collect_metric_descriptors,
        collect_span_descriptors,
        collect_event_types,
        collect_dashboard_refs,
    )

    return ObservabilityManifest(
        manifest_id="startd8.observability",
        version="1.0.0",
        description="Auto-generated observability manifest for the StartD8 SDK.",
        resource_attributes=[
            "service.name",
            "service.version",
            "io.contextcore.project.id",
            "io.contextcore.project.name",
            "io.contextcore.task.id",
            "io.contextcore.sprint.id",
            "io.contextcore.business.criticality",
        ],
        metrics=collect_metric_descriptors(),
        spans=collect_span_descriptors(),
        event_types=collect_event_types(),
        dashboards=collect_dashboard_refs(),
    )
