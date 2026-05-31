"""
Collector that introspects SDK modules to gather telemetry descriptors.

Uses lazy imports within functions to avoid circular import issues.
Only invoked by the generator script, never at runtime.
"""

import json
import logging
from pathlib import Path
from typing import List

from .manifest import (
    DashboardRef,
    EventTypeDescriptor,
    MetricDescriptor,
    SpanDescriptor,
)

logger = logging.getLogger(__name__)

# Modules that declare _OTEL_DESCRIPTORS, keyed by import path.
_INSTRUMENTED_MODULES = [
    ("startd8.session_tracking", "src/startd8/session_tracking.py"),
    ("startd8.costs.otel_metrics", "src/startd8/costs/otel_metrics.py"),
    ("startd8.events.otel_bridge", "src/startd8/events/otel_bridge.py"),
    ("startd8.agents.tracked", "src/startd8/agents/tracked.py"),
    ("startd8.workflows.base", "src/startd8/workflows/base.py"),
    ("startd8.orchestration", "src/startd8/orchestration.py"),
    ("startd8.contractors.adapters.contextcore", "src/startd8/contractors/adapters/contextcore.py"),
    ("startd8.contractors.artisan_contractor", "src/startd8/contractors/artisan_contractor.py"),
    ("startd8.contractors.artisan_phases.runner", "src/startd8/contractors/artisan_phases/runner.py"),
    ("startd8.repair.orchestrator", "src/startd8/repair/orchestrator.py"),
]

# Event type → instrument-group mapping (derived from EventType enum grouping).
# This is the EventTypeDescriptor.event_group axis, NOT the observability taxonomy.
_EVENT_GROUPS = {
    "AGENT_CALL_START": "agent",
    "AGENT_CALL_COMPLETE": "agent",
    "AGENT_CALL_ERROR": "agent",
    "AGENT_MANUAL_PAUSED": "agent",
    "AGENT_AUTO_PAUSED": "agent",
    "AGENT_MANUAL_RESUMED": "agent",
    "AGENT_AUTO_RESUMED": "agent",
    "COST_RECORDED": "cost",
    "BUDGET_WARNING": "cost",
    "BUDGET_EXCEEDED": "cost",
    "BUDGET_CREATED": "cost",
    "BUDGET_UPDATED": "cost",
    "BUDGET_DELETED": "cost",
    "USAGE_LIMIT_WARNING": "usage",
    "USAGE_LIMIT_EXCEEDED": "usage",
    "USAGE_LIMIT_CRITICAL": "usage",
    "PIPELINE_START": "pipeline",
    "PIPELINE_STEP_START": "pipeline",
    "PIPELINE_STEP_COMPLETE": "pipeline",
    "PIPELINE_COMPLETE": "pipeline",
    "PIPELINE_STEP_RETRY": "pipeline",
    "PIPELINE_ERROR": "pipeline",
    "JOB_QUEUED": "job",
    "JOB_PROCESSING_START": "job",
    "JOB_PROCESSING_COMPLETE": "job",
    "JOB_FAILED": "job",
    "JOB_ARCHIVED": "job",
    "ENHANCEMENT_START": "enhancement",
    "ENHANCEMENT_STEP_START": "enhancement",
    "ENHANCEMENT_STEP_COMPLETE": "enhancement",
    "ENHANCEMENT_COMPLETE": "enhancement",
    "PROMPT_CREATED": "storage",
    "RESPONSE_RECORDED": "storage",
    "BENCHMARK_CREATED": "storage",
    "BENCHMARK_COMPLETED": "storage",
    "TRUNCATION_DETECTED": "truncation",
    "TRUNCATION_WARNING": "truncation",
    "TRUNCATION_PREFLIGHT_REJECT": "truncation",
    "QUALITY_GATE_RESULT": "quality",
    "SYSTEM_ERROR": "system",
    "SYSTEM_WARNING": "system",
    "FRAMEWORK_INITIALIZED": "system",
    "CACHE_CLEARED": "system",
}


def _load_descriptors(module_path: str, source_file: str) -> dict:
    """Import a module and return its _OTEL_DESCRIPTORS, or empty dict."""
    import importlib

    try:
        mod = importlib.import_module(module_path)
        descriptors = getattr(mod, "_OTEL_DESCRIPTORS", {})
        return descriptors
    except Exception as exc:
        logger.warning("Failed to load descriptors from %s: %s", module_path, exc)
        return {}


