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
from .taxonomy_enums import (
    Category,
    Orientation,
    CATEGORY_VALUES,
    ORIENTATION_VALUES,
    is_valid_category,
    is_valid_orientation,
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
    # Taxonomy axes — single source of truth (REQ-OBS-SHARED-001).
    "Category",
    "Orientation",
    "CATEGORY_VALUES",
    "ORIENTATION_VALUES",
    "is_valid_category",
    "is_valid_orientation",
]
