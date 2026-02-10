"""
Observability manifest for the StartD8 SDK.

Provides machine-readable declarations of the SDK's telemetry surface:
metrics, spans, events, dashboard references, SLO and alert templates.

Usage:
    from startd8.observability import ObservabilityManifest

    manifest = ObservabilityManifest.from_yaml(
        "docs/capability-index/startd8.observability.manifest.yaml"
    )
    print(f"Metrics: {len(manifest.metrics)}")
"""

from .manifest import (
    MetricDescriptor,
    LabelDescriptor,
    SpanDescriptor,
    EventTypeDescriptor,
    DashboardRef,
    SLOTemplate,
    AlertTemplate,
    ObservabilityManifest,
    generate_manifest,
)

__all__ = [
    "MetricDescriptor",
    "LabelDescriptor",
    "SpanDescriptor",
    "EventTypeDescriptor",
    "DashboardRef",
    "SLOTemplate",
    "AlertTemplate",
    "ObservabilityManifest",
    "generate_manifest",
]