# ---------------------------------------------------------------------------
# Public collector functions
# ---------------------------------------------------------------------------


def collect_metric_descriptors() -> List[MetricDescriptor]:
    """Walk instrumented modules and collect all metric descriptors."""
    result: List[MetricDescriptor] = []
    seen_names: set = set()

    for module_path, source_file in _INSTRUMENTED_MODULES:
        desc = _load_descriptors(module_path, source_file)
        for m in desc.get("metrics", []):
            if m["name"] in seen_names:
                continue
            seen_names.add(m["name"])
            result.append(
                MetricDescriptor(
                    name=m["name"],
                    instrument=m["instrument"],
                    unit=m["unit"],
                    description=m["description"],
                    meter=m.get("meter", ""),
                    source_file=source_file,
                    labels=m.get("labels", []),
                    # Pass through optional + taxonomy fields (REQ-OBS-SHARED-001,
                    # R3-F1): without this the collector silently drops them and
                    # the generated manifest carries empty axes.
                    prometheus_name=m.get("prometheus_name"),
                    dashboard_hints=m.get("dashboard_hints"),
                    category=m.get("category", ""),
                    orientation=m.get("orientation", ""),
                )
            )
    return result


def collect_span_descriptors() -> List[SpanDescriptor]:
    """Walk instrumented modules and collect all span descriptors."""
    result: List[SpanDescriptor] = []

    for module_path, source_file in _INSTRUMENTED_MODULES:
        desc = _load_descriptors(module_path, source_file)
        for s in desc.get("spans", []):
            result.append(
                SpanDescriptor(
                    name_pattern=s["name_pattern"],
                    kind=s.get("kind", "INTERNAL"),
                    source_file=source_file,
                    attributes=s.get("attributes", []),
                    events=s.get("events", []),
                    attributes_dynamic=s.get("attributes_dynamic", False),
                    # Pass through taxonomy fields (REQ-OBS-SHARED-001, R3-F1).
                    category=s.get("category", ""),
                    orientation=s.get("orientation", ""),
                )
            )
    return result


def collect_event_types() -> List[EventTypeDescriptor]:
    """Introspect the EventType enum and return descriptors for each member."""
    from startd8.events.types import EventType

    result: List[EventTypeDescriptor] = []
    for member in EventType:
        event_group = _EVENT_GROUPS.get(member.name, "unknown")
        result.append(
            EventTypeDescriptor(
                name=member.name,
                event_group=event_group,
            )
        )
    return result


def collect_dashboard_refs() -> List[DashboardRef]:
    """Scan dashboards/ for JSON files and extract metadata."""
    result: List[DashboardRef] = []

    # Find repo root relative to this file
    repo_root = Path(__file__).resolve().parents[3]  # src/startd8/observability -> repo root
    dashboards_dir = repo_root / "dashboards"

    if not dashboards_dir.is_dir():
        return result

    for json_file in sorted(dashboards_dir.glob("*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read dashboard %s: %s", json_file, exc)
            continue

        uid = data.get("uid", json_file.stem)
        title = data.get("title", json_file.stem)

        # Collect datasource types
        datasources: list = []
        for ds in data.get("__inputs", []):
            ds_type = ds.get("type", "")
            if ds_type.startswith("datasource"):
                ds_name = ds.get("pluginId", ds.get("name", ""))
                if ds_name and ds_name not in datasources:
                    datasources.append(ds_name)

        # Collect metric names referenced in panel targets
        metrics_used: list = []
        for panel in data.get("panels", []):
            for target in panel.get("targets", []):
                expr = target.get("expr", "")
                # Extract metric names from PromQL
                for prefix in ("startd8_", "startd8."):
                    idx = expr.find(prefix)
                    while idx != -1:
                        end = idx
                        while end < len(expr) and (expr[end].isalnum() or expr[end] in "._"):
                            end += 1
                        metric_name = expr[idx:end]
                        if metric_name and metric_name not in metrics_used:
                            metrics_used.append(metric_name)
                        idx = expr.find(prefix, end)

        result.append(
            DashboardRef(
                uid=uid,
                title=title,
                file_path=f"dashboards/{json_file.name}",
                datasources=datasources,
                metrics_used=metrics_used,
            )
        )

    return result
