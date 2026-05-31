"""
Descriptor → onboarding-metadata bridge (REQ-AAO-008): closes the loop so the SDK is
its own *declare, don't guess* producer for its own telemetry.

``generate_manifest()`` already collects the SDK's `_OTEL_DESCRIPTORS`. This module
projects that manifest into the ``manifest_declared`` metric-set shape the artifact
generator consumes from onboarding metadata — produced from the manifest, not
hand-authored. Each entry carries the exported Prometheus name + type + the taxonomy
axes + ``route_state=sdk_emitted`` (REQ-OBS-SHARED-004), so a downstream generator
routes these as *produced* artifacts without inference.
"""

from typing import Any, Dict, List, Optional

from .manifest import ObservabilityManifest, generate_manifest
from .parity import exported_name

# OTel instrument kind -> Prometheus-style metric type.
_INSTRUMENT_TO_TYPE = {
    "counter": "counter",
    "observable_counter": "counter",
    "histogram": "histogram",
    "up_down_counter": "gauge",
    "observable_up_down_counter": "gauge",
    "gauge": "gauge",
    "observable_gauge": "gauge",
}


def manifest_to_declared_metrics(
    manifest: Optional[ObservabilityManifest] = None,
) -> List[Dict[str, Any]]:
    """Project manifest metric descriptors into ``manifest_declared`` entries.

    Entry shape: ``{name, type, source, category, orientation, route_state}`` where
    ``name`` is the **exported** Prometheus name operators query.
    """
    if manifest is None:
        manifest = generate_manifest()

    entries: List[Dict[str, Any]] = []
    for m in manifest.metrics:
        entry: Dict[str, Any] = {
            "name": exported_name(m.name, m.prometheus_name),
            "type": _INSTRUMENT_TO_TYPE.get(m.instrument, "gauge"),
            "source": "manifest",
            "route_state": "sdk_emitted",
        }
        # Carry the taxonomy axes when set (compat: omit when unset).
        if m.category:
            entry["category"] = m.category
        if m.orientation:
            entry["orientation"] = m.orientation
        entries.append(entry)
    return entries


def build_sdk_self_instrumentation_hint(
    service_id: str = "startd8",
    transport: str = "otlp",
    manifest: Optional[ObservabilityManifest] = None,
) -> Dict[str, Any]:
    """Build an ``instrumentation_hints`` service entry describing the SDK's OWN
    telemetry, with ``manifest_declared`` produced from the manifest (REQ-AAO-008).
    """
    return {
        "service_id": service_id,
        "transport": transport,
        "language": "python",
        "metrics": {
            "manifest_declared": manifest_to_declared_metrics(manifest),
        },
    }
